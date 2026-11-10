using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Configuration;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

int checks = 0;
void Check(bool condition, string message) {
    checks++;
    if (!condition) throw new Exception(message);
}
string temporary = Path.Combine(Path.GetTempPath(), "melonx-cache-cases-" + Guid.NewGuid());
Directory.CreateDirectory(temporary);
try {
    const string title = "010062b01525c000";
    const string sharedName = "pipeline-00000001-00000002-00000003.vkpc";
    const string titleName = "pipeline-00000001-00000002-00000003-" + title + ".vkpc";
    AppDataManager.BaseDirPath = temporary;
    VulkanRenderer.PipelineCacheScope = () => title;
    string cacheDir = Path.Combine(temporary, "cache", "vulkan");
    Directory.CreateDirectory(cacheDir);
    string old = Path.Combine(cacheDir, sharedName);
    byte[] oldBytes = Enumerable.Repeat((byte)77, 16).ToArray();
    File.WriteAllBytes(old, oldBytes);
    var vk = new Vk();
    using (var cache = new PipelineCacheManager(vk, new(), new(), 1, new Lock())) {
        Check(File.ReadAllBytes(old).SequenceEqual(oldBytes), "Constructing title cache deleted shared snapshot");
        cache.MergeAndSave();
        Check(vk.Exports == 0, "Empty clean caches exported");
        string main = Path.Combine(cacheDir, titleName);
        Check(!File.Exists(main), "Empty session replaced cache");

        vk.Set(cache.MainCache, 1);
        cache.NotifyMainPipelineCreated();
        cache.MergeAndSave();
        Check(File.ReadAllBytes(main).All(b => b == 1), "Initial main content not persisted");
        long bytes = new FileInfo(main).Length;
        vk.Set(cache.MainCache, 2);
        cache.NotifyMainPipelineCreated();
        cache.MergeAndSave();
        Check(new FileInfo(main).Length == bytes, "Driver test must retain cache size");
        Check(File.ReadAllBytes(main).All(b => b == 2), "Same-size changed cache was lost");
        int exports = vk.Exports;
        cache.MergeAndSave();
        Check(vk.Exports == exports, "Clean cache exported repeatedly");

        vk.Set(cache.GetWorkerCache(0), 3);
        cache.NotifyWorkerPipelineCreated(0);
        cache.MergeAndSave();
        Check(File.ReadAllBytes(main).All(b => b == 3), "Worker merge was not persisted");
        exports = vk.Exports;
        int merges = vk.Merges;
        cache.MergeAndSave();
        Check(vk.Exports == exports && vk.Merges == merges, "Unchanged worker was merged or exported again");

        vk.Set(cache.GetWorkerCache(0), 4);
        cache.NotifyWorkerPipelineCreated(0);
        vk.FailNextMerge = true;
        cache.MergeAndSave();
        Check(File.ReadAllBytes(main).All(b => b == 3), "Failed merge replaced good snapshot");
        cache.MergeAndSave();
        Check(File.ReadAllBytes(main).All(b => b == 4), "Failed merge lost its dirty generation");
        Check(File.ReadAllBytes(old).SequenceEqual(oldBytes), "Successful title save removed shared cache");
    }
    // Imported snapshots start clean. A worker snapshot still merges into the
    // main cache once because it may contain work the previous main missed.
    vk = new Vk();
    using (var cache = new PipelineCacheManager(vk, new(), new(), 0, new Lock())) {
        cache.MergeAndSave();
        Check(vk.Exports == 0, "Unmodified loaded cache was rewritten");
    }

    // Driver-rejected snapshots restart empty and are dirty relative to the
    // rejected disk bytes, even without a later pipeline creation.
    vk = new Vk { RejectNextSnapshot = true };
    using (var cache = new PipelineCacheManager(vk, new(), new(), 0, new Lock())) {
        cache.MergeAndSave();
        Check(vk.Exports == 1, "Rejected snapshot incorrectly considered clean");
        Check(File.ReadAllBytes(Path.Combine(cacheDir, titleName)).All(b => b == 0),
              "Rejected snapshot survived instead of the accepted replacement");
    }

    // A failed file write must not mark the in-memory generation persisted.
    string secondRoot = Path.Combine(temporary, "io-error");
    AppDataManager.BaseDirPath = secondRoot;
    Directory.CreateDirectory(Path.Combine(secondRoot, "cache"));
    string blockedDir = Path.Combine(secondRoot, "cache", "vulkan");
    File.WriteAllText(blockedDir, "not a directory");
    vk = new Vk();
    using (var cache = new PipelineCacheManager(vk, new(), new(), 0, new Lock())) {
        vk.Set(cache.MainCache, 5);
        cache.NotifyMainPipelineCreated();
        cache.MergeAndSave();
        File.Delete(blockedDir);
        cache.MergeAndSave();
        Check(File.ReadAllBytes(Path.Combine(blockedDir, titleName)).All(b => b == 5), "Failed save was not retried");
    }
    Console.WriteLine(JsonSerializer.Serialize(new { checks, sameSizeChangedBlobPersisted = true,
        cleanSnapshotsSkipped = true, failedMergeAndSaveRetried = true, sharedSnapshotPreserved = true,
        physicalDeviceTested = false }));
} finally { Directory.Delete(temporary, true); }
