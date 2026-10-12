import 'dart:async';
import 'dart:collection';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:neostation/services/library_local_models.dart';

import 'library_reader_palette.dart';
import 'library_reflow_source.dart';
import 'library_reflow_view.dart';

/// Error of the futures of a pagination stopped by
/// [LibraryReflowPaginator.cancel], [LibraryReflowPaginator.invalidate],
/// a relayout by [LibraryReflowPaginator.update] or
/// [LibraryReflowPaginator.dispose]: the request is superseded, nothing
/// failed.
class LibraryReflowPaginationCancelled implements Exception {
  const LibraryReflowPaginationCancelled();

  @override
  String toString() => 'LibraryReflowPaginationCancelled';
}

/// What a [LibraryReflowPageSlice] shows.
enum LibraryReflowSliceKind { text, image, rule }

/// The part of one display unit shown on a page: whole lines of a text
/// unit, an image or a rule.
@immutable
class LibraryReflowPageSlice {
  const LibraryReflowPageSlice._({
    required this.kind,
    required this.unit,
    required this.unitIndex,
    required this.startOffset,
    required this.endOffset,
    required this.firstLine,
    required this.lineStarts,
    required this.rect,
    required this.imageFailed,
    Offset origin = Offset.zero,
    double? clipTop,
    double? clipBottom,
    Rect? background,
    Rect? bar,
    Offset? marker,
  }) : _origin = origin,
       _clipTop = clipTop,
       _clipBottom = clipBottom,
       _background = background,
       _bar = bar,
       _marker = marker;

  final LibraryReflowSliceKind kind;
  final LibraryReflowUnit unit;

  /// Index of [unit] in `libraryReflowUnits(chapter, blocks)`.
  final int unitIndex;

  /// Characters of [unit] on this page: `startOffset <= c < endOffset`
  /// (offsets in the unit, as in the scroll view's `offsetAt`).
  final int startOffset;
  final int endOffset;

  /// First line of the unit's layout on this page.
  final int firstLine;

  /// Offsets (in the unit) of the lines on this page, in order; empty for
  /// an image or a rule.
  final List<int> lineStarts;

  /// Lines (text), picture box (image) or stroke (rule), in page
  /// coordinates.
  final Rect rect;

  /// The image could not be read: a placeholder 48 px high is shown, like
  /// the scroll view.
  final bool imageFailed;

  // Painting (page coordinates): where the unit's whole TextPainter is
  // drawn, the edges where it is cut, and the decorations.
  final Offset _origin;
  final double? _clipTop;
  final double? _clipBottom;
  final Rect? _background;
  final Rect? _bar;
  final Offset? _marker;

  int get lineCount => lineStarts.length;

  /// Position of the first character on this page.
  LibraryReflowPosition get start =>
      LibraryReflowPosition(unit.chapter, unit.block, unit.start + startOffset);

  /// Position after the last character on this page.
  LibraryReflowPosition get end =>
      LibraryReflowPosition(unit.chapter, unit.block, unit.start + endOffset);
}

/// One page of a chapter.
///
/// [start] is the reading position of the page (the first character of its
/// first line); [end] is the [start] of the next page, or the end of the
/// chapter for the last one. The pages of a chapter cover its text once, in
/// order, as whole lines. Pages compare equal when they come from the same
/// layout (same paginator, same settings) at the same place.
@immutable
class LibraryReflowPageSpec {
  const LibraryReflowPageSpec._({
    required _PageLayout layout,
    required this.chapter,
    required this.indexInChapter,
    required this.start,
    required this.end,
    required this.isLastInChapter,
    required this.slices,
  }) : _layout = layout;

  final _PageLayout _layout;
  final int chapter;
  final int indexInChapter;
  final LibraryReflowPosition start;
  final LibraryReflowPosition end;
  final bool isLastInChapter;

  /// What the page shows, top to bottom.
  final List<LibraryReflowPageSlice> slices;

  /// Logical size of the page (of its picture at pixel ratio 1).
  Size get size => _layout.pageSize;

  /// An empty chapter has one empty page.
  bool get isEmpty => slices.isEmpty;

  @override
  bool operator ==(Object other) =>
      other is LibraryReflowPageSpec &&
      identical(other._layout, _layout) &&
      other.chapter == chapter &&
      other.indexInChapter == indexInChapter;

  @override
  int get hashCode =>
      Object.hash(identityHashCode(_layout), chapter, indexInChapter);

  @override
  String toString() =>
      'LibraryReflowPageSpec($chapter, $indexInChapter, $start..$end)';
}

/// Cost of the pagination of one chapter (the reader's trace
/// `library.reader.paginate:<chapter>:<ms>`, and the frame budget check).
@immutable
class LibraryReflowPaginationStats {
  const LibraryReflowPaginationStats({
    required this.chapter,
    required this.complete,
    required this.cancelled,
    required this.pages,
    required this.units,
    required this.turns,
    required this.work,
    required this.longestTurn,
    required this.elapsed,
  });

  final int chapter;
  final bool complete;
  final bool cancelled;

  /// Pages and display units laid out so far.
  final int pages;
  final int units;

  /// Event-loop turns the layout ran in, their total and longest time.
  final int turns;
  final Duration work;
  final Duration longestTurn;

  /// From the start to the end of the pagination (or now), waits included.
  final Duration elapsed;
}

