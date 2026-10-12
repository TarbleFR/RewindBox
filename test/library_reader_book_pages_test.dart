// Build 447 pages layout of the EPUB/TXT reader
// (docs/library-books-3d-plan.md § 3.5, § 3.9, § 3.10): the default layout,
// resume and save (EPUB CFI, txt:b:o unchanged), the same first words across
// layout switches, typography changes and rotations, spreads in landscape,
// right to left, the three page turns and Reduce Motion, links, VoiceOver
// labels, "Page N of M" and the controller. Real reader, store, paginator
// and page curl (drawn by its painter: the shader has its own tests).
//
// The paginator yields to the event loop with zero-delay timers, which
// `tester.pump()` without a duration does not fire: these tests pump
// `Duration.zero` where pages are laid out ([settlePages]).
import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/reader/library_book_pages_view.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_chrome.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_paginator.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_view.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_local_fixtures.dart';
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

String enFormat(String key, Map<String, Object?> values) {
  var text = en(key);
  values.forEach((name, value) => text = text.replaceAll('{$name}', '$value'));
  return text;
}

/// 1000 paragraphs: five TXT sections of 200.
String sampleText() => List<String>.generate(
  1000,
  (i) => 'Paragraph $i ${List<String>.filled(40, 'word$i').join(' ')}',
).join('\n\n');

const Size portrait = Size(400, 860);
const Size landscape = Size(900, 600);

LibraryBookReaderScreenState bookState(WidgetTester tester) => tester
    .state<LibraryBookReaderScreenState>(find.byType(LibraryBookReaderScreen));

LibraryTextReflowSource textSource() =>
    LibraryTextReflowSource(LibraryTextDocument.fromText(sampleText()));

LibraryBookReaderScreen textReader(
  LibraryReadingStore store, {
  String progressKey = 'local:pages',
  bool rightToLeft = false,
  LibraryReflowSourceOpener? open,
}) => LibraryBookReaderScreen(
  open: open ?? () async => textSource(),
  progressKey: progressKey,
  title: 'Sample',
  store: store,
  rightToLeft: rightToLeft,
);

/// Runs the paginator's turns (zero-delay timers) and real I/O until the
/// reader shows a laid-out window.
Future<void> settlePages(WidgetTester tester, {int rounds = 4}) async {
  for (var i = 0; i < rounds; i++) {
    await tester.pump(Duration.zero);
    await settle(tester, rounds: 1);
  }
}

Future<void> openPages(WidgetTester tester, Widget reader) async {
  await pumpReader(tester, reader);
  await settlePages(tester);
}

/// Closes the reader, then runs the paginator turns it cancelled.
Future<void> closePages(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(Duration.zero);
  await settle(tester, rounds: 2);
  await tester.pump(Duration.zero);
  await flushStore(tester, store);
}

/// A turn (curl 380 ms, slide 220 ms), then the paginator's turns.
Future<void> turned(WidgetTester tester) async {
  await frames(tester);
  await settlePages(tester, rounds: 2);
}

/// Whether [page] holds [position].
bool holds(LibraryReflowPageSpec page, LibraryReflowPosition position) =>
    compare(page.start, position) <= 0 &&
    (page.isLastInChapter || compare(position, page.end) < 0);

bool spreadHolds(LibraryBookSpread spread, LibraryReflowPosition position) =>
    spread.pages.any((page) => holds(page, position));

int compare(LibraryReflowPosition a, LibraryReflowPosition b) {
  if (a.chapter != b.chapter) return a.chapter - b.chapter;
  if (a.block != b.block) return a.block - b.block;
  return a.offset - b.offset;
}

String txt(LibraryReflowPosition position) =>
    'txt:${position.chapter * 200 + position.block}:${position.offset}';

Future<LibraryEpubDocument> openEpub(
  WidgetTester tester, {
  String? chapter1,
  String? chapter2,
}) async {
  return (await tester.runAsync(() async {
    final directory = await createTempDir('ns_reader_pages_epub_');
    final file = await writeFile(
      directory,
      'book.epub',
      buildEpub3(chapter1: chapter1, chapter2: chapter2),
    );
    return LibraryEpubDocument.open(file.path);
  }))!;
}

/// A long first chapter.
String longChapter() => xhtml(
  List<String>.generate(
    160,
    (i) => '<p>Paragraph $i ${List<String>.filled(28, 'w$i').join(' ')}</p>',
  ).join(),
);

void setLayout(
  LibraryReadingStore store, {
  LibraryTextLayout? textLayout,
  LibraryPageTurnStyle? turnStyle,
  LibraryDoublePageMode? doublePage,
  bool? firstPageAlone,
}) {
  store.updateSettings(
    store.settings.copyWith(
      textLayout: textLayout,
      turnStyle: turnStyle,
      doublePage: doublePage,
      firstPageAlone: firstPageAlone,
    ),
  );
}

