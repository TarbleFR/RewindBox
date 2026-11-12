import 'dart:async';
import 'dart:io';
import 'dart:ui' show Locale, PlatformDispatcher;

import 'package:external_folder_access/external_folder_access.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:xenia_internal_bridge/xenia_internal_bridge.dart';

import 'config_service.dart';
import 'logger_service.dart';
import 'storage/storage_import_activity.dart';
import 'storage/storage_picker_copies.dart';
import 'storage/storage_stat_ffi.dart';
import 'xenia_content.dart';
import 'xenia_jit_service.dart';
import '../l10n/xenia_locale.dart';
import 'xenia_settings_service.dart';

/// Outcome of one picked file in an Xbox 360 import. [reason] is a
/// XeniaLocale key.
class XeniaImportItem {
  const XeniaImportItem(this.name, this.reason, {this.destination});
  final String name;
  final String reason;
  final String? destination;

  bool get imported => reason == 'imported';
}

class XeniaImportResult {
  const XeniaImportResult(this.items, {this.cancelled = false});
  final List<XeniaImportItem> items;
  final bool cancelled;

  int get imported => items.where((item) => item.imported).length;
  int get duplicates =>
      items.where((item) => item.reason == 'duplicate').length;
  Iterable<XeniaImportItem> get rejected =>
      items.where((item) => !item.imported && item.reason != 'duplicate');
}

/// Progress of the file being copied.
class XeniaImportProgress {
  const XeniaImportProgress({
    required this.name,
    required this.index,
    required this.count,
    required this.done,
    required this.total,
  });
  final String name;
  final int index;
  final int count;
  final int done;
  final int total;

  double? get fraction => total <= 0 ? null : (done / total).clamp(0.0, 1.0);
}

/// Cancels an import between two copied chunks.
class XeniaImportControl {
  bool _cancelled = false;
  bool get cancelled => _cancelled;
  void cancel() => _cancelled = true;
}

class _Cancelled implements Exception {}

/// Result of a launch request; [error] is a XeniaLocale key.
class XeniaLaunchOutcome {
  const XeniaLaunchOutcome.success()
    : success = true,
      error = null,
      detail = null;
  const XeniaLaunchOutcome.failure(this.error, [this.detail]) : success = false;
  final bool success;
  final String? error;
  final String? detail;
}

/// Storage, import and launch of the Xbox 360 playlist's embedded XeniOS
/// engine (docs/xenios-playlist.md). Files-visible layout:
///
/// - `Documents/XeniOS/Games`: games imported by RewindBox (scanned as the
///   `xbox360` system's own root, beside the user's library folders);
/// - `Documents/XeniOS/Content`: Xenia content root (saves, updates, DLC);
/// - `Documents/XeniOS/Engine`: Xenia storage root (its own config files);
/// - `Documents/XeniOS/Frontend`: RewindBox's XeniOS settings;
/// - `Library/Caches/XeniOS`: shader and pipeline caches.
abstract final class XeniaInternalService {
  static final _log = LoggerService.instance;

  static const String systemFolder = 'xbox360';
  static const String sessionExecutable = 'ios_xenia_internal';

  /// Kept free on the volume beyond the copied file.
  static const int spaceMargin = 512 * 1024 * 1024;
  static const int _chunk = 4 * 1024 * 1024;

  @visibleForTesting
  static Future<Directory> Function() documentsDirectory =
      getApplicationDocumentsDirectory;

  @visibleForTesting
  static Future<Directory> Function() cachesDirectory =
      getApplicationCacheDirectory;

  /// Free bytes of the volume holding a path; null when unknown.
  @visibleForTesting
  static int? Function(String path) freeBytes = _statFreeBytes;

  static int? _statFreeBytes(String location) =>
      StorageStatFfi.tryLoad()?.statvfs(location)?.freeBytes;

  static Future<Directory> rootDirectory() async =>
      Directory(path.join((await documentsDirectory()).path, 'XeniOS'));

  static Future<Directory> _child(String name) async =>
      Directory(path.join((await rootDirectory()).path, name));

