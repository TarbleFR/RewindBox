import 'dart:async';
import 'dart:io';
import 'dart:ui' show Locale, PlatformDispatcher;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import 'package:neostation/l10n/s2arm_engine_locale.dart';
import 'package:neostation/l10n/switch2_settings_locale.dart';
import 's2arm_settings.dart';
import 'storage/storage_import_activity.dart';
import 'switch2_export_content.dart';
import 'storage/storage_stat_ffi.dart';

export 's2arm_settings.dart';

/// Why the embedded Switch 2 engine cannot run, shown as a reason in the Consoles tab.
enum S2ArmRuntimeState {
  ready,
  engineMissing,       // no S2ArmEngine.framework in this build
  jitHelperMissing,    // the S2Arm JIT helper extension is absent
  systemDataMissing,   // the engine's system data is absent
  requiresIOS26,       // the universal JIT handshake needs iOS 26
  unsupportedPlatform, // not iOS
  unknown,
}

class S2ArmRuntimeAvailability {
  const S2ArmRuntimeAvailability(this.state, {this.detail});
  final S2ArmRuntimeState state;
  final String? detail;
  bool get ready => state == S2ArmRuntimeState.ready;
}

/// Outcome of one game in a Switch 2 import. [reason] is an S2ArmEngineLocale key (or 'imported' / 'duplicate').
class S2ArmImportItem {
  const S2ArmImportItem(this.name, this.reason, {this.destination});
  final String name;
  final String reason;
  final String? destination;
  bool get imported => reason == 'imported';
}

class S2ArmImportResult {
  const S2ArmImportResult(this.items, {this.cancelled = false});
  final List<S2ArmImportItem> items;
  final bool cancelled;
  int get imported => items.where((item) => item.imported).length;
  Iterable<S2ArmImportItem> get rejected => items.where((item) => !item.imported && item.reason != 'duplicate');
}

class S2ArmImportProgress {
  const S2ArmImportProgress({required this.name, required this.index, required this.count, required this.done, required this.total});
  final String name;
  final int index;
  final int count;
  final int done;
  final int total;
  double? get fraction => total <= 0 ? null : (done / total).clamp(0.0, 1.0);
}

class S2ArmImportControl {
  bool _cancelled = false;
  bool get cancelled => _cancelled;
  void cancel() => _cancelled = true;
}

class _Cancelled implements Exception {}

/// Result of a launch request; [error] is an S2ArmEngineLocale key.
class S2ArmLaunchOutcome {
  const S2ArmLaunchOutcome.success() : success = true, error = null, detail = null;
  const S2ArmLaunchOutcome.failure(this.error, [this.detail]) : success = false;
  final bool success;
  final String? error;
  final String? detail;
}

/// A native session-end event delivered to [sessionEvents].
class S2ArmSessionEvent {
  const S2ArmSessionEvent(this.code, this.reason);
  final int code;
  final String reason;
  bool get normal => code == 0;
}

/// Storage, import, preparation and launch of the Switch 2 (S2Arm) embedded engine (docs/s2arm-engine-bridge.md).
/// Files-visible layout under Documents/S2Arm: `Games` (one export folder per game, filled by import or by the Files app).
/// Private to the engine (never exported): `Library/S2Arm/<gid>` (prepared per-game files), written by the native host.
/// Mirrors lib/services/xenia_internal_service.dart so the shared library layer calls both the same way.
abstract final class S2ArmInternalService {
  static const channel = MethodChannel('neostation/s2arm_internal');

  static const String systemFolder = 'switch2';
  static const String sessionExecutable = 'ios_s2arm_internal';

  /// Kept free on the volume beyond the copied game.
  static const int spaceMargin = 512 * 1024 * 1024;
  static const int _chunk = 4 * 1024 * 1024;

  @visibleForTesting
  static Future<Directory> Function() documentsDirectory = getApplicationDocumentsDirectory;

