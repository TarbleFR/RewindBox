// End-to-end user journeys of the Build 437 reading Library, offline.
//
// Each journey chains the real production classes: catalogue preview and
// activation, LibraryHttp with its disk cache, the Aidoku engines, the
// catalogue feed, the reading store, the image cache, the local library,
// the readers and the hub. Only what touches the outside world is replaced:
// the HTTP transport under LibraryHttp serves the minimized fixtures of
// test/fixtures (no network), files live in temporary directories and the
// PDF engine is the injectable fake inspector. Deterministic and CI-safe,
// except journey 4, which waits about 5 s of real time for its slow source.
//
// These are host tests (flutter_test). They prove nothing about an iPhone.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/screens/library_screen/library_catalog_preview_screen.dart';
import 'package:neostation/screens/library_screen/library_gamepad_view_controller.dart';
import 'package:neostation/screens/library_screen/library_manga_details_screen.dart';
import 'package:neostation/screens/library_screen/library_reader_launcher.dart';
import 'package:neostation/screens/library_screen/library_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/screens/library_screen/reader/library_page_source.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_archive_pages.dart';
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:neostation/services/library_text_document.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import 'library_catalog_import_fakes.dart' as catalog_fakes;
import 'library_local_fixtures.dart';
import 'library_reader_test_support.dart' as reader;
import 'library_ui_sources_harness.dart' as ui;

const String _frenchDirectory =
    'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/gh-pages/';
const String _frenchIndex = '${_frenchDirectory}index.min.json';
const String _moAjax = 'https://mangas-origines.fr/wp-admin/admin-ajax.php';
const String _lelscan = 'https://www.lelscanfr.com';
const String _sushiListing = 'https://sushiscan.net/catalogue/?order=update';
const String _sushiScansListing =
    'https://sushiscan.fr/catalogue/?page=1&order=update';

/// The three sources verified as working on 2026-10-10.
const List<String> _working = <String>[
  'fr.mangasorigines',
  'fr.lelscanfr',
  'fr.sushiscan',
];

const List<int> _pngSignature = <int>[
  0x89,
  0x50,
  0x4E,
  0x47,
  0x0D,
  0x0A,
  0x1A,
  0x0A,
];

/// Prints one line of measured values per journey (read by the reports).
void _report(String journey, Map<String, Object?> values) {
  // ignore: avoid_print
  print('[library-e2e] $journey ${jsonEncode(values)}');
}

void main() {
  // Wake lock, orientation, gamepad and platform channels stubbed; fresh
  // in-memory preferences before every test.
  reader.setUpReaderEnvironment();

  _catalogueJourney();
  _singleSourceJourney();
  _localLibraryJourney();
  _slowNetworkJourney();
  _largeCatalogueJourney();
  _hubPositionJourney();
}

// ---------------------------------------------------------------------------
// 1. Catalogue → three sources → feed → read → deactivate / reactivate
// ---------------------------------------------------------------------------

void _serveFrenchSources(_FixtureTransport transport) {
  transport
    ..onGet(
      _frenchIndex,
      file: 'test/fixtures/library_catalog/aidoku_french_legacy_index.min.json',
      headers: const <String, String>{'etag': '"french-index-fixture"'},
    )
    // Mangas Origines (Madara child theme): listing, details, chapter.
    ..onPost(
      _moAjax,
      form: const <String, String>{'action': 'madara_load_more'},
      fixture: 'mangasorigines_listing_latest_p0.html',
    )
    ..onGet(
      'https://mangas-origines.fr/oeuvre/swordmasters-youngest-son/',
      fixture: 'mangasorigines_details_swordmaster.html',
    )
    // The captured chapter page of another title of the same site (same
    // markup) stands in for chapter 216, which was not captured.
    ..onGet(
      'https://mangas-origines.fr/oeuvre/swordmasters-youngest-son/'
      'chapitre-216/?style=list',
      fixture: 'mangasorigines_chapter_solo_leveling_200.html',
    )
    // LelscanFR: home page (latest), One Piece over six chapter pages.
    ..onGet('$_lelscan/', fixture: 'lelscan_home_p1.html')
    ..onGet(
      '$_lelscan/manga/one-piece',
      fixture: 'lelscan_details_one_piece.html',
    )
    ..onGet(
      '$_lelscan/manga/one-piece/1194',
      fixture: 'lelscan_chapter_one_piece_1194.html',
    )
    // SushiScan: latest listing, Kagurabachi details and chapter 119.
    ..onGet(_sushiListing, fixture: 'sushiscan_catalogue_update_p1.html')
    ..onGet(
      'https://sushiscan.net/catalogue/kagurabachi/',
      fixture: 'sushiscan_details_kagurabachi.html',
    )
    ..onGet(
      'https://sushiscan.net/kagurabachi-chapitre-119/',
      fixture: 'sushiscan_chapter_kagurabachi_119.html',
    );
  for (var page = 2; page <= 6; page++) {
    transport.onGet(
      '$_lelscan/manga/one-piece?page=$page',
      fixture: 'lelscan_chapters_one_piece_p$page.html',
    );
  }
}

/// Opens [chapter] in the page reader's controller (the reader logic without
/// its widgets), shows the pages up to [upTo] (default: the last one), then
/// closes it. Returns the page URLs the reader received.
Future<List<String>> _readChapter({
  required LibraryAidokuNativeService native,
  required LibraryImageCache images,
  required LibraryReadingStore store,
  required LibraryAddon addon,
  required LibraryMangaDetails details,
  required LibraryMangaChapter chapter,
  int? upTo,
  void Function(LibraryPageReaderController controller)? onReady,
}) async {
  final controller = LibraryPageReaderController(
    content: LibraryOnlineReaderContent(
      addon: addon,
      details: details,
      chapter: chapter,
      loader: (addon, item, chapter, cancel) =>
          native.loadPages(addon, item, chapter, cancel: cancel),
      imageHeaders: native.imageHeaders(addon),
      imageCache: images,
    ),
    store: store,
    saveDelay: const Duration(milliseconds: 1),
  );
  try {
    await controller.start();
    expect(
      controller.status,
      LibraryPageReaderStatus.ready,
      reason: 'chapter ${chapter.id}: ${controller.error}',
    );
    onReady?.call(controller);
    final last = upTo ?? controller.pageCount - 1;
    for (var page = controller.page + 1; page <= last; page++) {
      controller.setPage(page);
    }
    return List<String>.of(
      (controller.source! as LibraryNetworkPageSource).urls,
    );
  } finally {
    controller.dispose();
  }
}

/// The favourite the title page writes (LibraryMangaDetailsScreen).
LibraryFavorite _favoriteFor(
  LibraryAddon addon,
  LibraryMangaDetails details,
  Map<String, String> imageHeaders,
) {
  final item = details.item;
  return LibraryFavorite(
    key: details.onlineKey,
    sourceId: details.sourceId,
    mangaId: item.id,
    title: item.title,
    addonId: addon.id,
    coverUrl: item.coverUrl,
    coverHeaders: imageHeaders,
    mangaUrl: item.raw['mangaUrl']?.toString(),
    language: item.raw['language']?.toString(),
    snapshot: LibraryMangaDetailsScreen.favoriteSnapshot(item),
  );
}

