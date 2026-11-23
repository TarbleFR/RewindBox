// Gate fixture of adapt_device_pressure_compaction: the production EmbeddedHeapCompaction class (EmbeddedMemory.cs of the
// variant, between its markers, unchanged) next to doubles of HostMemoryBudget (device share and process headroom set by
// the fixture, footprint = resident bytes), the launch journal, the render drain's age and the retention note, run with
// the host's segments GC library and the Core's GC settings.
// "before" (both variants): the IPA 822 situation: device at 8 %, the process 2.3 GB under its limit, a large object heap
// with about 240 MiB free after a sweep, a session presenting for 21 s, then a gap of 1.5 s: the control compacts nothing.
// "policy", "live", "detector", "bounds" (candidate): the rule at each limit; the same gap compacted once, inside it, with
// the existing line; refusals (interval, device not short or unknown, render drain, host pause, stop, background
// collection); the background-collection detector against a real background gen2; the bounds closing the rule; the
// session's summary line once; nothing after the session's end.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using Ryujinx.Library;

namespace Ryujinx.Memory
{
    public static class HostMemoryBudget
    {
        public static bool Constrained = true;
        public static bool IsConstrained => Constrained;
        public static int Device = 8;
        public static int DeviceAvailablePercent => Device;
        public static ulong FootprintBytes => (ulong)Environment.WorkingSet;
        public static ulong Available = 2300UL * 1024 * 1024;
        public static ulong AvailableBytes => Available;
    }
}

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Lines = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            lock (Lines) Lines.Add(stage + " " + status + ": " + detail);
        }
    }

    public static class EmbeddedPerformanceDiagnostics
    {
        public static long Drain = -1;
        public static long RenderDrainInFlightMs() => Volatile.Read(ref Drain);
    }
}

namespace Ryujinx.Library
{
    internal static class Library
    {
        internal static void RecordRetentionChain(string moment) { }
    }
}

static class Fixture
{
    const long MiB = 1024 * 1024;
    static readonly List<object> Live = new();
    static readonly List<byte[]> Holes = new();
    static bool Stopping;
    static readonly Dictionary<string, object> Report = new();

    static void Set(string field, object value) =>
        typeof(EmbeddedHeapCompaction).GetField(field, BindingFlags.NonPublic | BindingFlags.Static)!.SetValue(null, value);

    static object Get(string field) =>
        typeof(EmbeddedHeapCompaction).GetField(field, BindingFlags.NonPublic | BindingFlags.Static)!.GetValue(null);

    static long LohFree() => GC.GetGCMemoryInfo().GenerationInfo[3].FragmentationAfterBytes;
    static long Reclaimable() => EmbeddedHeapCompaction.ReclaimableBytes(GC.GetGCMemoryInfo());
    static int Compactions => Volatile.Read(ref EmbeddedHeapCompaction.Compactions);

