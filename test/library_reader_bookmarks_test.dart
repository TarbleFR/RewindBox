// Build 447 bookmarks of the Library readers (docs/library-books-3d-plan.md
// § 3.7, § 3.10, phase 7): Y adds or removes the bookmark of the position
// shown in the three readers (page reader `page:N`, online chapters with
// their chapter, PDF `page:N` with its rendering injected, EPUB/TXT at the
// start of the spread or of the line being read), the ribbon and its
// option, the bookmarks sheet (empty state, add, open, delete), the limit
// of 500 per title, and the labels in French and Traditional Chinese. Real
// readers, store, navigator and page curl (painter); no device.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/library_pdf_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_bookmarks.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_chrome.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_gamepad.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_reader_pdf_modes_test.dart'
    show FakeOpener, mockPathProvider, rendered;
import 'library_reader_test_support.dart';

String tr(String language, String key) =>
    LibraryReaderLocale.values[language]![key]!;

String en(String key) => tr('en', key);

String format(String language, String key, Map<String, Object> values) {
  var text = tr(language, key);
  values.forEach((name, value) => text = text.replaceAll('{$name}', '$value'));
  return text;
}

LibraryPageReaderScreenState pageState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

LibraryBookReaderScreenState bookState(WidgetTester tester) => tester
    .state<LibraryBookReaderScreenState>(find.byType(LibraryBookReaderScreen));

LibraryPdfReaderScreenState pdfState(WidgetTester tester) => tester
    .state<LibraryPdfReaderScreenState>(find.byType(LibraryPdfReaderScreen));

LibraryBookmarkRibbon ribbon(WidgetTester tester) =>
    tester.widget<LibraryBookmarkRibbon>(find.byType(LibraryBookmarkRibbon));

/// Single pages turned without animation: every turn is immediate.
void plainTurns(LibraryReadingStore store) => store.updateSettings(
  store.settings.copyWith(
    turnStyle: LibraryPageTurnStyle.none,
    doublePage: LibraryDoublePageMode.never,
  ),
);

/// The toolbar button with this tooltip.
Finder toolbarButton(String tooltip) => find.byWidgetPredicate(
  (widget) => widget is LibraryReaderIconButton && widget.tooltip == tooltip,
);

/// Runs the action of the toolbar's Bookmarks button (shown or not) and
/// lets the sheet slide in.
Future<void> openBookmarks(
  WidgetTester tester, {
  String language = 'en',
}) async {
  tester
      .widget<LibraryReaderIconButton>(toolbarButton(tr(language, 'bookmarks')))
      .onPressed!();
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
}

Future<void> closeSheet(WidgetTester tester) async {
  Navigator.of(tester.element(find.byType(LibraryReaderBookmarksSheet))).pop();
  await sheetClosed(tester);
}

/// Runs the exit of a sheet to its end (B pops it asynchronously:
/// `Navigator.maybePop` asks the route first).
Future<void> sheetClosed(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
  }
}

/// The message [text] at the bottom of the reader (the snack bar is also
/// laid out, hidden, in the route below). A message asked while another is
/// shown comes once that one has left: [wait] lets it.
Future<Finder> message(
  WidgetTester tester,
  String text, {
  bool wait = false,
}) async {
  if (wait) await tester.pump(const Duration(seconds: 1));
  return find.descendant(of: find.byType(SnackBar), matching: find.text(text));
}

/// The controller actions of the bookmarks sheet (its own modal layer).
LibraryReaderGamepadBindings sheetBindings(WidgetTester tester) => tester
    .widget<LibraryReaderGamepadScope>(
      find.descendant(
        of: find.byType(LibraryReaderBookmarksSheet),
        matching: find.byType(LibraryReaderGamepadScope),
      ),
    )
    .bindings;

/// The row of [bookmark] in the sheet.
Finder bookmarkRow(LibraryBookmark bookmark) =>
    find.byKey(ValueKey<String>('bookmark-${bookmark.id}'));

