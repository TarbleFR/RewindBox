import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollCacheExtent;
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_http.dart' show LibraryCancelToken;
import 'package:neostation/services/library_manga_models.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_page_curl.dart';
import 'library_page_reader_content.dart';
import 'library_page_reader_controller.dart';
import 'library_page_source.dart';
import 'library_page_spreads.dart';
import 'library_page_textures.dart';
import 'library_reader_bookmarks.dart';
import 'library_reader_chrome.dart';
import 'library_reader_errors.dart';
import 'library_reader_gamepad.dart';
import 'library_reader_palette.dart';
import 'library_reader_sheets.dart';
import 'library_reader_system.dart';
import 'library_reader_toolbar.dart';

/// Comic / manga reader for online chapters and CBZ books.
///
/// Pages are drawn edge to edge; only the chrome stays inside the safe
/// area. Paged mode (left-to-right or right-to-left) zooms each page with a
/// pinch or a double tap; vertical mode is a lazy continuous strip
/// (webtoons) that also zooms with a pinch. Pages are decoded at the
/// viewport size (capped; the width alone in vertical mode) and the
/// neighbours are prefetched.
///
/// Paged mode (docs/library-books-3d-plan.md § 3.4, § 3.9): the pages turn
/// with the controller's [LibraryPageReaderController.turnStyle] — a page
/// curl ([LibraryPageCurlLayer] above the `PageView`, never while zoomed;
/// the chapter cards still slide), the 440 slide, or no animation (also
/// with Reduce Motion). Two pages are shown side by side as
/// [LibraryPageSpreads] lays them out (landscape in automatic mode, the
/// cover alone by default, never in the vertical strip): each `PageView`
/// item is then a spread, while the progress, the chapter marks, the slider
/// and its labels stay page based (the first page of the spread is saved,
/// the spread holding the saved page is opened).
///
/// Toolbar (§ 3.8): settings in three sections (the navigation choices kept
/// for the title), bookmarks (Y adds or removes the bookmark of the page or
/// spread shown; a ribbon shows it), the chapters of an online title (X),
/// the progress with the time left, and Library (the reader's close path).
/// Hidden after 4 s, or always shown ([LibraryReaderToolbarMode.always]:
/// the pages are then laid out between the bars).
class LibraryPageReaderScreen extends StatefulWidget {
  const LibraryPageReaderScreen({
    super.key,
    required this.content,
    this.store,
    this.orientation,
  });

  final LibraryPageReaderContent content;

  /// Reading store (defaults to [LibraryReadingStore.instance]).
  final LibraryReadingStore? store;

  /// Orientation service (defaults to [LibraryReaderOrientation.instance]).
  final LibraryReaderOrientation? orientation;

  @override
  State<LibraryPageReaderScreen> createState() =>
      LibraryPageReaderScreenState();
}

