import 'dart:ui' show FrameTiming;

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/frontend_media_gate.dart';
import 'package:neostation/services/ui_refresh_rate_service.dart';
import 'package:ui_refresh_rate/ui_refresh_rate.dart';

Map<String, Object?> nativeState({
  String hookStatus = 'installed',
  bool storedEnabled = true,
  bool activeEnabled = true,
  int screenMaxHz = 120,
  double engineTargetHz = 120,
  bool lowPowerMode = false,
  int thermalState = 0,
}) => <String, Object?>{
  'hookStatus': hookStatus,
  'storedEnabled': storedEnabled,
  'activeEnabled': activeEnabled,
  'screenMaxHz': screenMaxHz,
  'engineTargetHz': engineTargetHz,
  'cappedHz': 60.0,
  'lowPowerMode': lowPowerMode,
  'thermalState': thermalState,
};

/// Fake native side: answers like UiRefreshRatePlugin.m (stored preference
/// in "NSUserDefaults", active snapshot fixed for the process).
class FakeNative {
  FakeNative({Map<String, Object?>? state}) : state = state ?? nativeState();

  Map<String, Object?> state;
  final List<MethodCall> calls = <MethodCall>[];
  PlatformException? failSetEnabled;
  PlatformException? failGetState;

  Future<Object?> handle(MethodCall call) async {
    calls.add(call);
    switch (call.method) {
      case 'getState':
        if (failGetState != null) throw failGetState!;
        return state;
      case 'setEnabled':
        if (failSetEnabled != null) throw failSetEnabled!;
        final enabled = (call.arguments as Map)['enabled'] as bool;
        state = <String, Object?>{...state, 'storedEnabled': enabled};
        return state;
    }
    throw MissingPluginException();
  }

  int count(String method) => calls.where((c) => c.method == method).length;
}

/// Frames as the engine reports them: [count] vsyncs [intervalMicros] apart.
List<FrameTiming> frames({
  required int start,
  required int count,
  required int intervalMicros,
}) => <FrameTiming>[
  for (var index = 0; index < count; index++)
    FrameTiming(
      vsyncStart: start + index * intervalMicros,
      buildStart: start + index * intervalMicros + 200,
      buildFinish: start + index * intervalMicros + 1500,
      rasterStart: start + index * intervalMicros + 1600,
      rasterFinish: start + index * intervalMicros + 3500,
      rasterFinishWallTime: start + index * intervalMicros + 3500,
    ),
];

