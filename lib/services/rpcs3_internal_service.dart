import 'dart:async';
import 'dart:io';

import '../data/datasources/sqlite_service.dart';
import '../l10n/rpcs3_saves_locale.dart';
import '../l10n/rpcs3_ui_locale.dart';
import 'rpcs3_game_deletion.dart';
import 'rpcs3_save_exchange_service.dart';
import 'game_launch_manager.dart';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart' show visibleForTesting;
import 'package:flutter_localization/flutter_localization.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

import 'logger_service.dart';
import 'local_dev_vpn_route_service.dart';
import 'pairing_file_service.dart';
import 'rpcs3_game_profile_service.dart';
import 'rpcs3_library_service.dart';
import 'storage/storage_import_activity.dart';
import 'storage/storage_picker_copies.dart';

enum Rpcs3RuntimePhase {
  idle,
  checkingJit,
  enablingJit,
  jitReady,
  initializingCore,
  ready,
  installingFirmware,
  importingContent,
  launching,
  error,
}

class Rpcs3RuntimeState {
  const Rpcs3RuntimeState({
    required this.phase,
    required this.message,
    required this.jitReady,
    required this.coreReady,
    this.error,
  });

  const Rpcs3RuntimeState.idle()
    : phase = Rpcs3RuntimePhase.idle,
      message = '',
      jitReady = false,
      coreReady = false,
      error = null;

  final Rpcs3RuntimePhase phase;
  final String message;
  final bool jitReady;
  final bool coreReady;
  final String? error;

  bool get busy => switch (phase) {
    Rpcs3RuntimePhase.checkingJit ||
    Rpcs3RuntimePhase.enablingJit ||
    Rpcs3RuntimePhase.initializingCore ||
    Rpcs3RuntimePhase.installingFirmware ||
    Rpcs3RuntimePhase.importingContent ||
    Rpcs3RuntimePhase.launching => true,
    _ => false,
  };
}

class Rpcs3ImportResult {
  const Rpcs3ImportResult({
    required this.imported,
    required this.rejected,
    this.errors = const [],
  });

  final int imported;
  final int rejected;
  final List<String> errors;
}

class Rpcs3InternalException implements Exception {
  const Rpcs3InternalException(this.code, this.message);

  final String code;
  final String message;

  @override
  String toString() => 'Rpcs3InternalException($code, $message)';
}

/// Owns the in-process PlayStation 3 engine embedded in NeoStation iOS.
///
/// The ABI-compatible RPCS3 iOS Core with v0.9-era JIT backports requires JIT before libRPCS3Core.dylib is dlopened. The
/// Universal JIT is a two-phase transaction: attach, load/initialize the Core
/// while the debugger prepares its arena, then confirm the helper detached.
class Rpcs3InternalService {
  Rpcs3InternalService._();

  static String get _localeTag =>
      FlutterLocalization.instance.currentLocale?.toLanguageTag() ?? 'en';
  static String _ui(String key) =>
      Rpcs3UiLocale.textForLocale(_localeTag, key);

  static final _log = LoggerService.instance;
  static final _stateController = StreamController<Rpcs3RuntimeState>.broadcast(
    sync: true,
  );

  static const _statusTimeout = Duration(seconds: 5);
  static const _jitTimeout = Duration(minutes: 11);
  static const _coreTimeout = Duration(minutes: 3);
  static const _jitCompletionTimeout = Duration(seconds: 130);
  static const _firmwareInstallTimeout = Duration(minutes: 10);
  static const _contentInstallTimeout = Duration(minutes: 30);

  static Future<void>? _runtimePreparation;
  static bool _initialized = false;
  static bool _libraryMutationInProgress = false;
  static bool _jitPrepared = false;
  static Rpcs3RuntimeState _state = const Rpcs3RuntimeState.idle();

  static bool get supported => Platform.isIOS;
  static bool get initialized => _initialized;
  static bool get jitPrepared => _jitPrepared;
  static Rpcs3RuntimeState get runtimeState => _state;
  static Stream<Rpcs3RuntimeState> get runtimeStates => _stateController.stream;

  static void _emit(
    Rpcs3RuntimePhase phase,
    String message, {
    bool? jitReady,
    bool? coreReady,
    String? error,
  }) {
    _state = Rpcs3RuntimeState(
      phase: phase,
      message: message,
      jitReady: jitReady ?? _state.jitReady,
      coreReady: coreReady ?? _initialized,
      error: error,
    );
    _stateController.add(_state);
  }

