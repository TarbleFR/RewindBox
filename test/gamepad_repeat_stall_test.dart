// A held direction never runs ahead of the screen (maintainer video of the
// DS playlist, 14 November 2026). While a game shown for the first time froze
// the screen for up to 0.9 s, the repeat of the held D-pad kept moving the
// selection unseen, then fired once more before the release queued behind the
// freeze: the list jumped two games and the player had to come back one. A
// hold that spent its time behind a frozen screen also switched to letter
// jumps after 1.2 s, having moved only a few games.
//
// The navigation debounces with the wall clock, so the holds run in real time
// (tester.runAsync); frames are drawn only where the test pumps them.
import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/utils/gamepad_nav.dart';

Future<void> _wait(WidgetTester tester, int ms) =>
    tester.runAsync(() => Future<void>.delayed(Duration(milliseconds: ms)));

void main() {
  late GamepadNavigation nav;
  var steps = 0;
  var letterJumps = 0;

  Future<void> start(WidgetTester tester) async {
    SfxService().setEnabled(false);
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (_) async => <Object>[],
    );
    steps = 0;
    letterJumps = 0;
    nav = GamepadNavigation(
      onNavigateDown: () => steps++,
      onNavigateUp: () => steps--,
      onLetterJump: (forward) {
        letterJumps++;
        return true;
      },
      accelerateRepeats: true,
    );
    await tester.runAsync(() async {
      nav.initialize();
      await Future<void>.delayed(const Duration(milliseconds: 50));
    });
    nav.activate();
    // Past the reactivation grace of a freshly activated layer.
    await _wait(tester, 250);
    await tester.pump();
  }

  tearDown(() {
    nav.dispose();
    SfxService().setEnabled(true);
  });

  Future<void> press(WidgetTester tester) => tester.runAsync(
        () => tester.sendKeyDownEvent(LogicalKeyboardKey.arrowDown),
      );
  Future<void> release(WidgetTester tester) => tester.runAsync(
        () => tester.sendKeyUpEvent(LogicalKeyboardKey.arrowDown),
      );

  testWidgets('a held direction waits for the frame of its last step', (
    tester,
  ) async {
    await start(tester);
    await press(tester);
    expect(steps, 1);
    expect(nav.debugStepShown, isFalse);
    // Held well past the first repeats, with no frame drawn.
    await _wait(tester, 700);
    expect(steps, 1, reason: 'the first step is not on screen yet');
    // Frames are drawn again: the held direction moves on, never more than
    // one step per frame.
    var previous = steps;
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(milliseconds: 16));
      expect(steps - previous, lessThanOrEqualTo(1), reason: 'frame $i');
      previous = steps;
    }
    expect(steps, greaterThanOrEqualTo(3));
    await release(tester);
    final released = steps;
    for (var i = 0; i < 10; i++) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(steps, released, reason: 'nothing moves after the release');
  });

  testWidgets('frames keep coming: the hold repeats as before', (
    tester,
  ) async {
    await start(tester);
    await press(tester);
    for (var i = 0; i < 12; i++) {
      await tester.pump();
      await _wait(tester, 50);
    }
    await release(tester);
    expect(steps, greaterThan(3), reason: 'initial delay then the fast ramp');
    expect(letterJumps, 0);
  });

  testWidgets('a repeat run late lets the release queued behind it through', (
    tester,
  ) async {
    await start(tester);
    await press(tester);
    await tester.pump();
    expect(nav.debugStepShown, isTrue);
    await tester.runAsync(() async {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      // The isolate is busy past the first repeat (due 300 ms after the
      // press), the way a long frame holds it on the device.
      final busy = Stopwatch()..start();
      while (busy.elapsedMilliseconds < 500) {}
      // The release arrives behind the overdue repeat.
      Timer.run(() => tester.sendKeyUpEvent(LogicalKeyboardKey.arrowDown));
      await Future<void>.delayed(const Duration(milliseconds: 400));
    });
    await tester.pump();
    expect(steps, 1, reason: 'one press, one game');
  });

  testWidgets('a hold behind a slow screen does not start letter jumps', (
    tester,
  ) async {
    await start(tester);
    await press(tester);
    // About four frames a second for 1.6 s: the hold is long, but it moved
    // only a few games.
    for (var i = 0; i < 6; i++) {
      await _wait(tester, 270);
      await tester.pump();
      await tester.pump();
    }
    await release(tester);
    expect(letterJumps, 0);
    expect(steps, inInclusiveRange(2, 8));
  });
}
