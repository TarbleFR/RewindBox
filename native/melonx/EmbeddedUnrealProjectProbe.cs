using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;

namespace Ryujinx.Library;

// Reads paths only. A .pak layout identifies an Unreal project, not the
// game's support for individual CVars or its configuration load order.
internal static class EmbeddedUnrealProjectProbe
{
    internal static string Detect(IEnumerable<string> paths)
    {
        string project = null;
        int visited = 0;
        foreach (string path in paths)
        {
            if (++visited > 16384) throw new InvalidDataException("Unreal inspection exceeds its bounded path inventory.");
            if (path == null || path.Length > 1024 || path.Contains('\\')) continue;
            string[] parts = path.TrimStart('/').Split('/');
            if (parts.Length < 4 || !parts[1].Equals("Content", StringComparison.OrdinalIgnoreCase) ||
                !parts[2].Equals("Paks", StringComparison.OrdinalIgnoreCase) ||
                !path.EndsWith(".pak", StringComparison.OrdinalIgnoreCase)) continue;
            string name = parts[0];
            if (name.Equals("Engine", StringComparison.OrdinalIgnoreCase) ||
                !Regex.IsMatch(name, "^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")) continue;
            foreach (string part in parts)
                if (part.Length == 0 || part == "." || part == "..") throw new InvalidDataException("Unsafe Unreal project path.");
            if (project != null && project != name) throw new InvalidDataException("Multiple Unreal projects require manual inspection.");
            project = name;
        }
        return project;
    }
}
