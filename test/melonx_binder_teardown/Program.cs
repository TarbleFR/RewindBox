// Fixture of melonx_binder_teardown_test.py. The real HOSBinderDriverServer.cs (control or candidate) is compiled beside
// this file; the real SurfaceFlinger members (Layer, CreateLayerFromId, DestroyManagedLayer, CloseLayer, SetRenderLayer,
// GetLayerByIdLocked, Dispose) are extracted from SurfaceFlinger.cs into the class below, and for the candidate the real
// sessionRetention probe (NoteReleasedSession, RecordSessionRetention) is extracted from Library.cs. The doubles keep the
// production reference chain: registry -> producer -> BufferQueueCore -> KEvent -> KernelContext -> Switch (a stub
// device holding 4 MB) -> GpuContext.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Logging;
using Ryujinx.HLE;
using Ryujinx.HLE.HOS;
using Ryujinx.HLE.HOS.Kernel.Common;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.HLE.HOS.Services.SurfaceFlinger;

namespace Ryujinx.Common.Logging
{
    enum LogClass { SurfaceFlinger }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) { lock (Lines) Lines.Add(m); } }
    static class Logger { public static Sink Info = new(); public static Sink Error = new(); }
}
namespace Ryujinx.Common
{
    static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
            => Records.Add($"{stage} {status} {code} {detail}");
    }
}
namespace Ryujinx.Graphics.Gpu
{
    sealed class GpuContext { public readonly byte[] Caches = new byte[1 << 20]; }
}
namespace Ryujinx.HLE
{
    sealed class Switch
    {
        public readonly byte[] GuestMemory = new byte[4 << 20];
        public Ryujinx.Graphics.Gpu.GpuContext Gpu { get; } = new();
    }
}
namespace Ryujinx.HLE.HOS
{
    sealed class KernelContext { public readonly Switch Device; public KernelContext(Switch device) { Device = device; } }
}
namespace Ryujinx.HLE.HOS.Kernel.Common
{
    abstract class KAutoObject { protected KernelContext KernelContext; protected KAutoObject(KernelContext context) { KernelContext = context; } }
}
namespace Ryujinx.HLE.HOS.Kernel.Threading
{
    sealed class KReadableEvent : KAutoObject { public KReadableEvent(KernelContext context) : base(context) { } }
    sealed class KEvent : KAutoObject
    {
        public readonly KReadableEvent ReadableEvent;
        public KEvent(KernelContext context) : base(context) { ReadableEvent = new KReadableEvent(context); }
    }
}
namespace Ryujinx.HLE.HOS.Services.Vi
{
    enum ResultCode { Success = 0, InvalidArguments = 1, InvalidValue = 2, PermissionDenied = 3 }
}
namespace Ryujinx.HLE.HOS.Services.SurfaceFlinger
{
    enum ResultCode { Success = 0 }
    enum LayerState { NotInitialized, ManagedClosed, ManagedOpened, Stray }
    interface IConsumerListener { }
    interface IBinder
    {
        ResultCode AdjustRefcount(int addVal, int type);
        void GetNativeHandle(uint typeId, out KReadableEvent readableEvent);
        ResultCode OnTransact(uint code, uint flags, ReadOnlySpan<byte> inputParcel, Span<byte> outputParcel);
    }
    abstract class IHOSBinderDriver
    {
        protected abstract ResultCode AdjustRefcount(int binderId, int addVal, int type);
        protected abstract void GetNativeHandle(int binderId, uint typeId, out KReadableEvent readableEvent);
        protected abstract ResultCode OnTransact(int binderId, uint code, uint flags, ReadOnlySpan<byte> inputParcel, Span<byte> outputParcel);
    }
    sealed class BufferQueueCore
    {
        public readonly Switch Device;
        public readonly KEvent WaitBufferFreeEvent;
        public bool Active = true;
        public int Prepared;
        public event Action BufferQueued;
        public BufferQueueCore(Switch device) { Device = device; WaitBufferFreeEvent = new KEvent(new KernelContext(device)); }
        public void PrepareForExit() { Active = false; Prepared++; }
        public void Queue() => BufferQueued?.Invoke();
    }
    abstract class IGraphicBufferProducer : IBinder
    {
        public ResultCode AdjustRefcount(int addVal, int type) => ResultCode.Success;
        public void GetNativeHandle(uint typeId, out KReadableEvent readableEvent) => readableEvent = null;
        public ResultCode OnTransact(uint code, uint flags, ReadOnlySpan<byte> inputParcel, Span<byte> outputParcel) => ResultCode.Success;
    }
    sealed class BufferQueueProducer : IGraphicBufferProducer { public readonly BufferQueueCore Core; public BufferQueueProducer(BufferQueueCore core) { Core = core; } }
    sealed class BufferQueueConsumer { public readonly BufferQueueCore Core; public BufferQueueConsumer(BufferQueueCore core) { Core = core; } }
    sealed class BufferItemConsumer
    {
        public BufferItemConsumer(Switch device, BufferQueueConsumer consumer, ulong consumerUsage, int bufferCount, bool controlledByApp,
                                  IConsumerListener listener) { }
    }
    static class BufferQueue
    {
        public static BufferQueueCore CreateBufferQueue(Switch device, ulong pid, out BufferQueueProducer producer, out BufferQueueConsumer consumer)
        {
            BufferQueueCore core = new(device);
            producer = new BufferQueueProducer(core);
            consumer = new BufferQueueConsumer(core);
            return core;
        }
    }
    class SurfaceFlinger : IConsumerListener, IDisposable
    {
        private readonly Switch _device;
        private readonly Dictionary<long, Layer> _layers = new();
        private bool _isRunning = true;
        private readonly AutoResetEvent _nextFrameEvent = new(true);
        private readonly Lock _lock = new();
        public long RenderLayerId { get; private set; }
        public SurfaceFlinger(Switch device) { _device = device; }
        public void Create(ulong pid, long layerId, LayerState state) => CreateLayerFromId(pid, layerId, state);
        public int BinderIdOf(long layerId) => _layers[layerId].ProducerBinderId;
        public BufferQueueCore[] Cores() => _layers.Values.Select(l => l.Core).ToArray();
        public bool IsRunning => _isRunning;
//__FLINGER_MEMBERS__
    }
}
namespace Ryujinx.Library
{
    static class Library
    {
#if PROBE
        public static void Note(Switch context) => NoteReleasedSession(context);
        public static void Retention() => RecordSessionRetention();
//__PROBE__
#endif
    }
}
static class Program
{
    static readonly Dictionary<string, object> Report = new();
    static SurfaceFlinger LiveFlinger;
    static Switch Leaked;

