import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/adapters/armsx2_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/adapters/ps2_disc_identity.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:path/path.dart' as path;

import 'enhancement_test_support.dart';

/// A minimal ISO9660 volume: PVD, root directory, SYSTEM.CNF and a boot ELF.
Uint8List isoImage(List<int> elf, {String boot = r'cdrom0:\SLUS_210.50;1'}) {
  const rootSector = 20, cnfSector = 21, elfSector = 22;
  final cnf = 'BOOT2 = $boot\r\nVER = 1.00\r\nVMODE = NTSC\r\n'.codeUnits;
  final elfSectors = (elf.length + 2047) ~/ 2048;
  final image = Uint8List((elfSector + elfSectors) * 2048);
  Uint8List record(String name, int extent, int size, {bool directory = false}) {
    final length = 33 + name.length + (name.length.isEven ? 1 : 0);
    final bytes = Uint8List(length);
    final view = ByteData.sublistView(bytes);
    bytes[0] = length;
    view.setUint32(2, extent, Endian.little);
    view.setUint32(10, size, Endian.little);
    bytes[25] = directory ? 2 : 0;
    bytes[32] = name.length;
    bytes.setRange(33, 33 + name.length, name.codeUnits);
    return bytes;
  }

  final pvd = 16 * 2048;
  image[pvd] = 1;
  image.setRange(pvd + 1, pvd + 6, 'CD001'.codeUnits);
  final root = record('\u0000', rootSector, 2048, directory: true);
  image.setRange(pvd + 156, pvd + 156 + root.length, root);
  var at = rootSector * 2048;
  for (final entry in [
    record('\u0000', rootSector, 2048, directory: true),
    record('\u0001', rootSector, 2048, directory: true),
    record('SYSTEM.CNF;1', cnfSector, cnf.length),
    record('SLUS_210.50;1', elfSector, elf.length),
  ]) {
    image.setRange(at, at + entry.length, entry);
    at += entry.length;
  }
  image.setRange(cnfSector * 2048, cnfSector * 2048 + cnf.length, cnf);
  image.setRange(elfSector * 2048, elfSector * 2048 + elf.length, elf);
  return image;
}

/// The same volume in raw 2352-byte MODE2/XA sectors (24-byte headers).
Uint8List mode2Image(Uint8List iso) {
  final sectors = iso.length ~/ 2048;
  final raw = Uint8List(sectors * 2352);
  for (var i = 0; i < sectors; i++) {
    raw.setRange(i * 2352 + 24, i * 2352 + 24 + 2048, iso, i * 2048);
  }
  return raw;
}

