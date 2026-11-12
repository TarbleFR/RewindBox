"""A closed session no longer stays reachable through the process-wide network address event (next Core candidate).

IPA 729 / Core 743, Hogwarts Legacy then Super Smash Bros. Ultimate in one process (pid 58475): after each close and
its final collections the Switch, GpuContext, Horizon, kernel, renderer, audio driver, window, input managers, the
application's CPU memory and the eleven ServerBase service processes are still reachable (sessionRetention and
retentionChain lines: 1/1 after Hogwarts, the same six full collections later at Smash's first frame, 2/2 after
Smash). Smash's first-frame compaction keeps 484 MiB of gen2 and 468 MiB of LOH against Hogwarts' 104 and 266.

Cause read in the source: nifm's IGeneralService subscribes an instance method to
System.Net.NetworkInformation.NetworkChange.NetworkAddressChanged, a static event of the runtime, and unsubscribes
only in its Dispose. The object holds its ServerBase (IpcService.Server), which holds the KernelContext, which holds
the Switch. ServerBase.DestroySession (the guest closed the session) disposes the session's root object only: a
general service created inside a domain is never disposed when the guest closes that session without deleting each
object first, and the runtime's static event then keeps it, and through it the whole session, until the process
ends. It is the only subscription of a session object to a process-wide event in the engine.

Change (IGeneralService.cs): no object subscribes any more. One static handler, subscribed once per process, counts
the address changes (NetworkAddressWatch.Version); a general service remembers the count its cache was filled at and
empties the cache when the count has moved, at the only place the cache is read (GetLocalInterface). The control
emptied the cache from the event's thread, the candidate at the next read: the same values are returned, since nothing
else reads the two cached fields. The static handler holds no object. Creations and disposals are counted for the
sessionRetention journal line (Library.cs: "Nifm general services created C, disposed D"): after a close, C - D above
zero with the Switch released names this path as the one that held the session.

Not changed: DestroySession still disposes the root object only (a cloned session shares its root, so disposing the
domain's objects there needs per-handle counts); GeneralServiceManager's list.
Rollback: drop this adapter from prepare_embedded.py and the plan. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

SERVICE = 'src/Ryujinx.HLE/HOS/Services/Nifm/StaticService/IGeneralService.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
BASELINE = {
    SERVICE: '8cf2c08cb6046676d9acef024d58f5e835cb46c2e4b668c26ad35b0080534327',
    LIBRARY: 'ecb8f4ff1a27479498dc849d6a47a610b7e857c8b19f76c9886f2a05dcf980a1',
}

FIELD_OLD = '''        private string _cacheChosenInterface = null;
'''
FIELD_NEW = '''        private string _cacheChosenInterface = null;
        // RewindBox (adapt_nifm_network_watch): NetworkAddressWatch.Version when the cache above was filled.
        private int _cacheNetworkVersion;
'''

SUBSCRIBE_OLD = '''            NetworkChange.NetworkAddressChanged += LocalInterfaceCacheHandler;
'''
SUBSCRIBE_NEW = '''            // RewindBox (adapt_nifm_network_watch): this object is not subscribed to the runtime's process-wide event: the
            // event kept it, its server, the kernel and so the whole Switch reachable whenever it was not disposed (a
            // session the guest closed disposes its root object only). One static handler counts the changes.
            NetworkAddressWatch.Created();
            _cacheNetworkVersion = NetworkAddressWatch.Version;
'''

READ_OLD = '''            string chosenInterface = context.Device.Configuration.MultiplayerLanInterfaceId;

            if (_targetPropertiesCache == null || _targetAddressInfoCache == null || _cacheChosenInterface != chosenInterface)
'''
READ_NEW = '''            string chosenInterface = context.Device.Configuration.MultiplayerLanInterfaceId;

            // RewindBox (adapt_nifm_network_watch): an address change since the cache was filled empties it, here, where
            // it is read.
            int networkVersion = NetworkAddressWatch.Version;

            if (networkVersion != _cacheNetworkVersion)
            {
                _cacheNetworkVersion = networkVersion;
                _targetPropertiesCache = null;
                _targetAddressInfoCache = null;
            }

            if (_targetPropertiesCache == null || _targetAddressInfoCache == null || _cacheChosenInterface != chosenInterface)
'''

HANDLER_OLD = '''        private void LocalInterfaceCacheHandler(object sender, EventArgs e)
        {
            Logger.Info?.Print(LogClass.ServiceNifm, "NetworkAddress changed, invalidating cached data.");

            _targetPropertiesCache = null;
            _targetAddressInfoCache = null;
        }

        protected override void Dispose(bool isDisposing)
        {
            if (isDisposing)
            {
                NetworkChange.NetworkAddressChanged -= LocalInterfaceCacheHandler;
'''
HANDLER_NEW = '''        protected override void Dispose(bool isDisposing)
        {
            if (isDisposing)
            {
                NetworkAddressWatch.Disposed(); // RewindBox (adapt_nifm_network_watch): counted; nothing to unsubscribe
'''

TAIL_OLD = '''                GeneralServiceManager.Remove(_generalServiceDetail.ClientId);
            }
        }
    }
}
'''
TAIL_NEW = '''                GeneralServiceManager.Remove(_generalServiceDetail.ClientId);
            }
        }
    }

    // RewindBox (adapt_nifm_network_watch): the runtime's process-wide network address event, watched by one static
    // handler subscribed at the first general service of the process and never removed. It holds no object: it counts the
    // changes, and each general service compares the count with the one its cache was filled at.
    static class NetworkAddressWatch
    {
        private static int _subscribed;
        private static int _version;
        private static long _created;
        private static long _disposed;

        // Test seam; production subscribes to the runtime's event.
        internal static Action<NetworkAddressChangedEventHandler> Subscribe =
            static handler => NetworkChange.NetworkAddressChanged += handler;

        public static int Version => System.Threading.Volatile.Read(ref _version);
        public static long CreatedCount => System.Threading.Interlocked.Read(ref _created);
        public static long DisposedCount => System.Threading.Interlocked.Read(ref _disposed);

        public static void Created()
        {
            System.Threading.Interlocked.Increment(ref _created);

            if (System.Threading.Interlocked.CompareExchange(ref _subscribed, 1, 0) == 0)
            {
                try
                {
                    Subscribe(OnAddressChanged);
                }
                catch
                {
                    // As before this change, a runtime that refuses the subscription fails the service's creation; the next
                    // creation tries again.
                    System.Threading.Volatile.Write(ref _subscribed, 0);
                    throw;
                }
            }
        }

        public static void Disposed() => System.Threading.Interlocked.Increment(ref _disposed);

        private static void OnAddressChanged(object sender, EventArgs e)
        {
            System.Threading.Interlocked.Increment(ref _version);
            Logger.Info?.Print(LogClass.ServiceNifm, "NetworkAddress changed, invalidating cached data.");
        }
    }

    // RewindBox (adapt_nifm_network_watch): read-only, for the host's sessionRetention journal line.
    public static class NifmSessionDiagnostics
    {
        public static string Describe() =>
            $"Nifm general services created {NetworkAddressWatch.CreatedCount}, disposed {NetworkAddressWatch.DisposedCount}";
    }
}
'''

JOURNAL_OLD = '''                $"binder registry entries {Ryujinx.HLE.HOS.Services.SurfaceFlinger.BinderRegistryDiagnostics.RegisteredBinderCount}; " +
                $"managed heap {GC.GetTotalMemory(false) / (1024 * 1024)} MB");
'''
JOURNAL_NEW = '''                $"binder registry entries {Ryujinx.HLE.HOS.Services.SurfaceFlinger.BinderRegistryDiagnostics.RegisteredBinderCount}; " +
                // RewindBox (adapt_nifm_network_watch): general services the guest left undisposed (they no longer hold a session).
                $"{Ryujinx.HLE.HOS.Services.Nifm.StaticService.NifmSessionDiagnostics.Describe()}; " +
                $"managed heap {GC.GetTotalMemory(false) / (1024 * 1024)} MB");
'''

SERVICE_PAIRS = ((FIELD_OLD, FIELD_NEW), (SUBSCRIBE_OLD, SUBSCRIBE_NEW), (READ_OLD, READ_NEW), (HANDLER_OLD, HANDLER_NEW),
                 (TAIL_OLD, TAIL_NEW))
LIBRARY_PAIRS = ((JOURNAL_OLD, JOURNAL_NEW),)
PAIRS = SERVICE_PAIRS + LIBRARY_PAIRS


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in SERVICE_PAIRS:
        once(paths[SERVICE], old, new)
    for old, new in LIBRARY_PAIRS:
        once(paths[LIBRARY], old, new)
    return list(paths.values())
