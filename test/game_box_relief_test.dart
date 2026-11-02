// Relief of the box while it turns (docs/game-box-3d.md § 20 and § 21): the
// sides of every format read as solid panels, dark cases stay visible on a
// dark background, cardboard sides are printed without stretched pixels, and
// a box without an authentic back shows a labelled reconstruction.
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
import 'package:neostation/widgets/game_box/game_box_surfaces.dart';

const _viewport = Size(400, 600);

GameBoxScene _scene(String system, {GameBoxArt? art, BoxPose pose = BoxPose.rest}) => GameBoxScene(
      model: GameBoxModel(GameBoxProfile.forSystem(system)),
      art: art ?? const GameBoxArt(title: 'Castle Run'),
      pose: pose,
    );

List<ProjectedFace> _faces(String system, BoxPose pose) =>
    BoxProjector(model: GameBoxModel(GameBoxProfile.forSystem(system)), viewport: _viewport, pose: pose).project();

ProjectedFace _face(String system, BoxPose pose, String id) => _faces(system, pose).firstWhere((f) => f.face.id == id);

const _threeQuarter = BoxPose(yaw: -0.62, pitch: 0.5);
const _families = ['ps2', 'ps3', 'switch', 'ds', '3ds', 'psp', 'vita', 'ps1', 'md', 'gc', 'wii', 'n64', 'snes', 'nes', 'gba'];

void main() {
  group('light on the faces', () {
    test('a face seen straight on keeps its print untouched', () {
      for (final id in ['n64', 'snes', 'switch', 'ps3', 'ds', 'wii']) {
        final scene = _scene(id, pose: BoxPose.front);
        final front = _face(id, BoxPose.front, 'body.front');
        final light = scene.lightOf(front);
        expect(light.darken, lessThan(0.004), reason: id);
        expect(light.sheen, 0, reason: id);
        expect(light.rim, lessThan(0.01), reason: '$id: no outline on a light case seen straight on');
      }
    });

    test('every side seen at three quarters catches light on its folds', () {
      for (final id in _families) {
        final scene = _scene(id, pose: _threeQuarter);
        final sides = _faces(id, _threeQuarter).where((f) =>
            f.face.surface != BoxSurface.front && f.face.surface != BoxSurface.back && !f.face.id.contains('corner'));
        expect(sides, isNotEmpty, reason: id);
        for (final f in sides) {
          expect(scene.lightOf(f).rim, greaterThan(0.1), reason: '$id ${f.face.id}');
        }
      }
    });

    test('a dark plastic side is lifted, not darkened into the background', () {
      final dark = _scene('ps2', pose: _threeQuarter); // black keep case
      final light = _scene('wii', pose: _threeQuarter); // white keep case
      final darkSide = dark.lightOf(_face('ps2', _threeQuarter, 'body.top'));
      final lightSide = light.lightOf(_face('wii', _threeQuarter, 'body.top'));
      expect(darkSide.sheen, greaterThan(lightSide.sheen + 0.05));
      expect(darkSide.darken, lessThan(lightSide.darken * 0.6));
      expect(darkSide.rim, greaterThan(lightSide.rim));
    });

    test('gloss grows as a side turns away from the viewer', () {
      final scene = _scene('ps3');
      double sheenAt(double yaw) => scene.lightOf(_face('ps3', BoxPose(yaw: yaw), 'body.left')).sheen;
      expect(sheenAt(-0.4), greaterThan(sheenAt(-math.pi / 2 + 0.05)));
    });

    test('rounded corners carry their own light: sides light only their folds with the front and back', () {
      final scene = _scene('ps3', pose: _threeQuarter);
      final top = scene.lightOf(_face('ps3', _threeQuarter, 'body.top'));
      expect(top.rimHorizontal, isTrue, reason: 'folds with the front and back');
      expect(top.rimVertical, isFalse, reason: 'the rounded corners continue the top');
      final cardboard = _scene('n64', pose: _threeQuarter).lightOf(_face('n64', _threeQuarter, 'body.top'));
      expect(cardboard.rimHorizontal && cardboard.rimVertical, isTrue, reason: 'a cardboard box is folded on every edge');
    });
  });

  group('sides of a cardboard box', () {
    testWidgets('top, bottom and opening side are printed with the title, never with the cover stretched',
        (tester) async {
      for (final pose in const [BoxPose(yaw: -0.45, pitch: 0.75), BoxPose(yaw: 0.6, pitch: -0.75)]) {
        await tester.pumpWidget(MaterialApp(
          home: SizedBox.fromSize(
            size: _viewport,
            child: _scene('n64', pose: pose, art: const GameBoxArt(title: "A Bug's Life", edgeColor: Color(0xFF2E7D32))),
          ),
        ));
        final panels = tester.widgetList<GameBoxCardboardPanel>(find.byType(GameBoxCardboardPanel)).toList();
        expect(panels, isNotEmpty);
        for (final p in panels) {
          expect(p.title, "A Bug's Life");
          expect(p.color, const Color(0xFF2E7D32), reason: 'the colour of the cover border');
        }
        expect(panels.any((p) => p.standing), pose.yaw > 0, reason: 'the opening side shows when turned that way');
        expect(find.byType(GameBoxEdgePainter), findsNothing);
      }
    });
  });

  group('reconstructed back', () {
    const details = GameBoxBackDetails(
      title: 'Bladestorm',
      platform: 'PlayStation 3',
      year: '2007',
      developer: 'Koei',
      publisher: 'Koei',
      genre: 'Action',
      summary: 'A summary.',
    );

    testWidgets('without an authentic back, every format shows the verified details and the label', (tester) async {
      for (final id in _families) {
        await tester.pumpWidget(MaterialApp(
          home: SizedBox.fromSize(
            size: _viewport,
            child: _scene(
              id,
              pose: BoxPose.back,
              art: const GameBoxArt(
                title: 'Bladestorm',
                composedBack: details,
                composedBackLabel: 'Verso reconstitué',
              ),
            ),
          ),
        ));
        expect(find.byType(GameBoxComposedBack), findsOneWidget, reason: id);
        expect(find.text('Verso reconstitué'), findsOneWidget, reason: id);
        expect(find.text('2007 · Koei · Action'), findsOneWidget, reason: '$id: the facts, once each');
        expect(find.byType(GameBoxNeutralFace), findsNothing, reason: id);
      }
    });

    testWidgets('without details the back stays neutral, with its notice', (tester) async {
      await tester.pumpWidget(MaterialApp(
        home: SizedBox.fromSize(
          size: _viewport,
          child: _scene('ps3', pose: BoxPose.back, art: const GameBoxArt(title: 'X', backUnavailable: 'Back not available')),
        ),
      ));
      expect(find.byType(GameBoxComposedBack), findsNothing);
      expect(find.text('Back not available'), findsOneWidget);
    });

    test('the facts leave out empty and repeated values', () {
      expect(details.facts, '2007 · Koei · Action');
      expect(const GameBoxBackDetails(title: 'X', year: '0', genre: ' ').facts, '');
    });
  });
}
