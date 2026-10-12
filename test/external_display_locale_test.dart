import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/external_display_locale.dart';

void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = ExternalDisplayLocale.values['en']!;

  // docs/external-display-universal.md § 6 and § 10. Retired with Build 449:
  // `menuOnTv`, `menuOnTvHelp` (the "Show the menu on the TV" row) and
  // `menuOffMirroring` (its status line, review m2 of 12 October 2026):
  // outside a game the TV now always mirrors the iPhone, which
  // `mirroringOutsideGames` says.
  const contractKeys = <String>{
    'title',
    'description',
    'modeTitle',
    'modeAutomatic',
    'modeFit',
    'modeFill',
    'modeOriginal',
    'modeAutomaticHelp',
    'modeFitHelp',
    'modeFillHelp',
    'modeOriginalHelp',
    'fillCrops',
    'noExternalScreen',
    'externalScreen',
    'gameOnExternal',
    'mirroringOff',
    'unsupportedEngine',
    'mirroringOutsideGames',
    'unavailable',
    'saveFailed',
    'technicalCode',
  };

  test('the external display catalog covers exactly the twelve languages', () {
    expect(
      ExternalDisplayLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(ExternalDisplayLocale.values.length, 12);
  });

  test('the English catalog holds exactly the keys of the contract', () {
    expect(english.keys.toSet(), contractKeys);
    expect(english[ExternalDisplayLocale.externalScreen], contains('{width}'));
    expect(english[ExternalDisplayLocale.externalScreen], contains('{height}'));
    expect(english[ExternalDisplayLocale.technicalCode], contains('{code}'));
  });

  for (final entry in ExternalDisplayLocale.values.entries) {
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
    final french = ExternalDisplayLocale.values['fr']!;
    expect(french[ExternalDisplayLocale.title], 'AirPlay et écran externe');
    expect(french[ExternalDisplayLocale.modeAutomatic], 'Automatique');
    expect(french[ExternalDisplayLocale.modeFit], 'Adapter à l’écran');
    expect(french[ExternalDisplayLocale.modeFill], 'Remplir l’écran');
    expect(french[ExternalDisplayLocale.modeOriginal], 'Format d’origine');
  });

  test('the texts say that the TV mirrors the iPhone outside a game', () {
    // Build 449: no text may promise NeoStation's own picture outside a
    // game any more (the TV view of the second engine is gone).
    final french = ExternalDisplayLocale.values['fr']!;
    expect(
      french[ExternalDisplayLocale.description],
      'Pendant un jeu, NeoStation affiche le jeu en plein écran sur le '
      'téléviseur ou l’adaptateur, les commandes restant sur l’iPhone. '
      'Hors jeu, iOS recopie l’iPhone.',
    );
    expect(
      french[ExternalDisplayLocale.mirroringOutsideGames],
      'Hors jeu, iOS recopie l’interface NeoStation de l’iPhone.',
    );
    for (final entry in ExternalDisplayLocale.values.entries) {
      for (final key in <String>[
        ExternalDisplayLocale.description,
        ExternalDisplayLocale.mirroringOutsideGames,
      ]) {
        expect(entry.value[key], contains('iPhone'), reason: '${entry.key}:$key');
      }
      expect(
        entry.value[ExternalDisplayLocale.mirroringOutsideGames],
        contains('NeoStation'),
        reason: '${entry.key}: the interface that is mirrored is named',
      );
    }
  });

  test('the four format names are distinct in every language', () {
    for (final entry in ExternalDisplayLocale.values.entries) {
      final names = <String>{
        entry.value[ExternalDisplayLocale.modeAutomatic]!,
        entry.value[ExternalDisplayLocale.modeFit]!,
        entry.value[ExternalDisplayLocale.modeFill]!,
        entry.value[ExternalDisplayLocale.modeOriginal]!,
      };
      expect(names.length, 4, reason: entry.key);
    }
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    const key = ExternalDisplayLocale.title;
    final traditional = ExternalDisplayLocale.values['zh_Hant']![key];
    final simplified = ExternalDisplayLocale.values['zh']![key];
    expect(traditional, isNot(simplified));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(
        ExternalDisplayLocale.forLocale(locale, key),
        traditional,
        reason: locale.toString(),
      );
    }
    expect(ExternalDisplayLocale.forLocale(const Locale('zh'), key), simplified);
    expect(
      ExternalDisplayLocale.values['zh_Hant']![ExternalDisplayLocale
          .mirroringOutsideGames],
      isNot(
        ExternalDisplayLocale.values['zh']![ExternalDisplayLocale
            .mirroringOutsideGames],
      ),
      reason: 'the mirroring line of Build 449 has its own Traditional text',
    );
    expect(
      ExternalDisplayLocale.forLocale(const Locale('zh', 'CN'), key),
      simplified,
    );
    expect(
      ExternalDisplayLocale.forLocale(const Locale('nl'), key),
      english[key],
    );
  });

  testWidgets('format() follows the app locale and fills the parameters', (
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
      ExternalDisplayLocale.format(
        captured,
        ExternalDisplayLocale.externalScreen,
        <String, Object?>{'width': 1920, 'height': 1080},
      ),
      'Écran externe : 1920×1080',
    );
    expect(
      ExternalDisplayLocale.format(
        captured,
        ExternalDisplayLocale.technicalCode,
        <String, Object?>{'code': 'SAVE_FAILED'},
      ),
      'Code technique : SAVE_FAILED',
    );
    expect(
      ExternalDisplayLocale.text(captured, ExternalDisplayLocale.fillCrops),
      'Remplir l’écran coupe le haut et le bas de l’image.',
    );
  });

  test('every key used by the settings rows exists, and every key is used', () {
    final source = File(
      'lib/screens/settings_screen/new_settings_options/widgets/'
      'external_display_setting_rows.dart',
    ).readAsStringSync();
    final used = RegExp(r'ExternalDisplayLocale\.(\w+)')
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
    expect(english.keys, containsAll(used));
    expect(used, english.keys.toSet(), reason: 'a key without a surface');
  });
}
