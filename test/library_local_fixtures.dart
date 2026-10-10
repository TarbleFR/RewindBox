// Programmatic fixtures for the local library tests (no third-party books).
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart' show getCrc32;
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_models.dart';

/// One entry of a hand-built ZIP.
class FixtureZipEntry {
  FixtureZipEntry(
    this.name,
    List<int> data, {
    this.deflate = true,
    this.flags = 0,
    this.method,
    this.crc,
    this.payload,
    this.declaredSize,
  }) : data = Uint8List.fromList(data);

  FixtureZipEntry.text(String name, String text, {bool deflate = true})
    : this(name, utf8.encode(text), deflate: deflate);

  final String name;
  final Uint8List data;
  final bool deflate;

  /// Extra general purpose flags (bit 0 = encrypted).
  final int flags;

  /// Compression method written in the headers (overrides store/deflate).
  final int? method;

  /// CRC written in the headers (defaults to the real CRC of [data]).
  final int? crc;

  /// Bytes written as entry content (defaults to [data], deflated or not).
  final List<int>? payload;

  /// Uncompressed size written in the headers (defaults to [data] length).
  final int? declaredSize;
}

/// Builds a ZIP archive with local headers, central directory and EOCD.
Uint8List buildZip(List<FixtureZipEntry> entries) {
  final out = BytesBuilder();
  final central = BytesBuilder();
  void u16(BytesBuilder b, int v) => b.add(<int>[v & 0xFF, (v >> 8) & 0xFF]);
  void u32(BytesBuilder b, int v) => b.add(<int>[
    v & 0xFF,
    (v >> 8) & 0xFF,
    (v >> 16) & 0xFF,
    (v >> 24) & 0xFF,
  ]);

  for (final entry in entries) {
    final name = utf8.encode(entry.name);
    final payload =
        entry.payload ??
        (entry.deflate
            ? ZLibCodec(raw: true, level: 6).encode(entry.data)
            : entry.data);
    final method = entry.method ?? (entry.deflate ? 8 : 0);
    final crc = entry.crc ?? getCrc32(entry.data);
    final size = entry.declaredSize ?? entry.data.length;
    final flags = 0x800 | entry.flags;
    final offset = out.length;

    u32(out, 0x04034b50);
    u16(out, 20);
    u16(out, flags);
    u16(out, method);
    u16(out, 0);
    u16(out, 0x21);
    u32(out, crc);
    u32(out, payload.length);
    u32(out, size);
    u16(out, name.length);
    u16(out, 0);
    out.add(name);
    out.add(payload);

    u32(central, 0x02014b50);
    u16(central, (3 << 8) | 20);
    u16(central, 20);
    u16(central, flags);
    u16(central, method);
    u16(central, 0);
    u16(central, 0x21);
    u32(central, crc);
    u32(central, payload.length);
    u32(central, size);
    u16(central, name.length);
    u16(central, 0);
    u16(central, 0);
    u16(central, 0);
    u16(central, 0);
    u32(central, (entry.name.endsWith('/') ? 0x41ED : 0x81A4) << 16);
    u32(central, offset);
    central.add(name);
  }
  final centralOffset = out.length;
  final centralBytes = central.takeBytes();
  out.add(centralBytes);
  u32(out, 0x06054b50);
  u16(out, 0);
  u16(out, 0);
  u16(out, entries.length);
  u16(out, entries.length);
  u32(out, centralBytes.length);
  u32(out, centralOffset);
  u16(out, 0);
  return out.takeBytes();
}

