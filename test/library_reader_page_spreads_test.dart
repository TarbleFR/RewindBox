// Two-page spreads of the page reader (docs/library-books-3d-plan.md § 3.9,
// Q16): automatic in landscape, the cover alone, the next page on the left
// right to left, never in the vertical strip; the progress, the chapter
// marks, the resume, the slider and its label stay page based (a spread is
// saved as its first page, the last spread as the last page, the spread
// holding the saved page opens); a pair is announced as one image; a
// rotation keeps the page on screen; the curl faces are the spreads'.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_reader_test_support.dart';

String tr(String language, String key) =>
    LibraryReaderLocale.values[language]![key]!;

const Size landscape = Size(900, 600);
const Size portrait = Size(600, 900);

LibraryPageReaderScreenState readerState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

LibraryPageCurlLayer curlLayer(WidgetTester tester) =>
    tester.widget<LibraryPageCurlLayer>(find.byType(LibraryPageCurlLayer));

/// Position of the PageView (item index).
double viewPage(WidgetTester tester) =>
    tester.widget<PageView>(find.byType(PageView)).controller!.page!;

/// One-based page numbers on screen, from the left of the screen to the
/// right.
List<int> pagesOnScreen(WidgetTester tester) {
  final placed = <(double, int)>[
    for (final element in find.byType(LibraryReaderPageImage).evaluate())
      (
        tester.getRect(find.byElementPredicate((e) => e == element)).left,
        (element.widget as LibraryReaderPageImage).pageNumber,
      ),
  ]..sort((a, b) => a.$1.compareTo(b.$1));
  return <int>[for (final (_, page) in placed) page];
}

Rect pageRect(WidgetTester tester, int pageNumber) => tester.getRect(
  find.byWidgetPredicate(
    (widget) =>
        widget is LibraryReaderPageImage && widget.pageNumber == pageNumber,
  ),
);

/// Runs [work] to completion: the store was loaded in the real zone, so its
/// continuations need both real turns and fake-time microtask flushes.
Future<void> drive(WidgetTester tester, Future<void> work) async {
  var done = false;
  unawaited(work.whenComplete(() => done = true));
  for (var i = 0; i < 20 && !done; i++) {
    await settle(tester, rounds: 1);
  }
  expect(done, isTrue);
}

/// Alignment of the decoded page drawn for [pageNumber].
Alignment drawnAlignment(WidgetTester tester, int pageNumber) =>
    tester
            .widget<RawImage>(
              find.descendant(
                of: find.byWidgetPredicate(
                  (widget) =>
                      widget is LibraryReaderPageImage &&
                      widget.pageNumber == pageNumber,
                ),
                matching: find.byType(RawImage),
              ),
            )
            .alignment
        as Alignment;

Future<void> closeAll(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await flushStore(tester, store);
}

/// Lets the opening transition of the reader's route end (the pages are
/// measured in place).
Future<void> routeShown(WidgetTester tester) =>
    tester.pump(const Duration(seconds: 1));

/// Lets real work (decoding) progress until [condition] holds.
Future<void> waitUntil(
  WidgetTester tester,
  bool Function() condition, {
  String? reason,
}) async {
  for (var i = 0; i < 40 && !condition(); i++) {
    await settle(tester, rounds: 1);
  }
  expect(condition(), isTrue, reason: reason);
}

/// Whether the pages [pageNumbers] on screen show their decoded images.
bool imagesShown(List<int> pageNumbers) => pageNumbers.every(
  (pageNumber) => find
      .descendant(
        of: find.byWidgetPredicate(
          (widget) =>
              widget is LibraryReaderPageImage &&
              widget.pageNumber == pageNumber,
        ),
        matching: find.byType(RawImage),
      )
      .evaluate()
      .isNotEmpty,
);

/// The frames of a rotation (the layout, then the pages shown counted).
Future<void> rotate(WidgetTester tester, Size size) async {
  tester.view.physicalSize = size;
  await tester.pump();
  await tester.pump();
}

