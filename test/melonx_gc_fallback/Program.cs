using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;
using Journal = Ryujinx.Common.EmbeddedLaunchDiagnostics;

// Test-only seam: the driver rewrites the collector's GC.GetGCMemoryInfo and GC.CollectionCount calls (control and
// candidate alike) to these, which return the runtime's own values unless an override is installed.
static class GcFeed
{
    public static Func<GCKind, GCMemoryInfo> Override;
    public static GCMemoryInfo GetGCMemoryInfo() => GC.GetGCMemoryInfo();
    public static GCMemoryInfo GetGCMemoryInfo(GCKind kind) => Override != null ? Override(kind) : GC.GetGCMemoryInfo(kind);
    public static int CollectionCount(int generation) => GC.CollectionCount(generation);
}

// Runs the real collector and journal (control or candidate source, the same program for both) through the device
// signature of a background gen2 that fell back to a blocking one (.NET 10.0.0 do_pre_gc stamps the background record
// with the blocking collection's index and leaves an earlier background collection's payload in it): the blocking
// information is the runtime's own for a real forced collection, the background information is the runtime's own
// latest background collection with only its index set to the blocking one's. Reports what the Core journal received.
static class GcFallbackProgram
{
    static readonly BindingFlags PrivateStatic = BindingFlags.NonPublic | BindingFlags.Static;
    static string core;
    static long generation;
    static readonly List<byte[]> Survivors = new();

    static object Current => typeof(PD).GetField("_current", PrivateStatic).GetValue(null);
    static void Due()
    {
        object epoch = Current;
        epoch.GetType().GetField("PreviousTimestamp", BindingFlags.Public | BindingFlags.Instance)
            .SetValue(epoch, Stopwatch.GetTimestamp() - Stopwatch.Frequency * 6);
    }
    static void Poll() { Due(); PD.Poll(generation); }

    static List<JsonElement> GcLines()
    {
        var lines = new List<JsonElement>();
        if (!File.Exists(core)) return lines;
        foreach (string line in File.ReadAllLines(core))
        {
            using var doc = JsonDocument.Parse(line.Substring(line.IndexOf('{')));
            if (doc.RootElement.GetProperty("stage").GetString() != "gcEvent") continue;
            using var detail = JsonDocument.Parse(doc.RootElement.GetProperty("diagnostic").GetString());
            lines.Add(detail.RootElement.Clone());
        }
        return lines;
    }

    static bool Background()
    {
        long before = GC.GetGCMemoryInfo(GCKind.Background).Index;
        for (int attempt = 0; attempt < 5; attempt++)
        {
            GC.Collect(2, GCCollectionMode.Default, blocking: false);
            if (SpinWait.SpinUntil(() => GC.GetGCMemoryInfo(GCKind.Background).Index != before, 1000)) return true;
        }
        return false;
    }

    // This host's own runtime produced the signature (a background gen2 that ran blocking): both records share the index.
    static bool HostFallback() => GC.GetGCMemoryInfo(GCKind.Background).Index == GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;

    static long Blocking()
    {
        GC.Collect(2, GCCollectionMode.Forced, blocking: true, compacting: true);
        return GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
    }

