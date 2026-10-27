"""Start the game without waiting for the pipeline warm-ups of the shader cache.

Build 572 app.log (27 October 2026): Super Smash Bros. Ultimate spent 18 s in
"Loading 2743 shaders from the cache" before its guest process ran its first
service call, and showed its first frame 23 s after launch. The disk cache
loader waits for each program with CheckProgramLink, and for a program loaded
from the cache that wait also covered its initial pipeline warm-up (the
pipeline state saved with it). Those warm-ups run in the low-priority pipeline
queue of BackgroundCompilationScheduler, which has a single worker on a
six-core iPhone (Math.Min(2, cores / 4)): every cached pipeline was compiled
through MoltenVK and Metal, one after the other, before the game could start.

- CheckProgramLink: a program from the cache is ready once its shader modules
  are (EnsureShadersReady, unchanged); its initial pipeline keeps compiling in
  the background. The warm-up never decided LinkStatus: BackgroundCompilation
  catches its failures, logs them and the draw creates the pipeline itself.
  Programs compiled during play keep waiting for their pipeline as before.
- A draw that needs a pipeline its program is still warming up promotes that
  warm-up to the demand worker (PromoteBackgroundCompilation, the existing path
  of TryGetInfos and WaitForShaderModules) instead of waiting, or skipping the
  draw, behind every queued warm-up: when it waits for it
  (TryWaitForBackgroundGraphicsPipeline) and when the skip path finds the
  pipeline already queued (QueueBackground{Graphics,Compute}Pipeline).
- Dispose of such a program cancels its warm-up if no worker took it yet,
  instead of compiling it on the way out (closing a game soon after launch);
  one already started is waited for as before. A cancelled warm-up is not
  reported as a failure.

No compilation result, cache format or priority of play-time compilation
changes. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan'
    collection = vulkan / 'ShaderCollection.cs'
    once(collection, '''        private int _backgroundCompilationDemanded;
        private bool _firstBackgroundUse;''', '''        private int _backgroundCompilationDemanded;
        private bool _firstBackgroundUse;
        // Loaded from the shader cache: the initial pipeline warms up without
        // holding the cache loader.
        private bool _detachedWarmUp;''')
    once(collection, '''            if (warmUpInitialPipeline)
            {
                RegisterInitialBackgroundPipelineTask(_compileTask);

                if (_compileTask.IsCompleted)
                {
                    ClearInitialBackgroundPipelineTask();
                }
            }

            _firstBackgroundUse = !fromCache;''', '''            if (warmUpInitialPipeline)
            {
                RegisterInitialBackgroundPipelineTask(_compileTask);

                if (_compileTask.IsCompleted)
                {
                    ClearInitialBackgroundPipelineTask();
                }
            }

            _detachedWarmUp = fromCache && warmUpInitialPipeline;
            _firstBackgroundUse = !fromCache;''')
    once(collection, '''            if (!EnsureShadersReady(blocking))
            {
                return LinkStatus == ProgramLinkStatus.Failure ? ProgramLinkStatus.Failure : ProgramLinkStatus.Incomplete;
            }

            if (!_compileTask.IsCompleted)''', '''            if (!EnsureShadersReady(blocking))
            {
                return LinkStatus == ProgramLinkStatus.Failure ? ProgramLinkStatus.Failure : ProgramLinkStatus.Incomplete;
            }

            // The warm-up does not decide LinkStatus; a draw that needs it promotes it.
            if (_detachedWarmUp)
            {
                return LinkStatus;
            }

            if (!_compileTask.IsCompleted)''')
    once(collection, '''            if (task != null && !task.IsCompleted)
            {
                try
                {
                    task.Wait(timeoutMs);''', '''            if (task != null && !task.IsCompleted)
            {
                PromoteBackgroundCompilation();

                try
                {
                    task.Wait(timeoutMs);''')
    for kind in ('compute', 'graphics'):
        once(collection, f'''                if (_{kind}PipelineBackgroundQueue != null &&
                    _{kind}PipelineBackgroundQueue.TryGetValue(ref key, out _))
                {{
                    return true;
                }}''', f'''                if (_{kind}PipelineBackgroundQueue != null &&
                    _{kind}PipelineBackgroundQueue.TryGetValue(ref key, out _))
                {{
                    PromoteBackgroundCompilation();

                    return true;
                }}''')
    once(collection, '''        private void LogBackgroundPipelineFailure(Exception exception)
        {''', '''        private void LogBackgroundPipelineFailure(Exception exception)
        {
            if (exception is ObjectDisposedException)
            {
                return; // Cancelled by Dispose or by the closing renderer.
            }
''')
    once(collection, '''                if (!_gd.Shaders.Remove(this))
                {
                    return;
                }

                try
                {
                    _compileTask.Wait();''', '''                if (!_gd.Shaders.Remove(this))
                {
                    return;
                }

                if (_detachedWarmUp &&
                    !_gd.BackgroundCompilationScheduler.TryCancelPipelineCompile(Volatile.Read(ref _initialPipelineCompileTask)))
                {
                    PromoteBackgroundCompilation();
                }

                try
                {
                    _compileTask.Wait();''')
    scheduler = vulkan / 'BackgroundCompilationScheduler.cs'
    once(scheduler, '''        public void PromotePipelineCompile(Task task)
        {
            _pipelineQueue.Promote(task);
        }''', '''        public void PromotePipelineCompile(Task task)
        {
            _pipelineQueue.Promote(task);
        }

        public bool TryCancelPipelineCompile(Task task)
        {
            return _pipelineQueue.TryCancel(task);
        }''')
    once(scheduler, '''            private void Enqueue(WorkItem item, bool demanded, bool highPriority)''', '''            // Removes work that no worker has taken yet; it completes with
            // ObjectDisposedException, like the work pending at Dispose.
            public bool TryCancel(Task task)
            {
                WorkItem item;

                lock (_queueLock)
                {
                    if (task == null ||
                        _stopping ||
                        !_scheduled.TryGetValue(task, out item) ||
                        item.Node == null)
                    {
                        return false;
                    }

                    item.Node.List.Remove(item.Node);
                    item.Node = null;
                    _scheduled.Remove(task);
                }

                item.Cancel(new ObjectDisposedException($"{_name} background compilation queue"));

                return true;
            }

            private void Enqueue(WorkItem item, bool demanded, bool highPriority)''')
    return [collection, scheduler]
