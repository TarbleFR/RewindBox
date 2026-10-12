// The two modes of the PDF reader (docs/library-books-3d-plan.md § 3.6,
// § 3.9, § 3.10, § 5): which mode opens (session > book > global, pages by
// default), the toggle kept per book and keeping the page, the pages mode
// (pages rendered through the texture cache at the size of the page area,
// renders cancelled outside the spreads kept, curl / slide / none and
// Reduce Motion, spreads in landscape, right to left, tap zones, Back and
// resume), the scroll mode in two columns where the double page applies,
// and the controller (right stick = Fit in the scroll mode only, Y the
// bookmark, X / LB / RB in both modes).
//
// PDFium is not loaded by `flutter test`: the pages mode opens fake
// documents through LibraryPdfReaderScreen.openDocument, whose pages return
// BGRA pixels the way PDFium does; the real libraryPdfRenderPage turns them
// into images in the engine (real time, hence the settle rounds). The
// scroll mode is driven through the pdfrx viewer's own callbacks, as in
// library_reader_back_button_test.dart.
import 'dart:async';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/screens/library_screen/library_pdf_reader_screen.dart';
import 'package:neostation/screens/library_screen/reader/library_page_curl.dart';
import 'package:neostation/screens/library_screen/reader/library_page_textures.dart';
import 'package:neostation/screens/library_screen/reader/library_pdf_pages_view.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_chrome.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_errors.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:pdfrx/pdfrx.dart';

import 'library_reader_test_support.dart';

const String bookKey = 'local:pdf-modes';
const Size portrait = Size(400, 800);
const Size landscape = Size(900, 600);
final String pdfPath = '${Directory.systemTemp.path}/missing-pdf-modes.pdf';

String en(String key) => LibraryReaderLocale.values['en']![key]!;

String enFormat(String key, Map<String, Object> values) {
  var text = en(key);
  values.forEach((name, value) => text = text.replaceAll('{$name}', '$value'));
  return text;
}

/// A rendered page as PDFium gives it (BGRA pixels), recording its use.
class FakePdfImage implements PdfImage {
  FakePdfImage(this.width, this.height)
    : _pixels = Uint8List(width * height * 4)
        ..fillRange(0, width * height * 4, 0xFF);

  @override
  final int width;
  @override
  final int height;
  final Uint8List _pixels;

  /// Reads of the pixels: `createImage` reads them once to decode them.
  int pixelReads = 0;
  bool disposed = false;

  @override
  Uint8List get pixels {
    pixelReads++;
    return _pixels;
  }

  @override
  void dispose() => disposed = true;
}

class FakePdfPage implements PdfPage {
  FakePdfPage(
    this.document,
    this.pageNumber, {
    required this.width,
    required this.height,
  });

  @override
  final FakePdfDocument document;
  @override
  final int pageNumber;
  @override
  final double width;
  @override
  final double height;

  /// Sizes asked (`fullWidth` x `fullHeight`).
  final List<Size> renders = <Size>[];
  final List<FakePdfImage> images = <FakePdfImage>[];

  /// While set, renders wait for it (PDFium still drawing).
  Completer<void>? hold;

  /// Renders give no image.
  bool blank = false;

  /// Renders throw it.
  Object? failure;

  @override
  bool get isLoaded => true;

  @override
  PdfPageRotation get rotation => PdfPageRotation.none;

