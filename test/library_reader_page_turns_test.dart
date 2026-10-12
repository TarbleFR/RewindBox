// Page turns of the page reader (docs/library-books-3d-plan.md § 3.4,
// § 3.10, § 3.12): the curl layer above the kept PageView (enabled in the
// curl style only, never zoomed, never vertical, never with Reduce Motion),
// drags that complete or cancel a curl, the d-pad and the tap zones turning
// through it (a press during a turn never turns a second page), turns
// without animation, the 440 slide, the chapter cards that still slide, and
// the curl drawing the reader's own decoded pages.
import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_source.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_local_fixtures.dart';
import 'library_reader_test_support.dart';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

/// A portrait surface: one page per screen (two-page spreads are automatic
/// in landscape only).
const Size portrait = Size(600, 900);

LibraryPageReaderScreenState readerState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

LibraryPageCurlLayer curlLayer(WidgetTester tester) =>
    tester.widget<LibraryPageCurlLayer>(find.byType(LibraryPageCurlLayer));

/// Position of the PageView (item index, fractional while it moves).
double viewPage(WidgetTester tester) =>
    tester.widget<PageView>(find.byType(PageView)).controller!.page!;

/// A store that records the page of every progress saved.
class RecordingStore extends LibraryReadingStore {
  RecordingStore(Directory directory)
    : super(directory: directory, saveDelay: const Duration(milliseconds: 5));

  final List<int?> saved = <int?>[];

  @override
  void saveProgress(
    LibraryReadingProgress progress, {
    bool keepTimestamp = false,
  }) {
    saved.add(progress.pageIndex);
    super.saveProgress(progress, keepTimestamp: keepTimestamp);
  }
}

Future<RecordingStore> createRecordingStore(WidgetTester tester) async {
  final directory = (await tester.runAsync(
    () => createTempDir('ns_reader_turns_'),
  ))!;
  final store = RecordingStore(directory);
  await tester.runAsync(store.load);
  return store;
}

Future<void> closeAll(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await flushStore(tester, store);
}

/// Lets the curl render the pages around the current one (real decoding).
Future<void> waitForTextures(
  WidgetTester tester,
  LibraryPageReaderScreenState state, {
  int count = 2,
}) async {
  for (var i = 0; i < 30 && state.textures.textures < count; i++) {
    await settle(tester, rounds: 1);
  }
  expect(state.textures.textures, greaterThanOrEqualTo(count));
}

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

/// Lets the pages around the current one decode until the curl can turn in
/// [direction] (a page still loading is never curled).
Future<void> waitForCurl(
  WidgetTester tester,
  LibraryPageReaderScreenState state, [
  LibraryPageTurnDirection direction = LibraryPageTurnDirection.forward,
]) => waitUntil(
  tester,
  () => state.curl.canTurn(direction),
  reason: 'the pages decode',
);

/// Drags slowly (well under 600 px/s) by [dx] from [from], holding the
/// finger down.
Future<TestGesture> slowDrag(
  WidgetTester tester,
  Offset from,
  double dx, {
  int steps = 10,
}) async {
  final gesture = await tester.startGesture(from);
  for (var i = 0; i < steps; i++) {
    await gesture.moveBy(Offset(dx / steps, 0));
    await tester.pump(const Duration(milliseconds: 60));
  }
  return gesture;
}

/// Runs a curl animation to its end, then the frame that removes it.
Future<void> finish(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pump();
}

/// Double-taps the middle of the surface (zoom toggle).
Future<void> doubleTapCentre(WidgetTester tester, Size size) async {
  final centre = Offset(size.width / 2, size.height / 2);
  await tester.tapAt(centre);
  await tester.pump(const Duration(milliseconds: 50));
  await tester.tapAt(centre + const Offset(2, 2));
  await frames(tester);
}