  static Future<T> _bounded<T>(
    Future<T> future,
    Duration timeout,
    String code,
    String message,
  ) async {
    try {
      return await future.timeout(timeout);
    } on TimeoutException {
      throw Rpcs3InternalException(code, message);
    }
  }

  static Future<Directory> rootDirectory() async {
    final support = await getApplicationSupportDirectory();
    final root = Directory(path.join(support.path, 'NeoStation', 'RPCS3'));
    await root.create(recursive: true);
    return root;
  }

  static Future<Directory> dataDirectory() async {
    final root = await rootDirectory();
    final directory = Directory(path.join(root.path, 'Data'));
    await directory.create(recursive: true);
    return directory;
  }

  static Future<Directory> cacheDirectory() async {
    final root = await rootDirectory();
    final directory = Directory(path.join(root.path, 'Cache'));
    await directory.create(recursive: true);
    return directory;
  }

  /// Documents root of the Files workspace; tests point it at a temporary
  /// folder so no path_provider channel is needed.
  @visibleForTesting
  static Future<Directory> Function()? filesWorkspaceDocumentsOverride;

  /// Text of `Documents/RPCS3/README.txt`, rewritten whenever it differs
  /// (the Build 441 text promised an automatic consumption that no longer
  /// exists).
  static const String filesWorkspaceReadme =
      'RewindBox - RPCS3 game saves (manual exchange)\n'
      '\n'
      'Import/Game Saves : drop PS3 save folders (each holding PARAM.SFO,\n'
      '                    alone or under a parent folder) or ZIP archives\n'
      '                    here, then open RewindBox > RPCS3 manager and\n'
      '                    tap "Import game saves". Nothing is read or\n'
      '                    removed from this folder automatically; the\n'
      '                    manager asks before replacing an existing save.\n'
      'Export/Game Saves : "Export game saves" in the RPCS3 manager writes\n'
      '                    one RPCS3-saves-<date>.zip here (savedata/<DIR>/...).\n'
      '                    Share it from the report, or copy it from Files.\n'
      'Import/Savestates, Export/Savestates : reserved; not used by these\n'
      '                    flows.\n'
      '\n'
      'RPCS3 reads the saves from RewindBox\'s private RPCS3 folder; an\n'
      'imported save appears in RPCS3 without any further step.\n';

  /// `Documents/RPCS3` with its Import/Export folders and README. Only
  /// creates what is missing; existing files are never read, moved or
  /// deleted.
  static Future<Directory> filesWorkspaceDirectory() async {
    final documents = await (filesWorkspaceDocumentsOverride?.call() ??
        getApplicationDocumentsDirectory());
    final root = Directory(path.join(documents.path, 'RPCS3'));
    await root.create(recursive: true);
    for (final relative in const <String>[
      'Import/Game Saves',
      'Import/Savestates',
      'Export/Game Saves',
      'Export/Savestates',
    ]) {
      await Directory(path.join(root.path, relative)).create(recursive: true);
    }
    final readme = File(path.join(root.path, 'README.txt'));
    String? current;
    try {
      if (await readme.exists()) current = await readme.readAsString();
    } catch (_) {
      current = null;
    }
    if (current != filesWorkspaceReadme) {
      await readme.writeAsString(filesWorkspaceReadme, flush: true);
    }
    return root;
  }

  /// Startup housekeeping of the Files workspace, called by the locked
  /// `lib/main.dart` and before an explicit Core startup: makes sure the
  /// folders and README exist, nothing more. Saves are exchanged only on
  /// the user's explicit action through [Rpcs3SaveExchangeService]; the
  /// returned counters stay zero and exist for the locked caller.
  static Future<({int imported, int exported})> synchronizeFilesWorkspace() async {
    if (!supported && filesWorkspaceDocumentsOverride == null) {
      return (imported: 0, exported: 0);
    }
    await filesWorkspaceDirectory();
    return (imported: 0, exported: 0);
  }

  static String _saves(String key) =>
      Rpcs3SavesLocale.textForLocale(_localeTag, key);

  /// Reads the Core's emulation state for [runSaveExchange]; tests replace
  /// it to simulate a running game.
  @visibleForTesting
  static Future<int> Function() saveExchangeEmulationState =
      Rpcs3InternalBridge.emulationState;

