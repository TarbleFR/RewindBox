// Scenarios of the lot after IPA 747 for melonx_pipeline_variant_replay_test.py, compiled into the same probe, against the
// production Ryujinx.Graphics.Vulkan of the final preparation (test-only InternalsVisibleTo). The gate defines a symbol for
// each of these adapters that ORDER runs after adapt_pipeline_variant_replay on its files, so the final preparation's own
// code runs here: the real PipelineVariantJournal (adapt_variant_journal_room: eviction order, the load's trim, the file's
// compaction; adapt_queued_variant_record: states built for skipped draws and the draws that waited for them), the real
// PipelineCacheManager.WaitForMainLoadOnWorker and RenderStageTimer (adapt_queued_variant_record), and the real
// BackgroundCompilationScheduler (adapt_compute_warmup_demand: which thread takes a demanded compile). Plan 748's
// adapt_replay_integer_mask runs here too: the real PipelineState read of a variant and the journal's summary count. Host
// only: no Vulkan device, no pipeline is created, times are host times.
using Ryujinx.Graphics.Vulkan;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using System.Threading.Tasks;

static class LotScenarios
{
    private const BindingFlags Instance = BindingFlags.Instance | BindingFlags.NonPublic;

    private static string PathOf(string root, string name)
    {
        string directory = Path.Combine(root, "lot");
        Directory.CreateDirectory(directory);
        return Path.Combine(directory, name + ".variants");
    }

    private static PipelineVariantJournal Open(string root, string name) =>
        new(PathOf(root, name), PipelineVariantJournal.Schema, () => 60, loadInBackground: false);

    // Opaque variants of a given size (the journal stores and reads back the bytes; the codec is the probe's section A).
    private static byte[] Variant(int i, int size = 64)
    {
        var variant = new byte[size];
        BitConverter.TryWriteBytes(variant.AsSpan(0, 4), i);
        for (int k = 4; k < size; k++) variant[k] = (byte)(i * 31 + k);
        return variant;
    }

    // The lines are appended on the thread pool: wait until the file stops changing.
    private static void Settle(string root, string name)
    {
        long last = -1;
        int stable = 0;
        for (int i = 0; i < 600 && stable < 4; i++)
        {
            Thread.Sleep(50);
            long now = File.Exists(PathOf(root, name)) ? new FileInfo(PathOf(root, name)).Length : 0;
            stable = now == last ? stable + 1 : 0;
            last = now;
        }
    }

