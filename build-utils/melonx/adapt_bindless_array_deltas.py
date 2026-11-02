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
- Changed elements are resolved exactly as the full rebuild does and sent with
  SetTextures / SetSamplers / SetImages(start, run) for each contiguous run, an
  offset form every backend implements; unchanged elements are not re-sent.
- The entry's texture set stays exact (reference counts per bound texture), so
  SynchronizeMemory, SignalModified (image stores) and the scale blacklist reach
  exactly the bound textures, as on the cache-hit path.
- New entries, TextureBuffer arrays (their storage is rebound on every update) and
  any failure keep the full rebuild, which also records the per-element state.
Pool synchronisation, the order of renderer commands and resource lifetimes are
unchanged; memory is still synchronised for every bound texture on every update.

Bounded counters and scopes attribute the remaining cost on the device: compute
commits apart from graphics ones, full rebuilds, delta passes (elements scanned and
changed), buffer-handle array rebuilds and pool creations. Updating counters
allocates nothing. Not measured on the iPhone yet; no FPS claim.
"""
from pathlib import Path

from adapt_session import once

ARRAY_CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
TEXTURE_POOL = 'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs'
POOL_CACHE = 'src/Ryujinx.Graphics.Gpu/Image/PoolCache.cs'
TEXTURE_MANAGER = 'src/Ryujinx.Graphics.Gpu/Image/TextureManager.cs'
DIAGNOSTICS = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
NAMES = [ARRAY_CACHE, TEXTURE_POOL, POOL_CACHE, TEXTURE_MANAGER, DIAGNOSTICS]
ALIAS = 'using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n'

ENTRY_STATE = '''            private int _texturePoolSequence;
            private int _samplerPoolSequence;

            /// <summary>
            /// Per-element state of the last update of a pool array, for delta updates.
            /// Texture arrays use the item, resolved texture and sequence arrays; sampler arrays the sampler array.
            /// </summary>
            public Texture[] DeltaItems;
            public Texture[] DeltaTextures;
            public int[] DeltaSequences;
            public Sampler[] DeltaSamplers;
            public int DeltaLength;
            public bool DeltaReady;

            /// <summary>
            /// How many elements resolve to each bound texture, so that a delta update keeps the
            /// texture set exact (every bound texture, with its current sequence, and nothing else).
            /// </summary>
            private Dictionary<Texture, int> _deltaReferences;

            /// <summary>
            /// Allocates the per-element state once for an array of <paramref name="length"/> elements.
            /// </summary>
            public void PrepareDelta(int length, bool isSampler)
            {
                DeltaReady = false;
                DeltaLength = length;

                if (isSampler)
                {
                    if (DeltaSamplers?.Length != length)
                    {
                        DeltaSamplers = new Sampler[length];
                    }
                }
                else
                {
                    if (DeltaItems?.Length != length)
                    {
                        DeltaItems = new Texture[length];
                        DeltaTextures = new Texture[length];
                        DeltaSequences = new int[length];
                    }

                    (_deltaReferences ??= new Dictionary<Texture, int>()).Clear();
                }
            }

            /// <summary>
            /// Records the pool objects an element was resolved from. A full rebuild (<paramref name="replacing"/>
            /// false) fills the texture set itself; a delta update replaces the element's previous texture here.
            /// </summary>
            public void RecordDelta(int index, Texture item, Texture texture, Sampler sampler, bool replacing)
            {
                if (DeltaSamplers != null && DeltaItems == null)
                {
                    DeltaSamplers[index] = sampler;
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
                DeltaSequences[index] = texture?.InvalidatedSequence ?? 0;

                if (texture != null)
                {
                    _deltaReferences[texture] = (_deltaReferences.TryGetValue(texture, out int count) ? count : 0) + 1;

                    if (replacing)
                    {
                        Textures[texture] = texture.InvalidatedSequence;
                    }
                }
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
FULL_DISPATCH_NEW = '''            if (!isNewEntry && entry.DeltaReady &&
                UpdateFromPoolDelta(entry, texturePool, samplerPool, stage, isImage, isSampler, isStore, resScaleUnsupported, bindingInfo))
            {
                return;
            }

            if (!isNewEntry)
            {
                entry.Reset();
            }

            using var arrayWork = PD.Track(PD.Work.ArrayFull);

            int length = (isSampler ? samplerPool.MaximumId : texturePool.MaximumId) + 1;
            length = Math.Min(length, bindingInfo.ArrayLength);

            PD.Count(PD.Counter.ArrayFullRebuilds);
            PD.Count(PD.Counter.ArrayFullElements, length);

            entry.PrepareDelta(length, isSampler);
            bool deltaCapable = bindingInfo.Target != Target.TextureBuffer;

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

                    entry.RecordDelta(
                        index,
                        isSampler ? null : texturePool.PeekForBindingDelta(index, out _),
                        texture,
                        isSampler ? samplerPool?.GetCachedItem(index) : null,
                        replacing: false);

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
        // elements between them are re-sent with their recorded values, identical to what is bound.
        private const int DeltaRunCapacity = 4096;
        private const int DeltaGapLimit = 16;
        private readonly ITexture[] _deltaRunTextures = new ITexture[DeltaRunCapacity];
        private readonly ISampler[] _deltaRunSamplers = new ISampler[DeltaRunCapacity];

        /// <summary>
        /// Updates the elements of a pool array whose pool objects changed since its last update.
        /// </summary>
        /// <returns>False if the array must be rebuilt instead (nothing was left half-recorded)</returns>
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
            using var arrayWork = PD.Track(PD.Work.ArrayDelta);

            int length = entry.DeltaLength;
            int changed = 0;
            int runStart = 0;
            int runCount = 0;
            int gap = 0;
            bool completed = false;

            try
            {
                for (int index = 0; index < length; index++)
                {
                    bool unchanged;

                    if (isSampler)
                    {
                        Sampler item = samplerPool?.GetCachedItem(index);
                        unchanged = item != null && item == entry.DeltaSamplers[index] && !item.IsDisposed;
                    }
                    else
                    {
                        Texture item = texturePool.PeekForBindingDelta(index, out bool knownInvalid);
                        Texture previous = entry.DeltaTextures[index];

                        unchanged = item == entry.DeltaItems[index] && (item != null
                            ? previous != null && previous.InvalidatedSequence == entry.DeltaSequences[index]
                            : knownInvalid && previous == null);
                    }

                    if (unchanged)
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
                        isSampler ? samplerPool?.GetCachedItem(index) : null,
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
                                _deltaRunTextures[runCount] = isSampler ? null : entry.DeltaTextures[skipped]?.GetTargetTexture(bindingInfo.Target);
                                _deltaRunSamplers[runCount] = isSampler ? entry.DeltaSamplers[skipped]?.GetHostSampler(null) : null;
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

                // The same memory synchronisation, store signal and scale blacklist as the cache-hit path.
                entry.SynchronizeMemory(isStore, resScaleUnsupported);

                if (isImage)
                {
                    SetImageArray(stage, bindingInfo, entry.ImageArray);
                }
                else
                {
                    SetTextureArray(stage, bindingInfo, entry.TextureArray);
                }

                PD.Count(PD.Counter.ArrayDeltaPasses);
                PD.Count(PD.Counter.ArrayDeltaElements, length);
                PD.Count(PD.Counter.ArrayDeltaChanged, changed);

                completed = true;
                return true;
            }
            finally
            {
                if (!completed)
                {
                    // A partial pass leaves the backend array and the state to the full rebuild.
                    entry.DeltaReady = false;
                    Array.Clear(_deltaRunTextures, 0, runCount);
                    Array.Clear(_deltaRunSamplers, 0, runCount);
                }
            }
        }

        /// <summary>
        /// Sends the pending run of changed elements with an exact-length array, then clears the run.
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
                ISampler[] samplers = RentBindingScratch(_samplerBindingScratch, count);

                try
                {
                    Array.Copy(_deltaRunSamplers, samplers, count);
                    entry.TextureArray.SetSamplers(runStart, samplers);
                }
                finally
                {
                    ReturnBindingScratch(_samplerBindingScratch, samplers, ref _nextSamplerBindingScratch);
                    Array.Clear(_deltaRunSamplers, 0, count);
                    Array.Clear(_deltaRunTextures, 0, count);
                }

                return;
            }

            ITexture[] textures = RentBindingScratch(_textureBindingScratch, count);

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
                ReturnBindingScratch(_textureBindingScratch, textures, ref _nextTextureBindingScratch);
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

            using var arrayWork = PD.Track(PD.Work.ArrayBuffer);
            PD.Count(PD.Counter.ArrayBufferRebuilds);
            PD.Count(PD.Counter.ArrayBufferElements, bindingInfo.ArrayLength);

            entry.UpdateData(cachedTextureBuffer, cachedSamplerBuffer, separateSamplerBuffer);'''

PEEK_ANCHOR = '''        public int CheckModified()
        {'''
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

''' + PEEK_ANCHOR

CREATE = '''            // If not found, create a new one.
            pool = CreatePool(_context, channel, address, maximumId);'''
CREATE_NEW = '''            // If not found, create a new one.
            PD.Count(PD.Counter.PoolCreates);
            pool = CreatePool(_context, channel, address, maximumId);'''

COMPUTE = '''        public bool CommitComputeBindings(ShaderSpecializationState specState)
        {
            using var gpuWork = PD.Track(PD.Work.Bindings);'''
COMPUTE_NEW = COMPUTE + '''
            using var computeWork = PD.Track(PD.Work.ComputeBindings);'''


# Rows and counters appended to the prepared collector (its other names and order are unchanged).
DIAGNOSTIC_EDITS = (
    ("""        VirtualDependencySingle, VirtualDependencyMultiple, ReadCopies, ReadCopyBytes, PooledReads, PooledReadBytes, Count }""",
     """        VirtualDependencySingle, VirtualDependencyMultiple, ReadCopies, ReadCopyBytes, PooledReads, PooledReadBytes,
        ArrayFullRebuilds, ArrayFullElements, ArrayDeltaPasses, ArrayDeltaElements, ArrayDeltaChanged,
        ArrayBufferRebuilds, ArrayBufferElements, PoolCreates, Count }"""),
    ("""        BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, Count }""",
     """        BufferLoad, BufferFlush, PoolSync, ShaderLookup, Bindings, ComputeBindings, ArrayFull, ArrayDelta,
        ArrayBuffer, Count }"""),
    ("""        "texFlushAction", "bufLoad", "bufFlush", "poolSync", "shader", "bindings" };""",
     """        "texFlushAction", "bufLoad", "bufFlush", "poolSync", "shader", "bindings", "computeBindings", "arrayFull",
        "arrayDelta", "arrayBuffer" };"""),
    ("""        "virtualDependencySingle", "virtualDependencyMultiple", "readCopies", "readCopyBytes", "pooledReads", "pooledReadBytes" };""",
     """        "virtualDependencySingle", "virtualDependencyMultiple", "readCopies", "readCopyBytes", "pooledReads", "pooledReadBytes",
        "arrayFullRebuilds", "arrayFullElements", "arrayDeltaPasses", "arrayDeltaElements", "arrayDeltaChanged",
        "arrayBufferRebuilds", "arrayBufferElements", "poolCreates" };"""),
)
WORK_ROWS = ('computeBindings', 'arrayFull', 'arrayDelta', 'arrayBuffer')
COUNTERS = ('arrayFullRebuilds', 'arrayFullElements', 'arrayDeltaPasses', 'arrayDeltaElements', 'arrayDeltaChanged',
            'arrayBufferRebuilds', 'arrayBufferElements', 'poolCreates')


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
    once(cache, FULL_DISPATCH, FULL_DISPATCH_NEW)
    once(cache, FULL_RECORD, FULL_RECORD_NEW)
    once(cache, FULL_END, FULL_END_NEW)
    once(cache, BUFFER_REBUILD, BUFFER_REBUILD_NEW)
    add_alias(cache)
    return [ARRAY_CACHE]


def apply(source):
    source = Path(source)
    apply_array_cache(source)
    once(source / TEXTURE_POOL, PEEK_ANCHOR, PEEK)
    once(source / POOL_CACHE, CREATE, CREATE_NEW)
    add_alias(source / POOL_CACHE)
    once(source / TEXTURE_MANAGER, COMPUTE, COMPUTE_NEW)
    for old, new in DIAGNOSTIC_EDITS:
        once(source / DIAGNOSTICS, old, new)
    return NAMES