    static IDictionary Registry => (IDictionary)typeof(HOSBinderDriverServer)
        .GetField("_registeredBinderObjects", BindingFlags.NonPublic | BindingFlags.Static).GetValue(null);

    // The closed session A, built and released here so nothing in Main holds it strongly.
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (WeakReference Device, WeakReference Gpu) CloseSessionA()
    {
        Switch device = new();
        SurfaceFlinger flinger = new(device);
        flinger.Create(1, 1, LayerState.ManagedClosed);
        flinger.Create(1, 2, LayerState.Stray);
        flinger.Create(1, 3, LayerState.ManagedOpened);
        Report["registeredWithA"] = Registry.Count;
        // The guest destroys one layer itself (existing path, which unregisters it).
        int destroyedId = flinger.BinderIdOf(3);
        Report["guestDestroy"] = flinger.DestroyManagedLayer(3).ToString();
        Report["afterGuestDestroy"] = Registry.Count;
        BufferQueueCore[] cores = flinger.Cores();
        flinger.Dispose();
        Report["afterDispose"] = Registry.Count;
        // Horizon disposes once; a second Dispose must change nothing (Remove of an absent id is a no-op).
        flinger.Dispose();
        Report["afterSecondDispose"] = Registry.Count;
        Report["destroyedIdRegistered"] = Registry.Contains(destroyedId);
        Report["prepareForExitCalls"] = cores.Sum(c => c.Prepared);
        Report["coresInactive"] = cores.All(c => !c.Active);
        Report["composerStopped"] = !flinger.IsRunning;
#if PROBE
        Ryujinx.Library.Library.Note(device);
#endif
        return (new WeakReference(device), new WeakReference(device.Gpu));
    }

    // A session some other root keeps (the probe must report it as retained).
    [MethodImpl(MethodImplOptions.NoInlining)]
    static void CloseLeakedSession()
    {
        Leaked = new Switch();
#if PROBE
        Ryujinx.Library.Library.Note(Leaked);
#endif
    }

    static void Collect()
    {
        GC.Collect(2, GCCollectionMode.Aggressive, blocking: true, compacting: true);
        GC.WaitForPendingFinalizers();
        GC.Collect();
    }

    static void Main()
    {
        Switch live = new();
        LiveFlinger = new SurfaceFlinger(live);
        LiveFlinger.Create(2, 1, LayerState.ManagedOpened);
        int liveId = LiveFlinger.BinderIdOf(1);
        Report["registeredBefore"] = Registry.Count;

        (WeakReference device, WeakReference gpu) = CloseSessionA();
        Collect();
        Report["registryAfter"] = Registry.Count;
        Report["liveSessionBinderKept"] = Registry.Contains(liveId);
        Report["closedSwitchAlive"] = device.IsAlive;
        Report["closedGpuAlive"] = gpu.IsAlive;
        Report["liveSwitchAlive"] = GC.GetGeneration(live) >= 0;
        PropertyInfo accessor = typeof(HOSBinderDriverServer).Assembly
            .GetType("Ryujinx.HLE.HOS.Services.SurfaceFlinger.BinderRegistryDiagnostics")?.GetProperty("RegisteredBinderCount");
        Report["publicAccessor"] = accessor?.GetValue(null);
#if PROBE
        Ryujinx.Library.Library.Retention();
        CloseLeakedSession();
        Collect();
        Ryujinx.Library.Library.Retention();
#endif
        Report["journal"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records;
        Report["errors"] = Logger.Error.Lines;
        GC.KeepAlive(LiveFlinger);
        GC.KeepAlive(live);
        GC.KeepAlive(Leaked);
        Console.WriteLine(JsonSerializer.Serialize(Report));
    }
}
