"""A graphics state a skipped draw queued for a background compile is recorded for the next launch once built, the draws
that wait for such a compile are counted with the render thread's time, and the render stages tell skips for a queued state
from skips for shader modules not ready (every title).

Evidence (IPA 740 / Core da2525a1, Hogwarts Legacy, private journals, pid 5954; counts and times only):
- 233 draws were skipped in the session ("not ready by cause: async skips"; 19, 87 and 30 in the stage windows of
  04:32:12, 04:32:17 and 04:32:22). That counter adds two causes the logs cannot separate: a draw whose program's shader
  modules are not compiled yet (PrepareGraphicsDraw and CreatePipeline, UpdateProgramStagesIfReady false: nothing to
  record, no pipeline state was queued) and a draw whose pipeline state was queued for a background compile
  (QueueBackgroundGraphicsPipeline), counted once per skipped draw, so several times per queued state.
- A queued state never reaches the variant journal (adapt_pipeline_variant_replay): PipelineBase.CreatePipeline notes a
  late state (ShaderCollection.NoteLateVariant, its only call site) after the draw obtained a pipeline; the draw that
  queues the state returns before that note, and once the compile is built the next draws find it in the program's table
  (TryGetGraphicsPipeline) and note nothing. CompileQueuedGraphicsPipeline notes nothing either.
- Those are the costly states: MoltenVK's statistics show 77 SPIR-V to MSL conversions (1067 ms) and 77 MSL compiles (5040
  ms, longest 1364 ms) between 04:32:08 and 04:32:22 for 6 new shader modules; the build journal counts 12 worker
  compilations of 50 ms or more (9906 ms) between 04:32:11 and 04:33:33, none compiled in an earlier session.
- Without this adapter such a state can still come back a session later as a late creation of the render thread (about
  3.5 ms: 975 ms for 281 late creations), when the worker's cache was merged into the main cache at the next startup
  (Hogwarts' previous session: 19 merges, 10 refused for low memory, 2 for a busy lock), and is recorded then if the
  journal has room.
- The logs do not tell how long draws waited for a queued compile. "draws that joined another queued compile" is 0 in all
  23 pipelineVariants summaries of this core log, but it counts only the draws that cannot skip (CreatePipeline's
  lateJoined); a draw into a critical offscreen target (waitForBackgroundGraphicsPipeline) that joins a compile a skipped
  draw queued waits for it without a timeout and, as the first note of the state, was counted among the late creations
  (281, 975 ms in the session). Every worker creation also waits for the main cache's background load first
  (TryCreateFromMainCache): the first such wait of 50 ms or more is logged at every launch, 1260 and 1547 ms in this core
  log (1202 to 1750 ms in two earlier core logs); adapt_build_journal_load_wait does not count it as a compilation.

Change (PipelineBase.cs, ShaderCollection.cs, PipelineCacheManager.cs):
- A draw that will skip hands its framebuffer to QueueBackgroundGraphicsPipeline (a draw that will wait hands none and
  notes the state itself). For a program that records variants, the new compile keeps the framebuffer's colour slots and
  its key is registered (_queuedForRecord) before the compile starts, until it leaves the queue.
- CompileQueuedGraphicsPipeline times the creation on its worker without the worker's wait for the main cache's load
  (PipelineCacheManager.WorkerLoadWaitTicks, a per-thread sum that WaitForMainLoadOnWorker adds to only when it waits; the
  wait itself is unchanged). Once the pipeline is built and before the compile leaves the queue, it keeps the pipeline's
  handle (_queuedBuilt) and records the state with those slots and that time (ShaderCollection.NoteQueuedVariant: the
  warm-up's own state excepted, as in NoteLateVariant; best effort). A failed compile records nothing (its failure marker
  stays as before).
- NoteLateVariant (a draw that missed the program's table and then obtained the pipeline) passes "waitedForSkipped" when the
  pipeline it obtained is one such a compile built, or such a compile is still registered for the state: the draw waited
  for it (CreatePipeline's two waits without a timeout), or obtained it in the instant it was built.
- PipelineVariantJournal.NoteLate counts both before the session's once-per-state gate. builtForSkipped (the compile's own
  note): "built for skipped draws N (compile M ms, without the main cache's load wait)", once per state and session
  (_builtForSkipped), with that compile's time, whichever note records the state. waitedForSkipped (a draw's note): "draws
  that waited for them W (X ms)", each draw, with the render thread's time from the draw's miss to its pipeline. Neither is
  a late creation; the first note of the state records it as a late state is recorded (once per session, the journal's
  bounds and eviction of adapt_variant_journal_room), and a failure marker of the state is cleared, as when a draw
  obtains it. A repeat writes nothing.
- RenderStageTimer.AsyncQueuedSkips: the skips of draws whose state is queued; the render stages line reads "async skips
  N (pipeline state queued Q, shader modules not ready N-Q)". The three AsyncSkips increments are unchanged.
Nothing changes for a draw: it still skips while the compile runs, waits where it waited, and binds the pipeline once
built; no early return, no skip and no wait is added.

Bound (from the logs, not measured): at most the distinct states queued by skipping draws in a session (not the 233
skips), each replayed at the next launch instead of being created late on the render thread (about 3.5 ms each), one
session earlier than the cache merge would allow, or skipped again when the merge was refused. Nothing for the first visit
of an area (04:32:19). A replay at launch was cheap in IPA 740 (1928 replays, compile 187 ms, queue wait 8689 ms). Without
adapt_variant_journal_room a full journal drops these states too (Hogwarts had room for 115 at that launch). Memory: a
handle (8 bytes) per pipeline built for a skipped draw, for the program's life, and a key (16 bytes) per such state and
session in the journal; no pipeline is added.

Expected on the device: the render stages' "pipeline state queued Q" and "shader modules not ready" in the windows of
04:32:12-04:32:22's kind; "built for skipped draws N (compile M ms, ...)" in the pipelineVariants summaries with N at most
the distinct queued states, and "draws that waited for them W (X ms)", the render thread's waits that "late creations"
used to hold; at the next launch in an area already visited, a lower "pipeline state queued" and more "ready before their
first draw". Not measured on an iPhone; no FPS, heat or stability gain claimed. Runs after adapt_variant_journal_room (its
post-image of PipelineCacheManager.cs; this adapter's anchors there are text of Core bacdcacd, so without that adapter
only its digest changes, 45ee8376...). ShaderCollection.cs is also edited by adapt_compute_warmup_demand, which runs
before both journal adapters (constructor and scheduler, anchors disjoint from these): this adapter takes its post-image
of that file (b019b24b...; the composition is the same in either order). Rollback:
drop this adapter from prepare_embedded.py and ORDER (recorded queued states then replay as any recorded state). Fail
closed on drift.
"""
import hashlib
from adapt_session import once

