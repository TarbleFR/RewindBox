import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

/// What RewindBox needs to reach Nextendo Network as a registered third-party
/// application (https://nextendo.network/developers, public client with PKCE).
///
/// - The client identifier (`nxc_…`) is issued to RewindBox's maintainer by the
///   Nextendo Developers portal. It is public: a PKCE client has no secret.
/// - The two game-server addresses are what Nextendo's own builds receive at
///   build time; Nextendo keeps them out of its public source, so RewindBox
///   keeps them out of its repository too and takes them from build defines.
///
/// A build without the defines can still be configured on the device (the
/// maintainer's test path); a build with them ignores the on-device values.
class NextendoConfig {
  const NextendoConfig({required this.clientId, required this.serverAddress, required this.natAddress, required this.fromBuild});

  final String clientId;
  final String serverAddress;
  final String natAddress;

  /// Whether the values come from the build (players cannot change them).
  final bool fromBuild;

  /// The account API. Tokens are only ever sent to this origin.
  static const apiBase = 'https://nextendo.network';

  /// Registered on the Nextendo Developers portal as the application's redirect.
  static const callbackScheme = 'rewindbox-auth';
  static const redirectUri = '$callbackScheme://nextendo/callback';

  /// `identity` is required; `game.matchmaking` opens the game token. Nothing
  /// else is requested: RewindBox reads no friend list and edits no profile.
  static const scopes = 'identity game.matchmaking';

  static const _buildClientId = String.fromEnvironment('NEXTENDO_CLIENT_ID');
  static const _buildServer = String.fromEnvironment('NEXTENDO_SERVER_IP');
  static const _buildNat = String.fromEnvironment('NEXTENDO_NAT_IP');
  static const _clientIdKey = 'rewindbox.nextendo.clientId';
  static const _serverKey = 'rewindbox.nextendo.serverAddress';
  static const _natKey = 'rewindbox.nextendo.natAddress';

  /// Sign-in needs the client identifier only.
  bool get canSignIn => isClientId(clientId);

  /// Online play also needs both server addresses (the NAT check compares two
  /// vantage points, so one address is not enough).
  bool get canPlayOnline => canSignIn && isAddress(serverAddress) && isAddress(natAddress);

  static bool isClientId(String value) => RegExp(r'^nxc_[A-Za-z0-9_-]{4,128}$').hasMatch(value);

  /// A literal IPv4 address: the engine answers the game's DNS queries with it
  /// (a host name would have nothing to resolve it), and the Switch resolver
  /// only hands IPv4 addresses to a game.
  static bool isAddress(String value) {
    final parsed = InternetAddress.tryParse(value);
    return parsed != null &&
        parsed.type == InternetAddressType.IPv4 &&
        !parsed.isLoopback &&
        parsed.address != '0.0.0.0';
  }

  static Future<NextendoConfig> load([SharedPreferences? preferences]) async {
    if (_buildClientId.isNotEmpty) {
      return const NextendoConfig(clientId: _buildClientId, serverAddress: _buildServer, natAddress: _buildNat, fromBuild: true);
    }
    final prefs = preferences ?? await SharedPreferences.getInstance();
    return NextendoConfig(
      clientId: prefs.getString(_clientIdKey) ?? '',
      serverAddress: prefs.getString(_serverKey) ?? '',
      natAddress: prefs.getString(_natKey) ?? '',
      fromBuild: false,
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
    final prefs = preferences ?? await SharedPreferences.getInstance();
    for (final entry in values.entries) {
      final stored = entry.value.isEmpty ? await prefs.remove(entry.key) : await prefs.setString(entry.key, entry.value);
      if (!stored) throw const FileSystemException('Nextendo configuration could not be saved');
    }
    return load(prefs);
  }
}
