// melonx_guest_start_during_shader_load_test.py: launches, stops and failures of the GPU initialization with a guest.
// Each launch follows the embedded host: the guest process is created and its first thread started (it enters the real
// ArmProcessContext.Execute), then the GPU thread calls the real InitializeShaderCache and runs WindowBase.Render's loop
// only when it answered true; a stop is WindowBase.Execute's lambda (cancel the initialization, cancel the window's
// token, terminate the guest), then the release of the GPU once the loop has drained.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Cpu;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.HLE.HOS;

sealed class Launch
{
    private const int JoinMs = 10000;
    public readonly World World = new();
    public readonly GpuContext Gpu;
    private readonly ArmProcessContext<GuestMemory> _process;
    private readonly GuestMemory _memory = new();
    private readonly List<Thread> _guestThreads = new();
    private readonly CancellationTokenSource _windowToken = new();
    private readonly ManualResetEventSlim _renderDrained = new(false);
    private Thread _gpuThread;
    private volatile bool _renderAllowed = true;
    private int _destroyed;

    public double GpuStartMs = -1, UnregisterEnterMs = -1, UnregisterReturnMs = -1, StopMs = -1, StopReturnedMs = -1, ReleaseEnterMs = -1, ReleaseReturnMs = -1;
    public bool? InitializeResult;
    public bool UnregisterReturnedDuringLoad, WaitUntilGpuReady;
    public int BlockedThreads;
    public string RenderFailure = "", DisposeFailure = "", StateBeforeRelease = "";

    public Launch(Action<World> configure = null, bool hostInitialized = true)
    {
        World.Current = World;
        configure?.Invoke(World);
        Gpu = new GpuContext(World);
        Gpu.ShaderCacheStateChanged += (state, current, total) => { if (state == ShaderCacheState.Loaded) World.LoadedEventSeen = true; };
        if (hostInitialized) SetHostInitialized();
        // ProcessLoader: the process registers its memory with the GPU context when it is created.
        _process = new ArmProcessContext<GuestMemory>(1, new GuestCpu(World), Gpu, _memory, 1UL << 39, true);
    }

    public void SetHostInitialized()
    {
        World.HostInitializedSet = true;
        Gpu.HostInitalized.Set();
    }

    // KThread.ThreadStart: the host thread of a guest thread enters the process context.
    public Thread StartGuestThread()
    {
        Thread thread = null;
        thread = new Thread(() =>
        {
            bool forbidden = World.GuestForbidden;
            World.RanGuestCode = false;
            _process.Execute(null, 0);
            if (!World.RanGuestCode) Interlocked.Increment(ref World.ThreadsEndedWithoutRunning);
            else if (forbidden) Interlocked.Increment(ref World.ForbiddenGuestRuns);
            // A guest that exits by itself: its last thread drops the process (KProcess.Destroy).
            if (World.RanGuestCode && !World.TerminateRequested && World.GuestExitAfterMs >= 0) DestroyProcess();
        }) { IsBackground = true, Name = "Guest" };
        lock (_guestThreads) _guestThreads.Add(thread);
        thread.Start();
        return thread;
    }

    private void DestroyProcess()
    {
        if (Interlocked.Exchange(ref _destroyed, 1) != 0) return;
        UnregisterEnterMs = World.Now;
        _process.Dispose(); // the real ArmProcessContext.Dispose: GpuContext.UnregisterProcess
        UnregisterReturnedDuringLoad = Volatile.Read(ref World.LoadsRunning) != 0;
        UnregisterReturnMs = World.Now;
    }

