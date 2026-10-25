import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/painting.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_sharp_scan.dart';
import 'package:path/path.dart' as p;

/// The back scan made for the size it is shown at (docs/game-box-3d.md § 12):
/// exact resampling, the light sharpening of the brightness, and how close
/// small print comes to the same text drawn directly at that size, against a
/// model of the GPU's trilinear filtering of a larger decode (what the box
/// showed before Build 494).

GameBoxPixels _solid(int w, int h, List<int> rgba) {
  final data = Uint8List(w * h * 4);
  for (var i = 0; i < w * h; i++) {
    data.setRange(i * 4, i * 4 + 4, rgba);
  }
  return GameBoxPixels(w, h, data);
}

/// Mipmap pyramid by 2 × 2 averaging, as the GPU builds it.
List<GameBoxPixels> _pyramid(GameBoxPixels base, int levels) {
  final out = [base];
  for (var l = 1; l <= levels; l++) {
    final s = out.last;
    final w = math.max(1, s.width ~/ 2), h = math.max(1, s.height ~/ 2);
    final d = Uint8List(w * h * 4);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        for (var c = 0; c < 4; c++) {
          int at(int xx, int yy) => s.rgba[(math.min<int>(yy, s.height - 1) * s.width + math.min<int>(xx, s.width - 1)) * 4 + c];
          d[(y * w + x) * 4 + c] = (at(2 * x, 2 * y) + at(2 * x + 1, 2 * y) + at(2 * x, 2 * y + 1) + at(2 * x + 1, 2 * y + 1) + 2) >> 2;
        }
      }
    }
    out.add(GameBoxPixels(w, h, d));
  }
  return out;
}

double _bilinear(GameBoxPixels img, double u, double v, int c) {
  final x = u * img.width - 0.5, y = v * img.height - 0.5;
  final x0 = x.floor(), y0 = y.floor();
  final fx = x - x0, fy = y - y0;
  int at(int xx, int yy) =>
      img.rgba[(yy.clamp(0, img.height - 1) * img.width + xx.clamp(0, img.width - 1)) * 4 + c];
  final top = at(x0, y0) * (1 - fx) + at(x0 + 1, y0) * fx;
  final bottom = at(x0, y0 + 1) * (1 - fx) + at(x0 + 1, y0 + 1) * fx;
  return top * (1 - fy) + bottom * fy;
}

/// Model of drawing [src] at [tw] × [th] with linear filtering between two
/// mipmap levels (FilterQuality.medium of the box's faces).
GameBoxPixels _trilinear(GameBoxPixels src, int tw, int th) {
  final lod = math.log(src.width / tw) / math.ln2;
  final l0 = lod.floor(), f = lod - l0;
  final pyramid = _pyramid(src, l0 + 1);
  final out = Uint8List(tw * th * 4);
  for (var y = 0; y < th; y++) {
    for (var x = 0; x < tw; x++) {
      final u = (x + 0.5) / tw, v = (y + 0.5) / th;
      for (var c = 0; c < 4; c++) {
        final a = _bilinear(pyramid[l0], u, v, c), b = _bilinear(pyramid[l0 + 1], u, v, c);
        out[(y * tw + x) * 4 + c] = (a * (1 - f) + b * f).round().clamp(0, 255);
      }
    }
  }
  return GameBoxPixels(tw, th, out);
}

Uint8List _gray(GameBoxPixels img) {
  final g = Uint8List(img.width * img.height);
  for (var i = 0; i < g.length; i++) {
    g[i] = (77 * img.rgba[i * 4] + 150 * img.rgba[i * 4 + 1] + 29 * img.rgba[i * 4 + 2] + 128) >> 8;
  }
  return g;
}

double _psnr(GameBoxPixels a, GameBoxPixels b) {
  final x = _gray(a), y = _gray(b);
  var se = 0.0;
  for (var i = 0; i < x.length; i++) {
    final d = x[i] - y[i];
    se += d * d;
  }
  final mse = se / x.length;
  return 10 * math.log(255 * 255 / math.max(mse, 1e-9)) / math.ln10;
}

/// Mean gradient magnitude: how crisp the strokes are.
double _acutance(GameBoxPixels img) {
  final g = _gray(img);
  var sum = 0.0;
  for (var y = 1; y < img.height; y++) {
    for (var x = 1; x < img.width; x++) {
      final i = y * img.width + x;
      sum += (g[i] - g[i - 1]).abs() + (g[i] - g[i - img.width]).abs();
    }
  }
  return sum / (img.width * img.height);
}

String? _roboto() {
  final candidates = <String>[
    if (Platform.environment['FLUTTER_ROOT'] case final root?) p.join(root, 'bin/cache/artifacts/material_fonts'),
  ];
  // flutter_tester runs from <sdk>/bin/cache/artifacts/engine/<platform>/.
  final exe = File(Platform.resolvedExecutable).absolute.path;
  final i = exe.indexOf('${p.separator}bin${p.separator}cache${p.separator}');
  if (i > 0) candidates.add(p.join(exe.substring(0, i), 'bin/cache/artifacts/material_fonts'));
  for (final dir in candidates) {
    final f = File(p.join(dir, 'Roboto-Regular.ttf'));
    if (f.existsSync()) return f.path;
  }
  return null;
}

