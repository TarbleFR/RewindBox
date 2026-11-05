// Doubles for melonx_setprogram_warmup_test.py. Compiled with the REAL members of each variant (control: Core 658
// preparation, candidate: plus adapt_setprogram_warmup): BackgroundCompilationScheduler, HashTableSlim and SpecData;
// ShaderCollection's constructors (the base one without its descriptor-layout part) and every compile, link, warm-up and
// pipeline-table member; Shader's constructors and waits; VulkanRenderer.CreateProgram and its failure members;
// PipelineBase.SetProgram, CreatePipeline, CanSkipForBackgroundCompile and UpdateProgramStagesIfReady; the GAL
// ProgramQueue, SetProgramCommand, CreateProgramCommand, SourceProgramRequest and TableRef. Only Vulkan itself is a
// double: a shader module or pipeline compile is a timed sleep (Native), the main-cache lock is the renderer's real
// PipelineCreationLock taken as PipelineState takes it.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Threading;
using System.Threading.Tasks;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Silk.NET.Vulkan;

namespace Silk.NET.Vulkan
{
    struct Device { }
    struct PipelineCache { public int Id; } // 0: main cache, 1 + n: worker n's cache (n = worker count: demand thread)
    struct PipelineLayout { }
    struct ShaderModule { public ulong Handle; }
    struct RenderPass { public ulong Handle; }
    struct Pipeline { public ulong Handle; }
    struct CommandBuffer { }
    enum PipelineBindPoint { Graphics, Compute }
    [Flags] enum ShaderStageFlags { None = 0, VertexBit = 1, TessellationControlBit = 2, TessellationEvaluationBit = 4, GeometryBit = 8, FragmentBit = 16, ComputeBit = 32 }
    [Flags] enum PipelineStageFlags { None = 0 }
    enum Result { Success, ErrorInitializationFailed, ErrorDeviceLost, ErrorOutOfHostMemory, ErrorOutOfDeviceMemory, PipelineCompileRequired }
    struct PipelineShaderStageCreateInfo { public ShaderStageFlags Stage; public ShaderModule Module; }
    class Vk
    {
        public readonly List<ulong> Bound = new();
        public void CmdBindPipeline(CommandBuffer commandBuffer, PipelineBindPoint bindPoint, Pipeline pipeline) { lock (Bound) Bound.Add(pipeline.Handle); }
    }
}

namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    class Sink
    {
        public readonly List<string> Lines = new();
        public void Print(LogClass logClass, string message) { lock (Lines) Lines.Add(message); }
        public void PrintMsg(LogClass logClass, string message) => Print(logClass, message);
    }
    static class Logger { public static Sink Warning = new(), Error = new(), Debug = new(), Info = new(); }
}

namespace Ryujinx.Graphics.Shader
{
    enum ShaderStage { Compute, Vertex, TessellationControl, TessellationEvaluation, Geometry, Fragment }
}

namespace Ryujinx.Graphics.GAL
{
    enum ProgramLinkStatus { Incomplete, Success, Failure }
    interface IProgram { bool CanBindWhileIncomplete { get; } ProgramLinkStatus CheckProgramLink(bool blocking); byte[] GetBinary(); }
    interface IPipeline { void SetProgram(IProgram program); }
    interface IRenderer { IPipeline Pipeline { get; } IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info); }
    public class ResourceLayout { }
    class ShaderSource
    {
        public Ryujinx.Graphics.Shader.ShaderStage Stage;
        public bool FailModule;
    }
    // The fields of the warm-up key this fixture varies (the 658 misses: topology and primitive restart).
    public struct ProgramPipelineState { public int Topology; public bool PrimitiveRestartEnable; }
}

namespace Ryujinx.Graphics.GAL.Multithreading
{
    enum CommandType { CreateProgram, SetProgram }
    static class HostThreadQos { public static void RaiseCurrentThread() { } }
    class ThreadedRenderer
    {
        public readonly ProgramQueue Programs;
        private readonly Dictionary<int, object> _refs = new();
        private int _next;
        public ThreadedRenderer(IRenderer renderer) { Programs = new ProgramQueue(renderer); }
        public int AddTableRef(object reference) { _refs[++_next] = reference; return _next; }
        public object RemoveTableRef(int index) { object reference = _refs[index]; _refs.Remove(index); return reference; }
    }
}

