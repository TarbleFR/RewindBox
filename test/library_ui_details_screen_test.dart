// LibraryMangaDetailsScreen: card first, saved details, background refresh
// that keeps the scroll position, progressive chapter lists, favourite
// persistence, resume, read marks, chapter order, deactivated sources and
// errors translated by kind.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/library_manga_details_screen.dart';
import 'package:neostation/screens/library_screen/library_reader_launcher.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_ui_sources_harness.dart';

class _Opened {
  final List<LibraryOnlineChapterSession> sessions =
      <LibraryOnlineChapterSession>[];

  /// When set, an open lasts until it completes (like the reader route,
  /// which the launcher awaits until it is closed).
  Completer<void>? readerOpen;

  Future<void> call(
    BuildContext context,
    LibraryOnlineChapterSession session,
  ) async {
    sessions.add(session);
    await readerOpen?.future;
  }
}

Widget _screen({
  required LibraryCatalogItem item,
  required FakeAidokuService aidoku,
  required LibraryReadingStore store,
  required _Opened opened,
  LibraryAddon? addon,
  String? aidokuSourceId,
}) => LibraryMangaDetailsScreen(
  item: item,
  addon: addon,
  aidokuSourceId: aidokuSourceId,
  aidokuService: aidoku,
  readingStore: store,
  imageCache: NoImageCache(),
  chapterOpener: opened.call,
  enableGamepad: false,
);

ScrollPosition _chapterScroll(WidgetTester tester) => tester
    .state<ScrollableState>(
      find.descendant(
        of: find.byKey(const PageStorageKey<String>('manga-chapters')),
        matching: find.byType(Scrollable),
      ),
    )
    .position;

