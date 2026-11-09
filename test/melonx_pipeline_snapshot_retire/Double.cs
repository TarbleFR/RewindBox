// Doubles for melonx_pipeline_snapshot_retire_test.py, compiled with the variant's real PipelineCacheManager.cs and
// VulkanException.cs (from test/melonx_pipeline_cache_background/Double.cs, with cache CONTENT instead of byte counts).
//
// Each VkPipelineCache holds entries (id -> payload length), as MoltenVK holds shader libraries keyed by their shader
// module key. vkGetPipelineCacheData writes a header (size 32, version 1, vendor, device, a 16-byte cache UUID, as
// VkPipelineCacheHeaderVersionOne), then one record per entry (type 1, id, length, a payload derived from the id), then
// type 0. vkCreatePipelineCache with initial data behaves as MoltenVK v1.4.2 MVKPipelineCache::readData: a header that
// does not match the device (size, version, vendor, device, UUID) is ignored and the cache starts empty with success; a
// record cut short or a payload that does not verify fails the creation (VK_ERROR_INITIALIZATION_FAILED, the cereal
// exception path), nothing kept; each entry read is verified byte by byte (the hydration work, counted).
// vkMergePipelineCaches adds each source entry the destination lacks (MVKShaderLibraryCache::merge). Every call is
// counted per cache role (main / worker / staging).
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using Ryujinx.Common.Logging;
using Silk.NET.Vulkan;

namespace FixtureSupport {
    static class Events {
        private static readonly Stopwatch Clock = Stopwatch.StartNew();
        public static readonly List<(long Ms, string Thread, string Text)> List = new();
        public static void Add(string text) { lock (List) List.Add((Clock.ElapsedMilliseconds, Thread.CurrentThread.Name ?? "unnamed", text)); }
        public static (long Ms, string Thread, string Text)[] Snapshot() { lock (List) return List.ToArray(); }
        public static void Clear() { lock (List) List.Clear(); }
    }

    // The serialized form, shared by the double and the scenarios (which read files back to check their content).
    static class CacheFormat {
        public const int HeaderBytes = 32;
        public static byte Payload(ulong id, int index) => (byte)((id * 0x9E3779B1UL >> 7) + (ulong)index * 31);
        public static long Size(IReadOnlyDictionary<ulong, int> entries) => HeaderBytes + entries.Sum(e => 16L + e.Value) + 4;

        public static void Write(Span<byte> target, IReadOnlyDictionary<ulong, int> entries, uint vendor, uint device, byte[] uuid) {
            int offset = 0;
            U32(target, ref offset, HeaderBytes); U32(target, ref offset, 1); U32(target, ref offset, vendor); U32(target, ref offset, device);
            uuid.CopyTo(target.Slice(offset, 16)); offset += 16;
            foreach (var (id, length) in entries.OrderBy(e => e.Key)) {
                U32(target, ref offset, 1);
                BitConverter.TryWriteBytes(target.Slice(offset, 8), id); offset += 8;
                U32(target, ref offset, (uint)length);
                for (int i = 0; i < length; i++) target[offset + i] = Payload(id, i);
                offset += length;
            }
            U32(target, ref offset, 0);
        }

        private static void U32(Span<byte> target, ref int offset, uint value) { BitConverter.TryWriteBytes(target.Slice(offset, 4), value); offset += 4; }

        // null: refused (cut short or not verifying); empty with ignored = true: a header of another device or UUID.
        public static Dictionary<ulong, int> Read(ReadOnlySpan<byte> data, uint vendor, uint device, byte[] uuid, out bool ignored, out long verified) {
            ignored = false;
            verified = 0;
            var entries = new Dictionary<ulong, int>();
            if (data.Length < HeaderBytes + 4) { ignored = true; return entries; }
            if (BitConverter.ToUInt32(data.Slice(0)) != HeaderBytes || BitConverter.ToUInt32(data.Slice(4)) != 1 ||
                BitConverter.ToUInt32(data.Slice(8)) != vendor || BitConverter.ToUInt32(data.Slice(12)) != device ||
                !data.Slice(16, 16).SequenceEqual(uuid)) { ignored = true; return entries; }
            int offset = HeaderBytes;
            while (true) {
                if (offset + 4 > data.Length) return null;
                uint type = BitConverter.ToUInt32(data.Slice(offset)); offset += 4;
                if (type != 1) return entries;
                if (offset + 12 > data.Length) return null;
                ulong id = BitConverter.ToUInt64(data.Slice(offset)); offset += 8;
                int length = (int)BitConverter.ToUInt32(data.Slice(offset)); offset += 4;
                if (length < 0 || offset + length > data.Length) return null;
                for (int i = 0; i < length; i++) if (data[offset + i] != Payload(id, i)) return null;
                verified += length;
                offset += length;
                entries[id] = length;
            }
        }

