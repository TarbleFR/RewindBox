// Build 440: the readers always offer one Back the user can reach in one
// tap (the top bar's arrow while the bars are shown, a floating back button
// at the same place while they are hidden). Real reader widgets, real
// navigator, store and orientation service; no device.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show RenderParagraph;
import 'package:flutter/semantics.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/library_pdf_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_book_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_controller.dart';
import 'package:neostation/screens/library_screen/reader/library_page_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_source.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_chrome.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_view.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';
import 'package:pdfrx/pdfrx.dart';

import 'library_reader_test_support.dart';

String tr(String language, String key) =>
    LibraryReaderLocale.values[language]![key]!;

String en(String key) => tr('en', key);

/// 1000 paragraphs: five TXT sections of 200.
String sampleText() => List<String>.generate(
  1000,
  (i) => 'Paragraph $i ${List<String>.filled(40, 'word$i').join(' ')}',
).join('\n\n');

LibraryPageReaderScreenState pageState(WidgetTester tester) => tester
    .state<LibraryPageReaderScreenState>(find.byType(LibraryPageReaderScreen));

LibraryBookReaderScreenState bookState(WidgetTester tester) => tester
    .state<LibraryBookReaderScreenState>(find.byType(LibraryBookReaderScreen));

/// The floating back button (built in every reader, offered only while the
/// bars are hidden).
Finder floatingBack() => find.byType(LibraryReaderFloatingBackButton);

/// The Back control (tooltip owner) inside [owner].
Finder backIn(Finder owner, [String? label]) =>
    find.descendant(of: owner, matching: find.byTooltip(label ?? en('back')));

Finder topBar() => find.byType(LibraryReaderTopBar);

/// Insets of an iPhone with a Dynamic Island, in logical points.
const EdgeInsets portraitInsets = EdgeInsets.only(top: 59, bottom: 34);
const EdgeInsets landscapeInsets = EdgeInsets.only(
  left: 59,
  right: 59,
  bottom: 21,
);

/// An iPhone-sized surface with its safe-area insets; returns the insets.
EdgeInsets usePhone(WidgetTester tester, {bool landscape = false}) {
  useSurface(
    tester,
    size: landscape ? const Size(852, 393) : const Size(393, 852),
  );
  final insets = landscape ? landscapeInsets : portraitInsets;
  tester.view.padding = FakeViewPadding(
    left: insets.left,
    top: insets.top,
    right: insets.right,
    bottom: insets.bottom,
  );
  return insets;
}

/// Lets the bars hide by themselves (4 s) and their fade end.
Future<void> waitForBarsToHide(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 5));
  await tester.pump(const Duration(milliseconds: 300));
}

/// Focus node of the Back control inside [owner] (the one of its
/// InkResponse).
FocusNode backFocus(WidgetTester tester, Finder owner, String label) =>
    Focus.of(
      tester.element(
        find.descendant(of: backIn(owner, label), matching: find.byType(Icon)),
      ),
    );

/// Exactly one Back can be reached, by touch, by VoiceOver and with the
/// keyboard: the top bar's arrow when [barsVisible], else the floating back
/// button. The other one is neither hit-testable, nor in the semantics
/// tree, nor focusable.
///
/// [slidingIn]: the top bar is still sliding in. Until its arrow covers the
/// floating button's place, the floating button keeps the touches there
/// (both close the reader: a tap at that place is never a page turn), but
/// it is already out of the semantics tree and of focus.
void expectOneBack(
  WidgetTester tester, {
  required bool barsVisible,
  String? label,
  bool slidingIn = false,
}) {
  assert(!slidingIn || barsVisible);
  final text = label ?? en('back');
  final shown = barsVisible ? topBar() : floatingBack();
  final hidden = barsVisible ? floatingBack() : topBar();
  expect(backIn(shown, text).hitTestable(), findsOne);
  if (slidingIn) {
    expect(backIn(hidden, text).hitTestable(), findsOne);
    expect(find.byTooltip(text).hitTestable(), findsNWidgets(2));
  } else {
    expect(find.byTooltip(text).hitTestable(), findsOne);
    expect(backIn(hidden, text).hitTestable(), findsNothing);
  }
  // Keyboard: only the shown control can take the focus.
  expect(backFocus(tester, shown, text).canRequestFocus, isTrue);
  expect(backFocus(tester, hidden, text).canRequestFocus, isFalse);
  expect(find.semantics.byLabel(text), findsOne);
  // The one node is the shown control's; the hidden one has none.
  final shownNode = find.descendant(
    of: shown,
    matching: find.bySemanticsLabel(text),
  );
  expect(shownNode, findsOne);
  final SemanticsNode node = tester.renderObject(shownNode).debugSemantics!;
  expect(node.attached, isTrue);
  expect(node, isSemantics(label: text, isButton: true, hasTapAction: true));
  expect(find.semantics.byLabel(text).evaluate().single.id, node.id);
  // A control hidden after being shown may keep its former node, detached
  // from the tree.
  for (final element
      in find
          .descendant(of: hidden, matching: find.bySemanticsLabel(text))
          .evaluate()) {
    final former = (element as RenderObjectElement).renderObject.debugSemantics;
    expect(former?.attached ?? false, isFalse, reason: 'hidden control');
  }
}

