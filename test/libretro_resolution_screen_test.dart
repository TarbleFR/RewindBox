// "Resolution and picture" of a console (Build 455, docs/libretro-resolution.md
// § 5): System Settings › Emulators and the Consoles tab show, for each core
// of the console, the internal resolutions it really offers (native first),
// save the choice for every game of the core where the in-game menu saves it,
// refuse it while a game runs, and explain a core without internal
// resolution. Real files in a temporary folder; the session probe is
// simulated.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/cupertino.dart' show CupertinoLocalizations, DefaultCupertinoLocalizations;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/screens/libretro/libretro_resolution_screen.dart';
import 'package:neostation/services/libretro_core_option_store.dart';
import 'package:neostation/services/libretro_resolution_service.dart';
import 'package:path/path.dart' as p;

const _gamepads = MethodChannel('xyz.luan/gamepads');

/// English Material and Cupertino texts for any locale, so the page can be
/// pumped in every NeoStation language.
class _AnyLocaleDelegate<T> extends LocalizationsDelegate<T> {
  const _AnyLocaleDelegate(this.loader);

  final Future<T> Function(Locale locale) loader;

  @override
  bool isSupported(Locale locale) => true;

  @override
  Future<T> load(Locale locale) => loader(locale);

  @override
  bool shouldReload(covariant LocalizationsDelegate<T> old) => false;
}

