import 'dart:math' as math;

import 'package:flutter/material.dart';

import 'package:neostation/l10n/library_reader_locale.dart';

import 'library_reader_chrome.dart';
import 'library_reader_palette.dart';

// Toolbar of the Library readers (Build 447, docs/library-books-3d-plan.md
// § 3.8). Its mode (hidden after 4 s like the 440 chrome, or always shown)
// is `LibraryReaderToolbarMode`, kept with the other reader settings in
// lib/services/library_reading_store.dart; the readers pass it to
// `LibraryReaderChromeController.alwaysVisible`.

/// What the contents action of a reader opens.
enum LibraryReaderContents {
  /// The table of contents of a book (EPUB contents, PDF outline).
  tableOfContents,

  /// The chapters of an online title.
  chapters,
}

/// Reading progress shown by [LibraryReaderToolbar].
@immutable
class LibraryReaderToolbarProgress {
  const LibraryReaderToolbarProgress({
    this.page,
    this.pageCount,
    this.lastPage,
    required this.fraction,
    this.remainingInChapter,
    this.remainingInBook,
    this.chapterTitle,
    this.paginating = false,
  });

  /// One-based page shown (in its chapter for the EPUB/TXT pages); null
  /// where the reader's page slider already prints the page ("n / N").
  final int? page;

  /// Number of pages [page] counts in (the book, or the chapter shown).
  final int? pageCount;

  /// One-based second page of a two-page spread shown with [page].
  final int? lastPage;

  /// Overall progress in the book or title, 0..1.
  final double fraction;

  /// Estimated reading time left in the chapter ([LibraryReadingPace]);
  /// null while unknown or without chapters.
  final Duration? remainingInChapter;

  /// Estimated reading time left in the book; null while unknown.
  final Duration? remainingInBook;

  /// Chapter label printed by the source or the book (never translated),
  /// read by VoiceOver with the progress.
  final String? chapterTitle;

  /// The pages of the chapter shown are being laid out: "Laying out
  /// pages…" stands for the page.
  final bool paginating;

  @override
  bool operator ==(Object other) =>
      other is LibraryReaderToolbarProgress &&
      other.page == page &&
      other.pageCount == pageCount &&
      other.lastPage == lastPage &&
      other.fraction == fraction &&
      other.remainingInChapter == remainingInChapter &&
      other.remainingInBook == remainingInBook &&
      other.chapterTitle == chapterTitle &&
      other.paginating == paginating;

  @override
  int get hashCode => Object.hash(
    page,
    pageCount,
    lastPage,
    fraction,
    remainingInChapter,
    remainingInBook,
    chapterTitle,
    paginating,
  );
}

/// The toolbar of a reader, drawn inside its `LibraryReaderBottomBar`
/// (docs/library-books-3d-plan.md § 3.8): the reader's [slider] row, then
/// Settings, Bookmarks, Contents (or Chapters) when the reader has them, the
/// progress (page, percentage, time left), the reader's [extra] buttons and
/// Library.
///
/// Library closes the reader through its own close path ([onLibrary], the
/// action of the back control): it is never a second Back (its label is
/// "Library", not "Back"), and like the rest of the bar it leaves the
/// semantics tree and the focus order while the bars are hidden.
class LibraryReaderToolbar extends StatelessWidget {
  const LibraryReaderToolbar({
    super.key,
    required this.palette,
    required this.progress,
    required this.onSettings,
    required this.onBookmarks,
    this.onContents,
    this.contents = LibraryReaderContents.tableOfContents,
    required this.onLibrary,
    this.slider,
    this.extra = const <Widget>[],
    this.bookmarked = false,
    this.settingsIcon = Icons.tune_rounded,
  });

  final LibraryReaderPalette palette;
  final LibraryReaderToolbarProgress progress;
  final VoidCallback onSettings;

  /// Opens the bookmarks of the title; null (disabled) where nothing can
  /// be kept (a PDF read without a progress key).
  final VoidCallback? onBookmarks;

  /// Opens the table of contents or the chapters ([contents]); null when
  /// the reader has none.
  final VoidCallback? onContents;
  final LibraryReaderContents contents;

  /// The reader's close action (the one of its back control).
  final VoidCallback onLibrary;

  /// The reader's page slider row, above the actions.
  final Widget? slider;

  /// Buttons of the reader between the progress and Library (layout
  /// switch).
  final List<Widget> extra;

  /// Whether the position shown carries a bookmark (filled icon).
  final bool bookmarked;
  final IconData settingsIcon;

  /// Height of each row (slider, actions).
  static const double rowHeight = kLibraryReaderTouchTarget;

  /// The page label of the progress ("Page N of M", "Laying out pages…").
  /// Its value predates the toolbar: the EPUB/TXT pages layout (Build 447
  /// phase 6) showed this label in its bottom bar.
  static const Key pageLabelKey = ValueKey<String>('library-book-pages-label');

  /// The percentage of the progress.
  static const Key percentKey = ValueKey<String>('library-reader-percent');

  /// The time left of the progress ("N min left in chapter").
  static const Key timeLeftKey = ValueKey<String>('library-reader-time-left');

