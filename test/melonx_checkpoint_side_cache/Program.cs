// Scenarios for melonx_checkpoint_side_cache_test.py on the variant's real PipelineCacheManager.cs (control: Core 673
// postimage; candidate: with adapt_checkpoint_side_cache, CANDIDATE). The Vulkan double is
// test/melonx_main_cache_checkpoint/Double.cs. A render-thread creation is modelled as the variant's main-cache path:
// control takes the main lock (Core 673 PipelineState: a blocking creation enters it); candidate calls EnterMainCreation.
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

var report = new Dictionary<string, object> { ["variant"] = args[0] };
string root = Path.Combine(Path.GetTempPath(), "melonx-checkpoint-side-cache-" + Environment.ProcessId);
int sessions = 0;

(PipelineCacheManager Manager, Vk Vk, Lock MainLock) NewManager()
{
    string directory = Path.Combine(root, "session" + sessions++);
    Directory.CreateDirectory(directory);
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = directory;
    var vk = new Vk();
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    return (new PipelineCacheManager(vk, new VulkanPhysicalDevice(), default, 2, mainLock), vk, mainLock);
}

void Age(PipelineCacheManager manager) =>
    typeof(PipelineCacheManager).GetField("_mainCheckpointTimestamp", BindingFlags.Instance | BindingFlags.NonPublic)
        .SetValue(manager, Environment.TickCount64 - 200_000);

// One render-thread pipeline creation meant for the main cache; returns (wait ms, created into main, created at all).
(double WaitMs, bool IntoMain, bool Created) Create(PipelineCacheManager manager, Vk vk, Lock mainLock, bool tryOnly)
{
    var watch = Stopwatch.StartNew();
#if CANDIDATE
    bool taken = manager.EnterMainCreation(mainLock, tryOnly, out PipelineCache target);
    double waited = watch.Elapsed.TotalMilliseconds;
    if (!taken) return (waited, false, false);
    vk.Grow(target, 64 * 1024);
    manager.ExitMainCreation(mainLock, target);
    return (waited, target.Handle == manager.MainCache.Handle, true);
#else
    bool taken = tryOnly ? mainLock.TryEnter() : true;
    if (!tryOnly) mainLock.Enter();
    double waited = watch.Elapsed.TotalMilliseconds;
    if (!taken) return (waited, false, false);
    vk.Grow(manager.MainCache, 64 * 1024);
    mainLock.Exit();
    return (waited, true, true);
#endif
}

// A: a 400 ms checkpoint runs on a worker thread; the render thread creates two pipelines (blocking, then try-only) while
// the checkpoint holds the main lock.
{
    Events.Clear();
    var (manager, vk, mainLock) = NewManager();
    vk.SlowMainDataMs = 400;
    for (int i = 0; i < 100; i++) { vk.Grow(manager.MainCache, 64 * 1024); manager.NotifyMainPipelineCreated(); }
    Age(manager);
    long mainBefore = vk.Size(manager.MainCache);
    var worker = new Thread(() => { vk.Grow(manager.GetWorkerCache(0), 16 * 1024); manager.NotifyWorkerPipelineCreated(0); }) { Name = "worker0" };
    worker.Start();
    var spin = Stopwatch.StartNew();
    while (!Events.Snapshot().Any(e => e.Text.StartsWith("data main begin")) && spin.ElapsedMilliseconds < 3000) Thread.Sleep(1);
    (double, bool, bool) blocking = default, tryOnly = default;
    var render = new Thread(() => { blocking = Create(manager, vk, mainLock, false); tryOnly = Create(manager, vk, mainLock, true); }) { Name = "render" };
    render.Start();
    render.Join();
    worker.Join();
    var events = Events.Snapshot();
    int dataEnd = Array.FindIndex(events, e => e.Text == "data main end");
    int merge = Array.FindIndex(events, e => e.Text.StartsWith("merge into main"));
    report["duringCheckpoint"] = new Dictionary<string, object>
    {
        ["blockingWaitMs"] = Math.Round(blocking.Item1, 1), ["blockingIntoMain"] = blocking.Item2, ["blockingCreated"] = blocking.Item3,
        ["tryOnlyWaitMs"] = Math.Round(tryOnly.Item1, 1), ["tryOnlyIntoMain"] = tryOnly.Item2, ["tryOnlyCreated"] = tryOnly.Item3,
        ["mergeAfterSave"] = merge > dataEnd && dataEnd >= 0, ["mergeLine"] = merge >= 0 ? events[merge].Text : null,
        ["mainGrowthBytes"] = vk.Size(manager.MainCache) - mainBefore,
        ["checkpointInProgressAfter"] = manager.MainCheckpointInProgress,
    };
    manager.Dispose();
}

// B: no checkpoint; another creation holds the main lock for 200 ms: a try-only creation fails, a blocking one waits.
{
    Events.Clear();
    var (manager, vk, mainLock) = NewManager();
    using var held = new ManualResetEventSlim();
    var other = new Thread(() => { lock (mainLock) { held.Set(); Thread.Sleep(200); } }) { Name = "other" };
    other.Start();
    held.Wait();
    (double, bool, bool) tryOnly = default, blocking = default;
    var render = new Thread(() => { tryOnly = Create(manager, vk, mainLock, true); blocking = Create(manager, vk, mainLock, false); }) { Name = "render" };
    render.Start();
    render.Join();
    other.Join();
    report["noCheckpoint"] = new Dictionary<string, object>
    {
        ["tryOnlyCreated"] = tryOnly.Item3, ["blockingWaitMs"] = Math.Round(blocking.Item1, 1), ["blockingIntoMain"] = blocking.Item2,
    };
    manager.Dispose();
}

report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Lines + Ryujinx.Common.Logging.Logger.Error.Lines;
Directory.Delete(root, true);
Console.WriteLine(JsonSerializer.Serialize(report));