    private static T Field<T>(object o, string name) => (T)o.GetType().GetField(name, Instance).GetValue(o);

#if VARIANT_JOURNAL_ROOM
    // adapt_variant_journal_room: a full journal gives up, for a new state, the first state of its eviction order not met in
    // the session; a state given up and met again comes back with its history; the next load keeps exactly the session's
    // journal; a journal full of the session's own states counts what it cannot record; a full file is compacted from memory.
    public static Dictionary<string, object> JournalRoom(string root, Action<bool, string> require)
    {
        var report = new Dictionary<string, object>();
        // The journal's bound in the source this probe runs (2048 states as adapt_pipeline_variant_replay writes it, 4096
        // with adapt_variant_journal_capacity): the scenarios fill exactly the bound and go 300, 52 or one refresh past it.
        const int Bound = PipelineVariantJournal.MaxRecords;
        {
            var s1 = Open(root, "evict");
            for (int i = 0; i < Bound; i++) s1.NoteLate(0x10, Variant(i), 10 + i % 7, joined: false);
            Settle(root, "evict");
            require(s1.LateNew == Bound && s1.NotRecorded == 0, "journal room: session 1 records the bound");

            var s2 = Open(root, "evict");
            int loaded2 = s2.Loaded;
            for (int i = 0; i < 500; i++) s2.NoteLate(0x10, Variant(i * 3), 5, joined: false); // met again this session
            for (int i = 0; i < 300; i++) s2.NoteLate(0x20, Variant(100000 + i), 5, joined: false); // new: each gives up one
            var records2 = Field<Dictionary<(ulong, ulong), PipelineVariantJournal.Record>>(s2, "_records");
            var evicted2 = Field<Dictionary<(ulong, ulong), PipelineVariantJournal.Record>>(s2, "_evicted");
            int heldAfterNew = records2.Count, evictedAfterNew = s2.Evicted, givenUpKnown = evicted2.Count, notRecorded2 = s2.NotRecorded;
            bool noneMetGivenUp = evicted2.Values.All(r => r.LastSession < s2.Session);
            var notMet = records2.Values.Where(r => r.LastSession < s2.Session).ToList();
            bool firstInOrder = evicted2.Values.All(e => notMet.All(k => PipelineVariantJournal.EvictionOrder(e, k, s2.Session) < 0));
            // A given-up state met again by a draw comes back with its history (another state gives up its place).
            var back = evicted2.Values.OrderBy(r => r.Id).Take(10).ToList();
            foreach (var r in back) s2.NoteLate(r.Program, r.Variant, 5, joined: false);
            bool backWithHistory = back.All(r => records2.ContainsKey((r.Program, r.Id)) && r.Sessions == 2 && r.LastSession == s2.Session);
            // A given-up replayed state a draw binds comes back too (NoteReplayUsed).
            var used = evicted2.Values.OrderBy(r => r.Id).First();
            s2.NoteReplayUsed(used);
            bool usedBack = records2.ContainsKey((used.Program, used.Id)) && used.LastSession == s2.Session;
            var keptAtEnd = new HashSet<(ulong, ulong)>(records2.Keys);
            int held2 = records2.Count, evicted = s2.Evicted;
            string summary = s2.Summary("test");
            Settle(root, "evict");

            var s3 = Open(root, "evict");
            var records3 = Field<Dictionary<(ulong, ulong), PipelineVariantJournal.Record>>(s3, "_records");
            bool sameJournal = keptAtEnd.SetEquals(records3.Keys);
            require(loaded2 == Bound && heldAfterNew == Bound && evictedAfterNew == 300 && givenUpKnown == 300 && notRecorded2 == 0,
                $"journal room: 300 new states recorded by giving up 300 ({heldAfterNew} held, {evictedAfterNew} given up, {notRecorded2} not recorded)");
            require(noneMetGivenUp && firstInOrder, "journal room: only states not met this session, first in eviction order, are given up");
            require(backWithHistory && usedBack && held2 == Bound && evicted == 311, $"journal room: met again or used, back with its history ({evicted})");
            require(s3.Loaded == Bound && s3.GivenUpAtLoad == 300 && sameJournal,
                $"journal room: the load trims the 300 given up whose lines are in the file, keeping the session's journal ({s3.GivenUpAtLoad})");
            require(summary.Contains($"Journal: {Bound} of {Bound} states, given up for newer states 311 (at the load 0), not recorded 0, compactions 0, lines not written 0"),
                "journal room: summary line: " + summary);
            report["evict"] = new Dictionary<string, object>
            {
                ["loaded"] = loaded2, ["metAgain"] = 500, ["newStates"] = 300, ["givenUpForNew"] = evictedAfterNew,
                ["noneMetGivenUp"] = noneMetGivenUp, ["firstInEvictionOrder"] = firstInOrder, ["backWithHistory"] = backWithHistory,
                ["usedReplayBack"] = usedBack, ["evicted"] = evicted, ["held"] = held2, ["givenUpAtLoad"] = s3.GivenUpAtLoad,
                ["loadedNext"] = s3.Loaded, ["nextLoadKeepsSessionJournal"] = sameJournal, ["summary"] = summary,
            };
        }
        {
            // Every state held met this session: a new one cannot take a place and is counted.
            var s1 = Open(root, "full");
            for (int i = 0; i < Bound + 52; i++) s1.NoteLate(0x30, Variant(200000 + i), 5, joined: false);
            var records = Field<Dictionary<(ulong, ulong), PipelineVariantJournal.Record>>(s1, "_records");
            require(records.Count == Bound && s1.NotRecorded == 52 && s1.Evicted == 0,
                $"journal room: the bound recorded, 52 counted not recorded ({records.Count}, {s1.NotRecorded}, {s1.Evicted})");
            Settle(root, "full");
            report["full"] = new Dictionary<string, object> { ["held"] = records.Count, ["notRecorded"] = s1.NotRecorded, ["evicted"] = s1.Evicted };
        }
        {
            // A full file: the bound's worth of variants of the codec's largest size (1444 bytes), then a refresh line for each.
            // The file is compacted from memory instead of dropping lines; every refresh survives to the next load. The file
            // bound is the one of the bound's adapter (4 MiB for 2048 states, 8 MiB for 4096): a compaction at the bound fits.
            const int size = 1444;
            var s1 = Open(root, "compact");
            for (int i = 0; i < Bound; i++) s1.NoteLate(0x40, Variant(300000 + i, size), 7, joined: false);
            Settle(root, "compact");
            long bytes1 = new FileInfo(PathOf(root, "compact")).Length;
            var s2 = Open(root, "compact");
            for (int i = 0; i < Bound; i++) s2.NoteLate(0x40, Variant(300000 + i, size), 9, joined: false);
            Settle(root, "compact");
            long bytes2 = new FileInfo(PathOf(root, "compact")).Length;
            var s3 = Open(root, "compact");
            var records3 = Field<Dictionary<(ulong, ulong), PipelineVariantJournal.Record>>(s3, "_records");
            int refreshed = records3.Values.Count(r => r.Sessions == 2 && r.LastSession == 2);
            require(s2.Compactions >= 1 && s2.LinesNotWritten == 0 && bytes2 <= PipelineVariantJournal.MaxFileBytes &&
                    PipelineVariantJournal.MaxFileBytes == (Bound == 2048 ? 4L : Bound == 4096 ? 8L : 0L) * 1024 * 1024 &&
                    (long)Bound * (size + 39) < PipelineVariantJournal.MaxFileBytes * 7 / 8,
                $"journal room: compacted {s2.Compactions}, not written {s2.LinesNotWritten}, {bytes2} bytes of {PipelineVariantJournal.MaxFileBytes}");
            require(s3.Loaded == Bound && refreshed == Bound, "journal room: every refresh survived the compaction: " + refreshed);
            report["compact"] = new Dictionary<string, object>
            {
                ["variantBytes"] = size, ["bytesAfterSession1"] = bytes1, ["bytesAfterSession2"] = bytes2, ["compactions"] = s2.Compactions,
                ["linesNotWritten"] = s2.LinesNotWritten, ["loadedNext"] = s3.Loaded, ["refreshed"] = refreshed,
            };
        }
        {
            // The eviction order is a strict total order on distinct states (the load trims in it).
            var random = new Random(5);
            var list = Enumerable.Range(0, 400).Select(i => new PipelineVariantJournal.Record
            {
                Program = (ulong)random.Next(3), Id = (ulong)random.Next(50), LastSession = (uint)random.Next(1, 12),
                Sessions = (ushort)random.Next(1, 4), FirstSeenMs = (uint)random.Next(3), CostMs = (uint)random.Next(3),
            }).GroupBy(r => (r.Program, r.Id)).Select(g => g.First()).ToList();
            bool total = true;
            foreach (var a in list)
                foreach (var b in list)
                {
                    int x = PipelineVariantJournal.EvictionOrder(a, b, 11), y = PipelineVariantJournal.EvictionOrder(b, a, 11);
                    if (Math.Sign(x) != -Math.Sign(y) || (x == 0) != ReferenceEquals(a, b)) total = false;
                }
            require(total, "journal room: EvictionOrder is a strict total order on distinct states");
            report["order"] = new Dictionary<string, object> { ["states"] = list.Count, ["strictTotal"] = total };
        }
        return report;
    }
#endif

#if QUEUED_VARIANT_RECORD
    // adapt_queued_variant_record: a state built for skipped draws is recorded once per session with its compile time,
    // whichever note records it; the draws that waited for such a compile are counted apart; neither is a late creation and
    // each state is one line; a worker's wait for the main cache's load is summed on its own thread; the render stages line
    // splits the async skips by cause and resets the new counter with its window.
    public static Dictionary<string, object> QueuedRecord(string root, Action<bool, string> require)
    {
        var report = new Dictionary<string, object>();
        {
            var s1 = Open(root, "queued");
            // The compile's note first, then a draw that waited for it (it notes after the compile left the queue).
            s1.NoteLate(0x50, Variant(400000), 120, joined: false, builtForSkipped: true);
            s1.NoteLate(0x50, Variant(400000), 40, joined: true, waitedForSkipped: true);
            // The race: a draw obtained the pipeline in the instant it was built, before the compile's own note.
            s1.NoteLate(0x50, Variant(400002), 2, joined: false, waitedForSkipped: true);
            s1.NoteLate(0x50, Variant(400002), 300, joined: false, builtForSkipped: true);
            // The same state built again for a skipped draw (another program instance): counted once.
            s1.NoteLate(0x50, Variant(400000), 90, joined: false, builtForSkipped: true);
            // A late creation of another state.
            s1.NoteLate(0x50, Variant(400001), 3, joined: false);
            string summary = s1.Summary("test");
            require(s1.DrawQueued == 2 && s1.DrawQueuedMs == 420, $"queued record: built for skipped draws {s1.DrawQueued} ({s1.DrawQueuedMs} ms)");
            require(s1.WaitedForSkipped == 2 && s1.WaitedForSkippedMs == 42, $"queued record: waited {s1.WaitedForSkipped} ({s1.WaitedForSkippedMs} ms)");
            require(s1.LateNew == 1 && s1.LateMs == 3 && s1.JoinedOther == 0 && s1.NotRecorded == 0,
                $"queued record: late {s1.LateNew} ({s1.LateMs} ms), joined {s1.JoinedOther}, not recorded {s1.NotRecorded}");
            require(summary.Contains("built for skipped draws 2 (compile 420 ms, without the main cache's load wait), draws that waited for them 2 (42 ms)"),
                "queued record: summary labels: " + summary);
            Settle(root, "queued");
            var reference = Open(root, "queuedref");
            for (int i = 0; i < 3; i++) reference.NoteLate(0x50, Variant(500000 + i), 5, joined: false);
            Settle(root, "queuedref");
            long bytes = new FileInfo(PathOf(root, "queued")).Length, referenceBytes = new FileInfo(PathOf(root, "queuedref")).Length;
            var s2 = Open(root, "queued");
            var records2 = Field<Dictionary<(ulong, ulong), PipelineVariantJournal.Record>>(s2, "_records");
            uint cost = records2.TryGetValue((0x50UL, PipelineVariantJournal.Checksum64(Variant(400000))), out var first) ? first.CostMs : 0;
            require(bytes == referenceBytes && s2.Loaded == 3 && cost == 120,
                $"queued record: one line per state ({bytes} / {referenceBytes} bytes), three states loaded ({s2.Loaded}), the compile's cost ({cost})");
            report["counts"] = new Dictionary<string, object>
            {
                ["builtForSkipped"] = s1.DrawQueued, ["builtForSkippedMs"] = s1.DrawQueuedMs, ["waitedForSkipped"] = s1.WaitedForSkipped,
                ["waitedForSkippedMs"] = s1.WaitedForSkippedMs, ["lateNew"] = s1.LateNew, ["joinedOther"] = s1.JoinedOther,
                ["notRecorded"] = s1.NotRecorded, ["oneLinePerState"] = bytes == referenceBytes, ["loadedNext"] = s2.Loaded,
                ["costOfFirstNote"] = cost, ["summary"] = summary,
            };
        }
        {
            // The main cache's load never completes here: the worker waits until the deadline (300 ms), and that wait is added
            // to its own thread's sum only; once loaded, nothing is added.
            var manager = (PipelineCacheManager)System.Runtime.CompilerServices.RuntimeHelpers.GetUninitializedObject(typeof(PipelineCacheManager));
            var loaded = new ManualResetEventSlim(false);
            typeof(PipelineCacheManager).GetField("_mainLoaded", Instance).SetValue(manager, loaded);
            // After IPA 800 (the Hogwarts lots) the worker waits for the primary cache's readiness, an event of its own that
            // the load resets with the main one and publishes no later than it: the same unset event stands for both here.
            typeof(PipelineCacheManager).GetField("_primaryCacheReady", Instance)?.SetValue(manager, loaded);
            typeof(PipelineCacheManager).GetField("_mainLoadWaitDeadline", Instance).SetValue(manager, Environment.TickCount64 + 300);
            long waitedMs = -1, elapsedMs = -1;
            var worker = new Thread(() =>
            {
                long before = PipelineCacheManager.WorkerLoadWaitTicks;
                var watch = Stopwatch.StartNew();
                manager.WaitForMainLoadOnWorker();
                elapsedMs = watch.ElapsedMilliseconds;
                waitedMs = (PipelineCacheManager.WorkerLoadWaitTicks - before) * 1000 / Stopwatch.Frequency;
            });
            worker.Start();
            worker.Join();
            long otherThread = PipelineCacheManager.WorkerLoadWaitTicks;
            loaded.Set();
            long beforeLoaded = PipelineCacheManager.WorkerLoadWaitTicks;
            manager.WaitForMainLoadOnWorker();
            bool nothingOnceLoaded = PipelineCacheManager.WorkerLoadWaitTicks == beforeLoaded;
            require(waitedMs >= 200 && waitedMs <= elapsedMs + 5 && elapsedMs - waitedMs <= 50 && otherThread == 0 && nothingOnceLoaded,
                $"queued record: load wait {waitedMs} ms of {elapsedMs} ms on the worker, {otherThread} ticks on another thread");
            report["loadWait"] = new Dictionary<string, object>
            {
                ["waitedMs"] = waitedMs, ["elapsedMs"] = elapsedMs, ["otherThreadTicks"] = otherThread, ["nothingOnceLoaded"] = nothingOnceLoaded,
            };
        }
        {
            // The render stages line of a window: 7 async skips, 3 of them for a queued pipeline state.
            var lines = new List<string>();
            Ryujinx.Common.Logging.Logger.RemoveTarget("console");
            EventHandler<Ryujinx.Common.Logging.LogEventArgs> capture = (_, e) => { lock (lines) lines.Add(e.Message); };
            Ryujinx.Common.Logging.Logger.Updated += capture;
            RenderStageTimer.AsyncSkips = 7;
            RenderStageTimer.AsyncQueuedSkips = 3;
            typeof(RenderStageTimer).GetMethod("Log", BindingFlags.NonPublic | BindingFlags.Static).Invoke(null, new object[] { Stopwatch.Frequency * 5 });
            Ryujinx.Common.Logging.Logger.Updated -= capture;
            string line;
            lock (lines) line = lines.FirstOrDefault(l => l.Contains("Vulkan render stages over"));
            const string split = "; not ready by cause: async skips 7 (pipeline state queued 3, shader modules not ready 4), unavailable pipelines 0";
            bool reset = RenderStageTimer.AsyncQueuedSkips == 0 && RenderStageTimer.AsyncSkips == 0;
            require(line != null && line.Contains(split), "queued record: the stages line splits the async skips: " + line);
            require(reset, "queued record: the counters start again with the next window");
            report["stageLine"] = new Dictionary<string, object> { ["asyncSkips"] = 7, ["queued"] = 3, ["split"] = line != null && line.Contains(split), ["reset"] = reset };
        }
        return report;
    }
#endif

#if COMPUTE_WARMUP_DEMAND
    // adapt_compute_warmup_demand, the demand-queue rule of WorkerQueue.TryTake, on the real scheduler of the final preparation
    // (one pipeline worker: the gate runs this process with six logical processors, as a six-core iPhone). Each round starts
    // once the demand thread waits for work (its flag read under the queue's lock).
    public static Dictionary<string, object> DemandQueue(Func<BackgroundCompilationScheduler> newScheduler, Action<bool, string> require)
    {
        const string DemandThread = "Vulkan Pipeline Demand Compile", Worker = "Vulkan Pipeline Compile 0";
        var report = new Dictionary<string, object> { ["workers"] = BackgroundCompilationScheduler.PipelineWorkerCount };
        require(BackgroundCompilationScheduler.PipelineWorkerCount == 1, "demand queue: one pipeline worker, as on a six-core iPhone");
        var scheduler = newScheduler();
        object queue = typeof(BackgroundCompilationScheduler).GetField("_pipelineQueue", Instance).GetValue(scheduler);
        object queueLock = queue.GetType().GetField("_queueLock", Instance).GetValue(queue);
        FieldInfo waitingField = queue.GetType().GetField("_demandThreadWaiting", Instance);
        require(waitingField != null && waitingField.FieldType == typeof(bool), "demand queue: the scheduler knows when the demand thread waits");
        int notWaiting = 0;

        void WaitForIdleDemandThread()
        {
            var watch = Stopwatch.StartNew();
            while (watch.ElapsedMilliseconds < 3000)
            {
                lock (queueLock)
                {
                    if ((bool)waitingField.GetValue(queue)) return;
                }
                Thread.Sleep(1);
            }
            notWaiting++;
        }

        bool Done(params Task[] tasks) => Task.WaitAll(tasks, 10000);

        {
            // Both threads idle: a demanded compile goes to the demand thread (in the control, to whichever wakes first).
            int rounds = 30, onDemand = 0, completed = 0;
            for (int i = 0; i < rounds; i++)
            {
                WaitForIdleDemandThread();
                string thread = null;
                if (Done(scheduler.SchedulePipelineCompile(_ => thread = Thread.CurrentThread.Name, demanded: true))) completed++;
                if (thread == DemandThread) onDemand++;
            }
            require(completed == rounds && onDemand == rounds, $"demand queue: a demanded compile goes to the idle demand thread ({onDemand} of {rounds})");
            report["idle"] = new Dictionary<string, object> { ["rounds"] = rounds, ["onDemandThread"] = onDemand, ["completed"] = completed };
        }
        {
            // The review's case: the worker ends an item that queued two demanded compiles while a non-demanded high-priority
            // compile waits; the demand thread still waits for work. The demand thread takes the first, the worker the
            // second, and the non-demanded one starts only after it (the worker never skips the whole demanded queue).
            int rounds = 20, firstOnDemand = 0, secondOnWorker = 0, highBeforeSecond = 0, completed = 0;
            for (int i = 0; i < rounds; i++)
            {
                WaitForIdleDemandThread();
                using var started = new ManualResetEventSlim();
                using var go = new ManualResetEventSlim();
                string firstThread = null, secondThread = null;
                long secondStart = 0, highStart = 0;
                Task first = null, second = null;
                Task end = scheduler.SchedulePipelineCompile(_ =>
                {
                    started.Set();
                    go.Wait(5000);
                    first = scheduler.SchedulePipelineCompile(cache => { firstThread = Thread.CurrentThread.Name; Thread.Sleep(30); }, demanded: true);
                    second = scheduler.SchedulePipelineCompile(cache =>
                    {
                        secondStart = Stopwatch.GetTimestamp();
                        secondThread = Thread.CurrentThread.Name;
                        Thread.Sleep(30);
                    }, demanded: true);
                }, highPriority: true);
                started.Wait(5000);
                Task high = scheduler.SchedulePipelineCompile(_ => { highStart = Stopwatch.GetTimestamp(); Thread.Sleep(40); }, highPriority: true);
                go.Set();
                if (Done(end) && Done(first, second, high)) completed++;
                if (firstThread == DemandThread) firstOnDemand++;
                if (secondThread == Worker) secondOnWorker++;
                if (highStart != 0 && highStart < secondStart) highBeforeSecond++;
            }
            require(completed == rounds && firstOnDemand == rounds && secondOnWorker == rounds && highBeforeSecond == 0,
                $"demand queue: first demanded on the demand thread {firstOnDemand}, second on the worker {secondOnWorker}, " +
                $"non-demanded before the second {highBeforeSecond}, of {rounds}");
            report["twoDemanded"] = new Dictionary<string, object>
            {
                ["rounds"] = rounds, ["firstOnDemandThread"] = firstOnDemand, ["secondOnWorker"] = secondOnWorker,
                ["highBeforeSecond"] = highBeforeSecond, ["completed"] = completed,
            };
        }
        {
            // The demand thread busy: a free worker takes the next demanded compile before a high-priority one queued first.
            int rounds = 10, busyOnDemand = 0, demandedOnWorker = 0, demandedFirst = 0, completed = 0;
            for (int i = 0; i < rounds; i++)
            {
                WaitForIdleDemandThread();
                using var workerStarted = new ManualResetEventSlim();
                using var releaseWorker = new ManualResetEventSlim();
                using var busyStarted = new ManualResetEventSlim();
                using var releaseBusy = new ManualResetEventSlim();
                string busyThread = null, demandedThread = null;
                long demandedStart = 0, highStart = 0;
                Task occupy = scheduler.SchedulePipelineCompile(_ => { workerStarted.Set(); releaseWorker.Wait(5000); }, highPriority: true);
                workerStarted.Wait(5000);
                Task busy = scheduler.SchedulePipelineCompile(_ => { busyThread = Thread.CurrentThread.Name; busyStarted.Set(); releaseBusy.Wait(5000); }, demanded: true);
                busyStarted.Wait(5000);
                Task high = scheduler.SchedulePipelineCompile(_ => highStart = Stopwatch.GetTimestamp(), highPriority: true);
                Task demanded = scheduler.SchedulePipelineCompile(_ => { demandedStart = Stopwatch.GetTimestamp(); demandedThread = Thread.CurrentThread.Name; }, demanded: true);
                releaseWorker.Set();
                bool done = Done(occupy, high, demanded);
                releaseBusy.Set();
                if (done && Done(busy)) completed++;
                if (busyThread == DemandThread) busyOnDemand++;
                if (demandedThread == Worker) demandedOnWorker++;
                if (demandedStart != 0 && (highStart == 0 || demandedStart < highStart)) demandedFirst++;
            }
            require(completed == rounds && busyOnDemand == rounds && demandedOnWorker == rounds && demandedFirst == rounds,
                $"demand queue: demand thread busy {busyOnDemand}, demanded on the worker {demandedOnWorker}, before the high one {demandedFirst}, of {rounds}");
            report["demandThreadBusy"] = new Dictionary<string, object>
            {
                ["rounds"] = rounds, ["busyOnDemandThread"] = busyOnDemand, ["demandedOnWorker"] = demandedOnWorker,
                ["demandedBeforeHigh"] = demandedFirst, ["completed"] = completed,
            };
        }
        {
            // A compile nobody demanded is the worker's, never the demand thread's (unchanged).
            int rounds = 10, onWorker = 0, completed = 0;
            for (int i = 0; i < rounds; i++)
            {
                WaitForIdleDemandThread();
                string thread = null;
                if (Done(scheduler.SchedulePipelineCompile(_ => thread = Thread.CurrentThread.Name, highPriority: true))) completed++;
                if (thread == Worker) onWorker++;
            }
            require(completed == rounds && onWorker == rounds, $"demand queue: a non-demanded compile runs on the worker ({onWorker} of {rounds})");
            report["undemanded"] = new Dictionary<string, object> { ["rounds"] = rounds, ["onWorker"] = onWorker, ["completed"] = completed };
        }
        require(notWaiting == 0, "demand queue: the demand thread was found waiting before every round: " + notWaiting);
        report["roundsWithoutIdleDemandThread"] = notWaiting;
        scheduler.Dispose();
        return report;
    }
#endif
#if REPLAY_INTEGER_MASK
    // adapt_replay_integer_mask: a recorded variant is read with the integer-format mask a draw has for its colour attachments.
    // The draw's rule (FramebufferParams): bit s for each colour target in slot s whose GAL format IsInt, the target's Vulkan
    // format being FormatTable's for that GAL format (ConvertToVkFormat may give R4G4B4A4UnormPack16 for R4G4B4A4Unorm). The
    // oracle below takes the rule from the GAL side (forward table and IsInt); the final PipelineState reads the Vulkan formats.
    private static bool IsInt(Ryujinx.Graphics.GAL.Format format) => Ryujinx.Graphics.GAL.FormatExtensions.get_IsInt(format);