DRAWS = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
PROGRAM = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
MANAGER = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'

BASELINE = {
    DRAWS: 'a4660b4d61585fd740d619f40f42d8ec5be181f49a425fc0b906b93b42a2271a',  # Core bacdcacd (IPA 745)
    PROGRAM: 'b019b24beb8185b5fb4c476d045d730f0cb4345ae2e1ed23f153a02ced1b34c0',  # adapt_compute_warmup_demand
    MANAGER: '8090b9dc466a344b903f43b4ede8b45441b729160542ce0c038f227bb26ede13',  # adapt_variant_journal_room
}

# --- PipelineBase.cs: the split counter; a draw that will skip hands its framebuffer with the state it queues ---
STAGE_FIELDS_OLD = '''        public static long AsyncSkips, UnavailablePipelines; // RewindBox (adapt_pipeline_failure_identity)
        public static long PipelineTicks, Pipelines;
'''
STAGE_FIELDS_NEW = '''        public static long AsyncSkips, UnavailablePipelines; // RewindBox (adapt_pipeline_failure_identity)
        // RewindBox (adapt_queued_variant_record): the async skips of draws whose pipeline state is queued for a background
        // compile (the other async skips wait for the program's shader modules).
        public static long AsyncQueuedSkips;
        public static long PipelineTicks, Pipelines;
'''

