// melonx_render_thread_compile_relief_test.py: the scheduler's order, the short wait of a skippable draw and a
// dispatch joining a cached compute program's warm-up, on the real members.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.Vulkan;

static class Program
{
    static Task Schedule(BackgroundCompilationScheduler scheduler, Action action, bool high, bool demanded, bool prebuild)
    {
        // The candidate's fourth parameter; the control has three.
        MethodInfo method = typeof(BackgroundCompilationScheduler).GetMethod("SchedulePipelineCompile");
        Action<Silk.NET.Vulkan.PipelineCache> work = _ => action();
        return (Task)(method.GetParameters().Length == 4
            ? method.Invoke(scheduler, new object[] { work, high, demanded, prebuild })
            : method.Invoke(scheduler, new object[] { work, high, demanded }));
    }

    static int Main(string[] args)
    {
        bool candidate = args[0] == "candidate";

        // 1. Order: every pipeline thread busy, then 6 speculative warm-ups, 4 recorded states, 2 high priority, 1 demanded.
        VulkanRenderer gd = new();
        BackgroundCompilationScheduler scheduler = gd.BackgroundCompilationScheduler;
        int workers = BackgroundCompilationScheduler.PipelineWorkerCount;
        ManualResetEventSlim release = new();
        int started = 0;
        for (int index = 0; index <= workers; index++)
        {
            Schedule(scheduler, () => { Interlocked.Increment(ref started); release.Wait(); }, high: true, demanded: true, prebuild: false);
        }
        SpinWait.SpinUntil(() => Volatile.Read(ref started) == workers + 1, 5000);
        List<string> order = new();
        List<Task> tasks = new();
        void Add(string name, bool high, bool demanded, bool prebuild) =>
            tasks.Add(Schedule(scheduler, () => { lock (order) order.Add(name); Thread.Sleep(2); }, high, demanded, prebuild));
        for (int index = 0; index < 6; index++) Add("warmup" + index, false, false, false);
        for (int index = 0; index < 4; index++) Add("replay" + index, false, false, true);
        for (int index = 0; index < 2; index++) Add("high" + index, true, false, false);
        Add("demanded", true, true, false);
        release.Set();
        Task.WaitAll(tasks.ToArray());

        // 2. Cancellation at the guest's stop drains the prebuild queue too.
        ManualResetEventSlim release2 = new();
        started = 0;
        for (int index = 0; index <= workers; index++)
        {
            Schedule(scheduler, () => { Interlocked.Increment(ref started); release2.Wait(); }, high: true, demanded: true, prebuild: false);
        }
        SpinWait.SpinUntil(() => Volatile.Read(ref started) == workers + 1, 5000);
        int ranAfterStop = 0;
        List<Task> pending = new();
        for (int index = 0; index < 5; index++) pending.Add(Schedule(scheduler, () => Interlocked.Increment(ref ranAfterStop), false, false, true));
        for (int index = 0; index < 5; index++) pending.Add(Schedule(scheduler, () => Interlocked.Increment(ref ranAfterStop), false, false, false));
        MethodInfo cancel = typeof(BackgroundCompilationScheduler).GetMethod("CancelPending");
        cancel.Invoke(scheduler, null);
        int cancelled = pending.Count(task => task.IsFaulted && task.Exception.InnerException is ObjectDisposedException);
        release2.Set();
        scheduler.Dispose();

        // 3. A dispatch of a compute program loaded from the cache whose warm-up (120 ms) waits behind a busy worker.
        VulkanRenderer gd2 = new();
        ManualResetEventSlim release3 = new();
        started = 0;
        for (int index = 0; index < workers; index++)
        {
            Schedule(gd2.BackgroundCompilationScheduler, () => { Interlocked.Increment(ref started); release3.Wait(); }, high: true, demanded: false, prebuild: false);
        }
        SpinWait.SpinUntil(() => Volatile.Read(ref started) == workers, 5000);
        ShaderCollection cached = new(gd2, playTimeWarmUp: false);
        cached.QueueComputeWarmUp(7, 120, highPriority: false);
        SpecData computeKey = new() { Id = 7 };
        Stopwatch dispatch = Stopwatch.StartNew();
        bool joined = cached.TryWaitForBackgroundComputePipeline(ref computeKey, out Auto<DisposablePipeline> computePipeline);
        if (!joined) { cached.CreateComputeOnRenderThread(7, 120); }
        long dispatchMs = dispatch.ElapsedMilliseconds;
        release3.Set();
        // The control's warm-up still runs afterwards: the same pipeline a second time.
        SpinWait.SpinUntil(() => Volatile.Read(ref cached.NativeCompiles) == (joined ? 1 : 2), 5000);
        Thread.Sleep(50);
        int computeCompiles = cached.NativeCompiles;
        // A key no warm-up has: the dispatch creates it itself, as before.
        SpecData otherKey = new() { Id = 8 };
        bool otherJoined = cached.TryWaitForBackgroundComputePipeline(ref otherKey, out _);

        // 4. The short wait of a skippable draw (candidate only): quick compile obtained, slow compile left to its thread.
        long quickMs = -1, slowMs = -1;
        bool quickObtained = false, slowObtained = true, slowObtainedLater = false;
        int briefPromotions = -1, allowanceIdle = -1, allowanceSpent = -1, allowanceLater = -1;
        string waitText = null;
        MethodInfo brief = typeof(ShaderCollection).GetMethod("TryWaitBrieflyForQueuedGraphicsPipeline");
        Type wait = typeof(BackgroundCompilationScheduler).Assembly.GetType("Ryujinx.Graphics.Vulkan.SkippableDrawWait");
        if (brief != null && wait != null)
        {
            ShaderCollection program = new(gd2, playTimeWarmUp: false);
            program.QueueGraphics(1, 1);
            object[] arguments = { new PipelineUid { Id = 1 }, 40, null };
            Stopwatch quick = Stopwatch.StartNew();
            quickObtained = (bool)brief.Invoke(program, arguments);
            quickMs = quick.ElapsedMilliseconds;
            Task slowTask = program.QueueGraphics(2, 300);
            arguments = new object[] { new PipelineUid { Id = 2 }, 4, null };
            Stopwatch slow = Stopwatch.StartNew();
            slowObtained = (bool)brief.Invoke(program, arguments);
            slowMs = slow.ElapsedMilliseconds;
            slowTask.Wait();
            arguments = new object[] { new PipelineUid { Id = 2 }, 4, null };
            slowObtainedLater = (bool)brief.Invoke(program, arguments);
            briefPromotions = program.Promotions;

            MethodInfo take = wait.GetMethod("Take"), spend = wait.GetMethod("Spend"), text = wait.GetMethod("TakeText");
            Thread.Sleep(60);
            allowanceIdle = (int)take.Invoke(null, null);
            spend.Invoke(null, new object[] { Stopwatch.Frequency * 4 / 1000, false });
            allowanceSpent = (int)take.Invoke(null, null);
            Thread.Sleep(24);
            allowanceLater = (int)take.Invoke(null, null);
            spend.Invoke(null, new object[] { Stopwatch.Frequency / 1000, true });
            waitText = (string)text.Invoke(null, null);
        }
        gd2.BackgroundCompilationScheduler.Dispose();

        Console.WriteLine(JsonSerializer.Serialize(new
        {
            variant = args[0], workers, order = order.ToArray(), cancelled, ranAfterStop,
            joined, dispatchMs, computeCompiles, computePipeline = computePipeline != null, otherJoined,
            briefAvailable = brief != null, quickObtained, quickMs, slowObtained, slowMs, slowObtainedLater, briefPromotions,
            allowanceIdle, allowanceSpent, allowanceLater, waitText,
        }));
        return 0;
    }
}
