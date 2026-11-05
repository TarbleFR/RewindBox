// Drives the real NvHostEvent.Wait forced path (Ryujinx.HLE), the real SynchronizationManager and the real GpuContext /
// GPFifoDevice members of the built production assemblies, with a GPU double that increments the syncpoint, marks
// command buffers and dispatches, fills the GPFIFO and counts threaded-renderer commands through the production members
// (the candidate's; the control has none of them and ignores them). The {Nv} server thread is a host thread whose
// kernel thread is an uninitialised KThread, terminated by setting its production termination flag.
// Usage: Fixture <control|candidate>; prints one JSON line.
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Engine.GPFifo;
using Ryujinx.Graphics.Gpu.Synchronization;
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;

static class Program
{
    const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.Static;
    const uint SyncpointId = 1;
    static readonly Assembly Hle = typeof(Ryujinx.HLE.Switch).Assembly;
    static readonly Type HostEventType = Hle.GetType("Ryujinx.HLE.HOS.Services.Nv.NvDrvServices.NvHostCtrl.NvHostEvent", true);
    static readonly Type FenceType = Hle.GetType("Ryujinx.HLE.HOS.Services.Nv.Types.NvFence", true);
    static readonly Type KThreadType = Hle.GetType("Ryujinx.HLE.HOS.Kernel.Threading.KThread", true);
    static readonly Type KernelStaticType = Hle.GetType("Ryujinx.HLE.HOS.Kernel.KernelStatic", true);
    static readonly List<(string Level, string Message)> Lines = new();
    static readonly object LinesGate = new();

    static void SetField(object target, string name, object value)
    {
        FieldInfo field = target.GetType().GetField(name, Any) ?? throw new MissingFieldException(target.GetType().Name, name);
        field.SetValue(target, value);
    }

    static bool HasMember(Type type, string name) => type.GetMember(name, Any).Length != 0;

    static object NewFence(uint value)
    {
        object fence = Activator.CreateInstance(FenceType);
        FenceType.GetField("Id").SetValue(fence, SyncpointId);
        FenceType.GetField("Value").SetValue(fence, value);
        return fence;
    }

    sealed class Gpu
    {
        public readonly GpuContext Context;
        readonly object _renderer;
        public Gpu()
        {
            Context = (GpuContext)RuntimeHelpers.GetUninitializedObject(typeof(GpuContext));
            SetField(Context, "<Synchronization>k__BackingField", new SynchronizationManager());
            object fifo = Activator.CreateInstance(typeof(GPFifoDevice), Any, null, new object[] { Context }, null);
            SetField(Context, "<GPFifo>k__BackingField", fifo);
            // The threaded backend renderer (its state is read through CompletedCommands only).
            _renderer = RuntimeHelpers.GetUninitializedObject(typeof(Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer));
            SetField(Context, "<Renderer>k__BackingField", _renderer);
            // The queued-syncpoint FIFO of adapt_queued_syncpoints (a field initialiser): empty.
            FieldInfo queue = typeof(GpuContext).GetField("_queuedSyncpoints", Any);
            queue.SetValue(Context, Activator.CreateInstance(queue.FieldType));
        }

        public uint Value => Context.Synchronization.GetSyncpointValue(SyncpointId);
        public void Increment() => Context.Synchronization.IncrementSyncpoint(SyncpointId);

        // Production members of the candidate; the control has none.
        public void CommandBuffer() => typeof(GpuContext).GetMethod("NoteCommandBufferStarted", Any)?.Invoke(Context, null);
        public void Dispatching(bool on) => typeof(GpuContext).GetMethod("NoteDispatching", Any)?.Invoke(Context, new object[] { on });
        public void RenderCommand()
        {
            FieldInfo field = _renderer.GetType().GetField("_completedCommands", Any);
            field?.SetValue(_renderer, (long)field.GetValue(_renderer) + 1);
        }

        // A command buffer the GPU thread has not taken yet (production GPFifoDevice.PushHostCommandBuffer), or none.
        public void FifoHolds(bool holds)
        {
            object fifo = Context.GPFifo;
            if (holds)
                typeof(GPFifoDevice).GetMethod("PushHostCommandBuffer", Any).Invoke(fifo, new object[] { null, new int[1] });
            else
            {
                object queue = typeof(GPFifoDevice).GetField("_commandBufferQueue", Any).GetValue(fifo);
                queue.GetType().GetMethod("Clear").Invoke(queue, null);
            }
        }
    }

    sealed class Outcome
    {
        public bool WaitReturned { get; set; }
        public double Ms { get; set; }
        public uint Threshold { get; set; }
        public uint ValueAtReturn { get; set; }
        public bool TrueCompletion { get; set; }
        public double TerminationToReturnMs { get; set; } = -1;
        public List<string> Lines { get; set; } = new();
    }

