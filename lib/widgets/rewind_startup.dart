import 'dart:async';
import 'dart:math' as math;
import 'package:flutter/material.dart';
import 'rewind_mark_path.dart';

/// Owns presentation only. Database, permissions and scanning continue normally.
class RewindStartupController extends ChangeNotifier {
  Widget? application;
  Widget? issue;
  bool ready = false;

  void attach(Widget child) {
    application = child;
    notifyListeners();
  }

  void showIssue(Widget? child) {
    issue = child;
    notifyListeners();
  }

  void contentReady() {
    if (ready) return;
    ready = true;
    notifyListeners();
  }
}

class _StartupScope extends InheritedWidget {
  const _StartupScope({required this.controller, required super.child});
  final RewindStartupController controller;
  @override
  bool updateShouldNotify(_StartupScope oldWidget) =>
      controller != oldWidget.controller;
}

/// Signals a real painted destination (library, setup, or a recoverable error).
/// Merely constructing MaterialApp is deliberately insufficient.
class RewindStartupReady extends StatefulWidget {
  const RewindStartupReady({super.key, required this.child});
  final Widget child;
  static bool pending(BuildContext context) =>
      !(context.getInheritedWidgetOfExactType<_StartupScope>()?.controller.ready ?? true);
  @override
  State<RewindStartupReady> createState() => _RewindStartupReadyState();
}

class _RewindStartupReadyState extends State<RewindStartupReady> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.getInheritedWidgetOfExactType<_StartupScope>()
          ?.controller.contentReady();
    });
  }

  @override
  Widget build(BuildContext context) => widget.child;
}

/// A single root survives the handoff from pre-database loading to MyApp.
/// The real app stays mounted and paints below the input/semantics barrier.
class RewindStartupRoot extends StatefulWidget {
  const RewindStartupRoot({super.key, required this.controller});
  final RewindStartupController controller;
  @override
  State<RewindStartupRoot> createState() => _RewindStartupRootState();
}

class _RewindStartupRootState extends State<RewindStartupRoot>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _assembly = AnimationController(
    vsync: this, duration: const Duration(milliseconds: 1120),
  );
  late final AnimationController _breath = AnimationController(
    vsync: this, duration: const Duration(milliseconds: 1800),
  );
  late final AnimationController _opening = AnimationController(
    vsync: this, duration: const Duration(milliseconds: 240),
  );
  Timer? _activityTimer;
  bool _showActivity = false;
  bool _dismissed = false;
  bool _reduced = false;
  bool _active = true;
  bool _openingStarted = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    widget.controller.addListener(_changed);
    _opening.addStatusListener((status) {
      if (status == AnimationStatus.completed && mounted) {
        _assembly.stop();
        _breath.stop();
        _activityTimer?.cancel();
        setState(() => _dismissed = true);
      }
    });
    // Paint the static native mark first, then rewind its actual fragments.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _changed();
      _updateMotion();
    });
    _activityTimer = Timer(const Duration(milliseconds: 1500), () {
      if (mounted && !_dismissed) setState(() => _showActivity = true);
    });
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _readAccessibility();
  }

  void _readAccessibility() {
    final features = WidgetsBinding.instance.platformDispatcher.accessibilityFeatures;
    _reduced = features.reduceMotion || features.disableAnimations ||
        features.accessibleNavigation || (MediaQuery.maybeOf(context)?.disableAnimations ?? false);
    _updateMotion();
  }

  @override
  void didChangeAccessibilityFeatures() {
    if (!mounted) return;
    setState(_readAccessibility);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _active = state == AppLifecycleState.resumed;
    _updateMotion();
  }

  void _updateMotion() {
    if (_dismissed) return;
    if (!_active || _reduced || widget.controller.issue != null) {
      _assembly.stop();
      _breath.stop();
      _opening.stop();
      if (_reduced) _assembly.value = 1;
      if (_active && _openingStarted) _opening.forward();
      return;
    }
    if (!_openingStarted) {
      if (!_assembly.isCompleted) _assembly.forward();
      if (!_breath.isAnimating) _breath.repeat(reverse: true);
    } else {
      _opening.forward();
    }
  }

  void _changed() {
    if (!mounted || _dismissed) return;
    if (widget.controller.ready && widget.controller.issue == null &&
        widget.controller.application != null && !_openingStarted) {
      _openingStarted = true;
      _assembly.stop();
      _breath.stop();
      // No minimum intro duration: settle the current fragments while opening.
      _opening.duration = Duration(milliseconds: _reduced ? 100 : 240);
      if (_active) _opening.forward();
    }
    _updateMotion();
    setState(() {});
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    widget.controller.removeListener(_changed);
    _activityTimer?.cancel();
    _assembly.dispose();
    _breath.dispose();
    _opening.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return _StartupScope(
      controller: widget.controller,
      child: Directionality(
        textDirection: TextDirection.ltr,
        child: Stack(fit: StackFit.expand, children: [
          const ColoredBox(color: Colors.black),
          if (widget.controller.application != null)
            ExcludeSemantics(
              excluding: !_dismissed,
              child: IgnorePointer(
                ignoring: !_dismissed,
                child: ExcludeFocus(
                  excluding: !_dismissed,
                  child: widget.controller.application!,
                ),
              ),
            ),
          if (!_dismissed)
            Positioned.fill(
              child: AbsorbPointer(
                key: const ValueKey('rewind-motion-intro'),
                child: AnimatedBuilder(
                  animation: Listenable.merge([_assembly, _breath, _opening]),
                  builder: (context, _) {
                    final exit = Curves.easeOutCubic.transform(_opening.value);
                    return Opacity(
                      opacity: 1 - exit,
                      child: ColoredBox(
                        color: Colors.black,
                        child: Stack(fit: StackFit.expand, children: [
                          Center(child: LayoutBuilder(builder: (context, constraints) {
                            final side = math.min(232.0, math.min(constraints.maxWidth, constraints.maxHeight) * .58);
                            return Transform.scale(
                              scale: _reduced ? 1 : 1 + exit * .045 +
                                  (_assembly.isCompleted && !_openingStarted ? _breath.value * .006 : 0),
                              child: SizedBox.square(
                                dimension: side,
                                child: RepaintBoundary(child: CustomPaint(
                                  painter: RewindMarkPainter(
                                    progress: _assembly.value,
                                    settle: exit,
                                    reduced: _reduced,
                                  ),
                                )),
                              ),
                            );
                          })),
                          if (_showActivity && !_openingStarted && widget.controller.issue == null)
                            Align(
                              alignment: const Alignment(0, .55),
                              child: SizedBox(width: 44, height: 2,
                                child: LinearProgressIndicator(
                                  value: _reduced ? 0.5 : null,
                                  color: Colors.white54,
                                  backgroundColor: Colors.white12,
                                  minHeight: 2,
                                ),
                              ),
                            ),
                        ]),
                      ),
                    );
                  },
                ),
              ),
            ),
          // Recovery stays interactive and never looks like ongoing progress.
          if (widget.controller.issue != null) widget.controller.issue!,
        ]),
      ),
    );
  }
}

