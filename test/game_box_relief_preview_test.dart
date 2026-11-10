// Relief of every box format, for manual inspection (not part of CI): front,
// three-quarter, both profiles, top, bottom and back views of each format,
// with a back and with a front only. Writes PNGs to $GAME_BOX_RELIEF_OUT;
// real scans come from $GAME_BOX_COMPARE_ART (local files, never committed),
// other covers are drawn here. docs/game-box-3d.md § 20.
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/widgets/game_box/game_box_art_loader.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
import 'package:neostation/widgets/game_box/game_box_surfaces.dart';
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

/// A cover drawn for formats without a scan here: artwork, title block and
/// the platform band where the format prints it.
Future<Uint8List> _drawn(String title, int w, int h, Color a, Color b, {String band = '', bool bandRight = false}) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  final r = Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble());
  c.drawRect(r, Paint()..shader = ui.Gradient.linear(r.topLeft, r.bottomRight, [a, b]));
  for (var i = 0; i < 9; i++) {
    c.drawCircle(Offset(w * (0.15 + 0.09 * i), h * (0.55 + 0.25 * math.sin(i))), w * 0.08,
        Paint()..color = Colors.white.withValues(alpha: 0.18));
  }
  if (band.isNotEmpty) {
    final bandRect = bandRight ? Rect.fromLTWH(w * 0.9, 0, w * 0.1, h.toDouble()) : Rect.fromLTWH(0, 0, w.toDouble(), h * 0.09);
    c.drawRect(bandRect, Paint()..color = Colors.white);
    final tp = TextPainter(
      text: TextSpan(text: band, style: TextStyle(fontSize: h * 0.045, color: Colors.black, fontWeight: FontWeight.bold, fontFamily: 'Roboto')),
      textDirection: TextDirection.ltr,
    )..layout();
    if (bandRight) {
      c.save();
      c.translate(bandRect.center.dx + tp.height / 2, bandRect.center.dy - tp.width / 2);
      c.rotate(math.pi / 2);
      tp.paint(c, Offset.zero);
      c.restore();
    } else {
      tp.paint(c, Offset(bandRect.center.dx - tp.width / 2, bandRect.center.dy - tp.height / 2));
    }
  }
  final tp = TextPainter(
    text: TextSpan(text: title, style: TextStyle(fontSize: h * 0.08, color: Colors.white, fontWeight: FontWeight.w900, fontFamily: 'Roboto')),
    textDirection: TextDirection.ltr,
    textAlign: TextAlign.center,
  )..layout(maxWidth: w * 0.8);
  tp.paint(c, Offset((w - tp.width) / 2, h * 0.14));
  final img = await recorder.endRecording().toImage(w, h);
  final data = await img.toByteData(format: ui.ImageByteFormat.png);
  img.dispose();
  return data!.buffer.asUint8List();
}

/// A spine scan drawn like a cartridge box's (§ 27): the print's black,
/// a coloured band and the title running from top to bottom.
Future<Uint8List> _drawnSpine(String title, int w, int h) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  c.drawRect(Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()), Paint()..color = const Color(0xFF111111));
  c.drawRect(Rect.fromLTWH(0, h * 0.04, w.toDouble(), h * 0.16), Paint()..color = const Color(0xFFD32F2F));
  final tp = TextPainter(
    text: TextSpan(text: title.toUpperCase(), style: TextStyle(fontSize: w * 0.5, color: const Color(0xFFFFEB3B), fontWeight: FontWeight.w900, fontFamily: 'Roboto')),
    textDirection: TextDirection.ltr,
  )..layout();
  c.save();
  c.translate(w / 2 + tp.height / 2, h * 0.26);
  c.rotate(math.pi / 2);
  tp.paint(c, Offset.zero);
  c.restore();
  final img = await recorder.endRecording().toImage(w, h);
  final data = await img.toByteData(format: ui.ImageByteFormat.png);
  img.dispose();
  return data!.buffer.asUint8List();
}

