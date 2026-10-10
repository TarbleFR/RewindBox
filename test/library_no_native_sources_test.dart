import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_catalog_feed.dart';

import 'library_feed_test_fakes.dart';

// Library source policy: nothing is built in (no MangaDex, no Gallica
// unless imported), and every imported browsable source is listed.
// Build 437 moved the catalogue from library_screen.dart into
// LibraryCatalogFeed, so the screen-specific string checks of earlier
// builds are replaced by behaviour tests of the feed.
void main() {
  group('Library source policy', () {
    test('Gallica is import-only while compatibility remains', () async {
      final addons = File(
        'lib/services/library_addon_service.dart',
      ).readAsStringSync();
      final catalog = File(
        'lib/services/library_catalog_service.dart',
      ).readAsStringSync();
      final screen = File(
        'lib/screens/library_screen/library_screen.dart',
      ).readAsStringSync();

      expect(addons, isNot(contains('_builtInGallicaAddon')));
      expect(addons, isNot(contains('gallicaAddonId')));
      expect(addons, contains("gallicaProviderType = 'gallica-opds'"));
      expect(addons, contains('isGallicaSource'));
      expect(catalog, contains('parseGallicaOpdsDocument'));
      expect(screen, isNot(contains('Les sources natives sont conservées')));

      // Without an import there is no source at all.
      final backend = FakeFeedBackend();
      final empty = LibraryCatalogFeed(backend: backend);
      addTearDown(empty.dispose);
      await empty.open(const []);
      expect(empty.sources, isEmpty);
      expect(backend.calls, isEmpty);

      // An imported Gallica source is browsed and its entries stay
      // filterable as French when an Atom entry has no dc:language.
      final gallica = catalogTestAddon('gallica.user', gallica: true);
      backend.catalogs[gallica.id] = (_) async => [testItem('ark:/1')];
      final feed = LibraryCatalogFeed(backend: backend);
      addTearDown(feed.dispose);
      await feed.open([gallica]);
      expect(feed.sources.single.key, gallica.id);
      expect(feed.sources.single.kind, LibraryFeedSourceKind.catalog);
      expect(feed.entries.single.languages, {'fr'});
    });

    test('MangaDex is not provided as a native Library source', () async {
      final addons = File(
        'lib/services/library_addon_service.dart',
      ).readAsStringSync();
      expect(
        File('lib/services/library_mangadex_service.dart').existsSync(),
        isFalse,
      );
      for (final path in [
        'lib/screens/library_screen/library_screen.dart',
        'lib/services/library_catalog_feed.dart',
      ]) {
        final source = File(path).readAsStringSync();
        expect(source, isNot(contains('LibraryMangaDexService')), reason: path);
        expect(source, isNot(contains('_mangaDexService')), reason: path);
        expect(source, isNot(contains('native.mangadex')), reason: path);
        expect(source, isNot(contains('_openMangaDexTitle')), reason: path);
      }

      // User-imported sources remain visible and persisted. Migration removes
      // only records that were explicitly marked as bundled by older builds;
      // it must never delete an import merely because of its name or id.
      expect(
        addons,
        contains("if (addon.isBuiltIn || addon.origin.startsWith('builtin:'))"),
      );
      expect(addons, isNot(contains("addon.id == 'native.mangadex'")));
    });

    test('every imported browsable source is listed, nothing else', () async {
      final backend = FakeFeedBackend();
      final sushi = aidokuTestAddon('fr.sushiscan', name: 'SushiScan');
      final custom = catalogTestAddon('user.catalog', name: 'My catalog');
      final mangadexLike = aidokuTestAddon('all.mangadex', name: 'MangaDex');
      backend.cachedPages['fr.sushiscan'] = testPage([
        testItem('one'),
      ], fetchedAt: DateTime.now());
      backend.cachedPages['all.mangadex'] = testPage([
        testItem('two'),
      ], fetchedAt: DateTime.now());
      backend.catalogs[custom.id] = (_) async => [testItem('three')];
      final feed = LibraryCatalogFeed(backend: backend);
      addTearDown(feed.dispose);

      await feed.open([sushi, custom]);
      expect(feed.sources.map((source) => source.name), [
        'SushiScan',
        'My catalog',
      ]);

      // A source named like MangaDex is listed only because the user
      // imported it, never on its own.
      await feed.open([sushi, custom, mangadexLike]);
      expect(feed.sources.map((source) => source.key), [
        sushi.id,
        custom.id,
        mangadexLike.id,
      ]);
      await feed.open([sushi]);
      expect(feed.sources.map((source) => source.key), [sushi.id]);
    });

    test('other Library compatibility layers remain present', () {
      expect(File('assets/data/manga-providers.json').existsSync(), isFalse);
      final metadata = File(
        'lib/services/library_metadata_provider_service.dart',
      );
      expect(metadata.existsSync(), isTrue);
      final metadataSource = metadata.readAsStringSync();
      expect(metadataSource, isNot(contains('rootBundle.loadString')));
      expect(metadataSource, isNot(contains('manifestAsset')));
    });
  });
}
