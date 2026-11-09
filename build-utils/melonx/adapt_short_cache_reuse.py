"""Keep valid textures past the short texture cache's two presents, bounded (Core 709, lot 4).

Cause (production path, test/melonx_texture_pool_allocations): a texture a pool entry stops naming, held by nothing else, goes
to the short texture cache (TexturePool -> AddShortCache) and is destroyed when two presented frames later
ProcessShortCache drops the last reference (Window.Present -> TextureCache.Tick). A descriptor that names it again after
that finds nothing: TextureCache.FindOrCreateTexture creates a new texture and uploads all of its data from guest memory.
Production TexturePool/TextureCache/AutoDeleteCache on guest memory with a doubled renderer, 64 bindless elements named
for one frame then left for three, 120 frames after warm-up: 1 920 host textures created and 1 920 full uploads (one per
return), 682 B allocated per changed element; the same swap without a present in between creates nothing (66 B, the new
ShortTextureCacheEntry of each leaving texture).

Change (AutoDeleteCache): at expiry, a texture only the entry holds that is still valid (InvalidatedSequence unchanged,
mapping never changed, not a buffer texture, its descriptor still finds this entry, at most MaxRetainedTextureBytes) stays
on a retained list with its reference and its descriptor lookup instead of being destroyed. FindShortCache returns it like
an entry of the two ticks: the pool synchronizes its memory (CPU writes since are uploaded, as for any live texture) and
references it, which takes it off the list (RemoveShortCache). The list holds at most 1 024 textures and 32 MiB (estimated host
size, a view counts its storage); when full, an expiring texture is destroyed as before (evicting the oldest instead would,
on a cyclic reuse larger than the bounds, drop each texture just before its return and keep the bytes for nothing). A
retained texture is released 60 presents after its retention, as soon as it is found
invalidated or with a changed mapping, when a texture of the same descriptor supersedes it, at every TextureCache.Trim
(host memory pressure: all of them, before the auto delete cache) and at TextureCache.Dispose (close). Released entries
are reused (at most 256 kept), instead of one ShortTextureCacheEntry per leaving texture. Bounds (IPA 694 Hogwarts 1x,
pid 40200): texture budget 768 MiB, pool-only textures 165-213 MiB for 5 836-8 164 textures (about 28 KiB each);
32 MiB is 4 % of the budget, about 1 100 such textures, below the smallest TrimCaches release logged (29 MiB) and
released by each; 1 024 entries bound the list and lookup work; 60 presents is 2 s at 30 FPS, so an abandoned set of
textures goes within 2 s; a quarter of the bytes for one texture keeps a large one from flushing the list. Same thread as
before (the render loop runs Tick, the pool lookups and TrimCaches). A host memory journal line per 30 s report
(GpuContext.CheckHostMemory) counts the retained textures and their fates. Fail closed on drift: the three files must be
the Core 707 preparation's.
"""
import hashlib
from adapt_session import once

CACHE = 'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs'
TEXTURE_CACHE = 'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'
CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
BASELINE = {
    CACHE: 'fdd852b6972ac243198f1d6055d76b9ce99cbd5df33bcbbf10b99d0a96deaf13',
    TEXTURE_CACHE: '6d1f599458280e509a0821ef7805bb0e83806f109e58898c181127515fcd4a82',
    CONTEXT: '8600d75c306800c4672cc8f7274846783dde9c0f4feb264f3ee42450ac37593a',
}

ENTRY_FIELDS_OLD = '''        public bool IsAutoDelete;
        public readonly TextureDescriptor Descriptor;
        public readonly int InvalidatedSequence;
        public readonly Texture Texture;
'''
ENTRY_FIELDS_NEW = '''        public bool IsAutoDelete;
        // RewindBox (adapt_short_cache_reuse): writable, a released entry is reused for another texture (AutoDeleteCache).
        public TextureDescriptor Descriptor;
        public int InvalidatedSequence;
        public Texture Texture;

        // RewindBox (adapt_short_cache_reuse): set while the entry is kept past its two ticks, on the retained list (oldest
        // first); RetainedNext also links the reusable entries.
        public bool IsRetained;
        public ulong RetainedSize;
        public long RetainedTick;
        public ShortTextureCacheEntry RetainedPrevious;
        public ShortTextureCacheEntry RetainedNext;
'''

