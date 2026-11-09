// Scenarios for melonx_pipeline_snapshot_retire_test.py on the variant's real PipelineCacheManager.cs (control: the Core 711
// preparation; candidate: with adapt_pipeline_snapshot_retire). Every launch is a new manager and a new Vulkan double over
// the same isolated directory (a copy, never a player's cache); content is checked entry by entry in the files.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text.Json;
using System.Threading;
using FixtureSupport;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

string variant = args[0];
var report = new Dictionary<string, object> { ["variant"] = variant };
string root = Path.Combine(Path.GetTempPath(), $"melonx-pipeline-snapshot-retire-{Environment.ProcessId}-{variant}");
const string Title = "0100F7E00C70E000";
const int EntryBytes = 32 * 1024;
const uint DriverA = 10402, DriverB = 10403;
VulkanRenderer.PipelineCacheScope = () => Title;
ulong nextId = 1;

string MainPath(string dir, uint driver = DriverA) =>
    Path.Combine(dir, "cache", "vulkan", $"pipeline-{0x106B:X8}-{0x1A2B3C4D:X8}-{driver:X8}-{Title.ToLowerInvariant()}.vkpc");
string WorkerPath(string dir, int index, uint driver = DriverA) => Path.ChangeExtension(MainPath(dir, driver), null) + $".worker{index}.vkpc";
long Length(string path) => File.Exists(path) ? new FileInfo(path).Length : 0;
string Hash(string path) => File.Exists(path) ? Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)))[..16] : "absent";

Launch Open(string dir, uint driver = DriverA, int loadMs = 0, byte[] uuid = null, int skip = 0, int refuseIntact = 0)
{
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = dir;
    var vk = new Vk { SnapshotLoadMs = loadMs, SkipSnapshots = skip, RefuseIntact = refuseIntact };
    if (uuid != null) vk.Uuid = uuid;
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    var properties = new PhysicalDeviceProperties { VendorID = vk.Vendor, DeviceID = vk.DeviceId, DriverVersion = driver };
    unsafe { for (int i = 0; i < 16; i++) properties.PipelineCacheUuid[i] = vk.Uuid[i]; }
    var device = new VulkanPhysicalDevice { PhysicalDeviceProperties = properties };
    long mainBytes = Length(MainPath(dir, driver));
    long workerBytes = Length(WorkerPath(dir, 0, driver)) + Length(WorkerPath(dir, 1, driver));
    var watch = Stopwatch.StartNew();
    var manager = new PipelineCacheManager(vk, device, default, 2, mainLock);
    double ctorMs = watch.Elapsed.TotalMilliseconds;
    var launch = new Launch { Manager = manager, Vk = vk, Dir = dir, Driver = driver };
    launch.Load["mainFileBytes"] = mainBytes;
    launch.Load["workerFileBytes"] = workerBytes;
    launch.Load["ctorMs"] = Math.Round(ctorMs, 1);
    launch.Load["watch"] = watch;
    return launch;
}

bool WaitLoaded(Launch launch, int timeoutMs = 60_000)
{
    var watch = Stopwatch.StartNew();
    while (launch.Manager.MainLoadPending && watch.ElapsedMilliseconds < timeoutMs) Thread.Sleep(2);
    var started = (Stopwatch)launch.Load["watch"];
    launch.Load.Remove("watch");
    launch.Load["loadMs"] = Math.Round(started.Elapsed.TotalMilliseconds, 1);
    launch.Load["hydratedBytes"] = launch.Vk.HydratedBytes;
    launch.Load["hydratedEntries"] = launch.Vk.HydratedEntries;
    launch.Load["mergedEntries"] = launch.Vk.MergedSourceEntries;
    launch.Load["mergeAddedEntries"] = launch.Vk.MergeAddedEntries;
    launch.Load["ignored"] = launch.Vk.IgnoredSnapshots;
    launch.Load["refused"] = launch.Vk.RefusedSnapshots;
    launch.Load["snapshots"] = string.Join(",", launch.Vk.Snapshots);
    launch.Load["mainEntries"] = launch.Vk.Entries(launch.Manager.MainCache).Count;
    return !launch.Manager.MainLoadPending;
}

