import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:retro_achievements_session/retro_achievements_session.dart';

import '../l10n/retro_achievements_status_locale.dart';
import '../models/retro_achievements_session.dart';
import '../repositories/retro_achievements_repository.dart';
import 'retroachievements_hash_service.dart';
import 'logger_service.dart';

/// Session error codes meaning RetroAchievements refused the stored in-game
/// token (rcheevos RC_INVALID_CREDENTIALS -34 / RC_EXPIRED_TOKEN -35 /
/// RC_ACCESS_DENIED -33, surfaced by the engines without any response text).
const raTokenRejectionCodes = {
  'RA_AUTHENTICATION_FAILED', 'login_failed_-33', 'login_failed_-34', 'login_failed_-35',
};

/// The main RA tab is the only writer. Every embedded launch asks this service
/// for an immutable policy; account changes never mutate a running game.
class RetroAchievementsSessionService extends ChangeNotifier {
  RetroAchievementsSessionService({RetroAchievementsNativeClient? native,
    Future<RetroAchievementsPreferences> Function()? readPreferences,
    Future<void> Function(RetroAchievementsPreferences)? writePreferences,
    Future<void> Function(String contentPath, int gameId)? gameIdentified})
    : _native = native ?? RetroAchievementsNativeClient(),
      _readPreferences = readPreferences ?? RetroAchievementsRepository.loadSessionPreferences,
      _writePreferences = writePreferences ?? RetroAchievementsRepository.saveSessionPreferences,
      _gameIdentified = gameIdentified ?? _rememberLaunchIdentity {
    _native.onSessionChanged = _onSessionChanged;
  }

  /// NEOSTATION_RA_IDENTIFICATION_V1: an emulator that loaded the set
  /// recognized the file itself; the library then shows its achievements
  /// whatever its format (Dolphin excepted: it reports no RetroAchievements id).
  static Future<void> _rememberLaunchIdentity(String contentPath, int gameId) =>
      RetroAchievementsHashService.identityStore.saveGameId(contentPath, gameId, source: 'launch');

  static final shared = RetroAchievementsSessionService();
  static final _log = LoggerService.instance;
  final RetroAchievementsNativeClient _native;
  final Future<RetroAchievementsPreferences> Function() _readPreferences;
  final Future<void> Function(RetroAchievementsPreferences) _writePreferences;
  final Future<void> Function(String contentPath, int gameId) _gameIdentified;
  /// Library file of each prepared session (sessionId -> path), until its
  /// game id is reported once.
  final Map<String, String> _launchContent = {};
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
  bool _tokenRejected = false;
  /// An engine reported that RetroAchievements refused the stored in-game
  /// token (password changed, token reset or account restriction). The account
  /// stays selected; the main tab asks for the password again.
  bool get tokenRejected => _authenticated && _tokenRejected;

  void _notify() { if (!_disposed) notifyListeners(); }

