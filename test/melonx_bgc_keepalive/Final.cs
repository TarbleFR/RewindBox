// Fixture of the bgc-keepalive gate on the final preparation (adapt_keepalive_after_ephemeral): the final
// EmbeddedSession.cs's keep-alive classes (KeepAliveMemoryHold and BackgroundGcKeepAlive, inserted below by the gate,
// unchanged; or the same text with that adapter's replacements undone, as control) run their real loop. The classes they
// call in other files are stubs that do nothing (the collection class, the stall compaction's poll, the device's memory).
// "simulated": a virtual clock and a scripted background record, ephemeral record, heap and fragmentation, read by every
// poll as they stood when it started (the stall compaction's poll stub, called once at the top of each poll, takes the
// snapshot); after each change the fixture waits for two polls to start, so the first poll that saw it has decided. "real": the production reads and the
// production request on the host .NET 10 runtime with a 448 MiB live heap, first with an ephemeral collection forced every
// 1.7 s, then with none. Prints one JSON line.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common;
using KeepAlive = Ryujinx.Library.BackgroundGcKeepAlive;

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
}

namespace Ryujinx.Memory
{
    public static class HostMemoryBudget
    {
        public static int DeviceAvailablePercent => -1;
    }
}

namespace Ryujinx.Library
{
    public static class CollectionClass
    {
        public static int Register() => 0;
        public static void MarkSession() { }
        public static void ReleaseAfterRestart() { }
        public static string Describe() => "stub";
    }

    internal static class EmbeddedHeapCompaction
    {
        internal static void OnPoll() => global::Program.PollStarted();
    }

//__KEEPALIVE__
}

public static class Program
{
    private static readonly object Gate = new();
    private static long _clock, _background = 7, _ephemeral = 100, _polls;
    private static double _fragmentation = 0.1;
    // The state as the current poll started.
    private static long _pollClock, _pollBackground = 7, _pollEphemeral = 100;
    private static double _pollFragmentation = 0.1;
    private static readonly List<long> Requests = new();

    public static void PollStarted()
    {
        lock (Gate)
        {
            _polls++;
            _pollClock = _clock;
            _pollBackground = _background;
            _pollEphemeral = _ephemeral;
            _pollFragmentation = _fragmentation;
        }
    }

    public static int Main(string[] args)
    {
        var report = new Dictionary<string, object>();
        if (args[0] == "simulated") Simulated(report);
        else Real(report);
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }

    private static List<string> Journal()
    {
        lock (EmbeddedLaunchDiagnostics.Lines)
        {
            var lines = new List<string>(EmbeddedLaunchDiagnostics.Lines);
            EmbeddedLaunchDiagnostics.Lines.Clear();
            return lines;
        }
    }

    // After a change of the scripted state: two polls start, so the first one (which took the whole new state) has decided.
    private static void Settle(long before)
    {
        var watch = Stopwatch.StartNew();
        while (watch.ElapsedMilliseconds < 5000)
        {
            lock (Gate) if (_polls >= before + 2) return;
            Thread.Sleep(10);
        }
        throw new TimeoutException("the loop did not poll");
    }

    private static void At(long clock, Action change = null)
    {
        long before;
        lock (Gate)
        {
            _clock = clock;
            change?.Invoke();
            before = _polls;
        }
        Settle(before);
    }

    private static List<long> RequestTimes()
    {
        lock (Gate) return new List<long>(Requests);
    }

    private static void Simulated(Dictionary<string, object> report)
    {
        Type type = typeof(KeepAlive);
        object latest = type.GetField("LatestRequestMs")?.GetRawConstantValue();
        var requestNow = type.GetMethod("RequestNow");
        report["latestRequestMs"] = latest;
        if (requestNow != null)
        {
            var policy = new Dictionary<string, bool>();
            foreach (long ms in new long[] { 12_000, 15_499, 15_500, 16_000 })
            {
                foreach (bool ended in new[] { false, true })
                {
                    policy[ms + (ended ? "ended" : "none")] = (bool)requestNow.Invoke(null, new object[] { ms, ended });
                }
            }
            report["requestNow"] = policy;
        }

        KeepAlive.ReadMilliseconds = () => { lock (Gate) return _pollClock; };
        KeepAlive.ReadBackgroundIndex = () => { lock (Gate) return _pollBackground; };
        KeepAlive.ReadHeapBytes = () => 512L << 20;
        KeepAlive.ReadFragmentation = () => { lock (Gate) return _pollFragmentation; };
        KeepAlive.ReadBlockingIndex = () => 3;
        KeepAlive.RequestBackgroundCollection = () => { lock (Gate) Requests.Add(_pollClock); };
        KeepAlive.ReadEphemeral = () => { lock (Gate) return new KeepAlive.EphemeralRecord(_pollEphemeral, 0, 1.0, 1L << 20, 16L << 20, 0, 0, 0, true); };

        Journal();
        KeepAlive.Start(11);
        At(0);
        var marks = new Dictionary<string, int>();
        // Window 1: the record changes at 1 s; an ephemeral collection 5 s later (before the window), none at 12 s and
        // 13 s, one 13.25 s after the change.
        At(1_000, () => _background = 8);
        At(6_000, () => _ephemeral++);
        At(13_000);
        marks["at12sWithoutEphemeral"] = RequestTimes().Count;
        At(14_000);
        At(14_250, () => _ephemeral++);
        marks["afterEphemeralAt13250"] = RequestTimes().Count;
        // Window 2: the requested gen2 changes the record at 15.25 s; an ephemeral collection 11.75 s later (before the
        // window), then none: nothing at 12 s or 15.25 s, a request at 15.5 s.
        At(15_250, () => _background = 9);
        At(27_000, () => _ephemeral++);
        At(27_250);
        At(30_500);
        marks["at15250WithoutEphemeral"] = RequestTimes().Count;
        At(30_750);
        // Window 3: the record changes at 31.75 s; at 44.25 s an ephemeral collection ends while the heap is too fragmented
        // (refused); at 44.5 s the fragmentation is low, no collection ended; at 44.75 s one ends.
        At(31_750, () => _background = 10);
        At(44_250, () => { _fragmentation = 0.6; _ephemeral++; });
        At(44_500, () => _fragmentation = 0.1);
        marks["fragmentedThenLow"] = RequestTimes().Count;
        At(44_750, () => _ephemeral++);
        // Window 4: the record changes at 46 s; no ephemeral collection; the keep-alive is held from 15.25 s to 16.25 s
        // after it (its window's last polls): the window is missed; then an ephemeral collection ends: nothing.
        At(46_000, () => _background = 11);
        At(61_250);
        At(62_250);
        At(67_250, () => _ephemeral++);
        KeepAlive.Stop(11);
        Thread.Sleep(600);
        report["marks"] = marks;
        report["requests"] = RequestTimes();
        report["journal"] = Journal();
    }

