// Doubles for melonx_guest_stop_compile_cancel_test.py. The real BackgroundCompilationScheduler, the real
// ShaderCollection warm-up methods and the real wait of ShaderCollection.Dispose (from CancelPendingWarmUp to the first
// module release), the real VulkanRenderer.BeginTeardown and, in the candidate, the real
// VulkanRenderer.CancelCompilesAtGuestStop are compiled with these doubles; a native compile is a controllable delay.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common.Logging;
using Silk.NET.Vulkan;

namespace Silk.NET.Vulkan { struct PipelineCache { } enum Result { Success, ErrorDeviceLost, ErrorOutOfHostMemory, ErrorOutOfDeviceMemory } }
namespace Ryujinx.Common.Logging {
    enum LogClass { Gpu }
    class Sink { public int Lines; public void PrintMsg(LogClass c, string message) { Interlocked.Increment(ref Lines); } }
    static class Logger { public static Sink Warning = new(), Error = new(); }
}
namespace Ryujinx.Common {
    static class EmbeddedLaunchDiagnostics {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        { lock (Records) Records.Add(stage + " " + status + " " + detail); }
    }
}
namespace Ryujinx.Graphics.GAL.Multithreading {
    static class HostThreadQos { public static void RaiseCurrentThread() { } }
}
namespace Ryujinx.Graphics.GAL.Multithreading.Resources {
    static class RenderThreadPrograms { public static bool Bound => false; public static int CreateQueued() => 0; }
}
namespace Ryujinx.Graphics.Vulkan {
    class PipelineCacheManager {
        public int Saves;
        public volatile bool SavedWhileCompiling;
        public Func<bool> Compiling = () => false;
        public long ContentGeneration => 1;
        public void MergeAndSave() { if (Compiling()) SavedWhileCompiling = true; Saves++; }
        public PipelineCache GetWorkerCache(int index) => new();
        public void NotifyWorkerPipelineCreated(int index) { }
    }
    enum ProgramLinkStatus { Incomplete, Success, Failure }
    class VulkanException : Exception { public Result ResultCode; }
    class Shader {
        public ProgramLinkStatus CompileStatus = ProgramLinkStatus.Success;
        public Task CompileTask = Task.CompletedTask;
        private readonly VulkanRenderer _gd;
        public Shader(VulkanRenderer gd) { _gd = gd; }
        public void PromoteCompilation() { _gd.BackgroundCompilationScheduler.PromoteShaderCompile(CompileTask); }
    }
    class VulkanRenderer {
        public PipelineCacheManager PipelineCacheManager = new();
        internal BackgroundCompilationScheduler BackgroundCompilationScheduler { get; private set; }
        public VulkanRenderer() { BackgroundCompilationScheduler = new(PipelineCacheManager); }
        public HashSet<ShaderCollection> Shaders = new();
        private bool _initialized = true;
        private int _teardownBegun;
        private long _teardownSavedGeneration = -1;
        internal bool TeardownBegun => Volatile.Read(ref _teardownBegun) != 0;
        public void ThrowIfBackgroundPipelineFailed() { }
        public void RecordBackgroundPipelineFailure(Exception e) { Failures++; }
        public int Failures;
        // The candidate's guest-stop cancellation; the control has none.
        public bool GuestStop(out int shaderModules, out int pipelines) {
            shaderModules = pipelines = -1;
            /* GUEST_STOP_CALL */
        }
        /* RENDERER_METHODS */
    }
    class ShaderCollection {
        private readonly VulkanRenderer _gd;
        private readonly bool _detachedWarmUp;
        private readonly object _pipelineCacheLock = new();
        private readonly List<Task> _queuedPipelines = new();
        private int _cancelUndemandedWarmUp;
        private int _backgroundCompilationDemanded;
        private bool _highPriorityBackgroundCompilation;
        private Task _initialPipelineCompileTask;
        private Task _compileTask = Task.CompletedTask;
        private Task[] _shaderCompileTasks;
        private Shader[] _shaders;
        public bool CompilesInBackground = true, IsCompute;
        public ProgramLinkStatus LinkStatus;
        public static int NativeCompiles, ModuleCompiles, Running;
        public static int CompileMs = 20, ModuleMs = 10;
        public ShaderCollection(VulkanRenderer gd, bool detached, bool queuedModule) {
            _gd = gd;
            _detachedWarmUp = detached;
            _shaders = [new Shader(gd)];
            if (queuedModule) {
                _shaders[0].CompileStatus = ProgramLinkStatus.Incomplete;
                Shader shader = _shaders[0];
                shader.CompileTask = gd.BackgroundCompilationScheduler.ScheduleShaderCompile(() => {
                    Interlocked.Increment(ref Running);
                    try { Thread.Sleep(ModuleMs); Interlocked.Increment(ref ModuleCompiles); shader.CompileStatus = ProgramLinkStatus.Success; }
                    finally { Interlocked.Decrement(ref Running); }
                });
            }
            _shaderCompileTasks = [_shaders[0].CompileTask];
            gd.Shaders.Add(this);
        }
        public void Start() { _compileTask = BackgroundCompilation(); }
        // A play-time pipeline compile queued for this program (QueueBackgroundGraphicsPipeline's queue).
        public Task QueuePlayTimePipeline() {
            Task task = _gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => CreateBackgroundGraphicsPipeline());
            lock (_pipelineCacheLock) _queuedPipelines.Add(task);
            return task;
        }
        private void CancelVariantReplays() { }
        // As the real method for one module per program: linked once its module is compiled, never after a failure.
        private bool EnsureShadersReady(bool blocking) {
            if (LinkStatus == ProgramLinkStatus.Failure) return false;
            if (_shaders[0].CompileStatus != ProgramLinkStatus.Success) { LinkStatus = ProgramLinkStatus.Failure; return false; }
            LinkStatus = ProgramLinkStatus.Success;
            return true;
        }
        private void CreateBackgroundComputePipeline(PipelineCache cache = default) => CreateBackgroundGraphicsPipeline(cache);
        private void CreateBackgroundGraphicsPipeline(PipelineCache cache = default) {
            Interlocked.Increment(ref Running);
            try { Thread.Sleep(CompileMs); Interlocked.Increment(ref NativeCompiles); }
            finally { Interlocked.Decrement(ref Running); }
        }
        private void ClearInitialBackgroundPipelineTask() { }
        // As the real method: every pipeline task queued for this program, waited together.
        private void WaitForBackgroundPipelineQueue() {
            Task[] tasks;
            lock (_pipelineCacheLock) tasks = _queuedPipelines.ToArray();
            if (tasks.Length != 0) Task.WaitAll(tasks);
        }
        // ShaderCollection.Dispose as the render loop's drain runs it, up to the first module release.
        public void DisposeAtDrain() {
            _gd.Shaders.Remove(this);
            /* DISPOSE_WAIT */
        }
        /* SHADER_METHODS */
    }
}
