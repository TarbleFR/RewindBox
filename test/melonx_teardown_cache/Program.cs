// Scenarios for melonx_teardown_cache_test.py. Built once per variant: control (Core 658 preparation) and candidate
// (with adapt_teardown_cache, DefineConstants CANDIDATE). Prints one JSON report.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using FixtureSupport;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using Window = Ryujinx.Library.Window;

var report = new Dictionary<string, object> { ["variant"] = args[0] };
string root = Path.Combine(Path.GetTempPath(), "melonx-teardown-cache-" + Environment.ProcessId);
int sessions = 0;

(VulkanRenderer Gd, Vk Vk, string Directory) NewRenderer(int mainPipelines)
{
    string directory = Path.Combine(root, "session" + sessions++);
    Directory.CreateDirectory(directory);
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = directory;
    var vk = new Vk();
    var gd = new VulkanRenderer(vk);
    for (int i = 0; i < mainPipelines; i++)
    {
        // A pipeline the render thread created in the main cache during play.
        vk.Grow(gd.PipelineCacheManager.MainCache, 64 * 1024);
        gd.PipelineCacheManager.NotifyMainPipelineCreated();
    }
    return (gd, vk, directory);
}

string MainFile(string directory) =>
    Directory.Exists(Path.Combine(directory, "cache", "vulkan"))
        ? Directory.GetFiles(Path.Combine(directory, "cache", "vulkan"), "pipeline-*.vkpc").FirstOrDefault(f => !f.Contains(".worker"))
        : null;

string[] Journal()
{
    lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Records) return Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.ToArray();
}

void ClearJournal()
{
    lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Records) Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.Clear();
    Events.Clear();
}

int Failures() => Ryujinx.Common.Logging.Logger.Warning.Lines + Ryujinx.Common.Logging.Logger.Error.Lines;

// Build 658, cold MoltenVK cache, close after play: the background pipeline worker and the demand thread are each inside a
// native compile, 200 play-time pipelines (20 ms each) are queued for 200 programs and 20 cache warm-ups are pending. The
// render loop has drained; the window's GPU release runs: GpuContext.Dispose disposes every program on the render thread,
// then the renderer. The main cache holds 10 pipelines this session created in it.
{
    ClearJournal();
    var (gd, vk, directory) = NewRenderer(10);
    int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
    using var entered = new CountdownEvent(workers);
    using var demandEntered = new ManualResetEventSlim();
    using var unblock = new ManualResetEventSlim();
    for (int i = 0; i < workers; i++)
        gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { entered.Signal(); unblock.Wait(); });
    if (!entered.Wait(5000)) throw new Exception("compile workers did not start");
    // Scheduled once every background worker is busy, so only the demand thread can take it.
    gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { demandEntered.Set(); unblock.Wait(); }, demanded: true);
    if (!demandEntered.Wait(5000)) throw new Exception("demand thread did not start");
    var programs = Enumerable.Range(0, 200).Select(_ => new ShaderCollection(gd, Task.CompletedTask, detached: false)).ToList();
    foreach (var program in programs) program.QueuePlayTimePipeline();
    var warmUps = Enumerable.Range(0, 20).Select(_ => new ShaderCollection(gd, Task.CompletedTask, detached: true)).ToList();
    foreach (var warmUp in warmUps) warmUp.Start();
    var all = programs.Concat(warmUps).ToList();
    var window = new Window { Renderer = gd };
    window.Device.DisposeGpuAction = () =>
    {
        var render = new Thread(() => { foreach (var program in all) program.Dispose(); }) { Name = "render" };
        render.Start();
        render.Join();
        gd.Close();
    };
    int before = Failures();
    var watch = Stopwatch.StartNew();
    var release = new Thread(window.Release) { Name = "release" };
    release.Start();
    Thread.Sleep(300);
    bool releasedWhileRunning = gd.Released;
    unblock.Set();
    if (!release.Join(120000)) throw new Exception("close never completed");
    report["closeMs"] = watch.ElapsedMilliseconds;
    report["workers"] = workers;
    report["compiledDuringClose"] = all.Sum(p => p.NativeCompiles);
    report["releasedWhileWorkerRan"] = releasedWhileRunning;
    report["finalized"] = window.Finalized;
    report["failureLines"] = Failures() - before;
    var events = Events.Snapshot();
    int firstDispose = Array.FindIndex(events, e => e.Text == "programDispose");
    int rendererDispose = Array.FindIndex(events, e => e.Text == "rendererDispose");
    int[] mainWrites = events.Select((e, i) => (e, i)).Where(x => x.e.Text.StartsWith("data main end")).Select(x => x.i).ToArray();
    report["mainWrites"] = mainWrites.Length;
    report["mainWrittenBeforeFirstProgramDispose"] = mainWrites.Length > 0 && mainWrites[0] < firstDispose;
    report["mainWrittenAfterRendererDispose"] = mainWrites.Any(i => i > rendererDispose);
    report["programDisposes"] = events.Count(e => e.Text == "programDispose");
    report["mainFileSaved"] = MainFile(directory) != null;
    report["mainFileBytes"] = MainFile(directory) is string path ? new FileInfo(path).Length : 0;
    report["journal"] = Journal();
    report["order"] = events.Where(e => !e.Text.StartsWith("programDispose") || e.Text == "programDispose")
        .Select(e => e.Text).Where(t => !t.StartsWith("data worker")).Distinct().ToArray();
    report["deviceIdles"] = vk.Idles;
}

#if CANDIDATE
// A pipeline added to the main cache after BeginTeardown (not expected on the release path) is still saved by Dispose.
{
    ClearJournal();
    var (gd, vk, directory) = NewRenderer(4);
    var window = new Window { Renderer = gd };
    window.Device.DisposeGpuAction = () =>
    {
        vk.Grow(gd.PipelineCacheManager.MainCache, 64 * 1024);
        gd.PipelineCacheManager.NotifyMainPipelineCreated();
        gd.Close();
    };
    window.Release();
    report["mainWritesWhenChangedAfterHook"] = Events.Snapshot().Count(e => e.Text == "data main end");
    report["savedBytesWhenChangedAfterHook"] = new FileInfo(MainFile(directory)).Length;
    report["expectedBytesWhenChangedAfterHook"] = vk.Size(gd.PipelineCacheManager.MainCache);
}

// The hook fails (here: the cache manager was already disposed): the release goes on, DisposeGpu runs, one journal line.
{
    ClearJournal();
    var (gd, vk, directory) = NewRenderer(1);
    gd.PipelineCacheManager.Dispose();
    bool disposed = false;
    var window = new Window { Renderer = gd };
    window.Device.DisposeGpuAction = () => disposed = true;
    window.Release();
    report["disposeGpuAfterHookFailure"] = disposed;
    report["hookFailureJournal"] = Journal().Where(j => j.StartsWith("teardown compileCancelFailed")).ToArray();
}
#endif

report["failureLinesTotal"] = Failures();
report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Messages.Distinct().Take(10).ToArray();
try { Directory.Delete(root, recursive: true); } catch (IOException) { }
Console.WriteLine(JsonSerializer.Serialize(report));
