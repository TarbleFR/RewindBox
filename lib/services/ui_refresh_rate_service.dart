import 'dart:async';
import 'dart:ui' show FramePhase, FrameTiming;

import 'package:flutter/foundation.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/utils/frame_cadence_estimator.dart';
import 'package:ui_refresh_rate/ui_refresh_rate.dart';

export 'package:ui_refresh_rate/ui_refresh_rate.dart' show UiRefreshRateState;
export 'package:neostation/utils/frame_cadence_estimator.dart'
    show FrameCadenceSummary;

/// Why the last user action on the option did not apply.
enum UiRefreshRateError { saveFailed }

/// Settings › General › "120 Hz interface" (Build 440, iOS).
///
/// - The preference lives in NSUserDefaults on the native side
///   (`NeoStation.UI.HighRefreshRate.Enabled`, read once per process before
///   the first Flutter view): a change applies at the next launch.
/// - The screen capability and the engine hook come from the native plugin;
///   the option is unavailable on 60 Hz screens or without the hook.
/// - The effective rate is measured passively from `FrameTiming` (no ticker,
///   no scheduled frame), including the first frames after a game, and by a
///   bounded measurement the settings row drives on request. A rate is only
///   ever shown when it was measured.
class UiRefreshRateService extends ChangeNotifier with WidgetsBindingObserver {
  UiRefreshRateService._({
    UiRefreshRateChannel channel = const UiRefreshRateChannel(),
    FrontendMediaGate? gate,
    DateTime Function()? clock,
    Duration reportWait = const Duration(milliseconds: 1200),
  }) : _channel = channel,
       _gateOverride = gate,
       _clock = clock ?? DateTime.now,
       _reportWait = reportWait;

  static final UiRefreshRateService instance = UiRefreshRateService._();

  /// A separate service for tests (own gate, clock and report wait).
  @visibleForTesting
  factory UiRefreshRateService.forTesting({
    FrontendMediaGate? gate,
    DateTime Function()? clock,
    Duration reportWait = const Duration(milliseconds: 1200),
  }) =>
      UiRefreshRateService._(gate: gate, clock: clock, reportWait: reportWait);

  /// iOS only; tests override [defaultTargetPlatform].
  static bool get isSupportedPlatform =>
      !kIsWeb && defaultTargetPlatform == TargetPlatform.iOS;

  /// Duration of the animation run by the "Measure" action.
  static const Duration measureDuration = Duration(milliseconds: 1500);

  /// After a game, the first measurable burst within this window is kept as
  /// the post-game measurement.
  static const Duration postGameWindow = Duration(seconds: 60);

  static final _log = LoggerService.instance;

  final UiRefreshRateChannel _channel;
  final FrontendMediaGate? _gateOverride;
  final DateTime Function() _clock;
  final Duration _reportWait;
  final FrameCadenceEstimator _estimator = FrameCadenceEstimator();

  FrontendMediaGate get _gate => _gateOverride ?? FrontendMediaGate.instance;

  UiRefreshRateState? _state;
  Future<UiRefreshRateState>? _refreshing;
  bool _saving = false;
  UiRefreshRateError? _error;
  String? _errorCode;

  bool _probing = false;
  bool _gateBlocked = false;
  bool _backgrounded = false;
  bool _gameSeen = false;
  int _framesDuringGame = 0;

  FrameCadenceSummary? _lastMeasurement;
  FrameCadenceSummary? _postGameMeasurement;
  int? _postGameSearchFrom;
  int? _postGameBurst;
  DateTime? _postGameDeadline;

  bool _measuring = false;
  bool _measureFailed = false;
  int? _measureFrom;
  Completer<void>? _reportWaiter;

  /// Native state, null until the first [refresh] completes.
  UiRefreshRateState? get state => _state;

  bool get saving => _saving;

  /// Last action error (cleared by the next successful action).
  UiRefreshRateError? get error => _error;

  /// Raw technical code of [error] (platform error code), never translated.
  String? get errorCode => _errorCode;

  /// Whether the passive FrameTiming probe is registered.
  bool get probing => _probing;

  /// Most recent measurable burst of interface frames.
  FrameCadenceSummary? get lastMeasurement => _lastMeasurement;

  /// First measurable burst after the last game (see [postGameWindow]).
  FrameCadenceSummary? get postGameMeasurement => _postGameMeasurement;

  /// Flutter frames reported while the last game held the media gate (about
  /// zero for full-screen games; frames reported in the second after a
  /// launch can be included because the engine reports in batches).
  int get framesDuringGame => _framesDuringGame;

  bool get measuring => _measuring;

  /// The last requested measurement found too few frames.
  bool get measureFailed => _measureFailed;

