import 'dart:async';
import 'dart:io';

import 'package:shared_preferences/shared_preferences.dart';

import 'nextendo_bcat.dart';
import 'nextendo_catalog.dart';
import 'nextendo_config.dart';
import 'nextendo_engine_support.dart';
import 'nextendo_servers.dart';
import 'nextendo_service.dart';

/// What one Switch launch gives the engine to play on Nextendo Network.
class NextendoLaunchOnline {
  const NextendoLaunchOnline({
    required this.token,
    required this.serverAddress,
    required this.natAddress,
    this.bcatDirectory,
    this.gameDnsAddresses = const [],
    this.nexCompatibility = false,
    this.nsa,
    this.acceptedVersions = const [],
  });
  final NextendoGameToken token;
  final String serverAddress;
  final String natAddress;

  /// The answers of the operator's game server name (2 to 4, the configured
  /// address first); the engine keeps the one that takes a TLS handshake.
  final List<String> gameDnsAddresses;

  /// The player's consent, given once by turning online services on: the
  /// engine may accept the legacy private certificate Nextendo's NEX game
  /// servers present, on Nextendo's addresses only, for every NEX title.
  final bool nexCompatibility;

  /// The game's BCAT delivery data on the device ([NextendoBcat]); null when
  /// Nextendo has none for the title.
  final String? bcatDirectory;

  /// The account id Animal Crossing: New Horizons must receive instead of the
  /// PID (`nsa` of `/api/me`); null for every other game.
  final String? nsa;

  /// The exact versions Nextendo's signed catalog accepts for the title (journal).
  final List<String> acceptedVersions;

  /// The engine's request (`configureOnline`). The game token goes to the
  /// engine in memory only; it is never written to a file or a journal. The
  /// PID is the account id the game reads (Nextendo's integration guide).
  Map<String, dynamic> toEngine() => {
    'nexToken': token.token,
    'pid': token.pid,
    'serverAddress': serverAddress,
    'natAddress': natAddress,
    if (gameDnsAddresses.length > 1) 'gameDnsAddresses': gameDnsAddresses,
    if (nexCompatibility) 'nexCompatibility': true,
    if (bcatDirectory != null) 'bcatDirectory': bcatDirectory,
    if (nsa != null) 'nsa': nsa,
    if (acceptedVersions.isNotEmpty) 'acceptedVersions': acceptedVersions,
  };
}

/// Decides, at each Switch launch, whether the game starts with online play.
///
/// The player has one switch, online services. Turning it on is also the
/// consent the game servers need (their legacy private certificate, accepted
/// only on Nextendo's addresses); everything else is automatic at each launch:
/// server addresses by name, the game token, the title's catalog versions, its
/// BCAT data and, for Animal Crossing, the account id.
abstract final class NextendoOnlinePlay {
  // The last real game handshake on a NEX host (any title), kept across app
  // restarts so the Nextendo screen can say a game was refused. Only the
  // guest's own handshake updates it; no token, address or certificate.
  static const _gameTlsKey = 'rewindbox.nextendo.lastGameTls';
  static const _legacySmashTlsKey = 'rewindbox.nextendo.lastSmashTls';
  static String? _lastGameTls;
  static Future<void> _gameTlsWrite = Future<void>.value();
  static String? get lastGameTls => _lastGameTls;
  static set lastGameTls(String? value) {
    if (value == null || !const {'accepted', 'refused', 'compatibility'}.contains(value)) return;
    _lastGameTls = value;
    // Serialize writes so a delayed refusal cannot overwrite a later success.
    _gameTlsWrite = _gameTlsWrite.then((_) async {
      try {
        final prefs = await SharedPreferences.getInstance();
        await prefs.setString(_gameTlsKey, value);
      } on Object {
        // Storage failure must not interrupt the game's diagnostic callback.
      }
    });
  }

  static Future<void> restoreGameTls() async {
    if (_lastGameTls != null) return;
    try {
      final prefs = await SharedPreferences.getInstance();
      final saved = prefs.getString(_gameTlsKey) ?? prefs.getString(_legacySmashTlsKey);
      if (saved == 'accepted' || saved == 'refused' || saved == 'compatibility') {
        // A live handshake received while reading preferences takes priority.
        _lastGameTls ??= saved;
      }
    } on Object {
      // The next guest handshake still updates the in-memory result.
    }
  }

