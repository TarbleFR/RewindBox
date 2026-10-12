import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_local_models.dart'
    show LibraryBookException, LibraryBookIssue;
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'reader/library_page_curl.dart' show LibraryPageTurnDirection;
import 'reader/library_pdf_pages_view.dart';
import 'reader/library_reader_chrome.dart';
import 'reader/library_reader_effective_settings.dart';
import 'reader/library_reader_errors.dart';
import 'reader/library_reader_gamepad.dart';
import 'reader/library_reader_palette.dart';
import 'reader/library_reader_sheets.dart';
import 'reader/library_reader_system.dart';

/// Full-screen PDF reader (local library books and Library downloads), in
/// two modes (docs/library-books-3d-plan.md § 3.6):
///
/// * [LibraryPdfMode.pages]: one page, or a two-page spread where the
///   double page applies (landscape in automatic mode), turned like a book
///   ([LibraryPdfPagesView]: page curl, slide or no animation). No zoom,
///   text selection or links in this mode.
/// * [LibraryPdfMode.scroll]: the continuous, zoomable pdfrx viewer of
///   Build 440, in two columns where the double page applies.
///
/// The mode is the one chosen for this session
/// ([LibraryPdfReaderScreenState.toggleMode]), else the book's
/// (`LibraryReaderBookSettings.pdfMode`), else the global reader setting
/// (pages by default). Pages are drawn edge to edge; the chrome stays inside
/// the safe area. With a [progressKey] the page is restored and saved
/// (`page:N`, in both modes; debounced, and when the app goes to the
/// background or the reader closes).
class LibraryPdfReaderScreen extends StatefulWidget {
  const LibraryPdfReaderScreen({
    super.key,
    required this.filePath,
    required this.title,
    this.progressKey,
    this.subtitle,
    this.store,
    this.orientation,
    this.openDocument,
  });

  final String filePath;
  final String title;

  /// Key in [LibraryReadingStore]; null reads without saving the position.
  final String? progressKey;
  final String? subtitle;
  final LibraryReadingStore? store;
  final LibraryReaderOrientation? orientation;

  /// Opens the document of the pages mode; null uses [libraryPdfOpenFile]
  /// (test seam: `flutter test` has no PDFium). The scroll mode keeps the
  /// viewer's own loading.
  final LibraryPdfDocumentOpener? openDocument;

  @override
  State<LibraryPdfReaderScreen> createState() => LibraryPdfReaderScreenState();
}

/// Progress of a PDF page (zero-based [pageIndex] of [pageCount]).
@visibleForTesting
LibraryReadingProgress libraryPdfProgress({
  required String key,
  required int pageIndex,
  required int pageCount,
  required String title,
  String? subtitle,
}) {
  final count = pageCount < 1 ? 1 : pageCount;
  final page = pageIndex.clamp(0, count - 1);
  return LibraryReadingProgress(
    key: key,
    location: LibraryReadingProgress.pageLocation(page),
    fraction: (page + 1) / count,
    pageIndex: page,
    pageCount: count,
    title: title,
    subtitle: subtitle,
  );
}

/// One-based page to open from saved progress (1 when nothing is saved).
@visibleForTesting
int libraryPdfInitialPage(LibraryReadingProgress? progress) {
  final index = progress?.pageIndex ?? progress?.locationPage;
  if (index == null || index < 0) return 1;
  return index + 1;
}

