"""Hold less managed memory per bindless pool array, and journal what the pool arrays hold.

Finding (MeloNX Core 658 logs, Hogwarts Legacy, players 1 and 2, private, not in the repository): the gcEvent journal
shows 250-282 MiB of live large-object heap (LOH) in play, 250 MiB already at the first collection of every session
(before any texture array exists, and in Super Smash Bros. Ultimate, which builds no pool array), 171 MiB retained by
a 12 s session that barely rendered, and 271-282 MiB retained after a Hogwarts close (the session stays reachable).
The 479-603 MiB readings of player 2 are first-scene background collections with 36-53 MiB of free space: objects
allocated during the collection count as live there, and the next collection finds 250-433 MiB. In every Hogwarts
session the core-performance windows show one burst that creates the pool arrays: 3 full rebuilds of 524288 elements
plus one of 4096 (arrFullElems 1576960 = 3 x 524288 + 4096) with 80-92 MiB allocated on the render thread (three
Vulkan TextureArray of 524288 elements, 24 MiB each); no later window allocates another. So a session holds three
pool-sized texture-array entries and one 4096-element sampler entry, all updated every frame (range writes of about
524070 kept elements, about 95 a second): nothing to age out.

Accounting per 524288-element pool texture entry (read in the Core 658 preparation, measured by
test/melonx_bindless_retention_test.py with the real classes):
- GPU, TextureBindingsArrayCache.CacheEntry (adapt_bindless_array_deltas): DeltaItems, DeltaTextures, DeltaHosts (8
  bytes each) and DeltaSequences (4): 14 MiB, plus two dictionaries per distinct texture.
- GAL, ThreadedTextureArray: no per-element storage; each whole rebuild copies the textures and the samplers into
  ThreadedArrayPool snapshots (4 MiB each), of which the pool keeps up to 1048576 elements per type
  (adapt_array_rebuild_allocations). The cache keeps the same budget of rebuild scratch per type.
- Vulkan, TextureArray: TextureRef[] (storage, image view, sampler: 24 bytes) and DescriptorImageInfo[] (24): 24 MiB.
Duplicates: a TextureRef's storage and image view are both read-only members of the one TextureView they come from;
a pool texture array never receives a sampler, so its sampler slots, the 4 MiB sampler scratch and the 4 MiB sampler
snapshot of each whole rebuild hold only nulls (a pool sampler array the same for textures).

Change:
- TextureBindingsArrayCache.UpdateFromPool: a pool texture array no longer rents, fills and sends its all-null
  sampler array, and a pool sampler array no longer its all-null texture array (the delta runs already send only the
  array's own kind). The backend element contents are unchanged: those slots hold null from the array's creation on.
- Vulkan TextureArray: one TextureView reference per element replaces the storage and image-view references (read
  from that view, both read-only there), and the samplers live in an array allocated at the first non-null sampler:
  8 bytes per element instead of 24 for a texture array. The descriptor values, the reference counts, the change log,
  the barriers' storage set and the exceptions of the delivered code (buffer arrays, out-of-range indices) are those
  of the delivered code (asserted on the real class).
- Journal: the "Vulkan pass and GPU detail" line (every 5 s) ends its texture-array part with the pool-array entries
  held by the GPU caches, those not updated for 30 s or more, their per-element delta bytes, and the backend texture
  arrays longer than 4096 elements with their element bytes (GAL TextureArrayInventory, written by both layers).
Not changed: no entry is evicted (the measured ones are all in use), MaxSlots and the descriptor sets (native memory,
not in the managed heap), the delta state, DescriptorImageInfo[], buffer arrays and ImageArray.
Expected effect for Hogwarts (three 524288-element texture entries): 3 x 8 MiB of Vulkan element arrays and up to
16 MiB of kept sampler scratch and snapshots, about 40 MiB of live LOH, and 8 MiB less LOH allocation plus one
524288-element sampler pass on each thread per whole rebuild of a pool texture array. Not measured on an iPhone.
Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
INVENTORY = 'src/Ryujinx.Graphics.GAL/ITextureArray.cs'
ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
DETAIL = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
BASELINE = {
    CACHE: '7d119713c215827c4b092fbaa7689854bb49312482859de83db16d0d5de274c5',
    INVENTORY: '5dd236e731089d04967d4c6ba7551a7b69450154e4800d925dc022c01883f3db',
    ARRAY: '912c3ee1f5f5b9e7270a9bb64c7ce7e76732d228b5dff1cca49fe992b2baed63',
    DETAIL: '4cefef6adf901c47b16c534eed2c028ef5fe8382b94ea1a89ce4a722341e4bfa',
}

INVENTORY_CLASS = '''
    /// <summary>
    /// RewindBox (adapt_bindless_retention): the managed per-element storage of bindless arrays still held, for the
    /// backend's detail line. The GPU texture bindings array caches write the pool entries (count, those not updated for
    /// <see cref="IdleMilliseconds"/>, bytes of their per-element delta state); the backend writes its texture arrays
    /// longer than <see cref="LargeLength"/> elements not yet disposed and the bytes of their element arrays.
    /// </summary>
    public static class TextureArrayInventory
    {
        public const long IdleMilliseconds = 30000;
        public const int LargeLength = 4096;

        public static long PoolEntries;
        public static long PoolEntriesIdle;
        public static long PoolEntryBytes;
        public static long LargeBackendArrays;
        public static long LargeBackendBytes;
    }
'''

# GPU cache: the bytes of an entry's delta state, kept up to date where it is allocated and released.
ENTRY_FIELDS_OLD = '''            public TexturePool DeltaLogPool;
            public long DeltaLogPosition;
'''
ENTRY_FIELDS_NEW = '''            public TexturePool DeltaLogPool;
            public long DeltaLogPosition;

            /// <summary>
            /// RewindBox (adapt_bindless_retention): when a pool entry was last updated (Environment.TickCount64).
            /// </summary>
            public long LastUse;

            /// <summary>
            /// RewindBox (adapt_bindless_retention): bytes of the per-element delta arrays the entry holds.
            /// </summary>
            public long DeltaBytes()
            {
                return ((long)(DeltaItems?.Length ?? 0) + (DeltaTextures?.Length ?? 0) + (DeltaHosts?.Length ?? 0) +
                        (DeltaSamplers?.Length ?? 0) + (DeltaHostSamplers?.Length ?? 0)) * IntPtr.Size +
                       (long)(DeltaSequences?.Length ?? 0) * sizeof(int);
            }
'''
PREPARE_OLD = '''            public void PrepareDelta(int length, bool isSampler, FormatInfo formatInfo, int aliasGeneration, bool resScaleUnsupported)
            {
                DeltaReady = false;
'''
PREPARE_NEW = '''            public void PrepareDelta(int length, bool isSampler, FormatInfo formatInfo, int aliasGeneration, bool resScaleUnsupported)
            {
                // RewindBox (adapt_bindless_retention): the arrays allocated below are counted in the inventory.
                long heldBytes = DeltaBytes();
                DeltaReady = false;
'''
PREPARE_END_OLD = '''                    (_deltaReferences ??= new Dictionary<Texture, int>()).Clear();
                }
            }
'''
PREPARE_END_NEW = '''                    (_deltaReferences ??= new Dictionary<Texture, int>()).Clear();
                }

                Interlocked.Add(ref TextureArrayInventory.PoolEntryBytes, DeltaBytes() - heldBytes);
            }
'''
UPDATE_OLD = '''            CacheEntry entry = GetOrAddEntry(texturePool, samplerPool, bindingInfo, isImage, out bool isNewEntry);

            bool isSampler = bindingInfo.IsSamplerOnly;
'''
UPDATE_NEW = '''            CacheEntry entry = GetOrAddEntry(texturePool, samplerPool, bindingInfo, isImage, out bool isNewEntry);

            // RewindBox (adapt_bindless_retention): the entry's use, and once a second the idle entries, for the inventory.
            long now = Environment.TickCount64;
            entry.LastUse = now;

            if (now - _inventoryPublished >= 1000)
            {
                PublishIdleEntries(now);
            }

            bool isSampler = bindingInfo.IsSamplerOnly;
'''
RENT_OLD = '''                // RewindBox (adapt_array_rebuild_allocations): pool-sized arrays come from the bounded large slots.
                samplers = isImage ? null : RentRebuildScratch(_samplerBindingScratch, _largeSamplerBindingScratch, bindingInfo.ArrayLength);
                textures = RentRebuildScratch(_textureBindingScratch, _largeTextureBindingScratch, bindingInfo.ArrayLength);

                for (int index = 0; index < length; index++)
'''
RENT_NEW = '''                // RewindBox (adapt_array_rebuild_allocations): pool-sized arrays come from the bounded large slots.
                // RewindBox (adapt_bindless_retention): a pool texture array only ever holds null samplers and a pool
                // sampler array null textures (its delta runs send its own kind only): that all-null array is neither
                // rented, filled nor sent.
                samplers = isImage || !isSampler ? null : RentRebuildScratch(_samplerBindingScratch, _largeSamplerBindingScratch, bindingInfo.ArrayLength);
                textures = isSampler ? null : RentRebuildScratch(_textureBindingScratch, _largeTextureBindingScratch, bindingInfo.ArrayLength);

                for (int index = 0; index < length; index++)
'''
FILL_OLD = '''                    else
                    {
                        samplers[index] = hostSampler;
                        textures[index] = hostTexture;
                    }
                }

                if (isImage)
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
'''
FILL_NEW = '''                    else if (isSampler)
                    {
                        // RewindBox (adapt_bindless_retention): hostTexture is null here.
                        samplers[index] = hostSampler;
                    }
                    else
                    {
                        // RewindBox (adapt_bindless_retention): hostSampler is null here.
                        textures[index] = hostTexture;
                    }
                }

                if (isImage)
                {
                    entry.ImageArray.SetImages(0, textures);

                    SetImageArray(stage, bindingInfo, entry.ImageArray);
                }
                else
                {
                    // RewindBox (adapt_bindless_retention): the array's own kind only; the other stays null.
                    if (isSampler)
                    {
                        entry.TextureArray.SetSamplers(0, samplers);
                    }
                    else
                    {
                        entry.TextureArray.SetTextures(0, textures);
                    }

                    SetTextureArray(stage, bindingInfo, entry.TextureArray);
                }

                // Only a complete rebuild makes the recorded state valid for delta updates.
'''
ADD_OLD = '''                    ITextureArray array = _context.Renderer.CreateTextureArray(arrayLength, bindingInfo.Target == Target.TextureBuffer);

                    _cacheFromPool.Add(key, entry = new CacheEntry(array, texturePool, samplerPool));
                }
            }

            return entry;
'''
ADD_NEW = '''                    ITextureArray array = _context.Renderer.CreateTextureArray(arrayLength, bindingInfo.Target == Target.TextureBuffer);

                    _cacheFromPool.Add(key, entry = new CacheEntry(array, texturePool, samplerPool));
                }

                // RewindBox (adapt_bindless_retention): one more pool entry held.
                Interlocked.Increment(ref TextureArrayInventory.PoolEntries);
            }

            return entry;
'''
REMOVE_OLD = '''                if (key.MatchesPool(pool))
                {
                    (keysToRemove ??= []).Add(key);
'''
REMOVE_NEW = '''                if (key.MatchesPool(pool))
                {
                    (keysToRemove ??= []).Add(key);

                    // RewindBox (adapt_bindless_retention): the entry and its delta state leave the inventory.
                    Interlocked.Decrement(ref TextureArrayInventory.PoolEntries);
                    Interlocked.Add(ref TextureArrayInventory.PoolEntryBytes, -entry.DeltaBytes());
'''
REMOVE_END_OLD = '''                foreach (CacheEntryFromPoolKey key in keysToRemove)
                {
                    _cacheFromPool.Remove(key);
                }
            }
        }
'''
REMOVE_END_NEW = '''                foreach (CacheEntryFromPoolKey key in keysToRemove)
                {
                    _cacheFromPool.Remove(key);
                }

                PublishIdleEntries(Environment.TickCount64);
            }
        }

        // RewindBox (adapt_bindless_retention): this cache's share of TextureArrayInventory.PoolEntriesIdle.
        private long _inventoryPublished;
        private long _idlePublished;

        private void PublishIdleEntries(long now)
        {
            long idle = 0;

            foreach (CacheEntry entry in _cacheFromPool.Values)
            {
                if (now - entry.LastUse >= TextureArrayInventory.IdleMilliseconds)
                {
                    idle++;
                }
            }

            Interlocked.Add(ref TextureArrayInventory.PoolEntriesIdle, idle - _idlePublished);
            _idlePublished = idle;
            _inventoryPublished = now;
        }
'''

# Vulkan TextureArray: one view reference per element, samplers apart.
REF_OLD = '''        private struct TextureRef
        {
            public TextureStorage Storage;
            public Auto<DisposableImageView> View;
            public Auto<DisposableSampler> Sampler;
        }

        private readonly TextureRef[] _textureRefs;
        private readonly TextureBuffer[] _bufferTextureRefs;
'''
REF_NEW = '''        // RewindBox (adapt_bindless_retention): an element held its view's storage, image view and sampler (24 bytes). The
        // storage and the image view are read-only members of the view (TextureView.Storage, GetImageView), and a texture
        // array of a pool never gets a sampler: one view reference per element, and the samplers in an array allocated at
        // the first non-null one (8 bytes per element instead of 24 for a texture array). Null for a buffer array, as the
        // delivered element array was.
        private readonly TextureView[] _views;
        private Auto<DisposableSampler>[] _samplers;
        private readonly TextureBuffer[] _bufferTextureRefs;
        private bool _inventoried;

        private Auto<DisposableImageView> ViewAt(int index) => _views[index]?.GetImageView();

        private Auto<DisposableSampler> SamplerAt(int index) => _samplers?[index];

        // The delivered TextureRef comparison of two elements: the same image view and sampler references.
        private bool SameElement(int left, int right)
        {
            return ReferenceEquals(ViewAt(left), ViewAt(right)) && ReferenceEquals(SamplerAt(left), SamplerAt(right));
        }

        private void Inventory(long arrays, long bytes)
        {
            if (_textures != null ? _textures.Length > TextureArrayInventory.LargeLength : _bufferTextures.Length > TextureArrayInventory.LargeLength)
            {
                System.Threading.Interlocked.Add(ref TextureArrayInventory.LargeBackendArrays, arrays);
                System.Threading.Interlocked.Add(ref TextureArrayInventory.LargeBackendBytes, bytes);
            }
        }

        /// <summary>
        /// RewindBox (adapt_bindless_retention): the inventory part of the detail line.
        /// </summary>
        public static string InventoryText()
        {
            const double MiB = 1024 * 1024;

            return FormattableString.Invariant($"; bindless pool arrays held: entries {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntries)} (not updated for 30 s or more {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntriesIdle)}), per-element delta state {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntryBytes) / MiB:F1} MiB; backend texture arrays over {TextureArrayInventory.LargeLength} elements {System.Threading.Interlocked.Read(ref TextureArrayInventory.LargeBackendArrays)}, element arrays {System.Threading.Interlocked.Read(ref TextureArrayInventory.LargeBackendBytes) / MiB:F1} MiB");
        }
'''
CTOR_OLD = '''            else
            {
                _textureRefs = new TextureRef[size];
                _textures = new DescriptorImageInfo[size];
            }
'''
CTOR_NEW = '''            else
            {
                _views = new TextureView[size];
                _textures = new DescriptorImageInfo[size];
            }

            // RewindBox (adapt_bindless_retention): the element arrays allocated above.
            Inventory(1, (long)size * (isBuffer ? 2 * IntPtr.Size : IntPtr.Size + Unsafe.SizeOf<DescriptorImageInfo>()));
'''
SAMPLERS_OLD = '''            for (int i = 0; i < samplers.Length; i++)
            {
                Auto<DisposableSampler> previous = counted ? _textureRefs[index + i].Sampler : null;

                try
                {
                    ISampler sampler = samplers[i];

                    if (sampler is SamplerHolder samplerHolder)
                    {
                        _textureRefs[index + i].Sampler = samplerHolder.GetSampler();
                    }
                    else
                    {
                        _textureRefs[index + i].Sampler = default;
                    }
                }
                catch
                 {
                    _textureRefs[index + i].Sampler = default;
                }

                if (counted)
                {
                    SwapReference(_samplerReferences, previous, _textureRefs[index + i].Sampler);
                }
            }
'''
# The delivered lines end "try " and "} " (a trailing space each).
SAMPLERS_OLD = SAMPLERS_OLD.replace('                try\n', '                try \n', 1).replace(
    '                }\n                catch\n', '                } \n                catch\n', 1)
SAMPLERS_NEW = '''            for (int i = 0; i < samplers.Length; i++)
            {
                // RewindBox (adapt_bindless_retention): the element access of the delivered code, for its exceptions (a
                // buffer array has no element array, an index beyond the array has no element).
                _ = _views[index + i];

                Auto<DisposableSampler> previous = counted ? SamplerAt(index + i) : null;
                Auto<DisposableSampler> current;

                try
                {
                    current = samplers[i] is SamplerHolder samplerHolder ? samplerHolder.GetSampler() : default;
                }
                catch
                {
                    current = default;
                }

                if (current != null && _samplers == null)
                {
                    _samplers = new Auto<DisposableSampler>[_views.Length];
                    Inventory(0, (long)_samplers.Length * IntPtr.Size);
                }

                if (_samplers != null)
                {
                    _samplers[index + i] = current;
                }

                if (counted)
                {
                    SwapReference(_samplerReferences, previous, current);
                }
            }
'''
TEXTURES_OLD = '''                else if (texture is TextureView view)
                {
                    storageChanged |= !ReferenceEquals(_textureRefs[index + i].Storage, view.Storage);
                    _textureRefs[index + i].Storage = view.Storage;
                    Auto<DisposableImageView> imageView = view.GetImageView();

                    if (counted)
                    {
                        SwapReference(_viewReferences, _textureRefs[index + i].View, imageView);
                    }

                    _textureRefs[index + i].View = imageView;
                }
                else if (!_isBuffer)
                {
                    storageChanged |= _textureRefs[index + i].Storage != null;
                    _textureRefs[index + i].Storage = null;

                    if (counted)
                    {
                        SwapReference(_viewReferences, _textureRefs[index + i].View, null);
                    }

                    _textureRefs[index + i].View = default;
                }
'''
TEXTURES_NEW = '''                else if (texture is TextureView view)
                {
                    // RewindBox (adapt_bindless_retention): the element's storage and image view are the view's.
                    TextureView previous = _views[index + i];
                    storageChanged |= !ReferenceEquals(previous?.Storage, view.Storage);

                    if (counted)
                    {
                        SwapReference(_viewReferences, previous?.GetImageView(), view.GetImageView());
                    }

                    _views[index + i] = view;
                }
                else if (!_isBuffer)
                {
                    TextureView previous = _views[index + i];
                    storageChanged |= previous?.Storage != null;

                    if (counted)
                    {
                        SwapReference(_viewReferences, previous?.GetImageView(), null);
                    }

                    _views[index + i] = null;
                }
'''
BARRIERS_OLD = '''                for (int index = 0; index < _textureRefs.Length; index++)
                {
                    if (_textureRefs[index].Storage != null)
                    {
                        storages.Add(_textureRefs[index].Storage);
                    }
                }
'''
BARRIERS_NEW = '''                for (int index = 0; index < _views.Length; index++)
                {
                    // RewindBox (adapt_bindless_retention): the storage of the element's view.
                    TextureStorage storage = _views[index]?.Storage;

                    if (storage != null)
                    {
                        storages.Add(storage);
                    }
                }
'''
WALK_OLD = '''                ref DescriptorImageInfo texture = ref textures[i];
                ref TextureRef refs = ref _textureRefs[i];

                if (i > 0 && _textureRefs[i - 1].View == refs.View && _textureRefs[i - 1].Sampler == refs.Sampler)
                {
                    texture = textures[i - 1];
                    RenderDetail.ArrayDestroyedViewWalkElements += destroyedView ? 1 : 0;

                    continue;
                }

                texture.ImageLayout = ImageLayout.General;
                texture.ImageView = refs.View?.Get(cbs).Value ?? default;
                texture.Sampler = refs.Sampler?.Get(cbs).Value ?? default;
                // RewindBox (adapt_artifact_counters): a view held but destroyed; the element takes the dummy (black) view below.
                destroyedView = refs.View != null && texture.ImageView.Handle == 0;
'''
WALK_NEW = '''                ref DescriptorImageInfo texture = ref textures[i];

                // RewindBox (adapt_bindless_retention): the element's image view and sampler, as the delivered TextureRef.
                if (i > 0 && SameElement(i - 1, i))
                {
                    texture = textures[i - 1];
                    RenderDetail.ArrayDestroyedViewWalkElements += destroyedView ? 1 : 0;

                    continue;
                }

                Auto<DisposableImageView> elementView = ViewAt(i);
                Auto<DisposableSampler> elementSampler = SamplerAt(i);

                texture.ImageLayout = ImageLayout.General;
                texture.ImageView = elementView?.Get(cbs).Value ?? default;
                texture.Sampler = elementSampler?.Get(cbs).Value ?? default;
                // RewindBox (adapt_artifact_counters): a view held but destroyed; the element takes the dummy (black) view below.
                destroyedView = elementView != null && texture.ImageView.Handle == 0;
'''
REBUILD_OLD = '''            for (int i = 0; i < _textureRefs.Length;)
            {
                ref TextureRef refs = ref _textureRefs[i];
                int run = 1;

                while (i + run < _textureRefs.Length && _textureRefs[i + run].View == refs.View && _textureRefs[i + run].Sampler == refs.Sampler)
                {
                    run++;
                }

                bool destroyed = false;

                if (refs.View != null)
                {
                    if (refs.View.GetUnsafe().Value.Handle != 0)
                    {
                        CollectionsMarshal.GetValueRefOrAddDefault(_viewReferences, refs.View, out _) += run;
                    }
                    else
                    {
                        destroyed = true;
                    }
                }

                if (refs.Sampler != null)
                {
                    if (refs.Sampler.GetUnsafe().Value.Handle != 0)
                    {
                        CollectionsMarshal.GetValueRefOrAddDefault(_samplerReferences, refs.Sampler, out _) += run;
                    }
'''
REBUILD_NEW = '''            for (int i = 0; i < _views.Length;)
            {
                // RewindBox (adapt_bindless_retention): the element's image view and sampler, as the delivered TextureRef.
                Auto<DisposableImageView> elementView = ViewAt(i);
                Auto<DisposableSampler> elementSampler = SamplerAt(i);
                int run = 1;

                while (i + run < _views.Length && SameElement(i + run, i))
                {
                    run++;
                }

                bool destroyed = false;

                if (elementView != null)
                {
                    if (elementView.GetUnsafe().Value.Handle != 0)
                    {
                        CollectionsMarshal.GetValueRefOrAddDefault(_viewReferences, elementView, out _) += run;
                    }
                    else
                    {
                        destroyed = true;
                    }
                }

                if (elementSampler != null)
                {
                    if (elementSampler.GetUnsafe().Value.Handle != 0)
                    {
                        CollectionsMarshal.GetValueRefOrAddDefault(_samplerReferences, elementSampler, out _) += run;
                    }
'''
RESOLVE_OLD = '''                ref TextureRef refs = ref _textureRefs[i];

                if (i > start && _textureRefs[i - 1].View == refs.View && _textureRefs[i - 1].Sampler == refs.Sampler)
                {
                    textures[i] = textures[i - 1];
                    RenderDetail.ArrayDestroyedViewRefreshElements += destroyedView ? 1 : 0;

                    continue;
                }

                ImageView view = refs.View?.GetUnsafe().Value ?? default;
                Silk.NET.Vulkan.Sampler sampler = refs.Sampler?.GetUnsafe().Value ?? default;
                // RewindBox (adapt_artifact_counters): a view held but destroyed; the element takes the dummy (black) view below.
                destroyedView = refs.View != null && view.Handle == 0;
'''
RESOLVE_NEW = '''                // RewindBox (adapt_bindless_retention): the element's image view and sampler, as the delivered TextureRef.
                if (i > start && SameElement(i - 1, i))
                {
                    textures[i] = textures[i - 1];
                    RenderDetail.ArrayDestroyedViewRefreshElements += destroyedView ? 1 : 0;

                    continue;
                }

                Auto<DisposableImageView> elementView = ViewAt(i);
                Auto<DisposableSampler> elementSampler = SamplerAt(i);
                ImageView view = elementView?.GetUnsafe().Value ?? default;
                Silk.NET.Vulkan.Sampler sampler = elementSampler?.GetUnsafe().Value ?? default;
                // RewindBox (adapt_artifact_counters): a view held but destroyed; the element takes the dummy (black) view below.
                destroyedView = elementView != null && view.Handle == 0;
'''
RELEASE_OLD = '''        protected override void ReleaseOwnDescriptorSets()
        {
            if (_slots == null)
'''
RELEASE_NEW = '''        protected override void ReleaseOwnDescriptorSets()
        {
            // RewindBox (adapt_bindless_retention): called by Dispose only; the array leaves the inventory once.
            if (!_inventoried)
            {
                _inventoried = true;
                Inventory(-1, -((long)(_textures?.Length ?? 0) * Unsafe.SizeOf<DescriptorImageInfo>() +
                                (long)(_views?.Length ?? 0) * IntPtr.Size + (long)(_samplers?.Length ?? 0) * IntPtr.Size +
                                (long)(_bufferTextureRefs?.Length ?? 0) * IntPtr.Size + (long)(_bufferTextures?.Length ?? 0) * IntPtr.Size));
            }

            if (_slots == null)
'''

DETAIL_OLD = '''            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));
'''
DETAIL_NEW = '''            // RewindBox (adapt_bindless_retention): the managed storage of the bindless pool arrays still held.
            text.Append(TextureArray.InventoryText());

            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    inventory = paths[INVENTORY]
    once(inventory, '''        void SetTextures(int index, ITexture[] textures);
    }
''', '''        void SetTextures(int index, ITexture[] textures);
    }
''' + INVENTORY_CLASS)

    cache = paths[CACHE]
    for old, new in ((ENTRY_FIELDS_OLD, ENTRY_FIELDS_NEW), (PREPARE_OLD, PREPARE_NEW), (PREPARE_END_OLD, PREPARE_END_NEW),
                     (UPDATE_OLD, UPDATE_NEW), (RENT_OLD, RENT_NEW), (FILL_OLD, FILL_NEW), (ADD_OLD, ADD_NEW),
                     (REMOVE_OLD, REMOVE_NEW), (REMOVE_END_OLD, REMOVE_END_NEW)):
        once(cache, old, new)

    array = paths[ARRAY]
    for old, new in ((REF_OLD, REF_NEW), (CTOR_OLD, CTOR_NEW), (SAMPLERS_OLD, SAMPLERS_NEW), (TEXTURES_OLD, TEXTURES_NEW),
                     (BARRIERS_OLD, BARRIERS_NEW), (WALK_OLD, WALK_NEW), (REBUILD_OLD, REBUILD_NEW),
                     (RESOLVE_OLD, RESOLVE_NEW), (RELEASE_OLD, RELEASE_NEW)):
        once(array, old, new)

    once(paths[DETAIL], DETAIL_OLD, DETAIL_NEW)
    return list(paths.values())
