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
                Thread.Sleep(300);
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

    static void Sleep(CancellationToken token, int ms) => token.WaitHandle.WaitOne(ms);

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
            report["lineBudget"] = new Dictionary<string, object> { ["reachedWaits"] = 300, ["reachedLines"] = reachedLines,
                ["idleWaits"] = 100, ["idleLines"] = idleLines.Count, ["idleWarnings"] = idleLines.Count(l => l.StartsWith("Warning")),
                ["lastLine"] = idleLines.LastOrDefault() };
        }
#endif

        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
