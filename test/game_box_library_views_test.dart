import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/config_model.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/screens/game_screen/game_list_view.dart';
import 'package:neostation/screens/game_screen/my_games_grid.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/widgets/game_box/game_box_card.dart';
import 'package:neostation/widgets/game_box/game_box_library.dart';
import 'package:neostation/widgets/marquee_text.dart';
import 'package:neostation/widgets/rainbow_selection_border.dart';
import 'package:neostation/themes/dark_theme.dart';
import 'package:path/path.dart' as p;
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// The 3D boxes in the grid and the list (docs/game-box-3d.md § 3): the
/// halo stays only on the selected title of the list, never around a box;
/// touching a box opens the common viewer without starting the game.

class _TestFileProvider extends FileProvider {
  _TestFileProvider(this.root);
  final String root;

  @override
  bool get isInitialized => true;

  @override
  String getMediaPath(String systemFolderName, String imageType, String romName, String extension) =>
      p.join(root, 'media', systemFolderName, imageType, '${FileProvider.stripRomExtension(romName)}.$extension');

  @override
  String getMediaDirectoryPath() => p.join(root, 'media');

  @override
  List<String> getEsdeMediaCandidates(String systemFolderName, String imageType, String romName) => const [];
}

class _StyleConfig extends SqliteConfigProvider {
  _StyleConfig(this.style);
  final String style;
  @override
  ConfigModel get config => ConfigModel.empty.copyWith(gameCarouselCardStyle: style, gameViewMode: 'grid');
}

final _png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
);

GameModel _game(String rom, String name) => GameModel(
      romname: rom, realname: name, name: name, year: '', developer: '', publisher: '',
      genre: '', players: '', rating: 0, systemId: 'ps2', systemFolderName: 'ps2',
      romPath: '/roms/ps2/$rom',
    );

final _system = SystemModel(id: 'ps2', folderName: 'ps2', realName: 'PlayStation 2', iconImage: '', color: '#2244aa');

final _games = [
  _game('a.iso', 'Ace'),
  _game('b.iso', 'A Very Long Adventure Title'),
  _game('c.iso', 'No Box Art'),
];

