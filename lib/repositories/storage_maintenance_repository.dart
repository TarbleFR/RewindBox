/// Maintenance of the orphan scraped metadata of `data.sqlite`
/// (docs/storage-audit-cleanup.md § 3.6). Only an explicit user action
/// reaches it: preview, then deletion of exactly the previewed keys in one
/// transaction, each key checked again by the same join. Only
/// `user_screenscraper_metadata` is ever written; `user_roms` and every
/// other table are only read. A `VACUUM INTO` copy is made first, outside
/// the transaction, under `Support/NeoStation/Maintenance`.
library;

import 'dart:collection';
import 'dart:io';

import 'package:path/path.dart' as p;

import '../data/datasources/sqlite_service.dart';
import '../services/storage/storage_orphan_detector.dart';
import '../services/storage/storage_roots.dart';

class StorageMetadataDeletion {
  const StorageMetadataDeletion({
    required this.deleted,
    required this.skippedNotOrphan,
    required this.backupPath,
  });

  /// Rows removed from `user_screenscraper_metadata`.
  final int deleted;

  /// Keys left in place: referenced again by `user_roms` (or gone, or the
  /// library empty) when checked inside the transaction.
  final int skippedNotOrphan;

  /// `VACUUM INTO` copy made before the deletion (`''` when no key was
  /// given and no backup was needed).
  final String backupPath;
}

class StorageMaintenanceRepository {
  StorageMaintenanceRepository({
    Future<DatabaseAdapter> Function()? database,
    Future<String> Function()? backupDirectory,
    DateTime Function()? now,
    this.keptBackups = 3,
  }) : _database = database ?? (() => SqliteService.instance.database),
       _backupDirectory = backupDirectory ?? _defaultBackupDirectory,
       _now = now ?? DateTime.now;

  final Future<DatabaseAdapter> Function() _database;
  final Future<String> Function() _backupDirectory;
  final DateTime Function() _now;

  /// `data-*.sqlite` copies kept (the newest ones).
  final int keptBackups;

  String? _lastBackup;

  /// Copy made by the last [backupBeforeDeletion] not yet used by a
  /// deletion.
  String? get lastBackupPath => _lastBackup;

  /// The same join as `storageOrphanMetadataQuery`, for one key.
  static const String _stillOrphan =
      'SELECT 1 FROM user_screenscraper_metadata m '
      'LEFT JOIN user_roms r ON r.app_system_id = m.app_system_id '
      'AND r.filename = m.filename '
      'WHERE m.app_system_id = ? AND m.filename = ? AND r.filename IS NULL '
      'LIMIT 1';

  static const String _delete =
      'DELETE FROM user_screenscraper_metadata '
      'WHERE app_system_id = ? AND filename = ?';

  static Future<String> _defaultBackupDirectory() async => p.join(
    await StorageContainers.applicationSupportPath(),
    StorageLayout.maintenance,
  );

  static Future<bool> _libraryHasGames(DatabaseExecutorAdapter db) async =>
      (await db.rawQuery('SELECT 1 FROM user_roms LIMIT 1')).isNotEmpty;

  /// Orphan keys (§ 3.5 query). Empty while `user_roms` is empty: a library
  /// not scanned yet is not evidence that its metadata is orphan.
  Future<List<StorageOrphanMetadataKey>> previewOrphanMetadata() async {
    final db = await _database();
    if (!await _libraryHasGames(db)) return const [];
    final rows = await db.rawQuery(storageOrphanMetadataQuery);
    return List.unmodifiable([
      for (final row in rows)
        StorageOrphanMetadataKey(
          row['app_system_id'].toString(),
          row['filename'].toString(),
        ),
    ]);
  }

