using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using LibHac.Common.Keys;

namespace Ryujinx.Library;

internal static class EmbeddedKeyValidation
{
    // Validate against the exact embedded LibHac schema without deriving keys,
    // mutating the live KeySet or passing secret values to a diagnostic logger.
    internal static void Validate(string path)
    {
        var file = new FileInfo(path);
        string name = file.Name.ToLowerInvariant();
        if (!file.Exists || file.Length == 0 || file.Length > 4 * 1024 * 1024 ||
            (name != "prod.keys" && name != "title.keys" && name != "dev.keys" && name != "console.keys"))
            throw new InvalidDataException("Invalid personal key file.");
        var keys = KeySet.CreateDefaultKeySet();
        var schema = KeySet.CreateKeyInfoList();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (string line in File.ReadLines(path))
        {
            string text = line.Trim();
            if (text.Length == 0 || text.StartsWith('#')) continue;
            string[] parts = text.Split('=');
            if (parts.Length != 2) throw new InvalidDataException("Invalid personal key syntax.");
            string key = parts[0].Trim().ToLowerInvariant();
            string value = parts[1].Trim();
            if (!seen.Add(key) || value.Length == 0 || value.Any(c => !Uri.IsHexDigit(c)))
                throw new InvalidDataException("Invalid or duplicate personal key entry.");
            int expected = 0;
            if (name == "title.keys")
            {
                if (key.Length != 32 || key.Any(c => !Uri.IsHexDigit(c)))
                    throw new InvalidDataException("Invalid personal rights identifier.");
                expected = 32;
            }
            else
            {
                foreach (var info in schema)
                {
                    if (info.Matches(key.AsSpan(), out int index, out _))
                    { expected = info.Getter(keys, index).Length * 2; break; }
                }
            }
            if (expected == 0 || value.Length != expected)
                throw new InvalidDataException("Unsupported key name or incorrect personal key size.");
        }
        if (seen.Count == 0) throw new InvalidDataException("Empty personal key file.");
    }
}
