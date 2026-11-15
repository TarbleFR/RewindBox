// The Nextendo online lot (adapt_nextendo_online) on the production Ryujinx.HLE assembly the nifm-network-watch gate builds
// from the final preparation: request refusals, guest Internet only while configured, the documented redirect rules
// through the real resolver and blacklist, the PID as the account id, the id_token claims of the real generator, ALPN,
// Nextendo's published roots and chain plus host validation (a test root stands in for Nextendo's private keys).
// Host .NET runtime, not an iPhone: TLS on iOS goes through Apple's stack.
using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.NetworkInformation;
using System.Net.Sockets;
using System.Threading.Tasks;
using System.Net;
using System.Net.Security;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Text.Json;
using Ryujinx.HLE;

static class Program
{
    static int checks;
    static string handshakes;
    const string Smash = "g23380901-lp1.s.n.srv.nintendo.net";

    static string Request(string tokenText, object pid, string server, string nat) =>
        JsonSerializer.Serialize(new Dictionary<string, object> { ["nexToken"] = tokenText, ["pid"] = pid, ["serverAddress"] = server, ["natAddress"] = nat });

    static string Handshakes(Assembly hle, IPAddress local, string game)
    {
        X509Certificate2 root = Ca("Handshake test root", out RSA rootKey);
        X509Certificate2 named = Issue(root, rootKey, Smash, [Smash], false, out RSA namedKey).CopyWithPrivateKey(namedKey);
        X509Certificate2 other = Issue(root, rootKey, "other.example", ["other.example"], false, out RSA otherKey).CopyWithPrivateKey(otherKey);
        FieldInfo testRoots = typeof(EmbeddedOnline).GetField("RootsForTests", BindingFlags.NonPublic | BindingFlags.Static);
        Type defaultSocket = hle.GetType("Ryujinx.HLE.HOS.Services.Sockets.Bsd.Proxy.DefaultSocket", true);
        Type managedSocket = hle.GetType("Ryujinx.HLE.HOS.Services.Sockets.Bsd.Impl.ManagedSocket", true);
        Type connectionType = hle.GetType("Ryujinx.HLE.HOS.Services.Ssl.SslService.SslManagedSocketConnection", true);
        Type versionType = hle.GetType("Ryujinx.HLE.HOS.Services.Ssl.Types.SslVersion", true);
        const BindingFlags any = BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance;
        const int connectionAbort = (210 << 9) | 123;

        (int code, SslApplicationProtocol alpn, string sni) Run(X509Certificate2 presented, string hostName)
        {
            using TcpListener listener = new(local, 0);
            listener.Start();
            Task<(SslApplicationProtocol, string)> server = Task.Run(() =>
            {
                using TcpClient accepted = listener.AcceptTcpClient();
                using SslStream stream = new(accepted.GetStream());
                string seen = null;
                try
                {
                    stream.AuthenticateAsServer(new SslServerAuthenticationOptions
                    {
                        ServerCertificateSelectionCallback = (_, name) => { seen = name; return presented; },
                        ApplicationProtocols = [SslApplicationProtocol.Http2, SslApplicationProtocol.Http11],
                    });
                    return (stream.NegotiatedApplicationProtocol, seen);
                }
                catch (Exception)
                {
                    return (default(SslApplicationProtocol), seen);
                }
            });
            Socket client = new(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
            client.Connect(new IPEndPoint(local, ((IPEndPoint)listener.LocalEndpoint).Port));
            object impl = Activator.CreateInstance(defaultSocket, any, null, [client, null], null);
            object managed = Activator.CreateInstance(managedSocket, any, null, [impl], null);
            object connection = Activator.CreateInstance(connectionType, any, null, [null, Enum.ToObject(versionType, 1u << 5), 0, managed], null);
            int code = Convert.ToInt32(connectionType.GetMethod("Handshake").Invoke(connection, [hostName]));
            client.Dispose();
            (SslApplicationProtocol alpn, string sni) = server.Wait(15000) ? server.Result : (default, null);
            return (code, alpn, sni);
        }

        EmbeddedOnline.Configure(Request(game, 1800000042L, local.ToString(), "203.0.113.8"));
        EmbeddedOnline.BeginSession();
        testRoots.SetValue(null, new X509Certificate2Collection(root));
        Check(local.Equals(EmbeddedOnline.Redirect(Smash)), "the server rule points at the local server");
        (int code, SslApplicationProtocol alpn, string sni) = Run(named, "");
        Check(code == 0 && alpn == SslApplicationProtocol.Http11 && sni == Smash,
              $"handshake accepted: chain and host, ALPN http/1.1, SNI from the redirected name ({code}, {alpn}, {sni})");
        (code, _, _) = Run(other, Smash);
        Check(code == connectionAbort, "a certificate naming another host is the game's connection error, no exception");
        testRoots.SetValue(null, null);
        (code, _, _) = Run(named, Smash);
        Check(code == connectionAbort, "a chain to another root than Nextendo's is the game's connection error, no exception");
        testRoots.SetValue(null, new X509Certificate2Collection(root));
        EmbeddedOnline.Configure(Request(game, 1800000042L, local.ToString(), "203.0.113.8"));
        EmbeddedOnline.BeginSession();
        (code, _, sni) = Run(named, "");
        Check(code == connectionAbort && sni == null, "no host name and none redirected: refused without a reverse lookup");
        testRoots.SetValue(null, null);
        return "4 handshakes";
    }
    static void Check(bool condition, string what)
    {
        checks++;
        if (!condition) { Console.Error.WriteLine("FAIL: " + what); Environment.Exit(1); }
    }
    static bool Throws<T>(Action action) where T : Exception
    {
        try { action(); return false; } catch (T) { return true; }
    }
    static string B64(string part)
    {
        string padded = part.Replace('-', '+').Replace('_', '/');
        padded += new string('=', (4 - padded.Length % 4) % 4);
        return Encoding.UTF8.GetString(Convert.FromBase64String(padded));
    }

    static X509Certificate2 Ca(string name, out RSA key)
    {
        key = RSA.Create(2048);
        CertificateRequest request = new("CN=" + name, key, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        request.CertificateExtensions.Add(new X509BasicConstraintsExtension(true, false, 0, true));
        request.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.KeyCertSign | X509KeyUsageFlags.CrlSign, true));
        request.CertificateExtensions.Add(new X509SubjectKeyIdentifierExtension(request.PublicKey, false));
        return request.CreateSelfSigned(DateTimeOffset.UtcNow.AddDays(-1), DateTimeOffset.UtcNow.AddYears(5));
    }

