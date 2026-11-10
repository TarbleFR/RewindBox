// Nintendo Switch controller skins (MeloNX): the console, its input table, its
// iPhone verdict and the native overlay's table and Core indices.
//
// The Switch skin path (docs/dolphin-skins.md): the skin manager of the console
// `switch` (from the MeloNX playlist) stores the choice in
// Config/Frontend/switch.json; MeloNXSkinOverlay reads it at launch, draws the
// skin and sends the embedded Core's button indices (native/melonx/EmbeddedInput.cs
// neostation_melonx_input_button, order proven on the real NativeGamepadDriver by
// test/melonx_input_test.py) through MeloNXInputRouter. Host tests: no iPhone,
// no Core.
import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/dolphin_skins.dart';
import 'package:neostation/services/libretro_skin_compatibility.dart';
import 'package:path/path.dart' as path;

const _overlay = 'packages/melonx_internal_bridge/ios/Classes/MeloNXSkinOverlay.mm';
const _session = 'packages/melonx_internal_bridge/ios/Classes/MeloNXSkinSession.swift';
const _router = 'packages/melonx_internal_bridge/ios/Classes/MeloNXInputRouter.swift';
const _controller = 'packages/melonx_internal_bridge/ios/Classes/MeloNXMetalSessionViewController.swift';

Map<String, Object?> _frame(num x, num y, num w, num h) => {'x': x, 'y': y, 'width': w, 'height': h};

Map<String, Object?> _stick(String side, Map<String, Object?> frame) => {
      'frame': frame,
      'inputs': {for (final d in const ['Up', 'Down', 'Left', 'Right']) d.toLowerCase(): '${side}Thumbstick$d'},
      'asset': {'normal': 'art.png'},
      'thumbstick': {'name': 'art.png', 'width': 50, 'height': 50},
    };

Map<String, Object?> _button(String input, Map<String, Object?> frame) => {
      'frame': frame,
      'inputs': [input],
      'asset': {'normal': 'art.png'},
    };

List<Map<String, Object?>> _items({bool a = true, bool home = true}) => [
      _stick('left', _frame(20, 500, 90, 90)),
      _stick('right', _frame(260, 640, 90, 90)),
      {
        'frame': _frame(30, 640, 90, 90),
        'inputs': {'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'},
        'asset': {'normal': 'art.png'},
      },
      if (a) _button('a', _frame(300, 540, 46, 46)),
      _button('b', _frame(250, 590, 46, 46)),
      _button('x', _frame(250, 490, 46, 46)),
      _button('y', _frame(200, 540, 46, 46)),
      for (final (i, name) in const ['l', 'zl', 'minus', 'menu', 'plus', 'zr', 'r'].indexed)
        _button(name, _frame(10 + i * 52, 410, 48, 46)),
      if (home) _button('home', _frame(130, 460, 46, 46)),
      _button('capture', _frame(190, 460, 46, 46)),
      _button('l3', _frame(110, 600, 46, 46)),
      _button('r3', _frame(320, 740, 46, 46)),
    ];

Map<String, Object?> _info({bool a = true, String type = 'org.rewindbox.game.switch'}) => {
      'name': 'Switch test skin',
      'identifier': 'org.rewindbox.test.switch',
      'gameTypeIdentifier': type,
      'representations': {
        'iphone': {
          'edgeToEdge': {
            for (final o in const ['portrait', 'landscape'])
              o: {
                'assets': {'large': 'art.png'},
                'mappingSize': o == 'portrait' ? {'width': 393, 'height': 852} : {'width': 852, 'height': 393},
                'screens': [
                  {'outputFrame': _frame(10, 60, 373, 210)},
                ],
                'items': _items(a: a),
              },
          },
        },
      },
    };

final List<int> _png = base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=');

Future<String> _unpacked(Directory root, Map<String, Object?> info) async {
  final directory = await Directory(path.join(root.path, 'skin${root.listSync().length}')).create(recursive: true);
  await File(path.join(directory.path, 'info.json')).writeAsString(jsonEncode(info));
  await File(path.join(directory.path, 'art.png')).writeAsBytes(_png);
  return directory.path;
}

/// The native button table: canonical input -> Core button index.
Map<String, int> _nativeIds(String source) {
  final start = source.indexOf('static NSDictionary<NSString*, NSNumber*>* MLXSkinButtonIds(void)');
  expect(start, greaterThanOrEqualTo(0));
  final body = source.substring(start, source.indexOf('};', start));
  return {for (final m in RegExp(r'@"(\w+)"\s*:\s*@(\d+)').allMatches(body)) m.group(1)!: int.parse(m.group(2)!)};
}

