import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:retro_achievements_session/retro_achievements_session.dart';

import '../models/retro_achievements_session.dart';
import '../repositories/retro_achievements_repository.dart';

/// The main RA tab is the only writer. Every embedded launch asks this service
/// for an immutable policy; account changes never mutate a running game.
class RetroAchievementsSessionService extends ChangeNotifier {
  RetroAchievementsSessionService({RetroAchievementsNativeClient? native,
    Future<RetroAchievementsPreferences> Function()? readPreferences,
    Future<void> Function(RetroAchievementsPreferences)? writePreferences})
    : _native = native ?? RetroAchievementsNativeClient(),
      _readPreferences = readPreferences ?? RetroAchievementsRepository.loadSessionPreferences,
      _writePreferences = writePreferences ?? RetroAchievementsRepository.saveSessionPreferences {
    _native.onSessionChanged = _onSessionChanged;
  }

  static final shared = RetroAchievementsSessionService();
  final RetroAchievementsNativeClient _native;
  final Future<RetroAchievementsPreferences> Function() _readPreferences;
  final Future<void> Function(RetroAchievementsPreferences) _writePreferences;
  Future<void>? _initializing;
  Future<void> _writes = Future<void>.value();
  RetroAchievementsPreferences _preferences = const RetroAchievementsPreferences();
  RetroAchievementsPreferences get preferences => _preferences;
  RetroAchievementsSessionState? _session;
  RetroAchievementsSessionState? get session => _session;
  bool _authenticated = false;
  bool get authenticated => _authenticated;
  String _username = '';
  String get username => _username;
  bool get available => _native.available;
  bool _initialized = false;
  bool get initialized => _initialized;
  bool _accountLoaded = false;
  bool get canRecoverLegacy => !_initialized && _accountLoaded && _preferences.migrationVersion < 1;
  bool _busy = false;
  bool get busy => _busy;
  String? _errorCode;
  String? get errorCode => _errorCode;
  int _generation = 0;
  bool _disposed = false;
  List<RetroAchievementsMigrationCandidate> _migrationCandidates = const [];
  List<RetroAchievementsMigrationCandidate> get migrationCandidates => _migrationCandidates;
  bool get changesPending => _session?.running == true && _session!.generation != _generation;

  void _notify() { if (!_disposed) notifyListeners(); }

  Future<void> initialize() => _initializing ??= _initialize();

  Future<void> _initialize() async {
    _initialized = false;
    _accountLoaded = false;
    if (!available) { _initialized = true; _notify(); return; }
    try {
      _preferences = await _readPreferences();
      final account = await _native.invoke('account');
      _authenticated = account['authenticated'] == true;
      _username = account['username'] as String? ?? '';
      _accountLoaded = true;
      final active = account['session'];
      if (active is Map && active.isNotEmpty) {
        _session = RetroAchievementsSessionState(Map<String, Object?>.from(active));
        _generation = _session!.generation;
      }
      if (_preferences.migrationVersion < 1) await _migrateLegacy();
      _errorCode = null;
      _initialized = true;
    } on PlatformException catch (error) {
      _errorCode = error.code;
    } on MissingPluginException {
      _errorCode = 'RA_UNAVAILABLE';
    } catch (_) {
      _errorCode = 'RA_STORAGE_UNAVAILABLE';
    }
    _notify();
  }

  Future<void> retry() async {
    if (_busy) return;
    _initializing = null;
    await initialize();
  }

  Future<void> _migrateLegacy() async {
    final legacy = await _native.invoke('inspectLegacy');
    if (legacy['central'] == true) {
      await _finishMigration(legacy);
      return;
    }
    final candidates = (legacy['candidates'] as List? ?? const [])
      .map((item) => RetroAchievementsMigrationCandidate.fromMap(Map<Object?, Object?>.from(item as Map)))
      .toList(growable: false);
    _migrationCandidates = List.unmodifiable(candidates);
    if (candidates.length == 1) {
      await _finishMigration(await _native.invoke('importLegacy', {'id': candidates.single.id}));
    } else if (candidates.isEmpty) {
      final next = _preferences.copyWith(enabled: false, migrationVersion: 1);
      await _writePreferences(next);
      _preferences = next;
      await _native.invoke('completeLegacy');
    }
    // Conflicting accounts/settings are shown only in the main RA tab. Games
    // may still launch, but no legacy store can independently enable RA.
  }

  Future<void> _finishMigration(Map<String, Object?> account) async {
    if (account['authenticated'] != true) throw PlatformException(code: 'RA_LOGIN_REQUIRED');
    final policy = account['policy'] is Map ? account['policy'] as Map : const {};
    final next = _preferences.copyWith(
      enabled: policy['enabled'] is bool ? policy['enabled'] as bool : _preferences.enabled,
      hardcore: policy['hardcore'] is bool ? policy['hardcore'] as bool : _preferences.hardcore,
      migrationVersion: 1);
    // The native Keychain record keeps this policy until this transaction has
    // committed. A crash/write failure resumes the same account on next start.
    await _writePreferences(next);
    _preferences = next;
    _authenticated = true;
    _username = account['username'] as String? ?? '';
    _migrationCandidates = const [];
    _generation++;
    await _native.invoke('completeLegacy');
  }