void CompileMain(Launch launch, int count, HashSet<ulong> expected)
{
    for (int i = 0; i < count; i++)
    {
        ulong id = nextId++;
        launch.Vk.Add(launch.Manager.MainCache, id, EntryBytes);
        launch.Manager.NotifyMainPipelineCreated();
        expected?.Add(id);
    }
}

List<ulong> CompileWorker(Launch launch, int worker, int count, HashSet<ulong> expected)
{
    var ids = new List<ulong>();
    for (int i = 0; i < count; i++)
    {
        ulong id = nextId++;
        launch.Vk.Add(launch.Manager.GetWorkerCache(worker), id, EntryBytes);
        launch.Manager.NotifyWorkerPipelineCreated(worker);
        expected?.Add(id);
        ids.Add(id);
    }
    return ids;
}

// The content of every file of that driver version.
HashSet<ulong> OnDisk(string dir, uint driver = DriverA, byte[] uuid = null)
{
    var vk = new Vk();
    uuid ??= vk.Uuid;
    var all = new HashSet<ulong>();
    foreach (string path in new[] { MainPath(dir, driver), WorkerPath(dir, 0, driver), WorkerPath(dir, 1, driver) })
    {
        var entries = CacheFormat.ReadFile(path, vk.Vendor, vk.DeviceId, uuid, out _);
        if (entries != null) all.UnionWith(entries.Keys);
    }
    return all;
}

HashSet<ulong> InMemory(Launch launch)
{
    var all = new HashSet<ulong>(launch.Vk.Entries(launch.Manager.MainCache).Keys);
    all.UnionWith(launch.Vk.Entries(launch.Manager.GetWorkerCache(0)).Keys);
    all.UnionWith(launch.Vk.Entries(launch.Manager.GetWorkerCache(1)).Keys);
    return all;
}

Dictionary<string, object> Close(Launch launch, bool dispose = true)
{
    launch.Vk.ResetCounters();
    var watch = Stopwatch.StartNew();
    launch.Manager.MergeAndSave();
    double closeMs = watch.Elapsed.TotalMilliseconds;
    var result = new Dictionary<string, object>
    {
        ["closeMs"] = Math.Round(closeMs, 1),
        ["writtenMain"] = launch.Vk.WrittenBytes.GetValueOrDefault("main"),
        ["writtenWorkers"] = launch.Vk.WrittenBytes.GetValueOrDefault("worker"),
        ["mainFile"] = Length(MainPath(launch.Dir, launch.Driver)),
        ["workerFiles"] = new[] { Length(WorkerPath(launch.Dir, 0, launch.Driver)), Length(WorkerPath(launch.Dir, 1, launch.Driver)) },
        ["workerFilesPresent"] = (File.Exists(WorkerPath(launch.Dir, 0, launch.Driver)) ? 1 : 0) + (File.Exists(WorkerPath(launch.Dir, 1, launch.Driver)) ? 1 : 0),
    };
    if (dispose) launch.Manager.Dispose();
    return result;
}

// A kill: nothing saved at the close (the process ends; the files stay as the last checkpoint left them).
void Kill(Launch launch) => launch.Manager.Dispose();

string NewDir(string name) { string dir = Path.Combine(root, name); Directory.CreateDirectory(dir); return dir; }
List<ulong> Missing(HashSet<ulong> expected, HashSet<ulong> have) => expected.Where(id => !have.Contains(id)).ToList();

// S1. Four launches of one title: the steady state of read, hydration, merge and close writes.
{
    string dir = NewDir("steady");
    var expected = new HashSet<ulong>();
    var launches = new List<object>();
    for (int round = 0; round < 4; round++)
    {
        var launch = Open(dir);
        bool loaded = WaitLoaded(launch);
        var missingAfterLoad = Missing(expected, InMemory(launch)).Count;
        CompileMain(launch, round == 0 ? 300 : 100, expected);
        CompileWorker(launch, 0, round == 0 ? 120 : 60, expected);
        CompileWorker(launch, 1, round == 0 ? 120 : 60, expected);
        string workersBeforePause = Hash(WorkerPath(dir, 0)) + Hash(WorkerPath(dir, 1));
        launch.Manager.CheckpointMainOnPause();
        bool pauseKeptWorkerFiles = workersBeforePause == Hash(WorkerPath(dir, 0)) + Hash(WorkerPath(dir, 1));
        var close = Close(launch);
        launches.Add(new Dictionary<string, object>
        {
            ["loaded"] = loaded, ["load"] = launch.Load, ["missingAfterLoad"] = missingAfterLoad, ["close"] = close,
            ["pauseKeptWorkerFiles"] = pauseKeptWorkerFiles, ["missingOnDisk"] = Missing(expected, OnDisk(dir)).Count,
            ["expected"] = expected.Count,
        });
    }
    var last = Open(dir);
    WaitLoaded(last);
    var final = new Dictionary<string, object> { ["load"] = last.Load, ["missingAfterLoad"] = Missing(expected, InMemory(last)).Count };
    Kill(last);
    report["steady"] = new Dictionary<string, object> { ["launches"] = launches, ["final"] = final };
}