/// Minimal valid RGB PNG of [width] x [height].
Uint8List buildPng(
  int width,
  int height, {
  int red = 200,
  int green = 80,
  int blue = 40,
}) {
  final raw = BytesBuilder();
  final row = Uint8List(1 + width * 3);
  for (var x = 0; x < width; x++) {
    row[1 + x * 3] = red;
    row[2 + x * 3] = green;
    row[3 + x * 3] = (blue + x) & 0xFF;
  }
  for (var y = 0; y < height; y++) {
    raw.add(row);
  }
  final out = BytesBuilder()
    ..add(<int>[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]);
  void chunk(String type, List<int> data) {
    final length = ByteData(4)..setUint32(0, data.length);
    out.add(length.buffer.asUint8List());
    final typed = <int>[...ascii.encode(type), ...data];
    out.add(typed);
    final crc = ByteData(4)..setUint32(0, getCrc32(typed));
    out.add(crc.buffer.asUint8List());
  }

  final header = ByteData(13)
    ..setUint32(0, width)
    ..setUint32(4, height)
    ..setUint8(8, 8)
    ..setUint8(9, 2)
    ..setUint8(10, 0)
    ..setUint8(11, 0)
    ..setUint8(12, 0);
  chunk('IHDR', header.buffer.asUint8List());
  chunk('IDAT', ZLibCodec().encode(raw.takeBytes()));
  chunk('IEND', const <int>[]);
  return out.takeBytes();
}

/// Width and height read from a PNG header.
(int, int) pngSize(List<int> png) {
  final data = ByteData.sublistView(Uint8List.fromList(png.sublist(16, 24)));
  return (data.getUint32(0), data.getUint32(4));
}

/// Minimal one-page PDF with a correct cross-reference table.
Uint8List buildPdf({int pages = 1}) {
  final objects = <String>[
    '<< /Type /Catalog /Pages 2 0 R >>',
    '<< /Type /Pages /Kids [${List<String>.generate(pages, (i) => '${3 + i} 0 R').join(' ')}] /Count $pages >>',
    for (var i = 0; i < pages; i++)
      '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 300] >>',
  ];
  final buffer = StringBuffer('%PDF-1.4\n');
  final offsets = <int>[];
  for (var i = 0; i < objects.length; i++) {
    offsets.add(buffer.length);
    buffer.write('${i + 1} 0 obj\n${objects[i]}\nendobj\n');
  }
  final xref = buffer.length;
  buffer.write('xref\n0 ${objects.length + 1}\n0000000000 65535 f \n');
  for (final offset in offsets) {
    buffer.write('${offset.toString().padLeft(10, '0')} 00000 n \n');
  }
  buffer.write(
    'trailer\n<< /Size ${objects.length + 1} /Root 1 0 R >>\nstartxref\n$xref\n%%EOF\n',
  );
  return Uint8List.fromList(ascii.encode(buffer.toString()));
}

const String containerXml = '''<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>''';

String xhtml(String body, {String title = 'Chapter'}) =>
    '''<?xml version="1.0" encoding="utf-8"?>
<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
<head><title>$title</title><style>p { color: red; }</style></head>
<body>$body</body>
</html>''';

