using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;
using Journal = Ryujinx.Common.EmbeddedLaunchDiagnostics;

static class Program
{
    static int checks;
    static long generation;
    static readonly BindingFlags PrivateStatic = BindingFlags.NonPublic | BindingFlags.Static;
    static object Current => typeof(PD).GetField("_current", PrivateStatic).GetValue(null);
    static object Gate => typeof(Journal).GetField("Gate", PrivateStatic).GetValue(null);
    static FieldInfo Field(object o, string name) => o.GetType().GetField(name, BindingFlags.Public | BindingFlags.Instance);
    static T Get<T>(object o, string name) => (T)Field(o, name).GetValue(o);
    static void Check(bool ok, string message)
    {
        checks++;
        if (!ok) throw new Exception(message);
    }
    static long Start()
    {
        PD.Start(++generation);
        Check(Current != null, "collector failed to start");
        return generation;
    }
    static void Due(object epoch = null)
    {
        epoch ??= Current;
        Field(epoch, "PreviousTimestamp").SetValue(epoch, Stopwatch.GetTimestamp() - Stopwatch.Frequency * 6);
    }
    static JsonElement Snapshot()
    {
        using var doc = JsonDocument.Parse(Journal.Snapshot());
        return doc.RootElement.Clone();
    }
    static JsonElement Details(JsonElement snapshot, string name = "performance")
    {
        using var doc = JsonDocument.Parse(snapshot.GetProperty(name).GetProperty("diagnostic").GetString());
        return doc.RootElement.Clone();
    }
    static JsonElement Poll()
    {
        Due(); PD.Poll(generation); return Snapshot();
    }
    static long Count(JsonElement detail, string key) => detail.GetProperty("counts").GetProperty(key).GetInt64();

    [MethodImpl(MethodImplOptions.NoInlining)]
    static void HotCounters(int count)
    {
        for (int i = 0; i < count; i++) PD.Count(PD.Counter.Draws);
    }
    [MethodImpl(MethodImplOptions.NoInlining)]
    static void HotScopes(int count)
    {
        for (int i = 0; i < count; i++)
        {
            using var scope = PD.Measure(PD.Phase.CounterReports);
        }
    }
    static (long Bytes, double Nanoseconds) Cost(Action<int> action)
    {
        action(20_000);
        const int iterations = 200_000;
        long allocated = GC.GetAllocatedBytesForCurrentThread(), start = Stopwatch.GetTimestamp();
        action(iterations);
        return (GC.GetAllocatedBytesForCurrentThread() - allocated,
                (Stopwatch.GetTimestamp() - start) * 1_000_000_000d / Stopwatch.Frequency / iterations);
    }
    static void Join(Thread thread)
    {
        Check(thread.Join(5000), "diagnostic worker blocked");
    }

