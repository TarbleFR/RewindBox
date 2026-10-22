using System;
using System.Runtime.InteropServices;
using System.Text.Json;
using Ryujinx.Common.Configuration;

namespace Ryujinx.Library;

internal sealed class EmbeddedGraphicsSettings
{
    internal float Resolution = 1;
    internal bool ShaderCache;
    internal bool AsyncShaders = true;
    internal VSyncMode Vsync = VSyncMode.Switch;
    internal ScalingFilter Filter = ScalingFilter.Bilinear;

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
                case "resolution": settings.Resolution = property.Value.GetSingle(); break;
                case "shaderCache": settings.ShaderCache = property.Value.GetBoolean(); break;
                case "asyncShaders": settings.AsyncShaders = property.Value.GetBoolean(); break;
                case "vsync": settings.Vsync = property.Value.GetBoolean() ? VSyncMode.Switch : VSyncMode.Unbounded; break;
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
        options.ResScale = Resolution;
        options.DisableShaderCache = !ShaderCache;
        options.EnableAsyncShaderCompilation = AsyncShaders;
        options.VSyncMode = Vsync;
        options.ScalingFilter = Filter;
        return options;
    }
}

partial class Library
{
    private static EmbeddedGraphicsSettings EmbeddedGraphics = new();

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
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