/// Lays out the chapters of a [LibraryReflowSource] as pages of whole lines
/// and paints them (docs/library-books-3d-plan.md § 3.5).
///
/// Every display unit (`libraryReflowUnits`, at most about 2000 characters)
/// is laid out by a [TextPainter] with exactly the [TextStyle], alignment
/// and width that `LibraryReflowUnitView` gives it (headings by
/// [LibraryReflowStyle.headingScales]), so the same words fall on each line
/// as in the scroll view. A page holds whole lines only; a unit continues on
/// the next page at a line start; spacing above a unit is dropped at the top
/// of a page that a break opened (kept on the first page of a chapter); a
/// heading is not cut and does not end a page when what follows it does not
/// fit; an image taller than the room left starts a page and is at most
/// 0.85 of the page height (and never taller than the page's text area).
/// Each chapter starts a page (for TXT, every section of
/// `LibraryTextDocument.sectionSize` paragraphs).
///
/// Pagination is incremental: it yields to the event loop whenever
/// [frameBudget] is spent (checked after every unit; the first slice runs
/// in the call that starts it), so a long chapter never blocks a frame;
/// [TextPainter]s are disposed as soon as their lines are measured. Results
/// are memoized per chapter (the [maxChapters] used last). Pictures are
/// produced on demand by [paint].
///
/// ## Use in `LibraryBookReaderScreen` (pages layout)
///
/// `LibraryTextLayout.scroll` keeps the scroll path unchanged; in the pages
/// layout:
///
/// 1. Create one paginator per open book, for the page area given by the
///    reader's `LayoutBuilder` (one page; in a landscape spread, half of
///    it):
///
///    ```dart
///    final style = LibraryReflowStyle.of(settings, palette);
///    final safe = MediaQuery.paddingOf(context);
///    final paginator = LibraryReflowPaginator(
///      source: source,
///      style: style,
///      pageSize: pageSize,
///      // The scroll view's `horizontalPadding`: same words on each line.
///      padding: EdgeInsets.fromLTRB(safe.left + style.margin, topInset,
///          safe.right + style.margin, bottomInset),
///      // `LibraryReflowUnitView` lays out with `TextScaler.noScaling` (the
///      // font size setting is the user's text size): pass the same.
///      textScaler: TextScaler.noScaling,
///      textDirection: Directionality.of(context),
///      locale: Localizations.maybeLocaleOf(context),
///      images: imageCache, // the reader's LibraryReflowImageCache
///      devicePixelRatio: MediaQuery.devicePixelRatioOf(context),
///    );
///    ```
///
/// 2. Open or resume: `position = await source.resolveLocation(saved)` (the
///    reader's `_startPosition`), then `page = await locate(position)`.
///    [locate] completes as soon as the page holding the position is laid
///    out, before the rest of its chapter; [paginate] completes with the
///    whole chapter ("Page N of M": `page.indexInChapter + 1` of
///    [pageCountOf]). Call [prefetch] for the next chapter once the current
///    one is done (chapters are paginated lazily: the current one and the
///    next). Show a waiting state while [locate] runs.
///
/// 3. Turn pages with [next] / [previous] (they cross chapters; null at the
///    ends of the book). The reading position of a page is
///    [LibraryReflowPageSpec.start]: save `source.locationFor(page.start)`
///    (EPUB CFI, `txt:b:o`: unchanged formats) and
///    `source.fractionFor(page.start)`; a bookmark uses the same location.
///    Switching to the scroll layout anchors on `page.start` (`_setAnchor`),
///    and back with `locate(position)`.
///
/// 4. Draw: `await prepare(page)` (decodes the book images of the page),
///    then `paint(page, pixelRatio: dpr)`: a picture of the whole page,
///    background included, of `page.size * dpr` pixels. Draw it with
///    `canvas.drawPicture` (scaled by 1 / dpr), or make the curl texture
///    with `picture.toImage(...)`; dispose the picture. Paint the visible
///    page(s) and their neighbours only. Equal pages (`==`) paint the same
///    picture except for colours: a texture key is `(page, palette)`.
///    [textOf] is the page's text for VoiceOver (`Semantics(label:)`) and
///    [linkAt] the link under a tap (for the reader's `_onLink`).
///
/// 5. New typography, margins, safe area or rotation: [update] returns true
///    when the pages changed (running paginations are cancelled, memoized
///    pages dropped); then `locate(previousPage.start)` shows a page that
///    holds the same first words (the `_setAnchor` rule). A theme change
///    returns false: paint the same pages again in the new colours. Futures
///    of a superseded pagination complete with
///    [LibraryReflowPaginationCancelled]: ignore it.
///
/// 6. Right to left (`LibraryBookReaderScreen.rightToLeft`, EPUB
///    `page-progression-direction`): pages stay in reading order here (index
///    0 is the first page of a chapter, [next] is the following one). The
///    reader mirrors the presentation: "next" is the left tap zone, swipe
///    and curl corner, and a spread shows the next page on the left.
///    [textDirection] is the base direction of the paragraphs (the ambient
///    `Directionality`, as in the scroll view), not the page progression.
///
/// 7. [cancel] when leaving the pages layout, [dispose] with the reader;
///    [statsOf] gives the cost of a chapter for the trace
///    `library.reader.paginate:<chapter>:<ms>`.
class LibraryReflowPaginator {
  LibraryReflowPaginator({
    required this.source,
    required LibraryReflowStyle style,
    required Size pageSize,
    required EdgeInsets padding,
    required TextScaler textScaler,
    this.frameBudget = const Duration(milliseconds: 6),
    TextDirection textDirection = TextDirection.ltr,
    Locale? locale,
    LibraryReflowImageCache? images,
    double devicePixelRatio = 1.0,
    this.maxChapters = 4,
  }) : _style = style,
       _layout = _PageLayout(
         style: style,
         pageSize: pageSize,
         padding: padding,
         textScaler: textScaler,
         textDirection: textDirection,
         locale: locale,
       ),
       _images = images ?? LibraryReflowImageCache(source.resource),
       _ownsImages = images == null,
       _devicePixelRatio = devicePixelRatio,
       assert(maxChapters > 0);

  final LibraryReflowSource source;

  /// Longest synchronous layout work before yielding to the event loop.
  final Duration frameBudget;

  /// Chapters whose pages stay memoized (least recently used dropped).
  final int maxChapters;

  LibraryReflowStyle _style;
  _PageLayout _layout;
  final LibraryReflowImageCache _images;
  final bool _ownsImages;
  double _devicePixelRatio;
  bool _disposed = false;

  final LinkedHashMap<int, _ChapterJob> _jobs =
      LinkedHashMap<int, _ChapterJob>();
  final LinkedHashMap<int, _JobStats> _stats = LinkedHashMap<int, _JobStats>();

  /// Pixel sizes of the book images (null: unreadable), from their headers.
  final LinkedHashMap<String, Size?> _imageSizes =
      LinkedHashMap<String, Size?>();
  final Map<String, Future<Size?>> _probing = <String, Future<Size?>>{};

  /// Images decoded for [paint] by [prepare] (the visible pages').
  final LinkedHashMap<String, ui.Image> _decoded =
      LinkedHashMap<String, ui.Image>();
  final Map<String, Future<void>> _decoding = <String, Future<void>>{};
  final Set<String> _undecodable = <String>{};

  static const int _maxImageSizes = 1024;
  static const int _maxDecoded = 6;
  static const int _maxStats = 64;
  static const int _imageLookahead = 2;

  /// Current typography (its palette colours the pictures).
  LibraryReflowStyle get style => _style;
  Size get pageSize => _layout.pageSize;
  EdgeInsets get padding => _layout.padding;
  TextScaler get textScaler => _layout.textScaler;
  TextDirection get textDirection => _layout.textDirection;
  Locale? get locale => _layout.locale;
  double get devicePixelRatio => _devicePixelRatio;

  // ----------------------------------------------------------- queries --

  /// Pages of [chapter] (loaded by the source if needed), memoized; a call
  /// during the pagination joins it. Completes with the error of
  /// [LibraryReflowSource.loadChapter], or [LibraryReflowPaginationCancelled]
  /// when superseded.
  Future<List<LibraryReflowPageSpec>> paginate(int chapter) {
    final invalid = _check(chapter);
    if (invalid != null) {
      return Future<List<LibraryReflowPageSpec>>.error(invalid);
    }
    return _jobFor(chapter).done.future;
  }

  /// Starts the pagination of [chapter] (the next one while reading)
  /// without waiting for it; a failure is retried by the next request.
  void prefetch(int chapter) {
    if (_disposed || chapter < 0 || chapter >= source.chapterCount) return;
    _jobFor(chapter);
  }

  /// The page holding [position], as soon as it is laid out (the rest of the
  /// chapter is paginated on). A position beyond its chapter's text gives
  /// the last page.
  Future<LibraryReflowPageSpec> locate(LibraryReflowPosition position) {
    final invalid = _check(position.chapter);
    if (invalid != null) return Future<LibraryReflowPageSpec>.error(invalid);
    final job = _jobFor(position.chapter);
    final page = job.find(position);
    if (page != null) return Future<LibraryReflowPageSpec>.value(page);
    final waiter = _Waiter(position);
    waiter.completer.future.ignore();
    job.waiters.add(waiter);
    return waiter.completer.future;
  }

