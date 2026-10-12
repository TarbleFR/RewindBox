import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/repositories/storage_maintenance_repository.dart';
import 'package:neostation/services/storage/storage_orphan_detector.dart';
import 'package:path/path.dart' as p;
import 'package:sqlite3/sqlite3.dart' as sqlite;

import 'database_test_helper.dart';

/// Test D of docs/storage-audit-cleanup.md § 6: the previewed keys are
/// deleted in one transaction, a key referenced again is skipped, a failure
/// removes nothing, `user_roms` is never touched, `VACUUM INTO` gives a
/// readable copy whose integrity check is `ok`, three copies are kept.
void main() {
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late Directory backups;
  late DateTime clock;

  setUp(() async {
    db = await helper.setUp();
    backups = await Directory.systemTemp.createTemp(
      "storage_maintenance_O'Brien_",
    );
    clock = DateTime(2026, 10, 12, 10, 10, 10);
    for (final (system, filename) in [
      ('snes', 'Super Mario World.sfc'),
      ('snes', 'Zelda.sfc'),
      ('psx', 'Final Fantasy VII.m3u'),
    ]) {
      await db.execute(
        'INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES (?, ?, ?)',
        [system, filename, '/roms/$system/$filename'],
      );
    }
    for (final (system, filename) in [
      ('snes', 'Super Mario World.sfc'), // referenced
      ('snes', 'Deleted A.sfc'),
      ('snes', 'Deleted B.sfc'),
      ('psx', 'Final Fantasy VII.m3u'), // referenced
      ('psx', 'Deleted C.cue'),
      ('psx', 'Zelda.sfc'), // same name, other system: orphan
    ]) {
      await db.execute(
        'INSERT INTO user_screenscraper_metadata (app_system_id, filename, real_name) VALUES (?, ?, ?)',
        [system, filename, 'Title of $filename'],
      );
    }
  });

  tearDown(() async {
    await helper.tearDown();
    if (await backups.exists()) await backups.delete(recursive: true);
  });

  StorageMaintenanceRepository repository({int kept = 3}) =>
      StorageMaintenanceRepository(
        database: () async => db,
        backupDirectory: () async => backups.path,
        now: () => clock,
        keptBackups: kept,
      );

  Future<List<Map<String, Object?>>> romRows() =>
      db.rawQuery('SELECT * FROM user_roms ORDER BY rom_path');

  Future<Set<StorageOrphanMetadataKey>> metadataKeys() async => {
    for (final row in await db.rawQuery(
      'SELECT app_system_id, filename FROM user_screenscraper_metadata',
    ))
      StorageOrphanMetadataKey(
        row['app_system_id'].toString(),
        row['filename'].toString(),
      ),
  };

  test('preview lists exactly the orphan keys of the LEFT JOIN', () async {
    final keys = await repository().previewOrphanMetadata();
    expect(keys, const [
      StorageOrphanMetadataKey('psx', 'Deleted C.cue'),
      StorageOrphanMetadataKey('psx', 'Zelda.sfc'),
      StorageOrphanMetadataKey('snes', 'Deleted A.sfc'),
      StorageOrphanMetadataKey('snes', 'Deleted B.sfc'),
    ]);
    // Same query as the detector.
    final rows = await db.rawQuery(storageOrphanMetadataQuery);
    expect(
      rows.map(
        (row) => StorageOrphanMetadataKey(
          '${row['app_system_id']}',
          '${row['filename']}',
        ),
      ),
      keys,
    );
  });

  test('preview claims nothing while user_roms is empty', () async {
    await db.execute('DELETE FROM user_roms');
    expect(await repository().previewOrphanMetadata(), isEmpty);
  });

  test(
    'deletes exactly the given keys in one transaction, never user_roms',
    () async {
      final repo = repository();
      final roms = await romRows();
      final backup = await repo.backupBeforeDeletion();
      var commits = 0;
      db.rawDb.commitFilter = () {
        commits++;
        return true;
      };
      final changes = <sqlite.SqliteUpdate>[];
      final subscription = db.rawDb.updatesSync.listen(changes.add);
      addTearDown(() async {
        db.rawDb.commitFilter = null;
        await subscription.cancel();
      });

      final result = await repo.deleteOrphanMetadata(const [
        StorageOrphanMetadataKey('snes', 'Deleted A.sfc'),
        StorageOrphanMetadataKey('psx', 'Zelda.sfc'),
        StorageOrphanMetadataKey('snes', 'Deleted A.sfc'), // duplicate key
      ]);
      expect(result.deleted, 2);
      expect(result.skippedNotOrphan, 0);
      expect(result.backupPath, backup);
      expect(repo.lastBackupPath, isNull);
      expect(commits, 1, reason: 'one transaction');
      expect(changes, hasLength(2));
      for (final change in changes) {
        expect(change.kind, sqlite.SqliteUpdateKind.delete);
        expect(change.tableName, 'user_screenscraper_metadata');
      }
      expect(await metadataKeys(), {
        const StorageOrphanMetadataKey('snes', 'Super Mario World.sfc'),
        const StorageOrphanMetadataKey('snes', 'Deleted B.sfc'),
        const StorageOrphanMetadataKey('psx', 'Final Fantasy VII.m3u'),
        const StorageOrphanMetadataKey('psx', 'Deleted C.cue'),
      });
      expect(await romRows(), roms);
    },
  );

  test('a key referenced again since the preview is skipped', () async {
    final repo = repository();
    final keys = await repo.previewOrphanMetadata();
    // The user rescans: Deleted B.sfc is a game again.
    await db.execute(
      "INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES ('snes', 'Deleted B.sfc', '/roms/snes/Deleted B.sfc')",
    );
    final roms = await romRows();
    final result = await repo.deleteOrphanMetadata(keys);
    expect(result.deleted, 3);
    expect(result.skippedNotOrphan, 1);
    expect(await metadataKeys(), {
      const StorageOrphanMetadataKey('snes', 'Super Mario World.sfc'),
      const StorageOrphanMetadataKey('snes', 'Deleted B.sfc'),
      const StorageOrphanMetadataKey('psx', 'Final Fantasy VII.m3u'),
    });
    expect(await romRows(), roms);
    // A key never previewed is never deleted, a referenced one neither.
    final again = await repo.deleteOrphanMetadata(const [
      StorageOrphanMetadataKey('snes', 'Super Mario World.sfc'),
      StorageOrphanMetadataKey('gba', 'Not there.gba'),
    ]);
    expect(again.deleted, 0);
    expect(again.skippedNotOrphan, 2);
    expect((await metadataKeys()).length, 3);
  });

  test('a simulated failure rolls everything back', () async {
    final repo = repository();
    final roms = await romRows();
    final before = await metadataKeys();
    await db.execute('''
      CREATE TRIGGER storage_simulated_failure BEFORE DELETE ON user_screenscraper_metadata
      WHEN old.filename = 'Deleted B.sfc'
      BEGIN SELECT RAISE(ABORT, 'simulated failure'); END
    ''');
    var rollbacks = 0;
    final subscription = db.rawDb.rollbacks.listen((_) => rollbacks++);
    addTearDown(subscription.cancel);
    await expectLater(
      repo.deleteOrphanMetadata(const [
        StorageOrphanMetadataKey('snes', 'Deleted A.sfc'), // deleted first
        StorageOrphanMetadataKey('snes', 'Deleted B.sfc'), // fails
        StorageOrphanMetadataKey('psx', 'Deleted C.cue'),
      ]),
      throwsA(isA<sqlite.SqliteException>()),
    );
    await Future<void>.delayed(Duration.zero);
    expect(rollbacks, greaterThanOrEqualTo(1));
    expect(db.rawDb.autocommit, isTrue, reason: 'no transaction left open');
    expect(await metadataKeys(), before);
    expect(await romRows(), roms);
    // The backup was made before the transaction and is kept.
    final copies = await backups
        .list()
        .where((entity) => entity.path.endsWith('.sqlite'))
        .toList();
    expect(copies, hasLength(1));
  });

  test(
    'VACUUM INTO gives a readable copy whose integrity check is ok',
    () async {
      final repo = repository();
      final path = await repo.backupBeforeDeletion();
      expect(p.dirname(path), backups.path);
      expect(p.basename(path), 'data-20261012-101010.sqlite');
      expect(repo.lastBackupPath, path);
      final copy = sqlite.sqlite3.open(path, mode: sqlite.OpenMode.readOnly);
      addTearDown(copy.close);
      expect(copy.select('PRAGMA integrity_check').single.values.single, 'ok');
      expect(copy.select('SELECT COUNT(*) AS n FROM user_roms').single['n'], 3);
      expect(
        copy
            .select('SELECT COUNT(*) AS n FROM user_screenscraper_metadata')
            .single['n'],
        6,
      );
      expect(await repo.integrityCheck(), 'ok');
      expect(await repo.sqliteVersion(), matches(RegExp(r'^3\.\d+\.\d+')));
      await repo.walCheckpoint();
    },
  );

  test('a deletion without a pending backup makes its own first', () async {
    final repo = repository();
    final result = await repo.deleteOrphanMetadata(const [
      StorageOrphanMetadataKey('psx', 'Deleted C.cue'),
    ]);
    expect(result.deleted, 1);
    expect(await File(result.backupPath).exists(), isTrue);
    final copy = sqlite.sqlite3.open(
      result.backupPath,
      mode: sqlite.OpenMode.readOnly,
    );
    addTearDown(copy.close);
    // The copy predates the deletion.
    expect(
      copy
          .select(
            "SELECT COUNT(*) AS n FROM user_screenscraper_metadata WHERE filename = 'Deleted C.cue'",
          )
          .single['n'],
      1,
    );
    final nothing = await repo.deleteOrphanMetadata(const []);
    expect(nothing.deleted, 0);
    expect(nothing.backupPath, '');
    expect(await backups.list().length, 1);
  });

  test(
    'three backups are kept, only the repository’s own files are removed',
    () async {
      final repo = repository();
      await File(p.join(backups.path, 'notes.txt')).writeAsString('keep');
      await File(p.join(backups.path, 'data.sqlite')).writeAsString('keep');
      final made = <String>[];
      for (var index = 0; index < 5; index++) {
        clock = DateTime(2026, 10, 12, 10, 10, index);
        made.add(await repo.backupBeforeDeletion());
      }
      // Two backups in the same second.
      made.add(await repo.backupBeforeDeletion());
      expect(p.basename(made.last), 'data-20261012-101004-2.sqlite');
      final names =
          (await backups
                .list()
                .map((entity) => p.basename(entity.path))
                .toList())
            ..sort();
      expect(names, [
        'data-20261012-101003.sqlite',
        'data-20261012-101004-2.sqlite',
        'data-20261012-101004.sqlite',
        'data.sqlite',
        'notes.txt',
      ]);
      final one = repository(kept: 1);
      clock = DateTime(2026, 10, 12, 11);
      final last = await one.backupBeforeDeletion();
      expect(
        (await backups.list().map((entity) => p.basename(entity.path)).toList())
          ..sort(),
        [p.basename(last), 'data.sqlite', 'notes.txt'],
      );
    },
  );

  test('on a WAL database file: backup, deletion and checkpoint', () async {
    final file = p.join(backups.path, 'live', 'data.sqlite');
    await Directory(p.dirname(file)).create(recursive: true);
    final raw = sqlite.sqlite3.open(file);
    addTearDown(raw.close);
    raw.execute('PRAGMA journal_mode=WAL');
    final live = DatabaseAdapter(raw);
    await helper.createMinimalSchema(live);
    await live.execute(
      "INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES ('snes', 'a.sfc', '/a.sfc')",
    );
    await live.execute(
      "INSERT INTO user_screenscraper_metadata (app_system_id, filename) VALUES ('snes', 'gone.sfc')",
    );
    final repo = StorageMaintenanceRepository(
      database: () async => live,
      backupDirectory: () async => p.join(backups.path, 'Maintenance'),
      now: () => clock,
    );
    final keys = await repo.previewOrphanMetadata();
    expect(keys, const [StorageOrphanMetadataKey('snes', 'gone.sfc')]);
    final result = await repo.deleteOrphanMetadata(keys);
    expect(result.deleted, 1);
    expect(
      await File('$file-wal').length(),
      0,
      reason: 'wal_checkpoint(TRUNCATE)',
    );
    final copy = sqlite.sqlite3.open(
      result.backupPath,
      mode: sqlite.OpenMode.readOnly,
    );
    addTearDown(copy.close);
    expect(copy.select('PRAGMA integrity_check').single.values.single, 'ok');
    expect(
      copy
          .select('SELECT filename FROM user_screenscraper_metadata')
          .single['filename'],
      'gone.sfc',
    );
    expect(await repo.integrityCheck(), 'ok');
  });
}
