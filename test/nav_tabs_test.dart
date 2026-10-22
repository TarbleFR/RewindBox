import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/l10n/neoplay_locale.dart';
import 'package:neostation/models/config_model.dart';
import 'package:neostation/utils/nav_tabs.dart';

/// Build 440: the consoles tab (a console with a "+") is drawn right after
/// Systems and before Search on iOS, is cycled in that order by LB/RB, and
/// can never be hidden; the canonical tab indices do not move.
void main() {
  const config = ConfigModel.empty;

  void onPlatform(TargetPlatform platform) {
    debugDefaultTargetPlatformOverride = platform;
    addTearDown(() => debugDefaultTargetPlatformOverride = null);
  }

  test('canonical indices are unchanged; the consoles tab is appended', () {
    expect(NavTab.values.map((tab) => tab.index), [0, 1, 2, 3, 4, 5, 6, 7]);
    expect(NavTab.systems.index, 0);
    expect(NavTab.search.index, 1);
    expect(NavTab.achievements.index, 2);
    expect(NavTab.scraper.index, 3);
    expect(NavTab.settings.index, 4);
    expect(NavTab.library.index, 5);
    expect(NavTab.consoles.index, 6);
    expect(NavTab.airplay.index, 7);
  });

  test('the display order places every tab once, consoles after Systems', () {
    expect(navTabDisplayOrder.toSet(), NavTab.values.toSet());
    expect(navTabDisplayOrder.length, NavTab.values.length);
    expect(navTabDisplayOrder.take(3), [
      NavTab.systems,
      NavTab.consoles,
      NavTab.search,
    ]);
    expect(
      inNavTabDisplayOrder(NavTab.values),
      navTabDisplayOrder,
      reason: 'canonical order in, display order out',
    );
  });

  test('on iOS the strip reads Systems, Consoles, Search…', () {
    onPlatform(TargetPlatform.iOS);
    expect(visibleNavTabs(config), [
      NavTab.systems,
      NavTab.consoles,
      NavTab.search,
      NavTab.airplay,
      NavTab.achievements,
      NavTab.scraper,
      NavTab.settings,
      NavTab.library,
    ]);
  });

  test('the consoles tab cannot be hidden, whatever the other toggles', () {
    onPlatform(TargetPlatform.iOS);
    final everythingHidden = config.copyWith(
      hideTabSearch: true,
      hideTabAchievements: true,
      hideTabScraper: true,
    );
    expect(visibleNavTabs(everythingHidden), [
      NavTab.systems,
      NavTab.consoles,
      NavTab.airplay,
      NavTab.settings,
      NavTab.library,
    ]);
    expect(hidableNavTabs(), isNot(contains(NavTab.consoles)));
    expect(hidableNavTabs(), [
      NavTab.search,
      NavTab.airplay,
      NavTab.achievements,
      NavTab.scraper,
    ]);
    expect(navTabSpec(NavTab.consoles).isHidable, isFalse);
  });

  test('the consoles tab does not exist outside iOS', () {
    for (final platform in [
      TargetPlatform.android,
      TargetPlatform.windows,
      TargetPlatform.macOS,
    ]) {
      onPlatform(platform);
      expect(
        visibleNavTabs(config),
        isNot(contains(NavTab.consoles)),
        reason: '$platform',
      );
      expect(visibleNavTabs(config).first, NavTab.systems);
      expect(
        visibleNavTabs(config)[1],
        NavTab.search,
        reason: 'the strip is unchanged there',
      );
      expect(hidableNavTabs(), isNot(contains(NavTab.consoles)));
      expect(visibleNavTabs(config), isNot(contains(NavTab.airplay)));
    }
  });

  test('LB/RB go Systems → Consoles → Search and wrap at both ends', () {
    onPlatform(TargetPlatform.iOS);
    final visible = visibleNavTabs(config);
    expect(cycleNavTab(visible, NavTab.systems, 1), NavTab.consoles);
    expect(cycleNavTab(visible, NavTab.consoles, 1), NavTab.search);
    expect(cycleNavTab(visible, NavTab.search, -1), NavTab.consoles);
    expect(cycleNavTab(visible, NavTab.consoles, -1), NavTab.systems);
    expect(cycleNavTab(visible, NavTab.systems, -1), NavTab.library);
    expect(cycleNavTab(visible, NavTab.library, 1), NavTab.systems);

    // A full RB round visits every tab once, in display order.
    var tab = NavTab.systems;
    final visited = <NavTab>[];
    for (var i = 0; i < visible.length; i++) {
      visited.add(tab);
      tab = cycleNavTab(visible, tab, 1)!;
    }
    expect(visited, visible);
    expect(tab, NavTab.systems);
  });

  test(
    'hidden tabs are skipped and a vanished tab restarts from the strip start',
    () {
      onPlatform(TargetPlatform.iOS);
      final visible = visibleNavTabs(config.copyWith(hideTabSearch: true));
      expect(cycleNavTab(visible, NavTab.consoles, 1), NavTab.airplay);
      expect(cycleNavTab(visible, NavTab.airplay, 1), NavTab.achievements);
      expect(cycleNavTab(visible, NavTab.achievements, -1), NavTab.airplay);
      expect(cycleNavTab(visible, NavTab.airplay, -1), NavTab.consoles);
      // Search was hidden while selected: step from Systems.
      expect(cycleNavTab(visible, NavTab.search, 1), NavTab.consoles);
      expect(cycleNavTab(visible, NavTab.search, -1), NavTab.library);
      expect(cycleNavTab(const [], NavTab.systems, 1), isNull);
    },
  );

  test('AirPlay is visited once between Search and Achievements in both directions', () {
    onPlatform(TargetPlatform.iOS);
    final tabs = visibleNavTabs(config);
    expect(cycleNavTab(tabs, NavTab.search, 1), NavTab.airplay);
    expect(cycleNavTab(tabs, NavTab.airplay, 1), NavTab.achievements);
    expect(cycleNavTab(tabs, NavTab.achievements, -1), NavTab.airplay);
    expect(cycleNavTab(tabs, NavTab.airplay, -1), NavTab.search);
    expect(tabs.where((tab) => tab == NavTab.airplay).length, 1);
  });

  testWidgets(
    'AirPlay labels reuse every supported catalogue including zh-Hant',
    (tester) async {
      for (final entry in NeoPlayLocale.values.entries) {
        final locale = entry.key == 'zh_Hant'
            ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
            : Locale(entry.key);
        late String label;
        await tester.pumpWidget(
          Localizations(
            locale: locale,
            delegates: const [DefaultWidgetsLocalizations.delegate],
            child: Builder(
              builder: (context) {
                label = navTabLabel(context, NavTab.airplay);
                return const SizedBox();
              },
            ),
          ),
        );
        expect(
          label,
          'AirPlay · ${entry.value['subtitle']}',
          reason: entry.key,
        );
      }
    },
  );

  test('on Android LB/RB keep the previous order', () {
    onPlatform(TargetPlatform.android);
    final visible = visibleNavTabs(config);
    expect(cycleNavTab(visible, NavTab.systems, 1), NavTab.search);
    expect(cycleNavTab(visible, NavTab.search, -1), NavTab.systems);
  });

  testWidgets('the consoles tab is named in the twelve languages', (
    tester,
  ) async {
    expect(
      navTabSpec(NavTab.consoles).labelCatalog,
      NavTabLabelCatalog.libretro,
    );
    final english = LibretroLocale.values['en']!['consolesTab']!;
    for (final language in LibretroLocale.values.keys) {
      final locale = language == 'zh_Hant'
          ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
          : Locale(language);
      late String label;
      await tester.pumpWidget(
        Localizations(
          locale: locale,
          delegates: const [DefaultWidgetsLocalizations.delegate],
          child: Builder(
            builder: (context) {
              label = navTabLabel(context, NavTab.consoles);
              return const SizedBox();
            },
          ),
        ),
      );
      expect(
        label,
        LibretroLocale.values[language]!['consolesTab'],
        reason: language,
      );
      expect(label.trim(), isNotEmpty, reason: language);
      if (language != 'en') expect(label, isNot(english), reason: language);
    }
    // Traditional Chinese from a region as well as from the script.
    for (final region in ['TW', 'HK', 'MO']) {
      expect(
        LibretroLocale.forLocale(Locale('zh', region), 'consolesTab'),
        LibretroLocale.values['zh_Hant']!['consolesTab'],
      );
    }
    expect(
      LibretroLocale.forLocale(const Locale('zh'), 'consolesTab'),
      LibretroLocale.values['zh']!['consolesTab'],
    );
  });
}
