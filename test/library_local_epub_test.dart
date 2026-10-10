import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_epub.dart';
import 'package:neostation/services/library_local_models.dart';

import 'library_local_fixtures.dart';

LibraryEpubChapter parse(String body, {String href = 'OEBPS/text/ch1.xhtml'}) =>
    libraryParseEpubChapter(spineIndex: 0, href: href, markup: xhtml(body));

void main() {
  late Directory temp;

  setUp(() async => temp = await createTempDir('library_epub_'));
  tearDown(() async {
    if (await temp.exists()) await temp.delete(recursive: true);
  });

  group('chapter blocks', () {
    test('headings, paragraphs and inline styles', () {
      final chapter = parse(
        '<h1 id="top">Title <small>here</small></h1>'
        '<h3>Sub</h3>'
        '<p>Plain <b>bold</b> <em>italic</em> <u>under</u> x<sup>2</sup> H<sub>2</sub>O '
        '<code>code()</code> <span style="font-weight: 700; font-style: italic">both</span></p>',
      );
      expect(chapter.blocks, hasLength(3));
      final h1 = chapter.blocks[0];
      expect(h1.kind, LibraryTextBlockKind.heading);
      expect(h1.headingLevel, 1);
      expect(h1.text, 'Title here');
      expect(h1.id, 'top');
      expect(chapter.blocks[1].headingLevel, 3);

      final spans = chapter.blocks[2].spans;
      LibraryTextSpan span(String text) =>
          spans.firstWhere((s) => s.text == text);
      expect(span('bold').bold, isTrue);
      expect(span('italic').italic, isTrue);
      expect(span('under').underline, isTrue);
      expect(span('2').superscript, isTrue);
      expect(span('2').subscript, isFalse);
      expect(spans.where((s) => s.subscript).single.text, '2');
      expect(span('code()').monospace, isTrue);
      expect(span('both').bold && span('both').italic, isTrue);
      expect(
        chapter.blocks[2].text,
        'Plain bold italic under x2 H2O code() both',
      );
    });

    test(
      'whitespace collapses like HTML; br becomes a newline; script and style are ignored',
      () {
        final chapter = parse(
          '<script>var x = "hidden";</script>'
          '<p>\n   Lots   of\n\tspace   <i> here </i> and<br/>   next line<br/></p>'
          '<p>   </p>'
          '<pre>\n  keep   this\n    indentation\n</pre>',
        );
        expect(chapter.blocks, hasLength(2));
        expect(chapter.blocks[0].text, 'Lots of space here and\nnext line');
        expect(chapter.blocks[1].kind, LibraryTextBlockKind.preformatted);
        expect(chapter.blocks[1].text, '  keep   this\n    indentation');
        expect(chapter.blocks[1].spans.every((s) => s.monospace), isTrue);
        expect(chapter.blocks.any((b) => b.text.contains('hidden')), isFalse);
      },
    );

    test('an image inside a paragraph becomes its own block', () {
      final chapter = parse(
        '<p>Before <img src="../images/pic.png" alt=" A picture "/> after</p>',
      );
      expect(chapter.blocks.map((b) => b.kind).toList(), <LibraryTextBlockKind>[
        LibraryTextBlockKind.paragraph,
        LibraryTextBlockKind.image,
        LibraryTextBlockKind.paragraph,
      ]);
      expect(chapter.blocks[0].text, 'Before');
      expect(chapter.blocks[1].imageHref, 'OEBPS/images/pic.png');
      expect(chapter.blocks[1].imageAlt, 'A picture');
      expect(chapter.blocks[2].text, 'after');
      // Text before the image starts the paragraph: element path; the run
      // after the image starts at a text node (odd step).
      expect(chapter.blocks[0].cfiPath, '/4/2');
      expect(chapter.blocks[1].cfiPath, '/4/2/2');
      expect(chapter.blocks[2].cfiPath, '/4/2/3');
    });

    test('links resolve inside the archive, external links stay as written', () {
      final chapter = parse(
        '<p><a href="ch2.xhtml#note%201">internal</a> <a href="#local">same</a> '
        '<a href="https://example.org/x">web</a></p>',
      );
      final spans = chapter.blocks.single.spans;
      expect(
        spans.firstWhere((s) => s.text == 'internal').href,
        'OEBPS/text/ch2.xhtml#note%201',
      );
      expect(
        spans.firstWhere((s) => s.text == 'same').href,
        'OEBPS/text/ch1.xhtml#local',
      );
      expect(
        spans.firstWhere((s) => s.text == 'web').href,
        'https://example.org/x',
      );
    });

    test('lists, quotes, rules, centring, anchors and SVG images', () {
      final chapter = parse(
        '<section id="s1"><ol start="3"><li>three</li><li><p>four</p><p>more</p></li></ol>'
        '<ul><li>bullet <a id="mark"/>point</li></ul></section>'
        '<blockquote><p>quoted</p></blockquote>'
        '<hr/>'
        '<p class="center">middle</p>'
        '<div><svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">'
        '<image xlink:href="../images/pic.png"/></svg></div>',
      );
      final kinds = chapter.blocks.map((b) => b.kind).toList();
      expect(kinds, <LibraryTextBlockKind>[
        LibraryTextBlockKind.listItem,
        LibraryTextBlockKind.listItem,
        LibraryTextBlockKind.paragraph,
        LibraryTextBlockKind.listItem,
        LibraryTextBlockKind.quote,
        LibraryTextBlockKind.rule,
        LibraryTextBlockKind.paragraph,
        LibraryTextBlockKind.image,
      ]);
      expect(chapter.blocks[0].ordinal, 3);
      expect(chapter.blocks[1].ordinal, 4);
      expect(chapter.blocks[1].text, 'four');
      expect(chapter.blocks[2].text, 'more');
      expect(chapter.blocks[3].ordinal, isNull);
      expect(chapter.blocks[0].indent, 1);
      expect(chapter.blocks[4].indent, 1);
      expect(chapter.blocks[6].alignCenter, isTrue);
      expect(chapter.blocks[7].imageHref, 'OEBPS/images/pic.png');
      expect(chapter.anchors['s1'], 0);
      expect(chapter.anchors['mark'], 3);
      expect(chapter.characterCount, greaterThan(20));
    });

    test('malformed XHTML falls back to the lenient HTML parser', () {
      final chapter = libraryParseEpubChapter(
        spineIndex: 0,
        href: 'a.html',
        markup:
            '<html><body><p>Unclosed <b>bold<p>Next &nbsp;para &eacute;</body>',
      );
      expect(chapter.blocks.map((b) => b.text).toList(), <String>[
        'Unclosed bold',
        'Next  para é',
      ]);
    });
  });

  group('CFI', () {
    test('build and parse with escaping, ranges and assertions', () {
      final cfi = LibraryEpubCfi.build(
        spineIndex: 2,
        idref: 'ch[3]',
        blockPath: '/4/2/6',
        charOffset: 12,
      );
      expect(cfi, 'epubcfi(/6/6[ch^[3^]]!/4/2/6:12)');
      final parts = LibraryEpubCfi.parse(cfi)!;
      expect(parts.spineStep, 6);
      expect(parts.idref, 'ch[3]');
      expect(parts.steps, <int>[4, 2, 6]);
      expect(parts.offset, 12);

      final range = LibraryEpubCfi.parse(
        'epubcfi(/6/4[chap01ref]!/4[body01]/10[para05],/2/1:1,/3:4)',
      )!;
      expect(range.steps, <int>[4, 10, 2, 1]);
      expect(range.stepIds.first, 'body01');
      expect(range.offset, 1);

      final assertion = LibraryEpubCfi.parse('epubcfi(/6/4!/4/2/1:3[yy;s=b])')!;
      expect(assertion.offset, 3);

      for (final bad in <String>[
        '',
        'epubcfi()',
        'epubcfi(/6/4)',
        'cfi(/6/4!/4)',
        'epubcfi(/6/x!/4)',
        'epubcfi(/6/4!/4[unclosed)',
      ]) {
        expect(LibraryEpubCfi.parse(bad), isNull, reason: bad);
      }
    });
  });

  group('LibraryEpubDocument', () {
    late LibraryEpubDocument document;

    Future<LibraryEpubDocument> openFixture(
      List<int> bytes, [
      String name = 'book.epub',
    ]) async {
      final file = await writeFile(temp, name, bytes);
      return LibraryEpubDocument.open(file.path);
    }

    test('EPUB 3: metadata, spine, nav TOC, chapters and resources', () async {
      document = await openFixture(buildEpub3());
      addTearDown(document.close);
      expect(document.metadata.title, 'Le Petit Livre');
      expect(document.spine.map((s) => s.idref).toList(), <String>[
        'ch1',
        'ch2',
      ]);
      expect(document.spine.first.href, 'OEBPS/text/ch1.xhtml');
      expect(document.coverHref, 'OEBPS/images/cover art.png');

      expect(document.toc.map((e) => e.title).toList(), <String>[
        'Chapter One',
        'Chapter Two',
      ]);
      final part2 = document.toc.first.children.single;
      expect(part2.title, 'Part Two');
      expect(part2.spineIndex, 0);
      expect(part2.fragment, 'part2');
      expect(document.toc[1].spineIndex, 1);

      final chapter = await document.loadChapter(0);
      expect(chapter.blocks.first.kind, LibraryTextBlockKind.heading);
      expect(chapter.anchors['part2'], 2);
      expect(identical(await document.loadChapter(0), chapter), isTrue);

      final link = (await document.loadChapter(
        1,
      )).blocks[1].spans.firstWhere((s) => s.href != null).href!;
      expect(
        await document.resolveLink(link),
        const LibraryEpubLocation(0, 2, 0),
      );

      final cover = await document.resource(document.coverHref!);
      expect(pngSize(cover), (40, 60));
      final relative = await document.resource(
        '../images/pic.png',
        relativeTo: 'OEBPS/text/ch1.xhtml',
      );
      expect(pngSize(relative), (10, 10));
      await expectLater(
        document.resource('OEBPS/missing.png'),
        throwsA(isA<LibraryBookException>()),
      );
    });

    test('links with a percent-encoded fragment reach their anchor', () async {
      document = await openFixture(
        buildEpub3(
          chapter1: xhtml(
            '<h1>One</h1><p>a</p><p id="café">b</p><p id="x%41">c</p>',
          ),
          chapter2: xhtml(
            '<p><a href="ch1.xhtml#caf%C3%A9">encoded</a> '
            '<a href="ch1.xhtml#x%41">literal</a></p>',
          ),
        ),
      );
      addTearDown(document.close);
      final spans = (await document.loadChapter(
        1,
      )).blocks.single.spans.where((s) => s.href != null).toList();
      expect(
        await document.resolveLink(spans[0].href!),
        const LibraryEpubLocation(0, 2, 0),
      );
      // An id that itself contains '%' still matches as written.
      expect(
        await document.resolveLink(spans[1].href!),
        const LibraryEpubLocation(0, 3, 0),
      );
    });

    test('an image placed directly in the spine is one image block', () async {
      final page = buildPng(12, 18);
      final opf = '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Pages</dc:title></metadata>
  <manifest>
    <item id="p1" href="p1.png" media-type="image/png"/>
    <item id="t" href="t.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine><itemref idref="p1"/><itemref idref="t"/></spine>
</package>''';
      document = await openFixture(
        buildZip(<FixtureZipEntry>[
          FixtureZipEntry.text(
            'mimetype',
            'application/epub+zip',
            deflate: false,
          ),
          FixtureZipEntry.text('META-INF/container.xml', containerXml),
          FixtureZipEntry.text('OEBPS/content.opf', opf),
          FixtureZipEntry('OEBPS/p1.png', page, deflate: false),
          FixtureZipEntry.text('OEBPS/t.xhtml', xhtml('<p>End</p>')),
        ]),
        'pages.epub',
      );
      addTearDown(document.close);
      expect(document.coverHref, 'OEBPS/p1.png');
      final chapter = await document.loadChapter(0);
      expect(chapter.blocks, hasLength(1));
      expect(chapter.blocks.single.kind, LibraryTextBlockKind.image);
      expect(chapter.blocks.single.imageHref, 'OEBPS/p1.png');
      expect(await document.resource('OEBPS/p1.png'), page);
      final cfi = document.cfiForChapter(chapter, 0, 0);
      expect(
        await document.resolveCfi(cfi),
        const LibraryEpubLocation(0, 0, 0),
      );
      expect((await document.loadChapter(1)).blocks.single.text, 'End');
    });

    test('EPUB 2: NCX TOC with nesting and non-linear items', () async {
      document = await openFixture(buildEpub2());
      addTearDown(document.close);
      expect(document.spine[1].linear, isFalse);
      expect(document.toc.map((e) => e.title).toList(), <String>[
        'Start',
        'Appendix',
      ]);
      expect(document.toc.first.children.single.title, 'Inner');
      expect(document.toc.first.children.single.fragment, 'inner');
      expect(document.toc.last.spineIndex, 1);
      final chapter = await document.loadChapter(0);
      expect(chapter.blocks.first.kind, LibraryTextBlockKind.image);
      expect(chapter.blocks.first.imageHref, 'OEBPS/img/inside.png');
    });

    test('CFI round trip and tolerant resolution', () async {
      document = await openFixture(
        buildEpub3(
          chapter2: xhtml(
            '<h2>Two</h2><div><p>alpha</p><p id="beta">beta text</p><p>gamma</p></div>',
          ),
        ),
      );
      addTearDown(document.close);
      final chapter = await document.loadChapter(1);
      for (var block = 0; block < chapter.blocks.length; block++) {
        final cfi = await document.cfiFor(1, block, 2);
        expect(
          await document.resolveCfi(cfi),
          LibraryEpubLocation(1, block, 2),
          reason: cfi,
        );
      }
      final cfi = await document.cfiFor(1, 2, 4);
      expect(cfi, 'epubcfi(/6/4[ch2]!/4/4/4:4)');

      // Unknown idref: falls back to the spine step.
      expect(
        await document.resolveCfi('epubcfi(/6/4[renamed]!/4/4/4:4)'),
        const LibraryEpubLocation(1, 2, 4),
      );
      // A text node inside the block keeps its offset.
      expect(
        await document.resolveCfi('epubcfi(/6/4[ch2]!/4/4/4/1:3)'),
        const LibraryEpubLocation(1, 2, 3),
      );
      // A path that no longer exists resolves to the closest preceding block.
      expect(
        await document.resolveCfi('epubcfi(/6/4[ch2]!/4/4/5:9)'),
        const LibraryEpubLocation(1, 2, 0),
      );
      // An id assertion wins over a wrong path.
      expect(
        await document.resolveCfi('epubcfi(/6/4[ch2]!/4/40[beta]:0)'),
        const LibraryEpubLocation(1, 2, 0),
      );
      // Before every block.
      expect(
        await document.resolveCfi('epubcfi(/6/4!/2:0)'),
        const LibraryEpubLocation(1, 0, 0),
      );
      // Offsets are clamped to the block.
      expect(
        await document.resolveCfi('epubcfi(/6/4!/4/4/2:999)'),
        const LibraryEpubLocation(1, 1, 5),
      );
      // Malformed or outside the spine.
      expect(await document.resolveCfi('nonsense'), isNull);
      expect(await document.resolveCfi('epubcfi(/6/40!/4:0)'), isNull);
    });

    test('fractions grow through the book and invert', () async {
      document = await openFixture(buildEpub3());
      addTearDown(document.close);
      await document.loadChapter(0);
      await document.loadChapter(1);
      final start = document.fractionFor(const LibraryEpubLocation(0, 0, 0));
      final middle = document.fractionFor(const LibraryEpubLocation(0, 2, 3));
      final second = document.fractionFor(const LibraryEpubLocation(1, 0, 0));
      final end = document.fractionFor(const LibraryEpubLocation(1, 1, 30));
      expect(start, 0);
      expect(middle, greaterThan(start));
      expect(second, greaterThan(middle));
      expect(end, lessThanOrEqualTo(1));
      expect(end, greaterThan(second));
      expect(
        await document.locationForFraction(0),
        const LibraryEpubLocation(0, 0, 0),
      );
      final back = await document.locationForFraction((second + end) / 2);
      expect(back.spineIndex, 1);
      expect(
        document.fractionFor(back),
        moreOrLessEquals((second + end) / 2, epsilon: 0.05),
      );
    });

    test('DRM and corrupt EPUBs throw typed errors', () async {
      await expectLater(
        openFixture(
          buildEpub3(
            extra: <FixtureZipEntry>[
              FixtureZipEntry.text('META-INF/rights.xml', '<r/>'),
            ],
          ),
          'drm.epub',
        ),
        throwsA(
          isA<LibraryBookException>().having(
            (e) => e.issue,
            'issue',
            LibraryBookIssue.drmProtected,
          ),
        ),
      );
      await expectLater(
        openFixture(
          buildZip(<FixtureZipEntry>[
            FixtureZipEntry.text(
              'mimetype',
              'application/epub+zip',
              deflate: false,
            ),
            FixtureZipEntry.text('META-INF/container.xml', containerXml),
          ]),
          'nopackage.epub',
        ),
        throwsA(
          isA<LibraryBookException>().having(
            (e) => e.issue,
            'issue',
            LibraryBookIssue.corrupt,
          ),
        ),
      );
    });
  });
}
