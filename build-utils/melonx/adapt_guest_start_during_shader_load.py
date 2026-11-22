"""The guest starts executing while the disk shader cache loads, instead of after it (launch time, every title).

IPA 816-820, 22 November 2026 (private device logs, not in the repository; times and counts only). The shader cache
load (ParallelDiskCacheLoader.LoadShaders) takes 9.2-10.7 s for Super Smash Bros. Ultimate (12,6xx programs) and 2.5 s
for Hogwarts Legacy. The guest then boots for 4.2-6.2 s before its first present, and for the first 3-5 s of that boot
the GPU thread has nothing to do: the two waits are spent one after the other.

Cause. ArmProcessContext.Execute, which every guest thread enters before it executes any CPU code, waits for
GpuContext.WaitUntilGpuReady, and its event is set only when InitializeShaderCache ends (the GPU thread, called by
WindowBase.Render before its loop). The wait is upstream's ("we must wait until shader cache is loaded, among other
things"); adapt_gpu_startup_failure gave it its states (Pending, Initializing, Ready, Failed, Cancelled).

Change (GpuContext.cs, ArmProcessContext.cs; SynchronizationManager.cs for the fences, below).
- GpuContext has a second event, _guestStartEvent. InitializeShaderCache sets it once the host is initialized and the
  loader holds its snapshot of the registered physical memories (ConcurrentDictionary.Values copies), before the first
  ShaderCache.Initialize, unless a cancellation was requested; it is also set wherever _gpuReadyEvent is (the end of
  InitializeShaderCache, CancelShaderCacheInitialization on a pending initialization), just before it, so that the
  ready event stays the last thing a loader touches, and disposed with it.
- WaitUntilGuestMayStart waits for it and answers true when the state is Ready, or Initializing with no cancellation
  requested; a cancelled or failed initialization still answers false and the thread exits through the kernel, as
  before. ArmProcessContext.Execute calls it instead of WaitUntilGpuReady (kept, with no caller left in the tree).
- The GPU thread is unchanged: it enters WindowBase's loop only after InitializeShaderCache returns, so the commands
  the guest submits meanwhile wait in the GPFIFO and every cached program is in the tables before the first of them.
- The old wait also meant "the loader has returned and joined its workers before guest threads can unregister memory
  or the owner can dispose caches". UnregisterProcess (a guest process ends) and Dispose now wait for the loader's
  terminal event themselves when the state is Initializing (WaitForShaderCacheLoader, outside the state lock). In
  this tree PhysicalMemory.Dispose already hands the caches' destruction to the GPU thread (adapt_gpu_lifetime), so
  in UnregisterProcess the wait keeps the former order (the unregistration, the progress handler's removal and the
  queued destruction follow the loader) rather than preventing a use-after-dispose. Dispose's wait does prevent one:
  after a failed render worker the drain is reported while the loader may still run, and only the join of the
  waiting guest thread ordered the release after it. No deadlock: the loader (GPU thread) waits only for its own
  translation threads and the render thread and calls the host's progress callback, as before; it never waits for a
  guest, service or controlling thread and takes no kernel lock. The stop (WindowBase's lambda) requests the
  cancellation before it terminates the guest, and its controlling thread already waited for the loader through the
  guest thread it joined.
- One durable journal line, "launch guestStartedDuringShaderLoad", when the first guest thread is released during a
  load. One lock and one event wait per guest thread start, as before; nothing in the frame loop.

What the guest reaches earlier, all through paths that already run on service threads beside a busy GPU thread during
play: GPU channel and memory manager creation, GPU memory map/unmap (the texture and buffer caches' handlers, which
the loader does not touch), GPFIFO submissions (a concurrent queue, prefetched on the service thread), syncpoints
(their own locks), Window.EnqueueFrameThreadSafe (a concurrent queue). None of them calls the renderer or reads the
shader tables the loader fills; the loader reads the cache files, not guest memory.

Fences while the cache loads. A title that reaches its first submissions before the end of the load waits on fences
the GPU thread cannot reach yet. NVN's timed waits fail, the guest cancels, and after two cancellations
NvHostEvent.Wait forces the wait on the CPU side: Fence.Wait(infinite) -> SynchronizationManager.WaitOnSyncpoint,
which clamps an infinite wait to 1 s and then lets its caller tell the guest the fence was reached; under the Hogwarts
policy WaitOnSyncpointWhileProgressing, which gives up when the GPU side looks idle or makes no progress. Before this
change no guest code ran in that state; with it, each would report a fence reached although the GPU thread has
processed nothing (Super Smash Bros. Ultimate: a 9-10 s load, first submissions expected after 3-5 s).
Resolution (SynchronizationManager.cs, told by GpuContext.GetShaderLoadPhase through a delegate given at construction:
Running while a loader runs with no cancellation requested, Ready once it ended ready, None otherwise):
- WaitOnSyncpoint with an infinite timeout, issued while the phase is Running, waits in 50 ms slices until the fence is
  signalled or the phase changes: Ready, it then waits its usual 1 s from that moment, as a wait issued then; None
  (cancelled, failed: the guest is being stopped), it ends at once, unsignalled, so a parked service thread wakes
  within a slice of CancelShaderCacheInitialization. A finite timeout is unchanged: it ends when the guest asked.
- WaitOnSyncpointWhileProgressing treats Running as progress pending: no idle or no-progress fallback and no cap while
  it lasts (checked at its 50 ms poll); Ready, its clocks restart from that moment; None, it ends as cancelled.
- Once the load has ended ready the manager remembers it: every later wait reads one volatile flag and is today's,
  for every title and the whole of play. A wait issued before a loader runs, or after a cancelled or failed one, is
  today's too. The GPU-side waits (GPFifoClass, on the GPU thread, hence after the load) and AndroidFence's (the GPU
  thread at present) never see Running; Host1xClass's infinite wait follows the same rule on its own thread.
- One durable journal line, "launch syncpointWaitHeldForShaderLoad", for the first wait held beyond the former 1 s.

Not measured on an iPhone, and not covered by the host gate: the gain itself (the loader's eight translation threads
and the guest's boot now share the cores, so the load may last longer); what a title does while its fences wait for
the end of the load (the guest's own timed waits still fail and are retried, as during any long GPU stall; a game's
own watchdog is unknown); guest audio and guest time advancing behind the shader progress screen; the memory peak of
a load and a boot at once.
Fail closed on drift: each file must be the preparation after adapt_deferred_release_roots.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': 'a0fd265deec4cb5ae0676495f42733add8be1435d2dd47f0d3601dbe5adc5c01',
    'src/Ryujinx.Graphics.Gpu/Synchronization/SynchronizationManager.cs': '04bd68ec461e397f90ba02d851b1be467a6aa4137af3caecffba0c46119e531b',
    'src/Ryujinx.HLE/HOS/ArmProcessContext.cs': '181ace86bf35ee4fce3d961bacdfceb780c8e02552839b407d112c0e934ceffd',
}

GPU_PAIRS = (
    ('''            Synchronization = new SynchronizationManager();
''', '''            // RewindBox (adapt_guest_start_during_shader_load): infinite syncpoint waits do not give up while the cache loads.
            Synchronization = new SynchronizationManager(GetShaderLoadPhase);
'''),
    ('''        private readonly ManualResetEvent _gpuReadyEvent;
        private readonly object _gpuInitializationLock = new();
''', '''        private readonly ManualResetEvent _gpuReadyEvent;
        // RewindBox (adapt_guest_start_during_shader_load): set once guest threads may execute CPU code: the shader cache
        // loader holds its snapshot of the registered physical memories, or the initialization ended (as _gpuReadyEvent).
        private readonly ManualResetEvent _guestStartEvent;
        private long _guestReleaseTimestamp;
        private int _shaderLoadMemories;
        private int _guestStartJournaled;
        private readonly object _gpuInitializationLock = new();
'''),
    ('''            _gpuReadyEvent = new ManualResetEvent(false);
''', '''            _gpuReadyEvent = new ManualResetEvent(false);
            _guestStartEvent = new ManualResetEvent(false);
'''),
    ('''        public void UnregisterProcess(ulong pid)
        {
            if (PhysicalMemoryRegistry.TryRemove(pid, out PhysicalMemory physicalMemory))
''', '''        public void UnregisterProcess(ulong pid)
        {
            // RewindBox (adapt_guest_start_during_shader_load): a guest process can end while the cache loads; its memory
            // is unregistered only once the loader has returned, as when the guest started after the load.
            WaitForShaderCacheLoader();

            if (PhysicalMemoryRegistry.TryRemove(pid, out PhysicalMemory physicalMemory))
'''),
    ('''                    token.ThrowIfCancellationRequested();

                    foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
                    {
''', '''                    token.ThrowIfCancellationRequested();

                    // RewindBox (adapt_guest_start_during_shader_load): the loader's snapshot of the registered memories
                    // (Values copies them), then the guest is released and executes while the cache loads. This thread
                    // processes no GPU command before it returns from here: what the guest submits waits in the GPFIFO
                    // until every cached program is in the tables.
                    ICollection<PhysicalMemory> physicalMemories = PhysicalMemoryRegistry.Values;
                    ReleaseGuestForShaderLoad(physicalMemories.Count);

                    foreach (PhysicalMemory physicalMemory in physicalMemories)
                    {
'''),
    ('''                // The loader has returned and joined its workers before guest
                // threads can unregister memory or the owner can dispose caches.
                lock (_gpuInitializationLock)
''', '''                // The loader has returned and joined its workers before guest
                // threads can unregister memory or the owner can dispose caches.
                // RewindBox (adapt_guest_start_during_shader_load): guest threads run during the load now, so
                // UnregisterProcess and Dispose wait for this event themselves (WaitForShaderCacheLoader).
                lock (_gpuInitializationLock)
'''),
    ('''                    _gpuInitializationState = outcome;
                    _gpuReadyEvent.Set();
''', '''                    _gpuInitializationState = outcome;
                    // RewindBox (adapt_guest_start_during_shader_load): the guest event first. The ready event stays the
                    // loader's last use of this context: UnregisterProcess and Dispose proceed as soon as it is set.
                    _guestStartEvent.Set();
                    _gpuReadyEvent.Set();
'''),
    ('''                    _gpuInitializationState = GpuInitializationState.Cancelled;
                    _gpuReadyEvent.Set();
''', '''                    _gpuInitializationState = GpuInitializationState.Cancelled;
                    _guestStartEvent.Set(); // RewindBox (adapt_guest_start_during_shader_load): cancelled before a loader
                    _gpuReadyEvent.Set();
'''),
    ('''        public bool WaitUntilGpuReady()
        {
            _gpuReadyEvent.WaitOne();

            lock (_gpuInitializationLock)
            {
                return _gpuInitializationState == GpuInitializationState.Ready;
            }
        }
''', '''        public bool WaitUntilGpuReady()
        {
            _gpuReadyEvent.WaitOne();

            lock (_gpuInitializationLock)
            {
                return _gpuInitializationState == GpuInitializationState.Ready;
            }
        }

        /// <summary>
        /// RewindBox (adapt_guest_start_during_shader_load): waits until guest threads may execute CPU code.
        /// </summary>
        /// <remarks>
        /// That is once the shader cache loader has started (host initialized, its snapshot of the registered physical
        /// memories taken) or the initialization has ended. The GPU thread processes no command before the loader
        /// returns, so the guest's submissions wait in the GPFIFO. Called once per guest thread start.
        /// </remarks>
        /// <returns>True if the guest may execute; false if the initialization was cancelled or failed</returns>
        public bool WaitUntilGuestMayStart()
        {
            _guestStartEvent.WaitOne();

            lock (_gpuInitializationLock)
            {
                if (_gpuInitializationState == GpuInitializationState.Ready)
                {
                    return true;
                }

                if (_gpuInitializationState != GpuInitializationState.Initializing || _gpuInitializationCancellationRequested)
                {
                    return false;
                }
            }

            // The first guest thread released while the cache loads, once per context; never under the state lock.
            if (Interlocked.Exchange(ref _guestStartJournaled, 1) == 0)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("launch", "guestStartedDuringShaderLoad", detail:
                    $"a guest thread executes while the disk shader cache loads, " +
                    $"{System.Diagnostics.Stopwatch.GetElapsedTime(Interlocked.Read(ref _guestReleaseTimestamp)).TotalMilliseconds:F0} ms after the loader " +
                    $"released the guest; registered memories in the loader's snapshot {Volatile.Read(ref _shaderLoadMemories)}; " +
                    "GPU commands wait in the GPFIFO until the load ends (adapt_guest_start_during_shader_load)");
            }

            return true;
        }

        // RewindBox (adapt_guest_start_during_shader_load): by the loader, once it holds its snapshot. A cancellation
        // already requested keeps the guest waiting for the terminal state, which then answers false.
        private void ReleaseGuestForShaderLoad(int physicalMemories)
        {
            lock (_gpuInitializationLock)
            {
                if (_gpuInitializationCancellationRequested)
                {
                    return;
                }

                Volatile.Write(ref _shaderLoadMemories, physicalMemories);
                Interlocked.Exchange(ref _guestReleaseTimestamp, System.Diagnostics.Stopwatch.GetTimestamp());
                _guestStartEvent.Set();
            }
        }

        // RewindBox (adapt_guest_start_during_shader_load): returns once no shader cache loader runs. The loader publishes
        // its terminal event after it has unwound and joined its workers; it never waits for the caller's thread. Not
        // for the GPU thread, which is the loader's.
        private void WaitForShaderCacheLoader()
        {
            bool loading;

            lock (_gpuInitializationLock)
            {
                loading = _gpuInitializationState == GpuInitializationState.Initializing;
            }

            if (loading)
            {
                _gpuReadyEvent.WaitOne();
            }
        }

        // RewindBox (adapt_guest_start_during_shader_load): for SynchronizationManager's infinite waits. Running while a
        // loader runs and no cancellation was requested: the guest may execute and the GPU thread processes nothing yet.
        internal SynchronizationManager.ShaderLoadPhase GetShaderLoadPhase()
        {
            lock (_gpuInitializationLock)
            {
                if (_gpuInitializationState == GpuInitializationState.Ready)
                {
                    return SynchronizationManager.ShaderLoadPhase.Ready;
                }

                return _gpuInitializationState == GpuInitializationState.Initializing && !_gpuInitializationCancellationRequested
                    ? SynchronizationManager.ShaderLoadPhase.Running
                    : SynchronizationManager.ShaderLoadPhase.None;
            }
        }
'''),
    ('''        public void Dispose()
        {
            foreach (var cache in _counterReportCaches) cache.CancelPendingReports();
''', '''        public void Dispose()
        {
            // RewindBox (adapt_guest_start_during_shader_load): the guest's threads no longer end after the loader, so a
            // release that follows a failed render worker waits for the loader here before any cache or event goes.
            WaitForShaderCacheLoader();

            foreach (var cache in _counterReportCaches) cache.CancelPendingReports();
'''),
    ('''            _gpuReadyEvent.Dispose();
''', '''            _gpuReadyEvent.Dispose();
            _guestStartEvent.Dispose();
'''),
)

SYNC_PAIRS = (
    ('''        private readonly Syncpoint[] _syncpoints;

        public SynchronizationManager()
        {
''', '''        private readonly Syncpoint[] _syncpoints;

        // RewindBox (adapt_guest_start_during_shader_load): the guest executes while the disk shader cache loads, and the
        // GPU thread processes no command until the load has ended. Running: a loader runs and no cancellation was
        // requested. Ready: the load ended and the GPU thread processes commands. None: not started, cancelled or failed.
        internal enum ShaderLoadPhase { None, Running, Ready }

        private const int ShaderLoadWaitSliceMs = 50;
        private readonly Func<ShaderLoadPhase> _shaderLoadPhase;
        private bool _shaderLoadOver;
        private int _shaderLoadWaitJournaled;

        internal SynchronizationManager(Func<ShaderLoadPhase> shaderLoadPhase) : this()
        {
            _shaderLoadPhase = shaderLoadPhase;
        }

        // True only while a loader runs. Once the load has ended ready, one volatile read for the rest of the session.
        private bool ShaderCacheLoading()
        {
            if (_shaderLoadPhase == null || Volatile.Read(ref _shaderLoadOver))
            {
                return false;
            }

            ShaderLoadPhase phase = _shaderLoadPhase();

            if (phase == ShaderLoadPhase.Ready)
            {
                Volatile.Write(ref _shaderLoadOver, true);
            }

            return phase == ShaderLoadPhase.Running;
        }

        // The wait of an infinite WaitOnSyncpoint issued while the cache loads: in slices, until the fence is signalled
        // or the load has ended. False when it ended cancelled or failed (the guest is being stopped).
        private bool WaitWhileShaderCacheLoads(uint id, uint threshold, ManualResetEvent waitEvent)
        {
            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            ShaderLoadPhase phase = ShaderLoadPhase.Running;

            while (phase == ShaderLoadPhase.Running && !waitEvent.WaitOne(ShaderLoadWaitSliceMs))
            {
                phase = _shaderLoadPhase();
            }

            double milliseconds = System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds;

            // The first wait the former 1 s would have ended as "reached" before the GPU thread processed anything.
            if (milliseconds >= 1000 && Interlocked.Exchange(ref _shaderLoadWaitJournaled, 1) == 0)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("launch", "syncpointWaitHeldForShaderLoad", detail:
                    $"wait on syncpoint {id} for threshold {threshold} held {milliseconds:F0} ms while the disk shader cache loaded " +
                    $"(value {_syncpoints[id].Value}, load {(phase == ShaderLoadPhase.Running ? "running: signalled" : phase == ShaderLoadPhase.Ready ? "ended ready" : "cancelled or failed")}); " +
                    "the former 1 s would have reported it reached (adapt_guest_start_during_shader_load, logged once)");
            }

            return phase != ShaderLoadPhase.None;
        }

        public SynchronizationManager()
        {
'''),
    ('''            if (timeout == Timeout.InfiniteTimeSpan)
            {
                timeout = TimeSpan.FromSeconds(1);
            }

            using ManualResetEvent waitEvent = new(false);
            SyncpointWaiterHandle info = _syncpoints[id].RegisterCallback(threshold, _ => waitEvent.Set());

            if (info == null)
            {
                return false;
            }

            bool signaled = waitEvent.WaitOne(timeout);
''', '''            // RewindBox (adapt_guest_start_during_shader_load): an infinite wait issued while the shader cache loads.
            bool duringShaderLoad = false;

            if (timeout == Timeout.InfiniteTimeSpan)
            {
                timeout = TimeSpan.FromSeconds(1);
                duringShaderLoad = ShaderCacheLoading();
            }

            using ManualResetEvent waitEvent = new(false);
            SyncpointWaiterHandle info = _syncpoints[id].RegisterCallback(threshold, _ => waitEvent.Set());

            if (info == null)
            {
                return false;
            }

            // RewindBox (adapt_guest_start_during_shader_load): the GPU thread has processed nothing yet, and the 1 s above
            // would let the caller tell the guest that a fence was reached before any of its commands ran. The wait lasts
            // until the fence is signalled or the load has ended: ready, the wait below then lasts its usual time from that
            // moment; cancelled or failed, the guest is being stopped and the wait ends at once, unsignalled.
            if (duringShaderLoad && !WaitWhileShaderCacheLoads(id, threshold, waitEvent))
            {
                _syncpoints[id].UnregisterCallback(info);

                return !waitEvent.WaitOne(0);
            }

            bool signaled = waitEvent.WaitOne(timeout);
'''),
    ('''                long gpu = gpuProgress(), renderer = rendererProgress();

                while (true)
                {
                    if (cancelled())
                    {
                        outcome = ProgressWaitOutcome.Cancelled;
                        break;
                    }
''', '''                long gpu = gpuProgress(), renderer = rendererProgress();
                // RewindBox (adapt_guest_start_during_shader_load): while the shader cache loads the GPU thread has not started
                // processing. It is neither idle nor wedged: no fallback and no cap count that time.
                bool shaderLoad = ShaderCacheLoading();
                long capStart = start;

                while (true)
                {
                    if (cancelled())
                    {
                        outcome = ProgressWaitOutcome.Cancelled;
                        break;
                    }

                    if (shaderLoad)
                    {
                        ShaderLoadPhase phase = _shaderLoadPhase();

                        if (phase == ShaderLoadPhase.None)
                        {
                            // Cancelled or failed: the guest is being stopped.
                            outcome = ProgressWaitOutcome.Cancelled;
                            break;
                        }

                        if (phase == ShaderLoadPhase.Ready)
                        {
                            // The load has ended: the wait goes on as one issued at this moment.
                            shaderLoad = false;
                            sliceStart = lastProgress = capStart = System.Diagnostics.Stopwatch.GetTimestamp();
                            value = _syncpoints[id].Value;
                            gpu = gpuProgress();
                            renderer = rendererProgress();
                        }
                    }
'''),
    ('''                    if (System.Diagnostics.Stopwatch.GetElapsedTime(start) >= totalCap)
                    {
''', '''                    if (shaderLoad)
                    {
                        continue; // RewindBox (adapt_guest_start_during_shader_load): loading is progress pending
                    }

                    if (System.Diagnostics.Stopwatch.GetElapsedTime(capStart) >= totalCap)
                    {
'''),
)

PROCESS_PAIRS = (
    ('''            // We must wait until shader cache is loaded, among other things, before executing CPU code.
            if (!_gpuContext.WaitUntilGpuReady())
''', '''            // RewindBox (adapt_guest_start_during_shader_load): the guest executes once the shader cache loader has
            // started, while it loads; the GPU thread processes the guest's commands only after the load. A cancelled
            // or failed GPU initialization still ends the thread here.
            if (!_gpuContext.WaitUntilGuestMayStart())
'''),
)

FILE_PAIRS = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': GPU_PAIRS,
    'src/Ryujinx.Graphics.Gpu/Synchronization/SynchronizationManager.cs': SYNC_PAIRS,
    'src/Ryujinx.HLE/HOS/ArmProcessContext.cs': PROCESS_PAIRS,
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
