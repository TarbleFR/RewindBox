// LelscanFR engine. Fixtures are minimized copies of pages captured on
// 2026-10-10 (chapter list pages keep 2-3 rows each).
import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_aidoku_test_support.dart';

const String _base = 'https://www.lelscanfr.com';

LibraryCatalogItem _item(String id, {String url = ''}) => LibraryCatalogItem(
  id: id,
  title: id,
  mediaType: LibraryMediaType.manga,
  subtitle: '',
  description: '',
  coverUrl: null,
  content: null,
  contentUrl: null,
  pageUrls: const <String>[],
  raw: <String, dynamic>{'mangaUrl': url},
);

void _onePiece(FakeLibraryFetcher fake, {Set<int> failing = const <int>{}}) {
  fake.get('$_base/manga/one-piece', fixture: 'lelscan_details_one_piece.html');
  for (var page = 2; page <= 6; page++) {
    if (failing.contains(page)) {
      fake.get(
        '$_base/manga/one-piece?page=$page',
        error: LibraryNetworkException(
          LibraryNetworkErrorKind.timeout,
          uri: Uri.parse('$_base/manga/one-piece?page=$page'),
        ),
      );
    } else {
      fake.get(
        '$_base/manga/one-piece?page=$page',
        fixture: 'lelscan_chapters_one_piece_p$page.html',
        delay: const Duration(milliseconds: 5),
      );
    }
  }
}

