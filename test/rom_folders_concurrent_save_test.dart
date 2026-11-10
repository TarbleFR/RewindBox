import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';

import 'database_test_helper.dart';

/// Build 557: two configuration saves started together interleaved their
/// replacement of user_rom_folders on the shared connection, and the second
/// insert of a path failed (`UNIQUE constraint failed: user_rom_folders.path`,
/// seen in a user's app.log). Each save now runs after the previous one.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;

  setUp(() async {
    db = await helper.setUp();
    // The production table (sqlite_service.dart), not the helper's minimal one.
    await db.execute('DROP TABLE user_rom_folders');
    await db.execute('''
      CREATE TABLE user_rom_folders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        path TEXT NOT NULL UNIQUE COLLATE NOCASE
      )
    ''');
  });
  tearDown(() => helper.tearDown());

  const first = '/var/mobile/Containers/Data/Application/A/Documents/roms';
  const second = '/private/var/mobile/Library/Mobile Documents/Jeux';

  test('concurrent saves of the same folders no longer collide', () async {
    await Future.wait([
      SqliteService.saveUserRomFolders([first, second]),
      SqliteService.saveUserRomFolders([first, second]),
      SqliteService.saveUserRomFolders([first, second]),
    ]);
    expect(await SqliteService.getUserRomFolders(), [first, second]);
  });

  test('concurrent saves keep the last call, in call order', () async {
    await Future.wait([
      SqliteService.saveUserRomFolders([first, second]),
      SqliteService.saveUserRomFolders([first]),
    ]);
    expect(await SqliteService.getUserRomFolders(), [first]);

    await Future.wait([
      SqliteService.saveUserRomFolders([second]),
      SqliteService.saveUserRomFolders([second, first]),
    ]);
    expect(await SqliteService.getUserRomFolders(), [second, first]);
  });

  test('a folder listed twice is stored once', () async {
    await SqliteService.saveUserRomFolders([
      first,
      second,
      first,
      '',
      second.toUpperCase(),
    ]);
    expect(await SqliteService.getUserRomFolders(), [first, second]);
  });

  test('the list is read when the save is called, not when it runs', () async {
    final folders = [first];
    final pending = [
      SqliteService.saveUserRomFolders([second]),
      SqliteService.saveUserRomFolders(folders),
    ];
    folders.add(second);
    await Future.wait(pending);
    expect(await SqliteService.getUserRomFolders(), [first]);
  });

  test('a failed save is reported and the next saves still run', () async {
    await SqliteService.saveUserRomFolders([first]);
    await db.execute(
      '''CREATE TRIGGER reject_root BEFORE INSERT ON user_rom_folders
      WHEN NEW.path LIKE '%/rejected' BEGIN SELECT RAISE(ABORT, 'fixture_write_failure'); END''',
    );
    final failed = SqliteService.saveUserRomFolders(['$first/rejected']);
    final next = SqliteService.saveUserRomFolders([second]);
    await expectLater(
      failed,
      throwsA(predicate((error) => '$error'.contains('fixture_write_failure'))),
    );
    await next;
    expect(await SqliteService.getUserRomFolders(), [second]);
  });
}