/// EPUB 3 with a nav document, two chapters, a cover image and an inline
/// image.
Uint8List buildEpub3({
  String title = 'Le Petit Livre',
  String creator = 'Ada Lovelace',
  String language = 'fr',
  String? chapter1,
  String? chapter2,
  List<FixtureZipEntry> extra = const <FixtureZipEntry>[],
  bool rtl = false,
  Uint8List? cover,
}) {
  final opf =
      '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:identifier id="uid">urn:uuid:fixture</dc:identifier>
    <dc:title id="t1">$title</dc:title>
    <meta refines="#t1" property="title-type">main</meta>
    <dc:creator id="c1">$creator</dc:creator>
    <meta refines="#c1" property="role" scheme="marc:relators">aut</meta>
    <dc:creator id="c2">Illustrator Person</dc:creator>
    <meta refines="#c2" property="role" scheme="marc:relators">ill</meta>
    <dc:language>$language</dc:language>
    <meta property="belongs-to-collection" id="s1">Saga</meta>
    <meta refines="#s1" property="group-position">2</meta>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/>
    <item id="cover-img" href="images/cover%20art.png" media-type="image/png" properties="cover-image"/>
    <item id="pic" href="images/pic.png" media-type="image/png"/>
    <item id="ch1" href="text/ch1.xhtml" media-type="application/xhtml+xml"/>
    <item id="ch2" href="text/ch2.xhtml" media-type="application/xhtml+xml"/>
  </manifest>
  <spine${rtl ? ' page-progression-direction="rtl"' : ''}>
    <itemref idref="ch1"/>
    <itemref idref="ch2"/>
  </spine>
</package>''';
  final nav = xhtml('''
<nav epub:type="landmarks"><ol><li><a href="text/ch2.xhtml">Wrong list</a></li></ol></nav>
<nav epub:type="toc" id="toc"><h1>Contents</h1>
  <ol>
    <li><a href="text/ch1.xhtml">Chapter One</a>
      <ol><li><a href="text/ch1.xhtml#part2">Part <em>Two</em></a></li></ol>
    </li>
    <li><a href="text/ch2.xhtml">Chapter Two</a></li>
  </ol>
</nav>''');
  return buildZip(<FixtureZipEntry>[
    FixtureZipEntry.text('mimetype', 'application/epub+zip', deflate: false),
    FixtureZipEntry.text('META-INF/container.xml', containerXml),
    FixtureZipEntry.text('OEBPS/content.opf', opf),
    FixtureZipEntry.text('OEBPS/nav.xhtml', nav),
    FixtureZipEntry(
      'OEBPS/images/cover art.png',
      cover ?? buildPng(40, 60),
      deflate: false,
    ),
    FixtureZipEntry('OEBPS/images/pic.png', buildPng(10, 10), deflate: false),
    FixtureZipEntry.text(
      'OEBPS/text/ch1.xhtml',
      chapter1 ??
          xhtml(
            '<h1 id="c1">Chapter One</h1><p>First <em>para</em>.</p><p id="part2">Second para.</p>',
          ),
    ),
    FixtureZipEntry.text(
      'OEBPS/text/ch2.xhtml',
      chapter2 ??
          xhtml(
            '<h2>Chapter Two</h2><p>Third para with <a href="ch1.xhtml#part2">a link</a>.</p>',
          ),
    ),
    ...extra,
  ]);
}

/// EPUB 2 with an NCX and a cover declared through `<meta name="cover">`.
Uint8List buildEpub2({
  List<FixtureZipEntry> extra = const <FixtureZipEntry>[],
  String? metaCover = 'cover',
}) {
  final opf =
      '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:opf="http://www.idpf.org/2007/opf">
    <dc:title>Old Book</dc:title>
    <dc:creator opf:role="aut">Jules Verne</dc:creator>
    <dc:language>en</dc:language>
    ${metaCover == null ? '' : '<meta name="cover" content="$metaCover"/>'}
    <meta name="calibre:series" content="Voyages"/>
    <meta name="calibre:series_index" content="3.0"/>
  </metadata>
  <manifest>
    <item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml"/>
    <item id="cover" href="img/front.jpg" media-type="image/jpeg"/>
    <item id="a" href="a.html" media-type="application/xhtml+xml"/>
    <item id="b" href="b.html" media-type="application/xhtml+xml"/>
  </manifest>
  <spine toc="ncx">
    <itemref idref="a"/>
    <itemref idref="b" linear="no"/>
  </spine>
  <guide><reference type="cover" href="a.html" title="Cover"/></guide>
</package>''';
  const ncx = '''<?xml version="1.0" encoding="UTF-8"?>
<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
  <navMap>
    <navPoint id="p1" playOrder="1"><navLabel><text>Start</text></navLabel><content src="a.html"/>
      <navPoint id="p2" playOrder="2"><navLabel><text>Inner</text></navLabel><content src="a.html#inner"/></navPoint>
    </navPoint>
    <navPoint id="p3" playOrder="3"><navLabel><text>Appendix</text></navLabel><content src="b.html"/></navPoint>
  </navMap>
</ncx>''';
  return buildZip(<FixtureZipEntry>[
    FixtureZipEntry.text('mimetype', 'application/epub+zip', deflate: false),
    FixtureZipEntry.text('META-INF/container.xml', containerXml),
    FixtureZipEntry.text('OEBPS/content.opf', opf),
    FixtureZipEntry.text('OEBPS/toc.ncx', ncx),
    FixtureZipEntry('OEBPS/img/front.jpg', utf8.encode('jpeg-cover-bytes')),
    FixtureZipEntry('OEBPS/img/inside.png', buildPng(4, 4)),
    FixtureZipEntry.text(
      'OEBPS/a.html',
      xhtml(
        '<p><img src="img/inside.png" alt="x"/></p><p id="inner">Inner text</p>',
      ),
    ),
    FixtureZipEntry.text('OEBPS/b.html', xhtml('<p>Appendix</p>')),
    ...extra,
  ]);
}

