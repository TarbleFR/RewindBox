import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

import 'library_catalog_import_fakes.dart';

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
}