    // ThreadedRenderer's GPU thread running WindowBase.Render's lambda.
    public void StartGpuThread()
    {
        _gpuThread = new Thread(() =>
        {
            try
            {
                GpuStartMs = World.Now;
                bool gpuReady;
                try { gpuReady = Gpu.InitializeShaderCache(_windowToken.Token); }
                catch { World.GuestForbidden = true; throw; }
                InitializeResult = gpuReady;

                while (gpuReady && _renderAllowed)
                {
                    // Device.WaitFifo / Device.ProcessFrame: the first GPU command is processed here.
                    while (World.Fifo.TryDequeue(out _))
                    {
                        if (World.FirstCommandMs < 0) World.FirstCommandMs = World.Now;
                        if (Volatile.Read(ref World.LoadsRunning) != 0 || Volatile.Read(ref World.LoadsEnded) == 0) World.CommandsDuringLoad++;
                        if (Volatile.Read(ref World.Table) != World.Programs) World.CommandsWithPartialTable++;
                        Interlocked.Increment(ref World.CommandsProcessed);
                        // The command's syncpoint increment: what the guest's fence waits for.
                        if (World.FenceSyncpoint >= 0) Gpu.Synchronization.IncrementSyncpoint((uint)World.FenceSyncpoint);
                    }
                    Gpu.RunDeferredActions();
                    Thread.Sleep(1);
                }
            }
            catch (Exception error) { RenderFailure = error.GetType().Name; }
            finally { _renderDrained.Set(); }
        }) { IsBackground = true, Name = "GPU.MainThread" };
        _gpuThread.Start();
    }

    // WindowBase.Execute's stop lambda. A guest thread created after it may execute only if the GPU was already ready.
    public void CancelInitialization()
    {
        Gpu.CancelShaderCacheInitialization();
        if (Gpu.State != "Ready") World.GuestForbidden = true;
        _windowToken.Cancel();
    }

    // Device.System.Dispose(): the guest's threads are terminated and joined, then the process is destroyed unless
    // something else still holds it.
    public void TerminateGuest(bool destroyProcess = true)
    {
        World.TerminateRequested = true;
        Thread[] threads;
        lock (_guestThreads) threads = _guestThreads.ToArray();
        foreach (Thread thread in threads) if (!thread.Join(JoinMs)) BlockedThreads++;
        if (destroyProcess) DestroyProcess();
    }

    // EmbeddedWindowLifetime.Run after the stop: the loop drains, then the controlling thread releases the GPU. A render
    // worker that failed has reported the drain while the GPU thread may still be in the loader (waitForDrain false).
    public void ReleaseGpu(bool waitForDrain = true)
    {
        _renderAllowed = false;
        if (waitForDrain && _gpuThread != null && !_renderDrained.Wait(JoinMs)) BlockedThreads++;
        StateBeforeRelease = Gpu.State;
        WaitUntilGpuReady = StateBeforeRelease != "Pending" && StateBeforeRelease != "Initializing" && Gpu.WaitUntilGpuReady();
        ReleaseEnterMs = World.Now;
        try { Gpu.Dispose(); }
        catch (Exception error) { DisposeFailure = error.GetType().Name; }
        ReleaseReturnMs = World.Now;
        if (_gpuThread != null && !_gpuThread.Join(JoinMs)) BlockedThreads++;
        lock (_guestThreads) foreach (Thread thread in _guestThreads) if (!thread.Join(JoinMs)) BlockedThreads++;
    }

    public void Stop(bool destroyProcess = true, bool waitForDrain = true)
    {
        StopMs = World.Now;
        CancelInitialization();
        TerminateGuest(destroyProcess);
        StopReturnedMs = World.Now;
        ReleaseGpu(waitForDrain);
    }

    public bool WaitFor(Func<bool> condition, int milliseconds = JoinMs) => SpinWait.SpinUntil(condition, milliseconds);

    // A service thread waiting for a fence: NvHostEvent's forced wait (NvFence.Wait with an infinite timeout, or
    // WaitOnSyncpointWhileProgressing under the Hogwarts policy), or a wait with the timeout the guest gave.
    public sealed class Waiter
    {
        public Thread Thread;
        public double IssuedMs, ReturnedMs = -1;
        public string Outcome = "";
        public uint Value;
        public bool LoadRunningAtReturn;
        public int CommandsAtReturn;
    }

