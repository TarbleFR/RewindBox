import 'dart:convert';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

import '../data/datasources/sqlite_service.dart';
import 'logger_service.dart';

/// A library folder outside RewindBox's container, picked with the system
/// folder picker and kept reachable by its own security-scoped bookmark.
class LinkedLibraryFolder {
  const LinkedLibraryFolder({required this.key, required this.root});

  /// The bookmark slot of the native plugin.
  final String key;

  /// The picked folder, as iOS last gave it back.
  final String root;

  Map<String, Object?> toJson() => <String, Object?>{'key': key, 'root': root};

  static LinkedLibraryFolder? fromJson(Object? value) {
    if (value is! Map) return null;
    final key = value['key'];
    final root = value['root'];
    if (key is! String || root is! String || key.isEmpty || root.isEmpty) return null;
    return LinkedLibraryFolder(key: key, root: root);
  }
}

/// The library folders added on iOS with "Add ROM folder".
///
/// iOS only lets an app read a folder outside its container through a
/// security-scoped bookmark that is resolved again at every launch. The
/// first link (the RetroArch card of the settings) has a single slot; this
/// registry adds one slot per folder, next to it. It only adds: the folders
/// registered before it existed, the single-slot link and the games already
/// indexed are read exactly as before.
///
/// A folder iOS does not give back at a launch is not removed and its games
/// are kept (see `SqliteDatabaseService.unreachableLibraryRoots`); adding
/// the same folder again restores its access.
abstract final class IosLinkedLibraryFolders {
  static final _log = LoggerService.instance;

  static const String prefsKey = 'ios_linked_library_folders_v1';
  static const String keyPrefix = 'library-';

  /// The linked folders iOS did not give back at this launch: folder ->
  /// native reason code.
  static final Map<String, String> unavailable = <String, String>{};

