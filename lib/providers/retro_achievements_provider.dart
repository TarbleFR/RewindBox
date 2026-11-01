import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:neostation/services/logger_service.dart';
import '../models/retro_achievements_user.dart';
import '../models/retro_achievements_summary.dart';
import '../services/retro_achievements_service.dart';
import '../l10n/app_locale.dart';
import '../services/retro_achievements_session_service.dart';
import 'retro_achievements_dashboard_source.dart';
import '../models/retro_achievements_dashboard_models.dart';
import '../models/retro_achievements_game_info.dart';
import '../models/retro_achievements_gotw.dart';
import '../models/retro_achievements_user_awards.dart';
import 'retro_achievements_credentials.dart';

/// Provider responsible for managing the integration with RetroAchievements.org.
///
/// Handles user authentication, profile synchronization, achievement progress
/// tracking, and ROM identification via console-specific hashing algorithms.
class RetroAchievementsProvider extends ChangeNotifier {
  RetroAchievementsProvider({
    RetroAchievementsSessionService? sessionService,
    RetroAchievementsDashboardSource? source,
  }) : _sessionService = sessionService,
       _source = source ?? const RetroAchievementsDashboardSource() {
    _sessionService?.addListener(_onCentralAccountChanged);
  }

  final RetroAchievementsSessionService? _sessionService;
  final RetroAchievementsDashboardSource _source;
  RetroAchievementsSessionService? get sessionService => _sessionService;
  Future<void>? _initializing;
  Future<void>? _restoringCentralAccount;
  Future<void> _credentialWrites = Future<void>.value();
  int _accountGeneration = 0;
  int _restoreGeneration = 0;
  bool _disposed = false;
  bool _observeCentralAccount = false;
  String? _centralIdentity;
  String? _accountErrorKey;

  /// Localized by the UI; Web API diagnostics remain separate.
  String? get accountErrorKey => _accountErrorKey;

  bool _isCurrent(int generation) =>
      !_disposed && generation == _accountGeneration;
  bool _isRestoring(int generation) =>
      !_disposed && generation == _restoreGeneration;
  void _notify() { if (!_disposed) notifyListeners(); }

  static String _identity(String username) => username.trim().toLowerCase();

  String _centralAccountIdentity() {
    final session = _sessionService;
    if (session == null || !session.available || !session.initialized ||
        !session.authenticated) {
      return '';
    }
    return _identity(session.username);
  }

  /// The Web dashboard (Web API key) and the in-game session (password-derived
  /// Connect token kept in the Keychain) are different credentials. Build 608
  /// refused the dashboard whenever the in-game session was signed out, which
  /// rejected valid usernames/keys locally without contacting RetroAchievements.
  /// Only a confirmed in-game account with another identity is a conflict:
  /// one screen never mixes two accounts.
  bool _conflictsWithCentralAccount(String username) {
    final central = _centralAccountIdentity();
    return central.isNotEmpty && central != _identity(username);
  }

  void _onCentralAccountChanged() {
    final session = _sessionService;
    if (_disposed || !_observeCentralAccount || session == null ||
        !session.available || !session.initialized) {
      return;
    }
    final identity = _centralAccountIdentity();
    if (_centralIdentity == identity) return;
    _centralIdentity = identity;
    // A closed dialog, an unmounted tab and background account migration all
    // use this listener. Never depend on a widget callback for identity.
    final dashboard = (_isConnected || _isLoading) ? _identity(_username) : '';
    if (dashboard.isNotEmpty && identity.isNotEmpty && dashboard != identity) {
      // Another account signed in for games: drop the old dashboard and every
      // pending response. The saved pair is kept; restore refuses it.
      _log.i('RetroAchievements dashboard cleared: in-game account changed');
      final restoration = ++_restoreGeneration;
      _resetMemory();
      _notify();
      _restoringCentralAccount = _restoreSavedAccount(restoration);
      return;
    }
    if (dashboard.isEmpty) {
      // A sign-in or sign-out may have resolved an earlier conflict.
      _restoringCentralAccount = _restoreSavedAccount(++_restoreGeneration);
    }
    // Same account, or an in-game sign-out: the Web dashboard is unaffected.
  }

