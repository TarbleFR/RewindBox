// Build 447 accessibility and performance of the three readers
// (docs/library-books-3d-plan.md § 3.12, § 4 row 8, § 5, § 6):
//
// * Reduce Motion, from `MediaQuery.disableAnimations` and from iOS's
//   `AccessibilityFeatures.reduceMotion` (which changes no MediaQuery
//   value: the readers follow it live through
//   `didChangeAccessibilityFeatures`): the page turn is forced to none in
//   the page (CBZ / online), PDF and EPUB/TXT readers, the continuous
//   scroll and the zoom jump, the bookmark ribbon appears without
//   animation, the bars fade in place, the sheets come without animation,
//   the covers and volumes stay still and the opening route is a 200 ms
//   fade;
// * memory pressure: each reader keeps only the textures (and decoded
//   images) of the spread on screen;
// * VoiceOver: "Page N of M" for a page alone, "Pages N and N+1 of M" for a
//   spread, in the three readers, and "Image unavailable" for an image that
//   cannot be shown;
// * the trace `library.reader.*` through LoggerService (observed with
//   `Logger.addLogListener`): the curl once per opening, the textures when
//   they change, each chapter's pagination, the memory pressure, nothing
//   per frame;
// * phase 7 follow-up: "Apply to all books" makes a book's navigation the
//   general one.
//
// Real readers, store, paginator and page curl (drawn by its painter: the
// shader has its own tests); PDF pages through the fake documents of
// library_reader_pdf_modes_test.dart (no PDFium in `flutter test`).
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:logger/logger.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/library_pdf_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_book_pages_view.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_content.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_textures.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_bookmarks.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_chrome.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_toolbar.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_trace.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_paginator.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_view.dart'
    show LibraryReflowStyle;
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/widgets/library_book_cover.dart';
import 'package:neostation/widgets/library_book_open_transition.dart';
import 'package:neostation/widgets/library_book_volume.dart';
import 'package:neostation/widgets/library_reduce_motion.dart';

import 'library_local_fixtures.dart';
import 'library_reader_book_pages_test.dart'
    as book
    show
        bookState,
        closePages,
        landscape,
        openEpub,
        openPages,
        portrait,
        setLayout,
        settlePages,
        textReader,
        turned;
import 'library_reader_page_turns_test.dart'
    as turns
    show
        closeAll,
        curlLayer,
        finish,
        viewPage,
        waitForCurl,
        waitForTextures,
        waitUntil;
import 'library_reader_pdf_modes_test.dart'
    as pdf
    show
        FakeOpener,
        FakePdfDocument,
        closeReader,
        finishTurn,
        mockPathProvider,
        openReader,
        pagesOf,
        pdfPath,
        portrait,
        readerOf,
        rendered,
        spreadLabel;
import 'library_reader_settings_sections_test.dart'
    as sections
    show closeAll, inSheet, openSettings, sheetBindings, tall, tapChip;
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

String tr(String language, String key) =>
    LibraryReaderLocale.values[language]![key]!;

String enFormat(String key, Map<String, Object> values) {
  var text = en(key);
  values.forEach((name, value) => text = text.replaceAll('{$name}', '$value'));
  return text;
}

/// One page per screen for the page reader.
const Size phone = Size(600, 900);

/// Two-page spreads (automatic in landscape).
const Size wide = Size(900, 600);

/// Reduce Motion as iOS reports it ([ios]: `reduceMotion`, which no
/// MediaQuery value carries) or as Android and the tests do
/// (`disableAnimations`), for the rest of the test.
void reduceMotion(WidgetTester tester, {required bool ios}) {
  tester.platformDispatcher.accessibilityFeaturesTestValue =
      FakeAccessibilityFeatures(reduceMotion: ios, disableAnimations: !ios);
  addTearDown(tester.platformDispatcher.clearAccessibilityFeaturesTestValue);
}

/// The trace lines `library.reader.*` written through LoggerService from
/// now on.
List<String> recordTrace() {
  final lines = <String>[];
  void listener(LogEvent event) {
    final message = event.message;
    if (message is String && message.startsWith(LibraryReaderTrace.prefix)) {
      lines.add(message);
    }
  }

  Logger.addLogListener(listener);
  addTearDown(() => Logger.removeLogListener(listener));
  return lines;
}

LibraryPageReaderScreenState pageState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

LibraryBookmarkRibbon ribbonOf(WidgetTester tester) =>
    tester.widget<LibraryBookmarkRibbon>(find.byType(LibraryBookmarkRibbon));

/// The slide of the bar holding a widget of type [bar].
AnimatedSlide barSlide(WidgetTester tester, Type bar) =>
    tester.widget<AnimatedSlide>(
      find
          .ancestor(of: find.byType(bar), matching: find.byType(AnimatedSlide))
          .first,
    );

/// Whether the floating back button takes touches.
bool floatingBackTouchable(WidgetTester tester) => !tester
    .widget<IgnorePointer>(
      find
          .ancestor(
            of: find.byType(LibraryReaderFloatingBackButton),
            matching: find.byType(IgnorePointer),
          )
          .first,
    )
    .ignoring;

/// An image node with exactly this label (the page slider says "Page N of
/// M" too, not as an image).
SemanticsFinder pageImage(String label) => find.semantics.byPredicate(
  (node) =>
      node.label == label && node.getSemanticsData().flagsCollection.isImage,
);

/// The first page of a page reader as the first test pages: 1 of 5.
String pageOfTotal(int page, int total) =>
    enFormat('pageOfTotal', <String, Object>{'page': page, 'total': total});

/// Runs the paginator's turns and real I/O until [condition] holds.
Future<void> waitPages(
  WidgetTester tester,
  bool Function() condition, {
  String? reason,
}) async {
  for (var i = 0; i < 60 && !condition(); i++) {
    await book.settlePages(tester, rounds: 1);
  }
  expect(condition(), isTrue, reason: reason);
}

/// The settings sheet stays where it is drawn first: it did not slide in.
Future<void> expectSheetStill(WidgetTester tester) async {
  final top = tester.getTopLeft(find.byType(BottomSheet)).dy;
  await tester.pump(const Duration(milliseconds: 400));
  expect(tester.getTopLeft(find.byType(BottomSheet)).dy, top);
}

/// Closes the sheet; without animation it is gone at once.
Future<void> closeSheetAtOnce(WidgetTester tester) async {
  Navigator.of(tester.element(find.byType(BottomSheet))).pop();
  await tester.pump();
  await tester.pump();
  expect(find.byType(BottomSheet), findsNothing);
}

/// Page images of a book whose pages in [broken] hold bytes no codec reads.
class BrokenPageSource extends MemoryPageSource {
  BrokenPageSource(super.count, {required this.broken}) : super(key: 'broken');

  final Set<int> broken;

