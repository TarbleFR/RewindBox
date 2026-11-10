"""The GPU thread's synchronous waits on the render thread, attributed per invoked command (Core 699).

IPA 692 (Hogwarts Legacy, pid 36711, Core 693 performance windows): GPU.MainThread waited for the render thread in
InvokeCommand (syncInvoke) 107-2844 ms per 5 s window, often 300-600 ms, up to 1017 calls; the waits the existing
windows can name (counterReports 30-300 ms, texFlushAction 1-38 ms, bufFlush 3-795 ms, these partly overlapping)
leave most of it unexplained, and nothing tells whether a wait was the render thread draining the queue ahead of the
command or the command itself (a read-back). Eight commands are invoked synchronously (ActionCommand for the GPU
thread's BackgroundContextAction, BufferGetData, TextureGetData, TextureGetDataSlice, TryHostConditionalRendering,
ProgramCheckLink, ProgramGetBinary, GetCapabilities): the next fix depends on which one costs the time.

Change, observation only (no command, wait or order changes; no log line added): InvokeCommand notes the type of the
command it waits for, the wait from its queueing to the wake-up, and the time the render thread spent running that
command itself (written by the render thread before it wakes the waiter); the rest of the wait is the queue drained
ahead of it. Per type: calls, wait and own time, three atomic adds per synchronous call (about 1 000 per 5 s). The
existing "Render thread commands" line (LogRenderWork, every 5 s of render work) appends the window's totals and the six
types with the most waiting, then clears them.
Fail closed on drift: the file must be the Core 697 preparation's.
"""
import hashlib
from adapt_session import once

RENDERER = 'src/Ryujinx.Graphics.GAL/Multithreading/ThreadedRenderer.cs'
BASELINE = {
    RENDERER: '3b75889ca6452943e26ebfc5467f9edd2bb3592d2b07f66f837a9731ddf3aee8',
}

FIELDS_OLD = '''        private readonly long[] _renderWorkCalls = new long[256];
        private long _renderWorkStart;
'''
FIELDS_NEW = '''        private readonly long[] _renderWorkCalls = new long[256];
        private long _renderWorkStart;

        // RewindBox (adapt_sync_wait_attribution): the synchronous waits on the render thread (InvokeCommand) per invoked
        // command type over the same window: calls, the wait from queueing to wake-up, and the invoked command's own
        // render-thread time (the rest is the queue drained ahead of it). Added by the waiting thread, read and cleared by
        // LogRenderWork on the render thread.
        private readonly long[] _syncWaitCalls = new long[256];
        private readonly long[] _syncWaitTicks = new long[256];
        private readonly long[] _syncOwnTicks = new long[256];
        private readonly long[] _syncWindowCalls = new long[256];
        private readonly long[] _syncWindowTicks = new long[256];
        private readonly long[] _syncWindowOwn = new long[256];
        // Written by the render thread before it wakes the waiter, read by the waiter once woken.
        private long _invokedOwnTicks;

        private void NoteSyncWait(byte type, long waitStart)
        {
            long waited = Stopwatch.GetTimestamp() - waitStart;
            // Never throws (an observation must not stop the GPU thread): 0 <= own <= waited.
            long own = Math.Max(0, Math.Min(Volatile.Read(ref _invokedOwnTicks), waited));

            Interlocked.Increment(ref _syncWaitCalls[type]);
            Interlocked.Add(ref _syncWaitTicks[type], waited);
            Interlocked.Add(ref _syncOwnTicks[type], own);
        }

        private void AppendSyncWaits(System.Text.StringBuilder text)
        {
            long calls = 0;
            long ticks = 0;
            long own = 0;

            for (int i = 0; i < _syncWaitCalls.Length; i++)
            {
                _syncWindowCalls[i] = Interlocked.Exchange(ref _syncWaitCalls[i], 0);
                _syncWindowTicks[i] = Interlocked.Exchange(ref _syncWaitTicks[i], 0);
                _syncWindowOwn[i] = Interlocked.Exchange(ref _syncOwnTicks[i], 0);
                calls += _syncWindowCalls[i];
                ticks += _syncWindowTicks[i];
                own += _syncWindowOwn[i];
            }

            text.Append(" GPU thread sync waits ").Append(calls).Append(" calls ").Append(RenderMilliseconds(ticks))
                .Append(" ms (invoked commands themselves ").Append(RenderMilliseconds(own))
                .Append(" ms, the rest queued ahead); top (calls, ms, own ms):");

            for (int rank = 0; rank < 6; rank++)
            {
                int best = -1;

                for (int i = 0; i < _syncWindowTicks.Length; i++)
                {
                    if (_syncWindowTicks[i] > 0 && (best < 0 || _syncWindowTicks[i] > _syncWindowTicks[best]))
                    {
                        best = i;
                    }
                }

                if (best < 0)
                {
                    break;
                }

                text.Append(' ').Append(((CommandType)best).ToString()).Append(' ').Append(_syncWindowCalls[best]).Append(' ')
                    .Append(RenderMilliseconds(_syncWindowTicks[best])).Append(' ').Append(RenderMilliseconds(_syncWindowOwn[best]))
                    .Append(';');
                _syncWindowTicks[best] = 0;
            }
        }
'''

