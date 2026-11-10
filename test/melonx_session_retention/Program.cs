// Fixture of melonx_session_retention_test.py. Compiled beside the REAL files of the variant (control: the Core 658
// preparation; candidate: the same plus adapt_session_retention): PerformanceStatistics.cs, Ryujinx.Common's
// PerformanceCounter.cs, the time service (TimeManager.cs, TimeSharedMemory.cs, ResultCode.cs, Types/, Clock/ and
// Clock/Types/ but ClockSnapshot.cs), BluetoothEventManager.cs, KEvent.cs and KWritableEvent.cs. The real
// Switch.Dispose members (Switch.cs), the lines the adapter adds to Horizon.Dispose after KernelContext.Dispose
// (Horizon.cs, candidate only) and the sessionRetention probe (NoteReleasedSession, RecordSessionRetention from
// Library.cs) are pasted at the markers. The doubles keep the production chains: statistics timer -> Elapsed ->
// PerformanceStatistics -> Switch, and time singleton -> shared memory / KEvent -> KernelContext -> Switch, the Switch
// holding 8 MB of guest memory and a GpuContext holding 2 MB.
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;
using System.Text.Json;
using System.Threading;
using Ryujinx.HLE;
using Ryujinx.HLE.HOS;
using Ryujinx.HLE.HOS.Kernel;
using Ryujinx.HLE.HOS.Kernel.Threading;
using Ryujinx.HLE.HOS.Services.Bluetooth.BluetoothDriver;
using Ryujinx.HLE.HOS.Services.Time;
using Ryujinx.HLE.HOS.Services.Time.Clock;

namespace Ryujinx.Common
{
    static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
            => Records.Add($"{stage} {status} {code} {detail}");
    }
}
namespace Ryujinx.Common.Utilities
{
    static class RandomExtensions
    {
        public static UInt128 NextUInt128(this Random random) => new((ulong)random.NextInt64(), (ulong)random.NextInt64());
    }
}
namespace Ryujinx.Cpu
{
    public interface ITickSource
    {
        ulong Frequency { get; }
        ulong Counter { get; }
    }
}
namespace Ryujinx.Horizon.Common
{
    public readonly struct Result
    {
        public static Result Success => default;
    }
}
namespace Ryujinx.HLE.Exceptions
{
    class InternalServiceException : Exception { public InternalServiceException(string message) : base(message) { } }
}
namespace Ryujinx.Graphics.Gpu
{
    public sealed class GpuContext { public readonly byte[] Caches = new byte[2 << 20]; }
}
namespace Ryujinx.HLE
{
    sealed class Holder { public object Value; }
    static class TitleIDs { public static readonly Holder CurrentApplication = new(); }
    public sealed class Disposable : IDisposable { public bool Disposed; public void Dispose() => Disposed = true; }
    public sealed class GuestMemory : IDisposable
    {
        public readonly byte[] Bytes = new byte[8 << 20];
        public T Read<T>(ulong offset) where T : unmanaged => default;
        public void Dispose() { }
    }

    // Constructed in Switch's order (Switch.cs: Memory, Gpu, System, Statistics); disposed by the real Switch.Dispose.
    public class Switch : IDisposable
    {
        public static Switch Shared { get; set; }
        public GuestMemory Memory { get; }
        public Ryujinx.Graphics.Gpu.GpuContext Gpu { get; }
        public HOS.Horizon System { get; }
        public PerformanceStatistics Statistics { get; }
        public Disposable AudioDeviceDriver { get; } = new();
        public Disposable FileSystem { get; } = new();
        public Disposable Debugger { get; }

