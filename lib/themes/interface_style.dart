import 'dart:convert';

import 'package:flutter/foundation.dart';

/// Overall presentation of RewindBox's chrome, chosen in
/// Settings › Themes › User interface.
enum InterfaceStyle {
  /// Translucent, blurred surfaces with a convex rim and a soft sheen.
  liquidGlass,

  /// Mostly opaque surfaces, light blur: close to the previous interface.
  classic,

  /// Flat, opaque surfaces, no blur, no sheen, reduced motion.
  minimal,

  /// The original NeoStation look: matte surface-tinted pills, a solid
  /// accent pill sliding under the selected tab, LB/RB glyphs.
  neoStation,
}

/// Shape of the main navigation bar.
enum TabBarStyle { floating, compact, classic }

/// Selection marker of the main navigation bar. [solid] is NeoStation's
/// accent pill: the icon under it switches to the accent's contrast colour.
enum TabIndicatorStyle { lens, pill, underline, solid }

enum TabIconSize { small, medium, large }

/// When a tab shows its translated name under the icon.
enum TabLabelMode { hidden, selectedOnly, always }

/// Colour mixed into every glass surface.
enum GlassTint { neutral, accent, secondary, cool, warm }

enum InterfaceDensity { compact, regular, comfortable }

/// How much of the interface motion plays. iOS accessibility settings always
/// take precedence (see [LiquidGlassTheme.motionEnabled]).
enum MotionLevel { full, reduced, essential }

/// Accent replacing the theme's primary colour, or the theme's own.
enum AccentColor { theme, rose, violet, blue, cyan, green, amber, red }

/// How a control focused with the gamepad stands out.
enum FocusIndicatorStyle { ring, glow, ringGlow }

/// User-adjustable presentation of the interface. Every slider is stored as
/// a 0..1 fraction; the resolver maps it onto a bounded range so no value can
/// make text unreadable. `0.5` is the designed look for every slider.
@immutable
class InterfaceStyleSettings {
  const InterfaceStyleSettings({
    this.style = InterfaceStyle.liquidGlass,
    this.tabBarStyle = TabBarStyle.floating,
    this.tabIndicator = TabIndicatorStyle.lens,
    this.tabIconSize = TabIconSize.medium,
    this.tabLabels = TabLabelMode.hidden,
    this.tabEffectIntensity = 0.5,
    this.glassIntensity = 0.5,
    this.transparency = 0.5,
    this.blur = 0.5,
    this.tint = GlassTint.neutral,
    this.contrast = 0.5,
    this.cornerRadius = 0.5,
    this.density = InterfaceDensity.regular,
    this.depth = 0.5,
    this.motion = MotionLevel.full,
    this.showTabBumpers = false,
    this.showClock = true,
    this.showNotifications = true,
    this.showDeviceBattery = true,
    this.showControllerBattery = true,
    this.accent = AccentColor.theme,
    this.focusIndicator = FocusIndicatorStyle.ring,
    this.showSideMenuPanel = false,
    this.showSystemBubbles = true,
  });

  static const int schemaVersion = 2;
  static const InterfaceStyleSettings defaults = InterfaceStyleSettings();

  final InterfaceStyle style;
  final TabBarStyle tabBarStyle;
  final TabIndicatorStyle tabIndicator;
  final TabIconSize tabIconSize;
  final TabLabelMode tabLabels;

  /// Strength of the navigation bar's rim, fill and shadow (0..1).
  final double tabEffectIntensity;

  /// Rim and sheen strength of every glass surface (0..1).
  final double glassIntensity;

  /// Clarity of the surfaces: 0 is the most opaque safe value, 1 the clearest.
  final double transparency;

  /// Backdrop blur amount (0..1); 0 disables the blur pass entirely.
  final double blur;
  final GlassTint tint;

  /// Foreground/surface separation (0..1): rims, dividers and fills.
  final double contrast;

