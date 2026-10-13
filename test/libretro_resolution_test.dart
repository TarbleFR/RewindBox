// Internal resolution of the embedded libretro engine (Build 455,
// docs/libretro-resolution.md): how NeoStation reads the values of a core's
// resolution option, the rules it sends to the native session, the pinned
// cores' declarations, and the console settings' service (reading what the
// core declared at its last launch, falling back on the catalog, saving the
// value for every game of the core only outside a game). The Objective-C
// reader must agree on test/fixtures/libretro_resolution/value_cases.json
// (test/libretro_host/host_test.m). All roots are temporary folders.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/services/libretro_core_option_store.dart';
import 'package:neostation/services/libretro_resolution.dart';
import 'package:neostation/services/libretro_resolution_service.dart';
import 'package:path/path.dart' as p;

Map<String, Object?> _fixture(String name) =>
    jsonDecode(File('test/fixtures/libretro_resolution/$name').readAsStringSync()) as Map<String, Object?>;

List<int>? _ints(Object? value) => value is List ? value.cast<num>().map((number) => number.toInt()).toList() : null;

void main() {
  group('values', () {
    final cases = _fixture('value_cases.json');

    test('every token of the shared cases reads the same in Dart', () {
      for (final entry in (cases['tokens'] as List).cast<Map<String, Object?>>()) {
        final value = entry['value'] as String;
        final expected = entry['expected'] as Map<String, Object?>?;
        final token = LibretroResolution.token(value);
        if (expected == null) {
          expect(token, isNull, reason: value);
        } else if (expected.containsKey('factor')) {
          expect(token?.isSize, isFalse, reason: value);
          expect(token?.factor, (expected['factor'] as num).toDouble(), reason: value);
        } else {
          expect(token?.isSize, isTrue, reason: value);
          expect(<int?>[token?.width, token?.height], <int>[expected['width'] as int, expected['height'] as int],
              reason: value);
        }
      }
    });

    test('every choice list of the shared cases is the same in Dart', () {
      for (final entry in (cases['choices'] as List).cast<Map<String, Object?>>()) {
        final choices = LibretroResolution.choices(
          (entry['values'] as List).cast<String>(),
          labels: (entry['labels'] as List?)?.cast<String>(),
          nativeSize: _ints(entry['nativeSize']),
          consoleSize: _ints(entry['consoleSize']),
          maxFactor: (entry['maxFactor'] as num?)?.toDouble() ?? 0,
          maxDimension: (entry['maxDimension'] as num?)?.toInt() ?? LibretroResolution.maxDimension,
        );
        final expected = <LibretroResolutionChoice>[
          for (final choice in (entry['expected'] as List).cast<Map<String, Object?>>())
            LibretroResolutionChoice(
              value: choice['value'] as String,
              factor: (choice['factor'] as num).toDouble(),
              width: (choice['width'] as int?) ?? 0,
              height: (choice['height'] as int?) ?? 0,
            ),
        ];
        expect(choices, expected, reason: entry['name'] as String);
      }
    });

    test('factors read in the language of the menu', () {
      expect(LibretroResolution.factorText(2, 'en'), '2');
      expect(LibretroResolution.factorText(4.5, 'en'), '4.5');
      expect(LibretroResolution.factorText(4.5, 'fr'), '4,5');
      expect(LibretroResolution.factorText(1.25, 'de'), '1,25');
      expect(LibretroResolution.factorText(4.5, 'zh_Hant'), '4.5');
      expect(LibretroResolution.factorText(3.0, 'ja'), '3');
    });
  });

  group('rules', () {
    test('the native session gets exactly the rules of the fixture both readers use', () {
      expect(
        jsonDecode(jsonEncode(LibretroResolution.nativeRules())),
        _fixture('native_rules.json'),
        reason: 'regenerate test/fixtures/libretro_resolution/native_rules.json from LibretroResolution.nativeRules()',
      );
    });

    test('profiles: a key named twice only for other configurations, the first being the default one', () {
      final seen = <String, LibretroResolutionProfile>{};
      for (final profile in LibretroResolution.profiles) {
        expect(profile.keys, isNotEmpty);
        for (final key in profile.keys) {
          final first = seen[key];
          if (first == null) {
            seen[key] = profile;
          } else {
            // Its own conditions: other option values, or other renderers.
            expect(profile.requires.isNotEmpty || profile.renderers.isNotEmpty, isTrue,
                reason: '$key: a second profile needs its own conditions');
            expect(
              jsonEncode(profile.requires) != jsonEncode(first.requires) ||
                  jsonEncode(profile.renderers) != jsonEncode(first.renderers),
              isTrue,
              reason: key,
            );
          }
          for (final renderer in profile.renderers) {
            expect(
              <String>[
                LibretroResolutionRenderer.gles,
                LibretroResolutionRenderer.vulkan,
                LibretroResolutionRenderer.software,
              ],
              contains(renderer),
              reason: key,
            );
          }
          expect(LibretroResolution.profileFor(key), same(seen[key]));
        }
        expect(profile.maxFactor, greaterThanOrEqualTo(0));
        final native = profile.nativeSize;
        if (native != null) {
          expect(native, hasLength(2));
          expect(native.every((side) => side > 0), isTrue);
        }
      }
      expect(LibretroResolution.profileFor('not_a_resolution'), isNull);
    });

    test('live only where the core redraws during the game; next launch otherwise', () {
      LibretroResolutionApply apply(String key) => LibretroResolution.profileFor(key)!.apply;
      // Sources: docs/libretro-resolution.md § 2.
      expect(apply('citra_resolution_factor'), LibretroResolutionApply.live);
      expect(apply('desmume_internal_resolution'), LibretroResolutionApply.live);
      expect(apply('beetle_psx_hw_internal_resolution'), LibretroResolutionApply.live);
      expect(apply('beetle_psx_internal_resolution'), LibretroResolutionApply.live);
      expect(apply('ppsspp_internal_resolution'), LibretroResolutionApply.live);
      expect(apply('mupen64plus-43screensize'), LibretroResolutionApply.relaunch);
      expect(apply('mupen64plus-parallel-rdp-upscaling'), LibretroResolutionApply.relaunch);
      // PPSSPP with Vulkan and Beetle's Vulkan renderer: next launch.
      final vulkan = LibretroResolution.profiles.where((profile) =>
          profile.keys.contains('ppsspp_internal_resolution') &&
          profile.requires['ppsspp_backend']?.contains('vulkan') == true);
      expect(vulkan.single.apply, LibretroResolutionApply.relaunch);
      final beetleVulkan = LibretroResolution.profiles.where((profile) =>
          profile.requires['beetle_psx_hw_renderer']?.contains('hardware_vk') == true);
      expect(beetleVulkan.single.apply, LibretroResolutionApply.relaunch);
      // Cores NeoStation does not package: always the next launch.
      for (final key in <String>['reicast_internal_resolution', 'dolphin_efb_scale', 'play_res_multi']) {
        expect(apply(key), LibretroResolutionApply.relaunch, reason: key);
      }
    });

    test('renderers: each live profile names the renderers its source was read for', () {
      List<LibretroResolutionProfile> named(String key) =>
          LibretroResolution.profiles.where((profile) => profile.keys.contains(key)).toList();
      // PPSSPP: live only with an OpenGL ES context. In its own software
      // context (no hardware context from the frontend) the frames stay
      // 480x272, and a change during the game makes check_variables call
      // ContextReset on that software context: nothing is offered then.
      final ppsspp = named('ppsspp_internal_resolution');
      expect(ppsspp.map((profile) => profile.renderers), <List<String>>[
        <String>[LibretroResolutionRenderer.gles],
        <String>[LibretroResolutionRenderer.vulkan],
      ]);
      expect(ppsspp.map((profile) => profile.apply),
          <LibretroResolutionApply>[LibretroResolutionApply.live, LibretroResolutionApply.relaunch]);
      for (final profile in ppsspp) {
        expect(profile.renderers, isNot(contains(LibretroResolutionRenderer.software)));
      }
      // Beetle PSX: live with OpenGL ES or its software renderer, next
      // launch with Vulkan.
      final beetle = named('beetle_psx_hw_internal_resolution');
      expect(beetle.first.renderers,
          <String>[LibretroResolutionRenderer.gles, LibretroResolutionRenderer.software]);
      expect(beetle.last.renderers, <String>[LibretroResolutionRenderer.vulkan]);
      expect(beetle.last.apply, LibretroResolutionApply.relaunch);
      // Azahar draws with a GPU renderer only; DeSmuME's rasterizer is
      // software: no renderer condition.
      expect(named('citra_resolution_factor').single.renderers, isNot(contains(LibretroResolutionRenderer.software)));
      expect(named('desmume_internal_resolution').single.renderers, isEmpty);
      expect(named('mupen64plus-43screensize').single.renderers, <String>[LibretroResolutionRenderer.gles]);
      // Sent to the native session only when set.
      expect(named('desmume_internal_resolution').single.toNative().containsKey('renderers'), isFalse);
      expect(ppsspp.first.toNative()['renderers'], <String>[LibretroResolutionRenderer.gles]);
    });

    test('generic patterns recognize resolution options of cores without a profile', () {
      final keyPattern = RegExp(LibretroResolution.genericKeyPattern, caseSensitive: false);
      final descriptionPattern = RegExp(LibretroResolution.genericDescriptionPattern, caseSensitive: false);
      for (final key in <String>[
        'flycast_internal_resolution',
        'melonds_render_scale',
        'dolphin_efb_scale',
        'swanstation_GPU_ResolutionScale',
        'play_res_multi',
        'pcsx2_upscale_multiplier',
        'citra_resolution_factor',
      ]) {
        expect(keyPattern.hasMatch(key), isTrue, reason: key);
      }
      for (final key in <String>['snes9x_hires_blend', 'genesis_plus_gx_render', 'mgba_frameskip', 'fbneo-cpu-speed-adjust']) {
        expect(keyPattern.hasMatch(key), isFalse, reason: key);
      }
      expect(descriptionPattern.hasMatch('Internal GPU Resolution'), isTrue);
      expect(descriptionPattern.hasMatch('Rendering Resolution'), isTrue);
      expect(descriptionPattern.hasMatch('Frameskip'), isFalse);
    });
  });

  group('catalog', () {
    // Build 455 (docs/libretro-resolution.md § 3): the internal resolution of
    // each pinned core as its binary declares it
    // (test/libretro_core_options_test.py --cores), and the values offered.
    const expected = <String, List<double>>{
      'desmume': <double>[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      'mupen64plus_next': <double>[1, 2, 3, 4, 4.5, 5, 6],
      'mednafen_psx_hw': <double>[1, 2, 4, 8],
      'mednafen_psx': <double>[1, 2, 4, 8],
      'ppsspp': <double>[1, 2, 3, 4, 5],
      'azahar': <double>[1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
    };

    test('the 3D cores declare an internal resolution, the 2D cores none', () {
      final declared = <String>{
        for (final core in LibretroCoreCatalog.cores.values)
          if (core.resolution != null) core.id,
      };
      expect(declared, expected.keys.toSet());
      for (final id in <String>['nestopia', 'snes9x', 'gambatte', 'mgba', 'genesis_plus_gx', 'genesis_plus_gx_wide',
        'picodrive', 'fbneo']) {
        expect(LibretroCoreCatalog.cores[id]!.resolution, isNull, reason: id);
      }
    });

    test('each declaration offers native first and only the factors NeoStation allows', () {
      for (final entry in expected.entries) {
        final core = LibretroCoreCatalog.cores[entry.key]!;
        final declaration = core.resolution!;
        final profile = LibretroResolution.profileFor(declaration.key);
        expect(profile, isNotNull, reason: declaration.key);
        expect(declaration.values, contains(declaration.coreDefault), reason: core.id);
        final console = LibretroCoreCatalog.consoles[
            LibretroCoreCatalog.systems.values.firstWhere((binding) =>
                binding.coreId == core.id || binding.alternatives.contains(core.id)).console]!;
        final choices = LibretroResolution.choices(
          declaration.values,
          nativeSize: profile!.nativeSize,
          consoleSize: <int>[console.width, console.height],
          maxFactor: profile.maxFactor,
        );
        expect(choices.map((choice) => choice.factor).toList(), entry.value, reason: core.id);
        expect(choices.first.isNative, isTrue, reason: core.id);
        // Native by default: no NeoStation default above it.
        expect(core.optionDefaults.containsKey(declaration.key), isFalse, reason: core.id);
      }
    });

    test('the curated resolution settings gave way to the resolution page', () {
      for (final core in LibretroCoreCatalog.cores.values) {
        for (final setting in core.settings) {
          expect(setting.labelKey, isNot('settingResolution'), reason: '${core.id} ${setting.key}');
        }
      }
    });
  });

  group('service', () {
    late Directory root;
    late Directory config;
    var active = false;

    setUp(() async {
      root = await Directory.systemTemp.createTemp('neostation-resolution-');
      config = Directory(p.join(root.path, 'Config'));
      await config.create(recursive: true);
      active = false;
    });

    tearDown(() async {
      if (await root.exists()) await root.delete(recursive: true);
    });

    LibretroResolutionService service() => LibretroResolutionService(
          configDirectory: () async => config,
          store: LibretroCoreOptionStore(configDirectory: () async => config, sessionProbe: () async => active),
        );

    Future<void> writeJson(String relative, Object value) async {
      final file = File(p.join(config.path, relative));
      await file.parent.create(recursive: true);
      await file.writeAsString(jsonEncode(value));
    }

    test('cores of a console: the default cores first, alternatives after, once each', () {
      expect(LibretroResolutionService.coresForConsole('psx').map((core) => core.id),
          <String>['mednafen_psx_hw', 'mednafen_psx']);
      // PicoDrive is the default core of the Pico system, a Mega Drive one.
      expect(LibretroResolutionService.coresForConsole('md').map((core) => core.id),
          <String>['genesis_plus_gx', 'picodrive', 'genesis_plus_gx_wide']);
      expect(LibretroResolutionService.isDefaultFor(LibretroCoreCatalog.cores['picodrive']!, 'md'), isTrue);
      expect(LibretroResolutionService.isDefaultFor(LibretroCoreCatalog.cores['mednafen_psx']!, 'psx'), isFalse);
      expect(LibretroResolutionService.coresForConsole('psp').map((core) => core.id), <String>['ppsspp']);
      expect(LibretroResolutionService.coresForConsole('unknown'), isEmpty);
    });

    test('a 2D core is explained, not offered, and nothing can be saved for it', () async {
      final snes = await service().forCore(LibretroCoreCatalog.cores['snes9x']!, console: 'snes');
      expect(snes.supported, isFalse);
      expect(snes.key, isNull);
      expect(snes.current, isNull);
      await expectLater(service().setValue(snes, '2x'), throwsArgumentError);
      expect(config.listSync(), isEmpty);
    });

    test('what the core declared at its last launch wins over the catalog', () async {
      final ppsspp = LibretroCoreCatalog.cores['ppsspp']!;
      await writeJson('Resolution/ppsspp.json', <String, Object?>{
        'version': 1,
        'coreId': 'ppsspp',
        'libraryName': 'PPSSPP',
        'libraryVersion': 'test',
        'internalResolution': <String, Object?>{
          'key': 'ppsspp_internal_resolution',
          'apply': 'live',
          'source': 'profile',
          'coreDefault': '480x272',
          'native': '480x272',
          'choices': <Object>[
            <String, Object>{'value': '960x544', 'factor': 2, 'width': 960, 'height': 544},
            <String, Object>{'value': '480x272', 'factor': 1, 'width': 480, 'height': 272},
          ],
        },
      });
      final resolution = await service().forCore(ppsspp, console: 'psp');
      expect(resolution.detected, isTrue);
      expect(resolution.supported, isTrue);
      expect(resolution.libraryName, 'PPSSPP');
      expect(resolution.choices.map((choice) => choice.value), <String>['480x272', '960x544']);
      expect(resolution.apply, LibretroResolutionApply.live);
      expect(resolution.current, '480x272', reason: 'native by default');
    });

    test('a core that declared no internal resolution at its last launch is explained', () async {
      final ppsspp = LibretroCoreCatalog.cores['ppsspp']!;
      await writeJson('Resolution/ppsspp.json', <String, Object?>{
        'version': 1,
        'coreId': 'ppsspp',
        'libraryName': 'PPSSPP',
        'internalResolution': null,
      });
      final resolution = await service().forCore(ppsspp, console: 'psp');
      expect(resolution.detected, isTrue);
      expect(resolution.supported, isFalse);
      expect(resolution.inapplicableKey, isNull);
    });

    test('an option that did not apply to the way the core drew is told apart', () async {
      // PPSSPP in its software context: the session found the option but
      // offered nothing (Config/Resolution/ppsspp.json, Build 455).
      final ppsspp = LibretroCoreCatalog.cores['ppsspp']!;
      await writeJson('Resolution/ppsspp.json', <String, Object?>{
        'version': 1,
        'coreId': 'ppsspp',
        'libraryName': 'PPSSPP',
        'renderer': 'software',
        'internalResolution': null,
        'inapplicableKey': 'ppsspp_internal_resolution',
      });
      final resolution = await service().forCore(ppsspp, console: 'psp');
      expect(resolution.detected, isTrue);
      expect(resolution.supported, isFalse);
      expect(resolution.inapplicableKey, 'ppsspp_internal_resolution');
      await expectLater(service().setValue(resolution, '960x544'), throwsArgumentError);
      expect(File(p.join(config.path, 'PPSSPP.json')).existsSync(), isFalse);
    });

    test('a snapshot of another core or without a library name is ignored', () async {
      final ppsspp = LibretroCoreCatalog.cores['ppsspp']!;
      await writeJson('Resolution/ppsspp.json', <String, Object?>{'coreId': 'azahar', 'libraryName': 'Azahar'});
      expect((await service().forCore(ppsspp, console: 'psp')).detected, isFalse);
      await writeJson('Resolution/ppsspp.json', <String, Object?>{'coreId': 'ppsspp'});
      expect((await service().forCore(ppsspp, console: 'psp')).detected, isFalse);
      await File(p.join(config.path, 'Resolution/ppsspp.json')).writeAsString('{not json');
      expect((await service().forCore(ppsspp, console: 'psp')).detected, isFalse);
    });

    test('saving writes the value for every game, keeps the other options and the games of their own', () async {
      final ppsspp = LibretroCoreCatalog.cores['ppsspp']!;
      await writeJson('PPSSPP.json', <String, Object?>{
        'values': <String, String>{'ppsspp_cpu_core': 'IR JIT'},
      });
      await writeJson('Games/PPSSPP.json', <String, Object?>{
        'version': 1,
        'games': <String, Object?>{
          'psp/A.iso': <String, String>{'ppsspp_internal_resolution': '1440x816'},
          'psp/B.iso': <String, String>{'ppsspp_internal_resolution': '480x272'},
          'psp/C.iso': <String, String>{'other': 'x'},
        },
      });
      final before = File(p.join(config.path, 'Games/PPSSPP.json')).readAsStringSync();
      var resolution = await service().forCore(ppsspp, console: 'psp');
      expect(resolution.supported, isTrue);
      expect(resolution.gamesWithOwnValue, 2);
      final twice = resolution.choices.firstWhere((choice) => choice.factor == 2);
      await service().setValue(resolution, twice.value);
      final stored = LibretroCoreOptionStore.decode(File(p.join(config.path, 'PPSSPP.json')).readAsStringSync());
      expect(stored, <String, String>{'ppsspp_cpu_core': 'IR JIT', 'ppsspp_internal_resolution': twice.value});
      resolution = await service().forCore(ppsspp, console: 'psp');
      expect(resolution.stored, twice.value);
      expect(resolution.current, twice.value);
      expect(File(p.join(config.path, 'Games/PPSSPP.json')).readAsStringSync(), before,
          reason: 'a game of its own keeps its resolution');
    });

    test('saving is refused while a game runs and writes nothing', () async {
      final ppsspp = LibretroCoreCatalog.cores['ppsspp']!;
      final resolution = await service().forCore(ppsspp, console: 'psp');
      active = true;
      await expectLater(
        service().setValue(resolution, resolution.choices.last.value),
        throwsA(isA<LibretroCoreOptionStoreException>()),
      );
      expect(File(p.join(config.path, 'PPSSPP.json')).existsSync(), isFalse);
    });

    test('a value the core does not offer is refused', () async {
      final ppsspp = LibretroCoreCatalog.cores['ppsspp']!;
      final resolution = await service().forCore(ppsspp, console: 'psp');
      await expectLater(service().setValue(resolution, '123x45'), throwsArgumentError);
      expect(File(p.join(config.path, 'PPSSPP.json')).existsSync(), isFalse);
    });
  });
}