void _catalogueJourney() {
  testWidgets(
    '1. catalogue: preview, tick three sources, read them, deactivate and '
    'reactivate one without losing its favourite or progress',
    (tester) async {
      final transport = _FixtureTransport();
      _serveFrenchSources(transport);
      final clock = _Clock(DateTime.utc(2026, 10, 11, 9));
      late Directory root;
      late Directory support;
      late LibraryHttp httpLayer;
      late LibraryAidokuNativeService native;
      late LibraryImageCache images;
      late LibraryAddonService addons;
      late LibrarySourceCatalogService catalogs;
      late LibraryCatalogPreview preview;
      final previewWatch = Stopwatch();
      await tester.runAsync(() async {
        root = await Directory.systemTemp.createTemp('ns_e2e_catalogue_');
        support = Directory(p.join(root.path, 'Support', 'Library'));
        final caches = Directory(p.join(root.path, 'Caches', 'Library'));
        httpLayer = LibraryHttp(
          client: transport,
          cacheDirectory: caches,
          clock: clock.call,
        );
        native = LibraryAidokuNativeService(
          fetcher: httpLayer.send,
          clock: clock.call,
        );
        images = LibraryImageCache(
          fetcher: httpLayer.send,
          cacheDirectory: caches,
          clock: clock.call,
        );
        addons = LibraryAddonService.forTesting();
        await addons.load();
        catalogs = LibrarySourceCatalogService(
          fetcher: httpLayer.send,
          addons: addons,
          store: LibraryCatalogFileStore(directory: () async => support),
          clock: clock.call,
        );
        previewWatch.start();
        preview = await catalogs.preview(_frenchIndex);
        previewWatch.stop();
      });
      addTearDown(() => _deleteQuietly(root));

      expect(preview.format, LibraryCatalogFormat.aidokuLegacyIndex);
      expect(preview.sources, hasLength(10));
      expect(preview.sources.where((entry) => entry.alreadyInstalled), isEmpty);
      expect(addons.addons, isEmpty, reason: 'a preview installs nothing');

      // The preview screen: nothing is ticked; the user ticks three rows.
      LibraryActivationResult? activation;
      await ui.pumpLibraryUi(
        tester,
        Builder(
          builder: (context) => Center(
            child: FilledButton(
              onPressed: () async {
                activation = await LibraryCatalogPreviewScreen.open(
                  context,
                  preview,
                  catalogService: catalogs,
                  aidokuService: native,
                  imageCache: ui.NoImageCache(),
                  enableGamepad: false,
                );
              },
              child: const Text('open preview'),
            ),
          ),
        ),
        size: const Size(1280, 1600),
      );
      await tester.tap(find.text('open preview'));
      await tester.pumpAndSettle();
      final ticks = tester
          .widgetList<Checkbox>(find.byType(Checkbox))
          .map((box) => box.value)
          .toList();
      expect(ticks, hasLength(10));
      expect(ticks, everyElement(isFalse), reason: 'nothing pre-selected');
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const ValueKey<String>('activate-button')),
            )
            .onPressed,
        isNull,
      );
      for (final id in _working) {
        await tester.tap(find.byKey(ValueKey<String>('entry-$id')));
        await tester.pump();
      }
      await tester.tap(find.text('Activate (3)'));
      await _pumpUntil(tester, find.text('Activation finished'));
      expect(find.text('Added: 3'), findsOneWidget);
      await tester.tap(find.text('Done'));
      await tester.pumpAndSettle();
      expect(
        activation?.added.map((addon) => addon.aidokuSourceId).toSet(),
        _working.toSet(),
      );
      expect(activation!.skipped, isEmpty);
      expect(activation!.catalogRemembered, isTrue);

      final metrics = <String, Object?>{
        'previewMs': previewWatch.elapsedMilliseconds,
        'catalogueSources': preview.sources.length,
      };
      await tester.runAsync(() async {
        final installed = await addons.load();
        expect(
          installed.map((addon) => addon.aidokuSourceId).toSet(),
          _working.toSet(),
          reason: 'exactly the ticked sources',
        );
        expect(
          (await LibraryAddonService.forTesting().load())
              .map((addon) => addon.aidokuSourceId)
              .toSet(),
          _working.toSet(),
          reason: 'persisted for the next launch',
        );
        // A new catalogue service on the same catalogs.json. (The screen's
        // instance ran in the test's fake-async zone; its internal lock
        // future cannot be awaited from this real zone.)
        catalogs = LibrarySourceCatalogService(
          fetcher: httpLayer.send,
          addons: addons,
          store: LibraryCatalogFileStore(directory: () async => support),
          clock: clock.call,
        );
        final remembered = await catalogs.list();
        expect(remembered, hasLength(1));
        expect(remembered.single.sourceCount, 10);
        expect(remembered.single.url, _frenchIndex);

        LibraryAddon addonOf(String id) =>
            installed.firstWhere((addon) => addon.aidokuSourceId == id);
        final origines = addonOf('fr.mangasorigines');
        final lelscan = addonOf('fr.lelscanfr');
        final sushi = addonOf('fr.sushiscan');

        // The hub feed opens the three sources and publishes their titles.
        final feed = LibraryCatalogFeed(
          backend: LibraryCatalogFeedBackend(aidoku: native),
          clock: clock.call,
        );
        final feedWatch = Stopwatch()..start();
        await feed.open(installed);
        feedWatch.stop();
        expect(
          feed.sources.map((source) => source.addon.aidokuSourceId).toSet(),
          _working.toSet(),
        );
        for (final source in feed.sources) {
          expect(source.failure, isNull, reason: source.key);
        }
        final counts = <String, int>{
          for (final source in feed.sources)
            source.addon.aidokuSourceId!: source.entryCount,
        };
        expect(counts, <String, int>{
          'fr.mangasorigines': 16,
          'fr.lelscanfr': 3,
          'fr.sushiscan': 3,
        });
        expect(feed.entries, hasLength(22));

        final store = LibraryReadingStore(
          directory: support,
          clock: clock.call,
          saveDelay: const Duration(milliseconds: 5),
          coverPinner: images,
        );
        await store.load();

        // Mangas Origines: the first title of the latest listing, read to
        // its last page.
        final originesItem = feed.source(origines.id)!.entries.first.item;
        expect(originesItem.id, 'swordmasters-youngest-son');
        final originesDetails = await native.loadManga(origines, originesItem);
        expect(originesDetails.chapters.map((c) => c.number), <double>[
          216,
          100,
          87.5,
          1,
        ]);
        expect(originesDetails.chaptersAscending.map((c) => c.number), <double>[
          1,
          87.5,
          100,
          216,
        ]);
        final originesChapter = originesDetails.chapters.first;
        final originesPages = await _readChapter(
          native: native,
          images: images,
          store: store,
          addon: origines,
          details: originesDetails,
          chapter: originesChapter,
        );
        expect(originesPages, hasLength(12));

        // LelscanFR: One Piece (chapter list over six pages), chapter 1194
        // read up to page 7 of 13, added to the favourites.
        final lelscanItem = feed.source(lelscan.id)!.entries.first.item;
        expect(lelscanItem.id, 'one-piece');
        final lelscanDetails = await native.loadManga(lelscan, lelscanItem);
        expect(lelscanDetails.chaptersComplete, isTrue);
        expect(lelscanDetails.chapters, hasLength(14));
        final served = lelscanDetails.chapters.map((c) => c.number!).toList();
        expect(served, [...served]..sort((a, b) => b.compareTo(a)));
        final ascending = lelscanDetails.chaptersAscending
            .map((c) => c.number!)
            .toList();
        expect(ascending, [...ascending]..sort());
        final lelscanChapter = lelscanDetails.chapters.firstWhere(
          (chapter) => chapter.id == '1194',
        );
        final lelscanPages = await _readChapter(
          native: native,
          images: images,
          store: store,
          addon: lelscan,
          details: lelscanDetails,
          chapter: lelscanChapter,
          upTo: 6,
        );
        expect(lelscanPages, hasLength(13));
        await store.addFavorite(
          _favoriteFor(lelscan, lelscanDetails, native.imageHeaders(lelscan)),
        );

        // SushiScan: the listing fixture's titles have no captured details
        // page; Kagurabachi (details + chapter 119 captured) is opened from
        // its catalogue id, as a favourite or a link would.
        expect(
          feed.source(sushi.id)!.entries.map((entry) => entry.item.id),
          <String>['black-clover', 'kingdom', '1-blue-lock'],
        );
        final sushiDetails = await native.loadManga(
          sushi,
          LibraryCatalogItem(
            id: 'kagurabachi',
            title: 'Kagurabachi',
            mediaType: LibraryMediaType.manga,
            subtitle: '',
            description: '',
            coverUrl: null,
            content: null,
            contentUrl: null,
            pageUrls: const <String>[],
            raw: const <String, dynamic>{
              'mangaUrl': 'https://sushiscan.net/catalogue/kagurabachi/',
            },
          ),
        );
        expect(sushiDetails.chapters.map((c) => c.number), <double>[
          119,
          112.5,
          1,
        ]);
        final sushiPages = await _readChapter(
          native: native,
          images: images,
          store: store,
          addon: sushi,
          details: sushiDetails,
          chapter: sushiDetails.chapters.first,
        );
        expect(sushiPages, hasLength(17));
        await store.addFavorite(
          _favoriteFor(sushi, sushiDetails, native.imageHeaders(sushi)),
        );

        // First page image of each chapter through the image cache, with
        // the Referer each site requires.
        final referers = <String, String>{};
        for (final (addon, url) in <(LibraryAddon, String)>[
          (origines, originesPages.first),
          (lelscan, lelscanPages.first),
          (sushi, sushiPages.first),
        ]) {
          final bytes = await images.load(
            url,
            headers: native.imageHeaders(addon),
          );
          expect(bytes.sublist(0, 8), _pngSignature);
          final sent = transport.exchanges.lastWhere((e) => e.url == url);
          referers[addon.aidokuSourceId!] = sent.header('referer') ?? '';
        }
        expect(referers, <String, String>{
          'fr.mangasorigines': 'https://mangas-origines.fr/',
          'fr.lelscanfr': '$_lelscan/',
          'fr.sushiscan': 'https://sushiscan.net/',
        });

        // Progress, chapter marks and favourites as the readers wrote them.
        final originesKey = originesDetails.onlineKey;
        final lelscanKey = lelscanDetails.onlineKey;
        final sushiKey = sushiDetails.onlineKey;
        expect(lelscanKey, 'online:fr.lelscanfr:one-piece');
        final originesProgress = store.progressFor(originesKey)!;
        expect(originesProgress.chapterId, originesChapter.id);
        expect(originesProgress.pageIndex, 11);
        expect(originesProgress.fraction, 1.0);
        expect(
          store.chapterMark(originesKey, originesChapter.id)!.read,
          isTrue,
        );
        final lelscanProgress = store.progressFor(lelscanKey)!;
        expect(lelscanProgress.chapterId, '1194');
        expect(lelscanProgress.pageIndex, 6);
        expect(lelscanProgress.pageCount, 13);
        expect(store.chapterMark(lelscanKey, '1194')!.read, isFalse);
        expect(store.chapterMark(lelscanKey, '1194')!.page, 6);
        expect(
          store.chapterMark(sushiKey, sushiDetails.chapters.first.id)!.read,
          isTrue,
        );
        expect(store.favorites.map((f) => f.key).toSet(), <String>{
          lelscanKey,
          sushiKey,
        });
        final lelscanCover = store.favorite(lelscanKey)!.coverUrl!;
        expect(await images.isPinned(lelscanCover), isTrue);
        await store.flush();

        // Deactivating LelscanFR removes it from the feed only.
        final lelscanListingRequests = transport.count('$_lelscan/');
        expect(await catalogs.deactivate(lelscan.id), isTrue);
        final afterDeactivation = await addons.load();
        expect(
          afterDeactivation.map((addon) => addon.aidokuSourceId).toSet(),
          <String>{'fr.mangasorigines', 'fr.sushiscan'},
        );
        await feed.open(afterDeactivation);
        expect(feed.source(lelscan.id), isNull);
        expect(
          feed.entries.where((entry) => entry.sourceKey == lelscan.id),
          isEmpty,
        );
        expect(store.isFavorite(lelscanKey), isTrue);
        expect(store.progressFor(lelscanKey)!.pageIndex, 6);
        final relaunchedStore = LibraryReadingStore(
          directory: support,
          clock: clock.call,
        );
        await relaunchedStore.load();
        expect(relaunchedStore.isFavorite(lelscanKey), isTrue);
        expect(relaunchedStore.progressFor(lelscanKey)!.pageIndex, 6);
        expect(relaunchedStore.chapterMark(lelscanKey, '1194')!.page, 6);
        expect(await images.isPinned(lelscanCover), isTrue);

        // Reactivating it from the remembered catalogue (cached, no new
        // download) brings back the same keys, favourite and position.
        final indexRequests = transport.count(_frenchIndex);
        final again = await catalogs.preview(_frenchIndex);
        expect(transport.count(_frenchIndex), indexRequests);
        expect(again.fromCache, isTrue);
        expect(again.sourceById('fr.lelscanfr')!.alreadyInstalled, isFalse);
        expect(again.sourceById('fr.sushiscan')!.alreadyInstalled, isTrue);
        final reactivation = await catalogs.activate(again, <String>{
          'fr.lelscanfr',
        });
        expect(reactivation.added.single.aidokuSourceId, 'fr.lelscanfr');
        final reactivated = await addons.load();
        await feed.open(reactivated);
        final back = feed.source(lelscan.id)!;
        expect(back.entryCount, 3);
        expect(back.entries.first.item.raw['onlineKey'], lelscanKey);
        expect(
          transport.count('$_lelscan/'),
          lelscanListingRequests,
          reason: 'the listing is shown from the cache',
        );
        expect(relaunchedStore.isFavorite(lelscanKey), isTrue);
        final resumedAt = <int>[];
        await _readChapter(
          native: native,
          images: images,
          store: relaunchedStore,
          addon: reactivated.firstWhere(
            (addon) => addon.aidokuSourceId == 'fr.lelscanfr',
          ),
          details: await native.loadManga(
            reactivated.firstWhere(
              (addon) => addon.aidokuSourceId == 'fr.lelscanfr',
            ),
            back.entries.first.item,
          ),
          chapter: lelscanChapter,
          upTo: 6,
          onReady: (controller) => resumedAt.add(controller.page),
        );
        expect(resumedAt, <int>[6], reason: 'the reader resumes at page 7');
        await relaunchedStore.flush();
        feed.dispose();

        expect(transport.unexpected, isEmpty);
        metrics.addAll(<String, Object?>{
          'feedOpenMs': feedWatch.elapsedMilliseconds,
          'feedEntries': counts,
          'chapters': <String, int>{
            'fr.mangasorigines': originesDetails.chapters.length,
            'fr.lelscanfr': lelscanDetails.chapters.length,
            'fr.sushiscan': sushiDetails.chapters.length,
          },
          'pages': <String, int>{
            'fr.mangasorigines': originesPages.length,
            'fr.lelscanfr': lelscanPages.length,
            'fr.sushiscan': sushiPages.length,
          },
          'transportRequests': transport.exchanges.length,
          'http': httpLayer.stats.toJson(),
        });
        await httpLayer.idle();
        await images.idle();
        httpLayer.close();
      });
      _report('journey1-catalogue', metrics);
    },
  );
}

