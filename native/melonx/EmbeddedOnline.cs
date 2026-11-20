using Ryujinx.Common.Logging;
using System;
using System.Collections.Generic;
using System.IO;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Threading;
using System.Threading.Tasks;
using System.Security.Cryptography;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;

namespace Ryujinx.HLE
{
    /// <summary>
    /// Online play of one session on Nextendo Network (https://nextendo.network), as its integration guide for emulators
    /// and client apps describes the client side (https://wiki.nextendo.network/developers/integration, 15 November
    /// 2026). RewindBox's own code: no Nextendo source is used.
    ///
    /// The host signs the player in (OAuth 2.0 PKCE), asks Nextendo for the game token of the launch (nx2, 24 hours,
    /// scope game.matchmaking) and hands this class, before the session is prepared (content operation 11), that token,
    /// the account's PID and the two server addresses. The request belongs to the next session only: the configuration
    /// of the session's first program takes it (BeginSession), programs the game starts in the same session keep it,
    /// and a later session without a request is offline. RewindBox sends a request before every launch (an empty one
    /// offline), so a request left by a launch that never started is replaced before the next session takes it.
    /// While a session has it:
    ///   - the guest is told it has Internet access (DNS, nifm requests);
    ///   - the documented Nintendo and third-party host names resolve to the two addresses;
    ///   - the account id the game reads is the PID, and the BAAS id_token carries jti, hm, tv (installed version) and
    ///     nnex (the game token);
    ///   - TLS to one of the two addresses offers ALPN http/1.1 (h2 on NPLN hosts), sends the last host name redirected
    ///     there as SNI when the game gave none, and accepts only a chain to one of Nextendo's published roots that
    ///     names the host. An explicitly consented SSBU session may instead accept the legacy private NEX certificate
    ///     on its configured game address; this is reported as unverified compatibility, never verified TLS;
    ///   - a refused or failed TLS handshake, to those addresses or any other host, is the game's connection error
    ///     (ConnectionAbort, also for a later read or write), never an exception through the service.
    /// RewindBox (adapt_nextendo_data), optional parts of the request: the host's folder of the launched title's BCAT data
    /// (bcatDirectory), served as its delivery cache while the session plays online (EmbeddedDeliveryCache, Horizon); the
    /// account's BAAS user id (nsa, Animal Crossing: New Horizons), then the account id the game reads instead of the PID;
    /// and the versions Nextendo's signed game catalog accepts for the title (acceptedVersions), journaled with the
    /// installed one when the game first asks for its id_token. A malformed optional part is left out (journaled); it
    /// never makes the session offline.
    /// Without a configuration (the default) nothing above applies. The game token is kept in memory only: it is never
    /// logged and never written to a file.
    /// </summary>
    public static class EmbeddedOnline
    {
        /// <summary>Answered by the content request; the host also finds this text in the engine binary.</summary>
        public const string Protocol = "rewindbox-nextendo-online-1";

        public const int MaxTokenLength = 1024;

        private sealed class Settings
        {
            public string NexToken;
            public long Pid;
            public IPAddress Server;
            public IPAddress Nat;
            public IPAddress[] SmashCandidates;
            public Task<IPAddress> SmashSelection;
            public volatile IPAddress SmashServer;
            public int SmashTlsState;
            public int TransportSequence;
            public bool SmashPrivateTls;
            public readonly Dictionary<IPAddress, string> Resolved = new();
            public string BcatDirectory; // adapt_nextendo_data
            public long? Nsa; // adapt_nextendo_data
            public string[] AcceptedVersions; // adapt_nextendo_data
            public int BcatFiles = -1; // adapt_nextendo_data: files served at the session's start, -1 none
            public int Journaled; // adapt_nextendo_data: the session's line is written once
        }

        public const int MaxAcceptedVersions = 16; // adapt_nextendo_data
        public const int MaxVersionLength = 32; // adapt_nextendo_data

        private const string SmashHost = "g23380901-lp1.s.n.srv.nintendo.net";
        private const string SmashTitle = "01006a800016e000";

        private static volatile Settings _settings; // the running session's
        private static volatile Settings _pending; // the host's last request, for the next session
        // The documented built-in rules, in their order: the names of the second (NAT test) address first.
        private static readonly string[] _natHosts =
        [
            "nncs2-*.n.n.srv.nintendo.net",
            "g2b309e01-lp1.s.n.srv.nintendo.net",
            "g2df33d01-lp1.p.srv.nintendo.net",
        ];

        private static readonly string[] _serverHosts =
        [
            "*.nintendo.net",
            "*.nintendo.com",
            "*.nintendowifi.net",
            "*.nintendo.co.jp",
            "demonware.net",
            "*.demonware.net",
            "nswitch.f13.illfonic.com",
            "spring18.gosredirector.ea.com",
            "pvzgw3prodapp-*.ea.com",
            "public-ubiservices.ubi.com",
            "public-ws-ubiservices.ubi.com",
            "jd.ubisoft.com",
            "phonescoring.jd.ubisoft.com",
            "v2.phonescoring.jd.ubisoft.com",
            "api.braincloudservers.com",
            "na.ultimatechickenhorseserver.com",
            "eu.ultimatechickenhorseserver.com",
            "ap.ultimatechickenhorseserver.com",
        ];

        private sealed record Root(string Sha256, string Pem);