void main() {
  setUpReaderEnvironment();
  // The curl draws with its painter (the shader has its own tests).
  setUp(() {
    LibraryPageCurlProgram.resetForTesting();
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('curl enabled', () {
    testWidgets('in the curl style only, never zoomed, never vertical, never '
        'with Reduce Motion', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:matrix'),
          store: store,
        ),
      );
      final state = readerState(tester);
      // The new default.
      expect(store.settings.turnStyle, LibraryPageTurnStyle.curl);
      expect(curlLayer(tester).enabled, isTrue);
      // Decoded pages are curled; after a turn the textures of the pages
      // around the new one are rendered.
      await waitForCurl(tester, state);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      await finish(tester);
      expect(state.controller.page, 1);
      await waitForTextures(tester, state);
      // The PageView stays under it, with its own physics.
      expect(find.byType(PageView), findsOneWidget);
      expect(
        tester.widget<PageView>(find.byType(PageView)).physics,
        isA<PageScrollPhysics>(),
      );

      for (final (style, enabled) in <(LibraryPageTurnStyle, bool)>[
        (LibraryPageTurnStyle.slide, false),
        (LibraryPageTurnStyle.none, false),
        (LibraryPageTurnStyle.curl, true),
      ]) {
        store.updateSettings(store.settings.copyWith(turnStyle: style));
        await tester.pump();
        expect(curlLayer(tester).enabled, enabled, reason: style.name);
        expect(state.controller.turnStyle, style);
        // Without the curl, its textures are released; with it, rendered
        // again.
        if (enabled) {
          await waitForTextures(tester, state);
        } else {
          expect(state.textures.textures, 0, reason: style.name);
        }
      }

      // Zoomed: the pan belongs to the page.
      await doubleTapCentre(tester, portrait);
      expect(state.zoomed, isTrue);
      expect(curlLayer(tester).enabled, isFalse);
      expect(state.textures.textures, 0);
      await doubleTapCentre(tester, portrait);
      expect(state.zoomed, isFalse);
      expect(curlLayer(tester).enabled, isTrue);
      await waitForTextures(tester, state);

      // Vertical strip: no curl at all.
      state.controller.toggleMode();
      await frames(tester);
      expect(find.byType(ListView), findsOneWidget);
      expect(find.byType(LibraryPageCurlLayer), findsNothing);
      expect(state.textures.textures, 0);
      state.controller.toggleMode();
      await frames(tester);
      expect(curlLayer(tester).enabled, isTrue);

      // Reduce Motion: no animated turn, for this session only.
      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      await tester.pump();
      expect(curlLayer(tester).enabled, isFalse);
      expect(state.controller.turnStyle, LibraryPageTurnStyle.none);
      expect(store.settings.turnStyle, LibraryPageTurnStyle.curl);
      tester.platformDispatcher.clearAccessibilityFeaturesTestValue();
      await tester.pump();
      expect(curlLayer(tester).enabled, isTrue);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });
  });

  group('drags', () {
    testWidgets('a drag past 30 % curls to the next page, which is saved '
        'exactly once', (tester) async {
      useSurface(tester, size: portrait);
      final store = await createRecordingStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:drag'),
          store: store,
        ),
      );
      final state = readerState(tester);
      await waitForCurl(tester, state);
      // The opening position is saved after the reader's delay.
      await tester.pump(const Duration(seconds: 1));
      expect(store.saved, <int?>[0]);
      store.saved.clear();

      final gesture = await slowDrag(tester, const Offset(560, 450), -300);
      expect(state.curl.isDragging, isTrue);
      expect(state.curl.direction, LibraryPageTurnDirection.forward);
      expect(state.curl.progress, closeTo(0.5, 0.05));
      expect(find.byType(LibraryPageCurl), findsOneWidget);
      // The curl holds the page: the PageView did not move.
      expect(viewPage(tester), 0);
      expect(state.controller.page, 0);
      await gesture.up();
      await finish(tester);
      expect(state.controller.page, 1);
      expect(viewPage(tester), 1.0);
      expect(state.curl.isActive, isFalse);
      expect(find.byType(LibraryPageCurl), findsNothing);
      // One turn, one save.
      await tester.pump(const Duration(seconds: 1));
      expect(store.saved, <int?>[1]);
      expect(store.progressFor('local:drag')!.location, 'page:1');
      await frames(tester);
      expect(viewPage(tester), 1.0);
      expect(store.saved, <int?>[1]);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });

    testWidgets('a short drag returns the page: nothing turns, nothing is '
        'saved', (tester) async {
      useSurface(tester, size: portrait);
      final store = await createRecordingStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:cancel'),
          store: store,
        ),
      );
      final state = readerState(tester);
      await waitForCurl(tester, state);
      await tester.pump(const Duration(seconds: 1));
      store.saved.clear();

      final gesture = await slowDrag(tester, const Offset(560, 450), -90);
      expect(state.curl.isDragging, isTrue);
      expect(state.curl.progress, closeTo(0.15, 0.03));
      await tester.pump(const Duration(milliseconds: 200));
      await gesture.up();
      await finish(tester);
      expect(state.curl.isActive, isFalse);
      expect(find.byType(LibraryPageCurl), findsNothing);
      expect(state.controller.page, 0);
      expect(viewPage(tester), 0);
      await tester.pump(const Duration(seconds: 1));
      expect(store.saved, isEmpty);
      await closeAll(tester, store);
    });

    testWidgets('right to left, a rightward drag curls forward', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(pageDirection: LibraryPageDirection.rtl),
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:rtl-drag'),
          store: store,
        ),
      );
      final state = readerState(tester);
      expect(state.controller.rightToLeft, isTrue);
      expect(curlLayer(tester).rightToLeft, isTrue);
      await waitForCurl(tester, state);
      final gesture = await slowDrag(tester, const Offset(40, 450), 300);
      expect(state.curl.direction, LibraryPageTurnDirection.forward);
      expect(viewPage(tester), 0);
      await gesture.up();
      await finish(tester);
      expect(state.controller.page, 1);
      expect(viewPage(tester), 1.0);
      await closeAll(tester, store);
    });
  });

  group('d-pad and tap zones', () {
    testWidgets('the d-pad turns through the curl; presses during the turn '
        'are swallowed', (tester) async {
      useSurface(tester, size: portrait);
      final store = await createRecordingStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:dpad'),
          store: store,
        ),
      );
      final state = readerState(tester);
      await waitForCurl(tester, state);
      await tester.pump(const Duration(seconds: 1));
      store.saved.clear();

      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      expect(state.curl.direction, LibraryPageTurnDirection.forward);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 150));
      expect(find.byType(LibraryPageCurl), findsOneWidget);
      // The page lands at 380 ms: the view has not moved yet.
      expect(state.controller.page, 0);
      expect(viewPage(tester), 0);
      // Neither the d-pad, nor down, nor the right tap zone turns a second
      // page during the turn.
      state.gamepadBindings.right!();
      state.gamepadBindings.down!();
      await tester.tapAt(const Offset(580, 450));
      await tester.pump(const Duration(milliseconds: 300));
      await tester.pump();
      expect(state.controller.page, 1);
      expect(viewPage(tester), 1.0);
      await frames(tester);
      await frames(tester);
      expect(state.controller.page, 1);
      expect(viewPage(tester), 1.0);
      await tester.pump(const Duration(seconds: 1));
      expect(store.saved, <int?>[1]);

      // After it, a press turns again (once the next page is decoded),
      // backward as well.
      await waitForCurl(tester, state);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      await finish(tester);
      expect(state.controller.page, 2);
      state.gamepadBindings.left!();
      expect(state.curl.direction, LibraryPageTurnDirection.backward);
      await finish(tester);
      expect(state.controller.page, 1);
      expect(viewPage(tester), 1.0);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });

    testWidgets('a press the other way during a turn is swallowed too (it '
        'would slide to the chapter card under the curl)', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(
        chapterCount: 2,
        tracksChapters: true,
        initialChapterIndex: 1,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(state.controller.chapterIndex, 1);
      await waitForCurl(tester, state);
      // Item 0 is the start card (previous chapter), item 1 page 0.
      expect(viewPage(tester), 1.0);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      // Backward from page 0 is a slide to the card, never during a turn.
      expect(state.curl.canTurn(LibraryPageTurnDirection.backward), isFalse);
      state.gamepadBindings.left!();
      state.gamepadBindings.up!();
      await tester.tapAt(const Offset(20, 450));
      // (A slide would start on the next frame.)
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));
      expect(viewPage(tester), 1.0);
      await finish(tester);
      expect(state.controller.page, 1);
      expect(state.atStartCard, isFalse);
      expect(viewPage(tester), 2.0);
      await frames(tester);
      expect(viewPage(tester), 2.0);
      expect(state.controller.chapterIndex, 1);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });

    testWidgets('the tap zones turn through the curl, mirrored right to '
        'left', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:taps'),
          store: store,
        ),
      );
      final state = readerState(tester);
      await waitForCurl(tester, state);
      await tester.tapAt(const Offset(580, 450));
      expect(state.curl.isActive, isTrue);
      expect(state.curl.direction, LibraryPageTurnDirection.forward);
      await finish(tester);
      expect(state.controller.page, 1);
      await tester.tapAt(const Offset(20, 450));
      expect(state.curl.direction, LibraryPageTurnDirection.backward);
      await finish(tester);
      expect(state.controller.page, 0);

      // Right to left: the left zone turns forward.
      state.controller.overrideDirection(LibraryPageDirection.rtl);
      await tester.pump();
      await tester.tapAt(const Offset(20, 450));
      expect(state.curl.direction, LibraryPageTurnDirection.forward);
      await finish(tester);
      expect(state.controller.page, 1);
      await closeAll(tester, store);
    });

    testWidgets('closing during a curl saves the page turned to', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:close-curl'),
          store: store,
        ),
        home: StoreWatcher(store: store, progressKey: 'local:close-curl'),
      );
      await tester.pump(const Duration(seconds: 1));
      final state = readerState(tester);
      await waitForCurl(tester, state);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(state.controller.page, 0, reason: 'the curl is still turning');
      state.gamepadBindings.back!();
      expect(store.progressFor('local:close-curl')!.pageIndex, 1);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      expect(store.progressFor('local:close-curl')!.pageIndex, 1);
      expect(find.text('home page:1'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await flushStore(tester, store);
    });
  });

  group('pages still loading', () {
    testWidgets('a page not decoded yet is never curled: the d-pad slides '
        'at once; once decoded, the next turn curls', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      // An online chapter whose page 2 is still downloading.
      final source = GatedPageSource(4, open: <int>{0});
      final content = FakePageContent(
        progressKey: 'online:gated:manga',
        tracksChapters: true,
        loader: (index, cancel) async => source,
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(curlLayer(tester).enabled, isTrue);
      await waitUntil(
        tester,
        () => curlLayer(tester).faceOf(0) != null,
        reason: 'page 1 decodes',
      );
      expect(source.loads[1], 1, reason: 'requested, not decoded');
      expect(curlLayer(tester).faceOf(1), isNull);
      expect(state.curl.canTurn(LibraryPageTurnDirection.forward), isFalse);

      // The d-pad slides at once (no 380 ms of nothing).
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isFalse);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));
      expect(viewPage(tester), inExclusiveRange(0, 1));
      expect(find.byType(LibraryPageCurl), findsNothing);
      await frames(tester);
      expect(state.controller.page, 1);
      // From the page still loading, no curl either: back slides, and a
      // drag moves the PageView.
      expect(state.curl.canTurn(LibraryPageTurnDirection.backward), isFalse);
      final gesture = await slowDrag(tester, const Offset(40, 450), 200);
      expect(state.curl.isActive, isFalse);
      expect(viewPage(tester), lessThan(0.9));
      await gesture.up();
      await tester.pumpAndSettle();
      expect(viewPage(tester), 1.0);
      state.gamepadBindings.left!();
      expect(state.curl.isActive, isFalse);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));
      expect(viewPage(tester), inExclusiveRange(0, 1));
      await frames(tester);
      expect(state.controller.page, 0);

      // Page 2 arrives: the same turn curls, drawn from its first frames.
      source.open(1);
      await waitUntil(
        tester,
        () => state.curl.canTurn(LibraryPageTurnDirection.forward),
        reason: 'page 2 decodes',
      );
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      await tester.pump();
      expect(find.byType(LibraryPageCurl), findsOneWidget);
      await tester.pump(const Duration(milliseconds: 100));
      expect(viewPage(tester), 0);
      await finish(tester);
      expect(state.controller.page, 1);
      expect(viewPage(tester), 1.0);
      // Page 3 is still downloading: the next turn slides again.
      expect(state.curl.canTurn(LibraryPageTurnDirection.forward), isFalse);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isFalse);
      await frames(tester);
      expect(state.controller.page, 2);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });
  });

  group('without a curl', () {
    testWidgets('the slide animates the PageView as in 440', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.updateSettings(
        store.settings.copyWith(turnStyle: LibraryPageTurnStyle.slide),
      );
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:slide'),
          store: store,
        ),
      );
      final state = readerState(tester);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isFalse);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));
      expect(viewPage(tester), inExclusiveRange(0, 1));
      expect(find.byType(LibraryPageCurl), findsNothing);
      await frames(tester);
      expect(viewPage(tester), 1.0);
      expect(state.controller.page, 1);
      // A drag moves the PageView itself.
      final gesture = await slowDrag(tester, const Offset(560, 450), -200);
      expect(viewPage(tester), greaterThan(1.1));
      expect(state.curl.isActive, isFalse);
      await gesture.up();
      await tester.pumpAndSettle();
      await closeAll(tester, store);
    });

    for (final reduceMotion in <bool>[false, true]) {
      testWidgets(
        reduceMotion
            ? 'Reduce Motion turns the curl style without animation'
            : 'the style without animation jumps at once',
        (tester) async {
          useSurface(tester, size: portrait);
          if (reduceMotion) {
            tester.platformDispatcher.accessibilityFeaturesTestValue =
                const FakeAccessibilityFeatures(disableAnimations: true);
            addTearDown(
              tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
            );
          }
          final store = await createRecordingStore(tester);
          if (!reduceMotion) {
            store.updateSettings(
              store.settings.copyWith(turnStyle: LibraryPageTurnStyle.none),
            );
          }
          await pumpReader(
            tester,
            LibraryPageReaderScreen(
              content: FakePageContent(progressKey: 'local:none'),
              store: store,
            ),
          );
          final state = readerState(tester);
          expect(state.controller.turnStyle, LibraryPageTurnStyle.none);
          expect(curlLayer(tester).enabled, isFalse);
          await tester.pump(const Duration(seconds: 1));
          store.saved.clear();
          state.gamepadBindings.right!();
          // At once, without a frame of animation.
          expect(state.controller.page, 1);
          expect(viewPage(tester), 1.0);
          await tester.tapAt(const Offset(580, 450));
          expect(state.controller.page, 2);
          state.gamepadBindings.left!();
          expect(state.controller.page, 1);
          expect(viewPage(tester), 1.0);
          expect(find.byType(LibraryPageCurl), findsNothing);
          await tester.pump(const Duration(seconds: 1));
          expect(store.saved, <int?>[1]);
          await closeAll(tester, store);
        },
      );
    }
  });

  group('chapter cards', () {
    testWidgets('the end and start cards still slide, with the curl on', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final content = FakePageContent(chapterCount: 2, tracksChapters: true);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: content, store: store),
      );
      final state = readerState(tester);
      expect(curlLayer(tester).enabled, isTrue);
      final slider = tester.widget<Slider>(find.byType(Slider));
      slider.onChangeStart!(4);
      slider.onChangeEnd!(4);
      await tester.pump(const Duration(milliseconds: 50));
      expect(state.controller.page, 4);
      // Last page to the end card: no face for the card, the PageView
      // slides.
      expect(curlLayer(tester).faceOf(5), isNull);
      expect(state.curl.canTurn(LibraryPageTurnDirection.forward), isFalse);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isFalse);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));
      expect(viewPage(tester), inExclusiveRange(4, 5));
      expect(find.byType(LibraryPageCurl), findsNothing);
      await frames(tester);
      expect(state.atEndCard, isTrue);
      expect(find.text(en('endOfChapter')), findsOneWidget);

      // A drag on the card reaches the PageView (back to the last page).
      final gesture = await slowDrag(tester, const Offset(40, 450), 360);
      expect(state.curl.isActive, isFalse);
      expect(viewPage(tester), lessThan(4.9));
      await gesture.up();
      await tester.pumpAndSettle();
      expect(state.atEndCard, isFalse);
      expect(state.controller.page, 4);

      // Next chapter: before its first page, the start card slides too.
      state.gamepadBindings.rightBumper!();
      await frames(tester);
      expect(state.controller.chapterIndex, 1);
      expect(state.controller.page, 0);
      expect(curlLayer(tester).faceOf(0), isNull);
      expect(state.curl.canTurn(LibraryPageTurnDirection.backward), isFalse);
      state.gamepadBindings.left!();
      expect(state.curl.isActive, isFalse);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));
      expect(viewPage(tester), inExclusiveRange(0, 1));
      await frames(tester);
      expect(state.atStartCard, isTrue);
      // Between pages, the curl again (once they are decoded).
      state.gamepadBindings.right!();
      await frames(tester);
      expect(state.atStartCard, isFalse);
      await waitForCurl(tester, state);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      await finish(tester);
      expect(state.controller.page, 1);
      expect(tester.takeException(), isNull);
      await closeAll(tester, store);
    });
  });

  group('textures', () {
    testWidgets('the curl draws the reader\'s own decoded pages: one decode '
        'per page, at the size of the PageView', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final source = CountingPageSource(5);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            progressKey: 'local:decodes',
            loader: (index, cancel) async => source,
          ),
          store: store,
        ),
      );
      final state = readerState(tester);
      await waitForCurl(tester, state);
      // 600 x 900 at ratio 1, rounded up to steps of 128 px.
      expect(source.sizes, <(int?, int?)>{(640, 1024)});
      expect(source.decodes[0], 1);
      expect(source.decodes[1], 1);
      state.gamepadBindings.right!();
      expect(state.curl.isActive, isTrue);
      await finish(tester);
      expect(state.controller.page, 1);
      // Rendered from the decoded images: the pages around page 2.
      await waitForTextures(tester, state);
      await waitUntil(tester, () => source.decodes.containsKey(2));
      expect(source.decodes.values, everyElement(1));
      expect(source.decodes.keys, containsAll(<int>[0, 1, 2]));
      expect(source.sizes, <(int?, int?)>{(640, 1024)});
      await closeAll(tester, store);
    });
  });
}

