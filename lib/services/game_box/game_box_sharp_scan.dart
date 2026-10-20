import 'dart:async';
import 'dart:io';
import 'dart:isolate';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:flutter/scheduler.dart';

import 'package:neostation/services/game_box/game_box_media.dart';

/// Pixels of an image: RGBA, 8 bits per channel, premultiplied alpha.
class GameBoxPixels {
  const GameBoxPixels(this.width, this.height, this.rgba);
  final int width;
  final int height;
  final Uint8List rgba;
}

/// A box scan made for the exact size it is shown at (docs/game-box-3d.md
/// § 12).
///
/// The GPU draws a large decode smaller than it is by mixing two of its
/// halved copies (trilinear filtering), which softens small print. Here the
/// scan is brought once to the pixel width it covers on the screen with a
/// Mitchell-Netravali bicubic filter (B = C = 1/3: as crisp as text drawn at
/// that size, without the ringing of Lanczos or Catmull-Rom), so that it is
/// then drawn pixel for pixel. With `sharpen`, a light unsharp mask is added
/// on the brightness only: no colour fringes, and differences below a small
/// threshold (the grain and JPEG noise of the scan) are left alone. Nothing
/// is added to the scan and it is never enlarged: shown larger than it is,
/// it is used at its own size.
class GameBoxSharpScan {
  GameBoxSharpScan._();

  /// Widest decode of a scan (as the full decode of the flat view).
  static const int maxWidth = 4096;

  /// Target widths are rounded up to this step, so that small gestures
  /// reuse a render.
  static const int widthStep = 64;

  static const double sharpenAmount = 0.3;
  static const double sharpenSigma = 0.9;

  /// Brightness differences below this (0..255) are not sharpened.
  static const int sharpenThreshold = 3;

  /// Above this many pixels the scan is resampled but not sharpened (memory).
  static const int maxSharpenPixels = 12 * 1024 * 1024;

  /// Width of the render of a scan [scanWidth] px wide that fills
  /// [displayWidth] physical pixels: rounded up to [widthStep], never more
  /// than the scan (nor [maxWidth]).
  static int targetWidth(double scanWidth, double displayWidth) {
    final native = math.min(scanWidth.round(), maxWidth);
    if (native <= 0) return 0;
    final wanted = ((displayWidth / widthStep).ceil() * widthStep).clamp(widthStep, maxWidth);
    return math.min(wanted, native);
  }

  /// Whether a render [current] px wide can stay for a target [wanted] px wide.
  static bool closeEnough(int current, int wanted) =>
      current > 0 && (current - wanted).abs() <= math.max(widthStep, wanted * 0.12);

  @visibleForTesting
  static Future<GameBoxPixels> Function(String path, int width, bool sharpen)? debugProcessor;

