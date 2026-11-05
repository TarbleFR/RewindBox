"""Give the large object heap's free space back to iOS at two moments where nothing is playing: once after the first
presented frame of a session, and during a host pause that lasts while the device is short of memory.

Build 658, 5 November 2026, first player (private logs, not in the repository), Hogwarts Legacy, pid 11152 (session
03:10:01-03:21:03 UTC): the gcEvent journal shows a large object heap (LOH) of 532 MB at 03:10:08 and 03:10:13 (first
frame) with 254-261 MB of it free, 508-545 MB for the rest of the session with 177-264 MB free, and 282 MiB still live
after the close. Device RAM is 8-12 % available from 03:11:04 on (one memoryWarning at 03:20:04). The only collection
that gave memory back was the in-play blocking gen2 that compacted the small object heap at about 03:20:13: footprint
4541 -> 4404 MiB (-137) in one second, at the cost of a 332 ms freeze in play. The LOH was swept, never compacted.

Mechanism (read in the Core 658 preparation and dotnet/runtime v10.0.0, which iOS NativeAOT builds without regions):
- Ryujinx.Library.csproj sets ConserveMemory=5 and HighMemoryPercent=99 (adapt_gc). The GC compacts the LOH only on a
  request (GCSettings.LargeObjectHeapCompactionMode) or above 50 % gen2+LOH fragmentation; this session stayed at
  13-20 %. A swept free block stays committed and touched: gc.cpp reset_memory gives a free block over 128 KiB back
  (madvise) only when dt_high_memory_load_p(), i.e. a memory load at or above the 99 % threshold (88-92 % here).
- The only CompactOnce requests in the Core are ARMeilleure's PTC (Ptc.PreSave, MakeAndSaveTranslations). With the
  HostMappedUnsafe memory manager on an ARM64 host the CPU engine is LightningJit (ArmProcessContextFactory), whose
  LoadDiskCache returns a DummyDiskCacheLoadState: PTC never runs, so nothing ever asks for a LOH compaction.
- In the segments GC a compacting gen2 slides the live LOH objects down and decommits the end of the segments
  (executed on linux-x64 with the segments GC library libclrgc.so: a 527 MiB LOH with 222 MiB free, swept: RSS 560
  MiB; after CompactOnce: LOH 305 MiB, RSS 339 MiB, 66 ms).

Change (every title; nothing in rendering, emulation or the GC configuration):
- EmbeddedHeapCompaction (Ryujinx.Library, EmbeddedMemory.cs): one blocking collection that compacts the small object
  heap and, once (CompactOnce), the LOH; one durable journal line "memory heapCompacted" with the reason, the footprint,
  committed bytes, LOH and gen2 size and free space before (as of the last collection) and after, and the pause. Only
  when HostMemoryBudget.IsConstrained (iOS) and when the free space of gen2 plus the LOH at the last collection is at
  least 64 MiB. Never two at once (a busy gate skips the second).
- After the first presented frame of each session (WindowBase render loop, where _ranFirstFrame is set): the boot
  peak of the LOH is reached (532 MB at 03:10:08 in pid 11152) and the game shows its boot logo, not play.
- Host pause (the Library's pause control, after TogglePauseEmulation and SetEmbeddedPaused): when the same pause is
  still in force 3 s later, no close has begun, the device has 15 % or less available, and the last compaction was at
  least 60 s ago, a background thread runs it. The pause control only starts the thread. A resume during the
  collection waits for it in managed code (one collection, about 0.1-0.4 s).
No collection is forced during play: one per session at the first frame, then only in a held pause.
Not measured on an iPhone. Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Library/EmbeddedMemory.cs': 'fb58520f5581c579a6ca1e79a0bb91bf9d5df51caaa8cee108a2788b543c8150',
    'src/Ryujinx.Library/Library.cs': '2e2f8f2345af25333c579492017b4d12c03d3e61b054ae27ec0200bdd888ca2c',
    'src/Ryujinx.Library/Window/WindowBase.cs': 'f604579092e398ef90574c62a47845e51a336602c2bf9febb9c4a2d24a7e188f',
}

# The class the test fixture compiles as is (between the two markers).
COMPACTION_CLASS = '''// RewindBox (adapt_safe_point_compaction) begin
// The large object heap keeps the free space of its boot peak committed and touched for the whole session (the GC
// compacts it only on request, and the only requester, ARMeilleure's PTC, does not run with LightningJit); a compacting
// collection gives it back. It is run only where nothing plays: after the first presented frame of a session, and in a
// host pause held while the device is short of memory.
internal static class EmbeddedHeapCompaction
{
    internal const long MiB = 1024 * 1024;
    internal const long MinimumReclaimableBytes = 64 * MiB;
    internal const int PauseDeviceShortPercent = 15;
    internal const int PauseDelayMs = 3000;
    internal const long PauseIntervalMs = 60_000;

    private static readonly object _gate = new();
    private static int _pauseGeneration;
    private static long _lastCompaction;

    internal static int Compactions;

    // Free space of gen2 and the LOH at the last collection (every collection reports every generation).
    internal static long ReclaimableBytes(System.GCMemoryInfo info)
    {
        System.ReadOnlySpan<System.GCGenerationInfo> generations = info.GenerationInfo;
        return generations.Length > 3 ? generations[2].FragmentationAfterBytes + generations[3].FragmentationAfterBytes : 0;
    }

    internal static bool ShouldCompactAfterFirstFrame(long reclaimable) => reclaimable >= MinimumReclaimableBytes;

    internal static bool ShouldCompactInPause(long reclaimable, int devicePercent, long sinceLastMs) =>
        reclaimable >= MinimumReclaimableBytes && devicePercent >= 0 && devicePercent <= PauseDeviceShortPercent &&
        sinceLastMs >= PauseIntervalMs;

    // Render loop, once per session, right after the first frame was presented.
    internal static void AfterFirstFrame()
    {
        try
        {
            if (Ryujinx.Memory.HostMemoryBudget.IsConstrained &&
                ShouldCompactAfterFirstFrame(ReclaimableBytes(System.GC.GetGCMemoryInfo())))
            {
                Compact("firstFrame");
            }
        }
        catch (System.Exception error)
        {
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "heapCompactionFailed", detail: "firstFrame: " + error.GetType().Name);
        }
    }

    // The Library's pause control (under the session coordinator's lock: it only starts a thread).
    internal static void OnHostPause(bool paused, System.Func<bool> stopping)
    {
        int generation = System.Threading.Interlocked.Increment(ref _pauseGeneration);

        if (!paused || !Ryujinx.Memory.HostMemoryBudget.IsConstrained)
        {
            return;
        }

        System.Threading.Thread worker = new(() =>
        {
            try
            {
                System.Threading.Thread.Sleep(PauseDelayMs);

                if (System.Threading.Volatile.Read(ref _pauseGeneration) != generation || stopping())
                {
                    return;
                }

                long last = System.Threading.Interlocked.Read(ref _lastCompaction);
                long since = last == 0 ? long.MaxValue : System.Environment.TickCount64 - last;

                if (ShouldCompactInPause(ReclaimableBytes(System.GC.GetGCMemoryInfo()),
                        Ryujinx.Memory.HostMemoryBudget.DeviceAvailablePercent, since))
                {
                    Compact("hostPause");
                }
            }
            catch (System.Exception error)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "heapCompactionFailed", detail: "hostPause: " + error.GetType().Name);
            }
        })
        {
            IsBackground = true,
            Name = "HeapCompaction.Pause",
        };

        worker.Start();
    }

    private static void Compact(string reason)
    {
        if (!System.Threading.Monitor.TryEnter(_gate))
        {
            return;
        }

        try
        {
            System.GCMemoryInfo before = System.GC.GetGCMemoryInfo();
            long footprintBefore = (long)Ryujinx.Memory.HostMemoryBudget.FootprintBytes;
            long start = System.Diagnostics.Stopwatch.GetTimestamp();

            System.Runtime.GCSettings.LargeObjectHeapCompactionMode = System.Runtime.GCLargeObjectHeapCompactionMode.CompactOnce;
            System.GC.Collect(2, System.GCCollectionMode.Forced, blocking: true, compacting: true);

            long elapsedMs = (System.Diagnostics.Stopwatch.GetTimestamp() - start) * 1000 / System.Diagnostics.Stopwatch.Frequency;
            System.GCMemoryInfo after = System.GC.GetGCMemoryInfo(System.GCKind.FullBlocking);
            long footprintAfter = (long)Ryujinx.Memory.HostMemoryBudget.FootprintBytes;

            System.Threading.Interlocked.Exchange(ref _lastCompaction, System.Environment.TickCount64);
            System.Threading.Interlocked.Increment(ref Compactions);

            System.GCGenerationInfo lohBefore = before.GenerationInfo[3], lohAfter = after.GenerationInfo[3];
            System.GCGenerationInfo gen2Before = before.GenerationInfo[2], gen2After = after.GenerationInfo[2];

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "heapCompacted", detail:
                $"{reason}: footprint {footprintBefore / MiB} -> {footprintAfter / MiB} MiB; " +
                $"committed {before.TotalCommittedBytes / MiB} -> {after.TotalCommittedBytes / MiB} MiB; " +
                $"LOH {lohBefore.SizeAfterBytes / MiB} MiB ({lohBefore.FragmentationAfterBytes / MiB} free) -> " +
                $"{lohAfter.SizeAfterBytes / MiB} MiB ({lohAfter.FragmentationAfterBytes / MiB} free); " +
                $"gen2 {gen2Before.SizeAfterBytes / MiB} MiB ({gen2Before.FragmentationAfterBytes / MiB} free) -> " +
                $"{gen2After.SizeAfterBytes / MiB} MiB ({gen2After.FragmentationAfterBytes / MiB} free); " +
                $"pause {after.PauseDurations[0].TotalMilliseconds:F1} ms, {elapsedMs} ms in all; " +
                $"device {Ryujinx.Memory.HostMemoryBudget.DeviceAvailablePercent}% available (adapt_safe_point_compaction)");
        }
        finally
        {
            System.Threading.Monitor.Exit(_gate);
        }
    }
}
// RewindBox (adapt_safe_point_compaction) end
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths['src/Ryujinx.Library/EmbeddedMemory.cs'], '''        catch { return 3; }
    }
}
''', '''        catch { return 3; }
    }
}

''' + COMPACTION_CLASS)

    once(paths['src/Ryujinx.Library/Library.cs'], '''                    _emulationContext.System.TogglePauseEmulation(paused);
                    _window.SetEmbeddedPaused(paused);
                });''', '''                    _emulationContext.System.TogglePauseEmulation(paused);
                    _window.SetEmbeddedPaused(paused);
                    // RewindBox (adapt_safe_point_compaction): a pause held 3 s while the device is short compacts the heap.
                    EmbeddedHeapCompaction.OnHostPause(paused, () => EmbeddedSessions.IsStopping);
                });''')

    once(paths['src/Ryujinx.Library/Window/WindowBase.cs'], '''                        if (!_ranFirstFrame)
                        {\x20
                            _ranFirstFrame = true;
                            SendStatistics(false);
                         }''', '''                        if (!_ranFirstFrame)
                        {\x20
                            _ranFirstFrame = true;
                            SendStatistics(false);
                            // RewindBox (adapt_safe_point_compaction): the boot peak of the large object heap is reached
                            // and the game shows its boot logo; give its free space back once, before play.
                            EmbeddedHeapCompaction.AfterFirstFrame();
                         }''')
    return list(paths.values())