  /// Corner radius scale (0..1 → about half to one and a half times).
  final double cornerRadius;
  final InterfaceDensity density;

  /// Shadow and depth strength (0..1).
  final double depth;
  final MotionLevel motion;

  /// LB/RB glyphs on each side of the navigation bar.
  final bool showTabBumpers;

  /// Status pill of the main header: each element can be hidden to keep the
  /// header on one line.
  final bool showClock;
  final bool showNotifications;
  final bool showDeviceBattery;
  final bool showControllerBattery;
  final AccentColor accent;
  final FocusIndicatorStyle focusIndicator;

  /// Translucent panel behind the settings and scraper side menus. Hidden by
  /// default: only the category bubbles float over the background.
  final bool showSideMenuPanel;

  /// Liquid Glass bubbles around the System Art Packs of the main menu. Off,
  /// the artwork sits directly on the menu background and only a discreet
  /// marker follows the selection. Other menus keep their bubbles either way.
  final bool showSystemBubbles;

  /// A general style sets its surfaces, its navigation bar and its motion;
  /// labels, icon size, density, tint, colours and the status pill are kept.
  static InterfaceStyleSettings presetFor(
    InterfaceStyle style, {
    InterfaceStyleSettings? keep,
  }) {
    final base = keep ?? defaults;
    return switch (style) {
      InterfaceStyle.liquidGlass => base.copyWith(
        style: style,
        tabBarStyle: TabBarStyle.floating,
        tabIndicator: TabIndicatorStyle.lens,
        showTabBumpers: false,
        glassIntensity: 0.5,
        transparency: 0.5,
        blur: 0.5,
        contrast: 0.5,
        depth: 0.5,
        motion: MotionLevel.full,
      ),
      InterfaceStyle.classic => base.copyWith(
        style: style,
        tabBarStyle: TabBarStyle.classic,
        tabIndicator: TabIndicatorStyle.pill,
        showTabBumpers: false,
        glassIntensity: 0.3,
        transparency: 0.25,
        blur: 0.25,
        contrast: 0.6,
        depth: 0.4,
        motion: MotionLevel.full,
      ),
      InterfaceStyle.minimal => base.copyWith(
        style: style,
        tabBarStyle: TabBarStyle.compact,
        tabIndicator: TabIndicatorStyle.underline,
        showTabBumpers: false,
        glassIntensity: 0.1,
        transparency: 0.1,
        blur: 0.0,
        contrast: 0.65,
        depth: 0.15,
        motion: MotionLevel.reduced,
      ),
      // Upstream NeoStation: no blur, a surface tint about 83 % opaque, a
      // visible rim, the solid sliding pill and the shoulder glyphs.
      InterfaceStyle.neoStation => base.copyWith(
        style: style,
        tabBarStyle: TabBarStyle.classic,
        tabIndicator: TabIndicatorStyle.solid,
        showTabBumpers: true,
        glassIntensity: 0.35,
        transparency: 0.3,
        blur: 0.0,
        contrast: 0.55,
        depth: 0.3,
        motion: MotionLevel.full,
      ),
    };
  }

  /// Clamps every fraction into 0..1.
  InterfaceStyleSettings normalized() => copyWith(
    tabEffectIntensity: _unit(tabEffectIntensity),
    glassIntensity: _unit(glassIntensity),
    transparency: _unit(transparency),
    blur: _unit(blur),
    contrast: _unit(contrast),
    cornerRadius: _unit(cornerRadius),
    depth: _unit(depth),
  );

  static double _unit(double value) =>
      value.isFinite ? value.clamp(0.0, 1.0).toDouble() : 0.5;

