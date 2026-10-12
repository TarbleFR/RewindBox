// Build 447 toolbar of the Library readers (docs/library-books-3d-plan.md
// § 3.8, phase 7): its five actions (Settings, Bookmarks, Contents or
// Chapters, Progress, Library = the reader's close path), the "Always
// visible" mode (the chrome controller never hides, the pages are laid out
// between the bars), the progress with the time left once three pages were
// turned (LibraryReadingPace), and exactly one Back while the bars are
// shown. Real readers, store and navigator; the pace's clock is driven by
// the test.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_bookmarks.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_chrome.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_toolbar.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_local_fixtures.dart';
import 'library_reader_back_button_test.dart'
    show PopRecorder, expectOneBack, usePhone;
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

String enFormat(String key, Map<String, Object> values) {
  var text = en(key);
  values.forEach((name, value) => text = text.replaceAll('{$name}', '$value'));
  return text;
}

LibraryPageReaderScreenState pageState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

LibraryBookReaderScreenState bookState(WidgetTester tester) => tester
    .state<LibraryBookReaderScreenState>(find.byType(LibraryBookReaderScreen));

/// The toolbar button with this tooltip.
Finder toolbarButton(String tooltip) => find.descendant(
  of: find.byType(LibraryReaderToolbar),
  matching: find.byWidgetPredicate(
    (widget) => widget is LibraryReaderIconButton && widget.tooltip == tooltip,
  ),
);

Text? textOf(WidgetTester tester, Key key) {
  final found = find.byKey(key);
  if (found.evaluate().isEmpty) return null;
  return tester.widget<Text>(found);
}

/// Single pages turned without animation.
void plainTurns(LibraryReadingStore store) => store.updateSettings(
  store.settings.copyWith(
    turnStyle: LibraryPageTurnStyle.none,
    doublePage: LibraryDoublePageMode.never,
  ),
);

void useAlways(LibraryReadingStore store) => store.updateSettings(
  store.settings.copyWith(toolbarMode: LibraryReaderToolbarMode.always),
);

Future<void> closeAll(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump(Duration.zero);
  await settle(tester, rounds: 2);
  await flushStore(tester, store);
}

