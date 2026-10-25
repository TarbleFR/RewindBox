import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:provider/provider.dart';

import '../../../l10n/interface_style_locale.dart';
import '../../../providers/theme_provider.dart';
import '../../../services/game_service.dart';
import '../../../services/sfx_service.dart';
import '../../../utils/gamepad_nav.dart';
import '../../../widgets/custom_notification.dart';
import '../../../widgets/custom_toggle_switch.dart';
import '../../../widgets/glass/glass.dart';
import 'interface_style_preview.dart';

/// Settings › Themes › User interface.
///
/// A draft of [InterfaceStyleSettings] is edited here; the preview panel is
/// drawn with that draft while the rest of the app keeps the applied style.
/// Apply persists the draft through [ThemeProvider]; Restore defaults applies
/// the designed values. Touch and gamepad (Up/Down focus, Left/Right adjust,
/// A activate, B back) drive the same rows.
class InterfaceStyleScreen extends StatefulWidget {
  const InterfaceStyleScreen({super.key});

  static const String gamepadLayer = 'interface_style_screen';

  /// Opens the screen on its own backdrop: the settings behind it never show
  /// through, and the preview's glass shows its own sample background.
  static Future<void> open(BuildContext context) =>
      Navigator.of(context, rootNavigator: true).push(
        PageRouteBuilder<void>(
          barrierDismissible: false,
          transitionDuration: LiquidGlassTheme.of(
            context,
          ).duration(context, GlassMotion.standard),
          reverseTransitionDuration: LiquidGlassTheme.of(
            context,
          ).duration(context, GlassMotion.quick),
          pageBuilder: (_, _, _) => const InterfaceStyleScreen(),
          transitionsBuilder: (_, animation, _, child) => FadeTransition(
            opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
            child: child,
          ),
        ),
      );

  @override
  State<InterfaceStyleScreen> createState() => _InterfaceStyleScreenState();
}

/// One adjustable line of the screen.
abstract class _Row {
  const _Row(this.key);
  final String key;
}

class _ChoiceRow<T> extends _Row {
  const _ChoiceRow(
    super.key, {
    required this.title,
    required this.segments,
    required this.value,
    required this.onChanged,
    this.subtitle,
  });
  final String title;
  final String? subtitle;
  final List<GlassSegment<T>> segments;
  final T value;
  final ValueChanged<T> onChanged;

  int get index => segments.indexWhere((s) => s.value == value);

  void step(int delta) {
    final next = (index + delta).clamp(0, segments.length - 1);
    if (next != index) onChanged(segments[next].value);
  }

  /// Cycles to the next option (gamepad A).
  void next() => onChanged(segments[(index + 1) % segments.length].value);

  /// Typed entry point for callers holding the row through its base type:
  /// a `ValueChanged<T>` cannot be invoked through `_ChoiceRow<dynamic>`.
  void select(Object? chosen) => onChanged(chosen as T);
}

class _ToggleRow extends _Row {
  const _ToggleRow(
    super.key, {
    required this.title,
    required this.value,
    required this.onChanged,
    this.subtitle,
  });
  final String title;
  final String? subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;
}

class _SliderRow extends _Row {
  const _SliderRow(
    super.key, {
    required this.title,
    required this.value,
    required this.onChanged,
  });
  final String title;
  final double value;
  final ValueChanged<double> onChanged;

  void step(int delta) =>
      onChanged((value + delta * 0.05).clamp(0.0, 1.0).toDouble());
}

class _ActionRow extends _Row {
  const _ActionRow(
    super.key, {
    required this.label,
    required this.icon,
    required this.onTap,
    this.primary = false,
  });
  final String label;
  final IconData icon;
  final VoidCallback onTap;
  final bool primary;
}

class _SectionRow extends _Row {
  const _SectionRow(super.key, {required this.label});
  final String label;
}

class _InterfaceStyleScreenState extends State<InterfaceStyleScreen> {
  late InterfaceStyleSettings _draft;
  late InterfaceStyleSettings _applied;
  late final GamepadNavigation _gamepadNav;
  final ScrollController _scroll = ScrollController();
  final Map<String, GlobalKey> _rowKeys = {};
  int _focus = 0;
  List<_Row> _rows = const [];

