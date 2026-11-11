import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_database_service.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/services/xenia_content.dart';
import 'package:path/path.dart' as path;

import 'database_test_helper.dart';

/// Every XeniOS title folder ends in `default.xex`, but the `filename`
/// column is a game's identity (scraped metadata, media, favorites,
/// history): each folder gets its own stable library name
/// (docs/xenios-playlist.md § Folder import).
void main() {
  final dbHelper = DatabaseTestHelper();
  late dynamic db;
  late Directory root;

  const xbox = SystemModel(
    id: 'xbox360',
    realName: 'Microsoft - XBox 360',
    folderName: 'xbox360',
    iconImage: '',
    color: '#000000',
    recursiveScan: true,
  );

  setUp(() async {
    SqliteDatabaseService.xeniaLibraryRulesForTesting = true;
    db = await dbHelper.setUp();
    await db.execute(
      "INSERT INTO app_systems (id, real_name, folder_name) VALUES ('xbox360', 'Microsoft - XBox 360', 'xbox360')",
    );
    for (final extension in ['xex', 'iso', 'zar']) {
      await db.rawInsert(
        'INSERT INTO app_system_extensions (system_id, extension) VALUES (?, ?)',
        ['xbox360', extension],
      );
    }
    await db.rawInsert(
      'INSERT INTO app_system_folders (system_id, folder_name) VALUES (?, ?)',
      ['xbox360', 'xbox360'],
    );
    root = await Directory.systemTemp.createTemp('xenia_names_');
  });

  tearDown(() async {
    SqliteDatabaseService.xeniaLibraryRulesForTesting = false;
    await dbHelper.tearDown();
    if (await root.exists()) await root.delete(recursive: true);
  });

  void file(String relative) {
    final target = File(path.join(root.path, 'xbox360', relative));
    target.parent.createSync(recursive: true);
    target.writeAsStringSync('synthetic');
  }

  Future<Map<String, String>> rows() async {
    final result = await db.rawQuery(
      "SELECT rom_path, filename FROM user_roms WHERE app_system_id = 'xbox360'",
    );
    return <String, String>{
      for (final row in result)
        path.relative(
          row['rom_path'].toString(),
          from: path.join(root.path, 'xbox360'),
        ): row['filename']
            .toString(),
    };
  }

  test(
    'two title folders get two distinct names; ISO and .god keep theirs',
    () async {
      file('Forza/default.xex');
      file('Forza/default_mp.xex');
      file('Halo/default.xex');
      file('Halo 3.iso');
      file('Gears/Gears.god');
      file('Gears/Gears.god.data/Data0000');
      await SqliteDatabaseService.scanSystemRoms(xbox, [root.path]);
      expect(await rows(), <String, String>{
        'Forza/default.xex': 'Forza.xex',
        'Halo/default.xex': 'Halo.xex',
        'Halo 3.iso': 'Halo 3.iso',
        'Gears/Gears.god': 'Gears.god',
      });
    },
  );

  test(
    'a name already taken gets a short path digest, and stays stable',
    () async {
      file('A/Forza/default.xex');
      file('B/Forza/default.xex');
      await SqliteDatabaseService.scanSystemRoms(xbox, [root.path]);
      final first = await rows();
      expect(first['A/Forza/default.xex'], 'Forza.xex');
      expect(
        first['B/Forza/default.xex'],
        matches(RegExp(r'^Forza \[[0-9a-f]{8}\]\.xex$')),
      );
      file('0/Forza/default.xex');
      await SqliteDatabaseService.scanSystemRoms(xbox, [root.path]);
      final second = await rows();
      expect(
        second['A/Forza/default.xex'],
        first['A/Forza/default.xex'],
        reason: 'a stored name never changes on a later scan',
      );
      expect(second['B/Forza/default.xex'], first['B/Forza/default.xex']);
      expect(second.values.toSet(), hasLength(3));
    },
  );

  test(
    'rows stored before as default.xex are renamed once, nothing else',
    () async {
      file('Forza/default.xex');
      file('Halo/default.xex');
      file('Halo 3.iso');
      for (final relative in [
        'Forza/default.xex',
        'Halo/default.xex',
        'Halo 3.iso',
      ]) {
        await db.rawInsert(
          'INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES (?, ?, ?)',
          [
            'xbox360',
            path.basename(relative),
            path.join(root.path, 'xbox360', relative),
          ],
        );
      }
      await SqliteDatabaseService.scanSystemRoms(xbox, [root.path]);
      expect(await rows(), <String, String>{
        'Forza/default.xex': 'Forza.xex',
        'Halo/default.xex': 'Halo.xex',
        'Halo 3.iso': 'Halo 3.iso',
      });
    },
  );

  test('the naming rule alone', () {
    final names = XeniaFolderContent.libraryFileNames(
      <String>['/G/Forza/default.xex', '/G/Forza.xex', '/H/Halo/DEFAULT.XEX'],
      stored: <String, String>{'/g/halo/default.xex': 'Halo (kept).xex'},
    );
    expect(
      names['/G/Forza/default.xex'],
      matches(RegExp(r'^Forza \[[0-9a-f]{8}\]\.xex$')),
      reason: 'a loose Forza.xex file already uses the plain name',
    );
    expect(
      names['/H/Halo/DEFAULT.XEX'],
      'Halo.xex',
      reason: 'the stored row is another path',
    );
    expect(names.containsKey('/G/Forza.xex'), isFalse);
  });
}
