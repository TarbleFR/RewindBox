"""Cancel the queued background compiles when the guest stops, before the render loop drains its program disposals.

IPA 816-820, 22 November 2026 (private Core journal, not in the repository; times and counts only). A close goes
"teardown guestStop" -> "guestStopped" -> render loop drain -> "gpuRelease" -> "compilesCancelled". The guest stops in
27-518 ms in every session, and the wait is the drain: 7 ms and 2 ms for sessions closed at once, 4.5 s (Super Smash
Bros. Ultimate, 820), 13 s (SSBU, 818), 42 s (Hogwarts Legacy, 818), 69 s (SSBU, 819), and never ended for Hogwarts
Legacy on 816 (04:18:49 UTC) and 820 (14:04:51 UTC, the app killed after more than 100 s). In each slow close the
"compilesCancelled" line that follows reads "programs 24; ... shader modules 0, pipelines 0": every program of the game
had been disposed during the drain, and nothing was left to cancel.

Cause. Terminating the guest disposes its GPU channel's shader cache, which queues one program disposal per program on
the threaded renderer (about 2,150 for Hogwarts Legacy). The render loop executes them while it drains.
ShaderCollection.Dispose waits for that program's background compilation and for every pipeline compile queued for it;
only a detached, undemanded warm-up whose pipeline compile is already queued is cancelled there. A program still waiting
for its shader modules, one compiled during play, or one a draw had demanded is promoted and compiled first, on the
queues' few threads: the drain compiles the whole backlog, half a second to a second per pipeline in Metal's compiler.
The close's own cancellation (adapt_teardown_compile_cancel, adapt_teardown_cache: VulkanRenderer.BeginTeardown) runs
at the GPU release, which the embedded lifetime starts only once the loop has drained.

Change. Right after the guest is terminated (WindowBase's stop lambda, on the controlling thread), the renderer's
scheduler completes every compile no thread has taken with the ObjectDisposedException it already uses at Dispose, and
refuses new ones (BackgroundCompilationScheduler.CancelPending: both queues, every priority, demanded included). It
does not wait: the compiles that threads are running finish, as before, and those threads end. The program disposals
of the drain then find completed or cancelled tasks, which ShaderCollection already treats as a close's cancellation
(adapt_teardown_compile_cancel). Nothing waits for those results: the guest is terminated, and a pipeline not compiled
now is compiled when a later session needs it. BeginTeardown is unchanged and still joins the queues' threads before
the pipeline cache is saved; WorkerQueue.Dispose therefore joins also when the queue was already stopped, and reports
the count cancelled at the guest's stop. One durable journal line, "teardown guestCompilesCancelled", gives the counts
and the time. A failure of the cancellation leaves the close as it was.

A draw the render loop still executes during the drain and whose pipeline was cancelled is skipped or builds its
pipeline on the render thread, as when a background compile fails; the guest's last queued frames are not shown.
Not measured on an iPhone. Fail closed on drift: each file must be the Core 0fe58d62 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs': 'be16146c0e1362252cd2da96c44977068bd4296a95a78d5cd03c8756caa69063',
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '27f89c04260ce82bf3ff8468eda36785516b081567e260e534a7074bbf2eb2d8',
    'src/Ryujinx.Library/Window/WindowBase.cs': 'b5e37c5cc54f8e54f06525f67aeb21ccc1a582d87f7a1cbf256abbd689e3b0da',
}

SCHEDULER_PAIRS = (
    ('''        public void Dispose()
        {
            _shaderQueue.Dispose();
            _pipelineQueue.Dispose();
        }
''', '''        public void Dispose()
        {
            _shaderQueue.Dispose();
            _pipelineQueue.Dispose();
        }

        // RewindBox (adapt_guest_stop_compile_cancel): the guest is terminated and nothing draws for it any more. Every
        // compile no thread has taken completes with ObjectDisposedException and new ones are refused; the running ones
        // finish. Never waits; any thread. Dispose still joins the threads.
        public void CancelPending()
        {
            _shaderQueue.CancelPending();
            _pipelineQueue.CancelPending();
        }
'''),
    ('''            private bool _stopping;
''', '''            private bool _stopping;
            // RewindBox (adapt_guest_stop_compile_cancel): Dispose has joined, or is joining, the threads.
            private bool _joined;
'''),
    ('''            public void Dispose()
            {
                List<WorkItem> pending = [];

                lock (_queueLock)
                {
                    if (_stopping)
                    {
                        return;
                    }

                    _stopping = true;
''', '''            // RewindBox (adapt_guest_stop_compile_cancel): the cancellation of Dispose without its join.
            public void CancelPending()
            {
                List<WorkItem> pending = [];

                lock (_queueLock)
                {
                    if (_stopping)
                    {
                        return;
                    }

                    _stopping = true;
'''),
    ('''                    foreach (WorkItem item in pending)
                    {
                        item.Cancel(exception);
                    }
                }

                foreach (Thread thread in _threads)
''', '''                    foreach (WorkItem item in pending)
                    {
                        item.Cancel(exception);
                    }
                }
            }

            public void Dispose()
            {
                CancelPending();

                lock (_queueLock)
                {
                    if (_joined)
                    {
                        return;
                    }

                    _joined = true;
                }

                foreach (Thread thread in _threads)
'''),
)

RENDERER_PAIRS = (
    ('''        internal bool TeardownBegun => Volatile.Read(ref _teardownBegun) != 0;
''', '''        internal bool TeardownBegun => Volatile.Read(ref _teardownBegun) != 0;

        // RewindBox (adapt_guest_stop_compile_cancel): called by the embedded window once the guest is terminated, on its
        // controlling thread, while the render loop drains. The loop disposes every program of the guest's shader cache
        // there, and each disposal waited for the compiles queued for its program: the drain compiled the whole backlog
        // (IPA 816-820: 13 s to more than 100 s). Only the scheduler is touched; Shaders belongs to the render thread.
        public bool CancelCompilesAtGuestStop(out int shaderModules, out int pipelines)
        {
            BackgroundCompilationScheduler scheduler = BackgroundCompilationScheduler;

            shaderModules = 0;
            pipelines = 0;

            if (!_initialized || scheduler == null)
            {
                return false;
            }

            scheduler.CancelPending();
            shaderModules = scheduler.CancelledShaderCompiles;
            pipelines = scheduler.CancelledPipelineCompiles;

            return true;
        }
'''),
)

WINDOW_PAIRS = (
    ('''        private void BeginRendererTeardown()
        {
''', '''        // RewindBox (adapt_guest_stop_compile_cancel): the guest is terminated; the compiles still queued for its programs
        // are cancelled before the render loop's drain disposes those programs, which waited for each of them. A failure
        // here leaves the close as it was.
        private void CancelRendererCompilesAtGuestStop()
        {
            if (Renderer is not Ryujinx.Graphics.Vulkan.VulkanRenderer vulkan)
            {
                return;
            }

            try
            {
                long start = Stopwatch.GetTimestamp();

                if (vulkan.CancelCompilesAtGuestStop(out int shaderModules, out int pipelines))
                {
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "guestCompilesCancelled", detail:
                        $"cancelled before a thread took them: shader modules {shaderModules}, pipelines {pipelines}; " +
                        $"{(Stopwatch.GetTimestamp() - start) * 1000 / Stopwatch.Frequency} ms; the drain's program disposals do not wait for them");
                }
            }
            catch (Exception error)
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "guestCompileCancelFailed", detail: $"{error.GetType().Name}: {error.Message}");
            }
        }

        private void BeginRendererTeardown()
        {
'''),
    ('''                Device.System.Dispose();
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "guestStopped", detail:
''', '''                Device.System.Dispose();
                CancelRendererCompilesAtGuestStop(); // RewindBox (adapt_guest_stop_compile_cancel)
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("teardown", "guestStopped", detail:
'''),
)

FILE_PAIRS = {
    'src/Ryujinx.Graphics.Vulkan/BackgroundCompilationScheduler.cs': SCHEDULER_PAIRS,
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': RENDERER_PAIRS,
    'src/Ryujinx.Library/Window/WindowBase.cs': WINDOW_PAIRS,
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
