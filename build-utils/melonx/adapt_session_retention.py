"""Release the process-wide roots that keep a closed session's emulated Switch reachable, and name them in the journal.

IPA 657/658, maintainer's iPhone, 4-5 November 2026 (private logs, not in the repository): every "sessionRetention" line
written at a close (adapt_binder_teardown) reads "retained", Switch and GpuContext still reachable 1/1 with the binder
registry already empty, about 455 MB of managed heap still live after the forced full collection (282 MiB of it large
objects). With two sessions in one process (pid 10361) the line read 1/1 after the first close (379 MB) and 2/2 after
the second (683 MB): the first session survived a whole second session, which started about 495 MB higher.

Mechanism (read in the Core 658 preparation; Ryujinx.HLE files byte-identical to upstream MeloNX 13700519 where no
adapter edits them):
- PerformanceStatistics (src/Ryujinx.HLE/PerformanceStatistics.cs:9,31-54) stores the Switch and starts a 750 ms
  auto-reset System.Timers.Timer whose Elapsed handler is the statistics object. Nothing stops or disposes it: the file
  has no Dispose, and Switch.Dispose(bool) (Switch.cs:204-217) disposes System, the audio driver, the file system,
  memory and the debugger only. A running timer is held by the runtime's static timer queue through its callback, so the
  chain timer queue -> System.Timers.Timer -> Elapsed -> PerformanceStatistics -> Switch -> GpuContext is rooted for the
  rest of the process, once per closed session (cumulative). The stored Switch is never read.
- The time service is a process singleton (Services/Time/TimeManager.cs:13-23). Horizon's constructor (Horizon.cs:176)
  calls TimeManager.Initialize for every session: TimeSharedMemory keeps that session's Switch, KSharedMemory and
  SharedMemoryStorage (TimeSharedMemory.cs:14-16,27-35) and StandardUserSystemClockCore keeps a KEvent of its
  KernelContext (StandardUserSystemClockCore.cs:13,66-69). Horizon.Dispose (Horizon.cs:468-535) never releases them. A
  KAutoObject holds its KernelContext, whose Device is the Switch, so the latest closed session stays reachable until
  the next launch overwrites these fields (not cumulative, but a whole session graph held in the menu and during the
  next launch's construction, which allocates guest memory and the GpuContext before Horizon).
- Two code paths whose use by Hogwarts Legacy is unproven: ISystemClock command 4 registers a KWritableEvent of the
  calling session in the singleton clock writers' operation event list, which is never trimmed
  (Clock/SystemClockContextUpdateCallback.cs:9,30-35; StaticService/ISystemClock.cs:110-128): cumulative retention, and
  the next session's clock setup then signals the closed session's events. btdrv InitializeBluetoothLe keeps six KEvents
  and their handle values in static fields created once per process (Bluetooth/BluetoothDriver/
  BluetoothEventManager.cs; IBluetoothDriver.cs:29-95): the first session that opened it stays reachable and later
  sessions are handed handle values of a handle table that no longer exists.

Change:
- PerformanceStatistics implements IDisposable: Dispose unhooks Elapsed and disposes the timer. The unread Switch field
  is no longer stored (the constructor keeps its signature), so even an undisposed statistics object reaches no
  session. Switch.Dispose(bool) disposes Statistics right after System. While a game runs, nothing changes: the timer
  and every Record*/Get* member behave as before (they never use the timer); a callback already running finishes on the
  object's own arrays under its own locks.
- Horizon.Dispose(bool), after KernelContext.Dispose (every guest and HLE process terminated and joined, nvservices
  destroyed), calls TimeManager.ReleaseSession(Device, KernelContext) and BluetoothEventManager.ReleaseSession(
  KernelContext). Each release is identity-checked and clears only what belongs to the closing session: the time shared
  memory's device, shared memory and storage when its device is this Switch; the automatic correction event and the
  clock operation events (under the list's existing monitor) and the Bluetooth events with their handle values when
  their KWritableEvent belongs to this KernelContext. KWritableEvent gains a read-only internal OwnerContext accessor for
  that check. The next session's Horizon constructor calls TimeManager.Initialize before any time setup or IPC, and
  IBluetoothDriver creates the events again when their handle is 0 (the first-session path).
- Library (journal only): the sessionRetention probe also keeps weak references to each closed session's
  PerformanceStatistics and Horizon, and the line adds how many are still reachable and how many references the time
  service and Bluetooth statics still hold to the tracked closed sessions (HLE's public read-only
  SessionRootDiagnostics), so the next device log names any root still holding a session. No collection is added and
  the status ("released", "retained", "none") keeps its meaning.

Not changed: rendering, synchronisation, draws and quality (no per-title gate is needed: the releases run only at
session teardown, after the guest has terminated); the quarantine path (LoadApplication throws before
context.Dispose when guest termination is unproven, keeping everything rooted); other singletons; other copies of these
files in Ryujinx/Headless are not built for iOS. Not measured on an iPhone.
Fail closed on drift: each file must be the Core 658 preparation's.
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.HLE/PerformanceStatistics.cs': '843280c9bbc5d7fe206aaf486615894784512164ee2654328b8c714265897c89',
    'src/Ryujinx.HLE/Switch.cs': 'b04dc2434c97e623e47e128c197664da6c51d58e8aeac557f2e01b1f82d1672a',
    'src/Ryujinx.HLE/HOS/Horizon.cs': '41bfa93d42243b67c9be511294cb536bca238d42561e8d74df607b343b1a02a9',
    'src/Ryujinx.HLE/HOS/Services/Time/TimeManager.cs': 'c6d686e8837ab2badd5655551f521bfcf140be474d5ca3b9b22a89959c3e8a7a',
    'src/Ryujinx.HLE/HOS/Services/Time/TimeSharedMemory.cs': '26e5d5464ca071bc09b3891a18ab6eb1c093f5eb525b593a163c8516386f6b66',
    'src/Ryujinx.HLE/HOS/Services/Time/Clock/StandardUserSystemClockCore.cs': 'd677e6620b71fe85c4100a00692820790c226d7857b25376680e455587eea50d',
    'src/Ryujinx.HLE/HOS/Services/Time/Clock/SystemClockContextUpdateCallback.cs': '513f096c60eaa84ef3a8263671cc11c6a835bb100676f54ba4ac39adbfa08e11',
    'src/Ryujinx.HLE/HOS/Kernel/Threading/KWritableEvent.cs': '6d4224070cae2dc2a5ff6a833c80369c6f67bfb61f5b9733504835d3137d78f5',
    'src/Ryujinx.HLE/HOS/Services/Bluetooth/BluetoothDriver/BluetoothEventManager.cs': '2935b090f6bf4fd45371408888f29b8ac6b34a266257d4b3515f8d0ad04611d2',
    'src/Ryujinx.Library/Library.cs': '20f572ce28eb4c2f811ac6f88a976f5c9f76ff82a632d42da9ecddec99778dad',
}

BLUETOOTH_EVENTS = ('InitializeBleDebugEvent', 'UnknownBleDebugEvent', 'RegisterBleDebugEvent',
                    'InitializeBleEvent', 'UnknownBleEvent', 'RegisterBleEvent')


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    statistics = paths['src/Ryujinx.HLE/PerformanceStatistics.cs']
    once(statistics, '''    public class PerformanceStatistics
    {
        private readonly Switch _device;
''', '''    public class PerformanceStatistics : System.IDisposable
    {
        // RewindBox (adapt_session_retention): the Switch is no longer stored here (it was never read), so this object,
        // which a running timer keeps reachable, can never keep a closed session reachable.
''')
    once(statistics, '''            _device = device;

            _frameRate = new double[1];''', '''            _frameRate = new double[1];''')
    once(statistics, '''        private void ResetTimerElapsed(object sender, ElapsedEventArgs e)''', '''        // RewindBox (adapt_session_retention): a running System.Timers.Timer is held by the runtime's static timer queue
        // through its Elapsed handler; without this, every closed session's statistics kept firing every 750 ms for the
        // rest of the process. Called by Switch.Dispose; a second call changes nothing.
        public void Dispose()
        {
            _resetTimer.Elapsed -= ResetTimerElapsed;
            _resetTimer.Dispose();
            System.GC.SuppressFinalize(this);
        }

        private void ResetTimerElapsed(object sender, ElapsedEventArgs e)''')

    switch = paths['src/Ryujinx.HLE/Switch.cs']
    once(switch, '''                System.Dispose();
                AudioDeviceDriver.Dispose();''', '''                System.Dispose();
                // RewindBox (adapt_session_retention): stop the statistics timer, which the runtime's timer queue keeps.
                Statistics?.Dispose();
                AudioDeviceDriver.Dispose();''')

    horizon = paths['src/Ryujinx.HLE/HOS/Horizon.cs']
    once(horizon, '''                KernelContext.Dispose();
''', '''                KernelContext.Dispose();

                // RewindBox (adapt_session_retention): every process is terminated and joined; the process-wide time
                // service and Bluetooth statics release what belongs to this session only (identity-checked).
                TimeServiceManager.Instance.ReleaseSession(Device, KernelContext);
                Services.Bluetooth.BluetoothDriver.BluetoothEventManager.ReleaseSession(KernelContext);
''')

    time = paths['src/Ryujinx.HLE/HOS/Services/Time/TimeManager.cs']
    once(time, '''        public void InitializeTimeZone(Switch device)''', '''        // RewindBox (adapt_session_retention): called by Horizon.Dispose once the session's processes are gone. Clears
        // only the references that belong to this session; the next session's Horizon calls Initialize before any setup.
        internal void ReleaseSession(Switch device, Kernel.KernelContext context)
        {
            SharedMemory.Release(device);
            StandardUserSystemClock.ReleaseAutomaticCorrectionEvent(context);
            LocalClockContextWriter.ReleaseOperationEvents(context);
            NetworkClockContextWriter.ReleaseOperationEvents(context);
            EphemeralClockContextWriter.ReleaseOperationEvents(context);
        }

        // RewindBox (adapt_session_retention): references the singleton holds to this session, for the journal. Does not
        // create the singleton.
        internal static int CountSessionReferences(Switch device, Kernel.KernelContext context)
        {
            TimeManager instance = _instance;

            if (instance == null)
            {
                return 0;
            }

            return (instance.SharedMemory.Holds(device) ? 1 : 0) +
                (instance.StandardUserSystemClock.HoldsAutomaticCorrectionEvent(context) ? 1 : 0) +
                instance.LocalClockContextWriter.CountOperationEvents(context) +
                instance.NetworkClockContextWriter.CountOperationEvents(context) +
                instance.EphemeralClockContextWriter.CountOperationEvents(context);
        }

        public void InitializeTimeZone(Switch device)''')
    once(time, '''            SharedMemory.SetSteadyClockRawTimePoint(tickSource, currentTimePoint);
        }
    }
}''', '''            SharedMemory.SetSteadyClockRawTimePoint(tickSource, currentTimePoint);
        }
    }

    // RewindBox (adapt_session_retention): read-only, for the host's sessionRetention journal line. How many references
    // the process-wide time service and Bluetooth statics still hold to a closed session's Switch or kernel.
    public static class SessionRootDiagnostics
    {
        public static int StaticReferencesTo(Switch device)
        {
            Kernel.KernelContext context = device?.System?.KernelContext;

            if (context == null)
            {
                return 0;
            }

            return TimeManager.CountSessionReferences(device, context) +
                Bluetooth.BluetoothDriver.BluetoothEventManager.CountSessionEvents(context);
        }
    }
}''')

    shared = paths['src/Ryujinx.HLE/HOS/Services/Time/TimeSharedMemory.cs']
    once(shared, '''        public KSharedMemory GetSharedMemory()''', '''        // RewindBox (adapt_session_retention): forget the closing session's device and memory, only if they are its own.
        internal void Release(Switch device)
        {
            if (_device == device)
            {
                _device = null;
                _sharedMemory = null;
                _timeSharedMemoryStorage = null;
            }
        }

        internal bool Holds(Switch device) => _device == device;

        public KSharedMemory GetSharedMemory()''')

    user = paths['src/Ryujinx.HLE/HOS/Services/Time/Clock/StandardUserSystemClockCore.cs']
    once(user, '''        public ResultCode SetAutomaticCorrectionEnabled(''', '''        // RewindBox (adapt_session_retention): drop the closing session's event, only if it is its own.
        internal void ReleaseAutomaticCorrectionEvent(Kernel.KernelContext context)
        {
            if (HoldsAutomaticCorrectionEvent(context))
            {
                _autoCorrectionEvent = null;
            }
        }

        internal bool HoldsAutomaticCorrectionEvent(Kernel.KernelContext context) =>
            _autoCorrectionEvent != null && _autoCorrectionEvent.WritableEvent.OwnerContext == context;

        public ResultCode SetAutomaticCorrectionEnabled(''')

    callback = paths['src/Ryujinx.HLE/HOS/Services/Time/Clock/SystemClockContextUpdateCallback.cs']
    once(callback, '''        private void BroadcastOperationEvent()''', '''        // RewindBox (adapt_session_retention): the writers belong to the process-wide time service; drop the closing
        // session's events (never another session's) so they neither keep it reachable nor get signalled later.
        internal void ReleaseOperationEvents(Kernel.KernelContext context)
        {
            lock (_operationEventList)
            {
                _operationEventList.RemoveAll(e => e.OwnerContext == context);
            }
        }

        internal int CountOperationEvents(Kernel.KernelContext context)
        {
            lock (_operationEventList)
            {
                return _operationEventList.FindAll(e => e.OwnerContext == context).Count;
            }
        }

        private void BroadcastOperationEvent()''')

    writable = paths['src/Ryujinx.HLE/HOS/Kernel/Threading/KWritableEvent.cs']
    once(writable, '''        public void Signal()''', '''        // RewindBox (adapt_session_retention): read-only, so process-wide owners can release one session's events.
        internal KernelContext OwnerContext => KernelContext;

        public void Signal()''')

    bluetooth = paths['src/Ryujinx.HLE/HOS/Services/Bluetooth/BluetoothDriver/BluetoothEventManager.cs']
    release = ' +\n            '.join(f'Release(ref {name}, ref {name}Handle, context)' for name in BLUETOOTH_EVENTS)
    count = ' +\n            '.join(f'(Owned({name}, context) ? 1 : 0)' for name in BLUETOOTH_EVENTS)
    once(bluetooth, '''        public static int RegisterBleEventHandle;
''', f'''        public static int RegisterBleEventHandle;

        // RewindBox (adapt_session_retention): these events are created once per process and keep the session that
        // created them reachable; at its teardown, those of the closing session (only) and their handle values, which
        // belong to its handle table, are reset so a later session creates its own. Returns how many were reset.
        internal static int ReleaseSession(Kernel.KernelContext context) =>
            {release};

        internal static int CountSessionEvents(Kernel.KernelContext context) =>
            {count};

        private static bool Owned(KEvent kEvent, Kernel.KernelContext context) => kEvent != null && kEvent.WritableEvent.OwnerContext == context;

        private static int Release(ref KEvent kEvent, ref int handle, Kernel.KernelContext context)
        {{
            if (!Owned(kEvent, context))
            {{
                return 0;
            }}

            kEvent = null;
            handle = 0;

            return 1;
        }}
''')

    library = paths['src/Ryujinx.Library/Library.cs']
    once(library, '''        private static readonly List<(WeakReference Device, WeakReference Gpu)> _releasedSessions = new();''',
         '''        // RewindBox (adapt_session_retention): also the session's statistics and Horizon, to name what is still held.
        private static readonly List<(WeakReference Device, WeakReference Gpu, WeakReference Statistics, WeakReference System)> _releasedSessions = new();''')
    once(library, '''                _releasedSessions.Add((device, gpu));''',
         '''                _releasedSessions.Add((device, gpu, new WeakReference(context.Statistics), new WeakReference(context.System)));''')
    once(library, '''            int tracked, devices = 0, gpus = 0;''',
         '''            int tracked, devices = 0, gpus = 0, statistics = 0, systems = 0, staticReferences = 0;''')
    once(library, '''                    gpus += gpu ? 1 : 0;
''', '''                    gpus += gpu ? 1 : 0;
                    // RewindBox (adapt_session_retention): what of the closed session is still held, read after the counts.
                    statistics += _releasedSessions[i].Statistics.IsAlive ? 1 : 0;
                    systems += _releasedSessions[i].System.IsAlive ? 1 : 0;
                    if (_releasedSessions[i].Device.Target is Ryujinx.HLE.Switch closed)
                    {
                        staticReferences += Ryujinx.HLE.HOS.Services.Time.SessionRootDiagnostics.StaticReferencesTo(closed);
                    }
''')
    once(library, '''                $"binder registry entries {''', '''                $"PerformanceStatistics still reachable {statistics}/{tracked}; Horizon still reachable {systems}/{tracked}; " +
                $"time service and Bluetooth references to closed sessions {staticReferences}; " +
                $"binder registry entries {''')
    return list(paths.values())
