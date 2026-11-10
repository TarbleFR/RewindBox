import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/glass_performance_governor.dart';

void main() {
  final governor = GlassPerformanceGovernor.instance;

  setUp(() {
    governor.debugReset();
    governor.start();
  });

  tearDown(() => governor.debugReset());

  test('the full budget is spent when nothing competes for the GPU', () {
    expect(governor.blurBudget, 1);
    expect(governor.depthBudget, 1);
    expect(governor.decorativeMotion, isTrue);
  });

  test('an embedded game removes the blur pass entirely', () async {
    var notifications = 0;
    governor.addListener(() => notifications++);
    final owner = Object();
    await FrontendMediaGate.instance.hold(owner);
    expect(governor.emulationActive, isTrue);
    expect(governor.blurBudget, 0);
    expect(governor.decorativeMotion, isFalse);
    FrontendMediaGate.instance.release(owner);
    expect(governor.emulationActive, isFalse);
    expect(governor.blurBudget, 1);
    expect(notifications, 2);
  });

  test('Low Power Mode halves the blur and stops decorative motion', () {
    governor.lowPower = true;
    expect(governor.blurBudget, 0.5);
    expect(governor.depthBudget, 1);
    expect(governor.decorativeMotion, isFalse);
    governor.lowPower = false;
    expect(governor.blurBudget, 1);
  });

  testWidgets(
    'a memory warning drops blur and shadows for the relief window only',
    (tester) async {
      var notifications = 0;
      governor.addListener(() => notifications++);
      governor.noteMemoryPressure();
      expect(governor.blurBudget, 0);
      expect(governor.depthBudget, 0.5);
      expect(notifications, 1);
      // A second warning inside the window extends it without re-notifying.
      await tester.pump(const Duration(seconds: 60));
      governor.noteMemoryPressure();
      expect(notifications, 1);
      await tester.pump(const Duration(seconds: 60));
      expect(governor.memoryPressure, isTrue);
      await tester.pump(GlassPerformanceGovernor.memoryRelief);
      expect(governor.memoryPressure, isFalse);
      expect(governor.blurBudget, 1);
      expect(governor.depthBudget, 1);
      expect(notifications, 2);
    },
  );

  test('the binding observer path reports memory pressure too', () {
    governor.didHaveMemoryPressure();
    expect(governor.memoryPressure, isTrue);
    governor.debugEndRelief();
    expect(governor.memoryPressure, isFalse);
  });
}
