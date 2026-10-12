// The reader controller bindings (docs/library-books-3d-plan.md § 3.10):
// the right stick click (R3) reaches LibraryReaderGamepadBindings
// .rightStickClick through the real GamepadNavigation, and only it.
// Controller events are injected on the gamepads plugin channel with the
// Linux button numbering (the CI runs the Dart tests on Linux; the
// translator maps buttons per host platform). The face buttons are not
// pressed here: they play a sound through a native library the test host
// does not have; their bindings are covered by the reader tests.
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/library_screen/reader/library_reader_gamepad.dart';

import 'library_reader_test_support.dart';

/// Presses and releases controller button [key] (real time: the navigation
/// debounces with the wall clock).
Future<void> press(WidgetTester tester, String key) async {
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  for (final value in <double>[1.0, 0.0]) {
    await tester.runAsync(() async {
      await messenger.handlePlatformMessage(
        'xyz.luan/gamepads',
        const StandardMethodCodec().encodeMethodCall(
          MethodCall('onGamepadEvent', <String, Object>{
            'gamepadId': 'pad-1',
            'time': 0,
            'type': 'button',
            'key': key,
            'value': value,
          }),
        ),
        (_) {},
      );
      await Future<void>.delayed(const Duration(milliseconds: 40));
    });
  }
  // Past the action debounce before the next press.
  await tester.runAsync(
    () => Future<void>.delayed(const Duration(milliseconds: 150)),
  );
  await tester.pump();
}

void main() {
  setUpReaderEnvironment();

  testWidgets('R3 calls rightStickClick and no other binding', (tester) async {
    final calls = <String>[];
    void Function() record(String name) =>
        () => calls.add(name);
    await tester.pumpWidget(
      LibraryReaderGamepadScope(
        name: 'library_reader_gamepad_test',
        bindings: LibraryReaderGamepadBindings(
          up: record('up'),
          down: record('down'),
          left: record('left'),
          right: record('right'),
          select: record('a'),
          back: record('b'),
          leftBumper: record('lb'),
          rightBumper: record('rb'),
          x: record('x'),
          y: record('y'),
          start: record('start'),
          rightStickClick: record('r3'),
        ),
        child: const SizedBox.shrink(),
      ),
    );
    // The layer is pushed after the first frame; the first presses after
    // an activation are ignored for a short grace period.
    await tester.pump();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 250)),
    );

    await press(tester, 'button-10'); // R3 (Linux standard layout)
    expect(calls, <String>['r3']);
    await press(tester, 'button-10');
    expect(calls, <String>['r3', 'r3']);

    await tester.pumpWidget(const SizedBox.shrink());
  }, skip: !Platform.isLinux);

  testWidgets('without a rightStickClick binding R3 does nothing', (
    tester,
  ) async {
    final calls = <String>[];
    await tester.pumpWidget(
      LibraryReaderGamepadScope(
        name: 'library_reader_gamepad_test_unbound',
        bindings: LibraryReaderGamepadBindings(y: () => calls.add('y')),
        child: const SizedBox.shrink(),
      ),
    );
    await tester.pump();
    await tester.runAsync(
      () => Future<void>.delayed(const Duration(milliseconds: 250)),
    );
    await press(tester, 'button-10');
    expect(calls, isEmpty);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox.shrink());
  }, skip: !Platform.isLinux);
}
