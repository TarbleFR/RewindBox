using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using Ryujinx.Common.Configuration;

namespace Ryujinx.Library;

partial class Library
{
    // A single call, caller-owned UTF-8 output. Imports are never performed by
    // a sizing call. The host supplies 64 KiB; icons are cached separately.
    // 0 metadata; 1 install personal firmware; 2 reload personal keys; 3 status.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_content")]
    public static unsafe int EmbeddedContent(nint pathUtf8, int operation, byte* output, int capacity)
    {
        if (output == null || capacity < 65536 || capacity > 1048576) return 1;
        try
        {
            using var memory = new MemoryStream();
            using (var json = new Utf8JsonWriter(memory))
            {
                json.WriteStartObject();
                try
                {
                    lock (EmbeddedHostGate)
                    {
                        if (!EmbeddedBootstrap.Ready) throw new InvalidOperationException("Engine not initialized.");
                        if (EmbeddedSessions.State != 0) throw new InvalidOperationException("Close the current game before changing library content.");
                        string path = Marshal.PtrToStringUTF8(pathUtf8);
                        switch (operation)
                        {
                            case 0:
                                if (path == null || !Path.IsPathFullyQualified(path) || !File.Exists(path))
                                    throw new FileNotFoundException("A local game is required.");
                                using (var stream = File.OpenRead(path))
                                {
                                    string extension = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
                                    if (extension != "nsp" && extension != "xci" && extension != "nro" && extension != "nso")
                                        throw new InvalidDataException("Unsupported game format.");
                                    var info = GameInfoLoader.GetGameInfo(_virtualFileSystem, stream, extension);
                                    if (info == null) throw new InvalidDataException("The game could not be read with the current keys.");
                                    json.WriteString("title", info.TitleName?.TrimEnd('\0'));
                                    json.WriteString("titleId", info.TitleId?.TrimEnd('\0'));
                                    json.WriteString("developer", info.Developer?.TrimEnd('\0'));
                                    json.WriteString("version", info.Version?.TrimEnd('\0'));
                                    json.WriteNumber("bytes", stream.Length);
                                    if (info.Icon != null && info.Icon.Length > 0 && info.Icon.Length <= 16 * 1024 * 1024)
                                    {
                                        string cache = Path.Combine(AppDataManager.BaseDirPath, "cache", "artwork");
                                        Directory.CreateDirectory(cache);
                                        string icon = Path.Combine(cache, Convert.ToHexString(SHA256.HashData(info.Icon)) + ".jpg");
                                        if (!File.Exists(icon)) File.WriteAllBytes(icon, info.Icon);
                                        json.WriteString("iconPath", icon);
                                    }
                                }
                                break;
                            case 1:
                                if (path == null || !Path.IsPathFullyQualified(path) || !File.Exists(path))
                                    throw new FileNotFoundException("A local firmware archive is required.");
                                _contentManager.InstallFirmware(path);
                                json.WriteString("firmware", GetInstalledFirmwareVersion());
                                break;
                            case 2:
                                _virtualFileSystem.ReloadKeySet();
                                break;
                            case 3:
                                json.WriteString("firmware", GetInstalledFirmwareVersion());
                                json.WriteString("root", AppDataManager.BaseDirPath);
                                break;
                            default: throw new ArgumentOutOfRangeException(nameof(operation));
                        }
                        json.WriteBoolean("success", true);
                    }
                }
                catch (Exception error)
                {
                    Console.Error.WriteLine("MeloNX content: " + error);
                    json.WriteBoolean("success", false);
                    json.WriteString("error", error.GetType().Name);
                    json.WriteString("diagnostic", error.Message.Length > 8192 ? error.Message[..8192] : error.Message);
                }
                json.WriteEndObject();
            }
            byte[] bytes = memory.ToArray();
            if (bytes.Length >= capacity) return 2;
            bytes.CopyTo(new Span<byte>(output, capacity));
            output[bytes.Length] = 0;
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); output[0] = 0; return 3; }
    }
}
