"""The pipeline build journal no longer counts a worker's wait for the main cache's background load, nor a pipeline the main
cache served, as a compilation (diagnostics only, every title).

IPA 727, Hogwarts Legacy (Core 737; private journals, aggregates only): every launch reports one worker pipeline "compiled
again" in 1.3 s: 1 308 ms (pid 54035), 1 346 ms (55836), 1 299 ms (56836). In 55836 and 56836 the main cache's background
load took 1 350 ms and 1 307 ms, and 20 ms after it the first worker lookup line reads "Worker pipelines found in the main
cache: 1 (not in it: 0)": the first worker creation of the launch waited in TryCreateFromMainCache
(PipelineCacheManager.WaitForMainLoadOnWorker, adapt_pipeline_cache_background) for the load, then the main cache served
it. PipelineState times the whole creation from its start (adapt_pipeline_build_journal, adapt_pipeline_cache_growth), so
the wait reached the journal as a compilation of a pipeline an earlier session had compiled: a lost pipeline, while none
was lost. The maintainer's audit read it as a pipeline compiled again.

Change (PipelineState.cs only): on a worker, TryCreateFromMainCache times its wait for the main load and records whether
the main cache served the creation (thread-local, reset when each creation starts); the journal takes the creation's time
without that wait, and nothing for a creation the main cache served. The first wait of 50 ms or more of a session is
recorded once in the engine journal ("pipelineBuilds mainLoadWait": the wait and whether the main cache then served the
creation). Not changed: the waits themselves, the lookup, every pipeline, the performance phases (graphicsPipelineBuild,
computePipelineBuild keep the whole creation), the render thread's creations (no main lookup, nothing to subtract).
Expected at the next launch: no "compiled again" for the first worker creation; refuted if a launch whose mainLoadWait line
says "served" still counts one. Rollback: remove this adapter. Fail closed on drift: PipelineState.cs must be the Core 741
preparation's.
"""
import hashlib
from adapt_session import once

STATE = 'src/Ryujinx.Graphics.Vulkan/PipelineState.cs'
BASELINE = {
    STATE: '21d559841f0a72c73cf2e48b0425a855159889e65aef811af889390dd0534fe0',
}
TAG = 'RewindBox (adapt_build_journal_load_wait)'

