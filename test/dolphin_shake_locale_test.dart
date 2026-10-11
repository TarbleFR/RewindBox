import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/dolphin_extended_locale.dart';
import 'package:neostation/l10n/dolphin_import_locale.dart';
import 'package:neostation/l10n/dolphin_shake_locale.dart';

/// Build 440 Wii "Shake": the touch button and the Controls row texts reach
/// the native Dolphin overlay and menu only through the session labels.
void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = DolphinShakeLocale.values['en']!;
  const keys = <String>{
    'shakeTouchButton',
    'shakeTouchHint',
    'shakeAssign',
    'shakeAssignHelp',
    'shakeMixed',
  };

  test('the Shake catalog covers exactly the twelve NeoStation languages', () {
    expect(
      DolphinShakeLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(DolphinShakeLocale.values.length, 12);
    expect(english.keys.toSet(), keys);
  });

  for (final entry in DolphinShakeLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, translated text', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        expect(translated.trim(), isNotEmpty,
            reason: '${entry.key}:${message.key}');
        expect(
          placeholders.allMatches(translated).map((m) => m[0]).toSet(),
          placeholders.allMatches(message.value).map((m) => m[0]).toSet(),
          reason: '${entry.key}:${message.key}',
        );
        if (entry.key != 'en') {
          expect(translated, isNot(message.value),
              reason: '${entry.key}:${message.key} is an English copy');
        }
      }
    });
  }

  test('session labels carry the Shake texts of the selected language', () {
    for (final language in DolphinShakeLocale.values.keys) {
      final locale = language == 'zh_Hant'
          ? const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')
          : Locale(language);
      final labels = DolphinImportLocale.labelsFor(locale);
      expect(labels['__locale'], language);
      for (final key in keys) {
        expect(labels[key], DolphinShakeLocale.values[language]![key],
            reason: '$language:$key');
      }
      // The native Shake row reuses these existing session labels.
      for (final reused in ['unassigned', 'chooseInput', 'clearBinding', 'bindings']) {
        expect(labels[reused], isNotNull, reason: '$language:$reused');
        expect(labels[reused]!.trim(), isNotEmpty, reason: '$language:$reused');
        if (language != 'en') {
          expect(labels[reused], isNot(DolphinImportLocale.values['en']![reused]),
              reason: '$language:$reused');
        }
      }
    }
    expect(DolphinImportLocale.labelsFor(const Locale('fr'))['shakeAssign'],
        'Secouer');
  });

  test('script and regional Chinese settings select Traditional Chinese', () {
    final traditional = DolphinShakeLocale.values['zh_Hant']!;
    final simplified = DolphinShakeLocale.values['zh']!;
    expect(traditional['shakeAssign'], isNot(simplified['shakeAssign']));
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
    ]) {
      final labels = DolphinImportLocale.labelsFor(locale);
      for (final key in keys) {
        expect(labels[key], traditional[key], reason: '$locale:$key');
      }
    }
    for (final locale in <Locale>[const Locale('zh'), const Locale('zh', 'CN')]) {
      final labels = DolphinImportLocale.labelsFor(locale);
      for (final key in keys) {
        expect(labels[key], simplified[key], reason: '$locale:$key');
      }
    }
    expect(DolphinShakeLocale.labels('nl'), english);
  });

  test('Shake keys never replace another Dolphin session label', () {
    for (final language in DolphinShakeLocale.values.keys) {
      final older = <String>{
        ...DolphinImportLocale.values['en']!.keys,
        ...?DolphinImportLocale.values[language]?.keys,
        ...DolphinExtendedLocale.labels(language).keys,
      };
      expect(older.intersection(keys), isEmpty, reason: language);
    }
  });

  test('every Shake label read by the native overlay and menu exists', () {
    final used = <String>{};
    final pattern = RegExp(r'''@"(shake[A-Z]\w*)"''');
    for (final path in [
      'packages/dolphin_internal_bridge/ios/Classes/DolphinSessionMenu.mm',
      'packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm',
    ]) {
      used.addAll(pattern.allMatches(File(path).readAsStringSync()).map((m) => m[1]!));
    }
    expect(used, containsAll(<String>[
      'shakeTouchButton',
      'shakeTouchHint',
      'shakeAssign',
      'shakeAssignHelp',
      'shakeMixed',
    ]));
    expect(keys, containsAll(used));
  });
}
