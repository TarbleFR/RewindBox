// Fixture of adapt_gc_pause_journal: the candidate's BackgroundGcKeepAlive (namespace Ryujinx.Common, taken from the final
// preparation by the gate) runs its real loop. Scripted: the ephemeral record and the collection counts are a fake
// sequence (gen0 and gen1 pauses above and below the line threshold; a gen1 and a background gen2 ending between two
// reads). Bound: the candidate's own NoteEphemeral and PauseSummary (by reflection) over 500 long collections. Real: the
// production reads on the host .NET 10 runtime while the fixture forces gen0 and gen1 collections, a background gen2
// and a blocking gen2. The background record the keep-alive decides on never changes (no request in any scenario).
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Text.Json;
using System.Threading;

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Lines = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            lock (Lines) Lines.Add(stage + "/" + status + ": " + detail);
        }
    }

//__CANDIDATE__
}

public static class Program
{
    private static readonly object Gate = new();
    private static long _polls, _requests, _clock;
    private static Ryujinx.Common.BackgroundGcKeepAlive.EphemeralRecord _record;
    private static (long Gen0, long Gen1, long Gen2) _counts;

    private static void Install(bool scripted)
    {
        Ryujinx.Common.BackgroundGcKeepAlive.ReadBackgroundIndex = () => { lock (Gate) { _polls++; return 7; } };
        Ryujinx.Common.BackgroundGcKeepAlive.ReadMilliseconds = () => { lock (Gate) return _clock; };
        Ryujinx.Common.BackgroundGcKeepAlive.ReadHeapBytes = () => 512L << 20;
        Ryujinx.Common.BackgroundGcKeepAlive.ReadFragmentation = () => 0.1;
        Ryujinx.Common.BackgroundGcKeepAlive.ReadBlockingIndex = () => 3;
        Ryujinx.Common.BackgroundGcKeepAlive.RequestBackgroundCollection = () => { lock (Gate) _requests++; };
        if (!scripted) return;
        Ryujinx.Common.BackgroundGcKeepAlive.ReadEphemeral = () => { lock (Gate) return _record; };
        Ryujinx.Common.BackgroundGcKeepAlive.ReadCollectionCounts = () => { lock (Gate) return _counts; };
    }

    private static void WaitPolls(int count)
    {
        long before; lock (Gate) before = _polls;
        var watch = System.Diagnostics.Stopwatch.StartNew();
        while (watch.ElapsedMilliseconds < 5000) { lock (Gate) if (_polls >= before + count) return; Thread.Sleep(20); }
        throw new TimeoutException("the loop did not poll");
    }

