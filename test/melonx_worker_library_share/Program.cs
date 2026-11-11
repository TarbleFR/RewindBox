// Scenarios for melonx_worker_library_share_test.py on the variant's real PipelineCacheManager.cs (control: the Core 715
// preparation; candidate: with adapt_worker_library_share), over the content double of test/melonx_pipeline_snapshot_retire
// (an entry = a Metal library of one shader module and configuration; vkMergePipelineCaches adds the missing ones).
// A worker request is modelled as MeloNX makes it with MoltenVK v1.4.2: the libraries it needs are looked up in the main
// cache (PipelineState.TryCreateFromMainCache, VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT); when main lacks
// one, the pipeline is created in the worker's own cache, where each missing library is compiled (counted) unless that
// cache holds it; then PipelineCacheManager.WorkerCompiledOwn (candidate only) and NotifyWorkerPipelineCreated, on the
// worker's thread. Isolated directories, never a player's cache.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using FixtureSupport;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

string variant = args[0];
var report = new Dictionary<string, object> { ["variant"] = variant };
string root = Path.Combine(Path.GetTempPath(), $"melonx-worker-library-share-{Environment.ProcessId}-{variant}");
const string Title = "0100F7E00C70E000";
const int EntryBytes = 32 * 1024;
const uint Driver = 10402;
VulkanRenderer.PipelineCacheScope = () => Title;
FieldInfo compiledOwn = typeof(PipelineCacheManager).GetField("WorkerCompiledOwn", BindingFlags.NonPublic | BindingFlags.Static);
bool candidate = compiledOwn != null;
if ((variant == "candidate") != candidate) throw new InvalidOperationException("variant and source disagree");

string MainPath(string dir) => Path.Combine(dir, "cache", "vulkan", $"pipeline-{0x106B:X8}-{0x1A2B3C4D:X8}-{Driver:X8}-{Title.ToLowerInvariant()}.vkpc");
string WorkerPath(string dir, int index) => Path.ChangeExtension(MainPath(dir), null) + $".worker{index}.vkpc";

(PipelineCacheManager Manager, Vk Vk, Lock MainLock) Open(string dir, int refuseIntact = 0)
{
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = dir;
    var vk = new Vk { RefuseIntact = refuseIntact };
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    var properties = new PhysicalDeviceProperties { VendorID = vk.Vendor, DeviceID = vk.DeviceId, DriverVersion = Driver };
    unsafe { for (int i = 0; i < 16; i++) properties.PipelineCacheUuid[i] = vk.Uuid[i]; }
    var manager = new PipelineCacheManager(vk, new VulkanPhysicalDevice { PhysicalDeviceProperties = properties }, default, 2, mainLock);
    var watch = Stopwatch.StartNew();
    while (manager.MainLoadPending && watch.ElapsedMilliseconds < 60_000) Thread.Sleep(2);
    return (manager, vk, mainLock);
}

long Counter(PipelineCacheManager manager, string name) =>
    candidate ? Convert.ToInt64(typeof(PipelineCacheManager).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance).GetValue(manager)) : 0;

// One worker request: returns how many libraries it compiled.
int Request((PipelineCacheManager Manager, Vk Vk, Lock MainLock) l, int worker, ulong[] libraries, ref int mainHits, int compileMs = 0)
{
    var main = l.Vk.Entries(l.Manager.MainCache);
    if (libraries.All(main.ContainsKey) && l.MainLock.TryEnter())
    {
        l.MainLock.Exit();
        mainHits++;
        l.Manager.NotifyWorkerPipelineCreated(worker);
        return 0;
    }
    PipelineCache own = l.Manager.GetWorkerCache(worker);
    var held = l.Vk.Entries(own);
    int compiled = 0;
    foreach (ulong id in libraries)
    {
        if (!held.ContainsKey(id)) { if (compileMs > 0) Thread.Sleep(compileMs); l.Vk.Add(own, id, EntryBytes); compiled++; }
    }
    compiledOwn?.SetValue(null, true);
    l.Manager.NotifyWorkerPipelineCreated(worker);
    return compiled;
}

