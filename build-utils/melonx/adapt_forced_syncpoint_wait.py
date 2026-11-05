"""Keep the forced CPU-side syncpoint wait waiting while the GPU makes progress (Hogwarts policy).

IPA 658, 5 November 2026, Hogwarts Legacy, pid 11152 (private logs, not in the repository; counts and times only): 71
"ServiceNv Wait: GPU processing thread is too slow, waiting on CPU..." warnings, 14 of them followed 1.000-1.006 s
later by "Wait on syncpoint 1 for threshold N took more than 1000ms, resuming execution..." (03:13:00.513 -> 01.515,
03:13:03.896 -> 04.896, ... 03:19:55.874 -> 56.879). All 14 fall inside first-encounter pipeline build bursts, while
the GPU thread waits for the render thread (synchronous render call in flight 1.2-8.2 s, graphicsPipelineBuild 8-31 s
of wall time per 5 s window); 8 of them fall inside the 34 s present freeze at 03:13:01-03:13:34. The error is logged
by the nvdrv server thread "{Nv}", not by the GPU thread.

Mechanism (read in the Core 658 preparation):
- NvHostEvent.Wait (NvHostEvent.cs:139-147): once the guest has cancelled its event wait on the same fence twice
  (FailingCountMax = 2, Cancel at lines 98-127, from EventSignal), the next EventWait blocks the {Nv} thread in
  Fence.Wait(gpuContext, Timeout.InfiniteTimeSpan), discards its result and returns false.
- SynchronizationManager.WaitOnSyncpoint (SynchronizationManager.cs:83-87) turns InfiniteTimeSpan into 1 s ("TODO:
  Remove this when GPU channel scheduling will be implemented"), then logs the error and unregisters (lines 97-106).
- NvHostCtrlDeviceFile.EventWait (lines 399-420): hostEvent.Wait returning false answers the guest Success with
  value = fence.Value. So after 1 s the guest is told the GPU reached a threshold it has not reached: during
  03:13:01-03:13:31 the thresholds advanced by 193 in 29.7 s. Ryujinx reads guest memory (vertex, index, uniform,
  texture data) when the GPU thread processes each draw and writes occlusion reports before their increment, so the
  guest can recycle memory not yet read or read results not yet written: a likely source of one-frame wrong or black
  content (not proven: no recording of pid 11152).
- Syncpoint 1 moves only when the GPU thread processes its increments (GPFifoClass.Syncpointb, the 3D engine's
  SyncpointAction, the Hogwarts queued-syncpoint FIFO of adapt_queued_syncpoints). Every nvdrv ioctl, GPFIFO submits
  included, is served by the same {Nv} thread (Horizon.cs:258, INvDrvServices.cs:66): while this wait blocks it, no
  new GPU work can be submitted, so the work that can still advance the syncpoint is finite.

Change (Hogwarts Legacy only: GraphicsConfig.ProgressAwareForcedSyncpointWait, assigned by the Library for every
session from the launched title; off, the forced path is today's):
- SynchronizationManager.WaitOnSyncpointWhileProgressing: registers once and waits in 1 s slices (polling the guest's
  termination every 50 ms). At each slice end it reports progress when the syncpoint value or the GPU thread's
  command buffers advanced; otherwise, when the GPU side is idle (GPFIFO empty, no dispatch in flight, no queued
  syncpoint increment), nothing can advance the syncpoint without a new guest submission: it gives up as today after
  that slice (the same 1 s for a wait that never progressed); when the GPU side is busy, a completed threaded-renderer
  command is progress (the GPU thread waiting on a render thread that builds pipelines). It gives up after 10 s
  without any progress or, whatever the progress, after an absolute 30 s cap (the renderer counter moves for every
  completed threaded command); the cap is counted and journaled once. A slice end that finds the syncpoint at or past
  the threshold reports Reached with the true value even if the callback did not run (a wedged renderer; the longest pipeline build in flight in the logs is 3.2 s). The guest's
  termination ({Nv} thread's KThread.TerminationRequested, set by Horizon.Dispose before it spins on the server
  threads) ends it within 50 ms. The waiter is a monitor, not a disposed event, so a callback racing the end of the
  wait cannot hit a disposed handle. Counters (forced waits, slices, false completions avoided, fallbacks with the GPU
  idle, fallbacks without progress, waits ended by termination, longest wait) go to one bounded Info line, logged after
  each wait that outlived a slice or did not reach its fence (at most 64 per session) and every 256 forced waits; the
  first fallback of each kind is journaled once.
- GpuContext: the progress the wait reads (ForcedWaitGpuProgress, ForcedWaitRendererProgress, ForcedWaitGpuIdle);
  GPFifoDevice counts the command buffers it starts and marks DispatchCalls in flight; ThreadedRenderer counts the
  commands it completes (CompletedCommands, one field increment per command).
- NvHostEvent.Wait's forced path calls it under the policy. Its result is still false (Success with fence.Value):
  that answer is now true unless the wait gave up.

Not changed: GPU-side waits (GPFifoClass Syncpointb, Host1x, AndroidFence) keep WaitOnSyncpoint and its 1 s cap; the
event path before two cancels; the forced path for every other title; no draw, effect or synchronisation is removed.
The {Nv} thread stays blocked longer during a build burst (other nvdrv ioctls wait behind it, as they already do for
1 s per forced wait). Not measured on an iPhone.
Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

SYNCHRONIZATION = 'src/Ryujinx.Graphics.Gpu/Synchronization/SynchronizationManager.cs'
GPU_CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
GPFIFO_DEVICE = 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoDevice.cs'
THREADED_RENDERER = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
HOST_EVENT = 'src/Ryujinx.HLE/HOS/Services/Nv/NvDrvServices/NvHostCtrl/Types/NvHostEvent.cs'
GRAPHICS_CONFIG = 'src/Ryujinx.Graphics.Gpu/GraphicsConfig.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'

BASELINE = {
    SYNCHRONIZATION: '16993b4ce936012a516d29a2e2c73c319d2cb6ab523669e1cfa345328d95af0a',
    GPU_CONTEXT: '7f631c57ccb95243686e422361c0b4dcd04f2b77da6ad99fbe33f20819d7dfec',
    GPFIFO_DEVICE: 'd5a51e8b7ba834373ae08398624c7bd1ec6e677cfa512cfe31b32697bc5577bd',
    THREADED_RENDERER: 'e8591623a4baad5ddfd78ac9842869330e68fe3800442ae566bc2dadf94a682c',
    HOST_EVENT: '9ff868b0dc69d43111bec66e8555d6db52166f6465ef62225208a6a2478c3540',
    GRAPHICS_CONFIG: 'e9307f4cd474249b74a1e183439aa669b809d865b17974c8898911b48251316d',
    LIBRARY: 'ef4533888583df2775e47be7d736229bca45727f3183820daec08194a256a6ad',
}

WAIT_END = '''            return !signaled;
        }
'''
PROGRESS_WAIT = '''
        // RewindBox (adapt_forced_syncpoint_wait): the CPU-side wait NvHostEvent forces after the guest cancelled the same
        // fence twice (Hogwarts policy). WaitOnSyncpoint gives up after 1 s and its caller then tells the guest the fence
        // was reached; this one waits in slices while the GPU makes progress toward it and gives up, as before, only when
        // the GPU side is idle after a slice without progress or has made no progress at all for the limit (wedged).
        // The caller's cancellation (guest termination) ends it within ProgressWaitPollMs. GPU-side waits keep the above.
        public enum ProgressWaitOutcome { Reached, Idle, NoProgress, Capped, Cancelled }

        public static readonly TimeSpan ProgressWaitSlice = TimeSpan.FromSeconds(1);
        public static readonly TimeSpan ProgressWaitNoProgressLimit = TimeSpan.FromSeconds(10);
        // Absolute cap: the renderer's counter moves for every completed threaded command, so progress alone could keep it waiting.
        public static readonly TimeSpan ProgressWaitTotalCap = TimeSpan.FromSeconds(30);
        private const int ProgressWaitPollMs = 50;
        private const int ProgressWaitLineBudget = 64;

        private readonly object _forcedWaitGate = new();
        private long _forcedWaits, _forcedWaitSlices, _falseCompletionsAvoided, _idleFallbacks, _noProgressFallbacks, _cappedFallbacks, _cancelledForcedWaits;
        private double _longestForcedWaitMs;
        private int _forcedWaitLines;
        private bool _idleFallbackJournaled, _noProgressFallbackJournaled, _cappedFallbackJournaled;

        // A monitor rather than an event: a callback that races the end of the wait never touches a disposed handle.
        private sealed class ProgressWaiter
        {
            private readonly object _gate = new();
            private bool _signaled;

            public void Signal(SyncpointWaiterHandle _)
            {
                lock (_gate)
                {
                    _signaled = true;
                    Monitor.PulseAll(_gate);
                }
            }

            public bool Wait(int milliseconds)
            {
                lock (_gate)
                {
                    if (!_signaled && milliseconds > 0)
                    {
                        Monitor.Wait(_gate, milliseconds);
                    }

                    return _signaled;
                }
            }
        }

        public ProgressWaitOutcome WaitOnSyncpointWhileProgressing(uint id, uint threshold, Func<long> gpuProgress,
            Func<long> rendererProgress, Func<bool> gpuIdle, Func<bool> cancelled)
        {
            return WaitOnSyncpointWhileProgressing(id, threshold, ProgressWaitSlice, ProgressWaitNoProgressLimit, gpuProgress,
                rendererProgress, gpuIdle, cancelled);
        }

        public ProgressWaitOutcome WaitOnSyncpointWhileProgressing(uint id, uint threshold, TimeSpan slice, TimeSpan noProgressLimit,
            Func<long> gpuProgress, Func<long> rendererProgress, Func<bool> gpuIdle, Func<bool> cancelled)
        {
            return WaitOnSyncpointWhileProgressing(id, threshold, slice, noProgressLimit, ProgressWaitTotalCap, gpuProgress,
                rendererProgress, gpuIdle, cancelled);
        }

        public ProgressWaitOutcome WaitOnSyncpointWhileProgressing(uint id, uint threshold, TimeSpan slice, TimeSpan noProgressLimit,
            TimeSpan totalCap, Func<long> gpuProgress, Func<long> rendererProgress, Func<bool> gpuIdle, Func<bool> cancelled)
        {
            ArgumentOutOfRangeException.ThrowIfGreaterThanOrEqual(id, (uint)MaxHardwareSyncpoints);

            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            ProgressWaiter waiter = new();
            SyncpointWaiterHandle info = _syncpoints[id].RegisterCallback(threshold, waiter.Signal);
            ProgressWaitOutcome outcome = ProgressWaitOutcome.Reached;
            int slices = 0;
            bool unregister = false;
            uint value = _syncpoints[id].Value;

            if (info != null)
            {
                long sliceStart = start, lastProgress = start;
                long gpu = gpuProgress(), renderer = rendererProgress();

                while (true)
                {
                    if (cancelled())
                    {
                        outcome = ProgressWaitOutcome.Cancelled;
                        break;
                    }

                    double left = slice.TotalMilliseconds - System.Diagnostics.Stopwatch.GetElapsedTime(sliceStart).TotalMilliseconds;

                    if (waiter.Wait((int)Math.Clamp(Math.Ceiling(left), 0, ProgressWaitPollMs)))
                    {
                        break;
                    }

                    if (System.Diagnostics.Stopwatch.GetElapsedTime(sliceStart) < slice)
                    {
                        continue;
                    }

                    slices++;
                    sliceStart = System.Diagnostics.Stopwatch.GetTimestamp();

                    uint nowValue = _syncpoints[id].Value;

                    // Reached without the callback having run yet (or at all): report it with its true value.
                    if (nowValue >= threshold)
                    {
                        outcome = ProgressWaitOutcome.Reached;
                        unregister = true;
                        break;
                    }

                    if (System.Diagnostics.Stopwatch.GetElapsedTime(start) >= totalCap)
                    {
                        outcome = ProgressWaitOutcome.Capped;
                        break;
                    }

                    long nowGpu = gpuProgress(), nowRenderer = rendererProgress();
                    bool progressed;

                    if (nowValue != value || nowGpu != gpu)
                    {
                        progressed = true;
                    }
                    else if (gpuIdle())
                    {
                        // Nothing on the GPU side can advance the syncpoint without a new guest submission.
                        outcome = ProgressWaitOutcome.Idle;
                        break;
                    }
                    else
                    {
                        // The GPU thread is busy, for example waiting on a render thread that builds pipelines.
                        progressed = nowRenderer != renderer;
                    }

                    value = nowValue;
                    gpu = nowGpu;
                    renderer = nowRenderer;

                    if (progressed)
                    {
                        lastProgress = sliceStart;
                    }
                    else if (System.Diagnostics.Stopwatch.GetElapsedTime(lastProgress, sliceStart) >= noProgressLimit)
                    {
                        outcome = ProgressWaitOutcome.NoProgress;
                        break;
                    }
                }

                if (outcome != ProgressWaitOutcome.Reached || unregister)
                {
                    _syncpoints[id].UnregisterCallback(info);

                    // Reached while giving up: the increment publishes the value before it runs the callbacks.
                    if (waiter.Wait(0) || _syncpoints[id].Value >= threshold)
                    {
                        outcome = ProgressWaitOutcome.Reached;
                    }
                }

                value = _syncpoints[id].Value;
            }

            NoteForcedWait(id, threshold, value, outcome, slices, System.Diagnostics.Stopwatch.GetElapsedTime(start).TotalMilliseconds,
                noProgressLimit, totalCap);

            return outcome;
        }

        private void NoteForcedWait(uint id, uint threshold, uint value, ProgressWaitOutcome outcome, int slices, double milliseconds,
            TimeSpan noProgressLimit, TimeSpan totalCap)
        {
            string journal = null, line = null;

            lock (_forcedWaitGate)
            {
                _forcedWaits++;
                _forcedWaitSlices += slices;
                _longestForcedWaitMs = Math.Max(_longestForcedWaitMs, milliseconds);

                switch (outcome)
                {
                    case ProgressWaitOutcome.Reached:
                        // The 1 s wait would have told the guest that this fence was reached before it was.
                        if (slices > 0)
                        {
                            _falseCompletionsAvoided++;
                        }
                        break;
                    case ProgressWaitOutcome.Idle:
                        _idleFallbacks++;
                        if (!_idleFallbackJournaled)
                        {
                            _idleFallbackJournaled = true;
                            journal = $"Forced wait on syncpoint {id} for threshold {threshold}: value {value}, GPU idle with nothing queued " +
                                $"after {milliseconds:F0} ms; resuming execution as before (adapt_forced_syncpoint_wait, logged once)";
                        }
                        break;
                    case ProgressWaitOutcome.NoProgress:
                        _noProgressFallbacks++;
                        if (!_noProgressFallbackJournaled)
                        {
                            _noProgressFallbackJournaled = true;
                            journal = $"Forced wait on syncpoint {id} for threshold {threshold}: value {value}, no GPU progress for " +
                                $"{noProgressLimit.TotalMilliseconds:F0} ms after {milliseconds:F0} ms; resuming execution as before " +
                                "(adapt_forced_syncpoint_wait, logged once)";
                        }
                        break;
                    case ProgressWaitOutcome.Capped:
                        _cappedFallbacks++;
                        if (!_cappedFallbackJournaled)
                        {
                            _cappedFallbackJournaled = true;
                            journal = $"Forced wait on syncpoint {id} for threshold {threshold}: value {value}, not reached within the " +
                                $"{totalCap.TotalMilliseconds:F0} ms cap after {milliseconds:F0} ms; resuming execution as before " +
                                "(adapt_forced_syncpoint_wait, logged once)";
                        }
                        break;
                    case ProgressWaitOutcome.Cancelled:
                        _cancelledForcedWaits++;
                        break;
                }

                bool notable = outcome != ProgressWaitOutcome.Reached || slices > 0;

                if ((notable && _forcedWaitLines < ProgressWaitLineBudget) || (_forcedWaits & 255) == 0)
                {
                    if (notable && _forcedWaitLines < ProgressWaitLineBudget)
                    {
                        _forcedWaitLines++;
                    }

                    line = $"Forced syncpoint waits (adapt_forced_syncpoint_wait): {_forcedWaits} forced, {_forcedWaitSlices} slices, " +
                        $"{_falseCompletionsAvoided} false completions avoided, {_idleFallbacks} fallbacks with the GPU idle, " +
                        $"{_noProgressFallbacks} without progress, {_cancelledForcedWaits} ended by termination, {_cappedFallbacks} at the cap; " +
                        $"longest {_longestForcedWaitMs:F0} ms; last: syncpoint {id} threshold {threshold} value {value} {outcome} " +
                        $"after {milliseconds:F0} ms";
                }
            }

            if (journal != null)
            {
                Logger.Warning?.Print(LogClass.Gpu, journal);
            }

            if (line != null)
            {
                Logger.Info?.Print(LogClass.Gpu, line);
            }
        }
'''

GPU_CONTEXT_OLD = '''        public SynchronizationManager Synchronization { get; }
'''
GPU_CONTEXT_NEW = GPU_CONTEXT_OLD + '''
        // RewindBox (adapt_forced_syncpoint_wait): what the forced CPU-side syncpoint wait (NvHostEvent, Hogwarts policy)
        // reads to tell a GPU working toward the fence from one that cannot advance it any more.
        private long _commandBuffersStarted;
        private int _dispatching;

        internal void NoteCommandBufferStarted() => Interlocked.Increment(ref _commandBuffersStarted);

        internal void NoteDispatching(bool dispatching) => Volatile.Write(ref _dispatching, dispatching ? 1 : 0);

        /// <summary>GPFIFO command buffers the GPU thread has started.</summary>
        public long ForcedWaitGpuProgress => Interlocked.Read(ref _commandBuffersStarted);

        /// <summary>Commands the threaded renderer has completed (0 when the backend is not threaded).</summary>
        public long ForcedWaitRendererProgress => Renderer is Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer threaded ? threaded.CompletedCommands : 0;

        /// <summary>
        /// Nothing on the GPU side could advance a syncpoint without a new guest submission: the GPFIFO is empty, no
        /// dispatch is in flight and no increment is queued behind its reports. Read in this order (the GPU thread marks
        /// a dispatch before it dequeues).
        /// </summary>
        public bool ForcedWaitGpuIdle => !GPFifo.HasCommandBuffers && Volatile.Read(ref _dispatching) == 0 && !HasQueuedSyncpoints;
'''

FIFO_SIGNAL_OLD = '''        public void SignalNewEntries()
        {
            _event.Set();
        }
'''
FIFO_SIGNAL_NEW = FIFO_SIGNAL_OLD + '''
        // RewindBox (adapt_forced_syncpoint_wait): command buffers not yet taken by the GPU thread.
        internal bool HasCommandBuffers => !_commandBufferQueue.IsEmpty;
'''
DISPATCH_OLD = '''        public void DispatchCalls()
        {
            using var dispatchMeasurement = PD.Measure(PD.Phase.GpuDispatch);
'''
DISPATCH_NEW = '''        public void DispatchCalls()
        {
            // RewindBox (adapt_forced_syncpoint_wait): a dispatch in flight, marked before any command buffer is dequeued and
            // cleared even when Process throws and the loop survives.
            _context.NoteDispatching(true);

            try
            {
                DispatchCallsCore();
            }
            finally
            {
                _context.NoteDispatching(false);
            }
        }

        private void DispatchCallsCore()
        {
            using var dispatchMeasurement = PD.Measure(PD.Phase.GpuDispatch);
'''
ENTRY_OLD = '''            while (_ibEnable && !_interrupt && _commandBufferQueue.TryDequeue(out CommandBuffer entry))
            {
'''
ENTRY_NEW = ENTRY_OLD + '''                _context.NoteCommandBufferStarted();

'''

RENDERER_FIELD_OLD = '''        public uint ProgramCount { get; set; } = 0;
'''
RENDERER_FIELD_NEW = RENDERER_FIELD_OLD + '''
        // RewindBox (adapt_forced_syncpoint_wait): commands the render thread has completed, read by the forced CPU-side
        // syncpoint wait as progress while the GPU thread waits on the render thread.
        private long _completedCommands;
        public long CompletedCommands => Volatile.Read(ref _completedCommands);
'''
RENDERER_LOOP_OLD = '''                    _consumerPtr = (_consumerPtr + 1) % QueueCount;
'''
RENDERER_LOOP_NEW = RENDERER_LOOP_OLD + '''                    Volatile.Write(ref _completedCommands, _completedCommands + 1);
'''

HOST_EVENT_OLD = '''                    Fence.Wait(gpuContext, Timeout.InfiniteTimeSpan);
'''
HOST_EVENT_NEW = '''                    // RewindBox (adapt_forced_syncpoint_wait): Hogwarts policy, the wait goes on while the GPU makes progress
                    // toward the fence, so the Success below is true unless it gave up (GPU idle or wedged, or termination).
                    if (GraphicsConfig.ProgressAwareForcedSyncpointWait && Fence.IsValid())
                    {
                        KThread serverThread = KernelStatic.GetCurrentThread();

                        gpuContext.Synchronization.WaitOnSyncpointWhileProgressing(Fence.Id, Fence.Value,
                            () => gpuContext.ForcedWaitGpuProgress, () => gpuContext.ForcedWaitRendererProgress,
                            () => gpuContext.ForcedWaitGpuIdle, () => serverThread != null && serverThread.TerminationRequested);
                    }
                    else
                    {
                        Fence.Wait(gpuContext, Timeout.InfiniteTimeSpan);
                    }
'''

CONFIG_OLD = '''        public static bool HogwartsDmaRegionUpload { get; set; }
'''
CONFIG_NEW = CONFIG_OLD + '''
        /// <summary>
        /// RewindBox (adapt_forced_syncpoint_wait): the CPU-side syncpoint wait nvservices forces after the guest cancelled
        /// the same fence twice waits while the GPU makes progress toward it instead of giving up after 1 s.
        /// Set per session from the launched title (Hogwarts Legacy only).
        /// </summary>
        public static bool ProgressAwareForcedSyncpointWait { get; set; }
'''

LIBRARY_OLD = '''            Ryujinx.Graphics.Gpu.GraphicsConfig.HogwartsDmaRegionUpload = hogwarts;
'''
LIBRARY_NEW = LIBRARY_OLD + '''            // RewindBox (adapt_forced_syncpoint_wait): the forced CPU-side syncpoint wait goes on while the GPU progresses.
            Ryujinx.Graphics.Gpu.GraphicsConfig.ProgressAwareForcedSyncpointWait = hogwarts;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths[SYNCHRONIZATION], WAIT_END, WAIT_END + PROGRESS_WAIT)
    once(paths[GPU_CONTEXT], GPU_CONTEXT_OLD, GPU_CONTEXT_NEW)
    once(paths[GPFIFO_DEVICE], FIFO_SIGNAL_OLD, FIFO_SIGNAL_NEW)
    once(paths[GPFIFO_DEVICE], DISPATCH_OLD, DISPATCH_NEW)
    once(paths[GPFIFO_DEVICE], ENTRY_OLD, ENTRY_NEW)
    once(paths[THREADED_RENDERER], RENDERER_FIELD_OLD, RENDERER_FIELD_NEW)
    once(paths[THREADED_RENDERER], RENDERER_LOOP_OLD, RENDERER_LOOP_NEW)
    once(paths[HOST_EVENT], HOST_EVENT_OLD, HOST_EVENT_NEW)
    once(paths[GRAPHICS_CONFIG], CONFIG_OLD, CONFIG_NEW)
    once(paths[LIBRARY], LIBRARY_OLD, LIBRARY_NEW)
    return [paths[name] for name in BASELINE]
