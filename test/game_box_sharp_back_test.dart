import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/screens/game_box/game_box_scan_viewer.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_box/game_box_sharp_scan.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

/// The back shown at the size it covers on the screen (docs/game-box-3d.md
/// § 12): asked once the box is still and read straight on, used in place of
/// the larger decode, sharpened unless "Sharp text" is off, wider for a closer
/// look but never wider than the scan, and released when the viewer closes.
/// The resampling itself is tested by game_box_sharp_scan_test.dart; here a
/// plain image stands for it.

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

/// A PNG header saying [w] × [h] (only the size is read here).
Uint8List _pngOfSize(int w, int h) {
  final b = Uint8List.fromList(_png);
  final d = ByteData.view(b.buffer);
  d.setUint32(16, w);
  d.setUint32(20, h);
  return b;
}

GameModel _game() => const GameModel(
      romname: 'Sharp Test (USA).iso',
      realname: 'Sharp Test',
      name: 'Sharp Test',
      year: '',
      developer: '',
      publisher: '',
      genre: '',
      players: '',
      rating: 0,
      systemId: 'ps2',
      systemFolderName: 'ps2',
      romPath: '/roms/ps2/Sharp Test (USA).iso',
    );

const _scanWidth = 2000, _scanHeight = 2800;

Future<void> _frames(WidgetTester tester, Duration total) async {
  const step = Duration(milliseconds: 32);
  var elapsed = Duration.zero;
  while (elapsed < total) {
    await tester.pump(step);
    elapsed += step;
  }
}

/// Lets the renders asked during the last frames finish.
Future<void> _settle(WidgetTester tester) async {
  for (var i = 0; i < 4; i++) {
    await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 20)));
    await tester.pump();
  }
}

Finder _renderedBack() => find.byWidgetPredicate((w) => w is Image && w.image is GameBoxRenderedScan);