        public Switch(long posixTime, Cpu.ITickSource tickSource)
        {
            Shared = this;
            Memory = new GuestMemory();
            Gpu = new Ryujinx.Graphics.Gpu.GpuContext();
            System = new HOS.Horizon(this, posixTime, tickSource);
            Statistics = new PerformanceStatistics(this);
        }

//__SWITCH_DISPOSE__
    }
}
namespace Ryujinx.HLE.HOS.Kernel
{
    public sealed class KernelContext : IDisposable
    {
        public readonly Switch Device;
        public bool Disposed;
        public KernelContext(Switch device) { Device = device; }
        public void Dispose() => Disposed = true;
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Common
{
    public class KAutoObject
    {
        protected KernelContext KernelContext;
        public KAutoObject(KernelContext context) { KernelContext = context; }
        public KernelContext FixtureOwner => KernelContext;
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Threading
{
    public class KReadableEvent : Ryujinx.HLE.HOS.Kernel.Common.KAutoObject
    {
        // The count lives apart from the event, so a test can watch it without keeping the event's session reachable.
        public sealed class SignalCount { public int Value; }
        public readonly SignalCount Signals = new();
        public KReadableEvent(KernelContext context) : base(context) { }
        public void Signal() => Interlocked.Increment(ref Signals.Value);
        public Ryujinx.Horizon.Common.Result Clear() => Ryujinx.Horizon.Common.Result.Success;
    }
}
namespace Ryujinx.HLE.HOS.Kernel.Memory
{
    public enum KMemoryPermission { Read = 1 }
    public class SharedMemoryStorage
    {
        private readonly KernelContext _context;
        public readonly byte[] Bytes;
        public SharedMemoryStorage(KernelContext context, int size) { _context = context; Bytes = new byte[size]; }
        public void ZeroFill() => Array.Clear(Bytes);
        public ref T GetRef<T>(ulong offset) where T : unmanaged => ref MemoryMarshal.Cast<byte, T>(Bytes.AsSpan((int)offset, Unsafe.SizeOf<T>()))[0];
    }
    public class KSharedMemory : Ryujinx.HLE.HOS.Kernel.Common.KAutoObject
    {
        public readonly SharedMemoryStorage Storage;
        public KSharedMemory(KernelContext context, SharedMemoryStorage storage, ulong ownerPid, ulong ownerPermission, KMemoryPermission permission)
            : base(context) { Storage = storage; }
    }
}
namespace Ryujinx.HLE.HOS.Services.Time.TimeZone
{
    class TimeZoneManager
    {
        public ResultCode SetDeviceLocationNameWithTimeZoneRule(string locationName, System.IO.Stream stream) => ResultCode.Success;
        public void SetUpdatedTime(SteadyClockTimePoint timePoint, bool bypassUninitialized = false) { }
        public void SetTotalLocationNameCount(uint count) { }
        public void SetTimeZoneRuleVersion(UInt128 version) { }
        public void MarkInitialized() { }
    }
    class TimeZoneContentManager
    {
        internal TimeZoneManager Manager { get; } = new();
        internal void Initialize(TimeManager timeManager, Switch device) { }
    }
}
namespace Ryujinx.HLE.HOS.Services.SurfaceFlinger
{
    public static class BinderRegistryDiagnostics { public static int RegisteredBinderCount => 0; }
}
namespace Ryujinx.HLE.HOS
{
    using Ryujinx.HLE.HOS.Kernel.Memory;
    using TimeServiceManager = Services.Time.TimeManager;

    // The time part of Horizon's constructor (Horizon.cs:162-237), each TimeServiceManager call as in production; the
    // network clock's sufficient accuracy is a fixed value instead of NxSettings'.
    public class Horizon : IDisposable
    {
        public const int TimeSize = 0x1000;
        internal KernelContext KernelContext { get; }
        internal Switch Device { get; private set; }
        public Cpu.ITickSource TickSource { get; }
        public SharedMemoryStorage TimeStorage { get; }
        public KSharedMemory TimeSharedMemory { get; }

        public Horizon(Switch device, long posixTime, Cpu.ITickSource tickSource)
        {
            Device = device;
            KernelContext = new KernelContext(device);
            TickSource = tickSource;
            SharedMemoryStorage timeStorage = new(KernelContext, TimeSize);
            KSharedMemory timeSharedMemory = new(KernelContext, timeStorage, 0, 0, KMemoryPermission.Read);
            TimeStorage = timeStorage;
            TimeSharedMemory = timeSharedMemory;

            TimeServiceManager.Instance.Initialize(device, this, timeSharedMemory, timeStorage, TimeSize);

            UInt128 clockSourceId = new(0x36a0328702ce8bc1, 0x1608eaba02333284);
            TimeSpanType systemTime = TimeSpanType.FromSeconds(posixTime);
            TimeServiceManager.Instance.SetupStandardSteadyClock(TickSource, clockSourceId, TimeSpanType.Zero, TimeSpanType.Zero, TimeSpanType.Zero, false);
            TimeServiceManager.Instance.SetupStandardLocalSystemClock(TickSource, new SystemClockContext(), systemTime.ToSeconds());
            TimeServiceManager.Instance.StandardLocalSystemClock.GetClockContext(TickSource, out SystemClockContext localSytemClockContext);
            TimeSpanType standardNetworkClockSufficientAccuracy = new(10 * 60000000000);
            TimeServiceManager.Instance.SetupStandardNetworkSystemClock(localSytemClockContext, standardNetworkClockSufficientAccuracy);
            TimeServiceManager.Instance.SetupStandardUserSystemClock(TickSource, true, localSytemClockContext.SteadyTimePoint);
            TimeServiceManager.Instance.SetupEphemeralNetworkSystemClock();
        }

        // Horizon.Dispose(bool) once its termination thread has terminated and joined every process.
        public void Dispose()
        {
            KernelContext.Dispose();
//__HORIZON_RELEASE__
        }
    }
}
namespace Ryujinx.Library
{
    static class Library
    {
        public static void Note(Switch context) => NoteReleasedSession(context);
        public static void Retention() => RecordSessionRetention();
//__PROBE__
    }
}

sealed class FixedTickSource : Ryujinx.Cpu.ITickSource
{
    public ulong Frequency => 19_200_000;
    public ulong Counter { get; set; }
}

static class Program
{
    const long PosixA = 1_800_000_000, PosixB = 1_800_000_100, PosixC = 1_800_000_200;
    static readonly Dictionary<string, object> Report = new();
    static readonly FixedTickSource Ticks = new();
    static Switch SessionC;
    static int NextHandle = 0x40;

    static object Field(object target, string name)
    {
        for (Type type = target.GetType(); type != null; type = type.BaseType)
        {
            FieldInfo field = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.Public);
            if (field != null)
            {
                return field.GetValue(target);
            }
        }
        throw new MissingFieldException(target.GetType().Name, name);
    }

    static bool HasField(object target, string name) => target.GetType().GetField(name, BindingFlags.Instance | BindingFlags.NonPublic) != null;

    static IEnumerable<KWritableEvent> OperationEvents() =>
        new object[] { TimeManager.Instance.LocalClockContextWriter, TimeManager.Instance.NetworkClockContextWriter, TimeManager.Instance.EphemeralClockContextWriter }
            .SelectMany(writer => ((IEnumerable)Field(writer, "_operationEventList")).Cast<KWritableEvent>());

    static KEvent[] BluetoothEvents() =>
    [
        BluetoothEventManager.InitializeBleDebugEvent, BluetoothEventManager.UnknownBleDebugEvent, BluetoothEventManager.RegisterBleDebugEvent,
        BluetoothEventManager.InitializeBleEvent, BluetoothEventManager.UnknownBleEvent, BluetoothEventManager.RegisterBleEvent,
    ];

    // Every root this fixture knows, read by reflection whatever the variant: which ones still reach this session.
    static Dictionary<string, object> Census(Switch device)
    {
        KEvent correction = (KEvent)Field(TimeManager.Instance.StandardUserSystemClock, "_autoCorrectionEvent");
        System.Timers.Timer timer = (System.Timers.Timer)Field(device.Statistics, "_resetTimer");
        return new Dictionary<string, object>
        {
            ["statisticsTimerEnabled"] = timer.Enabled,
            ["statisticsStoresDevice"] = HasField(device.Statistics, "_device") && Field(device.Statistics, "_device") == device,
            ["timeSharedMemoryDevice"] = Field(TimeManager.Instance.SharedMemory, "_device") == device,
            ["timeSharedMemoryStorage"] = Field(TimeManager.Instance.SharedMemory, "_timeSharedMemoryStorage") == device.System.TimeStorage,
            ["automaticCorrectionEvent"] = correction?.WritableEvent.FixtureOwner.Device == device,
            ["operationEvents"] = OperationEvents().Count(e => e.FixtureOwner.Device == device),
            ["bluetoothEvents"] = BluetoothEvents().Count(e => e?.WritableEvent.FixtureOwner.Device == device),
        };
    }

    static Switch Open(long posix)
    {
        Ticks.Counter = 19_200_000UL * 5; // each session's tick source starts again (Horizon creates one per session)
        return new Switch(posix, Ticks);
    }

    // ISystemClock command 4 (StaticService/ISystemClock.cs:110-128) on the local clock.
    static KEvent GuestOperationEvent(Switch device)
    {
        KEvent kEvent = new(device.System.KernelContext);
        TimeManager.Instance.StandardLocalSystemClock.RegisterOperationEvent(kEvent.WritableEvent);
        return kEvent;
    }

    // btdrv InitializeBluetoothLe, not in debug mode (Bluetooth/IBluetoothDriver.cs:29-95): events made once per handle.
    static void GuestBluetooth(Switch device)
    {
        if (BluetoothEventManager.InitializeBleEventHandle == 0)
        {
            BluetoothEventManager.InitializeBleEvent = new KEvent(device.System.KernelContext);
            BluetoothEventManager.InitializeBleEventHandle = NextHandle++;
        }
        if (BluetoothEventManager.UnknownBleEventHandle == 0)
        {
            BluetoothEventManager.UnknownBleEvent = new KEvent(device.System.KernelContext);
            BluetoothEventManager.UnknownBleEventHandle = NextHandle++;
        }
        if (BluetoothEventManager.RegisterBleEventHandle == 0)
        {
            BluetoothEventManager.RegisterBleEvent = new KEvent(device.System.KernelContext);
            BluetoothEventManager.RegisterBleEventHandle = NextHandle++;
        }
    }

    // What the game reads of the time once its session is set up.
    static Dictionary<string, object> Time(Switch device, long posix)
    {
        TimeManager time = TimeManager.Instance;
        byte[] bytes = device.System.TimeStorage.Bytes;
        uint index = BitConverter.ToUInt32(bytes, 0x38);
        SystemClockContext local = MemoryMarshal.Read<SystemClockContext>(bytes.AsSpan(0x38 + 8 + (int)(index & 1) * Unsafe.SizeOf<SystemClockContext>()));
        ResultCode current = time.StandardLocalSystemClock.GetCurrentTime(Ticks, out long now);
        KReadableEvent correction = time.StandardUserSystemClock.GetAutomaticCorrectionReadableEvent();
        int before = correction.Signals.Value;
        time.StandardUserSystemClock.SignalAutomaticCorrectionEvent();
        return new Dictionary<string, object>
        {
            ["sharedMemoryIsSession"] = time.SharedMemory.GetSharedMemory() == device.System.TimeSharedMemory,
            ["sharedMemorySha"] = Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(bytes)),
            ["sharedMemoryWritten"] = bytes.Any(b => b != 0),
            ["sharedLocalOffsetMinusPosix"] = local.Offset - posix,
            ["sharedLocalClockSource"] = local.SteadyTimePoint.ClockSourceId.ToString("x"),
            ["automaticCorrectionByte"] = bytes[0xC8 + 4 + (int)(BitConverter.ToUInt32(bytes, 0xC8) & 1)],
            ["currentTime"] = current.ToString(),
            ["currentTimeMinusPosix"] = now - posix,
            ["automaticCorrectionEnabled"] = time.StandardUserSystemClock.IsAutomaticCorrectionEnabled(),
            ["automaticCorrectionEventIsSession"] = correction.FixtureOwner == device.System.KernelContext,
            ["automaticCorrectionSignalled"] = correction.Signals.Value == before + 1,
        };
    }

    // Session A plays without the two unproven calls; closed and released here so nothing in Main holds it strongly.
    [MethodImpl(MethodImplOptions.NoInlining)]
    static WeakReference[] SessionA()
    {
        Switch device = Open(PosixA);
        Report["timeA"] = Time(device, PosixA);
        Thread.Sleep(900); // the statistics timer (750 ms) has fired
        Report["timerRunningA"] = ((System.Timers.Timer)Field(device.Statistics, "_resetTimer")).Enabled;
        device.Dispose();
        Report["timerEnabledAfterCloseA"] = ((System.Timers.Timer)Field(device.Statistics, "_resetTimer")).Enabled;
        Report["timeHoldsAAfterClose"] = Census(device);
        Ryujinx.Library.Library.Note(device);
        return [new(device), new(device.Gpu), new(device.Statistics), new(device.System)];
    }

    // Session B re-initialises the time service and makes both unproven calls; closed and released here.
    [MethodImpl(MethodImplOptions.NoInlining)]
    static (WeakReference[] Refs, KReadableEvent.SignalCount OperationEventSignals) SessionB()
    {
        Switch device = Open(PosixB);
        Report["timeB"] = Time(device, PosixB);
        KEvent operation = GuestOperationEvent(device);
        GuestBluetooth(device);
        Report["bluetoothBOwned"] = BluetoothEvents().Count(e => e?.WritableEvent.FixtureOwner.Device == device);
        device.Dispose();
        Report["censusBAfterClose"] = Census(device);
        Report["bluetoothHandlesAfterCloseB"] = new[] { BluetoothEventManager.InitializeBleEventHandle, BluetoothEventManager.UnknownBleEventHandle,
                                                         BluetoothEventManager.RegisterBleEventHandle };
        Ryujinx.Library.Library.Note(device);
        return ([new(device), new(device.Gpu), new(device.Statistics), new(device.System)], operation.ReadableEvent.Signals);
    }

    static void Collect()
    {
        GC.Collect(2, GCCollectionMode.Aggressive, blocking: true, compacting: true);
        GC.WaitForPendingFinalizers();
        GC.Collect();
    }

    [MethodImpl(MethodImplOptions.NoInlining)]
    static Dictionary<string, object> Alive(WeakReference[] refs)
    {
        Dictionary<string, object> alive = new()
        {
            ["switch"] = refs[0].IsAlive, ["gpu"] = refs[1].IsAlive, ["statistics"] = refs[2].IsAlive, ["horizon"] = refs[3].IsAlive,
        };
        if (refs[0].Target is Switch held)
        {
            alive["census"] = Census(held);
        }
        return alive;
    }

    static void Main()
    {
        WeakReference[] a = SessionA();
        Collect();
        Report["afterCloseA"] = Alive(a);
        Ryujinx.Library.Library.Retention();

        (WeakReference[] b, KReadableEvent.SignalCount operationB) = SessionB();
        Collect();
        Report["afterCloseB_A"] = Alive(a);
        Report["afterCloseB_B"] = Alive(b);
        Ryujinx.Library.Library.Retention();

        // Session C: the next launch after B. Its clock setup broadcasts to the registered operation events, and its
        // Bluetooth initialisation creates events only for a handle that is 0.
        int signalsBefore = operationB.Value;
        SessionC = Open(PosixC);
        Report["timeC"] = Time(SessionC, PosixC);
        Report["closedSessionEventSignalledBySessionC"] = operationB.Value - signalsBefore;
        Report["operationEventsAfterC"] = OperationEvents().Count();
        GuestBluetooth(SessionC);
        Report["bluetoothCOwned"] = BluetoothEvents().Count(e => e?.WritableEvent.FixtureOwner.Device == SessionC);
        GuestOperationEvent(SessionC);
        // The probe's census on a session the statics do hold (C is live): shared memory, correction event, the operation
        // event and three Bluetooth events. Candidate only (the control has no census).
        Report["censusOfLiveC"] = typeof(TimeManager).Assembly.GetType("Ryujinx.HLE.HOS.Services.Time.SessionRootDiagnostics")?
            .GetMethod("StaticReferencesTo").Invoke(null, [SessionC]);
        Collect();
        Report["afterOpenC_A"] = Alive(a);
        Report["afterOpenC_B"] = Alive(b);

        Report["journal"] = Ryujinx.Common.EmbeddedLaunchDiagnostics.Records;
        GC.KeepAlive(SessionC);
        Console.WriteLine(JsonSerializer.Serialize(Report));
        Environment.Exit(0); // the control's statistics timers are still running
    }
}
