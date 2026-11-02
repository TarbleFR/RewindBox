"""Update full-bindless texture and sampler arrays by changed element, not by full rebuild.

Build 612 Hogwarts Legacy journal (2 November 2026, PID 63118, Core b99e754d): in
the six 5.1 s windows after t=81 the GPU thread allocates 260 MiB/s; the inclusive
'compute' scope (ComputeClass.SendSignalingPcasB) holds 246 MiB/s and 3.5-3.9 s of
every window, and the 'bindings' scope (TextureManager.Commit*Bindings) the same
bytes, so the graphics commits allocate almost nothing. Copies from guest memory
are excluded by complete counters (readCopies: about 1 MiB in 30.6 s; every
copying GetSpan branch of the HostTracked manager, PhysicalMemory and the GPU
memory manager counts). Allocation follows compute time at about 330 MiB per
second of compute work in every window, whatever the number of dispatches (116 to
1610 per window): a per-element cost, not a per-call one.

Shaders whose texture handle is fully dynamic become arrays sized to the whole
texture or sampler pool (BindlessElimination: QueryTextureArrayLengthFromPool =
MaximumId + 1). TextureBindingsArrayCache.UpdateFromPool rebuilds such an array
element by element whenever its pool was written since the last update. The game
writes its pools continuously, and CommitComputeBindings commits on every
dispatch, so every compute dispatch after a pool write walks the whole pool
(descriptor read, texture synchronisation, alias and sampler lookup per element)
and, above 4096 elements, allocates fresh texture and sampler arrays plus the
threaded renderer's two private copies (32 bytes per element; the bounded caches
of adapt_bindless_allocations / adapt_bounded_binding_snapshots stop at 4096).

The array now updates only the elements whose result can differ:
- A synchronised pool replaces Items[id] when a descriptor really changes
  (InvalidateRangeImpl compares it with its cached copy), and a texture that is
  replaced, unmapped or deleted bumps its InvalidatedSequence. An element is
  unchanged when its pool item is the same object as at the last update and its
  resolved texture (format alias included) keeps its InvalidatedSequence; an empty
  element is unchanged only while the pool still marks the id invalid. A sampler
  element is unchanged when the pool's sampler object is the same and alive.
- Changed elements are resolved exactly as the full rebuild does (store signal and
  scale blacklist before the host texture is read) and sent with
  SetTextures / SetSamplers / SetImages(start, run), an offset form every backend
  implements; changes at most 16 elements apart share a run, the unchanged elements
  between them re-sent with the host values recorded when they were bound.
- If a texture was invalidated during the pass (a global epoch that every
  InvalidatedSequence increment moves), a final check of every element (pool item
  and texture sequence) catches a texture that this pass's own lookups removed or
  replaced; without one, pool items changed only for the ids the pass resolved
  itself (RemoveFromPools and UpdatePoolMappings, the only other writers, move the
  epoch). Any mismatch, an alias list destroyed during the pass, another format than
  the one the state was built for, or a scale blacklist that only the end of the
  pass would apply, falls back to the full rebuild. (Build 614 on the iPhone: about
  245 passes of 524288 elements per 5.1 s, about 30 changed per pass, each with this
  check; the check alone was about half of the 1.0-1.1 s per window.) A failed update (delta pass or full
  rebuild) forces the next one to rebuild, even without a pool write.
- The entry's texture set stays exact (reference counts per bound texture), so
  SynchronizeMemory, SignalModified (image stores) and the scale blacklist reach
  exactly the bound textures, as on the cache-hit path.
- A synchronisation can replace the storage of a bound texture and release the host
  texture the array holds (scaled data written by the CPU, a copy dependency, the
  scale blacklist; Texture.ReplaceStorage bumps the sequence). The delivered cache-hit
  path then bound the released host for that draw; the full rebuild did not, as
  GetInternal synchronises before the host is read. Both the hit path and the delta
  path now check the bound sequences after synchronising and rebind otherwise.
- New entries, TextureBuffer arrays (their storage is rebound on every update; no
  per-element state is kept for them) and any failure keep the full rebuild, which
  records the per-element state.
Pool synchronisation, the order of renderer commands and resource lifetimes are
unchanged; memory is still synchronised for every bound texture on every update.

On the device, one gpuWork row and four counters attribute what remains, within the
collector's 4000-character payload bound: 'arrayDelta' (delta passes: calls, time,
bytes), and the elements walked by full pool rebuilds (arrFullElems), scanned and
changed by delta passes (arrDeltaElems, arrDeltaChanged) and rebuilt from constant
buffer handles (arrBufElems: UpdateFromBuffer arrays, untouched here). Counting
allocates nothing. Not measured on the iPhone yet; no FPS claim.
"""
from pathlib import Path

