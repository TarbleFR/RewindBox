// Progressive title loading (LibraryAidokuNativeService.watchManga) on the
// minimized LelscanFR / SushiScan fixtures captured on 2026-10-10, and the
// favourite snapshot used to reopen a title offline.
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/library_manga_details_screen.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_aidoku_test_support.dart';

const String _lelscan = 'https://www.lelscanfr.com';

LibraryCatalogItem _item(String id) => LibraryCatalogItem(
  id: id,
  title: id,
  mediaType: LibraryMediaType.manga,
  subtitle: '',
  description: '',
  coverUrl: null,
  content: null,
  contentUrl: null,
  pageUrls: const <String>[],
  raw: const <String, dynamic>{},
);

void _onePiece(FakeLibraryFetcher fake, {Set<int> failing = const <int>{}}) {
  fake.get(
    '$_lelscan/manga/one-piece',
    fixture: 'lelscan_details_one_piece.html',
  );
  for (var page = 2; page <= 6; page++) {
    final url = '$_lelscan/manga/one-piece?page=$page';
    if (failing.contains(page)) {
      fake.get(
        url,
        error: LibraryNetworkException(
          LibraryNetworkErrorKind.timeout,
          uri: Uri.parse(url),
        ),
      );
    } else {
      fake.get(
        url,
        fixture: 'lelscan_chapters_one_piece_p$page.html',
        // Later pages answer later, like the live site.
        delay: Duration(milliseconds: 5 * page),
      );
    }
  }
}

List<String> _ids(LibraryMangaDetails details) =>
    details.chapters.map((chapter) => chapter.id).toList();

