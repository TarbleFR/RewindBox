using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common.Logging;
using Silk.NET.Vulkan;

namespace Silk.NET.Vulkan { struct PipelineCache { } }
namespace Ryujinx.Common.Logging {
    enum LogClass { Gpu }
    class Sink { public void PrintMsg(LogClass c, string message) { } }
    static class Logger { public static Sink Warning = new(), Error = new(); }
}
namespace Ryujinx.Graphics.Vulkan {
    class PipelineCacheManager {
        public PipelineCache GetWorkerCache(int index) => new();
        public void NotifyWorkerPipelineCreated(int index) { }
    }
    enum ProgramLinkStatus { Incomplete, Success, Failure }
    class VulkanException : Exception { }
    class Shader {
        public ProgramLinkStatus CompileStatus = ProgramLinkStatus.Success;
        public void PromoteCompilation() { }
    }
    class VulkanRenderer {
        public BackgroundCompilationScheduler BackgroundCompilationScheduler = new(new());
        public HashSet<ShaderCollection> Shaders = new();
        public volatile bool Released;
        private bool _initialized = true;
        public void Close() {
            /* RENDERER_CLOSE_PREFIX */
            Released = true;
        }
    }
    class ShaderCollection {
        private readonly VulkanRenderer _gd;
        private readonly bool _detachedWarmUp;
        private int _cancelUndemandedWarmUp;
        private int _backgroundCompilationDemanded;
        private bool _highPriorityBackgroundCompilation;
        private Task _initialPipelineCompileTask;
        private Task _compileTask;
        private Task[] _shaderCompileTasks;
        private Shader[] _shaders = [new()];
        public bool CompilesInBackground = true, IsCompute;
        public ProgramLinkStatus LinkStatus;
        public int NativeCompiles;
        public Action CompileAction = () => { };
        public Task Completion => _compileTask;
        public Task Pending => Volatile.Read(ref _initialPipelineCompileTask);
        public ShaderCollection(VulkanRenderer gd, Task modules, bool detached = true) {
            _gd = gd;
            _detachedWarmUp = detached;
            _shaderCompileTasks = [modules];
            gd.Shaders.Add(this);
        }
        public void Start() { _compileTask = BackgroundCompilation(); }
        private async Task<bool> WaitForShaderModuleCompilation() {
            await Task.WhenAll(_shaderCompileTasks);
            return true;
        }
        private void CreateBackgroundComputePipeline(PipelineCache cache = default) => CreateBackgroundGraphicsPipeline(cache);
        private void CreateBackgroundGraphicsPipeline(PipelineCache cache = default) {
            if (_gd.Released) throw new Exception("Pipeline used released renderer");
            Interlocked.Increment(ref NativeCompiles);
            CompileAction();
        }
        private void ClearInitialBackgroundPipelineTask() { }
        private void WaitForBackgroundPipelineQueue() { }
        /* SHADER_METHODS */
    }
}