        // The roots Nextendo publishes for redirected hosts (integration guide, "TLS trust and certificates"), with the
        // SHA-256 fingerprints the guide lists. Public certificates; a chain to one of them is the only one accepted
        // from the two configured servers.
        private static readonly Root[] _roots =
        [
            // nextendo-network-ca.pem (accounts, both BAAS hosts, eShop, NSO and the other Nintendo services, third-party services)
            new("a654c0eff8aa20a72280ea0ef2b5c2a17392922dd78ffbb113862e1ad2c66d49", """
-----BEGIN CERTIFICATE-----
MIIDUzCCAjugAwIBAgIUe2MLLv0r9SUfUu/Y3QCzveSq6eswDQYJKoZIhvcNAQEL
BQAwMTEcMBoGA1UEAwwTTmV4dGVuZG8gTmV0d29yayBDQTERMA8GA1UECgwITmV4
dGVuZG8wHhcNMjYwNjMwMTk0OTM0WhcNMzYwNjI3MTk0OTM0WjAxMRwwGgYDVQQD
DBNOZXh0ZW5kbyBOZXR3b3JrIENBMREwDwYDVQQKDAhOZXh0ZW5kbzCCASIwDQYJ
KoZIhvcNAQEBBQADggEPADCCAQoCggEBAMJWnrQ4xsG7V+y0vmzqT9NVLf8yJhbQ
gpCEYleo2rV6IwCB499spgdzet7pOV64TSa67maF+wqBSfBJ2k0Vy3ceQCTJAFs3
orpWE6GcCIGoj18CSYQgeCm8ih4rNRECTYo/cKlDKeeZ+jL+JKSYc1HngZ78ORie
YZMJ0L2liWrbvoKvvYJ0tbOm7Cth9GWcS3IKGv1IB0Kc+qDAa2mVZ6fv7N2DJEGh
OMgqTebxrkI04VQk5E35fgO83dgrH/nj1Wt4oYRTOJtj5bQCLpKztggmUxYiTNUo
aawGWRKH4nmeBwR7sVM8SVkk77j/FSYFC5ZJRsjgHAmiAAv0lpCBM0sCAwEAAaNj
MGEwHQYDVR0OBBYEFAzPy4p77XJCgBJkQXYZ1WQy63FHMB8GA1UdIwQYMBaAFAzP
y4p77XJCgBJkQXYZ1WQy63FHMA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQD
AgEGMA0GCSqGSIb3DQEBCwUAA4IBAQCKt6g4McjcBCEGysAGf0kREMdA/mpPaaId
NGACL82AnPP7yeS6lFpAhYTB0nYik2etVGyzSym3WumPNCedIcT/9HmvzBdoXXIi
lIzzg3kndbkCrYQgoM6yeV6pPoJY5Xe0iISEUsMZdSJo2CTpL2pnoD4DVmmtz/iK
j/x/8+UbhQmAiVEEgfZAqgiwZ79E1639QKtpeWiX7iDopC+mZJtcmDIak/SX4i3k
xiEuumNCYO+o9cKzFLUqsbxMHdAE6FIBrurc8grhOawAqpRG/gJgc1uZkmkg4tez
ERdWDQSMRaS1/hySxRaKZxh2scmfDlpexIo0hgO5FTxb5tDylvMt
-----END CERTIFICATE-----
"""),
            // nextendo-npln-class2-ca-g3.pem (NPLN games, device authentication, friends)
            new("d76bf8d0d7a1cd81874b20314171de9ecb64864837d684ab689831a72b6c0a01", """
-----BEGIN CERTIFICATE-----
MIIDTTCCAjWgAwIBAgIUE3VUzsBqRzJr4mmR57zFDNFE8QkwDQYJKoZIhvcNAQEL
BQAwNjEhMB8GA1UEAwwYTmludGVuZG8gQ2xhc3MgMiBDQSAtIEczMREwDwYDVQQK
DAhOaW50ZW5kbzAeFw0yNjA2MjgxNDMyNTZaFw0zNjA2MjUxNDMyNTZaMDYxITAf
BgNVBAMMGE5pbnRlbmRvIENsYXNzIDIgQ0EgLSBHMzERMA8GA1UECgwITmludGVu
ZG8wggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDX9qd+gMkWxSW6swys
IoKYpstpveisbdpRo/t8VMcC/Jp2kJtMo7kbYZkNxPQ6i8rnQe+vajWm9eXH7iac
YrRwwKkcxhlRUgHbIxhprOiBKORNv4BMvBPQP2kBeyMVbM4jq15Ym0IdJ/CzvqW2
n0Piievi+060MabftCHph5CRynmh/WUdRYG84z+fVTKqoQlUjbTZVLpWpSFPfQY7
31KEeIlPmm/RsFp8z52hxvmMqZ9PkH3ygc9GghsLFmVjfW041npchn08YvFz7Bcj
tcPLypnjal7q0DR6R0UZeN7A2/OvfhtJxbHC948cEnkzm7XQu0EUKCYuidlO37CU
9xZTAgMBAAGjUzBRMB0GA1UdDgQWBBSDzEjsXmuITcjV0HYchd3/9odp1TAfBgNV
HSMEGDAWgBSDzEjsXmuITcjV0HYchd3/9odp1TAPBgNVHRMBAf8EBTADAQH/MA0G
CSqGSIb3DQEBCwUAA4IBAQBFZeIZGGVae0Q7szj1wB1pgi8cevmMNRQPqt1hAu6W
6IpJobU5Hvt0o046J+3Mcw2ML5ZTbgy9ad0k0dOXmJoahQxQ5pcOzTYV1ljSRBPF
SVwm35fGNFnd3GMW3768VVzTO/VBSUyik2KSTveAfTJv/e6D6GM5Vm+1zbYqUJ08
hzH4wHw3ZWkNAAR5lfRjmQeouIyKzkOZxEvO/874QdSNRu9Hw4KM+5SCTWMo6SPo
sbr0bZDNwV3KaGV1ECxwz7yL5020yfGF0HUOr8PKwoqDSIzV/JOMHjh+bh5CxjlD
Brs/F2G+Pi5J7ye5ZSJ/r3dISgTau1Ig810gPki1OFIF
-----END CERTIFICATE-----
"""),
            // nextendo-jd2022-service-ca.pem (Just Dance 2022)
            new("817d4a822fbbcdcf0a721563f83cec25be9ae8b2ba435d18bc10dfc2135bf064", """
-----BEGIN CERTIFICATE-----
MIIDOzCCAiOgAwIBAgIUNlcViDpZqmfHUngm9Z5y9/Pot/EwDQYJKoZIhvcNAQEL
BQAwJTEjMCEGA1UEAwwaTmV4dGVuZG8gSkQyMDIyIHNlcnZpY2UgQ0EwHhcNMjYx
MDIzMDIwNDIzWhcNMjcxMDMwMDIwNDIzWjAlMSMwIQYDVQQDDBpOZXh0ZW5kbyBK
RDIwMjIgc2VydmljZSBDQTCCASIwDQYJKoZIhvcNAQEBBQADggEPADCCAQoCggEB
AKtLa20mfvxoqIKc/XQc2+tiwbdOAWQzEyAPtf19SoP8/3rGQoNHDeOJKK0Zg9k7
3A5r1E34AH9tTvTZeAYBbzLEdX6sibZIcInmZtoiepAuu8CgDeGnDzd2QUflsGhn
JUa+Ev32h2cpYVlZ6EAExMRmsUgR2I4rvtH/T0kBf1P2qSmSg7msjL630l58wcg/
dykt/ZT/fDqvIBBSWIVfZBlCsJ/ihtiNJ+NMNhmuyt71Rql7HQRt3mIZdAFEB4KS
V1gk0FQwx2JtOl98GI3mT/F5Mf4gn0c3uvhj+7XctpYiQCB1PJxrwnqeS9TnDFE/
8WeRwNjX42/mnQFVwotzYwECAwEAAaNjMGEwHQYDVR0OBBYEFCsx7n0bpdpA2Bat
YtGdtHW9oJcxMB8GA1UdIwQYMBaAFCsx7n0bpdpA2BatYtGdtHW9oJcxMA8GA1Ud
EwEB/wQFMAMBAf8wDgYDVR0PAQH/BAQDAgEGMA0GCSqGSIb3DQEBCwUAA4IBAQAE
bgItdWKmrx1lMJ9F9n3nXDj1iveDIoNb+3d4cEyy4xT2i1l/CwNWycogh9cT0ON9
y/BHgyi5ac6+fkDgC8mzII8z+zrZYedxl7qXJJglKRQrdJJVFd3Df+ZsWCJwmF9A
IzDfZ/HxNAhhULfOCSKUd9wltcNa97Lxd8xMtD7pvcvpguEYZ0oNAVjvuqc5UCGD
8yQeLtztjeOG0GxwY314Vtmlb/0XMepBp3qKNsl7lxnomZax6Ys5r/WetxUgQD+/
2Ny7nt5UqRZWEC2+KwZ9+bDOQks4NCzYAFuYvJhgyi2tALEI7fyHIxkv2zGUsoBA
q4YNbp50n9pjxlEfUic3
-----END CERTIFICATE-----
"""),
            // nextendo-overcooked2-ca.pem (Overcooked! 2)
            new("8edcf2c39bb5264b905646569d23cdf265bfbf7c993d30accc3d66c6a953bf9d", """
-----BEGIN CERTIFICATE-----
MIIBrDCCAVGgAwIBAgIUDiduHhggWk9Sm4EvgAzuWwDAgCUwCgYIKoZIzj0EAwIw
IzEhMB8GA1UEAwwYTmV4dGVuZG8gT3ZlcmNvb2tlZCAyIENBMB4XDTI2MDkyMzA4
MDMzMVoXDTM2MDkyMDA4MDMzMVowIzEhMB8GA1UEAwwYTmV4dGVuZG8gT3ZlcmNv
b2tlZCAyIENBMFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAEZlGY+45tHGHAaBs7
hC9q2FJN9awfYCGOifU/fOYNuPcmytLIZ/E+x4GvFWeJatRO4/0cqLzI5jAmhZdy
R7g3aaNjMGEwHQYDVR0OBBYEFF074IFG9PLpJdowZYdG8yfXMGZ+MB8GA1UdIwQY
MBaAFF074IFG9PLpJdowZYdG8yfXMGZ+MA8GA1UdEwEB/wQFMAMBAf8wDgYDVR0P
AQH/BAQDAgEGMAoGCCqGSM49BAMCA0kAMEYCIQDuX2SXmEG3EfaB1mcbekLIgHSv
ow1nTUV/vU36rfsfCAIhAK1ZwoLX0GwDQh+Nm3836VNDDviWQ3dUN7zO5WMHl9Cz
-----END CERTIFICATE-----
"""),
            // nextendo-pokemon-legends-za-ca.pem (Pokemon Legends: Z-A)
            new("6391c69d6d01c3bcc39c30b261e16eab20242de4c14cfd80a4445dd304ad0722", """
-----BEGIN CERTIFICATE-----
MIIBuTCCAV+gAwIBAgIUb0S9q7d+vniIxKaaZlp1ycdDQiswCgYIKoZIzj0EAwIw
KjEoMCYGA1UEAwwfTmV4dGVuZG8gUG9rZW1vbiBMZWdlbmRzIFotQSBDQTAeFw0y
NjA5MjgyMjA1MzJaFw0zNjA5MjUyMjA1MzJaMCoxKDAmBgNVBAMMH05leHRlbmRv
IFBva2Vtb24gTGVnZW5kcyBaLUEgQ0EwWTATBgcqhkjOPQIBBggqhkjOPQMBBwNC
AARR0I4orZbvRFBI63PQwsvidiLlBc3tcPCGULkCqx9U0SiwWKYxmivCO//NZGsO
6cEwuNETv/cLZeyScft3qButo2MwYTAdBgNVHQ4EFgQUxl7nJ0vIzGKprujoG/8I
X0O7QFMwHwYDVR0jBBgwFoAUxl7nJ0vIzGKprujoG/8IX0O7QFMwDwYDVR0TAQH/
BAUwAwEB/zAOBgNVHQ8BAf8EBAMCAgQwCgYIKoZIzj0EAwIDSAAwRQIgTPEXrEA2
nuXm+mlLWlcBXRXhedNj7tB44Fo6ELb/GCACIQCgp5ckM4fRArnvE8Bwx+m7QJGw
zdAq1CTeFUrJ6r/siw==
-----END CERTIFICATE-----
"""),
        ];