ENTRY_END_OLD = '''        public ShortTextureCacheEntry(Texture texture)
        {
            IsAutoDelete = true;
            InvalidatedSequence = texture.InvalidatedSequence;
            Texture = texture;
        }
    }
'''
ENTRY_END_NEW = '''        public ShortTextureCacheEntry(Texture texture)
        {
            IsAutoDelete = true;
            InvalidatedSequence = texture.InvalidatedSequence;
            Texture = texture;
        }

        /// <summary>
        /// RewindBox (adapt_short_cache_reuse): an entry for the reusable list, filled by AutoDeleteCache.RentEntry.
        /// </summary>
        public ShortTextureCacheEntry()
        {
        }
    }

    /// <summary>
    /// RewindBox (adapt_short_cache_reuse): the textures kept past the short cache's two ticks and what became of them.
    /// </summary>
    struct ShortCacheReuseStats
    {
        public int Retained;
        public ulong RetainedBytes;
        public ulong PeakRetainedBytes;
        public long Reused;
        public long ReleasedByAge;
        public long RefusedByBound;
        public long ReleasedAll;
        public long ReleasedInvalid;
        public long DestroyedOnExpiry;

        public void Add(in ShortCacheReuseStats other)
        {
            Retained += other.Retained;
            RetainedBytes += other.RetainedBytes;
            PeakRetainedBytes += other.PeakRetainedBytes;
            Reused += other.Reused;
            ReleasedByAge += other.ReleasedByAge;
            RefusedByBound += other.RefusedByBound;
            ReleasedAll += other.ReleasedAll;
            ReleasedInvalid += other.ReleasedInvalid;
            DestroyedOnExpiry += other.DestroyedOnExpiry;
        }
    }
'''

FIELDS_OLD = '''        private readonly Dictionary<TextureDescriptor, ShortTextureCacheEntry> _shortCacheLookup;
'''
FIELDS_NEW = '''        private readonly Dictionary<TextureDescriptor, ShortTextureCacheEntry> _shortCacheLookup;

        // RewindBox (adapt_short_cache_reuse): bounds of the textures kept past the short cache's two ticks (ProcessShortCache).
        public const int MaxRetainedEntries = 1024;
        public const ulong MaxRetainedBytes = 32 * MiB;
        public const ulong MaxRetainedTextureBytes = MaxRetainedBytes / 4;
        public const long MaxRetainedTicks = 60;
        private const int MaxReusableEntries = 256;

        private ShortTextureCacheEntry _retainedOldest;
        private ShortTextureCacheEntry _retainedNewest;
        private ShortTextureCacheEntry _reusableEntries;
        private int _reusableCount;
        private long _shortCacheTicks;
        private ShortCacheReuseStats _reuse;

        public ShortCacheReuseStats ShortCacheReuse => _reuse;
'''

TRIM_START_OLD = '''            LastTrimKeptBytes = 0;

            if (!GraphicsConfig.EnableHostMemoryBudgetTracking)
            {
                return 0;
            }
'''
TRIM_START_NEW = '''            LastTrimKeptBytes = 0;

            // RewindBox (adapt_short_cache_reuse): host memory pressure first releases every texture kept past the short
            // cache's two ticks (counted when the release destroys it).
            ulong retained = ReleaseAllRetained();

            if (!GraphicsConfig.EnableHostMemoryBudgetTracking)
            {
                return retained;
            }
'''

TRIM_END_OLD = '''            if (target >= _totalSize)
            {
                return 0;
            }

            ulong before = _totalSize;

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
'''
TRIM_END_NEW = '''            if (target >= _totalSize)
            {
                return retained;
            }

            ulong before = _totalSize;

            if (freeOnly)
            {
                TrimUnreferencedTextures(target);

                return before - _totalSize + retained;
            }

            while (_totalSize > target && _textures.Count > 0)
            {
                RemoveLeastUsedTexture();
            }

            return before - _totalSize + retained;
        }
'''

