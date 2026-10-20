import 'package:flutter/services.dart';

/// Read the presented native session, including pause/menu/teardown. A failed
/// probe is not proof of exit and must never re-enable frontend audio. Only
/// an explicit `false` ends a session: a missing or non-boolean answer is
/// unknown (Build 453's libretro bridge sent the integer 0 or 1, whose
/// `bool` cast threw, and the game's frontend session ended a few seconds
/// after its launch).
abstract final class EmbeddedIOSSessionStatus {
  static const _channels = {
    'ios_melonx_internal': MethodChannel('neostation/melonx_internal'),
    'ios_dolphin_internal': MethodChannel('neostation/dolphin_internal'),
    'ios_rpcs3_internal': MethodChannel('neostation/rpcs3_internal'),
    'ios_libretro_internal': MethodChannel('neostation/libretro_internal'),
  };
  static bool handles(String? name) => _channels.containsKey(name);
  static Future<bool> isActive(String name) async {
    final channel = _channels[name];
    if (channel == null) throw ArgumentError.value(name, 'name');
    try {
      return await channel.invokeMethod<Object?>('isSessionActive') != false;
    } on PlatformException {
      return true;
    } on MissingPluginException {
      return true;
    }
  }
}