  @override
  Future<PdfImage?> render({
    int x = 0,
    int y = 0,
    int? width,
    int? height,
    double? fullWidth,
    double? fullHeight,
    int? backgroundColor,
    PdfPageRotation? rotationOverride,
    PdfAnnotationRenderingMode annotationRenderingMode =
        PdfAnnotationRenderingMode.annotationAndForms,
    int flags = PdfPageRenderFlags.none,
    PdfPageRenderCancellationToken? cancellationToken,
  }) async {
    renders.add(Size(fullWidth!, fullHeight!));
    document.renders.add(pageNumber - 1);
    final wait = hold;
    if (wait != null) await wait.future;
    final error = failure;
    if (error != null) throw error;
    if (blank) return null;
    final image = FakePdfImage(fullWidth.toInt(), fullHeight.toInt());
    images.add(image);
    return image;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class FakePdfDocument implements PdfDocument {
  FakePdfDocument(
    int count, {
    Size pageSize = const Size(60, 90),
    this.outline = const <PdfOutlineNode>[],
    Set<int> held = const <int>{},
  }) {
    pages = <PdfPage>[
      for (var i = 0; i < count; i++)
        FakePdfPage(this, i + 1, width: pageSize.width, height: pageSize.height)
          ..hold = held.contains(i) ? Completer<void>() : null,
    ];
  }

  @override
  late List<PdfPage> pages;
  final List<PdfOutlineNode> outline;

  /// Zero-based pages asked to PDFium, in order.
  final List<int> renders = <int>[];
  bool disposed = false;

  FakePdfPage page(int index) => pages[index] as FakePdfPage;

  Iterable<FakePdfImage> get images =>
      pages.expand((page) => (page as FakePdfPage).images);

  @override
  Future<void> dispose() async => disposed = true;

  @override
  Future<List<PdfOutlineNode>> loadOutline() async => outline;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Opens a new fake document at each call (the pages mode opens its own at
/// each visit).
class FakeOpener {
  FakeOpener({
    this.pageCount = 12,
    this.outline = const <PdfOutlineNode>[],
    this.held = const <int>{},
  });

  final int pageCount;
  final List<PdfOutlineNode> outline;

  /// Pages whose renders wait (see [FakePdfPage.hold]).
  final Set<int> held;
  final List<FakePdfDocument> documents = <FakePdfDocument>[];
  final List<String> paths = <String>[];

  /// Thrown instead of opening, when set.
  Object? error;

  FakePdfDocument get last => documents.last;

  Future<PdfDocument> call(String path) async {
    paths.add(path);
    final failure = error;
    if (failure != null) throw failure;
    final document = FakePdfDocument(pageCount, outline: outline, held: held);
    documents.add(document);
    return document;
  }
}

/// The viewer's controller as pdfrx reports it once the document is open.
class FakeViewerController extends PdfViewerController {
  FakeViewerController(this._page);

  final int _page;

  @override
  int? get pageNumber => _page;
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

LibraryPdfReaderScreen pdfReader(
  LibraryReadingStore store,
  FakeOpener opener, {
  String? progressKey = bookKey,
}) => LibraryPdfReaderScreen(
  filePath: pdfPath,
  title: 'Manual',
  progressKey: progressKey,
  store: store,
  openDocument: opener.call,
);

/// Lets the document open and its pages render: the fake pixels are
/// decoded by the engine in real time (a busy runner gets about 3 s).
Future<void> rendered(WidgetTester tester) async {
  for (var round = 0; round < 200; round++) {
    await settle(tester, rounds: 1);
    if (round >= 2 && pagesSettled(tester)) break;
  }
  // The items show the textures that just landed.
  await settle(tester, rounds: 2);
}

/// No reader, a reader in the scroll mode or showing an error, or the pages
/// mode with no render in progress.
bool pagesSettled(WidgetTester tester) {
  final screen = find.byType(LibraryPdfReaderScreen);
  if (screen.evaluate().isEmpty) return true;
  final mode = tester.state<LibraryPdfReaderScreenState>(screen).mode;
  if (mode != LibraryPdfMode.pages) return mode != null;
  if (find.byType(LibraryReaderErrorView).evaluate().isNotEmpty) return true;
  final view = find.byType(LibraryPdfPagesView);
  if (view.evaluate().isEmpty) return false;
  return tester.state<LibraryPdfPagesViewState>(view).textures.pendingRenders ==
      0;
}

Future<GlobalKey<NavigatorState>> openReader(
  WidgetTester tester,
  LibraryReadingStore store,
  FakeOpener opener, {
  String? progressKey = bookKey,
  Widget? below,
}) async {
  final navigator = await pumpReader(
    tester,
    pdfReader(store, opener, progressKey: progressKey),
    opener: below,
  );
  await rendered(tester);
  return navigator;
}

Future<void> closeReader(WidgetTester tester, LibraryReadingStore store) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await settle(tester, rounds: 2);
  await flushStore(tester, store);
}

LibraryPdfReaderScreenState readerOf(WidgetTester tester) => tester
    .state<LibraryPdfReaderScreenState>(find.byType(LibraryPdfReaderScreen));

LibraryPdfPagesViewState pagesOf(WidgetTester tester) =>
    tester.state<LibraryPdfPagesViewState>(find.byType(LibraryPdfPagesView));

LibraryPageCurlLayer curlLayer(WidgetTester tester) =>
    tester.widget<LibraryPageCurlLayer>(find.byType(LibraryPageCurlLayer));

PdfViewer viewerOf(WidgetTester tester) =>
    tester.widget<PdfViewer>(find.byType(PdfViewer));

/// The semantics node of a spread of the pages mode (the page slider has
/// its own "Page N of M").
Finder spreadLabel(String label) => find.descendant(
  of: find.byType(LibraryPdfPagesView),
  matching: find.bySemanticsLabel(label),
);

/// The top bar button with this tooltip.
Finder barButton(String tooltip) => find.byWidgetPredicate(
  (widget) => widget is LibraryReaderIconButton && widget.tooltip == tooltip,
);

void updateGlobal(
  LibraryReadingStore store,
  LibraryReaderSettings Function(LibraryReaderSettings settings) change,
) => store.updateSettings(change(store.settings));

/// Pages (zero-based) whose textures the pages mode keeps.
Set<int> keptPages(LibraryPdfPagesViewState view) => <int>{
  for (final key in view.textures.retained) (key as LibraryPageTextureKey).page,
};

/// Reports the scroll viewer as ready at [page], like pdfrx does.
Future<PdfViewerParams> makeViewerReady(
  WidgetTester tester, {
  int pageCount = 12,
  int page = 1,
}) async {
  final params = viewerOf(tester).params;
  params.onViewerReady!(FakePdfDocument(pageCount), FakeViewerController(page));
  await tester.pump();
  params.onPageChanged!(page);
  await tester.pump();
  return params;
}

/// Runs the pop transition of the reader route to its end.
Future<void> leave(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 120));
  await tester.pump(const Duration(milliseconds: 400));
}

/// Runs a page curl (380 ms) to its end, then the frame that removes it.
Future<void> finishTurn(WidgetTester tester) async {
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 400));
  await tester.pump();
}

