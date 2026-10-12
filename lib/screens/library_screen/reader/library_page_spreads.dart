/// Two-page spreads of the paged readers (docs/library-books-3d-plan.md
/// § 3.9): which pages are shown together, and on which half of the screen.
///
/// * [LibraryDoublePageMode.auto] shows two pages in landscape only,
///   [LibraryDoublePageMode.always] in both orientations,
///   [LibraryDoublePageMode.never] never; the vertical (webtoon) layout never
///   shows two pages.
/// * With `firstPageAlone` (default), the cover is alone, then pages 2-3,
///   4-5... (one-based, as printed in a book); without it 1-2, 3-4... An odd
///   last page is alone.
/// * Pages are laid out like a book: in left-to-right reading the first page
///   of a pair is on the left; right to left, the next page is on the LEFT.
///   A lone cover stands on the side a book puts it (right in left-to-right
///   reading, left in right-to-left), a lone last page on the other side, so
///   every turn lifts one half like a real page (see `LibraryPageCurlFace`).
///
/// Indices are zero-based: pages `0..pageCount-1`, spreads `0..length-1`.
library;

import 'package:flutter/foundation.dart' show immutable;

import 'package:neostation/services/library_reading_store.dart'
    show LibraryDoublePageMode;

/// One spread: one page, or two consecutive pages shown side by side.
@immutable
class LibraryPageSpread {
  const LibraryPageSpread({
    required this.index,
    required this.first,
    this.second,
    this.left,
    this.right,
    this.doublePage = false,
  });

  /// Spread index.
  final int index;

  /// First page of the spread (the lowest index, read first).
  final int first;

  /// Second page of a pair (`first + 1`), null when the page is alone.
  final int? second;

  /// Page on the left half in a two-page layout (null: an empty half, or a
  /// single-page layout).
  final int? left;

  /// Page on the right half in a two-page layout.
  final int? right;

  /// Laid out as two halves (a pair, or a lone page on its book side).
  /// False: one page using the whole surface.
  final bool doublePage;

  /// Pages shown, in reading order (ascending), one or two.
  List<int> get pages => <int>[first, ?second];

  bool get isPair => second != null;

  /// Last page shown.
  int get last => second ?? first;

  bool contains(int page) => page == first || page == second;

  @override
  bool operator ==(Object other) =>
      other is LibraryPageSpread &&
      other.index == index &&
      other.first == first &&
      other.second == second &&
      other.left == left &&
      other.right == right &&
      other.doublePage == doublePage;

  @override
  int get hashCode =>
      Object.hash(index, first, second, left, right, doublePage);

  @override
  String toString() => doublePage
      ? 'LibraryPageSpread($index: left $left, right $right)'
      : 'LibraryPageSpread($index: page $first)';
}

/// The spreads of a book or chapter of [pageCount] pages.
@immutable
class LibraryPageSpreads {
  /// Spreads for the reader's current layout.
  factory LibraryPageSpreads({
    required int pageCount,
    LibraryDoublePageMode doublePage = LibraryDoublePageMode.auto,
    bool firstPageAlone = true,
    bool landscape = false,
    bool vertical = false,
    bool rightToLeft = false,
  }) => LibraryPageSpreads._(
    pageCount: pageCount < 0 ? 0 : pageCount,
    doublePage: usesDoublePages(
      mode: doublePage,
      landscape: landscape,
      vertical: vertical,
    ),
    firstPageAlone: firstPageAlone,
    rightToLeft: rightToLeft,
  );

  /// One page per spread.
  factory LibraryPageSpreads.single(int pageCount) => LibraryPageSpreads._(
    pageCount: pageCount < 0 ? 0 : pageCount,
    doublePage: false,
    firstPageAlone: true,
    rightToLeft: false,
  );

  const LibraryPageSpreads._({
    required this.pageCount,
    required this.doublePage,
    required this.firstPageAlone,
    required this.rightToLeft,
  });

