"""Online play on Nextendo Network for the embedded Switch engine.

Nextendo Network (https://nextendo.network) is a community-run replacement for the Switch online services. Its
integration guide for emulators and client apps (https://wiki.nextendo.network/developers/integration, 15 November
2026) describes what a registered third-party client does; this adapter implements the engine's part on the pinned
engine, in RewindBox's own code. Nextendo's client and servers are published under the PolyForm Shield License 1.0.0:
none of that code is copied or adapted here.

The host (Dart, then Swift) signs the player in with OAuth 2.0 PKCE, asks Nextendo for the game token of the launch
(GET /api/nex-token, scope game.matchmaking) and sends the engine one request before the session is prepared (content
operation 11, EmbeddedOnline.Configure): the game token, the account's PID and the two server addresses. With no
request, or an empty one, every edit below is inert and the engine behaves as before.

Edits, each guarded by EmbeddedOnline.Enabled:

  HleConfiguration.cs                  the guest is told it has Internet access (DNS answers, nifm requests and the
                                       network clock task read EnableInternetAccess) while online play is configured;
                                       RewindBox's sessions set it off, as before, otherwise.
  EmbeddedContent.cs (prepared copy)   operation 11 applies the host's request and answers the protocol name;
                                       operation 12 makes a loaded engine read the profile file again after
                                       RewindBox's profile screen changed it.
  DnsBlacklist.cs                      a host name online play redirects is no longer refused as a Nintendo server.
  DnsMitmResolver.cs                   documented resolution order: an exact hosts-file entry, then the built-in rules
                                       (EmbeddedOnline.Redirect), then the hosts file's wildcards and the real DNS.
                                       nsd's FQDN rewrite (accounts.nintendo.com to the BAAS host) is upstream's.
  ManagerServer.cs                     the network service account id the game reads is the PID (the guide's NSA);
                                       the id_token carries jti, hm, tv (installed game version) and nnex (the game
                                       token). It is signed with this process's throwaway key: Nextendo gives its own
                                       key to its builds only, so a title that checks the signature itself (Splatoon 2)
                                       refuses it, as the guide says of third-party builds.
  SslManagedSocketConnection.cs        TLS to one of the two configured addresses: ALPN http/1.1 (h2 on NPLN hosts),
                                       the name last redirected there as SNI when the game gave none, and a chain to
                                       one of Nextendo's published roots naming the host. Explicit SSBU consent allows
                                       its legacy private certificate only on that session's game address and NEX ports;
                                       all other connections keep their existing validation.

Known limits: Animal Crossing's BAAS user id, signed NPLN patches, BCAT data, the signed game catalog and the
/api/nex-session heartbeat are not handled; nothing keeps a UDP NAT mapping alive during peer-to-peer set-up. Not
run on an iPhone.

Wiring (for the Core that takes it): this file goes to build-utils/melonx/, EmbeddedOnline.cs to native/melonx/ (mapped
to Ryujinx.HLE); the adapter runs last in prepare_embedded.py and ORDER (build-utils/melonx/online/wiring.patch).
Fail closed on drift: every file is pinned to the bytes the earlier steps of the 030cc14f preparation leave.
"""
import hashlib
from pathlib import Path

CONFIGURATION = 'src/Ryujinx.HLE/HleConfiguration.cs'
MANAGER = 'src/Ryujinx.HLE/HOS/Services/Account/Acc/AccountService/ManagerServer.cs'
RESOLVER = 'src/Ryujinx.HLE/HOS/Services/Sockets/Sfdnsres/Proxy/DnsMitmResolver.cs'
BLACKLIST = 'src/Ryujinx.HLE/HOS/Services/Sockets/Sfdnsres/Proxy/DnsBlacklist.cs'
TLS = 'src/Ryujinx.HLE/HOS/Services/Ssl/SslService/SslManagedSocketConnection.cs'
CONTENT = 'src/Ryujinx.Library/EmbeddedContent.cs'
ONLINE = 'src/Ryujinx.HLE/EmbeddedOnline.cs'