  /// Renders the scan at [path] [width] px wide (see [targetWidth]), or null
  /// when it cannot be read.
  static Future<ui.Image?> render(String path, {required int width, required bool sharpen}) async {
    final size = GameBoxImageSize.of(path);
    if (size == null || size.width <= 0 || size.height <= 0) return null;
    final native = math.min(size.width.round(), maxWidth);
    final target = width.clamp(1, native);
    try {
      final processor = debugProcessor;
      if (processor != null) {
        final px = await processor(path, target, sharpen);
        return await _toImage(px.rgba, px.width, px.height);
      }
      final bytes = await File(path).readAsBytes();
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      final codec = await ui.instantiateImageCodecFromBuffer(
        buffer,
        targetWidth: native < size.width.round() ? native : null,
      );
      final frame = await codec.getNextFrame();
      codec.dispose();
      final source = frame.image;
      final sw = source.width, sh = source.height;
      final th = math.max(1, (sh * target / sw).round());
      final shouldSharpen = sharpen && target * th <= maxSharpenPixels;
      if (target >= sw && !shouldSharpen) return source;
      final data = await source.toByteData(format: ui.ImageByteFormat.rawRgba);
      source.dispose();
      if (data == null) return null;
      final input = TransferableTypedData.fromList([data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes)]);
      final output = await Isolate.run(() {
        var px = GameBoxPixels(sw, sh, input.materialize().asUint8List());
        px = resample(px, math.min(target, sw), th);
        if (shouldSharpen) px = sharpenLuma(px);
        return TransferableTypedData.fromList([px.rgba]);
      });
      return await _toImage(output.materialize().asUint8List(), math.min(target, sw), th);
    } catch (_) {
      return null;
    }
  }

  static Future<ui.Image> _toImage(Uint8List rgba, int w, int h) {
    final completer = Completer<ui.Image>();
    ui.decodeImageFromPixels(rgba, w, h, ui.PixelFormat.rgba8888, completer.complete);
    return completer.future;
  }

  // Mitchell-Netravali bicubic ------------------------------------------------

  static const double _b = 1 / 3, _c = 1 / 3;

  /// The Mitchell-Netravali kernel (B = C = 1/3), support 2.
  static double mitchell(double x) {
    final a = x.abs();
    if (a < 1) {
      return ((12 - 9 * _b - 6 * _c) * a * a * a + (-18 + 12 * _b + 6 * _c) * a * a + (6 - 2 * _b)) / 6;
    }
    if (a < 2) {
      return ((-_b - 6 * _c) * a * a * a + (6 * _b + 30 * _c) * a * a + (-12 * _b - 48 * _c) * a + (8 * _b + 24 * _c)) / 6;
    }
    return 0;
  }

  /// Contributors of each output sample: first input index, tap count and
  /// normalised weights (row-major, [taps] per output).
  static (Int32List, Int32List, Float64List, int) _weights(int inLen, int outLen) {
    final scale = inLen / outLen;
    final filterScale = math.max(scale, 1.0);
    final support = 2.0 * filterScale;
    final taps = (support * 2).ceil() + 2;
    final starts = Int32List(outLen);
    final counts = Int32List(outLen);
    final weights = Float64List(outLen * taps);
    for (var o = 0; o < outLen; o++) {
      final center = (o + 0.5) * scale;
      final left = math.max(0, (center - support).floor());
      final right = math.min(inLen - 1, (center + support).ceil());
      var sum = 0.0;
      var n = 0;
      for (var i = left; i <= right && n < taps; i++) {
        final w = mitchell((i + 0.5 - center) / filterScale);
        weights[o * taps + n] = w;
        sum += w;
        n++;
      }
      if (sum != 0) {
        for (var k = 0; k < n; k++) {
          weights[o * taps + k] /= sum;
        }
      }
      starts[o] = left;
      counts[o] = n;
    }
    return (starts, counts, weights, taps);
  }

  static int _clamp8(double v) => v <= 0 ? 0 : (v >= 255 ? 255 : (v + 0.5).toInt());

  /// One pass along x (rows) or y (columns), written to a new image.
  static Uint8List _pass(Uint8List src, int w, int h, int outLen, {required bool horizontal}) {
    final inLen = horizontal ? w : h;
    final (starts, counts, weights, taps) = _weights(inLen, outLen);
    final ow = horizontal ? outLen : w;
    final oh = horizontal ? h : outLen;
    final out = Uint8List(ow * oh * 4);
    // Distance between two samples along the pass, in bytes.
    final step = horizontal ? 4 : w * 4;
    for (var line = 0; line < (horizontal ? h : w); line++) {
      final lineBase = horizontal ? line * w * 4 : line * 4;
      for (var o = 0; o < outLen; o++) {
        var r = 0.0, g = 0.0, b = 0.0, a = 0.0;
        var idx = lineBase + starts[o] * step;
        final wBase = o * taps;
        final n = counts[o];
        for (var k = 0; k < n; k++) {
          final wt = weights[wBase + k];
          r += src[idx] * wt;
          g += src[idx + 1] * wt;
          b += src[idx + 2] * wt;
          a += src[idx + 3] * wt;
          idx += step;
        }
        final oa = _clamp8(a);
        final dst = horizontal ? (line * ow + o) * 4 : (o * ow + line) * 4;
        // Premultiplied: no colour above its alpha (ringing).
        out[dst] = math.min(_clamp8(r), oa);
        out[dst + 1] = math.min(_clamp8(g), oa);
        out[dst + 2] = math.min(_clamp8(b), oa);
        out[dst + 3] = oa;
      }
    }
    return out;
  }

  /// [src] resampled to [tw] × [th] with the separable Mitchell-Netravali filter.
  static GameBoxPixels resample(GameBoxPixels src, int tw, int th) {
    if (tw == src.width && th == src.height) return src;
    // The order that keeps the intermediate image the smaller.
    if (tw * src.height <= src.width * th) {
      final mid = _pass(src.rgba, src.width, src.height, tw, horizontal: true);
      return GameBoxPixels(tw, th, _pass(mid, tw, src.height, th, horizontal: false));
    }
    final mid = _pass(src.rgba, src.width, src.height, th, horizontal: false);
    return GameBoxPixels(tw, th, _pass(mid, src.width, th, tw, horizontal: true));
  }

  // Unsharp mask on the brightness ---------------------------------------------

  /// A light unsharp mask on the brightness: the same correction on the three
  /// channels (no colour fringes), skipped below [threshold].
  static GameBoxPixels sharpenLuma(
    GameBoxPixels src, {
    double amount = sharpenAmount,
    double sigma = sharpenSigma,
    int threshold = sharpenThreshold,
  }) {
    final w = src.width, h = src.height, rgba = src.rgba;
    final n = w * h;
    final luma = Uint8List(n);
    for (var i = 0, j = 0; i < n; i++, j += 4) {
      luma[i] = (77 * rgba[j] + 150 * rgba[j + 1] + 29 * rgba[j + 2] + 128) >> 8;
    }
    final radius = math.max(1, (sigma * 2).ceil());
    final kernel = Float64List(radius * 2 + 1);
    var total = 0.0;
    for (var k = -radius; k <= radius; k++) {
      final v = math.exp(-(k * k) / (2 * sigma * sigma));
      kernel[k + radius] = v;
      total += v;
    }
    for (var k = 0; k < kernel.length; k++) {
      kernel[k] /= total;
    }
    final tmp = Float32List(n);
    for (var y = 0; y < h; y++) {
      final row = y * w;
      for (var x = 0; x < w; x++) {
        var s = 0.0;
        for (var k = -radius; k <= radius; k++) {
          final xx = (x + k).clamp(0, w - 1);
          s += luma[row + xx] * kernel[k + radius];
        }
        tmp[row + x] = s;
      }
    }
    final out = Uint8List.fromList(rgba);
    for (var y = 0; y < h; y++) {
      for (var x = 0; x < w; x++) {
        var blur = 0.0;
        for (var k = -radius; k <= radius; k++) {
          final yy = (y + k).clamp(0, h - 1);
          blur += tmp[yy * w + x] * kernel[k + radius];
        }
        final i = y * w + x;
        final diff = luma[i] - blur;
        if (diff.abs() < threshold) continue;
        final j = i * 4;
        final alpha = rgba[j + 3];
        if (alpha == 0) continue;
        final delta = amount * diff * alpha / 255;
        out[j] = math.min(_clamp8(rgba[j] + delta), alpha);
        out[j + 1] = math.min(_clamp8(rgba[j + 1] + delta), alpha);
        out[j + 2] = math.min(_clamp8(rgba[j + 2] + delta), alpha);
      }
    }
    return GameBoxPixels(w, h, out);
  }
}

