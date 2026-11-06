"""The main Vulkan pipeline cache is checkpointed during play, so a session that ends in a crash keeps its pipelines.

IPA 672 (Core 671), private journals, not in the repository: Hogwarts Legacy loads the same 301.62 MiB main pipeline
cache at every launch, because the main cache is written only by MergeAndSave at a clean close and every Hogwarts
session of the day ended in a crash or a kill. The pipelines the render thread created during an 18-minute session
(215 s of the 1093 s on the render thread; 38 % of the time of every window below 20 fps, 1 % above 25 fps) and the
worker caches merged into main before each recycle (PreserveBeforeRecycle) were lost and compiled again next time; the
session ended when a 30 s window with 15.4 s of pipeline creation froze rendering long enough for the game's own hang
detector (FHeartBeatThread) to abort it.

Change (PipelineCacheManager.cs, PipelineState.cs, every title):
- after a worker finishes a pipeline (NotifyWorkerPipelineCreated, on the worker thread, outside any compile and never on
  the render thread), the main cache is written to its snapshot path when it gained at least 64 pipelines or a merge
  since its last save and at least 180 s passed since the last checkpoint. The worker only tries the main cache lock
  (TryEnter): if the render thread holds it, nothing waits and a later worker completion tries again. The write is the
  same SaveCache as at close (temporary file, then an atomic rename) under the same lock and budget rule.
- while that checkpoint runs, a render-thread pipeline creation that would only try the lock (failOnCompileRequired,
  the asynchronous skip path) waits for it instead, so no draw is skipped because of a checkpoint.
One Info log line per checkpoint (duration, pipelines since the previous one). Close, recycling, budgets, worker
checkpoints and every compile path are unchanged.
Fail closed on drift: the files must be the Core 671 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': '89bc2adfe58f2ee20be6420f18a713cf2126160a2766f4b22740386f79cbf5b6',
    'src/Ryujinx.Graphics.Vulkan/PipelineState.cs': 'e1c2cadbdb525433a297781a585db068b14ddb3a89ef38b21d23d179f592152f',
}

FIELDS_OLD = '''        private bool _disposed;
'''
FIELDS_NEW = '''        private bool _disposed;

        // RewindBox (adapt_main_cache_checkpoint): the main cache written during play, from a worker thread.
        private const long MainCheckpointIntervalMs = 180_000;
        private const int MainCheckpointMinimumPipelines = 64;
        private long _mainCheckpointTimestamp = Environment.TickCount64;
        private int _mainCheckpointPipelineCount;
        private long _mainCheckpointGeneration;
        private volatile bool _mainCheckpointInProgress;

        // A render-thread creation that would only try the lock waits for it while a checkpoint holds it (no skipped draw).
        public bool MainCheckpointInProgress => _mainCheckpointInProgress;
'''

NOTIFY_OLD = '''            state.PipelineCount++;
            Interlocked.Increment(ref state.Generation);

            Maintain(state, force: false);
        }
'''
NOTIFY_NEW = '''            state.PipelineCount++;
            Interlocked.Increment(ref state.Generation);

            Maintain(state, force: false);
            CheckpointMainIfDue();
        }

        // RewindBox (adapt_main_cache_checkpoint): on a worker thread after its pipeline, never on the render thread.
        private void CheckpointMainIfDue()
        {
            CacheState main = _mainState;

            if (_disposed || main.Frozen || string.IsNullOrEmpty(main.Path) ||
                Environment.TickCount64 - Interlocked.Read(ref _mainCheckpointTimestamp) < MainCheckpointIntervalMs ||
                Interlocked.Read(ref main.Generation) == main.SavedGeneration)
            {
                return;
            }

            bool merged = Interlocked.Read(ref main.Generation) - Interlocked.Read(ref _mainCheckpointGeneration) >
                Volatile.Read(ref main.PipelineCount) - Volatile.Read(ref _mainCheckpointPipelineCount);

            if (!merged && Volatile.Read(ref main.PipelineCount) - Volatile.Read(ref _mainCheckpointPipelineCount) < MainCheckpointMinimumPipelines)
            {
                return;
            }

            // Raised before the lock is tried and lowered after it is released: a render-thread TryEnter that fails while it
            // is raised waits for the lock instead (PipelineState), so no draw is skipped for a checkpoint.
            _mainCheckpointInProgress = true;

            if (!_mainCacheLock.TryEnter())
            {
                _mainCheckpointInProgress = false;
                return;
            }

            try
            {
                long now = Environment.TickCount64;

                if (_disposed || now - Interlocked.Read(ref _mainCheckpointTimestamp) < MainCheckpointIntervalMs)
                {
                    return;
                }

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
                    $"Vulkan main pipeline cache checkpointed during play in {Environment.TickCount64 - now} ms, " +
                    $"{pipelines} main pipelines since the previous checkpoint (adapt_main_cache_checkpoint).");
            }
            finally
            {
                _mainCacheLock.Exit();
                _mainCheckpointInProgress = false;
            }
        }
'''

LOCK_OLD = '''                        if (failOnCompileRequired)
                        {
                            lockTaken = gd.PipelineCreationLock.TryEnter();
                        }
'''
LOCK_NEW = '''                        if (failOnCompileRequired)
                        {
                            lockTaken = gd.PipelineCreationLock.TryEnter();

                            // RewindBox (adapt_main_cache_checkpoint): a lock held by a play-time checkpoint of the main
                            // cache is waited for, so the checkpoint never makes a draw skip.
                            if (!lockTaken && gd.PipelineCacheManager.MainCheckpointInProgress)
                            {
                                gd.PipelineCreationLock.Enter();
                                lockTaken = true;
                            }
                        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    manager = paths['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs']
    once(manager, FIELDS_OLD, FIELDS_NEW)
    once(manager, NOTIFY_OLD, NOTIFY_NEW)
    once(paths['src/Ryujinx.Graphics.Vulkan/PipelineState.cs'], LOCK_OLD, LOCK_NEW)
    return list(paths.values())
