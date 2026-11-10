using System;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;

int checks = 0;
void Check(bool condition, string message) {
    checks++;
    if (!condition) throw new Exception(message);
}
void Wait(Task task, string message) => Check(task.Wait(5000), message);

// Queue many speculative warm-ups behind occupied background workers. Closing
// must cancel the entire set before waiting for its first shader.
{
    var gd = new VulkanRenderer();
    int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
    using var entered = new CountdownEvent(workers);
    using var unblock = new ManualResetEventSlim();
    for (int i = 0; i < workers; i++)
        gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => { entered.Signal(); unblock.Wait(); });
    Check(entered.Wait(5000), "Background workers did not start");
    var shaders = Enumerable.Range(0, 128).Select(_ => new ShaderCollection(gd, Task.CompletedTask)).ToArray();
    foreach (var shader in shaders) shader.Start();
    Check(shaders.All(s => s.Pending != null), "Warm-ups were not queued");
    Task close = Task.Run(gd.Close);
    try {
        Check(SpinWait.SpinUntil(() => shaders.All(s => s.Completion.IsCompleted), 5000), "Close waited for pending warm-ups");
        Check(shaders.Sum(s => s.NativeCompiles) == 0, "A speculative warm-up compiled during close");
        Check(!gd.Released && !close.IsCompleted, "Renderer released while workers were active");
    } finally { unblock.Set(); }
    Wait(close, "Close did not join running workers");
    Check(gd.Released, "Renderer never released");
}

// Close before shader modules complete: the later continuation must not enqueue
// a new undemanded warm-up behind the cancellation sweep.
{
    var gd = new VulkanRenderer();
    var modules = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
    var shader = new ShaderCollection(gd, modules.Task);
    shader.Start();
    shader.CancelPendingWarmUp();
    Task close = Task.Run(gd.Close);
    modules.SetResult(true);
    Wait(close, "Close with pending module compilation failed");
    Check(shader.NativeCompiles == 0, "Late module completion started a cancelled warm-up");
}

// A worker that already took a warm-up retains resources and completes normally.
{
    var gd = new VulkanRenderer();
    using var entered = new ManualResetEventSlim();
    using var unblock = new ManualResetEventSlim();
    var shader = new ShaderCollection(gd, Task.CompletedTask) { CompileAction = () => { entered.Set(); unblock.Wait(); } };
    shader.Start();
    Task close;
    try {
        Check(entered.Wait(5000), "Native compile did not start");
        close = Task.Run(gd.Close);
        shader.CancelPendingWarmUp();
        Check(!gd.Released, "Running compile's resources released early");
    } finally { unblock.Set(); }
    Wait(close, "Running compile did not complete close");
    Check(shader.NativeCompiles == 1, "Running compile was duplicated");
}

// The scheduler refuses to cancel demanded work even before a worker takes it.
{
    using var scheduler = new BackgroundCompilationScheduler(new());
    int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
    using var entered = new CountdownEvent(workers);
    using var demandEntered = new ManualResetEventSlim();
    using var unblock = new ManualResetEventSlim();
    int calls = 0;
    Task demand;
    try {
        for (int i = 0; i < workers; i++)
            _ = scheduler.SchedulePipelineCompile(_ => { entered.Signal(); unblock.Wait(); });
        Check(entered.Wait(5000), "Normal scheduler workers did not start");
        _ = scheduler.SchedulePipelineCompile(_ => { demandEntered.Set(); unblock.Wait(); }, demanded: true);
        Check(demandEntered.Wait(5000), "Demand scheduler worker did not start");
        demand = scheduler.SchedulePipelineCompile(_ => Interlocked.Increment(ref calls));
        scheduler.PromotePipelineCompile(demand);
        Check(!scheduler.TryCancelPipelineCompile(demand), "Demanded work was cancelled");
    } finally { unblock.Set(); }
    Wait(demand, "Demanded work never completed");
    Check(calls == 1, "Demanded work was duplicated");
}

// Play-time programs keep their existing compilation policy at teardown.
{
    var gd = new VulkanRenderer();
    var modules = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
    var shader = new ShaderCollection(gd, modules.Task, detached: false);
    shader.Start();
    shader.CancelPendingWarmUp();
    modules.SetResult(true);
    gd.Close();
    Check(shader.NativeCompiles == 1, "Play-time program was incorrectly cancelled");
}
Console.WriteLine(JsonSerializer.Serialize(new { checks, pendingWarmupsCancelled = 128,
    lateModuleCompletionCovered = true, runningAndDemandedWorkJoined = true, physicalDeviceTested = false }));
