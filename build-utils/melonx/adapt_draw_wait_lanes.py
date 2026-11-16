"""While a draw waits for a pipeline compile, the programs queued behind it are created and a second thread compiles them
(every title).

IPA 760 / Core 127b72b9, Super Smash Bros. Ultimate on the iPhone (private journals, pid 26654, 1 207 s; counts and times
only; docs/melonx-ssbu-stutter-2026-11-16.md):
- 60.0 FPS median; 203 presentation gaps of 50 ms or more, 28.8 s in all. The render thread's time to obtain pipelines in
  draw preparation is 62 ms per 5 s window at the median and 38.7 s over the session: 25.7 s above that median, and 28.2 s
  of the 28.8 s of gaps fall in the 42 windows that hold that excess.
- What the render thread waits for: the first pipeline of a program new to this device (345 programs translated during
  play, written to the disk shader cache afterwards). The build journal counts 253 compiles of 50 ms or more on the
  compile threads for 24.8 s (98 ms each), 3 on the render thread. MoltenVK's own statistics in the SSBU sessions of
  IPA 718 to 759 that have them give the split of such a compile: 3 to 4 ms per stage to convert SPIR-V to MSL, 24 to 34 ms
  per stage for Metal to compile the MSL into a library, 13 to 16 ms per pipeline for the rest.
- Not a thread priority matter: inside 37 of the 38 gaps the freeze watch sampled, no thread of the process runs (the
  compile thread, the render thread and the GPU thread wait; the work is in Metal's compiler, outside the process), and
  the 3 compiles made by the render thread itself (priority 47) took 116 ms each.
- One after the other: 11.2 s of the gap time is in gaps under 150 ms (one compile), 6.7 s in gaps of 150 to 250 ms and
  10.4 s in gaps of 250 ms or more (two compiles or more in one frame).

Why they run one after the other (read in the source):
- A program is created by the render thread: its CreateProgram command, or ProgramQueue.ProcessQueue, which creates
  every program the GPU thread has queued so far. While the render thread waits inside a draw for the first program's
  pipeline (ShaderCollection.TryWaitForBackgroundGraphicsPipeline), the GPU thread goes on translating the frame and
  queues the next programs, and nothing creates them: their compiles start only once the wait is over.
- A program's warm-up is scheduled high priority, not demanded. The one pipeline worker of a 6-core iPhone takes it at
  once; the demand thread takes demanded compiles only, and the draw's promotion of a compile already taken changes
  nothing (WorkerQueue.Promote). So in a burst the worker compiles every program in turn while the demand thread waits.

Change:
- GAL (ProgramQueue.cs, ThreadedRenderer.cs): RenderThreadPrograms, bound to the render thread by RunLoop for the time of
  its loop. CreateQueued() runs ProcessQueue on that thread's queue and returns how many programs it created; on any
  other thread, without a threaded renderer, or called from inside itself, it does nothing.
- BackgroundCompilationScheduler.WaitForPipelineAtDraw(task), called by the two waits a draw or a dispatch makes for a
  pipeline compile (TryWaitForBackgroundGraphicsPipeline with an infinite timeout, TryWaitForBackgroundComputePipeline)
  in place of task.Wait(): on a bound render thread it creates the queued programs, then waits for the task in slices of
  4 ms and creates the programs queued meanwhile after each; on any other thread it is task.Wait() and nothing else.
  The task's failure is thrown as Wait() throws it.
- WorkerQueue.Promote records a compile that is promoted once a thread has taken it (the draw's promotion, which until
  now changed nothing for such a compile); the end of the wait forgets it.
- WorkerQueue.TryTake (pipeline queue): while a draw waits and the compile it promoted is one a thread runs and has not
  completed, the demand thread, when no demanded compile is queued, takes the first high priority compile instead of
  waiting. Demanded compiles keep their precedence on both threads; the workers' rule is unchanged. A draw whose compile
  is not queued yet (its modules have just compiled) leaves the demand thread free for it, as before.
- Journal: the render-stage line gains, at its end, the draws that waited for a compile, the time, the programs created
  during those waits and the compiles the demand thread started ahead.
Not changed: the pipeline each draw binds, its key, and when the draw is made (no draw or dispatch is skipped, none is
made before its exact pipeline exists), async compile skip, the order in which programs are created (the queue's), what
a program's constructor does, the compile each thread runs once taken, the worker caches (a compile started ahead is
built in the demand thread's own cache, like a demanded one), teardown, the shader module queue.

What it costs: during those waits two pipeline compiles run at once instead of one, and the render thread wakes every 4 ms
(25 times per 98 ms compile). After such a wait the demand thread can still be busy with the compile it started ahead when
a draw demands another one: that one then goes to the worker if it is free, or waits for the first of the two to end
(before: the demand thread took it at once). The compile started ahead is the next program created, which is the next
program drawn. Two programs of the same code (adapt_sibling_pipelines: the second takes the first's pipeline instead of
compiling) that arrive in the same wait can now both compile it, since the second's compile starts before the first's
ends; the journals count 8 pipelines taken that way at one launch of Hogwarts Legacy and none in the SSBU session.
An independent reading of the first version of this adapter found the two cases the Promote record closes (the lane
opened for a draw whose compile was not queued yet, and stayed open after the awaited compile had ended).

Scope: every title; only programs whose compile a draw waits for (async shaders off, or a pipeline a draw must have).
Expected on the device, not measured on an iPhone, no FPS gain claimed: in a session that meets new shaders, the
render-stage lines show programs created during the waits and compiles started ahead, and the render thread's wait for
compiles falls below the compile threads' total of the build journal (they were equal: 25.7 s against 24.8 s); the gaps
of 150 ms or more shorten. A gap made by one compile (98 ms at the mean) is not shortened by this adapter. Refuted and
removed if no program is created during the waits, or if the gaps do not shorten. Rollback: drop this adapter from
prepare_embedded.py, ORDER and the plan. Fail closed on drift.
"""
import hashlib
from adapt_session import once

