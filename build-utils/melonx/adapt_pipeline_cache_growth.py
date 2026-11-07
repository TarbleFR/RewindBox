"""The main pipeline cache file is rewritten only when it gained real content; compute pipelines join the build journal;
the cache and journal lines reach the durable engine journal.

IPA 684, private journals, not in the repository (Hogwarts Legacy, pid 26658, one session 13:38:47-13:51:36 UTC):
- the main cache loaded 605.06 MiB (budget 1024 MiB: it is not full) and was checkpointed during play six times, 4.2-5.2 s
  of writing each plus a 1.0-1.5 s size probe, every one rewriting the whole file (vkGetPipelineCacheData into a mapped
  file) for little: 624.69 MiB at 1:36, 626.25 MiB at 4:01 (+1.56), 626.80 MiB at 6:13 (+0.55). About 3.7 GB written in
  13 min to keep a few MiB. iOS sent nine memory warnings from 13:50:18 (footprint 5334 MiB, 1321 MiB headroom, device
  6 %), starting in the 5 s window of the sixth checkpoint (cacheSave 4253 ms);
- the 15 s freeze at 13:49:09-13:49:30 is render-thread pipeline time, mostly compute ("compute prepare ... pipelines
  921 calls 3530.2 ms", then 634 calls 3720.9 ms) while MoltenVK converted 42 new shaders (13.5 s of MSL compilation):
  the build journal of Core 685 times graphics pipelines only, so it could not attribute it;
- the stderr capture copies 500 engine lines per session: the five-second Gpu warnings spent it by 6:23, so the journal
  summaries and the checkpoint lines after that were lost (the engine journal keeps the warnings, not these Info lines).

Change (PipelineCacheManager.cs, PipelineState.cs, every title):
- a play-time checkpoint (same cadence) writes the main file only when the measured cache is 8 MiB larger than what the
  file holds, or larger at all 10 min after the last write; a pause writes it when it is larger at all. The close, the
  worker caches, the side cache and the budgets are unchanged. Each decision and each write (with its time) is recorded
  in the engine journal ("pipelineCache checkpoint/checkpointSkipped/written/saved"), and each recycle ("recycled");
- compute pipeline compilations (50 ms or more) are noted in the build journal like graphics ones, with a key from the
  program's StableHash and the specialization data;
- the build journal's startup line and summaries are also recorded in the engine journal ("pipelineBuilds").
No pipeline, draw or cache content changes. Fail closed on drift: the files must be the Core 685 preparation's.
"""
import hashlib
from adapt_session import once

MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'

BASELINE = {
    MANAGER: '8fe5c91ca78f0ced2d453946439c5e580471d13290304026e73a734be2cf4d3a',
    STATE: 'd3a34a9886f1b9cba7764c88a8f634d6d46ada642d9ec36d3a4e599cb72d32a1',
}

FIELDS_OLD = '''        private int _mainCheckpointQueued;
'''
FIELDS_NEW = '''        private int _mainCheckpointQueued;

        // RewindBox (adapt_pipeline_cache_growth): the main file is rewritten whole (about 627 MiB for Hogwarts Legacy), so a
        // play-time checkpoint writes it only for 8 MiB of new content, or any 10 min after the last write; a pause, for any.
        internal const long MainCheckpointMinimumGrowthBytes = 8L * 1024 * 1024;
        internal const long MainCheckpointStaleMs = 600_000;
        private long _mainWrittenBytes;
        private long _mainWrittenTimestamp = Environment.TickCount64;
'''

STARTUP_OLD = '''                snapshotRejected: mainSnapshotRejected);
'''
STARTUP_NEW = '''                snapshotRejected: mainSnapshotRejected);

            // RewindBox (adapt_pipeline_cache_growth): what the main file on disk holds.
            _mainWrittenBytes = mainSnapshotRejected ? 0 : mainSnapshotBytes;
'''

PLAY_OLD = '''                SaveCache(main, size, final: false);
                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Vulkan main pipeline cache checkpointed during play in'''
