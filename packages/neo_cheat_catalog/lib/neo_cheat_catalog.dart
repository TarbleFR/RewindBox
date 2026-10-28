import 'dart:io';

import 'package:flutter/services.dart';

import 'src/origin_resolver.dart';

export 'src/origin_resolver.dart' show OriginResolver, OriginIntegrityError;

/// Shared catalogue storage; installing never activates any cheat.
class NeoCheatCatalog {
  NeoCheatCatalog._();

  static const _channel = MethodChannel('neostation/cheat_catalog');
  static const _progress = EventChannel('neostation/cheat_catalog/progress');

  static Stream<Map<String, dynamic>> get progress => _progress
      .receiveBroadcastStream()
      .map((value) => Map<String, dynamic>.from(value as Map));

  /// Lets the native catalogue rebuild packs of the origin publication: it
  /// calls `resolveOriginPack` with a pack's JSON and receives the standard
  /// pack back (OriginResolver). Origin files are cached under [cache].
  /// Call once at startup on iOS; without it, those packs report an error.
  static void enableOriginDownloads(Directory cache) {
    final resolver = OriginResolver(cache: cache);
    _channel.setMethodCallHandler((call) async {
      if (call.method != 'resolveOriginPack') throw MissingPluginException(call.method);
      final pack = call.arguments;
      if (pack is! Uint8List) throw PlatformException(code: 'origin_arguments');
      try {
        return await resolver.resolve(pack);
      } catch (error) {
        throw PlatformException(code: 'origin_failed', message: error.toString());
      }
    });
  }

  static Future<Map<String, dynamic>> load() async =>
      Map<String, dynamic>.from(await _channel.invokeMethod<Map>('load') ?? {});

  /// A partial result retains successful packs and lists failed_packs/errors.
  /// Calling again verifies installed chunks and retries missing data.
  static Future<Map<String, dynamic>> installAll() async =>
      Map<String, dynamic>.from(
        await _channel.invokeMethod<Map>('installAll') ?? {},
      );

  static Future<List<Map<String, dynamic>>> gamesForIdentity(
    Map<String, dynamic> identity,
  ) async => _rows(await _channel.invokeListMethod<dynamic>(
    'gamesForIdentity', {'identity': identity},
  ));

  static Future<List<Map<String, dynamic>>> searchGames(
    String query, {String system = ''}
  ) async => _rows(await _channel.invokeListMethod<dynamic>(
    'searchGames', {'query': query, 'system': system},
  ));

  static Future<List<Map<String, dynamic>>> cheatsForGame(
    Map<String, dynamic> game,
  ) async => _rows(await _channel.invokeListMethod<dynamic>(
    'cheatsForGame', {'game': game},
  ));

  static List<Map<String, dynamic>> _rows(List<dynamic>? rows) =>
      (rows ?? const []).whereType<Map>().map(Map<String, dynamic>.from).toList();
}
