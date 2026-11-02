// Correction of degraded pictures (docs/game-box-3d.md § 22): the defects
// are detected, only those are corrected, on a copy; the original file is
// never changed, and a print in the scraping language is never swapped for
// another scan.
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_enhance.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_sharp_scan.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
import 'package:path/path.dart' as p;

/// Print-like test card: dark strokes of several widths on a light panel,
/// a coloured band and a soft gradient.
GameBoxPixels _card(int w, int h) {
  final rgba = Uint8List(w * h * 4);
  for (var y = 0; y < h; y++) {
    for (var x = 0; x < w; x++) {
      final i = (y * w + x) * 4;
      var r = 225 - (x * 30 ~/ w), g = 215 - (y * 30 ~/ h), b = 190;
      if (y < h ~/ 8) {
        r = 180;
        g = 30;
        b = 40;
      } else if (y > h * 7 ~/ 8) {
        r = g = b = 18; // a dark band, as the rating and legal strip
      }
      final row = (y - h ~/ 6) % 14;
      final col = x % 9;
      if (y > h ~/ 6 && row < 3 && col < 6 && x > w ~/ 10 && x < w * 9 ~/ 10) {
        r = g = b = 25;
      }
      rgba[i] = r;
      rgba[i + 1] = g;
      rgba[i + 2] = b;
      rgba[i + 3] = 255;
    }
  }
  return GameBoxPixels(w, h, rgba);
}

GameBoxPixels _map(GameBoxPixels src, int Function(int v, int x, int y, int c) f) {
  final out = Uint8List.fromList(src.rgba);
  for (var y = 0; y < src.height; y++) {
    for (var x = 0; x < src.width; x++) {
      final i = (y * src.width + x) * 4;
      for (var c = 0; c < 3; c++) {
        out[i + c] = f(src.rgba[i + c], x, y, c).clamp(0, 255);
      }
    }
  }
  return GameBoxPixels(src.width, src.height, out);
}

/// The card under a Gaussian blur of [sigma] pixels (a blurred scan).
GameBoxPixels _blurred(GameBoxPixels src, {double sigma = 1.6}) {
  final r = (sigma * 3).ceil();
  final k = [for (var i = -r; i <= r; i++) math.exp(-(i * i) / (2 * sigma * sigma))];
  final total = k.reduce((a, b) => a + b);
  GameBoxPixels pass(GameBoxPixels px, bool horizontal) {
    final out = Uint8List.fromList(px.rgba);
    for (var y = 0; y < px.height; y++) {
      for (var x = 0; x < px.width; x++) {
        for (var c = 0; c < 3; c++) {
          var s = 0.0;
          for (var i = -r; i <= r; i++) {
            final xx = horizontal ? (x + i).clamp(0, px.width - 1) : x;
            final yy = horizontal ? y : (y + i).clamp(0, px.height - 1);
            s += px.rgba[(yy * px.width + xx) * 4 + c] * k[i + r];
          }
          out[(y * px.width + x) * 4 + c] = (s / total).round().clamp(0, 255);
        }
      }
    }
    return GameBoxPixels(px.width, px.height, out);
  }

  return pass(pass(src, true), false);
}

/// The card with the 8 × 8 blocks of a strong JPEG: each block's mean is
/// off by a few levels (quantised DC), so steps show on the block borders.
GameBoxPixels _blocky(GameBoxPixels src) {
  final random = math.Random(3);
  final bw = (src.width + 7) ~/ 8;
  final offsets = List.generate(bw * ((src.height + 7) ~/ 8), (_) => random.nextInt(17) - 8);
  return _map(src, (v, x, y, c) => v + offsets[(y ~/ 8) * bw + x ~/ 8]);
}

GameBoxPixels _noisy(GameBoxPixels src) {
  final random = math.Random(7);
  double gauss() => math.sqrt(-2 * math.log(1 - random.nextDouble())) * math.cos(2 * math.pi * random.nextDouble());
  final noise = List.generate(src.width * src.height, (_) => (gauss() * 10).round());
  return _map(src, (v, x, y, c) => v + noise[y * src.width + x]);
}

