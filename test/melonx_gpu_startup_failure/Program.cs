using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Cpu;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Memory;
using Ryujinx.HLE.HOS;
using Ryujinx.HLE.HOS.Kernel;
using Ryujinx.HLE.HOS.Kernel.Process;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.Library;

static class Program
{
#if GPU_STARTUP_ADAPTED
    const bool Adapted = true;
#else
    const bool Adapted = false;
#endif
    static int _checks, _cases, _blockedControls, _cancelCases;
    static void Check(bool condition, string message) { _checks++; if (!condition) throw new Exception(message); }
    static void Until(Func<bool> condition, string message) => Check(SpinWait.SpinUntil(condition, 10000), message);
    static void Event(ManualResetEventSlim signal, string message) => Check(signal.Wait(10000), message);
    static void Wait(Task task, string message) => Check(task.Wait(10000), message);
    static Exception Capture(Action action)
    {
        try { action(); return null; }
        catch (Exception failure) { return failure; }
    }
    sealed class Session
    {
        public readonly GpuContext Gpu = new();
        public readonly Ryujinx.Cpu.Memory Memory = new();
        public readonly Cpu Cpu = new();
        public readonly KProcess Process;
        public readonly KThread[] Threads;
        public readonly HorizonBoundary Horizon;
        public readonly DeviceBoundary Device;
        public readonly WindowBase Window;
        public readonly PhysicalMemory Physical;
        public Session(int threads = 6)
        {
            var context = new ArmProcessContext<Ryujinx.Cpu.Memory>(1, Cpu, Gpu, Memory, 0x10000, true);
            Process = new(new KernelContext(), context);
            Threads = Enumerable.Range(0, threads).Select(_ => new KThread(Process, new Ryujinx.Cpu.ExecutionContext())).ToArray();
            Horizon = new(Process, Threads);
            Device = new() { Gpu = Gpu, System = Horizon };
            Window = new(Device);
            Physical = Gpu.PhysicalMemoryRegistry[1];
            foreach (var thread in Threads) thread.HostThread.Start();
            Until(() => Threads.All(t => (t.HostThread.ThreadState & ThreadState.WaitSleepJoin) != 0), "Guest entry did not reach readiness wait");
            Check(Cpu.Executions == 0 && Threads.All(t => !t.Exited), "Guest ran before GPU readiness");
        }
        public void VerifyReleased(bool executed)
        {
            Check(Threads.All(t => t.Exited && t.SchedFlags == ThreadSchedState.TerminationPending), "Kernel termination was not published");
            Check(Threads.All(t => !t.HostThread.IsAlive), "Guest host thread did not return");
            Check(Threads.All(t => ((Ryujinx.Cpu.ExecutionContext)t.Context).Stops == 1 &&
                ((Ryujinx.Cpu.ExecutionContext)t.Context).Disposals == 1), "Kernel exit/context disposal was missing or duplicated");
            Check(Cpu.Executions == (executed ? Threads.Length : 0), "Unexpected CPU execution after terminal GPU state");
            Check(Cpu.Disposals == 1 && Memory.References == 0, "Process/memory ownership was not released");
            Check(Physical.ShaderCache.Disposed == 1 && Gpu.Renderer.Disposals == 1, "GPU ownership was not released once");
            Window.Dispose();
        }
    }
    static void StartupFailure(bool beforeInitialization, bool unexpectedCancellation = false)
    {
        var s = new Session();
        using var entered = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        Exception failure = unexpectedCancellation ? new OperationCanceledException("Unrequested loader cancellation") :
            new InvalidOperationException("Original GPU startup failure");
        if (beforeInitialization) s.Window.BeforeRender = () => throw failure;
        else
        {
            s.Gpu.HostInitalized.Set();
            s.Memory.InitializeShaderCache = _ => { entered.Set(); release.Wait(); throw failure; };
        }
        Task<Exception> owner = Task.Run(() => Capture(s.Window.Execute));
        try
        {
            if (!beforeInitialization)
            {
                Event(entered, "Loader did not enter");
                Check(!s.Gpu.TerminalSignalled && s.Cpu.Executions == 0, "Active loader opened readiness early");
                release.Set();
            }
            Event(s.Horizon.Entered, "Session owner did not stop guest after render failure");
            if (!Adapted)
            {
                Check(!owner.IsCompleted && s.Threads.All(t => !t.Exited) && !s.Gpu.TerminalSignalled,
                    "Control failed to reproduce startup termination deadlock");
                _blockedControls++;
                // Test-only rescue of the old deadlock. This deliberately runs
                // the CPU double; the candidate must never need this rescue.
                s.Gpu.ReleaseLegacyWaitersForCleanup();
            }
            Wait(owner, "Failed startup left the session owner blocked");
            Check(owner.Result is InvalidOperationException outer && ReferenceEquals(outer.InnerException, failure),
                "Original initialization error did not reach the owner");
            Check(s.Device.Frames == 0, "Guest frame ran after failed initialization");
            s.VerifyReleased(executed: !Adapted);
            _cases++;
        }
        finally { release.Set(); }
    }
    static void SuccessfulStartup()
    {
        var s = new Session();
        s.Gpu.HostInitalized.Set();
        Task<Exception> owner = Task.Run(() => Capture(s.Window.Execute));
        Wait(owner, "Successful session did not close");
        Check(owner.Result == null && s.Device.Frames > 0, "Successful startup behavior changed");
        Check(s.Gpu.Renderer.Flushes == 1 && s.Physical.ShaderCache.Calls == 1, "Success did not load/flush once");
        s.VerifyReleased(executed: true);
        _cases++;
    }
    static void CancelPending()
    {
#if GPU_STARTUP_ADAPTED
        var s = new Session();
        s.Gpu.CancelShaderCacheInitialization();
        Check(!s.Gpu.InitializeShaderCache(CancellationToken.None), "Pending cancellation was replaced by success");
        s.Horizon.Dispose();
        Check(s.Cpu.Executions == 0 && s.Physical.ShaderCache.Calls == 0, "Cancelled pre-entry startup ran CPU/cache work");
        Check(!s.Gpu.WaitUntilGpuReady(), "Cancelled state became ready");
        s.Gpu.Dispose();
        s.VerifyReleased(executed: false);
        _cases++; _cancelCases++;
#endif
    }
    static void CancelActive(bool hostReady, bool failAfterCancellation)
    {
#if GPU_STARTUP_ADAPTED
        var s = new Session();
        using var entered = new ManualResetEventSlim();
        using var cancelled = new ManualResetEventSlim();
        using var release = new ManualResetEventSlim();
        Exception failure = new InvalidOperationException("Failure after cancellation while loader unwinds");
        if (hostReady)
        {
            s.Gpu.HostInitalized.Set();
            s.Memory.InitializeShaderCache = token =>
            {
                using var registration = token.Register(cancelled.Set);
                entered.Set(); release.Wait();
                if (failAfterCancellation) throw failure;
            };
        }
        Task<Exception> owner = Task.Run(() => Capture(s.Window.Execute));
        try
        {
            if (hostReady) Event(entered, "Active cache did not start");
            else Until(() => s.Gpu.InitializationActive, "Initializer did not begin waiting for host readiness");
            s.Window.RequestStop();
            Event(s.Horizon.Entered, "Cancellation did not begin guest termination");
            if (hostReady)
            {
                Event(cancelled, "Active loader did not receive cancellation token");
                Check(!s.Gpu.TerminalSignalled && s.Threads.All(t => !t.Exited), "Cancellation opened readiness before loader unwind");
                Check(s.Physical.Disposals == 0 && s.Memory.References == 2 && s.Physical.ShaderCache.Loading == 1,
                    "Cancellation released memory/cache while loader still used it");
                Check(!owner.IsCompleted && s.Cpu.Executions == 0, "Owner/guest continued before safe loader exit");
            }
            release.Set();
            Wait(owner, "Cancellation did not drain and stop the session");
            if (failAfterCancellation)
                Check(owner.Result is InvalidOperationException outer && ReferenceEquals(outer.InnerException, failure),
                    "Cancellation masked an unrelated loader failure");
            else Check(owner.Result == null, "Expected cancellation became a render failure");
            Check(s.Device.Frames == 0 && s.Cpu.Executions == 0, "Cancelled initializer executed guest work");
            if (!failAfterCancellation) Check(s.Gpu.Renderer.Flushes == 1, "Cancelled callback skipped its flush/drain path");
            s.VerifyReleased(executed: false);
            _cases++; _cancelCases++;
        }
        finally { release.Set(); }
#endif
    }
    static void StableTerminalState()
    {
#if GPU_STARTUP_ADAPTED
        foreach (bool success in new[] { false, true })
        {
            var s = new Session();
            s.Gpu.HostInitalized.Set();
            Exception failure = new InvalidOperationException("Initial failure");
            if (!success) s.Memory.InitializeShaderCache = _ => throw failure;
            var observed = Capture(() => s.Gpu.InitializeShaderCache(CancellationToken.None));
            Check(success ? observed == null : ReferenceEquals(observed, failure), "Initializer changed original exception");
            s.Gpu.CancelShaderCacheInitialization();
            Check(s.Gpu.WaitUntilGpuReady() == success, "Cancellation overwrote a completed terminal state");
            Check(s.Gpu.InitializeShaderCache(CancellationToken.None) == success && s.Physical.ShaderCache.Calls == 1,
                "Terminal state was retried or replaced");
            var late = new KThread(s.Process, new Ryujinx.Cpu.ExecutionContext());
            late.HostThread.Start();
            Check(late.HostThread.Join(10000) && late.Exited, "Late readiness waiter missed terminal publication");
            s.Horizon.Dispose();
            Check(s.Cpu.Executions == (success ? s.Threads.Length + 1 : 0), "Late waiter ran guest after failure");
            s.Gpu.Dispose();
            Check(s.Memory.References == 0 && s.Cpu.Disposals == 1, "Terminal-state cleanup leaked process memory");
            s.Window.Dispose();
            _cases++;
        }
#endif
    }
    static void Main()
    {
        StartupFailure(beforeInitialization: true);
        StartupFailure(beforeInitialization: false);
        StartupFailure(beforeInitialization: false, unexpectedCancellation: true);
        SuccessfulStartup();
        CancelPending();
        CancelActive(hostReady: false, failAfterCancellation: false);
        CancelActive(hostReady: true, failAfterCancellation: false);
        CancelActive(hostReady: true, failAfterCancellation: true);
        StableTerminalState();
        Console.WriteLine(JsonSerializer.Serialize(new { variant = Adapted ? "candidate" : "control", checks = _checks,
            cases = _cases, cancellationCases = _cancelCases, reproducedBlockedControls = _blockedControls,
            guestThreadsPerCase = 6, kernelEntryExitAndTerminationLoopReal = true,
            sourceLifecycleOwnerReal = true, physicalDeviceTested = false, timingGate = false }));
    }
}