  Future<void> _queueCredentialWrite(Future<void> Function() operation) {
    _credentialWrites = _credentialWrites.then((_) => operation());
    return _credentialWrites;
  }

  static const String _dashboardApiKeyError =
      'A RetroAchievements web API key is required for this dashboard data.';

  static const String _rateLimitError =
      'RetroAchievements is rate-limiting requests. Please wait a moment and try again.';

  /// Basic profile information for the authenticated user.
  RetroAchievementsUser? _user;

  /// Whether a data retrieval task is currently in progress.
  bool _isLoading = false;

  /// Whether a successful connection has been established with the API.
  bool _isConnected = false;

  /// Last error message encountered during API interactions.
  String? _error;

  /// Current authenticated username.
  String _username = '';

  /// Current RetroAchievements API key used for requests.
  String _apiKey = '';

  static final _log = LoggerService.instance;

  /// Full user summary including recent activity and badges.
  RetroAchievementsUserSummary? _userSummary;

  /// Memory cache for detailed game metadata and user progress, keyed by Game ID.
  final Map<int, GameInfoAndUserProgress> _gameInfoCache = {};

  /// Current "Game of the Week" metadata.
  RetroAchievementsGOTW? _gotw;

  /// Whether the GOTW metadata has been loaded.
  bool _gotwLoaded = false;

  /// List of special awards and site badges earned by the user.
  RetroAchievementsUserAwards? _userAwards;

  /// Whether the user awards have been loaded.
  bool _userAwardsLoaded = false;
  bool _userAwardsLoading = false;
  String? _userAwardsError;

  /// Cached filtered/sorted award lists so the dashboard build doesn't redo
  /// the work on every frame.
  List<UserAward> _cachedRecentMasteries = [];
  List<UserAward> _cachedRecentCompletions = [];

  List<RetroAchievementRecentUnlockItem> _recentUnlocks = [];
  bool _recentUnlocksLoaded = false;
  bool _recentUnlocksLoading = false;
  String? _recentUnlocksError;

  List<RetroAchievementRecentlyPlayedGameItem> _recentlyPlayedGames = [];
  bool _recentlyPlayedLoaded = false;
  bool _recentlyPlayedLoading = false;
  String? _recentlyPlayedError;

  RetroAchievementCompletionProgressSummary? _completionProgress;
  bool _completionProgressLoaded = false;
  bool _completionProgressLoading = false;
  String? _completionProgressError;

  bool _gotwLoading = false;
  String? _gotwError;
  OwnedWeekGameResolution? _ownedWeekGame;

  // Getters
  RetroAchievementsUser? get user => _user;
  bool get isLoading => _isLoading;
  bool get isConnected => _isConnected;
  String? get error => _error;
  String get username => _username;
  String get apiKey => _apiKey;

  RetroAchievementsUserSummary? get userSummary => _userSummary;

  RetroAchievementsGOTW? get gotw => _gotw;

  /// Whether the current user has already earned the Achievement of the Week.
  bool get gotwEarned {
    if (_gotw == null || _user == null) return false;
    return _gotw!.unlocks.any((u) => u.user == _user!.user);
  }

  /// Recent mastery awards (hardcore) visible to the user.
  List<UserAward> get recentMasteries => _cachedRecentMasteries;

  /// Recent completion awards (casual) visible to the user.
  List<UserAward> get recentCompletions => _cachedRecentCompletions;

