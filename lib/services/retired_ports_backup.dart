/// Copy of `data.sqlite` made before the former Ports system leaves the
/// database (removal of Dusklight, KartPad and the Ports playlist,
/// docs/ports-removal-2026-10-20.md).
///
/// The bundled system definitions no longer contain `ports`, so the next
/// [SqliteService.syncSystems] prunes its `app_systems` row and, through
/// `ON DELETE CASCADE`, the rows that belong to it: its games in `user_roms`
/// (play time, favorites, last played), their scraped metadata and the
/// playlist settings. No file is touched: games, saves and settings stay
/// under Documents/Ports, where the Files app shows them.
///
/// Before that sync, when the former system still has game or metadata
/// rows, the whole database is copied with `VACUUM INTO` next to the
/// storage maintenance copies (Support/NeoStation/Maintenance, never proposed
/// for deletion) and the copy is checked: `integrity_check` answers `ok` and
/// it holds the same Ports rows. Without a checked copy the sync is
/// postponed, nothing is deleted, and the next start tries again.
library;

import 'dart:io';

import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:path/path.dart' as p;
import 'package:sqlite3/sqlite3.dart' as sqlite;

import '../data/datasources/sqlite_service.dart';
import '../models/system_configuration.dart';
import 'logger_service.dart';
import 'storage/storage_roots.dart';

/// What [RetiredPortsBackup.prepareForSync] decided for the next sync.
enum RetiredPortsSyncDecision {
  /// The sync removes no Ports row with user data: it runs as before.
  notNeeded,

  /// A checked copy exists: the sync may prune the former system.
  backedUp,

  /// No checked copy: the sync must not run now.
  postponed,
}

class RetiredPortsBackup {
  RetiredPortsBackup._();

  /// `folder_name` of the former system (assets/systems/ports.json until
  /// the removal).
  static const String retiredFolderName = 'ports';

  /// `<backup directory>/data-before-ports-removal-<yyyyMMdd-HHmmss>.sqlite`
  /// (`-<n>` when two copies share a second). The storage maintenance
  /// rotation only removes its own `data-<stamp>.sqlite` copies, so these
  /// are kept.
  static final RegExp fileName = RegExp(
    r'^data-before-ports-removal-\d{8}-\d{6}(?:-\d+)?\.sqlite$',
  );

  @visibleForTesting
  static Future<String> Function() backupDirectory = _defaultBackupDirectory;

  @visibleForTesting
  static DateTime Function() now = DateTime.now;

  static Future<String> _defaultBackupDirectory() async => p.join(
    await StorageContainers.applicationSupportPath(),
    StorageLayout.maintenance,
  );

  static final _log = LoggerService.instance;

  /// Called by [SqliteService.loadAndSyncSystems] with the definitions it
  /// is about to sync. [database] defaults to the app's connection.
  static Future<RetiredPortsSyncDecision> prepareForSync(
    List<SystemConfiguration> configurations, {
    sqlite.Database? database,
  }) async {
    // An empty list prunes nothing; a definition still present keeps the row.
    if (configurations.isEmpty ||
        configurations.any(
          (config) =>
              config.system.folderName.toLowerCase() == retiredFolderName,
        )) {
      return RetiredPortsSyncDecision.notNeeded;
    }
    try {
      final db = database ?? (await SqliteService.instance.database).rawDb;
      final ids = [
        for (final row in db.select(
          'SELECT id FROM app_systems WHERE folder_name = ? COLLATE NOCASE',
          [retiredFolderName],
        ))
          row['id'].toString(),
      ];
      if (ids.isEmpty) return RetiredPortsSyncDecision.notNeeded;
      final counts = _personalRows(db, ids);
      if (counts.games == 0 && counts.metadata == 0) {
        return RetiredPortsSyncDecision.notNeeded;
      }
      if (!db.autocommit) {
        _log.w(
          '[RetiredPorts] Sync postponed: a transaction is open, the copy '
          'cannot be made now.',
        );
        return RetiredPortsSyncDecision.postponed;
      }
      final target = await _target();
      db.execute('VACUUM INTO ?', [target]);
      final problem = _check(target, ids, counts);
      if (problem != null) {
        _log.e('[RetiredPorts] Sync postponed: copy $target rejected: $problem');
        try {
          await File(target).delete();
        } catch (_) {}
        return RetiredPortsSyncDecision.postponed;
      }
      _log.i(
        '[RetiredPorts] Database copied to $target before the former Ports '
        'system leaves it (${counts.games} game rows, ${counts.metadata} '
        'metadata rows). Files under Documents/Ports are not touched.',
      );
      return RetiredPortsSyncDecision.backedUp;
    } catch (error, stack) {
      _log.e(
        '[RetiredPorts] Sync postponed: the database copy failed.',
        error: error,
        stackTrace: stack,
      );
      return RetiredPortsSyncDecision.postponed;
    }
  }

  static ({int games, int metadata}) _personalRows(
    sqlite.Database db,
    List<String> ids,
  ) {
    final marks = List.filled(ids.length, '?').join(',');
    int count(String table) =>
        db.select(
              'SELECT COUNT(*) AS n FROM $table WHERE app_system_id IN ($marks)',
              ids,
            ).first['n']
            as int;
    return (
      games: count('user_roms'),
      metadata: count('user_screenscraper_metadata'),
    );
  }

  static Future<String> _target() async {
    final directory = await backupDirectory();
    await Directory(directory).create(recursive: true);
    final time = now();
    String two(int value) => value.toString().padLeft(2, '0');
    final stamp =
        '${time.year.toString().padLeft(4, '0')}${two(time.month)}${two(time.day)}'
        '-${two(time.hour)}${two(time.minute)}${two(time.second)}';
    var target = p.join(directory, 'data-before-ports-removal-$stamp.sqlite');
    for (
      var index = 2;
      await FileSystemEntity.type(target, followLinks: false) !=
          FileSystemEntityType.notFound;
      index++
    ) {
      target = p.join(directory, 'data-before-ports-removal-$stamp-$index.sqlite');
    }
    return target;
  }

  /// Null when the copy at [path] is sound and holds the same Ports rows.
  static String? _check(
    String path,
    List<String> ids,
    ({int games, int metadata}) expected,
  ) {
    final copy = sqlite.sqlite3.open(path, mode: sqlite.OpenMode.readOnly);
    try {
      final integrity = copy
          .select('PRAGMA integrity_check')
          .map((row) => row.values.first.toString())
          .join('\n');
      if (integrity != 'ok') return 'integrity_check: $integrity';
      final found = _personalRows(copy, ids);
      if (found != expected) {
        return 'rows ${found.games}/${found.metadata}, '
            'expected ${expected.games}/${expected.metadata}';
      }
      return null;
    } finally {
      copy.close();
    }
  }
}