void main() {
  late Directory dir;
  late _TestFileProvider fp;
  late String backPath;
  final calls = <(String, int, bool)>[];

  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
  });

  setUp(() {
    dir = Directory.systemTemp.createTempSync('game_box_sharp');
    fp = _TestFileProvider(dir.path);
    final store = GameBoxMediaStore(fp);
    File(store.canonicalPath(_game(), 'ps2', 'box2d', 'png'))
      ..createSync(recursive: true)
      ..writeAsBytesSync(_png);
    backPath = store.canonicalPath(_game(), 'ps2', GameBoxMediaFolders.back, 'png');
    File(backPath)
      ..createSync(recursive: true)
      ..writeAsBytesSync(_pngOfSize(_scanWidth, _scanHeight));
    calls.clear();
    GameBoxSharpScan.debugProcessor = (path, width, sharpen) async {
      calls.add((path, width, sharpen));
      final h = (_scanHeight * width / _scanWidth).round();
      final rgba = Uint8List(width * h * 4)..fillRange(0, width * h * 4, 200);
      return GameBoxPixels(width, h, rgba);
    };
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
  });

  tearDown(() {
    GameBoxLaunchGate.leave();
    GameBoxSharpScan.debugProcessor = null;
    GameBoxImageSize.evict(backPath);
    dir.deleteSync(recursive: true);
  });

  Future<GameBoxInspectorState> open(WidgetTester tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 2;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
      supportedLocales: FlutterLocalization.instance.supportedLocales,
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: ElevatedButton(
              onPressed: () => GameBoxInspector.open(
                context,
                onPlay: () {},
                subject: GameBoxSubject(game: _game(), systemFolder: 'ps2', fileProvider: fp, systemId: 'ps2'),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tap(find.text('open'));
    await tester.pump();
    await _frames(tester, const Duration(milliseconds: 500));
    await _settle(tester);
    return tester.state<GameBoxInspectorState>(find.byType(GameBoxInspector));
  }

  Future<void> turnToBack(WidgetTester tester) async {
    await tester.tap(find.text('Back cover'));
    await _frames(tester, const Duration(milliseconds: 700));
    await _settle(tester);
  }

  testWidgets('read straight on, the back is the render made for its size, sharpened by default', (tester) async {
    final state = await open(tester);
    expect(calls, isEmpty, reason: 'nothing is made while the front is shown');
    expect(_renderedBack(), findsNothing);
    await turnToBack(tester);
    expect(calls, hasLength(1));
    final (path, width, sharpen) = calls.single;
    expect(path, backPath);
    expect(sharpen, isTrue, reason: 'on by default');
    // Measured on the screen: the widest image drawing the back.
    var drawn = 0.0;
    for (final e in _renderedBack().evaluate()) {
      final box = e.renderObject! as RenderBox;
      final a = box.localToGlobal(Offset.zero), b = box.localToGlobal(Offset(box.size.width, 0));
      drawn = drawn > (b - a).distance ? drawn : (b - a).distance;
    }
    final shownPx = drawn * 2;
    expect(shownPx, greaterThan(400), reason: 'the back panel, not a corner facet ($shownPx)');
    expect(state.backScreenWidth(state.viewport)! * 2, closeTo(shownPx, shownPx * 0.05));
    expect(width, greaterThanOrEqualTo(shownPx.floor()), reason: 'never smaller than shown ($shownPx)');
    expect(width, lessThan(shownPx * 1.05 + GameBoxSharpScan.widthStep), reason: 'not larger than needed');
    expect(width, lessThan(_scanWidth));
    expect(state.sharpBack?.width, width);
    expect(_renderedBack(), findsWidgets, reason: 'the face shows it');

    // Still: no new render for the same size.
    await _frames(tester, const Duration(milliseconds: 300));
    await _settle(tester);
    expect(calls, hasLength(1));
  });

  testWidgets('a closer look asks for a wider render, never wider than the scan', (tester) async {
    final state = await open(tester);
    await turnToBack(tester);
    final first = calls.single.$2;
    // Double tap on the box zooms in.
    final area = tester.getCenter(find.bySemanticsLabel(RegExp('showing the back')));
    await tester.tapAt(area);
    await tester.pump(const Duration(milliseconds: 50));
    await tester.tapAt(area);
    await _frames(tester, const Duration(milliseconds: 700));
    await _settle(tester);
    expect(state.pose.zoom, greaterThan(1.5));
    expect(calls.length, greaterThanOrEqualTo(2));
    final closer = calls.last.$2;
    expect(closer, greaterThan(first));
    expect(closer, lessThanOrEqualTo(_scanWidth), reason: 'the scan is never enlarged');
    expect(state.sharpBack?.width, closer);
  });

  testWidgets('Sharp text off: the back is only resized, and the choice is kept', (tester) async {
    final state = await open(tester);
    await turnToBack(tester);
    expect(calls.single.$3, isTrue);
    await tester.tap(find.byIcon(Icons.tune));
    await _frames(tester, const Duration(milliseconds: 400));
    await tester.tap(find.byKey(const ValueKey('game_box_sharp_text')));
    await tester.pump();
    expect(await GameBoxPreferences.sharpText(), isFalse);
    await tester.tapAt(const Offset(10, 10)); // closes the sheet
    await _frames(tester, const Duration(milliseconds: 500));
    await _settle(tester);
    expect(calls.last.$3, isFalse);
    expect(state.sharpBack?.sharpen, isFalse);
    expect(_renderedBack(), findsWidgets);
  });

  testWidgets('turning away hides it; closing the viewer releases it', (tester) async {
    final state = await open(tester);
    await turnToBack(tester);
    final render = state.sharpBack!;
    expect(render.image.debugDisposed, isFalse);
    await tester.tap(find.text('Front cover'));
    await _frames(tester, const Duration(milliseconds: 700));
    expect(_renderedBack(), findsNothing, reason: 'the front side never shows it');
    await tester.tap(find.byKey(const ValueKey('game_box_back')));
    await _frames(tester, const Duration(milliseconds: 500));
    expect(find.byType(GameBoxInspector), findsNothing);
    expect(render.image.debugDisposed, isTrue, reason: 'released with the viewer');
  });

  group('room for the back', () {
    // Build 493 left the box 39 px (iPhone SE) and 272 px (iPhone 14) of
    // height in portrait: the panel took the rest, and the back was drawn
    // at most 234 pt wide (none at all on the SE once turned).
    for (final screen in const [Size(375, 667), Size(390, 844), Size(400, 600)]) {
      testWidgets('portrait ${screen.width.round()} × ${screen.height.round()}: the back is drawn large, the buttons stay reachable',
          (tester) async {
        tester.view.physicalSize = screen * 3;
        tester.view.devicePixelRatio = 3;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(MaterialApp(
          localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
          supportedLocales: FlutterLocalization.instance.supportedLocales,
          home: Builder(
            builder: (context) => Scaffold(
              body: Center(
                child: ElevatedButton(
                  onPressed: () => GameBoxInspector.open(
                    context,
                    onPlay: () {},
                    subject: GameBoxSubject(game: _game(), systemFolder: 'ps2', fileProvider: fp, systemId: 'ps2'),
                  ),
                  child: const Text('open'),
                ),
              ),
            ),
          ),
        ));
        await tester.pump();
        await tester.pump(const Duration(milliseconds: 50));
        await tester.tap(find.text('open'));
        await tester.pump();
        await _frames(tester, const Duration(milliseconds: 600));
        final state = tester.state<GameBoxInspectorState>(find.byType(GameBoxInspector));
        expect(find.text('Back cover').hitTestable(), findsOneWidget, reason: 'Back cover is on screen');
        expect(find.text('Play').hitTestable(), findsOneWidget, reason: 'Play always shows');
        await tester.tap(find.text('Back cover'));
        await _frames(tester, const Duration(milliseconds: 700));
        expect(state.viewport.height, greaterThanOrEqualTo(screen.height * 0.54), reason: '${state.viewport}');
        final back = state.backScreenWidth(state.viewport);
        expect(back, isNotNull);
        expect(back!, greaterThanOrEqualTo(screen.width * 0.68), reason: 'back drawn $back pt wide');
        expect(find.text('Play').hitTestable(), findsOneWidget);
        expect(tester.takeException(), isNull);
        await tester.pump(const Duration(seconds: 1));
      });
    }

    testWidgets('landscape: the options fit, scrolling when needed', (tester) async {
      tester.view.physicalSize = const Size(844, 390) * 3;
      tester.view.devicePixelRatio = 3;
      addTearDown(tester.view.reset);
      await open(tester);
      tester.view.physicalSize = const Size(844, 390) * 3;
      await tester.pump();
      await tester.tap(find.byIcon(Icons.tune));
      await _frames(tester, const Duration(milliseconds: 400));
      expect(tester.takeException(), isNull, reason: 'no overflow');
      final sharp = find.byKey(const ValueKey('game_box_sharp_text'));
      await tester.ensureVisible(sharp);
      await tester.pump();
      expect(sharp.hitTestable(), findsOneWidget);
      await tester.pump(const Duration(seconds: 1));
    });
  });

  group('flat view', () {
    Future<void> openFlat(WidgetTester tester) async {
      tester.view.physicalSize = const Size(800, 1200);
      tester.view.devicePixelRatio = 2;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: FlutterLocalization.instance.localizationsDelegates,
        supportedLocales: FlutterLocalization.instance.supportedLocales,
        home: GameBoxScanViewer(path: backPath, title: 'Back'),
      ));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 50));
      await _settle(tester);
    }

    Finder sharp() => find.byKey(const ValueKey('game_box_scan_sharp'));

    testWidgets('the scan is shown as made for its fitted size, then for each zoom', (tester) async {
      await openFlat(tester);
      expect(calls, isNotEmpty);
      final fitted = calls.last.$2;
      // The fitted scan: as wide as its box on screen, in physical pixels.
      final box = tester.getSize(find.byType(InteractiveViewer));
      final fit = (box.width / _scanWidth) < (box.height / _scanHeight) ? box.width / _scanWidth : box.height / _scanHeight;
      final shownPx = _scanWidth * fit * 2;
      expect(fitted, GameBoxSharpScan.targetWidth(_scanWidth.toDouble(), shownPx));
      expect(calls.last.$3, isTrue);
      expect(sharp(), findsOneWidget);

      // Zoomed in, the render too small for it is hidden until the wider one.
      final viewer = tester.getCenter(find.byType(InteractiveViewer));
      await tester.tapAt(viewer);
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tapAt(viewer);
      await tester.pump();
      expect(calls.last.$2, greaterThan(fitted));
      await _settle(tester);
      expect(sharp(), findsOneWidget);
      expect(calls.last.$2, lessThanOrEqualTo(_scanWidth));
      await tester.pump(const Duration(seconds: 1));
    });

    testWidgets('the toggle turns the sharpening off and keeps the choice', (tester) async {
      await openFlat(tester);
      final toggle = find.byKey(const ValueKey('game_box_sharp_toggle'));
      expect(toggle, findsOneWidget);
      expect(find.byTooltip('Sharp text'), findsOneWidget, reason: 'labelled in the app language');
      await tester.tap(toggle);
      await tester.pump();
      expect(await GameBoxPreferences.sharpText(), isFalse);
      await _settle(tester);
      expect(calls.last.$3, isFalse);
      expect(sharp(), findsOneWidget);
    });
  });
}
