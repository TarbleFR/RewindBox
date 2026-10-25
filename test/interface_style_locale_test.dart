import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/interface_style_locale.dart';

/// Settings › Themes › User interface must read in every supported language:
/// same keys, same placeholders, actual translations.
void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = InterfaceStyleLocale.values['en']!;

  // Product names, a bare percentage and a few words shared with English
  // (French "Notifications", "Violet", "Cyan", "Halo"; German "Cyan") read the
  // same in several languages.
  const sameAsEnglishAllowed = <String>{
    InterfaceStyleLocale.styleLiquidGlass,
    InterfaceStyleLocale.styleNeoStation,
    InterfaceStyleLocale.valuePercent,
    InterfaceStyleLocale.statusNotifications,
    InterfaceStyleLocale.accentViolet,
    InterfaceStyleLocale.accentCyan,
    InterfaceStyleLocale.focusGlow,
  };

  test('the catalog covers exactly the twelve languages', () {
    expect(
      InterfaceStyleLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(InterfaceStyleLocale.values.length, 12);
  });

  test('English holds every key the screen uses', () {
    expect(english.length, greaterThanOrEqualTo(100));
    for (final key in [
      InterfaceStyleLocale.title,
      InterfaceStyleLocale.sectionStyle,
      InterfaceStyleLocale.sectionTabBar,
      InterfaceStyleLocale.sectionSurfaces,
      InterfaceStyleLocale.sectionMotion,
      InterfaceStyleLocale.sectionPreview,
      InterfaceStyleLocale.sectionStatusBar,
      InterfaceStyleLocale.sectionColors,
      InterfaceStyleLocale.styleNeoStation,
      InterfaceStyleLocale.sidePanel,
      InterfaceStyleLocale.apply,
      InterfaceStyleLocale.resetDefaults,
      InterfaceStyleLocale.valuePercent,
    ]) {
      expect(english[key], isNotEmpty);
    }
  });

  for (final entry in InterfaceStyleLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, translated text', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        final reason = '${entry.key}:${message.key}';
        expect(translated.trim(), isNotEmpty, reason: reason);
        expect(
          placeholders.allMatches(translated).map((m) => m.group(0)).toSet(),
          placeholders.allMatches(message.value).map((m) => m.group(0)).toSet(),
          reason: reason,
        );
        if (entry.key != 'en' && !sameAsEnglishAllowed.contains(message.key)) {
          expect(translated, isNot(message.value), reason: reason);
        }
      }
    });
  }

  test('Traditional Chinese is selected by script or region', () {
    expect(InterfaceStyleLocale.codeFor(const Locale('zh')), 'zh');
    expect(
      InterfaceStyleLocale.codeFor(
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      ),
      'zh_Hant',
    );
    expect(InterfaceStyleLocale.codeFor(const Locale('zh', 'TW')), 'zh_Hant');
    expect(InterfaceStyleLocale.codeFor(const Locale('zh', 'HK')), 'zh_Hant');
    expect(InterfaceStyleLocale.codeFor(const Locale('xx')), 'en');
    expect(
      InterfaceStyleLocale.forLocale(
        const Locale('fr'),
        InterfaceStyleLocale.apply,
      ),
      'Appliquer',
    );
  });
}
