import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../themes/app_themes.dart';
import 'glass_surface.dart';

enum GlassBannerKind { neutral, info, success, warning, error }

/// Information, warning or error card on glass: an accent bar, a tinted
/// icon, a title and a message, with an optional trailing action.
class GlassBanner extends StatelessWidget {
  const GlassBanner({
    super.key,
    required this.message,
    this.title,
    this.icon,
    this.kind = GlassBannerKind.info,
    this.action,
    this.compact = false,
    this.margin,
  });

  final String message;
  final String? title;
  final IconData? icon;
  final GlassBannerKind kind;
  final Widget? action;
  final bool compact;
  final EdgeInsetsGeometry? margin;

  static Color accentFor(BuildContext context, GlassBannerKind kind) {
    final theme = Theme.of(context);
    final custom = AppThemes.getCustomColors(context);
    return switch (kind) {
      GlassBannerKind.neutral => theme.colorScheme.onSurface,
      GlassBannerKind.info => custom.infoColor as Color,
      GlassBannerKind.success => custom.successColor as Color,
      GlassBannerKind.warning => custom.warningColor as Color,
      GlassBannerKind.error => theme.colorScheme.error,
    };
  }

  static IconData iconFor(GlassBannerKind kind) => switch (kind) {
    GlassBannerKind.neutral => Symbols.notes_rounded,
    GlassBannerKind.info => Symbols.info_rounded,
    GlassBannerKind.success => Symbols.check_circle_rounded,
    GlassBannerKind.warning => Symbols.warning_rounded,
    GlassBannerKind.error => Symbols.error_rounded,
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final accent = accentFor(context, kind);
    return GlassSurface(
      role: GlassRole.banner,
      margin: margin,
      fillColor: Color.alphaBlend(
        accent.withValues(alpha: kind == GlassBannerKind.neutral ? 0.04 : 0.09),
        glass.fill(context, GlassRole.banner),
      ),
      rimColor: accent.withValues(alpha: 0.35),
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 10.r : 12.r,
        vertical: compact ? 7.r : 10.r,
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Container(
            width: 3.r,
            height: compact ? 18.r : 26.r,
            decoration: BoxDecoration(
              color: accent,
              borderRadius: BorderRadius.circular(2.r),
            ),
          ),
          SizedBox(width: 10.r),
          Icon(
            icon ?? iconFor(kind),
            color: accent,
            size: compact ? 16.r : 20.r,
          ),
          SizedBox(width: 10.r),
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (title != null)
                  Text(
                    title!,
                    style: theme.textTheme.titleSmall?.copyWith(
                      fontSize: compact ? 10.r : 11.r,
                      fontWeight: FontWeight.w600,
                      color: accent,
                    ),
                  ),
                if (title != null) SizedBox(height: 2.r),
                Text(
                  message,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontSize: compact ? 8.5.r : 9.5.r,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.82),
                  ),
                ),
              ],
            ),
          ),
          if (action != null) ...[SizedBox(width: 10.r), action!],
        ],
      ),
    );
  }
}
