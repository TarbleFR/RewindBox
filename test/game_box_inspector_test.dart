import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_launch_manager.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

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
    );

/// Advances time frame by frame, as the device would.
Future<void> _frames(WidgetTester tester, Duration total) async {
  const step = Duration(milliseconds: 32);
  var elapsed = Duration.zero;
  while (elapsed < total) {
    await tester.pump(step);
    elapsed += step;
  }
}

double _wrap(double a) {
  final t = a % (2 * math.pi);
  return t < 0 ? t + 2 * math.pi : t;
}

void main() {
  late Directory dir;
  late _TestFileProvider fp;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('game_box_inspector');
    fp = _TestFileProvider(dir.path);
    final store = GameBoxMediaStore(fp);
    for (final folder in ['box2d', GameBoxMediaFolders.back]) {
      File(store.canonicalPath(_game(), 'ps2', folder, 'png'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(_png);
    }
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
  });

  tearDown(() {
    GameBoxLaunchGate.leave();
    dir.deleteSync(recursive: true);
  });

  Future<GameBoxInspectorState> open(
    WidgetTester tester, {
    required VoidCallback onPlay,
    bool reduceMotion = false,
  }) async {
    await tester.pumpWidget(MaterialApp(
      // Applies to every route, the viewer's included.
      builder: (context, child) => MediaQuery(
        data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
        child: child!,
      ),
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: ElevatedButton(
              onPressed: () => GameBoxInspector.open(
                context,
                onPlay: onPlay,
                subject: GameBoxSubject(game: _game(), systemFolder: 'ps2', fileProvider: fp, systemId: 'ps2'),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pump(const Duration(milliseconds: 50));
    return tester.state<GameBoxInspectorState>(find.byType(GameBoxInspector));
  }

  testWidgets('Front, Back and Reset turn the box to a stable pose', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final state = await open(tester, onPlay: () {});
    expect(state.pose.yaw, closeTo(BoxPose.rest.yaw, 1e-9));
    await tester.tap(find.text('Back'));
    await tester.pumpAndSettle();
    expect(_wrap(state.pose.yaw), closeTo(math.pi, 1e-6));
    expect(state.pose.perspective, lessThan(0.5), reason: 'the reading pose reduces the perspective');
    expect(find.bySemanticsLabel(RegExp('showing the back')), findsOneWidget);
    await tester.tap(find.text('Front'));
    await tester.pumpAndSettle();
    expect(_wrap(state.pose.yaw), anyOf(closeTo(0, 1e-6), closeTo(2 * math.pi, 1e-6)));
    await tester.tap(find.text('Reset view'));
    await tester.pumpAndSettle();
    expect(state.pose.yaw, closeTo(BoxPose.rest.yaw, 1e-6));
    expect(state.pose.pitch, closeTo(BoxPose.rest.pitch, 1e-6));
  });

  testWidgets('dragging turns the box freely; it comes to rest by itself', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final state = await open(tester, onPlay: () {});
    final start = state.pose.yaw;
    final box = find.bySemanticsLabel(RegExp('Box of Box Test'));
    await tester.fling(box, const Offset(-500, 0), 2000);
    await tester.pumpAndSettle();
    expect(state.pose.yaw - start, greaterThan(math.pi / 2), reason: 'a drag to the left turns past a quarter');
    final settled = state.pose.yaw;
    await tester.pump(const Duration(seconds: 2));
    expect(state.pose.yaw, settled, reason: 'no idle spin');
    await tester.drag(box, const Offset(0, 200));
    await tester.pumpAndSettle();
    expect(state.pose.pitch, lessThanOrEqualTo(BoxPose.maxPitch));
    expect(state.pose.pitch, greaterThan(BoxPose.rest.pitch));
  });

  testWidgets('Play opens the box and launches once, then leaves for the launch', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    var plays = 0;
    final state = await open(tester, onPlay: () {
      plays++;
      GameLaunchManager().beginSession();
    });
    await tester.tap(find.text('Play'));
    await tester.pump();
    await tester.tap(find.text('Play'), warnIfMissed: false);
    await tester.pump(const Duration(milliseconds: 900));
    expect(state.phase, GameBoxInspectorPhase.opening);
    expect(GameBoxLaunchGate.busy, isTrue);
    await tester.pump(const Duration(milliseconds: 1000));
    await tester.pump(const Duration(milliseconds: 50));
    expect(plays, 1);
    for (var i = 0; i < 6; i++) {
      await tester.pump(const Duration(milliseconds: 20));
    }
    expect(find.byType(GameBoxInspector), findsNothing, reason: 'the viewer leaves once the session began');
    expect(GameBoxLaunchGate.busy, isFalse);
    GameLaunchManager().onDialogDisposed();
    await tester.pump(const Duration(seconds: 1));
  });

  testWidgets('a launch that does not start brings the closed box back', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    var plays = 0;
    final state = await open(tester, onPlay: () => plays++);
    await tester.tap(find.text('Play'));
    await _frames(tester, const Duration(milliseconds: 2100));
    expect(plays, 1);
    expect(state.phase, GameBoxInspectorPhase.launching);
    await _frames(tester, const Duration(seconds: 7));
    expect(state.phase, GameBoxInspectorPhase.inspecting);
    expect(GameBoxLaunchGate.busy, isFalse);
    expect(find.text('Play'), findsOneWidget);
  });

  testWidgets('Reduce Motion: no turning, a single launch', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    var plays = 0;
    final state = await open(tester, onPlay: () => plays++, reduceMotion: true);
    await tester.tap(find.text('Back'));
    await tester.pump();
    expect(_wrap(state.pose.yaw), closeTo(math.pi, 1e-6), reason: 'poses change without animation');
    await tester.tap(find.text('Play'));
    await tester.pump();
    await tester.pump();
    expect(state.pose.yaw, closeTo(-0.22, 1e-9), reason: 'the opened box appears without movement');
    await _frames(tester, const Duration(milliseconds: 700));
    expect(plays, 1);
    await _frames(tester, const Duration(seconds: 7));
  });

  testWidgets('with the opening turned off, the game starts right away', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await GameBoxPreferences.setOpeningAnimation(false);
    var plays = 0;
    final state = await open(tester, onPlay: () => plays++);
    await tester.tap(find.text('Play'));
    await _frames(tester, const Duration(milliseconds: 300));
    expect(plays, 1);
    expect(state.pose.yaw, closeTo(BoxPose.rest.yaw, 1e-9), reason: 'the box did not move');
    await _frames(tester, const Duration(seconds: 7));
  });

  testWidgets('a damaged scan never prevents the launch', (tester) async {
    tester.view.physicalSize = const Size(800, 1200);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    final store = GameBoxMediaStore(fp);
    File(store.canonicalPath(_game(), 'ps2', 'box2d', 'png')).writeAsBytesSync([1, 2, 3, 4, 5]);
    var plays = 0;
    await open(tester, onPlay: () => plays++);
    await tester.tap(find.text('Play'));
    await _frames(tester, const Duration(milliseconds: 2100));
    expect(plays, 1);
    await _frames(tester, const Duration(seconds: 7));
  });
}
