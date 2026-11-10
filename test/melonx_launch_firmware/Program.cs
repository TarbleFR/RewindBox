using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using LibHac.Common;
using LibHac.Common.Keys;
using LibHac.Fs;
using LibHac.Fs.Fsa;
using LibHac.FsSystem;
using LibHac.Ncm;
using LibHac.Tools.FsSystem;
using LibHac.Tools.FsSystem.NcaUtils;
using Ryujinx.Common;
using Ryujinx.Common.Configuration;
using Ryujinx.HLE.FileSystem;
using Ryujinx.Library;
using Path = System.IO.Path;

internal static class Program
{
#if ADAPTED
    private const int ExpectedScans = 1;
#else
    private const int ExpectedScans = 2;
#endif
    private static int _checks;
    private static readonly List<string> Trace = new();
    private static void Check(bool value, string message)
    {
        if (!value) throw new Exception(message);
        _checks++;
    }

    private static JsonDocument Launch(string path, string expectedVersion)
    {
        int before = FirmwareProbe.Nca.MarkerReads;
        int accounts = Library.AccountRefreshes;
        int reloads = Library.KeyReloads;
        var result = JsonDocument.Parse(Library.Preflight(path));
        Check(FirmwareProbe.Nca.MarkerReads - before == ExpectedScans, "The preflight did not perform the expected number of real directory scans.");
        Check(result.RootElement.GetProperty("firmware").GetString() == expectedVersion, "Firmware version changed.");
        Check(result.RootElement.GetProperty("preflightOnly").GetBoolean(), "Preflight result lost.");
        Check(Library.AccountRefreshes == accounts + 1 && Library.KeyReloads == reloads + 1, "Successful preflight must refresh keys and account.");
        Trace.Add("version:" + expectedVersion);
        return result;
    }

    private static void Rejected<T>(string path, string stage, string code, string message, int scans) where T : Exception
    {
        int before = FirmwareProbe.Nca.MarkerReads;
        int accounts = Library.AccountRefreshes;
        try { Library.Preflight(path); throw new Exception("Accepted invalid fixture."); }
        catch (T error)
        {
            Check(error.Message == message, "Original error detail was not preserved: " + error.Message);
            Check(EmbeddedLaunchDiagnostics.Stage == stage && EmbeddedLaunchDiagnostics.ErrorCode == code, "Original refusal stage/code changed.");
            Check(Library.AccountRefreshes == accounts, "Rejected preflight refreshed the account.");
            Check(FirmwareProbe.Nca.MarkerReads - before == scans, "Wrong scan count on failure.");
            Trace.Add(typeof(T).Name + ":" + stage + ":" + code + ":" + error.Message);
        }
    }