// ---------------------------------------------------------------------------
// 2. A single source.json or .aix
// ---------------------------------------------------------------------------

void _singleSourceJourney() {
  test('2. a single source.json (legacy and new format) or .aix is recognized '
      'with its adapter status; a package stays metadata only', () async {
    final root = await Directory.systemTemp.createTemp('ns_e2e_single_');
    addTearDown(() => _deleteQuietly(root));
    final clock = _Clock(DateTime.utc(2026, 10, 11, 10));
    const legacyBlob =
        'https://github.com/Moomooo95/aidoku-french-sources/blob/master/'
        'src/rust/madara/sources/mangascantrad/res/source.json';
    const legacyRaw =
        'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/'
        'master/src/rust/madara/sources/mangascantrad/res/source.json';
    const modernUrl =
        'https://raw.githubusercontent.com/Aidoku-Community/sources/main/'
        'sources/fr.bigsolo/res/source.json';
    const packageUrl = 'https://example.org/aidoku/sources/fr.sushiscan-v9.aix';
    // Packages built here. main.wasm is flagged as a UNIX symlink with
    // corrupt deflate data: any attempt to inflate it would fail.
    final readablePackage = catalog_fakes.markAsCorruptSymlink(
      catalog_fakes.buildAix(
        sourceJson: <String, dynamic>{
          'info': <String, dynamic>{
            'id': 'fr.sushiscan',
            'name': 'SushiScan',
            'version': 9,
            'url': 'https://sushiscan.net',
            'languages': <String>['fr'],
            'contentRating': 0,
          },
        },
        mainWasm: Uint8List(4096),
      ),
      'Payload/main.wasm',
    );
    final unknownPackage = catalog_fakes.markAsCorruptSymlink(
      catalog_fakes.buildAix(
        sourceJson: <String, dynamic>{
          'info': <String, dynamic>{
            'id': 'fr.inconnu',
            'lang': 'fr',
            'name': 'Source inconnue',
            'version': 2,
            'url': 'https://inconnu.example.fr',
            'nsfw': 0,
          },
        },
        mainWasm: Uint8List(4096),
      ),
      'Payload/main.wasm',
    );
    final transport = _FixtureTransport()
      ..onGet(
        legacyRaw,
        file: 'test/fixtures/library_catalog/source_legacy_mangascantrad.json',
      )
      ..onGet(
        modernUrl,
        file: 'test/fixtures/library_catalog/source_new_bigsolo.json',
      )
      ..onGet(
        packageUrl,
        bytes: readablePackage,
        headers: const <String, String>{
          'content-type': 'application/octet-stream',
        },
      )
      ..onGet(_sushiListing, fixture: 'sushiscan_catalogue_update_p1.html');
    final httpLayer = LibraryHttp(
      client: transport,
      cacheDirectory: Directory(p.join(root.path, 'Caches', 'Library')),
      clock: clock.call,
    );
    addTearDown(httpLayer.close);
    final addons = LibraryAddonService.forTesting();
    await addons.load();
    final catalogs = LibrarySourceCatalogService(
      fetcher: httpLayer.send,
      addons: addons,
      store: LibraryCatalogMemoryStore(),
      clock: clock.call,
    );
    final native = LibraryAidokuNativeService(
      fetcher: httpLayer.send,
      clock: clock.call,
    );

    // Legacy source.json pasted as a GitHub page link.
    final legacy = await catalogs.preview(legacyBlob);
    expect(transport.exchanges.map((e) => e.url), <String>[legacyRaw]);
    expect(legacy.format, LibraryCatalogFormat.aidokuSourceJson);
    final scantrad = legacy.sources.single;
    expect(scantrad.id, 'fr.mangascantrad');
    expect(scantrad.legacyAidokuFormat, isTrue);
    expect(scantrad.version, 12);
    expect(scantrad.contentRating, 1);
    expect(scantrad.websiteUrl, 'https://manga-scantrad.io');
    final scantradSupport = native.supportFor(scantrad.id);
    expect(scantradSupport.hasAdapter, isTrue);
    expect(scantradSupport.knownState, LibrarySourceKnownState.challenge);

    // New-format source.json of a source NeoStation has no reader for.
    final modern = await catalogs.preview(modernUrl);
    final bigsolo = modern.sources.single;
    expect(bigsolo.id, 'fr.bigsolo');
    expect(bigsolo.legacyAidokuFormat, isFalse);
    expect(bigsolo.languages, <String>['fr']);
    final bigsoloSupport = native.supportFor(bigsolo.id);
    expect(bigsoloSupport.hasAdapter, isFalse);
    expect(
      bigsoloSupport.unsupportedReason,
      LibrarySourceUnsupportedReason.adapterMissing,
    );

    // .aix package from a URL: source.json and the icon only.
    final package = await catalogs.preview(packageUrl);
    expect(package.format, LibraryCatalogFormat.aidokuPackage);
    final packaged = package.sources.single;
    expect(packaged.id, 'fr.sushiscan');
    expect(packaged.legacyAidokuFormat, isFalse);
    expect(packaged.iconBytes, catalog_fakes.fakePngBytes);
    expect(packaged.packageSize, readablePackage.length);
    expect(packaged.packageSha256, sha256.convert(readablePackage).toString());
    expect(native.supportFor(packaged.id).hasAdapter, isTrue);
    expect(
      native.supportFor(packaged.id).knownState,
      LibrarySourceKnownState.working,
    );

    // .aix package picked as a local file.
    final local = await catalogs.previewDocument(
      unknownPackage,
      fileName: 'fr.inconnu-v2.aix',
    );
    expect(local.isLocalFile, isTrue);
    expect(local.format, LibraryCatalogFormat.aidokuPackage);
    expect(local.sources.single.id, 'fr.inconnu');
    expect(local.sources.single.legacyAidokuFormat, isTrue);
    expect(
      native.supportFor('fr.inconnu').unsupportedReason,
      LibrarySourceUnsupportedReason.adapterMissing,
    );

    // Activation installs each recognized source as metadata only.
    expect(
      (await catalogs.activate(legacy, <String>{'fr.mangascantrad'})).added,
      hasLength(1),
    );
    expect(
      (await catalogs.activate(modern, <String>{'fr.bigsolo'})).added,
      hasLength(1),
    );
    expect(
      (await catalogs.activate(package, <String>{'fr.sushiscan'})).added,
      hasLength(1),
    );
    final fromFile = await catalogs.activate(local, <String>{'fr.inconnu'});
    expect(fromFile.added, hasLength(1));
    expect(
      fromFile.catalogRemembered,
      isFalse,
      reason: 'a local file cannot be refreshed',
    );
    expect(
      transport.count(packageUrl),
      1,
      reason: 'activation never downloads the package again',
    );
    final installed = {
      for (final addon in await addons.load()) addon.aidokuSourceId!: addon,
    };
    expect(installed.keys.toSet(), <String>{
      'fr.mangascantrad',
      'fr.bigsolo',
      'fr.sushiscan',
      'fr.inconnu',
    });
    for (final addon in installed.values) {
      expect(addon.isAidokuRepositorySource, isTrue, reason: addon.id);
      expect(addon.isMetadataOnlyOnIos, isTrue, reason: addon.id);
    }
    expect(
      (installed['fr.sushiscan']!.manifest['provider'] as Map)['packageSha256'],
      packaged.packageSha256,
    );
    final supported = <String, bool>{
      for (final entry in installed.entries)
        entry.key: native.supports(entry.value),
    };
    expect(supported, <String, bool>{
      'fr.mangascantrad': true,
      'fr.bigsolo': false,
      'fr.sushiscan': true,
      'fr.inconnu': false,
    });
    expect(
      native.unsupportedReasonKind(installed['fr.bigsolo']!),
      LibrarySourceUnsupportedReason.adapterMissing,
    );

    // The feed browses only what NeoStation reads, and never requests a
    // source verified as blocked.
    final feed = LibraryCatalogFeed(
      backend: LibraryCatalogFeedBackend(aidoku: native),
      clock: clock.call,
    );
    addTearDown(feed.dispose);
    await feed.open(installed.values.toList());
    expect(
      feed.sources.map((source) => source.addon.aidokuSourceId).toSet(),
      <String>{'fr.mangascantrad', 'fr.sushiscan'},
    );
    expect(feed.source('aidoku.fr.sushiscan')!.entryCount, 3);
    final blocked = feed.source('aidoku.fr.mangascantrad')!.failure!;
    expect(blocked.issue, LibraryFeedIssue.challenge);
    expect(blocked.known, isTrue);
    expect(transport.to('manga-scantrad.io'), isEmpty);
    expect(transport.unexpected, isEmpty);
    _report('journey2-single-source', <String, Object?>{
      'legacy': scantrad.id,
      'legacyAdapter': scantradSupport.hasAdapter,
      'legacyKnownState': scantradSupport.knownState.name,
      'modern': bigsolo.id,
      'modernAdapter': bigsoloSupport.hasAdapter,
      'modernReason': bigsoloSupport.unsupportedReason?.name,
      'packageAdapter': supported['fr.sushiscan'],
      'localPackageAdapter': supported['fr.inconnu'],
      'packageBytes': readablePackage.length,
      'feedSources': feed.sources.length,
    });
  });
}