    // A session's heap: small linked objects, then large arrays of 256 KiB to 2 MiB with every other one dying, swept by a
    // collection that does not compact (what the background collections do): the large object heap's holes.
    static void Fragment(int seed, long total)
    {
        Random random = new(seed);
        List<byte[]> all = new();
        long allocated = 0;
        while (allocated < total)
        {
            int size = 256 * 1024 * random.Next(1, 9);
            byte[] array = new byte[size];
            for (int i = 0; i < size; i += 4096) array[i] = 1;
            all.Add(array);
            allocated += size;
        }
        Holes.Clear();
        for (int i = 0; i < all.Count; i += 2) Holes.Add(all[i]);
        all.Clear();
        GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: false);
    }

    static void Play(int milliseconds)
    {
        long end = Environment.TickCount64 + milliseconds, nextPoll = Environment.TickCount64;
        while (Environment.TickCount64 < end)
        {
            EmbeddedHeapCompaction.NotePresented();
            if (Environment.TickCount64 >= nextPoll) { EmbeddedHeapCompaction.OnPoll(); nextPoll += 250; }
            Thread.Sleep(33);
        }
    }

    // Nothing presented: the poll alone every 250 ms. Returns ms from the last frame to the compaction, or -1.
    static long Stall(int milliseconds)
    {
        int before = Compactions;
        long start = Environment.TickCount64;
        while (Environment.TickCount64 - start < milliseconds)
        {
            Thread.Sleep(250);
            EmbeddedHeapCompaction.OnPoll();
            if (Compactions != before) return Environment.TickCount64 - start;
        }
        return -1;
    }

    // A session presenting for 21 s of its life (its first frame placed 21 s back), the last 0.6 s at 30 frames a second.
    static void Session()
    {
        EmbeddedHeapCompaction.WatchStalls(() => Volatile.Read(ref Stopping));
        EmbeddedHeapCompaction.NotePresented();
        Set("_firstPresent", Environment.TickCount64 - 21_000);
        Play(600);
    }

    static int Main(string[] args)
    {
        string variant = args[0];
        string gc = GC.GetConfigurationVariables().TryGetValue("GCName", out object name) ? name?.ToString() ?? "" : "";
        Report["gcName"] = gc;
        for (int i = 0; i < 400_000; i++) Live.Add(new object[] { i, new byte[200] });
        Fragment(1, 440 * MiB);
#if CANDIDATE
        Candidate();
#else
        // --- before: the IPA 822 situation (the candidate runs the same as "live") ---
        Session();
        long freeBefore = LohFree(), reclaimable = Reclaimable(), rssBefore = Environment.WorkingSet;
        long committedBefore = GC.GetGCMemoryInfo().TotalCommittedBytes;
        long waited = Stall(1500);
        GCMemoryInfo after = GC.GetGCMemoryInfo();
        Report["before"] = new Dictionary<string, object>
        {
            ["lohFreeBeforeMiB"] = freeBefore / MiB, ["reclaimableMiB"] = reclaimable / MiB, ["waitedMs"] = waited,
            ["lohFreeAfterMiB"] = after.GenerationInfo[3].FragmentationAfterBytes / MiB,
            ["committedBeforeMiB"] = committedBefore / MiB, ["committedAfterMiB"] = after.TotalCommittedBytes / MiB,
            ["rssBeforeMiB"] = rssBefore / MiB, ["rssAfterMiB"] = Environment.WorkingSet / MiB,
            ["compactions"] = Compactions, ["lines"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.ToList(),
        };
#endif
        Console.WriteLine(JsonSerializer.Serialize(Report));
        return 0;
    }

#if CANDIDATE
    static bool Rule(int device = 10, long free = 192 * MiB, long first = 20_000, long gap = 250, long drain = 124, long interval = 60_000,
        int done = 2, double paused = 599, bool closed = false, bool running = false, double predicted = 300) =>
        EmbeddedHeapCompaction.ShouldCompactUnderPressure(device, free, first, gap, drain, interval, done, paused, closed, running, predicted);

    static void Candidate()
    {
        Report["policy"] = new Dictionary<string, object>
        {
            ["limits"] = new[] { EmbeddedHeapCompaction.PressureDevicePercent, EmbeddedHeapCompaction.PressureGapMs, EmbeddedHeapCompaction.PressureDrainMs,
                (int)(EmbeddedHeapCompaction.PressureReclaimableBytes / MiB), (int)EmbeddedHeapCompaction.PressureAfterFirstFrameMs,
                (int)EmbeddedHeapCompaction.PressureIntervalMs, EmbeddedHeapCompaction.PressureMaxPerSession,
                (int)EmbeddedHeapCompaction.PressureSinglePauseMs, (int)EmbeddedHeapCompaction.PressurePauseBudgetMs,
                (int)(EmbeddedHeapCompaction.PressureMinimumGainBytes / MiB) },
            ["atEveryLimit"] = Rule(), ["device11"] = Rule(device: 11), ["deviceUnknown"] = Rule(device: -1), ["device0"] = Rule(device: 0),
            ["free191"] = Rule(free: 191 * MiB), ["firstFrame19999"] = Rule(first: 19_999), ["gap249"] = Rule(gap: 249),
            ["drain125"] = Rule(drain: 125), ["noDrain"] = Rule(drain: -1), ["interval59999"] = Rule(interval: 59_999),
            ["third"] = Rule(done: 2), ["fourth"] = Rule(done: 3), ["paused600"] = Rule(paused: 600), ["closed"] = Rule(closed: true),
            ["backgroundRunning"] = Rule(running: true), ["neverCompacted"] = Rule(interval: long.MaxValue),
            ["predicted301"] = Rule(predicted: 301),
            ["defaultMsPerLiveMiB"] = EmbeddedHeapCompaction.PressureDefaultMsPerLiveMiB,
        };

        // --- live: the same gap compacted once, inside it ---
        Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Clear();
        Session();
        long freeBefore = LohFree(), rssBefore = Environment.WorkingSet;
        long committedBefore = GC.GetGCMemoryInfo().TotalCommittedBytes;
        double predictedFirst = EmbeddedHeapCompaction.PredictedPauseMs(GC.GetGCMemoryInfo());
        Stopwatch clock = Stopwatch.StartNew();
        long waited = Stall(1500);
        GCMemoryInfo after = GC.GetGCMemoryInfo(GCKind.FullBlocking);
        Dictionary<string, object> live = new()
        {
            ["waitedMs"] = waited, ["lohFreeBeforeMiB"] = freeBefore / MiB, ["lohFreeAfterMiB"] = after.GenerationInfo[3].FragmentationAfterBytes / MiB,
            ["committedBeforeMiB"] = committedBefore / MiB, ["committedAfterMiB"] = after.TotalCommittedBytes / MiB,
            ["rssBeforeMiB"] = rssBefore / MiB, ["rssAfterMiB"] = Environment.WorkingSet / MiB,
            ["pauseMs"] = after.PauseDurations[0].TotalMilliseconds, ["pressureCompactions"] = EmbeddedHeapCompaction.PressureCompactions,
            ["lohLiveAfterMiB"] = (after.GenerationInfo[3].SizeAfterBytes - after.GenerationInfo[3].FragmentationAfterBytes) / MiB,
            ["gen2LiveAfterMiB"] = (after.GenerationInfo[2].SizeAfterBytes - after.GenerationInfo[2].FragmentationAfterBytes) / MiB,
            ["predictedPauseMs"] = Math.Round(predictedFirst, 1), ["msPerLiveMiBAfter"] = Math.Round((double)Get("_msPerLiveMiB"), 4),
        };

        // Refusals: the interval (a second fragmented heap, 60 s not passed), then with the interval past: the device not
        // short or unknown, a render drain, a host pause, a stop request.
        Fragment(2, 440 * MiB);
        Play(600);
        live["interval"] = Stall(1000);
        Set("_lastCompaction", Environment.TickCount64 - 61_000);
        Ryujinx.Memory.HostMemoryBudget.Device = 11;
        Play(300);
        live["device11"] = Stall(1000);
        Ryujinx.Memory.HostMemoryBudget.Device = -1;
        Play(300);
        live["deviceUnknown"] = Stall(1000);
        Ryujinx.Memory.HostMemoryBudget.Device = 8;
        Volatile.Write(ref Ryujinx.Common.EmbeddedPerformanceDiagnostics.Drain, 200);
        Play(300);
        live["drain"] = Stall(1000);
        Volatile.Write(ref Ryujinx.Common.EmbeddedPerformanceDiagnostics.Drain, -1);
        Play(300);
        EmbeddedHeapCompaction.OnHostPause(true, () => Volatile.Read(ref Stopping));
        live["hostPause"] = Stall(1000);
        EmbeddedHeapCompaction.BeforeResume();
        EmbeddedHeapCompaction.OnHostPause(false, () => Volatile.Read(ref Stopping));
        Play(300);
        Volatile.Write(ref Stopping, true);
        live["stopping"] = Stall(1000);
        Volatile.Write(ref Stopping, false);
        live["freeStillMiB"] = Reclaimable() / MiB;

        // A background gen2 in progress: refused while it runs (a blocking collection asked then would wait for it). With
        // ConserveMemory 5 a gen2 asked above 50 % of fragmentation runs blocking and compacting (adapt_bgc_fragmentation
        // _guard): long-lived large objects bring the heap under it, as a session's heap is (IPA 822: 0.28-0.30).
        for (int i = 0; i < 1_500_000; i++) Live.Add(new object[] { i });
        for (int i = 0; i < 480; i++) { byte[] array = new byte[1 << 20]; for (int j = 0; j < array.Length; j += 4096) array[j] = 1; Live.Add(array); }
        live["fragmentationAtBackground"] = Math.Round((double)GC.GetGCMemoryInfo().FragmentedBytes / GC.GetGCMemoryInfo().HeapSizeBytes, 3);
        Play(300);
        Thread.Sleep(260);
        int refusedBefore = (int)Get("_refusedBackground");
        long backgroundIndex = GC.GetGCMemoryInfo(GCKind.Background).Index;
        int compactionsBefore = Compactions;
        GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
        Thread.Sleep(2);
        EmbeddedHeapCompaction.OnPoll();
        bool endedAtPoll = GC.GetGCMemoryInfo(GCKind.Background).Index != backgroundIndex;
        live["backgroundRefused"] = (int)Get("_refusedBackground") - refusedBefore;
        live["backgroundEndedAtPoll"] = endedAtPoll;
        Thread.Sleep(1500);
        live["backgroundRanConcurrently"] = GC.GetGCMemoryInfo(GCKind.Background).Index != backgroundIndex;
        live["blockingInstead"] = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index > backgroundIndex && !(bool)live["backgroundRanConcurrently"];
        live["compactedDuringBackground"] = Compactions != compactionsBefore && !endedAtPoll;

        // A heap whose compaction this session's ratio predicts over 300 ms: refused before it pauses.
        Fragment(4, 440 * MiB);
        Set("_lastCompaction", Environment.TickCount64 - 61_000);
        Play(300);
        int predictedBefore = (int)Get("_refusedPredicted");
        live["predictedLarge"] = Math.Round(EmbeddedHeapCompaction.PredictedPauseMs(GC.GetGCMemoryInfo()), 1);
        live["predictedRefusal"] = Stall(1000);
        live["predictedRefused"] = (int)Get("_refusedPredicted") - predictedBefore;
        Live.RemoveAll(o => o is byte[] || (o is object[] cell && cell.Length == 1));
        Report["live"] = live;

        // --- the detector against a real background gen2 (polled every millisecond) ---
        Set("_gen2Baseline", -1L);
        EmbeddedHeapCompaction.BackgroundCollectionRunning();
        long index = GC.GetGCMemoryInfo(GCKind.Background).Index;
        GC.Collect(2, GCCollectionMode.Forced, blocking: false, compacting: false);
        int seenRunning = 0, wrongAfterEnd = 0, polls = 0;
        Stopwatch watch = Stopwatch.StartNew();
        while (watch.ElapsedMilliseconds < 5000)
        {
            bool running = EmbeddedHeapCompaction.BackgroundCollectionRunning();
            bool ended = GC.GetGCMemoryInfo(GCKind.Background).Index != index;
            polls++;
            seenRunning += running && !ended ? 1 : 0;
            if (ended)
            {
                Thread.Sleep(5);
                for (int i = 0; i < 50; i++) { wrongAfterEnd += EmbeddedHeapCompaction.BackgroundCollectionRunning() ? 1 : 0; Thread.Sleep(1); }
                break;
            }
            Thread.Sleep(1);
        }
        Report["detector"] = new Dictionary<string, object> { ["seenRunning"] = seenRunning, ["wrongAfterEnd"] = wrongAfterEnd, ["polls"] = polls,
            ["ended"] = GC.GetGCMemoryInfo(GCKind.Background).Index != index, ["ms"] = watch.ElapsedMilliseconds };

        // --- bounds: what closes the rule for the session ---
        Dictionary<string, object> bounds = new();
        void Note(double pause, long gain)
        {
            Set("_lastPauseMs", pause);
            Set("_lastCommittedGainBytes", gain);
            typeof(EmbeddedHeapCompaction).GetMethod("NotePressureCompaction", BindingFlags.NonPublic | BindingFlags.Static)!.Invoke(null, null);
        }
        Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Clear();
        EmbeddedHeapCompaction.WatchStalls(() => false);
        Note(310, 200 * MiB);
        bounds["longPause"] = EmbeddedHeapCompaction.PressureClosed;
        EmbeddedHeapCompaction.WatchStalls(() => false);
        bounds["reopened"] = !EmbeddedHeapCompaction.PressureClosed && EmbeddedHeapCompaction.PressureCompactions == 0;
        Note(100, 63 * MiB);
        bounds["littleGiven"] = EmbeddedHeapCompaction.PressureClosed;
        EmbeddedHeapCompaction.WatchStalls(() => false);
        Note(290, 200 * MiB);
        bool openAfterOne = !EmbeddedHeapCompaction.PressureClosed;
        Note(290, 200 * MiB);
        bool openAfterTwo = !EmbeddedHeapCompaction.PressureClosed;
        Note(30, 200 * MiB);
        bounds["budget"] = openAfterOne && openAfterTwo && EmbeddedHeapCompaction.PressureClosed;
        bounds["closedLines"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Where(l => l.StartsWith("memory pressureCompactionClosed: ")).ToList();
        Report["bounds"] = bounds;

        // --- the session's end: one summary line, then nothing ---
        Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Clear();
        Session();
        Fragment(3, 440 * MiB);
        Set("_lastCompaction", Environment.TickCount64 - 61_000);
        Play(300);
        long third = Stall(1500);
        EmbeddedHeapCompaction.OnSessionEnd();
        EmbeddedHeapCompaction.OnSessionEnd();
        Set("_lastCompaction", Environment.TickCount64 - 61_000);
        long afterEnd = Stall(1000);
        Report["end"] = new Dictionary<string, object>
        {
            ["compactedInSession"] = third, ["afterEnd"] = afterEnd,
            ["lines"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.ToList(),
        };

        // At the critical process headroom the presentation-gap rule decides, as before: its compaction at 700 ms of gap.
        Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Clear();
        Session();
        Fragment(5, 440 * MiB);
        Set("_lastCompaction", Environment.TickCount64 - 61_000);
        Ryujinx.Memory.HostMemoryBudget.Available = 256UL * 1024 * 1024;
        Play(300);
        long critical = Stall(1500);
        Report["criticalHeadroom"] = new Dictionary<string, object>
        {
            ["waitedMs"] = critical, ["pressureCompactions"] = EmbeddedHeapCompaction.PressureCompactions,
            ["lines"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Where(l => l.Contains("heapCompacted")).Select(l => l.Substring(0, Math.Min(60, l.Length))).ToList(),
        };
    }
#endif
}