from adapt_session import once

ARRAY_CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
TEXTURE_POOL = 'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs'
TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
DIAGNOSTICS = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
NAMES = [ARRAY_CACHE, TEXTURE_POOL, TEXTURE, DIAGNOSTICS]
ALIAS = 'using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n'

ENTRY_STATE = '''            private int _texturePoolSequence;
            private int _samplerPoolSequence;

            /// <summary>
            /// Per-element state of the last update of a pool array, for delta updates: the pool item, the
            /// resolved texture, its sequence and the host value bound (texture arrays and image arrays), or the
            /// pool sampler and its host value (sampler arrays). Valid only while <see cref="DeltaReady"/>.
            /// </summary>
            public Texture[] DeltaItems;
            public Texture[] DeltaTextures;
            public int[] DeltaSequences;
            public ITexture[] DeltaHosts;
            public Sampler[] DeltaSamplers;
            public ISampler[] DeltaHostSamplers;
            public int DeltaLength;
            public bool DeltaReady;
            public FormatInfo DeltaFormatInfo;
            public int DeltaAliasGeneration;
            public bool DeltaAllBlacklisted;

            /// <summary>
            /// Set while a full rebuild runs and when a delta pass fails: after a failed update, the next one
            /// rebuilds even without a pool write.
            /// </summary>
            public bool ForceRebuild;

            /// <summary>
            /// How many elements resolve to each bound texture, so that a delta update keeps the
            /// texture set exact (every bound texture, with its recorded sequence, and nothing else).
            /// </summary>
            private Dictionary<Texture, int> _deltaReferences;

            /// <summary>
            /// Allocates the per-element state once for an array of <paramref name="length"/> elements. Until the
            /// full rebuild that calls it completes, the entry neither hits nor takes the delta path.
            /// </summary>
            public void PrepareDelta(int length, bool isSampler, FormatInfo formatInfo, int aliasGeneration, bool resScaleUnsupported)
            {
                DeltaReady = false;
                ForceRebuild = true;
                DeltaLength = length;
                DeltaFormatInfo = formatInfo;
                DeltaAliasGeneration = aliasGeneration;
                DeltaAllBlacklisted = resScaleUnsupported;

                if (isSampler)
                {
                    if (DeltaSamplers?.Length != length)
                    {
                        DeltaSamplers = new Sampler[length];
                        DeltaHostSamplers = new ISampler[length];
                    }
                }
                else
                {
                    if (DeltaItems?.Length != length)
                    {
                        DeltaItems = new Texture[length];
                        DeltaTextures = new Texture[length];
                        DeltaSequences = new int[length];
                        DeltaHosts = new ITexture[length];
                    }

                    (_deltaReferences ??= new Dictionary<Texture, int>()).Clear();
                }
            }

            /// <summary>
            /// Records what an element was resolved from and bound to. A full rebuild (<paramref name="replacing"/>
            /// false) has filled the texture set itself, and its recorded sequence is the one stored there; a delta
            /// update replaces the element's previous texture here.
            /// </summary>
            public void RecordDelta(int index, Texture item, Texture texture, ITexture host, Sampler sampler, ISampler hostSampler, bool replacing)
            {
                if (DeltaSamplers != null && DeltaItems == null)
                {
                    DeltaSamplers[index] = sampler;
                    DeltaHostSamplers[index] = hostSampler;
                    return;
                }

                Texture previous = DeltaTextures[index];

                if (replacing && previous != null && --_deltaReferences[previous] == 0)
                {
                    _deltaReferences.Remove(previous);
                    Textures.Remove(previous);
                }

                DeltaItems[index] = item;
                DeltaTextures[index] = texture;
                DeltaHosts[index] = host;

                int sequence = texture?.InvalidatedSequence ?? 0;

                if (texture != null)
                {
                    _deltaReferences[texture] = (_deltaReferences.TryGetValue(texture, out int count) ? count : 0) + 1;

                    if (replacing)
                    {
                        Textures[texture] = sequence;
                    }
                    else if (Textures.TryGetValue(texture, out int stored))
                    {
                        // The full rebuild stored the sequence before blacklisting the texture: keep the two equal so
                        // that a sequence moved by that blacklist re-resolves the element, as a rebuild would.
                        sequence = stored;
                    }
                }

                DeltaSequences[index] = sequence;
            }

            /// <summary>
            /// Synchronizes memory for all textures in the array, then checks that no synchronisation replaced the
            /// storage (and released the host texture) of a bound texture: scaled data written by the CPU, a copy
            /// dependency or the scale blacklist replace it and bump its sequence.
            /// </summary>
            /// <returns>True if the bound host textures are still current</returns>
            public bool SynchronizeMemoryAndValidate(bool isStore, bool blacklistScale)
            {
                SynchronizeMemory(isStore, blacklistScale);

                return ValidateTextures();
            }

            /// <summary>
            /// Checks that the element still resolves to what was recorded, without resolving it.
            /// </summary>
            public bool DeltaUnchanged(int index, TexturePool texturePool, SamplerPool samplerPool, bool isSampler, bool aliasesMoved)
            {
                if (isSampler)
                {
                    Sampler sampler = samplerPool?.GetCachedItem(index);

                    return sampler != null && sampler == DeltaSamplers[index] && !sampler.IsDisposed;
                }

                Texture item = texturePool.PeekForBindingDelta(index, out bool knownInvalid);
                Texture texture = DeltaTextures[index];

                if (item != DeltaItems[index])
                {
                    return false;
                }

                if (item == null)
                {
                    return knownInvalid && texture == null;
                }

                return texture != null && texture.InvalidatedSequence == DeltaSequences[index] &&
                    (!aliasesMoved || texture == item);
            }'''