  RetroAchievementsUserAwards? get userAwards => _userAwards;
  bool get userAwardsLoaded => _userAwardsLoaded;
  bool get userAwardsLoading => _userAwardsLoading;
  String? get userAwardsError => _userAwardsError;
  List<RetroAchievementRecentUnlockItem> get recentUnlocks => _recentUnlocks;
  bool get recentUnlocksLoading => _recentUnlocksLoading;
  String? get recentUnlocksError => _recentUnlocksError;
  List<RetroAchievementRecentlyPlayedGameItem> get recentlyPlayedGames =>
      _recentlyPlayedGames;
  bool get recentlyPlayedLoading => _recentlyPlayedLoading;
  String? get recentlyPlayedError => _recentlyPlayedError;
  RetroAchievementCompletionProgressSummary? get completionProgress =>
      _completionProgress;
  bool get completionProgressLoading => _completionProgressLoading;
  bool get gotwLoading => _gotwLoading;
  String? get gotwError => _gotwError;
  OwnedWeekGameResolution? get ownedWeekGame => _ownedWeekGame;
  bool get hasResolvedApiKey =>
      RetroAchievementsService.resolveApiKey(_apiKey).trim().isNotEmpty;

  bool get dashboardLoaded =>
      _recentUnlocksLoaded &&
      _recentlyPlayedLoaded &&
      _userAwardsLoaded &&
      _completionProgressLoaded &&
      _gotwLoaded;

  /// Connects the Web dashboard with the player's Web API key. It works with
  /// or without the in-game session and never signs in an emulator; only a
  /// confirmed in-game account with another name is refused. The native
  /// password/token never enters this provider. Desktop platforms without the
  /// native session plugin keep their existing Web-only login.
  Future<bool> connect(String username, {String? apiKey}) {
    ++_restoreGeneration;
    return _connect(username, apiKey: apiKey);
  }

  Future<bool> _connect(String username, {String? apiKey}) async {
    if (_disposed) return false;
    final requestedUsername = username.trim();
    final resolvedApiKey = RetroAchievementsService.resolveApiKey(apiKey);
    if (requestedUsername.isEmpty || resolvedApiKey.isEmpty) {
      // Input error: nothing is sent to RetroAchievements.
      _accountErrorKey = AppLocale.pleaseCompleteAllFields;
      _error = requestedUsername.isEmpty
          ? 'Please enter a username'
          : 'Please enter your RetroAchievements web API key';
      _notify();
      return false;
    }
    if (_conflictsWithCentralAccount(requestedUsername)) {
      _accountErrorKey = AppLocale.raSessionDifferentAccount;
      _log.w('RetroAchievements dashboard sign-in refused: different in-game account');
      _notify();
      return false;
    }
    _accountErrorKey = null;

    // Account and key changes invalidate every outstanding dashboard request,
    // including game caches and errors/finally blocks from the previous user.
    _resetMemory();
    final generation = _accountGeneration;
    _username = requestedUsername;
    _apiKey = resolvedApiKey;
    _setLoading(true);

    try {
      final userProfile = await _source.getUserProfile(
        requestedUsername,
        resolvedApiKey,
      );
      if (!_isCurrent(generation)) return false;

      // RetroAchievements resolves the requested name (or a previous name of
      // the same account) to the profile it returns; that profile is the user.
      if (userProfile != null && userProfile.user.trim().isNotEmpty) {
        await _queueCredentialWrite(() async {
          if (!_isCurrent(generation)) return;
          // Keep each pair ordered with disconnect/new-account writes. Once
          // started, finish the pair so a key is not bound to another name.
          await _saveRAUserToConfig(requestedUsername);
          await _saveRAApiKeyToConfig(resolvedApiKey);
        });
        if (!_isCurrent(generation)) return false;
        _accountErrorKey = null;
        _user = userProfile;
        _isConnected = true;
        _log.i('RetroAchievements dashboard signed in');
        unawaited(loadUserSummary());
        _notify();
        return true;
      }
      _accountErrorKey = AppLocale.raWebUserNotFound;
      _error = 'User not found on RetroAchievements';
      _isConnected = false;
      _log.w('RetroAchievements dashboard sign-in: user not found');
      _notify();
      return false;
    } on RetroAchievementsWebException catch (e) {
      if (!_isCurrent(generation)) return false;
      _accountErrorKey = switch (e.failure) {
        RetroAchievementsWebFailure.rejected => AppLocale.raWebKeyRejected,
        RetroAchievementsWebFailure.notFound => AppLocale.raWebUserNotFound,
        RetroAchievementsWebFailure.network ||
        RetroAchievementsWebFailure.rateLimited => AppLocale.raSessionNetworkError,
        RetroAchievementsWebFailure.server => AppLocale.raSessionServerError,
      };
      _error = 'RetroAchievements sign-in failed: ${e.failure.name}';
      _isConnected = false;
      _log.w('RetroAchievements dashboard sign-in failed: $e');
      _notify();
      return false;
    } catch (e) {
      if (!_isCurrent(generation)) return false;
      _accountErrorKey = AppLocale.raSessionNetworkError;
      _error = 'Error connecting to RetroAchievements: $e';
      _isConnected = false;
      _log.e('$_error');
      _notify();
      return false;
    } finally {
      if (_isCurrent(generation)) _setLoading(false);
    }
  }

