import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/storage_locale.dart';
import 'package:neostation/repositories/storage_maintenance_repository.dart';
import 'package:neostation/services/library_source_files.dart';
import 'package:neostation/services/rpcs3_save_exchange_service.dart';
import 'package:neostation/services/storage/storage_deletion_manager.dart';
import 'package:neostation/services/storage/storage_orphan_detector.dart';
import 'package:neostation/services/storage/storage_report.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:neostation/services/storage/storage_scanner.dart';
import 'package:neostation/services/storage/storage_stat_ffi.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';
import 'package:share_plus/share_plus.dart';

import 'database_test_helper.dart';

/// docs/storage-audit-cleanup.md § 3.9 and test G of § 6, on a real
/// temporary container whose path holds a UUID: the aggregate export has
/// exact totals and no game, book or user name, no UUID, no absolute path and
/// never the hidden library folder; the detailed export adds relative paths,
/// still without UUID nor hidden folder; the text rendering is translated;
/// sharing goes through a temporary file of `tmp/`, removed afterwards.
void main() {
  const uuid = '5F0E7A21-0B6C-4D2E-8A41-1C2D3E4F5A6B';
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late Directory base;
  late Directory home;
  late Directory outside;
  late StorageContainers containers;
  late Map<String, int> written;

  String doc(String relative) => p.join(containers.documents, relative);
  String sup(String relative) =>
      p.join(containers.applicationSupport, relative);
  String cac(String relative) => p.join(containers.caches, relative);
  String tmp(String relative) => p.join(containers.temporary, relative);
  final hidden = LibrarySourceFiles.folderName;

  Future<void> write(String path, int length) async {
    final file = File(path);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(List<int>.filled(length, 1));
    written[path] = length;
  }

  setUp(() async {
    StorageStatFfi.resetSession();
    db = await helper.setUp();
    written = {};
    base = await Directory.systemTemp.createTemp('storage_report_');
    outside = await Directory.systemTemp.createTemp('storage_outside_');
    home = Directory(p.join(base.path, 'Containers/Data/Application/$uuid'));
    containers = StorageContainers(
      documents: p.join(home.path, 'Documents'),
      applicationSupport: p.join(home.path, 'Library', 'Application Support'),
      caches: p.join(home.path, 'Library', 'Caches'),
      temporary: p.join(home.path, 'tmp'),
    );
    for (final container in StorageContainer.values) {
      await Directory(containers.pathOf(container)).create(recursive: true);
    }
    await db.execute(
      'INSERT INTO app_systems (id, real_name, folder_name) VALUES (?, ?, ?)',
      ['snes', 'SNES', 'snes'],
    );
    await db.execute(
      'INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES (?, ?, ?)',
      ['snes', 'Super Mario World.sfc', doc('roms/snes/Super Mario World.sfc')],
    );
    await write(doc('roms/snes/Super Mario World.sfc'), 1000);
    await write(doc('roms/snes/Corentin Fourreau Hack.sfc'), 200);
    await write(doc('MyGames/snes/Super Mario World.sfc'), 1000);
    await write(doc('Library/Books/Dune.epub'), 300);
    await write(doc('Library/$hidden/neostation-source-mangadex.json'), 40);
    await write(doc('Libretro/Saves/Snes9x/Super Mario World.srm'), 50);
    await write(doc('user-data/temp/snes/Zelda.zip/Zelda.sfc'), 60);
    await write(tmp('Picked Game.zip'), 70);
    await write(sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'), 80);
    await write(cac('Library/library_images/cover.png'), 90);
    await write(doc('media/snes/box2d/Deleted Game.png'), 10);
    final secret = File(p.join(outside.path, 'secret.sfc'))
      ..writeAsBytesSync(List<int>.filled(5000, 1));
    await Link(doc('roms/snes/link.sfc')).create(secret.path);
  });

  tearDown(() async {
    StorageStatFfi.resetSession();
    StorageContainers.documentsDirectory = getApplicationDocumentsDirectory;
    await helper.tearDown();
    for (final directory in [base, outside]) {
      if (await directory.exists()) await directory.delete(recursive: true);
    }
  });

  Future<(StorageScanResult, StorageOrphanReport)> analyze() async {
    final registry = StorageRootRegistry(
      containers,
      libraryRoots: [doc('MyGames')],
    );
    final scan = await StorageScanner().scan(registry);
    final orphans = await StorageOrphanDetector(
      database: () async => db,
      registry: registry,
    ).detect(scan);
    return (scan, orphans);
  }

  /// No container UUID, no absolute path, never the hidden library folder.
  void expectAnonymous(String encoded) {
    for (final secret in [
      uuid,
      uuid.toLowerCase(),
      home.path,
      base.path,
      outside.path,
      hidden,
    ]) {
      expect(encoded, isNot(contains(secret)), reason: secret);
    }
  }

  /// Nothing that names a game, a book or the user either.
  void expectPrivate(String encoded) {
    for (final secret in [
      'Super Mario',
      'Corentin',
      'Fourreau',
      'Dune',
      'Zelda',
      'Picked Game',
      'Deleted Game',
      'mangadex',
      'MyGames',
      'secret',
    ]) {
      expect(encoded, isNot(contains(secret)), reason: secret);
    }
    expectAnonymous(encoded);
  }

  Map<String, Object?> rootOf(Map<String, Object?> report, String id) =>
      (report['roots']! as List).cast<Map<String, Object?>>().firstWhere(
        (root) => root['id'] == id,
      );

  int bytes(Object? totals) => (totals! as Map)['logicalBytes'] as int;

  test(
    'G — the aggregate export: exact totals, no name, no UUID, no hidden folder',
    () async {
      final (scan, orphans) = await analyze();
      final report = StorageReport.aggregate(scan, orphans: orphans);
      final encoded = StorageReport.encode(report);
      expectPrivate(encoded);
      expect(jsonDecode(encoded), report);
      expect(report['format'], StorageReport.format);
      expect(report['mode'], 'aggregate');
      expect(report['statViaFfi'], scan.statViaFfi);

      final total = written.values.fold<int>(0, (sum, value) => sum + value);
      final totals = report['totals']! as Map<String, Object?>;
      expect(totals['logicalBytes'], total);
      expect(totals['logicalBytes'], scan.logicalBytes);
      expect(totals['fileCount'], written.length);
      expect(totals['linkCount'], 1);
      if (scan.statViaFfi) {
        expect(totals['allocatedBytes'], scan.allocatedBytes);
      } else {
        expect(totals['allocatedBytes'], isNull);
      }

      expect(bytes(rootOf(report, 'INV-01')), 1000 + 200 + 1000);
      expect(rootOf(report, 'INV-01')['locations'], [
        '<Documents>/roms',
        '<library folder>',
      ]);
      expect(rootOf(report, 'INV-01')['linkCount'], 1);
      // The hidden library folder is counted in the Library root.
      expect(bytes(rootOf(report, 'INV-15')), 300 + 40);
      expect(rootOf(report, 'INV-15')['label'], StorageLocale.rootLibrary);
      expect(rootOf(report, 'INV-15')['locations'], ['<Documents>/Library']);
      expect(rootOf(report, 'INV-26')['label'], StorageLocale.rootLibrary);
      expect(rootOf(report, 'INV-18')['label'], StorageLocale.rootSupport);
      expect(bytes(rootOf(report, 'INV-14')), 50);
      expect(bytes(rootOf(report, 'INV-03')), 60);
      expect(bytes(rootOf(report, 'INV-28')), 70);
      expect(bytes(rootOf(report, 'INV-18')), 80);
      expect(bytes(rootOf(report, 'INV-26')), 90);
      expect(bytes(rootOf(report, 'INV-05')), 10);
      expect(
        ((report['roots']! as List).cast<Map<String, Object?>>()).fold<int>(
          0,
          (sum, root) => sum + (root['logicalBytes']! as int),
        ),
        total,
      );
      final library = rootOf(report, 'INV-15')['categories']! as Map;
      expect(library.keys, ['userContent']);
      expect(bytes(library['userContent']), 340);
      expect((library['userContent'] as Map)['fileCount'], 2);

      final byContainer = report['containers']! as Map<String, Object?>;
      expect(
        bytes(byContainer['<Documents>']),
        1000 + 200 + 1000 + 300 + 40 + 50 + 60 + 10,
      );
      expect(bytes(byContainer['<Support>']), 80);
      expect(bytes(byContainer['<Caches>']), 90);
      expect(bytes(byContainer['<tmp>']), 70);

      final categories = report['categories']! as Map<String, Object?>;
      expect(bytes(categories['games']), 2200);
      expect(bytes(categories['userContent']), 340);
      expect(bytes(categories['saves']), 50);
      expect(bytes(categories['temporary']), 60 + 70);
      expect(bytes(categories['caches']), 80 + 90);
      expect(bytes(categories['media']), 10);
      expect(report['temporaries'], categories['temporary']);

      final orphanTotals = report['orphans']! as Map<String, Object?>;
      expect(orphanTotals['media'], {'count': 1, 'logicalBytes': 10});
      expect(orphanTotals['metadata'], {'count': 0});
      expect(report['duplicates'], {
        'groups': 1,
        'copies': 2,
        'referencedCopies': 1,
        'selectableCopies': 1,
        'selectableBytes': 1000,
        'hashedGroups': 0,
      });
      expect(report['lastCleanup'], isNull);
      expect((report['inaccessible']! as Map)['count'], 0);
      expect((report['inaccessible']! as Map).containsKey('paths'), isFalse);
    },
  );

  test(
    'G — the detailed export: relative paths, never the UUID nor the hidden folder',
    () async {
      final (scan, orphans) = await analyze();
      final report = StorageReport.detailed(
        scan,
        orphans: orphans,
        maxEntriesPerRoot: 3,
      );
      final encoded = StorageReport.encode(report);
      expectAnonymous(encoded);
      expect(report['mode'], 'detailed');
      final roms = rootOf(report, 'INV-01')['largest']! as List;
      expect(roms, hasLength(3));
      expect(
        [for (final entry in roms) (entry as Map)['logicalBytes']],
        [1200, 1000, 1000],
      );
      // Largest first, then by path.
      expect(
        [for (final entry in roms) (entry as Map)['path']],
        [
          '<Documents>/roms/snes',
          '<Documents>/MyGames/snes',
          '<Documents>/MyGames/snes/Super Mario World.sfc',
        ],
      );
      final library = [
        for (final entry in rootOf(report, 'INV-15')['largest']! as List)
          (entry as Map)['path'],
      ];
      expect(library, [
        '<Documents>/Library/Books',
        '<Documents>/Library/Books/Dune.epub',
      ]);
      for (final root in (report['roots']! as List).cast<Map>()) {
        for (final entry in root['largest']! as List) {
          expect((entry as Map)['path'], startsWith('<'));
        }
      }
      // Totals are the aggregate's.
      final aggregate = StorageReport.aggregate(scan, orphans: orphans);
      expect(report['totals'], aggregate['totals']);
      expect(report['categories'], aggregate['categories']);
      expect((report['inaccessible']! as Map)['paths'], isEmpty);
    },
  );

  test('the last cleanup is summarized without any path', () async {
    final (scan, _) = await analyze();
    final result = StorageDeletionResult(
      deletedFiles: 3,
      deletedBytes: 1234,
      deletedDirectories: 2,
      skippedChanged: 1,
      skippedMissing: 2,
      refusals: [
        StoragePlanRefusal(
          path: doc('roms/snes/Super Mario World.sfc'),
          reason: StorageRefusalReason.isProtected,
          displayPath: '<Documents>/roms/snes/Super Mario World.sfc',
        ),
        StoragePlanRefusal(
          path: tmp('Picked Game.zip'),
          reason: StorageRefusalReason.accessDenied,
          detail: 'OS Error: Permission denied, errno = 13',
          errorCode: 13,
        ),
        StoragePlanRefusal(
          path: tmp('Other.zip'),
          reason: StorageRefusalReason.accessDenied,
        ),
      ],
      metadata: StorageMetadataDeletion(
        deleted: 4,
        skippedNotOrphan: 1,
        backupPath: sup('NeoStation/Maintenance/data-20261012-101010.sqlite'),
      ),
      journalPath: doc('Diagnostics/storage-cleanup-20261012-101010.jsonl'),
      journalDisplayPath:
          '<Documents>/Diagnostics/storage-cleanup-20261012-101010.jsonl',
      cancelled: false,
      clearedCaches: const [StorageCacheApi.libraryImages],
    );
    final report = StorageReport.aggregate(scan, lastCleanup: result);
    final encoded = StorageReport.encode(report);
    expectPrivate(encoded);
    expect(report['lastCleanup'], {
      'deletedFiles': 3,
      'deletedBytes': 1234,
      'deletedDirectories': 2,
      'skippedChanged': 1,
      'skippedMissing': 2,
      'refusals': {'isProtected': 1, 'accessDenied': 2},
      'metadataDeleted': 4,
      'metadataSkippedNotOrphan': 1,
      'clearedCaches': ['libraryImages'],
      'cancelled': false,
      'stoppedBySession': false,
      'journal':
          '<Documents>/Diagnostics/storage-cleanup-20261012-101010.jsonl',
    });
    expect(report['orphans'], isNull);
  });

  test('text: translated, sizes formatted, still private', () async {
    final (scan, orphans) = await analyze();
    for (final locale in const [Locale('fr'), Locale('ja'), Locale('en')]) {
      String t(String key) => StorageLocale.forLocale(locale, key);
      final text = StorageReport.text(
        StorageReport.aggregate(scan, orphans: orphans),
        t,
      );
      expectPrivate(text);
      expect(text, contains(t(StorageLocale.summary)));
      expect(text, contains(t(StorageLocale.rootLibrary)));
      expect(text, contains(t(StorageLocale.catGames)));
      expect(
        text,
        contains(
          StorageLocale.fill(t(StorageLocale.totalLogical), {
            'size': Rpcs3SaveExchangeService.formatBytes(scan.logicalBytes),
          }),
        ),
      );
      expect(
        text,
        contains(
          StorageLocale.fill(t(StorageLocale.orphanMedia), {
            'count': 1,
            'size': Rpcs3SaveExchangeService.formatBytes(10),
          }),
        ),
      );
      expect(text, contains('INV-15'));
      expect(text.contains(t(StorageLocale.limitFfi)), !scan.statViaFfi);
      expect(text, contains(t(StorageLocale.limitUnverified)));
      expect(text, isNot(contains('{')));
    }
    // A detailed rendering lists the relative paths.
    final detailed = StorageReport.text(
      StorageReport.detailed(scan, orphans: orphans, maxEntriesPerRoot: 1),
      (key) => StorageLocale.forLocale(const Locale('fr'), key),
    );
    expect(detailed, contains('<Documents>/roms/snes'));
    expectAnonymous(detailed);
  });

  test('share through a temporary file of tmp/, removed afterwards', () async {
    final (scan, orphans) = await analyze();
    final content = StorageReport.encode(
      StorageReport.aggregate(scan, orphans: orphans),
    );
    final name = StorageReport.fileNameFor(DateTime(2026, 10, 12, 10, 10, 10));
    expect(name, 'storage-report-20261012-101010.json');

    ShareParams? shared;
    String? seen;
    final sharer = StorageReportSharer(
      temporaryDirectory: () async => Directory(containers.temporary),
      share: (params) async {
        shared = params;
        seen = await File(params.files!.single.path).readAsString();
      },
    );
    await sharer.share(content, fileName: name);
    final file = shared!.files!.single;
    expect(file.path, tmp(name));
    expect(file.mimeType, 'application/json');
    expect(seen, content);
    expect(await File(tmp(name)).exists(), isFalse);

    // A failing share sheet: the error reaches the screen, the file goes.
    final failing = StorageReportSharer(
      temporaryDirectory: () async => Directory(containers.temporary),
      share: (params) async => throw StateError('no share sheet'),
    );
    await expectLater(
      failing.share(content, fileName: name),
      throwsA(isA<StateError>()),
    );
    expect(await File(tmp(name)).exists(), isFalse);

    // Only a bare file name is accepted.
    for (final invalid in ['', '.hidden.json', '../escape.json', 'a/b.json']) {
      await expectLater(
        sharer.share(content, fileName: invalid),
        throwsArgumentError,
        reason: invalid,
      );
    }
    expect(await File(p.join(home.path, 'escape.json')).exists(), isFalse);

    // By default the file goes to the container's tmp/, beside Documents
    // (not path_provider's temporary directory, Library/Caches on iOS).
    StorageContainers.documentsDirectory = () async =>
        Directory(containers.documents);
    String? defaultPath;
    await StorageReportSharer(
      share: (params) async {
        defaultPath = params.files!.single.path;
        expect(await File(defaultPath!).readAsString(), content);
      },
    ).share(content, fileName: name);
    expect(defaultPath, tmp(name));
    expect(await File(tmp(name)).exists(), isFalse);
  });
}