    private static List<string> Since(int lines)
    {
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines)
            return Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.GetRange(lines, Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Count - lines);
    }

    private static int LineCount()
    {
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines) return Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Count;
    }

    private static Ryujinx.Common.BackgroundGcKeepAlive.EphemeralRecord R(long index, int generation, double pause) =>
        new(index, generation, pause, 3L << 20, 64L << 20, 1L << 20, generation >= 1 ? 40L << 20 : 30L << 20, 30L << 20, true);

    // A collection of `generation` (2: background or blocking) as the runtime counts it: in it and every younger one.
    private static void Count(int generation)
    {
        _counts = (_counts.Gen0 + 1, _counts.Gen1 + (generation >= 1 ? 1 : 0), _counts.Gen2 + (generation >= 2 ? 1 : 0));
    }

    private static (long, long, long) Counts() => (GC.CollectionCount(0), GC.CollectionCount(1), GC.CollectionCount(2));

    public static int Main()
    {
        var report = new Dictionary<string, object>();
        var defaultRead = Ryujinx.Common.BackgroundGcKeepAlive.ReadEphemeral; // the production reads, before any seam
        var defaultCounts = Ryujinx.Common.BackgroundGcKeepAlive.ReadCollectionCounts;
        int lines;

        // Scripted: records the loop sees one at a time; a gen1 (index 13) and a background gen2 (index 14) end between
        // two reads; then 20 more long ones.
        lines = LineCount();
        _record = R(9, 0, 1);
        _counts = (100, 40, 7);
        Install(true);
        Ryujinx.Common.BackgroundGcKeepAlive.Start(1);
        WaitPolls(2);
        var script = new List<(Ryujinx.Common.BackgroundGcKeepAlive.EphemeralRecord Record, int[] Unseen)>
        {
            (R(10, 0, 25.4), Array.Empty<int>()), (R(11, 1, 140.2), Array.Empty<int>()), (R(12, 0, 5.0), Array.Empty<int>()),
            (R(15, 0, 30.0), new[] { 1, 2 }), (R(16, 1, 19.9), Array.Empty<int>()),
        };
        for (int i = 0; i < 20; i++) script.Add((R(17 + i, i % 2, 60 + i), Array.Empty<int>()));
        foreach (var (record, unseen) in script)
        {
            lock (Gate)
            {
                foreach (int generation in unseen) Count(generation);
                Count(record.Generation);
                _record = record;
            }
            WaitPolls(2);
        }
        Ryujinx.Common.BackgroundGcKeepAlive.Stop(1);
        Thread.Sleep(400);
        report["scripted"] = new Dictionary<string, object> { ["journal"] = Since(lines), ["requests"] = _requests };

        // Bound: 500 collections of 25 ms, alternately gen0 and gen1, noted by the candidate's own method; the summary of a
        // run whose start counts were not read.
        lines = LineCount();
        Type keepAlive = typeof(Ryujinx.Common.BackgroundGcKeepAlive);
        Type runType = keepAlive.GetNestedType("Run", BindingFlags.NonPublic);
        object run = Activator.CreateInstance(runType, 4L);
        MethodInfo note = keepAlive.GetMethod("NoteEphemeral", BindingFlags.NonPublic | BindingFlags.Static);
        MethodInfo summary = keepAlive.GetMethod("PauseSummary", BindingFlags.NonPublic | BindingFlags.Static);
        for (int i = 0; i < 500; i++) note.Invoke(null, new object[] { run, R(1000 + i, i % 2, 25.0) });
        report["bound"] = new Dictionary<string, object> { ["journal"] = Since(lines), ["summary"] = (string)summary.Invoke(null, new[] { run }) };

        // Real: the production reads while the fixture forces collections, each followed by a few polls. The runtime may
        // run a requested gen1 as a gen2: each forced collection's generation is read back from the runtime's record.
        lines = LineCount();
        Ryujinx.Common.BackgroundGcKeepAlive.ReadEphemeral = defaultRead;
        Ryujinx.Common.BackgroundGcKeepAlive.ReadCollectionCounts = defaultCounts;
        Install(false);
        var keep = new List<byte[]>();
        var ran = new int[3];
        int forced = 0;
        var before = Counts();
        Ryujinx.Common.BackgroundGcKeepAlive.Start(2);
        WaitPolls(2);
        void Force(int generation)
        {
            for (int j = 0; j < 500; j++) keep.Add(new byte[512]);
            GC.Collect(generation, GCCollectionMode.Forced, true);
            forced++;
            ran[GC.GetGCMemoryInfo(GCKind.Any).Generation]++;
            WaitPolls(3);
        }
        for (int i = 0; i < 6; i++) Force(i % 2);
        // A gen2 requested in the background (the runtime may run it blocking: .NET 10.0.0 background thread start race),
        // then a blocking one.
        long background = GC.GetGCMemoryInfo(GCKind.Background).Index, blocking = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
        GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
        var watch = System.Diagnostics.Stopwatch.StartNew();
        while (GC.GetGCMemoryInfo(GCKind.Background).Index == background && GC.GetGCMemoryInfo(GCKind.FullBlocking).Index == blocking &&
               watch.ElapsedMilliseconds < 10000) Thread.Sleep(20);
        string requestedBackground = GC.GetGCMemoryInfo(GCKind.Background).Index != background ? "background" :
            GC.GetGCMemoryInfo(GCKind.FullBlocking).Index != blocking ? "blocking" : "none";
        WaitPolls(2);
        GC.Collect(2, GCCollectionMode.Forced, true, true);
        WaitPolls(2);
        // At least two of each ephemeral generation ran (the runtime may have run a requested one older).
        for (int attempt = 0; attempt < 8 && (ran[0] < 2 || ran[1] < 2); attempt++) Force(ran[0] < 2 ? 0 : 1);
        Force(0);
        Force(1);
        Ryujinx.Common.BackgroundGcKeepAlive.Stop(2);
        var after = Counts();
        Thread.Sleep(400);
        report["real"] = new Dictionary<string, object> { ["journal"] = Since(lines), ["ranGen0"] = ran[0], ["ranGen1"] = ran[1],
            ["ranGen2"] = ran[2], ["forced"] = forced, ["requestedBackground"] = requestedBackground, ["countsBefore"] = new[] { before.Item1, before.Item2, before.Item3 },
            ["countsAfter"] = new[] { after.Item1, after.Item2, after.Item3 }, ["requests"] = _requests, ["kept"] = keep.Count };
        report["lineThresholdMs"] = Ryujinx.Common.BackgroundGcKeepAlive.PauseLineMs;
        report["maxPauseLines"] = Ryujinx.Common.BackgroundGcKeepAlive.MaxPauseLines;
        report["denseLines"] = Ryujinx.Common.BackgroundGcKeepAlive.DenseLines;
        report["lineStride"] = Ryujinx.Common.BackgroundGcKeepAlive.LineStride;
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }

}