  @override
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight}) {
    if (broken.contains(index)) {
      return MemoryImage(Uint8List.fromList(List<int>.filled(64, 7)));
    }
    return super.imageFor(
      index,
      cacheWidth: cacheWidth,
      cacheHeight: cacheHeight,
    );
  }
}

/// An EPUB of the fixture whose first chapter is [chapter1], with [extra]
/// files.
Future<LibraryEpubDocument> epubWith(
  WidgetTester tester, {
  required String chapter1,
  List<FixtureZipEntry> extra = const <FixtureZipEntry>[],
  bool rtl = false,
}) async => (await tester.runAsync(() async {
  final directory = await createTempDir('ns_reader_a11y_epub_');
  final file = await writeFile(
    directory,
    'book.epub',
    buildEpub3(chapter1: chapter1, extra: extra, rtl: rtl),
  );
  return LibraryEpubDocument.open(file.path);
}))!;

/// An EPUB whose first chapter holds the picture of the fixture, a missing
/// picture and some text.
Future<LibraryEpubDocument> picturesEpub(WidgetTester tester) => book.openEpub(
  tester,
  chapter1: xhtml(
    '<h1>Pictures</h1><p><img src="../images/pic.png" alt="Pic"/></p>'
    '<p>Between the pictures.</p><p><img src="../images/missing.png"/></p>'
    '<p>After the pictures.</p>',
  ),
);