class LibraryPageReaderScreenState extends State<LibraryPageReaderScreen>
    with WidgetsBindingObserver, TickerProviderStateMixin {
  /// Largest decode width of a page, in physical pixels.
  static const int maxDecodeWidth = 2400;

  /// Largest decode height of a page in paged mode, in physical pixels
  /// (above the tallest iPad screen, so no page is shown upscaled).
  static const int maxDecodeHeight = 3072;
  static const double _cardExtent = 280;
  static const double _zoomScale = 2.5;

  late final LibraryReadingStore _store;
  late final LibraryPageReaderController _controller;
  late final LibraryReaderChromeController _chrome;
  late final LibraryReaderSystemSession _system;
  late LibraryReaderSettings _settings;

  /// Settings of this title when last seen (store changes are compared to
  /// them).
  LibraryReaderBookSettings? _book;

  /// Bookmarks of this title when last seen.
  List<LibraryBookmark> _bookmarks = const <LibraryBookmark>[];

  /// Reading pace (time left in the toolbar), fed by [_followPace].
  final LibraryReadingPace _pace = LibraryReadingPace();
  int _paceGeneration = -1;
  int _pacePage = -1;
  int _paceLastShown = -1;

  // Paged mode.
  PageController? _pageController;
  int _pagedGeneration = -1;
  int _pagedLeading = 0;

  /// Spreads of the `PageView` items (one page each when two pages are not
  /// shown side by side).
  LibraryPageSpreads? _pagedSpreads;

  /// Changes when the items of the `PageView` change (double page on or
  /// off): the view is built again at the spread of the current page.
  int _pagedLayout = 0;
  final TransformationController _zoom = TransformationController();
  bool _zoomed = false;
  bool _atStartCard = false;
  bool _atEndCard = false;

  // Page curl.
  late final LibraryPageCurlController _curl;
  final LibraryPageTextureCache _textures = LibraryPageTextureCache();

  /// Whether the curl layer was last built enabled: its textures are kept
  /// only while it is.
  bool _curlInUse = false;
  bool _texturePurgeScheduled = false;

  /// Configuration the page images are resolved with (as last built).
  ImageConfiguration _imageConfiguration = ImageConfiguration.empty;

  // Vertical mode.
  ScrollController? _scrollController;
  int _verticalGeneration = -1;
  final TransformationController _verticalZoom = TransformationController();
  bool _verticalZoomed = false;
  final Map<int, double> _aspects = <int, double>{};

  /// Height of unmeasured pages (x width). Constant for one chapter so the
  /// strip never shifts when it is refined; the next chapter starts from
  /// the last measured page.
  double _estimatedAspect = 1.42;
  double? _lastMeasuredAspect;
  bool _sliderDragging = false;

  /// Page under the slider thumb while it is dragged: only the label
  /// follows it; the view moves (and loads) when the drag ends.
  final ValueNotifier<int?> _sliderPage = ValueNotifier<int?>(null);
  double _listWidth = 0;
  int _anchorItem = 0;
  double _anchorFraction = 0;

  AnimationController? _zoomAnimation;
  Timer? _pendingTap;
  Offset? _pendingTapPosition;
  LibraryPageReaderMode? _builtMode;
  int _decodeWidth = 1080;
  int _decodeHeight = 1920;
  final Set<ImageProvider> _providers = <ImageProvider>{};
  bool _closing = false;

  /// Page an animated turn is heading to. The controller only learns the
  /// new page when the animation crosses it (a slide) or ends (a curl), so
  /// a reader closed during a turn saves this page instead of the one being
  /// left.
  int? _turnTarget;

  @visibleForTesting
  LibraryPageReaderController get controller => _controller;

  /// Page curl of the paged view (driven by drags, the d-pad and the tap
  /// zones).
  @visibleForTesting
  LibraryPageCurlController get curl => _curl;

  /// Textures of the curl (the spread on screen and its neighbours).
  @visibleForTesting
  LibraryPageTextureCache get textures => _textures;

  /// Spreads of the paged view as last built (null before it is built).
  @visibleForTesting
  LibraryPageSpreads? get spreads => _pagedSpreads;

  @visibleForTesting
  bool get chromeVisible => _chrome.visible;

  @visibleForTesting
  bool get atEndCard => _atEndCard;

  /// Whether the current page (paged) or the strip (vertical) is zoomed.
  @visibleForTesting
  bool get zoomed => _vertical ? _verticalZoomed : _zoomed;

  @visibleForTesting
  bool get atStartCard => _atStartCard;

  /// Controller actions of the reader (docs/library-books-3d-plan.md
  /// § 3.10): d-pad, A, B, bumpers, X the chapters of an online title, Y
  /// the bookmark of the page or spread shown, Start.
  @visibleForTesting
  LibraryReaderGamepadBindings get gamepadBindings =>
      LibraryReaderGamepadBindings(
        left: () => _turnVisual(-1),
        right: () => _turnVisual(1),
        up: () => _vertical ? _scrollBy(-0.8) : _previous(),
        down: () => _vertical ? _scrollBy(0.8) : _next(),
        leftBumper: _controller.hasPreviousChapter
            ? () => unawaited(_controller.previousChapter())
            : null,
        rightBumper: _controller.hasNextChapter
            ? () => unawaited(_controller.nextChapter())
            : null,
        // A retries a chapter that failed to load (the button is touch
        // only), else shows or hides the chrome.
        select: _controller.status == LibraryPageReaderStatus.error
            ? () => unawaited(_controller.retry())
            : _chrome.toggle,
        back: _close,
        x: _chaptersAvailable ? _openChapters : null,
        y: _controller.status == LibraryPageReaderStatus.ready
            ? _toggleBookmark
            : null,
        start: _openSettings,
      );

  bool get _vertical => _controller.mode == LibraryPageReaderMode.vertical;

  /// An online title with several chapters: the Chapters action and X.
  bool get _chaptersAvailable =>
      widget.content.tracksChapters && widget.content.chapters.length > 1;

  /// The toolbar stays shown (global setting).
  bool get _toolbarAlways =>
      _settings.toolbarMode == LibraryReaderToolbarMode.always;

  @override
  void initState() {
    super.initState();
    _store = widget.store ?? LibraryReadingStore.instance;
    _settings = _store.settings;
    _book = _store.bookSettingsFor(widget.content.progressKey);
    _bookmarks = _store.bookmarksFor(widget.content.progressKey);
    _controller = LibraryPageReaderController(
      content: widget.content,
      store: _store,
    );
    _curl = LibraryPageCurlController(vsync: this);
    _chrome = LibraryReaderChromeController()..alwaysVisible = _toolbarAlways;
    _system = LibraryReaderSystemSession(orientation: widget.orientation);
    _controller.addListener(_onController);
    _store.addListener(_onStore);
    _zoom.addListener(_onZoom);
    _verticalZoom.addListener(_onVerticalZoom);
    WidgetsBinding.instance.addObserver(this);
    unawaited(_start());
  }

  Future<void> _start() async {
    try {
      await _store.load();
    } catch (_) {
      // The store keeps working in memory.
    }
    if (!mounted) return;
    // Orientation and wake lock follow the settings from the start, not
    // only once the first chapter has downloaded.
    _settings = _store.settings;
    _book = _store.bookSettingsFor(widget.content.progressKey);
    _bookmarks = _store.bookmarksFor(widget.content.progressKey);
    _chrome.alwaysVisible = _toolbarAlways;
    unawaited(_system.start(_settings));
    await _controller.start();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // VoiceOver: the bars stay until the user hides them.
    _chrome.accessibleNavigation = MediaQuery.accessibleNavigationOf(context);
    // Reduce Motion: pages turn without animation (no curl, no slide).
    _controller.reduceMotion = MediaQuery.disableAnimationsOf(context);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _pendingTap?.cancel();
    _zoomAnimation?.dispose();
    _store.removeListener(_onStore);
    _controller.removeListener(_onController);
    _controller.dispose();
    _chrome.dispose();
    // The curl layer was unmounted first (it detached from the controller
    // and released its retained textures).
    _curl.dispose();
    _textures.dispose();
    _pageController?.dispose();
    _scrollController?.dispose();
    _zoom.dispose();
    _verticalZoom.dispose();
    _sliderPage.dispose();
    unawaited(_system.stop());
    unawaited(_store.flush().catchError((Object _) {}));
    // Release the decoded pages of this session (the iOS image cache is
    // small and a page decoded at full width uses several megabytes).
    final cache = PaintingBinding.instance.imageCache;
    for (final provider in _providers) {
      cache.evict(provider);
    }
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      unawaited(_controller.flush().catchError((Object _) {}));
    }
  }

  void _onStore() {
    if (!mounted) return;
    final settings = _store.settings;
    final book = _store.bookSettingsFor(widget.content.progressKey);
    final bookmarks = _store.bookmarksFor(widget.content.progressKey);
    final settingsChanged = settings != _settings;
    final bookmarksChanged = !identical(bookmarks, _bookmarks);
    if (!settingsChanged && book == _book && !bookmarksChanged) return;
    // The mode the session override replaced: the title's, else the global
    // one. Only a change of it lets the stored mode decide again (a global
    // change under a title's own mode changes nothing on screen).
    final previousMode = _book?.mangaMode ?? _settings.mangaMode;
    setState(() {
      _settings = settings;
      _book = book;
      _bookmarks = bookmarks;
    });
    if ((book?.mangaMode ?? settings.mangaMode) != previousMode) {
      _controller.clearModeOverride();
    }
    if (settingsChanged) {
      _system.update(settings);
      _chrome.alwaysVisible = _toolbarAlways;
    }
  }

  void _onController() {
    if (!mounted) return;
    _followPace();
    setState(() {});
    if (_controller.status == LibraryPageReaderStatus.ready) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _prefetchAround());
    }
  }

  void _onZoom() {
    final zoomed = _zoom.value.getMaxScaleOnAxis() > 1.01;
    if (zoomed != _zoomed && mounted) setState(() => _zoomed = zoomed);
  }

  void _onVerticalZoom() {
    final zoomed = _verticalZoom.value.getMaxScaleOnAxis() > 1.01;
    if (zoomed != _verticalZoomed && mounted) {
      setState(() => _verticalZoomed = zoomed);
    }
  }

  void _close() {
    if (_closing || !mounted) return;
    _closing = true;
    final target = _turnTarget;
    if (target != null && target != _controller.page) {
      _controller.setPage(target, through: _lastPageShownWith(target));
    }
    // Saved before the pop, while the screens below can rebuild for it.
    _controller.saveNow();
    Navigator.of(context).maybePop().then((popped) {
      if (!popped) _closing = false;
    });
  }

  /// The route was popped (Back, B, the iOS back swipe): the screen below
  /// is on stage from now on, so landscape is restored now rather than in
  /// [dispose], after the reverse transition, and the progress is saved
  /// now (from [dispose], the store would notify the screens below while
  /// the widget tree is locked). [dispose] stays the fallback (the session
  /// stops once; nothing is left to save).
  void _onPopped(bool didPop, Object? _) {
    if (!didPop) return;
    _controller.finish();
    unawaited(_system.stop());
  }

  // ---------------------------------------------------------- navigation --

  int get _leading =>
      widget.content.tracksChapters && _controller.hasPreviousChapter ? 1 : 0;

  // Items of the paged view: the start card (a previous chapter), one item
  // per spread (one page, or two side by side), the end card.

  /// Number of items of the paged view.
  int get _pagedItemCount =>
      _pagedLeading + (_pagedSpreads?.length ?? _controller.pageCount) + 1;

  /// Item of the paged view on screen.
  int get _currentItem {
    if (_atStartCard) return 0;
    if (_atEndCard) {
      return _pagedLeading + (_pagedSpreads?.length ?? _controller.pageCount);
    }
    return _itemOfPage(_controller.page);
  }

  /// Item of the paged view showing [page].
  int _itemOfPage(int page) =>
      _pagedLeading + (_pagedSpreads?.spreadOf(page) ?? page);

  /// First page of item [item]; null for the chapter cards.
  int? _pageOfItem(int item) {
    final spreads = _pagedSpreads;
    final index = item - _pagedLeading;
    if (index < 0 || index >= (spreads?.length ?? _controller.pageCount)) {
      return null;
    }
    return spreads?.firstPageOf(index) ?? index;
  }

  /// Last page on screen with [page]: the other page of its spread, else
  /// [page] itself.
  int _lastPageShownWith(int page) {
    final spreads = _pagedSpreads;
    if (_vertical || spreads == null || spreads.isEmpty) return page;
    return spreads.spreadAt(spreads.spreadOf(page)).last;
  }

  /// Visual direction: -1 is the left side of the screen, 1 the right.
  void _turnVisual(int side) {
    if (_vertical) {
      side < 0 ? _previous() : _next();
      return;
    }
    final forward = _controller.rightToLeft ? side < 0 : side > 0;
    forward ? _next() : _previous();
  }

  void _next() {
    if (_controller.status != LibraryPageReaderStatus.ready) return;
    if (_vertical) {
      if (_atEndCard || (_controller.isLastPage && _atEndOfList())) {
        _advancePastEnd();
        return;
      }
      if (_controller.isLastPage) {
        // Show the end card below the last page.
        final scroll = _scrollController;
        if (scroll != null && scroll.hasClients) {
          scroll.animateTo(
            scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
          );
        }
        return;
      }
      _jumpToPage(_controller.page + 1, animate: true);
      return;
    }
    if (_atEndCard) {
      _advancePastEnd();
      return;
    }
    if (_curlTurn(LibraryPageTurnDirection.forward)) return;
    _turnPagedBy(1);
  }

  /// Turns the page with the curl when it can draw this turn (between two
  /// pages or spreads; never toward a chapter card, never while zoomed, in
  /// the curl style only). True when the turn is handled, also when a turn
  /// is already running: a press then never turns a second page.
  bool _curlTurn(LibraryPageTurnDirection direction) {
    if (_vertical) return false;
    if (_curl.isActive) return true;
    if (!_curl.canTurn(direction)) return false;
    final forward = direction == LibraryPageTurnDirection.forward;
    final target = _pageOfItem(_currentItem + (forward ? 1 : -1));
    final turn = _curl.turn(direction);
    if (target != null && target != _controller.page) {
      _trackTurn(target, turn);
    } else {
      unawaited(turn);
    }
    return true;
  }

  /// Turns the paged view by [delta] items: the 440 slide, or a jump
  /// without animation ([LibraryPageTurnStyle.none], Reduce Motion).
  void _turnPagedBy(int delta) {
    final pages = _pageController;
    if (pages == null || !pages.hasClients) return;
    final item = _currentItem + delta;
    if (item < 0 || item >= _pagedItemCount) return;
    if (_controller.turnStyle == LibraryPageTurnStyle.none) {
      pages.jumpToPage(item);
      return;
    }
    final target = _pageOfItem(item);
    final turn = pages.animateToPage(
      item,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
    );
    if (target != null && target != _controller.page) {
      _trackTurn(target, turn);
    } else {
      unawaited(turn);
    }
  }

  void _trackTurn(int target, Future<void> turn) {
    _turnTarget = target;
    unawaited(
      turn.whenComplete(() {
        if (_turnTarget == target) _turnTarget = null;
      }),
    );
  }

  void _previous() {
    if (_controller.status != LibraryPageReaderStatus.ready) return;
    if (_atStartCard) {
      unawaited(_controller.previousChapter(fromEnd: true));
      return;
    }
    if (_vertical) {
      if (_controller.page == 0) {
        _scrollController?.animateTo(
          0,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
        );
        return;
      }
      _jumpToPage(_controller.page - 1, animate: true);
      return;
    }
    if (_curlTurn(LibraryPageTurnDirection.backward)) return;
    _turnPagedBy(-1);
  }

  void _advancePastEnd() {
    if (_controller.hasNextChapter && widget.content.tracksChapters) {
      unawaited(_controller.nextChapter());
    }
  }

  bool _atEndOfList() {
    final scroll = _scrollController;
    if (scroll == null || !scroll.hasClients) return false;
    return scroll.position.extentAfter < 1;
  }

  void _jumpToPage(int page, {bool animate = false}) {
    final count = _controller.pageCount;
    if (count == 0) return;
    final target = page.clamp(0, count - 1);
    if (_vertical) {
      final scroll = _scrollController;
      if (scroll == null || !scroll.hasClients) return;
      final offset = _offsetOfItem(
        _leading + target,
      ).clamp(0.0, scroll.position.maxScrollExtent);
      if (animate) {
        _trackTurn(
          target,
          scroll.animateTo(
            offset,
            duration: const Duration(milliseconds: 220),
            curve: Curves.easeOut,
          ),
        );
      } else {
        scroll.jumpTo(offset);
      }
      return;
    }
    final pages = _pageController;
    if (pages == null || !pages.hasClients) return;
    final item = _itemOfPage(target);
    if (animate) {
      _trackTurn(
        target,
        pages.animateToPage(
          item,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
        ),
      );
    } else {
      pages.jumpToPage(item);
    }
  }

  void _scrollBy(double viewports) {
    final scroll = _scrollController;
    if (scroll == null || !scroll.hasClients) return;
    final position = scroll.position;
    final target = (position.pixels + position.viewportDimension * viewports)
        .clamp(position.minScrollExtent, position.maxScrollExtent);
    scroll.animateTo(
      target,
      duration: const Duration(milliseconds: 200),
      curve: Curves.easeOut,
    );
  }

  void _onPagedChanged(int index) {
    final spreads = _pagedSpreads;
    final count = spreads?.length ?? _controller.pageCount;
    final leading = _pagedLeading;
    if (_zoomed) {
      // The physics of the PageView follow the zoom.
      setState(_resetZoom);
    } else {
      _resetZoom();
    }
    if (index < leading) {
      setState(() {
        _atStartCard = true;
        _atEndCard = false;
      });
      return;
    }
    if (index >= leading + count) {
      setState(() {
        _atEndCard = true;
        _atStartCard = false;
      });
      // The last page was reached (marks the chapter read).
      _controller.setPage(_controller.pageCount - 1);
      return;
    }
    if (_atStartCard || _atEndCard) {
      setState(() {
        _atStartCard = false;
        _atEndCard = false;
      });
    }
    // A spread is saved as its first page; its other page counts as shown
    // (the chapter is read once its last page is on screen).
    final spread = spreads?.spreadAt(index - leading);
    final page = spread?.first ?? index - leading;
    if (page != _controller.page && !_sliderDragging) {
      unawaited(HapticFeedback.selectionClick().catchError((Object _) {}));
      if (_chrome.visible) _chrome.hideAfterTurn();
    }
    _controller.setPage(page, through: spread?.last);
  }

  /// The curl has fully turned the page: the `PageView` jumps under it,
  /// without animation, so that its page change runs as for any turn
  /// (progress, chapter marks, prefetch, haptics).
  void _onCurlTurned(int item) {
    final pages = _pageController;
    if (!mounted || pages == null || !pages.hasClients) return;
    pages.jumpToPage(item);
  }

  /// After a new layout of the paged view (chapter, rotation, double page
  /// on or off), the pages on screen beside the current one are counted as
  /// shown.
  void _syncShownPages() {
    if (_vertical || _atStartCard || _atEndCard || _pagedSpreads == null) {
      return;
    }
    final page = _controller.page;
    _controller.setPage(page, through: _lastPageShownWith(page));
  }

  /// Unzooms the paged view. Also called while the reader builds (new
  /// chapter, layout switch): the flag is cleared first so the zoom
  /// listener never calls setState during a build.
  void _resetZoom() {
    _zoomAnimation?.stop();
    _zoomed = false;
    if (_zoom.value.getMaxScaleOnAxis() != 1.0) {
      _zoom.value = Matrix4.identity();
    }
  }

  /// Unzooms the vertical strip (same rule as [_resetZoom]).
  void _resetVerticalZoom() {
    _zoomAnimation?.stop();
    _verticalZoomed = false;
    if (_verticalZoom.value.getMaxScaleOnAxis() != 1.0) {
      _verticalZoom.value = Matrix4.identity();
    }
  }

  // ---------------------------------------------------------------- taps --

  void _onTapUp(TapUpDetails details, Size size) {
    final position = details.localPosition;
    final pending = _pendingTapPosition;
    if (_pendingTap != null &&
        pending != null &&
        (position - pending).distance < kDoubleTapSlop) {
      _pendingTap!.cancel();
      _pendingTap = null;
      _pendingTapPosition = null;
      _onDoubleTap(position);
      return;
    }
    _pendingTap?.cancel();
    _pendingTap = null;
    final third = size.width / 3;
    final zone = position.dx < third
        ? -1
        : position.dx > size.width - third
        ? 1
        : 0;
    final zoomed = _vertical ? _verticalZoomed : _zoomed;
    final ready = _controller.status == LibraryPageReaderStatus.ready;
    if (!ready || zone == 0 || zoomed || !_settings.tapZones) {
      // Centre (or zoomed page): the chrome, unless a second tap makes it a
      // double tap. Side zones react at once.
      _pendingTapPosition = position;
      _pendingTap = Timer(kDoubleTapTimeout, () {
        _pendingTap = null;
        _pendingTapPosition = null;
        if (mounted) _chrome.toggle();
      });
      return;
    }
    if (_chrome.visible) _chrome.hide();
    if (_vertical) {
      _scrollBy(zone < 0 ? -0.85 : 0.85);
    } else {
      _turnVisual(zone);
    }
  }

  void _onDoubleTap(Offset position) {
    if (_controller.status != LibraryPageReaderStatus.ready) return;
    final transform = _vertical ? _verticalZoom : _zoom;
    final zoomed = transform.value.getMaxScaleOnAxis() > 1.01;
    final target = zoomed
        ? Matrix4.identity()
        : (Matrix4.identity()
            ..setEntry(0, 0, _zoomScale)
            ..setEntry(1, 1, _zoomScale)
            ..setEntry(0, 3, -position.dx * (_zoomScale - 1))
            ..setEntry(1, 3, -position.dy * (_zoomScale - 1)));
    _animateZoom(transform, target);
  }

  void _animateZoom(TransformationController transform, Matrix4 target) {
    _zoomAnimation?.dispose();
    final animation = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
    final tween = Matrix4Tween(begin: transform.value, end: target);
    final curve = CurvedAnimation(parent: animation, curve: Curves.easeOut);
    animation.addListener(() => transform.value = tween.evaluate(curve));
    _zoomAnimation = animation;
    animation.forward();
  }

  // ------------------------------------------------------------ prefetch --

  void _prefetchAround() {
    if (!mounted) return;
    final source = _controller.source;
    if (source == null) return;
    final page = _controller.page;
    // Two pages side by side: the pages of the previous and next spreads
    // as well.
    final spreads = _vertical ? null : _pagedSpreads;
    final neighbours = <int>[];
    if (spreads != null &&
        spreads.doublePage &&
        spreads.pageCount == source.length) {
      final index = spreads.spreadOf(page);
      if (index + 1 < spreads.length) {
        neighbours.addAll(spreads.pagesOf(index + 1));
      }
      if (index > 0) neighbours.addAll(spreads.pagesOf(index - 1));
    }
    var first = page - 2;
    var last = page + 3;
    for (final index in neighbours) {
      first = math.min(first, index - 1);
      last = math.max(last, index + 1);
    }
    // Downloads of pages the reader moved away from stop: they would hold
    // the site's request slots ahead of the page being read.
    source.cancelPrefetchOutside(first, last);
    for (final index in <int>{page + 1, page + 2, page - 1, ...neighbours}) {
      if (index >= 0 && index < source.length) source.prefetch(index);
    }
    if (_vertical) return;
    // Decode the next and previous pages ahead in paged mode.
    for (final index in <int>{page + 1, page - 1, ...neighbours}) {
      if (index < 0 || index >= source.length) continue;
      final provider = _provider(source, index);
      unawaited(precacheImage(provider, context, onError: (_, _) {}));
    }
  }

  ImageProvider _provider(LibraryPageSource source, int index) {
    // Paged mode shows the whole page on the screen (BoxFit.contain): a
    // portrait page in landscape is limited by the screen height, so it is
    // decoded no taller than the screen. The vertical strip fills the
    // width, so only the width limits it there.
    final provider = source.imageFor(
      index,
      cacheWidth: _decodeWidth,
      cacheHeight: _vertical ? null : _decodeHeight,
    );
    _providers.add(provider);
    return provider;
  }

  /// Image of page [page] for the curl: the reader's own provider, at the
  /// decode size of the `PageView` items (the decoded page is shared, never
  /// decoded twice), as a new handle the texture cache owns. [pixels] is
  /// the size the curl draws it at (the page is drawn contained in it).
  /// Null once [cancel] is cancelled, or when the page fails to load (that
  /// turn then slides).
  Future<ui.Image?> _renderCurlPage(
    int page,
    Size pixels,
    LibraryCancelToken cancel,
  ) {
    final source = _controller.source;
    if (!mounted ||
        cancel.isCancelled ||
        source == null ||
        page < 0 ||
        page >= source.length) {
      return Future<ui.Image?>.value();
    }
    final completer = Completer<ui.Image?>();
    final stream = _provider(
      source,
      page,
    ).resolve(createLocalImageConfiguration(context));
    late final ImageStreamListener listener;
    void Function()? unregister;
    void finish(ui.Image? image) {
      if (completer.isCompleted) {
        image?.dispose();
        return;
      }
      stream.removeListener(listener);
      unregister?.call();
      completer.complete(image);
    }

    listener = ImageStreamListener((info, _) {
      // The listener owns this ImageInfo: the cache gets its own handle.
      final image = cancel.isCancelled ? null : info.image.clone();
      info.dispose();
      finish(image);
    }, onError: (_, _) => finish(null));
    stream.addListener(listener);
    if (!completer.isCompleted) {
      unregister = cancel.addCancelListener(() => finish(null));
    }
    return completer.future;
  }

  void _updateDecodeSize(Size size) {
    // A closing reader rotates back to landscape during its transition:
    // its pages keep the sizes they were decoded at instead of being read
    // and decoded again for a screen that is going away.
    if (_controller.finished) return;
    final ratio = MediaQuery.devicePixelRatioOf(context);
    _decodeWidth = _decodeLimit(size.width * ratio, maxDecodeWidth);
    _decodeHeight = _decodeLimit(size.height * ratio, maxDecodeHeight);
  }

  /// [physical] pixels rounded up to a step of 128 px (keeps the decoded
  /// sizes few across small changes), within 256 and [max].
  static int _decodeLimit(double physical, int max) {
    final stepped = ((physical.ceil() + 127) ~/ 128) * 128;
    return math.max(256, math.min(max, stepped));
  }

  // ------------------------------------------------------------- vertical --

  double _aspectOf(int page) => _aspects[page] ?? _estimatedAspect;

  double _extentOfItem(int item, double width) {
    final leading = _leading;
    final count = _controller.pageCount;
    if (item < leading || item >= leading + count) return _cardExtent;
    return width * _aspectOf(item - leading);
  }

  double _offsetOfItem(int item) {
    var offset = 0.0;
    for (var i = 0; i < item; i++) {
      offset += _extentOfItem(i, _listWidth);
    }
    return offset;
  }

  /// Item at scroll offset [y] and the fraction of it above [y].
  (int, double) _itemAt(double y) {
    final total = _leading + _controller.pageCount + 1;
    var top = 0.0;
    for (var i = 0; i < total; i++) {
      final extent = _extentOfItem(i, _listWidth);
      if (y < top + extent || i == total - 1) {
        return (i, extent <= 0 ? 0 : ((y - top) / extent).clamp(0.0, 1.0));
      }
      top += extent;
    }
    return (0, 0);
  }

  void _onVerticalScroll() {
    final scroll = _scrollController;
    if (scroll == null || !scroll.hasClients) return;
    final position = scroll.position;
    final (anchor, fraction) = _itemAt(position.pixels);
    _anchorItem = anchor;
    _anchorFraction = fraction;
    final (item, _) = _itemAt(position.pixels + position.viewportDimension / 2);
    final leading = _leading;
    final count = _controller.pageCount;
    final atEnd = item >= leading + count;
    final atStart = item < leading;
    if (atEnd != _atEndCard || atStart != _atStartCard) {
      setState(() {
        _atEndCard = atEnd;
        _atStartCard = atStart;
      });
    }
    if (atStart) return;
    _controller.setPage(atEnd ? count - 1 : item - leading);
  }

  void _onMeasured(int page, double aspect) {
    if (!aspect.isFinite || aspect <= 0) return;
    final generation = _controller.generation;
    if (SchedulerBinding.instance.schedulerPhase ==
        SchedulerPhase.persistentCallbacks) {
      // Reported while the list lays out its children (cached image).
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && generation == _controller.generation) {
          _applyMeasured(page, aspect);
        }
      });
      return;
    }
    _applyMeasured(page, aspect);
  }

  void _applyMeasured(int page, double aspect) {
    final previous = _aspectOf(page);
    _aspects[page] = aspect;
    _lastMeasuredAspect = aspect;
    if ((previous - aspect).abs() < 0.0005 || !_vertical || !mounted) return;
    final scroll = _scrollController;
    if (scroll != null && scroll.hasClients) {
      final item = _leading + page;
      final top = _offsetOfItem(item);
      final position = scroll.position;
      // A page above the viewport changed height: keep the visible content
      // where it is.
      if (top + _listWidth * previous <= position.pixels + 0.5) {
        position.correctBy(_listWidth * (aspect - previous));
      }
    }
    setState(() {});
  }

  /// Releases a controller after the frame that replaces its view.
  void _disposeLater(ChangeNotifier? controller) {
    if (controller == null) return;
    WidgetsBinding.instance.addPostFrameCallback((_) => controller.dispose());
  }

  void _ensureVerticalController() {
    if (_scrollController != null &&
        _verticalGeneration == _controller.generation) {
      return;
    }
    _scrollController?.removeListener(_onVerticalScroll);
    _disposeLater(_scrollController);
    _verticalGeneration = _controller.generation;
    _aspects.clear();
    _estimatedAspect =
        _lastMeasuredAspect ??
        (widget.content.layoutHint == LibraryPageLayoutHint.vertical
            ? 1.8
            : 1.42);
    _resetVerticalZoom();
    _atEndCard = false;
    _atStartCard = false;
    final offset = _offsetOfItem(_leading + _controller.page);
    _scrollController = ScrollController(initialScrollOffset: offset)
      ..addListener(_onVerticalScroll);
  }

  /// The `PageView` controller for [spreads]: a new one for a new chapter
  /// or layout switch, and when the items change (double page on or off,
  /// first page alone or not, rotation), at the item showing the current
  /// page (so a rotation keeps the page on screen).
  void _ensurePagedController(LibraryPageSpreads spreads) {
    final fresh =
        _pageController == null || _pagedGeneration != _controller.generation;
    final previous = _pagedSpreads;
    _pagedSpreads = spreads;
    if (!fresh && previous != null && _sameItems(previous, spreads)) return;
    _disposeLater(_pageController);
    if (fresh) {
      _pagedGeneration = _controller.generation;
      _pagedLeading = _leading;
      _atEndCard = false;
      _atStartCard = false;
    }
    _pagedLayout++;
    _resetZoom();
    _pageController = PageController(initialPage: _currentItem);
    final layout = _pagedLayout;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && layout == _pagedLayout) _syncShownPages();
    });
  }

  /// Whether two layouts have the same items (the same pages in each).
  static bool _sameItems(LibraryPageSpreads a, LibraryPageSpreads b) =>
      a.pageCount == b.pageCount &&
      a.doublePage == b.doublePage &&
      (!a.doublePage || a.firstPageAlone == b.firstPageAlone);

  void _onModeBuilt(LibraryPageReaderMode mode) {
    if (_builtMode == mode) return;
    final switching = _builtMode != null;
    _builtMode = mode;
    if (!switching) return;
    // Keep the current page when switching layouts: the view of the new
    // mode starts again from the current page.
    if (mode == LibraryPageReaderMode.vertical) {
      _scrollController?.removeListener(_onVerticalScroll);
      _disposeLater(_scrollController);
      _scrollController = null;
    } else {
      _disposeLater(_pageController);
      _pageController = null;
    }
    _resetZoom();
    _resetVerticalZoom();
  }

  // ------------------------------------------------- bookmarks, pace --

  /// Chapter a bookmark of this title names: the online chapter shown,
  /// none for a book.
  String? get _bookmarkChapterId =>
      widget.content.tracksChapters ? _controller.chapter.id : null;

  /// Pages on screen (zero-based): the spread of the current page, or the
  /// page in the middle of the vertical strip; none on a chapter card or
  /// before the chapter is ready.
  List<int> _shownPages() {
    if (_controller.status != LibraryPageReaderStatus.ready ||
        _controller.pageCount == 0 ||
        _atStartCard ||
        _atEndCard) {
      return const <int>[];
    }
    final page = _controller.page;
    final last = _lastPageShownWith(page);
    return <int>[for (var shown = page; shown <= last; shown++) shown];
  }

  bool _onPagesShown(LibraryBookmark bookmark, List<int> pages) =>
      bookmark.chapterId == _bookmarkChapterId &&
      pages.contains(libraryBookmarkPage(bookmark));

  /// The title's bookmarks on the pages shown.
  List<LibraryBookmark> _shownBookmarks([List<LibraryBookmark>? bookmarks]) {
    final pages = _shownPages();
    if (pages.isEmpty) return const <LibraryBookmark>[];
    return <LibraryBookmark>[
      for (final bookmark in bookmarks ?? _bookmarks)
        if (_onPagesShown(bookmark, pages)) bookmark,
    ];
  }

  /// Overall progress at [page] of the chapter shown (as
  /// [LibraryPageReaderController.fraction]).
  double _fractionAt(int page) {
    final count = _controller.pageCount;
    if (count == 0) return 0;
    final inChapter = (page + 1) / count;
    final chapters = widget.content.chapters.length;
    if (!widget.content.tracksChapters || chapters <= 1) return inChapter;
    return (_controller.chapterIndex + inChapter) / chapters;
  }

  /// Y: adds a bookmark at the page (or spread) shown, or removes the ones
  /// it carries; the result is said at the bottom of the screen unless
  /// [feedback] is false (the bookmarks sheet shows it itself).
  LibraryBookmarkToggleResult _toggleBookmark({bool feedback = true}) {
    final pages = _shownPages();
    if (pages.isEmpty) return LibraryBookmarkToggleResult.unchanged;
    final key = widget.content.progressKey;
    final chapterId = _bookmarkChapterId;
    final chapter = _controller.chapter;
    final page = pages.first;
    final result = toggleLibraryBookmark(
      _store,
      key: key,
      shown: _shownBookmarks(_store.bookmarksFor(key)),
      location: libraryPageBookmarkLocation(page, chapterId: chapterId),
      fraction: _fractionAt(page),
      chapterId: chapterId,
      chapterTitle: chapterId != null && chapter.title.isNotEmpty
          ? chapter.title
          : null,
      pageIndex: page,
    );
    final message = libraryBookmarkMessageKey(result);
    if (feedback && message != null && mounted) {
      showLibraryReaderMessage(context, message);
    }
    return result;
  }

  Future<void> _openBookmarks() async {
    _chrome.hold();
    try {
      await showLibraryReaderBookmarksSheet(
        context,
        store: _store,
        progressKey: widget.content.progressKey,
        palette: _palette(context),
        isShown: (bookmark) => _onPagesShown(bookmark, _shownPages()),
        onOpen: _openBookmark,
        onToggle: _shownPages().isEmpty
            ? null
            : () => _toggleBookmark(feedback: false),
        chapterLabel: widget.content.tracksChapters
            ? (bookmark) => _chapterLabelOf(bookmark.chapterId)
            : null,
      );
    } finally {
      if (mounted) _chrome.release();
    }
  }

  /// Label of the online chapter [id], if it is one of this title's.
  String? _chapterLabelOf(String? id) {
    if (id == null) return null;
    for (final chapter in widget.content.chapters) {
      if (chapter.id == id) return _chapterLabel(context, chapter);
    }
    return null;
  }

  /// Shows the page of [bookmark], in its chapter for an online title.
  void _openBookmark(LibraryBookmark bookmark) {
    if (!mounted) return;
    final page = libraryBookmarkPage(bookmark);
    if (page == null) return;
    if (widget.content.tracksChapters) {
      final index = widget.content.chapters.indexWhere(
        (chapter) => chapter.id == bookmark.chapterId,
      );
      if (index < 0) return;
      if (index != _controller.chapterIndex ||
          _controller.status != LibraryPageReaderStatus.ready) {
        unawaited(_controller.openChapter(index, page: page));
        return;
      }
    }
    if (_controller.status != LibraryPageReaderStatus.ready) return;
    // The page chosen is the position, also inside a spread (as the
    // slider).
    _jumpToPage(page);
    _controller.setPage(page, through: _lastPageShownWith(page));
  }

  /// The chapters of an online title (X); the one chosen opens at its
  /// first page.
  Future<void> _openChapters() async {
    final chapters = widget.content.chapters;
    _chrome.hold();
    try {
      final index = await showLibraryReaderListSheet(
        context,
        palette: _palette(context),
        title: LibraryReaderLocale.text(context, 'chapters'),
        entries: <LibraryReaderListEntry>[
          for (final chapter in chapters)
            LibraryReaderListEntry(title: _chapterLabel(context, chapter)),
        ],
        currentIndex: _controller.chapterIndex,
      );
      if (index == null || !mounted || index == _controller.chapterIndex) {
        return;
      }
      unawaited(_controller.openChapter(index));
    } finally {
      if (mounted) _chrome.release();
    }
  }

  /// Feeds the reading pace: a turn to the page after the ones shown counts
  /// (with the pages it leaves); a jump, a turn back or another chapter
  /// starts its clock again.
  void _followPace() {
    if (_controller.status != LibraryPageReaderStatus.ready ||
        _controller.finished) {
      return;
    }
    final page = _controller.page;
    if (_controller.generation != _paceGeneration) {
      _paceGeneration = _controller.generation;
      _pace.restart();
    } else if (page != _pacePage) {
      if (page == _paceLastShown + 1 && page > _pacePage) {
        _pace.pageShown(pages: page - _pacePage);
      } else {
        _pace.restart();
      }
    }
    _pacePage = page;
    _paceLastShown = _controller.lastShownPage;
  }

  LibraryReaderToolbarProgress _toolbarProgress(BuildContext context) {
    final tracks = widget.content.tracksChapters;
    final left = math.max(
      0,
      _controller.pageCount - 1 - _controller.lastShownPage,
    );
    final time = _pace.remaining(left);
    return LibraryReaderToolbarProgress(
      // The slider prints the page ("n / N").
      fraction: _controller.fraction,
      remainingInChapter: tracks ? time : null,
      remainingInBook: tracks ? null : time,
      chapterTitle: tracks ? _chapterLabel(context, _controller.chapter) : null,
    );
  }

  // ---------------------------------------------------------- settings --

  /// The settings in three sections (docs/library-books-3d-plan.md § 3.8):
  /// Appearance (global), Navigation (the reading mode, direction, page
  /// turn and two-page choices kept for this title; toolbar, tap zones,
  /// screen and rotation global), "Revert to general settings".
  Future<void> _openSettings() async {
    _chrome.hold();
    final palette = _palette(context);
    try {
      await showLibraryReaderSettingsSheet(
        context,
        store: _store,
        palette: palette,
        builder: (context, settings, update) {
          String t(String key) => LibraryReaderLocale.text(context, key);
          final editor = LibraryReaderBookSettingsEditor(
            store: _store,
            key: widget.content.progressKey,
          );
          final book = editor.settings;
          final turnStyle = book?.turnStyle ?? settings.turnStyle;
          return <LibraryReaderSettingItem>[
            ...LibraryReaderCommonSettings.appearance(
              context,
              settings,
              update,
              themeLabelKey: 'background',
            ),
            ...LibraryReaderCommonSettings.navigationHeader(context, editor),
            LibraryReaderChoiceSetting<LibraryMangaMode>(
              label: t('readingMode'),
              value: book?.mangaMode ?? settings.mangaMode,
              options: <LibraryReaderChoice<LibraryMangaMode>>[
                LibraryReaderChoice(LibraryMangaMode.auto, t('modeAuto')),
                LibraryReaderChoice(LibraryMangaMode.paged, t('modePaged')),
                LibraryReaderChoice(
                  LibraryMangaMode.vertical,
                  t('modeVertical'),
                ),
              ],
              onChanged: (value) => LibraryReaderCommonSettings.write(
                editor,
                settings,
                update,
                book: (book) => book.copyWith(mangaMode: value),
                global: (global) => global.copyWith(mangaMode: value),
              ),
            ),
            // The direction in use (the content's hint may decide it in
            // automatic mode); a choice applies at once and is kept for
            // this title.
            LibraryReaderCommonSettings.pageDirection(
              context,
              settings,
              update,
              editor,
              value: _controller.rightToLeft
                  ? LibraryPageDirection.rtl
                  : LibraryPageDirection.ltr,
            ),
            LibraryReaderCommonSettings.turnStyle(
              context,
              settings,
              update,
              editor,
            ),
            if (turnStyle == LibraryPageTurnStyle.curl)
              LibraryReaderSettingNote(t('curlDisabledZoom')),
            LibraryReaderCommonSettings.doublePage(
              context,
              settings,
              update,
              editor,
            ),
            LibraryReaderSettingNote(t('doublePageNotVertical')),
            LibraryReaderCommonSettings.firstPageAlone(
              context,
              settings,
              update,
              editor,
            ),
            ...LibraryReaderCommonSettings.navigationTail(
              context,
              settings,
              update,
            ),
            ...LibraryReaderCommonSettings.bookReset(context, editor),
          ];
        },
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

  String _chapterLabel(BuildContext context, LibraryPageReaderChapter chapter) {
    if (chapter.title.isNotEmpty) return chapter.title;
    final number = chapter.number;
    if (number != null) {
      return LibraryReaderLocale.format(
        context,
        'chapterNumber',
        <String, Object?>{'number': LibraryMangaChapter.formatNumber(number)},
      );
    }
    final volume = chapter.volume;
    if (volume != null) {
      return LibraryReaderLocale.format(
        context,
        'volumeNumber',
        <String, Object?>{'number': LibraryMangaChapter.formatNumber(volume)},
      );
    }
    return chapter.id;
  }

  @override
  Widget build(BuildContext context) {
    final palette = _palette(context);
    final ready = _controller.status == LibraryPageReaderStatus.ready;
    final tracks = widget.content.tracksChapters;
    final pages = _buildContent(context, palette);
    // After the pages: the spread of the current page as just laid out.
    final bookmarked = _shownBookmarks().isNotEmpty;
    // Always shown, the bars never cover the pages: these are laid out
    // between them. The ribbon hangs from the top of the pages.
    final content = LibraryReaderBarsInset(
      enabled: _toolbarAlways,
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          pages,
          LibraryBookmarkRibbon(
            visible: bookmarked && _settings.bookmarkRibbon,
            palette: palette,
          ),
        ],
      ),
    );
    return PopScope<Object?>(
      onPopInvokedWithResult: _onPopped,
      child: LibraryReaderGamepadScope(
        name: 'library_page_reader',
        bindings: gamepadBindings,
        child: AnnotatedRegion<SystemUiOverlayStyle>(
          value: palette.isDark
              ? SystemUiOverlayStyle.light
              : SystemUiOverlayStyle.dark,
          child: Scaffold(
            backgroundColor: palette.background,
            // Showing or hiding the chrome does not rebuild the pages (child).
            body: ListenableBuilder(
              listenable: Listenable.merge(<Listenable>[_chrome, _sliderPage]),
              child: content,
              builder: (context, content) => LibraryReaderChromeOverlay(
                visible: _chrome.visible || !ready,
                content: content!,
                palette: palette,
                // The floating back button closes like the top bar and B.
                onBack: _close,
                // Settings moved to the toolbar (one Settings, one Back).
                topBar: LibraryReaderTopBar(
                  palette: palette,
                  title: widget.content.title,
                  subtitle: tracks
                      ? _chapterLabel(context, _controller.chapter)
                      : widget.content.subtitle,
                  onBack: _close,
                ),
                bottomBar: ready
                    ? _buildBottomBar(context, palette, bookmarked: bookmarked)
                    : null,
              ),
            ),
          ),
        ),
      ),
    );
  }

  /// The toolbar (§ 3.8) below the page slider and the chapter buttons.
  Widget _buildBottomBar(
    BuildContext context,
    LibraryReaderPalette palette, {
    required bool bookmarked,
  }) {
    final tracks = widget.content.tracksChapters;
    final vertical = _vertical;
    String t(String key) => LibraryReaderLocale.text(context, key);
    final slider = Row(
      children: <Widget>[
        if (tracks)
          LibraryReaderIconButton(
            icon: Icons.skip_previous_rounded,
            tooltip: t('previousChapter'),
            onPressed: _controller.hasPreviousChapter
                ? () => unawaited(_controller.previousChapter())
                : null,
            color: palette.chromeForeground,
          ),
        Expanded(
          child: LibraryReaderPageSlider(
            palette: palette,
            page: _sliderPage.value ?? _controller.page,
            pageCount: _controller.pageCount,
            rightToLeft: !vertical && _controller.rightToLeft,
            onChangeStart: (page) {
              _sliderDragging = true;
              _sliderPage.value = page;
              _chrome.hold();
            },
            // Dragging only updates the label: jumping at every page
            // crossed downloaded each of them, ahead of the page the
            // drag stops on.
            onChanged: (page) => _sliderPage.value = page,
            onChangeEnd: (page) {
              // The page chosen is the position, also inside a spread.
              _jumpToPage(page);
              _controller.setPage(page, through: _lastPageShownWith(page));
              _sliderDragging = false;
              _sliderPage.value = null;
              _chrome.release();
            },
          ),
        ),
        if (tracks)
          LibraryReaderIconButton(
            icon: Icons.skip_next_rounded,
            tooltip: t('nextChapter'),
            onPressed: _controller.hasNextChapter
                ? () => unawaited(_controller.nextChapter())
                : null,
            color: palette.chromeForeground,
          ),
      ],
    );
    return LibraryReaderBottomBar(
      palette: palette,
      child: LibraryReaderToolbar(
        palette: palette,
        progress: _toolbarProgress(context),
        onSettings: _openSettings,
        onBookmarks: _openBookmarks,
        onContents: _chaptersAvailable ? _openChapters : null,
        contents: LibraryReaderContents.chapters,
        onLibrary: _close,
        bookmarked: bookmarked,
        slider: slider,
        extra: <Widget>[
          LibraryReaderIconButton(
            icon: vertical
                ? Icons.view_carousel_rounded
                : Icons.view_day_rounded,
            tooltip: t(vertical ? 'switchToPaged' : 'switchToVertical'),
            onPressed: () {
              _chrome.touch();
              _controller.toggleMode();
            },
            color: palette.chromeForeground,
          ),
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context, LibraryReaderPalette palette) {
    switch (_controller.status) {
      case LibraryPageReaderStatus.loading:
        _releaseCurlTextures();
        return _LoadingView(
          palette: palette,
          label: LibraryReaderLocale.text(context, 'loadingPages'),
        );
      case LibraryPageReaderStatus.error:
        _releaseCurlTextures();
        return SafeArea(
          child: LibraryReaderErrorView(
            error: LibraryReaderErrorInfo.from(_controller.error!),
            palette: palette,
            onRetry: () => unawaited(_controller.retry()),
            onClose: _close,
          ),
        );
      case LibraryPageReaderStatus.ready:
        break;
    }
    final mode = _controller.mode;
    _onModeBuilt(mode);
    if (mode == LibraryPageReaderMode.vertical) _releaseCurlTextures();
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = constraints.biggest;
        _updateDecodeSize(size);
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTapUp: (details) => _onTapUp(details, size),
          child: mode == LibraryPageReaderMode.vertical
              ? _buildVertical(context, palette, size)
              : _buildPaged(context, palette),
        );
      },
    );
  }

  Widget _buildPaged(BuildContext context, LibraryReaderPalette palette) {
    final source = _controller.source!;
    final effective = _controller.effective;
    final rightToLeft = effective.rightToLeft;
    final built = _pagedSpreads;
    // A closing reader keeps its layout: it may rotate back to landscape
    // during its transition, for a screen that is going away.
    final spreads =
        _controller.finished &&
            built != null &&
            built.pageCount == source.length
        ? built
        : LibraryPageSpreads(
            pageCount: source.length,
            doublePage: effective.doublePage,
            firstPageAlone: effective.firstPageAlone,
            landscape:
                MediaQuery.orientationOf(context) == Orientation.landscape,
            rightToLeft: rightToLeft,
          );
    _ensurePagedController(spreads);
    final leading = _pagedLeading;
    final count = spreads.length;
    final itemCount = _pagedItemCount;
    final current = _currentItem;
    // The curl style, not zoomed (Reduce Motion gives the style none; the
    // vertical strip never gets here).
    final curl = effective.turnStyle == LibraryPageTurnStyle.curl && !_zoomed;
    if (curl) {
      _curlInUse = true;
    } else {
      _releaseCurlTextures();
    }
    _imageConfiguration = createLocalImageConfiguration(context);
    // Asked by the layer whenever it decides on a curl (drag, d-pad, tap
    // zone): the chapter cards have no face, nor a spread with a page not
    // decoded yet. Their turns stay PageView slides (or jumps), never a curl
    // drawing nothing while the page loads.
    LibraryPageCurlFace? faceOf(int item) {
      final index = item - leading;
      if (index < 0 || index >= count) return null;
      final spread = spreads[index];
      for (final page in spread.pages) {
        if (!_pageDrawable(source, page)) return null;
      }
      return LibraryPageCurlFace.of(spread);
    }

    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        PageView.builder(
          key: ValueKey<String>(
            'paged-${_controller.generation}-$_pagedLayout',
          ),
          controller: _pageController,
          reverse: rightToLeft,
          physics: _zoomed
              ? const NeverScrollableScrollPhysics()
              : const PageScrollPhysics(parent: ClampingScrollPhysics()),
          itemCount: itemCount,
          onPageChanged: _onPagedChanged,
          itemBuilder: (context, index) {
            if (index < leading) return _buildStartCard(context, palette);
            if (index >= leading + count) {
              return _buildEndCard(context, palette);
            }
            final isCurrent = index == current;
            return InteractiveViewer(
              transformationController: isCurrent ? _zoom : null,
              minScale: 1,
              maxScale: 4,
              panEnabled: isCurrent && _zoomed,
              clipBehavior: Clip.hardEdge,
              child: SizedBox.expand(
                child: _buildSpread(
                  context,
                  palette,
                  source,
                  spreads[index - leading],
                  spreads.pageCount,
                ),
              ),
            );
          },
        ),
        // Above the PageView, it takes the horizontal drags it can curl;
        // disabled (another style, zoomed, Reduce Motion: style none), it
        // is out of hit testing and every drag reaches the PageView.
        Positioned.fill(
          child: LibraryPageCurlLayer(
            enabled: curl,
            controller: _curl,
            currentIndex: current,
            itemCount: itemCount,
            faceOf: faceOf,
            render: _renderCurlPage,
            onTurned: _onCurlTurned,
            contentKey: source.key,
            rightToLeft: rightToLeft,
            paperColor: palette.background,
            cache: _textures,
          ),
        ),
      ],
    );
  }

  /// Whether the curl can draw page [page] at once: its texture is ready,
  /// or its image is decoded in the image cache (the curl's render then
  /// clones it before the next frame). A page still loading or that failed
  /// is not.
  bool _pageDrawable(LibraryPageSource source, int page) {
    for (final key in _textures.retained) {
      if (key is LibraryPageTextureKey &&
          key.page == page &&
          key.source == source.key &&
          _textures.contains(key)) {
        return true;
      }
    }
    // The page providers give their image cache key synchronously; any
    // other provider is never curled.
    Object? cacheKey;
    try {
      unawaited(
        _provider(source, page)
            .obtainKey(_imageConfiguration)
            .then<void>(
              (key) => cacheKey = key,
              onError: (Object _, StackTrace _) {},
            ),
      );
    } catch (_) {
      return false;
    }
    final key = cacheKey;
    if (key == null) return false;
    final status = PaintingBinding.instance.imageCache.statusForKey(key);
    return status.keepAlive || (status.live && !status.pending);
  }

  /// The curl is not drawn (vertical strip, loading, error, another page
  /// turn, a zoomed page): its textures are released after this frame, so
  /// they never keep alive decoded pages the image cache has let go. They
  /// are rendered again (from the image cache) when the curl comes back.
  void _releaseCurlTextures() {
    _curlInUse = false;
    if (_texturePurgeScheduled) return;
    if (_textures.textures == 0 && _textures.pendingRenders == 0) return;
    _texturePurgeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _texturePurgeScheduled = false;
      if (mounted && !_curlInUse) _textures.purge();
    });
  }

  /// One item of the paged view: a page on the whole surface, or a spread's
  /// pages in their halves, aligned toward the spine as the curl draws them
  /// ([LibraryPageSpreadLayout]). A pair is announced as one image ("Pages
  /// N and N+1 of M").
  Widget _buildSpread(
    BuildContext context,
    LibraryReaderPalette palette,
    LibraryPageSource source,
    LibraryPageSpread spread,
    int pageCount,
  ) {
    final pair = spread.isPair;
    final layout = LibraryPageSpreadLayout(
      face: LibraryPageCurlFace.of(spread),
      pageBuilder: (context, page, alignment) => LibraryReaderPageImage(
        key: ValueKey<String>('${source.key}#$page'),
        provider: _provider(source, page),
        pageNumber: page + 1,
        fit: BoxFit.contain,
        alignment: alignment,
        labelled: !pair,
        palette: palette,
        onMeasured: (aspect) => _onMeasured(page, aspect),
      ),
    );
    if (!pair) return layout;
    return Semantics(
      container: true,
      image: true,
      label: LibraryReaderLocale.format(
        context,
        'pagesOfTotal',
        <String, Object?>{
          'first': spread.first + 1,
          'second': spread.last + 1,
          'total': pageCount,
        },
      ),
      child: layout,
    );
  }

  Widget _buildVertical(
    BuildContext context,
    LibraryReaderPalette palette,
    Size size,
  ) {
    final widthChanged = _listWidth != 0 && _listWidth != size.width;
    _listWidth = size.width;
    _ensureVerticalController();
    if (widthChanged) {
      // Rotation: keep the same page and the same place inside it.
      final item = _anchorItem;
      final fraction = _anchorFraction;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        final scroll = _scrollController;
        if (!mounted || scroll == null || !scroll.hasClients) return;
        final target =
            _offsetOfItem(item) + _extentOfItem(item, _listWidth) * fraction;
        scroll.jumpTo(target.clamp(0.0, scroll.position.maxScrollExtent));
      });
    }
    final source = _controller.source!;
    final count = source.length;
    final leading = _leading;
    return InteractiveViewer(
      transformationController: _verticalZoom,
      minScale: 1,
      maxScale: 3,
      panEnabled: _verticalZoomed,
      panAxis: PanAxis.horizontal,
      clipBehavior: Clip.hardEdge,
      child: ListView.builder(
        key: ValueKey<String>('vertical-${_controller.generation}'),
        controller: _scrollController,
        scrollCacheExtent: const ScrollCacheExtent.viewport(1),
        padding: EdgeInsets.zero,
        itemCount: leading + count + 1,
        itemExtentBuilder: (index, dimensions) =>
            _extentOfItem(index, dimensions.crossAxisExtent),
        itemBuilder: (context, index) {
          if (index < leading) return _buildStartCard(context, palette);
          if (index >= leading + count) return _buildEndCard(context, palette);
          final page = index - leading;
          return LibraryReaderPageImage(
            key: ValueKey<String>('${source.key}#$page'),
            provider: _provider(source, page),
            pageNumber: page + 1,
            fit: BoxFit.fill,
            palette: palette,
            onMeasured: (aspect) => _onMeasured(page, aspect),
          );
        },
      ),
    );
  }

  Widget _buildStartCard(BuildContext context, LibraryReaderPalette palette) {
    final previous = widget.content.chapters[_controller.chapterIndex - 1];
    return _ChapterCard(
      palette: palette,
      icon: Icons.first_page_rounded,
      lines: <String>[
        LibraryReaderLocale.format(
          context,
          'previousChapterTitle',
          <String, Object?>{'title': _chapterLabel(context, previous)},
        ),
      ],
      action: LibraryReaderTextButton(
        label: LibraryReaderLocale.text(context, 'previousChapter'),
        icon: Icons.skip_previous_rounded,
        palette: palette,
        filled: true,
        onPressed: () => unawaited(_controller.previousChapter(fromEnd: true)),
      ),
    );
  }

  Widget _buildEndCard(BuildContext context, LibraryReaderPalette palette) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    if (!widget.content.tracksChapters) {
      return _ChapterCard(
        palette: palette,
        icon: Icons.menu_book_rounded,
        lines: <String>[t('endOfBook')],
        action: LibraryReaderTextButton(
          label: t('close'),
          icon: Icons.close_rounded,
          palette: palette,
          onPressed: _close,
        ),
      );
    }
    if (!_controller.hasNextChapter) {
      return _ChapterCard(
        palette: palette,
        icon: Icons.done_all_rounded,
        lines: <String>[t('endOfChapter'), t('lastChapterReached')],
        action: LibraryReaderTextButton(
          label: t('close'),
          icon: Icons.close_rounded,
          palette: palette,
          onPressed: _close,
        ),
      );
    }
    final next = widget.content.chapters[_controller.chapterIndex + 1];
    return _ChapterCard(
      palette: palette,
      icon: Icons.last_page_rounded,
      lines: <String>[
        t('endOfChapter'),
        LibraryReaderLocale.format(
          context,
          'nextChapterTitle',
          <String, Object?>{'title': _chapterLabel(context, next)},
        ),
      ],
      action: LibraryReaderTextButton(
        label: t('nextChapter'),
        icon: Icons.skip_next_rounded,
        palette: palette,
        filled: true,
        onPressed: () => unawaited(_controller.nextChapter()),
      ),
    );
  }
}