namespace Ryujinx.Graphics.GAL.Multithreading.Resources
{
    // As the real ThreadedProgram for what the queue and SetProgramCommand use (Base, Compiled, CanBindWhileIncomplete).
    class ThreadedProgram : IProgram
    {
        public IProgram Base;
        internal bool Compiled;
        public bool CanBindWhileIncomplete => Base?.CanBindWhileIncomplete ?? false;
        public ProgramLinkStatus CheckProgramLink(bool blocking) => throw new NotSupportedException("the GPU thread's path; Base is polled directly");
        public byte[] GetBinary() => null;
        // Core 661 (adapt_shader_save_poll): the composed ProgramQueue publishes the link status it observes for the GPU
        // thread's save poll; nothing on the SetProgram path reads it.
        internal void PublishLinkStatus(ProgramLinkStatus status, bool queuedCheck) { }
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    using Ryujinx.Graphics.Shader;

    // One record per native compile: what, on which cache and thread, when (ms on one clock).
    record Compile(string Key, int Cache, string Thread, double Start, double End, ulong Handle);

    static class Native
    {
        public static readonly Stopwatch Clock = Stopwatch.StartNew();
        public static int PipelineMs = 400, ModuleMs = 1, CheckpointMs;
        public static int Checkpoints;
        public static readonly HashSet<string> FailOnce = new();
        public static readonly List<Compile> Records = new();
        private static long _handles = 100;
        public static double Now => Clock.Elapsed.TotalMilliseconds;

        public static Result Pipeline(string key, PipelineCache cache, out ulong handle)
        {
            double start = Now;
            Thread.Sleep(PipelineMs);
            bool fail;
            lock (FailOnce) fail = FailOnce.Remove(key);
            handle = fail ? 0 : (ulong)Interlocked.Increment(ref _handles);
            lock (Records) Records.Add(new Compile(key, cache.Id, Thread.CurrentThread.Name ?? "pool", start, Now, handle));
            return fail ? Result.ErrorInitializationFailed : Result.Success;
        }

        public static void Module() => Thread.Sleep(ModuleMs);

        public static void Reset() { lock (Records) Records.Clear(); lock (FailOnce) FailOnce.Clear(); }
    }

    static class Constants { public const int MaxShaderStages = 5; }

    static class EnumConversionDouble
    {
        public static ShaderStageFlags Convert(this ShaderStage stage) => stage switch
        {
            ShaderStage.Compute => ShaderStageFlags.ComputeBit,
            ShaderStage.Fragment => ShaderStageFlags.FragmentBit,
            ShaderStage.Geometry => ShaderStageFlags.GeometryBit,
            ShaderStage.TessellationControl => ShaderStageFlags.TessellationControlBit,
            ShaderStage.TessellationEvaluation => ShaderStageFlags.TessellationEvaluationBit,
            _ => ShaderStageFlags.VertexBit,
        };
    }

    class VulkanException : Exception
    {
        public Result ResultCode { get; }
        public VulkanException(Result result) : base("Vulkan " + result) { ResultCode = result; }
    }

    static class ResultExtensions
    {
        public static void ThrowOnError(this Result result) { if (result != Result.Success) throw new VulkanException(result); }
        public static bool IsError(this Result result) => result != Result.Success;
    }

    class Auto<T>
    {
        private readonly T _value;
        public Auto(T value) { _value = value; }
        public T Get(CommandBufferScoped cbs) => _value;
        public T GetUnsafe() => _value;
        public void Dispose() { }
        public bool TryIncrementReferenceCount() => true;
        public void DecrementReferenceCount() { }
    }

    struct DisposablePipeline { public Pipeline Value; public DisposablePipeline(ulong handle) { Value = new Pipeline { Handle = handle }; } }
    struct DisposableRenderPass { public RenderPass Value; public DisposableRenderPass(RenderPass value) { Value = value; } public void Dispose() { } }
    struct CommandBufferScoped { }
    class PipelineLayoutCacheEntry { public PipelineLayout PipelineLayout; }
    struct ResourceBindingSegment { }
    class DescriptorSetTemplate { public void Dispose() { } }
    class SpecDescription { }

    struct PipelineUid : IRefEquatable<PipelineUid>
    {
        public int Topology;
        public bool PrimitiveRestartEnable;
        public override int GetHashCode() => HashCode.Combine(Topology, PrimitiveRestartEnable);
        public bool Equals(ref PipelineUid other) => Topology == other.Topology && PrimitiveRestartEnable == other.PrimitiveRestartEnable;
        public override string ToString() => "graphics topology " + Topology + (PrimitiveRestartEnable ? " restart" : "");
    }

    // The Vulkan pipeline state the real members use; compiles as PipelineState does: table lookup first, the main
    // cache under the renderer's PipelineCreationLock (TryEnter when failOnCompileRequired), a worker cache without it.
    struct PipelineState
    {
        public PipelineUid Internal;
        public SpecData SpecializationData;
        public PipelineShaderStageCreateInfo[] Stages;
        public uint StagesCount;
        public PipelineLayout PipelineLayout;
        public bool HasTessellationControlShader;
        public bool RasterizerDiscardEnable;