// ---------------------------------------------------------------------------
// 3. Local library: import, rename, delete, restart, resume
// ---------------------------------------------------------------------------

String _longChapter() => xhtml(
  <String>[
    '<h1 id="c1">Chapter One</h1>',
    for (var i = 0; i < 240; i++)
      i == 120
          ? '<p id="part2">Part two begins with paragraph $i.</p>'
          : '<p>Paragraph $i ${List<String>.filled(28, 'word$i').join(' ')}.</p>',
  ].join(),
);

void _localLibraryJourney() {
  testWidgets(
    '3. local library: several formats at once, refusals explained, rename, '
    'delete, restart and resume without any network access',
    (tester) async {
      reader.useSurface(tester);
      final guard = _NoNetworkClient();
      LibraryHttp.instance = LibraryHttp(client: guard);
      LibraryImageCache.instance = LibraryImageCache(
        fetcher: (request, {mode = LibraryFetchMode.cacheFirst, cancel}) =>
            LibraryHttp.instance.send(request, mode: mode, cancel: cancel),
      );
      final idleTimeout = LibraryArchivePages.idleTimeout;
      LibraryArchivePages.idleTimeout = Duration.zero;
      addTearDown(() => LibraryArchivePages.idleTimeout = idleTimeout);

      final comicPages = <Uint8List>[
        for (var i = 1; i <= 12; i++) buildPng(4 + i, 6, red: (i * 20) & 0xFF),
      ];
      final epubBytes = buildEpub3(
        title: 'Le Long Roman',
        chapter1: _longChapter(),
        cover: buildPng(400, 600),
      );
      final text = List<String>.generate(
        80,
        (i) => 'Paragraphe $i ${List<String>.filled(12, 'mot$i').join(' ')}',
      ).join('\n\n');

      late Directory root;
      late Directory picks;
      late LibraryLocalRoots roots;
      var tick = 1000;
      LibraryLocalLibraryService newLibrary() => LibraryLocalLibraryService(
        roots: () async => roots,
        inspector: LibraryFileBookInspector(pdfInspector: FakePdfInspector()),
        thumbnailer: const LibraryEngineThumbnailer(),
        clock: () => tick += 1000,
      );
      LibraryReadingStore newStore() => LibraryReadingStore(
        directory: Directory(roots.supportLibrary),
        saveDelay: const Duration(milliseconds: 5),
      );

      late LibraryLocalLibraryService library;
      late LibraryReadingStore store;
      late List<LibraryImportOutcome> outcomes;
      late List<LibraryImportOutcome> second;
      final progress = <LibraryImportProgress>[];
      final importWatch = Stopwatch();
      late String novelPick;
      late String pdfPick;
      await tester.runAsync(() async {
        root = await Directory.systemTemp.createTemp('ns_e2e_local_');
        picks = Directory(p.join(root.path, 'picks'))..createSync();
        roots = LibraryLocalRoots(
          documentsLibrary: p.join(root.path, 'Documents', 'Library'),
          supportLibrary: p.join(root.path, 'Support', 'Library'),
        );
        library = newLibrary();
        store = newStore();
        await store.load();
        Future<String> pick(String name, List<int> bytes) async =>
            (await writeFile(picks, name, bytes)).path;
        novelPick = await pick('novel.epub', epubBytes);
        pdfPick = await pick('paper.pdf', buildPdf(pages: 3));
        final rightStory = await pick(
          p.join('right', 'story.txt'),
          utf8.encode('Droite\n\nUne autre histoire.'),
        );
        final sources = <String>[
          novelPick,
          await pick(
            'comic.cbz',
            buildCbz(pages: 12, pageBytes: (page) => comicPages[page - 1]),
          ),
          await pick('notes.txt', utf8.encode(text)),
          pdfPick,
          await pick('novel copy.epub', epubBytes),
          await pick(
            p.join('left', 'story.txt'),
            utf8.encode('Gauche\n\nUne histoire.'),
          ),
          rightStory,
          // file_picker copies every pick to tmp/<name>: two picks with one
          // name arrive as the same path twice.
          rightStory,
          await pick(
            'locked.epub',
            buildEpub3(
              title: 'Verrouillé',
              extra: <FixtureZipEntry>[
                FixtureZipEntry.text('META-INF/rights.xml', '<rights/>'),
              ],
            ),
          ),
          await pick('scan.cbr', buildRar()),
          await pick('empty.epub', const <int>[]),
          await pick(
            'garbage.bin',
            List<int>.generate(4096, (i) => (i * 31 + 7) & 0xFF),
          ),
        ];
        importWatch.start();
        outcomes = await library.importFiles(sources, onProgress: progress.add);
        importWatch.stop();
        second = await library.importFiles(<String>[novelPick]);
      });
      addTearDown(() => _deleteQuietly(root));

      expect(
        outcomes.map((outcome) => outcome.issue).toList(),
        <LibraryBookIssue?>[
          null,
          null,
          null,
          null,
          LibraryBookIssue.duplicateInSelection,
          null,
          null,
          LibraryBookIssue.sameNameInSelection,
          LibraryBookIssue.drmProtected,
          LibraryBookIssue.rarArchive,
          LibraryBookIssue.emptyFile,
          LibraryBookIssue.unsupportedFormat,
        ],
      );
      final imported = <LibraryLocalBook>[
        for (final outcome in outcomes)
          if (outcome.imported) outcome.book!,
      ];
      expect(imported.map((book) => book.relativePath), <String>[
        'Books/novel.epub',
        'Books/comic.cbz',
        'Books/notes.txt',
        'Books/paper.pdf',
        'Books/story.txt',
        'Books/story (2).txt',
      ]);
      final novel = imported[0];
      final comic = imported[1];
      final notes = imported[2];
      final paper = imported[3];
      expect(outcomes[4].duplicateOf!.id, novel.id);
      expect(second.single.issue, LibraryBookIssue.duplicate);
      expect(second.single.duplicateOf!.id, novel.id);
      expect(progress.last.fraction, 1.0);
      expect(novel.format, LibraryBookFormat.epub);
      expect(novel.title, 'Le Long Roman');
      expect(novel.authors, contains('Ada Lovelace'));
      expect(novel.hasCover, isTrue);
      expect(comic.format, LibraryBookFormat.cbz);
      expect(comic.title, 'The Duel');
      expect(comic.rightToLeft, isTrue);
      expect(paper.pageCount, 3);
      expect(notes.hasCover, isFalse);
      final coverSize = pngSize(
        File(library.coverPath(novel)!).readAsBytesSync(),
      );
      expect(coverSize, (360, 540), reason: 'thumbnail at display size');

      // Rename, then delete the PDF: only NeoStation's copy goes.
      late LibraryLocalBook? renamed;
      late LibraryDeleteResult deleted;
      await tester.runAsync(() async {
        renamed = await library.rename(novel.id, 'Mon roman préféré');
        deleted = await library.delete(paper.id);
      });
      expect(renamed!.title, 'Mon roman préféré');
      expect(deleted, LibraryDeleteResult.deleted);
      expect(
        File(p.join(roots.booksDirectory, 'paper.pdf')).existsSync(),
        isFalse,
      );
      expect(File(pdfPick).existsSync(), isTrue, reason: 'the original stays');
      expect(
        File(p.join(roots.coversDirectory, '${paper.id}.png')).existsSync(),
        isFalse,
      );
      expect(library.books, hasLength(5));

      // EPUB: read with the app's reader, a few pages down, then closed.
      // The 440 continuous scroll (the default text layout is pages): the
      // setting is saved, so the relaunched store below keeps it.
      store.updateSettings(
        store.settings.copyWith(textLayout: LibraryTextLayout.scroll),
      );
      LibraryReadingStore.instance = store;
      await reader.pumpReader(
        tester,
        LibraryReaderLauncher.readerForLocalBook(
          library.bookById(novel.id)!,
          library.absolutePath(novel),
        ),
      );
      await reader.settle(tester);
      var state = tester.state<LibraryBookReaderScreenState>(
        find.byType(LibraryBookReaderScreen),
      );
      expect(state.currentPosition!.chapter, 0);
      for (var i = 0; i < 5; i++) {
        state.gamepadBindings.right!();
        await reader.frames(tester);
      }
      await reader.settle(tester, rounds: 2);
      final reached = state.currentPosition!;
      expect(reached.chapter, 0);
      expect(reached.block, greaterThan(10));
      state.gamepadBindings.back!();
      await reader.frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      await reader.settle(tester, rounds: 2);
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      final savedCfi = store.progressFor(novel.readingKey)!.location;
      expect(savedCfi, startsWith('epubcfi(/6/2[ch1]!'));

      // CBZ through the page reader's logic; TXT position as the book
      // reader records it.
      await tester.runAsync(() async {
        final controller = LibraryPageReaderController(
          content: LibraryArchiveReaderContent(
            path: library.absolutePath(comic),
            title: comic.title,
            progressKey: comic.readingKey,
            rightToLeft: comic.rightToLeft,
          ),
          store: store,
          saveDelay: const Duration(milliseconds: 1),
        );
        await controller.start();
        expect(controller.status, LibraryPageReaderStatus.ready);
        expect(controller.pageCount, 12);
        expect(controller.rightToLeft, isTrue);
        controller.setPage(7);
        controller.dispose();
        final document = await LibraryTextDocument.open(
          library.absolutePath(notes),
        );
        store.saveProgress(
          LibraryReadingProgress(
            key: notes.readingKey,
            location: document.locationFor(40, 12),
            fraction: document.fractionFor(40, 12),
            title: notes.title,
          ),
        );
      });
      // The reader wrote through the store in the test's fake zone: its
      // pending write is drained with frames (as the reader tests do).
      await reader.flushStore(tester, store);

      // "Restart": new service and store instances on the same folders.
      late LibraryLocalLibraryService relaunched;
      late LibraryReadingStore relaunchedStore;
      await tester.runAsync(() async {
        relaunched = newLibrary();
        await relaunched.load();
        relaunchedStore = newStore();
        await relaunchedStore.load();
      });
      expect(
        relaunched.books.map((book) => book.id).toSet(),
        library.books.map((book) => book.id).toSet(),
      );
      expect(relaunched.books, hasLength(5));
      expect(relaunched.bookById(paper.id), isNull);
      expect(relaunched.bookById(novel.id)!.title, 'Mon roman préféré');
      expect(relaunched.bookById(novel.id)!.customTitle, 'Mon roman préféré');
      expect(relaunched.bookById(novel.id)!.hasCover, isTrue);
      expect(relaunchedStore.progressFor(novel.readingKey)!.location, savedCfi);
      expect(relaunchedStore.progressFor(comic.readingKey)!.pageIndex, 7);

      // The font size changes, then the EPUB opens at the same block.
      relaunchedStore.updateSettings(
        relaunchedStore.settings.copyWith(fontSize: 28),
      );
      LibraryReadingStore.instance = relaunchedStore;
      final novelAgain = relaunched.bookById(novel.id)!;
      await reader.pumpReader(
        tester,
        LibraryReaderLauncher.readerForLocalBook(
          novelAgain,
          relaunched.absolutePath(novelAgain),
        ),
      );
      await reader.settle(tester);
      state = tester.state<LibraryBookReaderScreenState>(
        find.byType(LibraryBookReaderScreen),
      );
      final reopenedAt28 = state.currentPosition!;
      expect(reopenedAt28.chapter, reached.chapter);
      expect(reopenedAt28.block, reached.block);
      relaunchedStore.updateSettings(
        relaunchedStore.settings.copyWith(fontSize: 14),
      );
      await tester.pump();
      await tester.pump();
      final resizedTo14 = state.currentPosition!;
      expect(resizedTo14.block, reached.block);
      state.gamepadBindings.back!();
      await reader.frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      await reader.settle(tester, rounds: 2);
      final cfiAfterFontChanges = relaunchedStore
          .progressFor(novel.readingKey)!
          .location;
      await reader.flushStore(tester, relaunchedStore);

      late List<int> comicResumedAt;
      late ({int blockIndex, int charOffset})? textAt;
      late double savedFontSize;
      await tester.runAsync(() async {
        final document = await LibraryEpubDocument.open(
          relaunched.absolutePath(novelAgain),
        );
        try {
          final first = (await document.resolveCfi(savedCfi))!;
          final after = (await document.resolveCfi(cfiAfterFontChanges))!;
          expect(first.spineIndex, reached.chapter);
          expect(first.blockIndex, reached.block);
          expect(after.spineIndex, reached.chapter);
          expect(after.blockIndex, reached.block);
          expect(document.toc.map((entry) => entry.title), <String>[
            'Chapter One',
            'Chapter Two',
          ]);
          expect(document.toc.first.children.single.title, 'Part Two');
        } finally {
          await document.close();
        }

        final comicAgain = relaunched.bookById(comic.id)!;
        comicResumedAt = <int>[];
        await _openComic(
          relaunched.absolutePath(comicAgain),
          comicAgain,
          relaunchedStore,
          (controller) => comicResumedAt.add(controller.page),
        );
        final pages = await LibraryArchivePages.open(
          relaunched.absolutePath(comicAgain),
        );
        try {
          expect(pages.pageCount, 12);
          expect(pages.pageNames.first, endsWith('page1.jpg'));
          expect(pages.pageNames.last, endsWith('page12.jpg'));
          expect(await pages.page(0), comicPages.first);
          expect(await pages.page(11), comicPages.last);
        } finally {
          await pages.close();
        }

        final notesAgain = relaunched.bookById(notes.id)!;
        final document2 = await LibraryTextDocument.open(
          relaunched.absolutePath(notesAgain),
        );
        textAt = document2.parseLocation(
          relaunchedStore.progressFor(notesAgain.readingKey)!.location,
        );
        final thirdLaunch = newStore();
        await thirdLaunch.load();
        savedFontSize = thirdLaunch.settings.fontSize;
      });
      expect(comicResumedAt, <int>[7]);
      expect(textAt, (blockIndex: 40, charOffset: 12));
      expect(savedFontSize, 14);
      expect(guard.requests, isEmpty, reason: 'no network access at all');
      _report('journey3-local-library', <String, Object?>{
        'files': outcomes.length,
        'imported': imported.length,
        'refused': <String, String>{
          for (final outcome in outcomes)
            if (!outcome.imported) outcome.sourceName: outcome.issue!.name,
        },
        'importMs': importWatch.elapsedMilliseconds,
        'epubBlockReached': reached.block,
        'epubPositionReached': '$reached',
        'epubSavedCfi': savedCfi,
        'epubReopenedAfterRestartAtFont28': '$reopenedAt28',
        'epubAfterChangeToFont14': '$resizedTo14',
        'epubCfiAfterFontChanges': cfiAfterFontChanges,
        'cbzResumedPage': comicResumedAt.single,
        'networkRequests': guard.requests.length,
      });
    },
  );
}

