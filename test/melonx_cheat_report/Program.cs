// The cheat report (adapt_cheat_report) on the production Ryujinx.HLE assembly built from the final preparation: a cheats
// folder in the engine's own layout (mods/contents/<title>/cheats/<build id>.txt and enabled.txt) collected by the real
// ModLoader and installed by the real ModLoader.LoadCheats into the real TamperMachine for a process whose build ids match
// one file and not the others, then the report's Warning line: found / installed / enabled / skipped for another build
// id, the skipped files' distinct ids, the main build id. Also the main build id as the host's metadata reads it (an
// ExeFS "main" header) and as the loader picks it (the NSO named "main"). KProcess is left uninitialised (Pid only):
// cheats are compiled and installed, never executed against guest memory here (the tamper thread's run of a cheat on a
// process without memory throws and is caught by the machine, as during a game's start). Host .NET runtime on Linux, not
// an iPhone.
using MemoryStorage = LibHac.Fs.MemoryStorage;
using LibHac.FsSystem;
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Logging;
using Ryujinx.Common.Logging.Targets;
using Ryujinx.HLE;
using Ryujinx.HLE.HOS;
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Emit;
using System.Runtime.CompilerServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

static class Program
{
    static int checks;
    static readonly Dictionary<string, object> report = new();
    const ulong Smash = 0x01006A800016E000UL;
    const ulong Other = 0x0100000000010000UL;
    const BindingFlags Any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Static | BindingFlags.Instance;
    // The installed build: a 32-byte module id as the loader prints it (64 upper-case hex digits).
    const string Installed = "0123456789ABCDEF00112233445566778899AABBCCDDEEFF0011223344556677";
    const string Rtld = "AAAABBBBCCCCDDDD00000000000000000000000000000000000000000000000E";

    static void Check(bool condition, string message)
    {
        checks++;
        if (!condition) throw new Exception("FAILED: " + message);
    }

    sealed class Capture : ILogTarget
    {
        public readonly List<(LogLevel Level, string Message)> Lines = new();
        public string Name => "cheat-report-capture";
        public void Log(object sender, LogEventArgs args)
        {
            lock (Lines) Lines.Add((args.Level, args.Message));
        }
        public void Dispose() { }
    }

    static readonly Assembly Hle = typeof(TamperMachine).Assembly;

    static object Process(ulong pid)
    {
        Type type = Hle.GetType("Ryujinx.HLE.HOS.Kernel.Process.KProcess", true);
        object process = RuntimeHelpers.GetUninitializedObject(type);
        type.GetField("<Pid>k__BackingField", Any).SetValue(process, pid);
        return process;
    }

    static object TamperInfo(object process, string[] buildIds)
    {
        Type type = Hle.GetType("Ryujinx.HLE.HOS.Kernel.Process.ProcessTamperInfo", true);
        ulong[] addresses = buildIds.Select((_, i) => 0x8000000UL + (ulong)i * 0x100000UL).ToArray();
        return Activator.CreateInstance(type, Any, null, new object[] { process, buildIds, addresses, 0x10000000UL, 0x20000000UL, 0x8000000UL }, null);
    }

    static void LoadCheats(ModLoader loader, ulong application, object tamperInfo, TamperMachine machine) =>
        typeof(ModLoader).GetMethod("LoadCheats", Any).Invoke(loader, new[] { application, tamperInfo, machine });

    static (int Installed, int Enabled) Counts(TamperMachine machine, IEnumerable<string> ids) =>
        ((int, int))typeof(TamperMachine).GetMethod("CheatCounts", Any).Invoke(machine, new object[] { ids });

    static int Programs(TamperMachine machine) =>
        ((System.Collections.IDictionary)typeof(TamperMachine).GetField("_programDictionary", Any).GetValue(machine)).Count;

    // An uncompressed, unhashed NSO: header (magic NSO0, module id at 0x40) and three 0x10-byte segments.
    static byte[] Nso(byte[] moduleId)
    {
        byte[] nso = new byte[0x130];
        Encoding.ASCII.GetBytes("NSO0").CopyTo(nso, 0);
        void Segment(int at, uint file, uint memory) { BitConverter.GetBytes(file).CopyTo(nso, at); BitConverter.GetBytes(memory).CopyTo(nso, at + 4); BitConverter.GetBytes(0x10u).CopyTo(nso, at + 8); }
        Segment(0x10, 0x100, 0);
        Segment(0x20, 0x110, 0x1000);
        Segment(0x30, 0x120, 0x2000);
        moduleId.CopyTo(nso, 0x40);
        return nso;
    }