// S2. A kill after worker checkpoints during play: their content is only in the worker files.
{
    string dir = NewDir("crash");
    var expected = new HashSet<ulong>();
    var first = Open(dir);
    WaitLoaded(first);
    CompileMain(first, 100, null);                   // never written: lost by the kill in both variants
    var checkpointed = new HashSet<ulong>();
    checkpointed.UnionWith(CompileWorker(first, 0, 70, null).Take(64));
    checkpointed.UnionWith(CompileWorker(first, 1, 70, null).Take(64));
    Kill(first);
    expected.UnionWith(checkpointed);
    var afterKill = OnDisk(dir);
    var second = Open(dir);
    WaitLoaded(second);
    int missingAfterRelaunch = Missing(expected, InMemory(second)).Count;
    var close = Close(second);
    var third = Open(dir);
    WaitLoaded(third);
    int missingThird = Missing(expected, InMemory(third)).Count;
    Kill(third);
    report["crash"] = new Dictionary<string, object>
    {
        ["checkpointed"] = checkpointed.Count, ["onDiskAfterKill"] = afterKill.Count, ["missingAfterRelaunch"] = missingAfterRelaunch,
        ["close"] = close, ["missingThirdLaunch"] = missingThird, ["thirdLoad"] = third.Load,
    };
}

// S3/S4. Main is not written at the close (its write fails; it is over its budget): nothing may be removed.
foreach (string mode in new[] { "writeFailure", "overBudget" })
{
    string dir = NewDir(mode);
    var expected = new HashSet<ulong>();
    var first = Open(dir);
    WaitLoaded(first);
    CompileMain(first, 50, expected);
    CompileWorker(first, 0, 70, expected);
    CompileWorker(first, 1, 70, expected);
    Close(first);
    var second = Open(dir);
    WaitLoaded(second);
    var lostByMainFailure = new HashSet<ulong>();
    CompileMain(second, 40, lostByMainFailure);
    var workerSession = new HashSet<ulong>();
    CompileWorker(second, 0, 40, workerSession);
    CompileWorker(second, 1, 40, workerSession);
    string mainBefore = Hash(MainPath(dir));
    if (mode == "writeFailure") second.Vk.FailMainData = true; else second.Vk.InflateMainSize = 1200L * 1024 * 1024;
    var close = Close(second);
    bool mainUnchanged = mainBefore == Hash(MainPath(dir));
    var disk = OnDisk(dir);
    var third = Open(dir);
    WaitLoaded(third);
    var memory = InMemory(third);
    Kill(third);
    report[mode] = new Dictionary<string, object>
    {
        ["close"] = close, ["mainUnchanged"] = mainUnchanged, ["missingEarlier"] = Missing(expected, disk).Count,
        ["sessionWorkerEntries"] = workerSession.Count, ["sessionWorkerKept"] = workerSession.Count(id => disk.Contains(id)),
        ["sessionMainEntries"] = lostByMainFailure.Count, ["sessionMainKept"] = lostByMainFailure.Count(id => disk.Contains(id)),
        ["missingEarlierThirdLaunch"] = Missing(expected, memory).Count,
        ["sessionWorkerThirdLaunch"] = workerSession.Count(id => memory.Contains(id)), ["thirdLoad"] = third.Load,
    };
}

