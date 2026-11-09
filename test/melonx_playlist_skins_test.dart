// Nintendo Switch playlist → Skins (maintainer request of 9 November: "Le skin doit être
// accessible dans le menu de la playlist Switch via l'entrée Skins, comme pour les autres
// consoles : choix → enregistrement pour cette console → relecture → lancement MeloNX →
// affichage effectif"). The real Switch playlist menu (MelonxInternalPlaylistActions, the
// menu of my_games_list for the MeloNX library) offers Skins and opens the skins manager
// for the console `switch`; Switch Pocket is chosen for both orientations, stored under
// skin.portrait / skin.landscape of Config/Frontend/switch.json and read back; that is the
// file and the folders the native MeloNXSkinOverlay reads when MeloNX launches, and the
// MeloNX session creates the overlay for the launched game.
//
// Host widget tests: no iPhone, no native store (the bridge is a recorder that keeps the
// values like LibretroFrontendStore), no MeloNX Core. The overlay itself runs in the iOS
// Simulator (packages/melonx_internal_bridge/ci, MeloNXSkinOverlayTests).
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/screens/libretro/libretro_skin_manager_screen.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/libretro_skin_service.dart';
import 'package:neostation/widgets/liquid_progress.dart';
import 'package:neostation/widgets/melonx_internal_playlist_actions.dart';
import 'package:path/path.dart' as path;
import 'package:shared_preferences/shared_preferences.dart';

const _bridge = MethodChannel('neostation/libretro_internal');
const _gamepads = MethodChannel('xyz.luan/gamepads');
const _paths = MethodChannel('plugins.flutter.io/path_provider');

/// The shipped Switch Pocket archive (or, before its original board is in the
/// repository, a provisional build named by SWITCH_POCKET_ARCHIVE for local checks).
String get _switchPocket =>
    Platform.environment['SWITCH_POCKET_ARCHIVE'] ??
    'assets/skins/pocket/switch-pocket.manicskin';

/// The frontend store as the skin screens use it, per console.
class _Store {
  final calls = <MethodCall>[];
  final consoles = <String, Map<String, Object?>>{};