Future<void> _openComic(
  String path,
  LibraryLocalBook book,
  LibraryReadingStore store,
  void Function(LibraryPageReaderController controller) onReady,
) async {
  final controller = LibraryPageReaderController(
    content: LibraryArchiveReaderContent(
      path: path,
      title: book.title,
      progressKey: book.readingKey,
      rightToLeft: book.rightToLeft,
    ),
    store: store,
    saveDelay: const Duration(milliseconds: 1),
  );
  try {
    await controller.start();
    expect(controller.status, LibraryPageReaderStatus.ready);
    onReady(controller);
  } finally {
    controller.dispose();
  }
}

// ---------------------------------------------------------------------------
// 4. Slow network and unavailable sources
// ---------------------------------------------------------------------------

LibraryAddon _addon(String sourceId, String name, {int contentRating = 0}) {
  return LibraryAddon.fromManifest(
    LibraryAddon.aidokuSourceManifest(
      sourceId: sourceId,
      name: name,
      version: '1',
      languages: const <String>['fr'],
      contentRating: contentRating,
      repositoryOrigin: _frenchIndex,
      fallbackBaseUrl: _frenchDirectory,
    ),
    origin: _frenchIndex,
    installedAt: DateTime.utc(2026, 10, 11),
  );
}

void _slowNetworkJourney() {
  test('4. slow network: the fast source is shown first, unavailable sources '
      'are reported with their kind, the cache is served stale offline', () async {
    final root = await Directory.systemTemp.createTemp('ns_e2e_slow_');
    addTearDown(() => _deleteQuietly(root));
    final caches = Directory(p.join(root.path, 'Caches', 'Library'));
    final clock = _Clock(DateTime.utc(2026, 10, 11, 9));
    final transport = _FixtureTransport()
      ..onGet(_sushiListing, fixture: 'sushiscan_catalogue_update_p1.html')
      ..onGet(
        '$_lelscan/',
        fixture: 'lelscan_home_p1.html',
        delay: const Duration(seconds: 5),
      )
      ..onPost(
        _moAjax,
        form: const <String, String>{'action': 'madara_load_more'},
        fixture: 'cloudflare_challenge_403.html',
        status: 403,
        headers: const <String, String>{'cf-mitigated': 'challenge'},
      )
      // What dart:io raises when a connection attempt times out.
      ..onGet(
        _sushiScansListing,
        delay: const Duration(milliseconds: 50),
        error: const SocketException('Connection timed out'),
      );
    final sushi = _addon('fr.sushiscan', 'SushiScan');
    final lelscan = _addon('fr.lelscanfr', 'LelscanFR');
    final origines = _addon('fr.mangasorigines', 'Mangas Origines');
    final sushiScans = _addon('fr.sushiscans', 'Sushi Scans');
    final scantrad = _addon(
      'fr.mangascantrad',
      'Manga Scantrad',
      contentRating: 1,
    );
    final addons = <LibraryAddon>[
      sushi,
      lelscan,
      origines,
      sushiScans,
      scantrad,
    ];

    final firstLaunch = LibraryHttp(
      client: transport,
      cacheDirectory: caches,
      clock: clock.call,
    );
    final feed = LibraryCatalogFeed(
      backend: LibraryCatalogFeedBackend(
        aidoku: LibraryAidokuNativeService(
          fetcher: firstLaunch.send,
          clock: clock.call,
        ),
      ),
      clock: clock.call,
    );
    addTearDown(feed.dispose);
    final watch = Stopwatch()..start();
    final shownAt = <String, int>{};
    final failedAt = <String, int>{};
    feed.addListener(() {
      for (final source in feed.sources) {
        if (source.entryCount > 0) {
          shownAt.putIfAbsent(source.key, () => watch.elapsedMilliseconds);
        }
        if (source.failure != null) {
          failedAt.putIfAbsent(source.key, () => watch.elapsedMilliseconds);
        }
      }
    });
    final opening = feed.open(addons);
    await _waitFor(() => (feed.source(sushi.id)?.entryCount ?? 0) > 0);
    final fastShownMs = watch.elapsedMilliseconds;
    expect(feed.source(lelscan.id)!.loading, isTrue);
    expect(feed.source(lelscan.id)!.entryCount, 0);
    await opening;
    final openMs = watch.elapsedMilliseconds;

    // Real time: generous bounds, all well before the slow source's 5 s.
    expect(fastShownMs, lessThan(4000));
    expect(shownAt[lelscan.id], greaterThanOrEqualTo(5000));
    expect(shownAt[sushi.id]!, lessThan(shownAt[lelscan.id]!));
    expect(failedAt[origines.id], lessThan(4000));
    expect(failedAt[sushiScans.id], lessThan(4000));
    final challenge = feed.source(origines.id)!.failure!;
    expect(challenge.issue, LibraryFeedIssue.challenge);
    expect(challenge.statusCode, 403);
    expect(challenge.known, isFalse);
    final timeout = feed.source(sushiScans.id)!.failure!;
    expect(timeout.issue, LibraryFeedIssue.timeout);
    final known = feed.source(scantrad.id)!.failure!;
    expect(known.issue, LibraryFeedIssue.challenge);
    expect(known.known, isTrue);
    expect(
      feed.unavailableSources.map((source) => source.key).toSet(),
      <String>{origines.id, sushiScans.id, scantrad.id},
    );
    expect(transport.to('manga-scantrad.io'), isEmpty);
    expect(feed.entries, hasLength(6));
    expect(feed.allSourcesFailed, isFalse);
    final unavailable = <String, String>{
      for (final source in feed.unavailableSources)
        source.key:
            '${source.failure!.issue.name}'
            '${source.failure!.known ? ' (verified state, not requested)' : ''}'
            '${source.failure!.statusCode == null ? '' : ' HTTP ${source.failure!.statusCode}'}',
    };

    // The connection drops: a manual refresh keeps every title shown.
    transport.offline = true;
    clock.advance(const Duration(minutes: 20));
    await feed.refresh();
    expect(feed.entries, hasLength(6));
    expect(feed.source(sushi.id)!.failure!.issue, LibraryFeedIssue.offline);
    expect(feed.source(lelscan.id)!.failure!.issue, LibraryFeedIssue.offline);
    final staleAfterRefresh = <String, bool>{
      for (final source in <LibraryAddon>[sushi, lelscan])
        source.id: feed.source(source.id)!.entryCount == 3,
    };
    await firstLaunch.idle();
    firstLaunch.close();

    // Relaunch offline: the cached listings are served marked stale.
    final relaunch = LibraryHttp(
      client: transport,
      cacheDirectory: caches,
      clock: clock.call,
    );
    addTearDown(relaunch.close);
    final native = LibraryAidokuNativeService(
      fetcher: relaunch.send,
      clock: clock.call,
    );
    final stalePage = await native.loadCatalogPage(sushi);
    expect(stalePage.items.map((item) => item.id), <String>[
      'black-clover',
      'kingdom',
      '1-blue-lock',
    ]);
    expect(stalePage.stale, isTrue);
    expect(stalePage.fromCache, isTrue);
    final offlineFeed = LibraryCatalogFeed(
      backend: LibraryCatalogFeedBackend(aidoku: native),
      clock: clock.call,
    );
    addTearDown(offlineFeed.dispose);
    await offlineFeed.open(addons);
    for (final source in <LibraryAddon>[sushi, lelscan]) {
      final state = offlineFeed.source(source.id)!;
      expect(state.entryCount, 3, reason: source.id);
      expect(state.fromCache, isTrue, reason: source.id);
      expect(state.stale, isTrue, reason: source.id);
      expect(state.failure!.issue, LibraryFeedIssue.offline);
    }
    expect(offlineFeed.source(origines.id)!.entryCount, 0);
    expect(
      offlineFeed.source(origines.id)!.failure!.issue,
      LibraryFeedIssue.offline,
    );
    await offlineFeed.refresh();
    expect(offlineFeed.entries, hasLength(6));
    expect(transport.unexpected, isEmpty);
    _report('journey4-slow-network', <String, Object?>{
      'fastSourceShownMs': fastShownMs,
      'slowSourceShownMs': shownAt[lelscan.id],
      'challengeReportedMs': failedAt[origines.id],
      'timeoutReportedMs': failedAt[sushiScans.id],
      'openCompletedMs': openMs,
      'unavailable': unavailable,
      'offlineEntriesAfterRefresh': feed.entries.length,
      'titlesKeptPerSourceAfterOfflineRefresh': staleAfterRefresh,
      'relaunchStaleEntries': offlineFeed.entries.length,
      'relaunchHttp': relaunch.stats.toJson(),
    });
  }, timeout: const Timeout(Duration(minutes: 2)));
}