/// Pages of an online chapter that decode only once their download (a
/// gate) is open.
class GatedPageSource implements LibraryPageSource {
  GatedPageSource(this.length, {Set<int> open = const <int>{}})
    : _pages = List<Uint8List>.generate(
        length,
        (i) => buildPng(4, 6, red: (40 * i) & 0xFF),
      ) {
    open.forEach(this.open);
  }

  @override
  final int length;
  final List<Uint8List> _pages;
  final Map<int, Completer<void>> _gates = <int, Completer<void>>{};

  /// Image loads started per page.
  final Map<int, int> loads = <int, int>{};

  @override
  String get key => 'gated';

  Completer<void> _gate(int page) =>
      _gates.putIfAbsent(page, Completer<void>.new);

  /// The download of [page] completes.
  void open(int page) {
    final gate = _gate(page);
    if (!gate.isCompleted) gate.complete();
  }

  @override
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight}) =>
      _GatedImage(this, index, cacheWidth, cacheHeight);

  @override
  void prefetch(int index) {}

  @override
  void cancelPrefetchOutside(int first, int last) {}

  @override
  Future<void> dispose() async {}
}

class _GatedImage extends ImageProvider<_GatedImage> {
  _GatedImage(this.source, this.index, this.cacheWidth, this.cacheHeight);

