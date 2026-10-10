// Service-level behaviour of the native Aidoku sources: verified support
// registry (2026-10-10), typed errors, cache modes, request reuse between
// details and chapters, and the health check.
//
// This file replaces the former assertions that seven sources were
// "currently working" and three were not: on 2026-10-10 Astral Manga had
// migrated to a Next.js app behind a Cloudflare challenge and PhenixScans'
// domain was parked, so both are now refused with a precise reason, while
// Manga Scantrad and Sushi Scans keep an adapter with a non-working known
// state.
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_aidoku_test_support.dart';

const String _moAjax = 'https://mangas-origines.fr/wp-admin/admin-ajax.php';
const String _moDetails =
    'https://mangas-origines.fr/oeuvre/swordmasters-youngest-son/';
const String _moChapter =
    'https://mangas-origines.fr/oeuvre/swordmasters-youngest-son/chapitre-216/'
    '?style=list';

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

final Uint8List _jpeg = Uint8List.fromList(<int>[
  0xff, 0xd8, 0xff, 0xe0, 0, 16, 0x4a, 0x46, 0x49, 0x46, 0, 1, 1, 0, //
]);

void _healthyOrigines(FakeLibraryFetcher fake, {bool htmlImage = false}) {
  const chapterPage =
      '<div class="reading-content"><div class="page-break">'
      '<img data-src=" https://mangas-origines.fr/wp-content/uploads/p/01.jpg">'
      '</div><div class="page-break">'
      '<img data-src=" https://mangas-origines.fr/wp-content/uploads/p/02.jpg">'
      '</div></div>';
  fake
    ..post(_moAjax, fixture: 'mangasorigines_listing_latest_p0.html')
    ..get(_moDetails, fixture: 'mangasorigines_details_swordmaster.html')
    ..get(_moChapter, body: chapterPage);
  if (htmlImage) {
    fake.get(
      'https://mangas-origines.fr/wp-content/uploads/p/01.jpg',
      body: '<html>blocked</html>',
      headers: const <String, String>{'content-type': 'text/html'},
    );
  } else {
    fake.get(
      'https://mangas-origines.fr/wp-content/uploads/p/01.jpg',
      bytes: _jpeg,
      headers: const <String, String>{'content-type': 'image/jpeg'},
    );
  }
}

