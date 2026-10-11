import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'reader/library_reader_chrome.dart';
import 'reader/library_reader_errors.dart';
import 'reader/library_reader_gamepad.dart';
import 'reader/library_reader_palette.dart';
import 'reader/library_reader_sheets.dart';
import 'reader/library_reader_system.dart';

/// Full-screen PDF reader (local library books and Library downloads).
///
/// Pages are drawn edge to edge by pdfrx; the chrome stays inside the safe
/// area. With a [progressKey] the page is restored and saved (debounced,
/// and when the app goes to the background or the reader closes).
class LibraryPdfReaderScreen extends StatefulWidget {
  const LibraryPdfReaderScreen({
    super.key,
    required this.filePath,
    required this.title,
    this.progressKey,
    this.subtitle,
    this.store,
    this.orientation,
  });

  final String filePath;
  final String title;

  /// Key in [LibraryReadingStore]; null reads without saving the position.
  final String? progressKey;
  final String? subtitle;
  final LibraryReadingStore? store;
  final LibraryReaderOrientation? orientation;

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
  final PdfViewerController _viewer = PdfViewerController();
  final ValueNotifier<int> _page = ValueNotifier<int>(1);
  int _pageCount = 0;
  bool _ready = false;
  bool _storeLoaded = false;
  int _initialPage = 1;
  Timer? _saveTimer;
  bool _dirty = false;
  bool _closing = false;
  bool _sliderDragging = false;
  int? _reportedPage;

  @visibleForTesting
  LibraryReaderGamepadBindings get gamepadBindings =>
      LibraryReaderGamepadBindings(
        left: () => _goRelative(-1),
        right: () => _goRelative(1),
        up: () => _goRelative(-1),
        down: () => _goRelative(1),
        leftBumper: () => _goRelative(-10),
        rightBumper: () => _goRelative(10),
        select: _chrome.toggle,
        back: _close,
        x: _openOutline,
        y: _fitPage,
        start: _openSettings,
      );

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
      _initialPage = key == null
          ? 1
          : libraryPdfInitialPage(_store.progressFor(key));
      _page.value = _initialPage;
      _storeLoaded = true;
    });
    unawaited(_system.start(_settings));
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // VoiceOver: the bars stay until the user hides them.
    _chrome.accessibleNavigation = MediaQuery.accessibleNavigationOf(context);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _saveNow();
    _saveTimer?.cancel();
    _store.removeListener(_onStore);
    _chrome.dispose();
    _page.dispose();
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
      _saveNow();
      unawaited(_store.flush().catchError((Object _) {}));
    }
  }

  void _onStore() {
    final settings = _store.settings;
    if (settings == _settings || !mounted) return;
    setState(() => _settings = settings);
    _system.update(settings);
  }

  void _close() {
    if (_closing || !mounted) return;
    _closing = true;
    Navigator.of(context).maybePop().then((popped) {
      if (!popped) _closing = false;
    });
  }

  void _onPageChanged(int? pageNumber) {
    if (pageNumber == null) return;
    final turned = _reportedPage != null && _reportedPage != pageNumber;
    _reportedPage = pageNumber;
    _page.value = pageNumber;
    // The first report is the initial page: the chrome stays for a moment.
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

  void _goRelative(int delta) {
    if (!_ready || !_viewer.isReady) return;
    final target = (_page.value + delta).clamp(1, _viewer.pageCount);
    unawaited(_viewer.goToPage(pageNumber: target));
  }

  void _goToPage(int pageNumber) {
    if (!_ready || !_viewer.isReady) return;
    unawaited(
      _viewer.goToPage(
        pageNumber: pageNumber.clamp(1, _viewer.pageCount),
        duration: Duration.zero,
      ),
    );
  }

  void _fitPage() {
    if (!_ready || !_viewer.isReady) return;
    final matrix = _viewer.calcMatrixForFit(pageNumber: _page.value);
    if (matrix != null) unawaited(_viewer.goTo(matrix));
  }

  Future<void> _openOutline() async {
    if (!_ready || !_viewer.isReady) return;
    _chrome.hold();
    try {
      List<PdfOutlineNode> outline;
      try {
        outline = await _viewer.document.loadOutline();
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
      if (dest != null) unawaited(_viewer.goToDest(dest));
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
            tapZones: false,
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

  bool _onGeneralTap(
    BuildContext context,
    PdfViewerController controller,
    PdfViewerGeneralTapHandlerDetails details,
  ) {
    if (details.type != PdfViewerGeneralTapType.tap) return false;
    _chrome.toggle();
    return true;
  }

  Widget _errorBanner(
    BuildContext context,
    Object error,
    StackTrace? stackTrace,
    PdfDocumentRef documentRef,
  ) {
    return ColoredBox(
      color: _palette(context).background,
      child: SafeArea(
        child: LibraryReaderErrorView(
          error: LibraryReaderErrorInfo.from(error),
          palette: _palette(context),
          onClose: _close,
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final palette = _palette(context);
    final viewer = !_storeLoaded
        ? const SizedBox.expand()
        : PdfViewer.file(
            widget.filePath,
            controller: _viewer,
            initialPageNumber: _initialPage,
            params: PdfViewerParams(
              backgroundColor: palette.background,
              margin: 4,
              enableKeyboardNavigation: false,
              maxImageBytesCachedOnMemory: 48 * 1024 * 1024,
              sizeDelegateProvider: const PdfViewerSizeDelegateProviderLegacy(
                maxScale: 6,
              ),
              onViewerReady: (document, controller) {
                if (!mounted) return;
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
              loadingBannerBuilder: (context, _, _) => Center(
                child: SizedBox(
                  width: 32,
                  height: 32,
                  child: CircularProgressIndicator(
                    strokeWidth: 3,
                    color: palette.secondaryText,
                  ),
                ),
              ),
            ),
          );
    String t(String key) => LibraryReaderLocale.text(context, key);
    return LibraryReaderGamepadScope(
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
            child: viewer,
            builder: (context, content) => LibraryReaderChromeOverlay(
              visible: _chrome.visible || !_ready,
              content: content!,
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
                  if (_ready)
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
    );
  }
}