/// Where the keyboard focus lands on each of [count] Tab presses: `top`
/// (in the top bar), `bottom` (in the bottom bar), `floating` (the
/// floating back button), else `other` or `none`.
Future<List<String>> tabStops(WidgetTester tester, {int count = 8}) async {
  final stops = <String>[];
  for (var i = 0; i < count; i++) {
    await tester.sendKeyEvent(LogicalKeyboardKey.tab);
    await tester.pump();
    final context = FocusManager.instance.primaryFocus?.context;
    if (context == null) {
      stops.add('none');
    } else if (context.findAncestorWidgetOfExactType<LibraryReaderTopBar>() !=
        null) {
      stops.add('top');
    } else if (context
            .findAncestorWidgetOfExactType<LibraryReaderBottomBar>() !=
        null) {
      stops.add('bottom');
    } else if (context
            .findAncestorWidgetOfExactType<LibraryReaderFloatingBackButton>() !=
        null) {
      stops.add('floating');
    } else {
      stops.add('other');
    }
  }
  return stops;
}

/// One line of the reflowed text: the book position where it starts and
/// the box of its glyphs on screen.
class TextLine {
  TextLine(this.position, this.rect);

  final LibraryReflowPosition position;
  final Rect rect;

  String get key => '${position.chapter}:${position.block}:${position.offset}';

  @override
  String toString() => '$key $rect';
}

/// Orders two book positions.
int comparePositions(LibraryReflowPosition a, LibraryReflowPosition b) {
  if (a.chapter != b.chapter) return a.chapter.compareTo(b.chapter);
  if (a.block != b.block) return a.block.compareTo(b.block);
  return a.offset.compareTo(b.offset);
}

/// Every text line the book reader has laid out (on screen and in its
/// cache), top to bottom.
List<TextLine> textLines(WidgetTester tester) {
  final lines = <TextLine>[];
  for (final element in find.byType(LibraryReflowUnitView).evaluate()) {
    final unit = (element.widget as LibraryReflowUnitView).unit;
    void visit(Element child) {
      final object = child.renderObject;
      if (child is RenderObjectElement &&
          object is RenderParagraph &&
          object.attached &&
          object.hasSize) {
        final length = object.text.toPlainText().length;
        final boxes = object.getBoxesForSelection(
          TextSelection(baseOffset: 0, extentOffset: length),
        );
        // One box per run: the runs of a line share its top.
        final byTop = <double, Rect>{};
        for (final box in boxes) {
          final rect = box.toRect();
          final top = (rect.top * 2).roundToDouble() / 2;
          byTop[top] = byTop[top]?.expandToInclude(rect) ?? rect;
        }
        final origin = object.localToGlobal(Offset.zero);
        for (final rect in byTop.values) {
          final start = object
              .getPositionForOffset(Offset(rect.left, rect.center.dy))
              .offset;
          lines.add(
            TextLine(
              LibraryReflowPosition(
                unit.chapter,
                unit.block,
                unit.start + start,
              ),
              rect.shift(origin),
            ),
          );
        }
        return;
      }
      child.visitChildren(visit);
    }

    element.visitChildren(visit);
  }
  lines.sort((a, b) => a.rect.top.compareTo(b.rect.top));
  return lines;
}

/// The floating button calls the reader's own close action: the one of the
/// top bar's arrow and of B on a controller (same save, same orientation
/// restore).
void expectReaderCloseAction(WidgetTester tester, VoidCallback? gamepadBack) {
  final overlay = tester.widget<LibraryReaderChromeOverlay>(
    find.byType(LibraryReaderChromeOverlay),
  );
  expect(overlay.onBack, tester.widget<LibraryReaderTopBar>(topBar()).onBack);
  expect(overlay.onBack, gamepadBack);
}

/// Records the routes popped from the navigator.
class PopRecorder extends NavigatorObserver {
  final List<Route<dynamic>> popped = <Route<dynamic>>[];

  @override
  void didPop(Route<dynamic> route, Route<dynamic>? previousRoute) =>
      popped.add(route);
}

Future<void> closeAll(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await settle(tester, rounds: 2);
  await flushStore(tester, store);
}

/// WCAG contrast ratio of two opaque colours.
double contrast(Color a, Color b) {
  final la = a.computeLuminance();
  final lb = b.computeLuminance();
  final light = la > lb ? la : lb;
  final dark = la > lb ? lb : la;
  return (light + 0.05) / (dark + 0.05);
}

/// pdfium is not loaded in Flutter tests: these stand for the document
/// pdfrx reports through the viewer's own callbacks.
class FakePdfDocument implements PdfDocument {
  FakePdfDocument(int count)
    : pages = List<PdfPage>.generate(count, (_) => FakePdfPage());

