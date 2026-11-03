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
  barriers, descriptor updates, auto-flushes), and from build 625 a compute dispatch's (pipelines, barriers,
  descriptors; build 624: 21-29 ms of render-thread time per frame for about 40 dispatches, each ending the
  render pass it interrupts), the render passes it begins (and how many begin again on
  the framebuffer the last one ended on), the command buffer submissions, the buffer fence waits (the
  render thread's own, before a direct buffer write or for a read, and those of other threads, such as a
  guest thread reading a deferred read-back) and the presentation (swapchain image acquisition and queue
  present). It logs them every 5 s of presentation to the core log.
- MoltenVK's own performance tracking is on and logs its statistics every 300 presented frames to stderr:
  Metal encoding of each command buffer on MoltenVK's submission thread, GPU execution of each Metal
  command buffer, drawable waits and frame intervals. Together they tell whether a frame waits for the
  render thread, for MoltenVK's encoding or for the GPU.

Build 628 (MoltenVK on a tile-based GPU; Hogwarts Legacy only until a second title is measured):
- MoltenVK 1.4.0 restarts the Metal render pass for every image barrier with the GENERAL layout recorded
  inside a render pass (MVKCmdPipelineBarrier::encode: all attachments stored, then loaded again), and
  Ryujinx records each texture's write-to-read barrier as such an image barrier when the texture is bound
  while a pass is active. That barrier only follows the texture's use as an attachment
  (TextureStorage.AddStoreOpUsage, QueueLoadOpBarrier). When the texture is not an attachment of the
  active pass, that use was in a pass that has ended, an earlier Metal encoder, and Metal's hazard
  tracking (MoltenVK's resources are tracked) already orders the read after it. Such a barrier is now
  deferred to the next begin of that pass (the forced fence BarrierBatch adds for an in-pass barrier)
  instead of being recorded inside it (PipelineBase.TryDeferInPassReadBarrier). An attachment of the
  active pass (a feedback loop) keeps its barrier.
- A second line after each "Vulkan render stages" line ("Vulkan pass and GPU detail") gives: the render
  command that ended each pass begun again on the same framebuffer (ThreadedRenderer.CurrentRenderCommand),
  the in-pass read barriers deferred and kept, the compute descriptor updates by program size, the
  process's first-chance exceptions, and the GPU's busy time.
- The GPU's busy time comes from the Metal command buffers (MetalGpuTimer): MoltenVK's "Execute a
  MTLCommandBuffer on GPU" counts from the commit to the completion handler, queue wait included, so it
  is not the GPU's work. -[MTLCommandBuffer commit] of the command buffer class of MoltenVK's queue is
  replaced (Objective-C runtime) by a function that retains the command buffer and calls the original;
  the render thread reads GPUStartTime and GPUEndTime of each completed one and merges the intervals, so
  overlapping command buffers count once. At most 1024 are pending, and none is recorded when the render
  thread has not read them for a second.

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
TEXTURE_STORAGE = 'src/Ryujinx.Graphics.Vulkan/TextureStorage.cs'
NAMES = [THREADED, PIPELINE_CACHE, SCHEDULER, PIPELINE_BASE, PIPELINE_FULL, WINDOW, MVK_INITIALIZATION, BUFFER_HOLDER, TEXTURE_STORAGE]

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
                    CurrentRenderCommand = commandType;
                    long commandStart = Stopwatch.GetTimestamp();
                    CommandHelper.RunCommand(command, this, _baseRenderer);
                    NoteRenderCommand(commandType, commandStart);

                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)'''

RENDER_STATE_OLD = '''        public void RenderLoop()
        {'''
RENDER_STATE_NEW = '''        // Render-thread time per queued command type over each 5 s of rendering. The 8 types with the most time are logged
        // with their calls and milliseconds, then the window starts again (render thread only, no lock).
        private readonly long[] _renderWorkTicks = new long[256];

        /// <summary>
        /// The type of the command the render thread runs now (the backend attributes its render pass ends to it).
        /// </summary>
        public static byte CurrentRenderCommand;

        /// <summary>
        /// The name of a command type, for the backend's diagnostics.
        /// </summary>
        public static string RenderCommandName(byte type) => ((CommandType)type).ToString();
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
        public static long ComputePrepareTicks, ComputePrepares, ComputePipelineTicks, ComputePipelines;
        public static long ComputeBarrierTicks, ComputeDescriptorTicks, Dispatches, DispatchPassEnds;
        private static long _otherWaitTicks, _otherWaits;
        private static long _presentTicks, _presents, _acquireTicks, _queuePresentTicks, _windowStart;

        public static long Now() => System.Diagnostics.Stopwatch.GetTimestamp();

        // A compute dispatch, and whether it ends a render pass (the next draw on that framebuffer begins it again).
        public static void NoteDispatch(bool renderPassActive)
        {
            Dispatches++;

            if (renderPassActive)
            {
                DispatchPassEnds++;
            }
        }

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
            MetalGpuTimer.Poll();
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
                " ms, auto-flushes " + AutoFlushes + " calls " + Ms(AutoFlushTicks) + " ms); compute prepare " + ComputePrepares +
                " calls " + Ms(ComputePrepareTicks) + " ms (pipelines " + ComputePipelines + " calls " + Ms(ComputePipelineTicks) +
                " ms, barriers " + Ms(ComputeBarrierTicks) + " ms, descriptors " + Ms(ComputeDescriptorTicks) + " ms; dispatches " +
                Dispatches + ", render passes ended " + DispatchPassEnds + "); render passes " + PassBegins +
                " begun " + Ms(PassTicks) + " ms (same framebuffer again " + PassResumes + "); submits " + Submits + " calls " +
                Ms(SubmitTicks) + " ms (queue " + Ms(QueueTicks) + " ms); fence waits on the render thread: buffer writes " +
                WriteWaits + " calls " + Ms(WriteWaitTicks) + " ms, reads " + ReadWaits + " calls " + Ms(ReadWaitTicks) +
                " ms; on other threads " + otherWaits + " calls " + Ms(otherWaitTicks) + " ms; present " + _presents + " calls " +
                Ms(_presentTicks) +
                " ms (acquire " + Ms(_acquireTicks) + " ms, queue present " + Ms(_queuePresentTicks) + " ms)";

            PrepareTicks = Prepares = NotReady = PipelineTicks = Pipelines = BarrierTicks = DescriptorTicks = 0;
            AutoFlushTicks = AutoFlushes = PassTicks = PassBegins = PassResumes = SubmitTicks = Submits = QueueTicks = 0;
            WriteWaitTicks = WriteWaits = ReadWaitTicks = ReadWaits = 0;
            ComputePrepareTicks = ComputePrepares = ComputePipelineTicks = ComputePipelines = 0;
            ComputeBarrierTicks = ComputeDescriptorTicks = Dispatches = DispatchPassEnds = 0;
            string window = Ms(end - _windowStart);
            long frames = _presents;
            _presentTicks = _presents = _acquireTicks = _queuePresentTicks = 0;
            _windowStart = end;
            Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, text);
            RenderDetail.Log(window, frames);
        }
    }

    /// <summary>
    /// Per-session MoltenVK policy, set at launch from the title (Hogwarts Legacy only until a second title is measured).
    /// </summary>
    public static class MoltenVkPolicy
    {
        /// <summary>
        /// Defers the write-to-read barrier of a texture bound inside a render pass it is not an attachment of
        /// (PipelineBase.TryDeferInPassReadBarrier): MoltenVK restarts the Metal render pass for each one.
        /// </summary>
        public static bool DeferInPassReadBarriers { get; set; }

        /// <summary>
        /// Measures the GPU's busy time from the Metal command buffers (MetalGpuTimer).
        /// </summary>
        public static bool MeasureGpu { get; set; }
    }

    /// <summary>
    /// The render passes and the GPU in more detail, logged after each "Vulkan render stages" line: the render command that
    /// ended each pass begun again on the same framebuffer, the in-pass read barriers deferred and kept, the compute
    /// descriptor updates by program size (descriptors in its four main sets), the process's first-chance exceptions (the
    /// first four kinds once each), and the GPU's busy time (MetalGpuTimer). Render thread only, except the exception count.
    /// </summary>
    static class RenderDetail
    {
        public static long DeferredPassBarriers, FeedbackPassBarriers;
        private static readonly long[] _resumesAfter = new long[256];
        private static readonly long[] _computeTicks = new long[3];
        private static readonly long[] _computeCalls = new long[3];
        private static int _largestCompute;
        private static long _exceptions;
        private static readonly System.Collections.Generic.List<string> _exceptionKinds = new();
        private static int _exceptionKindsLogged;
        private static bool _watching;
        [ThreadStatic] private static bool _inException;

        public static void NoteResume(byte endCommand) => _resumesAfter[endCommand]++;

        public static void NoteComputeDescriptors(ShaderCollection program, long ticks)
        {
            int descriptors = 0;
            ResourceBindingSegment[][] sets = program?.BindingSegments;

            for (int set = 0; sets != null && set < sets.Length && set < PipelineBase.DescriptorSetLayouts; set++)
            {
                foreach (ResourceBindingSegment segment in sets[set])
                {
                    descriptors += segment.Count;
                }
            }

            int bucket = descriptors <= 32 ? 0 : descriptors <= 256 ? 1 : 2;
            _computeTicks[bucket] += ticks;
            _computeCalls[bucket]++;
            _largestCompute = Math.Max(_largestCompute, descriptors);
        }

        private static void WatchExceptions()
        {
            _watching = true;

            AppDomain.CurrentDomain.FirstChanceException += static (_, args) =>
            {
                if (_inException)
                {
                    return;
                }

                _inException = true;

                try
                {
                    System.Threading.Interlocked.Increment(ref _exceptions);

                    lock (_exceptionKinds)
                    {
                        if (_exceptionKinds.Count < 4)
                        {
                            string trace = args.Exception.StackTrace ?? string.Empty;
                            int line = trace.IndexOf((char)10);
                            string site = (line < 0 ? trace : trace[..line]).Trim();
                            string message = args.Exception.Message ?? string.Empty;
                            string kind = args.Exception.GetType().Name + " (" + (message.Length > 80 ? message[..80] : message) + ") " + site;

                            if (!_exceptionKinds.Contains(kind))
                            {
                                _exceptionKinds.Add(kind);
                            }
                        }
                    }
                }
                catch
                {
                }
                finally
                {
                    _inException = false;
                }
            };
        }

        public static void Log(string window, long frames)
        {
            if (!_watching)
            {
                WatchExceptions();
            }

            var text = new System.Text.StringBuilder("Vulkan pass and GPU detail over ").Append(window).Append(" ms, ").Append(frames)
                .Append(" frames: same framebuffer again after");
            long[] resumes = (long[])_resumesAfter.Clone();

            for (int rank = 0; rank < 4; rank++)
            {
                int best = -1;

                for (int i = 0; i < resumes.Length; i++)
                {
                    if (resumes[i] > 0 && (best < 0 || resumes[i] > resumes[best]))
                    {
                        best = i;
                    }
                }

                if (best < 0)
                {
                    text.Append(rank == 0 ? " none" : string.Empty);
                    break;
                }

                text.Append(rank == 0 ? " " : ", ").Append(Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer.RenderCommandName((byte)best))
                    .Append(' ').Append(resumes[best]);
                resumes[best] = 0;
            }

            text.Append("; in-pass read barriers deferred ").Append(DeferredPassBarriers).Append(", kept for attachments ")
                .Append(FeedbackPassBarriers).Append("; compute descriptors by program size: up to 32 ").Append(_computeCalls[0])
                .Append(" calls ").Append(Ms(_computeTicks[0])).Append(" ms, up to 256 ").Append(_computeCalls[1]).Append(" calls ")
                .Append(Ms(_computeTicks[1])).Append(" ms, larger ").Append(_computeCalls[2]).Append(" calls ").Append(Ms(_computeTicks[2]))
                .Append(" ms (largest ").Append(_largestCompute).Append("); exceptions ")
                .Append(System.Threading.Interlocked.Exchange(ref _exceptions, 0));

            lock (_exceptionKinds)
            {
                for (; _exceptionKindsLogged < _exceptionKinds.Count; _exceptionKindsLogged++)
                {
                    text.Append(_exceptionKindsLogged == 0 ? " (first: " : " | ").Append(_exceptionKinds[_exceptionKindsLogged]);
                    text.Append(_exceptionKindsLogged == _exceptionKinds.Count - 1 ? ")" : string.Empty);
                }
            }

            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));

            Array.Clear(_resumesAfter);
            Array.Clear(_computeTicks);
            Array.Clear(_computeCalls);
            _largestCompute = 0;
            DeferredPassBarriers = FeedbackPassBarriers = 0;
            Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, text.ToString());
        }

        private static string Ms(long ticks) =>
            (ticks * 1000.0 / System.Diagnostics.Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);
    }

    /// <summary>
    /// The GPU's busy time from the Metal command buffers themselves (MoltenVK's own GPU figure counts from the commit to the
    /// completion handler, queue wait included). -[MTLCommandBuffer commit] of the command buffer class of MoltenVK's queue
    /// is replaced, through the Objective-C runtime, by Commit: it retains the command buffer and calls the original. Poll,
    /// on the render thread at each present, reads GPUStartTime and GPUEndTime of each completed one and releases it;
    /// TakeWindow merges the intervals, so overlapping command buffers count once. At most 1024 are pending, and none is
    /// recorded when Poll has not run for a second.
    /// </summary>
    static unsafe partial class MetalGpuTimer
    {
        private const string ObjC = "/usr/lib/libobjc.A.dylib";

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "sel_registerName",
            StringMarshalling = System.Runtime.InteropServices.StringMarshalling.Utf8)]
        private static partial nint Selector(string name);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "object_getClass")]
        private static partial nint GetClass(nint instance);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "class_getInstanceMethod")]
        private static partial nint GetMethod(nint type, nint selector);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "method_getImplementation")]
        private static partial nint GetImplementation(nint method);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "method_setImplementation")]
        private static partial nint SetImplementation(nint method, nint implementation);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "objc_retain")]
        private static partial nint Retain(nint instance);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "objc_release")]
        private static partial void Release(nint instance);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "objc_msgSend")]
        private static partial nint SendPointer(nint receiver, nint selector);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "objc_msgSend")]
        private static partial nuint SendUnsigned(nint receiver, nint selector);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "objc_msgSend")]
        private static partial double SendDouble(nint receiver, nint selector);

        [System.Runtime.InteropServices.LibraryImport(ObjC, EntryPoint = "objc_msgSend")]
        [return: System.Runtime.InteropServices.MarshalAs(System.Runtime.InteropServices.UnmanagedType.I1)]
        private static partial bool Responds(nint receiver, nint selector, nint argument);

        private const nuint Completed = 4;
        private static nint _original, _status, _gpuStart, _gpuEnd;
        private static readonly object _lock = new();
        private static nint[] _pending = new nint[1024], _taken = new nint[1024];
        private static int _pendingCount;
        private static long _lastPoll;
        private static readonly System.Collections.Generic.List<(double Start, double End)> _intervals = new(4096);
        private static string _state = "not measured";

        public static bool Tried { get; private set; }

        public static void Install(nint metalQueue)
        {
            Tried = true;

            try
            {
                nint responds = Selector("respondsToSelector:");
                _status = Selector("status");
                _gpuStart = Selector("GPUStartTime");
                _gpuEnd = Selector("GPUEndTime");
                // A command buffer of a queue of MoltenVK's device gives the class its command buffers have. It is never
                // committed, so it comes from a queue of its own: it holds none of the slots of MoltenVK's queue.
                nint device = metalQueue == 0 ? 0 : SendPointer(metalQueue, Selector("device"));
                nint ownQueue = device == 0 ? 0 : SendPointer(device, Selector("newCommandQueue"));
                nint probe = ownQueue == 0 ? 0 : SendPointer(ownQueue, Selector("commandBuffer"));

                if (ownQueue != 0)
                {
                    // The probe, autoreleased, keeps its queue alive while it exists.
                    Release(ownQueue);
                }

                if (probe == 0 || !Responds(probe, responds, _gpuStart) || !Responds(probe, responds, _gpuEnd) ||
                    !Responds(probe, responds, _status))
                {
                    _state = "timer unavailable";
                    return;
                }

                nint method = GetMethod(GetClass(probe), Selector("commit"));
                nint original = method == 0 ? 0 : GetImplementation(method);

                if (original == 0)
                {
                    _state = "timer unavailable (no commit)";
                    return;
                }

                // The original is known before the replacement can run.
                _original = original;
                System.Threading.Volatile.Write(ref _lastPoll, System.Diagnostics.Stopwatch.GetTimestamp());
                SetImplementation(method, (nint)(delegate* unmanaged<nint, nint, void>)&Commit);
                _state = "timer on";
            }
            catch (Exception e)
            {
                _state = "timer failed (" + e.GetType().Name + ")";
            }
        }

        [System.Runtime.InteropServices.UnmanagedCallersOnly]
        private static void Commit(nint self, nint selector)
        {
            try
            {
                if (System.Diagnostics.Stopwatch.GetTimestamp() - System.Threading.Volatile.Read(ref _lastPoll) <
                    System.Diagnostics.Stopwatch.Frequency)
                {
                    lock (_lock)
                    {
                        if (_pendingCount < _pending.Length)
                        {
                            _pending[_pendingCount++] = Retain(self);
                        }
                    }
                }
            }
            catch
            {
            }

            ((delegate* unmanaged<nint, nint, void>)_original)(self, selector);
        }

        public static void Poll()
        {
            if (_original == 0)
            {
                return;
            }

            System.Threading.Volatile.Write(ref _lastPoll, System.Diagnostics.Stopwatch.GetTimestamp());
            int count;

            lock (_lock)
            {
                (_pending, _taken) = (_taken, _pending);
                count = _pendingCount;
                _pendingCount = 0;
            }

            int kept = 0;

            for (int i = 0; i < count; i++)
            {
                nint commandBuffer = _taken[i];
                nuint status = SendUnsigned(commandBuffer, _status);

                if (status < Completed)
                {
                    _taken[kept++] = commandBuffer;
                    continue;
                }

                if (status == Completed)
                {
                    double start = SendDouble(commandBuffer, _gpuStart), end = SendDouble(commandBuffer, _gpuEnd);

                    if (start > 0 && end > start)
                    {
                        _intervals.Add((start, end));
                    }
                }

                Release(commandBuffer);
            }

            lock (_lock)
            {
                for (int i = 0; i < kept && _pendingCount < _pending.Length; i++)
                {
                    _pending[_pendingCount++] = _taken[i];
                }
            }
        }

        public static string TakeWindow(long frames)
        {
            if (_original == 0 || _intervals.Count == 0)
            {
                return _state;
            }

            _intervals.Sort(static (a, b) => a.Start.CompareTo(b.Start));
            double busy = 0, longest = 0, spanStart = _intervals[0].Start, spanEnd = _intervals[0].End, from = spanStart, to = spanEnd;

            foreach ((double start, double end) in _intervals)
            {
                longest = Math.Max(longest, end - start);
                spanEnd = Math.Max(spanEnd, end);

                if (start > to)
                {
                    busy += to - from;
                    from = start;
                    to = end;
                }
                else
                {
                    to = Math.Max(to, end);
                }
            }

            busy += to - from;
            double span = spanEnd - spanStart;
            var culture = System.Globalization.CultureInfo.InvariantCulture;
            string text = "busy " + (busy * 1000.0 / Math.Max(frames, 1)).ToString("F1", culture) + " ms per frame (" +
                (span > 0 ? busy * 100.0 / span : 0).ToString("F0", culture) + " % of " + (span * 1000.0).ToString("F0", culture) +
                " ms) in " + _intervals.Count + " command buffers, longest " + (longest * 1000.0).ToString("F1", culture) + " ms";
            _intervals.Clear();

            return text;
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
        // The render command that ended it (ThreadedRenderer.CurrentRenderCommand), for RenderDetail.
        private byte _lastEndCommand;
        private RenderPassHolder _rpHolder;

        /// <summary>
        /// MoltenVK on a tile-based GPU (MoltenVkPolicy.DeferInPassReadBarriers): MoltenVK restarts the Metal render pass for
        /// every image barrier with the GENERAL layout recorded inside a render pass (all attachments stored, then loaded
        /// again). A texture's write-to-read barrier only follows its use as an attachment; when the texture is not an
        /// attachment of the active pass, that use was in a pass that has ended, an earlier Metal encoder, and Metal's hazard
        /// tracking already orders this read after it. The barrier is then deferred to the next begin of this pass (the
        /// forced fence BarrierBatch adds for an in-pass barrier) instead of being recorded inside it. An attachment of the
        /// active pass (a feedback loop) keeps its barrier.
        /// </summary>
        /// <returns>True if the barrier was deferred, false to queue it</returns>
        internal bool TryDeferInPassReadBarrier(TextureStorage storage, PipelineStageFlags dstStageFlags)
        {
            if (!MoltenVkPolicy.DeferInPassReadBarriers || !RenderPassActive || !Gd.IsMoltenVk || !Gd.IsTBDR || _rpHolder == null)
            {
                return false;
            }

            if (_rpHolder.ContainsAttachment(storage))
            {
                RenderDetail.FeedbackPassBarriers++;
                return false;
            }

            _rpHolder.AddForcedFence(storage, dstStageFlags);
            RenderDetail.DeferredPassBarriers++;

            return true;
        }'''

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
                    RenderDetail.NoteResume(_lastEndCommand);
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
                _lastEndedFramebuffer = _framebuffer;
                _lastEndCommand = Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer.CurrentRenderCommand;'''

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

            if (MoltenVkPolicy.MeasureGpu && !MetalGpuTimer.Tried && _gd.IsMoltenVk)
            {
                MetalGpuTimer.Install(MoltenVK.MoltenVkMetalInterop.GetMetalCommandQueue(_gd.Queue));
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

READ_BARRIER_OLD = '''            if (_lastModificationAccess != AccessFlags.None)
            {
                ImageAspectFlags aspectFlags = Info.Format.ConvertAspectFlags();
                ImageMemoryBarrier barrier = TextureView.GetImageBarrier(
                    _imageAuto.Get(cbs).Value,
                    _lastModificationAccess,
                    dstAccessFlags,'''
READ_BARRIER_NEW = '''            if (_lastModificationAccess != AccessFlags.None)
            {
                // Inside a render pass this texture is not an attachment of, on MoltenVK with a tile-based GPU, the barrier
                // is deferred to the next begin of that pass (PipelineBase.TryDeferInPassReadBarrier).
                if (_gd.PipelineInternal != null && _gd.PipelineInternal.TryDeferInPassReadBarrier(this, dstStageFlags))
                {
                    _lastModificationAccess = AccessFlags.None;
                    return;
                }

                ImageAspectFlags aspectFlags = Info.Format.ConvertAspectFlags();
                ImageMemoryBarrier barrier = TextureView.GetImageBarrier(
                    _imageAuto.Get(cbs).Value,
                    _lastModificationAccess,
                    dstAccessFlags,'''
TEXTURE_STORAGE_HUNKS = [(READ_BARRIER_OLD, READ_BARRIER_NEW)]
COMPUTE_PREPARE_OLD = '''        private bool RecreateComputePipelineIfNeeded(bool allowAsyncSkip = false)
        {
            if (_computeStateDirty || Pbp != PipelineBindPoint.Compute)
            {
                if (!CreatePipeline(PipelineBindPoint.Compute, allowAsyncSkip))
                {
                    return false;
                }'''
COMPUTE_PREPARE_NEW = '''        private bool RecreateComputePipelineIfNeeded(bool allowAsyncSkip = false)
        {
            // Every dispatch's preparation is timed whole (RenderStageTimer), with its pipeline, barrier and descriptor parts.
            long start = RenderStageTimer.Now();
            bool ready = PrepareComputeDispatch(allowAsyncSkip);
            RenderStageTimer.ComputePrepareTicks += RenderStageTimer.Now() - start;
            RenderStageTimer.ComputePrepares++;

            return ready;
        }

        private bool PrepareComputeDispatch(bool allowAsyncSkip)
        {
            if (_computeStateDirty || Pbp != PipelineBindPoint.Compute)
            {
                long pipelineStart = RenderStageTimer.Now();
                bool created = CreatePipeline(PipelineBindPoint.Compute, allowAsyncSkip);
                RenderStageTimer.ComputePipelineTicks += RenderStageTimer.Now() - pipelineStart;
                RenderStageTimer.ComputePipelines++;

                if (!created)
                {
                    return false;
                }'''

COMPUTE_STATE_OLD = '''            Gd.Barriers.Flush(Cbs, _program, _feedbackLoop != 0, RenderPassActive, _rpHolder, EndRenderPassDelegate);

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Compute);'''
COMPUTE_STATE_NEW = '''            long barrierStart = RenderStageTimer.Now();
            Gd.Barriers.Flush(Cbs, _program, _feedbackLoop != 0, RenderPassActive, _rpHolder, EndRenderPassDelegate);
            long descriptorStart = RenderStageTimer.Now();

            _descriptorSetUpdater.UpdateAndBindDescriptorSets(Cbs, PipelineBindPoint.Compute);
            long computeDescriptorTicks = RenderStageTimer.Now() - descriptorStart;
            RenderStageTimer.ComputeBarrierTicks += descriptorStart - barrierStart;
            RenderStageTimer.ComputeDescriptorTicks += computeDescriptorTicks;
            RenderDetail.NoteComputeDescriptors(_program, computeDescriptorTicks);'''

DISPATCH_OLD = '''        public void DispatchCompute(int groupsX, int groupsY, int groupsZ)
        {
            EndRenderPass();'''
DISPATCH_NEW = '''        public void DispatchCompute(int groupsX, int groupsY, int groupsZ)
        {
            RenderStageTimer.NoteDispatch(RenderPassActive);
            EndRenderPass();'''

DISPATCH_INDIRECT_OLD = '''        public void DispatchComputeIndirect(Auto<DisposableBuffer> indirectBuffer, int indirectBufferOffset)
        {
            EndRenderPass();'''
DISPATCH_INDIRECT_NEW = '''        public void DispatchComputeIndirect(Auto<DisposableBuffer> indirectBuffer, int indirectBufferOffset)
        {
            RenderStageTimer.NoteDispatch(RenderPassActive);
            EndRenderPass();'''

PIPELINE_BASE_HUNKS = [(STAGE_CLASS_OLD, STAGE_CLASS_NEW), (STAGE_FIELD_OLD, STAGE_FIELD_NEW), (PREPARE_OLD, PREPARE_NEW),
                       (AUTO_FLUSH_OLD, AUTO_FLUSH_NEW), (DRAW_STATE_OLD, DRAW_STATE_NEW), (PASS_BEGIN_OLD, PASS_BEGIN_NEW),
                       (PASS_BEGUN_OLD, PASS_BEGUN_NEW), (PASS_END_OLD, PASS_END_NEW), (COMPUTE_PREPARE_OLD, COMPUTE_PREPARE_NEW),
                       (COMPUTE_STATE_OLD, COMPUTE_STATE_NEW), (DISPATCH_OLD, DISPATCH_NEW),
                       (DISPATCH_INDIRECT_OLD, DISPATCH_INDIRECT_NEW)]
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
    apply_hunks(source / TEXTURE_STORAGE, TEXTURE_STORAGE_HUNKS)


def apply(source):
    source = Path(source)
    apply_threaded(source / THREADED)
    apply_pipeline_budget(source / PIPELINE_CACHE)
    apply_scheduler(source / SCHEDULER)
    apply_render_stages(source)
    return NAMES
