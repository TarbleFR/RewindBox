"""A compute program translated during play has its warm-up demanded at once; a demanded compile goes to the demand thread
while that thread waits for work (every title).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journals, pid 5954; counts and times only): the session's longest
pipeline wait on the render thread is one compute pipeline.
- computePipelineBuild: one call of 980.3 ms (performance window ending 04:32:03.50), in flight since about 04:31:58.42
  (38.3 ms at the end of the window before); the session's only compute build over 300 ms (527 calls for 180.0 ms in its
  first window, the startup warm-ups). In the Hogwarts sessions of builds 725 to 740 in the journals (10), two such builds:
  1 072 ms (727) and this one.
- Render stages 04:31:57.1-04:32:02.1: compute prepare 4 995 calls 1 292.8 ms, of which pipelines 976.4 ms (0.8 and 3.1 ms
  in the windows before and after). Render work 04:31:55.1-04:32:00.1: DispatchCompute 2 780 calls 1 296.1 ms. The sampler
  shows no presentation in the next second (t=52, process CPU 62 %), then a 1 133 ms presentation gap (t=53).
- What it was: the first build of a compute program new to this device, translated during play. MoltenVK hashed one new
  SPIR-V module between its reports of 04:31:54.0 and 04:32:08.7; the GPU thread's shader lookups took 116 calls, 45.5 ms
  and 4.9 MiB in the window ending 04:31:58.5 (2 calls, 0 ms before). In that report interval MoltenVK's maxima rose to
  727 ms for one MSL compile into a MTLLibrary (4 ms before) and 229 ms for one MTLFunction-to-pipeline compile (7 ms
  before), with 25 SPIR-V to MSL conversions for 290 ms (at most 54 ms each). The graphics builds of the three windows
  total 168, 49 and 182 ms and none was in flight at a window end: both maxima are inside the 980 ms, about 956 ms of
  Metal compilation and 24 ms of the rest. The build journal (compilations of 50 ms or more) counts it on a compile
  thread, not on the main cache (04:32:11: render thread 0; workers 3 in 1 147 ms; compiled again 0), and its key in
  none of the 23 earlier sessions.
- Not a specialization: every guest compute dispatch has SpecData.Empty (only the SMAA helper pipelines call Specialize),
  the key of the program's warm-up. Not a second build: the dispatch waited for that warm-up
  (ShaderCollection.TryWaitForBackgroundComputePipeline, adapt_setprogram_warmup); no main-cache build. Not a replay miss:
  a compute program has that one variant, and one read from the disk shader cache is warmed at startup (the 527 builds
  above), so the variant journal has nothing to add. Not skippable by design: ShaderInfoBuilder.BuildForCompute passes no
  pipeline state, so EnableAsyncCompile, and with it async compile skip, is false for every compute program.
- Why the render thread waited the whole build: the program is created by the render thread's CreateProgram command
  right before its SetProgram and its dispatch. Once its modules exist, its warm-up is scheduled high priority, not
  demanded; the one pipeline worker of a 6-core iPhone (Vulkan_Pipeline_Compile_0, base priority 31, default QoS, in the
  stall watch) takes it at once. The dispatch promotes it a few milliseconds later, and WorkerQueue.Promote leaves a taken
  item where it runs. The build (980.3 ms) began 3.9 ms or more before the render thread's wait (976.4 ms, the wait and
  the window's other lookups) and did not move, so it ran on that worker while the render thread (priority 47) waited.
  adapt_host_qos_pipeline_budget raised the demand thread to user-interactive QoS because the Metal compilation a thread
  requests runs at that thread's QoS; this one was not requested from there.

Change:
- ShaderCollection, constructor of a program with a pipeline state or compute: a compute program translated during play
  (VulkanRenderer.DetachPlayTimeWarmUps, compiled in the background) calls PromoteBackgroundCompilation() before its
  warm-up starts, as its dispatch would a few milliseconds later: the warm-up is scheduled demanded, and its shader
  modules' compiles are promoted (SetProgram promotes them for these programs anyway).
- BackgroundCompilationScheduler.WorkerQueue.TryTake (shader module and pipeline queues): while the demand thread waits for
  work, a background worker leaves it the first demanded compile only, and takes the next demanded compile, if any, before
  the high and low priority queues, as before; while the demand thread is busy, the workers take demanded compiles first,
  as before. The flag stays set from the demand thread's last empty look until it takes the lock back, so a worker that
  finishes during that wake-up leaves it only the one compile it will take. When the demand thread takes one
  and others remain, the waiting workers are woken. A worker starts a non-demanded compile only when no demanded compile
  is queued, or when exactly one is and the demand thread waits for work (it takes that one as it wakes).
Not changed: the pipeline, its key, the cache it is built in (the compile thread's own), what the dispatch binds and when
it waits, async compile skip (still off for compute), graphics programs' warm-ups, cached programs, the order inside each
queue (the first demanded compile goes to the demand thread, the next to a worker), teardown (the scheduler's Dispose
cancels a queued compile; CancelPendingWarmUp of a program whose warm-up is demanded returns at once, as it does today
once its dispatch has promoted it).

Scope: every title (DetachPlayTimeWarmUps is set for every title by adapt_playtime_warmup_all_titles). The first dispatch
of a compute program new to the device still waits for its Metal compilation: this adapter does not remove that wait, it
has the compilation requested from the demand thread (user-interactive QoS) whenever that thread is free. A later visit is
already fast (disk shader cache, startup warm-up, Metal's own cache). Expected on the device, not measured on an iPhone, no
FPS, heat or stability gain claimed: in a window with a single compute build of 300 ms or more, the hot profiles and stall
watch show the demand thread (priority 47), not Vulkan_Pipeline_Compile_0, waiting in MoltenVK; read with that window's
computePipelineBuild, the render stages' compute pipelines ms, MoltenVK's MTLLibrary compile maximum and the presentation
gap. Whether user-interactive QoS shortens the Metal compiler's work is not established here (the premise of
adapt_host_qos_pipeline_budget). Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

COLLECTION = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
SCHEDULER = 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs'
# Core bacdcacd preparation (IPA 745); no adapter of the IPA 746 lot edits these two files.
BASELINE = {
    COLLECTION: '41f18f7edd08bc7e5c451d167fc0a8ca3323ac46a02f19be291663437cad6a86',
    SCHEDULER: 'e96c9513aeb152b4be29e09a189173736f704eec23999b96a4c94cb66af9bb43',
}

DEMAND_OLD = '''            _state = state;

            // RewindBox (adapt_pipeline_variant_replay): states drawn late are recorded; a cached program replays them.
'''
DEMAND_NEW = '''            _state = state;

            // RewindBox (adapt_compute_warmup_demand): a compute program translated during play is created right before a
            // dispatch of it, which is never skipped and waits for this warm-up (its key, SpecData.Empty, is every guest
            // dispatch's). Demanded from the start, as that dispatch would demand it a few milliseconds later: the warm-up
            // is queued with the demanded compiles, not where a background worker takes it before the dispatch comes.
            if (IsCompute && playTimeWarmUp && compileInBackground)
            {
                PromoteBackgroundCompilation();
            }

            // RewindBox (adapt_pipeline_variant_replay): states drawn late are recorded; a cached program replays them.
'''

FIELD_OLD = '''            private bool _stopping;

            public int Cancelled { get; private set; }
'''
FIELD_NEW = '''            private bool _stopping;
            // RewindBox (adapt_compute_warmup_demand): the demand thread found no work and waits for it (under _queueLock).
            private bool _demandThreadWaiting;

            public int Cancelled { get; private set; }
'''

TAKE_OLD = '''            private WorkItem TryTake(bool demandOnly)
            {
                LinkedListNode<WorkItem> node = _demandQueue.First;

                if (node == null && !demandOnly)
                {
                    node = _highPriorityQueue.First ?? _lowPriorityQueue.First;
                }

                if (node == null)
                {
                    return null;
                }

                node.List.Remove(node);
'''
TAKE_NEW = '''            private WorkItem TryTake(bool demandOnly)
            {
                // RewindBox (adapt_compute_warmup_demand): a demanded compile is one a draw or a dispatch waits for or needs
                // next. While the demand thread waits for work, a background worker leaves it the first demanded compile,
                // so that compile and the Metal compilation it requests run at that thread's user-interactive QoS, not at a
                // worker's default QoS; the worker takes the next demanded compile before the other queues, and while the
                // demand thread is busy, the workers take demanded compiles first, as before.
                LinkedListNode<WorkItem> node = demandOnly || !_demandThreadWaiting
                    ? _demandQueue.First
                    : _demandQueue.First?.Next;

                if (node == null && !demandOnly)
                {
                    node = _highPriorityQueue.First ?? _lowPriorityQueue.First;
                }

                if (demandOnly)
                {
                    _demandThreadWaiting = node == null;
                }

                if (node == null)
                {
                    return null;
                }

                node.List.Remove(node);

                if (demandOnly && _demandQueue.First != null)
                {
                    // The demand thread is busy from here on: a waiting worker takes the next demanded compile.
                    Monitor.PulseAll(_queueLock);
                }
'''

PAIRS = ((COLLECTION, DEMAND_OLD, DEMAND_NEW), (SCHEDULER, FIELD_OLD, FIELD_NEW), (SCHEDULER, TAKE_OLD, TAKE_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
