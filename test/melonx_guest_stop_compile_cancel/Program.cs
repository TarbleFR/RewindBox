// melonx_guest_stop_compile_cancel_test.py: a close whose render loop drains the guest's program disposals.
// Hogwarts Legacy and Super Smash Bros. Ultimate, IPA 816-820: the drain waited for every queued compile.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.Vulkan;

static class Program
{
    static int Main(string[] args)
    {
        bool candidate = args[0] == "candidate";
        VulkanRenderer gd = new();
        gd.PipelineCacheManager.Compiling = () => Volatile.Read(ref ShaderCollection.Running) != 0;
        BackgroundCompilationScheduler scheduler = gd.BackgroundCompilationScheduler;
        int workers = BackgroundCompilationScheduler.PipelineWorkerCount;

        // Every pipeline thread is inside a compile when the guest stops (the demand thread takes a demanded one).
        ManualResetEventSlim release = new();
        int blockersStarted = 0, blockersEnded = 0;
        List<Task> blockers = new();
        for (int index = 0; index <= workers; index++)
        {
            blockers.Add(scheduler.SchedulePipelineCompile(_ =>
            {
                Interlocked.Increment(ref ShaderCollection.Running);
                Interlocked.Increment(ref blockersStarted);
                release.Wait();
                Thread.Sleep(30);
                Interlocked.Increment(ref blockersEnded);
                Interlocked.Decrement(ref ShaderCollection.Running);
            }, highPriority: true, demanded: true));
        }
        // The shader module worker too: no queued module is compiled before the guest stops.
        for (int index = 0; index < workers; index++)
        {
            blockers.Add(scheduler.ScheduleShaderCompile(() =>
            {
                Interlocked.Increment(ref ShaderCollection.Running);
                Interlocked.Increment(ref blockersStarted);
                release.Wait();
                Thread.Sleep(30);
                Interlocked.Increment(ref blockersEnded);
                Interlocked.Decrement(ref ShaderCollection.Running);
            }, highPriority: true));
        }
        SpinWait.SpinUntil(() => Volatile.Read(ref blockersStarted) == blockers.Count, 5000);

        List<ShaderCollection> programs = new();
        // Programs compiled during play: their warm-up pipeline is queued, not detached (a disposal promotes it).
        for (int index = 0; index < 150; index++) { ShaderCollection p = new(gd, detached: false, queuedModule: false); p.Start(); programs.Add(p); }
        // Programs of the disk cache whose shader module is still queued: nothing of theirs is cancellable by the program.
        for (int index = 0; index < 50; index++) { ShaderCollection p = new(gd, detached: true, queuedModule: true); p.Start(); programs.Add(p); }
        // Programs with a play-time pipeline compile queued for a state a draw skipped.
        for (int index = 0; index < 20; index++) { ShaderCollection p = new(gd, detached: true, queuedModule: false); p.QueuePlayTimePipeline(); programs.Add(p); }
        // The async warm-ups reach the pipeline queue.
        Thread.Sleep(100);

        // The guest stops (controlling thread); the render loop then drains the program disposals.
        Stopwatch stop = Stopwatch.StartNew();
        bool cancelled = gd.GuestStop(out int cancelledModules, out int cancelledPipelines);
        long guestStopMs = stop.ElapsedMilliseconds;
        bool runningWhenStopReturned = Volatile.Read(ref blockersEnded) == 0;
        release.Set();

        int compilesBefore = Volatile.Read(ref ShaderCollection.NativeCompiles), modulesBefore = Volatile.Read(ref ShaderCollection.ModuleCompiles);
        Stopwatch drain = Stopwatch.StartNew();
        foreach (ShaderCollection program in programs) { program.DisposeAtDrain(); }
        long drainMs = drain.ElapsedMilliseconds;
        int compiledDuringDrain = Volatile.Read(ref ShaderCollection.NativeCompiles) - compilesBefore;
        int modulesDuringDrain = Volatile.Read(ref ShaderCollection.ModuleCompiles) - modulesBefore;

        // Work scheduled after the guest stopped (a queued command the loop still executes).
        int lateRan = 0;
        Task late = scheduler.SchedulePipelineCompile(_ => Interlocked.Increment(ref lateRan));
        Task lateModule = scheduler.ScheduleShaderCompile(() => Interlocked.Increment(ref lateRan));
        bool lateRefused = candidate
            ? late.IsFaulted && late.Exception.InnerException is ObjectDisposedException && lateModule.IsFaulted
            : !late.IsFaulted;
        if (!candidate) { late.Wait(); lateModule.Wait(); }

        // The GPU release: cancel what is left, join the threads, save the cache.
        Stopwatch teardown = Stopwatch.StartNew();
        gd.BeginTeardown();
        long teardownMs = teardown.ElapsedMilliseconds;
        bool blockersCompleted = blockers.All(task => task.Status == TaskStatus.RanToCompletion);
        gd.BeginTeardown();
        scheduler.Dispose();
        scheduler.CancelPending();

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant = args[0], workers, programs = programs.Count, cancelled, cancelledModules, cancelledPipelines, guestStopMs,
            runningWhenStopReturned, drainMs, compiledDuringDrain, modulesDuringDrain, lateRefused, lateRan, teardownMs,
            blockersCompleted, blockers = blockers.Count, blockersStarted, blockersEnded, saves = gd.PipelineCacheManager.Saves,
            savedWhileCompiling = gd.PipelineCacheManager.SavedWhileCompiling,
            reportedModules = scheduler.CancelledShaderCompiles, reportedPipelines = scheduler.CancelledPipelineCompiles,
            failureLines = Logger.Warning.Lines + Logger.Error.Lines, rendererFailures = gd.Failures,
            failedPrograms = programs.Count(p => p.LinkStatus == ProgramLinkStatus.Failure),
            journal = EmbeddedLaunchDiagnostics.Records.ToArray(),
        }));
        return 0;
    }
}
