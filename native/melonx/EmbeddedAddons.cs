using System;
using System.Globalization;
using System.IO;
using Path = System.IO.Path;
using LibHac.Fs.Shim;
using LibHac.Tools.FsSystem;
using LibHac.Tools.Ncm;
using System.Text.Json;
using System.Collections.Generic;
using LibHac.Common;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.FsSystem;
using LibHac.Ncm;
using LibHac.Ns;
using LibHac.Tools.Fs;
using LibHac.Tools.FsSystem.NcaUtils;
using Ryujinx.HLE.FileSystem;
using Ryujinx.HLE.Loaders.Processes.Extensions;
using Ryujinx.HLE.Utilities;

namespace Ryujinx.Library;

partial class Library
{
    // Inspect actual CNMT/NCA contents with the user's keys before any update
    // or DLC selection is committed. Filenames and UI labels are not proof.
    private static void EmbeddedInspectAddon(string request, int operation, Utf8JsonWriter json)
    {
        if (request == null || request.Length > 16384) throw new ArgumentException("Invalid add-on request.");
        using var document = JsonDocument.Parse(request);
        string path = document.RootElement.GetProperty("path").GetString();
        string title = document.RootElement.TryGetProperty("titleId", out var titleProperty)
            ? titleProperty.GetString() : null;
        ulong? requested = EmbeddedAddonSelection.RequestedTitle(title, required: operation != 4);
        ulong titleId = requested ?? 0;
        if (path == null || !Path.IsPathFullyQualified(path) || !File.Exists(path))
            throw new FileNotFoundException("The add-on must be a readable local package.");
        if (operation == 4 && string.Equals(Path.GetExtension(path), ".nsz", StringComparison.OrdinalIgnoreCase))
        {
            string stage = document.RootElement.GetProperty("expandedPath").GetString();
            try { EmbeddedNsz.Expand(path, stage); }
            catch (IOException error) when ((error.HResult & 0xffff) is 28 or 39 or 112)
            { throw new IOException("insufficientSpace", error); }
            catch (Exception error) when (error is InvalidDataException or EndOfStreamException or OverflowException or
                                          System.Text.DecoderFallbackException or ZstdSharp.ZstdException)
            { throw new InvalidDataException("invalidContent", error); }
            path = stage;
        }
        using IFileSystem pfs = PartitionFileSystemUtils.OpenApplicationFileSystem(path, _virtualFileSystem);
        _virtualFileSystem.ImportTickets(pfs);
        if (operation == 4)
        {
            var verifiedTitles = new List<ulong>();
            var controls = new Dictionary<ulong, Nca>();
            var programs = new Dictionary<ulong, Nca>();
            foreach (var pair in pfs.GetContentData(ContentMetaType.Patch, _virtualFileSystem, IntegrityCheckLevel.None))
            {
                if (requested.HasValue && (pair.Key & ~0x1FFFUL) != requested.Value) continue;
                var patch = pair.Value.GetNcaByType(_virtualFileSystem.KeySet, LibHac.Ncm.ContentType.Program, 0);
                var control = pair.Value.GetNcaByType(_virtualFileSystem.KeySet, LibHac.Ncm.ContentType.Control, 0);
                if (patch != null && control != null) { verifiedTitles.Add(pair.Key); controls[pair.Key] = control; programs[pair.Key] = patch; }
            }
            titleId = EmbeddedAddonSelection.SelectUpdate(verifiedTitles, requested);
            json.WriteString("kind", "update");
            // RewindBox (Nextendo data): the update's display version, from its Control NCA's /control.nacp, so the host can
            // compare the installed version with the one Nextendo's catalog requires. Omitted when unreadable; never throws.
            string displayVersion = UpdateDisplayVersion(controls, titleId);
            if (displayVersion != null) json.WriteString("displayVersion", displayVersion);
            // RewindBox (adapt_cheat_report): the update's main executable build id, in the cheat files' 16-digit form (the
            // selected update is what runs). Omitted when unreadable; never throws.
            string updateBuildId = UpdateBuildId(programs, titleId);
            if (updateBuildId != null) json.WriteString("buildId", updateBuildId);
        }
        else
        {
            var found = new List<(string Path, ulong Title)>();
            foreach (var entry in pfs.EnumerateEntries("/", "*.nca"))
            {
                using var file = new UniqueRef<IFile>();
                pfs.OpenFile(ref file.Ref, entry.FullPath.ToU8Span(), OpenMode.Read).ThrowIfFailure();
                var nca = TryCreateNca(file.Get.AsStorage(), path);
                if (nca == null || nca.Header.ContentType != NcaContentType.PublicData || (nca.Header.TitleId & ~0x1FFFUL) != titleId) continue;
                if (entry.FullPath.Length > 256 || found.Count >= 128) throw new InvalidDataException("The package exceeds this add-on import's bounded manifest.");
                found.Add((entry.FullPath, nca.Header.TitleId));
            }
            if (found.Count == 0) throw new InvalidDataException("This package contains no compatible DLC for the selected game, or its keys are missing.");
            json.WriteString("kind", "dlc");
            json.WriteStartArray("dlc_nca_list");
            foreach (var item in found)
            {
                json.WriteStartObject(); json.WriteString("path", item.Path);
                json.WriteNumber("title_id", item.Title); json.WriteBoolean("is_enabled", true); json.WriteEndObject();
            }
            json.WriteEndArray();
        }
        json.WriteString("baseTitleId", titleId.ToString("x16"));
    }