RESET = '''            public virtual void Reset()
            {
                Textures.Clear();
            }'''
RESET_NEW = '''            public virtual void Reset()
            {
                Textures.Clear();
                DeltaReady = false;
            }'''

HIT = '''            if (!poolModified && !isNewEntry && entry.ValidateTextures())
            {
                entry.SynchronizeMemory(isStore, resScaleUnsupported);

                if (isImage)'''
HIT_NEW = '''            // A synchronisation that replaces a bound texture's storage releases the host texture the array holds:
            // the array is reused only if every bound texture is still current after it (else it is updated below).
            if (!poolModified && !isNewEntry && !entry.ForceRebuild && entry.ValidateTextures() &&
                entry.SynchronizeMemoryAndValidate(isStore, resScaleUnsupported))
            {
                if (isImage)'''

FULL_DISPATCH = '''            if (!isNewEntry)
            {
                entry.Reset();
            }

            int length = (isSampler ? samplerPool.MaximumId : texturePool.MaximumId) + 1;
            length = Math.Min(length, bindingInfo.ArrayLength);

            ISampler[] samplers = null;
            ITexture[] textures = null;

            try
            {
                samplers = isImage ? null : RentBindingScratch(_samplerBindingScratch, bindingInfo.ArrayLength);
                textures = RentBindingScratch(_textureBindingScratch, bindingInfo.ArrayLength);

                for (int index = 0; index < length; index++)
                {'''