  @override
  void initState() {
    super.initState();
    _applied = context.read<ThemeProvider>().interfaceStyle;
    _draft = _applied;
    _gamepadNav = GamepadNavigation(
      onNavigateUp: () => _moveFocus(-1),
      onNavigateDown: () => _moveFocus(1),
      onNavigateLeft: () => _adjust(-1),
      onNavigateRight: () => _adjust(1),
      onSelectItem: _activate,
      onBack: _close,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        InterfaceStyleScreen.gamepadLayer,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(InterfaceStyleScreen.gamepadLayer);
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  bool get _dirty => _draft != _applied;

  List<_Row> get _focusable =>
      _rows.where((row) => row is! _SectionRow).toList(growable: false);

  void _moveFocus(int delta) {
    final rows = _focusable;
    if (rows.isEmpty) return;
    final next = (_focus + delta).clamp(0, rows.length - 1);
    if (next == _focus) return;
    SfxService().playNavSound();
    setState(() => _focus = next);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ctx = _rowKeys[rows[next].key]?.currentContext;
      if (ctx != null) {
        Scrollable.ensureVisible(
          ctx,
          alignment: 0.5,
          duration: LiquidGlassTheme.of(
            context,
          ).duration(context, GlassMotion.standard),
        );
      }
    });
  }

  void _adjust(int delta) {
    final rows = _focusable;
    if (_focus >= rows.length) return;
    final row = rows[_focus];
    if (row is _ChoiceRow) {
      SfxService().playNavSound();
      row.step(delta);
    } else if (row is _SliderRow) {
      row.step(delta);
    } else if (row is _ToggleRow && row.value != delta > 0) {
      SfxService().playNavSound();
      row.onChanged(delta > 0);
    }
  }

  void _activate() {
    final rows = _focusable;
    if (_focus >= rows.length) return;
    final row = rows[_focus];
    if (row is _ActionRow) {
      SfxService().playEnterSound();
      row.onTap();
    } else if (row is _ChoiceRow) {
      SfxService().playNavSound();
      row.next();
    } else if (row is _ToggleRow) {
      SfxService().playNavSound();
      row.onChanged(!row.value);
    }
  }

  void _close() {
    if (!mounted) return;
    SfxService().playBackSound();
    Navigator.of(context).pop();
  }

  void _update(InterfaceStyleSettings next) {
    if (next == _draft) return;
    setState(() => _draft = next.normalized());
  }

  Future<void> _apply() async {
    final provider = context.read<ThemeProvider>();
    await provider.setInterfaceStyle(_draft);
    if (!mounted) return;
    setState(() => _applied = provider.interfaceStyle);
    AppNotification.showNotification(
      context,
      InterfaceStyleLocale.text(context, InterfaceStyleLocale.applied),
      type: NotificationType.success,
    );
  }

  /// Drops the draft and goes back to the applied style.
  void _revert() {
    if (!_dirty) return;
    setState(() => _draft = _applied);
  }

  Future<void> _reset() async {
    final provider = context.read<ThemeProvider>();
    await provider.resetInterfaceStyle();
    if (!mounted) return;
    setState(() {
      _draft = InterfaceStyleSettings.defaults;
      _applied = provider.interfaceStyle;
    });
    AppNotification.showNotification(
      context,
      InterfaceStyleLocale.text(context, InterfaceStyleLocale.resetDone),
      type: NotificationType.info,
    );
  }

  String _t(String key) => InterfaceStyleLocale.text(context, key);

  String _percent(double value) => InterfaceStyleLocale.format(
    context,
    InterfaceStyleLocale.valuePercent,
    <String, Object?>{'value': (value * 100).round()},
  );