/// Delivers a batch through the engine entry point, i.e. to every
/// registered timings callback (the framework's own debug one included).
void report(List<FrameTiming> timings) {
  final binding = TestWidgetsFlutterBinding.instance;
  binding.platformDispatcher.onReportTimings!(timings);
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  late FakeNative native;

  setUp(() {
    native = FakeNative();
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      UiRefreshRateChannel.channel,
      native.handle,
    );
  });

  tearDown(() {
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      UiRefreshRateChannel.channel,
      null,
    );
  });

  group('state', () {
    test('a ProMotion screen with the hook installed is available', () async {
      final service = UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      );
      final state = await service.refresh();
      expect(state.available, isTrue);
      expect(state.restartRequired, isFalse);
      expect(state.systemLimited, isFalse);
      expect(state.screenMaxHz, 120);
      expect(state.engineTargetHz, 120);
      expect(service.state, same(state));
    });

    test('a 60 Hz screen is unavailable even with the hook', () async {
      native.state = nativeState(screenMaxHz: 60, engineTargetHz: 60);
      final state = await UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      ).refresh();
      expect(state.hookInstalled, isTrue);
      expect(state.available, isFalse);
    });

    for (final status in <String>[
      'notInstalled',
      'classMissing',
      'methodMissing',
      'signatureMismatch',
    ]) {
      test('hook status $status makes the option unavailable', () async {
        native.state = nativeState(hookStatus: status);
        final state = await UiRefreshRateService.forTesting(
          gate: FrontendMediaGate(),
        ).refresh();
        expect(state.available, isFalse);
        expect(state.hookStatus, status);
      });
    }

    test(
      'Low Power Mode keeps the option usable and reports the limit',
      () async {
        // iOS can report 60 Hz for a ProMotion screen in Low Power Mode.
        native.state = nativeState(screenMaxHz: 60, lowPowerMode: true);
        final state = await UiRefreshRateService.forTesting(
          gate: FrontendMediaGate(),
        ).refresh();
        expect(state.screenCapabilityUnknown, isTrue);
        expect(state.available, isTrue);
        expect(state.systemLimited, isTrue);
      },
    );

    test('a serious thermal state is a system limit', () async {
      native.state = nativeState(thermalState: 2);
      final state = await UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      ).refresh();
      expect(state.thermalLimited, isTrue);
      expect(state.systemLimited, isTrue);
      expect(state.available, isTrue);
    });

    test('a missing plugin or a failing channel is unavailable', () async {
      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        UiRefreshRateChannel.channel,
        null,
      );
      final missing = await UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      ).refresh();
      expect(missing.hookStatus, UiRefreshRateState.hookPluginMissing);
      expect(missing.available, isFalse);

      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        UiRefreshRateChannel.channel,
        native.handle,
      );
      native.failGetState = PlatformException(code: 'BROKEN');
      final failing = await UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      ).refresh();
      expect(failing.hookStatus, 'BROKEN');
      expect(failing.available, isFalse);
    });
  });

  group('preference', () {
    test('a change is stored for the next launch, not applied now', () async {
      final service = UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      );
      await service.refresh();

      expect(await service.toggle(), isTrue);
      expect(native.calls.last.method, 'setEnabled');
      expect(native.calls.last.arguments, <String, Object?>{'enabled': false});
      expect(service.state!.storedEnabled, isFalse);
      expect(service.state!.activeEnabled, isTrue);
      expect(service.state!.restartRequired, isTrue);
      expect(service.error, isNull);

      expect(await service.toggle(), isTrue);
      expect(service.state!.storedEnabled, isTrue);
      expect(service.state!.restartRequired, isFalse);
    });

    test('SAVE_FAILED is surfaced and never shown as a saved choice', () async {
      final service = UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      );
      await service.refresh();
      native.failSetEnabled = PlatformException(code: 'SAVE_FAILED');

      expect(await service.setEnabled(false), isFalse);
      expect(service.error, UiRefreshRateError.saveFailed);
      expect(service.errorCode, 'SAVE_FAILED');
      expect(service.state!.storedEnabled, isTrue);
      expect(service.state!.restartRequired, isFalse);
      expect(service.saving, isFalse);

      native.failSetEnabled = null;
      expect(await service.setEnabled(false), isTrue);
      expect(service.error, isNull);
    });

    test('an answer that did not keep the choice is a save failure', () async {
      final service = UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      );
      await service.refresh();
      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        UiRefreshRateChannel.channel,
        (call) async => nativeState(storedEnabled: true),
      );
      expect(await service.setEnabled(false), isFalse);
      expect(service.error, UiRefreshRateError.saveFailed);
      expect(service.state!.storedEnabled, isTrue);
    });

    test('nothing is written while the option is unavailable', () async {
      native.state = nativeState(screenMaxHz: 60);
      final service = UiRefreshRateService.forTesting(
        gate: FrontendMediaGate(),
      );
      await service.refresh();
      expect(await service.toggle(), isFalse);
      expect(await service.setEnabled(false), isFalse);
      expect(native.count('setEnabled'), 0);
    });
  });

  group('passive measurement', () {
    late FrontendMediaGate gate;
    late DateTime now;
    late UiRefreshRateService service;

    setUp(() {
      gate = FrontendMediaGate();
      now = DateTime(2026, 10, 11, 12);
      service = UiRefreshRateService.forTesting(
        gate: gate,
        clock: () => now,
        reportWait: const Duration(milliseconds: 20),
      );
    });

    tearDown(() => service.dispose());

    testWidgets(
      'the probe registers once, schedules no frame and is removable',
      (tester) async {
        await tester.pump();
        expect(tester.binding.hasScheduledFrame, isFalse);

        service.startProbe();
        service.startProbe(); // idempotent
        await tester.idle();
        expect(service.probing, isTrue);
        expect(tester.binding.hasScheduledFrame, isFalse);
        expect(tester.binding.transientCallbackCount, 0);
        expect(native.count('getState'), 1);

        // Registered twice, each frame would be seen twice (zero intervals) and
        // no burst could ever be measured.
        report(frames(start: 1000000, count: 31, intervalMicros: 8333));
        expect(service.lastMeasurement!.effectiveHz, 120);
        expect(service.lastMeasurement!.intervals, 30);

        service.stopProbe();
        expect(service.probing, isFalse);
        report(frames(start: 9000000, count: 61, intervalMicros: 16667));
        expect(service.lastMeasurement!.effectiveHz, 120);
        expect(tester.binding.hasScheduledFrame, isFalse);
      },
    );

    test(
      'frames while a game holds the gate are counted, never measured',
      () async {
        service.startProbe();
        report(frames(start: 0, count: 61, intervalMicros: 8333));
        expect(service.lastMeasurement!.effectiveHz, 120);

        await gate.hold('game');
        report(frames(start: 2000000, count: 90, intervalMicros: 16667));
        expect(service.framesDuringGame, 90);
        expect(service.lastMeasurement!.effectiveHz, 120);
        expect(service.postGameMeasurement, isNull);
      },
    );

    test(
      'a released gate arms the post-game measurement (first burst only)',
      () async {
        service.startProbe();
        await gate.hold('game');
        report(frames(start: 0, count: 10, intervalMicros: 16667));
        gate.release('game');

        // A few frames are too short to measure, then a measurable burst.
        report(frames(start: 3000000, count: 5, intervalMicros: 8333));
        expect(service.postGameMeasurement, isNull);
        report(frames(start: 4000000, count: 20, intervalMicros: 16667));
        report(
          frames(start: 4000000 + 20 * 16667, count: 20, intervalMicros: 16667),
        );
        expect(service.postGameMeasurement!.effectiveHz, 60);
        expect(service.postGameMeasurement!.intervals, 39);

        // Later bursts update the current rate, not the post-game one.
        report(frames(start: 8000000, count: 61, intervalMicros: 8333));
        expect(service.lastMeasurement!.effectiveHz, 120);
        expect(service.postGameMeasurement!.effectiveHz, 60);
        expect(service.framesDuringGame, 10);
      },
    );

    test('a new game clears the previous post-game measurement', () async {
      service.startProbe();
      await gate.hold('game');
      gate.release('game');
      report(frames(start: 0, count: 40, intervalMicros: 16667));
      expect(service.postGameMeasurement!.effectiveHz, 60);

      await gate.hold('game');
      expect(service.postGameMeasurement, isNull);
      gate.release('game');
      report(frames(start: 9000000, count: 40, intervalMicros: 8333));
      expect(service.postGameMeasurement!.effectiveHz, 120);
    });

    test('the post-game window closes after 60 s without frames', () async {
      service.startProbe();
      await gate.hold('game');
      gate.release('game');
      now = now.add(const Duration(seconds: 61));
      report(frames(start: 0, count: 5, intervalMicros: 8333));
      report(frames(start: 500000, count: 40, intervalMicros: 8333));
      expect(service.lastMeasurement!.effectiveHz, 120);
      expect(service.postGameMeasurement, isNull);
    });

    test(
      'returning to the foreground after a game re-arms the window',
      () async {
        service.startProbe();
        await service.refresh(); // joins the read started by the probe
        final reads = native.count('getState');

        // An external game (RetroArch app): the gate is released while
        // NeoStation is in the background, the window would expire there.
        await gate.hold('game');
        gate.release('game');
        service.didChangeAppLifecycleState(AppLifecycleState.paused);
        now = now.add(const Duration(minutes: 10));
        service.didChangeAppLifecycleState(AppLifecycleState.resumed);
        await Future<void>.delayed(Duration.zero);
        expect(native.count('getState'), reads + 1, reason: 'state refreshed');

        report(frames(start: 0, count: 40, intervalMicros: 8333));
        expect(service.postGameMeasurement!.effectiveHz, 120);
      },
    );

    test(
      'a plain background trip without a game measures nothing post-game',
      () async {
        service.startProbe();
        service.didChangeAppLifecycleState(AppLifecycleState.paused);
        service.didChangeAppLifecycleState(AppLifecycleState.resumed);
        report(frames(start: 0, count: 40, intervalMicros: 8333));
        expect(service.lastMeasurement!.effectiveHz, 120);
        expect(service.postGameMeasurement, isNull);
      },
    );

    test(
      'a requested measurement keeps the longest burst it produced',
      () async {
        service.startProbe();
        report(frames(start: 0, count: 61, intervalMicros: 16667));
        expect(service.lastMeasurement!.effectiveHz, 60);

        service.beginMeasurement();
        expect(service.measuring, isTrue);
        report(frames(start: 2000000, count: 100, intervalMicros: 8333));
        final pending = service.completeMeasurement();
        report(
          frames(start: 2000000 + 100 * 8333, count: 81, intervalMicros: 8333),
        );
        final result = await pending;
        expect(result!.effectiveHz, 120);
        expect(result.intervals, 180);
        expect(service.measuring, isFalse);
        expect(service.measureFailed, isFalse);
        expect(service.lastMeasurement!.effectiveHz, 120);
      },
    );

    test(
      'a measurement without frames reports a failure, not a rate',
      () async {
        service.startProbe();
        service.beginMeasurement();
        final result = await service.completeMeasurement();
        expect(result, isNull);
        expect(service.measureFailed, isTrue);
        expect(service.lastMeasurement, isNull);
      },
    );
  });
}