  Future<Object?> handle(MethodCall call) async {
    calls.add(call);
    final arguments = (call.arguments as Map? ?? const {})
        .cast<String, Object?>();
    final console = consoles.putIfAbsent(
      arguments['console'] as String? ?? '',
      () => <String, Object?>{},
    );
    switch (call.method) {
      case 'frontendSettings':
        return <String, Object?>{
          'console': Map<String, Object?>.of(console),
          'games': <String, Object?>{},
        };
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
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  final english = LibretroLocale.values['en']!;
  late Directory root;
  late _Store store;

  setUp(() {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    root = Directory.systemTemp.createTempSync('melonx-playlist-skins-');
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

  Future<void> settle(
    WidgetTester tester,
    Finder until, {
    int rounds = 300,
  }) async {
    for (var round = 0; round < rounds; round++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 5)),
      );
      await tester.pump();
      if (until.evaluate().isNotEmpty &&
          find.byType(LinearProgressIndicator).evaluate().isEmpty &&
          find.byType(LiquidProgressIndicator).evaluate().isEmpty) {
        for (var extra = 0; extra < 5; extra++) {
          await tester.runAsync(
            () => Future<void>.delayed(const Duration(milliseconds: 5)),
          );
          await tester.pump();
        }
        return;
      }
    }
    fail('Timed out waiting for $until');
  }

  Widget app(Widget home) => ScreenUtilInit(
    designSize: const Size(600, 1200),
    builder: (context, child) =>
        MaterialApp(locale: const Locale('en'), home: home),
  );

  void phone(WidgetTester tester) {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
  }

  testWidgets(
    'the Switch playlist menu offers Skins and opens the skins manager of the Switch',
    (tester) async {
      phone(tester);
      await tester.pumpWidget(
        app(
          Scaffold(
            body: Align(
              alignment: Alignment.topRight,
              child: MelonxInternalPlaylistActions(
                onLibraryChanged: () async {},
              ),
            ),
          ),
        ),
      );
      await tester.tap(find.byKey(const ValueKey('melonx-import-menu')));
      // The menu opens over a playlist whose engine status may still be loading (an
      // indefinite progress animation): fixed pumps instead of settling.
      for (var i = 0; i < 6; i++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      final item = find.byKey(const ValueKey('melonx-skins'));
      expect(item, findsOneWidget, reason: 'Skins in the Switch playlist menu');
      expect(
        find.descendant(of: item, matching: find.text(english['skins']!)),
        findsOneWidget,
      );
      expect(tester.widget<PopupMenuItem<String>>(item).enabled, isTrue);

      await tester.tap(item);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      final manager = tester.widget<LibretroSkinManagerScreen>(
        find.byType(LibretroSkinManagerScreen),
      );
      expect(
        manager.console,
        'switch',
        reason: 'the Switch skins, not another console',
      );
      await settle(tester, find.text(english['skinsLicenseNotice']!));
      expect(
        find.text(
          LibretroLocale.format(const Locale('en'), 'skinsTitle', {
            'console': 'Nintendo Switch',
          }),
        ),
        findsOneWidget,
        reason: 'the manager is titled with the Switch',
      );
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  testWidgets('outside iOS the Switch playlist shows no embedded-engine menu', (
    tester,
  ) async {
    await tester.pumpWidget(
      app(
        Scaffold(
          body: MelonxInternalPlaylistActions(onLibraryChanged: () async {}),
        ),
      ),
    );
    expect(find.byKey(const ValueKey('melonx-import-menu')), findsNothing);
  }, variant: TargetPlatformVariant.only(TargetPlatform.android));

  testWidgets(
    'Switch Pocket is chosen for both orientations, stored for switch and read back',
    (tester) async {
      phone(tester);
      expect(
        File(_switchPocket).existsSync(),
        isTrue,
        reason:
            'Switch Pocket ships with its original board (docs/design/pocket/approved-switch.png, '
            'tools/skins/build_switch_pocket.py); SWITCH_POCKET_ARCHIVE names a provisional build',
      );
      final skins = LibretroSkinService(
        skinsDirectory: path.join(root.path, 'Libretro', 'Skins'),
        frontendDirectory: path.join(
          root.path,
          'Libretro',
          'Config',
          'Frontend',
        ),
        cacheDirectory: path.join(root.path, 'Cache'),
      );
      final imported = await tester.runAsync(
        () => skins.importFromFile(
          _switchPocket,
          targetConsole: 'switch',
          source: 'pocket-test-switch-archive',
        ),
      );
      expect(
        imported,
        isA<LibretroSkinImported>(),
        reason: imported is LibretroSkinImportFailed
            ? '${imported.messageKey}: ${imported.technicalDetails}'
            : '$imported',
      );
      final installed = (imported as LibretroSkinImported).skin;
      expect(installed.consoles, ['switch']);
      expect(installed.identifier, 'org.rewindbox.switch-pocket');

      await tester.pumpWidget(
        app(LibretroSkinManagerScreen(console: 'switch', service: skins)),
      );
      await settle(tester, find.text(english['skinsLicenseNotice']!));
      expect(find.text('Switch Pocket'), findsOneWidget);

      for (final (label, key) in [
        ('skinsUseForPortrait', 'skin.portrait'),
        ('skinsUseForLandscape', 'skin.landscape'),
      ]) {
        final use = find.text(english[label]!).last;
        await tester.ensureVisible(use);
        await tester.tap(use);
        await settle(
          tester,
          find.text(
            LibretroLocale.format(
              const Locale('en'),
              key == 'skin.portrait'
                  ? 'skinsSelectedPortrait'
                  : 'skinsSelectedLandscape',
              {'name': 'Switch Pocket'},
            ),
          ),
        );
        final stored =
            store.calls
                    .where((call) => call.method == 'setFrontendSetting')
                    .last
                    .arguments
                as Map;
        expect(stored['console'], 'switch');
        expect(
          stored['game'],
          isNull,
          reason: 'the console choice, inherited by every Switch game',
        );
        expect(stored['key'], key);
        expect(stored['value'], installed.id);
        expect(stored['directory'], skins.frontendDirectory);
      }
      // Read back the way the screens and the next launch see it.
      final selected = await tester.runAsync(
        () => skins.selectedSkins('switch'),
      );
      expect(selected, {'portrait': installed.id, 'landscape': installed.id});
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  test(
    'the stored choice reaches the file and folders MeloNXSkinOverlay reads when MeloNX launches',
    () async {
      final frontend = await LibretroInternalService.frontendDirectory();
      final skinsDirectory = await LibretroInternalService.skinsDirectory();
      expect(
        frontend.path,
        path.join(root.path, 'Libretro', 'Config', 'Frontend'),
      );
      expect(skinsDirectory.path, path.join(root.path, 'Libretro', 'Skins'));
      expect(LibretroSkinService.selectionKey('portrait'), 'skin.portrait');
      // Native side (executed in the simulator by MeloNXSkinOverlayTests): the overlay
      // reads the same paths for the console switch.
      final overlay = File(
        'packages/melonx_internal_bridge/ios/Classes/MeloNXSkinOverlay.mm',
      ).readAsStringSync();
      expect(overlay, contains('stringByAppendingPathComponent:@"Libretro"]'));
      expect(
        overlay,
        contains('stringByAppendingPathComponent:@"Config/Frontend"]'),
      );
      expect(overlay, contains('@"switch"'));
      expect(overlay, contains('stringByAppendingPathComponent:@"Skins"]'));
      // And the MeloNX session creates it for the launched game, routes it to the Core's
      // pad and gives it the game's place (MeloNXSkinSession).
      final session = File(
        'packages/melonx_internal_bridge/ios/Classes/MeloNXMetalSessionViewController.swift',
      ).readAsStringSync();
      expect(
        session,
        contains(
          'MeloNXSkinSession(game:game,router:router,host:view,surface:surface',
        ),
      );
      final skin = File(
        'packages/melonx_internal_bridge/ios/Classes/MeloNXSkinSession.swift',
      ).readAsStringSync();
      expect(
        skin,
        contains('MeloNXSkinOverlay(gameKey: game.lastPathComponent)'),
      );
      expect(
        skin,
        contains('router?.skinButton(Int32(button), pressed: pressed)'),
      );
      expect(
        skin,
        contains(
          'router?.skinSticks(leftX: lx, leftY: ly, rightX: rx, rightY: ry)',
        ),
      );
    },
  );
}