  List<_Row> _buildRows() {
    final d = _draft;
    return [
      _SectionRow(
        'section.style',
        label: _t(InterfaceStyleLocale.sectionStyle),
      ),
      _ChoiceRow<InterfaceStyle>(
        'style',
        title: _t(InterfaceStyleLocale.sectionStyle),
        subtitle: switch (d.style) {
          InterfaceStyle.liquidGlass => _t(
            InterfaceStyleLocale.styleLiquidGlassHint,
          ),
          InterfaceStyle.classic => _t(InterfaceStyleLocale.styleClassicHint),
          InterfaceStyle.minimal => _t(InterfaceStyleLocale.styleMinimalHint),
          InterfaceStyle.neoStation => _t(
            InterfaceStyleLocale.styleNeoStationHint,
          ),
        },
        segments: [
          GlassSegment(
            value: InterfaceStyle.liquidGlass,
            label: _t(InterfaceStyleLocale.styleLiquidGlass),
            icon: Symbols.blur_on_rounded,
          ),
          GlassSegment(
            value: InterfaceStyle.classic,
            label: _t(InterfaceStyleLocale.styleClassic),
            icon: Symbols.crop_square_rounded,
          ),
          GlassSegment(
            value: InterfaceStyle.minimal,
            label: _t(InterfaceStyleLocale.styleMinimal),
            icon: Symbols.remove_rounded,
          ),
          GlassSegment(
            value: InterfaceStyle.neoStation,
            label: _t(InterfaceStyleLocale.styleNeoStation),
            icon: Symbols.sports_esports_rounded,
          ),
        ],
        value: d.style,
        onChanged: (style) =>
            _update(InterfaceStyleSettings.presetFor(style, keep: d)),
      ),
      _SectionRow(
        'section.tabBar',
        label: _t(InterfaceStyleLocale.sectionTabBar),
      ),
      _ChoiceRow<TabBarStyle>(
        'tabBarStyle',
        title: _t(InterfaceStyleLocale.tabBarStyle),
        segments: [
          GlassSegment(
            value: TabBarStyle.floating,
            label: _t(InterfaceStyleLocale.tabBarFloating),
          ),
          GlassSegment(
            value: TabBarStyle.compact,
            label: _t(InterfaceStyleLocale.tabBarCompact),
          ),
          GlassSegment(
            value: TabBarStyle.classic,
            label: _t(InterfaceStyleLocale.tabBarClassic),
          ),
        ],
        value: d.tabBarStyle,
        onChanged: (v) => _update(d.copyWith(tabBarStyle: v)),
      ),
      _ChoiceRow<TabIndicatorStyle>(
        'tabIndicator',
        title: _t(InterfaceStyleLocale.tabIndicator),
        segments: [
          GlassSegment(
            value: TabIndicatorStyle.lens,
            label: _t(InterfaceStyleLocale.indicatorLens),
          ),
          GlassSegment(
            value: TabIndicatorStyle.pill,
            label: _t(InterfaceStyleLocale.indicatorPill),
          ),
          GlassSegment(
            value: TabIndicatorStyle.underline,
            label: _t(InterfaceStyleLocale.indicatorUnderline),
          ),
          GlassSegment(
            value: TabIndicatorStyle.solid,
            label: _t(InterfaceStyleLocale.indicatorSolid),
          ),
        ],
        value: d.tabIndicator,
        onChanged: (v) => _update(d.copyWith(tabIndicator: v)),
      ),
      _ChoiceRow<TabIconSize>(
        'tabIconSize',
        title: _t(InterfaceStyleLocale.tabIconSize),
        segments: [
          GlassSegment(
            value: TabIconSize.small,
            label: _t(InterfaceStyleLocale.sizeSmall),
          ),
          GlassSegment(
            value: TabIconSize.medium,
            label: _t(InterfaceStyleLocale.sizeMedium),
          ),
          GlassSegment(
            value: TabIconSize.large,
            label: _t(InterfaceStyleLocale.sizeLarge),
          ),
        ],
        value: d.tabIconSize,
        onChanged: (v) => _update(d.copyWith(tabIconSize: v)),
      ),
      _ChoiceRow<TabLabelMode>(
        'tabLabels',
        title: _t(InterfaceStyleLocale.tabLabels),
        segments: [
          GlassSegment(
            value: TabLabelMode.hidden,
            label: _t(InterfaceStyleLocale.labelsHidden),
          ),
          GlassSegment(
            value: TabLabelMode.selectedOnly,
            label: _t(InterfaceStyleLocale.labelsSelected),
          ),
          GlassSegment(
            value: TabLabelMode.always,
            label: _t(InterfaceStyleLocale.labelsAlways),
          ),
        ],
        value: d.tabLabels,
        onChanged: (v) => _update(d.copyWith(tabLabels: v)),
      ),
      _ToggleRow(
        'tabBumpers',
        title: _t(InterfaceStyleLocale.tabBumpers),
        subtitle: _t(InterfaceStyleLocale.tabBumpersHint),
        value: d.showTabBumpers,
        onChanged: (v) => _update(d.copyWith(showTabBumpers: v)),
      ),
      _SliderRow(
        'tabEffects',
        title: _t(InterfaceStyleLocale.tabEffects),
        value: d.tabEffectIntensity,
        onChanged: (v) => _update(d.copyWith(tabEffectIntensity: v)),
      ),
      _SectionRow(
        'section.statusBar',
        label: _t(InterfaceStyleLocale.sectionStatusBar),
      ),
      _ToggleRow(
        'statusClock',
        title: _t(InterfaceStyleLocale.statusClock),
        subtitle: _t(InterfaceStyleLocale.statusBarHint),
        value: d.showClock,
        onChanged: (v) => _update(d.copyWith(showClock: v)),
      ),
      _ToggleRow(
        'statusNotifications',
        title: _t(InterfaceStyleLocale.statusNotifications),
        value: d.showNotifications,
        onChanged: (v) => _update(d.copyWith(showNotifications: v)),
      ),
      _ToggleRow(
        'statusDeviceBattery',
        title: _t(InterfaceStyleLocale.statusDeviceBattery),
        value: d.showDeviceBattery,
        onChanged: (v) => _update(d.copyWith(showDeviceBattery: v)),
      ),
      _ToggleRow(
        'statusControllerBattery',
        title: _t(InterfaceStyleLocale.statusControllerBattery),
        value: d.showControllerBattery,
        onChanged: (v) => _update(d.copyWith(showControllerBattery: v)),
      ),
      _SectionRow(
        'section.colors',
        label: _t(InterfaceStyleLocale.sectionColors),
      ),
      _ChoiceRow<AccentColor>(
        'accent',
        title: _t(InterfaceStyleLocale.accentColor),
        subtitle: _t(InterfaceStyleLocale.accentHint),
        segments: [
          for (final (accent, key) in const [
            (AccentColor.theme, InterfaceStyleLocale.accentTheme),
            (AccentColor.rose, InterfaceStyleLocale.accentRose),
            (AccentColor.violet, InterfaceStyleLocale.accentViolet),
            (AccentColor.blue, InterfaceStyleLocale.accentBlue),
            (AccentColor.cyan, InterfaceStyleLocale.accentCyan),
            (AccentColor.green, InterfaceStyleLocale.accentGreen),
            (AccentColor.amber, InterfaceStyleLocale.accentAmber),
            (AccentColor.red, InterfaceStyleLocale.accentRed),
          ])
            GlassSegment(
              value: accent,
              label: _t(key),
              swatch:
                  accentColorOf(accent) ??
                  context.read<ThemeProvider>().baseTheme.colorScheme.primary,
            ),
        ],
        value: d.accent,
        onChanged: (v) => _update(d.copyWith(accent: v)),
      ),
      _ChoiceRow<GlassTint>(
        'tint',
        title: _t(InterfaceStyleLocale.tint),
        segments: [
          GlassSegment(
            value: GlassTint.neutral,
            label: _t(InterfaceStyleLocale.tintNeutral),
          ),
          GlassSegment(
            value: GlassTint.accent,
            label: _t(InterfaceStyleLocale.tintAccent),
          ),
          GlassSegment(
            value: GlassTint.secondary,
            label: _t(InterfaceStyleLocale.tintSecondary),
          ),
          GlassSegment(
            value: GlassTint.cool,
            label: _t(InterfaceStyleLocale.tintCool),
          ),
          GlassSegment(
            value: GlassTint.warm,
            label: _t(InterfaceStyleLocale.tintWarm),
          ),
        ],
        value: d.tint,
        onChanged: (v) => _update(d.copyWith(tint: v)),
      ),
      _ChoiceRow<FocusIndicatorStyle>(
        'focusIndicator',
        title: _t(InterfaceStyleLocale.focusIndicator),
        segments: [
          GlassSegment(
            value: FocusIndicatorStyle.ring,
            label: _t(InterfaceStyleLocale.focusRing),
          ),
          GlassSegment(
            value: FocusIndicatorStyle.glow,
            label: _t(InterfaceStyleLocale.focusGlow),
          ),
          GlassSegment(
            value: FocusIndicatorStyle.ringGlow,
            label: _t(InterfaceStyleLocale.focusRingGlow),
          ),
        ],
        value: d.focusIndicator,
        onChanged: (v) => _update(d.copyWith(focusIndicator: v)),
      ),
      _SectionRow(
        'section.surfaces',
        label: _t(InterfaceStyleLocale.sectionSurfaces),
      ),
      _SliderRow(
        'glassIntensity',
        title: _t(InterfaceStyleLocale.glassIntensity),
        value: d.glassIntensity,
        onChanged: (v) => _update(d.copyWith(glassIntensity: v)),
      ),
      _SliderRow(
        'transparency',
        title: _t(InterfaceStyleLocale.transparency),
        value: d.transparency,
        onChanged: (v) => _update(d.copyWith(transparency: v)),
      ),
      _SliderRow(
        'blur',
        title: _t(InterfaceStyleLocale.blur),
        value: d.blur,
        onChanged: (v) => _update(d.copyWith(blur: v)),
      ),
      _SliderRow(
        'contrast',
        title: _t(InterfaceStyleLocale.contrast),
        value: d.contrast,
        onChanged: (v) => _update(d.copyWith(contrast: v)),
      ),
      _SliderRow(
        'cornerRadius',
        title: _t(InterfaceStyleLocale.cornerRadius),
        value: d.cornerRadius,
        onChanged: (v) => _update(d.copyWith(cornerRadius: v)),
      ),
      _ChoiceRow<InterfaceDensity>(
        'density',
        title: _t(InterfaceStyleLocale.density),
        segments: [
          GlassSegment(
            value: InterfaceDensity.compact,
            label: _t(InterfaceStyleLocale.densityCompact),
          ),
          GlassSegment(
            value: InterfaceDensity.regular,
            label: _t(InterfaceStyleLocale.densityRegular),
          ),
          GlassSegment(
            value: InterfaceDensity.comfortable,
            label: _t(InterfaceStyleLocale.densityComfortable),
          ),
        ],
        value: d.density,
        onChanged: (v) => _update(d.copyWith(density: v)),
      ),
      _SliderRow(
        'depth',
        title: _t(InterfaceStyleLocale.depth),
        value: d.depth,
        onChanged: (v) => _update(d.copyWith(depth: v)),
      ),
      _ToggleRow(
        'sidePanel',
        title: _t(InterfaceStyleLocale.sidePanel),
        subtitle: _t(InterfaceStyleLocale.sidePanelHint),
        value: d.showSideMenuPanel,
        onChanged: (v) => _update(d.copyWith(showSideMenuPanel: v)),
      ),
      _SectionRow(
        'section.motion',
        label: _t(InterfaceStyleLocale.sectionMotion),
      ),
      _ChoiceRow<MotionLevel>(
        'motion',
        title: _t(InterfaceStyleLocale.sectionMotion),
        subtitle: _t(InterfaceStyleLocale.motionSystemNote),
        segments: [
          GlassSegment(
            value: MotionLevel.full,
            label: _t(InterfaceStyleLocale.motionFull),
          ),
          GlassSegment(
            value: MotionLevel.reduced,
            label: _t(InterfaceStyleLocale.motionReduced),
          ),
          GlassSegment(
            value: MotionLevel.essential,
            label: _t(InterfaceStyleLocale.motionEssential),
          ),
        ],
        value: d.motion,
        onChanged: (v) => _update(d.copyWith(motion: v)),
      ),
      _ActionRow(
        'apply',
        label: _t(InterfaceStyleLocale.apply),
        icon: Symbols.check_rounded,
        onTap: _apply,
        primary: true,
      ),
      _ActionRow(
        'reset',
        label: _t(InterfaceStyleLocale.resetDefaults),
        icon: Symbols.restart_alt_rounded,
        onTap: _reset,
      ),
    ];
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    _rows = _buildRows();
    final focusable = _focusable;
    if (_focus >= focusable.length) _focus = focusable.length - 1;
    final focusedKey = focusable.isEmpty ? null : focusable[_focus].key;
    for (final row in _rows) {
      _rowKeys.putIfAbsent(row.key, GlobalKey.new);
    }
    final previewTheme = context
        .read<ThemeProvider>()
        .previewTheme(_draft)
        .copyWith(textTheme: theme.textTheme, iconTheme: theme.iconTheme);
    final safe = MediaQuery.viewPaddingOf(context);

    return GlassBackdrop(
      child: Material(
        color: Colors.transparent,
        child: SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              glass.margin + safe.left * 0,
              glass.gap,
              glass.margin,
              glass.gap,
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final wide = constraints.maxWidth >= 620;
                final list = _buildList(theme, glass, focusedKey);
                final preview = _buildPreview(theme, glass, previewTheme, wide);
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _buildHeader(theme, glass),
                    SizedBox(height: glass.gap),
                    Expanded(
                      child: wide
                          ? Row(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                Expanded(flex: 11, child: list),
                                SizedBox(width: glass.gap),
                                Expanded(flex: 9, child: preview),
                              ],
                            )
                          : Column(
                              crossAxisAlignment: CrossAxisAlignment.stretch,
                              children: [
                                SizedBox(height: 150.r, child: preview),
                                SizedBox(height: glass.gap),
                                Expanded(child: list),
                              ],
                            ),
                    ),
                  ],
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(ThemeData theme, LiquidGlassTheme glass) {
    return GlassSurface(
      role: GlassRole.chrome,
      padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 6.r),
      child: Row(
        children: [
          GlassIconButton(
            icon: Symbols.arrow_back_rounded,
            tooltip: _t(InterfaceStyleLocale.back),
            onPressed: _close,
            sound: GlassButtonSound.back,
            size: 26.r,
          ),
          SizedBox(width: 10.r),
          Icon(
            Symbols.auto_awesome_rounded,
            color: theme.colorScheme.primary,
            size: 16.r,
          ),
          SizedBox(width: 8.r),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  _t(InterfaceStyleLocale.title),
                  style: theme.textTheme.titleLarge?.copyWith(fontSize: 13.r),
                ),
                Text(
                  _t(InterfaceStyleLocale.description),
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodyMedium?.copyWith(
                    fontSize: 8.r,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                  ),
                ),
              ],
            ),
          ),
          if (_dirty) ...[
            SizedBox(width: 8.r),
            GlassChip(
              key: const ValueKey('interface-style-unsaved'),
              label: _t(InterfaceStyleLocale.unsaved),
              icon: Symbols.edit_rounded,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildList(ThemeData theme, LiquidGlassTheme glass, String? focused) {
    final children = <Widget>[];
    var first = true;
    for (final row in _rows) {
      final key = _rowKeys[row.key];
      if (row is _SectionRow) {
        children.add(
          GlassSectionHeader(key: key, label: row.label, first: first),
        );
        first = false;
        continue;
      }
      if (children.isNotEmpty && children.last is! GlassSectionHeader) {
        children.add(const GlassGap());
      }
      final isFocused = row.key == focused;
      if (row is _ChoiceRow) {
        children.add(_choiceBubble(theme, glass, row, isFocused, key));
      } else if (row is _SliderRow) {
        children.add(_sliderBubble(theme, glass, row, isFocused, key));
      } else if (row is _ToggleRow) {
        children.add(_toggleBubble(theme, glass, row, isFocused, key));
      } else if (row is _ActionRow) {
        children.add(
          KeyedSubtree(
            key: key,
            child: GlassButton(
              key: ValueKey('interface-style-${row.key}'),
              label: row.label,
              icon: row.icon,
              expanded: true,
              focused: isFocused,
              variant: row.primary
                  ? GlassButtonVariant.primary
                  : GlassButtonVariant.tonal,
              sound: GlassButtonSound.enter,
              onPressed: row.onTap,
            ),
          ),
        );
      }
    }
    children.add(const GlassGap.section());
    children.add(
      GlassBanner(
        kind: GlassBannerKind.info,
        compact: true,
        message: _t(InterfaceStyleLocale.performanceNote),
      ),
    );
    if (LiquidGlassTheme.highContrastOf(context)) {
      children.add(const GlassGap());
      children.add(
        GlassBanner(
          kind: GlassBannerKind.warning,
          compact: true,
          message: _t(InterfaceStyleLocale.highContrastNote),
        ),
      );
    }
    return ListView(
      controller: _scroll,
      padding: EdgeInsets.only(bottom: glass.gap, right: 2.r),
      children: children,
    );
  }

  Widget _choiceBubble(
    ThemeData theme,
    LiquidGlassTheme glass,
    _ChoiceRow row,
    bool focused,
    Key? key,
  ) {
    return GlassSurface(
      key: key,
      role: GlassRole.bubble,
      focused: focused,
      padding: glass.bubblePadding,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            row.title,
            style: theme.textTheme.bodyLarge?.copyWith(
              fontSize: 11.r,
              fontWeight: FontWeight.w500,
              color: focused
                  ? theme.colorScheme.primary
                  : theme.colorScheme.onSurface,
            ),
          ),
          if (row.subtitle != null) ...[
            SizedBox(height: 2.r),
            Text(
              row.subtitle!,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontSize: 8.5.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
          ],
          SizedBox(height: 6.r),
          GlassSegmentedControl(
            key: ValueKey('interface-style-${row.key}'),
            segments: row.segments,
            value: row.value,
            dense: true,
            onChanged: row.select,
          ),
        ],
      ),
    );
  }

