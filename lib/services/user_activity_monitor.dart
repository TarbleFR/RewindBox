import 'dart:async';

import 'package:flutter/gestures.dart';
import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:gamepads/gamepads.dart';

/// Whether the player has left the interface alone for a while.
///
/// A looping decoration (the floating bubble of the selected console, the
/// rainbow outline of the selected game, the liquid of a charging battery,
/// the bell's pulse) asks the engine for a frame on every vsync, 120 per
/// second on a ProMotion screen, for as long as it runs: left on a menu, the
/// phone keeps rendering and warms up for nothing. After [idleAfter] without
/// a touch, a key or a controller input, [idle] turns true and those
/// decorations hold a still frame; the next input brings them back at once.
///
/// One timer, armed lazily: an input only records its time, the timer
/// checks it when it fires and waits again for the remainder.
class UserActivityMonitor extends ChangeNotifier {
  UserActivityMonitor._();

  static final UserActivityMonitor instance = UserActivityMonitor._();

  /// Time without input after which the interface counts as idle.
  static const Duration idleAfter = Duration(seconds: 60);

  /// A stick deflection below this is drift, not the player.
  static const double _stickThreshold = 0.5;

  bool _started = false;
  bool _idle = false;
  Timer? _timer;
  StreamSubscription<GamepadEvent>? _pads;
  Duration _last = Duration.zero;
  final Stopwatch _clock = Stopwatch();

  /// No input for [idleAfter].
  bool get idle => _idle;

  /// Starts watching the inputs (idempotent; called by the first decoration).
  void ensureStarted() {
    if (_started) return;
    _started = true;
    _clock.start();
    _last = _clock.elapsed;
    GestureBinding.instance.pointerRouter.addGlobalRoute(_onPointer);
    HardwareKeyboard.instance.addHandler(_onKey);
    try {
      _pads = Gamepads.events.listen(
        _onPad,
        onError: (Object _) {},
        cancelOnError: false,
      );
    } catch (_) {
      // No controller plugin (tests, other platforms): touches and keys only.
    }
    _arm(idleAfter);
  }

  /// Counts as an input (also used by tests).
  void noteActivity() {
    if (!_started) return;
    _last = _clock.elapsed;
    if (_idle) {
      _idle = false;
      _arm(idleAfter);
      notifyListeners();
    }
  }

  void _onPointer(PointerEvent event) {
    if (event is PointerDownEvent ||
        event is PointerMoveEvent ||
        event is PointerScrollEvent ||
        event is PointerPanZoomUpdateEvent) {
      noteActivity();
    }
  }

  bool _onKey(KeyEvent event) {
    noteActivity();
    return false;
  }

  void _onPad(GamepadEvent event) {
    if (event.type == KeyType.analog && event.value.abs() < _stickThreshold) {
      return;
    }
    noteActivity();
  }

  void _arm(Duration delay) {
    _timer?.cancel();
    // In the root zone: the watch outlives whichever widget started it (and a
    // widget test's fake clock, which must not count it as left pending).
    _timer = Zone.root.createTimer(delay, _check);
  }

  void _check() {
    final quiet = _clock.elapsed - _last;
    if (quiet < idleAfter) {
      _arm(idleAfter - quiet);
      return;
    }
    _timer = null;
    if (_idle) return;
    _idle = true;
    notifyListeners();
  }

  /// Test hook: forgets the inputs and the idle state.
  @visibleForTesting
  void debugReset({bool idle = false}) {
    _idle = idle;
    if (_started) {
      _last = _clock.elapsed;
      if (!idle) _arm(idleAfter);
    }
    notifyListeners();
  }

  /// Test hook: turns idle now, as if [idleAfter] had passed.
  @visibleForTesting
  void debugGoIdle() {
    _timer?.cancel();
    _timer = null;
    if (_idle) return;
    _idle = true;
    notifyListeners();
  }

  /// Test hook: stops watching (a fresh [ensureStarted] starts again).
  @visibleForTesting
  void debugStop() {
    if (!_started) return;
    _started = false;
    _timer?.cancel();
    _timer = null;
    _pads?.cancel();
    _pads = null;
    GestureBinding.instance.pointerRouter.removeGlobalRoute(_onPointer);
    HardwareKeyboard.instance.removeHandler(_onKey);
    _clock
      ..stop()
      ..reset();
    _idle = false;
  }
}
