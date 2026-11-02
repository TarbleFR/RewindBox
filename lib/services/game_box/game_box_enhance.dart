import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_sharp_scan.dart';
import 'package:neostation/services/logger_service.dart';

/// A defect found in a picture by [GameBoxEnhance.diagnose].
enum GameBoxImageDefect {
  /// Too few pixels for its print to read at full screen.
  lowResolution,

  /// The 8 × 8 blocks of a strong JPEG compression show.
  jpegBlocks,

  /// Grain or sensor noise over flat areas.
  noise,

  /// Soft edges: a blurred scan or a picture enlarged before.
  blur,

  /// Washed-out tones: the darkest and lightest parts are close.
  faded,
}

/// What [GameBoxEnhance.diagnose] measured in a picture, and the defects
/// those measures show.
@immutable
class GameBoxImageDiagnosis {
  const GameBoxImageDiagnosis({
    required this.width,
    required this.height,
    required this.blockiness,
    required this.blur,
    required this.noise,
    required this.range,
    required this.jpeg,
  });

  final int width;
  final int height;

  /// Step across the 8 × 8 borders over the step elsewhere (≈ 1 when clean).
  final double blockiness;

  /// No-reference blur measure of Crété-Roffet et al. (2007): 0 sharp, 1
  /// fully blurred.
  final double blur;

  /// Standard deviation of the noise over flat areas, in 0..255 levels
  /// (Immerkær 1996, restricted to the flattest half of the picture).
  final double noise;

  /// Brightness range between the 1st and 99th percentiles (0..255).
  final int range;
  final bool jpeg;

  static const double blockinessLimit = 1.18;
  static const double blurLimit = 0.42;
  static const double noiseLimit = 6.0;
  static const int fadedRange = 150;

  int get steps => GameBoxEnhance.stepsFor(width, height);

  Set<GameBoxImageDefect> get defects => {
        if (steps > 0) GameBoxImageDefect.lowResolution,
        if (jpeg && blockiness > blockinessLimit) GameBoxImageDefect.jpegBlocks,
        if (noise > noiseLimit) GameBoxImageDefect.noise,
        if (blur > blurLimit) GameBoxImageDefect.blur,
        if (range < fadedRange) GameBoxImageDefect.faded,
      };

  Map<String, Object> toJson() => {
        'width': width,
        'height': height,
        'blockiness': blockiness,
        'blur': blur,
        'noise': noise,
        'range': range,
        'jpeg': jpeg,
      };

  static GameBoxImageDiagnosis? fromJson(Object? raw) {
    if (raw is! Map) return null;
    double d(String k) => (raw[k] as num?)?.toDouble() ?? 0;
    return GameBoxImageDiagnosis(
      width: (raw['width'] as num?)?.toInt() ?? 0,
      height: (raw['height'] as num?)?.toInt() ?? 0,
      blockiness: d('blockiness'),
      blur: d('blur'),
      noise: d('noise'),
      range: (raw['range'] as num?)?.toInt() ?? 255,
      jpeg: raw['jpeg'] == true,
    );
  }

  @override
  String toString() => 'blocks ${blockiness.toStringAsFixed(2)}, blur ${blur.toStringAsFixed(2)}, '
      'noise ${noise.toStringAsFixed(1)}, range $range, ${width}x$height -> ${defects.map((d) => d.name).join('+')}';
}

/// A corrected copy of a picture, kept beside the original.
@immutable
class GameBoxEnhanced {
  const GameBoxEnhanced({
    required this.path,
    required this.sourceWidth,
    required this.sourceHeight,
    required this.width,
    required this.height,
    required this.diagnosis,
  });

  /// The corrected PNG (cache); the original is never changed.
  final String path;
  final int sourceWidth;
  final int sourceHeight;
  final int width;
  final int height;
  final GameBoxImageDiagnosis diagnosis;

  Set<GameBoxImageDefect> get defects => diagnosis.defects;

  int get factor => sourceWidth <= 0 ? 1 : (width / sourceWidth).round();
}

/// Correction of a degraded picture (docs/game-box-3d.md § 22), whatever the
/// picture: a front, back, spine or full sheet, in French or not.
///
/// The picture is first examined; only the defects found are corrected, on a
/// copy. The original file stays as it is and is never replaced by another
/// scan: a French cover stays the French cover, corrected.
///
/// | Defect found | Correction |
/// |---|---|
/// | JPEG blocks | weak deblocking filter on the 8 × 8 borders |
/// | noise | edge-preserving (bilateral) smoothing sized to the noise |
/// | washed-out tones | partial stretch of the 1–99 % range |
/// | blur | Richardson-Lucy deconvolution of the brightness (Gaussian blur of the measured width) |
/// | low resolution | directional cubic convolution (DCCI), ×2 per step, then a light unsharp mask |
///
/// Every step is computed from the picture's own pixels: nothing is drawn
/// that it does not hold (no generative model). Print smaller than about two
/// pixels per stroke in the original stays unreadable.
///
/// The result is cached on the device ([debugDirectory] in tests), keyed by
/// the original's path, size and date and by the process [version]: a new
/// download at the same path is examined again. A picture without defect is
/// remembered as such and shown as it is.
class GameBoxEnhance {
  GameBoxEnhance._();