STAGE_LOG_OLD = '''                "; not ready by cause: async skips " + AsyncSkips + ", unavailable pipelines " + UnavailablePipelines +
                SubmitCausesText(); // RewindBox (adapt_submit_causes)
            AsyncHeld = AsyncHeldTicks = 0;
            AsyncSkips = UnavailablePipelines = 0;
'''
STAGE_LOG_NEW = '''                "; not ready by cause: async skips " + AsyncSkips + " (pipeline state queued " + AsyncQueuedSkips +
                ", shader modules not ready " + (AsyncSkips - AsyncQueuedSkips) + ")" + // RewindBox (adapt_queued_variant_record)
                ", unavailable pipelines " + UnavailablePipelines +
                SubmitCausesText(); // RewindBox (adapt_submit_causes)
            AsyncHeld = AsyncHeldTicks = 0;
            AsyncSkips = UnavailablePipelines = AsyncQueuedSkips = 0;
'''

QUEUE_CALL_OLD = '''                        if (pipeline == null &&
                            canSkipForBackgroundCompile &&
                            _program.QueueBackgroundGraphicsPipeline(ref _newState, renderPass))
                        {
                            if (!waitForBackgroundGraphicsPipeline)
                            {
                                _renderPassHadSkippedDraw = true;
                                RenderStageTimer.AsyncSkips++; // RewindBox (adapt_pipeline_failure_identity)
                                return false;
                            }
'''
QUEUE_CALL_NEW = '''                        // RewindBox (adapt_queued_variant_record): a draw that will skip hands its framebuffer: the state is
                        // recorded for the next launch once built. A draw that will wait hands none and notes it itself.
                        if (pipeline == null &&
                            canSkipForBackgroundCompile &&
                            _program.QueueBackgroundGraphicsPipeline(
                                ref _newState, renderPass, waitForBackgroundGraphicsPipeline ? null : FramebufferParams))
                        {
                            if (!waitForBackgroundGraphicsPipeline)
                            {
                                _renderPassHadSkippedDraw = true;
                                RenderStageTimer.AsyncSkips++; // RewindBox (adapt_pipeline_failure_identity)
                                RenderStageTimer.AsyncQueuedSkips++; // RewindBox (adapt_queued_variant_record)
                                return false;
                            }
'''

# --- ShaderCollection.cs: the queued compile keeps the colour slots, is registered, times its creation without the main
# cache's load wait, keeps its pipeline's handle and records the state once built; a draw's note says it waited for it ---
FIELDS_OLD = '''        private int _replayedUnusedCount;
        private readonly object _initializeLock;
'''
FIELDS_NEW = '''        private int _replayedUnusedCount;
        // RewindBox (adapt_queued_variant_record): the states whose queued compile records them once built (a draw that
        // skipped queued them), from before the compile starts until it leaves the queue; and the handles of the pipelines
        // those compiles built, for the program's life (a draw that missed one and obtained it waited for that compile).
        // Under _pipelineCacheLock.
        private HashTableSlim<PipelineUid, byte> _queuedForRecord;
        private HashSet<ulong> _queuedBuilt;
        private readonly object _initializeLock;
'''

QUEUE_SIGNATURE_OLD = '''        public bool QueueBackgroundGraphicsPipeline(
            ref PipelineState state,
            Auto<DisposableRenderPass> renderPass)
        {
'''
QUEUE_SIGNATURE_NEW = '''        public bool QueueBackgroundGraphicsPipeline(
            ref PipelineState state,
            Auto<DisposableRenderPass> renderPass,
            FramebufferParams recordFor = null)
        {
'''

