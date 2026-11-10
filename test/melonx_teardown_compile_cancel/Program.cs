using System;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;

int checks = 0;
void Check(bool condition, string message) { checks++; if (!condition) throw new Exception(message); }
var report = new System.Collections.Generic.Dictionary<string, object> { ["variant"] = args[0] };

// IPA 643, SSBU closed early: every background worker is inside a native compile, and 200 play-time pipeline compiles
// of 20 ms each are queued for 200 programs compiled during play (not cache warm-ups). The render loop has drained.
{
    var gd = new VulkanRenderer();
    int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
    using var entered = new CountdownEvent(workers);
    using var unblock = new ManualResetEventSlim();
    for (int i = 0; i < workers; i++)
        gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { entered.Signal(); unblock.Wait(); });
    Check(entered.Wait(5000), "workers did not start");
    var programs = Enumerable.Range(0, 200).Select(_ => new ShaderCollection(gd, Task.CompletedTask, detached: false) {
        CompileAction = () => Thread.Sleep(20) }).ToArray();
    foreach (var p in programs) p.QueuePlayTimePipeline();
    var watch = Stopwatch.StartNew();
    Task close = Task.Run(gd.Close);
    Thread.Sleep(200);
    bool releasedWhileRunning = gd.Released;
    unblock.Set();
    Check(close.Wait(60000), "close never completed");
    report["closeMs"] = watch.ElapsedMilliseconds;
    report["workers"] = workers;
    report["idles"] = gd.Api.Idles;
    report["saves"] = gd.PipelineCacheManager.Saves;
    report["queuedCompiledDuringClose"] = programs.Sum(p => p.NativeCompiles);
    report["releasedWhileWorkerRan"] = releasedWhileRunning;
    report["cancelledPipelines"] = gd.BackgroundCompilationScheduler.GetType().GetProperty("CancelledPipelineCompiles")?.GetValue(gd.BackgroundCompilationScheduler);
    report["failureLines"] = Ryujinx.Common.Logging.Logger.Warning.Lines + Ryujinx.Common.Logging.Logger.Error.Lines;
    lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Records) report["journal"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.ToArray();
}

// A demanded compile still queued at close (a draw promoted it before the render loop ended).
{
    var gd = new VulkanRenderer();
    int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
    using var entered = new CountdownEvent(workers);
    using var demandEntered = new ManualResetEventSlim();
    using var unblock = new ManualResetEventSlim();
    for (int i = 0; i < workers; i++)
        gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { entered.Signal(); unblock.Wait(); });
    Check(entered.Wait(5000), "workers did not start");
    gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { demandEntered.Set(); unblock.Wait(); }, demanded: true);
    Check(demandEntered.Wait(5000), "demand worker did not start");
    var program = new ShaderCollection(gd, Task.CompletedTask, detached: false);
    program.QueuePlayTimePipeline(demanded: true);
    Task close = Task.Run(gd.Close);
    Thread.Sleep(100);
    unblock.Set();
    Check(close.Wait(10000), "close with demanded work never completed");
    report["demandedCompiledDuringClose"] = program.NativeCompiles;
}

// Shader modules still queued at close: the program's background compilation ends without a pipeline, quietly.
{
    var gd = new VulkanRenderer();
    int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
    using var unblock = new ManualResetEventSlim();
    // Occupy every shader worker so the module compiles stay queued.
    using var entered = new CountdownEvent(workers);
    for (int i = 0; i < workers; i++)
        gd.BackgroundCompilationScheduler.ScheduleShaderCompile(() => { entered.Signal(); unblock.Wait(); });
    Check(entered.Wait(5000), "shader workers did not start");
    int moduleRuns = 0;
    var programs = Enumerable.Range(0, 20).Select(_ => {
        Task modules = gd.BackgroundCompilationScheduler.ScheduleShaderCompile(() => { Interlocked.Increment(ref moduleRuns); Thread.Sleep(20); });
        var p = new ShaderCollection(gd, modules, detached: false);
        p.Start();
        return p;
    }).ToArray();
    int before = Ryujinx.Common.Logging.Logger.Warning.Lines + Ryujinx.Common.Logging.Logger.Error.Lines;
    Task close = Task.Run(gd.Close);
    Thread.Sleep(100);
    unblock.Set();
    Check(close.Wait(20000), "close with queued modules never completed");
    report["modulesCompiledDuringClose"] = moduleRuns;
    report["pipelinesAfterModules"] = programs.Sum(p => p.NativeCompiles);
    report["moduleFailureLines"] = Ryujinx.Common.Logging.Logger.Warning.Lines + Ryujinx.Common.Logging.Logger.Error.Lines - before;
}

// Work scheduled after close (a late continuation) is refused, never run after the renderer is released.
{
    var gd = new VulkanRenderer();
    gd.Close();
    int ran = 0;
    Task late = gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => Interlocked.Increment(ref ran));
    try { late.Wait(1000); } catch (AggregateException) { }
    report["lateRan"] = ran;
    report["lateFaulted"] = late.IsFaulted && late.Exception?.InnerException is ObjectDisposedException;
}
report["checks"] = checks;
Console.WriteLine(JsonSerializer.Serialize(report));
