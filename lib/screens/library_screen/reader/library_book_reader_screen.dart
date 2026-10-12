import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart'
    show RenderSliver, ScrollCacheExtent, ScrollDirection;
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_http.dart' show LibraryCancelToken;
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_book_pages_view.dart';
import 'library_page_curl.dart';
import 'library_page_spreads.dart';
import 'library_page_textures.dart';
import 'library_reader_chrome.dart';
import 'library_reader_effective_settings.dart';
import 'library_reader_errors.dart';
import 'library_reader_gamepad.dart';
import 'library_reader_palette.dart';
import 'library_reader_sheets.dart';
import 'library_reader_system.dart';
import 'library_reflow_paginator.dart';
import 'library_reflow_source.dart';
import 'library_reflow_view.dart';

/// Opens the reflowable source of a book (may throw a typed error).
typedef LibraryReflowSourceOpener = Future<LibraryReflowSource> Function();

/// Opens an https link outside NeoStation.
typedef LibraryExternalLinkLauncher = Future<bool> Function(Uri uri);

class _ChapterData {
  _ChapterData(this.units);

  final List<LibraryReflowUnit> units;
}

/// Where the pages layout draws its pages, for one body size and settings.
@immutable
class _BookPagesGeometry {
  const _BookPagesGeometry({
    required this.area,
    required this.pageSize,
    required this.padding,
    required this.style,
    required this.rule,
    required this.devicePixelRatio,
  });

  /// The pager (and the page curl above it) in the reader's body.
  final Rect area;

  /// One page: the whole [area], or half of it in a spread.
  final Size pageSize;
  final EdgeInsets padding;
  final LibraryReflowStyle style;
  final LibraryBookSpreadRule rule;
  final double devicePixelRatio;

  /// Whether a window laid out for this geometry can be shown in [other]
  /// (the same pages at the same place; the typography may differ while
  /// the pages are laid out again).
  bool fits(_BookPagesGeometry other) =>
      area == other.area && pageSize == other.pageSize && rule == other.rule;
}

/// Reflowable reader for EPUB and plain text.
///
/// Two layouts (Build 447, docs/library-books-3d-plan.md § 3.5), chosen by
/// [LibraryTextLayout] (session, then the book's setting, then the global
/// one; pages by default):
///
/// * Pages: [LibraryReflowPaginator] lays the chapters out as pages of
///   whole lines; a `PageView` of spreads (the shown one and its
///   neighbours) turns them with the page curl
///   ([LibraryPageCurlLayer], [LibraryPageTurnStyle]), a slide or a jump,
///   two pages side by side in landscape ([LibraryPageSpreads] rules), in
///   [rightToLeft] order when the book asks for it.
/// * Continuous scroll (the 440 reader): one chapter (EPUB document, TXT
///   section) is laid out lazily at a time: the scroll view is centred on
///   the block being read, earlier blocks grow upwards in a reverse sliver,
///   so the reader opens anywhere without laying out what comes before.
///   Neighbouring chapters are appended as the reader scrolls.
///
/// The position (first visible block + character offset) survives font,
/// theme, layout and orientation changes and is stored as an EPUB CFI or a
/// `txt:b:o` location.
class LibraryBookReaderScreen extends StatefulWidget {
  const LibraryBookReaderScreen({
    super.key,
    required this.open,
    required this.progressKey,
    required this.title,
    this.subtitle,
    this.coverUrl,
    this.initialFraction,
    this.store,
    this.orientation,
    this.launchExternal,
    this.rightToLeft = false,
  });

  final LibraryReflowSourceOpener open;
  final String progressKey;
  final String title;

  /// Author, shown under the title.
  final String? subtitle;
  final String? coverUrl;

  /// Position to open at when nothing is saved for [progressKey] (former
  /// bookmarks).
  final double? initialFraction;
  final LibraryReadingStore? store;
  final LibraryReaderOrientation? orientation;

  /// Opens external links (defaults to the system browser).
  final LibraryExternalLinkLauncher? launchExternal;

  /// The book's EPUB `page-progression-direction` (Build 447,
  /// docs/library-books-3d-plan.md § 3.5): in the pages layout, page order
  /// and hinge are mirrored; no effect on the continuous scroll.
  final bool rightToLeft;

  @override
  State<LibraryBookReaderScreen> createState() =>
      LibraryBookReaderScreenState();
}

