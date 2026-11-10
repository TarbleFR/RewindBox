// Fixture of adapt_bgc_fragmentation_guard: the candidate's BackgroundGcKeepAlive (namespace Ryujinx.Common) and the
// control's (Core 717, namespace ControlKeepAlive), both taken from their preparations by the gate, run on the host
// .NET 10 runtime with System.GC.ConserveMemory 5 (the Core's setting): their real loops ask on a fragmented heap
// (gen2 + LOH ratio above 0.5) and on a compact one; the clock and the background record are fakes, the GC is real.
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
    private static readonly Dictionary<string, object> Report = new();
    private static List<object> _held = new();

    private static double Ratio()
    {
        var g = GC.GetGCMemoryInfo().GenerationInfo;
        long size = g[2].SizeAfterBytes + g[3].SizeAfterBytes;
        return size == 0 ? 0 : (double)(g[2].FragmentationAfterBytes + g[3].FragmentationAfterBytes) / size;
    }

    // About 300 MiB of LOH arrays and 180 MiB of small objects in gen2, then a share of them dropped and swept by a
    // background gen2 (no compaction): the free space stays as fragmentation, as on the device.
    private static double MakeHeap(double keep)
    {
        _held = null;
        GC.Collect(2, GCCollectionMode.Forced, true, true);
        var loh = new List<object>(); var soh = new List<object>();
        for (int i = 0; i < 1200; i++) loh.Add(new byte[256 * 1024]);
        for (int i = 0; i < 2_000_000; i++) soh.Add(new byte[64]);
        GC.Collect(2, GCCollectionMode.Forced, true, false);
        GC.Collect(2, GCCollectionMode.Forced, true, false);
        var random = new Random(1);
        for (int i = 0; i < loh.Count; i++) if (random.NextDouble() > keep) loh[i] = null;
        for (int i = 0; i < soh.Count; i++) if (random.NextDouble() > keep) soh[i] = null;
        GC.Collect(2, GCCollectionMode.Forced, false, false);
        Thread.Sleep(2000);
        _held = new List<object> { loh, soh };
        return Ratio();
    }

    // One window of the real loop: the background record changes at clock 0, the clock jumps to 13 s (inside the
    // 12-16 s window); the GC, the heap and the fragmentation read are the runtime's.
    private static Dictionary<string, object> Window(bool candidate, double keep, Func<double> fragmentationOverride = null)
    {
        double ratio = MakeHeap(keep);
        long clock = 0, index = 7;
        var gate = new object();
        long blocking = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index, background = GC.GetGCMemoryInfo(GCKind.Background).Index;
        bool compacted = false;
        int lines = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Count;
        if (candidate)
        {
            Ryujinx.Common.BackgroundGcKeepAlive.ReadMilliseconds = () => { lock (gate) return clock; };
            Ryujinx.Common.BackgroundGcKeepAlive.ReadBackgroundIndex = () => { lock (gate) return index; };
            if (fragmentationOverride != null) Ryujinx.Common.BackgroundGcKeepAlive.ReadFragmentation = fragmentationOverride;
            Ryujinx.Common.BackgroundGcKeepAlive.Start(1);
        }
        else
        {
            ControlKeepAlive.BackgroundGcKeepAlive.ReadMilliseconds = () => { lock (gate) return clock; };
            ControlKeepAlive.BackgroundGcKeepAlive.ReadBackgroundIndex = () => { lock (gate) return index; };
            ControlKeepAlive.BackgroundGcKeepAlive.Start(1);
        }
        Thread.Sleep(700);
        lock (gate) index = 8;           // a background gen2 started: the window opens
        Thread.Sleep(700);
        lock (gate) clock = 13_000;      // 13 s later
        Thread.Sleep(2500);
        long requests = candidate ? Ryujinx.Common.BackgroundGcKeepAlive.Requests : ControlKeepAlive.BackgroundGcKeepAlive.Requests;
        if (candidate) Ryujinx.Common.BackgroundGcKeepAlive.Stop(1); else ControlKeepAlive.BackgroundGcKeepAlive.Stop(1);
        var full = GC.GetGCMemoryInfo(GCKind.FullBlocking);
        if (full.Index != blocking) compacted = full.Compacted;
        List<string> journal;
        lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines) journal = Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.GetRange(lines, Ryujinx.Common.EmbeddedLaunchDiagnostics.Lines.Count - lines);
        if (candidate) Ryujinx.Common.BackgroundGcKeepAlive.ReadFragmentation =
            static () => Ryujinx.Common.BackgroundGcKeepAlive.FragmentationOf(GC.GetGCMemoryInfo());
        return new Dictionary<string, object>
        {
            ["ratio"] = Math.Round(ratio, 3),
            ["requests"] = requests,
            ["blockingAdded"] = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index - blocking,
            ["blockingPauseMs"] = full.Index != blocking ? Math.Round(full.PauseDurations[0].TotalMilliseconds, 1) : 0,
            ["compacted"] = compacted,
            ["backgroundAdded"] = GC.GetGCMemoryInfo(GCKind.Background).Index - background,
            ["journal"] = journal,
        };
    }

    public static int Main()
    {
        const long big = 512L << 20, small = 128L << 20;
        Report["limit"] = Ryujinx.Common.BackgroundGcKeepAlive.FragmentationLimit;
        Report["policy"] = new Dictionary<string, string>
        {
            ["14000/0.60"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, big, 0.60).ToString(),
            ["14000/0.49"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, big, 0.49).ToString(),
            ["14000/0.47"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, big, 0.47).ToString(),
            ["14000/0.0"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, big, 0.0).ToString(),
            ["11999/0.9"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(11_999, big, 0.9).ToString(),
            ["30000/0.9"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(30_000, big, 0.9).ToString(),
            ["none/0.9"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(-1, big, 0.9).ToString(),
            ["small/0.9"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, small, 0.9).ToString(),
            ["2arg"] = Ryujinx.Common.BackgroundGcKeepAlive.Decide(14_000, big).ToString(),
        };
        Report["controlFragmented"] = Window(false, 0.35);
        Report["candidateFragmented"] = Window(true, 0.35);
        Report["candidateCompact"] = Window(true, 0.7);
        Report["candidateAttribution"] = Window(true, 0.35, () => 0.1);  // the guard misled: the request runs blocking
        Console.WriteLine(JsonSerializer.Serialize(Report));
        return 0;
    }
}
