import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/l10n/storage_locale.dart';
import 'package:neostation/services/libretro_3ds_system_data_service.dart';
import 'package:neostation/services/library_source_files.dart';
import 'package:neostation/services/storage/storage_cleanup_planner.dart';
import 'package:neostation/services/storage/storage_import_activity.dart';
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
/// lines and the lower levels, levels 1–2 preselected and nothing at all in
/// a level-3 plan; ages (from the later of the modification and the status
/// change, one hour for the picker's copies), kept logs, session exclusions
/// (game or import running, libretro session or unfinished journal, Dolphin
/// marker) and the RPCS3 redirection.
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
    libraryScanActive: () => false,
  );

  Future<(StorageCleanupPlan, StorageRootRegistry)> planFor(
    StorageCleanupLevel level, {
    StorageSessionGuard? sessions,
    List<String> libraryRoots = const [],
    bool redirected = false,
    bool hash = false,
    StorageScanner? scanner,
  }) async {
    final registry = StorageRootRegistry(
      containers,
      libraryRoots: libraryRoots,
      rpcs3Redirected: redirected,
    );
    final scan = await (scanner ?? StorageScanner()).scan(registry);
    final orphans = await StorageOrphanDetector(
      database: () async => db,
      registry: registry,
    ).detect(scan, hashDuplicates: hash);
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
    // Partial files of the user in games and user content folders, old
    // enough for the one-hour `*.part` age.
    final userParts = <String>[
      doc('ARMSX2/Games/God of War.iso.part'),
      dolphin('Library/gc/Metroid Prime.rvz.part'),
      doc('Libretro/Skins/delta-snes/assets.part'),
      dolphin('User/Load/Textures/GALE01/tex1_64x64_x.png.part'),
      doc('Library/Downloads/One Piece 1002.cbz.part'),
      doc('Library/Books/Dune.epub.part'),
      doc('Ports/KartPad/Mods/track.szs.part'),
      doc('user-data/themes/epic/bg.png.part'),
      doc('Libretro/Cheats/Snes9x/Game.cht.part'),
      doc('RPCS3/Import/Game Saves/save.zip.part'),
    ];
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
      // Review of the storage services: the backups NeoStation makes of user
      // data, the NSURLCache database, and the `.part` files of games and
      // user content folders (where the `*.part` override used to apply).
      sup('NeoStation/RPCS3/SaveBackups'),
      sup('NeoStation/RPCS3/RapBackups'),
      sup('NeoStation/Maintenance/data-20261001-100000.sqlite'),
      doc('Libretro/Backups/Azahar'),
      cac('com.neogamelab.neostation/Cache.db'),
      ...userParts,
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
      sup('NeoStation/RPCS3/SaveBackups/BLES00113-SAVE01-1/PARAM.SFO'),
      sup('NeoStation/RPCS3/RapBackups/EP0001.rap'),
      sup('NeoStation/Maintenance/data-20261001-100000.sqlite'),
      doc('Libretro/Backups/Azahar/20261001-100000/sysdata/otp.bin'),
      cac('com.neogamelab.neostation/Cache.db'),
      ...userParts,
    ]) {
      await write(path, length: 64, age: const Duration(days: 30));
    }
    // What a plan may hold, to show the plans are not empty.
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    await write(doc('user-data/temp/snes/Game.zip/Game.sfc'));
    await write(sup('NeoStation/RPCS3/Cache/ppu-BLES00113/obj.bin'));
    await write(doc('Diagnostics/rpcs3_startup_debug.txt'));
    await write(cac('com.neogamelab.neostation/fsCachedData/0A1B'));

    final mine = doc('MyGames');
    // This test's library folder, then the production inputs as well:
    // `Documents/roms` and the ARMSX2 linked folders that
    // StorageRootRegistry.resolve() adds (review of the storage services).
    for (final roots in [
      [mine],
      [doc('roms'), doc('ARMSX2'), doc('ARMSX2/Games'), mine],
    ]) {
      final registry = StorageRootRegistry(containers, libraryRoots: roots);
      for (final (level, hash) in [
        for (final level in StorageCleanupLevel.values) (level, false),
        (StorageCleanupLevel.confirmed, true),
      ]) {
        final (plan, _) = await planFor(level, libraryRoots: roots, hash: hash);
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
        // Contract replaced by the review of the storage services: the
        // NSURLCache database `Cache.db` used to be a level-2 candidate
        // beside `fsCachedData`; an open SQLite file of the system, it is
        // never proposed now (below).
        cac('com.neogamelab.neostation/fsCachedData'),
        cac('KartPad/shader.cache'),
      };
      final level3 = <String>{
        doc('user-data/app.log.old'),
        doc('Diagnostics/rpcs3_startup_debug.txt'),
        doc('NeoPlay.jsonl'),
        doc('Recordings/Dolphin/clip.mp4'),
        doc('RPCS3/Export/Game Saves/saves.zip'),
        doc('Libretro/Logs/previous-session.log'),
        doc('Libretro/Logs/session.log'),
        dolphin('Logs/dolphin-persistent.jsonl'),
        data('dev_hdd1/caches'),
        doc('Ports/KartPad/Runtime/GameData/sys'),
      };
      // Contract replaced by the review of the storage services: the RPCS3
      // save and licence backups, the copies of data.sqlite and the 3DS
      // backups used to be level-3 candidates; backups of user data, they
      // are never proposed now. The unreferenced duplicate used to be one
      // too without checksums: it is offered only when its checksum equals
      // the referenced copy's (the hashed plan below).
      final neverProposed = <String>{
        sup('NeoStation/RPCS3/SaveBackups/BLES00113-SAVE01-20261001'),
        sup('NeoStation/RPCS3/RapBackups/EP0001.rap'),
        sup('NeoStation/Maintenance/data-20261001-100000.sqlite'),
        sup('NeoStation/Maintenance/data-20261002-100000.sqlite'),
        doc('Libretro/Backups/Azahar/20261001-100000'),
        cac('com.neogamelab.neostation/Cache.db'),
        // Contract replaced by the removal of Dusklight and the Ports
        // playlist (docs/ports-removal-2026-10-20.md): its partial game copy
        // (level 1) and its cache folder (level 2) used to be candidates.
        // Without the engine they are unknown data, never proposed.
        doc('Ports/Dusklight/Games/GZ2E01.rvz.part'),
        cac('Dusklight'),
      };
      final duplicatePath = doc('MyGames/snes/Super Mario World.sfc');

      // Level 1 entries. The picker's copies wait one hour since the review
      // of phase 5d (they used to wait 10 minutes; a copy keeps the date of
      // its original, and an import may still be reading it).
      await write(tmp('picked.zip'), age: minute * 65);
      await write(
        tmp('com.neogamelab.neostation-Inbox/picked.zip'),
        age: minute * 65,
      );
      await write(tmp('armsx2-shaders-1234.zip'), age: minute * 65);
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
      await write(tmp('recent.zip'), age: minute * 30);
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
      // lead), the KartPad cache folder (level 2) and the one Dusklight left
      // (never).
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
      final (hashed, _) = await planFor(
        StorageCleanupLevel.confirmed,
        libraryRoots: mine,
        hash: true,
      );

      expect(paths(safe), level1);
      expect(paths(regenerable), {...level1, ...level2});
      expect(paths(confirmed), {...level1, ...level2, ...level3});
      expect(paths(hashed), {...level1, ...level2, ...level3, duplicatePath});
      for (final plan in [safe, regenerable, confirmed, hashed]) {
        for (final path in neverProposed) {
          expect(
            plan.candidates.where((value) => inside(path, value.path)),
            isEmpty,
            reason: '${plan.level.name}: $path',
          );
        }
      }
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
          // Review of phase 5d: a level-3 plan preselects nothing, its
          // level-1 and level-2 lines included (they used to be ticked).
          expect(
            value.preselected,
            plan.level != StorageCleanupLevel.confirmed &&
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
      // Levels 1 and 2 are preselected; a level-3 plan preselects nothing,
      // not even its level-1 and level-2 lines nor the metadata rows (review
      // of phase 5d: they used to be ticked there too).
      expect(confirmed.preselectedPaths, isEmpty);
      expect(confirmed.preselectedBytes, 0);
      expect(regenerable.preselectedPaths, {
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
      // Listed at level 3 too, never ticked there.
      expect(confirmed.metadataKeys, regenerable.metadataKeys);
      expect(confirmed.metadataPreselected, isFalse);

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
      expect(
        candidate(regenerable, cac('KartPad/shader.cache')).reasonKey,
        StorageLocale.catCaches,
      );
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
      final duplicate = candidate(hashed, duplicatePath);
      expect(duplicate.isDuplicate, isTrue);
      expect(duplicate.level, StorageCleanupLevel.confirmed);
      expect(duplicate.preselected, isFalse);
      expect(duplicate.warningKeys, [StorageLocale.duplicateWarning]);
      expect(duplicate.pairedPath, doc('roms/snes/Super Mario World.sfc'));
      expect(
        duplicate.pairedDisplayPath,
        '<Documents>/roms/snes/Super Mario World.sfc',
      );
      // What the deletion checks again: the checksum of both copies and the
      // referenced copy's size and modification time at the preview.
      expect(duplicate.sha256, isNotNull);
      expect(duplicate.pairedLogicalBytes, 100);
      expect(
        duplicate.pairedModified,
        File(doc('roms/snes/Super Mario World.sfc')).statSync().modified,
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
    void expectRefused(StorageCleanupPlan plan) {
      expect(plan.candidates, isEmpty);
      expect(plan.metadataKeys, isEmpty);
      expect(plan.blocked, isTrue);
      expect(plan.refusals, hasLength(1));
      expect(plan.refusals.single.path, StoragePlanRefusal.wholePlan);
      expect(plan.refusals.single.reason, StorageRefusalReason.sessionActive);
      expect(plan.refusals.single.localeKey, StorageLocale.sessionActive);
    }

    var (plan, _) = await planFor(
      StorageCleanupLevel.confirmed,
      sessions: guard(launch: true),
    );
    expectRefused(plan);
    expect(plan.session.launchActive, isTrue);

    // An import that follows a Files pick (review of phase 5d): the default
    // guard reads StorageImportActivity, the whole plan is refused too.
    addTearDown(StorageImportActivity.reset);
    final picking = Completer<void>();
    final import = StorageImportActivity.run(() => picking.future);
    for (final level in StorageCleanupLevel.values) {
      (plan, _) = await planFor(level);
      expectRefused(plan);
      expect(plan.session.importActive, isTrue, reason: level.name);
      expect(plan.session.launchActive, isFalse);
    }
    picking.complete();
    await import;
    (plan, _) = await planFor(StorageCleanupLevel.confirmed);
    expect(plan.blocked, isFalse);
    expect(plan.session.importActive, isFalse);
    expect(
      paths(plan),
      containsAll([tmp('picked.zip'), doc('Diagnostics/x.txt')]),
    );
  });

  test('a failing import probe counts as an import running', () async {
    await write(tmp('picked.zip'), age: const Duration(hours: 1));
    final (plan, _) = await planFor(
      StorageCleanupLevel.safe,
      sessions: StorageSessionGuard(
        launchActive: () => false,
        libretroActive: () async => false,
        dolphinMarkerPresent: () async => false,
        libretroJournalUnfinished: () async => false,
        importActive: () => throw StateError('import state unreadable'),
        libraryScanActive: () => false,
      ),
    );
    expect(plan.session.importActive, isTrue);
    expect(
      plan.session.probeErrors['importActive'],
      contains('import state unreadable'),
    );
    expect(plan.blocked, isTrue);
    expect(plan.candidates, isEmpty);
  });

  // Review of the storage services: the library scanner rewrites user_roms
  // (the orphans are computed from it) and keeps a transaction open on the
  // database while it reads files.
  test(
    'a library scan in progress: no candidate, one refusal of its own',
    () async {
      await write(tmp('picked.zip'), age: const Duration(hours: 1));
      await write(doc('Diagnostics/x.txt'));
      StorageSessionGuard scanning({
        bool Function()? scan,
        bool launch = false,
      }) => StorageSessionGuard(
        launchActive: () => launch,
        libretroActive: () async => false,
        dolphinMarkerPresent: () async => false,
        libretroJournalUnfinished: () async => false,
        importActive: () => false,
        libraryScanActive: scan,
      );
      void expectRefused(StorageCleanupPlan plan, StorageRefusalReason reason) {
        expect(plan.candidates, isEmpty);
        expect(plan.metadataKeys, isEmpty);
        expect(plan.blocked, isTrue);
        expect(plan.refusals, hasLength(1));
        expect(plan.refusals.single.path, StoragePlanRefusal.wholePlan);
        expect(plan.refusals.single.reason, reason);
      }

      for (final level in StorageCleanupLevel.values) {
        final (plan, _) = await planFor(
          level,
          sessions: scanning(scan: () => true),
        );
        expectRefused(plan, StorageRefusalReason.libraryScanActive);
        expect(plan.refusals.single.localeKey, StorageLocale.refuseLibraryScan);
        expect(plan.session.libraryScanActive, isTrue);
        expect(plan.session.wholeCleanupRefused, isTrue);
      }
      // A game as well: the game's reason, as before.
      var (plan, _) = await planFor(
        StorageCleanupLevel.safe,
        sessions: scanning(scan: () => true, launch: true),
      );
      expectRefused(plan, StorageRefusalReason.sessionActive);
      // A failing probe counts as a scan.
      (plan, _) = await planFor(
        StorageCleanupLevel.safe,
        sessions: scanning(scan: () => throw StateError('provider disposed')),
      );
      expectRefused(plan, StorageRefusalReason.libraryScanActive);
      expect(
        plan.session.probeErrors['libraryScanActive'],
        contains('provider disposed'),
      );
      // No probe at all: nobody can tell that no scan runs (fail closed).
      (plan, _) = await planFor(StorageCleanupLevel.safe, sessions: scanning());
      expectRefused(plan, StorageRefusalReason.libraryScanActive);
      expect(
        plan.session.probeErrors['libraryScanActive'],
        contains('no library scan probe'),
      );
      // Idle: the plan is built.
      (plan, _) = await planFor(
        StorageCleanupLevel.confirmed,
        sessions: scanning(scan: () => false),
      );
      expect(plan.blocked, isFalse);
      expect(
        paths(plan),
        containsAll([tmp('picked.zip'), doc('Diagnostics/x.txt')]),
      );
    },
  );

  test(
    'a known system without any game row keeps all its media and metadata',
    () async {
      await db.execute(
        'INSERT INTO app_systems (id, real_name, folder_name) VALUES (?, ?, ?)',
        ['psx', 'PSX', 'psx'],
      );
      // snes has a game: the library is not empty.
      await rom('snes', 'Zelda.sfc', doc('roms/snes/Zelda.sfc'));
      for (final (system, name) in [
        ('psx', 'Final Fantasy VII.cue'),
        ('snes', 'Deleted Game.sfc'),
      ]) {
        await db.execute(
          'INSERT INTO user_screenscraper_metadata (app_system_id, filename) VALUES (?, ?)',
          [system, name],
        );
      }
      // The psx games live in a library folder the last scan could not
      // read: their rows are gone, their media are still there.
      final psxMedia = [
        doc('media/psx/box2d/Final Fantasy VII.png'),
        doc('media/psx/screenshots/Final Fantasy VII.png'),
        doc('media/psx/videos/Final Fantasy VII.mp4'),
        doc('media/psx/manuals/Final Fantasy VII.pdf'),
        doc('media/psx/box2d/Custom cover set by the user.png'),
      ];
      for (final path in psxMedia) {
        await write(path, length: 2048);
      }
      await write(doc('media/snes/box2d/Zelda.png'), length: 2048);
      await write(doc('media/snes/box2d/Deleted Game.png'), length: 2048);
      for (final level in [
        StorageCleanupLevel.regenerable,
        StorageCleanupLevel.confirmed,
      ]) {
        final (plan, _) = await planFor(level);
        expect(paths(plan).intersection(psxMedia.toSet()), isEmpty);
        expect(paths(plan), contains(doc('media/snes/box2d/Deleted Game.png')));
        expect(paths(plan), isNot(contains(doc('media/snes/box2d/Zelda.png'))));
        expect(plan.metadataKeys, const [
          StorageOrphanMetadataKey('snes', 'Deleted Game.sfc'),
        ]);
      }
    },
  );

  test('a registered library folder missing: no orphan media, metadata or '
      'cover is proposed, the caches still are', () async {
    await rom('snes', 'Zelda.sfc', doc('roms/snes/Zelda.sfc'));
    await write(doc('roms/snes/Zelda.sfc'));
    await db.execute(
      'INSERT INTO user_screenscraper_metadata (app_system_id, filename) VALUES (?, ?)',
      ['snes', 'Deleted Game.sfc'],
    );
    await write(doc('media/snes/box2d/Deleted Game.png'));
    File(sup('Library/local-index.json'))
      ..createSync(recursive: true)
      ..writeAsStringSync('{"version": 1, "books": []}');
    await write(sup('Library/covers/orphan.png'));
    await write(cac('Libretro/SkinCache/skin1/a.png'));
    final orphans = {
      doc('media/snes/box2d/Deleted Game.png'),
      sup('Library/covers/orphan.png'),
    };
    var (plan, _) = await planFor(
      StorageCleanupLevel.regenerable,
      libraryRoots: [doc('roms')],
    );
    expect(paths(plan), containsAll(orphans));
    expect(plan.metadataKeys, hasLength(1));
    // The folder of the scan is gone (an external drive, a stale bookmark).
    (plan, _) = await planFor(
      StorageCleanupLevel.regenerable,
      libraryRoots: [doc('roms'), doc('Removed Drive')],
    );
    expect(paths(plan).intersection(orphans), isEmpty);
    expect(plan.metadataKeys, isEmpty);
    expect(paths(plan), contains(cac('Libretro/SkinCache/skin1')));
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
        libraryScanActive: () => false,
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
        libraryScanActive: () => false,
      );

      // The duplicate in Dolphin/Library is offered with the checksums only
      // (review of the storage services; it used to be without).
      var (plan, _) = await planFor(
        StorageCleanupLevel.confirmed,
        sessions: fromFiles(),
        hash: true,
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
        hash: true,
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
        libraryScanActive: () => false,
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
    // The picker's copies wait one hour (review of phase 5d: 10 minutes
    // before, when eleven.zip was proposed).
    await write(tmp('nine.zip'), age: minute * 9);
    await write(tmp('eleven.zip'), age: minute * 11);
    await write(tmp('fifty-nine.zip'), age: minute * 59);
    await write(tmp('sixty-one.zip'), age: minute * 61);
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
      tmp('sixty-one.zip'),
      doc('media/snes/y.png.part'),
      tmp('old.iso.part'),
    });
  });

  test('ages count from the later of the modification and the status change '
      '(a copy keeps the date of its original)', () async {
    final real = DateTime.now();
    // The picker just copied an old game (its modification date is the
    // original's, three days old) and an import unpacked an old archive
    // into user-data/temp: their status change is the copy, just now.
    now = real.add(const Duration(minutes: 30));
    await write(tmp('Old Game.zip'), age: const Duration(days: 3));
    await write(
      doc('user-data/temp/unpacked/Old Game.sfc'),
      age: const Duration(days: 3),
    );
    final (scan, plan) = await () async {
      final registry = StorageRootRegistry(containers);
      final scan = await StorageScanner().scan(registry);
      final plan = await StorageCleanupPlanner(
        registry: registry,
        guard: guard(),
        now: () => now,
      ).plan(scan, const StorageOrphanReport(), StorageCleanupLevel.safe);
      return (scan, plan);
    }();
    // The scanner keeps both dates.
    final copy = scan.allNodes.firstWhere(
      (node) => node.path == tmp('Old Game.zip'),
    );
    expect(
      copy.modified!.isBefore(real.subtract(const Duration(days: 2))),
      isTrue,
    );
    expect(copy.changed, isNotNull);
    expect(
      copy.changed!.isAfter(real.subtract(const Duration(minutes: 5))),
      isTrue,
    );
    // Idle for 30 minutes since the copy: under the picker's hour, over
    // user-data/temp's 10 minutes.
    expect(paths(plan), {doc('user-data/temp/unpacked')});

    // Two hours after the copy, the picker's copy is idle long enough.
    now = real.add(const Duration(hours: 2));
    final (later, _) = await planFor(StorageCleanupLevel.safe);
    expect(paths(later), {tmp('Old Game.zip'), doc('user-data/temp/unpacked')});
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
      // Preselected in a level-1 plan; a level-3 plan preselects nothing
      // (review of phase 5d: the level-1 line used to be ticked there too).
      expect(
        candidate(safe, doc('Diagnostics/sub/b.part')).preselected,
        isTrue,
      );
      expect(
        candidate(confirmed, doc('Diagnostics/sub/b.part')).preselected,
        isFalse,
      );
      expect(folder.preselected, isFalse);
      expect(confirmed.preselectedPaths, isEmpty);
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
      // Contract replaced by the review of the storage services: the backup
      // folders (`older`, `complete`) used to be level-3 candidates; they
      // may hold the only copy of console-unique files and are never
      // proposed now, whatever the level. The staging folders stay level-1
      // candidates while no pass is interrupted.
      bool any3ds(StorageCleanupPlan plan, Iterable<String> roots) => plan
          .candidates
          .any((value) => roots.any((root) => inside(root, value.path)));
      var (plan, _) = await planFor(StorageCleanupLevel.confirmed);
      expect(paths(plan), containsAll([importStaging, restoreStaging]));
      expect(candidate(plan, importStaging).level, StorageCleanupLevel.safe);
      for (final level in StorageCleanupLevel.values) {
        (plan, _) = await planFor(level);
        expect(any3ds(plan, [older, complete]), isFalse, reason: level.name);
      }

      // A pass journal without its completion marker: an interrupted pass,
      // recovered from its backup folder and its staging by the 3DS page.
      await write(
        p.join(interrupted, StorageCleanupPlanner.threeDsPassLogName),
      );
      await write(p.join(interrupted, 'nand/original.bin'));
      for (final level in StorageCleanupLevel.values) {
        (plan, _) = await planFor(level);
        expect(
          any3ds(plan, [
            importStaging,
            restoreStaging,
            older,
            complete,
            interrupted,
          ]),
          isFalse,
          reason: level.name,
        );
      }
      expect(
        await StorageCleanupPlanner.interrupted3dsPasses(
          StorageRootRegistry(containers),
        ),
        {storageCanonicalPath(interrupted)},
      );
    },
  );

  /// Lists a directory sorted by name, the 3DS pass journals last, so that
  /// an entry bound is reached before them (test seam of the scanner).
  Stream<FileSystemEntity> journalsLast(Directory directory) async* {
    final entities = directory.listSync(followLinks: false)
      ..sort((a, b) {
        int rank(FileSystemEntity entity) =>
            p.basename(entity.path) == StorageCleanupPlanner.threeDsPassLogName
            ? 1
            : 0;
        final byRank = rank(a).compareTo(rank(b));
        return byRank != 0 ? byRank : a.path.compareTo(b.path);
      });
    for (final entity in entities) {
      yield entity;
    }
  }

  // Review of the storage services: the interrupted passes are read from
  // the disk, not from the scan, and an incomplete walk of INV-14 or an
  // unreadable backups folder offers nothing of the 3DS (fail closed).
  test('an interrupted 3DS pass hidden by a truncated scan still keeps every '
      '3DS staging', () async {
    const stamp = '20261012-100000';
    final backup = doc('Libretro/Backups/Azahar/$stamp');
    for (var index = 0; index < 40; index++) {
      await write(p.join(backup, 'f$index.bin'));
    }
    await write(p.join(backup, StorageCleanupPlanner.threeDsPassLogName));
    final staging = doc(
      'Libretro/Saves/Azahar/${Libretro3dsSystemDataService.stagingPrefix}'
      '$stamp',
    );
    await write(p.join(staging, 'sysdata/keys.txt'));
    final truncated = StorageScanner(
      maxEntriesPerRoot: 20,
      lister: journalsLast,
    );
    for (final scanner in [null, truncated]) {
      for (final level in StorageCleanupLevel.values) {
        final (plan, _) = await planFor(level, scanner: scanner);
        expect(plan.candidateFor(staging), isNull, reason: level.name);
        expect(plan.preselectedPaths, isNot(contains(staging)));
      }
    }
    // The truncated walk did not see the journal: the disk did.
    final registry = StorageRootRegistry(containers);
    final scan = await truncated.scan(registry);
    expect(scan.truncations.map((cut) => cut.rootId), contains('INV-14'));
    expect(
      scan
          .nodesOfRoot('INV-14')
          .expand((node) => node.descendants)
          .where(
            (node) => node.name == StorageCleanupPlanner.threeDsPassLogName,
          ),
      isEmpty,
    );

    // The pass completes: the staging is offered again by a full walk,
    // never by a truncated one.
    await write(
      p.join(backup, StorageCleanupPlanner.threeDsCompleteMarkerName),
    );
    var (plan, _) = await planFor(StorageCleanupLevel.safe);
    expect(plan.candidateFor(staging), isNotNull);
    expect(plan.preselectedPaths, contains(staging));
    (plan, _) = await planFor(StorageCleanupLevel.safe, scanner: truncated);
    expect(plan.candidateFor(staging), isNull);
  });

  test('an unreadable 3DS backups folder offers nothing of the 3DS', () async {
    final staging = doc(
      'Libretro/Saves/Azahar/${Libretro3dsSystemDataService.stagingPrefix}'
      '20261012-100000',
    );
    await write(p.join(staging, 'nand/x'));
    // Not a folder: its passes cannot be read.
    await write(doc('Libretro/Backups/Azahar'));
    final registry = StorageRootRegistry(containers);
    expect(await StorageCleanupPlanner.interrupted3dsPasses(registry), isNull);
    final (plan, _) = await planFor(StorageCleanupLevel.safe);
    expect(plan.candidateFor(staging), isNull);
    await File(doc('Libretro/Backups/Azahar')).delete();
    // No backups folder at all: no pass, the staging is offered.
    expect(await StorageCleanupPlanner.interrupted3dsPasses(registry), isEmpty);
    final (open, _) = await planFor(StorageCleanupLevel.safe);
    expect(open.candidateFor(staging), isNotNull);
  });

  test(
    'the KartPad cache folder is level 2, never during a game; Dusklight\'s '
    'is never proposed',
    () async {
      await write(cac('KartPad/shaders/GALE01.cache'));
      await write(cac('KartPad/runtime.bin'));
      // Left by Dusklight (removed, docs/ports-removal-2026-10-20.md).
      await write(cac('Dusklight/pipeline.bin'));
      final caches = {
        cac('KartPad/shaders'),
        cac('KartPad/runtime.bin'),
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
          // Ticked in the level-2 plan only: a level-3 plan preselects
          // nothing (review of phase 5d).
          expect(
            value.preselected,
            level == StorageCleanupLevel.regenerable,
            reason: level.name,
          );
          expect(value.reasonKey, StorageLocale.catCaches);
          expect(value.engine, StorageEngine.kartpad);
        }
        expect(paths(plan), isNot(contains(cac('Dusklight/pipeline.bin'))));
      }
      // Modified in the last minutes: the engine may still be writing.
      await write(cac('KartPad/fresh.bin'), age: const Duration(minutes: 5));
      final (fresh, _) = await planFor(StorageCleanupLevel.regenerable);
      expect(paths(fresh), isNot(contains(cac('KartPad/fresh.bin'))));
      expect(paths(fresh), containsAll(caches));
      // A game running.
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
