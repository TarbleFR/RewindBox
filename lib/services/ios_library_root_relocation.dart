import 'dart:io';

import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import '../data/datasources/sqlite_service.dart';
import 'logger_service.dart';

/// Finds the registered ROM folders again after iOS moved an app container.
///
/// ROM folders are stored as absolute paths, and an app's data container
/// lives at `.../Containers/Data/Application/<UUID>/`. When NeoStation (or
/// the app whose folder was linked) is reinstalled or updated, iOS can give
/// it a new UUID: the files are still there, but the stored path no longer
/// opens, the scanner finds no console and the library looks empty until
/// the folder is picked again, which only added the new path next to the
/// dead one (seven saved folders on 9 October 2026, several in containers
/// that no longer existed).
///
/// At startup, before the configuration is read, each registered folder
/// that no longer opens and lies in an app container is looked for at the
/// same place in the current containers: NeoStation's own first, then the
/// container of the linked folder (its security-scoped bookmark follows the
/// folder). A folder found there replaces the dead path; one found nowhere
/// is kept as it is (it may only be unavailable for now). No file is moved
/// and no game row is rewritten: the scanner indexes the folder at its new
/// path, as after picking the folder again by hand.
abstract final class IosLibraryRootRelocation {
  static final _log = LoggerService.instance;

  static final RegExp _appContainer = RegExp(
    r'^((?:/private)?/var/mobile/Containers/(?:Data/Application|Shared/AppGroup)/[0-9A-Fa-f-]{36})(?:/(.*))?$',
  );

  /// Whether this launch replaced a registered folder.
  static bool relocatedThisLaunch = false;

  /// The container of [folder] and its path inside it; null outside an iOS
  /// app container.
  static ({String container, String relative})? split(String folder) {
    final match = _appContainer.firstMatch(path.posix.normalize(folder));
    if (match == null) return null;
    return (container: match.group(1)!, relative: match.group(2) ?? '');
  }

  /// [registered] with each folder that no longer opens replaced by the same
  /// folder in one of [containers] (in that order) when it exists there;
  /// duplicates are dropped. Null when nothing changes.
  static Future<List<String>?> relocate(
    List<String> registered, {
    required List<String> containers,
    Future<bool> Function(String folder)? exists,
  }) async {
    final reachable = exists ?? (folder) => Directory(folder).exists();
    final folders = <String>[];
    var changed = false;
    for (final folder in registered) {
      var chosen = folder;
      final parts = split(folder);
      if (parts != null && parts.relative.isNotEmpty && !await reachable(folder)) {
        for (final container in containers) {
          if (container == parts.container) continue;
          final candidate = '$container/${parts.relative}';
          if (await reachable(candidate)) {
            chosen = candidate;
            break;
          }
        }
      }
      if (chosen != folder) changed = true;
      if (folders.contains(chosen)) {
        changed = true;
      } else {
        folders.add(chosen);
      }
    }
    return changed ? folders : null;
  }

  /// The folders of [before] that [after] holds at a new place: the same
  /// path inside another container. A folder that was only dropped as a
  /// duplicate of one already listed moves nowhere.
  static List<({String from, String to})> moves(List<String> before, List<String> after) {
    final pairs = <({String from, String to})>[];
    final arrived = after.where((folder) => !before.contains(folder)).toList();
    for (final folder in before) {
      if (after.contains(folder)) continue;
      final parts = split(folder);
      if (parts == null) continue;
      for (final candidate in arrived) {
        if (split(candidate)?.relative == parts.relative) {
          pairs.add((from: folder, to: candidate));
          break;
        }
      }
    }
    return pairs;
  }

  /// Runs once at startup, after the linked folders' bookmarks were resolved
  /// ([linkedFolder] for the single-slot link, [linkedFolders] for the
  /// folders added since; none when nothing is linked) and before the
  /// configuration provider reads the ROM folders.
  static Future<void> run({
    String? linkedFolder,
    Iterable<String> linkedFolders = const <String>[],
  }) async {
    try {
      final containers = <String>[];
      final own = split((await getApplicationDocumentsDirectory()).path)?.container;
      if (own != null) containers.add(own);
      for (final folder in <String?>[linkedFolder, ...linkedFolders]) {
        final linked = folder == null ? null : split(folder)?.container;
        if (linked != null && !containers.contains(linked)) containers.add(linked);
      }
      if (containers.isEmpty) return;
      final registered = await SqliteService.getUserRomFolders();
      final folders = await relocate(registered, containers: containers);
      if (folders == null) return;
      await SqliteService.saveUserRomFolders(folders);
      relocatedThisLaunch = true;
      // The games follow their folder: the same rows at the new path, so
      // play time, favourites and scraped data are kept. Without this the
      // next scan dropped every row of the old path and indexed the files
      // again as new games.
      var followed = 0;
      try {
        for (final move in moves(registered, folders)) {
          followed += await SqliteService.relocateRomPaths(move.from, move.to);
        }
      } catch (error) {
        _log.w('Games of a moved library folder keep their old rows: $error');
      }
      _log.i(
        'Library folders found again after a container move: '
        '${registered.where((folder) => !folders.contains(folder)).toList()} -> '
        '${folders.where((folder) => !registered.contains(folder)).toList()} '
        '($followed game row(s) follow their folder)',
      );
    } catch (error) {
      _log.e('Library folder relocation failed: $error');
    }
  }
}
