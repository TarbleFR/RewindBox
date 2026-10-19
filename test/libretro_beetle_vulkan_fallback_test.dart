import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

/// Build 489: Beetle PSX HW asks the session for Vulkan (MoltenVK), with its
/// HD texture options locked; when no Vulkan device can be made, one new
/// session runs it on its software renderer. No other core is relaunched.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const paths = MethodChannel('plugins.flutter.io/path_provider');
  const bridge = MethodChannel('neostation/libretro_internal');
  late Directory root;
  final launches = <Map<Object?, Object?>>[];
  var answers = <Map<String, Object?>>[];

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

  const failure = <String, Object?>{
    'success': false,
    'code': 'LIBRETRO_HARDWARE_RENDER_FAILED',
    'message': 'vkCreateDevice failed',
  };
  const success = <String, Object?>{'success': true, 'libraryName': 'Beetle PSX HW', 'libraryVersion': '0'};

  setUp(() async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    root = await Directory.systemTemp.createTemp('libretro_beetle_vulkan_');
    launches.clear();
    messenger.setMockMethodCallHandler(paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(bridge, (call) async {
      if (call.method == 'launch') {
        launches.add(Map<Object?, Object?>.from(call.arguments as Map));
        return answers.isNotEmpty ? answers.removeAt(0) : success;
      }
      return null;
    });
    final systemDirectory = await LibretroInternalService.systemDirectory();
    File(p.join(systemDirectory.path, 'scph5501.bin')).writeAsBytesSync(List<int>.filled(16, 2));
  });

  tearDown(() {
    messenger.setMockMethodCallHandler(paths, null);
    messenger.setMockMethodCallHandler(bridge, null);
    root.deleteSync(recursive: true);
  });

  String rom(String name) => (File(p.join(root.path, 'roms', name))
        ..createSync(recursive: true)
        ..writeAsBytesSync(List<int>.filled(16, 1)))
      .path;

  Map<Object?, Object?> locked(Map<Object?, Object?> launch) => Map<Object?, Object?>.from(launch['lockedOptions'] as Map);

  test('Beetle PSX HW asks for Vulkan with its texture options locked', () async {
    final outcome = await LibretroInternalService.launch(
        system: system('ps1'), game: game(rom('Castlevania (USA).cue')), locale: const Locale('en'));
    expect(outcome.success, isTrue);
    expect(launches, hasLength(1));
    expect(launches.single['coreId'], 'mednafen_psx_hw');
    expect(launches.single['preferredHardwareContext'], LibretroHardwareContext.vulkan);
    expect(locked(launches.single), containsPair('beetle_psx_hw_texture_directory', 'save'));
    expect(locked(launches.single), containsPair('beetle_psx_hw_dump_textures', 'disabled'));
    expect(locked(launches.single).containsKey('beetle_psx_hw_renderer'), isFalse,
        reason: 'the renderer is left to the core and the user while Vulkan works');
  });

  test('without a Vulkan device, one new session on the software renderer', () async {
    answers = [failure];
    final outcome = await LibretroInternalService.launch(
        system: system('ps1'), game: game(rom('Castlevania (USA).cue')), locale: const Locale('en'));
    expect(outcome.success, isTrue);
    expect(launches, hasLength(2));
    expect(launches.last['preferredHardwareContext'], LibretroHardwareContext.none);
    expect(locked(launches.last), containsPair('beetle_psx_hw_renderer', 'software'));
    // The texture options stay locked: nothing is dumped, nothing written beside the games.
    expect(locked(launches.last), containsPair('beetle_psx_hw_dump_textures', 'disabled'));
    expect(locked(launches.last), containsPair('beetle_psx_hw_texture_directory', 'save'));
    expect(launches.last['contentPath'], launches.first['contentPath']);
  });

  test('a software session that fails too is reported, never retried again', () async {
    answers = [failure, failure];
    final outcome = await LibretroInternalService.launch(
        system: system('ps1'), game: game(rom('Castlevania (USA).cue')), locale: const Locale('en'));
    expect(outcome.success, isFalse);
    expect(outcome.errorCode, 'LIBRETRO_HARDWARE_RENDER_FAILED');
    expect(launches, hasLength(2));
  });

  test('another core is never relaunched on a hardware failure', () async {
    answers = [failure];
    final outcome = await LibretroInternalService.launch(
        system: system('psp'), game: game(rom('Patapon (USA).iso')), locale: const Locale('en'));
    expect(outcome.success, isFalse);
    expect(outcome.errorCode, 'LIBRETRO_HARDWARE_RENDER_FAILED');
    expect(launches, hasLength(1));
  });
}
