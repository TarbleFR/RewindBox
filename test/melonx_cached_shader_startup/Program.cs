using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Shader.Translation;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

static class Program
{
#if CACHED_STARTUP_ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
    static int _checks, _matrixCases, _failureCases;
    const int CachePrograms = 2743;
    static void Check(bool condition, string message)
    {
        _checks++;
        if (!condition) throw new Exception(message);
    }
    static void Wait(Task task, string message) => Check(task.Wait(10000), message);
    static void Until(Func<bool> condition, string message) => Check(SpinWait.SpinUntil(condition, 10000), message);
    static void Event(ManualResetEventSlim signal, string message) => Check(signal.Wait(10000), message);
    static ShaderCollection Make(VulkanRenderer gd, bool cache = true, bool async = false, bool allowSkip = false,
        bool compute = false, int key = 0, bool state = true, bool binary = true)
    {
        ShaderSource Source(ShaderStage stage) => binary
            ? new ShaderSource(BitConverter.GetBytes(key), stage, TargetLanguage.Spirv)
            : new ShaderSource(key.ToString(), stage, TargetLanguage.Glsl);
        ShaderSource[] sources = compute
            ? [Source(ShaderStage.Compute)]
            : [Source(ShaderStage.Vertex), Source(ShaderStage.Fragment)];
        var layout = new ResourceLayout(Array.AsReadOnly(Array.Empty<ResourceDescriptorCollection>()),
            Array.AsReadOnly(Array.Empty<ResourceUsageCollection>()));
        var info = state ? new ShaderInfo(0, layout, new ProgramPipelineState { Key = key }, cache, async, allowSkip)
            : new ShaderInfo(0, layout, cache, async, allowSkip);
        return (ShaderCollection)gd.CreateProgram(sources, info);
    }
    static Exception Capture(Action action)
    {
        try { action(); return null; }
        catch (Exception error) { return error; }
    }
    static void Matrix()
    {
        foreach (bool cache in new[] { false, true })
        foreach (bool async in new[] { false, true })
        foreach (bool allowSkip in new[] { false, true })
        foreach (bool compute in new[] { false, true })
        foreach (bool state in compute ? new[] { true } : new[] { false, true })
        foreach (bool binary in new[] { false, true })
        {
            using var gd = new VulkanRenderer();
            var shader = Make(gd, cache, async, allowSkip, compute, state: state, binary: binary);
            Wait(shader.Completion, "Matrix initial compilation did not finish");
            Check(shader.CheckProgramLink(true) == ProgramLinkStatus.Success, "Matrix modules invalid");
            Check(shader.CompilesInBackground == (async || (Adapted && cache)), "Wrong scheduling policy");
            Check(shader.CanBindWhileIncomplete == (async && allowSkip), "Implicit incomplete bind permission");
            if (Adapted) Check(shader.AllowAsyncCompileSkip == (async && allowSkip), "Skip flag escaped async setting");
            gd.Pipeline.SetProgram(shader);
            Check(gd.Pipeline.CanSkip() == (async && allowSkip), "Draw skip policy differs");
            Check(gd.Pipeline.Submit(compute, allowSkip: false),
                $"Ready matrix draw/dispatch failed: cache={cache} async={async} skip={allowSkip} compute={compute} state={state}");
            Check(!gd.Pipeline.Skipped, "Complete pipeline skipped draw");
            Check(gd.Api.BoundPipelines == 1, "Pipeline was not bound exactly once");
            _matrixCases++;
        }
    }
    static int BulkCache()
    {
        using var gd = new VulkanRenderer();
        using var occupied = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        Task blocker = null;
        if (Adapted)
        {
            Check(BackgroundCompilationScheduler.PipelineWorkerCount == 1, "Fixture must model six-core scheduler");
            blocker = gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { occupied.Set(); release.Wait(); });
            Event(occupied, "Speculative worker did not occupy");
        }
        int beforeExit;
        try
        {
            for (int i = 0; i < CachePrograms; i++)
            {
                var shader = Make(gd, key: i);
                Check(shader.CheckProgramLink(true) == ProgramLinkStatus.Success, "Cache loader rejected valid modules");
                if (!Adapted) Wait(shader.Completion, "Legacy cache validation missed pipeline completion");
            }
            beforeExit = gd.NativeCompiles;
            if (Adapted)
            {
                Until(() => gd.Shaders.All(s => s.Pending != null), "Warm-ups did not enqueue after module readiness");
                Check(beforeExit == 0, "Loader waited for speculative pipeline");
                Task close = Task.Run(gd.Dispose);
                Until(() => gd.Shaders.All(s => s.Completion.IsCompleted), "Close did not cancel pending cache work");
                Check(!close.IsCompleted && !gd.Released, "Close released an occupied worker");
                Check(gd.NativeCompiles == 0, "Close compiled undemanded cache pipelines");
                release.Set();
                Wait(close, "Bulk close failed to join");
            }
            else Check(beforeExit == CachePrograms, "Legacy control did not compile the whole cache");
        }
        finally { release.Set(); if (blocker != null) Wait(blocker, "Blocking worker did not exit"); }
        return beforeExit;
    }
    static void ModulesBlockActualUse()
    {
        foreach (bool compute in new[] { false, true })
        {
            using var gd = new VulkanRenderer();
            using var entered = new ManualResetEventSlim();
            using var release = new ManualResetEventSlim();
            using var submissionEntered = new ManualResetEventSlim();
            gd.Api.ModuleAction = _ => { entered.Set(); release.Wait(); };
            var shader = Make(gd, allowSkip: true, compute: compute);
            Event(entered, "Module compilation never entered");
            Check(shader.CheckProgramLink(false) == ProgramLinkStatus.Incomplete, "Unfinished module reported ready");
            Check(!shader.CanBindWhileIncomplete, "async=false permits incomplete bind");
            Task<bool> submit = Task.Run(() =>
            {
                submissionEntered.Set();
                gd.Pipeline.SetProgram(shader);
                return gd.Pipeline.Submit(compute, allowSkip: true);
            });
            try
            {
                Event(submissionEntered, "Submission did not enter");
                Check(!submit.IsCompleted && gd.Api.BoundPipelines == 0, "Use did not wait for required modules");
            }
            finally { release.Set(); }
            Wait(submit, "Required modules did not unblock use");
            Check(submit.Result && !gd.Pipeline.Skipped, "Synchronous use was dropped");
        }
    }
    static void DemandPromotesAndWaits()
    {
        using var gd = new VulkanRenderer();
        using var occupied = new ManualResetEventSlim();
        using var releaseWorker = new ManualResetEventSlim();
        using var demandEntered = new ManualResetEventSlim();
        using var releaseDemand = new ManualResetEventSlim();
        Task blocker = gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { occupied.Set(); releaseWorker.Wait(); });
        Event(occupied, "Speculative worker did not start");
        gd.CompileAction = request => { demandEntered.Set(); releaseDemand.Wait(); return Result.Success; };
        var shader = Make(gd, async: !Adapted, allowSkip: Adapted);
        Check(shader.CheckProgramLink(true) == ProgramLinkStatus.Success, "Demand fixture modules not ready");
        Until(() => shader.Pending != null, "Initial warm-up not queued");
        gd.Pipeline.SetProgram(shader);
        Task<bool> draw = Task.Run(() => gd.Pipeline.Submit());
        try
        {
            Event(demandEntered, "Demand worker did not bypass occupied speculative worker");
            Check(!draw.IsCompleted, "Actual draw skipped while required pipeline compiles");
            Check(gd.Api.BoundPipelines == 0, "Pipeline bound before native completion");
            Check(!gd.BackgroundCompilationScheduler.TryCancelPipelineCompile(shader.Pending), "Demanded work was cancelled");
            Check(gd.Requests.Single().CacheIndex == BackgroundCompilationScheduler.PipelineCacheCount,
                "Demand did not use its recovered worker cache");
            releaseDemand.Set();
            Wait(draw, "Demand draw did not finish");
            Check(draw.Result && !gd.Pipeline.Skipped && gd.NativeCompiles == 1, "Demand was duplicated or dropped");
        }
        finally { releaseDemand.Set(); releaseWorker.Set(); Wait(blocker, "Speculative blocker stuck"); }
    }
    static void RecoverableAndModuleFailures()
    {
        foreach (bool compute in new[] { false, true })
        {
            using (var gd = new VulkanRenderer())
            {
                int calls = 0;
                gd.CompileAction = _ => Interlocked.Increment(ref calls) == 1 ? Result.ErrorUnknown : Result.Success;
                var shader = Make(gd, compute: compute);
                Wait(shader.Completion, "Recoverable warm-up did not complete");
                Check(shader.CheckProgramLink(true) == ProgramLinkStatus.Success, "Dummy pass poisoned modules");
                gd.PreFrame();
                gd.Pipeline.SetProgram(shader);
                Check(gd.Pipeline.Submit(compute), "Real pipeline did not retry recoverable warm-up");
                Check(calls == 2, "Unexpected retry count");
            }
            using (var gd = new VulkanRenderer())
            {
                gd.Api.ModuleAction = _ => throw new InvalidOperationException("Module fixture failure");
                var shader = Make(gd, compute: compute);
                Wait(shader.Completion, "Failed modules did not settle");
                Check(shader.CheckProgramLink(true) == ProgramLinkStatus.Failure, "Module failure became a valid program");
                gd.Pipeline.SetProgram(shader);
                Check(!gd.Pipeline.Submit(compute) && gd.NativeCompiles == 0, "Failed modules reached native pipeline creation");
            }
        }
    }
    static void ExplicitAsyncSkipPreserved()
    {
        foreach (bool compute in new[] { false, true })
        {
            using var gd = new VulkanRenderer();
            using var occupied = new ManualResetEventSlim();
            using var releaseWorker = new ManualResetEventSlim();
            using var entered = new ManualResetEventSlim();
            using var releaseDemand = new ManualResetEventSlim();
            Task blocker = gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { occupied.Set(); releaseWorker.Wait(); });
            Event(occupied, "Explicit async blocker did not start");
            gd.CompileAction = _ => { entered.Set(); releaseDemand.Wait(); return Result.Success; };
            try
            {
                var shader = Make(gd, async: true, allowSkip: true, compute: compute);
                Check(shader.CheckProgramLink(true) == ProgramLinkStatus.Success, "Explicit async modules invalid");
                Until(() => shader.Pending != null, "Explicit async warm-up did not queue");
                gd.Pipeline.SetProgram(shader);
                Check(!gd.Pipeline.Submit(compute), "Explicit async draw/dispatch stopped skipping pending pipelines");
                Event(entered, "Explicit async demand did not promote");
                Check(gd.Api.BoundPipelines == 0, "Explicit async bound unfinished pipeline");
                releaseDemand.Set();
                Wait(shader.Completion, "Explicit async pipeline did not complete");
                Check(gd.Pipeline.Submit(compute), "Explicit async pipeline did not become usable");
            }
            finally { releaseDemand.Set(); releaseWorker.Set(); Wait(blocker, "Explicit async blocker stuck"); }
        }
    }
    static void FatalDuringDemandWait()
    {
#if CACHED_STARTUP_ADAPTED
        foreach (Result result in new[] { Result.ErrorDeviceLost, Result.ErrorOutOfHostMemory, Result.ErrorOutOfDeviceMemory })
        {
            using var gd = new VulkanRenderer();
            using var occupied = new ManualResetEventSlim();
            using var releaseWorker = new ManualResetEventSlim();
            using var entered = new ManualResetEventSlim();
            using var releaseDemand = new ManualResetEventSlim();
            Task blocker = gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { occupied.Set(); releaseWorker.Wait(); });
            Event(occupied, "Fatal demand blocker did not start");
            gd.CompileAction = _ => { entered.Set(); releaseDemand.Wait(); return result; };
            try
            {
                var shader = Make(gd, allowSkip: true);
                Check(shader.CheckProgramLink(true) == ProgramLinkStatus.Success, "Fatal demand modules invalid");
                Until(() => shader.Pending != null, "Fatal demand warm-up did not queue");
                gd.Pipeline.SetProgram(shader);
                Task<bool> draw = Task.Run(() => gd.Pipeline.Submit());
                Event(entered, "Fatal demand did not start");
                Check(!draw.IsCompleted, "Demand completed before its native result");
                releaseDemand.Set();
                Until(() => draw.IsCompleted, "Fatal demand remained blocked");
                Check(draw.IsFaulted && draw.Exception.Flatten().InnerExceptions.Single() is VulkanException error &&
                    error.ResultCode == result, "Wait swallowed fatal and attempted fallback");
                Check(gd.NativeCompiles == 1 && gd.Api.BoundPipelines == 0, "Fatal demand retried or bound a pipeline");
                _failureCases++;
            }
            finally { releaseDemand.Set(); releaseWorker.Set(); Wait(blocker, "Fatal demand blocker stuck"); }
        }