// ---------------------------------------------------------------------------
// 5. Large catalogue
// ---------------------------------------------------------------------------

const String _bigIndexUrl = 'https://catalog.example.org/big/index.min.json';
const String _bigLegacyUrl = 'https://catalog.example.org/old/index.min.json';

Uint8List _syntheticIndex(int count) => Uint8List.fromList(
  utf8.encode(
    jsonEncode(<String, dynamic>{
      'name': 'Synthetic catalogue',
      'sources': <Map<String, dynamic>>[
        for (var i = 0; i < count; i++)
          <String, dynamic>{
            'id': 'fr.synthetic${i.toString().padLeft(4, '0')}',
            'name': 'Synthetic source ${i.toString().padLeft(4, '0')}',
            'version': 1 + i % 7,
            'iconURL': 'icons/fr.synthetic$i-v1.png',
            'downloadURL': 'sources/fr.synthetic$i-v1.aix',
            'languages': <String>['fr', 'en'],
            'contentRating': i % 3,
            'baseURL': 'https://synthetic$i.example.org',
            'altNames': <String>['Alt $i'],
          },
      ],
    }),
  ),
);

Uint8List _syntheticLegacyIndex(int count) => Uint8List.fromList(
  utf8.encode(
    jsonEncode(<Map<String, dynamic>>[
      for (var i = 0; i < count; i++)
        <String, dynamic>{
          'id': 'fr.legacy${i.toString().padLeft(4, '0')}',
          'name': 'Legacy source $i',
          'file': 'fr.legacy$i-v1.aix',
          'icon': 'fr.legacy$i-v1.png',
          'lang': 'fr',
          'version': 1,
          'nsfw': i % 2,
        },
    ]),
  ),
);

/// Source rows in the element tree: on screen, or [offstage] too (the rows
/// kept in the list's cache extent).
int _builtRows({bool offstage = true}) => find
    .byWidgetPredicate((widget) {
      final key = widget.key;
      return key is ValueKey<String> && key.value.startsWith('entry-');
    }, skipOffstage: !offstage)
    .evaluate()
    .length;