QUEUE_TASK_OLD = '''                task = CompileQueuedGraphicsPipeline(state.Clone(), renderPass, key);
                (_graphicsPipelineBackgroundQueue ??= new()).Add(ref key, task);
'''
QUEUE_TASK_NEW = '''                // RewindBox (adapt_queued_variant_record): the colour slots of the draw that skips (none: not recorded), its
                // key registered before the compile starts (a compile that ends at once removes it as it leaves the queue).
                int[] colorSlots = recordFor != null && _recordsVariants
                    ? recordFor.AttachmentIndices.AsSpan(0, recordFor.ColorAttachmentsCount).ToArray()
                    : null;

                if (colorSlots != null)
                {
                    (_queuedForRecord ??= new()).Add(ref key, 0);
                }

                task = CompileQueuedGraphicsPipeline(state.Clone(), renderPass, key, colorSlots);
                (_graphicsPipelineBackgroundQueue ??= new()).Add(ref key, task);
'''

COMPILE_OLD = '''            Auto<DisposableRenderPass> renderPass,
            PipelineUid key)
        {
            Auto<DisposablePipeline> pipeline = null;

            try
            {
                await RunBackgroundPipelineCompile(pipelineCache =>
                {
                    pipeline = state.CreateGraphicsPipeline(
                        _gd,
                        _device,
                        this,
                        pipelineCache,
                        renderPass.GetUnsafe().Value,
                        throwOnError: false,
                        cachePipelineFailure: false);
                }, highPriority: true, demanded: true);

                if (pipeline == null)
                {
                    AddBackgroundGraphicsPipelineFailure(ref key);
                }
            }
'''
COMPILE_NEW = '''            Auto<DisposableRenderPass> renderPass,
            PipelineUid key,
            int[] colorSlots = null)
        {
            Auto<DisposablePipeline> pipeline = null;
            long compileTicks = 0; // RewindBox (adapt_queued_variant_record)

            try
            {
                await RunBackgroundPipelineCompile(pipelineCache =>
                {
                    // RewindBox (adapt_queued_variant_record): the creation's time on this worker, without its wait for the
                    // main cache's background load (not a compilation: adapt_build_journal_load_wait leaves it out too).
                    long loadWait = PipelineCacheManager.WorkerLoadWaitTicks;
                    long compileStart = System.Diagnostics.Stopwatch.GetTimestamp();
                    pipeline = state.CreateGraphicsPipeline(
                        _gd,
                        _device,
                        this,
                        pipelineCache,
                        renderPass.GetUnsafe().Value,
                        throwOnError: false,
                        cachePipelineFailure: false);
                    compileTicks = System.Diagnostics.Stopwatch.GetTimestamp() - compileStart -
                        (PipelineCacheManager.WorkerLoadWaitTicks - loadWait);
                }, highPriority: true, demanded: true);

                if (pipeline == null)
                {
                    AddBackgroundGraphicsPipelineFailure(ref key);
                }
                else if (colorSlots != null)
                {
                    // RewindBox (adapt_queued_variant_record): built for a skipped draw: recorded before the compile leaves the
                    // queue (a draw that waited for it notes after this and is counted apart).
                    NoteQueuedVariant(ref state, pipeline, colorSlots, compileTicks);
                }
            }
'''

COMPILE_EXIT_OLD = '''                lock (_pipelineCacheLock)
                {
                    _graphicsPipelineBackgroundQueue?.Remove(ref key);
                }
            }
        }
'''
COMPILE_EXIT_NEW = '''                lock (_pipelineCacheLock)
                {
                    _graphicsPipelineBackgroundQueue?.Remove(ref key);
                    _queuedForRecord?.Remove(ref key); // RewindBox (adapt_queued_variant_record)
                }
            }
        }
'''