  /// Number of pages of [chapter] once its pagination is complete.
  int? pageCountOf(int chapter) {
    final job = _current(chapter);
    return job != null && job.finished ? job.pages.length : null;
  }

  /// The page holding [position] when it is already laid out; never starts
  /// a pagination ([locate] does).
  LibraryReflowPageSpec? pageFor(LibraryReflowPosition position) =>
      _current(position.chapter)?.find(position);

  /// Page [index] of [chapter] when it is already laid out.
  LibraryReflowPageSpec? pageAt(int chapter, int index) {
    final job = _current(chapter);
    if (job == null || index < 0 || index >= job.pages.length) return null;
    return job.pages[index];
  }

  /// The page after [page] (the first page of the next chapter after the
  /// last one); null at the end of the book. A [page] of an earlier layout
  /// is first located again (`locate(page.start)`).
  Future<LibraryReflowPageSpec?> next(LibraryReflowPageSpec page) async {
    final current = identical(page._layout, _layout)
        ? page
        : await locate(page.start);
    if (!current.isLastInChapter) return locate(current.end);
    final chapter = current.chapter + 1;
    if (chapter >= source.chapterCount) return null;
    return locate(LibraryReflowPosition(chapter, 0, 0));
  }

  /// The page before [page] (the last page of the previous chapter before
  /// the first one, which paginates that chapter whole); null at the start
  /// of the book.
  Future<LibraryReflowPageSpec?> previous(LibraryReflowPageSpec page) async {
    final current = identical(page._layout, _layout)
        ? page
        : await locate(page.start);
    if (current.indexInChapter > 0) {
      // The pages before it are laid out once it is.
      await locate(current.start);
      final before = pageAt(current.chapter, current.indexInChapter - 1);
      if (before == null) throw const LibraryReflowPaginationCancelled();
      return before;
    }
    final chapter = current.chapter - 1;
    if (chapter < 0) return null;
    return (await paginate(chapter)).last;
  }

  /// Cost of the latest pagination of [chapter] (running, complete or
  /// cancelled).
  LibraryReflowPaginationStats? statsOf(int chapter) =>
      _stats[chapter]?.snapshot(chapter);

  // ----------------------------------------------------------- changes --

  /// Applies new settings. Returns true when the pages change (typography,
  /// margins, page size or text scale): memoized pages are dropped and
  /// running paginations cancelled; show `locate(previous.start)`. A new
  /// palette only (theme) or [devicePixelRatio] keeps the pages and returns
  /// false: paint them again.
  bool update({
    LibraryReflowStyle? style,
    Size? pageSize,
    EdgeInsets? padding,
    TextScaler? textScaler,
    double? devicePixelRatio,
  }) {
    if (devicePixelRatio != null) _devicePixelRatio = devicePixelRatio;
    final next = _PageLayout(
      style: style ?? _style,
      pageSize: pageSize ?? _layout.pageSize,
      padding: padding ?? _layout.padding,
      textScaler: textScaler ?? _layout.textScaler,
      textDirection: _layout.textDirection,
      locale: _layout.locale,
    );
    if (style != null) _style = style;
    if (next.sameGeometry(_layout)) return false;
    _layout = next;
    _dropAll();
    return true;
  }

  /// Drops every memoized page and cancels the running paginations (their
  /// futures complete with [LibraryReflowPaginationCancelled]).
  void invalidate() {
    _layout = _layout.copy();
    _dropAll();
  }

  /// Stops the running paginations (their futures complete with
  /// [LibraryReflowPaginationCancelled]); complete chapters stay memoized.
  /// Completes once no pagination runs any more.
  Future<void> cancel() {
    final running = <_ChapterJob>[
      for (final job in _jobs.values)
        if (!job.finished) job,
    ];
    for (final job in running) {
      _jobs.remove(job.chapter);
      job.cancel();
    }
    return Future.wait(<Future<void>>[
      for (final job in running) job.exited.future,
    ]);
  }

  /// Cancels everything and releases the decoded images.
  void dispose() {
    if (_disposed) return;
    _disposed = true;
    _dropAll();
    for (final image in _decoded.values) {
      image.dispose();
    }
    _decoded.clear();
    _decoding.clear();
    if (_ownsImages) _images.clear();
  }

  void _dropAll() {
    final jobs = _jobs.values.toList(growable: false);
    _jobs.clear();
    for (final job in jobs) {
      if (!job.finished) job.cancel();
    }
  }

  // ------------------------------------------------------------- jobs --

  Object? _check(int chapter) {
    if (_disposed) return StateError('LibraryReflowPaginator disposed');
    if (chapter < 0 || chapter >= source.chapterCount) {
      return RangeError.range(chapter, 0, source.chapterCount - 1, 'chapter');
    }
    return null;
  }

  /// The job of [chapter] for the current layout, if any (made most
  /// recently used).
  _ChapterJob? _current(int chapter) {
    final job = _jobs.remove(chapter);
    if (job == null) return null;
    _jobs[chapter] = job;
    return job;
  }

  _ChapterJob _jobFor(int chapter) {
    final existing = _current(chapter);
    if (existing != null) return existing;
    final job = _ChapterJob(chapter, _layout);
    job.done.future.ignore();
    _jobs[chapter] = job;
    _stats.remove(chapter);
    _stats[chapter] = job.stats;
    while (_stats.length > _maxStats) {
      _stats.remove(_stats.keys.first);
    }
    _evict();
    unawaited(_run(job));
    return job;
  }

  /// Keeps the [maxChapters] complete chapters used last.
  void _evict() {
    while (_jobs.length > maxChapters) {
      int? oldest;
      for (final entry in _jobs.entries) {
        if (entry.value.finished) {
          oldest = entry.key;
          break;
        }
      }
      if (oldest == null) return;
      _jobs.remove(oldest);
    }
  }

  Future<void> _run(_ChapterJob job) async {
    final stats = job.stats..wall.start();
    final watch = Stopwatch()..start();
    void endTurn() {
      stats.endTurn(watch.elapsed);
      watch.reset();
    }

    try {
      final List<LibraryTextBlock> blocks;
      final loaded = source.loadedChapter(job.chapter);
      if (loaded != null) {
        blocks = loaded;
      } else {
        endTurn();
        blocks = await job.guard(source.loadChapter(job.chapter));
      }
      final layout = job.layout;
      final units = libraryReflowUnits(job.chapter, blocks);
      final images = <int>[
        for (var i = 0; i < units.length; i++)
          if (units[i].source.kind == LibraryTextBlockKind.image) i,
      ];
      var nextImage = 0;
      final builder = _ChapterBuilder(
        layout: layout,
        chapter: job.chapter,
        onPage: job.addPage,
      );
      for (var i = 0; i < units.length; i++) {
        if (job.cancelled) return;
        final unit = units[i];
        switch (unit.source.kind) {
          case LibraryTextBlockKind.image:
            while (nextImage < images.length && images[nextImage] <= i) {
              nextImage++;
            }
            // The next images' bytes are read while this one is placed.
            for (
              var k = nextImage;
              k < math.min(images.length, nextImage + _imageLookahead);
              k++
            ) {
              _probe(units[images[k]].source.imageHref);
            }
            final href = unit.source.imageHref;
            Size? size;
            if (href != null && href.isNotEmpty) {
              if (_imageSizes.containsKey(href)) {
                size = _imageSizes[href];
              } else {
                endTurn();
                size = await job.guard(_probe(href));
                if (job.cancelled) return;
              }
            }
            builder.addBlock(i, unit, _Measured.image(unit, size, layout));
          case LibraryTextBlockKind.rule:
            builder.addBlock(i, unit, _Measured.rule(layout));
          case LibraryTextBlockKind.paragraph ||
              LibraryTextBlockKind.heading ||
              LibraryTextBlockKind.quote ||
              LibraryTextBlockKind.listItem ||
              LibraryTextBlockKind.preformatted:
            builder.addText(i, unit, _Measured.text(unit, layout));
        }
        stats.units++;
        if (i < units.length - 1 && watch.elapsed >= frameBudget) {
          endTurn();
          await job.yieldTurn();
          if (job.cancelled) return;
        }
      }
      builder.finish(
        units.isEmpty
            ? LibraryReflowPosition(job.chapter, 0, 0)
            : LibraryReflowPosition(
                job.chapter,
                units.last.block,
                units.last.end,
              ),
      );
      endTurn();
      job.finish();
      _evict();
    } on _Stopped {
      // Cancelled: the futures already carry the cancellation.
    } catch (error, stackTrace) {
      if (!job.cancelled) {
        if (identical(_jobs[job.chapter], job)) _jobs.remove(job.chapter);
        job.fail(error, stackTrace);
      }
    } finally {
      watch.stop();
      stats.wall.stop();
      job.exited.complete();
    }
  }