    static byte[] Bytes(string hex) => Convert.FromHexString(hex);

    static object Executable(byte[] nso, string name)
    {
        Type type = Hle.GetType("Ryujinx.HLE.Loaders.Executables.NsoExecutable", true);
        return Activator.CreateInstance(type, Any, null, new object[] { new MemoryStorage(nso), name }, null);
    }

    // EmbeddedCheatReport.MainOf(ReadOnlySpan<IExecutable>) is internal and takes a span of an internal interface: a
    // visibility-skipping thunk builds the span from an array.
    static Func<object[], string> MainOf()
    {
        Type executable = Hle.GetType("Ryujinx.HLE.Loaders.Executables.IExecutable", true);
        Type array = executable.MakeArrayType();
        Type span = typeof(ReadOnlySpan<>).MakeGenericType(executable);
        MethodInfo method = typeof(EmbeddedCheatReport).GetMethod("MainOf", Any);
        DynamicMethod thunk = new("MainOfThunk", typeof(string), new[] { typeof(object[]) }, typeof(Program).Module, true);
        ILGenerator il = thunk.GetILGenerator();
        il.Emit(OpCodes.Ldarg_0);
        il.Emit(OpCodes.Call, typeof(Program).GetMethod(nameof(Cast), Any).MakeGenericMethod(executable));
        il.Emit(OpCodes.Newobj, span.GetConstructor(new[] { array }));
        il.Emit(OpCodes.Call, method);
        il.Emit(OpCodes.Ret);
        return thunk.CreateDelegate<Func<object[], string>>();
    }

    static T[] Cast<T>(object[] values) => values.Cast<T>().ToArray();

