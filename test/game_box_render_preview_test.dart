// Render previews for manual inspection (not part of CI). Writes PNGs to
// $GAME_BOX_RENDER_DIR when set.
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';

Future<Uint8List> _png(String label, Color color, int w, int h, {bool circle = false}) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  final rect = Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble());
  if (circle) {
    canvas.drawCircle(rect.center, w / 2, Paint()..color = color);
  } else {
    canvas.drawRect(rect, Paint()..color = color);
    canvas.drawRect(rect.deflate(6), Paint()..style = PaintingStyle.stroke..strokeWidth = 6..color = Colors.white);
    canvas.drawLine(rect.topLeft, rect.center, Paint()..strokeWidth = 8..color = Colors.yellow);
  }
  final tp = TextPainter(
    text: TextSpan(text: label, style: const TextStyle(fontSize: 48, color: Colors.white, fontFamily: 'Roboto')),
    textDirection: TextDirection.ltr,
  )..layout(maxWidth: w.toDouble());
  tp.paint(canvas, Offset((w - tp.width) / 2, (h - tp.height) / 2));
  final img = await recorder.endRecording().toImage(w, h);
  final bytes = await img.toByteData(format: ui.ImageByteFormat.png);
  return bytes!.buffer.asUint8List();
}

void main() {
  final out = Platform.environment['GAME_BOX_RENDER_DIR'];
  testWidgets('render previews', (tester) async {
    if (out == null) return;
    await tester.runAsync(() async {
      final font = FontLoader('Roboto')
        ..addFont(File('${Platform.environment['ROBOTO']}').readAsBytes().then((b) => ByteData.view(b.buffer)));
      await font.load();
    });
    late Uint8List front, back, spine, disc, psFront, psBack;
    await tester.runAsync(() async {
      front = await _png('FRONT', Colors.indigo, 540, 760);
      back = await _png('BACK', Colors.teal, 540, 760);
      spine = await _png('SPINE', Colors.deepOrange, 56, 760);
      disc = await _png('DISC', Colors.purple, 400, 400, circle: true);
      psFront = await _png('PS1 FRONT', Colors.blueGrey, 600, 594);
      // Back inlay with its two spines (151 x 118 mm).
      final recorder = ui.PictureRecorder();
      final c = Canvas(recorder);
      c.drawRect(const Rect.fromLTWH(0, 0, 768, 600), Paint()..color = Colors.brown);
      c.drawRect(const Rect.fromLTWH(0, 0, 33, 600), Paint()..color = Colors.red);
      c.drawRect(const Rect.fromLTWH(735, 0, 33, 600), Paint()..color = Colors.green);
      final img = await recorder.endRecording().toImage(768, 600);
      psBack = (await img.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
    });
    final art = GameBoxArt(
      title: 'Test Game',
      front: MemoryImage(front),
      back: MemoryImage(back),
      spine: MemoryImage(spine),
      support: MemoryImage(disc),
      backUnavailable: 'Back not available',
    );
    final key = GlobalKey();
    Future<void> shot(String name, GameBoxProfile profile, BoxPose pose, BoxOpening opening, {GameBoxArt? a, double blend = 0}) async {
      await tester.pumpWidget(MaterialApp(
        debugShowCheckedModeBanner: false,
        home: Scaffold(
          backgroundColor: const Color(0xFF202024),
          body: Center(
            child: RepaintBoundary(
              key: key,
              child: SizedBox(
                width: 400, height: 500,
                child: ColoredBox(
                  color: const Color(0xFF202024),
                  child: GameBoxScene(model: GameBoxModel(profile), art: a ?? art, pose: pose, opening: opening, outlineBlend: blend, groundShadow: true),
                ),
              ),
            ),
          ),
        ),
      ));
      await tester.runAsync(() async {
        for (final p in [front, back, spine, disc, psFront, psBack]) {
          await precacheImage(MemoryImage(p), tester.element(find.byKey(key)));
        }
      });
      await tester.pump();
      await tester.runAsync(() async {
        final boundary = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
        final image = await boundary.toImage(pixelRatio: 1);
        final data = await image.toByteData(format: ui.ImageByteFormat.png);
        File('$out/$name.png').writeAsBytesSync(data!.buffer.asUint8List());
      });
    }

    final ps2 = GameBoxProfile.forSystem('ps2').withFrontAspect(540 / 760);
    await shot('ps2_rest', ps2, BoxPose.rest, BoxOpening.closed);
    await shot('ps2_back', ps2, BoxPose.back, BoxOpening.closed);
    await shot('ps2_spine', ps2, const BoxPose(yaw: -1.2, pitch: 0.2), BoxOpening.closed);
    await shot('ps2_top', ps2, const BoxPose(yaw: 0.6, pitch: 0.7), BoxOpening.closed);
    await shot('ps2_open_half', ps2, const BoxPose(yaw: -0.22, pitch: 0.1, zoom: 0.7), const BoxOpening(lid: 0.5));
    await shot('ps2_open', ps2, const BoxPose(yaw: -0.22, pitch: 0.1), const BoxOpening(lid: 1, support: 1), blend: 1);
    final ps1 = GameBoxProfile.forSystem('ps1').withFrontAspect(600 / 594);
    final psArt = GameBoxArt(title: 'Test Game', front: MemoryImage(psFront), back: MemoryImage(psBack),
        support: MemoryImage(disc), backAspect: 768 / 600, backUnavailable: 'Back not available');
    await shot('ps1_rest', ps1, BoxPose.rest, BoxOpening.closed, a: psArt);
    await shot('ps1_back', ps1, BoxPose.back, BoxOpening.closed, a: psArt);
    await shot('ps1_left', ps1, const BoxPose(yaw: -1.2, pitch: 0.15), BoxOpening.closed, a: psArt);
    await shot('ps1_right', ps1, const BoxPose(yaw: 1.2, pitch: 0.15), BoxOpening.closed, a: psArt);
    await shot('ps1_open', ps1, const BoxPose(yaw: -0.22, pitch: 0.1), const BoxOpening(lid: 1, support: 1), a: psArt, blend: 1);
    final nes = GameBoxProfile.forSystem('nes').withFrontAspect(540 / 760);
    await shot('nes_rest', nes, BoxPose.rest, BoxOpening.closed);
    await shot('nes_flap', nes, const BoxPose(yaw: -0.2, pitch: 0.35, zoom: 0.8), const BoxOpening(lid: 0.5));
    await shot('nes_open', nes, const BoxPose(yaw: -0.2, pitch: 0.35), const BoxOpening(lid: 1, support: 1), blend: 1);
    final ds = GameBoxProfile.forSystem('ds');
    await shot('ds_open', ds, const BoxPose(yaw: -0.22, pitch: 0.1), const BoxOpening(lid: 1, support: 1), blend: 1,
        a: GameBoxArt(title: 'Test Game', front: MemoryImage(front), backUnavailable: 'Back not available'));
    await shot('ds_back_missing', ds, BoxPose.back, BoxOpening.closed,
        a: GameBoxArt(title: 'Test Game', front: MemoryImage(front), backUnavailable: 'Back not available'));
  });
}