    private Waiter StartWaiter(uint id, Func<string> wait)
    {
        Waiter waiter = new();
        waiter.Thread = new Thread(() =>
        {
            waiter.IssuedMs = World.Now;
            waiter.Outcome = wait();
            waiter.LoadRunningAtReturn = Volatile.Read(ref World.LoadsRunning) != 0;
            waiter.CommandsAtReturn = Volatile.Read(ref World.CommandsProcessed);
            waiter.Value = Gpu.Synchronization.GetSyncpointValue(id);
            waiter.ReturnedMs = World.Now;
        }) { IsBackground = true, Name = "Nv" };
        waiter.Thread.Start();
        return waiter;
    }

    public Waiter Wait(uint id, TimeSpan timeout) =>
        StartWaiter(id, () => Gpu.Synchronization.WaitOnSyncpoint(id, 1, timeout) ? "timedOut" : "signalled");

    public Waiter WaitProgressing(uint id, bool idle, int sliceMs, int noProgressMs, int capMs) =>
        StartWaiter(id, () => Gpu.Synchronization.WaitOnSyncpointWhileProgressing(id, 1, TimeSpan.FromMilliseconds(sliceMs),
            TimeSpan.FromMilliseconds(noProgressMs), TimeSpan.FromMilliseconds(capMs), () => Volatile.Read(ref World.CommandsProcessed),
            () => 0, () => idle, () => World.TerminateRequested).ToString());

    public void Join(params Waiter[] waiters)
    {
        foreach (Waiter waiter in waiters) if (!waiter.Thread.Join(JoinMs)) BlockedThreads++;
    }

    public object Report(Waiter waiter) => new
    {
        issuedMs = Since(waiter.IssuedMs), returnedMs = Since(waiter.ReturnedMs),
        elapsedMs = waiter.ReturnedMs < 0 ? -1 : Math.Round(waiter.ReturnedMs - waiter.IssuedMs, 1),
        outcome = waiter.Outcome, value = waiter.Value, loadRunningAtReturn = waiter.LoadRunningAtReturn, commandsAtReturn = waiter.CommandsAtReturn,
    };

    public double SinceGpuStart(double ms) => Since(ms);

    // Milliseconds since the GPU thread started; -1 for what did not happen.
    private double Since(double ms) => ms < 0 || GpuStartMs < 0 ? -1 : Math.Round(ms - GpuStartMs, 1);

    public object Report() => new
    {
        guestStartMs = Since(World.FirstGuestStartMs), loadBeginMs = Since(World.LoadBeginMs), loadEndMs = Since(World.LoadEndMs),
        loadMs = World.LoadEndMs < 0 ? -1 : Math.Round(World.LoadEndMs - World.LoadBeginMs, 1), firstCommandMs = Since(World.FirstCommandMs),
        stopMs = Since(StopMs), stopReturnedMs = Since(StopReturnedMs), unregisterEnterMs = Since(UnregisterEnterMs), unregisterReturnMs = Since(UnregisterReturnMs),
        releaseEnterMs = Since(ReleaseEnterMs), releaseReturnMs = Since(ReleaseReturnMs),
        initializeResult = InitializeResult, state = StateBeforeRelease, waitUntilGpuReady = WaitUntilGpuReady,
        loadsBegun = World.LoadsBegun, table = World.Table, programs = World.Programs, loadedEventSeen = World.LoadedEventSeen,
        guestThreadsRan = World.GuestThreadsRan, guestStartsDuringLoad = World.GuestStartsDuringLoad,
        guestStartsBeforeLoadEnded = World.GuestStartsBeforeLoadEnded, guestStartsBeforeSnapshot = World.GuestStartsBeforeSnapshot,
        guestStartsBeforeHostInitialized = World.GuestStartsBeforeHostInitialized, forbiddenGuestRuns = World.ForbiddenGuestRuns,
        threadsEndedWithoutRunning = World.ThreadsEndedWithoutRunning, kernelExits = World.KernelExits,
        commands = World.CommandsProcessed, commandsDuringLoad = World.CommandsDuringLoad, commandsWithPartialTable = World.CommandsWithPartialTable,
        unregisterReturnedDuringLoad = UnregisterReturnedDuringLoad, handlersRemovedDuringLoad = World.HandlersRemovedDuringLoad,
        destroysQueuedDuringLoad = World.DestroysQueuedDuringLoad, destroysQueued = World.DestroysQueued,
        cachesDisposed = World.CachesDisposed, cachesDisposedDuringLoad = World.CachesDisposedDuringLoad,
        eventsDisposedDuringLoad = World.EventsDisposedDuringLoad, blockedThreads = BlockedThreads,
        renderFailure = RenderFailure, disposeFailure = DisposeFailure, journal = World.Journal.ToArray(),
        errorLines = World.ErrorLines,
    };
}

