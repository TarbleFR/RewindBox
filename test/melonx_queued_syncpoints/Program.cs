// Scenarios of the queued syncpoint fixture: order, waits, age, release, the 3D engine's increments, the renderer
// barrier before a blocking wait, disposal, logging and a concurrent consumer. Each scenario states the guarantee of
// the delivered blocking path that the queue must keep (docs/melonx-optimization-map-2026-11-03.md, design of #2).
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Threading;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;

static class Program
{
    static int checks, scenarios;
    static readonly List<string> Passed = new();
    static readonly List<string> Failed = new();

    internal static void Check(bool ok, string message)
    {
        Interlocked.Increment(ref checks);
        if (!ok) throw new Exception("FAIL: " + message + " | trace: " + string.Join(" ", FixtureTrace.Snapshot().TakeLast(24)));
    }

    // A failed scenario is reported and the next one runs, so one execution shows every broken guarantee.
    static void Scenario(string name, Action body)
    {
        scenarios++;
        try
        {
            body();
            Passed.Add(name);
        }
        catch (Exception error)
        {
            Failed.Add(name + ": " + error.GetType().Name + ": " + error.Message);
        }
        GpuContext.QueueSyncpointsBehindReports = false;
    }

    static bool InOrder(params string[] events)
    {
        string[] trace = FixtureTrace.Snapshot();
        int at = -1;
        foreach (string value in events)
        {
            int index = Array.IndexOf(trace, value, at + 1);
            if (index < 0) return false;
            at = index;
        }
        return true;
    }

    static int Count(string prefix) => FixtureTrace.Snapshot().Count(value => value.StartsWith(prefix, StringComparison.Ordinal));

    static uint[] Increments() => FixtureTrace.Snapshot().Where(value => value.StartsWith("inc:", StringComparison.Ordinal))
        .Select(value => uint.Parse(value.Substring(4))).ToArray();