  /// Shared while running. A failed read is not cached: the next consumer
  /// (RA tab, toggle or game launch) retries instead of leaving RA off for the
  /// rest of the run after one transient Keychain/database failure.
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
    if (_initialized) {
      _log.i('RetroAchievements in-game session ready: account=${_authenticated ? 'present' : 'absent'} '
          'enabled=${_preferences.enabled} hardcore=${_preferences.hardcore}');
    } else {
      _initializing = null;
      _log.w('RetroAchievements in-game session unavailable: ${_errorCode ?? 'unknown'} (will retry)');
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

  /// Signs the in-game session in. Empty fields are an input error reported
  /// locally (`RA_INPUT_REQUIRED`) without any network request; the native
  /// plugin separates a refusal (`RA_AUTHENTICATION_FAILED`) from an
  /// unreachable server (`RA_NETWORK_UNAVAILABLE`/`RA_SERVER_ERROR`).
  Future<bool> login(String username, String password) {
    if (username.trim().isEmpty || password.isEmpty) return _reject('RA_INPUT_REQUIRED');
    return _mutate(() async {
      _log.i('RetroAchievements in-game sign-in requested');
      final Map<String, Object?> account;
      try {
        account = await _native.invoke('login', {'username': username.trim(), 'password': password});
      } on PlatformException catch (error) {
        _log.w('RetroAchievements in-game sign-in failed: ${error.code}');
        rethrow;
      }
      if (account['authenticated'] != true) throw PlatformException(code: 'RA_AUTHENTICATION_FAILED');
      _authenticated = true;
      _tokenRejected = false;
      _username = account['username'] as String? ?? username.trim();
      _generation++;
      final next = _preferences.copyWith(migrationVersion: 1);
      await _writePreferences(next);
      _preferences = next;
      _migrationCandidates = const [];
      await _native.invoke('completeLegacy');
      _initialized = true;
      _log.i('RetroAchievements in-game sign-in succeeded (enabled=${_preferences.enabled})');
    }, allowLegacyRecovery: true);
  }

  /// Queue-ordered local refusal: no initialization, no native/network call.
  Future<bool> _reject(String code) {
    final completed = Completer<bool>();
    _writes = _writes.then((_) {
      _errorCode = code;
      _notify();
      completed.complete(false);
    });
    return completed.future;
  }

  Future<bool> logout() => _mutate(() async {
    // Persist disabled first: even an interrupted sign-out cannot enable RA at
    // the next launch. A failed Keychain delete remains visible and retryable.
    final next = _preferences.copyWith(enabled: false, migrationVersion: 1);
    await _writePreferences(next);
    _preferences = next; _generation++;
    _initialized = true;
    await _native.invoke('logout');
    _authenticated = false; _username = ''; _tokenRejected = false;
    _migrationCandidates = const [];
    await _native.invoke('completeLegacy');
    _initialized = true;
    _log.i('RetroAchievements in-game session signed out');
  }, allowLegacyRecovery: true);

  /// [contentPath] is the library file being launched (never sent to the
  /// native side): when the engine reports the RetroAchievements game it
  /// loaded, the library remembers it for this file.
  Future<Map<String, Object?>> prepareLaunch({required String engine,
    required String system, String? core, required String language, bool systemMenu = false,
    String? contentPath}) async {
    await initialize();
    await _writes;
    final capability = RetroAchievementsCapabilities.forEngine(engine,
      system: system, core: core, systemMenu: systemMenu);
    if (!available) return const {};
    final enabled = _initialized && _preferences.enabled && _authenticated;
    try {
      final result = await _native.invoke('prepareSession', {
        'engine': engine, 'system': system, 'core': core ?? '', 'language': language,
        'capability': capability.name,
        'supported': capability == RetroAchievementsCapability.supported,
        'enabled': enabled,
        // The player's own choice, even when no usable account is available:
        // the engine then shows "sign-in required" instead of staying silent.
        // Players who switched RA off are never notified in game.
        'requested': _preferences.enabled,
        'hardcore': _preferences.hardcore, 'generation': _generation,
        // In-game status labels in the app language (no account data).
        'statusText': RetroAchievementsStatusLocale.forLanguage(language),
      });
      _log.i('RetroAchievements launch prepared: engine=$engine system=$system core=${core ?? '-'} '
          'capability=${capability.name} requested=${_preferences.enabled} '
          'account=${_authenticated ? 'present' : 'absent'} enabled=${result['enabled'] == true} '
          'hardcoreRequested=${result['hardcore'] == true} generation=$_generation');
      final sessionId = result['raSessionId'];
      if (sessionId is String && sessionId.isNotEmpty && contentPath != null && contentPath.isNotEmpty) {
        if (_launchContent.length > 16) _launchContent.remove(_launchContent.keys.first);
        _launchContent[sessionId] = contentPath;
      }
      return result;
    } on PlatformException catch (error) {
      _errorCode = error.code;
    } on MissingPluginException {
      _errorCode = 'RA_UNAVAILABLE';
    }
    _log.w('RetroAchievements launch preparation failed: $_errorCode (game continues without RA)');
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
    final next = RetroAchievementsSessionState(Map.unmodifiable(state));
    final previous = _session;
    _session = next;
    // Journal only transitions and public codes (the hub never forwards the
    // username/token): enough to follow login -> game -> tracking on device.
    if (previous == null || previous.id != next.id || previous.active != next.active ||
        previous.gameLoaded != next.gameLoaded || previous.errorCode != next.errorCode ||
        previous.hardcoreActive != next.hardcoreActive || previous.running != next.running) {
      _log.i('RetroAchievements session ${next.engine}: running=${next.running} '
          'enabled=${next.enabled} supported=${next.supported} gameLoaded=${next.gameLoaded} '
          'active=${next.active} hardcoreActive=${next.hardcoreActive} '
          'achievements=${next.unlockedCount}/${next.totalCount} '
          'error=${(next.errorCode?.isEmpty ?? true) ? '-' : next.errorCode}');
    }
    // A refusal is only meaningful for the account this launch used: a later
    // sign-in (new token) clears it, an unrelated engine error never sets it.
    if (next.enabled && raTokenRejectionCodes.contains(next.errorCode) &&
        next.generation == _generation && _authenticated) {
      _tokenRejected = true;
    }
    final contentPath = next.gameLoaded && next.gameId > 0 ? _launchContent.remove(next.id) : null;
    if (contentPath != null) {
      _log.i('RetroAchievements: ${next.engine} recognized the launched game (id ${next.gameId})');
      _gameIdentified(contentPath, next.gameId).catchError((Object error) {
        _log.w('RetroAchievements launch identity not saved: $error');
      });
    }
    _notify();
  }

  @override
  void dispose() {
    _disposed = true;
    _native.dispose();
    super.dispose();
  }
}