HashSet<ulong> OnDisk(string dir)
{
    var vk = new Vk();
    var all = new HashSet<ulong>();
    foreach (string path in new[] { MainPath(dir), WorkerPath(dir, 0), WorkerPath(dir, 1) })
    {
        var entries = CacheFormat.ReadFile(path, vk.Vendor, vk.DeviceId, vk.Uuid, out _);
        if (entries != null) all.UnionWith(entries.Keys);
    }
    return all;
}

// The variants of 12 new programs: (fragment library, vertex library), alternating between the two workers.
List<(int Worker, ulong[] Libraries)> Program12(ulong baseId)
{
    var list = new List<(int, ulong[])>();
    ulong vertexIndex = baseId + 1000, vertexBuffer = baseId + 1001;
    for (ulong p = 0; p < 12; p++)
    {
        ulong fragment = baseId + p;
        list.Add((0, new[] { vertexIndex, fragment }));
        list.Add((1, new[] { vertexIndex, fragment }));
        list.Add((0, new[] { vertexIndex, fragment }));
        list.Add((1, new[] { vertexIndex, fragment }));
        list.Add((1, new[] { vertexBuffer, fragment }));
    }
    return list;
}

// S1: alternating variants, one session, then the close and a second launch.
{
    string dir = Path.Combine(root, "alternating");
    var l = Open(dir);
    int compiled = 0, hits = 0;
    var mergedBefore = l.Vk.MergedSourceEntries;
    foreach (var (worker, libraries) in Program12(1)) compiled += Request(l, worker, libraries, ref hits);
    long mergedEntries = l.Vk.MergedSourceEntries - mergedBefore;
    int mainEntries = l.Vk.Entries(l.Manager.MainCache).Count;
    long shares = Counter(l.Manager, "_shares");
    double shareMs = Counter(l.Manager, "_shareTicks") * 1000.0 / Stopwatch.Frequency;
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    var disk = OnDisk(dir);
    var again = Open(dir);
    int hitsAgain = 0, compiledAgain = 0;
    foreach (var (worker, libraries) in Program12(1)) compiledAgain += Request(again, worker, libraries, ref hitsAgain);
    again.Manager.MergeAndSave();
    again.Manager.Dispose();
    report["alternating"] = new Dictionary<string, object>
    {
        ["requests"] = 60, ["librariesCompiled"] = compiled, ["distinctLibraries"] = 14, ["mainHits"] = hits,
        ["mainEntriesBeforeClose"] = mainEntries, ["shares"] = shares, ["shareMs"] = Math.Round(shareMs, 3),
        ["entriesIteratedByMerges"] = mergedEntries, ["onDisk"] = disk.Count, ["onDiskAll"] = Enumerable.Range(1, 12).All(p => disk.Contains((ulong)p)) && disk.Contains(1001) && disk.Contains(1002),
        ["nextLaunchCompiled"] = compiledAgain, ["nextLaunchMainHits"] = hitsAgain,
    };
}

// S2: two workers ask for the same new program at the same moment: both compile it (nothing published yet).
{
    string dir = Path.Combine(root, "concurrent");
    var l = Open(dir);
    int compiled = 0, hits = 0;
    var barrier = new Barrier(2);
    int[] counts = new int[2];
    var threads = Enumerable.Range(0, 2).Select(w => new Thread(() =>
    {
        int localHits = 0;
        barrier.SignalAndWait();
        counts[w] = Request(l, w, new ulong[] { 5000, 5001 }, ref localHits, compileMs: 100); // both compiling at once
    }) { Name = "worker" + w }).ToArray();
    foreach (var t in threads) t.Start();
    foreach (var t in threads) t.Join();
    compiled = counts.Sum();
    int after = Request(l, 0, new ulong[] { 5000, 5001 }, ref hits) + Request(l, 1, new ulong[] { 5000, 5001 }, ref hits);
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    report["concurrent"] = new Dictionary<string, object> { ["simultaneousCompiled"] = compiled, ["laterCompiled"] = after, ["laterMainHits"] = hits };
}

