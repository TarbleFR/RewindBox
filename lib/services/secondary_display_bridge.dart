import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/services/external_display_service.dart';
import 'package:neostation/services/logger_service.dart';

/// Main engine → TV menu engine (iOS, Build 447).
///
/// On Android the producers (systems grid, game lists, app tabs…) share
/// their display state with the bottom screen through
/// `SecondaryDisplayState.updateState`, which is a no-op elsewhere. On iOS
/// the same state goes to the external display's second engine instead:
/// a producer calls [forward] next to its `updateState` call with the same
/// `copyWith` arguments, and this bridge keeps the merged state (like the
/// shared state does) and pushes its JSON through
/// `ExternalDisplayService.pushMenuState`. The `Platform.isIOS` gate lives
/// here, never in the producers nor in the locked files.
///
/// The producers that change on every selection (systems grid, carousel,
/// games lists) forward only while a TV shows the menu
/// ([forwardsSelections], [forwardSelection]) and push their current
/// selection again when one starts showing it ([followSelections]).
class SecondaryDisplayBridge {
  SecondaryDisplayBridge._({ExternalDisplayService? service, bool? supported})
    : _serviceOverride = service,
      _supportedOverride = supported;

  static final SecondaryDisplayBridge instance = SecondaryDisplayBridge._();

  /// A separate bridge for tests (own service, platform gate forced).
  @visibleForTesting
  factory SecondaryDisplayBridge.forTesting({
    ExternalDisplayService? service,
    bool supported = true,
  }) => SecondaryDisplayBridge._(service: service, supported: supported);

  static final _log = LoggerService.instance;

  final ExternalDisplayService? _serviceOverride;
  final bool? _supportedOverride;

  SecondaryDisplayStateData? _latest;
  int _forwarded = 0;

  final List<SecondaryDisplaySelectionFollower> _followers =
      <SecondaryDisplaySelectionFollower>[];
  ExternalDisplayService? _followedService;
  bool _forwardingSelections = false;

  ExternalDisplayService get _service =>
      _serviceOverride ?? ExternalDisplayService.instance;

  /// iOS only: the producers' `Platform.isAndroid` gates use `dart:io` too.
  bool get isSupportedPlatform => _supportedOverride ?? Platform.isIOS;

  /// The last state forwarded to the TV menu (null before the first one).
  SecondaryDisplayStateData? get latest => _latest;

  /// States accepted by the native host.
  int get forwarded => _forwarded;

  /// Applies [merge] to the last forwarded state (the `WELCOME` default
  /// before the first one, like `SecondaryDisplayState.updateState`) and
  /// pushes the result to the TV menu engine. Returns false outside iOS,
  /// when [merge] throws, or when the native host did not accept it; never
  /// throws.
  Future<bool> forward(
    SecondaryDisplayStateData Function(SecondaryDisplayStateData current) merge,
  ) async {
    if (!isSupportedPlatform) return false;
    final current = _latest ?? SecondaryDisplayStateData(systemName: 'WELCOME');
    final SecondaryDisplayStateData next;
    try {
      next = merge(current);
    } catch (error) {
      _log.w('External display: menu state not built ($error)');
      return false;
    }
    _latest = next;
    final accepted = await _service.pushMenuState(next);
    if (accepted) _forwarded++;
    return accepted;
  }

  /// Pushes [state] as is (no merge).
  Future<bool> forwardState(SecondaryDisplayStateData state) =>
      forward((_) => state);

  /// [forward], only while [forwardsSelections]: the producers that change
  /// on every selection (systems grid and carousel, games lists) use it, so
  /// an iPhone without a TV pays no channel message per selection; they
  /// check [forwardsSelections] before their own file checks too. Returns
  /// false without a TV showing the menu.
  Future<bool> forwardSelection(
    SecondaryDisplayStateData Function(SecondaryDisplayStateData current) merge,
  ) {
    if (!forwardsSelections) return Future<bool>.value(false);
    return forward(merge);
  }

  /// Calls [reforward] with [owner] each time [forwardsSelections] becomes
  /// true (a TV starts showing the menu: connection, own window enabled,
  /// menu turned on), so the producer pushes its current selection then;
  /// nothing is pushed while no TV shows the menu. [owner] is held weakly:
  /// a producer whose state is gone is dropped, and a producer
  /// [SecondaryDisplaySelectionFollower.cancel]s in its `dispose`.
  /// [reforward] must not capture [owner] (a static function or a top-level
  /// one). Registering the same owner again returns its follower. Outside
  /// iOS nothing is followed.
  SecondaryDisplaySelectionFollower followSelections<T extends Object>(
    T owner,
    void Function(T owner) reforward,
  ) {
    for (final follower in _followers) {
      if (identical(follower._owner.target, owner) && follower.active) {
        return follower;
      }
    }
    final follower = SecondaryDisplaySelectionFollower._(
      this,
      owner,
      (Object target) => reforward(target as T),
    );
    if (!isSupportedPlatform) {
      follower._cancelled = true;
      return follower;
    }
    _followers.add(follower);
    _listen();
    return follower;
  }

  /// Producers following the TV menu right now (tests).
  @visibleForTesting
  int get followerCount =>
      _followers.where((follower) => follower.active).length;

  void _listen() {
    if (_followedService != null) return;
    final service = _service;
    _followedService = service;
    _forwardingSelections = forwardsSelections;
    service.addListener(_serviceChanged);
  }

