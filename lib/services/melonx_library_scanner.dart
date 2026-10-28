import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;
import '../data/datasources/sqlite_service.dart';
import '../providers/sqlite_config_provider.dart';
import '../repositories/system_repository.dart';
import 'frontend_media_gate.dart';
import 'ios_library_root_relocation.dart';
import 'melonx_internal_service.dart';
import 'melonx_file_transaction.dart';

/// Incremental Switch discovery. Never copies ROMs or deletes missing entries.
/// File hashes identify moves; a metadata-only match is deliberately refused.
///
/// Discovery never runs while a game is launching or running, and stops at the
/// next file when one starts: whole-file digests of 7-16 GB games used to run
/// on the root isolate (the iOS main thread) for up to two minutes into a
/// MeloNX session (builds 575-576 app.log).
abstract final class MelonxLibraryScanner {
  static Future<int>? _pending;
  static Future<int> refresh(SqliteConfigProvider config) =>
      _pending ??= _refresh(config).whenComplete(() => _pending = null);

  /// Whole-file SHA-256 (lowercase hex), off the root isolate.
  static Future<String> fingerprint(File file) =>
      Isolate.run(() async => (await sha256.bind(file.openRead()).first).toString());

  /// Whether discovery hashes on the native bridge (CryptoKit, a utility
  /// queue, abandoned by a launch); elsewhere [fingerprint] is used.
  @visibleForTesting
  static bool nativeDigests = Platform.isIOS;

  static int _generation = 0;
  static final Object _gateOwner = Object();
  static bool _gateRegistered = false;

  // Called synchronously when a launch or a game takes the frontend: ends the
  // discovery under way at its next file and abandons the native hash.
  static Future<void> _stop() async {
    _generation++;
    if (nativeDigests)
      unawaited(
        MelonxInternalService.channel
            .invokeMethod<void>('cancelFingerprint')
            .catchError((Object _) {}),
      );
  }

  static bool _interrupted(int generation) =>
      generation != _generation || FrontendMediaGate.instance.blocked;

  static Future<String> _digest(
    String location,
    File file,
    int generation,
  ) async {
    // No await between this check and the request: FrontendMediaGate.hold
    // runs _stop synchronously, so a stop after it posts cancelFingerprint
    // behind this request and the native side abandons the hash. A stop
    // during the metadata call that preceded it never reaches a later hash.
    if (_interrupted(generation)) throw const _DiscoveryInterrupted();
    if (!nativeDigests) return fingerprint(file);
    try {
      final digest = await MelonxInternalService.channel.invokeMethod<String>(
        'fingerprint',
        {'path': location},
      );
      if (digest != null && RegExp(r'^[0-9a-f]{64}$').hasMatch(digest))
        return digest;
      throw StateError('Invalid MeloNX fingerprint');
    } on PlatformException catch (error) {
      if (error.code == 'cancelled' || error.code == 'busy')
        throw const _DiscoveryInterrupted();
      rethrow;
    }
  }

  /// The iOS app container of a path and the path inside it.
  @visibleForTesting
  static ({String container, String relative})? Function(String path)
  containerOf = IosLibraryRootRelocation.split;

  /// Index entries of files under a scan root's former iOS app container,
  /// keyed by the same file's path in the current one. iOS gives the app a
  /// new container when it is reinstalled or updated
  /// ([IosLibraryRootRelocation]); the files keep their size and modification
  /// time. A file found there with an entry's stamp is the file indexed before:
  /// its digest and metadata are reused instead of hashing the whole game
  /// again, and the digest match below still re-points its row.
  @visibleForTesting
  static Map<String, List<Map>> containerMoves(
    Map<String, dynamic> index,
    Iterable<String> roots,
  ) {
    final mounts = [
      for (final root in roots) containerOf(root),
    ].nonNulls.toList();
    final moves = <String, List<Map>>{};
    if (mounts.isEmpty) return moves;
    index.forEach((key, entry) {
      if (entry is! Map) return;
      final old = containerOf(key);
      if (old == null) return;
      for (final mount in mounts) {
        if (mount.container == old.container) continue;
        if (mount.relative.isNotEmpty &&
            old.relative != mount.relative &&
            !p.posix.isWithin(mount.relative, old.relative))
          continue;
        final moved = '${mount.container}/${old.relative}';
        if (!index.containsKey(moved))
          (moves[moved] ??= <Map>[]).add(entry);
      }
    });
    return moves;
  }

