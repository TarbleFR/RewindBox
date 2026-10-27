import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/themes/interface_style.dart';

void main() {
  const defaults = InterfaceStyleSettings.defaults;

  test('every slider defaults to the designed midpoint', () {
    for (final value in [
      defaults.tabEffectIntensity,
      defaults.glassIntensity,
      defaults.transparency,
      defaults.blur,
      defaults.contrast,
      defaults.cornerRadius,
      defaults.depth,
    ]) {
      expect(value, 0.5);
    }
    expect(defaults.style, InterfaceStyle.liquidGlass);
    expect(defaults.tabBarStyle, TabBarStyle.floating);
    expect(defaults.tabIndicator, TabIndicatorStyle.lens);
    expect(defaults.tabLabels, TabLabelMode.hidden);
    expect(defaults.motion, MotionLevel.full);
    // Status pill complete, theme accent, ring focus, no LB/RB glyphs, and
    // floating side-menu bubbles (no panel) unless the user asks.
    expect(defaults.showTabBumpers, isFalse);
    expect(defaults.showClock, isTrue);
    expect(defaults.showNotifications, isTrue);
    expect(defaults.showDeviceBattery, isTrue);
    expect(defaults.showControllerBattery, isTrue);
    expect(defaults.accent, AccentColor.theme);
    expect(defaults.focusIndicator, FocusIndicatorStyle.ring);
    expect(defaults.showSideMenuPanel, isFalse);
    // The main menu keeps its Liquid Glass system bubbles unless turned off.
    expect(defaults.showSystemBubbles, isTrue);
  });

  test('encode and decode round-trip every field', () {
    const custom = InterfaceStyleSettings(
      style: InterfaceStyle.classic,
      tabBarStyle: TabBarStyle.compact,
      tabIndicator: TabIndicatorStyle.underline,
      tabIconSize: TabIconSize.large,
      tabLabels: TabLabelMode.always,
      tabEffectIntensity: 0.1,
      glassIntensity: 0.2,
      transparency: 0.3,
      blur: 0.4,
      tint: GlassTint.warm,
      contrast: 0.6,
      cornerRadius: 0.7,
      density: InterfaceDensity.comfortable,
      depth: 0.8,
      motion: MotionLevel.reduced,
      showTabBumpers: true,
      showClock: false,
      showNotifications: false,
      showDeviceBattery: false,
      showControllerBattery: false,
      accent: AccentColor.cyan,
      focusIndicator: FocusIndicatorStyle.ringGlow,
      showSideMenuPanel: true,
      showSystemBubbles: false,
    );
    final decoded = InterfaceStyleSettings.decode(custom.encode());
    expect(decoded, custom);
    expect(decoded.hashCode, custom.hashCode);
    expect(
      jsonDecode(custom.encode())['v'],
      InterfaceStyleSettings.schemaVersion,
    );
  });

  test(
    'a malformed or future preference keeps the defaults field by field',
    () {
      expect(InterfaceStyleSettings.decode(null), defaults);
      expect(InterfaceStyleSettings.decode(''), defaults);
      expect(InterfaceStyleSettings.decode('not json'), defaults);
      expect(InterfaceStyleSettings.decode('[1,2]'), defaults);
      final partial = InterfaceStyleSettings.fromJson({
        'v': 99,
        'style': 'holographic',
        'tabBarStyle': 'compact',
        'blur': 'high',
        'depth': 7.5,
        'contrast': double.nan,
        'extra': true,
      });
      expect(
        InterfaceStyleSettings.decode(
          jsonEncode({'v': 99, 'style': 'holographic', 'depth': 7.5}),
        ).depth,
        1.0,
      );
      expect(partial.style, InterfaceStyle.liquidGlass);
      expect(partial.tabBarStyle, TabBarStyle.compact);
      expect(partial.blur, 0.5);
      expect(partial.depth, 1.0, reason: 'out-of-range numbers are clamped');
      expect(partial.contrast, 0.5, reason: 'NaN keeps the default');
      // A version-1 preference (no new fields) and wrongly typed flags keep
      // the new defaults.
      final v1 = InterfaceStyleSettings.fromJson({
        'v': 1,
        'style': 'classic',
        'showClock': 'no',
        'accent': 'magenta',
        'showSideMenuPanel': 1,
        'showSystemBubbles': 'off',
      });
      expect(v1.style, InterfaceStyle.classic);
      expect(v1.showClock, isTrue);
      expect(v1.accent, AccentColor.theme);
      expect(v1.showSideMenuPanel, isFalse);
      // Saved before the option existed: the bubbles stay on.
      expect(v1.showSystemBubbles, isTrue);
    },
  );

  test('normalized clamps every fraction into 0..1', () {
    final wild = const InterfaceStyleSettings(
      transparency: 4,
      blur: -2,
      depth: double.infinity,
    ).normalized();
    expect(wild.transparency, 1);
    expect(wild.blur, 0);
    expect(wild.depth, 0.5);
  });

  test('a general style sets its surfaces, bar and motion, keeps the rest', () {
    const tuned = InterfaceStyleSettings(
      tabBarStyle: TabBarStyle.compact,
      tabIndicator: TabIndicatorStyle.underline,
      tabLabels: TabLabelMode.always,
      tabIconSize: TabIconSize.large,
      tint: GlassTint.accent,
      transparency: 0.9,
      blur: 0.9,
      accent: AccentColor.violet,
      showClock: false,
      focusIndicator: FocusIndicatorStyle.glow,
      showSideMenuPanel: true,
      showSystemBubbles: false,
    );
    final minimal = InterfaceStyleSettings.presetFor(
      InterfaceStyle.minimal,
      keep: tuned,
    );
    expect(minimal.style, InterfaceStyle.minimal);
    expect(minimal.tabBarStyle, TabBarStyle.compact);
    expect(minimal.tabIndicator, TabIndicatorStyle.underline);
    expect(minimal.blur, 0);
    expect(minimal.motion, MotionLevel.reduced);
    final classic = InterfaceStyleSettings.presetFor(InterfaceStyle.classic);
    expect(classic.transparency, lessThan(defaults.transparency));
    expect(classic.blur, lessThan(defaults.blur));
    expect(classic.tabBarStyle, TabBarStyle.classic);
    expect(classic.tabIndicator, TabIndicatorStyle.pill);
    final glass = InterfaceStyleSettings.presetFor(
      InterfaceStyle.liquidGlass,
      keep: classic,
    );
    expect(glass.transparency, defaults.transparency);
    expect(glass.blur, defaults.blur);
    expect(glass.tabBarStyle, TabBarStyle.floating);
    expect(glass.tabIndicator, TabIndicatorStyle.lens);

    // NeoStation: upstream's solid pill, LB/RB glyphs, no blur.
    final neo = InterfaceStyleSettings.presetFor(
      InterfaceStyle.neoStation,
      keep: tuned,
    );
    expect(neo.style, InterfaceStyle.neoStation);
    expect(neo.tabIndicator, TabIndicatorStyle.solid);
    expect(neo.tabBarStyle, TabBarStyle.classic);
    expect(neo.showTabBumpers, isTrue);
    expect(neo.blur, 0);
    expect(neo.motion, MotionLevel.full);
    // Personal choices survive every style change.
    for (final styled in [minimal, neo]) {
      expect(styled.tabLabels, TabLabelMode.always);
      expect(styled.tabIconSize, TabIconSize.large);
      expect(styled.tint, GlassTint.accent);
      expect(styled.accent, AccentColor.violet);
      expect(styled.showClock, isFalse);
      expect(styled.focusIndicator, FocusIndicatorStyle.glow);
      expect(styled.showSideMenuPanel, isTrue);
      expect(styled.showSystemBubbles, isFalse);
    }
    // Leaving NeoStation drops its glyphs again.
    expect(
      InterfaceStyleSettings.presetFor(
        InterfaceStyle.liquidGlass,
        keep: neo,
      ).showTabBumpers,
      isFalse,
    );
  });
}