  /// Refreshes the full user summary, including recent achievements and active game list.
  Future<bool> loadUserSummary() async {
    if (_disposed) return false;
    final generation = _accountGeneration;
    if (!_isConnected || _username.isEmpty) {
      _error = 'User not connected';
      _notify();
      return false;
    }

    if (!hasResolvedApiKey) {
      _error = _dashboardApiKeyError;
      _notify();
      return false;
    }

    _setLoading(true);
    _error = null;

    try {
      final summary = await _source.getUserSummary(_username, _apiKey);
      if (!_isCurrent(generation)) return false;

      if (summary != null) {
        _userSummary = summary;
        _notify();
        return true;
      } else {
        _error = 'User summary could not be loaded';
        _notify();
        return false;
      }
    } catch (e) {
      if (!_isCurrent(generation)) return false;
      _error = _describeApiError(e, 'Error loading user summary');
      _log.e('$_error');
      _notify();
      return false;
    } finally {
      if (_isCurrent(generation)) {
        _setLoading(false);
      }
    }
  }

  /// Fetches metadata for the current site-wide "Game of the Week".
  Future<bool> fetchGOTW() async {
    if (_disposed) return false;
    final generation = _accountGeneration;
    if (!_isConnected) {
      _gotwLoaded = false;
      return false;
    }

    if (!hasResolvedApiKey) {
      _gotw = null;
      _gotwLoaded = false;
      _gotwError = _dashboardApiKeyError;
      _notify();
      return false;
    }

    _gotwLoading = true;
    _gotwError = null;
    _notify();

    try {
      final gotw = await _source.getAchievementOfTheWeek(_apiKey);
      if (!_isCurrent(generation)) return false;

      if (gotw != null) {
        final ownedGame = await _resolveOwnedWeekGame(gotw);
        if (!_isCurrent(generation)) return false;
        _gotw = gotw;
        _gotwLoaded = true;
        _ownedWeekGame = ownedGame;
        _notify();
        return true;
      } else {
        _log.w('fetchAOTW returned null');
        _gotw = null;
        _gotwLoaded = false;
        _gotwError = 'Could not load Achievement of the Week';
        _notify();
        return false;
      }
    } catch (e) {
      if (!_isCurrent(generation)) return false;
      _gotwError = _describeApiError(
        e,
        'Error loading Achievement of the Week',
      );
      _gotwLoaded = false;
      _gotw = null;
      _ownedWeekGame = null;
      _log.e(_gotwError ?? 'Unknown GOTW error');
      _notify();
      return false;
    } finally {
      if (_isCurrent(generation)) {
        _gotwLoading = false;
        _notify();
      }
    }
  }