  /// Whether two pages are shown side by side: never in the vertical
  /// layout; [LibraryDoublePageMode.auto] in landscape only.
  static bool usesDoublePages({
    required LibraryDoublePageMode mode,
    required bool landscape,
    required bool vertical,
  }) {
    if (vertical) return false;
    return switch (mode) {
      LibraryDoublePageMode.always => true,
      LibraryDoublePageMode.auto => landscape,
      LibraryDoublePageMode.never => false,
    };
  }

  final int pageCount;

  /// Two pages side by side.
  final bool doublePage;

  /// The cover is alone (two-page layout only).
  final bool firstPageAlone;

  /// Right-to-left reading: the next page is on the left.
  final bool rightToLeft;

  // Offset of the pairing: with the cover alone, pairs start at page 1.
  int get _shift => firstPageAlone ? 1 : 0;

  /// Number of spreads.
  int get length {
    if (pageCount == 0) return 0;
    if (!doublePage) return pageCount;
    // Pairs (2k - shift, 2k + 1 - shift) for k = 0..: the last one holding
    // page count - 1.
    return (pageCount - 1 + _shift) ~/ 2 + 1;
  }

  bool get isEmpty => pageCount == 0;

  /// Spread showing [page] (clamped to the pages).
  int spreadOf(int page) {
    if (pageCount == 0) return 0;
    final clamped = page.clamp(0, pageCount - 1);
    if (!doublePage) return clamped;
    return (clamped + _shift) ~/ 2;
  }

  /// Spread [index] (clamped to the spreads). Throws on an empty book.
  LibraryPageSpread spreadAt(int index) {
    if (pageCount == 0) {
      throw RangeError('No spread in an empty book');
    }
    final spread = index.clamp(0, length - 1);
    if (!doublePage) {
      return LibraryPageSpread(index: spread, first: spread);
    }
    // Pair (leading, trailing) in reading order; out-of-range halves empty.
    final leading = 2 * spread - _shift;
    final trailing = leading + 1;
    final first = leading >= 0 ? leading : trailing;
    final second = leading >= 0 && trailing < pageCount ? trailing : null;
    final leadingPage = leading >= 0 ? leading : null;
    final trailingPage = trailing < pageCount ? trailing : null;
    return LibraryPageSpread(
      index: spread,
      first: first,
      second: second,
      left: rightToLeft ? trailingPage : leadingPage,
      right: rightToLeft ? leadingPage : trailingPage,
      doublePage: true,
    );
  }

  /// Spread [index] (clamped).
  LibraryPageSpread operator [](int index) => spreadAt(index);

  /// First page (in reading order) of spread [index].
  int firstPageOf(int index) => pageCount == 0 ? 0 : spreadAt(index).first;

  /// Pages of spread [index] in reading order.
  List<int> pagesOf(int index) =>
      pageCount == 0 ? const <int>[] : spreadAt(index).pages;

  /// Pages a spread shows, for its semantics label: one page ("Page N of
  /// M") or the pair ("Pages N and N+1 of M"), ascending.
  List<int> pagesShown(int index) => pagesOf(index);

  /// Pages of spread [index] from the left of the screen to the right,
  /// `(left, right)`, null for an empty half. A single-page layout has no
  /// halves: `(page, null)`.
  (int?, int?) sidesOf(int index) {
    if (pageCount == 0) return (null, null);
    final spread = spreadAt(index);
    if (!spread.doublePage) return (spread.first, null);
    return (spread.left, spread.right);
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryPageSpreads &&
      other.pageCount == pageCount &&
      other.doublePage == doublePage &&
      other.firstPageAlone == firstPageAlone &&
      other.rightToLeft == rightToLeft;

  @override
  int get hashCode =>
      Object.hash(pageCount, doublePage, firstPageAlone, rightToLeft);

  @override
  String toString() =>
      'LibraryPageSpreads($pageCount pages, ${doublePage ? 'double' : 'single'}'
      '${doublePage && firstPageAlone ? ', cover alone' : ''}'
      '${rightToLeft ? ', rtl' : ''})';
}