void main() {
  setUpReaderEnvironment();

  setUp(() {
    mockPathProvider();
    // The curl draws with its painter here (the shader has its own tests).
    LibraryPageCurlProgram.loader = (_) => throw StateError('painter');
  });
  tearDown(LibraryPageCurlProgram.resetForTesting);

  group('mode', () {
    testWidgets('pages by default, rendered at the size of the page area', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final reader = readerOf(tester);
      expect(reader.mode, LibraryPdfMode.pages);
      expect(reader.ready, isTrue);
      expect(find.byType(LibraryPdfPagesView), findsOneWidget);
      expect(find.byType(PdfViewer), findsNothing);
      expect(opener.paths, <String>[pdfPath]);
      // The page on screen first, then the next one; 60 x 90 pt pages are
      // drawn whole in the 400 x 800 px view.
      final document = opener.last;
      expect(document.renders.take(2), <int>[0, 1]);
      expect(document.page(0).renders, <Size>[const Size(400, 600)]);
      final view = pagesOf(tester);
      expect(keptPages(view), <int>{0, 1});
      expect(view.textures.textures, 2);
      final image = tester.widget<RawImage>(find.byType(RawImage)).image!;
      expect((image.width, image.height), (400, 600));
      expect(tester.takeException(), isNull);
      await closeReader(tester, store);
      expect(document.disposed, isTrue);
    });

    testWidgets('the book\'s mode wins over the global one; other books '
        'follow the global one', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener();
      updateGlobal(store, (s) => s.copyWith(pdfMode: LibraryPdfMode.scroll));
      await openReader(tester, store, opener);
      expect(readerOf(tester).mode, LibraryPdfMode.scroll);
      expect(find.byType(PdfViewer), findsOneWidget);
      expect(find.byType(LibraryPdfPagesView), findsNothing);
      expect(opener.paths, isEmpty, reason: 'the viewer opens its own');
      await closeReader(tester, store);

      store.updateBookSettings(
        bookKey,
        const LibraryReaderBookSettings(pdfMode: LibraryPdfMode.pages),
      );
      await openReader(tester, store, opener);
      expect(readerOf(tester).mode, LibraryPdfMode.pages);
      expect(find.byType(LibraryPdfPagesView), findsOneWidget);
      await closeReader(tester, store);

      updateGlobal(store, (s) => s.copyWith(pdfMode: LibraryPdfMode.pages));
      store.updateBookSettings(
        bookKey,
        const LibraryReaderBookSettings(pdfMode: LibraryPdfMode.scroll),
      );
      await openReader(tester, store, opener);
      expect(readerOf(tester).mode, LibraryPdfMode.scroll);
      await closeReader(tester, store);

      await openReader(tester, store, opener, progressKey: 'local:other');
      expect(readerOf(tester).mode, LibraryPdfMode.pages);
      await closeReader(tester, store);
    });

    testWidgets('toggleMode switches at the page being read and keeps the '
        'choice for this book', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener(pageCount: 30);
      await openReader(tester, store, opener);
      final reader = readerOf(tester);
      reader.gamepadBindings.rightBumper!();
      await rendered(tester);
      expect(reader.pageNumber, 11);

      reader.toggleMode();
      await tester.pump();
      expect(reader.mode, LibraryPdfMode.scroll);
      expect(viewerOf(tester).initialPageNumber, 11);
      expect(find.byType(LibraryPdfPagesView), findsNothing);
      expect(opener.last.disposed, isTrue, reason: 'pages mode closed');
      expect(store.bookSettingsFor(bookKey)?.pdfMode, LibraryPdfMode.scroll);
      expect(store.settings.pdfMode, LibraryPdfMode.pages, reason: 'global');

      // The viewer reaches page 15; back to the pages, at that page.
      final params = await makeViewerReady(tester, pageCount: 30, page: 11);
      params.onPageChanged!(15);
      await tester.pump();
      reader.toggleMode();
      await rendered(tester);
      expect(reader.mode, LibraryPdfMode.pages);
      expect(opener.documents, hasLength(2));
      expect(pagesOf(tester).page, 14);
      expect(pagesOf(tester).pageController!.page, 14);
      expect(reader.pageNumber, 15);
      expect(store.bookSettingsFor(bookKey)?.pdfMode, LibraryPdfMode.pages);

      // Kept for the book: it opens in the scroll mode after a toggle.
      reader.toggleMode();
      await tester.pump();
      await closeReader(tester, store);
      await openReader(tester, store, opener);
      expect(readerOf(tester).mode, LibraryPdfMode.scroll);
      expect(viewerOf(tester).initialPageNumber, 15);
      await closeReader(tester, store);
      // Another book: the global setting.
      await openReader(tester, store, opener, progressKey: 'local:other');
      expect(readerOf(tester).mode, LibraryPdfMode.pages);
      await closeReader(tester, store);
    });

    testWidgets('a choice stored meanwhile replaces the session\'s; without a '
        'progress key the toggle lasts for the session', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final reader = readerOf(tester);
      reader.toggleMode();
      await tester.pump();
      expect(reader.mode, LibraryPdfMode.scroll);
      // The settings sheet stores the pages for this book.
      store.updateBookSettings(
        bookKey,
        store.bookSettingsFor(bookKey)!.copyWith(pdfMode: LibraryPdfMode.pages),
      );
      await rendered(tester);
      expect(reader.mode, LibraryPdfMode.pages);
      expect(find.byType(LibraryPdfPagesView), findsOneWidget);
      await closeReader(tester, store);

      final (other, _) = await createStore(tester);
      await openReader(tester, other, opener, progressKey: null);
      final session = readerOf(tester);
      expect(session.mode, LibraryPdfMode.pages);
      session.toggleMode();
      await tester.pump();
      expect(session.mode, LibraryPdfMode.scroll);
      expect(other.hasPendingChanges, isFalse, reason: 'nothing stored');
      session.toggleMode();
      await rendered(tester);
      expect(session.mode, LibraryPdfMode.pages);
      expect(other.hasPendingChanges, isFalse);
      await closeReader(tester, other);
    });

    testWidgets('a saved page reopens in either mode', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      store.saveProgress(
        libraryPdfProgress(
          key: bookKey,
          pageIndex: 8,
          pageCount: 12,
          title: 'Manual',
        ),
      );
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      expect(pagesOf(tester).page, 8);
      expect(pagesOf(tester).pageController!.page, 8);
      expect(readerOf(tester).pageNumber, 9);
      expect(opener.last.renders.first, 8, reason: 'the saved page first');
      await closeReader(tester, store);

      // Landscape: the spread holding it (pages 8 and 9), at page 9.
      useSurface(tester, size: landscape);
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      expect(view.spreads!.doublePage, isTrue);
      expect(view.spreads![view.spreadIndex].pages, <int>[7, 8]);
      expect(view.page, 8);
      expect(readerOf(tester).pageNumber, 9);
      await closeReader(tester, store);
      expect(store.progressFor(bookKey)!.pageIndex, 8, reason: 'unchanged');

      updateGlobal(store, (s) => s.copyWith(pdfMode: LibraryPdfMode.scroll));
      await openReader(tester, store, opener);
      expect(viewerOf(tester).initialPageNumber, 9);
      await closeReader(tester, store);
    });

    testWidgets('a document that cannot be opened shows why; B leaves', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener()..error = const PdfException('format', 3);
      final navigator = await openReader(tester, store, opener);
      expect(find.text(en('issueCorrupt')), findsOneWidget);
      expect(readerOf(tester).ready, isFalse);
      readerOf(tester).gamepadBindings.back!();
      await leave(tester);
      expect(find.byType(LibraryPdfReaderScreen), findsNothing);
      expect(navigator.currentState!.canPop(), isFalse);
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });
  });

  group('pages mode', () {
    testWidgets('at most five textures while turning; every image disposed '
        'when the reader closes', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      final images = <ui.Image>{};
      void collect() {
        for (final key in view.textures.retained) {
          final texture = view.textures.peek(key);
          if (texture != null) images.add(texture.image);
        }
      }

      collect();
      for (var page = 1; page <= 8; page++) {
        readerOf(tester).gamepadBindings.down!();
        await rendered(tester);
        expect(view.page, page);
        // The page on screen and its neighbours are kept, renders of the
        // others cancelled; the cache holds five textures at most.
        expect(keptPages(view), <int>{page - 1, page, page + 1});
        expect(view.textures.textures, lessThanOrEqualTo(5));
        expect(view.textures.pendingRenders, 0);
        collect();
      }
      expect(images, hasLength(10));
      final document = opener.last;
      await closeReader(tester, store);
      expect(store.progressFor(bookKey)!.location, 'page:8');
      for (final image in images) {
        expect(image.debugDisposed, isTrue);
        expect(image.debugGetOpenHandleStackTraces(), isEmpty);
      }
      expect(document.images, hasLength(greaterThanOrEqualTo(10)));
      expect(document.images.every((image) => image.disposed), isTrue);
      expect(document.disposed, isTrue);
    });

    testWidgets('a page that leaves the spreads kept has its render cancelled: '
        'never decoded, its PDFium image disposed', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      final opener = FakeOpener(pageCount: 30, held: <int>{1});
      await pumpReader(tester, pdfReader(store, opener));
      // Page 2 stays in PDFium: only page 1 can be rendered.
      for (var round = 0; round < 200; round++) {
        await settle(tester, rounds: 1);
        if (round >= 2 &&
            find.byType(LibraryPdfPagesView).evaluate().isNotEmpty &&
            pagesOf(tester).textures.textures == 1) {
          break;
        }
      }
      await settle(tester, rounds: 2);
      final document = opener.last;
      final view = pagesOf(tester);
      expect(document.renders, <int>[0, 1]);
      expect(view.textures.pendingRenders, 1, reason: 'page 2 still drawn');

      readerOf(tester).gamepadBindings.rightBumper!();
      await tester.pump();
      expect(view.page, 10);
      expect(keptPages(view), <int>{9, 10, 11});
      document.page(1).hold!.complete();
      await rendered(tester);
      final abandoned = document.page(1).images.single;
      expect(abandoned.disposed, isTrue);
      expect(abandoned.pixelReads, 0, reason: 'cancelled before createImage');
      expect(view.textures.pendingRenders, 0);
      expect(view.textures.textures, lessThanOrEqualTo(5));
      expect(document.page(10).images.single.pixelReads, 1);
      await closeReader(tester, store);
      expect(document.images.every((image) => image.disposed), isTrue);
    });

    testWidgets('landscape: two-page spreads, the cover alone, half-width '
        'textures; a rotation keeps the page', (tester) async {
      final semantics = tester.ensureSemantics();
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      final reader = readerOf(tester);
      expect(view.spreads!.doublePage, isTrue);
      expect(view.spreads!.length, 7);
      expect(view.spreadIndex, 0);
      // Each page is drawn whole in its half (450 x 600 px).
      final document = opener.last;
      expect(document.page(0).renders, <Size>[const Size(400, 600)]);
      expect(document.page(1).renders, <Size>[const Size(400, 600)]);
      expect(keptPages(view), <int>{0, 1, 2});
      expect(
        spreadLabel(
          enFormat('pageOfTotal', <String, Object>{'page': 1, 'total': 12}),
        ),
        findsOneWidget,
      );

      reader.gamepadBindings.down!();
      await rendered(tester);
      expect(view.spreadIndex, 1);
      expect(reader.pageNumber, 2);
      // Left to right: page 2 on the left, page 3 on the right.
      expect(view.spreads![1].left, 1);
      expect(view.spreads![1].right, 2);
      expect(
        spreadLabel(
          enFormat('pagesOfTotal', <String, Object>{
            'first': 2,
            'second': 3,
            'total': 12,
          }),
        ),
        findsOneWidget,
      );
      // Three spreads kept around a turn.
      expect(keptPages(view), <int>{0, 1, 2, 3, 4});

      // Portrait: one page at a time, at the same page.
      tester.view.physicalSize = portrait;
      await rendered(tester);
      expect(view.spreads!.doublePage, isFalse);
      expect(view.pageController!.page, 1);
      expect(reader.pageNumber, 2);
      // Rendered again for the new page area (400 x 800 px).
      expect(document.page(1).renders, hasLength(2));
      expect(keptPages(view), <int>{0, 1, 2});
      expect(tester.takeException(), isNull);
      semantics.dispose();
      await closeReader(tester, store);
    });

    // Replaces "right to left (store direction)" (maintainer decision,
    // review of the books chantier): a PDF never follows the general page
    // direction. In 440-446 that setting came from the CBZ/manga reader and
    // never applied to PDFs; now that they open in the pages mode, a reader
    // who chose right to left for manga would have had every PDF mirrored.
    // Right to left is chosen for the PDF itself (the book's settings, or
    // the session without a progress key), as EPUB and TXT books have their
    // own direction.
    testWidgets('right to left (the book\'s direction): the next page is on '
        'the left, the left side turns forward; the general direction never '
        'applies', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      // Right to left in general, as chosen for manga.
      updateGlobal(
        store,
        (s) => s.copyWith(
          turnStyle: LibraryPageTurnStyle.none,
          pageDirection: LibraryPageDirection.rtl,
        ),
      );
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isFalse);
      expect(curlLayer(tester).rightToLeft, isFalse);
      expect(pagesOf(tester).spreads![1].left, 1);
      expect(pagesOf(tester).spreads![1].right, 2);
      readerOf(tester).gamepadBindings.right!();
      await tester.pump();
      expect(pagesOf(tester).spreadIndex, 1);
      readerOf(tester).gamepadBindings.left!();
      await tester.pump();
      expect(pagesOf(tester).spreadIndex, 0);
      await closeReader(tester, store);

      // Right to left chosen for this book.
      store.updateBookSettings(
        bookKey,
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.rtl,
        ),
      );
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isTrue);
      expect(curlLayer(tester).rightToLeft, isTrue);
      expect(view.spreads![1].right, 1);
      expect(view.spreads![1].left, 2);
      expect(
        tester
            .widget<LibraryReaderPageSlider>(
              find.byType(LibraryReaderPageSlider),
            )
            .rightToLeft,
        isTrue,
      );
      readerOf(tester).gamepadBindings.left!();
      await tester.pump();
      expect(view.spreadIndex, 1);
      readerOf(tester).gamepadBindings.right!();
      await tester.pump();
      expect(view.spreadIndex, 0);
      await closeReader(tester, store);

      // Left to right for the book: the right side turns forward.
      store.updateBookSettings(
        bookKey,
        const LibraryReaderBookSettings(
          pageDirection: LibraryPageDirection.ltr,
        ),
      );
      await openReader(tester, store, opener);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isFalse);
      readerOf(tester).gamepadBindings.right!();
      await tester.pump();
      expect(pagesOf(tester).spreadIndex, 1);
      await closeReader(tester, store);

      // Without a progress key: left to right as well.
      await openReader(tester, store, opener, progressKey: null);
      expect(tester.widget<PageView>(find.byType(PageView)).reverse, isFalse);
      expect(curlLayer(tester).rightToLeft, isFalse);
      await closeReader(tester, store);
      expect(store.settings.pageDirection, LibraryPageDirection.rtl);
    });

    testWidgets('page curl: the d-pad curls the page, one turn at a time', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      final reader = readerOf(tester);
      expect(curlLayer(tester).enabled, isTrue);
      reader.gamepadBindings.right!();
      expect(view.curl.isActive, isTrue);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(find.byType(LibraryPageCurl), findsOneWidget);
      expect(view.pageController!.page, 0, reason: 'the curl holds the page');
      // Pressed again while the page curls: nothing more.
      reader.gamepadBindings.right!();
      reader.gamepadBindings.down!();
      await finishTurn(tester);
      expect(view.page, 1);
      expect(view.pageController!.page, 1);
      expect(reader.pageNumber, 2);
      expect(find.byType(LibraryPageCurl), findsNothing);
      // Backward.
      reader.gamepadBindings.up!();
      expect(view.curl.isActive, isTrue);
      await finishTurn(tester);
      expect(view.page, 0);
      expect(reader.pageNumber, 1);
      expect(tester.takeException(), isNull);
      await closeReader(tester, store);
    });

    testWidgets('slide: the PageView animates the turn', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.slide),
      );
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      expect(curlLayer(tester).enabled, isFalse);
      readerOf(tester).gamepadBindings.right!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      final page = view.pageController!.page!;
      expect(page, greaterThan(0));
      expect(page, lessThan(1));
      expect(find.byType(LibraryPageCurl), findsNothing);
      await tester.pump(const Duration(milliseconds: 300));
      expect(view.pageController!.page, 1);
      expect(readerOf(tester).pageNumber, 2);
      await closeReader(tester, store);
    });

    testWidgets('another page turn chosen while reading keeps the pages '
        'around the one on screen', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      expect(curlLayer(tester).enabled, isTrue);
      readerOf(tester).gamepadBindings.down!();
      await finishTurn(tester);
      await rendered(tester);
      expect(keptPages(view), <int>{0, 1, 2});
      // The curl layer, turned off, lets go of its pages: they are kept
      // again for the slide, without being rendered twice.
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.slide),
      );
      await rendered(tester);
      expect(curlLayer(tester).enabled, isFalse);
      expect(keptPages(view), <int>{0, 1, 2});
      expect(view.textures.textures, 3);
      expect(opener.last.renders, <int>[0, 1, 2]);
      await closeReader(tester, store);
    });

    testWidgets('no animation, and Reduce Motion whatever the style: the '
        'turn is a jump', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      expect(curlLayer(tester).enabled, isFalse);
      readerOf(tester).gamepadBindings.right!();
      expect(pagesOf(tester).pageController!.page, 1, reason: 'at once');
      expect(readerOf(tester).pageNumber, 2);
      await closeReader(tester, store);

      tester.platformDispatcher.accessibilityFeaturesTestValue =
          const FakeAccessibilityFeatures(disableAnimations: true);
      addTearDown(
        tester.platformDispatcher.clearAccessibilityFeaturesTestValue,
      );
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.curl),
      );
      await openReader(tester, store, opener);
      expect(curlLayer(tester).enabled, isFalse);
      readerOf(tester).gamepadBindings.right!();
      expect(pagesOf(tester).curl.isActive, isFalse);
      expect(pagesOf(tester).pageController!.page, 2, reason: 'at once');
      await tester.pump();
      expect(find.byType(LibraryPageCurl), findsNothing);
      await closeReader(tester, store);
    });

    testWidgets('tap zones turn toward their side; the middle shows or hides '
        'the bars', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final view = pagesOf(tester);
      final reader = readerOf(tester);
      await tester.tapAt(const Offset(390, 400));
      await tester.pump();
      expect(view.page, 1);
      expect(reader.chromeVisible, isFalse, reason: 'hidden by the turn');
      await tester.tapAt(const Offset(10, 400));
      await tester.pump();
      expect(view.page, 0);
      await tester.tapAt(const Offset(200, 400));
      await tester.pump();
      expect(reader.chromeVisible, isTrue);
      await tester.tapAt(const Offset(200, 400));
      await tester.pump();
      expect(reader.chromeVisible, isFalse);
      // Without tap zones, a side shows the bars too.
      updateGlobal(store, (s) => s.copyWith(tapZones: false));
      await tester.pump();
      await tester.tapAt(const Offset(390, 400));
      await tester.pump();
      expect(view.page, 0);
      expect(reader.chromeVisible, isTrue);
      await closeReader(tester, store);
    });

    testWidgets('one tap on the floating Back saves the page reached and '
        'returns to the opener', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener(pageCount: 30);
      final navigator = await openReader(
        tester,
        store,
        opener,
        below: StoreWatcher(store: store, progressKey: bookKey),
      );
      final reader = readerOf(tester);
      reader.gamepadBindings.rightBumper!();
      await rendered(tester);
      expect(reader.pageNumber, 11);
      // The jump hid the bars: the floating Back is offered.
      await tester.pump(const Duration(milliseconds: 300));
      expect(reader.chromeVisible, isFalse);
      final back = find.byType(LibraryReaderFloatingBackButton);
      expect(back.hitTestable(), findsOneWidget);
      await tester.tap(back);
      expect(store.progressFor(bookKey)!.pageIndex, 10);
      await leave(tester);
      expect(find.byType(LibraryPdfReaderScreen), findsNothing);
      expect(find.text('home page:10'), findsOneWidget);
      expect(navigator.currentState!.canPop(), isTrue, reason: 'opener');
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
      expect(opener.last.disposed, isTrue);
    });

    testWidgets('a page curling when the reader closes is saved as turned', (
      tester,
    ) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      final opener = FakeOpener();
      await openReader(tester, store, opener);
      final reader = readerOf(tester);
      reader.gamepadBindings.right!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));
      expect(pagesOf(tester).curl.isActive, isTrue);
      expect(pagesOf(tester).page, 0);
      reader.gamepadBindings.back!();
      expect(store.progressFor(bookKey)!.pageIndex, 1);
      await leave(tester);
      expect(find.byType(LibraryPdfReaderScreen), findsNothing);
      await settle(tester, rounds: 2);
      await flushStore(tester, store);
    });
  });

  group('scroll mode', () {
    testWidgets('two columns where the double page applies', (tester) async {
      useSurface(tester, size: landscape);
      final (store, _) = await createStore(tester);
      updateGlobal(store, (s) => s.copyWith(pdfMode: LibraryPdfMode.scroll));
      await openReader(tester, store, FakeOpener());
      expect(viewerOf(tester).params.margin, 4);
      final layout = viewerOf(tester).params.layoutPages;
      expect(layout, isNotNull, reason: 'landscape, automatic double page');
      final pages = FakePdfDocument(5).pages;
      final result = layout!(pages, viewerOf(tester).params);
      // The cover alone on the right, then pages 2 and 3, 4 and 5 side by
      // side at the spine.
      expect(result.pageLayouts, <Rect>[
        const Rect.fromLTWH(68, 4, 60, 90),
        const Rect.fromLTWH(4, 98, 60, 90),
        const Rect.fromLTWH(68, 98, 60, 90),
        const Rect.fromLTWH(4, 192, 60, 90),
        const Rect.fromLTWH(68, 192, 60, 90),
      ]);
      expect(result.documentSize, const Size(132, 286));

      // Portrait: pdfrx's single column.
      tester.view.physicalSize = portrait;
      await tester.pump();
      expect(viewerOf(tester).params.layoutPages, isNull);
      updateGlobal(
        store,
        (s) => s.copyWith(doublePage: LibraryDoublePageMode.always),
      );
      await tester.pump();
      expect(viewerOf(tester).params.layoutPages, isNotNull);
      tester.view.physicalSize = landscape;
      updateGlobal(
        store,
        (s) => s.copyWith(doublePage: LibraryDoublePageMode.never),
      );
      await tester.pump();
      expect(viewerOf(tester).params.layoutPages, isNull);
      await closeReader(tester, store);
    });

    test('the spread layout: right to left, and without the cover alone', () {
      final pages = FakePdfDocument(3).pages;
      const params = PdfViewerParams(margin: 4);
      final rtl = libraryPdfSpreadLayout(pages, params, rightToLeft: true);
      // The cover alone on the left, then page 2 on the right, 3 on the left.
      expect(rtl.pageLayouts, <Rect>[
        const Rect.fromLTWH(4, 4, 60, 90),
        const Rect.fromLTWH(68, 98, 60, 90),
        const Rect.fromLTWH(4, 98, 60, 90),
      ]);
      final pairs = libraryPdfSpreadLayout(
        pages,
        params,
        firstPageAlone: false,
      );
      expect(pairs.pageLayouts, <Rect>[
        const Rect.fromLTWH(4, 4, 60, 90),
        const Rect.fromLTWH(68, 4, 60, 90),
        const Rect.fromLTWH(4, 98, 60, 90),
      ]);
      // Pages of other sizes: the columns are as wide as the widest page,
      // each page at the spine and centred in its row.
      final mixed = FakePdfDocument(3).pages
        ..[1] = FakePdfPage(FakePdfDocument(0), 2, width: 80, height: 50);
      final sized = libraryPdfSpreadLayout(mixed, params);
      expect(sized.pageLayouts[0], const Rect.fromLTWH(88, 4, 60, 90));
      expect(sized.pageLayouts[1], const Rect.fromLTWH(4, 118, 80, 50));
      expect(sized.pageLayouts[2], const Rect.fromLTWH(88, 98, 60, 90));
      expect(sized.documentSize, const Size(172, 192));
    });
  });

  group('controller', () {
    // Phase 7 (docs/library-books-3d-plan.md § 3.10) gives Y its role: it
    // was left free ("Y is free", `y` null in both modes) until the
    // bookmarks came; it now adds or removes the bookmark of the page shown
    // in both modes, which replaces those two `isNull` expectations.
    testWidgets('the right stick click fits the page in the scroll mode only; '
        'Y is the bookmark in both modes', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      await openReader(tester, store, FakeOpener());
      final reader = readerOf(tester);
      expect(reader.mode, LibraryPdfMode.pages);
      expect(reader.gamepadBindings.rightStickClick, isNull);
      expect(barButton(en('fitPage')), findsNothing);
      reader.gamepadBindings.y!();
      await tester.pump();
      expect(store.bookmarkAt(bookKey, 'page:0')?.pageIndex, 0);

      reader.toggleMode();
      await tester.pump();
      await makeViewerReady(tester);
      final fit = tester.widget<LibraryReaderIconButton>(
        barButton(en('fitPage')),
      );
      expect(reader.gamepadBindings.rightStickClick, isNotNull);
      // The binding is the Fit button's action (formerly on Y).
      expect(reader.gamepadBindings.rightStickClick, fit.onPressed);
      // The same page in the scroll mode: Y removes its bookmark.
      reader.gamepadBindings.y!();
      await tester.pump();
      expect(store.bookmarksFor(bookKey), isEmpty);
      await closeReader(tester, store);
    });

    testWidgets('X opens the table of contents and LB/RB move ten pages in '
        'both modes', (tester) async {
      useSurface(tester, size: portrait);
      final (store, _) = await createStore(tester);
      updateGlobal(
        store,
        (s) => s.copyWith(turnStyle: LibraryPageTurnStyle.none),
      );
      final opener = FakeOpener(
        pageCount: 30,
        outline: const <PdfOutlineNode>[
          PdfOutlineNode(
            title: 'Preface',
            dest: PdfDest(1, PdfDestCommand.fit, null),
            children: <PdfOutlineNode>[],
          ),
          PdfOutlineNode(
            title: 'Chapter 2',
            dest: PdfDest(7, PdfDestCommand.fit, null),
            children: <PdfOutlineNode>[],
          ),
        ],
      );
      await openReader(tester, store, opener);
      final reader = readerOf(tester);
      final toc = tester.widget<LibraryReaderIconButton>(
        barButton(en('tableOfContents')),
      );
      expect(reader.gamepadBindings.x, toc.onPressed);
      reader.gamepadBindings.x!();
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.text(en('tableOfContents')), findsWidgets);
      await tester.tap(find.text('Chapter 2'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(reader.pageNumber, 7);
      expect(pagesOf(tester).page, 6);

      reader.gamepadBindings.rightBumper!();
      await tester.pump();
      expect(reader.pageNumber, 17);
      expect(pagesOf(tester).pageController!.page, 16);
      reader.gamepadBindings.leftBumper!();
      await tester.pump();
      expect(reader.pageNumber, 7);
      reader.gamepadBindings.leftBumper!();
      await tester.pump();
      expect(reader.pageNumber, 1, reason: 'clamped to the first page');

      // The scroll mode keeps the same actions.
      reader.toggleMode();
      await tester.pump();
      await makeViewerReady(tester, pageCount: 30);
      final scrollToc = tester.widget<LibraryReaderIconButton>(
        barButton(en('tableOfContents')),
      );
      expect(reader.gamepadBindings.x, scrollToc.onPressed);
      expect(reader.gamepadBindings.leftBumper, isNotNull);
      expect(reader.gamepadBindings.rightBumper, isNotNull);
      await closeReader(tester, store);
    });
  });

  group('rendering a page', () {
    test('the whole page in the area, in whole pixels', () {
      expect(
        libraryPdfRenderSize(const Size(60, 90), const Size(400, 800)),
        const Size(400, 600),
      );
      expect(
        libraryPdfRenderSize(const Size(60, 90), const Size(450, 600)),
        const Size(400, 600),
      );
      expect(
        libraryPdfRenderSize(const Size(90, 60), const Size(400, 800)),
        const Size(400, 266),
      );
      // An A4 page on an iPhone 15 Pro in portrait.
      expect(
        libraryPdfRenderSize(const Size(595, 842), const Size(1179, 2556)),
        const Size(1179, 1668),
      );
      expect(libraryPdfRenderSize(Size.zero, const Size(400, 800)), isNull);
      expect(libraryPdfRenderSize(const Size(60, 90), Size.zero), isNull);
      expect(
        libraryPdfRenderSize(const Size(double.nan, 90), const Size(4, 8)),
        isNull,
      );
    });

    test('drawn at that size, decoded, its PDFium image disposed', () async {
      final page = FakePdfDocument(1).page(0);
      final image = await libraryPdfRenderPage(
        page,
        const Size(400, 800),
        LibraryCancelToken(),
      );
      expect(page.renders, <Size>[const Size(400, 600)]);
      expect((image!.width, image.height), (400, 600));
      expect(page.images.single.pixelReads, 1);
      expect(page.images.single.disposed, isTrue);
      image.dispose();
    });

    test('cancelled while PDFium draws: never decoded, always freed', () async {
      final page = FakePdfDocument(1).page(0)..hold = Completer<void>();
      final cancel = LibraryCancelToken();
      final result = libraryPdfRenderPage(page, const Size(400, 800), cancel);
      await Future<void>.delayed(Duration.zero);
      expect(page.renders, hasLength(1));
      cancel.cancel();
      page.hold!.complete();
      expect(await result, isNull);
      expect(page.images.single.pixelReads, 0);
      expect(page.images.single.disposed, isTrue);
    });

    test(
      'nothing asked of PDFium once cancelled or for an empty area',
      () async {
        final page = FakePdfDocument(1).page(0);
        final cancelled = LibraryCancelToken()..cancel();
        expect(
          await libraryPdfRenderPage(page, const Size(400, 800), cancelled),
          isNull,
        );
        expect(
          await libraryPdfRenderPage(page, Size.zero, LibraryCancelToken()),
          isNull,
        );
        expect(page.renders, isEmpty);
      },
    );

    test('no image from PDFium gives none; a PDFium error is passed on, and '
        'the texture cache counts it as no image', () async {
      final blank = FakePdfDocument(1).page(0)..blank = true;
      expect(
        await libraryPdfRenderPage(
          blank,
          const Size(400, 800),
          LibraryCancelToken(),
        ),
        isNull,
      );
      final failing = FakePdfDocument(1).page(0)
        ..failure = const PdfException('FPDF_LoadPage(1) failed.');
      await expectLater(
        libraryPdfRenderPage(
          failing,
          const Size(400, 800),
          LibraryCancelToken(),
        ),
        throwsA(isA<PdfException>()),
      );
      final cache = LibraryPageTextureCache();
      addTearDown(cache.dispose);
      final texture = await cache.acquire(
        'failing',
        (cancel) => libraryPdfRenderPage(failing, const Size(400, 800), cancel),
      );
      expect(texture, isNull);
      expect(cache.textures, 0);
    });
  });
}