    // The Vulkan formats of IsInt GAL formats: the only formats a draw's colour target carries with its mask bit set.
    public static HashSet<Silk.NET.Vulkan.Format> IntegerTargets() =>
        Enum.GetValues<Ryujinx.Graphics.GAL.Format>().Where(IsInt).Select(f => FormatTable.GetFormat(f)).ToHashSet();

    public static uint DrawMask(ReadOnlySpan<Silk.NET.Vulkan.Format> formats, ReadOnlySpan<int> slots, HashSet<Silk.NET.Vulkan.Format> integer)
    {
        uint mask = 0;
        for (int i = 0; i < slots.Length; i++) mask |= integer.Contains(formats[i]) ? 1u << slots[i] : 0u;
        return mask;
    }

    // ShaderCollection's replay Schedule, its read only: the real TryReadVariant, the key it gives, nothing created.
    private sealed class ReadTarget : PipelineVariantJournal.ITarget
    {
        public readonly System.Collections.Concurrent.ConcurrentDictionary<ulong, PipelineUid> Keys = new();

        public Task<long> Schedule(PipelineVariantJournal.Record record)
        {
            var state = new PipelineState();
            state.Initialize(false);
            Span<int> slots = stackalloc int[8];

            if (!state.TryReadVariant(record.Variant, slots, out _))
            {
                return null;
            }

            Keys[record.Id] = state.Internal;
            return Task.FromResult(1L);
        }
    }

