import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart' show ScrollCacheExtent;
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_manga_models.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_page_reader_content.dart';
import 'library_page_reader_controller.dart';
import 'library_page_source.dart';
import 'library_reader_chrome.dart';
import 'library_reader_errors.dart';
import 'library_reader_gamepad.dart';
import 'library_reader_palette.dart';
import 'library_reader_sheets.dart';
import 'library_reader_system.dart';

/// Comic / manga reader for online chapters and CBZ books.
///
/// Pages are drawn edge to edge; only the chrome stays inside the safe
/// area. Paged mode (left-to-right or right-to-left) zooms each page with a
/// pinch or a double tap; vertical mode is a lazy continuous strip
/// (webtoons) that also zooms with a pinch. Pages are decoded at the
/// viewport size (capped; the width alone in vertical mode) and the
/// neighbours are prefetched.
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

  // Paged mode.
  PageController? _pageController;
  int _pagedGeneration = -1;
  int _pagedLeading = 0;
  final TransformationController _zoom = TransformationController();
  bool _zoomed = false;
  bool _atStartCard = false;
  bool _atEndCard = false;

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

  @visibleForTesting
  LibraryPageReaderController get controller => _controller;

  @visibleForTesting
  bool get chromeVisible => _chrome.visible;

  @visibleForTesting
  bool get atEndCard => _atEndCard;

  /// Whether the current page (paged) or the strip (vertical) is zoomed.
  @visibleForTesting
  bool get zoomed => _vertical ? _verticalZoomed : _zoomed;

  @visibleForTesting
  bool get atStartCard => _atStartCard;

  /// Controller actions of the reader (d-pad, A, B, bumpers, Start).
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
        start: _openSettings,
      );

  bool get _vertical => _controller.mode == LibraryPageReaderMode.vertical;

  @override
  void initState() {
    super.initState();
    _store = widget.store ?? LibraryReadingStore.instance;
    _settings = _store.settings;
    _controller = LibraryPageReaderController(
      content: widget.content,
      store: _store,
    );
    _chrome = LibraryReaderChromeController();
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
    unawaited(_system.start(_settings));
    await _controller.start();
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
    _pendingTap?.cancel();
    _zoomAnimation?.dispose();
    _store.removeListener(_onStore);
    _controller.removeListener(_onController);
    _controller.dispose();
    _chrome.dispose();
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
    final settings = _store.settings;
    if (settings == _settings || !mounted) return;
    final previous = _settings;
    setState(() => _settings = settings);
    if (previous.mangaMode != settings.mangaMode) {
      _controller.clearModeOverride();
    }
    _system.update(settings);
  }

  void _onController() {
    if (!mounted) return;
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
    _pageController?.nextPage(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
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
    _pageController?.previousPage(
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
    );
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
        scroll.animateTo(
          offset,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOut,
        );
      } else {
        scroll.jumpTo(offset);
      }
      return;
    }
    final pages = _pageController;
    if (pages == null || !pages.hasClients) return;
    if (animate) {
      pages.animateToPage(
        _pagedLeading + target,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      );
    } else {
      pages.jumpToPage(_pagedLeading + target);
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
    final count = _controller.pageCount;
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
      _controller.setPage(count - 1);
      return;
    }
    if (_atStartCard || _atEndCard) {
      setState(() {
        _atStartCard = false;
        _atEndCard = false;
      });
    }
    final page = index - leading;
    if (page != _controller.page && !_sliderDragging) {
      unawaited(HapticFeedback.selectionClick().catchError((Object _) {}));
      if (_chrome.visible) _chrome.hideAfterTurn();
    }
    _controller.setPage(page);
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
    // Downloads of pages the reader moved away from stop: they would hold
    // the site's request slots ahead of the page being read.
    source.cancelPrefetchOutside(page - 2, page + 3);
    for (final index in <int>[page + 1, page + 2, page - 1]) {
      if (index >= 0 && index < source.length) source.prefetch(index);
    }
    if (_vertical) return;
    // Decode the next and previous pages ahead in paged mode.
    for (final index in <int>[page + 1, page - 1]) {
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

  void _ensurePagedController() {
    if (_pageController != null && _pagedGeneration == _controller.generation) {
      return;
    }
    _disposeLater(_pageController);
    _pagedGeneration = _controller.generation;
    _pagedLeading = _leading;
    _atEndCard = false;
    _atStartCard = false;
    _resetZoom();
    _pageController = PageController(
      initialPage: _pagedLeading + _controller.page,
    );
  }

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

  // ---------------------------------------------------------- settings --

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
          return <LibraryReaderSettingItem>[
            LibraryReaderChoiceSetting<LibraryMangaMode>(
              label: t('readingMode'),
              value: settings.mangaMode,
              options: <LibraryReaderChoice<LibraryMangaMode>>[
                LibraryReaderChoice(LibraryMangaMode.auto, t('modeAuto')),
                LibraryReaderChoice(LibraryMangaMode.paged, t('modePaged')),
                LibraryReaderChoice(
                  LibraryMangaMode.vertical,
                  t('modeVertical'),
                ),
              ],
              onChanged: (value) => update(settings.copyWith(mangaMode: value)),
            ),
            // The direction in use (the content's hint may decide it in
            // automatic mode); a choice applies at once and is stored for
            // books without a hint.
            LibraryReaderChoiceSetting<LibraryPageDirection>(
              label: t('pageDirection'),
              value: _controller.rightToLeft
                  ? LibraryPageDirection.rtl
                  : LibraryPageDirection.ltr,
              options: <LibraryReaderChoice<LibraryPageDirection>>[
                LibraryReaderChoice(
                  LibraryPageDirection.ltr,
                  t('directionLtr'),
                ),
                LibraryReaderChoice(
                  LibraryPageDirection.rtl,
                  t('directionRtl'),
                ),
              ],
              onChanged: (value) {
                _controller.overrideDirection(value);
                update(settings.copyWith(pageDirection: value));
              },
            ),
            LibraryReaderCommonSettings.theme(
              context,
              settings,
              update,
              labelKey: 'background',
            ),
            ...LibraryReaderCommonSettings.toggles(context, settings, update),
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
              child: _buildContent(context, palette),
              builder: (context, content) => LibraryReaderChromeOverlay(
                visible: _chrome.visible || !ready,
                content: content!,
                topBar: LibraryReaderTopBar(
                  palette: palette,
                  title: widget.content.title,
                  subtitle: tracks
                      ? _chapterLabel(context, _controller.chapter)
                      : widget.content.subtitle,
                  onBack: _close,
                  actions: <Widget>[
                    LibraryReaderIconButton(
                      icon: Icons.tune_rounded,
                      tooltip: LibraryReaderLocale.text(context, 'settings'),
                      onPressed: _openSettings,
                      color: palette.chromeForeground,
                    ),
                  ],
                ),
                bottomBar: ready ? _buildBottomBar(context, palette) : null,
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomBar(BuildContext context, LibraryReaderPalette palette) {
    final tracks = widget.content.tracksChapters;
    final vertical = _vertical;
    String t(String key) => LibraryReaderLocale.text(context, key);
    return LibraryReaderBottomBar(
      palette: palette,
      child: Row(
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
                _jumpToPage(page);
                _controller.setPage(page);
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
        return _LoadingView(
          palette: palette,
          label: LibraryReaderLocale.text(context, 'loadingPages'),
        );
      case LibraryPageReaderStatus.error:
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
    _ensurePagedController();
    final source = _controller.source!;
    final count = source.length;
    final leading = _pagedLeading;
    final current = leading + _controller.page;
    return PageView.builder(
      key: ValueKey<String>('paged-${_controller.generation}'),
      controller: _pageController,
      reverse: _controller.rightToLeft,
      physics: _zoomed
          ? const NeverScrollableScrollPhysics()
          : const PageScrollPhysics(parent: ClampingScrollPhysics()),
      itemCount: leading + count + 1,
      onPageChanged: _onPagedChanged,
      itemBuilder: (context, index) {
        if (index < leading) return _buildStartCard(context, palette);
        if (index >= leading + count) return _buildEndCard(context, palette);
        final page = index - leading;
        final isCurrent = index == current;
        return InteractiveViewer(
          transformationController: isCurrent ? _zoom : null,
          minScale: 1,
          maxScale: 4,
          panEnabled: isCurrent && _zoomed,
          clipBehavior: Clip.hardEdge,
          child: SizedBox.expand(
            child: LibraryReaderPageImage(
              key: ValueKey<String>('${source.key}#$page'),
              provider: _provider(source, page),
              pageNumber: page + 1,
              fit: BoxFit.contain,
              palette: palette,
              onMeasured: (aspect) => _onMeasured(page, aspect),
            ),
          ),
        );
      },
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
    this.onMeasured,
  });

  final ImageProvider provider;

  /// One-based page number (accessibility label).
  final int pageNumber;
  final BoxFit fit;
  final LibraryReaderPalette palette;

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
      return Semantics(
        image: true,
        label: label,
        child: RawImage(
          image: info.image,
          scale: info.scale,
          fit: widget.fit,
          filterQuality: FilterQuality.medium,
        ),
      );
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
    return Semantics(
      label: label,
      child: Center(
        child: Text(
          '${widget.pageNumber}',
          style: TextStyle(
            color: widget.palette.secondaryText.withValues(alpha: 0.6),
            fontSize: 28,
            fontWeight: FontWeight.w600,
          ),
        ),
      ),
    );
  }
}