  /// Long side a picture should reach to read well at full screen.
  static const int readableSide = 1600;

  /// Longest side of an enlarged picture (memory of the decode).
  static const int maxSide = 3200;

  /// At most ×8 (three ×2 steps).
  static const int maxSteps = 3;

  /// Larger pictures are left as they are (they are good scans, and their
  /// examination would cost too much memory).
  static const int maxExaminedPixels = 6 * 1024 * 1024;

  /// Version of the process, part of the cache key.
  static const int version = 2;

  /// Corrected copies are shown (the viewer's "Sharp text"); off, the
  /// originals are.
  static bool enabled = true;

  @visibleForTesting
  static Directory? debugDirectory;

  static final Map<String, GameBoxEnhanced?> _ready = {};
  static final Map<String, Future<GameBoxEnhanced?>> _running = {};

  /// Number of ×2 steps for a picture [width] × [height]: enough for its long
  /// side to reach [readableSide], without passing [maxSide]; 0 when it is
  /// already large enough.
  static int stepsFor(int width, int height) {
    final long = math.max(width, height);
    if (long <= 0 || long >= readableSide) return 0;
    var steps = 0;
    var side = long;
    while (steps < maxSteps && side < readableSide && side * 2 <= maxSide) {
      side *= 2;
      steps++;
    }
    return steps;
  }

  /// The corrected copy of [path] once prepared, or null.
  static GameBoxEnhanced? of(String? path) => path == null ? null : _ready[path];

  /// The file to decode for [path]: its corrected copy when prepared and
  /// [enabled], else the original.
  static String sourceOf(String path) => enabled ? (_ready[path]?.path ?? path) : path;

  /// Forgets the copy of [path] (its file was replaced).
  static void evict(String path) {
    _ready.remove(path);
    _running.remove(path);
  }

  @visibleForTesting
  static void clearMemory() {
    _ready.clear();
    _running.clear();
  }

  static Future<Directory> _directory() async {
    final override = debugDirectory;
    if (override != null) return override;
    final support = await getApplicationSupportDirectory();
    return Directory(p.join(support.path, 'NeoStation', 'GameBox', 'enhanced'));
  }

  /// Examines [path] and corrects the defects found (see the class), from
  /// the cache when it was done before. Null when the picture has no defect
  /// or cannot be read; the original is never changed.
  static Future<GameBoxEnhanced?> prepare(String path) {
    if (_ready.containsKey(path)) return Future.value(_ready[path]);
    return _running[path] ??= _prepare(path).then((r) {
      _running.remove(path);
      _ready[path] = r;
      return r;
    });
  }

