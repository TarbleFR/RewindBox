"""The main pipeline cache file is written again once when it holds far more than the driver keeps (Core 729 candidate).

IPA 724, Hogwarts Legacy (pid 49375): the main file is 792.03 MiB for 4 669 libraries, 177 876 bytes each, of which about
nine tenths are the pipeline layout's binding table MoltenVK serialized with every library (MeloNX declares 261 bindings
for a vertex + fragment program, MoltenVK lists each once per Metal stage: 1 305 entries of 134 bytes). With the fifth
part of build-utils/melonx/moltenvk/rewindbox-moltenvk.patch the driver keeps and writes a library under the bindings a
lookup reads, so main's data after loading that file is a small fraction of it. Nothing in the manager expects that:
- the file is rewritten only for growth over what it held (MainGrowthWorthWriting, adapt_pipeline_cache_growth), so a
  shrunk main is not written until the close of a session that compiled something, and never if the session is killed:
  every launch would read and parse the 792 MiB again (4.4 s in IPA 724);
- the budget estimate starts from the file's size (CacheState._measuredBytes), so main looks 792 MiB of its 1 024 MiB
  budget when it holds a tenth of it (worker shares are refused for budget on that estimate).

Change (PipelineCacheManager.cs, every title), at the end of the background load, on the load thread, under the main
lock, after the staging caches are destroyed and only when the snapshot was accepted and merged:
- main's data size is asked once (the driver counts each entry once and keeps it: recipe patch, second part);
- the budget estimate becomes that size, and what "the file holds" for the growth rule becomes that size when it is
  smaller than the file;
- a file at least twice main's data, by 8 MiB or more (MainCheckpointMinimumGrowthBytes), is written again now by the
  existing SaveCache (beside the file, then moved over it: the mapped snapshot main references stays valid), before
  play, so the next launch reads the small file whatever happens to this session; a failure leaves the file as it is.
- one engine journal record: "pipelineCache compact" or "pipelineCache loadedSize", with both sizes.
Nothing is deleted: the file is replaced by main's data, which holds every library the file held.
Not measured on an iPhone. Fail closed on drift: the file must be the Core 727 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
BASELINE = {
    MANAGER: '9a74ebe45dcbbbbb73fcc61a22dcba0eacad4249058434a4c50636df6130cd7d',
}

CALL_OLD = '''                    foreach (PipelineCache workerCache in workerStaging)
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
                    Interlocked.Decrement(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)
                }
'''
CALL_NEW = '''                    foreach (PipelineCache workerCache in workerStaging)
                    {
                        if (workerCache.Handle != 0)
                        {
                            _api.DestroyPipelineCache(_device, workerCache, null);
                        }
                    }

                    // RewindBox (adapt_pipeline_cache_compact): main holds the file's libraries; what it would write may be
                    // far less than the file.
                    if (accepted && !failed && !_disposed)
                    {
                        CompactMainAfterLoad(length);
                    }
                }
                finally
                {
                    _mainCacheLock.Exit();
                    Interlocked.Decrement(ref _mainCheckpointHolders); // RewindBox (adapt_worker_library_share)
                }
'''

METHOD_OLD = '''        // RewindBox (adapt_pipeline_cache_growth): whether a checkpoint rewrites the main file, recorded in the engine journal.
        private bool MainGrowthWorthWriting(long size, long now, bool pause)
'''
METHOD_NEW = '''        // RewindBox (adapt_pipeline_cache_compact): a file at least this many times main's data is written again at the load.
        internal const int MainCompactFileShare = 2;

        internal static bool MainFileWorthCompacting(long fileBytes, long dataBytes)
        {
            return dataBytes > 0 && dataBytes <= fileBytes / MainCompactFileShare &&
                fileBytes - dataBytes >= MainCheckpointMinimumGrowthBytes;
        }

        // RewindBox (adapt_pipeline_cache_compact): at the end of the background load, under the main lock. The driver keeps
        // a library without the binding tables a file written before carries with each (IPA 724: 792 MiB for 4 669
        // libraries, about nine tenths tables), so main's data may be a fraction of the file it was loaded from. The budget
        // estimate and the growth rule, which started from the file's size, take main's data; and a file at least twice
        // main's data, by 8 MiB or more, is written again now (beside it, then moved over it: the mapped snapshot main
        // references stays valid), before play: the next launch reads the small file whatever happens to this session.
        private void CompactMainAfterLoad(long fileBytes)
        {
            CacheState main = _mainState;

            if (main.Frozen || string.IsNullOrEmpty(main.Path))
            {
                return;
            }

            try
            {
                long data = GetCacheDataSize(main);

                if (data < 0)
                {
                    return;
                }

                main.OnMeasured(data);

                if (data < Interlocked.Read(ref _mainWrittenBytes))
                {
                    Interlocked.Exchange(ref _mainWrittenBytes, data);
                }

                bool compact = data <= main.Budget && MainFileWorthCompacting(fileBytes, data);

                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                    "pipelineCache",
                    compact ? "compact" : "loadedSize",
                    detail: $"main's data {FormatSize(data)} of a {FormatSize(fileBytes)} file{(compact ? ": written again now" : "")} " +
                            "(adapt_pipeline_cache_compact)");

                if (compact)
                {
                    SaveCache(main, data, final: false);
                }
            }
            catch (Exception exception)
            {
                // The load is complete either way; the file stays as it is and the next launch tries again.
                Logger.Warning?.PrintMsg(LogClass.Gpu, $"Vulkan main pipeline cache not written again after its load: {exception.Message}");
            }
        }

        // RewindBox (adapt_pipeline_cache_growth): whether a checkpoint rewrites the main file, recorded in the engine journal.
        private bool MainGrowthWorthWriting(long size, long now, bool pause)
'''

PAIRS = ((CALL_OLD, CALL_NEW), (METHOD_OLD, METHOD_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[MANAGER], old, new)
    return list(paths.values())
