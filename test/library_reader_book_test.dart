import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_view.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_local_fixtures.dart';
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

/// 1000 paragraphs: five TXT sections of 200.
String sampleText() => List<String>.generate(
  1000,
  (i) => 'Paragraph $i ${List<String>.filled(40, 'word$i').join(' ')}',
).join('\n\n');

LibraryBookReaderScreenState bookState(WidgetTester tester) => tester
    .state<LibraryBookReaderScreenState>(find.byType(LibraryBookReaderScreen));

/// These tests exercise the 440 continuous scroll: since Build 447 the
/// default text layout is pages (test/library_reader_book_pages_test.dart).
void useScroll(LibraryReadingStore store) => store.updateSettings(
  store.settings.copyWith(textLayout: LibraryTextLayout.scroll),
);

Future<LibraryEpubDocument> openEpub(
  WidgetTester tester, {
  String? chapter1,
  String? chapter2,
}) async {
  return (await tester.runAsync(() async {
    final directory = await createTempDir('ns_reader_epub_');
    final file = await writeFile(
      directory,
      'book.epub',
      buildEpub3(chapter1: chapter1, chapter2: chapter2),
    );
    return LibraryEpubDocument.open(file.path);
  }))!;
}

Future<void> closeBook(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await settle(tester, rounds: 3);
  await flushStore(tester, store);
}