        public static Dictionary<ulong, int> ReadFile(string path, uint vendor, uint device, byte[] uuid, out bool ignored) {
            if (!File.Exists(path)) { ignored = false; return new Dictionary<ulong, int>(); }
            return Read(File.ReadAllBytes(path), vendor, device, uuid, out ignored, out _);
        }
    }
}

namespace Silk.NET.Vulkan {
    struct Device { }
    struct PipelineCache { public ulong Handle; }
    struct AllocationCallbacks { }
    enum StructureType { PipelineCacheCreateInfo = 17 }
    [Flags] enum PipelineCacheCreateFlags { None = 0, ExternallySynchronizedBitExt = 1 }
    enum Result { Success = 0, PipelineCompileRequired = 1000297000, ErrorOutOfHostMemory = -1, ErrorOutOfDeviceMemory = -2,
                  ErrorInitializationFailed = -3, ErrorDeviceLost = -4 }
    unsafe struct PipelineCacheCreateInfo { public StructureType SType; public void* PNext; public PipelineCacheCreateFlags Flags;
                                            public nuint InitialDataSize; public void* PInitialData; }
    unsafe struct PhysicalDeviceProperties { public uint VendorID, DeviceID, DriverVersion; public fixed byte PipelineCacheUuid[16]; }

    unsafe class Vk {
        private readonly Dictionary<ulong, Dictionary<ulong, int>> _caches = new();
        private ulong _next;
        public ulong MainHandle;
        public Lock MainLock;
        public uint Vendor = 0x106B, DeviceId = 0x1A2B3C4D;
        public byte[] Uuid = Enumerable.Range(1, 16).Select(i => (byte)i).ToArray(); // MoltenVK revision, OS, GPU family
        public int SnapshotLoadMs;
        public bool FailMainData;      // vkGetPipelineCacheData of main fails (a write that cannot complete)
        public long InflateMainSize;   // main's size query reports this much more (over its budget)
        // A transient refusal of intact data (one Metal library failing to compile makes MoltenVK refuse the whole data):
        // the next SkipSnapshots creations with data are left alone, then the next RefuseIntact ones are refused.
        public int SkipSnapshots, RefuseIntact;
        public long HydratedBytes, HydratedEntries, IgnoredSnapshots, RefusedSnapshots, MergedSourceEntries, MergeAddedEntries;
        public readonly Dictionary<string, long> WrittenBytes = new();
        public readonly List<string> Snapshots = new();
        public void ResetCounters() {
            lock (_caches) {
                HydratedBytes = HydratedEntries = IgnoredSnapshots = RefusedSnapshots = MergedSourceEntries = MergeAddedEntries = 0;
                WrittenBytes.Clear(); Snapshots.Clear();
            }
        }
        public void Add(PipelineCache cache, ulong id, int length) { lock (_caches) _caches[cache.Handle][id] = length; }
        public Dictionary<ulong, int> Entries(PipelineCache cache) { lock (_caches) return new(_caches[cache.Handle]); }
        private string Name(ulong handle) => handle == MainHandle ? "main" : "other";

