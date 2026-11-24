"""No pipeline is compiled on the render thread for a draw that may skip, and what is known in advance is built first.

IPA 821, 22 November 2026 (private journals; counts and durations only), Hogwarts Legacy, 174 s of play: gaps of
100 ms or more are 36 % of the time (58 % on IPA 820). The render thread spends 24 s obtaining pipelines for draws and
16 s for compute dispatches; 19 creations a minute of 50 ms or more run on it (582 ms on average); the driver compiles
2 647 shader libraries at 59 ms each (up to 3.35 s) and 2 759 Metal pipeline states at 17 ms; 185 compute pipelines
take 39.1 s. The variant replay built 2 of 2 028 recorded states, its two scheduled compiles in the queue until the
close; "ready before their first draw" stays 0. Super Smash Bros. Ultimate: 7 ms per library, 3 % of gaps.

Causes, in the engine:
- A draw allowed to skip (async compile) first created its pipeline itself on the main cache with
  FAIL_ON_PIPELINE_COMPILE_REQUIRED (adapt "non-blocking creation"). In MoltenVK that flag only avoids the SPIR-V to
  MSL conversion: the cached library is compiled by Metal (at its first use since the recipe's ninth part) and so is
  the pipeline state, on the render thread. The draw that could have skipped a frame stalled the frame instead.
- The scheduler's one background worker takes the high priority queue, then the low priority one in order. The
  warm-ups of the 2 116 programs loaded from the disk cache are queued there at launch; the replays of the states the
  last sessions drew (PipelineVariantJournal) are queued behind them, and the warm-up of a cached compute program,
  which no dispatch can skip, waits among them too. A dispatch of such a program did not join that queued warm-up
  (only a program translated during play did): it created the same pipeline itself.

Change, for every title:
- PipelineBase.CreatePipeline: a skippable draw no longer creates on the render thread. Its compile is queued as
  before (demanded: the demand thread, or a worker, takes it at once) and the draw waits for it only within a small
  allowance (SkippableDrawWait: one eighth of the elapsed time, 4 ms at most), so a pipeline that is quick to obtain
  is still drawn in its frame; otherwise the draw skips, as a draw whose state the main cache lacks always did.
  The wait is a plain bounded wait on the queued task: it promotes nothing.
- BackgroundCompilationScheduler: a prebuild queue between the high and the low priority ones. The variant replays
  go there, ahead of the cached programs' speculative warm-ups. Everything else is as before: demanded work first,
  the demand thread's lanes, cancellation at the guest's stop and at Dispose (the prebuild queue is drained with the
  others).
- VulkanRenderer.CreateProgram: a compute program loaded from the cache compiles at high priority (modules and
  warm-up), like a program translated during play. ShaderCollection.TryWaitForBackgroundComputePipeline: a dispatch
  joins the queued warm-up of any program that has one for its key (promoted to the demand thread) instead of
  creating the same pipeline a second time; without one, or if it fails, the dispatch creates it as before.
- The render-stage line gains the short waits (count, obtained in time, milliseconds).
- ShaderCollection.CheckProgramLink: a blocking check of a program whose warm-up is not detached (translated during play
  with async compilation) demands its background compilation before waiting for it. IPA 824-829, Hogwarts Legacy, 24
  November 2026 (private journals; counts and durations only): with the iOS Metal compiler cache cold, each cached
  compute warm-up took about 0.5 s on the one worker, so 150 to 500 of them were still queued high when the game
  translated new programs at 22 s (28 shader calls, 32 MiB). SetProgram of such a program (one that writes memory
  cannot bind incomplete) waited in ProgramQueue.WaitForProgram for its warm-up, queued behind them and never demanded:
  the render thread stayed in one command at under 1 % CPU, the GPU thread waited for it, the demand thread idled, and
  Unreal's heartbeat aborted the game 25 s later. With the cache warm (IPA 822) the queue was empty by then. A cached
  program, and a play-time one of a title without async compilation, has a detached warm-up and never reaches this wait.

Not changed: a draw that must not skip (transform feedback, targets not regenerated every frame, titles without
async compile such as SSBU) waits or creates as before; what a worker compiles and where; the pipeline caches; the
replay's own bounds. Not measured on an iPhone. Fail closed on drift: each file must be the Core c82639d5 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': 'bbf8b90d238e19bad3bdb1aeac1d01f5e4d99e412b98fc6dcb8b3e650832e6b4',
    'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs': 'a1772a3268fd1ca5b7b48de266bd3aac1c7c01851f9c743eaa1f75ca8dc4cd76',
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': 'ed428f163c2bedd653e9969b448056ad7b80b4574e1730aff9a0e9d73e212f0a',
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': 'cb496e96dbb780a5a22124d2694499ee1cd9936bb9eaf7cedf75f73a1e76d0f7',
}

PIPELINE_PAIRS = (
    ('''                        if (pipeline == null &&
                            canSkipForBackgroundCompile &&
                            Gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation)
                        {
                            pipeline = _newState.CreateGraphicsPipeline(
                                Gd,
                                Device,
                                _program,
                                PipelineCache,
                                renderPass.Get(Cbs).Value,
                                throwOnError: false,
                                cachePipelineFailure: false,
                                failOnCompileRequired: true);
                        }

''', '''                        // RewindBox (adapt_render_thread_compile_relief): a draw that may skip no longer creates its
                        // pipeline here. The driver compiled the cached library and the Metal state on this thread
                        // whatever the "fail on compile required" flag (IPA 821, Hogwarts Legacy: 24 s of 174 s).

'''),
    ('''                            if (!waitForBackgroundGraphicsPipeline)
                            {
                                _renderPassHadSkippedDraw = true;
                                RenderStageTimer.AsyncSkips++; // RewindBox (adapt_pipeline_failure_identity)
                                RenderStageTimer.AsyncQueuedSkips++; // RewindBox (adapt_queued_variant_record)
                                return false;
                            }

                            if (!_program.TryWaitForBackgroundGraphicsPipeline(
''', '''                            if (!waitForBackgroundGraphicsPipeline)
                            {
                                // RewindBox (adapt_render_thread_compile_relief): the compile is queued (demanded). Wait
                                // for it within the allowance, so a pipeline that is quick to obtain is drawn in its frame;
                                // otherwise skip. Nothing is compiled on this thread.
                                int shortWaitMs = SkippableDrawWait.Take();

                                if (shortWaitMs > 0)
                                {
                                    long shortWaitStart = RenderStageTimer.Now();
                                    _program.TryWaitBrieflyForQueuedGraphicsPipeline(ref key, shortWaitMs, out pipeline);
                                    SkippableDrawWait.Spend(RenderStageTimer.Now() - shortWaitStart, pipeline != null);
                                }

                                if (pipeline == null)
                                {
                                    _renderPassHadSkippedDraw = true;
                                    RenderStageTimer.AsyncSkips++; // RewindBox (adapt_pipeline_failure_identity)
                                    RenderStageTimer.AsyncQueuedSkips++; // RewindBox (adapt_queued_variant_record)
                                    return false;
                                }
                            }
                            else if (!_program.TryWaitForBackgroundGraphicsPipeline(
'''),
    ('''                DrawWaitCounters.TakeText(); // RewindBox (adapt_draw_wait_lanes)
''', '''                DrawWaitCounters.TakeText() + // RewindBox (adapt_draw_wait_lanes)
                SkippableDrawWait.TakeText(); // RewindBox (adapt_render_thread_compile_relief)
'''),
)

SCHEDULER_PAIRS = (
    ('''    sealed class BackgroundCompilationScheduler : IDisposable
    {
''', '''    /// <summary>
    /// RewindBox (adapt_render_thread_compile_relief): how long a draw that may skip waits for its queued compile before
    /// it skips. The allowance grows by one eighth of the elapsed time and holds 4 ms at most: a burst of new states
    /// costs a frame a few milliseconds, never a compilation. Render thread only; the counters are for the journal.
    /// </summary>
    static class SkippableDrawWait
    {
        internal const int CapMs = 4;
        internal const int ElapsedShare = 8;

        private static long _allowanceTicks;
        private static long _lastTicks;
        private static long _waits, _obtained, _waitTicks;

        public static int Take()
        {
            long now = System.Diagnostics.Stopwatch.GetTimestamp();
            long cap = CapMs * System.Diagnostics.Stopwatch.Frequency / 1000;

            if (_lastTicks == 0 || now - _lastTicks >= cap * ElapsedShare)
            {
                _allowanceTicks = cap;
            }
            else
            {
                _allowanceTicks = Math.Min(cap, _allowanceTicks + (now - _lastTicks) / ElapsedShare);
            }

            _lastTicks = now;

            return (int)(_allowanceTicks * 1000 / System.Diagnostics.Stopwatch.Frequency);
        }

        public static void Spend(long ticks, bool obtained)
        {
            _allowanceTicks = Math.Max(0, _allowanceTicks - ticks);
            _lastTicks = System.Diagnostics.Stopwatch.GetTimestamp();
            _waits++;
            _waitTicks += ticks;

            if (obtained)
            {
                _obtained++;
            }
        }

        public static string TakeText()
        {
            string text = "; skippable draws that waited briefly " + _waits + " (obtained in time " + _obtained + ", " +
                (_waitTicks * 1000.0 / System.Diagnostics.Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture) +
                " ms)";

            _waits = _obtained = _waitTicks = 0;

            return text;
        }
    }

    sealed class BackgroundCompilationScheduler : IDisposable
    {
'''),
    ('''        public Task SchedulePipelineCompile(Action<PipelineCache> action, bool highPriority = false, bool demanded = false)
        {
''', '''        // RewindBox (adapt_render_thread_compile_relief): prebuild is work known in advance to be drawn (a recorded
        // state): taken after the high priority compiles and before the low priority, speculative ones.
        public Task SchedulePipelineCompile(Action<PipelineCache> action, bool highPriority = false, bool demanded = false, bool prebuild = false)
        {
'''),
    ('''                highPriority,
                demanded,
                workerIndex => _pipelineCacheManager.NotifyWorkerPipelineCreated(workerIndex));
''', '''                highPriority,
                demanded,
                workerIndex => _pipelineCacheManager.NotifyWorkerPipelineCreated(workerIndex),
                prebuild);
'''),
    ('''            private readonly LinkedList<WorkItem> _lowPriorityQueue = new();
''', '''            private readonly LinkedList<WorkItem> _prebuildQueue = new(); // RewindBox (adapt_render_thread_compile_relief)
            private readonly LinkedList<WorkItem> _lowPriorityQueue = new();
'''),
    ('''            public Task Schedule(Action<int> action, bool highPriority, bool demanded = false, Action<int> afterCompletion = null)
            {
''', '''            public Task Schedule(Action<int> action, bool highPriority, bool demanded = false, Action<int> afterCompletion = null,
                bool prebuild = false)
            {
'''),
    ('''                    Enqueue(item, demanded, highPriority);

                    Monitor.PulseAll(_queueLock);
                }

                return item.Completion.Task;
''', '''                    Enqueue(item, demanded, highPriority, prebuild);

                    Monitor.PulseAll(_queueLock);
                }

                return item.Completion.Task;
'''),
    ('''            private void Enqueue(WorkItem item, bool demanded, bool highPriority)
            {
                LinkedList<WorkItem> queue = demanded
                    ? _demandQueue
                    : highPriority
                        ? _highPriorityQueue
                        : _lowPriorityQueue;
''', '''            private void Enqueue(WorkItem item, bool demanded, bool highPriority, bool prebuild = false)
            {
                LinkedList<WorkItem> queue = demanded
                    ? _demandQueue
                    : highPriority
                        ? _highPriorityQueue
                        : prebuild
                            ? _prebuildQueue
                            : _lowPriorityQueue;
'''),
    ('''                    node = _highPriorityQueue.First ?? _lowPriorityQueue.First;
''', '''                    node = _highPriorityQueue.First ?? _prebuildQueue.First ?? _lowPriorityQueue.First;
'''),
    ('''                    Drain(_highPriorityQueue, pending);
''', '''                    Drain(_highPriorityQueue, pending);
                    Drain(_prebuildQueue, pending);
'''),
)

COLLECTION_PAIRS = (
    ('''        private Task RunBackgroundPipelineCompile(Action<PipelineCache> compileAction, bool highPriority, bool demanded = false)
        {
            return _gd.BackgroundCompilationScheduler.SchedulePipelineCompile(compileAction, highPriority, demanded);
        }
''', '''        private Task RunBackgroundPipelineCompile(Action<PipelineCache> compileAction, bool highPriority, bool demanded = false,
            bool prebuild = false)
        {
            return _gd.BackgroundCompilationScheduler.SchedulePipelineCompile(compileAction, highPriority, demanded, prebuild);
        }

        // RewindBox (adapt_render_thread_compile_relief): a draw that may skip waits at most timeoutMs for the compile
        // queued for its key, without promoting anything (that compile is demanded already) and without compiling.
        public bool TryWaitBrieflyForQueuedGraphicsPipeline(ref PipelineUid key, int timeoutMs, out Auto<DisposablePipeline> pipeline)
        {
            Task task = null;

            lock (_pipelineCacheLock)
            {
                _graphicsPipelineBackgroundQueue?.TryGetValue(ref key, out task);
            }

            if (task != null && !task.IsCompleted)
            {
                try
                {
                    task.Wait(timeoutMs);
                }
                catch (AggregateException)
                {
                    // The compile's own failure path records it; the draw skips.
                }
            }

            return TryGetGraphicsPipeline(ref key, out pipeline) && pipeline != null;
        }
'''),
    ('''            Task task = null;

            if (_playTimeWarmUp)
            {
                lock (_pipelineCacheLock)
                {
                    _computePipelineBackgroundQueue?.TryGetValue(ref key, out task);
                }
            }
''', '''            Task task = null;

            // RewindBox (adapt_render_thread_compile_relief): the queued warm-up of any program, also one loaded from
            // the disk cache (it was created a second time by the dispatch while its warm-up waited in the queue).
            lock (_pipelineCacheLock)
            {
                _computePipelineBackgroundQueue?.TryGetValue(ref key, out task);
            }
'''),
    ('''                }, highPriority: false);

                (_graphicsPipelineBackgroundQueue ??= new()).Add(ref key, compile);
                (_variantTasks ??= new()).Add(compile);
''', '''                }, highPriority: false, prebuild: true); // RewindBox (adapt_render_thread_compile_relief): before the warm-ups

                (_graphicsPipelineBackgroundQueue ??= new()).Add(ref key, compile);
                (_variantTasks ??= new()).Add(compile);
'''),
    ('''            // The warm-up does not decide LinkStatus; a draw that needs it promotes it.
            if (_detachedWarmUp)
            {
                return LinkStatus;
            }

            if (!_compileTask.IsCompleted)
            {
                if (blocking)
                {
                    _compileTask.Wait();
''', '''            // The warm-up does not decide LinkStatus; a draw that needs it promotes it.
            if (_detachedWarmUp)
            {
                return LinkStatus;
            }

            if (!_compileTask.IsCompleted)
            {
                if (blocking)
                {
                    // RewindBox (adapt_render_thread_compile_relief): this wait covers the warm-up pipeline too (a program
                    // translated during play with async compilation, bound by SetProgram when it cannot bind incomplete).
                    // It demands that compile first, as a draw or a dispatch does; queued high in arrival order, it came
                    // only after the launch's cached compute warm-ups (Metal cache cold, IPA 824-829: 0.5 s each).
                    PromoteBackgroundCompilation();
                    _compileTask.Wait();
'''),
)

RENDERER_PAIRS = (
    ('''            bool highPriorityBackgroundCompilation = compileInBackground && !info.FromCache;
''', '''            // RewindBox (adapt_render_thread_compile_relief): a cached compute program too; no dispatch can skip.
            bool highPriorityBackgroundCompilation = compileInBackground && (!info.FromCache || isCompute);
'''),
)

FILE_PAIRS = {
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': PIPELINE_PAIRS,
    'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs': SCHEDULER_PAIRS,
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': COLLECTION_PAIRS,
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': RENDERER_PAIRS,
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
