// Scenarios for melonx_pipeline_cache_compact_test.py on the variant's real PipelineCacheManager.cs (control: the Core 727
// preparation; candidate: with adapt_pipeline_cache_compact; noCall / alwaysCompact: the candidate with one part changed,
// which must fail), over the content double of Double.cs in key mode: a cache created from data keeps each whole entry
// (64 KiB) at a sixteenth of its length (4 KiB), as MoltenVK with the fifth part of the RewindBox patch keeps a library
// under its cache key instead of its whole configuration. Isolated directories, never a player's cache.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using FixtureSupport;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

string variant = args[0];
var report = new Dictionary<string, object> { ["variant"] = variant };
string root = Path.Combine(Path.GetTempPath(), $"melonx-pipeline-cache-compact-{Environment.ProcessId}-{variant}");
const string Title = "0100F7E00C70E000";
const int WholeBytes = 64 * 1024, KeyBytes = 4 * 1024, Divisor = 16;
const uint Driver = 10402;
VulkanRenderer.PipelineCacheScope = () => Title;
bool candidate = typeof(PipelineCacheManager).GetMethod("CompactMainAfterLoad", BindingFlags.NonPublic | BindingFlags.Instance) != null;
if ((variant != "control") != candidate) throw new InvalidOperationException("variant and source disagree");

string MainPath(string dir) => Path.Combine(dir, "cache", "vulkan", $"pipeline-{0x106B:X8}-{0x1A2B3C4D:X8}-{Driver:X8}-{Title.ToLowerInvariant()}.vkpc");
string WorkerPath(string dir, int index) => Path.ChangeExtension(MainPath(dir), null) + $".worker{index}.vkpc";

void WriteCache(string path, IEnumerable<ulong> ids, int entryBytes)
{
    var vk = new Vk();
    var entries = ids.ToDictionary(id => id, _ => entryBytes);
    var data = new byte[CacheFormat.Size(entries)];
    CacheFormat.Write(data, entries, vk.Vendor, vk.DeviceId, vk.Uuid);
    Directory.CreateDirectory(Path.GetDirectoryName(path));
    File.WriteAllBytes(path, data);
}

(PipelineCacheManager Manager, Vk Vk, Lock MainLock) Open(string dir, bool failMainData = false, int loadMs = 0, bool wait = true)
{
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = dir;
    var vk = new Vk { KeyDivisor = Divisor, WholeBytes = WholeBytes, FailMainData = failMainData, SnapshotLoadMs = loadMs };
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    var properties = new PhysicalDeviceProperties { VendorID = vk.Vendor, DeviceID = vk.DeviceId, DriverVersion = Driver };
    unsafe { for (int i = 0; i < 16; i++) properties.PipelineCacheUuid[i] = vk.Uuid[i]; }
    var manager = new PipelineCacheManager(vk, new VulkanPhysicalDevice { PhysicalDeviceProperties = properties }, default, 2, mainLock);
    if (wait) WaitLoaded(manager);
    return (manager, vk, mainLock);
}

void WaitLoaded(PipelineCacheManager manager)
{
    var watch = Stopwatch.StartNew();
    while (manager.MainLoadPending && watch.ElapsedMilliseconds < 60_000) Thread.Sleep(2);
    if (manager.MainLoadPending) throw new TimeoutException("main load");
}

int Records(string stage) { lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Records) return Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.Count(r => r.StartsWith("pipelineCache " + stage + " ")); }
string LastRecord(string stage) { lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Records) return Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.LastOrDefault(r => r.StartsWith("pipelineCache " + stage + " ")) ?? ""; }

void AddToMain((PipelineCacheManager Manager, Vk Vk, Lock MainLock) l, IEnumerable<ulong> ids)
{
    foreach (ulong id in ids)
    {
        l.Manager.EnterMainCreation(l.MainLock, false, out PipelineCache target);
        try { l.Vk.Add(target, id, KeyBytes); }
        finally { l.Manager.ExitMainCreation(l.MainLock, target); }
        l.Manager.NotifyMainPipelineCreated();
    }
}