void main() {
  late Directory dir;
  late _TestFileProvider fp;

  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
    SfxService().setEnabled(false);
  });

  setUp(() {
    dir = Directory.systemTemp.createTempSync('game_box_views');
    fp = _TestFileProvider(dir.path);
    GameBoxLibrary.evictAll();
    final store = GameBoxMediaStore(fp);
    for (final g in _games.take(2)) {
      File(store.canonicalPath(g, 'ps2', 'box2d', 'png'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(_png);
    }
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
  });

  tearDown(() {
    GameBoxLaunchGate.leave();
    GameBoxLibrary.evictAll();
    dir.deleteSync(recursive: true);
  });

  Widget app(Widget child) => MediaQuery(
        data: const MediaQueryData(size: Size(1280, 720)),
        child: ScreenUtilInit(
          designSize: const Size(640, 360),
          builder: (context, _) => MaterialApp(
            theme: darkTheme,
            localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            home: Scaffold(body: child),
          ),
        ),
      );

  group('list', () {
    Future<void> pumpList(
      WidgetTester tester, {
      required int selected,
      FileProvider? fileProvider,
      List<String>? inspected,
      List<int>? confirmed,
    }) async {
      tester.view.physicalSize = const Size(1280, 720);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      Widget tree() => app(Row(children: [
        SizedBox(
          width: 400,
          child: GameListView(
            system: _system,
            games: _games,
            selectedIndex: selected,
            systemColor: Colors.blue,
            onGameSelected: (_) {},
            onGameConfirmed: () => confirmed?.add(selected),
            fileProvider: fileProvider,
            onInspectBox: (g) => inspected?.add(g.romname),
          ),
        ),
        const Expanded(child: SizedBox()),
      ]));
      await tester.pumpWidget(tree());
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));
      // The library rebuilds its list once its scroll position is known.
      await tester.pumpWidget(tree());
      await tester.pump(const Duration(milliseconds: 500));
    }

    Finder rowTitle(String text) =>
        find.descendant(of: find.byType(MarqueeText), matching: find.text(text));

    testWidgets('the halo is only on the selected title, beside its 3D box', (tester) async {
      await pumpList(tester, selected: 0, fileProvider: fp);
      expect(find.byType(RainbowSelectionBorder), findsOneWidget, reason: 'one halo');
      final halo = tester.getRect(find.byKey(const ValueKey('list_title_halo')));
      final boxes = find.byType(GameBoxCard);
      expect(boxes, findsNWidgets(2), reason: 'a 3D box for each game with a front scan');
      final box = tester.getRect(boxes.first);
      expect(halo.left, greaterThanOrEqualTo(box.right - 0.5), reason: 'never around the box');
      final title = tester.getRect(rowTitle('Ace'));
      expect(halo.left, lessThan(title.left));
      expect(halo.width, lessThan(title.width + 40), reason: 'proportioned to a short title');
      expect(halo.width, lessThan(400 * 0.5), reason: 'not the whole row');
      expect(halo.top, greaterThanOrEqualTo(box.top - 6));
      expect(halo.bottom, lessThanOrEqualTo(box.bottom + 6), reason: 'on the selected row');
    });

    testWidgets('the halo follows the selection and fits the new title', (tester) async {
      await pumpList(tester, selected: 0, fileProvider: fp);
      final short = tester.getRect(find.byKey(const ValueKey('list_title_halo')));
      await pumpList(tester, selected: 1, fileProvider: fp);
      await tester.pump(const Duration(milliseconds: 400));
      final long = tester.getRect(find.byKey(const ValueKey('list_title_halo')));
      expect(long.top, greaterThan(short.top), reason: 'moved to the next row');
      expect(long.width, greaterThan(short.width * 2), reason: 'a longer title, a longer halo');
      expect(long.right, lessThanOrEqualTo(400), reason: 'never wider than the row');
    });

    testWidgets('touching a box opens its viewer, not the game', (tester) async {
      final inspected = <String>[];
      final confirmed = <int>[];
      await pumpList(tester, selected: 0, fileProvider: fp, inspected: inspected, confirmed: confirmed);
      await tester.tap(find.byType(GameBoxCard).first);
      await tester.pump();
      expect(inspected, ['a.iso']);
      expect(confirmed, isEmpty);
      await tester.pump(const Duration(milliseconds: 500));
    });

    testWidgets('without box media the rows keep their former full-width highlight', (tester) async {
      await pumpList(tester, selected: 0);
      expect(find.byType(GameBoxCard), findsNothing);
      expect(find.byKey(const ValueKey('list_title_halo')), findsNothing);
      final halo = tester.getRect(find.byType(RainbowSelectionBorder));
      expect(halo.width, greaterThan(400 * 0.8));
      await tester.pump(const Duration(milliseconds: 500));
    });
  });

  group('grid', () {
    Future<void> pumpGrid(WidgetTester tester, String style, {List<int>? plays}) async {
      tester.view.physicalSize = const Size(1280, 720);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(ChangeNotifierProvider<SqliteConfigProvider>(
        create: (_) => _StyleConfig(style),
        child: app(GamesGrid(
          system: _system,
          games: _games,
          selectedIndex: 0,
          fileProvider: fp,
          onGameSelected: (_) {},
          onBack: () {},
          onPlay: () => plays?.add(1),
          onFavorite: () {},
          onRandom: () {},
        )),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 600));
    }

    testWidgets('Box style: 3D boxes without halo, the selected one a little larger', (tester) async {
      await pumpGrid(tester, 'box');
      expect(find.byType(GameBoxCard), findsNWidgets(2));
      expect(find.byType(RainbowSelectionBorder), findsNothing);
      final scales = tester.widgetList<AnimatedScale>(find.byType(AnimatedScale)).map((s) => s.scale).toList();
      expect(scales.where((s) => s > 1), hasLength(1), reason: 'only the selection stands out');
      await tester.pump(const Duration(seconds: 1));
    });

    testWidgets('touching the selected box opens the viewer without starting the game', (tester) async {
      final plays = <int>[];
      await pumpGrid(tester, 'box', plays: plays);
      await tester.tap(find.byType(GameBoxCard).first);
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 400));
      expect(find.byType(GameBoxInspector), findsOneWidget);
      expect(plays, isEmpty);
      await tester.tap(find.byKey(const ValueKey('game_box_back')));
      for (var i = 0; i < 10; i++) {
        await tester.pump(const Duration(milliseconds: 50));
      }
      expect(find.byType(GameBoxInspector), findsNothing);
      expect(find.byType(GameBoxCard), findsNWidgets(2), reason: 'the grid is still there');
      await tester.pump(const Duration(seconds: 1));
    });

    testWidgets('the fanart style keeps its halo', (tester) async {
      await pumpGrid(tester, 'fanart');
      expect(find.byType(GameBoxCard), findsNothing);
      expect(find.byType(RainbowSelectionBorder), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
    });
  });
}