// S5. The close comes while the background load still runs: no file changes; the next launch has everything.
{
    string dir = NewDir("closeDuringLoad");
    var expected = new HashSet<ulong>();
    var first = Open(dir);
    WaitLoaded(first);
    CompileMain(first, 50, expected);
    Close(first);
    var second = Open(dir);
    WaitLoaded(second);
    expected.UnionWith(CompileWorker(second, 0, 70, null).Take(64));
    expected.UnionWith(CompileWorker(second, 1, 70, null).Take(64));
    Kill(second);                                    // worker files with content main's file does not hold
    string before = Hash(MainPath(dir)) + Hash(WorkerPath(dir, 0)) + Hash(WorkerPath(dir, 1));
    var third = Open(dir, loadMs: 800);
    bool pendingAtClose = third.Manager.MainLoadPending;
    CompileMain(third, 10, null);
    CompileWorker(third, 0, 10, null);
    var close = Close(third, dispose: false);
    bool filesUnchanged = before == Hash(MainPath(dir)) + Hash(WorkerPath(dir, 0)) + Hash(WorkerPath(dir, 1));
    third.Manager.Dispose();
    var wait = Stopwatch.StartNew();
    while (third.Manager.MainLoadPending && wait.ElapsedMilliseconds < 30_000) Thread.Sleep(5);
    bool filesUnchangedAfterLoad = before == Hash(MainPath(dir)) + Hash(WorkerPath(dir, 0)) + Hash(WorkerPath(dir, 1));
    var fourth = Open(dir);
    WaitLoaded(fourth);
    int missing = Missing(expected, InMemory(fourth)).Count;
    var fourthClose = Close(fourth);
    var fifth = Open(dir);
    WaitLoaded(fifth);
    int missingFifth = Missing(expected, InMemory(fifth)).Count;
    Kill(fifth);
    report["closeDuringLoad"] = new Dictionary<string, object>
    {
        ["pendingAtClose"] = pendingAtClose, ["close"] = close, ["filesUnchanged"] = filesUnchanged,
        ["filesUnchangedAfterLoad"] = filesUnchangedAfterLoad, ["missingNextLaunch"] = missing, ["nextClose"] = fourthClose,
        ["missingLaunchAfter"] = missingFifth, ["expected"] = expected.Count,
    };
}

// S6. A worker file cut short (an incomplete file): the driver refuses it.
{
    string dir = NewDir("cutWorker");
    var expected = new HashSet<ulong>();
    var first = Open(dir);
    WaitLoaded(first);
    CompileMain(first, 50, expected);
    Close(first);
    var second = Open(dir);
    WaitLoaded(second);
    expected.UnionWith(CompileWorker(second, 0, 70, null).Take(64));
    var cut = CompileWorker(second, 1, 70, null).Take(64).ToHashSet();
    Kill(second);
    using (var stream = new FileStream(WorkerPath(dir, 1), FileMode.Open)) stream.SetLength(stream.Length / 2 + 7);
    var refusedPerLaunch = new List<long>();
    var workerFilesPerLaunch = new List<int>();
    int missing = 0;
    for (int round = 0; round < 3; round++)
    {
        var launch = Open(dir);
        WaitLoaded(launch);
        refusedPerLaunch.Add(launch.Vk.RefusedSnapshots);
        missing = Missing(expected, InMemory(launch)).Count;
        CompileWorker(launch, 0, 20, expected);
        CompileMain(launch, 10, expected);
        var close = Close(launch);
        workerFilesPerLaunch.Add((int)close["workerFilesPresent"]);
    }
    var last = Open(dir);
    WaitLoaded(last);
    int missingLast = Missing(expected, InMemory(last)).Count;
    Kill(last);
    report["cutWorker"] = new Dictionary<string, object>
    {
        ["refusedPerLaunch"] = refusedPerLaunch, ["workerFilesAfterEachClose"] = workerFilesPerLaunch, ["missingLastLoop"] = missing,
        ["missingAfter"] = missingLast, ["cutFileOnlyEntries"] = cut.Count,
    };
}

