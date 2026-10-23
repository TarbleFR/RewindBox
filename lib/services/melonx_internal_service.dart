import 'dart:io';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:stikjit_bridge/stikjit_bridge.dart';
import 'package:neostation/l10n/pairing_file_locale.dart';

import 'jit_backend_preference_service.dart';
import 'pairing_file_service.dart';
import 'melonx_launch_diagnostics.dart';

import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

/// Nintendo Switch runs only inside RewindBox. No external URL, shortcut,
/// app discovery, or title-only substitution is accepted at this boundary.
abstract final class MelonxInternalService {
  static const channel = MethodChannel('neostation/melonx_internal');
  static const gameExtensions = {'nsp', 'xci', 'nro', 'nso'};
  static const _jit = MethodChannel('neostation/melonx_jit');
  static bool _launching = false;
  static bool _editing = false;
  static bool _diagnosticsInstalled = false;
  static bool nativeQuarantined = false;

  static void _installDiagnostics() {
    if (_diagnosticsInstalled) return;
    _diagnosticsInstalled = true;
    channel.setMethodCallHandler((call) async {
      if (call.method == 'launchDiagnostic' && call.arguments is Map) {
        final event = Map<String, dynamic>.from(call.arguments as Map);
        MelonxLaunchDiagnostics.record(
          event['stage']?.toString() ?? 'native',
          event['status']?.toString() ?? 'unknown',
          event,
        );
      }
    });
  }

  /// Holds the native launch gate while files used by the engine are changed.
  /// Unknown/native-error states fail closed, including a pending JIT launch.
  static Future<T> editLibrary<T>(Future<T> Function() operation) async {
    if (_editing || _launching) throw StateError('libraryBusy');
    _editing = true;
    var acquired = false;
    try {
      acquired =
          await channel.invokeMethod<bool>('beginLibraryMutation') == true;
      if (!acquired) throw StateError('libraryBusy');
      return await operation();
    } finally {
      try {
        if (acquired) await channel.invokeMethod<void>('endLibraryMutation');
      } finally {
        _editing = false;
      }
    }
  }

  static Future<Directory> rootDirectory() async {
    final documents = await getApplicationDocumentsDirectory();
    final root = Directory(path.join(documents.path, 'MeloNX'));
    await root.create(recursive: true);
    return root;
  }

  static Future<Map<String, dynamic>> content(
    String method, {
    String? filePath,
    String? titleId,
  }) async {
    _installDiagnostics();
    final report = await channel.invokeMapMethod<String, dynamic>(method, {
      'path': filePath ?? '',
      if (titleId != null) 'titleId': titleId,
    });
    if (report == null) throw StateError('Missing MeloNX content response');
    if (report['success'] != true)
      throw MelonxContentException(
        report['errorCode']?.toString() ?? 'failed',
        report['diagnostic']?.toString() ?? 'MeloNX content failed',
        nativeType: report['error']?.toString(),
      );
    return report;
  }

  static String _graphicsKey(String gamePath) =>
      'rewindbox.melonx.graphics.${path.normalize(gamePath).split('/Documents/').last}';
  static Future<Map<String, dynamic>> graphicsForGame(String gamePath) async {
    final text = (await SharedPreferences.getInstance()).getString(
      _graphicsKey(gamePath),
    );
    if (text == null) {
      if (!Platform.isIOS) return {};
      final root = await rootDirectory();
      final global = File(path.join(root.path, 'config.json'));
      final configurations = Directory(path.join(root.path, 'config'));
      if (!await global.exists() && !await configurations.exists()) return {};
      final values = <String, dynamic>{};
      if (await global.exists() && await global.length() <= 4 * 1024 * 1024) {
        values.addAll(
          Map<String, dynamic>.from(jsonDecode(await global.readAsString())),
        );
      }
      if (await configurations.exists()) {
        final info = await content('metadata', filePath: gamePath);
        final title = info['titleId']?.toString();
        if (title != null && RegExp(r'^[a-fA-F0-9]{16}$').hasMatch(title)) {
          final file = File(
            path.join(configurations.path, '${title}_config.json'),
          );
          if (await file.exists() && await file.length() <= 4 * 1024 * 1024) {
            values.addAll(
              Map<String, dynamic>.from(jsonDecode(await file.readAsString())),
            );
          }
        }
      }
      return migratedGraphics(values);
    }
    final value = jsonDecode(text);
    return value is Map ? Map<String, dynamic>.from(value) : {};
  }