/// A rendered scan as an [ImageProvider], so that the box draws it like any
/// other face (crops of a jewel inlay included). [dispose] releases it.
class GameBoxRenderedScan extends ImageProvider<GameBoxRenderedScan> {
  GameBoxRenderedScan(this.image, {required this.path, required this.width, required this.sharpen});

  final ui.Image image;
  final String path;
  final int width;
  final bool sharpen;
  bool _disposed = false;

  @override
  Future<GameBoxRenderedScan> obtainKey(ImageConfiguration configuration) => SynchronousFuture(this);

  @override
  ImageStreamCompleter loadImage(GameBoxRenderedScan key, ImageDecoderCallback decode) =>
      OneFrameImageStreamCompleter(SynchronousFuture(ImageInfo(image: image.clone(), debugLabel: path)));

  void dispose() {
    if (_disposed) return;
    _disposed = true;
    evict();
    image.dispose();
  }
}

/// The render of one scan kept for a screen: asked again when the shown size
/// changes enough, replaced when ready, released by [clear]. Late results of
/// an earlier request are dropped.
class GameBoxSharpTexture {
  GameBoxSharpTexture({required this.onChanged});

  final VoidCallback onChanged;
  GameBoxRenderedScan? _current;
  (String, int, bool)? _pending;
  int _generation = 0;
  bool _disposed = false;

  GameBoxRenderedScan? get current => _current;

  /// The render of [path] when it was made for it with [sharpen].
  GameBoxRenderedScan? providerFor(String? path, {required bool sharpen}) {
    final c = _current;
    if (c == null || path == null || c.path != path || c.sharpen != sharpen) return null;
    return c;
  }

  /// Asks for [path] rendered to fill [displayWidth] physical pixels.
  void request(String path, double displayWidth, {required bool sharpen}) {
    if (_disposed || !displayWidth.isFinite || displayWidth <= 0) return;
    final size = GameBoxImageSize.of(path);
    if (size == null) return;
    final width = GameBoxSharpScan.targetWidth(size.width, displayWidth);
    if (width <= 0) return;
    final c = _current;
    if (c != null && c.path == path && c.sharpen == sharpen && GameBoxSharpScan.closeEnough(c.width, width)) return;
    final p = _pending;
    if (p != null && p.$1 == path && p.$3 == sharpen && GameBoxSharpScan.closeEnough(p.$2, width)) return;
    final generation = ++_generation;
    _pending = (path, width, sharpen);
    GameBoxSharpScan.render(path, width: width, sharpen: sharpen).then((image) {
      if (_disposed || generation != _generation) {
        image?.dispose();
        return;
      }
      _pending = null;
      if (image == null) return;
      final previous = _current;
      _current = GameBoxRenderedScan(image, path: path, width: width, sharpen: sharpen);
      onChanged();
      // The previous render stays until the frame that shows the new one.
      if (previous != null) {
        SchedulerBinding.instance.addPostFrameCallback((_) => previous.dispose());
      }
    });
  }

  /// Releases the render (closing the screen, before a game starts).
  void clear() {
    _generation++;
    _pending = null;
    _current?.dispose();
    _current = null;
  }

  void dispose() {
    clear();
    _disposed = true;
  }
}
