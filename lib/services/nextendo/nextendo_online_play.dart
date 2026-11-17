import 'package:shared_preferences/shared_preferences.dart';

import 'nextendo_config.dart';
import 'nextendo_engine_support.dart';
import 'nextendo_servers.dart';
import 'nextendo_service.dart';

/// What one Switch launch gives the engine to play on Nextendo Network.
class NextendoLaunchOnline {
  const NextendoLaunchOnline({required this.token, required this.serverAddress, required this.natAddress});
  final NextendoGameToken token;
  final String serverAddress;
  final String natAddress;

  /// The engine's request (`configureOnline`). The game token goes to the
  /// engine in memory only; it is never written to a file or a journal. The
  /// PID is the account id the game reads (Nextendo's integration guide).
  Map<String, dynamic> toEngine() => {
    'nexToken': token.token,
    'pid': token.pid,
    'serverAddress': serverAddress,
    'natAddress': natAddress,
  };
}

/// Decides, at each Switch launch, whether the game starts with online play.
abstract final class NextendoOnlinePlay {
  static const _enabledKey = 'rewindbox.nextendo.onlinePlay';
  static const _retail = ['.nsp', '.xci'];

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
    Future<bool> Function()? engineSupported,
    void Function(String reason)? onSkipped,
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
      if (!await (engineSupported ?? NextendoEngineSupport.supported)()) {
        onSkipped?.call('engineUnsupported');
        return null;
      }
      final token = await nextendo.gameToken(settings);
      if (token.pid <= 0) {
        onSkipped?.call('pidMissing');
        return null;
      }
      return NextendoLaunchOnline(token: token, serverAddress: settings.serverAddress, natAddress: settings.natAddress);
    } on NextendoException catch (error) {
      onSkipped?.call(error.code);
      return null;
    } on Object catch (error) {
      onSkipped?.call(error.runtimeType.toString());
      return null;
    }
  }
}
