import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';

import '../services/frontend_media_gate.dart';
import '../services/glass_performance_governor.dart';

/// One paint-only clock for all visible liquid indicators. No idle timer,
/// image decoding or widget rebuilds; native catalogue pages use their own
/// shared CADisplayLink because they do not render through Flutter.
class LiquidMotionClock extends ChangeNotifier with WidgetsBindingObserver {
  LiquidMotionClock._();
  static final instance = LiquidMotionClock._();
  final Set<Object> _owners = {};
  Ticker? _ticker;
  Duration _last = Duration.zero;
  bool _foreground = true;
  bool _lowPower = false;
  double _phase = 0;
  double get phase => _phase;
  bool get lowPower => _lowPower;
  bool get running => _ticker?.isActive ?? false;

  set lowPower(bool value) {
    if (_lowPower == value) return;
    _lowPower = value;
    GlassPerformanceGovernor.instance.lowPower = value;
    _sync();
    notifyListeners();
  }

  void attach(Object owner) {
    if (_owners.isEmpty) {
      WidgetsBinding.instance.addObserver(this);
      FrontendMediaGate.instance.addListener(_sync);
      _foreground =
          WidgetsBinding.instance.lifecycleState == null ||
          WidgetsBinding.instance.lifecycleState == AppLifecycleState.resumed;
    }
    _owners.add(owner);
    _sync();
  }

  void detach(Object owner) {
    _owners.remove(owner);
    _sync();
    if (_owners.isEmpty) {
      WidgetsBinding.instance.removeObserver(this);
      FrontendMediaGate.instance.removeListener(_sync);
      _ticker?.dispose();
      _ticker = null;
    }
  }

  void _sync() {
    final features =
        WidgetsBinding.instance.platformDispatcher.accessibilityFeatures;
    final enabled =
        _owners.isNotEmpty &&
        _foreground &&
        !_lowPower &&
        !FrontendMediaGate.instance.blocked &&
        !features.reduceMotion &&
        !features.disableAnimations &&
        !features.accessibleNavigation;
    if (enabled) {
      _ticker ??= Ticker((elapsed) {
        // Slow water needs only 30 paint updates/sec, independent of 120 Hz UI.
        if (elapsed - _last < const Duration(milliseconds: 32)) return;
        _last = elapsed;
        _phase = (elapsed.inMicroseconds / 2400000) % 1;
        notifyListeners();
      });
      if (!_ticker!.isActive) {
        _last = Duration.zero;
        _ticker!.start();
      }
    } else {
      _ticker?.stop();
    }
  }

  @override
  void didChangeAccessibilityFeatures() => _sync();
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    _sync();
  }
}

/// Attaches only an active, visible surface to the shared clock.
class LiquidMotionPaint extends StatefulWidget {
  const LiquidMotionPaint({
    super.key,
    required this.active,
    required this.builder,
  });
  final bool active;
  final Widget Function(BuildContext, LiquidMotionClock) builder;
  @override
  State<LiquidMotionPaint> createState() => _LiquidMotionPaintState();
}

class _LiquidMotionPaintState extends State<LiquidMotionPaint> {
  bool _attached = false;
  void _sync() {
    final media = MediaQuery.maybeOf(context);
    final active =
        widget.active &&
        TickerMode.valuesOf(context).enabled &&
        !(media?.disableAnimations ?? false) &&
        !(media?.accessibleNavigation ?? false);
    if (_attached == active) return;
    _attached = active;
    if (active) {
      LiquidMotionClock.instance.attach(this);
    } else {
      LiquidMotionClock.instance.detach(this);
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _sync();
  }

  @override
  void didUpdateWidget(LiquidMotionPaint old) {
    super.didUpdateWidget(old);
    _sync();
  }

  @override
  void dispose() {
    if (_attached) LiquidMotionClock.instance.detach(this);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) =>
      widget.builder(context, LiquidMotionClock.instance);
}