// S3: the main lock is held (a render-thread creation, a checkpoint) when the worker would publish: not shared then; the
// next own compilation publishes both.
{
    string dir = Path.Combine(root, "busy");
    var l = Open(dir);
    int hits = 0;
    using var held = new ManualResetEventSlim();
    using var release = new ManualResetEventSlim();
    var holder = new Thread(() => { lock (l.MainLock) { held.Set(); release.Wait(); } }) { Name = "render" };
    holder.Start();
    held.Wait();
    int first = Request(l, 0, new ulong[] { 6000 }, ref hits);
    bool inMainWhileBusy = l.Vk.Entries(l.Manager.MainCache).ContainsKey(6000);
    release.Set();
    holder.Join();
    int second = Request(l, 0, new ulong[] { 6001 }, ref hits);
    var main = l.Vk.Entries(l.Manager.MainCache);
    report["busy"] = new Dictionary<string, object>
    {
        ["inMainWhileBusy"] = inMainWhileBusy, ["busyCount"] = Counter(l.Manager, "_sharesBusy"),
        ["bothInMainAfter"] = main.ContainsKey(6000) && main.ContainsKey(6001), ["compiled"] = first + second,
    };
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
}

// S4: a main snapshot refused once leaves main Frozen this session (adapt_pipeline_snapshot_retire): nothing is merged
// into it during play.
{
    string dir = Path.Combine(root, "frozen");
    var seed = Open(dir);
    seed.Vk.Add(seed.Manager.MainCache, 7000, EntryBytes);
    seed.Manager.NotifyMainPipelineCreated();
    seed.Manager.MergeAndSave();
    seed.Manager.Dispose();
    var l = Open(dir, refuseIntact: 1);
    int hits = 0;
    long addedBefore = l.Vk.MergeAddedEntries;
    int compiled = Request(l, 0, new ulong[] { 7001 }, ref hits) + Request(l, 1, new ulong[] { 7001 }, ref hits);
    long addedToMain = l.Vk.MergeAddedEntries - addedBefore;
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    report["frozen"] = new Dictionary<string, object>
    {
        ["addedToMainDuringPlay"] = addedToMain, ["compiled"] = compiled, ["mainFileKept"] = OnDisk(dir).Contains(7000),
    };
}

// S5: a worker cache recycled after its content was published (over its budget): nothing lost; then the close.
{
    string dir = Path.Combine(root, "recycle");
    var l = Open(dir);
    int hits = 0, compiled = 0;
    // 128 MiB per worker (TotalCacheBudget - MainCacheBudget over two workers), 32 KiB entries: past 4 096 it recycles.
    for (ulong i = 0; i < 4300; i++) compiled += Request(l, 0, new ulong[] { 100_000 + i }, ref hits);
    var main = l.Vk.Entries(l.Manager.MainCache);
    bool allInMain = Enumerable.Range(0, 4300).All(i => main.ContainsKey(100_000 + (ulong)i));
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    var disk = OnDisk(dir);
    report["recycle"] = new Dictionary<string, object>
    {
        ["compiled"] = compiled, ["allInMainBeforeClose"] = allInMain,
        ["allOnDisk"] = Enumerable.Range(0, 4300).All(i => disk.Contains(100_000 + (ulong)i)),
        ["workerEntriesAfter"] = 0,
    };
}

