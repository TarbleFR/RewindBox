import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/enhancements_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/enhancements/adapters/beetle_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/console_catalog.dart';
import 'package:neostation/services/embedded_engine_policy.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/services/libretro_core_option_store.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

import 'enhancement_test_support.dart';

/// Option keys (without the core's prefix) and values the presets use, as
/// the pinned core declares them: libretro_core_options.h of
/// libretro/beetle-psx-libretro at 10e4b0c6 (native/beetle-psx/source.json),
/// whose libretro.c has the pinned SHA-256. A value the core does not offer
/// is ignored by the host without a word. mdec_yuv is declared only with
/// HAVE_VULKAN, which HAVE_HW=1 turns on (Beetle PSX HW).
final _pinned = <String, List<String>>{
  'widescreen_hack': ['disabled', 'enabled'],
  'widescreen_hack_aspect_ratio': ['16:9', '16:10', '18:9', '19:9', '20:9', '21:9', '32:9'],
  'pgxp_mode': ['disabled', 'memory only', 'memory + CPU'],
  'pgxp_texture': ['disabled', 'enabled'],
  'mdec_yuv': ['disabled', 'enabled'],
  'gte_overclock': ['disabled', 'enabled'],
  'cpu_freq_scale': [for (var percent = 50; percent <= 750; percent += 10) '$percent%'],
};
const _hardwareOnly = {'mdec_yuv'};

/// A PS1 data track: ISO 9660 with SYSTEM.CNF in its root directory, in
/// raw 2352-byte MODE2 sectors (user data at 24) or 2048-byte ones.
Uint8List _track(String systemCnf, {int stride = 2352, int offset = 24}) {
  final bytes = Uint8List(24 * stride);
  void put(int sector, List<int> data) => bytes.setAll(sector * stride + offset, data);
  final volume = Uint8List(2048)
    ..[0] = 1
    ..setAll(1, 'CD001'.codeUnits);
  ByteData.sublistView(volume)
    ..setUint32(156 + 2, 22, Endian.little)
    ..setUint32(156 + 10, 2048, Endian.little);
  put(16, volume);
  final directory = Uint8List(2048);
  var at = 0;
  void record(List<int> name, int extent, int size, {bool folder = false}) {
    final length = 33 + name.length + (name.length.isEven ? 1 : 0);
    directory[at] = length;
    ByteData.sublistView(directory)
      ..setUint32(at + 2, extent, Endian.little)
      ..setUint32(at + 10, size, Endian.little);
    directory[at + 25] = folder ? 2 : 0;
    directory[at + 32] = name.length;
    directory.setAll(at + 33, name);
    at += length;
  }

  record([0], 22, 2048, folder: true);
  record([1], 22, 2048, folder: true);
  record('SYSTEM.CNF;1'.codeUnits, 23, systemCnf.length);
  put(22, directory);
  put(23, systemCnf.codeUnits);
  return bytes;
}

const _crashCnf = 'BOOT = cdrom:\\SCUS_944.26;1\r\nTCB = 4\r\nEVENT = 10\r\nSTACK = 801FFFF0\r\n';