        private static X509Certificate2Collection _trusted;

        /// <summary>Whether the next (or current) session plays online.</summary>
        public static bool Enabled => _settings != null;

        // Tests only (the gate's fixture sets it by reflection): roots standing in for Nextendo's, whose keys are theirs.
        internal static X509Certificate2Collection RootsForTests;

        /// <summary>Back to offline: what a launch without online play asks for.</summary>
        public static void Clear()
        {
            _settings = null;
            _pending = null;
            Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCache.Clear(); // adapt_nextendo_data
        }

        /// <summary>
        /// Called when a program's configuration is made. The first program of a host session takes the host's last
        /// request, which is consumed, so a session that follows without a new request is offline whatever the host
        /// does; a program the game starts in the same session (ExecuteProgram, a restart) keeps the session's.
        /// </summary>
        public static void BeginSession(bool firstProgram)
        {
            if (!firstProgram) return;
            Settings settings = _pending;
            if (settings?.SmashCandidates is { Length: > 1 } candidates)
            {
                settings.SmashSelection = Task.Run(() => SelectSmashServer(candidates, settings.SmashPrivateTls));
            }
            _settings = settings;
            _pending = null;

            // adapt_nextendo_data: the title's BCAT data, served while this session plays online (nothing offline).
            int files = Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCache.Serve(settings?.BcatDirectory, out string reason);
            if (settings != null) settings.BcatFiles = settings.BcatDirectory == null ? -1 : files;
            if (settings?.BcatDirectory != null && reason != null)
            {
                Logger.Warning?.Print(LogClass.ServiceBcat, "Online play: BCAT data " + (files < 0 ? "not served: " : "served; ") + reason + ".");
            }
        }

