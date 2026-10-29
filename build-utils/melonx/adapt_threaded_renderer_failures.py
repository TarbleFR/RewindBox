"""Return renderer failures to the session owner and wake abandoned GAL waits.

A command can fail after consuming only part of its reference slots. Never
execute more commands from that queue after a failure. Preserve the first
exception, unblock producer/external waits, and let the existing session owner
stop the guest before Dispose joins the GPU thread and releases the backend.
The normal command path gains volatile checks, not locks or allocations.
"""
import hashlib
from adapt_session import once


BASELINE = {
    'CommandHelper.cs': '50f4890a0081bb447f92fc9a03d5f244818ce73e9ab940655938ce385a21211c',
    'ThreadedRenderer.cs': '0bb45c762eb54dfeb6007c69088c6c766382af9c3fe1bc6cfc3ce05241772f75',
    'BufferMap.cs': 'd382e0f3150cc0383972d7439d4eff6ed1684ad3ea1143bd8284d6693b5dc9b2',
    'SyncMap.cs': '50463427144b27d437608f317b1b7f0d44415f623f51576b659264f979f1e0a7',
    'ThreadedHelpers.cs': 'f6770237d21fcad32d771a40604d6f2e71b8d5242683504fe0aa483e1b00f252',
    'Resources/ThreadedTexture.cs': 'f332c29af532288ce067faf6c056249b5335ffcd4c7dd6f418dfb3639677bc15',
    'Resources/ThreadedCounterEvent.cs': 'afa55bad7d89aac269d8bfdd3656a4aab6a2d6610a19cad7a514159d6354f286',
}


