import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../../services/sfx_service.dart';
import 'glass_surface.dart';

enum GlassButtonVariant {
  /// Filled with the accent colour: the one confirming action of a surface.
  primary,

  /// Accent tint on glass: secondary actions.
  tonal,

  /// Neutral glass: tertiary actions, toolbars.
  glass,

  /// Filled with the error colour.
  destructive,

  /// No surface at all: cancel/back links.
  ghost,
}

enum GlassButtonSize { small, medium }

/// Sound a [GlassButton] plays when tapped.
enum GlassButtonSound { enter, back, nav, none }

/// Button on the glass system with a gentle press compression. The visual
/// states (enabled, pressed, focused, disabled) are shared by every variant.
class GlassButton extends StatefulWidget {
  const GlassButton({
    super.key,
    required this.onPressed,
    this.label,
    this.icon,
    this.child,
    this.variant = GlassButtonVariant.tonal,
    this.size = GlassButtonSize.medium,
    this.sound = GlassButtonSound.nav,
    this.focused = false,
    this.expanded = false,
    this.semanticLabel,
    this.tooltip,
  }) : assert(label != null || icon != null || child != null);

  final VoidCallback? onPressed;
  final String? label;
  final IconData? icon;
  final Widget? child;
  final GlassButtonVariant variant;
  final GlassButtonSize size;
  final GlassButtonSound sound;

  /// Gamepad focus ring.
  final bool focused;

  /// Stretches to the available width.
  final bool expanded;
  final String? semanticLabel;
  final String? tooltip;

  @override
  State<GlassButton> createState() => _GlassButtonState();
}

class _GlassButtonState extends State<GlassButton> {
  bool _pressed = false;

  bool get _enabled => widget.onPressed != null;

  void _tap() {
    switch (widget.sound) {
      case GlassButtonSound.enter:
        SfxService().playEnterSound();
      case GlassButtonSound.back:
        SfxService().playBackSound();
      case GlassButtonSound.nav:
        SfxService().playNavSound();
      case GlassButtonSound.none:
        break;
    }
    widget.onPressed?.call();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final glass = LiquidGlassTheme.of(context);
    final small = widget.size == GlassButtonSize.small;

    final (
      Color? fill,
      Color foreground,
      Color? rim,
      GlassRole role,
    ) = switch (widget.variant) {
      GlassButtonVariant.primary => (
        scheme.primary,
        scheme.onPrimary,
        scheme.primary.withValues(alpha: 0.0),
        GlassRole.control,
      ),
      GlassButtonVariant.destructive => (
        scheme.error,
        scheme.onError,
        scheme.error.withValues(alpha: 0.0),
        GlassRole.control,
      ),
      GlassButtonVariant.tonal => (
        Color.alphaBlend(
          scheme.primary.withValues(alpha: 0.18),
          glass.fill(context, GlassRole.control),
        ),
        scheme.primary,
        scheme.primary.withValues(alpha: 0.40),
        GlassRole.control,
      ),
      GlassButtonVariant.glass => (
        null,
        scheme.onSurface,
        null,
        GlassRole.control,
      ),
      GlassButtonVariant.ghost => (
        Colors.transparent,
        scheme.onSurface.withValues(alpha: 0.75),
        Colors.transparent,
        GlassRole.control,
      ),
    };

    final textStyle = TextStyle(
      color: foreground,
      fontSize: small ? 10.r : 12.r,
      fontWeight: FontWeight.w600,
    );
    final content =
        widget.child ??
        Row(
          mainAxisSize: widget.expanded ? MainAxisSize.max : MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            if (widget.icon != null)
              Icon(widget.icon, size: small ? 14.r : 16.r, color: foreground),
            if (widget.icon != null && widget.label != null)
              SizedBox(width: 6.r),
            if (widget.label != null)
              Flexible(
                child: Text(
                  widget.label!,
                  style: textStyle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
          ],
        );

    final motion = glass.motionEnabled(context);
    Widget button = AnimatedScale(
      scale: _pressed && motion ? 0.96 : 1,
      duration: glass.duration(context, GlassMotion.quick),
      curve: Curves.easeOutCubic,
      child: Opacity(
        opacity: _enabled ? 1 : 0.45,
        child: GlassSurface(
          role: role,
          radiusSize: GlassRadius.m,
          fillColor: fill,
          rimColor: rim,
          focused: widget.focused,
          pressed: _pressed && widget.variant == GlassButtonVariant.glass,
          blur: false,
          showSheen: widget.variant == GlassButtonVariant.glass,
          padding: EdgeInsets.symmetric(
            horizontal: small ? 10.r : 14.r,
            vertical: small ? 6.r : 8.r,
          ),
          child: DefaultTextStyle(
            style: textStyle,
            child: IconTheme(
              data: IconThemeData(color: foreground, size: 16.r),
              child: content,
            ),
          ),
        ),
      ),
    );

    button = Semantics(
      button: true,
      enabled: _enabled,
      label: widget.semanticLabel ?? widget.label,
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: _enabled ? _tap : null,
          onHighlightChanged: (value) {
            if (_pressed != value) setState(() => _pressed = value);
          },
          canRequestFocus: false,
          focusColor: Colors.transparent,
          hoverColor: Colors.transparent,
          highlightColor: Colors.transparent,
          splashColor: Colors.transparent,
          borderRadius: glass.radius(GlassRadius.m),
          child: button,
        ),
      ),
    );
    if (widget.tooltip != null) {
      button = Tooltip(message: widget.tooltip!, child: button);
    }
    return button;
  }
}

