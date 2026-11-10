"""Every ephemeral GC's pause, generation and sizes, journaled by the keep-alive thread (Core 723 candidate, decides the
gen0 budget).

IPA 718, Hogwarts Legacy in play (pid 44597): each 5 s record shows 130-190 ms of GC pause for 2-3 collections and no
gen2; fitting the windows by their collection counts gives about 29 ms per gen0 and about 135 ms per gen1, i.e. a hitch
of several frames every ~5 s. The engine runs with a 64 MiB gen0 budget (MeloNXRuntimeAPI.swift, DOTNET_GCgen0size,
chosen at build 620 for the 610 gen0 collections of the start). The per-window record keeps only totals and the gcEvent
lines only gen2s, so neither the cost per generation nor what it scales with (gen0/gen1 size, promotions) is known.

Change (EmbeddedSession.cs, BackgroundGcKeepAlive only; no collection, schedule or setting changes): the loop that
already reads the GC records every 250 ms also reads the ephemeral record (GC.GetGCMemoryInfo(GCKind.Ephemeral)); each
new one is added to its generation's count, pause total, longest pause and promoted bytes, and counted when over a
33.3 ms frame. A collection paused 20 ms or more gets one `gcPause ephemeral` line (generation, pause, promoted bytes,
gen0 and gen1 size before/after, compacted, its rank among such collections): the first 24, then every 16th, at most 48
per session. The run's collections are counted by generation from the runtime's collection counts (GC.CollectionCount;
a gen2, background or blocking, counts in all three generations and so in neither ephemeral total; the record index is
shared by every kind of collection and does not count ephemeral ones), read when the run starts and in the summary: a
`gcPause summary` line after the keep-alive's own gives, per generation, the collections seen of those that ran.
Every read and line is inside its own catch: a failure only silences the journal. Not measured on an iPhone. Fail
closed on drift: the file must be adapt_gc_keepalive_dormant's output on the Core 721 preparation.
"""
import hashlib
from adapt_session import once

SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
BASELINE = {
    SESSION: 'e0b64f83e5c2f648cde40f2707c918ee599d8c1a53e454bce370e52362cef560',
}

CONST_OLD = '''    public const int MaxDormantLines = 4; // RewindBox (adapt_gc_keepalive_dormant)
'''
CONST_NEW = '''    public const int MaxDormantLines = 4; // RewindBox (adapt_gc_keepalive_dormant)
    // RewindBox (adapt_gc_pause_journal): an ephemeral collection paused this long or more gets a line: the first
    // DenseLines of them, then every LineStride-th, at most MaxPauseLines per session.
    public const double PauseLineMs = 20;
    public const int DenseLines = 24;
    public const int LineStride = 16;
    public const int MaxPauseLines = 48;
    public const double FrameBudgetMs = 33.3;
'''

RUN_OLD = '''        public long Dormant; // RewindBox (adapt_gc_keepalive_dormant): windows closed dormant after a fragmented skip
'''
RUN_NEW = '''        public long Dormant; // RewindBox (adapt_gc_keepalive_dormant): windows closed dormant after a fragmented skip
        // RewindBox (adapt_gc_pause_journal): the runtime's collection counts when the run started (-1: not read); per
        // ephemeral generation (0, 1) the collections seen, their pause total and longest, the bytes they promoted.
        public (long Gen0, long Gen1, long Gen2) CountsAtStart = (-1, -1, -1);
        public readonly long[] Seen = new long[2], Promoted = new long[2];
        public readonly double[] PauseMs = new double[2], LongestMs = new double[2];
        public long OverFrame, LongPauses, PauseLines;
'''

