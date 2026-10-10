// MangaThemesia engine: SushiScan (sushiscan.net) and Sushi Scans
// (sushiscan.fr). Fixtures are minimized copies of pages captured on
// 2026-10-10 (sushiscan.fr chapter: Wayback capture of 2026-04-23, the
// origin answering 504 on the day).
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_aidoku_test_support.dart';

LibraryCatalogItem _item(String id, {String url = ''}) => LibraryCatalogItem(
  id: id,
  title: id,
  mediaType: LibraryMediaType.manga,
  subtitle: '',
  description: '',
  coverUrl: 'https://sushiscan.net/wp-content/uploads/listing.jpg',
  content: null,
  contentUrl: null,
  pageUrls: const <String>[],
  raw: <String, dynamic>{
    'mangaUrl': url,
    'categories': const <String>['Manga'],
  },
);

void main() {
  group('SushiScan (sushiscan.net)', () {
    final addon = aidokuAddon('fr.sushiscan');

    test(
      'latest listing: page 1 without page parameter, hpage hasMore',
      () async {
        final fake = FakeLibraryFetcher()
          ..get(
            'https://sushiscan.net/catalogue/?order=update',
            fixture: 'sushiscan_catalogue_update_p1.html',
          )
          ..get(
            'https://sushiscan.net/catalogue/?page=145&order=update',
            fixture: 'sushiscan_catalogue_update_p145.html',
          );
        final service = LibraryAidokuNativeService(fetcher: fake.call);

        final first = await service.loadCatalogPage(addon);
        expect(first.items.map((item) => item.id), <String>[
          'black-clover',
          'kingdom',
          '1-blue-lock',
        ]);
        expect(first.items.first.title, 'Black Clover');
        expect(
          first.items.first.coverUrl,
          'https://sushiscan.net/wp-content/uploads/blackclovercover.jpg'
          '?ver=1790341491',
          reason: 'the ?ver= suffix is kept verbatim (encoding it gives 404)',
        );
        expect(first.items.first.raw['mangaType'], 'Manga');
        expect(first.hasMore, isTrue);
        expect(fake.requests.first.headers['User-Agent'], isNotEmpty);

        final last = await service.loadCatalogPage(addon, page: 145);
        expect(last.items, hasLength(2));
        expect(last.items.first.title, 'Fairy Tail – Zerø');
        expect(last.hasMore, isFalse, reason: 'no Suivant link on page 145');
      },
    );

    test('popular and newest listings map to the site orders', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.net/catalogue/?order=popular',
          fixture: 'sushiscan_catalogue_update_p1.html',
        )
        ..get(
          'https://sushiscan.net/catalogue/?page=2&order=latest',
          fixture: 'sushiscan_catalogue_update_p145.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      await service.loadCatalogPage(
        addon,
        listing: LibraryMangaListing.popular,
      );
      final newest = await service.loadCatalogPage(
        addon,
        page: 2,
        listing: LibraryMangaListing.newest,
      );
      expect(newest.listing, LibraryMangaListing.newest);
      // trending is not offered: the default listing is used instead.
      expect(
        service.listings(addon),
        isNot(contains(LibraryMangaListing.trending)),
      );
    });

    test(
      'search normalizes smart punctuation and keeps titles intact',
      () async {
        final fake = FakeLibraryFetcher()
          ..get(
            'https://sushiscan.net/catalogue/page/1/?s=l+attaque+des+titans',
            fixture: 'sushiscan_search_the_p1.html',
          )
          ..get(
            'https://sushiscan.net/catalogue/page/1/?s=new+gotham',
            fixture: 'sushiscan_search_new_gotham.html',
          )
          ..get(
            'https://sushiscan.net/catalogue/page/2/?s=new+gotham',
            status: 404,
            body: 'not found',
          );
        final service = LibraryAidokuNativeService(fetcher: fake.call);

        final curly = await service.loadCatalogPage(
          addon,
          query: 'l’attaque  des “titans”',
        );
        expect(curly.query, 'l attaque des titans');
        expect(curly.items, hasLength(2));
        expect(curly.hasMore, isTrue, reason: '.pagination a.next present');
        expect(fake.requests.first.cache, same(LibraryCachePolicy.search));

        final gotham = await service.loadCatalogPage(
          addon,
          query: 'new gotham',
        );
        expect(gotham.items.single.title, 'Batman : New Gotham');
        expect(gotham.hasMore, isFalse);

        final end = await service.loadCatalogPage(
          addon,
          query: 'new gotham',
          page: 2,
        );
        expect(end.items, isEmpty, reason: 'HTTP 404 past the end is the end');
        expect(end.hasMore, isFalse);
      },
    );

    test('details and chapters from one request; volumes kept apart', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.net/catalogue/one-piece/',
          fixture: 'sushiscan_details_one_piece.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);
      final item = _item(
        'one-piece',
        url: 'https://sushiscan.net/catalogue/one-piece/',
      );

      final details = await service.loadManga(addon, item);

      expect(fake.requests, hasLength(1));
      expect(details.item.title, 'One Piece');
      expect(
        details.item.coverUrl,
        'https://sushiscan.net/wp-content/uploads/OnePieceCov.jpg',
      );
      expect(details.item.description.split('\n\n'), hasLength(3));
      expect(details.author, 'Oda Eiichiro');
      expect(details.status, LibraryMangaStatus.ongoing);
      expect(details.typeLabel, 'Manga');
      expect(details.readingMode, LibraryReadingMode.rightToLeft);
      expect(details.genres, <String>[
        'Action',
        'Aventure',
        'Comédie',
        'Drame',
        'Fantastique',
      ]);
      expect(details.contentRating, LibraryContentRating.safe);

      final chapters = details.chapters;
      expect(chapters, hasLength(5));
      expect(chapters.first.id, 'one-piece-chapitre-1180');
      expect(
        chapters.first.url,
        'https://sushiscan.net/one-piece-chapitre-1180/',
      );
      expect(chapters.first.title, 'Chapitre 1180');
      expect(chapters.first.number, 1180);
      expect(chapters.first.volume, isNull);
      expect(chapters.first.date, DateTime.utc(2026, 4, 19));
      final volume = chapters[3];
      expect(volume.title, 'Volume 97');
      expect(volume.volume, 97);
      expect(volume.number, isNull, reason: 'a volume is not chapter 97');
      expect(volume.isVolume, isTrue);
      expect(chapters.last.volume, 1);
      // Ascending order keeps volumes before chapters (reading order).
      expect(details.chaptersAscending.first.title, 'Volume 1');
      expect(details.chaptersAscending.last.title, 'Chapitre 1180');

      final again = await service.loadChapters(addon, item);
      expect(again, hasLength(5));
      expect(fake.requests, hasLength(1), reason: 'details reused');
    });

    test('decimal chapters parse from the label', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.net/catalogue/kagurabachi/',
          fixture: 'sushiscan_details_kagurabachi.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final details = await service.loadManga(addon, _item('kagurabachi'));

      expect(details.chapters.map((c) => c.number), <double>[119, 112.5, 1]);
      expect(details.chapters[1].date, DateTime.utc(2026, 2, 23));
    });

    test('pages come from ts_reader with the exact Referer', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.net/kagurabachi-chapitre-119/',
          fixture: 'sushiscan_chapter_kagurabachi_119.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final pages = await service.loadPages(
        addon,
        _item('kagurabachi'),
        const LibraryMangaChapter(
          id: 'kagurabachi-chapitre-119',
          url: 'https://sushiscan.net/kagurabachi-chapitre-119/',
        ),
      );

      expect(pages, hasLength(17));
      expect(
        pages.first,
        'https://c.sushiscan.net/wp-content/uploads97/KagurabachiChap119-01.webp',
      );
      expect(pages.last, endsWith('KagurabachiChap119-17.webp'));
      final request = fake.requests.single;
      expect(request.headers['Referer'], 'https://sushiscan.net/');
      expect(request.cache, same(LibraryCachePolicy.chapterPages));

      final headers = service.imageHeaders(addon);
      expect(headers['Referer'], 'https://sushiscan.net/');
      expect(headers['User-Agent'], LibraryHttp.defaultUserAgent);
      expect(headers['Accept'], startsWith('image/'));
    });

    test('a protected chapter is reported as such', () async {
      const page =
          '<html><body><div id="readerarea"></div><script>ts_reader.run('
          '{"sources":[{"source":"Server 1","images":[]}],'
          '"defaultSource":"Server 1","protected":true,'
          '"unlock_token":"abc"});</script></body></html>';
      final fake = FakeLibraryFetcher()
        ..get('https://sushiscan.net/locked-chapitre-1/', body: page)
        ..get('https://sushiscan.net/empty-chapitre-1/', body: '<p>x</p>');
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      await expectLater(
        service.loadPages(
          addon,
          _item('locked'),
          const LibraryMangaChapter(
            id: 'locked-chapitre-1',
            url: 'https://sushiscan.net/locked-chapitre-1/',
          ),
        ),
        throwsA(
          isA<LibrarySourceException>().having(
            (error) => error.kind,
            'kind',
            LibrarySourceErrorKind.protectedChapter,
          ),
        ),
      );
      await expectLater(
        service.loadPages(
          addon,
          _item('empty'),
          const LibraryMangaChapter(
            id: 'empty-chapitre-1',
            url: 'https://sushiscan.net/empty-chapitre-1/',
          ),
        ),
        throwsA(
          isA<LibrarySourceException>().having(
            (error) => error.kind,
            'kind',
            LibrarySourceErrorKind.noPages,
          ),
        ),
      );
    });

    test('a chapter URL from another host is rebuilt on the site', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.net/kagurabachi-chapitre-119/',
          fixture: 'sushiscan_chapter_kagurabachi_119.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final pages = await service.loadPages(
        addon,
        _item('kagurabachi'),
        const LibraryMangaChapter(
          id: 'kagurabachi-chapitre-119',
          url: 'https://evil.example/kagurabachi-chapitre-119/',
        ),
      );
      expect(pages, hasLength(17));
    });
  });

  group('Sushi Scans (sushiscan.fr)', () {
    final addon = aidokuAddon('fr.sushiscans');

    test('listing page 1 uses the explicit ?page=1 form', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.fr/catalogue/?page=1&order=update',
          fixture: 'sushiscans_catalog_p1.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final page = await service.loadCatalogPage(addon);

      expect(page.items.map((item) => item.title), <String>[
        'The Ruined World Was Mistaken for a Game',
        'La Servante Secrète',
        'Martial Peak',
      ]);
      expect(page.items.first.raw['mangaType'], 'Manhwa');
      expect(page.hasMore, isTrue);
    });

    test('details with English dates ignore the history template', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.fr/catalogue/one-piece/',
          fixture: 'sushiscans_details_one_piece.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final details = await service.loadManga(
        addon,
        _item('one-piece', url: 'https://sushiscan.fr/catalogue/one-piece/'),
      );

      expect(details.author, 'ODA Eiichiro');
      expect(details.artist, 'ODA Eiichiro');
      expect(details.chapters.map((c) => c.number), <double>[
        1189,
        1188,
        1187,
        1,
      ]);
      expect(details.chapters.first.date, DateTime.utc(2026, 7, 26));
      expect(details.chapters.last.date, DateTime.utc(2024, 4, 30));
      expect(
        details.chapters.any((chapter) => chapter.url.contains('{{')),
        isFalse,
      );
    });

    test('pages take the default ts_reader source, %20 kept', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.fr/one-piece-chapitre-1179/',
          fixture: 'sushiscans_chapter_one_piece_1179.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final pages = await service.loadPages(
        addon,
        _item('one-piece'),
        const LibraryMangaChapter(
          id: 'one-piece-chapitre-1179',
          url: 'https://sushiscan.fr/one-piece-chapitre-1179/',
        ),
      );

      expect(pages, hasLength(16));
      expect(
        pages.first,
        'https://s22.anime-sama.me/s1/scans/One%20Piece/1179/1.webp',
      );
      expect(service.imageHeaders(addon)['Referer'], 'https://sushiscan.fr/');
    });

    test('an origin 504 surfaces as serverUnavailable', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.fr/catalogue/?page=1&order=popular',
          status: 504,
          body: '<html><title>504 Gateway Time-out</title></html>',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      await expectLater(
        service.loadCatalogPage(addon, listing: LibraryMangaListing.popular),
        throwsA(
          isA<LibraryNetworkException>().having(
            (error) => error.kind,
            'kind',
            LibraryNetworkErrorKind.serverUnavailable,
          ),
        ),
      );
    });
  });
}
