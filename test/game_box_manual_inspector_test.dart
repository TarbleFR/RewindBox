import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/screens/game_box/game_box_scan_viewer.dart';
import 'package:neostation/screens/game_screen/game_manual_reader_screen.dart';
import 'package:neostation/services/game_box/game_box_manual.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_launch_manager.dart';
import 'package:neostation/services/game_manual_service.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

/// The viewer's navigation and the manual in the box (docs/game-box-3d.md
/// § 11): Library → viewer → open box → manual → open box → viewer → library,
/// never a launch on the way, the same PDF as Game Settings › Manual, never
/// downloaded twice, and a manual downloaded later appears at once.

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

final _png = base64Decode(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==',
);

GameModel _game() => const GameModel(
      romname: 'Box Test (USA).iso',
      realname: 'Box Test',
      name: 'Box Test',
      year: '',
      developer: '',
      publisher: '',
      genre: '',
      players: '',
      rating: 0,
      systemId: 'ps2',
      systemFolderName: 'ps2',
      romPath: '/roms/ps2/Box Test (USA).iso',
    );

final _system = SystemModel(id: 'ps2', folderName: 'ps2', realName: 'PlayStation 2', iconImage: '', color: '#2244aa');

Future<void> _frames(WidgetTester tester, Duration total) async {
  const step = Duration(milliseconds: 32);
  var elapsed = Duration.zero;
  while (elapsed < total) {
    await tester.pump(step);
    elapsed += step;
  }
}

/// The library under the viewer: counts its own creations and keeps a
/// selection, so that the tests see whether coming back reloads it.
class _Library extends StatefulWidget {
  const _Library({required this.open});
  final void Function(BuildContext context) open;
  @override
  State<_Library> createState() => _LibraryState();
}

int _libraryCreations = 0;

class _LibraryState extends State<_Library> {
  int selected = 3;

  @override
  void initState() {
    super.initState();
    _libraryCreations++;
  }

  @override
  Widget build(BuildContext context) => Scaffold(
        body: Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text('selected $selected'),
            ElevatedButton(onPressed: () => widget.open(context), child: const Text('open')),
          ]),
        ),
      );
}