  final GatedPageSource source;
  final int index;
  final int? cacheWidth;
  final int? cacheHeight;

  @override
  Future<_GatedImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_GatedImage>(this);

  @override
  ImageStreamCompleter loadImage(_GatedImage key, ImageDecoderCallback decode) {
    source.loads[index] = (source.loads[index] ?? 0) + 1;
    return MultiFrameImageStreamCompleter(
      codec: source._gate(index).future.then((_) async {
        final buffer = await ui.ImmutableBuffer.fromUint8List(
          source._pages[index],
        );
        return decode(buffer);
      }),
      scale: 1.0,
    );
  }

  @override
  bool operator ==(Object other) =>
      other is _GatedImage &&
      identical(other.source, source) &&
      other.index == index &&
      other.cacheWidth == cacheWidth &&
      other.cacheHeight == cacheHeight;

  @override
  int get hashCode => Object.hash(source, index, cacheWidth, cacheHeight);
}

/// Pages decoded from tiny PNGs; counts the decodes per page and records
/// the decode sizes asked for.
class CountingPageSource implements LibraryPageSource {
  CountingPageSource(this.length)
    : _pages = List<Uint8List>.generate(
        length,
        (i) => buildPng(4, 6, red: (40 * i) & 0xFF),
      );

  @override
  final int length;
  final List<Uint8List> _pages;
  final Map<int, int> decodes = <int, int>{};
  final Set<(int?, int?)> sizes = <(int?, int?)>{};