COMPUTE_START_OLD = '''            long buildStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_pipeline_cache_growth)
'''
COMPUTE_START_NEW = COMPUTE_START_OLD + '''            BeginBuildTiming(); // RewindBox (adapt_build_journal_load_wait)
'''
GRAPHICS_START_OLD = '''            long buildStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_pipeline_build_journal)
'''
GRAPHICS_START_NEW = GRAPHICS_START_OLD + '''            BeginBuildTiming(); // RewindBox (adapt_build_journal_load_wait)
'''
COMPUTE_NOTE_OLD = '''            // RewindBox (adapt_pipeline_cache_growth): compute compilations (50 ms or more) join the build journal.
            double buildMs = System.Diagnostics.Stopwatch.GetElapsedTime(buildStart).TotalMilliseconds;
'''
COMPUTE_NOTE_NEW = '''            // RewindBox (adapt_pipeline_cache_growth): compute compilations (50 ms or more) join the build journal.
            double buildMs = CompiledMs(buildStart); // RewindBox (adapt_build_journal_load_wait): without the main load wait
'''
GRAPHICS_NOTE_OLD = '''            // RewindBox (adapt_pipeline_build_journal): a compilation (50 ms or more) is noted with a key stable across sessions.
            double buildMs = System.Diagnostics.Stopwatch.GetElapsedTime(buildStart).TotalMilliseconds;
'''
GRAPHICS_NOTE_NEW = '''            // RewindBox (adapt_pipeline_build_journal): a compilation (50 ms or more) is noted with a key stable across sessions.
            double buildMs = CompiledMs(buildStart); // RewindBox (adapt_build_journal_load_wait): without the main load wait
'''
GRAPHICS_WAIT_OLD = '''GraphicsPipelineCreateInfo* info, Pipeline* handle)
        {
            gd.PipelineCacheManager.WaitForMainLoadOnWorker(); // RewindBox (adapt_pipeline_cache_background)
'''
GRAPHICS_WAIT_NEW = '''GraphicsPipelineCreateInfo* info, Pipeline* handle)
        {
            long loadWaitStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_build_journal_load_wait)
            gd.PipelineCacheManager.WaitForMainLoadOnWorker(); // RewindBox (adapt_pipeline_cache_background)
            NoteMainLoadWait(loadWaitStart); // RewindBox (adapt_build_journal_load_wait)
'''
COMPUTE_WAIT_OLD = '''ComputePipelineCreateInfo* info, Pipeline* handle)
        {
            gd.PipelineCacheManager.WaitForMainLoadOnWorker(); // RewindBox (adapt_pipeline_cache_background)
'''
COMPUTE_WAIT_NEW = '''ComputePipelineCreateInfo* info, Pipeline* handle)
        {
            long loadWaitStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_build_journal_load_wait)
            gd.PipelineCacheManager.WaitForMainLoadOnWorker(); // RewindBox (adapt_pipeline_cache_background)
            NoteMainLoadWait(loadWaitStart); // RewindBox (adapt_build_journal_load_wait)
'''
LOOKUP_OLD = '''        private static void NoteMainCacheLookup(bool hit)
        {
'''
LOOKUP_NEW = '''        // RewindBox (adapt_build_journal_load_wait): on the creating thread, the time the current creation waited for the main
        // cache's background load and whether the main cache served it (reset when each creation starts): neither is a
        // compilation for the build journal. The first wait of 50 ms or more of the session is recorded once.
        [ThreadStatic] private static long _mainLoadWaitTicks;
        [ThreadStatic] private static bool _servedByMain;
        [ThreadStatic] private static long _reportedLoadWaitTicks;
        private static int _mainLoadWaitRecorded;

        private static void BeginBuildTiming()
        {
            _mainLoadWaitTicks = 0;
            _servedByMain = false;
            _reportedLoadWaitTicks = 0;
        }

        private static void NoteMainLoadWait(long start)
        {
            long ticks = System.Diagnostics.Stopwatch.GetTimestamp() - start;
            _mainLoadWaitTicks += ticks;

            if (ticks * 1000 >= (long)PipelineCacheManager.CompiledBuildMs * System.Diagnostics.Stopwatch.Frequency &&
                System.Threading.Interlocked.Exchange(ref _mainLoadWaitRecorded, 1) == 0)
            {
                _reportedLoadWaitTicks = ticks;
            }
        }

        // The creation's time for the build journal: 0 when the main cache served it, else without the main load wait.
        private static double CompiledMs(long buildStart)
        {
            if (_servedByMain)
            {
                return 0;
            }

            long ticks = System.Diagnostics.Stopwatch.GetTimestamp() - buildStart - _mainLoadWaitTicks;

            return Math.Max(0, ticks) * 1000.0 / System.Diagnostics.Stopwatch.Frequency;
        }

        private static void NoteMainCacheLookup(bool hit)
        {
            _servedByMain = hit; // RewindBox (adapt_build_journal_load_wait)

            if (_reportedLoadWaitTicks != 0)
            {
                long waitMs = _reportedLoadWaitTicks * 1000 / System.Diagnostics.Stopwatch.Frequency;
                _reportedLoadWaitTicks = 0;
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineBuilds", "mainLoadWait", detail:
                    $"a worker pipeline creation waited {waitMs} ms for the main cache's background load, then the main cache " +
                    (hit ? "served it" : "did not hold it") + "; the wait is not counted as a compilation (adapt_build_journal_load_wait)");
            }

'''

PAIRS = [
    (STATE, COMPUTE_START_OLD, COMPUTE_START_NEW), (STATE, GRAPHICS_START_OLD, GRAPHICS_START_NEW),
    (STATE, COMPUTE_NOTE_OLD, COMPUTE_NOTE_NEW), (STATE, GRAPHICS_NOTE_OLD, GRAPHICS_NOTE_NEW),
    (STATE, GRAPHICS_WAIT_OLD, GRAPHICS_WAIT_NEW), (STATE, COMPUTE_WAIT_OLD, COMPUTE_WAIT_NEW),
    (STATE, LOOKUP_OLD, LOOKUP_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
