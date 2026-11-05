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

// Runs the real collector and journal (control or candidate source, the same
// program for both) and reports what the durable Core journal received. The
// Python driver decides what each side must show; this program only observes.
static class GcEventsProgram
{
    static readonly BindingFlags PrivateStatic = BindingFlags.NonPublic | BindingFlags.Static;
    static string core;
    static long generation;
    static object Current => typeof(PD).GetField("_current", PrivateStatic).GetValue(null);

    static void Due()
    {
        object epoch = Current;
        epoch.GetType().GetField("PreviousTimestamp", BindingFlags.Public | BindingFlags.Instance)
            .SetValue(epoch, Stopwatch.GetTimestamp() - Stopwatch.Frequency * 6);
    }
    static void Poll() { Due(); PD.Poll(generation); }
    static List<JsonElement> CoreLines(string stage)
    {
        var lines = new List<JsonElement>();
        if (!File.Exists(core)) return lines;
        foreach (string line in File.ReadAllLines(core))
        {
            using var doc = JsonDocument.Parse(line.Substring(line.IndexOf('{')));
            if (doc.RootElement.GetProperty("stage").GetString() == stage) lines.Add(doc.RootElement.Clone());
        }
        return lines;
    }
    static JsonElement Detail(JsonElement line)
    {
        using var doc = JsonDocument.Parse(line.GetProperty("diagnostic").GetString());
        return doc.RootElement.Clone();
    }
    static string[] PerformanceKeys()
    {
        using var snapshot = JsonDocument.Parse(Journal.Snapshot());
        using var doc = JsonDocument.Parse(snapshot.RootElement.GetProperty("performance").GetProperty("diagnostic").GetString());
        var keys = doc.RootElement.EnumerateObject().Select(p => p.Name).ToList();
        keys.AddRange(doc.RootElement.GetProperty("managed").EnumerateObject().Select(p => "managed." + p.Name));
        return keys.ToArray();
    }
    static bool Increasing(List<JsonElement> lines) => lines.Select(l => Detail(l).GetProperty("index").GetInt64())
        .Zip(lines.Skip(1).Select(l => Detail(l).GetProperty("index").GetInt64()), (a, b) => b > a).All(x => x);
    // Asks for a non-blocking gen2 and waits until the runtime completed a background one.
    static int HostFallbacks;
    static bool Background()
    {
        long before = GC.GetGCMemoryInfo(GCKind.Background).Index;
        for (int attempt = 0; attempt < 5; attempt++)
        {
            GC.Collect(2, GCCollectionMode.Default, blocking: false);
            if (SpinWait.SpinUntil(() => GC.GetGCMemoryInfo(GCKind.Background).Index != before, 1000))
            {
                // The host runtime's own fallback (dotnet/runtime#119383): the background record carries the index of the
                // blocking collection that ran instead. Recorded so the test can tell it from a collector defect.
                if (GC.GetGCMemoryInfo(GCKind.Background).Index == GC.GetGCMemoryInfo(GCKind.FullBlocking).Index) HostFallbacks++;
                return true;
            }
        }
        return false;
    }
    // .NET 10.0.0's workstation GC can run a requested background gen2 blocking when it must first create the
    // background GC thread (the thread exits after 20 s idle; dotnet/runtime#119383, docs/melonx-bgc-fallback-2026-11-05.md).
    // The background record then holds the blocking collection's index, which Background() takes for a background GC.
    // Before the measured windows, the thread is created by one real background gen2 (record index not the blocking
    // one), outside any session, so the windows see this runtime's real concurrent collections.
    static void WarmBackgroundThread()
    {
        for (int attempt = 0; attempt < 8; attempt++)
        {
            if (Background() && GC.GetGCMemoryInfo(GCKind.Background).Index != GC.GetGCMemoryInfo(GCKind.FullBlocking).Index) return;
        }
    }
    static int RingCount(string stage)
    {
        using var snapshot = JsonDocument.Parse(Journal.Snapshot());
        return snapshot.RootElement.GetProperty("events").EnumerateArray().Count(e => e.GetProperty("stage").GetString() == stage);
    }