class _LoadingView extends StatelessWidget {
  const _LoadingView({required this.palette, required this.label});

  final LibraryReaderPalette palette;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          SizedBox(
            width: 32,
            height: 32,
            child: CircularProgressIndicator(
              strokeWidth: 3,
              color: palette.secondaryText,
            ),
          ),
          const SizedBox(height: 14),
          Text(
            label,
            style: TextStyle(color: palette.secondaryText, fontSize: 15),
          ),
        ],
      ),
    );
  }
}

class _ChapterCard extends StatelessWidget {
  const _ChapterCard({
    required this.palette,
    required this.icon,
    required this.lines,
    required this.action,
  });

  final LibraryReaderPalette palette;
  final IconData icon;
  final List<String> lines;
  final Widget action;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Center(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Icon(icon, size: 40, color: palette.secondaryText),
              const SizedBox(height: 12),
              for (var i = 0; i < lines.length; i++)
                Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Text(
                    lines[i],
                    textAlign: TextAlign.center,
                    style: TextStyle(
                      color: i == 0 ? palette.text : palette.secondaryText,
                      fontSize: i == 0 ? 18 : 15,
                      fontWeight: i == 0 ? FontWeight.w600 : FontWeight.w400,
                    ),
                  ),
                ),
              const SizedBox(height: 12),
              action,
            ],
          ),
        ),
      ),
    );
  }
}

