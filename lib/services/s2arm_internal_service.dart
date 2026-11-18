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

typedef _TitleSaveSlot = ({String program, Directory folder});

class S2ArmImportProgress {
  const S2ArmImportProgress({
    required this.name,
    required this.index,
    required this.count,
    required this.done,
    required this.total,
    this.step,
    this.part,
    this.phase,
    this.attempt = 0,
    this.unitsDone,
    this.unitsTotal,
    this.overall,
  });
  final String name;
  final int index;
  final int count;
  final int done;
  final int total;
  double? get fraction => total <= 0 ? null : (done / total).clamp(0.0, 1.0);

  // Import stages are 'scan', 'clone', 'nup' (unpacked bytes), and null (folder copy).
  // For launch preparation the step is unpack, code, caps, direct, module, pack or done. part: the
  // code stage's part (zbic, addr_need, nro, a module such as main, tables) or "reused". phase: the part's phase (a
  // pass of the rewriter, "walk", "zbic"...). attempt: 2... when the rewriter redoes a module with a new layout.
  // unitsDone / unitsTotal: the phase's own counts (functions, rewrite units, bytes, files), total 0 = no count.
  final String? step;
  final String? part;
  final String? phase;
  final int attempt;
  final int? unitsDone;
  final int? unitsTotal;

  /// The whole preparation in [0, 1], weighted by step ([S2ArmInternalService.preparationOverall]).
  final double? overall;
}

class S2ArmImportControl {
  bool _cancelled = false;
  bool get cancelled => _cancelled;

  /// Also stops the native work in progress (a NUP expansion), set by the service while it runs.
  void Function()? _onCancel;
  void cancel() {
    _cancelled = true;
    _onCancel?.call();
  }
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

  /// The space an import may use at [location]. On iOS it is the capacity the system gives a task the user asked for:
  /// it counts what iOS can purge (caches), as the Settings app does. [freeBytes] (statvfs) counts none of it, and IPA 728
  /// refused Mario Kart World as "not enough space" while Settings showed about 68 GB available. Falls back to
  /// [freeBytes] when the native side does not answer. Visible for tests.
  @visibleForTesting
  static Future<int?> Function(String path) availableBytes = _availableBytes;
  static Future<int?> _availableBytes(String location) async {
    if (defaultTargetPlatform == TargetPlatform.iOS) {
      try {
        final info = await channel.invokeMapMethod<String, dynamic>('storageInfo', {'path': location});
        final important = (info?['importantFreeBytes'] as num?)?.toInt();
        if (important != null && important > 0) return important;
      } on MissingPluginException {
        // No native side: statvfs below.
      } on PlatformException {
        // statvfs below.
      }
    }
    return freeBytes(location);
  }

  /// Clones the folder [from] to [to] (APFS copy-on-write, clonefile(2)): instant, and no space is taken until a file
  /// changes; game files are only read. False when it cannot (another volume or file system, not iOS): the import then
  /// copies. Visible for tests.
  @visibleForTesting
  static Future<bool> Function(String from, String to) cloneTree = _cloneTree;
  static Future<bool> _cloneTree(String from, String to) async {
    if (defaultTargetPlatform != TargetPlatform.iOS) return false;
    try {
      final report = await channel.invokeMapMethod<String, dynamic>('cloneTree', {'from': from, 'to': to});
      if (report?['success'] == true) return true;
      LoggerService.instance.i('S2Arm import: no clone (errno ${report?['errno']}), copying instead');
    } on MissingPluginException {
      // Not iOS.
    } on PlatformException catch (error) {
      LoggerService.instance.i('S2Arm import: no clone (${error.code}), copying instead');
    }
    return false;
  }

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
  static void Function(int done, int total)? _activeNupProgress;

  static void _installHandler() {
    if (_handlerInstalled) return;
    _handlerInstalled = true;
    channel.setMethodCallHandler((call) async {
      if (call.arguments is! Map) return null;
      final arguments = Map<String, dynamic>.from(call.arguments as Map);
      if (call.method == 'prepareProgress') {
        final step = arguments['step']?.toString() ?? '';
        final detail = arguments['detail']?.toString() ?? '';
        _logPrepareStep(step, detail);
        final progress = _activePrepareProgress;
        if (progress != null) {
          final fraction = ((arguments['fraction'] as num?)?.toDouble() ?? 0).clamp(0.0, 1.0);
          progress(S2ArmImportProgress(
            // "code · main": the module the code stage is on, so a long stage visibly moves.
            name: detail.isEmpty ? step : '$step · $detail',
            index: (arguments['index'] as num?)?.toInt() ?? 0,
            count: (arguments['count'] as num?)?.toInt() ?? 0,
            done: (fraction * 1000).round(),
            total: 1000,
            step: step,
            part: detail.isEmpty ? null : detail,
            phase: arguments['phase']?.toString(),
            attempt: (arguments['attempt'] as num?)?.toInt() ?? 0,
            unitsDone: (arguments['done'] as num?)?.toInt(),
            unitsTotal: (arguments['total'] as num?)?.toInt(),
            overall: preparationOverall(step, fraction),
          ));
        }
      } else if (call.method == 'nupProgress') {
        _activeNupProgress?.call((arguments['done'] as num?)?.toInt() ?? 0, (arguments['total'] as num?)?.toInt() ?? 0);
      } else if (call.method == 'sessionEnded') {
        _sessionEndSerial++;
        _sessionRunning = false;
        _sessionEvents.add(S2ArmSessionEvent((arguments['code'] as num?)?.toInt() ?? 0, arguments['reason']?.toString() ?? ''));
      }
      return null;
    });
  }

