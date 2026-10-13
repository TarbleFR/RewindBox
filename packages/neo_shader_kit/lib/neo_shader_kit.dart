import 'package:flutter/services.dart';

/// Dart side of the shared shader kit (`neostation/shader_kit`): storage
/// report and cleanup for NeoStation's maintenance tools. Installing,
/// applying and configuring shaders happens in the in-game menus.
class NeoShaderKit {
  NeoShaderKit._();

  static const MethodChannel _channel = MethodChannel('neostation/shader_kit');

  /// What the shader storage holds, per engine: installed shaders, the
  /// files they use, and what can be removed without touching an installed
  /// shader, a profile or a file still in use:
  /// {"engines": [{"engine", "installed", "installedBytes", "orphanFiles",
  ///   "orphanBytes", "staleDownloads", "staleBytes"}], "previewCacheBytes"}.
  static Future<Map<String, dynamic>> storageReport({required Map<String, String> roots}) async {
    final report = await _channel.invokeMapMethod<String, dynamic>('storageReport', {'roots': roots});
    return report ?? const <String, dynamic>{};
  }

  /// Removes only what [storageReport] lists as removable (orphan files,
  /// interrupted downloads, preview cache); returns the bytes freed.
  static Future<int> cleanCaches({required Map<String, String> roots}) async {
    final freed = await _channel.invokeMethod<int>('cleanCaches', {'roots': roots});
    return freed ?? 0;
  }
}
