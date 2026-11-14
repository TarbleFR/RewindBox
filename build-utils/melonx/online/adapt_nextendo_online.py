"""Online play on Nextendo Network for the embedded Switch engine (source only: not part of any Core yet).

Nextendo Network (https://nextendo.network) is a community-run replacement for the Switch online services. Its
developer documentation (https://wiki.nextendo.network/developers) describes what a registered third-party emulator
does on the client side; this adapter implements those documented points on the pinned engine, in RewindBox's own
code. Nextendo's client and servers are published under the PolyForm Shield License 1.0.0: none of that code is
copied or adapted here.

The host (Dart, then Swift) signs the player in with OAuth 2.0 PKCE, asks Nextendo for the game token of the launch
(GET /api/nex-token, scope game.matchmaking) and sends the engine one request before the session is prepared
(content operation 11, EmbeddedOnline.Configure): the game token and the two server addresses. With no request, or an
empty one, every edit below is inert and the engine behaves as it does today.

Edits, each guarded by EmbeddedOnline.Enabled:

  EmbeddedSession.cs (prepared copy)   the session has guest network access (EnableInternetAccess) when online play is
                                       configured; it stays off otherwise, as today.
  EmbeddedContent.cs (prepared copy)   operation 11 applies the host's request; operation 12 makes a loaded engine read
                                       the profile file again after RewindBox's profile screen changed it.
  DnsBlacklist.cs                      a host name online play redirects is no longer refused as a Nintendo server.
  DnsMitmResolver.cs                   documented resolution order: an exact hosts-file entry, then the built-in rules
                                       (EmbeddedOnline.Redirect), then the hosts file's wildcards and the real DNS.
  ManagerServer.cs                     the account id_token carries Nextendo's key identifier and the claims jti, hm,
                                       tv (installed game version) and nnex (the game token), as documented. It is
                                       signed with this process's throwaway key: Nextendo gives its signing key to its
                                       own builds only, so a game that checks the signature itself (Splatoon 2) refuses
                                       it; games whose server reads nnex do not.
  SslManagedSocketConnection.cs        a TLS connection to one of the two configured addresses accepts that service's
                                       certificate (it is presented for Nintendo host names); when the game gave no
                                       host name, the name last redirected to that address is the SNI. Every other
                                       connection keeps the system's validation.

Not done, known limits: no ALPN is offered (NEX over WebSocket works without it; NPLN titles need h2 and stay out of
reach); nothing keeps the UDP NAT mapping alive during peer-to-peer set-up; nifm's interface queries have never run on
an iPhone with network access on. Nothing here has been compiled into a Core or run on a device.

Wiring, when a Core takes this lot: move this file to build-utils/melonx/ and EmbeddedOnline.cs to native/melonx/
(prepare_embedded.py then copies it; map it to the Ryujinx.HLE project and drop the copy made in apply() below), call
the adapter last in prepare_embedded.py, add it to ORDER, the plan and the contract, and freeze. Rollback: remove it.
Fail closed on drift: every file is pinned to the preparation bytes it was written against.
"""
import hashlib
from pathlib import Path
import shutil

MANAGER = 'src/Ryujinx.HLE/HOS/Services/Account/Acc/AccountService/ManagerServer.cs'
RESOLVER = 'src/Ryujinx.HLE/HOS/Services/Sockets/Sfdnsres/Proxy/DnsMitmResolver.cs'
BLACKLIST = 'src/Ryujinx.HLE/HOS/Services/Sockets/Sfdnsres/Proxy/DnsBlacklist.cs'
TLS = 'src/Ryujinx.HLE/HOS/Services/Ssl/SslService/SslManagedSocketConnection.cs'
SESSION = 'src/Ryujinx.Library/EmbeddedSession.cs'
CONTENT = 'src/Ryujinx.Library/EmbeddedContent.cs'
ONLINE = 'src/Ryujinx.HLE/EmbeddedOnline.cs'
ONLINE_SOURCE = Path(__file__).resolve().parents[3] / 'native/melonx/online/EmbeddedOnline.cs'