Dictionary<ulong, int> OnDisk(string dir)
{
    var vk = new Vk();
    return CacheFormat.ReadFile(MainPath(dir), vk.Vendor, vk.DeviceId, vk.Uuid, out _) ?? new Dictionary<ulong, int>();
}

long Length(string dir) => new FileInfo(MainPath(dir)).Length;
long KeySize(int entries) => CacheFormat.HeaderBytes + entries * (16L + KeyBytes) + 4;
long WholeSize(int entries) => CacheFormat.HeaderBytes + entries * (16L + WholeBytes) + 4;
long MainWritten(Vk vk) => vk.WrittenBytes.GetValueOrDefault("main");
bool Temporary(string dir) => File.Exists(MainPath(dir) + ".tmp");
long Field(PipelineCacheManager manager, string name) => (long)typeof(PipelineCacheManager).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance).GetValue(manager);

// The decision by itself (candidate only: the method is the adapter's).
{
    var decide = typeof(PipelineCacheManager).GetMethod("MainFileWorthCompacting", BindingFlags.NonPublic | BindingFlags.Static);
    const long MiB = 1024 * 1024;
    var cases = new (string Name, long File, long Data)[]
    {
        ("ipa724", 792 * MiB + 31457, 85 * MiB), ("moreThanHalf", 100 * MiB, 60 * MiB), ("exactlyHalf", 100 * MiB, 50 * MiB),
        ("under8MiBSaved", 12 * MiB, 5 * MiB), ("smallFile", 2 * MiB, MiB / 8), ("sameSize", 85 * MiB, 85 * MiB),
        ("grown", 85 * MiB, 90 * MiB), ("empty", 100 * MiB, 0),
    };
    report["decisions"] = decide == null ? null : cases.ToDictionary(c => c.Name, c => (object)(bool)decide.Invoke(null, new object[] { c.File, c.Data }));
}

// S1: a player's file written before the driver kept keys (200 whole libraries, 12.5 MiB); the session is then killed
// (never closed), and the next launch reads what is on disk.
{
    string dir = Path.Combine(root, "migration");
    WriteCache(MainPath(dir), Enumerable.Range(1, 200).Select(i => (ulong)i), WholeBytes);
    long fileBefore = Length(dir);
    int compactBefore = Records("compact"), sizeBefore = Records("loadedSize"), writtenBefore = Records("written");
    var l = Open(dir);
    var attempt = l.Vk.Attempts.Single(a => a.Len == fileBefore);
    long fileAfterLoad = Length(dir), writtenAtLoad = MainWritten(l.Vk);
    var disk = OnDisk(dir);
    l.Vk.Touch(l.Manager.MainCache);
    bool mappedAfterLoad = Vk.IsMapped(attempt.Ptr, attempt.Len);
    int compact = Records("compact") - compactBefore, written = Records("written") - writtenBefore;
    string record = LastRecord("compact");
    long writtenBytesField = Field(l.Manager, "_mainWrittenBytes");
    int loadedSize = Records("loadedSize") - sizeBefore;
    // Killed here: nothing closes this manager. The next launch:
    int compactBeforeNext = Records("compact");
    var again = Open(dir);
    report["migration"] = new Dictionary<string, object>
    {
        ["fileBefore"] = fileBefore, ["wholeSize"] = WholeSize(200), ["fileAfterLoad"] = fileAfterLoad, ["keySize"] = KeySize(200),
        ["writtenAtLoad"] = writtenAtLoad, ["compactRecords"] = compact, ["loadedSizeRecords"] = loadedSize,
        ["writtenRecords"] = written, ["record"] = record, ["entriesOnDisk"] = disk.Count,
        ["entriesOnDiskAtKeyLength"] = disk.Count(e => e.Value == KeyBytes), ["allOnDisk"] = Enumerable.Range(1, 200).All(i => disk.ContainsKey((ulong)i)),
        ["temporaryLeft"] = Temporary(dir), ["mappedAfterLoad"] = mappedAfterLoad, ["invalidReads"] = l.Vk.InvalidReads,
        ["validReads"] = l.Vk.ValidReads, ["entriesInMain"] = l.Vk.Entries(l.Manager.MainCache).Count, ["mainWrittenBytes"] = writtenBytesField,
        ["nextLaunchReadBytes"] = again.Vk.Attempts.Single(a => a.Referenced).Len, ["nextLaunchEntries"] = again.Vk.Entries(again.Manager.MainCache).Count,
        ["nextLaunchCompactRecords"] = Records("compact") - compactBeforeNext, ["nextLaunchWritten"] = MainWritten(again.Vk),
        ["nextLaunchFile"] = Length(dir), ["nextLaunchInvalidReads"] = again.Vk.InvalidReads,
    };
    again.Manager.Dispose();
}