    // The production reads and request on the host runtime. An observer records when the runtime's ephemeral and
    // background records change (Stopwatch time); each request is stamped the same way.
    private static void Real(Dictionary<string, object> report)
    {
        var live = new List<object>();
        for (int i = 0; i < 448; i++)
        {
            var node = new object[16 * 1024]; // references, so a background mark has work
            for (int j = 0; j < node.Length; j += 64) node[j] = new byte[64];
            live.Add(node);
            live.Add(new byte[1 << 20]);
        }

        var clock = Stopwatch.StartNew();
        var ephemeralEnds = new List<long>();
        var backgroundChanges = new List<long>();
        var requests = new List<long>();
        bool observe = true;
        var observer = new Thread(() =>
        {
            long ephemeral = GC.GetGCMemoryInfo(GCKind.Ephemeral).Index, background = GC.GetGCMemoryInfo(GCKind.Background).Index;
            while (Volatile.Read(ref observe))
            {
                long e = GC.GetGCMemoryInfo(GCKind.Ephemeral).Index, b = GC.GetGCMemoryInfo(GCKind.Background).Index;
                lock (Gate)
                {
                    if (e != ephemeral) { ephemeral = e; ephemeralEnds.Add(clock.ElapsedMilliseconds); }
                    if (b != background) { background = b; backgroundChanges.Add(clock.ElapsedMilliseconds); }
                }
                Thread.Sleep(20); // few reads: each allocates its record, and the quiet phase must not cause an ephemeral collection
            }
        }) { IsBackground = true, Priority = ThreadPriority.AboveNormal };
        observer.Start();
        KeepAlive.RequestBackgroundCollection = () =>
        {
            lock (Gate) requests.Add(clock.ElapsedMilliseconds);
            GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
        };
        long startBackground = GC.GetGCMemoryInfo(GCKind.Background).Index;
        long startBlocking = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;

        Dictionary<string, object> Phase(long generation, int forceEveryMs, int seconds)
        {
            int before;
            lock (Gate) before = requests.Count;
            Journal();
            GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false); // the run's first background gen2
            KeepAlive.Start(generation);
            long started = clock.ElapsedMilliseconds, lastForced = started;
            while (clock.ElapsedMilliseconds - started < seconds * 1000L)
            {
                if (forceEveryMs > 0 && clock.ElapsedMilliseconds - lastForced >= forceEveryMs)
                {
                    GC.Collect(0, GCCollectionMode.Forced, blocking: true);
                    lastForced = clock.ElapsedMilliseconds;
                }
                Thread.Sleep(10);
            }
            KeepAlive.Stop(generation);
            Thread.Sleep(600);
            var made = new List<Dictionary<string, long>>();
            lock (Gate)
            {
                for (int i = before; i < requests.Count; i++)
                {
                    long at = requests[i], ended = -1, changed = -1;
                    foreach (long t in ephemeralEnds) if (t <= at) ended = t;
                    foreach (long t in backgroundChanges) if (t <= at) changed = t;
                    long endedInWindow = 0;
                    foreach (long t in ephemeralEnds) if (changed >= 0 && t > changed + 11_750 && t <= at) endedInWindow++;
                    made.Add(new Dictionary<string, long>
                    {
                        ["sinceEphemeralEnd"] = ended < 0 ? -1 : at - ended,
                        ["sinceBackgroundChange"] = changed < 0 ? -1 : at - changed,
                        ["ephemeralEndsInWindow"] = endedInWindow,
                    });
                }
            }
            return new Dictionary<string, object> { ["requests"] = made, ["journal"] = Journal() };
        }

        report["forced"] = Phase(21, 1_700, 40);
        report["quiet"] = Phase(22, 0, 20);
        Volatile.Write(ref observe, false);
        observer.Join();
        GC.KeepAlive(live);
        report["backgroundAdvanced"] = GC.GetGCMemoryInfo(GCKind.Background).Index - startBackground;
        report["blockingAdvanced"] = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index - startBlocking;
        report["heapMiB"] = GC.GetGCMemoryInfo().HeapSizeBytes >> 20;
        lock (Gate) report["ephemeralEnds"] = ephemeralEnds.Count;
    }
}