  /// Height of a `LibraryReaderBottomBar` holding a toolbar, with or without
  /// its [slider] row, the bottom of the safe area included: what a reader
  /// whose bars stay shown keeps free below its pages.
  static double barExtent(BuildContext context, {bool slider = true}) =>
      MediaQuery.paddingOf(context).bottom + 8 + (slider ? 2 : 1) * rowHeight;

  @override
  Widget build(BuildContext context) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    final color = palette.chromeForeground;
    final chapters = contents == LibraryReaderContents.chapters;
    final contentsAction = onContents;
    final actions = Row(
      children: <Widget>[
        LibraryReaderIconButton(
          icon: settingsIcon,
          tooltip: t('settings'),
          onPressed: onSettings,
          color: color,
        ),
        LibraryReaderIconButton(
          icon: bookmarked
              ? Icons.bookmark_rounded
              : Icons.bookmark_border_rounded,
          tooltip: t('bookmarks'),
          onPressed: onBookmarks,
          color: color,
        ),
        if (contentsAction != null)
          LibraryReaderIconButton(
            icon: chapters
                ? Icons.format_list_numbered_rounded
                : Icons.toc_rounded,
            tooltip: t(chapters ? 'chapters' : 'tableOfContents'),
            onPressed: contentsAction,
            color: color,
          ),
        const SizedBox(width: 4),
        Expanded(
          child: _LibraryReaderProgressView(
            palette: palette,
            progress: progress,
          ),
        ),
        const SizedBox(width: 4),
        ...extra,
        LibraryReaderIconButton(
          icon: Icons.local_library_rounded,
          tooltip: t('library'),
          onPressed: onLibrary,
          color: color,
        ),
      ],
    );
    final slider = this.slider;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (slider != null) SizedBox(height: rowHeight, child: slider),
        SizedBox(height: rowHeight, child: actions),
      ],
    );
  }
}

/// Minutes shown for [time] (rounded up, at least one).
int libraryReaderMinutesLeft(Duration time) =>
    math.max(1, (time.inSeconds / 60).ceil());

class _LibraryReaderProgressView extends StatelessWidget {
  const _LibraryReaderProgressView({
    required this.palette,
    required this.progress,
  });

  final LibraryReaderPalette palette;
  final LibraryReaderToolbarProgress progress;

