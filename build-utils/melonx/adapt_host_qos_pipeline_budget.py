"""Raise the threads that pace a frame, and keep large games' pipeline caches (every title).

Build 620 journals, iPhone 16 Pro (A18 Pro: two performance cores of six), 2 November 2026:

- Hogwarts Legacy (PID 66809, 13-16 FPS): the render thread, NeoStation.MeloNX.Render, is the
  busiest thread (55-65 % CPU, busy 96 % of each 5.1 s window), and GPU.MainThread paces the GPU
  commands. Both run at priority 31 (default QoS): .NET starts its threads without a QoS class.
  The guest's and the system's GCD work above them runs at 37-47, so the scheduler may keep the
  two threads off the performance cores.
- Super Smash Bros. Ultimate (PID 67058, 57.6 FPS, p50/p95/p99 17 ms): 143 pauses over 50 ms
  and 80 over 100 ms (up to 3.75 s), each in a window of pipeline builds of 120-320 ms each.
  During them the GPU thread waits for the render thread (up to 2.5 s per window), and the guest
  for the GPU ("ServiceNv Wait"). A draw waits for its demanded pipeline compile; the demand
  thread runs at the default QoS, and so does the Metal compilation it requests. The main
  pipeline cache loaded 383.81 MiB of its 384 MiB budget and "will not be persisted until it
  fits". A full main cache cannot take a worker cache either: the worker 0 cache was recycled
  six times in 10 s at its 64 MiB budget. So nothing a session compiles is kept, and the same
  pipelines are converted again, in game, every session.

Changes, for every title:
- ThreadedRenderer.RunLoop raises the render thread (its caller) and the GPU command thread it
  starts to user-interactive QoS (pthread_set_qos_class_self_np), on Apple platforms only.
  Elsewhere, or if the call is unavailable, nothing changes.
- The demand thread of BackgroundCompilationScheduler, which compiles what a draw waits for,
  raises itself the same way. The background workers keep their QoS.
- The pipeline cache budget is 1 GiB (main 768 MiB, 128 MiB per worker), 512 MiB before;
  everything else in its policy is unchanged. MoltenVK keeps that data LZ4-compressed in memory.
  Hogwarts Legacy's cache is 104 MiB and does not grow from this change.

- ThreadedRenderer times each command it runs by type and logs, every 5 s of rendering, the 8 command
  types with the most time (calls and milliseconds) to the core log: once the read-backs no longer
  stall it, the render thread's own work is the next limit, and these lines tell which commands that
  work is made of.
- The Vulkan backend times, on the render thread, what a draw's preparation is made of (pipeline lookups,
  barriers, descriptor updates, auto-flushes), the render passes it begins (and how many begin again on
  the framebuffer the last one ended on), the command buffer submissions, the buffer fence waits (the
  render thread's own, before a direct buffer write or for a read, and those of other threads, such as a
  guest thread reading a deferred read-back) and the presentation (swapchain image acquisition and queue
  present). It logs them every 5 s of presentation to the core log.
- MoltenVK's own performance tracking is on and logs its statistics every 300 presented frames to stderr:
  Metal encoding of each command buffer on MoltenVK's submission thread, GPU execution of each Metal
  command buffer, drawable waits and frame intervals. Together they tell whether a frame waits for the
  render thread, for MoltenVK's encoding or for the GPU.

Not measured on the iPhone; no FPS claim. Fail closed on drift.
"""
from pathlib import Path

from adapt_session import once

THREADED = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
PIPELINE_CACHE = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
SCHEDULER = 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs'
PIPELINE_BASE = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
PIPELINE_FULL = 'src/Ryujinx.Graphics.Vulkan/PipelineFull.cs'
WINDOW = 'src/Ryujinx.Graphics.Vulkan/Window.cs'
MVK_INITIALIZATION = 'src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs'
BUFFER_HOLDER = 'src/Ryujinx.Graphics.Vulkan/BufferHolder.cs'
NAMES = [THREADED, PIPELINE_CACHE, SCHEDULER, PIPELINE_BASE, PIPELINE_FULL, WINDOW, MVK_INITIALIZATION, BUFFER_HOLDER]

