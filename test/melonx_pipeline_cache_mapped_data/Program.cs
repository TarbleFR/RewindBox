// Scenarios for melonx_pipeline_cache_mapped_data_test.py on the variant's real PipelineCacheManager.cs (control: the Core
// 719 preparation; candidate: with adapt_pipeline_cache_mapped_data; releasedEarly / neverReleased: the candidate with one
// part reverted, which must fail), over the content double of Double.cs in reference mode: a cache created with the 'RBX1'
// pNext structure keeps pointers into the caller's data (as MoltenVK with the RewindBox patch keeps each library's
// compressed MSL), vkMergePipelineCaches carries them to the destination (MVKShaderLibrary's copy keeps the pointer), and
// every later use (merge, write, destroy) checks the region is still mapped (msync) and still holds the data it read.
// Isolated directories, never a player's cache.
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
string root = Path.Combine(Path.GetTempPath(), $"melonx-pipeline-cache-mapped-data-{Environment.ProcessId}-{variant}");
const string Title = "0100F7E00C70E000";
const int EntryBytes = 32 * 1024;
const uint Driver = 10402;
VulkanRenderer.PipelineCacheScope = () => Title;
bool candidate = typeof(PipelineCacheManager).GetField("_mainDataSnapshot", BindingFlags.NonPublic | BindingFlags.Instance) != null;
if ((variant != "control") != candidate) throw new InvalidOperationException("variant and source disagree");

string MainPath(string dir) => Path.Combine(dir, "cache", "vulkan", $"pipeline-{0x106B:X8}-{0x1A2B3C4D:X8}-{Driver:X8}-{Title.ToLowerInvariant()}.vkpc");
string WorkerPath(string dir, int index) => Path.ChangeExtension(MainPath(dir), null) + $".worker{index}.vkpc";

void WriteCache(string path, IEnumerable<ulong> ids, byte[] uuid = null)
{
    var vk = new Vk();
    var entries = ids.ToDictionary(id => id, _ => EntryBytes);
    var data = new byte[CacheFormat.Size(entries)];
    CacheFormat.Write(data, entries, vk.Vendor, vk.DeviceId, uuid ?? vk.Uuid);
    Directory.CreateDirectory(Path.GetDirectoryName(path));
    File.WriteAllBytes(path, data);
}

