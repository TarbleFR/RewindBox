// Scenarios for melonx_pipeline_cache_persist_test.py on the variant's real PipelineCacheManager.cs (control: Core 681
// postimage; candidate: with adapt_pipeline_cache_persist, CANDIDATE). The Vulkan double is
// test/melonx_main_cache_checkpoint/Double.cs. "Pause" is what the host pause callback does in each variant: nothing in
// the control, CheckpointMainOnPause (on a thread-pool thread in production) in the candidate.
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

const long MiB = 1024 * 1024;
const string Key = "00000000-00000000-00000000";
var report = new Dictionary<string, object> { ["variant"] = args[0] };
string root = Path.Combine(Path.GetTempPath(), "melonx-pipeline-cache-persist-" + Environment.ProcessId);
int sessions = 0;

(PipelineCacheManager Manager, Vk Vk, string MainFile) Session(long mainBytes)
{
    string directory = Path.Combine(root, "session" + sessions++);
    string mainFile = Path.Combine(directory, "cache", "vulkan", $"pipeline-{Key}.vkpc");
    Directory.CreateDirectory(Path.GetDirectoryName(mainFile));
    using (var file = File.Create(mainFile)) file.SetLength(mainBytes);
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = directory;
    var vk = new Vk();
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    Events.Clear();
    return (new PipelineCacheManager(vk, new VulkanPhysicalDevice(), default, 2, mainLock), vk, mainFile);
}

void Pause(PipelineCacheManager manager)
{
#if CANDIDATE
    manager.CheckpointMainOnPause();
#endif
}

void Age(PipelineCacheManager manager) =>
    typeof(PipelineCacheManager).GetField("_mainCheckpointTimestamp", BindingFlags.Instance | BindingFlags.NonPublic)
        .SetValue(manager, Environment.TickCount64 - 200_000);

double M(string path) => Math.Round(new FileInfo(path).Length / (double)MiB, 2);

void RenderCreations(PipelineCacheManager manager, Vk vk, int count)
{
    for (int i = 0; i < count; i++) { vk.Grow(manager.MainCache, 256 * 1024); manager.NotifyMainPipelineCreated(); }
}

double WaitForGrowth(string path, double before, int timeoutMs)
{
    var watch = Stopwatch.StartNew();
    while (watch.ElapsedMilliseconds < timeoutMs && M(path) == before) Thread.Sleep(5);
    Thread.Sleep(20);
    return M(path);
}

// A: three render-thread pipelines after the last write (fewer than any checkpoint minimum), then the app is paused.
{
    var (manager, vk, mainFile) = Session(10 * MiB);
    RenderCreations(manager, vk, 3);
    Pause(manager);
    report["pausedAfterNewPipelines"] = new Dictionary<string, object> { ["mainFileMiB"] = M(mainFile) };
    // B: paused again with nothing new: no second write.
    int reads = Events.Snapshot().Count(e => e.Text.StartsWith("data main begin"));
    Pause(manager);
    report["pausedAgainUnchanged"] = new Dictionary<string, object>
    {
        ["extraWrites"] = Events.Snapshot().Count(e => e.Text.StartsWith("data main begin")) - reads,
    };
    manager.Dispose();
}

// C: render-thread pipelines only (no worker activity), past the interval: 8 of them make a checkpoint due.
{
    var (manager, vk, mainFile) = Session(10 * MiB);
    Age(manager);
    RenderCreations(manager, vk, 7);
    double afterSeven = WaitForGrowth(mainFile, 10, 300);
    RenderCreations(manager, vk, 1);
    double afterEight = WaitForGrowth(mainFile, afterSeven, 3000);
    string renderThread = Thread.CurrentThread.Name ?? "unnamed";
    report["renderThreadTrigger"] = new Dictionary<string, object>
    {
        ["afterSevenMiB"] = afterSeven, ["afterEightMiB"] = afterEight,
        ["writtenOffTheCreatingThread"] = Events.Snapshot().Where(e => e.Text.StartsWith("data main begin")).All(e => e.Thread != renderThread),
    };
    manager.Dispose();
}

// D: within the interval, 20 render-thread pipelines do not checkpoint.
{
    var (manager, vk, mainFile) = Session(10 * MiB);
    RenderCreations(manager, vk, 20);
    report["withinInterval"] = new Dictionary<string, object> { ["mainFileMiB"] = WaitForGrowth(mainFile, 10, 300) };
    manager.Dispose();
}

#if CANDIDATE
// E: a slow pause write (400 ms) in flight when the session is disposed: Dispose waits for it.
{
    var (manager, vk, mainFile) = Session(10 * MiB);
    vk.SlowMainDataMs = 400;
    RenderCreations(manager, vk, 2);
    var writer = new Thread(() => manager.CheckpointMainOnPause()) { Name = "pause" };
    writer.Start();
    var spin = Stopwatch.StartNew();
    while (!Events.Snapshot().Any(e => e.Text.StartsWith("data main begin")) && spin.ElapsedMilliseconds < 3000) Thread.Sleep(1);
    var watch = Stopwatch.StartNew();
    manager.Dispose();
    long disposeMs = watch.ElapsedMilliseconds;
    writer.Join();
    var events = Events.Snapshot();
    report["disposeDuringPauseWrite"] = new Dictionary<string, object>
    {
        ["disposeWaitedMs"] = disposeMs,
        ["writeCompleted"] = events.Any(e => e.Text == "data main end"),
        ["mainFileMiB"] = M(mainFile),
    };
}
#endif

report["errors"] = Ryujinx.Common.Logging.Logger.Error.Lines;
report["pauseLine"] = Ryujinx.Common.Logging.Logger.Info.Messages.FirstOrDefault(m => m.Contains("checkpointed on pause"));
Directory.Delete(root, true);
Console.WriteLine(JsonSerializer.Serialize(report));
