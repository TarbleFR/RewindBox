// Two-page spreads of the paged readers (docs/library-books-3d-plan.md
// § 3.9): automatic = landscape only, never in the vertical layout, cover
// alone then 2-3, 4-5... (one-based), an odd last page alone, the next page
// on the left in right-to-left reading.
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_page_spreads.dart';
import 'package:neostation/services/library_reading_store.dart';

/// `(left, right)` of every spread.
List<(int?, int?)> sides(LibraryPageSpreads spreads) => <(int?, int?)>[
  for (var i = 0; i < spreads.length; i++) spreads.sidesOf(i),
];

List<List<int>> pages(LibraryPageSpreads spreads) => <List<int>>[
  for (var i = 0; i < spreads.length; i++) spreads.pagesOf(i),
];

LibraryPageSpreads book(
  int pageCount, {
  bool firstPageAlone = true,
  bool rightToLeft = false,
}) => LibraryPageSpreads(
  pageCount: pageCount,
  doublePage: LibraryDoublePageMode.always,
  firstPageAlone: firstPageAlone,
  rightToLeft: rightToLeft,
);

void main() {
  group('when two pages are shown', () {
    test('automatic: in landscape only', () {
      expect(
        LibraryPageSpreads.usesDoublePages(
          mode: LibraryDoublePageMode.auto,
          landscape: true,
          vertical: false,
        ),
        isTrue,
      );
      expect(
        LibraryPageSpreads.usesDoublePages(
          mode: LibraryDoublePageMode.auto,
          landscape: false,
          vertical: false,
        ),
        isFalse,
      );
    });

    test('always and never ignore the orientation', () {
      for (final landscape in <bool>[true, false]) {
        expect(
          LibraryPageSpreads.usesDoublePages(
            mode: LibraryDoublePageMode.always,
            landscape: landscape,
            vertical: false,
          ),
          isTrue,
        );
        expect(
          LibraryPageSpreads.usesDoublePages(
            mode: LibraryDoublePageMode.never,
            landscape: landscape,
            vertical: false,
          ),
          isFalse,
        );
      }
    });

    test('never in the vertical layout', () {
      for (final mode in LibraryDoublePageMode.values) {
        for (final landscape in <bool>[true, false]) {
          expect(
            LibraryPageSpreads.usesDoublePages(
              mode: mode,
              landscape: landscape,
              vertical: true,
            ),
            isFalse,
            reason: '$mode landscape=$landscape',
          );
          final spreads = LibraryPageSpreads(
            pageCount: 6,
            doublePage: mode,
            landscape: landscape,
            vertical: true,
          );
          expect(spreads.doublePage, isFalse);
          expect(spreads.length, 6);
        }
      }
    });

    test('the default mode is automatic with the cover alone', () {
      final landscape = LibraryPageSpreads(pageCount: 5, landscape: true);
      expect(landscape.doublePage, isTrue);
      expect(pages(landscape), <List<int>>[
        <int>[0],
        <int>[1, 2],
        <int>[3, 4],
      ]);
      final portrait = LibraryPageSpreads(pageCount: 5);
      expect(portrait.doublePage, isFalse);
    });
  });

  group('single pages (portrait, never)', () {
    test('one page per spread, on the whole surface', () {
      final spreads = LibraryPageSpreads(
        pageCount: 4,
        doublePage: LibraryDoublePageMode.never,
        landscape: true,
      );
      expect(spreads.length, 4);
      for (var page = 0; page < 4; page++) {
        expect(spreads.spreadOf(page), page);
        final spread = spreads.spreadAt(page);
        expect(spread.doublePage, isFalse);
        expect(spread.first, page);
        expect(spread.second, isNull);
        expect(spread.left, isNull);
        expect(spread.right, isNull);
        expect(spreads.sidesOf(page), (page, null));
        expect(spreads.pagesShown(page), <int>[page]);
      }
    });

    test('firstPageAlone and right to left change nothing', () {
      for (final alone in <bool>[true, false]) {
        for (final rtl in <bool>[true, false]) {
          final spreads = LibraryPageSpreads(
            pageCount: 3,
            doublePage: LibraryDoublePageMode.auto,
            firstPageAlone: alone,
            rightToLeft: rtl,
          );
          expect(pages(spreads), <List<int>>[
            <int>[0],
            <int>[1],
            <int>[2],
          ]);
        }
      }
    });
  });

  group('cover alone (firstPageAlone)', () {
    test('cover alone, then 2-3, 4-5... and an odd last page alone', () {
      // One-based: (1), (2-3), (4-5), (6-7).
      expect(pages(book(7)), <List<int>>[
        <int>[0],
        <int>[1, 2],
        <int>[3, 4],
        <int>[5, 6],
      ]);
      // One-based: (1), (2-3), (4-5), (6).
      expect(pages(book(6)), <List<int>>[
        <int>[0],
        <int>[1, 2],
        <int>[3, 4],
        <int>[5],
      ]);
    });

    test('left to right: the cover on the right, a lone last page on the '
        'left', () {
      expect(sides(book(6)), <(int?, int?)>[
        (null, 0),
        (1, 2),
        (3, 4),
        (5, null),
      ]);
      expect(sides(book(7)).last, (5, 6));
    });

    test('right to left: the next page on the left', () {
      expect(sides(book(6, rightToLeft: true)), <(int?, int?)>[
        (0, null),
        (2, 1),
        (4, 3),
        (null, 5),
      ]);
      // Reading order is unchanged.
      expect(pages(book(6, rightToLeft: true)), pages(book(6)));
    });

    test('page <-> spread', () {
      final spreads = book(6);
      expect(
        <int>[for (var p = 0; p < 6; p++) spreads.spreadOf(p)],
        <int>[0, 1, 1, 2, 2, 3],
      );
      expect(
        <int>[for (var s = 0; s < 4; s++) spreads.firstPageOf(s)],
        <int>[0, 1, 3, 5],
      );
    });
  });

  group('without firstPageAlone', () {
    test('1-2, 3-4... and an odd last page alone', () {
      expect(pages(book(5, firstPageAlone: false)), <List<int>>[
        <int>[0, 1],
        <int>[2, 3],
        <int>[4],
      ]);
      expect(pages(book(6, firstPageAlone: false)), <List<int>>[
        <int>[0, 1],
        <int>[2, 3],
        <int>[4, 5],
      ]);
    });

    test('sides, both directions', () {
      expect(sides(book(5, firstPageAlone: false)), <(int?, int?)>[
        (0, 1),
        (2, 3),
        (4, null),
      ]);
      expect(
        sides(book(5, firstPageAlone: false, rightToLeft: true)),
        <(int?, int?)>[(1, 0), (3, 2), (null, 4)],
      );
    });

    test('page <-> spread', () {
      final spreads = book(5, firstPageAlone: false);
      expect(
        <int>[for (var p = 0; p < 5; p++) spreads.spreadOf(p)],
        <int>[0, 0, 1, 1, 2],
      );
      expect(
        <int>[for (var s = 0; s < 3; s++) spreads.firstPageOf(s)],
        <int>[0, 2, 4],
      );
    });
  });

  test('every page belongs to exactly one spread, in order', () {
    for (var count = 1; count <= 9; count++) {
      for (final alone in <bool>[true, false]) {
        for (final rtl in <bool>[true, false]) {
          for (final double in <bool>[true, false]) {
            final spreads = LibraryPageSpreads(
              pageCount: count,
              doublePage: double
                  ? LibraryDoublePageMode.always
                  : LibraryDoublePageMode.never,
              firstPageAlone: alone,
              rightToLeft: rtl,
            );
            final all = <int>[
              for (var s = 0; s < spreads.length; s++) ...spreads.pagesOf(s),
            ];
            expect(all, List<int>.generate(count, (i) => i));
            for (var page = 0; page < count; page++) {
              final spread = spreads.spreadAt(spreads.spreadOf(page));
              expect(spread.contains(page), isTrue);
              expect(spread.index, spreads.spreadOf(page));
            }
            for (var s = 0; s < spreads.length; s++) {
              final spread = spreads[s];
              final shown = <int>[?spread.left, ?spread.right]..sort();
              if (spread.doublePage) expect(shown, spread.pages);
              expect(spreads.spreadOf(spread.first), s);
            }
          }
        }
      }
    }
  });

  test('semantics: one page, or the pair in ascending order', () {
    final ltr = book(5);
    final rtl = book(5, rightToLeft: true);
    expect(ltr.pagesShown(0), <int>[0]);
    expect(ltr.pagesShown(1), <int>[1, 2]);
    expect(rtl.pagesShown(1), <int>[1, 2]);
    expect(rtl.pagesShown(2), <int>[3, 4]);
    expect(book(4).pagesShown(2), <int>[3]);
  });

  test('out-of-range pages and spreads are clamped', () {
    final spreads = book(6);
    expect(spreads.spreadOf(-3), 0);
    expect(spreads.spreadOf(99), 3);
    expect(spreads.spreadAt(-1).index, 0);
    expect(spreads.spreadAt(42).index, 3);
  });

  test('a one-page book and an empty book', () {
    expect(sides(book(1)), <(int?, int?)>[(null, 0)]);
    expect(sides(book(1, firstPageAlone: false)), <(int?, int?)>[(0, null)]);
    final empty = book(0);
    expect(empty.length, 0);
    expect(empty.isEmpty, isTrue);
    expect(empty.spreadOf(0), 0);
    expect(empty.pagesOf(0), isEmpty);
    expect(empty.sidesOf(0), (null, null));
    expect(() => empty.spreadAt(0), throwsRangeError);
    expect(LibraryPageSpreads(pageCount: -2).length, 0);
  });

  test('equality follows the layout', () {
    expect(book(6), book(6));
    expect(book(6), isNot(book(6, rightToLeft: true)));
    expect(book(6), isNot(book(6, firstPageAlone: false)));
    expect(book(6), isNot(book(7)));
    expect(
      LibraryPageSpreads(pageCount: 6, landscape: true),
      LibraryPageSpreads(
        pageCount: 6,
        doublePage: LibraryDoublePageMode.always,
      ),
    );
  });
}