// S6: render-thread creations (main or side cache through EnterMainCreation) while two workers publish: no lost entry.
// Whatever the speed of the three threads: the render thread starts once both workers have published a first program
// and makes its 2 000 creations; each worker publishes its 300 programs, then asks for them again until the render
// thread is done (120 s at most), so every creation happens while the workers publish. (Until Core 731 the render
// thread was stopped when the workers finished, and the count of 2 000 held only if it was the faster: 1 878 on a
// loaded runner, with every entry on disk.)
{
    string dir = Path.Combine(root, "threads");
    var l = Open(dir);
    var workersPublishing = new CountdownEvent(2);
    var renderDone = new ManualResetEventSlim();
    var renderIds = new List<ulong>();
    var render = new Thread(() =>
    {
        workersPublishing.Wait();
        ulong id = 900_000;
        while (renderIds.Count < 2000)
        {
            l.Manager.EnterMainCreation(l.MainLock, false, out PipelineCache target);
            try { l.Vk.Add(target, id, EntryBytes); renderIds.Add(id++); }
            finally { l.Manager.ExitMainCreation(l.MainLock, target); }
            l.Manager.NotifyMainPipelineCreated();
            Thread.Sleep(0);
        }
        renderDone.Set();
    }) { Name = "render" };
    render.Start();
    var watch = Stopwatch.StartNew();
    var requests = new int[2];
    var workers = Enumerable.Range(0, 2).Select(w => new Thread(() =>
    {
        int localHits = 0;
        for (ulong i = 0; i < 300 || (!renderDone.IsSet && watch.ElapsedMilliseconds < 120_000); i++)
        {
            Request(l, w, new ulong[] { 800_000 + (ulong)w * 1000 + (i % 300), 800_500 + (i % 40) }, ref localHits);
            if (++requests[w] == 1) workersPublishing.Signal();
        }
    }) { Name = "worker" + w }).ToArray();
    foreach (var t in workers) t.Start();
    foreach (var t in workers) t.Join();
    bool renderFinished = render.Join(120_000);
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    var disk = OnDisk(dir);
    bool allWorker = Enumerable.Range(0, 2).All(w => Enumerable.Range(0, 300).All(i => disk.Contains(800_000 + (ulong)w * 1000 + (ulong)i)));
    report["threads"] = new Dictionary<string, object>
    {
        ["renderCreations"] = renderIds.Count, ["allRenderOnDisk"] = renderIds.All(disk.Contains), ["allWorkerOnDisk"] = allWorker,
        ["renderFinished"] = renderFinished, ["workerRequests"] = requests,
    };
}

// S7: another holder (a checkpoint) announces and holds the main lock while a worker fails to take it for a share: the
// announcement stays, and a render-thread creation goes to the side cache at once instead of waiting for the lock.
{
    string dir = Path.Combine(root, "overlap");
    var l = Open(dir);
    var counter = typeof(PipelineCacheManager).GetField("_mainCheckpointHolders", BindingFlags.NonPublic | BindingFlags.Instance);
    var flag = typeof(PipelineCacheManager).GetField("_mainCheckpointInProgress", BindingFlags.NonPublic | BindingFlags.Instance);
    void Announce(int delta)
    {
        if (counter != null) counter.SetValue(l.Manager, (int)counter.GetValue(l.Manager) + delta);
        else flag.SetValue(l.Manager, delta > 0);
    }
    using var held = new ManualResetEventSlim();
    using var release = new ManualResetEventSlim();
    var holder = new Thread(() => { Announce(1); lock (l.MainLock) { held.Set(); release.Wait(); } Announce(-1); }) { Name = "checkpoint" };
    holder.Start();
    held.Wait();
    int hits = 0;
    int compiled = Request(l, 0, new ulong[] { 9000 }, ref hits);   // its share finds the lock held
    bool announcedAfter = l.Manager.MainCheckpointInProgress;
    PipelineCache target = default;
    double routeMs = -1;
    using var routed = new ManualResetEventSlim();
    var render = new Thread(() =>
    {
        var watch = Stopwatch.StartNew();
        l.Manager.EnterMainCreation(l.MainLock, false, out target);
        routeMs = watch.Elapsed.TotalMilliseconds;
        routed.Set();
        l.Manager.ExitMainCreation(l.MainLock, target);
    }) { Name = "render" };
    render.Start();
    bool returnedWhileHeld = routed.Wait(500);
    bool toSide = returnedWhileHeld && target.Handle != 0 && target.Handle != l.Manager.MainCache.Handle;
    release.Set();
    holder.Join();
    render.Join();
    bool withdrawnAfter = !l.Manager.MainCheckpointInProgress;
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    report["overlap"] = new Dictionary<string, object>
    {
        ["compiled"] = compiled, ["announcementKept"] = announcedAfter, ["renderReturnedWhileHeld"] = returnedWhileHeld,
        ["renderToSideCache"] = toSide, ["renderRouteMs"] = Math.Round(routeMs, 2), ["announcementWithdrawnAfter"] = withdrawnAfter,
    };
}

