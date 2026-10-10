// Coverage of the Library sources / catalogue preview / title page catalog:
// the twelve NeoStation languages, same keys everywhere, same placeholders,
// no empty or untranslated (English) value, Traditional Chinese selection,
// and every typed error the screens translate has a key.
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_sources_locale.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_source_catalog_service.dart';

void main() {
  final placeholders = RegExp(r'\{\w+\}');
  final english = LibrarySourcesLocale.values['en']!;

  // Values that are genuinely the same words in that language: French
  // "Catalogue(s)", "source(s)", "Version", "Page"; German "Version";
  // "Volume" as used for manga volumes in Portuguese, Italian and Indonesian.
  const identical = <String>{
    'fr:catalogs',
    'fr:previewTitle',
    'fr:sourceCount',
    'fr:version',
    'fr:chapterPageOnly',
    'de:version',
    'pt:volumeNumber',
    'it:volumeNumber',
    'id:volumeNumber',
  };

  test('covers exactly the twelve NeoStation languages', () {
    expect(
      LibrarySourcesLocale.values.keys.toSet(),
      AppLocale.supportedLanguages.keys.toSet(),
    );
    expect(LibrarySourcesLocale.values.keys, hasLength(12));
  });

  for (final entry in LibrarySourcesLocale.values.entries) {
    test('${entry.key}: same keys, same placeholders, nothing empty', () {
      expect(entry.value.keys.toSet(), english.keys.toSet());
      for (final message in english.entries) {
        final translated = entry.value[message.key]!;
        expect(translated.trim(), isNotEmpty, reason: message.key);
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

  test('script or region selects Traditional Chinese', () {
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
      const Locale('zh_Hant'),
    ]) {
      expect(LibrarySourcesLocale.localeKey(locale), 'zh_Hant');
      expect(
        LibrarySourcesLocale.forLocale(locale, 'deactivate'),
        LibrarySourcesLocale.values['zh_Hant']!['deactivate'],
      );
    }
    expect(LibrarySourcesLocale.localeKey(const Locale('zh')), 'zh');
    expect(LibrarySourcesLocale.localeKey(const Locale('zh', 'CN')), 'zh');
    expect(LibrarySourcesLocale.localeKey(const Locale('nl')), 'en');
  });

  test('format replaces every placeholder', () {
    expect(
      LibrarySourcesLocale.formatLocale(
        const Locale('fr'),
        'continueChapter',
        <String, Object?>{'chapter': 12, 'page': 3},
      ),
      'Continuer – chapitre 12, page 3',
    );
  });

  test('every typed error, reason, state and step maps to a key', () {
    for (final kind in LibraryNetworkErrorKind.values) {
      expect(english, contains(LibrarySourcesLocale.networkKey(kind)));
    }
    for (final kind in LibrarySourceErrorKind.values) {
      expect(english, contains(LibrarySourcesLocale.sourceErrorKey(kind)));
    }
    for (final kind in LibraryCatalogErrorKind.values) {
      expect(english, contains(LibrarySourcesLocale.catalogErrorKey(kind)));
    }
    for (final reason in LibrarySourceUnsupportedReason.values) {
      expect(
        english,
        contains(LibrarySourcesLocale.unsupportedReasonKey(reason)),
      );
    }
    for (final state in LibrarySourceKnownState.values) {
      expect(english, contains(LibrarySourcesLocale.knownStateKey(state)));
    }
    for (final step in LibrarySourceHealthStep.values) {
      expect(english, contains(LibrarySourcesLocale.healthStepKey(step)));
    }
  });

  test('errors are explained by kind, the raw detail kept apart', () {
    const challenge = LibraryNetworkException(
      LibraryNetworkErrorKind.challenge,
      statusCode: 403,
    );
    expect(LibrarySourcesLocale.errorKey(challenge), 'netChallenge');
    expect(english['netChallenge'], contains('browser verification'));
    expect(LibrarySourcesLocale.technicalDetail(challenge), contains('403'));

    final wrapped = LibrarySourceException(
      LibrarySourceErrorKind.network,
      networkError: const LibraryNetworkException(
        LibraryNetworkErrorKind.serverUnavailable,
      ),
    );
    expect(LibrarySourcesLocale.errorKey(wrapped), 'netServerUnavailable');
    expect(
      LibrarySourcesLocale.errorKey(
        LibrarySourceException(LibrarySourceErrorKind.protectedChapter),
      ),
      'srcProtectedChapter',
    );
    expect(
      LibrarySourcesLocale.errorKey(
        const LibraryCatalogException(
          LibraryCatalogErrorKind.network,
          network: LibraryNetworkException(LibraryNetworkErrorKind.timeout),
        ),
      ),
      'netTimeout',
    );
    expect(
      LibrarySourcesLocale.errorKey(
        const LibraryCatalogException(LibraryCatalogErrorKind.notHttps),
      ),
      'catNotHttps',
    );
    expect(LibrarySourcesLocale.errorKey(StateError('x')), 'errorUnknown');
  });
}
