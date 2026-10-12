import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/skin_browser_locale.dart';

/// Build 448: texts of the skin pages' folding filters, preview selector and
/// skin details, in the twelve languages.
void main() {
  final english = SkinBrowserLocale.values['en']!;

  test('the catalog covers exactly the twelve languages and translates every key', () {
    expect(SkinBrowserLocale.values.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    for (final entry in SkinBrowserLocale.values.entries) {
      expect(entry.value.keys.toSet(), english.keys.toSet(), reason: entry.key);
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        expect(translated.trim(), isNotEmpty, reason: '${entry.key}:${message.key}');
        // "Filter" is German as well as English.
        final same = entry.key == 'de' && message.key == SkinBrowserLocale.filters;
        if (entry.key != 'en' && !same) {
          expect(translated, isNot(message.value), reason: '${entry.key}:${message.key} is English');
        }
      }
    }
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    const key = SkinBrowserLocale.filters;
    final traditional = SkinBrowserLocale.values['zh_Hant']![key];
    expect(traditional, isNot(SkinBrowserLocale.values['zh']![key]));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
    ]) {
      expect(SkinBrowserLocale.forLocale(locale, key), traditional, reason: '$locale');
    }
    expect(SkinBrowserLocale.forLocale(const Locale('nl'), key), english[key]);
  });

  test('every key is used by a skin page, and every used key exists', () {
    final sources = <String>[
      'lib/screens/libretro/libretro_skin_catalog_screen.dart',
      'lib/screens/libretro/libretro_skin_manager_screen.dart',
    ].map((path) => File(path).readAsStringSync()).join('\n');
    final used = RegExp(r'SkinBrowserLocale\.(\w+)')
        .allMatches(sources)
        .map((m) => m[1]!)
        .where((name) => !const {'text', 'forLocale', 'codeFor', 'values'}.contains(name))
        .toSet();
    expect(used, english.keys.toSet());
  });
}