        /// <summary>
        /// Applies the host's request: an empty object clears the configuration; otherwise nexToken, pid, serverAddress
        /// and natAddress are all required and the two addresses must differ (the NAT test compares two vantage points).
        /// A refused request leaves the engine offline. Returns whether the next session plays online.
        /// </summary>
        public static bool Configure(string request)
        {
            Clear();
            if (string.IsNullOrWhiteSpace(request)) return false;
            using JsonDocument document = JsonDocument.Parse(request);
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new FormatException("Online configuration must be an object.");
            bool any = false;
            foreach (JsonProperty _ in root.EnumerateObject()) { any = true; break; }
            if (!any) return false;
            string token = Text(root, "nexToken");
            if (token == null || token.Length > MaxTokenLength || !token.StartsWith("nx2.", StringComparison.Ordinal))
                throw new FormatException("Online configuration: the game token is missing or malformed.");
            foreach (char c in token)
                if (c <= ' ' || c > '~' || c == '"' || c == '\\') throw new FormatException("Online configuration: the game token is malformed.");
            if (!root.TryGetProperty("pid", out JsonElement pidValue) || pidValue.ValueKind != JsonValueKind.Number ||
                !pidValue.TryGetInt64(out long pid) || pid <= 0)
                throw new FormatException("Online configuration: the account PID is missing or malformed.");
            IPAddress server = Address(Text(root, "serverAddress"), "serverAddress");
            IPAddress nat = Address(Text(root, "natAddress"), "natAddress");
            if (server.Equals(nat)) throw new FormatException("Online configuration: the server and NAT test addresses must differ.");
            _pending = new Settings
            {
                NexToken = token, Pid = pid, Server = server, Nat = nat,
                SmashCandidates = SmashCandidates(root, server, nat),
                SmashPrivateTls = Text(root, "titleId") == SmashTitle &&
                    root.TryGetProperty("smashPrivateTls", out JsonElement consent) && consent.ValueKind == JsonValueKind.True,
                BcatDirectory = BcatDirectory(root), Nsa = Nsa(root), AcceptedVersions = AcceptedVersions(root),
            };
            return true;
        }