class LibraryBookReaderScreenState extends State<LibraryBookReaderScreen>
    with WidgetsBindingObserver, TickerProviderStateMixin {
  late final LibraryReadingStore _store;
  late final LibraryReaderChromeController _chrome;
  late final LibraryReaderSystemSession _system;
  late LibraryReaderSettings _settings;
  late final LibraryReflowImageCache _images;

  /// This book's navigation settings (`LibraryReadingStore.bookSettingsFor`).
  LibraryReaderBookSettings? _bookSettings;

  /// Layout chosen for this session by [setTextLayout] (before the book's
  /// setting, which it also writes).
  LibraryTextLayout? _sessionTextLayout;

  /// Layout shown.
  LibraryTextLayout _activeLayout = LibraryTextLayout.pages;
  bool _enteringScroll = false;

  /// The page start shown when the scroll layout was entered: back in the
  /// pages layout without having moved, the same page is shown again (the
  /// scroll layout reads the line holding it, which can start earlier).
  LibraryReflowPosition? _switchAnchor;
  bool _movedSinceSwitch = false;

  // ------------------------------------------------- pages layout state --

  LibraryReflowPaginator? _paginator;

  /// Layout generation of [_paginator] (typography, page size, margins).
  int _pagesLayout = 0;

  /// The geometry last given to [_paginator].
  _BookPagesGeometry? _pagesGeometry;

  /// Reading position of the pages layout: the start of the page last
  /// turned to, or the position opened (saved location) or jumped to
  /// (contents, link, slider). The page shown always holds it; a relayout
  /// (typography, rotation, two pages) keeps it, so the same first words
  /// stay on the page whatever the number of relayouts, and it is the
  /// location saved.
  LibraryReflowPosition _pageAnchor = LibraryReflowPosition.start;

  /// The window of spreads of the pager: the one shown and, when known, its
  /// neighbours. Its pages come from layout [_windowLayout], laid out for
  /// [_windowGeometry].
  LibraryBookSpread? _spread;
  LibraryBookSpread? _previous;
  LibraryBookSpread? _next;
  Object? _previousError;
  Object? _nextError;
  bool _hasPrevious = false;
  bool _hasNext = false;
  LibraryBookSpread? _previousRequestedFor;
  LibraryBookSpread? _nextRequestedFor;
  _BookPagesGeometry? _windowGeometry;
  int _windowLayout = -1;

  /// Identity of the pager (a new `PageView` per window laid out).
  int _windowGeneration = 0;

  /// A window was shown since the book opened: until then the body keeps
  /// saying the book is loading (no second message for a frame).
  bool _windowShownOnce = false;

  /// Error of the last attempt to lay out the page shown.
  Object? _pagesError;
  bool _relocateScheduled = false;
  bool _relocating = false;
  int _relocateRequest = 0;

  /// The pager rests on a neighbour still being laid out (1 next, -1
  /// previous): it becomes the spread shown once known.
  int _arrivalPending = 0;

  /// A turn asked while its neighbour was being laid out (1, -1).
  int _queuedTurn = 0;

  /// Item index of the page curl = [_virtualOrigin] + pager index: it moves
  /// with every turn (the curl renders the new neighbours ahead).
  int _virtualOrigin = 1 << 28;
  static const int _virtualItems = 1 << 30;
  bool _curlRefreshPending = false;
  PageController? _pager;
  LibraryPageCurlController? _curl;
  LibraryPageTextureCache? _textures;

  /// Chapter whose page count is awaited (the "Page N of M" label).
  int? _watchedChapter;
  LibraryReflowPaginator? _watchedPaginator;

  /// Space below the last line of a page, above the safe area.
  static const double _pageBottomGap = 16;

  /// Added to the margins of each half of a spread (the spine).
  static const double _spineGutter = 8;

  LibraryReflowSource? _source;
  Object? _openError;
  bool _opening = true;

  /// Display units of the chapters in the window and next to it only:
  /// farther ones are released (the source keeps a small cache).
  final Map<int, _ChapterData> _chapters = <int, _ChapterData>{};
  final Map<int, Object> _chapterErrors = <int, Object>{};
  final Set<int> _loading = <int>{};

  /// Chapters laid out in the scroll view. It grows while the reader
  /// scrolls on and is cut back around the chapter being read once it
  /// spans more than [_maxWindowChapters].
  int _windowStart = 0;
  int _windowEnd = 0;
  static const int _maxWindowChapters = 3;

  /// Scroll offset of the next scroll view, when it must show its anchor
  /// unit exactly where the previous view showed it.
  double? _nextScrollOffset;
  Timer? _trimTimer;

  /// Fingers on the text: the window is never cut back under them.
  int _pointers = 0;

  LibraryReflowPosition _anchor = LibraryReflowPosition.start;
  int _anchorUnit = 0;
  int _anchorUnitOffset = 0;
  int _generation = 0;

  /// True from a re-anchor until the frame laid out after the jump to the
  /// anchored line: until then the render boxes still describe the previous
  /// layout, so the position is [_anchor], never read from them.
  bool _anchorPending = false;
  ScrollController? _scroll;
  final LibraryReflowUnitRegistry _registry = LibraryReflowUnitRegistry();
  final GlobalKey _viewportKey = GlobalKey();

  LibraryReflowPosition? _lastPosition;

  /// Position shown by the chrome (percentage, chapter title); updating it
  /// never rebuilds the text.
  final ValueNotifier<LibraryReflowPosition?> _shownPosition =
      ValueNotifier<LibraryReflowPosition?>(null);
  DateTime _lastTrack = DateTime.fromMillisecondsSinceEpoch(0);
  bool _trackScheduled = false;
  bool _loadMoreScheduled = false;
  Timer? _saveTimer;
  bool _dirty = false;
  double? _lastWidth;
  final ValueNotifier<double?> _sliderValue = ValueNotifier<double?>(null);
  bool _closing = false;

  /// The route was popped: the saved position no longer changes.
  bool _leaving = false;

  /// The saved location could not be restored (an error, not an unknown
  /// location): it is not overwritten until the user moves.
  bool _keepSavedLocation = false;

  @visibleForTesting
  LibraryReflowSource? get source => _source;

  /// Reading position: in the scroll layout the first visible block, in
  /// the pages layout the position the page shown holds (the start of the
  /// page last turned to, or the position opened or jumped to).
  @visibleForTesting
  LibraryReflowPosition? get currentPosition =>
      _activeLayout == LibraryTextLayout.pages
      ? _lastPosition
      : _readingPosition();

  @visibleForTesting
  bool get chromeVisible => _chrome.visible;

  /// Chapters whose display units are in memory (tests).
  @visibleForTesting
  Set<int> get chaptersInMemory => Set<int>.of(_chapters.keys);

  /// First and last chapter laid out (tests).
  @visibleForTesting
  (int, int) get window => (_windowStart, _windowEnd);

  /// The layout shown: pages, or the continuous scroll.
  LibraryTextLayout get textLayout => _activeLayout;

  /// Pages layout: the spread shown, once laid out (tests).
  @visibleForTesting
  LibraryBookSpread? get shownSpread => _spread;

  /// Pages layout: the neighbours of the spread shown, once laid out.
  @visibleForTesting
  (LibraryBookSpread?, LibraryBookSpread?) get neighbourSpreads =>
      (_previous, _next);

  @visibleForTesting
  LibraryReflowPaginator? get paginator => _paginator;

  @visibleForTesting
  LibraryPageCurlController? get curl => _curl;

  @visibleForTesting
  LibraryPageTextureCache? get pageTextures => _textures;

  @visibleForTesting
  LibraryReaderGamepadBindings get gamepadBindings {
    if (_activeLayout == LibraryTextLayout.pages) {
      return LibraryReaderGamepadBindings(
        // Up / down: previous / next page in reading order; left / right:
        // the page on that side (right to left, the next page is on the
        // left). Y stays free for the bookmarks.
        up: () => _turnPage(forward: false),
        down: () => _turnPage(forward: true),
        left: () => _turnVisual(left: true),
        right: () => _turnVisual(left: false),
        leftBumper: () => _goToChapter(-1),
        rightBumper: () => _goToChapter(1),
        select: _openError != null && !_opening
            ? () => unawaited(_open())
            : _pagesError != null
            ? _retryPages
            : _chrome.toggle,
        back: _close,
        x: _openToc,
        start: _openSettings,
      );
    }
    return LibraryReaderGamepadBindings(
      up: () => _scrollBy(-0.3),
      down: () => _scrollBy(0.3),
      left: () => _scrollBy(-0.9),
      right: () => _scrollBy(0.9),
      leftBumper: () => _goToChapter(-1),
      rightBumper: () => _goToChapter(1),
      // A retries a book that failed to open (the button is touch only).
      select: _openError != null && !_opening
          ? () => unawaited(_open())
          : _chrome.toggle,
      back: _close,
      x: _openToc,
      start: _openSettings,
    );
  }

  /// Where the line being read is placed (opening, jumps, new typography)
  /// and read back from: just below the back control, which stays on
  /// screen while the bars are hidden, so that line is never under it.
  /// Positions are text locations (EPUB CFI, `txt:b:o`): placing and
  /// reading use this same line, so they stay valid.
  double get _topInset => libraryReaderBackControlBottom(context) + 4;

  @override
  void initState() {
    super.initState();
    _store = widget.store ?? LibraryReadingStore.instance;
    _settings = _store.settings;
    _bookSettings = _store.bookSettingsFor(widget.progressKey);
    _activeLayout = _desiredLayout();
    _chrome = LibraryReaderChromeController();
    _system = LibraryReaderSystemSession(orientation: widget.orientation);
    _images = LibraryReflowImageCache(_loadResource);
    _store.addListener(_onStore);
    WidgetsBinding.instance.addObserver(this);
    unawaited(_open());
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
    _trimTimer?.cancel();
    _store.removeListener(_onStore);
    _chrome.dispose();
    _shownPosition.dispose();
    _sliderValue.dispose();
    _scroll?.dispose();
    _pager?.dispose();
    _curl?.removeListener(_onCurlChanged);
    _curl?.dispose();
    _textures?.dispose();
    _paginator?.dispose();
    _images.clear();
    unawaited(_system.stop());
    unawaited(_store.flush().catchError((Object _) {}));
    final source = _source;
    if (source != null) unawaited(source.close().catchError((Object _) {}));
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.hidden ||
        state == AppLifecycleState.detached) {
      _track(force: true);
      _saveNow();
      unawaited(_store.flush().catchError((Object _) {}));
    }
  }

  Future<Uint8List> _loadResource(String href) {
    final source = _source;
    if (source == null) return Future<Uint8List>.error(StateError('closed'));
    return source.resource(href);
  }

  void _onStore() {
    if (!mounted) return;
    final settings = _store.settings;
    final book = _store.bookSettingsFor(widget.progressKey);
    final bookChanged = book != _bookSettings;
    if (settings == _settings && !bookChanged) return;
    if (bookChanged) {
      // The book's layout chosen elsewhere (settings, "revert to general
      // settings") replaces the one chosen in this session.
      if (book?.textLayout != _bookSettings?.textLayout) {
        _sessionTextLayout = null;
      }
      _bookSettings = book;
    }
    if (settings != _settings) {
      final previous = _settings;
      final relayout =
          previous.fontSize != settings.fontSize ||
          previous.lineHeight != settings.lineHeight ||
          previous.fontFamily != settings.fontFamily ||
          previous.margin != settings.margin ||
          previous.justify != settings.justify;
      // The pages layout keeps its own anchor: the paginator is updated
      // when the pages are built again.
      if (relayout &&
          _source != null &&
          _activeLayout == LibraryTextLayout.scroll) {
        // Keep reading the same words with the new typography.
        final position = _readingPosition();
        if (position != null) {
          _lastPosition = position;
          _setAnchor(position);
        }
      }
      setState(() => _settings = settings);
      _system.update(settings);
    } else {
      setState(() {});
    }
    _applyLayout(_desiredLayout());
  }

  // ------------------------------------------------------- text layout --

  LibraryReaderEffectiveSettings _effective({bool reduceMotion = false}) =>
      LibraryReaderEffectiveSettings.resolve(
        global: _settings,
        book: _bookSettings,
        // Reduce Motion: pages are turned without animation.
        session: reduceMotion
            ? const LibraryReaderSessionOverrides(
                turnStyle: LibraryPageTurnStyle.none,
              )
            : null,
      );

  /// Session choice, then the book's setting, then the global one.
  LibraryTextLayout _desiredLayout() =>
      _sessionTextLayout ?? _effective().textLayout;

  /// The book's `page-progression-direction` ([LibraryBookReaderScreen.
  /// rightToLeft]) unless a direction was chosen for this book.
  bool get _rightToLeft {
    final direction = _bookSettings?.pageDirection;
    return direction == null
        ? widget.rightToLeft
        : direction == LibraryPageDirection.rtl;
  }

  /// Shows the book in [layout] from now on, at the same words (the scroll
  /// view starts at the first line of the page shown; the pages layout
  /// shows the page holding the first line read), and keeps this choice
  /// for the book (`LibraryReaderBookSettings.textLayout`).
  void setTextLayout(LibraryTextLayout layout) {
    if (!mounted) return;
    _sessionTextLayout = layout;
    final key = widget.progressKey;
    if (key.isNotEmpty) {
      final next =
          (_store.bookSettingsFor(key) ??
                  _bookSettings ??
                  const LibraryReaderBookSettings())
              .copyWith(textLayout: layout);
      // Known before the store notifies: not taken for a change made
      // elsewhere.
      _bookSettings = next;
      _store.updateBookSettings(key, next);
    }
    _applyLayout(layout);
  }

  void _applyLayout(LibraryTextLayout layout) {
    if (!mounted || layout == _activeLayout) return;
    final source = _source;
    if (_opening ||
        _openError != null ||
        source == null ||
        source.chapterCount == 0) {
      // Applied when the book opens.
      setState(() => _activeLayout = layout);
      return;
    }
    if (layout == LibraryTextLayout.pages) {
      _enterPages();
    } else {
      unawaited(_enterScroll());
    }
  }

  /// Scroll -> pages: the page holding the first line read.
  void _enterPages() {
    final position = _readingPosition() ?? _lastPosition ?? _anchor;
    final remembered = _switchAnchor;
    final anchor = remembered != null && !_movedSinceSwitch
        ? remembered
        : position;
    _switchAnchor = null;
    if (anchor != _lastPosition) {
      _dirty = true;
      _scheduleSave();
    }
    setState(() {
      _leaveScrollView();
      _activeLayout = LibraryTextLayout.pages;
      _pageAnchor = anchor;
      _clearWindow();
    });
    _lastPosition = anchor;
    _shownPosition.value = anchor;
  }

  /// Pages -> scroll: the scroll view starts at the first line of the page
  /// shown.
  Future<void> _enterScroll() async {
    final source = _source;
    if (source == null || _enteringScroll) return;
    final start = _spread?.first.start ?? _pageAnchor;
    _enteringScroll = true;
    try {
      await source.loadChapter(start.chapter);
    } catch (error) {
      _enteringScroll = false;
      if (!mounted) return;
      final info = LibraryReaderErrorInfo.from(error);
      _message(info.messageKey, detail: info.detail);
      return;
    }
    _enteringScroll = false;
    if (!mounted ||
        _activeLayout == LibraryTextLayout.scroll ||
        _desiredLayout() != LibraryTextLayout.scroll) {
      return;
    }
    _switchAnchor = _pageAnchor;
    _movedSinceSwitch = false;
    if (start != _lastPosition) {
      _dirty = true;
      _scheduleSave();
    }
    setState(() {
      _leavePages();
      _activeLayout = LibraryTextLayout.scroll;
      _ensureChapterData(start.chapter);
      _chapterErrors.remove(start.chapter);
      _windowStart = start.chapter;
      _windowEnd = start.chapter;
      _releaseFarChapters();
      _setAnchor(start);
    });
    _lastPosition = start;
    _shownPosition.value = start;
  }

  /// Releases the scroll view's state (its controller after the frame that
  /// removes it); pending re-anchoring callbacks do nothing.
  void _leaveScrollView() {
    _generation++;
    _anchorPending = false;
    _nextScrollOffset = null;
    _trimTimer?.cancel();
    _pointers = 0;
    final scroll = _scroll;
    _scroll = null;
    if (scroll != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => scroll.dispose());
    }
    _chapters.clear();
    _chapterErrors.clear();
  }

  /// Stops the pagination (complete chapters stay memoized), the turn and
  /// the page textures.
  void _leavePages() {
    final paginator = _paginator;
    if (paginator != null) unawaited(paginator.cancel());
    _relocateRequest++;
    _relocating = false;
    _curl?.reset();
    _textures?.purge();
    _clearWindow();
  }

  void _close() {
    if (_closing || !mounted) return;
    _closing = true;
    // Saved before the pop, while the screens below can rebuild for it.
    _track(force: true);
    _saveNow();
    Navigator.of(context).maybePop().then((popped) {
      if (!popped) _closing = false;
    });
  }

  /// The route was popped (Back, B, the iOS back swipe): the screen below
  /// is on stage from now on, so landscape is restored now rather than in
  /// [dispose], after the reverse transition, and the position is saved
  /// now (from [dispose], the store would notify the screens below while
  /// the widget tree is locked). The position is then frozen: the closing
  /// view can still move (rotated back to landscape, it is laid out
  /// again). [dispose] stays the fallback (the session stops once).
  void _onPopped(bool didPop, Object? _) {
    if (!didPop) return;
    _track(force: true);
    _saveNow();
    _leaving = true;
    _saveTimer?.cancel();
    unawaited(_system.stop());
  }

  // ----------------------------------------------------------- opening --

  Future<void> _open() async {
    try {
      await _store.load();
    } catch (_) {
      // Works in memory.
    }
    if (!mounted) return;
    _settings = _store.settings;
    _bookSettings = _store.bookSettingsFor(widget.progressKey);
    unawaited(_system.start(_settings));
    setState(() {
      _opening = true;
      _openError = null;
    });
    try {
      final source = _source ?? await widget.open();
      if (!mounted) {
        unawaited(source.close());
        return;
      }
      _source = source;
      if (source.chapterCount == 0) {
        setState(() => _opening = false);
        return;
      }
      final (start, restoreError) = await _startPosition(source);
      await source.loadChapter(start.chapter);
      if (!mounted) return;
      _activeLayout = _desiredLayout();
      if (_activeLayout == LibraryTextLayout.pages) {
        // Laid out by the paginator once the pages are built (a chapter it
        // cannot read is shown as an error with Retry).
        _pageAnchor = start;
        _clearWindow();
      } else {
        final data = _ensureChapterData(start.chapter);
        if (data == null) throw StateError('chapter not loaded');
        _windowStart = start.chapter;
        _windowEnd = start.chapter;
        _releaseFarChapters();
        _setAnchor(start);
      }
      _lastPosition = start;
      _shownPosition.value = start;
      // Opening counts as reading (the book moves to "continue reading"),
      // unless the saved location failed to load: the book shows its
      // beginning, but the saved location stays until the user moves.
      _keepSavedLocation = restoreError != null;
      if (!_keepSavedLocation) {
        _dirty = true;
        _scheduleSave();
      }
      setState(() => _opening = false);
      if (restoreError != null) {
        _message(
          'positionNotRestored',
          detail: LibraryReaderErrorInfo.from(restoreError).detail,
        );
      }
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _opening = false;
        _openError = error;
      });
    }
  }

  /// Where the book opens, and the error that prevented restoring the
  /// saved location, if any.
  ///
  /// A saved location this book does not know (null: malformed, outside
  /// the spine) can never be restored: the book starts over. An error
  /// while resolving it (worker stopped, file or chapter unreadable) may be
  /// temporary: the book shows its beginning but the caller keeps the
  /// saved location.
  Future<(LibraryReflowPosition, Object?)> _startPosition(
    LibraryReflowSource source,
  ) async {
    final saved = _store.progressFor(widget.progressKey)?.location;
    if (saved != null && saved.isNotEmpty) {
      LibraryReflowPosition? position;
      try {
        position = await source.resolveLocation(saved);
      } catch (error) {
        return (LibraryReflowPosition.start, error);
      }
      if (position != null &&
          position.chapter >= 0 &&
          position.chapter < source.chapterCount) {
        return (position, null);
      }
    }
    final fraction = widget.initialFraction;
    if (fraction != null && fraction > 0) {
      try {
        return (await source.positionAtFraction(fraction), null);
      } catch (_) {}
    }
    return (LibraryReflowPosition.start, null);
  }

  /// The user moved (scroll, page turn, jump): the position shown is now
  /// the one to save, also after a saved location failed to load.
  void _userMoved() {
    _movedSinceSwitch = true;
    if (!_keepSavedLocation) return;
    _keepSavedLocation = false;
    _dirty = true;
    _scheduleSave();
  }

  _ChapterData? _ensureChapterData(int chapter) {
    final existing = _chapters[chapter];
    if (existing != null) return existing;
    final blocks = _source?.loadedChapter(chapter);
    if (blocks == null) return null;
    return _chapters[chapter] = _ChapterData(
      libraryReflowUnits(chapter, blocks),
    );
  }

  // ------------------------------------------------------------- anchor --

  /// Rebuilds the scroll view centred on [position].
  void _setAnchor(LibraryReflowPosition position) {
    final data = _ensureChapterData(position.chapter);
    var unitIndex = 0;
    var inUnit = 0;
    if (data != null && data.units.isNotEmpty) {
      unitIndex = data.units.length - 1;
      for (var i = 0; i < data.units.length; i++) {
        final unit = data.units[i];
        if (unit.block < position.block) continue;
        if (unit.block > position.block) {
          unitIndex = i;
          inUnit = 0;
          break;
        }
        if (position.offset < unit.end || unit.isLastPiece) {
          unitIndex = i;
          inUnit = (position.offset - unit.start).clamp(0, unit.length);
          break;
        }
      }
      if (unitIndex == data.units.length - 1 &&
          data.units.last.block < position.block) {
        inUnit = data.units.last.length;
      }
    }
    _anchor = position;
    _anchorUnit = unitIndex;
    _anchorUnitOffset = inUnit;
    _nextScrollOffset = null;
    _replaceView();
  }

  /// Replaces the scroll view in the coming frame, centred on the anchor
  /// unit.
  void _replaceView() {
    _anchorPending = true;
    _generation++;
    // The previous scroll view is replaced in the coming frame; its
    // controller is released after it.
    final previous = _scroll;
    _scroll = null;
    final generation = _generation;
    if (previous != null) {
      WidgetsBinding.instance.addPostFrameCallback((_) => previous.dispose());
    }
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => _afterAnchor(generation),
    );
  }

  /// Releases the display units of the chapters away from the window.
  void _releaseFarChapters() {
    _chapters.removeWhere(
      (chapter, _) => chapter < _windowStart - 1 || chapter > _windowEnd + 1,
    );
  }

  /// Cuts the window back once the reader is idle (not under a finger,
  /// not scrolling).
  void _scheduleTrim() {
    _trimTimer?.cancel();
    _trimTimer = Timer(const Duration(milliseconds: 300), _trimWindow);
  }

  /// Once the window spans more than [_maxWindowChapters], keeps only the
  /// chapter being read, its neighbours and any chapter with text on
  /// screen: the chapters read long ago are not kept for the whole
  /// session. Removing chapters beyond the anchor's side moves nothing on
  /// screen; when the anchor chapter itself is dropped, the view is rebuilt
  /// around the unit being read, at the same place on screen.
  void _trimWindow() {
    if (!mounted || _leaving || _anchorPending || _source == null) return;
    if (_windowEnd - _windowStart + 1 <= _maxWindowChapters) return;
    final scroll = _scroll;
    if (_pointers > 0 ||
        (scroll != null &&
            scroll.hasClients &&
            scroll.position.isScrollingNotifier.value)) {
      _scheduleTrim();
      return;
    }
    final reading = _readingUnit();
    if (reading == null) return;
    final (view, top) = reading;
    var start = view.unit.chapter - 1;
    var end = view.unit.chapter + 1;
    // Chapters with text on screen stay (short chapters: several can be in
    // view).
    for (final chapter in _chaptersOnScreen()) {
      if (chapter < start) start = chapter;
      if (chapter > end) end = chapter;
    }
    start = math.max(start, _windowStart);
    end = math.min(end, _windowEnd);
    if (start == _windowStart && end == _windowEnd) return;
    final anchor = _anchor.chapter;
    final recentre = anchor < start || anchor > end;
    final position = recentre ? _readingPosition() : null;
    setState(() {
      if (recentre) {
        _anchor =
            position ??
            LibraryReflowPosition(
              view.unit.chapter,
              view.unit.block,
              view.unit.start,
            );
        _anchorUnit = view.widget.unitIndex;
        _anchorUnitOffset = 0;
        _nextScrollOffset = -top;
        _replaceView();
      }
      _windowStart = start;
      _windowEnd = end;
      _releaseFarChapters();
    });
  }

  void _afterAnchor(int generation) {
    if (!mounted || generation != _generation) return;
    final scroll = _scroll;
    final view = _registry.find(_anchor.chapter, _anchorUnit);
    var jumped = false;
    if (scroll != null &&
        scroll.hasClients &&
        view != null &&
        _anchorUnitOffset > 0) {
      final top = view.caretTop(_anchorUnitOffset);
      if (top != null && top > 0) {
        scroll.jumpTo(-_topInset + top);
        jumped = true;
      }
    }
    if (!jumped) {
      _anchorSettled(generation);
      return;
    }
    // The jump is laid out in the next frame (jumpTo schedules it): the
    // position is read from the boxes only after it.
    WidgetsBinding.instance.addPostFrameCallback(
      (_) => _anchorSettled(generation),
    );
  }

  void _anchorSettled(int generation) {
    if (!mounted || generation != _generation) return;
    _anchorPending = false;
    _track(force: true);
    _maybeLoadMore();
  }

  /// The reading position: the pending anchor while the view moves to it,
  /// else the first visible line, else the last one tracked.
  LibraryReflowPosition? _readingPosition() {
    if (_anchorPending) return _anchor;
    return _computePosition() ?? _lastPosition;
  }

  /// Goes to [position], loading its chapter first.
  Future<void> _goTo(LibraryReflowPosition position) async {
    if (_activeLayout == LibraryTextLayout.pages) return _goToPage(position);
    final source = _source;
    if (source == null) return;
    if (position.chapter < 0 || position.chapter >= source.chapterCount) return;
    try {
      await source.loadChapter(position.chapter);
    } catch (error) {
      if (!mounted) return;
      // Shown inline if the chapter becomes an edge of the view; the jump
      // itself failed, so say so now (never a silent tap).
      setState(() => _chapterErrors[position.chapter] = error);
      final info = LibraryReaderErrorInfo.from(error);
      _message(info.messageKey, detail: info.detail);
      return;
    }
    if (!mounted) return;
    _ensureChapterData(position.chapter);
    _chapterErrors.remove(position.chapter);
    if (position.chapter < _windowStart - 1 ||
        position.chapter > _windowEnd + 1) {
      _windowStart = position.chapter;
      _windowEnd = position.chapter;
    } else {
      if (position.chapter < _windowStart) _windowStart = position.chapter;
      if (position.chapter > _windowEnd) _windowEnd = position.chapter;
    }
    setState(() {
      _releaseFarChapters();
      _setAnchor(position);
    });
    _lastPosition = position;
    _shownPosition.value = position;
    _userMoved();
    _dirty = true;
    _scheduleSave();
  }

  void _goToChapter(int delta) {
    final source = _source;
    if (source == null) return;
    final current = (_lastPosition ?? _anchor).chapter;
    final target = current + delta;
    if (target < 0 || target >= source.chapterCount) return;
    unawaited(_goTo(LibraryReflowPosition(target, 0, 0)));
  }

  // ------------------------------------------------------ pages layout --

  /// The window shows the pages of the current layout and can turn.
  bool get _pagesReady =>
      _spread != null &&
      _windowLayout == _pagesLayout &&
      !_relocating &&
      _pagesError == null;

  /// Pager index of the spread shown.
  int get _centerIndex => _hasPrevious ? 1 : 0;

  int get _slotCount => (_hasPrevious ? 1 : 0) + 1 + (_hasNext ? 1 : 0);

  /// Spread of pager item [index] (null: a neighbour not laid out yet).
  LibraryBookSpread? _slotSpread(int index) {
    final relative = index - _centerIndex;
    if (relative == 0) return _spread;
    if (relative == -1 && _hasPrevious) return _previous;
    if (relative == 1 && _hasNext) return _next;
    return null;
  }

  /// Name of a page for the page curl and its textures (unique in a
  /// layout; the layout is in the curl's content key).
  static int _pageIdOf(LibraryReflowPageSpec page) =>
      (page.chapter << 20) | page.indexInChapter;

  LibraryReflowPageSpec? _pageForId(int id) {
    for (final spread in <LibraryBookSpread?>[_spread, _next, _previous]) {
      if (spread == null) continue;
      for (final page in spread.pages) {
        if (_pageIdOf(page) == id) return page;
      }
    }
    return null;
  }

  LibraryPageCurlFace? _curlFaceOf(int item) {
    final index = item - _virtualOrigin;
    if (index < 0 || index >= _slotCount) return null;
    return _slotSpread(index)?.faceWith(_pageIdOf);
  }

  /// Pages layout: shows the page holding [position] (contents, link,
  /// slider, chapter), its chapter loaded first. The page shown stays until
  /// the new one is laid out.
  Future<void> _goToPage(LibraryReflowPosition position) async {
    final source = _source;
    if (source == null) return;
    if (position.chapter < 0 || position.chapter >= source.chapterCount) {
      return;
    }
    try {
      await source.loadChapter(position.chapter);
    } catch (error) {
      if (!mounted) return;
      // The jump failed: say so now (never a silent tap).
      final info = LibraryReaderErrorInfo.from(error);
      _message(info.messageKey, detail: info.detail);
      return;
    }
    if (!mounted || _activeLayout != LibraryTextLayout.pages) return;
    _pageAnchor = position;
    _lastPosition = position;
    _shownPosition.value = position;
    _userMoved();
    _dirty = true;
    _scheduleSave();
    _curl?.reset();
    unawaited(_relocate());
  }

  /// Forgets the window: a new one is laid out around [_pageAnchor].
  void _clearWindow() {
    _spread = null;
    _previous = null;
    _next = null;
    _previousError = null;
    _nextError = null;
    _pagesError = null;
    _hasPrevious = false;
    _hasNext = false;
    _previousRequestedFor = null;
    _nextRequestedFor = null;
    _arrivalPending = 0;
    _queuedTurn = 0;
    _windowGeometry = null;
    _windowLayout = -1;
    _windowGeneration++;
    final pager = _pager;
    _pager = null;
    if (pager != null) {
      // Its PageView leaves the tree in the coming frame.
      WidgetsBinding.instance.addPostFrameCallback((_) => pager.dispose());
    }
  }

  /// Lays the window out again after the frame being built (never during
  /// a build: the paginator works for up to a frame budget at once).
  void _scheduleRelocate() {
    _relocating = true;
    if (_relocateScheduled) return;
    _relocateScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _relocateScheduled = false;
      if (mounted) unawaited(_relocate());
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  bool _relocateCurrent(int request, LibraryReflowPaginator paginator) =>
      mounted &&
      request == _relocateRequest &&
      identical(paginator, _paginator) &&
      _activeLayout == LibraryTextLayout.pages;

  /// Shows the spread holding [_pageAnchor] in the current layout.
  Future<void> _relocate() async {
    final paginator = _paginator;
    final geometry = _pagesGeometry;
    if (!mounted ||
        paginator == null ||
        geometry == null ||
        _activeLayout != LibraryTextLayout.pages) {
      _relocating = false;
      return;
    }
    final request = ++_relocateRequest;
    final layout = _pagesLayout;
    _relocating = true;
    try {
      final page = await paginator.locate(_pageAnchor);
      final spread = await geometry.rule.holding(paginator, page);
      if (!_relocateCurrent(request, paginator)) return;
      _relocating = false;
      _showWindow(spread, geometry, layout);
    } on LibraryReflowPaginationCancelled {
      // Superseded by a relayout, which lays the window out again.
      if (_relocateCurrent(request, paginator)) _scheduleRelocate();
    } catch (error) {
      if (!_relocateCurrent(request, paginator)) return;
      _relocating = false;
      setState(() => _pagesError = error);
    }
  }

  void _showWindow(
    LibraryBookSpread spread,
    _BookPagesGeometry geometry,
    int layout,
  ) {
    setState(() {
      _clearWindow();
      _spread = spread;
      _windowGeometry = geometry;
      _windowLayout = layout;
      _updateEdges();
      // A new item for the page curl: nothing of an earlier window turns.
      _virtualOrigin += 16;
      _pager = PageController(initialPage: _centerIndex);
      _curl ??= LibraryPageCurlController(vsync: this)
        ..addListener(_onCurlChanged);
      _textures ??= LibraryPageTextureCache();
      _windowShownOnce = true;
    });
    _spreadShown(moved: false);
  }

  /// Whether spreads come before and after the one shown (known from its
  /// pages: the first page of the book, the last page of the last chapter).
  void _updateEdges() {
    final spread = _spread;
    final source = _source;
    final rule = _windowGeometry?.rule;
    if (spread == null || source == null || rule == null) {
      _hasPrevious = false;
      _hasNext = false;
      return;
    }
    _hasPrevious = rule.hasBefore(spread);
    _hasNext = rule.hasAfter(spread, source.chapterCount);
    if (!_hasPrevious) {
      _previous = null;
      _previousError = null;
    }
    if (!_hasNext) {
      _next = null;
      _nextError = null;
    }
  }

  /// The spread shown changed: after a turn ([moved]) its first page is
  /// the reading position, saved like the scroll position. Its neighbours
  /// and its chapter's page count are laid out next.
  void _spreadShown({required bool moved}) {
    final spread = _spread;
    final paginator = _paginator;
    if (spread == null || paginator == null) return;
    if (moved) {
      final position = spread.first.start;
      _pageAnchor = position;
      _lastPosition = position;
      _shownPosition.value = position;
      _userMoved();
      _dirty = true;
      _scheduleSave();
    }
    _fetchNeighbours();
    _watchChapter(paginator, spread.chapter);
  }

  /// Lays out the neighbours of the spread shown (at once when their pages
  /// are laid out already).
  void _fetchNeighbours() {
    final paginator = _paginator;
    final spread = _spread;
    final rule = _windowGeometry?.rule;
    if (paginator == null ||
        spread == null ||
        rule == null ||
        _windowLayout != _pagesLayout) {
      return;
    }
    var changed = false;
    if (_hasNext &&
        _next == null &&
        _nextError == null &&
        !identical(_nextRequestedFor, spread)) {
      final now = rule.afterNow(paginator, spread);
      if (now != null) {
        _next = now;
        changed = true;
      } else {
        _nextRequestedFor = spread;
        rule
            .after(paginator, spread)
            .then(
              (found) => _neighbourReady(
                spread,
                paginator,
                forward: true,
                found: found,
              ),
              onError: (Object error) => _neighbourReady(
                spread,
                paginator,
                forward: true,
                error: error,
              ),
            );
      }
    }
    if (_hasPrevious &&
        _previous == null &&
        _previousError == null &&
        !identical(_previousRequestedFor, spread)) {
      final now = rule.beforeNow(paginator, spread);
      if (now != null) {
        _previous = now;
        changed = true;
      } else {
        _previousRequestedFor = spread;
        rule
            .before(paginator, spread)
            .then(
              (found) => _neighbourReady(
                spread,
                paginator,
                forward: false,
                found: found,
              ),
              onError: (Object error) => _neighbourReady(
                spread,
                paginator,
                forward: false,
                error: error,
              ),
            );
      }
    }
    if (changed && mounted) setState(() {});
  }

  void _neighbourReady(
    LibraryBookSpread from,
    LibraryReflowPaginator paginator, {
    required bool forward,
    LibraryBookSpread? found,
    Object? error,
  }) {
    if (!mounted ||
        !identical(from, _spread) ||
        !identical(paginator, _paginator)) {
      return;
    }
    if (forward) {
      _nextRequestedFor = null;
    } else {
      _previousRequestedFor = null;
    }
    // Superseded by a relayout: the new window lays its neighbours out.
    if (error is LibraryReflowPaginationCancelled) return;
    final direction = forward ? 1 : -1;
    if (error == null && found == null) {
      // Nothing there after all: the pager loses that item.
      final center = _centerIndex;
      setState(() {
        if (forward) {
          _hasNext = false;
        } else {
          _hasPrevious = false;
          _virtualOrigin += center - _centerIndex;
        }
      });
      final pager = _pager;
      if (pager != null && pager.hasClients && center != _centerIndex) {
        pager.jumpToPage(_centerIndex);
      }
      if (_arrivalPending == direction) _arrivalPending = 0;
      if (_queuedTurn == direction) _queuedTurn = 0;
      return;
    }
    setState(() {
      if (forward) {
        _next = found;
        _nextError = error;
      } else {
        _previous = found;
        _previousError = error;
      }
    });
    if (error != null) {
      if (_queuedTurn == direction) {
        _queuedTurn = 0;
        final info = LibraryReaderErrorInfo.from(error);
        _message(info.messageKey, detail: info.detail);
      }
      return;
    }
    if (_arrivalPending == direction) {
      _arriveAt(_centerIndex + direction);
      return;
    }
    _refreshCurl();
    if (_queuedTurn == direction) {
      _queuedTurn = 0;
      _turnPage(forward: forward);
    }
  }

  /// The page curl renders a neighbour laid out late ahead of a turn (it
  /// renders the neighbours when its item changes); never during a turn.
  void _refreshCurl() {
    final curl = _curl;
    if (curl != null && curl.isActive) {
      _curlRefreshPending = true;
      return;
    }
    _curlRefreshPending = false;
    if (mounted) setState(() => _virtualOrigin += 4);
  }

  void _onCurlChanged() {
    if (!_curlRefreshPending || (_curl?.isActive ?? true)) return;
    // Notified while the curl layer builds (a reset) or ends a frame.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _curlRefreshPending && !(_curl?.isActive ?? false)) {
        _refreshCurl();
      }
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  /// Rebuilds once [chapter] is paginated ("Page N of M"), then paginates
  /// the next chapter ahead (the current chapter and the next one only).
  void _watchChapter(LibraryReflowPaginator paginator, int chapter) {
    if (paginator.pageCountOf(chapter) != null) {
      paginator.prefetch(chapter + 1);
      return;
    }
    if (identical(_watchedPaginator, paginator) && _watchedChapter == chapter) {
      return;
    }
    _watchedPaginator = paginator;
    _watchedChapter = chapter;
    void done() {
      if (identical(_watchedPaginator, paginator) &&
          _watchedChapter == chapter) {
        _watchedPaginator = null;
        _watchedChapter = null;
      }
    }

    paginator.paginate(chapter).then((_) {
      done();
      if (!mounted || !identical(paginator, _paginator)) return;
      setState(() {});
      paginator.prefetch(chapter + 1);
    }, onError: (Object _) => done());
  }

  /// Turns to the next (or previous) spread in reading order: with the
  /// page curl, a slide or at once ([LibraryPageTurnStyle]; Reduce Motion:
  /// at once). Never a second turn while one runs; a turn toward a
  /// neighbour still being laid out happens once it is.
  void _turnPage({required bool forward}) {
    if (!mounted || _activeLayout != LibraryTextLayout.pages || !_pagesReady) {
      return;
    }
    final curl = _curl;
    if (curl != null && curl.isActive) return;
    final pager = _pager;
    if (pager == null || !pager.hasClients) return;
    if (pager.position.isScrollingNotifier.value || _arrivalPending != 0) {
      return;
    }
    if (forward ? !_hasNext : !_hasPrevious) return;
    final target = forward ? _next : _previous;
    if (target == null) {
      final error = forward ? _nextError : _previousError;
      if (error != null) {
        final info = LibraryReaderErrorInfo.from(error);
        _message(info.messageKey, detail: info.detail);
        return;
      }
      _queuedTurn = forward ? 1 : -1;
      return;
    }
    _queuedTurn = 0;
    final index = _centerIndex + (forward ? 1 : -1);
    final direction = forward
        ? LibraryPageTurnDirection.forward
        : LibraryPageTurnDirection.backward;
    final style = _effective(
      reduceMotion: MediaQuery.disableAnimationsOf(context),
    ).turnStyle;
    if (style == LibraryPageTurnStyle.none) {
      _arriveAt(index);
      return;
    }
    if (style == LibraryPageTurnStyle.curl &&
        curl != null &&
        curl.canTurn(direction)) {
      // 380 ms, then onTurned jumps the pager under the turned page.
      unawaited(curl.turn(direction));
      return;
    }
    unawaited(
      pager.animateToPage(
        index,
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOut,
      ),
    );
  }

  /// Turns toward the page on that side of the screen (right to left, the
  /// next page is on the left).
  void _turnVisual({required bool left}) => _turnPage(
    forward: left == (_windowGeometry?.rule.rightToLeft ?? _rightToLeft),
  );

  /// The pager rests on item [index] (a slide, a jump, or the page curl
  /// has turned): that spread becomes the one shown and the pager jumps
  /// back to the middle of a new window around it, without animation.
  void _arriveAt(int index) {
    if (!mounted || _activeLayout != LibraryTextLayout.pages) return;
    final spread = _spread;
    if (spread == null) return;
    final center = _centerIndex;
    if (index == center) {
      _arrivalPending = 0;
      return;
    }
    final forward = index > center;
    final target = forward ? _next : _previous;
    if (target == null) {
      // Still being laid out (or failed: its placeholder offers Retry).
      _arrivalPending = forward ? 1 : -1;
      return;
    }
    _arrivalPending = 0;
    final item = _virtualOrigin + index;
    setState(() {
      if (forward) {
        _previous = spread;
        _previousError = null;
        _previousRequestedFor = null;
        _spread = target;
        _next = null;
        _nextError = null;
        _nextRequestedFor = null;
      } else {
        _next = spread;
        _nextError = null;
        _nextRequestedFor = null;
        _spread = target;
        _previous = null;
        _previousError = null;
        _previousRequestedFor = null;
      }
      _updateEdges();
      // The curl's item of the spread shown stays the one it turned to.
      _virtualOrigin = item - _centerIndex;
    });
    final pager = _pager;
    if (pager != null && pager.hasClients) pager.jumpToPage(_centerIndex);
    _spreadShown(moved: true);
  }

  bool _onPagerNotification(ScrollNotification notification) {
    if (notification.depth != 0 || notification is! ScrollEndNotification) {
      return false;
    }
    final generation = _windowGeneration;
    // After the notification: the pager then jumps to a new window.
    scheduleMicrotask(() {
      if (!mounted || generation != _windowGeneration) return;
      final pager = _pager;
      if (pager == null || !pager.hasClients) return;
      final page = pager.page;
      if (page == null) return;
      final index = page.round();
      if ((page - index).abs() > 0.001) return;
      _arriveAt(index);
    });
    return false;
  }

  /// Texture of page [id] for the curl: its picture at [pixels], with its
  /// images decoded first.
  Future<ui.Image?> _renderPageTexture(
    int id,
    Size pixels,
    LibraryCancelToken cancel,
  ) async {
    final paginator = _paginator;
    final page = _pageForId(id);
    if (paginator == null || page == null || cancel.isCancelled) return null;
    final size = page.size;
    if (size.isEmpty || pixels.isEmpty) return null;
    await paginator.prepare(page);
    if (!mounted || cancel.isCancelled || !identical(paginator, _paginator)) {
      return null;
    }
    final picture = paginator.paint(
      page,
      pixelRatio: pixels.width / size.width,
    );
    try {
      return picture.toImageSync(pixels.width.round(), pixels.height.round());
    } finally {
      picture.dispose();
    }
  }

  /// Where pages are drawn for a body of [body]: the whole body for one
  /// page, the safe area between the sides for a spread (two halves).
  _BookPagesGeometry _geometryFor(
    BuildContext context,
    Size body,
    LibraryReaderPalette palette,
    LibraryReaderEffectiveSettings effective,
  ) {
    final safe = MediaQuery.paddingOf(context);
    final style = LibraryReflowStyle.of(_settings, palette);
    final twoPages = LibraryPageSpreads.usesDoublePages(
      mode: effective.doublePage,
      landscape: MediaQuery.orientationOf(context) == Orientation.landscape,
      vertical: false,
    );
    // The first line below the back control, as in the scroll view.
    final top = _topInset;
    final bottom = safe.bottom + _pageBottomGap;
    final Rect area;
    final Size pageSize;
    final EdgeInsets padding;
    if (twoPages) {
      final width = math.max(0.0, body.width - safe.left - safe.right);
      area = Rect.fromLTWH(safe.left, 0, width, body.height);
      pageSize = Size(width / 2, body.height);
      // Both halves alike: one paginator lays out every page.
      final side = style.margin + _spineGutter;
      padding = EdgeInsets.fromLTRB(side, top, side, bottom);
    } else {
      area = Offset.zero & body;
      pageSize = body;
      // The scroll view's horizontal padding: the same words on each line.
      padding = EdgeInsets.fromLTRB(
        safe.left + style.margin,
        top,
        safe.right + style.margin,
        bottom,
      );
    }
    return _BookPagesGeometry(
      area: area,
      pageSize: pageSize,
      padding: padding,
      style: style,
      rule: LibraryBookSpreadRule(
        doublePage: twoPages,
        firstPageAlone: effective.firstPageAlone,
        rightToLeft: _rightToLeft,
        firstPageAloneInEveryChapter: _source?.separatesChapters ?? true,
      ),
      devicePixelRatio: MediaQuery.devicePixelRatioOf(context),
    );
  }

  /// Gives the paginator the geometry of this build (typography, page
  /// size, margins, colours) and asks for a new window when its pages no
  /// longer match.
  _BookPagesGeometry _syncPages(
    BuildContext context,
    Size body,
    LibraryReaderPalette palette,
    LibraryReaderEffectiveSettings effective,
  ) {
    final geometry = _geometryFor(context, body, palette, effective);
    final source = _source!;
    var paginator = _paginator;
    // A route that leaves is not laid out again (rotated back to
    // landscape while it slides out).
    if (_leaving && paginator != null) return geometry;
    final direction = Directionality.of(context);
    final locale = Localizations.maybeLocaleOf(context);
    if (paginator != null &&
        (paginator.textDirection != direction ||
            paginator.locale != locale ||
            !identical(paginator.source, source))) {
      paginator.dispose();
      paginator = _paginator = null;
    }
    if (paginator == null) {
      _paginator = LibraryReflowPaginator(
        source: source,
        style: geometry.style,
        pageSize: geometry.pageSize,
        padding: geometry.padding,
        // As LibraryReflowUnitView: the font size setting is the text size.
        textScaler: TextScaler.noScaling,
        textDirection: direction,
        locale: locale,
        images: _images,
        devicePixelRatio: geometry.devicePixelRatio,
      );
      _pagesLayout++;
      _pagesGeometry = geometry;
      _scheduleRelocate();
      return geometry;
    }
    final changed = paginator.update(
      style: geometry.style,
      pageSize: geometry.pageSize,
      padding: geometry.padding,
      devicePixelRatio: geometry.devicePixelRatio,
    );
    _pagesGeometry = geometry;
    if (changed) {
      // New typography, margins or page size: the page holding the same
      // anchor in the new layout.
      _pagesLayout++;
      _scheduleRelocate();
    } else {
      final window = _windowGeometry;
      final stale =
          _spread == null ||
          window == null ||
          _windowLayout != _pagesLayout ||
          !window.fits(geometry);
      if (stale && !_relocating && _pagesError == null) _scheduleRelocate();
    }
    return geometry;
  }

  String? _linkAt(Offset position, _BookPagesGeometry geometry) {
    final paginator = _paginator;
    final spread = _spread;
    final pager = _pager;
    if (paginator == null || spread == null) return null;
    if (pager != null &&
        pager.hasClients &&
        pager.position.isScrollingNotifier.value) {
      return null;
    }
    final area = geometry.area;
    if (!area.contains(position)) return null;
    var local = position - area.topLeft;
    LibraryReflowPageSpec? page;
    if (spread.doublePage) {
      final half = area.width / 2;
      final right = local.dx >= half;
      page = right ? spread.right : spread.left;
      if (right) local = local - Offset(half, 0);
    } else {
      page = spread.first;
    }
    if (page == null) return null;
    return paginator.linkAt(page, local);
  }

  void _onPagesTapUp(
    TapUpDetails details,
    Size size,
    _BookPagesGeometry geometry,
  ) {
    final href = _linkAt(details.localPosition, geometry);
    if (href != null) {
      unawaited(_onLink(href));
      return;
    }
    final x = details.localPosition.dx;
    final third = size.width / 3;
    if (_settings.tapZones && _source != null && !_opening) {
      if (x < third) {
        _chrome.hide();
        _turnVisual(left: true);
        return;
      }
      if (x > size.width - third) {
        _chrome.hide();
        _turnVisual(left: false);
        return;
      }
    }
    _chrome.toggle();
  }

  void _retryPages() {
    if (!mounted) return;
    setState(() => _pagesError = null);
  }

  void _retryNeighbour({required bool forward}) {
    if (!mounted) return;
    setState(() {
      if (forward) {
        _nextError = null;
        _nextRequestedFor = null;
      } else {
        _previousError = null;
        _previousRequestedFor = null;
      }
    });
    _fetchNeighbours();
  }

  /// "Page N of M" (or "Pages N and N+1 of M") in the chapter shown, once
  /// it is paginated; "Laying out pages…" until then.
  String _pagesLabel(BuildContext context) {
    final spread = _spread;
    final paginator = _paginator;
    final total = spread == null || paginator == null || !_pagesReady
        ? null
        : paginator.pageCountOf(spread.chapter);
    if (spread == null || total == null) {
      return LibraryReaderLocale.text(context, 'paginating');
    }
    final pages = spread.pages;
    if (pages.length > 1) {
      return LibraryReaderLocale.format(
        context,
        'pagesOfTotal',
        <String, Object?>{
          'first': pages.first.indexInChapter + 1,
          'second': pages.last.indexInChapter + 1,
          'total': total,
        },
      );
    }
    return LibraryReaderLocale.format(context, 'pageOfTotal', <String, Object?>{
      'page': pages.first.indexInChapter + 1,
      'total': total,
    });
  }

  // ------------------------------------------------------------ loading --

  bool get _laying =>
      SchedulerBinding.instance.schedulerPhase ==
      SchedulerPhase.persistentCallbacks;

  void _maybeLoadMore() {
    if (_laying) {
      // Notified while the viewport lays out: act after the frame.
      if (_loadMoreScheduled) return;
      _loadMoreScheduled = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _loadMoreScheduled = false;
        _maybeLoadMore();
      });
      return;
    }
    final scroll = _scroll;
    final source = _source;
    if (scroll == null || !scroll.hasClients || source == null || !mounted) {
      return;
    }
    final position = scroll.position;
    final margin = position.viewportDimension * 1.5;
    if (position.extentAfter < margin && _windowEnd < source.chapterCount - 1) {
      _loadEdge(_windowEnd + 1);
    }
    if (position.extentBefore < margin && _windowStart > 0) {
      _loadEdge(_windowStart - 1);
    }
  }

  void _loadEdge(int chapter) {
    final source = _source;
    if (source == null || _loading.contains(chapter)) return;
    if (_chapterErrors.containsKey(chapter)) return;
    _loading.add(chapter);
    source
        .loadChapter(chapter)
        .then(
          (_) {
            _loading.remove(chapter);
            if (!mounted) return;
            _ensureChapterData(chapter);
            setState(() {
              if (chapter == _windowEnd + 1) _windowEnd = chapter;
              if (chapter == _windowStart - 1) _windowStart = chapter;
            });
            WidgetsBinding.instance.addPostFrameCallback(
              (_) => _maybeLoadMore(),
            );
            _scheduleTrim();
          },
          onError: (Object error) {
            _loading.remove(chapter);
            if (!mounted) return;
            setState(() => _chapterErrors[chapter] = error);
          },
        );
  }

  void _retryEdge(int chapter) {
    setState(() => _chapterErrors.remove(chapter));
    _loadEdge(chapter);
  }

  // ----------------------------------------------------------- position --

  double get _readingLine => _topInset + 1;

  /// The unit at the reading line (else the first one below it) and its
  /// top in the viewport, from the current layout.
  (LibraryReflowUnitViewState, double)? _readingUnit() {
    final viewport = _viewportKey.currentContext?.findRenderObject();
    if (viewport is! RenderBox || !viewport.attached || !viewport.hasSize) {
      return null;
    }
    final readingLine = _readingLine;
    LibraryReflowUnitViewState? below;
    var belowTop = double.infinity;
    for (final view in _registry.views) {
      final top = _topOnScreen(view, viewport);
      if (top == null) continue;
      final bottom = top + view.box!.size.height;
      if (top <= readingLine && bottom > readingLine) return (view, top);
      if (top > readingLine && top < belowTop) {
        below = view;
        belowTop = top;
      }
    }
    return below == null ? null : (below, belowTop);
  }

  /// Top of [view] in [viewport] when some of it is on screen, else null.
  /// A list scrolled out of view keeps one of its units built (to measure
  /// its extent): only units of a list that paints something count.
  double? _topOnScreen(LibraryReflowUnitViewState view, RenderBox viewport) {
    final box = view.box;
    if (box == null) return null;
    RenderObject? list = box.parent;
    while (list != null && list is! RenderSliver) {
      list = list.parent;
    }
    if (list is! RenderSliver || !(list.geometry?.visible ?? false)) {
      return null;
    }
    final top = box.localToGlobal(Offset.zero, ancestor: viewport).dy;
    if (top + box.size.height <= 0 || top >= viewport.size.height) {
      return null;
    }
    return top;
  }

  /// Chapters with text on screen.
  Set<int> _chaptersOnScreen() {
    final viewport = _viewportKey.currentContext?.findRenderObject();
    if (viewport is! RenderBox || !viewport.attached || !viewport.hasSize) {
      return const <int>{};
    }
    return <int>{
      for (final view in _registry.views)
        if (_topOnScreen(view, viewport) != null) view.widget.chapter,
    };
  }

  LibraryReflowPosition? _computePosition() {
    final reading = _readingUnit();
    if (reading == null) return null;
    final (view, top) = reading;
    final unit = view.unit;
    if (top > _readingLine) {
      return LibraryReflowPosition(unit.chapter, unit.block, unit.start);
    }
    final offset = view.offsetAt(_readingLine - top);
    return LibraryReflowPosition(unit.chapter, unit.block, unit.start + offset);
  }

  void _track({bool force = false}) {
    // Scroll notifications of the jump to a new anchor arrive before its
    // layout: nothing to read yet.
    if (!mounted || _anchorPending || _leaving) return;
    if (_laying) {
      // Render boxes are only read outside layout.
      if (_trackScheduled) return;
      _trackScheduled = true;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _trackScheduled = false;
        _track(force: true);
      });
      return;
    }
    final now = DateTime.now();
    if (!force &&
        now.difference(_lastTrack) < const Duration(milliseconds: 300)) {
      return;
    }
    _lastTrack = now;
    final position = _computePosition();
    if (position == null || position == _lastPosition) return;
    _lastPosition = position;
    _shownPosition.value = position;
    _dirty = true;
    _scheduleSave();
  }

  /// Tracks the position once the coming frame has laid out the current
  /// scroll offset. The end of a page turn or of a fling is notified by the
  /// animation tick, before that layout: read at once, the boxes still
  /// describe the previous frame (one whole page turn earlier when the
  /// animation ran in a single frame) and that older position was saved.
  void _trackAfterLayout() {
    if (!mounted || _trackScheduled) return;
    _trackScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _trackScheduled = false;
      _track(force: true);
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _scheduleSave() {
    if (_leaving) return;
    _saveTimer?.cancel();
    _saveTimer = Timer(const Duration(milliseconds: 800), _saveNow);
  }

  void _saveNow() {
    _saveTimer?.cancel();
    _saveTimer = null;
    final source = _source;
    final position = _lastPosition;
    if (_leaving || _keepSavedLocation) return;
    if (!_dirty || source == null || position == null) return;
    String location;
    double fraction;
    try {
      location = source.locationFor(position);
      fraction = source.fractionFor(position);
    } catch (_) {
      return;
    }
    _dirty = false;
    _store.saveProgress(
      LibraryReadingProgress(
        key: widget.progressKey,
        location: location,
        fraction: fraction,
        title: widget.title,
        subtitle: widget.subtitle,
        coverUrl: widget.coverUrl,
        chapterTitle: _tocTitleFor(position.chapter),
      ),
    );
  }

  int? _tocIndexFor(int chapter) {
    final toc = _source?.toc ?? const <LibraryReflowTocEntry>[];
    int? best;
    for (var i = 0; i < toc.length; i++) {
      final entryChapter = toc[i].chapter;
      if (entryChapter == null) continue;
      // The first entry of the closest chapter (its own title, not a
      // section further down in it).
      if (entryChapter <= chapter) {
        if (best == null || (toc[best].chapter ?? -1) < entryChapter) best = i;
      }
    }
    return best;
  }

  String? _tocTitleFor(int chapter) {
    final index = _tocIndexFor(chapter);
    if (index == null) return null;
    final title = _source!.toc[index].title;
    return title.isEmpty ? null : title;
  }

  // ------------------------------------------------------------ actions --

  /// Longest scroll of one step: the text area below the back control,
  /// less its tallest line. Turning a page forward, the line cut by the
  /// bottom edge then lands below the back control, on the reading line or
  /// under it, never under the floating back button; turning back, the line
  /// cut under the back control lands whole on screen. No line is shown
  /// only behind the button, and the position saved after a turn is never
  /// past a line not shown yet.
  double _pageStep(double viewport) {
    final line = LibraryReflowStyle.of(
      _settings,
      _palette(context),
    ).tallestLine;
    return math.max(viewport - _topInset - line, line);
  }

  void _scrollBy(double viewports) {
    final scroll = _scroll;
    if (scroll == null || !scroll.hasClients) return;
    _userMoved();
    final position = scroll.position;
    final viewport = position.viewportDimension;
    // Page turns (0.9 screen) are capped to [_pageStep]; the shorter
    // controller steps (0.3 screen) stay as they were.
    final distance = math.min(viewport * viewports.abs(), _pageStep(viewport));
    final target = (position.pixels + distance * viewports.sign).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
    scroll.animateTo(
      target,
      duration: const Duration(milliseconds: 220),
      curve: Curves.easeOut,
    );
  }

  void _onTapUp(TapUpDetails details, Size size) {
    final x = details.localPosition.dx;
    final third = size.width / 3;
    if (_settings.tapZones && _source != null && !_opening) {
      if (x < third) {
        _chrome.hide();
        _scrollBy(-0.9);
        return;
      }
      if (x > size.width - third) {
        _chrome.hide();
        _scrollBy(0.9);
        return;
      }
    }
    _chrome.toggle();
  }

  Future<void> _onLink(String href) async {
    final source = _source;
    if (source == null) return;
    final uri = Uri.tryParse(href);
    if (uri != null && uri.hasScheme) {
      if (uri.scheme.toLowerCase() != 'https' || uri.host.isEmpty) {
        _message('linkNotSecure', detail: href);
        return;
      }
      final palette = _palette(context);
      final confirmed = await showLibraryReaderLinkDialog(
        context,
        palette: palette,
        uri: uri,
      );
      if (!confirmed || !mounted) return;
      final launch =
          widget.launchExternal ??
          (Uri target) =>
              launchUrl(target, mode: LaunchMode.externalApplication);
      bool opened;
      try {
        opened = await launch(uri);
      } catch (_) {
        opened = false;
      }
      if (!opened && mounted) _message('linkOpenFailed', detail: href);
      return;
    }
    LibraryReflowPosition? target;
    try {
      target = await source.resolveLink(href);
    } catch (_) {
      target = null;
    }
    if (!mounted) return;
    if (target == null) {
      _message('linkUnavailable', detail: href);
      return;
    }
    await _goTo(target);
  }

  void _message(String key, {String? detail}) {
    if (!mounted) return;
    final text = LibraryReaderLocale.text(context, key);
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(text),
              if (detail != null)
                Text(
                  detail,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12),
                ),
            ],
          ),
          duration: const Duration(seconds: 3),
        ),
      );
  }

  Future<void> _openToc() async {
    final source = _source;
    if (source == null || source.toc.isEmpty) return;
    _chrome.hold();
    try {
      final current = _tocIndexFor((_lastPosition ?? _anchor).chapter);
      final index = await showLibraryReaderListSheet(
        context,
        palette: _palette(context),
        title: LibraryReaderLocale.text(context, 'tableOfContents'),
        entries: <LibraryReaderListEntry>[
          for (final entry in source.toc)
            LibraryReaderListEntry(
              title: entry.title.isEmpty ? '—' : entry.title,
              depth: entry.depth,
              enabled: entry.target != null,
            ),
        ],
        currentIndex: current,
        emptyMessage: LibraryReaderLocale.text(context, 'noTableOfContents'),
      );
      if (index == null || !mounted) return;
      final target = source.toc[index].target;
      if (target == null) return;
      final position = await source.resolveLink(target);
      if (position == null || !mounted) {
        if (mounted) _message('linkUnavailable', detail: target);
        return;
      }
      await _goTo(position);
    } catch (error) {
      if (mounted) {
        _message(LibraryReaderErrorInfo.from(error).messageKey);
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
        builder: (context, settings, update) {
          String t(String key) => LibraryReaderLocale.text(context, key);
          return <LibraryReaderSettingItem>[
            LibraryReaderSliderSetting(
              label: t('fontSize'),
              value: settings.fontSize,
              min: LibraryReaderSettings.minFontSize,
              max: LibraryReaderSettings.maxFontSize,
              step: 1,
              format: (value) => value.round().toString(),
              onChanged: (value) =>
                  update(settings.copyWith(fontSize: value.roundToDouble())),
            ),
            LibraryReaderSliderSetting(
              label: t('lineHeight'),
              value: settings.lineHeight,
              min: LibraryReaderSettings.minLineHeight,
              max: LibraryReaderSettings.maxLineHeight,
              step: 0.1,
              format: (value) => value.toStringAsFixed(1),
              onChanged: (value) => update(
                settings.copyWith(lineHeight: (value * 10).round() / 10),
              ),
            ),
            LibraryReaderChoiceSetting<LibraryReaderFontFamily>(
              label: t('fontFamily'),
              value: settings.fontFamily,
              options: <LibraryReaderChoice<LibraryReaderFontFamily>>[
                LibraryReaderChoice(
                  LibraryReaderFontFamily.serif,
                  t('fontSerif'),
                ),
                LibraryReaderChoice(
                  LibraryReaderFontFamily.sans,
                  t('fontSans'),
                ),
              ],
              onChanged: (value) =>
                  update(settings.copyWith(fontFamily: value)),
            ),
            LibraryReaderCommonSettings.theme(context, settings, update),
            LibraryReaderSliderSetting(
              label: t('margins'),
              value: settings.margin,
              min: LibraryReaderSettings.minMargin,
              max: LibraryReaderSettings.maxMargin,
              step: 4,
              format: (value) => value.round().toString(),
              onChanged: (value) =>
                  update(settings.copyWith(margin: value.roundToDouble())),
            ),
            LibraryReaderToggleSetting(
              label: t('justify'),
              value: settings.justify,
              onChanged: (value) => update(settings.copyWith(justify: value)),
            ),
            ...LibraryReaderCommonSettings.toggles(context, settings, update),
          ];
        },
      );
    } finally {
      if (mounted) _chrome.release();
    }
  }

  Future<void> _jumpToFraction(double fraction) async {
    final source = _source;
    if (source == null) return;
    try {
      final position = await source.positionAtFraction(fraction);
      if (!mounted) return;
      await _goTo(position);
    } catch (error) {
      if (mounted) _message(LibraryReaderErrorInfo.from(error).messageKey);
    }
  }

  LibraryReaderPalette _palette(BuildContext context) =>
      LibraryReaderPalette.forBook(
        _settings.theme,
        MediaQuery.platformBrightnessOf(context),
      );

  // -------------------------------------------------------------- build --

  @override
  Widget build(BuildContext context) {
    final palette = _palette(context);
    final source = _source;
    final ready = source != null && !_opening && _openError == null;
    final width = MediaQuery.sizeOf(context).width;
    if (ready &&
        _activeLayout == LibraryTextLayout.scroll &&
        _lastWidth != null &&
        _lastWidth != width) {
      // Rotation: same words at the top in the new layout (the pages
      // layout keeps its anchor: _syncPages).
      _setAnchor(_anchorPending ? _anchor : (_lastPosition ?? _anchor));
    }
    _lastWidth = width;
    return PopScope<Object?>(
      onPopInvokedWithResult: _onPopped,
      child: LibraryReaderGamepadScope(
        name: 'library_book_reader',
        bindings: gamepadBindings,
        child: AnnotatedRegion<SystemUiOverlayStyle>(
          value: palette.isDark
              ? SystemUiOverlayStyle.light
              : SystemUiOverlayStyle.dark,
          child: Scaffold(
            backgroundColor: palette.background,
            // The chrome follows the position and its visibility; the text
            // (child) is not rebuilt for either.
            body: ListenableBuilder(
              listenable: Listenable.merge(<Listenable>[
                _chrome,
                _shownPosition,
                _sliderValue,
              ]),
              child: _buildBody(context, palette),
              builder: (context, body) {
                final position = _shownPosition.value ?? _anchor;
                final chapterTitle = ready
                    ? _tocTitleFor(position.chapter)
                    : null;
                return LibraryReaderChromeOverlay(
                  visible: _chrome.visible || !ready,
                  content: body!,
                  palette: palette,
                  // The floating back button closes like the top bar and B.
                  onBack: _close,
                  topBar: LibraryReaderTopBar(
                    palette: palette,
                    title: widget.title,
                    subtitle: chapterTitle ?? widget.subtitle,
                    onBack: _close,
                    actions: <Widget>[
                      if (ready && source.toc.isNotEmpty)
                        LibraryReaderIconButton(
                          icon: Icons.toc_rounded,
                          tooltip: LibraryReaderLocale.text(
                            context,
                            'tableOfContents',
                          ),
                          onPressed: _openToc,
                          color: palette.chromeForeground,
                        ),
                      LibraryReaderIconButton(
                        icon: Icons.text_format_rounded,
                        tooltip: LibraryReaderLocale.text(context, 'settings'),
                        onPressed: _openSettings,
                        color: palette.chromeForeground,
                      ),
                    ],
                  ),
                  bottomBar: ready && source.chapterCount > 0
                      ? _buildBottomBar(context, palette, source, position)
                      : null,
                );
              },
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomBar(
    BuildContext context,
    LibraryReaderPalette palette,
    LibraryReflowSource source,
    LibraryReflowPosition position,
  ) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    double fraction;
    try {
      fraction = source.fractionFor(position);
    } catch (_) {
      fraction = 0;
    }
    final shown = _sliderValue.value ?? fraction;
    final percent = (shown * 100).clamp(0, 100).round();
    final percentLabel = LibraryReaderLocale.format(
      context,
      'percentRead',
      <String, Object?>{'percent': percent},
    );
    final chapters = source.chapterCount;
    final multiple = chapters > 1 && source.separatesChapters;
    // Pages layout: the page in its chapter (the percentage stays for the
    // whole book).
    final pagesLabel = _activeLayout == LibraryTextLayout.pages
        ? _pagesLabel(context)
        : null;
    return LibraryReaderBottomBar(
      palette: palette,
      child: Row(
        children: <Widget>[
          if (multiple)
            LibraryReaderIconButton(
              icon: Icons.skip_previous_rounded,
              tooltip: t('previousChapter'),
              onPressed: position.chapter > 0 ? () => _goToChapter(-1) : null,
              color: palette.chromeForeground,
            ),
          Expanded(
            child: SizedBox(
              height: kLibraryReaderTouchTarget,
              child: Slider(
                value: shown.clamp(0.0, 1.0),
                activeColor: palette.accent,
                inactiveColor: palette.divider,
                semanticFormatterCallback: (_) =>
                    '${t('readingPosition')}: $percentLabel',
                onChangeStart: (value) {
                  _chrome.hold();
                  _sliderValue.value = value;
                },
                onChanged: (value) => _sliderValue.value = value,
                onChangeEnd: (value) {
                  _sliderValue.value = null;
                  _chrome.release();
                  unawaited(_jumpToFraction(value));
                },
              ),
            ),
          ),
          if (pagesLabel != null) ...<Widget>[
            ConstrainedBox(
              // The slider keeps most of the bar in portrait.
              constraints: const BoxConstraints(maxWidth: 150),
              child: Text(
                pagesLabel,
                key: const ValueKey<String>('library-book-pages-label'),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  color: palette.secondaryText,
                  fontSize: 13,
                  fontFeatures: const <FontFeature>[
                    FontFeature.tabularFigures(),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 12),
          ],
          Text(
            percentLabel,
            style: TextStyle(
              color: palette.chromeForeground,
              fontSize: 14,
              fontWeight: FontWeight.w600,
              fontFeatures: const <FontFeature>[FontFeature.tabularFigures()],
            ),
          ),
          if (multiple)
            LibraryReaderIconButton(
              icon: Icons.skip_next_rounded,
              tooltip: t('nextChapter'),
              onPressed: position.chapter < chapters - 1
                  ? () => _goToChapter(1)
                  : null,
              color: palette.chromeForeground,
            ),
        ],
      ),
    );
  }

  /// A spinner and [messageKey]: the book opening ('loadingBook'), its
  /// pages being laid out ('paginating').
  Widget _waiting(
    BuildContext context,
    LibraryReaderPalette palette,
    String messageKey,
  ) {
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
            LibraryReaderLocale.text(context, messageKey),
            style: TextStyle(color: palette.secondaryText, fontSize: 15),
          ),
        ],
      ),
    );
  }

  Widget _buildBody(BuildContext context, LibraryReaderPalette palette) {
    if (_opening) return _waiting(context, palette, 'loadingBook');
    final error = _openError;
    if (error != null) {
      return SafeArea(
        child: LibraryReaderErrorView(
          error: LibraryReaderErrorInfo.from(error),
          palette: palette,
          onRetry: () => unawaited(_open()),
          onClose: _close,
        ),
      );
    }
    final source = _source;
    if (source == null || source.chapterCount == 0) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            LibraryReaderLocale.text(context, 'emptyBook'),
            textAlign: TextAlign.center,
            style: TextStyle(color: palette.secondaryText, fontSize: 16),
          ),
        ),
      );
    }
    if (_activeLayout == LibraryTextLayout.pages) {
      return _buildPages(context, palette);
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        final size = constraints.biggest;
        return Listener(
          onPointerDown: (_) => _pointers++,
          onPointerUp: (_) => _pointers = _pointers > 0 ? _pointers - 1 : 0,
          onPointerCancel: (_) => _pointers = _pointers > 0 ? _pointers - 1 : 0,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTapUp: (details) => _onTapUp(details, size),
            child: NotificationListener<ScrollNotification>(
              onNotification: (notification) {
                // A drag (or a VoiceOver scroll, delivered as one); jumps
                // and layout changes are not user scrolls.
                if (notification is UserScrollNotification &&
                    notification.direction != ScrollDirection.idle) {
                  _userMoved();
                }
                if (notification is ScrollStartNotification) {
                  _trimTimer?.cancel();
                } else if (notification is ScrollEndNotification) {
                  _trackAfterLayout();
                  _maybeLoadMore();
                  _scheduleTrim();
                } else if (notification is ScrollUpdateNotification) {
                  _track();
                  _maybeLoadMore();
                }
                return false;
              },
              child: KeyedSubtree(
                key: _viewportKey,
                child: _buildScrollView(context, palette, source, size),
              ),
            ),
          ),
        );
      },
    );
  }

  /// Pages layout: the window of spreads once laid out, 'paginating'
  /// meanwhile.
  Widget _buildPages(BuildContext context, LibraryReaderPalette palette) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final body = constraints.biggest;
        final effective = _effective(
          reduceMotion: MediaQuery.disableAnimationsOf(context),
        );
        final geometry = _syncPages(context, body, palette, effective);
        final error = _pagesError;
        if (error != null) {
          return SafeArea(
            child: LibraryReaderErrorView(
              error: LibraryReaderErrorInfo.from(error),
              palette: palette,
              onRetry: _retryPages,
              onClose: _close,
            ),
          );
        }
        final window = _windowGeometry;
        // The pages shown before a typography change stay until the new
        // ones are laid out; pages of another size or pairing do not (a
        // closing route keeps them, scaled).
        if (_spread == null ||
            window == null ||
            (!window.fits(geometry) && !_leaving)) {
          return _waiting(
            context,
            palette,
            _windowShownOnce ? 'paginating' : 'loadingBook',
          );
        }
        return _buildPager(context, palette, geometry, effective, body);
      },
    );
  }

  Widget _buildPager(
    BuildContext context,
    LibraryReaderPalette palette,
    _BookPagesGeometry geometry,
    LibraryReaderEffectiveSettings effective,
    Size body,
  ) {
    final paginator = _paginator!;
    final window = _windowGeometry!;
    final rightToLeft = window.rule.rightToLeft;
    final current = _pagesReady && window.fits(geometry);
    // Both made with the first window (_showWindow).
    final curl = _curl!;
    final textures = _textures!;
    final pager = PageView.builder(
      key: ValueKey<int>(_windowGeneration),
      controller: _pager,
      // Right to left: the next spread comes from the left.
      reverse: rightToLeft,
      allowImplicitScrolling: true,
      physics: const PageScrollPhysics(parent: ClampingScrollPhysics()),
      itemCount: _slotCount,
      findChildIndexCallback: _slotIndexOfKey,
      itemBuilder: (context, index) => _buildSlot(palette, paginator, index),
    );
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapUp: (details) => _onPagesTapUp(details, body, geometry),
      child: Stack(
        children: <Widget>[
          Positioned.fromRect(
            rect: geometry.area,
            // Pages are placed on the left and right of the screen whatever
            // the direction of the interface.
            child: Directionality(
              textDirection: TextDirection.ltr,
              child: Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  NotificationListener<ScrollNotification>(
                    onNotification: _onPagerNotification,
                    child: pager,
                  ),
                  // Above the pager: it takes the horizontal drags it can
                  // curl; disabled (another style, Reduce Motion, pages
                  // being laid out again) every drag reaches the pager.
                  LibraryPageCurlLayer(
                    enabled:
                        effective.turnStyle == LibraryPageTurnStyle.curl &&
                        current,
                    controller: curl,
                    currentIndex: _virtualOrigin + _centerIndex,
                    itemCount: _virtualItems,
                    faceOf: _curlFaceOf,
                    render: _renderPageTexture,
                    onTurned: (item) => _arriveAt(item - _virtualOrigin),
                    // Textures are keyed by layout and colours.
                    contentKey: (_windowLayout, palette),
                    rightToLeft: rightToLeft,
                    paperColor: palette.background,
                    cache: textures,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSlot(
    LibraryReaderPalette palette,
    LibraryReflowPaginator paginator,
    int index,
  ) {
    final spread = _slotSpread(index);
    if (spread != null) {
      return LibraryBookSpreadView(
        key: _spreadKey(spread),
        spread: spread,
        paginator: paginator,
        palette: palette,
      );
    }
    final forward = index > _centerIndex;
    final error = forward ? _nextError : _previousError;
    return LibraryBookPagePlaceholder(
      key: ValueKey<String>(forward ? 'next-spread' : 'previous-spread'),
      palette: palette,
      error: error,
      onRetry: error == null ? null : () => _retryNeighbour(forward: forward),
    );
  }

  static Key _spreadKey(LibraryBookSpread spread) =>
      ValueKey<(int, int)>((spread.first.chapter, spread.first.indexInChapter));

  /// A spread keeps its element when the window moves around it.
  int? _slotIndexOfKey(Key key) {
    if (key is! ValueKey<(int, int)>) return null;
    for (var index = 0; index < _slotCount; index++) {
      final spread = _slotSpread(index);
      if (spread != null &&
          (spread.first.chapter, spread.first.indexInChapter) == key.value) {
        return index;
      }
    }
    return null;
  }

  Widget _buildScrollView(
    BuildContext context,
    LibraryReaderPalette palette,
    LibraryReflowSource source,
    Size size,
  ) {
    final style = LibraryReflowStyle.of(_settings, palette);
    final safe = MediaQuery.paddingOf(context);
    final horizontal = EdgeInsets.only(
      left: safe.left + style.margin,
      right: safe.right + style.margin,
    );
    var scroll = _scroll;
    if (scroll == null) {
      // The anchor unit at the top inset, or where the previous view showed
      // it (window cut back).
      scroll = _scroll = ScrollController(
        initialScrollOffset: _nextScrollOffset ?? -_topInset,
      );
      _nextScrollOffset = null;
    }
    final anchorChapter = _anchor.chapter;
    final anchorUnits =
        _chapters[anchorChapter]?.units ?? const <LibraryReflowUnit>[];
    final anchorUnit = anchorUnits.isEmpty
        ? 0
        : _anchorUnit.clamp(0, anchorUnits.length - 1);
    final separates = source.separatesChapters;
    final maxImageHeight = size.height * 0.85;

    Widget unitView(int chapter, int index, LibraryReflowUnit unit) =>
        LibraryReflowUnitView(
          key: ValueKey<String>('u-$chapter-$index'),
          unit: unit,
          chapter: chapter,
          unitIndex: index,
          style: style,
          horizontalPadding: horizontal,
          registry: _registry,
          onLink: (href) => unawaited(_onLink(href)),
          images: _images,
          maxImageHeight: maxImageHeight,
        );

    Widget separator() => SizedBox(
      height: style.fontSize * 3,
      child: Center(
        child: SizedBox(
          width: 48,
          child: Divider(color: palette.divider, height: 1),
        ),
      ),
    );

    // Reverse list of a whole chapter above the anchor (child 0 is its last
    // unit, adjacent to what follows).
    Widget reverseChapter(int chapter) {
      final units = _chapters[chapter]?.units ?? const <LibraryReflowUnit>[];
      final hasSeparator = separates && chapter > 0;
      return SliverList(
        key: ValueKey<String>('ch-$chapter-$_generation'),
        delegate: SliverChildBuilderDelegate((context, i) {
          if (i < units.length) {
            final index = units.length - 1 - i;
            return unitView(chapter, index, units[index]);
          }
          return separator();
        }, childCount: units.length + (hasSeparator ? 1 : 0)),
      );
    }

    Widget forwardChapter(int chapter) {
      final units = _chapters[chapter]?.units ?? const <LibraryReflowUnit>[];
      final hasSeparator = separates && chapter > 0;
      final offset = hasSeparator ? 1 : 0;
      return SliverList(
        key: ValueKey<String>('ch-$chapter-$_generation'),
        delegate: SliverChildBuilderDelegate((context, i) {
          if (i < offset) return separator();
          final index = i - offset;
          return unitView(chapter, index, units[index]);
        }, childCount: units.length + offset),
      );
    }

    Widget edge({required bool top}) {
      final chapter = top ? _windowStart - 1 : _windowEnd + 1;
      final atBookEdge = top
          ? _windowStart == 0
          : _windowEnd >= source.chapterCount - 1;
      if (atBookEdge) {
        if (top) return SizedBox(height: _topInset + 8);
        return Padding(
          padding: EdgeInsets.fromLTRB(24, 32, 24, 48 + safe.bottom),
          child: Column(
            children: <Widget>[
              Icon(Icons.menu_book_rounded, color: palette.secondaryText),
              const SizedBox(height: 8),
              Text(
                LibraryReaderLocale.text(context, 'endOfBook'),
                textAlign: TextAlign.center,
                style: TextStyle(color: palette.secondaryText, fontSize: 15),
              ),
            ],
          ),
        );
      }
      final error = _chapterErrors[chapter];
      if (error != null) {
        return SizedBox(
          height: 260,
          child: LibraryReaderErrorView(
            error: LibraryReaderErrorInfo.from(error),
            palette: palette,
            compact: true,
            onRetry: () => _retryEdge(chapter),
          ),
        );
      }
      return SizedBox(
        height: 96,
        child: Center(
          child: SizedBox(
            width: 24,
            height: 24,
            child: CircularProgressIndicator(
              strokeWidth: 2.5,
              color: palette.secondaryText,
            ),
          ),
        ),
      );
    }

    final centerKey = ValueKey<String>('center-$_generation');
    final hasAnchorSeparator = separates && anchorChapter > 0;
    final slivers = <Widget>[
      SliverToBoxAdapter(child: edge(top: true)),
      for (var c = _windowStart; c < anchorChapter; c++) reverseChapter(c),
      SliverList(
        key: ValueKey<String>('before-$_generation'),
        delegate: SliverChildBuilderDelegate((context, i) {
          if (i < anchorUnit) {
            final index = anchorUnit - 1 - i;
            return unitView(anchorChapter, index, anchorUnits[index]);
          }
          return separator();
        }, childCount: anchorUnit + (hasAnchorSeparator ? 1 : 0)),
      ),
      SliverList(
        key: centerKey,
        delegate: SliverChildBuilderDelegate((context, i) {
          final index = anchorUnit + i;
          return unitView(anchorChapter, index, anchorUnits[index]);
        }, childCount: anchorUnits.length - anchorUnit),
      ),
      for (var c = anchorChapter + 1; c <= _windowEnd; c++) forwardChapter(c),
      SliverToBoxAdapter(child: edge(top: false)),
    ];
    return CustomScrollView(
      key: ValueKey<String>('book-$_generation'),
      controller: scroll,
      center: centerKey,
      scrollCacheExtent: const ScrollCacheExtent.viewport(0.75),
      slivers: slivers,
    );
  }
}
