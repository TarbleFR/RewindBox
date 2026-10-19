import 'package:flutter/services.dart';

/// The shared HD textures page of the embedded engines (ARMSX2, Dolphin,
/// PPSSPP and Azahar). The native page does every download, installation and
/// engine-setting change; Dart only opens it with the directories NeoStation
/// gives each engine and, for a game, its file and libretro game key.
class NeoTextureCatalog {
  NeoTextureCatalog._();

  static const _channel = MethodChannel('neostation/texture_catalog');

  /// Opens the page over the app. [options]: system, locale, title, and
  /// either gamePath (+ gameKey for libretro) for a game, or games
  /// ([{path, title, gameKey}]) for a console; plus the engine directories
  /// (dolphinUser, armsx2Data, libretroSaves, libretroConfig).
  /// Returns false when the page could not be shown.
  static Future<bool> open(Map<String, Object?> options) async =>
      await _channel.invokeMethod<bool>('open', options) ?? false;

  /// Catalogue state without network access: state (missing, bundled,
  /// downloaded), pack counts per system, last refresh.
  static Future<Map<String, dynamic>> snapshot() async =>
      Map<String, dynamic>.from(await _channel.invokeMethod<Map>('snapshot') ?? {});
}