  InterfaceStyleSettings copyWith({
    InterfaceStyle? style,
    TabBarStyle? tabBarStyle,
    TabIndicatorStyle? tabIndicator,
    TabIconSize? tabIconSize,
    TabLabelMode? tabLabels,
    double? tabEffectIntensity,
    double? glassIntensity,
    double? transparency,
    double? blur,
    GlassTint? tint,
    double? contrast,
    double? cornerRadius,
    InterfaceDensity? density,
    double? depth,
    MotionLevel? motion,
    bool? showTabBumpers,
    bool? showClock,
    bool? showNotifications,
    bool? showDeviceBattery,
    bool? showControllerBattery,
    AccentColor? accent,
    FocusIndicatorStyle? focusIndicator,
    bool? showSideMenuPanel,
    bool? showSystemBubbles,
  }) => InterfaceStyleSettings(
    style: style ?? this.style,
    tabBarStyle: tabBarStyle ?? this.tabBarStyle,
    tabIndicator: tabIndicator ?? this.tabIndicator,
    tabIconSize: tabIconSize ?? this.tabIconSize,
    tabLabels: tabLabels ?? this.tabLabels,
    tabEffectIntensity: tabEffectIntensity ?? this.tabEffectIntensity,
    glassIntensity: glassIntensity ?? this.glassIntensity,
    transparency: transparency ?? this.transparency,
    blur: blur ?? this.blur,
    tint: tint ?? this.tint,
    contrast: contrast ?? this.contrast,
    cornerRadius: cornerRadius ?? this.cornerRadius,
    density: density ?? this.density,
    depth: depth ?? this.depth,
    motion: motion ?? this.motion,
    showTabBumpers: showTabBumpers ?? this.showTabBumpers,
    showClock: showClock ?? this.showClock,
    showNotifications: showNotifications ?? this.showNotifications,
    showDeviceBattery: showDeviceBattery ?? this.showDeviceBattery,
    showControllerBattery: showControllerBattery ?? this.showControllerBattery,
    accent: accent ?? this.accent,
    focusIndicator: focusIndicator ?? this.focusIndicator,
    showSideMenuPanel: showSideMenuPanel ?? this.showSideMenuPanel,
    showSystemBubbles: showSystemBubbles ?? this.showSystemBubbles,
  );

  Map<String, Object> toJson() => <String, Object>{
    'v': schemaVersion,
    'style': style.name,
    'tabBarStyle': tabBarStyle.name,
    'tabIndicator': tabIndicator.name,
    'tabIconSize': tabIconSize.name,
    'tabLabels': tabLabels.name,
    'tabEffectIntensity': tabEffectIntensity,
    'glassIntensity': glassIntensity,
    'transparency': transparency,
    'blur': blur,
    'tint': tint.name,
    'contrast': contrast,
    'cornerRadius': cornerRadius,
    'density': density.name,
    'depth': depth,
    'motion': motion.name,
    'showTabBumpers': showTabBumpers,
    'showClock': showClock,
    'showNotifications': showNotifications,
    'showDeviceBattery': showDeviceBattery,
    'showControllerBattery': showControllerBattery,
    'accent': accent.name,
    'focusIndicator': focusIndicator.name,
    'showSideMenuPanel': showSideMenuPanel,
    'showSystemBubbles': showSystemBubbles,
  };

  String encode() => jsonEncode(toJson());