  /// Reads the native state again (screen, Low Power Mode, temperature,
  /// stored and active preference).
  Future<UiRefreshRateState> refresh() {
    final pending = _refreshing;
    if (pending != null) return pending;
    final future = _readState();
    _refreshing = future;
    return future.whenComplete(() => _refreshing = null);
  }

  Future<UiRefreshRateState> _readState() async {
    UiRefreshRateState next;
    try {
      next = await _channel.getState();
    } on PlatformException catch (error) {
      _log.w('UI refresh: state unavailable (${error.code})');
      next = UiRefreshRateState.unreachable(error.code);
    } catch (error) {
      // A malformed answer must not escape the unawaited probe start.
      _log.w('UI refresh: state unreadable ($error)');
      next = UiRefreshRateState.unreachable('invalidState');
    }
    final previous = _state;
    _state = next;
    if (previous == null ||
        previous.hookStatus != next.hookStatus ||
        previous.screenMaxHz != next.screenMaxHz ||
        previous.storedEnabled != next.storedEnabled) {
      _log.i(
        'UI refresh: hook=${next.hookStatus} stored=${next.storedEnabled} '
        'active=${next.activeEnabled} screenMax=${next.screenMaxHz}Hz '
        'engineTarget=${next.engineTargetHz}Hz lowPower=${next.lowPowerMode} '
        'thermal=${next.thermalState}',
      );
    }
    notifyListeners();
    return next;
  }

  /// Stores [enabled] for the next launch. Returns false (and sets [error]
  /// to [UiRefreshRateError.saveFailed]) when iOS did not keep it; never
  /// reports success for an unsaved choice. Does nothing while unavailable.
  Future<bool> setEnabled(bool enabled) async {
    final current = _state;
    if (current == null || !current.available || _saving) return false;
    _saving = true;
    notifyListeners();
    try {
      final next = await _channel.setEnabled(enabled);
      if (next.storedEnabled != enabled) {
        throw PlatformException(code: 'SAVE_NOT_KEPT');
      }
      _state = next;
      _error = null;
      _errorCode = null;
      _log.i(
        'UI refresh: stored=${next.storedEnabled} active=${next.activeEnabled} '
        '(applies at next launch)',
      );
      return true;
    } on PlatformException catch (error) {
      return _saveFailed(error.code);
    } on MissingPluginException {
      return _saveFailed(UiRefreshRateState.hookPluginMissing);
    } catch (error) {
      _log.w('UI refresh: unreadable answer to setEnabled ($error)');
      return _saveFailed('invalidState');
    } finally {
      _saving = false;
      notifyListeners();
    }
  }

  bool _saveFailed(String code) {
    _error = UiRefreshRateError.saveFailed;
    _errorCode = code;
    _log.w('UI refresh: preference not saved ($code)');
    // Show what iOS actually kept, not the choice that failed.
    unawaited(refresh());
    return false;
  }

  /// Flips the stored preference (gamepad A / tap on the row).
  Future<bool> toggle() {
    final current = _state;
    if (current == null || !current.available) return Future.value(false);
    return setEnabled(!current.storedEnabled);
  }

  /// Starts the passive frame-rate measurement. Idempotent; registers one
  /// timings callback, never a ticker, and never schedules a frame.
  void startProbe() {
    if (_probing) return;
    _probing = true;
    SchedulerBinding.instance.addTimingsCallback(_onTimings);
    WidgetsBinding.instance.addObserver(this);
    _gate.addListener(_onGateChanged);
    _gateBlocked = _gate.blocked;
    _log.i('UI refresh: passive FrameTiming probe started');
    unawaited(refresh());
  }

  /// Removes everything [startProbe] registered.
  void stopProbe() {
    if (!_probing) return;
    _probing = false;
    SchedulerBinding.instance.removeTimingsCallback(_onTimings);
    WidgetsBinding.instance.removeObserver(this);
    _gate.removeListener(_onGateChanged);
  }

  @override
  void dispose() {
    stopProbe();
    _reportWaiter = null;
    super.dispose();
  }