/// CBZ with pages in non-natural archive order, macOS junk and ComicInfo.
Uint8List buildCbz({
  bool comicInfo = true,
  int pages = 12,
  List<FixtureZipEntry> extra = const <FixtureZipEntry>[],
  List<int> Function(int page)? pageBytes,
}) {
  final entries = <FixtureZipEntry>[
    for (var i = pages; i >= 1; i--)
      FixtureZipEntry(
        'pages/page$i.jpg',
        pageBytes?.call(i) ?? utf8.encode('page-$i-bytes'),
      ),
    FixtureZipEntry('__MACOSX/pages/._page1.jpg', utf8.encode('junk')),
    FixtureZipEntry('pages/.DS_Store', utf8.encode('junk')),
    FixtureZipEntry.text('notes.txt', 'not a page'),
    if (comicInfo)
      FixtureZipEntry.text('ComicInfo.xml', '''<?xml version="1.0"?>
<ComicInfo xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <Title>The Duel</Title>
  <Series>Blade Saga</Series>
  <Number>7</Number>
  <Writer>Mika Tan, Rui Sato</Writer>
  <LanguageISO>ja</LanguageISO>
  <Manga>YesAndRightToLeft</Manga>
</ComicInfo>'''),
    ...extra,
  ];
  return buildZip(entries);
}

/// File with a RAR 4 signature.
Uint8List buildRar() => Uint8List.fromList(<int>[
  0x52,
  0x61,
  0x72,
  0x21,
  0x1A,
  0x07,
  0x00,
  ...List<int>.filled(64, 7),
]);

/// File with a 7z signature.
Uint8List build7z() => Uint8List.fromList(<int>[
  0x37,
  0x7A,
  0xBC,
  0xAF,
  0x27,
  0x1C,
  0x00,
  0x04,
  ...List<int>.filled(64, 1),
]);

/// PalmDB file with the MOBI type/creator at offset 60.
Uint8List buildMobi() {
  final bytes = Uint8List(128);
  bytes.setRange(0, 9, ascii.encode('Fixture\x00\x00'));
  bytes.setRange(60, 68, ascii.encode('BOOKMOBI'));
  return bytes;
}

/// Fake PDF inspector: page count from the file length, cover from a PNG.
class FakePdfInspector implements LibraryPdfInspector {
  FakePdfInspector({this.failures = const <String, LibraryBookIssue>{}});

  final Map<String, LibraryBookIssue> failures;
  final List<String> inspected = <String>[];

  @override
  Future<LibraryPdfInspection> inspect(
    String path, {
    required int coverWidth,
  }) async {
    inspected.add(path);
    for (final entry in failures.entries) {
      if (path.endsWith(entry.key)) {
        throw LibraryBookException(entry.value, detail: 'fake');
      }
    }
    return LibraryPdfInspection(pageCount: 3, coverPng: buildPng(20, 30));
  }
}

/// Thumbnailer that records calls and returns a small marker PNG.
class FakeThumbnailer implements LibraryThumbnailer {
  int calls = 0;

  @override
  Future<Uint8List?> createPng(
    Uint8List encoded, {
    int maxWidth = 360,
    int maxHeight = 720,
  }) async {
    calls++;
    return buildPng(2, 3);
  }
}

/// Inspector wrapper counting the inspected file names.
class CountingInspector implements LibraryBookInspector {
  CountingInspector(this.inner);

  final LibraryBookInspector inner;
  final List<String> inspected = <String>[];

  @override
  Future<LibraryBookInspection> inspect(String path, {String? fileName}) {
    inspected.add(fileName ?? path);
    return inner.inspect(path, fileName: fileName);
  }
}

/// Creates (and registers for deletion) a temporary directory.
Future<Directory> createTempDir(String prefix) =>
    Directory.systemTemp.createTemp(prefix);

Future<File> writeFile(
  Directory directory,
  String name,
  List<int> bytes,
) async {
  final file = File('${directory.path}${Platform.pathSeparator}$name');
  await file.parent.create(recursive: true);
  await file.writeAsBytes(bytes, flush: true);
  return file;
}
