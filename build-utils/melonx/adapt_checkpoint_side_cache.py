"""While the main pipeline cache is checkpointed during play, pipeline creation goes to a side cache instead of waiting.

IPA 674 (Core 673), private journals, not in the repository: the play-time checkpoint of Hogwarts Legacy's main pipeline
cache (adapt_main_cache_checkpoint) held the main cache lock for 2818 ms; the render thread needed a pipeline meanwhile
and the 6.6 s window around it shows 4.4 s in pipeline creation and 59 frames. Every checkpoint could freeze rendering
for its whole duration.

Change (PipelineCacheManager.cs, PipelineState.cs, every title):
- PipelineCacheManager.EnterMainCreation: a creation meant for the main cache tries its lock; while a checkpoint is in
  progress it creates into a side cache with its own lock instead (created empty on first use, same flags), so it never
  waits for the checkpoint. Outside a checkpoint the behaviour is the previous one: a blocking creation waits for the
  main lock, a try-only creation (failOnCompileRequired) returns PipelineCompileRequired when another creation holds it.
- At the end of each checkpoint, still under the main lock, the side cache is merged into the main cache and released, so
  its pipelines reach the next save. Graphics and compute creation both go through EnterMainCreation/ExitMainCreation.
Close, recycling, budgets, worker caches and the checkpoint rules are unchanged.
Fail closed on drift: the files must be the Core 673 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': 'af18caa6dc8c8c2863013b6a33af408a949ba098696cb82f3c5ece3875823668',
    'src/Ryujinx.Graphics.Vulkan/PipelineState.cs': '34d06f12c5b4be454be06cf6e9e075bfe54f2a68db475231cce7168065c1eac2',
}

FIELDS_OLD = '''        public bool MainCheckpointInProgress => _mainCheckpointInProgress;
'''
FIELDS_NEW = '''        public bool MainCheckpointInProgress => _mainCheckpointInProgress;

        // RewindBox (adapt_checkpoint_side_cache): main-cache creations made while a checkpoint holds the main lock.
        private readonly Lock _sideCacheLock = new();
        private PipelineCache _sideCache;
        private int _sidePipelineCount;

        // Takes the lock of the cache a main-cache creation goes into and returns that cache: the main cache, or the side
        // cache while a play-time checkpoint holds the main lock (never waiting for the checkpoint). Returns false only
        // for a try-only creation when another creation holds the main lock.
        public bool EnterMainCreation(Lock mainLock, bool tryOnly, out PipelineCache target)
        {
            while (true)
            {
                if (mainLock.TryEnter(tryOnly ? 0 : 2))
                {
                    target = MainCache;
                    return true;
                }

                if (_mainCheckpointInProgress)
                {
                    _sideCacheLock.Enter();

                    if (_sideCache.Handle == 0)
                    {
                        _sideCache = CreateCache(null, "side");
                    }

                    target = _sideCache;
                    return true;
                }

                if (tryOnly)
                {
                    target = default;
                    return false;
                }
            }
        }

        public void ExitMainCreation(Lock mainLock, PipelineCache target)
        {
            if (target.Handle == MainCache.Handle)
            {
                mainLock.Exit();
            }
            else
            {
                _sidePipelineCount++;
                _sideCacheLock.Exit();
            }
        }

        // Under the main lock: the side cache's pipelines join the main cache, then the side cache is released.
        private unsafe void MergeSideCache()
        {
            lock (_sideCacheLock)
            {
                if (_sideCache.Handle == 0)
                {
                    return;
                }

                if (_sidePipelineCount != 0)
                {
                    ReadOnlySpan<PipelineCache> source = stackalloc PipelineCache[] { _sideCache };

                    if (MergeInto(_mainState.Cache, source))
                    {
                        Interlocked.Increment(ref _mainState.Generation);
                    }
                }

                _api.DestroyPipelineCache(_device, _sideCache, null);
                _sideCache = default;
                _sidePipelineCount = 0;
            }
        }
'''

FINALLY_OLD = '''            finally
            {
                _mainCacheLock.Exit();
                _mainCheckpointInProgress = false;
            }
'''
FINALLY_NEW = '''            finally
            {
                // RewindBox (adapt_checkpoint_side_cache): the side cache joins main before the main lock is released.
                MergeSideCache();
                _mainCacheLock.Exit();
                _mainCheckpointInProgress = false;
            }
'''

DISPOSE_OLD = '''            _api.DestroyPipelineCache(_device, _mainState.Cache, null);
        }
    }
}
'''
DISPOSE_NEW = '''            _api.DestroyPipelineCache(_device, _mainState.Cache, null);

            if (_sideCache.Handle != 0)
            {
                _api.DestroyPipelineCache(_device, _sideCache, null);
            }
        }
    }
}
'''

COMPUTE_OLD = '''                if (gd.PipelineCacheManager.IsMainCache(cache))
                {
                    lock (gd.PipelineCreationLock)
                    {
                        result = gd.Api.CreateComputePipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                    }
                }
'''
COMPUTE_NEW = '''                if (gd.PipelineCacheManager.IsMainCache(cache))
                {
                    // RewindBox (adapt_checkpoint_side_cache): never waits for a play-time checkpoint of the main cache.
                    gd.PipelineCacheManager.EnterMainCreation(gd.PipelineCreationLock, false, out PipelineCache target);

                    try
                    {
                        result = gd.Api.CreateComputePipelines(device, target, 1, &pipelineCreateInfo, null, &pipelineHandle);
                    }
                    finally
                    {
                        gd.PipelineCacheManager.ExitMainCreation(gd.PipelineCreationLock, target);
                    }
                }
'''

GRAPHICS_OLD = '''                    bool lockTaken = false;

                    try
                    {
                        if (failOnCompileRequired)
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
                        else
                        {
                            gd.PipelineCreationLock.Enter();
                            lockTaken = true;
                        }

                        result = lockTaken
                            ? gd.Api.CreateGraphicsPipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle)
                            : Result.PipelineCompileRequired;
                    }
                    finally
                    {
                        if (lockTaken)
                        {
                            gd.PipelineCreationLock.Exit();
                        }
                    }
'''
GRAPHICS_NEW = '''                    // RewindBox (adapt_checkpoint_side_cache): during a play-time checkpoint of the main cache the creation goes
                    // to the side cache, so it neither waits for the checkpoint nor fails (no skipped draw).
                    bool lockTaken = gd.PipelineCacheManager.EnterMainCreation(
                        gd.PipelineCreationLock, failOnCompileRequired, out PipelineCache target);

                    try
                    {
                        result = lockTaken
                            ? gd.Api.CreateGraphicsPipelines(device, target, 1, &pipelineCreateInfo, null, &pipelineHandle)
                            : Result.PipelineCompileRequired;
                    }
                    finally
                    {
                        if (lockTaken)
                        {
                            gd.PipelineCacheManager.ExitMainCreation(gd.PipelineCreationLock, target);
                        }
                    }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    manager = paths['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs']
    once(manager, FIELDS_OLD, FIELDS_NEW)
    once(manager, FINALLY_OLD, FINALLY_NEW)
    once(manager, DISPOSE_OLD, DISPOSE_NEW)
    state = paths['src/Ryujinx.Graphics.Vulkan/PipelineState.cs']
    once(state, COMPUTE_OLD, COMPUTE_NEW)
    once(state, GRAPHICS_OLD, GRAPHICS_NEW)
    return list(paths.values())