SHORT_OLD = '''        public Texture FindShortCache(in TextureDescriptor descriptor)
        {
            if (_shortCacheLookup.Count > 0 && _shortCacheLookup.TryGetValue(descriptor, out ShortTextureCacheEntry entry))
            {
                if (entry.InvalidatedSequence == entry.Texture.InvalidatedSequence)
                {
                    return entry.Texture;
                }
                else
                {
                    _shortCacheLookup.Remove(descriptor);
                }
            }

            return null;
        }

        /// <summary>
        /// Removes a texture from the short duration cache.
        /// </summary>
        /// <param name="texture">Texture to remove from the short cache</param>
        public void RemoveShortCache(Texture texture)
        {
            bool removed = _shortCache.Remove(texture.ShortCacheEntry);
            removed |= _shortCacheBuilder.Remove(texture.ShortCacheEntry);

            if (removed)
            {
                texture.DecrementReferenceCount();

                if (!texture.ShortCacheEntry.IsAutoDelete)
                {
                    _shortCacheLookup.Remove(texture.ShortCacheEntry.Descriptor);
                }

                texture.ShortCacheEntry = null;
            }
        }

        /// <summary>
        /// Adds a texture to the short duration cache.
        /// It starts in the builder set, and it is moved into the deletion set on next process.
        /// </summary>
        /// <param name="texture">Texture to add to the short cache</param>
        /// <param name="descriptor">Last used texture descriptor</param>
        public void AddShortCache(Texture texture, ref TextureDescriptor descriptor)
        {
            ShortTextureCacheEntry entry = new(descriptor, texture);

            _shortCacheBuilder.Add(entry);
            _shortCacheLookup.Add(entry.Descriptor, entry);

            texture.ShortCacheEntry = entry;

            texture.IncrementReferenceCount();
        }

        /// <summary>
        /// Adds a texture to the short duration cache without a descriptor. This typically keeps it alive for two ticks.
        /// On expiry, it will be removed from the AutoDeleteCache.
        /// </summary>
        /// <param name="texture">Texture to add to the short cache</param>
        public void AddShortCache(Texture texture)
        {
            if (texture.ShortCacheEntry == null)
            {
                ShortTextureCacheEntry entry = new(texture);

                _shortCacheBuilder.Add(entry);

                texture.ShortCacheEntry = entry;

                texture.IncrementReferenceCount();
            }
        }

        /// <summary>
        /// Delete textures from the short duration cache.
        /// Moves the builder set to be deleted on next process.
        /// </summary>
        public void ProcessShortCache()
        {
            HashSet<ShortTextureCacheEntry> toRemove = _shortCache;

            foreach (ShortTextureCacheEntry entry in toRemove)
            {
                entry.Texture.DecrementReferenceCount();

                if (entry.IsAutoDelete)
                {
                    Remove(entry.Texture, false);
                }
                else
                {
                    _shortCacheLookup.Remove(entry.Descriptor);
                }

                entry.Texture.ShortCacheEntry = null;
            }

            toRemove.Clear();
            _shortCache = _shortCacheBuilder;
            _shortCacheBuilder = toRemove;
        }

'''
SHORT_NEW = '''        public Texture FindShortCache(in TextureDescriptor descriptor)
        {
            if (_shortCacheLookup.Count > 0 && _shortCacheLookup.TryGetValue(descriptor, out ShortTextureCacheEntry entry))
            {
                // RewindBox (adapt_short_cache_reuse): a texture kept past the two ticks is returned only while it was not
                // invalidated and its mapping never changed; otherwise it is released now. The pool then synchronizes its
                // memory (CPU writes since are uploaded) and references it, which takes it off the retained list.
                if (entry.IsRetained)
                {
                    if (entry.InvalidatedSequence == entry.Texture.InvalidatedSequence && !entry.Texture.ChangedMapping)
                    {
                        _reuse.Reused++;

                        return entry.Texture;
                    }

                    _reuse.ReleasedInvalid++;
                    ReleaseRetainedEntry(entry);

                    return null;
                }

                if (entry.InvalidatedSequence == entry.Texture.InvalidatedSequence)
                {
                    return entry.Texture;
                }
                else
                {
                    _shortCacheLookup.Remove(descriptor);
                }
            }

            return null;
        }

        /// <summary>
        /// Removes a texture from the short duration cache.
        /// </summary>
        /// <param name="texture">Texture to remove from the short cache</param>
        public void RemoveShortCache(Texture texture)
        {
            // RewindBox (adapt_short_cache_reuse): a retained entry leaves the retained list (its texture is referenced
            // again, or invalidated).
            if (texture.ShortCacheEntry is { IsRetained: true } retained)
            {
                ReleaseRetainedEntry(retained);

                return;
            }

            ShortTextureCacheEntry entry = texture.ShortCacheEntry;
            bool removed = _shortCache.Remove(entry);
            removed |= _shortCacheBuilder.Remove(entry);

            if (removed)
            {
                texture.DecrementReferenceCount();

                if (!entry.IsAutoDelete)
                {
                    _shortCacheLookup.Remove(entry.Descriptor);
                }

                texture.ShortCacheEntry = null;
                ReturnEntry(entry);
            }
        }

        /// <summary>
        /// Adds a texture to the short duration cache.
        /// It starts in the builder set, and it is moved into the deletion set on next process.
        /// </summary>
        /// <param name="texture">Texture to add to the short cache</param>
        /// <param name="descriptor">Last used texture descriptor</param>
        public void AddShortCache(Texture texture, ref TextureDescriptor descriptor)
        {
            // RewindBox (adapt_short_cache_reuse): a retained texture listed under the same descriptor is superseded.
            if (_shortCacheLookup.TryGetValue(descriptor, out ShortTextureCacheEntry previous) && previous.IsRetained)
            {
                _reuse.ReleasedInvalid++;
                ReleaseRetainedEntry(previous);
            }

            ShortTextureCacheEntry entry = RentEntry(texture, descriptor, isAutoDelete: false);

            _shortCacheBuilder.Add(entry);
            _shortCacheLookup.Add(entry.Descriptor, entry);

            texture.ShortCacheEntry = entry;

            texture.IncrementReferenceCount();
        }

        /// <summary>
        /// Adds a texture to the short duration cache without a descriptor. This typically keeps it alive for two ticks.
        /// On expiry, it will be removed from the AutoDeleteCache.
        /// </summary>
        /// <param name="texture">Texture to add to the short cache</param>
        public void AddShortCache(Texture texture)
        {
            if (texture.ShortCacheEntry == null)
            {
                ShortTextureCacheEntry entry = RentEntry(texture, default, isAutoDelete: true);

                _shortCacheBuilder.Add(entry);

                texture.ShortCacheEntry = entry;

                texture.IncrementReferenceCount();
            }
        }

        /// <summary>
        /// Delete textures from the short duration cache.
        /// Moves the builder set to be deleted on next process.
        /// </summary>
        public void ProcessShortCache()
        {
            HashSet<ShortTextureCacheEntry> toRemove = _shortCache;

            // RewindBox (adapt_short_cache_reuse): one tick per presented frame (Window.Present).
            _shortCacheTicks++;

            foreach (ShortTextureCacheEntry entry in toRemove)
            {
                // RewindBox (adapt_short_cache_reuse): instead of being destroyed, a valid texture that only this entry
                // holds is kept, still found by its descriptor, within the retained bounds.
                if (TryRetain(entry))
                {
                    continue;
                }

                bool destroyed = entry.Texture.DecrementReferenceCount();

                if (entry.IsAutoDelete)
                {
                    Remove(entry.Texture, false);
                }
                else
                {
                    _shortCacheLookup.Remove(entry.Descriptor);

                    if (destroyed)
                    {
                        _reuse.DestroyedOnExpiry++;
                    }
                }

                entry.Texture.ShortCacheEntry = null;
                ReturnEntry(entry);
            }

            toRemove.Clear();
            _shortCache = _shortCacheBuilder;
            _shortCacheBuilder = toRemove;

            // RewindBox (adapt_short_cache_reuse): a texture not named again within MaxRetainedTicks presents goes.
            ReleaseRetained(_shortCacheTicks - MaxRetainedTicks);
        }

        /// <summary>
        /// RewindBox (adapt_short_cache_reuse): keeps an expiring short cache entry on the retained list instead of destroying
        /// its texture. Only a texture this entry alone holds would be destroyed now (one held elsewhere stays alive and the
        /// texture cache finds it again). Not kept: an invalidated texture or one whose mapping changed, a buffer texture, an
        /// entry its descriptor no longer finds, a texture above MaxRetainedTextureBytes, or any when the list is full. The
        /// entry keeps its reference and its descriptor lookup.
        /// </summary>
        private bool TryRetain(ShortTextureCacheEntry entry)
        {
            Texture texture = entry.Texture;

            if (entry.IsAutoDelete ||
                !texture.HasOneReference() ||
                entry.InvalidatedSequence != texture.InvalidatedSequence ||
                texture.ChangedMapping ||
                texture.Target == Target.TextureBuffer ||
                !_shortCacheLookup.TryGetValue(entry.Descriptor, out ShortTextureCacheEntry listed) ||
                !ReferenceEquals(listed, entry))
            {
                return false;
            }

            // A view keeps its storage alive: the storage is counted.
            ulong size = (texture.Group?.Storage ?? texture).GetEstimatedHostSize();

            if (size > MaxRetainedTextureBytes)
            {
                return false;
            }

            // A full list keeps what it holds: evicting the oldest would, on a cyclic reuse larger than the bounds, drop
            // each texture just before it comes back and hold the bytes for nothing. The texture expires as before.
            if (_reuse.Retained >= MaxRetainedEntries || _reuse.RetainedBytes + size > MaxRetainedBytes)
            {
                _reuse.RefusedByBound++;

                return false;
            }

            entry.IsRetained = true;
            entry.RetainedSize = size;
            entry.RetainedTick = _shortCacheTicks;
            entry.RetainedPrevious = _retainedNewest;
            entry.RetainedNext = null;

            if (_retainedNewest != null)
            {
                _retainedNewest.RetainedNext = entry;
            }
            else
            {
                _retainedOldest = entry;
            }

            _retainedNewest = entry;
            _reuse.Retained++;
            _reuse.RetainedBytes += size;
            _reuse.PeakRetainedBytes = Math.Max(_reuse.PeakRetainedBytes, _reuse.RetainedBytes);

            return true;
        }

        /// <summary>
        /// RewindBox (adapt_short_cache_reuse): releases the retained entries kept at or before the given tick (the list is
        /// in retention order).
        /// </summary>
        private void ReleaseRetained(long expiredTick)
        {
            while (_retainedOldest != null && _retainedOldest.RetainedTick <= expiredTick)
            {
                _reuse.ReleasedByAge++;
                ReleaseRetainedEntry(_retainedOldest);
            }
        }

        /// <summary>
        /// RewindBox (adapt_short_cache_reuse): releases every retained texture (host memory pressure, teardown).
        /// </summary>
        /// <returns>Estimated host bytes of the textures the release destroyed</returns>
        public ulong ReleaseAllRetained()
        {
            ulong released = 0;

            while (_retainedOldest != null)
            {
                ulong size = _retainedOldest.RetainedSize;

                _reuse.ReleasedAll++;

                if (ReleaseRetainedEntry(_retainedOldest))
                {
                    released += size;
                }
            }

            return released;
        }

        /// <summary>
        /// RewindBox (adapt_short_cache_reuse): takes an entry off the retained list, its descriptor lookup and its texture,
        /// then drops its reference.
        /// </summary>
        /// <returns>True if the texture was destroyed</returns>
        private bool ReleaseRetainedEntry(ShortTextureCacheEntry entry)
        {
            if (entry.RetainedPrevious != null)
            {
                entry.RetainedPrevious.RetainedNext = entry.RetainedNext;
            }
            else
            {
                _retainedOldest = entry.RetainedNext;
            }

            if (entry.RetainedNext != null)
            {
                entry.RetainedNext.RetainedPrevious = entry.RetainedPrevious;
            }
            else
            {
                _retainedNewest = entry.RetainedPrevious;
            }

            _reuse.Retained--;
            _reuse.RetainedBytes -= entry.RetainedSize;
            entry.IsRetained = false;

            if (_shortCacheLookup.TryGetValue(entry.Descriptor, out ShortTextureCacheEntry listed) && ReferenceEquals(listed, entry))
            {
                _shortCacheLookup.Remove(entry.Descriptor);
            }

            Texture texture = entry.Texture;

            texture.ShortCacheEntry = null;
            ReturnEntry(entry);

            return texture.DecrementReferenceCount();
        }

        /// <summary>
        /// RewindBox (adapt_short_cache_reuse): an entry from the reusable list, or a new one.
        /// </summary>
        private ShortTextureCacheEntry RentEntry(Texture texture, in TextureDescriptor descriptor, bool isAutoDelete)
        {
            ShortTextureCacheEntry entry = _reusableEntries;

            if (entry != null)
            {
                _reusableEntries = entry.RetainedNext;
                _reusableCount--;
                entry.RetainedNext = null;
            }
            else
            {
                entry = new ShortTextureCacheEntry();
            }

            entry.IsAutoDelete = isAutoDelete;
            entry.Descriptor = isAutoDelete ? default : descriptor;
            entry.InvalidatedSequence = texture.InvalidatedSequence;
            entry.Texture = texture;

            return entry;
        }

        /// <summary>
        /// RewindBox (adapt_short_cache_reuse): clears an entry no set, lookup, list or texture holds any more, and keeps up
        /// to MaxReusableEntries of them for reuse.
        /// </summary>
        private void ReturnEntry(ShortTextureCacheEntry entry)
        {
            entry.Texture = null;
            entry.Descriptor = default;
            entry.IsAutoDelete = false;
            entry.IsRetained = false;
            entry.RetainedPrevious = null;
            entry.RetainedNext = null;

            if (_reusableCount < MaxReusableEntries)
            {
                entry.RetainedNext = _reusableEntries;
                _reusableEntries = entry;
                _reusableCount++;
            }
        }

'''

