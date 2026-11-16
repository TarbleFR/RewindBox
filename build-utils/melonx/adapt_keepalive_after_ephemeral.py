"""The background-GC keep-alive makes its window's request right after an ephemeral collection ends, or 15.5 s after the
background record changed at the latest (every title with the keep-alive active).

Evidence (IPA 748-751 / Core 030cc14f, private journals; counts and times only):
- Hogwarts Legacy, pid 12613 (IPA 749), ephemeral collections journaled (startup and loading included; the 221.1 ms one
  at loading): certainly during a background gen2 3, for 999.5 ms (653.5, 258.7 and 87.3 ms); undecidable 6 (522.5 ms);
  outside one 17 (681.9 ms, median 36.5, longest 68.8 ms). None of 100 ms or more outside a background gen2. The gen0 of
  653.5 ms (1.2 MiB promoted) is a presentation gap of about 700 ms. The 16 journaled background gen2s (the per-kind line
  cap, reached 47 s before the journal ends) stop the engine 41.3 ms at most: the long stops are ephemeral collections
  that wait.
- Presentation gaps with stop samples: Hogwarts 566.7, 483.4 and 333.4 ms (the background thread uses 354, 430 and 236 ms
  of CPU in them, marking from the handle table; more than 6000 pages decompressed per episode); SSBU 150, 216.7 and
  283.4 ms. Only .NET_BGC and at most one other thread run in them.
- Cause (plan 748 rank 2, from gc.cpp and the iOS binary 4c783cc4): the background thread yields to a foreground
  collection only while g_fSuspensionPending is raised (allow_fgc), which the NativeAOT 10.0.0 runtime never does; it
  stays cooperative through its handle marking (background_mark_phase, right after the BGC's initial suspension) and
  background_sweep, and the ephemeral collection's pause counts the wait.
- The keep-alive (adapt_bgc_keepalive, adapt_keepalive_hold_off) requested its gen2 at the first poll 12 s after the
  previous one, wherever the gen0 budget stood: 14 background gen2s in 168.8 s of Hogwarts play (5.0 per min, against
  1.7 in IPA 740); 41 (pid 12550) and 20 (pid 14991) requests in the SSBU sessions; windows missed 0, requests run
  blocking 0, fellBackFromBackground 0 in the 55 gcEvent lines. Gen0 collections come every 1 to 2.5 s in Hogwarts play;
  the background thread's CPU episodes last 1 to 2 s.

Change (EmbeddedSession.cs, BackgroundGcKeepAlive):
- Loop: each poll notes whether its ephemeral record read (adapt_gc_pause_journal) saw a new collection end since the
  previous read. In case Decision.Induce the request is made only when that poll saw one end, or when the poll is
  LatestRequestMs = WindowEndMs - 2 x PollMs = 15500 ms or more after the background record changed (RequestNow);
  otherwise nothing happens at that poll and the next poll decides again. A background gen2 requested within a poll
  (250 ms) of an ephemeral collection's end usually finds gen0's budget unspent, so no ephemeral collection runs before it
  (gc.cpp check_for_ephemeral_alloc), and the next one, which would wait for the cooperative handle marking that starts
  the concurrent phase, comes about a whole gen0 budget later.
- The window itself is unchanged (Decide: no request before 12 s, none after 16 s, the heap size and fragmentation
  rules, dormancy); the window is not lengthened, short of memory or otherwise. The request, its blocking check, the
  journal lines and every other counter are unchanged; no collection, lock, wait or setting is added.
- The existing gcKeepAlive summary line gains two counts, to read the change on the device: "requests right after an
  ephemeral collection A, at 15500 ms without one B" (A + B = background gen2 requests).
Nothing guest-visible changes: only the instant of an existing host request inside its existing window.

Scope: every title whose managed heap reaches 384 MiB (the keep-alive's own rule). It covers only the keep-alive's
background gen2s, not the runtime's own (share unknown: the background gcEvent end lines are quantified to 5 s), and at
best the first ephemeral collection of each background gen2 (one BGC of pid 12613 saw at least three). The plan's
managed alternative to adapt_bgc_suspension_pending (rank 2, which needs native code); it is not written with it.

Bound (plan 748 rank 2, on the observed events only, not measured): at most the rank's bound, Hogwarts 749 about 2.1 s
of 168.8 s of play (about 1.2 %; up to 2.4 s if the undecidable pauses of play were during a background gen2) and SSBU
at most 0.58 s over 3 gaps in about 24 min; for this alternative only the share of those stops that follow the first
ephemeral collection of a keep-alive gen2 (the analysis' bound: at most about 1.4 % of play), and nothing for the
runtime's own.

Risk, a missed window (the window is not lengthened to cover it):
- If no ephemeral collection ends in the window before 15.5 s, the request waits for the first poll from 15.5 s instead
  of the first from 12 s. The last poll deferred then fell between 15.25 and 15.5 s (polls 250 ms apart), and holding the
  next poll longer than 15.75 s minus that time, 250 to 500 ms depending on the alignment, misses the window (counted in
  "windows missed"). The window's other poll from 15.5 s only helps after a refused poll (fragmented, small heap), never
  after a hold. The control (first poll from 12 s) misses only when held over 3.75 s.
- The keep-alive thread can hold itself there: each poll runs adapt_stall_compaction's blocking compaction (OnPoll,
  before the poll reads its clock), one presentationGap compaction of 345 and one of 346 ms in all in the two SSBU
  sessions, 158 ms in 12613 (at most 3 per session); 345 ms misses in about 38 % of the alignments. Any other hold of
  this below-normal thread at that poll counts the same.
- SSBU would rely on the 15.5 s request in about 40 % of its windows (estimate: 52 of 134 and 27 of 86 play windows of
  5.1 s saw no ephemeral collection; a Poisson estimate from 0.18 and 0.21 per second gives about half); Hogwarts rarely
  (each of its 31 play windows of 5.1 s saw one).
- A missed window lets the BGC thread leave after its 20 s idle wait, and the runtime's next gen2 risks the 300-500 ms
  blocking fallback (plan), as much as this alternative's whole SSBU bound. A hold must land on one poll per window: rare,
  not measured. The gate executes holds of 300 ms (a request at 16 s), 345 ms and 750 ms (missed) after a deferred poll.

Expected on the device (gcKeepAlive summary, at the session's close): "requests right after an ephemeral collection"
close to "background gen2 requests" in Hogwarts play, "at 15500 ms without one" small there and about 40 % of the
requests in SSBU (estimate); "windows missed 0" in most sessions (a miss is this alternative's cost, see the risk);
"requests run blocking 0" and gcEvent fellBackFromBackground 0 as before. The effect itself is read from fewer long
ephemeral pauses during a background gen2 (gcPause lines; adapt_gc_journal_interim, plan lot 1) and fewer freeze records
where .NET_BGC dominates. Not measured on an iPhone; no FPS, heat or stability gain claimed.

Applied after adapt_keepalive_hold_off, the last adapter of this file (its post-image is Core 030cc14f's final file).
Rollback: drop this adapter from prepare_embedded.py and ORDER, also when the device shows missed windows followed by a
gen2 that fell back from a background one. Fail closed on drift.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {SESSION: 'cfeddf0d7ed509df9b390ad741c87126e3ea7d249074768b53a1df3f120cc7ac'}

CONST_OLD = '''    public const int PollMs = 250;
'''
CONST_NEW = '''    public const int PollMs = 250;
    // RewindBox (adapt_keepalive_after_ephemeral): from this long after the background record changed, the window's request
    // no longer waits for an ephemeral collection to end; the window still closes at 16 s. At most two polls remain, and the
    // second only helps after a refused one: holding the poll after the last deferred one (from 15.25 s) 250 to 500 ms, by
    // alignment, misses the window, e.g. the stall compaction OnPoll runs on this thread (345 ms in SSBU).
    public const long LatestRequestMs = WindowEndMs - 2 * PollMs;
'''

DECIDE_OLD = '''        if (heapBytes < MinimumHeapBytes) return Decision.SmallHeap;
        return Decision.Induce;
    }
'''
DECIDE_NEW = '''        if (heapBytes < MinimumHeapBytes) return Decision.SmallHeap;
        return Decision.Induce;
    }

    // RewindBox (adapt_keepalive_after_ephemeral): a window's request (Decide gave Induce) is made at the poll that saw an
    // ephemeral collection end, or from LatestRequestMs on without one. A background gen2 started then has gen0's whole
    // budget before the next ephemeral collection, which waits for the background thread's cooperative handle marking
    // (NativeAOT never raises the collector's suspension-pending count: gc.cpp allow_fgc).
    public static bool RequestNow(long msSinceBackground, bool ephemeralEnded) =>
        ephemeralEnded || msSinceBackground >= LatestRequestMs;
'''

RUN_OLD = '''        public long Dormant; // RewindBox (adapt_gc_keepalive_dormant): windows closed dormant after a fragmented skip
'''
RUN_NEW = '''        public long Dormant; // RewindBox (adapt_gc_keepalive_dormant): windows closed dormant after a fragmented skip
        public long AfterEphemeral, AtLatest; // RewindBox (adapt_keepalive_after_ephemeral): the requests, by what allowed them
'''

SUMMARY_OLD = '''                $"dormant after a fragmented skip {run.Dormant} " +
                "(adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, adapt_gc_keepalive_dormant)");
'''
SUMMARY_NEW = '''                $"dormant after a fragmented skip {run.Dormant}, requests right after an ephemeral collection {run.AfterEphemeral}, " +
                $"at {LatestRequestMs} ms without one {run.AtLatest} " +
                "(adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, adapt_gc_keepalive_dormant, adapt_keepalive_after_ephemeral)");
'''

POLL_OLD = '''                long now = ReadMilliseconds();
'''
POLL_NEW = '''                long now = ReadMilliseconds();
                bool ephemeralEnded = false; // RewindBox (adapt_keepalive_after_ephemeral): set by this poll's read below
'''

ENDED_OLD = '''                        lastEphemeral = ephemeral.Index;
                        NoteEphemeral(run, ephemeral);
'''
ENDED_NEW = '''                        lastEphemeral = ephemeral.Index;
                        ephemeralEnded = true; // RewindBox (adapt_keepalive_after_ephemeral)
                        NoteEphemeral(run, ephemeral);
'''

INDUCE_OLD = '''                    case Decision.Induce:
                        long blockingBefore = ReadBlockingIndex();
'''
INDUCE_NEW = '''                    case Decision.Induce:
                        // RewindBox (adapt_keepalive_after_ephemeral): right after an ephemeral collection ended, or from
                        // LatestRequestMs on; otherwise nothing at this poll, and the next one decides again.
                        if (!RequestNow(now - lastChange, ephemeralEnded)) break;
                        long blockingBefore = ReadBlockingIndex();
'''

COUNT_OLD = '''                        refusedThisWindow = false; // RewindBox (adapt_gc_keepalive_dormant)
                        if (++run.Requests == 1)
'''
COUNT_NEW = '''                        refusedThisWindow = false; // RewindBox (adapt_gc_keepalive_dormant)
                        if (ephemeralEnded) run.AfterEphemeral++; else run.AtLatest++; // RewindBox (adapt_keepalive_after_ephemeral)
                        if (++run.Requests == 1)
'''

PAIRS = ((CONST_OLD, CONST_NEW), (DECIDE_OLD, DECIDE_NEW), (RUN_OLD, RUN_NEW), (SUMMARY_OLD, SUMMARY_NEW),
         (POLL_OLD, POLL_NEW), (ENDED_OLD, ENDED_NEW), (INDUCE_OLD, INDUCE_NEW), (COUNT_OLD, COUNT_NEW))


def apply(source):
    path = source / SESSION
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, SESSION
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
