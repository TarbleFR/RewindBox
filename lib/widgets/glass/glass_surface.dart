import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../../themes/liquid_glass_theme.dart';

export '../../themes/liquid_glass_theme.dart';

/// The one translucent surface every panel, bubble, dialog, sheet, menu,
/// chip and control of RewindBox is built from.
///
/// Fill, blur, rim, sheen, radius and shadow come from [LiquidGlassTheme],
/// so the user's interface style and the runtime performance budget reach
/// every surface at once. One optional BackdropFilter per surface; dense
/// collections (cards, rails) default to the zero-blur path.
class GlassSurface extends StatelessWidget {
  const GlassSurface({
    super.key,
    required this.child,
    this.role = GlassRole.panel,
    this.radius,
    this.radiusSize,
    this.padding,
    this.margin,
    this.shadow,
    this.blur,
    this.focused = false,
    this.selected = false,
    this.pressed = false,
    this.rimColor,
    this.fillColor,
    this.gradient,
    this.showSheen,
    this.borderWidth,
    this.width,
    this.height,
    this.constraints,
    this.alignment,
  });

  final Widget child;
  final GlassRole role;

  /// Explicit corners; otherwise [radiusSize] or the role's default size.
  final BorderRadius? radius;
  final GlassRadius? radiusSize;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;

  /// Shadow level; null picks the role's default.
  final GlassShadow? shadow;

  /// Forces the backdrop blur on or off; null picks the role's default.
  final bool? blur;

  /// Gamepad focus: a 2 px accent ring replaces the rim.
  final bool focused;

  /// Selected state: the fill takes a light accent tint.
  final bool selected;

  /// Pressed state: slightly darker fill.
  final bool pressed;
  final Color? rimColor;
  final Color? fillColor;
  final Gradient? gradient;
  final bool? showSheen;
  final double? borderWidth;
  final double? width;
  final double? height;
  final BoxConstraints? constraints;
  final AlignmentGeometry? alignment;

  static GlassRadius defaultRadius(GlassRole role) => switch (role) {
    GlassRole.modal => GlassRadius.l,
    GlassRole.pill => GlassRadius.pill,
    GlassRole.control => GlassRadius.s,
    GlassRole.menu => GlassRadius.m,
    GlassRole.chrome => GlassRadius.m,
    GlassRole.card => GlassRadius.m,
    GlassRole.bubble => GlassRadius.m,
    GlassRole.banner => GlassRadius.m,
    GlassRole.panel => GlassRadius.m,
    GlassRole.rail => GlassRadius.m,
  };

  static GlassShadow defaultShadow(GlassRole role) => switch (role) {
    GlassRole.modal => GlassShadow.high,
    GlassRole.menu => GlassShadow.high,
    GlassRole.chrome => GlassShadow.low,
    GlassRole.banner => GlassShadow.low,
    _ => GlassShadow.none,
  };

  /// Large or numerous surfaces skip the blur pass by default.
  static bool defaultBlur(GlassRole role) => switch (role) {
    GlassRole.card => false,
    GlassRole.rail => false,
    GlassRole.panel => false,
    _ => true,
  };