FULL_DISPATCH_NEW = '''            if (!isNewEntry && entry.DeltaReady && !entry.ForceRebuild &&
                entry.DeltaFormatInfo.Format == bindingInfo.FormatInfo.Format &&
                UpdateFromPoolDelta(entry, texturePool, samplerPool, stage, isImage, isSampler, isStore, resScaleUnsupported, bindingInfo))
            {
                return;
            }

            if (!isNewEntry)
            {
                entry.Reset();
            }

            int length = (isSampler ? samplerPool.MaximumId : texturePool.MaximumId) + 1;
            length = Math.Min(length, bindingInfo.ArrayLength);

            PD.Count(PD.Counter.ArrayFullElements, length);

            bool deltaCapable = bindingInfo.Target != Target.TextureBuffer;

            if (deltaCapable)
            {
                entry.PrepareDelta(length, isSampler, bindingInfo.FormatInfo, texturePool?.AliasGeneration ?? 0, resScaleUnsupported);
            }
            else
            {
                // Buffer-texture arrays rebind their storage on every update: no per-element state for them.
                entry.DeltaReady = false;
                entry.ForceRebuild = true;
            }

            ISampler[] samplers = null;
            ITexture[] textures = null;

            try
            {
                samplers = isImage ? null : RentBindingScratch(_samplerBindingScratch, bindingInfo.ArrayLength);
                textures = RentBindingScratch(_textureBindingScratch, bindingInfo.ArrayLength);

                for (int index = 0; index < length; index++)
                {'''

FULL_RECORD = '''                    ITexture hostTexture = texture?.GetTargetTexture(bindingInfo.Target);
                    ISampler hostSampler = sampler?.GetHostSampler(texture);

                    if (hostTexture != null && texture.Target == Target.TextureBuffer)
                    {
                        // Ensure that the buffer texture is using the correct buffer as storage.'''
FULL_RECORD_NEW = '''                    ITexture hostTexture = texture?.GetTargetTexture(bindingInfo.Target);
                    ISampler hostSampler = sampler?.GetHostSampler(texture);

                    if (deltaCapable)
                    {
                        entry.RecordDelta(
                            index,
                            isSampler ? null : texturePool.PeekForBindingDelta(index, out _),
                            texture,
                            hostTexture,
                            isSampler ? samplerPool?.GetCachedItem(index) : null,
                            hostSampler,
                            replacing: false);
                    }

                    if (hostTexture != null && texture.Target == Target.TextureBuffer)
                    {
                        deltaCapable = false;

                        // Ensure that the buffer texture is using the correct buffer as storage.'''

FULL_END = '''                if (isImage)
                {
                    entry.ImageArray.SetImages(0, textures);

                    SetImageArray(stage, bindingInfo, entry.ImageArray);
                }
                else
                {
                    entry.TextureArray.SetSamplers(0, samplers);
                    entry.TextureArray.SetTextures(0, textures);

                    SetTextureArray(stage, bindingInfo, entry.TextureArray);
                }
            }
            finally
            {
                // Direct backends have consumed these; threaded backends own a private copy.
                ReturnBindingScratch(_textureBindingScratch, textures, ref _nextTextureBindingScratch);
                ReturnBindingScratch(_samplerBindingScratch, samplers, ref _nextSamplerBindingScratch);
            }
        }

        /// <summary>
        /// Updates a texture or image array bindings and textures from constant buffer handles.'''