static class Program
{
    // 1. A launch: the guest's first thread exists before the GPU thread starts; a second thread starts in the middle of
    // the load and a third after it.
    static object LaunchCase()
    {
        Launch launch = new();
        launch.StartGuestThread();
        Thread.Sleep(50);
        launch.StartGpuThread();
        Thread.Sleep(300);
        launch.StartGuestThread();
        launch.WaitFor(() => launch.World.CommandsProcessed >= 6);
        launch.StartGuestThread();
        launch.WaitFor(() => launch.World.CommandsProcessed >= 9);
        launch.Stop();
        return launch.Report();
    }

    // 2. Stopped before the GPU thread reached the loader (the stop lambda also covers a renderer setup that failed).
    static object CancelBeforeLoaderCase()
    {
        Launch launch = new();
        launch.StartGuestThread();
        Thread.Sleep(50);
        launch.CancelInitialization();
        bool released = launch.WaitFor(() => launch.World.ThreadsEndedWithoutRunning == 1, 5000);
        launch.StartGpuThread(); // an early stop still starts the GPU service (EmbeddedWindowLifetime.Run)
        launch.StartGuestThread();
        launch.TerminateGuest();
        launch.ReleaseGpu();
        return new { released, report = launch.Report() };
    }

    // 3. Stopped during the load; a guest thread created after the cancellation must not execute.
    static object CancelDuringLoadCase(bool throwOnCancel)
    {
        Launch launch = new(world => { world.UnwindMs = 150; world.ThrowOnCancel = throwOnCancel; });
        launch.StartGuestThread();
        launch.StartGpuThread();
        Thread.Sleep(200);
        launch.StopMs = launch.World.Now;
        launch.CancelInitialization();
        launch.StartGuestThread();
        launch.TerminateGuest();
        launch.StopReturnedMs = launch.World.Now;
        launch.ReleaseGpu();
        return launch.Report();
    }

    // 4. The loader fails half way; the render worker's failure makes the owner stop the session.
    static object LoaderFailureCase()
    {
        Launch launch = new(world => { world.FailAt = 30; world.UnwindMs = 100; });
        launch.StartGuestThread();
        launch.StartGpuThread();
        launch.WaitFor(() => launch.RenderFailure != "");
        launch.StartGuestThread();
        Thread.Sleep(50);
        launch.Stop();
        return launch.Report();
    }

    // 5. The guest process ends by itself 100 ms after it started executing.
    static object GuestExitCase()
    {
        Launch launch = new(world => world.GuestExitAfterMs = 100);
        launch.StartGuestThread();
        launch.StartGpuThread();
        launch.WaitFor(() => launch.UnregisterReturnMs >= 0 && launch.World.CachesDisposed == 1);
        launch.Stop();
        return launch.Report();
    }

    // 6. The render worker failed while the GPU thread loads (the drain is reported at once) and something still holds
    // the process: neither the drain nor an unregistration orders the release after the loader.
    static object RenderWorkerFailedCase()
    {
        Launch launch = new(world => world.UnwindMs = 150);
        launch.StartGuestThread();
        launch.StartGpuThread();
        Thread.Sleep(200);
        launch.Stop(destroyProcess: false, waitForDrain: false);
        return launch.Report();
    }