  // ---------------- preparation progress ----------------

  /// The share of a whole preparation each step takes on the bar: the code stage (the rewriter) is by far the longest.
  /// The code stage's own fraction is already weighted by module size and by the rewriter's passes.
  static const List<MapEntry<String, double>> preparationSteps = [
    MapEntry('unpack', 0.04),
    MapEntry('code', 0.80),
    MapEntry('caps', 0.02),
    MapEntry('direct', 0.02),
    MapEntry('module', 0.06),
    MapEntry('pack', 0.06),
  ];

  /// The whole preparation in [0, 1] when [step] is at [fraction]; 1 when done; null for an unknown step.
  static double? preparationOverall(String step, double fraction) {
    if (step == 'done') return 1;
    var before = 0.0;
    for (final entry in preparationSteps) {
      if (entry.key == step) return (before + entry.value * fraction.clamp(0.0, 1.0)).clamp(0.0, 1.0);
      before += entry.value;
    }
    return null;
  }

  // ---------------- error mapping ----------------

  /// The native error/code -> localized-message key. Public so the UI and the tests map the same way.
  static String messageKey(String? code) {
    switch (code) {
      case 'engineRestartRequired':
        return 'restartRequired';
      case 'switch1EngineLoaded':
        return 'switch1EngineLoaded';
      case 'notExportFolder':
        return 'notExportFolder';
      case 'notDownloaded':
        return 'notDownloaded';
      case 'exportInvalid':
      case 'gameIdMismatch':
        return 'exportInvalid';
      case 'gameUnsupported':
        return 'gameUnsupported';
      case 'nupInvalid':
        return 'nupInvalid';
      case 'rewriterFailed':
      case 'prepareFailed':
        return 'rewriterFailed';
      case 'storageError':
      case 'copyFailed':
      case 'nupIo':
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
    if (!flag(report['enginePresent'])) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.engineMissing);
    if (!flag(report['systemDataPresent'])) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.systemDataMissing);
    if (!flag(report['helperPresent'])) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.jitHelperMissing);
    final major = (report['iosMajor'] as num?)?.toInt() ?? 0;
    if (!flag(report['universalHandshake']) && major < 26) {
      return const S2ArmRuntimeAvailability(S2ArmRuntimeState.requiresIOS26);
    }
    if (flag(report['available'])) return const S2ArmRuntimeAvailability(S2ArmRuntimeState.ready);
    return const S2ArmRuntimeAvailability(S2ArmRuntimeState.unknown);
  }

  /// A native yes / no value: true, or a non-zero number. IPA 727: a comparison boxed in the bridge's Objective-C (not
  /// C++) file is a C int, Flutter's codec sent it as 1, and `!= true` read systemDataPresent as missing, so the Consoles
  /// switch stayed off. The bridge now boxes BOOLs; this keeps a stray int from turning the engine off again.
  @visibleForTesting
  static bool flag(Object? value) => value == true || (value is num && value != 0);

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
      if (report == null) return {'success': false, 'code': 'exportInvalid'};
      final info = Map<String, dynamic>.from(report);
      if (info['success'] == true) {
        final title = Switch2ExportContent.resolvedTitle(
          Switch2ExportContent.entryPath(exportFolder),
          programId: info['titleId']?.toString(),
          fallback: info['title']?.toString(),
          locale: locale,
        );
        if (title != null) info['title'] = title;
      }
      return info;
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
    onProgress?.call(S2ArmImportProgress(
      name: path.basename(picked), index: 1, count: 1, done: 0, total: 0, step: 'scan',
    ));
    await ensureLayout();
    final games = await gamesDirectory();
    final staging = await stagingDirectory();
    await _removeStaging(staging);

    final detected = await detectExport(picked);
    // Native detection also accepts a parent for direct launch. An import of that parent must scan
    // all its children, including deeper siblings, instead of silently importing the first match.
    final detectedRoot = detected['exportDir']?.toString() ?? picked;
    final exports = detected['success'] == true && path.equals(detectedRoot, picked)
        ? <Map<String, dynamic>>[{...detected, 'exportDir': detectedRoot}]
        : await _exportsBelow(picked, control: control);
    if (control?.cancelled ?? false) return const S2ArmImportResult([], cancelled: true);
    if (exports.isEmpty) {
      // A folder that holds NUP containers instead of an export: they are imported as the NUP item does.
      final nups = await _nupFilesIn(picked);
      if (control?.cancelled ?? false) return const S2ArmImportResult([], cancelled: true);
      if (nups.isNotEmpty) return importNupAt(nups, onProgress: onProgress, control: control);
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

  // ---------------- NUP containers ----------------

  /// Picks Switch 2 NUP containers (.nup: base, update and DLC in one file) in Files and imports each one. The files are
  /// opened where they are, never copied into the app first (a NUP holds a whole game); each one is checked, expanded into
  /// staging as an export folder (base/, updates/<newest>/, dlc/<title id>/) by the native port of S2Arm's ns2_nup.py, then
  /// renamed into Games like any export. Null when the picker was dismissed. docs/s2arm-switch2-library.md § NUP containers.
  static Future<S2ArmImportResult?> importNupFiles({
    void Function(S2ArmImportProgress progress)? onProgress,
    S2ArmImportControl? control,
  }) => StorageImportActivity.run(() async {
    _installHandler();
    await ensureLayout();
    final List<String> picked;
    try {
      picked = await channel.invokeListMethod<String>('pickNupFiles') ?? const <String>[];
    } on MissingPluginException {
      return const S2ArmImportResult(<S2ArmImportItem>[S2ArmImportItem('', 'unavailable')]);
    } on PlatformException catch (error) {
      return S2ArmImportResult(<S2ArmImportItem>[S2ArmImportItem('', 'storageError', detail: error.message ?? error.code)]);
    }
    if (picked.isEmpty) return null;
    try {
      return await importNupAt(picked, onProgress: onProgress, control: control);
    } finally {
      try {
        await channel.invokeMethod<Object?>('releaseNupFiles');
      } on MissingPluginException {
        // Nothing to release.
      } on PlatformException {
        // Same.
      }
    }
  });

  /// Imports the NUP containers [files] (readable local paths). Visible for tests.
  static Future<S2ArmImportResult> importNupAt(
    List<String> files, {
    void Function(S2ArmImportProgress progress)? onProgress,
    S2ArmImportControl? control,
  }) async {
    _installHandler();
    await ensureLayout();
    final games = await gamesDirectory();
    final staging = await stagingDirectory();
    await _removeStaging(staging);
    final items = <S2ArmImportItem>[];
    try {
      for (var index = 0; index < files.length; index++) {
        if (control?.cancelled ?? false) return S2ArmImportResult(items, cancelled: true);
        final item = await _importNup(files[index], games, staging,
            index: index + 1, count: files.length, onProgress: onProgress, control: control);
        if (item == null) return S2ArmImportResult(items, cancelled: true);
        items.add(item);
      }
    } finally {
      await _removeStaging(staging);
    }
    return S2ArmImportResult(items);
  }

  /// The *.nup files directly inside [folder], sorted; none when it cannot be read.
  static Future<List<String>> _nupFilesIn(String folder) async {
    final files = <String>[];
    try {
      await for (final entry in Directory(folder).list(followLinks: false)) {
        final name = path.basename(entry.path);
        if (entry is File && path.extension(name).toLowerCase() == '.nup' && !name.startsWith('.')) files.add(entry.path);
      }
      return files..sort();
    } on FileSystemException {
      return const <String>[];
    }
  }

  static Future<Map<String, dynamic>> _nupCall(String method, Map<String, Object?> arguments) async {
    try {
      final report = await channel.invokeMapMethod<String, dynamic>(method, arguments);
      return report == null ? {'success': false, 'code': 'nupIo'} : Map<String, dynamic>.from(report);
    } on MissingPluginException {
      return {'success': false, 'code': 'unavailable'};
    } on PlatformException catch (error) {
      return {'success': false, 'code': 'nupIo', 'diagnostic': error.message ?? error.code};
    }
  }

  static S2ArmImportItem _nupRefusal(String name, Map<String, dynamic> report) {
    final detail = report['diagnostic']?.toString();
    return S2ArmImportItem(name, (report['code'] ?? 'nupIo').toString(), detail: detail == null || detail.isEmpty ? null : detail);
  }

  /// Expands one NUP container into Games/<title> through staging. Null when the player cancelled.
  static Future<S2ArmImportItem?> _importNup(
    String file,
    Directory games,
    Directory staging, {
    required int index,
    required int count,
    void Function(S2ArmImportProgress progress)? onProgress,
    S2ArmImportControl? control,
  }) async {
    var name = path.basenameWithoutExtension(file);
    final inspected = await _nupCall('inspectNup', {'path': file});
    if (inspected['success'] != true) {
      // A file iCloud has not downloaded yet is only a placeholder beside it (".<name>.icloud").
      final placeholder = File(path.join(path.dirname(file), '.${path.basename(file)}.icloud'));
      if (inspected['code'] == 'nupIo' && await placeholder.exists()) return S2ArmImportItem(name, 'notDownloaded');
      return _nupRefusal(name, inspected);
    }
    final bytes = (inspected['bytes'] as num?)?.toInt() ?? 0;
    final free = await availableBytes(games.path);
    if (free != null && free < bytes + spaceMargin) {
      LoggerService.instance.i('S2Arm import: $name refused, ${bytes ~/ (1024 * 1024)} MB to unpack, ${free ~/ (1024 * 1024)} MB available');
      return S2ArmImportItem(name, 'notEnoughSpace');
    }
    await staging.create(recursive: true);
    final stage = Directory(path.join(staging.path, '$index'));
    await _removeStaging(stage);
    onProgress?.call(S2ArmImportProgress(name: name, index: index, count: count, done: 0, total: bytes, step: 'nup'));
    _activeNupProgress = (done, total) => onProgress?.call(
        S2ArmImportProgress(name: name, index: index, count: count, done: done, total: total, step: 'nup'));
    control?._onCancel = () => unawaited(channel.invokeMethod<Object?>('cancelNup').then<void>((_) {}, onError: (Object _) {}));
    try {
      if (control?.cancelled ?? false) return null;
      final watch = Stopwatch()..start();
      final expanded = await _nupCall('expandNup', {'path': file, 'output': stage.path});
      if (expanded['code'] == 'cancelled' || (control?.cancelled ?? false)) return null;
      if (expanded['success'] != true) return _nupRefusal(name, expanded);
      final detected = await detectExport(stage.path);
      if (detected['success'] != true) return _nupRefusal(name, detected);
      final info = await gameInfo(stage.path);
      name = _safeName((info['title'] ?? name).toString(), detected['gid']?.toString());
      final target = await _freeDirectory(games, name);
      await stage.rename(target.path);
      LoggerService.instance.i('S2Arm import: $name unpacked from ${path.basename(file)} '
          '(${bytes ~/ (1024 * 1024)} MB, update ${inspected['updateVersion']}, ${inspected['dlcCount']} DLC, '
          '${watch.elapsed.inSeconds} s)');
      return S2ArmImportItem(name, 'imported', destination: target.path);
    } on FileSystemException catch (error) {
      return S2ArmImportItem(name, error.osError?.errorCode == 28 ? 'notEnoughSpace' : 'copyFailed');
    } finally {
      _activeNupProgress = null;
      control?._onCancel = null;
      await _removeStaging(stage);
    }
  }

  /// The Switch 2 exports inside [picked] when it is not one itself: a folder that holds the game folder (for example
  /// "<game> + Emulator/<game>/base/exefs/main.npdm") or several games. Looks up to three levels down, never inside an
  /// export's own base, ExeFS, RomFS, updates or DLC, and validates each base NPDM with native detection.
  static Future<List<Map<String, dynamic>>> _exportsBelow(String picked, {S2ArmImportControl? control}) async {
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
          if (control?.cancelled ?? false) return found;
          final name = path.basename(child.path);
          if (child is! Directory || name.startsWith('.') ||
              const {'base', 'exefs', 'romfs', 'updates', 'dlc'}.contains(name.toLowerCase())) continue;
          if (await File(path.join(child.path, 'base', 'exefs', 'main.npdm')).exists() ||
              await File(path.join(child.path, 'exefs', 'main.npdm')).exists()) {
            final detected = await detectExport(child.path);
            final root = detected['exportDir']?.toString() ?? child.path;
            if (detected['success'] == true && path.equals(root, child.path)) {
              found.add({...detected, 'exportDir': root});
              if (found.length >= 200) return found;
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
    final stage = Directory(path.join(staging.path, '$index'));
    var title = path.basename(exportDir);

    void report(int done, int total, {String? step, int? entries}) {
      onProgress?.call(S2ArmImportProgress(
        name: title, index: index, count: count, done: done, total: total,
        step: step, unitsDone: entries,
      ));
    }

    try {
      if (control?.cancelled ?? false) return null;
      report(0, 0, step: 'scan');
      final info = await gameInfo(exportDir);
      title = _safeName((info['title'] ?? title).toString(), detected['gid']?.toString());
      final source = Directory(exportDir);

      await staging.create(recursive: true);
      await _removeStaging(stage);
      if (control?.cancelled ?? false) return null;
      report(0, 0, step: 'clone');
      // APFS clones the tree in one system call. A successful clone needs no size walk.
      if (await cloneTree(source.path, stage.path)) {
        final target = await _freeDirectory(games, title);
        if (control?.cancelled ?? false) return null;
        await stage.rename(target.path);
        report(1, 1);
        LoggerService.instance.i('S2Arm import: $title cloned');
        return S2ArmImportItem(title, 'imported', destination: target.path);
      }

      await _removeStaging(stage);
      report(0, 0, step: 'scan');
      final watch = Stopwatch()..start();
      final total = await _directorySize(source, control: control, onEntry: (count) {
        if (watch.elapsedMilliseconds < 100) return;
        report(0, 0, step: 'scan', entries: count);
        watch.reset();
      });
      final free = await availableBytes(games.path);
      if (control?.cancelled ?? false) return null;
      if (free != null && free < total + spaceMargin) {
        LoggerService.instance.i('S2Arm import: $title refused, ${total ~/ (1024 * 1024)} MB to copy, ${free ~/ (1024 * 1024)} MB available');
        return S2ArmImportItem(title, 'notEnoughSpace');
      }

      var done = 0;
      report(0, total);
      watch.reset();
      void copied(int bytes) {
        if (watch.elapsedMilliseconds < 100) return;
        // Reserve 100% for a game already visible in the library.
        report(total > 0 && bytes >= total ? total - 1 : bytes, total);
        watch.reset();
      }

      await _copyDirectory(source, stage, control: control, progress: (bytes) {
        copied(done + bytes);
      }, onFileDone: (bytes) {
        done += bytes;
        copied(done);
      });
      final target = await _freeDirectory(games, title);
      if (control?.cancelled ?? false) return null;
      await stage.rename(target.path);
      report(done > 0 ? done : 1, done > 0 ? done : 1);
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

  static Future<int> _directorySize(
    Directory directory, {
    S2ArmImportControl? control,
    required void Function(int count) onEntry,
  }) async {
    var total = 0;
    var count = 0;
    await for (final entry in directory.list(recursive: true, followLinks: false)) {
      if (control?.cancelled ?? false) throw _Cancelled();
      if (entry is File) {
        try {
          total += await entry.length();
        } on FileSystemException {
          // Skipped from the estimate; the copy surfaces a real error.
        }
        onEntry(++count);
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
  static final Stopwatch _prepareClock = Stopwatch();
  static String? _lastLoggedStep;

  /// One app.log line per preparation step and code-stage module, with the time since the start. IPA 728 sat on
  /// "code · 0%" for minutes and app.log said nothing of the preparation.
  static void _logPrepareStep(String step, String detail) {
    final label = detail.isEmpty ? step : '$step $detail';
    if (label == _lastLoggedStep) return;
    _lastLoggedStep = label;
    LoggerService.instance.i('S2Arm prepare: $label at ${_prepareClock.elapsed.inSeconds} s');
  }

  static bool _journalConfigured = false;

  /// The native launch journal (one JSON line per preparation and launch step), in Documents/Diagnostics/S2Arm where
  /// the Files app reaches it. It was never opened before, so a failed preparation left no trace. Once per process.
  static Future<void> _configureJournal() async {
    if (_journalConfigured || defaultTargetPlatform != TargetPlatform.iOS) return;
    _journalConfigured = true;
    try {
      final folder = Directory(path.join((await documentsDirectory()).path, 'Diagnostics', 'S2Arm'));
      await folder.create(recursive: true);
      await channel.invokeMethod<Object?>('configureLaunchJournal', {'path': path.join(folder.path, 's2arm-journal.jsonl')});
    } on MissingPluginException {
      // Not iOS.
    } on PlatformException {
      // The journal is a diagnostic only.
    } on FileSystemException {
      // Same.
    }
  }

  /// Prepares an imported game for the engine. Returns the native map (gid, imagesPath, moduleDir, gameData, docs, sizes,
  /// durationsMs, reused) or {success:false, code}. A finished preparation of the same inputs is reused by the native
  /// side (prepared.json), so only the first launch of a game prepares it.
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
    await _configureJournal();
    _lastLoggedStep = null;
    _prepareClock
      ..reset()
      ..start();
    Map<String, dynamic> outcome;
    try {
      final report = await channel.invokeMapMethod<String, dynamic>('prepareGame', {
        'exportFolder': exportFolder,
        if (directChain != null) 'directChain': directChain,
        if (systemDataFolder != null) 'systemDataFolder': systemDataFolder,
      });
      outcome = report == null ? {'success': false, 'code': 'prepareFailed'} : Map<String, dynamic>.from(report);
    } on MissingPluginException {
      outcome = {'success': false, 'code': 'unavailable'};
    } on PlatformException catch (error) {
      outcome = {'success': false, 'code': error.code, 'diagnostic': error.message};
    } finally {
      _activePrepareProgress = null;
      _preparing = false;
      _prepareClock.stop();
    }
    final seconds = _prepareClock.elapsed.inSeconds;
    if (outcome['success'] == true) {
      LoggerService.instance.i('S2Arm prepare: ${outcome['reused'] == true ? 'reused' : 'passed'} in $seconds s, '
          'steps ${outcome['durationsMs'] ?? {}} ms, sizes ${outcome['sizes'] ?? {}}');
    } else {
      LoggerService.instance.w('S2Arm prepare: failed after $seconds s at ${outcome['stage'] ?? '?'}: ${outcome['code']} '
          '${outcome['diagnostic'] ?? ''}');
    }
    return outcome;
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
  static bool _importingSave = false;

  /// True from a successful launch until the native `sessionEnded` event.
  static bool _sessionRunning = false;
  static bool get sessionRunning => _sessionRunning;
  static int _sessionEndSerial = 0;

  /// A game is being prepared, launched or running: its files must not be deleted.
  static bool get busy => _preparing || _launching || _sessionRunning || _importingSave;

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
    if (_launching || _importingSave) return const S2ArmLaunchOutcome.failure('busy');
    _launching = true;
    // The in-game menu speaks RewindBox's language (the app's locale when the caller has it, else the system one).
    final uiLocale = Switch2SettingsLocale.codeFor(locale ?? PlatformDispatcher.instance.locale);
    try {
      // The Switch 1 engine's core (MeloNX) and the S2Arm engine cannot share a process (two NativeAOT runtimes), and the
      // native launch refuses once it is loaded. The Consoles tab loaded it to read its state (IPA 728), so say it now,
      // before a long preparation, rather than after it. Its own code and message, never the Switch 2 restart one; the
      // code shows in the failure dialog's technical details, so it names the console, not the engine.
      final now = await status();
      if (flag(now['melonxCoreLoaded'])) {
        LoggerService.instance.w('S2Arm launch: refused before preparing, the Switch 1 engine (MeloNX) is loaded in this process');
        return const S2ArmLaunchOutcome.failure('switch1EngineLoaded');
      }
      // One Switch 2 game per process, except the game the player quit: the engine parked it and it resumes (patch 0010).
      final parked = (now['parkedGameId'] ?? '').toString().toUpperCase();
      if (flag(now['engineLoaded']) && parked.isEmpty) return const S2ArmLaunchOutcome.failure('engineRestartRequired');
      final detected = await detectExport(exportFolder);
      if (detected['success'] != true) return S2ArmLaunchOutcome.failure((detected['code'] ?? 'notExportFolder').toString());
      if (flag(now['engineLoaded']) && (detected['gid'] ?? '').toString().toUpperCase() != parked) {
        return const S2ArmLaunchOutcome.failure('engineRestartRequired');
      }
      final prepared = await prepare(exportFolder: (detected['exportDir'] ?? exportFolder).toString(), onProgress: onPrepareProgress);
      if (prepared['success'] != true) {
        return S2ArmLaunchOutcome.failure((prepared['code'] ?? 'prepareFailed').toString(), prepared['diagnostic']?.toString());
      }
      final saveFolder = await saveFolderFor((detected['exportDir'] ?? exportFolder).toString());
      final endSerial = _sessionEndSerial;
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
        _sessionRunning = _sessionEndSerial == endSerial;
        LoggerService.instance.i('S2Arm launch: engine started');
        return const S2ArmLaunchOutcome.success();
      }
      LoggerService.instance.w('S2Arm launch: ${report?['error'] ?? 'launchFailed'} at ${report?['stage'] ?? '?'}: '
          '${report?['diagnostic'] ?? ''}');
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
    final existing = await _existingSaveFolder(saves, gid);
    if (existing != null) return existing;
    final tag = '[${gid.toUpperCase()}]';
    final folder = Directory(path.join(saves.path, '${_safeName(await title(), 'Switch 2')} $tag'));
    await folder.create(recursive: true);
    return folder;
  }

  static Future<Directory?> _existingSaveFolder(Directory saves, String gid) async {
    if (!await saves.exists()) return null;
    final tag = '[${gid.toUpperCase()}]';
    final matches = <({Directory folder, DateTime modified})>[];
    await for (final entry in saves.list(followLinks: false)) {
      if (entry is Directory && path.basename(entry.path).toUpperCase().endsWith(tag)) {
        matches.add((folder: entry, modified: (await entry.stat()).modified));
      }
    }
    if (matches.isEmpty) return null;
    matches.sort((a, b) {
      final byDate = b.modified.compareTo(a.modified);
      return byDate != 0 ? byDate : a.folder.path.compareTo(b.folder.path);
    });
    return matches.first.folder;
  }

  static final RegExp _hex16 = RegExp(r'^[0-9A-Fa-f]{16}$');
  static final RegExp _hex32 = RegExp(r'^[0-9A-Fa-f]{32}$');
  static final RegExp _checkpointName = RegExp(r'^0x([0-9A-Fa-f]{16})(?: .*)?$');
  static final RegExp _switch2SaveTitle = RegExp(r'^04[0-9A-Fa-f]{14}$');
  static final RegExp _titleSaveSlot = RegExp(r'^(?:Play|[0-9]{3})$', caseSensitive: false);

  // IPA 787 staged 26 files from a parent folder containing multiple titles for Mario Kart World.
  // An export in this format names its title even when Files returns only Play or 000.
  static String? _titleOfSaveSlot(String slot) {
    if (!_titleSaveSlot.hasMatch(path.basename(slot))) return null;
    final titleFolder = path.dirname(slot);
    final title = path.basename(titleFolder);
    if (!_switch2SaveTitle.hasMatch(title)) return null;
    final parent = path.dirname(titleFolder);
    // A yuzu title folder is already the payload root, even if it contains a slot named 000.
    if (_hex32.hasMatch(path.basename(parent)) &&
        path.basename(path.dirname(parent)) == '0000000000000000') return null;
    return title.toLowerCase();
  }

  static Future<List<_TitleSaveSlot>> _titleSaveSlots(Directory root) async {
    final title = _titleOfSaveSlot(path.normalize(root.path));
    if (title != null) return [(program: title, folder: root)];

    final titleFolders = <Directory>[];
    if (_switch2SaveTitle.hasMatch(path.basename(path.normalize(root.path)))) {
      titleFolders.add(root);
    } else {
      await for (final entry in root.list(followLinks: false)) {
        if (entry is Directory && _switch2SaveTitle.hasMatch(path.basename(entry.path))) {
          titleFolders.add(entry);
        }
      }
    }
    final slots = <_TitleSaveSlot>[];
    for (final folder in titleFolders) {
      await for (final entry in folder.list(followLinks: false)) {
        if (entry is! Directory) continue;
        final program = _titleOfSaveSlot(entry.path);
        if (program != null) slots.add((program: program, folder: entry));
      }
    }
    return slots;
  }

  // Preserve title and profile metadata outside the deepest folder picked in Files.
  static Future<({String program, String kind, String? user})?> _directSaveSource(String picked) async {
    final root = path.normalize(picked);
    final name = path.basename(root);
    final parent = path.dirname(root);
    final user = path.basename(parent).toLowerCase();
    if (_hex16.hasMatch(name) && _hex32.hasMatch(user) &&
        path.basename(path.dirname(parent)) == '0000000000000000') {
      final device = user == '00000000000000000000000000000000';
      return (program: name.toLowerCase(), kind: device ? 'device' : 'account', user: device ? null : user);
    }
    if (name != '0' || !_hex16.hasMatch(user)) return null;
    final meta = File(path.join(parent, 'ExtraData0'));
    if (!await meta.exists() || await meta.length() < 0x40) return null;
    final bytes = await meta.openRead(0, 0x40).fold<List<int>>(<int>[], (all, chunk) => all..addAll(chunk));
    final data = ByteData.sublistView(Uint8List.fromList(bytes));
    final program = data.getUint64(0, Endian.little);
    if (program == 0 || data.getUint64(0x18, Endian.little) != 0 || (bytes[0x20] != 1 && bytes[0x20] != 3)) return null;
    String word(int offset) => data.getUint32(offset, Endian.little).toRadixString(16).padLeft(8, '0');
    final profile = word(12) + word(8) + word(20) + word(16);
    final device = bytes[0x20] == 3;
    return (
      program: program.toRadixString(16).padLeft(16, '0'),
      kind: device ? 'device' : 'account',
      user: device ? null : profile,
    );
  }

  /// The game a picked save names, as 16 lower-case hex digits, read the way the engine recognizes saves (S2Arm services
  /// SaveFolder.cs Detect): a Ryujinx export (<16 hex>/0 beside ExtraData0, whose first 8 bytes are the program id), a
  /// yuzu tree (0000000000000000/<32 hex user>/<16 hex program>), a Checkpoint folder ("0x<16 hex> <name>"), or
  /// a Switch 2 save under its title folder (Play / a numbered slot). Null when
  /// the format names no game (JKSV, plain files, save / save_device) or names several. Visible for tests.
  static Future<String?> saveProgramId(String picked) async {
    final direct = await _directSaveSource(picked);
    if (direct != null) return direct.program;
    final root = Directory(picked);
    final slots = await _titleSaveSlots(root);
    if (slots.isNotEmpty) {
      final titles = slots.map((slot) => slot.program).toSet();
      return titles.length == 1 ? titles.single : null;
    }
    return _embeddedSaveProgramId(root);
  }

  static Future<String?> _embeddedSaveProgramId(Directory root) async {
    final ids = <String>{};
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

  /// A save may name a program ID. Launches use the matching game's library ID.
  static Future<S2ArmSaveGame?> _librarySaveGameFor(String gid) async {
    S2ArmSaveGame? program;
    for (final game in await libraryGames()) {
      if (game.gid == gid) return game;
      if (game.programId == gid) program ??= game;
    }
    return program;
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

  /// Copies [picked] into the game's save folder. Play exports replace their matching files inside save/Play.
  /// Other exports retain their layout for the engine's own recognition. What the save folder held before is kept beside
  /// it as "<name> (backup)" (one backup, replaced by the next import). With [exportFolder] null, the save must name its
  /// game (saveNoGame otherwise). Visible for tests.
  static Future<S2ArmSaveImportResult> importSaveAt(String? exportFolder, String picked) async {
    if (_sessionRunning || _launching) throw const S2ArmSaveException('saveGameRunning');
    if (_importingSave) throw const S2ArmSaveException('saveFailed');
    _importingSave = true;
    try {
      return await _importSaveAt(exportFolder, picked);
    } on FileSystemException {
      throw const S2ArmSaveException('saveFailed');
    } finally {
      _importingSave = false;
    }
  }

  static Future<S2ArmSaveImportResult> _importSaveAt(String? exportFolder, String picked) async {
    var own = const <String?>{};
    if (exportFolder != null) {
      final selected = await detectExport(exportFolder);
      final selectedGid = selected['gid']?.toString();
      if (selected['success'] != true || selectedGid == null || !_gidPattern.hasMatch(selectedGid)) {
        throw const S2ArmSaveException('saveNotExport');
      }
      own = {selectedGid.toLowerCase(), selected['programId']?.toString().toLowerCase()};
    }
    final pickedFolder = Directory(picked);
    if (!await pickedFolder.exists()) throw const S2ArmSaveException('saveEmpty');
    // A save that names another game goes to that game's folder: the player picked the wrong game in the list, or none.
    final direct = await _directSaveSource(picked);
    _TitleSaveSlot? slot;
    if (direct == null) {
      final slots = await _titleSaveSlots(pickedFolder);
      if (slots.isNotEmpty) {
        final matching = slots.where((slot) => own.contains(slot.program)).toList();
        final candidates = matching.isEmpty ? slots : matching;
        if (candidates.length != 1) throw const S2ArmSaveException('saveSelectTitleSlot');
        slot = candidates.single;
      }
    }
    final source = slot?.folder ?? pickedFolder;
    final saveId = direct?.program ?? slot?.program ?? await _embeddedSaveProgramId(pickedFolder);
    String? redirectedTo;
    String? redirectedTitle;
    final Directory target;
    if (saveId != null && !own.contains(saveId)) {
      final game = await _librarySaveGameFor(saveId);
      final targetId = game?.gid ?? saveId;
      redirectedTo = targetId.toUpperCase();
      redirectedTitle = game?.title;
      target = await _saveFolderForId(targetId, () async => redirectedTitle ?? '');
    } else if (exportFolder == null) {
      throw const S2ArmSaveException('saveNoGame');
    } else {
      final folder = await saveFolderFor(exportFolder);
      if (folder == null) throw const S2ArmSaveException('saveNotExport');
      target = folder;
    }
    final normalizedSource = await source.resolveSymbolicLinks();
    final normalizedPicked = slot == null ? normalizedSource : await pickedFolder.resolveSymbolicLinks();
    final normalizedTarget = await target.resolveSymbolicLinks();
    final saves = await (await savesDirectory()).resolveSymbolicLinks();
    if (normalizedPicked == saves ||
        normalizedSource == normalizedTarget || path.isWithin(normalizedTarget, normalizedSource) ||
        path.isWithin(normalizedSource, normalizedTarget)) {
      throw const S2ArmSaveException('saveSameFolder');
    }
    final name = path.basename(path.normalize(source.path));
    // Stage the whole import before moving either save or backup. The marker tells the
    // guest to commit this import even when file sizes and modification times match.
    final staging = await target.parent.createTemp('.save-import-');
    final contents = Directory(path.join(staging.path, 'contents'));
    final backup = Directory('${target.path} (backup)');
    final previousBackup = Directory(path.join(staging.path, 'previous-backup'));
    var clean = true;
    try {
      final String payload;
      final play = direct == null && name.toLowerCase() == 'play';
      if (play) {
        payload = await _stagePlaySave(target, contents, name);
      } else {
        payload = slot == null
            ? path.join(contents.path, direct?.kind ?? (name.isEmpty ? 'save' : name))
            : path.join(contents.path, slot.program, path.basename(slot.folder.path));
      }
      final files = await _copyTree(source, Directory(payload), rejectLinks: play);
      if (direct?.user case final String user) {
        await File(path.join(contents.path, 'user')).writeAsString(user, flush: true);
      }
      if (files == 0) throw const S2ArmSaveException('saveEmpty');
      await File(path.join(contents.path, '.rewindbox-import-pending')).writeAsString('1\n', flush: true);
      var backedUp = false;
      var keptBackup = false;
      try {
        if (await target.list(followLinks: false).isEmpty) {
          await target.delete();
        } else {
          if (await backup.exists()) {
            await backup.rename(previousBackup.path);
            keptBackup = true;
          }
          await target.rename(backup.path);
          backedUp = true;
        }
        await contents.rename(target.path);
      } on FileSystemException {
        try {
          if (backedUp) await backup.rename(target.path);
          if (keptBackup) await previousBackup.rename(backup.path);
        } on FileSystemException {
          clean = false;
          rethrow;
        }
        rethrow;
      }
      return S2ArmSaveImportResult(
        folder: target.path,
        files: files,
        backup: await backup.exists() ? backup.path : null,
        redirectedTo: redirectedTo,
        redirectedTitle: redirectedTitle,
      );
    } finally {
      if (clean) await _removeStaging(staging);
    }
  }

  // On IPA 788 Mario Kart World recovered its progress when account.sav was moved into save/Play.
  // Stage the native layout so the guest mounts save as the root and keeps the Play directory.
  static Future<String> _stagePlaySave(Directory target, Directory contents, String name) async {
    var playName = name;
    final account = Directory(path.join(target.path, 'save'));
    if (await account.exists()) {
      final matches = await account
          .list(followLinks: false)
          .where((entry) => path.basename(entry.path).toLowerCase() == 'play')
          .toList();
      if (matches.isNotEmpty) {
        if (matches.length != 1 || matches.single is! Directory) {
          throw const S2ArmSaveException('saveFailed');
        }
        playName = path.basename(matches.single.path);
      }
      await _copyTree(account, Directory(path.join(contents.path, 'save')), rejectLinks: true);
    }
    final device = Directory(path.join(target.path, 'save_device'));
    if (await device.exists()) {
      await _copyTree(device, Directory(path.join(contents.path, 'save_device')), rejectLinks: true);
    }
    final user = File(path.join(target.path, 'user'));
    if (await user.exists()) {
      await contents.create(recursive: true);
      await user.copy(path.join(contents.path, 'user'));
    }
    return path.join(contents.path, 'save', playName);
  }

  // The Files copy is pending until this marker is written by the guest after Commit.
  static Future<String?> saveImportStatus(String exportFolder) async {
    try {
      final detected = await detectExport(exportFolder);
      final gid = detected['gid']?.toString();
      if (detected['success'] != true || gid == null || !_gidPattern.hasMatch(gid)) return null;
      final folder = await _existingSaveFolder(await savesDirectory(), gid);
      if (folder == null) return null;
      final pending = File(path.join(folder.path, '.rewindbox-import-pending'));
      final result = File(path.join(folder.path, '.rewindbox-import-result'));
      final isPending = await pending.exists();
      if (!await result.exists() || await result.length() > 64) {
        return isPending ? 'saveRestorePending' : null;
      }
      return switch ((await result.readAsString()).trim()) {
        'applied' => isPending ? 'saveRestorePending' : 'saveRestoreApplied',
        'unrecognized' => 'saveRestoreUnrecognized',
        'ambiguousProfile' || 'profileUnavailable' => 'saveRestoreProfile',
        'mountFailed' || 'writeFailed' => 'saveRestoreWriteFailed',
        _ => isPending ? 'saveRestorePending' : null,
      };
    } on FileSystemException {
      return 'saveRestoreWriteFailed';
    }
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

  static Future<int> _copyTree(Directory from, Directory to, {bool rejectLinks = false}) async {
    var files = 0;
    await to.create(recursive: true);
    await for (final entry in from.list(followLinks: false)) {
      final destination = path.join(to.path, path.basename(entry.path));
      if (entry is Directory) {
        files += await _copyTree(entry, Directory(destination), rejectLinks: rejectLinks);
      } else if (entry is File) {
        await entry.copy(destination);
        files++;
      } else if (rejectLinks) {
        throw const S2ArmSaveException('saveFailed');
      }
    }
    return files;
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