THREADED_NAMESPACE_OLD = '''    /// <summary>
    /// The ThreadedRenderer is a layer'''
THREADED_NAMESPACE_NEW = '''    /// <summary>
    /// Apple platforms: the render thread and the GPU command thread pace every frame, and .NET starts them at the default
    /// QoS, below the guest's and the system's user-interactive work, so the scheduler may keep them off the performance
    /// cores. They raise themselves to user-interactive QoS. Elsewhere, or if the call is unavailable, nothing changes.
    /// </summary>
    public static partial class HostThreadQos
    {
        private const uint UserInteractive = 0x21;
        private static int _failureNoted;

        [LibraryImport("/usr/lib/libSystem.B.dylib", EntryPoint = "pthread_set_qos_class_self_np")]
        private static partial int SetQosClassSelf(uint qosClass, int relativePriority);

        public static void RaiseCurrentThread()
        {
            if (!OperatingSystem.IsIOS() && !OperatingSystem.IsMacOS() && !OperatingSystem.IsMacCatalyst())
            {
                return;
            }

            try
            {
                int result = SetQosClassSelf(UserInteractive, 0);

                // The thread keeps its QoS when the call fails (EPERM after pthread_setschedparam): logged once.
                if (result != 0 && Interlocked.Exchange(ref _failureNoted, 1) == 0)
                {
                    Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu,
                        $"Host thread QoS: pthread_set_qos_class_self_np returned {result} on {Thread.CurrentThread.Name}");
                }
            }
            catch (DllNotFoundException)
            {
            }
            catch (EntryPointNotFoundException)
            {
            }
        }
    }

    /// <summary>
    /// The ThreadedRenderer is a layer'''
THREADED_OLD = '''            _backendThread = Thread.CurrentThread;

            _gpuThread = new Thread(() =>
            {
                try { gpuLoop(); }'''
THREADED_NEW = '''            _backendThread = Thread.CurrentThread;
            HostThreadQos.RaiseCurrentThread();

            _gpuThread = new Thread(() =>
            {
                HostThreadQos.RaiseCurrentThread();
                try { gpuLoop(); }'''

RENDER_WORK_OLD = '''                    ThrowIfFailed();

                    CommandHelper.RunCommand(command, this, _baseRenderer);

                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)'''
RENDER_WORK_NEW = '''                    ThrowIfFailed();

                    // Render-thread time per command type (NoteRenderCommand, logged every 5 s): after the read-backs, the
                    // render thread's own work is the next limit, and this tells which commands it is made of.
                    byte commandType = command[^1];
                    long commandStart = Stopwatch.GetTimestamp();
                    CommandHelper.RunCommand(command, this, _baseRenderer);
                    NoteRenderCommand(commandType, commandStart);

                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)'''

RENDER_STATE_OLD = '''        public void RenderLoop()
        {'''
RENDER_STATE_NEW = '''        // Render-thread time per queued command type over each 5 s of rendering. The 8 types with the most time are logged
        // with their calls and milliseconds, then the window starts again (render thread only, no lock).
        private readonly long[] _renderWorkTicks = new long[256];
        private readonly long[] _renderWorkCalls = new long[256];
        private long _renderWorkStart;

        private void NoteRenderCommand(byte type, long start)
        {
            long end = Stopwatch.GetTimestamp();
            _renderWorkTicks[type] += end - start;
            _renderWorkCalls[type]++;

            if (_renderWorkStart == 0)
            {
                _renderWorkStart = start;
            }
            else if (end - _renderWorkStart >= Stopwatch.Frequency * 5)
            {
                LogRenderWork(end);
            }
        }

        private static string RenderMilliseconds(long ticks) =>
            (ticks * 1000.0 / Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);

        private void LogRenderWork(long end)
        {
            long total = 0;

            for (int i = 0; i < _renderWorkTicks.Length; i++)
            {
                total += _renderWorkTicks[i];
            }

            var text = new System.Text.StringBuilder(320);
            text.Append("Render thread commands over ").Append(RenderMilliseconds(end - _renderWorkStart)).Append(" ms: busy ")
                .Append(RenderMilliseconds(total)).Append(" ms; top (calls, ms):");

            for (int rank = 0; rank < 8; rank++)
            {
                int best = -1;

                for (int i = 0; i < _renderWorkTicks.Length; i++)
                {
                    if (_renderWorkTicks[i] > 0 && (best < 0 || _renderWorkTicks[i] > _renderWorkTicks[best]))
                    {
                        best = i;
                    }
                }

                if (best < 0)
                {
                    break;
                }

                text.Append(' ').Append(((CommandType)best).ToString()).Append(' ').Append(_renderWorkCalls[best]).Append(' ')
                    .Append(RenderMilliseconds(_renderWorkTicks[best])).Append(';');
                _renderWorkTicks[best] = 0;
            }

            Array.Clear(_renderWorkTicks);
            Array.Clear(_renderWorkCalls);
            _renderWorkStart = end;
            Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, text.ToString());
        }

''' + RENDER_STATE_OLD