    // 8. Fences while a 2 s load runs, then after it. The guest's commands increment syncpoint 5 once the GPU thread
    // processes them; nothing increments the other syncpoints unless said.
    static object FenceDuringLoadCase()
    {
        Launch launch = new(world => { world.Programs = 100; world.ProgramMs = 20; world.FenceSyncpoint = 5; });
        launch.StartGuestThread();
        launch.StartGpuThread();
        Thread.Sleep(100);
        Launch.Waiter forced = launch.Wait(5, Timeout.InfiniteTimeSpan);
        Launch.Waiter never = launch.Wait(7, Timeout.InfiniteTimeSpan);
        Launch.Waiter finite = launch.Wait(8, TimeSpan.FromMilliseconds(300));
        Launch.Waiter idle = launch.WaitProgressing(5, idle: true, sliceMs: 100, noProgressMs: 300, capMs: 600);
        Launch.Waiter busy = launch.WaitProgressing(5, idle: false, sliceMs: 100, noProgressMs: 300, capMs: 600);
        launch.Join(forced, never, finite, idle, busy);
        launch.WaitFor(() => launch.InitializeResult != null && Volatile.Read(ref launch.World.CommandsProcessed) >= 3);
        Thread.Sleep(50);
        int errorsDuringLoad = launch.World.ErrorLines;

        // The same waits issued once the load has ended.
        Launch.Waiter later = launch.Wait(9, Timeout.InfiniteTimeSpan);
        Launch.Waiter laterNever = launch.Wait(10, Timeout.InfiniteTimeSpan);
        Launch.Waiter laterFinite = launch.Wait(12, TimeSpan.FromMilliseconds(300));
        Launch.Waiter laterIdle = launch.WaitProgressing(11, idle: true, sliceMs: 100, noProgressMs: 300, capMs: 600);
        Launch.Waiter laterBusy = launch.WaitProgressing(11, idle: false, sliceMs: 100, noProgressMs: 300, capMs: 600);
        Thread.Sleep(200);
        launch.Gpu.Synchronization.IncrementSyncpoint(9);
        launch.Join(later, laterNever, laterFinite, laterIdle, laterBusy);
        launch.Stop();
        return new
        {
            forced = launch.Report(forced), never = launch.Report(never), finite = launch.Report(finite), idle = launch.Report(idle),
            busy = launch.Report(busy), later = launch.Report(later), laterNever = launch.Report(laterNever), laterFinite = launch.Report(laterFinite),
            laterIdle = launch.Report(laterIdle), laterBusy = launch.Report(laterBusy), errorsDuringLoad, report = launch.Report(),
        };
    }

    // 9. A stop while waits are parked in a load whose loader takes 500 ms to unwind; then a wait issued after it.
    static object FenceCancelCase()
    {
        Launch launch = new(world => { world.Programs = 100; world.ProgramMs = 20; world.UnwindMs = 500; });
        launch.StartGuestThread();
        launch.StartGpuThread();
        Thread.Sleep(100);
        Launch.Waiter parked = launch.Wait(7, Timeout.InfiniteTimeSpan);
        Launch.Waiter parkedProgressing = launch.WaitProgressing(7, idle: false, sliceMs: 100, noProgressMs: 700, capMs: 5000);
        Thread.Sleep(300);
        double cancelMs = launch.World.Now;
        launch.StopMs = cancelMs;
        launch.CancelInitialization();
        launch.Join(parked, parkedProgressing);
        launch.TerminateGuest();
        launch.StopReturnedMs = launch.World.Now;
        Launch.Waiter afterCancel = launch.Wait(7, Timeout.InfiniteTimeSpan);
        launch.Join(afterCancel);
        launch.ReleaseGpu();
        return new
        {
            cancelMs = launch.SinceGpuStart(cancelMs), parked = launch.Report(parked), parkedProgressing = launch.Report(parkedProgressing),
            afterCancel = launch.Report(afterCancel), report = launch.Report(),
        };
    }

