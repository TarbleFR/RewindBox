using System;
using System.Globalization;
using System.IO;
using System.Text.Json;
using System.Collections.Generic;
using LibHac.Common;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.FsSystem;
using LibHac.Ncm;
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
        string title = document.RootElement.GetProperty("titleId").GetString();
        if (title == null || title.Length != 16 || !ulong.TryParse(title, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out ulong titleId) || titleId == 0)
            throw new ArgumentException("A valid base-game title ID is required.");
        titleId &= ~0x1FFFUL;
        if (path == null || !Path.IsPathFullyQualified(path) || !File.Exists(path))
            throw new FileNotFoundException("The add-on must be a readable local package.");
        using IFileSystem pfs = PartitionFileSystemUtils.OpenApplicationFileSystem(path, _virtualFileSystem);
        _virtualFileSystem.ImportTickets(pfs);
        if (operation == 4)
        {
            bool matched = false;
            foreach (var pair in pfs.GetContentData(ContentMetaType.Patch, _virtualFileSystem, IntegrityCheckLevel.None))
            {
                if ((pair.Key & ~0x1FFFUL) != titleId) continue;
                var patch = pair.Value.GetNcaByType(_virtualFileSystem.KeySet, LibHac.Ncm.ContentType.Program, 0);
                var control = pair.Value.GetNcaByType(_virtualFileSystem.KeySet, LibHac.Ncm.ContentType.Control, 0);
                if (patch != null && control != null) { matched = true; break; }
            }
            if (!matched) throw new InvalidDataException("This package contains no compatible update for the selected game, or its keys are missing.");
            json.WriteString("kind", "update");
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
}
