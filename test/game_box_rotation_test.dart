// A continuous turn of the box: no step of projection at 90°/270°, at the
// zoom threshold or when the controls change; zoom where the fingers are
// (docs/game-box-3d.md § 14).
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

class _FP extends FileProvider {
  _FP(this.root);
  final String root;
  @override
  bool get isInitialized => true;
  @override
  String getMediaPath(String s, String t, String r, String e) =>
      p.join(root, 'media', s, t, '${FileProvider.stripRomExtension(r)}.$e');
  @override
  String getMediaDirectoryPath() => p.join(root, 'media');
  @override
  List<String> getEsdeMediaCandidates(String s, String t, String r) => const [];
}

/// A PNG header saying [w] × [h] (the box only needs the size here).
Uint8List _header(int w, int h) => Uint8List(33)
  ..setAll(0, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
  ..buffer.asByteData().setUint32(16, w)
  ..buffer.asByteData().setUint32(20, h);

GameModel _game(String system) => GameModel(
      romname: 'Turn Test.iso', realname: 'Turn Test', name: 'Turn Test',
      year: '', developer: '', publisher: '', genre: '', players: '', rating: 0,
      systemId: system, systemFolderName: system,
    );

/// Screen bounds of every face the scene draws, measured on the render tree
/// (each face's own perspective transform applied).
Rect _outline(WidgetTester tester) {
  var r = Rect.zero;
  var first = true;
  final faces = find.descendant(
    of: find.byType(GameBoxScene),
    matching: find.byWidgetPredicate((w) => w is Transform && w.key is ValueKey<String>),
  );
  for (final e in faces.evaluate()) {
    final child = (e.renderObject! as RenderTransform).child;
    if (child == null || !child.hasSize) continue;
    final s = child.size;
    for (final c in [Offset.zero, Offset(s.width, 0), Offset(0, s.height), Offset(s.width, s.height)]) {
      final g = child.localToGlobal(c);
      if (first) {
        r = Rect.fromPoints(g, g);
        first = false;
      } else {
        r = r.expandToInclude(Rect.fromPoints(g, g));
      }
    }
  }
  return r;
}

/// Screen bounds of the eight corners of the case as the inspector projects
/// them now (the same projector, pose and viewport as the drawn scene).
Rect _cornerOutline(GameBoxInspectorState state, String system) {
  final profile = GameBoxProfiles.of(system);
  final projector = BoxProjector(model: GameBoxModel(profile), viewport: state.viewport, pose: state.shownPose);
  Rect? r;
  for (final sx in const [-1.0, 1.0]) {
    for (final sy in const [-1.0, 1.0]) {
      for (final sz in const [-1.0, 1.0]) {
        final q = projector.screenPoint(
          'body',
          BoxV3(sx * profile.width / 2, sy * profile.height / 2, sz * profile.depth / 2),
        )!;
        final pt = Rect.fromPoints(q, q);
        r = r == null ? pt : r.expandToInclude(pt);
      }
    }
  }
  return r!;
}

/// Largest change of the step between frames: a smooth motion changes its
/// step a little from frame to frame; a projection that jumps changes it at
/// once (the filmed 90° crossing changed the height by 23 px in one frame).
double _maxJerk(List<double> values) {
  var worst = 0.0;
  for (var i = 2; i < values.length; i++) {
    final a = values[i - 1] - values[i - 2];
    final b = values[i] - values[i - 1];
    worst = math.max(worst, (b - a).abs());
  }
  return worst;
}

void main() {
  late Directory dir;
  late _FP fp;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(mapLocales: [MapLocale('en', AppLocale.en)], initLanguageCode: 'en');
  });

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(const MethodChannel('xyz.luan/gamepads'), (call) async => <Object>[]);
    GameBoxMediaChecker.debugCheck = (_) => const GameBoxImageCheck(GameBoxImageVerdict.ok);
    dir = Directory.systemTemp.createTempSync('gbturn');
    fp = _FP(dir.path);
  });

  tearDown(() {
    GameBoxMediaChecker.debugCheck = null;
    GameBoxLaunchGate.leave();
    dir.deleteSync(recursive: true);
  });

  Future<GameBoxInspectorState> open(WidgetTester tester, String system, Size screen) async {
    final store = GameBoxMediaStore(fp);
    final game = _game(system);
    File(store.canonicalPath(game, system, 'box2d', 'png'))
      ..createSync(recursive: true)
      ..writeAsBytesSync(_header(928, 1080));
    File(store.canonicalPath(game, system, GameBoxMediaFolders.back, 'png'))
      ..createSync(recursive: true)
      ..writeAsBytesSync(_header(928, 1080));
    tester.view.physicalSize = screen;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: ElevatedButton(
              onPressed: () => GameBoxInspector.open(
                context,
                onPlay: () {},
                subject: GameBoxSubject(game: game, systemFolder: system, fileProvider: fp, systemId: system),
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('open'));
    for (var i = 0; i < 20; i++) {
      await tester.pump(const Duration(milliseconds: 32));
    }
    return tester.state<GameBoxInspectorState>(find.byType(GameBoxInspector));
  }

  test('turning by hand leaves the reading perspective without a step', () {
    for (final start in [0.15, 0.35, 1.0]) {
      expect(GameBoxInspectorState.turningPerspective(start, 0), start);
      expect(GameBoxInspectorState.turningPerspective(start, math.pi / 2), closeTo(1, 1e-12));
      var previous = start;
      for (var i = 1; i <= 200; i++) {
        final v = GameBoxInspectorState.turningPerspective(start, -i * math.pi / 400);
        expect(v, greaterThanOrEqualTo(previous - 1e-12));
        expect((v - previous).abs(), lessThan(0.012), reason: 'no step at ${i / 400 * 180}°');
        previous = v;
      }
    }
  });

  test('pinching keeps the point under the fingers', () {
    const viewport = Size(500, 360);
    const start = BoxPose(zoom: 1);
    const focal = Offset(140, 180); // on the left part of the box
    final pan = GameBoxInspectorState.focalPan(
      viewport: viewport, start: start, startFocal: focal, focal: focal, zoom: 2.5);
    // The model point under the fingers: (focal - centre) at zoom 1.
    final centre = viewport.center(Offset.zero);
    final before = focal - centre;
    final after = centre + pan + before * 2.5;
    expect((after - focal).distance, lessThan(1e-9));
  });

  for (final system in ['ps3', 'switch']) {
    testWidgets('$system: "Back cover" turns without any step at 90° (landscape 852 × 393)', (tester) async {
      await open(tester, system, const Size(852, 393));
      await tester.tap(find.text('Front cover'));
      await tester.pumpAndSettle();
      final heights = <double>[], centres = <double>[], tops = <double>[];
      await tester.tap(find.text('Back cover'));
      for (var i = 0; i < 40; i++) {
        await tester.pump(const Duration(milliseconds: 16));
        final o = _outline(tester);
        heights.add(o.height);
        centres.add(o.center.dy);
        tops.add(o.top);
      }
      expect(_maxJerk(heights), lessThan(4), reason: 'heights $heights');
      expect(_maxJerk(tops), lessThan(4), reason: 'tops $tops');
      expect(_maxJerk(centres), lessThan(3), reason: 'centres $centres');
      await tester.pumpAndSettle();
    });

    testWidgets('$system: a full turn by hand, both ways, from the front and from the back pose', (tester) async {
      final state = await open(tester, system, const Size(852, 393));
      for (final startBack in [false, true]) {
        await tester.tap(find.text(startBack ? 'Back cover' : 'Front cover'));
        await tester.pumpAndSettle();
        for (final direction in [-1.0, 1.0]) {
          final heights = <double>[], centresX = <double>[], centresY = <double>[];
          final yaws = <double>[];
          final area = tester.getRect(find.byType(ClipRect).first);
          final gesture = await tester.startGesture(area.center, kind: PointerDeviceKind.touch);
          await tester.pump(const Duration(milliseconds: 16));
          // About 1.6° per step: 260 steps make more than a full turn, the
          // touch slop included.
          for (var i = 0; i < 260; i++) {
            await gesture.moveBy(Offset(direction * 4, 0));
            await tester.pump(const Duration(milliseconds: 16));
            final o = _cornerOutline(state, system);
            heights.add(o.height);
            centresX.add(o.center.dx);
            centresY.add(o.center.dy);
            yaws.add(state.pose.yaw);
          }
          await gesture.up();
          await tester.pumpAndSettle();
          final turned = (yaws.last - yaws.first).abs();
          expect(turned, greaterThan(2 * math.pi), reason: 'a full turn');
          expect(_maxJerk(heights), lessThan(4), reason: 'from ${startBack ? 'back' : 'front'}, dir $direction');
          expect(_maxJerk(centresY), lessThan(3));
          // The centre of rotation stays put: the outline's middle never
          // leaves the middle of the box area by more than the case depth.
          final mid = area.center.dx;
          for (final x in centresX) {
            expect((x - mid).abs(), lessThan(area.width * 0.12), reason: 'centre $x vs $mid');
          }
        }
      }
    });

    testWidgets('$system: zooming the back through ×1.05 changes nothing but the zoom', (tester) async {
      final state = await open(tester, system, const Size(852, 393));
      await tester.tap(find.text('Front cover'));
      await tester.pumpAndSettle();
      // As filmed (God of War III at 24 s): the back reached by turning the
      // box by hand, then pinched.
      final area = tester.getRect(find.byType(ClipRect).first);
      final turn = await tester.startGesture(area.center, kind: PointerDeviceKind.touch);
      await tester.pump(const Duration(milliseconds: 16));
      for (var i = 0; i < 61; i++) {
        await turn.moveBy(const Offset(-8, 0));
        await tester.pump(const Duration(milliseconds: 16));
      }
      await turn.up();
      await tester.pumpAndSettle();
      expect((state.pose.yaw.abs() - math.pi).abs(), lessThan(0.35), reason: 'the back faces the viewer');
      final h0 = _outline(tester).height;
      final a = await tester.startGesture(area.center - const Offset(40, 0));
      final b = await tester.startGesture(area.center + const Offset(40, 0));
      await tester.pump(const Duration(milliseconds: 16));
      final zooms = <double>[];
      var ratio = h0;
      for (var i = 0; i < 30; i++) {
        await a.moveBy(const Offset(-2, 0));
        await b.moveBy(const Offset(2, 0));
        await tester.pump(const Duration(milliseconds: 16));
        final z = state.pose.zoom;
        zooms.add(z);
        // The drawn back grows with the zoom (perspective bends it a little,
        // continuously): no change of projection when the zoom crosses the
        // old ×1.05 threshold, which changed this ratio by about 20 %.
        final r = _outline(tester).height / z;
        expect((r - ratio).abs(), lessThan(ratio * 0.004), reason: 'zoom $z: $r after $ratio');
        ratio = r;
      }
      await a.up();
      await b.up();
      await tester.pumpAndSettle();
      expect(zooms.first, lessThan(1.05), reason: 'starts below the old threshold');
      expect(zooms.last, greaterThan(1.3), reason: 'ends well above it');
    });
  }

  testWidgets('portrait: the box area keeps its size when the buttons change', (tester) async {
    final state = await open(tester, 'ps3', const Size(390, 844));
    await tester.tap(find.text('Front cover'));
    await tester.pumpAndSettle();
    final front = state.viewport;
    expect(find.text('Flat view'), findsNothing);
    await tester.tap(find.text('Back cover'));
    await tester.pumpAndSettle();
    expect(find.text('Flat view'), findsOneWidget, reason: 'a button appeared');
    expect(state.viewport, front);
    // Zoomed: "Recenter" appears too.
    final area = tester.getRect(find.byType(ClipRect).first);
    final a = await tester.startGesture(area.center - const Offset(30, 0));
    final b = await tester.startGesture(area.center + const Offset(30, 0));
    for (var i = 0; i < 10; i++) {
      await a.moveBy(const Offset(-6, 0));
      await b.moveBy(const Offset(6, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await a.up();
    await b.up();
    await tester.pumpAndSettle();
    expect(find.text('Recenter'), findsOneWidget);
    expect(state.viewport, front);
  });

  testWidgets('pinching on the left of the back keeps the left of the back in view (GBC capture)', (tester) async {
    await open(tester, 'ps3', const Size(852, 393));
    await tester.tap(find.text('Back cover'));
    await tester.pumpAndSettle();
    final before = _outline(tester);
    final area = tester.getRect(find.byType(ClipRect).first);
    final focus = Offset(before.left + before.width * 0.15, before.center.dy);
    final a = await tester.startGesture(focus - const Offset(15, 0));
    final b = await tester.startGesture(focus + const Offset(15, 0));
    await tester.pump(const Duration(milliseconds: 16));
    for (var i = 0; i < 15; i++) {
      await a.moveBy(const Offset(-4, 0));
      await b.moveBy(const Offset(4, 0));
      await tester.pump(const Duration(milliseconds: 16));
    }
    await a.up();
    await b.up();
    await tester.pumpAndSettle();
    final after = _outline(tester);
    final k = after.width / before.width;
    expect(k, greaterThan(1.5), reason: 'zoomed in');
    // The left edge moved away from the fingers by the zoom, no more.
    final expectedLeft = focus.dx - (focus.dx - before.left) * k;
    expect(after.left, closeTo(expectedLeft, before.width * 0.04));
    expect(after.left, greaterThan(area.left - 1), reason: 'the left of the back stays in the box area');
  });
}
