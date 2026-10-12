import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/services/storage/storage_orphan_detector.dart';
import 'package:neostation/services/storage/storage_roots.dart';
import 'package:neostation/services/storage/storage_scanner.dart';
import 'package:neostation/services/storage/storage_stat_ffi.dart';
import 'package:path/path.dart' as p;

import 'database_test_helper.dart';

/// Test A of docs/storage-audit-cleanup.md § 6: media matched by the four
/// name variants of `deleteNeoStationScrapedMedia` (playlists included),
/// unknown systems unattributed, metadata by the LEFT JOIN, covers absent
/// from `local-index.json`, saves and states listed only, duplicates by
/// name and size with the referenced copy never selectable; nothing is
/// ever deleted.

/// Minimal PARAM.SFO (PSF 1.1) with UTF-8 string values.
Uint8List _sfo(Map<String, String> values) {
  final keys = BytesBuilder();
  final data = BytesBuilder();
  final index = <List<int>>[];
  for (final item in values.entries) {
    final keyOffset = keys.length;
    keys
      ..add(utf8.encode(item.key))
      ..addByte(0);
    final value = [...utf8.encode(item.value), 0];
    final dataOffset = data.length;
    data.add(value);
    while (data.length % 4 != 0) {
      data.addByte(0);
    }
    index.add([keyOffset, value.length, data.length - dataOffset, dataOffset]);
  }
  final keyTable = 20 + index.length * 16;
  final keyBytes = keys.takeBytes();
  final dataTable = (keyTable + keyBytes.length + 3) & ~3;
  final dataBytes = data.takeBytes();
  final out = Uint8List(dataTable + dataBytes.length);
  final view = ByteData.sublistView(out)
    ..setUint32(0, 0x46535000, Endian.little)
    ..setUint32(4, 0x00000101, Endian.little)
    ..setUint32(8, keyTable, Endian.little)
    ..setUint32(12, dataTable, Endian.little)
    ..setUint32(16, index.length, Endian.little);
  for (var i = 0; i < index.length; i++) {
    final at = 20 + i * 16;
    view
      ..setUint16(at, index[i][0], Endian.little)
      ..setUint16(at + 2, 0x0204, Endian.little)
      ..setUint32(at + 4, index[i][1], Endian.little)
      ..setUint32(at + 8, index[i][2], Endian.little)
      ..setUint32(at + 12, index[i][3], Endian.little);
  }
  out
    ..setAll(keyTable, keyBytes)
    ..setAll(dataTable, dataBytes);
  return out;
}

/// Plain ISO 9660 image whose root holds `SYSTEM.CNF;1` = [systemCnf].
Uint8List _iso(String systemCnf) {
  const sector = 2048;
  final image = Uint8List(sector * 20);
  final view = ByteData.sublistView(image);
  int record(
    int at,
    int lba,
    int length,
    List<int> name, {
    bool directory = false,
  }) {
    final size = 33 + name.length + (name.length.isEven ? 1 : 0);
    image[at] = size;
    view
      ..setUint32(at + 2, lba, Endian.little)
      ..setUint32(at + 6, lba, Endian.big)
      ..setUint32(at + 10, length, Endian.little)
      ..setUint32(at + 14, length, Endian.big);
    image[at + 25] = directory ? 2 : 0;
    image[at + 32] = name.length;
    image.setAll(at + 33, name);
    return size;
  }

  const pvd = 16 * sector;
  image[pvd] = 1;
  image.setAll(pvd + 1, ascii.encode('CD001'));
  image[pvd + 6] = 1;
  record(pvd + 156, 18, sector, [0], directory: true);
  var at = 18 * sector;
  at += record(at, 18, sector, [0], directory: true);
  at += record(at, 18, sector, [1], directory: true);
  final cnf = ascii.encode(systemCnf);
  record(at, 19, cnf.length, ascii.encode('SYSTEM.CNF;1'));
  image.setAll(19 * sector, cnf);
  return image;
}

