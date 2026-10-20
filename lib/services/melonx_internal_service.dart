import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

/// Nintendo Switch runs only inside NeoStation. No external URL, shortcut,
/// app discovery, or title-only substitution is accepted at this boundary.
abstract final class MelonxInternalService {
  static const channel = MethodChannel('neostation/melonx_internal');
  static const gameExtensions = {'nsp', 'xci', 'nro', 'nso'};

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
  }) async {
    if (!Platform.isIOS || isRetiredLink(gamePath)) {
      return {'success': false, 'error': 'localGameRequired'};
    }
    if (!gameExtensions.contains(path.extension(gamePath).replaceFirst('.', '').toLowerCase()) ||
        !await File(gamePath).exists()) {
      return {'success': false, 'error': 'localGameRequired'};
    }
    final documents = await getApplicationDocumentsDirectory();
    try {
      final response = await channel.invokeMethod<Object?>('launch', {
        'gamePath': gamePath,
        'rootDirectory': path.join(documents.path, 'MeloNX'),
        'locale': locale,
      });
      return response is Map
          ? Map<String, dynamic>.from(response)
          : {'success': false, 'error': 'invalidResponse'};
    } on MissingPluginException {
      return {'success': false, 'error': 'runtimeUnavailable'};
    } on PlatformException catch (error) {
      return {'success': false, 'error': error.code, 'diagnostic': error.message};
    }
  }
}