        public void Initialize(bool allocateShaderStages = true)
        {
            HasTessellationControlShader = false;
            Stages = allocateShaderStages ? new PipelineShaderStageCreateInfo[Constants.MaxShaderStages] : null;
            SpecializationData = SpecData.Empty;
        }

        public void Dispose() { }

        public PipelineState Clone()
        {
            PipelineState clone = new();
            clone.Initialize();
            clone.Internal = Internal;
            clone.HasTessellationControlShader = HasTessellationControlShader;
            clone.PipelineLayout = PipelineLayout;
            clone.SpecializationData = SpecializationData;
            Stages.AsSpan().CopyTo(clone.Stages.AsSpan());
            return clone;
        }

        internal static string DescribeKeyDifference(ref PipelineUid warmUp, ref PipelineUid draw)
        {
            string text = "";
            if (warmUp.Topology != draw.Topology) text += " Differs from warm-up: Topology warm-up=" + warmUp.Topology + " draw=" + draw.Topology;
            if (warmUp.PrimitiveRestartEnable != draw.PrimitiveRestartEnable)
                text += (text.Length == 0 ? " Differs from warm-up: " : "; ") + "PrimitiveRestartEnable warm-up=" + warmUp.PrimitiveRestartEnable + " draw=" + draw.PrimitiveRestartEnable;
            return text;
        }

        private static Result Build(VulkanRenderer gd, PipelineCache cache, string key, bool failOnCompileRequired, out ulong handle)
        {
            if (!gd.PipelineCacheManager.IsMainCache(cache))
            {
                return Native.Pipeline(key, cache, out handle);
            }

            bool lockTaken = false;
            handle = 0;
            try
            {
                if (failOnCompileRequired) lockTaken = gd.PipelineCreationLock.TryEnter();
                else { gd.PipelineCreationLock.Enter(); lockTaken = true; }
                return lockTaken ? Native.Pipeline(key, cache, out handle) : Result.PipelineCompileRequired;
            }
            finally
            {
                if (lockTaken) gd.PipelineCreationLock.Exit();
            }
        }

        public Auto<DisposablePipeline> CreateGraphicsPipeline(VulkanRenderer gd, Device device, ShaderCollection program, PipelineCache cache,
            RenderPass renderPass, bool throwOnError = false, bool allowSynchronousCompile = true, bool cachePipelineFailure = true, bool failOnCompileRequired = false)
        {
            if (program.TryGetGraphicsPipeline(ref Internal, out Auto<DisposablePipeline> pipeline)) return pipeline;
            if (!allowSynchronousCompile) return null;
            Result result = Build(gd, cache, Internal.ToString(), failOnCompileRequired, out ulong handle);
            if (result is Result.ErrorDeviceLost or Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory) result.ThrowOnError();
            if (result == Result.PipelineCompileRequired) return null;
            if (throwOnError) result.ThrowOnError();
            else if (result.IsError())
            {
                if (cachePipelineFailure) program.AddGraphicsPipeline(ref Internal, null);
                return null;
            }
            return program.AddGraphicsPipeline(ref Internal, new Auto<DisposablePipeline>(new DisposablePipeline(handle)));
        }

        public Auto<DisposablePipeline> CreateComputePipeline(VulkanRenderer gd, Device device, ShaderCollection program, PipelineCache cache,
            bool allowSynchronousCompile = true, bool throwOnError = true, bool cachePipelineFailure = true)
        {
            if (program.TryGetComputePipeline(ref SpecializationData, out Auto<DisposablePipeline> pipeline)) return pipeline;
            if (!allowSynchronousCompile) return null;
            Result result = Build(gd, cache, "compute spec " + SpecializationData.Length, false, out ulong handle);
            if (result is Result.ErrorDeviceLost or Result.ErrorOutOfHostMemory or Result.ErrorOutOfDeviceMemory) result.ThrowOnError();
            if (throwOnError) result.ThrowOnError();
            else if (result.IsError())
            {
                if (cachePipelineFailure) program.AddComputePipeline(ref SpecializationData, null);
                return null;
            }
            return program.AddComputePipeline(ref SpecializationData, new Auto<DisposablePipeline>(new DisposablePipeline(handle)));
        }
    }

    // PipelineConverter's two conversions of a program's pipeline state, for the fields above.
    static class PipelineConverterDouble
    {
        public static PipelineState ToVulkanPipelineState(this ProgramPipelineState state, VulkanRenderer gd, bool allocateShaderStages = true)
        {
            PipelineState pipeline = new();
            pipeline.Initialize(allocateShaderStages);
            pipeline.Internal = new PipelineUid { Topology = state.Topology, PrimitiveRestartEnable = state.PrimitiveRestartEnable };
            return pipeline;
        }