    // One forced wait: the guest cancelled the fence twice (_failingCount == FailingCountMax), the {Nv} thread waits.
    static Outcome ForcedWait(Gpu gpu, uint threshold, Action<Gpu, CancellationToken, object> driver, bool terminateAt300Ms = false)
    {
        object hostEvent = RuntimeHelpers.GetUninitializedObject(HostEventType);
        SetField(hostEvent, "Lock", new Lock());
        object fence = NewFence(threshold);
        SetField(hostEvent, "Fence", fence);
        SetField(hostEvent, "_previousFailingFence", fence);
        SetField(hostEvent, "_failingCount", 2u);
        object kthread = RuntimeHelpers.GetUninitializedObject(KThreadType);
        int linesBefore;
        lock (LinesGate) linesBefore = Lines.Count;

        Outcome outcome = new() { Threshold = threshold };
        using CancellationTokenSource stop = new();
        Thread gpuThread = new(() => driver(gpu, stop.Token, kthread)) { IsBackground = true, Name = "GPU double" };
        long terminated = 0;
        Thread terminator = null;
        Thread server = new(() =>
        {
            KernelStaticType.GetMethod("SetKernelContext", Any).Invoke(null, new object[] { null, kthread });
            long start = Stopwatch.GetTimestamp();
            outcome.WaitReturned = (bool)HostEventType.GetMethod("Wait", Any).Invoke(hostEvent, new object[] { gpu.Context, fence });
            long end = Stopwatch.GetTimestamp();
            outcome.Ms = Stopwatch.GetElapsedTime(start, end).TotalMilliseconds;
            outcome.ValueAtReturn = gpu.Value;
            outcome.TrueCompletion = outcome.ValueAtReturn >= threshold;
            if (Interlocked.Read(ref terminated) != 0)
                outcome.TerminationToReturnMs = Stopwatch.GetElapsedTime(Interlocked.Read(ref terminated), end).TotalMilliseconds;
        }) { IsBackground = true, Name = "{Nv}" };
        gpuThread.Start();
        server.Start();
        if (terminateAt300Ms)
        {
            terminator = new(() =>
            {
                After(300);
                Interlocked.Exchange(ref terminated, Stopwatch.GetTimestamp());
                // Production KThread.PrepareForTermination sets this flag first (Horizon.Dispose terminating the HLE services).
                SetField(kthread, "_shallBeTerminated", 1);
            }) { IsBackground = true };
            terminator.Start();
        }
        if (!server.Join(TimeSpan.FromSeconds(40))) throw new TimeoutException("the {Nv} wait never returned");
        stop.Cancel();
        gpuThread.Join();
        terminator?.Join();
        lock (LinesGate) outcome.Lines = Lines.Skip(linesBefore).Where(l => !l.Message.Contains("too slow")).Select(l => l.Level + " " + l.Message).ToList();
        return outcome;
    }

    // The GPU double's steps follow an absolute schedule (n x ms from its first step), waited in short slices re-checked
    // against it: on the macOS Core runner one 100 ms wait lasted 165-190 ms (run 42006447546: 25 x 100 ms took 4.8 s),
    // which the schedule absorbs instead of adding up. The modeled GPU then advances as described on every host.
    [ThreadStatic] static long _schedule;

    static void Sleep(CancellationToken token, int ms)
    {
        if (_schedule == 0) _schedule = Stopwatch.GetTimestamp();
        _schedule += ms * Stopwatch.Frequency / 1000;
        WaitUntil(token, _schedule);
    }

    static void WaitUntil(CancellationToken token, long deadline)
    {
        for (long left; !token.IsCancellationRequested && (left = deadline - Stopwatch.GetTimestamp()) > 0;)
            token.WaitHandle.WaitOne(TimeSpan.FromMilliseconds(Math.Clamp(left * 1000.0 / Stopwatch.Frequency, 0.1, 10)));
    }

    static void After(int ms) => WaitUntil(CancellationToken.None, Stopwatch.GetTimestamp() + ms * Stopwatch.Frequency / 1000);

