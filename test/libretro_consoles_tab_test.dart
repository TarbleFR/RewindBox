import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/console_manager_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/repositories/system_repository.dart';
import 'package:neostation/screens/libretro/libretro_consoles_screen.dart';
import 'package:neostation/screens/libretro/libretro_skin_manager_screen.dart';
import 'package:neostation/services/console_catalog.dart';
import 'package:neostation/services/embedded_engine_policy.dart';
import 'package:neostation/services/libretro_main_menu.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';

const _gamepads = MethodChannel('xyz.luan/gamepads');

/// Every bundled core but Azahar: the 3DS is "not included in this version".
const _coresWithout3ds = <String>[
  'nestopia', 'snes9x', 'gambatte', 'mgba', 'genesis_plus_gx', 'picodrive',
  'fbneo', 'desmume', 'mupen64plus_next', 'mednafen_psx_hw', 'ppsspp',
];

/// A store whose changes wait for [release], to hold the page busy.
class _SlowMenu extends LibretroMainMenu {
  _SlowMenu() : super(availableCores: () async => _coresWithout3ds, isReady: (_) => true);

  final release = Completer<void>();

  @override
  Future<LibretroMainMenuAddResult> showEntry(ConsoleEntry entry, SqliteConfigProvider provider) async {
    await release.future;
    return super.showEntry(entry, provider);
  }
}

