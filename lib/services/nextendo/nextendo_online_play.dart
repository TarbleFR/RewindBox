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
    this.smashDnsAddresses = const [],
    this.nsa,
    this.acceptedVersions = const [],
  });
  final NextendoGameToken token;
  final String serverAddress;
  final String natAddress;
  final List<String> smashDnsAddresses;

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
    if (smashDnsAddresses.length > 1) 'smashDnsAddresses': smashDnsAddresses,
    if (bcatDirectory != null) 'bcatDirectory': bcatDirectory,
    if (nsa != null) 'nsa': nsa,
    if (acceptedVersions.isNotEmpty) 'acceptedVersions': acceptedVersions,
  };
}

/// Decides, at each Switch launch, whether the game starts with online play.
abstract final class NextendoOnlinePlay {
  // Only the actual guest handshake updates this, never the route probes.
  static String? lastSmashTls;

  static const _enabledKey = 'rewindbox.nextendo.onlinePlay';
  static const _retail = ['.nsp', '.xci'];

  /// Animal Crossing: New Horizons receives the account's BAAS user id.
  static const animalCrossingTitleId = '01006f8002326000';

  /// On by default: signing in is the player's request to play online.
  static Future<bool> enabled([SharedPreferences? preferences]) async =>
      (preferences ?? await SharedPreferences.getInstance()).getBool(_enabledKey) ?? true;

  static Future<void> setEnabled(bool value, [SharedPreferences? preferences]) async {
    await (preferences ?? await SharedPreferences.getInstance()).setBool(_enabledKey, value);
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
    void Function(String step, String detail)? onDetail,
    Future<NextendoCatalog?> Function()? catalog,
    Future<String?> Function(String titleId)? bcat,
  }) async {
    final nextendo = service ?? NextendoService.instance;
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
      unawaited(nextendo.markSession(token));
      if (titleId == null && readTitleId != null) {
        try {
          titleId = await readTitleId();
        } on Object {
          // Title-specific data is optional. The game can still use the authenticated account.
        }
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
        smashDnsAddresses: titleId?.toLowerCase() == '01006a800016e000' && settings.serverResolved
            ? await NextendoServers.smashAddresses(settings.serverAddress, settings.natAddress, preferences)
            : const [],
        serverAddress: settings.serverAddress,
        natAddress: settings.natAddress,
        bcatDirectory: extras.bcatDirectory,
        nsa: extras.nsa,
        acceptedVersions: extras.accepted,
      );
    } on NextendoException catch (error) {
      onSkipped?.call(error.code);
      return null;
    } on Object catch (error) {
      onSkipped?.call(error.runtimeType.toString());
      return null;
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
    String? directory;
    try {
      if (bcat != null) {
        directory = await bcat(id);
      } else if (dataRoot != null) {
        directory = await NextendoBcat.prepare(root: dataRoot, titleId: id, onEvent: (event) => onDetail?.call('bcat', event));
      }
    } on Object catch (error) {
      onDetail?.call('bcat', 'failed ${error.runtimeType}');
    }
    String? nsa;
    if (id == animalCrossingTitleId) {
      try {
        nsa = await service.baasUserId(settings);
        onDetail?.call('nsa', nsa == null ? 'missing' : 'present');
      } on Object catch (error) {
        onDetail?.call('nsa', 'failed ${error.runtimeType}');
      }
    }
    return (bcatDirectory: directory, nsa: nsa, accepted: accepted);
  }
}
