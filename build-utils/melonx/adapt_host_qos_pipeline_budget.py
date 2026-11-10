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

Build 631, descriptor encoding (EncodingPolicy, Hogwarts Legacy only until a second title is measured; off,
both paths are the delivered ones). Build 629 journals, heavy play (render thread busy 46.7 ms per frame,
GPU 19.2 ms): compute descriptor updates 30.7 ms per frame, following the bindless array delta passes
(r = 0.992, 7.7 ms per pass); 326 439 first-chance IndexOutOfRangeException in 1067 frames.
- DescriptorSetUpdater: the template path of UpdateAndBind indexes its scratch arrays by binding number,
  and they held one stage (32 textures, 16 images): a fragment texture (binding 64-95), a buffer texture or
  a buffer image threw, UpdateAndBindDescriptorSets caught it and wrote the set again one descriptor at a
  time. The scratch arrays are sized like the references (MaxTextureBindings * 2, MaxImageBindings * 2),
  the template path takes them whole under the policy, the one-stage lengths otherwise, and every
  template fallback is counted by set (uniform, storage, texture, image).
- TextureArray (texture arrays only): any update released the array's descriptor set, and its next bind
  wrote all 524 288 elements; every new command buffer walked them all to reference their views and
  samplers. Under the policy each update is recorded by range (a log of 1024 ranges), the element values
  are resolved from the changed ranges, each command buffer references the distinct views and samplers
  once (counted incrementally for updates of up to 4096 elements, counted again otherwise; a destroyed one
  found there is recorded as a change of its elements, which take the dummy), and the array keeps up to
  8 descriptor sets of its own from the program's manual-set cache: the current one is bound again, or
  an idle one (bound in no pending command buffer, PipelineLayoutCacheEntry.IsManualDescriptorSetCollection
  Idle) is brought up to date by writing only the elements changed since it was written (whole when the
  log no longer holds them or a quarter changed), or a new one is written whole. A binding that is not one
  array of the array's length, or every set pending, takes the delivered path. ResourceArray releases the
  array's own sets when it is disposed.