# The preparation of Core 030cc14f (contract 1362352a): pristine upstream 13700519 for the five engine files, the
# prepared copy of EmbeddedContent.cs.
BASELINE = {
    CONFIGURATION: '070d81f5d3edff00882bf21c9f8871efc191ca121b483a6508a7ea8fc2d81dc8',
    MANAGER: 'c6f291615bb4405f32830d7e10b4e2cb2c7c80f4c5e6c552950b466ea9a7e5e8',
    RESOLVER: '2c1067fc1f4c3b2201da2f197837e725cb9df3755b1de75c13dc62533b41b181',
    BLACKLIST: '6fab29932fc6cb23c2877ea7acff6267239564d76ad09682755bca3c5c223a68',
    TLS: '77d196aead689c16cd1d1c91b425db07ac5454fe9d2f4845f1d13cae358743f6',
    CONTENT: '496cdc23b439d3c46b3f5ccac1b658b7360573cd3a5a000ca8d99f0fffc414bc',
}

CONFIGURATION_OLD = '''        public bool EnableInternetAccess { internal get; set; }
'''
CONFIGURATION_NEW = '''        // RewindBox (adapt_nextendo_online): also on while the host configured this launch for online play.
        public bool EnableInternetAccess { internal get => _enableInternetAccess || EmbeddedOnline.Enabled; set => _enableInternetAccess = value; }

        private bool _enableInternetAccess;
'''
CONFIGURATION_SESSION_OLD = '''            UserChannelPersistence = userChannelPersistence;
'''
CONFIGURATION_SESSION_NEW = '''            UserChannelPersistence = userChannelPersistence;
            // RewindBox (adapt_nextendo_online): the first program of a host session takes the host's last online request;
            // a program the game starts in the same session (ExecuteProgram, a restart) keeps the session's.
            EmbeddedOnline.BeginSession(userChannelPersistence == null || userChannelPersistence.PreviousIndex == -1);
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
                                bool online;
                                try { online = Ryujinx.HLE.EmbeddedOnline.Configure(path); }
                                catch (JsonException) { throw new FormatException("Online configuration is not valid JSON."); }
                                json.WriteBoolean("online", online);
                                json.WriteString("protocol", Ryujinx.HLE.EmbeddedOnline.Protocol);
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
            if (Ryujinx.HLE.EmbeddedOnline.ShouldRedirect(host))
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
            // first (compared without case, as the loop below does), then the built-in rules; the hosts file's wildcards
            // and the real DNS follow as before.
            bool exactHostsEntry = false;
            foreach (string entry in _mitmHostEntries.Keys)
            {
                if (entry.IndexOfAny(['*', '?']) < 0 && string.Equals(entry, host, StringComparison.OrdinalIgnoreCase))
                {
                    exactHostsEntry = true;
                }
            }

            if (Ryujinx.HLE.EmbeddedOnline.Enabled && !exactHostsEntry)
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

MANAGER_ID_OLD = '''        private long NetworkServiceAccountId => _userId == default ? DefaultNetworkServiceAccountId : DefaultNetworkServiceAccountId + _userId.High;
'''
MANAGER_ID_NEW = '''        // RewindBox (adapt_nextendo_online): online, the account id the game reads is the Nextendo PID.
        private long NetworkServiceAccountId => Ryujinx.HLE.EmbeddedOnline.AccountId(_userId == default ? DefaultNetworkServiceAccountId : DefaultNetworkServiceAccountId + _userId.High);