Future<void> closeAll(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(Duration.zero);
  await settle(tester, rounds: 2);
  await flushStore(tester, store);
}

/// Runs the paginator's turns (zero-delay timers) and real I/O.
Future<void> settlePages(WidgetTester tester, {int rounds = 4}) async {
  for (var i = 0; i < rounds; i++) {
    await tester.pump(Duration.zero);
    await settle(tester, rounds: 1);
  }
}

/// 1000 paragraphs: five TXT sections of 200.
String sampleText() => List<String>.generate(
  1000,
  (i) => 'Paragraph $i ${List<String>.filled(40, 'word$i').join(' ')}',
).join('\n\n');

LibraryBookReaderScreen textReader(
  LibraryReadingStore store, {
  String progressKey = 'local:txt-marks',
}) => LibraryBookReaderScreen(
  open: () async =>
      LibraryTextReflowSource(LibraryTextDocument.fromText(sampleText())),
  progressKey: progressKey,
  title: 'Sample',
  store: store,
);

String txt(LibraryReflowPosition position) =>
    'txt:${position.chapter * 200 + position.block}:${position.offset}';

LibraryBookmark mark(
  String key,
  String id, {
  required int page,
  double fraction = 0.5,
}) => LibraryBookmark(
  id: id,
  key: key,
  location: 'page:$page',
  fraction: fraction,
  pageIndex: page,
  createdAt: DateTime.utc(2026, 10, 12),
);

