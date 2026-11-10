#if START_FAULT
global using Thread = StartFaultThread;
#endif
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Threading;
using OsThread = System.Threading.Thread;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Gpu.Shader.DiskCache;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Shader.Translation;

// The complete production loader owns every queue, worker, translation dispatch,
// validation decision, cache-insertion decision, recovery and join. Storage,
// shader IR/compiler and GPU resources are controlled boundaries. The default
// executable uses System.Threading.Thread directly, without instrumentation.
sealed class BoundaryState
{
    public readonly CountdownEvent FirstWorkersEntered = new(8);
    public readonly ManualResetEventSlim TranslateAllowed = new(false);
    public readonly ManualResetEventSlim HostFinished = new(false);
    public readonly ManualResetEventSlim Returned = new(false);
    public readonly ConcurrentDictionary<int, OsThread> Workers = new();
    public readonly ConcurrentQueue<ShaderCacheState> States = new();
    public readonly ConcurrentQueue<int> PackagedIndices = new();
    public int Entered, Completed, Active, LateUse, ResourceReleased;
    public int ProgramsCreated, ProgramChecks, BinaryReads, ProgramDisposals;
    public int FailTranslationIndex = -1;
    public Exception CreateError, CheckError, ReturnedError;
    public int WorkersAliveAtReturn, ActiveAtReturn, CompletedAtReturn;

    public void Touch()
    {
        if (Volatile.Read(ref ResourceReleased) != 0)
            Interlocked.Increment(ref LateUse);
    }

    public ShaderProgram Translate(byte[] code)
    {
        Workers.TryAdd(OsThread.CurrentThread.ManagedThreadId, OsThread.CurrentThread);
        Interlocked.Increment(ref Active);
        int entered = Interlocked.Increment(ref Entered);
        if (entered <= 8) FirstWorkersEntered.Signal();
        try
        {
            if (!TranslateAllowed.Wait(10000)) throw new TimeoutException("translation gate");
            Touch();
            if (code[0] == FailTranslationIndex)
                throw new InvalidOperationException("controlled shader translation failure");
            return new ShaderProgram { Info = new ShaderProgramInfo { Index = code[0] } };
        }
        finally
        {
            Interlocked.Increment(ref Completed);
            Interlocked.Decrement(ref Active);
        }
    }
}

sealed class NativeProgram(BoundaryState state) : IProgram
{
    public bool CanBindWhileIncomplete => false;
    public ProgramLinkStatus CheckProgramLink(bool blocking)
    {
        state.Touch();
        Interlocked.Increment(ref state.ProgramChecks);
        if (state.CheckError != null) throw state.CheckError;
        return ProgramLinkStatus.Success;
    }
    public byte[] GetBinary() { state.BinaryReads++; return [1, 2, 3]; }
    public void Dispose() => state.ProgramDisposals++;
}

sealed class NativeFailure(string message) : Exception(message);

#if START_FAULT
// A separate executable injects only Thread.Start failure. Each successful
// Start/Join still delegates to a real OS thread; it does not run the normal
// work/failure cases. No production source text is changed for this injection.
sealed class StartFaultThread
{
    public static readonly List<StartFaultThread> Created = new();
    public static int Attempts, FailAt, InvalidJoins;
    public static readonly Exception Failure = new OutOfMemoryException("controlled Thread.Start failure");
    public readonly OsThread Native;
    public bool Started, Joined;
    public StartFaultThread(ParameterizedThreadStart action)
    {
        Native = new OsThread(action);
        Created.Add(this);
    }
    public string Name { set => Native.Name = value; }
    public void Start(object argument)
    {
        if (++Attempts == FailAt) throw Failure;
        Native.Start(argument);
        Started = true;
    }
    public void Join()
    {
        if (!Started) InvalidJoins++;
        Native.Join();
        Joined = true;
    }
}
#endif

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }
    public static class Logger
    {
        public static readonly Sink Info = new(), Warning = new(), Error = new();
    }
    public sealed class Sink
    {
        public int Count;
        public void Print(LogClass kind, string message) => Interlocked.Increment(ref Count);
    }
}

namespace Ryujinx.Graphics.GAL
{
    public struct ShaderInfo { public bool FromCache; }
    public sealed class ShaderSource { }
}

namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuContext(BoundaryState state)
    {
        public BoundaryState State { get; } = state;
        public TestRenderer Renderer { get; } = new(state);
        public TestCapabilities Capabilities { get; } = new();
    }
    sealed class TestCapabilities
    {
        public TargetApi Api = TargetApi.Vulkan;
        public bool SupportsLayerVertexTessellation = true;
    }
    sealed class TestRenderer(BoundaryState state)
    {
        public IProgram CreateProgram(ShaderSource[] sources, ShaderInfo info)
        {
            state.Touch();
            if (!info.FromCache) throw new InvalidOperationException("missing cache flag");
            state.ProgramsCreated++;
            if (state.CreateError != null) throw state.CreateError;
            return new NativeProgram(state);
        }
    }
    static class Constants { public const int ShaderStages = 5; }
}

