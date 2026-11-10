using System;
using System.IO;
using Path = System.IO.Path;
using System.Linq;
using System.Collections.Generic;
using System.Text;
using System.Text.Json;
using LibHac.Common;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.Tools.FsSystem;
using LibHac.Tools.FsSystem.NcaUtils;
using LibHac.Ncm;
using Ryujinx.Common.Configuration;
using Ryujinx.HLE.FileSystem;
using Ryujinx.HLE.Loaders.Processes.Extensions;
using Ryujinx.HLE.Utilities;

namespace Ryujinx.Library;

partial class Library
{
    private static IEnumerable<string> EmbeddedUnrealPaths(IFileSystem romfs)
    {
        var pending = new Queue<(string Path, int Depth)>();
        pending.Enqueue(("/", 0));
        int directories = 0, entries = 0;
        while (pending.Count != 0)
        {
            var next = pending.Dequeue();
            if (++directories > 512) throw new InvalidDataException("Unreal directory inspection exceeds its limit.");
            foreach (var entry in romfs.EnumerateEntries(next.Path, "*", SearchOptions.Default))
            {
                if (++entries > 16384) throw new InvalidDataException("Unreal path inspection exceeds its limit.");
                yield return entry.FullPath;
                if (entry.Type == DirectoryEntryType.Directory && next.Depth < 5)
                    pending.Enqueue((entry.FullPath, next.Depth + 1));
            }
        }
    }

    private static void EmbeddedInspectUnreal(string path, Utf8JsonWriter json)
    {
        if (path == null || !Path.IsPathFullyQualified(path) || !File.Exists(path))
            throw new FileNotFoundException("A local game is required for Unreal inspection.");
        _virtualFileSystem.ReloadKeySet();
        using IFileSystem package = PartitionFileSystemUtils.OpenApplicationFileSystem(path, _virtualFileSystem);
        foreach (var entry in package.GetContentData(ContentMetaType.Application, _virtualFileSystem, IntegrityCheckLevel.ErrorOnInvalid))
        {
            if (entry.Key != 0x0100F7E00C70E000UL) continue;
            var program = entry.Value.GetNcaByType(_virtualFileSystem.KeySet, LibHac.Ncm.ContentType.Program, 0);
            if (program == null || !program.CanOpenSection(NcaSectionType.Data)) continue;
            (var patch, _) = program.GetUpdateData(_virtualFileSystem, IntegrityCheckLevel.ErrorOnInvalid, 0, out _);
            bool patched = patch != null && patch.CanOpenSection(NcaSectionType.Data);
            using IFileSystem romfs = patched
                ? program.OpenFileSystemWithPatch(patch, NcaSectionType.Data, IntegrityCheckLevel.ErrorOnInvalid)
                : program.OpenFileSystem(NcaSectionType.Data, IntegrityCheckLevel.ErrorOnInvalid);
            string[] paths = EmbeddedUnrealPaths(romfs).ToArray();
            string project = EmbeddedUnrealProjectProbe.Detect(paths);
            json.WriteString("titleId", entry.Key.ToString("x16"));
            json.WriteString("project", project);
            json.WriteBoolean("available", project != null);
            json.WriteBoolean("selectedUpdateInspected", patched);
            json.WriteBoolean("configurationLoadVerified", false);
            json.WriteBoolean("cvarsVerified", false);
            if (project != null)
            {
                string canonical = "/" + project + "/Config/UserEngine.ini";
                string[] existing = paths.Where(p => p.Equals(canonical, StringComparison.OrdinalIgnoreCase)).ToArray();
                if (existing.Length > 1) throw new InvalidDataException("Ambiguous Unreal configuration path.");
                string configuration = existing.FirstOrDefault() ?? canonical;
                string original = "";
                if (existing.Length == 1)
                {
                    using var file = new UniqueRef<IFile>();
                    romfs.OpenFile(ref file.Ref, configuration.ToU8Span(), OpenMode.Read).ThrowIfFailure();
                    file.Get.GetSize(out long size).ThrowIfFailure();
                    if (size < 0 || size > 65536) throw new InvalidDataException("Unreal configuration exceeds its bounded copy.");
                    byte[] bytes = new byte[(int)size];
                    file.Get.Read(out long read, 0, bytes, ReadOption.None).ThrowIfFailure();
                    if (read != size) throw new InvalidDataException("Truncated Unreal configuration.");
                    original = new UTF8Encoding(false, true).GetString(bytes);
                }
                json.WriteString("configurationPath", configuration.TrimStart('/'));
                json.WriteString("baseConfiguration", original);
            }
            json.WriteStartArray("modRoots");
            foreach (string root in new[] { AppDataManager.GetModsPath(), AppDataManager.GetSdModsPath() })
                json.WriteStringValue(Path.Combine(root, "contents", entry.Key.ToString("x16")));
            json.WriteEndArray();
            return;
        }
        throw new InvalidDataException("Unreal experiments are restricted to the inspected Hogwarts base title.");
    }
}
