import 'dart:async';
import 'dart:io';
import 'dart:ui' show Locale, PlatformDispatcher;

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

  static Future<String?> _refusal(File source) async {
    switch (XeniaContent.kindForName(source.path)) {
      case XeniaContentKind.profile:
        return 'profileNotGame';
      case XeniaContentKind.touchLayout:
        return 'touchLayoutNotGame';
      case XeniaContentKind.looseExecutable:
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
        _ => null,
      };

  /// Boots [romPath] in the embedded engine with this game's effective
  /// settings. Never reports success unless the bridge booted the title.
  static Future<XeniaLaunchOutcome> launch({
    required String romPath,
    required String title,
    required Locale uiLocale,
  }) async {
    final runtime = await availability();
    if (!runtime.ready) {
      return XeniaLaunchOutcome.failure(runtime.state.name, runtime.detail);
    }
    // The dedicated XeniOS JIT helper, only when the Core needs it
    // (docs/xenios-playlist.md § JIT helper).
    final jit = await XeniaJitService.ensure();
    if (!jit.success) return XeniaLaunchOutcome.failure(jit.error, jit.detail);
    final kind = contentKindFor(romPath);
    if (kind == null) return const XeniaLaunchOutcome.failure('unsupported');
    if (!await File(romPath).exists()) {
      return const XeniaLaunchOutcome.failure('gameUnreadable');
    }
    await ensureLayout();
    final gameKey = await XeniaSettingsService.gameKeyForFile(romPath);
    final values = await settings.launchSettings(
      gameKey: gameKey,
      uiLocale: uiLocale,
      deviceLocale: PlatformDispatcher.instance.locale,
    );
    _log.i(
      'XeniOS launch: ${path.basename(romPath)} key=$gameKey '
      'language=${values['user_language']} country=${values['user_country']}',
    );
    final report = await XeniaInternalBridge.launch(
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
        for (final key in const ['menu', 'resume', 'quit'])
          key: XeniaLocale.forLocale(uiLocale, 'session_$key'),
      },
    );
    if (report['success'] == true) return const XeniaLaunchOutcome.success();
    final error = report['error']?.toString() ?? 'launchFailed';
    _log.e('XeniOS launch failed: $error ${report['detail'] ?? ''}');
    return XeniaLaunchOutcome.failure(error, report['detail']?.toString());
  }
}
