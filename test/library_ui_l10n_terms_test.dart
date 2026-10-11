// Terms shared by the Library catalogs (hub, sources and title page, local
// library): one Portuguese variant (Brazilian, like AppLocale pt), one
// English spelling (US: catalog, favorites), and menu paths that name the
// Library and its sections exactly as the tab bar and the hub tiles do.
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_feature_locale.dart';
import 'package:neostation/l10n/library_local_locale.dart';
import 'package:neostation/l10n/library_sources_locale.dart';

const Map<String, Map<String, dynamic>> _appLocale =
    <String, Map<String, dynamic>>{
      'en': AppLocale.en,
      'es': AppLocale.es,
      'ru': AppLocale.ru,
      'zh': AppLocale.zh,
      'zh_Hant': AppLocale.zhHant,
      'pt': AppLocale.pt,
      'fr': AppLocale.fr,
      'de': AppLocale.de,
      'it': AppLocale.it,
      'id': AppLocale.id,
      'ja': AppLocale.ja,
      'ko': AppLocale.ko,
    };

Map<String, Map<String, String>> get _catalogs => <String, Map<String, String>>{
  for (final entry in LibraryFeatureLocale.catalog.entries)
    'hub ${entry.key}': entry.value,
  for (final entry in LibrarySourcesLocale.values.entries)
    'sources ${entry.key}': entry.value,
  for (final entry in LibraryLocalLocale.values.entries)
    'local ${entry.key}': entry.value,
};

Iterable<MapEntry<String, String>> _valuesOf(String locale) sync* {
  for (final catalog in _catalogs.entries) {
    if (!catalog.key.endsWith(' $locale')) continue;
    for (final entry in catalog.value.entries) {
      yield MapEntry<String, String>(
        '${catalog.key}.${entry.key}',
        entry.value,
      );
    }
  }
}

void main() {
  test('the twelve locales of AppLocale are the Library locales', () {
    expect(_appLocale.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
  });

  test(
    'Portuguese Library texts are Brazilian Portuguese, like AppLocale pt',
    () {
      // European Portuguese forms found in the Build 437 hub texts.
      final european = RegExp(
        r'\ba (carregar|pesquisar|atualizar|transferir)\b|ficheiro|utilizador|'
        r'ecrã|secção|guardad|\bgerir\b|ligação|apresentad|demasiad|respetiv|'
        r'em baixo|contactar|transferi',
        caseSensitive: false,
      );
      final found = <String>[
        for (final entry in _valuesOf('pt'))
          if (european.hasMatch(entry.value)) '${entry.key}: ${entry.value}',
      ];
      expect(found, isEmpty);
    },
  );

  test('English Library texts use one spelling (catalog, favorites)', () {
    final british = RegExp(
      r'catalogue|favourite|cancelled',
      caseSensitive: false,
    );
    final found = <String>[
      for (final entry in _valuesOf('en'))
        if (british.hasMatch(entry.value)) '${entry.key}: ${entry.value}',
    ];
    expect(found, isEmpty);
  });

  test('menu paths name the Library as the tab bar does', () {
    for (final locale in _appLocale.keys) {
      final app = _appLocale[locale]!;
      final library = app[AppLocale.library] as String;
      final sources = LibraryFeatureLocale.catalog[locale]!['sourcesSection']!;
      final sourcesTexts = LibrarySourcesLocale.values[locale]!;
      expect(
        sourcesTexts['sourceDisabled'],
        contains('$library › $sources'),
        reason: '$locale: the path to reactivate a source',
      );
      expect(
        sourcesTexts['kindLocal'],
        app[AppLocale.libraryLocal],
        reason: '$locale: the local library has the name of its hub tile',
      );
    }
  });

  test('zh, zh_Hant and it never use another word for the Library', () {
    const other = <String, String>{
      'zh': '书库',
      'zh_Hant': '書庫',
      'it': 'libreria',
    };
    for (final entry in other.entries) {
      final found = <String>[
        for (final value in _valuesOf(entry.key))
          if (value.value.toLowerCase().contains(entry.value)) value.key,
      ];
      expect(found, isEmpty, reason: entry.key);
    }
  });
}