NOTE_OLD = '''            journal.NoteLate(
                StableHash,
                state.WriteVariant(framebuffer.AttachmentIndices.AsSpan(0, framebuffer.ColorAttachmentsCount)),
                (long)elapsed.TotalMilliseconds,
                joined,
                replayJoined: TakeReplayed(pipelineHandle, out _));
        }
'''
NOTE_NEW = '''            // RewindBox (adapt_queued_variant_record): the pipeline the draw obtained is one a compile a skipped draw queued
            // built, or that compile is still registered for this state: the draw waited for it (or obtained it in the instant
            // it was built). Counted apart, with the render thread's time; that compile's own note counts the state.
            bool waitedForSkipped;

            lock (_pipelineCacheLock)
            {
                waitedForSkipped = (_queuedForRecord != null && _queuedForRecord.TryGetValue(ref state.Internal, out _)) ||
                    (_queuedBuilt != null && _queuedBuilt.Contains(pipelineHandle));
            }

            journal.NoteLate(
                StableHash,
                state.WriteVariant(framebuffer.AttachmentIndices.AsSpan(0, framebuffer.ColorAttachmentsCount)),
                (long)elapsed.TotalMilliseconds,
                joined,
                replayJoined: TakeReplayed(pipelineHandle, out _),
                waitedForSkipped: waitedForSkipped);
        }

        // RewindBox (adapt_queued_variant_record): a state a skipped draw queued for a background compile, once built, is
        // recorded for the next launch as a state obtained late is (NoteLateVariant), counted apart with the compile's time
        // (without the main cache's load wait): the draw that queued it obtained nothing to note, and the draws after it find
        // it built. Its pipeline is kept known (a draw that waited for it). The warm-up's own state is not recorded. Best
        // effort, on the compile's thread.
        private void NoteQueuedVariant(ref PipelineState state, Auto<DisposablePipeline> pipeline, int[] colorSlots, long compileTicks)
        {
            PipelineVariantJournal journal = _gd.PipelineCacheManager?.Variants;

            if (journal == null || !_recordsVariants || _disposed)
            {
                return;
            }

            try
            {
                PipelineUid initial = GetInitialGraphicsPipelineKey();

                if (state.Internal.Equals(ref initial))
                {
                    return;
                }

                lock (_pipelineCacheLock)
                {
                    (_queuedBuilt ??= new()).Add(pipeline.GetUnsafe().Value.Handle);
                }

                journal.NoteLate(
                    StableHash,
                    state.WriteVariant(colorSlots),
                    Math.Max(0, compileTicks) * 1000 / System.Diagnostics.Stopwatch.Frequency,
                    joined: false,
                    builtForSkipped: true);
            }
            catch (Exception)
            {
                // The pipeline is built and stays in use; a state that cannot be noted is not a failed compile.
            }
        }
'''

# --- PipelineCacheManager.cs: a worker's wait for the main load is summed per thread; PipelineVariantJournal counts a
# state built for skipped draws and the draws that waited for it apart, before its once-per-state gate ---
LOAD_WAIT_OLD = '''            long remaining = Interlocked.Read(ref _mainLoadWaitDeadline) - Environment.TickCount64;

            if (remaining > 0)
            {
                _mainLoaded.Wait((int)Math.Min(remaining, int.MaxValue));
            }
        }
'''
LOAD_WAIT_NEW = '''            long remaining = Interlocked.Read(ref _mainLoadWaitDeadline) - Environment.TickCount64;

            if (remaining > 0)
            {
                long waitStart = System.Diagnostics.Stopwatch.GetTimestamp(); // RewindBox (adapt_queued_variant_record)
                _mainLoaded.Wait((int)Math.Min(remaining, int.MaxValue));
                WorkerLoadWaitTicks += System.Diagnostics.Stopwatch.GetTimestamp() - waitStart;
            }
        }

        // RewindBox (adapt_queued_variant_record): on each thread, the Stopwatch ticks WaitForMainLoadOnWorker waited for the
        // main snapshot (never reset): a compile a skipped draw queued leaves its own creation's share out of its time.
        [ThreadStatic]
        internal static long WorkerLoadWaitTicks;
'''

COUNTERS_OLD = '''        internal long JoinedReplayMs, JoinedOtherMs, LateMs, QueueWaitMs;

        public PipelineVariantJournal(string path,'''
COUNTERS_NEW = '''        internal long JoinedReplayMs, JoinedOtherMs, LateMs, QueueWaitMs;
        // RewindBox (adapt_queued_variant_record): states built by compiles skipped draws queued (once per state and session,
        // _builtForSkipped) and their compile time without the main cache's load wait; draws that waited for such a compile
        // and the render thread's time.
        internal int DrawQueued, WaitedForSkipped;
        internal long DrawQueuedMs, WaitedForSkippedMs;
        private readonly HashSet<(ulong, ulong)> _builtForSkipped = new();

        public PipelineVariantJournal(string path,'''