    static void Write(string path, string text)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(path));
        File.WriteAllText(path, text);
    }

    static int Main(string[] args)
    {
        string work = Path.GetFullPath(args[0]);
        try
        {
            Logger.RemoveTarget("console");
            Capture capture = new();
            Logger.AddTarget(capture);
            AppDataManager.Initialize(work);
            Check(AppDataManager.BaseDirPath == work, "the engine's data folder is the fixture's");

            // The engine's layout: one file for the installed build (lower-case name, two cheats, one enabled), two for
            // other builds (three cheats), enabled.txt in the title's cheats folder.
            string cheats = Path.Combine(ModLoader.GetModsBasePath(), "contents", $"{Smash:x16}", "cheats");
            Write(Path.Combine(cheats, "0123456789abcdef.txt"),
                  "[Infinite jumps]\n04000000 00001000 00000063\n\n[Max damage]\n04000000 00002000 00000064\n");
            Write(Path.Combine(cheats, "FEDCBA9876543210.txt"),
                  "[Version 13 moon jump]\n04000000 00003000 00000001\n[Version 13 timer]\n04000000 00004000 00000002\n");
            Write(Path.Combine(cheats, "1111222233334444.txt"), "[Base game only]\n04000000 00005000 00000003\n");
            Write(Path.Combine(cheats, "enabled.txt"), "0123456789ABCDEF-<Infinite jumps Cheat>\n");

            ModLoader loader = new();
            loader.CollectMods(new[] { Smash }, ModLoader.GetModsBasePath());

            // 1. The process runs the build of one file: two installed, one enabled (enabled.txt), three skipped.
            TamperMachine machine = new();
            string[] buildIds = { Rtld, Installed, string.Empty };
            LoadCheats(loader, Smash, TamperInfo(Process(0x51), buildIds), machine);
            Check(Programs(machine) == 2, "LoadCheats installs the two cheats of the matching file: " + Programs(machine));
            string line = EmbeddedCheatReport.Write(Smash, "0123456789ABCDEF", buildIds, machine);
            const string expected = "Cheats of 01006a800016e000: main build id 0123456789ABCDEF; found 5, installed 2, enabled 1, skipped for another build id 3 " +
                                    "(1111222233334444, FEDCBA9876543210) (adapt_cheat_report)";
            Check(line == expected, "the line of a launch with one matching file: " + line);
            (LogLevel Level, string Message) logged;
            lock (capture.Lines) logged = capture.Lines.LastOrDefault(l => l.Message.Contains("(adapt_cheat_report)"));
            Check(logged.Level == LogLevel.Warning && logged.Message.StartsWith("ModLoader ") && logged.Message.EndsWith(expected),
                  "the line is a ModLoader Warning: " + logged.Message);
            int skippedWarnings;
            lock (capture.Lines) skippedWarnings = capture.Lines.Count(l => l.Level == LogLevel.Warning && l.Message.Contains("Skipping cheat"));
            Check(skippedWarnings == 3, "the loader's own Warning per skipped cheat is unchanged: " + skippedWarnings);
            Check(Counts(machine, new[] { "0123456789ABCDEF" }) == (2, 1) && Counts(machine, new[] { "0123456789abcdef" }) == (2, 1),
                  "the machine's counts for the installed build (any case)");
            Check(Counts(machine, new[] { "FEDCBA9876543210" }) == (0, 0) && Counts(machine, Array.Empty<string>()) == (0, 0),
                  "no count for a build with nothing installed");
            report["matching"] = line;

            // 2. The catalogue is for another version: nothing installed, every cheat skipped, every id listed.
            TamperMachine other = new();
            string[] otherBuild = { "9999888877776666" + new string('0', 48) };
            LoadCheats(loader, Smash, TamperInfo(Process(0x52), otherBuild), other);
            line = EmbeddedCheatReport.Write(Smash, "9999888877776666", otherBuild, other);
            Check(Programs(other) == 0, "nothing installed when no file matches");
            Check(line == "Cheats of 01006a800016e000: main build id 9999888877776666; found 5, installed 0, enabled 0, skipped for another build id 5 " +
                          "(0123456789ABCDEF, 1111222233334444, FEDCBA9876543210) (adapt_cheat_report)", "the line of a launch with no matching file: " + line);
            report["noneMatching"] = line;

            // 3. The cheats of another build installed by an earlier process are not counted for this one.
            line = EmbeddedCheatReport.Write(Smash, "9999888877776666", otherBuild, machine);
            Check(line.Contains("found 0, installed 0, enabled 0, skipped for another build id 0 (none)"),
                  "a line without its LoadCheats counts nothing of an earlier process: " + line);

            // 4. A title without cheats: LoadCheats returns early, the line still says so.
            TamperMachine empty = new();
            loader.CollectMods(new[] { Other }, ModLoader.GetModsBasePath());
            LoadCheats(loader, Other, TamperInfo(Process(0x53), new[] { Installed }), empty);
            line = EmbeddedCheatReport.Write(Other, null, new[] { Installed }, empty);
            Check(line == "Cheats of 0100000000010000: main build id unknown; found 0, installed 0, enabled 0, skipped for another build id 0 (none) (adapt_cheat_report)",
                  "the line of a title without cheats: " + line);
            report["withoutCheats"] = line;

            // 5. Without enabled.txt every installed cheat is enabled (the engine's default); a kernel process gets none.
            File.Delete(Path.Combine(cheats, "enabled.txt"));
            loader.CollectMods(new[] { Smash }, ModLoader.GetModsBasePath());
            TamperMachine all = new();
            LoadCheats(loader, Smash, TamperInfo(Process(0x54), new[] { Installed }), all);
            line = EmbeddedCheatReport.Write(Smash, "0123456789ABCDEF", new[] { Installed }, all);
            Check(line.Contains("found 5, installed 2, enabled 2, skipped for another build id 3"), "without enabled.txt all installed cheats are enabled: " + line);
            TamperMachine kernel = new();
            LoadCheats(loader, Smash, TamperInfo(Process(0x10), new[] { Installed }), kernel);
            line = EmbeddedCheatReport.Write(Smash, "0123456789ABCDEF", new[] { Installed }, kernel);
            Check(line.Contains("found 5, installed 0, enabled 0, skipped for another build id 3"), "a kernel process gets no cheat and the line says so: " + line);
            Check(EmbeddedCheatReport.Write(Smash, null, null, null).Contains("installed 0, enabled 0"), "no tamper machine, no build ids: zero, no exception");

            // 6. The skipped ids are bounded.
            EmbeddedCheatReport.Begin(Smash);
            for (int i = 0; i < 20; i++) EmbeddedCheatReport.Skipped($"{i:X16}");
            line = EmbeddedCheatReport.Write(Smash, null, null, null);
            Check(line.Contains("skipped for another build id 20 (") && Regex.Matches(line, "[0-9A-F]{16}").Count == EmbeddedCheatReport.MaxSkippedIds,
                  "the count is exact and at most MaxSkippedIds ids are listed: " + line);

            // 7. The forms of a build id.
            Check(EmbeddedCheatReport.Normalize(Installed.ToLowerInvariant()) == "0123456789ABCDEF" && EmbeddedCheatReport.Normalize("abc") == "ABC" &&
                  EmbeddedCheatReport.Normalize((string)null) == null && EmbeddedCheatReport.Normalize(string.Empty) == null,
                  "a build id string in the cheat files' form");
            Check(EmbeddedCheatReport.Normalize(Bytes(Installed)) == "0123456789ABCDEF" && EmbeddedCheatReport.Normalize(new byte[7]) == null,
                  "a module id in the cheat files' form");

            // 8. The main build id of an ExeFS (the host's metadata) and of the loaded executables (the loader).
            byte[] mainNso = Nso(Bytes(Installed));
            string exefs = Path.Combine(work, "exefs");
            Write(Path.Combine(exefs, "main"), string.Empty);
            File.WriteAllBytes(Path.Combine(exefs, "main"), mainNso);
            File.WriteAllBytes(Path.Combine(exefs, "rtld"), Nso(Bytes(Rtld)));
            Check(EmbeddedCheatReport.MainBuildId(new LocalFileSystem(exefs)) == "0123456789ABCDEF", "the ExeFS main NSO's build id");
            string missing = Path.Combine(work, "exefs-missing");
            Directory.CreateDirectory(missing);
            Check(EmbeddedCheatReport.MainBuildId(new LocalFileSystem(missing)) == null, "no main NSO: null");
            string badMagic = Path.Combine(work, "exefs-magic");
            byte[] notNso = (byte[])mainNso.Clone();
            notNso[3] = (byte)'1';
            Write(Path.Combine(badMagic, "main"), string.Empty);
            File.WriteAllBytes(Path.Combine(badMagic, "main"), notNso);
            Check(EmbeddedCheatReport.MainBuildId(new LocalFileSystem(badMagic)) == null, "not an NSO: null");
            string shortFile = Path.Combine(work, "exefs-short");
            Write(Path.Combine(shortFile, "main"), string.Empty);
            File.WriteAllBytes(Path.Combine(shortFile, "main"), mainNso[..0x50]);
            Check(EmbeddedCheatReport.MainBuildId(new LocalFileSystem(shortFile)) == null, "a truncated header: null");
            Check(EmbeddedCheatReport.MainBuildId(null) == null, "no ExeFS: null");

            Func<object[], string> mainOf = MainOf();
            object rtld = Executable(Nso(Bytes(Rtld)), "rtld");
            object main = Executable(mainNso, "main");
            object sdk = Executable(Nso(Bytes("5555666677778888" + new string('1', 48))), "sdk");
            Check(mainOf(new[] { rtld, main, sdk }) == "0123456789ABCDEF", "the loader's main executable is the NSO named main");
            Check(mainOf(new[] { rtld, sdk }) == null && mainOf(Array.Empty<object>()) == null, "no NSO named main: null");

            // 9. The journal filter (EmbeddedLaunchDiagnostics.Safe, the bridge's) keeps the line: no 32-digit hex run, no
            // leading key=value.
            foreach (string written in report.Values.Cast<string>())
            {
                Check(!Regex.IsMatch(written, @"\b[0-9a-f]{32,}\b", RegexOptions.IgnoreCase) && !Regex.IsMatch(written, @"^\s*[a-z0-9_]+\s*=", RegexOptions.IgnoreCase),
                      "the journal filter does not redact the line: " + written);
            }

            report["checks"] = checks;
            File.WriteAllText(Path.Combine(work, "report.json"), JsonSerializer.Serialize(report));
            Console.Out.Flush();
            Environment.Exit(0);
            return 0;
        }
        catch (Exception error)
        {
            File.WriteAllText(Path.Combine(work, "failure.txt"), error.ToString());
            Environment.Exit(1);
            return 1;
        }
    }
}