  static const _servicesKey = 'rewindbox.nextendo.onlineServices.v2';
  static const _legacyEnabledKey = 'rewindbox.nextendo.onlinePlay';
  static const _legacySmashConsentKey = 'rewindbox.nextendo.smashPrivateTlsConsent.v1';
  static const _retail = ['.nsp', '.xci'];

  /// Animal Crossing: New Horizons receives the account's BAAS user id.
  static const animalCrossingTitleId = '01006f8002326000';

  /// Whether online services are on. Off until the player turns them on in
  /// the Nextendo screen; an earlier build's SSBU consent with online play
  /// left on counts as turned on.
  static Future<bool> enabled([SharedPreferences? preferences]) async {
    final prefs = preferences ?? await SharedPreferences.getInstance();
    final value = prefs.getBool(_servicesKey);
    if (value != null) return value;
    return (prefs.getBool(_legacySmashConsentKey) ?? false) && (prefs.getBool(_legacyEnabledKey) ?? true);
  }

  static Future<void> setEnabled(bool value, [SharedPreferences? preferences]) async {
    final saved = await (preferences ?? await SharedPreferences.getInstance()).setBool(_servicesKey, value);
    if (!saved) throw StateError('Could not save the online services setting.');
  }

  /// At app start: looks the two server names up for a signed-in player with
  /// online play on, so a first launch finds fresh addresses. Nobody else's
  /// start contacts Nextendo. Never throws.
  static Future<void> prepareAtStartup({NextendoService? service, SharedPreferences? preferences}) async {
    try {
      final settings = await NextendoConfig.load(preferences);
      if (!settings.canSignIn || !await enabled(preferences)) return;
      if (await (service ?? NextendoService.instance).restore(settings) == null) return;
      await NextendoServers.refresh(preferences: preferences);
    } on Object {
      // A launch looks the names up again if needed.
    }
  }

  /// The online configuration of this launch, or null with [reason] reported
  /// through [onSkipped]: the game then starts offline, exactly as before.
  /// A launch is never refused or delayed beyond the token request and, when
  /// the last answer is older than ten minutes, the two name lookups (at most
  /// five seconds; a failure keeps the last good addresses).
  static Future<NextendoLaunchOnline?> forLaunch({
    NextendoService? service,
    NextendoConfig? config,
    SharedPreferences? preferences,
    String? gamePath,
    String? titleId,
    Future<String?> Function()? readTitleId,
    Directory? dataRoot,
    Future<bool> Function()? engineSupported,
    void Function(String reason)? onSkipped,
    void Function(NextendoLaunchOnline)? onAuthenticated,
    void Function(String step, String detail)? onDetail,
    Future<NextendoCatalog?> Function()? catalog,
    Future<String?> Function(String titleId)? bcat,
  }) async {
    final nextendo = service ?? NextendoService.instance;
    NextendoLaunchOnline? ready;
    void remember(NextendoLaunchOnline value) {
      ready = value;
      onAuthenticated?.call(value);
    }
    try {
      var settings = config ?? await NextendoConfig.load(preferences);
      if (!settings.canSignIn) return null; // Nextendo is not set up in this build: say nothing.
      if (await nextendo.restore(settings) == null) return null; // signed out
      if (!await enabled(preferences)) {
        onSkipped?.call('disabled');
        return null;
      }
      // Only a game dump goes online: a homebrew (.nro, .nso) could read the
      // game token from the account service, so it never receives one.
      if (gamePath != null && !_retail.any(gamePath.toLowerCase().endsWith)) {
        onSkipped?.call('homebrew');
        return null;
      }
      // The two server names, looked up again only when their answer is older
      // than ten minutes; a failed lookup keeps the last good addresses.
      if (config == null) {
        await NextendoServers.refresh(preferences: preferences);
        settings = await NextendoConfig.load(preferences);
      }
      if (!settings.serversConfigured) {
        onSkipped?.call(settings.serversIssue == 'same' ? 'serversSame' : 'serversNotConfigured');
        return null;
      }
      final primarySource = settings.serverResolved ? 'dns' : (settings.serverFromBuild ? 'build' : 'manual');
      final natSource = settings.natResolved ? 'dns' : (settings.natFromBuild ? 'build' : 'manual');
      onDetail?.call('servers', 'game=$primarySource nat=$natSource');
      if (!await (engineSupported ?? NextendoEngineSupport.supported)()) {
        onSkipped?.call('engineUnsupported');
        return null;
      }
      final token = await nextendo.gameToken(settings);
      if (token.pid <= 0) {
        onSkipped?.call('pidMissing');
        return null;
      }
      // Every title is handled alike; the operator's other answers go to the
      // engine only when they came from the name lookup.
      final addresses = settings.serverResolved
          ? await NextendoServers.gameAddresses(settings.serverAddress, settings.natAddress, preferences)
          : const <String>[];
      NextendoLaunchOnline authenticated({String? directory}) => NextendoLaunchOnline(
        token: token, serverAddress: settings.serverAddress, natAddress: settings.natAddress,
        gameDnsAddresses: addresses, bcatDirectory: directory, nexCompatibility: true,
      );
      remember(authenticated());
      unawaited(nextendo.markSession(token));
      if (titleId == null && readTitleId != null) {
        try {
          titleId = await readTitleId();
        } on Object {
          // Title-specific data is optional. The game can still use the authenticated account.
        }
      }
      if (onAuthenticated != null) {
        final previous = dataRoot == null || titleId == null ? null : await NextendoBcat.installed(dataRoot, titleId);
        remember(authenticated(directory: previous));
      }
      final extras = await _gameData(
        settings: settings,
        service: nextendo,
        titleId: titleId,
        dataRoot: dataRoot,
        onDetail: onDetail,
        catalog: catalog,
        bcat: bcat,
      );
      return NextendoLaunchOnline(
        token: token,
        gameDnsAddresses: addresses,
        nexCompatibility: true,
        serverAddress: settings.serverAddress,
        natAddress: settings.natAddress,
        bcatDirectory: extras.bcatDirectory,
        nsa: extras.nsa,
        acceptedVersions: extras.accepted,
      );
    } on NextendoException catch (error) {
      if (ready == null) onSkipped?.call(error.code);
      return ready;
    } on Object catch (error) {
      if (ready == null) onSkipped?.call(error.runtimeType.toString());
      return ready;
    }
  }