PIPELINE_BUDGET_OLD = '''        private const long TotalCacheBudget = 512L * 1024 * 1024;'''
PIPELINE_BUDGET_NEW = '''        // Super Smash Bros. Ultimate filled the 384 MiB main budget (383.81 MiB loaded in build 620): nothing a session
        // compiled was kept any more, and the same pipelines were converted again in game every session.
        private const long TotalCacheBudget = 1024L * 1024 * 1024;'''

SCHEDULER_OLD = '''            private void WorkerLoop(int workerIndex, bool demandOnly)
            {
                while (true)'''
SCHEDULER_NEW = '''            private void WorkerLoop(int workerIndex, bool demandOnly)
            {
                if (demandOnly)
                {
                    // A draw waits for every demanded compile: this thread, and the Metal compilation it requests, run at
                    // user-interactive QoS on Apple platforms. The background workers keep their QoS.
                    Ryujinx.Graphics.GAL.Multithreading.HostThreadQos.RaiseCurrentThread();
                }

                while (true)'''


# The Vulkan render thread's stages: one shared set of counters, logged with the presentation waits every 5 s.
STAGE_CLASS_OLD = '''    class PipelineBase : IDisposable
    {
        public const int DescriptorSetLayouts = 4;'''
STAGE_CLASS_NEW = '''    /// <summary>
    /// What the render thread's draws and frames are made of: the draw preparation (pipeline lookups, barriers, descriptor
    /// updates, auto-flushes), the render passes begun, the command buffer submissions and the presentation. Logged to the
    /// core log every 5 s of presentation, then counted again. The render thread updates these counters; a helper pass run
    /// on another thread may add to them without a lock (diagnostics only, never read by rendering).
    /// </summary>
    static class RenderStageTimer
    {
        public static long PrepareTicks, Prepares, NotReady;
        public static long PipelineTicks, Pipelines;
        public static long BarrierTicks, DescriptorTicks;
        public static long AutoFlushTicks, AutoFlushes;
        public static long PassTicks, PassBegins, PassResumes;
        public static long SubmitTicks, Submits, QueueTicks;
        public static long WriteWaitTicks, WriteWaits, ReadWaitTicks, ReadWaits;
        private static long _otherWaitTicks, _otherWaits;
        private static long _presentTicks, _presents, _acquireTicks, _queuePresentTicks, _windowStart;

        public static long Now() => System.Diagnostics.Stopwatch.GetTimestamp();

        // A buffer fence wait: the render thread's own (before a direct buffer write, or for a read), or another thread's
        // (a guest thread reading a flushed texture or buffer), counted apart; other threads add atomically.
        public static void NoteFenceWait(bool renderThread, bool write, long start)
        {
            long ticks = Now() - start;

            if (!renderThread)
            {
                System.Threading.Interlocked.Add(ref _otherWaitTicks, ticks);
                System.Threading.Interlocked.Increment(ref _otherWaits);
            }
            else if (write)
            {
                WriteWaitTicks += ticks;
                WriteWaits++;
            }
            else
            {
                ReadWaitTicks += ticks;
                ReadWaits++;
            }
        }

        public static void NotePresent(long start, long acquireStart, long acquired, long queuePresentStart)
        {
            long end = Now();
            _presentTicks += end - start;
            _acquireTicks += acquired - acquireStart;
            _queuePresentTicks += end - queuePresentStart;
            _presents++;

            if (_windowStart == 0)
            {
                _windowStart = start;
            }
            else if (end - _windowStart >= System.Diagnostics.Stopwatch.Frequency * 5)
            {
                Log(end);
            }
        }

        private static string Ms(long ticks) =>
            (ticks * 1000.0 / System.Diagnostics.Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);

        private static void Log(long end)
        {
            long otherWaits = System.Threading.Interlocked.Exchange(ref _otherWaits, 0);
            long otherWaitTicks = System.Threading.Interlocked.Exchange(ref _otherWaitTicks, 0);
            string text = "Vulkan render stages over " + Ms(end - _windowStart) + " ms, " + _presents + " frames: draw prepare " +
                Prepares + " calls " + Ms(PrepareTicks) + " ms (not ready " + NotReady + "; pipelines " + Pipelines + " calls " +
                Ms(PipelineTicks) + " ms, barriers " + Ms(BarrierTicks) + " ms, descriptors " + Ms(DescriptorTicks) +
                " ms, auto-flushes " + AutoFlushes + " calls " + Ms(AutoFlushTicks) + " ms); render passes " + PassBegins +
                " begun " + Ms(PassTicks) + " ms (same framebuffer again " + PassResumes + "); submits " + Submits + " calls " +
                Ms(SubmitTicks) + " ms (queue " + Ms(QueueTicks) + " ms); fence waits on the render thread: buffer writes " +
                WriteWaits + " calls " + Ms(WriteWaitTicks) + " ms, reads " + ReadWaits + " calls " + Ms(ReadWaitTicks) +
                " ms; on other threads " + otherWaits + " calls " + Ms(otherWaitTicks) + " ms; present " + _presents + " calls " +
                Ms(_presentTicks) +
                " ms (acquire " + Ms(_acquireTicks) + " ms, queue present " + Ms(_queuePresentTicks) + " ms)";

            PrepareTicks = Prepares = NotReady = PipelineTicks = Pipelines = BarrierTicks = DescriptorTicks = 0;
            AutoFlushTicks = AutoFlushes = PassTicks = PassBegins = PassResumes = SubmitTicks = Submits = QueueTicks = 0;
            WriteWaitTicks = WriteWaits = ReadWaitTicks = ReadWaits = 0;
            _presentTicks = _presents = _acquireTicks = _queuePresentTicks = 0;
            _windowStart = end;
            Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, text);
        }
    }

    class PipelineBase : IDisposable
    {
        public const int DescriptorSetLayouts = 4;'''

