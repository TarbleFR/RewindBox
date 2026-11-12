import 'dart:async';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' show Locale, PlatformDispatcher;

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import 'package:neostation/l10n/s2arm_engine_locale.dart';
import 'package:neostation/l10n/switch2_settings_locale.dart';
import 's2arm_settings.dart';
import 'logger_service.dart';
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
  const S2ArmImportItem(this.name, this.reason, {this.destination, this.detail});
  final String name;
  final String reason;
  final String? destination;

  /// The native diagnostic of a refusal (what the export check read), shown under the message.
  final String? detail;
  bool get imported => reason == 'imported';
}

class S2ArmImportResult {
  const S2ArmImportResult(this.items, {this.cancelled = false});
  final List<S2ArmImportItem> items;
  final bool cancelled;
  int get imported => items.where((item) => item.imported).length;
  Iterable<S2ArmImportItem> get rejected => items.where((item) => !item.imported && item.reason != 'duplicate');
}

/// A save put in a game's save folder by [S2ArmInternalService.importSave].
class S2ArmSaveImportResult {
  const S2ArmSaveImportResult({
    required this.folder,
    required this.files,
    this.backup,
    this.redirectedTo,
    this.redirectedTitle,
  });
  final String folder;
  final int files;
  final String? backup;

  /// The title id the save names when it is not the selected game's, or when no game was selected: it went to that game's
  /// folder.
  final String? redirectedTo;

  /// That game's title when it is in the library (Documents/S2Arm/Games), else null.
  final String? redirectedTitle;
}

/// A Switch 2 game of Documents/S2Arm/Games that a save can be put in: [S2ArmInternalService.importSave] asks for one
/// when no game is selected and the save does not name its game.
class S2ArmSaveGame {
  const S2ArmSaveGame({required this.title, required this.exportFolder, required this.gid, this.programId});
  final String title;
  final String exportFolder;

  /// The title id, 16 lower-case hex digits.
  final String gid;
  final String? programId;
}

/// Why a save import was refused; [code] is a Switch2LibraryLocale key.
class S2ArmSaveException implements Exception {
  const S2ArmSaveException(this.code);
  final String code;
  @override
  String toString() => 'S2ArmSaveException($code)';
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

