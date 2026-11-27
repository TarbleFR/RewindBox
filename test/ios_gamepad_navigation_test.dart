import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/utils/gamepad_nav.dart';

class _MobileNavigation extends GamepadNavigation {
  _MobileNavigation({required super.onNavigateDown});

  @override
  bool get isDesktop => false;
}

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
  testWidgets('the menu takes the controller back when a game session ends', (
    tester,
  ) async {
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

    // A modal can close before controller discovery answers. Disposal must
    // release keyboard input on iOS too, and stale initialization must never
    // register a listener after the next layer has taken ownership.
    const nativeChannel = MethodChannel('xyz.luan/gamepads');
    final messenger = tester.binding.defaultBinaryMessenger;
    final pending = <Completer<List<Object>>>[];
    messenger.setMockMethodCallHandler(nativeChannel, (_) {
      final result = Completer<List<Object>>();
      pending.add(result);
      return result.future;
    });
    final sfxWasEnabled = SfxService().isEnabled;
    SfxService().setEnabled(false);
    var steps = 0;
    final nav = _MobileNavigation(onNavigateDown: () => steps++);
    Future<void> pressDown() async {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 180)),
      );
      await tester.sendKeyDownEvent(LogicalKeyboardKey.arrowDown);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
    }

    Future<void> nativeEventAfterDispose(String id) async {
      // Any leaked event subscription would query this newly seen device.
      await messenger.handlePlatformMessage(
        nativeChannel.name,
        const StandardMethodCodec().encodeMethodCall(
          MethodCall('onGamepadEvent', {
            'gamepadId': id,
            'time': DateTime.now().millisecondsSinceEpoch,
            'type': 'button',
            'key': '0',
            'value': 1.0,
          }),
        ),
        null,
      );
      await tester.pump();
    }

    try {
      nav.initialize();
      await tester.pump();
      expect(pending, hasLength(1));
      nav.activate();
      nav.dispose();
      expect(nav.isActive, isFalse);
      pending[0].complete([]);
      await tester.pump();
      nav.activate();
      await pressDown();
      expect(steps, 0);
      await nativeEventAfterDispose('closed-before-discovery');
      expect(pending, hasLength(1));

      // Reinitialization is supported; an older concurrent call completing
      // last must neither duplicate nor replace the current subscription.
      nav.initialize();
      nav.initialize();
      await tester.pump();
      expect(pending, hasLength(3));
      pending[2].complete([]);
      await tester.pump();
      pending[1].complete([]);
      await tester.pump();
      nav.activate();
      await pressDown();
      expect(steps, 1);

      nav.dispose();
      await tester.pump();
      expect(nav.isActive, isFalse);
      // Reactivation alone cannot resurrect removed keyboard/native handlers.
      nav.activate();
      await pressDown();
      expect(steps, 1);
      await nativeEventAfterDispose('closed-after-reinitialization');
      expect(pending, hasLength(3));
    } finally {
      nav.dispose();
      for (final result in pending) {
        if (!result.isCompleted) result.complete([]);
      }
      messenger.setMockMethodCallHandler(nativeChannel, null);
      SfxService().setEnabled(sfxWasEnabled);
    }
  });
}