void main() {
  setUpReaderEnvironment();
  setUp(() {
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('Reduce Motion', () {
    testWidgets('libraryReduceMotion: MediaQuery.disableAnimations, or iOS '
        'Reduce Motion that no MediaQuery value carries', (tester) async {
      late BuildContext context;
      Widget probe(MediaQueryData data) => MediaQuery(
        data: data,
        child: Builder(
          builder: (built) {
            context = built;
            return const SizedBox.shrink();
          },
        ),
      );
      await tester.pumpWidget(probe(const MediaQueryData()));
      expect(libraryReduceMotion(context), isFalse);
      await tester.pumpWidget(
        probe(const MediaQueryData(disableAnimations: true)),
      );
      expect(libraryReduceMotion(context), isTrue);
      reduceMotion(tester, ios: true);
      await tester.pumpWidget(probe(const MediaQueryData()));
      expect(MediaQuery.disableAnimationsOf(context), isFalse);
      expect(libraryReduceMotion(context), isTrue);
    });

    for (final ios in <bool>[false, true]) {
      final setting = ios ? 'iOS Reduce Motion' : 'disableAnimations';

      testWidgets('$setting: the page reader turns, scrolls and zooms at once; '
          'the ribbon, the bars and the sheets do not move', (tester) async {
        useSurface(tester, size: phone);
        final (store, _) = await createStore(tester);
        reduceMotion(tester, ios: ios);
        await pumpReader(
          tester,
          LibraryPageReaderScreen(
            content: FakePageContent(progressKey: 'local:rm-page-$ios'),
            store: store,
          ),
        );
        final state = pageState(tester);
        final context = tester.element(find.byType(LibraryPageReaderScreen));
        expect(MediaQuery.disableAnimationsOf(context), !ios);
        expect(state.controller.reduceMotion, isTrue);
        expect(state.controller.turnStyle, LibraryPageTurnStyle.none);
        // A session override: the setting stays.
        expect(store.settings.turnStyle, LibraryPageTurnStyle.curl);
        expect(turns.curlLayer(tester).enabled, isFalse);
        state.gamepadBindings.right!();
        await tester.pump();
        // The next frame shows the next page: no animation ran.
        expect(turns.viewPage(tester), 1);
        expect(state.controller.page, 1);

        // The ribbon appears without sliding.
        state.gamepadBindings.y!();
        await tester.pump();
        expect(ribbonOf(tester).visible, isTrue);
        expect(ribbonOf(tester).animate, isFalse);

        // The bars fade in place; shown again, the top bar's arrow takes
        // the touches at once.
        if (!state.chromeVisible) {
          // Hidden by the turn.
          state.gamepadBindings.select!();
          await tester.pump(const Duration(milliseconds: 300));
        }
        expect(state.chromeVisible, isTrue);
        state.gamepadBindings.select!();
        await tester.pump();
        expect(state.chromeVisible, isFalse);
        for (final bar in <Type>[LibraryReaderTopBar, LibraryReaderToolbar]) {
          final slide = barSlide(tester, bar);
          expect(slide.offset, Offset.zero, reason: '$bar');
          expect(slide.duration, Duration.zero, reason: '$bar');
        }
        expect(floatingBackTouchable(tester), isTrue);
        await tester.pump(const Duration(milliseconds: 300));
        state.gamepadBindings.select!();
        await tester.pump();
        expect(state.chromeVisible, isTrue);
        expect(floatingBackTouchable(tester), isFalse);

        // The settings sheet comes and goes without animation.
        state.gamepadBindings.start!();
        await tester.pump();
        expect(find.text(en('settingsTitle')), findsOneWidget);
        await expectSheetStill(tester);
        await closeSheetAtOnce(tester);

        // A double tap zooms at once.
        final centre = Offset(phone.width / 2, phone.height / 2);
        await tester.tapAt(centre);
        await tester.pump(const Duration(milliseconds: 50));
        await tester.tapAt(centre + const Offset(2, 2));
        await tester.pump();
        expect(state.zoomed, isTrue);
        await turns.closeAll(tester, store);
      });

      testWidgets('$setting: the vertical strip scrolls at once', (
        tester,
      ) async {
        useSurface(tester, size: phone);
        final (store, _) = await createStore(tester);
        reduceMotion(tester, ios: ios);
        await pumpReader(
          tester,
          LibraryPageReaderScreen(
            content: FakePageContent(
              progressKey: 'local:rm-strip-$ios',
              pagesPerChapter: 12,
              layoutHint: LibraryPageLayoutHint.vertical,
            ),
            store: store,
          ),
        );
        final state = pageState(tester);
        expect(find.byType(ListView), findsOneWidget);
        final scrollable = tester.state<ScrollableState>(
          find.descendant(
            of: find.byType(ListView),
            matching: find.byType(Scrollable),
          ),
        );
        expect(scrollable.position.pixels, 0);
        state.gamepadBindings.down!();
        // Moved before any frame: a jump, not an animation.
        expect(scrollable.position.pixels, greaterThan(0));
        await tester.pump();
        await turns.closeAll(tester, store);
      });

      testWidgets('$setting: the PDF pages turn at once and the ribbon does '
          'not slide', (tester) async {
        pdf.mockPathProvider();
        useSurface(tester, size: pdf.portrait);
        final (store, _) = await createStore(tester);
        reduceMotion(tester, ios: ios);
        await pdf.openReader(
          tester,
          store,
          pdf.FakeOpener(),
          progressKey: 'local:rm-pdf-$ios',
        );
        final reader = pdf.readerOf(tester);
        expect(reader.mode, LibraryPdfMode.pages);
        expect(store.settings.turnStyle, LibraryPageTurnStyle.curl);
        expect(turns.curlLayer(tester).enabled, isFalse);
        reader.gamepadBindings.down!();
        await tester.pump();
        expect(pdf.pagesOf(tester).spreadIndex, 1);
        expect(reader.pageNumber, 2);
        reader.gamepadBindings.y!();
        await tester.pump();
        expect(ribbonOf(tester).visible, isTrue);
        expect(ribbonOf(tester).animate, isFalse);
        await pdf.closeReader(tester, store);
      });

      testWidgets('$setting: EPUB/TXT pages turn at once, the continuous '
          'scroll jumps', (tester) async {
        useSurface(tester, size: book.portrait);
        final (store, _) = await createStore(tester);
        reduceMotion(tester, ios: ios);
        await book.openPages(
          tester,
          book.textReader(store, progressKey: 'local:rm-text-$ios'),
        );
        var state = book.bookState(tester);
        expect(turns.curlLayer(tester).enabled, isFalse);
        state.gamepadBindings.down!();
        // No animation: shown before any frame.
        expect(state.shownSpread!.first.indexInChapter, 1);
        await book.settlePages(tester, rounds: 1);
        state.gamepadBindings.y!();
        await tester.pump();
        expect(ribbonOf(tester).visible, isTrue);
        expect(ribbonOf(tester).animate, isFalse);
        await book.closePages(tester, store);

        final (scroll, _) = await createStore(tester);
        book.setLayout(scroll, textLayout: LibraryTextLayout.scroll);
        await book.openPages(
          tester,
          book.textReader(scroll, progressKey: 'local:rm-scroll-$ios'),
        );
        state = book.bookState(tester);
        expect(state.textLayout, LibraryTextLayout.scroll);
        expect(state.currentPosition!.block, 0);
        state.gamepadBindings.right!();
        // One frame, no time: the text has moved by a screen already.
        await tester.pump();
        expect(state.currentPosition!.block, greaterThan(0));
        await book.closePages(tester, scroll);
      });
    }

    testWidgets('iOS Reduce Motion is followed live by the page reader', (
      tester,
    ) async {
      useSurface(tester, size: phone);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:live-page'),
          store: store,
        ),
      );
      final state = pageState(tester);
      state.gamepadBindings.y!();
      await tester.pump();
      expect(turns.curlLayer(tester).enabled, isTrue);
      expect(ribbonOf(tester).animate, isTrue);
      reduceMotion(tester, ios: true);
      await tester.pump();
      expect(state.controller.turnStyle, LibraryPageTurnStyle.none);
      expect(turns.curlLayer(tester).enabled, isFalse);
      expect(ribbonOf(tester).animate, isFalse);
      expect(barSlide(tester, LibraryReaderTopBar).duration, Duration.zero);
      tester.platformDispatcher.clearAccessibilityFeaturesTestValue();
      await tester.pump();
      expect(state.controller.turnStyle, LibraryPageTurnStyle.curl);
      expect(turns.curlLayer(tester).enabled, isTrue);
      expect(ribbonOf(tester).animate, isTrue);
      expect(
        barSlide(tester, LibraryReaderTopBar).duration,
        LibraryReaderChromeOverlay.duration,
      );
      await turns.closeAll(tester, store);
    });

    testWidgets('iOS Reduce Motion is followed live by the PDF reader', (
      tester,
    ) async {
      pdf.mockPathProvider();
      useSurface(tester, size: pdf.portrait);
      final (store, _) = await createStore(tester);
      await pdf.openReader(tester, store, pdf.FakeOpener());
      expect(turns.curlLayer(tester).enabled, isTrue);
      reduceMotion(tester, ios: true);
      await tester.pump();
      expect(turns.curlLayer(tester).enabled, isFalse);
      tester.platformDispatcher.clearAccessibilityFeaturesTestValue();
      await tester.pump();
      expect(turns.curlLayer(tester).enabled, isTrue);
      await pdf.closeReader(tester, store);
    });

    testWidgets('iOS Reduce Motion is followed live by the EPUB/TXT reader', (
      tester,
    ) async {
      useSurface(tester, size: book.portrait);
      final (store, _) = await createStore(tester);
      await book.openPages(
        tester,
        book.textReader(store, progressKey: 'local:live-text'),
      );
      final state = book.bookState(tester);
      expect(turns.curlLayer(tester).enabled, isTrue);
      reduceMotion(tester, ios: true);
      await tester.pump();
      expect(turns.curlLayer(tester).enabled, isFalse);
      state.gamepadBindings.down!();
      expect(state.shownSpread!.first.indexInChapter, 1);
      await book.settlePages(tester, rounds: 1);
      tester.platformDispatcher.clearAccessibilityFeaturesTestValue();
      await tester.pump();
      expect(turns.curlLayer(tester).enabled, isTrue);
      await book.closePages(tester, store);
    });

    testWidgets('iOS Reduce Motion keeps covers and volumes still (read when '
        'the cover would move)', (tester) async {
      Future<void> pumpCover({required bool selected}) => tester.pumpWidget(
        MaterialApp(
          home: Center(
            child: SizedBox(
              width: 160,
              height: 220,
              child: LibraryBookCover(
                selected: selected,
                thickness: LibraryBookThickness.fixed,
                child: const ColoredBox(color: Colors.teal),
              ),
            ),
          ),
        ),
      );
      LibraryBookVolume volume() =>
          tester.widget<LibraryBookVolume>(find.byType(LibraryBookVolume));

      await pumpCover(selected: false);
      reduceMotion(tester, ios: true);
      await pumpCover(selected: true);
      await tester.pump();
      expect(volume().opening, 0);
      expect(tester.binding.transientCallbackCount, 0);
      // A press does not open it either.
      final touch = await tester.startGesture(
        tester.getCenter(find.byType(LibraryBookCover)),
      );
      await tester.pump(const Duration(milliseconds: 160));
      expect(volume().opening, 0);
      await touch.up();
      await tester.pump();
      expect(tester.binding.hasScheduledFrame, isFalse);

      // Without it, the same cover opens.
      tester.platformDispatcher.clearAccessibilityFeaturesTestValue();
      await pumpCover(selected: false);
      await tester.pumpAndSettle();
      await pumpCover(selected: true);
      await tester.pump(const Duration(milliseconds: 80));
      expect(volume().opening, greaterThan(0));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    });

    testWidgets('iOS Reduce Motion: the opening route is a 200 ms fade', (
      tester,
    ) async {
      final route = LibraryReaderRoute<void>(
        builder: (_) => const SizedBox.shrink(),
      );
      expect(route.transitionDuration, LibraryReaderRoute.openDuration);
      reduceMotion(tester, ios: true);
      expect(route.motionReduced, isTrue);
      expect(route.transitionDuration, const Duration(milliseconds: 200));
      expect(
        route.reverseTransitionDuration,
        const Duration(milliseconds: 200),
      );
    });
  });

  group('memory pressure', () {
    testWidgets('page reader: only the spread on screen keeps its textures', (
      tester,
    ) async {
      useSurface(tester, size: wide);
      final (store, _) = await createStore(tester);
      final trace = recordTrace();
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            progressKey: 'local:pressure-page',
            pagesPerChapter: 7,
            startPage: 1,
          ),
          store: store,
        ),
      );
      final state = pageState(tester);
      // Pages are given textures once decoded, around a turn.
      await turns.waitForCurl(tester, state);
      state.gamepadBindings.right!();
      await turns.finish(tester);
      final spreads = state.spreads!;
      final shown = spreads.pagesOf(spreads.spreadOf(state.controller.page));
      expect(shown, <int>[3, 4]);
      // The spread shown and the pages of its neighbours.
      await turns.waitUntil(
        tester,
        () => state.textures.textures >= 3,
        reason: 'the curl renders the spreads around',
      );
      tester.binding.handleMemoryPressure();
      final textures = state.textures;
      expect(textures.textures, 2);
      final kept = <int>{
        for (final key in textures.retained)
          if (textures.contains(key)) (key as LibraryPageTextureKey).page,
      };
      expect(kept, <int>{3, 4});
      await tester.pump();
      expect(trace, contains('library.reader.memory_pressure'));
      expect(
        trace.last,
        'library.reader.textures:${textures.textures}/${textures.bytes}',
      );
      // Reading goes on: the next spread comes.
      state.gamepadBindings.right!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      await settle(tester, rounds: 2);
      expect(state.controller.page, 5);
      await turns.closeAll(tester, store);
    });

    testWidgets('PDF pages: only the page on screen keeps its texture', (
      tester,
    ) async {
      pdf.mockPathProvider();
      useSurface(tester, size: pdf.portrait);
      final (store, _) = await createStore(tester);
      final trace = recordTrace();
      await pdf.openReader(tester, store, pdf.FakeOpener());
      final view = pdf.pagesOf(tester);
      expect(view.textures.textures, greaterThanOrEqualTo(2));
      tester.binding.handleMemoryPressure();
      final textures = view.textures;
      expect(textures.textures, 1);
      final kept = <int>{
        for (final key in textures.retained)
          if (textures.contains(key)) (key as LibraryPageTextureKey).page,
      };
      expect(kept, <int>{0});
      await tester.pump();
      expect(trace, contains('library.reader.memory_pressure'));
      expect(trace.last, 'library.reader.textures:1/${textures.bytes}');
      await pdf.closeReader(tester, store);
    });

    testWidgets('EPUB/TXT pages: only the spread on screen keeps its '
        'textures', (tester) async {
      useSurface(tester, size: book.portrait);
      final (store, _) = await createStore(tester);
      final trace = recordTrace();
      await book.openPages(
        tester,
        book.textReader(store, progressKey: 'local:pressure-text'),
      );
      final state = book.bookState(tester);
      state.gamepadBindings.down!();
      await book.turned(tester);
      await waitPages(
        tester,
        () => state.pageTextures!.textures >= 2,
        reason: 'the curl renders the pages around',
      );
      final generation = state.paginator!.imagesGeneration;
      tester.binding.handleMemoryPressure();
      final textures = state.pageTextures!;
      expect(textures.textures, 1);
      final page = state.shownSpread!.first;
      final kept = <int>{
        for (final key in textures.retained)
          if (textures.contains(key)) (key as LibraryPageTextureKey).page,
      };
      expect(kept, <int>{(page.chapter << 20) | page.indexInChapter});
      // The decoded images were released too.
      expect(state.paginator!.imagesGeneration, generation + 1);
      await tester.pump();
      expect(trace, contains('library.reader.memory_pressure'));
      expect(trace.last, 'library.reader.textures:1/${textures.bytes}');
      await book.closePages(tester, store);
    });

    testWidgets('EPUB pages: the images of the page on screen stay decoded, '
        'the book bytes are read again when needed', (tester) async {
      useSurface(tester, size: book.portrait);
      final (store, _) = await createStore(tester);
      final document = await picturesEpub(tester);
      await book.openPages(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:pressure-epub',
          title: 'Pictures',
          store: store,
        ),
      );
      final state = book.bookState(tester);
      final page = state.shownSpread!.first;
      final picture = page.slices.firstWhere(
        (slice) =>
            slice.kind == LibraryReflowSliceKind.image && !slice.imageFailed,
      );
      final href = picture.unit.source.imageHref!;
      await waitPages(
        tester,
        () => state.paginator!.decodedImages == 1,
        reason: 'the page shown decodes its picture',
      );
      expect(state.reflowImages.loaded(href), isNotNull);
      tester.binding.handleMemoryPressure();
      expect(state.paginator!.decodedImages, 1);
      expect(state.paginator!.needsPrepare(page), isFalse);
      expect(state.reflowImages.loaded(href), isNull);
      // Painted again (another theme), the page needs no second decode.
      store.updateSettings(
        store.settings.copyWith(theme: LibraryReaderTheme.sepia),
      );
      await book.settlePages(tester, rounds: 2);
      expect(state.paginator!.decodedImages, 1);
      await book.closePages(tester, store);
    });

    testWidgets(
      'paginator: releaseImages keeps the pages given; a page painted '
      'again prepares its images again',
      (tester) async {
        final paragraphs = List<String>.generate(
          40,
          (i) =>
              '<p>Paragraph $i with enough words to fill a line or two of '
              'the page.</p>',
        ).join();
        final document = await epubWith(
          tester,
          chapter1: xhtml(
            '<h1>One</h1><p><img src="../images/pic.png"/></p>$paragraphs'
            '<p><img src="../images/second.png"/></p><p>The end.</p>',
          ),
          extra: <FixtureZipEntry>[
            FixtureZipEntry(
              'OEBPS/images/second.png',
              buildPng(12, 16),
              deflate: false,
            ),
          ],
        );
        final source = LibraryEpubReflowSource(document);
        final paginator = LibraryReflowPaginator(
          source: source,
          style: const LibraryReflowStyle(
            palette: LibraryReaderPalette.light,
            fontSize: 18,
            lineHeight: 1.5,
            fontFamily: LibraryReaderFontFamily.serif,
            justify: true,
            margin: 16,
          ),
          pageSize: const Size(360, 640),
          padding: const EdgeInsets.fromLTRB(16, 40, 16, 40),
          textScaler: TextScaler.noScaling,
        );
        addTearDown(paginator.dispose);
        final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
        final withImages = <LibraryReflowPageSpec>[
          for (final page in pages)
            if (page.slices.any(
              (slice) =>
                  slice.kind == LibraryReflowSliceKind.image &&
                  !slice.imageFailed,
            ))
              page,
        ];
        expect(withImages, hasLength(2));
        final (first, last) = (withImages.first, withImages.last);
        await tester.runAsync(() => paginator.prepare(first));
        await tester.runAsync(() => paginator.prepare(last));
        expect(paginator.decodedImages, 2);
        final generation = paginator.imagesGeneration;
        paginator.releaseImages(keep: <LibraryReflowPageSpec>[last]);
        expect(paginator.decodedImages, 1);
        expect(paginator.imagesGeneration, generation + 1);
        expect(paginator.needsPrepare(last), isFalse);
        expect(paginator.needsPrepare(first), isTrue);
        await tester.runAsync(() => paginator.prepare(first));
        expect(paginator.needsPrepare(first), isFalse);
        paginator.releaseImages();
        expect(paginator.decodedImages, 0);
        await tester.runAsync(source.close);
      },
    );
  });

  group('VoiceOver', () {
    testWidgets('page reader: "Page N of M" for a page alone, in pages and '
        'in the vertical strip', (tester) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: phone);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:vo-page'),
          store: store,
        ),
      );
      final state = pageState(tester);
      await turns.waitUntil(
        tester,
        () => pageImage(pageOfTotal(1, 5)).evaluate().isNotEmpty,
        reason: 'the first page decodes',
      );
      expect(pageImage(pageOfTotal(1, 5)), findsOne);
      expect(
        find.semantics.byLabel(
          enFormat('pageNumber', <String, Object>{'page': 1}),
        ),
        findsNothing,
      );
      state.controller.toggleMode();
      await frames(tester);
      expect(find.byType(ListView), findsOneWidget);
      await turns.waitUntil(
        tester,
        () => pageImage(pageOfTotal(1, 5)).evaluate().isNotEmpty,
        reason: 'the strip decodes its pages',
      );
      expect(pageImage(pageOfTotal(1, 5)), findsOne);
      await turns.closeAll(tester, store);
      semantics.dispose();
    });

    testWidgets('page reader: a page that cannot be decoded says its number, '
        '"Image unavailable" and offers Retry', (tester) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: phone);
      final (store, _) = await createStore(tester);
      final source = BrokenPageSource(3, broken: <int>{0});
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            progressKey: 'local:vo-broken',
            loader: (index, cancel) async => source,
          ),
          store: store,
        ),
      );
      await turns.waitUntil(
        tester,
        () => find.text(en('imageUnavailable')).evaluate().isNotEmpty,
        reason: 'the codec gives up',
      );
      expect(find.text(en('errorGeneric')), findsNothing);
      expect(find.text(en('retry')), findsOneWidget);
      // The page's node first ("Page 1 of 3"), then, inside it, the error
      // and Retry (the error view scrolls: nodes of their own).
      final page = find.semantics.byLabel(pageOfTotal(1, 3));
      expect(
        find.semantics.descendant(
          of: page,
          matching: find.semantics.byLabel(en('imageUnavailable')),
        ),
        findsOne,
      );
      expect(
        find.semantics.descendant(
          of: page,
          matching: find.semantics.byLabel(en('retry')),
        ),
        findsOne,
      );
      await turns.closeAll(tester, store);
      semantics.dispose();
    });

    testWidgets('PDF pages: a page PDFium cannot render says "Image '
        'unavailable" after "Page N of M"', (tester) async {
      final semantics = tester.ensureSemantics();
      pdf.mockPathProvider();
      useSurface(tester, size: pdf.portrait);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: pdf.pdfPath,
          title: 'Manual',
          progressKey: 'local:vo-pdf',
          store: store,
          openDocument: (path) async {
            final document = pdf.FakePdfDocument(3);
            document.page(0).blank = true;
            return document;
          },
        ),
      );
      await pdf.rendered(tester);
      final view = pdf.pagesOf(tester);
      expect(view.unavailablePages, <int>{0});
      expect(
        pdf.spreadLabel('${pageOfTotal(1, 3)}\n${en('imageUnavailable')}'),
        findsOneWidget,
      );
      // The next page renders: it is only "Page 2 of 3".
      pdf.readerOf(tester).gamepadBindings.down!();
      await pdf.finishTurn(tester);
      await pdf.rendered(tester);
      expect(pdf.pagesOf(tester).spreadIndex, 1);
      expect(pdf.spreadLabel(pageOfTotal(2, 3)), findsOneWidget);
      await pdf.closeReader(tester, store);
      semantics.dispose();
    });

    testWidgets('EPUB/TXT pages: "Page N of M" for a page alone, "Pages N '
        'and N+1 of M" for a spread, before the text of the pages', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: book.landscape);
      final (store, _) = await createStore(tester);
      book.setLayout(store, turnStyle: LibraryPageTurnStyle.none);
      await book.openPages(
        tester,
        book.textReader(store, progressKey: 'local:vo-text'),
      );
      final state = book.bookState(tester);
      await waitPages(
        tester,
        () => state.paginator!.pageCountOf(0) != null,
        reason: 'the first section is laid out',
      );
      final total = state.paginator!.pageCountOf(0)!;
      SemanticsNode spreadNode() => tester.getSemantics(
        find.byWidgetPredicate(
          (widget) =>
              widget is LibraryBookSpreadView &&
              widget.spread == state.shownSpread,
        ),
      );
      await tester.pump();
      // The book's first page, alone on its side.
      expect(state.shownSpread!.isPair, isFalse);
      expect(spreadNode().label, pageOfTotal(1, total));
      state.gamepadBindings.down!();
      await book.settlePages(tester);
      expect(state.shownSpread!.isPair, isTrue);
      expect(
        spreadNode().label,
        enFormat('pagesOfTotal', <String, Object>{
          'first': 2,
          'second': 3,
          'total': total,
        }),
      );
      // The text of each page follows, in its own node.
      final paginator = state.paginator!;
      for (final page in state.shownSpread!.pages) {
        final canvas = find.byWidgetPredicate(
          (widget) => widget is LibraryBookPageCanvas && widget.page == page,
        );
        expect(
          tester.getSemantics(canvas).label,
          paginator.textOf(page, imageUnavailable: en('imageUnavailable')),
        );
      }
      await book.closePages(tester, store);
      semantics.dispose();
    });

    testWidgets('EPUB pages: an image that cannot be shown says "Image '
        'unavailable"; a picture keeps its description', (tester) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: book.portrait);
      final (store, _) = await createStore(tester);
      final document = await picturesEpub(tester);
      await book.openPages(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:vo-epub',
          title: 'Pictures',
          store: store,
        ),
      );
      final state = book.bookState(tester);
      final page = state.shownSpread!.first;
      expect(
        page.slices.where((slice) => slice.imageFailed),
        hasLength(1),
        reason: 'the missing picture is on the first page',
      );
      await book.settlePages(tester, rounds: 2);
      final canvas = find.byWidgetPredicate(
        (widget) => widget is LibraryBookPageCanvas && widget.page == page,
      );
      final label = tester.getSemantics(canvas).label;
      expect(label, contains('Pic'));
      expect(label, contains(en('imageUnavailable')));
      expect(label, contains('After the pictures.'));
      // Without a translation given, the text is the 447 one.
      expect(state.paginator!.textOf(page), isNot(contains('unavailable')));
      await book.closePages(tester, store);
      semantics.dispose();
    });
  });

  group('trace', () {
    testWidgets('page reader: the curl once, the textures when they change, '
        'the memory pressure; nothing per frame', (tester) async {
      useSurface(tester, size: phone);
      final (store, _) = await createStore(tester);
      final trace = recordTrace();
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:trace-page'),
          store: store,
        ),
      );
      final state = pageState(tester);
      expect(
        trace.where((line) => line.startsWith('library.reader.curl:')),
        <String>['library.reader.curl:painter'],
      );
      // Textures come around a first turn.
      await turns.waitForCurl(tester, state);
      state.gamepadBindings.right!();
      await turns.finish(tester);
      await turns.waitForTextures(tester, state);
      await settle(tester, rounds: 2);
      // A turn of 380 ms: at most a couple of lines for its many frames.
      final before = trace.length;
      state.gamepadBindings.right!();
      for (var i = 0; i < 30; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      await settle(tester, rounds: 2);
      expect(state.controller.page, 2);
      final turn = trace.sublist(before);
      expect(turn.length, lessThanOrEqualTo(2));
      for (final line in turn) {
        expect(line, matches(RegExp(r'^library\.reader\.textures:\d+/\d+$')));
      }
      // Once the neighbours are rendered and the page saved, idle frames
      // write nothing.
      await settle(tester, rounds: 4);
      await tester.pump(const Duration(seconds: 1));
      await settle(tester, rounds: 2);
      final idle = trace.length;
      for (var i = 0; i < 20; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      expect(trace.length, idle);
      tester.binding.handleMemoryPressure();
      await tester.pump();
      expect(trace[idle], 'library.reader.memory_pressure');
      // Only changes are written.
      for (var i = 1; i < trace.length; i++) {
        expect(trace[i], isNot(trace[i - 1]), reason: trace[i]);
      }
      await turns.closeAll(tester, store);
      // Closed: nothing more.
      final closed = trace.length;
      tester.binding.handleMemoryPressure();
      await tester.pump();
      expect(trace.length, closed);
    });

    testWidgets('EPUB/TXT pages: each chapter laid out once per pagination, '
        'again after a new typography', (tester) async {
      useSurface(tester, size: book.portrait);
      final (store, _) = await createStore(tester);
      final trace = recordTrace();
      await book.openPages(
        tester,
        book.textReader(store, progressKey: 'local:trace-text'),
      );
      final state = book.bookState(tester);
      await waitPages(
        tester,
        () => state.paginator!.pageCountOf(0) != null,
        reason: 'the first section is laid out',
      );
      await book.settlePages(tester, rounds: 2);
      List<String> paginated(int chapter) => <String>[
        for (final line in trace)
          if (line.startsWith('library.reader.paginate:$chapter:')) line,
      ];
      final opened = paginated(0).length;
      expect(opened, greaterThanOrEqualTo(1));
      // Idle frames lay nothing out again.
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      expect(paginated(0), hasLength(opened));
      for (final line in trace.where(
        (line) => line.startsWith('library.reader.paginate:'),
      )) {
        expect(line, matches(RegExp(r'^library\.reader\.paginate:\d+:\d+$')));
      }
      expect(
        trace.where((line) => line.startsWith('library.reader.curl:')),
        <String>['library.reader.curl:painter'],
      );
      store.updateSettings(store.settings.copyWith(fontSize: 24));
      await book.settlePages(tester);
      await waitPages(
        tester,
        () => state.paginator!.pageCountOf(0) != null,
        reason: 'laid out again',
      );
      await book.settlePages(tester, rounds: 2);
      expect(paginated(0), hasLength(opened + 1));
      await book.closePages(tester, store);
    });

    testWidgets('PDF: the curl once, the textures after a turn', (
      tester,
    ) async {
      pdf.mockPathProvider();
      useSurface(tester, size: pdf.portrait);
      final (store, _) = await createStore(tester);
      final trace = recordTrace();
      await pdf.openReader(tester, store, pdf.FakeOpener());
      expect(
        trace.where((line) => line.startsWith('library.reader.curl:')),
        <String>['library.reader.curl:painter'],
      );
      pdf.readerOf(tester).gamepadBindings.down!();
      await pdf.finishTurn(tester);
      await pdf.rendered(tester);
      final textures = pdf.pagesOf(tester).textures;
      expect(
        trace.where((line) => line.startsWith('library.reader.textures:')),
        isNotEmpty,
      );
      pdf.readerOf(tester).gamepadBindings.down!();
      await pdf.finishTurn(tester);
      await pdf.rendered(tester);
      expect(
        trace.lastWhere((line) => line.startsWith('library.reader.textures:')),
        matches(RegExp(r'^library\.reader\.textures:\d+/\d+$')),
      );
      expect(textures.isDisposed, isFalse);
      await pdf.closeReader(tester, store);
    });
  });

  group('Apply to all books (phase 7 follow-up)', () {
    testWidgets('(a, d) no content hint: the book\'s navigation becomes the '
        'general one, its entry is cleared, it shows the same; other books '
        'keep theirs; confirmed in the sheet', (tester) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: sections.tall);
      final (store, _) = await createStore(tester);
      const key = 'local:apply';
      const other = 'online:source:other';
      // A general choice the book does not make stays as it is.
      store.updateSettings(store.settings.copyWith(firstPageAlone: false));
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          turnStyle: LibraryPageTurnStyle.slide,
          doublePage: LibraryDoublePageMode.never,
          pageDirection: LibraryPageDirection.rtl,
        ),
      );
      store.updateBookSettings(
        other,
        const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.none),
      );
      final kept = store.bookSettingsFor(other);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: key),
          store: store,
        ),
      );
      final state = pageState(tester);
      expect(state.controller.turnStyle, LibraryPageTurnStyle.slide);
      final shown = state.controller.effective;
      await sections.openSettings(tester, state.gamepadBindings.start!);
      final apply = sections.inSheet(
        find.text(en('applyNavigationToAllBooks')),
      );
      expect(apply, findsOneWidget);
      // Between the note and "Revert to general settings".
      double top(String key) =>
          tester.getTopLeft(sections.inSheet(find.text(en(key)))).dy;
      expect(
        top('bookSettingsActive'),
        lessThan(top('applyNavigationToAllBooks')),
      );
      expect(
        top('applyNavigationToAllBooks'),
        lessThan(top('resetBookSettings')),
      );

      await tester.tap(apply);
      await tester.pump();
      expect(store.settings.turnStyle, LibraryPageTurnStyle.slide);
      expect(store.settings.doublePage, LibraryDoublePageMode.never);
      expect(store.settings.pageDirection, LibraryPageDirection.rtl);
      expect(store.settings.firstPageAlone, isFalse);
      expect(store.bookSettingsFor(key), isNull);
      expect(store.bookSettingsFor(other), kept);
      // Nothing changes on screen.
      expect(state.controller.effective, shown);
      expect(state.controller.turnStyle, LibraryPageTurnStyle.slide);
      expect(state.controller.rightToLeft, isTrue);
      // Said in the sheet (VoiceOver reads it as it appears); the rows of
      // the book's own settings are gone.
      final confirmation = sections.inSheet(
        find.text(en('navigationAppliedToAllBooks')),
      );
      expect(confirmation, findsOneWidget);
      expect(
        tester
            .getSemantics(confirmation)
            .getSemanticsData()
            .flagsCollection
            .isLiveRegion,
        isTrue,
      );
      expect(apply, findsNothing);
      expect(
        sections.inSheet(find.text(en('resetBookSettings'))),
        findsNothing,
      );
      expect(
        sections.inSheet(find.text(en('bookSettingsActive'))),
        findsNothing,
      );

      // A new choice for this book: its rows come back, the confirmation
      // is past.
      await sections.tapChip(tester, 'turnNone');
      expect(store.bookSettingsFor(key)!.turnStyle, LibraryPageTurnStyle.none);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.slide);
      expect(apply, findsOneWidget);
      expect(confirmation, findsNothing);
      await sections.closeAll(tester, store);
      semantics.dispose();
    });

    testWidgets('(b, d) a content hint that differs from the book\'s '
        'direction: the direction stays with the book, the rest becomes '
        'general; the book still reads in the user\'s direction', (
      tester,
    ) async {
      useSurface(tester, size: sections.tall);
      final (store, _) = await createStore(tester);
      const key = 'online:source:hinted';
      const other = 'local:other-hinted';
      // The general direction, overwritten by the book's.
      store.updateSettings(
        store.settings.copyWith(pageDirection: LibraryPageDirection.rtl),
      );
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.ltr,
          turnStyle: LibraryPageTurnStyle.slide,
          doublePage: LibraryDoublePageMode.never,
        ),
      );
      store.updateBookSettings(
        other,
        const LibraryReaderBookSettings(firstPageAlone: false),
      );
      final kept = store.bookSettingsFor(other);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          // A manga: right to left in automatic mode.
          content: FakePageContent(
            progressKey: key,
            layoutHint: LibraryPageLayoutHint.rightToLeft,
          ),
          store: store,
        ),
      );
      final state = pageState(tester);
      expect(state.controller.rightToLeft, isFalse);
      final shown = state.controller.effective;
      await sections.openSettings(tester, state.gamepadBindings.start!);
      await tester.tap(
        sections.inSheet(find.text(en('applyNavigationToAllBooks'))),
      );
      await tester.pump();
      expect(store.settings.pageDirection, LibraryPageDirection.ltr);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.slide);
      expect(store.settings.doublePage, LibraryDoublePageMode.never);
      // Cleared, the direction would be the hint's: it stays.
      expect(
        store.bookSettingsFor(key),
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.ltr,
        ),
      );
      expect(store.bookSettingsFor(other), kept);
      expect(state.controller.effective, shown);
      expect(state.controller.rightToLeft, isFalse);
      // Confirmed; the book keeps a choice of its own (note, Revert), and
      // nothing is left to apply.
      expect(
        sections.inSheet(find.text(en('navigationAppliedToAllBooks'))),
        findsOneWidget,
      );
      expect(
        sections.inSheet(find.text(en('bookSettingsActive'))),
        findsOneWidget,
      );
      expect(
        sections.inSheet(find.text(en('applyNavigationToAllBooks'))),
        findsNothing,
      );
      // Reverting: the hint decides again, the confirmation is past.
      await tester.tap(sections.inSheet(find.text(en('resetBookSettings'))));
      await tester.pump();
      expect(store.bookSettingsFor(key), isNull);
      expect(state.controller.rightToLeft, isTrue);
      expect(
        sections.inSheet(find.text(en('navigationAppliedToAllBooks'))),
        findsNothing,
      );
      await sections.closeAll(tester, store);
    });

    testWidgets('(b) only a direction the hint would decide otherwise stays; '
        'the book never changes', (tester) async {
      useSurface(tester, size: sections.tall);
      for (final (index, (mode, direction, expectKept))
          in <(LibraryMangaMode?, LibraryPageDirection, bool)>[
            // Automatic mode, the hint says right to left.
            (null, LibraryPageDirection.ltr, true),
            (null, LibraryPageDirection.rtl, false),
            // Paged chosen for the book: the hint does not apply.
            (LibraryMangaMode.paged, LibraryPageDirection.ltr, false),
          ].indexed) {
        final (store, _) = await createStore(tester);
        final key = 'online:source:rule-$index';
        store.updateBookSettings(
          key,
          LibraryReaderBookSettings(
            mangaMode: mode,
            pageDirection: direction,
            turnStyle: LibraryPageTurnStyle.none,
          ),
        );
        await pumpReader(
          tester,
          LibraryPageReaderScreen(
            content: FakePageContent(
              progressKey: key,
              layoutHint: LibraryPageLayoutHint.rightToLeft,
            ),
            store: store,
          ),
        );
        final state = pageState(tester);
        final shown = state.controller.effective;
        await sections.openSettings(tester, state.gamepadBindings.start!);
        await tester.tap(
          sections.inSheet(find.text(en('applyNavigationToAllBooks'))),
        );
        await tester.pump();
        expect(store.settings.pageDirection, direction, reason: '$index');
        expect(store.settings.turnStyle, LibraryPageTurnStyle.none);
        expect(store.settings.mangaMode, mode ?? LibraryMangaMode.auto);
        expect(
          store.bookSettingsFor(key),
          expectKept
              ? LibraryReaderBookSettings(pageDirection: direction)
              : null,
          reason: '$index',
        );
        expect(state.controller.effective, shown, reason: '$index');
        await sections.closeAll(tester, store);
      }
    });

    testWidgets('(c, d) an EPUB whose page-progression-direction differs '
        'from its own direction: the direction stays with the book', (
      tester,
    ) async {
      useSurface(tester, size: sections.tall);
      final (store, _) = await createStore(tester);
      const key = 'local:apply-epub';
      const other = 'local:apply-epub-other';
      store.updateSettings(
        store.settings.copyWith(pageDirection: LibraryPageDirection.rtl),
      );
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.ltr,
          turnStyle: LibraryPageTurnStyle.none,
        ),
      );
      store.updateBookSettings(
        other,
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.always,
        ),
      );
      final kept = store.bookSettingsFor(other);
      final document = await epubWith(
        tester,
        chapter1: xhtml(
          '<h1>Un</h1>${List<String>.generate(30, (i) => '<p>Texte $i.</p>').join()}',
        ),
        rtl: true,
      );
      await book.openPages(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: key,
          title: 'Manga',
          store: store,
          // page-progression-direction="rtl", as the launcher passes it.
          rightToLeft: true,
        ),
      );
      final state = book.bookState(tester);
      bool reversed() => tester.widget<PageView>(find.byType(PageView)).reverse;
      // The user's left to right.
      expect(reversed(), isFalse);
      await sections.openSettings(tester, state.gamepadBindings.start!);
      await tester.tap(
        sections.inSheet(find.text(en('applyNavigationToAllBooks'))),
      );
      await tester.pump();
      await book.settlePages(tester);
      expect(store.settings.pageDirection, LibraryPageDirection.ltr);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.none);
      expect(
        store.bookSettingsFor(key),
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.ltr,
        ),
      );
      expect(store.bookSettingsFor(other), kept);
      expect(reversed(), isFalse);
      expect(
        sections.inSheet(find.text(en('navigationAppliedToAllBooks'))),
        findsOneWidget,
      );
      // An EPUB read in its own direction keeps nothing.
      await tester.tap(sections.inSheet(find.text(en('resetBookSettings'))));
      await tester.pump();
      await book.settlePages(tester);
      expect(reversed(), isTrue);
      await sections.tapChip(tester, 'turnSlide');
      await sections.tapChip(tester, 'directionRtl');
      await tester.tap(
        sections.inSheet(find.text(en('applyNavigationToAllBooks'))),
      );
      await tester.pump();
      await book.settlePages(tester);
      expect(store.bookSettingsFor(key), isNull);
      expect(store.settings.pageDirection, LibraryPageDirection.rtl);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.slide);
      expect(reversed(), isTrue);
      await book.closePages(tester, store);
    });

    testWidgets('offered only while the book has its own navigation: not for '
        'a new book, never for a PDF without progress key', (tester) async {
      pdf.mockPathProvider();
      useSurface(tester, size: sections.tall);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:fresh'),
          store: store,
        ),
      );
      await sections.openSettings(
        tester,
        pageState(tester).gamepadBindings.start!,
      );
      final apply = sections.inSheet(
        find.text(en('applyNavigationToAllBooks')),
      );
      expect(apply, findsNothing);
      await sections.tapChip(tester, 'turnSlide');
      expect(apply, findsOneWidget);
      await sections.closeAll(tester, store);

      final (keyless, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '/missing-apply.pdf',
          title: 'Download',
          store: keyless,
          openDocument: pdf.FakeOpener().call,
        ),
      );
      await pdf.rendered(tester);
      await sections.openSettings(
        tester,
        pdf.readerOf(tester).gamepadBindings.start!,
      );
      await sections.tapChip(tester, 'turnSlide');
      // Written globally: nothing to apply.
      expect(keyless.settings.turnStyle, LibraryPageTurnStyle.slide);
      expect(apply, findsNothing);
      expect(
        sections.inSheet(find.text(en('navigationAppliedToAllBooks'))),
        findsNothing,
      );
      await sections.closeAll(tester, keyless);
    });

    testWidgets('PDF: A on "Apply to all books" applies it', (tester) async {
      pdf.mockPathProvider();
      useSurface(tester, size: sections.tall);
      final (store, _) = await createStore(tester);
      const key = 'local:apply-pdf';
      store.updateBookSettings(
        key,
        const LibraryReaderBookSettings(
          doublePage: LibraryDoublePageMode.always,
        ),
      );
      await pumpReader(
        tester,
        LibraryPdfReaderScreen(
          filePath: '/missing-apply-pad.pdf',
          title: 'Manual',
          progressKey: key,
          store: store,
          openDocument: pdf.FakeOpener().call,
        ),
      );
      await pdf.rendered(tester);
      await sections.openSettings(
        tester,
        pdf.readerOf(tester).gamepadBindings.start!,
      );
      // Down to the last row ("Revert to general settings"), one up.
      for (var i = 0; i < 40; i++) {
        sections.sheetBindings(tester).down!();
      }
      sections.sheetBindings(tester).up!();
      await tester.pump();
      sections.sheetBindings(tester).select!();
      await tester.pump();
      expect(store.settings.doublePage, LibraryDoublePageMode.always);
      expect(store.bookSettingsFor(key), isNull);
      expect(
        sections.inSheet(find.text(en('navigationAppliedToAllBooks'))),
        findsOneWidget,
      );
      await sections.closeAll(tester, store);
    });

    for (final (language, locale) in <(String, Locale)>[
      ('fr', const Locale('fr')),
      ('zh_Hant', const Locale('zh', 'TW')),
    ]) {
      testWidgets('the row and its confirmation speak $locale', (tester) async {
        useSurface(tester, size: sections.tall);
        final (store, _) = await createStore(tester);
        const key = 'local:apply-language';
        store.updateBookSettings(
          key,
          const LibraryReaderBookSettings(turnStyle: LibraryPageTurnStyle.none),
        );
        await pumpReader(
          tester,
          LibraryPageReaderScreen(
            content: FakePageContent(progressKey: key),
            store: store,
          ),
          locale: locale,
        );
        pageState(tester).gamepadBindings.start!();
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 400));
        final row = sections.inSheet(
          find.text(tr(language, 'applyNavigationToAllBooks')),
        );
        expect(row, findsOneWidget);
        await tester.tap(row);
        await tester.pump();
        expect(
          sections.inSheet(
            find.text(tr(language, 'navigationAppliedToAllBooks')),
          ),
          findsOneWidget,
        );
        if (language == 'fr') {
          expect(
            tr('fr', 'navigationAppliedToAllBooks'),
            'Ces réglages de navigation s’appliquent maintenant à tous les '
            'livres qui n’ont pas les leurs.',
          );
          expect(
            tr('fr', 'applyNavigationToAllBooks'),
            'Appliquer à tous les livres',
          );
        } else {
          for (final key in <String>[
            'applyNavigationToAllBooks',
            'navigationAppliedToAllBooks',
          ]) {
            expect(tr('zh_Hant', key), isNot(tr('zh', key)), reason: key);
          }
        }
        await sections.closeAll(tester, store);
      });
    }
  });
}