  /// Bookmark slots of the two folder picks (game import, save import): each keeps the last folder picked for it.
  static const String importBookmark = 's2arm-import';
  static const String saveImportBookmark = 's2arm-save-import';
  /// Documents/S2Arm/Saves: one folder per game, visible in the Files app, that the engine reads its save from at the start
  /// and writes it back to when the game ends (S2A_SAVE_FOLDER; docs/s2arm-engine-bridge.md, Saves).
  static Future<Directory> savesDirectory() => _child('Saves');

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
      case 'notDownloaded':
        return 'notDownloaded';
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
    // One line per app run in app.log: which part of the engine the native side found (IPA 727 report: the Consoles
    // switch stayed off and the row's reason was not known).
    LoggerService.instance.i('S2Arm status: ${{
      for (final key in const ['enginePresent', 'systemDataPresent', 'helperPresent', 'iosMajor', 'universalHandshake',
          'available', 'ns2proPresent', 'directChain', 'melonxCoreLoaded', 'engineLoaded'])
        key: report[key],
    }}');
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
    // The folder is read where it is (often another app's or the iPhone's own folder): pickAndActivateFolder keeps iOS's
    // security-scoped access open for this session. file_picker's directory pick returns a bare path without it, so the
    // export check could read nothing and refused every game picked outside RewindBox (IPA 727 report).
    final String? folder;
    try {
      folder = await ExternalFolderAccess.pickAndActivateFolder(key: importBookmark);
    } on ExternalFolderAccessException catch (error) {
      return S2ArmImportResult(<S2ArmImportItem>[S2ArmImportItem('', 'storageError', detail: error.toString())]);
    }
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
    final exports = detected['success'] == true
        ? <Map<String, dynamic>>[detected]
        : await _exportsBelow(picked);
    if (exports.isEmpty) {
      // Files that iCloud has not downloaded to the iPhone are only placeholders (".<name>.icloud"): say so.
      final reason = await _hasICloudPlaceholder(picked) ? 'notDownloaded' : (detected['code'] ?? 'notExportFolder').toString();
      final detail = detected['diagnostic']?.toString();
      return S2ArmImportResult(<S2ArmImportItem>[
        S2ArmImportItem(path.basename(picked), reason, detail: detail == null || detail.isEmpty ? null : detail),
      ]);
    }
    final items = <S2ArmImportItem>[];
    try {
      for (var index = 0; index < exports.length; index++) {
        final item = await _importOne(exports[index], games, staging,
            index: index + 1, count: exports.length, onProgress: onProgress, control: control);
        if (item == null) return S2ArmImportResult(items, cancelled: true);
        items.add(item);
      }
    } finally {
      await _removeStaging(staging);
    }
    return S2ArmImportResult(items);
  }

  /// The Switch 2 exports inside [picked] when it is not one itself: a folder that holds the game folder (for example
  /// "<game> + Emulator/<game>/base/exefs/main.npdm") or several games. Looks up to three levels down, never inside an
  /// export's own base / exefs / romfs, and asks detectExport about each candidate that has base/exefs/main.npdm.
  static Future<List<Map<String, dynamic>>> _exportsBelow(String picked) async {
    final found = <Map<String, dynamic>>[];
    var level = <Directory>[Directory(picked)];
    for (var depth = 0; depth < 3 && level.isNotEmpty && found.length < 200; depth++) {
      final next = <Directory>[];
      for (final folder in level) {
        final List<FileSystemEntity> children;
        try {
          children = await folder.list(followLinks: false).toList();
        } on FileSystemException {
          continue;
        }
        children.sort((a, b) => a.path.compareTo(b.path));
        for (final child in children) {
          final name = path.basename(child.path);
          if (child is! Directory || name.startsWith('.') || const {'base', 'exefs', 'romfs'}.contains(name)) continue;
          if (await File(path.join(child.path, 'base', 'exefs', 'main.npdm')).exists()) {
            final detected = await detectExport(child.path);
            if (detected['success'] == true) {
              found.add(detected['exportDir'] == null ? {...detected, 'exportDir': child.path} : detected);
              continue;
            }
          }
          next.add(child);
        }
      }
      level = next;
    }
    return found;
  }

  /// Whether [picked] holds, up to four levels down, a file iCloud has not downloaded yet (".<name>.icloud").
  static Future<bool> _hasICloudPlaceholder(String picked) async {
    try {
      var seen = 0;
      await for (final entry in Directory(picked).list(recursive: true, followLinks: false)) {
        if (++seen > 20000) break;
        if (path.split(path.relative(entry.path, from: picked)).length > 5) continue;
        final name = path.basename(entry.path);
        if (entry is File && name.startsWith('.') && name.endsWith('.icloud')) return true;
      }
    } on FileSystemException {
      return false;
    }
    return false;
  }

  /// Copies one detected export into Games/<title> through staging. Null when the player cancelled.
  static Future<S2ArmImportItem?> _importOne(
    Map<String, dynamic> detected,
    Directory games,
    Directory staging, {
    required int index,
    required int count,
    void Function(S2ArmImportProgress progress)? onProgress,
    S2ArmImportControl? control,
  }) async {
    final exportDir = detected['exportDir'].toString();
    final info = await gameInfo(exportDir);
    final title = _safeName((info['title'] ?? path.basename(exportDir)).toString(), detected['gid']?.toString());

    final source = Directory(exportDir);
    final total = await _directorySize(source);
    final free = freeBytes(games.path);
    if (free != null && free < total + spaceMargin) return S2ArmImportItem(title, 'notEnoughSpace');
    final stage = Directory(path.join(staging.path, '$index'));
    try {
      var done = 0;
      await _copyDirectory(source, stage, control: control, progress: (copied) {
        onProgress?.call(S2ArmImportProgress(name: title, index: index, count: count, done: done + copied, total: total));
      }, onFileDone: (bytes) => done += bytes);
      final target = await _freeDirectory(games, title);
      await stage.rename(target.path);
      return S2ArmImportItem(title, 'imported', destination: target.path);
    } on _Cancelled {
      return null;
    } on FileSystemException catch (error) {
      final osCode = error.osError?.errorCode;
      return S2ArmImportItem(title, osCode == 28 ? 'notEnoughSpace' : 'copyFailed');
    } finally {
      await _removeStaging(stage);
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
    Locale? locale,
  }) async {
    final runtime = await availability();
    if (!runtime.ready) return S2ArmLaunchOutcome.failure(runtime.state.name, runtime.detail);
    if (_launching) return const S2ArmLaunchOutcome.failure('busy');
    _launching = true;
    // The in-game menu speaks RewindBox's language (the app's locale when the caller has it, else the system one).
    final uiLocale = Switch2SettingsLocale.codeFor(locale ?? PlatformDispatcher.instance.locale);
    try {
      final detected = await detectExport(exportFolder);
      if (detected['success'] != true) return S2ArmLaunchOutcome.failure((detected['code'] ?? 'notExportFolder').toString());
      final prepared = await prepare(exportFolder: (detected['exportDir'] ?? exportFolder).toString(), onProgress: onPrepareProgress);
      if (prepared['success'] != true) {
        return S2ArmLaunchOutcome.failure((prepared['code'] ?? 'prepareFailed').toString(), prepared['diagnostic']?.toString());
      }
      final saveFolder = await saveFolderFor((detected['exportDir'] ?? exportFolder).toString());
      final report = await channel.invokeMapMethod<String, dynamic>('launchGame', {
        'gid': prepared['gid'],
        'imagesPath': prepared['imagesPath'],
        'moduleDir': prepared['moduleDir'],
        'gameData': prepared['gameData'],
        'docs': prepared['docs'],
        'pairingFilePath': pairingFilePath,
        'uiLocale': uiLocale,
        'menuStrings': Switch2SettingsLocale.menuStrings(uiLocale),
        if (saveFolder != null) 'saveFolder': saveFolder.path,
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

  // ---------------- saves ----------------

  /// The save folder of the game whose export is [exportFolder]: Documents/S2Arm/Saves/<title> [<TITLE ID>], found again by
  /// its title id (a renamed folder keeps working). Created when missing. Null when the folder is not a Switch 2 export.
  static Future<Directory?> saveFolderFor(String exportFolder) async {
    final detected = await detectExport(exportFolder);
    final gid = detected['gid']?.toString();
    if (detected['success'] != true || gid == null || !_gidPattern.hasMatch(gid)) return null;
    return _saveFolderForId(gid, () async {
      final info = await gameInfo((detected['exportDir'] ?? exportFolder).toString());
      return (info['title'] ?? '').toString();
    });
  }

  /// The save folder tagged with title id [gid], created with the name [title] gives when there is none yet.
  static Future<Directory> _saveFolderForId(String gid, Future<String> Function() title) async {
    final saves = await savesDirectory();
    await saves.create(recursive: true);
    final tag = '[${gid.toUpperCase()}]';
    await for (final entry in saves.list(followLinks: false)) {
      if (entry is Directory && path.basename(entry.path).toUpperCase().endsWith(tag)) return entry;
    }
    final folder = Directory(path.join(saves.path, '${_safeName(await title(), 'Switch 2')} $tag'));
    await folder.create(recursive: true);
    return folder;
  }

  static final RegExp _hex16 = RegExp(r'^[0-9A-Fa-f]{16}$');
  static final RegExp _hex32 = RegExp(r'^[0-9A-Fa-f]{32}$');
  static final RegExp _checkpointName = RegExp(r'^0x([0-9A-Fa-f]{16})(?: .*)?$');

  /// The game a picked save names, as 16 lower-case hex digits, read the way the engine recognizes saves (S2Arm services
  /// SaveFolder.cs Detect): a Ryujinx export (<16 hex>/0 beside ExtraData0, whose first 8 bytes are the program id), a
  /// yuzu tree (0000000000000000/<32 hex user>/<16 hex program>) or a Checkpoint folder ("0x<16 hex> <name>"). Null when
  /// the format names no game (JKSV, plain files, save / save_device) or names several. Visible for tests.
  static Future<String?> saveProgramId(String picked) async {
    final ids = <String>{};
    final root = Directory(picked);
    final checkpoint = _checkpointName.firstMatch(path.basename(path.normalize(root.path)));
    if (checkpoint != null) ids.add(checkpoint.group(1)!.toLowerCase());
    var visited = 0;
    await for (final entry in root.list(recursive: true, followLinks: false)) {
      if (entry is! Directory || ++visited > 4000) continue;
      final name = path.basename(entry.path);
      final match = _checkpointName.firstMatch(name);
      if (match != null) ids.add(match.group(1)!.toLowerCase());
      if (!_hex16.hasMatch(name)) continue;
      // yuzu: …/0000000000000000/<user>/<program>/
      final user = path.basename(path.dirname(entry.path));
      final zero = path.basename(path.dirname(path.dirname(entry.path)));
      if (_hex32.hasMatch(user) && zero == '0000000000000000') ids.add(name.toLowerCase());
      // Ryujinx: …/<16 hex>/0 with ExtraData0 (program id u64, static save id u64 at 0x18 = 0, type 1 or 3 at 0x20).
      final meta = File(path.join(entry.path, 'ExtraData0'));
      if (await Directory(path.join(entry.path, '0')).exists() && await meta.exists() && await meta.length() >= 0x40) {
        final bytes = await meta.openRead(0, 0x40).fold<List<int>>(<int>[], (all, chunk) => all..addAll(chunk));
        final data = ByteData.sublistView(Uint8List.fromList(bytes));
        final program = data.getUint64(0, Endian.little);
        if (program != 0 && data.getUint64(0x18, Endian.little) == 0 && (bytes[0x20] == 1 || bytes[0x20] == 3)) {
          ids.add(program.toRadixString(16).padLeft(16, '0'));
        }
      }
    }
    return ids.length == 1 ? ids.single : null;
  }

  /// The Switch 2 games in Documents/S2Arm/Games, sorted by title: the games a save can be put in when none is selected.
  static Future<List<S2ArmSaveGame>> libraryGames() async {
    final games = await gamesDirectory();
    if (!await games.exists()) return const <S2ArmSaveGame>[];
    final found = <S2ArmSaveGame>[];
    await for (final entry in games.list(followLinks: false)) {
      if (entry is! Directory) continue;
      final detected = await detectExport(entry.path);
      final gid = detected['gid']?.toString().toLowerCase();
      if (detected['success'] != true || gid == null || !_gidPattern.hasMatch(gid)) continue;
      final exportDir = (detected['exportDir'] ?? entry.path).toString();
      final info = await gameInfo(exportDir);
      found.add(S2ArmSaveGame(
        title: (info['title'] ?? path.basename(entry.path)).toString(),
        exportFolder: exportDir,
        gid: gid,
        programId: detected['programId']?.toString().toLowerCase(),
      ));
    }
    found.sort((a, b) => a.title.toLowerCase().compareTo(b.title.toLowerCase()));
    return found;
  }

  /// The title of the library game in Documents/S2Arm/Games whose title id is [gid], or null when none is there.
  static Future<String?> _libraryTitleFor(String gid) async {
    for (final game in await libraryGames()) {
      if (game.gid == gid || game.programId == gid) return game.title;
    }
    return null;
  }

  /// Picks a save folder in Files (exported from a console with JKSV or Checkpoint, or copied from Ryujinx / yuzu) and puts
  /// it in the save folder of the game at [exportFolder]. The engine reads it the next time the game starts.
  ///
  /// With no game selected ([exportFolder] null), the save goes to the game it names. A save that names no game (JKSV,
  /// plain files) goes to the library game [chooseGame] returns; it is refused with saveNoGame when the library has no
  /// game or no [chooseGame] is given. Returns null when the picker or the choice was dismissed.
  static Future<S2ArmSaveImportResult?> importSave(String? exportFolder, {String? dialogTitle,
      Future<S2ArmSaveGame?> Function(List<S2ArmSaveGame> games)? chooseGame}) =>
      StorageImportActivity.run(() async {
    if (_sessionRunning) throw const S2ArmSaveException('saveGameRunning');
    final String? picked;
    try {
      picked = await ExternalFolderAccess.pickAndActivateFolder(key: saveImportBookmark);
    } on ExternalFolderAccessException {
      throw const S2ArmSaveException('saveFailed');
    }
    if (picked == null) return null;
    var game = exportFolder;
    if (game == null && await saveProgramId(picked) == null) {
      final games = await libraryGames();
      if (games.isEmpty || chooseGame == null) throw const S2ArmSaveException('saveNoGame');
      final chosen = await chooseGame(games);
      if (chosen == null) return null;
      game = chosen.exportFolder;
    }
    return importSaveAt(game, picked);
  });

  /// Copies the folder [picked] into the game's save folder, as one sub-folder, so the engine's own recognition (JKSV,
  /// Checkpoint, Ryujinx, yuzu, NX2Apple, plain files) sees it as picked. What the save folder held before is kept beside
  /// it as "<name> (backup)" (one backup, replaced by the next import). With [exportFolder] null, the save must name its
  /// game (saveNoGame otherwise). Visible for tests.
  static Future<S2ArmSaveImportResult> importSaveAt(String? exportFolder, String picked) async {
    var own = const <String?>{};
    if (exportFolder != null) {
      final selected = await detectExport(exportFolder);
      final selectedGid = selected['gid']?.toString();
      if (selected['success'] != true || selectedGid == null || !_gidPattern.hasMatch(selectedGid)) {
        throw const S2ArmSaveException('saveNotExport');
      }
      own = {selectedGid.toLowerCase(), selected['programId']?.toString().toLowerCase()};
    }
    final source = Directory(picked);
    if (!await source.exists()) throw const S2ArmSaveException('saveEmpty');
    // A save that names another game goes to that game's folder: the player picked the wrong game in the list, or none.
    final saveId = await saveProgramId(picked);
    String? redirectedTo;
    String? redirectedTitle;
    final Directory target;
    if (saveId != null && !own.contains(saveId)) {
      redirectedTo = saveId.toUpperCase();
      redirectedTitle = await _libraryTitleFor(saveId);
      target = await _saveFolderForId(saveId, () async => redirectedTitle ?? '');
    } else if (exportFolder == null) {
      throw const S2ArmSaveException('saveNoGame');
    } else {
      final folder = await saveFolderFor(exportFolder);
      if (folder == null) throw const S2ArmSaveException('saveNotExport');
      target = folder;
    }
    final normalizedSource = path.normalize(source.absolute.path);
    final normalizedTarget = path.normalize(target.absolute.path);
    final saves = path.normalize((await savesDirectory()).absolute.path);
    if (normalizedSource == normalizedTarget || path.isWithin(normalizedTarget, normalizedSource) ||
        path.isWithin(normalizedSource, normalizedTarget) || normalizedSource == saves) {
      throw const S2ArmSaveException('saveSameFolder');
    }
    final files = await source.list(recursive: true, followLinks: false).where((entry) => entry is File).length;
    if (files == 0) throw const S2ArmSaveException('saveEmpty');
    // Keep what the folder held (the progress the engine last wrote back) before replacing it.
    final backup = Directory('${target.path} (backup)');
    if (!await target.list().isEmpty) {
      if (await backup.exists()) await backup.delete(recursive: true);
      await target.rename(backup.path);
      await target.create(recursive: true);
    }
    final name = path.basename(normalizedSource);
    await _copyTree(source, Directory(path.join(target.path, name.isEmpty ? 'save' : name)));
    return S2ArmSaveImportResult(
      folder: target.path,
      files: files,
      backup: await backup.exists() ? backup.path : null,
      redirectedTo: redirectedTo,
      redirectedTitle: redirectedTitle,
    );
  }

  /// Opens the game's save folder in the Files app (creating it first), or Documents/S2Arm/Saves itself when no game is
  /// selected ([exportFolder] null). False when Files could not be opened.
  static Future<bool> openSaveFolder(String? exportFolder) async {
    final Directory? folder;
    if (exportFolder == null) {
      final saves = await savesDirectory();
      await saves.create(recursive: true);
      folder = saves;
    } else {
      folder = await saveFolderFor(exportFolder);
    }
    if (folder == null) return false;
    try {
      return await channel.invokeMethod<bool>('openFolder', {'path': folder.path}) ?? false;
    } on MissingPluginException {
      return false;
    } on PlatformException {
      return false;
    }
  }

  static Future<void> _copyTree(Directory from, Directory to) async {
    await to.create(recursive: true);
    await for (final entry in from.list(followLinks: false)) {
      final destination = path.join(to.path, path.basename(entry.path));
      if (entry is Directory) {
        await _copyTree(entry, Directory(destination));
      } else if (entry is File) {
        await entry.copy(destination);
      }
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
