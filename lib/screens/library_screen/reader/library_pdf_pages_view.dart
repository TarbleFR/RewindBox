/// The pages mode of the PDF reader (docs/library-books-3d-plan.md § 3.6).
///
/// [LibraryPdfPagesView] shows a PDF one page at a time, or as two-page
/// spreads where [LibraryPageSpreads] says so (landscape in automatic mode,
/// cover alone), turned like a book: a `PageView` of spreads with the
/// [LibraryPageCurlLayer] stacked on top (page curl), a `PageView` slide, or
/// a jump (no animation, Reduce Motion). Every page is drawn from one
/// [LibraryPageTextureCache], keyed by [LibraryPageTextureKey]: the
/// `PageView` items and the curl share the same textures, rendered by
/// [libraryPdfRenderPage] at the pixel size of the page area (the whole
/// view, or half of it for a spread). The spread on screen and its
/// neighbours are kept; renders of the other pages are cancelled. No zoom,
/// no text selection and no links in this mode (the scroll mode keeps
/// them). VoiceOver reads each spread as one image, "Page N of M" or
/// "Pages N and N+1 of M", followed by "Image unavailable" for a page that
/// PDFium could not render.
///
/// The scroll mode lays its pages out in two columns with
/// [libraryPdfSpreadLayout] where the two-page spread applies.
library;

import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_http.dart' show LibraryCancelToken;
import 'package:neostation/services/library_reading_store.dart'
    show LibraryDoublePageMode, LibraryPageTurnStyle;
import 'package:neostation/widgets/library_reduce_motion.dart';

import 'library_page_curl.dart';
import 'library_page_spreads.dart';
import 'library_page_textures.dart';
import 'library_reader_palette.dart';

/// Opens the document of the pages mode (`LibraryPdfReaderScreen`'s test
/// seam: `flutter test` has no PDFium).
typedef LibraryPdfDocumentOpener =
    Future<PdfDocument> Function(String filePath);

/// Opens [filePath] for the pages mode. pdfrx is initialised first (the
/// pages mode opens the file without the viewer, like
/// `LibraryPdfrxInspector`; idempotent), and every page is loaded at once
/// (no progressive loading: the page sizes lay the spreads out, and a page
/// that is not loaded yet would render blank).
Future<PdfDocument> libraryPdfOpenFile(String filePath) async {
  await pdfrxFlutterInitialize();
  return PdfDocument.openFile(filePath);
}

/// Pixel size of a page of [page] points drawn whole (`BoxFit.contain`) in
/// an area of [pixels] physical pixels: whole pixels, at least 1, never
/// larger than the area. Null when the page or the area is empty.
Size? libraryPdfRenderSize(Size page, Size pixels) {
  if (!(page.width > 0) ||
      !(page.height > 0) ||
      !page.isFinite ||
      !pixels.isFinite ||
      pixels.width < 1 ||
      pixels.height < 1) {
    return null;
  }
  final width = pixels.width.floorToDouble();
  final height = pixels.height.floorToDouble();
  // The page is relatively wider than the area: its width fills the area.
  if (page.width * height >= page.height * width) {
    return Size(
      width,
      math.max(1.0, (page.height * width / page.width).floorToDouble()),
    );
  }
  return Size(
    math.max(1.0, (page.width * height / page.height).floorToDouble()),
    height,
  );
}

/// Renders [page] whole in an area of [pixelSize] physical pixels (see
/// [libraryPdfRenderSize]) for a [LibraryPageTextureCache]: PDFium draws the
/// page (`PdfPage.render(fullWidth:, fullHeight:)`), then the pixels become
/// an image (`createImage`) unless [cancel] was cancelled meanwhile (the
/// page left the spreads kept around the one on screen). The [PdfImage] is
/// always disposed. Null when nothing is rendered; errors of PDFium are
/// passed on (the cache counts them as no image).
Future<ui.Image?> libraryPdfRenderPage(
  PdfPage page,
  Size pixelSize,
  LibraryCancelToken cancel,
) async {
  final size = libraryPdfRenderSize(Size(page.width, page.height), pixelSize);
  if (size == null || cancel.isCancelled) return null;
  final rendered = await page.render(
    fullWidth: size.width,
    fullHeight: size.height,
  );
  if (rendered == null) return null;
  try {
    if (cancel.isCancelled) return null;
    return await rendered.createImage();
  } finally {
    rendered.dispose();
  }
}

