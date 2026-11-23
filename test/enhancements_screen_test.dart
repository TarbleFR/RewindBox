import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/enhancements_locale.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/screens/enhancements/enhancements_screen.dart';
import 'package:neostation/services/enhancements/adapters/beetle_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/adapters/melonx_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/adapters/rpcs3_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/widgets/custom_toggle_switch.dart';
import 'package:path/path.dart' as path;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'enhancement_test_support.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  String en(String key) => EnhancementsLocale.forLocale(const Locale('en'), key);

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    SfxService().setEnabled(false);
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (call) async => <dynamic>[],
    );
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
  });
  tearDownAll(() => SfxService().setEnabled(true));

  testWidgets('a PS3 game lists its categories and switches a cheat in one tap', (tester) async {
    final temp = Directory.systemTemp.createTempSync('enh-screen-');
    addTearDown(() => temp.deleteSync(recursive: true));
    final data = Directory(path.join(temp.path, 'Data'))..createSync();
    final service = EnhancementService(
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [Rpcs3EnhancementAdapter(dataDirectory: () async => data, installedVersion: (_) async => '01.00')],
      texturesSupported: (_) => false,
    );
    await tester.binding.setSurfaceSize(const Size(956, 440));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    Future<void> settle(bool Function() done) async {
      for (var i = 0; i < 100 && !done(); i++) {
        await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
        await tester.pump();
      }
    }

    await tester.pumpWidget(
      ChangeNotifierProvider<ThemeProvider>.value(
        value: ThemeProvider.testing(),
        child: ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (context, _) => Consumer<ThemeProvider>(
            builder: (context, theme, _) => MaterialApp(
              theme: theme.currentTheme,
              localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
              supportedLocales: FlutterLocalization.instance.supportedLocales,
              home: EnhancementsScreen(
                game: testGame(name: "Demon's Souls", romPath: '/rpcs3/BLUS30443', titleId: 'BLUS30443'),
                system: const SystemModel(folderName: 'ps3', realName: 'PlayStation 3', iconImage: '', color: ''),
                systemFolder: 'ps3',
                service: service,
              ),
            ),
          ),
        ),
      ),
    );
    final toggle = find.byWidgetPredicate(
      (widget) =>
          widget.key is ValueKey<String> && (widget.key! as ValueKey<String>).value.startsWith('enhancements-toggle-'),
    );
    await settle(() => toggle.evaluate().isNotEmpty);
    expect(toggle, findsWidgets);
    expect(find.textContaining(en(EnhancementsLocale.catCheat)), findsWidgets);
    expect(find.textContaining(en(EnhancementsLocale.catGraphics)), findsWidgets);
    expect(find.text(en(EnhancementsLocale.restartNote)), findsOneWidget);
    expect(tester.takeException(), isNull);

    await tester.tap(toggle.first);
    final staged = File(path.join(data.path, 'NeoStationUnifiedCheats', 'state.json'));
    await settle(() => find.byKey(const ValueKey('enhancements-active-count')).evaluate().isNotEmpty);
    expect(find.byKey(const ValueKey('enhancements-active-count')), findsOneWidget);
    expect(staged.readAsStringSync(), contains('"enabled":true'));
    final restore = find.text(en(EnhancementsLocale.restore));
    await tester.scrollUntilVisible(
      restore,
      300,
      scrollable: find.descendant(of: find.byType(ListView), matching: find.byType(Scrollable)).first,
    );
    expect(restore, findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  // A Switch game: the page says when the engine refresh follows an FPS code, and which build the codes are for when
  // none matches the installed game. Made-up records, as the MeloNX adapter test's.
  Future<void> pumpSwitch(WidgetTester tester, EnhancementService service, {Size size = const Size(956, 440)}) async {
    await tester.binding.setSurfaceSize(size);
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      ChangeNotifierProvider<ThemeProvider>.value(
        value: ThemeProvider.testing(),
        child: ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (context, _) => Consumer<ThemeProvider>(
            builder: (context, theme, _) => MaterialApp(
              theme: theme.currentTheme,
              localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
              supportedLocales: FlutterLocalization.instance.supportedLocales,
              home: EnhancementsScreen(
                game: testGame(name: 'Fighter', romPath: '/Documents/MeloNX/roms/switch/fighter.nsp'),
                system: const SystemModel(folderName: 'switch', realName: 'Nintendo Switch', iconImage: '', color: ''),
                systemFolder: 'switch',
                service: service,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> settleUntil(WidgetTester tester, bool Function() done) async {
    for (var i = 0; i < 100 && !done(); i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
      await tester.pump();
    }
  }

  Map<String, dynamic> code(String name, String cat, List<String> builds) => {
    'id': name.toLowerCase().replaceAll(RegExp('[^a-z0-9]+'), '-'),
    'cat': cat,
    'name': name,
    'source': 'fixture',
    'builds': {for (final build in builds) build: ['04000000 00000000 00000001']},
  };

  EnhancementService switchService(Directory temp, String build, List<Map<String, dynamic>> entries) => EnhancementService(
    catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {
      'melonx': {
        '0100F1F1F1F1E000': {'title': 'Fighter', 'master': <String, dynamic>{}, 'credits': <String>[], 'entries': entries},
      },
    }),
    store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
    adapters: [
      MelonxEnhancementAdapter(
        root: () async => Directory(path.join(temp.path, 'MeloNX')),
        metadata: (_) async => {'titleId': '0100F1F1F1F1E000', 'version': '13.0.3', 'buildId': build},
        refreshSupported: () async => true,
      ),
    ],
    texturesSupported: (_) => false,
  );

  testWidgets('a Switch FPS code that is on says the engine refresh it sets', (tester) async {
    final temp = Directory.systemTemp.createTempSync('enh-screen-switch-');
    addTearDown(() => temp.deleteSync(recursive: true));
    final game = testGame(name: 'Fighter', romPath: '/Documents/MeloNX/roms/switch/fighter.nsp');
    // Created and turned on outside the test's fake clock (the store's queue belongs to the zone that made it).
    final service = (await tester.runAsync(() async {
      final service = switchService(temp, 'B9B166DF1DB90BAF', [code('120 FPS (Emulator)', 'fps', ['B9B166DF1DB90BAF'])]);
      final view = await service.open(game, 'switch', download: true);
      await service.setActive(game, 'switch', view, view.items.single, true);
      return service;
    }))!;
    await pumpSwitch(tester, service);
    final refresh = find.text(en(EnhancementsLocale.engineRefresh).replaceAll('{hz}', '120'));
    await settleUntil(tester, () => refresh.evaluate().isNotEmpty);
    expect(refresh, findsOneWidget);
    expect(find.byKey(const ValueKey('enhancements-active-count')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('when no Switch code is for the installed build, the page names the builds they are for', (tester) async {
    final temp = Directory.systemTemp.createTempSync('enh-screen-switch-');
    addTearDown(() => temp.deleteSync(recursive: true));
    final service = (await tester.runAsync(() async {
      final service = switchService(temp, '1111222233334444', [
        code('Infinite stock', 'cheat', ['77104350C9768709']),
        code('Max damage', 'cheat', ['77104350C9768709', 'B9B166DF1DB90BAF']),
      ]);
      await service.open(testGame(name: 'Fighter', romPath: '/Documents/MeloNX/roms/switch/fighter.nsp'), 'switch', download: true);
      return service;
    }))!;
    await pumpSwitch(tester, service);
    final unmatched = find.text(
      en(EnhancementsLocale.unmatchedBuild).replaceAll('{build}', '1111222233334444').replaceAll('{targets}', '77104350C9768709, B9B166DF1DB90BAF'),
    );
    await settleUntil(tester, () => unmatched.evaluate().isNotEmpty);
    expect(unmatched, findsOneWidget);
    expect(find.text(en(EnhancementsLocale.versionMismatch)), findsWidgets);
    expect(find.text(en(EnhancementsLocale.statusIncompatible)), findsWidgets);
    expect(find.byKey(const ValueKey('enhancements-active-count')), findsNothing);
    expect(tester.takeException(), isNull);
  });

  testWidgets("a Switch game's entries show the catalogue's warnings, their game version, the source's name and the "
      "authors' notes on every tab", (tester) async {
    final temp = Directory.systemTemp.createTempSync('enh-screen-switch-');
    addTearDown(() => temp.deleteSync(recursive: true));
    const build = 'B9B166DF1DB90BAF';
    const base = 'B0B0B0B0B0B0B0B0';
    const latest = 'C3C3C3C3C3C3C3C3';
    const note = '[Use TAAU] only for use with [AA Mode = TAA], else will crash';
    Map<String, dynamic> flagged(String name, String cat, List<String> flags) => {...code(name, cat, [build]), 'flags': flags};
    final dram = flagged('8K Docked (USE 8GB DRAM MEMORY LAYOUT)', 'graphics', ['dram8gb', 'heavy']);
    final service = (await tester.runAsync(() async {
      final service = EnhancementService(
        catalog: fixtureCatalog(
          Directory(path.join(temp.path, 'cache')),
          {
            'melonx': {
              '0100F1F1F1F1E000': {
                'title': 'Fighter',
                'master': <String, dynamic>{},
                'credits': [note],
                'releases': {
                  base: {'update': [0]},
                  build: {'update': [131072]},
                  latest: {'display': ['1.3.2'], 'update': [393216]},
                },
                'latest': {'update': 393216, 'build': latest, 'display': '1.3.2'},
                'entries': [
                  code('60 FPS', 'fps', [base, build]),
                  flagged('Default 30 FPS', 'fps', ['default', 'noRefresh']),
                  flagged('AA High (Crash If TAAU ON)', 'graphics', ['crashRisk']),
                  flagged('Foliage OFF (Experimental)', 'graphics', ['experimental']),
                  flagged('Docked RRS 240% (4K 2160p)', 'graphics', ['heavy']),
                  dram,
                ],
              },
            },
          },
          sources: [
            {
              'id': 'fixture',
              'name': 'Example/switch-codes (made-up codes for tests)',
              'url': 'https://example.org',
              'license': 'None',
              'revision': 'x',
              'engines': ['melonx'],
            },
          ],
        ),
        store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
        adapters: [
          MelonxEnhancementAdapter(
            root: () async => Directory(path.join(temp.path, 'MeloNX')),
            metadata: (_) async => {'titleId': '0100F1F1F1F1E000', 'version': '1.2.0', 'buildId': build},
            refreshSupported: () async => true,
          ),
        ],
        texturesSupported: (_) => false,
      );
      await service.open(testGame(name: 'Fighter', romPath: '/Documents/MeloNX/roms/switch/fighter.nsp'), 'switch', download: true);
      return service;
    }))!;
    await pumpSwitch(tester, service, size: const Size(956, 2000));
    final older = find.text(en(EnhancementsLocale.olderVersion).replaceAll('{version}', 'Update 6 (1.3.2)'));
    await settleUntil(tester, () => older.evaluate().isNotEmpty);

    // The FPS tab opens first (no cheat): its entries are for update 2, the newest known is update 6 (1.3.2).
    expect(older, findsNWidgets(2));
    expect(find.text(en(EnhancementsLocale.flagDefault)), findsOneWidget);
    expect(find.textContaining('${en(EnhancementsLocale.source)}: Example/switch-codes · '), findsNWidgets(2));
    // The page names the updates the adapter gives as numbers, in its language.
    expect(find.textContaining('Build ID $base (${en(EnhancementsLocale.baseGame)}), $build (Update 2)'), findsOneWidget);
    expect(find.textContaining('Build ID $build (Update 2)'), findsOneWidget);
    expect(find.text(en(EnhancementsLocale.authorNotes)), findsOneWidget, reason: 'the notes are on every tab');
    expect(find.text(note), findsOneWidget);

    await tester.tap(find.textContaining(en(EnhancementsLocale.catGraphics)));
    await settleUntil(tester, () => find.text(en(EnhancementsLocale.flagDram8gb)).evaluate().isNotEmpty);
    expect(find.text(en(EnhancementsLocale.flagCrashRisk)), findsOneWidget);
    expect(find.text(en(EnhancementsLocale.flagExperimental)), findsOneWidget);
    expect(find.text(en(EnhancementsLocale.flagHeavy)), findsNWidgets(2));
    expect(find.text(en(EnhancementsLocale.flagDram8gb)), findsOneWidget);
    expect(find.text(en(EnhancementsLocale.flagCrashRiskNote)), findsOneWidget, reason: 'the focused entry explains its flag');
    expect(find.text(en(EnhancementsLocale.dram8gbProblem)), findsOneWidget);
    final toggle = tester.widget<CustomToggleSwitch>(find.byKey(ValueKey('enhancements-toggle-${dram['id']}')));
    expect(toggle.disabled, isTrue, reason: 'RewindBox offers no 8 GB DRAM layout');
    expect(find.text(note), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('two choices of one group that are both on are flagged on both rows; an 8 GB DRAM mod turned on before '
      'its flag shows as on and turns off', (tester) async {
    final temp = Directory.systemTemp.createTempSync('enh-screen-switch-');
    addTearDown(() => temp.deleteSync(recursive: true));
    const build = 'B9B166DF1DB90BAF';
    const title = '0100F1F1F1F1E000';
    Map<String, dynamic> grouped(String name) => {...code(name, 'fps', [build]), 'group': 'alt/$title/ec9a9418ab'};
    final dram = {...code('8K Docked (USE 8GB DRAM MEMORY LAYOUT)', 'graphics', [build]), 'flags': ['dram8gb', 'heavy']};
    final service = (await tester.runAsync(() async {
      final service = switchService(temp, build, [grouped('60 FPS'), grouped('45 FPS'), code('Bloom ON', 'graphics', [build]), dram]);
      final game = testGame(name: 'Fighter', romPath: '/Documents/MeloNX/roms/switch/fighter.nsp');
      final view = await service.open(game, 'switch', download: true);
      await service.setActive(game, 'switch', view, view.items.firstWhere((item) => item.name == '60 FPS'), true);
      // Turned on before the alt group and the DRAM flag existed.
      await service.store.transaction((games) async => games['melonx:$title']!.active.addAll(['45-fps', dram['id'] as String]));
      return service;
    }))!;
    await pumpSwitch(tester, service, size: const Size(956, 2000));
    final conflict = find.text(en(EnhancementsLocale.exclusiveConflict));
    await settleUntil(tester, () => conflict.evaluate().isNotEmpty);
    expect(conflict, findsNWidgets(2), reason: '60 FPS and 45 FPS, each asking to keep one');

    await tester.tap(find.textContaining(en(EnhancementsLocale.catGraphics)));
    final active = find.text(en(EnhancementsLocale.dram8gbActive));
    await settleUntil(tester, () => active.evaluate().isNotEmpty);
    expect(active, findsOneWidget);
    expect(find.text(en(EnhancementsLocale.dram8gbProblem)), findsNothing);
    CustomToggleSwitch toggle() => tester.widget<CustomToggleSwitch>(find.byKey(ValueKey('enhancements-toggle-${dram['id']}')));
    expect((toggle().value, toggle().disabled), (true, false), reason: 'still applied by the engine: it can be turned off');

    await tester.tap(find.byKey(ValueKey('enhancements-toggle-${dram['id']}')));
    final problem = find.text(en(EnhancementsLocale.dram8gbProblem));
    await settleUntil(tester, () => problem.evaluate().isNotEmpty);
    expect(problem, findsOneWidget);
    expect((toggle().value, toggle().disabled), (false, true));
    expect(tester.takeException(), isNull);
  });

  test('updates are named in the page language; choices on together are found', () {
    expect(EnhancementsScreen.updateName(const Locale('fr'), 393216), 'Mise à jour 6');
    expect(EnhancementsScreen.updateName(const Locale('ja'), 0), EnhancementsLocale.forLocale(const Locale('ja'), EnhancementsLocale.baseGame));
    expect(EnhancementsScreen.updateName(const Locale('en'), 0), 'Base game');
    expect(EnhancementsScreen.updateName(const Locale('en'), 65537), 'v65537');
    EnhancementItem item(String id, String group, EnhancementStatus status) => EnhancementItem(
      id: id,
      engine: EnhancementEngine.melonx,
      category: EnhancementCategory.fps,
      name: id,
      sourceId: 'fixture',
      status: status,
      exclusiveGroup: group,
    );
    expect(
      EnhancementsScreen.conflicting([
        item('60', 'alt/a', EnhancementStatus.active),
        item('45', 'alt/a', EnhancementStatus.active),
        item('30', 'alt/a', EnhancementStatus.available),
        item('bloom', 'alt/b', EnhancementStatus.active),
        item('x', '', EnhancementStatus.active),
        item('y', '', EnhancementStatus.active),
      ]),
      {'60', '45'},
    );
  });

  test('every locale has every string of the page', () {
    final english = EnhancementsLocale.values['en']!.keys.toSet();
    expect(EnhancementsLocale.values.keys.toSet(), {
      'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko', //
    });
    for (final locale in EnhancementsLocale.values.entries) {
      expect(locale.value.keys.toSet(), english, reason: locale.key);
      expect(locale.value.values.every((text) => text.trim().isNotEmpty), isTrue, reason: locale.key);
      expect(locale.value[EnhancementsLocale.olderVersion], contains('{version}'), reason: locale.key);
      expect(locale.value[EnhancementsLocale.updateNumber], contains('{n}'), reason: locale.key);
    }
    expect(english, containsAll([
      EnhancementsLocale.authorNotes,
      EnhancementsLocale.flagExperimental,
      EnhancementsLocale.flagCrashRisk,
      EnhancementsLocale.flagHeavy,
      EnhancementsLocale.flagDefault,
      EnhancementsLocale.flagDram8gb,
      EnhancementsLocale.flagExperimentalNote,
      EnhancementsLocale.flagCrashRiskNote,
      EnhancementsLocale.flagHeavyNote,
      EnhancementsLocale.flagDefaultNote,
      EnhancementsLocale.dram8gbProblem,
      EnhancementsLocale.baseGame,
      EnhancementsLocale.dram8gbActive,
      EnhancementsLocale.exclusiveConflict,
    ]));
    expect(EnhancementsLocale.forLocale(const Locale('fr'), EnhancementsLocale.flagCrashRisk), 'Risque de plantage');
    expect(EnhancementsLocale.forLocale(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'), EnhancementsLocale.updateNumber),
        '更新 {n}');
  });

  test('a source is named without its description', () {
    expect(EnhancementsScreen.sourceLabel('HamletDuFromage/switch-cheats-db (GBAtemp main cheat file, ChanseyIsTheBest)'),
        'HamletDuFromage/switch-cheats-db');
    expect(EnhancementsScreen.sourceLabel('Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods'), 'Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods');
  });

  testWidgets("a PS1 game's presets read in the page's language and say what keeps them off", (tester) async {
    const french = Locale('fr');
    String fr(String key) => EnhancementsLocale.forLocale(french, key);
    final temp = Directory.systemTemp.createTempSync('enh-screen-ps1-');
    addTearDown(() => temp.deleteSync(recursive: true));
    final games = Directory(path.join(temp.path, 'Config', 'Games'))..createSync(recursive: true);
    // The game's own MDEC value (set in the in-game menu), and a Beetle PSX file RewindBox cannot read.
    File(path.join(games.path, 'Beetle PSX HW.json')).writeAsStringSync(jsonEncode({
      'version': 1,
      'games': {
        'ps1/Crash.cue': {'beetle_psx_hw_mdec_yuv': 'disabled'},
      },
    }));
    File(path.join(games.path, 'Beetle PSX.json')).writeAsStringSync('{"games": [');
    final service = EnhancementService(
      catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), const {}),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [
        BeetleEnhancementAdapter(
          configDirectory: () async => Directory(path.join(temp.path, 'Config')),
          sessionActive: () async => false,
          coreChoice: (_, _) async => null,
          runsEmbedded: (_, _) async => true,
        ),
      ],
      texturesSupported: (_) => false,
    );
    await tester.binding.setSurfaceSize(const Size(956, 2000));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      ChangeNotifierProvider<ThemeProvider>.value(
        value: ThemeProvider.testing(),
        child: ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (context, _) => Consumer<ThemeProvider>(
            builder: (context, theme, _) => MaterialApp(
              theme: theme.currentTheme,
              locale: french,
              localizationsDelegates: GlobalMaterialLocalizations.delegates,
              supportedLocales: const [Locale('en'), french],
              home: EnhancementsScreen(
                game: testGame(name: 'Crash Bandicoot', romPath: '/Documents/roms/ps1/Crash.cue'),
                system: const SystemModel(folderName: 'ps1', realName: 'PlayStation', iconImage: '', color: ''),
                systemFolder: 'ps1',
                service: service,
              ),
            ),
          ),
        ),
      ),
    );
    final widescreen = find.text(fr(EnhancementsLocale.beetleWidescreen));
    await settleUntil(tester, () => widescreen.evaluate().isNotEmpty);

    // The Ultrawide tab opens first: RewindBox's text in French, the source named, the file that blocks it.
    expect(widescreen, findsOneWidget);
    expect(find.text(fr(EnhancementsLocale.beetleWidescreenNote)), findsOneWidget);
    expect(
      find.text('${fr(EnhancementsLocale.source)}: ${fr(EnhancementsLocale.beetleSource)} · '
          '${fr(EnhancementsLocale.compatibility)}: ${fr(EnhancementsLocale.beetleBothCores)}'),
      findsOneWidget,
    );
    expect(find.text(fr(EnhancementsLocale.optionsUnreadable).replaceAll('{file}', 'Beetle PSX.json')), findsOneWidget);
    expect(find.text(fr(EnhancementsLocale.userFilePresent)), findsNothing);
    final toggle = find.byKey(const ValueKey('enhancements-toggle-beetle-widescreen-16-9'));
    expect(tester.widget<CustomToggleSwitch>(toggle).disabled, isTrue);
    expect(find.byKey(const ValueKey('enhancements-install')), findsNothing, reason: 'the presets ship with the cores');
    expect(find.byKey(const ValueKey('enhancements-restore')), findsNothing, reason: 'nothing of RewindBox\'s yet');

    await tester.tap(find.textContaining(fr(EnhancementsLocale.catGraphics)));
    final own = find.text(fr(EnhancementsLocale.playerValue));
    await settleUntil(tester, () => own.evaluate().isNotEmpty);
    expect(own, findsOneWidget, reason: 'the MDEC filter: the game has its own value');
    expect(find.text(fr(EnhancementsLocale.beetleMdec)), findsOneWidget);
    expect(find.textContaining('${fr(EnhancementsLocale.compatibility)}: ${fr(EnhancementsLocale.beetleVulkanCore)}'),
        findsOneWidget);
    expect(find.text(fr(EnhancementsLocale.beetlePgxpGeometry)), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  test("a failed switch or restore says why in the page's language", () {
    String text(String locale, String key) => EnhancementsLocale.forLocale(Locale(locale), key);
    String error(String locale, Object error) => EnhancementsScreen.errorText(Locale(locale), error);
    expect(error('fr', const EnhancementException('session_active')), text('fr', EnhancementsLocale.sessionActive));
    expect(
      error('de', const EnhancementException('player_value', 'Beetle PSX.json: beetle_psx_cpu_freq_scale')),
      text('de', EnhancementsLocale.playerValue),
    );
    expect(
      error('es', const EnhancementException('player_keeps_on', 'beetle-gte-overclock')),
      text('es', EnhancementsLocale.playerValueKeepsOn),
    );
    expect(
      error('ja', const EnhancementException('options_unreadable', 'Beetle PSX HW.json')),
      text('ja', EnhancementsLocale.optionsUnreadable).replaceAll('{file}', 'Beetle PSX HW.json'),
    );
    expect(error('en', const EnhancementException('user_file_present')), en(EnhancementsLocale.userFilePresent));
    expect(error('en', StateError('anything else')), en(EnhancementsLocale.failed));
    for (final locale in EnhancementsLocale.values.entries) {
      expect(locale.value[EnhancementsLocale.optionsUnreadable], contains('{file}'), reason: locale.key);
      for (final key in [
        EnhancementsLocale.playerValue,
        EnhancementsLocale.playerValueKeepsOn,
        EnhancementsLocale.optionsUnreadable,
        EnhancementsLocale.sessionActive,
      ]) {
        final reused = [locale.value[EnhancementsLocale.userFilePresent], locale.value[EnhancementsLocale.failed]];
        expect(reused, isNot(contains(locale.value[key])), reason: '${locale.key} $key: its own words');
      }
    }
  });
}