void main() {
  setUpReaderEnvironment();
  setUp(() {
    // The page curl draws with its painter here (the shader has its own
    // tests).
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('Y toggles the bookmark of the position shown', () {
    testWidgets('page reader (CBZ): page:N, the ribbon, then removed', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            progressKey: 'local:cbz',
            pagesPerChapter: 6,
          ),
          store: store,
        ),
      );
      final state = pageState(tester);
      expect(ribbon(tester).visible, isFalse);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);

      state.gamepadBindings.y!();
      await tester.pump();
      final bookmark = store.bookmarksFor('local:cbz').single;
      expect(bookmark.location, 'page:1');
      expect(bookmark.pageIndex, 1);
      expect(bookmark.chapterId, isNull);
      expect(bookmark.fraction, closeTo(2 / 6, 1e-9));
      expect(bookmark.label, isNull, reason: 'the default label is shown');
      expect(await message(tester, en('bookmarkAdded')), findsWidgets);
      expect(ribbon(tester).visible, isTrue);
      // The toolbar's icon says it too (also while the ribbon is hidden).
      expect(
        tester
            .widget<LibraryReaderIconButton>(toolbarButton(en('bookmarks')))
            .icon,
        Icons.bookmark_rounded,
      );

      // Another page carries none; back on the marked one, the ribbon.
      state.gamepadBindings.right!();
      await frames(tester);
      expect(ribbon(tester).visible, isFalse);
      state.gamepadBindings.left!();
      await frames(tester);
      expect(ribbon(tester).visible, isTrue);

      state.gamepadBindings.y!();
      await tester.pump();
      expect(store.bookmarksFor('local:cbz'), isEmpty);
      expect(ribbon(tester).visible, isFalse);
      expect(
        await message(tester, en('bookmarkRemoved'), wait: true),
        findsWidgets,
      );
      await closeAll(tester, store);
    });

    testWidgets('page reader (online chapters): the chapter is part of the '
        'bookmark; one opens in its chapter', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      const key = 'online:source:manga';
      final content = FakePageContent(
        progressKey: key,
        chapterCount: 3,
        tracksChapters: true,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = pageState(tester);
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      state.gamepadBindings.y!();
      await tester.pump();
      // The next chapter, at the same page: its own bookmark.
      state.gamepadBindings.rightBumper!();
      await frames(tester);
      expect(state.controller.chapterIndex, 1);
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      expect(state.controller.page, 2);
      expect(ribbon(tester).visible, isFalse, reason: 'page 3 of chapter 1');
      state.gamepadBindings.y!();
      await tester.pump();
      final bookmarks = store.bookmarksFor(key);
      expect(bookmarks.map((bookmark) => bookmark.location), <String>[
        'page:2@c0',
        'page:2@c1',
      ]);
      expect(bookmarks.map((bookmark) => bookmark.chapterId), <String>[
        'c0',
        'c1',
      ]);
      expect(bookmarks.first.fraction, closeTo((0 + 3 / 5) / 3, 1e-9));
      expect(ribbon(tester).visible, isTrue);

      // The sheet names their chapters; the first opens in chapter 1.
      await openBookmarks(tester);
      expect(
        find.descendant(
          of: bookmarkRow(bookmarks.first),
          matching: find.text('Chapter 1'),
        ),
        findsOneWidget,
      );
      expect(
        find.descendant(
          of: bookmarkRow(bookmarks.first),
          matching: find.text(format('en', 'pageNumber', {'page': 3})),
        ),
        findsOneWidget,
      );
      await tester.tap(
        find.descendant(
          of: bookmarkRow(bookmarks.first),
          matching: find.text(
            format('en', 'bookmarkDefaultLabel', {'index': 1}),
          ),
        ),
      );
      await sheetClosed(tester);
      await frames(tester);
      expect(find.byType(LibraryReaderBookmarksSheet), findsNothing);
      expect(state.controller.chapterIndex, 0);
      expect(state.controller.page, 2);
      expect(ribbon(tester).visible, isTrue);
      await closeAll(tester, store);
    });

    testWidgets('page reader (spread): a bookmark on either page shows; Y '
        'removes it, then marks the first page', (tester) async {
      useSurface(tester); // Landscape: two pages, the cover alone.
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      // Made on page 3 alone (in portrait, say).
      store.addBookmark(mark('local:spread', 'p3', page: 2));
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:spread'),
          store: store,
        ),
      );
      final state = pageState(tester);
      expect(state.spreads!.doublePage, isTrue);
      expect(ribbon(tester).visible, isFalse, reason: 'the cover');
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      expect(state.controller.lastShownPage, 2);
      expect(ribbon(tester).visible, isTrue, reason: 'pages 2 and 3');

      state.gamepadBindings.y!();
      await tester.pump();
      expect(store.bookmarksFor('local:spread'), isEmpty);
      state.gamepadBindings.y!();
      await tester.pump();
      expect(store.bookmarksFor('local:spread').single.location, 'page:1');
      expect(ribbon(tester).visible, isTrue);
      await closeAll(tester, store);
    });

    testWidgets('PDF pages mode (rendering injected): page:N of the page '
        'shown, then removed; the sheet opens one', (tester) async {
      mockPathProvider();
      useSurface(tester, size: const Size(400, 800));
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      const key = 'local:pdf-marks';
      final opener = FakeOpener();
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '/missing-bookmarks.pdf',
          title: 'Manual',
          progressKey: key,
          store: store,
          openDocument: opener.call,
        ),
      );
      await rendered(tester);
      final reader = pdfState(tester);
      expect(reader.mode, LibraryPdfMode.pages);
      expect(reader.ready, isTrue);

      reader.gamepadBindings.y!();
      await tester.pump();
      final first = store.bookmarksFor(key).single;
      expect(first.location, 'page:0');
      expect(first.pageIndex, 0);
      expect(first.fraction, closeTo(1 / 12, 1e-9));
      expect(await message(tester, en('bookmarkAdded')), findsWidgets);
      expect(ribbon(tester).visible, isTrue);

      reader.gamepadBindings.right!();
      await tester.pump();
      expect(reader.pageNumber, 2);
      expect(ribbon(tester).visible, isFalse);
      reader.gamepadBindings.y!();
      await tester.pump();
      expect(
        store.bookmarksFor(key).map((bookmark) => bookmark.location),
        <String>['page:0', 'page:1'],
      );

      await openBookmarks(tester);
      expect(bookmarkRow(first), findsOneWidget);
      await tester.tap(
        find.text(format('en', 'bookmarkDefaultLabel', {'index': 1})),
      );
      await sheetClosed(tester);
      expect(reader.pageNumber, 1);
      expect(ribbon(tester).visible, isTrue);

      reader.gamepadBindings.y!();
      await tester.pump();
      expect(store.bookmarkAt(key, 'page:0'), isNull);
      expect(
        await message(tester, en('bookmarkRemoved'), wait: true),
        findsWidgets,
      );
      await closeAll(tester, store);
    });

    testWidgets('EPUB/TXT pages: the start of the spread (txt:b:o); a new '
        'typography keeps the ribbon on the page holding its words', (
      tester,
    ) async {
      useSurface(tester, size: const Size(400, 860));
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      await pumpReader(tester, textReader(store));
      await settlePages(tester);
      final state = bookState(tester);
      expect(state.textLayout, LibraryTextLayout.pages);
      final cover = state.shownSpread!.first.start;
      state.gamepadBindings.y!();
      await tester.pump();
      expect(store.bookmarksFor('local:txt-marks').single.location, txt(cover));
      expect(state.bookmarkShown, isTrue);
      expect(ribbon(tester).visible, isTrue);

      state.gamepadBindings.down!();
      await frames(tester);
      await settlePages(tester, rounds: 2);
      expect(state.bookmarkShown, isFalse);
      final second = state.shownSpread!.first.start;
      state.gamepadBindings.y!();
      await tester.pump();
      expect(
        store.bookmarksFor('local:txt-marks').map((b) => b.location),
        <String>[txt(cover), txt(second)],
      );

      // Larger text: other pages, the same words on screen.
      store.updateSettings(store.settings.copyWith(fontSize: 26));
      await settlePages(tester, rounds: 6);
      expect(state.shownSpread, isNotNull);
      expect(state.bookmarkShown, isTrue);
      expect(ribbon(tester).visible, isTrue);
      state.gamepadBindings.y!();
      await tester.pump();
      expect(
        store.bookmarksFor('local:txt-marks').map((b) => b.location),
        <String>[txt(cover)],
      );
      await closeAll(tester, store);
    });

    testWidgets('EPUB/TXT continuous scroll: the line being read', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(textLayout: LibraryTextLayout.scroll),
      );
      await pumpReader(tester, textReader(store, progressKey: 'local:line'));
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.textLayout, LibraryTextLayout.scroll);
      state.gamepadBindings.down!();
      await frames(tester);
      await settle(tester, rounds: 2);
      final line = state.currentPosition!;
      expect(line.offset + line.block, greaterThan(0));

      state.gamepadBindings.y!();
      await tester.pump();
      final bookmark = store.bookmarksFor('local:line').single;
      expect(bookmark.location, txt(line));
      expect(state.bookmarkShown, isTrue);
      expect(ribbon(tester).visible, isTrue);

      // A screen further: another line.
      state.gamepadBindings.right!();
      await frames(tester);
      await settle(tester, rounds: 2);
      expect(state.currentPosition, isNot(line));
      expect(state.bookmarkShown, isFalse);

      // Opened from the sheet: the marked line again.
      await openBookmarks(tester);
      await tester.tap(bookmarkRow(bookmark));
      await sheetClosed(tester);
      await settle(tester, rounds: 3);
      await tester.pump(const Duration(milliseconds: 400));
      expect(state.currentPosition, line);
      expect(state.bookmarkShown, isTrue);
      await closeAll(tester, store);
    });
  });

  group('ribbon', () {
    testWidgets('the option hides it; the toolbar still shows the bookmark', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      store.updateSettings(store.settings.copyWith(bookmarkRibbon: false));
      store.addBookmark(mark('local:option', 'p1', page: 0));
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:option'),
          store: store,
        ),
      );
      expect(ribbon(tester).visible, isFalse);
      expect(
        tester
            .widget<LibraryReaderIconButton>(toolbarButton(en('bookmarks')))
            .icon,
        Icons.bookmark_rounded,
      );
      store.updateSettings(store.settings.copyWith(bookmarkRibbon: true));
      await tester.pump();
      expect(ribbon(tester).visible, isTrue);
      await closeAll(tester, store);
    });

    for (final animate in <bool>[true, false]) {
      testWidgets('slides in${animate ? '' : ' at once when not animated'}; '
          'read by VoiceOver only while shown', (tester) async {
        final semantics = tester.ensureSemantics();
        Widget host(bool visible) => MaterialApp(
          home: Scaffold(
            body: LibraryBookmarkRibbon(
              visible: visible,
              palette: LibraryReaderPalette.light,
              animate: animate,
            ),
          ),
        );
        await tester.pumpWidget(host(false));
        expect(find.semantics.byLabel(en('bookmarkedPage')), findsNothing);
        await tester.pumpWidget(host(true));
        await tester.pump(const Duration(milliseconds: 60));
        final fade = tester.widget<FadeTransition>(
          find.descendant(
            of: find.byType(LibraryBookmarkRibbon),
            matching: find.byType(FadeTransition),
          ),
        );
        if (animate) {
          expect(fade.opacity.value, inExclusiveRange(0, 1));
        } else {
          expect(fade.opacity.value, 1);
        }
        await tester.pump(const Duration(milliseconds: 300));
        expect(fade.opacity.value, 1);
        expect(find.semantics.byLabel(en('bookmarkedPage')), findsOne);
        // It takes no touch.
        expect(
          tester
              .widget<IgnorePointer>(
                find
                    .descendant(
                      of: find.byType(LibraryBookmarkRibbon),
                      matching: find.byType(IgnorePointer),
                    )
                    .first,
              )
              .ignoring,
          isTrue,
        );
        await tester.pumpWidget(host(false));
        expect(find.semantics.byLabel(en('bookmarkedPage')), findsNothing);
        semantics.dispose();
      });
    }
  });

  group('sheet', () {
    testWidgets('empty state, add from the sheet, open one, delete them', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      const key = 'local:sheet';
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key, pagesPerChapter: 6),
          store: store,
        ),
      );
      final state = pageState(tester);
      // The bars are shown at the opening: a tap on the toolbar's button.
      await tester.tap(toolbarButton(en('bookmarks')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryReaderBookmarksSheet), findsOneWidget);
      expect(find.text(en('bookmarks')), findsOneWidget);
      expect(find.text(en('noBookmarks')), findsOneWidget);
      expect(find.text(en('bookmarksLocalOnly')), findsOneWidget);
      await tester.tap(find.text(en('addBookmark')));
      await tester.pump();
      expect(store.bookmarksFor(key).single.location, 'page:0');
      expect(find.text(en('noBookmarks')), findsNothing);
      expect(
        find.text(format('en', 'bookmarkDefaultLabel', {'index': 1})),
        findsOneWidget,
      );
      // The page shown is marked: the first row now removes it.
      expect(find.text(en('removeBookmark')), findsOneWidget);
      expect(find.text(en('addBookmark')), findsNothing);
      await closeSheet(tester);

      for (var i = 0; i < 3; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      await openBookmarks(tester);
      await tester.tap(find.text(en('addBookmark')));
      await tester.pump();
      final bookmarks = store.bookmarksFor(key);
      expect(bookmarks.map((bookmark) => bookmark.location), <String>[
        'page:0',
        'page:3',
      ]);
      // In reading order, numbered by rank.
      expect(
        find.descendant(
          of: bookmarkRow(bookmarks[1]),
          matching: find.text(
            format('en', 'bookmarkDefaultLabel', {'index': 2}),
          ),
        ),
        findsOneWidget,
      );
      await tester.tap(bookmarkRow(bookmarks[0]));
      await sheetClosed(tester);
      expect(find.byType(LibraryReaderBookmarksSheet), findsNothing);
      expect(state.controller.page, 0);

      await openBookmarks(tester);
      Finder delete(LibraryBookmark bookmark) => find.descendant(
        of: bookmarkRow(bookmark),
        matching: find.byTooltip(en('removeBookmark')),
      );
      await tester.tap(delete(bookmarks[1]));
      await tester.pump();
      expect(store.bookmarksFor(key), <LibraryBookmark>[bookmarks[0]]);
      expect(bookmarkRow(bookmarks[1]), findsNothing);
      await tester.tap(delete(bookmarks[0]));
      await tester.pump();
      expect(store.bookmarksFor(key), isEmpty);
      expect(find.text(en('noBookmarks')), findsOneWidget);
      expect(find.text(en('addBookmark')), findsOneWidget);
      await closeSheet(tester);
      expect(ribbon(tester).visible, isFalse);
      await closeAll(tester, store);
    });

    // Review of the books chantier (probe A): without the add / remove row
    // (the end card of a CBZ or an online chapter, EPUB/TXT while it lays
    // out), deleting the last bookmark threw: the focus was clamped to an
    // empty range (0..-1).
    testWidgets('without the add / remove row, the last bookmark deleted '
        'leaves the empty state', (tester) async {
      useSurface(tester, size: const Size(400, 800));
      final (store, _) = await createStore(tester);
      plainTurns(store);
      const key = 'local:sheet-end';
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key, pagesPerChapter: 3),
          store: store,
        ),
      );
      final state = pageState(tester);
      // Pages 1 and 2 marked, then past the last page: the end card.
      state.gamepadBindings.y!();
      await tester.pump();
      state.gamepadBindings.down!();
      await frames(tester);
      state.gamepadBindings.y!();
      await tester.pump();
      expect(
        store.bookmarksFor(key).map((bookmark) => bookmark.location),
        <String>['page:0', 'page:1'],
      );
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.down!();
        await frames(tester);
      }
      expect(state.atEndCard, isTrue);

      await openBookmarks(tester);
      expect(find.text(en('addBookmark')), findsNothing);
      expect(find.text(en('removeBookmark')), findsNothing);
      // X on the second row, then the last one deleted with its button.
      sheetBindings(tester).down!();
      await tester.pump();
      sheetBindings(tester).x!();
      await tester.pump();
      expect(tester.takeException(), isNull);
      final first = store.bookmarksFor(key).single;
      expect(first.location, 'page:0');
      await tester.tap(
        find.descendant(
          of: bookmarkRow(first),
          matching: find.byTooltip(en('removeBookmark')),
        ),
      );
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(store.bookmarksFor(key), isEmpty);
      expect(find.text(en('noBookmarks')), findsOneWidget);
      // Nothing left to move to or delete; B still closes the sheet.
      sheetBindings(tester).down!();
      sheetBindings(tester).up!();
      sheetBindings(tester).x!();
      sheetBindings(tester).select!();
      await tester.pump();
      expect(tester.takeException(), isNull);
      expect(find.byType(LibraryReaderBookmarksSheet), findsOneWidget);
      sheetBindings(tester).back!();
      await sheetClosed(tester);
      expect(find.byType(LibraryReaderBookmarksSheet), findsNothing);
      await closeAll(tester, store);
    });

    testWidgets('controller: Y toggles, A opens, X deletes, B closes', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      const key = 'local:sheet-pad';
      store.addBookmark(mark(key, 'p4', page: 4, fraction: 1));
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: store,
        ),
      );
      final state = pageState(tester);
      await openBookmarks(tester);
      // Y: the page shown (page 1) is marked from the sheet as well.
      sheetBindings(tester).y!();
      await tester.pump();
      expect(
        store.bookmarksFor(key).map((bookmark) => bookmark.location),
        <String>['page:0', 'page:4'],
      );
      sheetBindings(tester).down!(); // The first bookmark (page 1).
      sheetBindings(tester).down!(); // The second one (page 5).
      await tester.pump();
      sheetBindings(tester).x!();
      await tester.pump();
      expect(
        store.bookmarksFor(key).map((bookmark) => bookmark.location),
        <String>['page:0'],
      );
      sheetBindings(tester).select!();
      await sheetClosed(tester);
      expect(find.byType(LibraryReaderBookmarksSheet), findsNothing);
      expect(state.controller.page, 0);
      await openBookmarks(tester);
      sheetBindings(tester).back!();
      await sheetClosed(tester);
      expect(find.byType(LibraryReaderBookmarksSheet), findsNothing);
      await closeAll(tester, store);
    });
  });

  testWidgets('500 bookmarks: the limit is said and nothing is added, from Y '
      'or from the sheet', (tester) async {
    useSurface(tester);
    final (store, _) = await createStore(tester);
    plainTurns(store);
    const key = 'local:full';
    for (var i = 0; i < LibraryReadingStore.maxBookmarksPerTitle; i++) {
      expect(store.addBookmark(mark(key, 'b$i', page: 10 + i)), isTrue);
    }
    await pumpReader(
      tester,
      LibraryPageReaderScreen(
        content: FakePageContent(progressKey: key),
        store: store,
      ),
    );
    final state = pageState(tester);
    state.gamepadBindings.y!();
    await tester.pump();
    expect(await message(tester, en('bookmarkLimitReached')), findsWidgets);
    expect(store.bookmarksFor(key), hasLength(500));
    expect(store.bookmarkAt(key, 'page:0'), isNull);
    expect(ribbon(tester).visible, isFalse);

    await openBookmarks(tester);
    await tester.tap(find.text(en('addBookmark')));
    await tester.pump();
    expect(
      find.descendant(
        of: find.byType(LibraryReaderBookmarksSheet),
        matching: find.text(en('bookmarkLimitReached')),
      ),
      findsOneWidget,
    );
    expect(store.bookmarksFor(key), hasLength(500));
    await closeSheet(tester);
    await closeAll(tester, store);
  });

  for (final (language, locale) in <(String, Locale)>[
    ('fr', const Locale('fr')),
    ('zh_Hant', const Locale('zh', 'TW')),
  ]) {
    testWidgets('the bookmarks speak $locale', (tester) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:$language'),
          store: store,
        ),
        locale: locale,
      );
      final state = pageState(tester);
      expect(toolbarButton(tr(language, 'bookmarks')), findsOneWidget);
      state.gamepadBindings.y!();
      await tester.pump();
      expect(
        await message(tester, tr(language, 'bookmarkAdded')),
        findsWidgets,
      );
      // Once the ribbon has slid in, VoiceOver reads it.
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.semantics.byLabel(tr(language, 'bookmarkedPage')), findsOne);

      await openBookmarks(tester, language: language);
      for (final text in <String>[
        tr(language, 'bookmarks'),
        format(language, 'bookmarkDefaultLabel', {'index': 1}),
        tr(language, 'removeBookmark'),
        tr(language, 'bookmarksLocalOnly'),
        format(language, 'pageNumber', {'page': 1}),
      ]) {
        expect(find.text(text), findsWidgets, reason: text);
      }
      if (language == 'zh_Hant') {
        // Traditional Chinese, never the Simplified texts.
        for (final key in <String>[
          'bookmarks',
          'removeBookmark',
          'bookmarksLocalOnly',
        ]) {
          expect(tr('zh_Hant', key), isNot(tr('zh', key)), reason: key);
          expect(find.text(tr('zh', key)), findsNothing, reason: key);
        }
      }
      await closeSheet(tester);
      await closeAll(tester, store);
      semantics.dispose();
    });
  }
}
