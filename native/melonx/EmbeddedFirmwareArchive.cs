using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Text.RegularExpressions;
using System.Threading;

namespace Ryujinx.HLE.FileSystem;

public static class EmbeddedFirmwareProgress
{
    private static int _phase, _cancelled;
    public static void Begin() { Volatile.Write(ref _cancelled, 0); Set(1); }
    public static void Cancel() => Volatile.Write(ref _cancelled, 1);
    public static void Check() { if (Volatile.Read(ref _cancelled) != 0) throw new OperationCanceledException("cancelled"); }
    public static int Phase => Volatile.Read(ref _phase);
    public static void Set(int value) => Volatile.Write(ref _phase, value);
}

internal static class EmbeddedFirmwareArchive
{
    // One normalizer for both verification and extraction. An arbitrary parent
    // folder is accepted; Finder metadata never reaches the NCA parser.
    internal static string Name(ZipArchiveEntry entry)
    {
        string[] parts = entry.FullName.Replace('\\', '/').Split('/');
        if (parts.Any(part => part == ".." || part == ".")) throw new InvalidDataException("Unsafe archive path.");
        if (parts.Any(part => part == "__MACOSX" || part.StartsWith("._", StringComparison.Ordinal))) return null;
        string name = parts[^1] == "00" && parts.Length > 1 ? parts[^2] : parts[^1];
        name = name.ToLowerInvariant().Replace(".cnmt", "");
        return Regex.IsMatch(name, "^[a-f0-9]{32}\\.nca$") ? name : null;
    }
    internal static IEnumerable<ZipArchiveEntry> Entries(ZipArchive archive)
    {
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        long total = 0;
        foreach (var entry in archive.Entries)
        {
            EmbeddedFirmwareProgress.Check();
            string name = Name(entry);
            if (name == null) continue;
            if (!seen.Add(name)) throw new InvalidDataException("Duplicate firmware NCA.");
            total = checked(total + entry.Length);
            if (entry.Length <= 0 || entry.Length > 512L * 1024 * 1024 || total > 8L * 1024 * 1024 * 1024)
                throw new InvalidDataException("Firmware archive exceeds import limits.");
            yield return entry;
        }
    }
}
