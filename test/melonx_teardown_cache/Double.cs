// Doubles for melonx_teardown_cache_test.py. Compiled with them, unchanged, from the variant's prepared tree: the whole
// PipelineCacheManager.cs, BackgroundCompilationScheduler.cs and VulkanException.cs; the ShaderCollection warm-up, wait and
// Dispose(bool) members (Dispose up to the release of its shader modules); the VulkanRenderer members the adapter adds and
// the Dispose prefix up to its first release (CommandBufferPool.Dispose); WindowBase's pause control (and the candidate's
// teardown hook) and the body of its GPU release callback. Vulkan is a host double: each VkPipelineCache is a byte count,
// vkGetPipelineCacheData writes that many bytes, and every call is recorded with its thread and whether the main cache lock
// is held. Native pipeline compilation is a controllable delay.
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
        public Result CreatePipelineCache(Device device, in PipelineCacheCreateInfo info, AllocationCallbacks* allocator, out PipelineCache cache) {
            lock (_sizes) { cache = new PipelineCache { Handle = ++_next }; _sizes[cache.Handle] = Math.Max(Header, (long)info.InitialDataSize); }
            if (MainHandle == 0) MainHandle = cache.Handle; // PipelineCacheManager creates main first
            return Result.Success;
        }
        public void DestroyPipelineCache(Device device, PipelineCache cache, AllocationCallbacks* allocator) {
            lock (_sizes) _sizes.Remove(cache.Handle);
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
    enum ProgramLinkStatus { Incomplete, Success, Failure }
    class Shader {
        public ProgramLinkStatus CompileStatus = ProgramLinkStatus.Success;
        public void PromoteCompilation() { }
    }
    class VulkanRenderer {
        public static Func<string> PipelineCacheScope;
        public readonly Vk Api;
        private Device _device;
        internal Lock PipelineCreationLock { get; } = new();
        internal PipelineCacheManager PipelineCacheManager { get; }
        internal BackgroundCompilationScheduler BackgroundCompilationScheduler { get; }
        internal HashSet<ShaderCollection> Shaders { get; } = new();
        public volatile bool Released;
        private bool _initialized = true;
        public VulkanRenderer(Vk api) {
            Api = api;
            api.MainLock = PipelineCreationLock;
            api.MainHandle = 0;
            PipelineCacheManager = new(api, new VulkanPhysicalDevice(), _device, BackgroundCompilationScheduler.PipelineCacheCount, PipelineCreationLock);
            BackgroundCompilationScheduler = new(PipelineCacheManager);
        }
        public void ThrowIfBackgroundPipelineFailed() { }
        public void RecordBackgroundPipelineFailure(Exception e) { }
        /* RENDERER_MEMBERS */
        public void Close() {
            FixtureSupport.Events.Add("rendererDispose");
            /* RENDERER_CLOSE_PREFIX */
            Released = true;
        }
    }
    class ShaderCollection {
        private readonly VulkanRenderer _gd;
        private readonly bool _detachedWarmUp;
        private readonly object _pipelineCacheLock = new();
        private readonly List<Task> _queuedPipelines = new();
        private bool _disposed;
        private int _cancelUndemandedWarmUp;
        private int _backgroundCompilationDemanded;
        private bool _highPriorityBackgroundCompilation;
        private Task _initialPipelineCompileTask;
        private Task _compileTask = Task.CompletedTask;
        private Task[] _shaderCompileTasks;
        private Shader[] _shaders = [new()];
        public bool CompilesInBackground = true, IsCompute;
        public ProgramLinkStatus LinkStatus;
        public int NativeCompiles;
        public Action<PipelineCache> CompileAction;
        public ShaderCollection(VulkanRenderer gd, Task modules, bool detached = true) {
            _gd = gd;
            _detachedWarmUp = detached;
            _shaderCompileTasks = [modules];
            // A native compile writes its pipeline into the cache it was given (a worker cache) and takes 20 ms.
            CompileAction = cache => { gd.Api.Grow(cache, 4096); Thread.Sleep(20); };
            gd.Shaders.Add(this);
        }
        public void Start() { _compileTask = BackgroundCompilation(); }
        // A play-time pipeline queued for this program, as QueueBackgroundGraphicsPipeline/CompileQueuedGraphicsPipeline do:
        // demanded, high priority, and a failure (a cancellation included) only marks the key.
        public Task QueuePlayTimePipeline() {
            Task task = CompileQueued();
            lock (_pipelineCacheLock) _queuedPipelines.Add(task);
            return task;
        }
        private async Task CompileQueued() {
            try { await RunBackgroundPipelineCompile(cache => CreateBackgroundGraphicsPipeline(cache), highPriority: true, demanded: true); }
            catch (Exception) { }
        }
        // GpuContext.Dispose -> ShaderCache.Dispose -> ProgramDisposeCommand -> ShaderCollection.Dispose, on the render thread.
        public void Dispose() {
            FixtureSupport.Events.Add("programDispose");
            Dispose(true);
        }
        private bool EnsureShadersReady(bool blocking) => true;
        private void CreateBackgroundComputePipeline(PipelineCache cache = default) => CreateBackgroundGraphicsPipeline(cache);
        private void CreateBackgroundGraphicsPipeline(PipelineCache cache = default) {
            if (_gd.Released) throw new Exception("Pipeline used released renderer");
            Interlocked.Increment(ref NativeCompiles);
            CompileAction(cache);
        }
        private void ClearInitialBackgroundPipelineTask() { }
        // As the real method: every pipeline task queued for this program, waited together.
        private void WaitForBackgroundPipelineQueue() {
            Task[] tasks;
            lock (_pipelineCacheLock) tasks = _queuedPipelines.ToArray();
            if (tasks.Length != 0) Task.WaitAll(tasks);
        }
        /* SHADER_METHODS */
    }
}

namespace Ryujinx.Library {
    class FakeLifetime {
        public volatile bool Paused, Requested;
        public void SetPaused(bool paused) { if (!Requested) Paused = paused; }
        public bool InputAllowed => !Requested;
    }
    class FakeDevice {
        public Action DisposeGpuAction = () => { };
        public void DisposeGpu() { FixtureSupport.Events.Add("disposeGpu"); DisposeGpuAction(); }
    }
    class Window {
        public object Renderer;
        public FakeDevice Device = new();
        public FakeLifetime _embeddedLifetime = new();
        public bool EmbeddedGpuReleased { get; private set; }
        public int Finalized;
        private void FinalizeWindowRenderer() { Finalized++; }
        /* WINDOW_MEMBERS */
        public void Release() {
            /* WINDOW_RELEASE */
        }
    }
}