  @override
  final List<PdfPage> pages;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakePdfPage implements PdfPage {
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakePdfViewerController extends PdfViewerController {
  @override
  int? get pageNumber => 1;
}

/// pdfrx asks path_provider for its cache folder.
void mockPathProvider() {
  const channel = MethodChannel('plugins.flutter.io/path_provider');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(
    channel,
    (call) async => Directory.systemTemp.path,
  );
  addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
}

/// Reports the PDF as opened with [pageCount] pages through the viewer's
/// own ready callback.
Future<PdfViewerParams> makePdfReady(
  WidgetTester tester, {
  int pageCount = 12,
}) async {
  final params = tester.widget<PdfViewer>(find.byType(PdfViewer)).params;
  params.onViewerReady!(FakePdfDocument(pageCount), FakePdfViewerController());
  await tester.pump();
  params.onPageChanged!(1);
  await tester.pump();
  return params;
}

/// The PDF reader in its scroll mode: the pdfrx viewer of Build 440, the
/// path these tests cover (set explicitly since the pages mode became the
/// default; the pages mode has its own Back tests in
/// library_reader_pdf_modes_test.dart).
LibraryPdfReaderScreen pdfReader(
  LibraryReadingStore store, {
  LibraryReaderOrientation? orientation,
  String progressKey = 'local:pdf',
}) {
  store.updateSettings(store.settings.copyWith(pdfMode: LibraryPdfMode.scroll));
  return LibraryPdfReaderScreen(
    filePath: '${Directory.systemTemp.path}/missing-back-button.pdf',
    title: 'Manual',
    progressKey: progressKey,
    store: store,
    orientation: orientation,
  );
}

/// The EPUB/TXT reader in its continuous scroll: the 440 reader, the path
/// these tests cover (set explicitly since the pages layout became the
/// default; the pages layout has its own Back tests in
/// library_reader_book_pages_test.dart).
LibraryBookReaderScreen bookReader(
  LibraryReadingStore store, {
  String progressKey = 'local:book',
  LibraryReaderOrientation? orientation,
  LibraryReflowSourceOpener? open,
}) {
  store.updateSettings(
    store.settings.copyWith(textLayout: LibraryTextLayout.scroll),
  );
  return LibraryBookReaderScreen(
    open:
        open ??
        () async =>
            LibraryTextReflowSource(LibraryTextDocument.fromText(sampleText())),
    progressKey: progressKey,
    title: 'Sample',
    store: store,
    orientation: orientation,
  );
}

void main() {
  setUpReaderEnvironment();

  group('page reader (CBZ, online chapters)', () {
    testWidgets(
      'bars hidden: one tap on the floating Back saves the page, restores '
      'landscape and returns to the screen that opened the reader',
      (tester) async {
        usePhone(tester);
        final (store, _) = await createStore(tester);
        final platform = RecordingOrientationPlatform();
        final orientation = LibraryReaderOrientation(
          platform: platform,
          isIOS: true,
        );
        final pops = PopRecorder();
        final navigator = await pumpReader(
          tester,
          LibraryPageReaderScreen(
            content: FakePageContent(progressKey: 'local:float'),
            store: store,
            orientation: orientation,
          ),
          opener: StoreWatcher(store: store, progressKey: 'local:float'),
          navigatorObservers: <NavigatorObserver>[pops],
        );
        await tester.pump();
        expect(platform.calls, readerOrientationRoundTrip.sublist(0, 2));
        final state = pageState(tester);
        for (var i = 0; i < 2; i++) {
          state.gamepadBindings.right!();
          await frames(tester);
        }
        expect(state.controller.page, 2);
        await waitForBarsToHide(tester);
        expect(state.chromeVisible, isFalse);
        expect(floatingBack().hitTestable(), findsOne);
        expectReaderCloseAction(tester, state.gamepadBindings.back);

        await tester.tap(floatingBack());
        // Saved before the pop, while the opener can rebuild for it.
        expect(store.progressFor('local:float')!.pageIndex, 2);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 120));
        // Landscape is restored as soon as the pop starts.
        expect(platform.calls, readerOrientationRoundTrip);
        await tester.pump(const Duration(milliseconds: 400));
        expect(find.byType(LibraryPageReaderScreen), findsNothing);
        expect(pops.popped, hasLength(1));
        expect(find.text('home page:2'), findsOneWidget);
        expect(navigator.currentState!.canPop(), isTrue, reason: 'opener');
        expect(tester.takeException(), isNull);
        await flushStore(tester, store);
      },
    );

    testWidgets('a tap during an animated turn saves the page turned to', (
      tester,
    ) async {
      usePhone(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(progressKey: 'local:turning'),
          store: store,
        ),
        opener: StoreWatcher(store: store, progressKey: 'local:turning'),
      );
      final state = pageState(tester);
      await waitForBarsToHide(tester);
      state.gamepadBindings.right!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 30));
      expect(state.controller.page, 0, reason: 'the turn is still running');

      await tester.tap(floatingBack());
      expect(store.progressFor('local:turning')!.pageIndex, 1);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      expect(store.progressFor('local:turning')!.pageIndex, 1);
      expect(find.text('home page:1'), findsOneWidget);
      await flushStore(tester, store);
    });

    // Second tap before any new frame, or 80 ms later like a finger's
    // double tap: only the reader is popped, the opener stays.
    for (final gap in <Duration>[
      Duration.zero,
      const Duration(milliseconds: 80),
    ]) {
      testWidgets('a double tap on the floating Back pops only the reader '
          '(${gap.inMilliseconds} ms apart)', (tester) async {
        usePhone(tester);
        final (store, _) = await createStore(tester);
        final pops = PopRecorder();
        final navigator = await pumpReader(
          tester,
          LibraryPageReaderScreen(
            content: FakePageContent(progressKey: 'local:twice'),
            store: store,
          ),
          opener: StoreWatcher(store: store, progressKey: 'local:twice'),
          navigatorObservers: <NavigatorObserver>[pops],
        );
        await waitForBarsToHide(tester);
        await tester.tap(floatingBack());
        if (gap > Duration.zero) await tester.pump(gap);
        await tester.tap(floatingBack(), warnIfMissed: false);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byType(LibraryPageReaderScreen), findsNothing);
        expect(pops.popped, hasLength(1));
        expect(find.byType(StoreWatcher), findsOneWidget);
        expect(navigator.currentState!.canPop(), isTrue);
        expect(tester.takeException(), isNull);
        await flushStore(tester, store);
      });
    }

    // Build 440 review: the floating Back stopped taking touches as soon as
    // the bars were shown, while the top bar only covers its place near the
    // end of its 200 ms slide. A tap there in between reached the page (left
    // zone: a page back) instead of leaving.
    for (final gap in <int>[20, 60, 100, 140, 250]) {
      testWidgets('a tap at the back place $gap ms after the bars are shown '
          'leaves the reader once, never turns a page', (tester) async {
        usePhone(tester);
        final (store, _) = await createStore(tester);
        final pops = PopRecorder();
        final navigator = await pumpReader(
          tester,
          LibraryPageReaderScreen(
            content: FakePageContent(progressKey: 'local:place'),
            store: store,
          ),
          opener: StoreWatcher(store: store, progressKey: 'local:place'),
          navigatorObservers: <NavigatorObserver>[pops],
        );
        final state = pageState(tester);
        for (var i = 0; i < 2; i++) {
          state.gamepadBindings.right!();
          await frames(tester);
        }
        await waitForBarsToHide(tester);
        final place = tester.getCenter(floatingBack());
        // A shows the bars; their slide starts on the next frame.
        state.gamepadBindings.select!();
        await tester.pump();
        await tester.pump(Duration(milliseconds: gap));
        expect(state.chromeVisible, isTrue);

        await tester.tapAt(place);
        expect(state.controller.page, 2);
        expect(store.progressFor('local:place')!.pageIndex, 2);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 500));
        expect(find.byType(LibraryPageReaderScreen), findsNothing);
        expect(pops.popped, hasLength(1));
        expect(find.text('home page:2'), findsOneWidget);
        expect(navigator.currentState!.canPop(), isTrue, reason: 'opener');
        expect(tester.takeException(), isNull);
        await flushStore(tester, store);
      });
    }

    testWidgets('the keyboard reaches one Back: the hidden bars take no '
        'focus', (tester) async {
      usePhone(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: FakePageContent(), store: store),
      );
      final state = pageState(tester);
      // Bars shown: their controls, not the floating Back.
      expect(state.chromeVisible, isTrue);
      final shown = await tabStops(tester);
      expect(shown, containsAll(<String>['top', 'bottom']));
      expect(shown, isNot(contains('floating')));
      // Bars hidden (Build 440 review: Tab still went through the invisible
      // top bar's Back and settings and the bottom bar).
      await waitForBarsToHide(tester);
      expect(state.chromeVisible, isFalse);
      final hidden = await tabStops(tester);
      expect(hidden, contains('floating'));
      expect(hidden, isNot(contains('top')));
      expect(hidden, isNot(contains('bottom')));
      // Moving the focus neither shows the bars nor turns a page.
      expect(state.chromeVisible, isFalse);
      expect(state.controller.page, 0);
      await closeAll(tester, store);
    });

    testWidgets('the floating Back turns no page and does not show the bars', (
      tester,
    ) async {
      usePhone(tester);
      final (store, _) = await createStore(tester);
      // The pop is refused, so the reader stays to be looked at after the
      // tap (its close path still saves).
      await pumpReader(
        tester,
        PopScope<Object?>(
          canPop: false,
          child: LibraryPageReaderScreen(
            content: FakePageContent(progressKey: 'local:stay'),
            store: store,
          ),
        ),
      );
      final state = pageState(tester);
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      await waitForBarsToHide(tester);
      expect(state.controller.page, 2);
      // A tap reaching the page there (left third) would turn back a page.
      await tester.tap(floatingBack());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(state.controller.page, 2);
      expect(state.chromeVisible, isFalse);
      expect(store.progressFor('local:stay')!.pageIndex, 2);
      // Without tap zones, a tap reaching the page would show the bars.
      store.updateSettings(store.settings.copyWith(tapZones: false));
      await tester.pump();
      await tester.tap(floatingBack());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(state.chromeVisible, isFalse);
      expect(state.controller.page, 2);
      expect(find.byType(LibraryPageReaderScreen), findsOneWidget);
      await closeAll(tester, store);
    });

    testWidgets('exactly one Back while paged, fading, zoomed and vertical', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      usePhone(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        LibraryPageReaderScreen(content: FakePageContent(), store: store),
      );
      final state = pageState(tester);
      // Bars shown at the opening: the top bar's arrow.
      expect(state.chromeVisible, isTrue);
      expectOneBack(tester, barsVisible: true);

      // The bars hide (4 s): halfway through the cross-fade, already one.
      await tester.pump(const Duration(seconds: 4));
      await tester.pump(const Duration(milliseconds: 100));
      expect(state.chromeVisible, isFalse);
      final fade = tester.widget<FadeTransition>(
        find
            .ancestor(of: floatingBack(), matching: find.byType(FadeTransition))
            .first,
      );
      expect(fade.opacity.value, inExclusiveRange(0, 1));
      expectOneBack(tester, barsVisible: false);
      await tester.pump(const Duration(milliseconds: 200));
      expectOneBack(tester, barsVisible: false);

      // Zoomed page (double tap in the middle; the bars stay hidden).
      await tester.tapAt(const Offset(196, 426));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tapAt(const Offset(198, 428));
      await frames(tester);
      expect(state.zoomed, isTrue);
      expect(state.chromeVisible, isFalse);
      expectOneBack(tester, barsVisible: false);
      // A tap shows the bars over the zoomed page: the arrow is the one
      // Back for VoiceOver and the keyboard at once. While the bar is still
      // sliding in (it does not cover the floating button yet), the
      // floating button keeps the touches at its place (Build 440 review:
      // a tap there reached the page and turned it); then only the arrow.
      await tester.tapAt(const Offset(196, 426));
      await tester.pump(const Duration(milliseconds: 400));
      expect(state.chromeVisible, isTrue);
      await tester.pump(const Duration(milliseconds: 60));
      final slide = tester.widget<SlideTransition>(
        find
            .ancestor(of: topBar(), matching: find.byType(SlideTransition))
            .first,
      );
      expect(slide.position.value.dy, inExclusiveRange(-1, 0));
      expectOneBack(tester, barsVisible: true, slidingIn: true);
      await tester.pump(const Duration(milliseconds: 300));
      expect(slide.position.value.dy, 0);
      expectOneBack(tester, barsVisible: true);

      // Vertical strip (webtoon), bars hidden again.
      state.controller.toggleMode();
      await frames(tester);
      expect(state.controller.mode, LibraryPageReaderMode.vertical);
      await waitForBarsToHide(tester);
      expect(state.chromeVisible, isFalse);
      expectOneBack(tester, barsVisible: false);

      await closeAll(tester, store);
      semantics.dispose();
    });

    testWidgets('loading and failed chapters keep the bars and their arrow', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      usePhone(tester);
      final (store, _) = await createStore(tester);
      final pending = Completer<LibraryPageSource>();
      await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(loader: (_, _) => pending.future),
          store: store,
        ),
      );
      expect(
        pageState(tester).controller.status,
        LibraryPageReaderStatus.loading,
      );
      await tester.pump(const Duration(seconds: 6));
      expectOneBack(tester, barsVisible: true);
      await closeAll(tester, store);

      final (failing, _) = await createStore(tester);
      final navigator = await pumpReader(
        tester,
        LibraryPageReaderScreen(
          content: FakePageContent(
            loader: (_, _) async => throw const LibraryNetworkException(
              LibraryNetworkErrorKind.serverUnavailable,
              statusCode: 503,
            ),
          ),
          store: failing,
        ),
      );
      expect(
        pageState(tester).controller.status,
        LibraryPageReaderStatus.error,
      );
      await tester.pump(const Duration(seconds: 6));
      expectOneBack(tester, barsVisible: true);
      // One tap on that arrow leaves the failed chapter.
      await tester.tap(backIn(topBar()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibraryPageReaderScreen), findsNothing);
      expect(navigator.currentState!.canPop(), isFalse);
      if (!pending.isCompleted) pending.complete(MemoryPageSource(1));
      await closeAll(tester, failing);
      semantics.dispose();
    });

    for (final landscape in <bool>[false, true]) {
      testWidgets('the floating Back sits in the safe area, where the arrow is '
          '(${landscape ? 'landscape' : 'portrait'})', (tester) async {
        final insets = usePhone(tester, landscape: landscape);
        final width = tester.view.physicalSize.width;
        final (store, _) = await createStore(tester);
        await pumpReader(
          tester,
          LibraryPageReaderScreen(content: FakePageContent(), store: store),
        );
        // Once the route transition has ended, before the bars hide.
        await tester.pump(const Duration(seconds: 1));
        final arrow = tester.getRect(backIn(topBar()));
        await waitForBarsToHide(tester);
        final target = tester.getRect(backIn(floatingBack()));
        // The finger finds it where the arrow was.
        expect(target, rectMoreOrLessEquals(arrow));
        expect(target.width, greaterThanOrEqualTo(kLibraryReaderTouchTarget));
        expect(target.height, greaterThanOrEqualTo(kLibraryReaderTouchTarget));
        // Inside the safe area: notch / Dynamic Island, rounded corners.
        expect(target.top, greaterThanOrEqualTo(insets.top));
        expect(target.left, greaterThanOrEqualTo(insets.left));
        expect(target.right, lessThanOrEqualTo(width - insets.right));
        // The disc is drawn inside its touch target.
        final disc = tester.getRect(
          find.descendant(of: floatingBack(), matching: find.byType(Ink)),
        );
        expect(target.contains(disc.topLeft), isTrue);
        expect(target.contains(disc.bottomRight - const Offset(1, 1)), isTrue);
        expect(disc.width, LibraryReaderFloatingBackButton.discDiameter);
        await closeAll(tester, store);
      });
    }

    for (final (language, locale) in <(String, Locale)>[
      ('fr', const Locale('fr')),
      ('zh_Hant', const Locale('zh', 'TW')),
    ]) {
      testWidgets('the floating Back is labelled in $locale', (tester) async {
        final semantics = tester.ensureSemantics();
        usePhone(tester);
        final (store, _) = await createStore(tester);
        await pumpReader(
          tester,
          LibraryPageReaderScreen(content: FakePageContent(), store: store),
          locale: locale,
        );
        await waitForBarsToHide(tester);
        final label = tr(language, 'back');
        expect(LibraryReaderLocale.forLocale(locale, 'back'), label);
        expectOneBack(tester, barsVisible: false, label: label);
        // The whole chrome reads the same catalog (zh-TW: Traditional
        // Chinese, not the Simplified texts).
        expect(find.byTooltip(tr(language, 'settings')), findsOneWidget);
        if (language == 'zh_Hant') {
          expect(tr('zh_Hant', 'settings'), isNot(tr('zh', 'settings')));
          expect(find.byTooltip(tr('zh', 'settings')), findsNothing);
        }
        await closeAll(tester, store);
        semantics.dispose();
      });
    }

    for (final (theme, palette) in <(LibraryReaderTheme, LibraryReaderPalette)>[
      (LibraryReaderTheme.dark, LibraryReaderPalette.dark),
      (LibraryReaderTheme.light, LibraryReaderPalette.light),
    ]) {
      testWidgets('the floating Back follows the ${theme.name} palette', (
        tester,
      ) async {
        usePhone(tester);
        final (store, _) = await createStore(tester);
        store.updateSettings(store.settings.copyWith(theme: theme));
        await pumpReader(
          tester,
          LibraryPageReaderScreen(content: FakePageContent(), store: store),
        );
        await waitForBarsToHide(tester);
        final ink = tester.widget<Ink>(
          find.descendant(of: floatingBack(), matching: find.byType(Ink)),
        );
        final decoration = ink.decoration! as ShapeDecoration;
        // Translucent disc in the reader's chrome colour.
        expect(
          decoration.color,
          palette.chromeBackground.withValues(
            alpha: LibraryReaderFloatingBackButton.discOpacity,
          ),
        );
        expect(decoration.color!.a, lessThan(1));
        expect((decoration.shape as CircleBorder).side.color, palette.divider);
        final icon = tester.widget<Icon>(
          find.descendant(of: floatingBack(), matching: find.byType(Icon)),
        );
        expect(icon.color, palette.chromeForeground);
        // Same icon as the top bar's arrow.
        final arrow = tester.widget<Icon>(
          find.descendant(of: topBar(), matching: find.byType(Icon)).first,
        );
        expect(icon.icon, kLibraryReaderBackIcon);
        expect(arrow.icon, icon.icon);
        expect(arrow.color, icon.color);
        await closeAll(tester, store);
      });
    }

    test('the arrow stays legible on its disc in every reader theme', () {
      for (final palette in <LibraryReaderPalette>[
        LibraryReaderPalette.light,
        LibraryReaderPalette.sepia,
        LibraryReaderPalette.dark,
        LibraryReaderPalette.black,
      ]) {
        // Over a black page, a white page and the theme's own background.
        for (final backdrop in <Color>[
          const Color(0xFF000000),
          const Color(0xFFFFFFFF),
          palette.background,
        ]) {
          final disc = Color.alphaBlend(
            LibraryReaderFloatingBackButton.discColor(palette),
            backdrop,
          );
          // WCAG 1.4.11 (non-text contrast): at least 3:1.
          expect(
            contrast(palette.chromeForeground, disc),
            greaterThanOrEqualTo(3),
            reason: '${palette.theme.name} over $backdrop',
          );
        }
      }
    });
  });

  group('EPUB/TXT reader', () {
    testWidgets(
      'bars hidden: one tap on the floating Back saves the line being read '
      'and returns to the screen that opened the book',
      (tester) async {
        usePhone(tester);
        final (store, _) = await createStore(tester);
        final platform = RecordingOrientationPlatform();
        final orientation = LibraryReaderOrientation(
          platform: platform,
          isIOS: true,
        );
        final pops = PopRecorder();
        final navigator = await pumpReader(
          tester,
          bookReader(store, orientation: orientation),
          opener: StoreWatcher(store: store, progressKey: 'local:book'),
          navigatorObservers: <NavigatorObserver>[pops],
        );
        await settle(tester, rounds: 2);
        expect(platform.calls, readerOrientationRoundTrip.sublist(0, 2));
        final state = bookState(tester);
        state.gamepadBindings.right!();
        await frames(tester);
        await waitForBarsToHide(tester);
        expect(state.chromeVisible, isFalse);
        // Read on, then leave within the save delay: the close saves it.
        state.gamepadBindings.right!();
        await frames(tester);
        final shown = state.currentPosition!;
        expect(shown.block, greaterThan(0));
        final location =
            'txt:${200 * shown.chapter + shown.block}:${shown.offset}';
        expectReaderCloseAction(tester, state.gamepadBindings.back);

        await tester.tap(floatingBack());
        expect(store.progressFor('local:book')!.location, location);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 120));
        expect(platform.calls, readerOrientationRoundTrip);
        await tester.pump(const Duration(milliseconds: 400));
        expect(find.byType(LibraryBookReaderScreen), findsNothing);
        expect(pops.popped, hasLength(1));
        expect(find.text('home $location'), findsOneWidget);
        expect(navigator.currentState!.canPop(), isTrue, reason: 'opener');
        expect(tester.takeException(), isNull);
        await settle(tester, rounds: 2);
        await flushStore(tester, store);
      },
    );

    for (final landscape in <bool>[false, true]) {
      testWidgets('the line being read is placed just below the back control '
          '(${landscape ? 'landscape' : 'portrait'})', (tester) async {
        usePhone(tester, landscape: landscape);
        final (store, _) = await createStore(tester);
        store.saveProgress(
          LibraryReadingProgress(
            key: 'local:inset',
            location: 'txt:450:0',
            fraction: 0.45,
          ),
        );
        await pumpReader(tester, bookReader(store, progressKey: 'local:inset'));
        await settle(tester, rounds: 2);
        final state = bookState(tester);
        // The saved location still opens at the same words.
        expect(state.currentPosition, const LibraryReflowPosition(2, 50, 0));
        final line = find.textContaining('Paragraph 450 ', findRichText: true);
        final back = tester.getRect(floatingBack());
        final top = tester.getRect(line).top;
        // Below the floating Back and below the top bar shown at the
        // opening, with a small reserve only.
        expect(top, greaterThanOrEqualTo(back.bottom));
        expect(top - back.bottom, lessThanOrEqualTo(8));
        expect(top, greaterThanOrEqualTo(tester.getRect(topBar()).bottom));
        // Hiding the bars moves no text.
        await waitForBarsToHide(tester);
        expect(state.chromeVisible, isFalse);
        expect(tester.getRect(line).top, top);
        expect(state.currentPosition, const LibraryReflowPosition(2, 50, 0));
        await closeAll(tester, store);
      });
    }

    // Build 440 review: a page turn moved 0.9 screen, so the first line not
    // shown yet landed under the floating Back (portrait y 67-95, landscape
    // y 21-40) and the position saved was often the line after it.
    for (final landscape in <bool>[false, true]) {
      testWidgets('a page turn never leaves a line not read yet under the '
          'floating Back (${landscape ? 'landscape' : 'portrait'})', (
        tester,
      ) async {
        usePhone(tester, landscape: landscape);
        final size = tester.view.physicalSize;
        final (store, _) = await createStore(tester);
        await pumpReader(tester, bookReader(store, progressKey: 'local:turns'));
        await settle(tester, rounds: 2);
        final state = bookState(tester);
        await waitForBarsToHide(tester);
        expect(state.chromeVisible, isFalse);
        final disc = tester.getRect(
          find.descendant(of: floatingBack(), matching: find.byType(Ink)),
        );

        Future<void> turn(String how, Future<void> Function() action) async {
          await action();
          await frames(tester);
          await settle(tester, rounds: 1);
          expect(state.chromeVisible, isFalse, reason: how);
        }

        // Forward: the first line not wholly on screen (cut by the bottom
        // edge or below it) lands wholly below the floating Back, and every
        // line now under the button was read before the turn.
        Future<void> forward(String how, Future<void> Function() action) async {
          final before = textLines(tester);
          final read = <String>{
            for (final line in before)
              if (line.rect.top >= 0 &&
                  line.rect.bottom <= size.height &&
                  !line.rect.overlaps(disc))
                line.key,
          };
          final next = before.firstWhere(
            (line) => line.rect.bottom > size.height,
          );
          await turn(how, action);
          final after = textLines(tester);
          final moved = after.singleWhere((line) => line.key == next.key);
          expect(
            moved.rect.top,
            greaterThanOrEqualTo(disc.bottom),
            reason: '$how: $next lands under the floating Back at $moved',
          );
          expect(moved.rect.bottom, lessThanOrEqualTo(size.height));
          for (final line in after.where((line) => line.rect.overlaps(disc))) {
            expect(read, contains(line.key), reason: '$how: $line not read');
          }
          // The position saved is never past a line not shown yet.
          expect(
            comparePositions(state.currentPosition!, next.position),
            lessThanOrEqualTo(0),
            reason: '$how: ${state.currentPosition} after $next',
          );
          // Still a page turn: most of a screen.
          expect(
            next.rect.top - moved.rect.top,
            greaterThan(size.height * 0.7),
          );
        }

        // Back: the last line above the text below the button (cut by it,
        // under it or above the screen) lands wholly on screen below it.
        Future<void> back(String how, Future<void> Function() action) async {
          final before = textLines(tester);
          final previous = before.lastWhere(
            (line) => line.rect.top < disc.bottom,
          );
          await turn(how, action);
          final moved = textLines(
            tester,
          ).singleWhere((line) => line.key == previous.key);
          expect(
            moved.rect.top,
            greaterThanOrEqualTo(disc.bottom),
            reason: '$how: $previous at $moved',
          );
          expect(
            moved.rect.bottom,
            lessThanOrEqualTo(size.height),
            reason: '$how: $previous skipped (now at $moved)',
          );
          expect(
            moved.rect.top - previous.rect.top,
            greaterThan(size.height * 0.7),
          );
        }

        final right = Offset(size.width - 24, size.height / 2);
        final left = Offset(24, size.height / 2);
        for (var i = 0; i < 3; i++) {
          await forward('right third', () => tester.tapAt(right));
          await forward('controller right', () async {
            state.gamepadBindings.right!();
          });
        }
        for (var i = 0; i < 2; i++) {
          await back('left third', () => tester.tapAt(left));
          await back('controller left', () async {
            state.gamepadBindings.left!();
          });
        }
        await closeAll(tester, store);
      });
    }

    testWidgets('a tap at the back place while the bars slide in closes the '
        'book, never pages up', (tester) async {
      usePhone(tester);
      final (store, _) = await createStore(tester);
      final pops = PopRecorder();
      await pumpReader(
        tester,
        bookReader(store, progressKey: 'local:place'),
        opener: StoreWatcher(store: store, progressKey: 'local:place'),
        navigatorObservers: <NavigatorObserver>[pops],
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      state.gamepadBindings.right!();
      await frames(tester);
      await waitForBarsToHide(tester);
      final shown = state.currentPosition!;
      final place = tester.getCenter(floatingBack());
      state.gamepadBindings.select!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 60));
      expect(state.chromeVisible, isTrue);

      await tester.tapAt(place);
      expect(
        store.progressFor('local:place')!.location,
        'txt:${200 * shown.chapter + shown.block}:${shown.offset}',
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      expect(pops.popped, hasLength(1));
      expect(tester.takeException(), isNull);
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });

    testWidgets('the floating Back neither scrolls nor shows the bars', (
      tester,
    ) async {
      usePhone(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(
        tester,
        PopScope<Object?>(
          canPop: false,
          child: bookReader(store, progressKey: 'local:stay'),
        ),
      );
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      for (var i = 0; i < 2; i++) {
        state.gamepadBindings.right!();
        await frames(tester);
      }
      await waitForBarsToHide(tester);
      final before = state.currentPosition;
      expect(before!.block, greaterThan(0));
      // A tap reaching the text there (left third) would page up.
      await tester.tap(floatingBack());
      await frames(tester);
      await settle(tester, rounds: 1);
      expect(state.currentPosition, before);
      expect(state.chromeVisible, isFalse);
      // Without tap zones, a tap reaching the text would show the bars.
      store.updateSettings(store.settings.copyWith(tapZones: false));
      await tester.pump();
      await tester.tap(floatingBack());
      await tester.pump();
      expect(state.chromeVisible, isFalse);
      expect(state.currentPosition, before);
      expect(find.byType(LibraryBookReaderScreen), findsOneWidget);
      await closeAll(tester, store);
    });

    testWidgets('exactly one Back while reading, opening and after a failure', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      usePhone(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(tester, bookReader(store));
      await settle(tester, rounds: 2);
      final state = bookState(tester);
      expect(state.chromeVisible, isTrue);
      expectOneBack(tester, barsVisible: true);
      await waitForBarsToHide(tester);
      expect(state.chromeVisible, isFalse);
      expectOneBack(tester, barsVisible: false);
      await closeAll(tester, store);

      // A book still opening: the bars stay with their arrow.
      final opening = Completer<LibraryReflowSource>();
      final (second, _) = await createStore(tester);
      await pumpReader(tester, bookReader(second, open: () => opening.future));
      await tester.pump(const Duration(seconds: 6));
      expectOneBack(tester, barsVisible: true);
      await closeAll(tester, second);

      // A book that failed to open: the same, and one tap leaves it.
      final (third, _) = await createStore(tester);
      final navigator = await pumpReader(
        tester,
        bookReader(third, open: () async => throw StateError('worker exited')),
      );
      await tester.pump(const Duration(seconds: 6));
      expect(find.text(en('errorWorker')), findsOneWidget);
      expectOneBack(tester, barsVisible: true);
      await tester.tap(backIn(topBar()));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.byType(LibraryBookReaderScreen), findsNothing);
      expect(navigator.currentState!.canPop(), isFalse);
      await closeAll(tester, third);
      semantics.dispose();
    });
  });

  group('PDF reader', () {
    testWidgets(
      'bars hidden: one tap on the floating Back saves the page and returns '
      'to the screen that opened the PDF',
      (tester) async {
        mockPathProvider();
        usePhone(tester);
        final (store, _) = await createStore(tester);
        final platform = RecordingOrientationPlatform();
        final orientation = LibraryReaderOrientation(
          platform: platform,
          isIOS: true,
        );
        final pops = PopRecorder();
        final navigator = await pumpReader(
          tester,
          pdfReader(store, orientation: orientation),
          opener: StoreWatcher(store: store, progressKey: 'local:pdf'),
          navigatorObservers: <NavigatorObserver>[pops],
        );
        await tester.pump();
        expect(platform.calls, readerOrientationRoundTrip.sublist(0, 2));
        final params = await makePdfReady(tester);
        await waitForBarsToHide(tester);
        expect(floatingBack().hitTestable(), findsOne);
        // The user scrolls to page 7, then leaves within the save delay.
        params.onPageChanged!(7);
        await tester.pump();
        expectReaderCloseAction(
          tester,
          tester
              .state<LibraryPdfReaderScreenState>(
                find.byType(LibraryPdfReaderScreen),
              )
              .gamepadBindings
              .back,
        );

        await tester.tap(floatingBack());
        final saved = store.progressFor('local:pdf')!;
        expect(saved.pageIndex, 6);
        expect(saved.pageCount, 12);
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 120));
        expect(platform.calls, readerOrientationRoundTrip);
        await tester.pump(const Duration(milliseconds: 400));
        expect(find.byType(LibraryPdfReaderScreen), findsNothing);
        expect(pops.popped, hasLength(1));
        expect(find.text('home page:6'), findsOneWidget);
        expect(navigator.currentState!.canPop(), isTrue, reason: 'opener');
        expect(tester.takeException(), isNull);
        await settle(tester, rounds: 2);
        await flushStore(tester, store);
      },
    );

    testWidgets('exactly one Back while opening and while reading', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      mockPathProvider();
      usePhone(tester);
      final (store, _) = await createStore(tester);
      await pumpReader(tester, pdfReader(store));
      await tester.pump();
      // Not ready yet (or failed): the bars stay with their arrow, past
      // the 4 s after which they would hide.
      await tester.pump(const Duration(seconds: 6));
      expectOneBack(tester, barsVisible: true);
      // Ready: the bars, already timed out, give way to the floating Back.
      await makePdfReady(tester);
      await tester.pump(const Duration(milliseconds: 300));
      expectOneBack(tester, barsVisible: false);
      // Shown again (A), then hidden again by themselves.
      tester
          .state<LibraryPdfReaderScreenState>(
            find.byType(LibraryPdfReaderScreen),
          )
          .gamepadBindings
          .select!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expectOneBack(tester, barsVisible: true);
      await waitForBarsToHide(tester);
      expectOneBack(tester, barsVisible: false);
      await closeAll(tester, store);
      semantics.dispose();
    });
  });
}
