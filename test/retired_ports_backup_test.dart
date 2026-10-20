// Removal of Dusklight, KartPad and the Ports playlist
// (docs/ports-removal-2026-10-20.md): the bundled systems no longer define
// `ports`, so SqliteService.loadAndSyncSystems prunes its row and, by the
// production foreign keys (ON DELETE CASCADE), the Ports game rows with their
// play time, favorites and scraped metadata. Driven here through the real
// database initialisation (production schema in a temporary file), the real
// bundled system definitions and the real sync: a checked copy of the whole
// database is made first; without one nothing is removed. Game files are
// never touched. Test host only: no iPhone claim.
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/models/system_configuration.dart';
import 'package:neostation/services/json_config_service.dart';
import 'package:neostation/services/retired_ports_backup.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:sqlite3/sqlite3.dart' as sqlite;

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  late Directory scratch;
  late String maintenance;

  setUp(() async {
    scratch = await Directory.systemTemp.createTemp('retired-ports-');
    final userData = Directory(p.join(scratch.path, 'user-data'))..createSync();
    maintenance = p.join(scratch.path, 'Support', 'NeoStation', 'Maintenance');
    SharedPreferences.setMockInitialValues({
      'custom_user_data_path': userData.path,
    });
    binding.defaultBinaryMessenger.setMockMethodCallHandler(paths, (call) async {
      return switch (call.method) {
        'getApplicationDocumentsDirectory' => p.join(scratch.path, 'Documents'),
        'getApplicationSupportDirectory' => p.join(scratch.path, 'Support'),
        _ => p.join(scratch.path, 'tmp'),
      };
    });
    RetiredPortsBackup.now = () => DateTime(2026, 10, 20, 10, 0, 0);
    RetiredPortsBackup.backupDirectory = () async => maintenance;
    await SqliteService.instance.close();
  });

  tearDown(() async {
    await SqliteService.instance.close();
    binding.defaultBinaryMessenger.setMockMethodCallHandler(paths, null);
    RetiredPortsBackup.now = DateTime.now;
    await scratch.delete(recursive: true);
  });

  Future<sqlite.Database> database() async =>
      (await SqliteService.instance.database).rawDb;

  /// The rows an install with Dusklight and KartPad games had before the
  /// update: the former system, two games with play time and a favorite,
  /// their scraped metadata, the playlist in the main menu.
  Future<void> seedFormerPorts({bool games = true}) async {
    final db = await database();
    db.execute(
      "INSERT INTO app_systems (id, real_name, short_name, folder_name) "
      "VALUES ('ports', 'Ports', 'Ports', 'ports')",
    );
    db.execute(
      "INSERT INTO user_detected_systems (app_system_id, actual_folder_name) "
      "VALUES ('ports', 'ports')",
    );
    if (!games) return;
    for (final (name, folder, seconds, favorite) in [
      ('Twilight Princess.iso', 'Dusklight', 7260, 1),
      ('Mario Kart Wii.wbfs', 'KartPad', 1800, 0),
    ]) {
      db.execute(
        'INSERT INTO user_roms (app_system_id, filename, rom_path, play_time, '
        'is_favorite, last_played) VALUES (?, ?, ?, ?, ?, ?)',
        [
          'ports',
          name,
          p.join(scratch.path, 'Documents', 'Ports', folder, 'Games', name),
          seconds,
          favorite,
          '2026-10-18 21:00:00',
        ],
      );
    }
    db.execute(
      'INSERT INTO user_screenscraper_metadata (app_system_id, filename, '
      'real_name) VALUES (?, ?, ?)',
      ['ports', 'Twilight Princess.iso', 'The Legend of Zelda: Twilight Princess'],
    );
  }

  int count(sqlite.Database db, String sql, [List<Object?> args = const []]) =>
      db.select(sql, args).first.values.first as int;

  List<String> copies() => Directory(maintenance).existsSync()
      ? [
          for (final entity in Directory(maintenance).listSync())
            p.basename(entity.path),
        ]
      : const [];

  test('the Ports rows leave data.sqlite only after a checked copy', () async {
    // First start of an older build: the bundled systems, then its Ports
    // playlist with games, and a game of another system.
    await SqliteService.loadAndSyncSystems();
    expect(copies(), isEmpty, reason: 'nothing to copy without Ports rows');
    await seedFormerPorts();
    final db = await database();
    final systems = count(db, 'SELECT COUNT(*) FROM app_systems');
    db.execute(
      "INSERT INTO user_roms (app_system_id, filename, rom_path, play_time) "
      "VALUES ('gc', 'Twilight Princess (GC).iso', '/roms/gc/tp.iso', 600)",
    );
    final game = File(
      p.join(scratch.path, 'Documents', 'Ports', 'Dusklight', 'Games',
          'Twilight Princess.iso'),
    )..createSync(recursive: true);
    game.writeAsBytesSync(List<int>.filled(64, 7));

    // First start of this build.
    final synced = await SqliteService.loadAndSyncSystems();

    expect(synced.map((system) => system.folderName), isNot(contains('ports')));
    expect(count(db, "SELECT COUNT(*) FROM app_systems WHERE folder_name = 'ports'"), 0);
    expect(count(db, "SELECT COUNT(*) FROM user_roms WHERE app_system_id = 'ports'"), 0);
    expect(
      count(db, "SELECT COUNT(*) FROM user_screenscraper_metadata WHERE app_system_id = 'ports'"),
      0,
    );
    expect(count(db, "SELECT COUNT(*) FROM user_detected_systems WHERE app_system_id = 'ports'"), 0);
    expect(count(db, 'SELECT COUNT(*) FROM app_systems'), systems - 1);
    expect(
      count(db, "SELECT play_time FROM user_roms WHERE app_system_id = 'gc'"),
      600,
      reason: 'the other systems keep their games',
    );
    expect(game.lengthSync(), 64, reason: 'no game file is touched');

    expect(copies(), ['data-before-ports-removal-20261020-100000.sqlite']);
    expect(RetiredPortsBackup.fileName.hasMatch(copies().single), isTrue);
    final copy = sqlite.sqlite3.open(
      p.join(maintenance, copies().single),
      mode: sqlite.OpenMode.readOnly,
    );
    addTearDown(copy.close);
    expect(copy.select('PRAGMA integrity_check').single.values.single, 'ok');
    expect(count(copy, "SELECT COUNT(*) FROM app_systems WHERE id = 'ports'"), 1);
    final kept = copy.select(
      "SELECT filename, play_time, is_favorite FROM user_roms "
      "WHERE app_system_id = 'ports' ORDER BY filename",
    );
    expect([for (final row in kept) row.values], [
      ['Mario Kart Wii.wbfs', 1800, 0],
      ['Twilight Princess.iso', 7260, 1],
    ]);
    expect(
      copy.select(
        "SELECT real_name FROM user_screenscraper_metadata WHERE app_system_id = 'ports'",
      ).single.values.single,
      'The Legend of Zelda: Twilight Princess',
    );

    // Later starts: nothing left to copy, no second copy.
    RetiredPortsBackup.now = () => DateTime(2026, 10, 21, 10, 0, 0);
    await SqliteService.loadAndSyncSystems();
    expect(copies(), ['data-before-ports-removal-20261020-100000.sqlite']);
  });

  test('without a checked copy the sync waits and nothing is removed', () async {
    await SqliteService.loadAndSyncSystems();
    await seedFormerPorts();
    final db = await database();
    // The copy cannot be written: its folder is a file.
    File(p.join(scratch.path, 'not-a-folder')).writeAsStringSync('x');
    RetiredPortsBackup.backupDirectory = () async =>
        p.join(scratch.path, 'not-a-folder', 'Maintenance');

    final systems = await SqliteService.loadAndSyncSystems();

    expect(systems, isNotEmpty);
    expect(
      systems.map((system) => system.folderName),
      isNot(contains('ports')),
      reason: 'the playlist leaves the menus even while its rows wait',
    );
    expect(count(db, "SELECT COUNT(*) FROM app_systems WHERE id = 'ports'"), 1);
    expect(count(db, "SELECT COUNT(*) FROM user_roms WHERE app_system_id = 'ports'"), 2);
    expect(
      count(db, "SELECT COUNT(*) FROM user_screenscraper_metadata WHERE app_system_id = 'ports'"),
      1,
    );

    // The next start can write the copy: the rows leave after it.
    RetiredPortsBackup.backupDirectory = () async => maintenance;
    await SqliteService.loadAndSyncSystems();
    expect(count(db, "SELECT COUNT(*) FROM user_roms WHERE app_system_id = 'ports'"), 0);
    expect(copies(), ['data-before-ports-removal-20261020-100000.sqlite']);
  });

  test('a former Ports playlist without games or metadata needs no copy',
      () async {
    await SqliteService.loadAndSyncSystems();
    await seedFormerPorts(games: false);
    final db = await database();

    await SqliteService.loadAndSyncSystems();

    expect(count(db, "SELECT COUNT(*) FROM app_systems WHERE folder_name = 'ports'"), 0);
    expect(copies(), isEmpty);
  });

  test('a copy is never made inside an open transaction', () async {
    await SqliteService.loadAndSyncSystems();
    await seedFormerPorts();
    final db = await database();
    db.execute('BEGIN');
    addTearDown(() {
      if (!db.autocommit) db.execute('ROLLBACK');
    });
    expect(
      await RetiredPortsBackup.prepareForSync(
        const <SystemConfiguration>[],
        database: db,
      ),
      RetiredPortsSyncDecision.notNeeded,
      reason: 'an empty definition list prunes nothing',
    );
    final bundled = await RetiredPortsBackup.prepareForSync(
      await JsonConfigService.instance.loadSystems(),
      database: db,
    );
    expect(bundled, RetiredPortsSyncDecision.postponed);
    expect(copies(), isEmpty);
  });
}
