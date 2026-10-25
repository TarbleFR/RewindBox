import 'package:flutter/material.dart';

import '../../themes/liquid_glass_theme.dart';

/// First level of the glass architecture: the page background behind every
/// glass surface. It is painted once, never blurred, and stays static (no
/// animation, no shader): a soft vertical tone over the scaffold colour and,
/// in the glass style, two faint accent glows so translucent surfaces have
/// something to show through. Custom console backgrounds sit above it.
class GlassBackdrop extends StatelessWidget {
  const GlassBackdrop({super.key, this.child});

  final Widget? child;

  static Decoration decorationFor(ThemeData theme) {
    final glass =
        theme.extension<LiquidGlassTheme>() ?? LiquidGlassTheme.standard;
    final base = theme.scaffoldBackgroundColor;
    final scheme = theme.colorScheme;
    final light = ChromeSurfaceLuminance.isLight(theme);
    switch (glass.style) {
      case InterfaceStyle.minimal:
        return BoxDecoration(color: base);
      case InterfaceStyle.classic:
        return BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topCenter,
            end: Alignment.bottomCenter,
            colors: [
              Color.alphaBlend(
                (light ? Colors.white : Colors.black).withValues(alpha: 0.05),
                base,
              ),
              base,
            ],
          ),
        );
      case InterfaceStyle.liquidGlass:
        final tint = glass.tintColor(theme);
        final primaryGlow = (tint ?? scheme.primary).withValues(
          alpha: light ? 0.10 : 0.13,
        );
        final secondaryGlow = (tint ?? scheme.secondary).withValues(
          alpha: light ? 0.06 : 0.08,
        );
        return _GlowDecoration(
          base: base,
          toneTop: Color.alphaBlend(
            (light ? Colors.white : Colors.black).withValues(alpha: 0.06),
            base,
          ),
          primaryGlow: primaryGlow,
          secondaryGlow: secondaryGlow,
        );
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return RepaintBoundary(
      child: DecoratedBox(
        decoration: decorationFor(theme),
        child: child ?? const SizedBox.expand(),
      ),
    );
  }
}

/// Brightness helper shared with [GlassBackdrop].
abstract final class ChromeSurfaceLuminance {
  static bool isLight(ThemeData theme) =>
      theme.brightness == Brightness.light ||
      theme.colorScheme.surface.computeLuminance() > 0.45;
}

class _GlowDecoration extends Decoration {
  const _GlowDecoration({
    required this.base,
    required this.toneTop,
    required this.primaryGlow,
    required this.secondaryGlow,
  });

  final Color base;
  final Color toneTop;
  final Color primaryGlow;
  final Color secondaryGlow;

  @override
  BoxPainter createBoxPainter([VoidCallback? onChanged]) => _GlowPainter(this);

  @override
  bool operator ==(Object other) =>
      other is _GlowDecoration &&
      other.base == base &&
      other.toneTop == toneTop &&
      other.primaryGlow == primaryGlow &&
      other.secondaryGlow == secondaryGlow;

  @override
  int get hashCode => Object.hash(base, toneTop, primaryGlow, secondaryGlow);
}

class _GlowPainter extends BoxPainter {
  _GlowPainter(this.decoration);
  final _GlowDecoration decoration;

  @override
  void paint(Canvas canvas, Offset offset, ImageConfiguration configuration) {
    final size = configuration.size ?? Size.zero;
    if (size.isEmpty) return;
    final rect = offset & size;
    canvas.drawRect(
      rect,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: [decoration.toneTop, decoration.base],
        ).createShader(rect),
    );
    final glowRadius = size.longestSide * 0.75;
    canvas.drawRect(
      rect,
      Paint()
        ..shader = RadialGradient(
          center: const Alignment(-0.85, -0.9),
          radius: glowRadius / size.shortestSide,
          colors: [
            decoration.primaryGlow,
            decoration.primaryGlow.withValues(alpha: 0),
          ],
        ).createShader(rect),
    );
    canvas.drawRect(
      rect,
      Paint()
        ..shader = RadialGradient(
          center: const Alignment(0.9, 1.0),
          radius: glowRadius / size.shortestSide,
          colors: [
            decoration.secondaryGlow,
            decoration.secondaryGlow.withValues(alpha: 0),
          ],
        ).createShader(rect),
    );
  }
}

/// Wraps a pushed page so its Scaffold paints over the glass backdrop: the
/// scaffold colour becomes transparent inside, the backdrop is painted once
/// below, and the app bar (transparent by theme) floats on it.
class GlassPageScope extends StatelessWidget {
  const GlassPageScope({super.key, required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Stack(
      fit: StackFit.expand,
      children: [
        const Positioned.fill(child: GlassBackdrop()),
        Theme(
          data: theme.copyWith(scaffoldBackgroundColor: Colors.transparent),
          child: child,
        ),
      ],
    );
  }
}
