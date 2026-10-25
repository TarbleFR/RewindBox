import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/services/sfx_service.dart';

import 'glass/glass_surface.dart';

/// Radio option drawn as a glass bubble: title, optional subtitle and a
/// round indicator. Gamepad focus draws the accent ring.
class CustomRadioButton<T> extends StatelessWidget {
  final T value;
  final T groupValue;
  final ValueChanged<T?> onChanged;
  final String title;
  final String? subtitle;
  final bool isFocused;

  const CustomRadioButton({
    super.key,
    required this.value,
    required this.groupValue,
    required this.onChanged,
    required this.title,
    this.subtitle,
    this.isFocused = false,
  });

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final isSelected = value == groupValue;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        canRequestFocus: false,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        splashColor: Colors.transparent,
        onTap: () {
          SfxService().playNavSound();
          onChanged(value);
        },
        borderRadius: glass.radius(GlassRadius.m),
        child: GlassSurface(
          role: GlassRole.bubble,
          focused: isFocused,
          selected: isSelected,
          padding: glass.bubblePadding,
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Text(
                      title,
                      style: theme.textTheme.bodyLarge?.copyWith(
                        fontWeight: FontWeight.w500,
                        fontSize: 12.r,
                        color: isFocused
                            ? theme.colorScheme.primary
                            : theme.colorScheme.onSurface,
                      ),
                    ),
                    if (subtitle != null) ...[
                      SizedBox(height: 4.r),
                      Text(
                        subtitle!,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontSize: 9.r,
                          color: theme.colorScheme.onSurface.withValues(
                            alpha: 0.6,
                          ),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              SizedBox(width: 16.r),
              _buildCustomIndicator(context, isSelected, theme, glass),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCustomIndicator(
    BuildContext context,
    bool isSelected,
    ThemeData theme,
    LiquidGlassTheme glass,
  ) {
    return AnimatedContainer(
      duration: glass.duration(context, GlassMotion.standard),
      curve: Curves.easeOut,
      width: 24.r,
      height: 24.r,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(
          color: isSelected
              ? theme.colorScheme.primary
              : glass.rim(context, GlassRole.control),
          width: 2.0,
        ),
        color: isSelected
            ? theme.colorScheme.primary
            : glass.fill(context, GlassRole.control),
      ),
      child: isSelected
          ? Center(
              child: Container(
                width: 10.r,
                height: 10.r,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: theme.colorScheme.onPrimary,
                ),
              ),
            )
          : null,
    );
  }
}