/// The consoles page as the body of the main bar's consoles tab.
///
/// Build 448 replaced the Build 440 contract of this file. Then the tab
/// listed the 17 embedded libretro consoles with an "Add to the main menu" /
/// "Show in the main menu" button, and hiding stayed in Settings › Systems.
/// Now it lists every console of [ConsoleCatalog] (libretro, Dolphin,
/// ARMSX2, RPCS3, Ports, MeloNX, RetroArch-only systems) with a main-menu
/// visibility switch (which also hides) and, when the console has one, the
/// switch of its built-in engine; "Show all" and "Restore defaults" act on
/// all of them. The behaviors the old buttons guaranteed are kept and tested
/// here through the switch: a console without games is shown at once and
/// remembered, a console present through another system is not added
/// twice, a hidden console is shown again, the tab follows the main menu,
/// one change at a time keeps the bumpers from leaving the page, and every
/// text follows the twelve languages.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late SqliteConfigProvider provider;
  late LibretroMainMenu menu;
  late EmbeddedEnginePolicy policy;
  late int previous;
  late int next;

  String c(String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
      ConsoleManagerLocale.format(const Locale('en'), key, values);

  setUpAll(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('en', AppLocale.en)],
      initLanguageCode: 'en',
    );
  });

  setUp(() async {
    db = await helper.setUp();
    for (final system in const <List<String>>[
      ['nes', 'Nintendo Entertainment System'],
      ['md', 'Sega Mega Drive'],
      ['genesis', 'Sega Genesis'],
      ['3ds', 'Nintendo 3DS'],
      ['gc', 'Nintendo GameCube'],
      ['2600', 'Atari 2600'],
      ['switch', 'Nintendo Switch'],
    ]) {
      await db.insert('app_systems', {'id': system[0], 'real_name': system[1], 'folder_name': system[0]});
    }
    provider = SqliteConfigProvider();
    menu = LibretroMainMenu(availableCores: () async => _coresWithout3ds, isReady: (_) => true);
    policy = EmbeddedEnginePolicy();
    previous = 0;
    next = 0;
    // GamepadNavigation.initialize() lists the controllers: none here.
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
    // Key presses play the navigation sound: no audio engine in tests.
    SfxService().setEnabled(false);
  });

  tearDown(() async {
    SfxService().setEnabled(true);
    messenger.setMockMethodCallHandler(_gamepads, null);
    provider.dispose();
    await helper.tearDown();
  });

  Future<void> pumpTab(
    WidgetTester tester, {
    Locale locale = const Locale('en'),
    bool inMainBar = true,
    LibretroMainMenu? store,
  }) async {
    tester.view.physicalSize = const Size(1600, 30000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, child) => ChangeNotifierProvider<SqliteConfigProvider>.value(
          value: provider,
          child: MaterialApp(
            locale: locale,
            supportedLocales: const <Locale>[
              Locale('en'), Locale('fr'), Locale('de'), Locale('es'), Locale('it'), Locale('pt'),
              Locale('ru'), Locale('id'), Locale('ja'), Locale('ko'), Locale('zh'),
              Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
            ],
            // AppLocale (the confirmation's Cancel) is initialized in English
            // only; the tab's own texts come from ConsoleManagerLocale.
            localizationsDelegates: <LocalizationsDelegate<dynamic>>[
              ...GlobalMaterialLocalizations.delegates,
              if (locale.languageCode == 'en') ...FlutterLocalization.instance.localizationsDelegates,
            ],
            // The app screen's Scaffold, under which the tab is drawn.
            home: Scaffold(
              body: LibretroConsolesScreen(
                inMainBar: inMainBar,
                onPreviousTab: () => previous++,
                onNextTab: () => next++,
                mainMenu: store ?? menu,
                policy: policy,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump();
    // The page's navigation layer starts listening to the keyboard once the
    // controllers are listed (a platform call): give it real time.
    for (var round = 0; round < 3; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 10)));
      await tester.pump();
    }
  }

  Finder visible(String id) => find.byKey(ValueKey('console-visible-$id'));
  Finder engine(String id) => find.byKey(ValueKey('console-engine-$id'));
  Switch switchOf(WidgetTester tester, Finder finder) => tester.widget<Switch>(finder);

  Future<void> settle(WidgetTester tester) async {
    for (var round = 0; round < 4; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
    }
  }

  testWidgets('the tab lists every console under the header, by engine, without an app bar', (tester) async {
    await pumpTab(tester);

    expect(find.byType(AppBar), findsNothing);
    expect(find.text(c(ConsoleManagerLocale.tabTitle)), findsOneWidget);
    expect(find.text(c(ConsoleManagerLocale.tabIntro)), findsOneWidget);
    expect(find.text(c(ConsoleManagerLocale.sectionEmbedded)), findsOneWidget);
    expect(find.text(c(ConsoleManagerLocale.sectionExternal)), findsOneWidget);
    // NeoStation's library actions stay in the tab.
    expect(find.byKey(const ValueKey('libretro-library-create-folders')), findsOneWidget);
    expect(find.byKey(const ValueKey('libretro-library-move')), findsOneWidget);
    expect(ConsoleCatalog.entries.length, 85);
    for (final entry in ConsoleCatalog.entries) {
      final card = find.byKey(ValueKey('console-${entry.id}'));
      expect(card, findsOneWidget, reason: entry.id);
      expect(find.descendant(of: card, matching: find.text(entry.name)), findsOneWidget, reason: entry.id);
      expect(switchOf(tester, visible(entry.id)).value, isFalse, reason: 'nothing is in the main menu yet');
      expect(engine(entry.id), entry.hasEmbeddedEngine ? findsOneWidget : findsNothing, reason: entry.id);
      final console = entry.libretro;
      expect(find.byKey(ValueKey('libretro-console-import-${console?.id}')), console == null ? findsNothing : findsOneWidget);
      expect(find.byKey(ValueKey('libretro-console-skins-${console?.id}')), console == null ? findsNothing : findsOneWidget);
    }
    // Dolphin, ARMSX2, RPCS3, the Ports and every libretro core: switchable.
    for (final id in ['gc', 'wii', 'ps2', 'ps3', 'ports', 'nes', 'psx', 'pico']) {
      expect(switchOf(tester, engine(id)).value, isTrue, reason: id);
      expect(switchOf(tester, engine(id)).onChanged, isNotNull, reason: id);
    }
    // External apps only: MeloNX, RetroArch.
    expect(find.descendant(of: find.byKey(const ValueKey('console-switch')), matching: find.text('External app: MeloNX')), findsOneWidget);
    expect(find.descendant(of: find.byKey(const ValueKey('console-2600')), matching: find.text('External app: RetroArch')), findsOneWidget);
    // The page sits below the 46.r header.
    expect(tester.getTopLeft(find.text(c(ConsoleManagerLocale.tabTitle))).dy, greaterThan(46.r));
    // A console whose core is not in the build is shown unavailable: no
    // engine to switch, while RetroArch can still take its games.
    expect(find.byKey(const ValueKey('console-unavailable-3ds')), findsOneWidget);
    expect(switchOf(tester, engine('3ds')).onChanged, isNull);
    expect(switchOf(tester, visible('3ds')).onChanged, isNotNull);
    expect(find.byKey(const ValueKey('libretro-console-system-3ds')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('switching a console on shows it in the main menu at once, without games', (tester) async {
    await pumpTab(tester);
    await tester.tap(visible('nes'));
    await settle(tester);

    expect(provider.detectedSystems.map((s) => s.folderName), contains('nes'));
    expect(await SystemRepository.getHiddenSystems(), isEmpty);
    expect(menu.pinned, ['nes']);
    expect(switchOf(tester, visible('nes')).value, isTrue);
    expect(find.text(c(ConsoleManagerLocale.stateShown, {'systems': 'Nintendo Entertainment System'})), findsOneWidget);

    // Not only libretro consoles: GameCube (Dolphin) and an external app.
    await tester.tap(visible('gc'));
    await settle(tester);
    await tester.tap(visible('2600'));
    await settle(tester);
    expect(provider.detectedSystems.map((s) => s.folderName), containsAll(<String>['gc', '2600']));
    expect(menu.pinned, ['nes', 'gc', '2600']);
  });

  testWidgets('a console present through another system is not added twice', (tester) async {
    await SystemRepository.addDetectedSystem('genesis', 'genesis');
    await provider.refreshDetectedSystems();
    await pumpTab(tester);

    expect(find.text(c(ConsoleManagerLocale.stateShown, {'systems': 'Sega Genesis'})), findsOneWidget);
    expect(switchOf(tester, visible('md')).value, isTrue);
    expect(switchOf(tester, visible('nes')).value, isFalse);
  });

  testWidgets('switching off hides the console like Settings › Systems; on shows it again', (tester) async {
    await SystemRepository.addDetectedSystem('nes', 'nes');
    await provider.refreshDetectedSystems();
    await pumpTab(tester);

    await tester.tap(visible('nes'));
    await settle(tester);
    expect(provider.hiddenSystemFolders, contains('nes'));
    expect(find.text(c(ConsoleManagerLocale.stateHidden, {'systems': 'Nintendo Entertainment System'})), findsOneWidget);
    // Hidden, not removed: the system and its detection stay.
    expect(provider.detectedSystems.map((s) => s.folderName), contains('nes'));

    await tester.tap(visible('nes'));
    await settle(tester);
    expect(provider.hiddenSystemFolders, isNot(contains('nes')));
    expect(switchOf(tester, visible('nes')).value, isTrue);
  });

  testWidgets('the tab follows the main menu when a console arrives elsewhere', (tester) async {
    await pumpTab(tester);
    expect(switchOf(tester, visible('nes')).value, isFalse);

    // A scan or an import adds the system while the tab is shown.
    await SystemRepository.addDetectedSystem('nes', 'nes');
    await provider.refreshDetectedSystems();
    await tester.pump();

    expect(switchOf(tester, visible('nes')).value, isTrue);
    expect(find.text(c(ConsoleManagerLocale.stateShown, {'systems': 'Nintendo Entertainment System'})), findsOneWidget);
  });

  testWidgets('the engine switch is the console’s own and survives the global switch', (tester) async {
    await pumpTab(tester);
    await tester.tap(engine('nes'));
    await settle(tester);
    expect(policy.isConsoleEnabled('nes'), isFalse);
    expect(switchOf(tester, engine('nes')).value, isFalse);
    expect(find.byKey(const ValueKey('console-engine-off-nes')), findsOneWidget);
    expect(find.text(c(ConsoleManagerLocale.fallbackRetroArch)), findsOneWidget);
    final preferences = await SharedPreferences.getInstance();
    expect(preferences.getStringList(EmbeddedEnginePolicy.disabledPreferenceKey), ['nes']);

    // Settings › General off: a banner, every engine switch locked with its
    // own value, nothing rewritten.
    await tester.runAsync(() => policy.setUseEmbedded(false));
    await tester.pump();
    expect(find.byKey(const ValueKey('consoles-global-off')), findsOneWidget);
    expect(switchOf(tester, engine('nes')).value, isFalse);
    expect(switchOf(tester, engine('gc')).value, isTrue);
    expect(switchOf(tester, engine('gc')).onChanged, isNull);
    expect(find.byKey(const ValueKey('console-engine-off-gc')), findsOneWidget);
    expect(find.text(c(ConsoleManagerLocale.fallbackNone)), findsWidgets);
    expect(preferences.getStringList(EmbeddedEnginePolicy.disabledPreferenceKey), ['nes']);

    await tester.runAsync(() => policy.setUseEmbedded(true));
    await tester.pump();
    expect(find.byKey(const ValueKey('consoles-global-off')), findsNothing);
    expect(switchOf(tester, engine('gc')).onChanged, isNotNull);
    expect(find.byKey(const ValueKey('console-engine-off-gc')), findsNothing);
    expect(policy.isConsoleEnabled('nes'), isFalse, reason: 'the console keeps its own choice');
  });

  testWidgets('Show all asks first, then shows every console', (tester) async {
    await SystemRepository.addDetectedSystem('nes', 'nes');
    await provider.refreshDetectedSystems();
    await provider.toggleSystemHidden('nes');
    await pumpTab(tester);

    await tester.tap(find.byKey(const ValueKey('consoles-show-all')));
    await tester.pumpAndSettle();
    final count = ConsoleCatalog.entries.length;
    expect(find.text(c(ConsoleManagerLocale.showAllBody, {'count': count})), findsOneWidget);
    await tester.tap(find.widgetWithText(ElevatedButton, c(ConsoleManagerLocale.showAll)).last);
    await settle(tester);
    await tester.pumpAndSettle();

    expect(provider.hiddenSystemFolders, isNot(contains('nes')));
    for (final id in ['nes', 'md', 'gc', '2600', 'switch']) {
      expect(switchOf(tester, visible(id)).value, isTrue, reason: id);
    }
    // Only systems known to this test database could be added.
    expect(provider.detectedSystems.map((s) => s.folderName).toSet(),
        <String>{'nes', 'md', '3ds', 'gc', '2600', 'switch'});
  });

  testWidgets('Restore defaults shows the hidden, removes the empty additions and turns the engines back on',
      (tester) async {
    // A console with games, hidden; one added without games; an engine off.
    await SystemRepository.addDetectedSystem('genesis', 'genesis');
    await db.execute("UPDATE user_detected_systems SET rom_count = 3 WHERE app_system_id = 'genesis'")
        .catchError((Object _) {});
    await provider.refreshDetectedSystems();
    await provider.toggleSystemHidden('genesis');
    await pumpTab(tester);
    await tester.tap(visible('gc'));
    await settle(tester);
    await tester.tap(engine('ps2'));
    await settle(tester);
    expect(menu.pinned, ['gc']);
    expect(policy.isConsoleEnabled('ps2'), isFalse);

    await tester.tap(find.byKey(const ValueKey('consoles-restore-defaults')));
    await tester.pumpAndSettle();
    expect(find.text(c(ConsoleManagerLocale.restoreBody)), findsOneWidget);
    await tester.tap(find.widgetWithText(ElevatedButton, c(ConsoleManagerLocale.restoreDefaults)).last);
    await settle(tester);
    await tester.pumpAndSettle();

    expect(menu.pinned, isEmpty);
    expect(policy.isConsoleEnabled('ps2'), isTrue);
    expect(provider.hiddenSystemFolders, isEmpty);
    expect(switchOf(tester, visible('gc')).value, isFalse);
    expect(find.text(c(ConsoleManagerLocale.restoreDone)), findsOneWidget);
  });

  testWidgets('Skins opens the skin manager of the console', (tester) async {
    await pumpTab(tester);
    await tester.tap(find.byKey(const ValueKey('libretro-console-skins-gba')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    final manager = tester.widget<LibretroSkinManagerScreen>(find.byType(LibretroSkinManagerScreen));
    expect(manager.console, 'gba');
  });

  testWidgets('the filters keep the shown or the hidden consoles', (tester) async {
    await SystemRepository.addDetectedSystem('nes', 'nes');
    await SystemRepository.addDetectedSystem('gc', 'gc');
    await provider.refreshDetectedSystems();
    await provider.toggleSystemHidden('gc');
    await pumpTab(tester);

    await tester.tap(find.byKey(const ValueKey('consoles-filter-shown')));
    await tester.pump();
    expect(find.byKey(const ValueKey('console-nes')), findsOneWidget);
    expect(find.byKey(const ValueKey('console-gc')), findsNothing);
    expect(find.byKey(const ValueKey('console-snes')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('consoles-filter-hidden')));
    await tester.pump();
    expect(find.byKey(const ValueKey('console-gc')), findsOneWidget);
    expect(find.byKey(const ValueKey('console-nes')), findsNothing);

    await tester.tap(find.byKey(const ValueKey('consoles-filter-all')));
    await tester.pump();
    expect(find.byKey(const ValueKey('console-snes')), findsOneWidget);
  });

  /// One key press, past GamepadNavigation's keyboard throttle (128 ms of
  /// real time), so a press that does nothing is not merely throttled.
  Future<void> press(WidgetTester tester, LogicalKeyboardKey key) async {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 160)));
    await tester.sendKeyEvent(key);
    await tester.pump();
  }

  testWidgets('LB/RB (Q/E) switch tabs, except while a change is running', (tester) async {
    final slow = _SlowMenu();
    await pumpTab(tester, store: slow);

    await press(tester, LogicalKeyboardKey.keyE);
    expect(next, 1);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect(previous, 1);

    // Leaving the tab would dispose the page in the middle of the change.
    await tester.tap(visible('nes'));
    await tester.pump();
    await press(tester, LogicalKeyboardKey.keyE);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect((previous, next), (1, 1));
    expect(switchOf(tester, visible('snes')).onChanged, isNull, reason: 'one change at a time');

    slow.release.complete();
    await settle(tester);
    expect(provider.detectedSystems.map((s) => s.folderName), contains('nes'));
    await press(tester, LogicalKeyboardKey.keyE);
    expect(next, 2);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect(previous, 2);
  });

  testWidgets('as a pushed page it keeps its app bar and leaves the bumpers alone', (tester) async {
    await pumpTab(tester, inMainBar: false);

    expect(find.byType(AppBar), findsOneWidget);
    expect(find.descendant(of: find.byType(AppBar), matching: find.text(c(ConsoleManagerLocale.tabTitle))), findsOneWidget);
    await press(tester, LogicalKeyboardKey.keyE);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect((previous, next), (0, 0));
  });

  testWidgets('the tab is translated in the twelve languages', (tester) async {
    final english = ConsoleManagerLocale.values['en']!;
    for (final language in ConsoleManagerLocale.values.keys) {
      final locale = language == 'zh_Hant'
          ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
          : Locale(language);
      final texts = ConsoleManagerLocale.values[language]!;
      await pumpTab(tester, locale: locale);
      for (final key in [
        ConsoleManagerLocale.tabIntro,
        ConsoleManagerLocale.sectionEmbedded,
        ConsoleManagerLocale.sectionExternal,
        ConsoleManagerLocale.showAll,
        ConsoleManagerLocale.unavailable,
      ]) {
        expect(find.text(texts[key]!), findsWidgets, reason: '$language:$key');
      }
      expect(find.text(texts[ConsoleManagerLocale.visibleLabel]!), findsWidgets, reason: language);
      expect(find.text(LibretroLocale.values[language]!['libraryTitle']!), findsOneWidget, reason: language);
      if (language != 'en') {
        expect(find.text(english[ConsoleManagerLocale.visibleLabel]!), findsNothing, reason: '$language: no English fallback');
      }
    }
  });
}