  @visibleForTesting
  static int? Function(String path) freeBytes = _statFreeBytes;
  static int? _statFreeBytes(String location) => StorageStatFfi.tryLoad()?.statvfs(location)?.freeBytes;

  static Future<Directory> rootDirectory() async => Directory(path.join((await documentsDirectory()).path, 'S2Arm'));
  static Future<Directory> _child(String name) async => Directory(path.join((await rootDirectory()).path, name));
  static Future<Directory> gamesDirectory() => _child('Games');
  static Future<Directory> stagingDirectory() => _child('.importing');

  static Future<void> ensureLayout() async {
    await (await gamesDirectory()).create(recursive: true);
  }

  // ---------------- session events ----------------

  static final StreamController<S2ArmSessionEvent> _sessionEvents = StreamController<S2ArmSessionEvent>.broadcast();
  static Stream<S2ArmSessionEvent> get sessionEvents => _sessionEvents.stream;

  static bool _handlerInstalled = false;
  static void Function(S2ArmImportProgress progress)? _activePrepareProgress;

  static void _installHandler() {
    if (_handlerInstalled) return;
    _handlerInstalled = true;
    channel.setMethodCallHandler((call) async {
      if (call.arguments is! Map) return null;
      final arguments = Map<String, dynamic>.from(call.arguments as Map);
      if (call.method == 'prepareProgress') {
        final progress = _activePrepareProgress;
        if (progress != null) {
          progress(S2ArmImportProgress(
            name: arguments['step']?.toString() ?? '',
            index: (arguments['index'] as num?)?.toInt() ?? 0,
            count: (arguments['count'] as num?)?.toInt() ?? 0,
            done: (((arguments['fraction'] as num?)?.toDouble() ?? 0) * 1000).round(),
            total: 1000,
          ));
        }
      } else if (call.method == 'sessionEnded') {
        _sessionRunning = false;
        _sessionEvents.add(S2ArmSessionEvent((arguments['code'] as num?)?.toInt() ?? 0, arguments['reason']?.toString() ?? ''));
      }
      return null;
    });
  }

  // ---------------- error mapping ----------------

  /// The native error/code -> localized-message key. Public so the UI and the tests map the same way.
  static String messageKey(String? code) {
    switch (code) {
      case 'engineRestartRequired':
        return 'restartRequired';
      case 'notExportFolder':
        return 'notExportFolder';
      case 'exportInvalid':
      case 'gameIdMismatch':
        return 'exportInvalid';
      case 'gameUnsupported':
        return 'gameUnsupported';
      case 'rewriterFailed':
      case 'prepareFailed':
        return 'rewriterFailed';
      case 'storageError':
      case 'copyFailed':
        return 'storageError';
      case 'insufficientSpace':
      case 'notEnoughSpace':
        return 'insufficientSpace';
      case 'systemDataMissing':
        return 'systemDataMissing';
      case 'engineChainMissing':
      case 'enginePresent':
      case 'engineMissing':
        return 'engineChainMissing';
      case 'jitUnavailable':
      case 'jitPairingRequired':
      case 'jitHelperMissing':
        return 'jitUnavailable';
      case 'cancelled':
        return 'cancelled';
      case 'unavailable':
      case 'runtimeUnavailable':
      case 'unsupportedPlatform':
        return 'unavailable';
      default:
        return 'launchFailed';
    }
  }

  /// The localized message for a native result ({success:false, code|error}) or a reason key.
  static String localizedError(Locale locale, Object? codeOrResult) {
    final code = codeOrResult is Map ? (codeOrResult['code'] ?? codeOrResult['error'])?.toString() : codeOrResult?.toString();
    return S2ArmEngineLocale.text(locale, messageKey(code));
  }

  // ---------------- availability ----------------

  static S2ArmRuntimeAvailability? _availability;

  @visibleForTesting
  static set availabilityForTesting(S2ArmRuntimeAvailability? value) => _availability = value;

  /// Whether this device and build can run S2Arm. Cached for the process: neither the OS version nor the bundled
  /// framework change while it runs.
  static Future<S2ArmRuntimeAvailability> availability() async => _availability ??= await _readAvailability();

