import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/tools_settings_content.dart';

// Contract replaced: the global StikDebug fallback switch
// (`ios_stikdebug_fallback_v1`) is removed. Its only consumer was MeloNX,
// whose external path ran the pre-iOS 26 RX/RW probe that iOS 26 kills
// (user app.log of 27 October 2026: four launches killed at `jitProbe`).
// The integrated helper is now the only JIT method; a stale stored value is
// ignored (test/melonx_launch_flow_test.py drives that launch).
void main() {
  test('the StikDebug fallback preference and its strings are removed', () {
    expect(
      File('lib/services/jit_backend_preference_service.dart').existsSync(),
      isFalse,
    );
    expect(File('lib/l10n/jit_fallback_locale.dart').existsSync(), isFalse);
    for (final entity in Directory('lib').listSync(recursive: true)) {
      if (entity is! File || !entity.path.endsWith('.dart')) continue;
      final source = entity.readAsStringSync();
      expect(source, isNot(contains('ios_stikdebug_fallback_v1')), reason: entity.path);
      expect(source, isNot(contains('JitBackendPreferenceService')), reason: entity.path);
      expect(source, isNot(contains('JitFallbackLocale')), reason: entity.path);
    }
  });

  test('MeloNX always launches through the integrated helper', () {
    final launcher = File('lib/services/melonx_internal_service.dart').readAsStringSync();
    expect(launcher, contains("'jitBackend': 'builtin',"));
    expect(launcher, isNot(contains("'external'")));
    final bridge = File(
      'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
    ).readAsStringSync();
    expect(bridge, contains('arguments["jitBackend"] as? String == "builtin" else {'));
    expect(bridge, isNot(contains('"external"')));
    // iOS 26 always takes the helper's core-mapping handshake, never the
    // RX/RW alias probe.
    expect(
      bridge,
      contains('let universal = ProcessInfo.processInfo.operatingSystemVersion.majorVersion >= 26'),
    );
  });

  test('retired external MeloNX shortcut cannot bypass the embedded route', () {
    expect(File('lib/services/ios_shortcut_jit_launch_service.dart').existsSync(), isFalse);
    final launcher = File('lib/services/melonx_internal_service.dart').readAsStringSync();
    expect(launcher, isNot(contains('launchUrl')));
    expect(launcher, isNot(contains('StikJitMeloNxService')));
    expect(launcher, contains("MethodChannel('neostation/melonx_internal')"));
  });

  // Without the fallback row: pairing and NeoSwap everywhere, plus the BIOS
  // checker (Build 440) and the storage analysis (docs/storage-audit-cleanup.md
  // § 3.10) on iOS.
  test(
    'Tools has two controller entries, plus the BIOS checker and the '
    'storage analysis on iOS',
    () {
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      for (final platform in TargetPlatform.values) {
        debugDefaultTargetPlatformOverride = platform;
        final state =
            const ToolsSettingsContent(
                  isContentFocused: true,
                  selectedContentIndex: 0,
                ).createState()
                as ToolsSettingsContentState;

        expect(
          state.getItemCount(),
          platform == TargetPlatform.iOS ? 5 : 2,
          reason:
              'Controller navigation must match the visible tools on $platform',
        );
      }
    },
  );

  test('Tools preserves pairing, NeoSwap and the iOS BIOS checker without a fallback switch', () {
    final tools = File(
      'lib/screens/settings_screen/new_settings_options/'
      'tools_settings_content.dart',
    ).readAsStringSync();

    expect(tools, contains('if (index == 0)'));
    expect(tools, contains('if (index == 1)'));
    expect(tools, contains('builder: (_) => const NeoSwapDialog()'));
    // Index 2 is the iOS-only BIOS checker (Build 440), never NeoPlay.
    expect(tools, contains('if (index == 2 && _showBiosChecker)'));
    expect(
      tools,
      contains(
        'bool get _showBiosChecker => defaultTargetPlatform == TargetPlatform.iOS;',
      ),
    );
    expect(tools, contains('builder: (_) => const LibretroBiosCheckerScreen()'));
    expect(RegExp(r'index == 2').allMatches(tools).length, 1);
    // Index 3 is the iOS-only storage analysis (chantier 5), never NeoPlay.
    expect(tools, contains('if (index == 3 && _showStorageAudit)'));
    expect(RegExp(r'index == 3').allMatches(tools).length, 1);
    expect(tools, contains('builder: (_) => const StorageAuditScreen()'));
    // Index 4 is the iOS-only Cheats & Enhancements catalogue
    // (docs/ENHANCEMENTS.md), never NeoPlay.
    expect(tools, contains('if (index == 4 && _showEnhancements)'));
    expect(RegExp(r'index == 4').allMatches(tools).length, 1);
    expect(tools, contains('builder: (_) => const EnhancementsCatalogScreen()'));
    expect(tools, isNot(contains('index == 5')));
    expect(tools, isNot(contains('showNeoPlayDialog(context)')));
    expect(tools, isNot(contains('LocalJitTunnel')));
    expect(tools, isNot(contains('VPN')));
    expect(tools, isNot(contains('CustomToggleSwitch')));
    expect(tools, isNot(contains('StikDebugFallback')));
  });
}