  /// Deletes exactly [keys] (duplicates ignored) in one
  /// `DatabaseAdapter.transaction()`: every key is checked again by the
  /// join and skipped when a game references it again. Any failure rolls
  /// the whole transaction back (nothing removed) and is rethrown. The
  /// backup of [backupBeforeDeletion] is made first when none is pending.
  Future<StorageMetadataDeletion> deleteOrphanMetadata(
    List<StorageOrphanMetadataKey> keys,
  ) async {
    final unique = LinkedHashSet<StorageOrphanMetadataKey>.of(keys);
    if (unique.isEmpty) {
      return StorageMetadataDeletion(
        deleted: 0,
        skippedNotOrphan: 0,
        backupPath: _lastBackup ?? '',
      );
    }
    final backupPath = _lastBackup ?? await backupBeforeDeletion();
    final db = await _database();
    final counts = await db.transaction<(int, int)>((txn) async {
      var deleted = 0;
      var skipped = 0;
      final hasGames = await _libraryHasGames(txn);
      for (final key in unique) {
        if (!hasGames) {
          skipped++;
          continue;
        }
        final orphan = await txn.rawQuery(_stillOrphan, [
          key.appSystemId,
          key.filename,
        ]);
        if (orphan.isEmpty) {
          skipped++;
          continue;
        }
        deleted += await txn.rawDelete(_delete, [
          key.appSystemId,
          key.filename,
        ]);
      }
      return (deleted, skipped);
    });
    // The copy belongs to this deletion; the next one makes its own.
    _lastBackup = null;
    try {
      await walCheckpoint();
    } catch (_) {
      // The rows are committed; the checkpoint is best effort.
    }
    return StorageMetadataDeletion(
      deleted: counts.$1,
      skippedNotOrphan: counts.$2,
      backupPath: backupPath,
    );
  }

  /// `PRAGMA integrity_check`: `ok` when the database is sound.
  Future<String> integrityCheck() async {
    final db = await _database();
    final rows = await db.rawQuery('PRAGMA integrity_check');
    return rows.map((row) => row.values.first.toString()).join('\n');
  }

  /// `PRAGMA wal_checkpoint(TRUNCATE)`.
  Future<void> walCheckpoint() async {
    final db = await _database();
    await db.rawQuery('PRAGMA wal_checkpoint(TRUNCATE)');
  }

  /// `sqlite_version()` (journal of the deletion manager).
  Future<String> sqliteVersion() async {
    final db = await _database();
    final rows = await db.rawQuery('SELECT sqlite_version() AS version');
    return rows.isEmpty ? '' : rows.first['version'].toString();
  }

  /// `VACUUM INTO ?` (bound parameter, outside any transaction) to
  /// `<backupDirectory>/data-<yyyyMMdd-HHmmss>.sqlite` (`-<n>` when two
  /// copies share a second), then keeps the [keptBackups] newest copies:
  /// only this repository's own `data-*.sqlite` regular files are removed.
  Future<String> backupBeforeDeletion() async {
    final directory = await _backupDirectory();
    await Directory(directory).create(recursive: true);
    final stamp = _stamp(_now());
    var target = p.join(directory, 'data-$stamp.sqlite');
    for (
      var index = 2;
      await FileSystemEntity.type(target, followLinks: false) !=
          FileSystemEntityType.notFound;
      index++
    ) {
      target = p.join(directory, 'data-$stamp-$index.sqlite');
    }
    final db = await _database();
    await db.execute('VACUUM INTO ?', [target]);
    _lastBackup = target;
    await _prune(directory, keep: target);
    return target;
  }

  static final RegExp _backupName = RegExp(
    r'^data-(\d{8}-\d{6})(?:-(\d+))?\.sqlite$',
  );

  Future<void> _prune(String directory, {required String keep}) async {
    final backups = <(String, int, String)>[];
    await for (final entity in Directory(directory).list(followLinks: false)) {
      if (entity is! File) continue;
      final match = _backupName.firstMatch(p.basename(entity.path));
      if (match == null) continue;
      backups.add((
        match.group(1)!,
        int.tryParse(match.group(2) ?? '') ?? 1,
        entity.path,
      ));
    }
    backups.sort((a, b) {
      final byStamp = b.$1.compareTo(a.$1);
      return byStamp != 0 ? byStamp : b.$2.compareTo(a.$2);
    });
    for (final old in backups.skip(keptBackups < 1 ? 1 : keptBackups)) {
      if (p.equals(old.$3, keep)) continue;
      if (await FileSystemEntity.type(old.$3, followLinks: false) !=
          FileSystemEntityType.file) {
        continue;
      }
      await File(old.$3).delete();
    }
  }

  static String _stamp(DateTime time) {
    String two(int value) => value.toString().padLeft(2, '0');
    return '${time.year.toString().padLeft(4, '0')}${two(time.month)}${two(time.day)}'
        '-${two(time.hour)}${two(time.minute)}${two(time.second)}';
  }
}