  static Future<void> _save(File cache, Map<String, dynamic> index) async {
    await cache.parent.create(recursive: true);
    final temporary = File('${cache.path}.importing');
    await temporary.writeAsString(jsonEncode(index), flush: true);
    await temporary.rename(cache.path);
  }

  static Future<int> _refresh(SqliteConfigProvider config) async {
    if (!_gateRegistered) {
      _gateRegistered = true;
      FrontendMediaGate.instance.register(_gateOwner, _stop);
    }
    final generation = _generation;
    if (_interrupted(generation)) return 0;
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
    final moves = containerMoves(index, roots);
    final seen = <String>{};
    var changed = 0;
    var interrupted = false;
    for (final folder in roots) {
      if (interrupted) break;
      if (!await Directory(folder).exists()) continue;
      try {
        await for (final file in walk(
          Directory(folder),
          recursive: !p.equals(folder, root.path),
        )) {
          if (_interrupted(generation)) {
            interrupted = true;
            break;
          }
          final location = p.normalize(file.absolute.path);
          if (!seen.add(location)) continue;
          final stat = await file.stat();
          final stamp = '${stat.size}:${stat.modified.microsecondsSinceEpoch}';
          final previous =
              (index[location] ??
                      moves[location]?.where((e) => e['stamp'] == stamp).firstOrNull)
                  as Map?;
          // An entry found through a container move belongs to this path now;
          // digest matches read index[row path], so keep it under this one.
          if (previous != null && index[location] == null)
            index[location] = Map<String, dynamic>.from(previous);
          if (previous?['stamp'] == stamp &&
              previous?['failed'] == true &&
              previous?['keys'] == keyStamp)
            continue;
          final row = rows
              .where((r) => p.equals(r['rom_path'] as String, location))
              .firstOrNull;
          if (previous?['stamp'] == stamp && row != null) continue;
          try {
            if (_interrupted(generation)) throw const _DiscoveryInterrupted();
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
                : await _digest(location, file, generation);
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
            // Kept at once: a stop or a killed app never costs this digest
            // again. A failed write is retried by the final one.
            try {
              await _save(cache, index);
            } on FileSystemException {
              /* kept in memory */
            }
            if (duplicate && row == null) continue;
            if (row == null && moved != null) {
              await _preserveControls(
                root,
                moved['rom_path'] as String,
                info['titleId']?.toString(),
              );
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
          } on _DiscoveryInterrupted {
            interrupted = true;
          } catch (error) {
            // A launch refuses content calls: stop, not a per-file failure.
            if (error is PlatformException && error.code == 'busy') {
              interrupted = true;
            } else if (error is MelonxContentException &&
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
          if (interrupted) break;
        }
      } on FileSystemException {
        /* a revoked folder must never purge its rows */
      }
    }
    // Also after a stop: the files already indexed are not hashed again.
    await _save(cache, index);
    if (changed > 0) {
      await SystemRepository.addDetectedSystem(system.id!, 'switch');
      await config.refreshDetectedSystems();
    }
    return changed;
  }

  static Future<void> _preserveControls(
    Directory root,
    String oldPath,
    String? titleId,
  ) async {
    if (titleId == null ||
        !RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(titleId) ||
        titleId == '0000000000000000')
      return;
    final legacy = sha256.convert(utf8.encode(p.normalize(oldPath))).toString();
    final title = titleId.toLowerCase();
    final candidates = <String, FileSystemEntity>{
      'controller_layouts/$title.json': File(
        p.join(root.path, 'controller_layouts/$legacy.json'),
      ),
      'controller_mappings/$title': Directory(
        p.join(root.path, 'controller_mappings/$legacy'),
      ),
    };
    final items = <MelonxTransferItem>[];
    for (final candidate in candidates.entries) {
      if (!await candidate.value.exists() ||
          await FileSystemEntity.type(
                p.join(root.path, candidate.key),
                followLinks: false,
              ) !=
              FileSystemEntityType.notFound)
        continue;
      items.add(
        MelonxTransferItem(
          candidate.value,
          candidate.key,
          await MelonxFileTransaction.size(candidate.value),
          false,
        ),
      );
    }
    if (items.isNotEmpty)
      await MelonxInternalService.editLibrary(
        () => MelonxFileTransaction.apply(root, items, MelonxTransferControl()),
      );
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

class _DiscoveryInterrupted implements Exception {
  const _DiscoveryInterrupted();
}