void main() {
  late Directory temp;
  late Directory config;
  late Directory roms;
  late bool session;
  late String? choice;
  late bool embedded;
  late List<String> routed;

  BeetleEnhancementAdapter adapter() => BeetleEnhancementAdapter(
    configDirectory: () async => config,
    sessionActive: () async => session,
    coreChoice: (system, romname) async {
      expect(system, 'ps1', reason: 'the per-game core choice is kept under the libretro system key');
      return choice;
    },
    runsEmbedded: (game, coreId) async {
      routed.add(coreId);
      return embedded;
    },
  );

  EnhancementService service() => EnhancementService(
    catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), const {}),
    store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
    adapters: [adapter()],
    texturesSupported: (_) => true,
    embeddedEngines: () => true,
  );

  String rom(String name, List<int> bytes) {
    final file = File(path.join(roms.path, name))..writeAsBytesSync(bytes);
    return file.path;
  }

  String text(String name, String content) => rom(name, utf8.encode(content));

  /// Crash Bandicoot as a CUE and its BIN, as a library row passes it.
  GameModel crash() {
    rom('Crash.bin', _track(_crashCnf));
    return testGame(name: 'Crash Bandicoot', romPath: text('Crash.cue', 'FILE "Crash.bin" BINARY\n  TRACK 01 MODE2/2352\n'));
  }

  File options(String library) => File(path.join(config.path, 'Games', '$library.json'));
  Map<String, dynamic>? json(String library) =>
      options(library).existsSync() ? jsonDecode(options(library).readAsStringSync()) as Map<String, dynamic> : null;
  Map<String, dynamic> values(String library, [String key = 'ps1/Crash.cue']) =>
      Map<String, dynamic>.from(((json(library)?['games'] as Map?)?[key] as Map?) ?? const {});
  void seed(String library, Map<String, dynamic> document) {
    options(library).parent.createSync(recursive: true);
    options(library).writeAsStringSync(jsonEncode(document));
  }

  EnhancementItem item(EnhancementGameView view, String id) => view.items.singleWhere((item) => item.id == id);

  setUp(() {
    temp = Directory.systemTemp.createTempSync('enh-beetle-');
    config = Directory(path.join(temp.path, 'Libretro', 'Config'))..createSync(recursive: true);
    roms = Directory(path.join(temp.path, 'roms'))..createSync();
    session = false;
    choice = null;
    embedded = true;
    routed = [];
  });
  tearDown(() => temp.deleteSync(recursive: true));

  group('contract with the cores and the launch', () {
    test('the game key and the cores are those the launch and the options store use', () {
      final binding = LibretroCoreCatalog.bindingFor(BeetleEnhancementAdapter.libretroSystem)!;
      expect(binding.coreId, 'mednafen_psx_hw');
      expect(binding.alternatives, ['mednafen_psx']);
      expect(BeetleEnhancementAdapter.cores.map((core) => core.id), [binding.coreId, ...binding.alternatives]);
      // LibretroInternalService.launch: '$systemKey/${game.romname}', with the PS1 system's own id.
      expect(LibretroCoreCatalog.canonicalSystem(id: 'ps1', folders: ['ps1', 'psx'], folderName: 'ps1'), 'ps1');
      expect(BeetleEnhancementAdapter.gameKey('Crash.cue'), 'ps1/Crash.cue');
      for (final core in BeetleEnhancementAdapter.cores) {
        final resolution = LibretroCoreCatalog.cores[core.id]!.resolution!;
        // The binary contract (test/libretro_core_options_test.py --cores) checks this library name.
        expect(resolution.libraryName, core.libraryName, reason: core.id);
        expect(resolution.key, '${core.prefix}internal_resolution', reason: core.id);
        expect(LibretroCoreOptionStore.libraryFileName(core.libraryName), '${core.libraryName}.json');
      }
      expect(BeetleEnhancementAdapter.cores.where((core) => core.hardware).map((core) => core.id), ['mednafen_psx_hw']);
    });

    test('every option and value is one the pinned core declares', () {
      for (final preset in BeetleEnhancementAdapter.presets) {
        for (final option in preset.options.entries) {
          expect(_pinned[option.key], contains(option.value), reason: '${preset.id}: ${option.key}');
        }
        expect(preset.hardwareOnly, preset.options.keys.any(_hardwareOnly.contains), reason: preset.id);
      }
    });

    test('no preset sets an option another service or the session owns', () {
      for (final core in BeetleEnhancementAdapter.cores) {
        final catalog = LibretroCoreCatalog.cores[core.id]!;
        final owned = {
          catalog.resolution!.key, // LibretroResolutionService and the in-game Resolution page
          ...catalog.lockedOptions.keys,
          ...catalog.optionDefaults.keys,
          ...catalog.noJitOverrides.keys,
          ...catalog.jitOverrides.keys,
          // HD textures page (NeoTextureBeetle), and the Vulkan format locks of the session.
          for (final option in ['track_textures', 'replace_textures', 'dump_textures', 'dither_mode', 'display_vram'])
            '${core.prefix}$option',
        };
        for (final preset in BeetleEnhancementAdapter.presets) {
          for (final option in preset.options.keys) {
            expect(owned, isNot(contains('${core.prefix}$option')), reason: preset.id);
          }
        }
      }
    });

    test('ids are stable, and presets setting one option are alternatives of one group', () {
      expect(BeetleEnhancementAdapter.presets.map((preset) => preset.id), [
        'beetle-widescreen-16-9',
        'beetle-pgxp-geometry',
        'beetle-pgxp-textures',
        'beetle-mdec-chroma',
        'beetle-gte-overclock',
        'beetle-cpu-150',
        'beetle-cpu-200',
      ]);
      final presets = BeetleEnhancementAdapter.presets;
      for (final a in presets) {
        expect(a.name, isNotEmpty);
        expect(a.description.length, inInclusiveRange(80, 400), reason: a.id);
        // RewindBox's own text: every language of the page has it, translated.
        for (final locale in EnhancementsLocale.values.entries) {
          expect(locale.value[a.nameKey], isNotEmpty, reason: '${locale.key} ${a.id}');
          if (locale.key == 'en') continue;
          expect(locale.value[a.descriptionKey], isNot(a.description), reason: '${locale.key} ${a.id}');
        }
        for (final b in presets) {
          if (identical(a, b)) continue;
          final shared = a.options.keys.toSet().intersection(b.options.keys.toSet());
          if (shared.isEmpty) continue;
          expect(a.group, isNotEmpty, reason: '${a.id} and ${b.id} set $shared');
          expect(a.group, b.group, reason: '${a.id} and ${b.id} set $shared');
          // Never both in effect: they differ on a value they share.
          expect(shared.any((option) => a.options[option] != b.options[option]), isTrue, reason: '${a.id} ${b.id}');
        }
      }
      expect({for (final preset in presets) preset.category}, {
        EnhancementCategory.ultrawide,
        EnhancementCategory.graphics,
        EnhancementCategory.performance,
      });
    });

    test('the default service offers the presets for the PS1 folders', () {
      final defaults = EnhancementService(texturesSupported: (_) => false, embeddedEngines: () => true);
      for (final folder in ['ps1', 'PSX', 'playstation']) {
        expect(defaults.adapterFor(folder), isA<BeetleEnhancementAdapter>(), reason: folder);
        expect(defaults.supports(folder), isTrue);
      }
      expect(defaults.adapterFor('ps2'), isNot(isA<BeetleEnhancementAdapter>()));
      expect(defaults.adapterForEngine('beetle'), isA<BeetleEnhancementAdapter>());
    });
  });

  group('identity', () {
    test('the options key of the game file, its serial for the compatibility line', () async {
      final game = crash();
      final identity = await adapter().identify(game, 'ps1');
      expect(identity.known, isTrue);
      expect(identity.engine, EnhancementEngine.beetle);
      expect(identity.key, 'ps1/Crash.cue');
      expect(identity.title, 'Crash Bandicoot');
      expect(identity.storeKey, 'beetle:ps1/Crash.cue');
      final view = await service().open(game, 'ps1');
      expect(view.items.map((item) => item.compatibility), everyElement(startsWith('SCUS-94426 · Beetle PSX HW')));
    });

    test('a game without a file name has no identity', () async {
      final identity = await adapter().identify(testGame(name: ''), 'ps1');
      expect(identity.known, isFalse);
      expect(identity.problem, EnhancementProblem.identityUnavailable);
    });

    test('SYSTEM.CNF of BIN, ISO, CUE, CCD and M3U; none from CHD, nested paths or PS2 discs', () async {
      rom('Disc.bin', _track(_crashCnf));
      rom('Cooked.iso', _track('BOOT=cdrom:SLUS_010.40;1\n', stride: 2048, offset: 0));
      rom('Clone.img', _track('BOOT = cdrom:\\SLES_123.45;1\n'));
      rom('Ps2.bin', _track('BOOT2 = cdrom0:\\SLUS_210.50;1\n'));
      final cue = text('Disc.cue', 'FILE "Disc.bin" BINARY\n  TRACK 01 MODE2/2352\n');
      Future<String?> serial(String file) => BeetleEnhancementAdapter.readSerial(file);
      expect(await serial(path.join(roms.path, 'Disc.bin')), 'SCUS-94426');
      expect(await serial(path.join(roms.path, 'Cooked.iso')), 'SLUS-01040');
      expect(await serial(cue), 'SCUS-94426');
      expect(await serial(text('Clone.ccd', '[CloneCD]\nVersion=3\n')), 'SLES-12345');
      expect(await serial(text('Multi.m3u', '# discs\n\nDisc.cue\nOther.cue\n')), 'SCUS-94426');
      expect(await serial(text('Loop.m3u', 'Multi.m3u\n')), isNull, reason: 'no nested playlist');
      expect(await serial(text('Far.cue', 'FILE "sub/Disc.bin" BINARY\n')), isNull, reason: 'same folder only');
      expect(await serial(rom('Game.chd', List.filled(4096, 7))), isNull);
      expect(await serial(path.join(roms.path, 'Ps2.bin')), isNull);
      expect(await serial(path.join(roms.path, 'Missing.bin')), isNull);
      expect(BeetleEnhancementAdapter.serialFromSystemCnf('BOOT = cdrom:PSX.EXE;1'), isNull);
      expect(BeetleEnhancementAdapter.serialFromSystemCnf('boot=cdrom:\\DATA\\SCES_000.01;1 arg'), 'SCES-00001');
    });
  });

  group('page', () {
    test('every preset is listed, nothing to install or download', () async {
      final view = await service().open(crash(), 'ps1');
      expect(view.identity.known, isTrue);
      expect(view.downloaded, isTrue);
      expect(view.installed, isFalse, reason: 'nothing of RewindBox\'s yet; the page offers no Install for these');
      expect(view.items, hasLength(BeetleEnhancementAdapter.presets.length));
      expect(view.items.map((item) => item.status), everyElement(EnhancementStatus.available));
      expect(view.countIn(EnhancementCategory.ultrawide), 1);
      expect(view.countIn(EnhancementCategory.graphics), 3);
      expect(view.countIn(EnhancementCategory.performance), 3);
      expect(item(view, 'beetle-cpu-150').exclusiveGroup, item(view, 'beetle-cpu-200').exclusiveGroup);
      expect(item(view, 'beetle-mdec-chroma').compatibility, endsWith('Beetle PSX HW (Vulkan)'));
      expect(options('Beetle PSX HW').existsSync(), isFalse, reason: 'opening writes nothing');
      // The page names RewindBox's own text in its language from these keys.
      final widescreen = item(view, 'beetle-widescreen-16-9');
      expect(widescreen.name, EnhancementsLocale.values['en']![EnhancementsLocale.beetleWidescreen]);
      expect(widescreen.payload, {
        'nameKey': EnhancementsLocale.beetleWidescreen,
        'descriptionKey': EnhancementsLocale.beetleWidescreenNote,
        'sourceKey': EnhancementsLocale.beetleSource,
        'serial': 'SCUS-94426',
        'coresKey': EnhancementsLocale.beetleBothCores,
      });
    });

    test('a game set to Beetle PSX cannot take a Vulkan-only option; one set elsewhere takes none', () async {
      choice = 'mednafen_psx';
      var view = await service().open(crash(), 'ps1');
      expect(item(view, 'beetle-mdec-chroma').status, EnhancementStatus.incompatible);
      expect(item(view, 'beetle-mdec-chroma').problem, EnhancementProblem.none);
      expect(item(view, 'beetle-mdec-chroma').compatibility, startsWith('Set to Beetle PSX'));
      String french(String key) => EnhancementsLocale.values['fr']![key]!;
      expect(
        BeetleEnhancementAdapter.compatibilityOf(item(view, 'beetle-mdec-chroma').payload, text: french),
        'Réglé sur Beetle PSX, qui n\'a pas cette option · SCUS-94426 · Beetle PSX HW (Vulkan)',
      );
      expect(item(view, 'beetle-gte-overclock').status, EnhancementStatus.available);
      choice = 'retroarch';
      view = await service().open(crash(), 'ps1');
      expect(view.items.map((item) => item.status), everyElement(EnhancementStatus.incompatible));
      expect(view.items.map((item) => item.payload['reasonKey']), everyElement(EnhancementsLocale.beetleOtherCore));
      choice = 'not_a_core';
      view = await service().open(crash(), 'ps1');
      expect(item(view, 'beetle-mdec-chroma').status, EnhancementStatus.available, reason: 'the default core runs it');
    });

    test('a game the launch sends to the RetroArch app takes none; what RewindBox wrote stays restorable', () async {
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-gte-overclock'), true);
      // Built-in engine off, file not readable here or core missing: the RetroArch app runs it.
      embedded = false;
      choice = 'mednafen_psx';
      routed.clear();
      view = await enhancements.open(game, 'ps1');
      expect(routed, ['mednafen_psx'], reason: 'asked for the core the game is set to');
      expect(view.items.map((item) => item.status), everyElement(EnhancementStatus.incompatible));
      expect(view.items.map((item) => item.payload['reasonKey']), everyElement(EnhancementsLocale.beetleRetroArchRoute));
      expect(view.items.where((item) => item.payload.containsKey('problemKey')), isEmpty);
      expect(item(view, 'beetle-gte-overclock').compatibility, startsWith('Opens in the RetroArch app'));
      await expectLater(
        enhancements.setActive(game, 'ps1', view, item(view, 'beetle-cpu-150'), true),
        throwsA(isA<EnhancementException>().having((error) => error.code, 'code', 'incompatible')),
      );
      expect(view.installed, isTrue, reason: 'RewindBox\'s values are still there');
      await enhancements.restore(view.identity.storeKey);
      expect(options('Beetle PSX HW').existsSync(), isFalse);
      expect(options('Beetle PSX').existsSync(), isFalse);
      expect(await enhancements.games(), isEmpty);
    });

    test('the route follows the launch: the console\'s built-in engine, a readable file, a bundled core', () async {
      final game = crash();
      final console = ConsoleCatalog.entryForKey(BeetleEnhancementAdapter.libretroSystem);
      expect(console, isNotNull, reason: 'the PS1 console has its own built-in engine switch');
      Future<bool> route(
        Map<String, Object> preferences, {
        GameModel? of,
        String core = 'mednafen_psx_hw',
        Future<List<String>> Function()? bundled,
      }) {
        SharedPreferences.setMockInitialValues(preferences);
        return BeetleEnhancementAdapter.launchesEmbedded(
          of ?? game,
          core,
          policy: EmbeddedEnginePolicy(preferences: SharedPreferences.getInstance),
          bundledCores: bundled ?? () async => ['mednafen_psx_hw', 'mednafen_psx'],
        );
      }

      expect(await route({}), isTrue);
      expect(await route({}, core: 'mednafen_psx'), isTrue);
      expect(await route({}, bundled: () async => ['mednafen_psx']), isFalse, reason: 'core not in this build');
      expect(await route({}, bundled: () async => throw StateError('no channel')), isFalse);
      expect(await route({EmbeddedEnginePolicy.globalPreferenceKey: false}), isFalse, reason: 'built-in emulators off');
      expect(
        await route({
          EmbeddedEnginePolicy.disabledPreferenceKey: [console!.id],
        }),
        isFalse,
        reason: 'the PS1 engine off',
      );
      expect(await route({}, of: testGame(name: 'Gone', romPath: path.join(roms.path, 'Gone.cue'))), isFalse);
      expect(await route({}, of: testGame(name: 'Nowhere')), isFalse, reason: 'no file');
    });
  });

  group('per-game options', () {
    test('a preset is written for both cores under the game key, beside what is there', () async {
      final players = {
        'version': 1,
        'games': {
          'ps1/Other.cue': {'beetle_psx_hw_widescreen_hack': 'enabled'},
          'ps1/Crash.cue': {'beetle_psx_hw_internal_resolution': '4x'},
        },
        'unknown': {'kept': true},
      };
      seed('Beetle PSX HW', players);
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-widescreen-16-9'), true);
      expect(item(view, 'beetle-widescreen-16-9').status, EnhancementStatus.active);
      expect(values('Beetle PSX HW'), {
        'beetle_psx_hw_internal_resolution': '4x',
        'beetle_psx_hw_widescreen_hack': 'enabled',
        'beetle_psx_hw_widescreen_hack_aspect_ratio': '16:9',
      });
      expect(values('Beetle PSX'), {
        'beetle_psx_widescreen_hack': 'enabled',
        'beetle_psx_widescreen_hack_aspect_ratio': '16:9',
      });
      expect(json('Beetle PSX HW')!['version'], 1);
      expect(json('Beetle PSX HW')!['unknown'], {'kept': true});
      expect(values('Beetle PSX HW', 'ps1/Other.cue'), {'beetle_psx_hw_widescreen_hack': 'enabled'});
      final state = (await enhancements.games()).single;
      expect(state.engine, 'beetle');
      expect(state.active, {'beetle-widescreen-16-9'});
      expect(state.data['created'], ['mednafen_psx'], reason: 'only the file RewindBox made');

      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-widescreen-16-9'), false);
      expect(item(view, 'beetle-widescreen-16-9').status, EnhancementStatus.available);
      expect(json('Beetle PSX HW'), players, reason: 'the entry is as it was');
      expect(options('Beetle PSX').existsSync(), isFalse, reason: 'the file RewindBox created is gone');
      expect(await enhancements.games(), isEmpty, reason: 'nothing of RewindBox is left');
    });

    test('alternatives of one option replace each other; a Vulkan-only option goes to Beetle PSX HW only', () async {
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-cpu-150'), true);
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-cpu-200'), true);
      expect(item(view, 'beetle-cpu-150').status, EnhancementStatus.available);
      expect(item(view, 'beetle-cpu-200').status, EnhancementStatus.active);
      expect(values('Beetle PSX HW'), {'beetle_psx_hw_cpu_freq_scale': '200%'});
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-pgxp-geometry'), true);
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-pgxp-textures'), true);
      expect(item(view, 'beetle-pgxp-geometry').status, EnhancementStatus.available);
      expect(values('Beetle PSX')['beetle_psx_pgxp_texture'], 'enabled');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-mdec-chroma'), true);
      expect(values('Beetle PSX HW')['beetle_psx_hw_mdec_yuv'], 'enabled');
      expect(values('Beetle PSX').keys.where((key) => key.contains('mdec')), isEmpty);
      expect(view.activeCount, 3);

      await enhancements.restore(view.identity.storeKey);
      expect(options('Beetle PSX HW').existsSync(), isFalse);
      expect(options('Beetle PSX').existsSync(), isFalse);
      expect(await enhancements.games(), isEmpty);
    });

    test('a different value of the player\'s is never replaced', () async {
      seed('Beetle PSX', {
        'version': 1,
        'games': {
          'ps1/Crash.cue': {'beetle_psx_cpu_freq_scale': '120%'},
        },
      });
      final before = options('Beetle PSX').readAsBytesSync();
      final game = crash();
      final enhancements = service();
      final view = await enhancements.open(game, 'ps1');
      for (final id in ['beetle-cpu-150', 'beetle-cpu-200']) {
        expect(item(view, id).status, EnhancementStatus.incompatible, reason: id);
        expect(item(view, id).problem, EnhancementProblem.userFilePresent, reason: id);
        expect(item(view, id).payload['problemKey'], EnhancementsLocale.playerValue, reason: 'the game\'s own value');
      }
      expect(item(view, 'beetle-gte-overclock').payload.containsKey('problemKey'), isFalse);
      // Turned on anyway (an older page): refused before anything is written.
      final forced = item(view, 'beetle-cpu-150').copyWith(status: EnhancementStatus.available);
      await expectLater(
        enhancements.setActive(game, 'ps1', view, forced, true),
        throwsA(isA<EnhancementException>().having((error) => error.code, 'code', 'player_value')),
      );
      expect(options('Beetle PSX').readAsBytesSync(), before);
      expect(options('Beetle PSX HW').existsSync(), isFalse);
      expect(item(view, 'beetle-gte-overclock').status, EnhancementStatus.available);
    });

    test('equal values of the player\'s stay theirs', () async {
      seed('Beetle PSX HW', {
        'version': 1,
        'games': {
          'ps1/Crash.cue': {'beetle_psx_hw_gte_overclock': 'enabled', 'beetle_psx_hw_pgxp_mode': 'memory only'},
        },
      });
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      expect(item(view, 'beetle-gte-overclock').status, EnhancementStatus.active, reason: 'in effect');
      // Made only of the player's values: it cannot be turned off here, and the page says so.
      await expectLater(
        enhancements.setActive(game, 'ps1', view, item(view, 'beetle-gte-overclock'), false),
        throwsA(isA<EnhancementException>().having((error) => error.code, 'code', 'player_keeps_on')),
      );
      expect(values('Beetle PSX HW')['beetle_psx_hw_gte_overclock'], 'enabled');

      // PGXP: the mode is the player's, texture correction RewindBox's.
      view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-pgxp-textures'), true);
      expect(values('Beetle PSX HW')['beetle_psx_hw_pgxp_texture'], 'enabled');
      final state = (await enhancements.games()).single;
      expect((state.data['values'] as Map)['mednafen_psx_hw'], {'beetle_psx_hw_pgxp_texture': 'enabled'});
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-pgxp-textures'), false);
      expect(values('Beetle PSX HW'), {
        'beetle_psx_hw_gte_overclock': 'enabled',
        'beetle_psx_hw_pgxp_mode': 'memory only',
      });
      expect(values('Beetle PSX'), isEmpty);
    });

    test('restoring keeps a value the player changed since, and drops what the player removed', () async {
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-gte-overclock'), true);
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-widescreen-16-9'), true);
      final hardware = json('Beetle PSX HW')!;
      (hardware['games'] as Map)['ps1/Crash.cue']['beetle_psx_hw_gte_overclock'] = 'disabled';
      seed('Beetle PSX HW', hardware);
      final software = json('Beetle PSX')!;
      (software['games'] as Map)['ps1/Crash.cue'].remove('beetle_psx_widescreen_hack');
      seed('Beetle PSX', software);

      view = await enhancements.open(game, 'ps1');
      expect(item(view, 'beetle-gte-overclock').status, EnhancementStatus.incompatible, reason: 'theirs now');
      expect(item(view, 'beetle-gte-overclock').problem, EnhancementProblem.userFilePresent);
      expect(item(view, 'beetle-widescreen-16-9').status, EnhancementStatus.active, reason: 'Beetle PSX HW runs it');

      await enhancements.restore(view.identity.storeKey);
      expect(values('Beetle PSX HW'), {'beetle_psx_hw_gte_overclock': 'disabled'});
      expect(options('Beetle PSX').existsSync(), isFalse);
      expect(await enhancements.games(), isEmpty);
    });

    test('nothing is written while a game runs, nor when that cannot be told', () async {
      final game = crash();
      final enhancements = service();
      final view = await enhancements.open(game, 'ps1');
      session = true;
      await expectLater(
        enhancements.setActive(game, 'ps1', view, item(view, 'beetle-widescreen-16-9'), true),
        throwsA(isA<EnhancementException>().having((error) => error.code, 'code', 'session_active')),
      );
      expect(Directory(path.join(config.path, 'Games')).existsSync(), isFalse);
      final unknown = BeetleEnhancementAdapter(
        configDirectory: () async => config,
        sessionActive: () async => throw StateError('no answer'),
        coreChoice: (_, _) async => null,
        runsEmbedded: (_, _) async => true,
      );
      final identity = await unknown.identify(game, 'ps1');
      final state = EnhancementGameState(storeKey: identity.storeKey, engine: 'beetle', key: identity.key);
      await expectLater(
        unknown.apply(identity, const {}, state, {'beetle-gte-overclock'}),
        throwsA(isA<EnhancementException>().having((error) => error.code, 'code', 'session_active')),
      );
      expect(Directory(path.join(config.path, 'Games')).existsSync(), isFalse);
      expect(state.data, isEmpty);
    });

    test('a file RewindBox cannot read is never written', () async {
      options('Beetle PSX').parent.createSync(recursive: true);
      options('Beetle PSX').writeAsStringSync('{"games": [');
      final game = crash();
      final enhancements = service();
      final view = await enhancements.open(game, 'ps1');
      expect(item(view, 'beetle-gte-overclock').status, EnhancementStatus.incompatible);
      expect(item(view, 'beetle-gte-overclock').payload['problemKey'], EnhancementsLocale.optionsUnreadable);
      expect(item(view, 'beetle-gte-overclock').payload['file'], 'Beetle PSX.json', reason: 'the page names it');
      expect(item(view, 'beetle-mdec-chroma').status, EnhancementStatus.available, reason: 'Beetle PSX HW only');
      await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-mdec-chroma'), true);
      expect(options('Beetle PSX').readAsStringSync(), '{"games": [');
      expect(values('Beetle PSX HW'), {'beetle_psx_hw_mdec_yuv': 'enabled'});
      final forced = item(view, 'beetle-gte-overclock').copyWith(status: EnhancementStatus.available);
      await expectLater(
        enhancements.setActive(game, 'ps1', view, forced, true),
        throwsA(
          isA<EnhancementException>()
              .having((error) => error.code, 'code', 'options_unreadable')
              .having((error) => error.detail, 'detail', 'Beetle PSX.json'),
        ),
      );
    });

    test('a Vulkan-only preset stays in Beetle PSX HW while the game is set to Beetle PSX, and comes back with it',
        () async {
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-mdec-chroma'), true);
      expect(values('Beetle PSX HW'), {'beetle_psx_hw_mdec_yuv': 'enabled'});

      // Set to Beetle PSX: other presets switch on and off without touching it.
      choice = 'mednafen_psx';
      view = await enhancements.open(game, 'ps1');
      expect(item(view, 'beetle-mdec-chroma').status, EnhancementStatus.incompatible);
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-gte-overclock'), true);
      expect(values('Beetle PSX HW'), {'beetle_psx_hw_mdec_yuv': 'enabled', 'beetle_psx_hw_gte_overclock': 'enabled'});
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-gte-overclock'), false);
      expect(values('Beetle PSX HW'), {'beetle_psx_hw_mdec_yuv': 'enabled'});
      expect(options('Beetle PSX').existsSync(), isFalse);
      expect((await enhancements.games()).single.data['values'], {
        'mednafen_psx_hw': {'beetle_psx_hw_mdec_yuv': 'enabled'},
      });

      // Back on Beetle PSX HW: still on, and turning it off there removes it.
      choice = null;
      view = await enhancements.open(game, 'ps1');
      expect(item(view, 'beetle-mdec-chroma').status, EnhancementStatus.active);
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-mdec-chroma'), false);
      expect(options('Beetle PSX HW').existsSync(), isFalse);
      expect(await enhancements.games(), isEmpty);

      // Restoring removes it whatever core the game is set to.
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-mdec-chroma'), true);
      choice = 'mednafen_psx';
      view = await enhancements.open(game, 'ps1');
      await enhancements.restore(view.identity.storeKey);
      expect(options('Beetle PSX HW').existsSync(), isFalse);
      expect(await enhancements.games(), isEmpty);
    });

    test('restoring with a damaged options file restores the other one and keeps only its values', () async {
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-gte-overclock'), true);
      options('Beetle PSX HW').writeAsStringSync('{"games": [');
      view = await enhancements.open(game, 'ps1');
      await expectLater(
        enhancements.restore(view.identity.storeKey),
        throwsA(
          isA<EnhancementException>()
              .having((error) => error.code, 'code', 'options_unreadable')
              .having((error) => error.detail, 'detail', 'Beetle PSX HW.json'),
        ),
      );
      expect(options('Beetle PSX').existsSync(), isFalse, reason: 'restored: the file RewindBox made is gone');
      expect(options('Beetle PSX HW').readAsStringSync(), '{"games": [', reason: 'never written');
      final state = (await enhancements.games()).single;
      expect(state.data['values'], {
        'mednafen_psx_hw': {'beetle_psx_hw_gte_overclock': 'enabled'},
      });
      expect(state.data['created'], ['mednafen_psx_hw']);

      // Once it reads again, restoring finishes.
      seed('Beetle PSX HW', {
        'version': 1,
        'games': {
          'ps1/Crash.cue': {'beetle_psx_hw_gte_overclock': 'enabled'},
        },
      });
      await enhancements.restore(view.identity.storeKey);
      expect(options('Beetle PSX HW').existsSync(), isFalse);
      expect(await enhancements.games(), isEmpty);
    });

    test('a game whose values RewindBox no longer holds is not kept, even with values it still records', () async {
      final game = crash();
      final enhancements = service();
      var view = await enhancements.open(game, 'ps1');
      view = await enhancements.setActive(game, 'ps1', view, item(view, 'beetle-gte-overclock'), true);
      expect(view.installed, isTrue);
      // The player resets the game's options in the in-game menu.
      for (final library in ['Beetle PSX HW', 'Beetle PSX']) {
        final document = json(library)!;
        (document['games'] as Map).remove('ps1/Crash.cue');
        seed(library, document);
      }
      view = await enhancements.open(game, 'ps1');
      expect(view.installed, isFalse);
      expect(view.activeCount, 0);
      expect(await enhancements.games(), isEmpty, reason: 'not listed with nothing active');
      final saved = EnhancementStore(root: () async => Directory(path.join(temp.path, 'store')));
      expect(await saved.all(), isEmpty, reason: 'nor saved');
    });
  });
}
