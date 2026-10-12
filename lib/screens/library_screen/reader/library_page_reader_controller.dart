import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/foundation.dart';

import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_page_reader_content.dart';
import 'library_page_source.dart';
import 'library_reader_effective_settings.dart';
import 'library_reader_errors.dart';

enum LibraryPageReaderStatus { loading, ready, error }

enum LibraryPageReaderMode { paged, vertical }

/// State of a page reader session: the chapter shown, its pages, the
/// current page, the reading layout and the saved progress.
///
/// Progress is written to [store] debounced (and at once by [saveNow], on
/// chapter changes and on [dispose]); reaching the last page of an online
/// chapter marks it read (in a two-page spread, showing it beside the page
/// before does). The page saved, for the position and the chapter mark, is
/// [page], or the last page once it is on screen: a spread is recorded
/// under its first page, and a chapter finished on its last spread must be
/// saved as finished (it starts again at its beginning, and the title page
/// continues with the next chapter), as a single last page is.
///
/// The reading layout follows [effective]: session override > settings of
/// the title (`LibraryReadingStore.bookSettingsFor`) > content hint >
/// global settings (docs/library-books-3d-plan.md § 3.9).
class LibraryPageReaderController extends ChangeNotifier {
  LibraryPageReaderController({
    required this.content,
    required this.store,
    this.saveDelay = const Duration(milliseconds: 700),
  }) : _chapterIndex = content.initialChapterIndex.clamp(
         0,
         content.chapters.isEmpty ? 0 : content.chapters.length - 1,
       );

  final LibraryPageReaderContent content;
  final LibraryReadingStore store;
  final Duration saveDelay;

  LibraryPageReaderStatus _status = LibraryPageReaderStatus.loading;
  Object? _error;
  LibraryPageSource? _source;
  int _chapterIndex;
  int _page = 0;
  int _generation = 0;
  LibraryCancelToken? _token;
  LibraryPageReaderMode? _modeOverride;
  bool? _directionOverride;
  bool _reduceMotion = false;

  /// Last page on screen, at least [_page] (a two-page spread shows the
  /// next one beside it).
  int _lastShown = 0;
  Timer? _saveTimer;
  bool _dirty = false;
  bool _disposed = false;
  bool _finished = false;
  bool _started = false;
  int? _retryPage;
  bool _retryResume = true;
  final Set<String> _markedRead = <String>{};

  LibraryPageReaderStatus get status => _status;

  /// Failure of the last load (typed; translate with
  /// [LibraryReaderErrorInfo.from]).
  Object? get error => _error;

  LibraryPageSource? get source => _source;

  int get chapterIndex => _chapterIndex;

  LibraryPageReaderChapter get chapter => content.chapters[_chapterIndex];

  /// Zero-based page of the chapter.
  int get page => _page;

  int get pageCount => _source?.length ?? 0;

  /// Increments whenever a chapter's pages become ready (views reset their
  /// scroll positions on change).
  int get generation => _generation;

  bool get hasPreviousChapter => _chapterIndex > 0;

  bool get hasNextChapter => _chapterIndex < content.chapters.length - 1;

  bool get isLastPage => pageCount > 0 && _page >= pageCount - 1;

  /// Last page on screen: [page], or the page shown beside it in a two-page
  /// spread (paged layout only).
  int get lastShownPage =>
      mode == LibraryPageReaderMode.vertical ? _page : _lastShown;

  /// Whether the last page of the chapter is on screen (alone or in a
  /// spread).
  bool get lastPageShown => pageCount > 0 && lastShownPage >= pageCount - 1;

  /// Global reader settings.
  LibraryReaderSettings get settings => store.settings;

  /// Settings chosen for this title (null: the global ones apply).
  LibraryReaderBookSettings? get bookSettings =>
      store.bookSettingsFor(content.progressKey);

  /// What this session imposes: [toggleMode], [overrideDirection] and, with
  /// [reduceMotion], pages turned without animation.
  LibraryReaderSessionOverrides get sessionOverrides =>
      LibraryReaderSessionOverrides(
        mode: _modeOverride,
        pageDirection: switch (_directionOverride) {
          null => null,
          true => LibraryPageDirection.rtl,
          false => LibraryPageDirection.ltr,
        },
        turnStyle: _reduceMotion ? LibraryPageTurnStyle.none : null,
      );