void main() {
  final addon = aidokuAddon('fr.lelscanfr');

  test(
    'newest listing reads full titles from alt and sibling genres',
    () async {
      final fake = FakeLibraryFetcher()
        ..get('$_base/manga?page=1', fixture: 'lelscan_catalog_p1.html')
        ..get('$_base/manga?page=21', fixture: 'lelscan_catalog_p21.html');
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final page = await service.loadCatalogPage(
        addon,
        listing: LibraryMangaListing.newest,
      );

      expect(page.items.map((item) => item.id), <String>[
        'maria-no-danzai',
        'nezumi-no-hatsukoi',
        'tomoshibi-no-oteru',
        'unnamed-memory',
        'yumenashi-sensei-no-shinroshidou',
      ]);
      expect(
        page.items.last.title,
        'Yumenashi-Sensei No Shinroshidou',
        reason: 'the h2 is truncated with "..."; img[alt] is complete',
      );
      final maria = page.items.first;
      expect(maria.raw['mangaUrl'], '$_base/manga/maria-no-danzai');
      expect(maria.coverUrl, '$_base/storage/covers/6886be30dad35.webp');
      expect(maria.raw['categories'], <String>[
        'Seinen',
        'Drame',
        'Mature',
        'Vie Scolaire',
        'Tragédie',
      ]);
      expect(maria.raw['contentRating'], LibraryContentRating.explicit);
      expect(maria.raw['explicitContent'], isTrue);
      expect(page.hasMore, isTrue, reason: 'Page 1 of 21');

      final last = await service.loadCatalogPage(
        addon,
        page: 21,
        listing: LibraryMangaListing.newest,
      );
      expect(last.hasMore, isFalse, reason: 'Page 21 of 21');
    },
  );

  test(
    'latest reads only the "Chapitres récents" section of the home page',
    () async {
      final fake = FakeLibraryFetcher()
        ..get('$_base/', fixture: 'lelscan_home_p1.html');
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final latest = await service.loadCatalogPage(addon);
      final popular = await service.loadCatalogPage(
        addon,
        listing: LibraryMangaListing.popular,
      );

      expect(latest.listing, LibraryMangaListing.latest);
      // "Ajouts récents" (maria-no-danzai, nezumi-no-hatsukoi) and the
      // popular carousel are other sections of the same page.
      expect(latest.items.map((item) => item.id), <String>[
        'one-piece',
        'sakamoto-days',
        'hunter-x-hunter',
      ]);
      expect(latest.hasMore, isTrue, reason: 'Page 1 of 20');
      expect(popular.items.map((item) => item.id), <String>[
        'one-piece',
        'kingdom',
      ]);
      expect(popular.hasMore, isFalse);

      final popularPage2 = await service.loadCatalogPage(
        addon,
        page: 2,
        listing: LibraryMangaListing.popular,
      );
      expect(popularPage2.items, isEmpty);
      expect(fake.requests, hasLength(2), reason: 'no request for page 2');
    },
  );

  test('search without pagination block has no next page', () async {
    final fake = FakeLibraryFetcher()
      ..get(
        '$_base/manga?page=1&title=one+piece',
        fixture: 'lelscan_search_one_piece.html',
      );
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final page = await service.loadCatalogPage(addon, query: 'one piece');

    expect(page.items.single.title, 'One Piece');
    expect(page.hasMore, isFalse);
  });

  test(
    'details reuse page 1 and fetch the other chapter pages two at a time',
    () async {
      final fake = FakeLibraryFetcher();
      _onePiece(fake);
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final details = await service.loadManga(
        addon,
        // A stored apex URL is rewritten to the canonical www host.
        _item('one-piece', url: 'https://lelscanfr.com/manga/one-piece'),
      );

      expect(fake.requestsTo('$_base/manga/one-piece'), hasLength(1));
      expect(fake.requests, hasLength(6));
      expect(fake.requests.first.timeout, const Duration(seconds: 30));
      expect(details.item.title, 'One Piece');
      expect(details.author, 'Eiichirō Oda');
      expect(details.artist, 'Eiichirō Oda');
      expect(details.status, LibraryMangaStatus.ongoing);
      expect(details.typeLabel, 'Manga');
      expect(details.readingMode, LibraryReadingMode.rightToLeft);
      expect(details.genres, hasLength(18));
      expect(details.alternativeTitles, isNotEmpty);
      expect(details.item.description, isNotEmpty);
      expect(details.chaptersComplete, isTrue);

      final chapters = details.chapters;
      expect(chapters, hasLength(14));
      expect(chapters.first.number, 1195);
      expect(chapters.first.title, 'Chapitre 1195');
      expect(chapters.first.id, '1195');
      expect(chapters.first.date, fake.now.subtract(const Duration(days: 2)));
      expect(chapters.last.number, 701);
      expect(chapters.map((c) => c.id), contains('1000.5'));
      expect(chapters.firstWhere((c) => c.id == '1000.5').number, 1000.5);
      final numbers = chapters.map((c) => c.number!).toList();
      final sorted = [...numbers]..sort((a, b) => b.compareTo(a));
      expect(numbers, sorted, reason: 'newest first across pages');
    },
  );

  test('a failed chapter list page marks the list incomplete', () async {
    final fake = FakeLibraryFetcher();
    _onePiece(fake, failing: const <int>{4});
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final details = await service.loadManga(addon, _item('one-piece'));

    expect(details.chaptersComplete, isFalse);
    expect(details.chapters, hasLength(12));

    // Incomplete results are not reused: the next call asks again.
    await service.loadManga(addon, _item('one-piece'));
    expect(fake.requestsTo('$_base/manga/one-piece'), hasLength(2));
  });

  test('a cancelled load stops instead of returning a partial list', () async {
    final fake = FakeLibraryFetcher();
    _onePiece(fake);
    final service = LibraryAidokuNativeService(fetcher: fake.call);
    final cancel = LibraryCancelToken();

    final future = service.loadManga(addon, _item('one-piece'), cancel: cancel);
    scheduleMicrotask(cancel.cancel);

    await expectLater(
      future,
      throwsA(
        isA<LibraryNetworkException>().having(
          (error) => error.kind,
          'kind',
          LibraryNetworkErrorKind.cancelled,
        ),
      ),
    );
  });

  test('a title without pagination costs one request', () async {
    final fake = FakeLibraryFetcher()
      ..get(
        '$_base/manga/maria-no-danzai',
        fixture: 'lelscan_details_maria_no_danzai.html',
      );
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final details = await service.loadManga(addon, _item('maria-no-danzai'));

    expect(fake.requests, hasLength(1));
    expect(details.chapters.map((c) => c.number), <double>[32, 31, 30]);
    expect(
      details.chapters.first.date,
      fake.now.subtract(const Duration(days: 365)),
    );
    expect(details.contentRating, LibraryContentRating.explicit);
  });

  test('pages keep the first src-only image and the data-src ones', () async {
    final fake = FakeLibraryFetcher()
      ..get(
        '$_base/manga/one-piece/1194',
        fixture: 'lelscan_chapter_one_piece_1194.html',
      );
    final service = LibraryAidokuNativeService(fetcher: fake.call);

    final pages = await service.loadPages(
      addon,
      _item('one-piece'),
      const LibraryMangaChapter(
        id: '1194',
        url: 'https://lelscanfr.com/manga/one-piece/1194',
      ),
    );

    expect(pages, hasLength(13));
    expect(
      pages.first,
      '$_base/storage/content/one-piece/1194/6ab9409fd4191_XVPk.webp',
    );
    expect(service.imageHeaders(addon)['Referer'], '$_base/');
  });
}
