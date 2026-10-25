import 'package:shared_preferences/shared_preferences.dart';

import '../data/datasources/sqlite_service.dart';
import 'logger_service.dart';

/// Retires the old alternate-frontend library, without opening or deleting any
/// game, save, firmware, key or external folder. Runs before iOS library reads,
/// so an existing install cannot keep or restore obsolete launch references.
abstract final class MelonxRetiredLibraryCleanup {
  static Future<void>? _pending;

  static Future<void> run() =>
      _pending ??= _run().whenComplete(() => _pending = null);

  static Future<void> _run() async {
    final db = await SqliteService.getDatabase();
    final removed = await db.transaction<int>((txn) async {
      final legacy = await txn.rawQuery('''
        SELECT app_system_id, filename, rom_path FROM user_roms
        WHERE app_system_id IN
          (SELECT id FROM app_systems WHERE lower(folder_name) = 'switch')
        AND (lower(rom_path) LIKE 'melonx:%'
          OR lower(rom_path) LIKE 'atariemulator:%')
      ''');
      for (final row in legacy) {
        await txn.delete(
          'user_roms',
          where: 'app_system_id = ? AND filename = ? AND rom_path = ?',
          whereArgs: [row['app_system_id'], row['filename'], row['rom_path']],
        );
        // A physical game with the same filename still owns this metadata.
        await txn.rawDelete(
          '''
          DELETE FROM user_screenscraper_metadata
          WHERE app_system_id = ? AND filename = ? AND NOT EXISTS
            (SELECT 1 FROM user_roms WHERE app_system_id = ? AND filename = ?)
        ''',
          [
            row['app_system_id'],
            row['filename'],
            row['app_system_id'],
            row['filename'],
          ],
        );
      }
      final oldEmulators = await txn.rawQuery('''
        SELECT system_id, os_id, unique_identifier FROM app_emulators
        WHERE system_id IN
          (SELECT id FROM app_systems WHERE lower(folder_name) = 'switch')
        AND os_id IN (SELECT id FROM app_os WHERE lower(name) = 'ios')
        AND (unique_identifier IS NULL OR unique_identifier != 'switch.ios.melonx_internal')
      ''');
      for (final emulator in oldEmulators) {
        final id = emulator['unique_identifier'];
        final args = [emulator['system_id'], emulator['os_id'], id];
        // Drop a retired choice on real local games; normal routing selects
        // the embedded engine. Their ROM paths and all play data stay intact.
        await txn.rawUpdate('''
          UPDATE user_roms SET app_emulator_unique_id = NULL, app_emulator_os_id = NULL
          WHERE app_system_id = ? AND app_emulator_os_id = ? AND app_emulator_unique_id IS ?
        ''', args);
        await txn.rawDelete('''
          DELETE FROM app_emulators WHERE system_id = ? AND os_id = ? AND unique_identifier IS ?
        ''', args);
        await txn.rawDelete(
          '''
          DELETE FROM user_emulator_config WHERE emulator_unique_id = ?
          AND NOT EXISTS (SELECT 1 FROM app_emulators WHERE unique_identifier = ?)
        ''',
          [id, id],
        );
      }
      return legacy.length;
    });
    final prefs = await SharedPreferences.getInstance();
    if (prefs.containsKey('melonx_library_cache_v1') &&
        !await prefs.remove('melonx_library_cache_v1')) {
      throw StateError('Retired MeloNX library cache could not be removed');
    }
    if (removed > 0) {
      LoggerService.instance.i(
        'MeloNX retirement: removed $removed external library references; local files preserved',
      );
    }
  }
}