        public static DisposableRenderPass ToRenderPass(this ProgramPipelineState state, VulkanRenderer gd, Device device) => new(new RenderPass { Handle = 1 });
    }

    class PipelineCacheManager
    {
        public PipelineCache MainCache => new() { Id = 0 };
        public bool SupportsNonBlockingPipelineCreation => true;
        public PipelineCache GetWorkerCache(int workerIndex) => new() { Id = 1 + workerIndex };
        public bool IsMainCache(PipelineCache cache) => cache.Id == 0;
        // Models PipelineCacheManager.Maintain: a periodic checkpoint (vkGetPipelineCacheData, mapped write, flush) on the
        // compile thread, here a timed sleep on every notify while Native.CheckpointMs is set (the real one runs every
        // SaveInterval = 64 pipelines per worker cache, and a Recycle under PipelineCreationLock above 128 MiB).
        public void NotifyWorkerPipelineCreated(int workerIndex)
        {
            if (Native.CheckpointMs > 0)
            {
                Interlocked.Increment(ref Native.Checkpoints);
                Thread.Sleep(Native.CheckpointMs);
            }
        }
    }

    partial class VulkanRenderer : IRenderer
    {
        public readonly PipelineCacheManager PipelineCacheManager = new();
        public readonly BackgroundCompilationScheduler BackgroundCompilationScheduler;
        public readonly Vk Api = new();
        internal HashSet<ShaderCollection> Shaders { get; } = new();
        internal Lock PipelineCreationLock { get; } = new();
        private Device _device;
        public uint ProgramCount { get; set; }
        private readonly PipelineBase _pipeline;
        public IPipeline Pipeline => _pipeline;
        public PipelineBase Full => _pipeline;

        public VulkanRenderer()
        {
            BackgroundCompilationScheduler = new(PipelineCacheManager);
            _pipeline = new PipelineBase(this);
        }
    }

    class DescriptorSetUpdaterDouble { public void SetProgram(CommandBufferScoped cbs, ShaderCollection program, bool isBound) { } }

    partial class PipelineBase : IPipeline
    {
        public readonly VulkanRenderer Gd;
        public readonly Device Device;
        public PipelineCache PipelineCache => Gd.PipelineCacheManager.MainCache;
        private ShaderCollection _program;
        private PipelineState _newState;
        private bool _programStagesReady;
        private ulong _currentPipelineHandle;
        private bool _bindingBarriersDirty;
        private bool _renderPassHadSkippedDraw;
        private bool _tfEnabled;
        private Auto<DisposableRenderPass> _renderPass;
        public Auto<DisposablePipeline> Pipeline;
        private readonly DescriptorSetUpdaterDouble _descriptorSetUpdater = new();
        public CommandBufferScoped Cbs => default;
        public CommandBuffer CommandBuffer => default;

        public PipelineBase(VulkanRenderer gd)
        {
            Gd = gd;
            _newState.Initialize();
        }

        private void SignalStateChange() { }
        private void EndRenderPass() { }
        private void CreateRenderPass() { _renderPass = new Auto<DisposableRenderPass>(new DisposableRenderPass(new RenderPass { Handle = 7 })); }
        private void PauseTransformFeedbackInternal() { }

        // PrepareGraphicsDraw with async compile skip off (canSkipForBackgroundCompile false, requiresCompletePipeline
        // false), and the dispatch's RecreateComputePipelineIfNeeded(allowAsyncSkip: true); the test binds both calls.
        public bool Draw(int topology, bool restart)
        {
            _newState.Internal = new PipelineUid { Topology = topology, PrimitiveRestartEnable = restart };
            return CreatePipeline(PipelineBindPoint.Graphics, allowAsyncSkip: true, waitForBackgroundGraphicsPipeline: false);
        }

        public bool Dispatch() => CreatePipeline(PipelineBindPoint.Compute, allowAsyncSkip: true);
        public ulong BoundHandle => _currentPipelineHandle;
        public bool SkippedDraw => _renderPassHadSkippedDraw;
    }

    partial class Shader
    {
        private void Compile(ShaderSource shaderSource)
        {
            Native.Module();
            CompileStatus = shaderSource.FailModule ? ProgramLinkStatus.Failure : ProgramLinkStatus.Success;
            if (!shaderSource.FailModule) _module = new ShaderModule { Handle = 1 };
        }

        public PipelineShaderStageCreateInfo GetInfo() => new() { Stage = _stage, Module = _module };
    }
}