QUEUE = 'src/Ryujinx.Graphics.GAL/Multithreading/Resources/ProgramQueue.cs'
THREADED = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
COLLECTION = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
SCHEDULER = 'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs'
PIPELINE = 'src/Ryujinx.Graphics.Vulkan/PipelineBase.cs'
# The preparation of Core 9943a5ca (IPA 761).
BASELINE = {
    QUEUE: 'c770902a07d0c3f09a0021369303df3b7d72908d5d95bd961f61f26361d5d9ab',
    THREADED: '1a9a1284c026b148a5d8fb9ea9e3c69f3f4c1b2f8ee0222917bc67d3b2ebd966',
    COLLECTION: '587f38c84e6f62a60e85e3401f9b5ad63220026682f121685074c6f7123a4a64',
    SCHEDULER: '203c337bba4138676bdd2dec25303e5beddf615c1acb6b8a71ddf2fa4d814a79',
    PIPELINE: '9582a009b7156f35fdd67e39bca34c78b1253eb0b2f73ef619056b02c5589038',
}
SLICE_MS = 4

# --- GAL: the render thread's program queue, reachable by a backend that waits inside a draw.
BINDING_OLD = '''namespace Ryujinx.Graphics.GAL.Multithreading.Resources
{
    /// <summary>
    /// A structure handling multithreaded compilation for programs.
    /// </summary>
    class ProgramQueue
    {
'''
BINDING_NEW = '''namespace Ryujinx.Graphics.GAL.Multithreading.Resources
{
    /// <summary>
    /// RewindBox (adapt_draw_wait_lanes): the program queue of the render thread, for a backend whose draw waits on that
    /// thread for a compile. ThreadedRenderer.RunLoop binds it on the render thread for the time of its loop.
    /// </summary>
    public static class RenderThreadPrograms
    {
        [ThreadStatic]
        private static ProgramQueue _queue;

        [ThreadStatic]
        private static bool _creating;

        /// <summary>
        /// True on a render thread whose loop runs.
        /// </summary>
        public static bool Bound => _queue != null;

        internal static void Bind(ProgramQueue queue)
        {
            _queue = queue;
        }

        /// <summary>
        /// Creates the programs the GPU thread has queued, as the next CreateProgram command would (ProcessQueue), so
        /// that their compiles start now. Returns how many it created: 0 on a thread that is not a bound render thread,
        /// and when called from inside itself.
        /// </summary>
        public static int CreateQueued()
        {
            ProgramQueue queue = _queue;

            if (queue == null || _creating)
            {
                return 0;
            }

            _creating = true;

            try
            {
                return queue.CreateQueued();
            }
            finally
            {
                _creating = false;
            }
        }
    }

    /// <summary>
    /// A structure handling multithreaded compilation for programs.
    /// </summary>
    class ProgramQueue
    {
'''