void main() {
  late Directory dir;
  late _TestFileProvider fp;
  late Widget Function(String, String) defaultReader;
  late String manualPath;
  var renders = 0;
  var downloads = 0;
  final readerPaths = <String>[];

  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    defaultReader = GameBoxInspector.manualReader;
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
  });

  setUp(() {
    dir = Directory.systemTemp.createTempSync('game_box_manual');
    fp = _TestFileProvider(dir.path);
    final store = GameBoxMediaStore(fp);
    for (final folder in ['box2d', GameBoxMediaFolders.back]) {
      File(store.canonicalPath(_game(), 'ps2', folder, 'png'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(_png);
    }
    manualPath = _game().getManualPath('ps2', fp);
    renders = 0;
    downloads = 0;
    readerPaths.clear();
    _libraryCreations = 0;
    GameBoxManualCover.debugRenderer = (path) async {
      renders++;
      return null; // plain cover: the PDF engine is not part of these tests
    };
    GameManualService.debugDownloader = (game, system) async {
      downloads++;
      File(manualPath)
        ..createSync(recursive: true)
        ..writeAsStringSync('%PDF-1.4');
      return const GameManualDownload(success: true, messageKey: AppLocale.manualDownloaded);
    };
    GameBoxInspector.manualReader = (path, title) {
      readerPaths.add(path);
      return Scaffold(body: Center(child: Text('reader of $title')));
    };
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
  });

  tearDown(() {
    GameBoxLaunchGate.leave();
    GameBoxManualCover.debugRenderer = null;
    GameManualService.debugDownloader = null;
    GameBoxInspector.manualReader = defaultReader;
    dir.deleteSync(recursive: true);
  });

  void writeManual() => File(manualPath)
    ..createSync(recursive: true)
    ..writeAsStringSync('%PDF-1.4');

  Future<GameBoxInspectorState> open(
    WidgetTester tester, {
    required VoidCallback onPlay,
    bool reduceMotion = false,
    bool withSystem = true,
  }) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
      supportedLocales: FlutterLocalization.instance.supportedLocales,
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
        child: child!,
      ),
      home: _Library(
        open: (context) => GameBoxInspector.open(
          context,
          onPlay: onPlay,
          subject: GameBoxSubject(
            game: _game(),
            systemFolder: 'ps2',
            fileProvider: fp,
            systemId: 'ps2',
            system: withSystem ? _system : null,
          ),
        ),
      ),
    ));
    // The localization delegates load before the first page is shown.
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.text('open'));
    await tester.pump();
    await _frames(tester, const Duration(milliseconds: 500));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pump();
    return tester.state<GameBoxInspectorState>(find.byType(GameBoxInspector));
  }

  Future<void> openBox(WidgetTester tester) async {
    await tester.tap(find.byKey(const ValueKey('game_box_open')));
    await _frames(tester, const Duration(milliseconds: 1200));
  }

  final back = find.byKey(const ValueKey('game_box_back'));

  testWidgets('Back, at the top left, returns to the library as it was', (tester) async {
    var plays = 0;
    await open(tester, onPlay: () => plays++);
    expect(back, findsOneWidget);
    final corner = tester.getTopLeft(back);
    expect(corner.dx, lessThan(40));
    expect(corner.dy, lessThan(40));
    expect(find.text('Back'), findsOneWidget, reason: 'labelled Back');
    await tester.tap(back);
    await _frames(tester, const Duration(milliseconds: 400));
    expect(find.byType(GameBoxInspector), findsNothing);
    expect(find.text('selected 3'), findsOneWidget, reason: 'the selection is kept');
    expect(_libraryCreations, 1, reason: 'the library is not rebuilt from scratch');
    expect(plays, 0, reason: 'Back never starts the game');
  });

  testWidgets('Open the box: the inside without a launch; Back closes it, Back again leaves', (tester) async {
    writeManual();
    var plays = 0;
    final state = await open(tester, onPlay: () => plays++);
    await openBox(tester);
    expect(state.inside, GameBoxInsideState.open);
    expect(state.phase, GameBoxInspectorPhase.inspecting);
    expect(GameBoxLaunchGate.busy, isFalse);
    expect(find.byKey(const ValueKey('game_box_manual_chip')), findsOneWidget);
    expect(find.textContaining('Manual: '), findsOneWidget);
    expect(renders, 1, reason: 'the first page is drawn once the box is opened');
    await tester.tap(back);
    await _frames(tester, const Duration(milliseconds: 900));
    expect(state.inside, GameBoxInsideState.closed);
    expect(find.byType(GameBoxInspector), findsOneWidget, reason: 'one level at a time');
    await tester.tap(back);
    await _frames(tester, const Duration(milliseconds: 400));
    expect(find.byType(GameBoxInspector), findsNothing);
    expect(plays, 0);
  });

  testWidgets('the manual opens in the manual reader on the same PDF, the box is still open on return', (tester) async {
    writeManual();
    var plays = 0;
    final state = await open(tester, onPlay: () => plays++);
    await openBox(tester);
    final yaw = state.pose.yaw;
    await tester.tap(find.byKey(const ValueKey('game_box_manual_chip')));
    await _frames(tester, const Duration(milliseconds: 900));
    expect(find.text('reader of Box Test'), findsOneWidget);
    expect(readerPaths, [manualPath]);
    expect(manualPath, GameManualService.pathFor(_game(), 'ps2', fp), reason: 'the file of Game Settings › Manual');
    Navigator.of(tester.element(find.text('reader of Box Test'))).pop();
    await _frames(tester, const Duration(milliseconds: 900));
    expect(find.text('reader of Box Test'), findsNothing);
    expect(state.inside, GameBoxInsideState.open, reason: 'back to the open box');
    expect(state.pose.yaw, closeTo(yaw, 1e-9), reason: 'at the same angle');
    expect(find.byKey(const ValueKey('game_box_manual_chip')), findsOneWidget);
    expect(downloads, 0, reason: 'a manual on the device is never downloaded again');
    expect(plays, 0, reason: 'reading the manual never starts the game');
  });

  testWidgets('a tap on the manual itself takes it', (tester) async {
    writeManual();
    final state = await open(tester, onPlay: () {});
    await openBox(tester);
    final chip = tester.getRect(find.byKey(const ValueKey('game_box_manual_chip')));
    // The manual lies just above its label.
    await tester.tapAt(Offset(chip.center.dx, chip.top - 60));
    await _frames(tester, const Duration(milliseconds: 1200));
    expect(readerPaths, [manualPath]);
    expect(state.inside, GameBoxInsideState.taking);
  });

  testWidgets('without a manual: no booklet, a plain message, an optional download that shows it at once', (tester) async {
    var plays = 0;
    final state = await open(tester, onPlay: () => plays++);
    await openBox(tester);
    expect(state.manualPath, isNull);
    expect(find.byKey(const ValueKey('game_box_manual_chip')), findsNothing, reason: 'no invented booklet');
    expect(find.text('No manual on this device for this game.'), findsOneWidget);
    expect(downloads, 0, reason: 'opening the box downloads nothing');
    await tester.tap(find.byKey(const ValueKey('game_box_download_manual')));
    await _frames(tester, const Duration(milliseconds: 200));
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
    await _frames(tester, const Duration(milliseconds: 600));
    expect(downloads, 1);
    expect(state.manualPath, manualPath);
    expect(find.byKey(const ValueKey('game_box_manual_chip')), findsOneWidget, reason: 'it appears without a restart');
    expect(find.text('Manual downloaded'), findsOneWidget, reason: 'the message of Game Settings › Manual');
    expect(plays, 0);
  });

  testWidgets('without the library system there is no download offered', (tester) async {
    final state = await open(tester, onPlay: () {}, withSystem: false);
    await openBox(tester);
    expect(state.inside, GameBoxInsideState.open);
    expect(find.byKey(const ValueKey('game_box_download_manual')), findsNothing);
  });

  testWidgets('the system back gesture closes the open box first', (tester) async {
    final state = await open(tester, onPlay: () {});
    await openBox(tester);
    await tester.binding.handlePopRoute();
    await _frames(tester, const Duration(milliseconds: 900));
    expect(state.inside, GameBoxInsideState.closed);
    expect(find.byType(GameBoxInspector), findsOneWidget);
    await tester.binding.handlePopRoute();
    await _frames(tester, const Duration(milliseconds: 400));
    expect(find.byType(GameBoxInspector), findsNothing);
  });

  testWidgets('Play from the open box launches once', (tester) async {
    writeManual();
    var plays = 0;
    final state = await open(tester, onPlay: () {
      plays++;
      GameLaunchManager().beginSession();
    });
    await openBox(tester);
    await tester.tap(find.text('Play'));
    await tester.pump();
    await tester.tap(find.text('Play'), warnIfMissed: false);
    expect(state.phase, GameBoxInspectorPhase.opening);
    await _frames(tester, const Duration(milliseconds: 2200));
    expect(plays, 1);
    expect(find.byType(GameBoxInspector), findsNothing);
    GameLaunchManager().onDialogDisposed();
    await tester.pump(const Duration(seconds: 1));
  });

  testWidgets('Reduce Motion: the box opens and the manual is taken without movement', (tester) async {
    writeManual();
    final state = await open(tester, onPlay: () {}, reduceMotion: true);
    await tester.tap(find.byKey(const ValueKey('game_box_open')));
    await tester.pump();
    await tester.pump();
    expect(state.inside, GameBoxInsideState.open);
    await tester.tap(find.byKey(const ValueKey('game_box_read_manual')));
    await tester.pump();
    await tester.pump();
    await tester.pump();
    expect(readerPaths, [manualPath]);
  });

  testWidgets('the back can be seen flat, full size, with its real resolution', (tester) async {
    await open(tester, onPlay: () {});
    await tester.tap(find.text('Back cover'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Flat view'));
    await tester.pumpAndSettle();
    expect(find.byType(GameBoxScanViewer), findsOneWidget);
    expect(find.textContaining('Low-resolution scan (1 × 1 px)'), findsOneWidget,
        reason: 'a small scan is never presented as a sharp one');
    expect(find.text('Recenter'), findsOneWidget);
  });

  test('the box reads the manual with NeoStation\'s own reader', () {
    final reader = defaultReader('/media/ps2/manuals/x.pdf', 'X');
    expect(reader, isA<GameManualReaderScreen>());
    expect((reader as GameManualReaderScreen).manualPath, '/media/ps2/manuals/x.pdf');
  });

  test('the manual service uses the path of Game Settings › Manual', () async {
    final game = _game();
    expect(GameManualService.pathFor(game, 'ps2', fp), game.getManualPath('ps2', fp));
    expect(await GameManualService.existing(game, 'ps2', fp), isNull);
    writeManual();
    expect(await GameManualService.existing(game, 'ps2', fp), manualPath);
    final all = SystemModel(id: 'all', folderName: 'all', realName: 'All', iconImage: '', color: '#000000');
    expect(GameManualService.folderFor(game, all, isAllMode: true), 'ps2');
    expect(GameManualService.folderFor(game, _system, isAllMode: false), 'ps2');
  });
}
