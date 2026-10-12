/// Pages layout of the EPUB/TXT reader (Build 447,
/// docs/library-books-3d-plan.md § 3.5): which paginated pages are shown
/// together, and how one page is drawn.
///
/// * [LibraryBookSpread]: the pages shown at once, one page or the two
///   halves of a landscape spread.
/// * [LibraryBookSpreadRule]: how the pages of a [LibraryReflowPaginator]
///   pair into spreads ([LibraryPageSpreads] rules: the first page of a
///   chapter alone, right to left the next page on the left) and the
///   spreads around a spread, in reading order.
/// * [LibraryBookSpreadView], [LibraryBookPageCanvas]: a spread drawn like
///   the page curl draws it ([LibraryPageSpreadLayout]), each page from its
///   picture ([LibraryReflowPaginator.paint]), announced by VoiceOver as
///   "Page N of M" or "Pages N and N+1 of M" (in its chapter) followed by
///   the text of its pages ([LibraryReflowPaginator.textOf]; an image that
///   cannot be shown reads "Image unavailable").
/// * [LibraryBookPagePlaceholder]: a neighbour still being laid out, or one
///   whose chapter could not be read.
library;

import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/semantics.dart' show OrdinalSortKey;

import 'package:neostation/l10n/library_reader_locale.dart';
import 'package:neostation/services/library_reading_store.dart'
    show LibraryDoublePageMode;

import 'library_page_curl.dart';
import 'library_page_spreads.dart';
import 'library_reader_errors.dart';
import 'library_reader_palette.dart';
import 'library_reflow_paginator.dart';

/// The pages shown at once: one page, or the two halves of a spread (a
/// pair, or a page alone on its side of the book).
@immutable
class LibraryBookSpread {
  /// One page using the whole page area.
  LibraryBookSpread.single(LibraryReflowPageSpec page)
    : pages = List<LibraryReflowPageSpec>.unmodifiable(<LibraryReflowPageSpec>[
        page,
      ]),
      left = null,
      right = null,
      doublePage = false;

  /// Two halves; [pages] in reading order (one or two pages of one
  /// chapter), each on its [left] or [right] half (null: an empty half).
  LibraryBookSpread.halves({
    required List<LibraryReflowPageSpec> pages,
    this.left,
    this.right,
  }) : assert(pages.isNotEmpty && pages.length <= 2),
       pages = List<LibraryReflowPageSpec>.unmodifiable(pages),
       doublePage = true;

  /// Pages shown, in reading order.
  final List<LibraryReflowPageSpec> pages;

  /// Page on the left half of a two-page layout.
  final LibraryReflowPageSpec? left;

  /// Page on the right half of a two-page layout.
  final LibraryReflowPageSpec? right;

  /// Laid out as two halves.
  final bool doublePage;

  LibraryReflowPageSpec get first => pages.first;

  LibraryReflowPageSpec get last => pages.last;

  int get chapter => first.chapter;

  bool get isPair => pages.length == 2;

  /// The face the page curl draws for this spread, its pages named by
  /// [idOf].
  LibraryPageCurlFace faceWith(int Function(LibraryReflowPageSpec page) idOf) {
    if (!doublePage) return LibraryPageCurlFace.single(idOf(first));
    final left = this.left;
    final right = this.right;
    return LibraryPageCurlFace.spread(
      left: left == null ? null : idOf(left),
      right: right == null ? null : idOf(right),
    );
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryBookSpread &&
      other.doublePage == doublePage &&
      other.left == left &&
      other.right == right &&
      listEquals(other.pages, pages);

  @override
  int get hashCode =>
      Object.hash(doublePage, left, right, Object.hashAll(pages));

  @override
  String toString() => doublePage
      ? 'LibraryBookSpread(left: $left, right: $right)'
      : 'LibraryBookSpread($first)';
}

/// How the pages of a paginator pair into [LibraryBookSpread]s, and the
/// spreads around one.
///
/// Without [doublePage] every page is alone. With it, the pages of each
/// chapter pair as [LibraryPageSpreads] lays them out: with
/// [firstPageAlone] the first page is alone on its book side (right in
/// left-to-right reading), then 2-3, 4-5...; an odd last page is alone on
/// the other side. Every EPUB chapter starts that way (a printed chapter
/// opening); the sections of a plain text flow as one text, so only the
/// first page of the book is alone ([firstPageAloneInEveryChapter] false).
/// Right to left, the next page is on the left.
@immutable
class LibraryBookSpreadRule {
  const LibraryBookSpreadRule({
    required this.doublePage,
    required this.firstPageAlone,
    required this.rightToLeft,
    required this.firstPageAloneInEveryChapter,
  });

