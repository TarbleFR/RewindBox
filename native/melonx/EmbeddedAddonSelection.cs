using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;

namespace Ryujinx.Library;

// Only inspected CNMT/NCA title IDs are candidates; never infer a target
// from a filename. A global import must identify exactly one base game.
internal static class EmbeddedAddonSelection
{
    internal static ulong? RequestedTitle(string text, bool required)
    {
        if (string.IsNullOrEmpty(text) && !required) return null;
        if (text == null || text.Length != 16 ||
            !ulong.TryParse(text, NumberStyles.HexNumber, CultureInfo.InvariantCulture, out ulong title) ||
            (title & ~0x1FFFUL) == 0)
            throw new InvalidDataException("invalidContent");
        return title & ~0x1FFFUL;
    }

    internal static ulong SelectUpdate(IEnumerable<ulong> verifiedTitles, ulong? requested)
    {
        ulong? selected = null;
        foreach (ulong title in verifiedTitles)
        {
            ulong candidate = title & ~0x1FFFUL;
            if (candidate == 0 || (requested.HasValue && candidate != requested.Value)) continue;
            if (selected.HasValue && selected.Value != candidate)
                throw new InvalidDataException("ambiguousUpdate");
            selected = candidate;
        }
        return selected ?? throw new InvalidDataException(requested.HasValue ? "addonWrongGame" : "invalidUpdate");
    }

    internal static string ErrorCode(Exception error) => error.Message switch
    {
        "invalidContent" or "ambiguousUpdate" or "addonWrongGame" or "invalidUpdate" => error.Message,
        _ => "failed",
    };
}