  /// Fetches the user's earned badges and awards from the API.
  Future<bool> fetchUserAwards() async {
    if (_disposed) return false;
    final generation = _accountGeneration;
    if (!_isConnected || _username.isEmpty) return false;

    if (!hasResolvedApiKey) {
      _userAwards = null;
      _userAwardsLoaded = false;
      _userAwardsError = _dashboardApiKeyError;
      _notify();
      return false;
    }

    _userAwardsLoading = true;
    _userAwardsError = null;
    _notify();

    try {
      final awardsData = await _source.getUserAwards(_username, _apiKey);
      if (!_isCurrent(generation)) return false;
      if (awardsData != null) {
        // Parse the (potentially large) awards payload off the main thread so
        // the dashboard doesn't jank while building.
        final awards = await compute(
          _parseRetroAchievementsUserAwards,
          awardsData,
        );
        if (!_isCurrent(generation)) return false;
        _userAwards = awards;
        _updateRecentAwardsCache();
        _userAwardsLoaded = true;
        return true;
      }
      _userAwardsLoaded = false;
      _userAwardsError = 'User awards could not be loaded';
      return false;
    } catch (e) {
      if (!_isCurrent(generation)) return false;
      _userAwardsError = _describeApiError(e, 'Error loading user awards');
      _userAwardsLoaded = false;
      _userAwards = null;
      _log.e(_userAwardsError ?? 'Unknown user awards error');
      return false;
    } finally {
      if (_isCurrent(generation)) {
        _userAwardsLoading = false;
        _notify();
      }
    }
  }

  /// Retrieves detailed information for a game and the current user's achievement progress.
  ///
  /// Leverages an internal cache to avoid redundant network calls.
  /// The [md5Hash] parameter is used for precise identification of ROM versions.
  Future<GameInfoAndUserProgress?> getGameInfoAndUserProgress(
    int gameId, {
    bool forceRefresh = false,
    String? md5Hash,
  }) async {
    if (_disposed) return null;
    final generation = _accountGeneration;
    if (!_isConnected || _username.isEmpty) {
      _error = 'User not connected';
      return null;
    }

    if (forceRefresh && _gameInfoCache.containsKey(gameId)) {
      _gameInfoCache.remove(gameId);
    }

    if (!forceRefresh && _gameInfoCache.containsKey(gameId)) {
      return _gameInfoCache[gameId];
    }

    _error = null;

    try {
      final gameInfo =
          await _source.getGameInfoAndUserProgress(
            gameId,
            _username,
            _apiKey,
            md5Hash: md5Hash,
          );
      if (!_isCurrent(generation)) return null;

      if (gameInfo != null) {
        _gameInfoCache[gameId] = gameInfo;
        return gameInfo;
      } else {
        _error = 'Game information could not be loaded';
        return null;
      }
    } catch (e) {
      if (!_isCurrent(generation)) return null;
      _error = 'Error loading game information: $e';
      _log.e('$_error');
      return null;
    }
  }

  /// Observes the central account for the provider lifetime, not a dialog's
  /// lifetime. Restoring the Web dashboard never authenticates an emulator.
  Future<void> initialize() => _initializing ??= _initialize();

  Future<void> _initialize() async {
    final session = _sessionService;
    if (session?.available == true) {
      await session!.initialize();
      if (_disposed) return;
      // Record the current in-game identity first: the listener reacts only to
      // later sign-in/sign-out changes. A failed Keychain read never blocks the
      // Web dashboard (Build 608 left it signed out after every restart).
      _centralIdentity = session.initialized ? _centralAccountIdentity() : null;
      _observeCentralAccount = true;
    }
    final restoration = ++_restoreGeneration;
    _restoringCentralAccount = _restoreSavedAccount(restoration);
    await _restoringCentralAccount;
  }