  final bool doublePage;
  final bool firstPageAlone;
  final bool rightToLeft;
  final bool firstPageAloneInEveryChapter;

  /// Whether the first page of [chapter] is shown alone.
  bool aloneAt(int chapter) =>
      doublePage &&
      firstPageAlone &&
      (firstPageAloneInEveryChapter || chapter == 0);

  /// Whether a spread comes before [spread] (not the first page of the
  /// book).
  bool hasBefore(LibraryBookSpread spread) =>
      spread.first.chapter > 0 || spread.first.indexInChapter > 0;

  /// Whether a spread comes after [spread] in a book of [chapterCount]
  /// chapters.
  bool hasAfter(LibraryBookSpread spread, int chapterCount) =>
      !spread.last.isLastInChapter || spread.last.chapter < chapterCount - 1;

  /// Indices in its chapter of the pair holding page [index]: the spread
  /// index, its first (leading, -1 for a lone first page) and second
  /// (trailing) page.
  (int, int, int) _pairOf(int chapter, int index) {
    final shift = aloneAt(chapter) ? 1 : 0;
    final spread = (index + shift) ~/ 2;
    final leading = 2 * spread - shift;
    return (spread, leading, leading + 1);
  }

  LibraryBookSpread _build(
    int chapter,
    (int, int, int) pair,
    LibraryReflowPageSpec? lead,
    LibraryReflowPageSpec? trail,
  ) {
    final (spread, leading, trailing) = pair;
    final layout = LibraryPageSpreads(
      pageCount: trail != null ? trailing + 1 : leading + 1,
      doublePage: LibraryDoublePageMode.always,
      firstPageAlone: aloneAt(chapter),
      rightToLeft: rightToLeft,
    ).spreadAt(spread);
    LibraryReflowPageSpec? at(int? index) => index == null
        ? null
        : index == leading
        ? lead
        : trail;
    return LibraryBookSpread.halves(
      pages: <LibraryReflowPageSpec>[?lead, ?trail],
      left: at(layout.left),
      right: at(layout.right),
    );
  }

  /// Whether [page] belongs to the current layout of [paginator].
  static bool _current(
    LibraryReflowPaginator paginator,
    LibraryReflowPageSpec page,
  ) => paginator.pageAt(page.chapter, page.indexInChapter) == page;

  /// The spread holding [page] when every page it needs is laid out in the
  /// current layout; else null (use [holding]).
  LibraryBookSpread? holdingNow(
    LibraryReflowPaginator paginator,
    LibraryReflowPageSpec page,
  ) {
    if (!_current(paginator, page)) return null;
    if (!doublePage) return LibraryBookSpread.single(page);
    final chapter = page.chapter;
    final index = page.indexInChapter;
    final pair = _pairOf(chapter, index);
    final (_, leading, trailing) = pair;
    LibraryReflowPageSpec? lead;
    if (leading == index) {
      lead = page;
    } else if (leading >= 0) {
      lead = paginator.pageAt(chapter, leading);
      if (lead == null) return null;
    }
    LibraryReflowPageSpec? trail;
    if (trailing == index) {
      trail = page;
    } else if (lead != null && !lead.isLastInChapter) {
      trail = paginator.pageAt(chapter, trailing);
      if (trail == null) return null;
    }
    return _build(chapter, pair, lead, trail);
  }