  /// Makes [runSaveExchange] treat the Core as loaded (true) or dormant
  /// (false) instead of the real state. Tests only.
  @visibleForTesting
  static bool? saveExchangeCoreInitializedOverride;

  /// Runs a game-save import or export under the same guard as
  /// [deleteInstalledGame]: refused while another library mutation, a
  /// runtime preparation or a content import runs, while a game session is
  /// active, and, once the Core is loaded, unless its emulation state is
  /// stopped (0) or ready (1), because RPCS3 may be writing a save. The
  /// library mutation flag is held for the whole [body].
  static Future<T> runSaveExchange<T>(Future<T> Function() body) async {
    if (GameLaunchManager().isActive) {
      throw Rpcs3InternalException('gameRunning', _saves('busyGameRunning'));
    }
    if (_libraryMutationInProgress ||
        _runtimePreparation != null ||
        _state.phase == Rpcs3RuntimePhase.importingContent) {
      throw Rpcs3InternalException('libraryBusy', _saves('busyLibrary'));
    }
    _libraryMutationInProgress = true;
    try {
      if (saveExchangeCoreInitializedOverride ?? _initialized) {
        final emulation = await saveExchangeEmulationState();
        if (emulation != 0 && emulation != 1) {
          throw Rpcs3InternalException(
            'gameRunning',
            _saves('busyGameRunning'),
          );
        }
      }
      return await body();
    } finally {
      _libraryMutationInProgress = false;
    }
  }

  static Future<Map<String, dynamic>> _jitStatus() => _bounded(
    Rpcs3InternalBridge.jitStatus(),
    _statusTimeout,
    'jitStatusTimeout',
    'RPCS3 could not read the current JIT state.',
  );

  /// UI-level JIT state. Unlike the RPCS3 Core launch gate, this intentionally
  /// accepts the kernel CS_DEBUGGED bit as proof that integrated StikJIT has
  /// enabled JIT for the current NeoStation process. The stricter live
  /// debugger/nonce handshake remains mandatory for Core loading.
  static Future<bool> jitEnabledForUi() async {
    if (!supported) return false;
    if (_jitPrepared || _state.jitReady) return true;
    try {
      final status = await _jitStatus();
      return status['debugged'] == true;
    } catch (_) {
      return false;
    }
  }

  static Future<Map<String, dynamic>> diagnostics() async {
    final core = await _bounded(
      Rpcs3InternalBridge.diagnostics(),
      _statusTimeout,
      'diagnosticsTimeout',
      'RPCS3 diagnostics did not respond.',
    );
    final jit = await _jitStatus();
    final jitEnabled =
        _jitPrepared || _state.jitReady || jit['debugged'] == true;
    return <String, dynamic>{
      ...core,
      'jit': jit,
      'jitPrepared': _jitPrepared,
      'jitEnabled': jitEnabled,
      'runtimeMode': _initialized ? 'ready' : 'stopped',
    };
  }

  /// Single RPCS3 startup owner.
  ///
  /// The launch path is deliberately linear:
  /// LocalDevVPN route -> pairing -> StikJIT attach -> Core load/initialize
  /// -> helper completion -> ready. There is no automatic retry, Core shutdown,
  /// JIT status polling, memory preflight, watchdog, fallback, or second attach.
  static Future<void> _ensureRuntime() {
    if (_libraryMutationInProgress) {
      throw Rpcs3InternalException('libraryBusy', _ui('operationFailed'));
    }
    if (_initialized) return Future<void>.value();

    final pending = _runtimePreparation;
    if (pending != null) return pending;

    final future = _initializeRuntime();
    _runtimePreparation = future;
    return future.whenComplete(() {
      if (identical(_runtimePreparation, future)) {
        _runtimePreparation = null;
      }
    });
  }