// S2: the same file through a whole session: load, play (30 new libraries), a pause (less than 8 MiB new: no write since
// Core 727), the close; then the next launch.
{
    string dir = Path.Combine(root, "session");
    WriteCache(MainPath(dir), Enumerable.Range(1, 200).Select(i => (ulong)i), WholeBytes);
    WriteCache(WorkerPath(dir, 0), Enumerable.Range(1000, 20).Select(i => (ulong)i), WholeBytes);
    var l = Open(dir);
    var diskAfterLoad = OnDisk(dir);
    long fileAfterLoad = Length(dir);
    AddToMain(l, Enumerable.Range(5000, 30).Select(i => (ulong)i));
    int skippedBefore = Records("checkpointSkipped");
    l.Manager.CheckpointMainOnPause();
    int skipped = Records("checkpointSkipped") - skippedBefore;
    long fileAfterPause = Length(dir);
    l.Vk.Touch(l.Manager.MainCache);
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    var disk = OnDisk(dir);
    var again = Open(dir);
    report["session"] = new Dictionary<string, object>
    {
        ["fileAfterLoad"] = fileAfterLoad, ["entriesOnDiskAfterLoad"] = diskAfterLoad.Count, ["keySizeWithWorker"] = KeySize(220),
        ["pauseSkipped"] = skipped, ["fileAfterPause"] = fileAfterPause, ["invalidReads"] = l.Vk.InvalidReads,
        ["mainDestroyedWithValidRegions"] = l.Vk.MainDestroyedWithValidRegions,
        ["entriesOnDiskAfterClose"] = disk.Count, ["fileAfterClose"] = Length(dir), ["keySizeAfterClose"] = KeySize(250),
        ["allOnDisk"] = Enumerable.Range(1, 200).Concat(Enumerable.Range(1000, 20)).Concat(Enumerable.Range(5000, 30)).All(i => disk.ContainsKey((ulong)i)),
        ["nextLaunchEntries"] = again.Vk.Entries(again.Manager.MainCache).Count, ["nextLaunchWritten"] = MainWritten(again.Vk),
        ["nextLaunchInvalidReads"] = again.Vk.InvalidReads,
    };
    again.Manager.Dispose();
}

// S3: a file that already holds keys: nothing to write at the load.
{
    string dir = Path.Combine(root, "alreadyKeys");
    WriteCache(MainPath(dir), Enumerable.Range(1, 2200).Select(i => (ulong)i), KeyBytes);
    long fileBefore = Length(dir);
    DateTime stamp = File.GetLastWriteTimeUtc(MainPath(dir));
    int compactBefore = Records("compact"), sizeBefore = Records("loadedSize");
    var l = Open(dir);
    report["alreadyKeys"] = new Dictionary<string, object>
    {
        ["fileBefore"] = fileBefore, ["fileAfterLoad"] = Length(dir), ["sameFile"] = File.GetLastWriteTimeUtc(MainPath(dir)) == stamp,
        ["writtenAtLoad"] = MainWritten(l.Vk), ["compactRecords"] = Records("compact") - compactBefore,
        ["loadedSizeRecords"] = Records("loadedSize") - sizeBefore, ["record"] = LastRecord("loadedSize"),
        ["entriesInMain"] = l.Vk.Entries(l.Manager.MainCache).Count, ["mainWrittenBytes"] = Field(l.Manager, "_mainWrittenBytes"),
    };
    l.Manager.Dispose();
}