  Future<void> _restoreSavedAccount(int restoration) async {
    try {
      // Preserve the existing cold-boot retry for temporarily unreadable Web
      // credentials. A disconnect/account change cancels the entire retry loop.
      const maxAttempts = 5;
      for (var attempt = 1; attempt <= maxAttempts; attempt++) {
        if (!_isRestoring(restoration)) return;
        final loggedIn = await _tryAutoLogin(restoration);
        if (!_isRestoring(restoration)) return;
        if (loggedIn) {
          await fetchGOTW();
          return;
        }
        // RetroAchievements explicitly refused the saved pair: retrying the
        // same key cannot succeed. The pair stays saved for the player to fix.
        if (_accountErrorKey == AppLocale.raWebKeyRejected ||
            _accountErrorKey == AppLocale.raWebUserNotFound) {
          return;
        }
        final user = await _readRAUserFromConfig();
        final apiKey = await _readRAApiKeyFromConfig();
        if (!_isRestoring(restoration)) return;
        if (user.hasValue && _conflictsWithCentralAccount(user.value!)) return;
        final worthRetrying =
            !user.ok || !apiKey.ok || (user.hasValue && apiKey.hasValue);
        if (!worthRetrying || attempt == maxAttempts) return;
        _log.i(
          'RetroAchievements auto-login attempt $attempt failed; retrying after startup delay',
        );
        await Future<void>.delayed(const Duration(seconds: 4));
      }
    } catch (e) {
      if (_isRestoring(restoration)) _log.e('Error initializing RA: $e');
    }
  }

  Future<bool> tryAutoLogin() => _tryAutoLogin(_restoreGeneration);

  Future<bool> _tryAutoLogin(int restoration) async {
    try {
      await _credentialWrites;
      final user = await _readRAUserFromConfig();
      final apiKey = await _readRAApiKeyFromConfig();
      if (!_isRestoring(restoration)) return false;
      if (user.hasValue && _conflictsWithCentralAccount(user.value!)) {
        _log.i('RetroAchievements saved dashboard account not restored: different in-game account');
        return false;
      }
      switch (resolveRaAutoLoginAction(user: user, apiKey: apiKey)) {
        case RaAutoLoginAction.attemptLogin:
          return await _connect(user.value!, apiKey: apiKey.value);
        case RaAutoLoginAction.clearOrphanedKey:
          // Native migration owns legacy inputs. Desktop retains the previous
          // orphan-key cleanup, but never after a concurrent manual connection.
          if (_sessionService?.available != true) {
            await _queueCredentialWrite(() async {
              if (_isRestoring(restoration)) await _clearRAApiKeyFromConfig();
            });
          }
          return false;
        case RaAutoLoginAction.skip:
          if (!user.ok || !apiKey.ok) {
            _log.w('RetroAchievements credential storage unreadable; credentials preserved');
          }
          return false;
      }
    } catch (e) {
      if (_isRestoring(restoration)) _log.e('Error loading RA credentials: $e');
      return false;
    }
  }

  /// Clears the current user session and memory state.
  ///
  /// If [clearSavedUser] is true, the credentials are removed from persistent storage.
  void disconnect({bool clearSavedUser = true}) {
    if (_disposed) return;
    ++_restoreGeneration;
    _resetMemory();
    if (clearSavedUser) {
      unawaited(_queueCredentialWrite(() async {
        await _clearRAUserFromConfig();
        await _clearRAApiKeyFromConfig();
      }));
    }
    _notify();
  }

  void _resetMemory() {
    ++_accountGeneration;
    _accountErrorKey = null;
    _isLoading = false;
    _gameInfoCache.clear();
    _user = null;
    _isConnected = false;
    _username = '';
    _apiKey = '';
    _error = null;
    _userSummary = null;
    _gotw = null;
    _gotwLoaded = false;
    _gotwLoading = false;
    _gotwError = null;
    _ownedWeekGame = null;
    _userAwards = null;
    _userAwardsLoaded = false;
    _userAwardsLoading = false;
    _userAwardsError = null;
    _cachedRecentMasteries = [];
    _cachedRecentCompletions = [];
    _recentUnlocks = [];
    _recentUnlocksLoaded = false;
    _recentUnlocksLoading = false;
    _recentUnlocksError = null;
    _recentlyPlayedGames = [];
    _recentlyPlayedLoaded = false;
    _recentlyPlayedLoading = false;
    _recentlyPlayedError = null;
    _completionProgress = null;
    _completionProgressLoaded = false;
    _completionProgressLoading = false;
    _completionProgressError = null;
  }