namespace Ryujinx.Graphics.Shader
{
    sealed class ShaderProgramInfo { public int Index; }
    sealed class ShaderProgram { public ShaderProgramInfo Info; }
}

namespace Ryujinx.Graphics.Shader.Translation
{
    sealed class ResourceCounts { }
    sealed class TranslatorContext(DiskCacheGpuAccessor accessor)
    {
        public bool HasStore => false;
        public bool LayerOutputWritten => false;
        public void SetNextStage(TranslatorContext next) { }
        public ShaderProgram Translate(TranslatorContext other = null) => accessor.Context.State.Translate(accessor.Code);
        public ShaderProgram GenerateGeometryPassthrough() => throw new NotSupportedException();
    }
}

namespace Ryujinx.Graphics.Gpu.Shader
{
    sealed class ShaderSpecializationState
    {
        public int GraphicsState, ComputeState, PipelineState;
        public object TransformFeedbackDescriptors;
        public ShaderSpecializationState() { }
        public ShaderSpecializationState(ref int state) { ComputeState = state; }
        public ShaderSpecializationState(ref int state, int pipeline, object descriptors)
        { GraphicsState = state; PipelineState = pipeline; TransformFeedbackDescriptors = descriptors; }
        public void Prepare(CachedShaderStage[] shaders) { }
    }
    sealed class ShaderAsCompute { public IProgram HostProgram; }
    sealed class CachedShaderBindings { public CachedShaderBindings(bool compute, CachedShaderStage[] shaders) { } }
    sealed class ShaderCacheHashTable
    {
        public readonly List<CachedShaderProgram> Programs = new();
        public void Add(CachedShaderProgram program) => Programs.Add(program);
    }
    sealed class ComputeShaderCacheHashTable
    {
        public readonly List<CachedShaderProgram> Programs = new();
        public void Add(CachedShaderProgram program) => Programs.Add(program);
    }
    sealed class ShaderInfoBuilder(GpuContext context, bool transformFeedback)
    {
        public void AddStageInfo(ShaderProgramInfo info) { }
        public ShaderInfo Build(int pipeline, bool fromCache) => new() { FromCache = fromCache };
    }
    static class ShaderCache
    {
        public const TranslationFlags DefaultFlags = 0;
        public static TranslatorContext DecodeGraphicsShader(DiskCacheGpuAccessor accessor, TargetApi api, TranslationFlags flags, ulong address) => new(accessor);
        public static TranslatorContext DecodeComputeShader(DiskCacheGpuAccessor accessor, TargetApi api, ulong address) => new(accessor);
        public static bool ShouldConvertVertexToCompute(GpuContext context, bool vertexStore, bool geometryStore, bool hasGeometry) => false;
        public static ShaderSource CreateShaderSource(ShaderProgram program) => new();
    }
}

namespace Ryujinx.Graphics.Gpu.Shader.DiskCache
{
    sealed class DiskCacheGpuAccessor(GpuContext context, byte[] code, byte[] cb1,
        ShaderSpecializationState oldState, ShaderSpecializationState newState,
        ResourceCounts counts, int stage, bool geometry)
    {
        public GpuContext Context { get; } = context;
        public byte[] Code { get; } = code;
        public void InitializeReservedCounts(bool tfEnabled, bool vertexAsCompute) { }
    }
    sealed class DiskCacheHostStorage(BoundaryState state)
    {
        public int ProgramCount, SharedClears, HostClears, GuestClears, Additions;
        public Action<GpuContext, ParallelDiskCacheLoader> OnLoad;
        public int GetProgramCount() => ProgramCount;
        public void LoadShaders(GpuContext context, ParallelDiskCacheLoader loader) => OnLoad?.Invoke(context, loader);
        public void ClearSharedCache() => SharedClears++;
        public void ClearHostCache(GpuContext context) => HostClears++;
        public void ClearGuestCache() => GuestClears++;
        public DiskCacheOutputStreams GetOutputStreams(GpuContext context) => new();
        public void AddShader(GpuContext context, CachedShaderProgram program, byte[] binary, DiskCacheOutputStreams streams)
        {
            Additions++;
            state.PackagedIndices.Enqueue(program.Shaders[program.Shaders.Length == 1 ? 0 : 1].Code[0]);
        }
    }
    sealed class DiskCacheOutputStreams : IDisposable { public void Dispose() { } }
    static class ShaderBinarySerializer { public static byte[] Pack(ShaderSource[] sources) => [1, 2, 3]; }
}
