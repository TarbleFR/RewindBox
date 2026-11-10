"""Release guest readiness waits after a failed or cancelled GPU initialization.

The terminal event is published only after an active shader-cache loader has
unwound. A pending initialization can be cancelled immediately. Guest threads
then exit through the kernel's existing Exit path without executing CPU code;
the original initialization exception still reaches the render/session owner.
The startup lock is used once per initialization/guest-thread start, never in
the frame loop. This follows the shader-loader worker-drain prerequisite.
"""
import hashlib
from adapt_session import once


BASELINE = {
    'src/Ryujinx.Graphics.Gpu/GpuContext.cs': '194ca019672e8e5fcc37bbb32db3cb2adc206a13cad70a5d6beef8aeed3c3dfc',
    'src/Ryujinx.HLE/HOS/ArmProcessContext.cs': 'a455fdf4f321c709accc58584dab97ac5b48b93d67762d39c07c579b57dd8204',
    'src/Ryujinx.Library/Window/WindowBase.cs': 'e749709340545e03dea3548f8c5cb59d3c8f85dfe1de29bbb8732d7fa0d43def',
}


def apply(source):
    for relative, expected in BASELINE.items():
        assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == expected, relative
    gpu, arm, window = [source / relative for relative in BASELINE]
    once(gpu, '        private readonly ManualResetEvent _gpuReadyEvent;', '''        private readonly ManualResetEvent _gpuReadyEvent;
        private readonly object _gpuInitializationLock = new();
        private readonly CancellationTokenSource _gpuInitializationCancellation = new();
        private GpuInitializationState _gpuInitializationState;
        private bool _gpuInitializationCancellationRequested;

        private enum GpuInitializationState
        {
            Pending,
            Initializing,
            Ready,
            Failed,
            Cancelled,
        }''')
    once(gpu, '''        public void InitializeShaderCache(CancellationToken cancellationToken)
        {
            HostInitalized.WaitOne();

            foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
            {
                physicalMemory.ShaderCache.Initialize(cancellationToken);
            }

            _gpuReadyEvent.Set();
        }''', '''        public bool InitializeShaderCache(CancellationToken cancellationToken)
        {
            lock (_gpuInitializationLock)
            {
                if (_gpuInitializationState == GpuInitializationState.Initializing)
                {
                    throw new InvalidOperationException("GPU initialization is already running.");
                }

                if (_gpuInitializationState != GpuInitializationState.Pending)
                {
                    return _gpuInitializationState == GpuInitializationState.Ready;
                }

                _gpuInitializationState = GpuInitializationState.Initializing;
            }

            GpuInitializationState outcome = GpuInitializationState.Failed;

            try
            {
                using CancellationTokenSource initializationCancellation = CancellationTokenSource.CreateLinkedTokenSource(
                    cancellationToken, _gpuInitializationCancellation.Token);
                CancellationToken token = initializationCancellation.Token;

                try
                {
                    token.ThrowIfCancellationRequested();
                    WaitHandle.WaitAny(new[] { HostInitalized, token.WaitHandle });
                    token.ThrowIfCancellationRequested();

                    foreach (PhysicalMemory physicalMemory in PhysicalMemoryRegistry.Values)
                    {
                        token.ThrowIfCancellationRequested();
                        physicalMemory.ShaderCache.Initialize(token);
                    }

                    token.ThrowIfCancellationRequested();
                    outcome = GpuInitializationState.Ready;
                }
                catch (OperationCanceledException) when (token.IsCancellationRequested)
                {
                    outcome = GpuInitializationState.Cancelled;
                }
            }
            finally
            {
                // The loader has returned and joined its workers before guest
                // threads can unregister memory or the owner can dispose caches.
                lock (_gpuInitializationLock)
                {
                    if (outcome == GpuInitializationState.Ready &&
                        (_gpuInitializationCancellationRequested || cancellationToken.IsCancellationRequested))
                    {
                        outcome = GpuInitializationState.Cancelled;
                    }

                    _gpuInitializationState = outcome;
                    _gpuReadyEvent.Set();
                }
            }

            return outcome == GpuInitializationState.Ready;
        }

        public void CancelShaderCacheInitialization()
        {
            lock (_gpuInitializationLock)
            {
                _gpuInitializationCancellationRequested = true;

                if (_gpuInitializationState == GpuInitializationState.Pending)
                {
                    _gpuInitializationState = GpuInitializationState.Cancelled;
                    _gpuReadyEvent.Set();
                }
            }

            // Never run cancellation callbacks under the state lock. An active
            // initializer publishes its terminal event only after it unwinds.
            _gpuInitializationCancellation.Cancel();
        }''')
    once(gpu, '''        public void WaitUntilGpuReady()
        {
            _gpuReadyEvent.WaitOne();
        }''', '''        public bool WaitUntilGpuReady()
        {
            _gpuReadyEvent.WaitOne();

            lock (_gpuInitializationLock)
            {
                return _gpuInitializationState == GpuInitializationState.Ready;
            }
        }''')
    once(gpu, '''            HostInitalized.Dispose();
            _gpuReadyEvent.Dispose();''', '''            HostInitalized.Dispose();
            _gpuReadyEvent.Dispose();
            _gpuInitializationCancellation.Dispose();''')

    once(arm, 'using Ryujinx.HLE.HOS.Kernel.Process;',
         'using Ryujinx.HLE.HOS.Kernel;\nusing Ryujinx.HLE.HOS.Kernel.Process;')
    once(arm, '''            _gpuContext.WaitUntilGpuReady();
            _cpuContext.Execute(context, codeAddress);''', '''            if (!_gpuContext.WaitUntilGpuReady())
            {
                // A host-thread return alone does not signal kernel termination.
                // Exit marks this thread terminated and stops its CPU context.
                KernelStatic.GetCurrentThread().Exit();
                return;
            }

            _cpuContext.Execute(context, codeAddress);''')

    once(window, '''                Device.Gpu.InitializeShaderCache(_gpuCancellationTokenSource.Token);

                while (_embeddedLifetime.RenderAllowed)''', '''                bool gpuReady = Device.Gpu.InitializeShaderCache(_gpuCancellationTokenSource.Token);

                while (gpuReady && _embeddedLifetime.RenderAllowed)''')
    once(window, '''                Library.WithdrawEmbeddedControls();
                _gpuCancellationTokenSource.Cancel();
                Device.System.Dispose();''', '''                Library.WithdrawEmbeddedControls();
                // Also covers renderer setup failing before shader-cache entry.
                Device.Gpu.CancelShaderCacheInitialization();
                _gpuCancellationTokenSource.Cancel();
                Device.System.Dispose();''')
    return [gpu, arm, window]