FULL_END_NEW = '''                if (isImage)
                {
                    entry.ImageArray.SetImages(0, textures);

                    SetImageArray(stage, bindingInfo, entry.ImageArray);
                }
                else
                {
                    entry.TextureArray.SetSamplers(0, samplers);
                    entry.TextureArray.SetTextures(0, textures);

                    SetTextureArray(stage, bindingInfo, entry.TextureArray);
                }

                // Only a complete rebuild makes the recorded state valid for delta updates.
                entry.DeltaReady = deltaCapable;
                entry.ForceRebuild = false;
            }
            finally
            {
                // Direct backends have consumed these; threaded backends own a private copy.
                ReturnBindingScratch(_textureBindingScratch, textures, ref _nextTextureBindingScratch);
                ReturnBindingScratch(_samplerBindingScratch, samplers, ref _nextSamplerBindingScratch);
            }
        }

        // One contiguous run of elements to send, at most DeltaRunCapacity long (GPU thread only).
        // Changes separated by at most DeltaGapLimit unchanged elements share one run: the unchanged
        // elements between them are re-sent with their recorded bound values.
        private const int DeltaRunCapacity = 4096;
        private const int DeltaGapLimit = 16;
        private readonly ITexture[] _deltaRunTextures = new ITexture[DeltaRunCapacity];
        private readonly ISampler[] _deltaRunSamplers = new ISampler[DeltaRunCapacity];

        // Exact-length run arrays come from their own bounded cache, so runs never evict the full rebuild's lengths.
        private readonly ITexture[][] _deltaTextureScratch = new ITexture[BindingScratchSlots][];
        private readonly ISampler[][] _deltaSamplerScratch = new ISampler[BindingScratchSlots][];
        private int _nextDeltaTextureScratch;
        private int _nextDeltaSamplerScratch;

        /// <summary>
        /// Updates the elements of a pool array whose pool objects changed since its last update.
        /// </summary>
        /// <returns>False if the array must be fully rebuilt instead</returns>
        private bool UpdateFromPoolDelta(
            CacheEntry entry,
            TexturePool texturePool,
            SamplerPool samplerPool,
            ShaderStage stage,
            bool isImage,
            bool isSampler,
            bool isStore,
            bool resScaleUnsupported,
            in TextureBindingInfo bindingInfo)
        {
            if (resScaleUnsupported && !entry.DeltaAllBlacklisted)
            {
                // The end of the pass would blacklist bound textures and replace their hosts after they were sent.
                return false;
            }

            using var arrayWork = PD.Track(PD.Work.ArrayDelta);

            int length = entry.DeltaLength;
            int aliasGeneration = texturePool?.AliasGeneration ?? 0;
            int invalidationEpoch = Volatile.Read(ref Texture.InvalidationEpoch);
            bool aliasesMoved = aliasGeneration != entry.DeltaAliasGeneration;
            int changed = 0;
            int runStart = 0;
            int runCount = 0;
            int gap = 0;
            bool completed = false;

            try
            {
                for (int index = 0; index < length; index++)
                {
                    if (entry.DeltaUnchanged(index, texturePool, samplerPool, isSampler, aliasesMoved))
                    {
                        if (runCount != 0 && ++gap > DeltaGapLimit)
                        {
                            // Too far from the next change: send the run without its unchanged tail.
                            FlushDeltaRun(entry, isImage, isSampler, runStart, ref runCount);
                            gap = 0;
                        }

                        continue;
                    }

                    Texture texture = null;
                    Sampler sampler = null;

                    if (isSampler)
                    {
                        sampler = samplerPool?.Get(index);
                    }
                    else
                    {
                        texturePool.GetForBinding(index, bindingInfo.FormatInfo, out texture);

                        // As in the full rebuild: signal and blacklist before the host texture is read.
                        if (texture != null)
                        {
                            if (isStore)
                            {
                                texture.SignalModified();
                            }

                            if (resScaleUnsupported && texture.ScaleMode != TextureScaleMode.Blacklisted)
                            {
                                texture.BlacklistScale();
                            }
                        }
                    }

                    ITexture hostTexture = texture?.GetTargetTexture(bindingInfo.Target);
                    ISampler hostSampler = sampler?.GetHostSampler(texture);

                    if (hostTexture != null && texture.Target == Target.TextureBuffer)
                    {
                        // Buffer textures rebind their storage on every update: rebuild the whole array.
                        return false;
                    }

                    entry.RecordDelta(
                        index,
                        isSampler ? null : texturePool.PeekForBindingDelta(index, out _),
                        texture,
                        hostTexture,
                        isSampler ? samplerPool?.GetCachedItem(index) : null,
                        hostSampler,
                        replacing: true);

                    if (runCount != 0 && gap != 0)
                    {
                        if (runCount + gap >= DeltaRunCapacity)
                        {
                            FlushDeltaRun(entry, isImage, isSampler, runStart, ref runCount);
                        }
                        else
                        {
                            for (int skipped = index - gap; skipped < index; skipped++)
                            {
                                _deltaRunTextures[runCount] = isSampler ? null : entry.DeltaHosts[skipped];
                                _deltaRunSamplers[runCount] = isSampler ? entry.DeltaHostSamplers[skipped] : null;
                                runCount++;
                            }
                        }

                        gap = 0;
                    }

                    if (runCount == DeltaRunCapacity)
                    {
                        FlushDeltaRun(entry, isImage, isSampler, runStart, ref runCount);
                    }

                    if (runCount == 0)
                    {
                        runStart = index;
                    }

                    _deltaRunTextures[runCount] = hostTexture;
                    _deltaRunSamplers[runCount] = hostSampler;
                    runCount++;
                    changed++;
                }

                FlushDeltaRun(entry, isImage, isSampler, runStart, ref runCount);

                if ((texturePool?.AliasGeneration ?? 0) != aliasGeneration)
                {
                    // A lookup of this pass destroyed an alias list: views bound before it may be stale.
                    return false;
                }

                if (Volatile.Read(ref Texture.InvalidationEpoch) != invalidationEpoch)
                {
                    // A texture was invalidated during the pass (possibly by one of its own lookups, which can remove
                    // or replace a texture bound at another element): every element must still resolve to what is
                    // bound. Without an invalidation, pool items change only for the ids this pass resolved itself
                    // (RemoveFromPools and UpdatePoolMappings, the only other writers, both move the epoch).
                    for (int index = 0; index < length; index++)
                    {
                        if (!entry.DeltaUnchanged(index, texturePool, samplerPool, isSampler, aliasesMoved: false))
                        {
                            return false;
                        }
                    }
                }

                // The same memory synchronisation, store signal and scale blacklist as the cache-hit path. Unchanged
                // elements were sent with their recorded hosts: if a synchronisation replaced a bound texture's
                // storage, the full rebuild binds the new host instead.
                if (!entry.SynchronizeMemoryAndValidate(isStore, resScaleUnsupported))
                {
                    return false;
                }

                if (isImage)
                {
                    SetImageArray(stage, bindingInfo, entry.ImageArray);
                }
                else
                {
                    SetTextureArray(stage, bindingInfo, entry.TextureArray);
                }

                entry.DeltaAliasGeneration = aliasGeneration;

                if (!resScaleUnsupported && changed != 0)
                {
                    entry.DeltaAllBlacklisted = false;
                }

                PD.Count(PD.Counter.ArrayDeltaElements, length);
                PD.Count(PD.Counter.ArrayDeltaChanged, changed);

                completed = true;
                return true;
            }
            finally
            {
                if (!completed)
                {
                    // The backend array and the state are left to the full rebuild, now or on the next update.
                    entry.DeltaReady = false;
                    entry.ForceRebuild = true;
                    Array.Clear(_deltaRunTextures, 0, runCount);
                    Array.Clear(_deltaRunSamplers, 0, runCount);
                }
            }
        }

        /// <summary>
        /// Sends the pending run with an exact-length array, then clears the run.
        /// Texture arrays hold no samplers and sampler arrays no textures, as in the full rebuild.
        /// </summary>
        private void FlushDeltaRun(CacheEntry entry, bool isImage, bool isSampler, int runStart, ref int runCount)
        {
            int count = runCount;

            if (count == 0)
            {
                return;
            }

            runCount = 0;

            if (isSampler)
            {
                ISampler[] samplers = RentBindingScratch(_deltaSamplerScratch, count);

                try
                {
                    Array.Copy(_deltaRunSamplers, samplers, count);
                    entry.TextureArray.SetSamplers(runStart, samplers);
                }
                finally
                {
                    ReturnBindingScratch(_deltaSamplerScratch, samplers, ref _nextDeltaSamplerScratch);
                    Array.Clear(_deltaRunSamplers, 0, count);
                    Array.Clear(_deltaRunTextures, 0, count);
                }

                return;
            }

            ITexture[] textures = RentBindingScratch(_deltaTextureScratch, count);

            try
            {
                Array.Copy(_deltaRunTextures, textures, count);

                if (isImage)
                {
                    entry.ImageArray.SetImages(runStart, textures);
                }
                else
                {
                    entry.TextureArray.SetTextures(runStart, textures);
                }
            }
            finally
            {
                ReturnBindingScratch(_deltaTextureScratch, textures, ref _nextDeltaTextureScratch);
                Array.Clear(_deltaRunTextures, 0, count);
                Array.Clear(_deltaRunSamplers, 0, count);
            }
        }

        /// <summary>
        /// Updates a texture or image array bindings and textures from constant buffer handles.'''