        // Only SSBU launches with multiple answers from the operator's game DNS name supply this field.
        private static IPAddress[] SmashCandidates(JsonElement root, IPAddress server, IPAddress nat)
        {
            if (!root.TryGetProperty("smashDnsAddresses", out JsonElement entries) ||
                entries.ValueKind != JsonValueKind.Array || entries.GetArrayLength() > 4) return null;
            List<IPAddress> addresses = [server];
            foreach (JsonElement entry in entries.EnumerateArray())
            {
                if (entry.ValueKind != JsonValueKind.String || !IPAddress.TryParse(entry.GetString(), out IPAddress address) ||
                    address.AddressFamily != AddressFamily.InterNetwork || IPAddress.IsLoopback(address) ||
                    address.Equals(IPAddress.Any) || address.Equals(nat) || addresses.Contains(address)) continue;
                addresses.Add(address);
            }
            return addresses.ToArray();
        }

        // No application data is sent. Start during guest startup and bound the whole race, including slow peers.
        private static async Task<IPAddress> SelectSmashServer(IPAddress[] candidates, bool privateTls)
        {
            using CancellationTokenSource deadline = new(TimeSpan.FromSeconds(2));
            List<Task<IPAddress>> probes = new(candidates.Length);
            foreach (IPAddress address in candidates) probes.Add(VerifySmashRoute(address, privateTls, deadline.Token));
            try
            {
                while (probes.Count != 0)
                {
                    Task<IPAddress> done = await Task.WhenAny(probes).ConfigureAwait(false);
                    probes.Remove(done);
                    IPAddress verified = await done.ConfigureAwait(false);
                    if (verified != null) return verified;
                }
                return candidates[0]; // The game's own TLS handshake can still recover from a transient failure.
            }
            finally
            {
                deadline.Cancel();
                await Task.WhenAll(probes).ConfigureAwait(false);
            }
        }

        private static async Task<IPAddress> VerifySmashRoute(IPAddress address, bool privateTls, CancellationToken stop)
        {
            try
            {
                using TcpClient socket = new(AddressFamily.InterNetwork);
                await socket.ConnectAsync(address, 443, stop).ConfigureAwait(false);
                using SslStream tls = new(socket.GetStream(), false);
                await tls.AuthenticateAsClientAsync(new SslClientAuthenticationOptions
                {
                    TargetHost = SmashHost,
                    ApplicationProtocols = [SslApplicationProtocol.Http11],
                    RemoteCertificateValidationCallback = (_, cert, chain, _) =>
                        CertificateFailure(cert, chain, SmashHost, RootsForTests ?? TrustedRoots(), localChainOnly: true) == null ||
                        (privateTls && IsLegacySmashCertificate(cert)),
                }, stop).ConfigureAwait(false);
                return address;
            }
            catch (Exception) { return null; }
        }

        // adapt_nextendo_data: the optional parts. A malformed one is left out and journaled (without its value); the rest
        // of the request stands.
        private static void Dropped(string name) =>
            Logger.Warning?.Print(LogClass.ServiceAcc, "Online play: the request's " + name + " is malformed and left out.");

        internal static string BcatDirectory(JsonElement root)
        {
            if (!root.TryGetProperty("bcatDirectory", out JsonElement value)) return null;
            string text = value.ValueKind == JsonValueKind.String ? value.GetString() : null;
            string name = text == null ? null : System.IO.Path.GetFileName(System.IO.Path.TrimEndingDirectorySeparator(text));
            if (text == null || text.Length > 1024 || !System.IO.Path.IsPathFullyQualified(text) ||
                Array.IndexOf(text.Split('/', '\\'), "..") >= 0 || name == null || name.Length != 16 || !IsLowerHex(name))
            {
                Dropped("bcatDirectory");
                return null;
            }

            return text;
        }

        internal static long? Nsa(JsonElement root)
        {
            if (!root.TryGetProperty("nsa", out JsonElement value)) return null;
            string text = value.ValueKind == JsonValueKind.String ? value.GetString() : null;
            if (text == null || text.Length != 16 || !IsLowerHex(text) ||
                !ulong.TryParse(text, System.Globalization.NumberStyles.AllowHexSpecifier, null, out ulong nsa) || nsa == 0)
            {
                Dropped("nsa");
                return null;
            }

            return unchecked((long)nsa);
        }

        internal static string[] AcceptedVersions(JsonElement root)
        {
            if (!root.TryGetProperty("acceptedVersions", out JsonElement value)) return null;
            if (value.ValueKind != JsonValueKind.Array || value.GetArrayLength() > MaxAcceptedVersions)
            {
                Dropped("acceptedVersions");
                return null;
            }

            List<string> versions = [];
            foreach (JsonElement item in value.EnumerateArray())
            {
                string text = item.ValueKind == JsonValueKind.String ? item.GetString() : null;
                if (string.IsNullOrWhiteSpace(text) || text.Length > MaxVersionLength)
                {
                    Dropped("acceptedVersions");
                    return null;
                }

                foreach (char c in text)
                {
                    if (c <= ' ' || c > '~')
                    {
                        Dropped("acceptedVersions");
                        return null;
                    }
                }

                versions.Add(text);
            }

            return versions.ToArray();
        }

        private static bool IsLowerHex(string text)
        {
            foreach (char c in text)
                if (!(c is >= '0' and <= '9' or >= 'a' and <= 'f')) return false;
            return true;
        }

