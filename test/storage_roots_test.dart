import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/storage/storage_categorizer.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:path/path.dart' as p;

/// Registry of docs/storage-audit-cleanup.md § 3.1: 28 roots in table
/// order (INV-13, Dusklight, left with that engine:
/// docs/ports-removal-2026-10-20.md), deepest rule with the never-lists
/// first, library folders always protected, whitelist resolved, nothing
/// created.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  const home =
      '/var/mobile/Containers/Data/Application/0E1C1A55-6C55-4A5A-9C4F-6B7E8A9B0C1D';
  const containers = StorageContainers(
    documents: '$home/Documents',
    applicationSupport: '$home/Library/Application Support',
    caches: '$home/Library/Caches',
    temporary: '$home/tmp',
  );
  String doc(String relative) => p.join(containers.documents, relative);
  String sup(String relative) =>
      p.join(containers.applicationSupport, relative);
  String cac(String relative) => p.join(containers.caches, relative);
  String tmp(String relative) => p.join(containers.temporary, relative);

  StorageRootRegistry registry({
    List<String> libraryRoots = const [],
    String? linked,
    bool redirected = false,
    String? bundle,
  }) => StorageRootRegistry(
    containers,
    libraryRoots: libraryRoots,
    linkedExternalFolder: linked,
    rpcs3Redirected: redirected,
    bundleIdentifier: bundle,
  );

  test('exposes the 28 inventory roots in table order with allowed labels', () {
    final roots = registry().roots;
    expect(roots.map((root) => root.id), [
      for (var index = 1; index <= 29; index++)
        // INV-13 is retired with Dusklight; its id is not reused.
        if (index != 13) 'INV-${index.toString().padLeft(2, '0')}',
    ]);
    const labels = {
      'rootLibrary',
      'rootDocuments',
      'rootSupport',
      'rootCaches',
      'rootTemporary',
    };
    for (final root in roots) {
      expect(labels, contains(root.labelKey), reason: root.id);
      expect(root.rules, isNotEmpty, reason: root.id);
    }
    expect(
      roots
          .where((root) => root.labelKey == 'rootLibrary')
          .map((root) => root.id),
      ['INV-15', 'INV-23', 'INV-26'],
    );
  });

  test(
    'rule ids are unique and never name a game, a book or the hidden folder',
    () {
      final ids = <String>[];
      for (final root in registry(libraryRoots: [doc('MyGames')]).roots) {
        for (final rule in root.rules) {
          expect(rule.id, startsWith('${root.id}.'));
          ids.add(rule.id);
          expect(rule.id.toLowerCase(), isNot(contains('source')));
          expect(rule.labelKey?.toLowerCase() ?? '', isNot(contains('source')));
        }
      }
      expect(ids.toSet(), hasLength(ids.length));
      final hidden = registry().ruleFor(doc('Library/Sources/abc.json'))!;
      expect(hidden.id.toLowerCase(), isNot(contains('source')));
      expect(hidden.labelKey, 'rootLibrary');
      expect(hidden.aggregateOnly, isTrue);
    },
  );

  test('every scanned directory lies in a container and is owned once', () {
    final value = registry(
      libraryRoots: [doc('MyGames'), '/private/var/other/roms'],
    );
    final seen = <String>{};
    for (final location in value.locations) {
      final canonical = storageCanonicalPath(location.path);
      expect(seen.add(canonical), isTrue, reason: location.path);
      expect(containers.containerOf(location.path), location.container);
      expect(value.isRootPath(location.path), isTrue);
      expect(value.rootIdFor(location.path), location.rootId);
    }
    // Container remainders: Documents (INV-07), tmp (INV-28), Support and
    // Caches (INV-29).
    expect(value.rootIdFor(doc('NeoPlay.jsonl')), 'INV-07');
    expect(value.rootIdFor(tmp('picked.zip')), 'INV-28');
    expect(
      value.rootIdFor(sup('Roboto-Regular_0123456789abcdef.ttf')),
      'INV-29',
    );
    expect(
      value.rootIdFor(cac('com.neogamelab.neostation/fsCachedData/x')),
      'INV-29',
    );
  });

  test('the deepest location owns a path, rules decide its class', () {
    final value = registry(bundle: 'com.example.renamed');
    expect(
      value.rootIdFor(doc('user-data/temp/snes/Game.zip/Game.sfc')),
      'INV-03',
    );
    expect(value.rootIdFor(doc('user-data/background.png')), 'INV-02');
    expect(
      value.ruleFor(doc('user-data/background.png'))!.id,
      'INV-04.background',
    );
    expect(value.rootIdFor(doc('user-data/themes/epic/theme.xml')), 'INV-04');
    expect(
      value.rootIdFor(sup('NeoStation/RPCS3/Data/dev_hdd1/caches/x')),
      'INV-17',
    );
    expect(
      value.rootIdFor(sup('NeoStation/RPCS3/Data/dev_hdd0/game/X/EBOOT.BIN')),
      'INV-16',
    );
    expect(
      value.rootIdFor(sup('NeoStation/Dolphin/Library/gc/Game.rvz')),
      'INV-20',
    );
    expect(value.rootIdFor(sup('NeoStation/Dolphin/User/Wii/x')), 'INV-21');
    expect(
      value.rootIdFor(sup('NeoStation/Dolphin/Logs/dolphin-persistent.jsonl')),
      'INV-22',
    );
    expect(
      value.rootIdFor(
        sup('NeoStation/Maintenance/data-20261012-101010.sqlite'),
      ),
      'INV-02',
    );
    expect(value.rootIdFor(cac('KartPad/shaders/x')), 'INV-12');
    expect(value.rootIdFor(cac('SoLoudLoader-Temp-Files/x')), 'INV-28');
    expect(
      value.ruleFor(cac('com.example.renamed/fsCachedData/a'))!.id,
      'INV-29.urlCache',
    );
    expect(
      value.ruleFor(cac('com.neogamelab.neostation/fsCachedData/a')),
      isNull,
    );
    expect(
      registry().ruleFor(cac('com.neogamelab.neostation.ABCDE12345/x'))!.id,
      'INV-29.urlCache',
    );
  });

  test('deepest rule wins, never-list entries come first', () {
    final value = registry();
    String? id(String path) => value.ruleFor(path)?.id;
    expect(id(doc('Libretro/Saves/snes9x/Game.srm')), 'INV-14.saves');
    expect(
      id(doc('Libretro/Skins/.staging/abc/info.json')),
      'INV-14.skinStaging',
    );
    expect(id(doc('Libretro/Skins/abc/info.json')), 'INV-14.skins');
    expect(id(doc('Ports/KartPad/Games/RMCP01.wbfs')), 'INV-12.games');
    expect(id(doc('Ports/KartPad/Games/RMCP01.wbfs.part')), 'INV-12.gamePart');
    expect(
      id(doc('Ports/KartPad/Runtime/GameData/files/x')),
      'INV-12.gameData',
    );
    expect(
      id(doc('Ports/KartPad/Runtime/GameData.import-1234/x')),
      'INV-12.gameDataStaging',
    );
    expect(
      id(tmp('NeoStation-Dolphin-FramePacing.json')),
      'INV-28.framePacing',
    );
    expect(
      id(tmp('com.neogamelab.neostation-Inbox/Game.zip')),
      'INV-28.pickerInbox',
    );
    expect(id(tmp('Game.zip')), 'INV-28.temporary');
    expect(
      id(sup('NeoStation/Dolphin/Logs/dolphin-2026-10-12T10-00-00.000Z.jsonl')),
      'INV-22.sessionLog',
    );
    expect(
      id(sup('NeoStation/Dolphin/Logs/dolphin-persistent.jsonl')),
      'INV-22.persistentLog',
    );
    expect(
      id(
        sup(
          'NeoStation/Dolphin/CrashMarkers/active-session.json.1760000000000.recovered',
        ),
      ),
      'INV-22.recoveredMarker',
    );
    // Never-lists before the deeper rule.
    expect(id(doc('Libretro/System/scph5501.bin')), 'NEVER.libretroSystem');
    expect(id(doc('user-data/data.sqlite-wal')), 'NEVER.sqlite');
    expect(
      id(sup('NeoStation/Dolphin/CrashMarkers/active-session.json')),
      'NEVER.dolphinActiveMarker',
    );
    expect(
      id(
        sup(
          'NeoStation/RPCS3/Data/dev_hdd0/home/00000001/savedata/BLES00113/PARAM.SFO',
        ),
      ),
      'NEVER.savedata',
    );
    expect(id(cac('NeoSwap-v1/blob')), 'NEVER.neoSwap');
    expect(id(cac('NeoSwap-v9/blob')), 'NEVER.neoSwap');
    // The § 3.6 backups are the only exemption of *.sqlite*.
    expect(
      id(sup('NeoStation/Maintenance/data-20261012-101010.sqlite')),
      'INV-02.maintenanceBackup',
    );
    expect(
      id(sup('NeoStation/Maintenance/data-20261012-101010-2.sqlite')),
      'INV-02.maintenanceBackup',
    );
    expect(id(sup('NeoStation/Maintenance/other.sqlite')), 'NEVER.sqlite');
    expect(
      id(sup('NeoStation/Maintenance/sub/data-20261012-101010.sqlite')),
      'NEVER.sqlite',
    );
    // Unknown paths have no rule.
    expect(id(doc('whatever.bin')), isNull);
    expect(id(doc('Libretro/Unknown/x')), isNull);
    expect(id(sup('NeoStation/Unknown/x')), isNull);
    expect(id('/elsewhere/file'), isNull);
  });

  test(
    'library folders and the linked folder are protected wherever they are',
    () {
      final value = registry(
        libraryRoots: [
          doc('MyGames'),
          doc('ARMSX2/Games'),
          '/mnt/external/roms',
        ],
        linked: '/var/mobile/Containers/Data/Application/RETROARCH/Documents',
      );
      // Measured only inside a container and outside the other roots.
      final inv01 = value.locations.where(
        (location) => location.rootId == 'INV-01',
      );
      expect(inv01.map((location) => location.relative), ['roms', 'MyGames']);
      for (final path in [
        doc('MyGames/snes/Game.sfc'),
        doc('ARMSX2/Games/Game.iso'),
        '/mnt/external/roms/snes/Game.sfc',
        '/var/mobile/Containers/Data/Application/RETROARCH/Documents/Game.zip',
        '/private/var/mobile/Containers/Data/Application/RETROARCH/Documents/Game.zip',
      ]) {
        expect(value.isProtected(path), isTrue, reason: path);
      }
      expect(
        value.ruleFor('/mnt/external/roms/a.sfc')!.id,
        'NEVER.libraryRoot',
      );
      expect(value.ruleFor(doc('MyGames/a.sfc'))!.id, 'NEVER.libraryRoot');
    },
  );

  test(
    'isProtected follows the categorizer, deletable paths stay deletable',
    () {
      final value = registry();
      for (final path in [
        containers.documents,
        containers.temporary,
        doc('roms'),
        doc('Library'),
        doc('Library/Sources'),
        doc('Library/Sources/neostation-source.json'),
        doc('Libretro/Saves/snes9x/Game.srm'),
        sup('StikJIT/pairing.mobiledevicepairing'),
        doc('unknown.bin'),
        doc('roms/snes/.Game.sfc.icloud'),
      ]) {
        expect(value.isProtected(path), isTrue, reason: path);
      }
      for (final path in [
        tmp('Game.zip'),
        cac('Libretro/SkinCache/abc.png'),
        doc('Diagnostics/rpcs3_startup_debug.txt'),
        doc('media/snes/box2d/Game.png'),
        sup('NeoStation/RPCS3/Cache/ppu-x.obj'),
      ]) {
        expect(value.isProtected(path), isFalse, reason: path);
      }
    },
  );

  test('a redirected RPCS3 tree protects every RPCS3 root', () {
    final open = registry();
    final redirected = registry(redirected: true);
    // Contract replaced by the review of the storage services: the save
    // backups (`SaveBackups`) used to be unprotected in an open tree (level
    // 3); they are backups of user data, protected by their own rule
    // whether the tree is redirected or not (below).
    for (final path in [
      sup('NeoStation/RPCS3/Cache/ppu-x.obj'),
      sup('NeoStation/RPCS3/Data/dev_hdd0/tmp/x'),
      sup('NeoStation/RPCS3/Data/dev_hdd1/x'),
      sup('NeoStation/RPCS3/Imports/PS3UPDAT-1.PUP'),
    ]) {
      expect(open.isProtected(path), isFalse, reason: path);
    }
    for (final path in [
      sup('NeoStation/RPCS3/Cache/ppu-x.obj'),
      sup('NeoStation/RPCS3/Data/dev_hdd0/tmp/x'),
      sup('NeoStation/RPCS3/Data/dev_hdd1/x'),
      sup('NeoStation/RPCS3/Imports/PS3UPDAT-1.PUP'),
      sup('NeoStation/RPCS3/SaveBackups/BLES-1/x'),
    ]) {
      expect(redirected.isProtected(path), isTrue, reason: path);
      expect(redirected.isRpcs3Path(path), isTrue, reason: path);
      expect(
        StorageCategorizer(
          redirected,
        ).classify(path, StorageEntryKind.file).protectedReason,
        StorageProtectedReason.rpcs3Redirected,
      );
    }
    final saveBackup = StorageCategorizer(open).classify(
      sup('NeoStation/RPCS3/SaveBackups/BLES-1/x'),
      StorageEntryKind.file,
    );
    expect(saveBackup.deletionClass, StorageDeletionClass.never);
    expect(saveBackup.protectedReason, StorageProtectedReason.rule);
    expect(saveBackup.ruleId, 'INV-19.saveBackups');
    expect(redirected.isProtected(tmp('Game.zip')), isFalse);
  });

  test('/var and /private/var name the same container', () {
    final value = registry();
    const resolved = '/private$home';
    expect(
      value.ruleFor('$resolved/Documents/Libretro/Saves/a/b.srm')!.id,
      'INV-14.saves',
    );
    expect(value.rootIdFor('$resolved/tmp/x.zip'), 'INV-28');
    expect(value.isRootPath('$resolved/Documents/roms'), isTrue);
    expect(value.isContainerPath('$resolved/Library/Caches'), isTrue);
    expect(
      containers.displayPathOf('$resolved/Library/Caches/Libretro/x'),
      '<Caches>/Libretro/x',
    );
  });

  test('containers locate, relativize and display paths', () {
    expect(containers.containerOf(doc('a/b')), StorageContainer.documents);
    expect(containers.containerOf('/elsewhere'), isNull);
    expect(
      containers.relativePathOf(sup('NeoStation/RPCS3')),
      'NeoStation/RPCS3',
    );
    expect(containers.relativePathOf(containers.temporary), '');
    expect(containers.displayPathOf(tmp('x/y')), '<tmp>/x/y');
    expect(
      containers.displayPathOf(containers.applicationSupport),
      '<Support>',
    );
    expect(containers.displayPathOf('/elsewhere'), isNull);
  });

  test(
    'resolvedRootPaths resolves links, missing roots through their parent',
    () async {
      final temp = await Directory.systemTemp.createTemp('storage_roots_');
      addTearDown(() => temp.delete(recursive: true));
      final real = await Directory(p.join(temp.path, 'real-home')).create();
      for (final relative in [
        'Documents',
        'Library/Application Support',
        'Library/Caches',
        'tmp',
      ]) {
        await Directory(p.join(real.path, relative)).create(recursive: true);
      }
      final link = await Link(p.join(temp.path, 'home')).create(real.path);
      final linked = StorageContainers(
        documents: p.join(link.path, 'Documents'),
        applicationSupport: p.join(link.path, 'Library/Application Support'),
        caches: p.join(link.path, 'Library/Caches'),
        temporary: p.join(link.path, 'tmp'),
      );
      final value = StorageRootRegistry(linked);
      final resolvedReal = await real.resolveSymbolicLinks();
      final whitelist = value.resolvedRootPaths;
      expect(whitelist, contains(p.join(resolvedReal, 'Documents')));
      // Documents/roms does not exist: resolved through Documents.
      expect(whitelist, contains(p.join(resolvedReal, 'Documents', 'roms')));
      expect(whitelist.every((path) => !path.startsWith(link.path)), isTrue);
      // Nothing was created by the registry.
      expect(
        await Directory(p.join(real.path, 'Documents', 'roms')).exists(),
        isFalse,
      );
      expect(await Directory(real.path).list(recursive: true).length, 5);
    },
  );

  test(
    'StorageContainers.resolve: tmp/ is next to Documents, never getTemporaryDirectory()',
    () async {
      const channel = MethodChannel('plugins.flutter.io/path_provider');
      final messenger =
          TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      final calls = <String>[];
      messenger.setMockMethodCallHandler(channel, (call) async {
        calls.add(call.method);
        return switch (call.method) {
          'getApplicationDocumentsDirectory' => '/c/Documents',
          'getApplicationSupportDirectory' => '/c/Library/Application Support',
          'getApplicationCacheDirectory' => '/c/Library/Caches',
          // What path_provider_foundation answers on iOS (NSCachesDirectory).
          'getTemporaryDirectory' => '/c/Library/Caches',
          _ => null,
        };
      });
      addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
      final resolved = await StorageContainers.resolve();
      expect(resolved.documents, '/c/Documents');
      expect(resolved.applicationSupport, '/c/Library/Application Support');
      expect(resolved.caches, '/c/Library/Caches');
      expect(resolved.temporary, '/c/tmp');
      expect((await StorageContainers.temporaryDirectory()).path, '/c/tmp');
      expect(calls, isNot(contains('getTemporaryDirectory')));
      expect(calls.toSet(), {
        'getApplicationDocumentsDirectory',
        'getApplicationSupportDirectory',
        'getApplicationCacheDirectory',
      });
    },
  );

  test('the test seams replace the path_provider calls', () async {
    final previous = (
      StorageContainers.documentsDirectory,
      StorageContainers.supportDirectory,
      StorageContainers.cacheDirectory,
    );
    addTearDown(() {
      StorageContainers.documentsDirectory = previous.$1;
      StorageContainers.supportDirectory = previous.$2;
      StorageContainers.cacheDirectory = previous.$3;
    });
    StorageContainers.documentsDirectory = () async =>
        Directory('/seam/home/Documents/');
    StorageContainers.supportDirectory = () async =>
        Directory('/seam/home/Library/Application Support');
    StorageContainers.cacheDirectory = () async =>
        Directory('/seam/home/Library/Caches');
    final resolved = await StorageContainers.resolve();
    expect(resolved.temporary, '/seam/home/tmp');
    expect(resolved.caches, '/seam/home/Library/Caches');
  });

  test(
    'engine caches built on getTemporaryDirectory() are classified under Caches',
    () {
      final value = registry();
      final categorizer = StorageCategorizer(value);
      for (final (path, root, rule) in [
        (cac('KartPad/pipeline.bin'), 'INV-12', 'INV-12.cache'),
        (cac('SoLoudLoader-Temp-Files/x.wav'), 'INV-28', 'INV-28.soloudCache'),
        (cac('scan_-123456.mp3'), 'INV-29', 'INV-28.musicCopy'),
      ]) {
        final classification = categorizer.classify(
          path,
          StorageEntryKind.file,
        );
        expect(classification.rootId, root, reason: path);
        expect(classification.ruleId, rule, reason: path);
        expect(
          classification.deletionClass,
          StorageDeletionClass.temporaryWhenIdle,
          reason: path,
        );
      }
      // A KartPad folder in the real tmp/ is just a temporary of INV-28.
      expect(value.ruleFor(tmp('KartPad/x'))!.id, 'INV-28.temporary');
    },
  );

  test('what Dusklight left is unknown, hence never deletable', () {
    // Dusklight and the Ports playlist were removed
    // (docs/ports-removal-2026-10-20.md): its games, saves, settings, mods
    // and caches stay where they were, outside every rule, and nothing
    // proposes them.
    final value = registry();
    final categorizer = StorageCategorizer(value);
    for (final path in [
      doc('Ports/Dusklight/Games/GZ2E01.rvz'),
      doc('Ports/Dusklight/Games/GZ2E01.rvz.part'),
      doc('Ports/Dusklight/Saves/save.bin'),
      doc('Ports/Dusklight/Config/settings.json'),
      doc('Ports/Dusklight/Mods/x'),
      cac('Dusklight/shaders/x'),
    ]) {
      expect(value.ruleFor(path), isNull, reason: path);
      final classification = categorizer.classify(path, StorageEntryKind.file);
      expect(classification.category, StorageCategory.unknown, reason: path);
      expect(
        classification.deletionClass,
        StorageDeletionClass.never,
        reason: path,
      );
      expect(
        classification.protectedReason,
        StorageProtectedReason.unknown,
        reason: path,
      );
    }
    // The database copy made before the Ports rows left data.sqlite is
    // protected by the *.sqlite never-list (only the maintenance rotation's
    // own data-<stamp>.sqlite copies are exempt from it, and those are
    // never proposed either).
    final copy = categorizer.classify(
      sup('NeoStation/Maintenance/data-before-ports-removal-20261020-101010.sqlite'),
      StorageEntryKind.file,
    );
    expect(copy.deletionClass, StorageDeletionClass.never);
    expect(copy.ruleId, 'NEVER.sqlite');
  });

  test('3DS backups are never proposed, staging is temporary, the NAND stays '
      'never', () {
    final categorizer = StorageCategorizer(registry());
    StorageClassification of(String relative) =>
        categorizer.classify(doc(relative), StorageEntryKind.file);
    final backup = of(
      'Libretro/Backups/Azahar/20261012-101010/sysdata/keys.txt',
    );
    expect(backup.ruleId, 'INV-14.3dsBackups');
    expect(backup.category, StorageCategory.userContent);
    // Contract replaced by the review of the storage services: the 3DS
    // backups used to need a detailed confirmation (level 3); they may hold
    // the only copy of console-unique files and are never proposed now.
    expect(backup.deletionClass, StorageDeletionClass.never);
    expect(backup.protectedReason, StorageProtectedReason.rule);
    for (final staging in [
      'Libretro/Saves/Azahar/.neostation-3ds-import-20261012-101010/nand/x',
      'Libretro/Saves/Azahar/.neostation-3ds-restore-20261012-101010',
    ]) {
      final value = of(staging);
      expect(value.ruleId, 'INV-14.3dsStaging', reason: staging);
      expect(value.category, StorageCategory.temporary);
      expect(value.deletionClass, StorageDeletionClass.temporaryWhenIdle);
    }
    for (final kept in [
      'Libretro/Saves/Azahar/Azahar/nand/00000000000000000000000000000000/title/x',
      'Libretro/Saves/Azahar/Azahar/sysdata/keys.txt',
      'Libretro/Saves/Azahar/.other-staging/x',
    ]) {
      expect(of(kept).deletionClass, StorageDeletionClass.never, reason: kept);
    }
  });

  // Review of the storage services (12 October 2026): the copies NeoStation
  // makes of user data before replacing or removing it are never proposed,
  // whatever the level, wherever they are and whatever their file kind.
  test('the NeoStation backups of user data are never proposed', () {
    final categorizer = StorageCategorizer(registry());
    for (final (path, rule) in [
      (
        sup('NeoStation/Maintenance/data-20261012-101010.sqlite'),
        'INV-02.maintenanceBackup',
      ),
      (
        sup('NeoStation/Maintenance/data-20261012-101010-2.sqlite'),
        'INV-02.maintenanceBackup',
      ),
      (
        sup('NeoStation/RPCS3/SaveBackups/BLES00113-SAVE-1/PARAM.SFO'),
        'INV-19.saveBackups',
      ),
      (
        sup(
          'NeoStation/RPCS3/RapBackups/EP0001-NPEB00001_00-0000000000000001.rap',
        ),
        'INV-19.rapBackups',
      ),
      (
        doc('Libretro/Backups/Azahar/20261012-101010/nand/x'),
        'INV-14.3dsBackups',
      ),
    ]) {
      for (final kind in [StorageEntryKind.file, StorageEntryKind.directory]) {
        final value = categorizer.classify(path, kind);
        expect(value.ruleId, rule, reason: path);
        expect(value.deletionClass, StorageDeletionClass.never, reason: path);
        expect(value.protectedReason, StorageProtectedReason.rule);
      }
      // Their folders too.
      expect(
        categorizer
            .classify(p.dirname(path), StorageEntryKind.directory)
            .deletionClass,
        StorageDeletionClass.never,
        reason: p.dirname(path),
      );
    }
    // A `.part` beside them keeps their class (user content).
    expect(
      categorizer
          .classify(
            sup('NeoStation/RPCS3/SaveBackups/BLES00113-SAVE-1/x.part'),
            StorageEntryKind.file,
          )
          .deletionClass,
      StorageDeletionClass.never,
    );
  });

  // Review of the storage services: NSURLCache keeps its index in an open
  // SQLite database beside `fsCachedData`; removing it under the system's
  // feet is never proposed (the Library cache API empties the cache).
  test(
    'the URL cache database is never, the cached data stays regenerable',
    () {
      for (final (value, bundle) in [
        (registry(bundle: 'com.example.renamed'), 'com.example.renamed'),
        (registry(), 'com.neogamelab.neostation.ABCDE12345'),
      ]) {
        final categorizer = StorageCategorizer(value);
        for (final name in ['Cache.db', 'Cache.db-wal', 'Cache.db-shm']) {
          final classification = categorizer.classify(
            cac('$bundle/$name'),
            StorageEntryKind.file,
          );
          expect(classification.ruleId, 'NEVER.urlCacheDatabase', reason: name);
          expect(
            classification.deletionClass,
            StorageDeletionClass.never,
            reason: name,
          );
          expect(
            classification.protectedReason,
            StorageProtectedReason.neverList,
          );
          expect(classification.category, StorageCategory.caches);
          expect(value.isProtected(cac('$bundle/$name')), isTrue, reason: name);
        }
        final data = categorizer.classify(
          cac('$bundle/fsCachedData/0A1B2C3D'),
          StorageEntryKind.file,
        );
        expect(data.ruleId, 'INV-29.urlCache');
        expect(data.deletionClass, StorageDeletionClass.regenerableAtCost);
        // Names that only start like it are not the database.
        expect(
          categorizer
              .classify(
                cac('$bundle/fsCachedData/Cache.dbx'),
                StorageEntryKind.file,
              )
              .deletionClass,
          StorageDeletionClass.regenerableAtCost,
        );
      }
    },
  );
}