  void _unlistenIfIdle() {
    _followers.removeWhere((follower) => !follower.active);
    if (_followers.isNotEmpty) return;
    _followedService?.removeListener(_serviceChanged);
    _followedService = null;
  }

  void _serviceChanged() {
    final now = forwardsSelections;
    final started = now && !_forwardingSelections;
    _forwardingSelections = now;
    if (!started) {
      _unlistenIfIdle();
      return;
    }
    // In registration order: the producer opened last (a games list over
    // the systems grid) pushes last, so its selection is the one shown.
    for (final follower in List<SecondaryDisplaySelectionFollower>.of(
      _followers,
    )) {
      try {
        follower._notify();
      } catch (error) {
        _log.w('External display: a selection was not forwarded ($error)');
      }
    }
    _unlistenIfIdle();
  }

  void _remove(SecondaryDisplaySelectionFollower follower) {
    _followers.remove(follower);
    _unlistenIfIdle();
  }

  /// True while a TV shows NeoStation's menu (iOS, connected, own window
  /// enabled, menu on the TV). Producers that change on every selection (the
  /// systems grid and carousel, the games lists) forward only then, so an
  /// iPhone without a TV pays no file checks or channel messages per
  /// selection.
  bool get forwardsSelections {
    if (!isSupportedPlatform) return false;
    final state = _service.state;
    return state != null &&
        state.supported &&
        state.connected &&
        state.enabled &&
        state.menuOnTV;
  }

  /// The TV menu state of a game selected in a games list, merged into
  /// [current] like the Android push of `_updateSecondaryDisplay`, images
  /// only: no video (no second decoder, no sound on the TV) and no music
  /// artwork bytes (they stay on the iPhone).
  static SecondaryDisplayStateData gameSelected(
    SecondaryDisplayStateData current, {
    required String systemName,
    required String? gameId,
    String? fanart,
    String? screenshot,
    String? wheel,
    int? backgroundColor,
    bool isGameLaunching = false,
    bool? isScraperLoggedIn,
  }) => current.copyWith(
    systemName: systemName,
    gameFanart: fanart,
    clearFanart: fanart == null,
    gameScreenshot: screenshot,
    clearScreenshot: screenshot == null,
    gameWheel: wheel,
    clearWheel: wheel == null,
    gameVideo: null,
    clearVideo: true,
    gameImageBytes: null,
    clearImageBytes: true,
    isGameSelected: true,
    backgroundColor: backgroundColor,
    isGameLaunching: isGameLaunching,
    gameId: gameId,
    clearGameId: gameId == null,
    isScraperLoggedIn: isScraperLoggedIn,
    showAchievementPanel: false,
  );

  /// The TV menu state of a console highlighted by the systems grid or the
  /// carousel, merged into [current] with the arguments of their Android
  /// push: the console's logo and background (or its shader colours), no
  /// game.
  static SecondaryDisplayStateData systemSelected(
    SecondaryDisplayStateData current, {
    required String systemName,
    required int backgroundColor,
    required String? systemLogo,
    required bool isLogoAsset,
    required String? systemBackground,
    int? shaderColor1,
    int? shaderColor2,
    required bool isOled,
  }) => current.copyWith(
    systemName: systemName,
    backgroundColor: backgroundColor,
    systemLogo: systemLogo,
    isLogoAsset: isLogoAsset,
    systemBackground: systemBackground,
    clearSystemBackground: systemBackground == null,
    isBackgroundAsset: false,
    useShader: systemBackground == null,
    shaderColor1: shaderColor1,
    shaderColor2: shaderColor2,
    isGameSelected: false,
    clearFanart: true,
    clearScreenshot: true,
    clearWheel: true,
    clearVideo: true,
    clearImageBytes: true,
    clearGameId: true,
    useFluidShader: false,
    isOled: isOled,
  );

  /// Whether [latest] already shows that selection (the games list skips the
  /// push then, like the Android dedup of `_updateSecondaryDisplay`).
  static bool showsSelection(
    SecondaryDisplayStateData? latest, {
    required String systemName,
    required String? gameId,
    String? fanart,
    String? screenshot,
    String? wheel,
    bool isGameLaunching = false,
  }) =>
      latest != null &&
      latest.isGameSelected &&
      latest.systemName == systemName &&
      latest.gameId == gameId &&
      latest.gameFanart == fanart &&
      latest.gameScreenshot == screenshot &&
      latest.gameWheel == wheel &&
      latest.gameVideo == null &&
      latest.isGameLaunching == isGameLaunching;
}

/// A producer that re-forwards its selection when a TV starts showing the
/// menu ([SecondaryDisplayBridge.followSelections]).
class SecondaryDisplaySelectionFollower {
  SecondaryDisplaySelectionFollower._(
    this._bridge,
    Object owner,
    this._reforward,
  ) : _owner = WeakReference<Object>(owner);

  final SecondaryDisplayBridge _bridge;
  final WeakReference<Object> _owner;
  final void Function(Object owner) _reforward;
  bool _cancelled = false;

  /// Still followed: not cancelled and its owner still alive.
  bool get active => !_cancelled && _owner.target != null;

  /// Stops following (the producer's `dispose`). Idempotent.
  void cancel() {
    if (_cancelled) return;
    _cancelled = true;
    _bridge._remove(this);
  }

  void _notify() {
    final owner = _owner.target;
    if (_cancelled || owner == null) return;
    _reforward(owner);
  }
}
