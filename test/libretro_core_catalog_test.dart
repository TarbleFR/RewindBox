import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart' show Locale;
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/services/libretro_3ds_language.dart';
import 'package:neostation/services/libretro_core_catalog.dart';

Map<String, Map<String, dynamic>> _systemsById() {
  final systems = <String, Map<String, dynamic>>{};
  for (final file in Directory('assets/systems').listSync().whereType<File>()) {
    if (!file.path.endsWith('.json')) continue;
    final json = jsonDecode(file.readAsStringSync()) as Map<String, dynamic>;
    final system = json['system'];
    if (system is Map<String, dynamic> && system['id'] is String) {
      systems[system['id'] as String] = json;
    }
  }
  return systems;
}

Set<String> _iosUrlSchemes(Map<String, dynamic> json) {
  final schemes = <String>{};
  for (final emulator in (json['emulators'] as List? ?? const [])) {
    final ios = (emulator as Map)['platforms']?['ios'];
    if (ios is Map && ios['url_scheme'] is String) schemes.add(ios['url_scheme'] as String);
    if (ios is Map && ios['embedded'] == true) schemes.add('embedded');
  }
  return schemes;
}

void main() {
  final systems = _systemsById();
  final manifest = jsonDecode(File('build-utils/libretro/cores.json').readAsStringSync())
      as Map<String, dynamic>;
  final packaged = {
    for (final core in manifest['cores'] as List) (core as Map)['id'] as String,
  };

  test('bound systems exist and were RetroArch systems, never another engine', () {
    for (final folder in LibretroCoreCatalog.systems.keys) {
      expect(systems.containsKey(folder), isTrue, reason: folder);
      expect(_iosUrlSchemes(systems[folder]!), contains('retroarch'), reason: folder);
      expect(_iosUrlSchemes(systems[folder]!), isNot(contains('embedded')), reason: folder);
    }
    for (final folder in <String>['ps2', 'ps3', 'gc', 'wii', 'ports', 'switch', 'mame']) {
      expect(LibretroCoreCatalog.handles(folder), isFalse, reason: folder);
    }
  });

  test('every bound core is described and packaged', () {
    for (final binding in LibretroCoreCatalog.systems.values) {
      for (final id in <String>[binding.coreId, ...binding.alternatives]) {
        expect(LibretroCoreCatalog.cores.containsKey(id), isTrue, reason: id);
        expect(packaged, contains(id), reason: id);
      }
    }
    for (final id in LibretroCoreCatalog.cores.keys) {
      expect(packaged, contains(id), reason: id);
      expect(RegExp(r'^[a-z0-9_]+$').hasMatch(id), isTrue, reason: id);
    }
  });

  test('RetroAchievements console ids agree with the system definitions', () {
    for (final entry in LibretroCoreCatalog.systems.entries) {
      final ids = systems[entry.key]!['system']['ids'];
      final declared = ids is Map ? ids['retroachievements'] : null;
      if (declared is int) {
        expect(entry.value.achievementsConsoleId, declared, reason: entry.key);
      }
    }
  });

  test('import accepts the core formats and zip archives', () {
    expect(LibretroCoreCatalog.importExtensionsFor('snes'), containsAll(<String>['sfc', 'smc', 'zip']));
    expect(LibretroCoreCatalog.importExtensionsFor('gba'), containsAll(<String>['gba', 'zip']));
    expect(LibretroCoreCatalog.importExtensionsFor('psp'), containsAll(<String>['iso', 'cso']));
    expect(LibretroCoreCatalog.importExtensionsFor('unknown'), <String>{'zip'});
  });

  test('the import picker only offers formats the library scanner indexes', () {
    Set<String> scanned(String folder) => {
          for (final extension in systems[folder]!['system']['extensions'] as List) extension as String,
        };
    // Without the scanner's list, PSP and 3DS archives were copied into
    // roms/<system> but never listed (assets/systems has no zip, no z3dsx).
    final psp = LibretroCoreCatalog.importExtensionsFor('psp', indexed: scanned('psp'));
    expect(psp, containsAll(<String>['iso', 'cso', 'pbp', 'chd']));
    expect(psp, isNot(contains('zip')));
    final threeDs = LibretroCoreCatalog.importExtensionsFor('3ds', indexed: scanned('3ds'));
    expect(threeDs, containsAll(<String>['3ds', 'cci', 'cxi', '3dsx']));
    expect(threeDs, isNot(contains('zip')));
    expect(threeDs, isNot(contains('z3dsx')));
    expect(LibretroCoreCatalog.importExtensionsFor('snes', indexed: scanned('snes')),
        containsAll(<String>['sfc', 'smc', 'zip']));
    expect(LibretroCoreCatalog.importExtensionsFor('gba', indexed: <String>['.GBA', 'zip']), <String>{'gba', 'zip'});
    for (final folder in LibretroCoreCatalog.systems.keys) {
      final offered = LibretroCoreCatalog.importExtensionsFor(folder, indexed: scanned(folder));
      expect(offered, isNotEmpty, reason: folder);
      expect(scanned(folder).containsAll(offered), isTrue, reason: folder);
    }
  });

  test('every bound system belongs to one of the 42 consoles', () {
    // The 17 consoles of the embedded engine, then the 21 of lot 1
    // (docs/libretro-consoles-lot1.md) and the 4 of lot 2
    // (docs/libretro-consoles-lot2.md), whose ids are those the Consoles tab
    // already used for them as RetroArch consoles.
    const ids = <String>[
      'nes', 'snes', 'gb', 'gbc', 'gba', 'md', 'mcd', '32x', 'sms', 'gg', 'sg1000', 'arcade', 'nds', 'n64',
      'psx', 'psp', '3ds', 'pce', 'tg16', 'pccd', 'tgcd', 'ws', 'wsc', 'ngp', 'ngpc', 'lynx', 'vb', '2600',
      '7800', '5200', 'cv', 'mini', 'gw', 'duck', 'wsv', 'ard', 'wasm4', 'uze', 'chf', 'intv', 'mo2', 'pcfx',
    ];
    expect(LibretroCoreCatalog.consoles.keys.toList(), ids);
    for (final entry in LibretroCoreCatalog.consoles.entries) {
      expect(entry.value.id, entry.key);
      expect(entry.value.name, isNotEmpty);
    }
    for (final entry in LibretroCoreCatalog.systems.entries) {
      expect(ids, contains(entry.value.console), reason: entry.key);
      expect(LibretroCoreCatalog.consoleFor(entry.key)!.id, entry.value.console, reason: entry.key);
    }
    final expected = <String, String>{
      'nes': 'nes', 'fc': 'nes', 'fds': 'nes', 'nes-hacks': 'nes', 'snes': 'snes', 'satellaview': 'snes',
      'gb': 'gb', 'gb-hacks': 'gb', 'gbc': 'gbc', 'gbc-hacks': 'gbc', 'gba': 'gba', 'gba-hacks': 'gba',
      'md': 'md', 'genesis': 'md', 'pico': 'md', 'mcd': 'mcd', 'scd': 'mcd', '32x': '32x', 'sms': 'sms',
      'mark3': 'sms', 'gg': 'gg', 'sg1k': 'sg1000', 'arc': 'arcade', 'fbneo': 'arcade', 'cps1': 'arcade',
      'cps2': 'arcade', 'cps3': 'arcade', 'neogeo': 'arcade', 'ds': 'nds', 'n64': 'n64', 'ps1': 'psx',
      'psp': 'psp', 'pspminis': 'psp', '3ds': '3ds',
      // Lot 1: one console per system, as in the Consoles tab before.
      'pce': 'pce', 'tg16': 'tg16', 'pccd': 'pccd', 'tgcd': 'tgcd', 'ws': 'ws', 'wsc': 'wsc', 'ngp': 'ngp',
      'ngpc': 'ngpc', 'lynx': 'lynx', 'vb': 'vb', '2600': '2600', '7800': '7800', '5200': '5200', 'cv': 'cv',
      'mini': 'mini', 'gw': 'gw', 'duck': 'duck', 'wsv': 'wsv', 'ard': 'ard', 'wasm4': 'wasm4', 'uze': 'uze',
      // Lot 2.
      'chf': 'chf', 'intv': 'intv', 'mo2': 'mo2', 'pcfx': 'pcfx',
    };
    for (final entry in expected.entries) {
      expect(LibretroCoreCatalog.systems[entry.key]!.console, entry.value, reason: entry.key);
    }
    // Game Boy, Game Boy Color and Game Boy Advance keep separate settings
    // even though gambatte and mGBA run more than one of them.
    expect(<String>{
      LibretroCoreCatalog.systems['gb']!.console,
      LibretroCoreCatalog.systems['gbc']!.console,
      LibretroCoreCatalog.systems['gba']!.console,
    }, hasLength(3));
  });

  test('the Dart console list is the native one', () {
    final source = File('packages/libretro_internal_bridge/ios/Classes/LibretroInputMap.m');
    expect(source.existsSync(), isTrue, reason: 'LibretroInputMap.m holds +[LibretroInputMap consoles]');
    // Tolerant to formatting: any @[...] or {...} list of string literals
    // (comments removed) that names the consoles in order.
    final text = source.readAsStringSync().replaceAll(RegExp(r'//[^\n]*'), '');
    final lists = RegExp(r'[\[{]\s*((?:@"[a-z0-9]+"\s*,\s*)+@"[a-z0-9]+"\s*,?\s*)[\]}]')
        .allMatches(text)
        .map((match) => RegExp(r'@"([a-z0-9]+)"').allMatches(match.group(1)!).map((id) => id.group(1)!).toList())
        .toList();
    expect(lists, contains(equals(LibretroCoreCatalog.consoles.keys.toList())));
  });

  test('console geometry follows the core pictures', () {
    final geometry = LibretroCoreCatalog.consoleGeometry();
    expect(geometry.keys.toList(), LibretroCoreCatalog.consoles.keys.toList());
    final sizes = <String, List<int>>{
      'gb': [160, 144], 'gbc': [160, 144], 'gba': [240, 160], 'nes': [256, 240], 'snes': [256, 224],
      'md': [320, 224], 'mcd': [320, 224], '32x': [320, 224], 'sms': [256, 192], 'sg1000': [256, 192],
      'gg': [160, 144], 'arcade': [0, 0], 'nds': [256, 384], 'n64': [320, 240], 'psx': [320, 240],
      'psp': [480, 272], '3ds': [400, 480],
      // Lot 1: av_info of each core (docs/libretro-consoles-lot1.md); 0 x 0
      // where it changes per game or TV standard (Beetle PCE Fast width,
      // Stella and ProSystem lines, Game & Watch backgrounds, Uzem's
      // 720 x 224 frames shown at 630:448).
      'pce': [0, 0], 'tg16': [0, 0], 'pccd': [0, 0], 'tgcd': [0, 0], 'ws': [224, 144], 'wsc': [224, 144],
      'ngp': [160, 152], 'ngpc': [160, 152], 'lynx': [160, 102], 'vb': [384, 224], '2600': [0, 0],
      '7800': [0, 0], '5200': [320, 224], 'cv': [256, 192], 'mini': [96, 64], 'gw': [0, 0],
      'duck': [160, 144], 'wsv': [160, 160], 'ard': [128, 64], 'wasm4': [160, 160], 'uze': [0, 0],
      // Lot 2 (docs/libretro-consoles-lot2.md): FreeChaF's 102 x 64 shown
      // three times larger, FreeIntv; 0 x 0 for O2EM (overscan crop) and
      // Beetle PC-FX (dot clock).
      'chf': [306, 192], 'intv': [352, 224], 'mo2': [0, 0], 'pcfx': [0, 0],
    };
    expect(sizes.keys.toSet(), LibretroCoreCatalog.consoles.keys.toSet());
    for (final entry in sizes.entries) {
      expect(geometry[entry.key]!['size'], entry.value, reason: entry.key);
    }
    expect(geometry['nds']!['regions'], <String, List<double>>{
      'top': [0, 0, 1, 0.5],
      'bottom': [0, 0.5, 1, 0.5],
    });
    // 400x240 top screen above the 320x240 bottom screen, centred.
    expect(geometry['3ds']!['regions'], <String, List<double>>{
      'top': [0, 0, 1, 0.5],
      'bottom': [0.1, 0.5, 0.8, 0.5],
    });
    final singleScreen = LibretroCoreCatalog.consoles.keys.where((console) => console != 'nds' && console != '3ds');
    for (final id in singleScreen) {
      expect(geometry[id]!.containsKey('regions'), isFalse, reason: id);
      expect(LibretroCoreCatalog.consoles[id]!.isDualScreen, isFalse, reason: id);
    }
  });

  test('each console imports into an existing system bound to it', () {
    for (final console in LibretroCoreCatalog.consoles.values) {
      expect(systems.containsKey(console.importSystem), isTrue, reason: console.id);
      expect(LibretroCoreCatalog.systems[console.importSystem]?.console, console.id, reason: console.id);
      expect(File('assets/systems/${console.importSystem}.json').existsSync(), isTrue, reason: console.id);
      for (final code in console.catalogSystems) {
        expect(code, code.toLowerCase(), reason: console.id);
      }
    }
    expect(LibretroCoreCatalog.consoles['nds']!.importSystem, 'ds');
    expect(LibretroCoreCatalog.consoles['psx']!.importSystem, 'ps1');
    expect(LibretroCoreCatalog.consoles['sg1000']!.importSystem, 'sg1k');
    // The scanner knows the Mega Duck as "megaduck" (its system id "duck"
    // is not one of its folders): imported games must go where they are
    // listed.
    for (final console in LibretroCoreCatalog.consoles.values) {
      final folders = <String>[
        for (final folder in systems[console.importSystem]!['system']['folders'] as List)
          (folder as String).toLowerCase(),
      ];
      expect(folders, contains(console.importFolder), reason: console.id);
    }
    expect(LibretroCoreCatalog.consoles['duck']!.importFolder, 'megaduck');
    for (final system in LibretroCoreCatalog.systems.keys) {
      final folders = <String>[
        for (final folder in systems[system]!['system']['folders'] as List) (folder as String).toLowerCase(),
      ];
      expect(folders, contains(LibretroCoreCatalog.importFolderFor(system)), reason: system);
    }
    expect(LibretroCoreCatalog.consoles['arcade']!.importSystem, 'arc');
  });

  test('an alias folder still resolves to its bound system', () {
    expect(LibretroCoreCatalog.canonicalSystem(id: '3ds', folders: ['3ds', 'n3ds'], folderName: 'n3ds'), '3ds');
    expect(
      LibretroCoreCatalog.canonicalSystem(folders: ['PlayStation Portable', 'PSP'], folderName: 'PlayStation Portable'),
      'psp',
    );
    expect(LibretroCoreCatalog.canonicalSystem(id: 'DS', folderName: 'Nintendo DS'), 'ds');
    expect(LibretroCoreCatalog.canonicalSystem(id: 'ps2', folders: ['ps2'], folderName: 'PS2'), 'ps2');
    // Canonical models already used their folder name as key: stored core
    // choices (libretro_core_v1.<key>/<rom>) keep the same key.
    for (final folder in LibretroCoreCatalog.systems.keys) {
      expect(LibretroCoreCatalog.canonicalSystem(id: folder, folderName: folder), folder);
    }
  });

  test('DS and 3DS options NeoStation needs are locked for the session', () {
    final cores = LibretroCoreCatalog.cores;
    expect(cores['desmume']!.lockedOptions, <String, String>{
      'desmume_screens_layout': 'top/bottom',
      'desmume_screens_gap': '0',
      'desmume_pointer_type': 'touch',
      'desmume_pointer_mouse': 'enabled',
    });
    // Contract change (docs/libretro-3ds-system-settings.md § 3.1): the
    // Azahar user folder is also locked under the libretro save directory,
    // so the Nintendo 3DS page always finds the keys, NAND titles and
    // system save in Libretro › Saves › Azahar › Azahar.
    expect(cores['azahar']!.lockedOptions, <String, String>{
      'citra_layout_option': 'default',
      'citra_swap_screen': 'Top',
      'citra_analog_function': 'c_stick',
      'citra_render_3d': 'off',
      'citra_use_libretro_save_path': 'LibRetro Default',
    });
    // Lot 1: WASM-4 plays its sound through the batch callback only with
    // "normal" audio; its default "callback" needs an audio callback the
    // host does not offer (the game would be silent).
    expect(cores['wasm4']!.lockedOptions, <String, String>{'wasm4_audio_type': 'normal'});
    for (final core in cores.values.where((core) => !{'desmume', 'azahar', 'wasm4'}.contains(core.id))) {
      expect(core.lockedOptions, isEmpty, reason: core.id);
    }
    for (final core in cores.values) {
      final settingKeys = core.settings.map((setting) => setting.key).toSet();
      for (final key in core.lockedOptions.keys) {
        expect(core.optionDefaults.containsKey(key), isFalse, reason: key);
        expect(settingKeys.contains(key), isFalse, reason: key);
      }
    }
  });

  test('the DeSmuME screen layout setting is replaced by NeoStation screen arrangement', () {
    // Contract change: DeSmuME's "Screen layout" was a curated setting with
    // a left/right default. NeoStation now crops and places both screens
    // itself (stacked core picture, locked above), so offering the core
    // layout again would break the crop and the touch screen. The layout*
    // translations stay: the native arrangement page reuses them.
    final desmume = LibretroCoreCatalog.cores['desmume']!;
    expect(desmume.settings.map((setting) => setting.key), isNot(contains('desmume_screens_layout')));
    expect(desmume.optionDefaults.containsKey('desmume_screens_layout'), isFalse);
    expect(desmume.lockedOptions['desmume_screens_layout'], 'top/bottom');
  });

  test('the 3DS core offers system region, language and model, translated twelve times', () {
    final azahar = LibretroCoreCatalog.cores['azahar']!;
    expect(azahar.settings.map((setting) => setting.key).toList(),
        <String>['citra_region_value', 'citra_language_value', 'citra_is_new_3ds', 'citra_use_fastinterp']);
    final region = azahar.settings[0];
    final language = azahar.settings[1];
    final model = azahar.settings[2];
    expect(region.labelKey, 'setting3dsRegion');
    expect(region.values, <String>['Auto', 'Japan', 'USA', 'Europe', 'Australia', 'China', 'Korea', 'Taiwan']);
    expect(region.valueLabelKeys, <String, String>{
      'Auto': 'region3dsAuto', 'Japan': 'region3dsJapan', 'USA': 'region3dsUsa', 'Europe': 'region3dsEurope',
      'Australia': 'region3dsAustralia', 'China': 'region3dsChina', 'Korea': 'region3dsKorea',
      'Taiwan': 'region3dsTaiwan',
    });
    expect(language.labelKey, 'setting3dsLanguage');
    expect(language.values, <String>[
      'English', 'Japanese', 'French', 'Spanish', 'German', 'Italian', 'Dutch', 'Portuguese', 'Russian', 'Korean',
      'Traditional Chinese', 'Simplified Chinese',
    ]);
    expect(language.valueLabelKeys, <String, String>{
      'English': 'lang3dsEnglish', 'Japanese': 'lang3dsJapanese', 'French': 'lang3dsFrench',
      'Spanish': 'lang3dsSpanish', 'German': 'lang3dsGerman', 'Italian': 'lang3dsItalian', 'Dutch': 'lang3dsDutch',
      'Portuguese': 'lang3dsPortuguese', 'Russian': 'lang3dsRussian', 'Korean': 'lang3dsKorean',
      'Traditional Chinese': 'lang3dsZhHant', 'Simplified Chinese': 'lang3dsZhHans',
    });
    expect(model.labelKey, 'setting3dsModel');
    expect(model.values, <String>['New 3DS', 'Old 3DS']);
    expect(model.valueLabelKeys, <String, String>{'New 3DS': 'model3dsNew', 'Old 3DS': 'model3dsOld'});
    expect(region.inGameMenu, isTrue);
    expect(language.inGameMenu, isTrue);
    expect(model.inGameMenu, isFalse, reason: 'needs a new session');
    // Every word value has a label; no stray label for a value the core
    // does not offer.
    for (final setting in azahar.settings) {
      expect(setting.valueLabelKeys.keys.toSet(), setting.values.toSet(), reason: setting.key);
    }
    // The language default of a launch (Libretro3dsLanguage) and the in-game
    // menu read the same value list.
    expect(Libretro3dsLanguage.coreValues, language.values);
    for (final value in language.values) {
      expect(Libretro3dsLanguage.labelKeyFor(value), language.valueLabelKeys[value], reason: value);
    }
    // Labels and value labels exist, non-empty, in all twelve languages.
    expect(LibretroLocale.values.keys.toSet(), AppLocale.supportedLanguages.keys.toSet());
    for (final entry in LibretroLocale.values.entries) {
      for (final setting in azahar.settings) {
        for (final key in <String>[setting.labelKey, ...setting.valueLabelKeys.values]) {
          expect(entry.value[key]?.trim(), isNotEmpty, reason: '${entry.key}:$key');
        }
      }
      // The in-game menu shows the translation of each value's label key,
      // never the raw-value fallback of coreSettings (in English the two
      // can coincide, "Japan", so the key's text is what is compared).
      // Contract change (docs/libretro-3ds-system-settings.md § 6.4, item
      // 9): the model needs a new session, which "Restart game" does not
      // start, so the in-game menu (footer: "after a restart") no longer
      // offers it; the Nintendo 3DS page still does.
      final translated = LibretroLocale.coreSettings(Locale(entry.key), azahar);
      expect(translated.map((setting) => setting['key']).toList(),
          <String>['citra_region_value', 'citra_language_value', 'citra_use_fastinterp']);
      final inGame = azahar.settings.where((setting) => setting.inGameMenu).toList();
      expect(inGame.length, translated.length);
      for (var index = 0; index < inGame.length; index++) {
        final setting = inGame[index];
        expect(translated[index]['label'], entry.value[setting.labelKey], reason: '${entry.key}:${setting.key}');
        for (final value in translated[index]['values'] as List<Map<String, String>>) {
          final labelKey = setting.valueLabelKeys[value['value']]!;
          expect(value['label'], entry.value[labelKey], reason: '${entry.key}:${value['value']}');
        }
      }
    }
  });

  test('default core comes first, alternatives follow', () {
    expect(LibretroCoreCatalog.coresFor('md').map((core) => core.id).toList(),
        <String>['genesis_plus_gx', 'genesis_plus_gx_wide', 'picodrive']);
    expect(LibretroCoreCatalog.coresFor('ps1').first.biosAnyOf, isNotEmpty);
    expect(LibretroCoreCatalog.coresFor('3ds').single.preferredHardwareContext,
        LibretroHardwareContext.vulkan);
  });

  test('cores that generate machine code fall back to interpreters without JIT', () {
    final cores = LibretroCoreCatalog.cores;
    // Both JITs are compiled off in the official iOS alpha. The packaging
    // check pins that binary and rejects the removed JIT option keys.
    expect(cores['azahar']!.noJitOverrides, isEmpty);
    expect(cores['azahar']!.optionDefaults['citra_use_fastinterp'], 'enabled');
    final fast = cores['azahar']!.settings.singleWhere(
      (setting) => setting.key == 'citra_use_fastinterp',
    );
    expect(fast.inGameMenu, isTrue);
    expect(fast.values, <String>['enabled', 'disabled']);
    expect(cores['azahar']!.lockedOptions.containsKey(fast.key), isFalse);
    expect(cores['mupen64plus_next']!.noJitOverrides,
        <String, String>{'mupen64plus-cpucore': 'cached_interpreter'});
    expect(cores['ppsspp']!.noJitOverrides, <String, String>{'ppsspp_cpu_core': 'IR JIT'});
    expect(cores['desmume']!.noJitOverrides, <String, String>{'desmume_cpu_mode': 'interpreter'});
  });
}
