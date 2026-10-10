import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart' show sha256;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'library_catalog_import_fakes.dart';

void main() {
  late FakeLibraryFetcher fetcher;
  late LibraryAddonService addons;
  late LibrarySourceCatalogService service;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    fetcher = FakeLibraryFetcher();
    addons = LibraryAddonService.forTesting();
    service = LibrarySourceCatalogService(
      fetcher: fetcher.call,
      addons: addons,
      store: LibraryCatalogMemoryStore(),
      clock: () => DateTime.utc(2026, 10, 10, 12),
    );
  });

  TypeMatcher<LibraryCatalogException> catalogError(
    LibraryCatalogErrorKind kind,
  ) => isA<LibraryCatalogException>().having(
    (error) => error.kind,
    'kind',
    kind,
  );

  group('Aidoku legacy index (French list)', () {
    test(
      'directory URL with trailing slash resolves files against the index',
      () async {
        fetcher.routes[frenchRawIndex] = FakeRoute.fixture(
          'aidoku_french_legacy_index.min.json',
        );

        final preview = await service.preview('  $frenchRawDirectory  ');

        expect(fetcher.urls.first, frenchRawIndex);
        expect(
          fetcher.calls.first.request.cache,
          same(LibraryCachePolicy.catalogIndex),
        );
        expect(fetcher.calls.first.mode, LibraryFetchMode.cacheFirst);
        expect(preview.format, LibraryCatalogFormat.aidokuLegacyIndex);
        expect(preview.name, isNull);
        expect(preview.inputUrl, frenchRawDirectory);
        expect(preview.catalogUrl, frenchRawDirectory);
        expect(preview.documentUrl, frenchRawIndex);
        expect(preview.resolvedUrl, frenchRawIndex);
        expect(preview.sources, hasLength(10));

        final lelscan = preview.sourceById('fr.lelscanfr')!;
        expect(lelscan.addonId, 'aidoku.fr.lelscanfr');
        expect(lelscan.name, 'LelscanFR');
        expect(lelscan.version, 3);
        expect(lelscan.languages, <String>['fr']);
        expect(lelscan.contentRating, 0);
        expect(
          lelscan.downloadUrl,
          '${frenchRawDirectory}sources/fr.lelscanfr-v3.aix',
        );
        expect(
          lelscan.iconUrl,
          '${frenchRawDirectory}icons/fr.lelscanfr-v3.png',
        );
        // Legacy lists do not publish the site; the repository folder must
        // not be presented as one.
        expect(lelscan.websiteUrl, isNull);
        expect(lelscan.activatable, isTrue);
        expect(lelscan.alreadyInstalled, isFalse);

        final ratings = {
          for (final entry in preview.sources) entry.id: entry.contentRating,
        };
        expect(ratings['fr.mangascan'], 1);
        expect(ratings['fr.mangascantrad'], 1);
        expect(ratings.values.where((rating) => rating == 0), hasLength(8));
      },
    );

    test('preview never installs anything', () async {
      fetcher.routes[frenchRawIndex] = FakeRoute.fixture(
        'aidoku_french_legacy_index.min.json',
      );

      await service.preview(frenchRawDirectory);

      expect(await addons.load(), isEmpty);
      expect(await service.list(), isEmpty);
    });

    test(
      'GitHub Pages directory without trailing slash keeps the directory',
      () async {
        const pagesIndex =
            'https://moomooo95.github.io/aidoku-french-sources/index.min.json';
        fetcher.routes[pagesIndex] = FakeRoute.fixture(
          'aidoku_french_legacy_index.min.json',
        );

        final preview = await service.preview(
          'https://moomooo95.github.io/aidoku-french-sources',
        );

        expect(fetcher.urls.first, pagesIndex);
        expect(
          preview.catalogUrl,
          'https://moomooo95.github.io/aidoku-french-sources',
        );
        // Not https://moomooo95.github.io/sources/... (HTTP 404 upstream).
        expect(
          preview.sourceById('fr.sushiscan')!.downloadUrl,
          'https://moomooo95.github.io/aidoku-french-sources/sources/fr.sushiscan-v4.aix',
        );
      },
    );

    test(
      'relative files resolve against the final URL after a redirect',
      () async {
        fetcher.routes['https://example.org/list/index.min.json'] =
            FakeRoute.fixture(
              'aidoku_french_legacy_index.min.json',
              finalUri: Uri.parse(
                'https://cdn.example.net/mirror/v2/index.min.json',
              ),
            );

        final preview = await service.preview('https://example.org/list');

        expect(preview.documentUrl, 'https://example.org/list/index.min.json');
        expect(
          preview.resolvedUrl,
          'https://cdn.example.net/mirror/v2/index.min.json',
        );
        expect(preview.catalogUrl, 'https://example.org/list');
        expect(
          preview.sourceById('fr.astralmanga')!.downloadUrl,
          'https://cdn.example.net/mirror/v2/sources/fr.astralmanga-v5.aix',
        );
        expect(
          preview.sourceById('fr.astralmanga')!.iconUrl,
          'https://cdn.example.net/mirror/v2/icons/fr.astralmanga-v5.png',
        );
      },
    );

    test(
      'directory falls back to index.json when index.min.json is missing',
      () async {
        fetcher.routes['https://example.org/repo/index.json'] =
            FakeRoute.fixture('aidoku_french_legacy_index.min.json');

        final preview = await service.preview('https://example.org/repo/');

        expect(fetcher.urls, <String>[
          'https://example.org/repo/index.min.json',
          'https://example.org/repo/index.json',
        ]);
        expect(preview.documentUrl, 'https://example.org/repo/index.json');
        expect(
          preview.sourceById('fr.phenixscans')!.downloadUrl,
          'https://example.org/repo/sources/fr.phenixscans-v5.aix',
        );
      },
    );

    test('Aidoku deep links and the aidoku.app page are unwrapped', () async {
      fetcher.routes[frenchRawIndex] = FakeRoute.fixture(
        'aidoku_french_legacy_index.min.json',
      );

      final fromScheme = await service.preview(
        'aidoku://addSourceList?url=$frenchRawDirectory',
      );
      final fromPage = await service.preview(
        'https://aidoku.app/add-source-list/?url=$frenchRawDirectory',
      );
      final fromEncoded = await service.preview(
        'aidoku://addSourceList?url=${Uri.encodeQueryComponent(frenchRawDirectory)}',
      );

      for (final preview in [fromScheme, fromPage, fromEncoded]) {
        expect(preview.catalogUrl, frenchRawDirectory);
        expect(preview.sources, hasLength(10));
      }
      expect(fetcher.urls.toSet(), <String>{frenchRawIndex});
    });

    test('GitHub repository page tries the known index locations', () async {
      fetcher.routes[frenchRawIndex] = FakeRoute.fixture(
        'aidoku_french_legacy_index.min.json',
      );

      final preview = await service.preview(
        'https://github.com/Moomooo95/aidoku-french-sources',
      );

      expect(fetcher.urls, <String>[frenchRawIndex]);
      expect(
        preview.catalogUrl,
        'https://github.com/Moomooo95/aidoku-french-sources',
      );
      expect(
        preview.sourceById('fr.mangasorigines')!.downloadUrl,
        '${frenchRawDirectory}sources/fr.mangasorigines-v7.aix',
      );
    });

    test('unknown GitHub repository tries repo, gh-pages, main, master', () async {
      const found =
          'https://raw.githubusercontent.com/someone/aidoku-list/gh-pages/index.min.json';
      fetcher.routes[found] = FakeRoute.fixture(
        'aidoku_french_legacy_index.min.json',
      );

      final preview = await service.preview(
        'github.com/someone/aidoku-list.git',
      );

      expect(fetcher.urls, <String>[
        'https://raw.githubusercontent.com/someone/aidoku-list/repo/index.min.json',
        'https://raw.githubusercontent.com/someone/aidoku-list/repo/index.json',
        found,
      ]);
      expect(preview.catalogUrl, 'https://github.com/someone/aidoku-list');
    });

    test('canonical catalogue URLs resolve to themselves', () {
      for (final input in <String>[
        frenchRawDirectory,
        'https://moomooo95.github.io/aidoku-french-sources',
        'https://github.com/Moomooo95/aidoku-french-sources',
        communityIndex,
      ]) {
        final first = LibrarySourceCatalogService.resolveInput(input);
        final second = LibrarySourceCatalogService.resolveInput(
          first.catalogUri.toString(),
        );
        expect(second.catalogUri, first.catalogUri, reason: input);
        expect(
          second.candidates.map((uri) => '$uri'),
          first.candidates.map((uri) => '$uri'),
          reason: input,
        );
      }
    });
  });

  group('Aidoku index (community excerpt)', () {
    test('keeps every field of the new format', () async {
      fetcher.routes[communityIndex] = FakeRoute.fixture(
        'aidoku_community_index_excerpt.json',
      );

      final preview = await service.preview(communityIndex);

      expect(preview.format, LibraryCatalogFormat.aidokuIndex);
      expect(preview.name, 'Aidoku Community Sources');
      expect(preview.sources, hasLength(7));

      final mangadex = preview.sourceById('multi.mangadex')!;
      expect(mangadex.languages, hasLength(54));
      expect(mangadex.languages.first, 'en');
      expect(mangadex.languages, contains('zh-Hant'));
      expect(mangadex.contentRating, 1);
      expect(mangadex.websiteUrl, 'https://mangadex.org');
      expect(
        mangadex.downloadUrl,
        'https://aidoku-community.github.io/sources/sources/multi.mangadex-v14.aix',
      );
      expect(
        mangadex.iconUrl,
        'https://aidoku-community.github.io/sources/icons/multi.mangadex-v14.png',
      );

      final armageddon = preview.sourceById('en.armageddon')!;
      expect(armageddon.contentRating, 2);
      expect(armageddon.isAdultOnly, isTrue);

      expect(preview.sourceById('en.qiscans')!.altNames, <String>['Qi Manga']);
      expect(preview.sourceById('ar.aasq')!.minAppVersion, '0.7.1');
      expect(preview.sourceById('fr.sushiscan')!.version, 8);
    });

    test('reports installed sources and available updates', () async {
      await addons.upsertAddons(<LibraryAddon>[
        LibraryAddon.fromManifest(
          LibraryAddon.aidokuSourceManifest(
            sourceId: 'fr.sushiscan',
            name: 'SushiScan',
            version: '4',
            languages: const <String>['fr'],
            contentRating: 0,
            repositoryOrigin: frenchRawDirectory,
            fallbackBaseUrl: frenchRawDirectory,
          ),
          origin: frenchRawDirectory,
        ),
      ]);
      fetcher.routes[communityIndex] = FakeRoute.fixture(
        'aidoku_community_index_excerpt.json',
      );

      final preview = await service.preview(communityIndex);

      final sushi = preview.sourceById('fr.sushiscan')!;
      expect(sushi.alreadyInstalled, isTrue);
      expect(sushi.installedVersion, 4);
      expect(sushi.updateAvailable, isTrue);
      final bigsolo = preview.sourceById('fr.bigsolo')!;
      expect(bigsolo.alreadyInstalled, isFalse);
      expect(bigsolo.updateAvailable, isFalse);
    });

    test(
      'duplicate ids inside one catalogue keep the highest version',
      () async {
        fetcher.routes['https://example.org/dup.json'] = FakeRoute.json(
          <String, dynamic>{
            'name': 'Dup',
            'sources': <Map<String, dynamic>>[
              {
                'id': 'en.dup',
                'name': 'Dup',
                'version': 2,
                'languages': ['en'],
                'downloadURL': 'a.aix',
              },
              {
                'id': 'en.dup',
                'name': 'Dup',
                'version': 7,
                'languages': ['en'],
                'downloadURL': 'b.aix',
              },
              {
                'id': 'en.dup',
                'name': 'Dup',
                'version': 5,
                'languages': ['en'],
                'downloadURL': 'c.aix',
              },
            ],
          },
        );

        final preview = await service.preview('https://example.org/dup.json');

        expect(preview.sources, hasLength(1));
        expect(preview.sources.single.version, 7);
        expect(preview.sources.single.downloadUrl, 'https://example.org/b.aix');
      },
    );

    test('large indexes are parsed off the UI isolate', () async {
      final sources = <Map<String, dynamic>>[
        for (var i = 0; i < 4000; i++)
          <String, dynamic>{
            'id': 'en.generated$i',
            'name': 'Generated source number $i with a long descriptive name',
            'version': i % 9 + 1,
            'iconURL': 'icons/en.generated$i-v1.png',
            'downloadURL': 'sources/en.generated$i-v1.aix',
            'languages': <String>['en', 'fr', 'de'],
            'contentRating': i % 3,
            'baseURL': 'https://generated$i.example.com',
          },
      ];
      final body = utf8.encode(
        jsonEncode(<String, dynamic>{'name': 'Big', 'sources': sources}),
      );
      expect(body.length, greaterThan(512 * 1024));
      fetcher.routes['https://example.org/big/index.min.json'] =
          FakeRoute.bytes(Uint8List.fromList(body));

      final preview = await service.preview(
        'https://example.org/big/index.min.json',
      );

      expect(preview.sources, hasLength(4000));
      expect(preview.sources[3999].contentRating, 3999 % 3);
      expect(
        preview.sources[10].downloadUrl,
        'https://example.org/big/sources/en.generated10-v1.aix',
      );
    });
  });

  group('single source.json', () {
    test('legacy source.json from a GitHub blob link', () async {
      const raw =
          'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/master/src/rust/madara/sources/mangascantrad/res/source.json';
      fetcher.routes[raw] = FakeRoute.fixture(
        'source_legacy_mangascantrad.json',
      );

      final preview = await service.preview(
        'https://github.com/Moomooo95/aidoku-french-sources/blob/master/src/rust/madara/sources/mangascantrad/res/source.json',
      );

      expect(fetcher.urls, <String>[raw]);
      expect(preview.format, LibraryCatalogFormat.aidokuSourceJson);
      expect(preview.catalogUrl, raw);
      expect(preview.name, 'Manga Scantrad');
      final entry = preview.sources.single;
      expect(entry.id, 'fr.mangascantrad');
      expect(entry.version, 12);
      expect(entry.languages, <String>['fr']);
      expect(entry.legacyAidokuFormat, isTrue);
      expect(entry.contentRating, 1);
      expect(entry.websiteUrl, 'https://manga-scantrad.io');
      expect(
        entry.iconUrl,
        'https://raw.githubusercontent.com/Moomooo95/aidoku-french-sources/master/src/rust/madara/sources/mangascantrad/res/Icon.png',
      );
      expect(entry.downloadUrl, isNull);
    });

    test('new-format source.json keeps languages and the rating', () async {
      const url =
          'https://raw.githubusercontent.com/Aidoku-Community/sources/main/sources/fr.bigsolo/res/source.json';
      fetcher.routes[url] = FakeRoute.fixture('source_new_bigsolo.json');

      final preview = await service.preview(url);

      final entry = preview.sources.single;
      expect(entry.legacyAidokuFormat, isFalse);
      expect(entry.languages, <String>['fr']);
      expect(entry.contentRating, 0);
      expect(entry.websiteUrl, 'https://bigsolo.org');
      expect(
        entry.iconUrl,
        'https://raw.githubusercontent.com/Aidoku-Community/sources/main/sources/fr.bigsolo/res/icon.png',
      );
    });

    test('website falls back to the first HTTPS entry of urls', () async {
      fetcher.routes['https://example.org/source.json'] = FakeRoute.json(
        <String, dynamic>{
          'info': <String, dynamic>{
            'id': 'multi.example',
            'name': 'Example',
            'version': 3,
            'urls': <String>[
              'https://mirror-a.example.com',
              'https://b.example.com',
            ],
            'languages': <String>['en', 'ja'],
            'contentRating': 'primarilyNsfw',
            'altNames': <String>['Exemple'],
            'minAppVersion': '0.8',
            'maxAppVersion': '0.9',
          },
        },
      );

      final entry = (await service.preview(
        'https://example.org/source.json',
      )).sources.single;

      expect(entry.websiteUrl, 'https://mirror-a.example.com');
      expect(entry.languages, <String>['en', 'ja']);
      expect(entry.contentRating, 2);
      expect(entry.altNames, <String>['Exemple']);
      expect(entry.minAppVersion, '0.8');
      expect(entry.maxAppVersion, '0.9');
    });
  });

  group('.aix package', () {
    const packageUrl = 'https://example.org/sources/fr.example-v6.aix';

    test('reads Payload/source.json and the icon only', () async {
      final package = buildAix(
        sourceJson: <String, dynamic>{
          'info': <String, dynamic>{
            'id': 'fr.example',
            'lang': 'fr',
            'name': 'Example FR',
            'version': 6,
            'url': 'https://example-fr.com',
            'nsfw': 1,
          },
        },
      );
      fetcher.routes[packageUrl] = FakeRoute.bytes(package);

      final preview = await service.preview(packageUrl);

      expect(
        fetcher.calls.single.request.maxBytes,
        LibrarySourceCatalogService.maxPackageBytes,
      );
      expect(preview.format, LibraryCatalogFormat.aidokuPackage);
      final entry = preview.sources.single;
      expect(entry.id, 'fr.example');
      expect(entry.version, 6);
      expect(entry.legacyAidokuFormat, isTrue);
      expect(entry.contentRating, 1);
      expect(entry.websiteUrl, 'https://example-fr.com');
      expect(entry.downloadUrl, packageUrl);
      expect(entry.iconUrl, isNull);
      expect(entry.iconBytes, fakePngBytes);
      expect(entry.packageSize, package.length);
      expect(entry.packageSha256, sha256.convert(package).toString());
    });

    test(
      'new-format package with a lowercase icon and stored entries',
      () async {
        final package = buildAix(
          sourceJson: <String, dynamic>{
            'info': <String, dynamic>{
              'id': 'fr.bigsolo',
              'name': 'BigSolo',
              'version': 4,
              'url': 'https://bigsolo.org',
              'contentRating': 0,
              'languages': <String>['fr'],
            },
          },
          iconName: 'icon.png',
          storeSourceJson: true,
        );
        fetcher.routes[packageUrl] = FakeRoute.bytes(package);

        final entry = (await service.preview(packageUrl)).sources.single;

        expect(entry.legacyAidokuFormat, isFalse);
        expect(entry.iconBytes, fakePngBytes);
        expect(entry.websiteUrl, 'https://bigsolo.org');
      },
    );

    test('main.wasm is never inflated, even flagged as a symlink', () async {
      // package:archive's ZipDecoder inflates UNIX symlink entries while
      // listing the archive, without any size limit: a crafted main.wasm
      // could exhaust memory before the bounded reader runs. Corrupt
      // deflate data proves the entry is not touched at all.
      final package = markAsCorruptSymlink(
        buildAix(
          sourceJson: <String, dynamic>{
            'info': <String, dynamic>{
              'id': 'fr.example',
              'lang': 'fr',
              'name': 'Example FR',
              'version': 6,
            },
          },
          mainWasm: Uint8List(4096),
        ),
        'Payload/main.wasm',
      );
      fetcher.routes[packageUrl] = FakeRoute.bytes(package);

      final entry = (await service.preview(packageUrl)).sources.single;

      expect(entry.id, 'fr.example');
      expect(entry.iconBytes, fakePngBytes);
    });

    test('rejects a package without source.json', () async {
      fetcher.routes[packageUrl] = FakeRoute.bytes(
        buildAix(
          sourceJson: const <String, dynamic>{},
          rawSourceJson: 'not json',
        ),
      );

      await expectLater(
        service.preview(packageUrl),
        throwsA(catalogError(LibraryCatalogErrorKind.invalidDocument)),
      );
    });

    test('refuses oversized and lying source.json entries', () async {
      final padded =
          '{"info":{"id":"fr.big","name":"Big","version":1,'
          '"lang":"fr"},"pad":"${' ' * (1100 * 1024)}"}';
      final package = buildAix(
        sourceJson: const <String, dynamic>{},
        rawSourceJson: padded,
      );
      fetcher.routes[packageUrl] = FakeRoute.bytes(package);
      await expectLater(
        service.preview(packageUrl),
        throwsA(catalogError(LibraryCatalogErrorKind.tooLarge)),
      );

      // Same content, but the ZIP headers claim 200 bytes: the bounded
      // inflater must still stop at the limit.
      fetcher.routes[packageUrl] = FakeRoute.bytes(
        patchDeclaredSize(package, 'Payload/source.json', 200),
      );
      await expectLater(
        service.preview(packageUrl),
        throwsA(catalogError(LibraryCatalogErrorKind.tooLarge)),
      );
    });

    test('a package larger than 8 MB is refused before parsing', () async {
      fetcher.routes[packageUrl] = FakeRoute.bytes(
        Uint8List(LibrarySourceCatalogService.maxPackageBytes + 1),
      );

      await expectLater(
        service.preview(packageUrl),
        throwsA(
          catalogError(LibraryCatalogErrorKind.tooLarge).having(
            (e) => e.network?.kind,
            'network',
            LibraryNetworkErrorKind.tooLarge,
          ),
        ),
      );
    });
  });

  group('NeoStation manifests and Tachiyomi repositories', () {
    test('a NeoStation manifest previews as one activatable entry', () async {
      fetcher.routes['https://example.com/manifest.json'] = FakeRoute.json(
        <String, dynamic>{
          'schema': LibraryAddon.schemaV1,
          'id': 'com.example.books',
          'name': 'Example Books',
          'version': '2.1.0',
          'baseUrl': 'https://example.com/api/',
          'endpoints': <String, dynamic>{'catalog': 'catalog.json'},
        },
      );

      final preview = await service.preview(
        'https://example.com/manifest.json',
      );

      expect(preview.format, LibraryCatalogFormat.neoStationManifest);
      final entry = preview.sources.single;
      expect(entry.id, 'com.example.books');
      expect(entry.addonId, 'com.example.books');
      expect(entry.versionLabel, '2.1.0');
      expect(entry.version, 2);
      expect(entry.activatable, isTrue);
      expect(entry.manifest?['schema'], LibraryAddon.schemaV1);
    });

    test('an invalid NeoStation manifest is an invalid document', () async {
      fetcher.routes['https://example.com/manifest.json'] =
          FakeRoute.json(<String, dynamic>{
            'schema': LibraryAddon.schemaV1,
            'id': 'com.example.books',
            'name': 'Example Books',
            'version': '1',
            'baseUrl': 'http://example.com/api/',
          });

      await expectLater(
        service.preview('https://example.com/manifest.json'),
        throwsA(catalogError(LibraryCatalogErrorKind.invalidDocument)),
      );
    });

    test('Tachiyomi repositories are listed as metadata only', () async {
      fetcher.routes['https://example.com/repo/index.min.json'] =
          FakeRoute.json(<Map<String, dynamic>>[
            {
              'name': 'Tachiyomi: Example',
              'pkg': 'eu.kanade.tachiyomi.extension.fr.example',
              'apk': 'tachiyomi-fr.example-v1.4.2.apk',
              'lang': 'fr',
              'code': 2,
              'version': '1.4.2',
              'nsfw': 1,
              'sources': [
                {
                  'name': 'Example',
                  'lang': 'fr',
                  'id': '123456789',
                  'baseUrl': 'https://example-fr.com',
                },
              ],
            },
            {
              'name': 'Outdated App',
              'pkg': 'eu.kanade.tachiyomi.extension.all.keiyoushi',
              'sources': [
                {'name': 'Outdated', 'id': '1', 'baseUrl': 'https://k.example'},
              ],
            },
          ]);

      final preview = await service.preview('https://example.com/repo/');

      expect(preview.format, LibraryCatalogFormat.tachiyomiRepository);
      expect(preview.isActivatable, isFalse);
      final entry = preview.sources.single;
      expect(entry.id, '123456789');
      expect(
        entry.addonId,
        'tachiyomi.123456789.eu.kanade.tachiyomi.extension.fr.example',
      );
      expect(entry.activatable, isFalse);
      expect(entry.contentRating, 1);
      expect(entry.websiteUrl, 'https://example-fr.com');
      expect(
        entry.downloadUrl,
        'https://example.com/repo/apk/tachiyomi-fr.example-v1.4.2.apk',
      );
      expect(entry.packageName, 'eu.kanade.tachiyomi.extension.fr.example');
      expect(await addons.load(), isEmpty);
    });
  });

  group('local files', () {
    test(
      'an Aidoku list with absolute URLs works without a web origin',
      () async {
        final bytes = utf8.encode(
          jsonEncode(<Map<String, dynamic>>[
            {
              'id': 'fr.absolute',
              'name': 'Absolute',
              'file': 'https://cdn.example.org/list/sources/fr.absolute-v2.aix',
              'icon': 'https://cdn.example.org/list/icons/fr.absolute-v2.png',
              'lang': 'fr',
              'version': 2,
              'nsfw': 0,
            },
            {
              'id': 'fr.relative',
              'name': 'Relative',
              'file': 'fr.relative-v1.aix',
              'lang': 'fr',
              'version': 1,
            },
          ]),
        );

        final preview = await service.previewDocument(
          bytes,
          fileName: '/private/var/mobile/Inbox/list.json',
        );

        expect(preview.catalogUrl, 'file:list.json');
        expect(preview.isLocalFile, isTrue);
        expect(preview.format, LibraryCatalogFormat.aidokuLegacyIndex);
        expect(
          preview.sourceById('fr.absolute')!.downloadUrl,
          'https://cdn.example.org/list/sources/fr.absolute-v2.aix',
        );
        expect(
          preview.sourceById('fr.absolute')!.iconUrl,
          'https://cdn.example.org/list/icons/fr.absolute-v2.png',
        );
        expect(preview.sourceById('fr.relative')!.downloadUrl, isNull);
        expect(fetcher.calls, isEmpty);
      },
    );

    test('a byte order mark before the JSON is accepted', () async {
      final preview = await service.previewDocument(<int>[
        0xEF,
        0xBB,
        0xBF,
        ...File(
          'test/fixtures/library_catalog/aidoku_community_index_excerpt.json',
        ).readAsBytesSync(),
      ], fileName: 'community.json');

      expect(preview.format, LibraryCatalogFormat.aidokuIndex);
      expect(preview.sources, hasLength(7));
      // Relative URLs cannot be resolved from a local file.
      expect(preview.sourceById('fr.bigsolo')!.downloadUrl, isNull);
      expect(
        preview.sourceById('fr.bigsolo')!.websiteUrl,
        'https://bigsolo.org',
      );
    });

    test('a local .aix file is read like a downloaded one', () async {
      final preview = await service.previewDocument(
        buildAix(
          sourceJson: <String, dynamic>{
            'info': <String, dynamic>{
              'id': 'fr.local',
              'lang': 'fr',
              'name': 'Local',
              'version': 1,
            },
          },
        ),
        fileName: 'fr.local-v1.aix',
      );

      expect(preview.format, LibraryCatalogFormat.aidokuPackage);
      expect(preview.sources.single.downloadUrl, isNull);
      expect(preview.sources.single.iconBytes, fakePngBytes);
    });
  });

  group('typed failures', () {
    test('address errors', () async {
      await expectLater(
        service.preview('   '),
        throwsA(catalogError(LibraryCatalogErrorKind.invalidUrl)),
      );
      await expectLater(
        service.preview('http://example.org/index.min.json'),
        throwsA(catalogError(LibraryCatalogErrorKind.notHttps)),
      );
      await expectLater(
        service.preview('aidoku://fr.example/manga/42'),
        throwsA(catalogError(LibraryCatalogErrorKind.invalidUrl)),
      );
      await expectLater(
        service.preview('aidoku://addSourceList?url=http://example.org/'),
        throwsA(catalogError(LibraryCatalogErrorKind.notHttps)),
      );
      expect(fetcher.calls, isEmpty);
    });

    test('every candidate missing is notFound', () async {
      await expectLater(
        service.preview('https://example.org/nothing/'),
        throwsA(
          catalogError(
            LibraryCatalogErrorKind.notFound,
          ).having((error) => error.network?.statusCode, 'status', 404),
        ),
      );
      expect(fetcher.calls, hasLength(3));
    });

    test('documents that are not catalogues', () async {
      fetcher.routes['https://example.org/page.html'] = FakeRoute.text(
        '<!DOCTYPE html><html><title>Aidoku</title></html>',
      );
      fetcher.routes['https://example.org/other.json'] = FakeRoute.json(
        <String, dynamic>{'hello': 'world'},
      );
      fetcher.routes['https://example.org/empty.json'] = FakeRoute.json(
        <dynamic>[],
      );
      fetcher.routes['https://example.org/empty-index.json'] = FakeRoute.json(
        <String, dynamic>{'name': 'Empty', 'sources': <dynamic>[]},
      );

      await expectLater(
        service.preview('https://example.org/page.html'),
        throwsA(catalogError(LibraryCatalogErrorKind.invalidDocument)),
      );
      await expectLater(
        service.preview('https://example.org/other.json'),
        throwsA(catalogError(LibraryCatalogErrorKind.unsupportedFormat)),
      );
      await expectLater(
        service.preview('https://example.org/empty.json'),
        throwsA(catalogError(LibraryCatalogErrorKind.emptyCatalog)),
      );
      await expectLater(
        service.preview('https://example.org/empty-index.json'),
        throwsA(catalogError(LibraryCatalogErrorKind.emptyCatalog)),
      );
    });

    test('network failures stop immediately and stay typed', () async {
      fetcher.routes['https://example.org/down/index.min.json'] =
          FakeRoute.failure(LibraryNetworkErrorKind.offline);

      await expectLater(
        service.preview('https://example.org/down'),
        throwsA(
          catalogError(LibraryCatalogErrorKind.network).having(
            (error) => error.network?.kind,
            'network',
            LibraryNetworkErrorKind.offline,
          ),
        ),
      );
      expect(fetcher.calls, hasLength(1));
    });

    test('a cancelled preview reports a cancelled network error', () async {
      final token = LibraryCancelToken()..cancel();

      await expectLater(
        service.preview(frenchRawDirectory, cancel: token),
        throwsA(
          catalogError(LibraryCatalogErrorKind.network).having(
            (error) => error.network?.kind,
            'network',
            LibraryNetworkErrorKind.cancelled,
          ),
        ),
      );
      expect(fetcher.calls, isEmpty);
    });
  });

  group('content rating normalisation', () {
    test('contentRating ?? nsfw ?? safe, robust to strings', () {
      int rating(Object? contentRating, [Object? nsfw]) =>
          LibraryAddon.normalizeContentRating(contentRating, nsfw);

      expect(rating(null), 0);
      expect(rating(null, null), 0);
      expect(rating(0, 2), 0);
      expect(rating(null, 1), 1);
      expect(rating(2), 2);
      expect(rating(7), 2);
      expect(rating(-1, 1), 1);
      expect(rating('1'), 1);
      expect(rating(' 2 '), 2);
      expect(rating('safe', 2), 0);
      expect(rating('containsNsfw'), 1);
      expect(rating('primarilyNsfw'), 2);
      expect(rating('primarily_nsfw'), 2);
      expect(rating('CONTENT_WARNING_NSFW'), 1);
      expect(rating('CONTENT_WARNING_NONE', 1), 0);
      expect(rating('garbage', 1), 1);
      expect(rating('garbage', 'garbage'), 0);
      expect(rating(true), 1);
      expect(rating(false, 2), 0);
      expect(rating(<String, dynamic>{}, 2), 2);
      expect(rating(double.nan, 1), 1);
    });
  });
}