/// Lets a sheet slide in or out (B pops it asynchronously).
Future<void> sheetMoved(WidgetTester tester) async {
  for (var i = 0; i < 3; i++) {
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
  }
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

void main() {
  setUpReaderEnvironment();
  late DateTime now;
  setUp(() {
    now = DateTime.utc(2026, 10, 12, 9);
    LibraryReadingPace.defaultClock = () => now;
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(() {
    LibraryReadingPace.defaultClock = DateTime.now;
    LibraryPageCurlProgram.resetForTesting();
  });

  group('LibraryReadingPace', () {
    test('no estimate before three turns, then the average time per page', () {
      final pace = LibraryReadingPace(clock: () => now);
      pace.pageShown(); // The clock starts: nothing counted.
      expect(pace.turns, 0);
      for (final seconds in <int>[20, 40]) {
        now = now.add(Duration(seconds: seconds));
        pace.pageShown();
        expect(pace.remaining(10), isNull, reason: '${pace.turns} turns');
      }
      now = now.add(const Duration(seconds: 30));
      pace.pageShown();
      expect(pace.turns, 3);
      expect(pace.remaining(10), const Duration(seconds: 300));
      expect(pace.remaining(0), Duration.zero);
      expect(pace.remaining(-2), Duration.zero);
    });

    test('flicking through, a reader left open and a restart count nothing; '
        'a spread counts its pages', () {
      final pace = LibraryReadingPace(clock: () => now)..restart();
      now = now.add(const Duration(milliseconds: 300));
      pace.pageShown(); // Flicked through.
      now = now.add(const Duration(minutes: 11));
      pace.pageShown(); // Left open.
      expect(pace.turns, 0);
      now = now.add(const Duration(seconds: 50));
      pace.restart(); // A jump: the 50 s are not a turn.
      now = now.add(const Duration(seconds: 40));
      pace.pageShown(pages: 2); // A spread: 20 s a page.
      now = now.add(const Duration(seconds: 20));
      pace.pageShown();
      now = now.add(const Duration(seconds: 20));
      pace.pageShown();
      expect(pace.turns, 3);
      expect(pace.remaining(3), const Duration(seconds: 60));
    });

    test('the average follows the last turns only', () {
      final pace = LibraryReadingPace(clock: () => now, window: 3)..restart();
      for (final seconds in <int>[100, 100, 100, 10, 10, 10]) {
        now = now.add(Duration(seconds: seconds));
        pace.pageShown();
      }
      expect(pace.turns, 3);
      expect(pace.remaining(6), const Duration(seconds: 60));
    });
  });

  group('LibraryReaderChromeController.alwaysVisible', () {
    testWidgets('never hidden: no delay, no hide, no page turn, no toggle; '
        'turned off, the delay starts again', (tester) async {
      final chrome = LibraryReaderChromeController();
      addTearDown(chrome.dispose);
      chrome.hide();
      expect(chrome.visible, isFalse);
      chrome.alwaysVisible = true;
      expect(chrome.visible, isTrue, reason: 'turned on, it shows');
      await tester.pump(const Duration(seconds: 10));
      expect(chrome.visible, isTrue);
      chrome.hideAfterTurn();
      chrome.hide();
      chrome.toggle();
      expect(chrome.visible, isTrue);
      chrome.hold();
      chrome.release();
      chrome.touch();
      await tester.pump(const Duration(seconds: 10));
      expect(chrome.visible, isTrue);

      chrome.alwaysVisible = false;
      await tester.pump(const Duration(seconds: 3));
      expect(chrome.visible, isTrue);
      await tester.pump(const Duration(seconds: 2));
      expect(chrome.visible, isFalse, reason: 'hidden 4 s later');
    });
  });

  group('actions', () {
    testWidgets('online title: Settings, Bookmarks, Chapters, Progress and '
        'Library (the close path, never a second Back)', (tester) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      const key = 'online:source:title';
      final content = FakePageContent(
        progressKey: key,
        chapterCount: 3,
        tracksChapters: true,
      );
      final pops = PopRecorder();
      final navigator = await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
        opener: StoreWatcher(store: store, progressKey: key),
        navigatorObservers: <NavigatorObserver>[pops],
      );
      final state = pageState(tester);
      expect(state.chromeVisible, isTrue);
      // One of each in the reader (the top bar keeps Back and the title).
      for (final action in <String>[
        'settings',
        'bookmarks',
        'chapters',
        'library',
      ]) {
        expect(find.byTooltip(en(action)), findsOneWidget, reason: action);
        expect(toolbarButton(en(action)), findsOneWidget, reason: action);
      }
      expect(find.byTooltip(en('tableOfContents')), findsNothing);
      expectOneBack(tester, barsVisible: true);

      // Settings.
      await tester.tap(toolbarButton(en('settings')));
      await sheetMoved(tester);
      expect(find.text(en('settingsTitle')), findsOneWidget);
      Navigator.of(tester.element(find.text(en('settingsTitle')))).pop();
      await sheetMoved(tester);
      expect(find.text(en('settingsTitle')), findsNothing);

      // Bookmarks.
      await tester.tap(toolbarButton(en('bookmarks')));
      await sheetMoved(tester);
      expect(find.byType(LibraryReaderBookmarksSheet), findsOneWidget);
      expect(find.text(en('noBookmarks')), findsOneWidget);
      Navigator.of(
        tester.element(find.byType(LibraryReaderBookmarksSheet)),
      ).pop();
      await sheetMoved(tester);

      // Chapters (X as well): the one chosen opens.
      expect(state.gamepadBindings.x, isNotNull);
      await tester.tap(toolbarButton(en('chapters')));
      await sheetMoved(tester);
      expect(find.text(en('chapters')), findsOneWidget);
      await tester.tap(find.text('Chapter 2').last);
      await sheetMoved(tester);
      expect(state.controller.chapterIndex, 1);

      // Progress: the percentage of the title (chapter 2 of 3, page 1 of
      // 5), read by VoiceOver as one "Progress" node.
      expect(textOf(tester, LibraryReaderToolbar.percentKey)!.data, '40%');
      expect(textOf(tester, LibraryReaderToolbar.timeLeftKey), isNull);
      final progress = find.semantics.byLabel(RegExp('^${en('progress')}\n'));
      expect(progress, findsOne);
      expect(
        progress.evaluate().single.label,
        allOf(contains('40%'), contains('Chapter 2')),
      );

      // Library: the reader's own close path (that of the back control),
      // with its save.
      final overlay = tester.widget<LibraryReaderChromeOverlay>(
        find.byType(LibraryReaderChromeOverlay),
      );
      final toolbar = tester.widget<LibraryReaderToolbar>(
        find.byType(LibraryReaderToolbar),
      );
      expect(toolbar.onLibrary, overlay.onBack);
      expect(toolbar.onLibrary, state.gamepadBindings.back);
      state.gamepadBindings.right!();
      await frames(tester);
      // The page turn hid the bars: shown again, then Library.
      state.gamepadBindings.select!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      // The three sheets were popped before.
      final popped = pops.popped.length;
      await tester.tap(toolbarButton(en('library')));
      expect(store.progressFor(key)!.pageIndex, 1);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      // Only the reader's route.
      expect(pops.popped, hasLength(popped + 1));
      expect(pops.popped.last, isA<PageRoute<dynamic>>());
      expect(find.byType(StoreWatcher), findsOneWidget);
      expect(navigator.currentState!.canPop(), isTrue, reason: 'opener');
      await closeAll(tester, store);
      semantics.dispose();
    });

    testWidgets('EPUB: Contents opens the table of contents; a book without '
        'one has no Contents action', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final document = (await tester.runAsync(() async {
        final directory = await createTempDir('ns_reader_toolbar_epub_');
        final file = await writeFile(directory, 'book.epub', buildEpub3());
        return LibraryEpubDocument.open(file.path);
      }))!;
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:toc-book',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      await settlePages(tester);
      final state = bookState(tester);
      expect(toolbarButton(en('tableOfContents')), findsOneWidget);
      expect(toolbarButton(en('chapters')), findsNothing);
      expect(
        tester
            .widget<LibraryReaderIconButton>(
              toolbarButton(en('tableOfContents')),
            )
            .onPressed,
        state.gamepadBindings.x,
      );
      await tester.tap(toolbarButton(en('tableOfContents')));
      await sheetMoved(tester);
      expect(find.text(en('tableOfContents')), findsOneWidget);
      expect(find.text('Part Two'), findsOneWidget);
      await closeAll(tester, store);

      // A TXT file has no table of contents.
      final (plain, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:plain',
          title: 'Sample',
          store: plain,
        ),
      );
      await settlePages(tester);
      expect(toolbarButton(en('settings')), findsOneWidget);
      expect(toolbarButton(en('bookmarks')), findsOneWidget);
      expect(toolbarButton(en('library')), findsOneWidget);
      expect(toolbarButton(en('tableOfContents')), findsNothing);
      await closeAll(tester, plain);
    });
  });

  group('always visible', () {
    testWidgets('the bars never hide (delay, page turns, taps): one Back, '
        'the pages laid out between the bars', (tester) async {
      final semantics = tester.ensureSemantics();
      usePhone(tester, landscape: true);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      useAlways(store);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(pagesPerChapter: 6),
          store: store,
        ),
      );
      final state = pageState(tester);
      expect(state.chromeVisible, isTrue);
      await tester.pump(const Duration(seconds: 6));
      expect(state.chromeVisible, isTrue);
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      expect(state.controller.page, 2);
      expect(state.chromeVisible, isTrue, reason: 'hideAfterTurn ignored');
      // A tap in the middle (it would toggle the bars) and A.
      await tester.tapAt(tester.getCenter(find.byType(PageView)));
      await tester.pump(const Duration(milliseconds: 400));
      state.gamepadBindings.select!();
      await tester.pump(const Duration(milliseconds: 400));
      expect(state.chromeVisible, isTrue);
      expectOneBack(tester, barsVisible: true);
      // The pages are between the bars: no part of a page under one.
      final pages = tester.getRect(find.byType(PageView));
      expect(
        pages.top,
        greaterThanOrEqualTo(
          tester.getRect(find.byType(LibraryReaderTopBar)).bottom,
        ),
      );
      expect(
        pages.bottom,
        lessThanOrEqualTo(
          tester.getRect(find.byType(LibraryReaderBottomBar)).top,
        ),
      );

      // Back to automatic: the bars hide again 4 s later.
      store.updateSettings(
        store.settings.copyWith(toolbarMode: LibraryReaderToolbarMode.auto),
      );
      await tester.pump();
      await tester.pump(const Duration(seconds: 5));
      expect(state.chromeVisible, isFalse);
      expect(
        tester.getRect(find.byType(PageView)).height,
        tester.view.physicalSize.height,
        reason: 'edge to edge again',
      );
      await closeAll(tester, store);
      semantics.dispose();
    });

    testWidgets('EPUB/TXT pages: the last lines stay above the toolbar', (
      tester,
    ) async {
      usePhone(tester);
      final (store, _) = await createStore(tester);
      useAlways(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:always-text',
          title: 'Sample',
          store: store,
        ),
      );
      await settlePages(tester);
      final state = bookState(tester);
      expect(state.shownSpread, isNotNull);
      await tester.pump(const Duration(seconds: 6));
      expect(state.chromeVisible, isTrue);
      final toolbarTop = tester
          .getRect(find.byType(LibraryReaderBottomBar))
          .top;
      final page = state.shownSpread!.first;
      // The page's area ends above the toolbar, and so does its text.
      expect(
        tester.getRect(find.byType(PageView)).bottom,
        lessThanOrEqualTo(toolbarTop),
      );
      expect(page.size.height, lessThanOrEqualTo(toolbarTop));
      await closeAll(tester, store);
    });
  });

  group('progress', () {
    testWidgets('page reader: the percentage, then the time left in the book '
        'once three pages were turned', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      plainTurns(store);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            progressKey: 'local:pace',
            pagesPerChapter: 9,
          ),
          store: store,
        ),
      );
      final state = pageState(tester);
      expect(textOf(tester, LibraryReaderToolbar.percentKey)!.data, '11%');
      for (var turn = 1; turn <= 3; turn++) {
        expect(
          textOf(tester, LibraryReaderToolbar.timeLeftKey),
          isNull,
          reason: 'after ${turn - 1} turns',
        );
        now = now.add(const Duration(seconds: 30));
        state.gamepadBindings.right!();
        await frames(tester);
      }
      expect(state.controller.page, 3);
      // 30 s a page, five pages left: 150 s, three minutes.
      expect(
        textOf(tester, LibraryReaderToolbar.timeLeftKey)!.data,
        enFormat('timeLeftInBook', <String, Object>{'minutes': 3}),
      );
      expect(textOf(tester, LibraryReaderToolbar.percentKey)!.data, '44%');
      // A jump back is not a turn: the estimate stays, the clock restarts.
      final slider = tester.widget<Slider>(find.byType(Slider));
      slider.onChangeStart!(0);
      slider.onChangeEnd!(0);
      await tester.pump(const Duration(milliseconds: 50));
      expect(state.controller.page, 0);
      expect(
        textOf(tester, LibraryReaderToolbar.timeLeftKey)!.data,
        enFormat('timeLeftInBook', <String, Object>{'minutes': 4}),
      );
      await closeAll(tester, store);
    });

    testWidgets('EPUB/TXT pages: the page in its chapter, then the time left '
        'once three pages were turned', (tester) async {
      useSurface(tester, size: const Size(400, 860));
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:text-pace',
          title: 'Sample',
          store: store,
        ),
      );
      await settlePages(tester);
      final state = bookState(tester);
      final total = state.paginator!.pageCountOf(0)!;
      expect(
        textOf(tester, LibraryReaderToolbar.pageLabelKey)!.data,
        enFormat('pageOfTotal', <String, Object>{'page': 1, 'total': total}),
      );
      for (var turn = 1; turn <= 3; turn++) {
        expect(textOf(tester, LibraryReaderToolbar.timeLeftKey), isNull);
        now = now.add(const Duration(seconds: 40));
        state.gamepadBindings.down!();
        await frames(tester);
        await settlePages(tester, rounds: 2);
      }
      expect(
        textOf(tester, LibraryReaderToolbar.pageLabelKey)!.data,
        enFormat('pageOfTotal', <String, Object>{'page': 4, 'total': total}),
      );
      // TXT sections are not chapters: the time left is the book's.
      final time = textOf(tester, LibraryReaderToolbar.timeLeftKey)!.data!;
      expect(
        time,
        matches(
          RegExp(
            '^${RegExp.escape(en('timeLeftInBook')).replaceAll(RegExp.escape('{minutes}'), r'\d+')}\$',
          ),
        ),
      );
      final minutes = int.parse(RegExp(r'\d+').firstMatch(time)![0]!);
      // At least the rest of this section at 40 s a page.
      expect(minutes, greaterThanOrEqualTo(((total - 4) * 40 / 60).ceil()));
      await closeAll(tester, store);
    });
  });
}