  static Future<GameBoxEnhanced?> _prepare(String path) async {
    try {
      final size = GameBoxImageSize.of(path);
      if (size == null || size.width * size.height > maxExaminedPixels) return null;
      final file = File(path);
      final stat = await file.stat();
      final dir = await _directory();
      final owner = sha1.convert(utf8.encode(path)).toString().substring(0, 16);
      final key = sha1
          .convert(utf8.encode('${stat.size}|${stat.modified.millisecondsSinceEpoch}|v$version'))
          .toString()
          .substring(0, 12);
      final target = File(p.join(dir.path, '$owner-$key.png'));
      final report = File(p.join(dir.path, '$owner-$key.json'));
      final sw = size.width.round(), sh = size.height.round();
      if (await report.exists()) {
        final diagnosis = GameBoxImageDiagnosis.fromJson(jsonDecode(await report.readAsString()));
        if (diagnosis != null && diagnosis.defects.isEmpty) return null;
        final done = await target.exists() ? GameBoxImageSize.of(target.path) : null;
        if (diagnosis != null && done != null) {
          return GameBoxEnhanced(
            path: target.path,
            sourceWidth: sw,
            sourceHeight: sh,
            width: done.width.round(),
            height: done.height.round(),
            diagnosis: diagnosis,
          );
        }
      }
      final bytes = await file.readAsBytes();
      final jpeg = bytes.length > 2 && bytes[0] == 0xFF && bytes[1] == 0xD8;
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      final codec = await ui.instantiateImageCodecFromBuffer(buffer);
      final frame = await codec.getNextFrame();
      codec.dispose();
      final image = frame.image;
      final w = image.width, h = image.height;
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      image.dispose();
      if (data == null) return null;
      final input = TransferableTypedData.fromList([data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes)]);
      final result = await Isolate.run(() {
        final px = GameBoxPixels(w, h, input.materialize().asUint8List());
        final diagnosis = diagnose(px, jpeg: jpeg);
        if (diagnosis.defects.isEmpty) return (null, 0, 0, diagnosis.toJson());
        final out = repair(px, diagnosis);
        return (TransferableTypedData.fromList([out.rgba]), out.width, out.height, diagnosis.toJson());
      });
      final (pixels, ow, oh, json) = result;
      final diagnosis = GameBoxImageDiagnosis.fromJson(json)!;
      await dir.create(recursive: true);
      // Older copies of the same original go.
      await for (final old in dir.list()) {
        final name = p.basename(old.path);
        if (name.startsWith('$owner-') && !name.startsWith('$owner-$key')) {
          try {
            await old.delete();
          } catch (_) {}
        }
      }
      final log = LoggerService.instance;
      if (pixels == null) {
        await report.writeAsString(jsonEncode(json));
        log.i('GameBox: $path examined, no defect ($diagnosis).');
        return null;
      }
      final completer = Completer<ui.Image>();
      ui.decodeImageFromPixels(pixels.materialize().asUint8List(), ow, oh, ui.PixelFormat.rgba8888, completer.complete);
      final corrected = await completer.future;
      final png = await corrected.toByteData(format: ui.ImageByteFormat.png);
      corrected.dispose();
      if (png == null) return null;
      final temp = File('${target.path}.part');
      await temp.writeAsBytes(png.buffer.asUint8List(png.offsetInBytes, png.lengthInBytes), flush: true);
      await temp.rename(target.path);
      await report.writeAsString(jsonEncode(json));
      log.i('GameBox: corrected $path ($diagnosis) -> ${ow}x$oh, original kept.');
      return GameBoxEnhanced(
        path: target.path,
        sourceWidth: sw,
        sourceHeight: sh,
        width: ow,
        height: oh,
        diagnosis: diagnosis,
      );
    } catch (e) {
      LoggerService.instance.w('GameBox: correction of $path failed: $e');
      return null;
    }
  }

  // Examination ----------------------------------------------------------------

  /// Brightness (0..255) of every pixel.
  static Float32List lumaOf(GameBoxPixels px) {
    final n = px.width * px.height, rgba = px.rgba;
    final out = Float32List(n);
    for (var i = 0, j = 0; i < n; i++, j += 4) {
      out[i] = 0.299 * rgba[j] + 0.587 * rgba[j + 1] + 0.114 * rgba[j + 2];
    }
    return out;
  }

  /// Measures the picture (see [GameBoxImageDiagnosis]).
  static GameBoxImageDiagnosis diagnose(GameBoxPixels px, {required bool jpeg}) {
    final luma = lumaOf(px);
    return GameBoxImageDiagnosis(
      width: px.width,
      height: px.height,
      blockiness: jpeg ? blockiness(px) : 1,
      blur: blurMeasure(luma, px.width, px.height),
      noise: noiseMeasure(luma, px.width, px.height),
      range: tonalRange(luma),
      jpeg: jpeg,
    );
  }

  /// Blur measure of Crété-Roffet, Dolmière, Ladret & Nicolas (2007): the
  /// share of the picture's neighbour-to-neighbour variation that a further
  /// 9-pixel blur does not remove. 0 = sharp, 1 = fully blurred.
  static double blurMeasure(Float32List luma, int w, int h) {
    if (w < 12 || h < 12) return 0;
    double along(bool horizontal) {
      final len = horizontal ? w : h, lines = horizontal ? h : w;
      var sumF = 0.0, sumV = 0.0;
      final line = Float32List(len), blurred = Float32List(len);
      for (var l = 0; l < lines; l++) {
        for (var i = 0; i < len; i++) {
          line[i] = horizontal ? luma[l * w + i] : luma[i * w + l];
        }
        for (var i = 0; i < len; i++) {
          var s = 0.0;
          for (var k = -4; k <= 4; k++) {
            s += line[(i + k).clamp(0, len - 1)];
          }
          blurred[i] = s / 9;
        }
        for (var i = 1; i < len; i++) {
          final dF = (line[i] - line[i - 1]).abs();
          final dB = (blurred[i] - blurred[i - 1]).abs();
          sumF += dF;
          sumV += math.max(0, dF - dB);
        }
      }
      return sumF <= 0 ? 1 : (sumF - sumV) / sumF;
    }

    return math.max(along(true), along(false));
  }

  /// Noise of Immerkær (1996) — the Laplacian difference mask — measured on
  /// the flattest half of the picture, where print edges do not count.
  static double noiseMeasure(Float32List luma, int w, int h) {
    if (w < 8 || h < 8) return 0;
    final grads = <double>[];
    final responses = <double>[];
    for (var y = 1; y < h - 1; y++) {
      for (var x = 1; x < w - 1; x++) {
        final i = y * w + x;
        double v(int dx, int dy) => luma[i + dy * w + dx];
        final gx = (v(1, -1) + 2 * v(1, 0) + v(1, 1)) - (v(-1, -1) + 2 * v(-1, 0) + v(-1, 1));
        final gy = (v(-1, 1) + 2 * v(0, 1) + v(1, 1)) - (v(-1, -1) + 2 * v(0, -1) + v(1, -1));
        grads.add(gx.abs() + gy.abs());
        final n = v(-1, -1) - 2 * v(0, -1) + v(1, -1) - 2 * v(-1, 0) + 4 * v(0, 0) - 2 * v(1, 0) +
            v(-1, 1) - 2 * v(0, 1) + v(1, 1);
        responses.add(n.abs());
      }
    }
    if (grads.isEmpty) return 0;
    final sorted = [...grads]..sort();
    final limit = sorted[sorted.length ~/ 2];
    var sum = 0.0;
    var count = 0;
    for (var i = 0; i < grads.length; i++) {
      if (grads[i] > limit) continue;
      sum += responses[i];
      count++;
    }
    if (count == 0) return 0;
    return math.sqrt(math.pi / 2) * sum / (6 * count);
  }

  /// Brightness between the 1st and 99th percentiles.
  static int tonalRange(Float32List luma) {
    final (lo, hi) = _percentiles(luma);
    return hi - lo;
  }

  static (int, int) _percentiles(Float32List luma) {
    final hist = List<int>.filled(256, 0);
    for (final v in luma) {
      hist[v.round().clamp(0, 255)]++;
    }
    final n = luma.length;
    var acc = 0, lo = 0, hi = 255;
    for (var i = 0; i < 256; i++) {
      acc += hist[i];
      if (acc >= n * 0.01) {
        lo = i;
        break;
      }
    }
    acc = 0;
    for (var i = 255; i >= 0; i--) {
      acc += hist[i];
      if (acc >= n * 0.01) {
        hi = i;
        break;
      }
    }
    return (lo, math.max(lo, hi));
  }

  // Repair --------------------------------------------------------------------

  /// Corrects the defects of [diagnosis] in their order: blocks, noise,
  /// tones, blur, then size.
  static GameBoxPixels repair(GameBoxPixels src, GameBoxImageDiagnosis diagnosis) {
    final defects = diagnosis.defects;
    var px = src;
    if (defects.contains(GameBoxImageDefect.jpegBlocks)) px = smoothChroma(deblock(px));
    if (defects.contains(GameBoxImageDefect.noise)) px = denoise(px, diagnosis.noise);
    if (defects.contains(GameBoxImageDefect.faded)) px = stretchTones(px);
    if (defects.contains(GameBoxImageDefect.blur)) px = deblur(px, sigmaForBlur(diagnosis.blur));
    final steps = diagnosis.steps;
    for (var i = 0; i < steps; i++) {
      px = double2x(px);
    }
    if (steps > 0) px = GameBoxSharpScan.sharpenLuma(px, amount: 0.25, sigma: 1.0, threshold: 4);
    return px;
  }

  /// Width (Gaussian sigma, pixels) of the blur measured as [blur],
  /// calibrated on scans blurred on purpose: a sharp scan measures about
  /// 0.2, the same scan under a 1.6 px Gaussian blur about 0.52.
  static double sigmaForBlur(double blur) => (0.5 + (blur - 0.2) * 3.4).clamp(0.8, 2.2);

  /// Edge-preserving smoothing (bilateral, 5 × 5): neighbours whose
  /// brightness differs by more than the noise count less, so print edges
  /// stay while the grain goes.
  static GameBoxPixels denoise(GameBoxPixels src, double noise) {
    final w = src.width, h = src.height, rgba = src.rgba;
    final luma = lumaOf(src);
    final out = Uint8List.fromList(rgba);
    final range = math.max(2.0, noise * 2.2);
    final spatial = Float64List(25);
    for (var dy = -2; dy <= 2; dy++) {
      for (var dx = -2; dx <= 2; dx++) {
        spatial[(dy + 2) * 5 + dx + 2] = math.exp(-(dx * dx + dy * dy) / (2 * 1.4 * 1.4));
      }
    }
    final rangeLut = Float64List(256);
    for (var d = 0; d < 256; d++) {
      rangeLut[d] = math.exp(-(d * d) / (2 * range * range));
    }
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        final i = y * w + x;
        final l0 = luma[i];
        var r = 0.0, g = 0.0, b = 0.0, a = 0.0, ws = 0.0;
        for (var dy = -2; dy <= 2; dy++) {
          final yy = (y + dy).clamp(0, h - 1);
          for (var dx = -2; dx <= 2; dx++) {
            final xx = (x + dx).clamp(0, w - 1);
            final j = yy * w + xx;
            final wt = spatial[(dy + 2) * 5 + dx + 2] * rangeLut[(luma[j] - l0).abs().round().clamp(0, 255)];
            final k = j * 4;
            r += rgba[k] * wt;
            g += rgba[k + 1] * wt;
            b += rgba[k + 2] * wt;
            a += rgba[k + 3] * wt;
            ws += wt;
          }
        }
        final o = i * 4;
        final oa = _byte(a / ws);
        out[o] = math.min(_byte(r / ws), oa);
        out[o + 1] = math.min(_byte(g / ws), oa);
        out[o + 2] = math.min(_byte(b / ws), oa);
        out[o + 3] = oa;
      }
    }
    return GameBoxPixels(w, h, out);
  }

  /// Washed-out tones brought part of the way to a full range: the 1st and
  /// 99th percentiles move [strength] of the way toward 6 and 249.
  static GameBoxPixels stretchTones(GameBoxPixels src, {double strength = 0.6}) {
    final (lo, hi) = _percentiles(lumaOf(src));
    if (hi - lo < 8) return src;
    final newLo = lo - (lo - 6) * strength, newHi = hi + (249 - hi) * strength;
    final k = (newHi - newLo) / (hi - lo);
    final rgba = src.rgba;
    final out = Uint8List.fromList(rgba);
    for (var j = 0; j < rgba.length; j += 4) {
      final a = rgba[j + 3];
      if (a == 0) continue;
      final f = a / 255;
      for (var c = 0; c < 3; c++) {
        // Premultiplied: the stretch applies to the colour, then alpha again.
        final v = (rgba[j + c] / f - lo) * k + newLo;
        out[j + c] = math.min(_byte(v * f), a);
      }
    }
    return GameBoxPixels(src.width, src.height, out);
  }

  /// Richardson-Lucy deconvolution of the brightness for a Gaussian blur of
  /// [sigma] pixels, [iterations] times; the change found is applied to the
  /// three channels alike (no colour fringes) and bounded, so that edges
  /// sharpen without halos.
  static GameBoxPixels deblur(GameBoxPixels src, double sigma, {int iterations = 12, double limit = 56}) {
    final w = src.width, h = src.height;
    final observed = lumaOf(src);
    for (var i = 0; i < observed.length; i++) {
      observed[i] += 1; // never zero
    }
    var estimate = Float32List.fromList(observed);
    for (var k = 0; k < iterations; k++) {
      final blurred = _gaussian(estimate, w, h, sigma);
      final ratio = Float32List(observed.length);
      for (var i = 0; i < ratio.length; i++) {
        ratio[i] = (observed[i] / math.max(blurred[i], 1e-3)).clamp(0.5, 2.0);
      }
      final correction = _gaussian(ratio, w, h, sigma);
      final next = Float32List(observed.length);
      for (var i = 0; i < next.length; i++) {
        next[i] = (estimate[i] * correction[i]).clamp(1.0, 256.0);
      }
      estimate = next;
    }
    final rgba = src.rgba;
    final out = Uint8List.fromList(rgba);
    for (var i = 0, j = 0; i < observed.length; i++, j += 4) {
      final a = rgba[j + 3];
      if (a == 0) continue;
      final delta = (estimate[i] - observed[i]).clamp(-limit, limit) * a / 255;
      out[j] = math.min(_byte(rgba[j] + delta), a);
      out[j + 1] = math.min(_byte(rgba[j + 1] + delta), a);
      out[j + 2] = math.min(_byte(rgba[j + 2] + delta), a);
    }
    return GameBoxPixels(w, h, out);
  }

  static Float32List _gaussian(Float32List src, int w, int h, double sigma) {
    final radius = math.max(1, (sigma * 3).ceil());
    final kernel = Float64List(radius * 2 + 1);
    var total = 0.0;
    for (var k = -radius; k <= radius; k++) {
      kernel[k + radius] = math.exp(-(k * k) / (2 * sigma * sigma));
      total += kernel[k + radius];
    }
    for (var k = 0; k < kernel.length; k++) {
      kernel[k] /= total;
    }
    final tmp = Float32List(w * h);
    for (var y = 0; y < h; y++) {
      final row = y * w;
      for (var x = 0; x < w; x++) {
        var s = 0.0;
        for (var k = -radius; k <= radius; k++) {
          s += src[row + (x + k).clamp(0, w - 1)] * kernel[k + radius];
        }
        tmp[row + x] = s;
      }
    }
    final out = Float32List(w * h);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var s = 0.0;
        for (var k = -radius; k <= radius; k++) {
          s += tmp[(y + k).clamp(0, h - 1) * w + x] * kernel[k + radius];
        }
        out[y * w + x] = s;
      }
    }
    return out;
  }

  static int _byte(double v) => v <= 0 ? 0 : (v >= 255 ? 255 : (v + 0.5).toInt());

  // JPEG deblocking -------------------------------------------------------------

  /// Ratio above which the 8 × 8 grid of a JPEG shows.
  static const double blockinessThreshold = GameBoxImageDiagnosis.blockinessLimit;

  static int _luma(Uint8List rgba, int i) => (77 * rgba[i] + 150 * rgba[i + 1] + 29 * rgba[i + 2] + 128) >> 8;

  /// Mean brightness step across the 8 × 8 block borders, divided by the
  /// mean step between other neighbours: about 1 for a clean picture, more
  /// when the compression blocks show.
  static double blockiness(GameBoxPixels px) {
    final w = px.width, h = px.height, rgba = px.rgba;
    if (w < 24 || h < 24) return 1;
    var border = 0.0, inner = 0.0;
    var nb = 0, ni = 0;
    for (var y = 0; y < h; y++) {
      final row = y * w;
      for (var x = 1; x < w; x++) {
        final d = (_luma(rgba, (row + x) * 4) - _luma(rgba, (row + x - 1) * 4)).abs();
        if (x % 8 == 0) {
          border += d;
          nb++;
        } else {
          inner += d;
          ni++;
        }
      }
    }
    for (var y = 1; y < h; y++) {
      for (var x = 0; x < w; x++) {
        final d = (_luma(rgba, (y * w + x) * 4) - _luma(rgba, ((y - 1) * w + x) * 4)).abs();
        if (y % 8 == 0) {
          border += d;
          nb++;
        } else {
          inner += d;
          ni++;
        }
      }
    }
    if (nb == 0 || ni == 0) return 1;
    final meanInner = inner / ni;
    return (border / nb) / math.max(0.5, meanInner);
  }

  /// Deblocking on every 8 × 8 border, as video codecs do it: where the
  /// step across the border is smaller than [alpha] and both sides are flat
  /// (variations under [beta]), the three pixels on each side are smoothed
  /// together (strong filter); where only the nearest neighbours are flat,
  /// the two border pixels move toward each other by at most [limit] (weak
  /// filter). Edges of the print are larger steps and stay.
  static GameBoxPixels deblock(GameBoxPixels src, {int alpha = 26, int beta = 8, int limit = 6}) {
    final w = src.width, h = src.height;
    final out = Uint8List.fromList(src.rgba);
    // [i] are byte offsets of p3 p2 p1 p0 | q0 q1 q2 q3.
    void filter(List<int> i) {
      final l = [for (final k in i) _luma(out, k)];
      final p0 = l[3], q0 = l[4], p1 = l[2], q1 = l[5], p2 = l[1], q2 = l[6];
      if ((p0 - q0).abs() >= alpha || (p1 - p0).abs() >= beta || (q1 - q0).abs() >= beta) return;
      final strong = (p2 - p0).abs() < beta && (q2 - q0).abs() < beta && (p0 - q0).abs() < (alpha >> 2) + 2;
      for (var c = 0; c < 4; c++) {
        final v = [for (final k in i) out[k + c]];
        if (strong) {
          final np0 = (v[1] + 2 * v[2] + 2 * v[3] + 2 * v[4] + v[5] + 4) >> 3;
          final np1 = (v[1] + v[2] + v[3] + v[4] + 2) >> 2;
          final np2 = (2 * v[0] + 3 * v[1] + v[2] + v[3] + v[4] + 4) >> 3;
          final nq0 = (v[6] + 2 * v[5] + 2 * v[4] + 2 * v[3] + v[2] + 4) >> 3;
          final nq1 = (v[6] + v[5] + v[4] + v[3] + 2) >> 2;
          final nq2 = (2 * v[7] + 3 * v[6] + v[5] + v[4] + v[3] + 4) >> 3;
          out[i[1] + c] = np2;
          out[i[2] + c] = np1;
          out[i[3] + c] = np0;
          out[i[4] + c] = nq0;
          out[i[5] + c] = nq1;
          out[i[6] + c] = nq2;
        } else {
          final delta = ((4 * (v[4] - v[3]) + (v[2] - v[5]) + 4) >> 3).clamp(-limit, limit);
          out[i[3] + c] = (v[3] + delta).clamp(0, 255);
          out[i[4] + c] = (v[4] - delta).clamp(0, 255);
        }
      }
      // Premultiplied colour never above its alpha.
      for (final k in i) {
        final a = out[k + 3];
        for (var c = 0; c < 3; c++) {
          if (out[k + c] > a) out[k + c] = a;
        }
      }
    }

    for (var y = 0; y < h; y++) {
      for (var x = 8; x + 3 < w; x += 8) {
        final i = (y * w + x) * 4;
        filter([i - 16, i - 12, i - 8, i - 4, i, i + 4, i + 8, i + 12]);
      }
    }
    final row = w * 4;
    for (var y = 8; y + 3 < h; y += 8) {
      for (var x = 0; x < w; x++) {
        final i = (y * w + x) * 4;
        filter([i - 4 * row, i - 3 * row, i - 2 * row, i - row, i, i + row, i + 2 * row, i + 3 * row]);
      }
    }
    return GameBoxPixels(w, h, out);
  }

  /// Colour of a compressed picture smoothed where the brightness is even:
  /// JPEG stores colour at half resolution in 16 × 16 blocks, which show as
  /// patches in dark, flat areas. Each pixel takes the colour (Cb, Cr) of
  /// its 7 × 7 neighbours of similar brightness; its brightness, which
  /// carries the print, is kept as it is.
  static GameBoxPixels smoothChroma(GameBoxPixels src, {double spatialSigma = 2.5, double lumaSigma = 10}) {
    final w = src.width, h = src.height, rgba = src.rgba;
    final n = w * h;
    final y = Float32List(n), cb = Float32List(n), cr = Float32List(n);
    for (var i = 0, j = 0; i < n; i++, j += 4) {
      final r = rgba[j].toDouble(), g = rgba[j + 1].toDouble(), b = rgba[j + 2].toDouble();
      y[i] = 0.299 * r + 0.587 * g + 0.114 * b;
      cb[i] = -0.168736 * r - 0.331264 * g + 0.5 * b;
      cr[i] = 0.5 * r - 0.418688 * g - 0.081312 * b;
    }
    const radius = 3;
    final spatial = Float64List((2 * radius + 1) * (2 * radius + 1));
    for (var dy = -radius; dy <= radius; dy++) {
      for (var dx = -radius; dx <= radius; dx++) {
        spatial[(dy + radius) * (2 * radius + 1) + dx + radius] =
            math.exp(-(dx * dx + dy * dy) / (2 * spatialSigma * spatialSigma));
      }
    }
    final lut = Float64List(256);
    for (var d = 0; d < 256; d++) {
      lut[d] = math.exp(-(d * d) / (2 * lumaSigma * lumaSigma));
    }
    final out = Uint8List.fromList(rgba);
    for (var py = 0; py < h; py++) {
      for (var px = 0; px < w; px++) {
        final i = py * w + px;
        final y0 = y[i];
        var sb = 0.0, sr = 0.0, ws = 0.0;
        for (var dy = -radius; dy <= radius; dy++) {
          final yy = (py + dy).clamp(0, h - 1);
          for (var dx = -radius; dx <= radius; dx++) {
            final j = yy * w + (px + dx).clamp(0, w - 1);
            final wt = spatial[(dy + radius) * (2 * radius + 1) + dx + radius] *
                lut[(y[j] - y0).abs().round().clamp(0, 255)];
            sb += cb[j] * wt;
            sr += cr[j] * wt;
            ws += wt;
          }
        }
        final b2 = sb / ws, r2 = sr / ws;
        final o = i * 4;
        final a = rgba[o + 3];
        out[o] = math.min(_byte(y0 + 1.402 * r2), a);
        out[o + 1] = math.min(_byte(y0 - 0.344136 * b2 - 0.714136 * r2), a);
        out[o + 2] = math.min(_byte(y0 + 1.772 * b2), a);
      }
    }
    return GameBoxPixels(w, h, out);
  }

  // Directional cubic convolution ×2 -----------------------------------------

  /// Edge test of DCCI: one direction is an edge when its variation is this
  /// many times smaller than the other's.
  static const double edgeRatio = 1.15;

  /// Exponent of the weights in smooth areas.
  static const int smoothExponent = 5;

  /// Left ends (dx, dy) of the pairs of known pixels compared along a row
  /// in the second pass (the column pairs are the same, transposed).
  static const List<(int, int)> _rowPairs = [
    (-3, -2), (-1, -2), (1, -2),
    (-3, 0), (-1, 0), (1, 0),
    (-3, 2), (-1, 2), (1, 2),
    (-2, -1), (0, -1),
    (-2, 1), (0, 1),
  ];

  /// [src] enlarged ×2 by directional cubic convolution. Pixel (2x, 2y) of
  /// the result is pixel (x, y) of [src]; the others are interpolated along
  /// the local edge.
  static GameBoxPixels double2x(GameBoxPixels src) {
    final w = src.width, h = src.height;
    final ow = w * 2, oh = h * 2;
    // Channels and brightness as doubles, on the enlarged grid; unknown
    // pixels are filled in two passes.
    final out = Float64List(ow * oh * 4);
    final luma = Float64List(ow * oh);
    final rgba = src.rgba;
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        final si = (y * w + x) * 4;
        final o = (2 * y) * ow + 2 * x;
        for (var c = 0; c < 4; c++) {
          out[o * 4 + c] = rgba[si + c].toDouble();
        }
        luma[o] = 0.299 * rgba[si] + 0.587 * rgba[si + 1] + 0.114 * rgba[si + 2];
      }
    }

    // Known pixel of the enlarged grid, clamped to its known lattice.
    int at(int x, int y, int stepX, int stepY) {
      // Clamp onto known positions of the same parity.
      var cx = x, cy = y;
      while (cx < 0) {
        cx += stepX;
      }
      while (cy < 0) {
        cy += stepY;
      }
      while (cx >= ow) {
        cx -= stepX;
      }
      while (cy >= oh) {
        cy -= stepY;
      }
      return cy * ow + cx;
    }

    final tmp = Float64List(4);
    final p1 = Float64List(4);
    final p2 = Float64List(4);

    // Cubic convolution of four samples along one direction (-1, 9, 9, -1) / 16.
    void cubic(Float64List dst, int a, int b, int c, int d) {
      for (var k = 0; k < 4; k++) {
        dst[k] = (-out[a * 4 + k] + 9 * out[b * 4 + k] + 9 * out[c * 4 + k] - out[d * 4 + k]) / 16;
      }
    }

    void write(int o, Float64List v) {
      for (var k = 0; k < 4; k++) {
        out[o * 4 + k] = v[k];
      }
      luma[o] = 0.299 * v[0] + 0.587 * v[1] + 0.114 * v[2];
    }

    void blend(int o, double g1, double g2) {
      // p1 runs along direction 1, p2 along direction 2; g1 and g2 are the
      // variations along them.
      if ((1 + g1) / (1 + g2) > edgeRatio) {
        write(o, p2);
      } else if ((1 + g2) / (1 + g1) > edgeRatio) {
        write(o, p1);
      } else {
        final w1 = 1 / (1 + math.pow(g1, smoothExponent));
        final w2 = 1 / (1 + math.pow(g2, smoothExponent));
        for (var k = 0; k < 4; k++) {
          tmp[k] = (w1 * p1[k] + w2 * p2[k]) / (w1 + w2);
        }
        write(o, tmp);
      }
    }

    // Pass 1: centres of four known pixels (odd, odd). Direction 1 runs up
    // to the right (45°), direction 2 down to the right (135°).
    for (var y = 1; y < oh; y += 2) {
      for (var x = 1; x < ow; x += 2) {
        var g1 = 0.0, g2 = 0.0;
        // Variations in the 4 × 4 window of known pixels around the centre.
        for (var j = -3; j <= 1; j += 2) {
          for (var i = -1; i <= 3; i += 2) {
            g1 += (luma[at(x + i, y + j, 2, 2)] - luma[at(x + i - 2, y + j + 2, 2, 2)]).abs();
          }
          for (var i = -3; i <= 1; i += 2) {
            g2 += (luma[at(x + i, y + j, 2, 2)] - luma[at(x + i + 2, y + j + 2, 2, 2)]).abs();
          }
        }
        cubic(p1, at(x - 3, y + 3, 2, 2), at(x - 1, y + 1, 2, 2), at(x + 1, y - 1, 2, 2), at(x + 3, y - 3, 2, 2));
        cubic(p2, at(x - 3, y - 3, 2, 2), at(x - 1, y - 1, 2, 2), at(x + 1, y + 1, 2, 2), at(x + 3, y + 3, 2, 2));
        blend(y * ow + x, g1, g2);
      }
    }

    // Known after pass 1: (even, even) and (odd, odd). Clamp onto them.
    int known(int x, int y) {
      var cx = x.clamp(0, ow - 1), cy = y.clamp(0, oh - 1);
      if ((cx + cy).isOdd) {
        // Step back inside on the axis that left the grid.
        if (x != cx) {
          cx += cx == 0 ? 1 : -1;
        } else {
          cy += cy == 0 ? 1 : -1;
        }
      }
      return cy * ow + cx;
    }

    // Pass 2: the rest (even, odd) and (odd, even). Direction 1 horizontal,
    // direction 2 vertical.
    for (var y = 0; y < oh; y++) {
      for (var x = (y.isEven ? 1 : 0); x < ow; x += 2) {
        // Variations between known neighbours two pixels apart, in the
        // diamond around (x, y): along the rows (g1) and the columns (g2).
        var g1 = 0.0, g2 = 0.0;
        for (final (i, j) in _rowPairs) {
          g1 += (luma[known(x + i, y + j)] - luma[known(x + i + 2, y + j)]).abs();
          g2 += (luma[known(x + j, y + i)] - luma[known(x + j, y + i + 2)]).abs();
        }
        cubic(p1, known(x - 3, y), known(x - 1, y), known(x + 1, y), known(x + 3, y));
        cubic(p2, known(x, y - 3), known(x, y - 1), known(x, y + 1), known(x, y + 3));
        blend(y * ow + x, g1, g2);
      }
    }

    final result = Uint8List(ow * oh * 4);
    for (var i = 0; i < ow * oh; i++) {
      final a = out[i * 4 + 3];
      final oa = a <= 0 ? 0 : (a >= 255 ? 255 : (a + 0.5).toInt());
      result[i * 4 + 3] = oa;
      for (var c = 0; c < 3; c++) {
        final v = out[i * 4 + c];
        final b = v <= 0 ? 0 : (v >= 255 ? 255 : (v + 0.5).toInt());
        result[i * 4 + c] = b > oa ? oa : b;
      }
    }
    return GameBoxPixels(ow, oh, result);
  }
}
