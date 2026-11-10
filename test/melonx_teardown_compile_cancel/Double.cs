// Doubles for melonx_teardown_compile_cancel_test.py. The real BackgroundCompilationScheduler, the real
// VulkanRenderer.Dispose prefix (up to the first release, CommandBufferPool.Dispose) and the real ShaderCollection warm-up/wait methods are compiled
// with these doubles (up to the pipeline cache save); native pipeline compilation is a controllable delay.
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
namespace Ryujinx.Graphics.Vulkan {
    class FakeApi { public int Idles; public void DeviceWaitIdle(object device) { Idles++; } }
    class PipelineCacheManager {
        public int Saves;
        public void MergeAndSave() { Saves++; }
        public PipelineCache GetWorkerCache(int index) => new();
        public void NotifyWorkerPipelineCreated(int index) { }
    }
    enum ProgramLinkStatus { Incomplete, Success, Failure }
    class VulkanException : Exception { public Result ResultCode; }
    class Shader {
        public ProgramLinkStatus CompileStatus = ProgramLinkStatus.Success;
        public void PromoteCompilation() { }
    }
    class VulkanRenderer {
        public PipelineCacheManager PipelineCacheManager = new();
        public FakeApi Api = new();
        private object _device = new();
        public BackgroundCompilationScheduler BackgroundCompilationScheduler;
        public VulkanRenderer() { BackgroundCompilationScheduler = new(PipelineCacheManager); }
        public HashSet<ShaderCollection> Shaders = new();
        public volatile bool Released;
        private bool _initialized = true;
        public void ThrowIfBackgroundPipelineFailed() { }
        public void RecordBackgroundPipelineFailure(Exception e) { }
        public void Close() {
            /* RENDERER_CLOSE_PREFIX */
            Released = true;
        }
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
        private Shader[] _shaders = [new()];
        public bool CompilesInBackground = true, IsCompute;
        public ProgramLinkStatus LinkStatus;
        public int NativeCompiles;
        public Action CompileAction = () => { };
        public Task Completion => _compileTask;
        public ShaderCollection(VulkanRenderer gd, Task modules, bool detached = true) {
            _gd = gd;
            _detachedWarmUp = detached;
            _shaderCompileTasks = [modules];
            gd.Shaders.Add(this);
        }
        public void Start() { _compileTask = BackgroundCompilation(); }
        // A play-time pipeline compile queued for this program (QueueBackgroundGraphicsPipeline's queue).
        public Task QueuePlayTimePipeline(bool demanded = false) {
            Task task = _gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => CreateBackgroundGraphicsPipeline(), demanded: demanded);
            lock (_pipelineCacheLock) _queuedPipelines.Add(task);
            return task;
        }
        private bool EnsureShadersReady(bool blocking) => true;
        private void CreateBackgroundComputePipeline(PipelineCache cache = default) => CreateBackgroundGraphicsPipeline(cache);
        private void CreateBackgroundGraphicsPipeline(PipelineCache cache = default) {
            if (_gd.Released) throw new Exception("Pipeline used released renderer");
            Interlocked.Increment(ref NativeCompiles);
            CompileAction();
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
