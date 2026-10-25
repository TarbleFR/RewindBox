import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/melonx_retired_library_cleanup.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final helper = DatabaseTestHelper();
  late dynamic db;
  setUp(() async {
    db = await helper.setUp();
    await db.insert('app_systems', {'id': 'switch', 'folder_name': 'switch'});
    await db.insert('app_systems', {'id': 'snes', 'folder_name': 'snes'});
    await db.insert('app_os', {'id': 1, 'name': 'ios'});
    await db.insert('app_os', {'id': 2, 'name': 'windows'});
  });
  tearDown(helper.tearDown);

  test(
    'upgrade removes old URLs, cache and iOS choices while preserving local games and other platforms',
    () async {
      final temp = await Directory.systemTemp.createTemp('melonx-retirement-');
      addTearDown(() => temp.delete(recursive: true));
      final local = await File(
        '${temp.path}/Mario.nsp',
      ).writeAsString('personal game');
      final save = await File('${temp.path}/save').writeAsString('save');
      for (final row in [
        {
          'filename': 'Mario.nsp',
          'rom_path': 'melonx://game?id=010028600ebda000',
        },
        {'filename': 'Old', 'rom_path': 'MELONX://game?id=010015100b514000'},
        {
          'filename': 'Older',
          'rom_path': 'atariemulator://game?id=01006a800016e000',
        },
        {'filename': 'Malformed', 'rom_path': 'melonx:game?id=1'},
      ]) {
        await db.insert('user_roms', {...row, 'app_system_id': 'switch'});
      }
      await db.insert('app_emulators', {
        'system_id': 'switch',
        'os_id': 1,
        'unique_identifier': 'switch.ios.melonx',
      });
      await db.insert('app_emulators', {
        'system_id': 'switch',
        'os_id': 1,
        'unique_identifier': 'switch.ios.melonx_internal',
      });
      await db.insert('app_emulators', {
        'system_id': 'switch',
        'os_id': 2,
        'unique_identifier': 'switch.windows.ryujinx',
      });
      await db.insert('user_emulator_config', {
        'emulator_unique_id': 'switch.ios.melonx',
        'emulator_path': 'melonx://',
      });
      await db.insert('user_emulator_config', {
        'emulator_unique_id': 'switch.windows.ryujinx',
        'emulator_path': 'C:/Ryujinx',
      });
      await db.insert('user_roms', {
        'filename': 'Mario.nsp',
        'rom_path': local.path,
        'app_system_id': 'switch',
        'is_favorite': 1,
        'play_time': 123,
        'app_emulator_unique_id': 'switch.ios.melonx',
        'app_emulator_os_id': 1,
      });
      await db.insert('user_roms', {
        'filename': 'Other.sfc',
        'rom_path': '/personal/Other.sfc',
        'app_system_id': 'snes',
      });
      await db.insert('user_screenscraper_metadata', {
        'app_system_id': 'switch',
        'filename': 'Mario.nsp',
        'title': 'Personal metadata',
      });
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString(
        'melonx_library_cache_v1',
        '{"old":"melonx://game"}',
      );
      await prefs.setString(
        'rewindbox.melonx.gameFolders',
        'keep linked local folders',
      );
      await MelonxRetiredLibraryCleanup.run();
      final rows = await db.query('user_roms');
      expect(rows, hasLength(2));
      final game = rows.firstWhere((row) => row['app_system_id'] == 'switch');
      expect(game['rom_path'], local.path);
      expect(game['is_favorite'], 1);
      expect(game['play_time'], 123);
      expect(game['app_emulator_unique_id'], isNull);
      expect(game['app_emulator_os_id'], isNull);
      expect(await db.query('user_screenscraper_metadata'), hasLength(1));
      expect(
        (await db.query(
          'app_emulators',
        )).map((row) => row['unique_identifier']),
        containsAll(['switch.ios.melonx_internal', 'switch.windows.ryujinx']),
      );
      expect(await db.query('app_emulators'), hasLength(2));
      expect(await db.query('user_emulator_config'), hasLength(1));
      expect(prefs.containsKey('melonx_library_cache_v1'), false);
      expect(
        prefs.getString('rewindbox.melonx.gameFolders'),
        'keep linked local folders',
      );
      expect(await local.readAsString(), 'personal game');
      expect(await save.readAsString(), 'save');
      await MelonxRetiredLibraryCleanup.run();
      expect(await db.query('user_roms'), rows);
    },
  );

  test('a later obsolete import cannot bring back an external link', () async {
    for (var i = 0; i < 2; i++) {
      await db.insert('user_roms', {
        'filename': 'Legacy',
        'rom_path': 'melonx://game?id=1',
        'app_system_id': 'switch',
      });
      await Future.wait([
        MelonxRetiredLibraryCleanup.run(),
        MelonxRetiredLibraryCleanup.run(),
      ]);
      expect(await db.query('user_roms'), isEmpty);
    }
  });

  test(
    'a database error rolls back cleanup and leaves the old cache for a retry',
    () async {
      await db.insert('user_roms', {
        'filename': 'Legacy',
        'rom_path': 'melonx://game?id=1',
        'app_system_id': 'switch',
      });
      await db.execute(
        "CREATE TRIGGER deny_cleanup BEFORE DELETE ON user_roms BEGIN SELECT RAISE(ABORT, 'denied'); END",
      );
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('melonx_library_cache_v1', 'old export');
      await expectLater(MelonxRetiredLibraryCleanup.run(), throwsA(anything));
      expect(await db.query('user_roms'), hasLength(1));
      expect(prefs.getString('melonx_library_cache_v1'), 'old export');
      await db.execute('DROP TRIGGER deny_cleanup');
      await MelonxRetiredLibraryCleanup.run();
      expect(await db.query('user_roms'), isEmpty);
    },
  );
}