/// A game logo drawn like a scraped "wheel": coloured type on transparency.
Future<Uint8List> _drawnWheel(String title) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  final tp = TextPainter(
    text: TextSpan(text: title, style: const TextStyle(fontSize: 120, color: Color(0xFFFFC107), fontWeight: FontWeight.w900, fontStyle: FontStyle.italic, fontFamily: 'Roboto')),
    textDirection: TextDirection.ltr,
  )..layout();
  tp.paint(c, const Offset(20, 10));
  final img = await recorder.endRecording().toImage(tp.width.ceil() + 40, tp.height.ceil() + 20);
  final data = await img.toByteData(format: ui.ImageByteFormat.png);
  img.dispose();
  return data!.buffer.asUint8List();
}

class _Case {
  const _Case(this.id, this.system, this.title,
      {this.front, this.back, this.full, this.drawn, this.drawnSpine = false, this.wheel = false});
  final String id, system, title;
  final String? front, back, full;

  /// A drawn spine scan, a drawn game logo.
  final bool drawnSpine, wheel;

  /// (width, height, colour a, colour b, band, band on the right).
  final (int, int, Color, Color, String, bool)? drawn;
}

const _cases = [
  _Case('n64_bugs', 'n64', "A Bug's Life", drawn: (900, 640, Color(0xFF2E7D32), Color(0xFF81D4FA), 'NINTENDO 64', true)),
  _Case('snes', 'snes', 'Super Quest', drawn: (900, 640, Color(0xFF4527A0), Color(0xFFFF7043), '', false)),
  _Case('nes', 'nes', 'Castle Run', drawn: (640, 900, Color(0xFF212121), Color(0xFFD32F2F), '', false)),
  // Sides of a cartridge box (§ 27): with the spine scan, without it but
  // with the game's logo, with neither.
  _Case('nes_spine', 'nes', '10-Yard Fight', drawn: (640, 900, Color(0xFF212121), Color(0xFF2E7D32), '', false),
      drawnSpine: true),
  _Case('nes_wheel', 'nes', '10-Yard Fight', drawn: (640, 900, Color(0xFF212121), Color(0xFF2E7D32), '', false),
      wheel: true),
  _Case('wiiu', 'wiiu', 'Kart Party', drawn: (700, 960, Color(0xFF0277BD), Color(0xFFFFCA28), 'Wii U', false)),
  _Case('gbc', 'gbc', 'Pocket Quest', front: 'gbc_front.png', back: 'gbc_back.png'),
  _Case('gba', 'gba', 'Tiny Knights', drawn: (700, 700, Color(0xFF1565C0), Color(0xFFFFCA28), 'GAME BOY ADVANCE', false)),
  _Case('neogeo', 'neogeo', 'Metal Fighters', drawn: (700, 920, Color(0xFF263238), Color(0xFFFF5252), '', false)),
  _Case('ps1', 'ps1', 'Disc Quest', drawn: (800, 790, Color(0xFF37474F), Color(0xFF26A69A), '', false)),
  _Case('md', 'md', 'Sonic Rush', drawn: (640, 900, Color(0xFF0D47A1), Color(0xFF00BCD4), 'MEGA DRIVE', false)),
  _Case('ps2', 'ps2', 'Shadow Run', drawn: (700, 1000, Color(0xFF1A237E), Color(0xFF7E57C2), 'PlayStation 2', false)),
  _Case('ps3_gow3', 'ps3', 'God of War III', front: 'ps3_gow3_front.jpg', back: 'ps3_gow3_back.jpg'),
  _Case('ps3_front_only', 'ps3', 'God of War III', front: 'ps3_gow3_front.jpg'),
  _Case('gc', 'gc', 'Cube Star', drawn: (700, 1000, Color(0xFF4A148C), Color(0xFFFFB300), '', false)),
  _Case('wii', 'wii', 'Smash Party', drawn: (700, 1000, Color(0xFFECEFF1), Color(0xFF90A4AE), 'Wii', false)),
  _Case('psp', 'psp', 'Portable Ops', drawn: (600, 1040, Color(0xFF263238), Color(0xFF5C6BC0), 'PSP', false)),
  _Case('switch_mario', 'switch', 'Super Mario 3D World', front: 'switch_mario_front.jpg', back: 'switch_mario_back.jpg'),
  _Case('switch_front_only', 'switch', 'Hogwarts Legacy', front: 'switch_hogwarts_front.jpg'),
  // DS and 3DS: the real scans of one edition each (GameTDB), § 23.
  _Case('3ds_mk7', '3ds', 'Mario Kart 7', front: '3ds_mk7_real_front.jpg', back: '3ds_mk7_real_back.jpg'),
  _Case('3ds_sheet_only', '3ds', "The Legend of Zelda: Majora's Mask 3D", full: '3ds_mm3d_full.jpg'),
  _Case('ds_mkds', 'ds', 'Mario Kart DS', front: 'ds_mkds_front.jpg', back: 'ds_mkds_back.jpg'),
  _Case('ds_sheet_only', 'ds', 'Mario Kart DS', full: 'ds_mkds_full.jpg'),
  // Other formats from real scans (§ 24): full sheets alone, fronts alone.
  _Case('wii_brawl_sheet', 'wii', 'Super Smash Bros. Brawl', full: 'wii_brawl_full.png'),
  _Case('gc_melee_sheet', 'gc', 'Super Smash Bros. Melee', full: 'gc_melee_full.png'),
  _Case('wiiu_mk8', 'wiiu', 'Mario Kart 8', front: 'wiiu_mk8_front.jpg', full: 'wiiu_mk8_full.jpg'),
  _Case('ps3_gow3_sheet', 'ps3', 'God of War III', full: 'ps3_gow3_full.jpg'),
  _Case('psp_gow', 'psp', 'God of War: Chains of Olympus', front: 'psp_gow_front.png'),
  _Case('vita_gravity', 'vita', 'Gravity Rush', front: 'vita_gravity_front.png'),
  _Case('tg16_front', 'tg16', 'TurboGrafx game', front: 'tg16_front.png'),
  _Case('ds', 'ds', 'Pocket Racers', drawn: (768, 680, Color(0xFF00897B), Color(0xFFFFEB3B), 'NINTENDO DS', false)),
  _Case('vita', 'vita', 'Gravity Run', drawn: (600, 720, Color(0xFF283593), Color(0xFF29B6F6), 'PS VITA', false)),
  _Case('fds', 'fds', 'Disk Hero', drawn: (700, 800, Color(0xFFF9A825), Color(0xFFE53935), '', false)),
];