COUNT_OLD = '''        public void Add(IProgramRequest request)
        {
            lock (_toCompile)
'''
COUNT_NEW = '''        // RewindBox (adapt_draw_wait_lanes): the programs ProcessQueue created (render thread only).
        private int _created;

        internal int CreateQueued()
        {
            int before = _created;

            ProcessQueue();

            return _created - before;
        }

        public void Add(IProgramRequest request)
        {
            lock (_toCompile)
'''

CREATE_OLD = '''                else
                {
                    program.Threaded.Base = program.Create(_renderer);
                }

                _inProgress.Add(program.Threaded);
'''
CREATE_NEW = '''                else
                {
                    program.Threaded.Base = program.Create(_renderer);
                    _created++; // RewindBox (adapt_draw_wait_lanes)
                }

                _inProgress.Add(program.Threaded);
'''

BIND_OLD = '''            _backendThread = Thread.CurrentThread;
            HostThreadQos.RaiseCurrentThread();
'''
BIND_NEW = '''            _backendThread = Thread.CurrentThread;
            HostThreadQos.RaiseCurrentThread();
            RenderThreadPrograms.Bind(Programs); // RewindBox (adapt_draw_wait_lanes): this thread runs the queue from here on
'''

UNBIND_OLD = '''            finally
            {
                _renderLoopExited.Set();
            }

            // Do not join here.'''
UNBIND_NEW = '''            finally
            {
                RenderThreadPrograms.Bind(null); // RewindBox (adapt_draw_wait_lanes)
                _renderLoopExited.Set();
            }

            // Do not join here.'''

# --- Vulkan: the wait of a draw, and the demand thread's work during it.
WAIT_OLD = '''        public bool TryCancelPipelineCompile(Task task)
        {
            return _pipelineQueue.TryCancel(task);
        }
'''
WAIT_NEW = '''        public bool TryCancelPipelineCompile(Task task)
        {
            return _pipelineQueue.TryCancel(task);
        }

        // RewindBox (adapt_draw_wait_lanes): the wait a draw or a dispatch slices to create the programs queued behind it.
        public const int DrawWaitSliceMs = ''' + str(SLICE_MS) + ''';

        // RewindBox (adapt_draw_wait_lanes): a draw or a dispatch waits here, on the render thread, for the pipeline
        // compile `task` (promoted by its caller). IPA 760, Super Smash Bros. Ultimate (pid 26654): 253 first compiles of
        // programs new to the device, 98 ms each in Metal's compiler, each waited for in full by the render thread
        // (25.7 s in 20 minutes), one after the other when a frame brings several (17 s of the 28.8 s of gaps). The
        // programs the GPU thread queues during the wait were created only after it, and the demand thread stayed idle
        // while the one worker compiled them in turn. Here the queued programs are created during the wait
        // (RenderThreadPrograms, the queue's own ProcessQueue) and, when the compile the draw promoted is one a thread
        // already runs, the pipeline queue lets its demand thread start the next high priority compile until that one
        // completes. Nothing else changes: the same pipelines, bound by the same draws; a failure of the task is thrown
        // as Wait() throws it.
        public void WaitForPipelineAtDraw(Task task)
        {
            if (!Ryujinx.Graphics.GAL.Multithreading.Resources.RenderThreadPrograms.Bound)
            {
                // Not the render thread of a threaded renderer: no program is queued behind this wait. As before.
                task.Wait();

                return;
            }

            long start = System.Diagnostics.Stopwatch.GetTimestamp();
            int created = 0;

            _pipelineQueue.BeginDrawWait(task);

            try
            {
                do
                {
                    created += Ryujinx.Graphics.GAL.Multithreading.Resources.RenderThreadPrograms.CreateQueued();
                }
                while (!task.Wait(DrawWaitSliceMs));
            }
            finally
            {
                _pipelineQueue.EndDrawWait(task);
                DrawWaitCounters.NoteWait(System.Diagnostics.Stopwatch.GetTimestamp() - start, created);
            }
        }
'''