# The preparation of Claude b83935f0 (Core contract 4396d7b0): pristine upstream 13700519 for the four engine files,
# the prepared copies of the two RewindBox files.
BASELINE = {
    MANAGER: 'c6f291615bb4405f32830d7e10b4e2cb2c7c80f4c5e6c552950b466ea9a7e5e8',
    RESOLVER: '2c1067fc1f4c3b2201da2f197837e725cb9df3755b1de75c13dc62533b41b181',
    BLACKLIST: '6fab29932fc6cb23c2877ea7acff6267239564d76ad09682755bca3c5c223a68',
    TLS: '77d196aead689c16cd1d1c91b425db07ac5454fe9d2f4845f1d13cae358743f6',
    SESSION: '80f67552d100c78398ceeaf8a22861e9672347a9b081f08a67c5a67d2430963f',
    CONTENT: '496cdc23b439d3c46b3f5ccac1b658b7360573cd3a5a000ca8d99f0fffc414bc',
}

SESSION_OLD = '''            UseHypervisor = false, EnableInternetAccess = false,
'''
SESSION_NEW = '''            // RewindBox (adapt_nextendo_online): guest network access only for a launch the host configured for
            // online play (content operation 11); off otherwise, as before.
            UseHypervisor = false, EnableInternetAccess = Ryujinx.HLE.EmbeddedOnline.Enabled,
'''

CONTENT_NOTE_OLD = '''    // 8 launch preflight; 9 configure the application-owned diagnostic path.
'''
CONTENT_NOTE_NEW = '''    // 8 launch preflight; 9 configure the application-owned diagnostic path.
    // 11 online play of the next session (adapt_nextendo_online): the request replaces the previous one, an empty
    // object or a refused request leaves the engine offline; 12 read the profile file again.
'''
CONTENT_CASE_OLD = '''                            default: throw new ArgumentOutOfRangeException(nameof(operation));
'''
CONTENT_CASE_NEW = '''                            case 11:
                                // The request holds the game token: nothing of it is echoed or journaled.
                                try { Ryujinx.HLE.EmbeddedOnline.Configure(path); }
                                catch (JsonException) { throw new FormatException("Online configuration is not valid JSON."); }
                                json.WriteBoolean("online", Ryujinx.HLE.EmbeddedOnline.Enabled);
                                break;
                            case 12:
                                _accountManager.Refresh();
                                break;
                            default: throw new ArgumentOutOfRangeException(nameof(operation));
'''

BLACKLIST_OLD = '''        public static bool IsHostBlocked(string host)
        {
'''
BLACKLIST_NEW = '''        public static bool IsHostBlocked(string host)
        {
            // RewindBox (adapt_nextendo_online): a name online play redirects goes to the configured service, not to
            // Nintendo's server; it is resolved by DnsMitmResolver instead of being refused here.
            if (Ryujinx.HLE.EmbeddedOnline.Redirect(host) != null)
            {
                return false;
            }

'''

RESOLVER_OLD = '''        public IPHostEntry ResolveAddress(string host)
        {
'''
RESOLVER_NEW = '''        public IPHostEntry ResolveAddress(string host)
        {
            // RewindBox (adapt_nextendo_online): with online play configured, an exact hosts-file entry still comes
            // first, then the built-in rules; the hosts file's wildcards and the real DNS follow as before.
            if (Ryujinx.HLE.EmbeddedOnline.Enabled && !_mitmHostEntries.ContainsKey(host))
            {
                IPAddress redirected = Ryujinx.HLE.EmbeddedOnline.Redirect(host);

                if (redirected != null)
                {
                    Logger.Info?.PrintMsg(LogClass.ServiceBsd, $"Online play: '{host}' redirected.");

                    return new IPHostEntry
                    {
                        AddressList = [redirected],
                        HostName = host,
                        Aliases = [],
                    };
                }
            }

'''