void _largeCatalogueJourney() {
  test(
    '5a. a 3000-source catalogue is parsed within a generous bound',
    () async {
      final modern = _syntheticIndex(3000);
      final legacy = _syntheticLegacyIndex(3000);
      final fetcher =
          catalog_fakes.FakeLibraryFetcher(<String, catalog_fakes.FakeRoute>{
            _bigIndexUrl: catalog_fakes.FakeRoute.bytes(modern),
            _bigLegacyUrl: catalog_fakes.FakeRoute.bytes(legacy),
          });
      final addons = LibraryAddonService.forTesting();
      await addons.load();
      final service = LibrarySourceCatalogService(
        fetcher: fetcher.call,
        addons: addons,
        store: LibraryCatalogMemoryStore(),
      );
      final timings = <String, int>{};
      for (final (label, url) in <(String, String)>[
        ('modernFirst', _bigIndexUrl),
        ('modernSecond', _bigIndexUrl),
        ('legacyFirst', _bigLegacyUrl),
      ]) {
        final watch = Stopwatch()..start();
        final preview = await service.preview(url);
        watch.stop();
        timings[label] = watch.elapsedMilliseconds;
        expect(preview.sources, hasLength(3000), reason: label);
        expect(
          preview.sources.every((entry) => !entry.alreadyInstalled),
          isTrue,
        );
      }
      final last = (await service.preview(_bigIndexUrl)).sources.last;
      expect(last.id, 'fr.synthetic2999');
      expect(
        last.downloadUrl,
        'https://catalog.example.org/big/sources/fr.synthetic2999-v1.aix',
      );
      // Generous bounds: a PC parses this in well under a second; the bound
      // only catches an accidental quadratic step.
      expect(timings['modernFirst'], lessThan(15000));
      expect(timings['modernSecond'], lessThan(15000));
      expect(timings['legacyFirst'], lessThan(15000));
      _report('journey5-parse', <String, Object?>{
        'sources': 3000,
        'modernBytes': modern.length,
        'legacyBytes': legacy.length,
        'parseMs': timings,
      });
    },
  );

  testWidgets('5b. the preview screen builds only the rows on screen', (
    tester,
  ) async {
    late LibraryCatalogPreview preview;
    late LibrarySourceCatalogService service;
    await tester.runAsync(() async {
      final addons = LibraryAddonService.forTesting();
      await addons.load();
      service = LibrarySourceCatalogService(
        fetcher: catalog_fakes.FakeLibraryFetcher(
          <String, catalog_fakes.FakeRoute>{
            _bigIndexUrl: catalog_fakes.FakeRoute.bytes(_syntheticIndex(3000)),
          },
        ).call,
        addons: addons,
        store: LibraryCatalogMemoryStore(),
      );
      preview = await service.preview(_bigIndexUrl);
    });
    final icons = ui.NoImageCache();
    final watch = Stopwatch()..start();
    await ui.pumpLibraryUi(
      tester,
      LibraryCatalogPreviewScreen(
        preview: preview,
        catalogService: service,
        aidokuService: ui.FakeAidokuService(),
        imageCache: icons,
        enableGamepad: false,
      ),
      wrapInScaffold: false,
    );
    await tester.pump();
    watch.stop();
    final visibleAtOpen = _builtRows(offstage: false);
    final builtAtOpen = _builtRows();
    expect(visibleAtOpen, greaterThanOrEqualTo(1));
    expect(builtAtOpen, inInclusiveRange(visibleAtOpen, 40));
    expect(
      tester
          .widgetList<Checkbox>(find.byType(Checkbox, skipOffstage: false))
          .map((box) => box.value),
      everyElement(isFalse),
      reason: 'nothing pre-selected',
    );
    // One icon request per row built, none for the 2990 others.
    final iconLoadsAtOpen = icons.loads;
    expect(iconLoadsAtOpen, lessThanOrEqualTo(builtAtOpen));

    final scrollable = tester.state<ScrollableState>(
      find
          .descendant(
            of: find.byKey(const ValueKey<String>('preview-scroll')),
            matching: find.byType(Scrollable),
          )
          .first,
    );
    // Far down the list (about row 600): still only the rows on screen.
    // The rows have no fixed extent, so a jump lays out every row it passes
    // (measured: one jump across all 3000 rows took about 9.7 s in this
    // debug test VM); the journey stays at a distance a user scrolls to.
    final rowExtent = tester
        .getSize(find.byKey(ValueKey<String>('entry-${preview.sources[0].id}')))
        .height;
    final jumpWatch = Stopwatch()..start();
    scrollable.position.jumpTo(600 * rowExtent);
    await tester.pump();
    jumpWatch.stop();
    final farKeys = find
        .byWidgetPredicate((widget) {
          final key = widget.key;
          return key is ValueKey<String> && key.value.startsWith('entry-');
        })
        .evaluate()
        .map((element) => (element.widget.key! as ValueKey<String>).value)
        .toList();
    expect(farKeys, isNotEmpty);
    final farIndex = preview.sources.indexWhere(
      (entry) => 'entry-${entry.id}' == farKeys.first,
    );
    expect(farIndex, inInclusiveRange(550, 650));
    final builtFarDown = _builtRows();
    expect(builtFarDown, inInclusiveRange(1, 40));
    expect(icons.loads, lessThan(100), reason: 'icons only for built rows');
    await tester.tap(find.byKey(ValueKey<String>(farKeys.first)));
    await tester.pump();
    expect(find.text('Activate (1)'), findsOneWidget);
    _report('journey5-preview-screen', <String, Object?>{
      'sources': preview.sources.length,
      'rowsOnScreenAtOpen': visibleAtOpen,
      'rowsBuiltAtOpen': builtAtOpen,
      'rowExtentPx': rowExtent,
      'firstRowShownAfterJump': farIndex,
      'rowsBuiltAfterJump': builtFarDown,
      'jumpOf600RowsMs': jumpWatch.elapsedMilliseconds,
      'iconLoadsAtOpen': iconLoadsAtOpen,
      'iconLoadsTotal': icons.loads,
      'firstFrameMs': watch.elapsedMilliseconds,
    });
  });
}

// ---------------------------------------------------------------------------
// 6. Hub: refresh, title page, section and tab switch keep the position
// ---------------------------------------------------------------------------

/// SushiScan latest listing (MangaThemesia markup) with [titles], one page.
String _themesiaListing(List<String> titles) {
  final buffer = StringBuffer(
    '<!DOCTYPE html><html><head><title>Manga - Sushiscan</title></head>'
    '<body><div class="listupd">',
  );
  for (final title in titles) {
    final slug = title.toLowerCase();
    buffer.write(
      '<div class="bs"><div class="bsx">'
      '<a href="https://sushiscan.net/catalogue/$slug/" title="$title">'
      '<div class="limit"><span class="typename Manga">Manga</span></div>'
      '<div class="bigor"><div class="tt">$title</div></div></a>'
      '</div></div>',
    );
  }
  buffer.write('</div></body></html>');
  return buffer.toString();
}

/// LibraryFetcher serving the SushiScan listing from [body] (no HTTP cache:
/// cacheOnly requests miss, as on a first launch).
class _ListingFetcher {
  _ListingFetcher(this.body);

  String Function() body;
  final List<LibraryFetchMode> modes = <LibraryFetchMode>[];

  Future<LibraryHttpResponse> call(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    modes.add(mode);
    if (request.uri.toString() != _sushiListing) {
      throw StateError('unexpected request ${request.uri}');
    }
    if (mode == LibraryFetchMode.cacheOnly) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.notFound,
        uri: request.uri,
        detail: 'cache-miss',
      );
    }
    return LibraryHttpResponse(
      request: request,
      statusCode: 200,
      bodyBytes: Uint8List.fromList(utf8.encode(body())),
      headers: const <String, String>{
        'content-type': 'text/html; charset=UTF-8',
      },
      finalUri: request.uri,
      fetchedAt: DateTime.utc(2026, 10, 11, 12),
    );
  }
}

class _SectionDelegate implements LibraryGamepadViewDelegate {
  bool backResult = true;

  @override
  bool navigate(int dx, int dy) => true;

  @override
  bool activate() => true;

  @override
  bool back() => backResult;

  @override
  bool secondary() => true;
}

class _FakeSection extends StatefulWidget {
  const _FakeSection({
    required this.section,
    required this.controller,
    required this.delegate,
  });

  final LibraryHubSection section;
  final LibraryGamepadViewController controller;
  final _SectionDelegate delegate;

  @override
  State<_FakeSection> createState() => _FakeSectionState();
}

class _FakeSectionState extends State<_FakeSection> {
  @override
  void initState() {
    super.initState();
    widget.controller.attach(widget.delegate);
  }

  @override
  void dispose() {
    widget.controller.detach(widget.delegate);
    super.dispose();
  }

  @override
  Widget build(BuildContext context) => Text('section:${widget.section.name}');
}

void _hubPositionJourney() {
  group('6. hub', () {
    setUpAll(() async {
      SharedPreferences.setMockInitialValues(<String, Object>{});
      await FlutterLocalization.instance.ensureInitialized();
      FlutterLocalization.instance.init(
        mapLocales: [const MapLocale('en', AppLocale.en)],
        initLanguageCode: 'en',
      );
    });

    testWidgets(
      'a cache refresh, a title page, a section and a tab switch keep the '
      'reading position in the catalogue',
      (tester) async {
        TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
            .setMockMethodCallHandler(
              const MethodChannel('xyz.luan/gamepads'),
              (call) async => <dynamic>[],
            );
        String name(String prefix, int i) =>
            '$prefix${i.toString().padLeft(2, '0')}';
        var titles = <String>[for (var i = 0; i < 60; i++) name('T', i)];
        final fetcher = _ListingFetcher(() => _themesiaListing(titles));
        final clock = _Clock(DateTime.utc(2026, 10, 11, 12));
        final feed = LibraryCatalogFeed(
          backend: LibraryCatalogFeedBackend(
            aidoku: LibraryAidokuNativeService(
              fetcher: fetcher.call,
              clock: clock.call,
            ),
          ),
          clock: clock.call,
          loadMoreThrottle: Duration.zero,
        );
        addTearDown(feed.dispose);
        final sushi = _addon('fr.sushiscan', 'SushiScan');
        final delegate = _SectionDelegate();
        final opened = <String>[];
        Widget hub() => ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (context, child) => MaterialApp(
            theme: ThemeData(extensions: [ChromeSurface.standard()]),
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: Scaffold(
              body: LibraryScreen(
                feed: feed,
                loadAddons: () async => <LibraryAddon>[sushi],
                enableSounds: false,
                openOnlineTitle:
                    (context, {required item, addon, aidokuSourceId}) async {
                      opened.add(item.title);
                      await Navigator.of(context).push(
                        MaterialPageRoute<void>(
                          builder: (_) =>
                              Scaffold(body: Text('page of ${item.title}')),
                        ),
                      );
                    },
                sectionBuilder: (context, section, controller, onBack) =>
                    _FakeSection(
                      section: section,
                      controller: controller,
                      delegate: delegate,
                    ),
              ),
            ),
          ),
        );
        tester.view.physicalSize = const Size(1280, 720);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(hub());
        await tester.pump();
        await tester.pump();
        await tester.pump();
        LibraryScreenState stateOf() =>
            tester.state<LibraryScreenState>(find.byType(LibraryScreen));
        expect(stateOf().visibleEntries, hasLength(60));
        expect(fetcher.modes, <LibraryFetchMode>[
          LibraryFetchMode.cacheOnly,
          LibraryFetchMode.cacheFirst,
        ]);

        await tester.drag(
          find.byType(CustomScrollView),
          const Offset(0, -1400),
        );
        await tester.pumpAndSettle();
        String probe() {
          for (final title in titles) {
            final finder = find.text(title);
            if (finder.evaluate().length != 1) continue;
            final y = tester.getTopLeft(finder).dy;
            if (y > 150 && y < 600) return title;
          }
          fail('no title card in the middle of the viewport');
        }

        final anchor = probe();
        // The card itself (its border thickens when it is selected, which
        // moves its text by a pixel or two without any scrolling).
        final card = find.byKey(
          ValueKey<String>('${sushi.id}|${anchor.toLowerCase()}'),
        );
        double cardY() => tester.getTopLeft(card).dy;
        final anchorY = cardY();
        final measured = <String, double>{'scrolled': anchorY};

        // 1) A refresh brings 12 titles that sort above the one in view.
        titles = <String>[for (var i = 0; i < 12; i++) name('A', i), ...titles];
        final refreshing = feed.refresh();
        await tester.pump();
        await tester.pump();
        await tester.runAsync(() => refreshing);
        await tester.pump();
        expect(stateOf().visibleEntries, hasLength(72));
        expect(stateOf().visibleEntries.first.item.title, 'A00');
        measured['afterRefresh'] = cardY();
        expect(measured['afterRefresh'], closeTo(anchorY, 1));

        // 2) The title page opens over the hub and closes again.
        await tester.tap(find.text(anchor));
        await tester.pumpAndSettle();
        expect(opened, <String>[anchor]);
        expect(find.text('page of $anchor'), findsOneWidget);
        Navigator.of(tester.element(find.text('page of $anchor'))).pop();
        await tester.pumpAndSettle();
        measured['afterTitlePage'] = cardY();
        expect(measured['afterTitlePage'], closeTo(anchorY, 1));

        // 3) Tab switch: the app replaces LibraryScreen; more titles arrive
        // meanwhile.
        await tester.pumpWidget(const SizedBox.shrink());
        titles = <String>[for (var i = 0; i < 6; i++) name('B', i), ...titles];
        await tester.runAsync(feed.refresh);
        await tester.pump();
        await tester.pumpWidget(hub());
        await tester.pump();
        await tester.pump();
        expect(stateOf().visibleEntries, hasLength(78));
        expect(find.text(anchor), findsOneWidget);
        measured['afterTabSwitch'] = cardY();
        expect(measured['afterTabSwitch'], closeTo(anchorY, 1));

        // 4) A section opened from the shortcut cards, then back.
        ScrollableState scrollable() =>
            tester.state<ScrollableState>(find.byType(Scrollable).first);
        scrollable().position.jumpTo(90);
        await tester.pump();
        final beforeSection = scrollable().position.pixels;
        await tester.tap(find.text('Favorites & reading'));
        await tester.pump();
        expect(find.text('section:favorites'), findsOneWidget);
        delegate.backResult = false;
        LibraryScreen.backCurrent();
        await tester.pump();
        await tester.pump();
        expect(find.text('section:favorites'), findsNothing);
        final afterSection = scrollable().position.pixels;
        expect(afterSection, closeTo(beforeSection, 1));
        expect(
          fetcher.modes.where((mode) => mode == LibraryFetchMode.refresh),
          hasLength(2),
          reason: 'only the two refreshes asked the site again',
        );
        _report('journey6-hub-position', <String, Object?>{
          'anchor': anchor,
          'anchorY': measured,
          'titles': stateOf().visibleEntries.length,
          'sectionOffset': <String, double>{
            'before': beforeSection,
            'after': afterSection,
          },
          'requests': fetcher.modes.map((mode) => mode.name).toList(),
        });
      },
    );
  });
}

