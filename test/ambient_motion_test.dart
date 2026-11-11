// Decorative loops (selected-game rainbow outline, startup glint, music
// indicator) stop while an embedded game runs, in Low Power Mode and with
// reduced motion, so no frame is scheduled for them under the emulator.
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/glass_performance_governor.dart';
import 'package:neostation/widgets/rainbow_selection_border.dart';
import 'package:neostation/widgets/shimmering_logo.dart';

Widget _app(Widget child, {bool disableAnimations = false}) => MaterialApp(
  home: MediaQuery(
    data: MediaQueryData(disableAnimations: disableAnimations),
    child: Center(child: child),
  ),
);

const _border = RainbowSelectionBorder(
  borderRadius: BorderRadius.all(Radius.circular(8)),
  child: SizedBox(width: 80, height: 80),
);

bool _framesScheduled(WidgetTester tester) =>
    SchedulerBinding.instance.hasScheduledFrame;

void main() {
  final owner = Object();

  tearDown(() {
    FrontendMediaGate.instance.release(owner);
    GlassPerformanceGovernor.instance.debugReset();
  });

  testWidgets('the rainbow outline turns only while nothing forbids it', (
    tester,
  ) async {
    await tester.pumpWidget(_app(_border));
    await tester.pump(const Duration(milliseconds: 100));
    expect(_framesScheduled(tester), isTrue, reason: 'idle menu: it turns');

    unawaited(FrontendMediaGate.instance.hold(owner));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(_framesScheduled(tester), isFalse, reason: 'game running: still');

    FrontendMediaGate.instance.release(owner);
    await tester.pump();
    expect(_framesScheduled(tester), isTrue, reason: 'back to the menu');

    GlassPerformanceGovernor.instance.debugReset(lowPower: true);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 100));
    expect(_framesScheduled(tester), isFalse, reason: 'Low Power Mode');
  });

  testWidgets('reduced motion draws a still outline', (tester) async {
    await tester.pumpWidget(_app(_border, disableAnimations: true));
    await tester.pump(const Duration(milliseconds: 100));
    expect(_framesScheduled(tester), isFalse);
    expect(find.byType(CustomPaint), findsWidgets);
  });

  testWidgets('the startup glint follows progress even under a game', (
    tester,
  ) async {
    unawaited(FrontendMediaGate.instance.hold(owner));
    await tester.pumpWidget(_app(const ShimmeringLogo()));
    await tester.pump(const Duration(milliseconds: 100));
    expect(_framesScheduled(tester), isFalse, reason: 'ambient sweep stops');

    await tester.pumpWidget(_app(const ShimmeringLogo(progress: 0.5)));
    await tester.pump();
    expect(_framesScheduled(tester), isTrue, reason: 'progress still moves');
    await tester.pumpAndSettle();
  });
}
