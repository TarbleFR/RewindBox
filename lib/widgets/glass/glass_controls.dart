import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../../services/sfx_service.dart';
import 'glass_surface.dart';

/// One option of a [GlassSegmentedControl].
class GlassSegment<T> {
  const GlassSegment({required this.value, required this.label, this.icon});
  final T value;
  final String label;
  final IconData? icon;
}

/// Pill track with a sliding glass thumb under the selected option.
class GlassSegmentedControl<T> extends StatelessWidget {
  const GlassSegmentedControl({
    super.key,
    required this.segments,
    required this.value,
    required this.onChanged,
    this.focused = false,
    this.dense = false,
  });

  final List<GlassSegment<T>> segments;
  final T value;
  final ValueChanged<T>? onChanged;
  final bool focused;
  final bool dense;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final index = segments
        .indexWhere((s) => s.value == value)
        .clamp(0, segments.length - 1);
    final duration = glass.duration(context, GlassMotion.standard);
    final height = dense ? 24.r : 28.r;
    return GlassSurface(
      role: GlassRole.control,
      radiusSize: GlassRadius.pill,
      focused: focused,
      blur: false,
      padding: EdgeInsets.all(2.r),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final count = segments.length;
          final width = constraints.maxWidth.isFinite
              ? constraints.maxWidth / count
              : null;
          Widget cell(GlassSegment<T> segment, bool selected) => SizedBox(
            width: width,
            height: height,
            child: InkWell(
              onTap: onChanged == null
                  ? null
                  : () {
                      if (segment.value != value) {
                        SfxService().playNavSound();
                        onChanged!(segment.value);
                      }
                    },
              canRequestFocus: false,
              focusColor: Colors.transparent,
              hoverColor: Colors.transparent,
              highlightColor: Colors.transparent,
              splashColor: Colors.transparent,
              borderRadius: BorderRadius.circular(999),
              child: Semantics(
                button: true,
                selected: selected,
                label: segment.label,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  mainAxisSize: width == null
                      ? MainAxisSize.min
                      : MainAxisSize.max,
                  children: [
                    if (segment.icon != null) ...[
                      Icon(
                        segment.icon,
                        size: dense ? 11.r : 13.r,
                        color: selected
                            ? theme.colorScheme.primary
                            : theme.colorScheme.onSurface.withValues(
                                alpha: 0.75,
                              ),
                      ),
                      SizedBox(width: 4.r),
                    ],
                    Flexible(
                      child: Padding(
                        padding: EdgeInsets.symmetric(
                          horizontal: width == null ? 10.r : 4.r,
                        ),
                        child: Text(
                          segment.label,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: dense ? 9.r : 10.r,
                            fontWeight: selected
                                ? FontWeight.w600
                                : FontWeight.w500,
                            color: selected
                                ? theme.colorScheme.primary
                                : theme.colorScheme.onSurface.withValues(
                                    alpha: 0.75,
                                  ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          );
          return Material(
            color: Colors.transparent,
            child: Stack(
              children: [
                if (width != null)
                  AnimatedPositioned(
                    key: const ValueKey('glass-segment-thumb'),
                    duration: duration,
                    curve: Curves.easeOutCubic,
                    left: width * index,
                    top: 0,
                    width: width,
                    height: height,
                    child: const _SegmentThumb(),
                  ),
                Row(
                  mainAxisSize: width == null
                      ? MainAxisSize.min
                      : MainAxisSize.max,
                  children: [
                    for (var i = 0; i < count; i++)
                      width == null && i == index
                          ? Stack(
                              children: [
                                const Positioned.fill(child: _SegmentThumb()),
                                cell(segments[i], true),
                              ],
                            )
                          : cell(segments[i], i == index),
                  ],
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

class _SegmentThumb extends StatelessWidget {
  const _SegmentThumb();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(999),
        color: Color.alphaBlend(
          theme.colorScheme.primary.withValues(alpha: 0.16),
          glass.fill(context, GlassRole.pill),
        ),
        border: Border.all(
          color: theme.colorScheme.primary.withValues(alpha: 0.45),
          width: 0.8,
        ),
        boxShadow: glass.shadows(context, GlassShadow.low),
      ),
    );
  }
}

/// Slider on a glass pill track. Values are fractions 0..1; the optional
/// [valueLabel] is drawn at the trailing edge.
class GlassSlider extends StatelessWidget {
  const GlassSlider({
    super.key,
    required this.value,
    required this.onChanged,
    this.onChangeEnd,
    this.focused = false,
    this.divisions,
    this.valueLabel,
    this.semanticLabel,
    this.min = 0,
    this.max = 1,
  });

  final double value;
  final ValueChanged<double>? onChanged;
  final ValueChanged<double>? onChangeEnd;
  final bool focused;
  final int? divisions;
  final String? valueLabel;
  final String? semanticLabel;
  final double min;
  final double max;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Row(
      children: [
        Expanded(
          child: GlassSurface(
            role: GlassRole.control,
            radiusSize: GlassRadius.pill,
            focused: focused,
            blur: false,
            padding: EdgeInsets.symmetric(horizontal: 4.r),
            height: 22.r,
            child: SliderTheme(
              data: theme.sliderTheme.copyWith(
                trackHeight: 5.r,
                overlayShape: SliderComponentShape.noOverlay,
                thumbShape: RoundSliderThumbShape(enabledThumbRadius: 7.r),
                activeTrackColor: theme.colorScheme.primary,
                inactiveTrackColor: theme.colorScheme.onSurface.withValues(
                  alpha: 0.14,
                ),
                thumbColor: theme.colorScheme.primary,
                trackShape: const _InsetTrackShape(),
              ),
              child: Slider(
                value: value.clamp(min, max).toDouble(),
                min: min,
                max: max,
                divisions: divisions,
                label: valueLabel,
                semanticFormatterCallback: semanticLabel == null
                    ? null
                    : (v) => '$semanticLabel ${(v * 100).round()} %',
                onChanged: onChanged,
                onChangeEnd: onChangeEnd,
              ),
            ),
          ),
        ),
        if (valueLabel != null) ...[
          SizedBox(width: 8.r),
          SizedBox(
            width: 34.r,
            child: Text(
              valueLabel!,
              textAlign: TextAlign.right,
              style: TextStyle(
                fontSize: 9.r,
                fontWeight: FontWeight.w600,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
              ),
            ),
          ),
        ],
      ],
    );
  }
}

class _InsetTrackShape extends RoundedRectSliderTrackShape {
  const _InsetTrackShape();

  @override
  Rect getPreferredRect({
    required RenderBox parentBox,
    Offset offset = Offset.zero,
    required SliderThemeData sliderTheme,
    bool isEnabled = false,
    bool isDiscrete = false,
  }) {
    final height = sliderTheme.trackHeight ?? 4;
    final inset =
        (sliderTheme.thumbShape?.getPreferredSize(true, false).width ?? 14) / 2;
    return Rect.fromLTWH(
      offset.dx + inset,
      offset.dy + (parentBox.size.height - height) / 2,
      parentBox.size.width - inset * 2,
      height,
    );
  }
}

/// Compact glass pill showing a value or a filter.
class GlassChip extends StatelessWidget {
  const GlassChip({
    super.key,
    required this.label,
    this.icon,
    this.trailingIcon,
    this.selected = false,
    this.accent = true,
    this.onTap,
    this.focused = false,
  });

  final String label;
  final IconData? icon;
  final IconData? trailingIcon;
  final bool selected;

  /// Accent-tinted (value chips) rather than neutral (filters).
  final bool accent;
  final VoidCallback? onTap;
  final bool focused;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final color = accent || selected
        ? theme.colorScheme.primary
        : theme.colorScheme.onSurface;
    final chip = GlassSurface(
      role: GlassRole.pill,
      radiusSize: GlassRadius.pill,
      blur: false,
      focused: focused,
      fillColor: accent || selected
          ? Color.alphaBlend(
              theme.colorScheme.primary.withValues(
                alpha: selected ? 0.22 : 0.15,
              ),
              glass.fill(context, GlassRole.pill),
            )
          : null,
      rimColor: accent || selected
          ? theme.colorScheme.primary.withValues(alpha: 0.4)
          : null,
      borderWidth: 0.6,
      padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 5.r),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (icon != null) ...[
            Icon(icon, size: 12.r, color: color),
            SizedBox(width: 4.r),
          ],
          Flexible(
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 9.r,
                fontWeight: FontWeight.w500,
                color: color,
              ),
            ),
          ),
          if (trailingIcon != null) ...[
            SizedBox(width: 2.r),
            Icon(trailingIcon, size: 14.r, color: color),
          ],
        ],
      ),
    );
    if (onTap == null) return chip;
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        canRequestFocus: false,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        splashColor: Colors.transparent,
        borderRadius: BorderRadius.circular(999),
        child: chip,
      ),
    );
  }
}