  /// The settings in effect: session override > settings of the title >
  /// content hint (automatic mode) > global settings.
  LibraryReaderEffectiveSettings get effective =>
      LibraryReaderEffectiveSettings.resolve(
        global: settings,
        book: bookSettings,
        hint: content.layoutHint,
        session: sessionOverrides,
      );

  /// Paged or vertical: the session override, the title's mode, the
  /// content's hint in automatic mode, then the global mode ([effective]).
  LibraryPageReaderMode get mode => effective.mode;

  /// Right-to-left page turning (manga) in paged mode: the direction chosen
  /// in this session, else the title's direction, else the content's hint
  /// in automatic mode, else the global setting ([effective]).
  bool get rightToLeft => effective.rightToLeft;

  /// Page turn of the paged layout ([LibraryPageTurnStyle.none] with
  /// [reduceMotion]).
  LibraryPageTurnStyle get turnStyle => effective.turnStyle;

  /// The system asks for reduced motion (the reader passes
  /// `libraryReduceMotion`, iOS's Reduce Motion included): pages turn
  /// without animation, whatever the settings say (a session override,
  /// never saved).
  bool get reduceMotion => _reduceMotion;

  set reduceMotion(bool value) {
    if (_reduceMotion == value) return;
    _reduceMotion = value;
    _notify();
  }

  /// Switches between paged and vertical for this session only.
  void toggleMode() {
    _modeOverride = mode == LibraryPageReaderMode.paged
        ? LibraryPageReaderMode.vertical
        : LibraryPageReaderMode.paged;
    _notify();
  }

  /// The reader chose [direction] while open: it applies at once, also
  /// where the content's hint decided (automatic mode).
  void overrideDirection(LibraryPageDirection direction) {
    final rtl = direction == LibraryPageDirection.rtl;
    if (_directionOverride == rtl) return;
    _directionOverride = rtl;
    _notify();
  }

  /// Lets the stored setting decide again (after it changed).
  void clearModeOverride() {
    if (_modeOverride == null) return;
    _modeOverride = null;
    _notify();
  }

  /// Loads the initial chapter at the requested or saved page.
  Future<void> start() async {
    if (_started) return;
    _started = true;
    try {
      await store.load();
    } catch (_) {
      // The store keeps working in memory.
    }
    if (_disposed) return;
    await _load(
      _chapterIndex,
      requestedPage: content.startPage,
      resume: content.startPage == null,
    );
  }

  /// Opens chapter [index] at its first page, its last with [fromEnd], or
  /// at [page] (zero-based, clamped: a bookmark).
  Future<void> openChapter(int index, {bool fromEnd = false, int? page}) {
    if (index < 0 || index >= content.chapters.length) {
      return Future<void>.value();
    }
    return _load(
      index,
      requestedPage: page ?? (fromEnd ? -1 : 0),
      resume: false,
    );
  }

  Future<void> nextChapter() =>
      hasNextChapter ? openChapter(_chapterIndex + 1) : Future<void>.value();

  Future<void> previousChapter({bool fromEnd = false}) => hasPreviousChapter
      ? openChapter(_chapterIndex - 1, fromEnd: fromEnd)
      : Future<void>.value();

  /// Loads the current chapter again after an error.
  Future<void> retry() =>
      _load(_chapterIndex, requestedPage: _retryPage, resume: _retryResume);

  /// The view shows page [page] (zero-based) of the chapter and, in a
  /// two-page spread, the pages up to [through] beside it. [page] is the
  /// position saved; [through] counts for [lastPageShown] and [fraction].
  void setPage(int page, {int? through}) {
    if (_finished) return;
    if (_status != LibraryPageReaderStatus.ready || pageCount == 0) return;
    final clamped = page.clamp(0, pageCount - 1);
    final last = math.max(
      clamped,
      (through ?? clamped).clamp(0, pageCount - 1),
    );
    if (clamped == _page && last == _lastShown) return;
    _page = clamped;
    _lastShown = last;
    _notify();
    _pageShown();
  }

