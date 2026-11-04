// GameCube and Wii controller skins for the embedded Dolphin
// (docs/dolphin-skins.md): read in Dart, imported, filtered and chosen like
// the libretro skins, drawn in a game by DOLSkinOverlay, which follows the
// same input table. The skins here are synthetic, laid out like the
// published GameCube Pocket (Manic EMU), with no third-party art.
import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart' show Archive, ArchiveFile, ZipEncoder;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/services/dolphin_skins.dart';
import 'package:neostation/services/libretro_skin_catalog_service.dart';
import 'package:neostation/services/libretro_skin_catalogs.dart';
import 'package:neostation/services/libretro_skin_compatibility.dart';
import 'package:neostation/services/libretro_skin_service.dart';
import 'package:path/path.dart' as path;

const _channel = MethodChannel('neostation/libretro_internal');
const _overlay = 'packages/dolphin_internal_bridge/ios/Classes/DOLSkinOverlay.mm';
const _buttonTypes = 'packages/dolphin_internal_bridge/ios/Classes/TouchController/TCButtonType.swift';

Map<String, Object?> _frame(num x, num y, num w, num h) => {'x': x, 'y': y, 'width': w, 'height': h};

Map<String, Object?> _stick(String side, Map<String, Object?> frame, String knob) => {
      'frame': frame,
      'inputs': {
        for (final d in const ['Up', 'Down', 'Left', 'Right']) d.toLowerCase(): '${side}Thumbstick$d',
      },
      'thumbstick': {'name': knob, 'width': 96, 'height': 96},
    };

Map<String, Object?> _button(String input, Map<String, Object?> frame, {String? asset}) => {
      'frame': frame,
      'inputs': [input],
      if (asset != null) 'asset': {'normal': asset},
      'extendedEdges': {'top': 6, 'bottom': 6, 'left': 4, 'right': 4},
    };

