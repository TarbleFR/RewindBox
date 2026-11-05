using System;
using System.Collections.Concurrent;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;

// Only the native backend is a double. The GAL (ThreadedRenderer, its command queue and dispatch, ThreadedProgram,
// ProgramQueue, ProgramCheckLinkCommand, SetProgramCommand, ThreadedPipeline) is the production assembly built from the
// prepared tree, and the save poll is the real ShaderCache.ProcessShaderCacheQueue compiled into SaveQueue.cs.
sealed class Backend : IRenderer
{
    public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured;
    public Thread RenderThread;
    public readonly ConcurrentQueue<CompileDouble> Planned = new();
    public readonly PipelineDouble NativePipeline = new();
    public Action OnPreFrame;
    public int Frames, Disposals;

    public bool PreferThreading => true;
    public IPipeline Pipeline => NativePipeline;
    public IWindow Window { get; } = new NativeWindow();
    public uint ProgramCount => 0;
    public void BackgroundContextAction(Action action, bool alwaysBackground = false) => action();
    public static BufferHandle Handle(ulong value) => Unsafe.As<ulong, BufferHandle>(ref value);
    public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default) => Handle(1);
    public BufferHandle CreateBuffer(nint pointer, int size) => Handle(1);
    public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storageBuffers) => Handle(1);
    public IImageArray CreateImageArray(int size, bool isBuffer) => throw new NotSupportedException();

    // Programs are created in the order the GPU thread asked for them (ProgramQueue keeps that order).
    public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info)
    {
        if (!Planned.TryDequeue(out CompileDouble program))
        {
            throw new InvalidOperationException("no planned program");
        }

        program.CreatedOnRenderThread = Thread.CurrentThread == RenderThread;
        return program;
    }

    public ISampler CreateSampler(SamplerCreateInfo info) => throw new NotSupportedException();
    public ITexture CreateTexture(TextureCreateInfo info) => throw new NotSupportedException();
    public ITextureArray CreateTextureArray(int size, bool isBuffer) => throw new NotSupportedException();
    public bool PrepareHostMapping(nint address, ulong size) => true;
    public void CreateSync(ulong id, bool strict) { }
    public void DeleteBuffer(BufferHandle buffer) { }
    public PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size) => default;
    public Capabilities GetCapabilities() => default;
    public ulong GetCurrentSync() => 0;
    public HardwareInfo GetHardwareInfo() => default;
    public IProgram LoadProgramBinary(byte[] programBinary, bool hasFragmentShader, ShaderInfo info) => CreateProgram([], info);
    public void SetBufferData(BufferHandle buffer, int offset, ReadOnlySpan<byte> data) { }
    public void UpdateCounters() { }
    public void PreFrame() { Frames++; OnPreFrame?.Invoke(); }
    public ICounterEvent ReportCounter(CounterType type, EventHandler<ulong> resultHandler, float divisor, bool hostReserved) =>
        throw new NotSupportedException();
    public void ResetCounter(CounterType type) { }
    public void WaitSync(ulong id) { }
    public void Initialize(GraphicsDebugLevel logLevel) { }
    public void SetInterruptAction(Action<Action> interruptAction) { }
    public void Screenshot() { }
    public void Dispose() => Disposals++;
}

// A backend program whose shader and warm-up pipeline compile ends when the scenario says so (Complete). A blocking link
// check waits for that, as Vulkan's ShaderCollection.CheckProgramLink(true) waits for its compile task.
sealed class CompileDouble(string name, Backend backend, bool canBindWhileIncomplete = false) : IProgram
{
    public readonly string Name = name;
    private readonly ManualResetEventSlim _linked = new(false);
    private int _status = (int)ProgramLinkStatus.Incomplete;
    public readonly ManualResetEventSlim BlockEntered = new(false);
    public volatile bool RenderBlocked;
    public bool CreatedOnRenderThread;
    public int BlockingChecks, NonBlockingChecks, OffRenderThreadChecks, BinaryReads;
    public long LinkedAt;

    public bool CanBindWhileIncomplete => canBindWhileIncomplete;

    public void Complete(ProgramLinkStatus status)
    {
        LinkedAt = Stopwatch.GetTimestamp();
        Volatile.Write(ref _status, (int)status);
        _linked.Set();
    }

    public ProgramLinkStatus CheckProgramLink(bool blocking)
    {
        if (Thread.CurrentThread != backend.RenderThread)
        {
            Interlocked.Increment(ref OffRenderThreadChecks);
        }

        if (blocking)
        {
            Interlocked.Increment(ref BlockingChecks);
            RenderBlocked = true;
            BlockEntered.Set();
            _linked.Wait();
            RenderBlocked = false;
        }
        else
        {
            Interlocked.Increment(ref NonBlockingChecks);
        }

        return (ProgramLinkStatus)Volatile.Read(ref _status);
    }

    public byte[] GetBinary()
    {
        Interlocked.Increment(ref BinaryReads);
        return [9, 9];
    }

    public void Dispose() { }
}

sealed class NativeWindow : IWindow
{
    public void Present(ITexture texture, ImageCrop crop, Action swapBuffersCallback) => swapBuffersCallback();
    public void SetSize(int width, int height) { }
    public void ChangeVSyncMode(VSyncMode vSyncMode) { }
    public void SetAntiAliasing(AntiAliasing antialiasing) { }
    public void SetScalingFilter(ScalingFilter type) { }
    public void SetScalingFilterLevel(float level) { }
    public void SetMetalFxUpscaleFactor(float factor) { }
    public void SetColorSpacePassthrough(bool colorSpacePassThroughEnabled) { }
}

// The backend pipeline: every IPipeline member of the prepared tree, generated by the test driver as no-ops, except
// SetProgram, which records the bound program.
sealed partial class PipelineDouble : IPipeline
{
    public int Bound;
    public IProgram LastProgram;

    private void OnSetProgram(IProgram program)
    {
        Bound++;
        LastProgram = program;
    }
}
