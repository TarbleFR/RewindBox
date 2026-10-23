using System;
using System.IO;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using Ryujinx.Common.Configuration;
using Ryujinx.HLE.FileSystem;
using Ryujinx.Common;

namespace Ryujinx.Library;

partial class Library
{
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_library_abi")]
    public static int EmbeddedLibraryAbi() => 2;
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_content_progress")]
    public static int EmbeddedContentProgress() => EmbeddedFirmwareProgress.Phase;
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_cancel_content")]
    public static int EmbeddedCancelContent() { EmbeddedFirmwareProgress.Cancel(); return 0; }
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
                                    EmbeddedGameHeader.Validate(stream, extension);
                                    var info = GameInfoLoader.GetGameInfo(_virtualFileSystem, stream, extension);
                                    if (info == null || ((extension == "nsp" || extension == "xci") &&
                                        (string.IsNullOrWhiteSpace(info.TitleId) || info.TitleId.TrimEnd('\0') == "0000000000000000"))) throw new InvalidDataException("The game could not be read with the current keys.");
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
                                EmbeddedFirmwareProgress.Begin();
                                if (path == null || !Path.IsPathFullyQualified(path) || !File.Exists(path))
                                    throw new FileNotFoundException("A local firmware archive is required.");
                                if (_contentManager.VerifyFirmwarePackage(path) == null)
                                    throw new InvalidDataException("The firmware package could not be validated.");
                                _contentManager.InstallFirmware(path);
                                json.WriteString("firmware", GetInstalledFirmwareVersion());
                                break;
                            case 2:
                                if (!string.IsNullOrEmpty(path))
                                {
                                    var validation = EmbeddedKeyValidation.Validate(path);
                                    json.WriteNumber("recognizedKeys", validation.Recognized);
                                    json.WriteNumber("ignoredKeys", validation.Ignored);
                                    json.WriteNumber("invalidSizeKeys", validation.InvalidSizes);
                                }
                                else
                                {
                                    // Staged validation above must never touch the live set.
                                    // Reload only after the transaction installs the keys.
                                    // Firmware discovery has its own operation/preflight and
                                    // must not turn a successful key import into a refusal.
                                    _virtualFileSystem.ReloadKeySet();
                                }
                                break;
                            case 3:
                                _contentManager.LoadEntries();
                                json.WriteString("firmware", GetInstalledFirmwareVersion());
                                json.WriteString("root", AppDataManager.BaseDirPath);
                                break;
                            case 4:
                            case 5:
                                EmbeddedInspectAddon(path, operation, json);
                                break;
                            case 6:
                                EmbeddedStorageInfo(json);
                                break;
                            case 7:
                                EmbeddedSaveTarget(path, json);
                                break;
                            case 8:
                                EmbeddedLaunchPreflight(path, json);
                                break;
                            default: throw new ArgumentOutOfRangeException(nameof(operation));
                        }
                        json.WriteBoolean("success", true);
                    }
                }
                catch (Exception error)
                {
                    if (operation == 8 && string.IsNullOrEmpty(EmbeddedLaunchDiagnostics.ErrorCode))
                        EmbeddedLaunchDiagnostics.Fail(EmbeddedLaunchDiagnostics.Stage,
                            EmbeddedLaunchDiagnostics.Classify(error), error);
                    json.WriteBoolean("success", false);
                    json.WriteString("error", error.GetType().Name);
                    json.WriteNumber("nativeStatus", error.HResult);
                    string code = error is OperationCanceledException ? "cancelled" : "failed";
                    if (operation == 8) code = EmbeddedLaunchDiagnostics.ErrorCode;
                    if (operation == 2) code = EmbeddedKeyValidation.ErrorCode(error);
                    if (operation == 1 && code != "cancelled")
                        code = EmbeddedFirmwareProgress.Phase >= 4 ? "firmwareInstallFailed" :
                            error.GetType().Name == "MissingKeyException" ? "firmwareIncompatible" :
                            error is FileNotFoundException ? "firmwareUnrecognized" : "firmwareIncomplete";
                    json.WriteString("errorCode", code);
                    json.WriteString("diagnostic", EmbeddedLaunchDiagnostics.Safe(error.ToString()));
                    if (operation == 8) json.WriteString("stage", EmbeddedLaunchDiagnostics.Stage);
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
