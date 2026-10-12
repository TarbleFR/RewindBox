import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/storage_locale.dart';
import 'package:neostation/repositories/storage_maintenance_repository.dart';
import 'package:neostation/services/library_source_files.dart';
import 'package:neostation/services/rpcs3_internal_service.dart';
import 'package:neostation/services/storage/storage_cleanup_planner.dart';
import 'package:neostation/services/storage/storage_deletion_manager.dart';
import 'package:neostation/services/storage/storage_import_activity.dart';
import 'package:neostation/services/storage/storage_orphan_detector.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:neostation/services/storage/storage_scanner.dart';
import 'package:neostation/services/storage/storage_stat_ffi.dart';
import 'package:path/path.dart' as p;
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

import 'database_test_helper.dart';

/// docs/storage-audit-cleanup.md § 3.8 and tests C, E and F of § 6
/// (deletion side), on real temporary trees: nothing is deleted without a
/// plan and a selection, level 3 starts with nothing ticked; links escaping a root,
/// roots, protected folders and paths outside the whitelist are refused even
/// in a forged plan; a file changed since the preview is kept, ENOENT is
/// tolerated, EACCES/EPERM keep their raw text; the session guard (a game or
/// an import) before the start and every 50 files, the libretro and Dolphin
/// exclusions, the RPCS3
/// guard (`gameRunning`, `libraryBusy`, redirection), the cancellation, the
/// journal (relative paths, 20 files at most), the duplicate exception, the
/// metadata rows and the Library caches through their API.
void main() {
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late Directory home;
  late Directory outside;
  late StorageContainers containers;
  late DateTime now;
  late DateTime clock;

  String doc(String relative) => p.join(containers.documents, relative);
  String sup(String relative) =>
      p.join(containers.applicationSupport, relative);
  String cac(String relative) => p.join(containers.caches, relative);
  String tmp(String relative) => p.join(containers.temporary, relative);
  String data(String relative) =>
      sup(p.join('NeoStation/RPCS3/Data', relative));
  String dolphin(String relative) =>
      sup(p.join('NeoStation/Dolphin', relative));
  final hiddenFolder = p.join('Library', LibrarySourceFiles.folderName);

  Future<File> write(String path, {int length = 8, Duration? age}) async {
    final file = File(path);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(List<int>.filled(length, 7));
    if (age != null) await file.setLastModified(now.subtract(age));
    return file;
  }

  setUp(() async {
    StorageStatFfi.resetSession();
    Rpcs3InternalService.saveExchangeCoreInitializedOverride = false;
    now = DateTime.now().add(const Duration(days: 2));
    clock = DateTime(2026, 10, 12, 10, 10, 10);
    db = await helper.setUp();
    home = await Directory.systemTemp.createTemp('storage_deletion_');
    outside = await Directory.systemTemp.createTemp('storage_outside_');
    containers = StorageContainers(
      documents: p.join(home.path, 'Documents'),
      applicationSupport: p.join(home.path, 'Library', 'Application Support'),
      caches: p.join(home.path, 'Library', 'Caches'),
      temporary: p.join(home.path, 'tmp'),
    );
    for (final container in StorageContainer.values) {
      await Directory(containers.pathOf(container)).create(recursive: true);
    }
    await Directory(doc('Diagnostics')).create(recursive: true);
    await db.execute(
      'INSERT INTO app_systems (id, real_name, folder_name) VALUES (?, ?, ?)',
      ['snes', 'SNES', 'snes'],
    );
  });

  tearDown(() async {
    StorageStatFfi.resetSession();
    Rpcs3InternalService.saveExchangeCoreInitializedOverride = null;
    Rpcs3InternalService.saveExchangeEmulationState =
        Rpcs3InternalBridge.emulationState;
    await helper.tearDown();
    for (final directory in [home, outside]) {
      if (await directory.exists()) await directory.delete(recursive: true);
    }
  });

  StorageSessionGuard guard({
    bool Function()? launch,
    Future<bool> Function()? libretro,
    Future<bool> Function()? dolphinMarker,
  }) => StorageSessionGuard(
    launchActive: launch ?? () => false,
    libretroActive: libretro ?? () async => false,
    dolphinMarkerPresent: dolphinMarker ?? () async => false,
    libretroJournalUnfinished: () async => false,
  );

  Future<(StorageCleanupPlan, StorageRootRegistry)> planFor(
    StorageCleanupLevel level, {
    List<String> libraryRoots = const [],
  }) async {
    final registry = StorageRootRegistry(
      containers,
      libraryRoots: libraryRoots,
    );
    final scan = await StorageScanner().scan(registry);
    final orphans = await StorageOrphanDetector(
      database: () async => db,
      registry: registry,
    ).detect(scan);
    final plan = await StorageCleanupPlanner(
      registry: registry,
      guard: guard(),
      now: () => now,
    ).plan(scan, orphans, level);
    return (plan, registry);
  }

  StorageDeletionManager manager(
    StorageRootRegistry registry, {
    StorageSessionGuard? sessions,
    Future<void> Function(String path)? deleteFile,
    StorageRpcs3Guard? rpcs3Guard,
    Future<bool> Function()? rpcs3Redirected,
    int journalLimit = 20,
  }) => StorageDeletionManager(
    registry: registry,
    guard: sessions ?? guard(),
    deleteFile: deleteFile,
    journalDirectory: () async => doc('Diagnostics'),
    now: () => clock,
    journalLimit: journalLimit,
    rpcs3Guard: rpcs3Guard,
    rpcs3Redirected: rpcs3Redirected ?? () async => false,
  );

  /// Every entry of the container (journals of the manager left out).
  Future<Map<String, int>> tree() async {
    final result = <String, int>{};
    await for (final entity in home.list(recursive: true, followLinks: false)) {
      if (StorageDeletionManager.journalName.hasMatch(
        p.basename(entity.path),
      )) {
        continue;
      }
      result[entity.path] = entity is File ? await entity.length() : -1;
    }
    return result;
  }

  Future<List<Map<String, Object?>>> journalOf(
    StorageDeletionResult result,
  ) async => [
    for (final line in await File(result.journalPath).readAsLines())
      if (line.trim().isNotEmpty) jsonDecode(line) as Map<String, Object?>,
  ];

  /// Journal lines never hold an absolute path.
  void expectRelative(List<Map<String, Object?>> lines) {
    expect(lines.first['op'], 'begin');
    expect(lines.last['op'], 'end');
    for (final line in lines) {
      expect(
        line['op'],
        isIn(const ['begin', 'delete', 'skip', 'refuse', 'metadata', 'end']),
      );
      final text = jsonEncode(line);
      expect(text, isNot(contains(home.path)));
      expect(text, isNot(contains(outside.path)));
      final path = line['path'];
      if (path != null) {
        expect(
          path,
          anyOf(startsWith('<'), StorageCleanupPlan.metadataSelectionKey),
        );
      }
      expect(line['t'], isA<String>());
      expect(DateTime.tryParse(line['t']! as String), isNotNull);
    }
  }

  Set<StorageRefusalReason> reasonsOf(StorageDeletionResult result) => {
    for (final refusal in result.refusals) refusal.reason,
  };

  StorageCleanupCandidate candidateOf(StorageCleanupPlan plan, String path) =>
      plan.candidates.firstWhere((value) => value.path == path);

  Set<String> paths(StorageCleanupPlan plan) => {
    for (final candidate in plan.candidates) candidate.path,
  };

  /// A candidate the planner would never produce (path checks only).
  Future<StorageCleanupCandidate> forged(
    String path, {
    StorageEntryKind kind = StorageEntryKind.file,
    StorageCandidateSource source = StorageCandidateSource.rule,
    String rootId = 'INV-03',
    String? pairedPath,
  }) async {
    final stat = await FileStat.stat(path);
    final exists = stat.type != FileSystemEntityType.notFound;
    return StorageCleanupCandidate(
      path: path,
      kind: kind,
      logicalBytes: exists && kind == StorageEntryKind.file ? stat.size : 0,
      modified: exists ? stat.modified : DateTime(2000),
      category: StorageCategory.temporary,
      deletionClass: StorageDeletionClass.temporaryWhenIdle,
      reasonKey: StorageLocale.catTemporary,
      preselected: true,
      level: StorageCleanupLevel.safe,
      source: source,
      rootId: rootId,
      container: containers.containerOf(path) ?? StorageContainer.documents,
      relativePath: containers.relativePathOf(path) ?? 'outside',
      fileCount: kind == StorageEntryKind.file ? 1 : 0,
      pairedPath: pairedPath,
      entries: [
        StorageCandidateEntry(
          path: path,
          kind: kind,
          logicalBytes: exists && kind == StorageEntryKind.file ? stat.size : 0,
          modified: exists ? stat.modified : null,
        ),
      ],
    );
  }

  StorageCleanupPlan forgedPlan(List<StorageCleanupCandidate> candidates) =>
      StorageCleanupPlan(
        level: StorageCleanupLevel.confirmed,
        builtAt: now,
        candidates: candidates,
        metadataKeys: const [],
        refusals: const [],
        containers: containers,
      );

  test('C — nothing is deleted without a plan and a selection', () async {
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    await write(doc('user-data/temp/snes/Game.zip/Game.sfc'));
    await write(doc('Diagnostics/old.txt'));
    await write(doc('roms/snes/Super Mario World.sfc'));
    await write(p.join(outside.path, 'mine.bin'));
    final (plan, registry) = await planFor(StorageCleanupLevel.confirmed);
    expect(plan.candidates, isNotEmpty);
    final before = await tree();

    var result = await manager(registry).execute(plan, selectedPaths: {});
    expect(result.deletedFiles, 0);
    expect(result.refusals, isEmpty);
    expect(await tree(), before);
    var lines = await journalOf(result);
    expect([for (final line in lines) line['op']], ['begin', 'end']);
    expect(lines.first['launchActive'], isFalse);
    expectRelative(lines);

    result = await manager(registry).execute(
      plan,
      selectedPaths: {
        doc('roms/snes/Super Mario World.sfc'),
        p.join(outside.path, 'mine.bin'),
        '/etc/hosts',
      },
    );
    expect(result.deletedFiles, 0);
    expect(result.refusals, hasLength(3));
    expect(reasonsOf(result), {StorageRefusalReason.notInPlan});
    expect(await tree(), before);
    lines = await journalOf(result);
    expectRelative(lines);
    expect(
      {
        for (final line in lines)
          if (line['op'] == 'refuse') line['path'],
      },
      {'<Documents>/roms/snes/Super Mario World.sfc', '<outside>'},
    );

    // A path of level 3 is not part of a level-1 plan.
    final (safe, _) = await planFor(StorageCleanupLevel.safe);
    result = await manager(
      registry,
    ).execute(safe, selectedPaths: {doc('Diagnostics/old.txt')});
    expect(reasonsOf(result), {StorageRefusalReason.notInPlan});
    expect(await File(doc('Diagnostics/old.txt')).exists(), isTrue);
  });

  test('C — level 3 starts unchecked: its preselection is empty, only the '
      'ticked items go', () async {
    await db.execute(
      'INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES (?, ?, ?)',
      ['snes', 'Super Mario World.sfc', doc('roms/snes/Super Mario World.sfc')],
    );
    await write(doc('roms/snes/Super Mario World.sfc'), length: 100);
    await write(doc('MyGames/snes/Super Mario World.sfc'), length: 100);
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    await write(dolphin('ShaderCache/GALE01.uidcache'));
    await write(doc('Diagnostics/old.txt'));
    final (plan, registry) = await planFor(
      StorageCleanupLevel.confirmed,
      libraryRoots: [doc('MyGames')],
    );
    final level3 = {
      for (final value in plan.candidates)
        if (value.level == StorageCleanupLevel.confirmed) value.path,
    };
    expect(level3, {
      doc('Diagnostics/old.txt'),
      doc('MyGames/snes/Super Mario World.sfc'),
    });
    // Review of phase 5d: a level-3 plan preselects nothing at all (its
    // level-1 and level-2 lines used to be ticked): run as it opens, the
    // preview deletes nothing.
    expect(plan.preselectedPaths, isEmpty);
    final before = await tree();
    var result = await manager(
      registry,
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(result.deletedFiles, 0);
    expect(result.refusals, isEmpty);
    expect(await tree(), before);

    // The user ticks the two lower-level items: exactly they go.
    final lower = {
      for (final value in plan.candidates)
        if (value.level != StorageCleanupLevel.confirmed) value.path,
    };
    expect(lower, {tmp('picked.zip'), dolphin('ShaderCache/GALE01.uidcache')});
    result = await manager(registry).execute(plan, selectedPaths: lower);
    expect(result.deletedFiles, 2);
    expect(await File(tmp('picked.zip')).exists(), isFalse);
    expect(
      await File(dolphin('ShaderCache/GALE01.uidcache')).exists(),
      isFalse,
    );
    for (final path in level3) {
      expect(await File(path).exists(), isTrue, reason: path);
    }
    expect(await File(doc('roms/snes/Super Mario World.sfc')).exists(), isTrue);
  });

  test(
    'deletes file by file, empties folders, exact counts, relative journal',
    () async {
      await write(tmp('picked.zip'), length: 10, age: const Duration(hours: 1));
      await write(doc('user-data/temp/snes/Game.zip/Game.sfc'), length: 300);
      await write(doc('user-data/temp/snes/readme.txt'), length: 20);
      await write(cac('Libretro/Content/game/disc.bin'), length: 50);
      await write(dolphin('ShaderCache/GALE01.uidcache'), length: 40);
      final (plan, registry) = await planFor(StorageCleanupLevel.regenerable);
      expect(plan.candidates, hasLength(4));
      final progress = <StorageDeletionProgress>[];
      final result = await manager(registry).execute(
        plan,
        selectedPaths: plan.preselectedPaths,
        onProgress: progress.add,
      );
      expect(result.deletedFiles, 5);
      expect(result.deletedBytes, 10 + 300 + 20 + 50 + 40);
      expect(result.deletedDirectories, 3);
      expect(result.skippedChanged, 0);
      expect(result.skippedMissing, 0);
      expect(result.refusals, isEmpty);
      expect(result.cancelled, isFalse);
      for (final path in [
        tmp('picked.zip'),
        doc('user-data/temp/snes'),
        cac('Libretro/Content/game'),
        dolphin('ShaderCache/GALE01.uidcache'),
      ]) {
        expect(
          await FileSystemEntity.type(path, followLinks: false),
          FileSystemEntityType.notFound,
          reason: path,
        );
      }
      // The root folders themselves stay.
      for (final path in [
        doc('user-data/temp'),
        cac('Libretro/Content'),
        dolphin('ShaderCache'),
        containers.temporary,
      ]) {
        expect(await Directory(path).exists(), isTrue, reason: path);
      }
      expect(progress.last.done, progress.last.total);
      expect(progress.last.total, 5);
      expect(progress.last.deletedBytes, 420);

      expect(
        p.basename(result.journalPath),
        matches(StorageDeletionManager.journalName),
      );
      expect(
        result.journalPath,
        doc('Diagnostics/storage-cleanup-20261012-101010.jsonl'),
      );
      expect(
        result.journalDisplayPath,
        '<Documents>/Diagnostics/storage-cleanup-20261012-101010.jsonl',
      );
      final lines = await journalOf(result);
      expectRelative(lines);
      expect(lines.first['op'], 'begin');
      expect(lines.last['op'], 'end');
      expect(lines.last['deletedFiles'], 5);
      expect(lines.last['deletedBytes'], 420);
      expect(
        {
          for (final line in lines)
            if (line['op'] == 'delete') line['path'],
        },
        {
          '<tmp>/picked.zip',
          '<Documents>/user-data/temp/snes/Game.zip/Game.sfc',
          '<Documents>/user-data/temp/snes/readme.txt',
          '<Documents>/user-data/temp/snes/Game.zip',
          '<Documents>/user-data/temp/snes',
          '<Caches>/Libretro/Content/game/disc.bin',
          '<Caches>/Libretro/Content/game',
          '<Support>/NeoStation/Dolphin/ShaderCache/GALE01.uidcache',
        },
      );
    },
  );

  test('E — a link escaping a root is refused, its target untouched', () async {
    await write(doc('user-data/temp/snes/Game.zip/Game.sfc'), length: 30);
    await write(
      tmp('com.neogamelab.neostation-Inbox/picked.zip'),
      age: const Duration(hours: 1),
    );
    await write(doc('user-data/temp/gba/sub/Game.gba'), length: 12);
    await write(doc('roms/gba/placeholder.gba'));
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    expect(plan.candidateFor(doc('user-data/temp/snes')), isNotNull);

    // The folder candidate becomes a link to a copy outside the container.
    final escaped = p.join(outside.path, 'snes');
    await Directory(doc('user-data/temp/snes')).rename(escaped);
    await Link(doc('user-data/temp/snes')).create(escaped);
    // The parent of a file candidate becomes a link outside.
    final inbox = p.join(outside.path, 'Inbox');
    await Directory(tmp('com.neogamelab.neostation-Inbox')).rename(inbox);
    await Link(tmp('com.neogamelab.neostation-Inbox')).create(inbox);
    // A subfolder becomes a link to the ROM folder, same file inside.
    final sub = doc('user-data/temp/gba/sub');
    final moved = p.join(outside.path, 'gba-sub');
    await Directory(sub).rename(moved);
    final rom = File(p.join(moved, 'Game.gba'));
    await rom.copy(doc('roms/gba/Game.gba'));
    await File(
      doc('roms/gba/Game.gba'),
    ).setLastModified(await rom.lastModified());
    await Link(sub).create(doc('roms/gba'));

    final result = await manager(
      registry,
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(result.deletedFiles, 0);
    final refusals = {
      for (final refusal in result.refusals) refusal.path: refusal.reason,
    };
    expect(refusals[doc('user-data/temp/snes')], StorageRefusalReason.isLink);
    expect(
      refusals[tmp('com.neogamelab.neostation-Inbox/picked.zip')],
      StorageRefusalReason.outsideWhitelist,
    );
    expect(
      refusals[doc('user-data/temp/gba/sub/Game.gba')],
      StorageRefusalReason.isLink,
    );
    expect(await File(p.join(escaped, 'Game.zip/Game.sfc')).length(), 30);
    expect(await File(p.join(inbox, 'picked.zip')).exists(), isTrue);
    expect(await File(doc('roms/gba/Game.gba')).length(), 12);
    expect(await File(p.join(moved, 'Game.gba')).exists(), isTrue);
    expect(await Link(doc('user-data/temp/snes')).exists(), isTrue);
    expectRelative(await journalOf(result));
  });

  test(
    'E — roots, containers, protected folders and outside paths are refused',
    () async {
      final mine = doc('MyGames');
      for (final path in [
        doc('user-data/temp/x.bin'),
        doc('roms/snes/Super Mario World.sfc'),
        doc(p.join(hiddenFolder, 'neostation-source-mangadex.json')),
        cac('NeoSwap-v1/donation.bin'),
        doc('Libretro/System/scph5501.bin'),
        doc('Libretro/System/scph1001.bin'),
        doc('ARMSX2/BIOS/scph39001.bin'),
        data('dev_flash/sys/external/libsysutil.sprx'),
        data('dev_hdd0/home/00000002/savedata/BLES00113-SAVE/PARAM.SFO'),
        data('dev_hdd0/home/00000001/exdata/EP0001.rap'),
        sup('StikJIT/pairing.mobiledevicepairing'),
        p.join(mine, 'snes/Super Mario World.sfc'),
        doc('user-data/config.json'),
        doc('Libretro/Saves/Snes9x/Super Mario World.srm'),
        p.join(outside.path, 'mine.bin'),
      ]) {
        await write(path);
      }
      final registry = StorageRootRegistry(containers, libraryRoots: [mine]);
      final expected = <String, StorageRefusalReason>{
        doc('user-data/temp'): StorageRefusalReason.isRoot,
        containers.documents: StorageRefusalReason.isRoot,
        containers.temporary: StorageRefusalReason.isRoot,
        doc('roms'): StorageRefusalReason.isRoot,
        mine: StorageRefusalReason.isRoot,
        doc('roms/snes/Super Mario World.sfc'):
            StorageRefusalReason.isProtected,
        doc(p.join(hiddenFolder, 'neostation-source-mangadex.json')):
            StorageRefusalReason.isProtected,
        cac('NeoSwap-v1/donation.bin'): StorageRefusalReason.isProtected,
        doc('Libretro/System/scph5501.bin'): StorageRefusalReason.isProtected,
        doc('ARMSX2/BIOS/scph39001.bin'): StorageRefusalReason.isProtected,
        data('dev_flash/sys/external/libsysutil.sprx'):
            StorageRefusalReason.isProtected,
        data('dev_hdd0/home/00000002/savedata/BLES00113-SAVE/PARAM.SFO'):
            StorageRefusalReason.isProtected,
        data('dev_hdd0/home/00000001/exdata/EP0001.rap'):
            StorageRefusalReason.isProtected,
        sup('StikJIT/pairing.mobiledevicepairing'):
            StorageRefusalReason.isProtected,
        p.join(mine, 'snes/Super Mario World.sfc'):
            StorageRefusalReason.isProtected,
        doc('user-data/config.json'): StorageRefusalReason.isProtected,
        doc('Libretro/Saves/Snes9x/Super Mario World.srm'):
            StorageRefusalReason.isProtected,
        p.join(outside.path, 'mine.bin'): StorageRefusalReason.outsideWhitelist,
      };
      final candidates = <StorageCleanupCandidate>[
        for (final path in expected.keys)
          await forged(
            path,
            kind: await FileSystemEntity.isDirectory(path)
                ? StorageEntryKind.directory
                : StorageEntryKind.file,
          ),
      ];
      // Even as a « duplicate », a BIOS stays.
      candidates.add(
        await forged(
          doc('Libretro/System/scph1001.bin'),
          source: StorageCandidateSource.duplicate,
          rootId: 'INV-01',
          pairedPath: doc('roms/snes/Super Mario World.sfc'),
        ),
      );
      expected[doc('Libretro/System/scph1001.bin')] =
          StorageRefusalReason.isProtected;
      final plan = forgedPlan(candidates);
      final before = await tree();
      final result = await manager(registry).execute(
        plan,
        selectedPaths: {for (final value in candidates) value.path},
      );
      expect(result.deletedFiles, 0);
      expect(result.deletedDirectories, 0);
      expect(await tree(), before);
      final reasons = {
        for (final refusal in result.refusals) refusal.path: refusal.reason,
      };
      expect(reasons, expected);
      expectRelative(await journalOf(result));
    },
  );

  test('E — a file changed since the preview is skipped and kept', () async {
    for (final name in ['a.zip', 'b.zip', 'c.zip']) {
      await write(tmp(name), length: 10, age: const Duration(hours: 1));
    }
    await write(doc('user-data/temp/snes/one.bin'), length: 5);
    await write(doc('user-data/temp/snes/two.bin'), length: 5);
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    await File(
      tmp('a.zip'),
    ).writeAsString('longer content', mode: FileMode.append);
    await File(
      tmp('b.zip'),
    ).setLastModified(now.subtract(const Duration(minutes: 30)));
    await File(doc('user-data/temp/snes/two.bin')).writeAsString('changed');
    final result = await manager(
      registry,
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(result.skippedChanged, 3);
    expect(result.deletedFiles, 2);
    expect(await File(tmp('a.zip')).exists(), isTrue);
    expect(await File(tmp('b.zip')).exists(), isTrue);
    expect(await File(tmp('c.zip')).exists(), isFalse);
    expect(await File(doc('user-data/temp/snes/one.bin')).exists(), isFalse);
    expect(await File(doc('user-data/temp/snes/two.bin')).exists(), isTrue);
    // Its folder still holds the changed file.
    expect(
      {for (final refusal in result.refusals) refusal.path: refusal.reason},
      {doc('user-data/temp/snes'): StorageRefusalReason.notEmpty},
    );
    final skips = [
      for (final line in await journalOf(result))
        if (line['op'] == 'skip') line['reason'],
    ];
    expect(skips, everyElement('changedSincePreview'));
    expect(skips, hasLength(3));
  });

  test('E — ENOENT is tolerated', () async {
    for (final name in ['a.zip', 'b.zip', 'c.zip']) {
      await write(tmp(name), age: const Duration(hours: 1));
    }
    await write(doc('user-data/temp/gone/x.bin'));
    await write(doc('user-data/temp/gone/y.bin'));
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    await File(tmp('a.zip')).delete();
    await Directory(doc('user-data/temp/gone')).delete(recursive: true);
    final result = await manager(
      registry,
      deleteFile: (path) async {
        if (p.basename(path) == 'b.zip') {
          // Removed by someone else between the checks and the unlink.
          await File(path).delete();
          throw PathNotFoundException(
            path,
            const OSError('No such file or directory', 2),
            'Cannot delete file',
          );
        }
        await File(path).delete();
      },
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(result.refusals, isEmpty);
    expect(result.skippedMissing, 1 + 1 + 2);
    expect(result.deletedFiles, 1);
    expect(await File(tmp('c.zip')).exists(), isFalse);
  });

  test('E — EACCES and EPERM are refused with the raw text', () async {
    for (final name in ['locked.zip', 'denied.zip', 'free.zip']) {
      await write(tmp(name), age: const Duration(hours: 1));
    }
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    final result = await manager(
      registry,
      deleteFile: (path) async {
        switch (p.basename(path)) {
          case 'locked.zip':
            throw FileSystemException(
              'Cannot delete file',
              path,
              const OSError('Permission denied', 13),
            );
          case 'denied.zip':
            throw FileSystemException(
              'Cannot delete file',
              path,
              const OSError('Operation not permitted', 1),
            );
        }
        await File(path).delete();
      },
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(result.deletedFiles, 1);
    final byPath = {
      for (final refusal in result.refusals) refusal.path: refusal,
    };
    final locked = byPath[tmp('locked.zip')]!;
    expect(locked.reason, StorageRefusalReason.accessDenied);
    expect(locked.errorCode, 13);
    expect(locked.detail, 'OS Error: Permission denied, errno = 13');
    expect(locked.localeKey, StorageLocale.refuseAccess);
    final denied = byPath[tmp('denied.zip')]!;
    expect(denied.reason, StorageRefusalReason.accessDenied);
    expect(denied.errorCode, 1);
    expect(denied.detail, 'OS Error: Operation not permitted, errno = 1');
    expect(await File(tmp('locked.zip')).exists(), isTrue);
    expect(await File(tmp('denied.zip')).exists(), isTrue);
    final lines = await journalOf(result);
    expectRelative(lines);
    final refused = [
      for (final line in lines)
        if (line['op'] == 'refuse') line,
    ];
    expect({for (final line in refused) line['errno']}, {13, 1});
    expect(
      {for (final line in refused) line['detail']},
      {
        'OS Error: Permission denied, errno = 13',
        'OS Error: Operation not permitted, errno = 1',
      },
    );
  });

  test('F — a game or an import running refuses everything', () async {
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    await write(doc('user-data/temp/snes/x.bin'));
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    final before = await tree();
    final result = await manager(
      registry,
      sessions: guard(launch: () => true),
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(result.deletedFiles, 0);
    expect(result.stoppedBySession, isTrue);
    expect(reasonsOf(result), {StorageRefusalReason.sessionActive});
    expect(result.refusals, hasLength(2));
    expect(await tree(), before);

    // An import following a Files pick (review of phase 5d), read by the
    // default guard from StorageImportActivity.
    addTearDown(StorageImportActivity.reset);
    final picking = Completer<void>();
    final import = StorageImportActivity.run(() => picking.future);
    final imported = await manager(
      registry,
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(imported.deletedFiles, 0);
    expect(imported.stoppedBySession, isTrue);
    expect(reasonsOf(imported), {StorageRefusalReason.sessionActive});
    expect(imported.refusals, hasLength(2));
    expect(await tree(), before);
    final lines = await journalOf(imported);
    expect(lines.first['importActive'], isTrue);
    expect(lines.first['launchActive'], isFalse);
    picking.complete();
    await import;
  });

  test('F — an import starting during the cleanup stops it at the next '
      'check, like a game', () async {
    for (var index = 0; index < 120; index++) {
      await write(doc('user-data/temp/big/file-$index.bin'), length: 1);
    }
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    addTearDown(StorageImportActivity.reset);
    final picking = Completer<void>();
    Future<void>? import;
    var deleted = 0;
    final result = await manager(
      registry,
      // The default guard reads StorageImportActivity; the user starts an
      // import (another page) after the tenth file.
      deleteFile: (path) async {
        await File(path).delete();
        if (++deleted == 10) {
          import = StorageImportActivity.run(() => picking.future);
        }
      },
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    expect(StorageImportActivity.active, isTrue);
    expect(result.deletedFiles, 50);
    expect(result.stoppedBySession, isTrue);
    expect(
      {for (final refusal in result.refusals) refusal.path: refusal.reason},
      {doc('user-data/temp/big'): StorageRefusalReason.sessionActive},
    );
    expect(Directory(doc('user-data/temp/big')).listSync(), hasLength(70));
    expect((await journalOf(result)).first['importActive'], isFalse);
    picking.complete();
    await import;
    expect(StorageImportActivity.active, isFalse);
  });

  test(
    'F — the guard is checked before the start and every 50 files',
    () async {
      for (var index = 0; index < 120; index++) {
        await write(doc('user-data/temp/big/file-$index.bin'), length: 1);
      }
      final (plan, registry) = await planFor(StorageCleanupLevel.safe);
      expect(candidateOf(plan, doc('user-data/temp/big')).fileCount, 120);

      var checks = 0;
      var result = await manager(
        registry,
        sessions: guard(
          launch: () {
            checks++;
            return false;
          },
        ),
      ).execute(plan, selectedPaths: plan.preselectedPaths);
      expect(checks, 3, reason: 'before the start, after 50 and 100 files');
      expect(result.deletedFiles, 120);
      expect(await Directory(doc('user-data/temp/big')).exists(), isFalse);

      for (var index = 0; index < 120; index++) {
        await write(doc('user-data/temp/big/file-$index.bin'), length: 1);
      }
      final (again, _) = await planFor(StorageCleanupLevel.safe);
      checks = 0;
      result = await manager(
        registry,
        sessions: guard(launch: () => ++checks > 1),
      ).execute(again, selectedPaths: again.preselectedPaths);
      expect(result.deletedFiles, 50);
      expect(result.stoppedBySession, isTrue);
      expect(
        {for (final refusal in result.refusals) refusal.path: refusal.reason},
        {doc('user-data/temp/big'): StorageRefusalReason.sessionActive},
      );
      expect(Directory(doc('user-data/temp/big')).listSync(), hasLength(70));
    },
  );

  test(
    'F — a libretro session or the Dolphin marker stops their roots only',
    () async {
      for (var index = 0; index < 60; index++) {
        await write(cac('Libretro/Content/game/part-$index.bin'), length: 1);
      }
      await write(tmp('picked.zip'), age: const Duration(hours: 1));
      final (plan, registry) = await planFor(StorageCleanupLevel.safe);
      expect(paths(plan), {cac('Libretro/Content/game'), tmp('picked.zip')});

      // A libretro session starts while the cleanup runs: seen at the
      // check after 50 files, its root stops there, the rest goes on.
      var checks = 0;
      final result = await manager(
        registry,
        sessions: guard(libretro: () async => ++checks > 1),
      ).execute(plan, selectedPaths: plan.preselectedPaths);
      expect(checks, 2);
      expect(result.deletedFiles, 50 + 1);
      expect(
        {for (final refusal in result.refusals) refusal.path: refusal.reason},
        {cac('Libretro/Content/game'): StorageRefusalReason.sessionActive},
      );
      expect(Directory(cac('Libretro/Content/game')).listSync(), hasLength(10));
      expect(await File(tmp('picked.zip')).exists(), isFalse);
      expect(result.stoppedBySession, isFalse);

      // The Dolphin marker appears after the preview.
      await write(dolphin('ShaderCache/GALE01.uidcache'));
      await write(tmp('picked.zip'), age: const Duration(hours: 1));
      await write(tmp('NeoStation-Dolphin-FramePacing.json'));
      final (again, _) = await planFor(StorageCleanupLevel.regenerable);
      expect(
        paths(again),
        containsAll([
          dolphin('ShaderCache/GALE01.uidcache'),
          tmp('NeoStation-Dolphin-FramePacing.json'),
        ]),
      );
      await write(dolphin('CrashMarkers/active-session.json'));
      final marked = await manager(
        registry,
        sessions: StorageSessionGuard(
          launchActive: () => false,
          libretroActive: () async => false,
          libretroJournalUnfinished: () async => false,
          containers: containers,
        ),
      ).execute(again, selectedPaths: again.preselectedPaths);
      expect(
        {for (final refusal in marked.refusals) refusal.path: refusal.reason},
        {
          dolphin('ShaderCache/GALE01.uidcache'):
              StorageRefusalReason.sessionActive,
          tmp('NeoStation-Dolphin-FramePacing.json'):
              StorageRefusalReason.sessionActive,
        },
      );
      expect(
        await File(dolphin('ShaderCache/GALE01.uidcache')).exists(),
        isTrue,
      );
      expect(
        await File(tmp('NeoStation-Dolphin-FramePacing.json')).exists(),
        isTrue,
      );
      expect(await File(tmp('picked.zip')).exists(), isFalse);
      expect(await Directory(cac('Libretro/Content/game')).exists(), isFalse);
    },
  );

  Future<void> writeRpcs3() async {
    await write(sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'));
    await write(data('dev_hdd0/tmp/update.tmp'));
    await write(
      doc('RPCS3/Export/Game Saves/.saves.zip.part'),
      age: const Duration(hours: 2),
    );
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
  }

  final rpcs3Paths = <String Function()>[
    () => sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'),
    () => data('dev_hdd0/tmp/update.tmp'),
    () => doc('RPCS3/Export/Game Saves/.saves.zip.part'),
  ];

  test(
    'F — runSaveExchange refusing (gameRunning) refuses the RPCS3 candidates',
    () async {
      await writeRpcs3();
      final (plan, registry) = await planFor(StorageCleanupLevel.regenerable);
      Rpcs3InternalService.saveExchangeCoreInitializedOverride = true;
      Rpcs3InternalService.saveExchangeEmulationState = () async => 2;
      final result = await manager(
        registry,
      ).execute(plan, selectedPaths: plan.preselectedPaths);
      expect(result.deletedFiles, 1);
      expect(await File(tmp('picked.zip')).exists(), isFalse);
      for (final path in rpcs3Paths) {
        expect(await File(path()).exists(), isTrue, reason: path());
      }
      expect(reasonsOf(result), {StorageRefusalReason.rpcs3Busy});
      expect(result.refusals, hasLength(3));
      expect(
        {for (final refusal in result.refusals) refusal.detail},
        {'gameRunning'},
      );
      expect(result.refusals.first.localeKey, StorageLocale.rpcs3Busy);
    },
  );

  test(
    'F — runSaveExchange refusing (libraryBusy) refuses the RPCS3 candidates',
    () async {
      await writeRpcs3();
      final (plan, registry) = await planFor(StorageCleanupLevel.regenerable);
      // Another RPCS3 library operation holds the guard.
      final result = await Rpcs3InternalService.runSaveExchange(
        () => manager(
          registry,
        ).execute(plan, selectedPaths: plan.preselectedPaths),
      );
      expect(result.deletedFiles, 1);
      for (final path in rpcs3Paths) {
        expect(await File(path()).exists(), isTrue, reason: path());
      }
      expect(reasonsOf(result), {StorageRefusalReason.rpcs3Busy});
      expect(
        {for (final refusal in result.refusals) refusal.detail},
        {'libraryBusy'},
      );
    },
  );

  test(
    'RPCS3 candidates run inside the guard; a redirection refuses them',
    () async {
      await writeRpcs3();
      final (plan, registry) = await planFor(StorageCleanupLevel.regenerable);
      var inside = false;
      final deleted = <String, bool>{};
      final result = await manager(
        registry,
        rpcs3Guard: (body) async {
          inside = true;
          try {
            await Rpcs3InternalService.runSaveExchange(body);
          } finally {
            inside = false;
          }
        },
        deleteFile: (path) async {
          // The manager hands over the resolved path (/private/var on iOS).
          deleted[storageCanonicalPath(path)] = inside;
          await File(path).delete();
        },
      ).execute(plan, selectedPaths: plan.preselectedPaths);
      expect(result.refusals, isEmpty);
      expect(result.deletedFiles, 4);
      for (final path in rpcs3Paths) {
        expect(deleted[storageCanonicalPath(path())], isTrue, reason: path());
      }
      expect(deleted[storageCanonicalPath(tmp('picked.zip'))], isFalse);

      await writeRpcs3();
      final (again, _) = await planFor(StorageCleanupLevel.regenerable);
      final redirected = await manager(
        registry,
        rpcs3Redirected: () async => true,
      ).execute(again, selectedPaths: again.preselectedPaths);
      expect(
        {
          for (final refusal in redirected.refusals)
            refusal.path: refusal.reason,
        },
        {
          sup('NeoStation/RPCS3/Cache/ppu-BLES00113'):
              StorageRefusalReason.redirected,
          data('dev_hdd0/tmp/update.tmp'): StorageRefusalReason.redirected,
        },
      );
      // The Files workspace (INV-10) is not redirected by vfs.yml.
      expect(
        await File(doc('RPCS3/Export/Game Saves/.saves.zip.part')).exists(),
        isFalse,
      );
      expect(
        await File(
          sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'),
        ).exists(),
        isTrue,
      );
    },
  );

  test('a cancellation stops after the current file', () async {
    for (var index = 0; index < 10; index++) {
      await write(tmp('copy-$index.zip'), age: const Duration(hours: 1));
    }
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    final cancel = StorageScanCancelToken();
    final result = await manager(registry).execute(
      plan,
      selectedPaths: plan.preselectedPaths,
      cancel: cancel,
      onProgress: (progress) {
        if (progress.deletedFiles == 3) cancel.cancel();
      },
    );
    expect(result.cancelled, isTrue);
    expect(result.deletedFiles, 3);
    expect(result.refusals, isEmpty);
    expect(
      Directory(containers.temporary).listSync().whereType<File>(),
      hasLength(7),
    );
    final lines = await journalOf(result);
    expect(lines.last['op'], 'end');
    expect(lines.last['cancelled'], isTrue);

    final early = StorageScanCancelToken()..cancel();
    final none = await manager(
      registry,
    ).execute(plan, selectedPaths: plan.preselectedPaths, cancel: early);
    expect(none.cancelled, isTrue);
    expect(none.deletedFiles, 0);
  });

  test('the journal keeps 20 files at most, its own only', () async {
    final diagnostics = doc('Diagnostics');
    for (var index = 0; index < 25; index++) {
      final second = index.toString().padLeft(2, '0');
      await File(
        p.join(diagnostics, 'storage-cleanup-20260101-0000$second.jsonl'),
      ).writeAsString('{}\n');
    }
    await File(
      p.join(diagnostics, 'storage-cleanup-notes.txt'),
    ).writeAsString('');
    await File(p.join(diagnostics, 'other.jsonl')).writeAsString('');
    final target = File(p.join(outside.path, 'target.jsonl'))
      ..writeAsStringSync('keep');
    await Link(
      p.join(diagnostics, 'storage-cleanup-20250101-000000.jsonl'),
    ).create(target.path);
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);

    final result = await manager(
      registry,
    ).execute(plan, selectedPaths: plan.preselectedPaths);
    final journals = [
      for (final entity in Directory(diagnostics).listSync(followLinks: false))
        if (entity is File &&
            StorageDeletionManager.journalName.hasMatch(
              p.basename(entity.path),
            ))
          p.basename(entity.path),
    ]..sort();
    expect(journals, hasLength(20));
    expect(journals.last, 'storage-cleanup-20261012-101010.jsonl');
    expect(journals.first, 'storage-cleanup-20260101-000006.jsonl');
    expect(
      await File(p.join(diagnostics, 'storage-cleanup-notes.txt')).exists(),
      isTrue,
    );
    expect(await File(p.join(diagnostics, 'other.jsonl')).exists(), isTrue);
    expect(
      await Link(
        p.join(diagnostics, 'storage-cleanup-20250101-000000.jsonl'),
      ).exists(),
      isTrue,
    );
    expect(await target.readAsString(), 'keep');
    final lines = await journalOf(result);
    expect(lines.last['prunedJournals'], 6);
    expectRelative(lines);

    // A second run in the same second gets its own file.
    final again = await manager(registry).execute(plan, selectedPaths: {});
    expect(
      p.basename(again.journalPath),
      'storage-cleanup-20261012-101010-2.jsonl',
    );
  });

  test(
    'duplicates: the unused copy is deletable, the referenced one never',
    () async {
      final mine = doc('MyGames');
      await db.execute(
        'INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES (?, ?, ?)',
        [
          'snes',
          'Super Mario World.sfc',
          doc('roms/snes/Super Mario World.sfc'),
        ],
      );
      await write(doc('roms/snes/Super Mario World.sfc'), length: 100);
      await write(p.join(mine, 'snes/Super Mario World.sfc'), length: 100);
      final (plan, registry) = await planFor(
        StorageCleanupLevel.confirmed,
        libraryRoots: [mine],
      );
      final copy = candidateOf(
        plan,
        p.join(mine, 'snes/Super Mario World.sfc'),
      );
      expect(copy.isDuplicate, isTrue);
      expect(registry.isProtected(copy.path), isTrue);

      // The referenced copy is no candidate.
      var result = await manager(
        registry,
      ).execute(plan, selectedPaths: {doc('roms/snes/Super Mario World.sfc')});
      expect(reasonsOf(result), {StorageRefusalReason.notInPlan});

      // The referenced copy disappeared after the preview: the last copy stays.
      final referenced = File(doc('roms/snes/Super Mario World.sfc'));
      await referenced.rename(p.join(outside.path, 'kept.sfc'));
      result = await manager(
        registry,
      ).execute(plan, selectedPaths: {copy.path});
      expect(result.deletedFiles, 0);
      expect(reasonsOf(result), {StorageRefusalReason.changedSincePreview});
      expect(result.refusals.single.detail, 'referencedCopyMissing');
      expect(await File(copy.path).exists(), isTrue);
      await File(p.join(outside.path, 'kept.sfc')).rename(referenced.path);

      result = await manager(
        registry,
      ).execute(plan, selectedPaths: {copy.path});
      expect(result.deletedFiles, 1);
      expect(result.refusals, isEmpty);
      expect(await File(copy.path).exists(), isFalse);
      expect(await referenced.length(), 100);

      // A forged « duplicate » of the referenced copy, paired with nothing,
      // never goes.
      final forgedCopy = await forged(
        referenced.path,
        source: StorageCandidateSource.duplicate,
        rootId: 'INV-01',
        pairedPath: copy.path,
      );
      result = await manager(
        registry,
      ).execute(forgedPlan([forgedCopy]), selectedPaths: {referenced.path});
      expect(reasonsOf(result), {StorageRefusalReason.changedSincePreview});
      expect(await referenced.exists(), isTrue);
      // As a plain rule candidate, a ROM is protected.
      result = await manager(registry).execute(
        forgedPlan([await forged(referenced.path, rootId: 'INV-01')]),
        selectedPaths: {referenced.path},
      );
      expect(reasonsOf(result), {StorageRefusalReason.isProtected});
      expect(await referenced.exists(), isTrue);
    },
  );

  test('metadata rows go after the files, only when selected', () async {
    await db.execute(
      'INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES (?, ?, ?)',
      ['snes', 'Kept.sfc', doc('roms/snes/Kept.sfc')],
    );
    for (final name in ['Kept.sfc', 'Gone.sfc']) {
      await db.execute(
        'INSERT INTO user_screenscraper_metadata (app_system_id, filename) VALUES (?, ?)',
        ['snes', name],
      );
    }
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    final (plan, registry) = await planFor(StorageCleanupLevel.regenerable);
    expect(plan.metadataKeys, const [
      StorageOrphanMetadataKey('snes', 'Gone.sfc'),
    ]);
    final maintenance = StorageMaintenanceRepository(
      database: () async => db,
      backupDirectory: () async => sup('NeoStation/Maintenance'),
      now: () => clock,
    );
    Future<List<String>> rows() async => [
      for (final row in await db.rawQuery(
        'SELECT filename FROM user_screenscraper_metadata ORDER BY filename',
      ))
        row['filename'].toString(),
    ];

    var result = await manager(registry).execute(
      plan,
      selectedPaths: {tmp('picked.zip')},
      maintenance: maintenance,
    );
    expect(result.metadata, isNull);
    expect(await rows(), ['Gone.sfc', 'Kept.sfc']);

    result = await manager(registry).execute(
      plan,
      selectedPaths: {StorageCleanupPlan.metadataSelectionKey},
      maintenance: maintenance,
    );
    expect(result.metadata!.deleted, 1);
    expect(result.metadata!.skippedNotOrphan, 0);
    expect(await rows(), ['Kept.sfc']);
    expect(await File(result.metadata!.backupPath).exists(), isTrue);
    final lines = await journalOf(result);
    expectRelative(lines);
    final metadata = lines.singleWhere((line) => line['op'] == 'metadata');
    expect(metadata['deleted'], 1);
    expect(metadata['sqlite'], isA<String>());
    expect(
      metadata['backup'],
      '<Support>/NeoStation/Maintenance/data-20261012-101010.sqlite',
    );
    expect(
      (await db.rawQuery('SELECT COUNT(*) AS n FROM user_roms')).single['n'],
      1,
    );
  });

  test('the Library caches go through their API, never file by file', () async {
    await write(cac('Library/library_http/a.bin'), length: 10);
    await write(cac('Library/library_http/b.bin'), length: 20);
    await write(cac('Library/library_images/c.png'), length: 30);
    final (plan, registry) = await planFor(StorageCleanupLevel.regenerable);
    final selection = {
      cac('Library/library_http'),
      cac('Library/library_images'),
    };
    expect(selection.every((path) => plan.candidateFor(path) != null), isTrue);

    final calls = <StorageCacheApi>[];
    var result = await manager(registry).execute(
      plan,
      selectedPaths: selection,
      clearLibraryCaches: (cache) async => calls.add(cache),
    );
    expect(calls, unorderedEquals(StorageCacheApi.values));
    expect(result.deletedBytes, 0);
    expect(await File(cac('Library/library_http/a.bin')).exists(), isTrue);
    expect(await File(cac('Library/library_images/c.png')).exists(), isTrue);

    result = await manager(registry).execute(
      plan,
      selectedPaths: selection,
      clearLibraryCaches: (cache) async {
        if (cache == StorageCacheApi.libraryImages) {
          throw StateError('image cache busy');
        }
        await File(cac('Library/library_http/a.bin')).delete();
        await File(cac('Library/library_http/b.bin')).delete();
      },
    );
    expect(result.deletedBytes, 30);
    expect(result.deletedFiles, 2);
    expect(result.clearedCaches, [StorageCacheApi.libraryHttp]);
    final refusal = result.refusals.single;
    expect(refusal.reason, StorageRefusalReason.cacheApiFailed);
    expect(refusal.detail, contains('image cache busy'));
    expect(await File(cac('Library/library_images/c.png')).exists(), isTrue);
  });

  test(
    'a protected name inside a temporary folder keeps it: notEmpty',
    () async {
      await write(doc('user-data/temp/arch/config.json'));
      await write(doc('user-data/temp/arch/game.sfc'), length: 5);
      final (plan, registry) = await planFor(StorageCleanupLevel.safe);
      final result = await manager(
        registry,
      ).execute(plan, selectedPaths: plan.preselectedPaths);
      expect(result.deletedFiles, 1);
      expect(
        await File(doc('user-data/temp/arch/config.json')).exists(),
        isTrue,
      );
      expect(await File(doc('user-data/temp/arch/game.sfc')).exists(), isFalse);
      final refusal = result.refusals.single;
      expect(refusal.path, doc('user-data/temp/arch'));
      expect(refusal.reason, StorageRefusalReason.notEmpty);
      expect(refusal.localeKey, StorageLocale.refuseNotEmpty);
    },
  );
}