  @override
  void dispose() {
    _disposed = true;
    ++_accountGeneration;
    ++_restoreGeneration;
    _sessionService?.removeListener(_onCentralAccountChanged);
    super.dispose();
  }

  void _setLoading(bool loading) {
    _isLoading = loading;
    _notify();
  }

  /// Persists the RetroAchievements username to the local user configuration table.
  Future<void> _saveRAUserToConfig(String username) async {
    try {
      await _source.saveUsername(username);
    } catch (e) {
      _log.e('Error saving RA user: $e');
    }
  }

  /// Persists the RetroAchievements API key to secure storage.
  Future<void> _saveRAApiKeyToConfig(String apiKey) async {
    try {
      await _source.saveApiKey(apiKey);
    } catch (e) {
      _log.e('Error saving RA API key: $e');
    }
  }

  /// Retrieves the persisted RetroAchievements username from the configuration
  /// table, reporting whether the read itself succeeded.
  Future<CredentialRead> _readRAUserFromConfig() async {
    try {
      return CredentialRead.ok(await _source.readUsername());
    } catch (e) {
      _log.e('Error loading RA user from DB: $e');
      return const CredentialRead.failed();
    }
  }

  /// Retrieves the persisted RetroAchievements API key from secure storage,
  /// reporting whether the read itself succeeded.
  Future<CredentialRead> _readRAApiKeyFromConfig() async {
    try {
      return CredentialRead.ok(await _source.readApiKey());
    } catch (e) {
      _log.e('Error loading RA API key from secure storage: $e');
      return const CredentialRead.failed();
    }
  }

  /// Removes the RetroAchievements username from persistent storage.
  Future<void> _clearRAUserFromConfig() async {
    try {
      await _source.clearUsername();
    } catch (e) {
      _log.e('Error clearing RA user: $e');
    }
  }

  /// Removes the RetroAchievements API key from secure storage.
  Future<void> _clearRAApiKeyFromConfig() async {
    try {
      await _source.clearApiKey();
    } catch (e) {
      _log.e('Error clearing RA API key: $e');
    }
  }

  Future<bool> fetchCompletionProgress() async {
    if (_disposed) return false;
    final generation = _accountGeneration;
    if (!_isConnected || _username.isEmpty) return false;

    if (!hasResolvedApiKey) {
      _completionProgress = null;
      _completionProgressLoaded = false;
      _completionProgressError = _dashboardApiKeyError;
      _notify();
      return false;
    }

    _completionProgressLoading = true;
    _completionProgressError = null;
    _notify();

    try {
      final progress = await _source.getUserCompletionProgress(_username, _apiKey);
      if (!_isCurrent(generation)) return false;
      _completionProgress = progress;
      _completionProgressLoaded = true;
      _notify();
      return true;
    } catch (e) {
      if (!_isCurrent(generation)) return false;
      _completionProgressError = _describeApiError(
        e,
        'Error loading completion progress',
      );
      _completionProgressLoaded = false;
      _completionProgress = null;
      _log.e(_completionProgressError ?? 'Unknown completion progress error');
      return false;
    } finally {
      if (_isCurrent(generation)) {
        _completionProgressLoading = false;
        _notify();
      }
    }
  }

  Future<bool> fetchRecentlyPlayedGames() async {
    if (_disposed) return false;
    final generation = _accountGeneration;
    if (!_isConnected || _username.isEmpty) return false;

    if (!hasResolvedApiKey) {
      _recentlyPlayedGames = [];
      _recentlyPlayedLoaded = false;
      _recentlyPlayedError = _dashboardApiKeyError;
      _notify();
      return false;
    }

    _recentlyPlayedLoading = true;
    _recentlyPlayedError = null;
    _notify();

    try {
      final list = await _source.getUserRecentlyPlayedGames(_username, _apiKey);
      if (!_isCurrent(generation)) return false;
      _recentlyPlayedGames = list;
      _recentlyPlayedLoaded = true;
      _notify();
      return true;
    } catch (e) {
      if (!_isCurrent(generation)) return false;
      _recentlyPlayedError = _describeApiError(
        e,
        'Error loading recently played games',
      );
      _recentlyPlayedLoaded = false;
      _recentlyPlayedGames = [];
      _log.e(_recentlyPlayedError ?? 'Unknown recently played error');
      return false;
    } finally {
      if (_isCurrent(generation)) {
        _recentlyPlayedLoading = false;
        _notify();
      }
    }
  }

