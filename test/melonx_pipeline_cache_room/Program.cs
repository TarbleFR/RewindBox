// Scenarios for melonx_pipeline_cache_room_test.py on the variant's real PipelineCacheManager.cs (control: Core 679
// postimage; candidate: with adapt_pipeline_cache_room, CANDIDATE). The Vulkan double is
// test/melonx_main_cache_checkpoint/Double.cs; snapshot files are sparse files of the stated size.
using System;
using System.Collections.Generic;
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
string root = Path.Combine(Path.GetTempPath(), "melonx-pipeline-cache-room-" + Environment.ProcessId);
int sessions = 0;

string Snapshot(string directory, string suffix) => Path.Combine(directory, "cache", "vulkan", $"pipeline-{Key}{suffix}.vkpc");

void Sparse(string path, long bytes)
{
    Directory.CreateDirectory(Path.GetDirectoryName(path));
    using var file = File.Create(path);
    file.SetLength(bytes);
}

long Length(string path) => File.Exists(path) ? new FileInfo(path).Length : -1;

(PipelineCacheManager Manager, Vk Vk, string Directory) Session(long mainBytes, long worker0Bytes, long worker1Bytes)
{
    string directory = Path.Combine(root, "session" + sessions++);
    if (mainBytes > 0) Sparse(Snapshot(directory, ""), mainBytes);
    if (worker0Bytes > 0) Sparse(Snapshot(directory, ".worker0"), worker0Bytes);
    if (worker1Bytes > 0) Sparse(Snapshot(directory, ".worker1"), worker1Bytes);
    Directory.CreateDirectory(directory);
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = directory;
    var vk = new Vk();
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    Ryujinx.Common.Logging.Logger.Info.Messages.Clear();
    Ryujinx.Common.Logging.Logger.Warning.Messages.Clear();
    return (new PipelineCacheManager(vk, new VulkanPhysicalDevice(), default, 2, mainLock), vk, directory);
}

double M(long bytes) => Math.Round(bytes / (double)MiB, 2);

// A: the player's sizes (main 580 MiB, worker snapshots 120 and 100 MiB).
{
    var (manager, vk, _) = Session(580 * MiB, 120 * MiB, 100 * MiB);
    report["startup"] = new Dictionary<string, object>
    {
        ["mainMiB"] = M(vk.Size(manager.MainCache)),
        ["worker0MiB"] = M(vk.Size(manager.GetWorkerCache(0))),
        ["worker1MiB"] = M(vk.Size(manager.GetWorkerCache(1))),
        ["mergedLine"] = Ryujinx.Common.Logging.Logger.Info.Messages.FirstOrDefault(m => m.StartsWith("Merged ")),
        ["budgetLine"] = Ryujinx.Common.Logging.Logger.Notice.Messages.LastOrDefault(m => m.Contains("Budget")),
    };
    manager.Dispose();
}

// B: a main snapshot of 900 MiB (above 768, below 1024).
{
    var (manager, vk, _) = Session(900 * MiB, 0, 0);
    report["largeMain"] = new Dictionary<string, object>
    {
        ["mainMiB"] = M(vk.Size(manager.MainCache)),
        ["ignored"] = Ryujinx.Common.Logging.Logger.Warning.Messages.Any(m => m.StartsWith("Ignoring Vulkan pipeline cache")),
    };
    manager.Dispose();
}

// C: main 10 MiB and worker 0 5 MiB. Worker 0 compiles 64 pipelines (a due save), then main is checkpointed, then
// worker 0 compiles 64 more. The worker file must keep the merged snapshot until main holds it.
{
    var (manager, vk, directory) = Session(10 * MiB, 5 * MiB, 0);
    string workerFile = Snapshot(directory, ".worker0"), mainFile = Snapshot(directory, "");
    long workerAtStart = vk.Size(manager.GetWorkerCache(0));
    vk.Grow(manager.GetWorkerCache(0), 1 * MiB);
    for (int i = 0; i < 64; i++) manager.NotifyWorkerPipelineCreated(0);
    long workerFileAfterDueSave = Length(workerFile);
    typeof(PipelineCacheManager).GetField("_mainCheckpointTimestamp", BindingFlags.Instance | BindingFlags.NonPublic)
        .SetValue(manager, Environment.TickCount64 - 200_000);
    manager.NotifyWorkerPipelineCreated(0);
    long mainFileAfterCheckpoint = Length(mainFile);
    object worker = ((Array)typeof(PipelineCacheManager).GetField("_workerStates", BindingFlags.Instance | BindingFlags.NonPublic)
        .GetValue(manager)).GetValue(0);
    worker.GetType().GetField("LastSaveTimestamp").SetValue(worker, 0L);
    for (int i = 0; i < 64; i++) manager.NotifyWorkerPipelineCreated(0);
    report["hold"] = new Dictionary<string, object>
    {
        ["workerAtStartMiB"] = M(workerAtStart),
        ["workerFileAfterDueSaveMiB"] = M(workerFileAfterDueSave),
        ["mainFileAfterCheckpointMiB"] = M(mainFileAfterCheckpoint),
        ["workerFileAfterMainSavedMiB"] = M(Length(workerFile)),
    };
    manager.Dispose();
}

report["errors"] = Ryujinx.Common.Logging.Logger.Error.Lines;
Directory.Delete(root, true);
Console.WriteLine(JsonSerializer.Serialize(report));
