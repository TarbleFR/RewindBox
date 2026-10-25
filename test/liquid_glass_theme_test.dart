import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/themes/corner_radii.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';

/// The resolver must keep every surface readable whatever the user chooses,
/// reproduce the previous appearance at the default settings, and give every
/// built-in palette the same component themes.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const roles = GlassRole.values;
  final palettes = ThemeProvider.availableThemes;

  test('every built-in palette composes with the glass tokens and themes', () {
    for (final entry in palettes.entries) {
      final composed = applyLiquidGlass(
        entry.value,
        InterfaceStyleSettings.defaults,
      );
      final glass = composed.extension<LiquidGlassTheme>();
      expect(glass, isNotNull, reason: entry.key);
      expect(composed.extension<ChromeSurface>(), isNotNull, reason: entry.key);
      expect(composed.extension<CornerRadii>(), isNotNull, reason: entry.key);
      expect(composed.dialogTheme.elevation, 0, reason: entry.key);
      expect(
        composed.dialogTheme.backgroundColor,
        isNotNull,
        reason: entry.key,
      );
      expect(composed.appBarTheme.backgroundColor, Colors.transparent);
      expect(composed.popupMenuTheme.color, isNotNull);
      expect(composed.bottomSheetTheme.backgroundColor, isNotNull);
      expect(composed.cardTheme.elevation, 0);
      expect(composed.inputDecorationTheme.filled, isTrue);
      // The dialog surface is translucent, never fully opaque.
      final alpha = composed.dialogTheme.backgroundColor!.a;
      expect(alpha, inInclusiveRange(0.5, 0.95), reason: entry.key);
    }
  });

  test(
    'the default settings reproduce the historical ChromeSurface values',
    () {
      final dark = palettes['dark']!;
      final glass = const LiquidGlassTheme();
      expect(glass.fillAlpha(dark, GlassRole.panel), closeTo(0.48, 1e-9));
      expect(glass.fillAlpha(dark, GlassRole.rail), closeTo(0.52, 1e-9));
      expect(glass.fillAlpha(dark, GlassRole.modal), closeTo(0.60, 1e-9));
      expect(glass.fillAlpha(dark, GlassRole.chrome), closeTo(0.66, 1e-9));
      expect(glass.fillAlpha(dark, GlassRole.pill), closeTo(0.70, 1e-9));
      expect(glass.fillAlpha(dark, GlassRole.card), closeTo(0.18, 1e-9));
      expect(glass.blurSigma(dark, GlassRole.panel), closeTo(2.4, 1e-9));
      expect(glass.blurSigma(dark, GlassRole.modal), closeTo(3.0, 1e-9));
      expect(glass.fillScale, 1);
      expect(glass.blurScale, 1);
      expect(glass.intensityScale, 1);
      expect(glass.depthScale, 1);
      expect(glass.radiusScale, 1);
    },
  );

  test('every slider extreme keeps each role inside its readable range', () {
    for (final theme in palettes.values) {
      for (final transparency in [0.0, 0.5, 1.0]) {
        for (final contrast in [0.0, 1.0]) {
          for (final style in InterfaceStyle.values) {
            final glass = LiquidGlassTheme(
              settings: InterfaceStyleSettings(
                style: style,
                transparency: transparency,
                contrast: contrast,
              ),
            );
            for (final role in roles) {
              final alpha = glass.fillAlpha(theme, role);
              expect(alpha, inInclusiveRange(0.12, 0.97));
              if (role != GlassRole.card) {
                expect(alpha, greaterThanOrEqualTo(0.30));
              }
              if (style == InterfaceStyle.classic) {
                expect(alpha, greaterThanOrEqualTo(0.84));
              }
              if (style == InterfaceStyle.minimal) {
                expect(alpha, greaterThanOrEqualTo(0.94));
              }
              final high = glass.fillAlpha(theme, role, highContrast: true);
              expect(high, greaterThanOrEqualTo(0.92));
            }
          }
        }
      }
    }
  });

  test(
    'blur is removed by the minimal style, Increase Contrast and a zero budget',
    () {
      final dark = palettes['dark']!;
      const minimal = LiquidGlassTheme(
        settings: InterfaceStyleSettings(
          style: InterfaceStyle.minimal,
          blur: 1,
        ),
      );
      const budgetless = LiquidGlassTheme(blurBudget: 0);
      const full = LiquidGlassTheme(settings: InterfaceStyleSettings(blur: 1));
      for (final role in roles) {
        expect(minimal.blurSigma(dark, role), 0);
        expect(budgetless.blurSigma(dark, role), 0);
        expect(full.blurSigma(dark, role, highContrast: true), 0);
        expect(full.blurSigma(dark, role), greaterThan(0));
      }
      expect(minimal.sheenEnabled, isFalse);
      expect(minimal.shadowsEnabled, isFalse);
      expect(
        const LiquidGlassTheme(
          settings: InterfaceStyleSettings(blur: 0),
        ).blurEnabled,
        isFalse,
      );
      expect(
        const LiquidGlassTheme(blurBudget: 0.5).blurScale,
        closeTo(0.5, 1e-9),
      );
    },
  );

  test(
    'corner radius, density and depth scale the shape and spacing tokens',
    () {
      final dark = palettes['dark']!;
      final rounder = applyLiquidGlass(
        dark,
        const InterfaceStyleSettings(cornerRadius: 1),
      );
      final sharper = applyLiquidGlass(
        dark,
        const InterfaceStyleSettings(cornerRadius: 0),
      );
      expect(
        rounder.extension<CornerRadii>()!.rawExternal,
        greaterThan(dark.extension<CornerRadii>()!.rawExternal),
      );
      expect(
        sharper.extension<CornerRadii>()!.rawExternal,
        lessThan(dark.extension<CornerRadii>()!.rawExternal),
      );
      const compact = LiquidGlassTheme(
        settings: InterfaceStyleSettings(density: InterfaceDensity.compact),
      );
      const comfortable = LiquidGlassTheme(
        settings: InterfaceStyleSettings(density: InterfaceDensity.comfortable),
      );
      expect(compact.radiusScale, 1);
      expect(
        const LiquidGlassTheme(
          settings: InterfaceStyleSettings(depth: 0),
        ).depthScale,
        0,
      );
      expect(
        const LiquidGlassTheme(depthBudget: 0.5).depthScale,
        closeTo(0.5, 1e-9),
      );
      // Density ordering holds without ScreenUtil: compare the unscaled design.
      expect(
        comfortable.settings.density.index,
        greaterThan(compact.settings.density.index),
      );
    },
  );

  test(
    'lerp interpolates the sliders and switches the choices at midpoint',
    () {
      const a = LiquidGlassTheme(
        settings: InterfaceStyleSettings(
          transparency: 0,
          style: InterfaceStyle.liquidGlass,
        ),
      );
      const b = LiquidGlassTheme(
        settings: InterfaceStyleSettings(
          transparency: 1,
          style: InterfaceStyle.minimal,
        ),
        blurBudget: 0,
      );
      final quarter = a.lerp(b, 0.25);
      expect(quarter.settings.transparency, closeTo(0.25, 1e-9));
      expect(quarter.settings.style, InterfaceStyle.liquidGlass);
      expect(quarter.blurBudget, closeTo(0.75, 1e-9));
      final late = a.lerp(b, 0.75);
      expect(late.settings.style, InterfaceStyle.minimal);
      expect(a.lerp(null, 0.5), a);
    },
  );

  test('the tint colour follows the chosen palette role', () {
    final dark = palettes['dark']!;
    expect(const LiquidGlassTheme().tintColor(dark), isNull);
    expect(
      const LiquidGlassTheme(
        settings: InterfaceStyleSettings(tint: GlassTint.accent),
      ).tintColor(dark),
      dark.colorScheme.primary,
    );
    expect(
      const LiquidGlassTheme(
        settings: InterfaceStyleSettings(tint: GlassTint.secondary),
      ).surfaceColor(dark),
      isNot(dark.colorScheme.surface),
    );
  });

  test('ThemeProvider composes and caches the glass theme', () {
    final provider = ThemeProvider.testing();
    final first = provider.currentTheme;
    expect(first.extension<LiquidGlassTheme>(), isNotNull);
    expect(identical(first, provider.currentTheme), isTrue);
    final preview = provider.previewTheme(
      const InterfaceStyleSettings(style: InterfaceStyle.minimal),
    );
    expect(
      preview.extension<LiquidGlassTheme>()!.style,
      InterfaceStyle.minimal,
    );
    expect(provider.interfaceStyle, InterfaceStyleSettings.defaults);
    expect(identical(first, provider.currentTheme), isTrue);
  });
}
