import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_reader_locale.dart';

void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = LibraryReaderLocale.values['en']!;

  // Words that are genuinely identical in a language (loanwords, the same
  // word, or a number format that needs no translation).
  const identical = <String>{
    'fr:pageNumber', 'fr:image',
    'es:themeSepia',
    'de:themeSystem', 'de:themeSepia',
    'id:themeSepia',
    // "Volume" is the usual word for a manga volume in Portuguese and Italian.
    'pt:volumeNumber', 'it:volumeNumber',
    // Percentages written like English in these languages.
    'pt:percentRead', 'it:percentRead', 'id:percentRead', 'ja:percentRead',
    'ko:percentRead', 'zh:percentRead', 'zh_Hant:percentRead',
    // Reader settings: "Navigation" and "Pages" are the maintainer's French
    // words; "Text" and "Navigation" are the usual German words.
    'fr:sectionNavigation', 'fr:textLayoutPages',
    'de:sectionText', 'de:sectionNavigation',
  };

  test('the reader catalog covers exactly the twelve NeoStation languages', () {
    expect(
      LibraryReaderLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(LibraryReaderLocale.values.length, 12);
  });

  for (final entry in LibraryReaderLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, no empty text', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        expect(
          translated.trim(),
          isNotEmpty,
          reason: '${entry.key}:${message.key}',
        );
        expect(
          placeholders.allMatches(translated).map((m) => m[0]).toSet(),
          placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
          reason: '${entry.key}:${message.key}',
        );
        if (entry.key != 'en' &&
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

  test('script and regional Chinese settings select Traditional Chinese', () {
    final traditional = LibraryReaderLocale.values['zh_Hant']!['close'];
    final simplified = LibraryReaderLocale.values['zh']!['close'];
    expect(traditional, isNot(simplified));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(
        LibraryReaderLocale.forLocale(locale, 'close'),
        traditional,
        reason: locale.toString(),
      );
    }
    expect(
      LibraryReaderLocale.forLocale(const Locale('zh'), 'close'),
      simplified,
    );
    expect(
      LibraryReaderLocale.forLocale(const Locale('zh', 'CN'), 'close'),
      simplified,
    );
    expect(
      LibraryReaderLocale.forLocale(const Locale('nl'), 'close'),
      english['close'],
    );
  });

  testWidgets('text() and format() follow the app locale', (tester) async {
    late BuildContext captured;
    await tester.pumpWidget(
      Localizations(
        locale: const Locale('fr'),
        delegates: const <LocalizationsDelegate<dynamic>>[
          DefaultWidgetsLocalizations.delegate,
        ],
        child: Builder(
          builder: (context) {
            captured = context;
            return const SizedBox.shrink();
          },
        ),
      ),
    );
    expect(LibraryReaderLocale.text(captured, 'close'), 'Fermer');
    expect(
      LibraryReaderLocale.format(captured, 'pageOfTotal', <String, Object?>{
        'page': 3,
        'total': 12,
      }),
      'Page 3 sur 12',
    );
  });

  test('every key used by the reader sources exists in the catalog', () {
    // Keys passed as literals to text()/format() and the error mapping.
    final used = <String>{};
    final pattern = RegExp(
      r"""(?:LibraryReaderLocale\.(?:text|format)\(\s*\w+,\s*|t\(|labelKey:\s*|LibraryReaderErrorInfo\(\s*)'(\w+)'""",
    );
    final mapping = RegExp(r"=> '((?:error|issue)\w+)'");
    final files = <File>[
      ...Directory('lib/screens/library_screen/reader')
          .listSync()
          .whereType<File>()
          .where((file) => file.path.endsWith('.dart')),
      File('lib/screens/library_screen/library_pdf_reader_screen.dart'),
    ];
    for (final file in files) {
      final source = file.readAsStringSync();
      used.addAll(pattern.allMatches(source).map((m) => m[1]!));
      used.addAll(mapping.allMatches(source).map((m) => m[1]!));
    }
    expect(used.length, greaterThan(40));
    expect(english.keys, containsAll(used));
  });
}