  @override
  Widget build(BuildContext context) {
    String t(String key) => LibraryReaderLocale.text(context, key);
    String f(String key, Map<String, Object?> values) =>
        LibraryReaderLocale.format(context, key, values);
    final progress = this.progress;
    final percent = f('percentRead', <String, Object?>{
      'percent': (progress.fraction.isNaN ? 0.0 : progress.fraction * 100)
          .clamp(0, 100)
          .round(),
    });
    final page = progress.page;
    final pageCount = progress.pageCount;
    final lastPage = progress.lastPage;
    final String? pageLabel;
    if (progress.paginating) {
      pageLabel = t('paginating');
    } else if (page != null && pageCount != null) {
      pageLabel = lastPage != null && lastPage != page
          ? f('pagesOfTotal', <String, Object?>{
              'first': page,
              'second': lastPage,
              'total': pageCount,
            })
          : f('pageOfTotal', <String, Object?>{
              'page': page,
              'total': pageCount,
            });
    } else {
      pageLabel = null;
    }
    String? left(Duration? time, String key) =>
        time == null || time <= Duration.zero
        ? null
        : f(key, <String, Object?>{'minutes': libraryReaderMinutesLeft(time)});
    final inChapter = left(progress.remainingInChapter, 'timeLeftInChapter');
    final inBook = left(progress.remainingInBook, 'timeLeftInBook');
    // One time on screen (the chapter's when known); VoiceOver hears both.
    final shownTime = inChapter ?? inBook;
    final hiddenTime = inChapter != null ? inBook : null;
    final figures = <FontFeature>[const FontFeature.tabularFigures()];
    final firstLine = Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        if (pageLabel != null) ...<Widget>[
          Flexible(
            child: Text(
              pageLabel,
              key: LibraryReaderToolbar.pageLabelKey,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: palette.secondaryText,
                fontSize: 13,
                fontFeatures: figures,
              ),
            ),
          ),
          const SizedBox(width: 10),
        ],
        Text(
          percent,
          key: LibraryReaderToolbar.percentKey,
          maxLines: 1,
          style: TextStyle(
            color: palette.chromeForeground,
            fontSize: 14,
            fontWeight: FontWeight.w600,
            fontFeatures: figures,
          ),
        ),
      ],
    );
    final chapterTitle = progress.chapterTitle;
    return Semantics(
      container: true,
      label: t('progress'),
      child: LayoutBuilder(
        builder: (context, constraints) => FittedBox(
          // Large text sizes: the lines shrink to the bar, never overflow.
          fit: BoxFit.scaleDown,
          child: ConstrainedBox(
            constraints: BoxConstraints(
              maxWidth: constraints.maxWidth.isFinite
                  ? constraints.maxWidth
                  : double.infinity,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                if (chapterTitle != null && chapterTitle.isNotEmpty)
                  Semantics(label: chapterTitle, child: const SizedBox()),
                firstLine,
                if (shownTime != null)
                  Text(
                    shownTime,
                    key: LibraryReaderToolbar.timeLeftKey,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      color: palette.secondaryText,
                      fontSize: 12,
                      fontFeatures: figures,
                    ),
                  ),
                if (hiddenTime != null)
                  Semantics(label: hiddenTime, child: const SizedBox()),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Lays a reader's content between its bars while they stay shown
/// ([enabled]: `LibraryReaderToolbarMode.always`): below the top bar
/// ([top]) and above the toolbar ([bottom]), the safe area those bars cover
/// taken out of the content's `MediaQuery` padding. Pages and lines are
/// then never under a bar that cannot be hidden. With automatic bars the
/// content stays edge to edge, under the bars while they are shown.
///
/// The widget structure is the same in both modes, so switching keeps the
/// state of the content (scroll positions, page views).
class LibraryReaderBarsInset extends StatelessWidget {
  const LibraryReaderBarsInset({
    super.key,
    required this.enabled,
    required this.child,
    this.top = true,
    this.bottom = true,
    this.slider = true,
  });

  final bool enabled;
  final Widget child;

  /// Keeps the top bar's height free (the EPUB/TXT reader already lays its
  /// first line out below the back control).
  final bool top;
  final bool bottom;

  /// Whether the toolbar has its slider row.
  final bool slider;

  @override
  Widget build(BuildContext context) {
    final insetTop = enabled && top;
    final insetBottom = enabled && bottom;
    return Padding(
      padding: EdgeInsets.only(
        top: insetTop ? libraryReaderTopBarExtent(context) : 0,
        bottom: insetBottom
            ? LibraryReaderToolbar.barExtent(context, slider: slider)
            : 0,
      ),
      child: MediaQuery.removePadding(
        context: context,
        removeTop: insetTop,
        removeBottom: insetBottom,
        child: child,
      ),
    );
  }
}

/// Reading pace of one reader session, for the time left of the toolbar:
/// the time spent on each page turned forward while reading, averaged over
/// the last [window] turns. No estimate before [minimumTurns] turns.
///
/// Readers call [pageShown] when the reader turns to the next page or
/// spread, and [restart] when the position changes otherwise (a jump, a
/// turn back, another chapter, the book opening): the clock starts again
/// without counting anything.
class LibraryReadingPace {
  LibraryReadingPace({
    DateTime Function()? clock,
    this.window = 10,
    this.minimumTurns = 3,
    this.shortestTurn = const Duration(milliseconds: 500),
    this.longestTurn = const Duration(minutes: 10),
  }) : _clock = clock;

  /// Clock of the paces made without one. Widget tests replace it: their
  /// fake time does not move `DateTime.now`.
  @visibleForTesting
  static DateTime Function() defaultClock = DateTime.now;

  final DateTime Function()? _clock;

  /// Turns averaged.
  final int window;

  /// Turns counted before [remaining] gives an estimate.
  final int minimumTurns;

  /// A page turned faster than this was not read (flicking through).
  final Duration shortestTurn;

  /// A turn slower than this means the reader was left open: not counted.
  final Duration longestTurn;

  /// Seconds per page of the last turns counted, the oldest first.
  final List<double> _secondsPerPage = <double>[];
  DateTime? _since;

  DateTime _now() => (_clock ?? defaultClock)();

  /// Turns counted (at most [window]).
  int get turns => _secondsPerPage.length;

  /// The reader turned forward to the next page or spread after reading
  /// [pages] pages (a spread: two). The time since the previous call (or
  /// [restart]) counts for each of them; the first call only starts the
  /// clock. A turn faster than [shortestTurn] per page or slower than
  /// [longestTurn] is not counted.
  void pageShown({int pages = 1}) {
    final now = _now();
    final since = _since;
    _since = now;
    if (since == null || pages < 1) return;
    final elapsed = now.difference(since);
    if (elapsed > longestTurn) return;
    final perPage =
        elapsed.inMicroseconds / pages / Duration.microsecondsPerSecond;
    if (perPage * Duration.microsecondsPerSecond <
        shortestTurn.inMicroseconds) {
      return;
    }
    _secondsPerPage.add(perPage);
    while (_secondsPerPage.length > window) {
      _secondsPerPage.removeAt(0);
    }
  }

  /// The position changed without reading on: the clock starts again from
  /// now, nothing is counted.
  void restart() => _since = _now();

  /// Estimated time to read [pagesLeft] more pages at the average pace;
  /// null before [minimumTurns] turns were counted. Zero when nothing is
  /// left.
  Duration? remaining(int pagesLeft) {
    if (_secondsPerPage.length < minimumTurns) return null;
    if (pagesLeft <= 0) return Duration.zero;
    var total = 0.0;
    for (final seconds in _secondsPerPage) {
      total += seconds;
    }
    final average = total / _secondsPerPage.length;
    return Duration(
      microseconds: (average * pagesLeft * Duration.microsecondsPerSecond)
          .round(),
    );
  }
}