  static Future<Directory> gamesDirectory() => _child('Games');
  static Future<Directory> contentDirectory() => _child('Content');
  static Future<Directory> engineDirectory() => _child('Engine');
  static Future<Directory> frontendDirectory() => _child('Frontend');

  /// Staging of folder imports, beside `Games` so that the final move is a
  /// rename on the same volume and the scan never sees a partial game.
  static Future<Directory> stagingDirectory() => _child('.importing');

  /// Bookmark slot of the folder import: the last folder picked for it.
  static const String importBookmark = 'xenia-import';
  static Future<Directory> cacheDirectory() async =>
      Directory(path.join((await cachesDirectory()).path, 'XeniOS'));

  static Future<void> ensureLayout() async {
    for (final directory in <Directory>[
      await gamesDirectory(),
      await contentDirectory(),
      await engineDirectory(),
      await frontendDirectory(),
      await cacheDirectory(),
    ]) {
      await directory.create(recursive: true);
    }
    ConfigService.linkedXeniaGameFolderPath = (await gamesDirectory()).path;
  }

  static XeniaSettingsService? _settings;
  static XeniaSettingsService get settings =>
      _settings ??= XeniaSettingsService(frontendDirectory: frontendDirectory);

  @visibleForTesting
  static set settingsForTesting(XeniaSettingsService? value) =>
      _settings = value;

  // ------------------------------------------------------------ availability

  static XeniaRuntimeAvailability? _availability;

  /// Whether this device and build can run XeniOS. Cached for the process:
  /// neither the OS version nor the bundled framework change while it runs.
  static Future<XeniaRuntimeAvailability> availability() async =>
      _availability ??= await XeniaInternalBridge.availability(
        isIOS: defaultTargetPlatform == TargetPlatform.iOS,
      );

  @visibleForTesting
  static set availabilityForTesting(XeniaRuntimeAvailability? value) =>
      _availability = value;

  // ------------------------------------------------------------------ import

  /// Picks Xbox 360 games in Files and copies the supported ones into
  /// [gamesDirectory]. Returns null when the picker was dismissed.
  static Future<XeniaImportResult?> importGames({
    void Function(XeniaImportProgress progress)? onProgress,
    XeniaImportControl? control,
  }) => StorageImportActivity.run(() async {
    await ensureLayout();
    final selection = await FilePicker.pickFiles(
      allowMultiple: true,
      type: FileType.custom,
      allowedExtensions: XeniaContent.pickerExtensions.toList()..sort(),
      withData: false,
      lockParentWindow: true,
    );
    if (selection == null) return null;
    return importFiles(
      <String>[
        for (final file in selection.files)
          if (file.path != null) file.path!,
      ],
      missing: selection.files.where((file) => file.path == null).length,
      onProgress: onProgress,
      control: control,
      discardPickerCopy: true,
    );
  });