/// The GameCube Pocket layout: main stick, C-stick, D-pad, A B X Y, Z (r1),
/// L (l2), R (r2), quick save / load, Start and Menu.
List<Map<String, Object?>> _gameCubeItems({bool start = true}) => [
      _stick('left', _frame(36, 515, 100, 100), 'stick.pdf'),
      _stick('right', _frame(224, 669, 70, 70), 'cstick.pdf'),
      {
        'frame': _frame(79, 664, 79, 79),
        'inputs': {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'},
        'asset': {'normal': 'dpad.pdf'},
      },
      _button('a', _frame(253, 526, 75, 75), asset: 'a.pdf'),
      _button('b', _frame(198, 574, 47, 47), asset: 'b.pdf'),
      _button('x', _frame(333, 501, 48, 69)),
      _button('y', _frame(247, 471, 70, 40)),
      _button('r1', _frame(202, 510, 34, 34)),
      _button('l2', _frame(15, 422, 106, 44)),
      _button('r2', _frame(254, 422, 106, 44)),
      _button('quickSave', _frame(75, 372, 50, 16)),
      _button('quickLoad', _frame(247, 372, 50, 16)),
      if (start) _button('start', _frame(174, 761, 26, 26), asset: 'start.pdf'),
      // Its picture is not in the archive, as in the published skin.
      _button('menu', _frame(20, 767, 26, 26), asset: 'menu.pdf'),
    ];

Map<String, Object?> _layout(String background, num width, num height, List<Map<String, Object?>> items,
        {Map<String, Object?>? screen}) =>
    {
      'assets': {'small': background, 'medium': background, 'large': background},
      'mappingSize': {'width': width, 'height': height},
      if (screen != null) 'screens': [{'outputFrame': screen}],
      'items': items,
      'translucent': false,
    };

Map<String, Object?> _gameCubePocket({bool start = true, String type = 'public.aoshuang.game.ngc'}) => {
      'name': 'Pocket test skin',
      'identifier': 'org.neostation.test.gcpocket',
      'gameTypeIdentifier': type,
      'representations': {
        'iphone': {
          'edgeToEdge': {
            'portrait': _layout('portrait.png', 375, 812, _gameCubeItems(start: start),
                screen: _frame(8, 67, 360, 270)),
            'landscape': _layout('landscape.png', 812, 375, _gameCubeItems(start: start),
                screen: _frame(201, 24, 410, 308)),
          },
        },
      },
    };

/// The files of the synthetic skin: tiny PNG backgrounds and PDF pictures.
Map<String, List<int>> _files(Map<String, Object?> info, {List<String> omit = const ['menu.pdf']}) {
  final pdf = utf8.encode('%PDF-1.4\n%%EOF\n');
  return {
    'info.json': utf8.encode(jsonEncode(info)),
    'portrait.png': _png,
    'landscape.png': _png,
    for (final name in const ['stick.pdf', 'cstick.pdf', 'dpad.pdf', 'a.pdf', 'b.pdf', 'start.pdf', 'menu.pdf'])
      if (!omit.contains(name)) name: pdf,
  };
}

// A 1x1 transparent PNG.
final List<int> _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=');

Future<String> _unpacked(Directory root, Map<String, List<int>> files) async {
  final directory = await Directory(path.join(root.path, 'skin${root.listSync().length}')).create(recursive: true);
  for (final entry in files.entries) {
    await File(path.join(directory.path, entry.key)).writeAsBytes(entry.value);
  }
  return directory.path;
}

Uint8List _zip(Map<String, List<int>> files) {
  final archive = Archive();
  for (final entry in files.entries) {
    archive.add(ArchiveFile.bytes(entry.key, entry.value));
  }
  return ZipEncoder().encodeBytes(archive);
}

/// `@"raw" : @"canonical"` pairs of one table of DOLSkinOverlay.mm.
Map<String, String> _nativeTable(String source, String console) {
  final start = source.indexOf('// dolphin-skins-table: $console');
  expect(start, greaterThanOrEqualTo(0), reason: 'native $console table');
  final end = source.indexOf('// dolphin-skins-table: end', start);
  final body = source.substring(start, end);
  return {
    for (final m in RegExp(r'@"([^"]+)"\s*:\s*@"([^"]+)"').allMatches(body)) m.group(1)!: m.group(2)!,
  };
}

/// `@"name" : @id` pairs of a native dictionary literal after [marker].
Map<String, int> _nativeIds(String source, String marker) {
  final start = source.indexOf(marker);
  expect(start, greaterThanOrEqualTo(0), reason: marker);
  final body = source.substring(start, source.indexOf('};', start));
  return {
    for (final m in RegExp(r'@"(\w+)"\s*:\s*@(\d+)').allMatches(body)) m.group(1)!: int.parse(m.group(2)!),
  };
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Directory root;

  setUp(() async => root = await Directory.systemTemp.createTemp('dolphin-skins-'));
  tearDown(() async {
    messenger.setMockMethodCallHandler(_channel, null);
    await root.delete(recursive: true);
  });

  test('game types: the GameCube and Wii identifiers of Manic and Delta, nothing else', () {
    expect(DolphinSkins.consoleOfGameType('public.aoshuang.game.ngc'), 'gc');
    expect(DolphinSkins.consoleOfGameType('com.example.game.gamecube'), 'gc');
    expect(DolphinSkins.consoleOfGameType('public.aoshuang.game.wii'), 'wii');
    expect(DolphinSkins.consoleOfGameType('com.example.game.rvl'), 'wii');
    expect(DolphinSkins.consoleOfGameType('com.rileytestut.delta.game.gba'), isNull);
    // PlayStation 2 is ARMSX2's (ARMSX2SkinOverlay); PlayStation 1 is neither.
    expect(DolphinSkins.consoleOfGameType('public.aoshuang.game.ps2'), 'ps2');
    expect(DolphinSkins.consoleOfGameType('public.aoshuang.game.ps1'), isNull);
    expect(DolphinSkins.isDolphinConsole('gc') && DolphinSkins.isDolphinConsole('wii'), isTrue);
    expect(DolphinSkins.isDolphinConsole('ps2'), isTrue);
    expect(DolphinSkins.isDolphinConsole('gba'), isFalse);
    expect(DolphinSkins.skinConsoles.keys, containsAll(['gc', 'wii', 'ps2', 'gba', 'snes']));
  });

  test('input names: the GameCube conventions of Manic, Wii adaptations reported', () {
    String? gc(String raw, [List<bool>? adapted]) => DolphinSkins.canonicalInput('gc', raw, adapted: adapted);
    String? wii(String raw, [List<bool>? adapted]) => DolphinSkins.canonicalInput('wii', raw, adapted: adapted);
    expect(gc('leftThumbstickUp'), 'stickUp');
    expect(gc('rightThumbstickLeft'), 'cLeft', reason: 'the right stick is the C-stick');
    expect(gc('r1'), 'z');
    expect(gc('l2'), 'l');
    expect(gc('r2'), 'r');
    expect(gc('dpad_down'), 'down');
    expect(gc('quickSave'), 'quickSave');
    expect(gc('pause'), 'menu');
    expect(gc('select'), isNull, reason: 'a GameCube has no Select');
    final adapted = <bool>[];
    expect(gc('l1', adapted), 'z');
    expect(adapted, isNotEmpty, reason: 'l1 as Z is an adaptation');

    final noAdaptation = <bool>[];
    expect(wii('nunchukC', noAdaptation), 'c');
    expect(wii('1', noAdaptation), 'one');
    expect(wii('home', noAdaptation), 'home');
    expect(noAdaptation, isEmpty);
    for (final (raw, input) in const [('x', 'one'), ('y', 'two'), ('start', 'plus'), ('select', 'minus'),
      ('rightThumbstickUp', 'pointerUp'), ('l1', 'c'), ('r2', 'z')]) {
      final marks = <bool>[];
      expect(wii(raw, marks), input, reason: raw);
      expect(marks, isNotEmpty, reason: '$raw is an adaptation on a Wii');
    }
  });

  test('a GameCube Pocket layout: playable upright and sideways, a missing picture is a remark', () async {
    final directory = await _unpacked(root, _files(_gameCubePocket()));
    final report = await DolphinSkins.inspectDirectory(directory);
    expect(report, isNotNull);
    expect(report!.console, 'gc');
    expect(report.compatibility.verdict, LibretroSkinVerdict.compatible);
    expect(report.compatibility.orientations, {'portrait': 'compatible', 'landscape': 'compatible'});
    expect(report.orientations, ['portrait', 'landscape']);
    expect(report.compatibility.missingOptionalControls, isEmpty, reason: 'X Y Z L R and the C-stick are there');
    expect(report.warnings, ['SKIN_WARN_ASSET_MISSING'], reason: 'menu.pdf is not in the archive');
    expect(report.summary['consoles'], ['gc']);
    expect(report.summary['orientations'], {
      'iphone': ['portrait', 'landscape'],
      'ipad': ['portrait', 'landscape'],
    });
  });

  test('without Start a GameCube skin cannot be played; without art either', () async {
    final noStart = await DolphinSkins.inspectDirectory(await _unpacked(root, _files(_gameCubePocket(start: false))));
    expect(noStart!.compatibility.verdict, LibretroSkinVerdict.incompatible);
    expect(noStart.compatibility.missingControls, ['start']);
    expect(noStart.compatibility.reasons, contains('SKIN_COMPAT_MISSING_CONTROLS'));

    final files = _files(_gameCubePocket())
      ..remove('portrait.png')
      ..remove('landscape.png');
    final noArt = await DolphinSkins.inspectDirectory(await _unpacked(root, files));
    expect(noArt!.compatibility.verdict, LibretroSkinVerdict.incompatible);
    expect(noArt.compatibility.reasons, contains('SKIN_COMPAT_NO_ARTWORK'));

    final other = await DolphinSkins.inspectDirectory(
        await _unpacked(root, _files(_gameCubePocket(type: 'com.rileytestut.delta.game.gba'))));
    expect(other, isNull, reason: 'not a Dolphin skin: the libretro parser reads it');
  });

  test('a Wii skin drawn for a pad with Select and Start is adapted, an iPad-only one too', () async {
    final pad = [
      {
        'frame': _frame(20, 500, 120, 120),
        'inputs': {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'},
      },
      for (final (i, input) in const ['a', 'b', 'x', 'y', 'start', 'select'].indexed)
        _button(input, _frame(200 + i * 10, 500 + i * 40, 40, 40)),
    ];
    final info = {
      'name': 'Wii pad',
      'identifier': 'org.neostation.test.wii',
      'gameTypeIdentifier': 'public.aoshuang.game.wii',
      'representations': {
        'iphone': {
          'standard': {'portrait': _layout('portrait.png', 375, 667, pad)},
        },
      },
    };
    final report = await DolphinSkins.inspectDirectory(await _unpacked(root, _files(info)));
    expect(report!.console, 'wii');
    expect(report.compatibility.verdict, LibretroSkinVerdict.adaptable);
    expect(report.compatibility.reasons, contains('SKIN_COMPAT_ADAPTED_INPUTS'));
    expect(report.compatibility.adaptedInputs, containsAll(['x', 'y', 'start', 'select']));
    expect(report.warnings, contains('SKIN_WARN_ORIENTATION_MISSING'));

    final tablet = {
      ...info,
      'representations': {
        'ipad': {
          'standard': {'landscape': _layout('landscape.png', 1024, 768, pad)},
        },
      },
    };
    final adapted = await DolphinSkins.inspectDirectory(await _unpacked(root, _files(tablet)));
    expect(adapted!.compatibility.tabletLayout, isTrue);
    expect(adapted.compatibility.reasons, contains('SKIN_COMPAT_TABLET_ADAPTED'));
    expect(adapted.compatibility.orientations, {'landscape': 'adaptable'});
  });

  test('preview: the PNG of the orientation, never a PDF background', () async {
    final directory = await _unpacked(root, _files(_gameCubePocket()));
    expect(await DolphinSkins.previewImage(directory, 'portrait'), _png);
    final pdf = _gameCubePocket();
    final representation = ((pdf['representations'] as Map)['iphone'] as Map)['edgeToEdge'] as Map;
    (representation['landscape'] as Map)['assets'] = {'resizable': 'landscape.pdf'};
    final pdfDirectory = await _unpacked(root, {..._files(pdf), 'landscape.pdf': utf8.encode('%PDF-1.4\n')});
    expect(await DolphinSkins.previewImage(pdfDirectory, 'landscape'), isNull);
    expect(await DolphinSkins.previewImage(pdfDirectory, 'portrait'), _png);
  });

  test('import and choice go through the skin service, without the libretro parser', () async {
    final calls = <MethodCall>[];
    final store = <String, Map<String, Object?>>{};
    messenger.setMockMethodCallHandler(_channel, (call) async {
      calls.add(call);
      final arguments = (call.arguments as Map).cast<String, Object?>();
      switch (call.method) {
        case 'setFrontendSetting':
          final console = store.putIfAbsent(arguments['console'] as String, () => <String, Object?>{});
          console[arguments['key'] as String] = arguments['value'];
          return true;
        case 'frontendSettings':
          return {'console': store[arguments['console']] ?? <String, Object?>{}, 'games': <String, Object?>{}};
      }
      return null;
    });
    final service = LibretroSkinService(
      skinsDirectory: path.join(root.path, 'Skins'),
      frontendDirectory: path.join(root.path, 'Config', 'Frontend'),
      cacheDirectory: path.join(root.path, 'Caches'),
    );
    final archive = File(path.join(root.path, 'incoming', 'gcpocket.manicskin'));
    await archive.parent.create(recursive: true);
    await archive.writeAsBytes(_zip(_files(_gameCubePocket())));

    final result = await service.importFromFile(archive.path, targetConsole: 'gc');
    expect(result, isA<LibretroSkinImported>());
    final skin = (result as LibretroSkinImported).skin;
    expect(skin.consoles, ['gc']);
    expect(skin.supports('portrait') && skin.supports('landscape'), isTrue);
    expect(skin.compatibility['gc']?.verdict, LibretroSkinVerdict.compatible);
    expect(skin.warnings, ['SKIN_WARN_ASSET_MISSING']);
    expect(calls.where((c) => c.method == 'inspectSkin'), isEmpty, reason: 'read in Dart');
    expect(await File(path.join(skin.directory, 'info.json')).exists(), isTrue);
    expect((await service.installedSkins(console: 'gc')).map((s) => s.id), [skin.id]);
    expect(await service.installedSkins(console: 'wii'), isEmpty);
    expect((await service.compatibilityOf(skin))['gc']?.verdict, LibretroSkinVerdict.compatible);
    expect(await service.preview(skin: skin, console: 'gc', orientation: 'landscape', width: 844, height: 390), _png);
    expect(await service.preview(console: 'gc', orientation: 'landscape', width: 844, height: 390), isNull,
        reason: 'the default is the DolphiniOS pad: no libretro preview of it');
    expect(calls.where((c) => c.method == 'skinPreview'), isEmpty);

    // The file the Dolphin overlay reads: Config/Frontend/gc.json.
    expect(await service.select(console: 'gc', orientation: 'portrait', skinId: skin.id), isTrue);
    final stored = calls.singleWhere((c) => c.method == 'setFrontendSetting').arguments as Map;
    expect(stored['console'], 'gc');
    expect(stored['key'], 'skin.portrait');
    expect(stored['directory'], path.join(root.path, 'Config', 'Frontend'));
    expect(await service.selectedSkins('gc'), {'portrait': skin.id, 'landscape': null});
  });

  test('catalogs: the Dart reader classifies GameCube skins; RetroArch overlays are not offered', () async {
    final service = LibretroSkinService(
      skinsDirectory: path.join(root.path, 'Skins'),
      frontendDirectory: path.join(root.path, 'Config', 'Frontend'),
      cacheDirectory: path.join(root.path, 'Caches'),
    );
    final client = MockClient((_) async => http.Response('', 404));
    final catalogs = LibretroSkinCatalogs(
      skins: service,
      provenance: LibretroSkinCatalogService(cacheDirectory: service.cacheDirectory, skins: service, client: client),
      client: client,
    );
    const overlay = LibretroOverlayEntry(id: 'gc-overlay', source: 'pocketarch', path: 'gc/test.cfg',
        repository: 'stunrelay/PocketArch', commit: 'abc', device: 'iphone', files: ['gc/img/bg.png']);
    final entry = LibretroCatalogSkin(key: 'gc-overlay', source: 'pocketarch', name: 'Overlay', consoles: const ['gc'],
        overlay: overlay);
    final verdict = await catalogs.knownVerdict(entry, 'gc');
    expect(verdict?.reasons, [LibretroSkinCompatibility.overlayUnsupported]);
    // A Manic GameCube skin of a catalog is listed for the GameCube only.
    const listed = LibretroSkinCatalogEntry(id: 'pocket', name: 'GameCube Pocket',
        downloadURL: 'https://example.org/pocket.manicskin', gameTypeIdentifier: 'public.aoshuang.game.ngc');
    expect(listed.consoles, ['gc']);
    expect(const LibretroSkinCatalogEntry(id: 'w', name: 'Wii', downloadURL: 'https://example.org/w.manicskin',
        systems: ['wii']).consoles, ['wii']);
    catalogs.dispose();
  });

  test('the native overlay reads the same input table and sends the DolphiniOS ids', () {
    final source = File(_overlay).readAsStringSync();
    for (final console in const ['gc', 'wii']) {
      final table = _nativeTable(source, console);
      expect(table, isNotEmpty);
      for (final entry in table.entries) {
        expect(DolphinSkins.canonicalInput(console, entry.key), entry.value, reason: '$console ${entry.key}');
      }
      // Every input a skin may name for that console has a native target.
      for (final input in DolphinSkins.inputs[console]!) {
        final native = input.startsWith('stick') || input.startsWith('c') && input.length > 1 && console == 'gc' ||
            input.startsWith('pointer') || const ['menu', 'quickSave', 'quickLoad'].contains(input);
        if (native) continue;
        expect(table.values.contains(input) || const ['up', 'down', 'left', 'right'].contains(input), isTrue,
            reason: '$console $input');
      }
    }
    for (final prefix in const ['"leftthumbstick", @"analogstick", @"leftstick", @"leftanalog", @"analog", @"thumbstick"',
      '"rightthumbstick", @"rightstick", @"rightanalog", @"cstick", @"c"']) {
      expect(source, contains(prefix), reason: 'same stick prefixes as DolphinSkins.canonicalInput');
    }

    // TCButtonType (DolphiniOS): the ids the pad sends.
    final types = {
      for (final m in RegExp(r'case (\w+) = (\d+)').allMatches(File(_buttonTypes).readAsStringSync()))
        m.group(1)!: int.parse(m.group(2)!),
    };
    final gc = _nativeIds(source, 'return @{\n    @"a" : @0');
    expect(gc, {
      'a': types['gcButtonA'], 'b': types['gcButtonB'], 'start': types['gcButtonStart'], 'x': types['gcButtonX'],
      'y': types['gcButtonY'], 'z': types['gcButtonZ'], 'up': types['gcButtonUp'], 'down': types['gcButtonDown'],
      'left': types['gcButtonLeft'], 'right': types['gcButtonRight'],
    });
    final wii = _nativeIds(source, 'return @{\n      @"a" : @100');
    expect(wii, {
      'a': types['wiiButtonA'], 'b': types['wiiButtonB'], 'minus': types['wiiButtonMinus'],
      'plus': types['wiiButtonPlus'], 'home': types['wiiButtonHome'], 'one': types['wiiButtonOne'],
      'two': types['wiiButtonTwo'], 'up': types['wiiPadUp'], 'down': types['wiiPadDown'], 'left': types['wiiPadLeft'],
      'right': types['wiiPadRight'], 'c': types['nunchukButtonC'], 'z': types['nunchukButtonZ'],
    });
    expect(source, contains('@{@"l" : @${types['gcTriggerL']}, @"r" : @${types['gcTriggerR']}}'));
    expect(source, contains('return wii ? ${types['nunchukStick']} : ${types['gcStickMain']};'));
    expect(source, contains('&& !wii) return ${types['gcStickC']};'));
    expect(source, contains('&& wii) return ${types['wiiInfrared']};'));
    // The pad's ports (DolphinTouchOverlay: view.port = wii ? 4 : 0).
    expect(source, contains('_port = wii ? 4 : 0;'));
    expect(File('packages/dolphin_internal_bridge/ios/Classes/TouchController/DolphinTouchOverlay.swift')
        .readAsStringSync(), contains('view.port = wii ? 4 : 0'));
  });

  test('the overlay header is safe in the pod umbrella; the reviewed podspec is untouched', () {
    // The podspec is bound by its SHA-256 to a reviewed declaration
    // (build-utils/collect_build_source_evidence.py): the header is not made
    // private there, so it joins the module umbrella, which Swift compiles
    // as Objective-C. It must stay pure Objective-C importing UIKit only.
    final header = File('packages/dolphin_internal_bridge/ios/Classes/DOLSkinOverlay.h').readAsStringSync();
    expect(RegExp(r'^#(?:import|include)\s+(\S+)', multiLine: true).allMatches(header).map((m) => m.group(1)),
        ['<UIKit/UIKit.h>']);
    for (final cpp in const ['std::', 'namespace', 'template', 'extern "C"', 'class ']) {
      expect(header.contains(cpp), isFalse, reason: cpp);
    }
    final podspec = File('packages/dolphin_internal_bridge/ios/dolphin_internal_bridge.podspec').readAsStringSync();
    expect(podspec.contains('DOLSkinOverlay'), isFalse);
  });

  test('the session reads the files the skin screens write', () {
    final source = File(_overlay).readAsStringSync();
    expect(source, contains('[libretro stringByAppendingPathComponent:@"Config/Frontend"]'));
    expect(source, contains('[libretro stringByAppendingPathComponent:@"Skins"]'));
    expect(source, contains('[@"skin." stringByAppendingString:orientation]'));
    expect(LibretroSkinService.selectionKey('portrait'), 'skin.portrait');
    expect(LibretroSkinService.defaultSkinId, 'default');
    // The id rule of LibretroSkinService.isInstalledId.
    expect(source, contains('@"abcdefghijklmnopqrstuvwxyz0123456789-"'));
    expect(LibretroSkinService.isInstalledId('0123abcd-ef'), isTrue);
    expect(LibretroSkinService.isInstalledId('../x'), isFalse);
    final plugin = File('packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm').readAsStringSync();
    final lock = plugin.indexOf('[controller lockRenderSurface];');
    expect(lock, greaterThan(0));
    expect(lock, lessThan(plugin.indexOf('neostation_dolphin_launch_wii_menu((__bridge void*)layer')),
        reason: 'the surface is fixed before the core reads it');
    expect(plugin, contains('if (skin.hasSkin) {'), reason: 'no skin, no overlay: the session is unchanged');
  });
}
