import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/screens/settings_screen/new_settings_options/tools_settings_content.dart';
import 'package:neostation/services/jit_backend_preference_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() {
    SharedPreferences.setMockInitialValues({});
  });

  test('global JIT fallback defaults to integrated StikJIT', () async {
    expect(await JitBackendPreferenceService.useStikDebugFallback(), isFalse);
  });

  test('global JIT fallback persists both backend choices', () async {
    await JitBackendPreferenceService.setUseStikDebugFallback(true);
    expect(await JitBackendPreferenceService.useStikDebugFallback(), isTrue);

    await JitBackendPreferenceService.setUseStikDebugFallback(false);
    expect(await JitBackendPreferenceService.useStikDebugFallback(), isFalse);
  });

  test('global fallback remains scoped to the legacy MeloNX shortcut path', () {
    final launcher = File(
      'lib/services/ios_shortcut_jit_launch_service.dart',
    ).readAsStringSync();

    expect(
      launcher,
      contains('JitBackendPreferenceService.useStikDebugFallback()'),
    );
    expect(
      RegExp(
        r'!useStikDebugFallback\s*&&\s*shortcutName == melonxShortcutName',
      ).hasMatch(launcher),
      isTrue,
    );
    expect(launcher, isNot(contains('armsx2ShortcutName')));
    expect(launcher, isNot(contains('StikJitArmsx2Service')));
    expect(launcher, contains('final shortcutUri = buildRunUri'));
  });

  // Build 440 replaces the three-entry contract: screen sharing still lives
  // in the main menu, and iOS gains the BIOS checker of the embedded libretro
  // cores as a fourth entry. Chantier 5 (docs/storage-audit-cleanup.md
  // § 3.10) adds the storage analysis as a fifth entry on iOS. Every other
  // platform keeps exactly three.
  test(
    'Tools has three controller entries, plus the BIOS checker and the '
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
          platform == TargetPlatform.iOS ? 5 : 3,
          reason:
              'Controller navigation must match the visible tools on $platform',
        );
      }
    },
  );

  test('Tools preserves pairing, one fallback switch, NeoSwap and the iOS BIOS checker', () {
    final tools = File(
      'lib/screens/settings_screen/new_settings_options/'
      'tools_settings_content.dart',
    ).readAsStringSync();

    expect(tools, contains('if (index == 0)'));
    expect(tools, contains('if (index == 1 && _jitFallbackStateLoaded'));
    expect(tools, contains('if (index == 2)'));
    expect(tools, contains('builder: (_) => const NeoSwapDialog()'));
    // Index 3 is the iOS-only BIOS checker (Build 440), never NeoPlay.
    expect(tools, contains('if (index == 3 && _showBiosChecker)'));
    expect(
      tools,
      contains(
        'bool get _showBiosChecker => defaultTargetPlatform == TargetPlatform.iOS;',
      ),
    );
    expect(tools, contains('builder: (_) => const LibretroBiosCheckerScreen()'));
    expect(RegExp(r'index == 3').allMatches(tools).length, 1);
    // Index 4 is the iOS-only storage analysis (chantier 5), never NeoPlay.
    expect(tools, contains('if (index == 4 && _showStorageAudit)'));
    expect(RegExp(r'index == 4').allMatches(tools).length, 1);
    expect(tools, contains('builder: (_) => const StorageAuditScreen()'));
    expect(tools, isNot(contains('index == 5')));
    expect(tools, isNot(contains('showNeoPlayDialog(context)')));
    expect(RegExp(r'CustomToggleSwitch\(').allMatches(tools).length, 1);
    expect(tools, isNot(contains('LocalJitTunnel')));
    expect(tools, isNot(contains('VPN')));
    expect(tools, contains('JitFallbackLocale.title'));
    expect(tools, contains('CustomToggleSwitch'));
    expect(tools, contains('setUseStikDebugFallback'));
  });
}
