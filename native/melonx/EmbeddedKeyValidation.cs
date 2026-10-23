using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using LibHac.Common.Keys;

namespace Ryujinx.Library;

internal static class EmbeddedKeyValidation
{
    internal readonly record struct Result(int Recognized, int Ignored);
    internal static string ErrorCode(Exception error) => error is InvalidDataException &&
        error.Message is "keySyntax" or "keySize" or "keyConflict" or "keyNoSupported"
        ? error.Message : error is IOException or UnauthorizedAccessException ? "keyReadFailed" : "keyImportFailed";

    // Validate against the exact embedded LibHac schema without deriving keys,
    // mutating the live KeySet or passing secret values to a diagnostic logger.
    internal static Result Validate(string path)
    {
        var file = new FileInfo(path);
        string name = file.Name.ToLowerInvariant();
        if (!file.Exists || file.Length == 0 || file.Length > 4 * 1024 * 1024 ||
            (name != "prod.keys" && name != "title.keys" && name != "dev.keys" && name != "console.keys"))
            throw new InvalidDataException("keySyntax");
        var keys = KeySet.CreateDefaultKeySet();
        var schema = KeySet.CreateKeyInfoList();
        var seen = new Dictionary<string, string>(StringComparer.Ordinal);
        int recognized = 0, ignored = 0;
        foreach (string line in File.ReadLines(path))
        {
            string text = line.Trim();
            if (text.Length == 0 || text.StartsWith('#')) continue;
            // The actual LibHac reader accepts '=' and ',' and has a 2048-char
            // line buffer. Do not accept entries it would silently skip.
            string[] parts = text.Split(new[] { '=', ',' });
            if (parts.Length != 2 || text.Length >= 2048)
                throw new InvalidDataException("keySyntax");
            string key = parts[0].Trim().ToLowerInvariant();
            string value = parts[1].Trim().ToLowerInvariant();
            if (key.Length == 0 || key.Any(c => !(c is >= 'a' and <= 'z' or >= '0' and <= '9' or '_')) ||
                value.Length == 0 || value.Length % 2 != 0 || value.Any(c => !Uri.IsHexDigit(c)))
                throw new InvalidDataException("keySyntax");
            if (seen.TryGetValue(key, out string previous))
            {
                if (previous != value) throw new InvalidDataException("keyConflict");
                continue;
            }
            seen.Add(key, value);
            int expected = 0;
            if (name == "title.keys")
            {
                if (key.Length != 32 || key.Any(c => !Uri.IsHexDigit(c)))
                    throw new InvalidDataException("keySyntax");
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
            // Personal dumps can contain newer/console-only entries. LibHac
            // ReadMainKeys skips unmatched names; rejecting the entire dump here
            // prevented it from loading the supported entries beside them.
            if (expected == 0) { ignored++; continue; }
            if (value.Length != expected) throw new InvalidDataException("keySize");
            recognized++;
        }
        if (recognized == 0) throw new InvalidDataException("keyNoSupported");
        return new Result(recognized, ignored);
    }
}
