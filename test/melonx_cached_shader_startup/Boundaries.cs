using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Runtime.ExceptionServices;
using System.Runtime.InteropServices;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Common.Logging;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;

// Native GPU entry points and state packing are the controlled test boundary.
// The fixture does not emulate Vulkan compilation or claim a GPU timing.
namespace shaderc { class Result { } }
namespace Silk.NET.Vulkan
{
    enum Result { Success = 0, PipelineCompileRequired = 1000297000, ErrorUnknown = -13,
        ErrorDeviceLost = -4, ErrorOutOfHostMemory = -1, ErrorOutOfDeviceMemory = -2 }
    enum ShaderStageFlags { VertexBit = 1, TessellationControlBit = 2, TessellationEvaluationBit = 4,
        GeometryBit = 8, FragmentBit = 16, ComputeBit = 32 }
    enum StructureType { ShaderModuleCreateInfo, PipelineShaderStageCreateInfo }
    enum PipelineStageFlags { None }
    enum PipelineBindPoint { Compute, Graphics }
    struct Device { }
    struct PipelineLayout { }
    struct RenderPass { public ulong Handle; }
    struct Pipeline { public ulong Handle; }
    struct PipelineCache { public int Index; }
    struct ShaderModule { public ulong Handle; }
    unsafe struct ShaderModuleCreateInfo { public StructureType SType; public uint CodeSize; public uint* PCode; }
    unsafe struct PipelineShaderStageCreateInfo
    {
        public StructureType SType;
        public ShaderStageFlags Stage;
        public ShaderModule Module;
        public byte* PName;
    }
    sealed class Vk
    {
        private long _nextModule;
        public Action<int> ModuleAction = _ => { };
        public readonly ConcurrentDictionary<ulong, int> Modules = new();
        public int ModuleCalls, DestroyedModules, BoundPipelines;
        public unsafe Result CreateShaderModule(Device device, in ShaderModuleCreateInfo info, void* allocator, out ShaderModule module)
        {
            Interlocked.Increment(ref ModuleCalls);
            int id = (int)*info.PCode;
            ModuleAction(id);
            module = new ShaderModule { Handle = (ulong)Interlocked.Increment(ref _nextModule) };
            Modules.TryAdd(module.Handle, id);
            return Result.Success;
        }
        public unsafe void DestroyShaderModule(Device device, ShaderModule module, void* allocator)
        {
            if (!Modules.TryRemove(module.Handle, out _)) throw new Exception("Module disposed twice");
            Interlocked.Increment(ref DestroyedModules);
        }
        public void CmdBindPipeline(object commandBuffer, PipelineBindPoint point, Pipeline pipeline)
        {
            if (pipeline.Handle == 0) throw new Exception("Bound null pipeline");
            Interlocked.Increment(ref BoundPipelines);
        }
    }
}
namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink
    {
        public readonly ConcurrentQueue<string> Messages = new();
        public void PrintMsg(LogClass kind, string message) => Messages.Enqueue(message);
        public void Print(LogClass kind, string message) => Messages.Enqueue(message);
    }
    static class Logger { public static Sink Warning = new(), Error = new(), Debug = new(); }
}
namespace Ryujinx.Graphics.GAL
{
    interface IProgram : IDisposable { }
    public struct ProgramPipelineState { public int Key; }
}
namespace Ryujinx.Graphics.Vulkan
{
    static class Conversion
    {
        public static ShaderStageFlags Convert(this ShaderStage stage) => stage switch
        {
            ShaderStage.Compute => ShaderStageFlags.ComputeBit,
            ShaderStage.Vertex => ShaderStageFlags.VertexBit,
            ShaderStage.Fragment => ShaderStageFlags.FragmentBit,
            ShaderStage.Geometry => ShaderStageFlags.GeometryBit,
            ShaderStage.TessellationControl => ShaderStageFlags.TessellationControlBit,
            _ => ShaderStageFlags.TessellationEvaluationBit,
        };
        public static PipelineState ToVulkanPipelineState(this ProgramPipelineState state, VulkanRenderer gd)
        {
            var pipeline = new PipelineState { Internal = new PipelineUid { Key = state.Key } };
            pipeline.Initialize();
            return pipeline;
        }
    }
    struct PipelineUid : IRefEquatable<PipelineUid>
    {
        public int Key;
        public bool Equals(ref PipelineUid other) => Key == other.Key;
        public override int GetHashCode() => Key;
    }
    struct SpecData : IRefEquatable<SpecData>
    {
        public int Key;
        public static SpecData Empty => default;
        public bool Equals(ref SpecData other) => Key == other.Key;
        public override int GetHashCode() => Key;
    }
    struct SpecDescription { }
    struct ResourceBindingSegment { }
    sealed class DescriptorSetTemplate : IDisposable { public void Dispose() { } }
    sealed class PipelineLayoutCacheEntry { public PipelineLayout PipelineLayout; }
    sealed class PipelineLayoutCache
    {
        public PipelineLayoutCacheEntry GetOrCreate(VulkanRenderer gd, Device device,
            ReadOnlyCollection<ResourceDescriptorCollection> sets, bool push) => new();
    }
    struct Capabilities { public bool SupportsPushDescriptors; }
    static class VulkanConfiguration { public static bool UsePushDescriptors; }
    sealed class PipelineCacheManager
    {
        public bool SupportsNonBlockingPipelineCreation;
        public readonly ConcurrentDictionary<int, int> WorkerCompiles = new();
        public PipelineCache GetWorkerCache(int index) => new() { Index = index + 1 };
        public void NotifyWorkerPipelineCreated(int index) => WorkerCompiles.AddOrUpdate(index, 1, (_, count) => count + 1);
    }
    sealed class SyncManager { public int Calls; public void Cleanup() => Calls++; }
    sealed class DescriptorSetUpdater { public void SetProgram(object cbs, ShaderCollection program, bool bound) { } }
    sealed class DisposablePipeline : IDisposable
    {
        static long _next;
        public Pipeline Value = new() { Handle = (ulong)Interlocked.Increment(ref _next) };
        public int Disposed;
        public void Dispose() { if (Interlocked.Increment(ref Disposed) != 1) throw new Exception("Pipeline disposed twice"); }
    }
    struct DisposableRenderPass : IDisposable
    {
        public RenderPass Value;
        public DisposableRenderPass() => Value = new() { Handle = 1 };
        public void Dispose() { }
    }
    sealed class Auto<T> : IDisposable where T : IDisposable
    {
        readonly T _value;
        int _references = 1;
        public Auto(T value) => _value = value;
        public T GetUnsafe() => _value;
        public T Get(object cbs) => _value;
        public bool TryIncrementReferenceCount() { Interlocked.Increment(ref _references); return true; }
        public void DecrementReferenceCount() { if (Interlocked.Decrement(ref _references) == 0) _value.Dispose(); }
        public void Dispose() => DecrementReferenceCount();
        public int References => Volatile.Read(ref _references);
    }
    readonly record struct NativeRequest(ShaderCollection Program, int Key, bool Compute, int CacheIndex);
    partial class PipelineState : IDisposable
    {
        public PipelineUid Internal;
        public SpecData SpecializationData;
        public PipelineShaderStageCreateInfo[] Stages;
        public uint StagesCount, SamplesCount = 1;
        public bool HasTessellationControlShader, RasterizerDiscardEnable;
        public PipelineLayout PipelineLayout;
        int _allocated;
        public static int LiveStates;
        public void Initialize() { Stages = new PipelineShaderStageCreateInfo[6]; _allocated = 1; Interlocked.Increment(ref LiveStates); }
        public void Dispose() { if (Interlocked.Exchange(ref _allocated, 0) != 0) Interlocked.Decrement(ref LiveStates); }
        public PipelineState Clone()
        {
            var next = new PipelineState { Internal = Internal, SpecializationData = SpecializationData,
                StagesCount = StagesCount, PipelineLayout = PipelineLayout };
            next.Initialize();
            Stages.CopyTo(next.Stages, 0);
            return next;
        }
        public Auto<DisposablePipeline> CreateComputePipeline(VulkanRenderer gd, Device device, ShaderCollection program,
            PipelineCache cache, bool allowSynchronousCompile = true, bool throwOnError = true, bool cachePipelineFailure = true)
        {
            if (program.TryGetComputePipeline(ref SpecializationData, out var existing)) return existing;
            if (!allowSynchronousCompile) return null;
            Result result = gd.Compile(new(program, SpecializationData.Key, true, cache.Index));
            var pipeline = InterpretCompute(result, program, throwOnError, cachePipelineFailure);
            return pipeline == null ? null : program.AddComputePipeline(ref SpecializationData, pipeline);
        }
        public Auto<DisposablePipeline> CreateGraphicsPipeline(VulkanRenderer gd, Device device, ShaderCollection program,
            PipelineCache cache, RenderPass pass, bool throwOnError = false, bool allowSynchronousCompile = true,
            bool cachePipelineFailure = true, bool failOnCompileRequired = false)
        {
            if (program.TryGetGraphicsPipeline(ref Internal, out var existing)) return existing;
            if (!allowSynchronousCompile) return null;
            Result result = gd.Compile(new(program, Internal.Key, false, cache.Index));
            var pipeline = InterpretGraphics(result, program, throwOnError, cachePipelineFailure);
            return pipeline == null ? null : program.AddGraphicsPipeline(ref Internal, pipeline);
        }
    }
    partial class Shader
    {
        // The compiler itself is a boundary: execute the production null-binary
        // branch too, using a deterministic synthetic SPIR-V payload.
        static byte[] GlslToSpirv(string code, ShaderStage stage) => BitConverter.GetBytes(int.Parse(code));
    }
    partial class ShaderCollection
    {
        public Task Completion => _compileTask;
        public Task Pending => Volatile.Read(ref _initialPipelineCompileTask);
        public int TestKey => _state.Key;
        public bool ModulesDisposed => _shaders.All(s => ! _gd.Api.Modules.ContainsKey(s.GetInfo().Module.Handle));
        static bool HasPushDescriptorsBug(VulkanRenderer gd) => false;
        static bool CanUsePushDescriptors(VulkanRenderer gd, ResourceLayout layout, bool isCompute) => false;
        static ReadOnlyCollection<ResourceDescriptorCollection> BuildPushDescriptorSets(VulkanRenderer gd,
            ReadOnlyCollection<ResourceDescriptorCollection> sets) => sets;
        static ResourceBindingSegment[][] BuildClearSegments(ReadOnlyCollection<ResourceDescriptorCollection> sets) => [];
        static ResourceBindingSegment[][] BuildBindingSegments(ReadOnlyCollection<ResourceUsageCollection> usages,
            out bool bufferTextures) { bufferTextures = false; return []; }
        DescriptorSetTemplate[] BuildTemplates(bool usePushDescriptors) => [];
        static (PipelineStageFlags, PipelineStageFlags) BuildIncoherentStages(ReadOnlyCollection<ResourceUsageCollection> usages) => default;
        protected DisposableRenderPass CreateDummyRenderPass()
        {
            if (_dummyRenderPass.Value.Handle == 0) _dummyRenderPass = new();
            return _dummyRenderPass;
        }
    }
    partial class VulkanRenderer : IDisposable
    {
        public uint ProgramCount;
        public Vk Api = new();
        public PipelineBase Pipeline;
        public PipelineLayoutCache PipelineLayoutCache = new();
        public PipelineCacheManager PipelineCacheManager = new();
        public SyncManager SyncManager = new();
        public BackgroundCompilationScheduler BackgroundCompilationScheduler;
        public HashSet<ShaderCollection> Shaders = new();
        public Capabilities Capabilities;
        public bool IsQualcommProprietary;
        public Func<NativeRequest, Result> CompileAction = _ => Result.Success;
        public readonly ConcurrentQueue<NativeRequest> Requests = new();
        public int NativeCompiles, ActiveCompiles, PeakCompiles;
        public volatile bool Released;
        private Device _device;
        private bool _initialized = true;
#if CACHED_STARTUP_ADAPTED
        private ExceptionDispatchInfo _backgroundPipelineFailure;
#endif
        public VulkanRenderer()
        {
            BackgroundCompilationScheduler = new(PipelineCacheManager);
            Pipeline = new(this);
        }
        public Result Compile(NativeRequest request)
        {
            if (Released) throw new Exception("Used released native device");
            Requests.Enqueue(request);
            Interlocked.Increment(ref NativeCompiles);
            int active = Interlocked.Increment(ref ActiveCompiles);
            int peak;
            do { peak = PeakCompiles; } while (active > peak && Interlocked.CompareExchange(ref PeakCompiles, active, peak) != peak);
            try { return CompileAction(request); }
            finally { Interlocked.Decrement(ref ActiveCompiles); }
        }
        public void Dispose()
        {
            if (Released) return;
            JoinBeforeNativeRelease();
            foreach (var shader in Shaders.ToArray()) shader.Dispose();
            Pipeline.Dispose();
            Released = true;
        }
    }
    partial class PipelineBase : IDisposable
    {
        public VulkanRenderer Gd;
        public Device Device;
        public PipelineCache PipelineCache;
        public object CommandBuffer = new(), Cbs = new();
        public Auto<DisposablePipeline> Pipeline;
        ShaderCollection _program;
        PipelineState _newState = new();
        Auto<DisposableRenderPass> _renderPass;
        readonly DescriptorSetUpdater _descriptorSetUpdater = new();
        bool _programStagesReady, _bindingBarriersDirty, _tfEnabled, _renderPassHadSkippedDraw;
        ulong _currentPipelineHandle;
        public PipelineBase(VulkanRenderer gd) { Gd = gd; _newState.Initialize(); }
        void CreateRenderPass() => _renderPass ??= new(new());
        void PauseTransformFeedbackInternal() { }
        void SignalStateChange() { }
        void EndRenderPass() { }
        public bool Submit(bool compute = false, bool allowSkip = true, int stateKey = 0)
        {
            _newState.Internal = new PipelineUid { Key = stateKey };
            _newState.SpecializationData = new SpecData { Key = stateKey };
            return CreatePipeline(compute ? PipelineBindPoint.Compute : PipelineBindPoint.Graphics, allowSkip);
        }
        public bool CanSkip(bool allowSkip = true) => CanSkipForBackgroundCompile(allowSkip);
        public bool Skipped => _renderPassHadSkippedDraw;
        public void Dispose() { _newState.Dispose(); _renderPass?.Dispose(); }
    }
}
