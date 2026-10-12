import 'dart:io';

import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import '../logger_service.dart';

/// Light maintenance of the file picker's copies
/// (docs/storage-audit-cleanup.md § 4, INV-28).
///
/// On iOS, `file_picker` opens documents `asCopy: true`: the system first
/// copies each pick into `tmp/<bundle-id>-Inbox/<name>` (the iOS location,
/// still to be confirmed on the device), then the plugin copies it again into
/// `tmp/<name>` and returns that path without removing the system copy
/// (`IOSFilePickerHandler.copyToTemporaryDirectory`). Once an import has
/// copied the pick into NeoStation and verified its length, neither copy is
/// read again.
///
/// Called only right after such a verification, never at startup or in the
/// background, and never through `FilePicker.clearTemporaryFiles()`, which
/// empties the whole temporary directory, other engines' folders included.
abstract final class StoragePickerCopies {
  static final _log = LoggerService.instance;

  /// The directory the picker copies into: `NSTemporaryDirectory()`, the
  /// `tmp` folder of the app container, beside `Documents`. Not
  /// path_provider's `getTemporaryDirectory()`, which is `Library/Caches` on
  /// iOS (path_provider_foundation: `NSCachesDirectory`) and never holds a
  /// picker copy.
  @visibleForTesting
  static Future<Directory> Function() temporaryDirectory =
      _containerTemporaryDirectory;

  static Future<Directory> _containerTemporaryDirectory() async {
    final documents = await getApplicationDocumentsDirectory();
    return Directory(path.join(path.dirname(documents.path), 'tmp'));
  }

  /// Whether a picked path is the picker's own copy: only iOS copies every
  /// pick. Elsewhere a picked path may be the user's own file, even one under
  /// the temporary directory (`/tmp` on Linux), so nothing is deleted there.
  @visibleForTesting
  static bool Function() pickedPathsAreCopies = _isIOS;

  static bool _isIOS() => Platform.isIOS;

  /// Deletes the plugin's copy [pickedPath] and the system copy of the same
  /// name under `<tmp>/*-Inbox/`. Each copy goes only when, resolved, it lies
  /// under the resolved [temporaryDirectory], is a regular file (never a link
  /// or a folder; links are not followed) and is [expectedLength] bytes long,
  /// the length the import verified. When the plugin's copy does not qualify,
  /// the system copy is kept as well. Never throws: returns the bytes freed
  /// and logs what was done.
  static Future<int> discardAfterVerifiedImport(
    String pickedPath, {
    required int expectedLength,
  }) async {
    final name = path.basename(pickedPath);
    var freed = 0;
    try {
      if (!pickedPathsAreCopies() || expectedLength < 0 || name.isEmpty) {
        return 0;
      }
      final root = await (await temporaryDirectory()).resolveSymbolicLinks();
      final plugin = await _qualifies(root, pickedPath, expectedLength);
      if (plugin.path == null) {
        _log.i(
          '[StoragePickerCopies] Kept the picker copy of $name: '
          '${plugin.reason}.',
        );
        return 0;
      }
      final copies = <String>[plugin.path!];
      await for (final entity in Directory(root).list(followLinks: false)) {
        if (entity is! Directory ||
            !path.basename(entity.path).endsWith('-Inbox')) {
          continue;
        }
        final system = await _qualifies(
          root,
          path.join(entity.path, name),
          expectedLength,
        );
        if (system.path != null) copies.add(system.path!);
      }
      final removed = <String>[];
      for (final copy in copies) {
        final relative = path.relative(copy, from: root);
        try {
          // Still the regular file just verified: unlink never follows a link.
          if (await FileSystemEntity.type(copy, followLinks: false) !=
              FileSystemEntityType.file) {
            continue;
          }
          await File(copy).delete();
          freed += expectedLength;
          removed.add('tmp/$relative');
        } on FileSystemException catch (error) {
          _log.w(
            '[StoragePickerCopies] Could not delete tmp/$relative: $error',
          );
        }
      }
      if (removed.isNotEmpty) {
        _log.i(
          '[StoragePickerCopies] Freed $freed bytes of picker copies of '
          '$name: ${removed.join(', ')}.',
        );
      }
      return freed;
    } catch (error) {
      _log.w(
        '[StoragePickerCopies] Picker copies of $name kept '
        '($freed bytes freed): $error',
      );
      return freed;
    }
  }

