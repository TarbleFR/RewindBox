// Physical cases, undistorted prints, media recognition and picture checks
// of the 3D box (docs/game-box-3d.md § 13, § 15, § 16).
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_card.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
import 'package:neostation/widgets/game_box/game_box_surfaces.dart';

Uint8List _le32(int v) => Uint8List(4)..buffer.asByteData().setUint32(0, v, Endian.little);

Future<Uint8List> _encode(int w, int h, void Function(Canvas c, Size s) draw) async {
  final recorder = ui.PictureRecorder();
  draw(Canvas(recorder), Size(w.toDouble(), h.toDouble()));
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

void main() {
  group('physical cases (PS3, Switch): the image never reshapes a rigid case', () {
    test('PS3 is a clear 135 × 171.5 × 14 mm case; Switch a clear 105 × 170 × 11 mm case', () {
      final ps3 = GameBoxProfile.forSystem('ps3');
      expect((ps3.width, ps3.height, ps3.depth), (135.0, 171.5, 14.0));
      expect(ps3.material, GameBoxCaseMaterial.clear);
      expect(ps3.caseColor.b, lessThan(0.95), reason: 'a faint tint, not the old opaque blue');
      expect(ps3.caseColor.r, greaterThan(0.85));
      final sw = GameBoxProfile.forSystem('switch');
      expect((sw.width, sw.height, sw.depth), (105.0, 170.0, 11.0));
      expect(sw.material, GameBoxCaseMaterial.clear);
      expect(sw.caseColor.r - sw.caseColor.g, lessThan(0.1), reason: 'the red is printed, not the plastic');
      expect(sw.resolvedInsertColor, const Color(0xFFE60012), reason: 'Switch spine print tone');
    });

    for (final id in ['ps3', 'switch', 'ps2', '3ds', 'ds', 'vita', 'gc', 'md']) {
      test('$id keeps its size whatever the front image (logo 320×176, icon 1:1, tall, corrupt)', () {
        final base = GameBoxProfile.forSystem(id);
        for (final aspect in [320 / 176, 1.0, 0.45, 0.62, 1.9, double.nan, null]) {
          final p = base.withFrontAspect(aspect);
          expect((p.width, p.height, p.depth), (base.width, base.height, base.depth), reason: '$id at $aspect');
        }
      });
    }

    test('cardboard boxes still follow their art (SNES landscape, GBC square), jewel tall inserts too', () {
      final snes = GameBoxProfile.forSystem('snes').withFrontAspect(1.4);
      expect(snes.width / snes.height, closeTo(1.4, 1e-9));
      final gbc = GameBoxProfile.forSystem('gbc').withFrontAspect(1.0);
      expect(gbc.width / gbc.height, closeTo(1.0, 1e-9));
      final ps1 = GameBoxProfile.forSystem('ps1');
      expect(ps1.withFrontAspect(1.0).height, ps1.height, reason: 'square booklet: the jewel case stays');
      expect(ps1.withFrontAspect(0.6).height, greaterThan(ps1.height), reason: 'long Saturn/PAL box');
    });

    test('a case colour applies only to an identified edition', () {
      final ps3 = GameBoxProfile.forSystem('ps3');
      final red = ps3.withIdentifiedCase(const Color(0xFFFF0000), source: 'gametdb:BLUS30902');
      expect(red.material, GameBoxCaseMaterial.opaque);
      expect(red.caseColor, const Color(0xFFFF0000));
      expect(red.identifiedCase, 'gametdb:BLUS30902');
      expect((red.width, red.height, red.depth), (ps3.width, ps3.height, ps3.depth));
      expect(ps3.identifiedCase, isNull);
    });
  });

  group('prints keep their proportions', () {
    test('close proportions fill the printed area within 3 %', () {
      final sw = GameBoxProfile.forSystem('switch');
      final l = GameBoxArtFit.fit(1166 / 1888, sw.printedAspect);
      expect(l.target, GameBoxArtLayout.full);
      expect(l.source, GameBoxArtLayout.full);
      expect((l.stretch - 1).abs(), lessThan(0.03));
    });

    test('a GameTDB PS3 cover (928 × 1080) on the PS3 print: margins trimmed, thin bands, no distortion', () {
      final ps3 = GameBoxProfile.forSystem('ps3');
      final l = GameBoxArtFit.fit(928 / 1080, ps3.printedAspect);
      expect(l.source.width, closeTo(0.97, 1e-9), reason: '3 % of the width trimmed');
      expect(l.source.height, 1.0);
      expect(l.target.width, 1.0);
      expect(l.target.height, inInclusiveRange(0.95, 1.0));
      expect((l.stretch - 1).abs(), lessThanOrEqualTo(0.0301));
    });

    test('for any proportions: at most 3 % anisotropy, 3 % trimmed, inside the area', () {
      final rnd = math.Random(7);
      for (var i = 0; i < 2000; i++) {
        final image = math.exp(rnd.nextDouble() * 3 - 1.5);
        final area = math.exp(rnd.nextDouble() * 2 - 1);
        final l = GameBoxArtFit.fit(image, area);
        expect((l.stretch - 1).abs(), lessThanOrEqualTo(0.0301), reason: '$image on $area: $l');
        expect(l.source.width, greaterThanOrEqualTo(0.97 - 1e-9));
        expect(l.source.height, greaterThanOrEqualTo(0.97 - 1e-9));
        expect(l.target.left, greaterThanOrEqualTo(-1e-9));
        expect(l.target.right, lessThanOrEqualTo(1 + 1e-9));
        expect(l.target.top, greaterThanOrEqualTo(-1e-9));
        expect(l.target.bottom, lessThanOrEqualTo(1 + 1e-9));
        // What is drawn really has the stated anisotropy.
        final drawn = (image * l.source.width / l.source.height) / (area * l.target.width / l.target.height);
        expect(drawn, closeTo(1 / l.stretch, 1e-9));
      }
    });
  });

  group('what an image is', () {
    final ps3 = GameBoxProfile.forSystem('ps3');
    final sw = GameBoxProfile.forSystem('switch');
    GameBoxArtNature c(GameBoxProfile p, double w, double h, {String? provenance, double? opaque}) =>
        GameBoxArtClassifier.classify(profile: p, size: Size(w, h), provenance: provenance, opaqueShare: opaque);

    test('the filmed cases: PS3 XMB icon and Switch title icon are catalogue art', () {
      expect(c(ps3, 320, 176), GameBoxArtNature.promo, reason: 'Bladestorm: ICON0.PNG');
      expect(c(sw, 256, 256), GameBoxArtNature.promo, reason: 'Hogwarts Legacy: square title icon');
      expect(c(ps3, 1920, 1080), GameBoxArtNature.promo, reason: 'PIC1 background, landscape');
    });

    test('real covers and sheets', () {
      expect(c(sw, 1166, 1888), GameBoxArtNature.scan);
      expect(c(ps3, 928, 1080), GameBoxArtNature.scan);
      expect(c(ps3, 700, 972), GameBoxArtNature.scan, reason: 'a ScreenScraper scan with more height');
      expect(c(sw, 2454, 1888), GameBoxArtNature.wrap);
      expect(c(ps3, 2000, 1080), GameBoxArtNature.wrap);
      expect(c(sw, 300, 486, opaque: 0.62), GameBoxArtNature.render3d, reason: 'GameTDB box render');
    });

    test('provenance is trusted before proportions', () {
      expect(c(sw, 1166, 1888, provenance: 'gametdb:box'), GameBoxArtNature.render3d);
      expect(c(ps3, 928, 1080, provenance: 'rpcs3:icon0'), GameBoxArtNature.promo);
      expect(c(sw, 256, 256, provenance: 'manual:import'), GameBoxArtNature.scan);
      expect(c(ps3, 2000, 1080, provenance: 'gametdb:coverfullHQ'), GameBoxArtNature.wrap);
    });

    test('other families keep their scans (3DS control, cardboard, jewel)', () {
      final ds3 = GameBoxProfile.forSystem('3ds');
      // The control is the real scan of the edition: GameTDB AMKP coverHQ,
      // 768 × 680 (a 3DS cover is wider than tall, docs/game-box-3d.md § 23;
      // the 900 × 1000 picture used before assumed a portrait case).
      expect(c(ds3, 768, 680), GameBoxArtNature.scan, reason: 'Mario Kart 7 control');
      expect(c(ds3, 1616, 680), GameBoxArtNature.wrap, reason: "a 3DS full sheet (Majora's Mask 3D AJRP)");
      expect(c(GameBoxProfile.forSystem('ds'), 768, 680), GameBoxArtNature.scan, reason: 'Mario Kart DS AMCP');
      expect(c(ds3, 1000, 1000), GameBoxArtNature.scan, reason: 'a large square 3DS scan is not an icon');
      expect(c(ds3, 48, 48), GameBoxArtNature.promo, reason: 'a 3DS HOME menu icon');
      expect(c(GameBoxProfile.forSystem('gbc'), 600, 600), GameBoxArtNature.scan);
      expect(c(GameBoxProfile.forSystem('snes'), 1600, 1100), GameBoxArtNature.scan);
      expect(c(GameBoxProfile.forSystem('ps1'), 600, 594), GameBoxArtNature.scan);
    });

    test('a full sheet is cut along its verified layout only', () {
      final layout = GameBoxWrapLayout.forProfile(sw)!;
      final parts = layout.split(const Size(2454, 1888))!;
      expect(parts.back.left, 0);
      expect(parts.back.width, closeTo(1166 / 2454, 1e-9));
      expect(parts.spine.left, closeTo(1166 / 2454, 1e-9));
      expect(parts.spine.width, closeTo(122 / 2454, 1e-9));
      expect(parts.front.right, closeTo(1, 1e-9));
      expect(layout.split(const Size(340, 262)), isNotNull, reason: 'the small sheet has the same layout');
      expect(layout.split(const Size(2000, 1888)), isNull, reason: 'unverified proportions');
      expect(GameBoxWrapLayout.forProfile(GameBoxProfile.forSystem('ps2')), isNull);
    });
  });

  group('image sizes of every accepted format', () {
    test('PNG, JPEG (fill bytes, EXIF before the frame), WebP VP8/VP8L/VP8X, GIF, BMP', () {
      final png = Uint8List(24)
        ..setAll(0, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        ..buffer.asByteData().setUint32(16, 1166)
        ..buffer.asByteData().setUint32(20, 1888);
      expect(GameBoxImageSize.fromBytes(png), const Size(1166, 1888));

      final exif = List<int>.filled(70000, 0x20);
      final jpeg = Uint8List.fromList([
        0xFF, 0xD8, // SOI
        0xFF, 0xE1, (exif.length + 2) >> 8, (exif.length + 2) & 0xFF, ...exif, // APP1 (large EXIF)
        0xFF, 0xFF, 0xFF, // fill bytes
        0xFF, 0xC2, 0x00, 0x11, 0x08, 0x04, 0x38, 0x03, 0xA0, 0x03, // progressive SOF: 1080 x 928
        ...List<int>.filled(12, 0),
      ]);
      expect(GameBoxImageSize.fromBytes(jpeg), const Size(928, 1080));

      Uint8List riff(String chunk, List<int> payload) => Uint8List.fromList([
            ...'RIFF'.codeUnits, ..._le32(payload.length + 12), ...'WEBP'.codeUnits,
            ...chunk.codeUnits, ..._le32(payload.length), ...payload,
            ...List<int>.filled(16, 0),
          ]);
      // Lossy: frame tag, start code 9D 01 2A, 14-bit width and height.
      final vp8 = riff('VP8 ', [0, 0, 0, 0x9D, 0x01, 0x2A, 1166 & 0xFF, 1166 >> 8, 1888 & 0xFF, 1888 >> 8]);
      expect(GameBoxImageSize.fromBytes(vp8), const Size(1166, 1888));
      // Lossless: signature 0x2F, (width-1) and (height-1) on 14 bits each.
      final bits = (1166 - 1) | ((1888 - 1) << 14);
      final vp8l = riff('VP8L', [0x2F, bits & 0xFF, (bits >> 8) & 0xFF, (bits >> 16) & 0xFF, (bits >> 24) & 0xFF]);
      expect(GameBoxImageSize.fromBytes(vp8l), const Size(1166, 1888));
      // Extended: canvas (width-1) and (height-1) on 24 bits.
      final vp8x = riff('VP8X', [0x10, 0, 0, 0, (2454 - 1) & 0xFF, (2454 - 1) >> 8, 0, (1888 - 1) & 0xFF, (1888 - 1) >> 8, 0]);
      expect(GameBoxImageSize.fromBytes(vp8x), const Size(2454, 1888));

      final gif = Uint8List.fromList([...'GIF89a'.codeUnits, 64, 1, 176, 0, 0, 0, 0]);
      expect(GameBoxImageSize.fromBytes(gif), const Size(320, 176));

      final bmp = Uint8List(54)
        ..setAll(0, 'BM'.codeUnits)
        ..buffer.asByteData().setUint32(14, 40, Endian.little)
        ..buffer.asByteData().setInt32(18, 600, Endian.little)
        ..buffer.asByteData().setInt32(22, -600, Endian.little); // top-down
      expect(GameBoxImageSize.fromBytes(bmp), const Size(600, 600));

      expect(GameBoxImageSize.fromBytes(Uint8List.fromList('NOMEDIA'.codeUnits)), isNull);
    });

    test('a file replaced at the same path is read again', () async {
      final dir = Directory.systemTemp.createTempSync('gbsize');
      addTearDown(() => dir.deleteSync(recursive: true));
      final f = File('${dir.path}/front.png');
      Uint8List header(int w, int h) => Uint8List(24)
        ..setAll(0, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
        ..buffer.asByteData().setUint32(16, w)
        ..buffer.asByteData().setUint32(20, h);
      f.writeAsBytesSync(header(320, 176));
      expect(GameBoxImageSize.of(f.path), const Size(320, 176));
      f.writeAsBytesSync([...header(1166, 1888), 0, 0, 0]);
      f.setLastModifiedSync(DateTime.now().add(const Duration(seconds: 5)));
      expect(GameBoxImageSize.of(f.path), const Size(1166, 1888));
    });
  });

  group('picture checks (the green Switch back)', () {
    Uint8List flat(int w, int h, List<int> rgba, {int noise = 0}) {
      final out = Uint8List(w * h * 4);
      final rnd = math.Random(3);
      for (var i = 0; i < w * h; i++) {
        for (var c = 0; c < 3; c++) {
          out[i * 4 + c] = (rgba[c] + (noise == 0 ? 0 : rnd.nextInt(noise * 2 + 1) - noise)).clamp(0, 255);
        }
        out[i * 4 + 3] = rgba[3];
      }
      return out;
    }

    test('a uniform #00FF00 picture, even with JPEG noise, is refused', () {
      expect(GameBoxMediaChecker.analyzeRgba(flat(64, 104, [0, 255, 0, 255]), 64, 104).verdict,
          GameBoxImageVerdict.uniform);
      expect(GameBoxMediaChecker.analyzeRgba(flat(64, 104, [0, 251, 0, 255], noise: 2), 64, 104).verdict,
          GameBoxImageVerdict.uniform);
    });

    test('an empty transparent picture is refused; a scan with a plain margin is kept', () {
      expect(GameBoxMediaChecker.analyzeRgba(flat(64, 64, [0, 0, 0, 0]), 64, 64).verdict,
          GameBoxImageVerdict.transparent);
      // 90 % white margin, 10 % print: a real back with lots of white.
      final rgba = flat(64, 100, [255, 255, 255, 255]);
      for (var y = 40; y < 50; y++) {
        for (var x = 0; x < 64; x++) {
          final i = (y * 64 + x) * 4;
          rgba[i] = (x * 4) & 255;
          rgba[i + 1] = 30;
          rgba[i + 2] = 90;
        }
      }
      expect(GameBoxMediaChecker.analyzeRgba(rgba, 64, 100).verdict, GameBoxImageVerdict.ok);
    });

    testWidgets('encoded pictures: green placeholder refused, a cover kept, a 1 px image too small', (tester) async {
      await tester.runAsync(() async {
        final green = await _encode(240, 388, (c, s) => c.drawRect(Offset.zero & s, Paint()..color = const Color(0xFF00FF00)));
        expect((await GameBoxMediaChecker.checkBytes(green)).verdict, GameBoxImageVerdict.uniform);
        final cover = await _encode(240, 388, (c, s) {
          c.drawRect(Offset.zero & s, Paint()..color = const Color(0xFFE60012));
          c.drawCircle(const Offset(120, 200), 80, Paint()..color = const Color(0xFF2050C0));
          c.drawRect(const Rect.fromLTWH(10, 330, 50, 50), Paint()..color = Colors.white);
        });
        final ok = await GameBoxMediaChecker.checkBytes(cover);
        expect(ok.verdict, GameBoxImageVerdict.ok);
        expect(ok.opaqueShare, 1.0);
        final dot = await _encode(1, 1, (c, s) => c.drawRect(Offset.zero & s, Paint()..color = Colors.red));
        expect((await GameBoxMediaChecker.checkBytes(dot)).verdict, GameBoxImageVerdict.tiny);
        expect((await GameBoxMediaChecker.checkBytes(Uint8List.fromList([1, 2, 3, 4]))).verdict,
            GameBoxImageVerdict.unreadable);
      });
    });
  });

  group('the box draws what an image is', () {
    Future<void> pumpScene(WidgetTester tester, GameBoxProfile profile, GameBoxArt art) async {
      await tester.pumpWidget(MaterialApp(
        home: Center(
          child: SizedBox(width: 400, height: 500, child: GameBoxScene(model: GameBoxModel(profile), art: art, pose: BoxPose.front)),
        ),
      ));
    }

    testWidgets('catalogue art on a PS3 case: a neutral cover, never the print', (tester) async {
      final profile = GameBoxProfile.forSystem('ps3').withFrontAspect(320 / 176);
      final icon = MemoryImage(Uint8List.fromList(const [0]));
      await pumpScene(
        tester,
        profile,
        GameBoxArt(title: 'Bladestorm', front: icon, frontAspect: 320 / 176, frontNature: GameBoxArtNature.promo),
      );
      expect(find.byType(GameBoxNeutralCover), findsOneWidget);
      expect(find.text('Bladestorm'), findsOneWidget);
      expect(profile.width, 135, reason: 'the case stays a PS3 case');
      tester.takeException();
    });

    testWidgets('the library card recognises an XMB icon and keeps the PS3 case', (tester) async {
      final dir = Directory.systemTemp.createTempSync('gbcard');
      addTearDown(() => dir.deleteSync(recursive: true));
      final f = File('${dir.path}/icon0.png')
        ..writeAsBytesSync(Uint8List(24)
          ..setAll(0, [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A])
          ..buffer.asByteData().setUint32(16, 320)
          ..buffer.asByteData().setUint32(20, 176));
      await tester.pumpWidget(MaterialApp(
        home: Center(
          child: SizedBox(
            width: 300,
            height: 400,
            child: GameBoxCard(frontPath: f.path, title: 'Bladestorm', systemId: 'ps3'),
          ),
        ),
      ));
      expect(find.byType(GameBoxNeutralCover), findsOneWidget);
      final scene = tester.widget<GameBoxScene>(find.byType(GameBoxScene));
      expect((scene.model.width, scene.model.height), (135.0, 171.5));
      tester.takeException();
    });
  });
}