  /// Imports [sources] (already readable local paths). Visible for tests.
  static Future<XeniaImportResult> importFiles(
    List<String> sources, {
    int missing = 0,
    void Function(XeniaImportProgress progress)? onProgress,
    XeniaImportControl? control,
    bool discardPickerCopy = false,
  }) async {
    final destination = await gamesDirectory();
    await destination.create(recursive: true);
    final items = <XeniaImportItem>[
      for (var index = 0; index < missing; index++)
        const XeniaImportItem('?', 'unreadable'),
    ];
    var cancelled = false;
    // Picked path -> length its import verified (docs/storage-audit-cleanup.md § 4).
    final verifiedCopies = <String, int>{};
    for (var index = 0; index < sources.length; index++) {
      final source = File(sources[index]);
      final name = path.basename(source.path);
      if (control?.cancelled ?? false) {
        cancelled = true;
        break;
      }
      final reason = await _refusal(source);
      if (reason != null) {
        _log.w('XeniOS import: $name refused ($reason).');
        items.add(XeniaImportItem(name, reason));
        continue;
      }
      final length = await source.length();
      if (await _isDuplicate(source, length, destination)) {
        _log.i('XeniOS import: $name already in the library.');
        items.add(XeniaImportItem(name, 'duplicate'));
        continue;
      }
      final free = freeBytes(destination.path);
      if (free != null && free < length + spaceMargin) {
        items.add(XeniaImportItem(name, 'notEnoughSpace'));
        continue;
      }
      try {
        final output = await _copy(
          source,
          destination,
          control: control,
          progress: (done, total) => onProgress?.call(
            XeniaImportProgress(
              name: name,
              index: index + 1,
              count: sources.length,
              done: done,
              total: total,
            ),
          ),
        );
        final outputLength = await output.length();
        if (length <= 0 || length != outputLength) {
          await output.delete();
          items.add(XeniaImportItem(name, 'copyFailed'));
          continue;
        }
        items.add(XeniaImportItem(name, 'imported', destination: output.path));
        verifiedCopies[source.path] = outputLength;
        _log.i(
          'XeniOS import: $name imported as ${path.basename(output.path)}.',
        );
      } on _Cancelled {
        _log.i('XeniOS import: cancelled during $name.');
        cancelled = true;
        break;
      } on FileSystemException catch (error) {
        _log.e('XeniOS import: $name failed: $error');
        final osCode = error.osError?.errorCode;
        // ENOSPC (28 on Darwin and Linux).
        items.add(
          XeniaImportItem(name, osCode == 28 ? 'notEnoughSpace' : 'copyFailed'),
        );
      }
    }
    // Once every pick is handled, the picker's copies of the verified
    // imports are not read again.
    if (discardPickerCopy) {
      for (final copy in verifiedCopies.entries) {
        await StoragePickerCopies.discardAfterVerifiedImport(
          copy.key,
          expectedLength: copy.value,
        );
      }
    }
    return XeniaImportResult(items, cancelled: cancelled);
  }

  /// Picks a folder in Files and imports the Xbox 360 games it holds: title
  /// folders with `default.xex`, Games on Demand packages (header plus
  /// `.data`) and single-file STFS packages (docs/xenios-playlist.md §
  /// Folder import). Returns null when the picker was dismissed. The folder
  /// is read in place; nothing is left in the picker's inbox. [dialogTitle]
  /// is unused: the iOS folder picker shows no title.
  static Future<XeniaImportResult?> importFolder({
    String? dialogTitle,
    void Function(XeniaImportProgress progress)? onProgress,
    XeniaImportControl? control,
  }) => StorageImportActivity.run(() async {
    await ensureLayout();
    // The folder is read where it is (often another app's or the device's own
    // folder): pickAndActivateFolder keeps iOS's security-scoped access open
    // for this session. file_picker 12.0.0-beta.3's directory pick returns a
    // bare path without it (IOSFilePickerHandler.swift), so a folder outside
    // RewindBox's container read as empty (IPA 727, found on Switch 2).
    final String? folder;
    try {
      folder = await ExternalFolderAccess.pickAndActivateFolder(
        key: importBookmark,
      );
    } on ExternalFolderAccessException catch (error) {
      _log.w('XeniOS import: the picked folder could not be opened: $error');
      return XeniaImportResult(<XeniaImportItem>[
        XeniaImportItem(error.code, 'folderAccessFailed'),
      ]);
    }
    if (folder == null) return null;
    return importFolderAt(
      Directory(folder),
      onProgress: onProgress,
      control: control,
    );
  });