  /// The spread holding [page] (laid out again first when it comes from an
  /// earlier layout). Completes with the errors of the paginator
  /// (`LibraryReflowPaginationCancelled` when superseded).
  Future<LibraryBookSpread> holding(
    LibraryReflowPaginator paginator,
    LibraryReflowPageSpec page,
  ) async {
    final now = holdingNow(paginator, page);
    if (now != null) return now;
    final current = _current(paginator, page)
        ? page
        : await paginator.locate(page.start);
    if (!doublePage) return LibraryBookSpread.single(current);
    final chapter = current.chapter;
    final index = current.indexInChapter;
    final pair = _pairOf(chapter, index);
    final (_, leading, trailing) = pair;
    LibraryReflowPageSpec? lead;
    if (leading == index) {
      lead = current;
    } else if (leading >= 0) {
      lead =
          paginator.pageAt(chapter, leading) ??
          await paginator.previous(current);
    }
    LibraryReflowPageSpec? trail;
    if (trailing == index) {
      trail = current;
    } else if (lead != null && !lead.isLastInChapter) {
      trail = paginator.pageAt(chapter, trailing) ?? await paginator.next(lead);
    }
    return _build(chapter, pair, lead, trail);
  }

  /// The spread after [spread] when the pages it needs are laid out; null
  /// otherwise (use [after]) and at the end of the book.
  LibraryBookSpread? afterNow(
    LibraryReflowPaginator paginator,
    LibraryBookSpread spread,
  ) {
    final last = spread.last;
    if (!_current(paginator, last)) return null;
    final next = last.isLastInChapter
        ? (last.chapter + 1 < paginator.source.chapterCount
              ? paginator.pageAt(last.chapter + 1, 0)
              : null)
        : paginator.pageAt(last.chapter, last.indexInChapter + 1);
    return next == null ? null : holdingNow(paginator, next);
  }

  /// The spread after [spread]; null at the end of the book.
  Future<LibraryBookSpread?> after(
    LibraryReflowPaginator paginator,
    LibraryBookSpread spread,
  ) async {
    final now = afterNow(paginator, spread);
    if (now != null) return now;
    final next = await paginator.next(spread.last);
    return next == null ? null : holding(paginator, next);
  }

  /// The spread before [spread] when the pages it needs are laid out; null
  /// otherwise (use [before]) and at the start of the book.
  LibraryBookSpread? beforeNow(
    LibraryReflowPaginator paginator,
    LibraryBookSpread spread,
  ) {
    final first = spread.first;
    if (!_current(paginator, first)) return null;
    LibraryReflowPageSpec? previous;
    if (first.indexInChapter > 0) {
      previous = paginator.pageAt(first.chapter, first.indexInChapter - 1);
    } else if (first.chapter > 0) {
      final count = paginator.pageCountOf(first.chapter - 1);
      previous = count == null
          ? null
          : paginator.pageAt(first.chapter - 1, count - 1);
    }
    return previous == null ? null : holdingNow(paginator, previous);
  }

  /// The spread before [spread] (the last one of the previous chapter
  /// before the first spread of a chapter, which paginates that chapter
  /// whole); null at the start of the book.
  Future<LibraryBookSpread?> before(
    LibraryReflowPaginator paginator,
    LibraryBookSpread spread,
  ) async {
    final now = beforeNow(paginator, spread);
    if (now != null) return now;
    final previous = await paginator.previous(spread.first);
    return previous == null ? null : holding(paginator, previous);
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryBookSpreadRule &&
      other.doublePage == doublePage &&
      other.firstPageAlone == firstPageAlone &&
      other.rightToLeft == rightToLeft &&
      other.firstPageAloneInEveryChapter == firstPageAloneInEveryChapter;

  @override
  int get hashCode => Object.hash(
    doublePage,
    firstPageAlone,
    rightToLeft,
    firstPageAloneInEveryChapter,
  );
}

/// One spread: a page on the whole area, or its halves aligned toward the
/// spine as the page curl draws them ([LibraryPageSpreadLayout]).
class LibraryBookSpreadView extends StatelessWidget {
  const LibraryBookSpreadView({
    super.key,
    required this.spread,
    required this.paginator,
    required this.palette,
  });

