// Build 438 (maintainer decision of 11 October 2026): every installed
// Library source is a small file of Files › NeoStation › Library › Sources
// and deleting that file removes the source from NeoStation. The app never
// shows the folder. Behaviour of LibrarySourceFiles with real files in a
// temporary Documents folder (path_provider mocked), plus the screens that
// refresh after such a removal.
import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/library_catalog_preview_screen.dart';
import 'package:neostation/screens/library_screen/library_gamepad_view_controller.dart';
import 'package:neostation/screens/library_screen/library_sources_view.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:neostation/services/library_source_files.dart';
import 'package:neostation/services/library_source_health_store.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import 'library_feed_test_fakes.dart' as feed_fakes;
import 'library_ui_sources_harness.dart';

const MethodChannel _pathProvider = MethodChannel(
  'plugins.flutter.io/path_provider',
);
const String _addonsKey = 'neostation_library_addons_v1';
const String _catalogUrl = 'https://example.org/aidoku/index.min.json';

final LibraryAddon _lelscan = testAidokuAddon('fr.lelscanfr', 'LelscanFR');
final LibraryAddon _scantrad = testAidokuAddon(
  'fr.mangascantrad',
  'Manga Scantrad',
);
final LibraryAddon _astral = testAidokuAddon('fr.astralmanga', 'Astral Manga');

const String _lelscanFile = 'LelscanFR (fr).json';
const String _scantradFile = 'Manga Scantrad (fr).json';
const String _astralFile = 'Astral Manga (fr).json';

/// Records every removal of the add-on service (the in-app path).
class _CountingAddonService extends LibraryAddonService {
  _CountingAddonService({super.sourceFilesDirectory})
    : super.forTesting(sourceFiles: true, sourceFilesFollowLifecycle: false);

  final List<Set<String>> removeManyCalls = <Set<String>>[];

  @override
  Future<int> removeMany(Iterable<String> ids) {
    removeManyCalls.add(ids.toSet());
    return super.removeMany(ids);
  }
}

/// A Sources folder whose listing fails (permission, unmounted volume).
class _UnlistableFolder implements Directory {
  _UnlistableFolder(this.path);

  @override
  final String path;

  @override
  Directory get parent => Directory(path).parent;

  @override
  Stream<FileSystemEntity> list({
    bool recursive = false,
    bool followLinks = true,
  }) => Stream<FileSystemEntity>.error(
    FileSystemException('Operation not permitted', path),
  );

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// The real Sources folder, except that [unreadable] cannot be read.
class _FolderWithUnreadableFile implements Directory {
  _FolderWithUnreadableFile(this._real, this.unreadable);

  final Directory _real;
  final String unreadable;

  @override
  String get path => _real.path;

  @override
  Directory get parent => _real.parent;

  @override
  Stream<FileSystemEntity> list({
    bool recursive = false,
    bool followLinks = true,
  }) => _real
      .list(recursive: recursive, followLinks: followLinks)
      .map(
        (entity) => p.basename(entity.path) == unreadable
            ? _UnreadableFile(entity.path)
            : entity,
      );

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _UnreadableFile implements File {
  _UnreadableFile(this.path);

  @override
  final String path;

  @override
  Future<int> length() => File(path).length();

  @override
  Future<Uint8List> readAsBytes() =>
      Future<Uint8List>.error(FileSystemException('Permission denied', path));

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Lets real file I/O started from fake-async widget code complete.
Future<void> _settleUntil(
  WidgetTester tester,
  bool Function() done, {
  int rounds = 200,
}) async {
  for (var round = 0; round < rounds && !done(); round++) {
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 15)),
    );
    await tester.pump();
  }
}

