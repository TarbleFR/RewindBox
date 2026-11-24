import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/switch2_settings_locale.dart';
import 'package:neostation/services/s2arm_internal_service.dart';
import 'package:neostation/widgets/switch2_engine_settings_panel.dart';

/// The Switch 2 settings panel in its two scopes, through its test seams (no native side): a game without a settings
/// profile shows the global values read-only until "Customize for this game"; with one, its changes are the game's alone
/// and "Back to the global settings" removes it. The global scope keeps its controls.
void main() {
  const gid = '0400C3F00006E000';
  const en = Locale('en');
  const global = S2ArmSettings(resolutionScale: '0.75', docked: true);
  const resolution = ValueKey('s2arm-setting-resolution');
  const frameGeneration = ValueKey('s2arm-setting-frame-interpolation');

  Future<void> pump(WidgetTester tester, Widget panel) async {
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        builder: (context, _) => MaterialApp(home: Scaffold(body: SingleChildScrollView(child: panel))),
      ),
    );
    await tester.pumpAndSettle();
  }

  bool locked(WidgetTester tester) =>
      tester.widget<DropdownButton<String>>(find.byKey(resolution)).onChanged == null &&
      tester.widget<SwitchListTile>(find.byKey(frameGeneration)).onChanged == null;

  testWidgets('a game without a profile shows the global values read-only, then its own once customized', (tester) async {
    final calls = <String>[];
    var custom = false;
    var stored = global;
    await pump(
      tester,
      Switch2EngineSettingsPanel(
        gameId: gid,
        loadGame: (id) async {
          calls.add('load $id');
          return S2ArmGameSettings(custom: custom, settings: stored);
        },
        customizeGame: (id) async {
          calls.add('customize $id');
          custom = true;
          return S2ArmGameSettings(custom: custom, settings: stored);
        },
        saveGame: (id, settings) async {
          calls.add('save $id');
          stored = settings;
          return S2ArmGameSettings(custom: custom, settings: stored);
        },
        resetGame: (id) async {
          calls.add('reset $id');
          custom = false;
          stored = global;
          return const S2ArmGameSettings(custom: false, settings: global);
        },
        load: () async => fail('the game scope never reads the global settings itself'),
        save: (_) async => fail('the game scope never writes the global settings'),
      ),
    );
    expect(find.text(Switch2SettingsLocale.forLocale(en, 'gameUsesGlobal')), findsOneWidget);
    expect(find.byKey(const ValueKey('s2arm-game-customize')), findsOneWidget);
    expect(find.byKey(const ValueKey('s2arm-game-reset')), findsNothing);
    expect(find.byKey(const ValueKey('s2arm-global-scope')), findsNothing);
    expect(tester.widget<DropdownButton<String>>(find.byKey(resolution)).value, '0.75', reason: 'the global value is shown');
    expect(locked(tester), isTrue);

    await tester.tap(find.byKey(const ValueKey('s2arm-game-customize')));
    await tester.pumpAndSettle();
    expect(find.text(Switch2SettingsLocale.forLocale(en, 'gameUsesOwn')), findsOneWidget);
    expect(find.byKey(const ValueKey('s2arm-game-reset')), findsOneWidget);
    expect(locked(tester), isFalse);

    tester.widget<SwitchListTile>(find.byKey(frameGeneration)).onChanged!(true);
    await tester.pumpAndSettle();
    expect(stored.frameInterpolation, isTrue);
    expect(stored.resolutionScale, '0.75', reason: 'the other values stay those the profile was made from');
    expect(tester.widget<SwitchListTile>(find.byKey(frameGeneration)).value, isTrue);

    await tester.tap(find.byKey(const ValueKey('s2arm-game-reset')));
    await tester.pumpAndSettle();
    expect(find.byKey(const ValueKey('s2arm-game-customize')), findsOneWidget);
    expect(tester.widget<SwitchListTile>(find.byKey(frameGeneration)).value, isFalse, reason: 'the global value again');
    expect(locked(tester), isTrue);
    expect(calls, ['load $gid', 'customize $gid', 'save $gid', 'reset $gid']);
  });

  testWidgets('the global scope keeps its controls and says it applies to the games without a profile', (tester) async {
    S2ArmSettings? saved;
    await pump(
      tester,
      Switch2EngineSettingsPanel(
        load: () async => global,
        save: (settings) async => saved = settings,
        loadGame: (_) async => fail('the global scope never reads a game'),
      ),
    );
    expect(find.byKey(const ValueKey('s2arm-game-customize')), findsNothing);
    expect(find.byKey(const ValueKey('s2arm-game-reset')), findsNothing);
    expect(find.byKey(const ValueKey('s2arm-global-scope')), findsOneWidget);
    expect(find.text(Switch2SettingsLocale.forLocale(en, 'globalScope')), findsOneWidget);
    expect(locked(tester), isFalse);
    tester.widget<SwitchListTile>(find.byKey(frameGeneration)).onChanged!(true);
    await tester.pumpAndSettle();
    expect(saved?.frameInterpolation, isTrue);
    expect(saved?.resolutionScale, '0.75');
  });
}