void main() {
  setUpReaderEnvironment();
  // The page curl draws with its painter here.
  setUp(() {
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('opening and saving', () {
    testWidgets('pages are the default layout; a saved txt location opens on '
        'the page holding it', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      expect(store.settings.textLayout, LibraryTextLayout.pages);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:pages',
          location: 'txt:450:120',
          fraction: 0.45,
        ),
      );
      await openPages(tester, textReader(store));
      final state = bookState(tester);
      expect(state.textLayout, LibraryTextLayout.pages);
      const saved = LibraryReflowPosition(2, 50, 120);
      final spread = state.shownSpread!;
      expect(spread.doublePage, isFalse);
      expect(holds(spread.first, saved), isTrue, reason: '$spread');
      expect(state.currentPosition, saved);
      // No scroll view: the page is a picture labelled with its text.
      expect(find.byType(LibraryReflowUnitView), findsNothing);
      expect(find.byType(LibraryBookPageCanvas), findsWidgets);
      // Opening counts as reading; the location stays the same words.
      await tester.pump(const Duration(seconds: 1));
      expect(store.progressFor('local:pages')!.location, 'txt:450:120');
      await closePages(tester, store);
    });

    testWidgets('a saved EPUB CFI opens on the page holding it', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final document = await openEpub(tester, chapter1: longChapter());
      final cfi = (await tester.runAsync(() => document.cfiFor(0, 57, 30)))!;
      store.saveProgress(
        LibraryReadingProgress(key: 'local:cfi', location: cfi, fraction: 0.4),
      );
      await openPages(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:cfi',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      final state = bookState(tester);
      const position = LibraryReflowPosition(0, 57, 30);
      expect(state.currentPosition, position);
      expect(holds(state.shownSpread!.first, position), isTrue);
      await closePages(tester, store);
    });

    testWidgets('turning saves the start of the page turned to (txt, CFI)', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await openPages(tester, textReader(store, progressKey: 'local:turn'));
      final state = bookState(tester);
      final first = state.shownSpread!.first;
      expect(first.start, LibraryReflowPosition.start);
      state.gamepadBindings.down!();
      await turned(tester);
      final second = state.shownSpread!.first;
      expect(second.indexInChapter, 1);
      expect(second.start, first.end);
      expect(state.currentPosition, second.start);
      await tester.pump(const Duration(seconds: 1));
      expect(store.progressFor('local:turn')!.location, txt(second.start));
      expect(
        store.progressFor('local:turn')!.fraction,
        closeTo(state.source!.fractionFor(second.start), 1e-9),
      );
      await closePages(tester, store);

      // EPUB: the CFI of the page start, resolved by a new document.
      final (epubStore, _) = await createStore(tester);
      final document = await openEpub(tester, chapter1: longChapter());
      await openPages(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:epub-turn',
          title: 'Le Petit Livre',
          store: epubStore,
        ),
      );
      final epub = bookState(tester);
      for (var i = 0; i < 3; i++) {
        epub.gamepadBindings.down!();
        await turned(tester);
      }
      final shown = epub.shownSpread!.first.start;
      expect(shown.block, greaterThan(0));
      epub.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 800));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      final saved = epubStore.progressFor('local:epub-turn')!.location;
      final resolved = (await tester.runAsync(() async {
        final reopened = await LibraryEpubDocument.open(document.path);
        try {
          return await reopened.resolveCfi(saved);
        } finally {
          await reopened.close();
        }
      }))!;
      expect(
        (resolved.spineIndex, resolved.blockIndex, resolved.charOffset),
        (shown.chapter, shown.block, shown.offset),
      );
      await closePages(tester, epubStore);
    });

    testWidgets("'Laying out pages…' until the chapter is paginated, then "
        "'Page N of M'", (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final source = _GatedSource(textSource());
      await pumpReader(
        tester,
        textReader(store, progressKey: 'local:gate', open: () async => source),
      );
      await settlePages(tester);
      final state = bookState(tester);
      expect(state.shownSpread, isNull);
      // The bar says the pages are being laid out; the body still says
      // the book is loading (one message at the opening).
      Text pagesLabel() => tester.widget<Text>(
        find.byKey(const ValueKey<String>('library-book-pages-label')),
      );
      expect(pagesLabel().data, en('paginating'));
      expect(find.text(en('loadingBook')), findsOneWidget);
      expect(find.byType(LibraryBookPageCanvas), findsNothing);
      source.open();
      await settlePages(tester);
      expect(state.shownSpread, isNotNull);
      final total = state.paginator!.pageCountOf(0)!;
      expect(total, greaterThan(10));
      expect(
        find.text(enFormat('pageOfTotal', {'page': 1, 'total': total})),
        findsOneWidget,
      );
      expect(find.text(en('paginating')), findsNothing);
      state.gamepadBindings.down!();
      await turned(tester);
      expect(
        find.text(enFormat('pageOfTotal', {'page': 2, 'total': total})),
        findsOneWidget,
      );
      await closePages(tester, store);
    });
  });

  group('same words', () {
    testWidgets('switching layouts keeps the first words; the book keeps the '
        'choice', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await openPages(tester, textReader(store, progressKey: 'local:switch'));
      final state = bookState(tester);
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.down!();
        await turned(tester);
      }
      final page = state.shownSpread!.first;
      expect(page.indexInChapter, 2);

      // Pages -> scroll: the scroll view starts at the page's first line.
      state.setTextLayout(LibraryTextLayout.scroll);
      await settlePages(tester);
      expect(state.textLayout, LibraryTextLayout.scroll);
      expect(
        store.bookSettingsFor('local:switch')!.textLayout,
        LibraryTextLayout.scroll,
      );
      expect(find.byType(LibraryReflowUnitView), findsWidgets);
      expect(find.byType(LibraryBookPageCanvas), findsNothing);
      // Same width and typography as the page: the same line starts it.
      expect(state.currentPosition, page.start);

      // Back to pages without moving: the same page.
      state.setTextLayout(LibraryTextLayout.pages);
      await settlePages(tester);
      expect(state.textLayout, LibraryTextLayout.pages);
      expect(state.shownSpread!.first, page);
      expect(state.currentPosition, page.start);

      // Scroll on, then pages: the page holding the first line read.
      state.setTextLayout(LibraryTextLayout.scroll);
      await settlePages(tester);
      for (var i = 0; i < 3; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      await settlePages(tester, rounds: 2);
      final read = state.currentPosition!;
      expect(compare(read, page.end), greaterThan(0));
      state.setTextLayout(LibraryTextLayout.pages);
      await settlePages(tester);
      expect(spreadHolds(state.shownSpread!, read), isTrue);
      expect(state.currentPosition, read);
      expect(
        store.bookSettingsFor('local:switch')!.textLayout,
        LibraryTextLayout.pages,
      );
      await closePages(tester, store);
    });

    testWidgets('a typography change keeps the first words on the page, '
        'however many changes', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:font',
          location: 'txt:450:0',
          fraction: 0.45,
        ),
      );
      await openPages(tester, textReader(store, progressKey: 'local:font'));
      final state = bookState(tester);
      state.gamepadBindings.down!();
      await turned(tester);
      final start = state.shownSpread!.first.start;
      expect(start.chapter, 2);
      for (final size in <double>[22, 26, 30, 14, 18]) {
        store.updateSettings(store.settings.copyWith(fontSize: size));
        // The page shown before stays until the new one is laid out.
        await tester.pump();
        expect(find.byType(LibraryBookPageCanvas), findsWidgets);
        await settlePages(tester, rounds: 2);
        final page = state.shownSpread!.first;
        expect(state.paginator!.style.fontSize, size);
        expect(holds(page, start), isTrue, reason: 'font $size: $page');
        expect(state.currentPosition, start, reason: 'font $size');
      }
      // Margins too.
      store.updateSettings(store.settings.copyWith(margin: 48));
      await settlePages(tester, rounds: 2);
      expect(holds(state.shownSpread!.first, start), isTrue);
      await tester.pump(const Duration(seconds: 1));
      expect(store.progressFor('local:font')!.location, txt(start));
      await closePages(tester, store);
    });

    testWidgets('a rotation keeps the first words; landscape shows a spread', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:rotate',
          location: 'txt:610:0',
          fraction: 0.6,
        ),
      );
      await openPages(tester, textReader(store, progressKey: 'local:rotate'));
      final state = bookState(tester);
      state.gamepadBindings.down!();
      await turned(tester);
      final start = state.shownSpread!.first.start;
      tester.view.physicalSize = landscape;
      await tester.pump();
      // Pages of the former size are not shown in the new one.
      expect(find.byType(LibraryBookPageCanvas), findsNothing);
      expect(find.text(en('paginating')), findsWidgets);
      await settlePages(tester);
      final spread = state.shownSpread!;
      expect(spread.doublePage, isTrue);
      expect(spreadHolds(spread, start), isTrue, reason: '$spread');
      expect(state.currentPosition, start);
      tester.view.physicalSize = portrait;
      await tester.pump();
      await settlePages(tester);
      expect(state.shownSpread!.doublePage, isFalse);
      expect(holds(state.shownSpread!.first, start), isTrue);
      expect(state.currentPosition, start);
      await closePages(tester, store);
    });

    testWidgets('a theme change paints the same pages in its colours', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await openPages(tester, textReader(store, progressKey: 'local:theme'));
      final state = bookState(tester);
      final page = state.shownSpread!.first;
      final paginator = state.paginator;
      store.updateSettings(
        store.settings.copyWith(theme: LibraryReaderTheme.sepia),
      );
      await tester.pump();
      // Not laid out again: the same page, painted in sepia.
      expect(state.shownSpread!.first, page);
      expect(identical(state.paginator, paginator), isTrue);
      expect(state.paginator!.style.palette.theme, LibraryReaderTheme.sepia);
      final canvas = tester.widget<LibraryBookPageCanvas>(
        find.byType(LibraryBookPageCanvas).first,
      );
      expect(canvas.palette.theme, LibraryReaderTheme.sepia);
      await closePages(tester, store);
    });
  });

  group('spreads and direction', () {
    testWidgets('landscape: the first page alone on the right, then pairs; '
        '"Pages N and N+1 of M"', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      await openPages(tester, textReader(store, progressKey: 'local:spread'));
      final state = bookState(tester);
      final cover = state.shownSpread!;
      expect(cover.doublePage, isTrue);
      expect(cover.pages, hasLength(1));
      expect(cover.right, cover.first);
      expect(cover.left, isNull);
      // Two halves of the safe area, one paginator for both.
      expect(state.paginator!.pageSize, const Size(450, 600));
      state.gamepadBindings.right!();
      await turned(tester);
      final pair = state.shownSpread!;
      expect(pair.pages.map((page) => page.indexInChapter), <int>[1, 2]);
      expect(pair.left, pair.pages[0]);
      expect(pair.right, pair.pages[1]);
      final total = state.paginator!.pageCountOf(0)!;
      expect(
        find.text(
          enFormat('pagesOfTotal', {'first': 2, 'second': 3, 'total': total}),
        ),
        findsOneWidget,
      );
      // Never two pages without double page.
      setLayout(store, doublePage: LibraryDoublePageMode.never);
      await settlePages(tester);
      expect(state.shownSpread!.doublePage, isFalse);
      expect(state.paginator!.pageSize, const Size(900, 600));
      // Without the first page alone, pages pair 1-2 from the start.
      setLayout(
        store,
        doublePage: LibraryDoublePageMode.auto,
        firstPageAlone: false,
      );
      state.gamepadBindings.leftBumper!();
      await settlePages(tester);
      expect(state.shownSpread!.pages.map((page) => page.indexInChapter), <int>[
        0,
        1,
      ]);
      await closePages(tester, store);
    });

    testWidgets('right to left: the next page on the left, the pager and the '
        'taps mirrored', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      await openPages(
        tester,
        textReader(store, progressKey: 'local:rtl', rightToLeft: true),
      );
      final state = bookState(tester);
      // The first page alone on the left (its book side right to left).
      final cover = state.shownSpread!;
      expect(cover.left, cover.first);
      expect(cover.right, isNull);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isTrue);
      // The left third turns forward.
      await tester.tapAt(const Offset(40, 300));
      await turned(tester);
      final pair = state.shownSpread!;
      expect(pair.pages.map((page) => page.indexInChapter), <int>[1, 2]);
      // The next page (2) is on the left.
      expect(pair.left, pair.pages[1]);
      expect(pair.right, pair.pages[0]);
      // Right on the controller: backward.
      state.gamepadBindings.right!();
      await turned(tester);
      expect(state.shownSpread!.first.indexInChapter, 0);
      // A rightward drag turns forward (the curl takes it).
      final gesture = await tester.startGesture(const Offset(200, 300));
      for (var i = 0; i < 10; i++) {
        await gesture.moveBy(const Offset(40, 0));
        await tester.pump(const Duration(milliseconds: 30));
      }
      expect(state.curl!.isDragging, isTrue);
      expect(state.curl!.direction, LibraryPageTurnDirection.forward);
      await gesture.up();
      await turned(tester);
      expect(state.shownSpread!.first.indexInChapter, 1);
      await closePages(tester, store);
    });

    testWidgets('the book direction has no effect on the scroll layout', (
      tester,
    ) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      setLayout(store, textLayout: LibraryTextLayout.scroll);
      await openPages(
        tester,
        textReader(store, progressKey: 'local:rtl-scroll', rightToLeft: true),
      );
      final state = bookState(tester);
      expect(state.textLayout, LibraryTextLayout.scroll);
      expect(find.byType(PageView), findsNothing);
      state.gamepadBindings.right!();
      await frames(tester);
      // Right scrolls down, as for any book.
      expect(state.currentPosition!.block, greaterThan(0));
      await closePages(tester, store);
    });
  });

  group('page turns', () {
    testWidgets('curl: a page curls 380 ms then the next page is shown; no '
        'second turn meanwhile', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await openPages(tester, textReader(store, progressKey: 'local:curl'));
      final state = bookState(tester);
      expect(
        tester
            .widget<LibraryPageCurlLayer>(find.byType(LibraryPageCurlLayer))
            .enabled,
        isTrue,
      );
      state.gamepadBindings.down!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 150));
      expect(state.curl!.isActive, isTrue);
      expect(find.byType(LibraryPageCurl), findsOneWidget);
      // Pressed again during the curl: ignored.
      state.gamepadBindings.down!();
      state.gamepadBindings.right!();
      await turned(tester);
      expect(state.shownSpread!.first.indexInChapter, 1);
      expect(find.byType(LibraryPageCurl), findsNothing);
      expect(state.pageTextures!.textures, greaterThan(0));
      state.gamepadBindings.up!();
      await turned(tester);
      expect(state.shownSpread!.first.indexInChapter, 0);
      await closePages(tester, store);
    });

    testWidgets('slide: the pager slides 220 ms', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      setLayout(store, turnStyle: LibraryPageTurnStyle.slide);
      await openPages(tester, textReader(store, progressKey: 'local:slide'));
      final state = bookState(tester);
      expect(
        tester
            .widget<LibraryPageCurlLayer>(find.byType(LibraryPageCurlLayer))
            .enabled,
        isFalse,
      );
      state.gamepadBindings.down!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      final pager = tester.widget<PageView>(find.byType(PageView)).controller!;
      expect(pager.page! % 1, isNot(0));
      expect(find.byType(LibraryPageCurl), findsNothing);
      await turned(tester);
      expect(state.shownSpread!.first.indexInChapter, 1);
      // A swipe slides too (the pager's spring settles in about 1 s).
      await tester.fling(find.byType(PageView), const Offset(-300, 0), 1000);
      for (var i = 0; i < 12; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      await settlePages(tester, rounds: 2);
      expect(state.shownSpread!.first.indexInChapter, 2);
      await closePages(tester, store);
    });

    testWidgets('none, and Reduce Motion with the curl: the page is shown at '
        'once', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      setLayout(store, turnStyle: LibraryPageTurnStyle.none);
      await openPages(tester, textReader(store, progressKey: 'local:none'));
      var state = bookState(tester);
      state.gamepadBindings.down!();
      // No animation: shown before any frame.
      expect(state.shownSpread!.first.indexInChapter, 1);
      await settlePages(tester, rounds: 1);
      await closePages(tester, store);

      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      final (reduced, _) = await createStore(tester);
      expect(reduced.settings.turnStyle, LibraryPageTurnStyle.curl);
      await openPages(tester, textReader(reduced, progressKey: 'local:rm'));
      state = bookState(tester);
      expect(
        tester
            .widget<LibraryPageCurlLayer>(find.byType(LibraryPageCurlLayer))
            .enabled,
        isFalse,
      );
      await tester.tapAt(Offset(portrait.width - 20, 400));
      expect(state.shownSpread!.first.indexInChapter, 1);
      expect(find.byType(LibraryPageCurl), findsNothing);
      await settlePages(tester, rounds: 1);
      await closePages(tester, reduced);
    });

    testWidgets('next and previous cross chapters', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      setLayout(store, turnStyle: LibraryPageTurnStyle.none);
      await openPages(tester, textReader(store, progressKey: 'local:cross'));
      final state = bookState(tester);
      // RB: next section; up: the last page of the previous one.
      state.gamepadBindings.rightBumper!();
      await settlePages(tester);
      expect(
        state.shownSpread!.first.start,
        const LibraryReflowPosition(1, 0, 0),
      );
      state.gamepadBindings.up!();
      await settlePages(tester);
      final last = state.shownSpread!.first;
      expect(last.chapter, 0);
      expect(last.isLastInChapter, isTrue);
      expect(last.indexInChapter, state.paginator!.pageCountOf(0)! - 1);
      state.gamepadBindings.down!();
      await settlePages(tester);
      expect(
        state.shownSpread!.first.start,
        const LibraryReflowPosition(1, 0, 0),
      );
      // LB: back to section 0.
      state.gamepadBindings.leftBumper!();
      await settlePages(tester);
      expect(state.shownSpread!.first.start, LibraryReflowPosition.start);
      // Nothing before the first page.
      state.gamepadBindings.up!();
      await settlePages(tester);
      expect(state.shownSpread!.first.start, LibraryReflowPosition.start);
      await closePages(tester, store);
    });
  });

  group('controller, links and VoiceOver', () {
    // Phase 7 (docs/library-books-3d-plan.md § 3.10) gives Y its role: it
    // was left free (`y` null) until the bookmarks came; it now adds or
    // removes the bookmark of the spread shown, which replaces that
    // `isNull` expectation.
    testWidgets('the controller: left/right by side, up/down in reading order, '
        'bumpers by chapter, X the contents, Y the bookmark', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      setLayout(store, turnStyle: LibraryPageTurnStyle.none);
      final document = await openEpub(tester, chapter1: longChapter());
      await openPages(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:pad',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      final state = bookState(tester);
      final bindings = state.gamepadBindings;
      expect(bindings.x, isNotNull);
      // Y marks the page shown at its CFI; Y again removes the mark.
      bindings.y!();
      await tester.pump();
      expect(
        store.bookmarksFor('local:pad').single.location,
        startsWith('epubcfi('),
      );
      expect(state.bookmarkShown, isTrue);
      bindings.y!();
      await tester.pump();
      expect(store.bookmarksFor('local:pad'), isEmpty);
      expect(state.bookmarkShown, isFalse);
      bindings.right!();
      expect(state.shownSpread!.first.indexInChapter, 1);
      state.gamepadBindings.down!();
      expect(state.shownSpread!.first.indexInChapter, 2);
      state.gamepadBindings.left!();
      expect(state.shownSpread!.first.indexInChapter, 1);
      state.gamepadBindings.up!();
      expect(state.shownSpread!.first.indexInChapter, 0);
      state.gamepadBindings.rightBumper!();
      await settlePages(tester);
      expect(state.shownSpread!.chapter, 1);
      state.gamepadBindings.x!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text(en('tableOfContents')), findsWidgets);
      expect(find.text('Chapter One'), findsWidgets);
      await tester.tap(find.text('Chapter One').last);
      await tester.pump();
      await settlePages(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(state.shownSpread!.chapter, 0);
      expect(state.currentPosition!.chapter, 0);
      await closePages(tester, store);
    });

    testWidgets('links: an internal link turns to its target; an https link '
        'opens after asking', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final document = await openEpub(
        tester,
        chapter2: xhtml(
          '<h2>Chapter Two</h2><p><a href="ch1.xhtml#part2">earlier</a></p>'
          '<p><a href="https://example.org/a">website</a></p>',
        ),
      );
      final cfi = (await tester.runAsync(() => document.cfiFor(1, 0, 0)))!;
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:links',
          location: cfi,
          fraction: 0.6,
        ),
      );
      final launched = <Uri>[];
      await openPages(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:links',
          title: 'Links',
          store: store,
          launchExternal: (uri) async {
            launched.add(uri);
            return true;
          },
        ),
      );
      final state = bookState(tester);
      final page = state.shownSpread!.first;
      expect(page.chapter, 1);
      // The page fills the screen: page coordinates are screen coordinates.
      Offset linkOf(int block) {
        final slice = page.slices.firstWhere(
          (slice) => slice.unit.block == block,
        );
        return Offset(slice.rect.left + 4, slice.rect.center.dy);
      }

      final website = linkOf(2);
      expect(state.paginator!.linkAt(page, website), 'https://example.org/a');
      await tester.tapAt(website);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text(en('openLinkTitle')), findsOneWidget);
      await tester.tap(find.text(en('openLink')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(launched, <Uri>[Uri.parse('https://example.org/a')]);

      await tester.tapAt(linkOf(1));
      await tester.pump();
      await settlePages(tester);
      expect(state.currentPosition, const LibraryReflowPosition(0, 2, 0));
      expect(holds(state.shownSpread!.first, state.currentPosition!), isTrue);
      await closePages(tester, store);
    });

    testWidgets('VoiceOver reads the text of each page, in reading order', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      setLayout(store, turnStyle: LibraryPageTurnStyle.none);
      await openPages(
        tester,
        textReader(store, progressKey: 'local:labels', rightToLeft: true),
      );
      final state = bookState(tester);
      state.gamepadBindings.down!();
      await settlePages(tester);
      final spread = state.shownSpread!;
      expect(spread.isPair, isTrue);
      final paginator = state.paginator!;
      for (final (index, page) in spread.pages.indexed) {
        final text = paginator.textOf(page);
        expect(text, contains('word'));
        final canvas = find.byWidgetPredicate(
          (widget) => widget is LibraryBookPageCanvas && widget.page == page,
        );
        expect(canvas, findsOneWidget);
        final data = tester.getSemantics(canvas).getSemanticsData();
        expect(data.label, text);
        // Right to left the first page is on the right, read first.
        expect(
          tester.widget<LibraryBookPageCanvas>(canvas).readingOrder,
          index,
        );
      }
      expect(
        tester
            .getCenter(
              find.byWidgetPredicate(
                (widget) =>
                    widget is LibraryBookPageCanvas &&
                    widget.page == spread.first,
              ),
            )
            .dx,
        greaterThan(landscape.width / 2),
      );
      await closePages(tester, store);
      semantics.dispose();
    });
  });

  group('settings and resources', () {
    testWidgets('precedence: session, then the book, then the global setting', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.updateBookSettings(
        'local:book-layout',
        const LibraryReaderBookSettings(textLayout: LibraryTextLayout.scroll),
      );
      await openPages(
        tester,
        textReader(store, progressKey: 'local:book-layout'),
      );
      final state = bookState(tester);
      expect(state.textLayout, LibraryTextLayout.scroll);
      // The global setting does not override the book's.
      setLayout(store, textLayout: LibraryTextLayout.pages);
      await settlePages(tester);
      expect(state.textLayout, LibraryTextLayout.scroll);
      // The session's choice wins, and becomes the book's.
      state.setTextLayout(LibraryTextLayout.pages);
      await settlePages(tester);
      expect(state.textLayout, LibraryTextLayout.pages);
      expect(
        store.bookSettingsFor('local:book-layout')!.textLayout,
        LibraryTextLayout.pages,
      );
      // "Revert to general settings": the global one applies again.
      setLayout(store, textLayout: LibraryTextLayout.scroll);
      await settlePages(tester);
      expect(state.textLayout, LibraryTextLayout.pages);
      store.clearBookSettings('local:book-layout');
      await settlePages(tester);
      expect(state.textLayout, LibraryTextLayout.scroll);
      await closePages(tester, store);
    });

    testWidgets('leaving the pages layout stops the pagination and releases '
        'the textures; closing disposes them', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await openPages(tester, textReader(store, progressKey: 'local:release'));
      final state = bookState(tester);
      state.gamepadBindings.down!();
      await turned(tester);
      final textures = state.pageTextures!;
      expect(textures.textures, greaterThan(0));
      final paginator = state.paginator!;
      state.setTextLayout(LibraryTextLayout.scroll);
      await settlePages(tester);
      expect(textures.textures, 0);
      expect(textures.pendingRenders, 0);
      for (var chapter = 0; chapter < 5; chapter++) {
        final stats = paginator.statsOf(chapter);
        if (stats == null) continue;
        expect(stats.complete || stats.cancelled, isTrue, reason: '$chapter');
      }
      state.setTextLayout(LibraryTextLayout.pages);
      await settlePages(tester);
      state.gamepadBindings.down!();
      await turned(tester);
      expect(textures.textures, greaterThan(0));
      await closePages(tester, store);
      expect(textures.isDisposed, isTrue);
    });

    testWidgets('reading through many chapters keeps few chapters paginated '
        'and few textures', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      // 20 sections of 200 short paragraphs.
      final text = List<String>.generate(4000, (i) => 'Line $i').join('\n\n');
      await openPages(
        tester,
        textReader(
          store,
          progressKey: 'local:long',
          open: () async =>
              LibraryTextReflowSource(LibraryTextDocument.fromText(text)),
        ),
      );
      final state = bookState(tester);
      for (var chapter = 1; chapter <= 10; chapter++) {
        state.gamepadBindings.rightBumper!();
        await settlePages(tester, rounds: 2);
        state.gamepadBindings.down!();
        await turned(tester);
        expect(state.shownSpread!.chapter, chapter);
        final paginator = state.paginator!;
        final paginated = <int>[
          for (var c = 0; c < 20; c++)
            if (paginator.pageCountOf(c) != null) c,
        ];
        // The current chapter, the next one and the few used last.
        expect(paginated.length, lessThanOrEqualTo(paginator.maxChapters));
        expect(paginated, contains(chapter));
        // The spread shown and its neighbours.
        expect(state.pageTextures!.textures, lessThanOrEqualTo(6));
      }
      await closePages(tester, store);
    });
  });

  group('spread rule', () {
    testWidgets('pairs: alone at the book start (TXT) or at every chapter '
        '(EPUB), right to left halves, the last page alone, across chapters', (
      tester,
    ) async {
      final paginator = LibraryReflowPaginator(
        source: textSource(),
        style: const LibraryReflowStyle(
          palette: LibraryReaderPalette.light,
          fontSize: 18,
          lineHeight: 1.5,
          fontFamily: LibraryReaderFontFamily.serif,
          justify: true,
          margin: 16,
        ),
        pageSize: const Size(420, 600),
        padding: const EdgeInsets.fromLTRB(24, 50, 24, 16),
        textScaler: TextScaler.noScaling,
      );
      final first = (await tester.runAsync(() => paginator.paginate(0)))!;
      final second = (await tester.runAsync(() => paginator.paginate(1)))!;
      expect(first.length, greaterThan(4));
      const text = LibraryBookSpreadRule(
        doublePage: true,
        firstPageAlone: true,
        rightToLeft: false,
        firstPageAloneInEveryChapter: false,
      );
      // The first page of the book alone on the right, then 2-3.
      final cover = text.holdingNow(paginator, first[0])!;
      expect(cover.pages, <LibraryReflowPageSpec>[first[0]]);
      expect((cover.left, cover.right), (null, first[0]));
      expect(text.hasBefore(cover), isFalse);
      final pair = text.holdingNow(paginator, first[2])!;
      expect(pair.pages, <LibraryReflowPageSpec>[first[1], first[2]]);
      expect((pair.left, pair.right), (first[1], first[2]));
      expect(text.holdingNow(paginator, first[1]), pair);
      // A plain text section flows on: it starts a pair.
      expect(
        text.holdingNow(paginator, second[0])!.pages,
        <LibraryReflowPageSpec>[second[0], second[1]],
      );
      // An EPUB chapter opens alone, like the book.
      const epub = LibraryBookSpreadRule(
        doublePage: true,
        firstPageAlone: true,
        rightToLeft: false,
        firstPageAloneInEveryChapter: true,
      );
      expect(
        epub.holdingNow(paginator, second[0])!.pages,
        <LibraryReflowPageSpec>[second[0]],
      );
      // Right to left: the next page on the left, the cover on the left.
      const rtl = LibraryBookSpreadRule(
        doublePage: true,
        firstPageAlone: true,
        rightToLeft: true,
        firstPageAloneInEveryChapter: false,
      );
      final rtlPair = rtl.holdingNow(paginator, first[1])!;
      expect((rtlPair.left, rtlPair.right), (first[2], first[1]));
      final rtlCover = rtl.holdingNow(paginator, first[0])!;
      expect((rtlCover.left, rtlCover.right), (first[0], null));
      // The last page of a chapter: alone on the other side when odd.
      final last = text.holdingNow(paginator, first.last)!;
      if (first.length.isEven) {
        expect(last.pages, <LibraryReflowPageSpec>[first.last]);
        expect((last.left, last.right), (first.last, null));
      } else {
        expect(last.pages, hasLength(2));
      }
      // Neighbours across chapters, at once when laid out.
      expect(text.afterNow(paginator, last)!.first, second[0]);
      expect(
        text.beforeNow(paginator, text.holdingNow(paginator, second[0])!)!.last,
        first.last,
      );
      expect(text.hasAfter(last, 5), isTrue);
      // One page each without double page.
      const single = LibraryBookSpreadRule(
        doublePage: false,
        firstPageAlone: true,
        rightToLeft: false,
        firstPageAloneInEveryChapter: true,
      );
      final one = single.holdingNow(paginator, first[3])!;
      expect(one.doublePage, isFalse);
      expect(one.pages, <LibraryReflowPageSpec>[first[3]]);
      expect(single.afterNow(paginator, one)!.first, first[4]);
      expect(
        await tester.runAsync(() => single.before(paginator, one)),
        single.holdingNow(paginator, first[2]),
      );
      paginator.dispose();
    });
  });

  // The 440 contracts of test/library_reader_book_test.dart and
  // test/library_reader_back_button_test.dart (now set to the continuous
  // scroll there), in the pages layout.
  group('440 contracts in the pages layout', () {
    testWidgets('a saved location that fails to load is kept until the user '
        'turns a page', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:kept',
          location: 'txt:450:0',
          fraction: 0.45,
        ),
      );
      final source = _TestSource(textSource(), failResolve: true);
      await openPages(
        tester,
        textReader(store, progressKey: 'local:kept', open: () async => source),
      );
      final state = bookState(tester);
      expect(source.resolves, 1);
      expect(state.currentPosition, LibraryReflowPosition.start);
      expect(state.shownSpread!.first.start, LibraryReflowPosition.start);
      expect(
        find.descendant(
          of: find.byType(SnackBar),
          matching: find.text(en('positionNotRestored')),
        ),
        findsWidgets,
      );
      await tester.pump(const Duration(seconds: 2));
      expect(store.progressFor('local:kept')!.location, 'txt:450:0');
      state.gamepadBindings.down!();
      await turned(tester);
      final shown = state.shownSpread!.first.start;
      expect(shown, isNot(LibraryReflowPosition.start));
      await tester.pump(const Duration(seconds: 1));
      expect(store.progressFor('local:kept')!.location, txt(shown));
      await closePages(tester, store);
    });

    testWidgets('a location unknown to the book starts over and is replaced', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:unknown',
          location: 'epubcfi(/6/4[ch2]!/4/2:0)',
          fraction: 0.5,
        ),
      );
      await openPages(tester, textReader(store, progressKey: 'local:unknown'));
      final state = bookState(tester);
      expect(state.currentPosition, LibraryReflowPosition.start);
      expect(state.shownSpread!.first.start, LibraryReflowPosition.start);
      expect(find.text(en('positionNotRestored')), findsNothing);
      await tester.pump(const Duration(seconds: 1));
      expect(store.progressFor('local:unknown')!.location, 'txt:0:0');
      await closePages(tester, store);
    });

    testWidgets('a chapter the pages cannot be laid out from shows the error; '
        'A retries', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final source = _TestSource(textSource(), failNextLoads: 1);
      await openPages(
        tester,
        textReader(store, progressKey: 'local:retry', open: () async => source),
      );
      final state = bookState(tester);
      expect(state.shownSpread, isNull);
      expect(find.text(en('issueTooLarge')), findsOneWidget);
      // The bars stay with their Back while nothing can be read.
      expect(find.byTooltip(en('back')).hitTestable(), findsOneWidget);
      state.gamepadBindings.select!();
      await settlePages(tester);
      expect(find.text(en('issueTooLarge')), findsNothing);
      expect(state.shownSpread!.first.start, LibraryReflowPosition.start);
      await closePages(tester, store);
    });

    testWidgets('a jump to a chapter that fails to load says so; the page '
        'stays', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await openPages(
        tester,
        textReader(
          store,
          progressKey: 'local:fail',
          open: () async => _TestSource(textSource(), failingChapter: 3),
        ),
      );
      final state = bookState(tester);
      final page = state.shownSpread!.first;
      final slider = tester.widget<Slider>(find.byType(Slider));
      slider.onChangeStart!(0.7);
      slider.onChangeEnd!(0.7);
      await settlePages(tester);
      final snackBar = find.byType(SnackBar);
      expect(
        find.descendant(of: snackBar, matching: find.text(en('issueTooLarge'))),
        findsWidgets,
      );
      expect(
        find.descendant(
          of: snackBar,
          matching: find.textContaining('chapter 3 refused'),
        ),
        findsWidgets,
      );
      expect(state.shownSpread!.first, page);
      expect(state.currentPosition!.chapter, 0);
      await closePages(tester, store);
    });

    testWidgets('one Back; the floating Back neither turns the page nor shows '
        'the bars; one tap on it saves the page shown', (tester) async {
      useSurface(tester, size: const Size(393, 852));
      tester.view.padding = const FakeViewPadding(top: 59, bottom: 34);
      final (store, _) = await createStore(tester);
      await openPages(
        tester,
        PopScope<Object?>(
          canPop: false,
          child: textReader(store, progressKey: 'local:stay'),
        ),
      );
      final state = bookState(tester);
      expect(state.chromeVisible, isTrue);
      expect(find.byTooltip(en('back')).hitTestable(), findsOneWidget);
      state.gamepadBindings.down!();
      await turned(tester);
      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.chromeVisible, isFalse);
      expect(find.byTooltip(en('back')).hitTestable(), findsOneWidget);
      final floating = find.byType(LibraryReaderFloatingBackButton);
      final before = state.shownSpread!.first;
      // A tap reaching the page there (left third) would turn back.
      await tester.tap(floating);
      await turned(tester);
      expect(state.shownSpread!.first, before);
      expect(state.chromeVisible, isFalse);
      await closePages(tester, store);

      // Without the PopScope: one tap saves the page shown and closes.
      final (second, _) = await createStore(tester);
      await openPages(tester, textReader(second, progressKey: 'local:leave'));
      final reading = bookState(tester);
      for (var i = 0; i < 2; i++) {
        reading.gamepadBindings.down!();
        await turned(tester);
      }
      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(milliseconds: 300));
      final shown = reading.shownSpread!.first.start;
      await tester.tap(find.byType(LibraryReaderFloatingBackButton));
      expect(second.progressFor('local:leave')!.location, txt(shown));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      expect(tester.takeException(), isNull);
      await closePages(tester, second);
    });

    testWidgets('a pop right after a turn saves at once, then freezes', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final navigator = await pumpReader(
        tester,
        textReader(store, progressKey: 'local:quick'),
        home: StoreWatcher(store: store, progressKey: 'local:quick'),
      );
      await settlePages(tester);
      await tester.pump(const Duration(seconds: 1));
      final state = bookState(tester);
      state.gamepadBindings.down!();
      await turned(tester);
      final shown = state.shownSpread!.first.start;
      final location = txt(shown);
      // Within the 800 ms save delay (the iOS back swipe pops directly).
      navigator.currentState!.pop();
      expect(store.progressFor('local:quick')!.location, location);
      await tester.pump();
      // Rotated back to landscape while it leaves: no new pages, the saved
      // position does not move.
      tester.view.physicalSize = landscape;
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 800));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      expect(tester.takeException(), isNull);
      expect(store.progressFor('local:quick')!.location, location);
      expect(find.text('home $location'), findsOneWidget);
      await closePages(tester, store);
    });
  });
}

