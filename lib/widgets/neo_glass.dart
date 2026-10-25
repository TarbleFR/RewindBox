import 'package:flutter/material.dart';

import '../themes/chrome_surface.dart';
import 'glass/glass_surface.dart';

/// Lightweight theme-adaptive glass container.
///
/// Kept for the existing call sites; it is a thin facade over [GlassSurface],
/// so every NeoGlass panel follows the Liquid Glass tokens (interface style,
/// transparency, blur, rim, sheen and performance budget) at once.
class NeoGlass extends StatelessWidget {
  final Widget child;
  final BorderRadius borderRadius;
  final GlassSurfaceRole role;
  final Gradient? gradient;
  final EdgeInsetsGeometry? padding;
  final List<BoxShadow>? boxShadow;
  final double borderWidth;

  /// Disables the BackdropFilter for surfaces rendered many times at once
  /// (for example the systems grid). Transparency + rim still provide the
  /// glass appearance without forcing a separate blur pass per item.
  final bool enableBackdropBlur;

  /// The diagonal sheen is intentionally optional on dense grids. Large chrome
  /// surfaces keep it by default.
  final bool showSheen;

  const NeoGlass({
    super.key,
    required this.child,
    required this.borderRadius,
    this.role = GlassSurfaceRole.panel,
    this.gradient,
    this.padding,
    this.boxShadow,
    this.borderWidth = 1.0,
    this.enableBackdropBlur = true,
    this.showSheen = true,
  });

  static GlassRole roleOf(GlassSurfaceRole role) => switch (role) {
    GlassSurfaceRole.panel => GlassRole.panel,
    GlassSurfaceRole.rail => GlassRole.rail,
    GlassSurfaceRole.modal => GlassRole.modal,
    GlassSurfaceRole.chrome => GlassRole.chrome,
    GlassSurfaceRole.pill => GlassRole.pill,
    GlassSurfaceRole.card => GlassRole.card,
  };

  @override
  Widget build(BuildContext context) {
    final glass = GlassSurface(
      role: roleOf(role),
      radius: borderRadius,
      gradient: gradient,
      padding: padding,
      borderWidth: borderWidth,
      blur: enableBackdropBlur,
      showSheen: showSheen,
      // Callers that pass their own shadow keep it; the others get none, as
      // before.
      shadow: GlassShadow.none,
      child: child,
    );
    if (boxShadow == null || boxShadow!.isEmpty) return glass;
    final depth = LiquidGlassTheme.of(context).depthScale;
    if (depth <= 0) return glass;
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: borderRadius,
        boxShadow: [
          for (final shadow in boxShadow!)
            shadow.copyWith(
              color: shadow.color.withValues(
                alpha: (shadow.color.a * depth).clamp(0.0, 1.0),
              ),
            ),
        ],
      ),
      child: glass,
    );
  }
}
