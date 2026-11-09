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
lock and with the checkpoint protocol (render-thread creations go to the side cache meanwhile, nothing waits). The
announcement of that protocol becomes a count of holders for every holder of the file (background load, play-time and
pause checkpoints, shares): a holder that fails to take the lock, or releases it, withdraws only its own announcement (a
flag cleared by one holder could hide another's, and a render-thread creation would then wait for the lock). Main's
budget is checked against an estimate (measured bytes plus each merge's credit, the worker's estimated growth since its
last share), before taking the lock and again under it; it is not the native memory. Not done
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
        // these libraries. As a play-time checkpoint: announced before the lock is tried and withdrawn after it is released
        // (a count: it never withdraws another holder's announcement), so render-thread creations go to the side cache.
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

            // An estimate (main's measured bytes plus what merges credited since, and the worker's growth since its last
            // share), not the native memory: a cheap early refusal, checked again under the lock.
            if (main.EstimatedBytes + SharedGrowth(state) > main.Budget)
            {
                Interlocked.Increment(ref _sharesBudget);
                return;
            }

            Interlocked.Increment(ref _mainCheckpointHolders);

            if (!_mainCacheLock.TryEnter())
            {
                Interlocked.Decrement(ref _mainCheckpointHolders);
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

                // Admission again under the lock: a checkpoint, a recycle's preservation or another worker's share may have
                // moved main's estimate since the check above.
                long growth = SharedGrowth(state);

                if (main.EstimatedBytes + growth > main.Budget)
                {
                    Interlocked.Increment(ref _sharesBudget);
                    return;
                }

                ReadOnlySpan<PipelineCache> source = stackalloc PipelineCache[] { state.Cache };

                if (MergeInto(main.Cache, source))
                {
                    Interlocked.Increment(ref main.Generation);
                    state.MergedGeneration = Interlocked.Read(ref state.Generation);
                    main.OnMerged(growth);
                    state.SharedBytes = state.EstimatedBytes;

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
                Interlocked.Decrement(ref _mainCheckpointHolders);
            }

            if (line != null)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, line);
            }
        }

        // RewindBox (adapt_worker_library_share): an upper bound of what this worker's cache can add to main since its last
        // share (its estimated growth; the merge copies only what main lacks).
        private static long SharedGrowth(CacheState state) => Math.Max(0, state.EstimatedBytes - state.SharedBytes);

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