/// (name, yaw, pitch).
const _poses = <(String, double, double)>[
  ('1_front', 0, 0),
  ('2_three_quarter', -0.62, 0.14),
  ('3_profile_spine', -math.pi / 2, 0.0),
  ('4_profile_opening', math.pi / 2, 0.0),
  ('5_from_above', -0.45, 0.75),
  ('6_from_below', -0.45, -0.75),
  ('7_back_three_quarter', math.pi - 0.5, 0.1),
  ('8_back', math.pi, 0),
];

void main() {
  final out = Platform.environment['GAME_BOX_RELIEF_OUT'];
  final art = Platform.environment['GAME_BOX_COMPARE_ART'];
  final only = Platform.environment['GAME_BOX_RELIEF_ONLY'];
  // A full turn (every 30°) besides the fixed views.
  final turn = Platform.environment['GAME_BOX_RELIEF_TURN'] == '1';
  for (final c in _cases) {
    if (only != null && only.isNotEmpty && !only.split(',').contains(c.id)) continue;
    testWidgets('relief ${c.id}', (tester) async {
      if (out == null || art == null) return;
      SharedPreferences.setMockInitialValues({});
      final dir = Directory.systemTemp.createTempSync('gbrelief');
      final fp = _FP(dir.path);
      final game = GameModel(
        romname: '${c.title}.rom', realname: c.title, name: c.title,
        year: '', developer: '', publisher: '', genre: '', players: '', rating: 0,
        systemId: c.system, systemFolderName: c.system,
      );
      final store = GameBoxMediaStore(fp);
      await tester.runAsync(() async {
        final font = FontLoader('Roboto')
          ..addFont(File('${Platform.environment['ROBOTO']}').readAsBytes().then((b) => ByteData.view(b.buffer)));
        await font.load();
        Future<void> put(List<int> bytes, String ext, String folder) async {
          File(store.canonicalPath(game, c.system, folder, ext))
            ..createSync(recursive: true)
            ..writeAsBytesSync(bytes);
        }
        if (c.front != null) {
          await put(File(p.join(art, c.front!)).readAsBytesSync(), p.extension(c.front!).substring(1), 'box2d');
        }
        if (c.full != null) {
          await put(File(p.join(art, c.full!)).readAsBytesSync(), p.extension(c.full!).substring(1), GameBoxMediaFolders.full);
        }
        if (c.back != null) {
          await put(File(p.join(art, c.back!)).readAsBytesSync(), p.extension(c.back!).substring(1), GameBoxMediaFolders.back);
        }
        final d = c.drawn;
        if (d != null) await put(await _drawn(c.title, d.$1, d.$2, d.$3, d.$4, band: d.$5, bandRight: d.$6), 'png', 'box2d');
        if (c.drawnSpine) await put(await _drawnSpine(c.title, 140, 840), 'png', GameBoxMediaFolders.spine);
        if (c.wheel) await put(await _drawnWheel(c.title), 'png', 'wheels');
      });
      final profile = await tester.runAsync(() => GameBoxProfiles.load(c.system));

      final media = store.read(game, c.system);
      final edge = await tester.runAsync(() => GameBoxArtSet.edgeColor(media.front));
      final set = GameBoxArtSet(media: media, title: c.title);
      final boxArt = set.art(
        detailed: true,
        profile: profile,
        backPath: media.back,
        edgeColor: edge,
        backUnavailable: 'Back not available',
        composedBack: GameBoxBackDetails(
          title: c.title,
          platform: c.system.toUpperCase(),
          year: '2001',
          developer: 'Studio',
          publisher: 'Publisher',
          genre: 'Action',
          players: '1-2',
          summary: 'A summary as the scraper stores it: two or three sentences that tell what the game is '
              'about, kept whole on the box and faded where the space ends.',
        ),
        composedBackLabel: 'Reconstructed back',
        gameLogoPath: c.wheel ? store.canonicalPath(game, c.system, 'wheels', 'png') : null,
      );
      final model = GameBoxModel(profile!);

      final dirOut = Directory(p.join(out, c.id))..createSync(recursive: true);
      tester.view.physicalSize = const Size(520, 520);
      tester.view.devicePixelRatio = 1;
      final key = GlobalKey();
      Future<void> frame(BoxPose pose) async {
        await tester.pumpWidget(MaterialApp(
          debugShowCheckedModeBanner: false,
          theme: ThemeData(fontFamily: 'Roboto'),
          home: Material(
            type: MaterialType.transparency,
            child: RepaintBoundary(
              key: key,
              child: ColoredBox(
                // The inspector's background in the dark theme.
                color: const Color(0xFF0B0D12),
                child: GameBoxScene(model: model, art: boxArt, pose: pose, groundShadow: true),
              ),
            ),
          ),
        ));
      }

      // Decoded before the box is shown: a scene waiting for its pictures in
      // the test clock never settles.
      await tester.pumpWidget(MaterialApp(home: RepaintBoundary(key: key, child: const SizedBox.expand())));
      await tester.runAsync(() async {
        final ctx = key.currentContext!;
        for (final provider in [boxArt.front, boxArt.back, boxArt.spine, boxArt.gameLogo]) {
          if (provider != null) await precacheImage(provider, ctx);
        }
      });
      final poses = [
        ..._poses,
        if (turn)
          for (var k = 0; k < 12; k++) ('turn_${(k * 30).toString().padLeft(3, '0')}', k * math.pi / 6, 0.12),
      ];
      for (final (name, yaw, pitch) in poses) {
        await frame(BoxPose(yaw: yaw, pitch: pitch));
        for (var i = 0; i < 3; i++) {
          await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 60)));
          await tester.pump(const Duration(milliseconds: 30));
        }
        await tester.runAsync(() async {
          final b = key.currentContext!.findRenderObject()! as RenderRepaintBoundary;
          final im = await b.toImage();
          File(p.join(dirOut.path, '$name.png'))
              .writeAsBytesSync((await im.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List());
          im.dispose();
        });
      }
      tester.view.reset();
      dir.deleteSync(recursive: true);
    });
  }
}
