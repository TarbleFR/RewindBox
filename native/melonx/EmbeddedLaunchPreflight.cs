using System;
using System.IO;
using Path = System.IO.Path;
using System.Text.Json;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.Tools.FsSystem.NcaUtils;
using LibHac.Tools.FsSystem;
using LibHac.Ncm;
using Ryujinx.Common;
using Ryujinx.Common.Configuration;
using Ryujinx.HLE.Loaders.Processes.Extensions;
using Ryujinx.HLE.Utilities;

namespace Ryujinx.Library;

partial class Library
{
    // No emulation context, guest memory or session reservation is created here.
    // A configuration/content failure therefore leaves the engine retryable.
    private static void EmbeddedLaunchPreflight(string path, Utf8JsonWriter json)
    {
        EmbeddedLaunchDiagnostics.Begin();
        EmbeddedJitArenaHint = 0;
        EmbeddedLaunchDiagnostics.Record("file", "begin");
        if (path == null || !Path.IsPathFullyQualified(path) || !File.Exists(path))
            throw new FileNotFoundException("The selected local game is unavailable.");
        string extension = Path.GetExtension(path).TrimStart('.').ToLowerInvariant();
        using (var stream = File.OpenRead(path)) EmbeddedGameHeader.Validate(stream, extension);
        json.WriteNumber("bytes", new FileInfo(path).Length);
        EmbeddedLaunchDiagnostics.Record("file", "passed", detail: "Readable local file and bounded format header validated.");

        bool packaged = extension == "nsp" || extension == "xci";
        string system = Path.Combine(AppDataManager.BaseDirPath, "system");
        string prod = Path.Combine(system, "prod.keys"), title = Path.Combine(system, "title.keys");
        EmbeddedLaunchDiagnostics.Record("keys", "begin");
        json.WriteBoolean("prodKeysPresent", File.Exists(prod));
        json.WriteBoolean("titleKeysPresent", File.Exists(title));
        if (packaged && !File.Exists(prod))
        {
            var error = new InvalidDataException("Import your personal prod.keys into Documents/MeloNX/system.");
            EmbeddedLaunchDiagnostics.Fail("keys", "keysMissing", error); throw error;
        }
        // Validate names/sizes only. The live engine performs normal decryption
        // with the user's own keys; no secret values enter this response.
        foreach (string file in new[] { prod, title })
            if (File.Exists(file))
            {
                try { EmbeddedKeyValidation.Validate(file); }
                catch (Exception error) { EmbeddedLaunchDiagnostics.Fail("keys", "keysInvalid", error); throw; }
            }
        _virtualFileSystem.ReloadKeySet();
        EmbeddedLaunchDiagnostics.Record("keys", "passed", detail: packaged ? "Personal key files reloaded; content-specific verification follows." : "Unencrypted homebrew does not require personal keys.");

        EmbeddedLaunchDiagnostics.Record("contentPreflight", "begin");
        if (packaged)
        {
            // Metadata/icon decryption is insufficient: open the actual base
            // program's code/data sections with the engine's integrity policy.
            using IFileSystem fs = PartitionFileSystemUtils.OpenApplicationFileSystem(path, _virtualFileSystem);
            bool programFound = false;
            Span<byte> probe = stackalloc byte[1];
            foreach (var entry in fs.GetContentData(ContentMetaType.Application, _virtualFileSystem, IntegrityCheckLevel.ErrorOnInvalid))
            {
                var program = entry.Value.GetNcaByType(_virtualFileSystem.KeySet, LibHac.Ncm.ContentType.Program, 0);
                if (program == null) continue;
                foreach (var section in new[] { NcaSectionType.Code, NcaSectionType.Data })
                {
                    if (!program.SectionExists(section)) continue;
                    using var storage = program.OpenStorage(section, IntegrityCheckLevel.ErrorOnInvalid);
                    storage.GetSize(out long size).ThrowIfFailure();
                    if (size > 0)
                    {
                        storage.Read(0, probe).ThrowIfFailure(); probe.Clear();
                    }
                }
                json.WriteString("titleId", entry.Key.ToString("x16"));
                EmbeddedJitArenaHint = EmbeddedJitArenaFor(entry.Key, program);
                programFound = true; break;
            }
            if (!programFound) throw new InvalidDataException("No base program was found in the selected package.");
        }
        EmbeddedLaunchDiagnostics.Record("contentPreflight", "passed", detail: packaged ? "Base program sections opened with the user's keys; no decrypted bytes logged." : "Homebrew format validated.");

        EmbeddedLaunchDiagnostics.Record("firmware", "begin");
        _contentManager.LoadEntries();
        var version = _contentManager.GetCurrentFirmwareVersion();
        string firmware = version?.VersionString ?? "";
        json.WriteString("firmware", firmware);
        if (packaged && string.IsNullOrEmpty(firmware))
        {
            var error = new InvalidDataException("No readable personal firmware installation was recognized.");
            EmbeddedLaunchDiagnostics.Fail("firmware", "firmwareMissing", error); throw error;
        }
        EmbeddedLaunchDiagnostics.Record("firmware", "passed", detail: firmware.Length > 0 ? "Recognized firmware " + firmware : "Firmware absent; homebrew preflight permits this.");
        _accountManager.Refresh();
        json.WriteBoolean("preflightOnly", true);
    }
}
