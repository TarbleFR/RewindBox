import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_catalog_import_fakes.dart';

void main() {
  late FakeLibraryFetcher fetcher;
  late LibraryAddonService addons;
  late LibraryCatalogMemoryStore store;
  late LibrarySourceCatalogService service;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    fetcher = FakeLibraryFetcher(<String, FakeRoute>{
      frenchRawIndex: FakeRoute.fixture(
        'aidoku_french_legacy_index.min.json',
        notModifiedOnRefresh: true,
      ),
      communityIndex: FakeRoute.fixture('aidoku_community_index_excerpt.json'),
    });
    addons = LibraryAddonService.forTesting();
    store = LibraryCatalogMemoryStore();
    service = LibrarySourceCatalogService(
      fetcher: fetcher.call,
      addons: addons,
      store: store,
      clock: () => DateTime.utc(2026, 10, 10, 12),
    );
  });

  LibraryAddon? installed(List<LibraryAddon> list, String id) {
    for (final addon in list) {
      if (addon.id == id) return addon;
    }
    return null;
  }

  test('activation installs only the selected sources', () async {
    final preview = await service.preview(frenchRawDirectory);

    final result = await service.activate(preview, <String>{
      'fr.lelscanfr',
      'fr.mangascantrad',
    });

    expect(result.added.map((addon) => addon.id).toSet(), <String>{
      'aidoku.fr.lelscanfr',
      'aidoku.fr.mangascantrad',
    });
    expect(result.updated, isEmpty);
    expect(result.skipped, isEmpty);

    // A fresh service instance reads what was persisted.
    final stored = await LibraryAddonService.forTesting().load();
    expect(stored.map((addon) => addon.id).toSet(), <String>{
      'aidoku.fr.lelscanfr',
      'aidoku.fr.mangascantrad',
    });

    final lelscan = installed(stored, 'aidoku.fr.lelscanfr')!;
    expect(lelscan.manifest['schema'], LibraryAddon.schemaV1);
    expect(lelscan.isAidokuRepositorySource, isTrue);
    expect(lelscan.isMetadataOnlyOnIos, isTrue);
    expect(lelscan.aidokuSourceId, 'fr.lelscanfr');
    expect(lelscan.version, '3');
    expect(lelscan.language, 'fr');
    expect(lelscan.languages, <String>['fr']);
    expect(lelscan.contentRating, 0);
    expect(lelscan.description, isEmpty);
    expect(lelscan.repositoryOrigin, frenchRawDirectory);
    expect(
      lelscan.sourceDownloadUrl,
      '${frenchRawDirectory}sources/fr.lelscanfr-v3.aix',
    );
    expect(lelscan.iconUrl, '${frenchRawDirectory}icons/fr.lelscanfr-v3.png');
    // The legacy list has no site: baseUrl only keeps the manifest valid and
    // is not reported as the website.
    expect(lelscan.baseUrl, frenchRawDirectory);
    expect(lelscan.websiteUrl, isNull);
    final provider = lelscan.manifest['provider'] as Map;
    expect(provider['type'], LibraryAddon.aidokuProviderType);
    expect(provider['sourceId'], 'fr.lelscanfr');
    expect(provider['catalogFormat'], 'aidokuLegacyIndex');

    expect(installed(stored, 'aidoku.fr.mangascantrad')!.contentRating, 1);
  });

  test('activation remembers the catalogue', () async {
    final preview = await service.preview(frenchRawDirectory);
    expect(await service.list(), isEmpty);

    final result = await service.activate(preview, <String>{'fr.sushiscan'});

    expect(result.catalogRemembered, isTrue);
    final catalogs = await service.list();
    expect(catalogs, hasLength(1));
    expect(catalogs.single.url, frenchRawDirectory);
    expect(catalogs.single.format, LibraryCatalogFormat.aidokuLegacyIndex);
    expect(catalogs.single.sourceCount, 10);
    expect(catalogs.single.documentUrl, frenchRawIndex);
    expect(store.writeCount, 1);
  });

  test('an unwritable catalogue list does not undo the activation', () async {
    final failing = LibrarySourceCatalogService(
      fetcher: fetcher.call,
      addons: addons,
      store: _FailingStore(),
    );
    final preview = await failing.preview(frenchRawDirectory);

    final result = await failing.activate(preview, <String>{'fr.lelscanfr'});

    expect(result.added.single.id, 'aidoku.fr.lelscanfr');
    expect(result.catalogRemembered, isFalse);
    expect((await addons.load()).single.id, 'aidoku.fr.lelscanfr');
    expect(await failing.list(), isEmpty);
    // Never overwrite a list that could not be read.
    await expectLater(
      failing.forget(frenchRawDirectory),
      throwsA(isA<FileSystemException>()),
    );
  });

  test('forget accepts other spellings and older origins', () async {
    // Installed by the previous importer: origin is the index file itself.
    await addons.installDocumentFromJson(
      File(
        'test/fixtures/library_catalog/aidoku_french_legacy_index.min.json',
      ).readAsStringSync(),
      origin: 'https://example.org/old/index.min.json',
    );
    final preview = await service.preview(frenchRawDirectory);
    await service.activate(preview, <String>{'fr.lelscanfr'});
    expect(await addons.load(), hasLength(10));
    expect(
      installed(await addons.load(), 'aidoku.fr.lelscanfr')!.repositoryOrigins,
      <String>[frenchRawDirectory, 'https://example.org/old/index.min.json'],
    );

    final viaDeepLink = await service.forget(
      'aidoku://addSourceList?url=$frenchRawDirectory',
      deactivateSources: true,
    );
    expect(viaDeepLink, 1);
    expect(await service.list(), isEmpty);

    final viaOldOrigin = await service.forget(
      'https://example.org/old/index.min.json',
      deactivateSources: true,
    );
    expect(viaOldOrigin, 9);
    expect(await addons.load(), isEmpty);
  });

  test('new-format activation keeps languages, rating and website', () async {
    final preview = await service.preview(communityIndex);

    await service.activate(preview, <String>{'multi.mangadex', 'en.qiscans'});

    final stored = await addons.load();
    final mangadex = installed(stored, 'aidoku.multi.mangadex')!;
    expect(mangadex.languages, hasLength(54));
    expect(mangadex.language, 'multi');
    expect(mangadex.contentRating, 1);
    expect(mangadex.websiteUrl, 'https://mangadex.org');
    expect(mangadex.baseUrl, 'https://mangadex.org');
    expect(installed(stored, 'aidoku.en.qiscans')!.altNames, <String>[
      'Qi Manga',
    ]);
  });

  test('minAppVersion and maxAppVersion never block activation', () async {
    fetcher.routes['https://example.org/versions.json'] = FakeRoute.json(
      <String, dynamic>{
        'name': 'Versions',
        'sources': <Map<String, dynamic>>[
          {
            'id': 'en.future',
            'name': 'Future',
            'version': 1,
            'languages': ['en'],
            'downloadURL': 'sources/en.future-v1.aix',
            'minAppVersion': '99.0',
          },
          {
            'id': 'en.past',
            'name': 'Past',
            'version': 1,
            'languages': ['en'],
            'downloadURL': 'sources/en.past-v1.aix',
            'maxAppVersion': '0.1',
          },
        ],
      },
    );
    final preview = await service.preview('https://example.org/versions.json');

    final result = await service.activate(preview, <String>{
      'en.future',
      'en.past',
    });

    expect(result.added, hasLength(2));
    expect(result.skipped, isEmpty);
    final future = installed(await addons.load(), 'aidoku.en.future')!;
    expect((future.manifest['provider'] as Map)['minAppVersion'], '99.0');
  });

  test('the highest version wins across catalogues', () async {
    final french = await service.preview(frenchRawDirectory);
    await service.activate(french, <String>{'fr.sushiscan'});
    expect(installed(await addons.load(), 'aidoku.fr.sushiscan')!.version, '4');

    final community = await service.preview(communityIndex);
    final upgrade = await service.activate(community, <String>{'fr.sushiscan'});
    expect(upgrade.updated.single.id, 'aidoku.fr.sushiscan');
    var sushi = installed(await addons.load(), 'aidoku.fr.sushiscan')!;
    expect(sushi.version, '8');
    expect(sushi.repositoryOrigin, communityIndex);
    expect(sushi.repositoryOrigins, <String>[
      communityIndex,
      frenchRawDirectory,
    ]);
    expect(sushi.websiteUrl, 'https://sushiscan.net');

    // Activating the older version again is refused and keeps v8.
    final downgrade = await service.activate(french, <String>{'fr.sushiscan'});
    expect(downgrade.added, isEmpty);
    expect(downgrade.updated, isEmpty);
    final skip = downgrade.skipped.single;
    expect(skip.reason, LibraryActivationSkipReason.newerVersionInstalled);
    expect(skip.offeredVersion, '4');
    expect(skip.installedVersion, '8');
    sushi = installed(await addons.load(), 'aidoku.fr.sushiscan')!;
    expect(sushi.version, '8');
    expect(sushi.repositoryOrigin, communityIndex);
  });

  test('unknown ids are skipped, nothing else is installed', () async {
    final preview = await service.preview(frenchRawDirectory);

    final result = await service.activate(preview, <String>{'fr.unknown'});

    expect(result.added, isEmpty);
    expect(
      result.skipped.single.reason,
      LibraryActivationSkipReason.notInCatalog,
    );
    expect(await addons.load(), isEmpty);
  });

  test('Tachiyomi repositories are refused with a typed reason', () async {
    fetcher.routes['https://example.com/tachi.json'] = FakeRoute.json(
      <Map<String, dynamic>>[
        {
          'name': 'Tachiyomi: Example',
          'pkg': 'eu.kanade.tachiyomi.extension.en.example',
          'apk': 'example.apk',
          'version': '1.4.1',
          'code': 1,
          'sources': [
            {'name': 'Example', 'id': '42', 'baseUrl': 'https://example.com'},
          ],
        },
      ],
    );
    final preview = await service.preview('https://example.com/tachi.json');

    await expectLater(
      service.activate(preview, <String>{'42'}),
      throwsA(
        isA<LibraryCatalogException>().having(
          (error) => error.kind,
          'kind',
          LibraryCatalogErrorKind.notActivatable,
        ),
      ),
    );
    expect(await addons.load(), isEmpty);
    expect(await service.list(), isEmpty);
  });

  test('a NeoStation manifest activates that single manifest', () async {
    fetcher.routes['https://example.com/manifest.json'] = FakeRoute.json(
      <String, dynamic>{
        'schema': LibraryAddon.schemaV1,
        'id': 'com.example.books',
        'name': 'Example Books',
        'version': '1.0.0',
        'baseUrl': 'https://example.com/api/',
        'endpoints': <String, dynamic>{'catalog': 'catalog.json'},
      },
    );
    final preview = await service.preview('https://example.com/manifest.json');

    final result = await service.activate(preview, <String>{
      'com.example.books',
    });

    expect(result.added.single.id, 'com.example.books');
    final stored = await addons.load();
    expect(stored.single.canBrowseOnIos, isTrue);
    expect(stored.single.origin, 'https://example.com/manifest.json');
  });

  test('deactivate removes only that source', () async {
    final preview = await service.preview(frenchRawDirectory);
    await service.activate(preview, <String>{'fr.lelscanfr', 'fr.sushiscan'});

    expect(await service.deactivate('aidoku.fr.lelscanfr'), isTrue);
    expect(await service.deactivate('aidoku.fr.lelscanfr'), isFalse);

    final stored = await addons.load();
    expect(stored.map((addon) => addon.id), <String>['aidoku.fr.sushiscan']);
    expect(await service.list(), hasLength(1));

    // Re-activating brings the same add-on id back (favourites and progress
    // are keyed by the Aidoku source id elsewhere).
    final again = await service.activate(preview, <String>{'fr.lelscanfr'});
    expect(again.added.single.id, 'aidoku.fr.lelscanfr');
  });

  test('forget keeps sources unless asked to deactivate them', () async {
    final french = await service.preview(frenchRawDirectory);
    await service.activate(french, <String>{'fr.lelscanfr', 'fr.sushiscan'});
    final community = await service.preview(communityIndex);
    await service.activate(community, <String>{'fr.bigsolo', 'fr.sushiscan'});
    expect(await service.list(), hasLength(2));

    expect(await service.forget(communityIndex), 0);
    expect(await service.list(), hasLength(1));
    expect(await addons.load(), hasLength(3));

    // Remember it again, then forget it with its sources.
    await service.remember(community);
    final removed = await service.forget(
      communityIndex,
      deactivateSources: true,
    );

    // fr.bigsolo and fr.sushiscan (v8, activated from the community list)
    // are removed; fr.lelscanfr from the French list stays.
    expect(removed, 2);
    final stored = await addons.load();
    expect(stored.map((addon) => addon.id), <String>['aidoku.fr.lelscanfr']);
    expect((await service.list()).single.url, frenchRawDirectory);
  });

  test('forget only drops a secondary origin from shared sources', () async {
    final community = await service.preview(communityIndex);
    await service.activate(community, <String>{'fr.sushiscan'});
    final french = await service.preview(frenchRawDirectory);
    // v4 is older: skipped, but the French list is recorded as an origin.
    await service.activate(french, <String>{'fr.sushiscan'});
    expect(
      installed(await addons.load(), 'aidoku.fr.sushiscan')!.repositoryOrigins,
      <String>[communityIndex, frenchRawDirectory],
    );

    final removed = await service.forget(
      frenchRawDirectory,
      deactivateSources: true,
    );

    expect(removed, 0);
    final sushi = installed(await addons.load(), 'aidoku.fr.sushiscan')!;
    expect(sushi.repositoryOrigins, <String>[communityIndex]);
    expect(sushi.version, '8');
  });

  test('refresh revalidates a remembered catalogue conditionally', () async {
    final first = await service.preview(frenchRawDirectory);
    await service.activate(first, <String>{'fr.lelscanfr'});
    fetcher.calls.clear();

    final refreshed = await service.preview(frenchRawDirectory, refresh: true);

    final call = fetcher.calls.first;
    expect(call.url, frenchRawIndex);
    expect(call.mode, LibraryFetchMode.refresh);
    expect(call.request.cache, same(LibraryCachePolicy.catalogIndex));
    expect(refreshed.notModified, isTrue);
    expect(refreshed.sources, hasLength(10));
    expect(refreshed.sourceById('fr.lelscanfr')!.alreadyInstalled, isTrue);
    final stored = (await service.list()).single;
    expect(stored.lastFetchedAt, refreshed.fetchedAt);
    expect(stored.lastFetchedAt, isNot(first.fetchedAt));
  });

  test('refresh tries the document that answered last time first', () async {
    const pagesIndex =
        'https://moomooo95.github.io/aidoku-french-sources/index.json';
    fetcher.routes[pagesIndex] = FakeRoute.fixture(
      'aidoku_french_legacy_index.min.json',
    );
    final preview = await service.preview(
      'https://moomooo95.github.io/aidoku-french-sources/',
    );
    expect(fetcher.urls, <String>[
      'https://moomooo95.github.io/aidoku-french-sources/index.min.json',
      pagesIndex,
    ]);
    await service.remember(preview);
    fetcher.calls.clear();

    await service.preview(
      'https://moomooo95.github.io/aidoku-french-sources/',
      refresh: true,
    );

    expect(fetcher.urls, <String>[pagesIndex]);
  });

  test('a local Aidoku list with absolute URLs activates', () async {
    final preview = await service.previewDocument(
      utf8.encode(
        jsonEncode(<Map<String, dynamic>>[
          {
            'id': 'fr.absolute',
            'name': 'Absolute',
            'file': 'https://cdn.example.org/list/sources/fr.absolute-v2.aix',
            'lang': 'fr',
            'version': 2,
          },
        ]),
      ),
      fileName: 'list.json',
    );

    final result = await service.activate(preview, <String>{'fr.absolute'});

    final addon = result.added.single;
    expect(addon.repositoryOrigin, 'file:list.json');
    expect(
      addon.sourceDownloadUrl,
      'https://cdn.example.org/list/sources/fr.absolute-v2.aix',
    );
    expect(addon.baseUrl, 'https://cdn.example.org/list/sources/');
    expect(addon.websiteUrl, isNull);
    // A local file cannot be refreshed: it is not remembered.
    expect(result.catalogRemembered, isFalse);
    expect(await service.list(), isEmpty);
  });

  test('concurrent activations are serialised and all persisted', () async {
    final preview = await service.preview(frenchRawDirectory);

    await Future.wait(<Future<LibraryActivationResult>>[
      service.activate(preview, <String>{'fr.lelscanfr'}),
      service.activate(preview, <String>{'fr.sushiscan'}),
      service.activate(preview, <String>{'fr.phenixscans'}),
    ]);

    final stored = await LibraryAddonService.forTesting().load();
    expect(stored.map((addon) => addon.id).toSet(), <String>{
      'aidoku.fr.lelscanfr',
      'aidoku.fr.sushiscan',
      'aidoku.fr.phenixscans',
    });
    expect(await service.list(), hasLength(1));
  });

  group('catalogue file store', () {
    late Directory directory;

    setUp(() async {
      directory = await Directory.systemTemp.createTemp('neostation_catalogs');
    });

    tearDown(() async {
      if (await directory.exists()) await directory.delete(recursive: true);
    });

    test('round-trips remembered catalogues atomically', () async {
      final fileStore = LibraryCatalogFileStore(
        directory: () async => directory,
      );
      final catalogs = <LibraryStoredCatalog>[
        LibraryStoredCatalog(
          url: frenchRawDirectory,
          format: LibraryCatalogFormat.aidokuLegacyIndex,
          lastFetchedAt: DateTime.utc(2026, 10, 10, 12),
          sourceCount: 10,
          documentUrl: frenchRawIndex,
          addedAt: DateTime.utc(2026, 10, 9),
        ),
        LibraryStoredCatalog(
          url: communityIndex,
          name: 'Aidoku Community Sources',
          format: LibraryCatalogFormat.aidokuIndex,
          lastFetchedAt: DateTime.utc(2026, 10, 10, 13),
          sourceCount: 138,
        ),
      ];

      await fileStore.write(catalogs);
      final read = await LibraryCatalogFileStore(
        directory: () async => directory,
      ).read();

      expect(File('${directory.path}/catalogs.json.tmp').existsSync(), isFalse);
      expect(read, hasLength(2));
      expect(read.first.url, frenchRawDirectory);
      expect(read.first.name, isNull);
      expect(read.first.documentUrl, frenchRawIndex);
      expect(read.first.addedAt, DateTime.utc(2026, 10, 9));
      expect(read.last.name, 'Aidoku Community Sources');
      expect(read.last.format, LibraryCatalogFormat.aidokuIndex);
      expect(read.last.sourceCount, 138);
    });

    test('a corrupt file reads as empty and is kept aside', () async {
      final file = File('${directory.path}/catalogs.json');
      await file.writeAsString('{not json');

      final read = await LibraryCatalogFileStore(
        directory: () async => directory,
      ).read();

      expect(read, isEmpty);
      expect(File('${file.path}.corrupt').readAsStringSync(), '{not json');
    });

    test('the service persists through the file store', () async {
      final persistent = LibrarySourceCatalogService(
        fetcher: fetcher.call,
        addons: addons,
        store: LibraryCatalogFileStore(directory: () async => directory),
      );
      final preview = await persistent.preview(frenchRawDirectory);
      await persistent.activate(preview, <String>{'fr.lelscanfr'});

      final reopened = LibrarySourceCatalogService(
        fetcher: fetcher.call,
        addons: addons,
        store: LibraryCatalogFileStore(directory: () async => directory),
      );
      final catalogs = await reopened.list();
      expect(catalogs.single.url, frenchRawDirectory);
      expect(catalogs.single.sourceCount, 10);
    });
  });
}

/// Store whose file can be neither read nor written.
class _FailingStore implements LibraryCatalogStore {
  @override
  Future<List<LibraryStoredCatalog>> read() async =>
      throw const FileSystemException('read failed', 'catalogs.json');

  @override
  Future<void> write(List<LibraryStoredCatalog> catalogs) async =>
      throw const FileSystemException('write failed', 'catalogs.json');
}
