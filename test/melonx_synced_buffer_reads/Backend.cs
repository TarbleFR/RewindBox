using System;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Threading;
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;

// Only the native backend is a double. The GAL (ThreadedRenderer, its queue, InvokeCommand, BufferMap, SyncMap,
// GetBufferData and GetBufferDataAfterSync) is the production assembly built from the prepared tree. A queued write to
// the "busy" buffer keeps the render thread busy for BusyMs (work queued ahead); every buffer keeps its bytes, so a read
// returns what the writes run so far left; reads record their thread and whether the buffer had been created.
sealed class Backend : IRenderer
{
    public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured;
    public Thread RenderThread;
    public readonly PipelineDouble NativePipeline = new();
    public volatile int BusyMs, ReadBackMs;
    public int ReadBacks, ReadBacksOffRenderThread, ReadsOfMissingBuffers;
    public volatile bool FailNextWrite;
    private ulong _nextHandle = 100;
    private readonly System.Collections.Concurrent.ConcurrentDictionary<ulong, byte[]> _buffers = new();
    public readonly System.Collections.Concurrent.ConcurrentDictionary<ulong, long> Created = new();
    public readonly System.Collections.Concurrent.ConcurrentQueue<ulong> Syncs = new();

    public static void Spin(int ms)
    {
        long end = Stopwatch.GetTimestamp() + ms * Stopwatch.Frequency / 1000;
        while (Stopwatch.GetTimestamp() < end)
        {
            Thread.SpinWait(64);
        }
    }

    public bool PreferThreading => true;
    public IPipeline Pipeline => NativePipeline;
    public IWindow Window { get; } = new NativeWindow();
    public uint ProgramCount => 0;
    public void BackgroundContextAction(Action action, bool alwaysBackground = false) => action();
    public static BufferHandle Handle(ulong value) => Unsafe.As<ulong, BufferHandle>(ref value);
    public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default)
    {
        ulong handle = Interlocked.Increment(ref _nextHandle);
        _buffers[handle] = GC.AllocateArray<byte>(Math.Max(size, 16), pinned: true);
        Created[handle] = Stopwatch.GetTimestamp();
        if (BusyBuffer == 0) BusyBuffer = handle; // the first buffer created is the busy one
        return Handle(handle);
    }
    private static ulong Id(BufferHandle handle) => Unsafe.As<BufferHandle, ulong>(ref handle);
    public BufferHandle CreateBuffer(nint pointer, int size) => Handle(1);
    public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storageBuffers) => Handle(1);
    public IImageArray CreateImageArray(int size, bool isBuffer) => throw new NotSupportedException();
    public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info) => throw new NotSupportedException();
    public ISampler CreateSampler(SamplerCreateInfo info) => throw new NotSupportedException();
    public ITexture CreateTexture(TextureCreateInfo info) => throw new NotSupportedException();
    public ITextureArray CreateTextureArray(int size, bool isBuffer) => throw new NotSupportedException();
    public bool PrepareHostMapping(nint address, ulong size) => true;
    public void CreateSync(ulong id, bool strict) => Syncs.Enqueue(id);
    public void DeleteBuffer(BufferHandle buffer) { }

    public unsafe PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size)
    {
        Interlocked.Increment(ref ReadBacks);
        if (Thread.CurrentThread != RenderThread)
        {
            Interlocked.Increment(ref ReadBacksOffRenderThread);
        }

        Spin(ReadBackMs);
        if (!_buffers.TryGetValue(Id(buffer), out byte[] data))
        {
            Interlocked.Increment(ref ReadsOfMissingBuffers);
            return default;
        }

        return PinnedSpan<byte>.UnsafeFromSpan(new ReadOnlySpan<byte>(data, offset, size));
    }

    public Capabilities GetCapabilities() => default;
    public ulong GetCurrentSync() => 0;
    public HardwareInfo GetHardwareInfo() => default;
    public IProgram LoadProgramBinary(byte[] programBinary, bool hasFragmentShader, ShaderInfo info) => throw new NotSupportedException();
    // The "busy" buffer is work queued ahead; any other write stores its bytes.
    public ulong BusyBuffer;
    public void SetBufferData(BufferHandle buffer, int offset, ReadOnlySpan<byte> data)
    {
        if (FailNextWrite)
        {
            FailNextWrite = false;
            throw new InvalidOperationException("backend failure (fixture)");
        }

        ulong id = Id(buffer);
        if (id == BusyBuffer)
        {
            Spin(BusyMs);
            return;
        }

        data.CopyTo(_buffers[id].AsSpan(offset));
    }
    public void UpdateCounters() { }
    public void PreFrame() { }
    public ICounterEvent ReportCounter(CounterType type, EventHandler<ulong> resultHandler, float divisor, bool hostReserved) =>
        throw new NotSupportedException();
    public void ResetCounter(CounterType type) { }
    public void WaitSync(ulong id) { }
    public void Initialize(GraphicsDebugLevel logLevel) { }
    public void SetInterruptAction(Action<Action> interruptAction) { }
    public void Screenshot() { }
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

// The backend pipeline: every IPipeline member of the prepared tree, generated by the test driver as no-ops.
sealed partial class PipelineDouble : IPipeline
{
    private void OnSetProgram(IProgram program) { }
}