  static Future<S2ArmRuntimeAvailability> _readAvailability() async {
    if (defaultTargetPlatform != TargetPlatform.iOS) {
      return const S2ArmRuntimeAvailability(S2ArmRuntimeState.unsupportedPlatform);
    }
    final report = await status();
    if (report['enginePresent'] != true) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.engineMissing);
    if (report['systemDataPresent'] != true) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.systemDataMissing);
    if (report['helperPresent'] != true) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.jitHelperMissing);
    final major = (report['iosMajor'] as num?)?.toInt() ?? 0;
    if (report['universalHandshake'] != true && major < 26) {
      return const S2ArmRuntimeAvailability(S2ArmRuntimeState.requiresIOS26);
    }
    if (report['available'] == true) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.ready);
    return const S2ArmRuntimeAvailability(S2ArmRuntimeState.unknown);
  }

  static Future<Map<String, dynamic>> status() async {
    _installHandler();
    try {
      final report = await channel.invokeMapMethod<String, dynamic>('status');
      return report == null ? {'available': false} : Map<String, dynamic>.from(report);
    } on MissingPluginException {
      return {'available': false};
    } on PlatformException {
      return {'available': false};
    }
  }

  // ---------------- game info ----------------

  /// The export folder's display metadata (titleId, title, publisher, displayVersion, iconPath) for the library scan and
  /// scraping (NACP title as the ScreenScraper name, icon.jpg copied as box2d). {success:false, code} when it is not an export.
  static Future<Map<String, dynamic>> gameInfo(String exportFolder, {Locale? locale}) async {
    _installHandler();
    try {
      final report = await channel.invokeMapMethod<String, dynamic>('gameInfo', {
        'exportFolder': exportFolder,
        'locale': (locale ?? PlatformDispatcher.instance.locale).toLanguageTag(),
      });
      return report == null ? {'success': false, 'code': 'exportInvalid'} : Map<String, dynamic>.from(report);
    } on MissingPluginException {
      return {'success': false, 'code': 'unavailable'};
    } on PlatformException catch (error) {
      return {'success': false, 'code': error.code};
    }
  }

  /// Validates a folder through the native ns2-detect equivalent. {success, exportDir, gid, programId} or {success:false,code}.
  static Future<Map<String, dynamic>> detectExport(String folder) async {
    _installHandler();
    try {
      final report = await channel.invokeMapMethod<String, dynamic>('detectExport', {'exportFolder': folder});
      return report == null ? {'success': false, 'code': 'exportInvalid'} : Map<String, dynamic>.from(report);
    } on MissingPluginException {
      return {'success': false, 'code': 'unavailable'};
    } on PlatformException catch (error) {
      return {'success': false, 'code': error.code};
    }
  }

  // ---------------- import ----------------

  /// Picks a folder in Files and imports the Switch 2 export it holds. Returns null when the picker was dismissed.
  static Future<S2ArmImportResult?> importFolder({
    String? dialogTitle,
    void Function(S2ArmImportProgress progress)? onProgress,
    S2ArmImportControl? control,
  }) => StorageImportActivity.run(() async {
    await ensureLayout();
    final folder = await FilePicker.getDirectoryPath(dialogTitle: dialogTitle, lockParentWindow: true);
    if (folder == null) return null;
    return importFolderAt(folder, onProgress: onProgress, control: control);
  });

  /// Imports the export at [picked] (a readable local folder). Visible for tests. Refuses a folder that detectExport does
  /// not recognise as a Switch 2 export. Copies into staging beside Games, then renames, so the scan never sees a partial game.
  static Future<S2ArmImportResult> importFolderAt(
    String picked, {
    void Function(S2ArmImportProgress progress)? onProgress,
    S2ArmImportControl? control,
  }) async {
    await ensureLayout();
    final games = await gamesDirectory();
    final staging = await stagingDirectory();
    await _removeStaging(staging);

    final detected = await detectExport(picked);
    if (detected['success'] != true) {
      return S2ArmImportResult(<S2ArmImportItem>[S2ArmImportItem(path.basename(picked), (detected['code'] ?? 'notExportFolder').toString())]);
    }
    final exportDir = (detected['exportDir'] ?? picked).toString();
    final info = await gameInfo(exportDir);
    final title = _safeName((info['title'] ?? path.basename(exportDir)).toString(), detected['gid']?.toString());

    final source = Directory(exportDir);
    final total = await _directorySize(source);
    final free = freeBytes(games.path);
    if (free != null && free < total + spaceMargin) {
      return S2ArmImportResult(<S2ArmImportItem>[S2ArmImportItem(title, 'notEnoughSpace')]);
    }
    final stage = Directory(path.join(staging.path, '0'));
    try {
      var done = 0;
      await _copyDirectory(source, stage, control: control, progress: (copied) {
        onProgress?.call(S2ArmImportProgress(name: title, index: 1, count: 1, done: done + copied, total: total));
      }, onFileDone: (bytes) => done += bytes);
      final target = await _freeDirectory(games, title);
      await stage.rename(target.path);
      return S2ArmImportResult(<S2ArmImportItem>[S2ArmImportItem(title, 'imported', destination: target.path)]);
    } on _Cancelled {
      return const S2ArmImportResult(<S2ArmImportItem>[], cancelled: true);
    } on FileSystemException catch (error) {
      final osCode = error.osError?.errorCode;
      return S2ArmImportResult(<S2ArmImportItem>[S2ArmImportItem(title, osCode == 28 ? 'notEnoughSpace' : 'copyFailed')]);
    } finally {
      await _removeStaging(stage);
      await _removeStaging(staging);
    }
  }

  static Future<void> _removeStaging(Directory directory) async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } on FileSystemException {
      // Best effort.
    }
  }

  static Future<int> _directorySize(Directory directory) async {
    var total = 0;
    await for (final entry in directory.list(recursive: true, followLinks: false)) {
      if (entry is File) {
        try {
          total += await entry.length();
        } on FileSystemException {
          // Skipped from the estimate; the copy surfaces a real error.
        }
      }
    }
    return total;
  }

  static Future<void> _copyDirectory(
    Directory source,
    Directory destination, {
    S2ArmImportControl? control,
    void Function(int copied)? progress,
    void Function(int bytes)? onFileDone,
  }) async {
    await destination.create(recursive: true);
    await for (final entry in source.list(followLinks: false)) {
      if (control?.cancelled ?? false) throw _Cancelled();
      final target = path.join(destination.path, path.basename(entry.path));
      if (entry is Directory) {
        await _copyDirectory(entry, Directory(target), control: control, progress: progress, onFileDone: onFileDone);
      } else if (entry is File) {
        final expected = await entry.length();
        await _copyBytes(entry, File(target), control: control, progress: progress);
        if (await File(target).length() != expected) throw const FileSystemException('Copied length mismatch');
        onFileDone?.call(expected);
      } else if (entry is Link) {
        await Link(target).create(await entry.target(), recursive: true);
      }
    }
  }

  static Future<void> _copyBytes(File source, File target, {S2ArmImportControl? control, void Function(int copied)? progress}) async {
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

  static String _safeName(String value, [String? fallback]) {
    final cleaned = value.replaceAll(RegExp(r'[\x00-\x1F/\\:*?"<>|]'), ' ').replaceAll(RegExp(r'\s+'), ' ').trim();
    return cleaned.isEmpty || cleaned.startsWith('.') ? (fallback ?? 'Switch 2 game') : cleaned;
  }

  static Future<Directory> _freeDirectory(Directory games, String title) async {
    var target = Directory(path.join(games.path, title));
    for (var index = 2; await target.exists() || await File(target.path).exists(); index++) {
      if (index > 9999) throw const FileSystemException('No free destination name');
      target = Directory(path.join(games.path, '$title ($index)'));
    }
    return target;
  }

  // ---------------- prepare ----------------

  static bool _preparing = false;

  /// Prepares an imported game for the engine. Returns the native map (gid, imagesPath, moduleDir, gameData, docs, sizes,
  /// durationsMs) or {success:false, code}.
  static Future<Map<String, dynamic>> prepare({
    required String exportFolder,
    String? directChain,
    String? systemDataFolder,
    void Function(S2ArmImportProgress progress)? onProgress,
  }) async {
    _installHandler();
    if (_preparing) return {'success': false, 'code': 'prepareBusy'};
    _preparing = true;
    _activePrepareProgress = onProgress;
    try {
      final report = await channel.invokeMapMethod<String, dynamic>('prepareGame', {
        'exportFolder': exportFolder,
        if (directChain != null) 'directChain': directChain,
        if (systemDataFolder != null) 'systemDataFolder': systemDataFolder,
      });
      return report == null ? {'success': false, 'code': 'prepareFailed'} : Map<String, dynamic>.from(report);
    } on MissingPluginException {
      return {'success': false, 'code': 'unavailable'};
    } on PlatformException catch (error) {
      return {'success': false, 'code': error.code, 'diagnostic': error.message};
    } finally {
      _activePrepareProgress = null;
      _preparing = false;
    }
  }

  static Future<void> cancelPrepare() async {
    try {
      await channel.invokeMethod<void>('cancelPrepare');
    } on PlatformException {
      // The preparation polls the flag between steps.
    } on MissingPluginException {
      // No native side here.
    }
  }

  // ---------------- settings ----------------

  /// The stored engine settings, or null when this is not iOS or the native side does not answer.
  static Future<S2ArmSettings?> loadSettings() async {
    if (defaultTargetPlatform != TargetPlatform.iOS) return null;
    try {
      final map = await channel.invokeMapMethod<String, Object?>('getSettings');
      return map == null ? null : S2ArmSettings.fromMap(map);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  /// Stores [settings]; returns what the native side kept after validation, or null when it did not answer.
  static Future<S2ArmSettings?> saveSettings(S2ArmSettings settings) async {
    if (defaultTargetPlatform != TargetPlatform.iOS) return null;
    try {
      final map = await channel.invokeMapMethod<String, Object?>('setSettings', settings.toMap());
      return map == null ? null : S2ArmSettings.fromMap(map);
    } on MissingPluginException {
      return null;
    } on PlatformException {
      return null;
    }
  }

  // ---------------- launch ----------------

  static bool _launching = false;

  /// True from a successful launch until the native `sessionEnded` event.
  static bool _sessionRunning = false;

  /// A game is being prepared, launched or running: its files must not be deleted.
  static bool get busy => _preparing || _launching || _sessionRunning;

  @visibleForTesting
  static set sessionRunningForTesting(bool value) => _sessionRunning = value;

  /// Launches the game at [exportFolder], preparing it first when its engine files are not ready. [pairingFilePath] is the
  /// stored JIT pairing file. Reports success only when the engine configured and started.
  static Future<S2ArmLaunchOutcome> launch(
    String exportFolder, {
    required String pairingFilePath,
    void Function(S2ArmImportProgress progress)? onPrepareProgress,
  }) async {
    final runtime = await availability();
    if (!runtime.ready) return S2ArmLaunchOutcome.failure(runtime.state.name, runtime.detail);
    if (_launching) return const S2ArmLaunchOutcome.failure('busy');
    _launching = true;
    final uiLocale = Switch2SettingsLocale.codeFor(PlatformDispatcher.instance.locale);
    try {
      final detected = await detectExport(exportFolder);
      if (detected['success'] != true) return S2ArmLaunchOutcome.failure((detected['code'] ?? 'notExportFolder').toString());
      final prepared = await prepare(exportFolder: (detected['exportDir'] ?? exportFolder).toString(), onProgress: onPrepareProgress);
      if (prepared['success'] != true) {
        return S2ArmLaunchOutcome.failure((prepared['code'] ?? 'prepareFailed').toString(), prepared['diagnostic']?.toString());
      }
      final report = await channel.invokeMapMethod<String, dynamic>('launchGame', {
        'gid': prepared['gid'],
        'imagesPath': prepared['imagesPath'],
        'moduleDir': prepared['moduleDir'],
        'gameData': prepared['gameData'],
        'docs': prepared['docs'],
        'pairingFilePath': pairingFilePath,
        'uiLocale': uiLocale,
        'menuStrings': Switch2SettingsLocale.menuStrings(uiLocale),
      });
      if (report?['success'] == true) {
        _sessionRunning = true;
        return const S2ArmLaunchOutcome.success();
      }
      return S2ArmLaunchOutcome.failure((report?['error'] ?? 'launchFailed').toString(), report?['diagnostic']?.toString());
    } on MissingPluginException {
      return const S2ArmLaunchOutcome.failure('unavailable');
    } on PlatformException catch (error) {
      return S2ArmLaunchOutcome.failure(error.code, error.message);
    } finally {
      _launching = false;
    }
  }

  // ---------------- delete ----------------

  /// The app's private `Library` folder, where the native host keeps `S2Arm/<gid>`.
  @visibleForTesting
  static Future<Directory> Function() libraryDirectory = getLibraryDirectory;

  static final RegExp _gidPattern = RegExp(r'^[0-9A-Fa-f]{16}$');

  /// Whether the export of library entry [romPath] is inside RewindBox's own `Documents/S2Arm/Games`.
  static Future<bool> isInsideGames(String romPath) async {
    final games = path.normalize((await gamesDirectory()).path);
    return path.isWithin(games, path.normalize(Switch2ExportContent.exportFolder(romPath)));
  }

  /// Deletes the Switch 2 game whose library entry is [romPath] (`<export>/base/exefs/main.npdm`).
  /// - refused with [S2ArmDeleteException] `deleteBusy` while a game is preparing, launching or running;
  /// - the game's prepared data `Library/S2Arm/<gid>` is deleted except `docs` (saves are kept);
  /// - the export folder is deleted only when it is inside RewindBox's own `Documents/S2Arm/Games`; a user-linked
  ///   export elsewhere is left untouched on disk.
  /// Returns true when the export folder was deleted. The caller removes the database row and media.
  static Future<bool> deleteGame(String romPath) async {
    if (busy) throw const S2ArmDeleteException('deleteBusy');
    final target = path.normalize(Switch2ExportContent.exportFolder(romPath));
    final inside = await isInsideGames(romPath);
    // The gid comes from the export itself, so the prepared data is removed before the export.
    String? gid;
    if (await Directory(target).exists()) {
      final detected = await detectExport(target);
      final value = detected['gid']?.toString();
      if (detected['success'] == true && value != null && _gidPattern.hasMatch(value)) gid = value;
    }
    if (gid != null) await _deletePrepared(gid);
    if (!inside) return false;
    if (await FileSystemEntity.isLink(target)) {
      await Link(target).delete();
      return true;
    }
    final directory = Directory(target);
    if (await directory.exists()) await directory.delete(recursive: true);
    return true;
  }

  /// Everything in `Library/S2Arm/<gid>` except `docs`, which holds the saves.
  static Future<void> _deletePrepared(String gid) async {
    final Directory library;
    try {
      library = await libraryDirectory();
    } on UnsupportedError {
      return;
    } on MissingPluginException {
      return;
    }
    final prepared = Directory(path.join(library.path, 'S2Arm', gid));
    if (!await prepared.exists()) return;
    await for (final entry in prepared.list(followLinks: false)) {
      if (path.basename(entry.path) == 'docs') continue;
      if (entry is Directory) {
        await entry.delete(recursive: true);
      } else {
        await entry.delete();
      }
    }
  }
}

/// A refused or failed Switch 2 game deletion; [code] is a Switch2LibraryLocale key.
class S2ArmDeleteException implements Exception {
  const S2ArmDeleteException(this.code);
  final String code;
  @override
  String toString() => code;
}
