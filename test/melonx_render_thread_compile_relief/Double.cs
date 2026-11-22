// Doubles for melonx_render_thread_compile_relief_test.py. The real BackgroundCompilationScheduler (with, in the
// candidate, its prebuild queue and SkippableDrawWait) and the real ShaderCollection members
// TryWaitForBackgroundComputePipeline and, in the candidate, TryWaitBrieflyForQueuedGraphicsPipeline are compiled with
// these doubles; a native compile is a controllable delay.
using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Silk.NET.Vulkan;

namespace Silk.NET.Vulkan { struct PipelineCache { } }
namespace Ryujinx.Graphics.GAL.Multithreading {
    static class HostThreadQos { public static void RaiseCurrentThread() { } }
}
namespace Ryujinx.Graphics.GAL.Multithreading.Resources {
    static class RenderThreadPrograms { public static bool Bound => false; public static int CreateQueued() => 0; }
}
namespace Ryujinx.Graphics.Vulkan {
    class PipelineCacheManager {
        public PipelineCache GetWorkerCache(int index) => new();
        public void NotifyWorkerPipelineCreated(int index) { }
    }
    struct PipelineUid { public int Id; }
    struct SpecData { public int Id; }
    class DisposablePipeline { }
    class Auto<T> { public T Value; }
    // HashTableSlim's two members the real methods use.
    class Table<TKey, TValue> where TKey : struct {
        private readonly Dictionary<TKey, TValue> _items = new();
        public bool TryGetValue(ref TKey key, out TValue value) => _items.TryGetValue(key, out value);
        public void Add(ref TKey key, TValue value) { _items[key] = value; }
    }
    class VulkanRenderer {
        public PipelineCacheManager PipelineCacheManager = new();
        internal BackgroundCompilationScheduler BackgroundCompilationScheduler { get; }
        public VulkanRenderer() { BackgroundCompilationScheduler = new(PipelineCacheManager); }
        public void ThrowIfBackgroundPipelineFailed() { }
    }
    class ShaderCollection {
        private readonly VulkanRenderer _gd;
        private readonly object _pipelineCacheLock = new();
        private readonly bool _playTimeWarmUp;
        private Table<PipelineUid, Task> _graphicsPipelineBackgroundQueue;
        private Table<SpecData, Task> _computePipelineBackgroundQueue;
        private readonly Dictionary<int, Auto<DisposablePipeline>> _graphics = new(), _compute = new();
        public int Promotions, NativeCompiles;
        public ShaderCollection(VulkanRenderer gd, bool playTimeWarmUp) { _gd = gd; _playTimeWarmUp = playTimeWarmUp; }
        // As the real method: the program's queued warm-up moves to the demanded queue.
        public void PromoteBackgroundCompilation() { Interlocked.Increment(ref Promotions); if (_warmUp != null) _gd.BackgroundCompilationScheduler.PromotePipelineCompile(_warmUp); }
        public bool TryGetGraphicsPipeline(ref PipelineUid key, out Auto<DisposablePipeline> pipeline) { lock (_pipelineCacheLock) return _graphics.TryGetValue(key.Id, out pipeline); }
        public bool TryGetComputePipeline(ref SpecData key, out Auto<DisposablePipeline> pipeline) { lock (_pipelineCacheLock) return _compute.TryGetValue(key.Id, out pipeline); }
        // A compile queued for a skipped draw (demanded), as CompileQueuedGraphicsPipeline queues it.
        public Task QueueGraphics(int id, int compileMs) {
            PipelineUid key = new() { Id = id };
            Task task = _gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => {
                Thread.Sleep(compileMs); Interlocked.Increment(ref NativeCompiles);
                lock (_pipelineCacheLock) _graphics[id] = new();
            }, highPriority: true, demanded: true);
            lock (_pipelineCacheLock) (_graphicsPipelineBackgroundQueue ??= new()).Add(ref key, task);
            return task;
        }
        // The warm-up of a compute program, registered under its key at construction (low priority when cached).
        public Task QueueComputeWarmUp(int id, int compileMs, bool highPriority) {
            SpecData key = new() { Id = id };
            Task task = _gd.BackgroundCompilationScheduler.SchedulePipelineCompile(_ => {
                Thread.Sleep(compileMs); Interlocked.Increment(ref NativeCompiles);
                lock (_pipelineCacheLock) _compute[id] = new();
            }, highPriority);
            lock (_pipelineCacheLock) (_computePipelineBackgroundQueue ??= new()).Add(ref key, task);
            _warmUp = task;
            return task;
        }
        private Task _warmUp;
        // What PipelineBase does when the wait gives nothing: the dispatch creates the pipeline itself.
        public void CreateComputeOnRenderThread(int id, int compileMs) {
            Thread.Sleep(compileMs); Interlocked.Increment(ref NativeCompiles);
            lock (_pipelineCacheLock) _compute[id] = new();
        }
        /* SHADER_METHODS */
    }
}
