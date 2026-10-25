// Build 447 (docs/external-display-universal.md § 5, § 8 bis): an engine
// that cannot draw on the external screen hides NeoStation's window there for
// its session, so iOS mirrors the iPhone, and shows it again exactly once on
// every end path. The pairing runs in Dart:
// ExternalDisplayService.runUnsupportedEngineSession.
//
// KartPad, the engine this was written for, left NeoStation on 19 October
// 2026 (Dusklight, which paired natively, on 20 October); its channel group
// went with it. The service keeps its contract for
// any future engine in the same situation, driven here by a fake native
// coordinator. Source and channel behaviour only: no iPhone or Apple TV claim.
import 'dart:async';

import 'package:external_display/external_display.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/external_display_service.dart';

const suspend = 'suspendForUnsupportedEngine';
const resume = 'resumeAfterUnsupportedEngine';

/// Answers like ExternalDisplayPlugin.m for the two coordinator calls and
/// records them, with the other channels, in one ordered journal.
class FakeCoordinator {
  FakeCoordinator(this.journal);

  final List<String> journal;
  PlatformException? failSuspend;
  PlatformException? failResume;

  /// Runs inside the suspension call, before it answers.
  void Function()? duringSuspend;

  int count(String method) => journal.where((e) => e == method).length;

  /// The coordinator's single `suspended` flag after the calls so far.
  bool get hidden {
    final last = journal.lastWhere(
      (e) => e == suspend || e == resume,
      orElse: () => resume,
    );
    return last == suspend;
  }

  Future<Object?> handle(MethodCall call) async {
    switch (call.method) {
      case suspend:
        journal.add(suspend);
        duringSuspend?.call();
        if (failSuspend != null) throw failSuspend!;
        return true;
      case resume:
        journal.add(resume);
        if (failResume != null) throw failResume!;
        return true;
    }
    throw MissingPluginException();
  }
}

Future<void> settle() async {
  for (var i = 0; i < 10; ++i) {
    await Future<void>.delayed(Duration.zero);
  }
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  late List<String> journal;
  late FakeCoordinator native;
  late ExternalDisplayService service;

  setUp(() {
    journal = <String>[];
    native = FakeCoordinator(journal);
    service = ExternalDisplayService.forTesting(
      events: const Stream<ExternalDisplayState>.empty(),
    );
    debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      native.handle,
    );
  });

  tearDown(() {
    debugDefaultTargetPlatformOverride = null;
    binding.defaultBinaryMessenger.setMockMethodCallHandler(
      ExternalDisplayChannel.channel,
      null,
    );
  });

  group('runUnsupportedEngineSession', () {
    late StreamController<Map<String, Object?>> ended;

    setUp(() => ended = StreamController<Map<String, Object?>>.broadcast());
    tearDown(() => ended.close());

    Future<Map<String, Object?>> run(
      Future<Map<String, Object?>> Function() start,
    ) => service.runUnsupportedEngineSession<Map<String, Object?>>(
      engine: 'Engine',
      sessionEnded: ended.stream,
      start: start,
      sessionContinues: (answer) => answer['running'] == true,
    );

    test('hidden right before start, shown again at the end event', () async {
      final answer = await run(() async {
        journal.add('start');
        return {'running': true};
      });
      expect(answer, {'running': true});
      expect(journal, [suspend, 'start']);
      expect(service.unsupportedEngineHolds, 1);
      expect(native.hidden, isTrue);

      ended.add({'exitReason': 'userReturn'});
      await settle();
      expect(journal, [suspend, 'start', resume]);
      expect(service.unsupportedEngineHolds, 0);
      expect(native.hidden, isFalse);

      ended.add({'exitReason': 'userReturn'});
      await settle();
      expect(native.count(resume), 1, reason: 'a second end shows nothing');
    });

    test('an answer without a running session shows the window again '
        'before the caller gets it', () async {
      final answer = await run(() async => {'running': false});
      expect(answer, {'running': false});
      expect(journal, [suspend, resume]);
      expect(service.unsupportedEngineHolds, 0);

      ended.add({'exitReason': 'launchFailure'});
      await settle();
      expect(native.count(resume), 1);
    });

    test('a start that throws shows the window again and rethrows', () async {
      await expectLater(
        run(() async => throw PlatformException(code: 'CHANNEL_DOWN')),
        throwsA(isA<PlatformException>()),
      );
      expect(journal, [suspend, resume]);
      expect(service.unsupportedEngineHolds, 0);
    });

    test('an end reported while start is pending is not lost', () async {
      final pending = Completer<Map<String, Object?>>();
      final session = run(() => pending.future);
      await settle();
      expect(journal, [suspend]);

      ended.add({'exitReason': 'crash'});
      await settle();
      expect(journal, [suspend, resume]);

      pending.complete({'running': true});
      expect(await session, {'running': true});
      await settle();
      expect(native.count(resume), 1, reason: 'released once');
      expect(service.unsupportedEngineHolds, 0);
    });

    test('an end emitted before the session started is not taken for it',
        () async {
      native.duringSuspend = () => ended.add({'exitReason': 'earlier'});
      await run(() async => {'running': true});
      await settle();
      expect(journal, [suspend], reason: 'still hidden for this session');
      expect(service.unsupportedEngineHolds, 1);

      ended.add({'exitReason': 'userReturn'});
      await settle();
      expect(journal, [suspend, resume]);
    });

    test('overlapping holds share one suspension', () async {
      final other = StreamController<Map<String, Object?>>.broadcast();
      addTearDown(other.close);
      await run(() async => {'running': true});
      await service.runUnsupportedEngineSession<Map<String, Object?>>(
        engine: 'Engine',
        sessionEnded: other.stream,
        start: () async => {'running': true},
        sessionContinues: (answer) => answer['running'] == true,
      );
      expect(journal, [suspend]);
      expect(service.unsupportedEngineHolds, 2);

      ended.add({});
      await settle();
      expect(journal, [suspend], reason: 'the other session still runs');
      other.add({});
      await settle();
      expect(journal, [suspend, resume]);
      expect(service.unsupportedEngineHolds, 0);
    });

    test('an error on the end stream is not an end', () async {
      await run(() async => {'running': true});
      ended.addError(StateError('stream'));
      await settle();
      expect(journal, [suspend]);
      ended.add({});
      await settle();
      expect(journal, [suspend, resume]);
    });

    test('outside iOS the session runs alone', () async {
      debugDefaultTargetPlatformOverride = TargetPlatform.android;
      final answer = await run(() async => {'running': true});
      expect(answer, {'running': true});
      ended.add({});
      await settle();
      expect(journal, isEmpty);
      expect(service.unsupportedEngineHolds, 0);
    });

    test('a missing plugin never blocks the session', () async {
      binding.defaultBinaryMessenger.setMockMethodCallHandler(
        ExternalDisplayChannel.channel,
        null,
      );
      final answer = await run(() async => {'running': true});
      expect(answer, {'running': true});
      expect(service.unsupportedEngineHolds, 1);
      ended.add({});
      await settle();
      expect(service.unsupportedEngineHolds, 0);
    });

    test('a refused suspension still runs and pairs the release', () async {
      native.failSuspend = PlatformException(code: 'REFUSED');
      native.failResume = PlatformException(code: 'REFUSED');
      final answer = await run(() async {
        journal.add('start');
        return {'running': true};
      });
      expect(answer, {'running': true});
      ended.add({});
      await settle();
      expect(journal, [suspend, 'start', resume]);
      expect(service.unsupportedEngineHolds, 0);
    });
  });
}