void main() {
  final lelscan = aidokuAddon('fr.lelscanfr');
  final sushiscan = aidokuAddon('fr.sushiscan');

  test('LelscanFR emits details with the first list page, then a growing list, '
      'then the full result', () async {
    final fake = FakeLibraryFetcher();
    _onePiece(fake);
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final emissions = await service
        .watchManga(lelscan, _item('one-piece'))
        .toList();

    expect(emissions.length, greaterThanOrEqualTo(3));
    final first = emissions.first;
    expect(first.chaptersComplete, isFalse);
    expect(first.item.title, 'One Piece');
    expect(first.author, 'Eiichirō Oda');
    expect(first.chapters, isNotEmpty);
    expect(first.chapters.first.number, 1195, reason: 'newest first');

    for (var index = 1; index < emissions.length; index++) {
      final previous = _ids(emissions[index - 1]);
      final current = _ids(emissions[index]);
      expect(current.length, greaterThan(previous.length));
      expect(
        current.take(previous.length),
        previous,
        reason: 'the list only grows at its end',
      );
    }
    final last = emissions.last;
    expect(last.chaptersComplete, isTrue);
    expect(last.chapters, hasLength(14));
    expect(
      emissions
          .sublist(0, emissions.length - 1)
          .every((details) => !details.chaptersComplete),
      isTrue,
    );

    final again = LibraryAidokuNativeService(fetcher: fake.call);
    final loaded = await again.loadManga(lelscan, _item('one-piece'));
    expect(_ids(last), _ids(loaded), reason: 'same result as loadManga');
  });

  test('a failed list page ends the stream with an incomplete list', () async {
    final fake = FakeLibraryFetcher();
    _onePiece(fake, failing: const <int>{4});
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final emissions = await service
        .watchManga(lelscan, _item('one-piece'))
        .toList();

    expect(emissions.last.chaptersComplete, isFalse);
    expect(emissions.last.chapters.length, lessThan(14));
    expect(emissions.last.chapters.length, greaterThan(0));
  });

  test('sources with the list on the details page emit once', () async {
    final fake = FakeLibraryFetcher()
      ..get(
        'https://sushiscan.net/catalogue/kagurabachi/',
        fixture: 'sushiscan_details_kagurabachi.html',
      );
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final emissions = await service
        .watchManga(sushiscan, _item('kagurabachi'))
        .toList();

    expect(emissions, hasLength(1));
    expect(emissions.single.chaptersComplete, isTrue);
    expect(emissions.single.chapters.map((c) => c.number), <double>[
      119,
      112.5,
      1,
    ]);
  });

  test('a complete load is reused by cacheFirst without a request', () async {
    final fake = FakeLibraryFetcher();
    _onePiece(fake);
    final service = LibraryAidokuNativeService(fetcher: fake.call);
    await service.watchManga(lelscan, _item('one-piece')).toList();
    final requests = fake.requests.length;

    final again = await service
        .watchManga(lelscan, _item('one-piece'))
        .toList();

    expect(again, hasLength(1));
    expect(again.single.chaptersComplete, isTrue);
    expect(fake.requests, hasLength(requests));

    final refreshed = await service
        .watchManga(lelscan, _item('one-piece'), mode: LibraryFetchMode.refresh)
        .toList();
    expect(refreshed.last.chapters, hasLength(14));
    expect(fake.requests.length, greaterThan(requests));
  });

  test('a failure is one error event, then the stream closes', () async {
    final fake = FakeLibraryFetcher()
      ..get(
        '$_lelscan/manga/gone',
        status: 403,
        headers: const <String, String>{'cf-mitigated': 'challenge'},
      );
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final errors = <Object>[];
    final values = <LibraryMangaDetails>[];
    final done = Completer<void>();
    service
        .watchManga(lelscan, _item('gone'))
        .listen(values.add, onError: errors.add, onDone: done.complete);
    await done.future;

    expect(values, isEmpty);
    expect(errors, hasLength(1));
    expect(
      (errors.single as LibraryNetworkException).kind,
      LibraryNetworkErrorKind.challenge,
    );
  });

  test('cancelling the subscription stops the remaining list pages', () async {
    final fake = FakeLibraryFetcher();
    _onePiece(fake);
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final first = Completer<void>();
    late StreamSubscription<LibraryMangaDetails> subscription;
    subscription = service.watchManga(lelscan, _item('one-piece')).listen((_) {
      if (!first.isCompleted) first.complete();
    });
    await first.future;
    await subscription.cancel();
    await Future<void>.delayed(const Duration(milliseconds: 80));

    // Page 1 plus the two pages already in flight; pages 4-6 never start.
    expect(fake.requests.length, lessThanOrEqualTo(3));
  });

  test('an external cancel token also stops the load', () async {
    final fake = FakeLibraryFetcher();
    _onePiece(fake);
    final service = LibraryAidokuNativeService(fetcher: fake.call);
    final cancel = LibraryCancelToken();

    final values = <LibraryMangaDetails>[];
    final done = Completer<void>();
    service
        .watchManga(lelscan, _item('one-piece'), cancel: cancel)
        .listen(
          (details) {
            values.add(details);
            cancel.cancel();
          },
          onError: (Object _) {},
          onDone: done.complete,
        );
    await done.future;

    expect(values, hasLength(1), reason: 'nothing is emitted after cancel');
    expect(fake.requests.length, lessThanOrEqualTo(3));
  });

  test('cachedMangaForSource reads only the cache', () async {
    final fake = FakeLibraryFetcher()
      ..get(
        'https://sushiscan.net/catalogue/kagurabachi/',
        fixture: 'sushiscan_details_kagurabachi.html',
        cached: true,
      )
      // Served by the site but not cached: never fetched in cache-only mode.
      ..get(
        'https://sushiscan.net/catalogue/missing/',
        fixture: 'sushiscan_details_kagurabachi.html',
      );
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final cached = await service.cachedMangaForSource(
      'fr.sushiscan',
      _item('kagurabachi'),
    );
    expect(cached, isNotNull);
    expect(cached!.chapters, hasLength(3));
    expect(fake.modes, everyElement(LibraryFetchMode.cacheOnly));

    expect(
      await service.cachedMangaForSource('fr.sushiscan', _item('missing')),
      isNull,
      reason: 'a cache miss is null, not an error',
    );
    expect(
      await service.cachedMangaForSource('fr.astralmanga', _item('x')),
      isNull,
      reason: 'no adapter',
    );
  });

  test('a favourite snapshot reopens the title without the network', () {
    final item = LibraryCatalogItem(
      id: 'one-piece',
      title: 'One Piece',
      mediaType: LibraryMediaType.manga,
      subtitle: 'Eiichirō Oda',
      description: 'x' * 900,
      coverUrl: 'https://www.lelscanfr.com/storage/covers/op.webp',
      content: null,
      contentUrl: null,
      pageUrls: const <String>[],
      raw: <String, dynamic>{
        'aidokuSourceId': 'fr.lelscanfr',
        'mangaId': 'one-piece',
        'mangaUrl': '$_lelscan/manga/one-piece',
        'imageHeaders': <String, String>{'Referer': '$_lelscan/'},
        'contentRating': 0,
      },
    );
    final favorite = LibraryFavorite(
      key: LibraryMangaKeys.online('fr.lelscanfr', 'one-piece'),
      sourceId: 'fr.lelscanfr',
      mangaId: 'one-piece',
      title: 'One Piece',
      snapshot: LibraryMangaDetailsScreen.favoriteSnapshot(item),
    );
    // Survives the JSON round trip of the reading store.
    final stored = LibraryFavorite.fromJson(favorite.toJson())!;
    final reopened = LibraryMangaDetailsScreen.itemFromFavorite(stored);

    expect(reopened.id, 'one-piece');
    expect(reopened.title, 'One Piece');
    expect(reopened.coverUrl, item.coverUrl);
    expect(reopened.mediaType, LibraryMediaType.manga);
    expect(reopened.description.length, 600, reason: 'snapshot stays small');
    expect(reopened.raw['aidokuSourceId'], 'fr.lelscanfr');
    expect(reopened.raw['mangaUrl'], '$_lelscan/manga/one-piece');
    expect((reopened.raw['imageHeaders'] as Map)['Referer'], '$_lelscan/');

    final bare = LibraryMangaDetailsScreen.itemFromFavorite(
      LibraryFavorite(
        key: 'online:fr.sushiscan:kagurabachi',
        sourceId: 'fr.sushiscan',
        mangaId: 'kagurabachi',
        title: 'Kagurabachi',
        mangaUrl: 'https://sushiscan.net/catalogue/kagurabachi/',
      ),
    );
    expect(bare.title, 'Kagurabachi');
    expect(bare.raw['aidokuSourceId'], 'fr.sushiscan');
    expect(
      bare.raw['mangaUrl'],
      'https://sushiscan.net/catalogue/kagurabachi/',
    );
  });
}
