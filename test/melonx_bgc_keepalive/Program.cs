// Fixture of adapt_bgc_keepalive: the candidate's BackgroundGcKeepAlive class (inserted below by the gate, from the
// final preparation's EmbeddedPerformanceDiagnostics.cs) runs (1) its policy table, (2) its real loop on fake seams
// (clock, background record, heap) and (3) its real loop on the host .NET 10 runtime with a large live heap.
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

//__CLASS__
}

public static class Program
{
    private static readonly Dictionary<string, object> Report = new();

    public static int Main()
    {
        Policy();
        Simulated();
        Real();
        Console.WriteLine(JsonSerializer.Serialize(Report));
        return 0;
    }

    private static void Policy()
    {
        const long big = 512L << 20, small = 128L << 20;
        var table = new Dictionary<string, string>
        {
            ["none"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(-1, big).ToString(),
            ["0"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(0, big).ToString(),
            ["11999"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(11_999, big).ToString(),
            ["12000"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(12_000, big).ToString(),
            ["16000"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(16_000, big).ToString(),
            ["16001"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(16_001, big).ToString(),
            ["30000"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(30_000, big).ToString(),
            ["14000small"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, small).ToString(),
            ["14000at384"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, 384L << 20).ToString(),
        };
        Report["policy"] = table;
    }

    // The real loop on fake seams: a virtual clock advanced by the fixture, a background record the fixture changes.
    private static void Simulated()
    {
        long clock = 0, index = 7, heap = 512L << 20;
        var requests = new List<long>();
        var gate = new object();
        Ryujinx.Common.BackgroundGcKeepAlive.ReadMilliseconds = () => { lock (gate) return clock; };
        Ryujinx.Common.BackgroundGcKeepAlive.ReadBackgroundIndex = () => { lock (gate) return index; };
        Ryujinx.Common.BackgroundGcKeepAlive.ReadHeapBytes = () => { lock (gate) return heap; };
        Ryujinx.Common.BackgroundGcKeepAlive.RequestBackgroundCollection = () => { lock (gate) requests.Add(clock); };

        Ryujinx.Common.BackgroundGcKeepAlive.Start(1);
        // Each fixture step moves the virtual clock 250 ms and lets the loop take at least one poll.
        void Advance(long ms)
        {
            for (long t = 0; t < ms; t += 250)
            {
                lock (gate) clock += 250;
                Thread.Sleep(Ryujinx.Common.BackgroundGcKeepAlive.PollMs + 60);
            }
        }

        Advance(20_000);                          // no background gen2 seen yet: nothing is asked
        int beforeFirst = Count(requests, gate);
        lock (gate) index++;                       // a background gen2 starts at t = 20 s
        Advance(11_000);                           // 11 s later: still waiting
        int at11 = Count(requests, gate);
        Advance(3_000);                            // inside the window: one request
        int at14 = Count(requests, gate);
        lock (gate) index++;                       // the requested background gen2 starts
        Advance(16_000);                           // a second request about 12-13 s after it
        int second = Count(requests, gate);
        lock (gate) { index++; heap = 128L << 20; } // a small heap: no request
        Advance(15_000);
        int smallHeap = Count(requests, gate);
        lock (gate) { index++; heap = 512L << 20; }
        Advance(250);                              // the loop sees that background gen2
        // A paused loop (the clock jumps 25 s between two polls): the window is missed, nothing is asked.
        lock (gate) clock += 25_000;
        Advance(5_000);
        int missed = Count(requests, gate);
        Ryujinx.Common.BackgroundGcKeepAlive.Stop(1);
        Thread.Sleep(600);
        int afterStop = Count(requests, gate);
        long firstAt, secondAt;
        lock (gate) { firstAt = requests.Count > 0 ? requests[0] : -1; secondAt = requests.Count > 1 ? requests[1] : -1; }

        string[] lines;
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines) lines = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.ToArray();
        Report["simulated"] = new Dictionary<string, object>
        {
            ["beforeFirst"] = beforeFirst, ["at11"] = at11, ["at14"] = at14, ["second"] = second,
            ["smallHeap"] = smallHeap, ["missed"] = missed, ["afterStop"] = afterStop,
            ["firstAtMs"] = firstAt, ["secondAtMs"] = secondAt, ["lines"] = lines,
        };
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines) Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Clear();
    }

    private static int Count(List<long> list, object gate) { lock (gate) return list.Count; }

    // The real loop on the host runtime: a 448 MiB live heap, steady small allocations, 45 s.
    private static void Real()
    {
        Ryujinx.Common.BackgroundGcKeepAlive.ReadMilliseconds = static () => Environment.TickCount64;
        Ryujinx.Common.BackgroundGcKeepAlive.ReadBackgroundIndex = static () => GC.GetGCMemoryInfo(GCKind.Background).Index;
        Ryujinx.Common.BackgroundGcKeepAlive.ReadHeapBytes = static () => GC.GetGCMemoryInfo().HeapSizeBytes;
        long requested = 0;
        Ryujinx.Common.BackgroundGcKeepAlive.RequestBackgroundCollection = () =>
        {
            Interlocked.Increment(ref requested);
            GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
        };

        var live = new List<object>();
        for (int i = 0; i < 448; i++)
        {
            var node = new object[16 * 1024]; // references, so a background mark has work
            for (int j = 0; j < node.Length; j += 64) node[j] = new byte[64];
            live.Add(node);
            live.Add(new byte[1 << 20]);
        }
        GC.Collect(2, GCCollectionMode.Forced, blocking: false); // the session's first background gen2
        Thread.Sleep(500);

        long startBackground = GC.GetGCMemoryInfo(GCKind.Background).Index;
        long startBlocking = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
        int startGen2 = GC.CollectionCount(2);
        Ryujinx.Common.BackgroundGcKeepAlive.Start(2);
        var started = Environment.TickCount64;
        var churn = new object[4096];
        int k = 0;
        while (Environment.TickCount64 - started < 45_000)
        {
            churn[k++ % churn.Length] = new byte[256]; // gen0 traffic only
            if ((k & 0xFFF) == 0) Thread.Sleep(2);
        }
        Ryujinx.Common.BackgroundGcKeepAlive.Stop(2);
        Thread.Sleep(600);
        GC.KeepAlive(live);

        string[] lines;
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines) lines = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.ToArray();
        Report["real"] = new Dictionary<string, object>
        {
            ["requested"] = Interlocked.Read(ref requested),
            ["backgroundAdvanced"] = GC.GetGCMemoryInfo(GCKind.Background).Index - startBackground,
            ["blockingAdvanced"] = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index - startBlocking,
            ["gen2Collections"] = GC.CollectionCount(2) - startGen2,
            ["heapMiB"] = GC.GetGCMemoryInfo().HeapSizeBytes >> 20,
            ["concurrent"] = System.Runtime.GCSettings.LatencyMode.ToString(),
            ["lines"] = lines,
        };
    }
}
