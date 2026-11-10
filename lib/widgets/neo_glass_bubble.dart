import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';

import '../services/frontend_media_gate.dart';
import '../themes/liquid_glass_theme.dart';

/// Shared neutral glass. Theme accents never enter the selection material.
/// Strength follows the Liquid Glass intensity and contrast settings; the
/// user's motion level and iOS Reduce Motion both stop the decorative drift.
abstract final class NeoBubbleStyle {
  static bool reduceMotion(BuildContext context) =>
      !LiquidGlassTheme.of(context).decorativeMotion(context);

  /// Rim/fill strength multiplier of the active interface style.
  static double strength(BuildContext context) {
    final glass = LiquidGlassTheme.of(context);
    return (glass.intensityScale * glass.contrastScale).clamp(0.3, 2.0);
  }

  static Color fill(BuildContext context, {bool selected = true}) {
    final dark = Theme.of(context).brightness == Brightness.dark;
    final contrast = MediaQuery.maybeOf(context)?.highContrast ?? false;
    final base = contrast
        ? (selected ? 0.27 : 0.12)
        : (selected ? 0.14 : 0.045);
    return (dark ? Colors.white : Colors.black).withValues(
      alpha: (base * strength(context)).clamp(0.0, 0.5),
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

  static Color rim(BuildContext context, {bool selected = true}) =>
      (Theme.of(context).brightness == Brightness.dark
              ? Colors.white
              : Colors.black)
          .withValues(
            alpha: ((selected ? 0.56 : 0.18) * strength(context)).clamp(
              0.0,
              0.9,
            ),
          );
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
      final contrast = MediaQuery.maybeOf(context)?.highContrast ?? false;
      final light = _BubbleLight.of(context);
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
          foregroundPainter: NeoGlassLensPainter(
            selected: selected,
            radius: resolved,
            highContrast: contrast,
            light: light,
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

/// Optical depth painted over the artwork: a thick clear edge, a reflected
/// ceiling light and a narrow lower meniscus. The clear center preserves text
/// and original image detail; there is no per-card blur or artwork resampling.
class NeoGlassLensPainter extends CustomPainter {
  NeoGlassLensPainter({
    required this.selected,
    required this.radius,
    this.highContrast = false,
    this.light,
    this.opacity = 1,
  }) : super(repaint: light);
  final bool selected;
  final double radius;
  final bool highContrast;
  final Animation<double>? light;
  final double opacity;

  @override
  void paint(Canvas canvas, Size size) {
    if (opacity <= 0) return;
    final rect = (Offset.zero & size).deflate(0.7);
    if (rect.isEmpty) return;
    final r = math.min(radius, rect.shortestSide / 2);
    final thickness = (rect.shortestSide * 0.048).clamp(2.0, 8.0);
    final outside = RRect.fromRectAndRadius(rect, Radius.circular(r));
    final inside = RRect.fromRectAndRadius(
      rect.deflate(thickness),
      Radius.circular(math.max(0, r - thickness)),
    );
    final edge = Path()
      ..fillType = PathFillType.evenOdd
      ..addRRect(outside)
      ..addRRect(inside);
    final illumination = light?.value ?? 0;
    final drift = 0.045 * math.sin(illumination * math.pi);
    final strength = selected ? 1.0 : 0.62;
    Color white(double alpha) =>
        Colors.white.withValues(alpha: alpha * strength * opacity);
    Color black(double alpha) =>
        Colors.black.withValues(alpha: alpha * strength * opacity);

    // A light-dark-light annulus reads as a convex edge instead of a flat
    // translucent fill. Gradients stay neutral under every imported theme.
    canvas.drawPath(
      edge,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment(-0.9 + drift, -1),
          end: const Alignment(0.7, 1),
          colors: [
            white(0.40),
            white(0.08),
            black(0.13),
            white(0.18),
            white(0.33),
          ],
          stops: const [0, 0.18, 0.48, 0.79, 1],
        ).createShader(rect),
    );

    // Broad surface glint is kept near the upper edge, away from the label.
    if (!highContrast) {
      canvas.save();
      canvas.clipRRect(outside);
      final glint = Rect.fromLTWH(
        rect.left + rect.width * (0.06 + drift),
        rect.top - rect.height * 0.12,
        rect.width * 0.88,
        rect.height * 0.40,
      );
      canvas.drawOval(
        glint,
        Paint()
          ..shader = RadialGradient(
            center: const Alignment(-0.25, -0.1),
            radius: 0.85,
            colors: [white(0.17), white(0.045), white(0)],
            stops: const [0, 0.5, 1],
          ).createShader(glint),
      );
      canvas.restore();
    }

    final paint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = highContrast ? 1.6 : 1.05
      ..shader = LinearGradient(
        begin: Alignment.topLeft,
        end: Alignment.bottomRight,
        colors: [white(highContrast ? 0.95 : 0.80), white(0.06), white(0.42)],
        stops: const [0, 0.54, 1],
      ).createShader(rect);
    canvas.drawRRect(outside, paint);
    // A darker inner boundary adds thickness without a luminous outer halo.
    canvas.drawRRect(
      inside,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 0.7
        ..shader = LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [white(0.16), black(0.16), white(0.12)],
        ).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(NeoGlassLensPainter old) =>
      old.selected != selected ||
      old.radius != radius ||
      old.highContrast != highContrast ||
      old.opacity != opacity ||
      old.light != light;
}

/// Only the painter listens to idle light changes, without rebuilding artwork,
/// text, decoded media or the card layout on every frame.
class _BubbleLight extends InheritedWidget {
  const _BubbleLight({required this.light, required super.child});
  final Animation<double> light;
  static Animation<double>? of(BuildContext context) =>
      context.dependOnInheritedWidgetOfExactType<_BubbleLight>()?.light;
  @override
  bool updateShouldNotify(_BubbleLight old) => light != old.light;
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
    if (!_foreground && _touchDown && mounted) {
      setState(() => _touchDown = false);
    }
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
    final pressed = _touchDown || widget.pressed;
    return Listener(
      onPointerDown: (_) => _press(true),
      onPointerUp: (_) => _press(false),
      onPointerCancel: (_) => _press(false),
      child: _BubbleLight(
        light: _float,
        child: AnimatedScale(
          scale: _reduced || blocked
              ? 1
              : pressed
              ? 0.958
              : widget.selected && widget.float
              ? 1.018
              : 1,
          duration: _reduced || blocked
              ? Duration.zero
              : const Duration(milliseconds: 170),
          curve: Curves.easeOutCubic,
          child: TweenAnimationBuilder<double>(
            tween: Tween(
              begin: 0,
              end: !_reduced && !blocked && pressed ? 1 : 0,
            ),
            duration: _reduced || blocked
                ? Duration.zero
                : const Duration(milliseconds: 170),
            curve: Curves.easeOutCubic,
            builder: (context, pressure, child) => Transform.scale(
              key: const ValueKey('neo-bubble-pressure'),
              scaleX: 1 + pressure * 0.022,
              scaleY: 1 - pressure * 0.018,
              child: child,
            ),
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
        ),
      ),
    );
  }
}