(PipelineCacheManager Manager, Vk Vk, Lock MainLock) Open(string dir, int refuseIntact = 0, int loadMs = 0, bool wait = true)
{
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = dir;
    var vk = new Vk { RefuseIntact = refuseIntact, SnapshotLoadMs = loadMs };
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

int Mapped(string stage) { lock (Ryujinx.Common.EmbeddedLaunchDiagnostics.Records) return Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.Count(r => r.StartsWith("pipelineCache " + stage)); }

void AddToMain((PipelineCacheManager Manager, Vk Vk, Lock MainLock) l, IEnumerable<ulong> ids)
{
    foreach (ulong id in ids)
    {
        l.Manager.EnterMainCreation(l.MainLock, false, out PipelineCache target);
        try { l.Vk.Add(target, id, EntryBytes); }
        finally { l.Manager.ExitMainCreation(l.MainLock, target); }
        l.Manager.NotifyMainPipelineCreated();
    }
}

HashSet<ulong> OnDisk(string dir)
{
    var vk = new Vk();
    var entries = CacheFormat.ReadFile(MainPath(dir), vk.Vendor, vk.DeviceId, vk.Uuid, out _);
    return entries == null ? new HashSet<ulong>() : entries.Keys.ToHashSet();
}

object Attempts(Vk vk, long mainLength) => vk.Attempts.Select(a => new Dictionary<string, object>
{
    ["role"] = a.Len == mainLength ? "main" : "worker", ["bytes"] = a.Len, ["referenced"] = a.Referenced,
}).ToList();

// S1: a session over a main snapshot (200 libraries) and a worker snapshot (20): load, play, pause checkpoint (the main
// file replaced while main references the old one), more play, close; then a second launch reads everything.
{
    string dir = Path.Combine(root, "session");
    WriteCache(MainPath(dir), Enumerable.Range(1, 200).Select(i => (ulong)i));
    WriteCache(WorkerPath(dir, 0), Enumerable.Range(1000, 20).Select(i => (ulong)i));
    long mainLength = new FileInfo(MainPath(dir)).Length;
    int journalBefore = Mapped("mainDataMapped");
    var l = Open(dir);
    var mainAttempt = l.Vk.Attempts.Single(a => a.Len == mainLength);
    int mainRegions = l.Vk.Regions.TryGetValue(l.Vk.MainHandle, out var held) ? held.Count : 0; // the load is over
    bool mappedAfterLoad = Vk.IsMapped(mainAttempt.Ptr, mainAttempt.Len);
    int entriesAfterLoad = l.Vk.Entries(l.Manager.MainCache).Count;
    int journalLines = Mapped("mainDataMapped") - journalBefore;
    AddToMain(l, Enumerable.Range(5000, 30).Select(i => (ulong)i));
    l.Manager.CheckpointMainOnPause();
    bool checkpointWrote = OnDisk(dir).Contains(5000);
    bool mappedAfterCheckpoint = Vk.IsMapped(mainAttempt.Ptr, mainAttempt.Len);
    l.Vk.Touch(l.Manager.MainCache);
    AddToMain(l, Enumerable.Range(6000, 10).Select(i => (ulong)i));
    l.Manager.MergeAndSave();
    bool mappedBeforeDispose = Vk.IsMapped(mainAttempt.Ptr, mainAttempt.Len);
    l.Manager.Dispose();
    bool mappedAfterDispose = Vk.IsMapped(mainAttempt.Ptr, mainAttempt.Len);
    var disk = OnDisk(dir);
    var again = Open(dir);
    int entriesNextLaunch = again.Vk.Entries(again.Manager.MainCache).Count;
    again.Manager.Dispose();
    report["session"] = new Dictionary<string, object>
    {
        ["attempts"] = Attempts(l.Vk, mainLength), ["referenceCreations"] = l.Vk.ReferenceCreations, ["mainRegions"] = mainRegions,
        ["mappedAfterLoad"] = mappedAfterLoad, ["entriesAfterLoad"] = entriesAfterLoad, ["journalLines"] = journalLines,
        ["checkpointWrote"] = checkpointWrote, ["mappedAfterCheckpoint"] = mappedAfterCheckpoint,
        ["mappedBeforeDispose"] = mappedBeforeDispose, ["mappedAfterDispose"] = mappedAfterDispose,
        ["validReads"] = l.Vk.ValidReads, ["invalidReads"] = l.Vk.InvalidReads,
        ["mainDestroyedWithValidRegions"] = l.Vk.MainDestroyedWithValidRegions,
        ["onDisk"] = disk.Count, ["allOnDisk"] = Enumerable.Range(1, 200).Concat(Enumerable.Range(1000, 20)).Concat(Enumerable.Range(5000, 30))
            .Concat(Enumerable.Range(6000, 10)).All(i => disk.Contains((ulong)i)),
        ["entriesNextLaunch"] = entriesNextLaunch, ["invalidReadsNextLaunch"] = again.Vk.InvalidReads,
        ["mappedAfterNextDispose"] = again.Vk.Attempts.Any(a => a.Referenced && Vk.IsMapped(a.Ptr, a.Len)),
    };
}

// S2: a main snapshot refused once (MoltenVK refuses the whole data when one Metal library fails): nothing references it,
// released at once; main Frozen (its file kept), as before.
{
    string dir = Path.Combine(root, "refused");
    WriteCache(MainPath(dir), Enumerable.Range(1, 50).Select(i => (ulong)i));
    long mainLength = new FileInfo(MainPath(dir)).Length;
    int journalBefore = Mapped("mainDataMapped");
    var l = Open(dir, refuseIntact: 1);
    var attempt = l.Vk.Attempts.Single(a => a.Len == mainLength);
    bool mappedAfterLoad = Vk.IsMapped(attempt.Ptr, attempt.Len);
    int journalLines = Mapped("mainDataMapped") - journalBefore;
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    report["refused"] = new Dictionary<string, object>
    {
        ["referencedAttempt"] = attempt.Referenced, ["referenceCreations"] = l.Vk.ReferenceCreations, ["mappedAfterLoad"] = mappedAfterLoad,
        ["journalLines"] = journalLines, ["invalidReads"] = l.Vk.InvalidReads, ["fileKept"] = OnDisk(dir).Count == 50,
    };
}

// S3: a file of another driver identity (MoltenVK ignores it and keeps nothing): released at once, written again.
{
    string dir = Path.Combine(root, "foreign");
    WriteCache(MainPath(dir), Enumerable.Range(1, 50).Select(i => (ulong)i), Enumerable.Range(101, 16).Select(i => (byte)i).ToArray());
    long mainLength = new FileInfo(MainPath(dir)).Length;
    int journalBefore = Mapped("mainDataMapped");
    var l = Open(dir);
    var attempt = l.Vk.Attempts.Single(a => a.Len == mainLength);
    bool mappedAfterLoad = Vk.IsMapped(attempt.Ptr, attempt.Len);
    int journalLines = Mapped("mainDataMapped") - journalBefore;
    AddToMain(l, new ulong[] { 9000 });
    l.Manager.MergeAndSave();
    l.Manager.Dispose();
    report["foreign"] = new Dictionary<string, object>
    {
        ["referencedAttempt"] = attempt.Referenced, ["mappedAfterLoad"] = mappedAfterLoad, ["journalLines"] = journalLines,
        ["invalidReads"] = l.Vk.InvalidReads, ["rewritten"] = OnDisk(dir).SetEquals(new ulong[] { 9000 }),
    };
}

// S4: the close overtakes the background load (the driver still reading the snapshot): main destroyed first, the
// snapshot released when the load returns, nothing merged, no read of a released region.
{
    string dir = Path.Combine(root, "overtaken");
    WriteCache(MainPath(dir), Enumerable.Range(1, 50).Select(i => (ulong)i));
    long mainLength = new FileInfo(MainPath(dir)).Length;
    int journalBefore = Mapped("mainDataMapped");
    var l = Open(dir, loadMs: 400, wait: false);
    Thread.Sleep(100);
    bool pendingAtClose = l.Manager.MainLoadPending;
    l.Manager.Dispose();
    WaitLoaded(l.Manager);
    var attempt = l.Vk.Attempts.Single(a => a.Len == mainLength);
    report["overtaken"] = new Dictionary<string, object>
    {
        ["pendingAtClose"] = pendingAtClose, ["referencedAttempt"] = attempt.Referenced, ["referenceCreations"] = l.Vk.ReferenceCreations,
        ["mappedAfterLoad"] = Vk.IsMapped(attempt.Ptr, attempt.Len), ["journalLines"] = Mapped("mainDataMapped") - journalBefore,
        ["invalidReads"] = l.Vk.InvalidReads, ["fileKept"] = OnDisk(dir).Count == 50,
    };
}

report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Messages.Select(m => m.Length > 160 ? m[..160] : m).Distinct().Take(20).ToList();
try { Directory.Delete(root, true); } catch (IOException) { }
Console.WriteLine(JsonSerializer.Serialize(report));