  @override
  String get key => 'counting';

  @override
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight}) {
    sizes.add((cacheWidth, cacheHeight));
    return _CountingImage(this, index, cacheWidth, cacheHeight);
  }

  @override
  void prefetch(int index) {}

  @override
  void cancelPrefetchOutside(int first, int last) {}

  @override
  Future<void> dispose() async {}
}

class _CountingImage extends ImageProvider<_CountingImage> {
  _CountingImage(this.source, this.index, this.cacheWidth, this.cacheHeight);

  final CountingPageSource source;
  final int index;
  final int? cacheWidth;
  final int? cacheHeight;

  @override
  Future<_CountingImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_CountingImage>(this);

  @override
  ImageStreamCompleter loadImage(
    _CountingImage key,
    ImageDecoderCallback decode,
  ) {
    source.decodes[index] = (source.decodes[index] ?? 0) + 1;
    final image = MemoryImage(source._pages[index]);
    return image.loadImage(image, decode);
  }

  @override
  bool operator ==(Object other) =>
      other is _CountingImage &&
      identical(other.source, source) &&
      other.index == index &&
      other.cacheWidth == cacheWidth &&
      other.cacheHeight == cacheHeight;

  @override
  int get hashCode => Object.hash(source, index, cacheWidth, cacheHeight);
}
