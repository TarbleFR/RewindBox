import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_source.dart';
import 'package:neostation/services/library_aidoku_engines.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_local_fixtures.dart';
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

LibraryPageReaderScreenState readerState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

Future<void> closeAll(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await flushStore(tester, store);
}

/// Double-taps the middle of the 900 x 600 test surface (zoom toggle).
Future<void> doubleTapCentre(WidgetTester tester) async {
  await tester.tapAt(const Offset(450, 300));
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tapAt(const Offset(452, 302));
  await frames(tester);
}

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

void main() {
  setUpReaderEnvironment();

  group('LibraryPageReaderController', () {
    testWidgets('a book resumes at its saved page', (tester) async {
      final (store, _) = await createStore(tester);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:book',
          location: 'page:3',
          fraction: 0.5,
          pageIndex: 3,
        ),
      );
      final controller = LibraryPageReaderController(
        content: FakePageContent(progressKey: 'local:book'),
        store: store,
      );
      await drive(tester, controller.start());
      expect(controller.status, LibraryPageReaderStatus.ready);
      expect(controller.page, 3);
      controller.dispose();
      await flushStore(tester, store);
    });

    testWidgets(
      'an online chapter resumes from its mark; a finished one restarts',
      (tester) async {
        final (store, _) = await createStore(tester);
        store.markChapter('online:fake:manga', 'c1', page: 2, pageCount: 5);
        store.markChapter(
          'online:fake:manga',
          'c0',
          read: true,
          page: 4,
          pageCount: 5,
        );
        final resumed = LibraryPageReaderController(
          content: FakePageContent(
            chapterCount: 3,
            tracksChapters: true,
            initialChapterIndex: 1,
          ),
          store: store,
        );
        await drive(tester, resumed.start());
        expect(resumed.page, 2);
        resumed.dispose();

        final finished = LibraryPageReaderController(
          content: FakePageContent(chapterCount: 3, tracksChapters: true),
          store: store,
        );
        await drive(tester, finished.start());
        expect(finished.page, 0);
        finished.dispose();
        await flushStore(tester, store);
      },
    );

    testWidgets(
      'reaching the last page marks the chapter read and saves progress',
      (tester) async {
        final (store, _) = await createStore(tester);
        final content = FakePageContent(chapterCount: 2, tracksChapters: true);
        final controller = LibraryPageReaderController(
          content: content,
          store: store,
        );
        await drive(tester, controller.start());
        controller.setPage(4);
        expect(store.chapterMark(content.progressKey, 'c0')?.read, isTrue);
        controller.saveNow();
        final saved = store.progressFor(content.progressKey)!;
        expect(saved.location, 'page:4');
        expect(saved.pageIndex, 4);
        expect(saved.pageCount, 5);
        expect(saved.chapterId, 'c0');
        expect(saved.title, 'Fake title');
        // Chapter 1 of 2 finished: half the title.
        expect(saved.fraction, closeTo(0.5, 1e-9));
        controller.dispose();
        await flushStore(tester, store);
      },
    );

    testWidgets('a superseded chapter load is cancelled and ignored', (
      tester,
    ) async {
      final (store, _) = await createStore(tester);
      final first = Completer<LibraryPageSource>();
      final tokens = <LibraryCancelToken>[];
      final content = FakePageContent(
        chapterCount: 3,
        tracksChapters: true,
        loader: (index, cancel) {
          tokens.add(cancel);
          if (index == 0) return first.future;
          return Future<LibraryPageSource>.value(
            MemoryPageSource(7, key: 'c$index'),
          );
        },
      );
      final controller = LibraryPageReaderController(
        content: content,
        store: store,
      );
      unawaited(controller.start());
      for (var i = 0; i < 10 && tokens.isEmpty; i++) {
        await settle(tester, rounds: 1);
      }
      expect(tokens, hasLength(1));
      await drive(tester, controller.openChapter(2));
      expect(tokens.first.isCancelled, isTrue);
      expect(controller.chapterIndex, 2);
      expect(controller.pageCount, 7);
      final late = MemoryPageSource(3, key: 'late');
      first.complete(late);
      await tester.pump();
      expect(controller.chapterIndex, 2);
      expect(controller.pageCount, 7);
      expect(late.disposed, isTrue);
      controller.dispose();
      await flushStore(tester, store);
    });

    testWidgets('layout follows the content hint unless the settings decide', (
      tester,
    ) async {
      final (store, _) = await createStore(tester);
      LibraryPageReaderController make(LibraryPageLayoutHint hint) =>
          LibraryPageReaderController(
            content: FakePageContent(layoutHint: hint),
            store: store,
          );
      final rtl = make(LibraryPageLayoutHint.rightToLeft);
      expect(rtl.mode, LibraryPageReaderMode.paged);
      expect(rtl.rightToLeft, isTrue);
      final vertical = make(LibraryPageLayoutHint.vertical);
      expect(vertical.mode, LibraryPageReaderMode.vertical);
      final unknown = make(LibraryPageLayoutHint.unknown);
      expect(unknown.rightToLeft, isFalse);

      store.updateSettings(
        store.settings.copyWith(
          mangaMode: LibraryMangaMode.paged,
          pageDirection: LibraryPageDirection.ltr,
        ),
      );
      expect(rtl.rightToLeft, isFalse);
      expect(vertical.mode, LibraryPageReaderMode.paged);
      vertical.toggleMode();
      expect(vertical.mode, LibraryPageReaderMode.vertical);
      vertical.clearModeOverride();
      expect(vertical.mode, LibraryPageReaderMode.paged);
      for (final c in <LibraryPageReaderController>[rtl, vertical, unknown]) {
        c.dispose();
      }
      await flushStore(tester, store);
    });
  });

  group('LibraryPageReaderScreen', () {
    testWidgets('tap zones turn pages, the centre toggles the chrome', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(progressKey: 'local:taps');
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(state.controller.status, LibraryPageReaderStatus.ready);
      expect(state.controller.page, 0);

      await tester.tapAt(const Offset(850, 300));
      await frames(tester);
      expect(state.controller.page, 1);
      await tester.tapAt(const Offset(850, 300));
      await frames(tester);
      expect(state.controller.page, 2);
      await tester.tapAt(const Offset(50, 300));
      await frames(tester);
      expect(state.controller.page, 1);
      // Side taps hid the chrome; a centre tap shows it after the
      // double-tap window.
      expect(state.chromeVisible, isFalse);
      await tester.tapAt(const Offset(450, 300));
      await tester.pump(const Duration(milliseconds: 100));
      expect(state.chromeVisible, isFalse);
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.chromeVisible, isTrue);
      expect(find.text('2 / 5'), findsOneWidget);

      await closeAll(tester, store);
    });

    testWidgets('a double tap zooms and swipes then pan instead of turning', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: FakePageContent(), store: store),
      );
      final state = readerState(tester);
      await tester.tapAt(const Offset(450, 300));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tapAt(const Offset(452, 302));
      await frames(tester);
      expect(state.zoomed, isTrue);
      expect(
        tester.widget<PageView>(find.byType(PageView)).physics,
        isA<NeverScrollableScrollPhysics>(),
      );
      // Side zones do not turn pages while zoomed.
      await tester.tapAt(const Offset(850, 300));
      await frames(tester);
      expect(state.controller.page, 0);
      await closeAll(tester, store);
    });

    // Regression: the zoom was reset while the reader was building (new
    // chapter, layout switch) and its listener called setState during the
    // build ("setState() or markNeedsBuild() called during build").
    testWidgets('a zoomed page is unzoomed cleanly when the chapter changes', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(chapterCount: 2, tracksChapters: true);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      await doubleTapCentre(tester);
      expect(state.zoomed, isTrue);
      state.gamepadBindings.rightBumper!();
      await frames(tester);
      await frames(tester);
      expect(tester.takeException(), isNull);
      expect(state.controller.chapterIndex, 1);
      expect(state.controller.status, LibraryPageReaderStatus.ready);
      expect(state.zoomed, isFalse);
      expect(
        tester.widget<PageView>(find.byType(PageView)).physics,
        isNot(isA<NeverScrollableScrollPhysics>()),
      );
      await closeAll(tester, store);
    });

    testWidgets('a zoomed strip is unzoomed cleanly when the chapter changes', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(
        chapterCount: 2,
        tracksChapters: true,
        layoutHint: LibraryPageLayoutHint.vertical,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      await doubleTapCentre(tester);
      expect(state.zoomed, isTrue);
      state.gamepadBindings.rightBumper!();
      await frames(tester);
      await frames(tester);
      expect(tester.takeException(), isNull);
      expect(state.controller.chapterIndex, 1);
      expect(state.zoomed, isFalse);
      await closeAll(tester, store);
    });

    testWidgets('a zoomed page is unzoomed cleanly when the layout switches', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: FakePageContent(), store: store),
      );
      final state = readerState(tester);
      await doubleTapCentre(tester);
      expect(state.zoomed, isTrue);
      state.controller.toggleMode();
      await frames(tester);
      expect(tester.takeException(), isNull);
      expect(find.byType(ListView), findsOneWidget);
      expect(state.zoomed, isFalse);
      await closeAll(tester, store);
    });

    testWidgets('the d-pad turns a zoomed page and restores swiping', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: FakePageContent(), store: store),
      );
      final state = readerState(tester);
      await doubleTapCentre(tester);
      expect(state.zoomed, isTrue);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(tester.takeException(), isNull);
      expect(state.controller.page, 1);
      expect(state.zoomed, isFalse);
      expect(
        tester.widget<PageView>(find.byType(PageView)).physics,
        isNot(isA<NeverScrollableScrollPhysics>()),
      );
      await closeAll(tester, store);
    });

    testWidgets('right-to-left mirrors the tap zones, the d-pad and the view', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(
        layoutHint: LibraryPageLayoutHint.rightToLeft,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isTrue);

      await tester.tapAt(const Offset(50, 300));
      await frames(tester);
      expect(state.controller.page, 1);
      state.gamepadBindings.left!();
      await frames(tester);
      expect(state.controller.page, 2);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      await tester.tapAt(const Offset(850, 300));
      await frames(tester);
      expect(state.controller.page, 0);
      await closeAll(tester, store);
    });

    // Regression: in automatic mode the content's hint always won, so the
    // sheet showed the stored "left to right" while the manga read right to
    // left, and choosing a direction changed nothing.
    testWidgets('the direction in the settings shows and overrides the hint', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(
        layoutHint: LibraryPageLayoutHint.rightToLeft,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(store.settings.mangaMode, LibraryMangaMode.auto);
      expect(store.settings.pageDirection, LibraryPageDirection.ltr);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isTrue);

      state.gamepadBindings.start!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      ChoiceChip chip(String key) =>
          tester.widget<ChoiceChip>(find.widgetWithText(ChoiceChip, en(key)));
      expect(chip('directionRtl').selected, isTrue);
      expect(chip('directionLtr').selected, isFalse);

      await tester.tap(find.widgetWithText(ChoiceChip, en('directionLtr')));
      await tester.pump();
      expect(chip('directionLtr').selected, isTrue);
      expect(state.controller.rightToLeft, isFalse);
      Navigator.of(tester.element(find.byType(ChoiceChip).first)).pop();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isFalse);
      // The right edge turns forward again.
      await tester.tapAt(const Offset(850, 300));
      await frames(tester);
      expect(state.controller.page, 1);
      await closeAll(tester, store);
    });

    testWidgets('the slider jumps to a page', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(pagesPerChapter: 9),
          store: store,
        ),
      );
      final state = readerState(tester);
      final slider = tester.widget<Slider>(find.byType(Slider));
      slider.onChangeStart!(6);
      slider.onChanged!(6);
      slider.onChangeEnd!(6);
      await tester.pump(const Duration(milliseconds: 50));
      expect(state.controller.page, 6);
      expect(find.text('7 / 9'), findsOneWidget);
      await closeAll(tester, store);
    });

    testWidgets('progress is saved on close and restored on the next opening', (
      tester,
    ) async {
      useSurface(tester);
      final (store, directory) = await createStore(tester);
      final navigator = await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:resume'),
          store: store,
        ),
      );
      final state = readerState(tester);
      for (var i = 0; i < 3; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      expect(state.controller.page, 3);
      // B closes the reader.
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      expect(navigator.currentState!.canPop(), isFalse);
      final saved = store.progressFor('local:resume')!;
      expect(saved.location, 'page:3');
      expect(saved.pageIndex, 3);
      expect(saved.pageCount, 5);
      expect(saved.fraction, closeTo(0.8, 1e-9));
      await flushStore(tester, store);

      // A new store reads the file written by the first one.
      final (reloaded, _) = await createStore(tester, directory: directory);
      expect(reloaded.progressFor('local:resume')?.pageIndex, 3);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:resume'),
          store: reloaded,
        ),
      );
      expect(readerState(tester).controller.page, 3);
      await closeAll(tester, reloaded);
    });

    testWidgets('online chapters chain through the end and start cards', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(chapterCount: 3, tracksChapters: true);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(find.text('Chapter 1'), findsOneWidget);
      // The slider moves the view when it is released (a tap on the track
      // is a start, a change and an end).
      final slider = tester.widget<Slider>(find.byType(Slider));
      slider.onChangeStart!(0);
      slider.onChanged!(4);
      slider.onChangeEnd!(4);
      await tester.pump(const Duration(milliseconds: 50));
      expect(state.controller.page, 4);
      expect(store.chapterMark(content.progressKey, 'c0')?.read, isTrue);

      // Past the last page: the end card announces the next chapter.
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.atEndCard, isTrue);
      expect(find.text(en('endOfChapter')), findsOneWidget);
      expect(find.text('Next: Chapter 2'), findsOneWidget);
      await tester.tap(find.text(en('nextChapter')).last);
      await frames(tester);
      expect(state.controller.chapterIndex, 1);
      expect(state.controller.page, 0);
      expect(content.loads, <int>[0, 1]);

      // Before the first page: the start card, then the previous chapter
      // at its last page.
      state.gamepadBindings.left!();
      await frames(tester);
      expect(state.atStartCard, isTrue);
      expect(find.text('Previous: Chapter 1'), findsOneWidget);
      state.gamepadBindings.left!();
      await frames(tester);
      expect(state.controller.chapterIndex, 0);
      expect(state.controller.page, 4);

      // Bumpers move between chapters.
      state.gamepadBindings.rightBumper!();
      await frames(tester);
      expect(state.controller.chapterIndex, 1);
      await closeAll(tester, store);
    });

    testWidgets('a failed chapter shows a translated error and retries', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      var attempts = 0;
      final content = FakePageContent(
        tracksChapters: true,
        loader: (index, cancel) async {
          attempts++;
          if (attempts == 1) {
            throw LibraryNetworkException(
              LibraryNetworkErrorKind.timeout,
              uri: Uri.parse('https://example.org/chapter/1'),
              detail: 'no answer after 20 s',
            );
          }
          return MemoryPageSource(4);
        },
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(state.controller.status, LibraryPageReaderStatus.error);
      expect(find.text(en('errorTimeout')), findsOneWidget);
      // The raw detail stays hidden until asked for, and is untranslated.
      expect(find.textContaining('example.org'), findsNothing);
      await tester.tap(find.text(en('technicalDetails')));
      await tester.pump();
      expect(
        find.textContaining('https://example.org/chapter/1'),
        findsOneWidget,
      );

      await tester.tap(find.text(en('retry')));
      await frames(tester);
      expect(state.controller.status, LibraryPageReaderStatus.ready);
      expect(state.controller.pageCount, 4);
      await closeAll(tester, store);
    });

    testWidgets('A on the controller retries a failed chapter', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      var attempts = 0;
      final content = FakePageContent(
        loader: (index, cancel) async {
          attempts++;
          if (attempts == 1) {
            throw const LibraryNetworkException(
              LibraryNetworkErrorKind.offline,
            );
          }
          return MemoryPageSource(3);
        },
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(state.controller.status, LibraryPageReaderStatus.error);
      state.gamepadBindings.select!();
      await frames(tester);
      expect(attempts, 2);
      expect(state.controller.status, LibraryPageReaderStatus.ready);
      // Once ready, A shows or hides the chrome again.
      final visible = state.chromeVisible;
      state.gamepadBindings.select!();
      await tester.pump();
      expect(state.chromeVisible, !visible);
      expect(attempts, 2);
      await closeAll(tester, store);
    });

    testWidgets('a source error is translated in French', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(
        loader: (index, cancel) async => throw LibrarySourceException(
          LibrarySourceErrorKind.protectedChapter,
          sourceId: 'fr.example',
        ),
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
        locale: const Locale('fr'),
      );
      expect(
        find.text(LibraryReaderLocale.values['fr']!['errorProtectedChapter']!),
        findsOneWidget,
      );
      expect(find.text('Réessayer'), findsOneWidget);
      await closeAll(tester, store);
    });

    testWidgets('a page that fails to load offers its own retry', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final source = MemoryPageSource(3, failing: <int>{0});
      final content = FakePageContent(loader: (index, cancel) async => source);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      await tester.pump();
      expect(find.text(en('errorServerUnavailable')), findsOneWidget);
      final failing = source.imageFor(0) as FailingImage;
      expect(failing.loads, 1);
      await tester.tap(find.text(en('retry')));
      await tester.pump();
      expect(failing.loads, 2);
      expect(find.text(en('errorServerUnavailable')), findsNothing);
      await closeAll(tester, store);
    });

    testWidgets('the neighbours are prefetched', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(startPage: 2, pagesPerChapter: 6);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      await tester.pump();
      expect(content.sources.single.prefetched, containsAll(<int>[3, 4, 1]));
      await closeAll(tester, store);
    });

    testWidgets('vertical content opens as a lazy strip', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(
        pagesPerChapter: 40,
        layoutHint: LibraryPageLayoutHint.vertical,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      expect(find.byType(PageView), findsNothing);
      expect(find.byType(ListView), findsOneWidget);
      // Only the visible pages and the cache extent are built.
      final built = find.byType(LibraryReaderPageImage).evaluate().length;
      expect(built, lessThan(10));
      final state = readerState(tester);
      final scrollable = tester.state<ScrollableState>(
        find.descendant(
          of: find.byType(ListView),
          matching: find.byType(Scrollable),
        ),
      );
      expect(scrollable.position.pixels, 0);
      // Up/down scroll by most of the screen (a webtoon page is taller).
      state.gamepadBindings.down!();
      await frames(tester);
      expect(scrollable.position.pixels, closeTo(480, 1));
      expect(state.controller.page, 0);
      // Left/right jump to the previous/next page.
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 2);
      // The mode toggle switches to paged reading at the same page.
      final page = state.controller.page;
      state.controller.toggleMode();
      await tester.pump();
      await tester.pump();
      expect(find.byType(PageView), findsOneWidget);
      expect(state.controller.page, page);
      await closeAll(tester, store);
    });

    testWidgets(
      'vertical: next on the last page shows the end card, then the next chapter',
      (tester) async {
        useSurface(tester);
        final (store, _) = await createStore(tester);
        final content = FakePageContent(
          chapterCount: 2,
          pagesPerChapter: 3,
          tracksChapters: true,
          layoutHint: LibraryPageLayoutHint.vertical,
        );
        await pumpReader(
          tester,
          LibraryPageReaderScreen(content: content, store: store),
        );
        final state = readerState(tester);
        for (var i = 0; i < 2; i++) {
          state.gamepadBindings.right!();
          await frames(tester);
        }
        expect(state.controller.page, 2);
        expect(state.atEndCard, isFalse);
        state.gamepadBindings.right!();
        await frames(tester);
        expect(state.atEndCard, isTrue);
        expect(store.chapterMark(content.progressKey, 'c0')?.read, isTrue);
        state.gamepadBindings.right!();
        await frames(tester);
        expect(state.controller.chapterIndex, 1);
        expect(state.controller.page, 0);
        await closeAll(tester, store);
      },
    );

    testWidgets('opening and closing a reader enters and leaves portrait', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final orientation = LibraryReaderOrientation(
        platform: _OrientationRecorder(),
        isIOS: true,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(),
          store: store,
          orientation: orientation,
        ),
      );
      await tester.pump();
      expect(orientation.portraitActive, isTrue);
      expect(wakelockCalls.last, isTrue);
      final before = wakelockCalls.length;
      await tester.pumpWidget(const SizedBox.shrink());
      await tester.pump();
      expect(orientation.portraitActive, isFalse);
      expect(orientation.depth, 0);
      expect(wakelockCalls.sublist(before), <bool>[false]);
      await flushStore(tester, store);
    });
  });

  group('closing', () {
    // Regression: landscape came back only in dispose, after the reverse
    // transition, so the landscape-only screen below was laid out in
    // portrait for about 300 ms and then rotated.
    testWidgets('landscape is restored as soon as the reader is popped', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final platform = RecordingOrientationPlatform();
      final orientation = LibraryReaderOrientation(
        platform: platform,
        isIOS: true,
      );
      final navigator = await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(),
          store: store,
          orientation: orientation,
        ),
      );
      await tester.pump();
      await expectLandscapeWhenPopStarts(
        tester,
        navigator,
        platform,
        orientation,
        LibraryPageReaderScreen,
      );
      await flushStore(tester, store);
    });

    // Regression: closing within the save delay saved from dispose, so the
    // store notified the screens below while the widget tree was locked
    // ("setState() or markNeedsBuild() called when widget tree was
    // locked"), and their new progress was not drawn.
    testWidgets('B right after a page turn saves before the pop', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:quick'),
          store: store,
        ),
        home: StoreWatcher(store: store, progressKey: 'local:quick'),
      );
      // The opening is saved after the delay.
      await tester.pump(const Duration(seconds: 1));
      final state = readerState(tester);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      // B within the 700 ms save delay.
      state.gamepadBindings.back!();
      await tester.pump();
      expect(store.progressFor('local:quick')!.pageIndex, 1);
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      expect(tester.takeException(), isNull);
      expect(find.text('home page:1'), findsOneWidget);
      await flushStore(tester, store);
    });

    testWidgets('a pop (iOS back swipe) saves at once, then freezes the page', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final navigator = await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:swipe'),
          store: store,
        ),
        home: StoreWatcher(store: store, progressKey: 'local:swipe'),
      );
      await tester.pump(const Duration(seconds: 1));
      final state = readerState(tester);
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      navigator.currentState!.pop();
      // Saved when the pop starts, not when the transition ends.
      expect(store.progressFor('local:swipe')!.pageIndex, 1);
      await tester.pump();
      // The closing view reports another page (it is laid out again in
      // landscape): ignored.
      state.controller.setPage(3);
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      expect(tester.takeException(), isNull);
      expect(store.progressFor('local:swipe')!.pageIndex, 1);
      expect(find.text('home page:1'), findsOneWidget);
      await flushStore(tester, store);
    });
  });

  group('VoiceOver', () {
    // Regression: the bars hid 4 s after being shown, taking Back, the
    // settings, the chapter buttons and the slider out of the
    // accessibility tree, and the icon buttons had no tap action.
    testWidgets('the chrome stays and its buttons can be activated', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(accessibleNavigation: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final navigator = await pumpReader(
        tester,
        LibraryPageReaderScreen(content: FakePageContent(), store: store),
      );
      final state = readerState(tester);
      expect(state.chromeVisible, isTrue);
      await tester.pump(const Duration(seconds: 5));
      expect(state.chromeVisible, isTrue);
      // A page turn does not hide it either.
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.controller.page, 1);
      expect(state.chromeVisible, isTrue);

      final back = find.semantics.byLabel(en('back'));
      expect(back, findsOne);
      for (final key in <String>['back', 'settings', 'switchToVertical']) {
        final node = find.semantics.byLabel(en(key)).evaluate().single;
        expect(
          node.getSemanticsData().hasAction(SemanticsAction.tap),
          isTrue,
          reason: key,
        );
      }
      // Activating Back closes the reader.
      tester.semantics.tap(back);
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      expect(navigator.currentState!.canPop(), isFalse);
      await flushStore(tester, store);
      semantics.dispose();
    });

    testWidgets('without VoiceOver the chrome still hides after 4 s', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: FakePageContent(), store: store),
      );
      final state = readerState(tester);
      expect(find.semantics.byLabel(en('back')), findsOne);
      await tester.pump(const Duration(seconds: 5));
      await tester.pump(const Duration(milliseconds: 300));
      expect(state.chromeVisible, isFalse);
      expect(find.semantics.byLabel(en('back')), findsNothing);
      await closeAll(tester, store);
      semantics.dispose();
    });
  });

  group('page decoding and loading', () {
    // Regression: paged mode decoded by the viewport width only, so a
    // portrait page on a landscape iPhone was decoded at full resolution
    // (1920 x 3016) to be shown 1179 px tall.
    testWidgets('paged pages are decoded to fit the screen, strips by width', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final source = _SlowPageSource(6);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            pagesPerChapter: 6,
            loader: (index, cancel) async => source,
          ),
          store: store,
        ),
      );
      await tester.pump();
      // 900 x 600 at ratio 1, rounded up to steps of 128 px.
      expect(source.requests, isNotEmpty);
      expect(source.requests.map((r) => (r.$2, r.$3)).toSet(), <(int?, int?)>{
        (1024, 640),
      });

      source.requests.clear();
      readerState(tester).controller.toggleMode();
      await tester.pump();
      await tester.pump();
      expect(find.byType(ListView), findsOneWidget);
      expect(source.requests, isNotEmpty);
      expect(source.requests.map((r) => (r.$2, r.$3)).toSet(), <(int?, int?)>{
        (1024, null),
      });
      await closeAll(tester, store);
    });

    testWidgets('an iPhone in landscape decodes pages at the screen height', (
      tester,
    ) async {
      // iPhone 15 in landscape: 852 x 393 pt at 3x.
      tester.view.physicalSize = const Size(2556, 1179);
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);
      final (store, _) = await createStore(tester);
      final source = _SlowPageSource(6);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            pagesPerChapter: 6,
            loader: (index, cancel) async => source,
          ),
          store: store,
        ),
      );
      await tester.pump();
      expect(source.requests.map((r) => (r.$2, r.$3)).toSet(), <(int?, int?)>{
        (2400, 1280),
      });
      await closeAll(tester, store);
    });

    testWidgets('an online page is decoded no taller than the screen', (
      tester,
    ) async {
      useSurface(tester, size: const Size(400, 300));
      final (store, _) = await createStore(tester);
      final directory = (await tester.runAsync(
        () => createTempDir('ns_reader_pages_'),
      ))!;
      // A tall page: 200 x 600 shown in a 400 x 300 screen.
      final cache = _pageImageCache(directory, buildPng(200, 600));
      final source = LibraryNetworkPageSource(const <String>[
        'https://example.org/p1.png',
      ], cache: cache);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(loader: (index, cancel) async => source),
          store: store,
        ),
      );
      RawImage? page;
      for (var i = 0; i < 20 && page == null; i++) {
        await settle(tester, rounds: 1);
        final found = find.byType(RawImage);
        if (found.evaluate().isNotEmpty) page = tester.widget<RawImage>(found);
      }
      expect(page?.image, isNotNull);
      // Height 384 (300 rounded up to 128 px steps), proportions kept.
      expect(page!.image!.height, 384);
      expect(page.image!.width, 128);
      await closeAll(tester, store);
    });

    // Regression: each page crossed by a slider drag was shown, so its
    // download started (none can be cancelled) and the page the drag
    // stopped on was queued behind all of them.
    testWidgets('a slider drag loads only the page it stops on, first', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      final source = _SlowPageSource(60);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            pagesPerChapter: 60,
            loader: (index, cancel) async => source,
          ),
          store: store,
        ),
      );
      await tester.pump(const Duration(milliseconds: 50));
      final state = readerState(tester);
      expect(state.controller.page, 0);
      final loadsBefore = source.loads.length;
      final prefetchesBefore = source.prefetched.length;

      final track = tester.getRect(find.byType(Slider));
      final gesture = await tester.startGesture(
        Offset(track.left + 30, track.center.dy),
      );
      final step = (track.width * 0.7) / 45;
      for (var i = 0; i < 45; i++) {
        await gesture.moveBy(Offset(step, 0));
        await tester.pump(const Duration(milliseconds: 16));
      }
      // While dragging, the label follows the thumb; nothing is loaded and
      // the view stays on its page.
      final dragged = tester.widget<Slider>(find.byType(Slider)).value.round();
      expect(dragged, greaterThan(30));
      expect(find.text('${dragged + 1} / 60'), findsOneWidget);
      expect(source.loads.sublist(loadsBefore), isEmpty);
      expect(source.prefetched.sublist(prefetchesBefore), isEmpty);
      expect(state.controller.page, 0);

      await gesture.up();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      final target = state.controller.page;
      expect(target, dragged);
      final started = source.loads.sublist(loadsBefore);
      expect(started.first, target);
      expect(started.length, lessThanOrEqualTo(3));
      expect(started, everyElement(inInclusiveRange(target - 1, target + 1)));
      final prefetches = source.prefetched.sublist(prefetchesBefore);
      expect(prefetches.length, lessThanOrEqualTo(3));
      expect(
        prefetches,
        everyElement(inInclusiveRange(target - 1, target + 2)),
      );
      // Prefetches left behind (around page 1) are given up.
      expect(source.windows.last, (target - 2, target + 3));
      await closeAll(tester, store);
    });

    test('prefetches of pages left behind are cancelled', () async {
      final directory = await createTempDir('ns_reader_prefetch_');
      final tokens = <String, LibraryCancelToken?>{};
      final release = Completer<void>();
      final cache = LibraryImageCache(
        cacheDirectory: directory,
        fetcher: (request, {mode = LibraryFetchMode.cacheFirst, cancel}) async {
          tokens[request.uri.path] = cancel;
          await Future.any(<Future<void>>[
            release.future,
            if (cancel != null) cancel.whenCancelled,
          ]);
          cancel?.throwIfCancelled(request.uri);
          return LibraryHttpResponse(
            request: request,
            statusCode: 200,
            bodyBytes: buildPng(2, 2),
            headers: const <String, String>{'content-type': 'image/png'},
            finalUri: request.uri,
            fetchedAt: DateTime.utc(2026),
          );
        },
      );
      final source = LibraryNetworkPageSource(<String>[
        for (var i = 0; i < 10; i++) 'https://example.org/$i.png',
      ], cache: cache);
      source.prefetch(1);
      source.prefetch(6);
      for (var i = 0; i < 50 && tokens.length < 2; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 5));
      }
      expect(tokens.keys, containsAll(<String>['/1.png', '/6.png']));
      expect(source.prefetching, <int>{1, 6});

      // The reader is now around page 6: page 1 stops downloading.
      source.cancelPrefetchOutside(4, 9);
      await Future<void>.delayed(Duration.zero);
      expect(tokens['/1.png']!.isCancelled, isTrue);
      expect(tokens['/6.png']!.isCancelled, isFalse);
      expect(source.prefetching, <int>{6});

      // Back near page 1, it can be prefetched again.
      tokens.remove('/1.png');
      source.prefetch(1);
      for (var i = 0; i < 50 && !tokens.containsKey('/1.png'); i++) {
        await Future<void>.delayed(const Duration(milliseconds: 5));
      }
      expect(tokens['/1.png']!.isCancelled, isFalse);
      // Closing the reader stops every prefetch.
      await source.dispose();
      await Future<void>.delayed(Duration.zero);
      expect(source.prefetching, isEmpty);
      expect(tokens['/1.png']!.isCancelled, isTrue);
      expect(tokens['/6.png']!.isCancelled, isTrue);
      release.complete();
      await cache.idle();
      await directory.delete(recursive: true).catchError((Object _) {
        return directory;
      });
    });
  });
}