FIELD_OLD = '''            // RewindBox (adapt_compute_warmup_demand): the demand thread found no work and waits for it (under _queueLock).
            private bool _demandThreadWaiting;
'''
FIELD_NEW = '''            // RewindBox (adapt_compute_warmup_demand): the demand thread found no work and waits for it (under _queueLock).
            private bool _demandThreadWaiting;
            // RewindBox (adapt_draw_wait_lanes): the task a draw waits for on the render thread, from the start of its wait
            // to its end, and the compile that draw promoted once a thread had taken it (both under _queueLock).
            private Task _awaitedAtDraw;
            private WorkItem _promotedInFlight;
'''

LANE_OLD = '''            // Removes work that no worker has taken yet; it completes with
            // ObjectDisposedException, like the work pending at Dispose.
'''
LANE_NEW = '''            // RewindBox (adapt_draw_wait_lanes): a draw starts to wait for `task`. With a high priority compile queued (the
            // workers are then busy), the waiting threads are woken: the demand thread takes it (TryTake).
            public void BeginDrawWait(Task task)
            {
                lock (_queueLock)
                {
                    _awaitedAtDraw = task;

                    if (_highPriorityQueue.First != null)
                    {
                        Monitor.PulseAll(_queueLock);
                    }
                }
            }

            public void EndDrawWait(Task task)
            {
                lock (_queueLock)
                {
                    if (ReferenceEquals(_awaitedAtDraw, task))
                    {
                        _awaitedAtDraw = null;
                    }

                    _promotedInFlight = null;
                }
            }

            // Removes work that no worker has taken yet; it completes with
            // ObjectDisposedException, like the work pending at Dispose.
'''

TAKE_OLD = '''                if (node == null && !demandOnly)
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
'''
TAKE_NEW = '''                if (node == null && !demandOnly)
                {
                    node = _highPriorityQueue.First ?? _lowPriorityQueue.First;
                }

                // RewindBox (adapt_draw_wait_lanes): while a draw waits for a compile that another thread runs (the draw
                // promoted it once taken), the render thread can demand nothing else, and the programs created during
                // that wait are the ones it draws next. The demand thread, with no demanded compile queued, starts the
                // first high priority one instead of waiting through that compile. Demanded compiles keep their
                // precedence on both threads; a draw whose compile is not queued yet leaves the demand thread free for it.
                if (node == null && demandOnly && _awaitedAtDraw is { IsCompleted: false } &&
                    _promotedInFlight is { Completion.Task.IsCompleted: false } && _highPriorityQueue.First != null)
                {
                    node = _highPriorityQueue.First;
                    DrawWaitCounters.NoteStartedAhead();
                }

                if (demandOnly)
                {
                    _demandThreadWaiting = node == null;
                }

                if (node == null)
                {
                    return null;
                }
'''

COUNTERS_OLD = '''namespace Ryujinx.Graphics.Vulkan
{
    sealed class BackgroundCompilationScheduler : IDisposable
    {
'''
COUNTERS_NEW = '''namespace Ryujinx.Graphics.Vulkan
{
    /// <summary>
    /// RewindBox (adapt_draw_wait_lanes): the waits of draws for a pipeline compile over a render-stage window, for the
    /// journal only: how many, their time, the programs created during them and the compiles the demand thread started
    /// ahead. Added by the render thread and the demand thread, read and cleared by the render-stage line.
    /// </summary>
    static class DrawWaitCounters
    {
        private static long _waits, _waitTicks, _created, _startedAhead;

        public static void NoteWait(long ticks, int created)
        {
            Interlocked.Increment(ref _waits);
            Interlocked.Add(ref _waitTicks, ticks);
            Interlocked.Add(ref _created, created);
        }

        public static void NoteStartedAhead()
        {
            Interlocked.Increment(ref _startedAhead);
        }

        public static string TakeText()
        {
            long ticks = Interlocked.Exchange(ref _waitTicks, 0);

            return "; draws that waited for a compile " + Interlocked.Exchange(ref _waits, 0) + " (" +
                (ticks * 1000.0 / System.Diagnostics.Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture) +
                " ms; programs created meanwhile " + Interlocked.Exchange(ref _created, 0) +
                ", compiles started ahead " + Interlocked.Exchange(ref _startedAhead, 0) + ")";
        }
    }

    sealed class BackgroundCompilationScheduler : IDisposable
    {
'''

