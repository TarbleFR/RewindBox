import 'package:flutter/services.dart';

/// Shared catalogue storage; installing never activates any cheat.
class NeoCheatCatalog {
  NeoCheatCatalog._();

  static const _channel = MethodChannel('neostation/cheat_catalog');
  static const _progress = EventChannel('neostation/cheat_catalog/progress');

  static Stream<Map<String, dynamic>> get progress => _progress
      .receiveBroadcastStream()
      .map((value) => Map<String, dynamic>.from(value as Map));

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