  static Future<void> _initializeRuntime() async {
    if (!supported) {
      throw Rpcs3InternalException('unsupported', _ui('operationFailed'));
    }
    if (_initialized) return;

    // The Files workspace folders are ensured before an explicit Core
    // startup (nothing is imported or exported here: saves move only on
    // the user's action through Rpcs3SaveExchangeService).
    try {
      await synchronizeFilesWorkspace();
    } catch (error) {
      _log.w('RPCS3 Files workspace preflight failed: $error');
    }

    var completionPending = false;
    try {
      _emit(
        Rpcs3RuntimePhase.checkingJit,
        _ui('enabling'),
        jitReady: false,
        coreReady: false,
      );
      try {
        await LocalDevVpnRouteService.ensureReachable();
      } on LocalDevVpnRouteException catch (error) {
        _log.w('RPCS3 route unavailable: ${error.message} (nativeRouteCode=${error.code})');
        throw Rpcs3InternalException('RPCS3_ROUTE_UNAVAILABLE', _ui('operationFailed'));
      }

      if (!await PairingFileService.hasStoredPairingFile()) {
        throw Rpcs3InternalException('RPCS3_PAIRING_FILE_INVALID', _ui('operationFailed'));
      }

      final data = await dataDirectory();
      final cache = await cacheDirectory();
      final pairing = await PairingFileService.storedFile();

      _emit(
        Rpcs3RuntimePhase.enablingJit,
        _ui('enabling'),
        jitReady: false,
        coreReady: false,
      );
      final jit = await _bounded(
        Rpcs3InternalBridge.prepareJit(pairingFilePath: pairing.path),
        _jitTimeout,
        'RPCS3_JIT_PREPARATION_TIMEOUT',
        _ui('operationFailed'),
      );
      if (jit['success'] != true) {
        throw Rpcs3InternalException(
          jit['code']?.toString() ?? 'RPCS3_JIT_ATTACH_FAILED',
          jit['message']?.toString() ?? _ui('operationFailed'),
        );
      }
      completionPending = jit['requiresCompletion'] == true;

      _emit(
        Rpcs3RuntimePhase.initializingCore,
        _ui('jitCoreWillPrepare'),
        jitReady: false,
        coreReady: false,
      );
      final core = await _bounded(
        Rpcs3InternalBridge.initialize(
          supportPath: data.path,
          cachePath: cache.path,
          expandedJitRegion: false,
        ),
        _coreTimeout,
        'RPCS3_CORE_INITIALIZE_TIMEOUT',
        _ui('operationFailed'),
      );
      if (core['success'] != true) {
        throw Rpcs3InternalException(
          core['code']?.toString() ?? 'RPCS3_CORE_INITIALIZE_FAILED',
          core['message']?.toString() ?? _ui('operationFailed'),
        );
      }

      if (completionPending) {
        final completion = await _bounded(
          Rpcs3InternalBridge.completeJit(),
          _jitCompletionTimeout,
          'RPCS3_JIT_DETACH_TIMEOUT',
          _ui('operationFailed'),
        );
        if (completion['success'] != true) {
          throw Rpcs3InternalException(
            completion['code']?.toString() ?? 'RPCS3_JIT_DETACH_FAILED',
            completion['message']?.toString() ?? _ui('operationFailed'),
          );
        }
        completionPending = false;
      }

      // Library discovery may precede Core loading. Publish its local serial
      // recommendations once here, after helper completion, before becoming
      // ready; this does not mutate global or explicit per-game user settings.
      await Rpcs3GameProfileService.publishDetectedProfilesForReadyRuntime();
      _jitPrepared = true;
      _initialized = true;
      _emit(
        Rpcs3RuntimePhase.ready,
        _ui('ready'),
        jitReady: true,
        coreReady: true,
      );
      _log.i('RPCS3 minimal startup complete.');
    } on Rpcs3InternalException catch (error) {
      // Cleanup only the helper transaction. Never shutdown or reinitialize the
      // Core automatically: a failed startup remains the original failure.
      if (completionPending) {
        try {
          await Rpcs3InternalBridge.completeJit().timeout(
            _jitCompletionTimeout,
          );
        } catch (_) {}
      }
      _jitPrepared = false;
      _emit(
        Rpcs3RuntimePhase.error,
        error.message,
        jitReady: false,
        coreReady: false,
        error: error.message,
      );
      rethrow;
    }
  }

  /// A Universal attach cannot be pre-warmed independently of the Core.
  /// Opening the manager only inspects status; an explicit action starts JIT.
  static Future<void> prepareManager() async {
    await _jitStatus();
  }

  static Future<void> ensureJitReady() => _ensureRuntime();

  static Future<void> ensureManagementInitialized() => _ensureRuntime();