  /// Imports the games of [picked] (a readable local folder). Visible for
  /// tests.
  static Future<XeniaImportResult> importFolderAt(
    Directory picked, {
    void Function(XeniaImportProgress progress)? onProgress,
    XeniaImportControl? control,
  }) async {
    final games = await gamesDirectory();
    await games.create(recursive: true);
    final staging = await stagingDirectory();
    await _removeStaging(staging);
    final scan = await XeniaFolderContent.scan(picked);
    final items = <XeniaImportItem>[
      for (final problem in scan.problems)
        XeniaImportItem(problem.name, problem.reason),
    ];
    for (final problem in scan.problems) {
      _log.w(
        'XeniOS folder import: ${problem.name} refused (${problem.reason}).',
      );
    }
    var cancelled = false;
    final existing = await _libraryIdentities(games);
    for (var index = 0; index < scan.games.length; index++) {
      final game = scan.games[index];
      if (control?.cancelled ?? false) {
        cancelled = true;
        break;
      }
      final identity = _identityOf(
        game.kind,
        game.titleId,
        game.mediaId,
        game.discNumber,
        game.title,
        game.totalBytes,
      );
      if (existing.contains(identity)) {
        _log.i('XeniOS folder import: ${game.title} already in the library.');
        items.add(XeniaImportItem(game.title, 'duplicate'));
        continue;
      }
      final free = freeBytes(games.path);
      if (free != null && free < game.totalBytes + spaceMargin) {
        items.add(XeniaImportItem(game.title, 'notEnoughSpace'));
        continue;
      }
      final stage = Directory(path.join(staging.path, '$index'));
      try {
        final launch = await _stageFolderGame(
          game,
          stage,
          control: control,
          progress: (done, total) => onProgress?.call(
            XeniaImportProgress(
              name: game.title,
              index: index + 1,
              count: scan.games.length,
              done: done,
              total: total,
            ),
          ),
        );
        final target = await _freeDirectory(games, game.title);
        await stage.rename(target.path);
        final destination = path.join(
          target.path,
          path.relative(launch, from: stage.path),
        );
        existing.add(identity);
        items.add(
          XeniaImportItem(game.title, 'imported', destination: destination),
        );
        _log.i(
          'XeniOS folder import: ${game.title} imported '
          '(${game.kind.name}, ${game.files.length} files).',
        );
      } on _Cancelled {
        _log.i('XeniOS folder import: cancelled during ${game.title}.');
        cancelled = true;
        break;
      } on FileSystemException catch (error) {
        _log.e('XeniOS folder import: ${game.title} failed: $error');
        final osCode = error.osError?.errorCode;
        items.add(
          XeniaImportItem(
            game.title,
            osCode == 28 ? 'notEnoughSpace' : 'copyFailed',
          ),
        );
      } finally {
        await _removeStaging(stage);
      }
    }
    await _removeStaging(staging);
    return XeniaImportResult(items, cancelled: cancelled);
  }