/// Layout of the scroll mode in two-page spreads (pdfrx `layoutPages`):
/// one row per [LibraryPageSpreads] spread, the pages side by side at the
/// spine (the middle of the document), the cover alone on its book side
/// when [firstPageAlone], the next page on the left when [rightToLeft].
/// Both columns are as wide as the widest page; [PdfViewerParams.margin]
/// separates the rows, the columns and the edges.
PdfPageLayout libraryPdfSpreadLayout(
  List<PdfPage> pages,
  PdfViewerParams params, {
  bool firstPageAlone = true,
  bool rightToLeft = false,
}) {
  final spreads = LibraryPageSpreads(
    pageCount: pages.length,
    doublePage: LibraryDoublePageMode.always,
    firstPageAlone: firstPageAlone,
    rightToLeft: rightToLeft,
  );
  final margin = params.margin;
  final column = pages.fold<double>(
    0,
    (width, page) => math.max(width, page.width),
  );
  // Right edge of the left column.
  final spine = margin + column;
  final rects = List<Rect>.filled(pages.length, Rect.zero);
  var top = margin;
  for (var index = 0; index < spreads.length; index++) {
    final spread = spreads[index];
    final height = spread.pages.fold<double>(
      0,
      (tallest, page) => math.max(tallest, pages[page].height),
    );
    final left = spread.left;
    if (left != null) {
      final page = pages[left];
      rects[left] = Rect.fromLTWH(
        spine - page.width,
        top + (height - page.height) / 2,
        page.width,
        page.height,
      );
    }
    final right = spread.right;
    if (right != null) {
      final page = pages[right];
      rects[right] = Rect.fromLTWH(
        spine + margin,
        top + (height - page.height) / 2,
        page.width,
        page.height,
      );
    }
    top += height + margin;
  }
  return PdfPageLayout(
    pageLayouts: rects,
    documentSize: Size(column * 2 + margin * 3, top),
  );
}

/// The pages mode of the PDF reader (see the library documentation).
///
/// The view keeps the page the reader is at ([LibraryPdfPagesViewState.page],
/// zero-based): it opens at [initialPage], reports every change through
/// [onPageChanged], and lays the spreads out again around it when the
/// layout changes (rotation, settings). A spread that holds the page keeps
/// it; another spread is at its first page, or at the book's last page when
/// it shows that page (the book is then read to the end).
class LibraryPdfPagesView extends StatefulWidget {
  const LibraryPdfPagesView({
    super.key,
    required this.document,
    required this.contentKey,
    required this.initialPage,
    required this.palette,
    required this.onPageChanged,
    required this.onTap,
    this.turnStyle = LibraryPageTurnStyle.curl,
    this.doublePage = LibraryDoublePageMode.auto,
    this.firstPageAlone = true,
    this.rightToLeft = false,
  });

  /// An open document with at least one page.
  final PdfDocument document;

  /// Identity of the pages in the texture keys (the file).
  final Object contentKey;

  /// Zero-based page shown first.
  final int initialPage;
  final LibraryReaderPalette palette;

  /// The page the reader is at changed (zero-based): a turn, a jump.
  final ValueChanged<int> onPageChanged;

  /// A tap on the pages: -1 in the left third, 1 in the right third, 0 in
  /// the middle (the reader decides what it does).
  final ValueChanged<int> onTap;

  /// Page turn; Reduce Motion ([libraryReduceMotion]) always turns without
  /// animation.
  final LibraryPageTurnStyle turnStyle;
  final LibraryDoublePageMode doublePage;
  final bool firstPageAlone;

  /// Right-to-left reading: the next page is on the left.
  final bool rightToLeft;

  /// Turn of the [LibraryPageTurnStyle.slide] style (that of the page
  /// reader).
  static const Duration slideDuration = Duration(milliseconds: 220);

  @override
  State<LibraryPdfPagesView> createState() => LibraryPdfPagesViewState();
}

