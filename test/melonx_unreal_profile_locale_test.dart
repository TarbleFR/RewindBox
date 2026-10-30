import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/melonx_unreal_profile_locale.dart';

void main() {
  final english = MelonxUnrealProfileLocale.values['en']!;
  final placeholders = RegExp(r'\{\w+\}');

  test('Unreal profile catalog covers all twelve application languages', () {
    expect(MelonxUnrealProfileLocale.values.keys.toSet(),
        AppLocale.supportedLanguages.keys.toSet());
    expect(MelonxUnrealProfileLocale.values.length, 12);
  });

  for (final entry in MelonxUnrealProfileLocale.values.entries) {
    test('${entry.key}: all messages and placeholders are translated', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        final reason = '${entry.key}:${message.key}';
        expect(translated.trim(), isNotEmpty, reason: reason);
        expect(placeholders.allMatches(translated).map((m) => m[0]).toSet(),
            placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
            reason: reason);
        if (entry.key != 'en') {
          expect(translated, isNot(message.value), reason: reason);
        }
      }
    });
  }

  test('Traditional Chinese script and regional selections use their catalog', () {
    final traditional = MelonxUnrealProfileLocale.values['zh_Hant']!['title'];
    final simplified = MelonxUnrealProfileLocale.values['zh']!['title'];
    expect(traditional, isNot(simplified));
    for (final locale in [
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'), const Locale('zh', 'HK'),
      const Locale('zh', 'MO'), const Locale('zh_Hant'),
    ]) {
      expect(MelonxUnrealProfileLocale.forLocale(locale, 'title'), traditional);
    }
    expect(MelonxUnrealProfileLocale.forLocale(const Locale('zh', 'CN'), 'title'), simplified);
    expect(MelonxUnrealProfileLocale.forLocale(const Locale('nl'), 'title'), english['title']);
  });

  test('project names are substituted without changing technical identifiers', () {
    for (final language in MelonxUnrealProfileLocale.values.keys) {
      final message = MelonxUnrealProfileLocale.forLocale(
          Locale(language), 'project', {'project': 'Phoenix'});
      expect(message, contains('Phoenix'));
      expect(message, isNot(contains('{project}')));
    }
  });
}
