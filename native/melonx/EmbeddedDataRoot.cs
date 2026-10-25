using System;
using System.IO;

namespace Ryujinx.Library;

// Shared by the managed bootstrap and its executable host tests.
internal static class EmbeddedDataRoot
{
    internal static string Resolve(string documents, string requested)
    {
        if (string.IsNullOrWhiteSpace(documents) || string.IsNullOrWhiteSpace(requested) ||
            !Path.IsPathFullyQualified(documents) || !Path.IsPathFullyQualified(requested))
            throw new ArgumentException("An absolute embedded data directory is required.");

        string expected = Path.GetFullPath(Path.Combine(documents, "MeloNX"));
        string actual = Path.TrimEndingDirectorySeparator(Path.GetFullPath(requested));
        if (!string.Equals(expected, actual, StringComparison.Ordinal))
            throw new ArgumentException("The embedded data directory must be Documents/MeloNX.");

        if (new DirectoryInfo(actual).LinkTarget != null)
            throw new ArgumentException("The embedded data directory cannot be a symbolic link.");

        return actual;
    }
}
