// Host probe: does a requested background gen2 run as a blocking one (the equal-index signature of
// gc.cpp do_pre_gc + the WKS "!!bgc_thread" start check) when the background GC thread must be created,
// i.e. at the first background GC of the process and after the thread's 20 s idle exit?
// Prints one JSON line per trial. Usage: probe <idleTrials> <idleSeconds> <warmTrials>
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;

static class Probe
{
    static readonly List<object> Keep = new();

    // The BGC thread's name on Linux (CoreCLR and NativeAOT both name it ".NET BGC").
    static int BgcThreads()
    {
        int count = 0;
        foreach (string task in Directory.EnumerateDirectories("/proc/self/task"))
        {
            try { if (File.ReadAllText(Path.Combine(task, "comm")).Trim() == ".NET BGC") count++; } catch { }
        }
        return count;
    }

    static Dictionary<string, object> Trial(string kind)
    {
        int threadsBefore = BgcThreads();
        long bg0 = GC.GetGCMemoryInfo(GCKind.Background).Index, fb0 = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
        // A non-blocking induced gen2 goes through the same garbage_collect start decision as a budget-triggered one.
        GC.Collect(2, GCCollectionMode.Default, blocking: false);
        SpinWait.SpinUntil(() => GC.GetGCMemoryInfo(GCKind.Background).Index != bg0 ||
                                 GC.GetGCMemoryInfo(GCKind.FullBlocking).Index != fb0, 5000);
        // Let a real background collection finish before reading its record.
        SpinWait.SpinUntil(() => GC.GetGCMemoryInfo(GCKind.Background).Index != bg0 &&
                                 GC.GetGCMemoryInfo(GCKind.Background).Index ==
                                 GC.GetGCMemoryInfo().Index || GC.GetGCMemoryInfo(GCKind.FullBlocking).Index != fb0, 5000);
        GCMemoryInfo bg = GC.GetGCMemoryInfo(GCKind.Background), fb = GC.GetGCMemoryInfo(GCKind.FullBlocking);
        string outcome = fb.Index != fb0 && fb.Index == bg.Index ? "fallback"
            : bg.Index != bg0 ? "background" : fb.Index != fb0 ? "blocking" : "none";
        return new Dictionary<string, object>
        {
            ["trial"] = kind, ["outcome"] = outcome, ["bgcThreadsBefore"] = threadsBefore,
            ["bgcThreadsAfter"] = BgcThreads(), ["backgroundIndex"] = bg.Index, ["fullBlockingIndex"] = fb.Index,
            ["fullBlockingPauseMs"] = Math.Round(fb.PauseDurations[0].TotalMilliseconds, 3),
        };
    }

    static int Main(string[] args)
    {
        int idleTrials = int.Parse(args[0]), idleSeconds = int.Parse(args[1]), warmTrials = int.Parse(args[2]);
        // ~64 MB of promoted survivors so every background gen2 has marking to do.
        for (int i = 0; i < 64 * 1024; i++) Keep.Add(new byte[1000]);
        var trials = new List<Dictionary<string, object>> { Trial("first") };
        for (int i = 0; i < warmTrials; i++) { Thread.Sleep(2000); trials.Add(Trial("warm2s")); }
        for (int i = 0; i < idleTrials; i++) { Thread.Sleep(idleSeconds * 1000); trials.Add(Trial($"idle{idleSeconds}s")); }
        foreach (var t in trials) Console.WriteLine(JsonSerializer.Serialize(t));
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object>
        {
            ["runtime"] = Environment.Version.ToString(), ["framework"] = System.Runtime.InteropServices.RuntimeInformation.FrameworkDescription,
            ["serverGC"] = System.Runtime.GCSettings.IsServerGC, ["latency"] = System.Runtime.GCSettings.LatencyMode.ToString(),
            ["gcName"] = Environment.GetEnvironmentVariable("DOTNET_GCName") ?? "",
        }));
        GC.KeepAlive(Keep);
        return 0;
    }
}