  final LibraryBookSpread spread;
  final LibraryReflowPaginator paginator;
  final LibraryReaderPalette palette;

  /// What VoiceOver says of the spread before the text of its pages: "Page
  /// N of M" or "Pages N and N+1 of M", numbered in the chapter like the
  /// toolbar; "Page N" (each page) while the chapter is still being laid
  /// out.
  static String labelOf(
    BuildContext context,
    LibraryBookSpread spread,
    LibraryReflowPaginator paginator,
  ) {
    final total = paginator.pageCountOf(spread.chapter);
    final first = spread.first.indexInChapter + 1;
    final second = spread.isPair ? spread.last.indexInChapter + 1 : null;
    if (total == null) {
      return <String>[
        for (final page in <int?>[first, second])
          if (page != null)
            LibraryReaderLocale.format(context, 'pageNumber', <String, Object?>{
              'page': page,
            }),
      ].join('\n');
    }
    if (second == null) {
      return LibraryReaderLocale.format(
        context,
        'pageOfTotal',
        <String, Object?>{'page': first, 'total': total},
      );
    }
    return LibraryReaderLocale.format(
      context,
      'pagesOfTotal',
      <String, Object?>{'first': first, 'second': second, 'total': total},
    );
  }

  @override
  Widget build(BuildContext context) {
    final pages = spread.pages;
    return Semantics(
      container: true,
      label: labelOf(context, spread, paginator),
      child: LibraryPageSpreadLayout(
        // Pages named by their place in the reading order of the spread.
        face: spread.faceWith(pages.indexOf),
        pageBuilder: (context, index, alignment) => LibraryBookPageCanvas(
          key: ValueKey<(int, int)>((
            pages[index].chapter,
            pages[index].indexInChapter,
          )),
          page: pages[index],
          paginator: paginator,
          palette: palette,
          alignment: alignment,
          readingOrder: index,
        ),
      ),
    );
  }
}

/// One paginated page drawn from its picture, `BoxFit.contain` at
/// [alignment] (the page area has the page's size, so the picture fills
/// it), and announced by VoiceOver with the page's text.
///
/// The picture is painted once (again after a palette change, or once the
/// page's images are decoded by [LibraryReflowPaginator.prepare]) and
/// disposed with the widget. Painted again after the paginator released its
/// decoded images (memory pressure), the page prepares them first. Its text
/// is read again once the images are prepared (an image found undecodable
/// reads "Image unavailable").
class LibraryBookPageCanvas extends StatefulWidget {
  const LibraryBookPageCanvas({
    super.key,
    required this.page,
    required this.paginator,
    required this.palette,
    this.alignment = Alignment.center,
    this.readingOrder,
  });

  final LibraryReflowPageSpec page;
  final LibraryReflowPaginator paginator;

  /// Colours of the picture: a new palette paints it again.
  final LibraryReaderPalette palette;
  final Alignment alignment;

  /// Place of the page in its spread in reading order: VoiceOver reads a
  /// right-to-left spread from its right half.
  final int? readingOrder;

  @override
  State<LibraryBookPageCanvas> createState() => LibraryBookPageCanvasState();
}

class LibraryBookPageCanvasState extends State<LibraryBookPageCanvas> {
  ui.Picture? _picture;
  String? _text;
  int _prepare = 0;

  /// [LibraryReflowPaginator.imagesGeneration] when the images were last
  /// prepared.
  int _imagesGeneration = -1;

  @override
  void initState() {
    super.initState();
    _prepareImages();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // "Image unavailable" in the language of the app.
    _text = null;
  }

