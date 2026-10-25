import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../../l10n/interface_style_locale.dart';
import '../../../utils/nav_tabs.dart';
import '../../../widgets/custom_toggle_switch.dart';
import '../../../widgets/glass/glass.dart';
import '../../../widgets/main_menu_tab_strip.dart';
import '../new_settings_options/widgets/setting_row.dart';

/// Sample composition drawn with a draft theme: a navigation bar, two
/// settings bubbles, two buttons and a notice. Everything here is the real
/// production widget, so the preview is faithful by construction.
class InterfaceStylePreview extends StatefulWidget {
  const InterfaceStylePreview({
    super.key,
    required this.settings,
    this.compact = false,
  });

  final InterfaceStyleSettings settings;
  final bool compact;

  @override
  State<InterfaceStylePreview> createState() => _InterfaceStylePreviewState();
}

class _InterfaceStylePreviewState extends State<InterfaceStylePreview> {
  bool _toggle = true;
  NavTab _selected = NavTab.systems;

  static const _tabs = [
    NavTab.systems,
    NavTab.consoles,
    NavTab.search,
    NavTab.library,
    NavTab.settings,
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    String t(String key) => InterfaceStyleLocale.text(context, key);
    final tint = theme.colorScheme.onSurface;

    final strip = Center(
      child: MainMenuTabStrip(
        key: const ValueKey('interface-style-preview-tabs'),
        tabs: _tabs,
        selected: _selected,
        cellExtent: widget.compact ? 22.r : 26.r,
        tabBuilder: (tab) => Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: () => setState(() => _selected = tab),
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

    final rows = <Widget>[
      SettingRow(
        title: t(InterfaceStyleLocale.previewRowTitle),
        subtitle: t(InterfaceStyleLocale.previewRowSubtitle),
        focused: false,
        trailing: GlassChip(
          label: t(InterfaceStyleLocale.styleLiquidGlass),
          trailingIcon: Symbols.expand_more_rounded,
        ),
      ),
      const GlassGap(),
      SettingRow(
        title: t(InterfaceStyleLocale.previewToggleTitle),
        subtitle: t(InterfaceStyleLocale.previewToggleSubtitle),
        focused: true,
        trailing: CustomToggleSwitch(
          value: _toggle,
          onChanged: (value) => setState(() => _toggle = value),
        ),
      ),
      const GlassGap(),
      Row(
        children: [
          Expanded(
            child: GlassButton(
              label: t(InterfaceStyleLocale.previewPrimary),
              icon: Symbols.play_arrow_rounded,
              variant: GlassButtonVariant.primary,
              size: GlassButtonSize.small,
              expanded: true,
              sound: GlassButtonSound.none,
              onPressed: () {},
            ),
          ),
          SizedBox(width: glass.gap * 0.6),
          Expanded(
            child: GlassButton(
              label: t(InterfaceStyleLocale.previewSecondary),
              variant: GlassButtonVariant.tonal,
              size: GlassButtonSize.small,
              expanded: true,
              sound: GlassButtonSound.none,
              onPressed: () {},
            ),
          ),
          SizedBox(width: glass.gap * 0.6),
          GlassIconButton(
            icon: Symbols.more_horiz_rounded,
            size: 24.r,
            sound: GlassButtonSound.none,
            onPressed: () {},
          ),
        ],
      ),
      const GlassGap(),
      GlassBanner(
        kind: GlassBannerKind.info,
        compact: true,
        title: t(InterfaceStyleLocale.previewBannerTitle),
        message: t(InterfaceStyleLocale.previewBannerBody),
      ),
    ];

    if (widget.compact) {
      return Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(child: Column(children: [strip, const GlassGap(), rows[0]])),
          SizedBox(width: glass.gap),
          Expanded(
            child: Column(children: [rows[2], const GlassGap(), rows[6]]),
          ),
        ],
      );
    }
    return ListView(
      padding: EdgeInsets.zero,
      children: [strip, const GlassGap(), ...rows],
    );
  }
}