class _OrientationRecorder implements LibraryReaderOrientationPlatform {
  @override
  Future<bool> setNativePortraitAllowed(bool allowed) async => true;

  @override
  Future<void> setPreferredOrientations(
    List<DeviceOrientation> orientations,
  ) async {}
}

/// Pages whose images never finish loading (a slow network). Records the
/// decode sizes asked for, the order in which page loads start, the
/// prefetches and the prefetch windows.
class _SlowPageSource implements LibraryPageSource {
  _SlowPageSource(this.length);

  @override
  final int length;

  @override
  String get key => 'slow';

  final List<(int, int?, int?)> requests = <(int, int?, int?)>[];
  final List<int> loads = <int>[];
  final List<int> prefetched = <int>[];
  final List<(int, int)> windows = <(int, int)>[];

  @override
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight}) {
    requests.add((index, cacheWidth, cacheHeight));
    return _SlowImage(this, index, cacheWidth, cacheHeight);
  }

  @override
  void prefetch(int index) => prefetched.add(index);

  @override
  void cancelPrefetchOutside(int first, int last) => windows.add((first, last));

  @override
  Future<void> dispose() async {}
}

class _SlowImage extends ImageProvider<_SlowImage> {
  _SlowImage(this.source, this.index, this.cacheWidth, this.cacheHeight);

  final _SlowPageSource source;
  final int index;
  final int? cacheWidth;
  final int? cacheHeight;

  @override
  Future<_SlowImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_SlowImage>(this);

  @override
  ImageStreamCompleter loadImage(_SlowImage key, ImageDecoderCallback decode) {
    source.loads.add(index);
    return OneFrameImageStreamCompleter(Completer<ImageInfo>().future);
  }

  @override
  bool operator ==(Object other) =>
      other is _SlowImage &&
      identical(other.source, source) &&
      other.index == index &&
      other.cacheWidth == cacheWidth &&
      other.cacheHeight == cacheHeight;

  @override
  int get hashCode => Object.hash(source, index, cacheWidth, cacheHeight);
}

/// Image cache answering every page URL with [png] (no network).
LibraryImageCache _pageImageCache(Directory directory, Uint8List png) =>
    LibraryImageCache(
      cacheDirectory: directory,
      fetcher: (request, {mode = LibraryFetchMode.cacheFirst, cancel}) async =>
          LibraryHttpResponse(
            request: request,
            statusCode: 200,
            bodyBytes: png,
            headers: const <String, String>{'content-type': 'image/png'},
            finalUri: request.uri,
            fetchedAt: DateTime.utc(2026),
          ),
    );