  static Map<String, dynamic> migratedGraphics(Map<String, dynamic> source) {
    final result = <String, dynamic>{};
    final scale = source['resScale'];
    if (scale is num && scale.isFinite && scale >= 0.5 && scale <= 2)
      result['resolution'] = scale.toDouble();
    if (source['disableShaderCache'] is bool)
      result['shaderCache'] = !(source['disableShaderCache'] as bool);
    if (source['enableAsyncShaderCompilation'] is bool)
      result['asyncShaders'] = source['enableAsyncShaderCompilation'];
    if (source['vSyncMode'] is int &&
        const {0, 1}.contains(source['vSyncMode']))
      result['vsync'] = source['vSyncMode'] == 0;
    else if (source['disableVSync'] is bool)
      result['vsync'] = !(source['disableVSync'] as bool);
    final filter = source['scalingFilter'];
    if (filter is int && filter >= 0 && filter < 4)
      result['filter'] = ['bilinear', 'nearest', 'fsr', 'area'][filter];
    return result;
  }

  static Future<void> saveGraphics(
    String gamePath,
    Map<String, dynamic> settings,
  ) async {
    if (!await (await SharedPreferences.getInstance()).setString(
      _graphicsKey(gamePath),
      jsonEncode(settings),
    )) {
      throw StateError('Graphics configuration could not be saved');
    }
  }

