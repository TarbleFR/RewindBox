// Pagination of the reflowable reader (docs/library-books-3d-plan.md § 3.5):
// pages of whole lines laid out like the scroll view, positions that survive
// the EPUB CFI / `txt:b:o` round trip, repagination on the same words,
// images, frame budget, cancellation, memoization and painting.
import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_palette.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_paginator.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_source.dart';
import 'package:neostation/screens/library_screen/reader/library_reflow_view.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_text_document.dart';

import 'library_local_fixtures.dart';

const LibraryReflowStyle bookStyle = LibraryReflowStyle(
  palette: LibraryReaderPalette.light,
  fontSize: 16,
  lineHeight: 1.5,
  fontFamily: LibraryReaderFontFamily.serif,
  justify: true,
  margin: 16,
);

/// A phone page in portrait, below the back control.
const Size phonePage = Size(360, 560);
const EdgeInsets phonePadding = EdgeInsets.fromLTRB(16, 24, 16, 24);

/// 1000 paragraphs: five TXT sections of 200 (as in the reader tests).
String sampleText({int paragraphs = 1000}) => List<String>.generate(
  paragraphs,
  (i) => 'Paragraph $i ${List<String>.filled(40, 'word$i').join(' ')}',
).join('\n\n');

LibraryReflowPaginator paginatorFor(
  LibraryReflowSource source, {
  LibraryReflowStyle style = bookStyle,
  Size pageSize = phonePage,
  EdgeInsets padding = phonePadding,
  Duration frameBudget = const Duration(milliseconds: 6),
  TextDirection textDirection = TextDirection.ltr,
  Locale? locale,
}) => LibraryReflowPaginator(
  source: source,
  style: style,
  pageSize: pageSize,
  padding: padding,
  textScaler: TextScaler.noScaling,
  frameBudget: frameBudget,
  textDirection: textDirection,
  locale: locale,
);

int compare(LibraryReflowPosition a, LibraryReflowPosition b) {
  if (a.chapter != b.chapter) return a.chapter - b.chapter;
  if (a.block != b.block) return a.block - b.block;
  return a.offset - b.offset;
}

String unitText(LibraryReflowUnit unit) =>
    unit.spans.map((span) => span.text).join();

bool isText(LibraryReflowUnit unit) =>
    unit.source.kind != LibraryTextBlockKind.image &&
    unit.source.kind != LibraryTextBlockKind.rule;

/// The pages of [chapter] follow each other without gap or overlap, cover
/// every unit once, in order, from its first character to its last, and
/// keep their lines inside the text area; no page but the last ends with a
/// heading that has text above it on that page.
void expectCoversChapter(
  List<LibraryReflowPageSpec> pages,
  List<LibraryReflowUnit> units, {
  required int chapter,
  required Rect area,
}) {
  expect(pages, isNotEmpty);
  expect(pages.first.start, LibraryReflowPosition(chapter, 0, 0));
  expect(
    pages.last.end,
    LibraryReflowPosition(chapter, units.last.block, units.last.end),
  );
  var unit = 0;
  var offset = 0;
  for (var k = 0; k < pages.length; k++) {
    final page = pages[k];
    expect(page.chapter, chapter);
    expect(page.indexInChapter, k);
    expect(page.isLastInChapter, k == pages.length - 1);
    if (k > 0) expect(page.start, pages[k - 1].end, reason: 'page $k');
    expect(page.slices, isNotEmpty, reason: 'page $k');
    expect(page.slices.first.start, page.start, reason: 'page $k');
    var bottom = area.top;
    for (final slice in page.slices) {
      if (slice.unitIndex != unit) {
        expect(offset, units[unit].length, reason: 'unit $unit cut short');
        unit++;
        offset = 0;
      }
      expect(slice.unitIndex, unit, reason: 'page $k skips a unit');
      final expected = units[unit];
      expect(
        (slice.unit.block, slice.unit.start, slice.unit.end),
        (expected.block, expected.start, expected.end),
      );
      expect(slice.startOffset, offset, reason: 'page $k, unit $unit');
      if (isText(expected)) {
        expect(slice.lineStarts, isNotEmpty);
        expect(slice.lineStarts.first, slice.startOffset);
        expect(slice.endOffset, greaterThan(slice.startOffset));
      }
      offset = slice.endOffset;
      // Top to bottom, inside the text area.
      expect(slice.rect.top, greaterThanOrEqualTo(bottom - 0.01));
      expect(slice.rect.bottom, lessThanOrEqualTo(area.bottom + 0.01));
      bottom = slice.rect.bottom;
    }
    if (!page.isLastInChapter) {
      final last = page.slices.last;
      final onlyHeadings = page.slices.every(
        (slice) => slice.unit.source.kind == LibraryTextBlockKind.heading,
      );
      expect(
        last.unit.source.kind == LibraryTextBlockKind.heading && !onlyHeadings,
        isFalse,
        reason: 'page $k ends with a heading',
      );
    }
  }
  expect(unit, units.length - 1);
  expect(offset, units.last.length);
}

