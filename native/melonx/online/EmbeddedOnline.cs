using System;
using System.Collections.Generic;
using System.Net;
using System.Text.Json;

namespace Ryujinx.HLE
{
    /// <summary>
    /// Online play of one session on Nextendo Network (https://nextendo.network), as its developer documentation
    /// describes the client side (https://wiki.nextendo.network/developers, "Connecting an emulator" and
    /// "Authentication end to end"). RewindBox's own code: no Nextendo source is used.
    ///
    /// The host signs the player in (OAuth 2.0 PKCE) and hands this class, before a session is prepared, the game
    /// token of that launch (nx2.…, 24 hours, valid in games only) and the two server addresses. While a
    /// configuration is set:
    ///   - the session has guest network access;
    ///   - the game's online host names resolve to the two addresses (the documented built-in rules);
    ///   - the account id_token carries the game token (claim nnex) and the installed game version (claim tv);
    ///   - a TLS connection to one of the two addresses accepts that service's certificate.
    /// Without a configuration (the default) nothing above applies: the engine behaves exactly as before.
    /// The game token is kept in memory only; it is never logged and never written to a file.
    /// </summary>
    public static class EmbeddedOnline
    {
        private sealed class Settings
        {
            public string NexToken;
            public IPAddress Server;
            public IPAddress Nat;
        }

        private static volatile Settings _settings;
        private static readonly object _resolvedGate = new();
        // The host name last redirected to each server address: the SNI of a TLS connection the game opens by address.
        private static readonly Dictionary<IPAddress, string> _resolved = new();

        public const int MaxTokenLength = 1024;

        // Nextendo's documented redirect rules, in their order: the entries of the second (NAT check) address first.
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

        /// <summary>Whether the next (or current) session plays online.</summary>
        public static bool Enabled => _settings != null;

        /// <summary>Back to offline: what a launch without online play asks for.</summary>
        public static void Clear()
        {
            _settings = null;
            lock (_resolvedGate) _resolved.Clear();
        }

        /// <summary>
        /// Applies the host's request: an empty object clears the configuration; otherwise nexToken, serverAddress and
        /// natAddress are all required. A refused request leaves the engine offline.
        /// </summary>
        public static void Configure(string request)
        {
            Clear();
            if (string.IsNullOrWhiteSpace(request)) return;
            using JsonDocument document = JsonDocument.Parse(request);
            JsonElement root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object) throw new FormatException("Online configuration must be an object.");
            bool any = false;
            foreach (JsonProperty _ in root.EnumerateObject()) { any = true; break; }
            if (!any) return;
            string token = Text(root, "nexToken");
            if (token == null || token.Length > MaxTokenLength || !token.StartsWith("nx2.", StringComparison.Ordinal))
                throw new FormatException("Online configuration: the game token is missing or malformed.");
            foreach (char c in token)
                if (c <= ' ' || c > '~' || c == '"' || c == '\\') throw new FormatException("Online configuration: the game token is malformed.");
            _settings = new Settings
            {
                NexToken = token,
                Server = Address(Text(root, "serverAddress"), "serverAddress"),
                Nat = Address(Text(root, "natAddress"), "natAddress"),
            };
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
        public static IPAddress Redirect(string host)
        {
            Settings settings = _settings;
            if (settings == null || string.IsNullOrEmpty(host)) return null;
            foreach (string pattern in _natHosts)
                if (Matches(pattern, host)) return Note(settings.Nat, host);
            foreach (string pattern in _serverHosts)
                if (Matches(pattern, host)) return Note(settings.Server, host);
            return null;
        }

        private static IPAddress Note(IPAddress address, string host)
        {
            lock (_resolvedGate) _resolved[address] = host;
            return address;
        }

        /// <summary>Whether a TLS peer is one of the two configured servers.</summary>
        public static bool IsServer(IPAddress address)
        {
            Settings settings = _settings;
            if (settings == null || address == null) return false;
            if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
            return address.Equals(settings.Server) || address.Equals(settings.Nat);
        }

        /// <summary>The host name last redirected to a server address, or null.</summary>
        public static string HostFor(IPAddress address)
        {
            if (address == null) return null;
            if (address.IsIPv4MappedToIPv6) address = address.MapToIPv4();
            lock (_resolvedGate) return _resolved.TryGetValue(address, out string host) ? host : null;
        }

        /// <summary>
        /// Adds what Nextendo's game servers read from the account id_token: jti, hm (online membership), tv (the
        /// installed game version) and nnex (the game token). Nothing is added offline.
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

        /// <summary>One leading or inner '*' stands for any run of characters; names compare without case.</summary>
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
