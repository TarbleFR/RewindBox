"""The background GC thread is kept alive during a session, so a gen2 never falls back to a blocking one (Core 693).

IPA 690 (Hogwarts Legacy, pid 32980) and IPA 691 (pid 34380, Core 691), private Core journals: every in-play blocking
gen2 is flagged fellBackFromBackground (EmbeddedPerformanceDiagnostics, test/melonx_gc_fallback_test.py): 148 and
557 ms in 690, 151, 439 and 718 ms in 691, each one more than 20 s after the previous background gen2 (36, 56 and
44 s in 691); background gen2s that followed a shorter gap all ran concurrently. Mechanism (.NET 10.0.0 gc.cpp,
docs/melonx-bgc-fallback-2026-11-05.md): a workstation BGC thread exits after waiting 20000 ms for work, and the next
background gen2 recreates it; NativeAOT's CreateThread returns before the new thread sets bgc_thread, and
`do_concurrent_p = (!!bgc_thread && ...)` then runs that gen2 blocking and compacting. The upstream fix
(dotnet/runtime#119383) is in no 10.0.x package, and the spliced rebuilt GC of Core 659-661 was withdrawn in Core 663.

Change, official runtime, managed only (class BackgroundGcKeepAlive appended to src/Ryujinx.Library/EmbeddedSession.cs,
started after and stopped before the session's EmbeddedPerformanceDiagnostics epoch):
- a background thread (below-normal priority) polls GC.GetGCMemoryInfo(GCKind.Background).Index every 250 ms; the
  index changes when a background gen2 starts and when one falls back (the runtime stamps the background record
  then), so its change marks a moment after which the BGC thread exists and waits at most 20 s;
- 12 to 16 s after the last such change, when the managed heap of the last collection is at least 384 MiB, it asks
  for a background gen2: GC.Collect(2, Forced, blocking: false, compacting: false). The thread is alive then, so the
  collection runs concurrently (while one already runs, the runtime returns at once) and the thread's 20 s wait
  starts again;
- it never asks once 16 s have passed (the thread may be leaving: asking could start the race itself), never before
  the session's first background gen2 (no thread yet), and never for a smaller heap (titles that collect rarely keep
  the runtime's own schedule).
Cost: about one background mark every 13 s for a large heap (IPA 691: about 0.8-1.0 s of .NET_BGC CPU per background
gen2, a concurrent thread). Journal: one gcKeepAlive line at the first request and a summary at the session end
(requests, windows missed, small-heap skips). Not measured on an iPhone. Fail closed on drift: the file must be the
Core 691 preparation's.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {
    SESSION: '5b882aff47f53242bb25c2c8fd1906163db92231a460105e79ffd55a2b93fdba',
}

# The class is appended to EmbeddedSession.cs (file-scoped namespace Ryujinx.Library), so the adapter is a set of exact
# replacements the gates can reverse, in a file only one gate observes (performance-diagnostics, which applies the
# adapters in preparation order).
TAIL_OLD = '''            UseHypervisor = false, EnableInternetAccess = false,
        }, path));
    }
}
'''
KEEPALIVE_SOURCE = '''
// RewindBox (adapt_bgc_keepalive): keeps the workstation background GC thread from leaving after its 20 s idle wait,
// so a later background gen2 does not hit the .NET 10.0.0 thread start race and run blocking. Official runtime only.
public static class BackgroundGcKeepAlive
{
    public const long WindowStartMs = 12_000;
    public const long WindowEndMs = 16_000;
    public const long MinimumHeapBytes = 384L * 1024 * 1024;
    public const int PollMs = 250;

    public enum Decision { NotSeen, Wait, Induce, Missed, SmallHeap }

    // msSinceBackground: time since the background record last changed (a background gen2 started or fell back), or
    // -1 before the session's first one. heapBytes: the managed heap of the last collection.
    public static Decision Decide(long msSinceBackground, long heapBytes)
    {
        if (msSinceBackground < 0) return Decision.NotSeen;
        if (msSinceBackground < WindowStartMs) return Decision.Wait;
        if (msSinceBackground > WindowEndMs) return Decision.Missed;
        if (heapBytes < MinimumHeapBytes) return Decision.SmallHeap;
        return Decision.Induce;
    }

    private sealed class Run
    {
        public readonly long Generation;
        public int Stop;
        public long Requests, Missed, SmallHeap, Changes;
        public Run(long generation) => Generation = generation;
    }

    private static Run _current;

    // Test seams (the host gate drives them); production uses the runtime.
    internal static Func<long> ReadBackgroundIndex = static () => GC.GetGCMemoryInfo(GCKind.Background).Index;
    internal static Func<long> ReadHeapBytes = static () => GC.GetGCMemoryInfo().HeapSizeBytes;
    internal static Action RequestBackgroundCollection =
        static () => GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
    internal static Func<long> ReadMilliseconds = static () => Environment.TickCount64;

    public static long Requests => System.Threading.Volatile.Read(ref _current)?.Requests ?? 0;

    public static void Start(long generation)
    {
        try
        {
            Run run = new(generation);
            Run previous = System.Threading.Interlocked.Exchange(ref _current, run);
            if (previous != null) System.Threading.Volatile.Write(ref previous.Stop, 1);
            System.Threading.Thread thread = new(() => Loop(run))
            {
                IsBackground = true,
                Name = "RewindBox.GcKeepAlive",
                Priority = System.Threading.ThreadPriority.BelowNormal,
            };
            thread.Start();
        }
        catch { } // A missing keep-alive leaves the runtime's own schedule.
    }

    public static void Stop(long generation)
    {
        Run run = System.Threading.Volatile.Read(ref _current);
        if (run == null || run.Generation != generation) return;
        System.Threading.Volatile.Write(ref run.Stop, 1);
        System.Threading.Interlocked.CompareExchange(ref _current, null, run);
        try
        {
            EmbeddedLaunchDiagnostics.Record("gcKeepAlive", "summary", detail:
                $"background gen2 requests {run.Requests}, windows missed {run.Missed}, small-heap skips {run.SmallHeap}, " +
                $"background records seen {run.Changes} (adapt_bgc_keepalive)");
        }
        catch { }
    }

    private static void Loop(Run run)
    {
        try
        {
            long lastIndex = ReadBackgroundIndex();
            long lastChange = -1;
            bool counted = false;

            while (System.Threading.Volatile.Read(ref run.Stop) == 0)
            {
                System.Threading.Thread.Sleep(PollMs);
                long now = ReadMilliseconds();
                long index = ReadBackgroundIndex();

                if (index != lastIndex)
                {
                    lastIndex = index;
                    lastChange = now;
                    counted = false;
                    run.Changes++;
                    continue;
                }

                switch (Decide(lastChange < 0 ? -1 : now - lastChange, ReadHeapBytes()))
                {
                    case Decision.Induce:
                        RequestBackgroundCollection();
                        // The next attempt waits a whole window again unless the record changes first.
                        lastChange = now;
                        if (++run.Requests == 1)
                        {
                            EmbeddedLaunchDiagnostics.Record("gcKeepAlive", "started", detail:
                                "background gen2 requested 12-16 s after the previous one (adapt_bgc_keepalive)");
                        }
                        break;
                    case Decision.Missed:
                        if (!counted) { run.Missed++; counted = true; }
                        break;
                    case Decision.SmallHeap:
                        if (!counted) { run.SmallHeap++; counted = true; }
                        break;
                }
            }
        }
        catch { } // Never change the emulator's result.
    }
}
'''
TAIL_NEW = TAIL_OLD + KEEPALIVE_SOURCE

START_OLD = '''                EmbeddedPerformanceDiagnostics.Start(generation);
'''
START_NEW = '''                EmbeddedPerformanceDiagnostics.Start(generation);
                BackgroundGcKeepAlive.Start(generation); // RewindBox (adapt_bgc_keepalive)
'''
STOP_OLD = '''                    EmbeddedPerformanceDiagnostics.Stop(generation);
'''
STOP_NEW = '''                    BackgroundGcKeepAlive.Stop(generation); // RewindBox (adapt_bgc_keepalive)
                    EmbeddedPerformanceDiagnostics.Stop(generation);
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[SESSION], START_OLD, START_NEW)
    once(paths[SESSION], STOP_OLD, STOP_NEW)
    once(paths[SESSION], TAIL_OLD, TAIL_NEW)
    return list(paths.values())
