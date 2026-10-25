import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import 'glass_surface.dart';

/// Bottom sheet panel on glass: rounded top corners, a drag handle, the
/// bottom safe area reserved.
class GlassSheet extends StatelessWidget {
  const GlassSheet({
    super.key,
    required this.child,
    this.title,
    this.padding,
    this.showHandle = true,
    this.maxHeightFraction = 0.9,
  });

  final Widget child;
  final String? title;
  final EdgeInsetsGeometry? padding;
  final bool showHandle;
  final double maxHeightFraction;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final bottom = MediaQuery.viewPaddingOf(context).bottom;
    final top = glass.radiusValue(GlassRadius.xl);
    return SafeArea(
      top: false,
      bottom: false,
      child: ConstrainedBox(
        constraints: BoxConstraints(
          maxHeight: MediaQuery.sizeOf(context).height * maxHeightFraction,
        ),
        child: GlassSurface(
          role: GlassRole.modal,
          shadow: GlassShadow.high,
          radius: BorderRadius.vertical(top: Radius.circular(top)),
          padding: EdgeInsets.only(
            left: glass.margin,
            right: glass.margin,
            top: showHandle ? 6.r : glass.gap,
            bottom: glass.gap + bottom,
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (showHandle)
                Center(
                  child: Container(
                    width: 32.r,
                    height: 4.r,
                    margin: EdgeInsets.only(bottom: glass.gap * 0.7),
                    decoration: BoxDecoration(
                      color: theme.colorScheme.onSurface.withValues(
                        alpha: 0.35,
                      ),
                      borderRadius: BorderRadius.circular(2.r),
                    ),
                  ),
                ),
              if (title != null)
                Padding(
                  padding: EdgeInsets.only(bottom: glass.gap * 0.8),
                  child: Text(
                    title!,
                    style: theme.textTheme.titleMedium?.copyWith(
                      fontSize: 14.r,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              Flexible(
                child: padding == null
                    ? child
                    : Padding(padding: padding!, child: child),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Shows a glass bottom sheet; the Material sheet stays transparent so the
/// only surface is the glass panel.
Future<T?> showGlassSheet<T>(
  BuildContext context, {
  required WidgetBuilder builder,
  String? title,
  bool isScrollControlled = true,
  bool isDismissible = true,
  bool enableDrag = true,
  bool useRootNavigator = true,
}) {
  return showModalBottomSheet<T>(
    context: context,
    backgroundColor: Colors.transparent,
    elevation: 0,
    showDragHandle: false,
    isScrollControlled: isScrollControlled,
    isDismissible: isDismissible,
    enableDrag: enableDrag,
    useRootNavigator: useRootNavigator,
    barrierColor: Theme.of(context).bottomSheetTheme.modalBarrierColor,
    builder: (context) => GlassSheet(title: title, child: builder(context)),
  );
}
