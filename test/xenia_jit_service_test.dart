import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/xenia_locale.dart';
import 'package:neostation/services/xenia_jit_service.dart';

/// XeniaJitService: the Core's jitState decides whether the dedicated XeniOS
/// helper attaches, and how (docs/xenios-playlist.md § JIT helper).
void main() {
  late List<String> calls;
  late Map<String, dynamic> prepareResult;
  late Map<String, dynamic> completeResult;

  void wire(
    Map<String, dynamic> state, {
    bool pairing = true,
    bool route = true,
  }) {
    calls = <String>[];
    XeniaJitService.jitState = () async => state;
    XeniaJitService.pairingFile = () async {
      calls.add('pairing');
      return pairing ? File('/tmp/pairing.plist') : null;
    };
    XeniaJitService.probeRoute = () async {
      calls.add('route');
      if (!route) {
        throw PlatformException(code: 'localdevvpn_route_unavailable');
      }
    };
    XeniaJitService.prepareJit =
        ({
          required String pairingFilePath,
          required bool requiresCoreHandshake,
        }) async {
          calls.add('prepare:handshake=$requiresCoreHandshake');
          return prepareResult;
        };
    XeniaJitService.completeJit = () async {
      calls.add('complete');
      return completeResult;
    };
  }

  setUp(() {
    prepareResult = <String, dynamic>{
      'success': true,
      'helperConnected': true,
      'pidAttached': true,
      'debugged': true,
    };
    completeResult = <String, dynamic>{'success': true};
  });

  test('the Core decides the plan', () {
    expect(
      XeniaJitService.planFor({'needsTool': true, 'toolAttached': false}),
      XeniaJitPlan.attachForCoreHandshake,
    );
    expect(
      XeniaJitService.planFor({'needsTool': true, 'toolAttached': true}),
      XeniaJitPlan.reuseAttachedTool,
    );
    expect(
      XeniaJitService.planFor({'needsTool': false, 'debugged': true}),
      XeniaJitPlan.ready,
    );
    expect(
      XeniaJitService.planFor({'needsTool': false, 'debugged': false}),
      XeniaJitPlan.attachClassic,
    );
  });

  test(
    'a prepared region or a debugged non-TXM process needs no helper',
    () async {
      wire({'needsTool': false, 'debugged': true});
      final outcome = await XeniaJitService.ensure();
      expect(outcome.success, isTrue);
      expect(outcome.plan, XeniaJitPlan.ready);
      expect(
        calls,
        isEmpty,
        reason: 'a second session reuses the Core region without a new attach',
      );
    },
  );

  test('a tool still attached from an earlier attempt is reused', () async {
    wire({'needsTool': true, 'toolAttached': true, 'debugged': true});
    final outcome = await XeniaJitService.ensure();
    expect(outcome.plan, XeniaJitPlan.reuseAttachedTool);
    expect(calls, isEmpty);
  });

  test(
    'TXM on iOS 26: the helper stays attached for the Core handshake, no completion here',
    () async {
      wire({'needsTool': true, 'toolAttached': false, 'debugged': false});
      final outcome = await XeniaJitService.ensure();
      expect(outcome.success, isTrue);
      expect(
        calls,
        ['pairing', 'route', 'prepare:handshake=true'],
        reason:
            'the launch waits for the Core-issued detach (XeniaJitWaitForDetach)',
      );
    },
  );

  test(
    'not debugged and no tool needed: classic attach, then its completion',
    () async {
      wire({'needsTool': false, 'debugged': false});
      final outcome = await XeniaJitService.ensure();
      expect(outcome.success, isTrue);
      expect(calls, [
        'pairing',
        'route',
        'prepare:handshake=false',
        'complete',
      ]);
    },
  );

  test('failures are distinct facts with their own message', () async {
    wire({'needsTool': true, 'toolAttached': false}, pairing: false);
    expect((await XeniaJitService.ensure()).error, 'pairingRequired');
    expect(calls, ['pairing']);

    wire({'needsTool': true, 'toolAttached': false}, route: false);
    final route = await XeniaJitService.ensure();
    expect(route.error, 'jitAttachFailed');
    expect(calls, [
      'pairing',
      'route',
    ], reason: 'no helper without the LocalDevVPN route');

    for (final missing in [
      'success',
      'helperConnected',
      'pidAttached',
      'debugged',
    ]) {
      wire({'needsTool': true, 'toolAttached': false});
      prepareResult = <String, dynamic>{
        'success': true,
        'helperConnected': true,
        'pidAttached': true,
        'debugged': true,
        missing: false,
        'message': 'helper said no',
      };
      final outcome = await XeniaJitService.ensure();
      expect(outcome.error, 'jitAttachFailed', reason: missing);
      expect(outcome.detail, 'helper said no');
    }

    wire({'needsTool': false, 'debugged': false});
    prepareResult = <String, dynamic>{
      'success': true,
      'helperConnected': true,
      'pidAttached': true,
      'debugged': true,
    };
    completeResult = <String, dynamic>{
      'success': false,
      'message': 'timed out',
    };
    final incomplete = await XeniaJitService.ensure();
    expect(incomplete.error, 'jitHelperIncomplete');

    wire({'error': 'shaderConverterMissing'});
    expect((await XeniaJitService.ensure()).error, 'shaderConverterMissing');
    expect(calls, isEmpty);
  });

  test(
    'every JIT failure has a localized message; native stages map onto them',
    () {
      for (final key in [
        'pairingRequired',
        'jitAttachFailed',
        'jitHelperIncomplete',
        'jitUnavailable',
      ]) {
        expect(XeniaLocale.launchErrorKey(key), key);
        for (final code in XeniaLocale.values.keys) {
          expect(
            XeniaLocale.values[code]![key],
            isNotEmpty,
            reason: '$code:$key',
          );
        }
      }
      expect(
        XeniaLocale.launchErrorKey('jitHandshakeFailed'),
        'jitAttachFailed',
      );
      expect(
        XeniaLocale.launchErrorKey('jitDetachFailed'),
        'jitHelperIncomplete',
      );
    },
  );
}