void main() {
  setUpReaderEnvironment();
  setUp(() {
    LibraryPageCurlProgram.resetForTesting();
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('layout', () {
    testWidgets('landscape: the cover alone on the right, then pairs, the '
        'first page on the left', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:ltr'),
          store: store,
        ),
      );
      final state = readerState(tester);
      await routeShown(tester);
      expect(state.spreads!.doublePage, isTrue);
      expect(state.spreads!.length, 3);
      expect(pagesOnScreen(tester), <int>[1]);
      expect(pageRect(tester, 1), const Rect.fromLTWH(450, 0, 450, 600));
      // The curl lifts the spread's pages (once decoded: a page still
      // loading has no face).
      await waitUntil(tester, () => curlLayer(tester).faceOf(1) != null);
      expect(
        curlLayer(tester).faceOf(0),
        const LibraryPageCurlFace.spread(right: 0),
      );
      expect(
        curlLayer(tester).faceOf(1),
        const LibraryPageCurlFace.spread(left: 1, right: 2),
      );
      expect(curlLayer(tester).faceOf(3), isNull, reason: 'the end card');

      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      expect(viewPage(tester), 1.0);
      expect(pagesOnScreen(tester), <int>[2, 3]);
      expect(pageRect(tester, 2), const Rect.fromLTWH(0, 0, 450, 600));
      expect(pageRect(tester, 3), const Rect.fromLTWH(450, 0, 450, 600));
      // Each page leans on the spine, as the curl draws it.
      await waitUntil(tester, () => imagesShown(<int>[2, 3]));
      expect(drawnAlignment(tester, 2), Alignment.centerRight);
      expect(drawnAlignment(tester, 3), Alignment.centerLeft);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 3);
      expect(pagesOnScreen(tester), <int>[4, 5]);
      // Then the end card, at the last page.
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.atEndCard, isTrue);
      expect(state.controller.page, 4);
      // Back to the last spread.
      state.gamepadBindings.left!();
      await frames(tester);
      expect(state.atEndCard, isFalse);
      expect(state.controller.page, 3);
      expect(pagesOnScreen(tester), <int>[4, 5]);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });

    testWidgets('right to left: the cover on the left, the next page on the '
        'left', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            progressKey: 'local:rtl',
            layoutHint: LibraryPageLayoutHint.rightToLeft,
          ),
          store: store,
        ),
      );
      final state = readerState(tester);
      await routeShown(tester);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isTrue);
      expect(curlLayer(tester).rightToLeft, isTrue);
      expect(pagesOnScreen(tester), <int>[1]);
      expect(pageRect(tester, 1), const Rect.fromLTWH(0, 0, 450, 600));
      await waitUntil(tester, () => curlLayer(tester).faceOf(1) != null);
      expect(
        curlLayer(tester).faceOf(1),
        const LibraryPageCurlFace.spread(left: 2, right: 1),
      );
      // The left side turns forward.
      state.gamepadBindings.left!();
      await frames(tester);
      expect(state.controller.page, 1);
      expect(pagesOnScreen(tester), <int>[3, 2]);
      expect(pageRect(tester, 3), const Rect.fromLTWH(0, 0, 450, 600));
      expect(pageRect(tester, 2), const Rect.fromLTWH(450, 0, 450, 600));
      await tester.tapAt(const Offset(50, 300));
      await frames(tester);
      expect(state.controller.page, 3);
      expect(pagesOnScreen(tester), <int>[5, 4]);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      await closeAll(tester, store);
    });

    testWidgets('the title\'s settings: without the cover alone pages pair '
        '1-2, 3-4; always shows pairs in portrait too', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      const key = 'local:pairs';
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(firstPageAlone: false),
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: store,
        ),
      );
      final state = readerState(tester);
      expect(pagesOnScreen(tester), <int>[1, 2]);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 2);
      expect(pagesOnScreen(tester), <int>[3, 4]);
      state.gamepadBindings.right!();
      await frames(tester);
      // An odd last page is alone, on the left half.
      expect(state.controller.page, 4);
      expect(pagesOnScreen(tester), <int>[5]);
      expect(pageRect(tester, 5), const Rect.fromLTWH(0, 0, 450, 600));

      // Portrait: one page per screen in automatic mode...
      await rotate(tester, portrait);
      expect(state.spreads!.doublePage, isFalse);
      expect(pagesOnScreen(tester), <int>[5]);
      expect(pageRect(tester, 5), const Rect.fromLTWH(0, 0, 600, 900));
      // ...two with "always".
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          firstPageAlone: false,
          doublePage: LibraryDoublePageMode.always,
        ),
      );
      await tester.pump();
      await tester.pump();
      expect(state.spreads!.doublePage, isTrue);
      expect(pagesOnScreen(tester), <int>[5]);
      expect(pageRect(tester, 5), const Rect.fromLTWH(0, 0, 300, 900));
      // "Never" in landscape: one page.
      await rotate(tester, landscape);
      store.updateSettings(
        store.settings.copyWith(doublePage: LibraryDoublePageMode.always),
      );
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.never,
        ),
      );
      await tester.pump();
      await tester.pump();
      expect(state.spreads!.doublePage, isFalse);
      expect(pagesOnScreen(tester), <int>[5]);
      expect(state.controller.page, 4);
      await closeAll(tester, store);
    });

    testWidgets('never in the vertical strip', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(doublePage: LibraryDoublePageMode.always),
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:strip', startPage: 1),
          store: store,
        ),
      );
      final state = readerState(tester);
      expect(pagesOnScreen(tester), <int>[2, 3]);
      state.controller.toggleMode();
      await frames(tester);
      expect(find.byType(ListView), findsOneWidget);
      expect(find.byType(LibraryPageCurlLayer), findsNothing);
      // Every page of the strip uses the whole width.
      for (final element in find.byType(LibraryReaderPageImage).evaluate()) {
        expect(
          tester.getRect(find.byElementPredicate((e) => e == element)).width,
          900,
        );
      }
      expect(state.controller.page, 1);
      // Back to pages: the spread of the page.
      state.controller.toggleMode();
      await frames(tester);
      expect(pagesOnScreen(tester), <int>[2, 3]);
      await closeAll(tester, store);
    });
  });

  group('page based progress', () {
    testWidgets('the controller keeps the first page of a spread as the '
        'position, the last page for the last spread, and counts the other '
        'one as shown', (tester) async {
      final (store, _) = await createStore(tester);
      final content = FakePageContent(chapterCount: 2, tracksChapters: true);
      final controller = LibraryPageReaderController(
        content: content,
        store: store,
      );
      await drive(tester, controller.start());
      // The pair 2-3 (indices 1 and 2): saved as its first page.
      controller.setPage(1, through: 2);
      expect(controller.lastShownPage, 2);
      controller.saveNow();
      expect(store.progressFor(content.progressKey)!.pageIndex, 1);
      expect(store.chapterMark(content.progressKey, 'c0')?.page, 1);
      controller.setPage(3);
      expect(controller.lastShownPage, 3);
      expect(controller.lastPageShown, isFalse);
      expect(controller.fraction, closeTo((0 + 4 / 5) / 2, 1e-9));
      expect(store.chapterMark(content.progressKey, 'c0')?.read, isNot(true));
      // The pair 4-5 (indices 3 and 4).
      controller.setPage(3, through: 4);
      expect(controller.page, 3);
      expect(controller.lastShownPage, 4);
      expect(controller.lastPageShown, isTrue);
      expect(controller.isLastPage, isFalse);
      expect(store.chapterMark(content.progressKey, 'c0')?.read, isTrue);
      expect(controller.fraction, closeTo(0.5, 1e-9));
      controller.saveNow();
      // Changed contract (review of the books chantier): the last spread is
      // saved as the last page, for the position and the chapter mark, so
      // the chapter is saved as finished. Saved as page 3 (the spread's
      // first page), the finished chapter reopened at its last spread and
      // the title page continued with it instead of the next chapter.
      expect(store.progressFor(content.progressKey)!.pageIndex, 4);
      expect(store.progressFor(content.progressKey)!.location, 'page:4');
      expect(store.chapterMark(content.progressKey, 'c0')?.page, 4);
      expect(controller.page, 3, reason: 'the spread is still shown');
      // Never beyond the chapter, never before the page.
      controller.setPage(1, through: 9);
      expect(controller.lastShownPage, 4);
      controller.setPage(2, through: 0);
      expect(controller.lastShownPage, 2);
      // The vertical strip shows pages one by one.
      controller.setPage(3, through: 4);
      controller.toggleMode();
      expect(controller.mode, LibraryPageReaderMode.vertical);
      expect(controller.lastShownPage, 3);
      expect(controller.fraction, closeTo((0 + 4 / 5) / 2, 1e-9));
      controller.dispose();
      await flushStore(tester, store);
    });

    testWidgets('the spread holding the saved page opens; the last spread is '
        'saved as the last page', (tester) async {
      useSurface(tester, size: landscape);
      final (store, directory) = await createStore(tester);
      const key = 'local:resume';
      store.saveProgress(
        LibraryReadingProgress(
          key: key,
          location: 'page:2',
          fraction: 0.6,
          pageIndex: 2,
        ),
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: store,
        ),
      );
      final state = readerState(tester);
      // Page 3 (index 2) is the right page of the pair 2-3.
      expect(state.controller.page, 2);
      expect(viewPage(tester), 1.0);
      expect(pagesOnScreen(tester), <int>[2, 3]);
      expect(find.text('3 / 5'), findsOneWidget);
      state.gamepadBindings.right!();
      await frames(tester);
      // The pair 4-5, the last one: the reader's position is its first page
      // (index 3).
      expect(state.controller.page, 3);
      expect(pagesOnScreen(tester), <int>[4, 5]);
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      // Changed contract (review of the books chantier): the last spread is
      // saved as the last page (index 4), as the PDF reader does, so that a
      // finished chapter is saved as finished; it used to be saved as its
      // first page (index 3).
      final saved = store.progressFor(key)!;
      expect(saved.location, 'page:4');
      expect(saved.pageIndex, 4);
      expect(saved.pageCount, 5);
      expect(saved.fraction, closeTo(1.0, 1e-9));
      expect(saved.isFinished, isTrue);
      await flushStore(tester, store);

      // Reopened in landscape: the last spread again.
      final (reloaded, _) = await createStore(tester, directory: directory);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: reloaded,
        ),
      );
      expect(readerState(tester).controller.page, 4);
      expect(pagesOnScreen(tester), <int>[4, 5]);
      await closeAll(tester, reloaded);

      // Reopened in portrait: the last page alone.
      final (portraitStore, _) = await createStore(
        tester,
        directory: directory,
      );
      useSurface(tester, size: portrait);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: portraitStore,
        ),
      );
      expect(readerState(tester).controller.page, 4);
      expect(pagesOnScreen(tester), <int>[5]);
      await closeAll(tester, portraitStore);
    });

    testWidgets('the slider and its label stay page based', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(pagesPerChapter: 9),
          store: store,
        ),
      );
      final state = readerState(tester);
      expect(find.text('1 / 9'), findsOneWidget);
      for (final (page, label, shown) in <(int, String, List<int>)>[
        (3, '4 / 9', <int>[4, 5]),
        (4, '5 / 9', <int>[4, 5]),
        (7, '8 / 9', <int>[8, 9]),
        (0, '1 / 9', <int>[1]),
      ]) {
        final slider = tester.widget<Slider>(find.byType(Slider));
        slider.onChangeStart!(page.toDouble());
        slider.onChanged!(page.toDouble());
        slider.onChangeEnd!(page.toDouble());
        await tester.pump(const Duration(milliseconds: 50));
        expect(state.controller.page, page);
        expect(find.text(label), findsOneWidget);
        expect(pagesOnScreen(tester), shown);
      }
      await closeAll(tester, store);
    });

    testWidgets('an online chapter is read once its last page shows in a '
        'spread', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(chapterCount: 2, tracksChapters: true);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(store.chapterMark(content.progressKey, 'c0')?.read, isNot(true));
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 3);
      expect(pagesOnScreen(tester), <int>[4, 5]);
      expect(store.chapterMark(content.progressKey, 'c0')?.read, isTrue);
      state.controller.saveNow();
      final saved = store.progressFor(content.progressKey)!;
      // Changed contract (review of the books chantier): the last spread is
      // saved as the last page (it used to be index 3, the spread's first
      // page), for the position and the chapter mark.
      expect(saved.pageIndex, 4);
      expect(store.chapterMark(content.progressKey, 'c0')?.page, 4);
      expect(saved.chapterId, 'c0');
      // Chapter 1 of 2 seen to its end: half the title.
      expect(saved.fraction, closeTo(0.5, 1e-9));
      await closeAll(tester, store);

      // Opened on a spread that already shows the last page: read too.
      final (other, _) = await createStore(tester);
      final opened = FakePageContent(
        chapterCount: 2,
        tracksChapters: true,
        startPage: 3,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: opened, store: other),
      );
      expect(readerState(tester).controller.page, 3);
      expect(pagesOnScreen(tester), <int>[4, 5]);
      expect(other.chapterMark(opened.progressKey, 'c0')?.read, isTrue);
      await closeAll(tester, other);
    });

    // Review of the books chantier (probe B): saved as the first page of
    // its last spread, a finished chapter reopened at that spread as if it
    // were unfinished; on a single last page it restarts (440 rule).
    testWidgets('an online chapter finished on its last spread restarts at '
        'its beginning when opened again', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      LibraryPageReaderScreen reader() => LibraryPageReaderScreen(
        content: FakePageContent(chapterCount: 2, tracksChapters: true),
        store: store,
      );
      final navigator = await pumpReader(tester, reader());
      final state = readerState(tester);
      expect(state.spreads?.doublePage, isTrue);
      // Two turns: the last spread, pages 4 and 5.
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      expect(pagesOnScreen(tester), <int>[4, 5]);
      expect(state.controller.lastPageShown, isTrue);
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      final saved = store.progressFor('online:fake:manga')!;
      expect(saved.chapterId, 'c0');
      expect(saved.pageIndex, 4);
      final mark = store.chapterMark('online:fake:manga', 'c0')!;
      expect(mark.read, isTrue);
      expect(mark.page, 4);

      // The same chapter opened again: at its beginning.
      unawaited(
        navigator.currentState!.push<void>(
          MaterialPageRoute<void>(builder: (_) => reader()),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await settle(tester, rounds: 3);
      final reopened = readerState(tester).controller;
      expect(reopened.chapterIndex, 0);
      expect(reopened.page, 0);
      expect(pagesOnScreen(tester), <int>[1]);
      await closeAll(tester, store);
    });

    testWidgets('the pages of the previous and next spreads are prefetched', (
      tester,
    ) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(pagesPerChapter: 9, startPage: 3);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      await tester.pump();
      // On the pair 4-5: 6-7 ahead, 2-3 behind.
      expect(pagesOnScreen(tester), <int>[4, 5]);
      expect(content.sources.single.prefetched, containsAll(<int>[5, 6, 1, 2]));
      await closeAll(tester, store);
    });
  });

  group('rotation', () {
    testWidgets('a rotation keeps the current page on screen', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:rotate', startPage: 2),
          store: store,
        ),
      );
      final state = readerState(tester);
      expect(pagesOnScreen(tester), <int>[3]);
      await rotate(tester, landscape);
      expect(state.spreads!.doublePage, isTrue);
      expect(pagesOnScreen(tester), <int>[2, 3]);
      expect(viewPage(tester), 1.0);
      // The page itself is kept (not the first page of the spread).
      expect(state.controller.page, 2);
      await rotate(tester, portrait);
      expect(pagesOnScreen(tester), <int>[3]);
      expect(viewPage(tester), 2.0);
      expect(state.controller.page, 2);
      // A spread turned to in landscape is its first page in portrait.
      await rotate(tester, landscape);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(pagesOnScreen(tester), <int>[4, 5]);
      expect(state.controller.lastShownPage, 4);
      await rotate(tester, portrait);
      expect(pagesOnScreen(tester), <int>[4]);
      expect(state.controller.page, 3);
      expect(state.controller.lastShownPage, 3);
      // The turns follow the new layout.
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 4);
      expect(pagesOnScreen(tester), <int>[5]);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });
  });

  group('VoiceOver', () {
    testWidgets('a pair is announced as one image, a page alone as itself', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:voice'),
          store: store,
        ),
        locale: const Locale('fr'),
      );
      final state = readerState(tester);
      // The cover is decoded.
      await waitUntil(tester, () => imagesShown(<int>[1]));
      String format(String key, Map<String, Object> values) {
        var text = tr('fr', key);
        values.forEach(
          (name, value) => text = text.replaceAll('{$name}', '$value'),
        );
        return text;
      }

      // An image node with exactly this label (the page slider says "Page N
      // of M" too, not as an image).
      SemanticsFinder image(String label) => find.semantics.byPredicate(
        (node) =>
            node.label == label &&
            node.getSemanticsData().flagsCollection.isImage,
      );
      // Contract changed in phase 8 (docs/library-books-3d-plan.md § 4 row
      // 8): a page alone said "Page N"; it now says "Page N of M", as an
      // image, like the PDF and EPUB pages.
      expect(
        find.semantics.byLabel(
          format('pageNumber', <String, Object>{'page': 1}),
        ),
        findsNothing,
      );
      expect(
        image(format('pageOfTotal', <String, Object>{'page': 1, 'total': 5})),
        findsOne,
      );
      state.gamepadBindings.right!();
      await frames(tester);
      await waitUntil(tester, () => imagesShown(<int>[2, 3]));
      expect(find.semantics.byLabel('Pages 2 et 3 sur 5'), findsOne);
      final pair = find.semantics.byLabel(
        format('pagesOfTotal', <String, Object>{
          'first': 2,
          'second': 3,
          'total': 5,
        }),
      );
      expect(pair, findsOne);
      expect(
        pair.evaluate().single.getSemanticsData().flagsCollection.isImage,
        isTrue,
      );
      // Its pages do not announce themselves as well.
      for (final page in <int>[2, 3]) {
        expect(
          find.semantics.byLabel(
            format('pageNumber', <String, Object>{'page': page}),
          ),
          findsNothing,
        );
        expect(
          image(
            format('pageOfTotal', <String, Object>{'page': page, 'total': 5}),
          ),
          findsNothing,
        );
      }
      await closeAll(tester, store);
      semantics.dispose();
    });
  });
}
