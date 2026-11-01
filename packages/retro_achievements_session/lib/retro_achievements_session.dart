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

  Future<Map<String, Object?>> invoke(String method, [Map<String, Object?> arguments = const {}]) async {
    if (!available) return const {'available': false};
    final result = await _channel.invokeMapMethod<String, Object?>(method, arguments);
    return result ?? const {};
  }

  void dispose() {
    if (available) _channel.setMethodCallHandler(null);
    onSessionChanged = null;
  }
}
