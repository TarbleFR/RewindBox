// Scenarios for melonx_main_cache_checkpoint_test.py on the variant's real PipelineCacheManager.cs (control: Core 671
// preparation; candidate: with adapt_main_cache_checkpoint, DefineConstants CANDIDATE). Prints one JSON report.
// The 180 s interval is not waited for: the candidate's private checkpoint clock is moved back by reflection.
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
string root = Path.Combine(Path.GetTempPath(), "melonx-main-cache-checkpoint-" + Environment.ProcessId);
int sessions = 0;

(PipelineCacheManager Manager, Vk Vk, Lock MainLock, string Directory) NewManager()
{
    string directory = Path.Combine(root, "session" + sessions++);
    Directory.CreateDirectory(directory);
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = directory;
    var vk = new Vk();
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    var manager = new PipelineCacheManager(vk, new VulkanPhysicalDevice(), default, 2, mainLock);
    return (manager, vk, mainLock, directory);
}

string MainFile(string directory)
{
    string folder = Path.Combine(directory, "cache", "vulkan");
    return Directory.Exists(folder) ? Directory.GetFiles(folder, "pipeline-*.vkpc").FirstOrDefault(f => !f.Contains(".worker")) : null;
}

void MainPipelines(PipelineCacheManager manager, Vk vk, int count)
{
    for (int i = 0; i < count; i++)
    {
        // A pipeline the render thread created in the main cache during play.
        vk.Grow(manager.MainCache, 64 * 1024);
        manager.NotifyMainPipelineCreated();
    }
}

void Age(PipelineCacheManager manager)
{
#if CANDIDATE
    typeof(PipelineCacheManager).GetField("_mainCheckpointTimestamp", BindingFlags.Instance | BindingFlags.NonPublic)
        .SetValue(manager, Environment.TickCount64 - 200_000);
#endif
}

// Runs one worker completion on a named worker thread and returns its duration.
long Worker(PipelineCacheManager manager, Vk vk, int index)
{
    long duration = 0;
    var thread = new Thread(() =>
    {
        vk.Grow(manager.GetWorkerCache(index), 16 * 1024);
        var watch = Stopwatch.StartNew();
        manager.NotifyWorkerPipelineCreated(index);
        duration = watch.ElapsedMilliseconds;
    }) { Name = "worker" + index };
    thread.Start();
    thread.Join();
    return duration;
}

string[] MainReads() => Events.Snapshot().Where(e => e.Text.StartsWith("data main begin")).Select(e => e.Thread + " " + e.Text).ToArray();

int Infos() => Ryujinx.Common.Logging.Logger.Info.Messages.Count(m => m.Contains("adapt_main_cache_checkpoint"));

// A: 100 main pipelines made in play, the interval elapsed, a worker finishes a pipeline.
{
    Events.Clear();
    var (manager, vk, _, directory) = NewManager();
    MainPipelines(manager, vk, 100);
    Age(manager);
    long ms = Worker(manager, vk, 0);
    string file = MainFile(directory);
    report["played"] = new Dictionary<string, object>
    {
        ["mainFile"] = file != null,
        ["mainFileBytes"] = file != null ? new FileInfo(file).Length : 0,
        ["mainBytes"] = vk.Size(manager.MainCache),
        ["mainReads"] = MainReads(),
        ["workerMs"] = ms,
        ["infoLines"] = Infos(),
    };

    // B: right after, another worker completion with 100 more main pipelines: the interval has not elapsed.
    Events.Clear();
    MainPipelines(manager, vk, 100);
    Worker(manager, vk, 1);
    report["withinInterval"] = new Dictionary<string, object> { ["mainReads"] = MainReads() };
    manager.Dispose();
}

// C: the render thread holds the lock (a pipeline creation); a worker finishes: it does not wait and writes nothing.
{
    Events.Clear();
    var (manager, vk, mainLock, directory) = NewManager();
    MainPipelines(manager, vk, 100);
    Age(manager);
    using var held = new ManualResetEventSlim();
    using var release = new ManualResetEventSlim();
    var render = new Thread(() => { lock (mainLock) { held.Set(); release.Wait(); } }) { Name = "render" };
    render.Start();
    held.Wait();
    long ms = Worker(manager, vk, 0);
    release.Set();
    render.Join();
    bool inProgressAfter = false;
#if CANDIDATE
    inProgressAfter = manager.MainCheckpointInProgress;
#endif
    report["renderHoldsLock"] = new Dictionary<string, object>
    {
        ["workerMs"] = ms, ["mainReads"] = MainReads(), ["mainFile"] = MainFile(directory) != null, ["flagLeftRaised"] = inProgressAfter,
    };

    // D: then the next worker completion checkpoints.
    Events.Clear();
    Worker(manager, vk, 1);
    report["afterRenderReleased"] = new Dictionary<string, object> { ["mainReads"] = MainReads(), ["mainFile"] = MainFile(directory) != null };
    manager.Dispose();
}

// E: fewer than 64 main pipelines and no merge: no checkpoint.
{
    Events.Clear();
    var (manager, vk, _, directory) = NewManager();
    MainPipelines(manager, vk, 10);
    Age(manager);
    Worker(manager, vk, 0);
    report["fewPipelines"] = new Dictionary<string, object> { ["mainReads"] = MainReads(), ["mainFile"] = MainFile(directory) != null };
    manager.Dispose();
}

// F: a slow checkpoint (300 ms): while it runs, the flag is raised and a render-thread TryEnter fails; afterwards both clear.
{
    Events.Clear();
    var (manager, vk, mainLock, directory) = NewManager();
    vk.SlowMainDataMs = 300;
    MainPipelines(manager, vk, 100);
    Age(manager);
    bool flagSeen = false, tryEnterFailedWhileRaised = false;
    var worker = new Thread(() => { vk.Grow(manager.GetWorkerCache(0), 16 * 1024); manager.NotifyWorkerPipelineCreated(0); }) { Name = "worker0" };
    worker.Start();
    var watch = Stopwatch.StartNew();
    while (watch.ElapsedMilliseconds < 2000 && worker.IsAlive)
    {
#if CANDIDATE
        if (manager.MainCheckpointInProgress)
        {
            flagSeen = true;
            if (Events.Snapshot().Any(e => e.Text.StartsWith("data main begin")))
            {
                if (!mainLock.TryEnter()) { tryEnterFailedWhileRaised = true; }
                else { mainLock.Exit(); }
                break;
            }
        }
#endif
        Thread.Sleep(1);
    }

    worker.Join();
    bool raisedAfter = false;
#if CANDIDATE
    raisedAfter = manager.MainCheckpointInProgress;
#endif
    report["slowCheckpoint"] = new Dictionary<string, object>
    {
        ["flagSeen"] = flagSeen, ["renderTryEnterFailedWhileRaised"] = tryEnterFailedWhileRaised, ["flagAfter"] = raisedAfter,
        ["mainFile"] = MainFile(directory) != null,
    };
    manager.Dispose();
}

report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Lines + Ryujinx.Common.Logging.Logger.Error.Lines;
Directory.Delete(root, true);
Console.WriteLine(JsonSerializer.Serialize(report));