  // ----------------------------------------------------------- images --

  /// Pixel size of [href] from its header (memoized; null when unreadable).
  Future<Size?> _probe(String? href) {
    if (href == null || href.isEmpty) return Future<Size?>.value();
    if (_imageSizes.containsKey(href)) {
      return Future<Size?>.value(_imageSizes[href]);
    }
    return _probing[href] ??= () async {
      Size? size;
      try {
        size = await _readSize(await _images.load(href));
      } catch (_) {
        size = null;
      }
      _probing.remove(href);
      _imageSizes.remove(href);
      _imageSizes[href] = size;
      while (_imageSizes.length > _maxImageSizes) {
        _imageSizes.remove(_imageSizes.keys.first);
      }
      return size;
    }();
  }

  static Future<Size?> _readSize(Uint8List bytes) async {
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    try {
      final descriptor = await ui.ImageDescriptor.encoded(buffer);
      try {
        if (descriptor.width <= 0 || descriptor.height <= 0) return null;
        return Size(descriptor.width.toDouble(), descriptor.height.toDouble());
      } finally {
        descriptor.dispose();
      }
    } finally {
      buffer.dispose();
    }
  }

  int _decodeWidth(double width) =>
      (width * _devicePixelRatio).ceil().clamp(64, 2048);

  String _decodedKey(LibraryReflowPageSlice slice) =>
      '${_decodeWidth(slice.rect.width)}|${slice.unit.source.imageHref}';

  /// Decodes the book images of [page] for [paint] (at the page width times
  /// [devicePixelRatio], never upscaled). Only the last few pages' images
  /// are kept; an image that cannot be decoded is painted as unavailable.
  Future<void> prepare(LibraryReflowPageSpec page) async {
    final work = <Future<void>>[];
    for (final slice in page.slices) {
      if (slice.kind != LibraryReflowSliceKind.image || slice.imageFailed) {
        continue;
      }
      final href = slice.unit.source.imageHref!;
      final key = _decodedKey(slice);
      final decoded = _decoded.remove(key);
      if (decoded != null) {
        _decoded[key] = decoded;
        continue;
      }
      if (_undecodable.contains(href)) continue;
      work.add(
        _decoding[key] ??= _decodeInto(
          key,
          href,
          _decodeWidth(slice.rect.width),
        ),
      );
    }
    await Future.wait(work);
  }

  /// Decodes [href] into [_decoded] (a failure marks it undecodable).
  Future<void> _decodeInto(String key, String href, int width) async {
    try {
      final image = await _decode(href, width);
      if (_disposed) {
        image.dispose();
        return;
      }
      _decoded.remove(key)?.dispose();
      _decoded[key] = image;
      while (_decoded.length > _maxDecoded) {
        _decoded.remove(_decoded.keys.first)!.dispose();
      }
    } catch (_) {
      _undecodable.add(href);
    } finally {
      _decoding.remove(key);
    }
  }

  Future<ui.Image> _decode(String href, int width) async {
    final bytes = await _images.load(href);
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    ui.ImageDescriptor? descriptor;
    ui.Codec? codec;
    try {
      descriptor = await ui.ImageDescriptor.encoded(buffer);
      codec = await descriptor.instantiateCodec(
        targetWidth: math.min(width, descriptor.width),
      );
      final frame = await codec.getNextFrame();
      return frame.image;
    } finally {
      codec?.dispose();
      descriptor?.dispose();
      buffer.dispose();
    }
  }

  // ---------------------------------------------------------- painting --

  /// Picture of [page] (background, text, decorations, images decoded by
  /// [prepare]; an image not decoded yet leaves its box empty, like the
  /// scroll view before decoding), in the current [style]'s palette, of
  /// `page.size * pixelRatio` pixels. One [TextPainter] per slice, disposed.
  ui.Picture paint(LibraryReflowPageSpec page, {double pixelRatio = 1.0}) {
    final layout = page._layout;
    final size = layout.pageSize;
    final palette = _style.palette;
    final style = layout.style.withPalette(palette);
    final recorder = ui.PictureRecorder();
    final canvas = Canvas(recorder, Offset.zero & (size * pixelRatio));
    if (pixelRatio != 1.0) canvas.scale(pixelRatio);
    canvas.drawRect(Offset.zero & size, Paint()..color = palette.background);
    for (final slice in page.slices) {
      switch (slice.kind) {
        case LibraryReflowSliceKind.text:
          _paintText(canvas, slice, layout, style);
        case LibraryReflowSliceKind.rule:
          canvas.drawRect(slice.rect, Paint()..color = palette.divider);
        case LibraryReflowSliceKind.image:
          _paintImage(canvas, slice, palette);
      }
    }
    return recorder.endRecording();
  }

  void _paintText(
    Canvas canvas,
    LibraryReflowPageSlice slice,
    _PageLayout layout,
    LibraryReflowStyle style,
  ) {
    final palette = style.palette;
    final background = slice._background;
    if (background != null) {
      canvas.drawRect(background, Paint()..color = palette.codeBackground);
    }
    final bar = slice._bar;
    if (bar != null) canvas.drawRect(bar, Paint()..color = palette.quoteBar);
    final box = _TextBox.of(slice.unit, style, layout.contentWidth)!;
    final marker = slice._marker;
    if (marker != null) {
      final painter = box.markerPainter(slice.unit, layout);
      painter.paint(canvas, marker);
      painter.dispose();
    }
    final painter = box.painter(slice.unit, layout);
    canvas.save();
    canvas.clipRect(
      Rect.fromLTRB(
        0,
        slice._clipTop ?? 0,
        layout.pageSize.width,
        slice._clipBottom ?? layout.pageSize.height,
      ),
    );
    painter.paint(canvas, slice._origin);
    canvas.restore();
    painter.dispose();
  }

