import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../models/system_model.dart';
import '../providers/sqlite_config_provider.dart';
import '../repositories/system_repository.dart';
import 'libretro_core_catalog.dart';
import 'libretro_internal_service.dart';
import 'logger_service.dart';

/// Where an embedded console stands in the main menu.
enum LibretroMainMenuPresence {
  /// No system of the console is detected.
  absent,

  /// At least one system of the console is shown.
  present,

  /// Its systems are detected but all hidden (Settings › Systems).
  hidden,
}

/// [LibretroMainMenuPresence] of a console and the detected systems that
/// stand for it (the shown ones when present, the hidden ones when hidden).
class LibretroMainMenuState {
  const LibretroMainMenuState(this.presence, this.systems);

  final LibretroMainMenuPresence presence;
  final List<SystemModel> systems;

  bool get isPresent => presence == LibretroMainMenuPresence.present;
  bool get isHidden => presence == LibretroMainMenuPresence.hidden;
  bool get isAbsent => presence == LibretroMainMenuPresence.absent;

  /// Product names of [systems], as the main menu shows them.
  String get systemNames => systems
      .map(
        (system) =>
            system.realName.isNotEmpty ? system.realName : system.folderName,
      )
      .join(', ');
}

enum LibretroMainMenuAddStatus {
  /// The console's system was added to the main menu.
  added,

  /// A hidden system of the console is shown again.
  shown,

  /// The console was already in the main menu: nothing was written.
  alreadyPresent,

  /// An add of the same console is still running.
  inProgress,

  /// NeoStation has no system definition for the console.
  systemUnknown,

  /// Nothing changed; [LibretroMainMenuAddResult.error] holds the detail.
  failed,
}

class LibretroMainMenuAddResult {
  const LibretroMainMenuAddResult(this.status, {this.system, this.error});

  final LibretroMainMenuAddStatus status;

  /// System that stands for the console in the main menu.
  final SystemModel? system;

  /// Technical detail of a failure, kept apart from the translated message.
  final String? error;

  bool get succeeded =>
      status == LibretroMainMenuAddStatus.added ||
      status == LibretroMainMenuAddStatus.shown ||
      status == LibretroMainMenuAddStatus.alreadyPresent;
}

/// Embedded (libretro) consoles the user added to the main menu from the
/// consoles tab (Build 440).
///
/// A console is in the main menu when one of its systems is detected
/// (`user_detected_systems`), whatever its game count. Adding one registers
/// the console's import system through the existing public APIs
/// ([SystemRepository.addDetectedSystem], then
/// [SqliteConfigProvider.refreshDetectedSystems]): no scan, no ROM folder,
/// no game, file, system setting or sort preference is touched, and nothing
/// is ever removed.
///
/// The library scanner (unchanged) keeps only systems with games, so the
/// consoles added here are also remembered in SharedPreferences
/// ([preferenceKey], console ids) and the keeper started by [attach] adds a
/// remembered console back as soon as a scan, a system refresh or the
/// removal of the last ROM folder has dropped it, with its hidden state
/// (Settings › Systems) kept. The keeper awaits no file or preference I/O
/// on that path, so the console is back before the next frame.
class LibretroMainMenu {
  LibretroMainMenu({
    Future<List<String>> Function()? availableCores,
    @visibleForTesting bool Function(SqliteConfigProvider provider)? isReady,
    @visibleForTesting Future<SharedPreferences> Function()? preferences,
  }) : _availableCores =
           availableCores ?? LibretroInternalBridge.availableCores,
       _isReady = isReady ?? _initialized,
       _preferences = preferences ?? SharedPreferences.getInstance;

  static final LibretroMainMenu instance = LibretroMainMenu();

  /// SharedPreferences list of the console ids added from the consoles tab.
  static const String preferenceKey = 'libretro_main_menu_v1';

  /// Systems bound to a console for its core and frontend settings only,
  /// while being other hardware (the Sega Pico runs on PicoDrive with the
  /// Mega Drive settings): they never count as that console.
  static const Set<String> _otherHardware = <String>{'pico'};

  static final _log = LoggerService.instance;

  final Future<List<String>> Function() _availableCores;
  final bool Function(SqliteConfigProvider provider) _isReady;
  final Future<SharedPreferences> Function() _preferences;