NOTE_SIGNATURE_OLD = '''        public void NoteLate(ulong program, byte[] variant, long elapsedMs, bool joined, bool replayJoined = false)
'''
NOTE_SIGNATURE_NEW = '''        // builtForSkipped (adapt_queued_variant_record): the note of a compile a skipped draw queued (ShaderCollection.
        // NoteQueuedVariant); waitedForSkipped: a draw's, whose pipeline is one such a compile built or was building.
        public void NoteLate(ulong program, byte[] variant, long elapsedMs, bool joined, bool replayJoined = false,
            bool builtForSkipped = false, bool waitedForSkipped = false)
'''

GATE_OLD = '''            lock (_lock)
            {
                // Not before the journal is read (the first second of a launch), and at most 4 notes per kept variant.
'''
GATE_NEW = '''            lock (_lock)
            {
                // RewindBox (adapt_queued_variant_record): counted before the session's once-per-state gate. A state a skipped
                // draw's compile built: once per session, with that compile's time, whichever note records the state. A draw
                // that waited for such a compile: each, with the render thread's time (that compile's note came just before,
                // or comes just after). Neither is a late creation.
                if (!_stopped)
                {
                    if (builtForSkipped)
                    {
                        if (_builtForSkipped.Count < 4 * MaxRecords && _builtForSkipped.Add(key))
                        {
                            DrawQueued++;
                            DrawQueuedMs += elapsedMs;
                        }
                    }
                    else if (waitedForSkipped)
                    {
                        WaitedForSkipped++;
                        WaitedForSkippedMs += elapsedMs;
                    }
                }

                // Not before the journal is read (the first second of a launch), and at most 4 notes per kept variant.
'''

BRANCH_OLD = '''                bool markedFailed = _failed.Remove(key); // the draw obtained it: a valid state, its marker is cleared

                if (replayJoined)
                {
'''
BRANCH_NEW = '''                bool markedFailed = _failed.Remove(key); // the draw obtained it: a valid state, its marker is cleared

                if (builtForSkipped || waitedForSkipped)
                {
                    // RewindBox (adapt_queued_variant_record): counted above; recorded below, not a late creation.
                }
                else if (replayJoined)
                {
'''

SUMMARY_OLD = '''                    $"built yet {LatePlanned}, built but missed {LateAfterBuilt}, after a failed replay {LateAfterFailed}. Replays: built " +
'''
SUMMARY_NEW = '''                    $"built yet {LatePlanned}, built but missed {LateAfterBuilt}, after a failed replay {LateAfterFailed}; built for " +
                    $"skipped draws {DrawQueued} (compile {DrawQueuedMs} ms, without the main cache's load wait), draws that waited " +
                    $"for them {WaitedForSkipped} ({WaitedForSkippedMs} ms). Replays: built " +
'''

EDITS = {
    DRAWS: ((STAGE_FIELDS_OLD, STAGE_FIELDS_NEW), (STAGE_LOG_OLD, STAGE_LOG_NEW), (QUEUE_CALL_OLD, QUEUE_CALL_NEW)),
    PROGRAM: ((FIELDS_OLD, FIELDS_NEW), (QUEUE_SIGNATURE_OLD, QUEUE_SIGNATURE_NEW), (QUEUE_TASK_OLD, QUEUE_TASK_NEW),
              (COMPILE_OLD, COMPILE_NEW), (COMPILE_EXIT_OLD, COMPILE_EXIT_NEW), (NOTE_OLD, NOTE_NEW)),
    MANAGER: ((LOAD_WAIT_OLD, LOAD_WAIT_NEW), (COUNTERS_OLD, COUNTERS_NEW), (NOTE_SIGNATURE_OLD, NOTE_SIGNATURE_NEW),
              (GATE_OLD, GATE_NEW), (BRANCH_OLD, BRANCH_NEW), (SUMMARY_OLD, SUMMARY_NEW)),
}


def apply(source):
    paths = {name: source / name for name in EDITS}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in EDITS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