STAGE_FIELD_OLD = '''        private Auto<DisposableFramebuffer> _framebuffer;
        private RenderPassHolder _rpHolder;'''
STAGE_FIELD_NEW = '''        private Auto<DisposableFramebuffer> _framebuffer;
        // The framebuffer the last render pass ended on: a pass begun again on it was split (RenderStageTimer.PassResumes).
        private Auto<DisposableFramebuffer> _lastEndedFramebuffer;
        private RenderPassHolder _rpHolder;'''

PREPARE_OLD = '''        private bool RecreateGraphicsPipelineIfNeeded()
        {
            bool canSkipForBackgroundCompile = CanSkipForBackgroundCompile(allowAsyncSkip: true);'''
PREPARE_NEW = '''        private bool RecreateGraphicsPipelineIfNeeded()
        {
            // Every draw's preparation is timed whole (RenderStageTimer), with its pipeline, barrier, descriptor and
            // auto-flush parts inside it.
            long start = RenderStageTimer.Now();
            bool ready = PrepareGraphicsDraw();
            RenderStageTimer.PrepareTicks += RenderStageTimer.Now() - start;
            RenderStageTimer.Prepares++;

            if (!ready)
            {
                RenderStageTimer.NotReady++;
            }

            return ready;
        }

        private bool PrepareGraphicsDraw()
        {
            bool canSkipForBackgroundCompile = CanSkipForBackgroundCompile(allowAsyncSkip: true);'''