// S8: main's estimate near its budget: the share is refused (counted), the worker keeps its library; then room again:
// shared, and main's estimate credited with the worker's growth (an estimate, not native memory).
if (candidate)
{
    string dir = Path.Combine(root, "budget");
    var l = Open(dir);
    var mainState = typeof(PipelineCacheManager).GetField("_mainState", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(l.Manager);
    var stateType = mainState.GetType();
    long Estimate() => (long)stateType.GetProperty("EstimatedBytes").GetValue(mainState);
    long budget = (long)stateType.GetField("Budget").GetValue(mainState);
    void Measure(long bytes) => stateType.GetMethod("OnMeasured").Invoke(mainState, new object[] { bytes });
    int hits = 0;
    Measure(budget - 1024);
    Request(l, 0, new ulong[] { 9100 }, ref hits);
    bool refusedKeptOut = !l.Vk.Entries(l.Manager.MainCache).ContainsKey(9100);
    long overBudget = Counter(l.Manager, "_sharesBudget");
    Measure(1024 * 1024);
    long before = Estimate();
    Request(l, 0, new ulong[] { 9101 }, ref hits);
    long after = Estimate();
    var main = l.Vk.Entries(l.Manager.MainCache);
    report["budget"] = new Dictionary<string, object>
    {
        ["refusedKeptOut"] = refusedKeptOut, ["overBudget"] = overBudget, ["sharedAfterRoom"] = main.ContainsKey(9100) && main.ContainsKey(9101),
        ["estimateBefore"] = before, ["estimateAfter"] = after, ["credited"] = after - before,
    };
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
}

// S9 (review of Core 717): a merge's credit, then a real measure, then render-thread pipelines: the bytes per pipeline are
// not learnt from the span that held the merge, and the estimate never falls below the measured size.
if (candidate)
{
    string dir = Path.Combine(root, "estimate");
    var l = Open(dir);
    var mainState = typeof(PipelineCacheManager).GetField("_mainState", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(l.Manager);
    var type = mainState.GetType();
    long Estimate() => (long)type.GetProperty("EstimatedBytes").GetValue(mainState);
    long PerPipeline() => (long)type.GetProperty("BytesPerPipeline").GetValue(mainState);
    void Measure(long bytes) => type.GetMethod("OnMeasured").Invoke(mainState, new object[] { bytes });
    void Merged(long bytes) => type.GetMethod("OnMerged").Invoke(mainState, new object[] { bytes });
    Measure(10L << 20);
    long perBefore = PerPipeline();
    Merged(64L << 20);                                   // credited upper bound of a share
    for (int i = 0; i < 4; i++) l.Manager.NotifyMainPipelineCreated();
    long creditedEstimate = Estimate();
    long actual = (10L << 20) + (2L << 20);              // the share added less than its bound
    Measure(actual);
    long perAfter = PerPipeline();
    for (int i = 0; i < 16; i++) l.Manager.NotifyMainPipelineCreated();
    long laterEstimate = Estimate();
    report["estimate"] = new Dictionary<string, object>
    {
        ["perPipelineBefore"] = perBefore, ["perPipelineAfter"] = perAfter, ["creditedEstimate"] = creditedEstimate,
        ["actual"] = actual, ["laterEstimate"] = laterEstimate,
    };
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
}

report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Messages.Select(m => m.Length > 160 ? m[..160] : m).Distinct().Take(20).ToList();
report["shareLines"] = Ryujinx.Common.Logging.Logger.Info.Messages.Where(m => m.Contains("adapt_worker_library_share")).Take(10).ToList();
try { Directory.Delete(root, true); } catch (IOException) { }
Console.WriteLine(JsonSerializer.Serialize(report));
