import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/storage_locale.dart';
import 'package:neostation/services/library_source_files.dart';
import 'package:neostation/services/storage/storage_cleanup_planner.dart';
import 'package:neostation/services/storage/storage_orphan_detector.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:neostation/services/storage/storage_scanner.dart';
import 'package:neostation/services/storage/storage_stat_ffi.dart';
import 'package:path/path.dart' as p;

import 'database_test_helper.dart';

/// docs/storage-audit-cleanup.md § 3.7 and tests B and F of § 6 (planner
/// part), on real temporary trees: no plan of any level holds games, saves,
/// states, memory cards, BIOS, firmware, NAND, licences, pairing, books,
/// skins, settings, NeoSwap or unknown data; each level holds exactly its
/// lines and the lower levels, levels 1–2 preselected and level 3 never;
/// ages, kept logs, session exclusions (game or import running, libretro
/// session or unfinished journal, Dolphin marker) and the RPCS3 redirection.
void main() {
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late Directory home;
  late StorageContainers containers;

  /// The planner's clock: two days after the tree is written, so every
  /// entry without an explicit age is old enough.
  late DateTime now;

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

  /// Writes [length] bytes; [age] sets the modification time relative to
  /// the planner's clock.
  Future<File> write(String path, {int length = 8, Duration? age}) async {
    final file = File(path);
    await file.parent.create(recursive: true);
    await file.writeAsBytes(List<int>.filled(length, 7));
    if (age != null) await file.setLastModified(now.subtract(age));
    return file;
  }

  Future<void> rom(
    String system,
    String filename,
    String romPath,
  ) => db.execute(
    'INSERT INTO user_roms (app_system_id, filename, rom_path) VALUES (?, ?, ?)',
    [system, filename, romPath],
  );

  setUp(() async {
    StorageStatFfi.resetSession();
    now = DateTime.now().add(const Duration(days: 2));
    db = await helper.setUp();
    home = await Directory.systemTemp.createTemp('storage_planner_');
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
      'INSERT INTO app_system_extensions (system_id, extension) VALUES (?, ?)',
      ['snes', 'sfc'],
    );
  });

  tearDown(() async {
    StorageStatFfi.resetSession();
    await helper.tearDown();
    if (await home.exists()) await home.delete(recursive: true);
  });

  StorageSessionGuard guard({
    bool launch = false,
    bool libretro = false,
    bool dolphinMarker = false,
    bool journal = false,
  }) => StorageSessionGuard(
    launchActive: () => launch,
    libretroActive: () async => libretro,
    dolphinMarkerPresent: () async => dolphinMarker,
    libretroJournalUnfinished: () async => journal,
  );

  Future<(StorageCleanupPlan, StorageRootRegistry)> planFor(
    StorageCleanupLevel level, {
    StorageSessionGuard? sessions,
    List<String> libraryRoots = const [],
    bool redirected = false,
  }) async {
    final registry = StorageRootRegistry(
      containers,
      libraryRoots: libraryRoots,
      rpcs3Redirected: redirected,
    );
    final scan = await StorageScanner().scan(registry);
    final orphans = await StorageOrphanDetector(
      database: () async => db,
      registry: registry,
    ).detect(scan);
    final plan = await StorageCleanupPlanner(
      registry: registry,
      guard: sessions ?? guard(),
      now: () => now,
    ).plan(scan, orphans, level);
    return (plan, registry);
  }

  Set<String> paths(StorageCleanupPlan plan) => {
    for (final candidate in plan.candidates) candidate.path,
  };

  StorageCleanupCandidate candidate(StorageCleanupPlan plan, String path) =>
      plan.candidates.firstWhere((value) => value.path == path);

  bool inside(String parent, String path) =>
      parent == path || p.isWithin(parent, path);

  test('B — no plan of any level holds protected data', () async {
    final protected = <String>[
      // Games, ROM, ISO, installed games.
      doc('roms'),
      doc('MyGames'),
      doc('ARMSX2/Games'),
      doc('Ports/KartPad/Games/RMCP01.wbfs'),
      doc('Ports/Dusklight/Games/GZ2E01.rvz'),
      data('dev_hdd0/game'),
      data('games'),
      dolphin('Library'),
      // Saves, states, memory cards, NAND.
      doc('Libretro/Saves/Snes9x'),
      doc('Libretro/Saves/Azahar/Azahar'),
      doc('Libretro/States'),
      doc('ARMSX2/Saves'),
      doc('Ports/KartPad/Saves'),
      doc('Ports/Dusklight/Saves'),
      data('dev_hdd0/home/00000001/savedata'),
      data('savestates'),
      dolphin('User/GC'),
      dolphin('User/StateSaves'),
      dolphin('User/Wii'),
      dolphin('Saves'),
      // BIOS, firmware, licences, system files, pairing.
      doc('Libretro/System'),
      doc('ARMSX2/BIOS'),
      doc('Dolphin'),
      data('dev_flash'),
      data('dev_hdd0/home/00000001/exdata'),
      dolphin('Metadata'),
      sup('StikJIT'),
      // Books, skins, settings and indexes, user content.
      doc('Library/Books/Dune.epub'),
      doc('Library/Downloads'),
      doc(hiddenFolder),
      doc('Libretro/Skins/delta-snes'),
      doc('Libretro/SkinFavorites.json'),
      doc('Libretro/Config'),
      doc('Libretro/Cheats'),
      doc('user-data/config.json'),
      doc('user-data/data.sqlite'),
      doc('user-data/app.log'),
      doc('user-data/themes'),
      doc('user-data/background.png'),
      doc('RPCS3/Import'),
      dolphin('User/Config'),
      doc('Ports/KartPad/Config'),
      sup('Library/local-index.json'),
      data('games.yml'),
      dolphin('CrashMarkers/active-session.json'),
      // NeoSwap.
      cac('NeoSwap-v1'),
      cac('NeoSwapShaderStorage-v1'),
      // Unknown data.
      doc('stray.bin'),
      sup('NeoStation/Unknown'),
      cac('Somewhere'),
    ];
    for (final path in [
      doc('roms/snes/Super Mario World.sfc'),
      doc('roms/snes/Big Game.sfc.part'),
      doc('roms/psx/Final Fantasy VII/Final Fantasy VII (Disc 1).bin'),
      doc('MyGames/snes/Super Mario World.sfc'),
      doc('MyGames/n64/Mario.z64.part'),
      doc('ARMSX2/Games/God of War.iso'),
      doc('Ports/KartPad/Games/RMCP01.wbfs'),
      doc('Ports/Dusklight/Games/GZ2E01.rvz'),
      data('dev_hdd0/game/BLES00113/USRDIR/EBOOT.BIN'),
      data('games/ExtractedGames/BLES00114/PS3_GAME/PARAM.SFO'),
      dolphin('Library/gc/Metroid Prime.rvz'),
      doc('Libretro/Saves/Snes9x/Super Mario World.srm'),
      doc('Libretro/Saves/Snes9x/Super Mario World.srm.part'),
      doc('Libretro/Saves/Azahar/Azahar/nand/00000000/title.bin'),
      doc('Libretro/States/Snes9x/Super Mario World.state1'),
      doc('ARMSX2/Saves/Memory Cards/Mcd001.ps2'),
      doc('ARMSX2/Saves/Savestates/SLUS-20946 (0F0C4A9C).01.p2s'),
      doc('Ports/KartPad/Saves/NAND/title/00010004/data.bin'),
      doc('Ports/Dusklight/Saves/save.bin'),
      data('dev_hdd0/home/00000001/savedata/BLES00113-SAVE01/PARAM.SFO'),
      data('savestates/BLES00113.SAVESTAT'),
      dolphin('User/GC/USA/Card A/01-GALE-SuperSmashBros.gci'),
      dolphin('User/StateSaves/GALE01.s01'),
      dolphin('User/Wii/shared2/sys/SYSCONF'),
      dolphin('Saves/save.bin'),
      doc('Libretro/System/scph5501.bin'),
      doc('Libretro/System/firmware.bin.part'),
      doc('ARMSX2/BIOS/scph39001.bin'),
      doc('Dolphin/Wii/keys.bin'),
      data('dev_flash/sys/external/libsysutil.sprx'),
      data(
        'dev_hdd0/home/00000001/exdata/EP0001-BLES00113_00-0123456789ABCDEF.rap',
      ),
      dolphin('Metadata/IPL/USA/IPL.bin'),
      sup('StikJIT/pairing.mobiledevicepairing'),
      sup('StikJIT/pairing.import.tmp'),
      doc('Library/Books/Dune.epub'),
      doc('Library/Downloads/One Piece 1001.cbz'),
      doc(p.join(hiddenFolder, 'neostation-source-mangadex.json')),
      doc(p.join(hiddenFolder, 'partial.json.part')),
      doc('Libretro/Skins/delta-snes/info.json'),
      doc('Libretro/SkinFavorites.json'),
      doc('Libretro/Config/Azahar.json'),
      doc('Libretro/Cheats/Snes9x/Game.cht'),
      doc('user-data/config.json'),
      doc('user-data/data.sqlite'),
      doc('user-data/app.log'),
      doc('user-data/themes/epic/theme.xml'),
      doc('user-data/background.png'),
      doc('RPCS3/Import/Game Saves/saves.zip'),
      dolphin('User/Config/Dolphin.ini'),
      doc('Ports/KartPad/Config/Config.toml'),
      sup('Library/local-index.json'),
      data('games.yml'),
      dolphin('CrashMarkers/active-session.json'),
      cac('NeoSwap-v1/donation.bin'),
      cac('NeoSwapShaderStorage-v1/shader.bin'),
      doc('stray.bin'),
      sup('NeoStation/Unknown/x.bin'),
      cac('Somewhere/blob.bin'),
    ]) {
      await write(path, length: 64, age: const Duration(days: 30));
    }
    // What a plan may hold, to show the plans are not empty.
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    await write(doc('user-data/temp/snes/Game.zip/Game.sfc'));
    await write(sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'));
    await write(doc('Diagnostics/rpcs3_startup_debug.txt'));

    final mine = doc('MyGames');
    final registry = StorageRootRegistry(containers, libraryRoots: [mine]);
    for (final level in StorageCleanupLevel.values) {
      final (plan, _) = await planFor(level, libraryRoots: [mine]);
      expect(plan.candidates, isNotEmpty, reason: level.name);
      for (final candidate in plan.candidates) {
        expect(candidate.isDuplicate, isFalse);
        final targets = [
          candidate.path,
          for (final entry in candidate.entries) entry.path,
        ];
        for (final target in targets) {
          for (final path in protected) {
            expect(
              inside(path, target),
              isFalse,
              reason: '${level.name}: $target is inside protected $path',
            );
          }
          expect(registry.isProtected(target), isFalse, reason: target);
        }
      }
    }
    // The unreferenced duplicate pair is listed, never proposed.
    final (confirmed, _) = await planFor(
      StorageCleanupLevel.confirmed,
      libraryRoots: [mine],
    );
    expect(
      confirmed.candidates.where((candidate) => candidate.isDuplicate),
      isEmpty,
    );
  });

  test(
    'each level holds exactly its lines and the lower ones, preselection',
    () async {
      const minute = Duration(minutes: 1);
      const hour = Duration(hours: 1);
      await rom(
        'snes',
        'Super Mario World.sfc',
        doc('roms/snes/Super Mario World.sfc'),
      );
      await db.execute(
        'INSERT INTO user_screenscraper_metadata (app_system_id, filename) VALUES (?, ?)',
        ['snes', 'Super Mario World.sfc'],
      );
      await db.execute(
        'INSERT INTO user_screenscraper_metadata (app_system_id, filename) VALUES (?, ?)',
        ['snes', 'Deleted Game.sfc'],
      );
      await write(doc('roms/snes/Super Mario World.sfc'), length: 100);
      await write(doc('MyGames/snes/Super Mario World.sfc'), length: 100);
      await write(doc('media/snes/box2d/Super Mario World.png'));
      File(sup('Library/local-index.json'))
        ..createSync(recursive: true)
        ..writeAsStringSync('{"version": 1, "books": [{"id": "kept"}]}');
      await write(sup('Library/covers/kept.png'));

      final level1 = <String>{
        tmp('picked.zip'),
        tmp('com.neogamelab.neostation-Inbox/picked.zip'),
        tmp('armsx2-shaders-1234.zip'),
        cac('SoLoudLoader-Temp-Files/nav.wav'),
        tmp('NeoStation-Dolphin-FramePacing.json'),
        doc('media/snes/box2d/Partial.png.part'),
        doc('RPCS3/Export/Game Saves/.saves.zip.part'),
        doc('Ports/KartPad/Games/RMCP01.wbfs.part'),
        doc('Ports/Dusklight/Games/GZ2E01.rvz.part'),
        doc('Library/Books/.import-ab12.part'),
        doc('user-data/temp/snes'),
        doc('Libretro/Skins/.staging/import-1'),
        doc('user-data/background.importing.png'),
        sup('NeoStation/RPCS3/Imports/PS3UPDAT-1760000000.PUP'),
        data('dev_hdd0/home/00000001/.neostation-save-import-1'),
        doc('Ports/KartPad/Runtime/GameData.import-1234'),
        doc('Ports/KartPad/Runtime/GameData.rollback-5678'),
        doc('Libretro/Saves/Azahar/.neostation-3ds-import-20261012'),
        doc('Libretro/Saves/Azahar/.neostation-3ds-restore-20261012'),
        cac('Libretro/Content/game'),
        data('dev_hdd0/tmp/update.tmp'),
        cac('scan_123.mp3'),
        cac('scan_-42.jpg'),
      };
      final level2 = <String>{
        cac('Library/library_http'),
        cac('Library/library_images'),
        cac('Libretro/SkinCache/skin1'),
        cac('Libretro/SkinDownloads/pack.zip'),
        cac('Libretro/SkinInspection/inspect.bin'),
        cac('Libretro/skin-catalog.json'),
        dolphin('ShaderCache/GALE01.uidcache'),
        sup('NeoStation/RPCS3/Cache/ppu-BLES00113'),
        doc('media/snes/box2d/Deleted Game.png'),
        sup('Library/covers/orphan.png'),
        dolphin('Logs/dolphin-2026-10-01T10-00-00Z.jsonl'),
        dolphin('Logs/dolphin-2026-10-02T10-00-00Z.jsonl'),
        doc('Ports/KartPad/Logs/run-01.log'),
        doc('Ports/KartPad/Logs/run-02.log'),
        dolphin('CrashMarkers/active-session.json.1760000000000.recovered'),
        sup('Roboto-Regular_0123456789abcdef0123456789abcdef.ttf'),
        cac('com.neogamelab.neostation/Cache.db'),
        cac('com.neogamelab.neostation/fsCachedData'),
        cac('KartPad/shader.cache'),
        cac('Dusklight/pipeline'),
      };
      final level3 = <String>{
        doc('user-data/app.log.old'),
        doc('Diagnostics/rpcs3_startup_debug.txt'),
        doc('NeoPlay.jsonl'),
        doc('Recordings/Dolphin/clip.mp4'),
        doc('RPCS3/Export/Game Saves/saves.zip'),
        sup('NeoStation/RPCS3/SaveBackups/BLES00113-SAVE01-20261001'),
        sup('NeoStation/RPCS3/RapBackups/EP0001.rap'),
        sup('NeoStation/Maintenance/data-20261001-100000.sqlite'),
        doc('Libretro/Logs/previous-session.log'),
        doc('Libretro/Logs/session.log'),
        dolphin('Logs/dolphin-persistent.jsonl'),
        data('dev_hdd1/caches'),
        doc('Ports/KartPad/Runtime/GameData/sys'),
        doc('Libretro/Backups/Azahar/20261001-100000'),
        doc('MyGames/snes/Super Mario World.sfc'),
      };

      // Level 1 entries.
      await write(tmp('picked.zip'), age: minute * 20);
      await write(
        tmp('com.neogamelab.neostation-Inbox/picked.zip'),
        age: minute * 20,
      );
      await write(tmp('armsx2-shaders-1234.zip'), age: minute * 20);
      await write(cac('SoLoudLoader-Temp-Files/nav.wav'));
      await write(tmp('NeoStation-Dolphin-FramePacing.json'));
      await write(doc('media/snes/box2d/Partial.png.part'), age: hour * 2);
      await write(
        doc('RPCS3/Export/Game Saves/.saves.zip.part'),
        age: hour * 2,
      );
      await write(doc('Ports/KartPad/Games/RMCP01.wbfs.part'), age: hour * 2);
      await write(doc('Ports/Dusklight/Games/GZ2E01.rvz.part'), age: hour * 2);
      await write(doc('Library/Books/.import-ab12.part'), age: hour * 2);
      await write(doc('user-data/temp/snes/Game.zip/Game.sfc'), length: 300);
      await write(
        doc('Libretro/Skins/.staging/import-1/skin.deltaskin'),
        age: hour * 2,
      );
      await write(doc('user-data/background.importing.png'));
      await write(
        sup('NeoStation/RPCS3/Imports/PS3UPDAT-1760000000.PUP'),
        age: hour * 2,
      );
      await write(data('dev_hdd0/home/00000001/.neostation-save-import-1/x'));
      await write(
        doc('Ports/KartPad/Runtime/GameData.import-1234/sys/boot.bin'),
      );
      await write(doc('Ports/KartPad/Runtime/GameData.rollback-5678/x'));
      await write(
        doc('Libretro/Saves/Azahar/.neostation-3ds-import-20261012/a'),
      );
      await write(
        doc('Libretro/Saves/Azahar/.neostation-3ds-restore-20261012/b'),
      );
      await write(cac('Libretro/Content/game/disc.bin'));
      await write(data('dev_hdd0/tmp/update.tmp'));
      // Never proposed: too recent, not a picker copy, not a line.
      await write(tmp('fresh.zip'), age: minute * 5);
      await write(tmp('org.example-Inbox/sub/deep.bin'), age: hour);
      await write(tmp('someDir/x.bin'), age: hour);
      await write(doc('media/snes/box2d/Recent.png.part'), age: minute * 30);
      await write(
        doc('Libretro/Skins/.staging/import-2/skin.deltaskin'),
        age: minute * 30,
      );
      await write(doc('user-data/temp/fresh/x.bin'), age: minute * 5);
      await write(cac('temp_music_track.m4a'), age: minute * 5);
      await write(cac('Library/library_http/entry.part'), age: hour * 2);
      // The music player's copies (level 1 after 10 minutes, decision of the
      // lead) and the KartPad and Dusklight cache folders (level 2).
      await write(cac('scan_123.mp3'), age: hour);
      await write(cac('scan_-42.jpg'), age: minute * 20);
      await write(cac('KartPad/shader.cache'));
      await write(cac('Dusklight/pipeline/cache.bin'));
      // Level 2 entries.
      await write(cac('Library/library_images/cover.png'), length: 50);
      await write(cac('Libretro/SkinCache/skin1/a.png'));
      await write(cac('Libretro/SkinDownloads/pack.zip'));
      await write(cac('Libretro/SkinInspection/inspect.bin'));
      await write(cac('Libretro/skin-catalog.json'));
      await write(dolphin('ShaderCache/GALE01.uidcache'));
      await write(sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'));
      await write(doc('media/snes/box2d/Deleted Game.png'));
      await write(sup('Library/covers/orphan.png'));
      for (var day = 1; day <= 12; day++) {
        final stamp = day.toString().padLeft(2, '0');
        await write(
          dolphin('Logs/dolphin-2026-10-${stamp}T10-00-00Z.jsonl'),
          age: Duration(hours: 100 - day),
        );
        await write(
          doc('Ports/KartPad/Logs/run-$stamp.log'),
          age: Duration(hours: 100 - day),
        );
      }
      await write(
        dolphin('CrashMarkers/active-session.json.1760000000000.recovered'),
      );
      await write(sup('Roboto-Regular_0123456789abcdef0123456789abcdef.ttf'));
      await write(cac('com.neogamelab.neostation/Cache.db'));
      await write(cac('com.neogamelab.neostation/fsCachedData/0A1B'));
      // Level 3 entries.
      await write(doc('user-data/app.log.old'));
      await write(doc('Diagnostics/rpcs3_startup_debug.txt'));
      await write(doc('NeoPlay.jsonl'));
      await write(doc('Recordings/Dolphin/clip.mp4'));
      await write(doc('RPCS3/Export/Game Saves/saves.zip'));
      await write(
        sup('NeoStation/RPCS3/SaveBackups/BLES00113-SAVE01-20261001/PARAM.SFO'),
      );
      await write(sup('NeoStation/RPCS3/RapBackups/EP0001.rap'));
      await write(sup('NeoStation/Maintenance/data-20261001-100000.sqlite'));
      await write(sup('NeoStation/Maintenance/data-20261002-100000.sqlite'));
      await write(doc('Libretro/Logs/previous-session.log'));
      await File(doc('Libretro/Logs/session.log')).writeAsString(
        'NeoStation libretro session journal 1, started x\nEND closed\n',
      );
      await write(dolphin('Logs/dolphin-persistent.jsonl'));
      await write(data('dev_hdd1/caches/game.bin'));
      await write(doc('Ports/KartPad/Runtime/GameData/sys/boot.bin'));
      await write(doc('Libretro/Backups/Azahar/20261001-100000/sysdata/x'));

      final mine = [doc('MyGames')];
      final (safe, _) = await planFor(
        StorageCleanupLevel.safe,
        libraryRoots: mine,
      );
      final (regenerable, _) = await planFor(
        StorageCleanupLevel.regenerable,
        libraryRoots: mine,
      );
      final (confirmed, _) = await planFor(
        StorageCleanupLevel.confirmed,
        libraryRoots: mine,
      );

      expect(paths(safe), level1);
      expect(paths(regenerable), {...level1, ...level2});
      expect(paths(confirmed), {...level1, ...level2, ...level3});
      expect(safe.refusals, isEmpty);
      expect(confirmed.refusals, isEmpty);

      for (final plan in [safe, regenerable, confirmed]) {
        for (final value in plan.candidates) {
          final expectedLevel = level1.contains(value.path)
              ? StorageCleanupLevel.safe
              : level2.contains(value.path)
              ? StorageCleanupLevel.regenerable
              : StorageCleanupLevel.confirmed;
          expect(value.level, expectedLevel, reason: value.path);
          expect(
            value.preselected,
            expectedLevel != StorageCleanupLevel.confirmed,
            reason: value.path,
          );
          expect(value.relativePath, isNot(startsWith('/')));
          expect(value.displayPath, startsWith('<'));
          expect(
            StorageLocale.values['en']!.containsKey(value.reasonKey),
            isTrue,
            reason: value.reasonKey,
          );
          for (final key in value.warningKeys) {
            expect(StorageLocale.values['en']!.containsKey(key), isTrue);
          }
        }
      }
      // Level 3 is never preselected; levels 1 and 2 are.
      expect(confirmed.preselectedPaths, {
        ...level1,
        ...level2,
        StorageCleanupPlan.metadataSelectionKey,
      });
      expect(safe.preselectedPaths, level1);

      // Metadata rows from level 2: exactly the orphan keys.
      expect(safe.metadataKeys, isEmpty);
      expect(regenerable.metadataKeys, const [
        StorageOrphanMetadataKey('snes', 'Deleted Game.sfc'),
      ]);
      expect(regenerable.metadataPreselected, isTrue);

      // Warnings and reasons.
      expect(
        candidate(
          regenerable,
          sup('NeoStation/RPCS3/Cache/ppu-BLES00113'),
        ).warningKeys,
        [StorageLocale.rpcs3CacheWarning],
      );
      final media = candidate(
        regenerable,
        doc('media/snes/box2d/Deleted Game.png'),
      );
      expect(media.source, StorageCandidateSource.orphanMedia);
      expect(media.reasonKey, StorageLocale.orphanMedia);
      for (final path in [
        cac('KartPad/shader.cache'),
        cac('Dusklight/pipeline'),
      ]) {
        expect(candidate(regenerable, path).reasonKey, StorageLocale.catCaches);
      }
      expect(
        candidate(safe, cac('scan_123.mp3')).reasonKey,
        StorageLocale.catTemporary,
      );
      expect(media.warningKeys, [StorageLocale.mediaQuotaWarning]);
      expect(
        candidate(regenerable, sup('Library/covers/orphan.png')).reasonKey,
        StorageLocale.orphanCovers,
      );
      expect(
        candidate(
          confirmed,
          doc('Diagnostics/rpcs3_startup_debug.txt'),
        ).warningKeys,
        [StorageLocale.diagnosticsWarning],
      );
      expect(candidate(confirmed, data('dev_hdd1/caches')).warningKeys, [
        StorageLocale.hdd1Warning,
      ]);
      expect(
        candidate(
          confirmed,
          doc('Ports/KartPad/Runtime/GameData/sys'),
        ).warningKeys,
        [StorageLocale.kartpadGameDataWarning],
      );
      final duplicate = candidate(
        confirmed,
        doc('MyGames/snes/Super Mario World.sfc'),
      );
      expect(duplicate.isDuplicate, isTrue);
      expect(duplicate.preselected, isFalse);
      expect(duplicate.warningKeys, [StorageLocale.duplicateWarning]);
      expect(duplicate.pairedPath, doc('roms/snes/Super Mario World.sfc'));
      expect(
        duplicate.pairedDisplayPath,
        '<Documents>/roms/snes/Super Mario World.sfc',
      );

      // The Library caches are one API candidate each, never their files.
      for (final (path, api) in [
        (cac('Library/library_http'), StorageCacheApi.libraryHttp),
        (cac('Library/library_images'), StorageCacheApi.libraryImages),
      ]) {
        final cache = candidate(regenerable, path);
        expect(cache.source, StorageCandidateSource.cacheApi);
        expect(cache.cacheApi, api);
        expect(cache.entries, isEmpty);
      }
      expect(
        candidate(regenerable, cac('Library/library_images')).logicalBytes,
        50,
      );

      // A directory candidate lists its files, then its folders deepest
      // first, itself last.
      final temp = candidate(safe, doc('user-data/temp/snes'));
      expect(temp.kind, StorageEntryKind.directory);
      expect(temp.logicalBytes, 300);
      expect(temp.fileCount, 1);
      expect(
        [for (final entry in temp.entries) entry.path],
        [
          doc('user-data/temp/snes/Game.zip/Game.sfc'),
          doc('user-data/temp/snes/Game.zip'),
          doc('user-data/temp/snes'),
        ],
      );
      expect(temp.entries.first.modified, isNotNull);
      expect(
        safe.bytes,
        safe.candidates.fold<int>(0, (s, c) => s + c.logicalBytes),
      );
      expect(safe.preselectedBytes, safe.bytes);
    },
  );

  test('a game or an import running: no candidate, one refusal', () async {
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    await write(doc('Diagnostics/x.txt'));
    final (plan, _) = await planFor(
      StorageCleanupLevel.confirmed,
      sessions: guard(launch: true),
    );
    expect(plan.candidates, isEmpty);
    expect(plan.metadataKeys, isEmpty);
    expect(plan.blocked, isTrue);
    expect(plan.refusals, hasLength(1));
    expect(plan.refusals.single.path, StoragePlanRefusal.wholePlan);
    expect(plan.refusals.single.reason, StorageRefusalReason.sessionActive);
    expect(plan.refusals.single.localeKey, StorageLocale.sessionActive);
  });

  Future<void> writeLibretroAndOthers() async {
    await write(
      doc('Libretro/Skins/.staging/import-1/x'),
      age: const Duration(hours: 2),
    );
    await write(doc('Libretro/Logs/previous-session.log'));
    await write(cac('Libretro/Content/game/disc.bin'));
    await write(cac('Libretro/SkinCache/skin1/a.png'));
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    await write(doc('Diagnostics/x.txt'));
  }

  void expectLibretroExcluded(StorageCleanupPlan plan) {
    final libretro = {
      doc('Libretro/Skins/.staging/import-1'),
      doc('Libretro/Logs/previous-session.log'),
      cac('Libretro/Content/game'),
      cac('Libretro/SkinCache/skin1'),
    };
    for (final value in plan.candidates) {
      expect(
        StorageCleanupPlanner.libretroRootIds.contains(value.rootId),
        isFalse,
        reason: value.path,
      );
    }
    expect({
      for (final refusal in plan.refusals)
        if (refusal.reason == StorageRefusalReason.sessionActive) refusal.path,
    }, containsAll(libretro));
    expect(
      paths(plan),
      containsAll([tmp('picked.zip'), doc('Diagnostics/x.txt')]),
    );
  }

  test('F — a libretro session excludes INV-14 and INV-25', () async {
    await writeLibretroAndOthers();
    final (plan, _) = await planFor(
      StorageCleanupLevel.confirmed,
      sessions: guard(libretro: true),
    );
    expect(plan.session.libretroActive, isTrue);
    expectLibretroExcluded(plan);
  });

  test(
    'F — session.log without END in its last 4 KiB excludes INV-14 and INV-25',
    () async {
      await writeLibretroAndOthers();
      final journal = File(doc('Libretro/Logs/session.log'));
      StorageSessionGuard fromFiles() => StorageSessionGuard(
        launchActive: () => false,
        libretroActive: () async => false,
        containers: containers,
      );

      await journal.writeAsString(
        'NeoStation libretro session journal 1, started 2026-10-12T10:00:00Z\n'
        '2026-10-12T10:00:01Z +0.100s core loaded\n',
      );
      var (plan, _) = await planFor(
        StorageCleanupLevel.confirmed,
        sessions: fromFiles(),
      );
      expect(plan.session.libretroUnfinishedJournal, isTrue);
      expect(plan.session.libretroActive, isFalse);
      expectLibretroExcluded(plan);

      // Finished: the logs become level-3 candidates again.
      await journal.writeAsString(
        'END closed by the user\n',
        mode: FileMode.append,
      );
      (plan, _) = await planFor(
        StorageCleanupLevel.confirmed,
        sessions: fromFiles(),
      );
      expect(plan.session.libretroUnfinishedJournal, isFalse);
      expect(paths(plan), contains(doc('Libretro/Logs/session.log')));
      expect(paths(plan), contains(cac('Libretro/Content/game')));

      // The END line must be in the last 4 KiB (LibretroSessionJournal.m).
      await journal.writeAsString(
        '${List.filled(5000, 'x').join()}\n',
        mode: FileMode.append,
      );
      expect(await StorageSessionGuard.journalUnfinished(journal.path), isTrue);
      expect(
        await StorageSessionGuard.journalUnfinished(doc('Libretro/Logs/none')),
        isFalse,
      );
      await journal.writeAsString('');
      expect(
        await StorageSessionGuard.journalUnfinished(journal.path),
        isFalse,
      );
    },
  );

  test(
    'F — the Dolphin marker excludes INV-20 … INV-22 and the frame pacing',
    () async {
      await rom('snes', 'Metroid Prime.rvz', doc('roms/gc/Metroid Prime.rvz'));
      await write(doc('roms/gc/Metroid Prime.rvz'), length: 40);
      await write(dolphin('Library/gc/Metroid Prime.rvz'), length: 40);
      await write(dolphin('ShaderCache/GALE01.uidcache'));
      await write(dolphin('Logs/dolphin-persistent.jsonl'));
      await write(dolphin('CrashMarkers/active-session.json.1.recovered'));
      await write(tmp('NeoStation-Dolphin-FramePacing.json'));
      await write(tmp('picked.zip'), age: const Duration(hours: 1));
      StorageSessionGuard fromFiles() => StorageSessionGuard(
        launchActive: () => false,
        libretroActive: () async => false,
        containers: containers,
      );

      var (plan, _) = await planFor(
        StorageCleanupLevel.confirmed,
        sessions: fromFiles(),
      );
      final dolphinPaths = {
        dolphin('Library/gc/Metroid Prime.rvz'),
        dolphin('ShaderCache/GALE01.uidcache'),
        dolphin('Logs/dolphin-persistent.jsonl'),
        dolphin('CrashMarkers/active-session.json.1.recovered'),
        tmp('NeoStation-Dolphin-FramePacing.json'),
      };
      expect(plan.session.dolphinMarker, isFalse);
      expect(paths(plan), containsAll(dolphinPaths));

      await write(dolphin('CrashMarkers/active-session.json'));
      (plan, _) = await planFor(
        StorageCleanupLevel.confirmed,
        sessions: fromFiles(),
      );
      expect(plan.session.dolphinMarker, isTrue);
      expect(paths(plan).intersection(dolphinPaths), isEmpty);
      expect({
        for (final refusal in plan.refusals)
          if (refusal.reason == StorageRefusalReason.sessionActive)
            refusal.path,
      }, dolphinPaths);
      expect(paths(plan), contains(tmp('picked.zip')));
      // The marker itself is never a candidate.
      expect(
        paths(plan),
        isNot(contains(dolphin('CrashMarkers/active-session.json'))),
      );
    },
  );

  test('a failing probe counts as a running session', () async {
    await writeLibretroAndOthers();
    final (plan, _) = await planFor(
      StorageCleanupLevel.confirmed,
      sessions: StorageSessionGuard(
        launchActive: () => false,
        libretroActive: () async => throw StateError('channel closed'),
        dolphinMarkerPresent: () async => false,
        libretroJournalUnfinished: () async => false,
      ),
    );
    expect(plan.session.libretroActive, isTrue);
    expect(
      plan.session.probeErrors['libretroActive'],
      contains('channel closed'),
    );
    expectLibretroExcluded(plan);
  });

  test(
    'RPCS3 redirected by vfs.yml: INV-16 … INV-19 refused, INV-10 kept',
    () async {
      await write(sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'));
      await write(data('dev_hdd0/tmp/update.tmp'));
      await write(data('dev_hdd1/caches/game.bin'));
      await write(sup('NeoStation/RPCS3/RapBackups/EP0001.rap'));
      await write(
        doc('RPCS3/Export/Game Saves/.saves.zip.part'),
        age: const Duration(hours: 2),
      );
      final (plan, _) = await planFor(
        StorageCleanupLevel.confirmed,
        redirected: true,
      );
      expect(plan.rpcs3Redirected, isTrue);
      for (final value in plan.candidates) {
        expect(
          StorageRootRegistry.rpcs3RootIds.contains(value.rootId),
          isFalse,
          reason: value.path,
        );
      }
      expect(
        paths(plan),
        contains(doc('RPCS3/Export/Game Saves/.saves.zip.part')),
      );
      expect({
        for (final refusal in plan.refusals)
          if (refusal.reason == StorageRefusalReason.redirected) refusal.rootId,
      }, StorageRootRegistry.rpcs3RootIds);
      for (final refusal in plan.refusals) {
        expect(refusal.displayPath, startsWith('<Support>/NeoStation/RPCS3'));
      }
    },
  );

  test('ages: idle time, *.part inside a folder, staging', () async {
    const minute = Duration(minutes: 1);
    await write(doc('user-data/temp/old/x.bin'), age: minute * 20);
    await write(doc('user-data/temp/fresh/x.bin'), age: minute * 5);
    await write(doc('user-data/temp/young-part/x.part'), age: minute * 30);
    await write(doc('user-data/temp/old-part/x.part'), age: minute * 90);
    await write(doc('Libretro/Skins/.staging/a/x'), age: minute * 61);
    await write(doc('Libretro/Skins/.staging/b/x'), age: minute * 59);
    await write(tmp('nine.zip'), age: minute * 9);
    await write(tmp('eleven.zip'), age: minute * 11);
    await write(doc('media/snes/x.png.part'), age: minute * 59);
    await write(doc('media/snes/y.png.part'), age: minute * 61);
    // A partial picker copy is a *.part too: one hour.
    await write(tmp('copy.iso.part'), age: minute * 30);
    await write(tmp('old.iso.part'), age: minute * 90);
    final (plan, _) = await planFor(StorageCleanupLevel.safe);
    expect(paths(plan), {
      doc('user-data/temp/old'),
      doc('user-data/temp/old-part'),
      doc('Libretro/Skins/.staging/a'),
      tmp('eleven.zip'),
      doc('media/snes/y.png.part'),
      tmp('old.iso.part'),
    });
  });

  test(
    'a lower-level candidate inside a folder candidate stands alone',
    () async {
      await write(doc('Diagnostics/sub/a.txt'), length: 10);
      await write(
        doc('Diagnostics/sub/b.part'),
        length: 20,
        age: const Duration(hours: 2),
      );
      final (safe, _) = await planFor(StorageCleanupLevel.safe);
      expect(paths(safe), {doc('Diagnostics/sub/b.part')});

      final (confirmed, _) = await planFor(StorageCleanupLevel.confirmed);
      expect(paths(confirmed), {
        doc('Diagnostics/sub'),
        doc('Diagnostics/sub/b.part'),
      });
      final folder = candidate(confirmed, doc('Diagnostics/sub'));
      expect(folder.logicalBytes, 10);
      expect(
        [for (final entry in folder.entries) entry.path],
        [doc('Diagnostics/sub/a.txt'), doc('Diagnostics/sub')],
      );
      expect(
        candidate(confirmed, doc('Diagnostics/sub/b.part')).preselected,
        isTrue,
      );
      expect(folder.preselected, isFalse);
      expect(confirmed.bytes, 30);
    },
  );

  test(
    'an interrupted 3DS pass keeps its backup folder and every 3DS staging',
    () async {
      final importStaging = doc(
        'Libretro/Saves/Azahar/.neostation-3ds-import-20261012',
      );
      final restoreStaging = doc(
        'Libretro/Saves/Azahar/.neostation-3ds-restore-20261012',
      );
      final older = doc('Libretro/Backups/Azahar/20261001-100000');
      final complete = doc('Libretro/Backups/Azahar/20261002-100000');
      final interrupted = doc('Libretro/Backups/Azahar/20261003-100000');
      await write(p.join(importStaging, 'nand/title.app'));
      await write(p.join(restoreStaging, 'sysdata/otp.bin'));
      await write(p.join(older, 'sysdata/x'));
      for (final name in [
        StorageCleanupPlanner.threeDsPassLogName,
        '.neostation-manifest.json',
        StorageCleanupPlanner.threeDsCompleteMarkerName,
        'nand/x',
      ]) {
        await write(p.join(complete, name));
      }
      var (plan, _) = await planFor(StorageCleanupLevel.confirmed);
      expect(
        paths(plan),
        containsAll([importStaging, restoreStaging, older, complete]),
      );

      // A pass journal without its completion marker: an interrupted pass,
      // recovered from its backup folder and its staging by the 3DS page.
      await write(
        p.join(interrupted, StorageCleanupPlanner.threeDsPassLogName),
      );
      await write(p.join(interrupted, 'nand/original.bin'));
      for (final level in StorageCleanupLevel.values) {
        (plan, _) = await planFor(level);
        expect(
          paths(
            plan,
          ).intersection({importStaging, restoreStaging, interrupted}),
          isEmpty,
          reason: level.name,
        );
      }
      expect(paths(plan), containsAll([older, complete]));
    },
  );

  test(
    'the KartPad and Dusklight cache folders are level 2, never during a game',
    () async {
      await write(cac('KartPad/shaders/GALE01.cache'));
      await write(cac('KartPad/runtime.bin'));
      await write(cac('Dusklight/pipeline.bin'));
      final caches = {
        cac('KartPad/shaders'),
        cac('KartPad/runtime.bin'),
        cac('Dusklight/pipeline.bin'),
      };
      final (safe, _) = await planFor(StorageCleanupLevel.safe);
      expect(paths(safe).intersection(caches), isEmpty);
      for (final level in [
        StorageCleanupLevel.regenerable,
        StorageCleanupLevel.confirmed,
      ]) {
        final (plan, _) = await planFor(level);
        expect(paths(plan), containsAll(caches), reason: level.name);
        for (final path in caches) {
          final value = candidate(plan, path);
          expect(value.level, StorageCleanupLevel.regenerable);
          expect(value.preselected, isTrue);
          expect(value.reasonKey, StorageLocale.catCaches);
          expect(
            value.engine,
            path.contains('KartPad')
                ? StorageEngine.kartpad
                : StorageEngine.dusklight,
          );
        }
      }
      // Modified in the last minutes: the engine may still be writing.
      await write(cac('KartPad/fresh.bin'), age: const Duration(minutes: 5));
      final (fresh, _) = await planFor(StorageCleanupLevel.regenerable);
      expect(paths(fresh), isNot(contains(cac('KartPad/fresh.bin'))));
      expect(paths(fresh), containsAll(caches));
      // A game running (KartPad and Dusklight only run in a session).
      final (running, _) = await planFor(
        StorageCleanupLevel.regenerable,
        sessions: guard(launch: true),
      );
      expect(running.candidates, isEmpty);
      expect(
        running.refusals.single.reason,
        StorageRefusalReason.sessionActive,
      );
    },
  );

  test(
    'folders of tmp/ other than *-Inbox are never proposed, at any level',
    () async {
      final folders = [
        tmp('NeoStationDolphinJIT'),
        tmp('archive.part'),
        tmp('WebKit'),
      ];
      for (final path in [
        tmp('NeoStationDolphinJIT/helper.dylib'),
        tmp('NeoStationDolphinJIT/sub/deep.bin'),
        tmp('NeoStationDolphinJIT/stale.part'),
        tmp('archive.part/inner.bin'),
        tmp('WebKit/cache.db'),
      ]) {
        await write(path, age: const Duration(days: 3));
      }
      await write(tmp('picked.zip'), age: const Duration(hours: 1));
      await write(
        tmp('com.neogamelab.neostation-Inbox/picked.zip'),
        age: const Duration(hours: 1),
      );
      for (final level in StorageCleanupLevel.values) {
        final (plan, _) = await planFor(level);
        expect(
          {
            for (final value in plan.candidates)
              if (p.isWithin(containers.temporary, value.path)) value.path,
          },
          {
            tmp('picked.zip'),
            tmp('com.neogamelab.neostation-Inbox/picked.zip'),
          },
          reason: level.name,
        );
        for (final value in plan.candidates) {
          for (final entry in value.entries) {
            for (final folder in folders) {
              expect(inside(folder, entry.path), isFalse, reason: entry.path);
            }
          }
        }
      }
    },
  );

  test('folders a scan never lists are never proposed whole', () async {
    // A protected name inside a temporary folder stays out of its entries.
    await write(doc('user-data/temp/arch/config.json'));
    await write(doc('user-data/temp/arch/game.sfc'), length: 5);
    final outside = await Directory.systemTemp.createTemp('storage_outside_');
    addTearDown(() => outside.delete(recursive: true));
    await File(p.join(outside.path, 'secret.bin')).writeAsString('secret');
    await Link(doc('user-data/temp/arch/linked')).create(outside.path);
    final (plan, registry) = await planFor(StorageCleanupLevel.safe);
    final arch = candidate(plan, doc('user-data/temp/arch'));
    expect(
      [for (final entry in arch.entries) entry.path],
      [doc('user-data/temp/arch/game.sfc'), doc('user-data/temp/arch')],
    );
    expect(arch.logicalBytes, 5);
    expect(
      registry.isProtected(doc('user-data/temp/arch/config.json')),
      isTrue,
    );
  });
}
