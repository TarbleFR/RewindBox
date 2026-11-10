// Scenarios for melonx_pipeline_cache_growth_test.py on the variant's real PipelineCacheManager.cs (control: Core 685
// postimage; candidate: with adapt_pipeline_cache_growth, CANDIDATE). The Vulkan double is
// test/melonx_main_cache_checkpoint/Double.cs (a pipeline cache is a byte count; a write is "data main begin/end").
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

System.Globalization.CultureInfo.DefaultThreadCurrentCulture = System.Globalization.CultureInfo.InvariantCulture;
System.Globalization.CultureInfo.CurrentCulture = System.Globalization.CultureInfo.InvariantCulture;
const long MiB = 1024 * 1024;
const string Key = "00000000-00000000-00000000";
var report = new Dictionary<string, object> { ["variant"] = args[0] };
string root = Path.Combine(Path.GetTempPath(), "melonx-pipeline-cache-growth-" + Environment.ProcessId);
int sessions = 0;
var records = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records;

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
    lock (records) records.Clear();
    return (new PipelineCacheManager(vk, new VulkanPhysicalDevice(), default, 2, mainLock), vk, mainFile);
}

void SetField(PipelineCacheManager manager, string name, long value) =>
    typeof(PipelineCacheManager).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)?.SetValue(manager, value);

void Age(PipelineCacheManager manager) => SetField(manager, "_mainCheckpointTimestamp", Environment.TickCount64 - 200_000);

double M(string path) => Math.Round(new FileInfo(path).Length / (double)MiB, 2);
int Writes() => Events.Snapshot().Count(e => e.Text == "data main end");
string[] Records() { lock (records) return records.ToArray(); }

void RenderCreations(PipelineCacheManager manager, Vk vk, int count, long bytesEach)
{
    for (int i = 0; i < count; i++) { vk.Grow(manager.MainCache, bytesEach); manager.NotifyMainPipelineCreated(); }
}

PipelineCacheManager current = null;
bool Queued() => (int)typeof(PipelineCacheManager).GetField("_mainCheckpointQueued", BindingFlags.Instance | BindingFlags.NonPublic)
    .GetValue(current) != 0 || current.MainCheckpointInProgress;

// Waits until a main write completes after `writesBefore`, or a skip is recorded after `skipsBefore` (the candidate), then
// until the queued checkpoint has fully returned (file renamed, lock released).
string Settle(int writesBefore, int skipsBefore, int timeoutMs)
{
    var watch = Stopwatch.StartNew();
    string outcome = "none";
    while (watch.ElapsedMilliseconds < timeoutMs && outcome == "none")
    {
        if (Writes() > writesBefore) outcome = "written";
        else if (Records().Count(r => r.StartsWith("pipelineCache checkpointSkipped")) > skipsBefore) outcome = "skipped";
        else Thread.Sleep(5);
    }
    while (watch.ElapsedMilliseconds < timeoutMs && Queued()) Thread.Sleep(5);
    Thread.Sleep(20);
    return outcome;
}

int Skips() => Records().Count(r => r.StartsWith("pipelineCache checkpointSkipped"));

// A, B, C: one play session, main loaded at 100 MiB.
{
    var (manager, vk, mainFile) = Session(100 * MiB);
    current = manager;
    report["startRecords"] = Records().Where(r => r.StartsWith("pipelineBuilds journal")).ToArray();

    // A: past the interval, 8 render-thread pipelines adding 2 MiB in all: the whole file is not rewritten for it.
    Age(manager);
    int writes = Writes(), skips = Skips();
    vk.Grow(manager.MainCache, 2 * MiB);
    RenderCreations(manager, vk, 8, 0);
    string small = Settle(writes, skips, 3000);
    report["smallGrowth"] = new Dictionary<string, object> { ["outcome"] = small, ["mainFileMiB"] = M(mainFile), ["writes"] = Writes() - writes };

    // B: 8 more adding 7 MiB (9 MiB over the file in the candidate): written.
    Age(manager);
    writes = Writes(); skips = Skips();
    vk.Grow(manager.MainCache, 7 * MiB);
    RenderCreations(manager, vk, 8, 0);
    string large = Settle(writes, skips, 3000);
    report["largeGrowth"] = new Dictionary<string, object> { ["outcome"] = large, ["mainFileMiB"] = M(mainFile), ["writes"] = Writes() - writes };

    // C: 1 MiB more, the file written over 10 min ago: written (stale rule).
    Age(manager);
    SetField(manager, "_mainWrittenTimestamp", Environment.TickCount64 - 700_000);
    writes = Writes(); skips = Skips();
    vk.Grow(manager.MainCache, 1 * MiB);
    RenderCreations(manager, vk, 8, 0);
    string stale = Settle(writes, skips, 3000);
    report["staleGrowth"] = new Dictionary<string, object> { ["outcome"] = stale, ["mainFileMiB"] = M(mainFile), ["writes"] = Writes() - writes };

    report["playRecords"] = Records().Where(r => r.StartsWith("pipelineCache")).ToArray();
    manager.Dispose();
}

// D: pause with new content (written), then pause with new pipelines that add nothing to the cache (not rewritten).
{
    var (manager, vk, mainFile) = Session(50 * MiB);
    RenderCreations(manager, vk, 3, 64 * 1024);
    int writes = Writes();
    manager.CheckpointMainOnPause();
    int afterFirst = Writes() - writes;
    double firstMiB = M(mainFile);
    RenderCreations(manager, vk, 3, 0);
    writes = Writes();
    manager.CheckpointMainOnPause();
    report["pause"] = new Dictionary<string, object>
    {
        ["firstWrites"] = afterFirst, ["firstMiB"] = firstMiB, ["unchangedWrites"] = Writes() - writes, ["mainFileMiB"] = M(mainFile),
        ["records"] = Records().Where(r => r.StartsWith("pipelineCache")).ToArray(),
    };
    manager.Dispose();
}

// E: a worker cache grown over its budget is recycled; the build journal summary reaches the engine journal.
{
    var (manager, vk, mainFile) = Session(20 * MiB);
    PipelineCache worker = manager.GetWorkerCache(0);
    for (int i = 0; i < 64; i++) { vk.Grow(worker, 2_200_000); manager.NotifyWorkerPipelineCreated(0); }
    typeof(PipelineCacheManager).GetField("_buildSummaryTimestamp", BindingFlags.Instance | BindingFlags.NonPublic)?
        .SetValue(manager, Environment.TickCount64 - 120_000);
    manager.NotePipelineBuild(0x1234, 300, true);
    report["worker"] = new Dictionary<string, object>
    {
        ["recycledInfo"] = Ryujinx.Common.Logging.Logger.Info.Messages.Any(m => m.StartsWith("Recycled the Vulkan worker 0")),
        ["records"] = Records().Where(r => r.StartsWith("pipelineCache recycled") || r.StartsWith("pipelineBuilds summary")).ToArray(),
    };
    manager.MergeAndSave(); // the close
    manager.Dispose();
    report["closeRecords"] = Records().Where(r => r.StartsWith("pipelineCache saved")).ToArray();
}

report["errors"] = Ryujinx.Common.Logging.Logger.Error.Lines;
report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Lines;
Directory.Delete(root, true);
Console.WriteLine(JsonSerializer.Serialize(report));