  /// Management of files must remain usable when VPN/JIT/Core startup fails.
  static Future<void> deleteInstalledGame(String titleId) async {
    if (_libraryMutationInProgress ||
        _runtimePreparation != null ||
        GameLaunchManager().isActive ||
        _state.phase == Rpcs3RuntimePhase.importingContent) {
      throw Rpcs3InternalException('libraryBusy', _ui('operationFailed'));
    }
    _libraryMutationInProgress = true;
    final id = titleId.trim().toUpperCase();
    _log.i('Rpcs3Delete[$id] begin; coreInitialized=$_initialized');
    try {
      if (_initialized) {
        final emulation = await Rpcs3InternalBridge.emulationState();
        if (emulation != 0 && emulation != 1) {
          throw Rpcs3InternalException('gameRunning', _ui('operationFailed'));
        }
      }
      final root = await dataDirectory();
      await Rpcs3GameDeletion.delete(dataRoot: root.path, titleId: id);
      _log.i('Rpcs3Delete[$id] filesystem_and_registration_complete');
      await SqliteService.deleteRpcs3Title(id);
      await Rpcs3LibraryService.forgetDeletedTitle(id);
      await Rpcs3LibraryService.syncInternalLibrary();
      _log.i('Rpcs3Delete[$id] database_cache_and_ui_complete');
    } catch (error, stack) {
      _log.e('Rpcs3Delete[$id] failed', error: error, stackTrace: stack);
      rethrow;
    } finally {
      _libraryMutationInProgress = false;
    }
  }

  static Future<void> ensureInitialized() => _ensureRuntime();
  static Future<void> ensureGameplayInitialized() => _ensureRuntime();
  static Future<void> closeManagementRuntime() async {}

  static Future<String> firmwareVersion() async {
    // RPCS3's utils::get_firmware_version reads this same file under dev_flash.
    // Opening a library must not dlopen the Core or request JIT just to read it.
    // Read the actual install every time, including installs from older builds
    // or the manager, instead of trusting a preference flag.
    final data = await dataDirectory();
    final file = File(
      path.join(data.path, 'dev_flash', 'vsh', 'etc', 'version.txt'),
    );
    if (!await file.exists()) return '';
    final size = await file.length();
    if (size == 0 || size > 65536) return '';
    final record = await file.readAsString();
    final match = RegExp(
      r'^release:(\d+)\.(\d+):',
      multiLine: true,
    ).firstMatch(record.trim());
    if (match == null) return '';
    final major = int.tryParse(match.group(1)!);
    if (major == null) return '';
    var minor = match.group(2)!;
    while (minor.length > 2 && minor.endsWith('0')) {
      minor = minor.substring(0, minor.length - 1);
    }
    return '$major.${minor.padRight(2, '0')}';
  }

  static Future<bool> hasFirmware() async {
    try {
      return (await firmwareVersion()).isNotEmpty;
    } catch (_) {
      return false;
    }
  }

  /// Thin wrapper kept for the dormant playlist branches: exports every
  /// valid game save of user 00000001 to a ZIP in
  /// `Documents/RPCS3/Export/Game Saves` (see [Rpcs3SaveExchangeService])
  /// and returns that folder. Firmware, games, caches, trophies,
  /// savestates and configuration stay private; the live tree is not
  /// touched. The manager uses the service directly to show the report.
  static Future<Directory> exportSaveData() async {
    final result = await Rpcs3SaveExchangeService.instance.exportGuarded();
    return Directory(path.dirname(result.zipPath));
  }

  /// Thin wrapper kept for the dormant playlist branches: imports the save
  /// folders and ZIP archives found in `Documents/RPCS3/Import/Game Saves`
  /// without replacing existing saves (no prompt is possible here) and
  /// returns the number of saves installed. The manager uses the service
  /// directly, with the replace prompt and the per-save report.
  static Future<int> importSaveDataFromFiles() async {
    final report = await Rpcs3SaveExchangeService.instance.importGuarded(
      Rpcs3SaveImportSourceKind.filesFolder,
      confirmReplace: (_) async => false,
    );
    if (report == null) return 0;
    return report.imported + report.replaced;
  }

  static Future<String> _stageFirmware(String sourcePath) async {
    final root = await rootDirectory();
    final imports = Directory(path.join(root.path, 'Imports'));
    await imports.create(recursive: true);
    final staged = File(
      path.join(
        imports.path,
        'PS3UPDAT-${DateTime.now().microsecondsSinceEpoch}.PUP',
      ),
    );
    await File(sourcePath).copy(staged.path);
    return staged.path;
  }