        public Result CreatePipelineCache(Device device, in PipelineCacheCreateInfo info, AllocationCallbacks* allocator, out PipelineCache cache) {
            var entries = new Dictionary<ulong, int>();
            if (info.InitialDataSize > 0) {
                if (SnapshotLoadMs > 0) Thread.Sleep(SnapshotLoadMs);
                bool refuse = false;
                lock (_caches) {
                    if (SkipSnapshots > 0) SkipSnapshots--;
                    else if (RefuseIntact > 0) { RefuseIntact--; refuse = true; RefusedSnapshots++; Snapshots.Add($"{info.InitialDataSize}:refusedOnce"); }
                }
                if (refuse) { cache = default; return Result.ErrorInitializationFailed; }
                var read = FixtureSupport.CacheFormat.Read(new ReadOnlySpan<byte>(info.PInitialData, (int)info.InitialDataSize),
                                                            Vendor, DeviceId, Uuid, out bool ignored, out long verified);
                lock (_caches) {
                    Snapshots.Add($"{info.InitialDataSize}:{(read == null ? "refused" : ignored ? "ignored" : "read")}");
                    HydratedBytes += verified;
                    if (read != null) HydratedEntries += read.Count;
                    if (ignored) IgnoredSnapshots++;
                    if (read == null) RefusedSnapshots++;
                }
                if (read == null) { cache = default; return Result.ErrorInitializationFailed; }
                entries = read;
            }
            lock (_caches) { cache = new PipelineCache { Handle = ++_next }; _caches[cache.Handle] = entries; }
            if (MainHandle == 0) MainHandle = cache.Handle; // PipelineCacheManager creates main first
            return Result.Success;
        }
        public void DestroyPipelineCache(Device device, PipelineCache cache, AllocationCallbacks* allocator) {
            lock (_caches) _caches.Remove(cache.Handle);
        }
        public Result MergePipelineCaches(Device device, PipelineCache destination, uint count, PipelineCache* sources) {
            lock (_caches) {
                var target = _caches[destination.Handle];
                for (int i = 0; i < count; i++) {
                    foreach (var (id, length) in _caches[sources[i].Handle]) {
                        MergedSourceEntries++;
                        if (target.TryAdd(id, length)) MergeAddedEntries++;
                    }
                }
            }
            return Result.Success;
        }
        public Result GetPipelineCacheData(Device device, PipelineCache cache, nuint* size, void* data) {
            bool main = cache.Handle == MainHandle;
            if (main && FailMainData && data != null) return Result.ErrorOutOfHostMemory;
            Dictionary<ulong, int> entries;
            lock (_caches) entries = new(_caches[cache.Handle]);
            long bytes = FixtureSupport.CacheFormat.Size(entries);
            if (data == null) { *size = (nuint)(bytes + (main ? InflateMainSize : 0)); return Result.Success; }
            if ((long)*size < bytes) return Result.ErrorOutOfHostMemory;
            FixtureSupport.CacheFormat.Write(new Span<byte>(data, (int)bytes), entries, Vendor, DeviceId, Uuid);
            *size = (nuint)bytes;
            lock (_caches) { string role = main ? "main" : "worker"; WrittenBytes[role] = WrittenBytes.GetValueOrDefault(role) + bytes; }
            return Result.Success;
        }
        public void DeviceWaitIdle(Device device) { }
    }
}

namespace Ryujinx.Common.Configuration { static class AppDataManager { public static string BaseDirPath; } }
namespace Ryujinx.Common.Logging {
    enum LogClass { Gpu }
    class Sink {
        public readonly List<string> Messages = new();
        public void PrintMsg(LogClass c, string message) { lock (Messages) Messages.Add(message); }
    }
    static class Logger { public static Sink Warning = new(), Error = new(), Info = new(), Notice = new(); }
}
namespace Ryujinx.Common {
    static class EmbeddedLaunchDiagnostics {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        { lock (Records) Records.Add(stage + " " + status + " " + detail); }
    }
    sealed class EmbeddedStartupTrace : IDisposable { public EmbeddedStartupTrace(string stage) { } public void Dispose() { } }
    static class EmbeddedPerformanceDiagnostics {
        public enum Phase { CacheSizeProbe, CacheSave }
        public enum Counter { CacheExports, CacheExportBytes }
        public readonly struct Scope : IDisposable { public void Dispose() { } }
        public static Scope Measure(Phase phase) => new();
        public static void Count(Counter counter, long amount = 1) { }
    }
}
namespace Ryujinx.Graphics.GAL.Multithreading { static class HostThreadQos { public static void RaiseCurrentThread() { } } }

namespace Ryujinx.Graphics.Vulkan {
    class VulkanPhysicalDevice {
        public PhysicalDeviceProperties PhysicalDeviceProperties;
        public bool SupportsPipelineCreationCacheControl(Vk api) => true;
    }
    static class VulkanRenderer { public static Func<string> PipelineCacheScope; }
}
