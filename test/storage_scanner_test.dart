import 'dart:async';
import 'dart:ffi';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:neostation/services/storage/storage_scanner.dart';
import 'package:neostation/services/storage/storage_stat_ffi.dart';
import 'package:path/path.dart' as p;

/// § 3.2 of docs/storage-audit-cleanup.md and test E (scanner part): one
/// isolate per root, links never followed and counted 0 bytes, loops and
/// depth bounded, `.icloud` placeholders at 0, unreadable entries counted,
/// nested roots measured once, hidden library folder folded, progress and
/// cancellation, nothing written.

/// Lists like the scanner but refuses any directory named `locked`, as iOS
/// does for a folder without read permission (root ignores chmod 000).
Stream<FileSystemEntity> _lockedLister(Directory directory) {
  if (p.basename(directory.path) == 'locked') {
    return Stream<FileSystemEntity>.error(
      FileSystemException(
        'Directory listing failed',
        directory.path,
        const OSError('Permission denied', 13),
      ),
    );
  }
  return directory.list(recursive: false, followLinks: false);
}

final bool _isRoot = () {
  if (!Platform.isLinux && !Platform.isMacOS) return false;
  final result = Process.runSync('id', ['-u']);
  return (result.stdout as String).trim() == '0';
}();

void main() {
  late Directory home;
  late StorageContainers containers;

  String doc(String relative) => p.join(containers.documents, relative);
  String sup(String relative) =>
      p.join(containers.applicationSupport, relative);
  String cac(String relative) => p.join(containers.caches, relative);
  String tmp(String relative) => p.join(containers.temporary, relative);

  Future<File> write(String path, int length) async {
    final file = File(path);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(List<int>.filled(length, 7));
    return file;
  }

  setUp(() async {
    StorageStatFfi.resetSession();
    home = await Directory.systemTemp.createTemp('storage_scanner_');
    containers = StorageContainers(
      documents: p.join(home.path, 'Documents'),
      applicationSupport: p.join(home.path, 'Library', 'Application Support'),
      caches: p.join(home.path, 'Library', 'Caches'),
      temporary: p.join(home.path, 'tmp'),
    );
    for (final container in StorageContainer.values) {
      await Directory(containers.pathOf(container)).create(recursive: true);
    }
  });

  tearDown(() async {
    StorageStatFfi.resetSession();
    if (await home.exists()) {
      await Process.run('chmod', ['-R', 'u+rwx', home.path]);
      await home.delete(recursive: true);
    }
  });

  Future<Map<String, (int, DateTime)>> snapshot() async {
    final result = <String, (int, DateTime)>{};
    await for (final entity in home.list(recursive: true, followLinks: false)) {
      final stat = await entity.stat();
      result[entity.path] = (stat.size, stat.modified);
    }
    return result;
  }

  StorageNode node(StorageScanResult result, String path) =>
      result.allNodes.firstWhere((candidate) => candidate.path == path);

  test(
    'measures every root once, nested roots excluded from their parents',
    () async {
      await write(doc('roms/snes/Super Mario World.sfc'), 1000);
      await write(doc('user-data/config.json'), 10);
      await write(doc('user-data/temp/snes/Game.zip/Game.sfc'), 300);
      await write(doc('user-data/themes/epic/theme.xml'), 20);
      await write(doc('user-data/background.png'), 40);
      await write(doc('Libretro/Saves/Snes9x/Super Mario World.srm'), 8192);
      await write(doc('NeoPlay.jsonl'), 5);
      await write(doc('stray.bin'), 3);
      await write(sup('NeoStation/RPCS3/Data/dev_hdd0/game/BLES00113/x'), 500);
      await write(sup('NeoStation/RPCS3/Data/dev_hdd1/cache.bin'), 700);
      await write(sup('NeoStation/RPCS3/Cache/ppu.obj'), 900);
      await write(sup('NeoStation/Dolphin/Library/gc/Game.rvz'), 1200);
      await write(sup('NeoStation/Dolphin/User/Config/Dolphin.ini'), 30);
      await write(sup('NeoStation/Unknown/x'), 6);
      await write(cac('Libretro/SkinCache/x.png'), 50);
      await write(cac('KartPad/x'), 60);
      await write(tmp('picked.zip'), 70);
      await write(tmp('com.neogamelab.neostation-Inbox/picked.zip'), 70);

      final registry = StorageRootRegistry(containers);
      final result = await StorageScanner().scan(registry);
      expect(result.cancelled, isFalse);
      expect(
        result.logicalBytes,
        1000 +
            10 +
            300 +
            20 +
            40 +
            8192 +
            5 +
            3 +
            500 +
            700 +
            900 +
            1200 +
            30 +
            6 +
            50 +
            60 +
            70 +
            70,
      );
      expect(
        result.roots.fold<int>(0, (sum, root) => sum + root.logicalBytes),
        result.logicalBytes,
      );
      final byRoot = <String, int>{};
      for (final root in result.roots) {
        byRoot[root.rootId] = (byRoot[root.rootId] ?? 0) + root.logicalBytes;
      }
      expect(byRoot['INV-01'], 1000);
      expect(
        byRoot['INV-02'],
        10 + 40,
      ); // config.json + background (INV-04 rule)
      expect(byRoot['INV-03'], 300);
      expect(byRoot['INV-04'], 20);
      expect(byRoot['INV-07'], 5 + 3);
      expect(byRoot['INV-12'], 60);
      expect(byRoot['INV-14'], 8192);
      expect(byRoot['INV-16'], 500);
      expect(byRoot['INV-17'], 700);
      expect(byRoot['INV-18'], 900);
      expect(byRoot['INV-20'], 1200);
      expect(byRoot['INV-21'], 30);
      expect(byRoot['INV-25'], 50);
      expect(byRoot['INV-28'], 140);
      expect(byRoot['INV-29'], 6);
      // Absent roots count 0 bytes.
      expect(byRoot['INV-27'], 0);
      expect(
        result.nodesOfRoot('INV-27').every((root) => root.children.isEmpty),
        isTrue,
      );
      expect(
        result.roots.map((root) => root.path),
        registry.locations.map((location) => location.path),
      );

      // Classification of the nodes.
      final rom = node(result, doc('roms/snes/Super Mario World.sfc'));
      expect(rom.deletionClass, StorageDeletionClass.never);
      expect(rom.category, StorageCategory.games);
      expect(rom.relativePath, 'roms/snes/Super Mario World.sfc');
      expect(rom.displayPath, '<Documents>/roms/snes/Super Mario World.sfc');
      expect(rom.modified, isNotNull);
      final picked = node(result, tmp('picked.zip'));
      expect(picked.deletionClass, StorageDeletionClass.temporaryWhenIdle);
      expect(picked.ruleId, 'INV-28.temporary');
      expect(node(result, doc('stray.bin')).category, StorageCategory.unknown);
      expect(
        node(result, sup('NeoStation/Unknown/x')).deletionClass,
        StorageDeletionClass.never,
      );

      // Totals per category add up.
      final totals = result.byCategory;
      expect(
        totals.values.fold<int>(0, (sum, value) => sum + value.logicalBytes),
        result.logicalBytes,
      );
      expect(totals[StorageCategory.games]!.logicalBytes, 1000 + 500 + 1200);
      expect(totals[StorageCategory.games]!.fileCount, 3);
      expect(
        totals[StorageCategory.temporary]!.logicalBytes,
        300 + 60 + 70 + 70,
      );
      expect(totals[StorageCategory.unknown]!.logicalBytes, 3 + 6);
      expect(
        result.byRoot['INV-14']![StorageCategory.saves]!.logicalBytes,
        8192,
      );
    },
  );

  test('with lstat: allocated bytes, free space and the FFI flag', () async {
    await write(doc('roms/a.sfc'), 1);
    await write(doc('roms/b.sfc'), 5000);
    final result = await StorageScanner().scan(StorageRootRegistry(containers));
    if (Abi.current() != Abi.linuxX64 &&
        StorageStatLayout.forAbi(Abi.current()) == null) {
      expect(result.statViaFfi, isFalse);
      return;
    }
    expect(result.statViaFfi, isTrue);
    expect(result.statLayout, isNotNull);
    expect(result.allocatedBytes, isNotNull);
    expect(result.freeBytes, isNotNull);
    expect(result.volumeBytes, greaterThanOrEqualTo(result.freeBytes!));
    final small = node(result, doc('roms/a.sfc'));
    expect(small.allocatedBytes, greaterThanOrEqualTo(small.logicalBytes));
    final roms = result.nodesOfRoot('INV-01').first;
    expect(
      roms.allocatedBytes,
      (small.allocatedBytes ?? 0) +
          (node(result, doc('roms/b.sfc')).allocatedBytes ?? 0),
    );
    expect(
      result.byCategory[StorageCategory.games]!.allocatedBytes,
      roms.allocatedBytes,
    );
  }, skip: Abi.current() == Abi.linuxX64 ? false : 'glibc x86_64 lane');

  test(
    'logical fallback: no allocation, no free space, statViaFfi false',
    () async {
      await write(doc('roms/a.sfc'), 1234);
      final result = await StorageScanner(
        stat: const StorageStatLogical(),
      ).scan(StorageRootRegistry(containers));
      expect(result.statViaFfi, isFalse);
      expect(result.allocatedBytes, isNull);
      expect(result.freeBytes, isNull);
      expect(result.volumeBytes, isNull);
      expect(result.logicalBytes, 1234);
      expect(node(result, doc('roms/a.sfc')).allocatedBytes, isNull);
      expect(result.byCategory[StorageCategory.games]!.allocatedBytes, isNull);
    },
  );

  test(
    'links are counted 0 bytes and never followed, loops are harmless',
    () async {
      final outside = await Directory.systemTemp.createTemp(
        'storage_scanner_outside_',
      );
      addTearDown(() => outside.delete(recursive: true));
      final big = await write(p.join(outside.path, 'big.bin'), 1 << 20);
      await write(doc('roms/snes/real.sfc'), 10);
      await Link(doc('roms/snes/big-link.sfc')).create(big.path);
      await Link(doc('roms/outside-dir')).create(outside.path);
      // A loop: roms/snes/loop -> roms.
      await Link(doc('roms/snes/loop')).create(doc('roms'));
      // KartPad's Application Support links (INV-12).
      await Directory(doc('Ports/KartPad/Saves/NAND')).create(recursive: true);
      await write(doc('Ports/KartPad/Saves/NAND/title.bin'), 33);
      await Directory(sup('KartPad')).create(recursive: true);
      await Link(sup('KartPad/NAND')).create(doc('Ports/KartPad/Saves/NAND'));

      final result = await StorageScanner().scan(
        StorageRootRegistry(containers),
      );
      expect(result.logicalBytes, 10 + 33);
      final roms = result.nodesOfRoot('INV-01').first;
      expect(roms.linkCount, 3);
      expect(roms.logicalBytes, 10);
      for (final path in [
        doc('roms/snes/big-link.sfc'),
        doc('roms/outside-dir'),
        doc('roms/snes/loop'),
      ]) {
        final link = node(result, path);
        expect(link.kind, StorageEntryKind.link, reason: path);
        expect(link.logicalBytes, 0);
        expect(link.children, isEmpty);
        expect(link.deletionClass, StorageDeletionClass.never);
      }
      final support = result.roots.firstWhere(
        (root) => root.path == sup('KartPad'),
      );
      expect(support.rootId, 'INV-12');
      expect(support.linkCount, 1);
      expect(support.logicalBytes, 0);
      // A root that is itself a link is not followed either.
      await Link(doc('Libretro')).create(outside.path);
      final again = await StorageScanner().scan(
        StorageRootRegistry(containers),
      );
      final libretro = again.nodesOfRoot('INV-14').single;
      expect(libretro.kind, StorageEntryKind.link);
      expect(libretro.logicalBytes, 0);
      expect(again.logicalBytes, 10 + 33);
    },
  );

  test(
    'depth and entry limits bound the walk and mark the subtree truncated',
    () async {
      var deep = doc('roms/deep');
      for (var level = 0; level < 30; level++) {
        deep = p.join(deep, 'level$level');
      }
      await write(p.join(deep, 'bottom.bin'), 99);
      await write(doc('roms/top.bin'), 1);
      final limited = await StorageScanner(
        maxDepth: 3,
      ).scan(StorageRootRegistry(containers));
      final roms = limited.nodesOfRoot('INV-01').first;
      expect(roms.truncated, isTrue);
      expect(roms.logicalBytes, 1);
      expect(limited.truncated, isTrue);
      final full = await StorageScanner().scan(StorageRootRegistry(containers));
      // Default maxDepth 24 also stops before level 30.
      expect(full.nodesOfRoot('INV-01').first.truncated, isTrue);
      expect(full.nodesOfRoot('INV-01').first.logicalBytes, 1);
      final unlimited = await StorageScanner(
        maxDepth: 64,
      ).scan(StorageRootRegistry(containers));
      expect(unlimited.nodesOfRoot('INV-01').first.truncated, isFalse);
      expect(unlimited.nodesOfRoot('INV-01').first.logicalBytes, 100);

      for (var index = 0; index < 40; index++) {
        await write(tmp('copy-$index.bin'), 10);
      }
      final bounded = await StorageScanner(
        maxEntriesPerRoot: 15,
      ).scan(StorageRootRegistry(containers));
      final temporary = bounded.roots.firstWhere(
        (root) => root.path == containers.temporary,
      );
      expect(temporary.rootId, 'INV-28');
      expect(temporary.truncated, isTrue);
      expect(temporary.children.length, lessThanOrEqualTo(15));
      expect(temporary.logicalBytes, lessThanOrEqualTo(150));
    },
  );

  test('iCloud placeholders count 0 bytes and are never deletable', () async {
    await write(doc('roms/snes/.Chrono Trigger.sfc.icloud'), 4096);
    await write(doc('roms/snes/Chrono Trigger (local).sfc'), 50);
    final result = await StorageScanner().scan(StorageRootRegistry(containers));
    final placeholder = node(
      result,
      doc('roms/snes/.Chrono Trigger.sfc.icloud'),
    );
    expect(placeholder.kind, StorageEntryKind.icloudPlaceholder);
    expect(placeholder.logicalBytes, 0);
    expect(placeholder.allocatedBytes ?? 0, 0);
    expect(placeholder.icloudCount, 1);
    expect(placeholder.deletionClass, StorageDeletionClass.never);
    final roms = result.nodesOfRoot('INV-01').first;
    expect(roms.icloudCount, 1);
    expect(roms.fileCount, 1);
    expect(roms.logicalBytes, 50);
  });

  test(
    'unreadable directories are counted with their relative path (lister)',
    () async {
      await write(doc('Libretro/Saves/locked/game.srm'), 100);
      await write(doc('Libretro/Saves/open/game.srm'), 10);
      final result = await StorageScanner(
        lister: _lockedLister,
      ).scan(StorageRootRegistry(containers));
      expect(result.inaccessible, ['<Documents>/Libretro/Saves/locked']);
      final locked = node(result, doc('Libretro/Saves/locked'));
      expect(locked.kind, StorageEntryKind.inaccessible);
      expect(locked.deletionClass, StorageDeletionClass.never);
      expect(locked.inaccessibleCount, 1);
      final libretro = result.nodesOfRoot('INV-14').single;
      expect(libretro.inaccessibleCount, 1);
      expect(libretro.logicalBytes, 10);
    },
  );

  test(
    'unreadable directories are counted with their relative path (chmod 000)',
    () async {
      final locked = Directory(doc('Diagnostics/private'));
      await write(p.join(locked.path, 'trace.txt'), 100);
      await write(doc('Diagnostics/open.txt'), 10);
      await Process.run('chmod', ['000', locked.path]);
      final result = await StorageScanner().scan(
        StorageRootRegistry(containers),
      );
      expect(result.inaccessible, contains('<Documents>/Diagnostics/private'));
      expect(node(result, locked.path).kind, StorageEntryKind.inaccessible);
      expect(result.nodesOfRoot('INV-06').single.logicalBytes, 10);
    },
    skip: _isRoot || Platform.isWindows
        ? 'running as root: chmod 000 does not stop root from reading (covered by the lister test)'
        : false,
  );

  test('the hidden library folder is measured but never detailed', () async {
    await write(doc('Library/Books/Dune.epub'), 400);
    await write(doc('Library/Sources/neostation-source-a.json'), 1000);
    await write(doc('Library/Sources/nested/b.json'), 24);
    final result = await StorageScanner().scan(StorageRootRegistry(containers));
    final library = result.nodesOfRoot('INV-15').single;
    expect(library.logicalBytes, 1424);
    expect(library.fileCount, 3);
    expect(library.byCategory[StorageCategory.userContent]!.logicalBytes, 1424);
    expect(
      result.allNodes.where((candidate) => candidate.path.contains('Sources')),
      isEmpty,
    );
    expect(library.children.map((child) => child.name), ['Books']);
  });

  test('progress reaches every root and counts entries', () async {
    for (var index = 0; index < 600; index++) {
      await write(doc('roms/snes/game-$index.sfc'), 2);
    }
    final events = <StorageScanProgress>[];
    final registry = StorageRootRegistry(containers);
    final result = await StorageScanner().scan(
      registry,
      onProgress: events.add,
    );
    expect(events, isNotEmpty);
    expect(events.every((event) => event.rootsTotal == 29), isTrue);
    expect(events.last.rootsDone, 29);
    expect(events.last.entries, result.entries);
    expect(events.last.bytes, result.logicalBytes);
    for (var index = 1; index < events.length; index++) {
      expect(
        events[index].rootsDone,
        greaterThanOrEqualTo(events[index - 1].rootsDone),
      );
      expect(
        events[index].entries,
        greaterThanOrEqualTo(events[index - 1].entries),
      );
    }
    // Counters from inside the INV-01 isolate (every 256 entries).
    expect(
      events.where(
        (event) =>
            event.rootId == 'INV-01' &&
            event.rootsDone == 0 &&
            event.entries > 0,
      ),
      isNotEmpty,
    );
  });

  test(
    'cancellation before the scan, between roots and inside a root',
    () async {
      final registry = StorageRootRegistry(containers);
      final early = StorageScanCancelToken()..cancel();
      final none = await StorageScanner().scan(registry, cancel: early);
      expect(none.cancelled, isTrue);
      expect(none.roots, isEmpty);

      final between = StorageScanCancelToken();
      final partial = await StorageScanner().scan(
        registry,
        cancel: between,
        onProgress: (event) {
          if (event.rootsDone >= 3) between.cancel();
        },
      );
      expect(partial.cancelled, isTrue);
      expect(partial.roots.map((root) => root.rootId).toSet(), {
        'INV-01',
        'INV-02',
        'INV-03',
      });

      // Many folders: the isolate sees the cancellation between listings.
      for (var folder = 0; folder < 400; folder++) {
        for (var index = 0; index < 8; index++) {
          await write(doc('roms/f$folder/g$index.bin'), 1);
        }
      }
      final inside = StorageScanCancelToken();
      var cancelledAt = -1;
      final stopped = await StorageScanner().scan(
        registry,
        cancel: inside,
        onProgress: (event) {
          if (event.rootId == 'INV-01' &&
              event.entries > 0 &&
              !inside.isCancelled) {
            cancelledAt = event.entries;
            inside.cancel();
          }
        },
      );
      expect(cancelledAt, greaterThan(0));
      expect(stopped.cancelled, isTrue);
      // The INV-01 isolate stopped before measuring its 3 600 entries.
      expect(stopped.roots, isEmpty);
      expect(stopped.entries, 0);
    },
  );

  test('a scan never writes anything', () async {
    await write(doc('roms/snes/a.sfc'), 10);
    await write(doc('Libretro/Skins/.staging/x/y.png'), 10);
    await write(tmp('picked.zip'), 10);
    await write(sup('NeoStation/RPCS3/Data/vfs.yml'), 10);
    final before = await snapshot();
    await StorageScanner().scan(StorageRootRegistry(containers));
    await StorageScanner(
      stat: const StorageStatLogical(),
    ).scan(StorageRootRegistry(containers));
    expect(await snapshot(), before);
  });
}
