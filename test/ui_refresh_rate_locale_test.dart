import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/ui_refresh_rate_locale.dart';

void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = UiRefreshRateLocale.values['en']!;

  test('the 120 Hz catalog covers exactly the twelve NeoStation languages', () {
    expect(
      UiRefreshRateLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(UiRefreshRateLocale.values.length, 12);
  });

  for (final entry in UiRefreshRateLocale.values.entries) {
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
        if (entry.key != 'en') {
          expect(
            translated,
            isNot(message.value),
            reason: '$reason is English',
          );
        }
      }
    });
  }

  test('the maintainer wording is used in French', () {
    final french = UiRefreshRateLocale.values['fr']!;
    expect(french[UiRefreshRateLocale.title], 'Interface 120 Hz');
    expect(
      french[UiRefreshRateLocale.description],
      'Améliore la fluidité des menus et du défilement sur les écrans '
      'compatibles.',
    );
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    const key = UiRefreshRateLocale.title;
    final traditional = UiRefreshRateLocale.values['zh_Hant']![key];
    final simplified = UiRefreshRateLocale.values['zh']![key];
    expect(traditional, isNot(simplified));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(
        UiRefreshRateLocale.forLocale(locale, key),
        traditional,
        reason: locale.toString(),
      );
    }
    expect(UiRefreshRateLocale.forLocale(const Locale('zh'), key), simplified);
    expect(
      UiRefreshRateLocale.forLocale(const Locale('zh', 'CN'), key),
      simplified,
    );
    expect(
      UiRefreshRateLocale.forLocale(const Locale('nl'), key),
      english[key],
    );
  });

  testWidgets('format() follows the app locale and fills the rate', (
    tester,
  ) async {
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
    expect(
      UiRefreshRateLocale.format(
        captured,
        UiRefreshRateLocale.measured,
        <String, Object?>{'hz': 120},
      ),
      'Fréquence mesurée : 120 Hz',
    );
    expect(
      UiRefreshRateLocale.format(
        captured,
        UiRefreshRateLocale.unavailableScreen,
        <String, Object?>{'hz': 60},
      ),
      'Non disponible sur cet écran (maximum 60 Hz).',
    );
  });

  test('every key used by the settings row exists in the catalog', () {
    final source = File(
      'lib/screens/settings_screen/new_settings_options/widgets/'
      'ui_refresh_rate_setting_row.dart',
    ).readAsStringSync();
    final used = RegExp(r'UiRefreshRateLocale\.(\w+)')
        .allMatches(source)
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
    expect(used.length, greaterThanOrEqualTo(12));
    expect(english.keys, containsAll(used));
  });
}
