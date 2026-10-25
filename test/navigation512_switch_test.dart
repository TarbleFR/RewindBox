import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
// Test the actual filesystem boundary without an iOS container.
// ignore: depend_on_referenced_packages
import 'package:path_provider_platform_interface/path_provider_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/melonx_library_locale.dart';
import 'package:neostation/l10n/melonx_transfer_locale.dart';
import 'package:neostation/models/config_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/providers/retro_achievements_provider.dart';
import 'package:neostation/providers/scraping_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/sqlite_database_provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/providers/system_background_provider.dart';
import 'package:neostation/screens/game_screen/my_games_list.dart';
import 'package:neostation/services/melonx_internal_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/widgets/liquid_motion_clock.dart';

import 'database_test_helper.dart';

class _Paths extends PathProviderPlatform {
  _Paths(this.root);
  final String root;
  @override
  Future<String?> getApplicationDocumentsPath() async => root;
}

class _Config extends SqliteConfigProvider {
  @override
  ConfigModel get config => ConfigModel.empty.copyWith(gameViewMode: 'grid');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late ThemeProvider theme;
  late Directory temp;
  late DatabaseTestHelper database;
  late PathProviderPlatform previousPaths;
  final nativeCalls = <String>[];
  const system = SystemModel(
    id: 'switch',
    folderName: 'switch',
    realName: 'Nintendo Switch',
    shortName: 'Switch',
    iconImage: '',
    color: '#FF0000',
  );

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('fr', AppLocale.fr)],
      initLanguageCode: 'fr',
    );
    theme = await ThemeProvider.create();
  });
  tearDownAll(() => theme.dispose());
  setUp(() async {
    database = DatabaseTestHelper();
    final db = await database.setUp();
    await db.insert('app_systems', {
      'id': 'switch',
      'folder_name': 'switch',
      'real_name': 'Nintendo Switch',
    });
    // The repository helper predates these existing production config fields.
    // Keep the real import/save path enabled with a complete fixture schema.
    final configColumns = (await db.rawQuery(
      'PRAGMA table_info(user_config)',
    )).map((row) => row['name']).toSet();
    for (final column in [
      'game_grid_columns',
      'legend_hidden',
      'game_details_tab',
      'hide_tab_achievements',
      'hide_tab_scraper',
      'hide_tab_search',
      'game_carousel_card_style',
      'dock_apps',
      'dock_enabled',
      'dock_slot_count',
      'now_playing_dim_delay',
      'now_playing_dim_level',
      'fanart_dim_level',
      'esde_folder_path',
    ]) {
      if (!configColumns.contains(column)) {
        await db.execute('ALTER TABLE user_config ADD COLUMN "$column" TEXT');
      }
    }
    await db.insert('app_system_extensions', {
      'system_id': 'switch',
      'extension': 'nro',
    });
    temp = await Directory.systemTemp.createTemp('rewindbox-navigation512-');
    previousPaths = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Paths(temp.path);
    LiquidMotionClock.instance.lowPower = true;
    nativeCalls.clear();
    SfxService().setEnabled(false);
    messenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (_) async => [],
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('neostation/neoplay/events'),
      (_) async => null,
    );
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, (
      call,
    ) async {
      nativeCalls.add(call.method);
      if (call.method == 'beginLibraryMutation') return true;
      if (call.method == 'endLibraryMutation') return null;
      final path = (call.arguments as Map?)?['path']?.toString() ?? '';
      return {
        'success': true,
        'title': path.contains('added')
            ? 'Added homebrew'
            : 'Existing homebrew',
        'titleId': '0100123456780000',
        'hasMainProgram': true,
      };
    });
  });
  tearDown(() async {
    messenger.setMockMethodCallHandler(MelonxInternalService.channel, null);
    PathProviderPlatform.instance = previousPaths;
    LiquidMotionClock.instance.lowPower = false;
    SfxService().setEnabled(true);
    await database.tearDown();
    await temp.delete(recursive: true);
  });

  Future<void> settleIO(WidgetTester tester) async {
    for (var i = 0; i < 100; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 15)),
      );
      await tester.pump(const Duration(milliseconds: 50));
    }
  }

  Future<void> open(WidgetTester tester) async {
    tester.view.physicalSize = const Size(956, 440);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.binding.setSurfaceSize(const Size(956, 440));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        minTextAdapt: true,
        splitScreenMode: true,
        builder: (_, _) => MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: theme),
            ChangeNotifierProvider<SqliteConfigProvider>(
              create: (_) => _Config(),
            ),
            ChangeNotifierProvider(create: (_) => SqliteDatabaseProvider()),
            ChangeNotifierProvider(create: (_) => ScrapingProvider()),
            ChangeNotifierProvider(create: (_) => RetroAchievementsProvider()),
            ChangeNotifierProvider(create: (_) => NeoAssetsProvider()),
            ChangeNotifierProvider(create: (_) => SystemBackgroundProvider()),
          ],
          child: MaterialApp(
            theme: AppThemes.darkTheme,
            locale: const Locale('fr'),
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: Builder(
              builder: (context) => Scaffold(
                body: Center(
                  child: TextButton(
                    onPressed: () => Navigator.of(context).push(
                      MaterialPageRoute<void>(
                        builder: (_) => SystemGamesList(
                          system: system,
                          fileProvider: FileProvider(),
                        ),
                      ),
                    ),
                    child: const Text('Open Switch'),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(find.text('Open Switch'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await settleIO(tester);
    debugPrint('SWITCH native calls: $nativeCalls');
  }

  test('empty Switch text and return labels exist in all twelve languages', () {
    for (final map in [
      AppLocale.en,
      AppLocale.es,
      AppLocale.ru,
      AppLocale.zh,
      AppLocale.zhHant,
      AppLocale.pt,
      AppLocale.fr,
      AppLocale.de,
      AppLocale.it,
      AppLocale.id,
      AppLocale.ja,
      AppLocale.ko,
    ]) {
      expect(map[AppLocale.noGamesFoundFor], contains('{name}'));
      expect(map[AppLocale.back], isNotEmpty);
    }
  });

  testWidgets(
    'first empty Switch access keeps import available and returns to the same playlist without scan setup',
    (tester) async {
      await open(tester);
      expect(
        find.byKey(const ValueKey('switch-playlist-empty')),
        findsOneWidget,
      );
      expect(find.byType(Switch), findsNothing);
      expect(find.byKey(const ValueKey('melonx-import-menu')), findsOneWidget);
      expect(nativeCalls, isNot(contains('launch')));
      await tester.tap(
        find
            .text(
              AppLocale.back.getString(
                tester.element(find.byType(SystemGamesList)),
              ),
            )
            .last,
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await settleIO(tester);
      expect(find.byType(SystemGamesList), findsNothing);
      expect(find.text('Open Switch'), findsOneWidget);
      await tester.tap(find.text('Open Switch'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      await settleIO(tester);
      expect(
        find.byKey(const ValueKey('switch-playlist-empty')),
        findsOneWidget,
      );
      expect(find.byType(Switch), findsNothing);
      // Linux host events exercise the real controller parser and route owner.
      // The unchanged iOS named-event mappings retain their earlier proof.
      for (final value in [1.0, 0.0]) {
        await tester.runAsync(
          () => messenger.handlePlatformMessage(
            'xyz.luan/gamepads',
            const StandardMethodCodec().encodeMethodCall(
              MethodCall('onGamepadEvent', {
                'gamepadId': 'test-pad',
                'time': DateTime.now().millisecondsSinceEpoch,
                'type': 'button',
                'key': 'button-1',
                'value': value,
              }),
            ),
            null,
          ),
        );
        await tester.pump();
      }
      await settleIO(tester);
      expect(find.byType(SystemGamesList), findsNothing);
      expect(find.text('Open Switch'), findsOneWidget);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(seconds: 2));
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );

  testWidgets(
    'first Switch access discovers existing embedded files and manual rescan reveals a newly added game',
    (tester) async {
      final file = File('${temp.path}/MeloNX/games/nested/existing.nro');
      await tester.runAsync(() async {
        await file.parent.create(recursive: true);
        await file.writeAsString('personal homebrew');
      });
      await open(tester);
      expect(find.byKey(const ValueKey('switch-playlist-empty')), findsNothing);
      expect(find.textContaining('Existing homebrew'), findsWidgets);
      final added = File('${temp.path}/MeloNX/roms/switch/added.nro');
      await tester.runAsync(() async {
        await added.parent.create(recursive: true);
        await added.writeAsString('another personal homebrew');
      });
      await tester.tap(find.byKey(const ValueKey('melonx-import-menu')));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      final context = tester.element(find.byType(SystemGamesList));
      await tester.tap(find.text(MelonxTransferLocale.text(context, 'rescan')));
      await tester.pump();
      await settleIO(tester);
      debugPrint('AFTER RESCAN: $nativeCalls');
      expect(find.textContaining('Added homebrew'), findsWidgets);
      expect(find.byType(Switch), findsNothing);
      expect(nativeCalls, isNot(contains('launch')));
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
      await tester.pump(const Duration(seconds: 2));
    },
    variant: TargetPlatformVariant.only(TargetPlatform.iOS),
  );
  testWidgets('import a new Switch game directly from the empty playlist', (
    tester,
  ) async {
    final source = File('${temp.path}/personal/added.nro');
    await tester.runAsync(() async {
      await source.parent.create(recursive: true);
      await source.writeAsString('user supplied homebrew');
    });
    messenger.setMockMethodCallHandler(
      const MethodChannel('miguelruivo.flutter.plugins.filepicker'),
      (_) async => [
        {'name': 'added.nro', 'path': source.path, 'size': 22},
      ],
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('miguelruivo.flutter.plugins.filepickerevent'),
      (_) async => null,
    );
    addTearDown(() {
      messenger.setMockMethodCallHandler(
        const MethodChannel('miguelruivo.flutter.plugins.filepicker'),
        null,
      );
      messenger.setMockMethodCallHandler(
        const MethodChannel('miguelruivo.flutter.plugins.filepickerevent'),
        null,
      );
    });
    await open(tester);
    expect(find.byKey(const ValueKey('switch-playlist-empty')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('melonx-import-menu')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    await tester.tap(
      find.text(MelonxLibraryLocale.text(const Locale('fr'), 'Import games')),
    );
    await tester.pump();
    await settleIO(tester);
    expect(
      await tester.runAsync(
        () => File('${temp.path}/MeloNX/roms/switch/added.nro').exists(),
      ),
      isTrue,
    );
    expect(find.byKey(const ValueKey('switch-playlist-empty')), findsNothing);
    expect(find.textContaining('Added homebrew'), findsWidgets);
    expect(find.byType(Switch), findsNothing);
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(seconds: 2));
  }, variant: TargetPlatformVariant.only(TargetPlatform.iOS));
}
