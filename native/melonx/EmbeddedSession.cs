using System;
using System.IO;
using System.Runtime.InteropServices;
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Configuration.Hid;
using Ryujinx.HLE.HOS.SystemState;
using System.Text;
using System.Linq;
using Ryujinx.Input.Native;
using Ryujinx.Common;

namespace Ryujinx.Library;

partial class Library
{
    private static string EmbeddedPrepareFailure = "";
    private static readonly EmbeddedSessionCoordinator EmbeddedSessions = new();
    private static readonly object EmbeddedHostGate = new();
    private static Options EmbeddedPreparedOptions;
    internal static void WithdrawEmbeddedControls() => EmbeddedSessions.WithdrawControls();

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_session_abi")]
    public static int EmbeddedSessionAbi() => 1;

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_session_state")]
    public static int EmbeddedSessionState() => EmbeddedSessions.State;

    // Caller-owned error buffer. Returns required bytes excluding the NUL.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_session_error")]
    public static unsafe int EmbeddedSessionError(byte* output, int capacity)
    {
        try
        {
            byte[] error = Encoding.UTF8.GetBytes(!string.IsNullOrEmpty(EmbeddedPrepareFailure) ? EmbeddedPrepareFailure : EmbeddedSessions.LastFailure ?? EmbeddedBootstrap.LastFailure ?? "");
            if (output != null && capacity > 0)
            {
                int count = Math.Min(error.Length, capacity - 1);
                error.AsSpan(0, count).CopyTo(new Span<byte>(output, count));
                output[count] = 0;
            }
            return error.Length;
        }
        catch { return -1; }
    }