#endif
    }
    static void FatalDetachedFailures()
    {
#if CACHED_STARTUP_ADAPTED
        foreach (bool compute in new[] { false, true })
        foreach (Exception failure in new Exception[] {
            new VulkanException(Result.ErrorDeviceLost), new VulkanException(Result.ErrorOutOfHostMemory),
            new VulkanException(Result.ErrorOutOfDeviceMemory), new InvalidOperationException("Unexpected warm-up error"),
            new OutOfMemoryException("Managed warm-up allocation") })
        {
            using var gd = new VulkanRenderer();
            using var entered = new ManualResetEventSlim();
            using var release = new ManualResetEventSlim();
            gd.CompileAction = _ => { entered.Set(); release.Wait(); ThrowNativeFailure(failure); return Result.Success; };
            var unused = Make(gd, compute: compute);
            Event(entered, "Fatal warm-up did not enter native boundary");
            ShaderCollection other;
            try
            {
                Check(unused.CheckProgramLink(true) == ProgramLinkStatus.Success, "Detached pipeline held loader");
                other = Make(gd, state: false, key: 8);
                Check(other.CheckProgramLink(true) == ProgramLinkStatus.Success, "Independent modules did not load");
            }
            finally { release.Set(); }
            Until(() => unused.Completion.IsCompleted, "Fatal warm-up did not fault");
            Check(unused.Completion.IsFaulted, "Fatal task was converted into success");
            _ = unused.Completion.Exception;
            var observed = Capture(gd.PreFrame);
            Check(ReferenceEquals(observed, failure), "Unused program's failure did not reach next frame");
            Check(observed.StackTrace.Contains(nameof(ThrowNativeFailure)), "Original native failure stack was lost");
            Check(gd.SyncManager.Calls == 0, "Frame work continued after fatal error");
            Check(ReferenceEquals(Capture(() => other.CheckProgramLink(true)), failure), "Other program ignored renderer fatal");
            uint count = gd.ProgramCount;
            Check(ReferenceEquals(Capture(() => Make(gd)), failure) && gd.ProgramCount == count, "Loader continued after fatal");
            gd.Pipeline.SetProgram(other);
            Check(ReferenceEquals(Capture(() => gd.Pipeline.Submit(compute)), failure), "Real pipeline boundary ignored fatal");
            var key = new PipelineUid { Key = 99 };
            Check(ReferenceEquals(Capture(() => other.TryWaitForBackgroundGraphicsPipeline(ref key, 0, out _)), failure),
                "Completed/absent queue entry hid fatal");
            gd.RecordBackgroundPipelineFailure(new InvalidOperationException("Later failure"));
            Check(ReferenceEquals(Capture(gd.PreFrame), failure), "Later failure replaced first error");
            _failureCases++;
        }
        using var nextSession = new VulkanRenderer();
        nextSession.PreFrame();
        Check(nextSession.SyncManager.Calls == 1, "Fatal leaked across renderer/session instances");
#endif
    }
    static void ThrowNativeFailure(Exception failure) => throw failure;
    static void CloseBeforeModulesFinish()
    {
        using var gd = new VulkanRenderer();
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        gd.Api.ModuleAction = _ => { entered.Set(); release.Wait(); };
        var shader = Make(gd, async: !Adapted);
        Event(entered, "Late modules did not start");
        shader.CancelPendingWarmUp();
        Task close = Task.Run(gd.Dispose);
        try { Check(!gd.Released && !shader.Completion.IsCompleted, "Pending modules released prematurely"); }
        finally { release.Set(); }
        Wait(close, "Late modules prevented clean close");
        Check(gd.NativeCompiles == 0, "Cancelled warm-up queued after module completion");
    }
    static void FatalInitialStillJoinsDemand()
    {
#if CACHED_STARTUP_ADAPTED
        foreach (bool dispose in new[] { false, true })
        {
            using var gd = new VulkanRenderer();
            using var initialEntered = new ManualResetEventSlim();
            using var failInitial = new ManualResetEventSlim();
            using var demandEntered = new ManualResetEventSlim();
            using var finishDemand = new ManualResetEventSlim();
            using var joinEntered = new ManualResetEventSlim();
            gd.CompileAction = request =>
            {
                if (request.Key == 0)
                {
                    initialEntered.Set(); failInitial.Wait();
                    throw new VulkanException(Result.ErrorDeviceLost);
                }
                demandEntered.Set(); finishDemand.Wait();
                return Result.Success;
            };
            var shader = Make(gd, async: true, allowSkip: true);
            Event(initialEntered, "Initial warm-up did not start");
            var state = new PipelineState { Internal = new PipelineUid { Key = 7 } };
            state.Initialize();
            var pass = new Auto<DisposableRenderPass>(new());
            Task join = null;
            try
            {
                Check(shader.QueueBackgroundGraphicsPipeline(ref state, pass), "Second demand did not queue");
                Event(demandEntered, "Second demand did not start");
                failInitial.Set();
                Until(() => shader.Completion.IsFaulted, "Initial warm-up did not fault");
                var joined = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
                join = joined.Task;
                var joinThread = new Thread(() =>
                {
                    try
                    {
                        joinEntered.Set();
                        if (dispose) shader.Dispose(); else shader.WaitForBackgroundCompilation();
                        joined.SetResult();
                    }
                    catch (Exception error) { joined.SetException(error); }
                });
                joinThread.Start();
                Event(joinEntered, "Join did not begin");
                Until(() => join.IsCompleted || (joinThread.ThreadState & ThreadState.WaitSleepJoin) != 0,
                    "Join did not reach a blocking wait");
                Check(!join.IsCompleted && !shader.ModulesDisposed, "Fault skipped demand join and released modules");
                finishDemand.Set();
                Wait(join, "Faulted initial task prevented joining the demanded task");
                Check(pass.References == 1, "Demand continuation did not release its render pass");
                Check(shader.ModulesDisposed == dispose, "Wrong module lifetime after join");
            }
            finally
            {
                failInitial.Set(); finishDemand.Set();
                if (join != null) Wait(join, "Join cleanup failed");
                state.Dispose(); pass.Dispose();
            }
        }
#endif
    }
    static void Main()
    {
        Matrix();
        int beforeExit = BulkCache();
        ModulesBlockActualUse();
        DemandPromotesAndWaits();
        RecoverableAndModuleFailures();
        ExplicitAsyncSkipPreserved();
        FatalDetachedFailures();
        FatalDuringDemandWait();
        CloseBeforeModulesFinish();
        FatalInitialStillJoinsDemand();
        Check(PipelineState.LiveStates == 0, "Temporary pipeline state leaked");
        Console.WriteLine(JsonSerializer.Serialize(new { variant = Adapted ? "candidate" : "control", checks = _checks,
            matrixCases = _matrixCases, fatalCases = _failureCases, cachePrograms = CachePrograms,
            pipelineCompilesBeforeLoaderExit = beforeExit, bulkFixtureSpeculativeWorkerBlocked = Adapted,
            pipelineWorkerCount = BackgroundCompilationScheduler.PipelineWorkerCount,
            pipelineCacheCount = BackgroundCompilationScheduler.PipelineCacheCount,
            actualDrawsRemainSynchronous = true, physicalDeviceTested = false, timingGate = false }));
    }
}
