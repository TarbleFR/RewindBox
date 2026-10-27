"""TEMPORARY: show where FINAL FANTASY TACTICS - The Ivalice Chronicles freezes.

Remove this adaptation (and its prepare_embedded.py lines) once the freeze is
understood. It only acts for program 010038b015560000.

Build 572 app.log (27 October 2026): three launches of the game froze 0.4 s
after start, right after ServiceAm SetOperationModeChangedNotification. Every
guest thread then waited (WaitProcessWideKeyAtomic, WaitSynchronization), at
4 % CPU, with no frame and no audio, until the player closed it. The log does
not say what they waited for: implemented service calls are only traced at
Trace level, which RewindBox does not enable.

- ProcessResult.Start: before the game's process starts, a budget of 300
  service calls is set for this program only (0 for any other).
- IpcService.LogInvoke (HLE services) and ServiceDispatchTableBase (Horizon
  services): while budget remains, each call is printed at Info level
  ("Boot trace: Service: Command"), the order they reach the services in.
- Horizon.Dispose: before the processes are terminated, the existing
  HleProcessDebugger.GetMinidump() of this program is printed: its modules and,
  for each guest thread, its stack (with SDK symbols) and registers.

Bounded: 300 lines, and one dump per session. RewindBox's stderr capture keeps
500 distinct NSLog lines and 2000 other lines per session; repeated lines are
counted, not copied. No behaviour of the engine changes. Fail closed on drift.
"""
from adapt_session import once


def apply(source):
    logger = source / 'src/Ryujinx.Common/Logging/Logger.cs'
    once(logger, '''        public static event EventHandler<LogEventArgs> Updated;
''', '''        public static event EventHandler<LogEventArgs> Updated;

        // TEMPORARY (adapt_fft_boot_trace.py): service calls still to print.
        public static int ServiceCallTraceBudget;

        public static void TraceServiceCall(string call)
        {
            if (Interlocked.Decrement(ref ServiceCallTraceBudget) >= 0)
            {
                Info?.Print(LogClass.KernelIpc, "Boot trace: " + call);
            }
        }
''')
    ipc = source / 'src/Ryujinx.HLE/HOS/Services/IpcService.cs'
    once(ipc, '''        protected void LogInvoke(string name)
            => Logger.Trace?.Print(LogClass.KernelIpc, $"{this.GetType().Name}: {name}");''', '''        protected void LogInvoke(string name)
        {
            Logger.Trace?.Print(LogClass.KernelIpc, $"{this.GetType().Name}: {name}");

            if (System.Threading.Volatile.Read(ref Logger.ServiceCallTraceBudget) > 0)
            {
                Logger.TraceServiceCall($"{GetType().Name}: {name}");
            }
        }''')
    dispatch = source / 'src/Ryujinx.Horizon/Sdk/Sf/Cmif/ServiceDispatchTableBase.cs'
    once(dispatch, '''            Logger.Trace?.Print(LogClass.KernelIpc, $"{objectName}.{commandHandler.MethodName} called");
''', '''            Logger.Trace?.Print(LogClass.KernelIpc, $"{objectName}.{commandHandler.MethodName} called");

            if (System.Threading.Volatile.Read(ref Logger.ServiceCallTraceBudget) > 0)
            {
                Logger.TraceServiceCall($"{objectName}.{commandHandler.MethodName}");
            }
''')
    loader = source / 'src/Ryujinx.HLE/Loaders/Processes/ProcessResult.cs'
    once(loader, '''            Result result = device.System.KernelContext.Processes[ProcessId].Start(_mainThreadPriority, _mainThreadStackSize);
''', '''            // TEMPORARY (adapt_fft_boot_trace.py): FINAL FANTASY TACTICS - The Ivalice Chronicles.
            System.Threading.Volatile.Write(ref Logger.ServiceCallTraceBudget, ProgramId == 0x010038B015560000UL ? 300 : 0);

            Result result = device.System.KernelContext.Processes[ProcessId].Start(_mainThreadPriority, _mainThreadStackSize);
''')
    horizon = source / 'src/Ryujinx.HLE/HOS/Horizon.cs'
    once(horizon, '''                KProcess terminationProcess = new(KernelContext);
''', '''                // TEMPORARY (adapt_fft_boot_trace.py): where each thread waits.
                KProcess traced = DebugGetApplicationProcess();

                if (traced?.TitleId == 0x010038B015560000UL)
                {
                    try
                    {
                        Ryujinx.Common.Logging.Logger.Info?.Print(Ryujinx.Common.Logging.LogClass.Application,
                            "Boot trace minidump:\\n" + traced.Debugger.GetMinidump());
                    }
                    catch (Exception e)
                    {
                        Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Application,
                            $"Boot trace minidump failed: {e.Message}");
                    }
                }

                KProcess terminationProcess = new(KernelContext);
''')
    return [logger, ipc, dispatch, loader, horizon]
