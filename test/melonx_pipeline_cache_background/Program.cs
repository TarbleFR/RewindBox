// Scenarios for melonx_pipeline_cache_background_test.py on the variant's real PipelineCacheManager.cs (control: the
// Core 693 file; candidate: with adapt_pipeline_cache_background, CANDIDATE). The Vulkan double
// (test/melonx_pipeline_cache_background/Double.cs) takes SnapshotLoadMs to create a cache from a snapshot, as MoltenVK
// compiling every Metal library it holds.
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

var report = new Dictionary<string, object> { ["variant"] = args[0] };
string root = Path.Combine(Path.GetTempPath(), "melonx-pipeline-cache-background-" + Environment.ProcessId);
const long SnapshotBytes = 10L * 1024 * 1024;
const int LoadMs = 1500;
int sessions = 0;

string WriteSnapshot(string directory)
{
    string cacheDirectory = Path.Combine(directory, "cache", "vulkan");
    Directory.CreateDirectory(cacheDirectory);
    string path = Path.Combine(cacheDirectory, "pipeline-00000000-00000000-00000000.vkpc");
    using (var stream = new FileStream(path, FileMode.Create)) { stream.SetLength(SnapshotBytes); }
    return path;
}

(PipelineCacheManager Manager, Vk Vk, Lock MainLock, string Snapshot, double CtorMs) NewManager(bool snapshot, int loadMs, bool reject = false)
{
    string directory = Path.Combine(root, "session" + sessions++);
    Directory.CreateDirectory(directory);
    Ryujinx.Common.Configuration.AppDataManager.BaseDirPath = directory;
    string path = snapshot ? WriteSnapshot(directory) : null;
    var vk = new Vk { SnapshotLoadMs = loadMs, RejectSnapshot = reject };
    var mainLock = new Lock();
    vk.MainLock = mainLock;
    var watch = Stopwatch.StartNew();
    var manager = new PipelineCacheManager(vk, new VulkanPhysicalDevice(), default, 2, mainLock);
    return (manager, vk, mainLock, path, watch.Elapsed.TotalMilliseconds);
}

bool Pending(PipelineCacheManager manager)
{
#if CANDIDATE
    return manager.MainLoadPending;
#else
    return false;
#endif
}

bool WaitLoaded(PipelineCacheManager manager, int timeoutMs)
{
    var watch = Stopwatch.StartNew();
    while (Pending(manager) && watch.ElapsedMilliseconds < timeoutMs) Thread.Sleep(5);
    return !Pending(manager);
}

string FileState(string path) { var info = new FileInfo(path); return info.Length + "@" + info.LastWriteTimeUtc.Ticks; }

// A: startup with a 10 MiB snapshot whose creation takes 1.5 s.
{
    Events.Clear();
    var (manager, vk, mainLock, path, ctorMs) = NewManager(true, LoadMs);
    long mainAtStart = vk.Size(manager.MainCache);
    bool pendingAtStart = Pending(manager);
    string fileBefore = FileState(path);
    // While loading: a pause checkpoint and the teardown save must not replace the file.
    manager.NotifyMainPipelineCreated();
    vk.Grow(manager.MainCache, 64 * 1024);
    manager.CheckpointMainOnPause();
    manager.MergeAndSave();
    string fileDuringLoad = FileState(path);
    // A worker that looks a pipeline up in main waits for the load.
    double workerWaitMs = -1;
    bool workerSawLoaded = false;
#if CANDIDATE
    var worker = new Thread(() =>
    {
        var watch = Stopwatch.StartNew();
        manager.WaitForMainLoadOnWorker();
        workerWaitMs = watch.Elapsed.TotalMilliseconds;
        workerSawLoaded = !manager.MainLoadPending;
    }) { Name = "worker" };
    worker.Start();
    worker.Join();
#endif
    bool loaded = WaitLoaded(manager, 10_000);
    long mainAfterLoad = vk.Size(manager.MainCache);
    var events = Events.Snapshot();
    var merge = events.FirstOrDefault(e => e.Text.StartsWith("merge into main"));
    var snapshotBegin = events.FirstOrDefault(e => e.Text.StartsWith("snapshot begin"));
    // After the load: a pause checkpoint writes the session's content together with the snapshot's.
    manager.NotifyMainPipelineCreated();
    vk.Grow(manager.MainCache, 9L * 1024 * 1024);
    manager.CheckpointMainOnPause();
    long fileAfter = new FileInfo(path).Length;
    manager.Dispose();
    report["startup"] = new
    {
        ctorMs,
        mainAtStart,
        pendingAtStart,
        fileUnchangedDuringLoad = fileBefore == fileDuringLoad,
        workerWaitMs,
        workerSawLoaded,
        loaded,
        mainAfterLoad,
        snapshotThread = snapshotBegin.Thread,
        mergeThread = merge.Thread,
        mergeText = merge.Text,
        fileAfter,
        lines = Ryujinx.Common.Logging.Logger.Info.Messages.Where(m => m.Contains("adapt_pipeline_cache_background")).ToArray(),
    };
}

// B: the session ends while the snapshot still loads: the device release is left to the loader thread.
{
    Events.Clear();
    var (manager, vk, mainLock, path, ctorMs) = NewManager(true, 2000);
    string fileBefore = FileState(path);
    bool deferred = false;
    string releaseThread = null;
    var released = new ManualResetEventSlim(false);
    var watch = Stopwatch.StartNew();
    manager.MergeAndSave();
    manager.Dispose();
#if CANDIDATE
    deferred = manager.DeferDeviceRelease(() => { releaseThread = Thread.CurrentThread.Name; released.Set(); });
#endif
    double teardownMs = watch.Elapsed.TotalMilliseconds;
    bool releasedInTime = !deferred || released.Wait(10_000);
    var events = Events.Snapshot();
    int mergesAfterDispose = events.Count(e => e.Text.StartsWith("merge into main"));
    report["endDuringLoad"] = new
    {
        teardownMs,
        deferred,
        releasedInTime,
        releaseThread,
        mergesAfterDispose,
        stagingDestroyed = events.Any(e => e.Text == "destroy worker" && e.Thread == "RewindBox.PipelineCacheLoad"),
        fileUnchanged = fileBefore == FileState(path),
    };
}

// C: no snapshot: nothing to load, nothing deferred.
{
    var (manager, vk, mainLock, path, ctorMs) = NewManager(false, LoadMs);
    bool pending = Pending(manager);
    bool deferred = false;
#if CANDIDATE
    deferred = manager.DeferDeviceRelease(() => { });
#endif
    manager.Dispose();
    report["noSnapshot"] = new { ctorMs, pending, deferred };
}

// D: a snapshot the driver rejects: main is not the file's state, so the next pause checkpoint writes it.
{
    Events.Clear();
    var (manager, vk, mainLock, path, ctorMs) = NewManager(true, 200, reject: true);
    bool loaded = WaitLoaded(manager, 10_000);
    manager.NotifyMainPipelineCreated();
    vk.Grow(manager.MainCache, 64 * 1024);
    manager.CheckpointMainOnPause();
    long fileAfter = new FileInfo(path).Length;
    manager.Dispose();
    report["rejected"] = new { loaded, fileAfter, mainMerged = Events.Snapshot().Any(e => e.Text.StartsWith("merge into main")) };
}

Console.WriteLine(JsonSerializer.Serialize(report));