  @override
  Widget build(BuildContext context) {
    final glass = LiquidGlassTheme.of(context);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final borderRadius =
        radius ?? glass.radius(radiusSize ?? defaultRadius(role));
    final sigma = (blur ?? defaultBlur(role)) ? glass.blur(context, role) : 0.0;

    var fill = fillColor ?? glass.fill(context, role);
    if (selected) {
      fill = Color.alphaBlend(scheme.primary.withValues(alpha: 0.14), fill);
    }
    if (pressed) {
      fill = Color.alphaBlend(scheme.shadow.withValues(alpha: 0.10), fill);
    }
    // Gamepad focus: the accent ring, the accent halo or both, as chosen in
    // Settings › Themes › User interface.
    final ring = focused && glass.focusDrawsRing;
    final rim = ring
        ? glass.focusRing(context)
        : (rimColor ?? glass.rim(context, role));
    final rimWidth = ring ? 2.0 : (borderWidth ?? 1.0);
    final sheen = (showSheen ?? role != GlassRole.card)
        ? glass.sheen(context, role)
        : null;

    Widget content = child;
    if (padding != null) content = Padding(padding: padding!, child: content);
    if (alignment != null) {
      content = Align(alignment: alignment!, child: content);
    }

    final decorated = DecoratedBox(
      decoration: BoxDecoration(
        color: gradient == null ? fill : null,
        gradient: gradient,
        borderRadius: borderRadius,
        border: Border.all(color: rim, width: rimWidth),
      ),
      child: sheen == null
          ? content
          : Stack(
              fit: StackFit.passthrough,
              children: [
                Positioned.fill(
                  child: IgnorePointer(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: sheen,
                        borderRadius: borderRadius,
                      ),
                    ),
                  ),
                ),
                content,
              ],
            ),
    );

    Widget surface = ClipRRect(
      borderRadius: borderRadius,
      child: sigma > 0
          ? BackdropFilter(
              filter: ui.ImageFilter.blur(sigmaX: sigma, sigmaY: sigma),
              child: decorated,
            )
          : decorated,
    );

    final shadows = [
      ...glass.shadows(context, shadow ?? defaultShadow(role)),
      if (focused) ...glass.focusGlow(context),
    ];
    if (shadows.isNotEmpty) {
      surface = DecoratedBox(
        decoration: BoxDecoration(
          borderRadius: borderRadius,
          boxShadow: shadows,
        ),
        child: surface,
      );
    }

    if (width != null || height != null || constraints != null) {
      surface = ConstrainedBox(
        constraints: (constraints ?? const BoxConstraints()).tighten(
          width: width,
          height: height,
        ),
        child: surface,
      );
    }
    if (margin != null) surface = Padding(padding: margin!, child: surface);
    return surface;
  }
}

/// Vertical space between two independent glass bubbles.
class GlassGap extends StatelessWidget {
  const GlassGap({super.key, this.factor = 1});

  /// `1` is the standard bubble gap, `1.8` the gap between two categories.
  final double factor;

  const GlassGap.section({super.key}) : factor = 1.8;

  @override
  Widget build(BuildContext context) =>
      SizedBox(height: LiquidGlassTheme.of(context).gap * factor);
}

/// Horizontal page margins of a glass layout.
class GlassMargins extends StatelessWidget {
  const GlassMargins({super.key, required this.child, this.vertical = 0});
  final Widget child;
  final double vertical;

  @override
  Widget build(BuildContext context) => Padding(
    padding: EdgeInsets.symmetric(
      horizontal: LiquidGlassTheme.of(context).margin,
      vertical: vertical,
    ),
    child: child,
  );
}

/// Several rows that deliberately share one surface, separated by hairline
/// dividers. Their hierarchy stays visible: the group has one rim, the rows
/// no rim of their own.
class GlassGroup extends StatelessWidget {
  const GlassGroup({
    super.key,
    required this.children,
    this.role = GlassRole.bubble,
    this.dividers = true,
    this.padding,
    this.margin,
    this.radius,
  });

  final List<Widget> children;
  final GlassRole role;
  final bool dividers;
  final EdgeInsetsGeometry? padding;
  final EdgeInsetsGeometry? margin;
  final BorderRadius? radius;

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0 && dividers) {
        rows.add(
          Divider(
            height: 1,
            indent: LiquidGlassTheme.of(context).bubblePadding.horizontal / 2,
            endIndent:
                LiquidGlassTheme.of(context).bubblePadding.horizontal / 2,
          ),
        );
      }
      rows.add(children[i]);
    }
    return GlassSurface(
      role: role,
      radius: radius,
      padding: padding,
      margin: margin,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: rows,
      ),
    );
  }
}

/// Section heading: a short accent bar and an uppercase-weight label, with
/// the category spacing above it.
class GlassSectionHeader extends StatelessWidget {
  const GlassSectionHeader({
    super.key,
    required this.label,
    this.first = false,
    this.trailing,
  });

  final String label;

  /// The first header of a list has no category gap above it.
  final bool first;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    return Padding(
      padding: EdgeInsets.only(
        top: first ? 0 : glass.sectionGap - glass.gap,
        bottom: glass.gap * 0.6,
        left: 2.r,
      ),
      child: Row(
        children: [
          Container(
            width: 3.r,
            height: 14.r,
            decoration: BoxDecoration(
              color: theme.colorScheme.primary,
              borderRadius: BorderRadius.circular(2.r),
            ),
          ),
          SizedBox(width: 8.r),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11.r,
                fontWeight: FontWeight.bold,
                color: theme.colorScheme.primary,
                letterSpacing: 0.5,
              ),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ),
          ?trailing,
        ],
      ),
    );
  }
}
