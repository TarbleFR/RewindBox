import 'package:external_folder_access/external_folder_access.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import '../data/datasources/sqlite_service.dart';
import '../providers/sqlite_config_provider.dart';
import '../repositories/system_repository.dart';
import 'melonx_internal_service.dart';

/// Incremental Switch discovery. Never copies ROMs or deletes missing entries.
/// File hashes identify moves; a metadata-only match is deliberately refused.
abstract final class MelonxLibraryScanner {
  static Future<int>? _pending;
  static Future<int> refresh(SqliteConfigProvider config) =>
      _pending ??= _refresh(config).whenComplete(() => _pending = null);

  static Future<String> fingerprint(File file) async =>
      (await sha256.bind(file.openRead()).first).toString();

  static Future<int> _refresh(SqliteConfigProvider config) async {
    final root = await MelonxInternalService.rootDirectory();
    final system = await SystemRepository.getSystemByFolderName('switch');
    if (system?.id == null) return 0;
    final cache = File(p.join(root.path, 'cache', 'rewindbox-library.json'));
    Map<String, dynamic> index = {};
    try {
      index = Map<String, dynamic>.from(jsonDecode(await cache.readAsString()));
    } on FileSystemException {
      /* first scan */
    } on FormatException {
      /* rebuild a damaged, non-authoritative cache */
    }
    final keyParts = <String>[];
    for (final name in ['prod.keys', 'title.keys']) {
      final stat = await File(p.join(root.path, 'system', name)).stat();
      keyParts.add(
        '$name:${stat.size}:${stat.modified.microsecondsSinceEpoch}',
      );
    }
    final keyStamp = keyParts.join('|');
    final db = await SqliteService.getDatabase();
    final rows = await db.rawQuery(
      'SELECT * FROM user_roms WHERE app_system_id = ?',
      [system!.id],
    );
    final roots = <String>{
      root.path,
      p.join(root.path, 'roms'),
      p.join(root.path, 'games'),
    };
    for (final folder in config.config.romFolders) {
      roots.add(
        p.basename(folder).toLowerCase() == 'switch'
            ? folder
            : p.join(folder, 'switch'),
      );
    }
    for (final encoded
        in (await SharedPreferences.getInstance()).getStringList(
              'rewindbox.melonx.gameFolders',
            ) ??
            <String>[]) {
      try {
        final entry = jsonDecode(encoded) as Map;
        final linked = await ExternalFolderAccess.resolveBookmarkedFolder(
          key: entry['bookmark'] as String,
        );
        final relative = entry['relative'] as String;
        if (linked != null &&
            !p.isAbsolute(relative) &&
            !p.split(relative).contains('..'))
          roots.add(p.join(linked, relative));
      } catch (_) {
        /* revoked bookmarks retain their library rows */
      }
    }
    final seen = <String>{};
    var changed = 0;
    for (final folder in roots) {
      if (!await Directory(folder).exists()) continue;
      try {
        await for (final file in walk(
          Directory(folder),
          recursive: !p.equals(folder, root.path),
        )) {
          final location = p.normalize(file.absolute.path);
          if (!seen.add(location)) continue;
          final stat = await file.stat();
          final stamp = '${stat.size}:${stat.modified.microsecondsSinceEpoch}';
          final previous = index[location] as Map?;
          if (previous?['stamp'] == stamp &&
              previous?['failed'] == true &&
              previous?['keys'] == keyStamp)
            continue;
          final row = rows
              .where((r) => p.equals(r['rom_path'] as String, location))
              .firstOrNull;
          if (previous?['stamp'] == stamp && row != null) continue;
          try {
            final info = previous?['stamp'] == stamp && previous?['info'] is Map
                ? Map<String, dynamic>.from(previous!['info'] as Map)
                : await MelonxInternalService.content(
                    'metadata',
                    filePath: location,
                  );
            // Native metadata rejects NSPs without a main program; updates and
            // DLC are not games. Never infer a title from an archive filename.
            final digest =
                previous?['stamp'] == stamp && previous?['sha256'] is String
                ? previous!['sha256'] as String
                : await fingerprint(file);
            final identical = rows
                .where((r) => index[r['rom_path']]?['sha256'] == digest)
                .toList();
            Map<String, Object?>? moved;
            var duplicate = false;
            for (final candidate in identical) {
              if (candidate['rom_path'] == location) continue;
              final old = File(candidate['rom_path'] as String);
              if (await old.exists()) {
                duplicate = true;
                break;
              }
              // Access must be proven before classifying an old path as gone.
              try {
                if (await missing(old.path)) moved = candidate;
              } on FileSystemException {
                /* inaccessible is not missing */
              }
            }
            if (row == null && moved == null && !duplicate) {
              final titleId = info['titleId']?.toString();
              if (titleId != null &&
                  RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(titleId) &&
                  titleId != '0000000000000000') {
                final sameTitle = rows
                    .where(
                      (r) =>
                          r['title_id']?.toString().toLowerCase() ==
                          titleId.toLowerCase(),
                    )
                    .toList();
                // Legacy rows created before fingerprint indexing can be
                // relocated only for one uniquely identified base title.
                if (sameTitle.length == 1) {
                  final old = File(sameTitle.single['rom_path'] as String);
                  if (!await old.exists()) {
                    try {
                      if (await missing(old.path)) moved = sameTitle.single;
                    } on FileSystemException {
                      /* not proven absent */
                    }
                  }
                }
              }
            }
            index[location] = {'stamp': stamp, 'sha256': digest, 'info': info};
            if (duplicate && row == null) continue;
            if (row == null && moved != null) {
              await db.rawUpdate(
                "UPDATE user_roms SET rom_path = ?, updated_at = datetime('now') WHERE rom_path = ?",
                [location, moved['rom_path']],
              );
              // Preserve filename identity: scraped metadata/media, favourites,
              // play time and emulator settings continue to refer to this row.
              final oldSettings = await MelonxInternalService.graphicsForGame(
                moved['rom_path'] as String,
              );
              if (oldSettings.isNotEmpty)
                await MelonxInternalService.saveGraphics(location, oldSettings);
              rows.remove(moved);
              rows.add({...moved, 'rom_path': location});
            } else if (row == null) {
              await db.rawInsert(
                '''INSERT INTO user_roms
                (app_system_id, filename, rom_path, title_id, title_name)
                VALUES (?, ?, ?, ?, ?) ON CONFLICT(rom_path) DO NOTHING''',
                [
                  system.id,
                  p.basename(location),
                  location,
                  info['titleId'],
                  info['title'],
                ],
              );
              rows.add({
                'app_system_id': system.id,
                'filename': p.basename(location),
                'rom_path': location,
                'title_id': info['titleId'],
              });
            } else {
              continue;
            }
            changed++;
          } catch (error) {
            if (error is MelonxContentException &&
                const {
                  'InvalidDataException',
                  'MissingKeyException',
                  'FormatException',
                }.contains(error.nativeType)) {
              index[location] = {
                'stamp': stamp,
                'failed': true,
                'keys': keyStamp,
              };
            }
            /* unreadable/locked/non-game: retain existing records */
          }
        }
      } on FileSystemException {
        /* a revoked folder must never purge its rows */
      }
    }
    await cache.parent.create(recursive: true);
    final temporary = File('${cache.path}.importing');
    await temporary.writeAsString(jsonEncode(index), flush: true);
    await temporary.rename(cache.path);
    if (changed > 0) {
      await SystemRepository.addDetectedSystem(system.id!, 'switch');
      await config.refreshDetectedSystems();
    }
    return changed;
  }

  static Future<bool> missing(String location) async {
    var absent = p.normalize(location);
    while (true) {
      final parent = Directory(p.dirname(absent));
      try {
        final names = await parent
            .list(followLinks: false)
            .map((entry) => p.basename(entry.path))
            .toList();
        return !names.contains(p.basename(absent));
      } on FileSystemException catch (error) {
        if (error.osError?.errorCode != 2 || p.equals(parent.path, absent))
          return false;
        absent = parent.path;
      }
    }
  }

  static Stream<File> walk(Directory folder, {bool recursive = true}) async* {
    await for (final entry in folder.list(followLinks: false)) {
      final name = p.basename(entry.path);
      if (name.startsWith('.') || name == '__MACOSX') continue;
      if (entry is Directory && recursive) {
        yield* walk(entry);
      } else if (entry is File &&
          MelonxInternalService.gameExtensions.contains(
            p.extension(name).replaceFirst('.', '').toLowerCase(),
          )) {
        yield entry;
      }
    }
  }
}
