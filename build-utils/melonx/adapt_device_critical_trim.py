"""A Critical memory level, or a trim escalated after 30 s of play at 5 % or less, frees the GPU caches for real while only
the device is short: the texture cache gives back what it alone holds (GPU-written data flushed first), the buffer cache
evicts by capacity (Hogwarts Legacy: the only title with host memory budget tracking on).

Evidence (IPA 749 / Core 030cc14f, Hogwarts Legacy, private journals, pid 12613; counts and times only):
- the device sits at 6 % or less on 91 of the 164 performance lines; 9 memory alerts, the last at 05:02:57 with 4 814 MiB of
  footprint, 1 841 MiB of headroom to this process's own limit and the device at 4 %; the session ends at 05:03:06 without a
  close (a system jetsam is probable, not proven); the footprint rose by 327 MiB in its last 30 s;
- the trims visible until 05:01:15 (the end of the stderr capture): 8 calls (7 Warning, 1 Critical at 05:00:39 from the
  dispatch source) with 2 086 to 2 266 MiB of headroom and the device at 4-7 %, releasing 48, 52, 10, 0, 1, 1, 0 and 5 MiB
  (117 MiB); the Critical one released less than 1 MiB; each kept 141 to 210 MiB of textures "in use or holding GPU data".
  Those 8 are the calls that released something (a call releasing 0 bytes logs at Debug): the core journal shows 19 cold
  buffer passes until 05:02:52 (1 775 buffers, 26 MiB), one per periodic trim (every 10 s at 7 % or less), while the buffer
  cache grew from 74 to 184 MiB; at 05:03:00 the texture cache held 155 of 768 MiB;
- cause (GpuContext.cs as prepared for Core 030cc14f): TrimCaches computes freeOnly = deviceShort && available >=
  ComfortableHeadroomBytes without the level, so with more than 768 MiB of headroom a Critical becomes the flush-free trim
  (adapt_device_short_trim: only textures the cache alone holds and without GPU-written data); BufferCache.Trim takes the
  60 s cold branch (adapt_cold_buffer_trim) whenever the headroom is 768 MiB or more, whatever the level.

Change (plan 748 rank 11; GpuContext.cs, AutoDeleteCache.cs, BufferCache.cs):
1. TrimCaches(level, escalated = false): where freeOnly held (the device short with a comfortable headroom), a Critical level
   (an iOS report, or the periodic trim at DeviceCriticalPercent, 3 %, or less) or an escalated trim is no longer freeOnly
   (deviceCritical). Every other case is unchanged: Warning reports and periodic trims stay flush-free, this process's own
   pressure (headroom under 768 MiB, critical under 256 MiB, or unknown) evicts as upstream, an ignored report is ignored.
2. deviceCritical texture trim: GpuContext sets AutoDeleteCache.OnlyUnreferencedTrim (thread-static, GPU thread, cleared in a
   finally) around the cache loop; AutoDeleteCache.Trim then runs TrimUnreferencedTextures with flush: least recently used
   first, the textures the cache alone holds (Texture.HasOneReference) leave, those whose group holds GPU-written data too,
   flushed first exactly as RemoveLeastUsedTexture flushes an evicted texture (dependents synchronised and FlushModified(false)
   when the CPU has not dirtied the memory; the flush is called only when a handle of the group is modified). A texture a
   pool, a bound render target, a view or a lookup still holds is kept and counted (LastTrimKeptBytes), never evicted:
   evicting it would free nothing (upstream's blind RemoveLeastUsedTexture loop is not used here). Targets (Critical: half
   of the cache, Warning: a quarter) and the floor (an eighth of the limit) are unchanged.
3. deviceCritical buffer trim: BufferCache.Trim(level, byCapacity: true) evicts by capacity (EnforceCapacity, the eviction of
   this process's own pressure: least recently used first, CanEvict buffers only, none with GPU-modified ranges) instead of
   by age; targets and floor unchanged.
4. Escalation (CheckHostMemory): the play time of the texture use clock (adapt_texture_play_clock: at most two intervals per
   check) is noted at the first of the once-a-second checks reading the device at 5 % or less; the run lasts while the device
   stays short (7 % or less, the device oscillates between 4 and 7 % in play) and a reading above 7 % or unknown ends it. The periodic trim (every 10 s at 7 % or less, its level unchanged) is escalated once the
   run has lasted 30 s of play, at most once every 30 s (the time is taken when an escalated trim passes TrimCaches' 2 s
   interval). Host reports are never escalated.
5. Reading on the device: the existing trim line ("Host reported <level> memory pressure..., released N MiB of GPU caches")
   ends, for these trims, with "; device short, Critical" or "; device short, escalated after 30 s of play at 5% or less",
   then the MiB of textures kept because something else holds them and the MiB of buffers evicted by capacity, naming the
   adapter. No new line type, no new journal record.
Nothing changes for the guest: an evicted texture is flushed to guest memory as any capacity eviction flushes it, an evicted
buffer holds no GPU-modified range, and both are created again from guest memory on their next use, as after any eviction.
No setting, interval, target, floor or cache limit changes.

Scope: GraphicsConfig.EnableHostMemoryBudgetTracking (the per-title "Track available memory" setting; on for Hogwarts Legacy
in these sessions, off for SSBU, where TrimCaches and CheckHostMemory return at once), on iOS (HostMemoryBudget constrained).
Bound (plan 748, from the logs, not measured): at most about 70 to 78 MiB of textures per Critical trim (half of a 141-155 MiB
cache; the share only the cache holds is unknown), plus 50 to 92 MiB of buffers (half of a 100-184 MiB cache): 1 to 2 % of
8 GiB, 7 to 16 s of respite at the final rate of +327 MiB per 30 s. No effect on survival is shown; no FPS gain is claimed.
Costs: GPU to CPU read-backs for the flushed textures, re-creations (uploads) of evicted textures and buffers used again.
Expected on the device (Hogwarts, device at 5 % or less): trim lines with the "device short, Critical" or "escalated" suffix
releasing more than the flush-free ones around them; lower textureCacheBytes and bufferCacheBytes in the 30 s memoryInventory
records after them; texture flushes and buffer disposals in the 5 s render windows of those trims. The grey haze of the
Hogwarts videos is weakly suspected of purges: check it visually. Never ship with the haze diagnostic Core (same paths).
Not measured on an iPhone.

Runs after every current adapter (GpuContext.cs after adapt_queued_3d_syncpoints, adapt_texture_play_clock,
adapt_host_warning_trim and adapt_device_short_trim; AutoDeleteCache.cs after adapt_short_cache_reuse; BufferCache.cs after
adapt_merged_buffer_order and adapt_cold_buffer_trim); the files are patched as prepared for Core 030cc14f. Rollback: drop
this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
TEXTURES = 'src/Ryujinx.Graphics.Gpu/Image/AutoDeleteCache.cs'
BUFFERS = 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'

BASELINE = {
    CONTEXT: '0f5517eb8d1ae8869dec05dc7177c80ac938b643d564f70fdf81f32822daa34d',  # Core 030cc14f (adapt_queued_3d_syncpoints)
    TEXTURES: '5174d523fcd420db9a8cd50275f4ed7feb94115f5cffff80af08f0f42fcf1caa',  # Core 030cc14f (adapt_short_cache_reuse)
    BUFFERS: 'd594f8371cb2859f83907ff328b8670a3fa351bbe637e73aca2b0323598e9d13',  # Core 030cc14f (adapt_merged_buffer_order)
}

# --- GpuContext.cs: the trim that frees for real while only the device is short; the escalation of the periodic trim ---
SIGNATURE_OLD = '''        /// <param name="level">How much the host wants back</param>
        public void TrimCaches(MemoryPressureLevel level)
        {
'''
SIGNATURE_NEW = '''        /// <param name="level">How much the host wants back</param>
        /// <param name="escalated">RewindBox (adapt_device_critical_trim): the periodic trim after 30 s of play at 5 % or less</param>
        public void TrimCaches(MemoryPressureLevel level, bool escalated = false)
        {
'''

MODE_OLD = '''            bool freeOnly = deviceShort && available >= ComfortableHeadroomBytes;

            ulong evicted = 0;
            ulong kept = 0;

            foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
            {
                evicted += physicalMemory.TextureCache.Trim(level, freeOnly);
                kept += physicalMemory.TextureCache.LastTrimKeptBytes;
                evicted += physicalMemory.BufferCache.Trim(level);
            }
'''
MODE_NEW = '''            bool freeOnly = deviceShort && available >= ComfortableHeadroomBytes;

            // RewindBox (adapt_device_critical_trim): a Critical level (an iOS report, or the device at DeviceCriticalPercent or
            // less) or an escalated trim frees for real while only the device is short. The texture cache evicts the textures
            // it alone holds, those with GPU-written data too (flushed first, as its capacity eviction flushes them), and keeps
            // every texture something else holds; the buffer cache evicts by capacity instead of by age. Targets and floors
            // are unchanged, and so are the other trims.
            bool deviceCritical = freeOnly && (level == MemoryPressureLevel.Critical || escalated);
            freeOnly &= !deviceCritical;

            if (escalated)
            {
                _lastEscalatedTrim = now;
            }

            ulong evicted = 0;
            ulong kept = 0;
            ulong bufferBytes = 0;

            Image.AutoDeleteCache.OnlyUnreferencedTrim = deviceCritical;

            try
            {
                foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
                {
                    evicted += physicalMemory.TextureCache.Trim(level, freeOnly);
                    kept += physicalMemory.TextureCache.LastTrimKeptBytes;
                    ulong buffers = physicalMemory.BufferCache.Trim(level, deviceCritical);
                    evicted += buffers;
                    bufferBytes += buffers;
                }
            }
            finally
            {
                Image.AutoDeleteCache.OnlyUnreferencedTrim = false;
            }
'''

LINE_OLD = '''            string retained = freeOnly ? $"; device short only: kept {kept / TrimMiB} MiB of textures in use or holding GPU data" : string.Empty;
'''
LINE_NEW = '''            string retained = freeOnly ? $"; device short only: kept {kept / TrimMiB} MiB of textures in use or holding GPU data" : string.Empty;

            // RewindBox (adapt_device_critical_trim): the trim that frees for real while only the device is short.
            if (deviceCritical)
            {
                string why = escalated ? $"escalated after {EscalationPlaySeconds} s of play at {DeviceEscalationPercent}% or less" : "Critical";

                retained = $"; device short, {why}: released the textures only this cache held (GPU-written data flushed first), " +
                    $"kept {kept / TrimMiB} MiB of textures held elsewhere; buffers by capacity {bufferBytes / TrimMiB} MiB (adapt_device_critical_trim)";
            }
'''

FIELDS_OLD = '''        // RewindBox (adapt_texture_play_clock): the play time behind TextureUseEpoch, in milliseconds. GPU thread only.
        private long _texturePlayMilliseconds;
'''
FIELDS_NEW = '''        // RewindBox (adapt_texture_play_clock): the play time behind TextureUseEpoch, in milliseconds. GPU thread only.
        private long _texturePlayMilliseconds;
        // RewindBox (adapt_device_critical_trim): the periodic trim is escalated once every check has read the device at
        // DeviceEscalationPercent or less for EscalationPlaySeconds of play, at most once every EscalationIntervalMs. The
        // play time at the first check of that run (-1: no run). GPU thread only.
        private const int DeviceEscalationPercent = 5;
        private const int EscalationPlaySeconds = 30;
        private const long EscalationIntervalMs = 30_000;
        private long _deviceLowSincePlayMs = -1;
        private long _lastEscalatedTrim;
'''

PERIODIC_OLD = '''            int device = HostMemoryBudget.DeviceAvailablePercent;

            if (device >= 0 && device <= DeviceShortPercent && now - _lastDeviceShortTrim >= DeviceShortTrimIntervalMs)
            {
                _lastDeviceShortTrim = now;

                TrimCaches(device <= DeviceCriticalPercent ? MemoryPressureLevel.Critical : MemoryPressureLevel.Warning);
            }
'''
PERIODIC_NEW = '''            int device = HostMemoryBudget.DeviceAvailablePercent;

            // RewindBox (adapt_device_critical_trim): the run of checks, in play time, starts at DeviceEscalationPercent or less
            // and lasts while the device stays short (DeviceShortPercent or less: the device oscillates between 4 and 7 % in
            // play); a reading above it, or an unknown one, ends it.
            if (device >= 0 && device <= DeviceEscalationPercent)
            {
                if (_deviceLowSincePlayMs < 0)
                {
                    _deviceLowSincePlayMs = _texturePlayMilliseconds;
                }
            }
            else if (device < 0 || device > DeviceShortPercent)
            {
                _deviceLowSincePlayMs = -1;
            }

            if (device >= 0 && device <= DeviceShortPercent && now - _lastDeviceShortTrim >= DeviceShortTrimIntervalMs)
            {
                _lastDeviceShortTrim = now;

                // RewindBox (adapt_device_critical_trim): escalated once the run has lasted EscalationPlaySeconds of play, at
                // most once every EscalationIntervalMs (TrimCaches notes the time when an escalated trim runs).
                bool escalated = _deviceLowSincePlayMs >= 0 &&
                    _texturePlayMilliseconds - _deviceLowSincePlayMs >= EscalationPlaySeconds * 1000L &&
                    (_lastEscalatedTrim == 0 || now - _lastEscalatedTrim >= EscalationIntervalMs);

                TrimCaches(device <= DeviceCriticalPercent ? MemoryPressureLevel.Critical : MemoryPressureLevel.Warning, escalated);
            }
'''

# --- AutoDeleteCache.cs: the flag, and the flush-allowed walk of the textures the cache alone holds ---
FLAG_OLD = '''        private bool _protectedOverflowReported;

        private const ulong TrimFloorDivisor = 8;
'''
FLAG_NEW = '''        private bool _protectedOverflowReported;

        private const ulong TrimFloorDivisor = 8;

        /// <summary>
        /// RewindBox (adapt_device_critical_trim): set by GpuContext.TrimCaches on the GPU thread, for one trim, when only the
        /// device is short and the trim frees for real (a Critical level, or an escalated trim). Trim then evicts only the
        /// textures this cache alone holds, those with GPU-written data included (flushed first, as RemoveLeastUsedTexture
        /// flushes them); a texture a pool, a bound render target, a view or a lookup still holds stays.
        /// </summary>
        [ThreadStatic]
        internal static bool OnlyUnreferencedTrim;
'''

TRIM_OLD = '''            if (freeOnly)
            {
                TrimUnreferencedTextures(target);

                return before - _totalSize + retained;
            }
'''
TRIM_NEW = '''            // RewindBox (adapt_device_critical_trim): OnlyUnreferencedTrim walks the same textures as freeOnly, and also evicts
            // those holding GPU-written data, flushed first.
            if (freeOnly || OnlyUnreferencedTrim)
            {
                TrimUnreferencedTextures(target, flush: !freeOnly);

                return before - _totalSize + retained;
            }
'''

WALK_OLD = '''        /// <param name="target">Size to trim the cache down to</param>
        private void TrimUnreferencedTextures(ulong target)
        {
'''
WALK_NEW = '''        /// <param name="target">Size to trim the cache down to</param>
        /// <param name="flush">RewindBox (adapt_device_critical_trim): also evict those holding GPU-written data, flushed first</param>
        private void TrimUnreferencedTextures(ulong target, bool flush = false)
        {
'''

EVICT_OLD = '''                if (texture.HasOneReference() && !texture.Group.AnyHandleModified())
                {
                    // As RemoveLeastUsedTexture: resolve copies other handles deferred from this texture before it
                    // is released (they read its host texture). No flush: no handle holds GPU-written data.
                    if (!texture.CheckModified(false))
                    {
                        texture.Group.SynchronizeDependents(texture);
                    }
'''
EVICT_NEW = '''                if (texture.HasOneReference() && (flush || !texture.Group.AnyHandleModified()))
                {
                    // As RemoveLeastUsedTexture: resolve copies other handles deferred from this texture before it
                    // is released (they read its host texture). No flush: no handle holds GPU-written data.
                    // RewindBox (adapt_device_critical_trim): with flush, GPU-written data is flushed as RemoveLeastUsedTexture
                    // flushes it (untracked, unless the CPU dirtied the memory since).
                    if (!texture.CheckModified(false))
                    {
                        texture.Group.SynchronizeDependents(texture);

                        if (flush && texture.Group.AnyHandleModified())
                        {
                            texture.FlushModified(false);
                        }
                    }
'''

# --- BufferCache.cs: the trim that frees for real evicts by capacity ---
BUFFER_SIGNATURE_OLD = '''        /// <returns>Number of bytes evicted</returns>
        public ulong Trim(MemoryPressureLevel level)
        {
'''
BUFFER_SIGNATURE_NEW = '''        /// <returns>Number of bytes evicted</returns>
        /// <param name="byCapacity">RewindBox (adapt_device_critical_trim): evict by capacity whatever the headroom (a Critical level or
        /// an escalated trim while only the device is short)</param>
        public ulong Trim(MemoryPressureLevel level, bool byCapacity = false)
        {
'''

BUFFER_BRANCH_OLD = '''            if (HostMemoryBudget.AvailableBytes >= DeviceShortOnlyHeadroomBytes)
            {
                EvictCold(target);
            }
'''
BUFFER_BRANCH_NEW = '''            // RewindBox (adapt_device_critical_trim): a trim that frees for real evicts by capacity, as this process's own pressure.
            if (!byCapacity && HostMemoryBudget.AvailableBytes >= DeviceShortOnlyHeadroomBytes)
            {
                EvictCold(target);
            }
'''

EDITS = {
    CONTEXT: ((SIGNATURE_OLD, SIGNATURE_NEW), (MODE_OLD, MODE_NEW), (LINE_OLD, LINE_NEW), (FIELDS_OLD, FIELDS_NEW),
              (PERIODIC_OLD, PERIODIC_NEW)),
    TEXTURES: ((FLAG_OLD, FLAG_NEW), (TRIM_OLD, TRIM_NEW), (WALK_OLD, WALK_NEW), (EVICT_OLD, EVICT_NEW)),
    BUFFERS: ((BUFFER_SIGNATURE_OLD, BUFFER_SIGNATURE_NEW), (BUFFER_BRANCH_OLD, BUFFER_BRANCH_NEW)),
}


def apply(source):
    paths = {name: source / name for name in EDITS}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in EDITS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