class LibraryPdfReaderScreenState extends State<LibraryPdfReaderScreen>
    with WidgetsBindingObserver {
  late final LibraryReadingStore _store;
  late final LibraryReaderChromeController _chrome;
  late final LibraryReaderSystemSession _system;
  late LibraryReaderSettings _settings;

  /// Navigation settings of this book (null: the global settings).
  LibraryReaderBookSettings? _book;

  /// Mode chosen by [toggleMode] for this session; dropped when the stored
  /// choice changes (the settings sheet, another reader).
  LibraryPdfMode? _sessionMode;

  /// Mode on screen; null until the store is read.
  LibraryPdfMode? _mode;
  bool _reduceMotion = false;

  // Scroll mode: one controller per viewer (a closing viewer detaches its
  // controller).
  PdfViewerController _viewer = PdfViewerController();

  // Pages mode.
  final GlobalKey<LibraryPdfPagesViewState> _pagesKey =
      GlobalKey<LibraryPdfPagesViewState>();
  PdfDocument? _document;
  Object? _openError;
  int _openGeneration = 0;

  /// One-based page the reader is at (both modes).
  final ValueNotifier<int> _page = ValueNotifier<int>(1);
  int _pageCount = 0;
  bool _ready = false;
  bool _storeLoaded = false;
  int _initialPage = 1;
  Timer? _saveTimer;
  bool _dirty = false;
  bool _closing = false;

  /// The route was popped: the saved page no longer changes.
  bool _leaving = false;
  bool _sliderDragging = false;
  int? _reportedPage;

  /// Controller actions (docs/library-books-3d-plan.md § 3.10): the d-pad
  /// turns the page (in the pages mode through the page curl when it is on;
  /// left and right follow the screen, right to left books turn forward to
  /// the left), LB/RB move ten pages and X opens the table of contents in
  /// both modes; the right stick click fits the page, in the scroll mode
  /// only. Y is not bound (the bookmarks come later).
  @visibleForTesting
  LibraryReaderGamepadBindings get gamepadBindings =>
      LibraryReaderGamepadBindings(
        left: () => _turnSide(-1),
        right: () => _turnSide(1),
        up: () => _turnBy(-1),
        down: () => _turnBy(1),
        leftBumper: () => _goRelative(-10),
        rightBumper: () => _goRelative(10),
        select: _chrome.toggle,
        back: _close,
        x: _openOutline,
        start: _openSettings,
        rightStickClick: _mode == LibraryPdfMode.scroll ? _fitPage : null,
      );

  /// Mode on screen (null before the reading store is read).
  @visibleForTesting
  LibraryPdfMode? get mode => _mode;

  /// One-based page the reader is at.
  @visibleForTesting
  int get pageNumber => _page.value;

  /// The document (pages mode) or the viewer (scroll mode) is ready.
  @visibleForTesting
  bool get ready => _ready;

  @visibleForTesting
  bool get chromeVisible => _chrome.visible;

  @override
  void initState() {
    super.initState();
    _store = widget.store ?? LibraryReadingStore.instance;
    _settings = _store.settings;
    _chrome = LibraryReaderChromeController();
    _system = LibraryReaderSystemSession(orientation: widget.orientation);
    _store.addListener(_onStore);
    WidgetsBinding.instance.addObserver(this);
    unawaited(_start());
  }

  Future<void> _start() async {
    try {
      await _store.load();
    } catch (_) {}
    if (!mounted) return;
    final key = widget.progressKey;
    setState(() {
      _settings = _store.settings;
      _book = key == null ? null : _store.bookSettingsFor(key);
      _initialPage = key == null
          ? 1
          : libraryPdfInitialPage(_store.progressFor(key));
      _page.value = _initialPage;
      _storeLoaded = true;
    });
    _syncMode();
    unawaited(_system.start(_settings));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // VoiceOver: the bars stay until the user hides them.
    _chrome.accessibleNavigation = MediaQuery.accessibleNavigationOf(context);
    // Reduce Motion: the pages mode turns without animation.
    _reduceMotion = MediaQuery.disableAnimationsOf(context);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _saveNow();
    _saveTimer?.cancel();
    _store.removeListener(_onStore);
    _chrome.dispose();
    _page.dispose();
    _closeDocument();
    unawaited(_system.stop());
    unawaited(_store.flush().catchError((Object _) {}));
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      _commitTurnInFlight();
      _saveNow();
      unawaited(_store.flush().catchError((Object _) {}));
    }
  }

  void _onStore() {
    if (!mounted) return;
    final settings = _store.settings;
    final key = widget.progressKey;
    final book = key == null ? null : _store.bookSettingsFor(key);
    if (settings == _settings && book == _book) return;
    final previous = _settings;
    final stored = _storedMode;
    setState(() {
      _settings = settings;
      _book = book;
    });
    if (_storedMode != stored) _sessionMode = null;
    _syncMode();
    if (settings != previous) _system.update(settings);
  }

  // ---------------------------------------------------------------- mode --

  /// The book's choice, else the global one.
  LibraryPdfMode get _storedMode => _book?.pdfMode ?? _settings.pdfMode;

  LibraryReaderEffectiveSettings get _effective =>
      LibraryReaderEffectiveSettings.resolve(
        global: _settings,
        book: _book,
        session: _reduceMotion
            ? const LibraryReaderSessionOverrides(
                turnStyle: LibraryPageTurnStyle.none,
              )
            : null,
      );

  /// Switches between the pages and the scroll mode at the page being read
  /// (the mode button of the toolbar). The choice is kept for this book
  /// (`bookSettings[progressKey].pdfMode`); without a progress key it lasts
  /// for this session.
  void toggleMode() {
    final current = _mode;
    if (current == null || !mounted) return;
    _commitTurnInFlight();
    final next = current == LibraryPdfMode.pages
        ? LibraryPdfMode.scroll
        : LibraryPdfMode.pages;
    _sessionMode = next;
    final key = widget.progressKey;
    if (key != null) {
      final book =
          _store.bookSettingsFor(key) ?? const LibraryReaderBookSettings();
      _store.updateBookSettings(key, book.copyWith(pdfMode: next));
    }
    _syncMode();
  }

  /// Shows the mode resolved from the session, the book and the global
  /// settings; a new mode opens at the page being read.
  void _syncMode() {
    if (!mounted || !_storeLoaded) return;
    final mode = _sessionMode ?? _storedMode;
    if (mode == _mode) return;
    setState(() {
      _mode = mode;
      _ready = false;
      _reportedPage = null;
      _initialPage = _page.value;
      if (mode == LibraryPdfMode.scroll) _viewer = PdfViewerController();
    });
    if (mode == LibraryPdfMode.pages) {
      unawaited(_openDocument());
    } else {
      _closeDocument();
    }
  }

  /// Opens the document of the pages mode (the scroll viewer opens its own).
  Future<void> _openDocument() async {
    final generation = ++_openGeneration;
    if (_openError != null) setState(() => _openError = null);
    final PdfDocument document;
    try {
      document = await (widget.openDocument ?? libraryPdfOpenFile)(
        widget.filePath,
      );
    } catch (error) {
      if (!mounted || generation != _openGeneration) return;
      setState(() => _openError = error);
      return;
    }
    if (!mounted ||
        generation != _openGeneration ||
        _mode != LibraryPdfMode.pages) {
      // The reader left the pages mode (or closed) meanwhile.
      unawaited(_disposeDocument(document));
      return;
    }
    final count = document.pages.length;
    if (count == 0) {
      unawaited(_disposeDocument(document));
      setState(
        () =>
            _openError = const LibraryBookException(LibraryBookIssue.noContent),
      );
      return;
    }
    setState(() {
      _document = document;
      _pageCount = count;
      _ready = true;
      _page.value = _page.value.clamp(1, count);
    });
  }

  /// Closes the document of the pages mode and forgets an open in progress.
  void _closeDocument() {
    _openGeneration++;
    _openError = null;
    final document = _document;
    _document = null;
    if (document != null) unawaited(_disposeDocument(document));
  }

  static Future<void> _disposeDocument(PdfDocument document) async {
    try {
      await document.dispose();
    } catch (_) {}
  }

  LibraryPdfPagesViewState? get _pagesView =>
      _mode == LibraryPdfMode.pages && _ready ? _pagesKey.currentState : null;

  // ------------------------------------------------------------ progress --

  void _close() {
    if (_closing || !mounted) return;
    _closing = true;
    _commitTurnInFlight();
    // Saved before the pop, while the screens below can rebuild for it.
    _saveNow();
    Navigator.of(context).maybePop().then((popped) {
      if (!popped) _closing = false;
    });
  }

  /// The route was popped (Back, B, the iOS back swipe): the screen below
  /// is on stage from now on, so landscape is restored now rather than in
  /// [dispose], after the reverse transition, and the page is saved now
  /// (from [dispose], the store would notify the screens below while the
  /// widget tree is locked). Pages reported by the closing viewer (laid
  /// out again in landscape) are ignored. [dispose] stays the fallback
  /// (the session stops once).
  void _onPopped(bool didPop, Object? _) {
    if (!didPop) return;
    _commitTurnInFlight();
    _saveNow();
    _leaving = true;
    unawaited(_system.stop());
  }

  /// A page turning when the reader closes, goes to the background or
  /// switches modes counts as turned: its page is saved, not the one being
  /// left.
  void _commitTurnInFlight() {
    if (_leaving) return;
    final target = _pagesView?.turningToPage;
    if (target == null || target + 1 == _page.value) return;
    _page.value = target + 1;
    _dirty = true;
  }

  /// Page reported by the pdfrx viewer (scroll mode).
  void _onPageChanged(int? pageNumber) {
    if (pageNumber == null || _leaving) return;
    final turned = _reportedPage != null && _reportedPage != pageNumber;
    _reportedPage = pageNumber;
    // The first report is the initial page: the chrome stays for a moment.
    _pageReached(pageNumber, turned: turned);
  }

  /// Zero-based page reported by the pages mode (a turn or a jump).
  void _onPagesPageChanged(int page) {
    if (_leaving) return;
    _pageReached(page + 1, turned: true);
  }

  void _pageReached(int pageNumber, {required bool turned}) {
    _page.value = pageNumber;
    if (turned && !_sliderDragging) _chrome.hideAfterTurn();
    if (widget.progressKey == null) return;
    _dirty = true;
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 700), _saveNow);
  }

  void _saveNow() {
    _saveTimer?.cancel();
    _saveTimer = null;
    final key = widget.progressKey;
    if (!_dirty || key == null || _pageCount == 0) return;
    _dirty = false;
    _store.saveProgress(
      libraryPdfProgress(
        key: key,
        pageIndex: _page.value - 1,
        pageCount: _pageCount,
        title: widget.title,
        subtitle: widget.subtitle,
      ),
    );
  }

  // ---------------------------------------------------------- navigation --

  /// D-pad left/right: the page on that side (pages mode), the previous or
  /// next page (scroll mode).
  void _turnSide(int side) {
    if (_mode == LibraryPdfMode.pages) {
      _pagesView?.turnVisual(side);
      return;
    }
    _goRelative(side);
  }

  /// D-pad up/down: the previous or next page.
  void _turnBy(int delta) {
    if (_mode == LibraryPdfMode.pages) {
      _pagesView?.turn(
        delta > 0
            ? LibraryPageTurnDirection.forward
            : LibraryPageTurnDirection.backward,
      );
      return;
    }
    _goRelative(delta);
  }

  void _goRelative(int delta) {
    if (!_ready) return;
    if (_mode == LibraryPdfMode.pages) {
      _pagesView?.jumpToPage(_page.value - 1 + delta);
      return;
    }
    if (!_viewer.isReady) return;
    final target = (_page.value + delta).clamp(1, _viewer.pageCount);
    unawaited(_viewer.goToPage(pageNumber: target));
  }

  void _goToPage(int pageNumber) {
    if (!_ready) return;
    if (_mode == LibraryPdfMode.pages) {
      _pagesView?.jumpToPage(pageNumber - 1);
      return;
    }
    if (!_viewer.isReady) return;
    unawaited(
      _viewer.goToPage(
        pageNumber: pageNumber.clamp(1, _viewer.pageCount),
        duration: Duration.zero,
      ),
    );
  }

  /// "Fit": the scroll mode only (the pages mode always shows whole pages).
  void _fitPage() {
    if (_mode != LibraryPdfMode.scroll || !_ready || !_viewer.isReady) return;
    final matrix = _viewer.calcMatrixForFit(pageNumber: _page.value);
    if (matrix != null) unawaited(_viewer.goTo(matrix));
  }

  /// A tap on the pages: a side third turns toward it (tap zones), the
  /// middle (or any tap without tap zones) shows or hides the chrome.
  void _onPagesTap(int zone) {
    if (zone == 0 || !_settings.tapZones) {
      _chrome.toggle();
      return;
    }
    if (_chrome.visible) _chrome.hide();
    _turnSide(zone);
  }

  Future<void> _openOutline() async {
    if (!_ready) return;
    final PdfDocument document;
    if (_mode == LibraryPdfMode.pages) {
      final open = _document;
      if (open == null) return;
      document = open;
    } else {
      if (!_viewer.isReady) return;
      document = _viewer.document;
    }
    _chrome.hold();
    try {
      List<PdfOutlineNode> outline;
      try {
        outline = await document.loadOutline();
      } catch (_) {
        outline = const <PdfOutlineNode>[];
      }
      if (!mounted) return;
      final entries = <LibraryReaderListEntry>[];
      final destinations = <PdfDest?>[];
      void visit(List<PdfOutlineNode> nodes, int depth) {
        for (final node in nodes) {
          final dest = node.dest;
          entries.add(
            LibraryReaderListEntry(
              title: node.title.trim().isEmpty ? '—' : node.title.trim(),
              depth: depth,
              enabled: dest != null,
              trailing: dest == null ? null : '${dest.pageNumber}',
            ),
          );
          destinations.add(dest);
          visit(node.children, depth + 1);
        }
      }

      visit(outline, 0);
      var current = -1;
      for (var i = 0; i < destinations.length; i++) {
        final dest = destinations[i];
        if (dest != null && dest.pageNumber <= _page.value) current = i;
      }
      final index = await showLibraryReaderListSheet(
        context,
        palette: _palette(context),
        title: LibraryReaderLocale.text(context, 'tableOfContents'),
        entries: entries,
        currentIndex: current < 0 ? null : current,
        emptyMessage: LibraryReaderLocale.text(context, 'noTableOfContents'),
      );
      if (index == null || !mounted) return;
      final dest = destinations[index];
      if (dest == null) return;
      if (_mode == LibraryPdfMode.pages) {
        _goToPage(dest.pageNumber);
      } else if (_viewer.isReady) {
        unawaited(_viewer.goToDest(dest));
      }
    } finally {
      if (mounted) _chrome.release();
    }
  }

  Future<void> _openSettings() async {
    _chrome.hold();
    try {
      await showLibraryReaderSettingsSheet(
        context,
        store: _store,
        palette: _palette(context),
        builder: (context, settings, update) => <LibraryReaderSettingItem>[
          LibraryReaderCommonSettings.theme(
            context,
            settings,
            update,
            labelKey: 'background',
          ),
          ...LibraryReaderCommonSettings.toggles(
            context,
            settings,
            update,
            // The side thirds turn the pages of the pages mode only.
            tapZones: _mode == LibraryPdfMode.pages,
          ),
        ],
      );
    } finally {
      if (mounted) _chrome.release();
    }
  }

  LibraryReaderPalette _palette(BuildContext context) =>
      LibraryReaderPalette.forPages(
        _settings.theme,
        MediaQuery.platformBrightnessOf(context),
      );

  // --------------------------------------------------------------- build --

  bool _onGeneralTap(
    BuildContext context,
    PdfViewerController controller,
    PdfViewerGeneralTapHandlerDetails details,
  ) {
    if (details.type != PdfViewerGeneralTapType.tap) return false;
    _chrome.toggle();
    return true;
  }

  Widget _errorView(LibraryReaderPalette palette, Object error) {
    return ColoredBox(
      color: palette.background,
      child: SafeArea(
        child: LibraryReaderErrorView(
          error: LibraryReaderErrorInfo.from(error),
          palette: palette,
          onClose: _close,
        ),
      ),
    );
  }

  Widget _errorBanner(
    BuildContext context,
    Object error,
    StackTrace? stackTrace,
    PdfDocumentRef documentRef,
  ) => _errorView(_palette(context), error);

  /// The pdfrx viewer of Build 440, in two columns where the double page
  /// applies.
  Widget _buildScroll(
    LibraryReaderPalette palette,
    LibraryReaderEffectiveSettings effective,
  ) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final twoColumns = effective.doublePageApplies(
          landscape: constraints.maxWidth > constraints.maxHeight,
          vertical: false,
        );
        return PdfViewer.file(
          widget.filePath,
          controller: _viewer,
          initialPageNumber: _initialPage,
          params: PdfViewerParams(
            backgroundColor: palette.background,
            margin: 4,
            layoutPages: twoColumns
                ? (pages, params) => libraryPdfSpreadLayout(
                    pages,
                    params,
                    firstPageAlone: effective.firstPageAlone,
                    rightToLeft: effective.rightToLeft,
                  )
                : null,
            enableKeyboardNavigation: false,
            maxImageBytesCachedOnMemory: 48 * 1024 * 1024,
            sizeDelegateProvider: const PdfViewerSizeDelegateProviderLegacy(
              maxScale: 6,
            ),
            onViewerReady: (document, controller) {
              if (!mounted || _mode != LibraryPdfMode.scroll) return;
              setState(() {
                _ready = true;
                _pageCount = document.pages.length;
              });
              if (controller.pageNumber != null) {
                _page.value = controller.pageNumber!;
              }
            },
            onPageChanged: _onPageChanged,
            onGeneralTap: _onGeneralTap,
            errorBannerBuilder: _errorBanner,
            loadingBannerBuilder: (context, _, _) =>
                _LibraryPdfLoading(palette: palette),
          ),
        );
      },
    );
  }

  Widget _buildPages(
    LibraryReaderPalette palette,
    LibraryReaderEffectiveSettings effective,
  ) {
    final error = _openError;
    if (error != null) return _errorView(palette, error);
    final document = _document;
    if (document == null) return _LibraryPdfLoading(palette: palette);
    return LibraryPdfPagesView(
      key: _pagesKey,
      document: document,
      contentKey: widget.filePath,
      initialPage: _page.value - 1,
      palette: palette,
      turnStyle: effective.turnStyle,
      doublePage: effective.doublePage,
      firstPageAlone: effective.firstPageAlone,
      rightToLeft: effective.rightToLeft,
      onPageChanged: _onPagesPageChanged,
      onTap: _onPagesTap,
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = _palette(context);
    final effective = _effective;
    final mode = _mode;
    final content = switch (mode) {
      null => const SizedBox.expand(),
      LibraryPdfMode.scroll => _buildScroll(palette, effective),
      LibraryPdfMode.pages => _buildPages(palette, effective),
    };
    String t(String key) => LibraryReaderLocale.text(context, key);
    return PopScope<Object?>(
      onPopInvokedWithResult: _onPopped,
      child: LibraryReaderGamepadScope(
        name: 'library_pdf_reader',
        bindings: gamepadBindings,
        child: AnnotatedRegion<SystemUiOverlayStyle>(
          value: palette.isDark
              ? SystemUiOverlayStyle.light
              : SystemUiOverlayStyle.dark,
          child: Scaffold(
            backgroundColor: palette.background,
            body: ListenableBuilder(
              listenable: Listenable.merge(<Listenable>[_chrome, _page]),
              child: content,
              builder: (context, content) => LibraryReaderChromeOverlay(
                visible: _chrome.visible || !_ready,
                content: content!,
                palette: palette,
                // The floating back button closes like the top bar and B.
                onBack: _close,
                topBar: LibraryReaderTopBar(
                  palette: palette,
                  title: widget.title,
                  subtitle: widget.subtitle,
                  onBack: _close,
                  actions: <Widget>[
                    if (_ready)
                      LibraryReaderIconButton(
                        icon: Icons.toc_rounded,
                        tooltip: t('tableOfContents'),
                        onPressed: _openOutline,
                        color: palette.chromeForeground,
                      ),
                    // The pages mode has no zoom: nothing to fit.
                    if (_ready && mode == LibraryPdfMode.scroll)
                      LibraryReaderIconButton(
                        icon: Icons.fit_screen_rounded,
                        tooltip: t('fitPage'),
                        onPressed: _fitPage,
                        color: palette.chromeForeground,
                      ),
                    LibraryReaderIconButton(
                      icon: Icons.tune_rounded,
                      tooltip: t('settings'),
                      onPressed: _openSettings,
                      color: palette.chromeForeground,
                    ),
                  ],
                ),
                bottomBar: _ready && _pageCount > 0
                    ? LibraryReaderBottomBar(
                        palette: palette,
                        child: LibraryReaderPageSlider(
                          palette: palette,
                          page: _page.value - 1,
                          pageCount: _pageCount,
                          // Like the pages of a right-to-left book.
                          rightToLeft:
                              mode == LibraryPdfMode.pages &&
                              effective.rightToLeft,
                          onChangeStart: (_) {
                            _sliderDragging = true;
                            _chrome.hold();
                          },
                          onChangeEnd: (page) {
                            _sliderDragging = false;
                            _chrome.release();
                            _goToPage(page + 1);
                          },
                          onChanged: (page) => _page.value = page + 1,
                        ),
                      )
                    : null,
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The spinner shown while a document opens (both modes).
class _LibraryPdfLoading extends StatelessWidget {
  const _LibraryPdfLoading({required this.palette});

  final LibraryReaderPalette palette;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: SizedBox(
        width: 32,
        height: 32,
        child: CircularProgressIndicator(
          strokeWidth: 3,
          color: palette.secondaryText,
        ),
      ),
    );
  }
}