  void _paintImage(
    Canvas canvas,
    LibraryReflowPageSlice slice,
    LibraryReaderPalette palette,
  ) {
    final href = slice.unit.source.imageHref;
    if (slice.imageFailed || (href != null && _undecodable.contains(href))) {
      const icon = Icons.image_not_supported_outlined;
      final painter = TextPainter(
        text: TextSpan(
          text: String.fromCharCode(icon.codePoint),
          style: TextStyle(
            inherit: false,
            color: palette.secondaryText,
            fontSize: 24,
            height: 1,
            fontFamily: icon.fontFamily,
            package: icon.fontPackage,
          ),
        ),
        textDirection: TextDirection.ltr,
      )..layout();
      painter.paint(
        canvas,
        slice.rect.center - Offset(painter.width / 2, painter.height / 2),
      );
      painter.dispose();
      return;
    }
    final image = _decoded[_decodedKey(slice)];
    if (image == null) return;
    paintImage(
      canvas: canvas,
      rect: slice.rect,
      image: image,
      fit: BoxFit.contain,
      filterQuality: FilterQuality.medium,
    );
  }

  /// Text of [page] for assistive technologies: the characters of its lines
  /// (one paragraph per unit) and the alternative text of its images.
  String textOf(LibraryReflowPageSpec page) {
    final parts = <String>[];
    for (final slice in page.slices) {
      switch (slice.kind) {
        case LibraryReflowSliceKind.text:
          final text = _unitText(
            slice.unit,
          ).substring(slice.startOffset, slice.endOffset).trim();
          if (text.isNotEmpty) parts.add(text);
        case LibraryReflowSliceKind.image:
          final alt = slice.unit.source.imageAlt?.trim();
          if (alt != null && alt.isNotEmpty) parts.add(alt);
        case LibraryReflowSliceKind.rule:
          break;
      }
    }
    return parts.join('\n');
  }

  /// Target of the link under [position] (page coordinates), if any.
  String? linkAt(LibraryReflowPageSpec page, Offset position) {
    for (final slice in page.slices) {
      if (slice.kind != LibraryReflowSliceKind.text ||
          !slice.rect.contains(position)) {
        continue;
      }
      final layout = page._layout;
      final box = _TextBox.of(slice.unit, layout.style, layout.contentWidth)!;
      final painter = box.painter(slice.unit, layout);
      try {
        final glyph = painter.getClosestGlyphForOffset(
          position - slice._origin,
        );
        if (glyph == null ||
            !glyph.graphemeClusterLayoutBounds.contains(
              position - slice._origin,
            )) {
          return null;
        }
        var offset = 0;
        final at = glyph.graphemeClusterCodeUnitRange.start;
        for (final span in slice.unit.spans) {
          final end = offset + span.text.length;
          if (at < end) {
            final href = span.href;
            return href == null || href.isEmpty ? null : href;
          }
          offset = end;
        }
        return null;
      } finally {
        painter.dispose();
      }
    }
    return null;
  }
}

String _unitText(LibraryReflowUnit unit) {
  if (unit.spans.length == 1) return unit.spans.first.text;
  final buffer = StringBuffer();
  for (final span in unit.spans) {
    buffer.write(span.text);
  }
  return buffer.toString();
}

/// The settings that decide where lines and pages break; a new instance per
/// layout generation (pages hold theirs and compare it by identity).
class _PageLayout {
  _PageLayout({
    required this.style,
    required this.pageSize,
    required this.padding,
    required this.textScaler,
    required this.textDirection,
    required this.locale,
  });

  final LibraryReflowStyle style;
  final Size pageSize;
  final EdgeInsets padding;
  final TextScaler textScaler;
  final TextDirection textDirection;
  final Locale? locale;

  /// Text area of a page.
  late final Rect content = Rect.fromLTWH(
    padding.left,
    padding.top,
    math.max(1.0, pageSize.width - padding.horizontal),
    math.max(1.0, pageSize.height - padding.vertical),
  );

  double get contentWidth => content.width;

  double get contentHeight => content.height;

  /// Tallest image box: 0.85 of the page height (the scroll view's cap),
  /// and its spacing must fit in the text area too.
  double get maxImageHeight => math.max(
    1.0,
    math.min(pageSize.height * 0.85, contentHeight - style.fontSize),
  );

  _PageLayout copy() => _PageLayout(
    style: style,
    pageSize: pageSize,
    padding: padding,
    textScaler: textScaler,
    textDirection: textDirection,
    locale: locale,
  );

  bool sameGeometry(_PageLayout other) =>
      style.fontSize == other.style.fontSize &&
      style.lineHeight == other.style.lineHeight &&
      style.fontFamily == other.style.fontFamily &&
      style.justify == other.style.justify &&
      style.margin == other.style.margin &&
      pageSize == other.pageSize &&
      padding == other.padding &&
      textScaler == other.textScaler &&
      textDirection == other.textDirection &&
      locale == other.locale;
}

extension on LibraryReflowStyle {
  LibraryReflowStyle withPalette(LibraryReaderPalette palette) =>
      identical(palette, this.palette)
      ? this
      : LibraryReflowStyle(
          palette: palette,
          fontSize: fontSize,
          lineHeight: lineHeight,
          fontFamily: fontFamily,
          justify: justify,
          margin: margin,
        );
}

/// Style and box of a text unit, as `LibraryReflowUnitView.build` makes
/// them (keep both in step): offsets are relative to the text area.
class _TextBox {
  const _TextBox({
    required this.palette,
    required this.style,
    required this.align,
    required this.decorationLeft,
    required this.left,
    required this.width,
    required this.spaceBefore,
    required this.spaceAfter,
    this.insetTop = 0,
    this.insetBottom = 0,
    this.markerWidth = 0,
  });

  /// Colours of [style] and of the links.
  final LibraryReaderPalette palette;
  final TextStyle style;
  final TextAlign align;

  /// Left of the quote bar, list marker or code background.
  final double decorationLeft;

  /// Left and width of the text.
  final double left;
  final double width;
  final double spaceBefore;
  final double spaceAfter;

  /// Padding inside the code background, above the first line and below
  /// the last one.
  final double insetTop;
  final double insetBottom;
  final double markerWidth;

