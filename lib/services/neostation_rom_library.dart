import 'dart:io';

import 'package:path/path.dart' as path;

import 'libretro_core_catalog.dart';
import 'logger_service.dart';
import 'storage/storage_roots.dart';

/// Why a game of a library move is not (fully) moved.
enum RomLibraryFailureReason {
  /// An iCloud placeholder: the game is not downloaded on this device.
  icloud,

  /// The copy has not the size of the original.
  sizeMismatch,

  /// The file could not be moved or copied.
  copyError,

  /// Copied, but the original could not be removed.
  notRemoved,
}

/// One game that [NeoStationRomLibrary.moveLibrary] did not fully move.
class RomLibraryFailure {
  const RomLibraryFailure(this.name, this.reason);

  /// File name (an iCloud placeholder `.Name.ext.icloud` shows as `Name.ext`).
  final String name;
  final RomLibraryFailureReason reason;
}

/// Outcome of [NeoStationRomLibrary.moveLibrary].
class RomLibraryMove {
  const RomLibraryMove({
    this.moved = 0,
    this.alreadyPresent = 0,
    this.notRemoved = 0,
    this.failed = 0,
    this.ownLibrary = false,
    this.unrecognisedFolders = const <String>[],
    this.failures = const <RomLibraryFailure>[],
  });

  /// The picked folder is NeoStation's own `roms` folder, holds it, or is
  /// inside it: nothing was looked at.
  final bool ownLibrary;

  /// Sub-folders of the source that are not console folders, sorted.
  final List<String> unrecognisedFolders;

  /// The games that are not (fully) moved, with the cause.
  final List<RomLibraryFailure> failures;

  /// Games now in NeoStation's library and gone from the source.
  final int moved;

  /// Games left in the source because the same file (name and size) was
  /// already in NeoStation's library.
  final int alreadyPresent;

  /// Games copied into NeoStation's library whose original could not be
  /// removed: they are in both places.
  final int notRemoved;

  /// Games that could not be moved (left in the source only).
  final int failed;

  int get total => moved + alreadyPresent + notRemoved + failed;

  /// Every game of the source is in NeoStation's library: the source folder
  /// is no longer needed.
  bool get complete => failed == 0;
}

/// NeoStation's own ROM library on iOS: Files › On My iPhone › NeoStation ›
/// roms, one folder per console. NeoStation and its embedded engine read it
/// without any folder grant.
abstract final class NeoStationRomLibrary {
  static final _log = LoggerService.instance;

  /// The folder of each console the embedded engine runs, named as the
  /// scanner knows it (the system games are imported into).
  static List<String> consoleFolders() =>
      {for (final console in LibretroCoreCatalog.consoles.values) console.importFolder}.toList()
        ..sort();

  /// A few console folder names to show as examples of what a library must
  /// contain (up to five, real names of [consoleFolders]).
  static List<String> exampleFolders() {
    final folders = consoleFolders();
    final preferred = <String>[
      for (final name in const <String>['gba', 'snes', 'psp', 'ps1', '3ds'])
        if (folders.contains(name)) name,
    ];
    return preferred.isNotEmpty ? preferred : folders.take(5).toList();
  }

  /// Creates `<romsRoot>/<console>` for every console of the embedded engine;
  /// existing folders and their games are kept. Returns the folders created.
  static Future<int> createConsoleFolders(String romsRoot) async {
    var created = 0;
    for (final folder in consoleFolders()) {
      final directory = Directory(path.join(romsRoot, folder));
      if (await directory.exists()) continue;
      await directory.create(recursive: true);
      created++;
    }
    return created;
  }

