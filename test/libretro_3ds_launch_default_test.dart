import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/libretro_resolution.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

/// docs/libretro-3ds-system-settings.md § 3.2: a 3DS launch carries the
/// system language matching the NeoStation language in its `optionDefaults`
/// layer, only while `Config/Azahar.json` stores no `citra_language_value`.
/// The native host applies that layer under any stored value, so a choice
/// made in the in-game menu or on the Nintendo 3DS page always wins. The
/// other cores keep their catalog defaults untouched.
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
    root = await Directory.systemTemp.createTemp('libretro_3ds_launch_');
    launches.clear();
    messenger.setMockMethodCallHandler(paths, (_) async => root.path);
    messenger.setMockMethodCallHandler(bridge, (call) async {
      if (call.method == 'launch') {
        launches.add(Map<Object?, Object?>.from(call.arguments as Map));
        return <String, Object?>{'success': true, 'libraryName': 'Azahar', 'libraryVersion': '0'};
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

  Future<File> azaharOptions() async =>
      File(p.join((await LibretroInternalService.configDirectory()).path, 'Azahar.json'));

  Future<Map<Object?, Object?>> launch3ds(Locale locale, {String name = 'Game.3ds'}) async {
    final outcome = await LibretroInternalService.launch(system: system('3ds'), game: game(rom(name).path), locale: locale);
    expect(outcome.success, isTrue);
    return Map<Object?, Object?>.from(launches.last['optionDefaults'] as Map);
  }

  test('without a stored language, the launch default follows the NeoStation language', () async {
    expect(await launch3ds(const Locale('fr')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'French'});
    expect(await launch3ds(const Locale('ja')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'Japanese'});
    expect(await launch3ds(const Locale('zh', 'TW')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'Traditional Chinese'});
    expect(await launch3ds(const Locale('zh')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'Simplified Chinese'});
    // Indonesian has no 3DS equivalent: the explicit English fallback.
    expect(await launch3ds(const Locale('id')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'English'});
    // The option file is never written by the launch: the default stays a
    // launch-time layer, and the first in-game or page choice is what the
    // native session stores.
    expect(await (await azaharOptions()).exists(), isFalse);
  });

  test('a stored language wins: no default is sent', () async {
    final file = await azaharOptions();
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(jsonEncode(<String, Object>{
      'values': <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'Japanese', 'citra_region_value': 'Auto'},
    }));
    expect(await launch3ds(const Locale('fr')), <String, String>{'citra_use_fastinterp': 'enabled'});
    expect(launches.single['optionDefaults'], isA<Map<Object?, Object?>>());
  });

  test('other stored options leave the language default in place', () async {
    final file = await azaharOptions();
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(jsonEncode(<String, Object>{
      'values': <String, String>{'citra_region_value': 'Europe', 'citra_is_new_3ds': 'Old 3DS'},
    }));
    expect(await launch3ds(const Locale('de')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'German'});
  });

  test('a non-string or malformed stored value counts as absent, like the native reader', () async {
    final file = await azaharOptions();
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(jsonEncode(<String, Object>{
      'values': <String, Object>{'citra_language_value': 3},
    }));
    expect(await launch3ds(const Locale('it')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'Italian'});
    file.writeAsStringSync('{"values": not json');
    expect(await launch3ds(const Locale('es')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'Spanish'});
    file.writeAsStringSync(jsonEncode(<String, Object>{'values': <Object>[]}));
    expect(await launch3ds(const Locale('pt')), <String, String>{'citra_use_fastinterp': 'enabled', 'citra_language_value': 'Portuguese'});
  });

  test('a disabled FastInterp preference survives launch without being overwritten', () async {
    final file = await azaharOptions();
    file.parent.createSync(recursive: true);
    file.writeAsStringSync(jsonEncode(<String, Object>{
      'values': <String, String>{'citra_use_fastinterp': 'disabled', 'unrelated': 'keep'},
    }));
    final before = file.readAsStringSync();
    final defaults = await launch3ds(const Locale('fr'));
    expect(defaults['citra_use_fastinterp'], 'enabled');
    // Defaults are a lower layer; the native persistence test proves that
    // the stored disabled value wins when the real option store is opened.
    expect(file.readAsStringSync(), before);
  });

  test('the 3DS launch request also carries the lock and the in-game settings', () async {
    await launch3ds(const Locale('en'));
    final request = launches.single;
    expect(request['coreId'], 'azahar');
    expect(Map<Object?, Object?>.from(request['lockedOptions'] as Map)['citra_use_libretro_save_path'],
        'LibRetro Default');
    final settings = (request['coreSettings'] as List).cast<Map<Object?, Object?>>();
    // Contract change (docs/libretro-3ds-system-settings.md § 6.4, item 9):
    // the model needs a new session, which "Restart game" does not start,
    // so the in-game menu (footer: "after a restart") no longer receives
    // it; the Nintendo 3DS page of the Emulators tab still offers it.
    expect(settings.map((setting) => setting['key']).toList(),
        <String>['citra_region_value', 'citra_language_value', 'citra_use_fastinterp']);
    expect(settings.map((setting) => setting['key']), isNot(contains('citra_is_new_3ds')));
    expect(settings[0]['label'], 'System region');
    expect(settings[1]['label'], 'System language');
    expect(settings[2]['label'], 'Fast Interpreter (relaunch game)');
    expect(settings[2]['values'], <Map<String, String>>[
      {'value': 'enabled', 'label': 'Enabled'},
      {'value': 'disabled', 'label': 'Disabled'},
    ]);
    expect(request['noJitOverrides'], isEmpty);
    final languageValues = (settings[1]['values'] as List).cast<Map<Object?, Object?>>();
    expect(languageValues.map((value) => value['value']).toList(), contains('Traditional Chinese'));
    expect(languageValues.firstWhere((value) => value['value'] == 'Traditional Chinese')['label'],
        'Traditional Chinese');
  });

  test('other cores keep their catalog defaults, byte for byte', () async {
    var outcome = await LibretroInternalService.launch(
      system: system('nes'),
      game: game(rom('Mario.nes').path),
      locale: const Locale('fr'),
    );
    expect(outcome.success, isTrue);
    expect(launches.last['optionDefaults'], isEmpty);
    outcome = await LibretroInternalService.launch(
      system: system('psp'),
      game: game(rom('Game.iso').path),
      locale: const Locale('ja'),
    );
    expect(outcome.success, isTrue);
    // Contract change (Build 455, docs/libretro-resolution.md § 4): every
    // core starts at its native resolution unless the user chose another,
    // so PPSSPP no longer gets the 960x544 NeoStation default.
    expect(launches.last['optionDefaults'], isEmpty);
    // The session gets the rules recognizing the core's resolution option.
    expect(jsonDecode(jsonEncode(launches.last['resolution'])), jsonDecode(jsonEncode(LibretroResolution.nativeRules())));
    // Nothing of the 3DS layer leaks into another core.
    for (final launch in launches) {
      expect(Map<Object?, Object?>.from(launch['optionDefaults'] as Map).containsKey('citra_language_value'), isFalse);
    }
  });
}