  Future<bool> fetchRecentUnlocks() async {
    if (_disposed) return false;
    final generation = _accountGeneration;
    if (!_isConnected || _username.isEmpty) return false;

    if (!hasResolvedApiKey) {
      _recentUnlocks = [];
      _recentUnlocksLoaded = false;
      _recentUnlocksError = _dashboardApiKeyError;
      _notify();
      return false;
    }

    _recentUnlocksLoading = true;
    _recentUnlocksError = null;
    _notify();

    try {
      final list = await _source.getUserRecentAchievements(_username, _apiKey);
      if (!_isCurrent(generation)) return false;
      _recentUnlocks = list;
      _recentUnlocksLoaded = true;
      _notify();
      return true;
    } catch (e) {
      if (!_isCurrent(generation)) return false;
      _recentUnlocksError = _describeApiError(
        e,
        'Error loading recent unlocks',
      );
      _recentUnlocksLoaded = false;
      _recentUnlocks = [];
      _log.e(_recentUnlocksError ?? 'Unknown recent unlocks error');
      return false;
    } finally {
      if (_isCurrent(generation)) {
        _recentUnlocksLoading = false;
        _notify();
      }
    }
  }

  Future<OwnedWeekGameResolution?> _resolveOwnedWeekGame(
    RetroAchievementsGOTW gotw,
  ) async {
    final raGameId = gotw.game.id;
    if (raGameId <= 0) return null;
    try {
      return await _source.findBestLocalGameByRaGameId(raGameId);
    } catch (e) {
      _log.e('Error resolving local GOTW ownership: $e');
      return null;
    }
  }

  bool _isUnauthorizedError(Object error) => error.toString().contains('(401)');

  /// The RetroAchievements API (behind Cloudflare) returns HTTP 429 when a
  /// user exceeds the request rate. The services surface it as a `(429)` in
  /// the thrown message, so match on that.
  bool _isRateLimitedError(Object error) => error.toString().contains('(429)');

  /// Maps a caught API error to a user-facing message: a missing/invalid key
  /// and rate-limiting each get a dedicated, actionable string; everything
  /// else falls back to [fallback] with the raw error appended.
  String _describeApiError(Object error, String fallback) {
    if (_isUnauthorizedError(error)) return _dashboardApiKeyError;
    if (_isRateLimitedError(error)) return _rateLimitError;
    return '$fallback: $error';
  }

  /// Recomputes the filtered/sorted recent masteries/completions caches.
  /// Should be called whenever [_userAwards] changes.
  void _updateRecentAwardsCache() {
    _cachedRecentMasteries = _recentAwardsForMode(hardcore: true);
    _cachedRecentCompletions = _recentAwardsForMode(hardcore: false);
  }

  List<UserAward> _recentAwardsForMode({required bool hardcore}) {
    final awards = _userAwards?.visibleUserAwards ?? const <UserAward>[];
    final matchingMode = hardcore ? 1 : 0;

    final filtered = awards.where((award) {
      if (award.awardType.toLowerCase() != 'mastery/completion') {
        return false;
      }
      return award.awardDataExtra == matchingMode;
    }).toList();

    filtered.sort((a, b) => b.awardedAt.compareTo(a.awardedAt));
    return filtered;
  }
}

/// Top-level helper for [compute] so the large RA awards payload can be parsed
/// off the main thread.
RetroAchievementsUserAwards _parseRetroAchievementsUserAwards(
  Map<String, dynamic> json,
) {
  return RetroAchievementsUserAwards.fromJson(json);
}