/// A TXT source that can fail: [failResolve] (saved locations cannot be
/// resolved for now: the worker stopped), [failingChapter] (never loads),
/// [failNextLoads] (the loads after the reader's opening fail that many
/// times; the chapters are not kept loaded meanwhile).
class _TestSource implements LibraryReflowSource {
  _TestSource(
    this._inner, {
    this.failResolve = false,
    this.failingChapter,
    this.failNextLoads = 0,
  });

  final LibraryTextReflowSource _inner;
  final bool failResolve;
  final int? failingChapter;
  int failNextLoads;
  int resolves = 0;
  int _loads = 0;

  Future<List<LibraryTextBlock>> _refused(int chapter) =>
      Future<List<LibraryTextBlock>>.error(
        LibraryBookException(
          LibraryBookIssue.tooLarge,
          detail: 'chapter $chapter refused',
        ),
      );

  @override
  int get chapterCount => _inner.chapterCount;

  @override
  bool get separatesChapters => _inner.separatesChapters;

  @override
  List<LibraryReflowTocEntry> get toc => _inner.toc;

  @override
  Future<List<LibraryTextBlock>> loadChapter(int chapter) {
    _loads++;
    if (chapter == failingChapter) return _refused(chapter);
    if (_loads > 1 && failNextLoads > 0) {
      failNextLoads--;
      return _refused(chapter);
    }
    return _inner.loadChapter(chapter);
  }