    public static Dictionary<string, object> IntegerMask(string root, Action<bool, string> require)
    {
        var report = new Dictionary<string, object>();
        var random = new Random(748);
        var integer = IntegerTargets();
        var galFormats = Enum.GetValues<Ryujinx.Graphics.GAL.Format>();
        var colorFormats = galFormats.Where(f => FormatTable.GetFormat(f) != Silk.NET.Vulkan.Format.Undefined &&
            !Ryujinx.Graphics.GAL.FormatExtensions.get_IsDepthOrStencil(f)).ToArray();
        var depthFormats = galFormats.Where(f => Ryujinx.Graphics.GAL.FormatExtensions.get_IsDepthOrStencil(f)).ToArray();
        int Count() => Volatile.Read(ref PipelineVariantJournal.IntegerMasksRecomputedTotal);

        {
            // Every GAL format: the final read's rule on its Vulkan format is its IsInt, in any slot; the formats
            // ConvertToVkFormat substitutes and the swapchain's are not integer formats.
            int formats = 0, same = 0;
            foreach (var f in galFormats)
            {
                int slot = random.Next(8);
                uint read = PipelineState.IntegerFormatMask(new[] { FormatTable.GetFormat(f) }, new[] { slot });
                formats++;
                same += read == (IsInt(f) ? 1u << slot : 0u) ? 1 : 0;
            }
            var others = new[]
            {
                Silk.NET.Vulkan.Format.D32SfloatS8Uint, Silk.NET.Vulkan.Format.R4G4B4A4UnormPack16, Silk.NET.Vulkan.Format.B8G8R8A8Unorm,
                Silk.NET.Vulkan.Format.B8G8R8A8Srgb, Silk.NET.Vulkan.Format.R8G8B8A8Unorm, Silk.NET.Vulkan.Format.R8G8B8A8Srgb,
                Silk.NET.Vulkan.Format.Undefined,
            };
            bool othersNotInteger = others.All(v => PipelineState.IntegerFormatMask(new[] { v }, new[] { 0 }) == 0);
            require(same == formats && othersNotInteger && integer.Count == 26,
                $"integer mask: the read's rule is IsInt for {same} of {formats} GAL formats, {integer.Count} integer targets, substitutes {othersNotInteger}");
            report["table"] = new Dictionary<string, object>
            {
                ["galFormats"] = formats, ["sameAsIsInt"] = same, ["integerTargets"] = integer.Count, ["substitutesNotInteger"] = othersNotInteger,
            };
        }

        // A draw's state as PipelineBase builds it: colour targets in increasing slots (their Vulkan formats in that order, the
        // depth-stencil one after them), the mask by the rule, the blend state count up to the last slot, blending on at random.
        PipelineState DrawState(out int[] slots)
        {
            var state = new PipelineState();
            state.Initialize(false);
            state.StagesCount = 2;
            int count = random.Next(0, 9);
            slots = Enumerable.Range(0, 8).OrderBy(_ => random.Next()).Take(count).OrderBy(x => x).ToArray();
            uint mask = 0;
            for (int i = 0; i < count; i++)
            {
                var f = random.Next(4) == 0 ? Ryujinx.Graphics.GAL.Format.R16Uint : colorFormats[random.Next(colorFormats.Length)];
                state.Internal.AttachmentFormats[i] = f == Ryujinx.Graphics.GAL.Format.R4G4B4A4Unorm && random.Next(2) == 0
                    ? Silk.NET.Vulkan.Format.R4G4B4A4UnormPack16 : FormatTable.GetFormat(f);
                mask |= IsInt(f) ? 1u << slots[i] : 0u;
            }
            state.HasDepthStencil = random.Next(2) == 0;
            if (state.HasDepthStencil) state.Internal.AttachmentFormats[count] = FormatTable.GetFormat(depthFormats[random.Next(depthFormats.Length)]);
            state.Internal.AttachmentIntegerFormatMask = mask;
            state.ColorBlendAttachmentStateCount = count == 0 ? 0u : (uint)(slots[^1] + 1);
            for (int s = 0; s < 8; s++)
            {
                state.Internal.ColorBlendAttachmentState[s] = new Silk.NET.Vulkan.PipelineColorBlendAttachmentState(
                    random.Next(2) == 1, Silk.NET.Vulkan.BlendFactor.SrcAlpha, Silk.NET.Vulkan.BlendFactor.OneMinusSrcAlpha,
                    Silk.NET.Vulkan.BlendOp.Add, Silk.NET.Vulkan.BlendFactor.One, Silk.NET.Vulkan.BlendFactor.Zero,
                    Silk.NET.Vulkan.BlendOp.Add, (Silk.NET.Vulkan.ColorComponentFlags)15);
            }
            state.Topology = (Silk.NET.Vulkan.PrimitiveTopology)random.Next(4);
            return state;
        }

        (bool Ok, PipelineUid Key, int Counted) Read(byte[] variant)
        {
            var read = new PipelineState();
            read.Initialize(false);
            Span<int> slots = stackalloc int[8];
            int before = Count();
            bool ok = read.TryReadVariant(variant, slots, out _);
            return (ok, read.Internal, Count() - before);
        }

        {
            // 2000 draws' states read back unchanged and uncounted; 1000 recorded with another mask read back with the draw's,
            // each counted once; a variant refused (truncated) is not counted.
            int drawn = 0, sameKey = 0, uncounted = 0, otherMask = 0, readAsDrawn = 0, countedOnce = 0, oracle = 0, integerDrawn = 0;
            for (int n = 0; n < 3000; n++)
            {
                PipelineState state = DrawState(out int[] slots);
                PipelineUid drawKey = state.Internal;
                oracle += DrawMask(state.Internal.AttachmentFormats.AsSpan(), slots, integer) == drawKey.AttachmentIntegerFormatMask ? 1 : 0;
                integerDrawn += drawKey.AttachmentIntegerFormatMask != 0 ? 1 : 0;
                if (n < 2000)
                {
                    var (ok, key, counted) = Read(state.WriteVariant(slots));
                    drawn++;
                    sameKey += ok && key.Equals(ref drawKey) ? 1 : 0;
                    uncounted += ok && counted == 0 ? 1 : 0;
                }
                else
                {
                    state.Internal.AttachmentIntegerFormatMask ^= (uint)random.Next(1, 256);
                    var (ok, key, counted) = Read(state.WriteVariant(slots));
                    otherMask++;
                    readAsDrawn += ok && key.Equals(ref drawKey) && key.GetHashCode() == drawKey.GetHashCode() ? 1 : 0;
                    countedOnce += ok && counted == 1 ? 1 : 0;
                }
            }
            PipelineState sample = DrawState(out int[] sampleSlots);
            while (sampleSlots.Length == 0) sample = DrawState(out sampleSlots);
            sample.Internal.AttachmentIntegerFormatMask ^= 1u << sampleSlots[0];
            byte[] whole = sample.WriteVariant(sampleSlots);
            var refused = Read(whole[..^1]);
            bool refusedUncounted = !refused.Ok && refused.Counted == 0;
            require(oracle == 3000, $"integer mask: the draw states follow the GAL rule ({oracle})");
            require(sameKey == drawn && uncounted == drawn, $"integer mask: draw states read back unchanged {sameKey}, uncounted {uncounted} of {drawn}");
            require(readAsDrawn == otherMask && countedOnce == otherMask, $"integer mask: another mask read as the draw's {readAsDrawn}, counted once {countedOnce} of {otherMask}");
            require(refusedUncounted, "integer mask: a refused variant is not counted");
            report["codec"] = new Dictionary<string, object>
            {
                ["drawStates"] = drawn, ["sameKey"] = sameKey, ["uncounted"] = uncounted, ["withIntegerTarget"] = integerDrawn,
                ["otherMask"] = otherMask, ["readAsDrawn"] = readAsDrawn, ["countedOnce"] = countedOnce, ["refusedUncounted"] = refusedUncounted,
            };
        }

        {
            // The case of plan 748 rank 18: an R16_UINT target in slot 1 behind an RGBA8 one, blending on in both, recorded with
            // the mask 0: read back with the slot-1 bit, the key of the draw (whose blending CreateGraphicsPipeline turns off
            // for that slot under MoltenVK).
            var state = new PipelineState();
            state.Initialize(false);
            state.StagesCount = 2;
            state.ColorBlendAttachmentStateCount = 2;
            state.Internal.AttachmentFormats[0] = FormatTable.GetFormat(Ryujinx.Graphics.GAL.Format.R8G8B8A8Unorm);
            state.Internal.AttachmentFormats[1] = FormatTable.GetFormat(Ryujinx.Graphics.GAL.Format.R16Uint);
            for (int s = 0; s < 2; s++)
            {
                state.Internal.ColorBlendAttachmentState[s] = new Silk.NET.Vulkan.PipelineColorBlendAttachmentState(
                    true, Silk.NET.Vulkan.BlendFactor.SrcAlpha, Silk.NET.Vulkan.BlendFactor.OneMinusSrcAlpha, Silk.NET.Vulkan.BlendOp.Add,
                    Silk.NET.Vulkan.BlendFactor.One, Silk.NET.Vulkan.BlendFactor.Zero, Silk.NET.Vulkan.BlendOp.Add, (Silk.NET.Vulkan.ColorComponentFlags)15);
            }
            state.Internal.AttachmentIntegerFormatMask = 0b10;
            PipelineUid drawKey = state.Internal;
            state.Internal.AttachmentIntegerFormatMask = 0;
            var (ok, key, counted) = Read(state.WriteVariant(new[] { 0, 1 }));
            bool asDrawn = ok && key.Equals(ref drawKey);
            require(asDrawn && key.AttachmentIntegerFormatMask == 0b10 && counted == 1, "integer mask: the R16_UINT case reads back with the draw's mask");
            report["r16"] = new Dictionary<string, object> { ["recordedMask"] = 0, ["readMask"] = key.AttachmentIntegerFormatMask, ["asDrawn"] = asDrawn, ["counted"] = counted };
        }

        {
            // The journal: session 1 records 6 draws' states and 3 states with another mask; session 2 replays all 9 through a
            // target that reads them as ShaderCollection's Schedule does: every key is its draw's, the summary counts 3 for the
            // session; session 3 counts 0 before any replay.
            var s1 = Open(root, "mask");
            var expected = new Dictionary<ulong, PipelineUid>();
            for (int v = 0; v < 9; v++)
            {
                PipelineState state = DrawState(out int[] slots);
                while (slots.Length == 0) state = DrawState(out slots);
                state.LineWidth = 1f + v; // distinct variants
                PipelineUid drawKey = state.Internal;
                if (v >= 6) state.Internal.AttachmentIntegerFormatMask ^= 1u << slots[^1];
                byte[] variant = state.WriteVariant(slots);
                expected[PipelineVariantJournal.Checksum64(variant)] = drawKey;
                s1.NoteLate(0x60, variant, 10 + v, joined: false);
            }
            Settle(root, "mask");
            var s2 = Open(root, "mask");
            int before = s2.IntegerMasksRecomputed;
            var target = new ReadTarget();
            s2.Offer(0x60, target);
            for (int i = 0; i < 400 && s2.Replayed < 9; i++) Thread.Sleep(10);
            int keysAsDrawn = 0;
            foreach (var (id, drawn) in expected)
            {
                PipelineUid drawKey = drawn;
                keysAsDrawn += target.Keys.TryGetValue(id, out PipelineUid key) && key.Equals(ref drawKey) ? 1 : 0;
            }
            string summary = s2.Summary("test");
            var s3 = Open(root, "mask");
            string next = s3.Summary("test");
            require(s2.Loaded == 9 && s2.Replayed == 9 && keysAsDrawn == 9, $"integer mask: replayed {s2.Replayed} of {s2.Loaded}, keys as drawn {keysAsDrawn}");
            require(before == 0 && s2.IntegerMasksRecomputed == 3 && summary.Contains("still planned 0 of 9, integer masks recomputed 3. Journal: "),
                "integer mask: the session's summary counts its 3 recomputes: " + summary);
            require(s3.IntegerMasksRecomputed == 0 && next.Contains(", integer masks recomputed 0. Journal: "), "integer mask: the next session counts its own: " + next);
            report["journal"] = new Dictionary<string, object>
            {
                ["planned"] = s2.Loaded, ["replayed"] = s2.Replayed, ["keysAsDrawn"] = keysAsDrawn, ["recomputed"] = s2.IntegerMasksRecomputed,
                ["nextSession"] = s3.IntegerMasksRecomputed, ["summary"] = summary, ["nextSummary"] = next,
            };
        }
        return report;
    }
#endif
}
