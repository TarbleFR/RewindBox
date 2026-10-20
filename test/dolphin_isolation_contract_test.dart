import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('Dolphin is routed before the general iOS launcher and only for gc/wii', () {
    final launcher = File(
      'lib/services/game/game_launch_service.dart',
    ).readAsStringSync();
    expect(launcher, contains('DolphinInternalV2Service.isDolphinSystem'));
    expect(
      launcher.indexOf('DolphinInternalV2Service.isDolphinSystem'),
      lessThan(launcher.indexOf('if (Platform.isIOS)')),
    );
    expect(launcher, contains('Rpcs3LaunchService.launchTitle'));
    expect(launcher, contains('MelonxInternalService.launch'));
    expect(launcher, contains('Armsx2LibraryService.launchGameByRomPath'));
    expect(launcher, contains('RetroArchLibraryService.launchGameByRomPath'));
  });

  test('Dolphin JIT policy is legacy-only and does not alter shared StikJIT', () {
    final helper = File(
      'packages/dolphin_jit_helper/ios/Classes/DolphinJITRequestHandlerBase.swift',
    ).readAsStringSync();
    expect(helper, contains('script: .legacy'));
    expect(helper, isNot(contains('.universal')));

    final shared = File('packages/stikjit_bridge/ios/Classes/NeoStationStikjitBridgePlugin.swift').readAsStringSync();
    expect(shared, contains('LocalDevVpnRouteProbe.probe'));
    expect(shared, isNot(contains('StikJIT.enableJIT')));
    expect(File('packages/stikjit_bridge/ios/Classes/StikjitBridgePlugin.swift').existsSync(), isFalse);
    expect(File('packages/stikjit_bridge/ios/Classes/StikjitBridgePluginV2.swift').existsSync(), isFalse);

  });

  test('Dolphin does not own generic executable extensions', () {
    final service = File(
      'lib/services/dolphin_internal_v2_service.dart',
    ).readAsStringSync();
    expect(service, isNot(contains("'elf'")));
    expect(service, isNot(contains("'dol'")));
    expect(service, contains("normalized == 'gc' || normalized == 'wii'"));
  });

  test('Dolphin rejects legacy Lockdown files before starting StikJIT', () {
    final service = File(
      'lib/services/dolphin_internal_v2_service.dart',
    ).readAsStringSync();
    expect(service, contains('PairingFileService.hasStoredPairingFile()'));
    expect(service, contains('PairingFileService.inspectData'));
    expect(service, contains('PairingFileValidation.validRemotePairing'));
  });
}
