// Sides of a box like those of the original covers (docs/game-box-3d.md
// § 27): the spine scan wherever a real box prints its spine, else the
// spine template of the platform (Wii white with its grey mark, GameCube
// black, Wii U blue with a white head…), never the title alone on a plain
// panel; the plastic of a game case keeps its own colour on its edges.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
import 'package:neostation/widgets/game_box/game_box_spine_design.dart';
import 'package:neostation/widgets/game_box/game_box_surfaces.dart';

const _viewport = Size(400, 600);
final _scan = MemoryImage(base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='));
// A front scan, so that the front is a print, not the neutral face with
// the title.
final _front = MemoryImage(base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII='));
final _wheel = MemoryImage(base64Decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='));

Future<void> _pump(WidgetTester tester, String system, GameBoxArt art, BoxPose pose) => tester.pumpWidget(MaterialApp(
      home: SizedBox.fromSize(
        size: _viewport,
        child: GameBoxScene(model: GameBoxModel(GameBoxProfile.forSystem(system)), art: art, pose: pose),
      ),
    ));

/// Shows the spine (left side) and the top.
const _spineSide = BoxPose(yaw: -0.7, pitch: 0.5);

/// Shows the opening side (right) and the top.
const _openingSide = BoxPose(yaw: 0.7, pitch: 0.5);

int _images(WidgetTester tester, ImageProvider provider) =>
    tester.widgetList<Image>(find.byType(Image)).where((i) => i.image == provider).length;

void main() {
  test('every platform mark is a logo the app ships', () {
    for (final id in GameBoxSpineDesign.logos) {
      expect(File('assets/images/logos/$id.webp').existsSync(), isTrue, reason: id);
    }
    for (final id in ['wii', 'gc', 'wiiu', 'ps2', 'ps3', 'psp', 'vita', 'xbox', 'xbox360', 'ds', '3ds', 'switch',
      'ps1', 'nes', 'snes', 'n64', 'md', 'gba']) {
      final logo = GameBoxSpineDesign.of(GameBoxProfile.forSystem(id)).logo;
      expect(logo, isNotNull, reason: id);
      expect(GameBoxSpineDesign.logos, contains(logo), reason: id);
    }
  });

  test('templates follow the original spines', () {
    final wii = GameBoxSpineDesign.of(GameBoxProfile.forSystem('wii'));
    expect(wii.background, const Color(0xFFFFFFFF));
    expect(wii.logo, 'wii');
    expect(wii.logoInk!.computeLuminance(), inInclusiveRange(0.2, 0.5), reason: 'the grey Wii mark');
    expect(wii.ink.computeLuminance(), lessThan(0.1), reason: 'dark title');
    expect(wii.gameLogo, isFalse, reason: 'Nintendo case spines print the title as type');

    final gc = GameBoxSpineDesign.of(GameBoxProfile.forSystem('gc'));
    expect(gc.background.computeLuminance(), lessThan(0.02));
    expect(gc.ink, const Color(0xFFFFFFFF));
    expect(gc.uppercase, isTrue);

    final wiiu = GameBoxSpineDesign.of(GameBoxProfile.forSystem('wiiu'));
    expect(wiiu.background.b, greaterThan(wiiu.background.r), reason: 'blue');
    expect(wiiu.head, const Color(0xFFFFFFFF), reason: 'white head holding the Wii U mark');

    for (final id in ['3ds', 'switch']) {
      final design = GameBoxSpineDesign.of(GameBoxProfile.forSystem(id));
      expect(design.background, const Color(0xFFFFFFFF), reason: id);
      expect(design.head!.r, greaterThan(0.8), reason: '$id: red head');
    }
    // Other boxes: the colour of their own print, the game's logo.
    final nes = GameBoxSpineDesign.of(GameBoxProfile.forSystem('nes'), print: const Color(0xFF101010));
    expect(nes.background, const Color(0xFF101010));
    expect(nes.ink, const Color(0xFFFFFFFF));
    expect(nes.gameLogo, isTrue);
  });

  testWidgets('a game case without a spine scan shows its template; its edges stay plastic', (tester) async {
    await _pump(tester, 'wii', GameBoxArt(title: 'Super Smash Bros. Brawl', front: _front), _spineSide);
    final spine = tester.widget<GameBoxDesignedSpine>(find.byType(GameBoxDesignedSpine));
    expect(spine.design.logo, 'wii');
    expect(spine.title, 'Super Smash Bros. Brawl');
    expect(find.text('Super Smash Bros. Brawl'), findsOneWidget, reason: 'on the spine only, never on the top');
    expect(find.byWidgetPredicate((w) => w is CustomPaint && w.painter is GameBoxEdgePainter), findsWidgets,
        reason: 'the top is the white plastic of the case');
    expect(find.byType(GameBoxCardboardFlap), findsNothing);

    await _pump(tester, 'wii', GameBoxArt(title: 'Super Smash Bros. Brawl', front: _front, spine: _scan), _spineSide);
    expect(find.byType(GameBoxDesignedSpine), findsNothing, reason: 'the scan of the original spine');
    expect(_images(tester, _scan), 1);
  });

  testWidgets('a cardboard box prints its spine scan on both long sides and on its title flap', (tester) async {
    final art = GameBoxArt(title: '10-Yard Fight', front: _front, spine: _scan, edgeColor: const Color(0xFF111111));
    await _pump(tester, 'nes', art, _spineSide);
    expect(_images(tester, _scan), 2, reason: 'the spine and the top flap');
    await _pump(tester, 'nes', art, _openingSide);
    expect(_images(tester, _scan), 2, reason: 'the opening side and the top flap');
    expect(find.byType(GameBoxDesignedSpine), findsNothing);
    expect(find.text('10-Yard Fight'), findsNothing, reason: 'never the title alone in plain type');
    final flap = tester.widget<GameBoxCardboardFlap>(find.byType(GameBoxCardboardFlap));
    expect(flap.top, isTrue);
    expect(flap.spineAspect, closeTo(30 / 178, 0.01), reason: 'the NES box: 30 mm deep, 178 mm tall');
  });

  testWidgets('without a spine scan a cartridge box shows the game logo in the colour of its print', (tester) async {
    await _pump(tester, 'nes',
        GameBoxArt(title: '10-Yard Fight', front: _front, gameLogo: _wheel, edgeColor: const Color(0xFF111111)),
        _openingSide);
    final spines = tester.widgetList<GameBoxDesignedSpine>(find.byType(GameBoxDesignedSpine)).toList();
    expect(spines.length, 2, reason: 'the opening side, and the spine lying on the top flap');
    expect(spines.every((s) => s.design.background == const Color(0xFF111111) && s.design.logo == 'nes'), isTrue);
    expect(_images(tester, _wheel), 2);

    // A game case keeps its type: the logo is not used on a Wii spine.
    await _pump(tester, 'wii', GameBoxArt(title: 'Brawl', front: _front, gameLogo: _wheel), _spineSide);
    expect(_images(tester, _wheel), 0);
    expect(find.text('Brawl'), findsOneWidget);
  });

  testWidgets('a long title is set smaller, never cut', (tester) async {
    await _pump(tester, 'gc', GameBoxArt(title: 'Tom Clancy’s Splinter Cell: Chaos Theory Collector', front: _front), _spineSide);
    final text = tester.widget<Text>(find.textContaining('SPLINTER CELL'));
    expect(text.overflow, isNull);
    expect(find.ancestor(of: find.byWidget(text), matching: find.byType(FittedBox)), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
