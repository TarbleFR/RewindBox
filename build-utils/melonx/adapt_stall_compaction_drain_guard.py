"""No presentation-gap compaction while the render thread is held in one drain of its queue (plan 748, rank 7).

Evidence (IPA 748-751 / Core 030cc14f, Super Smash Bros. Ultimate, private journals; counts and times only):
- Both SSBU sessions with a core journal (pids 12550 and 14991) ran one adapt_stall_compaction compaction ("presentationGap")
  in play, inside their longest compile freeze: rule fired at a gap of 786 and 916 ms, pause 345.2 and 346.4 ms, footprint
  4 819 -> 4 074 and 4 887 -> 4 093 MiB, freezes of 1 767 and 1 750 ms in all (the compaction from about +0.79 to +1.13 s
  and +0.92 to +1.26 s into them; the rest is the pipeline wait). No other gap of those sessions held one.
- In those 5 s windows the render thread spent 2 925 and 2 152 ms in "pipelines" (SSBU runs asyncShaders=False: a draw
  waits for its pipeline with no timeout inside its command). In 12550 renderDrain was in flight for 712 ms at the sample
  of 04:43:32.66, about 0.8 s at the rule's poll; for 14991 the state at the poll is not observed (the samples around it
  show renderIdle). The 14991 compaction is audible: 211 ms of audio silence in that gap.
- The stall compaction of Hogwarts Legacy 12613 (05:00:01.2, 158 ms, a loading) had renderIdle in flight for 898 ms.
Cause: the rule "no frame for 700 ms" (StallGapMs) does not tell a loading screen, where the render thread waits for
work (renderIdle), from a render thread held inside one command (renderDrain); the blocking collection stops every
managed step of the compile-then-draw path for its pause.

Change (every title; EmbeddedPerformanceDiagnostics.cs, EmbeddedMemory.cs after adapt_stall_compaction):
- EmbeddedPerformanceDiagnostics.RenderDrainInFlightMs(): the age in ms of the Phase.RenderDrain scope in flight in the
  current epoch, -1 when none is or no session measures. Volatile reads of the epoch, its Active and FirstStarts slots
  (the values the samples' "active" field already reads); no lock, nothing written. Only the render loop opens that
  scope, one at a time, so the first registered start is that drain's start.
- EmbeddedHeapCompaction: when the stall rule holds (after ShouldCompactInStall, before the stop request), the poll
  compacts nothing if that age is StallGapMs / 2 (350 ms) or more; the same test inside the compaction's gate, in the
  presentStamp branch, right before collecting. A loading screen (render thread idle) or a drain younger than 350 ms
  keeps the compaction, as before; with no performance epoch the age is -1 and nothing changes. The first-frame and
  host-pause compactions are unchanged. A refusal is counted once per gap (the gap's presentation stamp), with the
  longest drain seen at a refusal; both start from zero with the session, as StallCompactions.
- The existing journal line (memory, heapCompacted) of every compaction ends with "renderDrain in flight <ms> ms;
  stall compactions refused for a drain <n> (longest <ms> ms)": the age read right before that collection and the
  session's refusals so far. No new line type.
Guest-visible behaviour unchanged: only whether a blocking compaction of the managed heap runs in such a gap.

Bound (from the logs, not measured): at most the 345-346 ms pause per occurrence, one occurrence in each of the 2 SSBU
sessions covered (2 of 2); the part actually added to those freezes is not separable from the pipeline wait. 14991 is
covered only if its render thread was in a drain at the poll (not observed). No FPS, heat or stability gain claimed.
Risk: the 745-794 MiB those compactions gave back stay committed until a later gap, a host pause or the end. The SSBU
part of session 11238 ran 784 s with no in-play compaction possible: footprint up to 5 053 MiB, 10 % or less available
for 498 s, one memory warning at 8 %, no jetsam. SSBU runs with hostMemoryBudget=False: no trim takes over.

Expected on the device (same SSBU route): no "presentationGap" heapCompacted line inside a compile freeze whose render
thread is in one drain for 350 ms or more; the next heapCompacted line of the session (any reason) reads "stall
compactions refused for a drain N (longest M ms)" with N at least 1 and M at least 350; loading-screen compactions keep
coming with "renderDrain in flight -1 ms" (or under 350). Refuted if a compile freeze still holds a presentationGap
compaction with renderDrain at 350 ms or more, or if Hogwarts loses its loading compactions.
Rollback: drop this adapter from prepare_embedded.py, ORDER and dma-core-plan.json (and its gate extensions). Not
measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

MEMORY = 'src/Ryujinx.Library/EmbeddedMemory.cs'
DIAGNOSTICS = 'src/Ryujinx.Common/EmbeddedPerformanceDiagnostics.cs'
# Core 030cc14f's preparation (prep767): EmbeddedMemory.cs after adapt_stall_compaction, the collector after
# adapt_bindless_array_deltas (no adapter of ORDER edits it before this one).
BASELINE = {
    MEMORY: '68ab9c935ded9fa449e6110dd4b822c05a9f2a75e9e6d712ea88cdba3b9c3e25',
    DIAGNOSTICS: 'cb4d8df1db93dfb663c2c384a73fa77416ba5de0afcfcd972c28890084b65882',
}

ACCESSOR_OLD = '''    public static Scope Measure(Phase phase) => Scope.Create(phase);
'''
ACCESSOR_NEW = ACCESSOR_OLD + '''
    // RewindBox (adapt_stall_compaction_drain_guard): how long the render thread's drain of its command queue
    // (Phase.RenderDrain) has been in flight in the current session, in milliseconds; -1 when none is (the render thread
    // waits for work or is between two drains) or no session measures. Only the render loop opens this scope, one at a
    // time, so the first registered start is that drain's start (the samples' "active" field reads the same values).
    // Volatile reads only: no lock, nothing written.
    public static long RenderDrainInFlightMs()
    {
        Epoch epoch = Volatile.Read(ref _current);
        if (epoch == null || Volatile.Read(ref epoch.Active[(int)Phase.RenderDrain]) == 0) return -1;
        long first = Volatile.Read(ref epoch.FirstStarts[(int)Phase.RenderDrain]);
        return first == 0 ? -1 : Math.Max(0, (Stopwatch.GetTimestamp() - first) * 1000 / Stopwatch.Frequency);
    }
'''

FIRST_FRAME_OLD = '''            System.Threading.Volatile.Write(ref _stallCompactions, 0);
            System.Threading.Volatile.Write(ref _firstPresent, now == 0 ? 1 : now);
'''
FIRST_FRAME_NEW = '''            System.Threading.Volatile.Write(ref _stallCompactions, 0);
            ClearDrainRefusals(); // RewindBox (adapt_stall_compaction_drain_guard)
            System.Threading.Volatile.Write(ref _firstPresent, now == 0 ? 1 : now);
'''

WATCH_OLD = '''        System.Threading.Volatile.Write(ref _stallCompactions, 0);
        System.Threading.Volatile.Write(ref _hostPaused, false);
    }
'''
WATCH_NEW = '''        System.Threading.Volatile.Write(ref _stallCompactions, 0);
        ClearDrainRefusals(); // RewindBox (adapt_stall_compaction_drain_guard)
        System.Threading.Volatile.Write(ref _hostPaused, false);
    }
'''

POLL_OLD = '''            System.Func<bool> stopping = System.Threading.Volatile.Read(ref _stopping);
'''
POLL_NEW = '''            // RewindBox (adapt_stall_compaction_drain_guard): the rule holds, but the render thread has been in one drain
            // for half the gap or more (held inside a command: a compile freeze, not a loading): refused.
            if (DrainHolds(stamp))
            {
                return;
            }

''' + POLL_OLD

GUARD_OLD = '''    // RewindBox (adapt_stall_compaction) end
'''
GUARD_NEW = GUARD_OLD + '''
    // RewindBox (adapt_stall_compaction_drain_guard) begin
    // IPA 748-751 SSBU: a compile freeze (the render thread held in one drain by a pipeline wait) is a presentation gap
    // too, and the compaction run in it added its 345-346 ms pause to it. The render thread in one drain for half the
    // gap or more waits inside a command, the game is not loading: no compaction. A loading screen, where the render
    // thread waits for work (renderIdle), keeps it; so does a session without a performance epoch (age -1).
    internal const int StallDrainMs = StallGapMs / 2;

    private static int _drainRefusals; // gaps of the session in which a compaction was refused for a drain
    private static long _drainRefusedStamp; // the presentation stamp of the last such gap
    private static long _drainRefusedLongestMs; // the longest drain seen at a refusal

    internal static int DrainRefusals => System.Threading.Volatile.Read(ref _drainRefusals);
    internal static long DrainRefusedLongestMs => System.Threading.Volatile.Read(ref _drainRefusedLongestMs);

    // On the poll's thread only: past the stall rule, and in the gate right before collecting. A refusal is counted
    // once per gap.
    private static bool DrainHolds(long presentStamp)
    {
        long drain = Ryujinx.Common.EmbeddedPerformanceDiagnostics.RenderDrainInFlightMs();

        if (drain < StallDrainMs)
        {
            return false;
        }

        if (System.Threading.Volatile.Read(ref _drainRefusedStamp) != presentStamp)
        {
            System.Threading.Volatile.Write(ref _drainRefusedStamp, presentStamp);
            System.Threading.Volatile.Write(ref _drainRefusals, System.Threading.Volatile.Read(ref _drainRefusals) + 1);
        }

        if (drain > System.Threading.Volatile.Read(ref _drainRefusedLongestMs))
        {
            System.Threading.Volatile.Write(ref _drainRefusedLongestMs, drain);
        }

        return true;
    }

    // A session's count starts from zero, as StallCompactions (its run, and its first frame).
    private static void ClearDrainRefusals()
    {
        System.Threading.Volatile.Write(ref _drainRefusals, 0);
        System.Threading.Volatile.Write(ref _drainRefusedStamp, 0);
        System.Threading.Volatile.Write(ref _drainRefusedLongestMs, 0);
    }
    // RewindBox (adapt_stall_compaction_drain_guard) end
'''

GATE_OLD = '''            if (presentStamp != -1 &&
                (System.Threading.Volatile.Read(ref _lastPresent) != presentStamp || System.Threading.Volatile.Read(ref _hostPaused)))
            {
                return;
            }
'''
GATE_NEW = GATE_OLD + '''
            // RewindBox (adapt_stall_compaction_drain_guard): nor once the render thread has been in one drain for half
            // the gap, checked again right before collecting.
            if (presentStamp != -1 && DrainHolds(presentStamp))
            {
                return;
            }
'''

AGE_OLD = '''            System.GCMemoryInfo before = System.GC.GetGCMemoryInfo();
'''
AGE_NEW = AGE_OLD + '''            long drain = Ryujinx.Common.EmbeddedPerformanceDiagnostics.RenderDrainInFlightMs(); // RewindBox (adapt_stall_compaction_drain_guard)
'''

LINE_OLD = '''                $"device {Ryujinx.Memory.HostMemoryBudget.DeviceAvailablePercent}% available (adapt_safe_point_compaction)");
'''
LINE_NEW = '''                $"device {Ryujinx.Memory.HostMemoryBudget.DeviceAvailablePercent}% available (adapt_safe_point_compaction); " +
                $"renderDrain in flight {drain} ms; stall compactions refused for a drain {System.Threading.Volatile.Read(ref _drainRefusals)} " +
                $"(longest {System.Threading.Volatile.Read(ref _drainRefusedLongestMs)} ms) (adapt_stall_compaction_drain_guard)");
'''

FILE_PAIRS = {
    MEMORY: ((FIRST_FRAME_OLD, FIRST_FRAME_NEW), (WATCH_OLD, WATCH_NEW), (POLL_OLD, POLL_NEW), (GUARD_OLD, GUARD_NEW),
             (GATE_OLD, GATE_NEW), (AGE_OLD, AGE_NEW), (LINE_OLD, LINE_NEW)),
    DIAGNOSTICS: ((ACCESSOR_OLD, ACCESSOR_NEW),),
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
