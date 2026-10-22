import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../services/frontend_media_gate.dart';

/// Shared neutral glass. Theme accents never enter the selection material.
abstract final class NeoBubbleStyle {
  static bool reduceMotion(BuildContext context) {
    final media = MediaQuery.maybeOf(context);
    final features =
        WidgetsBinding.instance.platformDispatcher.accessibilityFeatures;
    return features.reduceMotion ||
        features.disableAnimations ||
        features.accessibleNavigation ||
        (media?.disableAnimations ?? false) ||
        (media?.accessibleNavigation ?? false);
  }

  static Color fill(BuildContext context, {bool selected = true}) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final contrast = MediaQuery.maybeOf(context)?.highContrast ?? false;
    return (dark ? Colors.white : Colors.black).withValues(
      alpha: contrast ? (selected ? 0.27 : 0.12) : (selected ? 0.14 : 0.045),
    );
  }

  static BoxDecoration decoration(
    BuildContext context, {
    double radius = 24,
    bool selected = true,
  }) => BoxDecoration(
    color: fill(context, selected: selected),
    borderRadius: BorderRadius.circular(radius),
    border: Border.all(color: rim(context, selected: selected)),
    gradient: LinearGradient(
      begin: Alignment.topLeft,
      end: Alignment.bottomRight,
      colors: [
        Colors.white.withValues(alpha: selected ? 0.16 : 0.06),
        Colors.white.withValues(alpha: 0.015),
        Colors.white.withValues(alpha: selected ? 0.08 : 0.025),
      ],
    ),
  );

  static Color rim(BuildContext context, {bool selected = true}) => Theme.of(
    context,
  ).colorScheme.onSurface.withValues(alpha: selected ? 0.56 : 0.18);
}

/// A convex, translucent lens with a reflective rim and a soft lower lip.
/// Dense card/label collections deliberately use the zero-blur path.
class NeoGlassBubble extends StatelessWidget {
  const NeoGlassBubble({
    super.key,
    required this.child,
    this.selected = true,
    this.radius,
    this.blur = false,
    this.padding,
  });

  final Widget child;
  final bool selected;
  final double? radius;
  final bool blur;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final shortest = math.min(constraints.maxWidth, constraints.maxHeight);
      final resolved = radius ?? (shortest.isFinite ? shortest * 0.46 : 24.0);
      final borderRadius = BorderRadius.circular(resolved);
      final dark = Theme.of(context).brightness == Brightness.dark;
      final material = DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: borderRadius,
          color: NeoBubbleStyle.fill(context, selected: selected),
          gradient: LinearGradient(
            begin: const Alignment(-0.8, -1),
            end: const Alignment(0.65, 1),
            stops: const [0, 0.22, 0.64, 1],
            colors: [
              Colors.white.withValues(alpha: selected ? 0.22 : 0.10),
              Colors.white.withValues(alpha: selected ? 0.045 : 0.015),
              (dark ? Colors.black : Colors.white).withValues(alpha: 0.025),
              Colors.white.withValues(alpha: selected ? 0.11 : 0.035),
            ],
          ),
          border: Border.all(
            color: NeoBubbleStyle.rim(context, selected: selected),
            width: selected ? 1.2 : 0.8,
          ),
        ),
        child: CustomPaint(
          foregroundPainter: _BubbleReflection(
            selected: selected,
            radius: resolved,
          ),
          child: padding == null
              ? child
              : Padding(padding: padding!, child: child),
        ),
      );
      return DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: borderRadius,
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(alpha: selected ? 0.20 : 0.10),
              blurRadius: selected ? 12 : 6,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: ClipRRect(
          borderRadius: borderRadius,
          child: blur && !(MediaQuery.maybeOf(context)?.highContrast ?? false)
              ? BackdropFilter(
                  filter: ui.ImageFilter.blur(sigmaX: 5, sigmaY: 5),
                  child: material,
                )
              : material,
        ),
      );
    },
  );
}

class _BubbleReflection extends CustomPainter {
  const _BubbleReflection({required this.selected, required this.radius});
  final bool selected;
  final double radius;

