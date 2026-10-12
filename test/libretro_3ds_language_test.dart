import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/services/libretro_3ds_language.dart';
import 'package:neostation/services/libretro_core_catalog.dart';

/// docs/libretro-3ds-system-settings.md § 3.2: the 3DS system language
/// (`citra_language_value`) that follows the NeoStation language, with an
/// explicit English fallback for Indonesian, which the console never had.
void main() {
  const table = <String, String>{
    'en': 'English',
    'ja': 'Japanese',
    'fr': 'French',
    'es': 'Spanish',
    'de': 'German',
    'it': 'Italian',
    'pt': 'Portuguese',
    'ru': 'Russian',
    'ko': 'Korean',
    'zh_Hant': 'Traditional Chinese',
    'zh': 'Simplified Chinese',
    'id': 'English',
  };

  test('the twelve NeoStation languages map to a core value', () {
    expect(table.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    for (final entry in table.entries) {
      expect(Libretro3dsLanguage.forAppLocale(Locale(entry.key)), entry.value, reason: entry.key);
      expect(Libretro3dsLanguage.coreValues, contains(entry.value), reason: entry.key);
    }
  });

  test('Indonesian and unknown languages fall back to English, and say so', () {
    expect(Libretro3dsLanguage.fallback, 'English');
    expect(Libretro3dsLanguage.forAppLocale(const Locale('id')), 'English');
    expect(Libretro3dsLanguage.isFallback(const Locale('id')), isTrue);
    // A language NeoStation does not ship (Dutch exists on the 3DS, but
    // NeoStation has no Dutch interface) shows NeoStation itself in English
    // (LibretroLocale.localeKey): the 3DS follows that English interface,
    // which is a match, not the Indonesian-style fallback note.
    expect(Libretro3dsLanguage.forAppLocale(const Locale('nl')), 'English');
    expect(LibretroLocale.localeKey(const Locale('nl')), 'en');
    expect(Libretro3dsLanguage.isFallback(const Locale('nl')), isFalse);
    expect(Libretro3dsLanguage.forAppLocale(const Locale('xx')), 'English');
    // English itself is a real match, not a fallback.
    expect(Libretro3dsLanguage.isFallback(const Locale('en')), isFalse);
    for (final language in table.keys.where((language) => language != 'id')) {
      expect(Libretro3dsLanguage.isFallback(Locale(language)), isFalse, reason: language);
    }
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(Libretro3dsLanguage.forAppLocale(locale), 'Traditional Chinese', reason: locale.toString());
    }
    expect(Libretro3dsLanguage.forAppLocale(const Locale('zh')), 'Simplified Chinese');
    expect(Libretro3dsLanguage.forAppLocale(const Locale('zh', 'CN')), 'Simplified Chinese');
    expect(Libretro3dsLanguage.forAppLocale(const Locale('pt', 'BR')), 'Portuguese');
  });

  test('the value list is the catalog setting, every value labelled twelve times', () {
    final setting = LibretroCoreCatalog.cores['azahar']!.settings
        .singleWhere((setting) => setting.key == Libretro3dsLanguage.optionKey);
    expect(Libretro3dsLanguage.optionKey, 'citra_language_value');
    expect(Libretro3dsLanguage.coreValues, setting.values);
    expect(Libretro3dsLanguage.coreValues.toSet(), hasLength(12));
    for (final value in Libretro3dsLanguage.coreValues) {
      final key = Libretro3dsLanguage.labelKeyFor(value);
      expect(key, setting.valueLabelKeys[value], reason: value);
      for (final entry in LibretroLocale.values.entries) {
        expect(entry.value[key]?.trim(), isNotEmpty, reason: '${entry.key}:$value');
      }
    }
    expect(Libretro3dsLanguage.labelKeyFor('Klingon'), isNull);
    expect(Libretro3dsLanguage.labelKeyFor('english'), isNull);
  });

  test('the fallback and automatic notes keep their language placeholder', () {
    for (final entry in LibretroLocale.values.entries) {
      expect(entry.value['lang3dsFallback'], contains('{language}'), reason: entry.key);
      expect(entry.value['lang3dsAutomatic'], contains('{language}'), reason: entry.key);
    }
    expect(
      LibretroLocale.format(const Locale('fr'), 'lang3dsFallback', {'language': 'Indonésien'}),
      'Indonésien n’existe pas sur 3DS : anglais',
    );
  });
}
