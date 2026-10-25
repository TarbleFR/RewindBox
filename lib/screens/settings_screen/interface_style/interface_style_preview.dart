import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../../l10n/interface_style_locale.dart';
import '../../../services/sfx_service.dart';
import '../../../utils/nav_tabs.dart';
import '../../../widgets/custom_toggle_switch.dart';
import '../../../widgets/glass/glass.dart';
import '../../../widgets/main_menu_tab_strip.dart';
import '../new_settings_options/widgets/setting_row.dart';

/// Live sample drawn with the draft theme over a sample background: a
/// navigation bar, two settings bubbles, buttons, a menu and a notice. Every
/// piece is the production widget and every piece works: the tabs move the
/// indicator, the style chip and the menu switch the draft style, the switch
/// toggles the tab labels, and the buttons apply or undo the draft.
class InterfaceStylePreview extends StatefulWidget {
  const InterfaceStylePreview({
    super.key,
    required this.settings,
    this.compact = false,
    this.dirty = false,
    this.onChanged,
    this.onApply,
    this.onRevert,
  });

  final InterfaceStyleSettings settings;
  final bool compact;

  /// Whether the draft differs from the applied style.
  final bool dirty;
  final ValueChanged<InterfaceStyleSettings>? onChanged;
  final VoidCallback? onApply;
  final VoidCallback? onRevert;

  @override
  State<InterfaceStylePreview> createState() => _InterfaceStylePreviewState();
}

class _InterfaceStylePreviewState extends State<InterfaceStylePreview> {
  NavTab _selected = NavTab.systems;

  static const _tabs = [
    NavTab.systems,
    NavTab.consoles,
    NavTab.search,
    NavTab.library,
    NavTab.settings,
  ];

  static const _styleKeys = {
    InterfaceStyle.liquidGlass: InterfaceStyleLocale.styleLiquidGlass,
    InterfaceStyle.classic: InterfaceStyleLocale.styleClassic,
    InterfaceStyle.minimal: InterfaceStyleLocale.styleMinimal,
    InterfaceStyle.neoStation: InterfaceStyleLocale.styleNeoStation,
  };

  void _pickStyle(InterfaceStyle style) {
    if (style == widget.settings.style) return;
    widget.onChanged?.call(
      InterfaceStyleSettings.presetFor(style, keep: widget.settings),
    );
  }

  void _cycleStyle() {
    SfxService().playNavSound();
    const styles = InterfaceStyle.values;
    _pickStyle(
      styles[(styles.indexOf(widget.settings.style) + 1) % styles.length],
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    String t(String key) => InterfaceStyleLocale.text(context, key);
    final tint = theme.colorScheme.onSurface;
    final settings = widget.settings;

    final strip = Center(
      child: MainMenuTabStrip(
        key: const ValueKey('interface-style-preview-tabs'),
        tabs: _tabs,
        selected: _selected,
        cellExtent: widget.compact ? 22.r : 26.r,
        tabBuilder: (tab) => Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () {
              SfxService().playNavSound();
              setState(() => _selected = tab);
            },
            canRequestFocus: false,
            focusColor: Colors.transparent,
            hoverColor: Colors.transparent,
            highlightColor: Colors.transparent,
            splashColor: Colors.transparent,
            child: const SizedBox.expand(),
          ),
        ),
        iconBuilder: (tab) => NavTabIcon(spec: navTabSpec(tab), tint: tint),
        labelBuilder: (tab, selected) => Text(
          navTabLabel(context, tab),
          maxLines: 1,
          style: TextStyle(
            fontSize: 6.r,
            fontWeight: selected ? FontWeight.w700 : FontWeight.w500,
            color: tint.withValues(alpha: selected ? 1 : 0.72),
          ),
        ),
      ),
    );

    // The whole bubble is a target, not only its chip.
    final styleRow = GestureDetector(
      key: const ValueKey('interface-style-preview-style'),
      behavior: HitTestBehavior.opaque,
      onTap: _cycleStyle,
      child: SettingRow(
        title: t(InterfaceStyleLocale.sectionStyle),
        subtitle: t(InterfaceStyleLocale.previewTapHint),
        focused: false,
        trailing: GlassChip(
          key: const ValueKey('interface-style-preview-style-chip'),
          label: t(_styleKeys[settings.style]!),
          trailingIcon: Symbols.expand_more_rounded,
          onTap: _cycleStyle,
        ),
      ),
    );

    final labelsOn = settings.tabLabels != TabLabelMode.hidden;
    final labelsRow = SettingRow(
      title: t(InterfaceStyleLocale.tabLabels),
      subtitle: t(InterfaceStyleLocale.previewLabelsHint),
      focused: true,
      trailing: CustomToggleSwitch(
        key: const ValueKey('interface-style-preview-labels'),
        value: labelsOn,
        onChanged: (value) => widget.onChanged?.call(
          settings.copyWith(
            tabLabels: value ? TabLabelMode.always : TabLabelMode.hidden,
          ),
        ),
      ),
    );

