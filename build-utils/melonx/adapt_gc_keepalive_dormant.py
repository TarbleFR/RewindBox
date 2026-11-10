"""The GC keep-alive says when it goes dormant after a window refused for fragmentation (Core 723 candidate, F1).

Core 719 (adapt_bgc_fragmentation_guard) makes no background-gen2 request while the gen2 + LOH fragmentation is above
0.48 (the System.GC.ConserveMemory 5 rule would make it a blocking compacting collection). Independent review of 719
(main, F1): when every poll of a 12-16 s window is refused for fragmentation, the window closes and the keep-alive then
stays dormant until the runtime's own next background gen2 changes the record (as after an elevated request in Core
717); that window is counted as a fragmented skip, nothing says the keep-alive is dormant, and the summary cannot tell
it from a window simply missed. Decision recorded on the board: ship 719, the next Core says it.

Change (EmbeddedSession.cs, BackgroundGcKeepAlive only; no request, schedule or GC setting changes):
- a window that closes after its fragmented skip journals one `gcKeepAlive dormant` line (at most 4 per session) with
  the fragmentation and the limit, and is counted apart (`dormant after a fragmented skip` in the summary);
- such a window is still not a missed one (`windows missed` keeps counting windows closed without any refusal);
- a request made later in the same window (the fragmentation fell below the limit in time) clears it.
Not measured on an iPhone. Fail closed on drift: the file must be the Core 721 preparation's.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {
    SESSION: 'fb620f855a7946e97682592d047ff06eba9210ff6520a1c13ace740a048bbb06',
}

CONST_OLD = '''    public const int MaxElevatedLines = 4;
'''
CONST_NEW = '''    public const int MaxElevatedLines = 4;
    public const int MaxDormantLines = 4; // RewindBox (adapt_gc_keepalive_dormant)
'''

RUN_OLD = '''        public long Fragmented, Elevated; // RewindBox (adapt_bgc_fragmentation_guard)
'''
RUN_NEW = '''        public long Fragmented, Elevated; // RewindBox (adapt_bgc_fragmentation_guard)
        public long Dormant; // RewindBox (adapt_gc_keepalive_dormant): windows closed dormant after a fragmented skip
'''

SUMMARY_OLD = '''                $"background records seen {run.Changes}, fragmented skips {run.Fragmented}, requests run blocking {run.Elevated} " +
                "(adapt_bgc_keepalive, adapt_bgc_fragmentation_guard)");'''
SUMMARY_NEW = '''                $"background records seen {run.Changes}, fragmented skips {run.Fragmented}, requests run blocking {run.Elevated}, " +
                $"dormant after a fragmented skip {run.Dormant} " +
                "(adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, adapt_gc_keepalive_dormant)");'''

STATE_OLD = '''            bool counted = false;

            while (System.Threading.Volatile.Read(ref run.Stop) == 0)'''
STATE_NEW = '''            bool counted = false;
            bool refusedThisWindow = false; // RewindBox (adapt_gc_keepalive_dormant)

            while (System.Threading.Volatile.Read(ref run.Stop) == 0)'''

CHANGE_OLD = '''                    lastChange = now;
                    counted = false;
                    run.Changes++;
                    continue;'''
CHANGE_NEW = '''                    lastChange = now;
                    counted = false;
                    refusedThisWindow = false; // RewindBox (adapt_gc_keepalive_dormant)
                    run.Changes++;
                    continue;'''

FRAGMENTED_OLD = '''                    case Decision.Fragmented:
                        if (!counted) { run.Fragmented++; counted = true; }
                        break;'''
FRAGMENTED_NEW = '''                    case Decision.Fragmented:
                        if (!counted) { run.Fragmented++; counted = true; }
                        refusedThisWindow = true; // RewindBox (adapt_gc_keepalive_dormant)
                        break;'''

INDUCE_OLD = '''                        // The next attempt waits a whole window again unless the record changes first.
                        lastChange = now;'''
INDUCE_NEW = '''                        // The next attempt waits a whole window again unless the record changes first.
                        lastChange = now;
                        refusedThisWindow = false; // RewindBox (adapt_gc_keepalive_dormant)'''

MISSED_OLD = '''                    case Decision.Missed:
                        if (!counted) { run.Missed++; counted = true; }
                        break;'''
MISSED_NEW = '''                    case Decision.Missed:
                        // RewindBox (adapt_gc_keepalive_dormant): every poll of the window was refused for fragmentation; no
                        // request now until the runtime's next background gen2 changes the record. Said once per window.
                        if (refusedThisWindow)
                        {
                            refusedThisWindow = false;
                            if (++run.Dormant <= MaxDormantLines)
                            {
                                EmbeddedLaunchDiagnostics.Record("gcKeepAlive", "dormant", detail:
                                    $"window closed with gen2 + LOH fragmentation {fragmentation:F3} above {FragmentationLimit:F2}: " +
                                    "no request until the runtime's next background gen2 (adapt_gc_keepalive_dormant)");
                            }
                        }
                        if (!counted) { run.Missed++; counted = true; }
                        break;'''

PAIRS = ((CONST_OLD, CONST_NEW), (RUN_OLD, RUN_NEW), (SUMMARY_OLD, SUMMARY_NEW), (STATE_OLD, STATE_NEW),
         (CHANGE_OLD, CHANGE_NEW), (FRAGMENTED_OLD, FRAGMENTED_NEW), (INDUCE_OLD, INDUCE_NEW), (MISSED_OLD, MISSED_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[SESSION], old, new)
    return list(paths.values())