  static Future<bool> importFirmware() => StorageImportActivity.run(() async {
    // Present the picker immediately. JIT/Core preparation happens only after
    // the user has actually selected a firmware file.
    final picked = await FilePicker.pickFiles(
      dialogTitle: _ui('firmwarePicker'),
      allowMultiple: false,
      type: FileType.custom,
      allowedExtensions: const ['pup'],
      withData: false,
    );
    if (picked == null || picked.files.isEmpty) return false;

    final sourcePath = picked.files.single.path;
    if (sourcePath == null || !await File(sourcePath).exists()) {
      throw Rpcs3InternalException(
        'firmwareUnreadable',
        _ui('firmwareUnreadable'),
      );
    }

    String? stagedPath;
    try {
      stagedPath = await _stageFirmware(sourcePath);
      // The Core installs the staged copy: once it holds every byte (same
      // length), the picker's copies are not read again
      // (docs/storage-audit-cleanup.md § 4).
      await StoragePickerCopies.discardAfterVerifiedImport(
        sourcePath,
        expectedLength: (await File(stagedPath).stat()).size,
      );
      await ensureManagementInitialized();
      _emit(
        Rpcs3RuntimePhase.installingFirmware,
        _ui('installingFirmware'),
        jitReady: true,
        coreReady: true,
      );
      final report = await _bounded(
        Rpcs3InternalBridge.installFirmware(stagedPath),
        _firmwareInstallTimeout,
        'firmwareInstallTimeout',
        _ui('firmwareTimeout'),
      );
      if (report['success'] != true) {
        throw Rpcs3InternalException(
          'firmwareInstallFailed',
          report['message']?.toString() ?? _ui('firmwareRejected'),
        );
      }

      final version = (await _bounded(
        Rpcs3InternalBridge.firmwareVersion(),
        _statusTimeout,
        'firmwareStatusTimeout',
        _ui('firmwareNotConfirmed'),
      )).trim();
      if (version.isEmpty) {
        throw Rpcs3InternalException(
          'firmwareVerificationFailed',
          _ui('firmwareVerifyFailed'),
        );
      }
      _emit(
        Rpcs3RuntimePhase.ready,
        _ui('firmwareReady'),
        jitReady: true,
        coreReady: true,
      );
      _log.i('RPCS3 firmware installed successfully: $version');
      return true;
    } finally {
      if (stagedPath != null) {
        try {
          await File(stagedPath).delete();
        } catch (_) {}
      }
    }
  });

  static Future<Rpcs3ImportResult> importGames() => StorageImportActivity.run(() async {
    final picked = await FilePicker.pickFiles(
      dialogTitle: _ui('importGames'),
      allowMultiple: true,
      type: FileType.custom,
      allowedExtensions: const ['pkg', 'iso', 'zip'],
      withData: false,
    );
    if (picked == null) {
      return const Rpcs3ImportResult(imported: 0, rejected: 0);
    }

    await ensureManagementInitialized();
    _emit(
      Rpcs3RuntimePhase.importingContent,
      _ui('selectingGames'),
      jitReady: true,
      coreReady: true,
    );

    var imported = 0;
    var rejected = 0;
    final errors = <String>[];
    for (final item in picked.files) {
      final sourcePath = item.path;
      if (sourcePath == null || !await File(sourcePath).exists()) {
        rejected++;
        errors.add('${item.name}: ${_ui('operationFailed')}');
        continue;
      }

      final extension = path.extension(item.name).toLowerCase();
      Map<String, dynamic> report;
      if (extension == '.pkg') {
        report = await _bounded(
          Rpcs3InternalBridge.installPackage(sourcePath),
          _contentInstallTimeout,
          'gameImportTimeout',
          '${item.name}: ${_ui('operationFailed')}',
        );
      } else if (extension == '.zip') {
        report = await _bounded(
          Rpcs3InternalBridge.installZip(sourcePath),
          _contentInstallTimeout,
          'gameImportTimeout',
          '${item.name}: ${_ui('operationFailed')}',
        );
      } else if (extension == '.iso') {
        final key = File(path.setExtension(sourcePath, '.key'));
        report = await _bounded(
          Rpcs3InternalBridge.installIso(
            sourcePath,
            keyPath: await key.exists() ? key.path : null,
          ),
          _contentInstallTimeout,
          'gameImportTimeout',
          '${item.name}: ${_ui('operationFailed')}',
        );
      } else {
        report = <String, dynamic>{
          'success': false,
          'message': _ui('unsupportedGameFormat'),
        };
      }

      if (report['success'] == true) {
        imported++;
      } else {
        rejected++;
        errors.add(
          '${item.name}: ${report['message'] ?? _ui('importFailedShort')}',
        );
      }
    }

    await Rpcs3LibraryService.syncInternalLibrary();
    _emit(
      Rpcs3RuntimePhase.ready,
      _ui('ready'),
      jitReady: true,
      coreReady: true,
    );
    return Rpcs3ImportResult(
      imported: imported,
      rejected: rejected,
      errors: errors,
    );
  });