    final buttons = Row(
      children: [
        Expanded(
          child: GlassButton(
            key: const ValueKey('interface-style-preview-apply'),
            label: t(InterfaceStyleLocale.apply),
            icon: Symbols.check_rounded,
            variant: GlassButtonVariant.primary,
            size: GlassButtonSize.small,
            expanded: true,
            sound: GlassButtonSound.enter,
            onPressed: widget.dirty ? widget.onApply : null,
          ),
        ),
        SizedBox(width: glass.gap * 0.6),
        Expanded(
          child: GlassButton(
            key: const ValueKey('interface-style-preview-revert'),
            label: t(InterfaceStyleLocale.revert),
            variant: GlassButtonVariant.tonal,
            size: GlassButtonSize.small,
            expanded: true,
            sound: GlassButtonSound.back,
            onPressed: widget.dirty ? widget.onRevert : null,
          ),
        ),
        SizedBox(width: glass.gap * 0.6),
        PopupMenuButton<InterfaceStyle>(
          key: const ValueKey('interface-style-preview-menu'),
          tooltip: t(InterfaceStyleLocale.previewMenu),
          initialValue: settings.style,
          onOpened: () => SfxService().playEnterSound(),
          onSelected: (style) {
            SfxService().playNavSound();
            _pickStyle(style);
          },
          itemBuilder: (context) => [
            for (final style in InterfaceStyle.values)
              CheckedPopupMenuItem<InterfaceStyle>(
                value: style,
                checked: style == settings.style,
                child: Text(t(_styleKeys[style]!)),
              ),
          ],
          child: IgnorePointer(
            child: GlassIconButton(
              icon: Symbols.more_horiz_rounded,
              size: 24.r,
              sound: GlassButtonSound.none,
              onPressed: () {},
            ),
          ),
        ),
      ],
    );

    final banner = GlassBanner(
      kind: GlassBannerKind.info,
      compact: true,
      title: t(InterfaceStyleLocale.previewBannerTitle),
      message: t(InterfaceStyleLocale.previewBannerBody),
    );

    final Widget content = widget.compact
        ? Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [strip, const GlassGap(), styleRow],
                ),
              ),
              SizedBox(width: glass.gap),
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [labelsRow, const GlassGap(), buttons],
                ),
              ),
            ],
          )
        : Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              strip,
              const GlassGap(),
              styleRow,
              const GlassGap(),
              labelsRow,
              const GlassGap(),
              buttons,
              const GlassGap(),
              banner,
            ],
          );

    return ClipRRect(
      borderRadius: glass.radius(GlassRadius.m),
      child: Stack(
        children: [
          const Positioned.fill(child: _PreviewWallpaper()),
          Padding(
            padding: EdgeInsets.all(glass.gap * 0.5),
            // Never scrolls (a scrolled preview clipped its tab bar): the
            // sample shrinks uniformly when the panel is short.
            child: LayoutBuilder(
              builder: (context, constraints) => FittedBox(
                fit: BoxFit.scaleDown,
                alignment: Alignment.topCenter,
                child: SizedBox(width: constraints.maxWidth, child: content),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Sample background behind the preview: soft tiles in the theme's colours,
/// like the system cards of the main menu, so the glass surfaces have
/// something to show through. Static, painted once.
class _PreviewWallpaper extends StatelessWidget {
  const _PreviewWallpaper();

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return RepaintBoundary(
      child: CustomPaint(
        painter: _WallpaperPainter(
          base: theme.scaffoldBackgroundColor,
          colors: [
            theme.colorScheme.primary,
            theme.colorScheme.secondary,
            theme.colorScheme.tertiary,
          ],
        ),
      ),
    );
  }
}

class _WallpaperPainter extends CustomPainter {
  const _WallpaperPainter({required this.base, required this.colors});
  final Color base;
  final List<Color> colors;

  @override
  void paint(Canvas canvas, Size size) {
    canvas.drawRect(Offset.zero & size, Paint()..color = base);
    final tile = size.shortestSide * 0.34;
    final gap = tile * 0.18;
    var index = 0;
    for (var y = -tile * 0.3; y < size.height; y += tile + gap) {
      final shift = (index.isEven ? 0.0 : tile * 0.5) - tile * 0.2;
      for (var x = shift; x < size.width; x += tile + gap) {
        final color = colors[index % colors.length];
        final rect = Rect.fromLTWH(x, y, tile, tile);
        canvas.drawRRect(
          RRect.fromRectAndRadius(rect, Radius.circular(tile * 0.22)),
          Paint()
            ..shader = LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                color.withValues(alpha: 0.55),
                color.withValues(alpha: 0.18),
              ],
            ).createShader(rect),
        );
        index++;
      }
      index++;
    }
  }

  @override
  bool shouldRepaint(_WallpaperPainter old) =>
      old.base != base || old.colors.join() != colors.join();
}