void main() {
  setUpReaderEnvironment();

  group('TXT', () {
    testWidgets('opens at the saved location', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:txt',
          location: 'txt:450:0',
          fraction: 0.45,
        ),
      );
      final document = LibraryTextDocument.fromText(sampleText());
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(document),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.currentPosition, const LibraryReflowPosition(2, 50, 0));
      // The chrome shows the reading percentage (by characters).
      final percent = (state.source!.fractionFor(state.currentPosition!) * 100)
          .round();
      expect(percent, inInclusiveRange(40, 50));
      expect(find.text('$percent%'), findsOneWidget);
      await closeBook(tester, store);
    });

    // Regression: any error while resolving the saved location opened the
    // book at its beginning and saved that over the real position 800 ms
    // later, even if the user closed the book at once.
    testWidgets('a location that fails to load is kept until the user moves', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:kept',
          location: 'txt:450:0',
          fraction: 0.45,
        ),
      );
      final source = _ResolveFailsSource(
        LibraryTextReflowSource(LibraryTextDocument.fromText(sampleText())),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => source,
          progressKey: 'local:kept',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(source.resolves, 1);
      expect(state.currentPosition, LibraryReflowPosition.start);
      // Said, with the raw detail.
      final snackBar = find.byType(SnackBar);
      expect(
        find.descendant(
          of: snackBar,
          matching: find.text(en('positionNotRestored')),
        ),
        findsWidgets,
      );
      expect(
        find.descendant(
          of: snackBar,
          matching: find.textContaining('worker exited'),
        ),
        findsWidgets,
      );
      // Longer than the save delay, then closed without moving.
      await tester.pump(const Duration(seconds: 2));
      expect(store.progressFor('local:kept')!.location, 'txt:450:0');
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      expect(store.progressFor('local:kept')!.location, 'txt:450:0');
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    testWidgets('after such a failure, reading on saves the new position', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:moved',
          location: 'txt:450:0',
          fraction: 0.45,
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => _ResolveFailsSource(
            LibraryTextReflowSource(LibraryTextDocument.fromText(sampleText())),
          ),
          progressKey: 'local:moved',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      state.gamepadBindings.right!();
      await frames(tester);
      final shown = state.currentPosition!;
      expect(shown.block, greaterThan(0));
      await tester.pump(const Duration(seconds: 1));
      expect(
        store.progressFor('local:moved')!.location,
        'txt:${shown.block}:${shown.offset}',
      );
      await closeBook(tester, store);
    });

    testWidgets('a location unknown to the book starts over and is replaced', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:unknown',
          location: 'epubcfi(/6/4[ch2]!/4/2:0)',
          fraction: 0.5,
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:unknown',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      expect(bookState(tester).currentPosition, LibraryReflowPosition.start);
      expect(find.text(en('positionNotRestored')), findsNothing);
      // Opening counts as reading: the start replaces it.
      await tester.pump(const Duration(seconds: 1));
      expect(store.progressFor('local:unknown')!.location, 'txt:0:0');
      await closeBook(tester, store);
    });

    testWidgets(
      'a font size change keeps the same block and words at the top',
      (tester) async {
        useSurface(tester);
        final (store, _) = await createStore(tester);
        useScroll(store);
        store.saveProgress(
          LibraryReadingProgress(
            key: 'local:txt',
            location: 'txt:450:120',
            fraction: 0.45,
          ),
        );
        await pumpReader(
          tester,
          LibraryBookReaderScreen(
            open: () async => LibraryTextReflowSource(
              LibraryTextDocument.fromText(sampleText()),
            ),
            progressKey: 'local:txt',
            title: 'Sample',
            store: store,
          ),
        );
        await settle(tester, rounds: 2);
        final state = bookState(tester);
        final opened = state.currentPosition!;
        expect(opened.chapter, 2);
        expect(opened.block, 50);
        // The line holding character 120 is at the top.
        expect(opened.offset, inInclusiveRange(60, 120));
        expect(opened.offset, greaterThan(0));

        store.updateSettings(store.settings.copyWith(fontSize: 28));
        await tester.pump();
        await tester.pump();
        final bigger = state.currentPosition!;
        expect(bigger.chapter, 2);
        expect(bigger.block, 50);
        expect(bigger.offset, inInclusiveRange(30, opened.offset));

        store.updateSettings(store.settings.copyWith(fontSize: 14, margin: 40));
        await tester.pump();
        await tester.pump();
        final smaller = state.currentPosition!;
        expect(smaller.block, 50);
        expect(smaller.offset, lessThanOrEqualTo(bigger.offset));
        await closeBook(tester, store);
      },
    );

    // Regression: the position was read from the layout of the frame before
    // the jump to the saved line, so it fell back to the start of the
    // paragraph and that was saved (each opening moved the reader back).
    testWidgets('opening and closing keeps the saved offset inside a block', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:txt',
          location: 'txt:450:120',
          fraction: 0.45,
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final shown = bookState(tester).currentPosition!;
      expect(shown.block, 50);
      expect(shown.offset, greaterThan(0));
      await tester.pumpWidget(const SizedBox.shrink());
      await settle(tester, rounds: 2);
      final saved = store.progressFor('local:txt')!.location;
      final offset = int.parse(saved.split(':').last);
      expect(saved, startsWith('txt:450:'));
      // The line holding character 120 (never the start of the paragraph).
      expect(offset, inInclusiveRange(shown.offset, 120));
      await flushStore(tester, store);
    });

    // A slider drag changes the size again before the previous jump is laid
    // out: the position must not fall back to the start of the paragraph.
    testWidgets('quick successive font size changes keep the same words', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:txt',
          location: 'txt:450:120',
          fraction: 0.45,
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      for (final size in <double>[20, 22, 24, 26]) {
        store.updateSettings(store.settings.copyWith(fontSize: size));
        // One frame: the new layout and the jump to the line, not yet the
        // layout of that jump.
        await tester.pump();
      }
      await tester.pump();
      await tester.pump();
      final position = state.currentPosition!;
      expect(position.block, 50);
      expect(position.offset, inInclusiveRange(40, 120));
      await closeBook(tester, store);
    });

    testWidgets('a rotation keeps the reading position', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      store.saveProgress(
        LibraryReadingProgress(
          key: 'local:txt',
          location: 'txt:610:0',
          fraction: 0.6,
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      tester.view.physicalSize = const Size(400, 860);
      await tester.pump();
      await tester.pump();
      final state = bookState(tester);
      expect(state.currentPosition, const LibraryReflowPosition(3, 10, 0));
      await closeBook(tester, store);
    });

    testWidgets('a theme change repaints the page in its colours', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:txt',
          title: 'Sample',
          store: store,
        ),
      );
      Color background() => tester
          .widget<Scaffold>(
            find
                .descendant(
                  of: find.byType(LibraryBookReaderScreen),
                  matching: find.byType(Scaffold),
                )
                .first,
          )
          .backgroundColor!;
      store.updateSettings(
        store.settings.copyWith(theme: LibraryReaderTheme.sepia),
      );
      await tester.pump();
      expect(background(), LibraryReaderPalette.sepia.background);
      store.updateSettings(
        store.settings.copyWith(theme: LibraryReaderTheme.black),
      );
      await tester.pump();
      expect(background(), LibraryReaderPalette.black.background);
      await closeBook(tester, store);
    });

    testWidgets('scrolling is saved as a txt location when the reader closes', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:saved',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      for (var i = 0; i < 4; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      // Bumpers move by sections (TXT chapters).
      state.gamepadBindings.rightBumper!();
      await tester.pump();
      await tester.pump();
      expect(state.currentPosition!.chapter, 1);
      final position = state.currentPosition!;
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      final saved = store.progressFor('local:saved')!;
      expect(saved.location, 'txt:${200 + position.block}:${position.offset}');
      expect(saved.fraction, greaterThan(0.15));
      expect(saved.title, 'Sample');
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    // Regression (Build 437 end-to-end journey): the end of a page turn is
    // notified by the animation tick, before the frame lays out the final
    // offset. The position was read from the previous layout, so closing
    // the reader right after paging saved the page before the last turn.
    testWidgets('the last page turn is the position saved on close', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:turns',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      final shown = <LibraryReflowPosition>[];
      for (var i = 0; i < 3; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
        shown.add(state.currentPosition!);
      }
      expect(shown.map((p) => p.block).toSet(), hasLength(3));
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      final last = shown.last;
      expect(
        store.progressFor('local:turns')!.location,
        'txt:${200 * last.chapter + last.block}:${last.offset}',
      );
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    testWidgets('a jump to a chapter that fails to load says so', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => _FailingChapterSource(
            LibraryTextReflowSource(LibraryTextDocument.fromText(sampleText())),
            failing: 3,
          ),
          progressKey: 'local:fail',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.currentPosition!.chapter, 0);
      // The percentage slider jumps far from the chapters on screen.
      final slider = tester.widget<Slider>(find.byType(Slider));
      slider.onChangeStart!(0.7);
      slider.onChangeEnd!(0.7);
      await tester.pump();
      await tester.pump();
      // A message says why nothing moved: translated text and raw detail
      // (the app's messenger shows it in every Scaffold it serves).
      final snackBar = find.byType(SnackBar);
      expect(snackBar, findsWidgets);
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
      expect(state.currentPosition!.chapter, 0);
      await closeBook(tester, store);
    });

    testWidgets('A on the controller retries a book that failed to open', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      var attempts = 0;
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async {
            attempts++;
            if (attempts == 1) {
              throw StateError('worker exited');
            }
            return LibraryTextReflowSource(
              LibraryTextDocument.fromText(sampleText()),
            );
          },
          progressKey: 'local:retry',
          title: 'Sample',
          store: store,
        ),
      );
      await tester.pump();
      expect(find.text(en('errorWorker')), findsOneWidget);
      final state = bookState(tester);
      state.gamepadBindings.select!();
      await settle(tester, rounds: 2);
      expect(attempts, 2);
      expect(find.text(en('errorWorker')), findsNothing);
      expect(state.currentPosition, LibraryReflowPosition.start);
      await closeBook(tester, store);
    });

    // Regression: landscape came back only in dispose, after the reverse
    // transition (the screen below was shown in portrait first).
    testWidgets('landscape is restored as soon as the reader is popped', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final platform = RecordingOrientationPlatform();
      final orientation = LibraryReaderOrientation(
        platform: platform,
        isIOS: true,
      );
      final navigator = await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:rotation',
          title: 'Sample',
          store: store,
          orientation: orientation,
        ),
      );
      await settle(tester, rounds: 2);
      await expectLandscapeWhenPopStarts(
        tester,
        navigator,
        platform,
        orientation,
        LibraryBookReaderScreen,
      );
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    // Regression: closing within the save delay saved from dispose, so the
    // store notified the screens below while the widget tree was locked.
    testWidgets('a pop right after scrolling saves at once, then freezes', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final navigator = await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:quick',
          title: 'Sample',
          store: store,
        ),
        home: StoreWatcher(store: store, progressKey: 'local:quick'),
      );
      await settle(tester, rounds: 2);
      // The opening is saved after the delay.
      await tester.pump(const Duration(seconds: 1));
      final state = bookState(tester);
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      final shown = state.currentPosition!;
      expect(shown.block, greaterThan(0));
      final location = 'txt:${shown.block}:${shown.offset}';
      // Within the 800 ms save delay (the iOS back swipe pops directly).
      navigator.currentState!.pop();
      expect(store.progressFor('local:quick')!.location, location);
      await tester.pump();
      // Rotated back to landscape while it leaves: the text is laid out
      // again, the saved position does not move.
      tester.view.physicalSize = const Size(600, 900);
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      expect(tester.takeException(), isNull);
      expect(store.progressFor('local:quick')!.location, location);
      expect(find.text('home $location'), findsOneWidget);
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    // Regression: with VoiceOver the bars hid after 4 s, taking their
    // controls out of the accessibility tree.
    testWidgets('with VoiceOver the chrome does not hide by itself', (
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
      useScroll(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:voiceover',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.chromeVisible, isTrue);
      await tester.pump(const Duration(seconds: 5));
      expect(state.chromeVisible, isTrue);
      final settings = find.semantics.byLabel(en('settings'));
      expect(settings, findsOne);
      expect(
        settings.evaluate().single.getSemanticsData().hasAction(
          SemanticsAction.tap,
        ),
        isTrue,
      );
      // The user can still hide the bars explicitly.
      state.gamepadBindings.select!();
      await tester.pump();
      expect(state.chromeVisible, isFalse);
      await closeBook(tester, store);
      semantics.dispose();
    });

    testWidgets('tap zones page down and up; the centre toggles the chrome', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryTextReflowSource(
            LibraryTextDocument.fromText(sampleText()),
          ),
          progressKey: 'local:taps',
          title: 'Sample',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.currentPosition!.block, 0);
      await tester.tapAt(const Offset(860, 300));
      await frames(tester);
      await settle(tester, rounds: 1);
      final down = state.currentPosition!;
      expect(down.block, greaterThan(1));
      expect(state.chromeVisible, isFalse);
      await tester.tapAt(const Offset(40, 300));
      await frames(tester);
      await settle(tester, rounds: 1);
      expect(state.currentPosition!.block, lessThan(down.block));
      await tester.tapAt(const Offset(450, 300));
      await tester.pump();
      expect(state.chromeVisible, isTrue);
      await closeBook(tester, store);
    });
  });

  group('EPUB', () {
    testWidgets('opens at a saved CFI', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final document = await openEpub(tester);
      final cfi = (await tester.runAsync(() => document.cfiFor(1, 1, 3)))!;
      store.saveProgress(
        LibraryReadingProgress(key: 'local:epub', location: cfi, fraction: 0.7),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:epub',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      await settle(tester);
      final state = bookState(tester);
      final position = state.currentPosition!;
      expect(position.chapter, 1);
      expect(position.block, 1);
      await closeBook(tester, store);
    });

    testWidgets('paging down then closing saves a CFI of the last page shown', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final document = await openEpub(
        tester,
        chapter1: xhtml(
          List<String>.generate(
            200,
            (i) =>
                '<p>Paragraph $i ${List<String>.filled(28, 'w$i').join(' ')}</p>',
          ).join(),
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:epub-turns',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      await settle(tester);
      final state = bookState(tester);
      for (var i = 0; i < 4; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      final shown = state.currentPosition!;
      expect(shown.chapter, 0);
      expect(shown.block, greaterThan(8));
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      await settle(tester, rounds: 2);
      final saved = store.progressFor('local:epub-turns')!.location;
      // The reader closed its document: the CFI is resolved by a new one.
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
      await flushStore(tester, store);
    });

    testWidgets('the table of contents navigates, the position is a CFI', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final document = await openEpub(tester);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:toc',
          title: 'Le Petit Livre',
          store: store,
        ),
      );
      await settle(tester);
      final state = bookState(tester);
      expect(state.currentPosition!.chapter, 0);

      await tester.tap(find.byTooltip(en('tableOfContents')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text('Part Two'), findsOneWidget);
      await tester.tap(find.text('Chapter Two').last);
      await tester.pump();
      await settle(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(state.currentPosition!.chapter, 1);

      await tester.pumpWidget(const SizedBox.shrink());
      await settle(tester, rounds: 3);
      final saved = store.progressFor('local:toc')!;
      expect(saved.location, startsWith('epubcfi(/6/4[ch2]!'));
      expect(saved.chapterTitle, 'Chapter Two');
      await flushStore(tester, store);
    });

    testWidgets('links: internal ones navigate, only https opens after asking', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final document = await openEpub(
        tester,
        chapter2: xhtml(
          '<h2>Chapter Two</h2><p>Go <a href="https://example.org/a">website</a> '
          'or <a href="http://example.org/b">unencrypted</a> '
          'or <a href="ch1.xhtml#part2">earlier</a>.</p>',
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
      await pumpReader(
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
      await settle(tester);
      final state = bookState(tester);
      expect(state.currentPosition!.chapter, 1);

      await tester.tapOnText(find.textRange.ofSubstring('unencrypted'));
      await tester.pump();
      expect(find.text(en('linkNotSecure')), findsWidgets);
      expect(launched, isEmpty);

      await tester.tapOnText(find.textRange.ofSubstring('website'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.text(en('openLinkTitle')), findsOneWidget);
      expect(find.text('https://example.org/a'), findsOneWidget);
      await tester.tap(find.text(en('openLink')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(launched, <Uri>[Uri.parse('https://example.org/a')]);

      await tester.tapOnText(find.textRange.ofSubstring('earlier'));
      await tester.pump();
      await settle(tester);
      expect(state.currentPosition, const LibraryReflowPosition(0, 2, 0));
      await closeBook(tester, store);
    });

    // Regression: a rebuilt image unit showed a placeholder of half the width
    // for a frame, then the image: scrolling back up over an illustration
    // pushed the text being read down by the difference.
    testWidgets('an image built again has its final height at once', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final paragraphs = List<String>.generate(
        80,
        (i) =>
            '<p>Paragraph $i ${List<String>.filled(30, 'text').join(' ')}</p>',
      ).join();
      final document = await openEpub(
        tester,
        chapter1: xhtml(
          '<h1>Chapter One</h1><p><img src="../images/cover%20art.png" '
          'alt="Cover"/></p>$paragraphs',
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:image',
          title: 'Pictures',
          store: store,
        ),
      );
      await settle(tester);
      final image = find.byWidgetPredicate(
        (widget) =>
            widget is LibraryReflowUnitView &&
            widget.unit.source.kind == LibraryTextBlockKind.image,
      );
      expect(image, findsOneWidget);
      final height = tester.getSize(image).height;
      // 40 x 60 picture: 1.5 x the text width, capped at 85 % of the screen.
      expect(height, greaterThan(400));
      final picture = tester.widget<RawImage>(
        find.descendant(of: image, matching: find.byType(RawImage)),
      );
      expect(picture.image, isNotNull);
      expect(picture.image!.height / picture.image!.width, closeTo(1.5, 0.01));
      expect(find.bySemanticsLabel('Cover'), findsOneWidget);

      final scrollable = tester.state<ScrollableState>(
        find.byType(Scrollable).last,
      );
      final top = scrollable.position.pixels;
      // Far enough for the image unit to be disposed, then back above it.
      scrollable.position.jumpTo(top + 4000);
      await tester.pump();
      await tester.pump();
      expect(image, findsNothing);
      scrollable.position.jumpTo(top + 200);
      await tester.pump();
      expect(image, findsOneWidget);
      expect(tester.getSize(image).height, height);
      await closeBook(tester, store);
    });

    testWidgets('a missing image is announced as unavailable', (tester) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      final document = await openEpub(
        tester,
        chapter1: xhtml(
          '<h1>Chapter One</h1><p><img src="../images/missing.png"/></p>'
          '<p>After the picture.</p>',
        ),
      );
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => LibraryEpubReflowSource(document),
          progressKey: 'local:missing',
          title: 'Pictures',
          store: store,
        ),
      );
      await settle(tester);
      expect(find.bySemanticsLabel(en('imageUnavailable')), findsOneWidget);
      expect(find.byIcon(Icons.image_not_supported_outlined), findsOneWidget);
      expect(
        find.text('After the picture.', findRichText: true),
        findsOneWidget,
      );
      await closeBook(tester, store);
    });

    testWidgets('a damaged book shows a translated error with its detail', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async => throw const LibraryBookException(
            LibraryBookIssue.drmProtected,
            detail: 'META-INF/encryption.xml',
          ),
          progressKey: 'local:drm',
          title: 'Locked',
          store: store,
        ),
        locale: const Locale('de'),
      );
      await tester.pump();
      expect(
        find.text(LibraryReaderLocale.values['de']!['issueDrmProtected']!),
        findsOneWidget,
      );
      await tester.tap(
        find.text(LibraryReaderLocale.values['de']!['technicalDetails']!),
      );
      await tester.pump();
      expect(find.textContaining('META-INF/encryption.xml'), findsOneWidget);
      await closeBook(tester, store);
    });
  });

  group('memory over a long session', () {
    // Regression: the EPUB source and the reader kept every chapter ever
    // loaded until the book closed, bypassing the document's 6-chapter
    // cache, and the reader's window of chapters only grew.
    testWidgets('the EPUB source keeps only the chapters it used last', (
      tester,
    ) async {
      final document = (await tester.runAsync(() async {
        final directory = await createTempDir('ns_reader_epub_long_');
        final file = await writeFile(
          directory,
          'long.epub',
          _epubWithChapters(10),
        );
        return LibraryEpubDocument.open(file.path);
      }))!;
      final source = LibraryEpubReflowSource(document);
      await tester.runAsync(() async {
        for (var chapter = 0; chapter < 10; chapter++) {
          await source.loadChapter(chapter);
        }
      });
      expect(source.heldChapters, <int>[7, 8, 9]);
      // Dropped by the source and by the document's own cache.
      expect(source.loadedChapter(0), isNull);
      expect(source.loadedChapter(9), isNotNull);
      expect(
        source.locationFor(const LibraryReflowPosition(9, 1, 0)),
        startsWith('epubcfi(/6/20[c9]!'),
      );
      // A chapter that left both caches is loaded again on demand.
      await tester.runAsync(() => source.loadChapter(0));
      expect(source.loadedChapter(0), isNotNull);
      expect(source.heldChapters, <int>[8, 9, 0]);
      await tester.runAsync(source.close);
    });

    testWidgets('reading on keeps only the chapters around the one read', (
      tester,
    ) async {
      useSurface(tester);
      final (store, _) = await createStore(tester);
      useScroll(store);
      // 20 sections of 200 short paragraphs.
      final text = List<String>.generate(4000, (i) => 'Line $i').join('\n\n');
      await pumpReader(
        tester,
        LibraryBookReaderScreen(
          open: () async =>
              LibraryTextReflowSource(LibraryTextDocument.fromText(text)),
          progressKey: 'local:long',
          title: 'Long',
          store: store,
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      ScrollPosition scroll() =>
          tester.state<ScrollableState>(find.byType(Scrollable).last).position;
      Offset topOf(LibraryReflowPosition p) => tester.getTopLeft(
        find.byKey(ValueKey<String>('u-${p.chapter}-${p.block}')),
      );
      var previous = state.currentPosition!;
      var largest = 0;
      var recentred = false;
      for (var step = 0; step < 300 && previous.chapter < 8; step++) {
        final position = scroll();
        position.jumpTo(
          math.min(
            position.pixels + position.viewportDimension * 2,
            position.maxScrollExtent,
          ),
        );
        await tester.pump();
        final reading = state.currentPosition!;
        final before = topOf(reading);
        final windowBefore = state.window;
        // The window is cut back once the reader is idle.
        await tester.pump(const Duration(milliseconds: 400));
        await tester.pump();
        await tester.pump();
        // Nothing moved on screen, and the reading position is the same.
        expect(
          topOf(reading).dy,
          closeTo(before.dy, 0.01),
          reason: 'step $step',
        );
        expect(state.currentPosition, reading, reason: 'step $step');
        // The view was built around chapter 0 (where the book opened):
        // dropping it rebuilt the view around the unit being read.
        if (windowBefore.$1 == 0 && state.window.$1 > 0) recentred = true;
        expect(
          reading.chapter * 1000 + reading.block,
          greaterThanOrEqualTo(previous.chapter * 1000 + previous.block),
        );
        previous = reading;
        final (start, end) = state.window;
        largest = math.max(largest, state.chaptersInMemory.length);
        expect(
          state.chaptersInMemory,
          everyElement(inInclusiveRange(start - 1, end + 1)),
        );
      }
      expect(previous.chapter, greaterThanOrEqualTo(8));
      expect(recentred, isTrue);
      final (start, end) = state.window;
      expect(end - start + 1, lessThanOrEqualTo(3));
      // At most the window (cut back above 3 chapters) and one chapter on
      // each side, never the 9 chapters read.
      expect(largest, lessThanOrEqualTo(6));
      expect(
        state.chaptersInMemory,
        everyElement(
          inInclusiveRange(previous.chapter - 3, previous.chapter + 3),
        ),
      );
      // The position read last is the one saved.
      state.gamepadBindings.back!();
      await frames(tester);
      await tester.pump(const Duration(milliseconds: 400));
      expect(
        store.progressFor('local:long')!.location,
        'txt:${previous.chapter * 200 + previous.block}:${previous.offset}',
      );
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });
  });

  test('the sample text really has five sections', () {
    final document = LibraryTextDocument.fromText(sampleText());
    expect(document.blocks.length, 1000);
    expect(document.sectionCount, 5);
    expect(Platform.pathSeparator, isNotEmpty);
  });
}

/// EPUB 3 with [count] spine documents `c0` to `c{count-1}`.
Uint8List _epubWithChapters(int count) {
  final opf =
      '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:long</dc:identifier>
    <dc:title>Long</dc:title>
    <dc:language>en</dc:language>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
${[for (var i = 0; i < count; i++) '    <item id="c$i" href="c$i.xhtml" media-type="application/xhtml+xml"/>'].join('\n')}
  </manifest>
  <spine>
${[for (var i = 0; i < count; i++) '    <itemref idref="c$i"/>'].join('\n')}
  </spine>
</package>''';
  return buildZip(<FixtureZipEntry>[
    FixtureZipEntry.text('mimetype', 'application/epub+zip', deflate: false),
    FixtureZipEntry.text('META-INF/container.xml', containerXml),
    FixtureZipEntry.text('OEBPS/content.opf', opf),
    FixtureZipEntry.text(
      'OEBPS/nav.xhtml',
      xhtml(
        '<nav epub:type="toc"><ol><li><a href="c0.xhtml">Start</a></li></ol></nav>',
      ),
    ),
    for (var i = 0; i < count; i++)
      FixtureZipEntry.text(
        'OEBPS/c$i.xhtml',
        xhtml('<h1>Chapter $i</h1><p>Text of chapter $i.</p>'),
      ),
  ]);
}

/// A TXT source whose saved locations cannot be resolved for now (the
/// worker stopped).
class _ResolveFailsSource extends _FailingChapterSource {
  _ResolveFailsSource(super.inner) : super(failing: -1);

  int resolves = 0;

  @override
  Future<LibraryReflowPosition?> resolveLocation(String location) {
    resolves++;
    return Future<LibraryReflowPosition?>.error(
      StateError('library-epub worker exited'),
    );
  }
}

/// A TXT source whose chapter [failing] cannot be loaded.
class _FailingChapterSource implements LibraryReflowSource {
  _FailingChapterSource(this._inner, {required this.failing});

  final LibraryTextReflowSource _inner;
  final int failing;

  @override
  int get chapterCount => _inner.chapterCount;

  @override
  bool get separatesChapters => _inner.separatesChapters;

  @override
  List<LibraryReflowTocEntry> get toc => _inner.toc;

  @override
  Future<List<LibraryTextBlock>> loadChapter(int chapter) => chapter == failing
      ? Future<List<LibraryTextBlock>>.error(
          LibraryBookException(
            LibraryBookIssue.tooLarge,
            detail: 'chapter $chapter refused',
          ),
        )
      : _inner.loadChapter(chapter);

  @override
  List<LibraryTextBlock>? loadedChapter(int chapter) =>
      chapter == failing ? null : _inner.loadedChapter(chapter);

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
