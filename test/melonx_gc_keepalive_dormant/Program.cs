// Fixture of adapt_gc_keepalive_dormant: the candidate's BackgroundGcKeepAlive (namespace Ryujinx.Common) and the
// control's (Core 721, namespace ControlKeepAlive), taken from their preparations by the gate, run their real loops on
// fake seams: clock, background record, heap, fragmentation, blocking record and the request are the fixture's. Each
// step sets the seams and waits for two polls of the loop.
using System;
using System.Collections.Generic;
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

namespace ControlKeepAlive
{
    using Ryujinx.Common;

//__CONTROL__
}

public static class Program
{
    private static readonly object Gate = new();
    private static long _clock, _index, _polls, _requests;
    private static double _fragmentation;

    private static void Install(bool candidate)
    {
        Func<long> index = () => { lock (Gate) { _polls++; return _index; } };
        Func<long> clock = () => { lock (Gate) return _clock; };
        Func<long> heap = () => 512L << 20;
        Func<double> fragmentation = () => { lock (Gate) return _fragmentation; };
        Func<long> blocking = () => 3;
        Action request = () => { lock (Gate) _requests++; };
        if (candidate)
        {
            Ryujinx.Common.BackgroundGcKeepAlive.ReadBackgroundIndex = index;
            Ryujinx.Common.BackgroundGcKeepAlive.ReadMilliseconds = clock;
            Ryujinx.Common.BackgroundGcKeepAlive.ReadHeapBytes = heap;
            Ryujinx.Common.BackgroundGcKeepAlive.ReadFragmentation = fragmentation;
            Ryujinx.Common.BackgroundGcKeepAlive.ReadBlockingIndex = blocking;
            Ryujinx.Common.BackgroundGcKeepAlive.RequestBackgroundCollection = request;
        }
        else
        {
            ControlKeepAlive.BackgroundGcKeepAlive.ReadBackgroundIndex = index;
            ControlKeepAlive.BackgroundGcKeepAlive.ReadMilliseconds = clock;
            ControlKeepAlive.BackgroundGcKeepAlive.ReadHeapBytes = heap;
            ControlKeepAlive.BackgroundGcKeepAlive.ReadFragmentation = fragmentation;
            ControlKeepAlive.BackgroundGcKeepAlive.ReadBlockingIndex = blocking;
            ControlKeepAlive.BackgroundGcKeepAlive.RequestBackgroundCollection = request;
        }
    }

    private static void Step(long clock, double fragmentation, long index)
    {
        long before;
        lock (Gate) { _clock = clock; _fragmentation = fragmentation; _index = index; before = _polls; }
        var watch = System.Diagnostics.Stopwatch.StartNew();
        while (watch.ElapsedMilliseconds < 5000)
        {
            lock (Gate) if (_polls >= before + 2) return;
            Thread.Sleep(20);
        }
        throw new TimeoutException("the loop did not poll");
    }

    // steps: (clock ms, fragmentation, background record index); the record starts at 7.
    private static Dictionary<string, object> Run(bool candidate, (long Clock, double Fragmentation, long Index)[] steps)
    {
        lock (Gate) { _clock = 0; _index = 7; _polls = 0; _requests = 0; _fragmentation = 0; }
        int lines;
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines) lines = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Count;
        Install(candidate);
        if (candidate) Ryujinx.Common.BackgroundGcKeepAlive.Start(1); else ControlKeepAlive.BackgroundGcKeepAlive.Start(1);
        Step(0, 0, 7);
        foreach (var (clock, fragmentation, index) in steps) Step(clock, fragmentation, index);
        long requestsCounted = candidate ? Ryujinx.Common.BackgroundGcKeepAlive.Requests : ControlKeepAlive.BackgroundGcKeepAlive.Requests;
        if (candidate) Ryujinx.Common.BackgroundGcKeepAlive.Stop(1); else ControlKeepAlive.BackgroundGcKeepAlive.Stop(1);
        Thread.Sleep(400);
        List<string> journal;
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines)
            journal = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.GetRange(lines, Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Count - lines);
        lock (Gate) return new Dictionary<string, object> { ["requests"] = _requests, ["requestsCounted"] = requestsCounted, ["journal"] = journal };
    }

    public static int Main()
    {
        var report = new Dictionary<string, object>();
        // S1, the board's control: the ratio held above 0.48 for 20 s from the window's start, then below; the runtime's
        // own background gen2 at 24 s; a window later the fragmentation is low.
        var hold = new (long, double, long)[]
        {
            (0, 0.60, 8), (13_000, 0.60, 8), (15_000, 0.60, 8), (17_000, 0.60, 8), (21_000, 0.60, 8), (33_000, 0.60, 8),
            (34_000, 0.30, 8), (35_000, 0.30, 9), (48_500, 0.30, 9),
        };
        report["controlHold"] = Run(false, hold);
        report["candidateHold"] = Run(true, hold);
        // S2: the fragmentation falls inside the window: the request is made, nothing dormant; another one 14 s later.
        var recovers = new (long, double, long)[] { (0, 0.60, 8), (13_000, 0.60, 8), (15_000, 0.30, 8), (17_000, 0.30, 8), (29_000, 0.30, 8) };
        report["candidateRecovers"] = Run(true, recovers);
        // S3: a window missed without any refusal (no poll inside it): a miss, not dormant.
        var missed = new (long, double, long)[] { (0, 0.10, 8), (11_000, 0.10, 8), (17_000, 0.10, 8) };
        report["candidateMissed"] = Run(true, missed);
        report["controlMissed"] = Run(false, missed);
        // S4: six windows in a row refused for fragmentation: six dormant windows, four lines.
        var repeated = new List<(long, double, long)>();
        for (int w = 0; w < 6; w++)
        {
            long start = w * 40_000L;
            repeated.Add((start, 0.70, 8 + w));
            repeated.Add((start + 13_000, 0.70, 8 + w));
            repeated.Add((start + 17_000, 0.70, 8 + w));
        }
        report["candidateBound"] = Run(true, repeated.ToArray());
        report["maxDormantLines"] = Ryujinx.Common.BackgroundGcKeepAlive.MaxDormantLines;
        report["limit"] = Ryujinx.Common.BackgroundGcKeepAlive.FragmentationLimit;
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