/// A unit as the scroll view lays it out.
class ViewUnit {
  ViewUnit(this.lineStarts, this.textRect);

  /// Line starts read from the carets of its `RenderParagraph` (a new line
  /// starts where the caret moves down).
  final List<int> lineStarts;

  /// Its text in the column of units (column origin at 0, 0).
  final Rect textRect;
}

/// Builds [units] with `LibraryReflowUnitView` in a column [width] wide,
/// as the scroll view does, and reads where their lines break.
Future<Map<int, ViewUnit>> layOutInScrollView(
  WidgetTester tester,
  List<LibraryReflowUnit> units, {
  required LibraryReflowStyle style,
  required double width,
  required EdgeInsets horizontal,
  TextDirection textDirection = TextDirection.ltr,
}) async {
  final registry = LibraryReflowUnitRegistry();
  final images = LibraryReflowImageCache(
    (_) => Future<Uint8List>.error(StateError('no image here')),
  );
  const columnKey = ValueKey<String>('units');
  await tester.pumpWidget(
    MaterialApp(
      home: Material(
        child: SingleChildScrollView(
          child: Align(
            alignment: Alignment.topLeft,
            child: SizedBox(
              width: width,
              child: Directionality(
                textDirection: textDirection,
                child: Column(
                  key: columnKey,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    for (var i = 0; i < units.length; i++)
                      LibraryReflowUnitView(
                        key: ValueKey<int>(i),
                        unit: units[i],
                        chapter: units[i].chapter,
                        unitIndex: i,
                        style: style,
                        horizontalPadding: horizontal,
                        registry: registry,
                        onLink: (_) {},
                        images: images,
                        maxImageHeight: 1000,
                      ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
  final origin = tester.getTopLeft(find.byKey(columnKey));
  final result = <int, ViewUnit>{};
  for (var i = 0; i < units.length; i++) {
    if (!isText(units[i])) continue;
    final text = unitText(units[i]);
    final paragraph = tester
        .renderObjectList<RenderParagraph>(
          find.descendant(
            of: find.byKey(ValueKey<int>(i)),
            matching: find.byType(RichText),
          ),
        )
        .singleWhere((paragraph) => paragraph.text.toPlainText() == text);
    // A caret moves down by a whole line (at least 18 px here) at a line
    // start; within a line, a smaller run (inline code) only lowers it by a
    // pixel or two.
    final starts = <int>[0];
    var lineTop = paragraph
        .getOffsetForCaret(const TextPosition(offset: 0), Rect.zero)
        .dy;
    for (var k = 1; k <= text.length; k++) {
      final y = paragraph
          .getOffsetForCaret(TextPosition(offset: k), Rect.zero)
          .dy;
      if (y > lineTop + 6) {
        starts.add(k);
        lineTop = y;
      } else if (y < lineTop) {
        lineTop = y;
      }
    }
    final topLeft = paragraph.localToGlobal(Offset.zero) - origin;
    result[i] = ViewUnit(starts, topLeft & paragraph.size);
  }
  return result;
}

Future<LibraryEpubDocument> openEpub(
  WidgetTester tester,
  Uint8List bytes,
) async => (await tester.runAsync(() async {
  final directory = await createTempDir('ns_paginator_epub_');
  final file = await writeFile(directory, 'book.epub', bytes);
  return LibraryEpubDocument.open(file.path);
}))!;

/// A chapter with every kind of text block the reader shows.
String mixedChapter() {
  final long = List<String>.generate(420, (i) => 'long$i').join(' ');
  return xhtml(
    '<h1>Chapter One</h1>'
    '<p>First paragraph with <em>emphasis</em>, <b>bold words</b> and '
    '<code>code</code> in it, long enough to wrap over several lines.</p>'
    '<p align="center">A centred paragraph that also wraps around.</p>'
    '<blockquote><p>A quoted passage, indented, with a bar on its left '
    'side and long enough to wrap.</p></blockquote>'
    '<ul><li>A first bullet item long enough to wrap onto a second '
    'line.</li><li>Second item.</li></ul>'
    '<ol><li>Numbered item one with some words.</li><li>Item two.</li></ol>'
    '<pre>line one\n  indented line two\n\nline four after a blank line, '
    'long enough to wrap</pre>'
    '<h2>Part Two</h2>'
    '<p>$long</p>'
    '<hr/>'
    '<h3>After the rule</h3><p>Final <a href="ch2.xhtml">link</a> words.</p>',
  );
}

/// Reflowable chapters held in memory (exact geometry tests).
class BlocksSource implements LibraryReflowSource {
  BlocksSource(this.chapters);

  final List<List<LibraryTextBlock>> chapters;

  @override
  int get chapterCount => chapters.length;

  @override
  bool get separatesChapters => true;

  @override
  List<LibraryReflowTocEntry> get toc => const <LibraryReflowTocEntry>[];

  @override
  Future<List<LibraryTextBlock>> loadChapter(int chapter) =>
      SynchronousFuture<List<LibraryTextBlock>>(chapters[chapter]);

  @override
  List<LibraryTextBlock>? loadedChapter(int chapter) => chapters[chapter];

  @override
  String locationFor(LibraryReflowPosition position) =>
      'mem:${position.chapter}:${position.block}:${position.offset}';

  @override
  Future<LibraryReflowPosition?> resolveLocation(String location) async {
    final parts = location.split(':');
    return LibraryReflowPosition(
      int.parse(parts[1]),
      int.parse(parts[2]),
      int.parse(parts[3]),
    );
  }

  @override
  double fractionFor(LibraryReflowPosition position) => 0;

  @override
  Future<LibraryReflowPosition> positionAtFraction(double fraction) async =>
      LibraryReflowPosition.start;

  @override
  Future<LibraryReflowPosition?> resolveLink(String href) async => null;

  @override
  Future<Uint8List> resource(String href) =>
      Future<Uint8List>.error(StateError('no resource $href'));

  @override
  Future<void> close() async {}
}

LibraryTextBlock paragraphBlock(String text) => LibraryTextBlock(
  kind: LibraryTextBlockKind.paragraph,
  spans: <LibraryTextSpan>[LibraryTextSpan(text)],
);

LibraryTextBlock headingBlock(String text, {int level = 2}) => LibraryTextBlock(
  kind: LibraryTextBlockKind.heading,
  headingLevel: level,
  spans: <LibraryTextSpan>[LibraryTextSpan(text)],
);

/// RGBA pixels of a picture of [size] logical pixels at [pixelRatio].
Future<(ByteData, int, int)> pixelsOf(
  WidgetTester tester,
  ui.Picture picture,
  Size size, {
  double pixelRatio = 1,
}) async => (await tester.runAsync(() async {
  final width = (size.width * pixelRatio).ceil();
  final height = (size.height * pixelRatio).ceil();
  final image = await picture.toImage(width, height);
  try {
    final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
    return (data!, image.width, image.height);
  } finally {
    image.dispose();
    picture.dispose();
  }
}))!;

int pixelAt(ByteData data, int width, int x, int y) {
  final i = (y * width + x) * 4;
  return (data.getUint8(i + 3) << 24) |
      (data.getUint8(i) << 16) |
      (data.getUint8(i + 1) << 8) |
      data.getUint8(i + 2);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('lines and pages', () {
    testWidgets('the same words fall on each line as in the scroll view', (
      tester,
    ) async {
      final document = await openEpub(
        tester,
        buildEpub3(chapter1: mixedChapter()),
      );
      final source = LibraryEpubReflowSource(document);
      await tester.runAsync(() => source.loadChapter(0));
      final units = libraryReflowUnits(0, source.loadedChapter(0)!);
      // Every kind of block, and a paragraph cut into display units.
      expect(
        units.map((unit) => unit.source.kind).toSet(),
        containsAll(
          LibraryTextBlockKind.values.toSet()
            ..remove(LibraryTextBlockKind.image),
        ),
      );
      expect(units.where((unit) => !unit.isFirstPiece), isNotEmpty);
      const horizontal = EdgeInsets.only(left: 20, right: 12);
      final view = await layOutInScrollView(
        tester,
        units,
        style: bookStyle,
        width: phonePage.width,
        horizontal: horizontal,
      );

      // One page tall enough for the whole chapter: every text sits where
      // the scroll view puts it, and breaks the same way.
      final tall = paginatorFor(
        source,
        pageSize: const Size(360, 100000),
        padding: horizontal,
        locale: const Locale('en', 'US'),
      );
      final single = (await tester.runAsync(() => tall.paginate(0)))!;
      expect(single, hasLength(1));
      for (final slice in single.single.slices) {
        if (slice.kind != LibraryReflowSliceKind.text) continue;
        final reference = view[slice.unitIndex]!;
        expect(slice.lineStarts, reference.lineStarts);
        expect(slice.rect.left, closeTo(reference.textRect.left, 0.01));
        expect(slice.rect.top, closeTo(reference.textRect.top, 0.01));
        expect(slice.rect.width, closeTo(reference.textRect.width, 0.01));
        expect(slice.rect.height, closeTo(reference.textRect.height, 0.01));
      }

      // Phone pages: the units are cut between those same lines only.
      final paginator = paginatorFor(
        source,
        padding: phonePadding.copyWith(left: 20, right: 12),
        locale: const Locale('en', 'US'),
      );
      final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
      expect(pages.length, greaterThan(3));
      expectCoversChapter(
        pages,
        units,
        chapter: 0,
        area: const Rect.fromLTRB(20, 24, 348, 536),
      );
      var cut = 0;
      for (var i = 0; i < units.length; i++) {
        if (!isText(units[i])) continue;
        final slices = <LibraryReflowPageSlice>[
          for (final page in pages)
            for (final slice in page.slices)
              if (slice.unitIndex == i) slice,
        ];
        if (slices.length > 1) cut++;
        expect(
          <int>[for (final slice in slices) ...slice.lineStarts],
          view[i]!.lineStarts,
          reason: 'unit $i (${units[i].source.kind.name})',
        );
        for (final slice in slices) {
          expect(
            slice.endOffset == units[i].length ||
                view[i]!.lineStarts.contains(slice.endOffset),
            isTrue,
            reason: 'unit $i cut inside a line',
          );
        }
      }
      expect(cut, greaterThan(0), reason: 'some unit spans two pages');
      await tester.runAsync(source.close);
    });

    testWidgets('a TXT section is cut between lines of the scroll view', (
      tester,
    ) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText(paragraphs: 60)),
      );
      final units = libraryReflowUnits(0, source.loadedChapter(0)!);
      final view = await layOutInScrollView(
        tester,
        units,
        style: bookStyle,
        width: phonePage.width,
        horizontal: const EdgeInsets.symmetric(horizontal: 16),
      );
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
      expectCoversChapter(
        pages,
        units,
        chapter: 0,
        area: phonePadding.deflateRect(Offset.zero & phonePage),
      );
      for (final page in pages) {
        for (final slice in page.slices) {
          final lines = view[slice.unitIndex]!.lineStarts;
          final first = lines.indexOf(slice.startOffset);
          expect(first, greaterThanOrEqualTo(0));
          expect(
            slice.lineStarts,
            lines.sublist(first, first + slice.lineCount),
          );
        }
      }
      // Paragraphs longer than a page are spread over pages.
      expect(pages.length, greaterThan(units.length ~/ 2));
    });

    testWidgets('mixed and right-to-left lines break as in the scroll view', (
      tester,
    ) async {
      // Hebrew words inside Latin text and the reverse: the visual ends of
      // such lines are not their first characters.
      final blocks = <LibraryTextBlock>[
        for (var i = 0; i < 6; i++)
          paragraphBlock(
            List<String>.generate(
              24,
              (k) => k.isEven ? 'שלום$i$k' : 'word$i$k',
            ).join(i.isEven ? ' ' : ', '),
          ),
        paragraphBlock(List<String>.filled(30, 'עולם').join(' ')),
      ];
      final units = libraryReflowUnits(0, blocks);
      final source = BlocksSource(<List<LibraryTextBlock>>[blocks]);
      for (final direction in TextDirection.values) {
        final view = await layOutInScrollView(
          tester,
          units,
          style: bookStyle,
          width: phonePage.width,
          horizontal: const EdgeInsets.symmetric(horizontal: 16),
          textDirection: direction,
        );
        final paginator = paginatorFor(source, textDirection: direction);
        final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
        expectCoversChapter(
          pages,
          units,
          chapter: 0,
          area: phonePadding.deflateRect(Offset.zero & phonePage),
        );
        for (var i = 0; i < units.length; i++) {
          expect(
            <int>[
              for (final page in pages)
                for (final slice in page.slices)
                  if (slice.unitIndex == i) ...slice.lineStarts,
            ],
            view[i]!.lineStarts,
            reason: '${direction.name} unit $i',
          );
        }
      }
    });

    testWidgets('a heading never ends a page that holds text before it', (
      tester,
    ) async {
      // Filler of growing length puts the heading at every height of the
      // page, including just above the bottom.
      var moved = 0;
      for (var words = 40; words <= 120; words += 3) {
        final blocks = <LibraryTextBlock>[
          paragraphBlock(List<String>.filled(words, 'abc').join(' ')),
          headingBlock('Part'),
          paragraphBlock(List<String>.filled(30, 'xyz').join(' ')),
        ];
        final source = BlocksSource(<List<LibraryTextBlock>>[blocks]);
        final paginator = paginatorFor(source);
        final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
        final units = libraryReflowUnits(0, blocks);
        expectCoversChapter(
          pages,
          units,
          chapter: 0,
          area: phonePadding.deflateRect(Offset.zero & phonePage),
        );
        // The heading opens a page although it would have fitted at the
        // bottom of the previous one: it went on with its text.
        for (var k = 1; k < pages.length; k++) {
          final first = pages[k].slices.first;
          if (first.unit.source.kind != LibraryTextBlockKind.heading) {
            continue;
          }
          final before = pages[k - 1].slices.last.rect.bottom;
          final room = phonePage.height - phonePadding.bottom - before;
          if (room > 16 * 1.1 + first.rect.height + 16 * 0.6) moved++;
        }
      }
      expect(moved, greaterThan(0));
    });

    testWidgets('an empty chapter has one empty page', (tester) async {
      final source = BlocksSource(<List<LibraryTextBlock>>[
        <LibraryTextBlock>[],
        <LibraryTextBlock>[paragraphBlock('Text.')],
      ]);
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
      expect(pages, hasLength(1));
      expect(pages.single.isEmpty, isTrue);
      expect(pages.single.start, const LibraryReflowPosition(0, 0, 0));
      expect(pages.single.end, const LibraryReflowPosition(0, 0, 0));
      final next = (await tester.runAsync(() => paginator.next(pages.single)))!;
      expect(next.chapter, 1);
    });
  });

  group('positions', () {
    testWidgets('TXT: page start -> txt:b:o -> resolveLocation -> same page', (
      tester,
    ) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(2)))!;
      expect(pages.length, greaterThan(20));
      for (final page in pages) {
        final location = source.locationFor(page.start);
        expect(location, 'txt:${400 + page.start.block}:${page.start.offset}');
        final resolved = await source.resolveLocation(location);
        expect(resolved, page.start);
        expect(paginator.pageFor(resolved!), same(page));
        // Any character of the page leads to it.
        final inside = LibraryReflowPosition(
          2,
          page.slices.first.unit.block,
          page.slices.first.unit.start + page.slices.first.endOffset - 1,
        );
        expect(paginator.pageFor(inside), same(page));
      }
      // Beyond the text of the chapter: its last page.
      expect(
        paginator.pageFor(const LibraryReflowPosition(2, 9999, 0)),
        same(pages.last),
      );
      expect(paginator.pageCountOf(2), pages.length);
    });

    testWidgets('EPUB: page start -> CFI -> resolveLocation -> same page', (
      tester,
    ) async {
      final document = await openEpub(
        tester,
        buildEpub3(
          chapter1: xhtml(
            List<String>.generate(
              120,
              (i) =>
                  '<p>Paragraph $i ${List<String>.filled(28, 'w$i').join(' ')}</p>',
            ).join(),
          ),
        ),
      );
      final source = LibraryEpubReflowSource(document);
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
      expect(pages.length, greaterThan(20));
      for (final page in pages) {
        final cfi = source.locationFor(page.start);
        expect(cfi, startsWith('epubcfi(/6/2[ch1]!'));
        final resolved = await tester.runAsync(
          () => source.resolveLocation(cfi),
        );
        expect(resolved, page.start);
        expect(paginator.pageFor(resolved!), same(page));
      }
      // Resuming a saved CFI: resolveLocation, then the page holding it.
      final saved = await tester.runAsync(() => document.cfiFor(0, 57, 30));
      final position = (await tester.runAsync(
        () => source.resolveLocation(saved!),
      ))!;
      final page = paginator.pageFor(position)!;
      expect(compare(page.start, position), lessThanOrEqualTo(0));
      expect(compare(position, page.end), lessThan(0));
      await tester.runAsync(source.close);
    });

    testWidgets('next and previous cross chapters in reading order', (
      tester,
    ) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      final paginator = paginatorFor(source);
      final first = (await tester.runAsync(() => paginator.paginate(0)))!;
      final second = (await tester.runAsync(
        () => paginator.next(first.first),
      ))!;
      expect(second, first[1]);
      final opening = (await tester.runAsync(
        () => paginator.next(first.last),
      ))!;
      expect((opening.chapter, opening.indexInChapter), (1, 0));
      expect(
        await tester.runAsync(() => paginator.previous(opening)),
        first.last,
      );
      expect(
        await tester.runAsync(() => paginator.previous(first[1])),
        first.first,
      );
      expect(
        await tester.runAsync(() => paginator.previous(first.first)),
        null,
      );
      final last = (await tester.runAsync(() => paginator.paginate(4)))!;
      expect(await tester.runAsync(() => paginator.next(last.last)), null);
    });
  });

  group('repagination', () {
    testWidgets('a typography change keeps the first words on the page', (
      tester,
    ) async {
      final document = LibraryTextDocument.fromText(sampleText());
      final source = LibraryTextReflowSource(document);
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(2)))!;
      final shown = pages[pages.length ~/ 2];
      final start = shown.start;
      final text = document.blocks[400 + start.block].text;
      final firstWord = text.substring(start.offset).split(' ').first;
      expect(firstWord, isNotEmpty);

      // A theme only: same pages, painted in other colours.
      expect(
        paginator.update(
          style: LibraryReflowStyle.of(
            const LibraryReaderSettings(),
            LibraryReaderPalette.black,
          ),
        ),
        isTrue, // the default settings are 18 px: a relayout
      );
      final relaid = (await tester.runAsync(() => paginator.locate(start)))!;
      expect(
        paginator.update(
          style: LibraryReflowStyle.of(
            const LibraryReaderSettings(),
            LibraryReaderPalette.sepia,
          ),
        ),
        isFalse,
      );
      expect(paginator.pageFor(start), same(relaid));

      for (final style in <LibraryReflowStyle>[
        LibraryReflowStyle.of(
          const LibraryReaderSettings(fontSize: 26, lineHeight: 1.8),
          LibraryReaderPalette.light,
        ),
        LibraryReflowStyle.of(
          const LibraryReaderSettings(fontSize: 14, margin: 40, justify: false),
          LibraryReaderPalette.light,
        ),
      ]) {
        expect(paginator.update(style: style), isTrue);
        expect(paginator.pageCountOf(2), isNull);
        expect(paginator.pageFor(start), isNull);
        final page = (await tester.runAsync(() => paginator.locate(start)))!;
        expect(compare(page.start, start), lessThanOrEqualTo(0));
        expect(compare(start, page.end), lessThan(0));
        // The first word of the page shown is still whole on it.
        expect(
          compare(
            LibraryReflowPosition(
              2,
              start.block,
              start.offset + firstWord.length,
            ),
            page.end,
          ),
          lessThanOrEqualTo(0),
        );
        expect(paginator.textOf(page), contains(firstWord));
      }
    });

    testWidgets('a rotation keeps the first words on the page', (tester) async {
      final document = await openEpub(
        tester,
        buildEpub3(
          chapter1: xhtml(
            List<String>.generate(
              80,
              (i) =>
                  '<p>Paragraph $i ${List<String>.filled(30, 'v$i').join(' ')}</p>',
            ).join(),
          ),
        ),
      );
      final source = LibraryEpubReflowSource(document);
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
      final shown = pages[pages.length * 2 ~/ 3];
      final start = shown.start;
      final blocks = source.loadedChapter(0)!;
      final firstWord = blocks[start.block].text
          .substring(start.offset)
          .split(' ')
          .first;
      // Landscape, then a narrow portrait.
      for (final (size, padding) in <(Size, EdgeInsets)>[
        (const Size(800, 360), const EdgeInsets.fromLTRB(60, 16, 60, 16)),
        (const Size(320, 640), const EdgeInsets.fromLTRB(12, 40, 12, 30)),
      ]) {
        expect(paginator.update(pageSize: size, padding: padding), isTrue);
        final page = (await tester.runAsync(() => paginator.locate(start)))!;
        expect(page.size, size);
        expect(compare(page.start, start), lessThanOrEqualTo(0));
        expect(
          compare(
            LibraryReflowPosition(
              0,
              start.block,
              start.offset + firstWord.length,
            ),
            page.end,
          ),
          lessThanOrEqualTo(0),
        );
        expect(paginator.textOf(page), contains(firstWord));
        final all = (await tester.runAsync(() => paginator.paginate(0)))!;
        expectCoversChapter(
          all,
          libraryReflowUnits(0, blocks),
          chapter: 0,
          area: padding.deflateRect(Offset.zero & size),
        );
      }
      await tester.runAsync(source.close);
    });

    testWidgets('invalidate() drops the memoized pages', (tester) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(1)))!;
      // Memoized: the same list, no new pagination.
      final turns = paginator.statsOf(1)!.turns;
      expect(await tester.runAsync(() => paginator.paginate(1)), same(pages));
      expect(paginator.statsOf(1)!.turns, turns);
      expect(paginator.pageCountOf(1), pages.length);

      paginator.invalidate();
      expect(paginator.pageCountOf(1), isNull);
      expect(paginator.pageFor(pages[3].start), isNull);
      expect(paginator.pageAt(1, 0), isNull);
      final again = (await tester.runAsync(() => paginator.paginate(1)))!;
      expect(again, isNot(same(pages)));
      expect(again.first == pages.first, isFalse);
      // Same settings, same pages.
      expect(
        again.map((page) => page.start).toList(),
        pages.map((page) => page.start).toList(),
      );
    });
  });

  group('images', () {
    testWidgets('a tall image starts a page, alone, at 0.85 of its height', (
      tester,
    ) async {
      final document = await openEpub(
        tester,
        buildEpub3(
          chapter1: xhtml(
            '<h1>Pictures</h1>'
            '<p>Short paragraph 0.</p><p>Short paragraph 1.</p>'
            '<p>Short paragraph 2.</p>'
            '<p><img src="../images/tall.png" alt="Tall"/></p>'
            '<p>After the tall picture, a paragraph long enough to wrap.</p>'
            '<p><img src="../images/missing.png"/></p>'
            '<p>The end.</p>',
          ),
          extra: <FixtureZipEntry>[
            FixtureZipEntry(
              'OEBPS/images/tall.png',
              buildPng(40, 600),
              deflate: false,
            ),
          ],
        ),
      );
      final source = LibraryEpubReflowSource(document);
      const size = Size(360, 600);
      const padding = EdgeInsets.fromLTRB(16, 30, 16, 30);
      final paginator = paginatorFor(source, pageSize: size, padding: padding);
      final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
      final blocks = source.loadedChapter(0)!;
      expectCoversChapter(
        pages,
        libraryReflowUnits(0, blocks),
        chapter: 0,
        area: padding.deflateRect(Offset.zero & size),
      );
      final tallBlock = blocks.indexWhere(
        (block) => block.imageHref?.endsWith('tall.png') ?? false,
      );
      final index = pages.indexWhere(
        (page) => page.slices.any((slice) => slice.unit.block == tallBlock),
      );
      expect(index, greaterThan(0));
      final page = pages[index];
      // A page of its own, from the top of the text area.
      expect(page.slices, hasLength(1));
      expect(page.start, LibraryReflowPosition(0, tallBlock, 0));
      final image = page.slices.single;
      expect(image.kind, LibraryReflowSliceKind.image);
      expect(image.imageFailed, isFalse);
      expect(image.rect.top, padding.top);
      expect(image.rect.height, closeTo(size.height * 0.85, 0.01));
      expect(image.rect.width, size.width - padding.horizontal);
      // It did not fit below the text of the previous page.
      final above = pages[index - 1].slices.last.rect.bottom;
      expect(
        above + 8 + image.rect.height,
        greaterThan(size.height - padding.bottom),
      );
      // A missing image keeps the scroll view's 48 px placeholder.
      final missing = pages
          .expand((page) => page.slices)
          .singleWhere((slice) => slice.imageFailed);
      expect(missing.rect.height, 48);
      expect(paginator.textOf(page), 'Tall');

      // Painted once decoded: the picture, fitted, on the page colour.
      await tester.runAsync(() => paginator.prepare(page));
      final (data, width, _) = await pixelsOf(
        tester,
        paginator.paint(page),
        size,
      );
      final centre = image.rect.center;
      final pixel = pixelAt(data, width, centre.dx.round(), centre.dy.round());
      expect((pixel >> 16) & 0xFF, closeTo(200, 2));
      expect((pixel >> 8) & 0xFF, closeTo(80, 2));
      expect(
        pixelAt(data, width, image.rect.left.round() + 4, centre.dy.round()),
        LibraryReaderPalette.light.background.toARGB32(),
      );
      await tester.runAsync(source.close);
    });
  });

  group('frame budget', () {
    testWidgets('pagination yields to the event loop as its budget is spent', (
      tester,
    ) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      Future<(List<LibraryReflowPageSpec>, int)> paginateCountingTurns(
        LibraryReflowPaginator paginator,
      ) async => (await tester.runAsync(() async {
        // Another task of the event loop: it runs whenever pagination
        // gives the loop back.
        var ticks = 0;
        var running = true;
        void tick() {
          if (!running) return;
          ticks++;
          Timer.run(tick);
        }

        Timer.run(tick);
        final pages = await paginator.paginate(0);
        running = false;
        return (pages, ticks);
      }))!;

      // No budget: one unit per turn, the loop runs between each.
      final eager = paginatorFor(source, frameBudget: Duration.zero);
      final (pages, ticks) = await paginateCountingTurns(eager);
      final stats = eager.statsOf(0)!;
      expect(stats.complete, isTrue);
      expect(stats.units, 200);
      expect(stats.turns, stats.units);
      expect(ticks, greaterThanOrEqualTo(stats.turns - 1));
      expect(stats.pages, pages.length);

      // A budget longer than the chapter: one turn, nothing else ran.
      final patient = paginatorFor(
        source,
        frameBudget: const Duration(hours: 1),
      );
      final (again, none) = await paginateCountingTurns(patient);
      expect(none, 0);
      expect(patient.statsOf(0)!.turns, 1);
      expect(
        again.map((page) => page.start).toList(),
        pages.map((page) => page.start).toList(),
      );
    });

    testWidgets('locate() answers before the chapter is finished', (
      tester,
    ) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      final paginator = paginatorFor(source, frameBudget: Duration.zero);
      await tester.runAsync(() async {
        final page = await paginator.locate(
          const LibraryReflowPosition(3, 2, 10),
        );
        expect(
          compare(page.start, const LibraryReflowPosition(3, 2, 10)),
          lessThanOrEqualTo(0),
        );
        expect(
          compare(const LibraryReflowPosition(3, 2, 10), page.end),
          lessThan(0),
        );
        // The rest of the chapter is still being laid out.
        expect(paginator.pageCountOf(3), isNull);
        expect(paginator.statsOf(3)!.units, lessThan(20));
        final pages = await paginator.paginate(3);
        expect(pages[page.indexInChapter], same(page));
      });
    });

    testWidgets('cancel() stops a running pagination', (tester) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      final paginator = paginatorFor(source, frameBudget: Duration.zero);
      await tester.runAsync(() async {
        final whole = paginator.paginate(0);
        final late = paginator.locate(const LibraryReflowPosition(0, 190, 0));
        for (var i = 0; i < 5; i++) {
          await Future<void>.delayed(Duration.zero);
        }
        expect(paginator.statsOf(0)!.units, inExclusiveRange(0, 200));
        await paginator.cancel();
        final stopped = paginator.statsOf(0)!;
        expect(stopped.cancelled, isTrue);
        for (var i = 0; i < 20; i++) {
          await Future<void>.delayed(Duration.zero);
        }
        // Not one more unit laid out.
        expect(paginator.statsOf(0)!.units, stopped.units);
        await expectLater(
          whole,
          throwsA(isA<LibraryReflowPaginationCancelled>()),
        );
        await expectLater(
          late,
          throwsA(isA<LibraryReflowPaginationCancelled>()),
        );
        expect(paginator.pageCountOf(0), isNull);
        // A new request starts over and completes.
        final pages = await paginator.paginate(0);
        expect(paginator.pageCountOf(0), pages.length);
        expect(paginator.statsOf(0)!.units, 200);
      });
    });

    testWidgets('a relayout cancels the pagination of the old layout', (
      tester,
    ) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      final paginator = paginatorFor(source, frameBudget: Duration.zero);
      await tester.runAsync(() async {
        final old = paginator.paginate(1);
        await Future<void>.delayed(Duration.zero);
        expect(paginator.update(pageSize: const Size(560, 360)), isTrue);
        await expectLater(
          old,
          throwsA(isA<LibraryReflowPaginationCancelled>()),
        );
        final pages = await paginator.paginate(1);
        expect(pages.first.size, const Size(560, 360));
      });
    });
  });

  group('painting', () {
    testWidgets('paint() draws the page in the current colours', (
      tester,
    ) async {
      final source = LibraryTextReflowSource(
        LibraryTextDocument.fromText(sampleText()),
      );
      final paginator = paginatorFor(source);
      final pages = (await tester.runAsync(() => paginator.paginate(0)))!;
      final page = pages[1];
      final (data, width, height) = await pixelsOf(
        tester,
        paginator.paint(page, pixelRatio: 2),
        page.size,
        pixelRatio: 2,
      );
      expect((width, height), (720, 1120));
      final background = LibraryReaderPalette.light.background.toARGB32();
      expect(pixelAt(data, width, 2, 2), background);
      var ink = 0;
      for (var y = 0; y < height; y += 4) {
        for (var x = 0; x < width; x += 4) {
          if (pixelAt(data, width, x, y) != background) ink++;
        }
      }
      expect(ink, greaterThan(1000), reason: 'text is drawn');

      // A new theme repaints the same page without a relayout.
      expect(
        paginator.update(
          style: LibraryReflowStyle(
            palette: LibraryReaderPalette.black,
            fontSize: bookStyle.fontSize,
            lineHeight: bookStyle.lineHeight,
            fontFamily: bookStyle.fontFamily,
            justify: bookStyle.justify,
            margin: bookStyle.margin,
          ),
        ),
        isFalse,
      );
      expect(paginator.pageAt(0, 1), same(page));
      final (dark, darkWidth, _) = await pixelsOf(
        tester,
        paginator.paint(page),
        page.size,
      );
      expect(
        pixelAt(dark, darkWidth, 2, 2),
        LibraryReaderPalette.black.background.toARGB32(),
      );
    });

    testWidgets('right to left paragraphs start on the right', (tester) async {
      final source = BlocksSource(<List<LibraryTextBlock>>[
        <LibraryTextBlock>[paragraphBlock('Short')],
        <LibraryTextBlock>[
          for (var i = 0; i < 40; i++)
            paragraphBlock(List<String>.filled(20, 'rtl$i').join(' ')),
        ],
      ]);
      Future<(int, int)> inkSpan(TextDirection direction) async {
        final paginator = paginatorFor(
          source,
          style: LibraryReflowStyle.of(
            const LibraryReaderSettings(fontSize: 16, justify: false),
            LibraryReaderPalette.light,
          ),
          textDirection: direction,
        );
        final page = (await tester.runAsync(
          () => paginator.paginate(0),
        ))!.single;
        final (data, width, height) = await pixelsOf(
          tester,
          paginator.paint(page),
          page.size,
        );
        final background = LibraryReaderPalette.light.background.toARGB32();
        var left = width;
        var right = -1;
        for (var y = 0; y < height; y++) {
          for (var x = 0; x < width; x++) {
            if (pixelAt(data, width, x, y) == background) continue;
            left = math.min(left, x);
            right = math.max(right, x);
          }
        }
        // Pages stay in reading order whatever the direction.
        final pages = (await tester.runAsync(() => paginator.paginate(1)))!;
        expectCoversChapter(
          pages,
          libraryReflowUnits(1, source.chapters[1]),
          chapter: 1,
          area: phonePadding.deflateRect(Offset.zero & phonePage),
        );
        return (left, right);
      }

      final (ltrLeft, ltrRight) = await inkSpan(TextDirection.ltr);
      expect(ltrLeft, greaterThanOrEqualTo(16));
      expect(ltrRight, lessThan(phonePage.width ~/ 2));
      final (rtlLeft, rtlRight) = await inkSpan(TextDirection.rtl);
      expect(rtlLeft, greaterThan(phonePage.width ~/ 2));
      expect(rtlRight, lessThanOrEqualTo(phonePage.width - 16));
    });

    testWidgets('textOf and linkAt read the page', (tester) async {
      final document = await openEpub(tester, buildEpub3());
      final source = LibraryEpubReflowSource(document);
      final paginator = paginatorFor(source);
      final page = (await tester.runAsync(() => paginator.paginate(1)))!.single;
      expect(paginator.textOf(page), 'Chapter Two\nThird para with a link.');
      final text = page.slices.last;
      String? found;
      for (
        var y = text.rect.top + 2;
        y < text.rect.bottom && found == null;
        y += 6
      ) {
        for (var x = text.rect.left + 2; x < text.rect.right; x += 4) {
          found = paginator.linkAt(page, Offset(x, y));
          if (found != null) break;
        }
      }
      expect(found, endsWith('text/ch1.xhtml#part2'));
      // "Third" is not a link.
      expect(
        paginator.linkAt(page, text.rect.topLeft + const Offset(4, 8)),
        isNull,
      );
      await tester.runAsync(source.close);
    });
  });
}