  static Future<bool> runtimeAvailable() async {
    _installDiagnostics();
    try {
      final report = await channel.invokeMethod<Object?>('diagnostics');
      return report is Map && report['available'] == true;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  static bool isRetiredLink(String value) {
    final scheme = Uri.tryParse(value)?.scheme.toLowerCase();
    return scheme == 'melonx' || scheme == 'atariemulator';
  }

  static Future<Map<String, dynamic>?> verifyMemoryAccess() async {
    try {
      final access = await channel.invokeMapMethod<String, dynamic>(
        'memoryEntitlements',
      );
      if (access?['checked'] != true ||
          [
            'allowed',
            'increasedMemoryLimit',
            'extendedRequired',
            'extendedVirtualAddressing',
          ].any((key) => access?[key] is! bool)) {
        return {'success': false, 'error': 'entitlementCheckFailed'};
      }
      if (access?['allowed'] == true &&
          access?['increasedMemoryLimit'] == true &&
          (access?['extendedRequired'] == false ||
              access?['extendedVirtualAddressing'] == true))
        return null;
      return {
        'success': false,
        'error': 'memoryEntitlements',
        'diagnostic': [
          if (access?['increasedMemoryLimit'] != true)
            'com.apple.developer.kernel.increased-memory-limit',
          if (access?['extendedRequired'] == true &&
              access?['extendedVirtualAddressing'] != true)
            'com.apple.developer.kernel.extended-virtual-addressing',
        ].join('\n'),
      };
    } catch (error) {
      return {
        'success': false,
        'error': 'entitlementCheckFailed',
        'stage': 'entitlements',
        'diagnostic': error.toString(),
      };
    }
  }

  static Future<Map<String, dynamic>> launch({
    required String gamePath,
    required String locale,
    BuildContext? context,
  }) async {
    _installDiagnostics();
    final attempt = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
    MelonxLaunchDiagnostics.record('selection', 'begin', {
      'attempt': attempt,
      'gamePath': gamePath,
    });
    final result = await _launch(
      gamePath: gamePath,
      locale: locale,
      context: context,
    );
    if (result['requiresRestart'] == true) nativeQuarantined = true;
    MelonxLaunchDiagnostics.record(
      result['stage']?.toString() ?? 'launchResult',
      result['success'] == true ? 'passed' : 'failed',
      {...result, 'attempt': attempt},
    );
    return result;
  }

  static Future<Map<String, dynamic>> _launch({
    required String gamePath,
    required String locale,
    BuildContext? context,
  }) async {
    if (_launching || _editing) return {'success': false, 'error': 'busy'};
    if (nativeQuarantined)
      return {
        'success': false,
        'error': 'quarantined',
        'stage': 'close',
        'sessionActive': true,
        'requiresRestart': true,
      };
    _launching = true;
    var nativeTransaction = false;
    var launched = false;
    try {
      if (!Platform.isIOS || isRetiredLink(gamePath)) {
        return {'success': false, 'error': 'localGameRequired'};
      }
      MelonxLaunchDiagnostics.record('file', 'begin');
      if (!gameExtensions.contains(
            path.extension(gamePath).replaceFirst('.', '').toLowerCase(),
          ) ||
          !await File(gamePath).exists()) {
        return {'success': false, 'error': 'localGameRequired'};
      }
      final bytes = await File(gamePath).length();
      if (bytes == 0)
        return {
          'success': false,
          'error': 'invalidContent',
          'stage': 'file',
          'diagnostic': 'The local game file is empty.',
        };
      MelonxLaunchDiagnostics.record('file', 'passed', {'bytes': bytes});
      MelonxLaunchDiagnostics.record('entitlements', 'begin');
      final accessFailure = await verifyMemoryAccess();
      if (accessFailure != null) return accessFailure;
      MelonxLaunchDiagnostics.record('entitlements', 'passed');
      MelonxLaunchDiagnostics.record('runtime', 'begin');
      final report = await channel.invokeMapMethod<String, dynamic>(
        'diagnostics',
      );
      if (report?['available'] != true)
        return {
          'success': false,
          'error': 'runtimeUnavailable',
          'diagnostic': report?['diagnostic'],
          'stage': 'runtime',
        };
      MelonxLaunchDiagnostics.record('runtime', 'passed');
      final preflight = await channel.invokeMapMethod<String, dynamic>(
        'launchPreflight',
        {'path': gamePath},
      );
      if (preflight?['success'] != true)
        return {
          ...?preflight,
          'success': false,
          'error': preflight?['errorCode'] ?? 'invalidContent',
          'stage': preflight?['stage'] ?? 'contentPreflight',
        };
      final external = await JitBackendPreferenceService.useStikDebugFallback();
      MelonxLaunchDiagnostics.record('jitHelper', 'begin', {
        'diagnostic': external
            ? 'User-selected external JIT method.'
            : 'User-selected embedded helper with LocalDevVPN route.',
      });
      if (report?['jitArenaReady'] == true) {
        final state = await _jit.invokeMapMethod<String, dynamic>('status');
        if (state?['debugged'] != true)
          return {
            'success': false,
            'error': 'jitUnavailable',
            'stage': 'jitHelper',
            'diagnostic':
                'The RewindBox process no longer has JIT authorization.',
          };
      }
      if (report?['jitArenaReady'] != true && !external) {
        if (!await PairingFileService.hasStoredPairingFile()) {
          final title = context != null && context.mounted
              ? PairingFileLocale.get(context, PairingFileLocale.pickerTitle)
              : null;
          final imported = await PairingFileService.importFromPicker(
            dialogTitle: title,
          );
          if (imported == null)
            return {'success': false, 'error': 'jitPairingCancelled'};
        }
        // Read-only route proof. Neither this service nor the native helper
        // creates a VPN or changes the user's selected JIT method.
        await StikjitBridge.probeLocalDevVpnRoute();
        nativeTransaction = true;
        final jit = await _jit.invokeMapMethod<String, dynamic>('prepareJit', {
          'pairingFilePath': (await PairingFileService.storedFile()).path,
        });
        if (jit?['success'] != true ||
            jit?['helperConnected'] != true ||
            jit?['pidAttached'] != true ||
            jit?['debugged'] != true) {
          return {
            'success': false,
            'error': 'jitUnavailable',
            'diagnostic': jit?['message'],
            'stage': 'jitHelper',
          };
        }
      }
      final response = await channel.invokeMethod<Object?>('launch', {
        'gamePath': gamePath,
        'locale': locale,
        'jitBackend': external ? 'external' : 'builtin',
        'graphics': await graphicsForGame(gamePath),
      });
      final result = response is Map
          ? Map<String, dynamic>.from(response)
          : {'success': false, 'error': 'invalidResponse'};
      if (result['success'] == true &&
          (result['firstMetalFramePresented'] != true ||
              result['jitMappingConfirmed'] != true)) {
        return {
          'success': false,
          'error': 'invalidNativeStart',
          'stage': 'firstFrame',
          'diagnostic':
              'Native success omitted the required first-frame or JIT evidence.',
        };
      }
      launched = result['success'] == true;
      return result;
    } on MissingPluginException {
      return {'success': false, 'error': 'runtimeUnavailable'};
    } on PlatformException catch (error) {
      return {
        'success': false,
        'error': error.code == 'localdevvpn_route_unavailable'
            ? 'jitUnavailable'
            : error.code,
        'diagnostic': error.message,
        'nativeStatus': error.code,
        'stage': 'methodChannel',
      };
    } catch (error) {
      return {
        'success': false,
        'error': 'launchFailed',
        'diagnostic': error.toString(),
      };
    } finally {
      if (nativeTransaction && !launched) {
        try {
          await channel.invokeMethod<Object?>('cancelJit');
        } catch (_) {}
      }
      _launching = false;
    }
  }
}

class MelonxContentException extends StateError {
  MelonxContentException(this.code, super.message, {this.nativeType});
  final String? nativeType;
  final String code;
}