AUTO_FLUSH_OLD = '''            if (AutoFlush.ShouldFlushDraw(DrawCount))
            {
                Gd.FlushAllCommands();
            }'''
AUTO_FLUSH_NEW = '''            if (AutoFlush.ShouldFlushDraw(DrawCount))
            {
                long flushStart = RenderStageTimer.Now();
                Gd.FlushAllCommands();
                RenderStageTimer.AutoFlushTicks += RenderStageTimer.Now() - flushStart;
                RenderStageTimer.AutoFlushes++;
            }'''

DRAW_STATE_OLD = '''            if (UpdateFeedbackLoop() || _graphicsStateDirty || Pbp != PipelineBindPoint.Graphics)
            {
                if (!CreatePipeline(
                    PipelineBindPoint.Graphics,
                    allowAsyncSkip: true,
                    waitForBackgroundGraphicsPipeline: requiresCompletePipeline))
                {
                    return false;
                }

                _graphicsStateDirty = false;
                Pbp = PipelineBindPoint.Graphics;
            }

            Gd.Barriers.Flush(Cbs, _program, _feedbackLoop != 0, RenderPassActive, _rpHolder, EndRenderPassDelegate);

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);'''
DRAW_STATE_NEW = '''            if (UpdateFeedbackLoop() || _graphicsStateDirty || Pbp != PipelineBindPoint.Graphics)
            {
                long pipelineStart = RenderStageTimer.Now();
                bool created = CreatePipeline(
                    PipelineBindPoint.Graphics,
                    allowAsyncSkip: true,
                    waitForBackgroundGraphicsPipeline: requiresCompletePipeline);
                RenderStageTimer.PipelineTicks += RenderStageTimer.Now() - pipelineStart;
                RenderStageTimer.Pipelines++;

                if (!created)
                {
                    return false;
                }

                _graphicsStateDirty = false;
                Pbp = PipelineBindPoint.Graphics;
            }

            long barrierStart = RenderStageTimer.Now();
            Gd.Barriers.Flush(Cbs, _program, _feedbackLoop != 0, RenderPassActive, _rpHolder, EndRenderPassDelegate);
            long descriptorStart = RenderStageTimer.Now();

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Graphics);
            RenderStageTimer.BarrierTicks += descriptorStart - barrierStart;
            RenderStageTimer.DescriptorTicks += RenderStageTimer.Now() - descriptorStart;'''

PASS_BEGIN_OLD = '''            if (!RenderPassActive)
            {
                FramebufferParams.InsertLoadOpBarriers(Gd, Cbs);'''
PASS_BEGIN_NEW = '''            if (!RenderPassActive)
            {
                long passStart = RenderStageTimer.Now();

                if (_framebuffer != null && _framebuffer == _lastEndedFramebuffer)
                {
                    RenderStageTimer.PassResumes++;
                }

                FramebufferParams.InsertLoadOpBarriers(Gd, Cbs);'''

PASS_BEGUN_OLD = '''                Gd.Api.CmdBeginRenderPass(CommandBuffer, in renderPassBeginInfo, SubpassContents.Inline);
                RenderPassActive = true;'''
PASS_BEGUN_NEW = '''                Gd.Api.CmdBeginRenderPass(CommandBuffer, in renderPassBeginInfo, SubpassContents.Inline);
                RenderPassActive = true;
                RenderStageTimer.PassTicks += RenderStageTimer.Now() - passStart;
                RenderStageTimer.PassBegins++;'''

PASS_END_OLD = '''                Gd.Api.CmdEndRenderPass(CommandBuffer);
                SignalRenderPassEnd();
                RenderPassActive = false;'''
PASS_END_NEW = '''                Gd.Api.CmdEndRenderPass(CommandBuffer);
                SignalRenderPassEnd();
                RenderPassActive = false;
                _lastEndedFramebuffer = _framebuffer;'''

SUBMIT_OLD = '''        public void FlushCommandsImpl()
        {
            AutoFlush.RegisterFlush(DrawCount);'''
