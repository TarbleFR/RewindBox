"""Audited lifecycle edits against the pinned upstream; fail closed on drift."""
from pathlib import Path


def once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, (str(path), old[:90], text.count(old))
    path.write_text(text.replace(old, new), encoding='utf-8')


def section(path, start, end, replacement):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(start) == text.count(end) == 1, str(path)
    left = text.index(start)
    right = text.index(end, left + len(start))
    path.write_text(text[:left] + replacement + '\n\n' + text[right:], encoding='utf-8')


def apply(source):
    library = source / 'src/Ryujinx.Library/Library.cs'
    window = source / 'src/Ryujinx.Library/Window/WindowBase.cs'
    # A signal-only legacy boundary too: it must not bypass the session owner.
    section(library, '        public static void StopEmulation()\n',
            '        public static nint GetNativeMetalLayer()', '''        public static void StopEmulation()
        {
            _window?.Exit();
        }''')
    # Horizon is initialized by the once-only bootstrap. Replacing it each game
    # leaks the preceding FS/ARP/BCAT servers and their clients.
    once(library, '''        static void Load(Options option)
        {
            _libHacHorizonManager = new LibHacHorizonManager();
            _libHacHorizonManager.InitializeFsServer(_virtualFileSystem);
            _libHacHorizonManager.InitializeArpServer();
            _libHacHorizonManager.InitializeBcatServer();
            _libHacHorizonManager.InitializeSystemClients();''', '''        static void Load(Options option)
        {''')
    section(library, '            AppDomain.CurrentDomain.UnhandledException +=',
            '            if (OperatingSystem.IsMacOS() || OperatingSystem.IsIOS())', '')
    once(library, '                LoadApplication(option);', '''                if (EmbeddedSessions.IsStopping) break;
                if (!LoadApplication(option))
                    throw new InvalidOperationException("The engine could not load this game.");
                if (EmbeddedSessions.IsStopping) break;''')
    once(library, '            WindowBase window = CreateWindow(options);', '''            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("gpu", "begin", detail: "Resolving Vulkan for the native window.");
            WindowBase window = CreateWindow(options);''')
    once(library, '            IRenderer renderer = CreateRenderer(options, window);', '''            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("gpu", "begin", detail: "Creating the private MoltenVK renderer and CAMetalLayer surface.");
            IRenderer renderer = CreateRenderer(options, window);''')
    # Input drivers are process-owned. Npad/touch managers are window-owned.
    # Keep drivers alive, but discard per-game bindings to disconnected pads.
    once(library, '            _inputManager.Dispose();', '''            lock (inputConfigurationLock) _inputConfiguration.Clear();''')
    section(library, '        private static void ExecutionEntrypoint()',
            '        private static bool LoadApplication(Options options)', '''        private static void ExecutionEntrypoint()
        {
            try
            {
                if (OperatingSystem.IsWindows())
                    _windowsMultimediaTimerResolution = new WindowsMultimediaTimerResolution(1);
                DisplaySleep.Prevent();
                lock (inputConfigurationLock)
                    _window.Initialize(_emulationContext, _inputConfiguration, _enableKeyboard, _enableMouse);
                EmbeddedSessions.PublishControls(_window.Exit, paused =>
                {
                    _emulationContext.System.TogglePauseEmulation(paused);
                    _window.SetEmbeddedPaused(paused);
                });
                _window.Execute();
            }
            finally
            {
                EmbeddedSessions.WithdrawControls();
                DisplaySleep.Restore();
                _windowsMultimediaTimerResolution?.Dispose();
                _windowsMultimediaTimerResolution = null;
            }
        }

        private static bool LoadApplication(Options options)
        {
            try { return LoadApplicationOwned(options); }
            catch (Exception error)
            {
                // Capture the original loader failure before cleanup. A stuck
                // teardown must not hide the reason the game failed to load.
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Fail(
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Stage,
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Classify(error), error, 3);
                throw;
            }
            finally
            {
                EmbeddedSessions.WithdrawControls();
                var context = _emulationContext;
                var window = _window;
                // Failed guest termination leaves unknown live CPU users.
                // Keep every remaining handle rooted until process exit.
                if (window?.EmbeddedExecutionFailed == true)
                    throw new InvalidOperationException("Session termination is unproven; restart NeoStation.");
                context?.Dispose();
                // Execute releases GPU resources on the render worker.
                // A failure before Execute has no render worker yet.
                if (context != null && window?.EmbeddedGpuReleased != true) context.DisposeGpu();
                window?.Dispose();
                // Clear references only after all ownership was retired. If
                // any cleanup fails, the quarantined engine retains them.
                _emulationContext = null;
                _window = null;
            }
        }''')
    # The section above ends at the original signature, now rename just that one.
    once(library, '''        private static bool LoadApplication(Options options)
        {
            string path''', '''        private static bool LoadApplicationOwned(Options options)
        {
            string path''')
    once(library, '''            IRenderer renderer = CreateRenderer(options, window);

            _window = window;''', '''            _window = window;
            IRenderer renderer = CreateRenderer(options, window);''')
    once(library, '            _emulationContext = InitializeEmulationContext(window, renderer, options);', '''            try { _emulationContext = InitializeEmulationContext(window, renderer, options); }
            catch { renderer.Dispose(); throw; }''')
    once(library, '            bool isFirmwareTitle = false;', '''            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("sessionServices", "passed", detail: "User profile, Horizon services and guest memory initialized.");
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("content", "begin");
            bool isFirmwareTitle = false;''')
    once(library, '            SetupProgressHandler();', '''            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("content", "passed", detail: "Native loader accepted the game and started its guest process.");
            SetupProgressHandler();''')
    # A failed encrypted NSP must not fall through into the plain ExeFS loader:
    # that second failure hides the original CNMT/NCA/key error. Genuine ExeFS
    # containers have no CNMT and retain their existing successful fallback.
    loader = source / 'src/Ryujinx.HLE/Loaders/Processes/ProcessLoader.cs'
    once(loader, '''            if (processResult.ProcessId == 0)
            {''', '''            if (!success && !string.IsNullOrEmpty(errorMessage) &&
                !partitionFileSystem.FileExists("/main.npdm"))
                throw new InvalidDataException(errorMessage);

            if (processResult.ProcessId == 0)
            {''')
    helper = source / 'src/Ryujinx.HLE/Loaders/Processes/ProcessLoaderHelper.cs'
    once(helper, '            context.Device.System.ServiceTable.WaitServicesReady();', '''            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("systemServices", "begin", detail: "Waiting for Horizon service readiness before creating the guest process.");
            context.Device.System.ServiceTable.WaitServicesReady();
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("systemServices", "passed", detail: "All Horizon service readiness acknowledgements received.");''')
    text = library.read_text()
    assert text.count('_emulationContext.Dispose();') == 9
    library.write_text(text.replace('_emulationContext.Dispose();', '/* Session owner releases the context. */'))

    once(window, '        private bool _isStopped;', '''        private readonly EmbeddedWindowLifetime _embeddedLifetime = new();
        private readonly object _embeddedInputGate = new();
        private bool _embeddedInputDisposed;
        internal bool EmbeddedGpuReleased { get; private set; }
        internal bool EmbeddedGuestStopFailed => _embeddedLifetime.GuestStopFailed;
        internal bool EmbeddedExecutionFailed { get; private set; }
        internal void SetEmbeddedPaused(bool paused) => _embeddedLifetime.SetPaused(paused);''')
    once(window, '''            _inputUpdatedEvent.Set();
        }

        public void Initialize''', '''            lock (_embeddedInputGate)
                if (!_embeddedInputDisposed) _inputUpdatedEvent.Set();
        }

        public void Initialize''')
    once(window, '                while (_isActive)', '                while (_embeddedLifetime.RenderAllowed)')
    once(window, '            Device.Gpu.Renderer.Initialize(_glLogLevel);', '''            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("gpu", "begin", detail: "Initializing the real GPU renderer.");
            Device.Gpu.Renderer.Initialize(_glLogLevel);
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("gpu", "passed", detail: "Native GPU renderer initialized; Metal presentation remains unconfirmed.");''')
    syscall = source / 'src/Ryujinx.HLE/HOS/Kernel/SupervisorCall/Syscall.cs'
    once(syscall, '''        public void ExitProcess()
        {''', '''        public void ExitProcess()
        {
            Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("guestExecution", "passed", detail: "A guest ARM64 thread executed SVC ExitProcess.");''')
    once(window, '''                    if (_isStopped)
                    {
                        return;
                    }

                    _pauseEvent.WaitOne();''', '''                    _embeddedLifetime.WaitUntilResumed();
                    if (!_embeddedLifetime.RenderAllowed) break;''')
    once(window, '''                _gpuDoneEvent.Set();
            });

            FinalizeWindowRenderer();''', '''            });''')
    section(window, '        public void Exit()\n', '        public static void ProcessMainThreadQueue()', '''        public void Exit()
        {
            _embeddedLifetime.RequestStop();
        }''')
    once(window, '            while (_isActive)', '            while (_embeddedLifetime.InputAllowed)')
    section(window, '''            if (!_isActive)
''', '            NpadManager.Update();', '''            if (!_embeddedLifetime.InputAllowed) return false;
''')
    section(window, '        public void Execute()\n', '        public bool DisplayInputDialog(', '''        public void Execute()
        {
            _chrono.Restart();
            InitializeWindow();
            try { _embeddedLifetime.Run(MainLoop, Render, () =>
            {
                Library.WithdrawEmbeddedControls();
                _gpuCancellationTokenSource.Cancel();
                Device.System.Dispose();
            }, () =>
            {
                // Exactly one attempt. A failure quarantines the session;
                // never retry native GPU destruction on another thread.
                EmbeddedGpuReleased = true;
                try { Device.DisposeGpu(); }
                finally { FinalizeWindowRenderer(); }
            }); }
            catch { EmbeddedExecutionFailed = true; throw; }
        }''')
    section(window, '        protected virtual void Dispose(bool disposing)',
            '        internal sealed class StatisticsRequest', '''        protected virtual void Dispose(bool disposing)
        {
            if (!disposing) return;
            _embeddedLifetime.Dispose(() =>
            {
                NativeGamepadDriver.OnInputUpdated -= SignalInputUpdated;
                try { TouchScreenManager?.Dispose(); }
                finally
                {
                    try { NpadManager?.Dispose(); }
                    finally
                    {
                        _gpuCancellationTokenSource.Dispose();
                        _pauseEvent.Dispose();
                        _exitEvent.Dispose();
                        _gpuDoneEvent.Dispose();
                        lock (_embeddedInputGate)
                        {
                            _embeddedInputDisposed = true;
                            _inputUpdatedEvent.Dispose();
                        }
                    }
                }
            });
        }''')
    # UIKit sends touches concurrently with the input worker's snapshots.
    touch = source / 'src/Ryujinx.Library/Native/NativeTouchDriver.cs'
    once(touch, 'private static Dictionary<int, Vector2> _activeTouches = new();',
         'private static System.Collections.Concurrent.ConcurrentDictionary<int, Vector2> _activeTouches = new();')
    once(touch, '_activeTouches.Remove(index);', '_activeTouches.TryRemove(index, out _);')
    once(touch, '        public void UpdatePosition()', '''        internal static void ResetEmbeddedTouches() => _activeTouches.Clear();

        public void UpdatePosition()''')
    return [library, window, touch, loader, syscall, helper]
