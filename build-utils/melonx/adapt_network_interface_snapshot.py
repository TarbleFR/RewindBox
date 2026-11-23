"""The network services stop throwing two exceptions per host interface at every nifm call (every title): one
enumeration of the host's interfaces serves 5 s, and without /etc/resolv.conf the local-interface search, whose answer
is then known, makes none.

Evidence (private journals of IPA 822, Hogwarts Legacy; counts only): the Vulkan detail lines count the process's
first-chance exceptions per window: 408 in the window that ends 21.7 s into the session (the first: FileNotFoundException
"Could not find file '/etc/resolv.conf'" thrown by Interop.ThrowExceptionForIoErrno) and 410 in the next 5 s (with the
SocketExceptions of two SetSocketOption calls), none in the 14 other windows: the moments the game went online (sfdnsres
resolved its two hosts, nifm requests were made).
Read in the runtime (dotnet/runtime v10.0.0, System.Net.NetworkInformation): on iOS and macOS NetworkInterface.
GetAllNetworkInterfaces builds a BsdNetworkInterface per interface, whose BsdIpInterfaceProperties (UnixIPInterface
Properties, globalConfig false) reads /etc/resolv.conf twice (DNS suffix, DNS addresses), each read throwing and catching
FileNotFoundException where the file does not exist (the iOS sandbox). GetIsNetworkAvailable enumerates the same way
(NetworkInterfacePal.Bsd). Read in the Core: nifm's GetLocalInterface (IGeneralService) calls GetIsNetworkAvailable, then
NetworkHelpers.GetLocalInterface, which enumerates twice more; GetInternetConnectionStatus enumerates once. The search
keeps an interface only if it has a gateway AND a DNS address (or is the one the configuration names): with no
/etc/resolv.conf no interface has a DNS address, so the answer is "none" (NoInternetConnection for the IP address
commands, as today), and IGeneralService caches only an answer that is not "none": every call enumerated again.

Change (NetworkHelpers.cs and IGeneralService.cs; every title):
- NetworkHelpers.GetAllNetworkInterfaces: the runtime's enumeration, kept for 5 s (SnapshotMilliseconds) and returned to
  every caller in that time (its objects are the runtime's own snapshot of each interface anyway: status, addresses and
  DNS are read when an enumeration builds them).
- NetworkHelpers.GetIsNetworkAvailable: outside Windows the runtime's own loop (NetworkInterfacePal.Bsd and .Linux: an
  interface that is neither loopback nor tunnel and is up) over that enumeration; on Windows the runtime's call.
- NetworkHelpers.GetLocalInterface: when no interface is named (MultiplayerLanInterfaceId "0") and /etc/resolv.conf does
  not exist (File.Exists: no exception), returns "none" at once, the answer the search gives then; otherwise it searches
  as before, over the 5 s enumeration.
- IGeneralService: its two GetIsNetworkAvailable calls use NetworkHelpers'.
The answers are the ones of a fresh enumeration made up to 5 s earlier: a network that changes is seen up to 5 s later
by nifm (its own cache already keeps an interface until the runtime's address-change event, adapt_nifm_network_watch).
DNS resolution (sfdnsres), sockets, TLS and the Nextendo online paths (adapt_nextendo_online, adapt_nextendo_data) are
not touched: they never enumerate interfaces. Not changed either: the BSD service's EBADF and EOPNOTSUPP results (an
EBADF costs one asynchronous warning line, no exception; an EOPNOTSUPP from SetSocketOption one SocketException, three
in the session: not worth a change).

Expected on the device (same route): the Vulkan detail lines' "exceptions" count of the windows where the game goes
online at most 2 x (interfaces of the device) per 5 s of nifm polling, none from the IP address commands (IPA 822: 408
and 410); identical nifm behaviour (the same stubs and results in the stderr lines). Refuted if online play behaves
differently. Not measured on an iPhone. Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on
drift: each file must be the Core 827 preparation's.
"""
import hashlib
from adapt_session import once

HELPERS = 'src/Ryujinx.Common/Utilities/NetworkHelpers.cs'
GENERAL = 'src/Ryujinx.HLE/HOS/Services/Nifm/StaticService/IGeneralService.cs'
# The Core 827 preparation: NetworkHelpers.cs is upstream's, IGeneralService.cs after adapt_nifm_network_watch.
BASELINE = {
    HELPERS: '1260bc2851107eef8459669c93354b25da12cc88ee1d077b8d6d7675708ee09d',
    GENERAL: '28bf8f6322168dea7fe373fbeb3107ba98f444b0ab17f0730d28e732cfe3d792',
}

USINGS_OLD = '''using System.Buffers.Binary;
using System.Net;
'''
USINGS_NEW = '''using System;
using System.Buffers.Binary;
using System.IO;
using System.Net;
'''