  /// Null for images and rules.
  static _TextBox? of(
    LibraryReflowUnit unit,
    LibraryReflowStyle style,
    double contentWidth,
  ) {
    final base = style.base;
    final block = unit.source;
    final em = style.fontSize;
    final paragraphAlign = block.alignCenter
        ? TextAlign.center
        : (style.justify ? TextAlign.justify : TextAlign.start);
    final bottom = unit.isLastPiece ? em * 0.6 : 0.0;
    final indent = em * 1.2 * block.indent.clamp(0, 6);
    double widthFrom(double left, [double right = 0]) =>
        math.max(1.0, contentWidth - left - right);
    switch (block.kind) {
      case LibraryTextBlockKind.heading:
        final level = block.headingLevel.clamp(1, 6);
        return _TextBox(
          palette: style.palette,
          style: base.copyWith(
            fontSize: em * LibraryReflowStyle.headingScales[level - 1],
            fontWeight: FontWeight.w700,
            height: LibraryReflowStyle.headingLineHeight,
          ),
          align: block.alignCenter ? TextAlign.center : TextAlign.start,
          decorationLeft: 0,
          left: 0,
          width: widthFrom(0),
          spaceBefore: unit.isFirstPiece ? em * 1.1 : 0,
          spaceAfter: unit.isLastPiece ? em * 0.5 : 0,
        );
      case LibraryTextBlockKind.quote:
        // Left border of 3 px, then em * 0.8 of padding.
        final left = indent + 3 + em * 0.8;
        return _TextBox(
          palette: style.palette,
          style: base.copyWith(
            color: style.palette.text.withValues(alpha: 0.9),
          ),
          align: paragraphAlign,
          decorationLeft: indent,
          left: left,
          width: widthFrom(left),
          spaceBefore: 0,
          spaceAfter: bottom,
        );
      case LibraryTextBlockKind.listItem:
        final left = indent + em * 1.6;
        return _TextBox(
          palette: style.palette,
          style: base,
          align: TextAlign.start,
          decorationLeft: indent,
          left: left,
          width: widthFrom(left),
          spaceBefore: 0,
          spaceAfter: unit.isLastPiece ? em * 0.3 : 0,
          markerWidth: em * 1.6,
        );
      case LibraryTextBlockKind.preformatted:
        return _TextBox(
          palette: style.palette,
          style: base.copyWith(
            fontFamily: LibraryReaderFonts.monospace,
            fontFamilyFallback: LibraryReaderFonts.monospaceFallback,
            fontSize: em * 0.85,
            height: 1.35,
          ),
          align: TextAlign.start,
          decorationLeft: 0,
          left: em * 0.5,
          width: widthFrom(em * 0.5, em * 0.5),
          spaceBefore: 0,
          spaceAfter: bottom,
          insetTop: 4,
          insetBottom: 4,
        );
      case LibraryTextBlockKind.paragraph:
        return _TextBox(
          palette: style.palette,
          style: base,
          align: paragraphAlign,
          decorationLeft: indent,
          left: indent,
          width: widthFrom(indent),
          spaceBefore: 0,
          spaceAfter: bottom,
        );
      case LibraryTextBlockKind.image || LibraryTextBlockKind.rule:
        return null;
    }
  }

  /// The unit laid out like its `RichText` (tight width).
  TextPainter painter(LibraryReflowUnit unit, _PageLayout layout) =>
      TextPainter(
        text: TextSpan(
          style: style,
          children: <InlineSpan>[
            for (final span in unit.spans) _span(span, style, palette),
          ],
        ),
        textAlign: align,
        textDirection: layout.textDirection,
        textScaler: layout.textScaler,
        locale: layout.locale,
      )..layout(minWidth: width, maxWidth: width);

  /// The marker of a list item ("•", "3."), laid out like its `Text` in
  /// the scroll view (a box [markerWidth] wide, where a long number wraps).
  TextPainter markerPainter(LibraryReflowUnit unit, _PageLayout layout) {
    final ordinal = unit.source.ordinal;
    return TextPainter(
      text: TextSpan(text: ordinal != null ? '$ordinal.' : '•', style: style),
      textDirection: layout.textDirection,
      textScaler: layout.textScaler,
      locale: layout.locale,
    )..layout(minWidth: markerWidth, maxWidth: markerWidth);
  }

  /// `LibraryReflowUnitViewState._span` without its tap recognizer.
  static InlineSpan _span(
    LibraryTextSpan span,
    TextStyle style,
    LibraryReaderPalette palette,
  ) {
    var effective = style;
    if (span.bold) effective = effective.copyWith(fontWeight: FontWeight.w700);
    if (span.italic) {
      effective = effective.copyWith(fontStyle: FontStyle.italic);
    }
    if (span.monospace) {
      effective = effective.copyWith(
        fontFamily: LibraryReaderFonts.monospace,
        fontFamilyFallback: LibraryReaderFonts.monospaceFallback,
        fontSize: (effective.fontSize ?? 16) * 0.9,
      );
    }
    if (span.superscript || span.subscript) {
      effective = effective.copyWith(
        fontFeatures: <FontFeature>[
          span.superscript
              ? const FontFeature.superscripts()
              : const FontFeature.subscripts(),
        ],
      );
    }
    final href = span.href;
    if (href != null && href.isNotEmpty) {
      final link = palette.link;
      effective = effective.copyWith(
        color: link,
        decoration: TextDecoration.underline,
        decorationColor: link,
      );
    } else if (span.underline) {
      effective = effective.copyWith(decoration: TextDecoration.underline);
    }
    return TextSpan(text: span.text, style: effective);
  }
}

/// Geometry of one unit at the page width: lines of a text unit, box of an
/// image or rule.
class _Measured {
  _Measured._({
    required this.kind,
    required this.spaceBefore,
    required this.spaceAfter,
    this.box,
    this.lineTops = const <double>[0, 0],
    this.lineStarts = const <int>[0],
    this.height = 0,
    this.imageFailed = false,
    this.minHeight = 0,
  });

  /// Lays out a text unit and measures its lines; the painter is disposed.
  factory _Measured.text(LibraryReflowUnit unit, _PageLayout layout) {
    final box = _TextBox.of(unit, layout.style, layout.contentWidth)!;
    final painter = box.painter(unit, layout);
    try {
      final metrics = painter.computeLineMetrics();
      final length = unit.length;
      final tops = <double>[0];
      final starts = <int>[0];
      for (var i = 1; i < metrics.length; i++) {
        final line = metrics[i];
        final start = _lineStart(painter, line, starts.last, length);
        // A line that does not start after the previous one (never seen)
        // stays with it: pages break between lines that start apart only.
        if (start <= starts.last) continue;
        tops.add(math.max(tops.last, line.baseline - line.ascent));
        starts.add(start);
      }
      tops.add(math.max(tops.last, painter.height));
      // A list item's row is as tall as its marker when that is taller.
      var minHeight = 0.0;
      if (unit.source.kind == LibraryTextBlockKind.listItem &&
          unit.isFirstPiece) {
        final marker = box.markerPainter(unit, layout);
        minHeight = marker.height;
        marker.dispose();
      }
      return _Measured._(
        kind: LibraryReflowSliceKind.text,
        box: box,
        spaceBefore: box.spaceBefore,
        spaceAfter: box.spaceAfter,
        lineTops: tops,
        lineStarts: starts,
        minHeight: minHeight,
      );
    } finally {
      painter.dispose();
    }
  }

  factory _Measured.image(
    LibraryReflowUnit unit,
    Size? size,
    _PageLayout layout,
  ) {
    final em = layout.style.fontSize;
    final failed = size == null || size.width <= 0;
    return _Measured._(
      kind: LibraryReflowSliceKind.image,
      spaceBefore: em * 0.5,
      spaceAfter: em * 0.5,
      height: failed
          ? 48
          : math.min(
              layout.contentWidth * size.height / size.width,
              layout.maxImageHeight,
            ),
      imageFailed: failed,
    );
  }

  factory _Measured.rule(_PageLayout layout) {
    final em = layout.style.fontSize;
    return _Measured._(
      kind: LibraryReflowSliceKind.rule,
      spaceBefore: em * 0.8,
      spaceAfter: em * 0.8,
      height: 1,
    );
  }

  final LibraryReflowSliceKind kind;
  final _TextBox? box;
  final double spaceBefore;
  final double spaceAfter;

  /// Top of each line from the painter's top, then its height (text).
  final List<double> lineTops;

  /// Offset (in the unit) of each line, strictly increasing from 0 (text).
  final List<int> lineStarts;

