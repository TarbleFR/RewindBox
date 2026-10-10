// Coverage of the Library catalog (library_feature_locale.dart): the twelve
// supported locales share one key set, every value is translated (not
// empty), placeholders are identical per key and Traditional Chinese is
// selected for zh_Hant / TW / HK / MO.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_feature_locale.dart';

const List<String> _locales = <String>[
  'en',
  'es',
  'ru',
  'zh',
  'zh_Hant',
  'pt',
  'fr',
  'de',
  'it',
  'id',
  'ja',
  'ko',
];

/// Keys added for the Build 437 hub, feed, search and favourites.
const List<String> _hubKeys = <String>[
  'sourcesSection',
  'sourcesSectionSubtitle',
  'favoritesSection',
  'favoritesSectionSubtitle',
  'refreshSources',
  'updatingSources',
  'sourcesUnavailable',
  'unavailableSourcesTitle',
  'unavailableSourcesHelp',
  'technicalDetails',
  'savedCopyShown',
  'knownStateVerified',
  'issueChallenge',
  'issueOffline',
  'issueTimeout',
  'issueServerUnavailable',
  'issueNotFound',
  'issueHttpStatus',
  'issueTooLarge',
  'issueInvalidResponse',
  'issueParseFailed',
  'issueSiteChanged',
  'issueParked',
  'issueUnsupported',
  'issueUnknown',
  'emptyNoSourceTitle',
  'emptyNoSourceBody',
  'addCatalogue',
  'importYourFiles',
  'emptyAllFailedTitle',
  'loadingCatalogues',
  'searchMinChars',
  'noResults',
  'searchSourceSearching',
  'searchSourceResults',
  'searchSourceFailed',
  'searchSourceSkipped',
  'sourceHiddenBySafeMode',
  'openFailed',
  'readFailed',
  'downloadFailedPlain',
  'details',
  'continueReading',
  'favoritesTitle',
  'noFavorites',
  'nothingInProgress',
  'sourceInactive',
  'sourceInactiveHelp',
  'removeFavorite',
  'removeFavoriteQuestion',
  'removeFavoriteBody',
  'favoriteRemoved',
  'progressPercent',
  'bookMissing',
  'localBookLabel',
];

Set<String> _placeholders(String value) =>
    RegExp(r'\{(\w+)\}').allMatches(value).map((m) => m.group(1)!).toSet();

void main() {
  final catalog = LibraryFeatureLocale.catalog;

  test('the catalog has exactly the twelve supported locales', () {
    expect(catalog.keys.toSet(), _locales.toSet());
  });

  test('every locale has the same keys, including the hub keys', () {
    final english = catalog['en']!.keys.toSet();
    expect(english, containsAll(_hubKeys));
    for (final locale in _locales) {
      expect(
        catalog[locale]!.keys.toSet(),
        english,
        reason: '$locale key set differs from en',
      );
    }
  });

  test('no value is empty and hub keys are really translated', () {
    for (final locale in _locales) {
      for (final entry in catalog[locale]!.entries) {
        expect(
          entry.value.trim(),
          isNotEmpty,
          reason: '$locale.${entry.key} is empty',
        );
      }
    }
    // A translation identical to English in most locales would be an
    // untranslated copy (product names and short words excepted).
    const sharedWords = <String>{'sourcesSection', 'details', 'sourceInactive'};
    for (final key in _hubKeys.where((key) => !sharedWords.contains(key))) {
      final english = catalog['en']![key];
      final copies = _locales
          .where((locale) => locale != 'en' && catalog[locale]![key] == english)
          .toList();
      expect(copies, isEmpty, reason: '$key copied from English in $copies');
    }
  });

  test('placeholders are identical in every locale', () {
    for (final key in catalog['en']!.keys) {
      final expected = _placeholders(catalog['en']![key]!);
      for (final locale in _locales) {
        expect(
          _placeholders(catalog[locale]![key]!),
          expected,
          reason: '$locale.$key placeholders',
        );
      }
    }
  });

  test('Traditional Chinese is selected for Hant, TW, HK and MO', () {
    expect(
      LibraryFeatureLocale.localeCodeFor(
        const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      ),
      'zh_Hant',
    );
    for (final country in ['TW', 'HK', 'MO']) {
      expect(
        LibraryFeatureLocale.localeCodeFor(Locale('zh', country)),
        'zh_Hant',
        reason: country,
      );
    }
    expect(LibraryFeatureLocale.localeCodeFor(const Locale('zh')), 'zh');
    expect(LibraryFeatureLocale.localeCodeFor(const Locale('zh', 'CN')), 'zh');
    expect(LibraryFeatureLocale.localeCodeFor(const Locale('fr', 'CA')), 'fr');
  });

  testWidgets('text() and format() resolve through the locale', (tester) async {
    late BuildContext captured;
    await tester.pumpWidget(
      Localizations(
        locale: const Locale('zh', 'TW'),
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
      LibraryFeatureLocale.text(captured, 'favoritesTitle'),
      catalog['zh_Hant']!['favoritesTitle'],
    );
    expect(
      LibraryFeatureLocale.format(captured, 'sourcesUnavailable', {'count': 3}),
      '3 個來源無法使用',
    );
  });
}