  List<String> _pinned = const <String>[];
  bool _loaded = false;
  Future<void>? _loading;
  Set<String>? _bundled;
  Future<Set<String>?>? _bundledReading;
  final Set<String> _adding = <String>{};

  SqliteConfigProvider? _provider;
  Object? _owner;
  bool _listening = false;
  bool _wasBusy = true;
  bool _edgeSeen = false;
  bool _restoring = false;
  String? _lastAttempt;

  static bool _initialized(SqliteConfigProvider provider) =>
      provider.initialized;

  /// Console ids remembered by [add], in the order they were added.
  List<String> get pinned => List<String>.unmodifiable(_pinned);

  /// Whether [add] is running for [consoleId].
  bool isAdding(String consoleId) => _adding.contains(consoleId);

  /// Reads the remembered consoles once; a failed read is retried by the
  /// next call, and nothing is remembered before a read succeeded (an add
  /// would otherwise overwrite the stored list).
  Future<void> load() {
    if (_loaded) return Future<void>.value();
    return _loading ??= _readPins().whenComplete(() => _loading = null);
  }

  Future<void> _readPins() async {
    try {
      final preferences = await _preferences();
      _pinned = List<String>.unmodifiable(
        preferences.getStringList(preferenceKey) ?? const <String>[],
      );
      _loaded = true;
    } catch (error) {
      _log.w('Libretro main menu consoles not read: $error');
    }
  }

  /// Console a detected system stands for, null when the embedded engine
  /// does not run it (or runs it as other hardware, see [_otherHardware]).
  static String? consoleIdOf(SystemModel system) {
    final key = LibretroInternalService.systemKey(system);
    if (_otherHardware.contains(key)) return null;
    return LibretroCoreCatalog.bindingFor(key)?.console;
  }

  /// Where [console] stands among the [detected] systems, [hidden] being the
  /// folders hidden in Settings › Systems. A console counts once whatever
  /// system stands for it: Sega Genesis makes the Mega Drive present, so
  /// adding it never creates a second tile for the same hardware.
  static LibretroMainMenuState stateOf(
    LibretroConsole console,
    Iterable<SystemModel> detected,
    Set<String> hidden,
  ) {
    final systems = <SystemModel>[
      for (final system in detected)
        if (consoleIdOf(system) == console.id) system,
    ];
    final shown = <SystemModel>[
      for (final system in systems)
        if (!hidden.contains(system.folderName)) system,
    ];
    if (shown.isNotEmpty) {
      return LibretroMainMenuState(LibretroMainMenuPresence.present, shown);
    }
    if (systems.isNotEmpty) {
      return LibretroMainMenuState(LibretroMainMenuPresence.hidden, systems);
    }
    return const LibretroMainMenuState(
      LibretroMainMenuPresence.absent,
      <SystemModel>[],
    );
  }

  /// Ids of the consoles whose core ships in this build (default core or
  /// an alternative of the console's import system); null when the build
  /// could not be asked, retried by the next call.
  Future<Set<String>?> bundledConsoles() {
    final known = _bundled;
    if (known != null) return Future<Set<String>?>.value(known);
    return _bundledReading ??= _readBundled().whenComplete(
      () => _bundledReading = null,
    );
  }

  Future<Set<String>?> _readBundled() async {
    try {
      final cores = (await _availableCores()).toSet();
      return _bundled = Set<String>.unmodifiable(<String>{
        for (final console in LibretroCoreCatalog.consoles.values)
          if (_coresOf(console).any(cores.contains)) console.id,
      });
    } catch (error) {
      _log.w('Embedded libretro cores not listed: $error');
      return null;
    }
  }

  static List<String> _coresOf(LibretroConsole console) {
    final binding = LibretroCoreCatalog.bindingFor(console.importSystem);
    return binding == null
        ? const <String>[]
        : <String>[binding.coreId, ...binding.alternatives];
  }

