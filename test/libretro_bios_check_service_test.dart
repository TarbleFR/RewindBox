import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart' show Archive, ArchiveFile, ZipEncoder, getCrc32;
import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/libretro_bios_catalog.dart';
import 'package:neostation/services/libretro_bios_check_service.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:path/path.dart' as p;

/// Synthetic bytes standing in for a BIOS: the checker only sees sizes and
/// checksums, and the test injects the matching reference table. No BIOS
/// byte is ever used.
Uint8List synthetic(int length, int seed) =>
    Uint8List.fromList(List<int>.generate(length, (index) => (index * 31 + seed * 17 + (index >> 8)) & 0xff));

String hex(int value) => value.toRadixString(16).padLeft(8, '0');

Map<String, Object?> dumpOf(List<int> bytes, String label) => <String, Object?>{
      'size': bytes.length,
      'crc': hex(getCrc32(bytes)),
      'md5': crypto.md5.convert(bytes).toString(),
      'sha1': crypto.sha1.convert(bytes).toString(),
      'label': label,
      'source': 'test',
    };

List<int> zipOf(Map<String, List<int>> members) {
  final archive = Archive();
  for (final member in members.entries) {
    archive.add(ArchiveFile.bytes(member.key, member.value));
  }
  return ZipEncoder().encodeBytes(archive);
}

/// The real requirement data, with its reference checksums replaced by
/// those of synthetic files, and temporary NeoStation folders.
class Fixture {
  late Directory root;
  late Directory documents;
  late Directory system;
  late Directory config;
  late Directory saves;
  late Directory caches;
  late Directory library;
  late Map<String, dynamic> json;
  final hashed = <String>[];
  Set<String>? availableCores;
  List<LibretroBiosGame> games = <LibretroBiosGame>[];
  Map<String, String> bundled = <String, String>{};
  bool libraryFails = false;

  Future<void> create() async {
    root = await Directory.systemTemp.createTemp('libretro_bios_check_');
    documents = Directory(p.join(root.path, 'Documents'));
    system = Directory(p.join(documents.path, 'Libretro', 'System'))..createSync(recursive: true);
    config = Directory(p.join(documents.path, 'Libretro', 'Config'))..createSync(recursive: true);
    saves = Directory(p.join(documents.path, 'Libretro', 'Saves'))..createSync(recursive: true);
    caches = Directory(p.join(root.path, 'Library', 'Caches'))..createSync(recursive: true);
    library = Directory(p.join(root.path, 'ROMs'))..createSync(recursive: true);
    json = (jsonDecode(File('assets/data/libretro_bios_requirements.json').readAsStringSync()) as Map)
        .cast<String, dynamic>();
  }

  void dispose() => root.deleteSync(recursive: true);

  Map<String, dynamic> entry(String id) =>
      (json['entries'] as List).cast<Map<String, dynamic>>().firstWhere((entry) => entry['id'] == id);

  /// Replaces the reference checksums of [id] by those of [contents].
  void references(String id, List<List<int>> contents) {
    entry(id)['knownDumps'] = <Map<String, Object?>>[
      for (final (index, bytes) in contents.indexed) dumpOf(bytes, '$id dump $index'),
    ];
  }

  String get cacheFile => p.join(caches.path, 'Libretro', LibretroBiosCheckService.cacheFileName);

  LibretroBiosCheckService service() => LibretroBiosCheckService(
        catalog: () async => LibretroBiosCatalog.parse(jsonEncode(json)),
        environment: () async => LibretroBiosEnvironment(
          systemDirectory: system.path,
          configDirectory: config.path,
          cacheFile: cacheFile,
          documentsDirectory: documents.path,
          availableCores: availableCores,
          bundledSha256: bundled,
        ),
        library: (systems) async {
          if (libraryFails) throw StateError('database closed');
          return games.where((game) => systems.contains(game.system)).toList();
        },
        hasher: (requests) async {
          hashed.addAll(requests.map((request) => p.basename(request.path)));
          return LibretroBiosCheckService.hashFilesSync(requests);
        },
      );

  Future<LibretroBiosReport> check() => service().check(libraryRoots: <String>[library.path]);

  File put(String relative, List<int> bytes, {Directory? under}) {
    final file = File(p.joinAll(<String>[(under ?? system).path, ...relative.split('/')]));
    file.parent.createSync(recursive: true);
    file.writeAsBytesSync(bytes);
    return file;
  }

  LibretroBiosGame game(String system, String relative) {
    final file = put(relative, synthetic(64, 99), under: library);
    return LibretroBiosGame(system: system, path: file.path, name: p.basename(file.path));
  }
}

LibretroBiosEntryResult result(LibretroBiosReport report, String id) =>
    report.consoles.expand((console) => console.entries).firstWhere((entry) => entry.entry.id == id);

LibretroBiosConsoleResult console(LibretroBiosReport report, String id) =>
    report.consoles.firstWhere((console) => console.id == id);

Iterable<String> keys(LibretroBiosEntryResult result) => result.notes.map((note) => note.key);

