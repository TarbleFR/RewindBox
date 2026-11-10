using System;
using System.Runtime.InteropServices;
using System.Text.Json;
using Ryujinx.Common.Configuration;
using Ryujinx.Common;

namespace Ryujinx.Library;

internal sealed class EmbeddedGraphicsSettings
{
    internal AspectRatio? Aspect;
    internal bool? HostMemoryBudget;
    internal bool? TextureRecompression;
    internal float Resolution = 1;
    // iOS compatibility default: never skip a draw while compiling its pipeline.
    // Persist completed shaders where the engine cache budget allows it.
    // Explicit per-game values still override these conservative defaults.
    internal bool ShaderCache = true;
    internal bool AsyncShaders = false;
    internal VSyncMode Vsync = VSyncMode.Switch;
    internal ScalingFilter Filter = ScalingFilter.Bilinear;
    // Null leaves the base default (On, matching standalone). An explicit
    // per-game value is the escape hatch for a title that misbehaves threaded.
    internal BackendThreading? Threading;
    // Core-only experimental controls, off for every fresh configuration.
    internal bool OcclusionQuerySync;
    internal bool RelaxQueryFlushing;

    internal static EmbeddedGraphicsSettings Parse(string text)
    {
        if (text == null || text.Length > 8192) throw new ArgumentException("Invalid graphics configuration.");
        using var document = JsonDocument.Parse(text);
        var root = document.RootElement;
        var settings = new EmbeddedGraphicsSettings();
        foreach (var property in root.EnumerateObject())
        {
            switch (property.Name)
            {
                case "occlusionQuerySync": settings.OcclusionQuerySync = property.Value.GetBoolean(); break;
                case "relaxQueryFlushing": settings.RelaxQueryFlushing = property.Value.GetBoolean(); break;
                case "aspectRatio":
                    settings.Aspect = (AspectRatio)property.Value.GetInt32();
                    if (!Enum.IsDefined(settings.Aspect.Value)) throw new ArgumentException("Unsupported aspect ratio.");
                    break;
                case "hostMemoryBudget": settings.HostMemoryBudget = property.Value.GetBoolean(); break;
                case "textureRecompression": settings.TextureRecompression = property.Value.GetBoolean(); break;
                case "resolution": settings.Resolution = property.Value.GetSingle(); break;
                case "shaderCache": settings.ShaderCache = property.Value.GetBoolean(); break;
                case "asyncShaders": settings.AsyncShaders = property.Value.GetBoolean(); break;
                case "vsync": settings.Vsync = property.Value.GetBoolean() ? VSyncMode.Switch : VSyncMode.Unbounded; break;
                case "backendThreading": settings.Threading = property.Value.GetBoolean() ? BackendThreading.On : BackendThreading.Off; break;
                case "filter":
                    settings.Filter = property.Value.GetString() switch
                    {
                        "bilinear" => ScalingFilter.Bilinear, "nearest" => ScalingFilter.Nearest,
                        "fsr" => ScalingFilter.Fsr, "area" => ScalingFilter.Area,
                        _ => throw new ArgumentException("Unsupported scaling filter. MetalFX requires its native callbacks.")
                    };
                    break;
                default: throw new ArgumentException("Unknown graphics option: " + property.Name);
            }
        }
        if (!float.IsFinite(settings.Resolution) || settings.Resolution < 0.5f || settings.Resolution > 2f)
            throw new ArgumentOutOfRangeException("resolution");
        return settings;
    }

    internal Options Apply(Options options)
    {
        if (Aspect.HasValue) options.AspectRatio = Aspect.Value;
        if (HostMemoryBudget.HasValue) options.EnableHostMemoryBudgetTracking = HostMemoryBudget.Value;
        if (TextureRecompression.HasValue) options.EnableTextureRecompression = TextureRecompression.Value;
        options.ResScale = Resolution;
        options.DisableShaderCache = !ShaderCache;
        options.EnableAsyncShaderCompilation = AsyncShaders;
        options.VSyncMode = Vsync;
        options.ScalingFilter = Filter;
        // The standalone app forces BackendThreading.On before every launch and
        // never applies its saved value (default Off), so an imported personal
        // config must not turn it off here either: only this per-game switch can.
        options.BackendThreading = Threading ?? BackendThreading.On;
        return options;
    }
}

partial class Library
{
    private static EmbeddedGraphicsSettings EmbeddedGraphics = new();

    private static bool EmbeddedIsHogwarts(string path)
    {
        // Read the actual launched content, not a stale preflight or UI id.
        // A failed identity check disables both experiments for this session.
        try
        {
            using var stream = System.IO.File.OpenRead(path);
            string extension = System.IO.Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
            string title = GameInfoLoader.GetGameInfo(_virtualFileSystem, stream, extension)?.TitleId?.TrimEnd('\0');
            return string.Equals(title, "0100F7E00C70E000", StringComparison.OrdinalIgnoreCase);
        }
        catch { return false; }
    }

    // Uses the engine's existing SurfaceFlinger crop/ratio path. The session
    // gate rejects delayed UI callbacks after stop or for a different game.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_set_aspect_ratio")]
    public static int EmbeddedSetAspectRatio(long generation, int value)
    {
        if (!Enum.IsDefined((AspectRatio)value)) return 1;
        try
        {
            bool applied = false;
            bool current = EmbeddedSessions.WithInputs(generation, () =>
            {
                var window = _window;
                if (window?.Device?.Configuration == null) return;
                window.Device.Configuration.AspectRatio = (AspectRatio)value;
                applied = true;
            });
            return current && applied ? 0 : 2;
        }
        catch (Exception error) { EmbeddedLaunchDiagnostics.Fail("display", "displayUnavailable", error); return 3; }
    }

    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_configure_graphics")]
    public static int EmbeddedConfigureGraphics(nint jsonUtf8)
    {
        try
        {
            var settings = EmbeddedGraphicsSettings.Parse(Marshal.PtrToStringUTF8(jsonUtf8));
            lock (EmbeddedHostGate)
            {
                if (EmbeddedSessions.State != 0) return 2;
                EmbeddedGraphics = settings;
                return 0;
            }
        }
        catch (Exception error) { EmbeddedLaunchDiagnostics.Fail("graphics", "invalidGraphics", error); return 1; }
    }
}
