// Safe-mode content filter and per-entry precomputation. Regression for
// Build 436: the old filter regex-matched jsonEncode(provider), which always
// contains the key "nsfw", and hid 100% of the Aidoku titles.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_http.dart';

import 'library_feed_test_fakes.dart';

void main() {
  group('LibraryContentFilter', () {
    test('a source declaring nsfw 0 is visible and its titles too', () {
      final source = aidokuTestAddon('fr.safe', contentRating: 0, nsfw: 0);
      expect(source.manifest['provider'], containsPair('nsfw', 0));
      expect(LibraryContentFilter.sourceHiddenInSafeMode(source), isFalse);
      final item = testItem(
        'solo',
        title: 'Solo Leveling',
        raw: {
          'nsfw': 0,
          'contentRating': 0,
          'categories': ['Action', 'Fantasy'],
          'imageHeaders': {'Referer': 'https://example.com/'},
        },
      );
      expect(LibraryContentFilter.itemIsAdult(item), isFalse);
    });

    test('a primarily NSFW source (rating 2) is hidden as a whole', () {
      expect(
        LibraryContentFilter.sourceHiddenInSafeMode(
          aidokuTestAddon('fr.adult', contentRating: 2),
        ),
        isTrue,
      );
      expect(
        LibraryContentFilter.sourceHiddenInSafeMode(
          aidokuTestAddon('fr.mixed', contentRating: 1),
        ),
        isFalse,
        reason: 'rating 1 sources are filtered title by title',
      );
    });

    test('explicit titles are hidden individually', () {
      expect(
        LibraryContentFilter.itemIsAdult(
          testItem('a', raw: {'explicitContent': true}),
        ),
        isTrue,
      );
      expect(
        LibraryContentFilter.itemIsAdult(
          testItem('b', raw: {'contentRating': 2}),
        ),
        isTrue,
      );
      expect(
        LibraryContentFilter.itemIsAdult(
          testItem(
            'c',
            raw: {
              'categories': ['Romance', 'Hentai'],
            },
          ),
        ),
        isTrue,
      );
      expect(
        LibraryContentFilter.itemIsAdult(
          testItem(
            'd',
            raw: {
              'genres': ['Mature'],
            },
          ),
        ),
        isTrue,
      );
      expect(
        LibraryContentFilter.itemIsAdult(testItem('e', raw: {'isAdult': true})),
        isTrue,
      );
      expect(
        LibraryContentFilter.itemIsAdult(
          testItem('f', raw: {'ageRating': 'R18'}),
        ),
        isTrue,
      );
      expect(
        LibraryContentFilter.itemIsAdult(testItem('g', title: 'My Doujinshi')),
        isTrue,
      );
    });

    test('textual content ratings of imported providers are honoured', () {
      bool adult(Map<String, dynamic> raw) =>
          LibraryContentFilter.itemIsAdult(testItem('x', raw: raw));
      expect(adult({'contentRating': 'erotica'}), isTrue);
      expect(adult({'contentRating': 'pornographic'}), isTrue);
      expect(
        adult({
          'attributes': {'contentRating': 'pornographic'},
        }),
        isTrue,
      );
      expect(
        adult({
          'attributes': {'contentRating': 2},
        }),
        isTrue,
      );
      expect(adult({'contentRating': 'suggestive'}), isFalse);
      expect(
        adult({
          'attributes': {'contentRating': 'safe'},
        }),
        isFalse,
      );
    });

    test('a suggestive title of a rating 1 source stays visible', () {
      final item = testItem(
        'h',
        title: 'Spy Family',
        raw: {
          'contentRating': 1,
          'categories': ['Comedy'],
        },
      );
      expect(LibraryContentFilter.itemIsAdult(item), isFalse);
    });

    test('key names never trigger the filter, only values', () {
      final item = testItem(
        'i',
        raw: {
          'nsfw': false,
          'adult': 0,
          'explicitContent': false,
          'tags': [
            {'name': 'Drama', 'nsfw': false, 'adultContent': 0},
          ],
        },
      );
      expect(LibraryContentFilter.itemIsAdult(item), isFalse);
      final tagged = testItem(
        'j',
        raw: {
          'tags': [
            {'name': 'Hentai'},
          ],
        },
      );
      expect(LibraryContentFilter.itemIsAdult(tagged), isTrue);
    });

    test('words inside other words do not match', () {
      expect(
        LibraryContentFilter.itemIsAdult(
          testItem('k', title: 'Immature Essex Adulthood Sextant'),
        ),
        isFalse,
      );
    });
  });

  group('LibraryFeedEntry', () {
    test('precomputes identity, folded title, languages and headers', () {
      final source = aidokuTestAddon('fr.a');
      final entry = LibraryFeedEntry.create(
        sourceKey: source.id,
        kind: LibraryFeedSourceKind.aidoku,
        addon: source,
        item: testItem(
          'manga-1',
          title: 'Éclat de Lune',
          raw: {
            'language': 'fr',
            'imageHeaders': {'Referer': 'https://example.com/', 'Empty': ''},
          },
        ),
      );
      expect(entry.identity, 'aidoku.fr.a|manga-1');
      expect(entry.foldedTitle, 'eclat de lune');
      expect(entry.firstLetter, 'E');
      expect(entry.languages, {'fr'});
      expect(entry.languageBadge, 'FR');
      expect(entry.imageHeaders, {'Referer': 'https://example.com/'});
      expect(entry.adult, isFalse);
    });

    test('falls back to the single language declared by the source', () {
      final source = aidokuTestAddon('fr.a', languages: ['en']);
      final entry = LibraryFeedEntry.create(
        sourceKey: source.id,
        kind: LibraryFeedSourceKind.aidoku,
        addon: source,
        item: testItem('x', title: '42 Days'),
      );
      expect(entry.languages, {'en'});
      expect(entry.firstLetter, '4');
    });
  });

  group('LibraryFeedFailure', () {
    final at = DateTime.utc(2026, 10, 11);

    test('maps network kinds and drops cancellations', () {
      expect(
        LibraryFeedFailure.fromError(
          const LibraryNetworkException(LibraryNetworkErrorKind.cancelled),
          at,
        ),
        isNull,
      );
      final failure = LibraryFeedFailure.fromError(
        LibraryNetworkException(
          LibraryNetworkErrorKind.challenge,
          uri: Uri.parse('https://manga-scantrad.io/'),
          statusCode: 403,
          detail: 'cf-mitigated',
        ),
        at,
      )!;
      expect(failure.issue, LibraryFeedIssue.challenge);
      expect(failure.isBlocking, isTrue);
      expect(
        failure.technical,
        'challenge · manga-scantrad.io · HTTP 403 · cf-mitigated',
      );
    });

    test('maps source and addon exceptions through their network error', () {
      final wrapped = LibraryFeedFailure.fromError(
        LibrarySourceException(
          LibrarySourceErrorKind.network,
          networkError: const LibraryNetworkException(
            LibraryNetworkErrorKind.serverUnavailable,
            statusCode: 504,
          ),
        ),
        at,
      )!;
      expect(wrapped.issue, LibraryFeedIssue.serverUnavailable);
      final parse = LibraryFeedFailure.fromError(
        LibrarySourceException(LibrarySourceErrorKind.parseFailed),
        at,
      )!;
      expect(parse.issue, LibraryFeedIssue.parseFailed);
      final addon = LibraryFeedFailure.fromError(
        const LibraryAddonException(
          'catalog.example.com returned HTTP 404.',
          network: LibraryNetworkException(
            LibraryNetworkErrorKind.notFound,
            statusCode: 404,
          ),
        ),
        at,
      )!;
      expect(addon.issue, LibraryFeedIssue.notFound);
      expect(
        LibraryFeedFailure.fromError(TimeoutException('slow'), at)!.issue,
        LibraryFeedIssue.timeout,
      );
      expect(
        LibraryFeedFailure.fromError(StateError('boom'), at)!.issue,
        LibraryFeedIssue.unknown,
      );
    });

    test('verified states of the registry become known failures', () {
      final known = LibraryFeedFailure.fromKnownState(
        LibrarySourceSupportRegistry.forSourceId('fr.mangascantrad'),
      )!;
      expect(known.issue, LibraryFeedIssue.challenge);
      expect(known.known, isTrue);
      expect(
        LibraryCatalogFeed.isKnownBlocked(
          LibrarySourceSupportRegistry.forSourceId('fr.mangascantrad'),
        ),
        isTrue,
      );
      expect(
        LibraryCatalogFeed.isKnownBlocked(
          LibrarySourceSupportRegistry.forSourceId('fr.sushiscan'),
        ),
        isFalse,
      );
    });
  });
}