MANAGER_SIGNATURE_OLD = '''        private static string GenerateIdToken()
        {
'''
MANAGER_SIGNATURE_NEW = '''        private static string GenerateIdToken(string titleVersion)
        {
'''
MANAGER_KEY_OLD = '''            credentials.Key.KeyId = parameters.ToString();
'''
MANAGER_KEY_NEW = '''            // RewindBox (adapt_nextendo_online): the key identifier Nextendo documents, when online play is configured.
            credentials.Key.KeyId = Ryujinx.HLE.EmbeddedOnline.Enabled ? "nextendo-baas-key-1" : parameters.ToString();
'''
MANAGER_CLAIMS_OLD = '''            return new JsonWebTokenHandler().CreateToken(descriptor);
'''
MANAGER_CLAIMS_NEW = '''            // RewindBox (adapt_nextendo_online): jti, hm, tv and nnex (the game token), which the game forwards at its
            // NEX login; nothing is added offline.
            Ryujinx.HLE.EmbeddedOnline.AddClaims(descriptor.Claims, titleVersion);

            return new JsonWebTokenHandler().CreateToken(descriptor);
'''
MANAGER_CALL_OLD = '''                _cachedTokenData = Encoding.ASCII.GetBytes(GenerateIdToken());
'''
MANAGER_CALL_NEW = '''                _cachedTokenData = Encoding.ASCII.GetBytes(GenerateIdToken(context.Device.Processes.ActiveApplication.DisplayVersion));
'''

TLS_OLD = '''            _stream = new SslStream(new NetworkStream(((DefaultSocket)((ManagedSocket)Socket).Socket).BaseSocket, false), false, null, null);
            hostName = RetrieveHostName(hostName);
'''
TLS_NEW = '''            // RewindBox (adapt_nextendo_online): one of the two servers online play is configured with presents that
            // service's own certificate for the game's host name. It is accepted for those two addresses only; every
            // other connection keeps the system's validation. Without a host name from the game, the name last
            // redirected to that address is the SNI (a reverse lookup would name the server, not the game's host).
            IPAddress onlinePeer = Socket.RemoteEndPoint?.Address;
            bool onlineServer = Ryujinx.HLE.EmbeddedOnline.IsServer(onlinePeer);

            _stream = new SslStream(new NetworkStream(((DefaultSocket)((ManagedSocket)Socket).Socket).BaseSocket, false), false,
                onlineServer ? static (_, _, _, _) => true : null, null);
            hostName = onlineServer && string.IsNullOrEmpty(hostName)
                ? Ryujinx.HLE.EmbeddedOnline.HostFor(onlinePeer) ?? hostName
                : RetrieveHostName(hostName);
'''

EDITS = (
    (SESSION, SESSION_OLD, SESSION_NEW),
    (CONTENT, CONTENT_NOTE_OLD, CONTENT_NOTE_NEW),
    (CONTENT, CONTENT_CASE_OLD, CONTENT_CASE_NEW),
    (BLACKLIST, BLACKLIST_OLD, BLACKLIST_NEW),
    (RESOLVER, RESOLVER_OLD, RESOLVER_NEW),
    (MANAGER, MANAGER_SIGNATURE_OLD, MANAGER_SIGNATURE_NEW),
    (MANAGER, MANAGER_KEY_OLD, MANAGER_KEY_NEW),
    (MANAGER, MANAGER_CLAIMS_OLD, MANAGER_CLAIMS_NEW),
    (MANAGER, MANAGER_CALL_OLD, MANAGER_CALL_NEW),
    (TLS, TLS_OLD, TLS_NEW),
)


def once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, (str(path), old[:90], text.count(old))
    path.write_text(text.replace(old, new), encoding='utf-8')


def apply(source):
    source = Path(source)
    for name, expected in BASELINE.items():
        actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
        assert actual == expected, 'Preparation drift, refusing to adapt: ' + name
    assert not (source / ONLINE).exists(), 'EmbeddedOnline.cs is already in the tree'
    for name, old, new in EDITS:
        once(source / name, old, new)
    shutil.copyfile(ONLINE_SOURCE, source / ONLINE)
    return [source / name for name in (*BASELINE, ONLINE)]


if __name__ == '__main__':
    import sys
    for path in apply(sys.argv[1]):
        print(path)