Future<Uint8List> _png(GameBoxPixels px) async {
  final completer = <ui.Image>[];
  ui.decodeImageFromPixels(px.rgba, px.width, px.height, ui.PixelFormat.rgba8888, completer.add);
  while (completer.isEmpty) {
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
  final data = await completer.single.toByteData(format: ui.ImageByteFormat.png);
  return data!.buffer.asUint8List();
}

void main() {
  final card = _card(640, 720);

  group('detection', () {
    test('a clean large print shows no defect', () {
      expect(GameBoxEnhance.diagnose(_card(1200, 1700), jpeg: true).defects, isEmpty);
    });

    test('each defect is found in its own degraded copy, and only it', () {
      final blur = GameBoxEnhance.diagnose(_blurred(card, sigma: 2.4), jpeg: false);
      final blocks = GameBoxEnhance.diagnose(_blocky(card), jpeg: true);
      final noise = GameBoxEnhance.diagnose(_noisy(card), jpeg: false);
      final faded = GameBoxEnhance.diagnose(_map(card, (v, _, _, _) => 90 + v * 90 ~/ 255), jpeg: false);
      const low = GameBoxImageDefect.lowResolution;
      expect(blur.defects, {low, GameBoxImageDefect.blur}, reason: '$blur');
      expect(blocks.defects, {low, GameBoxImageDefect.jpegBlocks}, reason: '$blocks');
      expect(noise.defects, {low, GameBoxImageDefect.noise}, reason: '$noise');
      expect(faded.defects, {low, GameBoxImageDefect.faded}, reason: '$faded');
      expect(GameBoxEnhance.diagnose(_blocky(card), jpeg: false).defects, isNot(contains(GameBoxImageDefect.jpegBlocks)),
          reason: 'block steps count only in a JPEG');
    });

    test('resolution: up to ×8, enough for a readable long side', () {
      expect(GameBoxEnhance.stepsFor(160, 184), 3, reason: 'Bladestorm EU back (GameTDB thumbnail)');
      expect(GameBoxEnhance.stepsFor(350, 408), 2);
      expect(GameBoxEnhance.stepsFor(928, 1080), 1);
      expect(GameBoxEnhance.stepsFor(1166, 1888), 0);
      expect(GameBoxEnhance.stepsFor(3000, 200), 0);
    });
  });

  group('correction', () {
    test('every defect corrected is measured again below its limit', () {
      double measured(GameBoxPixels px, double Function(GameBoxImageDiagnosis d) f, {bool jpeg = false}) =>
          f(GameBoxEnhance.diagnose(GameBoxSharpScan.resample(px, card.width, card.height), jpeg: jpeg));
      final blurred = _blurred(card, sigma: 2.4);
      final blurBefore = measured(blurred, (d) => d.blur);
      final blurAfter = measured(GameBoxEnhance.deblur(blurred, GameBoxEnhance.sigmaForBlur(blurBefore)), (d) => d.blur);
      expect(blurAfter, lessThan(blurBefore - 0.05));
      final blocky = _blocky(card);
      expect(measured(GameBoxEnhance.smoothChroma(GameBoxEnhance.deblock(blocky)), (d) => d.blockiness, jpeg: true),
          lessThan(GameBoxImageDiagnosis.blockinessLimit));
      final noisy = _noisy(card);
      final noise = GameBoxEnhance.diagnose(noisy, jpeg: false).noise;
      expect(measured(GameBoxEnhance.denoise(noisy, noise), (d) => d.noise), lessThan(GameBoxImageDiagnosis.noiseLimit));
    });

    test('the enlargement keeps the known pixels and the proportions', () {
      final small = _card(80, 92);
      final big = GameBoxEnhance.double2x(small);
      expect((big.width, big.height), (160, 184));
      for (final (x, y) in [(0, 0), (10, 20), (79, 91), (40, 46)]) {
        for (var c = 0; c < 4; c++) {
          expect(big.rgba[((2 * y) * big.width + 2 * x) * 4 + c], small.rgba[(y * small.width + x) * 4 + c]);
        }
      }
    });

    test('a straight edge stays straight: no staircase across a diagonal', () {
      // A dark half-plane under a 45° diagonal, enlarged ×2.
      final w = 40;
      final rgba = Uint8List(w * w * 4);
      for (var y = 0; y < w; y++) {
        for (var x = 0; x < w; x++) {
          final v = x > y ? 230 : 20;
          rgba.setAll((y * w + x) * 4, [v, v, v, 255]);
        }
      }
      final big = GameBoxEnhance.double2x(GameBoxPixels(w, w, rgba));
      // Along the diagonal of the enlarged picture, the new pixels next to
      // it are interpolated along it, not across.
      for (var k = 4; k < 70; k += 2) {
        final off = big.rgba[((k + 3) * big.width + k) * 4];
        expect(off, lessThan(40), reason: 'below the edge at $k');
      }
    });
  });

  group('the files', () {
    late Directory dir;
    setUp(() {
      dir = Directory.systemTemp.createTempSync('gbenh');
      GameBoxEnhance.debugDirectory = Directory(p.join(dir.path, 'enhanced'));
      GameBoxEnhance.clearMemory();
      GameBoxEnhance.enabled = true;
    });
    tearDown(() {
      GameBoxEnhance.debugDirectory = null;
      GameBoxEnhance.clearMemory();
      GameBoxEnhance.enabled = true;
      dir.deleteSync(recursive: true);
    });

    testWidgets('a degraded back gets a corrected copy; the original stays byte for byte', (tester) async {
      await tester.runAsync(() async {
        final original = File(p.join(dir.path, 'media', 'ps3', 'box2dback', 'Bladestorm.png'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(await _png(_blurred(_card(160, 184), sigma: 0.8)));
        final digest = md5.convert(original.readAsBytesSync()).toString();
        final corrected = await GameBoxEnhance.prepare(original.path);
        expect(corrected, isNotNull);
        expect(corrected!.defects, contains(GameBoxImageDefect.lowResolution));
        expect((corrected.width, corrected.height), (1280, 1472));
        expect(corrected.factor, 8);
        expect(p.isWithin(GameBoxEnhance.debugDirectory!.path, corrected.path), isTrue);
        expect(md5.convert(original.readAsBytesSync()).toString(), digest, reason: 'the original is never written');
        expect(GameBoxEnhance.sourceOf(original.path), corrected.path);
        GameBoxEnhance.enabled = false;
        expect(GameBoxEnhance.sourceOf(original.path), original.path, reason: '"Sharp text" off shows the original');
        GameBoxEnhance.enabled = true;

        // After a restart, the copy and its report are read again, not redone.
        GameBoxEnhance.clearMemory();
        final stamp = File(corrected.path).lastModifiedSync();
        final again = await GameBoxEnhance.prepare(original.path);
        expect(again?.path, corrected.path);
        expect(again?.defects, corrected.defects);
        expect(File(corrected.path).lastModifiedSync(), stamp);
      });
    });

    testWidgets('a clean, large scan is left as it is, and remembered as such', (tester) async {
      await tester.runAsync(() async {
        final original = File(p.join(dir.path, 'front.png'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(await _png(_card(1200, 1700)));
        expect(await GameBoxEnhance.prepare(original.path), isNull);
        expect(GameBoxEnhance.sourceOf(original.path), original.path);
        final reports = GameBoxEnhance.debugDirectory!.listSync().map((f) => p.extension(f.path)).toList();
        expect(reports, ['.json'], reason: 'examined once, no copy');
      });
    });
  });

  group('a print in the scraping language is never swapped', () {
    const fr = GameBoxEditionHint(gameRegions: ['eu'], language: 'fr');
    GameBoxCandidate c(String region, {int? w, int? h, bool byProduct = true, GameBoxProvider provider = GameBoxProvider.screenscraper}) =>
        GameBoxCandidate(
          provider: provider, kind: GameBoxMediaKind.back, type: 't', identity: '$region$w', region: region,
          width: w, height: h, byProduct: byProduct, productId: provider == GameBoxProvider.gametdb ? 'BLES00113' : null,
          quality: provider == GameBoxProvider.gametdb ? 1 : 2,
        );

    test('a French thumbnail stays before a readable scan in another language', () {
      final thumb = c('fr', w: 160, h: 184, provider: GameBoxProvider.gametdb);
      final readable = c('eu', w: 928, h: 1080);
      expect(GameBoxCandidateRanking.preferReadable([thumb, readable], fr).first, thumb);
    });

    test('an English thumbnail gives way to a readable scan of the same edition, never of another', () {
      const en = GameBoxEditionHint(gameRegions: ['eu']);
      final thumb = c('uk', w: 160, h: 184, provider: GameBoxProvider.gametdb);
      final sameEdition = c('eu', w: 928, h: 1080);
      final american = c('us', w: 928, h: 1080);
      expect(GameBoxCandidateRanking.preferReadable([thumb, american], en).first, thumb);
      expect(GameBoxCandidateRanking.preferReadable([thumb, american, sameEdition], en).first, sameEdition);
      expect(GameBoxCandidateRanking.isThumbnail(thumb), isTrue);
      expect(GameBoxCandidateRanking.isThumbnail(sameEdition), isFalse);
    });

    test('the window of a sheet keeps its proportions (no stretch of a corrected copy)', () {
      // A ×8 copy has exactly the original's proportions, so the windows of
      // a full sheet (fractions) fall on the same panels.
      final wrap = GameBoxWrapLayout(panel: 928, spine: 144, height: 1080);
      final small = wrap.split(const Size(250, 135));
      final big = wrap.split(const Size(2000, 1080));
      expect(small?.back, big?.back);
    });
  });
}