    public static void Main()
    {
        string root = Path.Combine(Path.GetTempPath(), "melonx-firmware-fixture-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        AppDataManager.BaseDirPath = root;
        FirmwareProbe.Nca.RomFs = Path.Combine(root, "synthetic-romfs");
        Directory.CreateDirectory(FirmwareProbe.Nca.RomFs);
        string system = Path.Combine(root, "system");
        Directory.CreateDirectory(system);
        string keys = Path.Combine(system, "prod.keys");
        const string SyntheticKey = "header_key = 0000000000000000000000000000000000000000000000000000000000000000";
        File.WriteAllText(keys, SyntheticKey);
        string game = Path.Combine(root, "synthetic.nsp");
        File.WriteAllBytes(game, Encoding.ASCII.GetBytes("PFS0"));
        string homebrew = Path.Combine(root, "synthetic.nro");
        byte[] nro = new byte[0x80];
        Encoding.ASCII.GetBytes("NRO0").CopyTo(nro, 0x10);
        BitConverter.GetBytes(0x80).CopyTo(nro, 0x18);
        File.WriteAllBytes(homebrew, nro);
        ContentPath.TryGetRealPath(ContentPath.SystemContent, out string content);
        Directory.CreateDirectory(content);
        string marker = Path.Combine(content, "marker.nca");
        string version = Path.Combine(content, "version-before.nca");
        void WriteNca(string path, ulong id, NcaContentType type)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(path));
            byte[] data = new byte[16];
            BitConverter.GetBytes(id).CopyTo(data, 0);
            data[8] = (byte)type;
            File.WriteAllBytes(path, data);
        }
        void WriteVersion(string value)
        {
            byte[] data = new byte[0x100];
            data[0] = 22;
            Encoding.ASCII.GetBytes(value).CopyTo(data, 0x68);
            File.WriteAllBytes(Path.Combine(FirmwareProbe.Nca.RomFs, "file"), data);
        }
        WriteNca(marker, FirmwareProbe.Nca.MarkerId, NcaContentType.Program);
        WriteNca(version, FirmwareProbe.Nca.VersionId, NcaContentType.Data);
        WriteVersion("22.5.0");
        try
        {
            int initialReads = FirmwareProbe.Nca.MarkerReads;
            using (var result = Launch(game, "22.5.0"))
            {
                Check(result.RootElement.GetProperty("titleId").GetString() == "01006a800016e000", "Program identity changed.");
                Check(FirmwareProbe.Nca.ProgramProbes == 2, "Code and data preflight probes changed.");
                Check(Library.HasVersionEntry, "Fresh content index was not populated.");
            }
            int freshScans = FirmwareProbe.Nca.MarkerReads - initialReads;
            using (Launch(game, "22.5.0")) { }

            // Keep the same ContentManager, remove the old path, add a new path
            // and change the actual version bytes. A stale cached index fails.
            File.Delete(version);
            version = Path.Combine(content, "version-after.nca");
            WriteNca(version, FirmwareProbe.Nca.VersionId, NcaContentType.Data);
            WriteVersion("23.0.0");
            using (Launch(game, "23.0.0")) { }

            File.Delete(version);
            Rejected<InvalidDataException>(game, "firmware", "firmwareMissing", "No readable personal firmware installation was recognized.", ExpectedScans);
            Check(!Library.HasVersionEntry, "Deleted firmware remained in the index.");
            using (Launch(homebrew, "")) { }

            // Registered-directory NCA layout follows the other real scan arm.
            version = Path.Combine(content, "registered", "version.nca", "00");
            WriteNca(version, FirmwareProbe.Nca.VersionId, NcaContentType.Data);
            WriteVersion("24.1.2");
            using (Launch(game, "24.1.2")) { }

            File.Delete(keys);
            Rejected<InvalidDataException>(game, "keys", "keysMissing", "Import your personal prod.keys into Documents/MeloNX/system.", 0);
            File.WriteAllText(keys, "invalid fixture");
            Rejected<InvalidDataException>(game, "keys", "keysInvalid", "keySyntax", 0);
            File.WriteAllText(keys, SyntheticKey);
            FirmwareProbe.Nca.RejectProgram = true;
            Rejected<InvalidDataException>(game, "contentPreflight", "", "Synthetic program integrity failure.", 0);
            FirmwareProbe.Nca.RejectProgram = false;

            FirmwareProbe.Nca.RejectHeader = true;
            Rejected<InvalidDataException>(game, "firmware", "", "Synthetic firmware header failure.", 1);
            FirmwareProbe.Nca.RejectHeader = false;
            FirmwareProbe.Nca.RejectRomFs = true;
            Rejected<InvalidDataException>(game, "firmware", "", "Synthetic firmware integrity failure.", ExpectedScans);
            FirmwareProbe.Nca.RejectRomFs = false;
            File.WriteAllBytes(Path.Combine(FirmwareProbe.Nca.RomFs, "file"), Array.Empty<byte>());
            Rejected<EndOfStreamException>(game, "firmware", "", "Unable to read beyond the end of the stream.", ExpectedScans);
            File.Delete(Path.Combine(FirmwareProbe.Nca.RomFs, "file"));
            Rejected<InvalidDataException>(game, "firmware", "firmwareMissing", "No readable personal firmware installation was recognized.", ExpectedScans);
            WriteVersion("25.0.0");
            using (Launch(game, "25.0.0")) { }

            // Calling the real version getter directly still refreshes once.
            int beforeDirect = FirmwareProbe.Nca.MarkerReads;
            WriteVersion("26.0.0");
            Check(Library.VersionDirect() == "26.0.0", "Version getter retained stale data.");
            Check(FirmwareProbe.Nca.MarkerReads - beforeDirect == 1, "Version getter no longer owns exactly one refresh.");
            Trace.Add("direct:26.0.0");
            Console.WriteLine(JsonSerializer.Serialize(new {
                checks = _checks, freshLaunchScans = freshScans,
                semanticTrace = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\n", Trace)))),
                scenarios = Trace.Count, realDirectoryScan = true, realLibHacLocalFileSystem = true,
                realSystemVersionParsing = true, syntheticNcaDecryption = true
            }));
        }
        finally { Directory.Delete(root, true); }
    }
}

namespace FirmwareProbe
{
    // The sole content parser double: synthetic 16-byte headers replace
    // encrypted NCAs. LibHac IStorage, LocalFileSystem and file I/O stay real.
    public sealed class Nca
    {
        public const ulong MarkerId = 0x0100000000000816;
        public const ulong VersionId = 0x0100000000000809;
        public static int MarkerReads, ProgramProbes;
        public static bool RejectHeader, RejectRomFs, RejectProgram;
        public static string RomFs;
        public readonly record struct HeaderData(ulong TitleId, NcaContentType ContentType);
        public HeaderData Header { get; }
        public Nca(KeySet keys, IStorage storage)
        {
            Span<byte> bytes = stackalloc byte[16];
            storage.Read(0, bytes).ThrowIfFailure();
            Header = new(BitConverter.ToUInt64(bytes), (NcaContentType)bytes[8]);
            if (Header.TitleId == MarkerId)
            {
                MarkerReads++;
                if (RejectHeader) throw new InvalidDataException("Synthetic firmware header failure.");
            }
        }
        private Nca() { Header = new(0x01006A800016E000, NcaContentType.Program); }
        public static Nca Program() => new();
        public bool SectionExists(NcaSectionType section) => true;
        public IStorage OpenStorage(NcaSectionType section, IntegrityCheckLevel level)
        {
            if (level != IntegrityCheckLevel.ErrorOnInvalid) throw new Exception("Program integrity check weakened.");
            ProgramProbes++;
            if (RejectProgram) throw new InvalidDataException("Synthetic program integrity failure.");
            return new MemoryStream(new byte[] { 1 }).AsStorage();
        }
        public IFileSystem OpenFileSystem(NcaSectionType section, IntegrityCheckLevel level)
        {
            if (section != NcaSectionType.Data || level != IntegrityCheckLevel.ErrorOnInvalid) throw new Exception("Firmware integrity check weakened.");
            if (RejectRomFs) throw new InvalidDataException("Synthetic firmware integrity failure.");
            return new LocalFileSystem(RomFs);
        }
    }
}

