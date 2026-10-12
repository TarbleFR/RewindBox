import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/storage/storage_categorizer.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:path/path.dart' as p;

/// Test B of docs/storage-audit-cleanup.md § 6 (categorizer part): every
/// path of classes A/B/C/H/I and index of § 2, and the hidden library
/// folder, is never deletable; an unknown path is never deletable; the
/// order is never-lists, deepest rule, then the `*.part` override.
void main() {
  const home =
      '/var/mobile/Containers/Data/Application/5F0E7A21-0B6C-4D2E-8A41-1C2D3E4F5A6B';
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
  String data(String relative) =>
      sup(p.join('NeoStation/RPCS3/Data', relative));
  String dolphin(String relative) =>
      sup(p.join('NeoStation/Dolphin', relative));

  const externalLibrary =
      '/var/mobile/Library/Mobile Documents/com~apple~CloudDocs/Roms';
  const linked =
      '/var/mobile/Containers/Data/Application/AAAA-RETROARCH/Documents';
  final registry = StorageRootRegistry(
    containers,
    libraryRoots: [doc('MyGames'), externalLibrary],
    linkedExternalFolder: linked,
  );
  final categorizer = StorageCategorizer(registry);

  StorageClassification file(String path) =>
      categorizer.classify(path, StorageEntryKind.file);

  void expectNever(Map<String, StorageCategory> paths) {
    paths.forEach((path, category) {
      for (final kind in [StorageEntryKind.file, StorageEntryKind.directory]) {
        final value = categorizer.classify(path, kind);
        expect(
          value.deletionClass,
          StorageDeletionClass.never,
          reason: '$path ($kind) → $value',
        );
        expect(value.protectedReason, isNotNull, reason: path);
        expect(value.category, category, reason: '$path → $value');
      }
      expect(registry.isProtected(path), isTrue, reason: path);
    });
  }

  test('A — games, ROM, ISO and installed games are never deletable', () {
    expectNever({
      doc('roms/snes/Super Mario World.sfc'): StorageCategory.games,
      doc('roms/psx/Final Fantasy VII/Final Fantasy VII (Disc 1).bin'):
          StorageCategory.games,
      doc('MyGames/gba/Pokemon.gba'): StorageCategory.games,
      '$externalLibrary/n64/Mario.z64': StorageCategory.games,
      '$linked/roms/Game.zip': StorageCategory.games,
      doc('ARMSX2/Games/Game.iso'): StorageCategory.games,
      doc('Ports/KartPad/Games/RMCP01.wbfs'): StorageCategory.games,
      doc('Ports/Dusklight/Games/GZ2E01.rvz'): StorageCategory.games,
      data('dev_hdd0/game/BLES00113/PS3_GAME/USRDIR/EBOOT.BIN'):
          StorageCategory.games,
      data('games/ExtractedGames/BLES00113/PS3_GAME/PARAM.SFO'):
          StorageCategory.games,
      data('games/discImgs/BLES00114/game.iso'): StorageCategory.games,
      data('dev_bdvd/PS3_GAME/PARAM.SFO'): StorageCategory.games,
      data('dev_usb000/package.pkg'): StorageCategory.games,
      dolphin('Library/gc/Metroid Prime.rvz'): StorageCategory.games,
      dolphin('Library/wii/Zelda.wbfs'): StorageCategory.games,
    });
  });

  test('B — saves, states, NAND and memory cards are never deletable', () {
    expectNever({
      doc('Libretro/Saves/Snes9x/Super Mario World.srm'): StorageCategory.saves,
      doc(
        'Libretro/Saves/Azahar/Azahar/nand/00000000000000000000000000000000/x',
      ): StorageCategory.saves,
      doc('Libretro/States/Snes9x/Super Mario World.state1'):
          StorageCategory.saves,
      doc('ARMSX2/Saves/Memory Cards/Mcd001.ps2'): StorageCategory.saves,
      doc('ARMSX2/Saves/Savestates/SLUS-20946 (0F0C4A9C).01.p2s'):
          StorageCategory.saves,
      doc('Ports/KartPad/Saves/NAND/title/00010004/x'): StorageCategory.saves,
      doc('Ports/Dusklight/Saves/save.bin'): StorageCategory.saves,
      data('dev_hdd0/home/00000001/savedata/BLES00113-SAVE01/PARAM.SFO'):
          StorageCategory.saves,
      data('dev_hdd0/home/00000001/trophy/NPWR00001/TROPUSR.DAT'):
          StorageCategory.saves,
      data('savestates/BLES00113.SAVESTAT'): StorageCategory.saves,
      dolphin('User/GC/USA/Card A/01-GALE-SuperSmashBros0110290334.gci'):
          StorageCategory.saves,
      dolphin('User/StateSaves/GALE01.s01'): StorageCategory.saves,
      dolphin('Saves/save.bin'): StorageCategory.saves,
      sup('KartPad/NAND/x'): StorageCategory.saves,
    });
  });

  test(
    'C — BIOS, firmware, licences, system files and pairing are never deletable',
    () {
      expectNever({
        doc('Libretro/System/scph5501.bin'): StorageCategory.systemFiles,
        doc('ARMSX2/BIOS/scph39001.bin'): StorageCategory.systemFiles,
        doc('Dolphin/Wii/keys.bin'): StorageCategory.systemFiles,
        doc('Dolphin/GameCube/USA/IPL.bin'): StorageCategory.systemFiles,
        data('dev_flash/sys/external/libsysutil.sprx'):
            StorageCategory.systemFiles,
        data('dev_flash2/x'): StorageCategory.systemFiles,
        data('dev_flash3/x'): StorageCategory.systemFiles,
        data(
          'dev_hdd0/home/00000001/exdata/EP0001-BLES00000_00-0123456789ABCDEF.rap',
        ): StorageCategory.systemFiles,
        dolphin('User/Wii/shared2/sys/SYSCONF'): StorageCategory.systemFiles,
        dolphin('Metadata/IPL/USA/IPL.bin'): StorageCategory.systemFiles,
        sup('StikJIT/pairing.mobiledevicepairing'): StorageCategory.systemFiles,
        sup('StikJIT/pairing.import.tmp'): StorageCategory.systemFiles,
        sup('StikJIT/pairing.backup.tmp'): StorageCategory.systemFiles,
        sup('StikJIT/DDI/Image.dmg'): StorageCategory.systemFiles,
      });
    },
  );

  test('H — user content other than games is never deletable', () {
    expectNever({
      doc('Library/Books/Dune.epub'): StorageCategory.userContent,
      doc('Library/Downloads/One Piece 1001.cbz'): StorageCategory.userContent,
      doc('Libretro/Config/Azahar.json'): StorageCategory.userContent,
      doc('Libretro/Config/Frontend/snes.json'): StorageCategory.userContent,
      doc('Libretro/Cheats/Snes9x/Game.cht'): StorageCategory.userContent,
      doc('Libretro/Skins/delta-snes/info.json'): StorageCategory.userContent,
      doc('Libretro/SkinFavorites.json'): StorageCategory.userContent,
      doc('user-data/themes/epic/theme.xml'): StorageCategory.userContent,
      doc('user-data/background.png'): StorageCategory.userContent,
      doc('user-data/menu_music/track.mp3'): StorageCategory.userContent,
      doc('Ports/KartPad/Config/Config.toml'): StorageCategory.userContent,
      doc('Ports/KartPad/Mods/texture_replacements/x.png'):
          StorageCategory.userContent,
      doc('Ports/KartPad/Metadata/x.json'): StorageCategory.userContent,
      doc('Ports/Dusklight/Mods/x'): StorageCategory.userContent,
      doc('ARMSX2/cheats/SLUS-20946.pnach'): StorageCategory.userContent,
      doc('RPCS3/Import/Game Saves/saves.zip'): StorageCategory.userContent,
      doc('RPCS3/Export/Savestates/x'): StorageCategory.userContent,
      doc('RPCS3/README.txt'): StorageCategory.userContent,
      dolphin('User/Config/Dolphin.ini'): StorageCategory.userContent,
      dolphin('User/Load/Textures/GALE01/x.png'): StorageCategory.userContent,
      dolphin('User/GameSettings/GALE01.ini'): StorageCategory.userContent,
      dolphin('User/Dump/x'): StorageCategory.userContent,
    });
  });

  test('I — NeoSwap storage is never deletable', () {
    expectNever({
      cac('NeoSwap-v1/donation.bin'): StorageCategory.neoSwap,
      cac('NeoSwapShaderStorage-v1/shader.bin'): StorageCategory.neoSwap,
      cac('NeoSwap-v2/future.bin'): StorageCategory.neoSwap,
    });
  });

  test('index, database and configuration files are never deletable', () {
    expectNever({
      doc('user-data/config.json'): StorageCategory.indexFiles,
      doc('user-data/data.sqlite'): StorageCategory.indexFiles,
      doc('user-data/data.sqlite-wal'): StorageCategory.indexFiles,
      doc('user-data/data.sqlite-shm'): StorageCategory.indexFiles,
      sup('Library/local-index.json'): StorageCategory.indexFiles,
      sup('Library/local-index.json.corrupt-1760000000000'):
          StorageCategory.indexFiles,
      sup('Library/catalogs.json'): StorageCategory.indexFiles,
      sup('Library/source-health.json'): StorageCategory.indexFiles,
      sup('Library/reading-state.json'): StorageCategory.indexFiles,
      data('games.yml'): StorageCategory.indexFiles,
      data('vfs.yml'): StorageCategory.indexFiles,
      doc('Libretro/Skins/x/cache.sqlite'): StorageCategory.indexFiles,
    });
    expectNever({
      doc('user-data/app.log'): StorageCategory.logs,
      dolphin('CrashMarkers/active-session.json'): StorageCategory.logs,
    });
  });

  // The sidecar of the Library reading store (Build 447,
  // `LibraryReadingStore.extraFileName`): its atomic-write `.tmp` and kept
  // `.corrupt` copies follow the main file's pattern. It used to match no
  // rule (protected, but counted as unknown data).
  test(
    'the reading store sidecar is classified exactly like reading-state.json',
    () {
      expect(LibraryReadingStore.extraFileName, 'reading-state-extra.json');
      expect(LibraryReadingStore.fileName, 'reading-state.json');
      for (final suffix in [
        '',
        '.tmp',
        LibraryReadingStore.corruptSuffix,
        '${LibraryReadingStore.corruptSuffix}-1760000000000',
      ]) {
        final main = sup('Library/${LibraryReadingStore.fileName}$suffix');
        final extra = sup(
          'Library/${LibraryReadingStore.extraFileName}$suffix',
        );
        expectNever({main: StorageCategory.indexFiles});
        expectNever({extra: StorageCategory.indexFiles});
        for (final kind in [
          StorageEntryKind.file,
          StorageEntryKind.directory,
        ]) {
          final expected = categorizer.classify(main, kind);
          final value = categorizer.classify(extra, kind);
          expect(value.ruleId, expected.ruleId, reason: extra);
          expect(
            value.protectedReason,
            expected.protectedReason,
            reason: extra,
          );
          expect(value.rootId, 'INV-23', reason: extra);
          expect(value.engine, StorageEngine.library, reason: extra);
        }
        expect(
          categorizer.classify(extra, StorageEntryKind.file).ruleId,
          suffix.isEmpty ? 'NEVER.readingState' : 'INV-23.index',
          reason: extra,
        );
      }
      // Only these names: another file beside them stays unknown data.
      expect(
        file(sup('Library/reading-state-other.json')).category,
        StorageCategory.unknown,
      );
    },
  );

  test('the hidden library folder is never deletable and aggregate-only', () {
    for (final path in [
      doc('Library/Sources'),
      doc('Library/Sources/neostation-source-mangadex.json'),
      doc('Library/Sources/sub/x.part'),
    ]) {
      final value = file(path);
      expect(value.deletionClass, StorageDeletionClass.never, reason: path);
      expect(value.aggregateOnly, isTrue, reason: path);
      expect(value.ruleId!.toLowerCase(), isNot(contains('source')));
      expect(value.rootId, 'INV-15');
    }
    expect(file(doc('Library/Books/x.epub')).aggregateOnly, isFalse);
  });

  test(
    'containers, roots, links, placeholders, unreadable and unknown paths are never',
    () {
      for (final path in [
        containers.documents,
        containers.applicationSupport,
        containers.caches,
        containers.temporary,
      ]) {
        expect(
          file(path).protectedReason,
          StorageProtectedReason.container,
          reason: path,
        );
      }
      for (final location in registry.locations) {
        final value = categorizer.classify(
          location.path,
          StorageEntryKind.directory,
        );
        expect(
          value.deletionClass,
          StorageDeletionClass.never,
          reason: location.path,
        );
      }
      expect(
        file(doc('Libretro')).protectedReason,
        StorageProtectedReason.root,
      );
      final link = categorizer.classify(
        tmp('picked.zip'),
        StorageEntryKind.link,
      );
      expect(link.deletionClass, StorageDeletionClass.never);
      expect(link.protectedReason, StorageProtectedReason.link);
      final placeholder = categorizer.classify(
        doc('roms/snes/.Game.sfc.icloud'),
        StorageEntryKind.icloudPlaceholder,
      );
      expect(
        placeholder.protectedReason,
        StorageProtectedReason.icloudPlaceholder,
      );
      expect(placeholder.category, StorageCategory.games);
      // Even classified as a plain file, the name protects it.
      expect(
        file(tmp('.picked.zip.icloud')).protectedReason,
        StorageProtectedReason.icloudPlaceholder,
      );
      expect(
        categorizer
            .classify(tmp('x'), StorageEntryKind.inaccessible)
            .protectedReason,
        StorageProtectedReason.inaccessible,
      );
      for (final path in [
        doc('whatever.bin'),
        doc('Ports/readme.txt'),
        doc('Libretro/Unknown/x'),
        doc('user-data/unknown.bin'),
        sup('NeoStation/Unknown/x'),
        sup('NeoStation/RPCS3/config.yml'),
        cac('com.apple.something/x'),
        '/some/other/place',
      ]) {
        final value = file(path);
        expect(value.category, StorageCategory.unknown, reason: path);
        expect(value.deletionClass, StorageDeletionClass.never, reason: path);
        expect(
          value.protectedReason,
          StorageProtectedReason.unknown,
          reason: path,
        );
        expect(value.ruleId, isNull);
      }
    },
  );

  test(
    'temporary, regenerable and confirmation classes come from the deepest rule',
    () {
      final expected =
          <String, (StorageDeletionClass, StorageCategory, String)>{
            tmp('Game.zip'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-28.temporary',
            ),
            tmp('com.neogamelab.neostation-Inbox/Game.zip'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-28.pickerInbox',
            ),
            doc('user-data/temp/snes/Game.zip/Game.sfc'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-03.archiveTemp',
            ),
            doc('user-data/background.importing.png'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-04.backgroundImporting',
            ),
            doc('Libretro/Skins/.staging/abc/x.png'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-14.skinStaging',
            ),
            doc('Library/Books/.import-0a1b2c.part'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-15.importPart',
            ),
            doc(
              'RPCS3/Export/Game Saves/.RPCS3-saves-20261012-101010.zip.part',
            ): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-10.exportPart',
            ),
            doc('RPCS3/Export/Game Saves/RPCS3-saves-20261012-101010.zip'): (
              StorageDeletionClass.confirmation,
              StorageCategory.userContent,
              'INV-10.exportZip',
            ),
            data('dev_hdd0/tmp/x'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-16.hddTmp',
            ),
            data(
              'dev_hdd0/home/00000001/.neostation-save-import-1760000000/x',
            ): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-16.saveImportStaging',
            ),
            data('dev_hdd1/caches/x'): (
              StorageDeletionClass.confirmation,
              StorageCategory.caches,
              'INV-17.hdd1',
            ),
            sup('NeoStation/RPCS3/Cache/ppu-v9-neostation-x.obj'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-18.cache',
            ),
            sup('NeoStation/RPCS3/Imports/PS3UPDAT-1760000000000000.PUP'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-19.firmwareImport',
            ),
            dolphin('ShaderCache/x.cache'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-21.shaderCache',
            ),
            doc('Ports/KartPad/Runtime/GameData/files/x'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-12.gameData',
            ),
            doc('media/snes/box2d/Super Mario World.png'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.media,
              'INV-05.media',
            ),
            sup('Library/covers/abc.png'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-23.covers',
            ),
            cac('Libretro/SkinCache/x.png'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-25.skinCache',
            ),
            cac('Libretro/skin-catalog.json'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-25.catalogs',
            ),
            cac('Libretro/Content/abc/Game.sfc'): (
              StorageDeletionClass.temporaryWhenIdle,
              StorageCategory.temporary,
              'INV-25.content',
            ),
            cac('Library/library_http/x'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-26.http',
            ),
            sup('Roboto-Regular_e4f5a6b7c8d9e0f1a2b3c4d5e6f7a8b9.ttf'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.caches,
              'INV-29.fonts',
            ),
            doc('Diagnostics/rpcs3_startup_debug.txt'): (
              StorageDeletionClass.confirmation,
              StorageCategory.logs,
              'INV-06.diagnostics',
            ),
            doc('NeoPlay.jsonl'): (
              StorageDeletionClass.confirmation,
              StorageCategory.logs,
              'INV-07.neoPlayLog',
            ),
            doc('Recordings/Dolphin/2026-10-12.mp4'): (
              StorageDeletionClass.confirmation,
              StorageCategory.userContent,
              'INV-08.recording',
            ),
            doc('Libretro/Logs/session.log'): (
              StorageDeletionClass.confirmation,
              StorageCategory.logs,
              'INV-14.logs',
            ),
            doc('user-data/app.log.old'): (
              StorageDeletionClass.confirmation,
              StorageCategory.logs,
              'INV-02.appLogOld',
            ),
            dolphin('Logs/dolphin-2026-10-12T10-00-00.000Z.jsonl'): (
              StorageDeletionClass.regenerableAtCost,
              StorageCategory.logs,
              'INV-22.sessionLog',
            ),
            dolphin('Logs/dolphin-persistent.jsonl'): (
              StorageDeletionClass.confirmation,
              StorageCategory.logs,
              'INV-22.persistentLog',
            ),
          };
      expected.forEach((path, value) {
        final classification = file(path);
        expect(
          classification.deletionClass,
          value.$1,
          reason: '$path → $classification',
        );
        expect(classification.category, value.$2, reason: path);
        expect(classification.ruleId, value.$3, reason: path);
        expect(classification.protectedReason, isNull, reason: path);
      });
      // Contract replaced by the review of the storage services: the RPCS3
      // save and licence backups and the copies of data.sqlite used to need
      // a detailed confirmation (level 3). Backups of user data, they are
      // never proposed now, by their own rule (same category and rule id).
      for (final (path, rule) in [
        (
          sup('NeoStation/RPCS3/SaveBackups/BLES00113-SAVE-1/x'),
          'INV-19.saveBackups',
        ),
        (sup('NeoStation/RPCS3/RapBackups/x.rap'), 'INV-19.rapBackups'),
        (
          sup('NeoStation/Maintenance/data-20261012-101010.sqlite'),
          'INV-02.maintenanceBackup',
        ),
      ]) {
        final classification = file(path);
        expect(
          classification.deletionClass,
          StorageDeletionClass.never,
          reason: '$path → $classification',
        );
        expect(classification.category, StorageCategory.userContent);
        expect(classification.ruleId, rule, reason: path);
        expect(
          classification.protectedReason,
          StorageProtectedReason.rule,
          reason: path,
        );
      }
      expect(file(tmp('Game.zip')).minimumAge, const Duration(minutes: 10));
      expect(
        file(sup('NeoStation/RPCS3/Imports/PS3UPDAT-1.PUP')).minimumAge,
        const Duration(hours: 1),
      );
    },
  );

  test('*.part is temporary after the rule, except where never-lists, saves, '
      'system files, NeoSwap, index, games or user content rule', () {
    // Contract replaced by the review of the storage services: a `.part`
    // in a games folder (`ARMSX2/Games`, `Dolphin/Library`) used to become
    // a temporary of level 1, preselected. A partial file there — a
    // download, a copy the user started — is the user's: games and user
    // content now keep their rule's class, as saves, system files, NeoSwap
    // and index files already did. The override still applies under the
    // other rules (media, caches, logs).
    expect(
      StorageCategorizer.partOverrideExcluded,
      containsAll([StorageCategory.games, StorageCategory.userContent]),
    );
    for (final (path, rule, engine) in [
      (
        doc('media/snes/box2d/Game.png.part'),
        'INV-05.media',
        StorageEngine.frontend,
      ),
      (
        sup('NeoStation/RPCS3/Cache/ppu-x.obj.part'),
        'INV-18.cache',
        StorageEngine.rpcs3,
      ),
      (doc('Diagnostics/trace.txt.part'), 'INV-06.diagnostics', null),
      (
        cac('Libretro/SkinCache/x.png.part'),
        'INV-25.skinCache',
        StorageEngine.libretro,
      ),
    ]) {
      final value = file(path);
      expect(
        value.deletionClass,
        StorageDeletionClass.temporaryWhenIdle,
        reason: path,
      );
      expect(value.category, StorageCategory.temporary, reason: path);
      expect(value.ruleId, StorageCategorizer.partOverrideRuleId);
      expect(value.minimumAge, StorageCategorizer.partMinimumAge);
      expect(value.rule?.id, rule, reason: path);
      if (engine != null) expect(value.engine, engine, reason: path);
    }
    // The games and user content folders, with this test's registry and
    // with the production inputs (`Documents/roms` and the ARMSX2 linked
    // folders that StorageRootRegistry.resolve() adds).
    final production = StorageCategorizer(
      StorageRootRegistry(
        containers,
        libraryRoots: [doc('roms'), doc('ARMSX2'), doc('ARMSX2/Games')],
      ),
    );
    for (final (path, category) in [
      (doc('ARMSX2/Games/Game.iso.part'), StorageCategory.games),
      (dolphin('Library/gc/Game.rvz.part'), StorageCategory.games),
      (
        doc('Libretro/Skins/delta-snes/assets.part'),
        StorageCategory.userContent,
      ),
      (
        dolphin('User/Load/Textures/GALE01/tex1_64x64_x.png.part'),
        StorageCategory.userContent,
      ),
      (
        doc('Library/Downloads/One Piece 1002.cbz.part'),
        StorageCategory.userContent,
      ),
      (doc('Library/Books/Dune.epub.part'), StorageCategory.userContent),
      (doc('Ports/KartPad/Mods/track.szs.part'), StorageCategory.userContent),
      (doc('user-data/themes/epic/bg.png.part'), StorageCategory.userContent),
      (
        doc('Libretro/Cheats/Snes9x/Game.cht.part'),
        StorageCategory.userContent,
      ),
      (
        doc('RPCS3/Import/Game Saves/save.zip.part'),
        StorageCategory.userContent,
      ),
    ]) {
      for (final value in [
        file(path),
        production.classify(path, StorageEntryKind.file),
      ]) {
        expect(value.deletionClass, StorageDeletionClass.never, reason: path);
        expect(value.category, category, reason: path);
        expect(
          value.ruleId,
          isNot(StorageCategorizer.partOverrideRuleId),
          reason: path,
        );
      }
    }
    // NeoStation's own partial files there keep their explicit rules.
    expect(
      file(doc('Ports/KartPad/Games/RMCP01.wbfs.part')).ruleId,
      'INV-12.gamePart',
    );
    for (final kept in [
      doc('roms/snes/Game.sfc.part'),
      doc('MyGames/Game.iso.part'),
      doc('Libretro/Saves/Snes9x/Game.srm.part'),
      doc('Libretro/System/bios.bin.part'),
      sup('StikJIT/pairing.part'),
      data('dev_hdd0/game/BLES00113/x.part'),
      doc('unknown.part'),
      cac('NeoSwap-v1/x.part'),
    ]) {
      expect(
        file(kept).deletionClass,
        StorageDeletionClass.never,
        reason: kept,
      );
    }
  });

  test('classifyChild gives exactly the decision of classify', () {
    final paths = [
      doc('roms/snes/Game.sfc'),
      doc('Libretro/Skins/.staging/a'),
      tmp('Game.zip'),
      doc('Library/Sources/x'),
      sup('NeoStation/Maintenance/data-20261012-101010.sqlite'),
      cac('Libretro/Content/x'),
      doc('ARMSX2/Games/Game.iso.part'),
    ];
    for (final path in paths) {
      final parent = registry.contextFor(p.dirname(path));
      for (final kind in StorageEntryKind.values) {
        final direct = categorizer.classify(path, kind);
        final child = categorizer.classifyChild(parent, p.basename(path), kind);
        expect(child.ruleId, direct.ruleId, reason: '$path $kind');
        expect(
          child.deletionClass,
          direct.deletionClass,
          reason: '$path $kind',
        );
        expect(child.category, direct.category, reason: '$path $kind');
        expect(child.rootId, direct.rootId, reason: '$path $kind');
      }
    }
  });
}