BUFFER_REBUILD = '''            if (!isNewEntry)
            {
                entry.Reset();
            }

            entry.UpdateData(cachedTextureBuffer, cachedSamplerBuffer, separateSamplerBuffer);'''
BUFFER_REBUILD_NEW = '''            if (!isNewEntry)
            {
                entry.Reset();
            }

            PD.Count(PD.Counter.ArrayBufferElements, bindingInfo.ArrayLength);

            entry.UpdateData(cachedTextureBuffer, cachedSamplerBuffer, separateSamplerBuffer);'''

PEEK_ANCHOR = '''        /// <summary>
        /// Checks if the pool was modified, and returns the last sequence number where a modification was detected.'''
PEEK = '''        /// <summary>
        /// The pool item of <paramref name="id"/> as last synchronised, without loading it, and whether the id is
        /// known to hold no texture until its descriptor is written again. Bindless delta updates only.
        /// </summary>
        internal Texture PeekForBindingDelta(int id, out bool knownInvalid)
        {
            Texture texture = Items[id];
            knownInvalid = texture == null && _invalidMap.IsSet(id);

            return texture;
        }

        /// <summary>
        /// Moves whenever an alias list is destroyed, so that delta updates re-resolve format aliases.
        /// </summary>
        internal int AliasGeneration => _aliasGeneration;
        private int _aliasGeneration;

''' + PEEK_ANCHOR