  /// Tolerant decoder: an unknown or malformed field keeps its default, so a
  /// preference written by a newer build never breaks an older one.
  static InterfaceStyleSettings fromJson(Map<String, dynamic>? json) {
    if (json == null) return defaults;
    T pick<T extends Enum>(String key, List<T> values, T fallback) {
      final raw = json[key];
      if (raw is! String) return fallback;
      for (final value in values) {
        if (value.name == raw) return value;
      }
      return fallback;
    }

    double fraction(String key, double fallback) {
      final raw = json[key];
      if (raw is num && raw.isFinite) return raw.clamp(0.0, 1.0).toDouble();
      return fallback;
    }

    bool flag(String key, bool fallback) {
      final raw = json[key];
      return raw is bool ? raw : fallback;
    }

    const d = defaults;
    return InterfaceStyleSettings(
      style: pick('style', InterfaceStyle.values, d.style),
      tabBarStyle: pick('tabBarStyle', TabBarStyle.values, d.tabBarStyle),
      tabIndicator: pick(
        'tabIndicator',
        TabIndicatorStyle.values,
        d.tabIndicator,
      ),
      tabIconSize: pick('tabIconSize', TabIconSize.values, d.tabIconSize),
      tabLabels: pick('tabLabels', TabLabelMode.values, d.tabLabels),
      tabEffectIntensity: fraction('tabEffectIntensity', d.tabEffectIntensity),
      glassIntensity: fraction('glassIntensity', d.glassIntensity),
      transparency: fraction('transparency', d.transparency),
      blur: fraction('blur', d.blur),
      tint: pick('tint', GlassTint.values, d.tint),
      contrast: fraction('contrast', d.contrast),
      cornerRadius: fraction('cornerRadius', d.cornerRadius),
      density: pick('density', InterfaceDensity.values, d.density),
      depth: fraction('depth', d.depth),
      motion: pick('motion', MotionLevel.values, d.motion),
      showTabBumpers: flag('showTabBumpers', d.showTabBumpers),
      showClock: flag('showClock', d.showClock),
      showNotifications: flag('showNotifications', d.showNotifications),
      showDeviceBattery: flag('showDeviceBattery', d.showDeviceBattery),
      showControllerBattery: flag(
        'showControllerBattery',
        d.showControllerBattery,
      ),
      accent: pick('accent', AccentColor.values, d.accent),
      focusIndicator: pick(
        'focusIndicator',
        FocusIndicatorStyle.values,
        d.focusIndicator,
      ),
      showSideMenuPanel: flag('showSideMenuPanel', d.showSideMenuPanel),
      showSystemBubbles: flag('showSystemBubbles', d.showSystemBubbles),
    );
  }

  static InterfaceStyleSettings decode(String? encoded) {
    if (encoded == null || encoded.isEmpty) return defaults;
    try {
      final decoded = jsonDecode(encoded);
      return decoded is Map<String, dynamic> ? fromJson(decoded) : defaults;
    } catch (_) {
      return defaults;
    }
  }

  @override
  bool operator ==(Object other) =>
      other is InterfaceStyleSettings &&
      other.style == style &&
      other.tabBarStyle == tabBarStyle &&
      other.tabIndicator == tabIndicator &&
      other.tabIconSize == tabIconSize &&
      other.tabLabels == tabLabels &&
      other.tabEffectIntensity == tabEffectIntensity &&
      other.glassIntensity == glassIntensity &&
      other.transparency == transparency &&
      other.blur == blur &&
      other.tint == tint &&
      other.contrast == contrast &&
      other.cornerRadius == cornerRadius &&
      other.density == density &&
      other.depth == depth &&
      other.motion == motion &&
      other.showTabBumpers == showTabBumpers &&
      other.showClock == showClock &&
      other.showNotifications == showNotifications &&
      other.showDeviceBattery == showDeviceBattery &&
      other.showControllerBattery == showControllerBattery &&
      other.accent == accent &&
      other.focusIndicator == focusIndicator &&
      other.showSideMenuPanel == showSideMenuPanel &&
      other.showSystemBubbles == showSystemBubbles;

  @override
  int get hashCode => Object.hashAll([
    style,
    tabBarStyle,
    tabIndicator,
    tabIconSize,
    tabLabels,
    tabEffectIntensity,
    glassIntensity,
    transparency,
    blur,
    tint,
    contrast,
    cornerRadius,
    density,
    depth,
    motion,
    showTabBumpers,
    showClock,
    showNotifications,
    showDeviceBattery,
    showControllerBattery,
    accent,
    focusIndicator,
    showSideMenuPanel,
    showSystemBubbles,
  ]);

  @override
  String toString() => 'InterfaceStyleSettings(${encode()})';
}