namespace Ryujinx.Common.Configuration { public static class AppDataManager { public static string BaseDirPath; } }
namespace Ryujinx.HLE.FileSystem
{
    public sealed class VirtualFileSystem
    {
        public const string SystemNandPath = "nand/system", UserNandPath = "nand/user";
        public KeySet KeySet { get; } = KeySet.CreateDefaultKeySet();
        public int Reloads;
        public void ReloadKeySet() => Reloads++;
        public static string GetSdCardPath() => Path.Combine(AppDataManager.BaseDirPath, "sdcard");
        public static string SwitchPathToSystemPath(string path)
        {
            int end = path.IndexOf(":/", StringComparison.Ordinal);
            if (end < 0 || !ContentPath.TryGetRealPath(path[..end], out string root)) throw new InvalidDataException("Unknown fixture content path.");
            return Path.Combine(root, path[(end + 2)..]);
        }
    }
    public partial class ContentManager
    {
        private const ulong SystemVersionTitleId = FirmwareProbe.Nca.VersionId;
        private readonly System.Threading.Lock _lock = new();
        private readonly VirtualFileSystem _virtualFileSystem;
        private Dictionary<StorageId, LinkedList<LocationEntry>> _locationEntries = new();
        private SortedDictionary<(ulong, NcaContentType), string> _contentDictionary = new();
        public ContentManager(VirtualFileSystem files) { _virtualFileSystem = files; }
        public bool HasVersionEntry => _contentDictionary.ContainsKey((SystemVersionTitleId, NcaContentType.Data));
    }
    // LoadEntries' optional session-service branch is unchanged and unused by
    // preflight. These endpoints reject accidental invocation by the fixture.
    public sealed class Switch { public SessionSystem System => throw new Exception("Unexpected session creation."); }
    public sealed class SessionSystem { public FontManager SharedFontManager => throw new Exception("Unexpected font service."); }
    public sealed class FontManager { public void Initialize() => throw new Exception("Unexpected font initialization."); }
    public sealed class TimeManager
    {
        public static TimeManager Instance { get; } = new();
        public void InitializeTimeZone(Switch device) => throw new Exception("Unexpected time service.");
    }
    public sealed class BuiltInCertificateManager
    {
        public static BuiltInCertificateManager Instance { get; } = new();
        public void Initialize(Switch device) => throw new Exception("Unexpected certificate service.");
    }
}
namespace Ryujinx.HLE.Utilities
{
    public static class PartitionFileSystemUtils
    {
        public static IFileSystem OpenApplicationFileSystem(string path, VirtualFileSystem files) => new LocalFileSystem(Path.GetDirectoryName(path));
    }
}
namespace Ryujinx.HLE.Loaders.Processes.Extensions
{
    public sealed class FixtureContent
    {
        public FirmwareProbe.Nca GetNcaByType(KeySet keys, LibHac.Ncm.ContentType type, int index) => FirmwareProbe.Nca.Program();
    }
    public static class FixtureContents
    {
        public static Dictionary<ulong, FixtureContent> GetContentData(this IFileSystem fs, ContentMetaType type, VirtualFileSystem files, IntegrityCheckLevel level)
            => new() { [0x01006A800016E000] = new FixtureContent() };
    }
}
namespace Ryujinx.Library
{
    internal sealed class Account { public int Refreshes; public void Refresh() => Refreshes++; }
    partial class Library
    {
        private static readonly VirtualFileSystem _virtualFileSystem = new();
        private static readonly ContentManager _contentManager = new(_virtualFileSystem);
        private static readonly Account _accountManager = new();
        private static ulong EmbeddedJitArenaHint;
        private static ulong EmbeddedJitArenaFor(ulong titleId, FirmwareProbe.Nca program) => 0;
        public static int AccountRefreshes => _accountManager.Refreshes;
        public static int KeyReloads => _virtualFileSystem.Reloads;
        public static bool HasVersionEntry => _contentManager.HasVersionEntry;
        public static string VersionDirect() => _contentManager.GetCurrentFirmwareVersion()?.VersionString;
        public static string Preflight(string path)
        {
            using var memory = new MemoryStream();
            using (var json = new Utf8JsonWriter(memory))
            {
                json.WriteStartObject();
                EmbeddedLaunchPreflight(path, json);
                json.WriteEndObject();
            }
            return Encoding.UTF8.GetString(memory.ToArray());
        }
    }
}