LOG_OLD = '''            Array.Clear(_renderWorkTicks);
            Array.Clear(_renderWorkCalls);
            _renderWorkStart = end;
'''
LOG_NEW = '''            // RewindBox (adapt_sync_wait_attribution): the same window's synchronous waits, on this line.
            AppendSyncWaits(text);
            Array.Clear(_renderWorkTicks);
            Array.Clear(_renderWorkCalls);
            _renderWorkStart = end;
'''

LOOP_OLD = '''                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)
                    {
                        _invokeRun.Set();
                    }
'''
LOOP_NEW = '''                    if (Interlocked.CompareExchange(ref _invokePtr, -1, commandPtr) == commandPtr)
                    {
                        // RewindBox (adapt_sync_wait_attribution): the invoked command's own time, for its waiter.
                        Volatile.Write(ref _invokedOwnTicks, Stopwatch.GetTimestamp() - commandStart);
                        _invokeRun.Set();
                    }
'''

INVOKE_OLD = '''        internal void InvokeCommand()
        {
            ThrowIfFailed();
            _invokeRun.Reset();
            _invokePtr = _lastProducedPtr;

            QueueCommand();

            // QueueCommand checks after Reset, so a previously published
            // failure cannot have its only wake-up erased by that Reset.
            ThrowIfFailed();
            using (PD.Measure(PD.Phase.SyncInvoke)) _invokeRun.Wait();
            ThrowIfFailed();
        }
'''
INVOKE_NEW = '''        internal void InvokeCommand()
        {
            ThrowIfFailed();
            _invokeRun.Reset();
            _invokePtr = _lastProducedPtr;
            // RewindBox (adapt_sync_wait_attribution): the type of the command waited for, and the wait from its queueing
            // (the render thread cannot start it before); no invoke is outstanding, so the render thread is not writing
            // the own time now.
            byte invokedType = _commandQueue[_lastProducedPtr * _elementSize + _elementSize - 1];
            Volatile.Write(ref _invokedOwnTicks, 0);
            long waitStart = Stopwatch.GetTimestamp();

            QueueCommand();

            // QueueCommand checks after Reset, so a previously published
            // failure cannot have its only wake-up erased by that Reset.
            ThrowIfFailed();
            using (PD.Measure(PD.Phase.SyncInvoke)) _invokeRun.Wait();
            ThrowIfFailed();
            NoteSyncWait(invokedType, waitStart);
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    renderer = paths[RENDERER]
    once(renderer, FIELDS_OLD, FIELDS_NEW)
    once(renderer, LOG_OLD, LOG_NEW)
    once(renderer, LOOP_OLD, LOOP_NEW)
    once(renderer, INVOKE_OLD, INVOKE_NEW)
    return list(paths.values())
