"""A background worker publishes the Metal libraries it compiled to the main pipeline cache during play, so the next worker
asked for a compatible variant finds them instead of converting and compiling the same MSL again (Core 717, lot 8, every
title).

MoltenVK v1.4.2 keeps its Metal libraries per VkPipelineCache (MVKPipelineCache::_shaderCache: per shader module code hash,
one library per SPIR-V to MSL configuration). MeloNX's pipeline workers take any queued work item and compile into their
own cache after a non-blocking lookup in the main cache (adapt_worker_main_cache_lookup). A worker cache reached main only
before a recycle (PreserveBeforeRecycle) and at the close (MergeAndSave), so two variants of one new program taken by two
workers converted and compiled the same libraries twice in a session (the lookup in main finds a library only once main
holds it; the pipeline state itself is compiled per pipeline either way).

Change: when a worker creation was compiled in the worker's own cache (the lookup in main did not serve it), the worker
merges its cache into main right after (vkMergePipelineCaches copies library references, no compilation), under the main
lock and with the checkpoint protocol (render-thread creations go to the side cache meanwhile, nothing waits). Not done
when the main lock is held (the next own compilation tries again), when main is Frozen or disposed, when main's estimate
plus the worker's would pass main's budget, or when device memory is low (PipelineVariantJournal.LowDevicePercent).
The merge is counted as PreserveBeforeRecycle's: main's generation moves, the worker's merged generation is its current
one (MergeAndSave merges nothing it holds already), and a worker whose file is its cache's has nothing outside main.
Only requests that come after a publication benefit: two workers compiling the same library at the same moment still
both compile it. A merged library costs a copy of its compressed MSL in main while the worker cache holds the original.
Counted: one log line every 64 merges and at the close. Fail closed on drift: both files must be the Core 715
preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
BASELINE = {
    MANAGER: '3721ea7d7a67ea0ce71e5609ff8b959f94a625aa2b2a4b070915360ad04ca25d',
    STATE: 'a8877cbf67f77fc981eb10f8214d3ec742a82764137af9e02972be7d676f18f6',
}

COMPUTE_OLD = '''                    if (result != Result.Success)
                    {
                        result = gd.Api.CreateComputePipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                    }
'''
COMPUTE_NEW = '''                    if (result != Result.Success)
                    {
                        result = gd.Api.CreateComputePipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                        PipelineCacheManager.WorkerCompiledOwn = result == Result.Success; // RewindBox (adapt_worker_library_share)
                    }
'''
GRAPHICS_OLD = '''                    if (result != Result.Success)
                    {
                        result = gd.Api.CreateGraphicsPipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                    }
'''
GRAPHICS_NEW = '''                    if (result != Result.Success)
                    {
                        result = gd.Api.CreateGraphicsPipelines(device, cache, 1, &pipelineCreateInfo, null, &pipelineHandle);
                        PipelineCacheManager.WorkerCompiledOwn = result == Result.Success; // RewindBox (adapt_worker_library_share)
                    }
'''

NOTIFY_OLD = '''            state.PipelineCount++;
            Interlocked.Increment(ref state.Generation);

            Maintain(state, force: false);
            CheckpointMainIfDue();
        }
'''
NOTIFY_NEW = '''            state.PipelineCount++;
            Interlocked.Increment(ref state.Generation);

            Maintain(state, force: false);
            ShareWithMain(state); // RewindBox (adapt_worker_library_share)
            CheckpointMainIfDue();
        }

        // RewindBox (adapt_worker_library_share): set on a worker thread when its creation was compiled in its own cache (the
        // non-blocking lookup in main did not serve it); read and cleared by the same thread after the work item.
        [ThreadStatic]
        internal static bool WorkerCompiledOwn;
        private long _shares, _shareTicks, _shareMaxTicks, _sharesBusy, _sharesMemory, _sharesBudget;

        // RewindBox (adapt_worker_library_share): on the worker thread that owns `state`, after a pipeline it compiled in its own
        // cache: its cache joins main (library references copied, nothing compiled), so the next worker's lookup in main finds
        // these libraries. As a play-time checkpoint: render-thread creations go to the side cache while main's lock is held.
        private void ShareWithMain(CacheState state)
        {
            bool compiled = WorkerCompiledOwn;
            WorkerCompiledOwn = false;
            CacheState main = _mainState;

            if (!compiled || _disposed || main.Frozen || Interlocked.Read(ref state.Generation) == state.MergedGeneration)
            {
                return;
            }

            if (PipelineVariantJournal.DeviceAvailablePercent() <= PipelineVariantJournal.LowDevicePercent)
            {
                Interlocked.Increment(ref _sharesMemory);
                return;
            }

            if (main.EstimatedBytes + state.EstimatedBytes > main.Budget)
            {
                Interlocked.Increment(ref _sharesBudget);
                return;
            }

            _mainCheckpointInProgress = true;

            if (!_mainCacheLock.TryEnter())
            {
                _mainCheckpointInProgress = false;
                Interlocked.Increment(ref _sharesBusy);
                return;
            }

            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            string line = null;

            try
            {
                if (_disposed || main.Frozen)
                {
                    return;
                }

                ReadOnlySpan<PipelineCache> source = stackalloc PipelineCache[] { state.Cache };

                if (MergeInto(main.Cache, source))
                {
                    Interlocked.Increment(ref main.Generation);
                    state.MergedGeneration = Interlocked.Read(ref state.Generation);

                    // As PreserveBeforeRecycle: main holds this cache, so its file's content if the file is of it.
                    if (state.FileInCache)
                    {
                        state.FileOutsideMain = false;
                    }

                    long ticks = System.Diagnostics.Stopwatch.GetTimestamp() - start;
                    _shareTicks += ticks;
                    _shareMaxTicks = Math.Max(_shareMaxTicks, ticks);

                    if (++_shares % 64 == 0)
                    {
                        line = ShareSummaryLocked("during play");
                    }
                }
            }
            finally
            {
                MergeSideCache();
                _mainCacheLock.Exit();
                _mainCheckpointInProgress = false;
            }

            if (line != null)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, line);
            }
        }

        private string ShareSummaryLocked(string window)
        {
            double frequency = System.Diagnostics.Stopwatch.Frequency / 1000.0;

            return string.Format(System.Globalization.CultureInfo.InvariantCulture,
                "Worker libraries shared with the main cache ({0}): {1} merges in {2:F1} ms (longest {3:F1} ms), not shared: main " +
                "busy {4}, memory low {5}, over budget {6} (adapt_worker_library_share).",
                window, _shares, _shareTicks / frequency, _shareMaxTicks / frequency, Interlocked.Read(ref _sharesBusy),
                Interlocked.Read(ref _sharesMemory), Interlocked.Read(ref _sharesBudget));
        }
'''

CLOSE_OLD = '''            bool mainFileHoldsWorkers = false; // RewindBox (adapt_pipeline_snapshot_retire)

            lock (_mainCacheLock)
            {
'''
CLOSE_NEW = '''            bool mainFileHoldsWorkers = false; // RewindBox (adapt_pipeline_snapshot_retire)

            lock (_mainCacheLock)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, ShareSummaryLocked("session, at close")); // RewindBox (adapt_worker_library_share)
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[STATE], COMPUTE_OLD, COMPUTE_NEW)
    once(paths[STATE], GRAPHICS_OLD, GRAPHICS_NEW)
    once(paths[MANAGER], NOTIFY_OLD, NOTIFY_NEW)
    once(paths[MANAGER], CLOSE_OLD, CLOSE_NEW)
    return list(paths.values())
