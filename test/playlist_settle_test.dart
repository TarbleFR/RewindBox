// While the selection of a playlist moves, only the light work runs; the art
// behind the panels and the rest of the selected game come once it rests
// (maintainer video of the DS playlist, 14 November 2026). At each game shown
// for the first time the screen froze for 0.1-0.9 s: its 1920 px art was
// decoded and cross-faded under the blurred panel, its RetroAchievements and
// description looked up, while the list was still scrolling.
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
  ConfigModel get config => ConfigModel.empty.copyWith(gameViewMode: 'list');
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late ThemeProvider theme;
  late Directory temp;
  late DatabaseTestHelper database;
  late PathProviderPlatform previousPaths;
  const system = SystemModel(
    id: 'nds',
    folderName: 'nds',
    realName: 'Nintendo DS',
    shortName: 'DS',
    iconImage: '',
    color: '#888888',
  );
  const roms = [
    '/library/nds/Harvest Moon DS.nds',
    '/library/nds/Hidden Mysteries.nds',
    '/library/nds/Hot Wheels.nds',
    '/library/nds/Iron Man.nds',
  ];

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
      'id': 'nds',
      'folder_name': 'nds',
      'real_name': 'Nintendo DS',
    });
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
      'system_id': 'nds',
      'extension': 'nds',
    });
    for (final rom in roms) {
      await db.insert('user_roms', {
        'filename': rom.split('/').last,
        'rom_path': rom,
        'app_system_id': 'nds',
      });
    }
    temp = await Directory.systemTemp.createTemp('rewindbox-playlist-settle-');
    previousPaths = PathProviderPlatform.instance;
    PathProviderPlatform.instance = _Paths(temp.path);
    LiquidMotionClock.instance.lowPower = true;
    SfxService().setEnabled(false);
    messenger.setMockMethodCallHandler(
      const MethodChannel('xyz.luan/gamepads'),
      (_) async => [],
    );
    messenger.setMockMethodCallHandler(
      const MethodChannel('neostation/neoplay/events'),
      (_) async => null,
    );
  });
  tearDown(() async {
    PathProviderPlatform.instance = previousPaths;
    LiquidMotionClock.instance.lowPower = false;
    SfxService().setEnabled(true);
    await database.tearDown();
    await temp.delete(recursive: true);
  });

  Future<void> settleIO(WidgetTester tester, {int rounds = 60}) async {
    for (var i = 0; i < rounds; i++) {
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 15)),
      );
      await tester.pump(const Duration(milliseconds: 50));
    }
  }

  Future<void> open(WidgetTester tester) async {
    // The test font (Ahem) draws every glyph as a full square: the footer's
    // Play label overflows its row here, never with the app's fonts.
    final previousOnError = FlutterError.onError;
    FlutterError.onError = (details) {
      if (details.exceptionAsString().contains('RenderFlex overflowed')) return;
      previousOnError?.call(details);
    };
    addTearDown(() => FlutterError.onError = previousOnError);
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
            home: SystemGamesList(system: system, fileProvider: FileProvider()),
          ),
        ),
      ),
    );
    await tester.pump();
    await settleIO(tester);
  }

  // The art behind the panels is keyed by its game.
  String? shownArt(WidgetTester tester) {
    for (final element in find
        .byWidgetPredicate(
          (w) =>
              w.key is ValueKey<String> &&
              (w.key! as ValueKey<String>).value.startsWith('list_fanart_'),
        )
        .evaluate()) {
      final key = (element.widget.key! as ValueKey<String>).value;
      // The cross-fade keeps the outgoing art a moment: the newest is last.
      return key;
    }
    return null;
  }

  List<String> allArt(WidgetTester tester) => [
        for (final element in find
            .byWidgetPredicate(
              (w) =>
                  w.key is ValueKey<String> &&
                  (w.key! as ValueKey<String>).value.startsWith(
                    'list_fanart_',
                  ),
            )
            .evaluate())
          (element.widget.key! as ValueKey<String>).value,
      ];

  Future<void> down(WidgetTester tester) async {
    await tester.runAsync(() async {
      await tester.sendKeyDownEvent(LogicalKeyboardKey.arrowDown);
      await tester.sendKeyUpEvent(LogicalKeyboardKey.arrowDown);
    });
  }

  testWidgets(
    'the art of the game left stays while the selection moves, then the new one comes',
    (tester) async {
      await open(tester);
      expect(shownArt(tester), contains(roms[0]));

      // Two quick steps down: the list follows them at once.
      await down(tester);
      await tester.pump(const Duration(milliseconds: 16));
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 160)),
      );
      await down(tester);
      await tester.pump(const Duration(milliseconds: 16));
      expect(
        tester
            .widgetList<Text>(find.byType(Text))
            .any((t) => (t.data ?? '').contains('Hot Wheels')),
        isTrue,
      );
      // The art is still the one of the game left, alone: none of the games
      // passed over was loaded behind the panels.
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 20));
        expect(allArt(tester).every((k) => k.contains(roms[0])), isTrue,
            reason: 'art ${allArt(tester)} after ${(i + 1) * 20} ms');
      }

      // Once the selection rests (a real timer, armed by the key event), the
      // art of the selected game comes.
      await tester.runAsync(
        () => Future<void>.delayed(const Duration(milliseconds: 400)),
      );
      await tester.pump(const Duration(milliseconds: 16));
      await tester.pump(const Duration(milliseconds: 600));
      expect(allArt(tester).last, contains(roms[2]));
      expect(allArt(tester).any((k) => k.contains(roms[1])), isFalse,
          reason: 'the game passed over never had its art loaded');
      await tester.pumpWidget(const SizedBox());
      await settleIO(tester, rounds: 5);
    },
  );
}
