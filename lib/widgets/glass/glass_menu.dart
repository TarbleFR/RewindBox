import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'glass_surface.dart';

/// Floating overlay container for dropdowns and context menus.
class GlassMenu extends StatelessWidget {
  const GlassMenu({
    super.key,
    required this.child,
    this.width,
    this.maxHeight,
    this.padding,
  });

  final Widget child;
  final double? width;
  final double? maxHeight;
  final EdgeInsetsGeometry? padding;

  @override
  Widget build(BuildContext context) => Material(
    color: Colors.transparent,
    child: ConstrainedBox(
      constraints: BoxConstraints(
        minWidth: width ?? 0,
        maxWidth: width ?? double.infinity,
        maxHeight: maxHeight ?? double.infinity,
      ),
      child: GlassSurface(
        role: GlassRole.menu,
        shadow: GlassShadow.high,
        padding: padding ?? EdgeInsets.symmetric(vertical: 6.r),
        child: child,
      ),
    ),
  );
}

/// One row of a [GlassMenu]: label, optional leading icon, selected check.
/// The highlight is the neutral selection material, not the accent colour.
class GlassMenuItem extends StatelessWidget {
  const GlassMenuItem({
    super.key,
    required this.label,
    this.icon,
    this.selected = false,
    this.focused = false,
    this.onTap,
    this.trailing,
    this.destructive = false,
  });

  final String label;
  final IconData? icon;
  final bool selected;
  final bool focused;
  final VoidCallback? onTap;
  final Widget? trailing;
  final bool destructive;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final color = destructive
        ? theme.colorScheme.error
        : selected
        ? theme.colorScheme.primary
        : theme.colorScheme.onSurface;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: 6.r, vertical: 1.r),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          canRequestFocus: false,
          focusColor: Colors.transparent,
          hoverColor: Colors.transparent,
          highlightColor: Colors.transparent,
          splashColor: Colors.transparent,
          borderRadius: glass.radius(GlassRadius.s),
          child: AnimatedContainer(
            duration: glass.duration(context, GlassMotion.quick),
            padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 6.r),
            decoration: BoxDecoration(
              color: focused
                  ? theme.colorScheme.onSurface.withValues(alpha: 0.10)
                  : Colors.transparent,
              borderRadius: glass.radius(GlassRadius.s),
              border: Border.all(
                color: focused
                    ? theme.colorScheme.onSurface.withValues(alpha: 0.28)
                    : Colors.transparent,
                width: 0.8,
              ),
            ),
            child: Row(
              children: [
                if (icon != null) ...[
                  Icon(icon, size: 14.r, color: color),
                  SizedBox(width: 8.r),
                ],
                Expanded(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: 10.r,
                      color: color,
                      fontWeight: selected ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ),
                if (trailing != null)
                  trailing!
                else if (selected)
                  Icon(Icons.check_rounded, size: 12.r, color: color),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