PLAY_NEW = '''                // RewindBox (adapt_pipeline_cache_growth): the whole file is rewritten only for real new content.
                if (!MainGrowthWorthWriting(size, now, pause: false))
                {
                    return;
                }

                SaveCache(main, size, final: false);
                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Vulkan main pipeline cache checkpointed during play in'''

PAUSE_OLD = '''                SaveCache(main, size, final: false);
                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Vulkan main pipeline cache checkpointed on pause in'''
PAUSE_NEW = '''                // RewindBox (adapt_pipeline_cache_growth): written on pause when the cache holds more than the file.
                if (!MainGrowthWorthWriting(size, now, pause: true))
                {
                    return;
                }

                SaveCache(main, size, final: false);
                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Vulkan main pipeline cache checkpointed on pause in'''

DECISION_ANCHOR = '''        // RewindBox (adapt_pipeline_build_journal): records of (key, session ordinal); a torn tail is ignored.
'''
DECISION_NEW = '''        // RewindBox (adapt_pipeline_cache_growth): whether a checkpoint rewrites the main file, recorded in the engine journal.
        private bool MainGrowthWorthWriting(long size, long now, bool pause)
        {
            long grown = size - Interlocked.Read(ref _mainWrittenBytes);
            long sinceMs = now - Interlocked.Read(ref _mainWrittenTimestamp);
            bool write = pause
                ? grown > 0
                : grown >= MainCheckpointMinimumGrowthBytes || (grown > 0 && sinceMs >= MainCheckpointStaleMs);

            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                "pipelineCache",
                write ? "checkpoint" : "checkpointSkipped",
                detail: $"{(pause ? "pause" : "play")}: main {FormatSize(size)}, {(grown < 0 ? "-" : "+")}{FormatSize(Math.Abs(grown))} " +
                        $"since the file was written {sinceMs / 1000} s ago (adapt_pipeline_cache_growth)");

            return write;
        }

        // RewindBox (adapt_pipeline_build_journal): records of (key, session ordinal); a torn tail is ignored.
'''

JOURNAL_LOAD_OLD = '''                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Pipeline build journal: {_earlierBuilds.Count} pipelines compiled in {lastSession} earlier sessions of this title " +
                    "(adapt_pipeline_build_journal).");
'''
JOURNAL_LOAD_NEW = '''                Logger.Info?.PrintMsg(
                    LogClass.Gpu,
                    $"Pipeline build journal: {_earlierBuilds.Count} pipelines compiled in {lastSession} earlier sessions of this title " +
                    "(adapt_pipeline_build_journal).");
                // RewindBox (adapt_pipeline_cache_growth): also in the engine journal (stderr copies a bounded number of lines).
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                    "pipelineBuilds", "journal", detail: $"{_earlierBuilds.Count} pipelines compiled in {lastSession} earlier sessions");
'''

SUMMARY_OLD = '''            if (summary != null)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, summary);
            }
'''
SUMMARY_NEW = '''            if (summary != null)
            {
                Logger.Info?.PrintMsg(LogClass.Gpu, summary);
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineBuilds", "summary", detail: summary); // adapt_pipeline_cache_growth
            }
'''

PAUSE_SUMMARY_OLD = '''                summary = BuildSummaryLocked("since the previous summary, at pause");
            }

            Logger.Info?.PrintMsg(LogClass.Gpu, summary);
'''
PAUSE_SUMMARY_NEW = '''                summary = BuildSummaryLocked("since the previous summary, at pause");
            }

            Logger.Info?.PrintMsg(LogClass.Gpu, summary);
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineBuilds", "summary", detail: summary); // adapt_pipeline_cache_growth
'''

SAVE_START_OLD = '''            using var saveMeasurement = PD.Measure(PD.Phase.CacheSave);
'''
SAVE_START_NEW = '''            using var saveMeasurement = PD.Measure(PD.Phase.CacheSave);
            long saveStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_pipeline_cache_growth)
'''

