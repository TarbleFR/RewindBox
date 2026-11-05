"""Bind a program translated during play without waiting for its warm-up pipeline (Hogwarts Legacy policy).

IPA 658 logs, 5 November 2026, Hogwarts Legacy (pid 11152, private, not in the repository; counts and times only):
asyncShaders=False. Between 03:13:00 and 03:14:07 UTC the render thread spent about 33 s in SetProgram against about
20 s in DrawIndexed; its 5 s windows show SetProgram 2592, 4861, 4972, 4028, 4031 and 4941 ms, while the draw-time
pipeline builds of the same windows took a few ms. SetProgram dominates the render thread around 9 of the 14 "Wait on
syncpoint 1 ... resuming execution" timeouts: the GPU thread waits for the render thread, the guest for the GPU
thread. The same burst holds 230 graphics plus 27 compute pipeline builds summing 152.7 s of wall time for 45.0 s of
MoltenVK compile work, and 4 first draws logged "Background pipeline compile missed on draw" (primitive restart, two
of them also TriangleList/TriangleStrip).

Mechanism (Core 658 preparation):
- VulkanRenderer.CreateProgram compiles in the background only with async shaders or for a program read from the
  cache (adapt_cached_shader_startup). A program translated during play takes the synchronous path: its shader
  modules on Task.Run, then ShaderCollection.BackgroundCompilation builds its warm-up pipeline (the pipeline state at
  translation) on the main pipeline cache, under VulkanRenderer.PipelineCreationLock, as a thread-pool continuation.
- SetProgramCommand.Run: CanBindWhileIncomplete is false, so ProgramQueue.WaitForProgram -> CheckProgramLink(true),
  whose synchronous branch waits for _compileTask, i.e. for the warm-up; PipelineBase.SetProgram -> GetInfos ->
  EnsureShadersReadyLegacy waits for it again. The render thread sleeps for the whole Metal compile of that warm-up,
  also when the draw then needs another pipeline (a second, synchronous build). adapt_shader_warmup detached this wait
  only for cached programs ("Programs compiled during play keep waiting for their pipeline as before"). When the
  modules are already compiled as the constructor reaches BackgroundCompilation's await, the warm-up even runs inline
  on the render thread, in CreateProgram or in a ProgramQueue.ProcessQueue (which SetProgram runs and which creates up
  to 8 queued programs): seen in the executed fixture, not measured on the device.
- PipelineCreationLock (PipelineState.CreateGraphicsPipeline/CreateComputePipeline, main cache only) serializes the
  render thread's own builds with the thread-pool warm-ups of every program ProgramQueue created ahead (up to 8); the
  workers of BackgroundCompilationScheduler build on their own caches, outside that lock.

Change, under VulkanRenderer.DetachPlayTimeWarmUps (set per session by the Library: Hogwarts Legacy only until a
second title is measured; off, every path is the delivered one):
- a program translated during play with synchronous compilation (not async shaders, not from the cache) and a
  pipeline state, or a compute program, compiles as a cached program does: shader modules and warm-up on the bounded
  scheduler (high priority, ahead of cached warm-ups), the warm-up detached (_detachedWarmUp): CheckProgramLink
  returns once the shader modules exist, so SetProgram waits for the modules only (promoted to the demand worker
  while it waits), and no warm-up compiles on the render thread or under PipelineCreationLock. Async compile skip
  stays off: CanBindWhileIncomplete and CanSkipForBackgroundCompile stay false, no draw or dispatch is ever skipped;
- a draw with the warm-up's key promotes it to the demand worker (user-interactive QoS) and waits for it
  (TryWaitForBackgroundGraphicsPipeline, unchanged); a draw with another key builds its own pipeline synchronously on
  the main cache, as before, without waiting for a warm-up it does not use;
- compute: a dispatch with the warm-up's key (SpecData.Empty) waits for that warm-up the same way
  (TryWaitForBackgroundComputePipeline, new, play-time programs only) instead of compiling it a second time;
- the once-per-program "Background pipeline compile missed on draw" line stays for these programs: logged when the
  draw's key is that of no queued warm-up (the table may still be empty, the binding no longer waited);
- Dispose and renderer teardown cancel such a warm-up no worker has taken (adapt_shader_warmup's CancelPendingWarmUp,
  now covering it); one in progress is waited for, as before.
Not changed: pipeline keys and state, which pipeline a draw binds, async shader mode, cached programs, programs without
a pipeline state, helper programs, cache formats, the queues (their order and priorities). The GPU thread's disk-cache save poll
(ShaderCache.ProcessShaderCacheQueue -> CheckProgramLink(false)) now completes once the modules exist instead of after
the warm-up; what is saved does not change. The worker caches (128 MiB budget each) hold these warm-ups instead of the
main cache, merged at close as before; their periodic upkeep (PipelineCacheManager.NotifyWorkerPipelineCreated: checkpoint
save, recycle under PipelineCreationLock) runs on the worker after the work item completes (BackgroundCompilationScheduler),
so a draw waiting for a warm-up no longer waits for cache persistence (the compile threads still do the upkeep); a draw-time build with another key on the main cache converts SPIR-V to MSL
itself (MoltenVK keeps a shader library cache per pipeline cache). Not measured on an iPhone.
Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '1c94d13b6b10c011699283982408dbb4bfc9bd4ee9fdacf7354dc8dae216212f',
    'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs': '05a7151352f049d7c2f7b65803ae8d45581c96989fa02056446dc28de9000da0',
    'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs': 'efdd73f640552e80d0a7802e41c7997d33a96f175aea7b7146acd94943314a74',
    'src/Ryujinx.Library/Library.cs': 'a85914786f6895097b16c6a1f1cc4d8bfcb03ca461593b7a5b567d0f4dcdc201',
    'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs': '3b5c768c1350b918e0c9912e50fb06819f005db67f6c1ebaca3e8c14c888a966',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    renderer = paths['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs']
    once(renderer, '''        public IProgram CreateProgram(ShaderSource[] sources, ShaderInfo info)
        {
''', '''        // RewindBox (adapt_setprogram_warmup): set per session by the Library (Hogwarts Legacy policy). With synchronous
        // compilation, a program translated during play then binds once its shader modules exist; its warm-up pipeline
        // compiles on the bounded workers, and a draw or dispatch with the warm-up's key waits for it. Off: as delivered.
        public bool DetachPlayTimeWarmUps { get; set; }

        public IProgram CreateProgram(ShaderSource[] sources, ShaderInfo info)
        {
''')
    once(renderer, '''            bool compileInBackground = info.EnableAsyncCompile || info.FromCache;
''', '''            // RewindBox (adapt_setprogram_warmup): translated during play, synchronous compilation, with a warm-up.
            // Async compile skip stays off: no draw or dispatch is skipped, each waits for its exact pipeline.
            bool playTimeWarmUp = DetachPlayTimeWarmUps && !info.EnableAsyncCompile && !info.FromCache && (info.State.HasValue || isCompute);
            bool compileInBackground = info.EnableAsyncCompile || info.FromCache || playTimeWarmUp;
''')
    once(renderer, '''                    allowAsyncCompileSkip,
                    highPriorityBackgroundCompilation);
''', '''                    allowAsyncCompileSkip,
                    highPriorityBackgroundCompilation,
                    playTimeWarmUp);
''')

    collection = paths['src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs']
    once(collection, '''        private bool _detachedWarmUp;
        private int _cancelUndemandedWarmUp;
''', '''        private bool _detachedWarmUp;
        private int _cancelUndemandedWarmUp;
        // RewindBox (adapt_setprogram_warmup): translated during play under VulkanRenderer.DetachPlayTimeWarmUps; its
        // warm-up is detached like a cached program's.
        private bool _playTimeWarmUp;
''')
    once(collection, '''            bool allowAsyncCompileSkip,
            bool highPriorityBackgroundCompilation) : this(
''', '''            bool allowAsyncCompileSkip,
            bool highPriorityBackgroundCompilation,
            bool playTimeWarmUp = false) : this(
''')
    once(collection, '''            _detachedWarmUp = fromCache && warmUpInitialPipeline;
''', '''            _playTimeWarmUp = playTimeWarmUp && warmUpInitialPipeline;
            _detachedWarmUp = (fromCache || _playTimeWarmUp) && warmUpInitialPipeline;
''')
    once(collection, '''            if (!EnsureShadersReady(blocking))
            {
                return LinkStatus == ProgramLinkStatus.Failure ? ProgramLinkStatus.Failure : ProgramLinkStatus.Incomplete;
            }
''', '''            // RewindBox (adapt_setprogram_warmup): binding waits for these modules only; the warm-up stays speculative.
            if (blocking && _playTimeWarmUp)
            {
                foreach (Shader shader in _shaders)
                {
                    shader.PromoteCompilation();
                }
            }

            if (!EnsureShadersReady(blocking))
            {
                return LinkStatus == ProgramLinkStatus.Failure ? ProgramLinkStatus.Failure : ProgramLinkStatus.Incomplete;
            }
''')
    once(collection, '''                if (!CompilesInBackground)
                {
                    _firstBackgroundUse = false;
                }
''', '''                if (!CompilesInBackground || _playTimeWarmUp)
                {
                    _firstBackgroundUse = false;
                }
''')
    once(collection, '''            lock (_pipelineCacheLock)
            {
                _graphicsPipelineBackgroundQueue?.TryGetValue(ref key, out task);
            }
''', '''            lock (_pipelineCacheLock)
            {
                _graphicsPipelineBackgroundQueue?.TryGetValue(ref key, out task);

                // RewindBox (adapt_setprogram_warmup): binding no longer waited for the warm-up, so the first draw may
                // find the table empty. A key that no queued warm-up has and the table lacks is the synchronous path's
                // miss: logged once per program, the draw builds its own pipeline.
                if (task == null && _playTimeWarmUp && _firstBackgroundUse &&
                    (_graphicsPipelineCache == null || !_graphicsPipelineCache.TryGetValue(ref key, out _)))
                {
                    Logger.Warning?.Print(LogClass.Gpu, "Background pipeline compile missed on draw - incorrect pipeline state?" +
                        DescribeInitialKeyDifference(ref key) +
                        (_graphicsPipelineCache == null ? " (pipelines already built for this program: 0)" : DescribeMissContext()));
                    _firstBackgroundUse = false;
                }
            }
''')
    once(collection, '''        public bool QueueBackgroundComputePipeline(ref PipelineState state)
''', '''        // RewindBox (adapt_setprogram_warmup): a dispatch with the warm-up's key (SpecData.Empty) of a program translated
        // during play promotes that warm-up and waits for it, instead of compiling the same pipeline a second time on the
        // main cache. Other programs and keys: false, the dispatch compiles as before.
        public bool TryWaitForBackgroundComputePipeline(ref SpecData key, out Auto<DisposablePipeline> pipeline)
        {
            Task task = null;

            if (_playTimeWarmUp)
            {
                lock (_pipelineCacheLock)
                {
                    _computePipelineBackgroundQueue?.TryGetValue(ref key, out task);
                }
            }

            if (task == null)
            {
                pipeline = default;
                return false;
            }

            if (!task.IsCompleted)
            {
                PromoteBackgroundCompilation();

                try
                {
                    task.Wait();
                }
                catch (AggregateException)
                {
                    // The dispatch compiles the pipeline itself.
                }
            }

            _gd.ThrowIfBackgroundPipelineFailed();

            return TryGetComputePipeline(ref key, out pipeline) && pipeline != null;
        }

        public bool QueueBackgroundComputePipeline(ref PipelineState state)
''')

    pipeline = paths['src/Ryujinx.Graphics.Vulkan/PipelineBase.cs']
    once(pipeline, '''                        pipeline = _newState.CreateComputePipeline(Gd, Device, _program, PipelineCache);
''', '''                        // RewindBox (adapt_setprogram_warmup): the program's warm-up when it has this key and is compiling.
                        if (!_program.TryWaitForBackgroundComputePipeline(ref key, out pipeline))
                        {
                            pipeline = _newState.CreateComputePipeline(Gd, Device, _program, PipelineCache);
                        }
''')

    scheduler = paths['src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs']
    once(scheduler, '''            return _pipelineQueue.Schedule(workerIndex =>
            {
                try
                {
                    action(_pipelineCacheManager.GetWorkerCache(workerIndex));
                }
                finally
                {
                    _pipelineCacheManager.NotifyWorkerPipelineCreated(workerIndex);
                }
            }, highPriority, demanded);
''', '''            // RewindBox (adapt_setprogram_warmup): the cache upkeep (checkpoint save, recycle under PipelineCreationLock) runs
            // after the work item completes, so a draw waiting for this compile never waits for cache persistence.
            return _pipelineQueue.Schedule(
                workerIndex => action(_pipelineCacheManager.GetWorkerCache(workerIndex)),
                highPriority,
                demanded,
                workerIndex => _pipelineCacheManager.NotifyWorkerPipelineCreated(workerIndex));
''')
    once(scheduler, '''                private readonly Action<int> _action;

                public TaskCompletionSource<bool> Completion { get; }''', '''                private readonly Action<int> _action;
                private readonly Action<int> _afterCompletion;

                public TaskCompletionSource<bool> Completion { get; }''')
    once(scheduler, '''                public WorkItem(Action<int> action)
                {
                    _action = action;
''', '''                public WorkItem(Action<int> action, Action<int> afterCompletion = null)
                {
                    _action = action;
                    _afterCompletion = afterCompletion;
''')
    once(scheduler, '''                        Completion.TrySetException(exception);
                    }
                }

                public void Cancel(''', '''                        Completion.TrySetException(exception);
                    }

                    if (_afterCompletion != null)
                    {
                        try
                        {
                            _afterCompletion(workerIndex);
                        }
                        catch (Exception)
                        {
                            // Upkeep failure: the waiters were released already; it must not end the worker thread.
                        }
                    }
                }

                public void Cancel(''')
    once(scheduler, '''            public Task Schedule(Action<int> action, bool highPriority, bool demanded = false)
            {
                WorkItem item = new(action);
''', '''            public Task Schedule(Action<int> action, bool highPriority, bool demanded = false, Action<int> afterCompletion = null)
            {
                WorkItem item = new(action, afterCompletion);
''')

    library = paths['src/Ryujinx.Library/Library.cs']
    paced = ('            if (renderer is VulkanRenderer pacedVulkan) pacedVulkan.PresentPacingAllowed = !options.DisableVSync && '
             'options.VSyncMode == Ryujinx.Common.Configuration.VSyncMode.Switch;\n')
    once(library, paced, paced + '''            // RewindBox (adapt_setprogram_warmup): binding a program translated during play waits for its shader modules,
            // not for its warm-up pipeline (Hogwarts Legacy until a second title is measured).
            if (renderer is VulkanRenderer warmUpVulkan) warmUpVulkan.DetachPlayTimeWarmUps = hogwarts;
''')
    return list(paths.values())