  /// Box height (image, rule).
  final double height;
  final bool imageFailed;

  /// Least height of the slice holding the first line (list marker).
  final double minHeight;

  /// Height of lines [first] to [end] on a page.
  double span(int first, int end) =>
      math.max(lineTops[end] - lineTops[first], first == 0 ? minHeight : 0.0);

  int get lineCount => lineStarts.length;

  double get insetTop => box?.insetTop ?? 0;

  double get insetBottom => box?.insetBottom ?? 0;

  /// First character of [line] in logical order (also for right-to-left
  /// and mixed lines, whose visual ends are not their first character).
  ///
  /// A position in the middle of the line is on it; `getLineBoundary` of a
  /// position shared by two lines answers the next line for a downstream
  /// affinity and the previous one for an upstream affinity (and the
  /// following line for an empty one). The line's start is the earliest
  /// answer after [previous] (the start of the line above) and not after
  /// the position; without one, the position itself (an empty last line).
  static int _lineStart(
    TextPainter painter,
    ui.LineMetrics line,
    int previous,
    int length,
  ) {
    final probe = painter
        .getPositionForOffset(
          Offset(
            line.left + line.width / 2,
            line.baseline - line.ascent / 2 + line.descent / 2,
          ),
        )
        .offset
        .clamp(0, length);
    var start = -1;
    for (final affinity in TextAffinity.values) {
      final candidate = painter
          .getLineBoundary(TextPosition(offset: probe, affinity: affinity))
          .start;
      if (candidate > previous &&
          candidate <= probe &&
          (start < 0 || candidate < start)) {
        start = candidate;
      }
    }
    return start >= 0 ? start : probe;
  }
}

/// A slice being placed on the page under construction.
class _Placed {
  _Placed(
    this.unitIndex,
    this.unit,
    this.measured,
    this.firstLine,
    this.endLine,
    this.top,
  );

  final int unitIndex;
  final LibraryReflowUnit unit;
  final _Measured measured;
  final int firstLine;
  final int endLine;

  /// Top of the slice's box in the text area (below its spacing).
  final double top;

  bool get isWholeHeading =>
      measured.kind == LibraryReflowSliceKind.text &&
      unit.source.kind == LibraryTextBlockKind.heading &&
      firstLine == 0 &&
      endLine == measured.lineCount;

  LibraryReflowPosition get start => LibraryReflowPosition(
    unit.chapter,
    unit.block,
    unit.start +
        (measured.kind == LibraryReflowSliceKind.text
            ? measured.lineStarts[firstLine]
            : 0),
  );

  LibraryReflowPageSlice toSlice(_PageLayout layout) {
    final content = layout.content;
    final left = content.left;
    final y = content.top + top;
    switch (measured.kind) {
      case LibraryReflowSliceKind.image:
        return LibraryReflowPageSlice._(
          kind: LibraryReflowSliceKind.image,
          unit: unit,
          unitIndex: unitIndex,
          startOffset: 0,
          endOffset: unit.length,
          firstLine: 0,
          lineStarts: const <int>[],
          rect: Rect.fromLTWH(left, y, content.width, measured.height),
          imageFailed: measured.imageFailed,
        );
      case LibraryReflowSliceKind.rule:
        final width = math.min(96.0, content.width);
        return LibraryReflowPageSlice._(
          kind: LibraryReflowSliceKind.rule,
          unit: unit,
          unitIndex: unitIndex,
          startOffset: 0,
          endOffset: unit.length,
          firstLine: 0,
          lineStarts: const <int>[],
          rect: Rect.fromLTWH(
            left + (content.width - width) / 2,
            y,
            width,
            measured.height,
          ),
          imageFailed: false,
        );
      case LibraryReflowSliceKind.text:
        final box = measured.box!;
        final tops = measured.lineTops;
        final lines = measured.lineCount;
        final textTop = y + (firstLine == 0 ? box.insetTop : 0);
        final height = tops[endLine] - tops[firstLine];
        final textBottom = textTop + height;
        final kind = unit.source.kind;
        return LibraryReflowPageSlice._(
          kind: LibraryReflowSliceKind.text,
          unit: unit,
          unitIndex: unitIndex,
          startOffset: measured.lineStarts[firstLine],
          endOffset: endLine == lines
              ? unit.length
              : measured.lineStarts[endLine],
          firstLine: firstLine,
          lineStarts: List<int>.unmodifiable(
            measured.lineStarts.sublist(firstLine, endLine),
          ),
          rect: Rect.fromLTWH(left + box.left, textTop, box.width, height),
          imageFailed: false,
          origin: Offset(left + box.left, textTop - tops[firstLine]),
          clipTop: firstLine > 0 ? textTop : null,
          clipBottom: endLine < lines ? textBottom : null,
          background: kind == LibraryTextBlockKind.preformatted
              ? Rect.fromLTRB(
                  left,
                  y,
                  left + content.width,
                  textBottom + (endLine == lines ? box.insetBottom : 0),
                )
              : null,
          bar: kind == LibraryTextBlockKind.quote
              ? Rect.fromLTWH(left + box.decorationLeft, textTop, 3, height)
              : null,
          marker:
              kind == LibraryTextBlockKind.listItem &&
                  firstLine == 0 &&
                  unit.isFirstPiece
              ? Offset(left + box.decorationLeft, textTop)
              : null,
        );
    }
  }
}

/// Fills the pages of one chapter, unit after unit.
class _ChapterBuilder {
  _ChapterBuilder({
    required this.layout,
    required this.chapter,
    required this.onPage,
  }) : _pageStart = LibraryReflowPosition(chapter, 0, 0);

  final _PageLayout layout;
  final int chapter;
  final void Function(LibraryReflowPageSpec page) onPage;

  static const double _epsilon = 0.01;

  final List<_Placed> _current = <_Placed>[];
  int _pages = 0;
  double _y = 0;
  LibraryReflowPosition _pageStart;

  double get _height => layout.contentHeight;

  bool get _empty => _current.isEmpty;

  /// Spacing above an item: dropped at the top of a page opened by a break
  /// (kept on the first page of the chapter).
  double _spaceAbove(double space) => _empty && _pages > 0 ? 0 : space;

  void addText(int index, LibraryReflowUnit unit, _Measured measured) {
    final lines = measured.lineCount;
    final heading = unit.source.kind == LibraryTextBlockKind.heading;
    var first = 0;
    while (first < lines) {
      var space = first == 0 ? _spaceAbove(measured.spaceBefore) : 0.0;
      final inset = first == 0 ? measured.insetTop : 0.0;
      var end = _fit(measured, first, _height - _y - space - inset);
      // A heading is not cut, unless it is taller than a page.
      if (heading && end < lines && !_empty) end = first;
      if (end == first) {
        if (!_empty) {
          _break(_lineStart(unit, measured, first));
          continue;
        }
        // Nothing fits on an empty page: less spacing, then at least one
        // line (cut by the page edge when it is taller than the page).
        final line = measured.span(first, first + 1);
        space = math.max(0.0, math.min(space, _height - inset - line));
        end = math.max(
          first + 1,
          _fit(measured, first, _height - space - inset),
        );
      }
      _current.add(_Placed(index, unit, measured, first, end, _y + space));
      _y += space + inset + measured.span(first, end);
      if (end == lines) {
        _y += measured.insetBottom + measured.spaceAfter;
      } else {
        _break(_lineStart(unit, measured, end));
      }
      first = end;
    }
  }

