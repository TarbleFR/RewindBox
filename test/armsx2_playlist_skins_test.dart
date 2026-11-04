// PS2 playlist → Skins (maintainer report after IPA 640: "Il y a même pas
// l'option des skins via la playlist PS2 pour l'activer"). The real PS2
// playlist menu (Armsx2InternalPlaylistActions, the menu of my_games_list) must
// offer Skins, open the skins manager for the console `ps2`, where the shipped
// PS2 Pocket can be chosen; the choice is stored under the console's
// skin.portrait / skin.landscape keys of Config/Frontend/ps2.json, the file the
// native ARMSX2SkinOverlay reads at the next launch.
//
// Host widget tests: no iPhone, no native store (the bridge is a recorder that
// keeps the values like LibretroFrontendStore), no ARMSX2 Core.
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/screens/libretro/libretro_skin_manager_screen.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/libretro_skin_service.dart';
import 'package:neostation/widgets/armsx2_internal_playlist_actions.dart';
import 'package:neostation/widgets/liquid_progress.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

const _bridge = MethodChannel('neostation/libretro_internal');
const _gamepads = MethodChannel('xyz.luan/gamepads');
const _paths = MethodChannel('plugins.flutter.io/path_provider');

/// The frontend store as the skin screens use it, per console.
class _Store {
  final calls = <MethodCall>[];
  final consoles = <String, Map<String, Object?>>{};