// S7. The main file cut short: what the worker files still give back, and when the file is replaced.
{
    string dir = NewDir("cutMain");
    var mainOnly = new HashSet<ulong>();
    var workerContent = new HashSet<ulong>();
    var first = Open(dir);
    WaitLoaded(first);
    CompileMain(first, 80, mainOnly);
    CompileWorker(first, 0, 30, workerContent);
    CompileWorker(first, 1, 30, workerContent);
    Close(first);
    using (var stream = new FileStream(MainPath(dir), FileMode.Open)) stream.SetLength(stream.Length / 2 + 3);
    var refused = new List<object>();
    var sessions = new List<HashSet<ulong>>();
    int workerBack = 0;
    for (int round = 0; round < 2; round++)
    {
        var launch = Open(dir);
        WaitLoaded(launch);
        refused.Add(launch.Load["refused"]);
        if (round == 0) workerBack = workerContent.Count(id => InMemory(launch).Contains(id));
        var session = new HashSet<ulong>();
        CompileMain(launch, 10, session);
        sessions.Add(session);
        Close(launch);
    }
    var third = Open(dir);
    WaitLoaded(third);
    var memoryThird = InMemory(third);
    Kill(third);
    report["cutMain"] = new Dictionary<string, object>
    {
        ["refusedPerLaunch"] = refused, ["workerEntriesBack"] = workerBack, ["workerEntries"] = workerContent.Count,
        ["mainEntriesBack"] = mainOnly.Count(id => memoryThird.Contains(id)),
        ["sessionsKept"] = sessions.Select(s => s.Count(id => memoryThird.Contains(id))).ToList(), ["sessionSize"] = 10,
        ["thirdRefused"] = third.Load["refused"],
    };
}

// S8. Two driver versions alternating (A, B, A): each keeps its own files; A comes back whole.
{
    string dir = NewDir("alternating");
    var expectedA = new HashSet<ulong>();
    var expectedB = new HashSet<ulong>();
    var a = Open(dir, DriverA); WaitLoaded(a);
    CompileMain(a, 60, expectedA); CompileWorker(a, 0, 30, expectedA); CompileWorker(a, 1, 30, expectedA);
    Close(a);
    var b = Open(dir, DriverB); WaitLoaded(b);
    long bReadA = b.Vk.HydratedEntries;
    CompileMain(b, 40, expectedB); CompileWorker(b, 0, 20, expectedB);
    Close(b);
    var again = Open(dir, DriverA); WaitLoaded(again);
    int missingA = Missing(expectedA, InMemory(again)).Count;
    CompileMain(again, 5, expectedA);
    var closeA = Close(again);
    var backB = Open(dir, DriverB); WaitLoaded(backB);
    int missingB = Missing(expectedB, InMemory(backB)).Count;
    Kill(backB);
    report["alternating"] = new Dictionary<string, object>
    {
        ["bHydratedFromA"] = bReadA, ["missingAOnReturn"] = missingA, ["missingBOnReturn"] = missingB, ["closeA"] = closeA,
        ["filesA"] = new[] { Length(MainPath(dir, DriverA)), Length(WorkerPath(dir, 0, DriverA)), Length(WorkerPath(dir, 1, DriverA)) },
        ["filesB"] = new[] { Length(MainPath(dir, DriverB)), Length(WorkerPath(dir, 0, DriverB)), Length(WorkerPath(dir, 1, DriverB)) },
        ["returnLoadA"] = again.Load,
    };
}

// S9. Same file name, another cache UUID (an iOS or MoltenVK revision change): the driver ignores the data. The
// session is paused (a pause checkpoint), then killed; then a launch with a clean close.
{
    string dir = NewDir("identity");
    var first = Open(dir); WaitLoaded(first);
    CompileMain(first, 200, null);
    CompileWorker(first, 0, 30, null);
    Close(first);
    long oldFile = Length(MainPath(dir));
    byte[] otherUuid = Enumerable.Range(101, 16).Select(i => (byte)i).ToArray();
    var second = Open(dir, uuid: otherUuid); WaitLoaded(second);
    var secondLoad = new Dictionary<string, object>(second.Load);
    var session = new HashSet<ulong>();
    CompileMain(second, 100, session);
    string before = Hash(MainPath(dir));
    second.Manager.CheckpointMainOnPause();
    bool pauseWrote = before != Hash(MainPath(dir));
    Kill(second);
    var third = Open(dir, uuid: otherUuid); WaitLoaded(third);
    var thirdLoad = new Dictionary<string, object>(third.Load);
    int keptAfterKill = session.Count(id => InMemory(third).Contains(id));
    var more = new HashSet<ulong>();
    CompileMain(third, 20, more);
    var close = Close(third);
    var fourth = Open(dir, uuid: otherUuid); WaitLoaded(fourth);
    var memory = InMemory(fourth);
    Kill(fourth);
    report["identity"] = new Dictionary<string, object>
    {
        ["oldFile"] = oldFile, ["load"] = secondLoad, ["pauseWrote"] = pauseWrote, ["session"] = session.Count,
        ["keptAfterKill"] = keptAfterKill, ["thirdLoad"] = thirdLoad, ["close"] = close,
        ["keptAfterClose"] = session.Count(id => memory.Contains(id)) + more.Count(id => memory.Contains(id)),
        ["sessionsTotal"] = session.Count + more.Count,
    };
}