class LibraryPdfPagesViewState extends State<LibraryPdfPagesView>
    with TickerProviderStateMixin, WidgetsBindingObserver {
  late final LibraryPageCurlController _curl;
  final LibraryPageTextureCache _textures = LibraryPageTextureCache();

  /// Whether the last build enabled the curl layer.
  bool? _curlEnabled;
  PageController? _pages;
  LibraryPageSpreads? _spreads;
  int _layoutGeneration = 0;

  /// Spread on screen.
  int _index = 0;

  /// Page the reader is at (zero-based).
  late int _page;

  /// Spread an animated turn (curl or slide) is heading to.
  int? _turnTarget;
  Size _size = Size.zero;
  double _ratio = 1;
  bool _syncScheduled = false;

  /// Pages (zero-based) whose last render failed or gave no image (not
  /// cancelled): VoiceOver says they are unavailable until a render
  /// succeeds.
  final Set<int> _unavailable = <int>{};

  /// Textures of the pages (shared by the items and the curl; the reader's
  /// trace reads their counters).
  LibraryPageTextureCache get textures => _textures;

  @visibleForTesting
  LibraryPageCurlController get curl => _curl;

  @visibleForTesting
  PageController? get pageController => _pages;

  /// Spreads of the current layout (null before the first layout).
  LibraryPageSpreads? get spreads => _spreads;

  /// Spread on screen.
  int get spreadIndex => _index;

  /// Pages whose image could not be rendered (zero-based).
  @visibleForTesting
  Set<int> get unavailablePages => Set<int>.unmodifiable(_unavailable);

  /// Page the reader is at (zero-based).
  int get page => _page;

  /// Page (zero-based) an animated turn in progress is heading to, null at
  /// rest: a reader that closes meanwhile saves this page.
  int? get turningToPage {
    final target = _turnTarget;
    final spreads = _spreads;
    if (target == null || spreads == null || spreads.isEmpty) return null;
    return _pageShownBy(spreads[target]);
  }

  int get _pageCount => widget.document.pages.length;

  /// Page turn of the last build: [LibraryPdfPagesView.turnStyle], or none
  /// with Reduce Motion ([libraryReduceMotion]; the reader rebuilds the
  /// view when iOS's setting changes).
  LibraryPageTurnStyle _style = LibraryPageTurnStyle.none;

  @override
  void initState() {
    super.initState();
    _curl = LibraryPageCurlController(vsync: this);
    _page = _clampPage(widget.initialPage);
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didUpdateWidget(covariant LibraryPdfPagesView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.document, widget.document) ||
        oldWidget.contentKey != widget.contentKey) {
      // Other pages: nothing of the former document is kept (the curl
      // layer stops a turn when its content changes).
      _turnTarget = null;
      _textures.purge();
      _unavailable.clear();
      _page = _clampPage(widget.initialPage);
      _spreads = null;
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _curl.dispose();
    _pages?.dispose();
    _textures.dispose();
    super.dispose();
  }

  @override
  void didHaveMemoryPressure() {
    // Only the spread on screen stays (its items hold their own handles).
    _textures.purge(keep: _keysOf(_index));
  }

  int _clampPage(int page) {
    final count = _pageCount;
    return count == 0 ? 0 : page.clamp(0, count - 1);
  }

  // ---------------------------------------------------------- navigation --

  /// Turns one spread in reading order: through the page curl when it is on
  /// and can draw the turn, else a slide, else (no animation, Reduce
  /// Motion) a jump. A turn asked while a page curls does nothing (one turn
  /// at a time); false when nothing turns.
  bool turn(LibraryPageTurnDirection direction) {
    final spreads = _spreads;
    final pages = _pages;
    if (spreads == null || spreads.isEmpty || pages == null) return false;
    if (!pages.hasClients || _curl.isActive) return false;
    final forward = direction == LibraryPageTurnDirection.forward;
    final from = _turnTarget ?? _index;
    final target = from + (forward ? 1 : -1);
    if (target < 0 || target >= spreads.length) return false;
    final style = _style;
    final sliding = pages.position.isScrollingNotifier.value;
    if (style == LibraryPageTurnStyle.curl &&
        !sliding &&
        _curl.canTurn(direction)) {
      _turnTarget = target;
      unawaited(
        _curl.turn(direction).then((turned) {
          if (!turned && _turnTarget == target) _turnTarget = null;
        }),
      );
      return true;
    }
    if (style == LibraryPageTurnStyle.none) {
      _turnTarget = null;
      pages.jumpToPage(target);
      return true;
    }
    _turnTarget = target;
    unawaited(
      pages
          .animateToPage(
            target,
            duration: LibraryPdfPagesView.slideDuration,
            curve: Curves.easeOut,
          )
          .whenComplete(() {
            if (_turnTarget == target) _turnTarget = null;
          }),
    );
    return true;
  }

  /// Turns toward the page on [side] of the screen (-1 left, 1 right): the
  /// next one is on the right, or on the left when reading right to left.
  bool turnVisual(int side) {
    final forward = widget.rightToLeft ? side < 0 : side > 0;
    return turn(
      forward
          ? LibraryPageTurnDirection.forward
          : LibraryPageTurnDirection.backward,
    );
  }

  /// Shows the spread of [page] (zero-based, clamped) at once and makes it
  /// the page the reader is at.
  void jumpToPage(int page) {
    if (_pageCount == 0) return;
    final target = _clampPage(page);
    _turnTarget = null;
    if (_curl.isActive) _curl.reset();
    final changed = target != _page;
    _page = target;
    final spreads = _spreads;
    if (spreads != null && !spreads.isEmpty) {
      final index = spreads.spreadOf(target);
      final pages = _pages;
      if (pages != null && pages.hasClients) {
        // Reported by _onPageViewChanged, which keeps the page: its spread
        // holds it.
        if (index != _index) pages.jumpToPage(index);
      } else if (index != _index) {
        setState(() => _newController(index));
      }
    }
    if (changed) widget.onPageChanged(target);
  }

  /// The page a spread shows the reader at (see [LibraryPdfPagesView]).
  int _pageShownBy(LibraryPageSpread spread) {
    if (spread.contains(_page)) return _page;
    final last = _pageCount - 1;
    return spread.contains(last) ? last : spread.first;
  }

  void _onPageViewChanged(int index) {
    final spreads = _spreads;
    if (!mounted || spreads == null || spreads.isEmpty) return;
    final current = index.clamp(0, spreads.length - 1);
    if (_turnTarget == current) _turnTarget = null;
    final page = _pageShownBy(spreads[current]);
    setState(() => _index = current);
    _scheduleSync();
    if (page != _page) {
      _page = page;
      widget.onPageChanged(page);
    }
  }

  /// The page has curled over: the `PageView` jumps under it.
  void _onCurlTurned(int target) => _pages?.jumpToPage(target);

  // -------------------------------------------------------------- layout --

  void _newController(int index) {
    final previous = _pages;
    if (previous != null) {
      // Released after the frame that replaces its PageView.
      WidgetsBinding.instance.addPostFrameCallback((_) => previous.dispose());
    }
    _index = index;
    _turnTarget = null;
    _layoutGeneration++;
    _pages = PageController(initialPage: index);
    _scheduleSync();
  }

  /// Spreads for a view of [size]; a new layout restarts the `PageView` at
  /// the spread of the page the reader is at.
  LibraryPageSpreads _layOut(Size size) {
    final spreads = LibraryPageSpreads(
      pageCount: _pageCount,
      doublePage: widget.doublePage,
      firstPageAlone: widget.firstPageAlone,
      landscape: size.width > size.height,
      rightToLeft: widget.rightToLeft,
    );
    final resized = size != _size;
    _size = size;
    if (spreads == _spreads && _pages != null) {
      // Same spreads, other pixel sizes: other textures.
      if (resized) _scheduleSync();
      return spreads;
    }
    // A turn in progress is stopped by the curl layer itself (other items,
    // other size).
    _spreads = spreads;
    _newController(spreads.isEmpty ? 0 : spreads.spreadOf(_page));
    return spreads;
  }

  // ------------------------------------------------------------ textures --

  /// Pixel size of the area of one page: the whole view, or half of it for
  /// a spread (computed like `LibraryPageCurlLayer`, so that both use the
  /// same textures).
  Size _pixelSizeOf(bool spread) {
    final page = spread ? Size(_size.width / 2, _size.height) : _size;
    return Size(
      (page.width * _ratio).ceilToDouble(),
      (page.height * _ratio).ceilToDouble(),
    );
  }

  LibraryPageTextureKey _keyOf(int page, bool spread) {
    final pixels = _pixelSizeOf(spread);
    return LibraryPageTextureKey(
      widget.contentKey,
      page,
      pixels.width.toInt(),
      pixels.height.toInt(),
    );
  }

  Set<Object> _keysOf(int index) {
    final spreads = _spreads;
    if (spreads == null || index < 0 || index >= spreads.length) {
      return <Object>{};
    }
    final face = LibraryPageCurlFace.of(spreads[index]);
    return <Object>{for (final page in face.pages) _keyOf(page, face.isSpread)};
  }

  Future<ui.Image?> _render(
    int page,
    Size pixelSize,
    LibraryCancelToken cancel,
  ) async {
    final document = widget.document;
    final pages = document.pages;
    if (page < 0 || page >= pages.length) return null;
    try {
      final image = await libraryPdfRenderPage(pages[page], pixelSize, cancel);
      if (!cancel.isCancelled) _rendered(document, page, image != null);
      return image;
    } catch (_) {
      if (!cancel.isCancelled) _rendered(document, page, false);
      rethrow;
    }
  }

  /// Records whether [page] of [document] could be rendered (VoiceOver).
  void _rendered(PdfDocument document, int page, bool success) {
    if (!mounted || !identical(document, widget.document)) return;
    final changed = success
        ? _unavailable.remove(page)
        : _unavailable.add(page);
    if (changed) setState(() {});
  }

  void _scheduleSync() {
    if (_syncScheduled) return;
    _syncScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) => _syncTextures());
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  /// Keeps the spread on screen and its neighbours (rendering those that
  /// are missing, the spread on screen first) and cancels the renders of
  /// every other page.
  void _syncTextures() {
    _syncScheduled = false;
    final spreads = _spreads;
    if (!mounted || spreads == null || spreads.isEmpty || _size.isEmpty) {
      return;
    }
    final wanted = <(int, bool)>[];
    for (final index in <int>[_index, _index + 1, _index - 1]) {
      if (index < 0 || index >= spreads.length) continue;
      final face = LibraryPageCurlFace.of(spreads[index]);
      for (final page in face.pages) {
        wanted.add((page, face.isSpread));
      }
    }
    _textures.retain(<Object>{
      for (final (page, spread) in wanted) _keyOf(page, spread),
    });
    for (final (page, spread) in wanted) {
      final key = _keyOf(page, spread);
      if (_textures.contains(key)) continue;
      final pixels = _pixelSizeOf(spread);
      unawaited(
        _textures.acquire(key, (cancel) => _render(page, pixels, cancel)),
      );
    }
  }

  // --------------------------------------------------------------- build --

  int _zoneOf(double dx, double width) {
    final third = width / 3;
    if (dx < third) return -1;
    if (dx > width - third) return 1;
    return 0;
  }

  @override
  Widget build(BuildContext context) {
    final ratio = MediaQuery.maybeDevicePixelRatioOf(context) ?? 1.0;
    if (ratio != _ratio) {
      _ratio = ratio;
      _scheduleSync();
    }
    _style = libraryReduceMotion(context)
        ? LibraryPageTurnStyle.none
        : widget.turnStyle;
    final curl = _style == LibraryPageTurnStyle.curl;
    if (curl != _curlEnabled) {
      // A curl layer turned off releases what it kept: the spreads around
      // the one on screen are kept again after this frame.
      if (_curlEnabled != null) _scheduleSync();
      _curlEnabled = curl;
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = constraints.biggest;
        final spreads = _layOut(size);
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: (details) =>
              widget.onTap(_zoneOf(details.localPosition.dx, size.width)),
          child: LibraryPageCurlLayer(
            enabled: curl,
            controller: _curl,
            currentIndex: _index,
            itemCount: spreads.length,
            faceOf: (index) => LibraryPageCurlFace.of(spreads[index]),
            render: _render,
            onTurned: _onCurlTurned,
            contentKey: widget.contentKey,
            rightToLeft: widget.rightToLeft,
            paperColor: widget.palette.background,
            cache: _textures,
            child: PageView.builder(
              key: ValueKey<int>(_layoutGeneration),
              controller: _pages,
              reverse: widget.rightToLeft,
              physics: const PageScrollPhysics(parent: ClampingScrollPhysics()),
              itemCount: spreads.length,
              onPageChanged: _onPageViewChanged,
              itemBuilder: (context, index) =>
                  _buildSpread(context, spreads, index),
            ),
          ),
        );
      },
    );
  }

  Widget _buildSpread(
    BuildContext context,
    LibraryPageSpreads spreads,
    int index,
  ) {
    final spread = spreads[index];
    final face = LibraryPageCurlFace.of(spread);
    final second = spread.second;
    final label = second == null
        ? LibraryReaderLocale.format(context, 'pageOfTotal', <String, Object?>{
            'page': spread.first + 1,
            'total': spreads.pageCount,
          })
        : LibraryReaderLocale.format(context, 'pagesOfTotal', <String, Object?>{
            'first': spread.first + 1,
            'second': second + 1,
            'total': spreads.pageCount,
          });
    final pixels = _pixelSizeOf(face.isSpread);
    final pages = widget.document.pages;
    final unavailable = <int>[
      for (final page in spread.pages)
        if (_unavailable.contains(page)) page,
    ];
    final imageUnavailable = LibraryReaderLocale.text(
      context,
      'imageUnavailable',
    );
    // One node per spread: "Page N of M", or "Pages N and N+1 of M", then
    // "Image unavailable" for a page PDFium could not render (in a pair,
    // after that page's number).
    return Semantics(
      container: true,
      image: unavailable.length < spread.pages.length,
      label: <String>[
        label,
        for (final page in unavailable) ...<String>[
          if (second != null)
            LibraryReaderLocale.format(context, 'pageNumber', <String, Object?>{
              'page': page + 1,
            }),
          imageUnavailable,
        ],
      ].join('\n'),
      child: ExcludeSemantics(
        child: ColoredBox(
          color: widget.palette.background,
          child: LibraryPageSpreadLayout(
            face: face,
            pageBuilder: (context, page, alignment) => _LibraryPdfPageImage(
              key: ValueKey<int>(page),
              cache: _textures,
              textureKey: _keyOf(page, face.isSpread),
              render: (cancel) => _render(page, pixels, cancel),
              pageAspect: pages[page].height > 0
                  ? pages[page].width / pages[page].height
                  : null,
              alignment: alignment,
              palette: widget.palette,
              pageNumber: page + 1,
            ),
          ),
        ),
      ),
    );
  }
}

