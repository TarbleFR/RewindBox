import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

import 'nextendo_servers.dart';

/// What RewindBox needs to reach Nextendo Network as a registered third-party
/// application (https://nextendo.network/developers, public client with PKCE).
///
/// - The client identifier (`nxc_…`) was issued to RewindBox's maintainer by the
///   Nextendo Developers portal (14 November 2026). It is public: a PKCE client
///   has no secret, and the identifier travels in every sign-in address.
/// - The two game-server addresses are found by name (Nextendo's developer, 17
///   November 2026): `nex.nextendo.network` for the game server and
///   `nat.nextendo.network` for the secondary NAT test, looked up when the app
///   starts and before a launch, kept about ten minutes, the last good address
///   kept when a lookup fails ([NextendoServers]). Nothing is written into the
///   build and players never type them.
///
/// Each address comes from a build define when the build has a valid one (a
/// maintainer's test override; the delivery passes none by default), otherwise
/// from its name's last good lookup, otherwise from the maintainer's on-device
/// field (a test before any lookup succeeded). The client identifier comes from
/// the build, the on-device field or the registered application.
class NextendoConfig {
  const NextendoConfig({
    required this.clientId,
    required this.serverAddress,
    required this.natAddress,
    this.clientIdFromBuild = false,
    this.serverFromBuild = false,
    this.natFromBuild = false,
    this.serverResolved = false,
    this.natResolved = false,
  });

  final String clientId;
  final String serverAddress;
  final String natAddress;
  final bool clientIdFromBuild;
  final bool serverFromBuild;
  final bool natFromBuild;

  /// The address is its name's last good lookup ([NextendoServers]).
  final bool serverResolved;
  final bool natResolved;

  /// Both server addresses come from the build or from their names: players see
  /// no technical field.
  bool get serversAutomatic => (serverFromBuild || serverResolved) && (natFromBuild || natResolved);

  /// The account API. Tokens are only ever sent to this origin.
  static const apiBase = 'https://nextendo.network';

  /// RewindBox's public application on the Nextendo Developers portal.
  static const registeredClientId = 'nxc_Qs2TRpZuxz1X';

  /// The redirect the application registers: a loopback address. Nextendo then
  /// accepts any loopback port and path at sign-in and refuses any other
  /// redirect (a custom scheme included), so RewindBox receives the answer on
  /// 127.0.0.1, on a free port, for the duration of the sign-in only.
  static const registeredRedirect = 'http://127.0.0.1/callback';
  static const loopbackPath = '/callback';

  /// Closes the system sign-in sheet once the loopback answer has arrived: the
  /// local page redirects there, and the sheet ends on this scheme. Nothing is
  /// carried by it.
  static const callbackScheme = 'rewindbox-auth';
  static const sheetDone = '$callbackScheme://nextendo/done';

  /// The scopes registered for RewindBox's application on the portal (the
  /// maintainer's list of 14 November 2026). `identity` names the player and
  /// `game.matchmaking` opens the game token; the others (friends, presence,
  /// profile, history, favourite mods) are granted for features to come and
  /// are not read by RewindBox yet.
  static const scopes = 'identity friends presence game.matchmaking profil history mods.favorites';

  static const _buildClientId = String.fromEnvironment('NEXTENDO_CLIENT_ID');
  static const _buildServer = String.fromEnvironment('NEXTENDO_SERVER_IP');
  static const _buildNat = String.fromEnvironment('NEXTENDO_NAT_IP');
  static const _clientIdKey = 'rewindbox.nextendo.clientId';
  static const _serverKey = 'rewindbox.nextendo.serverAddress';
  static const _natKey = 'rewindbox.nextendo.natAddress';

  /// Sign-in needs the client identifier only.
  bool get canSignIn => isClientId(clientId);

  /// Online play also needs both server addresses, and two different ones: the
  /// NAT test compares two vantage points and fails silently on one (2618-0201).
  bool get serversConfigured => isAddress(serverAddress) && isAddress(natAddress) && serverAddress != natAddress;

  /// Why [serversConfigured] is false: `missing` or `same`; null when configured.
  String? get serversIssue => serversConfigured
      ? null
      : (isAddress(serverAddress) && isAddress(natAddress) ? 'same' : 'missing');

  bool get canPlayOnline => canSignIn && serversConfigured;

  static bool isClientId(String value) => RegExp(r'^nxc_[A-Za-z0-9_-]{4,128}$').hasMatch(value);

  /// A literal IPv4 address: the engine answers the game's DNS queries with it
  /// (a host name would have nothing to resolve it), and the Switch resolver
  /// only hands IPv4 addresses to a game.
  static bool isAddress(String value) => NextendoServers.usable(value);

  static Future<NextendoConfig> load([SharedPreferences? preferences]) =>
      resolve(buildClientId: _buildClientId, buildServer: _buildServer, buildNat: _buildNat, preferences: preferences);

  /// [load] with explicit build values (a build define that is empty or
  /// invalid counts as absent).
  static Future<NextendoConfig> resolve({
    required String buildClientId,
    required String buildServer,
    required String buildNat,
    SharedPreferences? preferences,
  }) async {
    final prefs = preferences ?? await SharedPreferences.getInstance();
    final clientFromBuild = isClientId(buildClientId.trim());
    final serverFromBuild = isAddress(buildServer.trim());
    final natFromBuild = isAddress(buildNat.trim());
    final localClientId = prefs.getString(_clientIdKey) ?? '';
    final resolved = NextendoServers.cached(prefs);
    final serverResolved = !serverFromBuild && isAddress(resolved.server);
    final natResolved = !natFromBuild && isAddress(resolved.nat);
    return NextendoConfig(
      clientId: clientFromBuild ? buildClientId.trim() : (localClientId.isEmpty ? registeredClientId : localClientId),
      serverAddress: serverFromBuild
          ? buildServer.trim()
          : (serverResolved ? resolved.server : prefs.getString(_serverKey) ?? ''),
      natAddress: natFromBuild ? buildNat.trim() : (natResolved ? resolved.nat : prefs.getString(_natKey) ?? ''),
      clientIdFromBuild: clientFromBuild,
      serverFromBuild: serverFromBuild,
      natFromBuild: natFromBuild,
      serverResolved: serverResolved,
      natResolved: natResolved,
    );
  }

  /// Keeps on-device values for a build without defines. Each value is either
  /// empty or valid; anything else is refused with its field's name.
  static Future<NextendoConfig> saveLocal({
    required String clientId,
    required String serverAddress,
    required String natAddress,
    SharedPreferences? preferences,
  }) async {
    final values = {_clientIdKey: clientId.trim(), _serverKey: serverAddress.trim(), _natKey: natAddress.trim()};
    if (values[_clientIdKey]!.isNotEmpty && !isClientId(values[_clientIdKey]!)) throw const FormatException('clientId');
    if (values[_serverKey]!.isNotEmpty && !isAddress(values[_serverKey]!)) throw const FormatException('serverAddress');
    if (values[_natKey]!.isNotEmpty && !isAddress(values[_natKey]!)) throw const FormatException('natAddress');
    if (values[_serverKey]!.isNotEmpty && values[_serverKey] == values[_natKey]) throw const FormatException('sameAddresses');
    final prefs = preferences ?? await SharedPreferences.getInstance();
    for (final entry in values.entries) {
      final stored = entry.value.isEmpty ? await prefs.remove(entry.key) : await prefs.setString(entry.key, entry.value);
      if (!stored) throw const FileSystemException('Nextendo configuration could not be saved');
    }
    return load(prefs);
  }
}