'''
MANAGER_SIGNATURE_OLD = '''        private static string GenerateIdToken()
        {
'''
MANAGER_SIGNATURE_NEW = '''        private static string GenerateIdToken(string titleVersion)
        {
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
MANAGER_CALL_NEW = '''                _cachedTokenData = Encoding.ASCII.GetBytes(GenerateIdToken(Ryujinx.HLE.EmbeddedOnline.Enabled ? context.Device.Processes.ActiveApplication.DisplayVersion : null));
'''

TLS_OLD = '''            StartSslOperation();
            _stream = new SslStream(new NetworkStream(((DefaultSocket)((ManagedSocket)Socket).Socket).BaseSocket, false), false, null, null);
            hostName = RetrieveHostName(hostName);
            _stream.AuthenticateAsClient(hostName, null, TranslateSslVersion(_sslVersion), false);
            EndSslOperation();

            return ResultCode.Success;
'''
TLS_NEW = '''            StartSslOperation();

            // RewindBox (adapt_nextendo_online): one of the two servers online play is configured with. ALPN http/1.1
            // (NEX over WebSocket; h2 on NPLN hosts), the name last redirected to that address as SNI when the game gave
            // none (a reverse lookup would name the server, not the game's host), and the scoped certificate policy.
            // The default requires Nextendo's published roots and the host name; SSBU's explicit private-certificate
            // consent is bound to this session and destination. A refused or failed handshake is the game's connection
            // error, never an exception through the service (only the host name is logged). Every other connection
            // takes the original handshake below.
            IPAddress onlinePeer = Socket.RemoteEndPoint?.Address;

            if (Ryujinx.HLE.EmbeddedOnline.IsServer(onlinePeer))
            {
                string onlineHost = string.IsNullOrEmpty(hostName) ? Ryujinx.HLE.EmbeddedOnline.HostFor(onlinePeer) : hostName;
                _onlineJournal = Ryujinx.HLE.EmbeddedOnline.TransportJournal(onlineHost, Socket.RemoteEndPoint.Port);
                _onlineJournal("begin", "handshake");

                try
                {
                    if (string.IsNullOrEmpty(onlineHost))
                    {
                        _onlineJournal("failed", "handshake; missing-host");
                        Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.ServiceSsl, "Online play: no host name for a TLS connection to a configured server.");

                        return ResultCode.ConnectionAbort;
                    }

                    SslClientAuthenticationOptions onlineOptions = new()
                    {
                        TargetHost = onlineHost,
                        EnabledSslProtocols = TranslateSslVersion(_sslVersion),
                        ApplicationProtocols = Ryujinx.HLE.EmbeddedOnline.ApplicationProtocols(onlineHost),
                        CertificateRevocationCheckMode = System.Security.Cryptography.X509Certificates.X509RevocationMode.NoCheck,
                        RemoteCertificateValidationCallback = Ryujinx.HLE.EmbeddedOnline.CertificateValidator(onlinePeer, Socket.RemoteEndPoint.Port),
                    };
                    _stream = new SslStream(new NetworkStream(((DefaultSocket)((ManagedSocket)Socket).Socket).BaseSocket, false), false);
                    _stream.AuthenticateAsClient(onlineOptions);
                    _onlineRead = new Ryujinx.HLE.EmbeddedOnline.TlsReadBuffer(_stream, _onlineJournal);
                    _onlineJournal("ready", "handshake-completed");

                    return ResultCode.Success;
                }
                catch (Exception error) when (error is AuthenticationException or IOException or SocketException or ObjectDisposedException)
                {
                    _onlineJournal("failed", "handshake; result=" + Ryujinx.HLE.EmbeddedOnline.TransportError(error));
                    Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.ServiceSsl, $"Online play: TLS to '{onlineHost}' failed ({error.GetType().Name}).");
                    _stream?.Dispose();
                    _stream = null;

                    return Ryujinx.HLE.EmbeddedOnline.TransportError(error);
                }
                finally
                {
                    EndSslOperation();
                }
            }

            try
            {
                _stream = new SslStream(new NetworkStream(((DefaultSocket)((ManagedSocket)Socket).Socket).BaseSocket, false), false, null, null);
                hostName = RetrieveHostName(hostName);
                _stream.AuthenticateAsClient(hostName, null, TranslateSslVersion(_sslVersion), false);
            }
            catch (Exception error) when (Ryujinx.HLE.EmbeddedOnline.Enabled && error is AuthenticationException or IOException or ObjectDisposedException)
            {
                // RewindBox (adapt_nextendo_online): while online play opens the guest's DNS, a failed handshake to any
                // other host is the game's connection error too; offline, the exception goes through as before.
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.ServiceSsl, $"Online play: TLS to '{hostName}' failed ({error.GetType().Name}).");
                _stream?.Dispose();
                _stream = null;
                EndSslOperation();

                return ResultCode.ConnectionAbort;
            }

            EndSslOperation();

            return ResultCode.Success;
'''

STREAM_GUARDS = (
    ('''        private SslStream _stream;
''', '''        private SslStream _stream;
        private Ryujinx.HLE.EmbeddedOnline.TlsReadBuffer _onlineRead;
        private Action<string, string> _onlineJournal;
'''),
    ('''        public ResultCode Read(out int readCount, Memory<byte> buffer)
        {
''', '''        public ResultCode Read(out int readCount, Memory<byte> buffer)
        {
            if (_onlineRead != null) return _onlineRead.Read(out readCount, buffer);
            // RewindBox (adapt_nextendo_online): no stream after a refused handshake while online.
            if (_stream == null && Ryujinx.HLE.EmbeddedOnline.Enabled)
            {
                readCount = -1;

                return ResultCode.ConnectionAbort;
            }

'''),
    ('''        public ResultCode Write(out int writtenCount, ReadOnlyMemory<byte> buffer)
        {
''', '''        public ResultCode Write(out int writtenCount, ReadOnlyMemory<byte> buffer)
        {
            // RewindBox (adapt_nextendo_online): no stream after a refused handshake while online.
            if (_stream == null && Ryujinx.HLE.EmbeddedOnline.Enabled)
            {
                writtenCount = 0;

                return ResultCode.ConnectionAbort;
            }

'''),
    ('''        public ResultCode GetServerCertificate(string hostname, Span<byte> certificates, out uint storageSize, out uint certificateCount)
        {
''', '''        public ResultCode GetServerCertificate(string hostname, Span<byte> certificates, out uint storageSize, out uint certificateCount)
        {
            // RewindBox (adapt_nextendo_online): no stream after a refused handshake while online.
            if (_stream == null && Ryujinx.HLE.EmbeddedOnline.Enabled)
            {
                storageSize = 0;
                certificateCount = 0;

                return ResultCode.ConnectionAbort;
            }

'''),
    ('''        public ResultCode Peek(out int peekCount, Memory<byte> buffer)
        {
''', '''        public ResultCode Peek(out int peekCount, Memory<byte> buffer)
        {
            if (_onlineRead != null) return _onlineRead.Read(out peekCount, buffer, peek: true);
'''),
    ('''        public int Pending()
        {
''', '''        public int Pending()
        {
            if (_onlineRead != null) return _onlineRead.Pending();
'''),
    ('''                _stream.Write(buffer.Span);
            }
            catch (IOException exception)
''', '''                _stream.Write(buffer.Span);
                _onlineRead?.Written(buffer.Length);
            }
            catch (Exception error) when (_onlineRead != null && error is IOException or SocketException or AuthenticationException or ObjectDisposedException)
            {
                writtenCount = -1;
                ResultCode result = Ryujinx.HLE.EmbeddedOnline.TransportError(error);
                _onlineJournal("failed", "write; result=" + result);
                return result;
            }
            catch (IOException exception)
'''),
    ('''        public void Dispose()
        {
            _bsdContext.CloseFileDescriptor(SocketFd);
        }
''', '''        public void Dispose()
        {
            try { _onlineRead?.Dispose(); }
            finally { _bsdContext.CloseFileDescriptor(SocketFd); }
        }
'''),
)

EDITS = (
    (CONFIGURATION, CONFIGURATION_OLD, CONFIGURATION_NEW),
    (CONFIGURATION, CONFIGURATION_SESSION_OLD, CONFIGURATION_SESSION_NEW),
    (CONTENT, CONTENT_NOTE_OLD, CONTENT_NOTE_NEW),
    (CONTENT, CONTENT_CASE_OLD, CONTENT_CASE_NEW),
    (BLACKLIST, BLACKLIST_OLD, BLACKLIST_NEW),
    (RESOLVER, RESOLVER_OLD, RESOLVER_NEW),
    (MANAGER, MANAGER_ID_OLD, MANAGER_ID_NEW),
    (MANAGER, MANAGER_SIGNATURE_OLD, MANAGER_SIGNATURE_NEW),
    (MANAGER, MANAGER_CLAIMS_OLD, MANAGER_CLAIMS_NEW),
    (MANAGER, MANAGER_CALL_OLD, MANAGER_CALL_NEW),
    (TLS, TLS_OLD, TLS_NEW),
    *((TLS, old, new) for old, new in STREAM_GUARDS),
)


def once(path: Path, old: str, new: str):
    text = path.read_text(encoding='utf-8-sig')
    assert text.count(old) == 1, (str(path), old[:90], text.count(old))
    path.write_text(text.replace(old, new), encoding='utf-8')


def apply(source):
    """Edits the prepared tree; EmbeddedOnline.cs is copied there with the native files (prepare_embedded)."""
    source = Path(source)
    for name, expected in BASELINE.items():
        actual = hashlib.sha256((source / name).read_bytes()).hexdigest()
        assert actual == expected, 'Preparation drift, refusing to adapt: ' + name
    for name, old, new in EDITS:
        once(source / name, old, new)
    return [source / name for name in BASELINE]


if __name__ == '__main__':
    import sys
    for path in apply(sys.argv[1]):
        print(path)