    // 10. The loader fails at 200 ms and takes 300 ms to unwind while a wait is parked.
    static object FenceFailureCase()
    {
        Launch launch = new(world => { world.Programs = 100; world.ProgramMs = 20; world.FailAt = 10; world.UnwindMs = 300; });
        launch.StartGuestThread();
        launch.StartGpuThread();
        Thread.Sleep(50);
        Launch.Waiter parked = launch.Wait(7, Timeout.InfiniteTimeSpan);
        launch.Join(parked);
        launch.WaitFor(() => launch.RenderFailure != "");
        launch.Stop();
        return new { parked = launch.Report(parked), report = launch.Report() };
    }

    // 7. Randomized small delays: every order of guest thread start, loader start, host initialization, cancellation,
    // loader failure, guest exit and stop.
    static object RaceCase(int iterations, int seed)
    {
        Random random = new(seed);
        string[] modes = { "none", "cancelBefore", "cancelDuring", "fail", "guestExit" };
        Dictionary<string, int> perMode = modes.ToDictionary(mode => mode, _ => 0);
        int commandsDuringLoad = 0, commandsWithPartialTable = 0, forbiddenGuestRuns = 0, guestRanAfterCancelBeforeLoader = 0;
        int guestStartsBeforeSnapshot = 0, guestStartsBeforeHostInitialized = 0, guestStartsBeforeLoadEnded = 0, launchesWithGuestBeforeLoadEnd = 0;
        int handlersRemovedDuringLoad = 0, destroysQueuedDuringLoad = 0, cachesDisposedDuringLoad = 0, eventsDisposedDuringLoad = 0, unregisterReturnedDuringLoad = 0;
        int blockedThreads = 0, unexpectedFailures = 0, commandsWithoutReady = 0, readyMismatch = 0, journalLines = 0, launchesWithCommands = 0;

        for (int iteration = 0; iteration < iterations; iteration++)
        {
            string mode = modes[random.Next(modes.Length)];
            perMode[mode]++;
            int programs = random.Next(3, 13), guestDelay = random.Next(0, 8), gpuDelay = random.Next(0, 8), extraDelay = random.Next(0, 30);
            int eventDelay = random.Next(0, programs * 2 + 6), hostDelay = random.Next(4) == 0 ? random.Next(1, 6) : -1;
            bool throwOnCancel = random.Next(2) == 0, leakProcess = random.Next(4) == 0, failedWorker = random.Next(4) == 0;
            Launch launch = new(world =>
            {
                world.Programs = programs;
                world.ProgramMs = 2;
                world.UnwindMs = random.Next(0, 6);
                world.ThrowOnCancel = throwOnCancel;
                world.FailAt = mode == "fail" ? random.Next(programs) : -1;
                world.GuestExitAfterMs = mode == "guestExit" ? random.Next(0, programs * 2 + 4) : -1;
            }, hostInitialized: hostDelay < 0);

            Thread guest = new(() => { Thread.Sleep(guestDelay); launch.StartGuestThread(); Thread.Sleep(extraDelay); launch.StartGuestThread(); });
            Thread host = new(() => { if (hostDelay >= 0) { Thread.Sleep(hostDelay); launch.SetHostInitialized(); } });
            guest.Start();
            host.Start();

            if (mode == "cancelBefore")
            {
                Thread.Sleep(eventDelay % 6);
                launch.CancelInitialization();
                launch.StartGpuThread();
            }
            else
            {
                Thread.Sleep(gpuDelay);
                launch.StartGpuThread();
                Thread.Sleep(eventDelay);
            }

            host.Join();
            guest.Join();
            if (mode == "none" || mode == "guestExit") launch.WaitFor(() => launch.InitializeResult != null, 5000);
            if (mode == "none") launch.WaitFor(() => launch.World.Fifo.IsEmpty, 5000);
            // A failed render worker and a process something still holds leave the release to its own wait.
            launch.Stop(destroyProcess: !leakProcess, waitForDrain: !failedWorker);

            World world = launch.World;
            commandsDuringLoad += world.CommandsDuringLoad;
            commandsWithPartialTable += world.CommandsWithPartialTable;
            if (world.CommandsProcessed != 0) launchesWithCommands++;
            if (world.CommandsProcessed != 0 && launch.InitializeResult != true) commandsWithoutReady++;
            forbiddenGuestRuns += world.ForbiddenGuestRuns;
            if (mode == "cancelBefore") guestRanAfterCancelBeforeLoader += world.GuestThreadsRan;
            guestStartsBeforeSnapshot += world.GuestStartsBeforeSnapshot;
            guestStartsBeforeHostInitialized += world.GuestStartsBeforeHostInitialized;
            guestStartsBeforeLoadEnded += world.GuestStartsBeforeLoadEnded;
            if (world.GuestStartsBeforeLoadEnded != 0) launchesWithGuestBeforeLoadEnd++;
            handlersRemovedDuringLoad += world.HandlersRemovedDuringLoad;
            destroysQueuedDuringLoad += world.DestroysQueuedDuringLoad;
            cachesDisposedDuringLoad += world.CachesDisposedDuringLoad;
            eventsDisposedDuringLoad += world.EventsDisposedDuringLoad;
            if (launch.UnregisterReturnedDuringLoad) unregisterReturnedDuringLoad++;
            blockedThreads += launch.BlockedThreads;
            // The only failure a launch may report is the loader's own, in its mode.
            if (launch.DisposeFailure != "" || (launch.RenderFailure != "" && !(mode == "fail" && launch.RenderFailure == "InvalidOperationException"))) unexpectedFailures++;
            if (!failedWorker && (launch.StateBeforeRelease == "Ready") != (launch.InitializeResult == true)) readyMismatch++;
            journalLines += world.Journal.Count;
            if (world.Journal.Count > 1) unexpectedFailures++;
        }

