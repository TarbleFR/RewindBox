"""Give GPU cache memory back when the whole device runs short, and say where memory goes.

Hogwarts Legacy v1.0.4, build 586, 28 October 2026 (one 12.7-minute session,
iPhone with an A18 Pro, 6,143 MiB process limit): the per-second journal's
mem= field (footprint/headroom/device available %/donors) shows the footprint
rising from 3.2 to 4.9 GiB while kern.memorystatus_level, the share of device
RAM iOS reports available, fell to 4-7 %. The 90 s spent at 7 % or less ran
at a median 4-6 FPS (every second below 20 FPS); the 640 s at 8 % or more at
a median 30 FPS. The RamDonor processes hold the guest memory outside this
process, so the device runs short while this process still has 1.2 GiB of
headroom to its own limit.

GpuContext.TrimCaches (upstream MeloNX) ignores host memory pressure while
os_proc_available_memory is 768 MiB or more ("only when this process looks
like the one under pressure"); the session's two memory warnings came with
2.2 and 1.3 GiB of headroom, so nothing was ever released (no "Host reported
... released" line). iOS also signals pressure on transitions only, not while
it lasts.

- HostMemoryBudget.DeviceAvailablePercent reads kern.memorystatus_level (-1
  when unreadable), as the host journal and the .NET GC do.
- TrimCaches no longer ignores pressure when the device has 7 % or less
  available, whatever this process's headroom; its log line adds the device
  share.
- GpuContext.CheckHostMemory, called once per frame from Switch.ProcessFrame
  on the GPU thread (where TrimCaches already runs), reads that share once a
  second. At 7 % or less it trims as for a Warning (a quarter of what the
  texture and buffer caches hold, least recently used and evictable only, never
  below an eighth of their limits), at 3 % or less as for a Critical (half), at
  most every 10 s. Evicted entries are rebuilt from guest memory when used
  again, as after any trim.
- Every 30 s one Info line gives the footprint, the headroom, the device share,
  the texture and buffer caches against their limits and the managed heap, so
  the next device log shows where the memory is.

Only with "Track available memory" (EnableHostMemoryBudgetTracking, the
default) and only on iOS. Not measured on a device; the 90 s above are a
correlation in one session, not a proven cause. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    budget = source / 'src/Ryujinx.Memory/HostMemoryBudget.cs'
    context = source / 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
    switch = source / 'src/Ryujinx.HLE/Switch.cs'
    textures = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureCache.cs'
    auto_delete = source / 'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs'
    buffers = source / 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'

    once(budget, '''            return Math.Clamp(total / (ulong)divisor, min, max);
        }
    }
}
''', '''            return Math.Clamp(total / (ulong)divisor, min, max);
        }

        [LibraryImport("libSystem.dylib", EntryPoint = "sysctlbyname", StringMarshalling = StringMarshalling.Utf8)]
        private static unsafe partial int SysctlByName(string name, void* oldValue, nuint* oldLength, void* newValue, nuint newLength);

        /// <summary>
        /// Share of the device's RAM iOS reports available (kern.memorystatus_level, 0 to 100), or -1 when
        /// it cannot be read. Unlike <see cref="AvailableBytes"/>, this process's headroom to its own limit,
        /// it falls when the whole device runs short.
        /// </summary>
        public static unsafe int DeviceAvailablePercent
        {
            get
            {
                if (!OperatingSystem.IsIOS())
                {
                    return -1;
                }

                try
                {
                    int level = 0;
                    nuint size = sizeof(int);

                    return SysctlByName("kern.memorystatus_level", &level, &size, null, 0) == 0 ? level : -1;
                }
                catch (EntryPointNotFoundException)
                {
                    return -1;
                }
            }
        }
    }
}
''')

    once(context, '''            ulong available = HostMemoryBudget.AvailableBytes;

            if (available != 0)
            {
                if (available >= ComfortableHeadroomBytes)
                {
''', '''            ulong available = HostMemoryBudget.AvailableBytes;
            int device = HostMemoryBudget.DeviceAvailablePercent;

            // The headroom is this process's own limit. The device can run short first: the RamDonor
            // processes hold the guest memory, and iOS compresses everything else.
            bool deviceShort = device >= 0 && device <= DeviceShortPercent;

            if (available != 0)
            {
                if (available >= ComfortableHeadroomBytes && !deviceShort)
                {
''')
    once(context, '''            string headroom = available != 0 ? $", {available / TrimMiB} MiB available" : string.Empty;
''', '''            string headroom = (available != 0 ? $", {available / TrimMiB} MiB available" : string.Empty) +
                (device >= 0 ? $", device {device}% available" : string.Empty);
''')
    once(context, '''        /// <summary>
        /// Advances internal sequence number.
        /// This forces the update of any modified GPU resource.
        /// </summary>
''', '''        private const int DeviceShortPercent = 7;
        private const int DeviceCriticalPercent = 3;
        private const long HostMemoryCheckIntervalMs = 1000;
        private const long DeviceShortTrimIntervalMs = 10_000;
        private const long HostMemoryReportIntervalMs = 30_000;

        private long _lastHostMemoryCheck;
        private long _lastDeviceShortTrim;
        private long _lastHostMemoryReport;

        /// <summary>
        /// Called once per frame on the GPU thread. iOS reports memory pressure on transitions only, so the
        /// device's available share is read once a second, the GPU caches are trimmed while it stays short,
        /// and their size is logged every 30 seconds.
        /// </summary>
        public void CheckHostMemory()
        {
            if (!GraphicsConfig.EnableHostMemoryBudgetTracking || !HostMemoryBudget.IsConstrained)
            {
                return;
            }

            long now = Environment.TickCount64;

            if (now - _lastHostMemoryCheck < HostMemoryCheckIntervalMs)
            {
                return;
            }

            _lastHostMemoryCheck = now;

            int device = HostMemoryBudget.DeviceAvailablePercent;

            if (device >= 0 && device <= DeviceShortPercent && now - _lastDeviceShortTrim >= DeviceShortTrimIntervalMs)
            {
                _lastDeviceShortTrim = now;

                TrimCaches(device <= DeviceCriticalPercent ? MemoryPressureLevel.Critical : MemoryPressureLevel.Warning);
            }

            if (now - _lastHostMemoryReport < HostMemoryReportIntervalMs)
            {
                return;
            }

            _lastHostMemoryReport = now;

            ulong textures = 0;
            ulong textureLimit = 0;
            ulong buffers = 0;
            ulong bufferLimit = 0;

            foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
            {
                textures += physicalMemory.TextureCache.CachedBytes;
                textureLimit += physicalMemory.TextureCache.CacheLimit;
                buffers += physicalMemory.BufferCache.CachedBytes;
                bufferLimit += physicalMemory.BufferCache.CacheLimit;
            }

            Logger.Info?.Print(LogClass.Gpu,
                $"Host memory: footprint {HostMemoryBudget.FootprintBytes / TrimMiB} MiB, " +
                $"{HostMemoryBudget.AvailableBytes / TrimMiB} MiB available, device {device}% available; " +
                $"GPU caches: textures {textures / TrimMiB}/{textureLimit / TrimMiB} MiB, " +
                $"buffers {buffers / TrimMiB}/{bufferLimit / TrimMiB} MiB; " +
                $"managed heap {GC.GetGCMemoryInfo().HeapSizeBytes / (long)TrimMiB} MiB");
        }

        /// <summary>
        /// Advances internal sequence number.
        /// This forces the update of any modified GPU resource.
        /// </summary>
''')

    once(switch, '''            if (pressure != MemoryPressureLevel.Normal)
            {
                Gpu.TrimCaches(pressure);
            }
''', '''            if (pressure != MemoryPressureLevel.Normal)
            {
                Gpu.TrimCaches(pressure);
            }

            Gpu.CheckHostMemory();
''')

    once(textures, '''        public ulong Trim(MemoryPressureLevel level)
        {
            return _cache.Trim(level);
        }
''', '''        public ulong Trim(MemoryPressureLevel level)
        {
            return _cache.Trim(level);
        }

        /// <summary>
        /// Bytes the texture cache holds, and its limit.
        /// </summary>
        public ulong CachedBytes => _cache.TotalSize;
        public ulong CacheLimit => _cache.MaxSize;
''')
    once(auto_delete, '''        private ulong _totalSize;
''', '''        private ulong _totalSize;

        public ulong TotalSize => _totalSize;
        public ulong MaxSize => _maxCacheMemoryUsage;
''')
    once(buffers, '''        private ulong _cachedBufferBytes;
''', '''        private ulong _cachedBufferBytes;

        /// <summary>
        /// Bytes the buffer cache holds, and its limit.
        /// </summary>
        public ulong CachedBytes => _cachedBufferBytes;
        public ulong CacheLimit => _maxCachedBufferBytes;
''')
    return [budget, context, switch, textures, auto_delete, buffers]