    static X509Certificate2 Issue(X509Certificate2 issuer, RSA issuerKey, string subject, string[] names, bool ca, out RSA key)
    {
        key = RSA.Create(2048);
        CertificateRequest request = new("CN=" + subject, key, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        request.CertificateExtensions.Add(new X509BasicConstraintsExtension(ca, false, 0, true));
        if (names.Length > 0)
        {
            SubjectAlternativeNameBuilder san = new();
            foreach (string name in names) san.AddDnsName(name);
            request.CertificateExtensions.Add(san.Build());
        }
        request.CertificateExtensions.Add(new X509SubjectKeyIdentifierExtension(request.PublicKey, false));
        request.CertificateExtensions.Add(X509AuthorityKeyIdentifierExtension.CreateFromCertificate(issuer, true, false));
        X509SignatureGenerator generator = X509SignatureGenerator.CreateForRSA(issuerKey, RSASignaturePadding.Pkcs1);
        byte[] serial = new byte[8];
        RandomNumberGenerator.Fill(serial);
        serial[0] &= 0x7F;
        return request.Create(issuer.SubjectName, generator, DateTimeOffset.UtcNow.AddHours(-1), DateTimeOffset.UtcNow.AddYears(1), serial);
    }

    static int Main()
    {
        Assembly hle = typeof(EmbeddedOnline).Assembly;
        Type blacklist = hle.GetType("Ryujinx.HLE.HOS.Services.Sockets.Sfdnsres.Proxy.DnsBlacklist", true);
        Type resolver = hle.GetType("Ryujinx.HLE.HOS.Services.Sockets.Sfdnsres.Proxy.DnsMitmResolver", true);
        Type manager = hle.GetType("Ryujinx.HLE.HOS.Services.Account.Acc.AccountService.ManagerServer", true);
        Type userIdType = hle.GetType("Ryujinx.HLE.HOS.Services.Account.Acc.UserId", true);
        Type configuration = hle.GetType("Ryujinx.HLE.HleConfiguration", true);
        MethodInfo blocked = blacklist.GetMethod("IsHostBlocked", BindingFlags.Public | BindingFlags.Static);
        object instance = resolver.GetProperty("Instance", BindingFlags.Public | BindingFlags.Static).GetValue(null);
        MethodInfo resolve = resolver.GetMethod("ResolveAddress");
        MethodInfo token = manager.GetMethod("GenerateIdToken", BindingFlags.NonPublic | BindingFlags.Static);
        PropertyInfo accountId = manager.GetProperty("NetworkServiceAccountId", BindingFlags.NonPublic | BindingFlags.Instance);
        PropertyInfo internet = configuration.GetProperty("EnableInternetAccess");
        MethodInfo roots = typeof(EmbeddedOnline).GetMethod("TrustedRoots", BindingFlags.NonPublic | BindingFlags.Static);
        MethodInfo validate = typeof(EmbeddedOnline).GetMethod("Validate", BindingFlags.NonPublic | BindingFlags.Static);
        const string mk8 = "g2b309e01-lp1.s.n.srv.nintendo.net";
        const string smash = "g23380901-lp1.s.n.srv.nintendo.net";

        object user = Activator.CreateInstance(userIdType, [0x0123456789L, 0x42L]);
        object server0 = Activator.CreateInstance(manager, [user]);
        object hleConfig = RuntimeHelpers.GetUninitializedObject(configuration);
        internet.SetValue(hleConfig, false);
        bool InternetOn() => (bool)internet.GetGetMethod(true).Invoke(hleConfig, null);

        // Offline (the default): nothing is redirected, Nintendo's servers stay refused, no Internet for the guest,
        // the account id and the token are the engine's own.
        Check(EmbeddedOnline.Protocol == "rewindbox-nextendo-online-1", "protocol name");
        Check(!EmbeddedOnline.Enabled, "offline by default");
        Check(!InternetOn(), "guest Internet off offline (RewindBox sets it off)");
        internet.SetValue(hleConfig, true);
        Check(InternetOn(), "the configured value still counts");
        internet.SetValue(hleConfig, false);
        Check((long)accountId.GetValue(server0) == 0xcafe + 0x42, "engine account id offline");
        Check(EmbeddedOnline.Redirect(mk8) == null, "no redirect offline");
        Check((bool)blocked.Invoke(null, [mk8]), "blacklist intact offline");
        Check(!EmbeddedOnline.IsServer(IPAddress.Parse("203.0.113.7")), "no server offline");
        string offline = (string)token.Invoke(null, ["4.0.1"]);
        string[] offlineParts = offline.Split('.');
        Check(offlineParts.Length == 3, "offline token shape");
        using (JsonDocument payload = JsonDocument.Parse(B64(offlineParts[1])))
        {
            Check(!payload.RootElement.TryGetProperty("nnex", out _) && !payload.RootElement.TryGetProperty("tv", out _) &&
                  !payload.RootElement.TryGetProperty("hm", out _), "no online claim offline");
            Check(payload.RootElement.GetProperty("iss").GetString() == "https://e0d67c509fb203858ebcb2fe3f88c2aa.baas.nintendo.com", "issuer kept");
        }

        // Refused requests leave the engine offline.
        const string game = "nx2.MTgwMDAwMDA0Mi50YXJibGUuMTc5OTk5OTk5OQ.c2lnbmF0dXJl";
        foreach (string bad in new[] {
            "[]", "{\"nexToken\":\"nx2.a.b\"}",
            Request("abc", 1800000042L, "203.0.113.7", "203.0.113.8"),
            Request(game, null, "203.0.113.7", "203.0.113.8"),
            Request(game, 0, "203.0.113.7", "203.0.113.8"),
            Request(game, "1800000042", "203.0.113.7", "203.0.113.8"),
            Request(game, 1800000042L, "example.org", "203.0.113.8"),
            Request(game, 1800000042L, "127.0.0.1", "203.0.113.8"),
            Request(game, 1800000042L, "2001:db8::1", "203.0.113.8"),
            Request(game, 1800000042L, "203.0.113.7", "203.0.113.7"),
            Request("nx2.a b", 1800000042L, "203.0.113.7", "203.0.113.8"),
            Request("nx2." + new string('a', 1100), 1800000042L, "203.0.113.7", "203.0.113.8") })
        {
            Check(Throws<FormatException>(() => EmbeddedOnline.Configure(bad)), "refused: " + bad[..Math.Min(60, bad.Length)]);
            Check(!EmbeddedOnline.Enabled && !InternetOn(), "offline after a refusal");
        }
        Check(Throws<JsonException>(() => EmbeddedOnline.Configure("{not json")), "invalid JSON refused");
        Check(!EmbeddedOnline.Configure("{}"), "empty request is offline");
        EmbeddedOnline.BeginSession();
        Check(!EmbeddedOnline.Enabled, "empty request: offline session");
        Check(!EmbeddedOnline.Configure(""), "blank request is offline");

        // A request belongs to the next session only.
        Check(EmbeddedOnline.Configure(Request(game, 1800000042L, "203.0.113.7", "203.0.113.8")), "request accepted");
        Check(!EmbeddedOnline.Enabled, "not online before the session takes it");
        EmbeddedOnline.BeginSession();
        Check(EmbeddedOnline.Enabled, "the session takes it");
        EmbeddedOnline.BeginSession();
        Check(!EmbeddedOnline.Enabled && !InternetOn(), "a later session without a request is offline");

        // Online: Internet for the guest, the documented rules, the PID as the account id.
        EmbeddedOnline.Configure(Request(game, 1800000042L, "203.0.113.7", "203.0.113.8"));
        EmbeddedOnline.BeginSession();
        Check(EmbeddedOnline.Enabled && InternetOn(), "online configured, guest Internet on");
        Check((long)accountId.GetValue(server0) == 1800000042L, "the account id the game reads is the PID");
        IPAddress server = IPAddress.Parse("203.0.113.7"), nat = IPAddress.Parse("203.0.113.8");
        (string host, IPAddress to)[] rules =
        [
            ("nncs2-lp1.n.n.srv.nintendo.net", nat), ("NNCS2-LP1.N.N.SRV.NINTENDO.NET", nat), (mk8, nat),
            ("g2df33d01-lp1.p.srv.nintendo.net", nat),
            ("nncs1-lp1.n.n.srv.nintendo.net", server), (smash, server), ("dauth-lp1.ndas.srv.nintendo.net", server),
            ("e0d67c509fb203858ebcb2fe3f88c2aa.baas.nintendo.com", server), ("ctest.cdn.nintendo.net", server),
            ("conntest.nintendowifi.net", server), ("www.nintendo.co.jp", server), ("demonware.net", server),
            ("mww3-switch.demonware.net", server), ("pvzgw3prodapp-01.ea.com", server), ("public-ubiservices.ubi.com", server),
            ("eu.ultimatechickenhorseserver.com", server),
        ];
        foreach ((string host, IPAddress to) in rules)
        {
            Check(to.Equals(EmbeddedOnline.Redirect(host)), "rule " + host);
            Check(!(bool)blocked.Invoke(null, [host]), "not refused when redirected: " + host);
            IPHostEntry entry = (IPHostEntry)resolve.Invoke(instance, [host]);
            Check(entry.AddressList.Length == 1 && entry.AddressList[0].Equals(to) && entry.HostName == host, "resolver " + host);
        }
        Check(!server.Equals(EmbeddedOnline.Redirect("nncs1-lp1.n.n.srv.nintendo.net")) == false &&
              !nat.Equals(EmbeddedOnline.Redirect("nncs1-lp1.n.n.srv.nintendo.net")), "the two NAT test names reach two addresses");
        foreach (string name in new[] { "example.org", "nintendo.net", "evilnintendo.com", "nintendo.com.example.org", "ubi.com", "ea.com", "" })
            Check(EmbeddedOnline.Redirect(name) == null, "not redirected: " + name);
        Check(EmbeddedOnline.IsServer(server) && EmbeddedOnline.IsServer(nat), "both servers recognised");
        Check(EmbeddedOnline.IsServer(server.MapToIPv6()), "IPv4-mapped peer recognised");
        Check(!EmbeddedOnline.IsServer(IPAddress.Parse("203.0.113.9")) && !EmbeddedOnline.IsServer(null), "no other peer");
        EmbeddedOnline.Redirect(mk8);
        Check(EmbeddedOnline.HostFor(nat) == mk8, "SNI is the name last redirected to the address");
        Check(EmbeddedOnline.HostFor(IPAddress.Parse("198.51.100.1")) == null, "no SNI for an unknown peer");

        // ALPN: http/1.1 for NEX hosts, h2 for NPLN hosts.
        Check(EmbeddedOnline.ApplicationProtocols(mk8).SequenceEqual([SslApplicationProtocol.Http11]), "ALPN http/1.1 on NEX");
        Check(EmbeddedOnline.ApplicationProtocols("dauth-lp1.ndas.srv.nintendo.net").SequenceEqual([SslApplicationProtocol.Http11]), "ALPN http/1.1 by default");
        Check(EmbeddedOnline.ApplicationProtocols("t-ba973ec6-lp1.lp1.t.npln.srv.nintendo.net").SequenceEqual([SslApplicationProtocol.Http2]), "ALPN h2 on NPLN");
        Check(EmbeddedOnline.ApplicationProtocols("gs.nintendo.net").SequenceEqual([SslApplicationProtocol.Http2]), "ALPN h2 on gs.nintendo.net");
        Check(EmbeddedOnline.ApplicationProtocols(null).SequenceEqual([SslApplicationProtocol.Http11]), "ALPN without a host");

        // The published roots, each with the fingerprint of the integration guide.
        X509Certificate2Collection published = (X509Certificate2Collection)roots.Invoke(null, null);
        string[] fingerprints = published.Select(c => Convert.ToHexString(SHA256.HashData(c.RawData)).ToLowerInvariant()).ToArray();
        Check(published.Count == 5, "five roots");
        Check(fingerprints.SequenceEqual(new[] {
            "a654c0eff8aa20a72280ea0ef2b5c2a17392922dd78ffbb113862e1ad2c66d49", "d76bf8d0d7a1cd81874b20314171de9ecb64864837d684ab689831a72b6c0a01",
            "817d4a822fbbcdcf0a721563f83cec25be9ae8b2ba435d18bc10dfc2135bf064", "8edcf2c39bb5264b905646569d23cdf265bfbf7c993d30accc3d66c6a953bf9d",
            "6391c69d6d01c3bcc39c30b261e16eab20242de4c14cfd80a4445dd304ad0722" }), "fingerprints of the guide");
        Check(published[0].Subject.Contains("CN=Nextendo Network CA") && published[0].Subject.Contains("O=Nextendo"), "network root subject");

        // Chain validation: a leaf from a test CA standing in for a Nextendo root (their keys are theirs).
        X509Certificate2 ca = Ca("Test Nextendo-like root", out RSA caKey);
        X509Certificate2 intermediate = Issue(ca, caKey, "Test intermediate", [], true, out RSA intermediateKey);
        X509Certificate2 leaf = Issue(intermediate, intermediateKey, mk8, [mk8], false, out _);
        X509Certificate2 wildcard = Issue(ca, caKey, "wildcard", ["*.s.n.srv.nintendo.net"], false, out _);
        X509Certificate2 other = Issue(Ca("Unknown root", out RSA unknownKey), unknownKey, mk8, [mk8], false, out _);
        X509Certificate2Collection test = [ca];
        using X509Chain presented = new();
        presented.ChainPolicy.ExtraStore.Add(intermediate);
        presented.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
        presented.Build(leaf);
        bool Valid(X509Certificate2 certificate, X509Chain chain, string host, X509Certificate2Collection anchors) =>
            (bool)validate.Invoke(null, [certificate, chain, host, anchors]);
        Check(Valid(leaf, presented, mk8, test), "chain to a trusted root naming the host is accepted");
        Check(!Valid(leaf, null, mk8, test), "a missing intermediate is refused");
        Check(!Valid(leaf, presented, smash, test), "another host name is refused");
        Check(!Valid(leaf, presented, null, test), "no host name, no acceptance");
        Check(!Valid(leaf, presented, mk8, published), "a chain to another root than Nextendo's is refused");
        Check(!Valid(other, null, mk8, test), "a leaf of an unknown root is refused");
        Check(Valid(wildcard, null, smash, test), "a one-label wildcard covers the host");
        Check(!Valid(wildcard, null, "a.b.s.n.srv.nintendo.net", test), "a wildcard covers one label only");
        Check(!Valid(leaf, presented, mk8, []), "no roots, no acceptance");

        // The id_token: the documented claims, RS256, three hours, no claim to Nextendo's own key.
        string online = (string)token.Invoke(null, ["4.0.1"]);
        string[] parts = online.Split('.');
        Check(parts.Length == 3 && online.Length < 0xC00, "online token shape and size (" + online.Length + ")");
        using (JsonDocument header = JsonDocument.Parse(B64(parts[0])))
        {
            Check(header.RootElement.GetProperty("alg").GetString() == "RS256", "RS256");
            Check(header.RootElement.GetProperty("typ").GetString() == "id_token", "typ id_token");
            Check(header.RootElement.GetProperty("kid").GetString() != "nextendo-baas-key-1", "no claim to Nextendo's key");
        }
        using (JsonDocument payload = JsonDocument.Parse(B64(parts[1])))
        {
            JsonElement p = payload.RootElement;
            Check(p.GetProperty("nnex").GetString() == game, "nnex is the game token");
            Check(p.GetProperty("tv").GetString() == "4.0.1", "tv is the installed version");
            Check(p.GetProperty("hm").ValueKind == JsonValueKind.True, "hm true");
            Check(Guid.TryParse(p.GetProperty("jti").GetString(), out _), "jti is a UUID");
            Check(p.GetProperty("aud").GetString() == "ed9e2f05d286f7b8", "aud");
            Check(p.GetProperty("sn").GetString() == "XAW10000000000", "sn");
            Check(p.GetProperty("sub").GetString().Length == 32 && p.GetProperty("di").GetString().Length == 32 &&
                  p.GetProperty("bs:did").GetString().Length == 32, "sub, di, bs:did random 16-byte hex");
            Check(p.GetProperty("exp").GetInt64() - p.GetProperty("iat").GetInt64() == 3 * 3600, "three hours");
        }
        string blank = (string)token.Invoke(null, new object[] { null });
        using (JsonDocument payload = JsonDocument.Parse(B64(blank.Split('.')[1])))
            Check(!payload.RootElement.TryGetProperty("tv", out _) && payload.RootElement.TryGetProperty("nnex", out _), "no tv without a version");
        Check(!online.Contains(EmbeddedOnline.Protocol), "nothing else leaks into the token");

        // The largest game token the request accepts still fits the id_token buffer (0xC00).
        string longest = "nx2." + new string('A', EmbeddedOnline.MaxTokenLength - 4);
        EmbeddedOnline.Configure(Request(longest, 9_999_999_999L, "203.0.113.7", "203.0.113.8"));
        EmbeddedOnline.BeginSession();
        string large = (string)token.Invoke(null, ["4.0.1.0"]);
        Check(large.Length < 0xC00, "largest id_token fits its buffer (" + large.Length + " bytes)");

        // The real Handshake of the emulated SSL service, over a real socket, against a local TLS server: chain to a
        // test root naming the host, ALPN http/1.1, SNI from the last redirected name; refusals are the game's
        // connection error (ConnectionAbort), never an exception. Needs a local non-loopback IPv4 address (Configure
        // refuses loopback); without one, the part is reported as skipped.
        IPAddress local = NetworkInterface.GetAllNetworkInterfaces()
            .Where(n => n.OperationalStatus == OperationalStatus.Up && n.NetworkInterfaceType != NetworkInterfaceType.Loopback)
            .SelectMany(n => n.GetIPProperties().UnicastAddresses).Select(a => a.Address)
            .FirstOrDefault(a => a.AddressFamily == AddressFamily.InterNetwork && !IPAddress.IsLoopback(a));
        handshakes = local == null ? "skipped: no local IPv4 address" : Handshakes(hle, local, game);

        // Cleared: back to the default.
        typeof(EmbeddedOnline).GetField("RootsForTests", BindingFlags.NonPublic | BindingFlags.Static).SetValue(null, null);
        EmbeddedOnline.Clear();
        Check(!EmbeddedOnline.Enabled && !InternetOn() && EmbeddedOnline.Redirect(mk8) == null && (bool)blocked.Invoke(null, [mk8]), "cleared");
        Check((long)accountId.GetValue(server0) == 0xcafe + 0x42, "engine account id again");
        Check(EmbeddedOnline.HostFor(server) == null && !EmbeddedOnline.IsServer(server), "nothing kept after a clear");
        // The gate reads the last JSON line.
        Console.WriteLine(JsonSerializer.Serialize(new Dictionary<string, object> { ["result"] = "passed", ["checks"] = checks, ["protocol"] = EmbeddedOnline.Protocol, ["roots"] = published.Count, ["handshakes"] = handshakes }));
        return 0;
    }
}