/// Round glass icon button (toolbar actions, close, delete).
class GlassIconButton extends StatelessWidget {
  const GlassIconButton({
    super.key,
    required this.icon,
    required this.onPressed,
    this.tooltip,
    this.size,
    this.variant = GlassButtonVariant.glass,
    this.focused = false,
    this.sound = GlassButtonSound.nav,
  });

  final IconData icon;
  final VoidCallback? onPressed;
  final String? tooltip;
  final double? size;
  final GlassButtonVariant variant;
  final bool focused;
  final GlassButtonSound sound;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final glass = LiquidGlassTheme.of(context);
    final dimension = size ?? 28.r;
    final (Color? fill, Color foreground) = switch (variant) {
      GlassButtonVariant.primary => (scheme.primary, scheme.onPrimary),
      GlassButtonVariant.destructive => (scheme.error, scheme.onError),
      GlassButtonVariant.tonal => (
        Color.alphaBlend(
          scheme.primary.withValues(alpha: 0.18),
          glass.fill(context, GlassRole.control),
        ),
        scheme.primary,
      ),
      GlassButtonVariant.glass => (null, scheme.onSurface),
      GlassButtonVariant.ghost => (Colors.transparent, scheme.onSurface),
    };
    Widget button = Semantics(
      button: true,
      enabled: onPressed != null,
      label: tooltip,
      child: Material(
        color: Colors.transparent,
        shape: const CircleBorder(),
        clipBehavior: Clip.antiAlias,
        child: InkWell(
          onTap: onPressed == null
              ? null
              : () {
                  switch (sound) {
                    case GlassButtonSound.enter:
                      SfxService().playEnterSound();
                    case GlassButtonSound.back:
                      SfxService().playBackSound();
                    case GlassButtonSound.nav:
                      SfxService().playNavSound();
                    case GlassButtonSound.none:
                      break;
                  }
                  onPressed!();
                },
          canRequestFocus: false,
          focusColor: Colors.transparent,
          hoverColor: Colors.transparent,
          highlightColor: Colors.transparent,
          splashColor: Colors.transparent,
          child: Opacity(
            opacity: onPressed == null ? 0.45 : 1,
            child: GlassSurface(
              role: GlassRole.control,
              radius: BorderRadius.circular(dimension),
              fillColor: fill,
              rimColor: fill == null ? null : Colors.transparent,
              focused: focused,
              blur: false,
              showSheen: fill == null,
              width: dimension,
              height: dimension,
              alignment: Alignment.center,
              child: Icon(icon, size: dimension * 0.55, color: foreground),
            ),
          ),
        ),
      ),
    );
    if (tooltip != null) button = Tooltip(message: tooltip!, child: button);
    return button;
  }
}