    // Both strings are borrowed, copied before return, and never freed here.
    // Positive generation ID on success; -1 busy, -2 invalid, -3 not initialized.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_prepare")]
    public static long EmbeddedPrepare(nint pathUtf8, nint localeUtf8, int width, int height)
    {
        try
        {
            lock (EmbeddedHostGate)
            {
                if (!EmbeddedBootstrap.Ready) return -3;
                string path = Marshal.PtrToStringUTF8(pathUtf8);
                string locale = Marshal.PtrToStringUTF8(localeUtf8) ?? "en";
                if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path) ||
                    !File.Exists(path) || width < 1 || height < 1 || width > 16384 || height > 16384)
                    return -2;
                string extension = Path.GetExtension(path).ToLowerInvariant();
                if (extension != ".nro" && extension != ".nso" && extension != ".nsp" && extension != ".xci") return -2;
                if (EmbeddedSessions.State != 0) return -1;
                EmbeddedPrepareFailure = "";
                EmbeddedLaunchDiagnostics.Record("session", "begin");
                Options options = EmbeddedOptions(Path.GetFullPath(path), locale, width, height);
                // Record effective values after personal/per-game overrides.
                // No game path, personal profile or key material is included.
                EmbeddedLaunchDiagnostics.Record("configuration", "effective", detail:
                    FormattableString.Invariant($"Applied graphics: resolution={options.ResScale}; shaderCache={!options.DisableShaderCache}; asyncShaders={options.EnableAsyncShaderCompilation}; vsync={options.VSyncMode}; hostMemoryBudget={options.EnableHostMemoryBudgetTracking}; textureRecompression={options.EnableTextureRecompression}; threading={options.BackendThreading}"));
                // Every other option the engine consumes, so a session can be
                // compared field by field with the standalone app's config.
                EmbeddedLaunchDiagnostics.Record("configuration", "engine", detail:
                    FormattableString.Invariant($"Engine options: ptc={!options.DisablePTC}; macroHle={!options.DisableMacroHLE}; docked={!options.DisableDockedMode}; memoryManager={options.MemoryManagerMode}; aspect={options.AspectRatio}; anisotropy={options.MaxAnisotropy}; antiAliasing={options.AntiAliasing}; scaling={options.ScalingFilter}/{options.ScalingFilterLevel}; language={options.SystemLanguage}; region={options.SystemRegion}; ignoreMissingServices={options.IgnoreMissingServices}; customVsync={options.CustomVSyncInterval}; moltenVk={EmbeddedNativeLibraries.MoltenVk}"));
                // Native Npad disposal disconnects its pad objects. A new
                // host view reattaches fresh pads after this reservation.
                foreach (var pad in ((NativeGamepadDriver)_inputManager.GamepadDriver).GetGamepads().ToArray())
                    NativeGamepadDriver.DetachGamepad((nint)Convert.ToInt64(pad.Id, 16));
                lock (inputConfigurationLock) _inputConfiguration.Clear();
                NativeTouchDriver.ResetEmbeddedTouches();
                long generation = EmbeddedSessions.Prepare();
                if (generation > 0) { EmbeddedPreparedOptions = options; EmbeddedLaunchDiagnostics.Record("session", "passed"); }
                return generation;
            }
        }
        catch (Exception error) { EmbeddedPrepareFailure = EmbeddedLaunchDiagnostics.Safe(error.ToString()); EmbeddedLaunchDiagnostics.Fail("session", EmbeddedLaunchDiagnostics.Classify(error), error, -2); return -2; }
    }

    // Synchronous: invoke on a dedicated host worker, never UIKit's main thread.
    // Return only after the guest/render workers and session resources end.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_run")]
    public static int EmbeddedRun(long generation)
    {
        try
        {
            Options options;
            lock (EmbeddedHostGate) options = EmbeddedPreparedOptions;
            return EmbeddedSessions.Run(generation, () =>
            {
                if (options == null || GetNativeMetalLayer() == nint.Zero)
                    throw new InvalidOperationException("No prepared game or CAMetalLayer.");
                try { Load(options); EmbeddedLaunchDiagnostics.Record("close", "passed"); return 0; }
                catch (Exception error)
                {
                    EmbeddedLaunchDiagnostics.Fail(EmbeddedLaunchDiagnostics.Stage,
                        EmbeddedLaunchDiagnostics.Classify(error), error, 3);
                    throw;
                }
                finally
                {
                    lock (metalLayerLock) nativeMetalLayer = nint.Zero;
                }
            });
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 3; }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_stop")]
    public static int EmbeddedStop(long generation)
    {
        try { return EmbeddedSessions.Stop(generation) ? 0 : 2; }
        catch (Exception error) { Console.Error.WriteLine(error); return 3; }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_cancel_prepared")]
    public static int EmbeddedCancelPrepared(long generation)
    {
        try { return EmbeddedSessions.CancelPrepared(generation) ? 0 : 2; }
        catch (Exception error) { Console.Error.WriteLine(error); return 3; }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_pause")]
    public static int EmbeddedPause(long generation, int paused)
    {
        try { return EmbeddedSessions.Pause(generation, paused != 0) ? 0 : 2; }
        catch (Exception error) { Console.Error.WriteLine(error); return 3; }
    }

    private static Options EmbeddedOptions(string path, string locale, int width, int height)
    {
        // Options' CLI attributes do not initialize new Options(). Spell out
        // required mobile defaults, including nonzero audio/resolution values.
        string language = locale.Replace('_', '-').Split('-')[0].ToLowerInvariant();
        SystemLanguage systemLanguage = language switch
        {
            "fr" => SystemLanguage.French, "de" => SystemLanguage.German,
            "it" => SystemLanguage.Italian, "es" => SystemLanguage.Spanish,
            "ja" => SystemLanguage.Japanese, "ko" => SystemLanguage.Korean,
            "nl" => SystemLanguage.Dutch, "pt" => SystemLanguage.Portuguese,
            "ru" => SystemLanguage.Russian, "zh" => SystemLanguage.SimplifiedChinese,
            _ => SystemLanguage.AmericanEnglish
        };
        return EmbeddedGraphics.Apply(ApplyEmbeddedPersonalOptions(new Options
        {
            InputPath = path, BaseDataDir = Ryujinx.Common.Configuration.AppDataManager.BaseDirPath,
            ExclusiveFullscreenWidth = width, ExclusiveFullscreenHeight = height,
            IsExclusiveFullscreen = true, IsFullscreen = true,
            // Backend (GPU) threading on by default, matching the standalone
            // MeloNX app, which forces BackendThreading.On before every launch.
            // Off serialized guest FIFO, Vulkan->Metal submission, pipeline
            // compilation and present on one thread and caused the slowdowns the
            // standalone did not have. An explicit per-game value still overrides.
            GraphicsBackend = GraphicsBackend.Vulkan, BackendThreading = BackendThreading.On,
            ResScale = 1, MaxAnisotropy = -1, AspectRatio = AspectRatio.Fixed16x9,
            ScalingFilter = ScalingFilter.Bilinear, ScalingFilterLevel = 60, MetalFxUpscaleFactor = 2,
            EnableHostMemoryBudgetTracking = true, EnableTextureRecompression = true,
            // Match EmbeddedGraphicsSettings defaults before saved per-game overrides.
            // Async compilation skipped draws in Persona 5 Royal on MoltenVK;
            // synchronous compilation may stall briefly, but keeps geometry intact.
            DisableShaderCache = false, EnableAsyncShaderCompilation = false,
            DisableDockedMode = true, MemoryManagerMode = MemoryManagerMode.HostMappedUnsafe,
            AudioVolume = 1, SystemLanguage = systemLanguage, SystemRegion = RegionCode.USA,
            SystemTimeZone = "UTC", MultiplayerLanInterfaceId = "0", PreferredGPUVendor = "",
            VSyncMode = VSyncMode.Switch, CustomVSyncInterval = 120,
            controllerType1 = ControllerType.ProController,
            LoggingEnableError = true, EnableKeyboard = false, EnableMouse = false,
            UseHypervisor = false, EnableInternetAccess = false,
        }, path));
    }
}
