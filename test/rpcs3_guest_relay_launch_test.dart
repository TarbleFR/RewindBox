import 'dart:async';
import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neo_swap/neo_swap.dart';
import 'package:neostation/services/rpcs3_internal_service.dart';

/// Build 610: every RPCS3 boot prepares the NeoSwap guest page relay first.
///
/// The Core maps its preallocated guest blocks during boot and a block mapped
/// before the relay is ready stays file-backed for the session. The bridge
/// waited for the relay only at Core load, and the relay shuts down when idle
/// after a session, so relaunches and game switches booted without it.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('neostation/neo_swap');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
    Rpcs3InternalService.guestRelayPreparer = NeoSwap.prepareGuestRelay;
    Rpcs3InternalService.guestRelayTimeout = const Duration(seconds: 12);
  });

  test('NeoSwap.prepareGuestRelay sends one bounded request', () async {
    final calls = <MethodCall>[];
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      return <String, Object?>{'result': 0, 'ok': true, 'waitedMs': 3.5};
    });

    final report = await NeoSwap.prepareGuestRelay();

    expect(calls, hasLength(1));
    expect(calls.single.method, 'prepareGuestRelay');
    expect(calls.single.arguments, {'timeoutMs': 10000});
    expect(report['ok'], isTrue);
    expect(() => NeoSwap.prepareGuestRelay(timeoutMs: -1), throwsArgumentError);
    expect(
      () => NeoSwap.prepareGuestRelay(timeoutMs: 10001),
      throwsArgumentError,
    );
  });

  test('a ready relay is reported before the boot', () async {
    var asked = 0;
    Rpcs3InternalService.guestRelayPreparer = ({int timeoutMs = 10000}) async {
      asked++;
      expect(timeoutMs, 10000);
      return {'result': 0, 'ok': true, 'relayEnabled': true, 'waitedMs': 2400.0};
    };

    final line = await Rpcs3InternalService.prepareGuestRelayForBoot(
      'BLES01717',
    );

    expect(asked, 1);
    expect(line, contains('BLES01717'));
    expect(line, contains('result=0 ok=true relayEnabled=true'));
    expect(line, contains('waitedMs=2400.0'));
  });

  test('a refused or missing relay never fails the launch', () async {
    Rpcs3InternalService.guestRelayPreparer = ({int timeoutMs = 10000}) async =>
        throw PlatformException(code: 'unavailable');
    expect(
      await Rpcs3InternalService.prepareGuestRelayForBoot('BCES00510'),
      contains('unavailable'),
    );

    Rpcs3InternalService.guestRelayPreparer = ({int timeoutMs = 10000}) async =>
        throw MissingPluginException();
    expect(
      await Rpcs3InternalService.prepareGuestRelayForBoot('BLES00158'),
      contains('unavailable'),
    );

    Rpcs3InternalService.guestRelayPreparer = ({int timeoutMs = 10000}) async =>
        {'result': -1, 'ok': false, 'relayEnabled': false, 'waitedMs': 0.0};
    expect(
      await Rpcs3InternalService.prepareGuestRelayForBoot('BLUS30110'),
      contains('result=-1 ok=false relayEnabled=false'),
    );
  });

  test('a native call that never answers is bounded on the Dart side', () async {
    final never = Completer<Map<String, dynamic>>();
    Rpcs3InternalService.guestRelayPreparer = ({int timeoutMs = 10000}) =>
        never.future;
    Rpcs3InternalService.guestRelayTimeout = const Duration(milliseconds: 50);

    final line = await Rpcs3InternalService.prepareGuestRelayForBoot(
      'BLES01717',
    );

    expect(line, contains('unavailable'));
    expect(line, contains('TimeoutException'));
  });

  test('the relay is prepared after the firmware check and before the boot', () {
    final service = File(
      'lib/services/rpcs3_internal_service.dart',
    ).readAsStringSync();
    final launch = service.indexOf('static Future<bool> launchTitle(');
    final firmware = service.indexOf("'firmwareRequired'", launch);
    final relay = service.indexOf(
      'await prepareGuestRelayForBoot(normalized);',
      launch,
    );
    final boot = service.indexOf('Rpcs3InternalBridge.launchGame(', launch);

    expect(launch, greaterThanOrEqualTo(0));
    expect(firmware, greaterThan(launch));
    expect(relay, greaterThan(firmware));
    expect(boot, greaterThan(relay));
    expect(
      RegExp(r'prepareGuestRelayForBoot\(normalized\)')
          .allMatches(service)
          .length,
      1,
    );
  });

  test('the native request waits off the main thread, bounded, and journals', () {
    final plugin = File(
      'packages/neo_swap/ios/Classes/NeoSwapPlugin.mm',
    ).readAsStringSync();
    final handler = plugin.indexOf(
      '- (void)handleMethodCall:(FlutterMethodCall*)call result:(FlutterResult)result {',
    );
    final branch = plugin.indexOf('@"prepareGuestRelay"', handler);
    final gate = plugin.indexOf('![call.method isEqualToString:@"snapshot"]', handler);
    final body = plugin.substring(branch, gate);

    expect(branch, greaterThan(handler));
    expect(gate, greaterThan(branch));
    // Relay-only symbols stay inside the NEOSWAP_RELAY build configuration.
    final guardStart = plugin.lastIndexOf('#if defined(NEOSWAP_RELAY)', branch);
    final guardEnd = plugin.indexOf('#endif', branch);
    expect(guardStart, greaterThan(handler));
    expect(guardEnd, greaterThan(branch));
    expect(guardEnd, lessThan(gate));
    expect(plugin.substring(guardStart, branch), isNot(contains('#endif')));
    expect(body, contains('[value longLongValue] > 10000'));
    expect(body, contains('dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0)'));
    expect(body.indexOf('NeoSwapRelay_Start();'), greaterThan(0));
    expect(
      body.indexOf('NeoSwapRelay_WaitReady(timeout)'),
      greaterThan(body.indexOf('NeoSwapRelay_Start();')),
    );
    expect(body, contains('NeoSwapExperimentProfile().relay()'));
    expect(body, contains('[self appendRecord:event];'));
    expect(body, contains('dispatch_async(dispatch_get_main_queue(), ^{ result(response); });'));
    expect(body, isNot(contains('NeoSwap_SetOwnerSessionActive')));
  });
}
