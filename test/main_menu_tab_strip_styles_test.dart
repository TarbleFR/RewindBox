import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/main_menu_tab_strip.dart';

/// Every navigation-bar option keeps the geometry the navigation relies on:
/// equal adjacent cells and an indicator aligned with the selected cell.
void main() {
  Future<void> pump(
    WidgetTester tester,
    InterfaceStyleSettings settings, {
    NavTab selected = NavTab.search,
    bool labels = true,
  }) async {
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, child) => MaterialApp(
          theme: applyLiquidGlass(AppThemes.darkTheme, settings),
          home: Scaffold(
            body: Center(
              child: MainMenuTabStrip(
                tabs: NavTab.values,
                selected: selected,
                cellExtent: 32,
                tabBuilder: (tab) => const SizedBox.expand(),
                iconBuilder: (tab) => const Icon(Icons.circle, size: 16),
                labelBuilder: labels ? (tab, selected) => Text(tab.name) : null,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();
  }

  Rect cell(WidgetTester tester, NavTab tab) =>
      tester.getRect(find.byKey(ValueKey('main-menu-cell-${tab.name}')));

  for (final bar in TabBarStyle.values) {
    for (final indicator in TabIndicatorStyle.values) {
      for (final labelMode in TabLabelMode.values) {
        for (final size in TabIconSize.values) {
          testWidgets(
            'bar=$bar indicator=$indicator labels=$labelMode icons=$size',
            (tester) async {
              await tester.binding.setSurfaceSize(const Size(844, 390));
              addTearDown(() => tester.binding.setSurfaceSize(null));
              await pump(
                tester,
                InterfaceStyleSettings(
                  tabBarStyle: bar,
                  tabIndicator: indicator,
                  tabLabels: labelMode,
                  tabIconSize: size,
                ),
              );
              final ordered = inNavTabDisplayOrder(NavTab.values);
              final first = cell(tester, ordered.first);
              for (var i = 1; i < ordered.length; i++) {
                final rect = cell(tester, ordered[i]);
                expect(rect.width, closeTo(first.width, 0.01));
                expect(rect.height, closeTo(first.height, 0.01));
                expect(rect.top, closeTo(first.top, 0.01));
                expect(
                  rect.left,
                  closeTo(cell(tester, ordered[i - 1]).right, 0.01),
                );
              }
              final selected = cell(tester, NavTab.search);
              final indicatorRect = tester.getRect(
                find.byKey(const ValueKey('main-menu-tab-indicator')),
              );
              expect(indicatorRect.left, closeTo(selected.left, 0.01));
              expect(indicatorRect.width, closeTo(selected.width, 0.01));
              // Labels add a band under the square icon area only when shown.
              if (labelMode == TabLabelMode.hidden) {
                expect(first.height, closeTo(first.width, 0.01));
                expect(find.text('search'), findsNothing);
              } else {
                expect(first.height, greaterThan(first.width));
                expect(find.text('search'), findsWidgets);
                if (labelMode == TabLabelMode.selectedOnly) {
                  expect(find.text('systems'), findsNothing);
                } else {
                  expect(find.text('systems'), findsWidgets);
                }
              }
              expect(tester.takeException(), isNull);
            },
          );
        }
      }
    }
  }

  testWidgets('icon size scales the cells', (tester) async {
    await tester.binding.setSurfaceSize(const Size(844, 390));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await pump(
      tester,
      const InterfaceStyleSettings(tabIconSize: TabIconSize.small),
      labels: false,
    );
    final small = cell(tester, NavTab.systems).width;
    await pump(
      tester,
      const InterfaceStyleSettings(tabIconSize: TabIconSize.large),
      labels: false,
    );
    final large = cell(tester, NavTab.systems).width;
    expect(large, greaterThan(small));
    await pump(
      tester,
      const InterfaceStyleSettings(tabBarStyle: TabBarStyle.compact),
      labels: false,
    );
    final compact = cell(tester, NavTab.systems).width;
    await pump(tester, const InterfaceStyleSettings(), labels: false);
    expect(compact, lessThan(cell(tester, NavTab.systems).width));
  });

  testWidgets('the capsule blurs only when the glass settings allow it', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(844, 390));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final blurLayer = find.byKey(const ValueKey('main-menu-capsule-blur'));
    await pump(tester, const InterfaceStyleSettings(), labels: false);
    expect(blurLayer, findsOneWidget);
    await pump(tester, const InterfaceStyleSettings(blur: 0), labels: false);
    expect(blurLayer, findsNothing);
    await pump(
      tester,
      const InterfaceStyleSettings(style: InterfaceStyle.minimal),
      labels: false,
    );
    expect(blurLayer, findsNothing);
    await pump(
      tester,
      const InterfaceStyleSettings(tabBarStyle: TabBarStyle.classic),
      labels: false,
    );
    expect(blurLayer, findsNothing, reason: 'the classic bar is a flat strip');
  });

  testWidgets('the essential motion level settles the lens immediately', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(844, 390));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    const essential = InterfaceStyleSettings(motion: MotionLevel.essential);
    await pump(tester, essential, selected: NavTab.systems, labels: false);
    await pump(tester, essential, selected: NavTab.settings, labels: false);
    expect(tester.binding.transientCallbackCount, 0);
    expect(
      tester
          .getRect(find.byKey(const ValueKey('main-menu-tab-indicator')))
          .left,
      closeTo(cell(tester, NavTab.settings).left, 0.01),
    );
  });
}
