import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/switch2_settings_locale.dart';
import 'package:neostation/services/s2arm_settings.dart';

/// The Switch 2 settings strings: 12 locales with identical keys, no empty text, the `menu.*` table and the language
/// endonyms sent to the native in-game menu.
void main() {
  const codes = ['en', 'fr', 'es', 'de', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh', 'zh_Hant'];
  const languages = [
    'AmericanEnglish', 'BritishEnglish', 'French', 'CanadianFrench', 'German', 'Italian', 'Spanish', 'LatinAmericanSpanish',
    'Dutch', 'Portuguese', 'BrazilianPortuguese', 'Russian', 'Polish', 'Japanese', 'Korean', 'SimplifiedChinese',
    'TraditionalChinese', 'Thai',
  ];

  test('the 12 project locales carry the same keys', () {
    expect(Switch2SettingsLocale.values.keys.toSet(), codes.toSet());
    final english = Switch2SettingsLocale.values['en']!.keys.toSet();
    for (final code in codes) {
      expect(Switch2SettingsLocale.values[code]!.keys.toSet(), english, reason: code);
    }
  });

  test('no text is empty', () {
    for (final code in codes) {
      Switch2SettingsLocale.values[code]!.forEach((key, value) {
        expect(value.trim(), isNotEmpty, reason: '$code $key');
      });
      Switch2SettingsLocale.menuStrings(code).forEach((key, value) {
        expect(value.trim(), isNotEmpty, reason: '$code $key');
      });
    }
  });

  test('every menu.* key is sent for every locale', () {
    const menuKeys = [
      'menu.title', 'menu.resume', 'menu.performanceOn', 'menu.performanceOff', 'menu.settings', 'menu.resolution',
      'menu.antiAliasing', 'menu.scalingFilter', 'menu.frameRateLimit', 'menu.mode', 'menu.imageFormat', 'menu.gameLanguage',
      'menu.nextLaunch', 'menu.quit', 'menu.quitTitle', 'menu.quitMessage', 'menu.cancel', 'menu.back', 'menu.res050',
      'menu.res075', 'menu.res100', 'menu.aaNone', 'menu.aaSmaaMedium', 'menu.aaSmaaHigh', 'menu.filterBilinear',
      'menu.filterNearest', 'menu.fps30', 'menu.fps60', 'menu.fps120', 'menu.fpsUnlimited', 'menu.modeHandheld',
      'menu.modeDocked', 'menu.formatWide', 'menu.format169', 'menu.languageAuto',
    ];
    for (final code in codes) {
      final strings = Switch2SettingsLocale.menuStrings(code);
      for (final key in menuKeys) {
        expect(strings.containsKey(key), isTrue, reason: '$code $key');
      }
      expect(strings.keys.where((key) => key.startsWith('menu.')).length, menuKeys.length, reason: code);
    }
  });

  test('language names are endonyms for exactly the 18 SystemLanguage names', () {
    expect(Switch2SettingsLocale.languageNames.keys.toSet(), languages.toSet());
    expect(S2ArmSettings.gameLanguages.toSet(), languages.toSet());
    for (final code in codes) {
      final strings = Switch2SettingsLocale.menuStrings(code);
      for (final name in languages) {
        expect(strings['lang.$name'], Switch2SettingsLocale.languageNames[name], reason: '$code $name');
      }
    }
  });

  test('codeFor maps Traditional Chinese regions and unknown languages', () {
    expect(Switch2SettingsLocale.codeFor(const Locale('fr', 'CA')), 'fr');
    expect(Switch2SettingsLocale.codeFor(const Locale('zh')), 'zh');
    expect(Switch2SettingsLocale.codeFor(const Locale('zh', 'TW')), 'zh_Hant');
    expect(Switch2SettingsLocale.codeFor(const Locale('sv')), 'en');
  });
}
