"""Preserve worker pipeline work before bounded cache recycling, when it fits.

The 29 October Hogwarts log recycles a 69.06 MiB worker cache after a
31.34 MiB checkpoint. Recycle previously destroyed everything since that
checkpoint. Merge into the main cache before destruction when the sum of the
measured sizes fits its existing snapshot budget. This is a conservative
admission estimate, not a guaranteed bound on an opaque driver's merged size.
Measure again afterwards; an over-budget main cache admits no further worker
preservations and retains its existing refusal to persist oversized snapshots.
The main budget was already a persistence budget, not a hard live-memory cap.
Hold the main cache's creation lock;
the worker owns its source cache throughout the operation. Do not export to
disk on the worker, wait on GPU work, raise budgets or retain old cache handles.
When sizing/merge fails or space is insufficient, keep the original bounded
recycle behavior and the previous on-disk checkpoint.
If the fresh worker stays empty, keep its last accepted/successfully written
checkpoint rather than replacing useful warm-start data with an empty cache.
Rejected snapshots retain their existing replacement path.
"""
from adapt_session import once


def apply(source):
    manager = source / 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
    once(manager, '''            public long MergedGeneration;
''', '''            public long MergedGeneration;
            public bool Recycled;
            public bool HasUsableSnapshot;
''')
    once(manager, '''                SavedGeneration = Generation;
''', '''                SavedGeneration = Generation;
                HasUsableSnapshot = loadedBytes > 0 && !snapshotRejected;
''')
    once(manager, '''                Interlocked.Increment(ref Generation);
''', '''                Interlocked.Increment(ref Generation);
                Recycled = true;
''')
    once(manager, '''        private void Maintain(CacheState state, bool force, bool allowRecycle = true)
        {
''', '''        private void Maintain(CacheState state, bool force, bool allowRecycle = true)
        {
            if (state.Recycled && state.PipelineCount == 0 && state.HasUsableSnapshot &&
                !ReferenceEquals(state, _mainState))
            {
                // An empty replacement must not overwrite the last useful worker
                // checkpoint. Rejected snapshots are not marked usable.
                return;
            }

''')
    once(manager, '''                state.SavedGeneration = generation;
''', '''                state.SavedGeneration = generation;
                state.HasUsableSnapshot = true;
''')
    once(manager, '''            PipelineCache outgrown = state.Cache;

            state.OnRecreated(replacement);
''', '''            PipelineCache outgrown = state.Cache;

            PreserveBeforeRecycle(state, size);
            state.OnRecreated(replacement);
''')
    once(manager, '''        private unsafe bool MergeInto(PipelineCache destination, ReadOnlySpan<PipelineCache> sources)
''', '''        private void PreserveBeforeRecycle(CacheState worker, long size)
        {
            if (ReferenceEquals(worker, _mainState) || size <= 0 || size > _mainState.Budget)
            {
                return;
            }

            lock (_mainCacheLock)
            {
                // Main pipeline creation uses this same lock. The worker that
                // invokes Maintain is the only writer of its source cache.
                // Opaque merged size can exceed this admission estimate;
                // OnMeasured below prevents subsequent admissions in that case.
                long mainSize = GetCacheDataSize(_mainState);

                if (mainSize < 0 || mainSize > _mainState.Budget - size)
                {
                    return;
                }

                ReadOnlySpan<PipelineCache> source = stackalloc PipelineCache[] { worker.Cache };

                if (MergeInto(_mainState.Cache, source))
                {
                    Interlocked.Increment(ref _mainState.Generation);

                    long mergedSize = GetCacheDataSize(_mainState);

                    if (mergedSize >= 0)
                    {
                        _mainState.OnMeasured(mergedSize);
                    }
                }
            }
        }

        private unsafe bool MergeInto(PipelineCache destination, ReadOnlySpan<PipelineCache> sources)
''')
    return [manager]