void main() {
  late Fixture fixture;

  setUp(() async {
    fixture = Fixture();
    await fixture.create();
  });

  tearDown(() => fixture.dispose());

  group('statuses', () {
    test('a known dump is verified, an unknown checksum is not, a short or empty file is unusable', () async {
      final good = synthetic(256, 1);
      fixture.references('gb-boot', <List<int>>[good]);

      fixture.put('gb_bios.bin', good);
      var gb = result(await fixture.check(), 'gb-boot');
      expect(gb.status, LibretroBiosStatus.verified);
      expect(gb.matchedDump?.md5, crypto.md5.convert(good).toString());
      expect(gb.found?.displayPath, 'NeoStation/Libretro/System/gb_bios.bin');
      expect(gb.need, LibretroBiosNeed.optional);
      expect(gb.neededNow, isFalse);

      fixture.put('gb_bios.bin', synthetic(256, 2));
      gb = result(await fixture.check(), 'gb-boot');
      expect(gb.status, LibretroBiosStatus.presentUnverified);
      expect(keys(gb), contains('biosHashUnknown'));

      fixture.put('gb_bios.bin', synthetic(100, 2));
      gb = result(await fixture.check(), 'gb-boot');
      expect(gb.status, LibretroBiosStatus.invalid);
      expect(gb.notes, contains(const LibretroBiosNote('biosInvalidSize', <String, String>{'expected': '256', 'actual': '100'})));

      fixture.put('gb_bios.bin', const <int>[]);
      gb = result(await fixture.check(), 'gb-boot');
      expect(gb.status, LibretroBiosStatus.invalid);
      expect(keys(gb), contains('biosInvalidEmpty'));
    });

    test('a file of another entry is present but not verified, and named', () async {
      final europe = synthetic(1024, 3);
      final usa = synthetic(1024, 4);
      fixture.references('mcd-eu', <List<int>>[europe]);
      fixture.references('mcd-na', <List<int>>[usa]);
      fixture.put('bios_CD_U.bin', europe);
      final us = result(await fixture.check(), 'mcd-na');
      expect(us.status, LibretroBiosStatus.presentUnverified);
      expect(us.notes, contains(const LibretroBiosNote('biosIdentifiedAs', <String, String>{'name': 'bios_CD_E.bin'})));
    });

    test('a missing optional file is never required', () async {
      final report = await fixture.check();
      final gb = result(report, 'gb-boot');
      expect(gb.status, LibretroBiosStatus.missingOptional);
      expect(gb.found, isNull);
      expect(console(report, 'gb').ready, isTrue);
      expect(console(report, 'gba').ready, isTrue);
      expect(console(report, '32x').entries, isEmpty);
      expect(console(report, '32x').notes, contains(const LibretroBiosNote('biosNoBiosNeeded')));
      expect(console(report, '32x').ready, isTrue);
    });
  });

  group('conditional files follow the library', () {
    test('the FDS BIOS is required only when the library has disk games', () async {
      var fds = result(await fixture.check(), 'nes-fds');
      expect(fds.status, LibretroBiosStatus.missingOptional);
      expect(fds.need, LibretroBiosNeed.onlyFor);
      expect(keys(fds), contains('biosConditionUnmet'));

      fixture.games = <LibretroBiosGame>[fixture.game('nes', 'nes/Zelda.nes')];
      fds = result(await fixture.check(), 'nes-fds');
      expect(fds.status, LibretroBiosStatus.missingOptional, reason: 'a cartridge needs no BIOS');

      fixture.games = <LibretroBiosGame>[fixture.game('nes', 'nes/Zelda no Densetsu.fds')];
      final report = await fixture.check();
      fds = result(report, 'nes-fds');
      expect(fds.status, LibretroBiosStatus.missingRequired);
      expect(fds.need, LibretroBiosNeed.requiredFor);
      expect(fds.notes, contains(const LibretroBiosNote('biosConditionMet', <String, String>{'count': '1'})));
      expect(console(report, 'nes').ready, isFalse);
    });

    test('Mega-CD BIOS follow the region tags of the discs', () async {
      fixture.references('mcd-eu', <List<int>>[synthetic(2048, 5)]);
      fixture.games = <LibretroBiosGame>[fixture.game('mcd', 'segacd/Sonic CD (USA).cue')];
      var report = await fixture.check();
      expect(result(report, 'mcd-na').status, LibretroBiosStatus.missingRequired);
      for (final id in <String>['mcd-eu', 'mcd-jp']) {
        expect(result(report, id).status, LibretroBiosStatus.missingOptional, reason: id);
        expect(keys(result(report, id)), contains('biosRegionNotNeeded'));
      }

      // A disc without region tag: any region could be needed while none is
      // present; one present region BIOS leaves the others optional.
      fixture.games = <LibretroBiosGame>[fixture.game('scd', 'segacd/Homebrew.cue')];
      report = await fixture.check();
      for (final id in <String>['mcd-na', 'mcd-eu', 'mcd-jp']) {
        expect(result(report, id).status, LibretroBiosStatus.missingRequired, reason: id);
      }
      fixture.put('bios_CD_E.bin', synthetic(2048, 5));
      report = await fixture.check();
      expect(result(report, 'mcd-eu').status, LibretroBiosStatus.verified);
      expect(result(report, 'mcd-na').status, LibretroBiosStatus.missingOptional);
      expect(result(report, 'mcd-jp').status, LibretroBiosStatus.missingOptional);
      expect(console(report, 'mcd').ready, isTrue);
    });

    test('a name only PicoDrive reads is reported without satisfying Genesis Plus GX', () async {
      final usa = synthetic(4096, 6);
      fixture.references('mcd-na', <List<int>>[usa]);
      fixture.games = <LibretroBiosGame>[fixture.game('mcd', 'segacd/Snatcher (USA).cue')];
      fixture.put('us_scd2_9306.zip', zipOf(<String, List<int>>{'us_scd2_9306.bin': usa}));
      final na = result(await fixture.check(), 'mcd-na');
      expect(na.status, LibretroBiosStatus.missingRequired);
      expect(na.notes, contains(const LibretroBiosNote('biosOnlyCore', <String, String>{'name': 'us_scd2_9306.zip', 'core': 'PicoDrive'})));
    });

    test('arcade board BIOS stay optional: the library cannot tell their games apart', () async {
      final pgm = result(await fixture.check(), 'arcade-pgm');
      expect(pgm.status, LibretroBiosStatus.missingOptional);
      expect(pgm.need, LibretroBiosNeed.onlyFor);
      expect(keys(pgm), contains('biosConditionUnknown'));
    });

    test('Neo Geo sets in a generic arcade folder are not called unneeded', () async {
      // mslug.zip in the arcade folder may be a Neo Geo set: the library
      // cannot tell, so the checker never says no game needs neogeo.zip.
      fixture.games = <LibretroBiosGame>[fixture.game('arc', 'arcade/mslug.zip')];
      var neogeo = result(await fixture.check(), 'arcade-neogeo');
      expect(neogeo.status, LibretroBiosStatus.missingOptional);
      expect(neogeo.need, LibretroBiosNeed.onlyFor);
      expect(keys(neogeo), contains('biosConditionUnknown'));
      expect(keys(neogeo), isNot(contains('biosConditionUnmet')));

      // CPS games are never Neo Geo sets.
      fixture.games = <LibretroBiosGame>[fixture.game('cps2', 'cps2/sfa3.zip')];
      neogeo = result(await fixture.check(), 'arcade-neogeo');
      expect(keys(neogeo), contains('biosConditionUnmet'));
      expect(keys(neogeo), isNot(contains('biosConditionUnknown')));
    });

    test('an unreadable library leaves conditional files not needed', () async {
      fixture.libraryFails = true;
      final report = await fixture.check();
      expect(report.libraryUnavailable, isTrue);
      expect(result(report, 'nes-fds').status, LibretroBiosStatus.missingOptional);
    });
  });

  group('PlayStation', () {
    final japan = synthetic(512 * 1024, 7);
    final america = synthetic(512 * 1024, 8);
    final europe = synthetic(512 * 1024, 9);

    setUp(() {
      fixture.references('psx-jp', <List<int>>[japan]);
      fixture.references('psx-na', <List<int>>[america]);
      fixture.references('psx-eu', <List<int>>[europe]);
    });

    test('without any BIOS NeoStation refuses PS1 launches and the three regions are required', () async {
      final report = await fixture.check();
      final psx = console(report, 'psx');
      expect(psx.ready, isFalse);
      expect(psx.gateNote, const LibretroBiosNote('biosGateMissing', <String, String>{'files': 'scph5500.bin, scph5501.bin, scph5502.bin'}));
      for (final id in <String>['psx-jp', 'psx-na', 'psx-eu']) {
        final row = result(report, id);
        expect(row.status, LibretroBiosStatus.missingRequired, reason: id);
        expect(keys(row), contains('biosGroupOneOf'));
      }
      // One file is enough: the console has one thing to fix, not one per
      // region row plus the launch rule.
      expect(psx.problems, 1);
    });

    test('a Beetle alias is verified but the launch rule asks for the exact name', () async {
      fixture.put('SCPH5501.BIN', america);
      final report = await fixture.check();
      final na = result(report, 'psx-na');
      expect(na.status, LibretroBiosStatus.verified);
      expect(na.found?.name, 'SCPH5501.BIN');
      expect(na.notes, contains(const LibretroBiosNote('biosRename', <String, String>{'found': 'SCPH5501.BIN', 'name': 'scph5501.bin'})));
      expect(console(report, 'psx').ready, isFalse);
      expect(console(report, 'psx').gateNote?.key, 'biosGateMissing');
      expect(console(report, 'psx').problems, 1, reason: 'the rename is the only thing to fix');
    });

    test('a file of another case is not one of the names; Beetle still finds it by checksum', () async {
      fixture.put('Scph5501.bin', synthetic(512 * 1024, 10));
      var na = result(await fixture.check(), 'psx-na');
      expect(na.status, LibretroBiosStatus.missingRequired);
      expect(na.notes, contains(const LibretroBiosNote('biosFoundElsewhere', <String, String>{
        'path': 'NeoStation/Libretro/System/Scph5501.bin',
        'expected': 'NeoStation/Libretro/System/scph5501.bin',
      })));

      fixture.put('Scph5501.bin', america);
      na = result(await fixture.check(), 'psx-na');
      expect(na.status, LibretroBiosStatus.verified);
      expect(na.found?.byChecksum, isTrue);
      expect(na.notes, contains(const LibretroBiosNote('biosFoundByChecksum', <String, String>{'name': 'Scph5501.bin'})));
      expect(na.notes, contains(const LibretroBiosNote('biosRename', <String, String>{'found': 'Scph5501.bin', 'name': 'scph5501.bin'})));
    });

    test('with one exact name the rule is met; other regions start with OpenBIOS', () async {
      fixture.put('scph5500.bin', japan);
      fixture.games = <LibretroBiosGame>[fixture.game('ps1', 'psx/Crash Bandicoot (USA).cue')];
      final report = await fixture.check();
      final psx = console(report, 'psx');
      expect(psx.gateNote, const LibretroBiosNote('biosGateOk', <String, String>{'file': 'scph5500.bin'}));
      expect(psx.ready, isTrue);
      expect(result(report, 'psx-jp').status, LibretroBiosStatus.verified);
      final na = result(report, 'psx-na');
      expect(na.status, LibretroBiosStatus.missingOptional);
      expect(na.need, LibretroBiosNeed.recommended);
      expect(keys(na), contains('biosOpenBiosFallback'));
    });

    test('without the OpenBIOS fallback a disc region with games needs its BIOS', () async {
      (fixture.json['flags'] as Map)['beetleOpenBiosFallback'] = false;
      fixture.put('scph5500.bin', japan);
      fixture.games = <LibretroBiosGame>[fixture.game('ps1', 'psx/Crash Bandicoot (USA).cue')];
      final report = await fixture.check();
      expect(result(report, 'psx-na').status, LibretroBiosStatus.missingRequired);
      expect(result(report, 'psx-eu').status, LibretroBiosStatus.missingOptional);
      expect(console(report, 'psx').ready, isFalse);
      expect(console(report, 'psx').problems, 1, reason: 'the launch rule is met; the US BIOS is missing');
    });
  });

  group('locations', () {
    test('Snes9x reads BS-X.bin next to the game before the System folder', () async {
      final bsx = synthetic(1024 * 1024, 11);
      fixture.references('snes-bsx', <List<int>>[bsx]);
      fixture.games = <LibretroBiosGame>[fixture.game('satellaview', 'satellaview/BS Zelda.bs')];
      fixture.put('BS-X.bin', synthetic(1024 * 1024, 12));
      var row = result(await fixture.check(), 'snes-bsx');
      expect(row.status, LibretroBiosStatus.presentUnverified);
      expect(row.found?.displayPath, 'NeoStation/Libretro/System/BS-X.bin');

      final local = fixture.put('satellaview/BS-X.bin', bsx, under: fixture.library);
      row = result(await fixture.check(), 'snes-bsx');
      expect(row.status, LibretroBiosStatus.verified);
      expect(row.found?.path, local.path);
      expect(row.expected.first, isNull, reason: 'the folder of the games comes first');

      // The core opens the copy next to the game and stops there.
      fixture.put('satellaview/BS-X.bin', synthetic(4096, 11), under: fixture.library);
      row = result(await fixture.check(), 'snes-bsx');
      expect(row.status, LibretroBiosStatus.invalid);
      expect(keys(row), contains('biosInvalidSize'));
    });

    test('the folder of the game is the one of the games that need the file', () async {
      final bsx = synthetic(1024 * 1024, 11);
      fixture.references('snes-bsx', <List<int>>[bsx]);
      final other = fixture.put('snes/BS-X.bin', bsx, under: fixture.library);
      // No Satellaview game yet: the copy in the library's SNES folder is shown.
      var row = result(await fixture.check(), 'snes-bsx');
      expect(row.found?.path, other.path);
      expect(row.need, LibretroBiosNeed.onlyFor);

      // The BS-X games are elsewhere: Snes9x looks next to them, then in System.
      fixture.games = <LibretroBiosGame>[fixture.game('satellaview', 'satellaview/BS Zelda.bs')];
      row = result(await fixture.check(), 'snes-bsx');
      expect(row.found, isNull);
      expect(row.status, LibretroBiosStatus.missingRequired);
      expect(row.notes.where((note) => note.key == 'biosFoundElsewhere').single.arguments['path'], other.path);
    });

    test('a file in the wrong folder is found and reported', () async {
      fixture.put('IPL.n64', <int>[0x80, 0x27, 0x07, 0x40, ...synthetic(60, 13)]);
      final ipl = result(await fixture.check(), 'n64-64dd');
      expect(ipl.status, LibretroBiosStatus.missingOptional);
      expect(ipl.notes, contains(const LibretroBiosNote('biosFoundElsewhere', <String, String>{
        'path': 'NeoStation/Libretro/System/IPL.n64',
        'expected': 'NeoStation/Libretro/System/Mupen64plus/IPL.n64',
      })));
    });

    test('folder names are compared exactly', () async {
      fixture.put('mupen64plus/IPL.n64', <int>[0x80, 0x27, 0x07, 0x40, ...synthetic(60, 13)]);
      final ipl = result(await fixture.check(), 'n64-64dd');
      expect(ipl.found, isNull);
      expect(keys(ipl), contains('biosFoundElsewhere'));
    });
  });

  group('validators', () {
    test('Genesis Plus GX ignores a boot ROM without its header', () async {
      final header = Uint8List.fromList(synthetic(2048, 14));
      fixture.put('bios_MD.bin', header);
      var tmss = result(await fixture.check(), 'md-tmss');
      expect(tmss.status, LibretroBiosStatus.invalid);
      expect(keys(tmss), contains('biosInvalidHeader'));

      header.setRange(0x120, 0x12a, ascii.encode('GENESIS OS'));
      fixture.put('bios_MD.bin', header);
      tmss = result(await fixture.check(), 'md-tmss');
      expect(tmss.status, LibretroBiosStatus.presentUnverified);
    });

    test('Snes9x needs a 256 KiB Sufami Turbo BIOS with its header', () async {
      final bios = Uint8List.fromList(synthetic(256 * 1024, 15));
      fixture.put('STBIOS.bin', bios);
      expect(result(await fixture.check(), 'snes-sufami').status, LibretroBiosStatus.invalid);

      bios.setRange(0, 14, ascii.encode('BANDAI SFC-ADX'));
      bios.setRange(16, 30, ascii.encode('SFC-ADX BACKUP'));
      fixture.put('STBIOS.bin', bios);
      expect(result(await fixture.check(), 'snes-sufami').status, LibretroBiosStatus.presentUnverified);

      fixture.put('STBIOS.bin', bios.sublist(0, 4096));
      final short = result(await fixture.check(), 'snes-sufami');
      expect(short.status, LibretroBiosStatus.invalid);
      expect(keys(short), contains('biosInvalidSize'));
    });

    test('the 64DD IPL must start with one of its byte orders', () async {
      fixture.put('Mupen64plus/IPL.n64', <int>[0x27, 0x80, 0x40, 0x07, ...synthetic(60, 16)]);
      final good = result(await fixture.check(), 'n64-64dd');
      expect(good.status, LibretroBiosStatus.presentUnverified);
      expect(keys(good), contains('biosHashVaries'));

      fixture.put('Mupen64plus/IPL.n64', <int>[0x12, 0x34, 0x56, 0x78, ...synthetic(60, 16)]);
      expect(result(await fixture.check(), 'n64-64dd').status, LibretroBiosStatus.invalid);
    });
  });

  group('FBNeo sets', () {
    final sm1 = synthetic(300, 20);
    final lo = synthetic(300, 21);
    final sp1 = synthetic(300, 22);
    final sfix = synthetic(300, 23);

    setUp(() {
      fixture.references('arcade-neogeo', <List<int>>[]);
      fixture.entry('arcade-neogeo')['validators'] = <Map<String, Object?>>[
        <String, Object?>{
          'type': 'zipMembers',
          'essential': <Map<String, String>>[
            <String, String>{'name': 'sm1.sm1', 'crc': hex(getCrc32(sm1))},
            <String, String>{'name': '000-lo.lo', 'crc': hex(getCrc32(lo))},
          ],
          'recommended': <Map<String, String>>[
            <String, String>{'name': 'sp-s3.sp1', 'crc': hex(getCrc32(sp1))},
            <String, String>{'name': 'sfix.sfix', 'crc': hex(getCrc32(sfix))},
          ],
        },
      ];
      fixture.games = <LibretroBiosGame>[fixture.game('neogeo', 'neogeo/mslug.zip')];
    });

    test('every member the core uses, found by CRC, verifies the set', () async {
      fixture.put('fbneo/neogeo.zip', zipOf(<String, List<int>>{'sm1.sm1': sm1, '000-lo.lo': lo, 'sp-s3.sp1': sp1, 'sfix.sfix': sfix}));
      final report = await fixture.check();
      final set = result(report, 'arcade-neogeo');
      expect(set.status, LibretroBiosStatus.verified);
      expect(set.need, LibretroBiosNeed.requiredFor);
      expect(keys(set), contains('biosMembersVerified'));
      expect(set.found?.displayPath, 'NeoStation/Libretro/System/fbneo/neogeo.zip');
      expect(console(report, 'arcade').ready, isTrue);
    });

    test('the copy next to the games comes before System › fbneo', () async {
      fixture.put('fbneo/neogeo.zip', zipOf(<String, List<int>>{'sm1.sm1': sm1, '000-lo.lo': lo}));
      final local = fixture.put('neogeo/neogeo.zip', zipOf(<String, List<int>>{'sp-s3.sp1': sp1, 'sfix.sfix': sfix}), under: fixture.library);
      final set = result(await fixture.check(), 'arcade-neogeo');
      expect(set.found?.path, local.path);
      expect(set.copies, hasLength(2));
      // FBNeo takes each member from any copy: together they are complete.
      expect(set.status, LibretroBiosStatus.verified);
      expect(set.notes, contains(const LibretroBiosNote('biosCopies', <String, String>{'count': '2'})));
    });

    test('a set without its essential members is unusable, unless patched', () async {
      fixture.put('fbneo/neogeo.zip', zipOf(<String, List<int>>{'sfix.sfix': sfix}));
      var set = result(await fixture.check(), 'arcade-neogeo');
      expect(set.status, LibretroBiosStatus.invalid);
      expect(set.notes, contains(const LibretroBiosNote('biosInvalidMembers', <String, String>{'files': 'sm1.sm1, 000-lo.lo'})));
      expect(console(await fixture.check(), 'arcade').ready, isFalse);

      fixture.put('fbneo/patched/neogeo.zip', zipOf(<String, List<int>>{'custom.bin': sfix}));
      set = result(await fixture.check(), 'arcade-neogeo');
      expect(set.status, LibretroBiosStatus.presentUnverified);
      expect(keys(set), contains('biosPatchedCopy'));
    });

    test('essential members present and others missing: present, not verified', () async {
      fixture.put('neogeo.zip', zipOf(<String, List<int>>{'sm1.sm1': sm1, '000-lo.lo': lo}));
      final set = result(await fixture.check(), 'arcade-neogeo');
      expect(set.status, LibretroBiosStatus.presentUnverified);
      expect(set.notes, contains(const LibretroBiosNote('biosArchiveMissingRecommended', <String, String>{'files': 'sp-s3.sp1, sfix.sfix'})));
    });

    test('a file that is not a ZIP archive is unusable', () async {
      fixture.put('fbneo/neogeo.zip', utf8.encode('not an archive'));
      final set = result(await fixture.check(), 'arcade-neogeo');
      expect(set.status, LibretroBiosStatus.invalid);
      expect(keys(set), contains('biosInvalidArchive'));
    });
  });

  group('core options', () {
    test('an option-gated file follows the stored core options', () async {
      var tmss = result(await fixture.check(), 'md-tmss');
      expect(tmss.notes, contains(const LibretroBiosNote('biosOptionOff', <String, String>{'option': 'genesis_plus_gx_bios'})));

      File(p.join(fixture.config.path, 'Genesis Plus GX.json'))
          .writeAsStringSync(jsonEncode(<String, Object?>{'values': <String, String>{'genesis_plus_gx_bios': 'enabled'}}));
      tmss = result(await fixture.check(), 'md-tmss');
      expect(tmss.notes, contains(const LibretroBiosNote('biosOptionOn', <String, String>{'option': 'genesis_plus_gx_bios'})));
    });

    test('Gambatte reads its boot ROM by default, not once the option is off', () async {
      fixture.availableCores = <String>{'gambatte'};
      var gb = result(await fixture.check(), 'gb-boot');
      expect(gb.notes, contains(const LibretroBiosNote('biosOptionOn', <String, String>{'option': 'gambatte_gb_bootloader'})));

      File(p.join(fixture.config.path, 'Gambatte.json'))
          .writeAsStringSync(jsonEncode(<String, Object?>{'values': <String, String>{'gambatte_gb_bootloader': 'disabled'}}));
      gb = result(await fixture.check(), 'gb-boot');
      expect(gb.notes, contains(const LibretroBiosNote('biosOptionOff', <String, String>{'option': 'gambatte_gb_bootloader'})));
    });

    test('mGBA reads the Super Game Boy boot ROM only with the Super Game Boy model', () async {
      fixture.availableCores = <String>{'mgba'};
      void model(String value) => File(p.join(fixture.config.path, 'mGBA.json'))
          .writeAsStringSync(jsonEncode(<String, Object?>{'values': <String, String>{'mgba_gb_model': value}}));

      model('Super Game Boy');
      var sgb = result(await fixture.check(), 'gb-sgb');
      expect(sgb.notes, contains(const LibretroBiosNote('biosOptionOn', <String, String>{'option': 'mgba_gb_model'})));

      // The Super Game Boy Color model boots with gbc_bios.bin
      // (mgba libretro.c:2094-2101).
      model('Super Game Boy Color');
      sgb = result(await fixture.check(), 'gb-sgb');
      expect(sgb.notes, contains(const LibretroBiosNote('biosOptionOff', <String, String>{'option': 'mgba_gb_model'})));
    });
  });

  group('lot 1 consoles', () {
    test('ColecoVision needs its BIOS for every game; the console is ready once it is there', () async {
      final os7 = synthetic(8192, 7);
      fixture.references('cv-os7', <List<int>>[os7]);
      var report = await fixture.check();
      expect(result(report, 'cv-os7').status, LibretroBiosStatus.missingRequired);
      expect(console(report, 'cv').ready, isFalse);
      expect(console(report, 'cv').notes, contains(const LibretroBiosNote('biosNoteColeco')));

      fixture.put('colecovision.rom', os7);
      report = await fixture.check();
      expect(result(report, 'cv-os7').status, LibretroBiosStatus.verified);
      expect(console(report, 'cv').ready, isTrue);
    });

    test('a PC Engine CD System Card is required only by discs, and follows the CD BIOS option', () async {
      var card = result(await fixture.check(), 'pcecd-syscard3');
      expect(card.status, LibretroBiosStatus.missingOptional);
      expect(keys(card), contains('biosConditionUnmet'));

      fixture.games = <LibretroBiosGame>[fixture.game('pce', 'pce/Bonk.pce')];
      card = result(await fixture.check(), 'pcecd-syscard3');
      expect(card.status, LibretroBiosStatus.missingOptional, reason: 'a HuCard needs no BIOS');

      fixture.games = <LibretroBiosGame>[fixture.game('pccd', 'pccd/Ys Book I & II.cue')];
      var report = await fixture.check();
      card = result(report, 'pcecd-syscard3');
      expect(card.status, LibretroBiosStatus.missingRequired);
      expect(console(report, 'pccd').ready, isFalse);
      expect(card.notes, contains(const LibretroBiosNote('biosOptionOn', <String, String>{'option': 'pce_fast_cdbios'})));
      // A disc kept in the HuCard folder needs it too.
      fixture.games = <LibretroBiosGame>[fixture.game('tg16', 'tg16/Lords of Thunder.chd')];
      expect(result(await fixture.check(), 'pcecd-syscard3').status, LibretroBiosStatus.missingRequired);

      File(p.join(fixture.config.path, 'Beetle PCE Fast.json'))
          .writeAsStringSync(jsonEncode(<String, Object?>{'values': <String, String>{'pce_fast_cdbios': 'System Card 2'}}));
      report = await fixture.check();
      expect(result(report, 'pcecd-syscard3').notes,
          contains(const LibretroBiosNote('biosOptionOff', <String, String>{'option': 'pce_fast_cdbios'})));
      expect(result(report, 'pcecd-syscard2').notes,
          contains(const LibretroBiosNote('biosOptionOn', <String, String>{'option': 'pce_fast_cdbios'})));
    });

    test('optional lot 1 BIOS never make a console unready', () async {
      final report = await fixture.check();
      for (final id in <String>['lynx-boot', '7800-na', '7800-eu', '5200-bios', 'mini-bios']) {
        expect(result(report, id).status, LibretroBiosStatus.missingOptional, reason: id);
      }
      for (final id in <String>['lynx', '7800', '5200', 'mini', 'pce', 'tg16', 'ws', 'ngp', 'vb', '2600', 'gw', 'uze']) {
        expect(console(report, id).ready, isTrue, reason: id);
      }
      expect(console(report, '5200').notes, contains(const LibretroBiosNote('biosNote5200')));
    });
  });

  group('lot 2 consoles', () {
    test('the Intellivision is ready only with both exec.bin and grom.bin', () async {
      final exec = synthetic(8192, 21), grom = synthetic(2048, 22);
      fixture.references('intv-exec', <List<int>>[exec]);
      fixture.references('intv-grom', <List<int>>[grom]);
      var report = await fixture.check();
      expect(result(report, 'intv-exec').status, LibretroBiosStatus.missingRequired);
      expect(result(report, 'intv-grom').status, LibretroBiosStatus.missingRequired);
      expect(console(report, 'intv').ready, isFalse);
      expect(console(report, 'intv').notes, contains(const LibretroBiosNote('biosNoteIntv')));

      fixture.put('exec.bin', exec);
      report = await fixture.check();
      expect(result(report, 'intv-exec').status, LibretroBiosStatus.verified);
      expect(console(report, 'intv').ready, isFalse, reason: 'grom.bin is still missing');

      fixture.put('grom.bin', grom);
      report = await fixture.check();
      expect(result(report, 'intv-grom').status, LibretroBiosStatus.verified);
      expect(console(report, 'intv').ready, isTrue);
    });

    test('O2EM needs the BIOS its option names; the other models follow the option', () async {
      final o2rom = synthetic(1024, 23);
      fixture.references('mo2-o2rom', <List<int>>[o2rom]);
      var report = await fixture.check();
      expect(result(report, 'mo2-o2rom').status, LibretroBiosStatus.missingRequired);
      expect(console(report, 'mo2').ready, isFalse);
      for (final id in <String>['mo2-c52', 'mo2-g7400', 'mo2-jopac']) {
        expect(result(report, id).status, LibretroBiosStatus.missingOptional, reason: id);
      }

      fixture.put('o2rom.bin', o2rom);
      report = await fixture.check();
      expect(result(report, 'mo2-o2rom').status, LibretroBiosStatus.verified);
      expect(console(report, 'mo2').ready, isTrue);

      File(p.join(fixture.config.path, 'O2EM.json'))
          .writeAsStringSync(jsonEncode(<String, Object?>{'values': <String, String>{'o2em_bios': 'c52.bin'}}));
      report = await fixture.check();
      expect(result(report, 'mo2-o2rom').notes,
          contains(const LibretroBiosNote('biosOptionOff', <String, String>{'option': 'o2em_bios'})));
      expect(result(report, 'mo2-c52').notes,
          contains(const LibretroBiosNote('biosOptionOn', <String, String>{'option': 'o2em_bios'})));
    });

    test('the PC-FX needs pcfx.rom; the Channel F BIOS stay optional', () async {
      final report = await fixture.check();
      expect(result(report, 'pcfx-bios').status, LibretroBiosStatus.missingRequired);
      expect(console(report, 'pcfx').ready, isFalse);
      for (final id in <String>['chf-psu1', 'chf-psu1-ii', 'chf-psu2']) {
        expect(result(report, id).status, LibretroBiosStatus.missingOptional, reason: id);
      }
      expect(console(report, 'chf').ready, isTrue);
      expect(console(report, 'chf').notes, contains(const LibretroBiosNote('biosNoteChannelF')));
    });
  });

  group('PPSSPP support files', () {
    test('installed at the next PSP launch, incomplete, or identical to the shipped copy', () async {
      var atlas = result(await fixture.check(), 'psp-atlas');
      expect(atlas.status, LibretroBiosStatus.missingOptional);
      expect(keys(atlas), contains('biosPpssppInstalledOnLaunch'));

      fixture.put('PPSSPP/compat.ini', utf8.encode('[Compat]'));
      var report = await fixture.check();
      atlas = result(report, 'psp-atlas');
      expect(atlas.status, LibretroBiosStatus.missingRequired);
      expect(keys(atlas), contains('biosPpssppIncomplete'));
      expect(console(report, 'psp').ready, isFalse);

      final bytes = synthetic(5000, 30);
      fixture.bundled = <String, String>{'PPSSPP/ppge_atlas.zim': crypto.sha256.convert(bytes).toString()};
      fixture.put('PPSSPP/ppge_atlas.zim', bytes);
      report = await fixture.check();
      atlas = result(report, 'psp-atlas');
      expect(atlas.status, LibretroBiosStatus.verified);
      expect(keys(atlas), contains('biosBundledMatch'));
      expect(console(report, 'psp').ready, isTrue);
    });
  });

  group('cache and side effects', () {
    test('unchanged files are not hashed again; a changed date is', () async {
      final good = synthetic(256, 1);
      fixture.references('gb-boot', <List<int>>[good]);
      final file = fixture.put('gb_bios.bin', good);
      fixture.put('bios_CD_U.bin', synthetic(1024, 40));

      var report = await fixture.check();
      expect(fixture.hashed, containsAll(<String>['gb_bios.bin', 'bios_CD_U.bin']));
      expect(report.hashedFiles, fixture.hashed.length);
      expect(File(fixture.cacheFile).existsSync(), isTrue);

      fixture.hashed.clear();
      report = await fixture.check();
      expect(fixture.hashed, isEmpty);
      expect(report.cachedFiles, report.examinedFiles);
      expect(result(report, 'gb-boot').status, LibretroBiosStatus.verified);

      file.setLastModifiedSync(DateTime.now().add(const Duration(minutes: 5)));
      report = await fixture.check();
      expect(fixture.hashed, <String>['gb_bios.bin']);

      // A damaged cache is ignored and rebuilt.
      fixture.hashed.clear();
      File(fixture.cacheFile).writeAsStringSync('{broken');
      report = await fixture.check();
      expect(fixture.hashed, containsAll(<String>['gb_bios.bin', 'bios_CD_U.bin']));
      expect(result(report, 'gb-boot').status, LibretroBiosStatus.verified);
    });

    test('a check changes nothing outside its cache', () async {
      fixture.put('gb_bios.bin', synthetic(256, 1));
      fixture.put('scph5501.bin', synthetic(512 * 1024, 8));
      fixture.put('fbneo/neogeo.zip', zipOf(<String, List<int>>{'sm1.sm1': synthetic(300, 20)}));
      fixture.put('PPSSPP/compat.ini', utf8.encode('[Compat]'));
      File(p.join(fixture.saves.path, 'Gambatte', 'Tetris.srm'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(synthetic(32, 50));
      File(p.join(fixture.config.path, 'Gambatte.json')).writeAsStringSync('{"values":{}}');
      fixture.games = <LibretroBiosGame>[fixture.game('neogeo', 'neogeo/mslug.zip')];

      Map<String, String> snapshot(Directory directory) => <String, String>{
            for (final entity in directory.listSync(recursive: true))
              p.relative(entity.path, from: directory.path):
                  '${entity.statSync().type} ${entity is File ? entity.lengthSync() : 0} ${entity.statSync().modified.millisecondsSinceEpoch}',
          };
      final documentsBefore = snapshot(fixture.documents);
      final libraryBefore = snapshot(fixture.library);

      await fixture.check();
      await fixture.check();

      expect(snapshot(fixture.documents), documentsBefore);
      expect(snapshot(fixture.library), libraryBefore);
      expect(
        fixture.caches.listSync(recursive: true).whereType<File>().map((file) => p.basename(file.path)),
        <String>[LibretroBiosCheckService.cacheFileName],
      );
    });
  });

  test('a console whose core is not in the build is shown as unavailable', () async {
    fixture.availableCores = LibretroCoreCatalog.cores.keys.where((core) => core != 'fbneo').toSet();
    final report = await fixture.check();
    final arcade = console(report, 'arcade');
    expect(arcade.available, isFalse);
    expect(arcade.entries, isEmpty);
    expect(arcade.notes, contains(const LibretroBiosNote('biosCoreUnavailable')));
    expect(report.entries.any((entry) => entry.entry.cores.every((core) => core == 'fbneo')), isFalse);
    expect(report.availableConsoles, report.consoles.length - 1);
  });

  test('the summary counts every file of the available consoles once', () async {
    final report = await fixture.check();
    final counts = report.counts;
    expect(counts.values.fold<int>(0, (sum, count) => sum + count), report.entries.length);
    expect(report.consoles.map((console) => console.id), <String>[
      'nes', 'snes', 'gb', 'gbc', 'gba', 'md', 'mcd', '32x', 'sms', 'gg', 'sg1000',
      'arcade', 'nds', 'n64', 'psx', 'psp', '3ds',
      // Lot 1.
      'pce', 'tg16', 'pccd', 'tgcd', 'ws', 'wsc', 'ngp', 'ngpc', 'lynx', 'vb', '2600', '7800', '5200', 'cv',
      'mini', 'gw', 'duck', 'wsv', 'ard', 'wasm4', 'uze',
      // Lot 2.
      'chf', 'intv', 'mo2', 'pcfx',
    ]);
  });

  test('files are hashed in a background isolate with the same results', () async {
    final file = fixture.put('abc.bin', ascii.encode('abc'));
    final request = LibretroBiosHashRequest(file.path, 3, file.lastModifiedSync().millisecondsSinceEpoch);
    final facts = (await LibretroBiosCheckService.isolateHasher(<LibretroBiosHashRequest>[request]))[file.path]!;
    expect(facts.md5, '900150983cd24fb0d6963f7d28e17f72');
    expect(facts.sha1, 'a9993e364706816aba3e25717850c26c9cd0d89d');
    expect(facts.sha256, 'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad');
    expect(facts.head, ascii.encode('abc'));
    expect(facts.zipMagic, isFalse);
    final missing = LibretroBiosCheckService.hashFileSync(LibretroBiosHashRequest(p.join(fixture.root.path, 'gone.bin'), 3, 0));
    expect(missing.unreadable, isTrue);
  });

  test('ZIP members are read from the central directory only', () {
    final bytes = Uint8List.fromList(zipOf(<String, List<int>>{'a.bin': synthetic(10, 1), 'dir/b.bin': synthetic(20, 2)}));
    final members = LibretroBiosCheckService.zipCentralDirectory(bytes)!;
    expect(members.map((member) => member.name), <String>['a.bin', 'dir/b.bin']);
    expect(members.first.crc, getCrc32(synthetic(10, 1)));
    expect(members.last.size, 20);
    expect(LibretroBiosCheckService.zipCentralDirectory(Uint8List.fromList(utf8.encode('plain text file'))), isNull);
  });
}
