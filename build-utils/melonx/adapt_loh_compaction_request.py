"""Memory (every title): at a host memory pressure report, ask the collector to compact the large object heap at its own
next blocking collection, when that heap holds at least 256 MiB of free space and the device is short.

IPA 767 journals (private, counts only; docs/melonx-ipa767-journals-2026-11-17.md):
- Super Smash Bros. Ultimate (pid 32759): the large object heap (LOH) holds 735 MiB, about 490 MiB of it free after each
  collection, for the last eight minutes of a twelve-minute session. The collector ran one blocking compacting gen2 of
  its own (09:42:35, 675 ms pause): the small object heap was compacted, the LOH was not (free 145 MiB before, 497 MiB
  after). Every gen2 after it was a background one (sweeps, no compaction). The device was at 4 to 9 % available; the
  remaining long gaps of the session are the GPU thread decompressing memory iOS had compressed (34 967 decompressions in
  the 650 ms gap of that collection).
- Hogwarts Legacy (pid 32106): LOH 444 MiB, 152 to 174 MiB free after the background collections of the courtyard; the
  engine's own compactions (adapt_safe_point_compaction, adapt_stall_compaction) compact it in loading gaps.
Read in the Core: the collector compacts the LOH only when GCSettings.LargeObjectHeapCompactionMode is CompactOnce
(adapt_safe_point_compaction's docstring: ConserveMemory 5 compacts the LOH past 50 % gen2+LOH fragmentation, which the
SSBU collection was past, and it still was not compacted), and a swept free block of the LOH stays committed and touched
below the 99 % high memory load (adapt_gc). The only requests are the engine's own compactions (EmbeddedHeapCompaction,
in loading gaps and held pauses) and ARMeilleure's PTC, which does not run with LightningJit.

Change (Switch.cs only): when the host reports memory pressure (the Warning or Critical report already consumed by
ProcessFrame for Gpu.TrimCaches), if the last collection left at least 256 MiB free in the LOH, the device has 15 % or
less available, no request is pending and no request was made since that collection, the mode is set to CompactOnce.
No collection is started: the request is consumed by the next blocking gen2 the collector itself decides (or by an
engine compaction, which sets the same mode); background collections leave it pending. One log line per request.
Cost: that collection also copies the live large objects (SSBU: about 240 MiB) and its pause is longer by that copy.
Not changed: the GC configuration (ConserveMemory, HighMemoryPercent), when collections run, the engine's compactions,
the cache trims. Not measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed
on drift.
"""
import hashlib
from adapt_session import once

SWITCH = 'src/Ryujinx.HLE/Switch.cs'
# The preparation of Core 58319c2c (IPA 766/767).
BASELINE = {SWITCH: 'fd2b4def30274349c6a9109133f329927752650ca32d058adb3c03bbbbb474ac'}

TRIM_OLD = '''            if (pressure != MemoryPressureLevel.Normal)
            {
                Gpu.TrimCaches(pressure);
            }
'''
TRIM_NEW = '''            if (pressure != MemoryPressureLevel.Normal)
            {
                Gpu.TrimCaches(pressure);
                // RewindBox (adapt_loh_compaction_request): the collector's next blocking collection also compacts the
                // large object heap when its free space is large and the device is short; no collection is started.
                if (LargeObjectHeapRequest.OnHostPressure(HostMemoryBudget.IsConstrained, HostMemoryBudget.DeviceAvailablePercent))
                {
                    Logger.Info?.Print(LogClass.Emulation, "Large object heap: compaction requested for the collector's next blocking " +
                        $"collection ({LargeObjectHeapRequest.LastFreeBytes >> 20} MiB free after collection {LargeObjectHeapRequest.LastIndex}, " +
                        $"device {LargeObjectHeapRequest.LastDevicePercent} % available, request {LargeObjectHeapRequest.Requests}) " +
                        "(adapt_loh_compaction_request).");
                }
            }
'''

END_OLD = '''                TitleIDs.CurrentApplication.Value = null;
                Shared = null;
            }
        }
    }
}
'''
END_NEW = '''                TitleIDs.CurrentApplication.Value = null;
                Shared = null;
            }
        }
    }

    // RewindBox (adapt_loh_compaction_request) begin
    // A request that the collector compact the large object heap at its next blocking collection (CompactOnce), made at a
    // host memory pressure report. The heap's free space after a sweep stays committed and touched; only a compacting
    // collection with this mode gives it back, and the collector itself never sets the mode.
    internal static class LargeObjectHeapRequest
    {
        internal const long MinimumFreeBytes = 256L * 1024 * 1024;
        internal const int DeviceShortPercent = 15;

        private static long _requestedAfterIndex = -1;

        internal static int Requests;
        internal static long LastFreeBytes;
        internal static long LastIndex;
        internal static int LastDevicePercent;

        internal static bool ShouldRequest(long lohFreeBytes, int devicePercent, long lastIndex, long requestedAfterIndex, bool pending) =>
            !pending && lohFreeBytes >= MinimumFreeBytes && devicePercent >= 0 && devicePercent <= DeviceShortPercent &&
            lastIndex > 0 && lastIndex != requestedAfterIndex;

        // On the GPU thread (Switch.ProcessFrame), only when the host reported pressure. True when the mode was set.
        internal static bool OnHostPressure(bool constrained, int devicePercent)
        {
            try
            {
                if (!constrained)
                {
                    return false;
                }

                System.GCMemoryInfo info = System.GC.GetGCMemoryInfo();
                System.ReadOnlySpan<System.GCGenerationInfo> generations = info.GenerationInfo;
                long free = generations.Length > 3 ? generations[3].FragmentationAfterBytes : 0;
                bool pending = System.Runtime.GCSettings.LargeObjectHeapCompactionMode == System.Runtime.GCLargeObjectHeapCompactionMode.CompactOnce;

                if (!ShouldRequest(free, devicePercent, info.Index, System.Threading.Volatile.Read(ref _requestedAfterIndex), pending))
                {
                    return false;
                }

                System.Runtime.GCSettings.LargeObjectHeapCompactionMode = System.Runtime.GCLargeObjectHeapCompactionMode.CompactOnce;
                System.Threading.Volatile.Write(ref _requestedAfterIndex, info.Index);
                LastFreeBytes = free;
                LastIndex = info.Index;
                LastDevicePercent = devicePercent;
                System.Threading.Interlocked.Increment(ref Requests);

                return true;
            }
            catch (System.Exception)
            {
                return false;
            }
        }
    }
    // RewindBox (adapt_loh_compaction_request) end
}
'''

PAIRS = [
    (SWITCH, TRIM_OLD, TRIM_NEW),
    (SWITCH, END_OLD, END_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