GRAPHICS_OLD = '''                try
                {
                    task.Wait(timeoutMs);
                }
                catch (AggregateException)
                {
                    // The normal pipeline failure path handles a failed background task.
                }
'''
GRAPHICS_NEW = '''                try
                {
                    // RewindBox (adapt_draw_wait_lanes): a draw's wait (every caller's: no bound) creates the programs
                    // queued behind it and lets the demand thread start the next compile.
                    if (timeoutMs == Timeout.Infinite)
                    {
                        _gd.BackgroundCompilationScheduler.WaitForPipelineAtDraw(task);
                    }
                    else
                    {
                        task.Wait(timeoutMs);
                    }
                }
                catch (AggregateException)
                {
                    // The normal pipeline failure path handles a failed background task.
                }
'''

COMPUTE_OLD = '''                try
                {
                    task.Wait();
                }
                catch (AggregateException)
                {
                    // The dispatch compiles the pipeline itself.
                }
'''
COMPUTE_NEW = '''                try
                {
                    _gd.BackgroundCompilationScheduler.WaitForPipelineAtDraw(task); // RewindBox (adapt_draw_wait_lanes)
                }
                catch (AggregateException)
                {
                    // The dispatch compiles the pipeline itself.
                }
'''

LINE_OLD = '''                SubmitCausesText(); // RewindBox (adapt_submit_causes)
'''
LINE_NEW = '''                SubmitCausesText() + // RewindBox (adapt_submit_causes)
                DrawWaitCounters.TakeText(); // RewindBox (adapt_draw_wait_lanes)
'''

PROMOTE_OLD = '''                lock (_queueLock)
                {
                    if (_stopping ||
                        !_scheduled.TryGetValue(task, out WorkItem item) ||
                        item.Demanded ||
                        item.Node == null)
                    {
                        return;
                    }
'''
PROMOTE_NEW = '''                lock (_queueLock)
                {
                    // RewindBox (adapt_draw_wait_lanes): promoted once a thread has taken it: that thread runs it now.
                    if (!_stopping && _scheduled.TryGetValue(task, out WorkItem taken) && taken.Node == null)
                    {
                        _promotedInFlight = taken;
                    }

                    if (_stopping ||
                        !_scheduled.TryGetValue(task, out WorkItem item) ||
                        item.Demanded ||
                        item.Node == null)
                    {
                        return;
                    }
'''

PAIRS = ((QUEUE, BINDING_OLD, BINDING_NEW), (QUEUE, COUNT_OLD, COUNT_NEW), (QUEUE, CREATE_OLD, CREATE_NEW),
         (THREADED, BIND_OLD, BIND_NEW), (THREADED, UNBIND_OLD, UNBIND_NEW),
         (SCHEDULER, COUNTERS_OLD, COUNTERS_NEW), (SCHEDULER, WAIT_OLD, WAIT_NEW), (SCHEDULER, FIELD_OLD, FIELD_NEW),
         (SCHEDULER, PROMOTE_OLD, PROMOTE_NEW), (SCHEDULER, LANE_OLD, LANE_NEW), (SCHEDULER, TAKE_OLD, TAKE_NEW),
         (COLLECTION, GRAPHICS_OLD, GRAPHICS_NEW), (COLLECTION, COMPUTE_OLD, COMPUTE_NEW),
         (PIPELINE, LINE_OLD, LINE_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
