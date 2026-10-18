import 'package:flutter/services.dart';

/// Touch-control layouts of the embedded Dolphin, ARMSX2 and RPCS3 engines
/// (Build 484). The layouts themselves are edited natively, over the real
/// controls; this channel reads and changes the per-console preference and
/// opens the editor outside a game.
class NeoTouchLayout {
  NeoTouchLayout._();

  static const channel = MethodChannel('neostation/touch_layout');

  /// Consoles with editable touch controls.
  static const consoles = <String>['gc', 'wii', 'ps2', 'ps3'];

  static Future<NeoTouchLayoutSettings?> settings(String console) async {
    final value = await channel.invokeMapMethod<String, dynamic>(
      'settings',
      {'console': console},
    );
    return value == null ? null : NeoTouchLayoutSettings.fromMap(value);
  }

  static Future<NeoTouchLayoutSettings?> setHideWithController(
    String console,
    bool hide,
  ) async {
    final value = await channel.invokeMapMethod<String, dynamic>(
      'setHideWithController',
      {'console': console, 'hide': hide},
    );
    return value == null ? null : NeoTouchLayoutSettings.fromMap(value);
  }

  /// Opens the native editor of [layout] ("gc", "wii", "wii-classic", "ps2",
  /// "ps3"); completes when it closes. `opened` is false when the engine of
  /// this layout is not available.
  static Future<({bool opened, bool saved})> openEditor(
    String layout,
    String locale,
  ) async {
    final value = await channel.invokeMapMethod<String, dynamic>(
      'openEditor',
      {'layout': layout, 'locale': locale},
    );
    return (
      opened: value?['opened'] == true,
      saved: value?['saved'] == true,
    );
  }
}

class NeoTouchLayoutEntry {
  const NeoTouchLayoutEntry({
    required this.key,
    required this.customized,
    required this.editable,
  });

  final String key;
  final bool customized;
  final bool editable;
}

class NeoTouchLayoutSettings {
  const NeoTouchLayoutSettings({
    required this.console,
    required this.hideWithController,
    required this.controllerConnected,
    required this.layouts,
  });

  factory NeoTouchLayoutSettings.fromMap(Map<String, dynamic> map) {
    final layouts = <NeoTouchLayoutEntry>[];
    final raw = map['layouts'];
    if (raw is List) {
      for (final item in raw) {
        if (item is! Map) continue;
        final key = item['key'];
        if (key is! String) continue;
        layouts.add(
          NeoTouchLayoutEntry(
            key: key,
            customized: item['customized'] == true,
            editable: item['editable'] == true,
          ),
        );
      }
    }
    return NeoTouchLayoutSettings(
      console: map['console'] is String ? map['console'] as String : '',
      // The engines treat a missing preference as on.
      hideWithController: map['hideWithController'] != false,
      controllerConnected: map['controllerConnected'] == true,
      layouts: layouts,
    );
  }

  final String console;
  final bool hideWithController;
  final bool controllerConnected;
  final List<NeoTouchLayoutEntry> layouts;
}
