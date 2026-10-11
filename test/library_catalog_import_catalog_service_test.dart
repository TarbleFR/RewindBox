import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart' show getCrc32;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_catalog_import_fakes.dart';
import 'library_local_fixtures.dart'
    show FixtureZipEntry, buildEpub3, buildZip, containerXml, xhtml;

LibraryAddon _catalogAddon({bool gallica = false}) =>
    LibraryAddon.fromManifest(<String, dynamic>{
      'schema': LibraryAddon.schemaV1,
      'id': gallica ? 'user.gallica' : 'com.example.books',
      'name': 'Example Books',
      'version': '1.0.0',
      'baseUrl': 'https://example.com/api/',
      if (gallica)
        'provider': <String, dynamic>{'type': LibraryAddon.gallicaProviderType},
      'endpoints': <String, dynamic>{'catalog': 'catalog.json'},
    }, origin: 'https://example.com/manifest.json');

void main() {
  late FakeLibraryFetcher fetcher;
  late LibraryCatalogService service;

  setUp(() {
    fetcher = FakeLibraryFetcher();
    service = LibraryCatalogService.withFetcher(fetcher.call);
  });

  test('catalogue requests use the listing cache policy', () async {
    fetcher.routes['https://example.com/api/catalog.json'] = FakeRoute.json(
      <String, dynamic>{
        'items': <Map<String, dynamic>>[
          {'id': 'b1', 'title': 'Book One', 'type': 'book', 'cover': 'c/1.jpg'},
          {'id': 'broken'},
        ],
      },
    );

    final items = await service.loadCatalog(_catalogAddon());
    await service.loadCatalog(_catalogAddon(), mode: LibraryFetchMode.refresh);

    expect(items.single.title, 'Book One');
    expect(items.single.coverUrl, 'https://example.com/api/c/1.jpg');
    final first = fetcher.calls.first;
    expect(first.request.cache, same(LibraryCachePolicy.listing));
    expect(first.request.maxBytes, 12 * 1024 * 1024);
    expect(first.request.headers['Accept'], 'application/json, text/plain');
    expect(first.mode, LibraryFetchMode.cacheFirst);
    expect(fetcher.calls.last.mode, LibraryFetchMode.refresh);
  });

  test('Gallica OPDS goes through the same fetcher', () async {
    fetcher.routes['https://example.com/api/catalog.json'] = FakeRoute.text(
      '<feed xmlns="http://www.w3.org/2005/Atom"><entry><id>x</id>'
      '<title>Livre</title><link rel="http://opds-spec.org/acquisition" '
      'type="application/epub+zip" href="https://example.com/x.epub"/>'
      '</entry></feed>',
    );

    final items = await service.loadCatalog(_catalogAddon(gallica: true));

    expect(items.single.contentUrl, 'https://example.com/x.epub');
    expect(
      fetcher.calls.single.request.cache,
      same(LibraryCachePolicy.listing),
    );
    expect(
      fetcher.calls.single.request.headers['Accept'],
      contains('application/atom+xml'),
    );
  });

  test('reader content is never cached', () async {
    fetcher.routes['https://example.com/read/1.json'] = FakeRoute.json(
      <String, dynamic>{'content': 'Il était une fois.'},
    );
    final item = LibraryCatalogItem.fromJson(<String, dynamic>{
      'id': '1',
      'title': 'Story',
      'readerUrl': 'read/1.json',
    }, baseUri: Uri.parse('https://example.com/'));

    final text = await service.loadReadableText(item);

    expect(text, 'Il était une fois.');
    final request = fetcher.calls.single.request;
    expect(request.cache, same(LibraryCachePolicy.none));
    expect(request.maxBytes, 32 * 1024 * 1024);
  });

  test('failures keep their messages and expose the typed cause', () async {
    // Unknown URL: the fake answers like LibraryHttp, with notFound / 404.
    await expectLater(
      service.loadCatalog(_catalogAddon()),
      throwsA(
        isA<LibraryAddonException>()
            .having(
              (e) => e.message,
              'message',
              'example.com returned HTTP 404.',
            )
            .having(
              (e) => e.network?.kind,
              'kind',
              LibraryNetworkErrorKind.notFound,
            ),
      ),
    );

    fetcher.routes['https://example.com/api/catalog.json'] = FakeRoute.failure(
      LibraryNetworkErrorKind.offline,
    );
    await expectLater(
      service.loadCatalog(_catalogAddon()),
      throwsA(
        isA<LibraryAddonException>()
            .having(
              (e) => e.message,
              'message',
              startsWith('Unable to load example.com:'),
            )
            .having(
              (e) => e.network?.kind,
              'kind',
              LibraryNetworkErrorKind.offline,
            ),
      ),
    );

    fetcher.routes['https://example.com/api/catalog.json'] = FakeRoute.failure(
      LibraryNetworkErrorKind.tooLarge,
    );
    await expectLater(
      service.loadCatalog(_catalogAddon()),
      throwsA(
        isA<LibraryAddonException>().having(
          (e) => e.message,
          'message',
          'Library response is too large.',
        ),
      ),
    );

    fetcher.routes['https://example.com/api/catalog.json'] = FakeRoute.text(
      'not json',
    );
    await expectLater(
      service.loadCatalog(_catalogAddon()),
      throwsA(
        isA<LibraryAddonException>().having(
          (e) => e.message,
          'message',
          'Catalog endpoint did not return valid JSON.',
        ),
      ),
    );
  });

  test('metadata-only sources never reach the network', () async {
    final addon = LibraryAddon.fromManifest(<String, dynamic>{
      'schema': LibraryAddon.schemaV1,
      'id': 'aidoku.fr.example',
      'name': 'Example',
      'version': '1',
      'baseUrl': 'https://example.com/',
      'iosCompatibility': 'metadata-only',
      'provider': <String, dynamic>{'type': LibraryAddon.aidokuProviderType},
    }, origin: 'https://example.com/index.min.json');

    await expectLater(
      service.loadCatalog(addon),
      throwsA(isA<LibraryAddonException>()),
    );
    expect(fetcher.calls, isEmpty);
  });

  group('EPUB text of remote and downloaded books', () {
    const bookUrl = 'https://example.com/books/b1.epub';
    final remoteBook = LibraryCatalogItem.fromJson(<String, dynamic>{
      'id': 'b1',
      'title': 'Book',
      'readerUrl': 'books/b1.epub',
    }, baseUri: Uri.parse('https://example.com/'));
    late Directory downloads;

    setUp(() async {
      downloads = await Directory.systemTemp.createTemp('library_epub_text_');
    });

    tearDown(() async {
      try {
        await downloads.delete(recursive: true);
      } catch (_) {}
    });

    Future<String> readDownloaded(Uint8List epub) async {
      final file = File('${downloads.path}${Platform.pathSeparator}b1.epub');
      await file.writeAsBytes(epub, flush: true);
      return service.loadReadableFile(file.path);
    }

    /// EPUB whose spine lists [chapters] (name -> raw deflated entry).
    Uint8List epubWith(List<FixtureZipEntry> chapters) {
      final opf =
          '''<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>Big</dc:title></metadata>
  <manifest>
${[for (var i = 0; i < chapters.length; i++) '    <item id="c$i" href="${chapters[i].name.substring('OEBPS/'.length)}" media-type="application/xhtml+xml"/>'].join('\n')}
  </manifest>
  <spine>
${[for (var i = 0; i < chapters.length; i++) '    <itemref idref="c$i"/>'].join('\n')}
  </spine>
</package>''';
      return buildZip(<FixtureZipEntry>[
        FixtureZipEntry.text(
          'mimetype',
          'application/epub+zip',
          deflate: false,
        ),
        FixtureZipEntry.text('META-INF/container.xml', containerXml),
        FixtureZipEntry.text('OEBPS/content.opf', opf),
        ...chapters,
      ]);
    }

    /// A chapter that really expands to [size] bytes (spaces compress to
    /// almost nothing), with an honest declared size.
    FixtureZipEntry expandingChapter(String name, int size) {
      final data = Uint8List(size)..fillRange(0, size, 0x20);
      final head = utf8.encode('<html><body><p>');
      final tail = utf8.encode('end</p></body></html>');
      data.setRange(0, head.length, head);
      data.setRange(size - tail.length, size, tail);
      return FixtureZipEntry(name, data);
    }

    Matcher tooLarge() => throwsA(
      isA<LibraryAddonException>().having(
        (e) => e.message,
        'message',
        'This EPUB is too large for the integrated text reader.',
      ),
    );

    test('chapters are read in spine order, remote or downloaded', () async {
      final epub = buildEpub3();
      fetcher.routes[bookUrl] = FakeRoute.bytes(epub);

      final remote = await service.loadReadableText(remoteBook);
      final downloaded = await readDownloaded(epub);

      for (final text in <String>[remote, downloaded]) {
        expect(text.indexOf('Chapter One'), greaterThanOrEqualTo(0));
        expect(
          text.indexOf('Chapter Two'),
          greaterThan(text.indexOf('Second para.')),
        );
        expect(text, isNot(contains('Contents')));
      }
      expect(fetcher.calls.single.request.cache, same(LibraryCachePolicy.none));
    });

    test('a symbolic link entry is never decompressed', () async {
      // archive's ZipDecoder inflated every UNIX symlink entry while listing
      // the archive, without any size limit: a damaged (or huge) one made
      // the whole book unreadable.
      final epub = markAsCorruptSymlink(
        buildEpub3(
          extra: <FixtureZipEntry>[
            FixtureZipEntry.text('OEBPS/text/link', 'ch1.xhtml'),
          ],
        ),
        'OEBPS/text/link',
      );
      fetcher.routes[bookUrl] = FakeRoute.bytes(epub);

      expect(await service.loadReadableText(remoteBook), contains('Third'));
      expect(await readDownloaded(epub), contains('Third'));
    });

    test(
      'a chapter expanding beyond the per-document cap is refused',
      () async {
        final epub = epubWith(<FixtureZipEntry>[
          FixtureZipEntry.text('OEBPS/one.xhtml', xhtml('<p>Small one.</p>')),
          expandingChapter(
            'OEBPS/two.xhtml',
            LibraryCatalogService.maxEpubEntryBytes + 1024 * 1024,
          ),
        ]);
        expect(epub.length, lessThan(256 * 1024));
        fetcher.routes[bookUrl] = FakeRoute.bytes(epub);

        await expectLater(service.loadReadableText(remoteBook), tooLarge());
        await expectLater(readDownloaded(epub), tooLarge());
      },
    );

    test('the chapters of one book are capped together', () async {
      const chapterSize = 14 * 1024 * 1024;
      final count = LibraryCatalogService.maxEpubTextBytes ~/ chapterSize + 1;
      final template = expandingChapter('OEBPS/c.xhtml', chapterSize);
      final payload = ZLibCodec(raw: true, level: 6).encode(template.data);
      final crc = getCrc32(template.data);
      final epub = epubWith(<FixtureZipEntry>[
        for (var index = 0; index < count; index++)
          FixtureZipEntry(
            'OEBPS/c$index.xhtml',
            const <int>[],
            payload: payload,
            crc: crc,
            declaredSize: chapterSize,
          ),
      ]);
      expect(epub.length, lessThan(512 * 1024));
      fetcher.routes[bookUrl] = FakeRoute.bytes(epub);

      await expectLater(service.loadReadableText(remoteBook), tooLarge());
      await expectLater(readDownloaded(epub), tooLarge());
    });
  });
}
