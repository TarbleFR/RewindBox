using System;
using System.Runtime.InteropServices;
using Ryujinx.Common;
using Ryujinx.Common.Logging;

namespace Ryujinx.Library;

partial class Library
{
    private static bool EmbeddedLogSubscribed;
    private static bool EmbeddedJitQuarantined;

    private static void EmbeddedSubscribeDiagnostics()
    {
        if (EmbeddedLogSubscribed) return;
        EmbeddedLogSubscribed = true;
        Logger.Updated += (_, entry) =>
        {
            if (entry.Level == LogLevel.Error || entry.Level == LogLevel.Warning)
                EmbeddedLaunchDiagnostics.RecordEngine(entry.Level == LogLevel.Error, entry.Message);
        };
        // adapt_session removes Library's per-game handler, which only queued
        // an Info line the dying process never wrote. Once per process.
        AppDomain.CurrentDomain.UnhandledException += (_, e) => EmbeddedLaunchDiagnostics.RecordCrash(e.ExceptionObject);
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_diagnostics_abi")]
    public static int EmbeddedDiagnosticsAbi() => 1;

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_diagnostics")]
    public static unsafe int EmbeddedDiagnostics(byte* output, int capacity)
    {
        try
        {
            byte[] data = EmbeddedLaunchDiagnostics.Snapshot();
            if (output == null || capacity <= data.Length) return -data.Length;
            data.CopyTo(new Span<byte>(output, capacity)); output[data.Length] = 0;
            return 0;
        }
        catch { return -1; }
    }

    // Code arena bytes the last launch preflight asks for; 0 keeps the default
    // (512 MiB under TXM). The helper maps the arena once per process.
    private static ulong EmbeddedJitArenaHint;

    // Hogwarts Legacy with its update filled the 512 MiB TXM arena 25-32 s
    // after every launch (Builds 564-575); the base game ran 727 s in it. The
    // helper writes every arena page, so the larger arena stays specific.
    private static ulong EmbeddedJitArenaFor(ulong titleId, LibHac.Tools.FsSystem.NcaUtils.Nca program)
    {
        if (titleId != 0x0100F7E00C70E000UL) return 0;
        try
        {
            (var patch, _) = Ryujinx.HLE.Loaders.Processes.Extensions.NcaExtensions.GetUpdateData(program,
                _virtualFileSystem, LibHac.Tools.FsSystem.IntegrityCheckLevel.None, 0, out _);
            return patch != null ? 1UL << 30 : 0;
        }
        catch { return 0; }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_prepare_jit")]
    public static int EmbeddedPrepareJit()
    {
        lock (EmbeddedHostGate)
        {
            if (!EmbeddedBootstrap.Ready || EmbeddedSessions.State != 0) return 2;
            if (EmbeddedJitQuarantined) return 3;
            EmbeddedLaunchDiagnostics.Record("jitArena", "begin");
            try
            {
                Ryujinx.Cpu.LightningJit.DualMappedMemory.RequestedArenaSize = EmbeddedJitArenaHint;
                Ryujinx.Cpu.LightningJit.DualMappedMemory.PrepareEmbeddedMapping();
                EmbeddedLaunchDiagnostics.Record("jitArena", "passed", detail: "Real MeloNX code arena (" +
                    (Ryujinx.Cpu.LightningJit.DualMappedMemory.ArenaSize >> 20) + " MiB) and signal mapping prepared; ARM64 probe executed through the arena's RX/RW aliases.");
                return 0;
            }
            catch (Exception error)
            {
                EmbeddedJitQuarantined = true;
                EmbeddedLaunchDiagnostics.Fail("jitArena", "jitRestartRequired", error);
                return 1;
            }
        }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_runtime_abi")]
    public static int EmbeddedRuntimeAbi() => 1;

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_configure_native")]
    public static int EmbeddedConfigureNative(nint rootUtf8)
    {
        try
        {
            EmbeddedSubscribeDiagnostics();
            EmbeddedLaunchDiagnostics.Record("frameworks", "begin");
            EmbeddedNativeLibraries.Configure(Marshal.PtrToStringUTF8(rootUtf8));
            EmbeddedLaunchDiagnostics.Record("frameworks", "passed", detail: "MoltenVK: " + EmbeddedNativeLibraries.MoltenVk);
            return 0;
        }
        catch (Exception error) { EmbeddedLaunchDiagnostics.Fail("frameworks", "runtimeUnavailable", error); return 1; }
    }

    // Before configure_native only: 0 = RewindBox's source-built MoltenVK,
    // 1 = the standalone MeloNX app's binary. Fixed for the process once loaded.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_select_moltenvk")]
    public static int EmbeddedSelectMoltenVk(int variant)
    {
        try { EmbeddedNativeLibraries.SelectMoltenVk(variant); return 0; }
        catch (ArgumentOutOfRangeException) { return 1; }
        catch (Exception error) { EmbeddedLaunchDiagnostics.Fail("frameworks", "moltenVkFixed", error); return 2; }
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
        catch (Exception error) { EmbeddedLaunchDiagnostics.Fail("jitMode", "jitRestartRequired", error); return 1; }
    }
}
