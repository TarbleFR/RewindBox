// Coverage of the local book library catalog: twelve languages, same keys,
// same placeholders, nothing empty or left in English, Traditional Chinese
// selection, and a translated explanation for every import problem.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_local_locale.dart';
import 'package:neostation/screens/library_screen/library_local_view.dart';
import 'package:neostation/services/library_local_models.dart';

void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = LibraryLocalLocale.values['en']!;

  // Pure patterns (numbers and a file name) and size units written the same
  // way in that language.
  const patternKeys = <String>{'importProgress'};
  const identical = <String>{
    'es:sizeKb',
    'es:sizeMb',
    'pt:sizeKb',
    'pt:sizeMb',
    'de:sizeKb',
    'de:sizeMb',
    'it:sizeKb',
    'it:sizeMb',
    'id:sizeKb',
    'id:sizeMb',
    'ja:sizeKb',
    'ja:sizeMb',
    'zh:sizeKb',
    'zh:sizeMb',
    'zh_Hant:sizeKb',
    'zh_Hant:sizeMb',
  };

  test('covers exactly the twelve NeoStation languages', () {
    expect(
      LibraryLocalLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(LibraryLocalLocale.values.keys, hasLength(12));
  });

  for (final entry in LibraryLocalLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, nothing empty', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        expect(translated.trim(), isNotEmpty, reason: message.key);
        expect(
          placeholders.allMatches(translated).map((m) => m[0]).toSet(),
          placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
          reason: '${entry.key}:${message.key}',
        );
        if (entry.key != 'en' &&
            !patternKeys.contains(message.key) &&
            !identical.contains('${entry.key}:${message.key}')) {
          expect(
            translated,
            isNot(message.value),
            reason: '${entry.key}:${message.key} is an English copy',
          );
        }
      }
    });
  }

  test('script or region selects Traditional Chinese', () {
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(LibraryLocalLocale.localeKey(locale), 'zh_Hant');
      expect(
        LibraryLocalLocale.forLocale(locale, 'deleteCopy'),
        LibraryLocalLocale.values['zh_Hant']!['deleteCopy'],
      );
    }
    expect(LibraryLocalLocale.localeKey(const Locale('zh')), 'zh');
    expect(LibraryLocalLocale.localeKey(const Locale('pt', 'BR')), 'pt');
    expect(LibraryLocalLocale.localeKey(const Locale('nl')), 'en');
  });

  test('every import problem has a translated explanation', () {
    for (final issue in LibraryBookIssue.values) {
      final key = libraryBookIssueKey(issue);
      for (final language in LibraryLocalLocale.values.keys) {
        expect(
          LibraryLocalLocale.values[language]![key],
          isNotNull,
          reason: '$language:$key',
        );
      }
    }
  });

  test('the delete confirmation says the original file is kept', () {
    expect(english['deleteBody'], contains('original file stays'));
    expect(english['deleteBody'], contains('only its own copy'));
    expect(
      LibraryLocalLocale.values['fr']!['deleteBody'],
      contains('Le fichier d’origine reste'),
    );
  });
}
