import 'package:shared_preferences/shared_preferences.dart';

import 'nextendo_config.dart';
import 'nextendo_service.dart';

/// What one Switch launch gives the engine to play on Nextendo Network.
class NextendoLaunchOnline {
  const NextendoLaunchOnline({required this.token, required this.serverAddress, required this.natAddress});
  final NextendoGameToken token;
  final String serverAddress;
  final String natAddress;

  /// The engine's request (`configureOnline`). The game token goes to the
  /// engine in memory only; it is never written to a file or a journal.
  Map<String, dynamic> toEngine() => {
    'nexToken': token.token,
    'serverAddress': serverAddress,
    'natAddress': natAddress,
  };
}

/// Decides, at each Switch launch, whether the game starts with online play.
abstract final class NextendoOnlinePlay {
  static const _enabledKey = 'rewindbox.nextendo.onlinePlay';

  /// On by default: signing in is the player's request to play online.
  static Future<bool> enabled([SharedPreferences? preferences]) async =>
      (preferences ?? await SharedPreferences.getInstance()).getBool(_enabledKey) ?? true;

  static Future<void> setEnabled(bool value, [SharedPreferences? preferences]) async {
    await (preferences ?? await SharedPreferences.getInstance()).setBool(_enabledKey, value);
  }

  /// The online configuration of this launch, or null with [reason] reported
  /// through [onSkipped]: the game then starts offline, exactly as before.
  /// A launch is never refused or delayed beyond the token request.
  static Future<NextendoLaunchOnline?> forLaunch({
    NextendoService? service,
    NextendoConfig? config,
    SharedPreferences? preferences,
    void Function(String reason)? onSkipped,
  }) async {
    final nextendo = service ?? NextendoService.instance;
    try {
      final settings = config ?? await NextendoConfig.load(preferences);
      if (!settings.canSignIn) return null; // Nextendo is not set up in this build: say nothing.
      if (await nextendo.restore(settings) == null) return null; // signed out
      if (!await enabled(preferences)) {
        onSkipped?.call('disabled');
        return null;
      }
      if (!settings.canPlayOnline) {
        onSkipped?.call('serversNotConfigured');
        return null;
      }
      final token = await nextendo.gameToken(settings);
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
