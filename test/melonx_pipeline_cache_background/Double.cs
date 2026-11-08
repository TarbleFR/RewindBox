// Doubles for melonx_pipeline_cache_background_test.py (from test/melonx_main_cache_checkpoint/Double.cs, plus a snapshot
// creation that takes SnapshotLoadMs, as MoltenVK compiling every Metal library of the snapshot, and RejectSnapshot).
// Originally: doubles for melonx_main_cache_checkpoint_test.py, compiled with the variant's real PipelineCacheManager.cs and
// VulkanException.cs. Vulkan is a host double (from test/melonx_teardown_cache/Double.cs): each VkPipelineCache is a byte
// count, vkGetPipelineCacheData writes that many bytes, and every call is recorded with its thread and whether the main
// cache lock is held.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
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
    struct PhysicalDeviceProperties { public uint VendorID, DeviceID, DriverVersion; }

    unsafe class Vk {
        private const long Header = 32; // a Vulkan pipeline cache always holds its header
        private readonly Dictionary<ulong, long> _sizes = new();
        private ulong _next;
        public ulong MainHandle;
        public Lock MainLock;
        public int SlowMainDataMs;
        public int Idles;
        public long Size(PipelineCache cache) { lock (_sizes) return _sizes[cache.Handle]; }
        public void Grow(PipelineCache cache, long bytes) { lock (_sizes) _sizes[cache.Handle] += bytes; }
        private string Name(ulong handle) => handle == MainHandle ? "main" : "worker";
        public int SnapshotLoadMs;
        public bool RejectSnapshot;
        public int Destroyed;
        public Result CreatePipelineCache(Device device, in PipelineCacheCreateInfo info, AllocationCallbacks* allocator, out PipelineCache cache) {
            if (info.InitialDataSize > 0) {
                FixtureSupport.Events.Add($"snapshot begin {info.InitialDataSize}");
                if (SnapshotLoadMs > 0) Thread.Sleep(SnapshotLoadMs);
                FixtureSupport.Events.Add("snapshot end");
                if (RejectSnapshot) { cache = default; return Result.ErrorInitializationFailed; }
            }
            lock (_sizes) { cache = new PipelineCache { Handle = ++_next }; _sizes[cache.Handle] = Math.Max(Header, (long)info.InitialDataSize); }
            if (MainHandle == 0) MainHandle = cache.Handle; // PipelineCacheManager creates main first
            return Result.Success;
        }
        public void DestroyPipelineCache(Device device, PipelineCache cache, AllocationCallbacks* allocator) {
            FixtureSupport.Events.Add($"destroy {Name(cache.Handle)}");
            lock (_sizes) { _sizes.Remove(cache.Handle); Destroyed++; }
        }
        public Result MergePipelineCaches(Device device, PipelineCache destination, uint count, PipelineCache* sources) {
            FixtureSupport.Events.Add($"merge into {Name(destination.Handle)} {count} lockHeld={MainLock.IsHeldByCurrentThread}");
            lock (_sizes) for (int i = 0; i < count; i++) _sizes[destination.Handle] += _sizes[sources[i].Handle] - Header;
            return Result.Success;
        }
        public Result GetPipelineCacheData(Device device, PipelineCache cache, nuint* size, void* data) {
            long bytes = Size(cache);
            if (data == null) { *size = (nuint)bytes; return Result.Success; }
            bool main = cache.Handle == MainHandle;
            FixtureSupport.Events.Add($"data {Name(cache.Handle)} begin lockHeld={MainLock.IsHeldByCurrentThread}");
            if (main && SlowMainDataMs > 0) Thread.Sleep(SlowMainDataMs);
            long count = Math.Min(bytes, (long)*size);
            new Span<byte>(data, (int)count).Fill(0x5A);
            *size = (nuint)count;
            FixtureSupport.Events.Add($"data {Name(cache.Handle)} end");
            return Result.Success;
        }
        public void DeviceWaitIdle(Device device) { Idles++; FixtureSupport.Events.Add("deviceIdle"); }
    }
}

namespace Ryujinx.Common.Configuration { static class AppDataManager { public static string BaseDirPath; } }
namespace Ryujinx.Common.Logging {
    enum LogClass { Gpu }
    class Sink {
        public int Lines;
        public readonly List<string> Messages = new();
        public void PrintMsg(LogClass c, string message) { lock (Messages) { Lines++; Messages.Add(message); } }
    }
    static class Logger { public static Sink Warning = new(), Error = new(), Info = new(), Notice = new(); }
}
namespace Ryujinx.Common {
    static class EmbeddedLaunchDiagnostics {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        { lock (Records) Records.Add(stage + " " + status + " " + detail); FixtureSupport.Events.Add("journal " + stage + " " + status); }
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