  void addBlock(int index, LibraryReflowUnit unit, _Measured measured) {
    while (true) {
      var space = _spaceAbove(measured.spaceBefore);
      final fits = _y + space + measured.height <= _height + _epsilon;
      if (fits || _empty) {
        if (!fits) {
          space = math.max(0.0, math.min(space, _height - measured.height));
        }
        _current.add(_Placed(index, unit, measured, 0, 1, _y + space));
        _y += space + measured.height + measured.spaceAfter;
        return;
      }
      _break(LibraryReflowPosition(chapter, unit.block, unit.start));
    }
  }

  /// Closes the last page.
  void finish(LibraryReflowPosition chapterEnd) => _close(chapterEnd, true);

  LibraryReflowPosition _lineStart(
    LibraryReflowUnit unit,
    _Measured measured,
    int line,
  ) => LibraryReflowPosition(
    chapter,
    unit.block,
    unit.start + measured.lineStarts[line],
  );

  /// Lines from [first] that fit in [room].
  int _fit(_Measured measured, int first, double room) {
    var end = first;
    while (end < measured.lineCount &&
        measured.span(first, end + 1) <= room + _epsilon) {
      end++;
    }
    return end;
  }

  /// Ends the page before [next]. Whole headings that end it go to the next
  /// page with what follows them, unless they are all the page holds.
  void _break(LibraryReflowPosition next) {
    var keep = _current.length;
    while (keep > 0 && _current[keep - 1].isWholeHeading) {
      keep--;
    }
    var moved = const <_Placed>[];
    if (keep > 0 && keep < _current.length) {
      moved = _current.sublist(keep);
      _current.removeRange(keep, _current.length);
      next = moved.first.start;
    }
    _close(next, false);
    for (final placed in moved) {
      addText(placed.unitIndex, placed.unit, placed.measured);
    }
  }

  void _close(LibraryReflowPosition end, bool last) {
    final page = LibraryReflowPageSpec._(
      layout: layout,
      chapter: chapter,
      indexInChapter: _pages,
      start: _pageStart,
      end: end,
      isLastInChapter: last,
      slices: List<LibraryReflowPageSlice>.unmodifiable(
        <LibraryReflowPageSlice>[
          for (final placed in _current) placed.toSlice(layout),
        ],
      ),
    );
    _pages++;
    _current.clear();
    _y = 0;
    _pageStart = end;
    onPage(page);
  }
}

/// Raised inside a cancelled job to unwind it.
class _Stopped implements Exception {
  const _Stopped();
}

class _Waiter {
  _Waiter(this.position);

  final LibraryReflowPosition position;
  final Completer<LibraryReflowPageSpec> completer =
      Completer<LibraryReflowPageSpec>();
}

class _JobStats {
  final Stopwatch wall = Stopwatch();
  bool complete = false;
  bool cancelled = false;
  int pages = 0;
  int units = 0;
  int turns = 0;
  Duration work = Duration.zero;
  Duration longest = Duration.zero;

  void endTurn(Duration spent) {
    turns++;
    work += spent;
    if (spent > longest) longest = spent;
  }

  LibraryReflowPaginationStats snapshot(int chapter) =>
      LibraryReflowPaginationStats(
        chapter: chapter,
        complete: complete,
        cancelled: cancelled,
        pages: pages,
        units: units,
        turns: turns,
        work: work,
        longestTurn: longest,
        elapsed: wall.elapsed,
      );
}

/// The pagination of one chapter for one layout.
class _ChapterJob {
  _ChapterJob(this.chapter, this.layout);

  final int chapter;
  final _PageLayout layout;
  final List<LibraryReflowPageSpec> pages = <LibraryReflowPageSpec>[];
  final List<_Waiter> waiters = <_Waiter>[];
  final Completer<List<LibraryReflowPageSpec>> done =
      Completer<List<LibraryReflowPageSpec>>();
  final Completer<void> exited = Completer<void>();
  final _JobStats stats = _JobStats();
  bool finished = false;
  bool cancelled = false;
  void Function()? _onStop;

  /// [future]'s result, unless the job is cancelled first (then [_Stopped]
  /// at once; a later error of [future] is ignored). The loop waits for one
  /// future at a time: only the pending one is held.
  Future<T> guard<T>(Future<T> future) {
    if (cancelled) return Future<T>.error(const _Stopped());
    final completer = Completer<T>();
    future.then(
      (value) {
        if (!completer.isCompleted) completer.complete(value);
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!completer.isCompleted) completer.completeError(error, stackTrace);
      },
    );
    _onStop = () {
      if (!completer.isCompleted) completer.completeError(const _Stopped());
    };
    return completer.future;
  }

  /// One event-loop turn between two layout slices. The timer is cancelled
  /// with the job, so a cancelled, superseded or disposed pagination leaves
  /// no timer behind.
  Future<void> yieldTurn() {
    if (cancelled) return Future<void>.error(const _Stopped());
    final completer = Completer<void>();
    final timer = Timer(Duration.zero, () {
      if (!completer.isCompleted) completer.complete();
    });
    _onStop = () {
      timer.cancel();
      if (!completer.isCompleted) completer.completeError(const _Stopped());
    };
    return completer.future;
  }

  /// The laid-out page holding [position], if any.
  LibraryReflowPageSpec? find(LibraryReflowPosition position) {
    if (pages.isEmpty) return null;
    var low = 0;
    var high = pages.length - 1;
    if (_compare(position, pages.first.start) < 0) return pages.first;
    while (low < high) {
      final middle = (low + high + 1) >> 1;
      if (_compare(pages[middle].start, position) <= 0) {
        low = middle;
      } else {
        high = middle - 1;
      }
    }
    final page = pages[low];
    return page.isLastInChapter || _compare(position, page.end) < 0
        ? page
        : null;
  }

  void addPage(LibraryReflowPageSpec page) {
    pages.add(page);
    stats.pages = pages.length;
    waiters.removeWhere((waiter) {
      if (!page.isLastInChapter && _compare(waiter.position, page.end) >= 0) {
        return false;
      }
      waiter.completer.complete(page);
      return true;
    });
  }

  void finish() {
    finished = true;
    stats.complete = true;
    done.complete(List<LibraryReflowPageSpec>.unmodifiable(pages));
    for (final waiter in waiters) {
      waiter.completer.complete(pages.last);
    }
    waiters.clear();
  }

  void fail(Object error, StackTrace stackTrace) {
    finished = true;
    done.completeError(error, stackTrace);
    for (final waiter in waiters) {
      waiter.completer.completeError(error, stackTrace);
    }
    waiters.clear();
  }

  void cancel() {
    if (cancelled || finished) return;
    cancelled = true;
    final stop = _onStop;
    _onStop = null;
    stop?.call();
    stats.cancelled = true;
    done.completeError(const LibraryReflowPaginationCancelled());
    for (final waiter in waiters) {
      waiter.completer.completeError(const LibraryReflowPaginationCancelled());
    }
    waiters.clear();
  }

  static int _compare(LibraryReflowPosition a, LibraryReflowPosition b) {
    if (a.chapter != b.chapter) return a.chapter - b.chapter;
    if (a.block != b.block) return a.block - b.block;
    return a.offset - b.offset;
  }
}
