import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  group('LibraryAddon manifest validation', () {
    test('accepts NeoStation Library v1 HTTPS manifest', () {
      final addon = LibraryAddon.fromManifest({
        'schema': 'neostation.library.v1',
        'id': 'com.example.manga',
        'name': 'Example Manga',
        'version': '1.0.0',
        'baseUrl': 'https://example.com/api',
        'description': 'Example catalog',
        'endpoints': {'search': '/search?q={query}'},
      }, origin: 'https://example.com/manifest.json');

      expect(addon.id, 'com.example.manga');
      expect(addon.name, 'Example Manga');
      expect(addon.version, '1.0.0');
      expect(addon.baseUrl, 'https://example.com/api');
    });

    test('rejects unsupported schema', () {
      expect(
        () => LibraryAddon.fromManifest({
          'schema': 'other.schema',
          'id': 'com.example.manga',
          'name': 'Example Manga',
          'version': '1.0.0',
          'baseUrl': 'https://example.com/api',
        }, origin: 'local'),
        throwsA(isA<LibraryAddonException>()),
      );
    });

    test('rejects non-HTTPS catalog base URL', () {
      expect(
        () => LibraryAddon.fromManifest({
          'schema': 'neostation.library.v1',
          'id': 'com.example.manga',
          'name': 'Example Manga',
          'version': '1.0.0',
          'baseUrl': 'http://example.com/api',
        }, origin: 'local'),
        throwsA(isA<LibraryAddonException>()),
      );
    });
  });

  group('Tachiyomi/Mihon repository import', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('imports repository array and expands nested sources', () async {
      final raw = jsonEncode([
        {
          'name': 'Example One',
          'pkg': 'eu.kanade.tachiyomi.extension.en.exampleone',
          'apk': 'tachiyomi-en.exampleone-v1.0.0.apk',
          'lang': 'en',
          'code': 1,
          'version': '1.0.0',
          'nsfw': 0,
          'sources': [
            {
              'name': 'Example One',
              'lang': 'en',
              'id': '101',
              'baseUrl': 'https://one.example.com',
            },
          ],
        },
        {
          'name': 'Example Two',
          'pkg': 'eu.kanade.tachiyomi.extension.fr.exampletwo',
          'apk': 'tachiyomi-fr.exampletwo-v2.0.0.apk',
          'lang': 'fr',
          'code': 2,
          'version': '2.0.0',
          'nsfw': 0,
          'sources': [
            {
              'name': 'Example Two',
              'lang': 'fr',
              'id': '202',
              'baseUrl': 'https://two.example.com',
            },
          ],
        },
      ]);

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin: 'https://example.com/index.json',
      );

      expect(result.format, LibraryAddonDocumentFormat.tachiyomiRepository);
      expect(result.totalCount, 2);
      expect(result.addedCount, 2);
      expect(result.updatedCount, 0);
      expect(result.addons.first.isTachiyomiRepositorySource, isTrue);
      expect(result.addons.first.isMetadataOnlyOnIos, isTrue);
      expect(result.addons.first.androidApk, isNotEmpty);
      expect(result.addons.map((item) => item.id).toSet().length, 2);
    });

    test('imports current Keiyoushi extensionList repository object', () async {
      final raw = jsonEncode({
        'name': 'Keiyoushi',
        'extensionList': {
          'extensions': [
            {
              'name': 'Example Modern',
              'packageName': 'eu.kanade.tachiyomi.extension.fr.examplemodern',
              'resources': {
                'apkUrl':
                    'https://github.com/example/releases/example-modern.apk',
                'iconUrl': 'https://example.com/icon.png',
              },
              'extensionLib': '1.4',
              'versionCode': '7',
              'versionName': '1.4.7',
              'contentWarning': 'CONTENT_WARNING_NONE',
              'sources': [
                {
                  'id': '7001',
                  'name': 'Example Modern FR',
                  'language': 'fr',
                  'homeUrl': 'https://modern.example.com',
                },
              ],
            },
          ],
        },
      });

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin:
            'https://raw.githubusercontent.com/keiyoushi/extensions/repo/index.json',
      );

      expect(result.format, LibraryAddonDocumentFormat.tachiyomiRepository);
      expect(result.totalCount, 1);
      expect(result.addons.single.name, 'Example Modern FR');
      expect(result.addons.single.language, 'fr');
      expect(
        result.addons.single.androidPackage,
        'eu.kanade.tachiyomi.extension.fr.examplemodern',
      );
      expect(
        result.addons.single.androidApk,
        'https://github.com/example/releases/example-modern.apk',
      );
    });

    test(
      'does not install Keiyoushi migration-warning pseudo sources',
      () async {
        final raw = jsonEncode([
          {
            'name': 'Outdated App',
            'pkg': 'eu.kanade.tachiyomi.extension.all.keiyoushi',
            'apk': 'tachiyomi-all.keiyoushi-v1.4.1.apk',
            'lang': 'all',
            'version': '1.4.1',
            'sources': [
              {
                'name': 'Outdated App',
                'lang': 'all',
                'id': '1',
                'baseUrl': 'https://keiyoushi.github.io',
              },
            ],
          },
          {
            'name': 'Update to Mihon 0.20.1+',
            'pkg': 'eu.kanade.tachiyomi.extension.all.mihon',
            'apk': 'tachiyomi-all.mihon-v1.4.1.apk',
            'lang': 'all',
            'version': '1.4.1',
            'sources': [
              {
                'name': 'Update to Mihon 0.20.1+',
                'lang': 'all',
                'id': '1',
                'baseUrl': 'https://mihon.app',
              },
            ],
          },
        ]);

        await expectLater(
          LibraryAddonService.instance.installDocumentFromJson(
            raw,
            origin: 'https://example.com/index.min.json',
          ),
          throwsA(isA<LibraryAddonException>()),
        );
      },
    );

    test('ignores non-HTTPS repository sources', () async {
      final raw = jsonEncode([
        {
          'name': 'Mixed',
          'pkg': 'eu.example.mixed',
          'version': '1.0.0',
          'sources': [
            {'name': 'Unsafe', 'id': '1', 'baseUrl': 'http://example.com'},
            {'name': 'Safe', 'id': '2', 'baseUrl': 'https://example.com'},
          ],
        },
      ]);

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin: 'file:test.json',
      );
      expect(result.totalCount, 1);
      expect(result.addons.single.name, 'Safe');
    });

    test('imports legacy Aidoku source-list entries', () async {
      final raw = jsonEncode([
        {
          'id': 'fr.example',
          'name': 'Example FR',
          'file': 'fr.example-v2.aix',
          'icon': 'fr.example-v2.png',
          'lang': 'fr',
          'version': 2,
          'nsfw': 0,
        },
      ]);

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin:
            'https://raw.githubusercontent.com/example/aidoku/gh-pages/index.min.json',
      );

      expect(result.format, LibraryAddonDocumentFormat.aidokuRepository);
      expect(result.totalCount, 1);
      expect(result.addons.single.isAidokuRepositorySource, isTrue);
      expect(result.addons.single.language, 'fr');
      expect(
        result.addons.single.sourceDownloadUrl,
        'https://raw.githubusercontent.com/example/aidoku/gh-pages/sources/fr.example-v2.aix',
      );
    });

    test('removes every source belonging to one imported repository', () async {
      final raw = jsonEncode([
        {
          'id': 'fr.one',
          'name': 'One',
          'file': 'fr.one-v1.aix',
          'lang': 'fr',
          'version': 1,
        },
        {
          'id': 'fr.two',
          'name': 'Two',
          'file': 'fr.two-v1.aix',
          'lang': 'fr',
          'version': 1,
        },
      ]);
      const origin =
          'https://raw.githubusercontent.com/example/remove-test/gh-pages/index.min.json';
      await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin: origin,
      );

      final removed = await LibraryAddonService.instance.removeRepository(
        origin,
      );
      expect(removed, 2);
      final remaining = await LibraryAddonService.instance.load();
      expect(
        remaining.where((item) => item.repositoryOrigin == origin),
        isEmpty,
      );
    });

    test('does not inject built-in Library sources', () async {
      final sources = await LibraryAddonService.instance.load();
      expect(sources.where((item) => item.isBuiltIn), isEmpty);
      expect(
        sources.where((item) => item.origin.startsWith('builtin:')),
        isEmpty,
      );
    });

    test('keeps explicitly imported Gallica OPDS compatible', () async {
      final raw = jsonEncode({
        'schema': LibraryAddon.schemaV1,
        'id': 'user.gallica.bnf',
        'name': 'Gallica / BnF',
        'version': '1',
        'baseUrl': 'https://gallica.bnf.fr/',
        'provider': {'type': LibraryAddon.gallicaProviderType},
        'endpoints': {
          'catalog':
              'services/engine/search/opds?operation=searchRetrieve&version=1.2&maximumRecords=50',
        },
      });

      final result = await LibraryAddonService.instance.installDocumentFromJson(
        raw,
        origin: 'file:user-gallica.json',
      );
      final gallica = result.addons.single;
      expect(gallica.isBuiltIn, isFalse);
      expect(gallica.isGallicaSource, isTrue);
      expect(gallica.canBrowseOnIos, isTrue);
    });
  });

  group('Normalized source metadata', () {
    LibraryAddon aidoku(
      Map<String, dynamic> provider, {
      String baseUrl = 'https://example.com/',
      String origin = 'https://example.com/index.min.json',
      Map<String, dynamic> extra = const <String, dynamic>{},
    }) => LibraryAddon.fromManifest({
      'schema': LibraryAddon.schemaV1,
      'id': 'aidoku.fr.example',
      'name': 'Example',
      'version': '3',
      'baseUrl': baseUrl,
      'iosCompatibility': 'metadata-only',
      ...extra,
      'provider': <String, dynamic>{
        'type': LibraryAddon.aidokuProviderType,
        'sourceId': 'fr.example',
        'repositoryOrigin': origin,
        ...provider,
      },
    }, origin: origin);

    test('content rating is contentRating ?? nsfw ?? safe', () {
      expect(aidoku({'contentRating': 2, 'nsfw': 0}).contentRating, 2);
      expect(aidoku({'contentRating': null, 'nsfw': 1}).contentRating, 1);
      expect(aidoku({'contentRating': '2'}).contentRating, 2);
      expect(aidoku({'contentRating': 'containsNsfw'}).contentRating, 1);
      expect(aidoku({'contentRating': 'unknown', 'nsfw': 0}).contentRating, 0);
      expect(aidoku({'nsfw': '1'}).contentRating, 1);
      expect(aidoku({'nsfw': true}).contentRating, 1);
      expect(aidoku({'contentRating': 9}).contentRating, 2);
      expect(aidoku(const {}).contentRating, 0);

      final tachiyomi = LibraryAddon.fromManifest({
        'schema': LibraryAddon.schemaV1,
        'id': 'tachiyomi.1.eu.example',
        'name': 'Example',
        'version': '1.0',
        'baseUrl': 'https://example.com',
        'provider': {'type': LibraryAddon.tachiyomiProviderType, 'nsfw': 1},
      }, origin: 'https://example.com/index.json');
      expect(tachiyomi.contentRating, 1);

      // A NeoStation manifest may declare its rating at the top level.
      final manifest = LibraryAddon.fromManifest({
        'schema': LibraryAddon.schemaV1,
        'id': 'com.example.books',
        'name': 'Example',
        'version': '1',
        'baseUrl': 'https://example.com',
        'contentRating': 'primarilyNsfw',
        'provider': {'type': LibraryAddon.gallicaProviderType},
      }, origin: 'https://example.com/manifest.json');
      expect(manifest.contentRating, 2);
    });

    test('languages keep the full list and fall back to sourceLang', () {
      expect(
        aidoku({
          'sourceLang': 'multi',
          'languages': ['en', 'fr', 'ja', 'en', ''],
        }).languages,
        ['en', 'fr', 'ja'],
      );
      expect(aidoku({'sourceLang': 'fr'}).languages, ['fr']);
      expect(aidoku(const {}).languages, isEmpty);
    });

    test('the repository folder is never reported as the website', () {
      // Stored by older builds: baseUrl was the list folder.
      final legacy = aidoku(
        const {},
        baseUrl: 'https://raw.githubusercontent.com/o/r/gh-pages/',
        origin: 'https://raw.githubusercontent.com/o/r/gh-pages/index.min.json',
      );
      expect(legacy.websiteUrl, isNull);

      final withWebsite = aidoku({'website': 'https://site.example'});
      expect(withWebsite.websiteUrl, 'https://site.example');

      final unknownWebsite = aidoku({'website': null});
      expect(unknownWebsite.websiteUrl, isNull);

      // A new-format list stored the site itself as baseUrl.
      final community = aidoku(
        const {},
        baseUrl: 'https://mangadex.org',
        origin: 'https://aidoku-community.github.io/sources/index.min.json',
      );
      expect(community.websiteUrl, 'https://mangadex.org');
    });

    test('generated English descriptions of older builds are hidden', () {
      final stored = aidoku(
        const {},
        extra: const {'description': 'Aidoku repository source • fr'},
      );
      expect(stored.description, isEmpty);

      final authored = LibraryAddon.fromManifest({
        'schema': LibraryAddon.schemaV1,
        'id': 'com.example.books',
        'name': 'Example',
        'version': '1',
        'baseUrl': 'https://example.com',
        'description': 'Aidoku repository source • written by the author',
      }, origin: 'https://example.com/manifest.json');
      expect(authored.description, isNotEmpty);
    });
  });

  group('Aidoku list import (direct path)', () {
    setUp(() {
      SharedPreferences.setMockInitialValues({});
    });

    test('new-format entries keep languages, rating and website', () async {
      final service = LibraryAddonService.forTesting();
      final raw = jsonEncode({
        'name': 'Community',
        'sources': [
          {
            'id': 'multi.example',
            'name': 'Example',
            'version': 14,
            'iconURL': 'icons/multi.example-v14.png',
            'downloadURL': 'sources/multi.example-v14.aix',
            'languages': ['en', 'fr', 'zh-Hant'],
            'contentRating': 2,
            'altNames': ['Exemple'],
            'baseURL': 'https://example.org',
            'minAppVersion': '0.7.1',
          },
        ],
      });

      final result = await service.installDocumentFromJson(
        raw,
        origin: 'https://lists.example.net/sources/index.min.json',
      );

      final addon = result.addons.single;
      expect(addon.id, 'aidoku.multi.example');
      expect(addon.languages, ['en', 'fr', 'zh-Hant']);
      expect(addon.language, 'multi');
      expect(addon.contentRating, 2);
      expect(addon.websiteUrl, 'https://example.org');
      expect(addon.baseUrl, 'https://example.org');
      expect(addon.altNames, ['Exemple']);
      expect(addon.description, isEmpty);
      expect(addon.manifest['description'], isEmpty);
      expect(
        addon.sourceDownloadUrl,
        'https://lists.example.net/sources/sources/multi.example-v14.aix',
      );
      expect(
        addon.iconUrl,
        'https://lists.example.net/sources/icons/multi.example-v14.png',
      );
    });

    test('a local Aidoku list with absolute URLs installs', () async {
      final service = LibraryAddonService.forTesting();
      final raw = jsonEncode([
        {
          'id': 'fr.absolute',
          'name': 'Absolute',
          'file': 'https://cdn.example.org/list/sources/fr.absolute-v2.aix',
          'icon': 'https://cdn.example.org/list/icons/fr.absolute-v2.png',
          'lang': 'fr',
          'version': 2,
          'nsfw': 1,
        },
        {
          'id': 'fr.relative',
          'name': 'Relative',
          'file': 'fr.relative-v1.aix',
          'lang': 'fr',
          'version': 1,
        },
      ]);

      final result = await service.installDocumentFromJson(
        raw,
        origin: 'file:aidoku-list.json',
      );

      // The relative entry cannot be resolved without a web origin.
      final addon = result.addons.single;
      expect(addon.id, 'aidoku.fr.absolute');
      expect(addon.repositoryOrigin, 'file:aidoku-list.json');
      expect(
        addon.sourceDownloadUrl,
        'https://cdn.example.org/list/sources/fr.absolute-v2.aix',
      );
      expect(
        addon.iconUrl,
        'https://cdn.example.org/list/icons/fr.absolute-v2.png',
      );
      expect(addon.contentRating, 1);
      expect(addon.websiteUrl, isNull);

      await expectLater(
        service.installDocumentFromJson(
          jsonEncode([
            {
              'id': 'fr.relative',
              'name': 'Relative',
              'file': 'fr.relative-v1.aix',
              'lang': 'fr',
              'version': 1,
            },
          ]),
          origin: 'file:relative-only.json',
        ),
        throwsA(isA<LibraryAddonException>()),
      );
    });

    test('Tachiyomi imports store no generated description', () async {
      final service = LibraryAddonService.forTesting();
      final result = await service.installDocumentFromJson(
        jsonEncode([
          {
            'name': 'Example',
            'pkg': 'eu.kanade.tachiyomi.extension.en.example',
            'version': '1.0.0',
            'lang': 'en',
            'nsfw': 1,
            'sources': [
              {'name': 'Example', 'id': '7', 'baseUrl': 'https://example.com'},
            ],
          },
        ]),
        origin: 'https://example.com/index.json',
      );

      expect(result.addons.single.manifest['description'], isEmpty);
      expect(result.addons.single.contentRating, 1);
      expect(result.addons.single.websiteUrl, 'https://example.com');
    });

    test('upsertAddons and removeMany touch only the given ids', () async {
      final service = LibraryAddonService.forTesting();
      LibraryAddon source(String id, String version) =>
          LibraryAddon.fromManifest(
            LibraryAddon.aidokuSourceManifest(
              sourceId: id,
              name: id,
              version: version,
              languages: const ['fr'],
              contentRating: 0,
              repositoryOrigin: 'https://example.com/index.min.json',
              fallbackBaseUrl: 'https://example.com/',
            ),
            origin: 'https://example.com/index.min.json',
          );

      final first = await service.upsertAddons([
        source('fr.one', '1'),
        source('fr.two', '1'),
      ]);
      expect(first.addedIds, ['aidoku.fr.one', 'aidoku.fr.two']);
      expect(first.updatedIds, isEmpty);

      final second = await service.upsertAddons([source('fr.two', '2')]);
      expect(second.addedIds, isEmpty);
      expect(second.updatedIds, ['aidoku.fr.two']);

      final reloaded = await LibraryAddonService.forTesting().load();
      expect(reloaded.map((addon) => '${addon.id}@${addon.version}'), [
        'aidoku.fr.one@1',
        'aidoku.fr.two@2',
      ]);

      expect(await service.removeMany(['aidoku.fr.two', 'missing']), 1);
      expect(await service.removeMany(const []), 0);
      final remaining = await LibraryAddonService.forTesting().load();
      expect(remaining.map((addon) => addon.id), ['aidoku.fr.one']);
    });
  });
}