// S10. A launch after an incident between main's write and the workers' removal: their copies are back on disk.
{
    string dir = NewDir("incident");
    var expected = new HashSet<ulong>();
    var first = Open(dir); WaitLoaded(first);
    CompileMain(first, 60, expected); CompileWorker(first, 0, 70, expected); CompileWorker(first, 1, 70, expected);
    first.Manager.MergeAndSave();                    // main written, then the workers
    // The state right after main's write: main holds everything; the worker files are what their caches held.
    var vk = first.Vk;
    for (int index = 0; index < 2; index++)
    {
        var entries = vk.Entries(first.Manager.GetWorkerCache(index));
        byte[] data = new byte[CacheFormat.Size(entries)];
        CacheFormat.Write(data, entries, vk.Vendor, vk.DeviceId, vk.Uuid);
        File.WriteAllBytes(WorkerPath(dir, index), data);
    }
    first.Manager.Dispose();
    var second = Open(dir); WaitLoaded(second);
    int missing = Missing(expected, InMemory(second)).Count;
    var close = Close(second);
    report["incident"] = new Dictionary<string, object>
    {
        ["load"] = second.Load, ["missing"] = missing, ["close"] = close, ["missingOnDisk"] = Missing(expected, OnDisk(dir)).Count,
    };
}

// S11. A kill while main was being written: a partial .tmp beside the previous file.
{
    string dir = NewDir("killDuringWrite");
    var expected = new HashSet<ulong>();
    var first = Open(dir); WaitLoaded(first);
    CompileMain(first, 80, expected);
    Close(first);
    string main = MainPath(dir);
    byte[] whole = File.ReadAllBytes(main);
    File.WriteAllBytes(main + ".tmp", whole.AsSpan(0, whole.Length / 3).ToArray());
    var second = Open(dir); WaitLoaded(second);
    int missing = Missing(expected, InMemory(second)).Count;
    CompileMain(second, 20, expected);
    var close = Close(second);
    report["killDuringWrite"] = new Dictionary<string, object>
    {
        ["missingAfterRelaunch"] = missing, ["tmpAfterSave"] = File.Exists(main + ".tmp"), ["close"] = close,
        ["missingOnDisk"] = Missing(expected, OnDisk(dir)).Count,
    };
}

// S12. Main's snapshot leaves no room for the worker snapshots: they stay as they are (content main does not hold).
{
    string dir = NewDir("room");
    var expected = new HashSet<ulong>();
    var first = Open(dir); WaitLoaded(first);
    CompileMain(first, 40, expected);
    Close(first);
    var second = Open(dir); WaitLoaded(second);
    expected.UnionWith(CompileWorker(second, 0, 70, null).Take(64));
    expected.UnionWith(CompileWorker(second, 1, 70, null).Take(64));
    Kill(second);
    // Main's file made as long as its budget allows less 1 MiB (sparse: what it holds is unchanged, the rest never read).
    using (var stream = new FileStream(MainPath(dir), FileMode.Open)) stream.SetLength(1023L * 1024 * 1024);
    string workersBefore = Hash(WorkerPath(dir, 0)) + Hash(WorkerPath(dir, 1));
    var third = Open(dir); WaitLoaded(third);
    var thirdLoad = new Dictionary<string, object>(third.Load);
    CompileMain(third, 10, expected);
    var close = Close(third);
    bool workersUntouched = workersBefore == Hash(WorkerPath(dir, 0)) + Hash(WorkerPath(dir, 1));
    var fourth = Open(dir); WaitLoaded(fourth);
    int missing = Missing(expected, InMemory(fourth)).Count;
    var fourthLoad = new Dictionary<string, object>(fourth.Load);
    var fourthClose = Close(fourth);
    var fifth = Open(dir); WaitLoaded(fifth);
    int missingFifth = Missing(expected, InMemory(fifth)).Count;
    Kill(fifth);
    report["room"] = new Dictionary<string, object>
    {
        ["load"] = thirdLoad, ["close"] = close, ["workersUntouched"] = workersUntouched, ["missingNextLaunch"] = missing,
        ["nextLoad"] = fourthLoad, ["nextClose"] = fourthClose, ["missingLaunchAfter"] = missingFifth, ["expected"] = expected.Count,
    };
}

