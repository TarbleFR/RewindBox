import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as path;

/// The engine receipts packaged with this installation. A successful read with
/// a missing engine means this build omitted it (for example a partial build).
typedef EmbeddedEngineBuild = ({String name, String version});

abstract final class EmbeddedEngineBuildInfo {
  static final Future<Map<String, EmbeddedEngineBuild>?> engines = _read();

  static Future<Map<String, EmbeddedEngineBuild>?> _read() async {
    if (!Platform.isIOS) return null;
    final bundle = path.dirname(Platform.resolvedExecutable);
    final file = File(path.join(bundle, 'EmulatorBuildMetadata.json'));
    try {
      final manifest = jsonDecode(await file.readAsString());
      if (manifest is! Map || manifest['engines'] is! Map) return null;
      final entries = manifest['engines'] as Map;
      return <String, EmbeddedEngineBuild>{
        for (final entry in entries.entries)
          if (entry.key case final String id)
            if (entry.value case {
              'name': final String name,
              'version': final String version,
            })
              id: (name: name, version: version),
      };
    } on FileSystemException {
      return null;
    } on FormatException {
      return null;
    }
  }
}
