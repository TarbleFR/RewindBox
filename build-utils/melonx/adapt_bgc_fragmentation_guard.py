"""The background GC keep-alive never asks for a gen2 the runtime would run blocking and compacting (Core 719).

IPA 718, Super Smash Bros. Ultimate (pid 45272, session E81E2B1B, asyncShaders off, private Core journal): an in-play
gen2 index 66 at about 03:56:20 UTC ran fullBlocking, compacted, 355.873 ms, gen2 362 MB with 157 MB free and the LOH
447 MB with 256 MB free before it (gen2 362 -> 203 MB, LOH 447 -> 172 MB after), not a fallback (fellBackFromBackground
0); a presentation interval of 366.7 ms is adjacent. Mechanism (.NET 10.0.0 gc.cpp generation_to_condemn): with
GCConserveMemory set (Ryujinx.Library.csproj: System.GC.ConserveMemory 5, adapt_gc) every gen2 the GC decides is made
blocking when (gen2 + LOH fragmentation) / (gen2 + LOH size) exceeds 1 - 5 / 10 = 0.5, and compacts the LOH when the
LOH's own ratio exceeds it: (157 + 256) / (362 + 447) = 0.51, LOH 256 / 447 = 0.57, exactly that collection. The
keep-alive of Core 693 (adapt_bgc_keepalive) asks for a non-blocking gen2 every 12-16 s; at such a fragmentation its
request IS that blocking compacting collection, in play. Reproduced on the host .NET 10.0.0 runtime with the same
setting: a non-blocking GC.Collect(2) at a ratio of 0.63 ran blocking and compacting (259 ms); at 0.28 it ran in the
background (test/melonx_bgc_fragmentation_guard_test.py). Hogwarts' long background final pause (3666.692 ms, index
211) is a different collection: concurrent, at a ratio of 0.31, not changed here.

Change (class BackgroundGcKeepAlive in src/Ryujinx.Library/EmbeddedSession.cs, every title; nothing else):
- the decision also reads the fragmentation of the last collection (gen2 and LOH, after it); above the conserve-memory
  limit less a 0.02 margin it answers Fragmented and asks for nothing (counted once per window). The runtime's own
  schedule is unchanged: its next gen2 is the compaction it would have run anyway, at its own moment, not ours;
- a request that the runtime still ran blocking (the full blocking record advanced during the call) is journaled
  (gcKeepAlive elevated, at most 4 lines, with its pause and ratio) and counted, so the next device log tells which
  blocking gen2s the keep-alive caused;
- the session summary adds the fragmented skips and the requests that ran blocking.
No forced collection is added, no GC setting or protection changes. Not measured on an iPhone. Fail closed on drift:
the file must be the Core 717 preparation's.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {
    SESSION: '9e25a7fc01276a323a0c9a48c567750a182ad76163d2123a40b2c7d04153b35c',
}
CONSERVE_MEMORY = 5  # Ryujinx.Library.csproj (adapt_gc); the gate checks the project still says so

ENUM_OLD = '''    public enum Decision { NotSeen, Wait, Induce, Missed, SmallHeap }
'''
ENUM_NEW = '''    public enum Decision { NotSeen, Wait, Induce, Missed, SmallHeap, Fragmented }

    // RewindBox (adapt_bgc_fragmentation_guard): with System.GC.ConserveMemory 5 (Ryujinx.Library.csproj) the GC runs every
    // gen2 it decides blocking once (gen2 + LOH fragmentation) / (gen2 + LOH size) exceeds 1 - 5 / 10, and compacts the LOH
    // above that ratio of its own (gc.cpp generation_to_condemn). A request then IS a blocking compacting collection in
    // play (IPA 718 SSBU: 355.873 ms at 0.51), so none is made above the limit less a margin.
    public const double ConserveMemorySetting = 5;
    public const double FragmentationLimit = 1.0 - ConserveMemorySetting / 10.0 - 0.02;
    public const int MaxElevatedLines = 4;

    // The fragmentation of gen2 and the LOH after the last collection, as the conserve-memory rule weighs it.
    public static double FragmentationOf(GCMemoryInfo info)
    {
        ReadOnlySpan<GCGenerationInfo> generations = info.GenerationInfo;
        if (generations.Length < 4) return 0;
        long size = generations[2].SizeAfterBytes + generations[3].SizeAfterBytes;
        return size <= 0 ? 0 : (double)(generations[2].FragmentationAfterBytes + generations[3].FragmentationAfterBytes) / size;
    }

    public static Decision Decide(long msSinceBackground, long heapBytes, double fragmentation)
    {
        Decision decision = Decide(msSinceBackground, heapBytes);
        return decision == Decision.Induce && fragmentation > FragmentationLimit ? Decision.Fragmented : decision;
    }
'''

RUN_OLD = '''        public long Requests, Missed, SmallHeap, Changes;
'''
RUN_NEW = '''        public long Requests, Missed, SmallHeap, Changes;
        public long Fragmented, Elevated; // RewindBox (adapt_bgc_fragmentation_guard)
'''

SEAMS_OLD = '''    internal static Func<long> ReadMilliseconds = static () => Environment.TickCount64;
'''
SEAMS_NEW = '''    internal static Func<long> ReadMilliseconds = static () => Environment.TickCount64;
    internal static Func<double> ReadFragmentation = static () => FragmentationOf(GC.GetGCMemoryInfo()); // adapt_bgc_fragmentation_guard
    internal static Func<long> ReadBlockingIndex = static () => GC.GetGCMemoryInfo(GCKind.FullBlocking).Index; // adapt_bgc_fragmentation_guard
'''

SUMMARY_OLD = '''                $"background records seen {run.Changes} (adapt_bgc_keepalive)");
'''
SUMMARY_NEW = '''                $"background records seen {run.Changes}, fragmented skips {run.Fragmented}, requests run blocking {run.Elevated} " +
                "(adapt_bgc_keepalive, adapt_bgc_fragmentation_guard)");
'''

LOOP_OLD = '''                switch (Decide(lastChange < 0 ? -1 : now - lastChange, ReadHeapBytes()))
                {
                    case Decision.Induce:
                        RequestBackgroundCollection();
'''
LOOP_NEW = '''                double fragmentation = ReadFragmentation(); // RewindBox (adapt_bgc_fragmentation_guard)
                switch (Decide(lastChange < 0 ? -1 : now - lastChange, ReadHeapBytes(), fragmentation))
                {
                    case Decision.Fragmented:
                        if (!counted) { run.Fragmented++; counted = true; }
                        break;
                    case Decision.Induce:
                        long blockingBefore = ReadBlockingIndex();
                        long requestStart = ReadMilliseconds();
                        RequestBackgroundCollection();
                        if (ReadBlockingIndex() != blockingBefore && ++run.Elevated <= MaxElevatedLines)
                        {
                            EmbeddedLaunchDiagnostics.Record("gcKeepAlive", "elevated", detail:
                                $"a requested background gen2 ran blocking: {ReadMilliseconds() - requestStart} ms in the call, " +
                                $"fragmentation {fragmentation:F3} (limit {FragmentationLimit:F2}) (adapt_bgc_fragmentation_guard)");
                        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    session = paths[SESSION]
    once(session, ENUM_OLD, ENUM_NEW)
    once(session, RUN_OLD, RUN_NEW)
    once(session, SEAMS_OLD, SEAMS_NEW)
    once(session, SUMMARY_OLD, SUMMARY_NEW)
    once(session, LOOP_OLD, LOOP_NEW)
    return list(paths.values())
