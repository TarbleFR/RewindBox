import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

/// App-owned journals grouped by actual console, or by service when unknown.
/// Existing engine roots retain player data and legacy journals unchanged.
class DiagnosticsDirectory {
  DiagnosticsDirectory._();

  static const _aliases = <String, String>{
    'switch': 'Switch', 'melonx': 'Switch', 'ryujinx': 'Switch',
    'ps3': 'PS3', 'rpcs3': 'PS3', 'ps2': 'PS2', 'armsx2': 'PS2',
    'ps1': 'PS1', 'psx': 'PS1', 'playstation': 'PS1',
    'psp': 'PSP', 'ppsspp': 'PSP', '3ds': 'Nintendo3DS',
    'n3ds': 'Nintendo3DS', 'nintendo3ds': 'Nintendo3DS', 'azahar': 'Nintendo3DS',
    'ds': 'NintendoDS', 'nds': 'NintendoDS', 'nintendods': 'NintendoDS',
    'gc': 'GameCube', 'gamecube': 'GameCube', 'wii': 'Wii',
    'dolphin': 'Dolphin', 'system': 'System',
  };

  static String systemFolder(String system) {
    final lower = system.toLowerCase();
    return _aliases[lower] ??
        (RegExp(r'^[a-z0-9][a-z0-9_-]{0,47}$').hasMatch(lower)
            ? lower.toUpperCase() : 'System');
  }

  static String _component(String value) {
    if (!RegExp(r'^[A-Za-z0-9][A-Za-z0-9_-]{0,47}$').hasMatch(value)) {
      throw ArgumentError.value(value, 'service', 'Invalid diagnostic component');
    }
    return value;
  }

  static String categoryForFile(String name) {
    final value = path.basename(name).toLowerCase();
    if (value.startsWith('rpcs3')) return 'PS3';
    if (value.startsWith('armsx2')) return 'PS2';
    if (value.startsWith('melonx') || value.startsWith('ryujinx')) return 'Switch';
    if (value.contains('3ds') || value.startsWith('azahar')) return 'Nintendo3DS';
    if (value.startsWith('ppsspp')) return 'PSP';
    if (value.startsWith('dolphin')) return 'Dolphin';
    if (value.startsWith('neoswap')) return 'System/NeoSwap';
    if (value.startsWith('neoplay')) return 'System/NeoPlay';
    if (value.startsWith('controller')) return 'System/Controllers';
    if (value.startsWith('storage')) return 'System/Storage';
    if (value.contains('scraper') || value.startsWith('game-id')) return 'System/Scraper';
    if (value.startsWith('libretro') || value.startsWith('retroarch')) return 'System/Libretro';
    return 'System/Application';
  }

  static Future<Directory> directory({String? system, String? service}) async =>
      directoryIn(await getApplicationDocumentsDirectory(), system: system, service: service);

  static Future<Directory> directoryIn(Directory documents, {String? system, String? service}) async {
    final folder = Directory(path.joinAll([
      documents.path, 'Diagnostics',
      if (system != null) systemFolder(system),
      if (service != null) _component(service),
    ]));
    await folder.create(recursive: true);
    return folder;
  }

  static Future<File> file(String name, {String? system, String? service}) async {
    final basename = path.basename(path.windows.basename(name));
    if (basename.isEmpty || basename == '.' || basename == '..') {
      throw ArgumentError.value(name, 'name', 'Invalid diagnostic filename');
    }
    final inferred = categoryForFile(basename).split('/');
    final folder = await directory(system: system ?? inferred.first,
        service: service ?? (system == null && inferred.length > 1 ? inferred[1] : null));
    return File(path.join(folder.path, basename));
  }