/// One page of a spread: its texture drawn `BoxFit.contain` at [alignment]
/// (as the curl draws it), a blank page of its shape with its number until
/// the texture is rendered. The item keeps its own handle of the image, so
/// a texture evicted or purged meanwhile stays on screen; after a resize it
/// keeps the former image until the new one is rendered.
class _LibraryPdfPageImage extends StatefulWidget {
  const _LibraryPdfPageImage({
    super.key,
    required this.cache,
    required this.textureKey,
    required this.render,
    required this.pageAspect,
    required this.alignment,
    required this.palette,
    required this.pageNumber,
  });

  final LibraryPageTextureCache cache;
  final LibraryPageTextureKey textureKey;
  final LibraryPageTextureRender render;

  /// Width / height of the page, null when unknown.
  final double? pageAspect;
  final Alignment alignment;
  final LibraryReaderPalette palette;

  /// One-based page number.
  final int pageNumber;

  @override
  State<_LibraryPdfPageImage> createState() => _LibraryPdfPageImageState();
}

class _LibraryPdfPageImageState extends State<_LibraryPdfPageImage> {
  ui.Image? _image;
  LibraryPageTextureKey? _shown;
  LibraryPageTextureKey? _requested;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void didUpdateWidget(covariant _LibraryPdfPageImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    // Another size, or a render that was cancelled or failed: asked again.
    if (_shown != widget.textureKey && _requested != widget.textureKey) {
      _load();
    }
  }

