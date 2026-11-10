import 'dart:async';

import 'package:flutter/services.dart';

/// Why the embedded XeniOS engine can or cannot run on this device and build.
enum XeniaRuntimeState {
  /// iOS 26 or later and XeniaCore.framework with the expected ABI.
  ready,

  /// Not iOS (the bridge has no implementation there).
  unsupportedPlatform,

  /// The device runs iOS 18-25: the Core needs iOS 26.
  requiresIOS26,

  /// This RewindBox build does not include XeniaCore.framework.
  engineMissing,

  /// XeniaCore.framework is there without Apple's Metal Shader Converter
  /// runtime (Frameworks/libmetalirconverter.dylib), which it cannot load or
  /// render without.
  shaderConverterMissing,

  /// The framework is there but exposes another ABI version.
  abiMismatch,
}

class XeniaRuntimeAvailability {
  const XeniaRuntimeAvailability(
    this.state, {
    this.osVersion,
    this.sourceRevision,
    this.detail,
  });

  factory XeniaRuntimeAvailability.fromMap(Map<String, dynamic> map) {
    final name = map['state']?.toString();
    final state = XeniaRuntimeState.values.firstWhere(
      (value) => value.name == name,
      orElse: () => XeniaRuntimeState.engineMissing,
    );
    return XeniaRuntimeAvailability(
      state,
      osVersion: map['osVersion']?.toString(),
      sourceRevision: map['sourceRevision']?.toString(),
      detail: map['detail']?.toString(),
    );
  }

  final XeniaRuntimeState state;
  final String? osVersion;
  final String? sourceRevision;
  final String? detail;

  bool get ready => state == XeniaRuntimeState.ready;
}

/// Flutter side of the in-process XeniOS bridge (`ios/Classes`). Every call
/// degrades to an explicit state: a missing plugin is [engineMissing] on
/// iOS and [unsupportedPlatform] elsewhere, never a fake success.
abstract final class XeniaInternalBridge {
  static const MethodChannel _channel = MethodChannel(
    'rewindbox/xenia_internal',
  );

  static final StreamController<Map<String, dynamic>> _sessionEvents =
      StreamController<Map<String, dynamic>>.broadcast();
  static bool _handlerInstalled = false;

  static void _ensureHandler() {
    if (_handlerInstalled) return;
    _handlerInstalled = true;
    _channel.setMethodCallHandler((call) async {
      if (call.method != 'sessionEvent') return;
      final arguments = call.arguments;
      _sessionEvents.add(
        arguments is Map
            ? Map<String, dynamic>.from(arguments)
            : const <String, dynamic>{'event': 'unknown'},
      );
    });
  }

  /// `event`: launched, firstFrame, paused, resumed, ended (with `reason`),
  /// error (with `error`).
  static Stream<Map<String, dynamic>> get sessionEvents {
    _ensureHandler();
    return _sessionEvents.stream;
  }

  static Future<XeniaRuntimeAvailability> availability({
    required bool isIOS,
  }) async {
    if (!isIOS) {
      return const XeniaRuntimeAvailability(
        XeniaRuntimeState.unsupportedPlatform,
      );
    }
    try {
      final map = await _channel.invokeMapMethod<String, dynamic>(
        'availability',
      );
      return XeniaRuntimeAvailability.fromMap(map ?? const {});
    } on MissingPluginException {
      return const XeniaRuntimeAvailability(XeniaRuntimeState.engineMissing);
    } on PlatformException catch (error) {
      return XeniaRuntimeAvailability(
        XeniaRuntimeState.engineMissing,
        detail: error.message,
      );
    }
  }

  /// Starts a session. The result has `success` and, on failure, `error`
  /// (a stable key) and `detail` (technical).
  static Future<Map<String, dynamic>> launch({
    required String gamePath,
    required int contentKind,
    required String title,
    required Map<String, String> settings,
    required Map<String, String> directories,
  }) async {
    _ensureHandler();
    try {
      final result = await _channel
          .invokeMapMethod<String, dynamic>('launch', <String, Object?>{
            'gamePath': gamePath,
            'contentKind': contentKind,
            'title': title,
            'settings': settings,
            ...directories,
          });
      return Map<String, dynamic>.from(result ?? const {});
    } on MissingPluginException {
      return const <String, dynamic>{
        'success': false,
        'error': 'engineMissing',
      };
    } on PlatformException catch (error) {
      return <String, dynamic>{
        'success': false,
        'error': error.code,
        'detail': error.message,
      };
    }
  }

  static const MethodChannel _jitChannel = MethodChannel(
    'neostation/xenia_jit',
  );

  /// What the next launch needs from the JIT helper, decided by the Core
  /// (`needsTool`, `toolAttached`, `debugged`, `brokerPath`,
  /// `handshakeActive`), or `error` when the Core cannot be loaded.
  static Future<Map<String, dynamic>> jitState() async {
    try {
      final result = await _channel.invokeMapMethod<String, dynamic>(
        'jitState',
      );
      return Map<String, dynamic>.from(result ?? const {});
    } on MissingPluginException {
      return const <String, dynamic>{'error': 'engineMissing'};
    } on PlatformException catch (error) {
      return <String, dynamic>{'error': error.code, 'detail': error.message};
    }
  }

  /// Attaches the dedicated XeniOS JIT helper to RewindBox. With
  /// [requiresCoreHandshake] it stays attached for the Core's own prepare
  /// and detach requests (the launch then waits for its detach); without,
  /// it is a classic attach to finish with [completeJit].
  static Future<Map<String, dynamic>> prepareJit({
    required String pairingFilePath,
    required bool requiresCoreHandshake,
  }) async {
    try {
      final result = await _jitChannel
          .invokeMapMethod<String, dynamic>('prepareJit', <String, Object?>{
            'pairingFilePath': pairingFilePath,
            'requiresCoreHandshake': requiresCoreHandshake,
          });
      return Map<String, dynamic>.from(result ?? const {});
    } on MissingPluginException {
      return const <String, dynamic>{
        'success': false,
        'message': 'engineMissing',
      };
    }
  }

  /// Waits for a classic attach to detach, leaving CS_DEBUGGED.
  static Future<Map<String, dynamic>> completeJit() async {
    try {
      final result = await _jitChannel.invokeMapMethod<String, dynamic>(
        'completeJit',
      );
      return Map<String, dynamic>.from(result ?? const {});
    } on MissingPluginException {
      return const <String, dynamic>{
        'success': false,
        'message': 'engineMissing',
      };
    }
  }

  static Future<bool> isSessionActive() async {
    try {
      return await _channel.invokeMethod<bool>('isSessionActive') ?? false;
    } on MissingPluginException {
      return false;
    }
  }
}