def apply(source):
    base = source / 'src/Ryujinx.Graphics.GAL/Multithreading'
    for name, expected in BASELINE.items():
        path = base / name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, str(path)
    dispatch = base / 'CommandHelper.cs'
    once(dispatch, '''            try 
            {
                _lookup[memory[^1]](memory, threaded, renderer);
            } 
            catch {}''', '''            // The renderer owns failure transport and shutdown. A command can
            // already have consumed reference slots when it throws; silently
            // resuming would corrupt that queue and expose an unset ResultBox.
            _lookup[memory[^1]](memory, threaded, renderer);''')
    renderer = base / 'ThreadedRenderer.cs'
    once(renderer, 'using System.Runtime.CompilerServices;',
         'using System.Runtime.CompilerServices;\nusing System.Runtime.ExceptionServices;')
    once(renderer, '        private bool _running;', '''        private bool _running;
        private ExceptionDispatchInfo _rendererFailure;
        private readonly ManualResetEvent _rendererFailed = new(false);
        private readonly ManualResetEventSlim _renderLoopExited = new(true);

        internal WaitHandle FailureWaitHandle => _rendererFailed;

        internal void ThrowIfFailed()
        {
            Volatile.Read(ref _rendererFailure)?.Throw();
        }

        private void RecordFailure(Exception exception)
        {
            if (Interlocked.CompareExchange(ref _rendererFailure,
                ExceptionDispatchInfo.Capture(exception), null) != null)
            {
                return;
            }

            // Publish the original error before waking any waiter. The manual
            // signal remains set for every buffer/sync waiter, including late ones.
            Volatile.Write(ref _running, false);
            _rendererFailed.Set();
            _invokeRun.Set();
            _frameComplete.Set();
            _interruptRun.Set();
            _galWorkAvailable.Set();
        }''')
    once(renderer, '            Buffers = new BufferMap();\n            Sync = new SyncMap();',
         '            Buffers = new BufferMap(this);\n            Sync = new SyncMap(this);')
    once(renderer, '''        public void RunLoop(ThreadStart gpuLoop)
        {
            _running = true;

            _backendThread = Thread.CurrentThread;

            _gpuThread = new Thread(gpuLoop)
            {
                Name = "GPU.MainThread",
            };

            _gpuThread.Start();

            RenderLoop();
        }''', '''        public void RunLoop(ThreadStart gpuLoop)
        {
            ThrowIfFailed();
            _running = true;
            _renderLoopExited.Reset();
            _backendThread = Thread.CurrentThread;

            _gpuThread = new Thread(() =>
            {
                try { gpuLoop(); }
                catch (Exception exception) { RecordFailure(exception); }
            })
            {
                Name = "GPU.MainThread",
            };

            try
            {
                _gpuThread.Start();
                RenderLoop();
            }
            catch (Exception exception)
            {
                RecordFailure(exception);
            }
            finally
            {
                _renderLoopExited.Set();
            }

            // Do not join here. The session owner must first wake a paused GPU
            // loop and stop the guest. Dispose joins after that existing handoff.
            ThrowIfFailed();
        }''')
    once(renderer, '            while (_running)\n', '            while (Volatile.Read(ref _running))\n')
    once(renderer, '                _galWorkAvailable.Reset();',
         '                _galWorkAvailable.Reset();\n                ThrowIfFailed();')
    once(renderer, '''                    // Run the command.

                    CommandHelper.RunCommand''', '''                    // A failed command may have consumed only some table refs.
                    // The queue cannot be resumed after either thread fails.
                    ThrowIfFailed();

                    CommandHelper.RunCommand''')
    once(renderer, '''        internal unsafe T* New<T>() where T : unmanaged, IGALCommand
        {
            while''', '''        internal unsafe T* New<T>() where T : unmanaged, IGALCommand
        {
            ThrowIfFailed();
            while''')
    once(renderer, '                Thread.Sleep(1);',
         '                ThrowIfFailed();\n                Thread.Sleep(1);')
    once(renderer, '''        internal void QueueCommand()
        {
            int result''', '''        internal void QueueCommand()
        {
            ThrowIfFailed();
            int result''')
    once(renderer, '''        internal void InvokeCommand()
        {
            _invokeRun.Reset();''', '''        internal void InvokeCommand()
        {
            ThrowIfFailed();
            _invokeRun.Reset();''')
    once(renderer, '''            // Wait for the command to complete.
            _invokeRun.Wait();''', '''            // QueueCommand checks after Reset, so a previously published
            // failure cannot have its only wake-up erased by that Reset.
            ThrowIfFailed();
            _invokeRun.Wait();
            ThrowIfFailed();''')
    once(renderer, '''        internal void WaitForFrame()
        {
            _frameComplete.WaitOne();
        }''', '''        internal void WaitForFrame()
        {
            ThrowIfFailed();
            _frameComplete.WaitOne();
            ThrowIfFailed();
        }''')
    once(renderer, '''        private void Interrupt(Action action)
        {
            // Interrupt''', '''        private void Interrupt(Action action)
        {
            ThrowIfFailed();
            // Interrupt''')
    once(renderer, '''                lock (_interruptLock)
                {
                    while''', '''                lock (_interruptLock)
                {
                    ThrowIfFailed();
                    while''')
    once(renderer, '''                    while (Interlocked.CompareExchange(ref _interruptAction, action, null) != null)
                    {
                    }''', '''                    while (Interlocked.CompareExchange(ref _interruptAction, action, null) != null)
                    {
                        ThrowIfFailed();
                    }''')
    once(renderer, '''                    _interruptRun.WaitOne();''', '''                    ThrowIfFailed();
                    _interruptRun.WaitOne();
                    ThrowIfFailed();''')
    once(renderer, '''        public void FlushThreadedCommands()
        {
            SpinWait wait = new();''', '''        public void FlushThreadedCommands()
        {
            ThrowIfFailed();
            SpinWait wait = new();''')
    once(renderer, '''            while (Volatile.Read(ref _commandCount) > 0)
            {
                wait.SpinOnce();
            }
        }''', '''            while (Volatile.Read(ref _commandCount) > 0)
            {
                ThrowIfFailed();
                wait.SpinOnce();
            }

            ThrowIfFailed();
        }''')
    once(renderer, '''            // Dispose the renderer.
            _baseRenderer.Dispose();''', '''            // The backend must also have left its event wait before events
            // are released. Normal close reaches here after the GPU drained.
            if (_backendThread != null && Thread.CurrentThread != _backendThread)
            {
                _renderLoopExited.Wait();
            }

            // Abandoned commands are never replayed. Only drop managed roots
            // after the producer can no longer publish reference slots.
            Array.Clear(_refQueue);

            // Dispose the renderer.
            _baseRenderer.Dispose();''')
    once(renderer, '''            Sync.Dispose();''', '''            Sync.Dispose();
            _rendererFailed.Dispose();
            if (Thread.CurrentThread != _backendThread)
            {
                _renderLoopExited.Dispose();
            }''')

    for filename, type_name, method in (
        ('BufferMap.cs', 'BufferMap', 'internal BufferHandle MapBufferBlocking(BufferHandle handle)'),
        ('SyncMap.cs', 'SyncMap', 'internal void WaitSyncAvailability(ulong id)'),
    ):
        path = base / filename
        once(path, '        private readonly AutoResetEvent _inFlightChanged = new(false);', f'''        private readonly AutoResetEvent _inFlightChanged = new(false);
        private readonly ThreadedRenderer _renderer;
        private readonly WaitHandle[] _waitHandles;

        internal {type_name}(ThreadedRenderer renderer)
        {{
            _renderer = renderer;
            _waitHandles = new[] {{ _inFlightChanged, renderer.FailureWaitHandle }};
        }}''')
        once(path, '        ' + method + '\n        {',
             '        ' + method + '\n        {\n            _renderer.ThrowIfFailed();')
        once(path, '''                _inFlightChanged.WaitOne();
                signal = true;''', '''                _renderer.ThrowIfFailed();
                WaitHandle.WaitAny(_waitHandles);
                _renderer.ThrowIfFailed();
                signal = true;''')
        once(path, '''            if (signal)
            {''', '''            _renderer.ThrowIfFailed();

            if (signal)
            {''')

    helpers = base / 'ThreadedHelpers.cs'
    once(helpers, 'public static void SpinUntilNonNull<T>(ref T obj) where T : class',
         'public static void SpinUntilNonNull<T>(ref T obj, ThreadedRenderer renderer) where T : class')
    once(helpers, 'public static void SpinUntilExchange(ref int target, int value, int comparand)',
         'public static void SpinUntilExchange(ref int target, int value, int comparand, ThreadedRenderer renderer)')
    text = helpers.read_text()
    anchor = '            Span<SpinWait> spinWait = stackalloc SpinWait[1];'
    assert text.count(anchor) == 2
    text = text.replace(anchor, '            renderer.ThrowIfFailed();\n' + anchor)
    anchor = '                spinWait[0].SpinOnce(-1);'
    assert text.count(anchor) == 2
    text = text.replace(anchor, '                renderer.ThrowIfFailed();\n' + anchor)
    helpers.write_text(text)
    texture = base / 'Resources/ThreadedTexture.cs'
    text = texture.read_text()
    for obj, count in (('Base', 3), ('dest.Base', 1)):
        anchor = f'ThreadedHelpers.SpinUntilNonNull(ref {obj});'
        assert text.count(anchor) == count, (obj, text.count(anchor))
        text = text.replace(anchor, f'ThreadedHelpers.SpinUntilNonNull(ref {obj}, _renderer);')
    texture.write_text(text)
    counter = base / 'Resources/ThreadedCounterEvent.cs'
    once(counter, 'ThreadedHelpers.SpinUntilNonNull(ref Base);',
         'ThreadedHelpers.SpinUntilNonNull(ref Base, _renderer);')
    text = counter.read_text()
    anchor = 'ThreadedHelpers.SpinUntilExchange(ref _createLock, 1, 0);'
    assert text.count(anchor) == 2
    counter.write_text(text.replace(anchor, 'ThreadedHelpers.SpinUntilExchange(ref _createLock, 1, 0, _renderer);'))
    return [base / name for name in BASELINE]
