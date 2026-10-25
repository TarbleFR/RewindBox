import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'glass_surface.dart';

/// Modal glass panel: an optional icon/title header, scrollable content and
/// an actions row. Pass [child] to lay the whole panel out yourself.
///
/// The dialog itself is transparent; the glass is on the panel, never on the
/// whole screen behind it.
class GlassDialog extends StatelessWidget {
  const GlassDialog({
    super.key,
    this.title,
    this.titleWidget,
    this.icon,
    this.accentColor,
    this.content,
    this.actions,
    this.child,
    this.maxWidth,
    this.maxHeight,
    this.padding,
    this.insetPadding,
    this.scrollable = true,
    this.actionsAlignment = MainAxisAlignment.end,
  }) : assert(child == null || (content == null && actions == null));

  final String? title;
  final Widget? titleWidget;
  final IconData? icon;

  /// Colour of the icon and title; defaults to the primary colour.
  final Color? accentColor;
  final Widget? content;
  final List<Widget>? actions;
  final Widget? child;
  final double? maxWidth;
  final double? maxHeight;
  final EdgeInsetsGeometry? padding;
  final EdgeInsets? insetPadding;
  final bool scrollable;
  final MainAxisAlignment actionsAlignment;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final accent = accentColor ?? theme.colorScheme.primary;
    final body =
        child ??
        Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (title != null || titleWidget != null)
              Padding(
                padding: EdgeInsets.only(bottom: glass.gap * 0.8),
                child: Row(
                  children: [
                    if (icon != null) ...[
                      Icon(icon, color: accent, size: 20.r),
                      SizedBox(width: 8.r),
                    ],
                    Expanded(
                      child:
                          titleWidget ??
                          Text(
                            title!,
                            style: theme.textTheme.titleMedium?.copyWith(
                              fontSize: 14.r,
                              color: accent,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                    ),
                  ],
                ),
              ),
            if (content != null)
              Flexible(
                child: scrollable
                    ? SingleChildScrollView(child: content)
                    : content!,
              ),
            if (actions != null && actions!.isNotEmpty)
              Padding(
                padding: EdgeInsets.only(top: glass.gap),
                child: Wrap(
                  alignment: WrapAlignment.end,
                  spacing: 8.r,
                  runSpacing: 6.r,
                  children: actions!,
                ),
              ),
          ],
        );
    return Dialog(
      backgroundColor: Colors.transparent,
      surfaceTintColor: Colors.transparent,
      elevation: 0,
      insetPadding:
          insetPadding ??
          EdgeInsets.symmetric(horizontal: 24.r, vertical: 16.r),
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: maxWidth ?? 440.r,
          maxHeight: maxHeight ?? 440.r,
        ),
        child: GlassSurface(
          role: GlassRole.modal,
          shadow: GlassShadow.high,
          padding: padding ?? glass.modalPadding,
          child: body,
        ),
      ),
    );
  }
}

/// Shows [builder]'s widget as a glass modal. Prefer this over a bare
/// `showDialog` so the barrier colour and route transition stay uniform.
Future<T?> showGlassDialog<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  bool barrierDismissible = true,
  bool useRootNavigator = true,
  RouteSettings? routeSettings,
}) {
  return showDialog<T>(
    context: context,
    barrierDismissible: barrierDismissible,
    useRootNavigator: useRootNavigator,
    routeSettings: routeSettings,
    barrierColor: Theme.of(context).dialogTheme.barrierColor,
    builder: builder,
  );
}