  @override
  List<LibraryTextBlock>? loadedChapter(int chapter) =>
      chapter == failingChapter || failNextLoads > 0
      ? null
      : _inner.loadedChapter(chapter);

  @override
  String locationFor(LibraryReflowPosition position) =>
      _inner.locationFor(position);

  @override
  Future<LibraryReflowPosition?> resolveLocation(String location) {
    resolves++;
    if (failResolve) {
      return Future<LibraryReflowPosition?>.error(
        StateError('library-epub worker exited'),
      );
    }
    return _inner.resolveLocation(location);
  }

  @override
  double fractionFor(LibraryReflowPosition position) =>
      _inner.fractionFor(position);

  @override
  Future<LibraryReflowPosition> positionAtFraction(double fraction) =>
      _inner.positionAtFraction(fraction);

  @override
  Future<LibraryReflowPosition?> resolveLink(String href) =>
      _inner.resolveLink(href);

  @override
  Future<Uint8List> resource(String href) => _inner.resource(href);

  @override
  Future<void> close() => _inner.close();
}

/// A TXT source whose chapters are read only once [open] is called (the
/// first read, by the reader's opening, is immediate).
class _GatedSource implements LibraryReflowSource {
  _GatedSource(this._inner);

  final LibraryTextReflowSource _inner;
  final Completer<void> _gate = Completer<void>();
  int _loads = 0;