  @override
  void dispose() {
    _requested = null;
    _image?.dispose();
    _image = null;
    super.dispose();
  }

  void _load() {
    final key = widget.textureKey;
    final cached = widget.cache.peek(key);
    if (cached != null && !cached.isDisposed) {
      _show(key, cached.image.clone());
      return;
    }
    _requested = key;
    unawaited(
      widget.cache.acquire(key, widget.render).then((texture) {
        if (!mounted || _requested != key) return;
        _requested = null;
        if (texture == null || texture.isDisposed) return;
        setState(() => _show(key, texture.image.clone()));
      }),
    );
  }

  void _show(LibraryPageTextureKey key, ui.Image image) {
    _image?.dispose();
    _image = image;
    _shown = key;
    _requested = null;
  }

  @override
  Widget build(BuildContext context) {
    final image = _image;
    if (image != null) {
      return RawImage(
        image: image,
        fit: BoxFit.contain,
        alignment: widget.alignment,
        filterQuality: FilterQuality.medium,
      );
    }
    final number = Text(
      '${widget.pageNumber}',
      style: TextStyle(
        color: const Color(0xFF000000).withValues(alpha: 0.28),
        fontSize: 28,
        fontWeight: FontWeight.w600,
      ),
    );
    final aspect = widget.pageAspect;
    if (aspect == null || !aspect.isFinite || aspect <= 0) {
      return Center(child: number);
    }
    // PDF pages are drawn on white paper.
    return Align(
      alignment: widget.alignment,
      child: AspectRatio(
        aspectRatio: aspect,
        child: ColoredBox(
          color: const Color(0xFFFFFFFF),
          child: Center(child: number),
        ),
      ),
    );
  }
}
