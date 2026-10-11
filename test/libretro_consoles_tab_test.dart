import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/repositories/system_repository.dart';
import 'package:neostation/screens/libretro/libretro_consoles_screen.dart';
import 'package:neostation/screens/libretro/libretro_skin_manager_screen.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/services/libretro_main_menu.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:provider/provider.dart';

import 'database_test_helper.dart';

const _gamepads = MethodChannel('xyz.luan/gamepads');

/// Every bundled core but Azahar: the 3DS is "not included in this version".
const _coresWithout3ds = <String>[
  'nestopia', 'snes9x', 'gambatte', 'mgba', 'genesis_plus_gx', 'picodrive',
  'fbneo', 'desmume', 'mupen64plus_next', 'mednafen_psx_hw', 'ppsspp',
];

/// A store whose add waits for [release], to hold the page busy.
class _SlowMenu extends LibretroMainMenu {
  _SlowMenu() : super(availableCores: () async => _coresWithout3ds, isReady: (_) => true);

  final release = Completer<void>();

  @override
  Future<LibretroMainMenuAddResult> add(LibretroConsole console, SqliteConfigProvider provider) async {
    await release.future;
    return super.add(console, provider);
  }
}

/// Build 438: the consoles page as the body of the main bar's consoles tab.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final helper = DatabaseTestHelper();
  final english = LibretroLocale.values['en']!;
  late DatabaseAdapter db;
  late SqliteConfigProvider provider;
  late LibretroMainMenu menu;
  late int previous;
  late int next;

  String en(String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
      LibretroLocale.format(const Locale('en'), key, values);

  setUp(() async {
    db = await helper.setUp();
    for (final system in const <List<String>>[
      ['nes', 'Nintendo Entertainment System'],
      ['md', 'Sega Mega Drive'],
      ['genesis', 'Sega Genesis'],
      ['3ds', 'Nintendo 3DS'],
    ]) {
      await db.insert('app_systems', {'id': system[0], 'real_name': system[1], 'folder_name': system[0]});
    }
    provider = SqliteConfigProvider();
    menu = LibretroMainMenu(availableCores: () async => _coresWithout3ds, isReady: (_) => true);
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
    tester.view.physicalSize = const Size(1600, 6000);
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
            localizationsDelegates: GlobalMaterialLocalizations.delegates,
            // The app screen's Scaffold, under which the tab is drawn.
            home: Scaffold(
              body: LibretroConsolesScreen(
                inMainBar: inMainBar,
                onPreviousTab: () => previous++,
                onNextTab: () => next++,
                mainMenu: store ?? menu,
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

  Finder addButton(String console) => find.byKey(ValueKey('libretro-console-add-$console'));

  ButtonStyleButton button(WidgetTester tester, Finder finder) =>
      tester.widget<ButtonStyleButton>(finder);

  testWidgets('the tab lists every embedded console under the header, without an app bar', (tester) async {
    await pumpTab(tester);

    expect(find.byType(AppBar), findsNothing);
    expect(find.text(english['embeddedConsoles']!), findsOneWidget);
    expect(find.text(english['embeddedConsolesIntro']!), findsOneWidget);
    // NeoStation's library actions stay in the tab.
    expect(find.byKey(const ValueKey('libretro-library-create-folders')), findsOneWidget);
    expect(find.byKey(const ValueKey('libretro-library-move')), findsOneWidget);
    for (final console in LibretroCoreCatalog.consoles.values) {
      final card = find.byKey(ValueKey('libretro-console-${console.id}'));
      expect(card, findsOneWidget, reason: console.id);
      expect(find.descendant(of: card, matching: find.text(console.name)), findsOneWidget);
      expect(find.byKey(ValueKey('libretro-console-import-${console.id}')), findsOneWidget);
      expect(find.byKey(ValueKey('libretro-console-skins-${console.id}')), findsOneWidget);
      expect(addButton(console.id), findsOneWidget, reason: 'nothing is in the main menu yet');
    }
    // The page sits below the 46.r header.
    expect(tester.getTopLeft(find.text(english['embeddedConsoles']!)).dy, greaterThan(46.r));
    // A console whose core is not in the build is shown unavailable.
    expect(find.byKey(const ValueKey('libretro-console-unavailable-3ds')), findsOneWidget);
    expect(find.text(english['consoleUnavailable']!), findsOneWidget);
    expect(button(tester, addButton('3ds')).onPressed, isNull);
    expect(button(tester, addButton('nes')).onPressed, isNotNull);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Add puts the console in the main menu at once and says so', (tester) async {
    await pumpTab(tester);
    expect(find.text(en('addToMainMenu')), findsNWidgets(LibretroCoreCatalog.consoles.length));

    await tester.tap(addButton('nes'));
    await tester.pump();
    await tester.pump();

    expect(provider.detectedSystems.map((s) => s.folderName), contains('nes'));
    expect(await SystemRepository.getHiddenSystems(), isEmpty);
    expect(menu.pinned, ['nes']);
    expect(find.text(en('inMainMenu', {'systems': 'Nintendo Entertainment System'})), findsOneWidget);
    expect(addButton('nes'), findsNothing, reason: 'already in the main menu');
    await tester.pump(const Duration(milliseconds: 500));
    expect(find.text(en('consoleAdded', {'console': 'NES'})), findsOneWidget);
  });

  testWidgets('a console already there through another system has no Add button', (tester) async {
    await SystemRepository.addDetectedSystem('genesis', 'genesis');
    await provider.refreshDetectedSystems();
    await pumpTab(tester);

    expect(find.text(en('inMainMenu', {'systems': 'Sega Genesis'})), findsOneWidget);
    expect(addButton('md'), findsNothing);
    expect(addButton('nes'), findsOneWidget);
  });

  testWidgets('a hidden console offers to show it again', (tester) async {
    await SystemRepository.addDetectedSystem('nes', 'nes');
    await provider.refreshDetectedSystems();
    await provider.toggleSystemHidden('nes');
    await pumpTab(tester);

    expect(find.text(en('hiddenInMainMenu', {'systems': 'Nintendo Entertainment System'})), findsOneWidget);
    expect(find.descendant(of: addButton('nes'), matching: find.text(en('showInMainMenu'))), findsOneWidget);

    await tester.tap(addButton('nes'));
    await tester.pump();
    await tester.pump();

    expect(provider.hiddenSystemFolders, isNot(contains('nes')));
    expect(find.text(en('inMainMenu', {'systems': 'Nintendo Entertainment System'})), findsOneWidget);
    expect(addButton('nes'), findsNothing);
  });

  testWidgets('the main menu refreshes the tab when a console arrives elsewhere', (tester) async {
    await pumpTab(tester);
    expect(addButton('nes'), findsOneWidget);

    // A scan or an import adds the system while the tab is shown.
    await SystemRepository.addDetectedSystem('nes', 'nes');
    await provider.refreshDetectedSystems();
    await tester.pump();

    expect(addButton('nes'), findsNothing);
    expect(find.text(en('inMainMenu', {'systems': 'Nintendo Entertainment System'})), findsOneWidget);
  });

  testWidgets('Skins opens the skin manager of the console', (tester) async {
    await pumpTab(tester);
    await tester.tap(find.byKey(const ValueKey('libretro-console-skins-gba')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    final manager = tester.widget<LibretroSkinManagerScreen>(find.byType(LibretroSkinManagerScreen));
    expect(manager.console, 'gba');
  });

  /// One key press, past GamepadNavigation's keyboard throttle (128 ms of
  /// real time), so a press that does nothing is not merely throttled.
  Future<void> press(WidgetTester tester, LogicalKeyboardKey key) async {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 160)));
    await tester.sendKeyEvent(key);
    await tester.pump();
  }

  testWidgets('LB/RB (Q/E) switch tabs, except while an add is running', (tester) async {
    final slow = _SlowMenu();
    await pumpTab(tester, store: slow);

    await press(tester, LogicalKeyboardKey.keyE);
    expect(next, 1);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect(previous, 1);

    // Leaving the tab would dispose the page in the middle of the add.
    await tester.tap(addButton('nes'));
    await tester.pump();
    await press(tester, LogicalKeyboardKey.keyE);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect((previous, next), (1, 1));
    expect(button(tester, addButton('snes')).onPressed, isNull, reason: 'one action at a time');

    slow.release.complete();
    await tester.pump();
    await tester.pump();
    expect(provider.detectedSystems.map((s) => s.folderName), contains('nes'));
    await press(tester, LogicalKeyboardKey.keyE);
    expect(next, 2);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect(previous, 2);
  });

  testWidgets('as a pushed page it keeps its app bar and leaves the bumpers alone', (tester) async {
    await pumpTab(tester, inMainBar: false);

    expect(find.byType(AppBar), findsOneWidget);
    expect(find.descendant(of: find.byType(AppBar), matching: find.text(english['embeddedConsoles']!)), findsOneWidget);
    await press(tester, LogicalKeyboardKey.keyE);
    await press(tester, LogicalKeyboardKey.keyQ);
    expect((previous, next), (0, 0));
  });

  testWidgets('the tab is translated in the twelve languages', (tester) async {
    for (final language in LibretroLocale.values.keys) {
      final locale = language == 'zh_Hant'
          ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
          : Locale(language);
      final texts = LibretroLocale.values[language]!;
      await pumpTab(tester, locale: locale);
      for (final key in ['embeddedConsoles', 'embeddedConsolesIntro', 'consoleUnavailable', 'libraryTitle']) {
        expect(find.text(texts[key]!), findsOneWidget, reason: '$language:$key');
      }
      expect(find.text(texts['addToMainMenu']!), findsWidgets, reason: language);
      if (language != 'en') {
        expect(find.text(english['addToMainMenu']!), findsNothing, reason: '$language: no English fallback');
      }
    }
  });
}
