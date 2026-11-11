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
        // RewindBox (adapt_guest_fault_context): after the crash line, a guest memory fault on a guest thread adds the
        // thread's name, control registers and guest stack (at most 250 ms and 3600 characters; nothing otherwise).
        AppDomain.CurrentDomain.UnhandledException += (_, e) =>
        {
            string guest = Ryujinx.HLE.HOS.Kernel.GuestFaultContext.Describe(e.ExceptionObject, 250);
            if (guest != null) EmbeddedLaunchDiagnostics.RecordCrash(guest);
        };
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_diagnostics_abi")]
    public static int EmbeddedDiagnosticsAbi() => 1;

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_diagnostics")]
    public static unsafe int EmbeddedDiagnostics(byte* output, int capacity)
    {
        // Copied from the bytes the journal keeps while nothing changes (EmbeddedLaunchDiagnostics.SnapshotTo): the
        // host polls this every 300 ms, and the managed copy made here was an allocation of the snapshot's size each time.
        try { return EmbeddedLaunchDiagnostics.SnapshotTo(output, capacity); }
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

    // The helper maps the code arena once per process, at the size the first launch asks for. Hogwarts Legacy with its
    // update, launched after another game, filled that game's 512 MiB arena 16 s after its start and the process
    // aborted ("JIT Cache exhausted", IPA 666; also builds 658 and 662 in that order, never with Hogwarts first). The
    // first launch therefore maps the largest arena a title needs wherever the process may use 6 GiB or more (the
    // helper writes every arena page: 512 MiB more footprint there). Once an arena is mapped its size is final: a title
    // that needs more is refused before it starts (false), never left to exhaust the arena in play.
    internal const ulong EmbeddedLargestJitArena = 1UL << 30;
    internal const ulong EmbeddedLargeArenaProcessBytes = 6UL << 30;

    internal static bool EmbeddedJitArenaRequest(ulong titleHint, ulong mappedBytes, ulong processBytes, out ulong request)
    {
        request = titleHint;
        if (mappedBytes != 0) return titleHint <= mappedBytes;
        if (titleHint < EmbeddedLargestJitArena && processBytes >= EmbeddedLargeArenaProcessBytes) request = EmbeddedLargestJitArena;
        return true;
    }

    // Titles whose shaders Metal compiles without fast math (adapt_hogwarts_precise_math); the preflight resets the choice
    // for each launch. Empty since Core 670: Core 667 listed Hogwarts Legacy (sky blocks, a NaN/Inf hypothesis), and on IPA
    // 669 its launch never reached the first frame in 230 s. MoltenVK 1.4.2 compiles every shader library of the pipeline
    // cache when it reads it (MVKPipelineCache::readData -> MVKShaderLibrary::compileLibrary), and Metal's compiled-library
    // cache held only the fast-math variants, so the whole 203 MiB cache was compiled again before the first frame
    // (0.6 s on IPA 666). A title may be listed again only with that cost measured.
    private static readonly ulong[] EmbeddedPreciseMathTitles = Array.Empty<ulong>();

    private static void EmbeddedNoteLaunchTitle(ulong titleId)
    {
        if (OperatingSystem.IsIOS() || OperatingSystem.IsMacOS())
            Ryujinx.Graphics.Vulkan.MoltenVK.MVKInitialization.PreciseMath = Array.IndexOf(EmbeddedPreciseMathTitles, titleId) >= 0;
        // Core 671 (adapt_nan_scrub): Hogwarts Legacy's colour and image writes are made finite (NaN -> 0, Inf -> 65504)
        // in the translated shaders, with fast math kept; its shader cache is translated again once.
        Ryujinx.Graphics.Shader.CodeGen.Spirv.SpirvNanScrub.Enabled = titleId == 0x0100F7E00C70E000UL;
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_prepare_jit")]
    public static int EmbeddedPrepareJit()
    {
        lock (EmbeddedHostGate)
        {
            if (!EmbeddedBootstrap.Ready || EmbeddedSessions.State != 0) return 2;
            if (EmbeddedJitQuarantined) return 3;
            EmbeddedLaunchDiagnostics.Record("jitArena", "begin");
            ulong mappedArena = Ryujinx.Cpu.LightningJit.DualMappedMemory.ArenaSize;
            if (!EmbeddedJitArenaRequest(EmbeddedJitArenaHint, mappedArena, Ryujinx.Memory.HostMemoryBudget.TotalBytes, out ulong arenaRequest))
            {
                // Not quarantined: the mapped arena still serves every title that fits in it.
                EmbeddedLaunchDiagnostics.Fail("jitArena", "jitRestartRequired", new InvalidOperationException(
                    "This game needs a " + (EmbeddedJitArenaHint >> 20) + " MiB code arena; RewindBox mapped " + (mappedArena >> 20) +
                    " MiB for an earlier game in this process. Close and reopen RewindBox, then start this game first."));
                return 1;
            }
            try
            {
                Ryujinx.Cpu.LightningJit.DualMappedMemory.RequestedArenaSize = arenaRequest;
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