void main() {
  final addon = testAidokuAddon('fr.lelscanfr', 'LelscanFR');
  final item = testMangaItem();
  final key = LibraryMangaKeys.online('fr.lelscanfr', 'one-piece');

  testWidgets(
    'card first, then saved details, then a refresh that keeps the scroll',
    (tester) async {
      final aidoku = FakeAidokuService()
        ..cached = testDetails(item, count: 60)
        ..watchController = StreamController<LibraryMangaDetails>();
      await pumpLibraryUi(
        tester,
        _screen(
          item: item,
          addon: addon,
          aidoku: aidoku,
          store: MemoryReadingStore(),
          opened: _Opened(),
        ),
        wrapInScaffold: false,
      );
      // The card is shown at once.
      expect(find.text('One Piece'), findsWidgets);

      await tester.pump();
      await tester.pump();
      expect(find.text('60 chapter(s)'), findsOneWidget);
      expect(find.text('Chapter 60'), findsOneWidget);
      expect(find.text('Author: Eiichiro Oda'), findsOneWidget);
      expect(find.text('Ongoing'), findsOneWidget);
      expect(find.text('Updating…'), findsOneWidget);
      expect(aidoku.watchModes, <LibraryFetchMode>[
        LibraryFetchMode.cacheFirst,
      ]);

      await tester.drag(
        find.byKey(const PageStorageKey<String>('manga-chapters')),
        const Offset(0, -900),
      );
      // The refresh indicator spins while the refresh runs: no settle.
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      final before = _chapterScroll(tester).pixels;
      expect(before, greaterThan(0));

      // The refresh adds the newest chapter.
      aidoku.watchController!.add(testDetails(item, count: 61));
      await aidoku.watchController!.close();
      await tester.pumpAndSettle();

      expect(_chapterScroll(tester).pixels, before);

      _chapterScroll(tester).jumpTo(0);
      await tester.pump();
      expect(find.text('61 chapter(s)'), findsOneWidget);
      expect(find.text('Chapter 61'), findsOneWidget);
      expect(find.text('Updating…'), findsNothing);
    },
  );

  testWidgets('a long chapter list arrives progressively', (tester) async {
    final controller = StreamController<LibraryMangaDetails>();
    final aidoku = FakeAidokuService()..watchController = controller;
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: _Opened(),
      ),
      wrapInScaffold: false,
    );
    await tester.pump();
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsWidgets);

    controller.add(testDetails(item, count: 10, first: 21, complete: false));
    await tester.pump();
    expect(find.text('Chapter 30'), findsOneWidget);
    // The footer of the list (the resume button says the same while the
    // first chapter is not loaded yet).
    expect(
      find.descendant(
        of: find.byKey(const ValueKey<String>('loading-more-chapters')),
        matching: find.text('Loading more chapters…'),
      ),
      findsOneWidget,
    );

    controller.add(testDetails(item, count: 30));
    await controller.close();
    await tester.pumpAndSettle();
    expect(find.text('Loading more chapters…'), findsNothing);
    expect(find.text('30 chapter(s)'), findsOneWidget);
    expect(
      find.text('Some chapters could not be loaded. Pull down to try again.'),
      findsNothing,
    );
  });

  testWidgets('the favourite toggle is saved with an offline snapshot', (
    tester,
  ) async {
    final directory = (await tester.runAsync(
      () => Directory.systemTemp.createTemp('ns_details_store_'),
    ))!;
    addTearDown(() => directory.delete(recursive: true));
    final store = LibraryReadingStore(directory: directory);
    await tester.runAsync(store.load);
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 3)
      ..watchResult = testDetails(item, count: 3);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: store,
        opened: _Opened(),
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Add to favourites'));
    await tester.pump();
    expect(store.isFavorite(key), isTrue);
    expect(find.text('Added to favourites.'), findsOneWidget);
    expect(find.text('Remove from favourites'), findsOneWidget);
    await tester.runAsync(store.flush);

    final reloaded = LibraryReadingStore(directory: directory);
    await tester.runAsync(reloaded.load);
    final favorite = reloaded.favorite(key)!;
    expect(favorite.sourceId, 'fr.lelscanfr');
    expect(favorite.addonId, addon.id);
    expect(favorite.mangaUrl, 'https://www.lelscanfr.com/manga/one-piece');
    expect(favorite.coverHeaders['Referer'], 'https://example.org/');
    final reopened = LibraryMangaDetailsScreen.itemFromFavorite(favorite);
    expect(reopened.raw['aidokuSourceId'], 'fr.lelscanfr');
    expect(reopened.title, 'One Piece');

    await tester.tap(find.text('Remove from favourites'));
    await tester.pump();
    expect(store.isFavorite(key), isFalse);
    await tester.runAsync(store.flush);
    final again = LibraryReadingStore(directory: directory);
    await tester.runAsync(again.load);
    expect(again.isFavorite(key), isFalse);
  });

  testWidgets('resume continues at the saved chapter and page', (tester) async {
    final store = MemoryReadingStore()
      ..saveProgress(
        LibraryReadingProgress(
          key: key,
          location: LibraryReadingProgress.pageLocation(4),
          fraction: 0.3,
          pageIndex: 4,
          chapterId: '12',
        ),
      )
      ..markChapter(key, '40', read: true)
      ..markChapter(key, '12', page: 4, pageCount: 18);
    final opened = _Opened();
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 40)
      ..watchResult = testDetails(item, count: 40);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: store,
        opened: opened,
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    expect(find.text('Continue – chapter 12, page 5'), findsOneWidget);
    await tester.tap(find.text('Continue – chapter 12, page 5'));
    await tester.pump();
    expect(opened.sessions.single.chapter.id, '12');
    expect(opened.sessions.single.startPage, 4);
    expect(opened.sessions.single.details.onlineKey, key);

    // Read and in-progress marks.
    expect(
      find.descendant(
        of: find.byKey(const ValueKey<String>('chapter-40')),
        matching: find.byIcon(Icons.check_circle),
      ),
      findsOneWidget,
    );

    // Tapping a chapter opens it from its first saved position.
    await tester.tap(find.text('Chapter 39'));
    await tester.pump();
    expect(opened.sessions.last.chapter.id, '39');
    expect(opened.sessions.last.startPage, isNull);
  });

  testWidgets('without progress the button starts with the first chapter', (
    tester,
  ) async {
    final opened = _Opened();
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 5)
      ..watchResult = testDetails(item, count: 5);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: opened,
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Start reading'));
    await tester.pump();
    expect(opened.sessions.single.chapter.id, '1');
  });

  testWidgets('a second tap while a chapter opens opens nothing more', (
    tester,
  ) async {
    final opened = _Opened()..readerOpen = Completer<void>();
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 5)
      ..watchResult = testDetails(item, count: 5);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: opened,
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    await tester.tap(find.text('Chapter 3'));
    await tester.pump();
    await tester.tap(find.text('Chapter 4'));
    await tester.tap(find.text('Start reading'));
    await tester.pump();
    expect(opened.sessions.map((session) => session.chapter.id), <String>['3']);

    // Once the reader is closed, chapters open again.
    opened.readerOpen!.complete();
    await tester.pumpAndSettle();
    opened.readerOpen = null;
    await tester.tap(find.text('Chapter 4'));
    await tester.pump();
    expect(opened.sessions.map((session) => session.chapter.id), <String>[
      '3',
      '4',
    ]);
  });

  testWidgets('resume waits for a partial list that is still loading', (
    tester,
  ) async {
    Future<void> check({LibraryReadingStore? saved}) async {
      final opened = _Opened();
      final controller = StreamController<LibraryMangaDetails>();
      final aidoku = FakeAidokuService()..watchController = controller;
      await pumpLibraryUi(
        tester,
        _screen(
          item: item,
          addon: addon,
          aidoku: aidoku,
          store: saved ?? MemoryReadingStore(),
          opened: opened,
        ),
        wrapInScaffold: false,
      );
      await tester.pump();
      await tester.pump();

      // LelscanFR serves the newest chapters first: 21-30 arrive before 1-20.
      controller.add(testDetails(item, count: 10, first: 21, complete: false));
      await tester.pump();
      final resume = find.byKey(const ValueKey<String>('resume-button'));
      expect(
        find.descendant(
          of: resume,
          matching: find.text('Loading more chapters…'),
        ),
        findsOneWidget,
      );
      await tester.tap(resume);
      await tester.pump();
      expect(opened.sessions, isEmpty);

      controller.add(testDetails(item, count: 30));
      await controller.close();
      await tester.pumpAndSettle();
      await tester.tap(resume);
      await tester.pump();
      expect(opened.sessions, hasLength(1));
      if (saved == null) {
        expect(find.text('Start reading'), findsOneWidget);
        expect(opened.sessions.single.chapter.id, '1');
      } else {
        expect(find.text('Continue – chapter 12, page 5'), findsOneWidget);
        expect(opened.sessions.single.chapter.id, '12');
        expect(opened.sessions.single.startPage, 4);
      }
      await tester.pumpWidget(const SizedBox.shrink());
    }

    await check();
    await check(
      saved: MemoryReadingStore()
        ..saveProgress(
          LibraryReadingProgress(
            key: key,
            location: LibraryReadingProgress.pageLocation(4),
            fraction: 0.3,
            pageIndex: 4,
            chapterId: '12',
          ),
        ),
    );
  });

  testWidgets('the chapter order is toggled and remembered for the session', (
    tester,
  ) async {
    Future<void> show() async {
      final aidoku = FakeAidokuService()
        ..cached = testDetails(item, count: 5)
        ..watchResult = testDetails(item, count: 5);
      await pumpLibraryUi(
        tester,
        _screen(
          item: item,
          addon: addon,
          aidoku: aidoku,
          store: MemoryReadingStore(),
          opened: _Opened(),
        ),
        wrapInScaffold: false,
      );
      await tester.pumpAndSettle();
    }

    double top(String label) => tester.getTopLeft(find.text(label)).dy;

    await show();
    expect(find.text('Newest first'), findsOneWidget);
    expect(top('Chapter 5'), lessThan(top('Chapter 1')));

    await tester.tap(find.byKey(const ValueKey<String>('order-button')));
    await tester.pump();
    expect(find.text('Oldest first'), findsOneWidget);
    expect(top('Chapter 1'), lessThan(top('Chapter 5')));

    // A new title page keeps the order chosen in this session.
    await tester.pumpWidget(const SizedBox.shrink());
    await show();
    expect(find.text('Oldest first'), findsOneWidget);

    // Restore the default for the other tests.
    await tester.tap(find.byKey(const ValueKey<String>('order-button')));
    await tester.pump();
    expect(find.text('Newest first'), findsOneWidget);
  });

  testWidgets('a deactivated source shows saved data and locked chapters', (
    tester,
  ) async {
    final opened = _Opened();
    final aidoku = FakeAidokuService()
      ..cachedForSource = testDetails(item, count: 5);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        aidokuSourceId: 'fr.lelscanfr',
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: opened,
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const ValueKey<String>('source-banner')), findsOneWidget);
    expect(find.textContaining('This source is deactivated.'), findsOneWidget);
    expect(find.text('Chapter 5'), findsOneWidget);
    expect(find.byIcon(Icons.lock_outline), findsWidgets);
    expect(find.byTooltip('Refresh'), findsNothing);
    expect(aidoku.watchModes, isEmpty, reason: 'no network for it');

    await tester.tap(find.text('Chapter 5'));
    await tester.pump();
    expect(opened.sessions, isEmpty);
    expect(
      find.text('Activate the source again to open this chapter.'),
      findsOneWidget,
    );
  });

  testWidgets('a partial saved list of a deactivated source offers no retry', (
    tester,
  ) async {
    // Only some LelscanFR list pages were saved: nothing can complete the
    // list while the source is deactivated (no pull-to-refresh either).
    final aidoku = FakeAidokuService()
      ..cachedForSource = testDetails(item, count: 5, complete: false);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        aidokuSourceId: 'fr.lelscanfr',
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: _Opened(),
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    expect(find.text('Chapter 5'), findsOneWidget);
    expect(find.byType(RefreshIndicator), findsNothing);
    expect(
      find.text('Some chapters could not be loaded. Pull down to try again.'),
      findsNothing,
    );
  });

  testWidgets('an error is explained by kind, with its detail and a retry', (
    tester,
  ) async {
    final aidoku = FakeAidokuService()
      ..watchResult = LibraryNetworkException(
        LibraryNetworkErrorKind.challenge,
        uri: Uri.parse('https://www.lelscanfr.com/manga/one-piece'),
        statusCode: 403,
      );
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: _Opened(),
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    expect(find.text('This title could not be loaded.'), findsOneWidget);
    expect(
      find.text(
        'The site requires a browser verification that NeoStation cannot '
        'perform.',
      ),
      findsOneWidget,
    );
    await tester.tap(find.text('Technical details'));
    await tester.pump();
    expect(find.textContaining('HTTP 403'), findsOneWidget);

    aidoku.watchResult = testDetails(item, count: 2);
    await tester.tap(find.text('Retry'));
    await tester.pumpAndSettle();
    expect(aidoku.watchModes.last, LibraryFetchMode.refresh);
    expect(find.text('2 chapter(s)'), findsOneWidget);
  });

  testWidgets('a failed refresh keeps the saved chapters on screen', (
    tester,
  ) async {
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 20, stale: true)
      ..watchResult = const LibraryNetworkException(
        LibraryNetworkErrorKind.serverUnavailable,
        statusCode: 504,
      );
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: _Opened(),
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    expect(find.text('20 chapter(s)'), findsOneWidget);
    expect(find.text('Chapter 20'), findsOneWidget);
    expect(
      find.textContaining('The title could not be updated.'),
      findsOneWidget,
    );
    expect(
      find.text('Saved copy shown: the site could not be reached.'),
      findsOneWidget,
    );
  });

  testWidgets('the screen is translated (French)', (tester) async {
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 3)
      ..watchResult = testDetails(item, count: 3);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: _Opened(),
      ),
      locale: const Locale('fr'),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    expect(find.text('Commencer la lecture'), findsOneWidget);
    expect(find.text('3 chapitre(s)'), findsOneWidget);
    expect(find.text('Chapitre 3'), findsOneWidget);
    expect(find.text('Ajouter aux favoris'), findsOneWidget);
    expect(find.text('En cours'), findsOneWidget);
  });

  testWidgets('the publication status is not shown as uncertain', (
    tester,
  ) async {
    final aidoku = FakeAidokuService()
      ..cached = testDetails(item, count: 3)
      ..watchResult = testDetails(item, count: 3);
    await pumpLibraryUi(
      tester,
      _screen(
        item: item,
        addon: addon,
        aidoku: aidoku,
        store: MemoryReadingStore(),
        opened: _Opened(),
      ),
      wrapInScaffold: false,
    );
    await tester.pumpAndSettle();

    final status = find.byKey(const ValueKey<String>('manga-status'));
    expect(
      find.descendant(of: status, matching: find.text('Ongoing')),
      findsOneWidget,
    );
    expect(
      find.descendant(of: status, matching: find.byIcon(Icons.help_outline)),
      findsNothing,
      reason: 'a question mark reads as "status not verified"',
    );
    expect(
      find.descendant(of: status, matching: find.byIcon(Icons.autorenew)),
      findsOneWidget,
    );
  });
}