  void _onGateChanged() {
    final blocked = _gate.blocked;
    if (blocked == _gateBlocked) return;
    _gateBlocked = blocked;
    if (blocked) {
      _framesDuringGame = 0;
      _gameSeen = true;
      // "After the last game" must describe the game starting now.
      _postGameMeasurement = null;
      _postGameBurst = null;
      _postGameSearchFrom = null;
      _estimator.split();
    } else {
      _log.i(
        'UI refresh: game ended, $_framesDuringGame interface frames '
        'reported during the game',
      );
      _armPostGame();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    switch (state) {
      case AppLifecycleState.paused:
      case AppLifecycleState.hidden:
        _backgrounded = true;
      case AppLifecycleState.resumed:
        if (!_backgrounded) return;
        _backgrounded = false;
        // Idle time is never measured: the next frames form a new burst.
        _estimator.split();
        if (_gameSeen && !_gateBlocked) _armPostGame();
        // Low Power Mode or the temperature may have changed meanwhile.
        unawaited(refresh());
      case AppLifecycleState.inactive:
      case AppLifecycleState.detached:
        break;
    }
  }

  void _armPostGame() {
    _postGameSearchFrom = _estimator.split();
    _postGameBurst = null;
    _postGameDeadline = _clock().add(postGameWindow);
  }

  void _onTimings(List<FrameTiming> timings) {
    if (_gateBlocked) {
      _framesDuringGame += timings.length;
    } else {
      for (final timing in timings) {
        _estimator.add(
          vsyncStartMicros: timing.timestampInMicroseconds(
            FramePhase.vsyncStart,
          ),
          totalSpanMicros: timing.totalSpan.inMicroseconds,
        );
      }
    }
    final before = _lastMeasurement;
    final beforePostGame = _postGameMeasurement;
    if (!_gateBlocked) {
      _lastMeasurement = _estimator.latest ?? _lastMeasurement;
      _trackPostGame();
    }
    final waiter = _reportWaiter;
    if (waiter != null && !waiter.isCompleted) waiter.complete();
    if (before?.effectiveHz != _lastMeasurement?.effectiveHz ||
        beforePostGame?.effectiveHz != _postGameMeasurement?.effectiveHz) {
      notifyListeners();
    }
  }

  void _trackPostGame() {
    final tracked = _postGameBurst;
    if (tracked != null) {
      // Follow the post-game burst while it grows, then freeze it.
      final current = _estimator.current;
      if (current != null && current.burstId == tracked) {
        _postGameMeasurement = current;
      } else {
        _postGameBurst = null;
        _log.i('UI refresh: after the last game $_postGameMeasurement');
      }
      return;
    }
    final from = _postGameSearchFrom;
    if (from == null) return;
    // The window is judged before any burst is accepted: frames first
    // reported after it no longer describe the return from the game, and a
    // later trip to the background must not re-arm it without a new game.
    final deadline = _postGameDeadline;
    if (deadline != null && _clock().isAfter(deadline)) {
      _postGameSearchFrom = null;
      _postGameDeadline = null;
      _gameSeen = false;
      _log.i(
        'UI refresh: no measurable interface frames within '
        '${postGameWindow.inSeconds} s after the last game',
      );
      return;
    }
    final found = _estimator.firstSince(from);
    if (found != null) {
      _postGameMeasurement = found;
      _postGameSearchFrom = null;
      _postGameDeadline = null;
      _gameSeen = false;
      final current = _estimator.current;
      if (current != null && current.burstId == found.burstId) {
        _postGameBurst = found.burstId;
      } else {
        _log.i('UI refresh: after the last game $found');
      }
    }
  }

  /// Starts a requested measurement. The caller animates for
  /// [measureDuration] (bounded), then calls [completeMeasurement].
  void beginMeasurement() {
    _measuring = true;
    _measureFailed = false;
    _measureFrom = _estimator.split();
    notifyListeners();
  }

  /// Waits for the engine's next timing report (the engine batches them, up
  /// to one second in release), then keeps the largest measurable burst
  /// since [beginMeasurement]. Null when the interface drew too few frames.
  Future<FrameCadenceSummary?> completeMeasurement() async {
    final from = _measureFrom;
    if (!_measuring || from == null) return null;
    final waiter = Completer<void>();
    _reportWaiter = waiter;
    await Future.any(<Future<void>>[
      waiter.future,
      Future<void>.delayed(_reportWait),
    ]);
    if (identical(_reportWaiter, waiter)) _reportWaiter = null;
    if (!_measuring || _measureFrom != from) return null; // cancelled
    final result = _estimator.bestSince(from);
    _measuring = false;
    _measureFrom = null;
    _measureFailed = result == null;
    if (result != null) _lastMeasurement = result;
    _log.i('UI refresh: requested measurement ${result ?? 'too few frames'}');
    notifyListeners();
    return result;
  }

  /// Ends a requested measurement without a result (row disposed).
  void cancelMeasurement() {
    if (!_measuring) return;
    _measuring = false;
    _measureFrom = null;
    final waiter = _reportWaiter;
    _reportWaiter = null;
    // No notification: called while the requesting row is being disposed.
    if (waiter != null && !waiter.isCompleted) waiter.complete();
  }
}