const _materialTexts = _AnyLocaleDelegate<MaterialLocalizations>(DefaultMaterialLocalizations.load);
const _cupertinoTexts = _AnyLocaleDelegate<CupertinoLocalizations>(DefaultCupertinoLocalizations.load);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Directory root;
  late Directory config;
  var active = false;

  String t(String locale, String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
      LibretroLocale.format(Locale(locale), key, values);

  setUp(() async {
    root = await Directory.systemTemp.createTemp('neostation-resolution-screen-');
    config = Directory(p.join(root.path, 'Config'));
    await config.create(recursive: true);
    active = false;
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
  });

  tearDown(() async {
    messenger.setMockMethodCallHandler(_gamepads, null);
    if (await root.exists()) await root.delete(recursive: true);
  });

  LibretroResolutionService service() => LibretroResolutionService(
        configDirectory: () async => config,
        store: LibretroCoreOptionStore(configDirectory: () async => config, sessionProbe: () async => active),
      );

  /// The page reads and writes real files: real time, then a pump, until
  /// [done] holds.
  Future<void> settle(WidgetTester tester, bool Function() done) async {
    for (var round = 0; round < 400; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
      if (done()) {
        await tester.pump();
        return;
      }
    }
    fail('the page did not settle');
  }

  Future<void> pumpPage(WidgetTester tester, String console, {Locale locale = const Locale('en')}) async {
    tester.view.physicalSize = const Size(1200, 3000);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      locale: locale,
      supportedLocales: <Locale>[locale],
      localizationsDelegates: const <LocalizationsDelegate<Object?>>[_materialTexts, _cupertinoTexts],
      home: LibretroResolutionScreen(console: console, service: service()),
    ));
    await settle(tester, () => find.byType(CircularProgressIndicator).evaluate().isEmpty);
  }

  Finder chip(String core, String value) => find.byKey(ValueKey('libretro-resolution-$core-$value'));

  bool selected(WidgetTester tester, String core, String value) =>
      tester.widget<ChoiceChip>(chip(core, value)).selected;

  testWidgets('each core of the console with its real values, native selected by default', (tester) async {
    await pumpPage(tester, 'psx');
    expect(find.text('Resolution and picture · PlayStation'), findsOneWidget);
    expect(find.text(t('en', 'resolutionConsoleIntro', {'console': 'PlayStation'})), findsOneWidget);
    expect(find.text('Beetle PSX HW (default)'), findsOneWidget);
    expect(find.text('Beetle PSX'), findsOneWidget);
    for (final core in <String>['mednafen_psx_hw', 'mednafen_psx']) {
      for (final value in <String>['1x(native)', '2x', '4x', '8x']) {
        expect(chip(core, value), findsOneWidget, reason: '$core $value');
      }
      // 16x is declared by the core but needs about 600 MiB.
      expect(chip(core, '16x'), findsNothing, reason: core);
      expect(selected(tester, core, '1x(native)'), isTrue, reason: core);
    }
    expect(find.text('Native'), findsNWidgets(2));
    expect(find.text('×2'), findsNWidgets(2));
    expect(find.text(t('en', 'resolutionInGameHint')), findsOneWidget);
  });

  testWidgets('a choice is saved for every game of the core and shown selected', (tester) async {
    await pumpPage(tester, 'psp');
    expect(find.text('Native · 480 × 272'), findsOneWidget);
    await tester.tap(chip('ppsspp', '960x544'));
    await settle(tester, () => selected(tester, 'ppsspp', '960x544'));
    final stored = LibretroCoreOptionStore.decode(File(p.join(config.path, 'PPSSPP.json')).readAsStringSync());
    expect(stored, <String, String>{'ppsspp_internal_resolution': '960x544'});
    expect(selected(tester, 'ppsspp', '480x272'), isFalse);
    expect(find.textContaining(t('en', 'resolutionFromCore', {'core': 'PPSSPP'})), findsOneWidget);
  });

  testWidgets('while a game runs nothing is written and the page says why', (tester) async {
    await pumpPage(tester, 'psp');
    active = true;
    await tester.tap(chip('ppsspp', '1440x816'));
    await settle(tester, () => find.text(t('en', 'resolutionSessionActive')).evaluate().isNotEmpty);
    expect(File(p.join(config.path, 'PPSSPP.json')).existsSync(), isFalse);
    expect(selected(tester, 'ppsspp', '480x272'), isTrue);
  });

  testWidgets('a 2D core is explained instead of offering values', (tester) async {
    await pumpPage(tester, 'snes');
    expect(find.byKey(const ValueKey('libretro-resolution-unsupported-snes9x')), findsOneWidget);
    expect(find.text(t('en', 'resolutionUnsupported', {'core': 'Snes9x'})), findsOneWidget);
    expect(find.text(t('en', 'resolutionUnsupportedFooter', {'core': 'Snes9x'})), findsOneWidget);
    expect(find.text(t('en', 'resolutionInapplicableFooter', {'core': 'Snes9x'})), findsNothing);
    expect(find.byType(ChoiceChip), findsNothing);
  });

  testWidgets('an option that did not apply at the last launch is explained, not offered', (tester) async {
    // PPSSPP in its software context (no OpenGL ES context): the session
    // recorded the option it found without offering it.
    final snapshot = File(p.join(config.path, 'Resolution', 'ppsspp.json'));
    snapshot.parent.createSync(recursive: true);
    snapshot.writeAsStringSync(jsonEncode(<String, Object?>{
      'version': 1,
      'coreId': 'ppsspp',
      'libraryName': 'PPSSPP',
      'renderer': 'software',
      'internalResolution': null,
      'inapplicableKey': 'ppsspp_internal_resolution',
    }));
    await pumpPage(tester, 'psp');
    expect(find.byKey(const ValueKey('libretro-resolution-unsupported-ppsspp')), findsOneWidget);
    expect(find.text(t('en', 'resolutionInapplicableFooter', {'core': 'PPSSPP'})), findsOneWidget);
    expect(find.text(t('en', 'resolutionUnsupportedFooter', {'core': 'PPSSPP'})), findsNothing);
    expect(find.byType(ChoiceChip), findsNothing);
  });

  testWidgets('games with their own resolution are counted, and kept', (tester) async {
    // Synchronous I/O: real asynchronous I/O never completes in the test's
    // fake time outside runAsync.
    final games = File(p.join(config.path, 'Games', 'Mupen64Plus-Next.json'));
    games.parent.createSync(recursive: true);
    games.writeAsStringSync(jsonEncode(<String, Object?>{
      'version': 1,
      'games': <String, Object?>{
        'n64/A.z64': <String, String>{'mupen64plus-43screensize': '1280x960'},
      },
    }));
    await pumpPage(tester, 'n64');
    expect(find.text(t('en', 'resolutionGamesOwn', {'count': 1})), findsOneWidget);
    // Native by default although the core's own default is 640x480.
    expect(selected(tester, 'mupen64plus_next', '320x240'), isTrue);
    expect(find.text('×4.5 · 1440 × 1080'), findsOneWidget);
    await tester.tap(chip('mupen64plus_next', '640x480'));
    await settle(tester, () => selected(tester, 'mupen64plus_next', '640x480'));
    expect(jsonDecode(games.readAsStringSync())['games']['n64/A.z64']['mupen64plus-43screensize'], '1280x960');
  });

  testWidgets('French: factors with a decimal comma, translated texts', (tester) async {
    await pumpPage(tester, 'n64', locale: const Locale('fr'));
    expect(find.text('Résolution et image · Nintendo 64'), findsOneWidget);
    expect(find.text('×4,5 · 1440 × 1080'), findsOneWidget);
    expect(find.text(t('fr', 'resolutionInGameHint')), findsOneWidget);
  });
}
