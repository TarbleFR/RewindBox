import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/setting_row.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/settings_card_row.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/widgets/custom_radio_button.dart';
import 'package:neostation/widgets/glass/glass_surface.dart';

/// Independent settings bubbles never touch: the standard gap separates
/// them, the category gap is wider, and every density keeps a visible gap.
void main() {
  Future<void> pump(
    WidgetTester tester,
    InterfaceStyleSettings settings,
    Widget child,
  ) async {
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, _) => MaterialApp(
          theme: applyLiquidGlass(AppThemes.darkTheme, settings),
          home: Scaffold(body: child),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Widget list() => ListView(
    padding: EdgeInsets.zero,
    children: const [
      SettingRow(
        key: ValueKey('row-a'),
        title: 'A',
        subtitle: 'a',
        focused: false,
        trailing: SizedBox(width: 10, height: 10),
      ),
      GlassGap(),
      SettingRow(
        key: ValueKey('row-b'),
        title: 'B',
        subtitle: 'b',
        focused: true,
        trailing: SizedBox(width: 10, height: 10),
      ),
      GlassSectionHeader(label: 'Section'),
      SettingsCardRow(
        key: ValueKey('card-c'),
        icon: Icons.folder,
        title: 'C',
        subtitle: 'c',
        selected: false,
      ),
      SettingsCardRow(
        key: ValueKey('card-d'),
        icon: Icons.folder,
        title: 'D',
        subtitle: 'd',
        selected: true,
      ),
      GlassGap(),
      CustomRadioButton<int>(
        key: ValueKey('radio-e'),
        value: 1,
        groupValue: 1,
        onChanged: _ignore,
        title: 'E',
      ),
    ],
  );

  for (final density in InterfaceDensity.values) {
    testWidgets('bubbles keep a visible gap at $density', (tester) async {
      await tester.binding.setSurfaceSize(const Size(956, 440));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await pump(tester, InterfaceStyleSettings(density: density), list());
      // The visible bubble is the clipped surface, inside any margin or shadow.
      Rect surface(String key) => tester.getRect(
        find
            .descendant(
              of: find.byKey(ValueKey(key)),
              matching: find.byType(ClipRRect),
            )
            .first,
      );
      final a = surface('row-a');
      final b = surface('row-b');
      final c = surface('card-c');
      final d = surface('card-d');
      final e = surface('radio-e');
      // Two independent bubbles: the standard gap, at least ten points.
      expect(b.top - a.bottom, greaterThanOrEqualTo(10));
      // A category header separates its group by more than the bubble gap.
      expect(c.top - b.bottom, greaterThan(b.top - a.bottom));
      // Card rows carry the gap themselves; a radio bubble follows the gap.
      expect(d.top - c.bottom, greaterThanOrEqualTo(10));
      expect(e.top - d.bottom, greaterThanOrEqualTo(10));
      // Every bubble shares the same left edge and the same radius token.
      for (final rect in [b, c, d, e]) {
        expect(rect.left, closeTo(a.left, 0.01));
        expect(rect.width, closeTo(a.width, 0.01));
      }
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('the comfortable density opens the gaps, compact tightens them', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(956, 440));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    Future<double> gap(InterfaceDensity density) async {
      await pump(tester, InterfaceStyleSettings(density: density), list());
      final a = tester.getRect(find.byKey(const ValueKey('row-a')));
      final b = tester.getRect(find.byKey(const ValueKey('row-b')));
      return b.top - a.bottom;
    }

    final compact = await gap(InterfaceDensity.compact);
    final regular = await gap(InterfaceDensity.regular);
    final comfortable = await gap(InterfaceDensity.comfortable);
    expect(compact, lessThan(regular));
    expect(regular, lessThan(comfortable));
  });

  testWidgets('a focused bubble draws the accent ring, not a different fill', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(956, 440));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await pump(tester, const InterfaceStyleSettings(), list());
    final surfaces = tester
        .widgetList<GlassSurface>(find.byType(GlassSurface))
        .toList();
    expect(surfaces.where((s) => s.focused).length, 2);
    expect(surfaces.every((s) => s.role == GlassRole.bubble), isTrue);
  });
}

void _ignore(int? _) {}
