import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/services/libretro_bios_check_service.dart';
import 'package:neostation/services/libretro_bios_catalog.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

/// The BIOS checker never adds a launch rule: a game whose BIOS is optional
/// or missing-but-optional reaches the native session exactly as before,
/// and NeoStation's PlayStation rule (an exact name of
/// `LibretroCore.biosAnyOf` in System) is unchanged.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  const bridge = MethodChannel('neostation/libretro_internal');
  late Directory root;
  final launches = <Map<Object?, Object?>>[];

  SystemModel system(String folder) =>
      SystemModel(id: folder, folderName: folder, realName: folder, iconImage: '', color: '#000000');

  GameModel game(String file) => GameModel(
        romname: p.basename(file),
        realname: p.basename(file),
        name: p.basenameWithoutExtension(file),
        year: '',
        developer: '',
        publisher: '',
        genre: '',
        players: '',
        rating: 0,
        romPath: file,
      );

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    root = await Directory.systemTemp.createTemp('libretro_bios_launch_');
    launches.clear();
    messenger.setMockMethodCallHandler(paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(bridge, (call) async {
      if (call.method == 'launch') {
        launches.add(Map<Object?, Object?>.from(call.arguments as Map));
        return <String, Object?>{'success': true, 'libraryName': 'mock', 'libraryVersion': '0'};
      }
      return null;
    });
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(paths, null);
    messenger.setMockMethodCallHandler(bridge, null);
    root.deleteSync(recursive: true);
  });

  File rom(String name) => File(p.join(root.path, 'roms', name))
    ..createSync(recursive: true)
    ..writeAsBytesSync(List<int>.filled(16, 1));

  test('a game whose BIOS is optional launches with an empty System folder', () async {
    for (final (folder, name) in <(String, String)>[('nes', 'Mario.nes'), ('gba', 'Zelda.gba'), ('md', 'Sonic.md')]) {
      final outcome = await LibretroInternalService.launch(
        system: system(folder),
        game: game(rom(name).path),
        locale: const Locale('en'),
      );
      expect(outcome.success, isTrue, reason: folder);
    }
    expect(launches, hasLength(3));
    final systemDirectory = await LibretroInternalService.systemDirectory();
    expect(systemDirectory.listSync(), isEmpty);
  });

  test('the PlayStation launch rule is unchanged: exact names in System only', () async {
    final disc = rom('Crash (USA).cue').path;
    var outcome = await LibretroInternalService.launch(system: system('ps1'), game: game(disc), locale: const Locale('en'));
    expect(outcome.success, isFalse);
    expect(outcome.errorCode, 'LIBRETRO_BIOS_MISSING');
    expect(outcome.technicalDetails, 'scph5500.bin, scph5501.bin, scph5502.bin');
    expect(launches, isEmpty);

    final systemDirectory = await LibretroInternalService.systemDirectory();
    File(p.join(systemDirectory.path, 'scph5501.bin')).writeAsBytesSync(List<int>.filled(16, 2));
    outcome = await LibretroInternalService.launch(system: system('ps1'), game: game(disc), locale: const Locale('en'));
    expect(outcome.success, isTrue);
    expect(launches, hasLength(1));
    expect(launches.single['coreId'], 'mednafen_psx_hw');
  });

  test('the Intellivision needs both BIOS files and names the missing ones (lot 2)', () async {
    final cartridge = rom('4-Tris.int').path;
    var outcome = await LibretroInternalService.launch(system: system('intv'), game: game(cartridge), locale: const Locale('en'));
    expect(outcome.success, isFalse);
    expect(outcome.errorCode, 'LIBRETRO_BIOS_MISSING_ALL');
    expect(outcome.technicalDetails, 'exec.bin, grom.bin');

    final systemDirectory = await LibretroInternalService.systemDirectory();
    File(p.join(systemDirectory.path, 'exec.bin')).writeAsBytesSync(List<int>.filled(16, 4));
    outcome = await LibretroInternalService.launch(system: system('intv'), game: game(cartridge), locale: const Locale('en'));
    expect(outcome.errorCode, 'LIBRETRO_BIOS_MISSING_ALL');
    expect(outcome.technicalDetails, 'grom.bin', reason: 'one file is not enough');
    expect(launches, isEmpty);

    File(p.join(systemDirectory.path, 'grom.bin')).writeAsBytesSync(List<int>.filled(16, 5));
    outcome = await LibretroInternalService.launch(system: system('intv'), game: game(cartridge), locale: const Locale('en'));
    expect(outcome.success, isTrue);
    expect(launches.single['coreId'], 'freeintv');
  });

  test('O2EM and Beetle PC-FX refuse the launch without their BIOS (lot 2)', () async {
    final o2 = await LibretroInternalService.launch(
        system: system('mo2'), game: game(rom('Quest for the Rings.bin').path), locale: const Locale('en'));
    expect(o2.errorCode, 'LIBRETRO_BIOS_MISSING');
    expect(o2.technicalDetails, 'o2rom.bin');
    final fx = await LibretroInternalService.launch(
        system: system('pcfx'), game: game(rom('Battle Heat.cue').path), locale: const Locale('en'));
    expect(fx.errorCode, 'LIBRETRO_BIOS_MISSING');
    expect(fx.technicalDetails, 'pcfx.rom');
    // The Channel F core has a replacement BIOS: it launches without one.
    final chf = await LibretroInternalService.launch(
        system: system('chf'), game: game(rom('Videocart 1.bin').path), locale: const Locale('en'));
    expect(chf.success, isTrue);
    expect(launches.single['coreId'], 'freechaf');
  });

  test('the checker and the launch rule agree on the PlayStation names', () async {
    final catalog = LibretroBiosCatalog.parse(File(LibretroBiosCatalog.assetPath).readAsStringSync());
    final service = LibretroBiosCheckService(
      catalog: () async => catalog,
      environment: () async => LibretroBiosEnvironment(
        systemDirectory: (await LibretroInternalService.systemDirectory()).path,
        configDirectory: (await LibretroInternalService.configDirectory()).path,
        cacheFile: p.join(root.path, 'cache', LibretroBiosCheckService.cacheFileName),
        documentsDirectory: root.path,
      ),
      library: (_) async => const <LibretroBiosGame>[],
      hasher: (requests) async => LibretroBiosCheckService.hashFilesSync(requests),
    );
    final systemDirectory = await LibretroInternalService.systemDirectory();
    systemDirectory.createSync(recursive: true);
    for (final name in <String>['scph5500.bin', 'scph5501.bin', 'scph5502.bin']) {
      final file = File(p.join(systemDirectory.path, name))..writeAsBytesSync(List<int>.filled(16, 3));
      final psx = (await service.check()).consoles.firstWhere((console) => console.id == 'psx');
      final launch = await LibretroInternalService.launch(
        system: system('ps1'),
        game: game(rom('Disc.cue').path),
        locale: const Locale('en'),
      );
      expect(psx.gateNote?.key, 'biosGateOk', reason: name);
      expect(launch.success, isTrue, reason: name);
      file.deleteSync();
    }
    final psx = (await service.check()).consoles.firstWhere((console) => console.id == 'psx');
    final launch = await LibretroInternalService.launch(system: system('ps1'), game: game(rom('Disc.cue').path), locale: const Locale('en'));
    expect(psx.gateNote?.key, 'biosGateMissing');
    expect(launch.errorCode, 'LIBRETRO_BIOS_MISSING');
  });
}