EPOCH_FIELD = '''        /// <summary>
        /// Increments when the host texture is swapped, or when the texture is removed from all pools.
        /// </summary>
        public int InvalidatedSequence { get; private set; }'''
EPOCH_FIELD_NEW = EPOCH_FIELD + '''

        /// <summary>
        /// Moves, from any thread, whenever the InvalidatedSequence of any texture moves: a bindless delta pass that
        /// sees it unchanged knows that none of its lookups removed or replaced a texture bound elsewhere.
        /// </summary>
        internal static int InvalidationEpoch;'''
EPOCH_BUMP = '''            InvalidatedSequence++;
'''
EPOCH_BUMP_NEW = '''            InvalidatedSequence++;
            System.Threading.Interlocked.Increment(ref InvalidationEpoch);
'''

ALIAS_REMOVE = '''            if (_aliasLists.TryGetValue(texture, out TextureAliasList aliasList))
            {
                _aliasLists.Remove(texture);
                aliasList.Destroy();
            }'''
ALIAS_REMOVE_NEW = '''            if (_aliasLists.TryGetValue(texture, out TextureAliasList aliasList))
            {
                _aliasLists.Remove(texture);
                aliasList.Destroy();
                _aliasGeneration++;
            }'''

# Rows and counters appended to the prepared collector (its other names and order are unchanged).
# The collector drops a window payload above 4000 characters (the journal cuts strings at 4096); the
# delivered payload is 3770 characters at maximum width. One row (68) and four short counters (143) fit.
DIAGNOSTIC_EDITS = (
    ("""        VirtualDependencySingle, VirtualDependencyMultiple, ReadCopies, ReadCopyBytes, PooledReads, PooledReadBytes, Count }""",
     """        VirtualDependencySingle, VirtualDependencyMultiple, ReadCopies, ReadCopyBytes, PooledReads, PooledReadBytes,
        ArrayFullElements, ArrayDeltaElements, ArrayDeltaChanged, ArrayBufferElements, Count }"""),
    ("""        BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, Count }""",
     """        BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, ArrayDelta, Count }"""),
    ("""        "texFlushAction", "bufLoad", "bufFlush", "poolSync", "shader", "bindings" };""",
     """        "texFlushAction", "bufLoad", "bufFlush", "poolSync", "shader", "bindings", "arrayDelta" };"""),
    ("""        "virtualDependencySingle", "virtualDependencyMultiple", "readCopies", "readCopyBytes", "pooledReads", "pooledReadBytes" };""",
     """        "virtualDependencySingle", "virtualDependencyMultiple", "readCopies", "readCopyBytes", "pooledReads", "pooledReadBytes",
        "arrFullElems", "arrDeltaElems", "arrDeltaChanged", "arrBufElems" };"""),
)
WORK_ROWS = ('arrayDelta',)
COUNTERS = ('arrFullElems', 'arrDeltaElems', 'arrDeltaChanged', 'arrBufElems')
MAX_PAYLOAD_GROWTH = 68 + 35 + 36 + 38 + 34