    // The main build id of the selected update: the Program NCA of the update for the base title's first program
    // (base | 0x800) when there is one, otherwise of any update of that base title; its ExeFS "main" header.
    internal static string UpdateBuildId(Dictionary<ulong, Nca> programs, ulong baseTitleId)
    {
        var ordered = new List<Nca>();
        if (programs.TryGetValue(baseTitleId | 0x800UL, out Nca first)) ordered.Add(first);
        foreach (var pair in programs)
            if ((pair.Key & ~0x1FFFUL) == baseTitleId && pair.Key != (baseTitleId | 0x800UL)) ordered.Add(pair.Value);
        foreach (Nca program in ordered)
        {
            try
            {
                string id = Ryujinx.HLE.EmbeddedCheatReport.MainBuildId(program.OpenFileSystem(NcaSectionType.Code, IntegrityCheckLevel.None));
                if (id != null) return id;
            }
            catch (Exception)
            {
                // An update without a readable ExeFS leaves the build id out.
            }
        }

        return null;
    }

    // RewindBox (adapt_cheat_report): the main executable build id of a game file (content operation 0), in the cheat
    // files' 16-digit form: the base application's program 0 ExeFS "main". Null for homebrew or anything unreadable.
    internal static string EmbeddedApplicationBuildId(string path)
    {
        try
        {
            string extension = Path.GetExtension(path ?? string.Empty).TrimStart('.').ToLowerInvariant();
            if (extension != "nsp" && extension != "xci") return null;
            using IFileSystem pfs = PartitionFileSystemUtils.OpenApplicationFileSystem(path, _virtualFileSystem, throwOnFailure: false);
            if (pfs == null) return null;
            foreach (var pair in pfs.GetContentData(ContentMetaType.Application, _virtualFileSystem, IntegrityCheckLevel.None))
            {
                if ((pair.Key & 0x1FFFUL) != 0) continue; // the base program, not another program of the application
                var program = pair.Value.GetNcaByType(_virtualFileSystem.KeySet, LibHac.Ncm.ContentType.Program, 0);
                if (program == null) continue;
                string id = Ryujinx.HLE.EmbeddedCheatReport.MainBuildId(program.OpenFileSystem(NcaSectionType.Code, IntegrityCheckLevel.None));
                if (id != null) return id;
            }
        }
        catch (Exception)
        {
            // Metadata never fails for the build id.
        }

        return null;
    }

    // The display version of the selected update: the Control NCA of the update for the base title's first program
    // (base | 0x800) when there is one, otherwise of any update of that base title. DisplayVersion is one field of the
    // NACP (not per language); NULs and blanks are trimmed. Null when nothing readable is found.
    internal static string UpdateDisplayVersion(Dictionary<ulong, Nca> controls, ulong baseTitleId)
    {
        var ordered = new List<Nca>();
        if (controls.TryGetValue(baseTitleId | 0x800UL, out Nca first)) ordered.Add(first);
        foreach (var pair in controls)
            if ((pair.Key & ~0x1FFFUL) == baseTitleId && pair.Key != (baseTitleId | 0x800UL)) ordered.Add(pair.Value);
        foreach (Nca control in ordered)
        {
            try
            {
                var nacp = new BlitStruct<ApplicationControlProperty>(1);
                using var file = new UniqueRef<IFile>();
                if (control.OpenFileSystem(NcaSectionType.Data, IntegrityCheckLevel.None)
                        .OpenFile(ref file.Ref, "/control.nacp".ToU8Span(), OpenMode.Read).IsFailure()) continue;
                if (file.Get.Read(out long read, 0, nacp.ByteSpan, ReadOption.None).IsFailure() || read < nacp.ByteSpan.Length) continue;
                string version = nacp.Value.DisplayVersionString.ToString()?.TrimEnd('\0').Trim();
                if (!string.IsNullOrEmpty(version) && version.Length <= 0x10) return version;
            }
            catch (Exception)
            {
                // An unreadable control leaves the version out; the inspection itself stands.
            }
        }

        return null;
    }
}
