import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:pdfrx/pdfrx.dart' show PdfException, PdfPasswordException;

import 'library_local_fixtures.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory temp;
  late FakePdfInspector pdf;
  late LibraryFileBookInspector inspector;

  setUp(() async {
    temp = await createTempDir('library_formats_');
    pdf = FakePdfInspector(
      failures: <String, LibraryBookIssue>{
        'locked.pdf': LibraryBookIssue.passwordProtected,
      },
    );
    inspector = LibraryFileBookInspector(pdfInspector: pdf);
  });

  tearDown(() async {
    if (await temp.exists()) await temp.delete(recursive: true);
  });

  Future<LibraryBookInspection> inspect(String name, List<int> bytes) async {
    final file = await writeFile(temp, name, bytes);
    return inspector.inspect(file.path);
  }

  group('detection matrix (signature, not extension)', () {
    test('EPUB, CBZ, PDF and TXT are recognised', () async {
      final epub = await inspect('book.epub', buildEpub3());
      expect(epub.issue, isNull);
      expect(epub.format, LibraryBookFormat.epub);

      final cbz = await inspect('comic.cbz', buildCbz());
      expect(cbz.issue, isNull);
      expect(cbz.format, LibraryBookFormat.cbz);

      final pdfResult = await inspect('paper.pdf', buildPdf());
      expect(pdfResult.issue, isNull);
      expect(pdfResult.format, LibraryBookFormat.pdf);
      expect(pdfResult.metadata.pageCount, 3);
      expect(pdfResult.metadata.title, 'paper');
      expect(pdfResult.coverImage, isNotNull);

      final txt = await inspect('notes.txt', utf8.encode('Hello\n\nWorld'));
      expect(txt.issue, isNull);
      expect(txt.format, LibraryBookFormat.txt);
    });

    test(
      'an EPUB renamed .zip is still an EPUB and a ZIP renamed .cbr is a CBZ',
      () async {
        final epub = await inspect('renamed.zip', buildEpub3());
        expect(epub.format, LibraryBookFormat.epub);
        final cbr = await inspect('really-zip.cbr', buildCbz());
        expect(cbr.issue, isNull);
        expect(cbr.format, LibraryBookFormat.cbz);
      },
    );

    test('RAR, 7z and MOBI are refused with their own reason', () async {
      expect(
        (await inspect('comic.cbr', buildRar())).issue,
        LibraryBookIssue.rarArchive,
      );
      final rar5 = Uint8List.fromList(<int>[
        0x52,
        0x61,
        0x72,
        0x21,
        0x1A,
        0x07,
        0x01,
        0x00,
        ...List<int>.filled(40, 0),
      ]);
      expect(
        (await inspect('comic5.cbr', rar5)).issue,
        LibraryBookIssue.rarArchive,
      );
      expect(
        (await inspect('comic.cb7', build7z())).issue,
        LibraryBookIssue.sevenZipArchive,
      );
      expect(
        (await inspect('novel.mobi', buildMobi())).issue,
        LibraryBookIssue.kindleFormat,
      );
      // Even with a misleading extension.
      expect(
        (await inspect('novel.epub', buildMobi())).issue,
        LibraryBookIssue.kindleFormat,
      );
    });

    test('garbage, empty files, folders and binary text are refused', () async {
      expect(
        (await inspect(
          'random.epub',
          List<int>.generate(4096, (i) => (i * 31 + 7) & 0xFF),
        )).issue,
        LibraryBookIssue.unsupportedFormat,
      );
      expect(
        (await inspect('empty.pdf', const <int>[])).issue,
        LibraryBookIssue.emptyFile,
      );
      expect(
        (await inspect('binary.txt', <int>[0x48, 0x00, 0x49, 0x00])).issue,
        LibraryBookIssue.unsupportedFormat,
      );
      // A text file with another extension is not a book.
      expect(
        (await inspect('readme.log', utf8.encode('plain text'))).issue,
        LibraryBookIssue.unsupportedFormat,
      );
      final folder = Directory(
        '${temp.path}${Platform.pathSeparator}Book.epub',
      );
      await folder.create();
      expect(
        (await inspector.inspect(folder.path)).issue,
        LibraryBookIssue.folder,
      );
      expect(
        (await inspector.inspect('${temp.path}/missing.epub')).issue,
        LibraryBookIssue.unreadable,
      );
    });

    test('truncated ZIP and ZIP without pages', () async {
      final cbz = buildCbz();
      final truncated = await inspect(
        'cut.cbz',
        cbz.sublist(0, cbz.length ~/ 2),
      );
      expect(truncated.issue, LibraryBookIssue.corrupt);
      final noPages = await inspect(
        'docs.zip',
        buildZip(<FixtureZipEntry>[FixtureZipEntry.text('a.txt', 'x')]),
      );
      expect(noPages.issue, LibraryBookIssue.noContent);
    });

    test('a PDF needing a password is reported by the PDF inspector', () async {
      final locked = await inspect('locked.pdf', buildPdf());
      expect(locked.format, LibraryBookFormat.pdf);
      expect(locked.issue, LibraryBookIssue.passwordProtected);
    });

    test('pdfrx errors map to typed issues', () {
      expect(
        LibraryPdfrxInspector.issueFor(const PdfPasswordException('x')),
        LibraryBookIssue.passwordProtected,
      );
      expect(
        LibraryPdfrxInspector.issueFor(const PdfException('x', 5)),
        LibraryBookIssue.drmProtected,
      );
      expect(
        LibraryPdfrxInspector.issueFor(const PdfException('x', 3)),
        LibraryBookIssue.corrupt,
      );
      expect(
        LibraryPdfrxInspector.issueFor(const PdfException('x', 2)),
        LibraryBookIssue.unreadable,
      );
      expect(
        LibraryPdfrxInspector.issueFor(StateError('x')),
        LibraryBookIssue.corrupt,
      );
    });

    test('signature helper', () {
      expect(
        libraryDetectSignature(ascii.encode('%PDF-1.7')),
        LibraryFileSignature.pdf,
      );
      final late = <int>[
        ...List<int>.filled(100, 0x20),
        ...ascii.encode('%PDF-1.4'),
      ];
      expect(
        libraryDetectSignature(late, fileName: 'x.pdf'),
        LibraryFileSignature.pdf,
      );
      expect(
        libraryDetectSignature(late, fileName: 'x.txt'),
        LibraryFileSignature.unknown,
      );
      expect(
        libraryDetectSignature(const <int>[0x50, 0x4B, 0x03, 0x04]),
        LibraryFileSignature.zip,
      );
    });
  });

  group('protection', () {
    test('EPUB with rights.xml is DRM protected', () async {
      final result = await inspect(
        'adobe.epub',
        buildEpub3(
          extra: <FixtureZipEntry>[
            FixtureZipEntry.text('META-INF/rights.xml', '<rights/>'),
          ],
        ),
      );
      expect(result.issue, LibraryBookIssue.drmProtected);
    });

    test(
      'encryption.xml listing content documents is DRM, font obfuscation is not',
      () async {
        String encryption(String algorithm, String uri) =>
            '''<?xml version="1.0"?>
<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" xmlns:enc="http://www.w3.org/2001/04/xmlenc#">
  <enc:EncryptedData>
    <enc:EncryptionMethod Algorithm="$algorithm"/>
    <enc:CipherData><enc:CipherReference URI="$uri"/></enc:CipherData>
  </enc:EncryptedData>
</encryption>''';

        final drm = await inspect(
          'lcp.epub',
          buildEpub3(
            extra: <FixtureZipEntry>[
              FixtureZipEntry.text(
                'META-INF/encryption.xml',
                encryption(
                  'http://www.w3.org/2001/04/xmlenc#aes256-cbc',
                  'OEBPS/text/ch1.xhtml',
                ),
              ),
            ],
          ),
        );
        expect(drm.issue, LibraryBookIssue.drmProtected);

        final fonts = await inspect(
          'fonts.epub',
          buildEpub3(
            extra: <FixtureZipEntry>[
              FixtureZipEntry.text(
                'META-INF/encryption.xml',
                encryption(
                  'http://www.idpf.org/2008/embedding',
                  'OEBPS/fonts/serif.otf',
                ),
              ),
            ],
          ),
        );
        expect(fonts.issue, isNull);
        expect(fonts.format, LibraryBookFormat.epub);

        final adobeFonts = await inspect(
          'adobe-fonts.epub',
          buildEpub3(
            extra: <FixtureZipEntry>[
              FixtureZipEntry.text(
                'META-INF/encryption.xml',
                encryption(
                  'http://ns.adobe.com/pdf/enc#RC',
                  'OEBPS/fonts/serif.ttf',
                ),
              ),
            ],
          ),
        );
        expect(adobeFonts.issue, isNull);
      },
    );

    test(
      'encrypted ZIP entries and unsupported compression methods are refused',
      () async {
        final encrypted = await inspect(
          'locked.cbz',
          buildCbz(
            extra: <FixtureZipEntry>[
              FixtureZipEntry(
                'pages/page13.jpg',
                utf8.encode('secret'),
                deflate: false,
                flags: 0x1,
              ),
            ],
          ),
        );
        expect(encrypted.issue, LibraryBookIssue.encryptedArchive);

        final lzma = await inspect(
          'lzma.cbz',
          buildCbz(
            extra: <FixtureZipEntry>[
              FixtureZipEntry(
                'pages/page13.jpg',
                utf8.encode('lzma'),
                deflate: false,
                method: 14,
              ),
            ],
          ),
        );
        expect(lzma.issue, LibraryBookIssue.unsupportedCompression);
      },
    );
  });

  group('ZIP reader validation', () {
    late File file;
    late LibraryZipArchive zip;

    tearDown(() => zip.close());

    test(
      'CRC mismatch and oversized expansion are corrupt, sizes are capped',
      () async {
        file = await writeFile(
          temp,
          'v.zip',
          buildZip(<FixtureZipEntry>[
            FixtureZipEntry('good.bin', List<int>.filled(1000, 5)),
            FixtureZipEntry('badcrc.bin', List<int>.filled(1000, 6), crc: 1234),
            FixtureZipEntry(
              'bomb.bin',
              List<int>.filled(100000, 0),
              declaredSize: 100,
            ),
            FixtureZipEntry('stored.bin', utf8.encode('plain'), deflate: false),
          ]),
        );
        zip = LibraryZipArchive.open(file.path);
        expect(
          zip.read(zip.find('good.bin')!, maxBytes: 4096),
          List<int>.filled(1000, 5),
        );
        expect(
          zip.read(zip.find('STORED.BIN')!, maxBytes: 4096),
          utf8.encode('plain'),
        );
        expect(
          () => zip.read(zip.find('badcrc.bin')!, maxBytes: 4096),
          throwsA(
            isA<LibraryBookException>().having(
              (e) => e.issue,
              'issue',
              LibraryBookIssue.corrupt,
            ),
          ),
        );
        expect(
          () => zip.read(zip.find('bomb.bin')!, maxBytes: 4096),
          throwsA(
            isA<LibraryBookException>().having(
              (e) => e.issue,
              'issue',
              LibraryBookIssue.corrupt,
            ),
          ),
        );
        expect(
          () => zip.read(zip.find('good.bin')!, maxBytes: 10),
          throwsA(
            isA<LibraryBookException>().having(
              (e) => e.issue,
              'issue',
              LibraryBookIssue.tooLarge,
            ),
          ),
        );
      },
    );

    test(
      'a file starting like a ZIP without central directory is corrupt',
      () async {
        file = await writeFile(temp, 'fake.zip', <int>[
          0x50,
          0x4B,
          0x03,
          0x04,
          ...List<int>.filled(70000, 1),
        ]);
        expect(
          () => LibraryZipArchive.open(file.path),
          throwsA(
            isA<LibraryBookException>().having(
              (e) => e.issue,
              'issue',
              LibraryBookIssue.corrupt,
            ),
          ),
        );
        zip = LibraryZipArchive.open(
          (await writeFile(temp, 'ok.zip', buildCbz())).path,
        );
      },
    );
  });

  group('metadata and covers', () {
    test(
      'EPUB 3: title, author role, language, series, cover-image, rtl',
      () async {
        final cover = buildPng(30, 45);
        final result = await inspect(
          'e3.epub',
          buildEpub3(cover: cover, rtl: true),
        );
        expect(result.metadata.title, 'Le Petit Livre');
        expect(result.metadata.authors, <String>['Ada Lovelace']);
        expect(result.metadata.language, 'fr');
        expect(result.metadata.series, 'Saga');
        expect(result.metadata.seriesNumber, '2');
        expect(result.metadata.rightToLeft, isTrue);
        expect(result.coverImage, cover);
      },
    );

    test(
      'EPUB 2: meta cover, then guide, then first image of the first chapter',
      () async {
        final withMeta = await inspect('e2.epub', buildEpub2());
        expect(withMeta.metadata.title, 'Old Book');
        expect(withMeta.metadata.authors, <String>['Jules Verne']);
        expect(withMeta.metadata.series, 'Voyages');
        expect(withMeta.metadata.seriesNumber, '3');
        expect(utf8.decode(withMeta.coverImage!), 'jpeg-cover-bytes');

        // Without <meta name="cover">: the guide points at a.html whose first
        // image is used ("cover" named manifest items come after the guide).
        final viaGuide = await inspect('e2b.epub', buildEpub2(metaCover: null));
        expect(viaGuide.coverImage, buildPng(4, 4));
      },
    );

    test(
      'CBZ: ComicInfo fields, right-to-left hint, natural order cover',
      () async {
        final result = await inspect('c.cbz', buildCbz());
        expect(result.metadata.title, 'The Duel');
        expect(result.metadata.series, 'Blade Saga');
        expect(result.metadata.seriesNumber, '7');
        expect(result.metadata.authors, <String>['Mika Tan', 'Rui Sato']);
        expect(result.metadata.language, 'ja');
        expect(result.metadata.rightToLeft, isTrue);
        expect(result.metadata.pageCount, 12);
        expect(utf8.decode(result.coverImage!), 'page-1-bytes');

        final plain = await inspect(
          'My Comic 01.cbz',
          buildCbz(comicInfo: false, pages: 3),
        );
        expect(plain.metadata.title, 'My Comic 01');
        expect(plain.metadata.rightToLeft, isFalse);
      },
    );

    test('natural order and junk filtering of comic pages', () async {
      final file = await writeFile(temp, 'order.cbz', buildCbz(pages: 11));
      final zip = LibraryZipArchive.open(file.path);
      addTearDown(zip.close);
      final names = libraryComicPageEntries(
        zip,
      ).map((entry) => entry.name).toList();
      expect(names, <String>[for (var i = 1; i <= 11; i++) 'pages/page$i.jpg']);
      expect(libraryNaturalCompare('Vol 2', 'vol 10'), lessThan(0));
      expect(libraryNaturalCompare('a007', 'a7'), isNot(0));
      expect(libraryNaturalCompare('ch10/p1', 'ch9/p2'), greaterThan(0));
      expect(libraryIsJunkEntry('__MACOSX/x/._p.jpg'), isTrue);
      expect(libraryIsJunkEntry('p/.DS_Store'), isTrue);
      expect(libraryIsJunkEntry('p/01.jpg'), isFalse);
    });
  });

  group('plain text', () {
    test('UTF-8, Windows-1252 fallback and UTF-16 with BOM', () async {
      final utf = await writeFile(temp, 'u.txt', utf8.encode('Café crème'));
      expect(libraryDetectTextEncodingSync(utf.path), LibraryTextEncoding.utf8);

      final latin = await writeFile(temp, 'l.txt', <int>[
        ...ascii.encode('Caf'),
        0xE9,
        0x20,
        0x93,
        0x6F,
        0x6B,
        0x94,
      ]);
      expect(
        libraryDetectTextEncodingSync(latin.path),
        LibraryTextEncoding.windows1252,
      );
      expect(
        libraryDecodeText(
          await latin.readAsBytes(),
          LibraryTextEncoding.windows1252,
        ),
        'Café “ok”',
      );

      final utf16 = await writeFile(temp, 'w.txt', <int>[
        0xFF,
        0xFE,
        0x48,
        0x00,
        0xE9,
        0x00,
      ]);
      expect(
        libraryDetectTextEncodingSync(utf16.path),
        LibraryTextEncoding.utf16le,
      );
      expect(
        libraryDecodeText(
          await utf16.readAsBytes(),
          LibraryTextEncoding.utf16le,
        ),
        'Hé',
      );

      final binary = await writeFile(temp, 'b.txt', <int>[
        0x41,
        0x01,
        0x02,
        0x03,
        0x04,
        0x05,
      ]);
      expect(libraryDetectTextEncodingSync(binary.path), isNull);
    });

    test('a UTF-8 sequence split across read chunks is still valid', () async {
      final text = '${'a' * (256 * 1024 - 1)}é and more';
      final file = await writeFile(temp, 'split.txt', utf8.encode(text));
      expect(
        libraryDetectTextEncodingSync(file.path),
        LibraryTextEncoding.utf8,
      );
    });
  });

  group('fingerprint', () {
    test(
      'same content gives the same id whatever the name; size and ends matter',
      () async {
        final a = await writeFile(temp, 'a.epub', buildEpub3());
        final b = await writeFile(temp, 'b-other-name.epub', buildEpub3());
        final c = await writeFile(temp, 'c.epub', buildEpub3(title: 'Other'));
        final fa = await libraryFingerprint(a.path);
        expect(fa, await libraryFingerprint(b.path));
        expect(fa.id, hasLength(32));
        expect(fa.value, startsWith('${await a.length()}:'));
        expect((await libraryFingerprint(c.path)).id, isNot(fa.id));
      },
    );

    test('large files hash only the first and last MiB', () async {
      final size = 3 * 1024 * 1024;
      final bytes = Uint8List(size);
      for (var i = 0; i < size; i++) {
        bytes[i] = i & 0xFF;
      }
      final original = await writeFile(temp, 'big1.pdf', bytes);
      final middle = Uint8List.fromList(bytes)..[size ~/ 2] ^= 0xFF;
      final tail = Uint8List.fromList(bytes)..[size - 1] ^= 0xFF;
      final id = (await libraryFingerprint(original.path)).id;
      expect(
        (await libraryFingerprint(
          (await writeFile(temp, 'big2.pdf', middle)).path,
        )).id,
        id,
      );
      expect(
        (await libraryFingerprint(
          (await writeFile(temp, 'big3.pdf', tail)).path,
        )).id,
        isNot(id),
      );
    });
  });

  group('engine thumbnailer', () {
    testWidgets('downscales to 360 px wide and never upscales', (tester) async {
      await tester.runAsync(() async {
        const thumbnailer = LibraryEngineThumbnailer();
        final large = await thumbnailer.createPng(buildPng(800, 1200));
        expect(large, isNotNull);
        expect(pngSize(large!), (360, 540));

        final small = await thumbnailer.createPng(buildPng(100, 150));
        expect(pngSize(small!), (100, 150));

        final tall = await thumbnailer.createPng(buildPng(400, 4000));
        expect(pngSize(tall!).$2, 720);

        expect(
          await thumbnailer.createPng(
            Uint8List.fromList(utf8.encode('not an image')),
          ),
          isNull,
        );
      });
    });
  });
}
