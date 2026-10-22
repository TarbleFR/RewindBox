using System;
using System.Runtime.InteropServices;
using Ryujinx.Common;

namespace Ryujinx.Library;

partial class Library
{
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_runtime_abi")]
    public static int EmbeddedRuntimeAbi() => 1;

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_configure_native")]
    public static int EmbeddedConfigureNative(nint rootUtf8)
    {
        try
        {
            EmbeddedNativeLibraries.Configure(Marshal.PtrToStringUTF8(rootUtf8));
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }

    // Configuration does not assert authorization. The host must first prove
    // its own PID's authenticated attach and executable dual mapping.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_configure_jit")]
    public static int EmbeddedConfigureJit(int universal)
    {
        try
        {
            lock (EmbeddedHostGate)
            {
                if (EmbeddedSessions.State != 0) return 2;
                EmbeddedNativeLibraries.ConfigureJit(universal);
                return 0;
            }
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