  /// Puts [console] in the main menu: shows it again when it is hidden,
  /// otherwise adds its import system, remembered so that it stays after
  /// the next scans. Writes nothing when the console is already present.
  Future<LibretroMainMenuAddResult> add(
    LibretroConsole console,
    SqliteConfigProvider provider,
  ) async {
    if (!_adding.add(console.id)) {
      return const LibretroMainMenuAddResult(
        LibretroMainMenuAddStatus.inProgress,
      );
    }
    try {
      await load();
      final state = stateOf(
        console,
        provider.detectedSystems,
        provider.hiddenSystemFolders,
      );
      switch (state.presence) {
        case LibretroMainMenuPresence.present:
          return LibretroMainMenuAddResult(
            LibretroMainMenuAddStatus.alreadyPresent,
            system: state.systems.first,
          );
        case LibretroMainMenuPresence.hidden:
          return await _show(console, state, provider);
        case LibretroMainMenuPresence.absent:
          return await _addSystem(console, provider);
      }
    } catch (error) {
      _log.w(
        'Libretro console ${console.id} not added to the main menu: $error',
      );
      return LibretroMainMenuAddResult(
        LibretroMainMenuAddStatus.failed,
        error: '$error',
      );
    } finally {
      _adding.remove(console.id);
    }
  }

  Future<LibretroMainMenuAddResult> _show(
    LibretroConsole console,
    LibretroMainMenuState state,
    SqliteConfigProvider provider,
  ) async {
    final target = state.systems.firstWhere(
      (system) =>
          LibretroInternalService.systemKey(system) == console.importSystem,
      orElse: () => state.systems.first,
    );
    // Without games, the next scan would drop the shown system again.
    if (target.romCount == 0) {
      final pinError = await _pin(console.id);
      if (pinError != null) {
        return LibretroMainMenuAddResult(
          LibretroMainMenuAddStatus.failed,
          error: pinError,
        );
      }
    }
    if (provider.hiddenSystemFolders.contains(target.folderName)) {
      await provider.toggleSystemHidden(target.folderName);
    }
    if (!stateOf(
      console,
      provider.detectedSystems,
      provider.hiddenSystemFolders,
    ).isPresent) {
      return LibretroMainMenuAddResult(
        LibretroMainMenuAddStatus.failed,
        error: '${target.folderName} still hidden',
      );
    }
    return LibretroMainMenuAddResult(
      LibretroMainMenuAddStatus.shown,
      system: target,
    );
  }

  Future<LibretroMainMenuAddResult> _addSystem(
    LibretroConsole console,
    SqliteConfigProvider provider,
  ) async {
    final system =
        _knownSystem(console, provider) ?? await _storedSystem(console);
    final systemId = system?.id;
    if (system == null || systemId == null) {
      return const LibretroMainMenuAddResult(
        LibretroMainMenuAddStatus.systemUnknown,
      );
    }
    final newlyPinned = !_pinned.contains(console.id);
    final pinError = await _pin(console.id);
    if (pinError != null) {
      return LibretroMainMenuAddResult(
        LibretroMainMenuAddStatus.failed,
        error: pinError,
      );
    }
    try {
      await SystemRepository.addDetectedSystem(systemId, system.folderName);
      // Hidden earlier, then dropped by a scan: the user asks to see it.
      if (provider.hiddenSystemFolders.contains(system.folderName)) {
        await provider.toggleSystemHidden(system.folderName);
      }
      await provider.refreshDetectedSystems();
    } catch (_) {
      if (newlyPinned) await _unpin(console.id);
      rethrow;
    }
    if (!stateOf(
      console,
      provider.detectedSystems,
      provider.hiddenSystemFolders,
    ).isPresent) {
      if (newlyPinned) await _unpin(console.id);
      return LibretroMainMenuAddResult(
        LibretroMainMenuAddStatus.failed,
        error: '$systemId not listed after refresh',
      );
    }
    return LibretroMainMenuAddResult(
      LibretroMainMenuAddStatus.added,
      system: system,
    );
  }

  /// The import system of [console] among the provider's systems (memory).
  static SystemModel? _knownSystem(
    LibretroConsole console,
    SqliteConfigProvider provider,
  ) {
    for (final system in provider.availableSystems) {
      if (system.id == console.importSystem) return system;
    }
    return null;
  }

  static Future<SystemModel?> _storedSystem(LibretroConsole console) async {
    try {
      return await SystemRepository.getSystemById(console.importSystem);
    } catch (error) {
      _log.w(
        'Libretro import system ${console.importSystem} unavailable: $error',
      );
      return null;
    }
  }

  /// Remembers [consoleId]; returns the failure detail, null when saved.
  Future<String?> _pin(String consoleId) async {
    if (!_loaded) return '$preferenceKey not read';
    if (_pinned.contains(consoleId)) return null;
    final next = <String>[..._pinned, consoleId];
    try {
      final preferences = await _preferences();
      if (!await preferences.setStringList(preferenceKey, next)) {
        return '$preferenceKey not saved';
      }
      _pinned = List<String>.unmodifiable(next);
      return null;
    } catch (error) {
      return '$preferenceKey not saved: $error';
    }
  }