  @override
  void paint(Canvas canvas, Size size) {
    final rect = (Offset.zero & size).deflate(2.1);
    if (rect.isEmpty) return;
    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [
          Colors.white.withValues(alpha: selected ? 0.65 : 0.30),
          Colors.white.withValues(alpha: 0),
          Colors.white.withValues(alpha: selected ? 0.20 : 0.08),
        ],
        stops: const [0, 0.48, 1],
      ).createShader(rect);
    canvas.drawRRect(
      RRect.fromRectAndRadius(rect, Radius.circular(math.max(0.0, radius - 2))),
      paint,
    );
  }

  @override
  bool shouldRepaint(_BubbleReflection old) =>
      old.selected != selected || old.radius != radius;
}

/// At most the focused card floats. Motion stops for reduced motion, hidden
/// routes/tabs, backgrounding and every embedded game via the existing gate.
class NeoBubbleMotion extends StatefulWidget {
  const NeoBubbleMotion({
    super.key,
    required this.child,
    this.selected = false,
    this.pressed = false,
    this.float = false,
  });
  final Widget child;
  final bool selected;
  final bool pressed;
  final bool float;

  @override
  State<NeoBubbleMotion> createState() => _NeoBubbleMotionState();
}

class _NeoBubbleMotionState extends State<NeoBubbleMotion>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late final AnimationController _float;
  bool _touchDown = false;
  bool _foreground = true;
  bool _tickerEnabled = true;
  bool _reduced = false;

  @override
  void initState() {
    super.initState();
    _float = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2800),
    );
    WidgetsBinding.instance.addObserver(this);
    FrontendMediaGate.instance.addListener(_mediaChanged);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _tickerEnabled = TickerMode.valuesOf(context).enabled;
    _reduced = NeoBubbleStyle.reduceMotion(context);
    _syncMotion();
  }

  @override
  void didUpdateWidget(NeoBubbleMotion oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncMotion();
  }

  @override
  void didChangeAccessibilityFeatures() {
    if (!mounted) return;
    setState(() => _reduced = NeoBubbleStyle.reduceMotion(context));
    _syncMotion();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _foreground = state == AppLifecycleState.resumed;
    if (!_foreground && _touchDown && mounted)
      setState(() => _touchDown = false);
    _syncMotion();
  }

  void _mediaChanged() {
    if (mounted) setState(() {});
    _syncMotion();
  }

  void _syncMotion() {
    if (widget.float &&
        widget.selected &&
        !_reduced &&
        _foreground &&
        _tickerEnabled &&
        !FrontendMediaGate.instance.blocked) {
      if (!_float.isAnimating) _float.repeat(reverse: true);
    } else {
      _float.stop();
      if (_float.value != 0) _float.value = 0;
    }
  }

  @override
  void dispose() {
    FrontendMediaGate.instance.removeListener(_mediaChanged);
    WidgetsBinding.instance.removeObserver(this);
    _float.dispose();
    super.dispose();
  }

  void _press(bool value) {
    if (_touchDown != value) setState(() => _touchDown = value);
  }

  @override
  Widget build(BuildContext context) {
    final blocked = FrontendMediaGate.instance.blocked || !_foreground;
    return Listener(
      onPointerDown: (_) => _press(true),
      onPointerUp: (_) => _press(false),
      onPointerCancel: (_) => _press(false),
      child: AnimatedScale(
        scale: _reduced || blocked
            ? 1
            : (_touchDown || widget.pressed)
            ? 0.958
            : widget.selected && widget.float
            ? 1.018
            : 1,
        duration: _reduced || blocked
            ? Duration.zero
            : const Duration(milliseconds: 170),
        curve: Curves.easeOutCubic,
        child: AnimatedBuilder(
          animation: _float,
          child: widget.child,
          builder: (context, child) => Transform.translate(
            offset: Offset(
              0,
              _reduced || blocked
                  ? 0
                  : -0.65 * (1 - math.cos(_float.value * math.pi)),
            ),
            child: child,
          ),
        ),
      ),
    );
  }
}