    // The runtime's latest background information, a fresh object each call, with its index stamped to `index`.
    static GCMemoryInfo Stamped(long index)
    {
        GCMemoryInfo info = GC.GetGCMemoryInfo(GCKind.Background);
        object data = typeof(GCMemoryInfo).GetField("_data", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(info);
        data.GetType().GetField("_index", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(data, index);
        return info;
    }

    static void StampBackground(long index) =>
        GcFeed.Override = kind => kind == GCKind.Background ? Stamped(index) : GC.GetGCMemoryInfo(kind);

    static object Describe(IEnumerable<JsonElement> lines) => lines.Select(line => new Dictionary<string, object>
    {
        ["kind"] = line.GetProperty("kind").GetString(),
        ["index"] = line.GetProperty("index").GetInt64(),
        ["finalSample"] = line.GetProperty("finalSample").GetBoolean(),
        ["concurrent"] = line.GetProperty("concurrent").GetInt32(),
        ["pauseMs0"] = line.GetProperty("pauseMs")[0].GetDouble(),
        ["suppressedLines"] = line.GetProperty("suppressedLines").GetInt32(),
        ["kindLine"] = line.GetProperty("kindLine").GetInt32(),
        ["fellBackFromBackground"] = line.TryGetProperty("fellBackFromBackground", out JsonElement flag) ? flag.GetInt32() : -1,
        ["fallbacksInSession"] = line.TryGetProperty("fallbacksInSession", out JsonElement count) ? count.GetInt32() : -1,
        ["lohOccupiedAfterBytes"] = line.TryGetProperty("lohOccupiedAfterBytes", out JsonElement loh) ? loh.GetInt64() : -1,
        ["lohSizeAfterBytes"] = line.GetProperty("loh")[2].GetInt64(),
        ["lohFreeAfterBytes"] = line.GetProperty("loh")[3].GetInt64(),
    }).ToList();

    static int Main()
    {
        string root = Path.Combine(Path.GetTempPath(), "melonx-gc-fallback-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            core = Path.Combine(root, "MeloNX-core.log");
            Journal.ConfigureJournal(core);
            var result = new Dictionary<string, object>();
            // As the gc-events probe: keep ~64 MB alive and promoted so the runtime runs background gen2s; a few large
            // objects live in the LOH.
            for (int i = 0; i < 64 * 1024; i++) Survivors.Add(new byte[1000]);
            for (int i = 0; i < 8; i++) Survivors.Add(new byte[256 * 1024]);

            // Session 1: a real background gen2, then the fallback signature, then real collections again.
            generation = 1;
            PD.Start(generation);
            result["backgroundObserved"] = Background();
            result["hostFallback1"] = HostFallback();
            Poll();
            int before = GcLines().Count;
            result["realBackgroundLines"] = Describe(GcLines());
            long stale = GC.GetGCMemoryInfo(GCKind.Background).Index;
            double stalePause = GC.GetGCMemoryInfo(GCKind.Background).PauseDurations[0].TotalMilliseconds;
            long fallback = Blocking();
            result["fallbackIndex"] = fallback;
            result["stalePayloadIndex"] = stale;
            result["stalePauseMs0"] = Math.Round(stalePause, 3);
            StampBackground(fallback);
            Poll();
            var lines = GcLines();
            result["fallbackLines"] = Describe(lines.Skip(before));
            before = lines.Count;
            Poll();
            result["linesAfterRepeatedSample"] = GcLines().Count - before;
            GcFeed.Override = null;
            result["backgroundObserved2"] = Background();
            result["hostFallback2"] = HostFallback();
            result["laterBackgroundIndex"] = GC.GetGCMemoryInfo(GCKind.Background).Index;
            Poll();
            lines = GcLines();
            result["laterBackgroundLines"] = Describe(lines.Skip(before));
            before = lines.Count;
            result["laterBlockingIndex"] = Blocking();
            Poll();
            lines = GcLines();
            result["laterBlockingLines"] = Describe(lines.Skip(before));
            before = lines.Count;
            PD.Stop(generation);
            lines = GcLines();
            result["session1FinalLines"] = Describe(lines.Skip(before));
            result["session1Lines"] = Describe(lines);

            // Session 2: the blocking budget is spent when the fallback happens; the final sample reports it.
            before = lines.Count;
            generation = 2;
            PD.Start(generation);
            for (int i = 0; i < 16; i++) { Blocking(); Poll(); }
            lines = GcLines();
            result["session2BudgetLines"] = lines.Count - before;
            before = lines.Count;
            long suppressed = Blocking();
            result["suppressedFallbackIndex"] = suppressed;
            StampBackground(suppressed);
            Poll();
            lines = GcLines();
            result["suppressedFallbackLines"] = Describe(lines.Skip(before));
            before = lines.Count;
            PD.Stop(generation);
            GcFeed.Override = null;
            lines = GcLines();
            result["session2FinalLines"] = Describe(lines.Skip(before));
            // Session 3: a fallback, then a later real blocking gen2 while the background record still holds the stale
            // index; the final sample must not write that record.
            before = lines.Count;
            generation = 3;
            PD.Start(generation);
            long third = Blocking();
            result["session3FallbackIndex"] = third;
            StampBackground(third);
            Poll();
            result["session3LaterBlockingIndex"] = Blocking();
            Poll();
            PD.Stop(generation);
            GcFeed.Override = null;
            lines = GcLines();
            result["session3Lines"] = Describe(lines.Skip(before));
            result["maxDetailLength"] = File.ReadAllLines(core).Max(line => line.Length);
            Console.WriteLine(JsonSerializer.Serialize(result));
            return 0;
        }
        finally
        {
            try { Directory.Delete(root, true); } catch { }
        }
    }
}
