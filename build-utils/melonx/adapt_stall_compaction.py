"""Give the managed heap's free space back while the game presents nothing (Core 745 candidate).

IPA 729 / Core 743, Hogwarts Legacy 1x (pid 58475, session 12:47:40-12:50:29Z). The first-frame compaction
(adapt_safe_point_compaction) ran at 12:47:47: large object heap 519 MiB (253 free) -> 266 MiB (0 free), footprint
2 903 -> 2 669 MiB, 80.5 ms. The game then went on loading: the GPU thread allocated 275 MiB in the 5 s window around
t = 20-25 s (texture uploads 141 MiB) and 216 MiB around t = 40-45 s (texture uploads 167 MiB, 144 MiB of bound texture
array storage in 11 calls). From the 30 s report on, the large object heap is 455-458 MiB with 165-234 MiB free, for
the whole session (memoryInventory reports 2-6), gen2 + LOH free space after each collection 141-250 MiB. Nothing gives
that space back: the background collections sweep, a swept free block stays committed and touched (gc.cpp thread_gap
resets gen2 gaps only, and only at 99 % memory load). At the session's end the compaction of the host pause ran:
LOH 455 MiB (169 free) -> 279 MiB (0 free), footprint 4 882 -> 4 576 MiB (306 MiB), with the device at 9 % available.
So 170-300 MiB of the footprint during play is free managed space left by the loading.
The same session presents nothing for a whole second at t = 36 s and 0.9 frame at t = 46 s (loading), after each burst.

Change (EmbeddedMemory.cs, WindowBase.cs, EmbeddedSession.cs; every title). The render loop stamps each presented
frame. The keep-alive's poll (250 ms, its own thread) runs the existing compaction (one blocking compacting collection,
the LOH once) when all of these hold: no frame was presented for 700 ms, the session's first frame is 10 s old, gen2
and the LOH had 128 MiB or more free at the last collection, the device has 15 % or less available, the last compaction
of any kind is 8 s old, fewer than 3 such compactions ran in the session, and no stop is requested. A host pause keeps
its own rule (held 3 s, 60 s apart): the poll does nothing while one lasts. A resume counts as a presented frame and
still waits for a compaction in flight, as before; inside the compaction's gate the stamp the poll saw is compared
again, so a frame, a resume or a pause that came in between cancels it. A session's run clears what an earlier
session left (a last frame of a closing session can come after its end).
Each compaction writes the existing journal line (memory, heapCompacted) with the reason "presentationGap <ms>", the
footprint, the heap sizes before and after and the pause: the bytes given back are read there.
No periodic collection: none without a presentation gap of 700 ms, at most three in a session. The engine threads are
stopped for the collection while the game was presenting nothing; guest code and native compilation go on.
Replayed on the 729 session (the gate, with the recorded frames per second, free space and device share): the rule
fires in the loading stall of the 36th second (250 MiB free), in that of the 46th second too (141 MiB free) if its
single frame came at its end, and never in the 76 s of play that follow; with the seconds the journal has no record
for counted as gaps, a third and last one in the 69th second.

Expected on the device (same save and route): one or two "presentationGap" lines before play, each with its
footprint before and after (729's two compactions gave 234 and 306 MiB); memoryInventory reports from 60 s on with
lohFreeAfterBytes under 100 MiB (729: 165-187) if the second loading burst is followed by a gap, and a footprint at
t = 150 s 150 MiB or more under 729's 4 782 MiB. Refuted and removed if no such line appears with the free space still
there, or if a line appears during play with gaps over 500 ms per minute above 729's 1.6.
Not treated: what allocates the loading bursts (texture uploads through the buffer pool's misses, the bound array
storage), free space that appears during play without a gap.
Rollback: drop this adapter from prepare_embedded.py and the plan. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

MEMORY = 'src/Ryujinx.Library/EmbeddedMemory.cs'
WINDOW = 'src/Ryujinx.Library/Window/WindowBase.cs'
SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {
    MEMORY: '18de65a8b0a06343339a24179065128fdfbb9b4cbf828b208766e7b844fee408',
    WINDOW: '41a467934c4eb022af756c7e303260d3ffec0face359780cd47b4efe94a0169d',
    SESSION: 'dc2e54e7f734fa3d4c2b40650c71e5734cdebe3c041468b549d4110f31a21aae',
}

RESUME_OLD = '''    internal static void BeforeResume()
    {
        System.Threading.Interlocked.Increment(ref _pauseGeneration);
'''
RESUME_NEW = RESUME_OLD + '''        // RewindBox (adapt_stall_compaction): a resume is not a presentation gap.
        System.Threading.Volatile.Write(ref _lastPresent, System.Environment.TickCount64);
        System.Threading.Volatile.Write(ref _hostPaused, false);
'''

PAUSE_OLD = '''    internal static void OnHostPause(bool paused, System.Func<bool> stopping)
    {
        int generation = System.Threading.Interlocked.Increment(ref _pauseGeneration);
'''
PAUSE_NEW = PAUSE_OLD + '''        // RewindBox (adapt_stall_compaction): a host pause has its own rule (held 3 s); the poll does nothing in it.
        System.Threading.Volatile.Write(ref _hostPaused, paused);
'''

END_OLD = '''    internal static void OnSessionEnd() => System.Threading.Interlocked.Increment(ref _pauseGeneration);
'''
END_NEW = '''    internal static void OnSessionEnd()
    {
        System.Threading.Interlocked.Increment(ref _pauseGeneration);
        // RewindBox (adapt_stall_compaction): no session presents; the poll does nothing until the next first frame.
        System.Threading.Volatile.Write(ref _firstPresent, 0);
        System.Threading.Volatile.Write(ref _hostPaused, false);
    }
'''

COMPACT_OLD = '''    private static void Compact(string reason, int generation = -1)
'''
COMPACT_SIGNATURE = '''    private static void Compact(string reason, int generation = -1, long presentStamp = -1)
'''

GATE_OLD = '''            if (generation != -1 && System.Threading.Volatile.Read(ref _pauseGeneration) != generation)
            {
                return;
            }
'''
GATE_NEW = GATE_OLD + '''
            // RewindBox (adapt_stall_compaction): a frame was presented, a resume began or a host pause started since
            // the poll saw the gap (a resume stamps before it waits for this gate): no longer the poll's to compact.
            if (presentStamp != -1 &&
                (System.Threading.Volatile.Read(ref _lastPresent) != presentStamp || System.Threading.Volatile.Read(ref _hostPaused)))
            {
                return;
            }
'''
STALL = '''    // RewindBox (adapt_stall_compaction) begin
    // The heap reaches a second peak after the first frame, while the game goes on loading, and the free space it
    // leaves stays committed for the session (IPA 729 Hogwarts Legacy: LOH 266 MiB at the first frame, 455 MiB with
    // 165-234 MiB free from 30 s on; the host pause's compaction at the end gave 306 MiB of footprint back). The same
    // compaction is run while the game presents nothing: see ShouldCompactInStall.
    internal const long StallReclaimableBytes = 128 * MiB;
    internal const int StallGapMs = 700;
    internal const long StallAfterFirstFrameMs = 10_000;
    internal const long StallIntervalMs = 8_000;
    internal const int StallMaxPerSession = 3;

    private static long _firstPresent; // the session's first presented frame; 0: no session presents
    private static long _lastPresent;
    private static int _stallCompactions;
    private static bool _hostPaused;
    private static System.Func<bool> _stopping;

    internal static int StallCompactions => System.Threading.Volatile.Read(ref _stallCompactions);

    // Render loop, after each presented frame.
    internal static void NotePresented()
    {
        long now = System.Environment.TickCount64;

        if (System.Threading.Volatile.Read(ref _firstPresent) == 0)
        {
            System.Threading.Volatile.Write(ref _stallCompactions, 0);
            System.Threading.Volatile.Write(ref _firstPresent, now == 0 ? 1 : now);
        }

        System.Threading.Volatile.Write(ref _lastPresent, now);
    }

    // The session's run, once, before its keep-alive starts: how the poll learns that a stop was requested; nothing of
    // an earlier session is left (a last frame of the closing one may have come after its end).
    internal static void WatchStalls(System.Func<bool> stopping)
    {
        System.Threading.Volatile.Write(ref _stopping, stopping);
        System.Threading.Volatile.Write(ref _firstPresent, 0);
        System.Threading.Volatile.Write(ref _stallCompactions, 0);
        System.Threading.Volatile.Write(ref _hostPaused, false);
    }

    internal static bool ShouldCompactInStall(long reclaimable, int devicePercent, long sinceFirstFrameMs, long sinceLastPresentMs,
        long sinceLastCompactionMs, int done) =>
        reclaimable >= StallReclaimableBytes && devicePercent >= 0 && devicePercent <= PauseDeviceShortPercent &&
        sinceFirstFrameMs >= StallAfterFirstFrameMs && sinceLastPresentMs >= StallGapMs &&
        sinceLastCompactionMs >= StallIntervalMs && done >= 0 && done < StallMaxPerSession;

    // The keep-alive's poll (every 250 ms, on its thread).
    internal static void OnPoll()
    {
        try
        {
            long first = System.Threading.Volatile.Read(ref _firstPresent);

            if (first == 0 || System.Threading.Volatile.Read(ref _hostPaused))
            {
                return;
            }

            long now = System.Environment.TickCount64;
            long stamp = System.Threading.Volatile.Read(ref _lastPresent);
            long gap = now - stamp;
            int done = System.Threading.Volatile.Read(ref _stallCompactions);

            // In play this is the whole poll: a frame was presented less than StallGapMs ago.
            if (gap < StallGapMs || done >= StallMaxPerSession || !Ryujinx.Memory.HostMemoryBudget.IsConstrained)
            {
                return;
            }

            long last = System.Threading.Interlocked.Read(ref _lastCompaction);

            if (!ShouldCompactInStall(ReclaimableBytes(System.GC.GetGCMemoryInfo()), Ryujinx.Memory.HostMemoryBudget.DeviceAvailablePercent,
                    now - first, gap, last == 0 ? long.MaxValue : now - last, done))
            {
                return;
            }

            System.Func<bool> stopping = System.Threading.Volatile.Read(ref _stopping);

            if (stopping != null && stopping())
            {
                return;
            }

            int before = System.Threading.Volatile.Read(ref Compactions);
            Compact(string.Create(System.Globalization.CultureInfo.InvariantCulture, $"presentationGap {gap} ms"), presentStamp: stamp);

            if (System.Threading.Volatile.Read(ref Compactions) != before)
            {
                System.Threading.Interlocked.Increment(ref _stallCompactions);
            }
        }
        catch (System.Exception error)
        {
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("memory", "heapCompactionFailed", detail: "presentationGap: " + error.GetType().Name);
        }
    }
    // RewindBox (adapt_stall_compaction) end

'''
COMPACT_NEW = STALL + COMPACT_SIGNATURE

PRESENT_OLD = '''                    if (Device.PresentLoop(SwapBuffers))
                    {
                        if (!_ranFirstFrame)
'''
PRESENT_NEW = '''                    if (Device.PresentLoop(SwapBuffers))
                    {
                        // RewindBox (adapt_stall_compaction): the time of the last presented frame (two stores).
                        EmbeddedHeapCompaction.NotePresented();
                        if (!_ranFirstFrame)
'''

WATCH_OLD = '''                BackgroundGcKeepAlive.Start(generation); // RewindBox (adapt_bgc_keepalive)
'''
WATCH_NEW = '''                EmbeddedHeapCompaction.WatchStalls(static () => EmbeddedSessions.IsStopping); // RewindBox (adapt_stall_compaction)
''' + WATCH_OLD

POLL_OLD = '''                CollectionClass.ReleaseAfterRestart();
'''
POLL_NEW = POLL_OLD + '''                // RewindBox (adapt_stall_compaction): the heap's free space is given back while the game presents nothing.
                EmbeddedHeapCompaction.OnPoll();
'''

FILE_PAIRS = {
    MEMORY: ((RESUME_OLD, RESUME_NEW), (END_OLD, END_NEW), (PAUSE_OLD, PAUSE_NEW), (GATE_OLD, GATE_NEW), (COMPACT_OLD, COMPACT_NEW)),
    WINDOW: ((PRESENT_OLD, PRESENT_NEW),),
    SESSION: ((WATCH_OLD, WATCH_NEW), (POLL_OLD, POLL_NEW)),
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
