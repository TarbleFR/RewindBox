"""While only the device is short of memory, trim the texture cache without flushes or pretend releases.

Build 621 logs of 3 November 2026 (Hogwarts Legacy, Core 4ad8814e, an 8 GiB iPhone, sessions 12AAAE01 and
2F562F0F; private player logs, not in the repository): adapt_device_memory trims the GPU caches every 10 s while
kern.memorystatus_level is 7 % or less, and on every host pressure notification while the device is short,
whatever this process's headroom. In session 2F562F0F that made 68 trims "releasing" 2008 MiB in 13 minutes
while this process kept 880-1400 MiB of headroom to its own limit:

- the device share stayed at 4-7 % and the footprint kept rising (4.8 to 5.3 GiB): no trim relieved anything;
- the texture cache sat at its trim floor (95 of 768 MiB, an eighth) and every trim took 15-45 MiB of it again,
  i.e. textures used within the last 10 s;
- AutoDeleteCache.Trim evicts by LRU order whatever the texture is: one still referenced by a texture pool loses
  only its cache membership (nothing is freed, the "released" bytes are not), and one holding data the GPU wrote
  is first flushed to guest memory (a render-thread round trip). The 5 s windows with a trim spent a median 52 ms
  (session 12AAAE01, up to 301 ms) and up to 120 ms (2F562F0F) in texture flushes, against 0-6.5 ms without one,
  plus about 6 ms more texture synchronisation and 26-29 ms more buffer loads.

Change, only when the device is short while this process's own headroom is comfortable (768 MiB or more, the
threshold below which upstream MeloNX already trims): the texture cache evicts, in LRU order, only the textures it
alone holds (Texture.HasOneReference) and whose group has no handle with GPU-written data
(TextureGroup.AnyHandleModified), so each eviction destroys its texture without a flush. As the delivered eviction,
it first synchronises the dependents of a texture whose memory the CPU has not dirtied (copies other handles deferred
from it read its host texture; an independent review found that skipping this left a deferred copy reading a released
texture). The others stay in place
and are counted (kept bytes in the trim line). Targets, floor, intervals, the buffer cache and every trim under
this process's own pressure (headroom under 768 MiB, critical under 256 MiB, or unknown) are unchanged; so is the
ordinary capacity eviction. No rendering, synchronisation, cache file or setting changes. Not measured on an
iPhone; no FPS gain is claimed. Fail closed on drift: each file must be the Core 631 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': 'c0e4fbfe9fc77332dcfdfd87d387a2a4e27c069ce86bd94f7f9dbb7ea59d742f',
    'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs': 'cc1c77cd40639c9b6cc79fc339fc8abf12ce92efd99910aa29ce34b8164b8025',
    'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs': '77d8be5373ec7256c375c5ad14045c1d4ce7ed4068d333119fa362bd935b9470',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    cache = paths['src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs']
    once(cache, '''        public ulong Trim(MemoryPressureLevel level)
        {''', '''        /// <param name="freeOnly">Evict only textures the eviction destroys without a flush (the device is short, not this process)</param>
        public ulong Trim(MemoryPressureLevel level, bool freeOnly = false)
        {
            LastTrimKeptBytes = 0;
''')
    once(cache, '''            ulong before = _totalSize;

            while (_totalSize > target && _textures.Count > 0)
            {
                RemoveLeastUsedTexture();
            }

            return before - _totalSize;
        }
''', '''            ulong before = _totalSize;

            if (freeOnly)
            {
                TrimUnreferencedTextures(target);

                return before - _totalSize;
            }

            while (_totalSize > target && _textures.Count > 0)
            {
                RemoveLeastUsedTexture();
            }

            return before - _totalSize;
        }

        /// <summary>
        /// Bytes of the textures the last trim walked and kept because a pool still referenced them or they held
        /// GPU-written data (textures past the point where the target was reached are not counted).
        /// </summary>
        public ulong LastTrimKeptBytes { get; private set; }

        /// <summary>
        /// RewindBox (adapt_device_short_trim): evicts, least recently used first, only the textures this cache alone
        /// holds and whose group has no GPU-written data, so each eviction destroys its texture and needs no flush.
        /// A texture a pool still references would only leave the cache; one with GPU-written data would be flushed.
        /// </summary>
        /// <param name="target">Size to trim the cache down to</param>
        private void TrimUnreferencedTextures(ulong target)
        {
            ulong kept = 0;
            LinkedListNode<Texture> node = _textures.First;

            while (_totalSize > target && node != null)
            {
                LinkedListNode<Texture> next = node.Next;
                Texture texture = node.Value;

                if (texture.HasOneReference() && !texture.Group.AnyHandleModified())
                {
                    // As RemoveLeastUsedTexture: resolve copies other handles deferred from this texture before it
                    // is released (they read its host texture). No flush: no handle holds GPU-written data.
                    if (!texture.CheckModified(false))
                    {
                        texture.Group.SynchronizeDependents(texture);
                    }

                    _totalSize -= texture.CacheSize;
                    texture.CacheSize = 0;

                    _textures.Remove(node);

                    texture.DecrementReferenceCount();
                    texture.CacheNode = null;
                }
                else
                {
                    kept += texture.CacheSize;
                }

                // Disposal never edits this list; stop rather than walk a node that left it.
                node = next != null && next.List == _textures ? next : null;
            }

            LastTrimKeptBytes = kept;
        }
''')

    texture_cache = paths['src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs']
    once(texture_cache, '''        public ulong Trim(MemoryPressureLevel level)
        {
            return _cache.Trim(level);
        }
''', '''        public ulong Trim(MemoryPressureLevel level, bool freeOnly = false)
        {
            return _cache.Trim(level, freeOnly);
        }

        /// <summary>
        /// Bytes of textures the last trim kept (in use by a pool or holding GPU-written data).
        /// </summary>
        public ulong LastTrimKeptBytes => _cache.LastTrimKeptBytes;
''')

    context = paths['src/Ryujinx.Graphics.Gpu/GpuContext.cs']
    once(context, '''            _lastTrimTimestamp = now;

            ulong evicted = 0;

            foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
            {
                evicted += physicalMemory.TextureCache.Trim(level);
                evicted += physicalMemory.BufferCache.Trim(level);
            }
''', '''            _lastTrimTimestamp = now;

            // RewindBox (adapt_device_short_trim): only the device is short, this process keeps a comfortable headroom.
            // Trim only textures whose eviction frees them without a flush; this process's own pressure evicts as before.
            bool freeOnly = deviceShort && available >= ComfortableHeadroomBytes;

            ulong evicted = 0;
            ulong kept = 0;

            foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
            {
                evicted += physicalMemory.TextureCache.Trim(level, freeOnly);
                kept += physicalMemory.TextureCache.LastTrimKeptBytes;
                evicted += physicalMemory.BufferCache.Trim(level);
            }
''')
    once(context, '''            Logger.Info?.Print(LogClass.Gpu,
                $"Host reported {level} memory pressure{headroom}, released {evicted / TrimMiB} MiB of GPU caches");''',
         '''            string retained = freeOnly ? $"; device short only: kept {kept / TrimMiB} MiB of textures in use or holding GPU data" : string.Empty;

            Logger.Info?.Print(LogClass.Gpu,
                $"Host reported {level} memory pressure{headroom}, released {evicted / TrimMiB} MiB of GPU caches{retained}");''')
    return list(paths.values())
