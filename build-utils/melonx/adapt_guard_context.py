"""Append bounded existing guest-dispatch context to fatal page-table guards.

The native signal callback supplies a one-byte hint, not instruction width.
DispatchAddress already exists and may describe a previous called block when
its caller resumes; it is deliberately not advertised as the faulting PC.
No signal ABI, mapping, retry policy or successful execution path changes.
"""
from adapt_session import once


def apply(source):
    interface = source / 'src/Ryujinx.Cpu/LightningJit/NativeInterface.cs'
    once(interface, '        public static void RegisterThread(ExecutionContext context, IMemoryManager memory, Translator translator)', '''        internal static string DescribeLastGuestDispatch()
        {
            // This is read only on an already fatal guard path. Existing thread
            // registration and dispatch stores supply all state; do not add a
            // per-instruction/per-dispatch trace or read guest memory here.
            try
            {
                ThreadContext thread = Context;
                if (thread == null)
                {
                    return "sizeIsSignalHint=True; guestContext=unavailable; faultPcKnown=False";
                }

                ExecutionContext execution = thread.Context;
                return $"sizeIsSignalHint=True; guestContext=present; guestThread={execution.ThreadUid}; lastGuestDispatch=0x{execution.Pc:X}; faultPcKnown=False";
            }
            catch
            {
                // Diagnostics must preserve the original invalid-memory error.
                return "sizeIsSignalHint=True; guestContext=unavailable; faultPcKnown=False";
            }
        }

        public static void RegisterThread(ExecutionContext context, IMemoryManager memory, Translator translator)''')
    guard = source / 'src/Ryujinx.Cpu/Jit/HostTracked/NativePageTable.cs'
    once(guard,
         'throw new InvalidMemoryRegionException($"Native page-table guard: relativeOffset=0x{address:X}; size={size}; write={write}; tableBytes=0x{_nativePageTable.Size - _hostPageSize:X}.");',
         'throw new InvalidMemoryRegionException($"Native page-table guard: relativeOffset=0x{address:X}; size={size}; write={write}; tableBytes=0x{_nativePageTable.Size - _hostPageSize:X}; {LightningJit.NativeInterface.DescribeLastGuestDispatch()}.");')
    return [interface, guard]
