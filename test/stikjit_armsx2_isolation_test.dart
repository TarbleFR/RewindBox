import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('ARMSX2 keeps its isolated helper after external MeloNX retirement', () {
    expect(File('lib/services/stikjit_melonx_service.dart').existsSync(), isFalse);

    final composite = File(
      'packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePlugin.swift',
    ).readAsStringSync();
    expect(composite, contains('LocalDevVpnRouteProbe.probe'));
    expect(composite, contains('FlutterMethodNotImplemented'));
    expect(composite, isNot(contains('enableMeloNxJit')));
    expect(composite, isNot(contains('StikjitArmsx2BridgePlugin')));
    expect(composite, isNot(contains('neostation/stikjit_armsx2')));
    expect(File('packages/stikjit_bridge/ios/Classes/Armsx2IdeviceRuntime.swift').existsSync(), isFalse);

    final host = File(
      'packages/armsx2_internal_bridge/ios/Classes/Armsx2JitBridgePlugin.mm',
    ).readAsStringSync();
    expect(host, contains('com.neogamelab.neostation.armsx2-jit-request'));
    expect(host, contains('NeoStationARMSX2JITHelper'));
    expect(host, contains('ARMSX2JitConfirmCoreLoadHandoff'));
    expect(host, contains('ARMSX2JitWaitForDetach'));

    final helper = File(
      'packages/armsx2_jit_helper/ios/Classes/Armsx2JITRequestHandlerBase.swift',
    ).readAsStringSync();
    expect(helper, contains('targetPID'));
    expect(helper, contains('StikJIT.enableJIT'));
    expect(helper, isNot(contains('launchArmsx2Suspended')));
  });
}