  Future<Object?> handle(MethodCall call) async {
    calls.add(call);
    final arguments = (call.arguments as Map? ?? const {}).cast<String, Object?>();
    final console = consoles.putIfAbsent(arguments['console'] as String? ?? '', () => <String, Object?>{});
    switch (call.method) {
      case 'frontendSettings':
        return <String, Object?>{'console': Map<String, Object?>.of(console), 'games': <String, Object?>{}};
      case 'setFrontendSetting':
        final value = arguments['value'];
        if (value == null) {
          console.remove(arguments['key']);
        } else {
          console[arguments['key'] as String] = value;
        }
        return true;
      case 'skinPreview':
      case 'forgetSkin':
        return null;
    }
    return null;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final english = LibretroLocale.values['en']!;
  late Directory root;
  late _Store store;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    root = Directory.systemTemp.createTempSync('armsx2-playlist-skins-');
    store = _Store();
    messenger.setMockMethodCallHandler(_bridge, store.handle);
    messenger.setMockMethodCallHandler(_gamepads, (call) async => <dynamic>[]);
    messenger.setMockMethodCallHandler(_paths, (call) async => root.path);
  });

  tearDown(() {
    for (final channel in [_bridge, _gamepads, _paths]) {
      messenger.setMockMethodCallHandler(channel, null);
    }
    root.deleteSync(recursive: true);
  });

  Future<void> settle(WidgetTester tester, Finder until, {int rounds = 300}) async {
    for (var round = 0; round < rounds; round++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
      await tester.pump();
      if (until.evaluate().isNotEmpty &&
          find.byType(LinearProgressIndicator).evaluate().isEmpty &&
          find.byType(LiquidProgressIndicator).evaluate().isEmpty) {
        for (var extra = 0; extra < 5; extra++) {
          await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 5)));
          await tester.pump();
        }
        return;
      }
    }
    fail('Timed out waiting for $until');
  }

  Widget app(Widget home) => ScreenUtilInit(
        designSize: const Size(600, 1200),
        builder: (context, child) => MaterialApp(locale: const Locale('en'), home: home),
      );

  void phone(WidgetTester tester) {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
  }

  testWidgets('the PS2 playlist menu offers Skins and opens the skins manager of the PS2', (tester) async {
    phone(tester);
    await tester.pumpWidget(app(Scaffold(
      body: Align(
        alignment: Alignment.topRight,
        child: Armsx2InternalPlaylistActions(onLibraryChanged: () async {}),
      ),
    )));
    await tester.tap(find.byKey(const ValueKey('armsx2-internal-import-menu')));
    await tester.pumpAndSettle();
    final item = find.byKey(const ValueKey('armsx2-skins'));
    expect(item, findsOneWidget, reason: 'Skins in the PS2 playlist menu');
    expect(find.descendant(of: item, matching: find.text(english['skins']!)), findsOneWidget);
    expect(tester.widget<PopupMenuItem<String>>(item).enabled, isTrue);
    // The existing entries are still there, Skins added after Boot BIOS.
    final values = tester.widgetList<PopupMenuItem<String>>(find.byType(PopupMenuItem<String>)).map((i) => i.value).toList();
    expect(values.take(5), ['games', 'bios', 'choose_bios', 'boot_bios', 'skins']);

    await tester.tap(item);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    final manager = tester.widget<LibretroSkinManagerScreen>(find.byType(LibretroSkinManagerScreen));
    expect(manager.console, 'ps2', reason: 'the PS2 skins, not another console');
    await settle(tester, find.text(english['skinsLicenseNotice']!));
    expect(find.text(LibretroLocale.format(const Locale('en'), 'skinsTitle', {'console': 'Sony PlayStation 2'})),
        findsOneWidget, reason: 'the manager is titled with the PS2');
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  testWidgets('outside iOS the PS2 playlist shows no embedded-engine menu', (tester) async {
    await tester.pumpWidget(app(Scaffold(body: Armsx2InternalPlaylistActions(onLibraryChanged: () async {}))));
    expect(find.byKey(const ValueKey('armsx2-internal-import-menu')), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets('the shipped PS2 Pocket is chosen for both orientations, stored for ps2 and read back', (tester) async {
    phone(tester);
    final skins = LibretroSkinService(
      skinsDirectory: path.join(root.path, 'Libretro', 'Skins'),
      frontendDirectory: path.join(root.path, 'Libretro', 'Config', 'Frontend'),
      cacheDirectory: path.join(root.path, 'Cache'),
    );
    final imported = await tester.runAsync(() => skins.importFromFile(
          'assets/skins/pocket/ps2-pocket.manicskin',
          targetConsole: 'ps2',
          source: 'pocket-test-original-archive',
        ));
    expect(imported, isA<LibretroSkinImported>(),
        reason: imported is LibretroSkinImportFailed ? '${imported.messageKey}: ${imported.technicalDetails}' : '$imported');
    final installed = (imported as LibretroSkinImported).skin;
    expect(installed.consoles, ['ps2']);

    await tester.pumpWidget(app(LibretroSkinManagerScreen(console: 'ps2', service: skins)));
    await settle(tester, find.text(english['skinsLicenseNotice']!));
    expect(find.text('PS2 Pocket — Noir mat'), findsOneWidget);

    for (final (label, key) in [('skinsUseForPortrait', 'skin.portrait'), ('skinsUseForLandscape', 'skin.landscape')]) {
      final use = find.text(english[label]!).last;
      await tester.ensureVisible(use);
      await tester.tap(use);
      await settle(tester, find.text(LibretroLocale.format(const Locale('en'),
          key == 'skin.portrait' ? 'skinsSelectedPortrait' : 'skinsSelectedLandscape', {'name': 'PS2 Pocket — Noir mat'})));
      final stored = store.calls.where((call) => call.method == 'setFrontendSetting').last.arguments as Map;
      expect(stored['console'], 'ps2');
      expect(stored['game'], isNull, reason: 'the console choice, inherited by every PS2 game');
      expect(stored['key'], key);
      expect(stored['value'], installed.id);
      expect(stored['directory'], skins.frontendDirectory);
    }
    // Read back the way the screens and the next launch see it.
    final selected = await tester.runAsync(() => skins.selectedSkins('ps2'));
    expect(selected, {'portrait': installed.id, 'landscape': installed.id});
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));

  test('the stored choice reaches the file and folders ARMSX2SkinOverlay reads at launch', () async {
    // Dart side: Documents/Libretro/Config/Frontend and Documents/Libretro/Skins.
    final frontend = await LibretroInternalService.frontendDirectory();
    final skinsDirectory = await LibretroInternalService.skinsDirectory();
    expect(frontend.path, path.join(root.path, 'Libretro', 'Config', 'Frontend'));
    expect(skinsDirectory.path, path.join(root.path, 'Libretro', 'Skins'));
    expect(LibretroSkinService.selectionKey('portrait'), 'skin.portrait');
    // Native side (executed in the simulator by ARMSX2SkinOverlayTests on the
    // shipped archive): the overlay reads the same paths for the console ps2.
    final overlay = File('packages/armsx2_internal_bridge/ios/Classes/ARMSX2SkinOverlay.mm').readAsStringSync();
    expect(overlay, contains('[documents stringByAppendingPathComponent:@"Libretro"]'));
    expect(overlay, contains('[libretro stringByAppendingPathComponent:@"Config/Frontend"]'));
    expect(overlay, contains('NSString* console = @"ps2";'));
    expect(overlay, contains('[libretro stringByAppendingPathComponent:@"Skins"]'));
    // And the session creates the overlay with the launched game's key.
    final plugin = File('packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm').readAsStringSync();
    expect(plugin, contains('[[ARMSX2SkinOverlay alloc] initWithGameKey:self.touchGameKey]'));
    expect(plugin, contains('controller.touchGameKey = biosBoot ? nil : gamePath.lastPathComponent;'));
  });
}