  Future<void> _unpin(String consoleId) async {
    if (!_loaded) return;
    final next = <String>[
      for (final id in _pinned)
        if (id != consoleId) id,
    ];
    try {
      final preferences = await _preferences();
      if (await preferences.setStringList(preferenceKey, next)) {
        _pinned = List<String>.unmodifiable(next);
      }
    } catch (error) {
      _log.w('Libretro main menu console $consoleId not forgotten: $error');
    }
  }

  /// Starts the keeper on [provider] once the remembered consoles are read.
  /// The last [owner] to attach is the one whose [detach] stops it, so a
  /// screen replaced by a new one (which attached first) cannot stop the
  /// keeper of its successor.
  Future<void> attach(SqliteConfigProvider provider, {Object? owner}) async {
    _owner = owner;
    if (identical(_provider, provider)) return;
    _stop();
    _provider = provider;
    _wasBusy = true;
    _edgeSeen = false;
    _lastAttempt = null;
    await load();
    if (!identical(_provider, provider) || _listening) return;
    provider.addListener(_onProviderChanged);
    _listening = true;
    _onProviderChanged();
  }

  /// Stops the keeper, unless another [owner] attached since.
  void detach({Object? owner}) {
    if (owner != null && !identical(owner, _owner)) return;
    _owner = null;
    _stop();
  }

  void _stop() {
    if (_listening) _provider?.removeListener(_onProviderChanged);
    _listening = false;
    _provider = null;
  }

  bool _busy(SqliteConfigProvider provider) =>
      provider.isScanning ||
      provider.isLoading ||
      provider.isSilentScanning ||
      !_isReady(provider);

  /// Remembered consoles that no detected system stands for.
  List<LibretroConsole> _missing(SqliteConfigProvider provider) =>
      <LibretroConsole>[
        for (final id in _pinned)
          if (!_adding.contains(id))
            if (LibretroCoreCatalog.consoles[id] case final console?)
              if (stateOf(
                console,
                provider.detectedSystems,
                provider.hiddenSystemFolders,
              ).isAbsent)
                console,
      ];

  /// Adds the dropped consoles back once the provider is idle: on each
  /// busy-to-idle edge (scans) and whenever the set of dropped consoles
  /// changes (a system refresh drops one without being busy). The same set
  /// is not retried before the next edge, so a system the database refuses
  /// never loops.
  void _onProviderChanged() {
    final provider = _provider;
    if (provider == null) return;
    final busy = _busy(provider);
    if (_wasBusy && !busy) _edgeSeen = true;
    _wasBusy = busy;
    if (busy || _restoring) return;
    final edge = _edgeSeen;
    _edgeSeen = false;
    final missing = _missing(provider);
    if (missing.isEmpty) {
      _lastAttempt = null;
      return;
    }
    final signature = missing.map((console) => console.id).join(',');
    if (!edge && signature == _lastAttempt) return;
    _lastAttempt = signature;
    unawaited(_restore(provider, missing));
  }

  Future<void> _restore(
    SqliteConfigProvider provider,
    List<LibretroConsole> missing,
  ) async {
    _restoring = true;
    try {
      var written = false;
      for (final console in missing) {
        final system =
            _knownSystem(console, provider) ?? await _storedSystem(console);
        final systemId = system?.id;
        if (system == null || systemId == null) {
          _log.w(
            'Libretro console ${console.id} not restored: no ${console.importSystem} system',
          );
          continue;
        }
        await SystemRepository.addDetectedSystem(systemId, system.folderName);
        // A scan rewrites the detected systems without the dropped ones'
        // hidden flag: keep the user's choice.
        if (provider.hiddenSystemFolders.contains(system.folderName)) {
          await SystemRepository.setSystemHidden(system.folderName, true);
        }
        written = true;
      }
      if (written && identical(_provider, provider)) {
        await provider.refreshDetectedSystems();
      }
    } catch (error) {
      _log.w('Libretro main menu consoles not restored: $error');
    } finally {
      _restoring = false;
      if (identical(_provider, provider)) _onProviderChanged();
    }
  }
}