  @override
  void didUpdateWidget(covariant LibraryBookPageCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.page != widget.page ||
        !identical(oldWidget.paginator, widget.paginator)) {
      _drop();
      _text = null;
      _prepareImages();
    } else if (!identical(oldWidget.palette, widget.palette)) {
      _drop();
    }
  }

  @override
  void dispose() {
    _prepare++;
    _drop();
    super.dispose();
  }

  void _drop() {
    _picture?.dispose();
    _picture = null;
  }

  void _prepareImages() {
    final page = widget.page;
    _imagesGeneration = widget.paginator.imagesGeneration;
    final hasImages = page.slices.any(
      (slice) =>
          slice.kind == LibraryReflowSliceKind.image && !slice.imageFailed,
    );
    if (!hasImages) return;
    final request = ++_prepare;
    void prepared() {
      if (!mounted || request != _prepare) return;
      // Painted again with its decoded images; its text says which images
      // could not be decoded.
      setState(() {
        _drop();
        _text = null;
      });
    }

    widget.paginator
        .prepare(page)
        .then((_) => prepared(), onError: (Object _) => prepared());
  }

  @override
  Widget build(BuildContext context) {
    final paginator = widget.paginator;
    final page = widget.page;
    if (_picture == null &&
        _imagesGeneration != paginator.imagesGeneration &&
        paginator.needsPrepare(page)) {
      // The decoded images were released (memory pressure) since they were
      // prepared: decoded again, then painted again.
      _prepareImages();
    }
    final picture = _picture ??= paginator.paint(page);
    final text = _text ??= paginator.textOf(
      page,
      imageUnavailable: LibraryReaderLocale.text(context, 'imageUnavailable'),
    );
    final order = widget.readingOrder;
    return Semantics(
      container: true,
      label: text.isEmpty ? null : text,
      textDirection: paginator.textDirection,
      sortKey: order == null ? null : OrdinalSortKey(order.toDouble()),
      child: CustomPaint(
        painter: LibraryBookPagePainter(
          picture: picture,
          pageSize: page.size,
          alignment: widget.alignment,
        ),
        child: const SizedBox.expand(),
      ),
    );
  }
}

/// Draws a page [picture] of [pageSize] `BoxFit.contain` at [alignment],
/// like the page curl draws its texture.
class LibraryBookPagePainter extends CustomPainter {
  LibraryBookPagePainter({
    required this.picture,
    required this.pageSize,
    this.alignment = Alignment.center,
  });

  final ui.Picture picture;
  final Size pageSize;
  final Alignment alignment;

  @override
  void paint(Canvas canvas, Size size) {
    if (pageSize.isEmpty || size.isEmpty) return;
    final scale = math.min(
      size.width / pageSize.width,
      size.height / pageSize.height,
    );
    final drawn = pageSize * scale;
    final offset = alignment.alongOffset(
      Offset(size.width - drawn.width, size.height - drawn.height),
    );
    canvas.save();
    canvas.translate(offset.dx, offset.dy);
    if (scale != 1) canvas.scale(scale);
    canvas.drawPicture(picture);
    canvas.restore();
  }

  @override
  bool shouldRepaint(covariant LibraryBookPagePainter oldDelegate) =>
      !identical(oldDelegate.picture, picture) ||
      oldDelegate.pageSize != pageSize ||
      oldDelegate.alignment != alignment;
}

/// A neighbouring spread still being laid out (paper and a small spinner),
/// or one whose chapter could not be read (the error and Retry).
class LibraryBookPagePlaceholder extends StatelessWidget {
  const LibraryBookPagePlaceholder({
    super.key,
    required this.palette,
    this.error,
    this.onRetry,
  });

  final LibraryReaderPalette palette;
  final Object? error;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final error = this.error;
    return ColoredBox(
      color: palette.background,
      child: error != null
          ? LibraryReaderErrorView(
              error: LibraryReaderErrorInfo.from(error),
              palette: palette,
              compact: true,
              onRetry: onRetry,
            )
          : Center(
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
}