def add_alias(path):
    text = path.read_text(encoding='utf-8-sig')
    if ALIAS not in text:
        path.write_text(ALIAS + text, encoding='utf-8')


def apply_array_cache(source):
    """Only the TextureBindingsArrayCache part (the host fixture compiles that file with doubles)."""
    source = Path(source)
    cache = source / ARRAY_CACHE
    once(cache, '''            private int _texturePoolSequence;
            private int _samplerPoolSequence;''', ENTRY_STATE)
    once(cache, RESET, RESET_NEW)
    once(cache, HIT, HIT_NEW)
    once(cache, FULL_DISPATCH, FULL_DISPATCH_NEW)
    once(cache, FULL_RECORD, FULL_RECORD_NEW)
    once(cache, FULL_END, FULL_END_NEW)
    once(cache, BUFFER_REBUILD, BUFFER_REBUILD_NEW)
    add_alias(cache)
    text = cache.read_text(encoding='utf-8')
    if 'using System.Threading;' not in text:
        once(cache, 'using System;\n', 'using System;\nusing System.Threading;\n')
    return [ARRAY_CACHE]


def apply(source):
    source = Path(source)
    apply_array_cache(source)
    once(source / TEXTURE_POOL, PEEK_ANCHOR, PEEK)
    once(source / TEXTURE_POOL, ALIAS_REMOVE, ALIAS_REMOVE_NEW)
    texture = source / TEXTURE
    once(texture, EPOCH_FIELD, EPOCH_FIELD_NEW)
    text = texture.read_text(encoding='utf-8-sig')
    assert text.count(EPOCH_BUMP) == 3, ('InvalidatedSequence increments', text.count(EPOCH_BUMP))
    texture.write_text(text.replace(EPOCH_BUMP, EPOCH_BUMP_NEW), encoding='utf-8')
    for old, new in DIAGNOSTIC_EDITS:
        once(source / DIAGNOSTICS, old, new)
    return NAMES
