import 'dart:async';

import 'package:flutter/services.dart';

class Armsx2InternalBridge {
  Armsx2InternalBridge._();

  static const MethodChannel _channel =
      MethodChannel('neostation/armsx2_internal');
  static const MethodChannel _jitChannel =
      MethodChannel('neostation/armsx2_jit');

  static final StreamController<Map<String, dynamic>> _sessionEvents =
      StreamController<Map<String, dynamic>>.broadcast();
  static final StreamController<Map<String, dynamic>> _textureProgress =
      StreamController<Map<String, dynamic>>.broadcast();
  static bool _eventHandlerInstalled = false;

  static void _ensureEventHandler() {
    if (_eventHandlerInstalled) return;
    _eventHandlerInstalled = true;
    _channel.setMethodCallHandler((call) async {
      final arguments = call.arguments;
      // Build 485: progress of an HD texture pack import.
      if (call.method == 'textureProgress') {
        if (arguments is Map) {
          _textureProgress.add(Map<String, dynamic>.from(arguments));
        }
        return;
      }
      if (call.method != 'sessionEnded') return;
      _sessionEvents.add(
        arguments is Map
            ? Map<String, dynamic>.from(arguments)
            : const <String, dynamic>{'reason': 'unknown'},
      );
    });
  }

  static Stream<Map<String, dynamic>> get sessionEvents {
    _ensureEventHandler();
    return _sessionEvents.stream;
  }

  static Future<Map<String, dynamic>> prepareJit({
    required String pairingFilePath,
  }) async => Map<String, dynamic>.from(
        await _jitChannel.invokeMapMethod<String, dynamic>('prepareJit', {
              'pairingFilePath': pairingFilePath,
            }) ??
            const <String, dynamic>{},
      );

  static Future<Map<String, dynamic>> diagnostics() async =>
      Map<String, dynamic>.from(
        await _channel.invokeMapMethod<String, dynamic>('diagnostics') ??
            const <String, dynamic>{},
      );

  static Future<Map<String, dynamic>> launch({
    required int transaction,
    required String gamePath,
    required String dataPath,
    required String biosDirectory,
    String? biosFilename,
    bool bootBios = false,
    String uiLocale = 'en',
  }) async {
    _ensureEventHandler();
    return Map<String, dynamic>.from(
      await _channel.invokeMapMethod<String, dynamic>('launch', {
            'transaction': transaction,
            'gamePath': gamePath,
            'bootBios': bootBios,
            'dataPath': dataPath,
            'biosDirectory': biosDirectory,
            'uiLocale': uiLocale,
            'biosFilename': ?biosFilename,
          }) ??
          const <String, dynamic>{},
    );
  }

  /// Build 485: HD texture packs of a PS2 game, outside any session. Every
  /// call answers a map with "success" and, on failure, an "error" key.
  static Stream<Map<String, dynamic>> get textureProgress {
    _ensureEventHandler();
    return _textureProgress.stream;
  }

  static Future<Map<String, dynamic>> texture(
    String method,
    Map<String, Object?> arguments,
  ) async {
    _ensureEventHandler();
    return Map<String, dynamic>.from(
      await _channel.invokeMapMethod<String, dynamic>(method, arguments) ??
          const <String, dynamic>{'success': false, 'error': 'failed'},
    );
  }

  static Future<Map<String, dynamic>> stop() async =>
      Map<String, dynamic>.from(
        await _channel.invokeMapMethod<String, dynamic>('stop') ??
            const <String, dynamic>{},
      );
}