// S13. An intact main file refused once (transient: one Metal library failed to compile), then loaded again.
{
    string dir = NewDir("transientMain");
    var earlier = new HashSet<ulong>();
    var first = Open(dir); WaitLoaded(first);
    CompileMain(first, 150, earlier); CompileWorker(first, 0, 30, earlier); CompileWorker(first, 1, 30, earlier);
    Close(first);
    long fileBefore = Length(MainPath(dir));
    var second = Open(dir, refuseIntact: 1);         // main's snapshot is the first one created
    WaitLoaded(second);
    var secondLoad = new Dictionary<string, object>(second.Load);
    var session = new HashSet<ulong>();
    CompileMain(second, 20, session);
    second.Manager.CheckpointMainOnPause();
    long afterPause = Length(MainPath(dir));
    var close = Close(second);
    var third = Open(dir); WaitLoaded(third);
    var memory = InMemory(third);
    var thirdLoad = new Dictionary<string, object>(third.Load);
    Kill(third);
    report["transientMain"] = new Dictionary<string, object>
    {
        ["fileBefore"] = fileBefore, ["load"] = secondLoad, ["fileAfterPause"] = afterPause, ["close"] = close,
        ["earlierKept"] = earlier.Count(id => memory.Contains(id)), ["earlier"] = earlier.Count,
        ["sessionKept"] = session.Count(id => memory.Contains(id)), ["session"] = session.Count, ["thirdLoad"] = thirdLoad,
        ["marker"] = File.Exists(MainPath(dir) + ".refused"),
    };
}

// S14. An intact worker file refused once while main loads: it must survive the close.
{
    string dir = NewDir("transientWorker");
    var expected = new HashSet<ulong>();
    var first = Open(dir); WaitLoaded(first);
    CompileMain(first, 50, expected);
    Close(first);
    var second = Open(dir); WaitLoaded(second);
    var unique0 = CompileWorker(second, 0, 70, null).Take(64).ToHashSet();
    expected.UnionWith(unique0);
    expected.UnionWith(CompileWorker(second, 1, 70, null).Take(64));
    Kill(second);
    var third = Open(dir, skip: 1, refuseIntact: 1); // main loads; worker 0 is refused once
    WaitLoaded(third);
    var thirdLoad = new Dictionary<string, object>(third.Load);
    CompileMain(third, 10, expected);
    var close = Close(third);
    var fourth = Open(dir); WaitLoaded(fourth);
    var memory = InMemory(fourth);
    var fourthClose = Close(fourth);
    report["transientWorker"] = new Dictionary<string, object>
    {
        ["load"] = thirdLoad, ["close"] = close, ["worker0Kept"] = unique0.Count(id => memory.Contains(id)), ["worker0"] = unique0.Count,
        ["missingNextLaunch"] = Missing(expected, memory).Count, ["nextClose"] = fourthClose,
        ["markerAfterLoad"] = File.Exists(WorkerPath(dir, 0) + ".refused"),
    };
}

report["warnings"] = Ryujinx.Common.Logging.Logger.Warning.Messages.Select(m => m.Length > 160 ? m[..160] : m).Distinct().Take(20).ToList();
report["journal"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records.Where(r => r.Contains("workerRetired") || r.Contains("workerKept") || r.Contains("mainIgnored") || r.Contains("mainRefusedKept")).Select(r => r.Length > 200 ? r[..200] : r).Distinct().Take(40).ToList();
try { Directory.Delete(root, true); } catch (IOException) { }
Console.WriteLine(JsonSerializer.Serialize(report));

sealed class Launch
{
    public PipelineCacheManager Manager;
    public Vk Vk;
    public string Dir;
    public uint Driver;
    public Dictionary<string, object> Load = new();
}
