import 'package:flutter/services.dart';

/// The shared HD textures page of the embedded engines (ARMSX2, Dolphin,
/// PPSSPP, Azahar, Mupen64Plus-Next, Beetle PSX HW and Mesen). The native page does every download, installation and
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

  /// Lets the page switch a game to another libretro core: when an NES pack is
  /// switched on for a game that starts with Nestopia, the page asks for Mesen
  /// through [select] (gameKey, core id), which records NeoStation's own
  /// per-game engine choice and answers whether it did.
  static void setCoreSelector(Future<bool> Function(String gameKey, String core) select) {
    _channel.setMethodCallHandler((call) async {
      if (call.method != 'selectLibretroCore') throw MissingPluginException(call.method);
      final arguments = call.arguments;
      if (arguments is! Map) return false;
      final gameKey = arguments['gameKey'], core = arguments['core'];
      if (gameKey is! String || core is! String) return false;
      return select(gameKey, core);
    });
  }

  /// Catalogue state without network access: state (missing, bundled,
  /// downloaded), pack counts per system, last refresh.
  static Future<Map<String, dynamic>> snapshot() async =>
      Map<String, dynamic>.from(await _channel.invokeMethod<Map>('snapshot') ?? {});
}