        return new
        {
            iterations, seed, perMode, commandsDuringLoad, commandsWithPartialTable, commandsWithoutReady, launchesWithCommands, forbiddenGuestRuns,
            guestRanAfterCancelBeforeLoader, guestStartsBeforeSnapshot, guestStartsBeforeHostInitialized, guestStartsBeforeLoadEnded,
            launchesWithGuestBeforeLoadEnd, handlersRemovedDuringLoad, destroysQueuedDuringLoad, cachesDisposedDuringLoad, eventsDisposedDuringLoad,
            unregisterReturnedDuringLoad, blockedThreads, unexpectedFailures, readyMismatch, journalLines,
        };
    }

    // A short launch first, not reported: the measured launch then times the waits, not the first compilation of the code.
    static void WarmUp()
    {
        Launch launch = new(world => { world.Programs = 5; world.ProgramMs = 2; });
        launch.StartGuestThread();
        launch.StartGpuThread();
        launch.WaitFor(() => launch.World.CommandsProcessed >= 3);
        launch.Stop();
    }

    static int Main(string[] args)
    {
        WarmUp();
        Dictionary<string, object> report = new() { ["variant"] = args[0] };
        // The candidate without its waits for the loader runs only the two cases that must show the fault.
        bool faultOnly = args[0] == "withoutWaits";
        if (!faultOnly)
        {
            report["launch"] = LaunchCase();
            report["cancelBeforeLoader"] = CancelBeforeLoaderCase();
            report["cancelDuringLoad"] = CancelDuringLoadCase(throwOnCancel: false);
            report["cancelDuringLoadThrowing"] = CancelDuringLoadCase(throwOnCancel: true);
            report["loaderFailure"] = LoaderFailureCase();
        }
        report["guestExit"] = GuestExitCase();
        report["renderWorkerFailed"] = RenderWorkerFailedCase();
        if (!faultOnly)
        {
            report["fenceDuringLoad"] = FenceDuringLoadCase();
            report["fenceCancel"] = FenceCancelCase();
            report["fenceFailure"] = FenceFailureCase();
            report["race"] = RaceCase(int.Parse(args[2]), int.Parse(args[1]));
        }
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
