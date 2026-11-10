using System;
using System.Runtime.CompilerServices;
using Ryujinx.Common.Memory;
using Ryujinx.Common.Configuration;
using Ryujinx.Graphics.GAL;

// Only the native backend and logger are doubles. The complete GAL, including
// its dispatch table, commands, resource wrappers and waiting paths, is real.
sealed class Backend : IRenderer
{
    public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured;
    public bool PreferThreading => true;
    public IPipeline Pipeline => null; // No pipeline commands in these scenarios.
    public IWindow Window { get; } = new NativeWindow();
    public uint ProgramCount => 0;
    public Action<Action> Interrupt;
    public Action OnPreFrame, OnCreateProgram, OnDispose, OnReportCounter;
    public Func<bool, ProgramLinkStatus> OnCheck;
    public int Counters, Buffers, Syncs, Waits, Reads, Disposals, Frames;
    public void BackgroundContextAction(Action action, bool alwaysBackground = false) => action();
    public static BufferHandle Handle(ulong value) => Unsafe.As<ulong, BufferHandle>(ref value);
    public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default)
    { Buffers++; return Handle((ulong)(100 + Buffers)); }
    public BufferHandle CreateBuffer(nint pointer, int size) => CreateBuffer(size);
    public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> ranges) => CreateBuffer(ranges.Length);
    public IImageArray CreateImageArray(int size, bool isBuffer) => throw new NotSupportedException();
    public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info)
    { OnCreateProgram?.Invoke(); return new NativeProgram(this); }
    public ISampler CreateSampler(SamplerCreateInfo info) => throw new NotSupportedException();
    public ITexture CreateTexture(TextureCreateInfo info) => new NativeTexture();
    public ITextureArray CreateTextureArray(int size, bool isBuffer) => throw new NotSupportedException();
    public bool PrepareHostMapping(nint address, ulong size) => true;
    public void CreateSync(ulong id, bool strict) => Syncs++;
    public void DeleteBuffer(BufferHandle buffer) { }
    public PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size)
    { Reads++; return default; }
    public Capabilities GetCapabilities() => default;
    public ulong GetCurrentSync() => 0;
    public HardwareInfo GetHardwareInfo() => default;
    public IProgram LoadProgramBinary(byte[] binary, bool fragment, ShaderInfo info) => CreateProgram([], info);
    public void SetBufferData(BufferHandle buffer, int offset, ReadOnlySpan<byte> data) { }
    public void UpdateCounters() => Counters++;
    public void PreFrame() { Frames++; OnPreFrame?.Invoke(); }
    public ICounterEvent ReportCounter(CounterType type, EventHandler<ulong> handler, float divisor, bool hostReserved)
    { OnReportCounter?.Invoke(); return new NativeCounter(); }
    public void ResetCounter(CounterType type) { }
    public void WaitSync(ulong id) => Waits++;
    public void Initialize(GraphicsDebugLevel level) { }
    public void SetInterruptAction(Action<Action> action) => Interrupt = action;
    public void Screenshot() { }
    public void Dispose() { OnDispose?.Invoke(); Disposals++; }
}

sealed class NativeProgram(Backend backend) : IProgram
{
    public bool CanBindWhileIncomplete => false;
    public ProgramLinkStatus CheckProgramLink(bool blocking) => backend.OnCheck?.Invoke(blocking) ?? ProgramLinkStatus.Success;
    public byte[] GetBinary() => [1, 2, 3];
    public void Dispose() { }
}

sealed class NativeTexture : ITexture
{
    public int Calls;
    public int Width => 1;
    public int Height => 1;
    public void CopyTo(ITexture destination, int firstLayer, int firstLevel) => Calls++;
    public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel) => Calls++;
    public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) => Calls++;
    public void CopyTo(BufferRange range, int layer, int level, int stride) => Calls++;
    public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) => new NativeTexture();
    public PinnedSpan<byte> GetData() { Calls++; return default; }
    public PinnedSpan<byte> GetData(int layer, int level) { Calls++; return default; }
    public void SetData(MemoryOwner<byte> data) { Calls++; data.Dispose(); }
    public void SetData(MemoryOwner<byte> data, int layer, int level) => SetData(data);
    public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region) => SetData(data);
    public void SetStorage(BufferRange buffer) => Calls++;
    public void Release() => Calls++;
}

sealed class NativeCounter : ICounterEvent
{
    public int Calls;
    public bool Invalid { get; set; }
    public bool ReserveForHostAccess() { Calls++; return true; }
    public void Flush() => Calls++;
    public void Dispose() => Calls++;
}

sealed class NativeWindow : IWindow
{
    public int Presents;
    public void Present(ITexture texture, ImageCrop crop, Action callback) { Presents++; callback(); }
    public void SetSize(int width, int height) { }
    public void ChangeVSyncMode(VSyncMode mode) { }
    public void SetAntiAliasing(AntiAliasing antialiasing) { }
    public void SetScalingFilter(ScalingFilter type) { }
    public void SetScalingFilterLevel(float level) { }
    public void SetMetalFxUpscaleFactor(float factor) { }
    public void SetColorSpacePassthrough(bool enabled) { }
}

namespace Ryujinx.Common.Logging
{
    public enum LogClass { Gpu }
    public static class Logger { public static Sink Info => null; }
    public sealed class Sink { public void PrintMsg(LogClass kind, string message) { } }
}