    static int Main(string[] args)
    {
        string variant = args[0];
        Logger.RemoveTarget("console");
        Logger.Updated += (_, e) => { lock (LinesGate) Lines.Add((e.Level.ToString(), e.Message)); };
        PropertyInfo gate = typeof(GraphicsConfig).GetProperty("ProgressAwareForcedSyncpointWait");
        bool candidate = gate != null;
        if (candidate != (variant == "candidate")) throw new InvalidOperationException("variant and assemblies disagree");
        gate?.SetValue(null, true); // the Library assigns it from the launched title: Hogwarts Legacy here

        Dictionary<string, object> report = new() { ["variant"] = variant, ["policyFlag"] = candidate,
            ["progressMembers"] = HasMember(typeof(GpuContext), "ForcedWaitGpuIdle") };

        // 1. The syncpoint advances every 100 ms, 25 increments to the fence (a GPU thread catching up, 2.5 s).
        Gpu gpu = new();
        report["progressing"] = ForcedWait(gpu, gpu.Value + 25, (g, token, _) =>
        {
            g.Dispatching(true);
            for (int i = 0; i < 25 && !token.IsCancellationRequested; i++) { Sleep(token, 100); g.CommandBuffer(); g.Increment(); }
            g.Dispatching(false);
        });

        // 2. The GPU thread processes command buffers for 3.2 s without incrementing the syncpoint, then increments it.
        gpu = new();
        report["gpuWorkThenFence"] = ForcedWait(gpu, gpu.Value + 1, (g, token, _) =>
        {
            g.FifoHolds(true);
            g.Dispatching(true);
            for (int i = 0; i < 32 && !token.IsCancellationRequested; i++) { Sleep(token, 100); g.CommandBuffer(); }
            g.FifoHolds(false);
            g.Increment();
            g.Dispatching(false);
        });

        // 3. The GPU thread is blocked on the render thread (a command buffer still queued, no dispatch progress) while the
        //    render thread completes commands (pipeline builds) for 3.2 s; then the fence.
        gpu = new();
        report["renderWorkThenFence"] = ForcedWait(gpu, gpu.Value + 1, (g, token, _) =>
        {
            g.FifoHolds(true);
            for (int i = 0; i < 32 && !token.IsCancellationRequested; i++) { Sleep(token, 100); g.RenderCommand(); }
            g.CommandBuffer();
            g.FifoHolds(false);
            g.Increment();
        });

        // 4. Nothing on the GPU side, twice on one session: falls back after one slice as before, journaled once.
        gpu = new();
        report["idle"] = ForcedWait(gpu, gpu.Value + 1, (g, token, _) => { });
        report["idleAgain"] = ForcedWait(gpu, gpu.Value + 1, (g, token, _) => { });

        // 5. Progress for 2 s (20 increments), then the GPU drains without reaching the fence (+100).
        gpu = new();
        report["drainedShort"] = ForcedWait(gpu, gpu.Value + 100, (g, token, _) =>
        {
            g.FifoHolds(true);
            g.Dispatching(true);
            for (int i = 0; i < 20 && !token.IsCancellationRequested; i++) { Sleep(token, 100); g.CommandBuffer(); g.Increment(); }
            g.FifoHolds(false);
            g.Dispatching(false);
        });

        // 6. Busy with no progress at all (a wedged render thread): the deadlock guard.
        gpu = new();
        report["stuckBusy"] = ForcedWait(gpu, gpu.Value + 1, (g, token, _) => { g.FifoHolds(true); g.Dispatching(true); });

        // 7. The guest terminates 300 ms into a wait while the GPU keeps working.
        gpu = new();
        report["termination"] = ForcedWait(gpu, gpu.Value + 1, (g, token, _) =>
        {
            g.FifoHolds(true);
            g.Dispatching(true);
            while (!token.IsCancellationRequested) { Sleep(token, 20); g.CommandBuffer(); g.RenderCommand(); }
        }, terminateAt300Ms: true);

        // 8. Already reached: no wait.
        gpu = new();
        gpu.Increment();
        report["alreadyReached"] = ForcedWait(gpu, gpu.Value, (g, token, _) => { });

        // 9. Policy off (every other title): the progressing case of 1 again.
        if (candidate)
        {
            gate.SetValue(null, false);
            gpu = new();
            report["policyOff"] = ForcedWait(gpu, gpu.Value + 25, (g, token, _) =>
            {
                g.Dispatching(true);
                for (int i = 0; i < 25 && !token.IsCancellationRequested; i++) { Sleep(token, 100); g.CommandBuffer(); g.Increment(); }
                g.Dispatching(false);
            });
            gate.SetValue(null, true);
        }

        // 10. A GPU-side wait (GPFifoClass Syncpointb, Host1x) keeps the 1 s cap: timed out, the error line.
        gpu = new();
        int before;
        lock (LinesGate) before = Lines.Count;
        long gpuWaitStart = Stopwatch.GetTimestamp();
        bool timedOut = gpu.Context.Synchronization.WaitOnSyncpoint(SyncpointId, gpu.Value + 1, Timeout.InfiniteTimeSpan);
        report["gpuSideWait"] = new Dictionary<string, object> { ["timedOut"] = timedOut,
            ["ms"] = Stopwatch.GetElapsedTime(gpuWaitStart).TotalMilliseconds,
            ["lines"] = Lines.Skip(before).Select(l => l.Level + " " + l.Message).ToList() };

        // 11. The bounded counters line: 300 already-reached forced waits on one session (none notable) log one line, at
        //     the 256th; notable waits beyond the budget of 64 lines log nothing more until the next multiple of 256. The
        //     candidate's API: compiled for the candidate only (CANDIDATE).
#if CANDIDATE
        {
            gpu = new();
            lock (LinesGate) before = Lines.Count;
            for (int i = 0; i < 300; i++)
                gpu.Context.Synchronization.WaitOnSyncpointWhileProgressing(SyncpointId, 0, () => 0, () => 0, () => true, () => false);
            int reachedLines;
            lock (LinesGate) reachedLines = Lines.Count - before;
            gpu = new();
            lock (LinesGate) before = Lines.Count;
            for (int i = 0; i < 100; i++)
                gpu.Context.Synchronization.WaitOnSyncpointWhileProgressing(SyncpointId, gpu.Value + 1, TimeSpan.FromMilliseconds(1),
                    TimeSpan.FromMilliseconds(5), () => 0, () => 0, () => true, () => false);
            List<string> idleLines;
            lock (LinesGate) idleLines = Lines.Skip(before).Select(l => l.Level + " " + l.Message).ToList();
            // 12. Progress that never reaches the threshold ends at the absolute cap (1.5 s here; 30 s in production), counted
            //     and journaled once, though the no-progress guard (10 s) never trips.
            {
                Gpu capGpu = new();
                int capBefore;
                lock (LinesGate) capBefore = Lines.Count;
                long counter = 0;
                using CancellationTokenSource capStop = new();
                Thread worker = new(() => { while (!capStop.IsCancellationRequested) { Interlocked.Increment(ref counter); Thread.Sleep(10); } }) { IsBackground = true };
                worker.Start();
                long capStart = Stopwatch.GetTimestamp();
                var capOutcome = capGpu.Context.Synchronization.WaitOnSyncpointWhileProgressing(SyncpointId, capGpu.Value + 1,
                    TimeSpan.FromMilliseconds(500), TimeSpan.FromSeconds(10), TimeSpan.FromMilliseconds(1500), () => 0,
                    () => Interlocked.Read(ref counter), () => false, () => false);
                double capMs = Stopwatch.GetElapsedTime(capStart).TotalMilliseconds;
                capStop.Cancel();
                worker.Join();
                // A second capped wait: counted again, not journaled again.
                capGpu.Context.Synchronization.WaitOnSyncpointWhileProgressing(SyncpointId, capGpu.Value + 1,
                    TimeSpan.FromMilliseconds(100), TimeSpan.FromSeconds(10), TimeSpan.FromMilliseconds(200), () => 0,
                    () => Interlocked.Increment(ref counter), () => false, () => false);
                List<string> capLines;
                lock (LinesGate) capLines = Lines.Skip(capBefore).Select(l => l.Level + " " + l.Message).ToList();
                report["cap"] = new Dictionary<string, object> { ["outcome"] = capOutcome.ToString(), ["ms"] = capMs,
                    ["capConstantMs"] = Ryujinx.Graphics.Gpu.Synchronization.SynchronizationManager.ProgressWaitTotalCap.TotalMilliseconds,
                    ["lines"] = capLines };
            }

            // 13. The value is reached without the callback (stored directly): the slice end reports Reached, true value.
            {
                Gpu valueGpu = new();
                uint target = valueGpu.Value + 3;
                object syncpoints = typeof(SynchronizationManager).GetField("_syncpoints", Any).GetValue(valueGpu.Context.Synchronization);
                object syncpoint = ((Array)syncpoints).GetValue((int)SyncpointId);
                Thread setter = new(() => { After(150); syncpoint.GetType().GetField("_storedValue", Any).SetValue(syncpoint, (int)target + 2); }) { IsBackground = true };
                setter.Start();
                long valueStart = Stopwatch.GetTimestamp();
                var valueOutcome = valueGpu.Context.Synchronization.WaitOnSyncpointWhileProgressing(SyncpointId, target,
                    TimeSpan.FromMilliseconds(400), TimeSpan.FromSeconds(10), () => 0, () => 0, () => false, () => false);
                report["valueNoCallback"] = new Dictionary<string, object> { ["outcome"] = valueOutcome.ToString(),
                    ["ms"] = Stopwatch.GetElapsedTime(valueStart).TotalMilliseconds, ["value"] = valueGpu.Value, ["target"] = target };
                setter.Join();
            }

            report["lineBudget"] = new Dictionary<string, object> { ["reachedWaits"] = 300, ["reachedLines"] = reachedLines,
                ["idleWaits"] = 100, ["idleLines"] = idleLines.Count, ["idleWarnings"] = idleLines.Count(l => l.StartsWith("Warning")),
                ["lastLine"] = idleLines.LastOrDefault() };
        }
#endif

        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