        /// <summary>
        /// adapt_nextendo_data: the session's line, written once when the game first asks for its id_token (the installed
        /// version is known then): the title, its installed version and whether the catalog accepts it, the BCAT data served
        /// and the account id used. No token or account value is written. Returns the version, as the id_token takes it.
        /// </summary>
        public static string NoteVersion(string titleId, string displayVersion)
        {
            Settings settings = _settings;
            if (settings == null) return displayVersion;
            if (System.Threading.Interlocked.Exchange(ref settings.Journaled, 1) == 0)
            {
                string version = displayVersion?.Trim();
                string accepted = settings.AcceptedVersions == null ? "unknown (no catalog entry)" :
                    Array.IndexOf(settings.AcceptedVersions, version) >= 0 ? "yes" : "no (accepted: " + string.Join(", ", settings.AcceptedVersions) + ")";
                string bcat = settings.BcatDirectory == null ? "none" : settings.BcatFiles < 0 ? "refused" : settings.BcatFiles + " files";
                Logger.Info?.Print(LogClass.ServiceAcc,
                    $"Online play: title {titleId}, installed version {version ?? "unknown"}, accepted by Nextendo's catalog: {accepted}; " +
                    $"BCAT data: {bcat}; account id: {(settings.Nsa != null ? "the account's NSA" : "the PID")} (adapt_nextendo_data)");
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("onlineAccount", "prepared",
                    detail: $"title={titleId}; version={version ?? "unknown"}; catalog={accepted}; BCAT={bcat}");
            }

            return displayVersion;
        }

        private static string Text(JsonElement root, string name) =>
            root.TryGetProperty(name, out JsonElement value) && value.ValueKind == JsonValueKind.String ? value.GetString() : null;

        // The Switch resolver hands a game IPv4 addresses only.
        private static IPAddress Address(string text, string name)
        {
            if (text == null || !IPAddress.TryParse(text, out IPAddress address) ||
                address.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork ||
                IPAddress.IsLoopback(address) || address.Equals(IPAddress.Any))
                throw new FormatException("Online configuration: " + name + " is not a usable IPv4 address.");
            return address;
        }

        /// <summary>
        /// The address a host name is redirected to, or null: offline, or not one of the documented names.
        /// </summary>
        public static IPAddress Redirect(string host) => Resolve(host, remember: true);

        public static bool ShouldRedirect(string host) => Resolve(host, remember: false) != null;

        private static IPAddress Resolve(string host, bool remember)
        {
            Settings settings = _settings;
            if (settings == null || string.IsNullOrEmpty(host)) return null;
            host = host.TrimEnd('.');
            if (remember && settings.SmashSelection != null && string.Equals(host, SmashHost, StringComparison.OrdinalIgnoreCase))
            {
                IPAddress selected = settings.SmashSelection.GetAwaiter().GetResult();
                settings.SmashServer = selected;
                return Note(settings, selected, SmashHost);
            }
            foreach (string pattern in _natHosts)
                if (Matches(pattern, host)) return remember ? Note(settings, settings.Nat, host) : settings.Nat;
            foreach (string pattern in _serverHosts)
                if (Matches(pattern, host)) return remember ? Note(settings, settings.Server, host) : settings.Server;
            return null;
        }

        private static IPAddress Note(Settings settings, IPAddress address, string host)
        {
            lock (settings.Resolved) settings.Resolved[address] = host;
            return address;
        }

        /// <summary>Whether a TLS peer is one of the two configured servers.</summary>
        public static bool IsServer(IPAddress address)
        {
            Settings settings = _settings;
            if (settings == null || address == null) return false;
            if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
            return address.Equals(settings.Server) || address.Equals(settings.Nat) || address.Equals(settings.SmashServer);
        }

        /// <summary>The host name last redirected to a server address, or null.</summary>
        public static string HostFor(IPAddress address)
        {
            Settings settings = _settings;
            if (settings == null || address == null) return null;
            if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
            lock (settings.Resolved) return settings.Resolved.TryGetValue(address, out string host) ? host : null;
        }

        /// <summary>The network service account id the game reads: the NSA or the PID online, the engine's own value otherwise.</summary>
        public static long AccountId(long offline)
        {
            Settings settings = _settings;
            // adapt_nextendo_data: the account's NSA when the request gives one (Animal Crossing: New Horizons).
            return settings == null ? offline : settings.Nsa ?? settings.Pid;
        }

        /// <summary>
        /// Adds what Nextendo's game servers read from the account id_token: jti, hm, tv (the installed game version) and
        /// nnex (the game token). Nothing is added offline.
        /// </summary>
        public static void AddClaims(IDictionary<string, object> claims, string titleVersion)
        {
            Settings settings = _settings;
            if (settings == null || claims == null) return;
            claims["jti"] = Guid.NewGuid().ToString();
            claims["hm"] = true;
            if (!string.IsNullOrWhiteSpace(titleVersion)) claims["tv"] = titleVersion.Trim();
            claims["nnex"] = settings.NexToken;
        }

        /// <summary>ALPN for a configured server: h2 on NPLN hosts (gRPC), http/1.1 otherwise (NEX over WebSocket).</summary>
        public static List<SslApplicationProtocol> ApplicationProtocols(string host)
        {
            string name = host ?? string.Empty;
            bool npln = name.Contains("npln", StringComparison.OrdinalIgnoreCase) ||
                        name.Contains("gs.nintendo.net", StringComparison.OrdinalIgnoreCase);
            return [npln ? SslApplicationProtocol.Http2 : SslApplicationProtocol.Http11];
        }

        // A certificate callback runs BEFORE AuthenticateAsClient finishes. Keep transport events separate:
        // neither certificate acceptance nor bytes exchanged proves NEX login or a completed match.
        // Bound events to the launching session and never record addresses, tokens, payloads or exception messages.
        public static Action<string, string> TransportJournal(string host, int port)
        {
            Settings settings = _settings;
            if (settings == null) return (_, _) => { };
            int id = Interlocked.Increment(ref settings.TransportSequence);
            int failed = 0;
            string route = string.Equals(host, SmashHost, StringComparison.OrdinalIgnoreCase) ? "ssbu" : "other";
            return (status, detail) =>
            {
                if (status == "failed" && Interlocked.Exchange(ref failed, 1) != 0) return;
                if (id <= 64 && ReferenceEquals(settings, _settings))
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("onlineTls", status,
                        detail: $"connection={id}; route={route}; port={port}; {detail}");
            };
        }

        public static HOS.Services.Ssl.ResultCode TransportError(Exception error)
        {
            for (Exception current = error; current != null; current = current.InnerException)
                if (current is SocketException socket)
                    return socket.SocketErrorCode switch
                    {
                        SocketError.ConnectionReset => HOS.Services.Ssl.ResultCode.ConnectionReset,
                        SocketError.TimedOut => HOS.Services.Ssl.ResultCode.Timeout,
                        _ => HOS.Services.Ssl.ResultCode.ConnectionAbort,
                    };
            return HOS.Services.Ssl.ResultCode.ConnectionAbort;
        }

        // Socket.Poll cannot see SslStream's decrypted buffer. A 1 ms synchronous read timeout is not a
        // safe substitute: a partial TLS record can outlive that timeout. Keep ONE asynchronous read alive
        // across guest polls, into owned storage (never an IPC WritableRegion that dies after WouldBlock).
        // The existing service returns WouldBlock when data is unavailable, for either guest socket mode.
        public sealed class TlsReadBuffer : IDisposable
        {
            private readonly SslStream _stream;
            private readonly Action<string, string> _journal;
            private readonly object _gate = new();
            private readonly byte[] _buffer = new byte[16 * 1024];
            private Task<int> _pending;
            private int _offset, _count;
            private bool _eof, _disposed;
            private long _readBytes, _writtenBytes;
            private HOS.Services.Ssl.ResultCode _error;

            public TlsReadBuffer(SslStream stream, Action<string, string> journal)
            {
                _stream = stream;
                _journal = journal;
            }

            private HOS.Services.Ssl.ResultCode Fill()
            {
                if (_disposed) return HOS.Services.Ssl.ResultCode.ConnectionAbort;
                if (_error != HOS.Services.Ssl.ResultCode.Success) return _error;
                if (_count != 0 || _eof) return HOS.Services.Ssl.ResultCode.Success;
                try
                {
                    _pending ??= _stream.ReadAsync(_buffer.AsMemory()).AsTask();
                    if (!_pending.IsCompleted) return HOS.Services.Ssl.ResultCode.WouldBlock;
                    _count = _pending.GetAwaiter().GetResult();
                    _pending = null;
                    _offset = 0;
                    if (_count == 0)
                    {
                        _eof = true;
                        _journal("eof", "read");
                    }
                    return HOS.Services.Ssl.ResultCode.Success;
                }
                catch (Exception error) when (error is IOException or SocketException or AuthenticationException or ObjectDisposedException)
                {
                    _pending = null;
                    _error = TransportError(error);
                    _journal("failed", "read; result=" + _error);
                    return _error;
                }
            }

            public HOS.Services.Ssl.ResultCode Read(out int count, Memory<byte> destination, bool peek = false)
            {
                lock (_gate)
                {
                    count = -1;
                    if (_disposed) return HOS.Services.Ssl.ResultCode.ConnectionAbort;
                    if (destination.Length == 0) { count = 0; return HOS.Services.Ssl.ResultCode.Success; }
                    HOS.Services.Ssl.ResultCode result = Fill();
                    if (result != HOS.Services.Ssl.ResultCode.Success) return result;
                    count = Math.Min(destination.Length, _count);
                    _buffer.AsMemory(_offset, count).CopyTo(destination);
                    if (!peek)
                    {
                        if (_readBytes == 0 && count > 0) _journal("received", "first-response");
                        _readBytes += count;
                        _offset += count;
                        _count -= count;
                    }
                    return HOS.Services.Ssl.ResultCode.Success;
                }
            }

            public int Pending()
            {
                lock (_gate) return Fill() == HOS.Services.Ssl.ResultCode.Success ? _count : 0;
            }

            public void Written(int count)
            {
                lock (_gate)
                {
                    if (_writtenBytes == 0 && count > 0) _journal("sent", "first-request");
                    _writtenBytes += count;
                }
            }

            public void Dispose()
            {
                lock (_gate)
                {
                    if (_disposed) return;
                    _disposed = true;
                    _journal("closed", $"readBytes={_readBytes}; writtenBytes={_writtenBytes}");
                    // Dispose cancels an outstanding read. Observe its eventual failure without waiting on
                    // the network or reusing its buffer in another session.
                    if (_pending != null)
                        _ = _pending.ContinueWith(task => { _ = task.Exception; }, CancellationToken.None,
                            TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                    _stream.Dispose();
                }
            }
        }

        /// <summary>Bind the optional SSBU exception to this session and this socket's actual destination.</summary>
        public static RemoteCertificateValidationCallback CertificateValidator(IPAddress peer, int port)
        {
            Settings settings = _settings;
            if (peer?.IsIPv4MappedToIPv6 == true) peer = peer.MapToIPv4();
            // The published SSBU auth and secure NEX ports. No NAT, arbitrary IP, account API or other title.
            bool privateRoute = settings?.SmashPrivateTls == true && peer != null && (port == 443 || port == 60005) &&
                !peer.Equals(settings.Nat) && (peer.Equals(settings.Server) || peer.Equals(settings.SmashServer));
            return (sender, certificate, chain, errors) =>
                ValidateServerCertificate(sender, certificate, chain, errors, settings, privateRoute);
        }

        /// <summary>Strict validation when no session/socket scope is supplied.</summary>
        public static bool ValidateServerCertificate(object sender, X509Certificate certificate, X509Chain chain, SslPolicyErrors errors)
            => ValidateServerCertificate(sender, certificate, chain, errors, _settings, false);

        private static bool ValidateServerCertificate(object sender, X509Certificate certificate, X509Chain chain,
            SslPolicyErrors errors, Settings settings, bool privateRoute)
        {
            string host = (sender as SslStream)?.TargetHostName;
            string failure = CertificateFailure(certificate, chain, host, RootsForTests ?? TrustedRoots());
            bool valid = failure == null;
            bool smash = string.Equals(host, SmashHost, StringComparison.OrdinalIgnoreCase);
            bool compatibility = !valid && privateRoute && ReferenceEquals(settings, _settings) && smash &&
                IsLegacySmashCertificate(certificate);
            if (settings != null && ReferenceEquals(settings, _settings) && smash)
            {
                int state = valid ? 1 : compatibility ? 3 : 2;
                if (Interlocked.Exchange(ref settings.SmashTlsState, state) != state)
                    Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("smashTls", valid ? "accepted" : compatibility ? "compatibility" : "refused",
                        detail: compatibility ? "unverified-private-certificate" : failure ?? "verified");
            }
            if (!valid && !compatibility)
            {
                Logger.Warning?.Print(LogClass.ServiceSsl,
                    $"Online play: certificate refused for '{host}' (reason: {failure}).");
            }

            return valid || compatibility;
        }

        // This identifies the legacy certificate format, NOT the server's identity. Only the explicitly consented,
        // socket-scoped SSBU route can use it. Never add this certificate to a trust store or learn a persistent pin
        // from an unverified connection. Missing, expired, renamed or SAN-bearing certificates keep the strict path.
        private static bool IsLegacySmashCertificate(X509Certificate certificate)
        {
            if (certificate == null) return false;
            try
            {
                using X509Certificate2 leaf = new(certificate);
                DateTime now = DateTime.UtcNow;
                if (leaf.Subject != "CN=nintendo-private-server" || !leaf.SubjectName.RawData.AsSpan().SequenceEqual(leaf.IssuerName.RawData) ||
                    now < leaf.NotBefore.ToUniversalTime() || now > leaf.NotAfter.ToUniversalTime()) return false;
                foreach (X509Extension extension in leaf.Extensions)
                    if (extension.Oid?.Value == "2.5.29.17") return false;
                return true;
            }
            catch (Exception) { return false; }
        }

        /// <summary>A chain from the certificate to one of the roots, with the host named by the leaf.</summary>
        internal static bool Validate(X509Certificate certificate, X509Chain presented, string host, X509Certificate2Collection roots) =>
            CertificateFailure(certificate, presented, host, roots) == null;

        private static string CertificateFailure(X509Certificate certificate, X509Chain presented, string host, X509Certificate2Collection roots, bool localChainOnly = false)
        {
            if (certificate == null) return "missing-certificate";
            if (string.IsNullOrEmpty(host)) return "missing-host";
            if (roots == null || roots.Count == 0) return "missing-roots";
            try
            {
                using X509Certificate2 leaf = new(certificate);
                if (!leaf.MatchesHostname(host, allowWildcards: true, allowCommonName: false)) return "hostname";
                using X509Chain chain = new();
                chain.ChainPolicy.DisableCertificateDownloads = localChainOnly;
                chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
                chain.ChainPolicy.CustomTrustStore.AddRange(roots);
                chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
                chain.ChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1")); // serverAuth
                if (presented != null)
                {
                    foreach (X509ChainElement element in presented.ChainElements)
                        if (!element.Certificate.RawData.AsSpan().SequenceEqual(leaf.RawData)) chain.ChainPolicy.ExtraStore.Add(element.Certificate);
                }

                return chain.Build(leaf) ? null : "chain";
            }
            catch (Exception)
            {
                return "validation-error";
            }
        }

        /// <summary>The published roots, each checked against its fingerprint once.</summary>
        internal static X509Certificate2Collection TrustedRoots()
        {
            X509Certificate2Collection trusted = _trusted;
            if (trusted != null) return trusted;
            trusted = [];
            foreach (Root root in _roots)
            {
                X509Certificate2 certificate = X509Certificate2.CreateFromPem(root.Pem);
                if (Convert.ToHexString(SHA256.HashData(certificate.RawData)).ToLowerInvariant() != root.Sha256)
                    throw new InvalidOperationException("A Nextendo root differs from its published fingerprint.");
                trusted.Add(certificate);
            }

            return _trusted = trusted;
        }

        /// <summary>One '*' stands for any run of characters (several labels included); names compare without case.</summary>
        internal static bool Matches(string pattern, string host)
        {
            int star = pattern.IndexOf('*');
            if (star < 0) return string.Equals(pattern, host, StringComparison.OrdinalIgnoreCase);
            string head = pattern[..star], tail = pattern[(star + 1)..];
            return host.Length >= head.Length + tail.Length &&
                host.StartsWith(head, StringComparison.OrdinalIgnoreCase) &&
                host.EndsWith(tail, StringComparison.OrdinalIgnoreCase);
        }
    }
}
