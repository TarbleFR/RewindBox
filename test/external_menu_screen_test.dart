import 'dart:convert';

import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/external_display/external_display_entrypoint.dart';
import 'package:neostation/external_display/external_display_state_channel.dart';
import 'package:neostation/external_display/external_menu_screen.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/secondary_achievement_item.dart';
import 'package:neostation/models/secondary_display_state.dart';
import 'package:neostation/screens/secondary_screen/secondary_screen.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  const tv = Size(1920, 1080);

  setUpAll(() async {
    // FlutterLocalization reads its stored language from SharedPreferences.
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [
        MapLocale('en', AppLocale.en),
        MapLocale('fr', AppLocale.fr),
      ],
      initLanguageCode: 'en',
    );
  });

  Future<void> pumpTv(
    WidgetTester tester, {
    required ValueListenable<SecondaryDisplayStateData?> source,
    String? theme,
    ValueListenable<String?>? language,
  }) async {
    tester.view.physicalSize = tv;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(
      ExternalMenuApp(
        stateSource: source,
        initialThemeName: theme,
        languageSource: language,
      ),
    );
    await tester.pumpAndSettle();
  }

  Future<void> sendLanguage(String code) => binding.defaultBinaryMessenger
      .handlePlatformMessage(
        ExternalDisplayStateChannel.languageChannelName,
        const StringCodec().encodeMessage(code),
        (_) {},
      );

  /// The localization the other tests of this file use (en, fr), restored
  /// after a test that initialised the TV engine's twelve languages.
  Future<void> restoreLocalization() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [
        MapLocale('en', AppLocale.en),
        MapLocale('fr', AppLocale.fr),
      ],
      initLanguageCode: 'en',
    );
  }

  /// The state of an engine whose localization never initialised: no
  /// language at all (init clears them before refusing an empty list).
  void clearLanguages() {
    try {
      FlutterLocalization.instance.init(
        mapLocales: const <MapLocale>[],
        initLanguageCode: 'en',
      );
    } on ArgumentError {
      // Expected: the supported languages are cleared first.
    }
  }

  String storedLocale(String code) => jsonEncode(<String, Object?>{
    'translator_language_code': code,
    'translator_country_code': null,
    'translator_script_code': null,
  });

  Future<void> send(String message) => binding.defaultBinaryMessenger
      .handlePlatformMessage(
        ExternalDisplayStateChannel.channelName,
        const StringCodec().encodeMessage(message),
        (_) {},
      );

  Scaffold scaffold(WidgetTester tester) =>
      tester.widget<Scaffold>(find.byType(Scaffold));

  testWidgets('fills a 1920×1080 TV in black with no band and no exception', (
    tester,
  ) async {
    final source = ValueNotifier<SecondaryDisplayStateData?>(null);
    addTearDown(source.dispose);
    await pumpTv(tester, source: source, theme: 'dark');
    expect(tester.takeException(), isNull);

    final background = find.byKey(ExternalMenuApp.backgroundKey);
    expect(tester.widget<ColoredBox>(background).color, Colors.black);
    expect(tester.getSize(background), tv);
    expect(tester.getTopLeft(background), Offset.zero);

    // The menu view lays itself out to the TV bounds: no band of its own.
    expect(find.byType(SecondaryScreen), findsOneWidget);
    expect(tester.getSize(find.byType(Scaffold)), tv);
    expect(tester.getTopLeft(find.byType(Scaffold)), Offset.zero);
    // Before any state: the WELCOME placeholder, not an empty screen.
    expect(find.text('WELCOME'), findsOneWidget);
    expect(tester.binding.hasScheduledFrame, isFalse);
  });

  testWidgets('the initial theme and the language apply before any state', (
    tester,
  ) async {
    final source = ValueNotifier<SecondaryDisplayStateData?>(null);
    addTearDown(source.dispose);
    await pumpTv(tester, source: source, theme: 'light');
    expect(
      scaffold(tester).backgroundColor,
      AppThemes.lightTheme.scaffoldBackgroundColor,
    );
    expect(scaffold(tester).backgroundColor, isNot(Colors.black));

    // Both MaterialApps carry the languages the entrypoint initialised.
    for (final app in tester.widgetList<MaterialApp>(find.byType(MaterialApp))) {
      expect(app.supportedLocales, FlutterLocalization.instance.supportedLocales);
      expect(app.supportedLocales, contains(const Locale('fr')));
      expect(app.debugShowCheckedModeBanner, isFalse);
    }
    expect(tester.takeException(), isNull);
  });

  testWidgets('a state received through the message channel updates the screen', (
    tester,
  ) async {
    final channel = ExternalDisplayStateChannel.forTesting();
    await pumpTv(tester, source: channel.state, theme: 'dark');
    expect(find.text('WELCOME'), findsOneWidget);

    await send(
      jsonEncode(
        SecondaryDisplayStateData(
          systemName: 'snes',
          backgroundColor: 0xFF123456,
        ).toJson(),
      ),
    );
    await tester.pumpAndSettle();
    expect(channel.received, 1);
    expect(channel.rejected, 0);
    expect(channel.state.value?.systemName, 'snes');
    expect(find.text('SNES'), findsOneWidget);
    expect(find.text('WELCOME'), findsNothing);
    expect(scaffold(tester).backgroundColor, const Color(0xFF123456));
    expect(tester.takeException(), isNull);

    // A second push replaces the first; a malformed one changes nothing.
    await send(
      jsonEncode(SecondaryDisplayStateData(systemName: 'Mega Drive').toJson()),
    );
    await tester.pumpAndSettle();
    expect(find.text('MEGA DRIVE'), findsOneWidget);
    expect(find.text('SNES'), findsNothing);

    await send('not json');
    await send('[1, 2]');
    await send('');
    await tester.pumpAndSettle();
    expect(channel.received, 2);
    expect(channel.rejected, 3);
    expect(find.text('MEGA DRIVE'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a state pushed before the screen exists is shown', (
    tester,
  ) async {
    final source = ValueNotifier<SecondaryDisplayStateData?>(
      SecondaryDisplayStateData(systemName: 'ps1'),
    );
    addTearDown(source.dispose);
    await pumpTv(tester, source: source, theme: 'dark');
    expect(find.text('PS1'), findsOneWidget);
    expect(find.text('WELCOME'), findsNothing);
    expect(tester.takeException(), isNull);
  });

  group('entrypoint arguments (no database in the TV engine)', () {
    test('language and theme are parsed; anything else is ignored', () {
      expect(
        ExternalDisplayMenuArgs.parse(const ['language=fr', 'theme=oled']),
        const ExternalDisplayMenuArgs(languageCode: 'fr', themeName: 'oled'),
      );
      expect(
        ExternalDisplayMenuArgs.parse(const [
          'theme=nord',
          '--verbose',
          'language=zh_Hant',
        ]),
        const ExternalDisplayMenuArgs(languageCode: 'zh_Hant', themeName: 'nord'),
      );
      expect(
        ExternalDisplayMenuArgs.parse(const []),
        const ExternalDisplayMenuArgs(),
      );
      expect(const ExternalDisplayMenuArgs().languageCode, 'en');
      expect(
        ExternalDisplayMenuArgs.parse(const ['language=nl', 'theme=']),
        const ExternalDisplayMenuArgs(languageCode: 'en'),
        reason: 'an unsupported language is English, an empty theme none',
      );
      expect(
        ExternalDisplayMenuArgs.parse(const ['language= ja ', 'theme= retro ']),
        const ExternalDisplayMenuArgs(languageCode: 'ja', themeName: 'retro'),
      );
      for (final code in kExternalDisplayLanguageCodes) {
        expect(
          ExternalDisplayMenuArgs.parse(['language=$code']).languageCode,
          code,
        );
      }
      expect(ExternalDisplayMenuArgs.supportedLanguage('zh-Hant'), isNull);
      expect(ExternalDisplayMenuArgs.supportedLanguage(null), isNull);
      // The arguments NeoExternalDisplayMenuEngine.m builds round-trip.
      const args = ExternalDisplayMenuArgs(languageCode: 'ko', themeName: 'aqua');
      expect(args.toEntrypointArgs(), const ['language=ko', 'theme=aqua']);
      expect(ExternalDisplayMenuArgs.parse(args.toEntrypointArgs()), args);
      expect(
        const ExternalDisplayMenuArgs(languageCode: 'de').toEntrypointArgs(),
        const ['language=de'],
      );
      expect(ExternalDisplayMenuArgs.languagePrefix, 'language=');
      expect(ExternalDisplayMenuArgs.themePrefix, 'theme=');
    });

    test('the twelve languages of the app, as the entrypoint declares them', () {
      expect(
        kExternalDisplayLanguageCodes.toSet(),
        AppLocale.supportedLanguages.keys.toSet(),
      );
      expect(kExternalDisplayLanguageCodes, hasLength(12));
      expect(
        externalDisplayMapLocales().map((locale) => locale.languageCode).toList(),
        kExternalDisplayLanguageCodes,
      );
      expect(kExternalDisplayEntrypoint, 'externalDisplayMain');
    });
  });

  group('the TV engine localization', () {
    tearDown(restoreLocalization);

    test('the main engine language wins and nothing is written', () async {
      final stored = storedLocale('fr');
      SharedPreferences.setMockInitialValues({'translator_locale_key': stored});
      expect(await initializeExternalDisplayLocalization('de'), isTrue);
      final localization = FlutterLocalization.instance;
      expect(localization.currentLocale?.languageCode, 'de');
      expect(localization.supportedLanguageCodes, kExternalDisplayLanguageCodes);
      final preferences = await SharedPreferences.getInstance();
      expect(
        preferences.getString('translator_locale_key'),
        stored,
        reason: 'the main engine owns the stored language',
      );
    });

    test('Traditional Chinese is kept, an unknown language is English', () async {
      SharedPreferences.setMockInitialValues({});
      expect(await initializeExternalDisplayLocalization('zh_Hant'), isTrue);
      expect(FlutterLocalization.instance.currentLocale?.languageCode, 'zh_Hant');
      SharedPreferences.setMockInitialValues({});
      expect(await initializeExternalDisplayLocalization('xx'), isTrue);
      expect(FlutterLocalization.instance.currentLocale?.languageCode, 'en');
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getString('translator_locale_key'), isNull);
    });

    test('a failure is reported, never thrown', () async {
      SharedPreferences.setMockInitialValues({
        'translator_locale_key': 'not json',
      });
      expect(await initializeExternalDisplayLocalization('fr'), isFalse);
    });

    test('applying a language the engine does not have changes nothing', () async {
      SharedPreferences.setMockInitialValues({});
      expect(await initializeExternalDisplayLocalization('en'), isTrue);
      expect(applyExternalDisplayLanguage('nl'), isFalse);
      expect(applyExternalDisplayLanguage('en'), isFalse, reason: 'current');
      expect(applyExternalDisplayLanguage('it'), isTrue);
      expect(FlutterLocalization.instance.currentLocale?.languageCode, 'it');
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getString('translator_locale_key'), isNull);
    });

    testWidgets('a language sent by the main engine rebuilds both apps in it', (
      tester,
    ) async {
      SharedPreferences.setMockInitialValues({});
      expect(await initializeExternalDisplayLocalization('en'), isTrue);
      final channel = ExternalDisplayStateChannel.forTesting();
      await pumpTv(
        tester,
        source: channel.state,
        theme: 'dark',
        language: channel.language,
      );
      BuildContext inner() => tester.element(find.text('WELCOME'));
      expect(
        AppLocale.raRateLimited.getString(inner()),
        AppLocale.en[AppLocale.raRateLimited],
      );

      await sendLanguage('fr');
      await tester.pumpAndSettle();
      expect(channel.language.value, 'fr');
      expect(FlutterLocalization.instance.currentLocale?.languageCode, 'fr');
      final delegate = FlutterLocalization.instance.localizationsDelegates.first;
      final apps = tester.widgetList<MaterialApp>(find.byType(MaterialApp));
      expect(apps, hasLength(2));
      for (final app in apps) {
        expect(identical(app.localizationsDelegates!.first, delegate), isTrue);
      }
      expect(
        AppLocale.raRateLimited.getString(inner()),
        AppLocale.fr[AppLocale.raRateLimited],
      );
      expect(
        AppLocale.fr[AppLocale.raRateLimited],
        isNot(AppLocale.en[AppLocale.raRateLimited]),
      );

      // Only the twelve codes are accepted; the screen stays in French.
      await sendLanguage('nl');
      await sendLanguage('');
      await tester.pumpAndSettle();
      expect(channel.rejectedLanguages, 2);
      expect(FlutterLocalization.instance.currentLocale?.languageCode, 'fr');
      expect(tester.takeException(), isNull);
      final preferences = await SharedPreferences.getInstance();
      expect(preferences.getString('translator_locale_key'), isNull);
    });

    testWidgets('without any language the TV stays black, without exception', (
      tester,
    ) async {
      clearLanguages();
      expect(FlutterLocalization.instance.supportedLocales, isEmpty);
      final source = ValueNotifier<SecondaryDisplayStateData?>(
        SecondaryDisplayStateData(systemName: 'snes'),
      );
      addTearDown(source.dispose);
      await pumpTv(tester, source: source, theme: 'dark');
      expect(tester.takeException(), isNull);
      expect(find.byType(MaterialApp), findsNothing);
      expect(find.byType(SecondaryScreen), findsNothing);
      final background = find.byKey(ExternalMenuApp.backgroundKey);
      expect(tester.widget<ColoredBox>(background).color, Colors.black);
      expect(tester.getSize(background), tv);
    });

    testWidgets('the entrypoint reaches runApp when its localization fails', (
      tester,
    ) async {
      tester.view.physicalSize = tv;
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      clearLanguages();
      SharedPreferences.setMockInitialValues({
        'translator_locale_key': 'not json',
      });
      await externalDisplayMain(const ['language=fr', 'theme=dark']);
      await tester.pump();
      expect(find.byType(ExternalMenuApp), findsOneWidget);
      expect(find.byKey(ExternalMenuApp.backgroundKey), findsOneWidget);
      expect(find.byType(MaterialApp), findsNothing);
      final app = tester.widget<ExternalMenuApp>(find.byType(ExternalMenuApp));
      expect(app.initialThemeName, 'dark');
      expect(app.stateSource, same(ExternalDisplayStateChannel.instance.state));
      expect(tester.takeException(), isNull);
    });
  });

  test('the JSON the main engine sends decodes into the same state', () {
    // The channel carries text: the bridge decodes what jsonEncode produced,
    // nested lists and bytes included.
    final sent = SecondaryDisplayStateData(
      systemName: 'snes',
      gameImageBytes: Uint8List.fromList([0, 1, 2, 253, 254, 255]),
      achievements: const [
        SecondaryAchievementItem(
          id: 1,
          title: 'A',
          description: 'first',
          points: 5,
          badgeName: '111',
          displayOrder: 0,
          earned: true,
          earnedHardcore: false,
        ),
      ],
      newlyEarnedIds: const [1, 2],
      nowPlayingActive: true,
      dockApps: const ['com.a', '', '', '', ''],
    );
    final received = SecondaryDisplayStateData.fromJson(
      jsonDecode(jsonEncode(sent.toJson())) as Map<String, dynamic>,
    );
    expect(received.toJson(), sent.toJson());
    expect(received.achievements!.single.id, 1);
    expect(received.gameImageBytes, sent.gameImageBytes);
  });
}