  static Future<bool> importExtractedGameFolder() => StorageImportActivity.run(() async {
    final folder = await FilePicker.getDirectoryPath(
      dialogTitle: _ui('importDecryptedFolder'),
    );
    if (folder == null) return false;

    await ensureManagementInitialized();
    _emit(
      Rpcs3RuntimePhase.importingContent,
      _ui('selectingFolder'),
      jitReady: true,
      coreReady: true,
    );
    final report = await _bounded(
      Rpcs3InternalBridge.installFolder(folder),
      _contentInstallTimeout,
      'gameImportTimeout',
      _ui('folderRejected'),
    );
    if (report['success'] != true) {
      throw Rpcs3InternalException(
        'gameImportFailed',
        report['message']?.toString() ?? _ui('folderRejected'),
      );
    }
    await Rpcs3LibraryService.syncInternalLibrary();
    _emit(
      Rpcs3RuntimePhase.ready,
      _ui('ready'),
      jitReady: true,
      coreReady: true,
    );
    return true;
  });

  static Future<bool> launchTitle(
    String titleId, {
    required String uiLocale,
    String? savestateId,
  }) async {
    final normalized = titleId.trim().toUpperCase();
    if (normalized.isEmpty) return false;

    if (!_initialized) {
      throw Rpcs3InternalException(
        'RPCS3_RUNTIME_NOT_READY',
        Rpcs3UiLocale.textForLocale(uiLocale, 'operationFailed'),
      );
    }
    final launchTimer = Stopwatch()..start();
    final firmware = (await _bounded(
      Rpcs3InternalBridge.firmwareVersion(),
      _statusTimeout,
      'firmwareStatusTimeout',
      Rpcs3UiLocale.textForLocale(uiLocale, 'operationFailed'),
    )).trim();
    if (firmware.isEmpty) {
      throw Rpcs3InternalException(
        'firmwareRequired',
        Rpcs3UiLocale.textForLocale(uiLocale, 'firmwareRequired'),
      );
    }

    _emit(
      Rpcs3RuntimePhase.launching,
      Rpcs3UiLocale.textForLocale(uiLocale, 'importingGame'),
      jitReady: true,
      coreReady: true,
    );

    final bootTimer = Stopwatch()..start();
    final report = await Rpcs3InternalBridge.launchGame(
      titleId: normalized,
      uiLocale: uiLocale,
      savestateId: savestateId,
    );
    if (report['success'] != true) {
      throw Rpcs3InternalException(
        report['code']?.toString() ?? 'RPCS3_GAME_BOOT_FAILED',
        report['message']?.toString() ??
            Rpcs3UiLocale.textForLocale(uiLocale, 'operationFailed'),
      );
    }
    _log.i(
      'RPCS3 launch timing $normalized: stage=boot_submitted; '
      'bootMs=${bootTimer.elapsedMilliseconds}; '
      'totalMs=${launchTimer.elapsedMilliseconds}.',
    );

    _emit(
      Rpcs3RuntimePhase.ready,
      Rpcs3UiLocale.textForLocale(uiLocale, 'ready'),
      jitReady: true,
      coreReady: true,
    );
    return true;
  }

  static Future<bool> stop() async {
    final stopped = await Rpcs3InternalBridge.stop();
    if (stopped) {
      try {
        await synchronizeFilesWorkspace();
      } catch (error) {
        _log.w('RPCS3 Files workspace refresh after stop failed: $error');
      }
    }
    return stopped;
  }
}