    static int Main()
    {
        string root = Path.Combine(Path.GetTempPath(), "melonx-perf-fixture-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try
        {
            foreach (string bad in new[] { "relative/app.log", "", Path.Combine(root, "other.log") })
            {
                bool refused = false;
                try { Journal.ConfigureJournal(bad); } catch (ArgumentException) { refused = true; }
                Check(refused, "invalid path accepted");
            }
            string core = Path.Combine(root, "MeloNX-core.log");
            Journal.ConfigureJournal(core);
            for (int i = 0; i < 70; i++) Journal.Record("ordinary", "event", detail: i.ToString());
            var events = Snapshot().GetProperty("events");
            Check(events.GetArrayLength() == 64, "ordinary ring bound changed");
            Check(events[0].GetProperty("diagnostic").GetString() == "6", "ordinary ring order changed");
            Check(events[63].GetProperty("diagnostic").GetString() == "69", "ordinary ring last changed");
            long originalCoreBytes = new FileInfo(core).Length;
            long g = Start();
            PD.Count(PD.Counter.Draws, 7); PD.Count(PD.Counter.Dispatches, 3);
            PD.Count(PD.Counter.VirtualDependencySingle, 5); PD.Count(PD.Counter.VirtualDependencyMultiple, 2);
            PD.ReportBatch(31); PD.ReportBatch(2);
            using (PD.Measure(PD.Phase.GpuDispatch))
            {
                byte[] allocated = new byte[1024]; GC.KeepAlive(allocated);
                using (PD.Measure(PD.Phase.RenderDrain)) Thread.Sleep(2);
            }
            var first = Poll(); var detail = Details(first);
            Check(detail.GetProperty("schema").GetInt32() == 1, "wrong schema");
            Check(detail.GetProperty("generation").GetInt64() == g, "wrong detail generation");
            Check(first.GetProperty("performance").GetProperty("generation").GetInt64() == g, "wrong event generation");
            Check(first.GetProperty("performance").GetProperty("pid").GetInt32() == Environment.ProcessId, "missing process identity");
            Check(DateTimeOffset.TryParse(first.GetProperty("performance").GetProperty("timestamp").GetString(), out _), "missing UTC timestamp");
            Check(Count(detail, "draws") == 7 && Count(detail, "dispatches") == 3, "wrong command counters");
            Check(Count(detail, "virtualDependencySingle") == 5 && Count(detail, "virtualDependencyMultiple") == 2, "wrong dependency counters");
            Check(Count(detail, "counterReportBatches") == 2 && Count(detail, "counterReportBatchMaxSession") == 31, "wrong batch aggregation");
            Check(detail.GetProperty("phases").GetProperty("gpuDispatch")[0].GetInt64() == 1, "scope calls missing");
            Check(detail.GetProperty("phases").GetProperty("gpuDispatch")[2].GetInt64() >= 1024, "thread allocations missing");
            Check(detail.GetProperty("phases").GetProperty("renderDrain")[1].GetDouble() > 0, "coarse wall time missing");
            Check(detail.GetProperty("scope").GetString().Contains("phases-overlap") && detail.GetProperty("scope").GetString().Contains("approximate-independent-deltas"), "scope limitations missing");
            Check(detail.GetProperty("active").EnumerateObject().Count() == 0, "completed scopes marked active");
            Check(!first.TryGetProperty("precedingPerformance", out _), "normal sample grows history");
            long sequence = first.GetProperty("performance").GetProperty("sequence").GetInt64();
            PD.Poll(g - 1); PD.Poll(g);
            Check(Snapshot().GetProperty("performance").GetProperty("sequence").GetInt64() == sequence, "wrong generation/early poll emitted");
            var next = Details(Poll());
            Check(Count(next, "draws") == 0 && Count(next, "counterReportBatches") == 0, "window counters not deltas");
            Check(Count(next, "counterReportBatchMaxSession") == 31, "session maximum reset");
            Check(next.GetProperty("phases").GetProperty("gpuDispatch")[0].GetInt64() == 0, "completed calls not delta");

            var active = PD.Measure(PD.Phase.GpuDispatch);
            detail = Details(Poll());
            Check(detail.GetProperty("active").GetProperty("gpuDispatch")[0].GetInt32() == 1, "busy phase looks idle");
            Check(detail.GetProperty("active").GetProperty("gpuDispatch")[1].GetDouble() >= 0, "invalid active age");
            Check(detail.GetProperty("activeColumns").GetString() == "inFlightScopes,firstRegisteredStartAgeMsApprox", "age semantics wrong");
            Get<long[]>(Current, "FirstStarts")[(int)PD.Phase.GpuDispatch] = 0;
            Check(Details(Poll()).GetProperty("active").GetProperty("gpuDispatch")[1].ValueKind == JsonValueKind.Null, "unpublished age must remain unknown");
            active.Dispose();
            Check(Details(Poll()).GetProperty("active").EnumerateObject().Count() == 0, "scope did not release active status");
            try { using var scope = PD.Measure(PD.Phase.QueryReadback); throw new InvalidOperationException("fixture"); }
            catch (InvalidOperationException) { }
            detail = Details(Poll());
            Check(detail.GetProperty("phases").GetProperty("queryReadback")[0].GetInt64() == 1, "exception lost scope completion");
            Check(detail.GetProperty("active").EnumerateObject().Count() == 0, "exception leaked active status");

            var counterCost = Cost(HotCounters); var scopeCost = Cost(HotScopes);
            Check(counterCost.Bytes == 0, "hot counters allocate");
            Check(scopeCost.Bytes == 0, "coarse scopes allocate");
            for (int i = 0; i < 64; i++) { PD.Count(PD.Counter.CacheExports); Poll(); }
            var latest = Snapshot();
            Check(latest.GetProperty("events").GetArrayLength() == 64, "metrics entered ordinary ring");
            Check(!latest.TryGetProperty("precedingPerformance", out _), "normal metrics accumulated");
            Check(new FileInfo(core).Length == originalCoreBytes, "performance duplicated into Core file");
            long before = GC.GetAllocatedBytesForCurrentThread();
            byte[] raw = Journal.Snapshot();
            long snapshotAllocations = GC.GetAllocatedBytesForCurrentThread() - before;
            // Ordinary ring is already full of real low-volume records. Clear
            // it only in this fixture to isolate the extra metrics transport.
            typeof(Journal).GetField("Events", PrivateStatic).GetValue(null).GetType().GetMethod("Clear").Invoke(typeof(Journal).GetField("Events", PrivateStatic).GetValue(null), null);
            Journal.Snapshot();
            before = GC.GetAllocatedBytesForCurrentThread(); raw = Journal.Snapshot();
            long latestAllocations = GC.GetAllocatedBytesForCurrentThread() - before;
            Check(raw.Length < 5000 && latestAllocations < 64_000, "latest-only transport amplification");
            int latestBytes = raw.Length;
            PD.Stop(g);
            latest = Snapshot();
            Check(Current == null, "Stop left active collector");
            Check(latest.GetProperty("performance").GetProperty("status").GetString() == "final", "final absent");
            Check(latest.GetProperty("precedingPerformance").GetProperty("status").GetString() == "sample", "preceding window lost at close");
            Check(latest.GetProperty("performance").GetProperty("sequence").GetInt64() > latest.GetProperty("precedingPerformance").GetProperty("sequence").GetInt64(), "final delivery order wrong");
            long finalSequence = latest.GetProperty("performance").GetProperty("sequence").GetInt64();
            PD.Stop(g); PD.Poll(g); HotCounters(100); HotScopes(100);
            Check(Snapshot().GetProperty("performance").GetProperty("sequence").GetInt64() == finalSequence, "stopped collector emitted");
            var disabledCounters = Cost(HotCounters); var disabledScopes = Cost(HotScopes);
            Check(disabledCounters.Bytes == 0 && disabledScopes.Bytes == 0, "disabled instrumentation allocates");

            g = Start();
            var oldScope = PD.Measure(PD.Phase.GpuDispatch);
            PD.Stop(g); long newer = Start(); oldScope.Dispose();
            detail = Details(Poll());
            Check(detail.GetProperty("phases").GetProperty("gpuDispatch")[0].GetInt64() == 0, "late scope charged next generation");
            long newSequence = Snapshot().GetProperty("performance").GetProperty("sequence").GetInt64();
            Journal.Record("performance", "final", detail: "{}", performanceGeneration: g);
            Check(Snapshot().GetProperty("performance").GetProperty("sequence").GetInt64() == newSequence, "old final replaced new sample");
            Check(!Snapshot().TryGetProperty("precedingPerformance", out _), "new sample kept prior final history");
            PD.Stop(newer);

            g = Start();
            var threads = Enumerable.Range(0, 20).Select(_ => new Thread(() => PD.Count(PD.Counter.Draws))).ToArray();
            foreach (var thread in threads) thread.Start();
            foreach (var thread in threads) Join(thread);
            detail = Details(Poll());
            Check(Count(detail, "draws") == 16, "owner counter slots not bounded");
            Check(Count(detail, "untrackedCounterThreads") == 4, "overflow silently omitted");
            PD.Stop(g);

            // A real reader blocks in the journal transport after Capture.
            // Stop must return promptly and the reader must flush its final.
            g = Start(); Due(); object epoch = Current;
            Thread poll;
            Monitor.Enter(Gate);
            try
            {
                poll = new Thread(() => PD.Poll(g)); poll.Start();
                Check(SpinWait.SpinUntil(() => Get<int>(epoch, "Sampling") == 1 &&
                    Stopwatch.GetTimestamp() - Get<long>(epoch, "PreviousTimestamp") < Stopwatch.Frequency, 2000), "reader never reached transport");
                var start = Stopwatch.GetTimestamp(); PD.Stop(g);
                Check((Stopwatch.GetTimestamp() - start) * 1000d / Stopwatch.Frequency < 200, "Stop waited on observer");
            }
            finally { Monitor.Exit(Gate); }
            Join(poll);
            latest = Snapshot();
            Check(latest.GetProperty("performance").GetProperty("status").GetString() == "final", "overlapped Stop lost final");
            Check(latest.TryGetProperty("precedingPerformance", out _), "overlapped Stop lost prior sample");

            // Start a new generation before an older blocked transport resumes.
            g = Start(); Due(); epoch = Current; long oldGeneration = g;
            Monitor.Enter(Gate);
            try
            {
                poll = new Thread(() => PD.Poll(oldGeneration)); poll.Start();
                Check(SpinWait.SpinUntil(() => Get<int>(epoch, "Sampling") == 1 &&
                    Stopwatch.GetTimestamp() - Get<long>(epoch, "PreviousTimestamp") < Stopwatch.Frequency, 2000), "old reader never reached transport");
                PD.Stop(oldGeneration); newer = Start();
                PD.Count(PD.Counter.Draws, 9); Poll();
                newSequence = Snapshot().GetProperty("performance").GetProperty("sequence").GetInt64();
            }
            finally { Monitor.Exit(Gate); }
            Join(poll); latest = Snapshot();
            Check(latest.GetProperty("performance").GetProperty("generation").GetInt64() == newer, "stale transport changed generation");
            Check(latest.GetProperty("performance").GetProperty("sequence").GetInt64() == newSequence, "stale transport replaced current sample");
            Check(Count(Details(latest), "draws") == 9, "new counters lost in old final");
            PD.Stop(newer);

            g = Start();
            int beforeGen2 = GC.CollectionCount(2); GC.Collect(2, GCCollectionMode.Forced, true, true);
            detail = Details(Poll());
            Check(detail.GetProperty("managed").GetProperty("collections")[2].GetInt32() >= 1, "GC collection delta missing");
            Check(detail.GetProperty("managed").GetProperty("lastGcHeapBytes").GetInt64() > 0, "last GC heap missing");
            Check(detail.GetProperty("managed").GetProperty("gcPauseMs").GetDouble() >= 0, "negative GC pause");
            Check(detail.GetProperty("managed").GetProperty("allocatedBytesApprox").GetInt64() >= 0, "negative global allocation");
            // Max-width counters plus all active phase names must survive the
            // real journal redactor without truncated or malformed JSON.
            epoch = Current;
            foreach (string name in new[] { "Calls", "Ticks", "Bytes" }) Array.Fill(Get<long[]>(epoch, name), long.MaxValue / 4);
            Array.Fill(Get<int[]>(epoch, "Active"), 1);
            Array.Fill(Get<long[]>(epoch, "FirstStarts"), Stopwatch.GetTimestamp() - Stopwatch.Frequency * 3600);
            Array.Fill(Get<long[][]>(epoch, "Counters")[0], long.MaxValue / 4);
            Field(epoch, "Slots").SetValue(epoch, 1);
            latest = Poll();
            string maximumJson = latest.GetProperty("performance").GetProperty("diagnostic").GetString();
            Check(maximumJson.Length <= 4000, "metric JSON exceeds redaction bound");
            detail = Details(latest);
            Check(detail.GetProperty("active").EnumerateObject().Count() == 14, "max-width report dropped phases");
            Check(detail.GetProperty("counts").GetProperty("virtualDependencyMultiple").GetInt64() > 0, "max-width metric lost");
            PD.Stop(g);
            Journal.PerformanceObserver = () => throw new InvalidOperationException("fixture observer");
            Check(Snapshot().GetProperty("stage").ValueKind == JsonValueKind.String, "observer failure propagated");
            Journal.PerformanceObserver = null;

            // Exercise actual native append, retained legacy size policy,
            // core rotation, redaction and the forced rename/create gap.
            using (var file = new FileStream(core, FileMode.Open, FileAccess.Write)) file.SetLength(5 * 1024 * 1024);
            Journal.Record("rotation", "passed", detail: "new generation marker");
            Check(File.Exists(core + ".1") && new FileInfo(core + ".1").Length == 5 * 1024 * 1024, "Core predecessor lost");
            Check(File.ReadAllText(core).Contains("new generation marker"), "Core rotation did not append");
            File.Move(core, core + ".gap");
            Journal.RecordCrash(new InvalidOperationException("rotation gap fatal " + new string('a', 64)));
            Check(File.Exists(core), "fatal report lost during rotation gap");
            string crash = File.ReadAllText(core);
            Check(crash.Contains("rotation gap fatal") && crash.Contains("[redacted]") && !crash.Contains(new string('a', 64)), "crash redaction or append failed");
            // This is the actual normal-rotation creation mode, after a forced
            // writer has already recreated the destination in the rename gap.
            using (var nextFile = new FileStream(core, FileMode.OpenOrCreate, FileAccess.Write, FileShare.ReadWrite)) { }
            Check(File.ReadAllText(core) == crash, "normal rotation creation truncated fatal record");
            Check(Snapshot().GetProperty("journalError").GetString() == "", "fatal retry reported spurious error");
            string legacy = Path.Combine(root, "app.log");
            Journal.ConfigureJournal(legacy);
            using (var file = new FileStream(legacy, FileMode.Open, FileAccess.Write)) file.SetLength(5 * 1024 * 1024);
            Journal.Record("legacy", "ordinary", detail: "must remain capped");
            Check(new FileInfo(legacy).Length == 5 * 1024 * 1024 && !File.Exists(legacy + ".1"), "legacy shared log rotated");
            Journal.RecordCrash(new Exception("forced legacy report"));
            Check(new FileInfo(legacy).Length > 5 * 1024 * 1024, "fatal report failed to bypass legacy cap");
            Journal.ConfigureJournal(core);
            File.Delete(core); Directory.CreateDirectory(core);
            Journal.Record("io", "failed", detail: "engine result remains available");
            Check(Snapshot().GetProperty("journalError").GetString().Length > 0, "IO failure not observable");

            Console.WriteLine(JsonSerializer.Serialize(new {
                result = "passed", checks, actualProductionCollector = true, actualProductionJournal = true,
                hotCounterAllocatedBytes = counterCost.Bytes, hotScopeAllocatedBytes = scopeCost.Bytes,
                enabledCounterNs = counterCost.Nanoseconds, enabledScopeNs = scopeCost.Nanoseconds,
                disabledCounterNs = disabledCounters.Nanoseconds, disabledScopeNs = disabledScopes.Nanoseconds,
                latestSnapshotBytes = latestBytes, latestSnapshotAllocatedBytes = latestAllocations,
                fullOrdinaryRingSnapshotAllocatedBytes = snapshotAllocations, maximumMetricCharacters = maximumJson.Length,
                normalMetricsRetained = 1, finalMetricsRetained = 2, threadCounterSlots = 16,
                timingScope = "host-only microbenchmark, not Apple NativeAOT or game FPS", physicalDeviceTested = false
            }));
            return 0;
        }
        finally { Directory.Delete(root, recursive: true); }
    }
}
