"""Release, while the device is short of memory, the sampler textures only a texture pool holds and nothing has used for
a while; measure them in the host-memory report.

IPA 658, 5 November 2026, Hogwarts Legacy, player 1, pid 11152 (private logs, not in the repository; aggregate numbers
only): MoltenVK's "GPU memory allocated" (MTLDevice.currentAllocatedSize) rose from 852 to 1094 MiB in play while the
Core's two budgets held 204 MiB of textures (budget 768) and 119 MiB of buffers: 590-760 MiB of Metal memory lay
outside any budget or trim. The device stayed at 8-12 % RAM available from the first scene on (one memoryWarning, at
11 %); the device-short trim (7 % or less) ran once and released 87 MiB.

Why nothing bounds them (Core 658 preparation): TextureCache.FindOrCreateTexture adds only non-sampler textures to the
auto delete cache ("Sampler textures are managed by the texture pool"); a pool slot drops its texture only when the
guest rewrites that descriptor (TexturePool.InvalidateRangeImpl). TrimCaches can only reach the auto delete cache and
the buffer cache.

Change (GpuContext, TexturePool, Texture):
- every texture records a use epoch (GpuContext.TextureUseEpoch, a seconds clock CheckHostMemory reads once a second
  on the GPU thread) at each synchronisation, which every pool fetch, cached binding and bindless array use performs,
  and when a pool slot takes it in TexturePool.GetInternal;
- once a second, when kern.memorystatus_level (the signal TrimCaches uses) is 10 % or less, and at most every 10 s,
  one bounded pass releases the pool-only textures (the slot holds the one reference: no other slot or pool, no auto
  delete or short cache, no bound render target, no view, not a view, not a buffer texture) unused for 60 s, whose
  group has no handle with GPU-written data and no copy dependency (never flushed, never dropped: counted), with no
  format alias and not pinned; at most 256 textures and 64 MiB a pass. The release is InvalidateRangeImpl's for a
  changed descriptor without the short cache: the slot is emptied, logged for the bindless delta passes, the
  reference dropped (the texture is disposed: its InvalidatedSequence moves, so cached bindings and arrays rebind),
  and its next fetch re-creates it from guest memory. The host texture is released through the GAL command queue,
  after the draws already queued; the Vulkan backend frees it when the last command buffer using it completes;
- a slot fetched again with the same descriptor within 300 s of its release is never released again while its pool
  lives (pinned and counted); when the reloads since a pass reach half of what it released, the age doubles (at most
  480 s);
- one journal line per pass, and one line next to the 30 s host-memory report with the pool-only textures' estimated
  host size, the cold share, the share holding GPU-written data and the release totals.
No draw, effect, resolution or quality change: a released texture's authoritative data is in guest memory, and any
use re-creates it before the draw. Not measured on an iPhone. Fail closed on drift: each file must be the Core 658
preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': '9ee9ce1c4346489f8b589827d27b9a969e4dc6b6ca02d65aa0b8c7fc4148ecbe',
    'src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs': 'bb2049ad8a5af038076958926b51b2e4fa3f0608ac5a289a43678d44772d7f1a',
    'src/Ryujinx.Graphics.Gpu/Image/Texture.cs': '1a99f074c951c51f7369802f078b30779bece3266c427db1492995904656a283',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    texture = paths['src/Ryujinx.Graphics.Gpu/Image/Texture.cs']
    once(texture, '''        public ShortTextureCacheEntry ShortCacheEntry { get; set; }
''', '''        public ShortTextureCacheEntry ShortCacheEntry { get; set; }

        /// <summary>
        /// RewindBox (adapt_cold_texture_release): GpuContext.TextureUseEpoch (seconds) at the last synchronisation of this
        /// texture, which every pool fetch, cached binding and bindless array use performs, or when a pool slot took it.
        /// </summary>
        internal int LastUseEpoch;
''')
    once(texture, '''        public void SynchronizeMemory()
        {
            if (Target == Target.TextureBuffer)
''', '''        public void SynchronizeMemory()
        {
            // RewindBox (adapt_cold_texture_release): a use, whether or not there is anything to synchronise.
            LastUseEpoch = _context.TextureUseEpoch;

            if (Target == Target.TextureBuffer)
''')

    pool = paths['src/Ryujinx.Graphics.Gpu/Image/TexturePool.cs']
    once(pool, '''            _invalidMap = new BitMap(maximumId + 1);
        }
''', '''            _invalidMap = new BitMap(maximumId + 1);

            // RewindBox (adapt_cold_texture_release): the cold texture release and its measurement visit every live pool.
            lock (context.TexturePools)
            {
                context.TexturePools.Add(this);
            }
        }
''')
    once(pool, '''                else
                {
                    texture.SynchronizeMemory();
                }

                Items[id] = texture;
''', '''                else
                {
                    texture.SynchronizeMemory();
                }

                // RewindBox (adapt_cold_texture_release): a fetch is a use; the same descriptor fetched again soon after
                // its texture was released cold pins the slot.
                texture.LastUseEpoch = Context.TextureUseEpoch;

                if (_coldReleasedAt != null && _coldReleasedAt.Remove(id, out int releasedEpoch))
                {
                    NoteColdReload(id, releasedEpoch, descriptor.Equals(ref DescriptorCache[id]));
                }

                Items[id] = texture;
''')
    once(pool, '''        /// <summary>
        /// Removes all aliases for a texture.
        /// </summary>''', '''        // RewindBox (adapt_cold_texture_release): the slots whose texture was released cold (id -> use epoch of the
        // release), kept for the reload window, and the slots whose texture came back within it, never released again
        // while this pool lives. GPU thread only, allocated at the first release.
        private Dictionary<int, int> _coldReleasedAt;
        private HashSet<int> _coldPinned;

        /// <summary>
        /// Textures of this pool fetched again with the same descriptor within the reload window after a cold release,
        /// and the slots pinned for it (both cumulative).
        /// </summary>
        internal int ColdReloads;
        internal int ColdPinnedSlots;

        private void NoteColdReload(int id, int releasedEpoch, bool sameDescriptor)
        {
            if (sameDescriptor && Context.TextureUseEpoch - releasedEpoch <= GpuContext.ColdTextureReloadWindowSeconds)
            {
                ColdReloads++;

                if ((_coldPinned ??= new HashSet<int>()).Add(id))
                {
                    ColdPinnedSlots++;
                }
            }
        }

        /// <summary>
        /// Forgets the cold releases older than the reload window.
        /// </summary>
        internal void PruneColdReleases(int epoch)
        {
            if (_coldReleasedAt == null)
            {
                return;
            }

            foreach ((int id, int releasedEpoch) in _coldReleasedAt)
            {
                if (epoch - releasedEpoch > GpuContext.ColdTextureReloadWindowSeconds)
                {
                    _coldReleasedAt.Remove(id);
                }
            }
        }

        /// <summary>
        /// RewindBox (adapt_cold_texture_release): measures the textures only this pool holds and, when
        /// <paramref name="release"/> is set, releases those unused for <paramref name="minimumAge"/> seconds whose data
        /// is in guest memory, within the pass budgets (shared across pools through <paramref name="stats"/>).
        /// GPU thread only, between command lists.
        /// </summary>
        internal void ScanColdTextures(int epoch, int minimumAge, bool release, ulong byteBudget, int countBudget, ref GpuContext.ColdTextureStats stats)
        {
            Texture[] items = Items;

            if (items == null)
            {
                return;
            }

            for (int id = 0; id < items.Length; id++)
            {
                Texture texture = items[id];

                // Pool-only: this slot holds the one reference (no other slot or pool, no auto delete or short cache, no
                // bound render target, no view of it), and it is a storage texture, not a view or a buffer texture.
                if (texture == null ||
                    !texture.HasOneReference() ||
                    texture.CacheNode != null ||
                    texture.ShortCacheEntry != null ||
                    texture.IsView ||
                    texture.HasViews ||
                    texture.Group == null ||
                    texture.Group.Storage != texture ||
                    texture.Target == Target.TextureBuffer)
                {
                    continue;
                }

                ulong size = texture.GetEstimatedHostSize();

                stats.PoolOnly++;
                stats.PoolOnlyBytes += size;

                // Fetched, bound or synchronised by a binding or a bindless array within minimumAge seconds.
                if (epoch - texture.LastUseEpoch < minimumAge)
                {
                    continue;
                }

                // Data the GPU wrote, or a copy pending from another texture, may exist only in this host texture: it is
                // neither flushed nor dropped here.
                if (texture.Group.AnyHandleModified() || texture.Group.HasCopyDependencies)
                {
                    stats.GpuData++;
                    stats.GpuDataBytes += size;
                    continue;
                }

                // A format alias may be bound where only the alias is synchronised; a pinned slot came back soon after a
                // release.
                if (_aliasLists.ContainsKey(texture) || (_coldPinned != null && _coldPinned.Contains(id)))
                {
                    stats.Kept++;
                    continue;
                }

                stats.Cold++;
                stats.ColdBytes += size;

                if (!release || stats.Released >= countBudget || stats.ReleasedBytes + size > byteBudget)
                {
                    continue;
                }

                // As InvalidateRangeImpl does for a changed descriptor, without the short cache: the next fetch of this
                // slot re-creates the texture from guest memory. Another thread may empty the slot (unmap): only the
                // thread that empties it drops the reference.
                if (Interlocked.CompareExchange(ref items[id], null, texture) != texture)
                {
                    continue;
                }

                LogDeltaChange(id);

                (_coldReleasedAt ??= new Dictionary<int, int>())[id] = epoch;

                if (texture.DecrementReferenceCount(this, id))
                {
                    stats.Released++;
                    stats.ReleasedBytes += size;
                }

                RemoveAliasList(texture);
            }
        }

        /// <summary>
        /// Removes all aliases for a texture.
        /// </summary>''')
    once(pool, '''        public override void Dispose()
        {
            ProcessDereferenceQueue();
''', '''        public override void Dispose()
        {
            // RewindBox (adapt_cold_texture_release): no pass visits a disposed pool.
            lock (Context.TexturePools)
            {
                Context.TexturePools.Remove(this);
            }

            ProcessDereferenceQueue();
''')

    context = paths['src/Ryujinx.Graphics.Gpu/GpuContext.cs']
    once(context, '''                TrimCaches(device <= DeviceCriticalPercent ? MemoryPressureLevel.Critical : MemoryPressureLevel.Warning);
            }
''', '''                TrimCaches(device <= DeviceCriticalPercent ? MemoryPressureLevel.Critical : MemoryPressureLevel.Warning);
            }

            // RewindBox (adapt_cold_texture_release): the texture use clock, then the bounded release of cold pool-only
            // textures while the device is short.
            TextureUseEpoch = (int)(now / 1000);
            ReleaseColdTextures(device, now, out _);
''')
    once(context, '''            _lastHostMemoryReport = now;
''', '''            _lastHostMemoryReport = now;

            // RewindBox (adapt_cold_texture_release): the sampler textures only a pool holds, which none of the budgets
            // reported below counts.
            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            ColdTextureStats pools = MeasurePoolTextures(out int reloads, out int pinned);

            Logger.Info?.Print(LogClass.Gpu,
                $"Host memory: pool-only textures {pools.PoolOnly} ({pools.PoolOnlyBytes / TrimMiB} MiB, in no budget), " +
                $"unused for {_coldTextureAgeSeconds} s {pools.Cold} ({pools.ColdBytes / TrimMiB} MiB), unused but holding GPU-written data or copy-linked " +
                $"{pools.GpuData} ({pools.GpuDataBytes / TrimMiB} MiB); cold release so far {_coldReleasedTotal} textures " +
                $"({_coldReleasedBytesTotal / TrimMiB} MiB), reloads {reloads}, pinned slots {pinned}; " +
                $"{System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds:F1} ms (adapt_cold_texture_release)");
''')
    once(context, '''        /// <summary>
        /// Advances internal sequence number.
''', '''        // RewindBox (adapt_cold_texture_release): sampler textures only a texture pool holds are in no budget and no trim
        // (TextureCache.FindOrCreateTexture adds only the others to the auto delete cache). While the device is short of
        // memory, those unused for a while and whose data is in guest memory are released, in bounded passes.
        private const int ColdTextureDevicePercent = 10;
        private const long ColdTextureIntervalMs = 10_000;
        private const int ColdTextureInitialAgeSeconds = 60;
        private const int ColdTextureMaximumAgeSeconds = 480;
        internal const int ColdTextureReloadWindowSeconds = 300;
        internal const ulong ColdTextureMaxBytesPerPass = 64 * TrimMiB;
        internal const int ColdTextureMaxTexturesPerPass = 256;

        /// <summary>
        /// Seconds clock (Environment.TickCount64 / 1000) set once a second on the GPU thread by CheckHostMemory; textures
        /// record it at each use (Texture.LastUseEpoch). It stays 0 where host memory is not tracked: nothing ages there.
        /// </summary>
        internal int TextureUseEpoch;

        /// <summary>
        /// Live texture pools (added at creation, removed at disposal), visited by the cold texture release.
        /// </summary>
        internal readonly List<Image.TexturePool> TexturePools = [];

        /// <summary>
        /// Pool-only textures a scan measured (all), and of them, those unused for the age: holding GPU-written data
        /// (never released), kept (format alias or pinned slot), cold (releasable), released.
        /// </summary>
        internal struct ColdTextureStats
        {
            public int PoolOnly;
            public ulong PoolOnlyBytes;
            public int GpuData;
            public ulong GpuDataBytes;
            public int Kept;
            public int Cold;
            public ulong ColdBytes;
            public int Released;
            public ulong ReleasedBytes;
        }

        private long _lastColdTextureRelease;
        private int _coldTextureAgeSeconds = ColdTextureInitialAgeSeconds;
        private int _coldReloadsAtLastPass;
        private int _coldReleasedLastPass;
        private long _coldReleasedTotal;
        private ulong _coldReleasedBytesTotal;

        /// <summary>
        /// Seconds without use after which a pool-only texture is cold (doubles on systemic reloads).
        /// </summary>
        internal int ColdTextureAgeSeconds => _coldTextureAgeSeconds;

        /// <summary>
        /// RewindBox (adapt_cold_texture_release): when the device has 10 % of its RAM available or less, at most every
        /// 10 s, releases up to 256 textures and 64 MiB of cold pool-only textures, and journals the pass in one line.
        /// GPU thread, between command lists (CheckHostMemory, from Switch.ProcessFrame before GPFifo.DispatchCalls).
        /// </summary>
        /// <returns>True if a pass ran</returns>
        internal bool ReleaseColdTextures(int device, long now, out ColdTextureStats stats)
        {
            stats = default;

            if (device < 0 || device > ColdTextureDevicePercent ||
                (_lastColdTextureRelease != 0 && now - _lastColdTextureRelease < ColdTextureIntervalMs))
            {
                return false;
            }

            _lastColdTextureRelease = now;

            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            int epoch = TextureUseEpoch;
            int reloads = 0;
            int pinned = 0;
            int reloadsSinceLastPass;

            lock (TexturePools)
            {
                foreach (Image.TexturePool pool in TexturePools)
                {
                    reloads += pool.ColdReloads;
                    pinned += pool.ColdPinnedSlots;
                    pool.PruneColdReleases(epoch);
                }

                reloadsSinceLastPass = reloads - _coldReloadsAtLastPass;
                _coldReloadsAtLastPass = reloads;

                // Half of the previous pass's releases came back already: textures stay unused longer before release.
                if (_coldReleasedLastPass > 0 && reloadsSinceLastPass * 2 >= _coldReleasedLastPass)
                {
                    _coldTextureAgeSeconds = Math.Min(_coldTextureAgeSeconds * 2, ColdTextureMaximumAgeSeconds);
                }

                foreach (Image.TexturePool pool in TexturePools)
                {
                    pool.ScanColdTextures(epoch, _coldTextureAgeSeconds, true, ColdTextureMaxBytesPerPass, ColdTextureMaxTexturesPerPass, ref stats);
                }
            }

            _coldReleasedLastPass = stats.Released;
            _coldReleasedTotal += stats.Released;
            _coldReleasedBytesTotal += stats.ReleasedBytes;

            Logger.Info?.Print(LogClass.Gpu,
                $"Cold texture release: device {device}% available; pool-only textures {stats.PoolOnly} ({stats.PoolOnlyBytes / TrimMiB} MiB), " +
                $"unused for {_coldTextureAgeSeconds} s {stats.Cold} ({stats.ColdBytes / TrimMiB} MiB), released {stats.Released} " +
                $"({stats.ReleasedBytes / TrimMiB} MiB; at most {ColdTextureMaxTexturesPerPass} or {ColdTextureMaxBytesPerPass / TrimMiB} MiB a pass); " +
                $"reloads of recently released {reloadsSinceLastPass} (pinned slots {pinned}); skipped holding GPU-written data or copy-linked " +
                $"{stats.GpuData} ({stats.GpuDataBytes / TrimMiB} MiB), kept {stats.Kept}; " +
                $"{System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds:F1} ms (adapt_cold_texture_release)");

            return true;
        }

        /// <summary>
        /// Measures the pool-only textures of every live pool without releasing any, and the cumulative reloads and pins.
        /// </summary>
        internal ColdTextureStats MeasurePoolTextures(out int reloads, out int pinned)
        {
            ColdTextureStats stats = default;
            int epoch = TextureUseEpoch;

            reloads = 0;
            pinned = 0;

            lock (TexturePools)
            {
                foreach (Image.TexturePool pool in TexturePools)
                {
                    reloads += pool.ColdReloads;
                    pinned += pool.ColdPinnedSlots;
                    pool.ScanColdTextures(epoch, _coldTextureAgeSeconds, false, 0, 0, ref stats);
                }
            }

            return stats;
        }

        /// <summary>
        /// Advances internal sequence number.
''')
    return list(paths.values())