  Widget _toggleBubble(
    ThemeData theme,
    LiquidGlassTheme glass,
    _ToggleRow row,
    bool focused,
    Key? key,
  ) {
    return GestureDetector(
      key: key,
      behavior: HitTestBehavior.opaque,
      onTap: () {
        SfxService().playNavSound();
        row.onChanged(!row.value);
      },
      child: GlassSurface(
        role: GlassRole.bubble,
        focused: focused,
        padding: glass.bubblePadding,
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    row.title,
                    style: theme.textTheme.bodyLarge?.copyWith(
                      fontSize: 11.r,
                      fontWeight: FontWeight.w500,
                      color: focused
                          ? theme.colorScheme.primary
                          : theme.colorScheme.onSurface,
                    ),
                  ),
                  if (row.subtitle != null) ...[
                    SizedBox(height: 2.r),
                    Text(
                      row.subtitle!,
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontSize: 8.5.r,
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.6,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: 10.r),
            CustomToggleSwitch(
              key: ValueKey('interface-style-${row.key}'),
              value: row.value,
              onChanged: row.onChanged,
            ),
          ],
        ),
      ),
    );
  }

  Widget _sliderBubble(
    ThemeData theme,
    LiquidGlassTheme glass,
    _SliderRow row,
    bool focused,
    Key? key,
  ) {
    return GlassSurface(
      key: key,
      role: GlassRole.bubble,
      focused: focused,
      padding: glass.bubblePadding,
      child: Row(
        children: [
          Expanded(
            flex: 5,
            child: Text(
              row.title,
              style: theme.textTheme.bodyLarge?.copyWith(
                fontSize: 11.r,
                fontWeight: FontWeight.w500,
                color: focused
                    ? theme.colorScheme.primary
                    : theme.colorScheme.onSurface,
              ),
            ),
          ),
          SizedBox(width: 10.r),
          Expanded(
            flex: 6,
            child: GlassSlider(
              key: ValueKey('interface-style-${row.key}'),
              value: row.value,
              divisions: 20,
              valueLabel: _percent(row.value),
              semanticLabel: row.title,
              onChanged: row.onChanged,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildPreview(
    ThemeData theme,
    LiquidGlassTheme glass,
    ThemeData previewTheme,
    bool wide,
  ) {
    return GlassSurface(
      role: GlassRole.panel,
      blur: false,
      padding: EdgeInsets.all(glass.gap * 0.7),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Symbols.preview_rounded,
                size: 12.r,
                color: theme.colorScheme.primary,
              ),
              SizedBox(width: 6.r),
              Text(
                _t(InterfaceStyleLocale.sectionPreview),
                style: TextStyle(
                  fontSize: 10.r,
                  fontWeight: FontWeight.bold,
                  color: theme.colorScheme.primary,
                  letterSpacing: 0.5,
                ),
              ),
            ],
          ),
          if (wide) ...[
            SizedBox(height: 2.r),
            Text(
              _t(InterfaceStyleLocale.previewHint),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: theme.textTheme.bodyMedium?.copyWith(
                fontSize: 8.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
          ],
          SizedBox(height: glass.gap * 0.6),
          Expanded(
            child: Theme(
              data: previewTheme,
              child: InterfaceStylePreview(
                key: const ValueKey('interface-style-preview'),
                settings: _draft,
                compact: !wide,
                dirty: _dirty,
                onChanged: _update,
                onApply: _apply,
                onRevert: _revert,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
