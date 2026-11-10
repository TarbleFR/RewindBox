"""The main Vulkan pipeline cache snapshot loads on a background thread: games no longer wait for it (Core 697).

IPA 693 (8 Nov, Hogwarts Legacy and Super Smash Bros. Ultimate, pids 38333-38401): every launch stopped in gpuStartup
mainPipelineCache; the one the maintainer waited for ended after 536 104 ms (about 9 min, then the game); IPA 692 and
every build before: 2.2-3.0 s. MoltenVK 1.4.2 MVKPipelineCache::readData builds an MVKShaderLibrary per entry and that
constructor compiles its MSL synchronously (MVKShaderLibrary::compileLibrary, newLibraryWithSource): creating the cache
from the 780 MiB Hogwarts snapshot recompiles every Metal library ever cached, fast only while the system Metal
compiler cache is warm. Startup also merged the worker snapshots into main (1.4 s, adapt_pipeline_cache_room).

Change:
- PipelineCacheManager starts main (and, beside it, the workers) empty and loads the snapshots on the thread
  RewindBox.PipelineCacheLoad (the worker snapshots join main there, as adapt_pipeline_cache_room did at startup, and
  the workers keep their files until main is written with them); MoltenVK's
  result is merged into main under the main lock with the checkpoint protocol (render-thread creations go to the side
  cache meanwhile, merged before the lock is released). Until then main is Frozen (no checkpoint, pause or final write
  can replace the file with less than it holds) and the worker snapshots stay as loaded (the startup merge requires a
  loaded main). A rejected snapshot is handled as before (main starts empty and is written later).
- Workers that look a pipeline up in main first (adapt_worker_main_cache_lookup) wait for the load, at most 15 s from
  the start of the session, instead of compiling again what the snapshot holds.
- If the session ends while MoltenVK still loads (a cold Metal cache), the session does not wait: VulkanRenderer leaves
  the device and instance release to the loader thread, which destroys its cache and then them once MoltenVK returns;
  the snapshot file was not written, so nothing is lost.
Fail closed on drift: the files must be the Core 693 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
RENDERER = 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs'
BASELINE = {
    MANAGER: 'cb88dec93c4f083b9c61498967c0a60492cec2feaf8608e11d864d0d92c7fa12',
    STATE: '1d4f227a64b5d9a6d4f582458a3ab4a60aae37c3f465ea11b3c558dfc47c5e55',
    RENDERER: '16b7141983efcc0ab7909f345da41a1d0ffa91306c81c7368b9725ee67ae19c6',
}

FIELDS_OLD = '''        private long _workerSnapshotsHeldUntil;
'''
FIELDS_NEW = '''        private long _workerSnapshotsHeldUntil;

        // RewindBox (adapt_pipeline_cache_background): MoltenVK compiles every Metal library of a snapshot while it
        // creates a cache from it, so the main snapshot is loaded on its own thread and merged into main.
        internal const int MainLoadWorkerWaitMs = 15_000;
        private readonly object _mainLoadLock = new();
        private readonly ManualResetEventSlim _mainLoaded = new(true);
        private MappedSnapshot _pendingMainSnapshot;
        private MappedSnapshot[] _pendingWorkerSnapshots;
        private bool _mainLoadRunning;
        private Action _deferredDeviceRelease;
        private long _mainLoadWaitDeadline;
        // Moves when a load is merged: a teardown that saved while main was Frozen sees it and saves again.
        private long _mainLoadCompletions;

        // Whether main still lacks its snapshot (the background load has not merged it yet).
        public bool MainLoadPending => !_mainLoaded.IsSet;

        // RewindBox (adapt_pipeline_cache_background): a worker looking a pipeline up in main waits for its snapshot, at
        // most until 15 s after the session started, instead of compiling again what the snapshot holds.
        public void WaitForMainLoadOnWorker()
        {
            if (_mainLoaded.IsSet)
            {
                return;
            }

            long remaining = Interlocked.Read(ref _mainLoadWaitDeadline) - Environment.TickCount64;

            if (remaining > 0)
            {
                _mainLoaded.Wait((int)Math.Min(remaining, int.MaxValue));
            }
        }

        // RewindBox (adapt_pipeline_cache_background): while MoltenVK still loads the main snapshot, the loader thread
        // releases the device and instance once it returns, instead of the session waiting for it.
        public bool DeferDeviceRelease(Action release)
        {
            lock (_mainLoadLock)
            {
                if (!_mainLoadRunning)
                {
                    return false;
                }

                _deferredDeviceRelease = release;
                return true;
            }
        }

        private void StartMainLoad()
        {
            MappedSnapshot snapshot = _pendingMainSnapshot;
            _pendingMainSnapshot = null;

            if (snapshot == null)
            {
                return;
            }

            _mainLoaded.Reset();
            _mainLoadRunning = true;
            Interlocked.Exchange(ref _mainLoadWaitDeadline, Environment.TickCount64 + MainLoadWorkerWaitMs);

            try
            {
                Thread loader = new(() => LoadMainSnapshot(snapshot))
                {
                    IsBackground = true,
                    Name = "RewindBox.PipelineCacheLoad",
                };

                loader.Start();
            }
            catch (Exception exception) when (exception is OutOfMemoryException || exception is ThreadStartException)
            {
                // No thread: load it here, as before.
                LoadMainSnapshot(snapshot);
            }
        }

        private unsafe void LoadMainSnapshot(MappedSnapshot snapshot)
        {
            long start = Environment.TickCount64;
            long length = snapshot.Length;
            MappedSnapshot[] workerSnapshots = _pendingWorkerSnapshots ?? Array.Empty<MappedSnapshot>();
            _pendingWorkerSnapshots = null;
            PipelineCache[] workerStaging = new PipelineCache[workerSnapshots.Length];
            long[] workerLengths = new long[workerSnapshots.Length];

            try
            {
                PipelineCache staging = default;
                bool accepted = false;
                // A failure other than the driver rejecting the snapshot leaves main Frozen for the session: the file is
                // not replaced by less than it holds.
                bool failed = false;

                try
                {
                    staging = CreateCache(snapshot, "main", out accepted);
                }
                catch (Exception exception)
                {
                    failed = true;
                    Logger.Warning?.PrintMsg(LogClass.Gpu, $"Vulkan main pipeline cache snapshot not loaded: {exception.Message}");
                }
                finally
                {
                    snapshot.Dispose();
                }

                // The worker snapshots load here too, outside the main lock.
                for (int index = 0; index < workerSnapshots.Length; index++)
                {
                    MappedSnapshot workerSnapshot = workerSnapshots[index];

                    if (workerSnapshot == null)
                    {
                        continue;
                    }

                    try
                    {
                        workerLengths[index] = workerSnapshot.Length;
                        workerStaging[index] = CreateCache(workerSnapshot, $"worker {index}", out bool workerAccepted);

                        if (!workerAccepted)
                        {
                            _api.DestroyPipelineCache(_device, workerStaging[index], null);
                            workerStaging[index] = default;
                        }
                    }
                    catch (Exception exception)
                    {
                        Logger.Warning?.PrintMsg(LogClass.Gpu, $"Vulkan worker {index} pipeline cache snapshot not loaded: {exception.Message}");
                    }
                    finally
                    {
                        workerSnapshot.Dispose();
                    }
                }

                // The checkpoint protocol: render-thread creations go to the side cache while the main lock is held.
                _mainCheckpointInProgress = true;
                _mainCacheLock.Enter();

                try
                {
                    if (!_disposed)
                    {
                        if (accepted && staging.Handle != 0)
                        {
                            ReadOnlySpan<PipelineCache> source = stackalloc PipelineCache[] { staging };

                            if (!MergeInto(_mainState.Cache, source))
                            {
                                accepted = false;
                                failed = true;
                            }
                        }

                        if (accepted)
                        {
                            // The file holds this content already: no new generation.
                            _mainState.HasUsableSnapshot = true;
                        }
                        else if (!failed)
                        {
                            // As a rejected snapshot at startup: main is not the file's state.
                            Interlocked.Exchange(ref _mainWrittenBytes, 0);
                            Interlocked.Increment(ref _mainState.Generation);
                        }

                        // As adapt_pipeline_cache_room at startup: each worker snapshot that fits joins main. Main then holds
                        // content its file does not; the workers keep their files until main is written at or past it,
                        // and for this session if a worker snapshot could not join main.
                        long room = failed ? 0 : _mainState.Budget - _mainState.EstimatedBytes;
                        int pendingWorkers = 0;
                        int mergedWorkers = 0;
                        long mergedBytes = 0;

                        for (int index = 0; index < workerSnapshots.Length; index++)
                        {
                            if (workerSnapshots[index] == null)
                            {
                                continue;
                            }

                            pendingWorkers++;

                            if (!failed && workerStaging[index].Handle != 0 && workerLengths[index] <= room &&
                                MergeInto(_mainState.Cache, workerStaging.AsSpan(index, 1)))
                            {
                                mergedWorkers++;
                                mergedBytes += workerLengths[index];
                                room -= workerLengths[index];
                            }
                        }

                        if (mergedWorkers != 0)
                        {
                            long held = Interlocked.Increment(ref _mainState.Generation);

                            if (mergedWorkers == pendingWorkers)
                            {
                                Interlocked.Exchange(ref _workerSnapshotsHeldUntil, held);
                            }
                        }
                        else if (pendingWorkers == 0)
                        {
                            Interlocked.Exchange(ref _workerSnapshotsHeldUntil, 0);
                        }

                        _mainState.Frozen = failed;
                        MergeSideCache();
                        Interlocked.Increment(ref _mainLoadCompletions);

                        Logger.Info?.PrintMsg(
                            LogClass.Gpu,
                            $"Vulkan main pipeline cache {(accepted ? "loaded" : failed ? "not loaded (its file is kept)" : "rejected")} in the background: " +
                            $"{FormatSize(length)}, {mergedWorkers}/{pendingWorkers} worker snapshots ({FormatSize(mergedBytes)}) joined, " +
                            $"in {Environment.TickCount64 - start} ms (adapt_pipeline_cache_background).");
                    }

                    if (staging.Handle != 0)
                    {
                        _api.DestroyPipelineCache(_device, staging, null);
                    }

                    foreach (PipelineCache workerCache in workerStaging)
                    {
                        if (workerCache.Handle != 0)
                        {
                            _api.DestroyPipelineCache(_device, workerCache, null);
                        }
                    }
                }
                finally
                {
                    _mainCacheLock.Exit();
                    _mainCheckpointInProgress = false;
                }
            }
            catch (Exception exception)
            {
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Vulkan main pipeline cache background load failed: {exception.Message}");
            }
            finally
            {
                Action release;

                lock (_mainLoadLock)
                {
                    _mainLoadRunning = false;
                    release = _deferredDeviceRelease;
                    _deferredDeviceRelease = null;
                }

                _mainLoaded.Set();

                try
                {
                    release?.Invoke();
                }
                catch (Exception exception)
                {
                    Logger.Warning?.PrintMsg(LogClass.Gpu, $"Vulkan device release after the background load failed: {exception.Message}");
                }
            }
        }
'''

LOAD_OLD = '''            using (new Ryujinx.Common.EmbeddedStartupTrace("mainPipelineCache"))
            using (MappedSnapshot mainSnapshot = OpenSnapshot(mainCachePath, MainCacheBudget))
            {
                mainSnapshotBytes = mainSnapshot?.Length ?? 0;
                mainCache = CreateCache(mainSnapshot, "main", out bool accepted);
                mainSnapshotRejected = mainSnapshot != null && !accepted;
            }

            _mainState = new(
                mainCache,
                mainCachePath,
                "main",
                MainCacheBudget,
                mainSnapshotBytes,
                snapshotRejected: mainSnapshotRejected);

            // RewindBox (adapt_pipeline_cache_growth): what the main file on disk holds.
            _mainWrittenBytes = mainSnapshotRejected ? 0 : mainSnapshotBytes;
'''
LOAD_NEW = '''            // RewindBox (adapt_pipeline_cache_background): main starts empty; its snapshot loads on a background thread
            // started at the end of this constructor and is merged into main when MoltenVK returns.
            using (new Ryujinx.Common.EmbeddedStartupTrace("mainPipelineCache"))
            {
                _pendingMainSnapshot = OpenSnapshot(mainCachePath, MainCacheBudget);
                mainSnapshotBytes = _pendingMainSnapshot?.Length ?? 0;
                mainCache = CreateCache(null, "main");
                mainSnapshotRejected = false;
            }

            _mainState = new(
                mainCache,
                mainCachePath,
                "main",
                MainCacheBudget,
                mainSnapshotBytes,
                snapshotRejected: mainSnapshotRejected);

            if (_pendingMainSnapshot != null)
            {
                // Until the snapshot is merged, nothing writes main and the worker snapshots stay as loaded.
                _mainState.Frozen = true;
                _mainState.HasUsableSnapshot = false;
            }

            // RewindBox (adapt_pipeline_cache_growth): what the main file on disk holds.
            _mainWrittenBytes = mainSnapshotRejected ? 0 : mainSnapshotBytes;
'''

END_OLD = '''            Logger.Notice.PrintMsg(
                LogClass.Gpu,
                $"Vulkan pipeline cache initialized: {FormatSize(mainSnapshotBytes)} main data, " +
                $"{loadedWorkerCaches}/{workerCount} worker snapshots recovered. " +
                $"Budget {FormatSize(MainCacheBudget)} main, {FormatSize(workerBudget)} per worker.");
        }
'''
END_NEW = '''            Logger.Notice.PrintMsg(
                LogClass.Gpu,
                $"Vulkan pipeline cache initialized: {FormatSize(mainSnapshotBytes)} main data" +
                $"{(_pendingMainSnapshot != null ? " (loading in the background)" : "")}, " +
                $"{loadedWorkerCaches}/{workerCount} worker snapshots recovered. " +
                $"Budget {FormatSize(MainCacheBudget)} main, {FormatSize(workerBudget)} per worker.");

            StartMainLoad(); // RewindBox (adapt_pipeline_cache_background)
        }
'''

GRAPHICS_OLD = '''        private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, GraphicsPipelineCreateInfo* info, Pipeline* handle)
        {
            if (!gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation ||
'''
GRAPHICS_NEW = '''        private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, GraphicsPipelineCreateInfo* info, Pipeline* handle)
        {
            gd.PipelineCacheManager.WaitForMainLoadOnWorker(); // RewindBox (adapt_pipeline_cache_background)

            if (!gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation ||
'''
COMPUTE_OLD = '''        private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, ComputePipelineCreateInfo* info, Pipeline* handle)
        {
            if (!gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation ||
'''
COMPUTE_NEW = '''        private static unsafe Result TryCreateFromMainCache(VulkanRenderer gd, Device device, ComputePipelineCreateInfo* info, Pipeline* handle)
        {
            gd.PipelineCacheManager.WaitForMainLoadOnWorker(); // RewindBox (adapt_pipeline_cache_background)

            if (!gd.PipelineCacheManager.SupportsNonBlockingPipelineCreation ||
'''

RELEASE_OLD = '''            SurfaceApi.DestroySurface(_instance.Instance, _surface, null);

            Api.DestroyDevice(_device, null);

            _debugMessenger.Dispose();

            // Last step destroy the instance
            _instance.Dispose();
        }
'''
RELEASE_NEW = '''            SurfaceApi.DestroySurface(_instance.Instance, _surface, null);

            // RewindBox (adapt_pipeline_cache_background): while MoltenVK still loads the main snapshot (a cold system Metal
            // cache), the loader thread releases the device and the instance once it returns; the session does not wait.
            void ReleaseDevice()
            {
                Api.DestroyDevice(_device, null);

                _debugMessenger.Dispose();

                // Last step destroy the instance
                _instance.Dispose();
            }

            if (!PipelineCacheManager.DeferDeviceRelease(ReleaseDevice))
            {
                ReleaseDevice();
            }
        }
'''
WORKERS_OLD = '''            int loadedWorkerCaches = 0;
            
            for (int index = 0; index < workerCount; index++)
            {
                using var startup = new Ryujinx.Common.EmbeddedStartupTrace("workerPipelineCache" + index);
                using MappedSnapshot workerSnapshot = OpenSnapshot(workerCachePaths[index], workerBudget);

                if (workerSnapshot != null)
                {
                    loadedWorkerCaches++;
                }

                string description = $"worker {index}";

                _workerStates[index] = new(
                    CreateCache(workerSnapshot, description, out bool workerSnapshotAccepted),
                    workerCachePaths[index],
                    description,
                    workerBudget,
                    workerSnapshot?.Length ?? 0,
                    snapshotRejected: workerSnapshot != null && !workerSnapshotAccepted);
            }
'''
WORKERS_NEW = '''            int loadedWorkerCaches = 0;
            // RewindBox (adapt_pipeline_cache_background): beside a main snapshot loading in the background, the worker
            // snapshots load with it and join main there (as adapt_pipeline_cache_room does at startup): the workers start
            // empty and do not overwrite their files until main is written with their content.
            _pendingWorkerSnapshots = new MappedSnapshot[workerCount];
            
            for (int index = 0; index < workerCount; index++)
            {
                using var startup = new Ryujinx.Common.EmbeddedStartupTrace("workerPipelineCache" + index);
                MappedSnapshot workerSnapshot = OpenSnapshot(workerCachePaths[index], workerBudget);

                if (workerSnapshot != null)
                {
                    loadedWorkerCaches++;
                }

                string description = $"worker {index}";

                if (workerSnapshot != null && _pendingMainSnapshot != null)
                {
                    _pendingWorkerSnapshots[index] = workerSnapshot;
                    _workerSnapshotsHeldUntil = long.MaxValue;
                    _workerStates[index] = new(CreateCache(null, description), workerCachePaths[index], description, workerBudget, 0);
                    continue;
                }

                using (workerSnapshot)
                {
                    _workerStates[index] = new(
                        CreateCache(workerSnapshot, description, out bool workerSnapshotAccepted),
                        workerCachePaths[index],
                        description,
                        workerBudget,
                        workerSnapshot?.Length ?? 0,
                        snapshotRejected: workerSnapshot != null && !workerSnapshotAccepted);
                }
            }
'''
CONTENT_OLD = '''                long generation = Interlocked.Read(ref _mainState.Generation);

                foreach (CacheState state in _workerStates)
                {
                    generation += Interlocked.Read(ref state.Generation);
                }

                return generation;
'''
CONTENT_NEW = '''                long generation = Interlocked.Read(ref _mainState.Generation);

                foreach (CacheState state in _workerStates)
                {
                    generation += Interlocked.Read(ref state.Generation);
                }

                // RewindBox (adapt_pipeline_cache_background): a load merged after a save seen as complete.
                return generation + Interlocked.Read(ref _mainLoadCompletions);
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    once(paths[MANAGER], FIELDS_OLD, FIELDS_NEW)
    once(paths[MANAGER], LOAD_OLD, LOAD_NEW)
    once(paths[MANAGER], END_OLD, END_NEW)
    once(paths[MANAGER], WORKERS_OLD, WORKERS_NEW)
    once(paths[MANAGER], CONTENT_OLD, CONTENT_NEW)
    once(paths[STATE], GRAPHICS_OLD, GRAPHICS_NEW)
    once(paths[STATE], COMPUTE_OLD, COMPUTE_NEW)
    once(paths[RENDERER], RELEASE_OLD, RELEASE_NEW)
    return list(paths.values())
