import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test(
    'iOS gamepad bridge discovers connected pads and emits canonical keys',
    () {
      final listener = File(
        'packages/gamepads_darwin/ios/Classes/GamepadsListener.swift',
      ).readAsStringSync();
      final plugin = File(
        'packages/gamepads_darwin/ios/Classes/GamepadsIosPlugin.swift',
      ).readAsStringSync();
      final translator = File(
        'lib/utils/gamepad_translator.dart',
      ).readAsStringSync();

      expect(listener, contains('GCController.controllers()'));
      expect(listener, contains('gamepad.valueChangedHandler'));
      expect(listener, contains('firstIndex(of: gamepad)'));

      expect(plugin, isNot(contains('sfSymbolsName')));
      expect(plugin, contains('("dpadup",'));
      expect(plugin, contains('("dpaddown",'));
      expect(plugin, contains('("leftthumbstickx",'));
      expect(plugin, contains('("a", gamepad.buttonA.value)'));

      expect(translator, contains('Platform.isWindows || Platform.isIOS'));
      expect(translator, contains('_translateNamedGamepadKey'));
      expect(translator, contains("case 'dpadup':"));
      expect(translator, contains("case 'leftthumbstickx':"));
      expect(translator, contains("case 'home':"));
    },
  );

  // Regression (27 October 2026): after a game the menu no longer followed the
  // controller until it was reconnected. GameController keeps one
  // valueChangedHandler per pad; RPCS3's input bridge replaced the menu's and
  // set it to nil at teardown, and the listener never reinstalled it for a
  // pad it already knew. The Swift and Objective-C++ halves cannot run on the
  // Linux test host, so their contract is checked here; the Dart side
  // (one reclaim per ended session) runs in test/game_audio_handoff_test.py.
  test('the menu takes the controller back when a game session ends', () {
    final listener = File(
      'packages/gamepads_darwin/ios/Classes/GamepadsListener.swift',
    ).readAsStringSync();
    final plugin = File(
      'packages/gamepads_darwin/ios/Classes/GamepadsIosPlugin.swift',
    ).readAsStringSync();
    final channel = File(
      'packages/gamepads_platform_interface/lib/'
      'method_channel_gamepads_platform_interface.dart',
    ).readAsStringSync();
    final manager = File(
      'lib/services/game_launch_manager.dart',
    ).readAsStringSync();
    final rpcs3 = File(
      'packages/rpcs3_internal_bridge/ios/Classes/RPCS3GameInputController.mm',
    ).readAsStringSync();

    final reclaim = listener.substring(
      listener.indexOf('func reclaimHandlers()'),
      listener.indexOf('@objc private func joystickDidConnect'),
    );
    expect(reclaim, contains('installHandler(on: gamepad)'));
    expect(reclaim, contains('handlerQueue = .main'));
    expect(plugin, contains('case "reclaimGamepads":'));
    expect(plugin, contains('gamepads.reclaimHandlers()'));
    expect(channel, contains("'reclaimGamepads'"));
    expect(manager, contains('Gamepads.reclaim()'));

    final unbind = rpcs3.substring(
      rpcs3.indexOf('- (void)unbindPhysicalController {'),
    );
    final unbindBody = unbind.substring(0, unbind.indexOf('\n}\n'));
    expect(unbindBody, isNot(contains('valueChangedHandler = nil')));
    expect(unbindBody, contains('= self.previousExtendedHandler;'));
    expect(
      rpcs3,
      contains('self.previousExtendedHandler = pad.valueChangedHandler;'),
    );
  });
}
