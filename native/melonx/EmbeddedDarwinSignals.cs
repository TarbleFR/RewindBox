using System;
using System.Runtime.InteropServices;

namespace Ryujinx.Cpu.Signal;

// Darwin's public sigaction ABI is not the Linux ABI. These methods run only
// during registration/restoration; the fault path remains generated native code.
static partial class UnixSignalHandlerRegistration
{
    [StructLayout(LayoutKind.Sequential)]
    internal struct DarwinSigAction
    {
        public nint Handler;
        public uint Mask;
        public int Flags;
    }

    internal static bool IsDarwin => OperatingSystem.IsMacOS() || OperatingSystem.IsIOS();
    internal static int SigInfoFlag => IsDarwin ? 0x40 : 4;
    private static DarwinSigAction PreviousDarwinBus;
    private static bool DarwinInstalled;

    [LibraryImport("/usr/lib/libSystem.B.dylib", EntryPoint = "sigaction", SetLastError = true)]
    private static partial int QueryDarwin(int signal, nint action, out DarwinSigAction previous);

    [LibraryImport("/usr/lib/libSystem.B.dylib", EntryPoint = "sigaction", SetLastError = true)]
    private static partial int InstallDarwin(int signal, ref DarwinSigAction action, out DarwinSigAction previous);

    private static unsafe SigAction Logical(DarwinSigAction value)
    {
        SigAction result = new() { sa_handler = value.Handler, sa_flags = value.Flags };
        *(uint*)&result.sa_mask = value.Mask;
        return result;
    }

    private static unsafe DarwinSigAction Darwin(SigAction value) => new()
    {
        Handler = value.sa_handler, Mask = *(uint*)&value.sa_mask, Flags = value.sa_flags,
    };

    internal static SigAction GetBusExceptionHandler() => IsDarwin ? GetDarwin(SIGBUS) : default;

    private static SigAction GetDarwin(int signal)
    {
        if (QueryDarwin(signal, 0, out var previous) != 0)
            throw new InvalidOperationException("Cannot read Darwin sigaction: " + Marshal.GetLastPInvokeError());
        return Logical(previous);
    }

    private static SigAction RegisterDarwin(nint handler)
    {
        var oldSegv = Darwin(GetDarwin(SIGSEGV));
        var oldBus = Darwin(GetDarwin(SIGBUS));
        // Preserve each signal's mask, alternate-stack and restart behavior.
        // SA_RESETHAND must not remove the process-owned tracking handler.
        var segv = new DarwinSigAction { Handler = handler, Mask = oldSegv.Mask,
            Flags = 0x40 | (oldSegv.Flags & 0x13) };
        var bus = new DarwinSigAction { Handler = handler, Mask = oldBus.Mask,
            Flags = 0x40 | (oldBus.Flags & 0x13) };
        if (InstallDarwin(SIGSEGV, ref segv, out oldSegv) != 0)
            throw new InvalidOperationException("Cannot install Darwin SIGSEGV handler: " + Marshal.GetLastPInvokeError());
        if (InstallDarwin(SIGBUS, ref bus, out oldBus) != 0)
        {
            int error = Marshal.GetLastPInvokeError();
            _ = InstallDarwin(SIGSEGV, ref oldSegv, out _);
            throw new InvalidOperationException("Cannot install Darwin SIGBUS handler: " + error);
        }
        PreviousDarwinBus = oldBus;
        DarwinInstalled = true;
        return Logical(oldSegv);
    }

    private static bool RestoreDarwin(SigAction previous)
    {
        var segv = Darwin(previous);
        bool restored = InstallDarwin(SIGSEGV, ref segv, out _) == 0;
        if (DarwinInstalled) restored &= InstallDarwin(SIGBUS, ref PreviousDarwinBus, out _) == 0;
        return restored;
    }
}