  Future<bool> importLegacy(String id) => _mutate(() async {
    if (!_migrationCandidates.any((candidate) => candidate.id == id)) {
      throw PlatformException(code: 'RA_MIGRATION_EXPIRED');
    }
    await _finishMigration(await _native.invoke('importLegacy', {'id': id}));
  });

  Future<bool> ignoreLegacy() => _mutate(() async {
    final next = _preferences.copyWith(enabled: false, hardcore: false, migrationVersion: 1);
    await _writePreferences(next);
    _preferences = next; _generation++;
    _initialized = true;
    await _native.invoke('logout');
    _authenticated = false; _username = '';
    _migrationCandidates = const [];
    await _native.invoke('completeLegacy');
    _initialized = true;
  }, allowLegacyRecovery: true);

  Future<bool> _mutate(Future<void> Function() operation, {bool allowLegacyRecovery = false}) {
    final completed = Completer<bool>();
    // Durable writes and account changes use one queue; a fast second toggle
    // cannot overwrite the last choice with an older database completion.
    _writes = _writes.then((_) async {
      final previousError = _errorCode;
      _busy = true; _errorCode = null; _notify();
      try {
        await initialize();
        if (!available || (!_initialized && !(allowLegacyRecovery && canRecoverLegacy))) {
          throw PlatformException(code: _errorCode ?? previousError ?? 'RA_UNAVAILABLE');
        }
        await operation();
        _errorCode = null;
        completed.complete(true);
      } on PlatformException catch (error) {
        _errorCode = error.code; completed.complete(false);
      } catch (_) {
        _errorCode = 'RA_STORAGE_UNAVAILABLE'; completed.complete(false);
      } finally {
        _busy = false; _notify();
      }
    });
    return completed.future;
  }

  Future<bool> setEnabled(bool enabled) => _mutate(() async {
    if (enabled && !_authenticated) throw PlatformException(code: 'RA_LOGIN_REQUIRED');
    final next = _preferences.copyWith(enabled: enabled);
    await _writePreferences(next);
    _preferences = next; _generation++;
  });

  Future<bool> setHardcore(bool hardcore) => _mutate(() async {
    final next = _preferences.copyWith(hardcore: hardcore);
    await _writePreferences(next);
    _preferences = next; _generation++;
  });

  Future<bool> login(String username, String password) => _mutate(() async {
    final account = await _native.invoke('login', {'username': username.trim(), 'password': password});
    if (account['authenticated'] != true) throw PlatformException(code: 'RA_AUTHENTICATION_FAILED');
    _authenticated = true;
    _username = account['username'] as String? ?? username.trim();
    _generation++;
    final next = _preferences.copyWith(migrationVersion: 1);
    await _writePreferences(next);
    _preferences = next;
    _migrationCandidates = const [];
    await _native.invoke('completeLegacy');
    _initialized = true;
  }, allowLegacyRecovery: true);

  Future<bool> logout() => _mutate(() async {
    // Persist disabled first: even an interrupted sign-out cannot enable RA at
    // the next launch. A failed Keychain delete remains visible and retryable.
    final next = _preferences.copyWith(enabled: false, migrationVersion: 1);
    await _writePreferences(next);
    _preferences = next; _generation++;
    _initialized = true;
    await _native.invoke('logout');
    _authenticated = false; _username = '';
    _migrationCandidates = const [];
    await _native.invoke('completeLegacy');
    _initialized = true;
  }, allowLegacyRecovery: true);

  Future<Map<String, Object?>> prepareLaunch({required String engine,
    required String system, String? core, required String language, bool systemMenu = false}) async {
    await initialize();
    await _writes;
    final capability = RetroAchievementsCapabilities.forEngine(engine,
      system: system, core: core, systemMenu: systemMenu);
    if (!available) return const {};
    try {
      final result = await _native.invoke('prepareSession', {
        'engine': engine, 'system': system, 'core': core ?? '', 'language': language,
        'capability': capability.name,
        'supported': capability == RetroAchievementsCapability.supported,
        'enabled': _initialized && _preferences.enabled && _authenticated,
        'hardcore': _preferences.hardcore, 'generation': _generation,
      });
      return result;
    } on PlatformException catch (error) {
      _errorCode = error.code;
    } on MissingPluginException {
      _errorCode = 'RA_UNAVAILABLE';
    }
    // RA preparation is independent of game boot. Missing handles are refused
    // by every native adapter; the main tab exposes the actual failure.
    _notify();
    return const {};
  }

  Future<void> finishLaunch(Map<String, Object?> launch) async {
    final identifier = launch['raSessionId'];
    if (!available || identifier is! String || identifier.isEmpty) return;
    try { await _native.invoke('finishSession', {'sessionId': identifier}); }
    on PlatformException { /* The native owner also closes its own session. */ }
    on MissingPluginException { /* No native session exists. */ }
  }

  void _onSessionChanged(Map<String, Object?> state) {
    if (_disposed || state['sessionId'] is! String) return;
    _session = RetroAchievementsSessionState(Map.unmodifiable(state));
    _notify();
  }

  @override
  void dispose() {
    _disposed = true;
    _native.dispose();
    super.dispose();
  }
}