void main() {
  late Directory temp;
  late Directory data;

  setUp(() {
    temp = Directory.systemTemp.createTempSync('enh-armsx2-');
    data = Directory(path.join(temp.path, 'ARMSX2'))..createSync();
  });
  tearDown(() => temp.deleteSync(recursive: true));

  group('PS2 disc identity', () {
    final elf = Uint8List(5000);
    for (var i = 0; i < elf.length; i++) {
      elf[i] = (i * 31 + 7) & 0xff;
    }
    var expected = 0;
    final words = ByteData.sublistView(elf);
    for (var i = 0; i + 4 <= elf.length; i += 4) {
      expected ^= words.getUint32(i, Endian.little);
    }
    final expectedCrc = expected.toRadixString(16).padLeft(8, '0').toUpperCase();

    test('reads the serial and the PCSX2 ELF CRC of an ISO', () async {
      final file = File(path.join(temp.path, 'game.iso'))..writeAsBytesSync(isoImage(elf));
      final identity = await Ps2DiscIdentity.read(file.path);
      expect(identity.serial, 'SLUS-21050');
      expect(identity.crc, expectedCrc);
    });

    test('reads the same identity from a raw MODE2 BIN', () async {
      final file = File(path.join(temp.path, 'game.bin'))..writeAsBytesSync(mode2Image(isoImage(elf)));
      final identity = await Ps2DiscIdentity.read(file.path);
      expect(identity.serial, 'SLUS-21050');
      expect(identity.crc, expectedCrc);
    });

    test('compressed images are reported, never guessed', () async {
      final file = File(path.join(temp.path, 'game.chd'))..writeAsBytesSync([1, 2, 3]);
      final identity = await Ps2DiscIdentity.read(file.path);
      expect(identity.known, isFalse);
      expect(identity.problem, Ps2DiscIdentity.unsupportedFormat);
      expect(Ps2DiscIdentity.serialFromBootName('SCES_534.55;1'), 'SCES-53455');
      expect(Ps2DiscIdentity.serialFromBootName('MAIN.ELF;1'), isNull);
    });
  });

  group('adapter', () {
    late EnhancementService service;
    late File rom;
    var crc = 'BEBF8793'; // Burnout 3: Takedown (U), SLUS-21050, in pcsx2_patches.

    setUp(() {
      crc = 'BEBF8793';
      rom = File(path.join(temp.path, 'Burnout 3.iso'))..writeAsBytesSync([0]);
      service = EnhancementService(
        catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
        store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
        adapters: [
          Armsx2EnhancementAdapter(
            dataDirectory: () async => data,
            readIdentity: (_) async => Ps2DiscIdentity('SLUS-21050', crc),
          ),
        ],
        texturesSupported: (_) => false,
      );
    });

    File pnach() => File(path.join(data.path, 'patches', 'SLUS-21050_BEBF8793.pnach'));
    File settings() => File(path.join(data.path, 'gamesettings', 'SLUS-21050_BEBF8793.ini'));

    test('installs the pnach PCSX2 prefers and enables the patch by name', () async {
      final game = testGame(name: 'Burnout 3', romPath: rom.path);
      var view = await service.open(game, 'ps2', download: true);
      final widescreen = view.items.firstWhere((item) => item.name == 'Widescreen 16:9');
      expect(widescreen.category, EnhancementCategory.ultrawide);
      view = await service.setActive(game, 'ps2', view, widescreen, true);
      expect(pnach().readAsStringSync(), contains('[Widescreen 16:9]'));
      expect(settings().readAsStringSync(), '[Patches]\nEnable = Widescreen 16:9\n');

      final fps = view.items.firstWhere((item) => item.name == '60 FPS for Menus');
      view = await service.setActive(game, 'ps2', view, fps, true);
      expect(settings().readAsStringSync(), contains('Enable = 60 FPS for Menus'));
      view = await service.setActive(game, 'ps2', view, view.items.firstWhere((i) => i.id == widescreen.id), false);
      expect(settings().readAsStringSync(), isNot(contains('Widescreen')));

      await service.restore(view.identity.storeKey);
      expect(pnach().existsSync(), isFalse);
      expect(settings().existsSync(), isFalse, reason: 'RewindBox created it');
    });

    test('settings written by ARMSX2 keep their other lines', () async {
      settings()
        ..createSync(recursive: true)
        ..writeAsStringSync('[EmuCore/GS]\nupscale_multiplier = 3\n\n[Patches]\nEnable = Progressive Scan\n');
      final game = testGame(name: 'Burnout 3', romPath: rom.path);
      var view = await service.open(game, 'ps2', download: true);
      expect(view.items.firstWhere((i) => i.name == 'Progressive Scan').status, EnhancementStatus.active,
          reason: 'enabled from the in-game Patches page');
      view = await service.setActive(game, 'ps2', view, view.items.firstWhere((i) => i.name == 'Widescreen 16:9'), true);
      await service.restore(view.identity.storeKey);
      expect(settings().readAsStringSync(),
          '[EmuCore/GS]\nupscale_multiplier = 3\n\n[Patches]\nEnable = Progressive Scan\n');
    });

    test('a pnach of the player is never replaced', () async {
      pnach()
        ..createSync(recursive: true)
        ..writeAsStringSync('gametitle=mine\n[Mine]\npatch=1,EE,00100000,word,00000000\n');
      final game = testGame(name: 'Burnout 3', romPath: rom.path);
      final view = await service.open(game, 'ps2', download: true);
      await expectLater(
        service.setActive(game, 'ps2', view, view.items.first, true),
        throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'user_file_present')),
      );
      expect(pnach().readAsStringSync(), contains('gametitle=mine'));
    });

    test('another disc revision shows the patches as incompatible', () async {
      crc = '00000001';
      final game = testGame(name: 'Burnout 3', romPath: rom.path);
      final view = await service.open(game, 'ps2', download: true);
      expect(view.items, isNotEmpty);
      expect(view.items.every((item) => item.status == EnhancementStatus.incompatible), isTrue);
      expect(view.items.first.problem, EnhancementProblem.revisionMismatch);
    });
  });
}
