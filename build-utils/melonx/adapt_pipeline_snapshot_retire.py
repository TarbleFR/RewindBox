"""A worker pipeline cache snapshot main's file already holds is removed at the close instead of written again; a main
snapshot the driver ignores (another driver identity) is written again from the session instead of blocking every write.

Lot 6 (cache durability and loading; no IPA). Inputs, private journals not in the repository (Hogwarts Legacy):
- IPA 694, the maintainer's measures of one session: 2048 shaders in 2.155 s; main cache 780.86 MiB; worker snapshots
  167.09 MiB; background load and integration 7.188 s; 1984 lookup hits for 1 miss;
- IPA 684 (pid 26658): 2 worker snapshots (155.37 MiB) merged into a 605.06 MiB main at startup; the first checkpoint
  after it measured main at 624.69 MiB, with 501 new main pipelines since: those snapshots added at most 19.6 MiB, so at
  least 87 % of them was main's content already.

Mechanism (Core 711 preparation; MoltenVK v1.4.2): the close (MergeAndSave) merges every worker cache into main, writes
main, then writes each worker cache that changed to its own file, unchanged otherwise. Since Core 697 a worker starts
empty beside the main snapshot loading in the background, so its file is either this session's worker content (also in
main's file now) or an older snapshot left in place. At the next launch every worker file is mapped, handed to
vkCreatePipelineCache (MVKPipelineCache::readData decompresses and compiles the MSL of each entry, MVKShaderModule.mm),
then merged into main, where MoltenVK drops each entry main holds. A worker snapshot rejected by the driver, or too
large for main's room, also keeps the workers' hold for the whole session (no worker file written again), launch after
launch.
- MoltenVK v1.4.2 (MVKPipelineCache::readData, MVKDevice.mm initPipelineCacheUUID): a snapshot whose header (size, version,
  vendor, device, pipelineCacheUUID = MoltenVK revision, OS major and minor version, GPU family, argument buffers) is not
  this device's is ignored and the cache created empty with success. The file name holds vendor, device and MVK_VERSION
  only, so after an iOS update the 780 MiB file loads as nothing; the manager counts it as loaded, the growth rule then
  compares the session's cache with the old file's length, and no play or pause checkpoint writes main (nor the workers,
  held until main is written) until a clean close, launch after launch while sessions end by a kill.

Change (PipelineCacheManager.cs only, every title):
- each worker records whether its file may hold content main's cache does not (FileOutsideMain), from what is known:
  a snapshot loaded into the worker, a snapshot pending beside main, a write of the worker's cache, a merge into main
  (background load, recycle, close), a recycle, a snapshot the driver refused (nothing in it to keep);
- at the close, once main's file is written with every worker's content (merge succeeded, main not Frozen, main's
  generation saved), a worker with no content since that merge has its file removed when nothing in it is outside main,
  and left untouched otherwise (it is not overwritten with content main's file holds); in every other case (main not
  written: over budget, write failure, load still running or failed) the workers are written as before;
- each removal and each kept file is recorded in the engine journal ("pipelineCache workerRetired/workerKept");
- a snapshot of this device's header the driver refuses is kept at its first refusal (MoltenVK refuses the whole data
  when one Metal library fails to compile, MVKShaderModule.mm, so a refusal may be transient): main stays Frozen for that
  session (nothing written over its file), a worker file is kept; only a second refusal of the same file (length and
  write time, recorded in <file>.refused) at the next launch handles it as before (main replaced by the next checkpoint,
  the worker file removable at the close); "pipelineCache mainRefusedKept";
- the background load compares the main snapshot's first 32 bytes with this device's header (VkPipelineCacheHeaderVersionOne
  as vkGetPipelineCacheData writes it); only when they differ, it asks the driver the size of the cache it created, and
  only when the driver kept nothing (64 bytes or less) the snapshot is handled as a rejected one: main's file counts as
  holding nothing, so the next pause or play checkpoint writes the session's content ("pipelineCache mainIgnored"). A
  matching header costs no size query; a header the driver loaded anyway keeps the current behaviour.
Unchanged: the background load, the protection against replacing a file with less than it holds (the workers' hold,
Frozen main), the play, pause and recycle checkpoints, the worker lookup in main, the budgets, every pipeline and draw.
Not done: no repair of an opaque driver blob; no partial reading of a snapshot (MoltenVK reads it whole).
Fail closed on drift: PipelineCacheManager.cs must be the Core 711 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'

BASELINE = {
    MANAGER: 'c283f61ab7d22079b6dad45c3bf69cf70278dd35c91aacabd87f5018562c2eb4',
}

FIELDS_OLD = '''            public bool Frozen;
'''
FIELDS_NEW = '''            public bool Frozen;
            // RewindBox (adapt_pipeline_snapshot_retire): what a worker's file holds, as far as it is known. FileInCache: all
            // of it is in this cache (also when there is no file). FileOutsideMain: it may hold content main's cache does
            // not. A file nothing outside main is in is removed at the close once main's file holds main's content.
            public bool FileInCache = true;
            public bool FileOutsideMain;
'''

CTOR_OLD = '''                HasUsableSnapshot = loadedBytes > 0 && !snapshotRejected;
'''
CTOR_NEW = '''                HasUsableSnapshot = loadedBytes > 0 && !snapshotRejected;
                FileOutsideMain = HasUsableSnapshot; // RewindBox (adapt_pipeline_snapshot_retire): loaded here, not in main
'''

RECREATED_OLD = '''                Recycled = true;
'''
RECREATED_NEW = '''                Recycled = true;
                FileInCache = false; // RewindBox (adapt_pipeline_snapshot_retire): the file holds the outgrown cache's content
'''

PENDING_OLD = '''                    _workerStates[index] = new(CreateCache(null, description), workerCachePaths[index], description, workerBudget, 0);
                    continue;
'''
PENDING_NEW = '''                    _workerStates[index] = new(CreateCache(null, description), workerCachePaths[index], description, workerBudget, 0);
                    // RewindBox (adapt_pipeline_snapshot_retire): the snapshot joins main in the background, not this cache.
                    _workerStates[index].FileInCache = false;
                    _workerStates[index].FileOutsideMain = true;
                    continue;
'''

ARRAYS_OLD = '''            long[] workerLengths = new long[workerSnapshots.Length];
'''
ARRAYS_NEW = '''            long[] workerLengths = new long[workerSnapshots.Length];
            bool[] workerRefused = new bool[workerSnapshots.Length]; // RewindBox (adapt_pipeline_snapshot_retire)
'''

REFUSED_OLD = '''                        workerStaging[index] = CreateCache(workerSnapshot, $"worker {index}", out bool workerAccepted);

                        if (!workerAccepted)
                        {
                            _api.DestroyPipelineCache(_device, workerStaging[index], null);
                            workerStaging[index] = default;
'''
REFUSED_NEW = '''                        bool workerForeign = !IsDeviceCacheHeader(workerSnapshot); // RewindBox (adapt_pipeline_snapshot_retire)
                        workerStaging[index] = CreateCache(workerSnapshot, $"worker {index}", out bool workerAccepted);

                        if (workerAccepted)
                        {
                            ClearRefusal(_workerStates[index].Path); // RewindBox (adapt_pipeline_snapshot_retire)
                        }

                        if (!workerAccepted)
                        {
                            _api.DestroyPipelineCache(_device, workerStaging[index], null);
                            workerStaging[index] = default;
                            // RewindBox (adapt_pipeline_snapshot_retire): a refusal may be transient (MoltenVK refuses the whole
                            // data when one Metal library fails to compile): the file is kept at its first refusal, and only a
                            // second refusal of that same file in a row lets the close remove it.
                            workerRefused[index] = workerForeign || !FirstRefusal(_workerStates[index].Path, workerLengths[index]);
'''

JOINED_OLD = '''                                mergedWorkers++;
                                mergedBytes += workerLengths[index];
                                room -= workerLengths[index];
                            }
'''
JOINED_NEW = '''                                mergedWorkers++;
                                mergedBytes += workerLengths[index];
                                room -= workerLengths[index];
                                _workerStates[index].FileOutsideMain = false; // RewindBox (adapt_pipeline_snapshot_retire)
                            }
                            else if (workerRefused[index])
                            {
                                // RewindBox (adapt_pipeline_snapshot_retire): refused at two launches in a row; nothing in it to keep.
                                _workerStates[index].FileOutsideMain = false;
                            }
'''

PRESERVE_OLD = '''                    long mergedSize = GetCacheDataSize(_mainState);
'''
PRESERVE_NEW = '''                    // RewindBox (adapt_pipeline_snapshot_retire): main holds this cache, so its file's content if the file is of it.
                    if (worker.FileInCache)
                    {
                        worker.FileOutsideMain = false;
                    }

                    long mergedSize = GetCacheDataSize(_mainState);
'''

SAVED_OLD = '''                state.HasUsableSnapshot = true;

                // RewindBox (adapt_pipeline_cache_growth): what the main file holds now; each write in the engine journal.
'''
SAVED_NEW = '''                state.HasUsableSnapshot = true;
                // RewindBox (adapt_pipeline_snapshot_retire): the file is this cache now, which main may not hold yet.
                state.FileInCache = true;
                state.FileOutsideMain = true;

                // RewindBox (adapt_pipeline_cache_growth): what the main file holds now; each write in the engine journal.
'''

CLOSE_OLD = '''            lock (_mainCacheLock)
            {
                PipelineCache[] workerCaches = new PipelineCache[_workerStates.Length];
                int count = 0;

                for (int index = 0; index < _workerStates.Length; index++)
                {
                    CacheState state = _workerStates[index];

                    if (state.Generation != state.MergedGeneration)
                    {
                        workerCaches[count++] = state.Cache;
                    }
                }

                if (MergeInto(_mainState.Cache, workerCaches.AsSpan(0, count)))
                {
                    if (count != 0)
                    {
                        Interlocked.Increment(ref _mainState.Generation);

                        foreach (CacheState state in _workerStates)
                        {
                            state.MergedGeneration = state.Generation;
                        }
                    }

                    Maintain(_mainState, force: true, allowRecycle: false);
                }
            }

            foreach (CacheState state in _workerStates)
            {
                Maintain(state, force: true, allowRecycle: false);
            }
'''
CLOSE_NEW = '''            bool mainFileHoldsWorkers = false; // RewindBox (adapt_pipeline_snapshot_retire)

            lock (_mainCacheLock)
            {
                PipelineCache[] workerCaches = new PipelineCache[_workerStates.Length];
                int count = 0;

                for (int index = 0; index < _workerStates.Length; index++)
                {
                    CacheState state = _workerStates[index];

                    if (state.Generation != state.MergedGeneration)
                    {
                        workerCaches[count++] = state.Cache;
                    }
                }

                if (MergeInto(_mainState.Cache, workerCaches.AsSpan(0, count)))
                {
                    if (count != 0)
                    {
                        Interlocked.Increment(ref _mainState.Generation);

                        foreach (CacheState state in _workerStates)
                        {
                            state.MergedGeneration = state.Generation;
                        }
                    }

                    // RewindBox (adapt_pipeline_snapshot_retire): main holds every worker cache now, so each file of one.
                    foreach (CacheState state in _workerStates)
                    {
                        if (state.FileInCache)
                        {
                            state.FileOutsideMain = false;
                        }
                    }

                    Maintain(_mainState, force: true, allowRecycle: false);

                    // Main's file holds main's content (written now or before), so every worker's and their merged files'.
                    mainFileHoldsWorkers = !_mainState.Frozen && !string.IsNullOrEmpty(_mainState.Path) &&
                        Interlocked.Read(ref _mainState.Generation) == Interlocked.Read(ref _mainState.SavedGeneration);
                }
            }

            foreach (CacheState state in _workerStates)
            {
                // RewindBox (adapt_pipeline_snapshot_retire): a worker with nothing new since that merge is not written again:
                // its file goes if nothing in it is outside main, and stays as it is otherwise. Else, as before.
                if (mainFileHoldsWorkers && Interlocked.Read(ref state.Generation) == state.MergedGeneration)
                {
                    if (state.FileOutsideMain)
                    {
                        NoteWorkerFileKept(state);
                    }
                    else
                    {
                        RetireWorkerFile(state);
                    }

                    continue;
                }

                Maintain(state, force: true, allowRecycle: false);
            }
'''

HEADER_FIELD_OLD = '''        private readonly PipelineCacheCreateFlags _createFlags;
'''
HEADER_FIELD_NEW = '''        private readonly PipelineCacheCreateFlags _createFlags;

        // RewindBox (adapt_pipeline_snapshot_retire): this device's pipeline cache header (VkPipelineCacheHeaderVersionOne, as
        // vkGetPipelineCacheData writes it: size 32, version 1, vendor, device, pipelineCacheUUID; little endian), and the
        // largest size of a cache the driver created empty (MoltenVK: that header and an end marker).
        private readonly byte[] _deviceCacheHeader = new byte[32];
        private const long EmptyCacheBytes = 64;
'''

HEADER_SET_OLD = '''            PhysicalDeviceProperties properties = physicalDevice.PhysicalDeviceProperties;
'''
HEADER_SET_NEW = '''            PhysicalDeviceProperties properties = physicalDevice.PhysicalDeviceProperties;
            SetDeviceCacheHeader(properties); // RewindBox (adapt_pipeline_snapshot_retire)
'''

IGNORED_OLD = '''                bool failed = false;

                try
                {
                    staging = CreateCache(snapshot, "main", out accepted);
                }
'''
IGNORED_NEW = '''                bool failed = false;
                bool ignored = false; // RewindBox (adapt_pipeline_snapshot_retire)

                try
                {
                    // RewindBox (adapt_pipeline_snapshot_retire): with another device's header the driver may have kept
                    // nothing (MoltenVK ignores such data and succeeds); only then is the snapshot handled as rejected.
                    bool foreign = !IsDeviceCacheHeader(snapshot);
                    staging = CreateCache(snapshot, "main", out accepted);

                    if (accepted && foreign && staging.Handle != 0 && IsEmptyCache(staging))
                    {
                        accepted = false;
                        ignored = true;
                        Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                            "pipelineCache", "mainIgnored", detail: $"{FormatSize(length)} file of another driver identity (MoltenVK " +
                            "revision, OS version or GPU family): the driver kept nothing; written again from this session " +
                            "(adapt_pipeline_snapshot_retire)");
                    }
                    else if (accepted)
                    {
                        ClearRefusal(_mainState.Path);
                    }
                    else if (!foreign && FirstRefusal(_mainState.Path, length))
                    {
                        // MoltenVK refuses the whole data when one Metal library fails to compile, so a refusal may be
                        // transient: the first one keeps the file and leaves main Frozen this session (nothing written over
                        // it); a second refusal of that same file in a row replaces it, as before.
                        failed = true;
                        Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                            "pipelineCache", "mainRefusedKept", detail: $"{FormatSize(length)} file refused by the driver for the first " +
                            "time: kept, not written over this session (adapt_pipeline_snapshot_retire)");
                    }
                }
'''

LOADED_LINE_OLD = '''failed ? "not loaded (its file is kept)" : "rejected")} in the background: " +'''
LOADED_LINE_NEW = '''failed ? "not loaded (its file is kept)" : ignored ? "ignored by the driver (another driver identity)" : "rejected")} in the background: " +'''

RETIRE_ANCHOR = '''        private void Maintain(CacheState state, bool force, bool allowRecycle = true)
'''
RETIRE_NEW = '''        // RewindBox (adapt_pipeline_snapshot_retire): at the close, main's file holds this worker's content and its file's: the
        // file is removed instead of being written again, so the next launch neither maps, hydrates nor merges that copy.
        private void RetireWorkerFile(CacheState state)
        {
            if (string.IsNullOrEmpty(state.Path) || !File.Exists(state.Path))
            {
                return;
            }

            long bytes;

            try
            {
                bytes = new FileInfo(state.Path).Length;
                File.Delete(state.Path);
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                // Left as it is: the next launch merges it into main again, as before.
                Logger.Warning?.PrintMsg(
                    LogClass.Gpu,
                    $"Could not remove the Vulkan {state.Description} pipeline cache snapshot main's file holds: {exception.Message}");

                return;
            }

            state.HasUsableSnapshot = false;
            state.FileInCache = true;
            state.SavedGeneration = Interlocked.Read(ref state.Generation);

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                "pipelineCache", "workerRetired", detail: $"{state.Description} {FormatSize(bytes)}: main's file holds it (adapt_pipeline_snapshot_retire)");
            Logger.Info?.PrintMsg(
                LogClass.Gpu,
                $"Removed the Vulkan {state.Description} pipeline cache snapshot ({FormatSize(bytes)}): main's file holds its content " +
                "(adapt_pipeline_snapshot_retire).");
        }

        // RewindBox (adapt_pipeline_snapshot_retire): its file may hold content main's file does not; nothing new to add to it.
        private static void NoteWorkerFileKept(CacheState state)
        {
            long bytes = 0;

            try
            {
                bytes = File.Exists(state.Path) ? new FileInfo(state.Path).Length : 0;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                "pipelineCache", "workerKept", detail: $"{state.Description} {FormatSize(bytes)}: may hold content main does not (adapt_pipeline_snapshot_retire)");
        }

        private unsafe void SetDeviceCacheHeader(PhysicalDeviceProperties properties)
        {
            System.Buffers.Binary.BinaryPrimitives.WriteUInt32LittleEndian(_deviceCacheHeader.AsSpan(0), 32);
            System.Buffers.Binary.BinaryPrimitives.WriteUInt32LittleEndian(_deviceCacheHeader.AsSpan(4), 1);
            System.Buffers.Binary.BinaryPrimitives.WriteUInt32LittleEndian(_deviceCacheHeader.AsSpan(8), properties.VendorID);
            System.Buffers.Binary.BinaryPrimitives.WriteUInt32LittleEndian(_deviceCacheHeader.AsSpan(12), properties.DeviceID);

            for (int index = 0; index < 16; index++)
            {
                _deviceCacheHeader[16 + index] = properties.PipelineCacheUuid[index];
            }
        }

        private unsafe bool IsDeviceCacheHeader(MappedSnapshot snapshot)
        {
            return snapshot.Length >= _deviceCacheHeader.Length &&
                new ReadOnlySpan<byte>(snapshot.Pointer, _deviceCacheHeader.Length).SequenceEqual(_deviceCacheHeader);
        }

        // RewindBox (adapt_pipeline_snapshot_retire): true at the first refusal of this file (path, length, write time),
        // recorded in <file>.refused; false when the previous launch refused the same file, or when the record cannot be
        // written (then the refusal is handled as before).
        private static bool FirstRefusal(string path, long length)
        {
            if (string.IsNullOrEmpty(path))
            {
                return false;
            }

            try
            {
                string marker = path + ".refused";
                string identity = $"{length}:{File.GetLastWriteTimeUtc(path).Ticks}";

                if (File.Exists(marker) && File.ReadAllText(marker) == identity)
                {
                    return false;
                }

                File.WriteAllText(marker, identity);

                return true;
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
                return false;
            }
        }

        private static void ClearRefusal(string path)
        {
            if (string.IsNullOrEmpty(path))
            {
                return;
            }

            try
            {
                File.Delete(path + ".refused");
            }
            catch (Exception exception) when (exception is IOException or UnauthorizedAccessException)
            {
            }
        }

        private unsafe bool IsEmptyCache(PipelineCache cache)
        {
            nuint dataSize = 0;
            Result result = _api.GetPipelineCacheData(_device, cache, &dataSize, null);

            return !result.IsError && dataSize <= EmptyCacheBytes;
        }

        private void Maintain(CacheState state, bool force, bool allowRecycle = true)
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    manager = paths[MANAGER]
    once(manager, FIELDS_OLD, FIELDS_NEW)
    once(manager, CTOR_OLD, CTOR_NEW)
    once(manager, RECREATED_OLD, RECREATED_NEW)
    once(manager, PENDING_OLD, PENDING_NEW)
    once(manager, ARRAYS_OLD, ARRAYS_NEW)
    once(manager, REFUSED_OLD, REFUSED_NEW)
    once(manager, JOINED_OLD, JOINED_NEW)
    once(manager, PRESERVE_OLD, PRESERVE_NEW)
    once(manager, SAVED_OLD, SAVED_NEW)
    once(manager, CLOSE_OLD, CLOSE_NEW)
    once(manager, RETIRE_ANCHOR, RETIRE_NEW)
    once(manager, HEADER_FIELD_OLD, HEADER_FIELD_NEW)
    once(manager, HEADER_SET_OLD, HEADER_SET_NEW)
    once(manager, IGNORED_OLD, IGNORED_NEW)
    once(manager, LOADED_LINE_OLD, LOADED_LINE_NEW)
    return list(paths.values())