  Future<void> _load(
    int index, {
    int? requestedPage,
    required bool resume,
  }) async {
    saveNow();
    _token?.cancel();
    final token = LibraryCancelToken();
    _token = token;
    final previous = _source;
    _source = null;
    _chapterIndex = index;
    _status = LibraryPageReaderStatus.loading;
    _error = null;
    _retryPage = requestedPage;
    _retryResume = resume;
    _notify();
    if (previous != null) unawaited(previous.dispose());
    try {
      final source = await content.load(index, token);
      if (token.isCancelled || _disposed) {
        unawaited(source.dispose());
        return;
      }
      if (source.length == 0) {
        unawaited(source.dispose());
        throw const LibraryBookException(
          LibraryBookIssue.noContent,
          detail: 'no page',
        );
      }
      _source = source;
      _page = _startPage(
        source.length,
        requested: requestedPage,
        resume: resume,
      );
      _lastShown = _page;
      _status = LibraryPageReaderStatus.ready;
      _generation++;
      _notify();
      _pageShown();
    } catch (error) {
      if (token.isCancelled || _disposed) return;
      if (LibraryReaderErrorInfo.isCancellation(error)) return;
      _status = LibraryPageReaderStatus.error;
      _error = error;
      _notify();
    }
  }

  int _startPage(int count, {int? requested, required bool resume}) {
    if (requested != null) {
      return requested < 0 ? count - 1 : requested.clamp(0, count - 1);
    }
    if (!resume) return 0;
    final saved = store.progressFor(content.progressKey);
    if (!content.tracksChapters) {
      final page = saved?.pageIndex ?? saved?.locationPage;
      return page == null ? 0 : page.clamp(0, count - 1);
    }
    final chapterId = chapter.id;
    int? page;
    if (saved != null && saved.chapterId == chapterId) {
      page = saved.pageIndex ?? saved.locationPage;
    }
    final mark = store.chapterMark(content.progressKey, chapterId);
    page ??= mark?.page;
    if (page == null) return 0;
    // A finished chapter opens again at its beginning.
    if (mark?.read == true && page >= count - 1) return 0;
    return page.clamp(0, count - 1);
  }

  /// The page saved for the position and the chapter mark (see the class
  /// documentation).
  int get _savedPage => lastPageShown ? pageCount - 1 : _page;

  void _pageShown() {
    if (_finished) return;
    _dirty = true;
    if (content.tracksChapters &&
        lastPageShown &&
        _markedRead.add(chapter.id)) {
      store.markChapter(
        content.progressKey,
        chapter.id,
        read: true,
        page: _savedPage,
        pageCount: pageCount,
      );
    }
    _saveTimer?.cancel();
    _saveTimer = Timer(saveDelay, saveNow);
  }

  /// Overall reading fraction: the last page shown inside the chapter (a
  /// spread counts both its pages), and for online titles the chapter
  /// inside the title.
  double get fraction {
    final count = pageCount;
    if (count == 0) return 0;
    final inChapter = (lastShownPage + 1) / count;
    if (!content.tracksChapters || content.chapters.length <= 1) {
      return inChapter;
    }
    return (_chapterIndex + inChapter) / content.chapters.length;
  }

  /// Writes the pending progress to the store now.
  void saveNow() {
    _saveTimer?.cancel();
    _saveTimer = null;
    if (!_dirty || _source == null) return;
    _dirty = false;
    final tracks = content.tracksChapters;
    final page = _savedPage;
    store.saveProgress(
      LibraryReadingProgress(
        key: content.progressKey,
        location: LibraryReadingProgress.pageLocation(page),
        fraction: fraction,
        pageIndex: page,
        pageCount: pageCount,
        chapterId: tracks ? chapter.id : null,
        chapterTitle: tracks && chapter.title.isNotEmpty ? chapter.title : null,
        title: content.title,
        subtitle: content.subtitle,
        coverUrl: content.coverUrl,
        coverHeaders: content.coverHeaders,
      ),
    );
    if (tracks) {
      store.markChapter(
        content.progressKey,
        chapter.id,
        page: page,
        pageCount: pageCount,
      );
    }
  }

  /// Saves and writes the store file (app going to the background).
  Future<void> flush() async {
    saveNow();
    await store.flush();
  }

  /// The reader is closing: saves the pending progress now, while the
  /// screens below can still rebuild for it (from [dispose], the store
  /// would notify them while the widget tree is locked), and ignores the
  /// pages the closing view reports afterwards (it can still move, for
  /// example when it rotates back to landscape).
  void finish() {
    saveNow();
    _finished = true;
  }

  /// Whether [finish] was called.
  bool get finished => _finished;

  void _notify() {
    if (!_disposed) notifyListeners();
  }

  @override
  void dispose() {
    saveNow();
    _disposed = true;
    _saveTimer?.cancel();
    _token?.cancel();
    final source = _source;
    _source = null;
    if (source != null) unawaited(source.dispose());
    super.dispose();
  }
}
