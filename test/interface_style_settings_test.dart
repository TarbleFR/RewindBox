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

  test('style presets keep the navigation choices and reset the surfaces', () {
    const tuned = InterfaceStyleSettings(
      tabBarStyle: TabBarStyle.classic,
      tabLabels: TabLabelMode.always,
      tint: GlassTint.accent,
      transparency: 0.9,
      blur: 0.9,
    );
    final minimal = InterfaceStyleSettings.presetFor(
      InterfaceStyle.minimal,
      keep: tuned,
    );
    expect(minimal.style, InterfaceStyle.minimal);
    expect(minimal.tabBarStyle, TabBarStyle.classic);
    expect(minimal.tabLabels, TabLabelMode.always);
    expect(minimal.tint, GlassTint.accent);
    expect(minimal.blur, 0);
    expect(minimal.motion, MotionLevel.reduced);
    final classic = InterfaceStyleSettings.presetFor(InterfaceStyle.classic);
    expect(classic.transparency, lessThan(defaults.transparency));
    expect(classic.blur, lessThan(defaults.blur));
    final glass = InterfaceStyleSettings.presetFor(
      InterfaceStyle.liquidGlass,
      keep: classic,
    );
    expect(glass.transparency, defaults.transparency);
    expect(glass.blur, defaults.blur);
  });
}
