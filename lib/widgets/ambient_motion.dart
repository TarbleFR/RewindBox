import 'package:flutter/widgets.dart';

import '../services/frontend_media_gate.dart';
import '../services/glass_performance_governor.dart';

/// Decides whether a decorative, endlessly repeating animation may run.
///
/// A repeating [AnimationController] schedules a frame on every vsync (60 to
/// 120 per second) for as long as it runs. The Flutter tree stays mounted
/// while an embedded game plays in-process, so an ungated loop keeps the
/// GPU and CPU busy under the emulator. Motion is allowed only when:
/// * the app is in the foreground;
/// * no embedded game holds [FrontendMediaGate];
/// * Low Power Mode is off ([GlassPerformanceGovernor.decorativeMotion]);
/// * the system does not ask to reduce motion.
///
/// [TickerMode] is already honoured by the ticker providers. The state calls
/// [onAmbientMotionChanged] on every change and shows a still frame when
/// motion is not allowed.
mixin AmbientMotion<T extends StatefulWidget> on State<T> {
  late final _AmbientLifecycle _ambientLifecycle = _AmbientLifecycle(
    _syncAmbientMotion,
  );
  bool _ambientForeground = true;
  bool _ambientReduced = false;
  bool? _ambientAllowed;

  /// Whether the decorative animation may run right now.
  bool get ambientMotionAllowed => _ambientAllowed ?? false;

  /// Starts or stops the animation; called on every change of
  /// [ambientMotionAllowed].
  void onAmbientMotionChanged(bool allowed);

  @override
  void initState() {
    super.initState();
    final state = WidgetsBinding.instance.lifecycleState;
    _ambientForeground = state == null || state == AppLifecycleState.resumed;
    WidgetsBinding.instance.addObserver(_ambientLifecycle);
    FrontendMediaGate.instance.addListener(_syncAmbientMotion);
    GlassPerformanceGovernor.instance.addListener(_syncAmbientMotion);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final media = MediaQuery.maybeOf(context);
    _ambientReduced =
        (media?.disableAnimations ?? false) ||
        (media?.accessibleNavigation ?? false);
    // A build follows didChangeDependencies: no extra rebuild needed.
    _updateAmbientMotion(rebuild: false);
  }

  @override
  void dispose() {
    GlassPerformanceGovernor.instance.removeListener(_syncAmbientMotion);
    FrontendMediaGate.instance.removeListener(_syncAmbientMotion);
    WidgetsBinding.instance.removeObserver(_ambientLifecycle);
    super.dispose();
  }

  void _syncAmbientMotion([AppLifecycleState? lifecycle]) {
    if (lifecycle != null) {
      _ambientForeground = lifecycle == AppLifecycleState.resumed;
    }
    _updateAmbientMotion(rebuild: true);
  }

  void _updateAmbientMotion({required bool rebuild}) {
    if (!mounted) return;
    final allowed =
        _ambientForeground &&
        !_ambientReduced &&
        !FrontendMediaGate.instance.blocked &&
        GlassPerformanceGovernor.instance.decorativeMotion;
    if (_ambientAllowed == allowed) return;
    _ambientAllowed = allowed;
    onAmbientMotionChanged(allowed);
    // The still frame differs from the moving one.
    if (rebuild) setState(() {});
  }
}

class _AmbientLifecycle with WidgetsBindingObserver {
  _AmbientLifecycle(this.onChange);

  final void Function([AppLifecycleState?]) onChange;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) => onChange(state);
}
