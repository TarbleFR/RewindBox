import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

/// Credentials stay in the native Keychain. Launch arguments contain only an
/// opaque, single-use session identifier, never a password or emulator token.
class RetroAchievementsNativeClient {
  RetroAchievementsNativeClient({MethodChannel? channel, bool? available})
    : _channel = channel ?? const MethodChannel('rewindbox/retro_achievements_session'),
      available = available ?? (!kIsWeb && defaultTargetPlatform == TargetPlatform.iOS) {
    if (this.available) _channel.setMethodCallHandler(_onEvent);
  }

  final MethodChannel _channel;
  final bool available;
  void Function(Map<String, Object?>)? onSessionChanged;

  Future<void> _onEvent(MethodCall call) async {
    if (call.method == 'sessionChanged' && call.arguments is Map) {
      onSessionChanged?.call(Map<String, Object?>.from(call.arguments as Map));
    }
  }

  /// Receives one diagnostic line per account read: where the saved sign-in
  /// was found ("keychain", "file" for the private copy, or "none") and the
  /// Keychain status code. Codes only, never account data. Set by the app to
  /// its log.
  static void Function(String message)? diagnostics;

  /// Answer fields that are flags. A native side that boxes a C int
  /// (`@(a != b)`) sends 1/0 instead of true/false; they are read as flags.
  static const _flags = {
    'available', 'authenticated', 'central', 'enabled', 'supported',
    'requested', 'hardcore', 'notifications',
  };

  static Map<String, Object?>? _normalized(Map<String, Object?>? result) {
    if (result == null || !result.keys.any(_flags.contains)) return result;
    return {
      for (final entry in result.entries)
        entry.key: _flags.contains(entry.key) && entry.value is num
            ? entry.value != 0
            : entry.value,
    };
  }

  Future<Map<String, Object?>> invoke(String method, [Map<String, Object?> arguments = const {}]) async {
    if (!available) return const {'available': false};
    final result = _normalized(
      await _channel.invokeMapMethod<String, Object?>(method, arguments),
    );
    if (method == 'account' && result != null && result['storage'] is String) {
      diagnostics?.call('RetroAchievements central account read: '
          'authenticated=${result['authenticated'] == true} storage=${result['storage']} '
          'keychain=${result['keychainStatus'] ?? '-'}');
    }
    return result ?? const {};
  }

  void dispose() {
    if (available) _channel.setMethodCallHandler(null);
    onSessionChanged = null;
  }
}
