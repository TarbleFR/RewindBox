using LibHac.Common;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using Ryujinx.Common.Logging;
using Ryujinx.HLE.HOS;
using Ryujinx.HLE.Loaders.Executables;
using System;
using System.Collections.Generic;

namespace Ryujinx.HLE
{
    /// <summary>
    /// RewindBox (adapt_cheat_report): which build the cheats of a launch were for. A cheat file is named after the first
    /// eight bytes of the module id (build id) of the executable it patches, as 16 hex digits (ModLoader.NormalizeCheatId,
    /// Cheat.CheatIdSize); ModLoader.LoadCheats skips, with a Warning per file, every cheat no executable of the process
    /// matches, and the journal's filter redacts the full 64-digit build ids it prints. A cheat catalogue made for another
    /// version of a game (a base game without its update, or the other way round) therefore installs nothing while every
    /// file looks in place.
    ///
    /// This class gives the main executable's build id in the cheat files' own form, for the host's metadata
    /// (content operation 0) and update inspection (operation 4), and writes one Warning line per process after LoadCheats:
    /// the title, the main build id, the cheats found, installed, enabled and skipped for another build id, and the
    /// distinct build ids of the skipped files. 16 hex digits are below the journal filter's 32-digit redaction and the
    /// line starts with no key=value, so it reaches the Core journal as written. Nothing is changed in what is installed.
    /// </summary>
    public static class EmbeddedCheatReport
    {
        public const int IdLength = 16; // ModLoader.Cheat.CheatIdSize
        public const int MaxSkippedIds = 8;

        private sealed class Stats
        {
            public ulong Application;
            public int Found;
            public int Skipped;
            public readonly SortedSet<string> SkippedIds = new(StringComparer.Ordinal);
        }

        private static readonly object _gate = new();
        private static Stats _current;

        /// <summary>The first eight bytes of a module id as 16 upper-case hex digits (a cheat file's name), or null.</summary>
        public static string Normalize(ReadOnlySpan<byte> moduleId) => moduleId.Length < IdLength / 2 ? null : Convert.ToHexString(moduleId[..(IdLength / 2)]);

        /// <summary>The cheat form of a build id string (ModLoader.NormalizeCheatId).</summary>
        public static string Normalize(string buildId) =>
            string.IsNullOrEmpty(buildId) ? null : buildId[..Math.Min(IdLength, buildId.Length)].ToUpperInvariant();

        /// <summary>
        /// The build id of the "main" NSO of an ExeFS, read from its header (magic NSO0, module id at 0x40), in the cheat
        /// files' form; null when the file is missing or unreadable. Never throws.
        /// </summary>
        public static string MainBuildId(IFileSystem exeFs)
        {
            try
            {
                if (exeFs == null) return null;
                using UniqueRef<IFile> file = new();
                if (exeFs.OpenFile(ref file.Ref, "/main".ToU8Span(), OpenMode.Read).IsFailure()) return null;
                Span<byte> header = stackalloc byte[0x60];
                if (file.Get.Read(out long read, 0, header, ReadOption.None).IsFailure() || read < header.Length) return null;
                if (header[0] != (byte)'N' || header[1] != (byte)'S' || header[2] != (byte)'O' || header[3] != (byte)'0') return null;
                return Normalize(header.Slice(0x40, 0x20));
            }
            catch (Exception)
            {
                return null;
            }
        }

        /// <summary>The main executable's build id of a process being loaded (the NSO named "main"), or null.</summary>
        internal static string MainOf(ReadOnlySpan<IExecutable> executables)
        {
            foreach (IExecutable executable in executables)
            {
                if (executable is NsoExecutable nso && nso.Name == "main") return Normalize(nso.BuildId);
            }

            return null;
        }

        /// <summary>LoadCheats begins for an application (its executables are known).</summary>
        public static void Begin(ulong application)
        {
            lock (_gate) _current = new Stats { Application = application };
        }

        /// <summary>The cheats the mod loader found for the application.</summary>
        public static void Found(int count)
        {
            lock (_gate) if (_current != null) _current.Found = count;
        }

        /// <summary>A cheat file skipped because no executable of the process has its build id.</summary>
        public static void Skipped(string cheatId)
        {
            lock (_gate)
            {
                if (_current == null) return;
                _current.Skipped++;
                if (!string.IsNullOrEmpty(cheatId) && _current.SkippedIds.Count < MaxSkippedIds) _current.SkippedIds.Add(cheatId);
            }
        }

        /// <summary>
        /// The process's line, after LoadCheats: its build ids decide which installed cheats are counted (the tamper machine
        /// keys them "{build id}-{name}"). Returns the line (tests).
        /// </summary>
        public static string Write(ulong application, string mainBuildId, IEnumerable<string> processBuildIds, TamperMachine tamperMachine)
        {
            Stats stats;
            lock (_gate)
            {
                stats = _current != null && _current.Application == application ? _current : new Stats { Application = application };
                _current = null;
            }

            List<string> ids = [];
            foreach (string id in processBuildIds ?? [])
            {
                string normalized = Normalize(id);
                if (!string.IsNullOrEmpty(normalized) && normalized.Trim('0').Length > 0) ids.Add(normalized);
            }

            (int installed, int enabled) = tamperMachine?.CheatCounts(ids) ?? (0, 0);
            string skippedIds = stats.SkippedIds.Count == 0 ? "none" : string.Join(", ", stats.SkippedIds);
            string line = $"Cheats of {application:x16}: main build id {mainBuildId ?? "unknown"}; found {stats.Found}, installed {installed}, " +
                          $"enabled {enabled}, skipped for another build id {stats.Skipped} ({skippedIds}) (adapt_cheat_report)";
            Logger.Warning?.Print(LogClass.ModLoader, line);
            return line;
        }
    }
}