/// One page image with its own loading and error states (retry) and the
/// measured aspect ratio reported to the reader.
class LibraryReaderPageImage extends StatefulWidget {
  const LibraryReaderPageImage({
    super.key,
    required this.provider,
    required this.pageNumber,
    required this.fit,
    required this.palette,
    this.alignment = Alignment.center,
    this.labelled = true,
    this.onMeasured,
  });

  final ImageProvider provider;

  /// One-based page number (accessibility label).
  final int pageNumber;
  final BoxFit fit;
  final LibraryReaderPalette palette;

  /// Where the image sits in its box (a spread's pages lean on the spine).
  final Alignment alignment;

  /// Whether the page announces itself ("Page N"). False inside a spread
  /// that announces both its pages; the error view keeps its retry.
  final bool labelled;

  /// Height / width of the decoded image.
  final ValueChanged<double>? onMeasured;

  @override
  State<LibraryReaderPageImage> createState() => _LibraryReaderPageImageState();
}

class _LibraryReaderPageImageState extends State<LibraryReaderPageImage> {
  ImageStream? _stream;
  ImageInfo? _info;
  Object? _error;
  late final ImageStreamListener _listener = ImageStreamListener(
    _onImage,
    onError: _onError,
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _resolve();
  }

  @override
  void didUpdateWidget(covariant LibraryReaderPageImage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.provider != widget.provider) _resolve();
  }

  @override
  void dispose() {
    _stream?.removeListener(_listener);
    _info?.dispose();
    _info = null;
    super.dispose();
  }

  void _resolve({bool force = false}) {
    final stream = widget.provider.resolve(
      createLocalImageConfiguration(context),
    );
    if (!force && _stream?.key != null && stream.key == _stream?.key) return;
    _stream?.removeListener(_listener);
    _stream = stream;
    stream.addListener(_listener);
  }

  void _onImage(ImageInfo info, bool synchronousCall) {
    final image = info.image;
    if (image.width > 0) widget.onMeasured?.call(image.height / image.width);
    if (!mounted) {
      info.dispose();
      return;
    }
    setState(() {
      _info?.dispose();
      _info = info;
      _error = null;
    });
  }

  void _onError(Object error, StackTrace? stackTrace) {
    if (!mounted) return;
    setState(() => _error = error);
  }

  void _retry() {
    PaintingBinding.instance.imageCache.evict(widget.provider);
    _stream?.removeListener(_listener);
    _stream = null;
    setState(() => _error = null);
    _resolve(force: true);
  }

  @override
  Widget build(BuildContext context) {
    final label = LibraryReaderLocale.format(
      context,
      'pageNumber',
      <String, Object?>{'page': widget.pageNumber},
    );
    final info = _info;
    if (info != null) {
      final image = RawImage(
        image: info.image,
        scale: info.scale,
        fit: widget.fit,
        alignment: widget.alignment,
        filterQuality: FilterQuality.medium,
      );
      if (!widget.labelled) return image;
      return Semantics(image: true, label: label, child: image);
    }
    final error = _error;
    if (error != null) {
      return LibraryReaderErrorView(
        error: LibraryReaderErrorInfo.from(error),
        palette: widget.palette,
        compact: true,
        onRetry: _retry,
      );
    }
    final placeholder = Center(
      child: Text(
        '${widget.pageNumber}',
        style: TextStyle(
          color: widget.palette.secondaryText.withValues(alpha: 0.6),
          fontSize: 28,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
    if (!widget.labelled) return ExcludeSemantics(child: placeholder);
    return Semantics(label: label, child: placeholder);
  }
}
