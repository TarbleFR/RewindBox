"""The render thread reads the clock once per queued command instead of twice: a command of a drain starts when the
previous one's time ended (every title).

Evidence (IPA 748-751 / Core 030cc14f, private journals, [MeloNX:hot] profiles of the render thread; counts and times
only): the clock read (GCToOSInterface::QueryPerformanceCounter, folded code) is called from RenderLoop and
NoteRenderCommand: 10 of 756 running samples (5 and 5) in the slow profiles of 11238 (0.48 ms per game frame), 17 of 492
(0.89 ms) and 11 of 328 (0.74 ms) in 12613, 11 of 784 in IPA 740; SSBU (14991) 29 of 409 (7.1 %: 16 RenderLoop, 11
NoteRenderCommand, 2 PrepareGraphicsDraw; 0.28 ms per frame). RenderLoop reads the clock before each command and
NoteRenderCommand reads it again after (adapt_host_qos_pipeline_budget's "Render thread commands over 5 s" line, which
other analyses read: kept); within a drain one command follows the other without a wait.

Change (ThreadedRenderer.cs, render thread only):
- NoteRenderCommand returns the time the next command starts at: its own end read, or, once the 5 s line was written, a
  new read (the line's time is no command's).
- RenderLoop keeps that value for the next command of the same drain; the drain's first command reads the clock as
  before (the value starts at 0 for each drain, so the wait for work is never counted). After a synchronous command
  wakes its waiter (adapt_sync_wait_attribution's own-time write, unchanged, then _invokeRun.Set()), the next command
  reads the clock again, so the wake-up is not counted either.
What is counted moves by the loop's own bookkeeping between two commands of a drain (the invoke check, the queue
pointers, the count decrement and the loop test, a few tens of nanoseconds), now added to the next command; busy time,
calls and the top list keep their meaning. Nothing else changes: no wait, no allocation, the same line and the same
synchronous-wait attribution. Guest-visible behaviour is identical (the change is in diagnostics only).

Host proof (gate sync-wait-attribution, final preparation, production GAL with a backend double): the same two render
work lines and the same synchronous-wait attribution as the candidate of adapt_sync_wait_attribution (a 200 ms read-back
behind 300 ms of work, actions of 0 and 150 ms, a second window); NoteRenderCommand returns the next start, 1 000
commands chained on it add exactly the time they span, and after a window's line the start returned is read after it.

Scope: every title. Bound (plan 748 rank 14, not measured): about half of those samples, at most 0.25 to 0.45 ms per game
frame for Hogwarts Legacy and about 0.14 ms for SSBU. Expected on the device: the render thread's clock-read samples
about halved in the [MeloNX:hot] profiles; the "Render thread commands" line unchanged in form, its busy time slightly
higher by the loop's bookkeeping. Not measured on an iPhone.
Runs after adapt_pinned_command_queue (its post-image of ThreadedRenderer.cs). The staged, unwired
adapt_render_command_longest anchors on Core 030cc14f's RenderLoop and NoteRenderCommand: wired later, it must be rebased
on this adapter's post-image and take its collection count with the same start. Rollback: drop this adapter from
prepare_embedded.py and ORDER (last edit of the file). Fail closed on drift.
"""
import hashlib
from adapt_session import once

RENDERER = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
BASELINE = {RENDERER: '8f65cf71b5680b83afddbab801c5802444f2815c6e8e937086b97e7cb3979714'}  # adapt_pinned_command_queue's post-image

NOTE_OLD = '''        private void NoteRenderCommand(byte type, long start)
        {
            long end = Stopwatch.GetTimestamp();
            _renderWorkTicks[type] += end - start;
            _renderWorkCalls[type]++;

            if (_renderWorkStart == 0)
            {
                _renderWorkStart = start;
            }
            else if (end - _renderWorkStart >= Stopwatch.Frequency * 5)
            {
                LogRenderWork(end);
            }
        }
'''
NOTE_NEW = '''        // RewindBox (adapt_render_command_clock): returns when the next command of the same drain starts: this command's
        // end read, or a new read once the window's line was written (its time is no command's).
        private long NoteRenderCommand(byte type, long start)
        {
            long end = Stopwatch.GetTimestamp();
            _renderWorkTicks[type] += end - start;
            _renderWorkCalls[type]++;

            if (_renderWorkStart == 0)
            {
                _renderWorkStart = start;
            }
            else if (end - _renderWorkStart >= Stopwatch.Frequency * 5)
            {
                LogRenderWork(end);

                return Stopwatch.GetTimestamp();
            }

            return end;
        }
'''

DRAIN_OLD = '''                using (PD.Measure(PD.Phase.RenderDrain))
                while (Volatile.Read(ref _commandCount) > 0 && Volatile.Read(ref _interruptAction) == null)
'''
DRAIN_NEW = '''                // RewindBox (adapt_render_command_clock): 0 until the drain's first command reads the clock.
                long nextCommandStart = 0;

                using (PD.Measure(PD.Phase.RenderDrain))
                while (Volatile.Read(ref _commandCount) > 0 && Volatile.Read(ref _interruptAction) == null)
'''

LOOP_OLD = '''                    long commandStart = Stopwatch.GetTimestamp();
                    CommandHelper.RunCommand(command, this, _baseRenderer);
                    NoteRenderCommand(commandType, commandStart);

                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)
                    {
                        // RewindBox (adapt_sync_wait_attribution): the invoked command's own time, for its waiter.
                        Volatile.Write(ref _invokedOwnTicks, Stopwatch.GetTimestamp() - commandStart);
                        _invokeRun.Set();
                    }
'''
LOOP_NEW = '''                    // RewindBox (adapt_render_command_clock): one clock read per command; a command of the drain starts
                    // when the previous one's time ended.
                    long commandStart = nextCommandStart != 0 ? nextCommandStart : Stopwatch.GetTimestamp();
                    CommandHelper.RunCommand(command, this, _baseRenderer);
                    nextCommandStart = NoteRenderCommand(commandType, commandStart);

                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)
                    {
                        // RewindBox (adapt_sync_wait_attribution): the invoked command's own time, for its waiter.
                        Volatile.Write(ref _invokedOwnTicks, Stopwatch.GetTimestamp() - commandStart);
                        _invokeRun.Set();
                        nextCommandStart = 0; // RewindBox (adapt_render_command_clock): waking the waiter is no command's time
                    }
'''

PAIRS = ((NOTE_OLD, NOTE_NEW), (DRAIN_OLD, DRAIN_NEW), (LOOP_OLD, LOOP_NEW))


def apply(source):
    path = source / RENDERER
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, RENDERER
    # NoteRenderCommand has one caller (RenderLoop) and one window print.
    text = path.read_text(encoding='utf-8-sig')
    assert not digests or (text.count('NoteRenderCommand(') == 2 and text.count('LogRenderWork(end);') == 1), RENDERER
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
