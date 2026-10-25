import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../../../../widgets/glass/glass_surface.dart';

/// Circular accent badge used as the trailing control on actionable settings
/// card rows (add ROM folder, rescan, edit, ES-DE import, etc.). The row
/// itself handles the tap.
///
/// Brightens while its owning row is selected and switches to the theme's
/// error colour for destructive actions (remove folder, reset import). Its
/// shadow follows the interface depth setting.
class SettingsActionButton extends StatelessWidget {
  /// Glyph shown inside the button.
  final IconData icon;

  /// Whether the owning row currently holds gamepad focus.
  final bool selected;

  /// Renders in the error colour instead of primary for destructive actions.
  final bool isDestructive;

  const SettingsActionButton({
    super.key,
    required this.icon,
    required this.selected,
    this.isDestructive = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final color = isDestructive
        ? theme.colorScheme.error
        : theme.colorScheme.primary;
    final depth = glass.depthScale;

    return Container(
      padding: EdgeInsets.all(4.r),
      decoration: BoxDecoration(
        color: color.withValues(alpha: selected ? 1.0 : 0.8),
        shape: BoxShape.circle,
        boxShadow: depth <= 0
            ? null
            : [
                BoxShadow(
                  color: color.withValues(alpha: (0.3 * depth).clamp(0, 0.5)),
                  blurRadius: 4.r,
                  offset: Offset(0, 2.r),
                ),
              ],
      ),
      child: Icon(
        icon,
        color: isDestructive
            ? theme.colorScheme.onError
            : theme.colorScheme.onPrimary,
        size: 16.r,
      ),
    );
  }
}