SEAM_OLD = '''    internal static Func<long> ReadBlockingIndex = static () => GC.GetGCMemoryInfo(GCKind.FullBlocking).Index; // adapt_bgc_fragmentation_guard
'''
SEAM_NEW = '''    internal static Func<long> ReadBlockingIndex = static () => GC.GetGCMemoryInfo(GCKind.FullBlocking).Index; // adapt_bgc_fragmentation_guard

    // RewindBox (adapt_gc_pause_journal): the latest ephemeral collection (index, generation, first pause, promoted bytes,
    // gen0 and gen1 size before and after, compacted), and the runtime's collection counts (each collection counts in its
    // generation and every younger one). Test seams; production reads the runtime.
    internal readonly record struct EphemeralRecord(long Index, int Generation, double PauseMs, long PromotedBytes,
        long Gen0Before, long Gen0After, long Gen1Before, long Gen1After, bool Compacted);

    internal static Func<EphemeralRecord> ReadEphemeral = static () =>
    {
        GCMemoryInfo info = GC.GetGCMemoryInfo(GCKind.Ephemeral);
        ReadOnlySpan<GCGenerationInfo> generations = info.GenerationInfo;
        ReadOnlySpan<TimeSpan> pauses = info.PauseDurations;
        return new EphemeralRecord(info.Index, info.Generation, pauses.Length > 0 ? pauses[0].TotalMilliseconds : 0, info.PromotedBytes,
            generations.Length > 0 ? generations[0].SizeBeforeBytes : 0, generations.Length > 0 ? generations[0].SizeAfterBytes : 0,
            generations.Length > 1 ? generations[1].SizeBeforeBytes : 0, generations.Length > 1 ? generations[1].SizeAfterBytes : 0,
            info.Compacted);
    };

    internal static Func<(long Gen0, long Gen1, long Gen2)> ReadCollectionCounts =
        static () => (GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2));

    private static string Mib(long bytes) =>
        (bytes / (1024.0 * 1024.0)).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);

    private static void NoteEphemeral(Run run, EphemeralRecord record)
    {
        int generation = record.Generation >= 1 ? 1 : 0;
        run.Seen[generation]++;
        run.PauseMs[generation] += record.PauseMs;
        run.Promoted[generation] += record.PromotedBytes;
        if (record.PauseMs > run.LongestMs[generation]) run.LongestMs[generation] = record.PauseMs;
        if (record.PauseMs >= FrameBudgetMs) run.OverFrame++;
        if (record.PauseMs < PauseLineMs) return;
        long rank = ++run.LongPauses;
        if (run.PauseLines >= MaxPauseLines || (rank > DenseLines && (rank - DenseLines) % LineStride != 0)) return;
        run.PauseLines++;
        EmbeddedLaunchDiagnostics.Record("gcPause", "ephemeral", detail: string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"gen{record.Generation} {record.PauseMs:F1} ms, promoted {Mib(record.PromotedBytes)} MiB, gen0 {Mib(record.Gen0Before)}->" +
            $"{Mib(record.Gen0After)} MiB, gen1 {Mib(record.Gen1Before)}->{Mib(record.Gen1After)} MiB, compacted " +
            $"{(record.Compacted ? 1 : 0)}, index {record.Index}, long collection {rank} (adapt_gc_pause_journal)"));
    }

    // RewindBox (adapt_gc_pause_journal): per ephemeral generation, the collections seen of those that ran since the run
    // started (from the runtime's counts: a gen2 counts in all three and so in neither total), their pause and promotions.
    private static string PauseSummary(Run run)
    {
        (long Gen0, long Gen1, long Gen2) start = run.CountsAtStart, now = ReadCollectionCounts();
        string ran0 = start.Gen0 < 0 ? "?" : ((now.Gen0 - start.Gen0) - (now.Gen1 - start.Gen1)).ToString(System.Globalization.CultureInfo.InvariantCulture);
        string ran1 = start.Gen0 < 0 ? "?" : ((now.Gen1 - start.Gen1) - (now.Gen2 - start.Gen2)).ToString(System.Globalization.CultureInfo.InvariantCulture);
        return string.Create(System.Globalization.CultureInfo.InvariantCulture,
            $"ephemeral collections gen0 seen {run.Seen[0]} of {ran0}, pause {run.PauseMs[0]:F0} ms, longest {run.LongestMs[0]:F1} ms, " +
            $"promoted {Mib(run.Promoted[0])} MiB; gen1 seen {run.Seen[1]} of {ran1}, pause {run.PauseMs[1]:F0} ms, longest " +
            $"{run.LongestMs[1]:F1} ms, promoted {Mib(run.Promoted[1])} MiB; over {FrameBudgetMs:F1} ms {run.OverFrame}, paused " +
            $"{PauseLineMs:F0} ms or more {run.LongPauses}, lines {run.PauseLines} (adapt_gc_pause_journal)");
    }
'''

START_RUN_OLD = '''            Run run = new(generation);
'''
START_RUN_NEW = '''            Run run = new(generation);
            try { run.CountsAtStart = ReadCollectionCounts(); } catch { } // RewindBox (adapt_gc_pause_journal)
'''

SUMMARY_OLD = '''                "(adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, adapt_gc_keepalive_dormant)");
        }
        catch { }
'''
SUMMARY_NEW = '''                "(adapt_bgc_keepalive, adapt_bgc_fragmentation_guard, adapt_gc_keepalive_dormant)");
        }
        catch { }
        try { EmbeddedLaunchDiagnostics.Record("gcPause", "summary", detail: PauseSummary(run)); } catch { } // adapt_gc_pause_journal
'''

START_OLD = '''            long lastIndex = ReadBackgroundIndex();
'''
START_NEW = '''            long lastIndex = ReadBackgroundIndex();
            // RewindBox (adapt_gc_pause_journal): collections before this read are not the run's; none is noted if it fails.
            long lastEphemeral = long.MaxValue;
            try { lastEphemeral = ReadEphemeral().Index; } catch { }
'''

POLL_OLD = '''                long now = ReadMilliseconds();
                long index = ReadBackgroundIndex();
'''
POLL_NEW = '''                long now = ReadMilliseconds();
                // RewindBox (adapt_gc_pause_journal): the ephemeral collection that ended since the previous read, if any; a
                // journal failure never stops the keep-alive.
                try
                {
                    EphemeralRecord ephemeral = ReadEphemeral();
                    if (ephemeral.Index > lastEphemeral)
                    {
                        lastEphemeral = ephemeral.Index;
                        NoteEphemeral(run, ephemeral);
                    }
                }
                catch { }
                long index = ReadBackgroundIndex();
'''

PAIRS = ((CONST_OLD, CONST_NEW), (RUN_OLD, RUN_NEW), (SEAM_OLD, SEAM_NEW), (START_RUN_OLD, START_RUN_NEW),
         (SUMMARY_OLD, SUMMARY_NEW), (START_OLD, START_NEW), (POLL_OLD, POLL_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[SESSION], old, new)
    return list(paths.values())
