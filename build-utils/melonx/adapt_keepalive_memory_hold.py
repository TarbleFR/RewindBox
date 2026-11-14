"""The GC keep-alive asks for no background gen2 while the device is short of memory (every title).

IPA 736 / Core c4a25b94, Hogwarts Legacy (private journals, pid 2349, session 7E68DFD7, 250 s). From the second the
world loads (footprint 3.6 -> 4.4 GiB in one second, device 4-8 % available) iOS compresses and decompresses the
process's memory without pause (30-500 MiB per second) and the game falls from a steady 30 FPS to 10-25. The managed
heap is 650-800 MiB and mostly compressed between collections (535 of 792 MiB of its regions at t = 210 s). In play the
runtime started no gen2 of its own: all 17 were the keep-alive's (adapt_bgc_keepalive: one background gen2 12-16 s
after the previous, so that the BGC thread never exits and a gen2 never falls back to a blocking one). Each marks and
sweeps the whole heap, which pulls it out of the compressor and pushes the game's pages in: of the 560 samples of
100 ms in the journal's freeze records, those with the background collector running decompress 26.2 MiB against 10.1
(median 19.5 against 4.2) and 17 % of them are inside a frame gap over 100 ms against 5 %; the collector's thread runs
in each of the 22 gaps. IPA 733 (pid 61839): 21.5 against 10.4 MiB, 21 % against 8 %.

Without the keep-alive the runtime's own gen2s in play were 57-194 s apart, 22 % of those after an idle exit of the BGC
thread fell back to a blocking one of 100-950 ms (docs/melonx-bgc-fallback-2026-11-05.md). So, short of memory: about
one whole-heap mark per minute or two instead of one per 13 s, and a blocking fallback once in several minutes.

Change (EmbeddedSession.cs; class KeepAliveMemoryHold and two call sites in BackgroundGcKeepAlive): when a window opens
for a request while iOS reports 8 % or less of the device's memory available (kern.memorystatus_level, the figure of
the heap compactions), the request is not made. The window then closes as any missed one does: nothing is asked until
the runtime's next background gen2 (the existing rule: no request once 16 s have passed). A window held at its first
poll stays held while the level is under 12 % (in that world the level is 4-8 % in 127 of 140 s and 9-11 % in the 13
others; Super Smash Bros. Ultimate, which does not thrash, plays at 9-15 %, mostly 11-13 %, and keeps its requests).
With more memory available, or where the level cannot be read, the keep-alive is unchanged. The session summary gains
one line (the windows held); the first held windows are journaled (at most four lines).

Expected on the device (same save and route as the IPA 736 capture): background gen2s in play from one per 13 s to the
runtime's own, vm= decompressed MiB per second lower in the world, frame gaps over 100 ms per minute lower; a blocking
gen2 flagged fellBackFromBackground may appear every few minutes. Refuted and removed if those fallbacks cost more
frame time than the marks did (gaps over 250 ms per minute higher than in IPA 736: 1.14-8.66).
Rollback: drop this adapter from prepare_embedded.py and ORDER. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {SESSION: 'fe51317c0684d131a6ddd42e35a2ec30911657b921b3eb6f871012c6a6b3d666'}

CLASS = '''// RewindBox (adapt_keepalive_memory_hold): the keep-alive's background gen2 marks and sweeps the whole managed heap. While
// the device is short of memory that heap is mostly in the compressor: each mark pulls it out and pushes the game's pages
// in (IPA 736, Hogwarts Legacy: 17 such requests in 250 s, every gen2 of the play; the samples with the collector
// running decompress 26.2 MiB per 100 ms against 10.1 and are inside a frame gap over 100 ms three times as often).
// Short of memory no request is made: the runtime keeps its own schedule (gen2s one to three minutes apart in play).
public static class KeepAliveMemoryHold
{
    // iOS reports this share of the device's memory available, or less (kern.memorystatus_level).
    public const int ShortPercent = 8;
    // A window held at its first poll stays held under this level (the level moves by a point or two between polls).
    public const int ReleasePercent = 12;
    public const int MaxLines = 4;

    private static long _generation = long.MinValue;
    private static long _windows;
    private static bool _heldThisWindow;

    // Test seam; production reads the device.
    internal static System.Func<int> ReadDevicePercent = static () => Ryujinx.Memory.HostMemoryBudget.DeviceAvailablePercent;

    public static bool IsShort(int devicePercent) => devicePercent >= 0 && devicePercent <= ShortPercent;

    public static bool Holds(int devicePercent, bool heldThisWindow) =>
        IsShort(devicePercent) || (heldThisWindow && devicePercent >= 0 && devicePercent < ReleasePercent);

    // Called by the keep-alive's thread only, with its decision of this poll.
    public static BackgroundGcKeepAlive.Decision Apply(long generation, BackgroundGcKeepAlive.Decision decision)
    {
        if (generation != _generation)
        {
            _generation = generation;
            _windows = 0;
            _heldThisWindow = false;
        }

        if (decision != BackgroundGcKeepAlive.Decision.Induce)
        {
            // No window is open: the previous one closed, or a background gen2 started since.
            _heldThisWindow = false;

            return decision;
        }

        int percent;
        try { percent = ReadDevicePercent(); } catch { return decision; }

        if (!Holds(percent, _heldThisWindow))
        {
            return decision;
        }

        if (!_heldThisWindow)
        {
            _heldThisWindow = true;

            if (++_windows <= MaxLines)
            {
                try
                {
                    EmbeddedLaunchDiagnostics.Record("gcKeepAlive", "held", detail:
                        $"device {percent}% available: no background gen2 requested in this window; the runtime's own " +
                        "schedule applies until its next background gen2 (adapt_keepalive_memory_hold)");
                }
                catch { }
            }
        }

        return BackgroundGcKeepAlive.Decision.Wait;
    }

    public static string Summary(long generation) => generation != _generation
        ? "no request held short of memory (adapt_keepalive_memory_hold)"
        : $"request windows held short of memory {_windows}, at {ShortPercent}% of the device's memory available or less " +
          $"(kept under {ReleasePercent}%) (adapt_keepalive_memory_hold)";
}

'''

CLASS_OLD = '''public static class BackgroundGcKeepAlive
{
    public const long WindowStartMs = 12_000;
'''
CLASS_NEW = CLASS + CLASS_OLD

DECIDE_OLD = '''                switch (Decide(lastChange < 0 ? -1 : now - lastChange, ReadHeapBytes(), fragmentation))
'''
DECIDE_NEW = '''                // RewindBox (adapt_keepalive_memory_hold): no request while the device is short of memory.
                switch (KeepAliveMemoryHold.Apply(run.Generation, Decide(lastChange < 0 ? -1 : now - lastChange, ReadHeapBytes(), fragmentation)))
'''

SUMMARY_OLD = '''        try { EmbeddedLaunchDiagnostics.Record("gcPause", "summary", detail: PauseSummary(run)); } catch { } // adapt_gc_pause_journal
'''
SUMMARY_NEW = '''        try { EmbeddedLaunchDiagnostics.Record("gcKeepAlive", "held", detail: KeepAliveMemoryHold.Summary(run.Generation)); } catch { } // adapt_keepalive_memory_hold
''' + SUMMARY_OLD

PAIRS = ((CLASS_OLD, CLASS_NEW), (DECIDE_OLD, DECIDE_NEW), (SUMMARY_OLD, SUMMARY_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[SESSION], old, new)
    return list(paths.values())