void main() {
  late Directory root;
  setUp(() async => root = await Directory.systemTemp.createTemp('melonx-skins-'));
  tearDown(() async => root.delete(recursive: true));

  test('the Nintendo Switch is a skin console of its own, drawn by MeloNX', () {
    for (final type in const ['org.rewindbox.game.switch', 'public.aoshuang.game.nx', 'com.example.game.nintendoswitch']) {
      expect(DolphinSkins.consoleOfGameType(type), 'switch', reason: type);
    }
    expect(DolphinSkins.consoleOfGameType('public.aoshuang.game.ngc'), 'gc', reason: 'the GameCube is unchanged');
    expect(DolphinSkins.consoleOfGameType('public.aoshuang.game.ps2'), 'ps2', reason: 'the PS2 is unchanged');
    expect(DolphinSkins.isDolphinConsole('switch'), isTrue, reason: 'read here, not by the libretro parser');
    expect(DolphinSkins.skinConsoles['switch']!.name, 'Nintendo Switch');
    expect(DolphinSkins.consoleGeometry()['switch'], isNotNull);
  });

  test('Switch input names: its own buttons, adaptations reported, no other console guessed', () {
    String? nx(String raw, [List<bool>? adapted]) => DolphinSkins.canonicalInput('switch', raw, adapted: adapted);
    final exact = <bool>[];
    for (final name in const ['a', 'b', 'x', 'y', 'l', 'r', 'zl', 'zr', 'minus', 'plus', 'l3', 'r3', 'home', 'capture']) {
      expect(nx(name, exact), name);
    }
    expect(nx('leftThumbstickUp', exact), 'stickUp');
    expect(nx('rightThumbstickLeft', exact), 'rstickLeft', reason: 'the right stick is the right stick');
    expect(nx('dpad_down', exact), 'down');
    expect(nx('menu', exact), 'menu', reason: 'the RewindBox session menu, not HOME');
    expect(exact, isEmpty);
    for (final (raw, input) in const [('select', 'minus'), ('start', 'plus'), ('leftStickClick', 'l3'),
      ('rightStickClick', 'r3'), ('screenshot', 'capture')]) {
      final marks = <bool>[];
      expect(nx(raw, marks), input, reason: raw);
      expect(marks, isNotEmpty, reason: '$raw is an adaptation on a Switch');
    }
    for (final other in const ['cross', 'circle', 'square', 'triangle', 'l1', 'r2', 'z', 'one', 'c', 'quickSave']) {
      expect(nx(other), isNull, reason: '$other is not a Switch input');
    }
    // The other consoles keep their tables.
    expect(DolphinSkins.canonicalInput('ps2', 'zl'), isNull);
    expect(DolphinSkins.canonicalInput('gc', 'quickSave'), 'quickSave');
  });

  test('a Switch layout with every control is playable upright and sideways; without A it is not', () async {
    final report = await DolphinSkins.inspectDirectory(await _unpacked(root, _info()));
    expect(report, isNotNull);
    expect(report!.console, 'switch');
    expect(report.compatibility.verdict, LibretroSkinVerdict.compatible);
    expect(report.orientations, ['portrait', 'landscape']);
    expect(report.compatibility.missingOptionalControls, isEmpty);
    final noA = await DolphinSkins.inspectDirectory(await _unpacked(root, _info(a: false)));
    expect(noA!.compatibility.verdict, LibretroSkinVerdict.incompatible);
    expect(noA.compatibility.missingControls, ['a']);
    final other = await DolphinSkins.inspectDirectory(await _unpacked(root, _info(type: 'com.rileytestut.delta.game.gba')));
    expect(other, isNull, reason: 'not a skin of these consoles');
  });

  test('the native overlay sends the Core\'s own indices for every Switch input', () {
    final source = File(_overlay).readAsStringSync();
    final ids = _nativeIds(source);
    // test/melonx_input_test.py: the index order checked on the real NativeGamepadDriver.
    final order = RegExp(r'GamepadButtonInputId\.(\w+)')
        .allMatches(File('test/melonx_input_test.py').readAsStringSync().split('var mapping = new[] {')[1].split('};')[0])
        .map((m) => m.group(1)!)
        .toList();
    expect(order, hasLength(17));
    const expected = {
      'a': 'A', 'b': 'B', 'x': 'X', 'y': 'Y', 'minus': 'Back', 'plus': 'Start', 'l3': 'LeftStick',
      'r3': 'RightStick', 'l': 'LeftShoulder', 'r': 'RightShoulder', 'up': 'DpadUp', 'down': 'DpadDown',
      'left': 'DpadLeft', 'right': 'DpadRight', 'zl': 'LeftTrigger', 'zr': 'RightTrigger',
    };
    expect(ids.keys.toSet(), expected.keys.toSet());
    for (final entry in expected.entries) {
      expect(order[ids[entry.key]!], entry.value, reason: '${entry.key} -> ${entry.value}');
    }
    expect(ids.values, isNot(contains(order.indexOf('Guide'))), reason: 'Guide is not a skin input');
    expect(File('native/melonx/EmbeddedInput.cs').readAsStringSync(), contains('button > 16'),
        reason: 'the ABI accepts 0...16, nothing for Capture');
    // Every Dart input has a native target: a pad index, a stick, the menu, or the session's
    // notice for HOME / Capture.
    for (final input in DolphinSkins.inputs['switch']!) {
      final native = ids.containsKey(input) || input.startsWith('stick') || input.startsWith('rstick') ||
          input == 'menu' || input == 'home' || input == 'capture';
      expect(native, isTrue, reason: input);
    }
    expect(source, contains('static NSArray<NSString*>* MLXSkinSystemButtons(void) { return @[ @"home", @"capture" ]; }'));
    expect(source, contains('NSString* console = @"switch";'));
    for (final prefix in const ['"leftthumbstick", @"analogstick", @"leftstick", @"leftanalog", @"analog", @"thumbstick"',
      '"rightthumbstick", @"rightstick", @"rightanalog", @"cstick", @"c"']) {
      expect(source, contains(prefix), reason: 'same stick prefixes as DolphinSkins.canonicalInput');
    }
    for (final alias in const ['@"leftstickclick", @"lsclick", @"ls"', '@"rightstickclick", @"rsclick", @"rs"',
      '@"select", @"back"', '[key isEqualToString:@"start"]', '[key isEqualToString:@"screenshot"]']) {
      expect(source, contains(alias), reason: 'Dart and native accept the same aliases');
    }
  });

  test('the session sends the skin to the real router path and keeps the Melo-Controller rule', () {
    final session = File(_session).readAsStringSync();
    final router = File(_router).readAsStringSync();
    final controller = File(_controller).readAsStringSync();
    expect(session, contains('router?.skinButton(Int32(button), pressed: pressed)'));
    expect(session, contains('router?.skinSticks(leftX: lx, leftY: ly, rightX: rx, rightY: ry)'));
    expect(session, contains('let hiddenByController = router.hideWithController && router.controllerCount > 0'));
    expect(session, contains('controlsView()?.isHidden = shown'));
    expect(session, contains('menuButton?.isHidden = shown && overlay.hasMenuControl'));
    expect(session, contains('if !interactive { overlay.releaseAllInputs() }'));
    expect(router, contains('setButton(pad: 1, source: "touch", index: index, pressed: pressed)'));
    expect(router, contains('setStick(pad: 1, source: "touch", stick: 1, x: leftX, y: -leftY)'));
    expect(router, contains('setStick(pad: 1, source: "touch", stick: 2, x: rightX, y: -rightY)'));
    expect(router, contains('index != Int32(VirtualControllerButton.guide.rawValue)'));
    // The session creates it after the router, pauses and lays it out, closes it before the router.
    final install = controller.substring(controller.indexOf('private func installControls'));
    expect(install.indexOf('let router = MeloNXInputRouter(') < install.indexOf('MeloNXSkinSession(game:game,router:router'), isTrue);
    expect(controller, contains('skinSession?.layout()'));
    // Since lot 9 (skin touches after the in-game menu) a resume syncs the skin now and again once the menu's sheet
    // has gone (MeloNXSkinInteraction.h, imported in Swift as syncNowAnd(whenUncovered:stillWanted:sync:)); a pause
    // keeps the single sync.
    expect(controller, contains('router?.suspend(!pauseReasons.isEmpty)\n        if let skinSession, pauseReasons.isEmpty {'));
    expect(controller, contains('MLXSkinInteraction.syncNowAnd(whenUncovered:self,'));
    expect(controller, isNot(contains('syncNowAndWhenUncovered(')), reason: 'the Objective-C spelling does not compile in Swift');
    expect(controller, contains('sync:{ [weak skinSession] in skinSession?.sync() })\n        } else {\n            skinSession?.sync()\n        }'));
    expect(controller.indexOf('self?.skinSession?.close()') < controller.indexOf('self?.router?.close()'), isTrue);
    expect(File('packages/melonx_internal_bridge/ios/Classes/MeloNXJitBridgePlugin.h').readAsStringSync(),
        contains('#import "MeloNXSkinOverlay.h"'), reason: 'Swift sees the overlay in the standalone typecheck too');
    // HOME and Capture are said, in twelve languages, never sent to the game.
    final strings = jsonDecode(File('build-utils/melonx/ui-strings.json').readAsStringSync()) as Map<String, dynamic>;
    for (final key in const ['HOME is not available with this Switch engine', 'Capture is not available with this Switch engine']) {
      final row = (strings['rows'] as Map<String, dynamic>)[key] as List<dynamic>;
      expect(row, hasLength(12), reason: key);
      expect(row.every((v) => (v as String).trim().isNotEmpty), isTrue);
      expect(session, contains('"$key"'));
    }
  });
}