  void open() => _gate.complete();

  @override
  int get chapterCount => _inner.chapterCount;

  @override
  bool get separatesChapters => _inner.separatesChapters;

  @override
  List<LibraryReflowTocEntry> get toc => _inner.toc;

  @override
  Future<List<LibraryTextBlock>> loadChapter(int chapter) async {
    if (_loads++ > 0) await _gate.future;
    return _inner.loadChapter(chapter);
  }

  @override
  List<LibraryTextBlock>? loadedChapter(int chapter) =>
      _gate.isCompleted ? _inner.loadedChapter(chapter) : null;

  @override
  String locationFor(LibraryReflowPosition position) =>
      _inner.locationFor(position);

  @override
  Future<LibraryReflowPosition?> resolveLocation(String location) =>
      _inner.resolveLocation(location);

  @override
  double fractionFor(LibraryReflowPosition position) =>
      _inner.fractionFor(position);

  @override
  Future<LibraryReflowPosition> positionAtFraction(double fraction) =>
      _inner.positionAtFraction(fraction);

  @override
  Future<LibraryReflowPosition?> resolveLink(String href) =>
      _inner.resolveLink(href);

  @override
  Future<Uint8List> resource(String href) => _inner.resource(href);

  @override
  Future<void> close() => _inner.close();
}
