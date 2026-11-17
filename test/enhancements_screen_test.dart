import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/enhancements_locale.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/screens/enhancements/enhancements_screen.dart';
import 'package:neostation/services/enhancements/adapters/melonx_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/adapters/rpcs3_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:neostation/services/sfx_service.dart';
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
  Future<void> pumpSwitch(WidgetTester tester, EnhancementService service) async {
    await tester.binding.setSurfaceSize(const Size(956, 440));
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
}
