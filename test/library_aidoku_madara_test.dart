// Madara engine: Mangas Origines (child-origines theme) and the generic
// Madara adapter kept for Manga Scantrad. Fixtures are minimized copies of
// pages captured on 2026-10-10 (Manga Scantrad: Wayback captures, the live
// site being behind a Cloudflare challenge).
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_aidoku_test_support.dart';

const String _ajax = 'https://mangas-origines.fr/wp-admin/admin-ajax.php';

LibraryCatalogItem _item(String id, String url) => LibraryCatalogItem(
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

void main() {
  group('Mangas Origines', () {
    final addon = aidokuAddon('fr.mangasorigines');

    test('latest listing posts madara_load_more with vars[paged]=1', () async {
      final fake = FakeLibraryFetcher()
        ..post(
          _ajax,
          form: const <String, String>{'page': '1'},
          fixture: 'mangasorigines_listing_latest_p0.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final page = await service.loadCatalogPage(addon, page: 2);

      final request = fake.requests.single;
      expect(request.method, 'POST');
      expect(request.form!['action'], 'madara_load_more');
      expect(request.form!['page'], '1');
      expect(request.form!['vars[paged]'], '1');
      expect(request.form!['vars[meta_key]'], '_latest_update');
      expect(request.headers['X-Requested-With'], 'XMLHttpRequest');
      expect(request.headers['Referer'], 'https://mangas-origines.fr/');
      expect(request.cache, same(LibraryCachePolicy.listing));

      expect(page.items, hasLength(16));
      expect(page.hasMore, isTrue, reason: '16 items = full page');
      final first = page.items.first;
      expect(first.id, 'swordmasters-youngest-son');
      expect(first.title, 'Swordmaster’s Youngest Son');
      expect(
        first.coverUrl,
        'https://mangas-origines.fr/wp-content/uploads/2023/06/'
        'thumbnail-10-175x238.webp',
      );
      expect(first.raw['categories'], <String>['Manhwa']);
      expect(
        first.raw['onlineKey'],
        'online:fr.mangasorigines:swordmasters-youngest-son',
      );
      expect(first.raw['contentRating'], 0);
      expect(first.raw.containsKey('explicitContent'), isFalse);
    });

    test('popular and trending listings use their meta keys', () async {
      final fake = FakeLibraryFetcher()
        ..post(
          _ajax,
          form: const <String, String>{'vars[meta_key]': '_wp_manga_views'},
          fixture: 'mangasorigines_listing_latest_p0.html',
        )
        ..post(
          _ajax,
          form: const <String, String>{
            'vars[meta_key]': '_wp_manga_week_views_value',
          },
          body: '',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      expect(service.listings(addon), <LibraryMangaListing>[
        LibraryMangaListing.latest,
        LibraryMangaListing.popular,
        LibraryMangaListing.trending,
      ]);
      final popular = await service.loadCatalogPage(
        addon,
        listing: LibraryMangaListing.popular,
      );
      expect(popular.listing, LibraryMangaListing.popular);
      expect(popular.items, hasLength(16));

      // Past the last page the site answers 200 with an empty body.
      final trending = await service.loadCatalogPage(
        addon,
        page: 200,
        listing: LibraryMangaListing.trending,
      );
      expect(trending.items, isEmpty);
      expect(trending.hasMore, isFalse);
    });

    test('search uses madara_child_catalogue JSON and its more flag', () async {
      final fake = FakeLibraryFetcher()
        ..post(
          _ajax,
          form: const <String, String>{
            'action': 'madara_child_catalogue',
            's': 'solo',
            'page': '1',
          },
          fixture: 'mangasorigines_catalogue_solo_p1.json',
        )
        ..post(
          _ajax,
          form: const <String, String>{
            'action': 'madara_child_catalogue',
            's': 'the',
            'page': '1',
          },
          fixture: 'mangasorigines_catalogue_the_p1.json',
        )
        ..post(
          _ajax,
          form: const <String, String>{
            'action': 'madara_child_catalogue',
            's': 'solo',
            'page': '2',
          },
          fixture: 'mangasorigines_catalogue_solo_p2.json',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final solo = await service.loadCatalogPage(addon, query: ' solo ');
      expect(solo.query, 'solo');
      expect(solo.items, hasLength(5));
      expect(solo.hasMore, isFalse);
      expect(solo.items.first.id, '13-solo-max-level-newbie');
      expect(solo.items.first.title, 'Solo Max-Level Newbie');
      expect(solo.items.first.raw['categories'], <String>['Action', 'Manhwa']);
      expect(solo.items.first.raw['status'], 'ongoing');
      expect(fake.requests.first.cache, same(LibraryCachePolicy.search));

      final the = await service.loadCatalogPage(addon, query: 'the');
      expect(the.items, hasLength(3));
      expect(the.hasMore, isTrue);

      final end = await service.loadCatalogPage(addon, query: 'solo', page: 2);
      expect(end.items, isEmpty);
      expect(end.hasMore, isFalse);
    });

    test('details and the full chapter list come from one request', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://mangas-origines.fr/oeuvre/826-solo-leveling/',
          fixture: 'mangasorigines_details_solo_leveling.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);
      final item = _item(
        '826-solo-leveling',
        'https://mangas-origines.fr/oeuvre/826-solo-leveling/',
      );

      final details = await service.loadManga(addon, item);

      expect(fake.requests, hasLength(1));
      expect(fake.requests.single.cache, same(LibraryCachePolicy.details));
      expect(details.item.title, 'Solo Leveling');
      expect(
        details.item.coverUrl,
        'https://mangas-origines.fr/wp-content/uploads/2023/06/'
        'solo-leveling-vol-3-comic-714x1024.jpg',
      );
      expect(details.item.description, isNotEmpty);
      expect(details.author, 'Chugong');
      expect(details.item.subtitle, 'Chugong');
      expect(details.artist, 'DUBU');
      expect(details.status, LibraryMangaStatus.completed);
      expect(details.typeLabel, 'Manhwa');
      expect(details.readingMode, LibraryReadingMode.vertical);
      expect(details.genres, <String>[
        'Action',
        'Aventure',
        'Combat',
        'Comédie',
        'Drame',
        'Ecchi',
      ]);
      expect(details.contentRating, LibraryContentRating.suggestive);
      expect(details.item.raw.containsKey('explicitContent'), isFalse);

      final numbers = details.chapters.map((c) => c.number).toList();
      expect(numbers, <double>[200, 199, 198, 179.5, 90.2, 1, 0]);
      final newest = details.chapters.first;
      expect(newest.id, '826-solo-leveling/chapitre-200/');
      expect(
        newest.url,
        'https://mangas-origines.fr/oeuvre/826-solo-leveling/chapitre-200/',
      );
      expect(newest.title, 'Chapitre 200');
      expect(newest.date, DateTime.utc(2023, 6, 21));
      expect(newest.sortKey, 202);
      expect(details.chaptersAscending.first.number, 0);
      expect(details.chaptersAscending.last.number, 200);

      // The legacy pair loadDetails + loadChapters shares the same request.
      await service.loadDetails(addon, item);
      final chapters = await service.loadChapters(addon, item);
      expect(chapters, hasLength(7));
      expect(fake.requests, hasLength(1));
    });

    test('chapter rows keep decimals, long names and data-ts dates', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://mangas-origines.fr/oeuvre/swordmasters-youngest-son/',
          fixture: 'mangasorigines_details_swordmaster.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final details = await service.loadManga(
        addon,
        _item('swordmasters-youngest-son', ''),
      );

      final chapters = details.chapters;
      expect(chapters.map((c) => c.number), <double>[216, 100, 87.5, 1]);
      expect(
        chapters.first.date,
        DateTime.fromMillisecondsSinceEpoch(1791657898 * 1000, isUtc: true),
      );
      expect(chapters[1].title, 'Chapitre 100 - Fin Saison 1');
      expect(chapters[1].number, 100, reason: 'not 100.1 from the slug');
      expect(chapters[1].date, DateTime.utc(2023, 11, 25));
      expect(chapters[2].date, DateTime.utc(2026, 7, 23));
    });

    test(
      'falls back to the ajax chapter endpoint when the page has no rows',
      () async {
        const page =
            '<html><body><div class="post-title">'
            '<h1 class="ori-sr-title">Solo Leveling</h1></div>'
            '<script id="wp-manga-js-extra">var manga = {"manga_id":"253"};'
            '</script></body></html>';
        final fake = FakeLibraryFetcher()
          ..get(
            'https://mangas-origines.fr/oeuvre/826-solo-leveling/',
            body: page,
          )
          ..post(
            'https://mangas-origines.fr/oeuvre/826-solo-leveling/ajax/chapters/',
            fixture: 'mangasorigines_ajax_chapters_solo_leveling.html',
          );
        final service = LibraryAidokuNativeService(fetcher: fake.call);

        final details = await service.loadManga(
          addon,
          _item('826-solo-leveling', ''),
        );

        expect(details.chapters.map((c) => c.number), <double>[200, 199, 198]);
        final ajax = fake.requests.last;
        expect(ajax.method, 'POST');
        expect(ajax.form, isEmpty);
        expect(ajax.headers['X-Requested-With'], 'XMLHttpRequest');
        expect(
          ajax.headers['Referer'],
          'https://mangas-origines.fr/oeuvre/826-solo-leveling/',
        );
      },
    );

    test(
      'a title without chapter rows keeps its details, no admin-ajax call',
      () async {
        // admin-ajax manga_get_chapters answers HTTP 400 on this site; the
        // fake fetcher fails the test on any request without a route.
        const page =
            '<html><body><div class="post-title">'
            '<h1 class="ori-sr-title">Nouveau titre</h1></div>'
            '<script id="wp-manga-js-extra">var manga = {"manga_id":"9001"};'
            '</script></body></html>';
        final fake = FakeLibraryFetcher()
          ..get('https://mangas-origines.fr/oeuvre/nouveau-titre/', body: page)
          ..post(
            'https://mangas-origines.fr/oeuvre/nouveau-titre/ajax/chapters/',
            body: '<div class="ori-chl-liste"></div>',
          );
        final service = LibraryAidokuNativeService(fetcher: fake.call);

        final details = await service.loadManga(
          addon,
          _item('nouveau-titre', ''),
        );

        expect(details.item.title, 'Nouveau titre');
        expect(details.chapters, isEmpty);
        expect(fake.requests, hasLength(2));
        expect(
          fake.requests.where((request) => request.uri.toString() == _ajax),
          isEmpty,
        );
      },
    );

    test('pages are read from div.page-break with trimmed data-src', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://mangas-origines.fr/oeuvre/826-solo-leveling/chapitre-200/'
          '?style=list',
          fixture: 'mangasorigines_chapter_solo_leveling_200.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final pages = await service.loadPages(
        addon,
        _item('826-solo-leveling', ''),
        const LibraryMangaChapter(
          id: '826-solo-leveling/chapitre-200/',
          url:
              'https://mangas-origines.fr/oeuvre/826-solo-leveling/chapitre-200/',
        ),
      );

      expect(pages, hasLength(12));
      expect(
        pages.first,
        'https://mangas-origines.fr/wp-content/uploads/WP-manga/data/'
        'manga_649064bd0c0db/9626520b2f07ca46b35c19b1f309e806/01.jpg',
      );
      expect(pages.last, endsWith('/12.jpg'));
      expect(fake.requests.single.cache, same(LibraryCachePolicy.chapterPages));
    });

    test('image headers carry the site Referer', () {
      final service = LibraryAidokuNativeService(
        fetcher: FakeLibraryFetcher().call,
      );
      final headers = service.imageHeaders(addon);
      expect(headers['Referer'], 'https://mangas-origines.fr/');
      expect(headers['User-Agent'], LibraryHttp.defaultUserAgent);
    });
  });

  group('Manga Scantrad (generic Madara)', () {
    final addon = aidokuAddon('fr.mangascantrad');

    test('is still callable although its known state is a challenge', () {
      final service = LibraryAidokuNativeService(
        fetcher: FakeLibraryFetcher().call,
      );
      expect(service.supports(addon), isTrue);
      expect(
        service.support(addon)!.knownState,
        LibrarySourceKnownState.challenge,
      );
    });

    test('a Cloudflare challenge surfaces as a typed network error', () async {
      final fake = FakeLibraryFetcher()
        ..post(
          'https://manga-scantrad.io/wp-admin/admin-ajax.php',
          status: 403,
          fixture: 'cloudflare_challenge_403.html',
          headers: const <String, String>{'cf-mitigated': 'challenge'},
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      await expectLater(
        service.loadCatalogPage(addon),
        throwsA(
          isA<LibraryNetworkException>().having(
            (error) => error.kind,
            'kind',
            LibraryNetworkErrorKind.challenge,
          ),
        ),
      );
    });

    test(
      'listing strips badges, reads src covers, uses non-empty hasMore',
      () async {
        final fake = FakeLibraryFetcher()
          ..post(
            'https://manga-scantrad.io/wp-admin/admin-ajax.php',
            form: const <String, String>{'page': '0', 'vars[paged]': '1'},
            fixture: 'mangascantrad_listing.html',
          );
        final service = LibraryAidokuNativeService(fetcher: fake.call);

        final page = await service.loadCatalogPage(addon);

        expect(page.items.map((item) => item.id), <String>[
          'the-princess-wants-to-die-peacefully',
          'the-real-daughter-is-back',
          'the-priest-of-corruption',
        ]);
        expect(
          page.items.first.title,
          'The Princess Wants to Die Peacefully !',
        );
        expect(
          page.items.first.coverUrl,
          'https://manga-scantrad.io/wp-content/uploads/2023/11/1-11-175x238.jpg',
        );
        expect(page.hasMore, isTrue);
      },
    );

    test('search sends the lowercased query and the adult cookie', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://manga-scantrad.io/page/1/?s=one+piece&post_type=wp-manga',
          body: '<html><body></body></html>',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final page = await service.loadCatalogPage(addon, query: 'One Piece');

      expect(page.items, isEmpty);
      expect(page.hasMore, isFalse);
      expect(fake.requests.single.headers['Cookie'], 'wpmanga-adault=1');
    });

    test(
      'details parse Madara fields and chapters use ajax/chapters/',
      () async {
        // Synthetic answer modelled on Madara's manga-chapters template: the
        // live endpoint is not observable behind the challenge.
        const chapters =
            '<div class="listing-chapters_wrap"><ul>'
            '<li class="wp-manga-chapter"><a href="https://manga-scantrad.io/'
            'manga/unknown-code/chapitre-062-5/">Chapitre 62.5</a>'
            '<span class="chapter-release-date"><i>3 mars 2025</i></span></li>'
            '<li class="wp-manga-chapter"><a href="https://manga-scantrad.io/'
            'manga/unknown-code/chapitre-62/"> Chapitre 62 </a>'
            '<span class="chapter-release-date"><a title="2 heures" '
            'class="c-new-tag"></a></span></li>'
            '<li class="wp-manga-chapter"><a href="https://manga-scantrad.io/'
            'manga/unknown-code/chapitre-1/"></a></li></ul></div>';
        final fake = FakeLibraryFetcher()
          ..get(
            'https://manga-scantrad.io/manga/unknown-code/',
            fixture: 'mangascantrad_details_unknown_code.html',
          )
          ..post(
            'https://manga-scantrad.io/manga/unknown-code/ajax/chapters/',
            body: chapters,
          );
        final service = LibraryAidokuNativeService(fetcher: fake.call);

        final details = await service.loadManga(
          addon,
          _item('unknown-code', ''),
        );

        expect(details.item.title, 'Unknown Code');
        expect(details.author, 'Carnby');
        expect(details.artist, 'Hoopa');
        expect(details.status, LibraryMangaStatus.ongoing);
        expect(details.genres, hasLength(9));
        expect(details.alternativeTitles, contains('Eonnoun Kodeu'));
        expect(
          details.item.coverUrl,
          'https://manga-scantrad.io/wp-content/uploads/2020/08/'
          '5d66dcd139a7c203196538-193x278.jpg',
        );
        expect(details.chapters.map((c) => c.number), <double?>[62.5, 62, 1]);
        expect(details.chapters.first.id, 'unknown-code/chapitre-062-5/');
        expect(details.chapters.first.date, DateTime.utc(2025, 3, 3));
        expect(
          details.chapters[1].date,
          fake.now.subtract(const Duration(hours: 2)),
        );
        expect(details.chapters[1].title, 'Chapitre 62');
        expect(fake.requests, hasLength(2));
      },
    );

    test(
      'falls back to admin-ajax manga_get_chapters with the numeric id',
      () async {
        final fake = FakeLibraryFetcher()
          ..get(
            'https://manga-scantrad.io/manga/unknown-code/',
            fixture: 'mangascantrad_details_unknown_code.html',
          )
          ..post(
            'https://manga-scantrad.io/manga/unknown-code/ajax/chapters/',
            status: 404,
          )
          ..post(
            'https://manga-scantrad.io/wp-admin/admin-ajax.php',
            form: const <String, String>{
              'action': 'manga_get_chapters',
              'manga': '8911',
            },
            body:
                '<li class="wp-manga-chapter"><a href="https://manga-scantrad.io/'
                'manga/unknown-code/chapitre-3/">Chapitre 3</a></li>',
          );
        final service = LibraryAidokuNativeService(fetcher: fake.call);

        final details = await service.loadManga(
          addon,
          _item('unknown-code', ''),
        );

        expect(details.chapters.single.number, 3);
      },
    );

    test('pages trim tab/newline-prefixed src values', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://manga-scantrad.io/manga/the-regressed-son-of-a-duke-is-an-'
          'assassin/chapitre-5/?style=list',
          fixture: 'mangascantrad_chapter_regressed_son_5.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final pages = await service.loadPages(
        addon,
        _item('the-regressed-son-of-a-duke-is-an-assassin', ''),
        const LibraryMangaChapter(
          id: 'the-regressed-son-of-a-duke-is-an-assassin/chapitre-5/',
          url:
              'https://manga-scantrad.io/manga/the-regressed-son-of-a-duke-is-'
              'an-assassin/chapitre-5/',
        ),
      );

      expect(pages, hasLength(14));
      expect(
        pages.first,
        'https://stockage.manga-scantrad.net/manga_65dbe1d8bbfc2/'
        'f311d16b4f1485ac0f35d36557b6e6f8/1.jpg',
      );
    });
  });
}