/// The two contours are a measured trace of the supplied mark, not a font or
/// a redrawn approximation. Native PDF and Flutter use the same coordinates.
class RewindMarkPainter extends CustomPainter {
  const RewindMarkPainter({this.progress = 1, this.settle = 0, this.reduced = false});
  final double progress;
  final double settle;
  final bool reduced;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.save();
    canvas.scale(size.width / 2048, size.height / 2048);
    final white = Paint()..color = (!reduced && progress > .82 && progress < 1)
        ? const Color(0xFFE6E6E6) : Colors.white;
    if (reduced || progress == 0 || progress >= .82 || settle >= 1) {
      canvas.drawPath(rewindMarkPath, white);
    } else {
      for (var i = 0; i < 6; i++) {
        final local = ((progress - .10 - i * .018) / .62).clamp(0.0, 1.0);
        final appearance = (progress / .1).clamp(0.0, 1.0);
        final displacement = (1 - Curves.elasticOut.transform(local)) * appearance * (1 - settle);
        final dx = (i.isEven ? 1 : -1) * 210 * displacement;
        final dy = (i - 2.5) * 20 * displacement;
        final clip = Rect.fromLTWH(0, i * 2048 / 6, 2048, 2048 / 6 + .3);
        for (var trail = 2; trail >= 0; trail--) {
          canvas.save();
          canvas.translate(dx + trail * 25 * displacement, dy);
          canvas.translate(1024, 1024);
          canvas.rotate(displacement * (i.isEven ? .035 : -.035));
          canvas.translate(-1024, -1024);
          canvas.clipRect(clip);
          canvas.drawPath(rewindMarkPath, Paint()..color = Colors.white.withValues(
            alpha: trail == 0 ? 1 : .065 * displacement.abs().clamp(0.0, 1.0),
          ));
          canvas.restore();
        }
      }
    }
    // A single restrained reflection, clipped to the real contours.
    if (!reduced && progress > .82 && progress < 1 && settle == 0) {
      final x = (progress - .82) / .18 * 2200 - 300;
      canvas.save();
      canvas.clipPath(rewindMarkPath);
      canvas.drawRect(const Rect.fromLTWH(0, 0, 2048, 2048), Paint()
        ..shader = LinearGradient(colors: const [Colors.transparent, Color(0x28FFFFFF), Colors.transparent])
            .createShader(Rect.fromLTWH(x, 0, 220, 2048)));
      canvas.restore();
    }
    canvas.restore();
  }

  @override
  bool shouldRepaint(RewindMarkPainter oldDelegate) => progress != oldDelegate.progress ||
      settle != oldDelegate.settle || reduced != oldDelegate.reduced;
}