SAVE_DONE_OLD = '''                state.HasUsableSnapshot = true;
'''
SAVE_DONE_NEW = '''                state.HasUsableSnapshot = true;

                // RewindBox (adapt_pipeline_cache_growth): what the main file holds now; each write in the engine journal.
                if (ReferenceEquals(state, _mainState))
                {
                    Interlocked.Exchange(ref _mainWrittenBytes, written);
                    Interlocked.Exchange(ref _mainWrittenTimestamp, Environment.TickCount64);
                }

                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                    "pipelineCache",
                    final ? "saved" : "written",
                    detail: $"{state.Description} {FormatSize(written)} in " +
                            $"{System.Diagnostics.Stopwatch.GetElapsedTime(saveStart).TotalMilliseconds:F0} ms (adapt_pipeline_cache_growth)");
'''

RECYCLE_OLD = '''                $"Recycled the Vulkan {state.Description} pipeline cache at {FormatSize(size)}, " +
                $"over its {FormatSize(state.Budget)} budget.");
'''
RECYCLE_NEW = '''                $"Recycled the Vulkan {state.Description} pipeline cache at {FormatSize(size)}, " +
                $"over its {FormatSize(state.Budget)} budget.");
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(
                "pipelineCache", "recycled", detail: $"{state.Description} at {FormatSize(size)} (adapt_pipeline_cache_growth)");
'''

COMPUTE_START_OLD = '''            using var pipelineMeasurement = PD.Measure(PD.Phase.ComputePipelineBuild);
'''
COMPUTE_START_NEW = '''            using var pipelineMeasurement = PD.Measure(PD.Phase.ComputePipelineBuild);
            long buildStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_pipeline_cache_growth)
'''

COMPUTE_END_OLD = '''            pipeline = new Auto<DisposablePipeline>(new DisposablePipeline(gd.Api, device, pipelineHandle));

            return program.AddComputePipeline(ref SpecializationData, pipeline);
        }
'''
COMPUTE_END_NEW = '''            // RewindBox (adapt_pipeline_cache_growth): compute compilations (50 ms or more) join the build journal.
            double buildMs = System.Diagnostics.Stopwatch.GetElapsedTime(buildStart).TotalMilliseconds;

            if (buildMs >= PipelineCacheManager.CompiledBuildMs)
            {
                gd.PipelineCacheManager.NotePipelineBuild(ComputeBuildKey(program), buildMs, gd.PipelineCacheManager.IsMainCache(cache));
            }

            pipeline = new Auto<DisposablePipeline>(new DisposablePipeline(gd.Api, device, pipelineHandle));

            return program.AddComputePipeline(ref SpecializationData, pipeline);
        }

        // RewindBox (adapt_pipeline_cache_growth): the program's StableHash with its specialization data, kept apart from the
        // graphics keys, the same for the same compute pipeline in every session.
        private ulong ComputeBuildKey(ShaderCollection program)
        {
            Ryujinx.Common.Hash128 spec = Ryujinx.Common.Hash128.ComputeHash(SpecializationData.Span);

            return ((spec.Low ^ program.StableHash ^ 0xC0FFEE0DDBA11C0DUL) * 0x9E3779B97F4A7C15UL) ^ spec.High;
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    manager = paths[MANAGER]
    once(manager, FIELDS_OLD, FIELDS_NEW)
    once(manager, STARTUP_OLD, STARTUP_NEW)
    once(manager, PLAY_OLD, PLAY_NEW)
    once(manager, PAUSE_OLD, PAUSE_NEW)
    once(manager, DECISION_ANCHOR, DECISION_NEW)
    once(manager, JOURNAL_LOAD_OLD, JOURNAL_LOAD_NEW)
    once(manager, SUMMARY_OLD, SUMMARY_NEW)
    once(manager, PAUSE_SUMMARY_OLD, PAUSE_SUMMARY_NEW)
    once(manager, SAVE_START_OLD, SAVE_START_NEW)
    once(manager, SAVE_DONE_OLD, SAVE_DONE_NEW)
    once(manager, RECYCLE_OLD, RECYCLE_NEW)
    once(paths[STATE], COMPUTE_START_OLD, COMPUTE_START_NEW)
    once(paths[STATE], COMPUTE_END_OLD, COMPUTE_END_NEW)
    return list(paths.values())