# The checkpoint announcement as a count of holders (every holder in this file: the background load, the play-time and
# pause checkpoints, the shares): an operation that fails to take the lock, or releases it, withdraws only its own.
FLAG_OLD = '''        private volatile bool _mainCheckpointInProgress;

        // A render-thread creation that would only try the lock waits for it while a checkpoint holds it (no skipped draw).
        public bool MainCheckpointInProgress => _mainCheckpointInProgress;
'''
FLAG_NEW = '''        // RewindBox (adapt_worker_library_share): the holders that announce the main lock (background load, checkpoints, shares),
        // a count so that one never withdraws another's announcement (was a flag each holder set and cleared).
        private int _mainCheckpointHolders;

        // A render-thread creation that would only try the lock waits for it while a checkpoint holds it (no skipped draw).
        public bool MainCheckpointInProgress => Volatile.Read(ref _mainCheckpointHolders) != 0;
'''
ENTER_OLD = '''                if (_mainCheckpointInProgress)
                {
'''
ENTER_NEW = '''                if (Volatile.Read(ref _mainCheckpointHolders) != 0) // RewindBox (adapt_worker_library_share)
                {
'''
LOAD_START_OLD = '''                // The checkpoint protocol: render-thread creations go to the side cache while the main lock is held.
                _mainCheckpointInProgress = true;
'''
LOAD_START_NEW = '''                // The checkpoint protocol: render-thread creations go to the side cache while the main lock is held.
                Interlocked.Increment(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)
'''
LOAD_END_OLD = '''                    _mainCacheLock.Exit();
                    _mainCheckpointInProgress = false;
                }
'''
LOAD_END_NEW = '''                    _mainCacheLock.Exit();
                    Interlocked.Decrement(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)
                }
'''
CHECKPOINT_START_OLD = '''            _mainCheckpointInProgress = true;

            if (!_mainCacheLock.TryEnter())
            {
                _mainCheckpointInProgress = false;
                return;
            }
'''
CHECKPOINT_START_NEW = '''            Interlocked.Increment(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)

            if (!_mainCacheLock.TryEnter())
            {
                Interlocked.Decrement(ref _mainCheckpointHolders);
                return;
            }
'''
CHECKPOINT_END_OLD = '''                // RewindBox (adapt_checkpoint_side_cache): the side cache joins main before the main lock is released.
                MergeSideCache();
                _mainCacheLock.Exit();
                _mainCheckpointInProgress = false;
'''
CHECKPOINT_END_NEW = '''                // RewindBox (adapt_checkpoint_side_cache): the side cache joins main before the main lock is released.
                MergeSideCache();
                _mainCacheLock.Exit();
                Interlocked.Decrement(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)
'''
PAUSE_START_OLD = '''            _mainCheckpointInProgress = true;
            _mainCacheLock.Enter();
'''
PAUSE_START_NEW = '''            Interlocked.Increment(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)
            _mainCacheLock.Enter();
'''
PAUSE_END_OLD = '''            {
                MergeSideCache();
                _mainCacheLock.Exit();
                _mainCheckpointInProgress = false;
            }
'''
PAUSE_END_NEW = '''            {
                MergeSideCache();
                _mainCacheLock.Exit();
                Interlocked.Decrement(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)
            }
'''
QUEUE_OLD = '''            if (!string.IsNullOrEmpty(_mainState.Path) && !_mainCheckpointInProgress &&
'''
QUEUE_NEW = '''            if (!string.IsNullOrEmpty(_mainState.Path) && Volatile.Read(ref _mainCheckpointHolders) == 0 && // adapt_worker_library_share
'''
# CacheState: what this worker had shared, and main's credit for merged content (replaced by the next measure).
STATE_FIELDS_OLD = '''            public bool FileInCache = true;
            public bool FileOutsideMain;
'''
STATE_FIELDS_NEW = '''            public bool FileInCache = true;
            public bool FileOutsideMain;
            // RewindBox (adapt_worker_library_share): this worker's estimated bytes at its last share into main.
            public long SharedBytes;
'''
ON_MERGED_OLD = '''            public void OnRecreated(PipelineCache cache)
            {
                Cache = cache;
'''
ON_MERGED_NEW = '''            // RewindBox (adapt_worker_library_share): content merged into this cache, an upper bound until the next measure.
            public void OnMerged(long bytes)
            {
                _measuredBytes += bytes;
            }

            public void OnRecreated(PipelineCache cache)
            {
                Cache = cache;
                SharedBytes = 0; // RewindBox (adapt_worker_library_share): a new, empty cache
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


PROTOCOL = [(STATE_FIELDS_OLD, STATE_FIELDS_NEW), (ON_MERGED_OLD, ON_MERGED_NEW), (FLAG_OLD, FLAG_NEW), (ENTER_OLD, ENTER_NEW),
            (LOAD_START_OLD, LOAD_START_NEW), (LOAD_END_OLD, LOAD_END_NEW), (CHECKPOINT_START_OLD, CHECKPOINT_START_NEW),
            (CHECKPOINT_END_OLD, CHECKPOINT_END_NEW), (PAUSE_START_OLD, PAUSE_START_NEW), (PAUSE_END_OLD, PAUSE_END_NEW),
            (QUEUE_OLD, QUEUE_NEW)]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[STATE], COMPUTE_OLD, COMPUTE_NEW)
    once(paths[STATE], GRAPHICS_OLD, GRAPHICS_NEW)
    for old, new in PROTOCOL:
        once(paths[MANAGER], old, new)
    once(paths[MANAGER], NOTIFY_OLD, NOTIFY_NEW)
    once(paths[MANAGER], CLOSE_OLD, CLOSE_NEW)
    assert '_mainCheckpointInProgress' not in paths[MANAGER].read_text(encoding='utf-8'), 'every holder counts'
    return list(paths.values())
