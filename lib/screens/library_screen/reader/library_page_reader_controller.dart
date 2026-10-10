import 'dart:async';

import 'package:flutter/foundation.dart';

import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';

import 'library_page_reader_content.dart';
import 'library_page_source.dart';
import 'library_reader_errors.dart';

enum LibraryPageReaderStatus { loading, ready, error }

enum LibraryPageReaderMode { paged, vertical }

/// State of a page reader session: the chapter shown, its pages, the
/// current page, the reading layout and the saved progress.
///
/// Progress is written to [store] debounced (and at once by [saveNow], on
/// chapter changes and on [dispose]); reaching the last page of an online
/// chapter marks it read.
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
  Timer? _saveTimer;
  bool _dirty = false;
  bool _disposed = false;
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

  LibraryReaderSettings get settings => store.settings;

  /// Paged or vertical, from the session override, the settings, then the
  /// content's hint.
  LibraryPageReaderMode get mode {
    final override = _modeOverride;
    if (override != null) return override;
    return switch (settings.mangaMode) {
      LibraryMangaMode.paged => LibraryPageReaderMode.paged,
      LibraryMangaMode.vertical => LibraryPageReaderMode.vertical,
      LibraryMangaMode.auto =>
        content.layoutHint == LibraryPageLayoutHint.vertical
            ? LibraryPageReaderMode.vertical
            : LibraryPageReaderMode.paged,
    };
  }

  /// Right-to-left page turning (manga) in paged mode.
  bool get rightToLeft {
    if (settings.mangaMode == LibraryMangaMode.auto) {
      switch (content.layoutHint) {
        case LibraryPageLayoutHint.rightToLeft:
          return true;
        case LibraryPageLayoutHint.leftToRight:
        case LibraryPageLayoutHint.vertical:
          return false;
        case LibraryPageLayoutHint.unknown:
          break;
      }
    }
    return settings.pageDirection == LibraryPageDirection.rtl;
  }

  /// Switches between paged and vertical for this session only.
  void toggleMode() {
    _modeOverride = mode == LibraryPageReaderMode.paged
        ? LibraryPageReaderMode.vertical
        : LibraryPageReaderMode.paged;
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

  /// Opens chapter [index] at its first page, or its last with [fromEnd].
  Future<void> openChapter(int index, {bool fromEnd = false}) {
    if (index < 0 || index >= content.chapters.length) {
      return Future<void>.value();
    }
    return _load(index, requestedPage: fromEnd ? -1 : 0, resume: false);
  }

  Future<void> nextChapter() =>
      hasNextChapter ? openChapter(_chapterIndex + 1) : Future<void>.value();

  Future<void> previousChapter({bool fromEnd = false}) => hasPreviousChapter
      ? openChapter(_chapterIndex - 1, fromEnd: fromEnd)
      : Future<void>.value();

  /// Loads the current chapter again after an error.
  Future<void> retry() =>
      _load(_chapterIndex, requestedPage: _retryPage, resume: _retryResume);

  /// The view shows page [page] (zero-based) of the chapter.
  void setPage(int page) {
    if (_status != LibraryPageReaderStatus.ready || pageCount == 0) return;
    final clamped = page.clamp(0, pageCount - 1);
    if (clamped == _page) return;
    _page = clamped;
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

  void _pageShown() {
    _dirty = true;
    if (content.tracksChapters && isLastPage && _markedRead.add(chapter.id)) {
      store.markChapter(
        content.progressKey,
        chapter.id,
        read: true,
        page: _page,
        pageCount: pageCount,
      );
    }
    _saveTimer?.cancel();
    _saveTimer = Timer(saveDelay, saveNow);
  }

  /// Overall reading fraction: the page inside the chapter, and for online
  /// titles the chapter inside the title.
  double get fraction {
    final count = pageCount;
    if (count == 0) return 0;
    final inChapter = (_page + 1) / count;
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
    store.saveProgress(
      LibraryReadingProgress(
        key: content.progressKey,
        location: LibraryReadingProgress.pageLocation(_page),
        fraction: fraction,
        pageIndex: _page,
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
        page: _page,
        pageCount: pageCount,
      );
    }
  }

  /// Saves and writes the store file (app going to the background).
  Future<void> flush() async {
    saveNow();
    await store.flush();
  }

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
