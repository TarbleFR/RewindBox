"""The main pipeline cache references its mapped file instead of copying it into memory (Core 721, RAM).

IPA 718, Hogwarts Legacy (pid 44597): the footprint reaches 5.4-5.5 GiB with 4 % of the device's memory available; the
790 MiB main pipeline cache is part of it for the whole session. RewindBox maps the cache file read-only
(MappedSnapshot) and creates a staging cache from it, but MoltenVK v1.4.2 copies every library's compressed MSL out of the
data into anonymous memory, the merge into main copies it again (most of the +650 MiB transient 5 s after launch:
2 090 -> 4 256 -> 3 600 MiB), and the mapping is closed right after. With the RewindBox MoltenVK patch
(build-utils/melonx/moltenvk/rewindbox-moltenvk.patch, third part) a private pNext structure of
VkPipelineCacheCreateInfo (sType 0x52425831, 'RBX1') makes MoltenVK reference each compressed MSL in the caller's data
instead: pages of a mapped file that are never written are not part of the footprint iOS limits, and the system can drop
and read them back.

Change (PipelineCacheManager.cs, every title):
- the main snapshot's staging cache is created with that structure (worker snapshots are copied as before);
- once the driver accepted it (and kept something: a header of another driver identity keeps nothing), the snapshot stays
  mapped while main can reference it: at the end of the load, whatever path it took, it is kept with the manager under
  the main lock and disposed after main is destroyed at the close, or disposed then if the close already destroyed main;
  a snapshot the driver did not accept is disposed as before;
- main is never a merge source, never recycled, and its file is replaced by a new file (written beside it, then moved)
  or deleted, never rewritten in place, so the mapped bytes stay what MoltenVK read;
- one journal line, pipelineCache mainDataMapped, with the size referenced.
A MoltenVK without the patch ignores the structure (it walks only the pNext types it knows) and copies as before.
Not measured on an iPhone. Fail closed on drift: the file must be the Core 719 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
BASELINE = {
    MANAGER: 'a59d72ae5da387f9405b5945a8e3afbeef00a2e25e1b12b4dbb26a425a6a29f8',
}
STYPE = 0x52425831

FIELD_OLD = '''        private readonly Lock _mainCacheLock;
'''
FIELD_NEW = '''        private readonly Lock _mainCacheLock;

        // RewindBox (adapt_pipeline_cache_mapped_data): the main snapshot's read-only mapping, kept while main references its
        // data (MoltenVK with the RewindBox patch keeps each library's compressed MSL in it instead of a copy); disposed after
        // main is destroyed. Written and read under _mainCacheLock.
        private MappedSnapshot _mainDataSnapshot;
        internal const uint MappedCacheDataSType = 0x52425831;

        private unsafe struct MappedCacheDataInfo
        {
            public StructureType SType;
            public void* PNext;
        }
'''

CREATE_OLD = '''        private unsafe PipelineCache CreateCache(MappedSnapshot snapshot, string description, out bool snapshotAccepted)
        {
            snapshotAccepted = false;
            PipelineCache pipelineCache;
            PipelineCacheCreateInfo createInfo = new()
            {
                SType = StructureType.PipelineCacheCreateInfo,
                Flags = _createFlags,
                InitialDataSize = (nuint)(snapshot?.Length ?? 0),
                PInitialData = snapshot != null ? snapshot.Pointer : null,
            };
'''
CREATE_NEW = '''        private unsafe PipelineCache CreateCache(MappedSnapshot snapshot, string description, out bool snapshotAccepted,
            bool referenceData = false)
        {
            snapshotAccepted = false;
            PipelineCache pipelineCache;
            // RewindBox (adapt_pipeline_cache_mapped_data): asks the driver to reference the snapshot's data, not copy it.
            MappedCacheDataInfo referenceInfo = new() { SType = (StructureType)MappedCacheDataSType };
            PipelineCacheCreateInfo createInfo = new()
            {
                SType = StructureType.PipelineCacheCreateInfo,
                PNext = referenceData && snapshot != null ? &referenceInfo : null,
                Flags = _createFlags,
                InitialDataSize = (nuint)(snapshot?.Length ?? 0),
                PInitialData = snapshot != null ? snapshot.Pointer : null,
            };
'''

RETRY_OLD = '''                createInfo.InitialDataSize = 0;
                createInfo.PInitialData = null;

                _api.CreatePipelineCache(_device, in createInfo, null, out pipelineCache).ThrowOnError();
'''
RETRY_NEW = '''                createInfo.InitialDataSize = 0;
                createInfo.PInitialData = null;
                createInfo.PNext = null;

                _api.CreatePipelineCache(_device, in createInfo, null, out pipelineCache).ThrowOnError();
'''

STAGING_OLD = '''                    staging = CreateCache(snapshot, "main", out accepted);
'''
STAGING_NEW = '''                    staging = CreateCache(snapshot, "main", out accepted, referenceData: true);
                    referenced = accepted; // RewindBox (adapt_pipeline_cache_mapped_data)
'''

DECLARE_OLD = '''            bool[] workerRefused = new bool[workerSnapshots.Length]; // RewindBox (adapt_pipeline_snapshot_retire)

            try
            {
'''
DECLARE_NEW = '''            bool[] workerRefused = new bool[workerSnapshots.Length]; // RewindBox (adapt_pipeline_snapshot_retire)
            // RewindBox (adapt_pipeline_cache_mapped_data): the driver accepted the snapshot and may reference its data; the
            // snapshot is then kept for main (or released after the close) at the end of the load.
            bool referenced = false;

            try
            {
'''

INNER_DISPOSE_OLD = '''                finally
                {
                    snapshot.Dispose();
                }

                // The worker snapshots load here too, outside the main lock.'''
INNER_DISPOSE_NEW = '''                finally
                {
                    // RewindBox (adapt_pipeline_cache_mapped_data): a snapshot the driver accepted stays mapped (below).
                    if (!referenced)
                    {
                        snapshot.Dispose();
                    }
                }

                // The worker snapshots load here too, outside the main lock.'''

IGNORED_OLD = '''                        accepted = false;
                        ignored = true;
'''
IGNORED_NEW = '''                        accepted = false;
                        ignored = true;
                        referenced = false; // RewindBox (adapt_pipeline_cache_mapped_data): the driver kept nothing of it
'''

OUTER_OLD = '''            catch (Exception exception)
            {
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Vulkan main pipeline cache background load failed: {exception.Message}");
            }
            finally
            {
                Action release;
'''
OUTER_NEW = '''            catch (Exception exception)
            {
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Vulkan main pipeline cache background load failed: {exception.Message}");
            }
            finally
            {
                // RewindBox (adapt_pipeline_cache_mapped_data): the driver accepted the snapshot, so main may reference its
                // data from here on: it stays mapped until main is destroyed (DisposeLocked), or is released now if the close
                // already destroyed main. Whatever path the load took (merged, merge failed, exception), never earlier.
                if (referenced)
                {
                    lock (_mainCacheLock)
                    {
                        if (_disposed)
                        {
                            snapshot.Dispose();
                        }
                        else
                        {
                            _mainDataSnapshot = snapshot;
                            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                                "pipelineCache", "mainDataMapped", detail: $"main {FormatSize(length)} referenced in its mapped file, " +
                                "not copied into memory (adapt_pipeline_cache_mapped_data)");
                        }
                    }

                    referenced = false;
                }

                Action release;
'''

DESTROY_OLD = '''            _api.DestroyPipelineCache(_device, _mainState.Cache, null);
'''
DESTROY_NEW = '''            _api.DestroyPipelineCache(_device, _mainState.Cache, null);

            // RewindBox (adapt_pipeline_cache_mapped_data): main no longer references the snapshot's data.
            _mainDataSnapshot?.Dispose();
            _mainDataSnapshot = null;
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    manager = paths[MANAGER]
    for old, new in ((FIELD_OLD, FIELD_NEW), (CREATE_OLD, CREATE_NEW), (RETRY_OLD, RETRY_NEW), (DECLARE_OLD, DECLARE_NEW),
                     (STAGING_OLD, STAGING_NEW), (IGNORED_OLD, IGNORED_NEW), (INNER_DISPOSE_OLD, INNER_DISPOSE_NEW),
                     (OUTER_OLD, OUTER_NEW), (DESTROY_OLD, DESTROY_NEW)):
        once(manager, old, new)
    return list(paths.values())
