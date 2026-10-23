using System;
using System.IO;
using System.Text.Json;
using Ryujinx.Common.Configuration;
using Ryujinx.HLE.HOS.SystemState;

namespace Ryujinx.Library;

partial class Library
{
    // The standalone app's actual Options+Codable keys. Host/window/JIT paths,
    // MetalFX callbacks and networking options are intentionally not activated.
    private static Options ApplyEmbeddedPersonalOptions(Options options, string game)
    {
        Apply(Path.Combine(AppDataManager.BaseDirPath, "config.json"));
        string configuration = Path.Combine(AppDataManager.BaseDirPath, "config");
        if (Directory.Exists(configuration))
        {
            using var stream = File.OpenRead(game);
            string extension = Path.GetExtension(game).TrimStart('.').ToLowerInvariant();
            string title = GameInfoLoader.GetGameInfo(_virtualFileSystem, stream, extension)?.TitleId?.TrimEnd('\0');
            if (title != null && title.Length == 16 && ulong.TryParse(title,
                System.Globalization.NumberStyles.HexNumber, null, out _))
                Apply(Path.Combine(configuration, title + "_config.json"));
        }
        return options;

        void Apply(string path)
        {
            if (!File.Exists(path)) return;
            if (new FileInfo(path).Length > 4 * 1024 * 1024) throw new InvalidDataException("Personal configuration exceeds limit.");
            using var document = JsonDocument.Parse(File.ReadAllText(path));
            foreach (var property in document.RootElement.EnumerateObject())
            {
                var value = property.Value;
                switch (property.Name)
                {
                    case "disablePTC": options.DisablePTC = value.GetBoolean(); break;
                    case "enableTextureRecompression": options.EnableTextureRecompression = value.GetBoolean(); break;
                    case "enableHostMemoryBudgetTracking": options.EnableHostMemoryBudgetTracking = value.GetBoolean(); break;
                    case "disableDockedMode": options.DisableDockedMode = value.GetBoolean(); break;
                    case "disableMacroHLE": options.DisableMacroHLE = value.GetBoolean(); break;
                    case "ignoreMissingServices": options.IgnoreMissingServices = value.GetBoolean(); break;
                    case "systemTimeZone":
                        string zone = value.GetString();
                        if (string.IsNullOrEmpty(zone) || zone.Length > 128) throw new InvalidDataException("Invalid time zone.");
                        options.SystemTimeZone = zone; break;
                    case "systemTimeOffset": options.SystemTimeOffset = value.GetInt64(); break;
                    case "audioVolume":
                        float volume = value.GetSingle();
                        if (!float.IsFinite(volume) || volume < 0 || volume > 1) throw new InvalidDataException("Invalid audio volume.");
                        options.AudioVolume = volume; break;
                    case "maxAnisotropy":
                        float anisotropy = value.GetSingle();
                        if (!float.IsFinite(anisotropy) || anisotropy < -1 || anisotropy > 16) throw new InvalidDataException("Invalid anisotropy.");
                        options.MaxAnisotropy = anisotropy; break;
                    case "aspectRatio": options.AspectRatio = Defined<AspectRatio>(value); break;
                    case "antiAliasing": options.AntiAliasing = Defined<AntiAliasing>(value); break;
                    case "backendThreading": options.BackendThreading = Defined<BackendThreading>(value); break;
                    case "systemLanguage": options.SystemLanguage = Defined<SystemLanguage>(value); break;
                    case "systemRegion": options.SystemRegion = Defined<RegionCode>(value); break;
                }
            }
        }
    }
    private static T Defined<T>(JsonElement value) where T : struct, Enum
    {
        var candidate = (T)Enum.ToObject(typeof(T), value.GetInt32());
        if (!Enum.IsDefined(candidate)) throw new InvalidDataException("Unsupported personal configuration value.");
        return candidate;
    }
}