// S4: a small whole file (30 libraries, under 8 MiB to gain): not written at the load; the growth rule then counts from
// main's data, so 8 MiB of new libraries are written at the pause.
{
    string dir = Path.Combine(root, "smallFile");
    WriteCache(MainPath(dir), Enumerable.Range(1, 30).Select(i => (ulong)i), WholeBytes);
    long fileBefore = Length(dir);
    int compactBefore = Records("compact");
    var l = Open(dir);
    long writtenAtLoad = MainWritten(l.Vk), fileAfterLoad = Length(dir), field = Field(l.Manager, "_mainWrittenBytes");
    AddToMain(l, Enumerable.Range(5000, 2080).Select(i => (ulong)i));   // 2 080 x 4 KiB = 8.1 MiB
    l.Manager.CheckpointMainOnPause();
    var disk = OnDisk(dir);
    report["smallFile"] = new Dictionary<string, object>
    {
        ["fileBefore"] = fileBefore, ["fileAfterLoad"] = fileAfterLoad, ["writtenAtLoad"] = writtenAtLoad,
        ["compactRecords"] = Records("compact") - compactBefore, ["mainWrittenBytesAfterLoad"] = field, ["keySize"] = KeySize(30),
        ["pauseWroteNewLibraries"] = disk.ContainsKey(5000), ["entriesOnDiskAfterPause"] = disk.Count,
    };
    l.Manager.Dispose();
}

// S5: the write at the load fails (the driver cannot give its data): the file stays whole and valid, nothing is left
// beside it, the session goes on and its close writes main.
{
    string dir = Path.Combine(root, "writeFails");
    WriteCache(MainPath(dir), Enumerable.Range(1, 200).Select(i => (ulong)i), WholeBytes);
    long fileBefore = Length(dir);
    var l = Open(dir, failMainData: true);
    long fileAfterLoad = Length(dir);
    bool temporary = Temporary(dir);
    int entriesOnDiskAfterLoad = OnDisk(dir).Count;
    l.Vk.FailMainData = false;
    AddToMain(l, Enumerable.Range(5000, 10).Select(i => (ulong)i));
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    report["writeFails"] = new Dictionary<string, object>
    {
        ["fileBefore"] = fileBefore, ["fileAfterLoad"] = fileAfterLoad, ["temporaryLeft"] = temporary,
        ["entriesOnDiskAfterLoad"] = entriesOnDiskAfterLoad, ["entriesOnDiskAfterClose"] = OnDisk(dir).Count,
        ["fileAfterClose"] = Length(dir), ["keySizeAfterClose"] = KeySize(210), ["invalidReads"] = l.Vk.InvalidReads,
    };
}

// S6: the close overtakes the background load: main is destroyed first; nothing is measured or written when the load returns.
{
    string dir = Path.Combine(root, "overtaken");
    WriteCache(MainPath(dir), Enumerable.Range(1, 200).Select(i => (ulong)i), WholeBytes);
    long fileBefore = Length(dir);
    int compactBefore = Records("compact"), sizeBefore = Records("loadedSize");
    var l = Open(dir, loadMs: 400, wait: false);
    Thread.Sleep(100);
    bool pendingAtClose = l.Manager.MainLoadPending;
    l.Manager.Dispose();
    WaitLoaded(l.Manager);
    report["overtaken"] = new Dictionary<string, object>
    {
        ["pendingAtClose"] = pendingAtClose, ["fileBefore"] = fileBefore, ["fileAfter"] = Length(dir), ["writtenAtLoad"] = MainWritten(l.Vk),
        ["compactRecords"] = Records("compact") - compactBefore, ["loadedSizeRecords"] = Records("loadedSize") - sizeBefore,
        ["invalidReads"] = l.Vk.InvalidReads, ["temporaryLeft"] = Temporary(dir),
    };
}

report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Messages.Select(m => m.Length > 160 ? m[..160] : m).Distinct().Take(20).ToList();
try { Directory.Delete(root, true); } catch (IOException) { }
Console.WriteLine(JsonSerializer.Serialize(report));
