import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/main_menu_tab_strip.dart';

void main() {
  for (final hidden in [
    <NavTab>{},
    {NavTab.search},
    {NavTab.achievements},
    {NavTab.search, NavTab.achievements},
  ]) {
    testWidgets(
      'AirPlay shares equal cells and selection remains aligned: $hidden',
      (tester) async {
        await tester.binding.setSurfaceSize(const Size(844, 390));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        final tabs = NavTab.values
            .where((tab) => !hidden.contains(tab))
            .toList();
        for (final selected in tabs) {
          await tester.pumpWidget(
            ScreenUtilInit(
              designSize: const Size(640, 480),
              builder: (context, child) => MaterialApp(
                home: Scaffold(
                  body: Center(
                    child: MainMenuTabStrip(
                      tabs: tabs,
                      selected: selected,
                      showAirPlay: true,
                      tabBuilder: (tab) =>
                          TextButton(onPressed: () {}, child: Text(tab.name)),
                    ),
                  ),
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          final strip = find.byKey(const ValueKey('main-menu-tab-strip'));
          final airPlay = find.byKey(const ValueKey('main-menu-airplay-cell'));
          expect(find.descendant(of: strip, matching: airPlay), findsOneWidget);
          final airRect = tester.getRect(airPlay);
          final systemRect = tester.getRect(
            find.byKey(const ValueKey('main-menu-cell-systems')),
          );
          expect(airRect.size, systemRect.size);
          expect(airRect.top, systemRect.top);
          if (!hidden.contains(NavTab.search)) {
            expect(
              tester
                  .getRect(find.byKey(const ValueKey('main-menu-cell-search')))
                  .right,
              airRect.left,
            );
          }
          if (!hidden.contains(NavTab.achievements)) {
            expect(
              airRect.right,
              tester
                  .getRect(
                    find.byKey(const ValueKey('main-menu-cell-achievements')),
                  )
                  .left,
            );
          }
          final selectedRect = tester.getRect(
            find.byKey(ValueKey('main-menu-cell-${selected.name}')),
          );
          final indicatorRect = tester.getRect(
            find.byKey(const ValueKey('main-menu-tab-indicator')),
          );
          expect(indicatorRect.left, selectedRect.left);
          expect(indicatorRect.width, selectedRect.width);
          expect(tester.takeException(), isNull);
        }
      },
    );
  }
  testWidgets('AirPlay is optional without shifting canonical tab identities', (
    tester,
  ) async {
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, child) => MaterialApp(
          home: MainMenuTabStrip(
            tabs: NavTab.values,
            selected: NavTab.settings,
            showAirPlay: false,
            tabBuilder: (tab) => Text(tab.name),
          ),
        ),
      ),
    );
    expect(find.byKey(const ValueKey('main-menu-airplay-cell')), findsNothing);
    expect(NavTab.achievements.index, 2);
    expect(NavTab.settings.index, 4);
    // Build 438: the consoles tab is appended, it does not renumber the others.
    expect(NavTab.consoles.index, 6);
    expect(NavTab.library.index, 5);
  });

  // Build 438: the consoles tab (index 6) is drawn right after Systems and
  // before Search, in a cell like the others, whatever order the tabs come in.
  for (final hidden in [
    <NavTab>{},
    {NavTab.search},
    {NavTab.achievements},
    {NavTab.search, NavTab.achievements},
    {NavTab.search, NavTab.achievements, NavTab.scraper},
  ]) {
    testWidgets(
      'the consoles cell sits after Systems and before Search: $hidden',
      (tester) async {
        await tester.binding.setSurfaceSize(const Size(844, 390));
        addTearDown(() => tester.binding.setSurfaceSize(null));
        // Canonical order on purpose: consoles comes last in NavTab.values.
        final tabs = NavTab.values
            .where((tab) => !hidden.contains(tab))
            .toList();
        for (final selected in tabs) {
          await tester.pumpWidget(
            ScreenUtilInit(
              designSize: const Size(640, 480),
              builder: (context, child) => MaterialApp(
                home: Scaffold(
                  body: Center(
                    child: MainMenuTabStrip(
                      tabs: tabs,
                      selected: selected,
                      showAirPlay: true,
                      tabBuilder: (tab) =>
                          TextButton(onPressed: () {}, child: Text(tab.name)),
                    ),
                  ),
                ),
              ),
            ),
          );
          await tester.pumpAndSettle();
          Rect cell(NavTab tab) => tester.getRect(
            find.byKey(ValueKey('main-menu-cell-${tab.name}')),
          );
          final systems = cell(NavTab.systems);
          final consoles = cell(NavTab.consoles);
          final airPlay = tester.getRect(
            find.byKey(const ValueKey('main-menu-airplay-cell')),
          );
          expect(consoles.size, systems.size);
          expect(consoles.top, systems.top);
          expect(consoles.left, systems.right);
          if (hidden.contains(NavTab.search)) {
            expect(airPlay.left, consoles.right);
          } else {
            expect(cell(NavTab.search).left, consoles.right);
            expect(airPlay.left, cell(NavTab.search).right);
          }
          if (!hidden.contains(NavTab.achievements)) {
            expect(airPlay.right, cell(NavTab.achievements).left);
          }
          // Left-to-right order of every cell is the display order.
          final drawn = [...tabs]
            ..sort((a, b) => cell(a).left.compareTo(cell(b).left));
          expect(drawn, inNavTabDisplayOrder(tabs));
          final indicator = tester.getRect(
            find.byKey(const ValueKey('main-menu-tab-indicator')),
          );
          expect(indicator.left, cell(selected).left);
          expect(indicator.width, cell(selected).width);
          expect(tester.takeException(), isNull);
        }
      },
    );
  }

  testWidgets('the consoles icon is a controller with a "+" in the tab tint', (
    tester,
  ) async {
    const tint = Color(0xFF123456);
    late double box;
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, child) {
          box = 16.r;
          return MaterialApp(
            home: Row(
              children: [
                NavTabIcon(
                  key: const ValueKey('consoles-icon'),
                  spec: navTabSpec(NavTab.consoles),
                  tint: tint,
                ),
                NavTabIcon(
                  key: const ValueKey('search-icon'),
                  spec: navTabSpec(NavTab.search),
                  tint: tint,
                ),
              ],
            ),
          );
        },
      ),
    );
    final consoles = find.byKey(const ValueKey('consoles-icon'));
    final icons = tester
        .widgetList<Icon>(
          find.descendant(of: consoles, matching: find.byType(Icon)),
        )
        .toList();
    expect(icons.map((icon) => icon.icon), [
      Symbols.sports_esports_rounded,
      Symbols.add_rounded,
    ]);
    expect(icons.every((icon) => icon.color == tint), isTrue);
    // Same 16.r box as every other tab icon (the cell's padding is shared).
    expect(tester.getSize(consoles), Size(box, box));
    final search = find.byKey(const ValueKey('search-icon'));
    expect(tester.getSize(search), Size(box, box));
    final searchIcon = tester.widget<Icon>(
      find.descendant(of: search, matching: find.byType(Icon)),
    );
    expect(searchIcon.icon, Symbols.search_rounded);
    expect(searchIcon.color, tint);
    expect(tester.takeException(), isNull);
  });
}
