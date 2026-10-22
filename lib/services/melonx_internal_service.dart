import 'dart:io';
import 'dart:convert';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:stikjit_bridge/stikjit_bridge.dart';
import 'package:neostation/l10n/pairing_file_locale.dart';
import 'jit_backend_preference_service.dart';
import 'pairing_file_service.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

/// Nintendo Switch runs only inside RewindBox. No external URL, shortcut,
/// app discovery, or title-only substitution is accepted at this boundary.
abstract final class MelonxInternalService {
  static const channel = MethodChannel('neostation/melonx_internal');
  static const gameExtensions = {'nsp', 'xci', 'nro', 'nso'};
  static const _jit = MethodChannel('neostation/melonx_jit');
  static bool _launching = false;

  static Future<Directory> rootDirectory() async {
    final documents = await getApplicationDocumentsDirectory();
    final root = Directory(path.join(documents.path, 'MeloNX'));
    await root.create(recursive: true);
    return root;
  }

  static Future<Map<String, dynamic>> content(String method, {String? filePath}) async {
    final report = await channel.invokeMapMethod<String, dynamic>(method, {'path': filePath ?? ''});
    if (report == null) throw StateError('Missing MeloNX content response');
    if (report['success'] != true) throw StateError(report['diagnostic']?.toString() ?? 'MeloNX content failed');
    return report;
  }

  static String _graphicsKey(String gamePath) => 'rewindbox.melonx.graphics.${path.basename(gamePath)}';
  static Future<Map<String, dynamic>> graphicsForGame(String gamePath) async {
    final text = (await SharedPreferences.getInstance()).getString(_graphicsKey(gamePath));
    if (text == null) return {};
    final value = jsonDecode(text);
    return value is Map ? Map<String, dynamic>.from(value) : {};
  }
  static Future<void> saveGraphics(String gamePath, Map<String, dynamic> settings) async {
    if (!await (await SharedPreferences.getInstance()).setString(_graphicsKey(gamePath), jsonEncode(settings))) {
      throw StateError('Graphics configuration could not be saved');
    }
  }

  static Future<bool> runtimeAvailable() async {
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

  static Future<Map<String, dynamic>> launch({
    required String gamePath,
    required String locale,
    BuildContext? context,
  }) async {
    if (_launching) return {'success': false, 'error': 'busy'};
    if (!Platform.isIOS || isRetiredLink(gamePath)) {
      return {'success': false, 'error': 'localGameRequired'};
    }
    if (!gameExtensions.contains(path.extension(gamePath).replaceFirst('.', '').toLowerCase()) ||
        !await File(gamePath).exists()) {
      return {'success': false, 'error': 'localGameRequired'};
    }
    _launching = true;
    var nativeTransaction = false;
    var launched = false;
    try {
      final report = await channel.invokeMapMethod<String, dynamic>('diagnostics');
      if (report?['available'] != true) return {'success': false, 'error': 'runtimeUnavailable', 'diagnostic': report?['diagnostic']};
      final external = await JitBackendPreferenceService.useStikDebugFallback();
      if (report?['jitArenaReady'] != true && !external) {
        if (!await PairingFileService.hasStoredPairingFile()) {
          final title = context != null && context.mounted
              ? PairingFileLocale.get(context, PairingFileLocale.pickerTitle)
              : null;
          final imported = await PairingFileService.importFromPicker(dialogTitle: title);
          if (imported == null) return {'success': false, 'error': 'jitPairingCancelled'};
        }
        // Read-only route proof. Neither this service nor the native helper
        // creates a VPN or changes the user's selected JIT method.
        await StikjitBridge.probeLocalDevVpnRoute();
        nativeTransaction = true;
        final jit = await _jit.invokeMapMethod<String, dynamic>('prepareJit', {
          'pairingFilePath': (await PairingFileService.storedFile()).path,
        });
        if (jit?['success'] != true || jit?['helperConnected'] != true ||
            jit?['pidAttached'] != true || jit?['debugged'] != true) {
          return {'success': false, 'error': 'jitUnavailable', 'diagnostic': jit?['message']};
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
      launched = result['success'] == true;
      return result;
    } on MissingPluginException {
      return {'success': false, 'error': 'runtimeUnavailable'};
    } on PlatformException catch (error) {
      return {'success': false, 'error': error.code, 'diagnostic': error.message};
    } catch (error) {
      return {'success': false, 'error': 'launchFailed', 'diagnostic': error.toString()};
    } finally {
      if (nativeTransaction && !launched) {
        try { await channel.invokeMethod<Object?>('cancelJit'); } catch (_) {}
      }
      _launching = false;
    }
  }
}