  static List<LinkedLibraryFolder> decode(String? raw) {
    if (raw == null || raw.isEmpty) return <LinkedLibraryFolder>[];
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! List) return <LinkedLibraryFolder>[];
      final keys = <String>{};
      return <LinkedLibraryFolder>[
        for (final entry in decoded.map(LinkedLibraryFolder.fromJson))
          if (entry != null && keys.add(entry.key)) entry,
      ];
    } on FormatException {
      return <LinkedLibraryFolder>[];
    }
  }

  static String encode(List<LinkedLibraryFolder> folders) =>
      jsonEncode(<Object?>[for (final folder in folders) folder.toJson()]);

  static Future<List<LinkedLibraryFolder>> load() async {
    final prefs = await SharedPreferences.getInstance();
    return decode(prefs.getString(prefsKey));
  }

  static Future<void> _save(List<LinkedLibraryFolder> folders) async {
    final prefs = await SharedPreferences.getInstance();
    if (folders.isEmpty) {
      await prefs.remove(prefsKey);
    } else {
      await prefs.setString(prefsKey, encode(folders));
    }
  }

  /// A bookmark slot none of [taken] uses.
  static String newKey(Iterable<String> taken, {DateTime? now}) {
    final used = taken.toSet();
    final stamp = (now ?? DateTime.now()).millisecondsSinceEpoch.toRadixString(36);
    var key = '$keyPrefix$stamp';
    for (var suffix = 2; used.contains(key); suffix++) {
      key = '$keyPrefix$stamp-$suffix';
    }
    return key;
  }

  /// Whether [folder] is [root] or lies inside it.
  static bool isInside(String folder, String root) {
    final child = path.posix.normalize(folder);
    final parent = path.posix.normalize(root);
    return child == parent || path.posix.isWithin(parent, child);
  }

  /// [registered] with every folder inside [from] replaced by the same
  /// folder inside [to], when the old one no longer opens and the new one
  /// does; duplicates are dropped. Null when nothing changes. A folder that
  /// still opens, or that is found at neither place, is kept as it is.
  static Future<List<String>?> rebase(
    List<String> registered, {
    required String from,
    required String to,
    required Future<bool> Function(String folder) exists,
  }) async {
    final oldRoot = path.posix.normalize(from);
    final newRoot = path.posix.normalize(to);
    if (oldRoot == newRoot) return null;
    final folders = <String>[];
    var changed = false;
    for (final folder in registered) {
      var chosen = folder;
      if (isInside(folder, oldRoot) && !await exists(folder)) {
        final relative = path.posix.relative(path.posix.normalize(folder), from: oldRoot);
        final candidate = relative == '.' ? newRoot : path.posix.join(newRoot, relative);
        if (await exists(candidate)) chosen = candidate;
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

  /// Runs once at startup, before the configuration reads the ROM folders:
  /// reopens every linked folder. Returns the folders iOS gave back. A
  /// folder that moved (its bookmark follows it) replaces its old path in
  /// the registered ROM folders, as the single-slot link always did.
  static Future<List<String>> activateAtStartup({
    Future<bool> Function(String folder)? exists,
  }) async {
    unavailable.clear();
    final reachable = <String>[];
    try {
      final entries = await load();
      if (entries.isEmpty) return reachable;
      final updated = <LinkedLibraryFolder>[];
      var entriesChanged = false;
      List<String>? romFolders;
      var romFoldersChanged = false;
      for (final entry in entries) {
        final resolved = await ExternalFolderAccess.resolveBookmarkedFolder(key: entry.key);
        if (resolved == null) {
          final failure = ExternalFolderAccess.resolveFailure(key: entry.key);
          unavailable[entry.root] = failure?.code ?? 'NO_BOOKMARK';
          _log.w(
            'Linked library folder not given back by iOS: ${entry.root} '
            '(${failure ?? 'no saved access'}). Its games are kept; add the '
            'folder again to restore access.',
          );
          updated.add(entry);
          continue;
        }
        reachable.add(resolved);
        if (path.posix.normalize(resolved) == path.posix.normalize(entry.root)) {
          updated.add(entry);
          continue;
        }
        romFolders ??= await SqliteService.getUserRomFolders();
        final rebased = await rebase(
          romFolders,
          from: entry.root,
          to: resolved,
          exists: exists ?? _directoryExists,
        );
        if (rebased != null) {
          romFolders = rebased;
          romFoldersChanged = true;
        }
        updated.add(LinkedLibraryFolder(key: entry.key, root: resolved));
        entriesChanged = true;
        _log.i('Linked library folder found at a new place: ${entry.root} -> $resolved');
      }
      if (romFoldersChanged) await SqliteService.saveUserRomFolders(romFolders!);
      if (entriesChanged) await _save(updated);
    } catch (error) {
      _log.e('Linked library folders could not be reopened: $error');
    }
    return reachable;
  }

  static Future<bool> _directoryExists(String folder) => Directory(folder).exists();

  /// Remembers that the folder picked under [key] is [root]. An earlier
  /// link of the same folder is replaced (its bookmark slot is cleared):
  /// this is how adding a folder again repairs a lost access.
  static Future<void> register({required String key, required String root}) async {
    final entries = await load();
    final kept = <LinkedLibraryFolder>[];
    for (final entry in entries) {
      if (entry.key == key) continue;
      if (path.posix.normalize(entry.root) == path.posix.normalize(root)) {
        await ExternalFolderAccess.clearBookmark(key: entry.key);
        continue;
      }
      kept.add(entry);
    }
    kept.add(LinkedLibraryFolder(key: key, root: root));
    unavailable.remove(root);
    await _save(kept);
  }

  /// Forgets the links that no registered ROM folder uses any more (the
  /// user removed the folder in the settings): their bookmark is cleared.
  /// The single-slot link of the RetroArch card is not part of this list.
  static Future<void> forgetUnused(List<String> romFolders) async {
    final entries = await load();
    if (entries.isEmpty) return;
    final kept = <LinkedLibraryFolder>[];
    for (final entry in entries) {
      if (romFolders.any((folder) => isInside(folder, entry.root))) {
        kept.add(entry);
      } else {
        await ExternalFolderAccess.clearBookmark(key: entry.key);
        unavailable.remove(entry.root);
        _log.i('Linked library folder forgotten: ${entry.root}');
      }
    }
    if (kept.length != entries.length) await _save(kept);
  }
}