  /// Moves the games of [sourceRoot] into [romsRoot], keeping their place:
  /// `<sourceRoot>/<console>/<path>` becomes `<romsRoot>/<console>/<path>`.
  /// Only the console folders of the source are moved (a child folder whose
  /// name, ignoring case, is in [consoleFolderNames]); hidden files (iCloud
  /// placeholders of files not downloaded) are counted as not moved.
  ///
  /// A file already in the library with the same name and size is left in
  /// the source; one with the same name and another size is moved as
  /// "name (2).ext". Each file is renamed (same volume, instant); when the
  /// system refuses, it is copied, checked by size, then its original is
  /// deleted with [deleteSource] (default: File.delete).
  static Future<RomLibraryMove> moveLibrary({
    required String sourceRoot,
    required String romsRoot,
    required Set<String> consoleFolderNames,
    void Function(int done, int total)? onProgress,
    Future<void> Function(String filePath)? deleteSource,
  }) async {
    final source = path.normalize(sourceRoot);
    final destination = path.normalize(romsRoot);
    // iOS spells one folder `/var/…` or `/private/var/…`; a symlink too.
    final canonicalSource = storageCanonicalPath(_resolved(source));
    final canonicalDestination = storageCanonicalPath(_resolved(destination));
    if (canonicalSource == canonicalDestination ||
        path.isWithin(canonicalDestination, canonicalSource) ||
        path.isWithin(canonicalSource, canonicalDestination)) {
      return const RomLibraryMove(ownLibrary: true);
    }
    final names = {for (final name in consoleFolderNames) name.trim().toLowerCase()};
    final files = <File>[];
    var failed = 0;
    final failures = <RomLibraryFailure>[];
    final unrecognised = <String>[];
    await for (final entity in Directory(source).list(followLinks: false)) {
      if (entity is! Directory) continue;
      if (!names.contains(path.basename(entity.path).trim().toLowerCase())) {
        final name = path.basename(entity.path);
        if (!name.startsWith('.')) unrecognised.add(name);
        continue;
      }
      await for (final item in entity.list(recursive: true, followLinks: false)) {
        if (item is! File) continue;
        if (path.basename(item.path).startsWith('.')) {
          final hidden = path.basename(item.path);
          // An iCloud placeholder is `.<name>.icloud`; `.icloud` and
          // `..icloud` hold no name: plain hidden files.
          if (hidden.endsWith('.icloud') && hidden.length > '.icloud'.length + 1) {
            failed++;
            final name = hidden.substring(1, hidden.length - '.icloud'.length);
            failures.add(RomLibraryFailure(name, RomLibraryFailureReason.icloud));
          }
          continue;
        }
        files.add(item);
      }
    }
    final remove = deleteSource ?? (filePath) => File(filePath).delete();
    var moved = 0;
    var alreadyPresent = 0;
    var notRemoved = 0;
    final total = files.length + failed;
    onProgress?.call(failed, total);
    for (final file in files) {
      try {
        final length = await file.length();
        var target = File(path.join(destination, path.relative(file.path, from: source)));
        if (await target.exists()) {
          if (await target.length() == length) {
            alreadyPresent++;
            continue;
          }
          target = await _unique(target);
        }
        await target.parent.create(recursive: true);
        try {
          await file.rename(target.path);
          moved++;
        } on FileSystemException {
          final copied = await file.copy(target.path);
          if (await copied.length() != length) {
            await copied.delete();
            failed++;
            failures.add(RomLibraryFailure(path.basename(file.path), RomLibraryFailureReason.sizeMismatch));
            continue;
          }
          try {
            await remove(file.path);
            moved++;
          } catch (error) {
            _log.w('Library move kept the original of ${file.path}: $error');
            notRemoved++;
            failures.add(RomLibraryFailure(path.basename(file.path), RomLibraryFailureReason.notRemoved));
          }
        }
      } catch (error) {
        _log.w('Library move skipped ${file.path}: $error');
        failed++;
        failures.add(RomLibraryFailure(path.basename(file.path), RomLibraryFailureReason.copyError));
      } finally {
        onProgress?.call(moved + alreadyPresent + notRemoved + failed, total);
      }
    }
    _log.i(
      'Library moved from $source to $destination: moved=$moved alreadyPresent=$alreadyPresent '
      'notRemoved=$notRemoved failed=$failed',
    );
    return RomLibraryMove(
      moved: moved,
      alreadyPresent: alreadyPresent,
      notRemoved: notRemoved,
      failed: failed,
      unrecognisedFolders: unrecognised..sort(),
      failures: failures,
    );
  }

  static String _resolved(String directory) {
    try {
      return Directory(directory).existsSync() ? Directory(directory).resolveSymbolicLinksSync() : directory;
    } catch (_) {
      return directory;
    }
  }

  static Future<File> _unique(File file) async {
    final base = path.basenameWithoutExtension(file.path);
    final extension = path.extension(file.path);
    var index = 2;
    var candidate = file;
    while (await candidate.exists()) {
      candidate = File(path.join(file.parent.path, '$base ($index)$extension'));
      index++;
    }
    return candidate;
  }
}