SUBMIT_NEW = '''        public void FlushCommandsImpl()
        {
            // Each command buffer submission is timed whole (RenderStageTimer), with the queue part: vkQueueSubmit and the
            // wait for a free command buffer.
            long start = RenderStageTimer.Now();
            SubmitCommands();
            RenderStageTimer.SubmitTicks += RenderStageTimer.Now() - start;
            RenderStageTimer.Submits++;
        }

        private void SubmitCommands()
        {
            AutoFlush.RegisterFlush(DrawCount);'''

QUEUE_OLD = '''            CommandBuffer = (Cbs = Gd.CommandBufferPool.ReturnAndRent(Cbs)).CommandBuffer;'''
QUEUE_NEW = '''            long queueStart = RenderStageTimer.Now();
            CommandBuffer = (Cbs = Gd.CommandBufferPool.ReturnAndRent(Cbs)).CommandBuffer;
            RenderStageTimer.QueueTicks += RenderStageTimer.Now() - queueStart;'''

PRESENT_START_OLD = '''            TextureView view = (TextureView)texture;

            _gd.RegisterPresentationTexture(view);
            _gd.PipelineInternal.AutoFlush.Present();

            uint nextImage = 0;'''
PRESENT_START_NEW = '''            // The whole presentation, the swapchain image acquisition and the queue present are timed (RenderStageTimer).
            long presentStart = RenderStageTimer.Now();
            TextureView view = (TextureView)texture;

            _gd.RegisterPresentationTexture(view);
            _gd.PipelineInternal.AutoFlush.Present();

            long acquireStart = RenderStageTimer.Now();
            uint nextImage = 0;'''

PRESENT_ACQUIRED_OLD = '''            Image swapchainImage = _swapchainImages[nextImage];

            _gd.FlushAllCommands();'''
PRESENT_ACQUIRED_NEW = '''            Image swapchainImage = _swapchainImages[nextImage];
            long acquired = RenderStageTimer.Now();

            _gd.FlushAllCommands();'''

PRESENT_END_OLD = '''            lock (_gd.QueueLock)
            {
                if (metalFxPrepared)
                {
                    _metalFxScalingFilter.Encode();
                }

                _gd.SwapchainApi.QueuePresent(_gd.Queue, in presentInfo);
            }'''
PRESENT_END_NEW = '''            long queuePresentStart = RenderStageTimer.Now();

            lock (_gd.QueueLock)
            {
                if (metalFxPrepared)
                {
                    _metalFxScalingFilter.Encode();
                }

                _gd.SwapchainApi.QueuePresent(_gd.Queue, in presentInfo);
            }

            RenderStageTimer.NotePresent(presentStart, acquireStart, acquired, queuePresentStart);'''

MVK_TRACKING_OLD = '''            config.ResumeLostDevice = true;

            vkSetMoltenVKConfigurationMVK(nint.Zero, config, configSize);'''
MVK_TRACKING_NEW = '''            config.ResumeLostDevice = true;

            // MoltenVK's own statistics, logged to stderr every 300 presented frames: Metal encoding of each command buffer
            // on its submission thread, GPU execution of each Metal command buffer, drawable waits and frame intervals.
            config.PerformanceTracking = true;
            config.PerformanceLoggingFrameCount = 300;

            vkSetMoltenVKConfigurationMVK(nint.Zero, config, configSize);'''

BUFFER_FLUSH_WAIT_OLD = '''                using (PD.Measure(PD.Phase.BufferReadback)) fence.Wait();'''
BUFFER_FLUSH_WAIT_NEW = '''                long flushWaitStart = RenderStageTimer.Now();
                using (PD.Measure(PD.Phase.BufferReadback)) fence.Wait();
                RenderStageTimer.NoteFenceWait(_gd.CommandBufferPool?.OwnedByCurrentThread == true, write: false, flushWaitStart);'''

BUFFER_WAITS_OLD = '''        public void WaitForFences()
        {
            using (PD.Measure(PD.Phase.BufferReadback)) _waitable.WaitForFences(_gd.Api, _device);
        }

        public void WaitForFences(int offset, int size)
        {
            using (PD.Measure(PD.Phase.BufferReadback)) _waitable.WaitForFences(_gd.Api, _device, offset, size);
        }'''