STATS_OLD = '''        public ulong CacheLimit => _cache.MaxSize;
'''
STATS_NEW = '''        public ulong CacheLimit => _cache.MaxSize;

        // RewindBox (adapt_short_cache_reuse): the textures kept past the short cache's two ticks.
        public ShortCacheReuseStats ShortCacheReuse => _cache.ShortCacheReuse;
'''

DISPOSE_OLD = '''        public void Dispose()
        {
            int released = 0;
            int stale = 0;
'''
DISPOSE_NEW = '''        public void Dispose()
        {
            // RewindBox (adapt_short_cache_reuse): the retained textures are released first, as their references would be.
            _cache.ReleaseAllRetained();

            int released = 0;
            int stale = 0;
'''

JOURNAL_OLD = '''            RecordMemoryInventory(device, textures, textureLimit, buffers, bufferLimit);
        }
'''
JOURNAL_NEW = '''            // RewindBox (adapt_short_cache_reuse): textures kept past the short cache's two presents and what became of them.
            Image.ShortCacheReuseStats reuse = default;

            foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
            {
                reuse.Add(physicalMemory.TextureCache.ShortCacheReuse);
            }

            Logger.Info?.Print(LogClass.Gpu,
                $"Short texture cache: kept past two presents {reuse.Retained} ({reuse.RetainedBytes / TrimMiB} MiB, peak " +
                $"{reuse.PeakRetainedBytes / TrimMiB} MiB; at most {Image.AutoDeleteCache.MaxRetainedEntries}, " +
                $"{Image.AutoDeleteCache.MaxRetainedBytes / TrimMiB} MiB, {Image.AutoDeleteCache.MaxRetainedTicks} presents), " +
                $"reused {reuse.Reused}, released by age {reuse.ReleasedByAge}, not kept (list full) {reuse.RefusedByBound}, " +
                $"by memory pressure or close {reuse.ReleasedAll}, invalidated or superseded {reuse.ReleasedInvalid}; " +
                $"destroyed at expiry {reuse.DestroyedOnExpiry} (adapt_short_cache_reuse)");

            RecordMemoryInventory(device, textures, textureLimit, buffers, bufferLimit);
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[CACHE], ENTRY_FIELDS_OLD, ENTRY_FIELDS_NEW)
    once(paths[CACHE], ENTRY_END_OLD, ENTRY_END_NEW)
    once(paths[CACHE], FIELDS_OLD, FIELDS_NEW)
    once(paths[CACHE], TRIM_START_OLD, TRIM_START_NEW)
    once(paths[CACHE], TRIM_END_OLD, TRIM_END_NEW)
    once(paths[CACHE], SHORT_OLD, SHORT_NEW)
    once(paths[TEXTURE_CACHE], STATS_OLD, STATS_NEW)
    once(paths[TEXTURE_CACHE], DISPOSE_OLD, DISPOSE_NEW)
    once(paths[CONTEXT], JOURNAL_OLD, JOURNAL_NEW)
    return list(paths.values())