  /// What this title needs beyond the token, from Nextendo's integration guide:
  /// the versions its signed catalog accepts, its BCAT delivery data, and for
  /// Animal Crossing the account's BAAS user id. Each part is best effort: a
  /// failure leaves that part out and the game still goes online.
  static Future<({String? bcatDirectory, String? nsa, List<String> accepted})> _gameData({
    required NextendoConfig settings,
    required NextendoService service,
    required String? titleId,
    required Directory? dataRoot,
    void Function(String step, String detail)? onDetail,
    Future<NextendoCatalog?> Function()? catalog,
    Future<String?> Function(String titleId)? bcat,
  }) async {
    final id = titleId?.toLowerCase();
    if (id == null || !RegExp(r'^[0-9a-f]{16}$').hasMatch(id)) return (bcatDirectory: null, nsa: null, accepted: const <String>[]);
    var accepted = const <String>[];
    String? directory;
    String? nsa;
    Future<void> loadCatalog() async {
      try {
        final requirement = (await (catalog ?? (() => NextendoCatalogStore.current()))())?.forTitle(id);
        if (requirement == null) {
          onDetail?.call('catalog', 'notListed');
        } else {
          accepted = requirement.accepted;
          onDetail?.call('catalog', '${requirement.enabled ? 'listed' : 'disabled'} ${requirement.accepted.join('|')}'
              '${requirement.needsNplnPatches ? ' npln' : ''}');
        }
      } on Object catch (error) {
        onDetail?.call('catalog', 'unavailable ${error.runtimeType}');
      }
    }
    Future<void> loadBcat() async {
      try {
        if (bcat != null) {
          directory = await bcat(id);
        } else if (dataRoot != null) {
          directory = await NextendoBcat.prepare(root: dataRoot, titleId: id, onEvent: (event) => onDetail?.call('bcat', event));
        }
      } on Object catch (error) {
        onDetail?.call('bcat', 'failed ${error.runtimeType}');
      }
    }
    Future<void> loadAccountId() async {
      if (id == animalCrossingTitleId) {
        try {
          nsa = await service.baasUserId(settings);
          onDetail?.call('nsa', nsa == null ? 'missing' : 'present');
        } on Object catch (error) {
          onDetail?.call('nsa', 'failed ${error.runtimeType}');
        }
      }
    }
    await Future.wait([loadCatalog(), loadBcat(), loadAccountId()]);
    return (bcatDirectory: directory, nsa: nsa, accepted: accepted);
  }
}