// ---------------------------------------------------------------------------
// Shared doubles and helpers
// ---------------------------------------------------------------------------

class _Clock {
  _Clock(this.now);

  DateTime now;

  DateTime call() => now;

  void advance(Duration duration) => now = now.add(duration);
}

class _Reply {
  _Reply({
    required this.body,
    this.status = 200,
    this.headers = const <String, String>{},
    this.delay = Duration.zero,
    this.error,
  });

  final Uint8List body;
  final int status;
  final Map<String, String> headers;
  final Duration delay;
  final Object? error;
}

class _Route {
  _Route(this.method, this.url, this.reply, {this.form});

  final String method;
  final String url;
  final _Reply reply;

  /// When set, a POST matches only when its form contains these entries.
  final Map<String, String>? form;

  bool matches(String method, String url, Map<String, String>? sent) {
    if (method != this.method || url != this.url) return false;
    final expected = form;
    if (expected == null) return true;
    final actual = sent ?? const <String, String>{};
    return expected.entries.every((entry) => actual[entry.key] == entry.value);
  }
}

/// One request received by [_FixtureTransport].
class _Exchange {
  _Exchange(this.method, this.url, this.headers, this.form, this.at);

  final String method;
  final String url;
  final Map<String, String> headers;
  final Map<String, String>? form;
  final Duration at;

  String? header(String name) {
    for (final entry in headers.entries) {
      if (entry.key.toLowerCase() == name.toLowerCase()) return entry.value;
    }
    return null;
  }
}

class _UrlResponse extends http.StreamedResponse
    implements http.BaseResponseWithUrl {
  _UrlResponse(
    super.stream,
    super.statusCode, {
    required this.url,
    super.headers,
    super.contentLength,
  });

  @override
  final Uri url;
}

/// HTTP transport placed under the real [LibraryHttp]: answers from the
/// fixtures, serves a tiny PNG for any image path, and can simulate a slow
/// answer, a connection error or the device going offline. Requests without
/// a route are recorded in [unexpected] and answered 404.
class _FixtureTransport extends http.BaseClient {
  final List<_Route> _routes = <_Route>[];
  final List<_Exchange> exchanges = <_Exchange>[];
  final List<String> unexpected = <String>[];
  final Stopwatch _since = Stopwatch()..start();
  final Uint8List image = buildPng(6, 9);
  bool offline = false;

  static final RegExp _imagePath = RegExp(
    r'\.(jpe?g|png|webp|gif)$',
    caseSensitive: false,
  );

  void onGet(
    String url, {
    String? fixture,
    String? file,
    Uint8List? bytes,
    int status = 200,
    Map<String, String> headers = const <String, String>{},
    Duration delay = Duration.zero,
    Object? error,
  }) => _routes.add(
    _Route(
      'GET',
      url,
      _reply(fixture, file, bytes, status, headers, delay, error),
    ),
  );

  void onPost(
    String url, {
    Map<String, String>? form,
    String? fixture,
    int status = 200,
    Map<String, String> headers = const <String, String>{},
  }) => _routes.add(
    _Route(
      'POST',
      url,
      _reply(fixture, null, null, status, headers, Duration.zero, null),
      form: form,
    ),
  );

  _Reply _reply(
    String? fixture,
    String? file,
    Uint8List? bytes,
    int status,
    Map<String, String> headers,
    Duration delay,
    Object? error,
  ) {
    final Uint8List body;
    if (bytes != null) {
      body = bytes;
    } else if (fixture != null) {
      body = File('test/fixtures/library_aidoku/$fixture').readAsBytesSync();
    } else if (file != null) {
      body = File(file).readAsBytesSync();
    } else {
      body = Uint8List(0);
    }
    final name = fixture ?? file ?? '';
    return _Reply(
      body: body,
      status: status,
      headers: <String, String>{
        'content-type': name.endsWith('.json')
            ? 'application/json'
            : 'text/html; charset=UTF-8',
        ...headers,
      },
      delay: delay,
      error: error,
    );
  }

  int count(String url) => exchanges.where((e) => e.url == url).length;

  List<_Exchange> to(String host) =>
      exchanges.where((e) => Uri.parse(e.url).host == host).toList();

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final url = request.url.toString();
    Map<String, String>? form;
    if (request is http.Request && request.bodyBytes.isNotEmpty) {
      form = Uri.splitQueryString(utf8.decode(request.bodyBytes));
    }
    exchanges.add(
      _Exchange(
        request.method,
        url,
        Map<String, String>.of(request.headers),
        form,
        _since.elapsed,
      ),
    );
    if (offline) {
      throw SocketException(
        "Failed host lookup: '${request.url.host}'",
        osError: const OSError(
          'nodename nor servname provided, or not known',
          8,
        ),
      );
    }
    _Reply? reply;
    for (final route in _routes) {
      if (route.matches(request.method, url, form)) {
        reply = route.reply;
        break;
      }
    }
    if (reply == null &&
        request.method == 'GET' &&
        _imagePath.hasMatch(request.url.path)) {
      reply = _Reply(
        body: image,
        headers: const <String, String>{'content-type': 'image/png'},
      );
    }
    if (reply == null) {
      unexpected.add('${request.method} $url');
      reply = _Reply(
        body: Uint8List.fromList(utf8.encode('not found')),
        status: 404,
        headers: const <String, String>{'content-type': 'text/plain'},
      );
    }
    if (reply.delay > Duration.zero) {
      final done = Completer<void>();
      final timer = Timer(reply.delay, () {
        if (!done.isCompleted) done.complete();
      });
      final trigger = request is http.Abortable ? request.abortTrigger : null;
      trigger?.then((_) {
        if (!done.isCompleted) {
          timer.cancel();
          done.completeError(http.RequestAbortedException(request.url));
        }
      });
      await done.future;
    }
    final error = reply.error;
    if (error != null) throw error;
    return _UrlResponse(
      Stream<List<int>>.value(reply.body),
      reply.status,
      url: request.url,
      headers: reply.headers,
      contentLength: reply.body.length,
    );
  }
}

/// Transport that records and refuses every request (journey 3 must not
/// touch the network at all).
class _NoNetworkClient extends http.BaseClient {
  final List<String> requests = <String>[];

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) {
    requests.add('${request.method} ${request.url}');
    return Future<http.StreamedResponse>.error(
      const SocketException('network disabled in this test'),
    );
  }
}

Future<void> _pumpUntil(
  WidgetTester tester,
  Finder finder, {
  int rounds = 300,
}) async {
  for (var i = 0; i < rounds; i++) {
    if (finder.evaluate().isNotEmpty) return;
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 10)),
    );
    await tester.pump(const Duration(milliseconds: 50));
  }
  fail('not shown: $finder');
}

Future<void> _waitFor(
  bool Function() condition, {
  Duration timeout = const Duration(seconds: 4),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) {
      throw TimeoutException('condition not reached', timeout);
    }
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
}

Future<void> _deleteQuietly(Directory directory) async {
  try {
    if (await directory.exists()) await directory.delete(recursive: true);
  } on FileSystemException {
    // A worker may still hold a file on Windows; the system cleans temp.
  }
}