BUFFER_WAITS_NEW = '''        // The fence waits are timed (RenderStageTimer): the whole-buffer one for reads (flush buffers), the ranged one before a
        // direct write (SetData); the render thread's apart from those of other threads.
        public void WaitForFences()
        {
            long start = RenderStageTimer.Now();
            using (PD.Measure(PD.Phase.BufferReadback)) _waitable.WaitForFences(_gd.Api, _device);
            RenderStageTimer.NoteFenceWait(_gd.CommandBufferPool?.OwnedByCurrentThread == true, write: false, start);
        }

        public void WaitForFences(int offset, int size)
        {
            long start = RenderStageTimer.Now();
            using (PD.Measure(PD.Phase.BufferReadback)) _waitable.WaitForFences(_gd.Api, _device, offset, size);
            RenderStageTimer.NoteFenceWait(_gd.CommandBufferPool?.OwnedByCurrentThread == true, write: true, start);
        }'''

BUFFER_HOLDER_HUNKS = [(BUFFER_FLUSH_WAIT_OLD, BUFFER_FLUSH_WAIT_NEW), (BUFFER_WAITS_OLD, BUFFER_WAITS_NEW)]
PIPELINE_BASE_HUNKS = [(STAGE_CLASS_OLD, STAGE_CLASS_NEW), (STAGE_FIELD_OLD, STAGE_FIELD_NEW), (PREPARE_OLD, PREPARE_NEW),
                       (AUTO_FLUSH_OLD, AUTO_FLUSH_NEW), (DRAW_STATE_OLD, DRAW_STATE_NEW), (PASS_BEGIN_OLD, PASS_BEGIN_NEW),
                       (PASS_BEGUN_OLD, PASS_BEGUN_NEW), (PASS_END_OLD, PASS_END_NEW)]
PIPELINE_FULL_HUNKS = [(SUBMIT_OLD, SUBMIT_NEW), (QUEUE_OLD, QUEUE_NEW)]
WINDOW_HUNKS = [(PRESENT_START_OLD, PRESENT_START_NEW), (PRESENT_ACQUIRED_OLD, PRESENT_ACQUIRED_NEW),
                (PRESENT_END_OLD, PRESENT_END_NEW)]
MVK_HUNKS = [(MVK_TRACKING_OLD, MVK_TRACKING_NEW)]


def apply_threaded(path):
    once(Path(path), THREADED_NAMESPACE_OLD, THREADED_NAMESPACE_NEW)
    once(Path(path), THREADED_OLD, THREADED_NEW)
    once(Path(path), RENDER_WORK_OLD, RENDER_WORK_NEW)
    once(Path(path), RENDER_STATE_OLD, RENDER_STATE_NEW)


def apply_pipeline_budget(path):
    once(Path(path), PIPELINE_BUDGET_OLD, PIPELINE_BUDGET_NEW)


def apply_scheduler(path):
    once(Path(path), SCHEDULER_OLD, SCHEDULER_NEW)


def apply_hunks(path, hunks):
    # Every anchor is checked before the file is written: a drifted anchor leaves the file as it was.
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    for old, new in hunks:
        assert text.count(old) == 1, (str(path), old[:90], text.count(old))
        text = text.replace(old, new)
    path.write_text(text, encoding='utf-8')


def apply_render_stages(source):
    source = Path(source)
    apply_hunks(source / PIPELINE_BASE, PIPELINE_BASE_HUNKS)
    apply_hunks(source / PIPELINE_FULL, PIPELINE_FULL_HUNKS)
    apply_hunks(source / WINDOW, WINDOW_HUNKS)
    apply_hunks(source / MVK_INITIALIZATION, MVK_HUNKS)
    apply_hunks(source / BUFFER_HOLDER, BUFFER_HOLDER_HUNKS)


def apply(source):
    source = Path(source)
    apply_threaded(source / THREADED)
    apply_pipeline_budget(source / PIPELINE_CACHE)
    apply_scheduler(source / SCHEDULER)
    apply_render_stages(source)
    return NAMES