    static T Field<T>(GpuContext context, string name)
    {
        FieldInfo field = typeof(GpuContext).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance);
        Check(field != null, "queue counter " + name);
        return (T)field.GetValue(context);
    }

    static long Counter(GpuContext context, string name) => Field<long>(context, name);

    static int QueueLength(GpuContext context) => ((System.Collections.ICollection)Field<object>(context, "_queuedSyncpoints")).Count;

    static void Main(string[] args)
    {
        Scenario("library assigns the policy per session", () =>
        {
            LibraryProbe.Assign(true);
            Check(GpuContext.QueueSyncpointsBehindReports && Ryujinx.Graphics.Vulkan.EncodingPolicy.IncrementalArrayDescriptors,
                  "the Library enables the queue with the other Hogwarts policies");
            LibraryProbe.Assign(false);
            Check(!GpuContext.QueueSyncpointsBehindReports, "the Library disables it for every other title");
        });

        foreach (bool threaded in new[] { false, true })
        {
            string mode = threaded ? " (threaded renderer)" : " (direct renderer)";

            Scenario("policy off: the delivered blocking path" + mode, () =>
            {
                using var s = new Session(policy: false, threaded: threaded);
                var report = s.Add(7);
                s.Fifo.Increment(1);
                Check(QueueLength(s.Context) == 0 && !s.Context.HasQueuedSyncpoints, "off: nothing queued");
                Check(s.Context.HostSyncs.SequenceEqual(new[] { HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force }), "off: one forced submission");
                Check(s.Context.Renderer.Drains == 1, "off: the renderer barrier of the blocking path");
                Check(InOrder("sync:StrictSyncpoint, Force", "renderer-barrier", "counter-flush:7", "publish:7", "inc:1"),
                      "off: submitted, barrier, report published, then incremented");
                Check(report.Released && s.Leases == 0, "off: lease returned");
            });

            Scenario("policy on, report synchronisation off: the delivered path" + mode, () =>
            {
                using var s = new Session(policy: true, synchronize: false, threaded: threaded);
                s.Fifo.Increment(2);
                Check(QueueLength(s.Context) == 0 && Increments().SequenceEqual(new uint[] { 2 }), "increment not queued");
                Check(s.Context.HostSyncs.SequenceEqual(new[] { HostSyncFlags.StrictSyncpoint }) && s.Context.Renderer.Drains == 0,
                      "strict sync, no barrier");
            });

            Scenario("policy on, nothing pending, empty queue: the delivered path" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                s.Fifo.Increment(3);
                Check(QueueLength(s.Context) == 0 && Increments().SequenceEqual(new uint[] { 3 }), "incremented at once");
                Check(s.Context.HostSyncs.SequenceEqual(new[] { HostSyncFlags.StrictSyncpoint }) && s.Context.Renderer.Drains == 0,
                      "strict sync, no barrier, no wait");
            });

            Scenario("order: increments in command order, each after its reports" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                var a = s.Add(100);
                s.Fifo.Increment(10);
                Check(QueueLength(s.Context) == 1 && Count("inc:") == 0, "A queued, not incremented");
                Check(s.Context.HostSyncs.Last() == (HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force), "A submitted (forced) with its reports");
                Check(s.Context.Renderer.Drains == 0 && a.Counter.Flushes == 0, "no renderer barrier and no report wait when queued");
                Check(!s.Cache.HasPendingReports && s.Cache.PendingReportCount == 0, "the pending reports handed over to the queue");
                Check(!s.Context.FlushCounterReports(), "no cache tracked once handed over");
                var b = s.Add(101);
                s.Fifo.Increment(11);
                s.Fifo.Increment(12);
                Check(s.Context.HostSyncs.Last() == HostSyncFlags.StrictSyncpoint, "an increment without reports queues behind, submitted unforced");
                Check(QueueLength(s.Context) == 3 && Count("inc:") == 0, "B and C queued behind A");
                b.Complete();
                Check(!s.Device.WaitForCommands(), "no command");
                Check(Count("inc:") == 0 && b.Publishes == 0, "B, complete, does not overtake A");
                Check(s.Device._event.Timeouts.Last() == 1, "1 ms FIFO wait while increments are queued");
                a.Complete();
                s.Device.WaitForCommands();
                Check(InOrder("publish:100", "inc:10", "publish:101", "inc:11", "inc:12"), "command order, each after its reports");
                Check(Increments().SequenceEqual(new uint[] { 10, 11, 12 }), "each increment exactly once");
                Check(QueueLength(s.Context) == 0 && s.Device._event.Timeouts.Last() == 8, "8 ms FIFO wait once empty");
                Check(Counter(s.Context, "_syncpointsQueued") == 3 && Counter(s.Context, "_syncpointsReady") == 3 &&
                      Counter(s.Context, "_deepestSyncpointQueue") == 3, "counted: queued, ready, deepest");
                Check(s.Context.Renderer.Drains == 0 && a.Counter.Flushes == 0 && b.Counter.Flushes == 0, "ready entries publish without waiting");
                Check(a.Released && b.Released && s.Leases == 0, "leases returned");
            });

            Scenario("order: reports of two channels in one increment" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                var other = new CounterCache();
                var a = s.Add(110);
                var b = s.Add(111, cache: other);
                s.Fifo.Increment(13);
                Check(!s.Cache.HasPendingReports && !other.HasPendingReports, "both caches handed over");
                a.Complete();
                s.Device.WaitForCommands();
                Check(Count("inc:") == 0, "not incremented before every report of the increment");
                b.Complete();
                s.Device.WaitForCommands();
                Check(InOrder("publish:110", "inc:13") && InOrder("publish:111", "inc:13"), "both reports before the increment");
            });

            Scenario("waits: a GPU syncpoint wait drains the queue first, with the blocking flush" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                var a = s.Add(200);
                s.Fifo.Increment(20);
                var b = s.Add(201);
                s.Fifo.Increment(21);
                int barriers = s.Context.Renderer.Drains;
                s.Fifo.Wait(21, 1);
                Check(InOrder("counter-flush:200", "publish:200", "inc:20", "counter-flush:201", "publish:201", "inc:21", "wait:21"),
                      "drained in order, each report published, before the GPU thread waits");
                Check(QueueLength(s.Context) == 0 && Counter(s.Context, "_syncpointsByWait") == 2, "counted: drained by a wait");
                Check(s.Context.Renderer.Drains == barriers + 1, "one renderer barrier before the blocking flushes, as the delivered path");
                Check(a.Released && b.Released && s.Leases == 0, "leases returned");
                int before = s.Context.Renderer.Drains;
                s.Fifo.Wait(21, 1);
                Check(s.Context.Renderer.Drains == before && Count("wait:21") == 2, "a wait with an empty queue does not wait for the renderer");
            });

            Scenario("age: a head older than 50 ms is drained with the blocking flush" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                var a = s.Add(300);
                s.Fifo.Increment(30);
                s.Device.WaitForCommands();
                Check(Count("inc:") == 0 && a.Counter.Flushes == 0, "a young incomplete head waits");
                Thread.Sleep(70);
                s.Device.WaitForCommands();
                Check(InOrder("counter-flush:300", "publish:300", "inc:30"), "the old head published then incremented");
                Check(Counter(s.Context, "_syncpointsByAge") == 1 && Field<double>(s.Context, "_oldestQueuedSyncpointMs") >= 50,
                      "counted: by age, oldest age");
                Check(a.Released && s.Leases == 0, "lease returned");
            });

            Scenario("age: a report that never completes withholds its syncpoint, as the delivered path" + mode, () =>
            {
                bool delivered = false, queued = false;
                using (var s = new Session(policy: false, threaded: threaded))
                {
                    s.Add(310, never: true);
                    try { s.Fifo.Increment(31); } catch (InvalidOperationException) { delivered = true; }
                    Check(delivered && Count("inc:31") == 0, "delivered: the syncpoint is withheld and the error raised");
                }
                using (var s = new Session(policy: true, threaded: threaded))
                {
                    var stuck = s.Add(311, never: true);
                    s.Fifo.Increment(32);
                    var next = s.Add(312);
                    s.Fifo.Increment(33);
                    next.Complete();
                    Thread.Sleep(70);
                    try { s.Device.WaitForCommands(); } catch (InvalidOperationException) { queued = true; }
                    Check(queued && Count("inc:") == 0, "queued: the syncpoint is withheld and the error raised; nothing behind it overtakes");
                    Check(QueueLength(s.Context) == 2, "the withheld increment stays at the head");
                    s.DisposeContext();
                    Check(Increments().SequenceEqual(new uint[] { 32, 33 }) && stuck.Released && stuck.Publishes == 0 && s.Leases == 0,
                          "disposal releases the withheld increment without publishing it, then the next");
                }
            });

            Scenario("release: an invalidated report (unmapped) is ready without publication" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                var a = s.Add(400);
                s.Fifo.Increment(40);
                a.Deferred.Invalid = true;
                Check(a.Released, "the unmap returns the lease at once");
                s.Device.WaitForCommands();
                Check(Increments().SequenceEqual(new uint[] { 40 }) && a.Publishes == 0 && a.Counter.Flushes == 0, "incremented, nothing published");
                Check(Counter(s.Context, "_syncpointsReady") == 1, "counted ready");
            });

            Scenario("release: disposal increments what is queued, in order, without publishing" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                var a = s.Add(500, never: true);
                s.Fifo.Increment(50);
                var b = s.Add(501, never: true);
                s.Fifo.Increment(51);
                var pending = s.Add(502, never: true);
                s.DisposeContext();
                Check(InOrder("inc:50", "inc:51", "fifo-dispose") && Increments().SequenceEqual(new uint[] { 50, 51 }),
                      "queued increments released in order before the FIFO is disposed");
                Check(a.Publishes == 0 && b.Publishes == 0 && pending.Publishes == 0, "nothing published at disposal");
                Check(a.Released && b.Released && pending.Released && s.Leases == 0, "every lease returned, the pending report's too");
                a.Complete();
                a.Deferred.Flush();
                Check(a.Publishes == 0, "a late result after disposal is not published");
                Check(Logger.Info.Lines.Any(line => line.StartsWith("Queued syncpoints (Hogwarts policy): 2 queued", StringComparison.Ordinal)),
                      "disposal logs the queue counters");
            });

            Scenario("3D engine increment: never ahead of the queued increments" + mode, () =>
            {
                using var s = new Session(policy: true, threaded: threaded);
                var a = s.Add(600);
                s.Fifo.Increment(60);
                var r = s.Add(601);
                s.Threed.Increment(61);
                Check(InOrder("publish:600", "inc:60", "publish:601", "inc:61"),
                      "the 3D increment follows the queued one and every earlier report");
                Check(Increments().SequenceEqual(new uint[] { 60, 61 }) && QueueLength(s.Context) == 0, "each once, queue empty");
                Check(Counter(s.Context, "_syncpointsByIncrement") == 1, "counted: drained by a 3D increment");
                Check(a.Released && r.Released && s.Leases == 0, "leases returned");
            });

            Scenario("3D engine increment, policy off: the delivered path" + mode, () =>
            {
                using var s = new Session(policy: false, threaded: threaded);
                var r = s.Add(610);
                s.Threed.Increment(62);
                Check(InOrder("sync:StrictSyncpoint, Force", "renderer-barrier", "publish:610", "inc:62") && s.Context.Renderer.Updates == 1,
                      "submitted, barrier, published, counters polled, incremented");
            });
        }

        Scenario("barrier: a drain waits for the renderer to run the submission, as the delivered path", () =>
        {
            using (var s = new Session(policy: false, threaded: true))
            {
                s.Context.Renderer.SubmitDelayMs = 200;
                s.Add(700);
                s.Fifo.Increment(70);
                Check(InOrder("renderer-barrier", "publish:700", "inc:70") && Count("counter-timeout") == 0,
                      "delivered: the barrier lets the backend wait end with a result");
            }
            using (var s = new Session(policy: true, threaded: true))
            {
                s.Context.Renderer.SubmitDelayMs = 200;
                s.Add(701);
                s.Fifo.Increment(71);
                try { s.Fifo.Wait(71, 1); }
                catch (InvalidOperationException) { Check(false, "queued: a wait drained the entry before its submission ran (syncpoint withheld)"); }
                Check(InOrder("renderer-barrier", "publish:701", "inc:71", "wait:71") && Count("counter-timeout") == 0,
                      "queued, drained by a wait: barrier, published, incremented, then the wait");
            }
            using (var s = new Session(policy: true, threaded: true))
            {
                s.Context.Renderer.SubmitDelayMs = 300;
                s.Add(702);
                s.Fifo.Increment(72);
                Thread.Sleep(70);
                try { s.Device.WaitForCommands(); }
                catch (InvalidOperationException) { Check(false, "queued: an old head drained before its submission ran (syncpoint withheld)"); }
                Check(InOrder("renderer-barrier", "publish:702", "inc:72") && Count("counter-timeout") == 0, "queued, drained by age: barrier first");
            }
        });

        Scenario("logging: every 4096 queued increments, deepest queue", () =>
        {
            using var s = new Session(policy: true);
            var head = s.Add(800);
            for (uint id = 0; id < 4096; id++) s.Fifo.Increment(1000 + id);
            Check(Logger.Info.Lines.Count(line => line.StartsWith("Queued syncpoints (Hogwarts policy): 4096 queued", StringComparison.Ordinal)) == 1,
                  "one line at 4096");
            head.Complete();
            s.Device.WaitForCommands();
            Check(Increments().SequenceEqual(Enumerable.Range(0, 4096).Select(i => (uint)(1000 + i))), "4096 increments in command order");
            Check(Counter(s.Context, "_deepestSyncpointQueue") == 4096 && Counter(s.Context, "_syncpointsReady") == 4096, "deepest and ready");
        });

        Scenario("concurrent consumer: results in any order, increments in command order", () =>
        {
            for (int seed = 0; seed < 8; seed++)
            {
                using var s = new Session(policy: true, threaded: true);
                var random = new Random(seed);
                var created = new BlockingCollection<Report>();
                var consumer = new Thread(() =>
                {
                    var rng = new Random(seed + 100);
                    var held = new List<Report>();
                    foreach (var report in created.GetConsumingEnumerable())
                    {
                        held.Add(report);
                        while (held.Count > 3 || (held.Count > 0 && rng.Next(3) == 0))
                        {
                            int index = rng.Next(held.Count);
                            held[index].Complete();
                            held.RemoveAt(index);
                            if (rng.Next(4) == 0) Thread.Sleep(1);
                        }
                    }
                    foreach (var report in held) report.Complete();
                });
                consumer.Start();
                var reportsOf = new Dictionary<uint, List<Report>>();
                for (uint id = 0; id < 400; id++)
                {
                    var reports = new List<Report>();
                    for (int n = random.Next(3); n > 0; n--)
                    {
                        var report = s.Add(10000 + (ulong)(id * 4 + n));
                        reports.Add(report);
                        created.Add(report);
                    }
                    reportsOf[id] = reports;
                    s.Fifo.Increment(id);
                    if (random.Next(4) == 0) s.Device.WaitForCommands();
                    if (random.Next(50) == 0) s.Fifo.Wait(id, 0);
                }
                created.CompleteAdding();
                Check(consumer.Join(10000), "consumer finished");
                var watch = Stopwatch.StartNew();
                while (QueueLength(s.Context) != 0 && watch.ElapsedMilliseconds < 5000) s.Device.WaitForCommands();
                Check(Increments().SequenceEqual(Enumerable.Range(0, 400).Select(i => (uint)i)), "every increment once, in command order (seed " + seed + ")");
                foreach (var (id, reports) in reportsOf)
                    foreach (var report in reports)
                        Check(InOrder("publish:" + report.Value, "inc:" + id), "report " + report.Value + " published before increment " + id);
                Check(s.Leases == 0, "every lease returned (seed " + seed + ")");
            }
        });

        Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { checks, scenarios, passed = Passed, failed = Failed }));
        Environment.Exit(Failed.Count == 0 ? 0 : 1);
    }

    internal sealed class Report
    {
        public DeferredCounterReport Deferred;
        public TestCounter Counter;
        public ulong Value;
        public int Publishes;
        public bool Released;
        public void Complete() => Deferred.Complete(Counter, Value);
    }

    // A backend counter event: its result exists once the submission holding its query has run on the renderer; the
    // blocking flush waits a short retry window for it, as the backend's bounded wait does (then the result is missing).
    internal sealed class TestCounter : ICounterEvent
    {
        public DeferredCounterReport Target;
        public RendererBoundary Renderer;
        public ulong Value;
        public int RequiredSubmit, Flushes;
        public bool Never;
        public bool Invalid { get; set; }
        public bool ReserveForHostAccess() => false;

        public void Flush()
        {
            Flushes++;
            FixtureTrace.Add("counter-flush:" + Value);
            if (Never) return;
            var watch = Stopwatch.StartNew();
            while (Renderer.Submitted < RequiredSubmit && watch.ElapsedMilliseconds < 5) Thread.Yield();
            if (Renderer.Submitted >= RequiredSubmit) Target.Complete(this, Value);
            else FixtureTrace.Add("counter-timeout:" + Value);
        }

        public void Dispose() { }
    }

    internal sealed class Session : IDisposable
    {
        public readonly GpuContext Context;
        public readonly CounterCache Cache = new();
        public readonly FifoClassProbe Fifo;
        public readonly FifoDeviceProbe Device;
        public readonly ThreedProbe Threed;
        public int Leases;
        private bool _disposed;

        public Session(bool policy, bool synchronize = true, bool threaded = false)
        {
            GpuContext.QueueSyncpointsBehindReports = policy;
            Context = new GpuContext(threaded) { SynchronizeOcclusionReports = synchronize };
            Fifo = new FifoClassProbe(Context);
            Device = new FifoDeviceProbe(Context);
            Threed = new ThreedProbe(Context);
            lock (Logger.Info.Lines) Logger.Info.Lines.Clear();
            FixtureTrace.Reset();
        }

        public Report Add(ulong value, bool never = false, CounterCache cache = null)
        {
            cache ??= Cache;
            var report = new Report { Value = value };
            Interlocked.Increment(ref Leases);
            report.Deferred = new DeferredCounterReport(published =>
            {
                Program.Check(published == value, "published value " + value);
                report.Publishes++;
                FixtureTrace.Add("publish:" + value);
            }, () => { report.Released = true; Interlocked.Decrement(ref Leases); });
            report.Counter = new TestCounter
            {
                Target = report.Deferred, Renderer = Context.Renderer, Value = value, Never = never,
                RequiredSubmit = Context.Renderer.SubmitsQueued + 1,
            };
            report.Deferred.Attach(report.Counter);
            cache.AddReport(report.Deferred);
            Context.TrackCounterReports(cache);
            return report;
        }

        public void DisposeContext()
        {
            if (_disposed) return;
            _disposed = true;
            Context.Dispose();
        }

        public void Dispose()
        {
            DisposeContext();
            Context.Renderer.Dispose();
            GpuContext.QueueSyncpointsBehindReports = false;
        }
    }
}
