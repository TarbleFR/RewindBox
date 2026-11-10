"""The worker pipeline cache snapshots join the main cache at startup, and the main cache gets 1 GiB.

IPA 674, private journals, not in the repository (Hogwarts Legacy, player 1, 6-7 Nov):
- every launch maps the main cache (301 -> 575 -> 580 MiB) and both worker snapshots (up to 128 MiB each); worker 0 is
  then recycled within 10-30 s (128-208 MiB), so the worker snapshots are loaded only to be thrown away, while their
  memory counts in a footprint that reached 5.3 GB with iOS memory warnings;
- a recycled worker joins main only when main has room under its 768 MiB budget: with main at 580 MiB, a 208 MiB worker
  was dropped with its pipelines;
- once main passes 768 MiB it is never written again ("it will not be persisted until it fits"); an earlier full
  Hogwarts cache held 3574 shaders in 747.90 MiB, at the edge of that budget.

Change (PipelineCacheManager.cs, every title):
- at startup, beside a loaded main snapshot, each worker snapshot that fits is merged into main and the worker restarts empty (the existing recycle path),
  so its content is kept once, in main, and the worker's own copy is released;
- the main budget becomes 1 GiB (worker budgets unchanged, 128 MiB each with two workers): the whole Hogwarts shader set
  keeps being persisted, and a recycled worker finds room in main;
- until main has been written after that merge, a worker does not overwrite its snapshot file, so a crash before the next
  main checkpoint loses nothing.
Close, checkpoints, the side cache and recycling rules are otherwise unchanged.
Fail closed on drift: the file must be the Core 679 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs': '4ff755fcc9917f1e74b377fba8931a92902eba3472a785ded0298a8a470c7a81',
}

BUDGET_OLD = '''        private const long TotalCacheBudget = 1024L * 1024 * 1024;
        private const long MainCacheBudget = TotalCacheBudget * 3 / 4;
'''
BUDGET_NEW = '''        // RewindBox (adapt_pipeline_cache_room): main 1 GiB (a full Hogwarts Legacy shader set held 747.90 MiB at the old
        // 768 MiB edge, and main is never written again past its budget); the workers keep 256 MiB between them.
        private const long TotalCacheBudget = 1280L * 1024 * 1024;
        private const long MainCacheBudget = 1024L * 1024 * 1024;
'''

FIELD_OLD = '''        private int _warnedMainCacheOverBudget;
'''
FIELD_NEW = '''        private int _warnedMainCacheOverBudget;

        // RewindBox (adapt_pipeline_cache_room): main generation that holds the worker snapshots merged at startup; until
        // main is written at or past it, a worker does not overwrite its snapshot file.
        private long _workerSnapshotsHeldUntil;
'''

STARTUP_OLD = '''            Logger.Notice.PrintMsg(
                LogClass.Gpu,
                $"Vulkan pipeline cache initialized: {FormatSize(mainSnapshotBytes)} main data, " +
'''
STARTUP_NEW = '''            // RewindBox (adapt_pipeline_cache_room): a worker snapshot that fits joins main now and the worker restarts
            // empty, so its pipelines are kept once (in main) instead of being loaded, then recycled within seconds.
            int mergedWorkers = 0;
            long mergedBytes = 0;

            for (int index = 0; index < workerCount; index++)
            {
                CacheState worker = _workerStates[index];

                // Only beside a loaded main snapshot (the duplicate being removed); with no main snapshot the worker keeps it.
                if (!worker.HasUsableSnapshot || !_mainState.HasUsableSnapshot)
                {
                    continue;
                }

                long workerSize = GetCacheDataSize(worker);
                long mainSize = GetCacheDataSize(_mainState);

                if (workerSize <= 0 || mainSize < 0 || mainSize > _mainState.Budget - workerSize)
                {
                    continue;
                }

                long generation = Interlocked.Read(ref _mainState.Generation);

                Recycle(worker, workerSize);

                if (Interlocked.Read(ref _mainState.Generation) != generation)
                {
                    mergedWorkers++;
                    mergedBytes += workerSize;
                    _workerSnapshotsHeldUntil = Interlocked.Read(ref _mainState.Generation);
                }
            }

            if (mergedWorkers != 0)
            {
                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Merged {mergedWorkers} Vulkan worker pipeline cache snapshots ({FormatSize(mergedBytes)}) into the main " +
                    "cache at startup; the workers start empty (adapt_pipeline_cache_room).");
            }

            Logger.Notice.PrintMsg(
                LogClass.Gpu,
                $"Vulkan pipeline cache initialized: {FormatSize(mainSnapshotBytes)} main data, " +
'''

SAVE_OLD = '''            SaveCache(state, size, force);
        }
'''
SAVE_NEW = '''            // RewindBox (adapt_pipeline_cache_room): a worker snapshot merged at startup stays on disk until main holds it.
            if (!ReferenceEquals(state, _mainState) &&
                Interlocked.Read(ref _mainState.SavedGeneration) < Interlocked.Read(ref _workerSnapshotsHeldUntil))
            {
                return;
            }

            SaveCache(state, size, force);
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    manager = paths['src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs']
    once(manager, BUDGET_OLD, BUDGET_NEW)
    once(manager, FIELD_OLD, FIELD_NEW)
    once(manager, STARTUP_OLD, STARTUP_NEW)
    once(manager, SAVE_OLD, SAVE_NEW)
    return list(paths.values())