  static Future<void> _removeStaging(Directory directory) async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException catch (error) {
      _log.w('XeniOS folder import: staging not removed: $error');
    }
  }

  /// Copies [game] into [stage] and returns its launch file there. An
  /// executable keeps its title folder's tree; a package header becomes
  /// `<title>.god` with its data files in `<title>.god.data` (the engine
  /// finds the data beside the header by name and reads the header's magic,
  /// not its name). Every copied length is checked.
  static Future<String> _stageFolderGame(
    XeniaFolderGame game,
    Directory stage, {
    XeniaImportControl? control,
    void Function(int done, int total)? progress,
  }) async {
    await stage.create(recursive: true);
    // Source path -> staged path (File has no value equality).
    final targets = <String, String>{};
    String launch;
    if (game.kind == XeniaFolderGameKind.executable) {
      for (final file in game.files) {
        targets[file.path] = path.join(
          stage.path,
          path.relative(file.path, from: game.root.path),
        );
      }
      launch = targets[game.launchFile.path]!;
    } else {
      final header = '${_safeName(game.title)}.god';
      launch = path.join(stage.path, header);
      targets[game.launchFile.path] = launch;
      for (final file in game.files.skip(1)) {
        targets[file.path] = path.join(
          stage.path,
          '$header.data',
          path.basename(file.path),
        );
      }
    }
    var done = 0;
    progress?.call(0, game.totalBytes);
    for (final entry in targets.entries) {
      final source = File(entry.key);
      final expected = await source.length();
      await Directory(path.dirname(entry.value)).create(recursive: true);
      await _copyBytes(
        source,
        File(entry.value),
        control: control,
        progress: (copied) => progress?.call(done + copied, game.totalBytes),
      );
      if (await File(entry.value).length() != expected) {
        throw const FileSystemException('Copied length mismatch');
      }
      done += expected;
      progress?.call(done, game.totalBytes);
    }
    // A cancel after the last chunk still keeps nothing.
    if (control?.cancelled ?? false) throw _Cancelled();
    return launch;
  }

  static Future<void> _copyBytes(
    File source,
    File target, {
    XeniaImportControl? control,
    void Function(int copied)? progress,
  }) async {
    RandomAccessFile? input;
    RandomAccessFile? output;
    try {
      input = await source.open();
      output = await target.open(mode: FileMode.write);
      var copied = 0;
      final watch = Stopwatch()..start();
      while (true) {
        if (control?.cancelled ?? false) throw _Cancelled();
        final bytes = await input.read(_chunk);
        if (bytes.isEmpty) break;
        await output.writeFrom(bytes);
        copied += bytes.length;
        if (watch.elapsedMilliseconds >= 100) {
          progress?.call(copied);
          watch.reset();
        }
      }
      await output.flush();
    } finally {
      await output?.close();
      await input?.close();
    }
  }

  static String _safeName(String value) {
    final cleaned = value
        .replaceAll(RegExp(r'[\x00-\x1F/\\:*?"<>|]'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    return cleaned.isEmpty || cleaned.startsWith('.')
        ? 'Xbox 360 game'
        : cleaned;
  }

  static Future<Directory> _freeDirectory(Directory games, String title) async {
    final base = _safeName(title);
    var target = Directory(path.join(games.path, base));
    for (
      var index = 2;
      await target.exists() || await File(target.path).exists();
      index++
    ) {
      if (index > 9999) {
        throw const FileSystemException('No free destination name');
      }
      target = Directory(path.join(games.path, '$base ($index)'));
    }
    return target;
  }

  /// Identity of a folder game: title, media and disc IDs when the header
  /// has them, otherwise its name and size.
  static String _identityOf(
    XeniaFolderGameKind kind,
    String? titleId,
    String? mediaId,
    int? discNumber,
    String title,
    int bytes,
  ) => titleId != null
      ? '${kind.name}:$titleId:${mediaId ?? ''}:${discNumber ?? ''}'
      : '${kind.name}:name:${title.toLowerCase()}:$bytes';

  /// Identities of the folder games already in `XeniOS/Games` (one level
  /// of title folders, as the folder import writes them).
  static Future<Set<String>> _libraryIdentities(Directory games) async {
    final identities = <String>{};
    await for (final entity in games.list(followLinks: false)) {
      if (entity is! Directory) continue;
      final List<FileSystemEntity> children;
      try {
        children = await entity.list(followLinks: false).toList();
      } on FileSystemException {
        continue;
      }
      for (final child in children.whereType<File>()) {
        final name = path.basename(child.path).toLowerCase();
        try {
          if (name == XeniaFolderContent.executableName) {
            final game = await XeniaFolderContent.scan(entity);
            for (final found in game.games) {
              identities.add(
                _identityOf(
                  found.kind,
                  found.titleId,
                  found.mediaId,
                  found.discNumber,
                  found.title,
                  found.totalBytes,
                ),
              );
            }
          } else if (XeniaContent.kindForName(name) ==
              XeniaContentKind.package) {
            final info = await XeniaFolderContent.inspectPackage(child);
            if (info == null) continue;
            var bytes = await child.length();
            final data = Directory('${child.path}.data');
            if (await data.exists()) {
              await for (final part in data.list(followLinks: false)) {
                if (part is File &&
                    !XeniaFolderContent.isSystemClutter(
                      path.basename(part.path),
                    )) {
                  bytes += await part.length();
                }
              }
            }
            identities.add(
              _identityOf(
                XeniaFolderGameKind.package,
                info.titleId,
                info.mediaId,
                null,
                path.basenameWithoutExtension(child.path),
                bytes,
              ),
            );
          }
        } on FileSystemException {
          continue;
        }
      }
    }
    return identities;
  }

  static Future<String?> _refusal(File source) async {
    switch (XeniaContent.kindForName(source.path)) {
      case XeniaContentKind.profile:
        return 'profileNotGame';
      case XeniaContentKind.touchLayout:
        return 'touchLayoutNotGame';
      case XeniaContentKind.looseExecutable:
      case XeniaContentKind.package:
        return 'folderRequired';
      case XeniaContentKind.unsupported:
        return 'unsupported';
      case XeniaContentKind.discImage:
      case XeniaContentKind.zarArchive:
        break;
    }
    try {
      if (!await source.exists() || await source.length() <= 0) {
        return 'unreadable';
      }
    } on FileSystemException {
      return 'unreadable';
    }
    if (XeniaContent.kindForName(source.path) != XeniaContentKind.discImage) {
      // ZArchive: the engine's reader validates it at boot.
      return null;
    }
    try {
      await XeniaContent.inspectDiscImage(source);
      return null;
    } on XeniaContentException catch (error) {
      return switch (error.error) {
        XeniaContentError.notXboxImage => 'notXboxImage',
        XeniaContentError.truncated => 'incomplete',
        XeniaContentError.unreadable => 'unreadable',
      };
    }
  }

  /// Same name and size, or another file of the same size holding the same
  /// disc (title and media IDs): not copied again.
  static Future<bool> _isDuplicate(
    File source,
    int length,
    Directory games,
  ) async {
    final name = path.basename(source.path).toLowerCase();
    XeniaDiscIdentity? identity;
    await for (final entity in games.list(followLinks: false)) {
      if (entity is! File || entity.path.endsWith('.importing')) continue;
      final FileStat stat;
      try {
        stat = await entity.stat();
      } on FileSystemException {
        continue;
      }
      if (stat.size != length) continue;
      if (path.basename(entity.path).toLowerCase() == name) return true;
      if (XeniaContent.kindForName(source.path) != XeniaContentKind.discImage ||
          XeniaContent.kindForName(entity.path) != XeniaContentKind.discImage) {
        continue;
      }
      try {
        identity ??= await XeniaContent.inspectDiscImage(source);
        final other = await XeniaContent.inspectDiscImage(entity);
        if (identity.titleId != null &&
            identity.titleId == other.titleId &&
            identity.mediaId == other.mediaId &&
            identity.discNumber == other.discNumber) {
          return true;
        }
      } on XeniaContentException {
        continue;
      }
    }
    return false;
  }

  static Future<File> _copy(
    File source,
    Directory destination, {
    XeniaImportControl? control,
    void Function(int done, int total)? progress,
  }) async {
    final name = path.basename(source.path);
    var target = File(path.join(destination.path, name));
    for (var index = 2; await target.exists(); index++) {
      if (index > 9999) {
        throw const FileSystemException('No free destination name');
      }
      target = File(
        path.join(
          destination.path,
          '${path.basenameWithoutExtension(name)} ($index)${path.extension(name)}',
        ),
      );
    }
    final temporary = File('${target.path}.importing');
    final expected = await source.length();
    RandomAccessFile? input;
    RandomAccessFile? output;
    try {
      input = await source.open();
      output = await temporary.open(mode: FileMode.write);
      var copied = 0;
      final watch = Stopwatch()..start();
      progress?.call(0, expected);
      while (true) {
        if (control?.cancelled ?? false) throw _Cancelled();
        final bytes = await input.read(_chunk);
        if (bytes.isEmpty) break;
        await output.writeFrom(bytes);
        copied += bytes.length;
        if (watch.elapsedMilliseconds >= 100 || copied == expected) {
          progress?.call(copied, expected);
          watch.reset();
        }
      }
      await output.flush();
      await output.close();
      output = null;
      if (copied != expected || await temporary.length() != expected) {
        throw const FileSystemException('Copied length mismatch');
      }
      return await temporary.rename(target.path);
    } catch (_) {
      await output?.close();
      if (await temporary.exists()) await temporary.delete();
      rethrow;
    } finally {
      await input?.close();
    }
  }

  // ------------------------------------------------------------------ launch

  static int? contentKindFor(String romPath) =>
      switch (XeniaContent.kindForName(romPath)) {
        XeniaContentKind.discImage => 1,
        XeniaContentKind.zarArchive => 2,
        XeniaContentKind.looseExecutable => 3,
        XeniaContentKind.package => 4,
        _ => null,
      };

  /// Boots [romPath] in the embedded engine with this game's effective
  /// settings. Never reports success unless the bridge booted the title.
  static Future<XeniaLaunchOutcome> launch({
    required String romPath,
    required String title,
    required Locale uiLocale,
  }) async {
    await takePreviousFatal();
    await takePreviousLaunchJournal();
    final runtime = await availability();
    if (!runtime.ready) return _refused(runtime.state.name, runtime.detail);
    // Every cheap refusal comes before the JIT helper: a transaction opened
    // for a launch that never reaches the bridge would refuse every later
    // prepareJit until RewindBox restarts.
    final kind = contentKindFor(romPath);
    if (kind == null) return _refused('unsupported');
    if (!await File(romPath).exists()) return _refused('gameUnreadable');
    // The dedicated XeniOS JIT helper, only when the Core needs it
    // (docs/xenios-playlist.md § JIT helper).
    final jit = await XeniaJitService.ensure();
    if (!jit.success) return _refused(jit.error ?? 'launchFailed', jit.detail);
    final Map<String, dynamic> report;
    try {
      report = await _bridgeLaunch(romPath, kind, title, uiLocale);
    } on Object catch (error) {
      // The bridge was not reached: end the transaction prepared for it
      // (the bridge ends it itself on every failure it reports).
      _log.e('XeniOS launch: $error');
      await abortJit();
      return XeniaLaunchOutcome.failure('launchFailed', error.toString());
    }
    if (report['success'] == true) return const XeniaLaunchOutcome.success();
    final error = report['error']?.toString() ?? 'launchFailed';
    _log.e('XeniOS launch failed: $error ${report['detail'] ?? ''}');
    return XeniaLaunchOutcome.failure(error, report['detail']?.toString());
  }

  /// A refusal before the bridge, with its reason in app.log (the caller
  /// only logs that the launch failed).
  static XeniaLaunchOutcome _refused(String error, [String? detail]) {
    final suffix = detail == null || detail.isEmpty ? '' : ' $detail';
    _log.w('XeniOS launch refused: $error$suffix');
    return XeniaLaunchOutcome.failure(error, detail);
  }

  /// The reason of a XeniOS fatal error that closed RewindBox in an earlier
  /// session: XeniOS ends the process after its fatal-error hook, which the
  /// Core points at `Engine/last-fatal.txt` (docs/xenios-playlist.md § Code
  /// region). Logged once, then removed.
  @visibleForTesting
  static Future<String?> takePreviousFatal() async {
    final record = File(
      path.join((await engineDirectory()).path, 'last-fatal.txt'),
    );
    try {
      if (!await record.exists()) return null;
      final reason = (await record.readAsString()).trim();
      await record.delete();
      if (reason.isEmpty) return null;
      _log.e(
        'XeniOS: an engine fatal error closed RewindBox in an earlier '
        'session: $reason',
      );
      return reason;
    } on FileSystemException catch (error) {
      _log.w('XeniOS: the previous fatal error record is unreadable: $error');
      return null;
    }
  }

  /// The stages of the previous launch, which the bridge appends and syncs to
  /// `Engine/launch-journal.txt` as they happen (`<uptime> <stage>` lines):
  /// after a crash the last line is the last stage reached, where Xenia's own
  /// log may have lost its tail. Logged once, then removed.
  @visibleForTesting
  static Future<List<String>?> takePreviousLaunchJournal() async {
    final journal = File(
      path.join((await engineDirectory()).path, 'launch-journal.txt'),
    );
    try {
      if (!await journal.exists()) return null;
      final stages = (await journal.readAsLines())
          .map((line) => line.trim())
          .where((line) => line.isNotEmpty)
          .toList();
      await journal.delete();
      if (stages.isEmpty) return null;
      final last = stages.last;
      final stage = last.substring(last.indexOf(' ') + 1);
      final summary = 'XeniOS: previous launch stages: ${stages.join(' | ')}';
      if (stage == 'launched' || stage.startsWith('failed: ')) {
        _log.i(summary);
      } else {
        _log.e('$summary (RewindBox ended during the last stage)');
      }
      return stages;
    } on FileSystemException catch (error) {
      _log.w('XeniOS: the previous launch journal is unreadable: $error');
      return null;
    }
  }

  @visibleForTesting
  static Future<void> Function() abortJit = XeniaInternalBridge.abortJit;

  @visibleForTesting
  static Future<Map<String, dynamic>> Function({
    required String gamePath,
    required int contentKind,
    required String title,
    required Map<String, String> settings,
    required Map<String, String> directories,
    String? touchGameKey,
    String locale,
    Map<String, String> texts,
    String overlay,
  })
  bridgeLaunch = XeniaInternalBridge.launch;

  static Future<Map<String, dynamic>> _bridgeLaunch(
    String romPath,
    int kind,
    String title,
    Locale uiLocale,
  ) async {
    await ensureLayout();
    final gameKey = await XeniaSettingsService.gameKeyForFile(romPath);
    _sessionGameKey = gameKey;
    _listenToBridge();
    final values = await settings.launchSettings(
      gameKey: gameKey,
      uiLocale: uiLocale,
      deviceLocale: PlatformDispatcher.instance.locale,
    );
    _log.i(
      'XeniOS launch: ${path.basename(romPath)} key=$gameKey '
      'language=${values['user_language']} country=${values['user_country']}',
    );
    return bridgeLaunch(
      gamePath: romPath,
      contentKind: kind,
      title: title,
      settings: values,
      directories: <String, String>{
        'storageRoot': (await engineDirectory()).path,
        'contentRoot': (await contentDirectory()).path,
        'cacheRoot': (await cacheDirectory()).path,
      },
      // The per-game touch layout uses the same stable identity as the settings.
      touchGameKey: gameKey,
      locale: uiLocale.toLanguageTag(),
      texts: <String, String>{
        for (final key in const [
          'menu',
          'resume',
          'quit',
          ...sessionTextKeys,
        ])
          key: XeniaLocale.forLocale(uiLocale, 'session_$key'),
      },
      overlay: settings.performanceOverlay,
    );
  }

  /// Keys of the launch `texts` map the in-game menu and overlay read, beside
  /// menu/resume/quit (locale key `session_<key>`).
  @visibleForTesting
  static const List<String> sessionTextKeys = <String>[
    'display',
    'overlay',
    'overlayOff',
    'overlaySimple',
    'overlayDetailed',
    'appliesNow',
    'aspect',
    'aspectWide',
    'aspectStandard',
    'resolution',
    'letterbox',
    'on',
    'off',
    'default',
    'thisGame',
    'nextLaunch',
    'fps',
    'frameTime',
    'memory',
    'thermal',
    'thermalNominal',
    'thermalFair',
    'thermalSerious',
    'thermalCritical',
    'saveFailed',
  ];

  /// Game key of the running (last launched) session, for per-game changes
  /// the in-game menu reports.
  static String? _sessionGameKey;
  static StreamSubscription<Map<String, String>>? _settingSubscription;
  static StreamSubscription<String>? _overlaySubscription;
  static StreamSubscription<Map<String, dynamic>>? _sessionSubscription;

  /// Subscribes once, however many launches follow.
  static void _listenToBridge() {
    _settingSubscription ??= XeniaInternalBridge.settingChanges.listen(
      (change) => unawaited(onSettingChanged(change['key'], change['value'])),
    );
    _overlaySubscription ??= XeniaInternalBridge.overlayChanges.listen(
      (level) => unawaited(onOverlayChanged(level)),
    );
    _sessionSubscription ??= XeniaInternalBridge.sessionEvents.listen((event) {
      if (event['event'] == 'ended') _sessionGameKey = null;
    });
  }

  /// A per-game cvar changed in the in-game menu: saved as an override of the
  /// running game when the key is managed and the value accepted.
  @visibleForTesting
  static Future<void> onSettingChanged(String? key, String? value) async {
    final gameKey = _sessionGameKey;
    final option = key == null ? null : XeniaSettingsService.option(key);
    if (gameKey == null || option == null || value == null) {
      _log.w('XeniOS in-game setting ignored: $key=$value');
      return;
    }
    if (!option.accepts(value)) {
      _log.w('XeniOS in-game setting refused: $key=$value');
      return;
    }
    try {
      await settings.setGame(gameKey, key!, value);
    } catch (error) {
      _log.e('XeniOS in-game setting not saved: $key=$value: $error');
    }
  }

  /// The overlay level changed in the in-game menu (global).
  @visibleForTesting
  static Future<void> onOverlayChanged(String? level) async {
    try {
      await settings.setPerformanceOverlay(level ?? '');
    } catch (error) {
      _log.e('XeniOS overlay level not saved: $level: $error');
    }
  }
}