void main() {
  final helper = DatabaseTestHelper();
  late DatabaseAdapter db;
  late Directory home;
  late StorageContainers containers;

  String doc(String relative) => p.join(containers.documents, relative);
  String sup(String relative) =>
      p.join(containers.applicationSupport, relative);
  String data(String relative) =>
      sup(p.join('NeoStation/RPCS3/Data', relative));

  Future<File> write(String path, [Object content = 'x']) async {
    final file = File(path);
    await file.parent.create(recursive: true);
    if (content is List<int>) {
      await file.writeAsBytes(content);
    } else if (content is int) {
      await file.writeAsBytes(List<int>.filled(content, 3));
    } else {
      await file.writeAsString('$content');
    }
    return file;
  }

  Future<void> rom(
    String system,
    String filename,
    String romPath, {
    String? titleId,
  }) => db.execute(
    'INSERT INTO user_roms (app_system_id, filename, rom_path, title_id) VALUES (?, ?, ?, ?)',
    [system, filename, romPath, titleId],
  );

  Future<void> metadata(String system, String filename) => db.execute(
    'INSERT INTO user_screenscraper_metadata (app_system_id, filename) VALUES (?, ?)',
    [system, filename],
  );

  setUp(() async {
    StorageStatFfi.resetSession();
    db = await helper.setUp();
    home = await Directory.systemTemp.createTemp('storage_orphans_');
    containers = StorageContainers(
      documents: p.join(home.path, 'Documents'),
      applicationSupport: p.join(home.path, 'Library', 'Application Support'),
      caches: p.join(home.path, 'Library', 'Caches'),
      temporary: p.join(home.path, 'tmp'),
    );
    for (final container in StorageContainer.values) {
      await Directory(containers.pathOf(container)).create(recursive: true);
    }
    for (final system in ['snes', 'psx', 'ps2', 'ps3', 'switch', 'gc']) {
      await db.execute(
        'INSERT INTO app_systems (id, real_name, folder_name) VALUES (?, ?, ?)',
        [system, system.toUpperCase(), system],
      );
    }
    for (final (system, extension) in [
      ('snes', 'sfc'),
      ('snes', 'smc'),
      ('psx', 'cue'),
      ('psx', 'bin'),
      ('psx', 'm3u'),
      ('ps2', 'iso'),
      ('gc', 'rvz'),
    ]) {
      await db.execute(
        'INSERT INTO app_system_extensions (system_id, extension) VALUES (?, ?)',
        [system, extension],
      );
    }
  });

  tearDown(() async {
    StorageStatFfi.resetSession();
    await helper.tearDown();
    if (await home.exists()) await home.delete(recursive: true);
  });

  Future<(StorageScanResult, StorageRootRegistry)> scan({
    List<String> libraryRoots = const [],
    bool redirected = false,
  }) async {
    final registry = StorageRootRegistry(
      containers,
      libraryRoots: libraryRoots,
      rpcs3Redirected: redirected,
    );
    return (await StorageScanner().scan(registry), registry);
  }

  Future<StorageOrphanReport> detect({
    List<String> libraryRoots = const [],
    bool redirected = false,
    bool hash = false,
    StorageScanCancelToken? cancel,
  }) async {
    final (result, registry) = await scan(
      libraryRoots: libraryRoots,
      redirected: redirected,
    );
    return StorageOrphanDetector(
      database: () async => db,
      registry: registry,
    ).detect(result, hashDuplicates: hash, cancel: cancel);
  }

  Set<String> relative(Iterable<StorageOrphanEntry> entries) => {
    for (final entry in entries) entry.relativePath,
  };

  test(
    'media: the four name variants, playlists, Title IDs, unknown systems',
    () async {
      await rom(
        'snes',
        'Super Mario World.sfc',
        doc('roms/snes/Super Mario World.sfc'),
      );
      await rom('snes', 'Game.v1.sfc', doc('roms/snes/Game.v1.sfc'));
      await rom('snes', 'Tetris.v2', doc('roms/snes/Tetris.v2'));
      await rom(
        'psx',
        'Final Fantasy VII (USA).m3u',
        doc('roms/psx/Final Fantasy VII (USA).m3u'),
      );
      await rom(
        'switch',
        'Zelda.melonx',
        'melonx://game?title-id=01006a800016e000',
        titleId: '01006a800016e000',
      );
      await rom(
        'ps3',
        'BLES00113.rpcs3',
        'rpcs3-library://game?title-id=BLES00113',
        titleId: 'BLES00113',
      );
      final kept = [
        'media/snes/box2d/Super Mario World.png', // _stripExtension(filename)
        'media/snes/screenshots/Super Mario World.sfc.png', // filename
        'media/snes/manuals/Super Mario World.pdf',
        'media/snes/wheels/Game.png', // _stripExtension(romBaseName)
        'media/snes/fanarts/Game.v1.jpg', // romBaseName
        'media/snes/videos/Game.v1.sfc.mp4', // filename
        'media/snes/box2d/Tetris.v2.png', // romBaseName kept whole (version)
        'media/snes/box2d/Tetris.webp',
        'media/psx/box2d/Final Fantasy VII (USA).png', // playlist base
        'media/psx/screenshots/Final Fantasy VII (USA).m3u.jpeg',
        'media/switch/box2d/01006a800016e000.png', // Title ID of a virtual row
        'media/ps3/screenshots/BLES00113.png',
      ];
      final orphans = [
        'media/snes/fanarts/Deleted Game.jpg',
        'media/snes/videos/Deleted Game.mp4',
        'media/snes/box2d/Super Mario World (Hack).png',
        'media/psx/box2d/Final Fantasy VII (USA) (Disc 1).png', // disc without a row
      ];
      // Contract replaced by the review of the storage services: the media of
      // a known system without any game row used to be orphan (preselected
      // at level 2). Its rows may have been pruned by a scan of a library
      // folder iOS could not read: they are not analysed now — neither
      // orphan nor unattributed — and the report says so.
      final notAnalysed = ['media/gc/box2d/Metroid Prime.png'];
      final ignored = [
        'media/snes/box2d/notes.txt',
        'media/snes/box2d/.DS_Store',
        'media/snes/covers/Deleted Game.png', // not a NeoStation media type
        'media/snes/box2d/sub/Deleted Game.png',
      ];
      for (final path in [...kept, ...orphans, ...notAnalysed, ...ignored]) {
        await write(doc(path), 10);
      }
      await write(doc('media/unknownsys/box2d/Game.png'), 10);

      final report = await detect();
      expect(relative(report.media), orphans.toSet());
      expect(report.skipped['systemsWithoutGames'], 'media: gc');
      expect(report.skipped.containsKey('media'), isFalse);
      for (final entry in report.media) {
        expect(entry.kind, StorageOrphanKind.media);
        expect(entry.selectable, isTrue);
        expect(entry.deletionClass, StorageDeletionClass.regenerableAtCost);
        expect(entry.rootId, 'INV-05');
        expect(entry.logicalBytes, 10);
      }
      expect(
        report.media.firstWhere((entry) => entry.key == 'Deleted Game').group,
        'snes',
      );
      expect(relative(report.unattributedMedia), {
        'media/unknownsys/box2d/Game.png',
      });
      expect(
        relative([...report.media, ...report.unattributedMedia]),
        isNot(contains(notAnalysed.single)),
      );
      expect(report.unattributedMedia.single.selectable, isFalse);
      expect(
        report.unattributedMedia.single.kind,
        StorageOrphanKind.unattributedMedia,
      );
    },
  );

  test(
    'media and metadata are not claimed orphan while user_roms is empty',
    () async {
      await write(doc('media/snes/box2d/Super Mario World.png'), 10);
      await metadata('snes', 'Super Mario World.sfc');
      final report = await detect();
      expect(report.media, isEmpty);
      expect(report.metadata, isEmpty);
      expect(report.skipped['media'], 'user_roms is empty');
      expect(report.skipped['metadata'], 'user_roms is empty');
    },
  );

  test(
    'metadata: LEFT JOIN on system and file name, exact keys in order',
    () async {
      await rom(
        'snes',
        'Super Mario World.sfc',
        doc('roms/snes/Super Mario World.sfc'),
      );
      await rom('psx', 'Final Fantasy VII (USA).m3u', doc('roms/psx/FF7.m3u'));
      await metadata('snes', 'Super Mario World.sfc');
      await metadata('snes', 'Deleted Game.sfc');
      await metadata('psx', 'Final Fantasy VII (USA).m3u');
      await metadata('psx', 'Final Fantasy VII (USA) (Disc 1).cue');
      // Same file name under another system: orphan there.
      await metadata('psx', 'Super Mario World.sfc');
      final report = await detect();
      expect(report.metadata, const [
        StorageOrphanMetadataKey('psx', 'Final Fantasy VII (USA) (Disc 1).cue'),
        StorageOrphanMetadataKey('psx', 'Super Mario World.sfc'),
        StorageOrphanMetadataKey('snes', 'Deleted Game.sfc'),
      ]);
      expect(
        (await db.rawQuery(
          'SELECT COUNT(*) AS n FROM user_screenscraper_metadata',
        )).single['n'],
        5,
      );
    },
  );

  test(
    'covers: absent from local-index.json, never claimed without a readable index',
    () async {
      await rom('snes', 'a.sfc', doc('roms/a.sfc'));
      for (final name in [
        'b1.png',
        'b2.png',
        'b3.png',
        '.hidden.png',
        'notes.txt',
      ]) {
        await write(sup('Library/covers/$name'), 5);
      }
      final index = File(sup('Library/local-index.json'));
      final noIndex = await detect();
      expect(noIndex.libraryCovers, isEmpty);
      expect(noIndex.skipped['libraryCovers'], 'local-index.json missing');

      await index.writeAsString('{not json');
      final corrupt = await detect();
      expect(corrupt.libraryCovers, isEmpty);
      expect(
        corrupt.skipped['libraryCovers'],
        startsWith('local-index.json unreadable'),
      );

      await index.writeAsString(jsonEncode({'version': 1, 'books': 'nope'}));
      expect((await detect()).libraryCovers, isEmpty);

      await index.writeAsString(
        jsonEncode({
          'version': 1,
          'books': [
            {'id': 'b1', 'relativePath': 'Books/One.epub'},
            {'id': 'b2', 'relativePath': 'Books/Two.epub'},
          ],
          'ignored': [],
        }),
      );
      final report = await detect();
      expect(relative(report.libraryCovers), {'Library/covers/b3.png'});
      final cover = report.libraryCovers.single;
      expect(cover.kind, StorageOrphanKind.libraryCover);
      expect(cover.key, 'b3');
      expect(cover.selectable, isTrue);
      expect(cover.container, StorageContainer.applicationSupport);
      expect(report.skipped.containsKey('libraryCovers'), isFalse);
    },
  );

  test('saves and states are listed, never selectable', () async {
    await rom(
      'snes',
      'Super Mario World.sfc',
      doc('roms/snes/Super Mario World.sfc'),
    );
    await rom(
      'snes',
      'Dr. Mario (v1.1).sfc',
      doc('roms/snes/Dr. Mario (v1.1).sfc'),
    );
    await write(doc('Libretro/Saves/Snes9x/Super Mario World.srm'), 8);
    await write(doc('Libretro/Saves/Snes9x/Super Mario World.rtc'), 8);
    await write(doc('Libretro/Saves/Snes9x/Dr. Mario (v1.1).srm'), 8);
    await write(doc('Libretro/Saves/Snes9x/Deleted Game.srm'), 8);
    await write(doc('Libretro/Saves/Azahar/Azahar/nand/data.bin'), 8);
    await write(doc('Libretro/States/Snes9x/Super Mario World.state'), 8);
    await write(doc('Libretro/States/Snes9x/Super Mario World.state3'), 8);
    await write(doc('Libretro/States/Snes9x/Deleted Game.state1'), 8);
    await write(sup('NeoStation/Dolphin/User/StateSaves/GALE01.s01'), 8);
    await write(sup('NeoStation/Dolphin/User/StateSaves/RMCP01.s02'), 8);

    final report = await detect();
    expect(relative(report.libretroSaves), {
      'Libretro/Saves/Snes9x/Deleted Game.srm',
    });
    expect(report.libretroSaves.single.group, 'Snes9x');
    expect(relative(report.libretroStates), {
      'Libretro/States/Snes9x/Deleted Game.state1',
    });
    expect(relative(report.dolphinStates), {
      'NeoStation/Dolphin/User/StateSaves/GALE01.s01',
      'NeoStation/Dolphin/User/StateSaves/RMCP01.s02',
    });
    for (final entry in report.savesAndStates) {
      expect(entry.selectable, isFalse, reason: entry.relativePath);
      expect(
        entry.deletionClass,
        StorageDeletionClass.never,
        reason: entry.relativePath,
      );
    }
  });

  test(
    'RPCS3 savedata: listed when no installed game owns its title',
    () async {
      await rom('snes', 'a.sfc', doc('roms/a.sfc'));
      await rom(
        'ps3',
        'BCES00001.rpcs3',
        'rpcs3-library://game?title-id=BCES00001',
        titleId: 'BCES00001',
      );
      await write(
        data('dev_hdd0/game/BLES00113/PARAM.SFO'),
        _sfo({'TITLE_ID': 'BLES00113'}),
      );
      await write(
        data('games/ExtractedGames/My Game/PS3_GAME/PARAM.SFO'),
        _sfo({'TITLE_ID': 'BLUS30443', 'CATEGORY': 'DG'}),
      );
      await write(data('games/discImgs/NPEB01234.iso'), 10);
      final saves = {
        'BLES00113-SAVE01': true, // dev_hdd0/game
        'BLUS30443-AUTO': true, // PARAM.SFO of an extracted game
        'NPEB01234-SLOT': true, // disc image name
        'BCES00001-DATA': true, // virtual library row
        'NPUB30000-AUTO': false, // no game: orphan
      };
      for (final name in saves.keys) {
        await write(
          data('dev_hdd0/home/00000001/savedata/$name/PARAM.SFO'),
          _sfo({'SAVEDATA_DIRECTORY': name, 'TITLE': 'Save'}),
        );
      }
      // No readable PARAM.SFO and no title in the name: never claimed.
      await write(data('dev_hdd0/home/00000001/savedata/weird/data.bin'), 4);

      final report = await detect();
      expect(report.rpcs3Savedata.map((entry) => entry.group), [
        'NPUB30000-AUTO',
      ]);
      final orphan = report.rpcs3Savedata.single;
      expect(orphan.key, 'NPUB30000');
      expect(orphan.entryKind, StorageEntryKind.directory);
      expect(orphan.selectable, isFalse);

      final redirected = await detect(redirected: true);
      expect(redirected.rpcs3Savedata, isEmpty);
      expect(redirected.skipped['rpcs3Savedata'], contains('vfs.yml'));
    },
  );

  test(
    'ARMSX2 savestates: by serial, only when every game serial is known',
    () async {
      await rom('snes', 'a.sfc', doc('roms/a.sfc'));
      await write(
        doc('ARMSX2/Games/Shadow of the Colossus [SCUS-97472].iso'),
        10,
      );
      await write(
        doc('ARMSX2/Games/Ico.iso'),
        _iso('BOOT2 = cdrom0:\\SCUS_971.13;1\r\nVER = 1.00\r\n'),
      );
      await write(
        doc('ARMSX2/Saves/Savestates/SCUS-97472 (11111111).01.p2s'),
        6,
      );
      await write(
        doc('ARMSX2/Saves/Savestates/SCUS-97113 (22222222).00.p2s'),
        6,
      );
      await write(
        doc('ARMSX2/Saves/Savestates/SLES-50003 (33333333).01.p2s'),
        6,
      );
      expect(
        await StorageOrphanDetector.serialFromIso(doc('ARMSX2/Games/Ico.iso')),
        'SCUS97113',
      );
      expect(
        StorageOrphanDetector.serialInName('SLUS-209.46 Game.iso'),
        'SLUS20946',
      );
      expect(StorageOrphanDetector.serialInName('Game (Europe).iso'), isNull);

      final report = await detect();
      expect(report.armsx2Savestates.map((entry) => entry.key), ['SLES50003']);
      expect(report.armsx2Savestates.single.selectable, isFalse);

      // A game whose serial cannot be read could own any state.
      await write(doc('ARMSX2/Games/Unknown.chd'), 10);
      final incomplete = await detect();
      expect(incomplete.armsx2Savestates, isEmpty);
      expect(
        incomplete.skipped['armsx2Savestates'],
        'serial unknown for 1 game(s)',
      );
    },
  );

  test(
    'duplicates: name and size, the referenced copy is never selectable',
    () async {
      final mine = doc('MyGames');
      await write(doc('roms/snes/Super Mario World.sfc'), 100);
      await write(p.join(mine, 'snes/Super Mario World.sfc'), 100);
      // Stored with another case: rom_path is COLLATE NOCASE.
      await rom(
        'snes',
        'Super Mario World.sfc',
        doc('roms/snes/SUPER MARIO WORLD.sfc'),
      );
      // Neither copy referenced: none offered.
      await write(sup('NeoStation/Dolphin/Library/gc/Metroid Prime.rvz'), 200);
      await write(doc('roms/gc/Metroid Prime.rvz'), 200);
      await write(doc('Ports/KartPad/Games/Mario Kart Wii.wbfs'), 300);
      await write(doc('roms/wii/Mario Kart Wii.wbfs'), 300);
      // A copy beside a descriptor may be one of its tracks.
      await write(doc('roms/psx/FF7/FF7 (Disc 1).bin'), 400);
      await write(doc('roms/psx/FF7/FF7 (Disc 1).cue'), 40);
      await write(doc('roms/psx/FF7 (Disc 1).bin'), 400);
      await write(p.join(mine, 'psx/Multi/Game.m3u'), 20);
      await write(p.join(mine, 'psx/Multi/discs/Game (Disc 2).bin'), 500);
      await write(doc('roms/psx/Game (Disc 2).bin'), 500);
      await rom('psx', 'FF7 (Disc 1).bin', doc('roms/psx/FF7 (Disc 1).bin'));
      await rom('psx', 'Game (Disc 2).bin', doc('roms/psx/Game (Disc 2).bin'));
      // Not duplicates: other size, partial copy, hidden, empty.
      await write(doc('roms/snes/Zelda.sfc'), 64);
      await write(p.join(mine, 'snes/Zelda.sfc'), 65);
      await write(doc('roms/snes/x.iso.part'), 5);
      await write(p.join(mine, 'x.iso.part'), 5);
      await write(doc('roms/snes/.hidden'), 5);
      await write(p.join(mine, '.hidden'), 5);
      await write(doc('roms/snes/empty.sfc'), 0);
      await write(p.join(mine, 'empty.sfc'), 0);
      final before = await home
          .list(recursive: true)
          .map((entity) => entity.path)
          .toSet();

      final report = await detect(libraryRoots: [mine]);
      final groups = {for (final group in report.duplicates) group.name: group};
      expect(groups.keys.toSet(), {
        'Super Mario World.sfc',
        'Metroid Prime.rvz',
        'Mario Kart Wii.wbfs',
        'FF7 (Disc 1).bin',
        'Game (Disc 2).bin',
      });
      StorageDuplicateCopy copy(String name, String path) => groups[name]!
          .copies
          .firstWhere((candidate) => candidate.path == path);

      final mario = groups['Super Mario World.sfc']!;
      expect(mario.size, 100);
      expect(mario.hashed, isFalse);
      expect(
        copy(
          'Super Mario World.sfc',
          doc('roms/snes/Super Mario World.sfc'),
        ).referenced,
        isTrue,
      );
      expect(
        copy(
          'Super Mario World.sfc',
          doc('roms/snes/Super Mario World.sfc'),
        ).selectable,
        isFalse,
      );
      expect(
        copy(
          'Super Mario World.sfc',
          doc('roms/snes/Super Mario World.sfc'),
        ).keep,
        StorageDuplicateKeep.referenced,
      );
      // Contract replaced by the review of the storage services: without
      // checksums the unreferenced copy used to be selectable. The same name
      // and size do not make the same game (USA and EUR images, two
      // GameCube discs of the standard size): it is listed, never offered,
      // until « Calculer les empreintes » shows it equal to the referenced
      // copy (end of this test).
      final unhashed = copy(
        'Super Mario World.sfc',
        p.join(mine, 'snes/Super Mario World.sfc'),
      );
      expect(unhashed.selectable, isFalse);
      expect(unhashed.keep, StorageDuplicateKeep.notHashed);
      expect(unhashed.sha256, isNull);
      expect(mario.selectableBytes, 0);
      expect(
        report.duplicates
            .expand((group) => group.copies)
            .where((candidate) => candidate.selectable),
        isEmpty,
      );

      for (final name in ['Metroid Prime.rvz', 'Mario Kart Wii.wbfs']) {
        for (final candidate in groups[name]!.copies) {
          expect(candidate.selectable, isFalse, reason: candidate.path);
          expect(candidate.keep, StorageDuplicateKeep.noReferencedCopy);
        }
      }
      expect(
        groups['Metroid Prime.rvz']!.copies
            .map((candidate) => candidate.rootId)
            .toSet(),
        {'INV-01', 'INV-20'},
      );
      final track = copy(
        'FF7 (Disc 1).bin',
        doc('roms/psx/FF7/FF7 (Disc 1).bin'),
      );
      expect(track.selectable, isFalse);
      expect(track.keep, StorageDuplicateKeep.companionFiles);
      final disc = copy(
        'Game (Disc 2).bin',
        p.join(mine, 'psx/Multi/discs/Game (Disc 2).bin'),
      );
      expect(disc.selectable, isFalse);
      expect(disc.keep, StorageDuplicateKeep.companionFiles);
      // With the checksums, the identical unreferenced copy is offered.
      final hashed = await detect(libraryRoots: [mine], hash: true);
      final hashedMario = hashed.duplicates.singleWhere(
        (group) => group.name == 'Super Mario World.sfc',
      );
      expect(hashedMario.hashed, isTrue);
      final offered = hashedMario.copies.singleWhere(
        (candidate) =>
            candidate.path == p.join(mine, 'snes/Super Mario World.sfc'),
      );
      expect(offered.selectable, isTrue);
      expect(offered.keep, isNull);
      expect(offered.sha256, hashedMario.sha256);
      expect(hashedMario.selectableBytes, 100);
      // Nothing was deleted or written.
      expect(
        await home.list(recursive: true).map((entity) => entity.path).toSet(),
        before,
      );
    },
  );

  test(
    'duplicates: SHA-256 on request splits copies of different content',
    () async {
      final mine = doc('MyGames');
      final same = List<int>.generate(64, (index) => index);
      await write(doc('roms/snes/Same.sfc'), same);
      await write(p.join(mine, 'Same.sfc'), same);
      await write(doc('roms/snes/Other.sfc'), List<int>.filled(64, 1));
      await write(p.join(mine, 'Other.sfc'), List<int>.filled(64, 2));
      await rom('snes', 'Same.sfc', doc('roms/snes/Same.sfc'));
      await rom('snes', 'Other.sfc', doc('roms/snes/Other.sfc'));

      final plain = await detect(libraryRoots: [mine]);
      expect(plain.duplicates.map((group) => group.name).toSet(), {
        'Same.sfc',
        'Other.sfc',
      });
      expect(plain.duplicates.every((group) => !group.hashed), isTrue);
      // Without checksums nothing is offered, whatever the content (review
      // of the storage services): `Other.sfc` holds other bytes than the
      // referenced copy, `Same.sfc` the same ones — neither is selectable.
      for (final group in plain.duplicates) {
        for (final candidate in group.copies) {
          expect(candidate.selectable, isFalse, reason: candidate.path);
          expect(
            candidate.keep,
            candidate.referenced
                ? StorageDuplicateKeep.referenced
                : StorageDuplicateKeep.notHashed,
            reason: candidate.path,
          );
        }
        expect(group.selectableBytes, 0);
      }

      final hashed = await detect(libraryRoots: [mine], hash: true);
      // The copies of different content are no group at all: nothing of
      // `Other.sfc` can be offered.
      expect(hashed.duplicates.map((group) => group.name), ['Same.sfc']);
      expect(
        hashed.duplicates
            .expand((group) => group.copies)
            .where((candidate) => p.basename(candidate.path) == 'Other.sfc'),
        isEmpty,
      );
      final group = hashed.duplicates.single;
      expect(group.hashed, isTrue);
      expect(group.sha256, sha256.convert(same).toString());
      expect(
        group.copies.every((candidate) => candidate.sha256 == group.sha256),
        isTrue,
      );
      expect(
        group.copies
            .where((candidate) => candidate.selectable)
            .map((candidate) => candidate.path),
        [p.join(mine, 'Same.sfc')],
      );
      expect(
        await StorageOrphanDetector.sha256OfFile(doc('missing.bin')),
        isNull,
      );
    },
  );

  test('a cancelled detection reports nothing and deletes nothing', () async {
    await rom('snes', 'a.sfc', doc('roms/a.sfc'));
    await write(doc('media/snes/box2d/Deleted.png'), 4);
    final cancel = StorageScanCancelToken()..cancel();
    final report = await detect(cancel: cancel);
    expect(report.cancelled, isTrue);
    expect(report.media, isEmpty);
    expect(await File(doc('media/snes/box2d/Deleted.png')).exists(), isTrue);
  });

  test('an unreachable database skips what needs it, never guesses', () async {
    await write(doc('media/snes/box2d/Deleted.png'), 4);
    await write(doc('roms/snes/Same.sfc'), 9);
    await write(doc('MyGames/Same.sfc'), 9);
    final (result, registry) = await scan(libraryRoots: [doc('MyGames')]);
    final report = await StorageOrphanDetector(
      database: () async => throw StateError('database closed'),
      registry: registry,
    ).detect(result);
    expect(report.skipped['database'], contains('database closed'));
    expect(report.media, isEmpty);
    expect(report.metadata, isEmpty);
    expect(
      report.duplicates.single.copies.every(
        (candidate) => !candidate.selectable,
      ),
      isTrue,
    );
  });

  // Review of the storage services (12 October 2026): a scan of the library
  // prunes the rows of a folder iOS could not read; the system then has no
  // row left while its media and metadata are still the user's.
  test('a known system without any game row: its media and metadata are not '
      'analysed, the other systems are', () async {
    await rom('snes', 'Zelda.sfc', doc('roms/snes/Zelda.sfc'));
    await metadata('snes', 'Zelda.sfc');
    await metadata('snes', 'Deleted.sfc');
    await metadata('psx', 'Final Fantasy VII.cue');
    await metadata('psx', 'Final Fantasy VIII.cue');
    final psxMedia = [
      'media/psx/box2d/Final Fantasy VII.png',
      'media/psx/screenshots/Final Fantasy VII.png',
      'media/psx/videos/Final Fantasy VII.mp4',
      'media/psx/manuals/Final Fantasy VII.pdf',
      'media/psx/box2d/Custom cover set by the user.png',
    ];
    for (final path in [
      ...psxMedia,
      'media/snes/box2d/Zelda.png',
      'media/snes/box2d/Deleted.png',
    ]) {
      await write(doc(path), 10);
    }
    final report = await detect();
    expect(relative(report.media), {'media/snes/box2d/Deleted.png'});
    expect(report.unattributedMedia, isEmpty);
    expect(report.metadata, const [
      StorageOrphanMetadataKey('snes', 'Deleted.sfc'),
    ]);
    expect(report.skipped['systemsWithoutGames'], 'media: psx; metadata: psx');
    // Only read.
    for (final path in psxMedia) {
      expect(await File(doc(path)).exists(), isTrue, reason: path);
    }
    expect(
      (await db.rawQuery(
        'SELECT COUNT(*) AS n FROM user_screenscraper_metadata',
      )).single['n'],
      4,
    );
    // Its first game row makes it analysed again.
    await rom('psx', 'Final Fantasy VII.cue', doc('roms/psx/FF7.cue'));
    final analysed = await detect();
    expect(relative(analysed.media), {
      'media/snes/box2d/Deleted.png',
      'media/psx/box2d/Custom cover set by the user.png',
    });
    expect(analysed.metadata, const [
      StorageOrphanMetadataKey('psx', 'Final Fantasy VIII.cue'),
      StorageOrphanMetadataKey('snes', 'Deleted.sfc'),
    ]);
    expect(analysed.skipped.containsKey('systemsWithoutGames'), isFalse);
  });

  test('a registered library folder missing or unreadable: no media, metadata '
      'or cover is claimed orphan', () async {
    await rom('snes', 'Zelda.sfc', doc('roms/snes/Zelda.sfc'));
    await write(doc('roms/snes/Zelda.sfc'), 10);
    await write(doc('media/snes/box2d/Deleted.png'), 10);
    await metadata('snes', 'Deleted.sfc');
    await write(sup('Library/covers/b3.png'), 5);
    await File(
      sup('Library/local-index.json'),
    ).writeAsString(jsonEncode({'version': 1, 'books': <Object>[]}));
    final outside = await Directory.systemTemp.createTemp('orphans_out_');
    addTearDown(() async {
      if (await outside.exists()) await outside.delete(recursive: true);
    });
    final aFile = await write(doc('NotAFolder'), 3);

    Future<StorageOrphanReport> detectWith({
      List<String> libraryRoots = const [],
      String? linked,
      StorageDirectoryLister? lister,
    }) async {
      final registry = StorageRootRegistry(
        containers,
        libraryRoots: libraryRoots,
        linkedExternalFolder: linked,
      );
      final result = await StorageScanner(lister: lister).scan(registry);
      return StorageOrphanDetector(
        database: () async => db,
        registry: registry,
      ).detect(result);
    }

    // Control: every folder readable.
    final readable = await detectWith(
      libraryRoots: [doc('roms'), outside.path],
      linked: outside.path,
    );
    expect(relative(readable.media), {'media/snes/box2d/Deleted.png'});
    expect(readable.metadata, isNotEmpty);
    expect(relative(readable.libraryCovers), {'Library/covers/b3.png'});

    Stream<FileSystemEntity> refusing(Directory directory) =>
        p.basename(directory.path) == 'MyGames'
        ? Stream<FileSystemEntity>.error(
            FileSystemException(
              'Directory listing failed',
              directory.path,
              const OSError('Operation not permitted', 1),
            ),
          )
        : directory.list(followLinks: false);
    await Directory(doc('MyGames')).create();
    for (final (label, report) in [
      (
        'missing in the container',
        await detectWith(libraryRoots: [doc('Gone')]),
      ),
      (
        'missing outside the containers',
        await detectWith(libraryRoots: [p.join(outside.path, 'gone')]),
      ),
      (
        'linked folder missing',
        await detectWith(linked: p.join(outside.path, 'linked')),
      ),
      ('not a folder', await detectWith(libraryRoots: [aFile.path])),
      (
        'unreadable in the analysis',
        await detectWith(libraryRoots: [doc('MyGames')], lister: refusing),
      ),
    ]) {
      expect(report.media, isEmpty, reason: label);
      expect(report.metadata, isEmpty, reason: label);
      expect(report.libraryCovers, isEmpty, reason: label);
      for (final key in ['media', 'metadata', 'libraryCovers']) {
        expect(
          report.skipped[key],
          startsWith('library folder missing or unreadable: '),
          reason: '$label: $key',
        );
      }
    }
    final unreadable = await detectWith(
      libraryRoots: [doc('MyGames')],
      lister: refusing,
    );
    expect(
      unreadable.skipped['media'],
      contains('<Documents>/MyGames: inaccessible in the analysis'),
    );
    expect(
      (await detectWith(libraryRoots: [doc('Gone')])).skipped['media'],
      contains('<Documents>/Gone: missing'),
    );
    // A folder outside the containers is never spelled out.
    final external = (await detectWith(
      libraryRoots: [p.join(outside.path, 'gone')],
    )).skipped['media'];
    expect(external, contains('<library folder>: missing'));
    expect(external, isNot(contains(outside.path)));
    // Nothing was touched.
    expect(await File(doc('media/snes/box2d/Deleted.png')).exists(), isTrue);
    expect(await File(sup('Library/covers/b3.png')).exists(), isTrue);
  });

  test('recheck confirms only what is still orphan on a fresh read', () async {
    await rom('snes', 'Zelda.sfc', doc('roms/snes/Zelda.sfc'));
    await rom('psx', 'Final Fantasy VII.cue', doc('roms/psx/FF7.cue'));
    await metadata('snes', 'Deleted.sfc');
    await metadata('snes', 'Later.sfc');
    final deleted = doc('media/snes/box2d/Deleted.png');
    final later = doc('media/snes/box2d/Later.png');
    for (final path in [deleted, later]) {
      await write(path, 10);
    }
    await write(sup('Library/covers/b3.png'), 5);
    await write(sup('Library/covers/b4.png'), 5);
    final index = File(sup('Library/local-index.json'));
    await index.writeAsString(jsonEncode({'version': 1, 'books': <Object>[]}));
    final (result, registry) = await scan();
    final detector = StorageOrphanDetector(
      database: () async => db,
      registry: registry,
    );
    final report = await detector.detect(result);
    expect(relative(report.media), {
      'media/snes/box2d/Deleted.png',
      'media/snes/box2d/Later.png',
    });
    const keys = [
      StorageOrphanMetadataKey('snes', 'Deleted.sfc'),
      StorageOrphanMetadataKey('snes', 'Later.sfc'),
    ];
    expect(report.metadata, keys);

    // A scan added Later.sfc, an import added book b4, since the preview.
    await rom('snes', 'Later.sfc', doc('roms/snes/Later.sfc'));
    await index.writeAsString(
      jsonEncode({
        'version': 1,
        'books': [
          {'id': 'b4', 'relativePath': 'Books/Four.epub'},
        ],
      }),
    );
    final now = await detector.recheck(
      media: [deleted, later, doc('roms/snes/Zelda.sfc')],
      covers: [sup('Library/covers/b3.png'), sup('Library/covers/b4.png')],
      metadata: keys,
    );
    expect(now.refused, isNull);
    expect(now.media, {storageCanonicalPath(deleted)});
    expect(now.covers, {storageCanonicalPath(sup('Library/covers/b3.png'))});
    expect(now.metadata, {keys.first});

    // A system that lost all its rows is not analysed any more.
    await db.execute("DELETE FROM user_roms WHERE app_system_id = 'snes'");
    final pruned = await detector.recheck(media: [deleted], metadata: keys);
    expect(pruned.refused, isNull);
    expect(pruned.media, isEmpty);
    expect(pruned.metadata, isEmpty);

    // An unreadable index confirms no cover.
    await index.writeAsString('{not json');
    expect(
      (await detector.recheck(covers: [sup('Library/covers/b3.png')])).covers,
      isEmpty,
    );

    // An empty library, a missing library folder or the database itself
    // refuse everything.
    await db.execute('DELETE FROM user_roms');
    final empty = await detector.recheck(media: [deleted], metadata: keys);
    expect(empty.refused, 'user_roms is empty');
    expect(empty.media, isEmpty);
    expect(empty.metadata, isEmpty);
    await rom('snes', 'Zelda.sfc', doc('roms/snes/Zelda.sfc'));
    final missingFolder = await StorageOrphanDetector(
      database: () async => db,
      registry: StorageRootRegistry(containers, libraryRoots: [doc('Gone')]),
    ).recheck(media: [deleted], metadata: keys);
    expect(
      missingFolder.refused,
      startsWith('library folder missing or unreadable: '),
    );
    expect(missingFolder.media, isEmpty);
    expect(missingFolder.metadata, isEmpty);
    final closed = await StorageOrphanDetector(
      database: () async => throw StateError('database closed'),
      registry: registry,
    ).recheck(media: [deleted], metadata: keys);
    expect(closed.refused, startsWith('database: '));
    expect(closed.media, isEmpty);
    expect(await File(deleted).exists(), isTrue);
  });
}