    static int Main()
    {
        string root = Path.Combine(Path.GetTempPath(), "melonx-gc-events-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            core = Path.Combine(root, "MeloNX-core.log");
            Journal.ConfigureJournal(core);
            var result = new Dictionary<string, object>();

            // Session 1: a collection before Start is not this session's event.
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            PD.Start(++generation);
            Poll();
            result["linesAfterStart"] = CoreLines("gcEvent").Count;
            Poll();
            result["linesAfterIdleSample"] = CoreLines("gcEvent").Count;

            // One forced blocking compacting gen2 between two samples.
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            GCMemoryInfo blocking = GC.GetGCMemoryInfo(GCKind.FullBlocking);
            result["expectedIndex"] = blocking.Index;
            result["expectedPauseMs"] = blocking.PauseDurations[0].TotalMilliseconds;
            Poll();
            var lines = CoreLines("gcEvent");
            result["linesAfterForcedGc"] = lines.Count;
            if (lines.Count > 0)
            {
                result["firstStatus"] = lines[0].GetProperty("status").GetString();
                result["firstNativeStatus"] = lines[0].GetProperty("nativeStatus").GetInt32();
                result["firstDetailLength"] = lines[0].GetProperty("diagnostic").GetString().Length;
                result["firstDetail"] = Detail(lines[0]);
            }
            result["ringGcEvents"] = RingCount("gcEvent");
            result["performanceKeys"] = PerformanceKeys();
            Poll(); Poll();
            result["linesAfterTwoIdleSamples"] = CoreLines("gcEvent").Count;

            // Bound: many more collections, each in its own sample window.
            for (int i = 0; i < 40; i++) { GC.Collect(2, GCCollectionMode.Forced, true, true); Poll(); }
            lines = CoreLines("gcEvent");
            result["linesAfterFortyMore"] = lines.Count;
            result["lineOrdinals"] = lines.Select(l => Detail(l).GetProperty("line").GetInt32()).ToArray();
            result["windowCounts"] = lines.Select(l => Detail(l).GetProperty("gen2CollectionsInWindow").GetInt32()).ToArray();
            result["indicesStrictlyIncreasing"] = Increasing(lines);
            // Teardown: a collection after the last sample, with the budget spent,
            // is still written by the final sample (Library.cs collects before Stop).
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            long teardown = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
            PD.Stop(generation);
            lines = CoreLines("gcEvent");
            result["linesAfterStop1"] = lines.Count;
            if (lines.Count > 0)
            {
                var detail = Detail(lines[^1]);
                result["stop1Final"] = detail.GetProperty("finalSample").GetBoolean();
                result["stop1IndexIsTeardown"] = detail.GetProperty("index").GetInt64() == teardown;
                result["stop1NewInWindow"] = detail.GetProperty("newInWindow").GetBoolean();
                result["stop1Window"] = detail.GetProperty("gen2CollectionsInWindow").GetInt32();
                result["stop1Suppressed"] = detail.GetProperty("suppressedLines").GetInt32();
                result["stop1KindLine"] = detail.GetProperty("kindLine").GetInt32();
            }

            // Session 2: the previous session's collections are not re-reported;
            // one collection per window, then two in the final one.
            PD.Start(++generation);
            Poll();
            int before = CoreLines("gcEvent").Count;
            result["session2LinesAfterStart"] = before;
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            Poll();
            // Two blocking collections in one window: only the latest is visible.
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            long last = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
            PD.Stop(generation);
            lines = CoreLines("gcEvent");
            result["session2NewLines"] = lines.Count - before;
            result["session2Windows"] = lines.Skip(before).Select(l => Detail(l).GetProperty("gen2CollectionsInWindow").GetInt32()).ToArray();
            result["session2Finals"] = lines.Skip(before).Select(l => Detail(l).GetProperty("finalSample").GetBoolean()).ToArray();
            result["session2KindLines"] = lines.Skip(before).Select(l => Detail(l).GetProperty("kindLine").GetInt32()).ToArray();
            if (lines.Count > before)
            {
                var detail = Detail(lines[^1]);
                result["session2Generation"] = detail.GetProperty("sessionGeneration").GetInt64();
                result["session2IndexIsLatest"] = detail.GetProperty("index").GetInt64() == last;
            }

            // Session 3: background gen2s with this runtime's concurrent GC (the thread warmed up first, outside the session).
            var warmSurvivors = new List<byte[]>();
            for (int i = 0; i < 64 * 1024; i++) warmSurvivors.Add(new byte[1000]);
            WarmBackgroundThread();
            PD.Start(++generation);
            // The runtime runs a background gen2 only over a non-trivial gen2:
            // keep ~64 MB alive and promoted while a non-blocking gen2 is asked.
            var survivors = new List<byte[]>();
            for (int i = 0; i < 64 * 1024; i++) survivors.Add(new byte[1000]);
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            Poll();
            before = CoreLines("gcEvent").Count;
            result["session3LinesAfterSetup"] = before;
            // Window A: one background gen2, then one forced blocking gen2, one sample.
            bool background = Background();
            GC.Collect(2, GCCollectionMode.Forced, true, true);
            long backgroundIndex = GC.GetGCMemoryInfo(GCKind.Background).Index, blockingIndex = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
            Poll();
            lines = CoreLines("gcEvent");
            var mixed = lines.Skip(before).ToList();
            result["backgroundObserved"] = background;
            result["mixedStatuses"] = mixed.Select(l => l.GetProperty("status").GetString()).ToArray();
            result["mixedIndicesStrictlyIncreasing"] = Increasing(mixed);
            result["mixedIndicesMatch"] = mixed.Count == 2 && Detail(mixed[0]).GetProperty("index").GetInt64() == backgroundIndex &&
                Detail(mixed[1]).GetProperty("index").GetInt64() == blockingIndex;
            result["mixedWindows"] = mixed.Select(l => Detail(l).GetProperty("gen2CollectionsInWindow").GetInt32()).ToArray();
            if (mixed.Count > 0)
            {
                var detail = Detail(mixed[0]);
                result["backgroundConcurrent"] = detail.GetProperty("concurrent").GetInt32();
                result["backgroundGeneration"] = detail.GetProperty("generation").GetInt32();
            }
            // Spend the blocking budget, then one more: suppressed, counted.
            before = lines.Count;
            for (int i = 0; i < 16; i++) { GC.Collect(2, GCCollectionMode.Forced, true, true); Poll(); }
            long suppressed = GC.GetGCMemoryInfo(GCKind.FullBlocking).Index;
            lines = CoreLines("gcEvent");
            result["session3BlockingSpent"] = lines.Count - before;
            // Window C: a background gen2 is still written once blocking lines are spent.
            before = lines.Count;
            bool background2 = Background();
            Poll();
            lines = CoreLines("gcEvent");
            var late = lines.Skip(before).ToList();
            result["backgroundObserved2"] = background2;
            result["lateStatuses"] = late.Select(l => l.GetProperty("status").GetString()).ToArray();
            result["lateSuppressed"] = late.Select(l => Detail(l).GetProperty("suppressedLines").GetInt32()).ToArray();
            GC.KeepAlive(survivors);
            // No collection after the last sample: the final sample writes the
            // latest blocking collection, whose line was suppressed.
            before = lines.Count;
            PD.Stop(generation);
            lines = CoreLines("gcEvent");
            result["session3FinalLines"] = lines.Count - before;
            if (lines.Count > before)
            {
                var detail = Detail(lines[^1]);
                result["session3FinalKind"] = detail.GetProperty("kind").GetString();
                result["session3FinalSample"] = detail.GetProperty("finalSample").GetBoolean();
                result["session3FinalIndexIsSuppressed"] = detail.GetProperty("index").GetInt64() == suppressed;
                result["session3FinalNewInWindow"] = detail.GetProperty("newInWindow").GetBoolean();
                result["session3FinalWindow"] = detail.GetProperty("gen2CollectionsInWindow").GetInt32();
                result["session3FinalSuppressed"] = detail.GetProperty("suppressedLines").GetInt32();
                result["session3FinalKindLine"] = detail.GetProperty("kindLine").GetInt32();
            }
            result["session3Lines"] = lines.Count(l => Detail(l).GetProperty("sessionGeneration").GetInt64() == generation);

            var all = CoreLines("gcEvent");
            result["totalLines"] = all.Count;
            result["statuses"] = all.Select(l => l.GetProperty("status").GetString()).Distinct().OrderBy(s => s).ToArray();
            result["maxDetailLength"] = all.Count == 0 ? 0 : all.Max(l => l.GetProperty("diagnostic").GetString().Length);
            result["journalError"] = JsonDocument.Parse(Journal.Snapshot()).RootElement.GetProperty("journalError").GetString();
            result["serverGc"] = System.Runtime.GCSettings.IsServerGC;
            result["concurrentGcConfigured"] = AppContext.TryGetSwitch("System.GC.Concurrent", out bool concurrent) ? concurrent : (bool?)null;
            result["hostFallbacks"] = HostFallbacks;
            Console.WriteLine(JsonSerializer.Serialize(result));
            return 0;
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}