void main() {
  group('support registry', () {
    final service = LibraryAidokuNativeService(
      fetcher: FakeLibraryFetcher().call,
    );

    test('adapters exist for the five sources verified on 2026-10-10', () {
      const expected = <String, LibrarySourceKnownState>{
        'fr.mangasorigines': LibrarySourceKnownState.working,
        'fr.lelscanfr': LibrarySourceKnownState.working,
        'fr.sushiscan': LibrarySourceKnownState.working,
        'fr.sushiscans': LibrarySourceKnownState.serverUnavailable,
        'fr.mangascantrad': LibrarySourceKnownState.challenge,
      };
      for (final entry in expected.entries) {
        final addon = aidokuAddon(entry.key);
        final support = service.support(addon)!;
        expect(service.supports(addon), isTrue, reason: entry.key);
        expect(support.hasAdapter, isTrue, reason: entry.key);
        expect(support.knownState, entry.value, reason: entry.key);
        expect(support.verifiedOn, DateTime.utc(2026, 10, 10));
        expect(support.listings, isNotEmpty, reason: entry.key);
        expect(support.evidence, isNotEmpty, reason: entry.key);
        expect(service.unsupportedReason(addon), isNull, reason: entry.key);
      }
      final working = expected.keys.where(
        (id) =>
            service.supportFor(id).knownState ==
            LibrarySourceKnownState.working,
      );
      for (final id in working) {
        expect(service.supportFor(id).navigationVerified, isTrue, reason: id);
        expect(service.supportFor(id).readingVerified, isTrue, reason: id);
      }
      expect(service.supportFor('fr.sushiscans').readingVerified, isFalse);
      expect(
        service.supportFor('fr.mangascantrad').navigationVerified,
        isFalse,
      );
    });

    test('offline, parked and migrated sources are refused with a reason', () {
      const expected = <String, LibrarySourceUnsupportedReason>{
        'fr.astralmanga':
            LibrarySourceUnsupportedReason.siteMigratedBehindChallenge,
        'fr.phenixscans': LibrarySourceUnsupportedReason.domainParked,
        'fr.mangascan': LibrarySourceUnsupportedReason.domainParked,
        'fr.reaperscans': LibrarySourceUnsupportedReason.siteOffline,
        'fr.legacyscans': LibrarySourceUnsupportedReason.originUnreachable,
      };
      for (final entry in expected.entries) {
        final addon = aidokuAddon(entry.key);
        expect(service.supports(addon), isFalse, reason: entry.key);
        expect(service.unsupportedReasonKind(addon), entry.value);
        expect(service.unsupportedReason(addon), entry.value.name);
        expect(service.listings(addon), isEmpty);
        expect(service.support(addon)!.hasAdapter, isFalse);
      }
      expect(
        service.supportFor('fr.astralmanga').knownState,
        LibrarySourceKnownState.siteChanged,
      );
      expect(
        service.supportFor('fr.phenixscans').knownState,
        LibrarySourceKnownState.parked,
      );
      expect(
        service.supportFor('fr.legacyscans').knownState,
        LibrarySourceKnownState.offline,
      );
    });

    test('unknown sources and non-Aidoku addons', () {
      final unknown = aidokuAddon('fr.someothersource');
      expect(service.supports(unknown), isFalse);
      expect(
        service.unsupportedReasonKind(unknown),
        LibrarySourceUnsupportedReason.adapterMissing,
      );
      expect(
        service.support(unknown)!.knownState,
        LibrarySourceKnownState.adapterMissing,
      );

      final plain = LibraryAddon.fromManifest(<String, dynamic>{
        'schema': LibraryAddon.schemaV1,
        'id': 'catalog.plain',
        'name': 'Plain',
        'version': '1',
        'baseUrl': 'https://example.com/',
      }, origin: 'https://example.com/addon.json');
      expect(service.supports(plain), isFalse);
      expect(service.support(plain), isNull);
      expect(service.unsupportedReason(plain), isNull);
    });

    test('the shared instance is usable before LibraryHttp is configured', () {
      final instance = LibraryAidokuNativeService.instance;
      expect(instance.supports(aidokuAddon('fr.sushiscan')), isTrue);
      expect(
        instance.imageHeaders(aidokuAddon('fr.reaperscans')),
        <String, String>{'User-Agent': LibraryHttp.defaultUserAgent},
      );
    });

    test('former page and chapter type names still construct', () {
      const page = LibraryAidokuCatalogPage(items: [], page: 3, hasMore: true);
      expect(page.page, 3);
      expect(page.hasMore, isTrue);
      expect(page.listing, LibraryMangaListing.latest);
      const chapter = LibraryAidokuChapter(
        id: 'one-piece-volume-97',
        url: 'https://sushiscan.net/one-piece-volume-97/',
        title: 'Volume 97',
        volume: 97,
      );
      expect(chapter.chapter, '');
      expect(chapter.displayTitle, 'Volume 97');
      expect(
        LibraryMangaChapter.fromJson(jsonDecode(jsonEncode(chapter.toJson()))),
        chapter,
      );
    });
  });

  group('requests and errors', () {
    test('an unsupported source fails without touching the network', () async {
      final fake = FakeLibraryFetcher();
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      await expectLater(
        service.loadCatalogPage(aidokuAddon('fr.phenixscans')),
        throwsA(
          isA<LibrarySourceException>()
              .having((e) => e.kind, 'kind', LibrarySourceErrorKind.unsupported)
              .having((e) => e.detail, 'detail', 'domainParked'),
        ),
      );
      expect(fake.requests, isEmpty);
    });

    test('network errors pass through; legacy wrappers wrap them', () async {
      final timeout = LibraryNetworkException(
        LibraryNetworkErrorKind.timeout,
        uri: Uri.parse(_moDetails),
      );
      final fake = FakeLibraryFetcher()..get(_moDetails, error: timeout);
      final service = LibraryAidokuNativeService(fetcher: fake.call);
      final addon = aidokuAddon('fr.mangasorigines');
      final item = _item('swordmasters-youngest-son');

      await expectLater(service.loadManga(addon, item), throwsA(same(timeout)));
      // The former screen catches LibraryAddonException only.
      await expectLater(
        service.loadChapters(addon, item),
        throwsA(
          isA<LibraryAddonException>().having(
            (error) => (error as LibrarySourceException).networkError,
            'networkError',
            same(timeout),
          ),
        ),
      );
    });

    test('cachedCatalogPage reads the cache only', () async {
      final fake = FakeLibraryFetcher()
        ..get(
          'https://sushiscan.net/catalogue/?order=update',
          fixture: 'sushiscan_catalogue_update_p1.html',
          cached: true,
        )
        ..get(
          'https://sushiscan.net/catalogue/?order=popular',
          fixture: 'sushiscan_catalogue_update_p1.html',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);
      final addon = aidokuAddon('fr.sushiscan');

      final cached = await service.cachedCatalogPage(addon);
      expect(cached, isNotNull);
      expect(cached!.items, hasLength(3));
      expect(cached.fromCache, isTrue);
      expect(cached.stale, isTrue);
      expect(cached.fetchedAt, fake.now);

      final missing = await service.cachedCatalogPage(
        addon,
        listing: LibraryMangaListing.popular,
      );
      expect(missing, isNull);
      expect(fake.modes, everyElement(LibraryFetchMode.cacheOnly));
    });

    test('cachedCatalogPage gives null for an unusable cached body', () async {
      final fake = FakeLibraryFetcher()
        ..post(
          'https://mangas-origines.fr/wp-admin/admin-ajax.php',
          body: '<html>maintenance</html>',
        );
      final modes = <LibraryFetchMode>[];
      // Serves the same body whatever the mode, as a cache holding it would.
      final service = LibraryAidokuNativeService(
        fetcher: (request, {mode = LibraryFetchMode.cacheFirst, cancel}) {
          modes.add(mode);
          return fake.call(request, cancel: cancel);
        },
      );
      final addon = aidokuAddon('fr.mangasorigines');

      // The network answer is not JSON: loadCatalogPage reports it ...
      await expectLater(
        service.loadCatalogPage(addon, query: 'solo'),
        throwsA(
          isA<LibrarySourceException>().having(
            (error) => error.kind,
            'kind',
            LibrarySourceErrorKind.parseFailed,
          ),
        ),
      );
      // ... and the cache-only helper treats the same body as unusable.
      expect(await service.cachedCatalogPage(addon, query: 'solo'), isNull);
      expect(modes.last, LibraryFetchMode.cacheOnly);
      expect(
        await service.cachedCatalogPage(aidokuAddon('fr.phenixscans')),
        isNull,
      );
      expect(fake.requests, hasLength(2));
    });

    test('details are reused for a short time, refresh asks again', () async {
      var now = DateTime.utc(2026, 10, 10, 21);
      final fake = FakeLibraryFetcher()
        ..get(_moDetails, fixture: 'mangasorigines_details_swordmaster.html');
      final service = LibraryAidokuNativeService(
        fetcher: fake.call,
        clock: () => now,
      );
      final addon = aidokuAddon('fr.mangasorigines');
      final item = _item('swordmasters-youngest-son');

      final first = await service.loadManga(addon, item);
      await service.loadDetails(addon, item);
      await service.loadChapters(addon, item);
      expect(fake.requests, hasLength(1));
      expect(
        first.onlineKey,
        'online:fr.mangasorigines:swordmasters-youngest-son',
      );

      await service.loadManga(addon, item, mode: LibraryFetchMode.refresh);
      expect(fake.requests, hasLength(2));
      expect(fake.modes.last, LibraryFetchMode.refresh);

      now = now.add(const Duration(minutes: 3));
      await service.loadManga(addon, item);
      expect(fake.requests, hasLength(3), reason: 'memo expired');
    });

    test('parse failures are typed', () async {
      final fake = FakeLibraryFetcher()
        ..get(_moDetails, body: '<html><body><p>maintenance</p></body></html>')
        ..post(
          '${_moDetails}ajax/chapters/',
          body: '<html><body></body></html>',
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      await expectLater(
        service.loadManga(
          aidokuAddon('fr.mangasorigines'),
          _item('swordmasters-youngest-son'),
        ),
        throwsA(
          isA<LibrarySourceException>().having(
            (error) => error.kind,
            'kind',
            LibrarySourceErrorKind.parseFailed,
          ),
        ),
      );
    });

    test('large bodies give the same result as small ones', () async {
      final small = aidokuFixture('sushiscan_details_one_piece.html');
      final padding = '<!-- ${'x' * 70000} -->';
      final large = Uint8List.fromList(<int>[
        ...utf8.encode(padding),
        ...small,
      ]);
      expect(large.length, greaterThan(64 * 1024));
      final fake = FakeLibraryFetcher()
        ..get('https://sushiscan.net/catalogue/one-piece/', bytes: small)
        ..get('https://sushiscan.net/catalogue/kagurabachi/', bytes: large);
      final service = LibraryAidokuNativeService(fetcher: fake.call);
      final addon = aidokuAddon('fr.sushiscan');

      final a = await service.loadManga(addon, _item('one-piece'));
      final b = await service.loadManga(addon, _item('kagurabachi'));

      expect(b.item.title, a.item.title);
      expect(b.chapters, a.chapters);
      expect(b.genres, a.genres);
    });
  });

  group('health check', () {
    test('runs the five steps with network-only requests', () async {
      final fake = FakeLibraryFetcher();
      _healthyOrigines(fake);
      final service = LibraryAidokuNativeService(
        fetcher: fake.call,
        clock: () => DateTime.utc(2026, 10, 11, 8),
      );

      final report = await service.checkHealth(
        aidokuAddon('fr.mangasorigines'),
      );

      expect(report.sourceId, 'fr.mangasorigines');
      expect(report.checkedAt, DateTime.utc(2026, 10, 11, 8));
      expect(report.steps.map((s) => s.step), LibrarySourceHealthStep.values);
      expect(report.steps.every((s) => s.ok), isTrue);
      expect(report.step(LibrarySourceHealthStep.listing).count, 16);
      expect(report.step(LibrarySourceHealthStep.chapters).count, 4);
      expect(report.step(LibrarySourceHealthStep.pages).count, 2);
      expect(report.step(LibrarySourceHealthStep.image).count, _jpeg.length);
      expect(report.navigationWorking, isTrue);
      expect(report.readingWorking, isTrue);
      expect(report.state, LibrarySourceKnownState.working);
      expect(fake.modes, everyElement(LibraryFetchMode.refresh));
      final imageRequest = fake.requests.last;
      expect(imageRequest.headers['Referer'], 'https://mangas-origines.fr/');

      final restored = LibrarySourceHealthReport.fromJson(
        jsonDecode(jsonEncode(report.toJson())),
      )!;
      expect(restored.readingWorking, isTrue);
      expect(restored.step(LibrarySourceHealthStep.image).count, _jpeg.length);
    });

    test('a challenge stops at the listing and names the state', () async {
      final fake = FakeLibraryFetcher()
        ..post(
          'https://manga-scantrad.io/wp-admin/admin-ajax.php',
          status: 403,
          fixture: 'cloudflare_challenge_403.html',
          headers: const <String, String>{'cf-mitigated': 'challenge'},
        );
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final report = await service.checkHealth(aidokuAddon('fr.mangascantrad'));

      final listing = report.step(LibrarySourceHealthStep.listing);
      expect(listing.ok, isFalse);
      expect(listing.networkError, LibraryNetworkErrorKind.challenge);
      expect(listing.statusCode, 403);
      expect(listing.errorKind, 'challenge');
      for (final step in LibrarySourceHealthStep.values.skip(1)) {
        expect(report.step(step).skipped, isTrue, reason: step.name);
      }
      expect(report.navigationWorking, isFalse);
      expect(report.state, LibrarySourceKnownState.challenge);
      expect(fake.requests, hasLength(1));
    });

    test('an HTML answer instead of an image fails the image step', () async {
      final fake = FakeLibraryFetcher();
      _healthyOrigines(fake, htmlImage: true);
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final report = await service.checkHealth(
        aidokuAddon('fr.mangasorigines'),
      );

      expect(report.navigationWorking, isTrue);
      expect(report.readingWorking, isFalse);
      final image = report.step(LibrarySourceHealthStep.image);
      expect(image.sourceError, LibrarySourceErrorKind.invalidImage);
      expect(report.state, LibrarySourceKnownState.siteChanged);
    });

    test('an unsupported source is reported without requests', () async {
      final fake = FakeLibraryFetcher();
      final service = LibraryAidokuNativeService(fetcher: fake.call);

      final report = await service.checkHealth(aidokuAddon('fr.legacyscans'));

      expect(
        report.step(LibrarySourceHealthStep.listing).sourceError,
        LibrarySourceErrorKind.unsupported,
      );
      expect(report.state, LibrarySourceKnownState.adapterMissing);
      expect(fake.requests, isEmpty);
    });
  });
}