- The detail line gives the template fallbacks by set and the texture array writes: whole (elements),
  by range (elements written and kept), their time, the reference passes (references, time), binds of
  the current set, sets added and binds that took the delivered path.

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
DESCRIPTOR_UPDATER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
TEXTURE_ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
RESOURCE_ARRAY = 'src/Ryujinx.Graphics.Vulkan/ResourceArray.cs'
LAYOUT_ENTRY = 'src/Ryujinx.Graphics.Vulkan/PipelineLayoutCacheEntry.cs'
SHADER_COLLECTION = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
# Build 631: the descriptor encoding files (template scratch, texture arrays written by range).
ENCODING_NAMES = [DESCRIPTOR_UPDATER, TEXTURE_ARRAY, RESOURCE_ARRAY, LAYOUT_ENTRY, SHADER_COLLECTION]
NAMES = [THREADED, PIPELINE_CACHE, SCHEDULER, PIPELINE_BASE, PIPELINE_FULL, WINDOW, MVK_INITIALIZATION, BUFFER_HOLDER, TEXTURE_STORAGE,
         *ENCODING_NAMES]

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
    /// Per-session descriptor encoding policy, set at launch from the title (Hogwarts Legacy only until a second title is
    /// measured). Off, both paths are the delivered ones; their uses and fallbacks are counted in the detail line.
    /// </summary>
    public static class EncodingPolicy
    {
        /// <summary>
        /// The template path of DescriptorSetUpdater.UpdateAndBind indexes its scratch arrays by binding number. Sized by
        /// binding (MaxTextureBindings * 2, MaxImageBindings * 2) instead of one stage, a fragment texture (binding 64-95),
        /// a buffer texture (32-63, and 64 more per stage) or a buffer image (16-31, and 32 more per stage) no longer throws
        /// IndexOutOfRangeException, caught by UpdateAndBindDescriptorSets, which then writes the set again one descriptor
        /// at a time. Off: the one-stage lengths, as delivered.
        /// </summary>
        public static bool BindingSizedDescriptorScratch { get; set; }

        /// <summary>
        /// A texture array keeps descriptor sets of its own and brings an idle one up to date by writing only the elements
        /// changed since it was last written, and each command buffer references its distinct views and samplers once
        /// (TextureArray). Off: any change releases the array's set and its next bind writes every element; every command
        /// buffer walks every element, as delivered.
        /// </summary>
        public static bool IncrementalArrayDescriptors { get; set; }
    }

    /// <summary>
    /// The render passes and the GPU in more detail, logged after each "Vulkan render stages" line: the render command that
    /// ended each pass begun again on the same framebuffer, the in-pass read barriers deferred and kept, the compute
    /// descriptor updates by program size (descriptors in its four main sets), the process's first-chance exceptions (the
    /// first four kinds once each), the descriptor template fallbacks, the texture array descriptor writes (EncodingPolicy),
    /// and the GPU's busy time (MetalGpuTimer). Render thread only, except the exception count.
    /// </summary>
    static class RenderDetail
    {
        public static long DeferredPassBarriers, FeedbackPassBarriers;
        // Template updates that threw and fell back to one descriptor at a time (DescriptorSetUpdater), by set: uniform,
        // storage, texture, image.
        public static readonly long[] TemplateFallbacks = new long[4];
        // Texture arrays (EncodingPolicy.IncrementalArrayDescriptors): sets written whole and their elements, sets brought up
        // to date by range with the elements written and those left as they were, the time of those writes, the passes that
        // reference the distinct views and samplers in a command buffer (references added, time), binds of the current set,
        // sets added, and binds that took the delivered path.
        public static long ArrayWholeWrites, ArrayWholeElements, ArrayRangeWrites, ArrayRangeElements, ArrayElementsKept;
        public static long ArrayWriteTicks, ArrayReferencePasses, ArrayReferencesAdded, ArrayReferenceTicks;
        public static long ArrayCurrentBinds, ArraySlotsAdded, ArrayFallbacks;
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

            text.Append("; descriptor template fallbacks ").Append(TemplateFallbacks[0]).Append('/').Append(TemplateFallbacks[1])
                .Append('/').Append(TemplateFallbacks[2]).Append('/').Append(TemplateFallbacks[3])
                .Append(" (uniform/storage/texture/image); texture arrays: whole writes ").Append(ArrayWholeWrites).Append(" (")
                .Append(ArrayWholeElements).Append(" elements), range writes ").Append(ArrayRangeWrites).Append(" (")
                .Append(ArrayRangeElements).Append(" elements, ").Append(ArrayElementsKept).Append(" kept), write time ")
                .Append(Ms(ArrayWriteTicks)).Append(" ms, reference passes ").Append(ArrayReferencePasses).Append(" (")
                .Append(ArrayReferencesAdded).Append(" references, ").Append(Ms(ArrayReferenceTicks)).Append(" ms), current binds ")
                .Append(ArrayCurrentBinds).Append(", sets added ").Append(ArraySlotsAdded).Append(", delivered path ")
                .Append(ArrayFallbacks);

            text.Append("; GPU ").Append(MetalGpuTimer.TakeWindow(frames));

            Array.Clear(_resumesAfter);
            Array.Clear(_computeTicks);
            Array.Clear(_computeCalls);
            Array.Clear(TemplateFallbacks);
            _largestCompute = 0;
            DeferredPassBarriers = FeedbackPassBarriers = 0;
            ArrayWholeWrites = ArrayWholeElements = ArrayRangeWrites = ArrayRangeElements = ArrayElementsKept = 0;
            ArrayWriteTicks = ArrayReferencePasses = ArrayReferencesAdded = ArrayReferenceTicks = 0;
            ArrayCurrentBinds = ArraySlotsAdded = ArrayFallbacks = 0;
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

# Build 631, descriptor encoding (EncodingPolicy, Hogwarts Legacy only). DescriptorSetUpdater: the template path's scratch
# arrays sized by binding number, and every template fallback counted.
SCRATCH_SIZES_OLD = '''            _textures = new DescriptorImageInfo[Constants.MaxTexturesPerStage];
            _images = new DescriptorImageInfo[Constants.MaxImagesPerStage];
            _bufferTextures = new BufferView[Constants.MaxTexturesPerStage];
            _bufferImages = new BufferView[Constants.MaxImagesPerStage];'''
SCRATCH_SIZES_NEW = '''            // The template path indexes these by binding number (EncodingPolicy.BindingSizedDescriptorScratch): sized like the
            // references. The other paths use their first elements only.
            _textures = new DescriptorImageInfo[Constants.MaxTextureBindings * 2];
            _images = new DescriptorImageInfo[Constants.MaxImageBindings * 2];
            _bufferTextures = new BufferView[Constants.MaxTextureBindings * 2];
            _bufferImages = new BufferView[Constants.MaxImageBindings * 2];'''
TEMPLATE_TEXTURES_OLD = '''                            Span<DescriptorImageInfo> textures = _textures;

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                ref var texture = ref textures[index];'''
TEMPLATE_TEXTURES_NEW = '''                            Span<DescriptorImageInfo> textures = TemplateScratch(_textures, Constants.MaxTexturesPerStage);

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                ref var texture = ref textures[index];'''
TEMPLATE_BUFFER_TEXTURES_OLD = '''                            Span<BufferView> bufferTextures = _bufferTextures;

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                bufferTextures[index] = '''
TEMPLATE_BUFFER_TEXTURES_NEW = '''                            Span<BufferView> bufferTextures = TemplateScratch(_bufferTextures, Constants.MaxTexturesPerStage);

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                bufferTextures[index] = '''
TEMPLATE_IMAGES_OLD = '''                            Span<DescriptorImageInfo> images = _images;

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                images[index].ImageView = '''
TEMPLATE_IMAGES_NEW = '''                            Span<DescriptorImageInfo> images = TemplateScratch(_images, Constants.MaxImagesPerStage);

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                images[index].ImageView = '''
TEMPLATE_BUFFER_IMAGES_OLD = '''                            Span<BufferView> bufferImages = _bufferImages;

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                bufferImages[index] = '''
TEMPLATE_BUFFER_IMAGES_NEW = '''                            Span<BufferView> bufferImages = TemplateScratch(_bufferImages, Constants.MaxImagesPerStage);

                            for (int i = 0; i < count; i++)
                            {
                                int index = binding + i;
                                bufferImages[index] = '''
UNIFORM_FALLBACK_OLD = '''                    catch
                    {
                        UpdateAndBind(cbs, PipelineBase.UniformSetIndex, pbp);
                    }'''
UNIFORM_FALLBACK_NEW = '''                    catch
                    {
                        RenderDetail.TemplateFallbacks[0]++;
                        UpdateAndBind(cbs, PipelineBase.UniformSetIndex, pbp);
                    }'''
STORAGE_FALLBACK_OLD = '''                catch
                {
                    UpdateAndBind(cbs, PipelineBase.StorageSetIndex, pbp);
                }'''
STORAGE_FALLBACK_NEW = '''                catch
                {
                    RenderDetail.TemplateFallbacks[1]++;
                    UpdateAndBind(cbs, PipelineBase.StorageSetIndex, pbp);
                }'''
TEXTURE_FALLBACK_OLD = '''                        catch
                        {
                            UpdateAndBind(cbs, PipelineBase.TextureSetIndex, pbp);
                        }'''
TEXTURE_FALLBACK_NEW = '''                        catch
                        {
                            RenderDetail.TemplateFallbacks[2]++;
                            UpdateAndBind(cbs, PipelineBase.TextureSetIndex, pbp);
                        }'''
IMAGE_FALLBACK_OLD = '''                catch
                {
                    UpdateAndBind(cbs, PipelineBase.ImageSetIndex, pbp);
                }'''
IMAGE_FALLBACK_NEW = '''                catch
                {
                    RenderDetail.TemplateFallbacks[3]++;
                    UpdateAndBind(cbs, PipelineBase.ImageSetIndex, pbp);
                }'''
# The delivered line is "catch" followed by a space; kept as it is (editors strip trailing spaces from this file).
IMAGE_FALLBACK_OLD = IMAGE_FALLBACK_OLD.replace('catch\n', 'catch \n', 1)
IMAGE_FALLBACK_NEW = IMAGE_FALLBACK_NEW.replace('catch\n', 'catch \n', 1)
SCRATCH_HELPER_OLD = '''        private void SignalDirty(DirtyFlags flag)
'''
SCRATCH_HELPER_NEW = '''        // EncodingPolicy.BindingSizedDescriptorScratch: the template path indexes its scratch by binding number. Off, the
        // one-stage lengths, as delivered: a binding past them throws, and UpdateAndBindDescriptorSets falls back.
        private static Span<T> TemplateScratch<T>(T[] scratch, int deliveredLength)
        {
            return EncodingPolicy.BindingSizedDescriptorScratch ? scratch : scratch.AsSpan(0, deliveredLength);
        }

        private void SignalDirty(DirtyFlags flag)
'''
DESCRIPTOR_UPDATER_HUNKS = [(SCRATCH_SIZES_OLD, SCRATCH_SIZES_NEW), (TEMPLATE_TEXTURES_OLD, TEMPLATE_TEXTURES_NEW),
                            (TEMPLATE_BUFFER_TEXTURES_OLD, TEMPLATE_BUFFER_TEXTURES_NEW), (TEMPLATE_IMAGES_OLD, TEMPLATE_IMAGES_NEW),
                            (TEMPLATE_BUFFER_IMAGES_OLD, TEMPLATE_BUFFER_IMAGES_NEW), (UNIFORM_FALLBACK_OLD, UNIFORM_FALLBACK_NEW),
                            (STORAGE_FALLBACK_OLD, STORAGE_FALLBACK_NEW), (TEXTURE_FALLBACK_OLD, TEXTURE_FALLBACK_NEW),
                            (IMAGE_FALLBACK_OLD, IMAGE_FALLBACK_NEW), (SCRATCH_HELPER_OLD, SCRATCH_HELPER_NEW)]

# TextureArray (EncodingPolicy.IncrementalArrayDescriptors, texture arrays only): every change recorded by range; the
# element values, the distinct references and descriptor sets of the array's own brought up to date from those ranges.
# The anchor opens with the line break before it, so that an altered first line no longer matches.
ARRAY_USINGS_OLD = '''
using System;
using System.Collections.Generic;
'''
ARRAY_USINGS_NEW = '''
using System;
using System.Collections.Generic;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
'''
ARRAY_FIELDS_OLD = '''        private readonly bool _isBuffer;

        public TextureArray(VulkanRenderer gd, int size, bool isBuffer)'''
ARRAY_FIELDS_NEW = '''        private readonly bool _isBuffer;

        // EncodingPolicy.IncrementalArrayDescriptors (texture arrays, not buffer arrays). Build 629, Hogwarts Legacy: the
        // full-bindless arrays have 524288 elements, a delta update of the GPU thread changes about 40 of them, and each one
        // cost a whole descriptor set write (7.7 ms per update). Every change is recorded by range in _changes; the element
        // values, the distinct views and samplers referenced, and the descriptor sets the array keeps (ArraySlot) are brought
        // up to date from those ranges. A consumer older than the log's floor, or with more than a quarter of the elements
        // to write, is brought up to date whole. A delta pass sends one range per run of changed elements (up to about 40),
        // and a set waits for the command buffers that use it: the log keeps the ranges of many passes.
        private const int LargeChange = 4096;
        private const int MaxChangeLog = 1024;
        private const int MaxSlots = 8;

        private readonly record struct ChangeRange(long Sequence, int Start, int Count);

        private sealed class ArraySlot
        {
            public ShaderCollection Program;
            public int SetIndex;
            public int CacheIndex;
            public int Binding;
            public DescriptorType Type;
            public DescriptorSet[] Sets;
            public long Sequence;
        }

        private readonly bool _incremental;
        private readonly List<ChangeRange> _changes;
        private readonly List<(int Start, int End)> _runs;
        private readonly List<ArraySlot> _slots;
        private ArraySlot _currentSlot;
        private long _changeSequence;
        private long _changeFloor;
        private long _valuesSequence = -1;
        private Dictionary<Auto<DisposableImageView>, int> _viewReferences;
        private Dictionary<Auto<DisposableSampler>, int> _samplerReferences;
        private bool _referencesInvalid = true;
        private int _referencesCommandBuffer = -1;
        private int _referencesSubmission;
        private long _referencesSequence = -1;
        private Auto<DisposableImageView> _dummyView;
        private Auto<DisposableSampler> _dummySampler;

        public TextureArray(VulkanRenderer gd, int size, bool isBuffer)'''
ARRAY_CONSTRUCTOR_OLD = '''            _isBuffer = isBuffer;
        }
'''
ARRAY_CONSTRUCTOR_NEW = '''            _isBuffer = isBuffer;
            _incremental = EncodingPolicy.IncrementalArrayDescriptors && !isBuffer;

            if (_incremental)
            {
                _changes = [];
                _runs = [];
                _slots = [];
            }
        }
'''
ARRAY_SAMPLERS_OLD = '''        public void SetSamplers(int index, ISampler[] samplers)
        {
            for (int i = 0; i < samplers.Length; i++)
            {
                try
                {
                    ISampler sampler = samplers[i];

                    if (sampler is SamplerHolder samplerHolder)
                    {
                        _textureRefs[index + i].Sampler = samplerHolder.GetSampler();
                    }
                    else
                    {
                        _textureRefs[index + i].Sampler = default;
                    }
                }
                catch
                 {
                    _textureRefs[index + i].Sampler = default;
                }
            }

            SetDirty(storageChanged: false);
        }'''
ARRAY_SAMPLERS_NEW = '''        public void SetSamplers(int index, ISampler[] samplers)
        {
            // EncodingPolicy.IncrementalArrayDescriptors: a small update keeps the distinct samplers counted, a large one has
            // them counted again at the next use.
            bool counted = _incremental && !_referencesInvalid && samplers.Length <= LargeChange;

            for (int i = 0; i < samplers.Length; i++)
            {
                Auto<DisposableSampler> previous = counted ? _textureRefs[index + i].Sampler : null;

                try
                {
                    ISampler sampler = samplers[i];

                    if (sampler is SamplerHolder samplerHolder)
                    {
                        _textureRefs[index + i].Sampler = samplerHolder.GetSampler();
                    }
                    else
                    {
                        _textureRefs[index + i].Sampler = default;
                    }
                }
                catch
                 {
                    _textureRefs[index + i].Sampler = default;
                }

                if (counted)
                {
                    SwapReference(_samplerReferences, previous, _textureRefs[index + i].Sampler);
                }
            }

            if (_incremental)
            {
                _referencesInvalid |= !counted;
                RecordChange(index, samplers.Length);
            }

            SetDirty(storageChanged: false);
        }'''
# The delivered "try" and the brace before "catch" end with a space; kept as they are.
ARRAY_SAMPLERS_OLD, ARRAY_SAMPLERS_NEW = (text.replace('                try\n', '                try \n', 1).replace(
    '                }\n                catch\n', '                } \n                catch\n', 1) for text in (ARRAY_SAMPLERS_OLD, ARRAY_SAMPLERS_NEW))
ARRAY_TEXTURES_OLD = '''        public void SetTextures(int index, ITexture[] textures)
        {
            bool storageChanged = false;

            for (int i = 0; i < textures.Length; i++)
            {
                ITexture texture = textures[i];

                if (texture is TextureBuffer textureBuffer)
                {
                    _bufferTextureRefs[index + i] = textureBuffer;
                }
                else if (texture is TextureView view)
                {
                    storageChanged |= !ReferenceEquals(_textureRefs[index + i].Storage, view.Storage);
                    _textureRefs[index + i].Storage = view.Storage;
                    _textureRefs[index + i].View = view.GetImageView();
                }
                else if (!_isBuffer)
                {
                    storageChanged |= _textureRefs[index + i].Storage != null;
                    _textureRefs[index + i].Storage = null;
                    _textureRefs[index + i].View = default;
                }
                else
                {
                    _bufferTextureRefs[index + i] = null;
                }
            }

            SetDirty(storageChanged);
        }'''
ARRAY_TEXTURES_NEW = '''        public void SetTextures(int index, ITexture[] textures)
        {
            bool storageChanged = false;
            // EncodingPolicy.IncrementalArrayDescriptors: a small update keeps the distinct views counted, a large one has them
            // counted again at the next use.
            bool counted = _incremental && !_referencesInvalid && textures.Length <= LargeChange;

            for (int i = 0; i < textures.Length; i++)
            {
                ITexture texture = textures[i];

                if (texture is TextureBuffer textureBuffer)
                {
                    _bufferTextureRefs[index + i] = textureBuffer;
                }
                else if (texture is TextureView view)
                {
                    storageChanged |= !ReferenceEquals(_textureRefs[index + i].Storage, view.Storage);
                    _textureRefs[index + i].Storage = view.Storage;
                    Auto<DisposableImageView> imageView = view.GetImageView();

                    if (counted)
                    {
                        SwapReference(_viewReferences, _textureRefs[index + i].View, imageView);
                    }

                    _textureRefs[index + i].View = imageView;
                }
                else if (!_isBuffer)
                {
                    storageChanged |= _textureRefs[index + i].Storage != null;
                    _textureRefs[index + i].Storage = null;

                    if (counted)
                    {
                        SwapReference(_viewReferences, _textureRefs[index + i].View, null);
                    }

                    _textureRefs[index + i].View = default;
                }
                else
                {
                    _bufferTextureRefs[index + i] = null;
                }
            }

            if (_incremental)
            {
                _referencesInvalid |= !counted;
                RecordChange(index, textures.Length);
            }

            SetDirty(storageChanged);
        }'''
ARRAY_INFOS_OLD = '''        public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView dummyTexture, SamplerHolder dummySampler)
        {
'''
ARRAY_INFOS_NEW = '''        public ReadOnlySpan<DescriptorImageInfo> GetImageInfos(VulkanRenderer gd, CommandBufferScoped cbs, TextureView dummyTexture, SamplerHolder dummySampler)
        {
            if (_incremental)
            {
                // The references first: a destroyed view or sampler found there is a change the values then take.
                AddReferences(cbs, dummyTexture, dummySampler);
                RefreshValues(dummyTexture, dummySampler);

                return _textures;
            }

'''
ARRAY_SETS_OLD = '''            SamplerHolder dummySampler)
        {
            if (TryGetCachedDescriptorSets(cbs, program, setIndex, out DescriptorSet[] sets))
            {'''
ARRAY_SETS_NEW = '''            SamplerHolder dummySampler)
        {
            if (_incremental)
            {
                DescriptorSet[] own = GetOwnDescriptorSets(device, cbs, program, setIndex, dummyTexture, dummySampler);

                if (own != null)
                {
                    return own;
                }
            }

            if (TryGetCachedDescriptorSets(cbs, program, setIndex, out DescriptorSet[] sets))
            {'''
ARRAY_METHODS_OLD = '''            templateUpdater.Commit(_gd, device, sets[0]);

            return sets;
        }
    }
}'''
ARRAY_METHODS_NEW = '''            templateUpdater.Commit(_gd, device, sets[0]);

            return sets;
        }

        private void RecordChange(int start, int count)
        {
            if (count <= 0)
            {
                return;
            }

            _changes.Add(new ChangeRange(++_changeSequence, start, count));

            if (_changes.Count > MaxChangeLog)
            {
                // The oldest half is dropped: a consumer older than the floor is brought up to date whole.
                int dropped = _changes.Count / 2;
                _changeFloor = _changes[dropped - 1].Sequence;
                _changes.RemoveRange(0, dropped);
            }
        }

        /// <summary>
        /// The element ranges changed after the given sequence, merged, in _runs; returns their element count, or -1 when the
        /// log no longer holds them all.
        /// </summary>
        private int GatherChanges(long since)
        {
            _runs.Clear();

            if (since < _changeFloor)
            {
                return -1;
            }

            // The log is in sequence order: only its tail after the given sequence is read.
            for (int index = _changes.Count - 1; index >= 0 && _changes[index].Sequence > since; index--)
            {
                ChangeRange change = _changes[index];
                _runs.Add((change.Start, change.Start + change.Count));
            }

            if (_runs.Count > 1)
            {
                _runs.Sort(static (a, b) => a.Start.CompareTo(b.Start));

                int write = 0;

                for (int read = 1; read < _runs.Count; read++)
                {
                    if (_runs[read].Start <= _runs[write].End)
                    {
                        if (_runs[read].End > _runs[write].End)
                        {
                            _runs[write] = (_runs[write].Start, _runs[read].End);
                        }
                    }
                    else
                    {
                        _runs[++write] = _runs[read];
                    }
                }

                _runs.RemoveRange(write + 1, _runs.Count - write - 1);
            }

            int elements = 0;

            foreach ((int start, int end) in _runs)
            {
                elements += end - start;
            }

            return elements;
        }

        private static void SwapReference<T>(Dictionary<Auto<T>, int> counts, Auto<T> previous, Auto<T> current) where T : IDisposable
        {
            if (ReferenceEquals(previous, current))
            {
                return;
            }

            if (previous != null)
            {
                ref int count = ref CollectionsMarshal.GetValueRefOrNullRef(counts, previous);

                if (!Unsafe.IsNullRef(ref count) && --count <= 0)
                {
                    counts.Remove(previous);
                }
            }

            if (current != null)
            {
                CollectionsMarshal.GetValueRefOrAddDefault(counts, current, out _)++;
            }
        }

        /// <summary>
        /// Counts the distinct views and samplers the elements hold, one dictionary entry per run of equal elements. A
        /// destroyed view or sampler is left out, and its elements are recorded as changed: they take the dummy, written
        /// again in every set that still holds the destroyed handle.
        /// </summary>
        private void RebuildReferences()
        {
            (_viewReferences ??= new Dictionary<Auto<DisposableImageView>, int>()).Clear();
            (_samplerReferences ??= new Dictionary<Auto<DisposableSampler>, int>()).Clear();

            for (int i = 0; i < _textureRefs.Length;)
            {
                ref TextureRef refs = ref _textureRefs[i];
                int run = 1;

                while (i + run < _textureRefs.Length && _textureRefs[i + run].View == refs.View && _textureRefs[i + run].Sampler == refs.Sampler)
                {
                    run++;
                }

                bool destroyed = false;

                if (refs.View != null)
                {
                    if (refs.View.GetUnsafe().Value.Handle != 0)
                    {
                        CollectionsMarshal.GetValueRefOrAddDefault(_viewReferences, refs.View, out _) += run;
                    }
                    else
                    {
                        destroyed = true;
                    }
                }

                if (refs.Sampler != null)
                {
                    if (refs.Sampler.GetUnsafe().Value.Handle != 0)
                    {
                        CollectionsMarshal.GetValueRefOrAddDefault(_samplerReferences, refs.Sampler, out _) += run;
                    }
                    else
                    {
                        destroyed = true;
                    }
                }

                if (destroyed)
                {
                    RecordChange(i, run);
                }

                i += run;
            }

            _referencesInvalid = false;
        }

        /// <summary>
        /// The command buffer references every distinct view and sampler of the array and the dummies, once per command
        /// buffer and change: what the delivered walk of every element added.
        /// </summary>
        private void AddReferences(CommandBufferScoped cbs, TextureView dummyTexture, SamplerHolder dummySampler)
        {
            int submission = _gd.CommandBufferPool.GetSubmissionCount(cbs.CommandBufferIndex);

            if (!_referencesInvalid && cbs.CommandBufferIndex == _referencesCommandBuffer && submission == _referencesSubmission &&
                _referencesSequence == _changeSequence)
            {
                return;
            }

            long start = RenderStageTimer.Now();

            if (_referencesInvalid)
            {
                RebuildReferences();
            }

            bool destroyed = false;

            foreach (Auto<DisposableImageView> view in _viewReferences.Keys)
            {
                destroyed |= view.Get(cbs).Value.Handle == 0;
            }

            foreach (Auto<DisposableSampler> sampler in _samplerReferences.Keys)
            {
                destroyed |= sampler.Get(cbs).Value.Handle == 0;
            }

            (_dummyView ??= dummyTexture.GetImageView()).Get(cbs);
            (_dummySampler ??= dummySampler.GetSampler()).Get(cbs);

            RenderDetail.ArrayReferencePasses++;
            RenderDetail.ArrayReferencesAdded += _viewReferences.Count + _samplerReferences.Count;

            if (destroyed)
            {
                // A view or sampler destroyed while the array still holds it: counted again without it, and its elements,
                // recorded as changed, take the dummy (the others were referenced above).
                RebuildReferences();
            }

            _referencesCommandBuffer = cbs.CommandBufferIndex;
            _referencesSubmission = submission;
            _referencesSequence = _changeSequence;
            RenderDetail.ArrayReferenceTicks += RenderStageTimer.Now() - start;
        }

        private void RefreshValues(TextureView dummyTexture, SamplerHolder dummySampler)
        {
            if (_valuesSequence == _changeSequence)
            {
                return;
            }

            _dummyView ??= dummyTexture.GetImageView();
            _dummySampler ??= dummySampler.GetSampler();

            int elements = GatherChanges(_valuesSequence);

            if (elements < 0 || elements > _textures.Length / 4)
            {
                ResolveValues(0, _textures.Length);
            }
            else
            {
                foreach ((int start, int end) in _runs)
                {
                    ResolveValues(start, end);
                }
            }

            _valuesSequence = _changeSequence;
        }

        /// <summary>
        /// The descriptor values of the elements of [start, end), as the delivered walk resolves them, without command buffer
        /// references (AddReferences adds them).
        /// </summary>
        private void ResolveValues(int start, int end)
        {
            ImageView dummyView = _dummyView.GetUnsafe().Value;
            Silk.NET.Vulkan.Sampler dummySampler = _dummySampler.GetUnsafe().Value;
            Span<DescriptorImageInfo> textures = _textures;

            for (int i = start; i < end; i++)
            {
                ref TextureRef refs = ref _textureRefs[i];

                if (i > start && _textureRefs[i - 1].View == refs.View && _textureRefs[i - 1].Sampler == refs.Sampler)
                {
                    textures[i] = textures[i - 1];

                    continue;
                }

                ImageView view = refs.View?.GetUnsafe().Value ?? default;
                Silk.NET.Vulkan.Sampler sampler = refs.Sampler?.GetUnsafe().Value ?? default;

                textures[i] = new DescriptorImageInfo
                {
                    ImageLayout = ImageLayout.General,
                    ImageView = view.Handle != 0 ? view : dummyView,
                    Sampler = sampler.Handle != 0 ? sampler : dummySampler,
                };
            }
        }

        /// <summary>
        /// An up-to-date descriptor set of the array's own: the current one, or an idle one brought up to date by writing the
        /// elements changed since it was written (the most recent first, the fewest to write), or a new one written whole.
        /// Null when the set is not one array binding of this array's length, or when every set of the array is still
        /// pending: the delivered path then writes a set whole.
        /// </summary>
        private DescriptorSet[] GetOwnDescriptorSets(
            Device device,
            CommandBufferScoped cbs,
            ShaderCollection program,
            int setIndex,
            TextureView dummyTexture,
            SamplerHolder dummySampler)
        {
            ResourceBindingSegment[] segments = program.BindingSegments[setIndex];

            if (segments.Length != 1 || !segments[0].IsArray || segments[0].Count != _textures.Length)
            {
                RenderDetail.ArrayFallbacks++;

                return null;
            }

            AddReferences(cbs, dummyTexture, dummySampler);
            RefreshValues(dummyTexture, dummySampler);

            int binding = segments[0].Binding;
            DescriptorType type = segments[0].Type.Convert();
            ArraySlot current = _currentSlot;

            if (current != null && current.Sequence == _changeSequence && current.Binding == binding && current.Type == type)
            {
                current.Program.UpdateManualDescriptorSetCollectionOwnership(cbs, current.SetIndex, current.CacheIndex);
                RenderDetail.ArrayCurrentBinds++;

                return current.Sets;
            }

            ArraySlot slot = null;

            foreach (ArraySlot candidate in _slots)
            {
                if (candidate.Binding == binding && candidate.Type == type && (slot == null || candidate.Sequence > slot.Sequence) &&
                    candidate.Program.IsManualDescriptorSetCollectionIdle(candidate.SetIndex, candidate.CacheIndex))
                {
                    slot = candidate;
                }
            }

            long start = RenderStageTimer.Now();

            if (slot == null)
            {
                if (_slots.Count >= MaxSlots)
                {
                    RenderDetail.ArrayFallbacks++;

                    return null;
                }

                slot = new ArraySlot
                {
                    Program = program,
                    SetIndex = setIndex,
                    Binding = binding,
                    Type = type,
                    Sequence = -1,
                };

                slot.Sets = program.GetNewManualDescriptorSetCollection(cbs, setIndex, out slot.CacheIndex).Get(cbs).GetSets();
                _slots.Add(slot);
                RenderDetail.ArraySlotsAdded++;
            }
            else
            {
                slot.Program.UpdateManualDescriptorSetCollectionOwnership(cbs, slot.SetIndex, slot.CacheIndex);
            }

            int elements = GatherChanges(slot.Sequence);

            if (elements < 0 || elements > _textures.Length / 4)
            {
                _runs.Clear();
                _runs.Add((0, _textures.Length));
                RenderDetail.ArrayWholeWrites++;
                RenderDetail.ArrayWholeElements += _textures.Length;
            }
            else
            {
                RenderDetail.ArrayRangeWrites++;
                RenderDetail.ArrayRangeElements += elements;
                RenderDetail.ArrayElementsKept += _textures.Length - elements;
            }

            WriteRuns(device, slot);
            RenderDetail.ArrayWriteTicks += RenderStageTimer.Now() - start;
            slot.Sequence = _changeSequence;
            _currentSlot = slot;

            return slot.Sets;
        }

        /// <summary>
        /// Writes the elements of _runs into the slot's set, one descriptor write per run, at most 16 per call.
        /// </summary>
        private unsafe void WriteRuns(Device device, ArraySlot slot)
        {
            const int Batch = 16;
            WriteDescriptorSet* writes = stackalloc WriteDescriptorSet[Batch];
            int pending = 0;

            fixed (DescriptorImageInfo* pTextures = _textures)
            {
                foreach ((int start, int end) in _runs)
                {
                    writes[pending++] = new WriteDescriptorSet
                    {
                        SType = StructureType.WriteDescriptorSet,
                        DstSet = slot.Sets[0],
                        DstBinding = (uint)slot.Binding,
                        DstArrayElement = (uint)start,
                        DescriptorCount = (uint)(end - start),
                        DescriptorType = slot.Type,
                        PImageInfo = pTextures + start,
                    };

                    if (pending == Batch)
                    {
                        _gd.Api.UpdateDescriptorSets(device, (uint)pending, writes, 0, (CopyDescriptorSet*)null);
                        pending = 0;
                    }
                }

                if (pending != 0)
                {
                    _gd.Api.UpdateDescriptorSets(device, (uint)pending, writes, 0, (CopyDescriptorSet*)null);
                }
            }
        }

        protected override void ReleaseOwnDescriptorSets()
        {
            if (_slots == null)
            {
                return;
            }

            foreach (ArraySlot slot in _slots)
            {
                slot.Program.ReleaseManualDescriptorSetCollection(slot.SetIndex, slot.CacheIndex);
            }

            _slots.Clear();
            _currentSlot = null;
        }
    }
}'''
TEXTURE_ARRAY_HUNKS = [(ARRAY_USINGS_OLD, ARRAY_USINGS_NEW), (ARRAY_FIELDS_OLD, ARRAY_FIELDS_NEW),
                       (ARRAY_CONSTRUCTOR_OLD, ARRAY_CONSTRUCTOR_NEW), (ARRAY_SAMPLERS_OLD, ARRAY_SAMPLERS_NEW),
                       (ARRAY_TEXTURES_OLD, ARRAY_TEXTURES_NEW), (ARRAY_INFOS_OLD, ARRAY_INFOS_NEW), (ARRAY_SETS_OLD, ARRAY_SETS_NEW),
                       (ARRAY_METHODS_OLD, ARRAY_METHODS_NEW)]

# ResourceArray: the sets an array keeps of its own are released with it.
RESOURCE_DISPOSE_OLD = '''        public void Dispose()
        {
            ReleaseDescriptorSet();
        }'''
RESOURCE_DISPOSE_NEW = '''        public void Dispose()
        {
            ReleaseDescriptorSet();
            ReleaseOwnDescriptorSets();
        }

        /// <summary>
        /// Releases the descriptor sets an array keeps of its own (TextureArray, EncodingPolicy.IncrementalArrayDescriptors).
        /// </summary>
        protected virtual void ReleaseOwnDescriptorSets()
        {
        }'''
RESOURCE_ARRAY_HUNKS = [(RESOURCE_DISPOSE_OLD, RESOURCE_DISPOSE_NEW)]

# PipelineLayoutCacheEntry and ShaderCollection: whether a manual set is bound in no pending command buffer.
LAYOUT_IDLE_OLD = '''        private static Span<DescriptorPoolSize> GetDescriptorPoolSizes('''
LAYOUT_IDLE_NEW = '''        /// <summary>
        /// Whether a manual descriptor set is bound in no command buffer still pending, the completed ones accounted first: it
        /// can then be written (TextureArray, EncodingPolicy.IncrementalArrayDescriptors).
        /// </summary>
        public bool IsManualDescriptorSetCollectionIdle(int setIndex, int cacheIndex)
        {
            FreeCompletedManualDescriptorSets();

            return CollectionsMarshal.AsSpan(_manualDsCache[setIndex])[cacheIndex].CbRefMask == 0;
        }

        private static Span<DescriptorPoolSize> GetDescriptorPoolSizes('''
LAYOUT_ENTRY_HUNKS = [(LAYOUT_IDLE_OLD, LAYOUT_IDLE_NEW)]
SHADER_IDLE_OLD = '''        public void ReleaseManualDescriptorSetCollection(int setIndex, int cacheIndex)
        {
            _plce.ReleaseManualDescriptorSetCollection(setIndex, cacheIndex);
        }'''
SHADER_IDLE_NEW = '''        public void ReleaseManualDescriptorSetCollection(int setIndex, int cacheIndex)
        {
            _plce.ReleaseManualDescriptorSetCollection(setIndex, cacheIndex);
        }

        public bool IsManualDescriptorSetCollectionIdle(int setIndex, int cacheIndex)
        {
            return _plce.IsManualDescriptorSetCollectionIdle(setIndex, cacheIndex);
        }'''
SHADER_COLLECTION_HUNKS = [(SHADER_IDLE_OLD, SHADER_IDLE_NEW)]
ENCODING_HUNKS = [(DESCRIPTOR_UPDATER, DESCRIPTOR_UPDATER_HUNKS), (TEXTURE_ARRAY, TEXTURE_ARRAY_HUNKS),
                  (RESOURCE_ARRAY, RESOURCE_ARRAY_HUNKS), (LAYOUT_ENTRY, LAYOUT_ENTRY_HUNKS),
                  (SHADER_COLLECTION, SHADER_COLLECTION_HUNKS)]
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
    for relative, hunks in ENCODING_HUNKS:
        apply_hunks(source / relative, hunks)


def apply(source):
    source = Path(source)
    apply_threaded(source / THREADED)
    apply_pipeline_budget(source / PIPELINE_CACHE)
    apply_scheduler(source / SCHEDULER)
    apply_render_stages(source)
    return NAMES
