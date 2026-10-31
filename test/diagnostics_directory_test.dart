import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/diagnostics_directory.dart';
import 'package:path/path.dart' as p;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory documents;
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  setUp(() async {
    documents = await Directory.systemTemp.createTemp('diagnostic_routes_');
    messenger.setMockMethodCallHandler(channel, (call) async =>
        call.method == 'getApplicationDocumentsDirectory' ? documents.path : null);
  });

  tearDown(() async {
    messenger.setMockMethodCallHandler(channel, null);
    await documents.delete(recursive: true);
  });

  test('console aliases and unknown systems stay inside Diagnostics', () async {
    const folders = {
      'melonx': 'Switch', 'ryujinx': 'Switch', 'rpcs3': 'PS3',
      'armsx2': 'PS2', 'psx': 'PS1', 'ppsspp': 'PSP',
      'nds': 'NintendoDS', 'azahar': 'Nintendo3DS',
      'gc': 'GameCube', 'wii': 'Wii', 'snes': 'SNES',
      '../../outside': 'System',
    };
    for (final entry in folders.entries) {
      final directory = await DiagnosticsDirectory.directoryIn(
        documents, system: entry.key, service: 'Libretro',
      );
      expect(directory.path,
          p.join(documents.path, 'Diagnostics', entry.value, 'Libretro'));
      expect(await directory.exists(), isTrue);
    }
    await expectLater(
      DiagnosticsDirectory.directoryIn(documents, service: '../outside'),
      throwsArgumentError,
    );
  });

  test('file routes summaries and engine details and strips both separators', () async {
    const files = {
      'app.log': 'System/Application/app.log',
      'rpcs3_startup_debug.txt': 'PS3/rpcs3_startup_debug.txt',
      'MeloNX-performance.log': 'Switch/MeloNX-performance.log',
      'controller_battery.log': 'System/Controllers/controller_battery.log',
      'storage-cleanup-1.jsonl': 'System/Storage/storage-cleanup-1.jsonl',
      'game-id-scraper.log': 'System/Scraper/game-id-scraper.log',
    };
    for (final entry in files.entries) {
      final file = await DiagnosticsDirectory.file(entry.key);
      expect(file.path, p.join(documents.path, 'Diagnostics', entry.value));
    }
    for (final name in ['../../app.log', r'C:\outside\app.log']) {
      expect((await DiagnosticsDirectory.file(name)).path,
          p.join(documents.path, 'Diagnostics/System/Application/app.log'));
    }
    expect((await DiagnosticsDirectory.file('session.log', system: 'psx', service: 'Libretro')).path,
        p.join(documents.path, 'Diagnostics/PS1/Libretro/session.log'));
    await expectLater(DiagnosticsDirectory.file('..'), throwsArgumentError);
  });

  test('legacy indexing is relative, repeatable and never migrates player bytes', () async {
    final originals = <String, List<int>>{};
    for (final relative in [
      'user-data/app.log', 'Libretro/Logs/session.log',
      'ARMSX2/logs/emulog.txt', 'RPCS3/old.log', 'NeoPlay.jsonl',
      'armsx2_jit_debug.log', 'rpcs3_startup_debug.txt',
      'Diagnostics/MeloNX-debug.txt', 'roms/PS3/private_debug.txt',
    ]) {
      final file = File(p.join(documents.path, relative));
      await file.parent.create(recursive: true);
      originals[relative] = [0, 255, ...utf8.encode('unchanged:$relative\n')];
      await file.writeAsBytes(originals[relative]!);
    }
    expect(await DiagnosticsDirectory.migrateLegacyRootFiles(), 0);
    await DiagnosticsDirectory.writeIndex(documents);
    final file = File(p.join(documents.path, 'Diagnostics/index.json'));
    final raw = await file.readAsString();
    final index = jsonDecode(raw) as Map<String, dynamic>;
    expect(index['pathBase'], 'Documents');
    expect(index['canonicalRoot'], 'Diagnostics');
    expect(raw, isNot(contains(documents.path)));
    expect(raw, isNot(contains('unchanged:')));
    expect(raw, isNot(contains('private_debug.txt')));
    final legacy = (index['legacy'] as List).cast<Map<String, dynamic>>();
    for (final entry in legacy) {
      final relative = entry['pathFromDocuments'] as String;
      expect(p.isAbsolute(relative), isFalse);
      expect(p.split(relative), isNot(contains('..')));
      expect(entry['retainedInPlace'], isTrue);
    }
    expect(legacy.any((entry) => entry['pathFromDocuments'] == 'Libretro/Logs' && entry['present'] == true), isTrue);
    expect(legacy.any((entry) => entry['pathFromDocuments'] == 'Diagnostics/MeloNX-debug.txt' && entry['present'] == true), isTrue);
    for (final entry in originals.entries) {
      expect(await File(p.join(documents.path, entry.key)).readAsBytes(), entry.value);
    }
    expect(await File('${file.path}.tmp').exists(), isFalse);
    expect(await File(p.join(documents.path, 'Diagnostics/PS3/rpcs3_startup_debug.txt')).exists(), isFalse);
  });
}
