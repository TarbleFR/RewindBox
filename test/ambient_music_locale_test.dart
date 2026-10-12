import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/ambient_music_locale.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/ambient_music_setting_rows.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/widgets/setting_value_chip.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/home_music_service.dart';
import 'package:neostation/widgets/custom_toggle_switch.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'ambient_music_service_test.dart' show FakeBackend, FakeUserMusic;

void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = AmbientMusicLocale.values['en']!;

  const contractKeys = <String>{
    'title',
    'description',
    'track',
    'trackHelp',
    'volumeTitle',
    'volumeDescription',
    'volumeValue',
    'on',
    'off',
    'cardDefault',
    'cardCustom',
    'choose',
    'restoreDefault',
  };

  // A percentage reads the same in several languages.
  const sameAsEnglishAllowed = <String>{'volumeValue'};

  test('the ambient music catalog covers exactly the twelve languages', () {
    expect(
      AmbientMusicLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(AmbientMusicLocale.values.length, 12);
  });

  test('the English catalog holds exactly the keys of the contract', () {
    expect(english.keys.toSet(), contractKeys);
  });

  for (final entry in AmbientMusicLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, translated text', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        final reason = '${entry.key}:${message.key}';
        expect(translated.trim(), isNotEmpty, reason: reason);
        expect(
          placeholders.allMatches(translated).map((m) => m[0]).toSet(),
          placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
          reason: reason,
        );
        if (entry.key != 'en' && !sameAsEnglishAllowed.contains(message.key)) {
          expect(translated, isNot(message.value), reason: '$reason is English');
        }
      }
    });
  }

  test('the maintainer wording is used in French', () {
    final french = AmbientMusicLocale.values['fr']!;
    expect(french[AmbientMusicLocale.title], 'Musique d’ambiance');
    expect(french[AmbientMusicLocale.volumeTitle], 'Volume de la musique');
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    const key = AmbientMusicLocale.title;
    final traditional = AmbientMusicLocale.values['zh_Hant']![key];
    final simplified = AmbientMusicLocale.values['zh']![key];
    expect(traditional, isNot(simplified));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(
        AmbientMusicLocale.forLocale(locale, key),
        traditional,
        reason: locale.toString(),
      );
    }
    expect(AmbientMusicLocale.forLocale(const Locale('zh', 'CN'), key), simplified);
    expect(AmbientMusicLocale.forLocale(const Locale('nl'), key), english[key]);
  });

  test('every key is used by a surface, and every used key exists', () {
    final sources = <String>[
      'lib/screens/settings_screen/new_settings_options/widgets/'
          'ambient_music_setting_rows.dart',
      'lib/screens/settings_screen/new_settings_options/'
          'themes_settings_content.dart',
    ].map((path) => File(path).readAsStringSync()).join('\n');
    final used = RegExp(r'AmbientMusicLocale\.(\w+)')
        .allMatches(sources)
        .map((m) => m[1]!)
        .where(
          (name) => !const {
            'text',
            'format',
            'forLocale',
            'codeFor',
            'values',
          }.contains(name),
        )
        .toSet();
    expect(english.keys, containsAll(used));
    expect(used, english.keys.toSet(), reason: 'a key without a surface');
  });

  group('settings rows', () {
    late FakeBackend backend;
    late HomeMusicService service;

    setUp(() async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      backend = FakeBackend();
      final userMusic = FakeUserMusic();
      service = HomeMusicService.forTesting(
        backend: backend,
        gate: FrontendMediaGate(),
        session: ValueNotifier<bool>(false),
        sessionActive: () => false,
        userMusic: userMusic,
        userMusicPlaying: () => false,
        userMusicDucked: () => false,
        bundledTrackPath: () async => '/bundle/once_upon_a_time_loop.ogg',
        customDirectory: () async =>
            Directory.systemTemp.createTempSync('neostation-ambient-rows-'),
      );
    });

    Future<void> pump(WidgetTester tester, Locale locale) async {
      await tester.runAsync(service.init);
      await tester.pumpWidget(
        MediaQuery(
          data: const MediaQueryData(size: Size(1920, 1080)),
          child: ScreenUtilInit(
            designSize: const Size(1920, 1080),
            builder: (context, child) => MaterialApp(
              locale: locale,
              supportedLocales: const <Locale>[
                Locale('en'),
                Locale('fr'),
                Locale('ja'),
              ],
              localizationsDelegates: GlobalMaterialLocalizations.delegates,
              home: Scaffold(
                body: Column(
                  children: [
                    AmbientMusicEnabledRow(focused: false, service: service),
                    AmbientMusicVolumeRow(focused: true, service: service),
                  ],
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('the switch and the volume show the stored values, in the '
        'app language, and write them', (tester) async {
      await pump(tester, const Locale('fr'));
      expect(find.text('Musique d’ambiance'), findsOneWidget);
      expect(find.text('Piste : Once Upon a Time — TAD'), findsOneWidget);
      expect(find.text('Volume de la musique'), findsOneWidget);
      final chip = tester.widget<SettingValueChip>(
        find.descendant(
          of: find.byKey(AmbientMusicVolumeRow.chipKey),
          matching: find.byType(SettingValueChip),
        ),
      );
      expect(chip.text, '50 %');
      final toggle = tester.widget<CustomToggleSwitch>(
        find.byKey(AmbientMusicEnabledRow.toggleKey),
      );
      expect(toggle.value, isTrue);

      await tester.runAsync(() => service.setEnabled(false));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<CustomToggleSwitch>(
              find.byKey(AmbientMusicEnabledRow.toggleKey),
            )
            .value,
        isFalse,
      );

      // The chip steps the volume by 10 %.
      await tester.runAsync(() async {
        await tester.tap(find.byKey(AmbientMusicVolumeRow.chipKey));
        await Future<void>.delayed(const Duration(milliseconds: 50));
      });
      await tester.pumpAndSettle();
      expect(service.volume, closeTo(0.6, 1e-9));
      final prefs = await SharedPreferences.getInstance();
      expect(prefs.getBool(HomeMusicService.enabledPreferenceKey), isFalse);
      expect(
        prefs.getDouble(HomeMusicService.volumePreferenceKey),
        closeTo(0.6, 1e-9),
      );
    });

    test('the A button walks the volume by 10 % and wraps', () {
      expect(AmbientMusicVolumeRow.nextStep(0.5), closeTo(0.6, 1e-9));
      expect(AmbientMusicVolumeRow.nextStep(0.55), closeTo(0.6, 1e-9));
      expect(AmbientMusicVolumeRow.nextStep(0.05), closeTo(0.1, 1e-9));
      expect(AmbientMusicVolumeRow.nextStep(0.9), closeTo(1.0, 1e-9));
      expect(AmbientMusicVolumeRow.nextStep(1.0), closeTo(0.1, 1e-9));
    });
  });
}