  /// [candidate] with its folder resolved (the file itself is never
  /// followed) when it is a regular file of [expectedLength] bytes under
  /// [root]; otherwise no path and the reason.
  static Future<({String? path, String reason})> _qualifies(
    String root,
    String candidate,
    int expectedLength,
  ) async {
    final type = await FileSystemEntity.type(candidate, followLinks: false);
    if (type != FileSystemEntityType.file) {
      return (
        path: null,
        reason: type == FileSystemEntityType.notFound
            ? 'missing'
            : 'not a regular file ($type)',
      );
    }
    final folder = await Directory(
      path.dirname(candidate),
    ).resolveSymbolicLinks();
    final resolved = path.join(folder, path.basename(candidate));
    if (!path.isWithin(root, resolved)) {
      return (path: null, reason: 'outside the temporary directory');
    }
    if (await FileSystemEntity.type(resolved, followLinks: false) !=
        FileSystemEntityType.file) {
      return (path: null, reason: 'not a regular file');
    }
    final length = await File(resolved).length();
    if (length != expectedLength) {
      return (
        path: null,
        reason: '$length bytes, not the verified $expectedLength',
      );
    }
    return (path: resolved, reason: 'verified');
  }
}

/// Bounds the logs the engines leave behind (docs/storage-audit-cleanup.md
/// § 4, INV-12 and INV-22), at the documented log points only: never at
/// startup, never while the engine that writes them runs.
abstract final class StorageLogRotation {
  static final _log = LoggerService.instance;

  /// Keeps the [keep] most recently modified regular files of [directory]
  /// whose name matches [name] and deletes the older ones. A [String] matches
  /// a whole name, a [RegExp] through [RegExp.hasMatch] (anchor it). Only
  /// the files directly in [directory] count: folders, links (never
  /// followed) and other names are left alone, and so is a [directory] that
  /// is itself a link. Never throws; returns the number of files deleted.
  static Future<int> keepNewest(
    Directory directory, {
    required Pattern name,
    required int keep,
  }) async {
    var removed = 0;
    try {
      if (keep < 0) return 0;
      if (await FileSystemEntity.type(directory.path, followLinks: false) !=
          FileSystemEntityType.directory) {
        return 0;
      }
      final logs = <({File file, DateTime modified})>[];
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is! File || !_matches(name, path.basename(entity.path))) {
          continue;
        }
        final stat = await entity.stat();
        if (stat.type != FileSystemEntityType.file) continue;
        logs.add((file: entity, modified: stat.modified));
      }
      if (logs.length <= keep) return 0;
      logs.sort((a, b) {
        final byTime = b.modified.compareTo(a.modified);
        if (byTime != 0) return byTime;
        return path.basename(b.file.path).compareTo(path.basename(a.file.path));
      });
      for (final old in logs.skip(keep)) {
        try {
          if (await FileSystemEntity.type(old.file.path, followLinks: false) !=
              FileSystemEntityType.file) {
            continue;
          }
          await old.file.delete();
          removed++;
        } on FileSystemException catch (error) {
          _log.w(
            '[StorageLogRotation] Could not delete '
            '${path.basename(old.file.path)}: $error',
          );
        }
      }
      _log.i(
        '[StorageLogRotation] Deleted $removed old logs in '
        '${path.basename(directory.path)}, kept the $keep newest.',
      );
      return removed;
    } catch (error) {
      _log.w(
        '[StorageLogRotation] Logs of ${directory.path} not bounded '
        '($removed deleted): $error',
      );
      return removed;
    }
  }

  /// Renames [file] to `<name>.old`, replacing a previous `.old`, once it is a
  /// regular file of more than [maxBytes] bytes: the rotation of `app.log`
  /// (`LoggerService.init`). A link, or a `.old` that is not a regular file,
  /// leaves everything in place. Never throws.
  static Future<void> rotateAtSize(
    File file, {
    int maxBytes = 5 * 1024 * 1024,
  }) async {
    final name = path.basename(file.path);
    try {
      if (await FileSystemEntity.type(file.path, followLinks: false) !=
          FileSystemEntityType.file) {
        return;
      }
      final length = await file.length();
      if (length <= maxBytes) return;
      final old = '${file.path}.old';
      final previous = await FileSystemEntity.type(old, followLinks: false);
      if (previous != FileSystemEntityType.file &&
          previous != FileSystemEntityType.notFound) {
        _log.w(
          '[StorageLogRotation] $name not rotated: $name.old is a $previous.',
        );
        return;
      }
      await file.rename(old);
      _log.i(
        '[StorageLogRotation] Rotated $name ($length bytes) to $name.old.',
      );
    } catch (error) {
      _log.w('[StorageLogRotation] $name not rotated: $error');
    }
  }

  static bool _matches(Pattern pattern, String name) {
    if (pattern is String) return pattern == name;
    if (pattern is RegExp) return pattern.hasMatch(name);
    final match = pattern.matchAsPrefix(name);
    return match != null && match.end == name.length;
  }
}