/// Real-time wait for [done] (work started in the real zone).
Future<void> _waitFor(bool Function() done) async {
  for (var round = 0; round < 300 && !done(); round++) {
    await Future<void>.delayed(const Duration(milliseconds: 10));
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  late Directory documents;
  late Directory sources;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    documents = Directory.systemTemp.createTempSync('ns_source_files_');
    sources = Directory(p.join(documents.path, 'Library', 'Sources'));
    messenger.setMockMethodCallHandler(
      _pathProvider,
      (call) async => documents.path,
    );
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(_pathProvider, null);
    try {
      documents.deleteSync(recursive: true);
    } on FileSystemException {
      // The system clears its temporary folder.
    }
  });

  /// Add-on service mirroring its sources in Documents/Library/Sources.
  LibraryAddonService newService({
    bool lifecycle = false,
    Future<Directory> Function()? directory,
  }) {
    final service = LibraryAddonService.forTesting(
      sourceFiles: true,
      sourceFilesDirectory: directory,
      sourceFilesFollowLifecycle: lifecycle,
    );
    addTearDown(() => service.sourceFiles!.dispose());
    return service;
  }

  File fileOf(String name) => File(p.join(sources.path, name));

  /// Visible entries of the Sources folder (files and folders), sorted.
  List<String> visible() {
    if (!sources.existsSync()) return const <String>[];
    return sources
        .listSync()
        .map((entity) => p.basename(entity.path))
        .where((name) => !name.startsWith('.'))
        .toList()
      ..sort();
  }

  Map<String, Object?> contentOf(String name) =>
      jsonDecode(fileOf(name).readAsStringSync()) as Map<String, Object?>;

  Future<Map<String, String>> written() async {
    final preferences = await SharedPreferences.getInstance();
    final raw = preferences.getString(LibrarySourceFiles.preferencesKey);
    if (raw == null) return const <String, String>{};
    return Map<String, String>.from(jsonDecode(raw) as Map);
  }

  List<String> idsOf(LibraryAddonService service) =>
      service.addons.map((addon) => addon.id).toList()..sort();

  /// Sources persisted in the preferences, read by a fresh service.
  Future<List<String>> persistedIds() async {
    final fresh = LibraryAddonService.forTesting();
    return (await fresh.load()).map((addon) => addon.id).toList()..sort();
  }

  void storeBuild437Sources(List<LibraryAddon> addons) {
    SharedPreferences.setMockInitialValues(<String, Object>{
      _addonsKey: jsonEncode(addons.map((addon) => addon.toJson()).toList()),
    });
  }

  group('Library source files', () {
    test('the first load after the update writes one file per source and '
        'removes nothing', () async {
      storeBuild437Sources(<LibraryAddon>[_lelscan, _scantrad, _astral]);
      expect(sources.existsSync(), isFalse);

      final service = newService();
      final loaded = await service.load();

      expect(loaded, hasLength(3));
      expect(visible(), <String>[_astralFile, _lelscanFile, _scantradFile]);
      expect(contentOf(_lelscanFile), <String, Object?>{
        'schema': LibrarySourceFiles.schema,
        'id': 'aidoku.fr.lelscanfr',
        'name': 'LelscanFR',
        'language': 'fr',
        'version': '5',
        'origin': _catalogUrl,
      });
      expect(await written(), <String, String>{
        _lelscan.id: _lelscanFile,
        _scantrad.id: _scantradFile,
        _astral.id: _astralFile,
      });
      expect(await persistedIds(), hasLength(3));

      // Nothing to do on the next pass.
      final before = fileOf(_lelscanFile).lastModifiedSync();
      await service.syncSourceFiles();
      expect(visible(), hasLength(3));
      expect(fileOf(_lelscanFile).lastModifiedSync(), before);
    });

    test('deleting one file removes only its source, once per pass, through '
        'the in-app removal', () async {
      final service = _CountingAddonService();
      addTearDown(() => service.sourceFiles!.dispose());
      final events = <Set<String>>[];
      final subscription = service.removedThroughSourceFiles.listen(events.add);
      addTearDown(subscription.cancel);
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad, _astral]);
      expect(visible(), hasLength(3));
      final lelscanBytes = fileOf(_lelscanFile).readAsBytesSync();

      fileOf(_scantradFile).deleteSync();
      await service.syncSourceFiles();
      await pumpEventQueue();

      expect(idsOf(service), <String>[_astral.id, _lelscan.id]);
      expect(service.removeManyCalls, <Set<String>>[
        <String>{_scantrad.id},
      ]);
      expect(events, <Set<String>>[
        <String>{_scantrad.id},
      ]);
      expect(await persistedIds(), <String>[_astral.id, _lelscan.id]);
      expect(await written(), isNot(contains(_scantrad.id)));
      expect(visible(), <String>[_astralFile, _lelscanFile]);
      expect(fileOf(_lelscanFile).readAsBytesSync(), lelscanBytes);

      // Two files deleted at once: one removal for both.
      fileOf(_lelscanFile).deleteSync();
      fileOf(_astralFile).deleteSync();
      await service.syncSourceFiles();
      expect(service.addons, isEmpty);
      expect(service.removeManyCalls.last, <String>{_lelscan.id, _astral.id});
      expect(service.removeManyCalls, hasLength(2));
    });

    test('a renamed file keeps its source and gets its updates', () async {
      final service = newService();
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);

      fileOf(_lelscanFile).renameSync(p.join(sources.path, 'My manga.json'));
      await service.syncSourceFiles();

      expect(idsOf(service), contains(_lelscan.id));
      expect(visible(), <String>['My manga.json', _scantradFile]..sort());
      expect((await written())[_lelscan.id], 'My manga.json');

      // An update is written into the renamed file.
      await service.upsertAddons(<LibraryAddon>[
        testAidokuAddon('fr.lelscanfr', 'LelscanFR', version: '6'),
      ]);
      expect(visible(), <String>['My manga.json', _scantradFile]..sort());
      expect(contentOf('My manga.json')['version'], '6');

      // Deleting the renamed file still removes the source.
      fileOf('My manga.json').deleteSync();
      await service.syncSourceFiles();
      expect(idsOf(service), <String>[_scantrad.id]);
    });

    test('files without the NeoStation marker are never written over nor '
        'deleted', () async {
      sources.createSync(recursive: true);
      final foreign = <String, String>{
        // Takes the usual name of LelscanFR, without the marker.
        _lelscanFile: '{"id": "aidoku.fr.lelscanfr", "name": "mine"}',
        'notes.txt': 'my notes',
        'other.json': '{"schema": "other", "id": "aidoku.fr.mangascantrad"}',
        'broken.json': '{"schema": "neostation.library.source-file.v1", ',
      };
      foreign.forEach((name, text) => fileOf(name).writeAsStringSync(text));
      final extra = Directory(p.join(sources.path, 'Extra'))..createSync();
      // Inside a sub-folder: not part of the folder's files.
      final nested = File(p.join(extra.path, 'nested.json'))
        ..writeAsStringSync(
          jsonEncode(<String, Object?>{
            'schema': LibrarySourceFiles.schema,
            'id': 'aidoku.fr.removedlongago',
          }),
        );

      final service = newService();
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);

      final hash = LibrarySourceFiles.fileNameHash(_lelscan.id);
      final ours = 'LelscanFR (fr) [${hash.substring(0, 4)}].json';
      expect(contentOf(ours)['id'], _lelscan.id);
      expect(
        visible(),
        <String>[
          'Extra',
          _lelscanFile,
          ours,
          _scantradFile,
          'broken.json',
          'notes.txt',
          'other.json',
        ]..sort(),
      );

      // Removing both sources (one through Files, one in the app) leaves
      // every foreign file as it was.
      fileOf(ours).deleteSync();
      await service.syncSourceFiles();
      await service.remove(_scantrad.id);
      expect(service.addons, isEmpty);
      foreign.forEach(
        (name, text) => expect(fileOf(name).readAsStringSync(), text),
      );
      expect(nested.existsSync(), isTrue);
      expect(
        visible(),
        <String>[
          'Extra',
          _lelscanFile,
          'broken.json',
          'notes.txt',
          'other.json',
        ]..sort(),
      );
    });

    test('an in-app removal deletes the file at once; a file whose source is '
        'not installed is deleted', () async {
      final service = newService();
      final catalogs = LibrarySourceCatalogService(
        addons: service,
        store: LibraryCatalogMemoryStore(),
      );
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad, _astral]);

      expect(await catalogs.deactivate(_scantrad.id), isTrue);
      expect(visible(), <String>[_astralFile, _lelscanFile]);
      expect(await written(), isNot(contains(_scantrad.id)));

      // Forgetting a catalogue with its sources (removeMany).
      await catalogs.forget(_catalogUrl, deactivateSources: true);
      expect(service.addons, isEmpty);
      expect(visible(), isEmpty);
      expect(await written(), isEmpty);

      // A source file copied from another device (or a source removed while
      // the app was not running).
      fileOf('Elsewhere.json').writeAsStringSync(
        LibrarySourceFileDescriptor.of(
          testAidokuAddon('fr.elsewhere', 'Elsewhere'),
        ).encode(),
      );
      await service.syncSourceFiles();
      expect(visible(), isEmpty);
    });

    test('reinstalling a source removed through Files writes its file '
        'again', () async {
      final service = newService();
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
      fileOf(_scantradFile).deleteSync();
      await service.syncSourceFiles();
      expect(idsOf(service), <String>[_lelscan.id]);

      await service.upsertAddons(<LibraryAddon>[_scantrad]);
      expect(fileOf(_scantradFile).existsSync(), isTrue);
      expect((await written())[_scantrad.id], _scantradFile);
      await service.syncSourceFiles();
      expect(idsOf(service), <String>[_lelscan.id, _scantrad.id]);

      // And it can be removed through Files again.
      fileOf(_scantradFile).deleteSync();
      await service.syncSourceFiles();
      expect(idsOf(service), <String>[_lelscan.id]);
    });

    test('deleting the whole Sources folder removes every source whose file '
        'had been written, and nothing else', () async {
      final books = File(p.join(documents.path, 'Library', 'Books', 'a.epub'))
        ..createSync(recursive: true)
        ..writeAsStringSync('book');
      final download = File(
        p.join(documents.path, 'Library', 'Downloads', 'b.cbz'),
      )..createSync(recursive: true);
      final service = newService();
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
      expect(visible(), hasLength(2));

      sources.deleteSync(recursive: true);
      // A source installed now has never had a file: it is kept and gets
      // one, the two others are removed.
      await service.upsertAddons(<LibraryAddon>[_astral]);

      expect(idsOf(service), <String>[_astral.id]);
      expect(visible(), <String>[_astralFile]);
      expect(await written(), <String, String>{_astral.id: _astralFile});
      expect(books.readAsStringSync(), 'book');
      expect(download.existsSync(), isTrue);

      // Without any source left, the folder is not recreated.
      sources.deleteSync(recursive: true);
      await service.syncSourceFiles();
      expect(service.addons, isEmpty);
      expect(sources.existsSync(), isFalse);
      await service.syncSourceFiles();
      expect(sources.existsSync(), isFalse);
    });

    test('a listing or read failure, or no Documents folder, removes '
        'nothing', () async {
      Directory Function() folder = () => sources;
      final service = newService(directory: () async => folder());
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
      fileOf(_scantradFile).deleteSync();
      final expected = <String>[_lelscan.id, _scantrad.id];

      folder = () => throw const FileSystemException('no container path');
      await service.syncSourceFiles();
      expect(idsOf(service), expected);

      folder = () => _UnlistableFolder(sources.path);
      await service.syncSourceFiles();
      expect(idsOf(service), expected);

      folder = () => _FolderWithUnreadableFile(sources, _lelscanFile);
      await service.syncSourceFiles();
      expect(idsOf(service), expected);

      folder = () =>
          Directory(p.join(documents.path, 'unmounted', 'Library', 'Sources'));
      await service.syncSourceFiles();
      expect(idsOf(service), expected);

      expect(await persistedIds(), expected);
      expect((await written()).keys, containsAll(expected));
      expect(visible(), <String>[_lelscanFile]);

      // Once the folder can be read, the deletion is applied.
      folder = () => sources;
      await service.syncSourceFiles();
      expect(idsOf(service), <String>[_lelscan.id]);
    });

    test('built-in sources never get a file', () async {
      final builtIn = LibraryAddon.fromManifest(<String, dynamic>{
        'schema': LibraryAddon.schemaV1,
        'id': 'org.neostation.builtin',
        'name': 'Bundled',
        'version': '1',
        'baseUrl': 'https://books.example.org/',
        'builtIn': true,
      }, origin: 'builtin:bundled');
      expect(builtIn.isBuiltIn, isTrue);
      final service = newService();
      await service.upsertAddons(<LibraryAddon>[builtIn, _lelscan]);

      expect(visible(), <String>[_lelscanFile]);
      expect((await written()).keys, <String>[_lelscan.id]);
      await service.syncSourceFiles();
      expect(idsOf(service), <String>[builtIn.id, _lelscan.id]..sort());
    });

    test('concurrent requests run one pass at a time and share the next '
        'one', () async {
      Completer<void>? gate;
      var maxActive = 0;
      late final _CountingAddonService service;
      service = _CountingAddonService(
        sourceFilesDirectory: () async {
          final files = service.sourceFiles!;
          if (files.activePasses > maxActive) maxActive = files.activePasses;
          final wait = gate;
          if (wait != null) await wait.future;
          return sources;
        },
      );
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
      fileOf(_scantradFile).deleteSync();
      final files = service.sourceFiles!;
      final passesBefore = files.passCount;

      gate = Completer<void>();
      final requests = <Future<void>>[
        service.syncSourceFiles(reason: 'one'),
        files.sync(reason: 'two'),
        service.syncSourceFiles(reason: 'three'),
        service.load(),
      ];
      await pumpEventQueue();
      expect(files.activePasses, 1);
      gate.complete();
      gate = null;
      await Future.wait(requests);

      expect(files.passCount - passesBefore, 2);
      expect(maxActive, 1);
      expect(files.activePasses, 0);
      expect(service.removeManyCalls, <Set<String>>[
        <String>{_scantrad.id},
      ]);
      expect(idsOf(service), <String>[_lelscan.id]);
      expect(visible(), <String>[_lelscanFile]);
    });

    test('the Library hub feed drops a source removed through Files', () async {
      final backend = feed_fakes.FakeFeedBackend();
      for (final addon in <LibraryAddon>[_lelscan, _scantrad]) {
        backend.pages[addon.aidokuSourceId!] = (call) async =>
            feed_fakes.testPage([
              feed_fakes.testItem('${addon.id}-title'),
            ], hasMore: false);
      }
      final previous = LibraryCatalogFeed.instance;
      final feed = LibraryCatalogFeed(backend: backend);
      LibraryCatalogFeed.instance = feed;
      addTearDown(() {
        LibraryCatalogFeed.instance = previous;
        feed.dispose();
      });

      final service = newService();
      // Wiring of the app's service (LibraryAddonService.instance on iOS).
      final subscription = service.removedThroughSourceFiles.listen(
        (removed) => LibrarySourceFiles.refreshLibraryFeed(service, removed),
      );
      addTearDown(subscription.cancel);
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
      await feed.open(service.addons);
      expect(feed.source(_scantrad.id), isNotNull);

      fileOf(_scantradFile).deleteSync();
      await service.syncSourceFiles();
      await _waitFor(() => feed.source(_scantrad.id) == null);

      expect(feed.source(_scantrad.id), isNull);
      expect(feed.source(_lelscan.id), isNotNull);
      expect(
        feed.entries.map((entry) => entry.item.id),
        isNot(contains('${_scantrad.id}-title')),
      );
    });

    test('reading progress, favourites, health reports, catalogues and '
        'local books are kept', () async {
      final support = Directory(p.join(documents.path, 'Support'))
        ..createSync();
      final readingKey = LibraryReadingStore.onlineKey(
        'fr.mangascantrad',
        'solo',
      );
      final reading = LibraryReadingStore(directory: support);
      await reading.load();
      reading.saveProgress(
        LibraryReadingProgress(
          key: readingKey,
          location: LibraryReadingProgress.pageLocation(3),
          fraction: 0.4,
          title: 'Solo',
        ),
      );
      await reading.addFavorite(
        LibraryFavorite(
          key: readingKey,
          sourceId: 'fr.mangascantrad',
          addonId: _scantrad.id,
          mangaId: 'solo',
          title: 'Solo',
        ),
      );
      await reading.flush();
      reading.dispose();
      final health = LibrarySourceHealthStore(directory: () async => support);
      await health.record(
        LibrarySourceHealthReport(
          sourceId: 'fr.mangascantrad',
          checkedAt: DateTime.utc(2026, 10, 11, 9),
          steps: const <LibrarySourceHealthStepResult>[],
        ),
      );
      final catalogStore = LibraryCatalogFileStore(
        directory: () async => support,
      );
      await catalogStore.write(<LibraryStoredCatalog>[
        LibraryStoredCatalog(
          url: _catalogUrl,
          format: LibraryCatalogFormat.aidokuLegacyIndex,
          lastFetchedAt: DateTime.utc(2026, 10, 11),
          sourceCount: 2,
        ),
      ]);
      final book = File(p.join(documents.path, 'Library', 'Books', 'a.cbz'))
        ..createSync(recursive: true)
        ..writeAsStringSync('pages');

      final service = newService();
      await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
      fileOf(_scantradFile).deleteSync();
      await service.syncSourceFiles();
      expect(idsOf(service), <String>[_lelscan.id]);

      final reread = LibraryReadingStore(directory: support);
      await reread.load();
      expect(reread.progressFor(readingKey)?.fraction, closeTo(0.4, 1e-9));
      expect(reread.isFavorite(readingKey), isTrue);
      reread.dispose();
      final healthAgain = LibrarySourceHealthStore(
        directory: () async => support,
      );
      await healthAgain.load();
      expect(healthAgain.latest('fr.mangascantrad'), isNotNull);
      expect(
        (await catalogStore.read()).map((catalog) => catalog.url),
        <String>[_catalogUrl],
      );
      expect(book.readAsStringSync(), 'pages');
    });

    test('file names are readable, safe for Files and unique', () async {
      expect(
        LibrarySourceFiles.sanitizeFileName('../A/B: C*?"<>|\n​end. '),
        'A B C end',
      );
      expect(LibrarySourceFiles.sanitizeFileName('...'), isEmpty);
      expect(LibrarySourceFiles.sanitizeFileName('con'), 'con_');
      final long = LibrarySourceFiles.sanitizeFileName('漫' * 200);
      expect(utf8.encode(long).length, lessThanOrEqualTo(180));
      expect(long.runes.every((rune) => rune == '漫'.runes.single), isTrue);
      expect(
        LibrarySourceFiles.fileNameHash('aidoku.x'),
        LibrarySourceFiles.fileNameHash('aidoku.x'),
      );

      final slash = testAidokuAddon('fr.slash', 'Scan/Trad: VF');
      final hidden = testAidokuAddon('fr.hidden', '.Hidden');
      final twin = testAidokuAddon('fr.lelscantwin', 'lelscanfr');
      final service = newService();
      await service.upsertAddons(<LibraryAddon>[_lelscan, slash, hidden]);
      await service.upsertAddons(<LibraryAddon>[twin]);

      final twinHash = LibrarySourceFiles.fileNameHash(twin.id);
      expect(
        visible(),
        <String>[
          'Hidden (fr).json',
          _lelscanFile,
          'lelscanfr (fr) [${twinHash.substring(0, 4)}].json',
          'Scan Trad VF (fr).json',
        ]..sort(),
      );
      for (final name in visible()) {
        expect(
          LibrarySourceFileDescriptor.tryParse(fileOf(name).readAsStringSync()),
          isNotNull,
        );
      }
    });

    test('a duplicated file is reduced to the one NeoStation knows', () async {
      final service = newService();
      await service.upsertAddons(<LibraryAddon>[_lelscan]);
      fileOf(_lelscanFile).copySync(p.join(sources.path, 'Copy.json'));

      await service.syncSourceFiles();

      expect(visible(), <String>[_lelscanFile]);
      expect(idsOf(service), <String>[_lelscan.id]);
    });
  });

  group('Library source files in the app', () {
    testWidgets('coming back to the app removes a source whose file was '
        'deleted in Files', (tester) async {
      final service = newService(lifecycle: true);
      await tester.runAsync(() async {
        await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
        fileOf(_scantradFile).deleteSync();
        final files = service.sourceFiles!;
        final passes = files.passCount;

        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.inactive,
        );
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        await Future<void>.delayed(const Duration(milliseconds: 50));
        expect(files.passCount, passes);
        expect(idsOf(service), hasLength(2));

        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.inactive,
        );
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await _waitFor(() => service.addons.length == 1);
        expect(files.passCount, passes + 1);
      });
      expect(idsOf(service), <String>[_lelscan.id]);
    });

    testWidgets('the sources view drops a source removed through Files and '
        'tells the hub', (tester) async {
      final service = newService(lifecycle: true);
      await tester.runAsync(
        () => service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]),
      );
      final catalogs = LibrarySourceCatalogService(
        addons: service,
        store: LibraryCatalogMemoryStore(),
      );
      var sourcesChanged = 0;
      final controller = LibraryGamepadViewController();
      Finder row(LibraryAddon addon) =>
          find.byKey(ValueKey<String>('source-${addon.id}'));

      await pumpLibraryUi(
        tester,
        LibrarySourcesView(
          controller: controller,
          onBack: () {},
          onSourcesChanged: () => sourcesChanged++,
          catalogService: catalogs,
          addonService: service,
          aidokuService: FakeAidokuService(),
          healthStore: MemoryHealthStore(),
          imageCache: NoImageCache(),
          enableGamepad: false,
        ),
      );
      await _settleUntil(tester, () => row(_scantrad).evaluate().isNotEmpty);
      expect(row(_lelscan), findsOneWidget);
      expect(row(_scantrad), findsOneWidget);
      expect(sourcesChanged, 0);

      await tester.runAsync(() async {
        fileOf(_scantradFile).deleteSync();
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        tester.binding.handleAppLifecycleStateChanged(
          AppLifecycleState.resumed,
        );
        await _waitFor(() => service.addons.length == 1);
      });
      await _settleUntil(tester, () => row(_scantrad).evaluate().isEmpty);

      expect(row(_scantrad), findsNothing);
      expect(row(_lelscan), findsOneWidget);
      expect(sourcesChanged, 1);
      // Silent: no message about the removal or the folder.
      expect(find.byType(SnackBar), findsNothing);
      expect(find.byType(AlertDialog), findsNothing);
    });

    testWidgets('opening the sources view applies a deletion made in '
        'Files', (tester) async {
      final service = newService();
      await tester.runAsync(() async {
        await service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]);
        fileOf(_lelscanFile).deleteSync();
      });
      await pumpLibraryUi(
        tester,
        LibrarySourcesView(
          controller: LibraryGamepadViewController(),
          onBack: () {},
          onSourcesChanged: () {},
          catalogService: LibrarySourceCatalogService(
            addons: service,
            store: LibraryCatalogMemoryStore(),
          ),
          addonService: service,
          aidokuService: FakeAidokuService(),
          healthStore: MemoryHealthStore(),
          imageCache: NoImageCache(),
          enableGamepad: false,
        ),
      );
      final scantradRow = find.byKey(
        ValueKey<String>('source-${_scantrad.id}'),
      );
      await _settleUntil(tester, () => scantradRow.evaluate().isNotEmpty);

      expect(scantradRow, findsOneWidget);
      expect(
        find.byKey(ValueKey<String>('source-${_lelscan.id}')),
        findsNothing,
      );
      expect(idsOf(service), <String>[_scantrad.id]);
    });

    testWidgets('the catalogue preview stops showing a source removed through '
        'Files as active', (tester) async {
      final service = newService();
      await tester.runAsync(
        () => service.upsertAddons(<LibraryAddon>[_lelscan, _scantrad]),
      );
      LibraryCatalogSourceEntry entry(LibraryAddon addon) =>
          LibraryCatalogSourceEntry(
            id: addon.aidokuSourceId!,
            addonId: addon.id,
            name: addon.name,
            version: 5,
            versionLabel: '5',
            languages: const <String>['fr'],
            alreadyInstalled: true,
            installedVersion: 5,
            installedVersionLabel: '5',
          );
      final preview = LibraryCatalogPreview(
        inputUrl: _catalogUrl,
        catalogUrl: _catalogUrl,
        documentUrl: _catalogUrl,
        resolvedUrl: _catalogUrl,
        format: LibraryCatalogFormat.aidokuLegacyIndex,
        name: 'Test catalogue',
        sources: <LibraryCatalogSourceEntry>[entry(_lelscan), entry(_scantrad)],
        fetchedAt: DateTime.utc(2026, 10, 11, 8),
      );
      await pumpLibraryUi(
        tester,
        LibraryCatalogPreviewScreen(
          preview: preview,
          catalogService: LibrarySourceCatalogService(
            addons: service,
            store: LibraryCatalogMemoryStore(),
          ),
          addonService: service,
          aidokuService: FakeAidokuService(),
          imageCache: NoImageCache(),
          enableGamepad: false,
        ),
        size: const Size(844, 390),
        wrapInScaffold: false,
      );
      await tester.pumpAndSettle();
      Finder active(LibraryAddon addon) => find.descendant(
        of: find.byKey(ValueKey<String>('entry-${addon.aidokuSourceId}')),
        matching: find.text('Active: version 5'),
      );
      expect(active(_lelscan), findsOneWidget);
      expect(active(_scantrad), findsOneWidget);

      await tester.runAsync(() async {
        fileOf(_scantradFile).deleteSync();
        await service.syncSourceFiles();
        await pumpEventQueue();
      });
      await tester.pumpAndSettle();

      expect(active(_scantrad), findsNothing);
      expect(active(_lelscan), findsOneWidget);
    });
  });
}
