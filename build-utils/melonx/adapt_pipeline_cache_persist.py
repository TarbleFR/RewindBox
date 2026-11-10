"""The main pipeline cache is written when the game is paused (the app leaves the foreground) and more often during play.

IPA 674/676, private journals, not in the repository (Hogwarts Legacy, player 1, pids 21216, 21727, 23682, 24714): every
session ends in the background or in a crash, never with a clean close, so the main pipeline cache is only ever written
by the play-time checkpoint, and each session has exactly one, about 3 min in. On IPA 676 (pid 24714) the render thread
then built new pipelines at 0.5-1 s each (12 in 6.9 s, 8 in 5.0 s, 2 in 1.9 s) between 01:00:58 and 01:02:29, after
the only checkpoint (01:00:32), and the app left the foreground at 01:02:30: those pipelines were lost, and the next
session compiles them again where the player already went. A cached pipeline costs about 9 ms instead.

Mechanism (Core 681 preparation): CheckpointMainIfDue runs only after a worker pipeline (NotifyWorkerPipelineCreated),
every 180 s at most and only after 64 main pipelines; the render-thread builds of a new area (NotifyMainPipelineCreated)
never trigger it, and nothing writes the cache when the guest is paused for the background.

Change (PipelineCacheManager.cs, VulkanRenderer.cs, Library.cs, every title):
- the host pause callback (the app leaves the foreground) asks the Vulkan renderer, on a thread-pool thread, to write the
  main cache now if it gained content since its last write (blocking on the main lock off the render thread; render-
  thread creations meanwhile go to the side cache);
- play-time checkpoints: every 90 s at most, after 8 main pipelines (was 180 s and 64), and a render-thread main pipeline
  that makes one due queues it on the thread pool (never run on the render thread);
- Dispose takes the main cache lock, so a write in flight finishes before the caches are destroyed.
Budgets, the side cache, the worker caches and the close path are unchanged.
Fail closed on drift: the files must be the Core 681 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
RENDERER = 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'

BASELINE = {
    MANAGER: '0a4d0890895e13073f7d72a2303008243cd2b2028c0daeaa85503646d52a8930',
    RENDERER: 'ca5218df938bc0a1c26c51bb3f7173948a24b6aab820f11d690eaa53d7a2c1a6',
    LIBRARY: '80992144937c50366da89d94b9c754e260e4459ad57a788be3e1d2f92b480049',
}

CADENCE_OLD = '''        private const long MainCheckpointIntervalMs = 180_000;
        private const int MainCheckpointMinimumPipelines = 64;
'''
CADENCE_NEW = '''        // RewindBox (adapt_pipeline_cache_persist): every 90 s at most after 8 main pipelines (was 180 s and 64): sessions end
        // in the background or a crash, so what is not checkpointed is compiled again next session.
        private const long MainCheckpointIntervalMs = 90_000;
        private const int MainCheckpointMinimumPipelines = 8;
        private int _mainCheckpointQueued;
'''

NOTIFY_OLD = '''            Interlocked.Increment(ref _mainState.PipelineCount);
            Interlocked.Increment(ref _mainState.Generation);
'''
NOTIFY_NEW = '''            Interlocked.Increment(ref _mainState.PipelineCount);
            Interlocked.Increment(ref _mainState.Generation);

            // RewindBox (adapt_pipeline_cache_persist): a render-thread pipeline that makes a checkpoint due queues it on the
            // thread pool (the render thread never writes the cache; its creations go to the side cache meanwhile).
            if (!string.IsNullOrEmpty(_mainState.Path) && !_mainCheckpointInProgress &&
                Environment.TickCount64 - Interlocked.Read(ref _mainCheckpointTimestamp) >= MainCheckpointIntervalMs &&
                Volatile.Read(ref _mainState.PipelineCount) - Volatile.Read(ref _mainCheckpointPipelineCount) >= MainCheckpointMinimumPipelines &&
                Interlocked.CompareExchange(ref _mainCheckpointQueued, 1, 0) == 0)
            {
                ThreadPool.UnsafeQueueUserWorkItem(_ =>
                {
                    try
                    {
                        CheckpointMainIfDue();
                    }
                    finally
                    {
                        Volatile.Write(ref _mainCheckpointQueued, 0);
                    }
                }, null);
            }
'''

PAUSE_METHOD_ANCHOR = '''        public void NotifyMainPipelineCreated()
'''
PAUSE_METHOD_NEW = '''        // RewindBox (adapt_pipeline_cache_persist): the guest is paused (the app leaves the foreground): the main cache is
        // written now if it gained content since its last write. Called off the render thread; waits for the main lock.
        public void CheckpointMainOnPause()
        {
            CacheState main = _mainState;

            if (_disposed || main.Frozen || string.IsNullOrEmpty(main.Path) ||
                Interlocked.Read(ref main.Generation) == main.SavedGeneration)
            {
                return;
            }

            _mainCheckpointInProgress = true;
            _mainCacheLock.Enter();

            try
            {
                if (_disposed || Interlocked.Read(ref main.Generation) == main.SavedGeneration)
                {
                    return;
                }

                long now = Environment.TickCount64;
                int pipelines = main.PipelineCount - _mainCheckpointPipelineCount;
                Interlocked.Exchange(ref _mainCheckpointTimestamp, now);
                _mainCheckpointPipelineCount = main.PipelineCount;
                Interlocked.Exchange(ref _mainCheckpointGeneration, Interlocked.Read(ref main.Generation));

                long size = GetCacheDataSize(main);

                if (size < 0)
                {
                    return;
                }

                main.OnMeasured(size);

                if (size > main.Budget)
                {
                    return;
                }

                SaveCache(main, size, final: false);
                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Vulkan main pipeline cache checkpointed on pause in {Environment.TickCount64 - now} ms, " +
                    $"{pipelines} main pipelines since the previous checkpoint (adapt_pipeline_cache_persist).");
            }
            finally
            {
                MergeSideCache();
                _mainCacheLock.Exit();
                _mainCheckpointInProgress = false;
            }
        }

        public void NotifyMainPipelineCreated()
'''

DISPOSE_OLD = '''        public unsafe void Dispose()
        {
            if (_disposed)
            {
                return;
            }

            _disposed = true;
'''
DISPOSE_NEW = '''        public unsafe void Dispose()
        {
            // RewindBox (adapt_pipeline_cache_persist): a pause checkpoint in flight finishes before the caches are destroyed.
            lock (_mainCacheLock)
            {
                DisposeLocked();
            }
        }

        private unsafe void DisposeLocked()
        {
            if (_disposed)
            {
                return;
            }

            _disposed = true;
'''

RENDERER_OLD = '''        internal PipelineCacheManager PipelineCacheManager { get; private set; }
'''
RENDERER_NEW = '''        internal PipelineCacheManager PipelineCacheManager { get; private set; }

        // RewindBox (adapt_pipeline_cache_persist): the guest was paused (the app left the foreground).
        public void CheckpointPipelineCacheOnPause()
        {
            try
            {
                PipelineCacheManager?.CheckpointMainOnPause();
            }
            catch (Exception exception)
            {
                Logger.Warning?.Print(LogClass.Gpu, $"Pause checkpoint of the pipeline cache failed: {exception.Message}");
            }
        }
'''

LIBRARY_OLD = '''                    _emulationContext.System.TogglePauseEmulation(paused);
                    _window.SetEmbeddedPaused(paused);
'''
LIBRARY_NEW = '''                    _emulationContext.System.TogglePauseEmulation(paused);
                    _window.SetEmbeddedPaused(paused);
                    // RewindBox (adapt_pipeline_cache_persist): sessions end in the background, so the pipelines built since the
                    // last checkpoint are written as the app leaves the foreground (thread pool, never this thread).
                    if (paused && _emulationContext?.Gpu?.Renderer is Ryujinx.Graphics.GAL.IRenderer pausedRenderer &&
                        ((pausedRenderer as Ryujinx.Graphics.GAL.Multithreading.ThreadedRenderer)?.BaseRenderer ?? pausedRenderer) is VulkanRenderer pausedVulkan)
                    {
                        System.Threading.ThreadPool.UnsafeQueueUserWorkItem(_ => pausedVulkan.CheckpointPipelineCacheOnPause(), null);
                    }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    once(paths[MANAGER], CADENCE_OLD, CADENCE_NEW)
    once(paths[MANAGER], NOTIFY_OLD, NOTIFY_NEW)
    once(paths[MANAGER], PAUSE_METHOD_ANCHOR, PAUSE_METHOD_NEW)
    once(paths[MANAGER], DISPOSE_OLD, DISPOSE_NEW)
    once(paths[RENDERER], RENDERER_OLD, RENDERER_NEW)
    once(paths[LIBRARY], LIBRARY_OLD, LIBRARY_NEW)
    return list(paths.values())