SEARCH_OLD = '''        public static (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(string lanInterfaceId = "0")
        {
            if (!NetworkInterface.GetIsNetworkAvailable())
            {
                return (null, null);
            }

            IPInterfaceProperties targetProperties = null;
            UnicastIPAddressInformation targetAddressInfo = null;

            NetworkInterface[] interfaces = NetworkInterface.GetAllNetworkInterfaces();

            string guid = lanInterfaceId;
            bool hasPreference = guid != "0";
'''
SEARCH_NEW = '''        // RewindBox (adapt_network_interface_snapshot) begin
        // An enumeration of the host's interfaces reads /etc/resolv.conf twice per interface on iOS and macOS (the runtime's
        // UnixIPInterfaceProperties), each read throwing and catching FileNotFoundException where the file does not exist
        // (IPA 822, Hogwarts Legacy going online: 408 and 410 first-chance exceptions in two windows). One enumeration
        // serves SnapshotMilliseconds; its objects are the runtime's snapshot of each interface anyway.
        public const long SnapshotMilliseconds = 5000;
        private const string ResolverConfiguration = "/etc/resolv.conf";
        private static readonly object _snapshotLock = new();
        private static NetworkInterface[] _snapshot;
        private static long _snapshotAt;
        private static long _enumerations;

        public static long Enumerations => System.Threading.Interlocked.Read(ref _enumerations);

        public static NetworkInterface[] GetAllNetworkInterfaces()
        {
            lock (_snapshotLock)
            {
                long now = Environment.TickCount64;

                if (_snapshot == null || now - _snapshotAt >= SnapshotMilliseconds)
                {
                    _snapshot = NetworkInterface.GetAllNetworkInterfaces();
                    _snapshotAt = now;
                    System.Threading.Interlocked.Increment(ref _enumerations);
                }

                return _snapshot;
            }
        }

        // The runtime's NetworkInterface.GetIsNetworkAvailable outside Windows (NetworkInterfacePal.Bsd and .Linux): an
        // interface that is neither loopback nor tunnel is up. On Windows, the runtime's own call.
        public static bool GetIsNetworkAvailable()
        {
            if (OperatingSystem.IsWindows())
            {
                return NetworkInterface.GetIsNetworkAvailable();
            }

            foreach (NetworkInterface adapter in GetAllNetworkInterfaces())
            {
                if (adapter.NetworkInterfaceType == NetworkInterfaceType.Loopback || adapter.NetworkInterfaceType == NetworkInterfaceType.Tunnel)
                {
                    continue;
                }

                if (adapter.OperationalStatus == OperationalStatus.Up)
                {
                    return true;
                }
            }

            return false;
        }
        // RewindBox (adapt_network_interface_snapshot) end

        public static (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(string lanInterfaceId = "0")
        {
            // RewindBox (adapt_network_interface_snapshot): with no interface named and no /etc/resolv.conf no interface has
            // a DNS address, so the search below keeps none: its answer, without enumerating (File.Exists throws nothing).
            if (lanInterfaceId == "0" && !OperatingSystem.IsWindows() && !File.Exists(ResolverConfiguration))
            {
                return (null, null);
            }

            if (!GetIsNetworkAvailable())
            {
                return (null, null);
            }

            IPInterfaceProperties targetProperties = null;
            UnicastIPAddressInformation targetAddressInfo = null;

            NetworkInterface[] interfaces = GetAllNetworkInterfaces();

            string guid = lanInterfaceId;
            bool hasPreference = guid != "0";
'''

STATUS_OLD = '''        public ResultCode GetInternetConnectionStatus(ServiceCtx context)
        {
            if (!NetworkInterface.GetIsNetworkAvailable())
'''
STATUS_NEW = '''        public ResultCode GetInternetConnectionStatus(ServiceCtx context)
        {
            // RewindBox (adapt_network_interface_snapshot): over the 5 s enumeration.
            if (!NetworkHelpers.GetIsNetworkAvailable())
'''

LOCAL_OLD = '''        private (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(ServiceCtx context)
        {
            if (!NetworkInterface.GetIsNetworkAvailable())
'''
LOCAL_NEW = '''        private (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(ServiceCtx context)
        {
            // RewindBox (adapt_network_interface_snapshot): over the 5 s enumeration.
            if (!NetworkHelpers.GetIsNetworkAvailable())
'''

FILE_PAIRS = {
    HELPERS: ((USINGS_OLD, USINGS_NEW), (SEARCH_OLD, SEARCH_NEW)),
    GENERAL: ((STATUS_OLD, STATUS_NEW), (LOCAL_OLD, LOCAL_NEW)),
}


def apply(source):
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter or a gate records the pairs
    for name, expected in digests:
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(source / name, old, new)
    return [source / name for name in FILE_PAIRS]
