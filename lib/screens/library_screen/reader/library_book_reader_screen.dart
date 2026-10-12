import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart'
    show RenderSliver, ScrollCacheExtent, ScrollDirection;
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_reader_orientation.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_reader_chrome.dart';
import 'library_reader_errors.dart';
import 'library_reader_gamepad.dart';
import 'library_reader_palette.dart';
import 'library_reader_sheets.dart';
import 'library_reader_system.dart';
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

/// Reflowable reader for EPUB and plain text.
///
/// One chapter (EPUB document, TXT section) is laid out lazily at a time:
/// the scroll view is centred on the block being read, earlier blocks grow
/// upwards in a reverse sliver, so the reader opens anywhere without laying
/// out what comes before. Neighbouring chapters are appended as the reader
/// scrolls. The position (first visible block + character offset) survives
/// font, theme and orientation changes and is stored as an EPUB CFI or a
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
    with WidgetsBindingObserver {
  late final LibraryReadingStore _store;
  late final LibraryReaderChromeController _chrome;
  late final LibraryReaderSystemSession _system;
  late LibraryReaderSettings _settings;
  late final LibraryReflowImageCache _images;

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

  /// Reading position (first visible block of the current layout).
  @visibleForTesting
  LibraryReflowPosition? get currentPosition => _readingPosition();

  @visibleForTesting
  bool get chromeVisible => _chrome.visible;

  /// Chapters whose display units are in memory (tests).
  @visibleForTesting
  Set<int> get chaptersInMemory => Set<int>.of(_chapters.keys);

  /// First and last chapter laid out (tests).
  @visibleForTesting
  (int, int) get window => (_windowStart, _windowEnd);

  @visibleForTesting
  LibraryReaderGamepadBindings get gamepadBindings =>
      LibraryReaderGamepadBindings(
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
    final settings = _store.settings;
    if (settings == _settings || !mounted) return;
    final previous = _settings;
    final relayout =
        previous.fontSize != settings.fontSize ||
        previous.lineHeight != settings.lineHeight ||
        previous.fontFamily != settings.fontFamily ||
        previous.margin != settings.margin ||
        previous.justify != settings.justify;
    if (relayout && _source != null) {
      // Keep reading the same words with the new typography.
      final position = _readingPosition();
      if (position != null) {
        _lastPosition = position;
        _setAnchor(position);
      }
    }
    setState(() => _settings = settings);
    _system.update(settings);
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
      final data = _ensureChapterData(start.chapter);
      if (data == null) throw StateError('chapter not loaded');
      _windowStart = start.chapter;
      _windowEnd = start.chapter;
      _releaseFarChapters();
      _setAnchor(start);
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
    if (ready && _lastWidth != null && _lastWidth != width) {
      // Rotation: same words at the top in the new layout.
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

  Widget _buildBody(BuildContext context, LibraryReaderPalette palette) {
    if (_opening) {
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
              LibraryReaderLocale.text(context, 'loadingBook'),
              style: TextStyle(color: palette.secondaryText, fontSize: 15),
            ),
          ],
        ),
      );
    }
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
