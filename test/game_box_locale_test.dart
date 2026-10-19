import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/game_box_locale.dart';

void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = GameBoxLocale.values['en']!;

  // Shared words that are legitimately written the same as in English.
  const sameAsEnglish = {
    'source', 'play', 'region.us', 'region.eu', 'region.it', 'region.fr', 'region.pt', 'region.au',
    'region.asi', 'region.ca', 'region.kr', 'region.cn', 'region.br', 'region.tw', 'region.jp',
    'region.uk', 'region.ru', 'region.se', 'region.nl', 'region.de', 'region.sp', 'region.wor',
    'supportDisc', 'supportCartridge', 'lang.it', 'lang.id', 'lang.ko', 'lang.pt', 'lang.fr', 'lang.de',
    'lang.ru', 'lang.ja', 'lang.es', 'lang.en', 'retry', 'original', 'front', 'back', 'edition', 'close',
  };

  test('the box catalogue covers exactly the twelve NeoStation languages', () {
    expect(GameBoxLocale.values.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    expect(GameBoxLocale.values.length, 12);
  });

  for (final entry in GameBoxLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, translated text', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      var translatedCount = 0;
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        final reason = '${entry.key}:${message.key}';
        expect(translated.trim(), isNotEmpty, reason: reason);
        expect(
          placeholders.allMatches(translated).map((m) => m[0]).toSet(),
          placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
          reason: reason,
        );
        if (translated != message.value) translatedCount++;
        if (entry.key != 'en' && !sameAsEnglish.contains(message.key)) {
          expect(translated, isNot(message.value), reason: '$reason is English');
        }
      }
      if (entry.key != 'en') expect(translatedCount, greaterThan(english.length * 0.7));
    });
  }

  test('script and regional Chinese settings select Traditional Chinese', () {
    const key = GameBoxLocale.readingLanguage;
    final traditional = GameBoxLocale.values['zh_Hant']![key];
    expect(traditional, isNot(GameBoxLocale.values['zh']![key]));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(GameBoxLocale.forLocale(locale, key), traditional, reason: locale.toString());
    }
    expect(GameBoxLocale.forLocale(const Locale('zh', 'CN'), key), GameBoxLocale.values['zh']![key]);
    expect(GameBoxLocale.forLocale(const Locale('xx'), key), english[key]);
  });

  test('every reading language has a translated name in every language', () {
    for (final code in AppLocale.supportedLanguages.keys) {
      for (final locale in GameBoxLocale.locales) {
        expect(GameBoxLocale.forCode(locale, 'lang.$code').trim(), isNotEmpty);
      }
    }
  });

  test('placeholders are filled', () {
    expect(
      GameBoxLocale.fill(GameBoxLocale.forCode('fr', GameBoxLocale.otherEdition), {'region': 'Japon', 'game': 'Europe'}),
      "Édition Japon : ce n'est pas l'édition de votre jeu (Europe).",
    );
  });
}