const _paragraph =
    'Explore forty dangerous caves, gather the seven crystals and defeat the Shadow King before the '
    'last moon rises. Memory card with at least two free blocks required. Licensed for home use only.';

/// Small print drawn at [scale] of a 2400 px scan width (dark on light, as
/// most back panels).
Future<GameBoxPixels> _print(double scale, {int width = 2400, int height = 520}) async {
  final w = (width * scale).round(), h = (height * scale).round();
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.drawRect(Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()), Paint()..color = const Color(0xFFF1ECDF));
  canvas.scale(scale);
  final tp = TextPainter(
    text: const TextSpan(
      text: _paragraph,
      style: TextStyle(fontFamily: 'Roboto', fontSize: 30, color: Color(0xFF1B1B22), height: 1.25),
    ),
    textDirection: TextDirection.ltr,
  )..layout(maxWidth: width - 120.0);
  tp.paint(canvas, const Offset(60, 40));
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  image.dispose();
  return GameBoxPixels(w, h, data!.buffer.asUint8List());
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('resampling', () {
    test('a flat colour stays exactly flat, at every ratio', () {
      final src = _solid(97, 61, [200, 120, 40, 255]);
      for (final (tw, th) in [(48, 30), (31, 20), (13, 9), (96, 60)]) {
        final out = GameBoxSharpScan.resample(src, tw, th);
        expect(out.width, tw);
        expect(out.height, th);
        for (var i = 0; i < tw * th; i++) {
          expect(out.rgba.sublist(i * 4, i * 4 + 4), [200, 120, 40, 255], reason: '$tw × $th pixel $i');
        }
      }
    });

    test('the Mitchell-Netravali kernel (B = C = 1/3)', () {
      expect(GameBoxSharpScan.mitchell(0), closeTo(8 / 9, 1e-12));
      expect(GameBoxSharpScan.mitchell(1), closeTo(1 / 18, 1e-12));
      expect(GameBoxSharpScan.mitchell(2), 0);
      expect(GameBoxSharpScan.mitchell(-0.5), closeTo(GameBoxSharpScan.mitchell(0.5), 1e-12));
      // Unit sum over the integer grid at any phase: a flat area stays flat.
      for (final phase in [0.0, 0.25, 0.5]) {
        var sum = 0.0;
        for (var k = -3; k <= 3; k++) {
          sum += GameBoxSharpScan.mitchell(k + phase);
        }
        expect(sum, closeTo(1, 1e-9));
      }
    });

    test('premultiplied colours never exceed their alpha (no ringing out of range)', () {
      final rnd = math.Random(4);
      final w = 120, h = 80;
      final data = Uint8List(w * h * 4);
      for (var i = 0; i < w * h; i++) {
        final a = rnd.nextBool() ? 255 : rnd.nextInt(256);
        data[i * 4 + 3] = a;
        for (var c = 0; c < 3; c++) {
          data[i * 4 + c] = rnd.nextInt(a + 1);
        }
      }
      for (final img in [
        GameBoxSharpScan.resample(GameBoxPixels(w, h, data), 47, 31),
        GameBoxSharpScan.sharpenLuma(GameBoxPixels(w, h, data)),
      ]) {
        for (var i = 0; i < img.width * img.height; i++) {
          final a = img.rgba[i * 4 + 3];
          for (var c = 0; c < 3; c++) {
            expect(img.rgba[i * 4 + c], lessThanOrEqualTo(a));
          }
        }
      }
    });

    test('a render is never wider than its scan, and small gestures reuse it', () {
      expect(GameBoxSharpScan.targetWidth(2400, 870), 896, reason: 'rounded up to 64 px');
      expect(GameBoxSharpScan.targetWidth(1000, 2600), 1000, reason: 'never enlarged');
      expect(GameBoxSharpScan.targetWidth(9000, 8000), GameBoxSharpScan.maxWidth);
      expect(GameBoxSharpScan.closeEnough(896, 960), isTrue);
      expect(GameBoxSharpScan.closeEnough(896, 1280), isFalse);
    });
  });

  group('sharpening', () {
    test('grain below the threshold is left alone; an edge gains contrast without colour fringes', () {
      // Faint noise of ±2 on grey.
      final w = 64, h = 32;
      final noisy = Uint8List(w * h * 4);
      final rnd = math.Random(7);
      for (var i = 0; i < w * h; i++) {
        final v = 128 + rnd.nextInt(5) - 2;
        noisy.setRange(i * 4, i * 4 + 4, [v, v, v, 255]);
      }
      final quiet = GameBoxSharpScan.sharpenLuma(GameBoxPixels(w, h, noisy));
      var changed = 0;
      for (var i = 0; i < noisy.length; i++) {
        if (quiet.rgba[i] != noisy[i]) changed++;
      }
      expect(changed, 0, reason: 'nothing below the threshold is touched');

      // A coloured edge: dark blue on beige.
      final edge = _solid(w, h, [240, 230, 210, 255]);
      for (var y = 0; y < h; y++) {
        for (var x = w ~/ 2; x < w; x++) {
          edge.rgba.setRange((y * w + x) * 4, (y * w + x) * 4 + 4, [20, 30, 90, 255]);
        }
      }
      final soft = GameBoxSharpScan.resample(edge, 40, 20);
      final crisp = GameBoxSharpScan.sharpenLuma(soft);
      expect(_acutance(crisp), greaterThan(_acutance(soft)));
      // The same brightness correction on the three channels.
      for (var i = 0; i < 40 * 20; i++) {
        final d = [for (var c = 0; c < 3; c++) crisp.rgba[i * 4 + c] - soft.rgba[i * 4 + c]];
        final clipped = [for (var c = 0; c < 3; c++) crisp.rgba[i * 4 + c] == 0 || crisp.rgba[i * 4 + c] == 255]
            .any((e) => e);
        if (!clipped) expect((d[0] - d[2]).abs(), lessThanOrEqualTo(1), reason: 'pixel $i: $d');
      }
    });
  });

  group('small print', () {
    final roboto = _roboto();

    setUpAll(() async {
      if (roboto == null) return;
      final loader = FontLoader('Roboto')
        ..addFont(File(roboto).readAsBytes().then((b) => ByteData.view(b.buffer)));
      await loader.load();
    });

    test('as close to the text drawn at that size as trilinear filtering of the decode, and as crisp', () async {
      expect(roboto, isNotNull, reason: 'Roboto of the Flutter SDK (material_fonts)');
      final report = <String, Object>{};
      // 2400 px decode shown 896, 640 and 1280 px wide (zoom 1 on a phone,
      // a smaller box, a closer look).
      for (final shown in [896, 640, 1280]) {
        final ratio = shown / 2400;
        final decode = await _print(1);
        final reference = await _print(ratio);
        final th = reference.height;
        final gpu = _trilinear(decode, shown, th);
        final exact = GameBoxSharpScan.resample(decode, shown, th);
        final sharpened = GameBoxSharpScan.sharpenLuma(exact);
        final r = {
          'psnrTrilinear': _psnr(gpu, reference),
          'psnrExact': _psnr(exact, reference),
          'psnrSharpened': _psnr(sharpened, reference),
          'acutanceReference': _acutance(reference),
          'acutanceTrilinear': _acutance(gpu),
          'acutanceExact': _acutance(exact),
          'acutanceSharpened': _acutance(sharpened),
        };
        report['$shown'] = r;
        // Closer to the text drawn at that size than the GPU's filtering.
        expect(r['psnrExact']!, greaterThan(r['psnrTrilinear']!), reason: '$shown: $r');
        // As crisp as that text (within 12 %), clearly crisper than before.
        expect(r['acutanceExact']! / r['acutanceReference']!, inInclusiveRange(0.88, 1.12), reason: '$shown: $r');
        expect(r['acutanceExact']!, greaterThan(r['acutanceTrilinear']! * 1.08), reason: '$shown: $r');
        // The light sharpening: crisper still, at no real cost in fidelity.
        expect(r['acutanceSharpened']!, greaterThan(r['acutanceExact']! * 1.1), reason: '$shown: $r');
        expect(r['psnrSharpened']!, greaterThan(r['psnrTrilinear']! - 1.0), reason: '$shown: $r');
      }
      final out = Platform.environment['GAME_BOX_SHARP_REPORT'];
      if (out != null) File(out).writeAsStringSync('$report');
      // ignore: avoid_print
      print('small print: $report');
    }, skip: roboto == null && Platform.environment['CI'] != 'true' ? 'Roboto not found' : false);

    test('a 2400 × 3400 back is resampled and sharpened in bounded time', () async {
      final w = 2400, h = 3400;
      final data = Uint8List(w * h * 4);
      final rnd = math.Random(1);
      for (var i = 0; i < data.length; i++) {
        data[i] = (i & 3) == 3 ? 255 : rnd.nextInt(256);
      }
      final watch = Stopwatch()..start();
      final out = GameBoxSharpScan.sharpenLuma(GameBoxSharpScan.resample(GameBoxPixels(w, h, data), 896, 1269));
      watch.stop();
      expect(out.width, 896);
      // ignore: avoid_print
      print('2400 × 3400 → 896 × 1269 + sharpening: ${watch.elapsedMilliseconds} ms (host, not iPhone)');
      expect(watch.elapsed, lessThan(const Duration(seconds: 20)));
    });
  });
}