  static const legacyLogRoots = <String, String>{
    'user-data/app.log': 'Application', 'user-data/app.log.old': 'Application',
    'Libretro/Logs': 'Libretro, console recorded within the session',
    'ARMSX2/logs': 'PS2 Core', 'RPCS3': 'PS3 legacy host',
    'NeoPlay.jsonl': 'NeoPlay', 'NeoPlay.jsonl.previous': 'NeoPlay',
    'armsx2_jit_debug.log': 'PS2 JIT',
  };

  /// An index, not a migration: never move or delete a file an old Core owns.
  /// Inspect only app-owned roots, never ROM, savedata or external directories.
  static Future<void> writeIndex(Directory documents) async {
    final root = await directoryIn(documents);
    final legacy = <Map<String, Object>>[];
    for (final entry in legacyLogRoots.entries) {
      legacy.add({'pathFromDocuments': entry.key, 'system': entry.value,
        'present': await FileSystemEntity.type(path.join(documents.path, entry.key), followLinks: false) != FileSystemEntityType.notFound,
        'retainedInPlace': true});
    }
    for (final directory in [documents, root]) {
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is! File) continue;
        final name = path.basename(entity.path), lower = path.basename(entity.path).toLowerCase();
        if (!(lower.endsWith('_debug.txt') || lower.endsWith('-debug.txt') || lower.startsWith('diagnostic-') ||
            RegExp(r'^(rpcs3|armsx2|melonx|dolphin|neoswap|neoplay|libretro|controller)[^/]*\.(log|jsonl)(\.[a-z0-9]+)?$').hasMatch(lower))) continue;
        legacy.add({'pathFromDocuments': path.relative(entity.path, from: documents.path),
          'system': categoryForFile(name), 'present': true, 'retainedInPlace': true});
      }
    }
    final index = <String, Object>{
      'schema': 1, 'pathBase': 'Documents', 'canonicalRoot': 'Diagnostics',
      'canonical': {
        'Switch': ['MeloNX-core.log', 'MeloNX-launch.log', 'MeloNX-performance.log', 'MeloNX-stderr.log'],
        'PS3': ['RPCS3 host, performance, timeline and load diagnostics'],
        'PS2': ['ARMSX2 host and JIT diagnostics'],
        'GameCube/Dolphin': ['per-session Dolphin journals'],
        'Wii/Dolphin': ['per-session Dolphin journals'],
        'Dolphin': ['process-wide Dolphin host journal'],
        '<console>/Libretro': ['session.log', 'previous-session.log', 'unfinished-session.log'],
        'System/Libretro': ['process-wide fatal breadcrumb; console not inferred'],
        'System/Application': ['app.log', 'app.log.old'],
        'System/NeoSwap': ['NeoSwap diagnostics'],
        'System/NeoPlay': ['NeoPlay.jsonl', 'NeoPlay.jsonl.previous'],
        'System/Storage': ['storage journals'], 'System/Controllers': ['controller_battery.log'],
        'System/Scraper': ['scraper diagnostics'],
        'System/RetroArch': ['RetroArch launch and library diagnostics'],
      },
      'legacy': legacy,
      'legacyOtherContainers': [
        {'container': 'ApplicationSupport', 'path': 'NeoStation/Dolphin/Logs', 'system': 'Dolphin', 'retainedInPlace': true},
        {'container': 'ApplicationSupport', 'path': 'NeoStation/RPCS3', 'system': 'PS3', 'retainedInPlace': true},
      ],
      'notes': ['Canonical files are created when their subsystem runs.',
        'Pinned Core internal logs keep engine-owned paths; legacy files are retained, not copied or deleted.',
        'The application journal is a summary; attach the relevant system folder for detailed diagnostics.'],
    };
    final target = File(path.join(root.path, 'index.json'));
    final temporary = File('${target.path}.tmp');
    await temporary.writeAsString('${const JsonEncoder.withIndent('  ').convert(index)}\n', flush: true);
    await temporary.rename(target.path);
  }

  static Future<int> migrateLegacyRootFiles() async {
    await writeIndex(await getApplicationDocumentsDirectory());
    return 0;
  }
}
