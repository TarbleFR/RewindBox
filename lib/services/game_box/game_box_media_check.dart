import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';

/// Why a picture cannot be a face of the box (docs/game-box-3d.md § 15).
enum GameBoxImageVerdict {
  ok,

  /// One flat colour (the filmed Super Mario 3D World back was #00FF00
  /// edge to edge): a placeholder, never a scan.
  uniform,

  /// Almost entirely transparent.
  transparent,

  /// Too small to be read as a scan.
  tiny,

  /// Not decodable.
  unreadable,
}

/// What a quick decode of a picture shows.
class GameBoxImageStats {
  const GameBoxImageStats({
    required this.width,
    required this.height,
    required this.opaqueShare,
    required this.dominantShare,
    required this.lumaDeviation,
    required this.dominant,
  });

  /// Size of the analysed decode (not of the file).
  final int width;
  final int height;

  /// Share of pixels at least half opaque.
  final double opaqueShare;

  /// Share of opaque pixels within a few levels of the most frequent colour.
  final double dominantShare;

  /// Standard deviation of the brightness of opaque pixels (0..255).
  final double lumaDeviation;

  /// Most frequent colour, 0xRRGGBB.
  final int dominant;

  GameBoxImageVerdict get verdict {
    if (opaqueShare < 0.05) return GameBoxImageVerdict.transparent;
    if (dominantShare >= 0.985 && lumaDeviation < 3.0) return GameBoxImageVerdict.uniform;
    return GameBoxImageVerdict.ok;
  }

  @override
  String toString() => 'GameBoxImageStats(${width}x$height, opaque ${opaqueShare.toStringAsFixed(3)}, '
      'dominant ${dominantShare.toStringAsFixed(3)} #${dominant.toRadixString(16).padLeft(6, '0')}, '
      'luma σ ${lumaDeviation.toStringAsFixed(2)})';
}

/// Result of a check, with the stats it is based on.
class GameBoxImageCheck {
  const GameBoxImageCheck(this.verdict, {this.stats});
  final GameBoxImageVerdict verdict;
  final GameBoxImageStats? stats;

  bool get ok => verdict == GameBoxImageVerdict.ok;

  /// Share of opaque pixels (a render or a logo has a transparent
  /// background), when the picture could be decoded.
  double? get opaqueShare => stats?.opaqueShare;

  static const GameBoxImageCheck unreadable = GameBoxImageCheck(GameBoxImageVerdict.unreadable);
}

/// Checks pictures before they are adopted as faces and before they are
/// drawn (docs/game-box-3d.md § 15).
///
/// The decode is small (at most [sampleWidth] pixels wide) and the result is
/// kept per file length and modification time, so a replaced file is checked
/// again and an unchanged one never twice.
class GameBoxMediaChecker {
  GameBoxMediaChecker._();

  /// Width of the analysed decode.
  static const int sampleWidth = 64;

  /// Smallest accepted scan side, in pixels of the file.
  static const int minSide = 48;

  static final Map<String, (int, int, GameBoxImageCheck)> _cache = {};

  /// Result already known for [path] at its current length and date, if any
  /// (synchronous, for widgets that cannot wait).
  static GameBoxImageCheck? cached(String path) {
    final hook = debugCheck?.call(path);
    if (hook != null) return hook;
    final hit = _cache[path];
    if (hit == null) return null;
    try {
      final stat = File(path).statSync();
      if (stat.size == hit.$1 && stat.modified.microsecondsSinceEpoch == hit.$2) return hit.$3;
    } catch (_) {}
    return null;
  }

  static void evict(String path) => _cache.remove(path);

  @visibleForTesting
  static void clearCache() => _cache.clear();

  /// Test hook: the check of a file, for fixtures that are only image
  /// headers (their size matters, not their pixels).
  @visibleForTesting
  static GameBoxImageCheck? Function(String path)? debugCheck;

  /// Checks the picture file at [path].
  static Future<GameBoxImageCheck> checkFile(String path) async {
    final hook = debugCheck?.call(path);
    if (hook != null) return hook;
    final known = cached(path);
    if (known != null) return known;
    GameBoxImageCheck result;
    int length = 0, modified = 0;
    try {
      final file = File(path);
      final stat = await file.stat();
      length = stat.size;
      modified = stat.modified.microsecondsSinceEpoch;
      result = await checkBytes(await file.readAsBytes());
    } catch (_) {
      result = GameBoxImageCheck.unreadable;
    }
    _cache[path] = (length, modified, result);
    return result;
  }

  /// Checks a downloaded picture before it is written anywhere.
  static Future<GameBoxImageCheck> checkBytes(Uint8List bytes) async {
    ui.Codec? codec;
    ui.Image? image;
    try {
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      final descriptor = await ui.ImageDescriptor.encoded(buffer);
      final w = descriptor.width, h = descriptor.height;
      if (w < minSide || h < minSide) {
        descriptor.dispose();
        buffer.dispose();
        return const GameBoxImageCheck(GameBoxImageVerdict.tiny);
      }
      codec = await descriptor.instantiateCodec(targetWidth: w > sampleWidth ? sampleWidth : null);
      final frame = await codec.getNextFrame();
      image = frame.image;
      final data = await image.toByteData(format: ui.ImageByteFormat.rawStraightRgba);
      if (data == null) return GameBoxImageCheck.unreadable;
      final stats = analyzeRgba(data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes), image.width, image.height);
      return GameBoxImageCheck(stats.verdict, stats: stats);
    } catch (_) {
      return GameBoxImageCheck.unreadable;
    } finally {
      image?.dispose();
      codec?.dispose();
    }
  }

  /// Statistics of straight (not premultiplied) RGBA pixels.
  static GameBoxImageStats analyzeRgba(Uint8List rgba, int width, int height) {
    final n = width * height;
    var opaque = 0;
    final buckets = <int, int>{};
    var sum = 0.0, sumSq = 0.0;
    for (var i = 0; i < n; i++) {
      final o = i * 4;
      if (o + 3 >= rgba.length) break;
      if (rgba[o + 3] < 128) continue;
      opaque++;
      final r = rgba[o], g = rgba[o + 1], b = rgba[o + 2];
      // Colours within a few levels share a bucket (JPEG noise of a flat
      // placeholder stays in one).
      final key = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3);
      buckets[key] = (buckets[key] ?? 0) + 1;
      final y = 0.2126 * r + 0.7152 * g + 0.0722 * b;
      sum += y;
      sumSq += y * y;
    }
    var dominantKey = 0, dominantCount = 0;
    buckets.forEach((k, v) {
      if (v > dominantCount) {
        dominantCount = v;
        dominantKey = k;
      }
    });
    final mean = opaque == 0 ? 0.0 : sum / opaque;
    final variance = opaque == 0 ? 0.0 : (sumSq / opaque - mean * mean).clamp(0.0, double.infinity);
    final dr = ((dominantKey >> 10) & 31) << 3 | 4;
    final dg = ((dominantKey >> 5) & 31) << 3 | 4;
    final db = (dominantKey & 31) << 3 | 4;
    return GameBoxImageStats(
      width: width,
      height: height,
      opaqueShare: n == 0 ? 0 : opaque / n,
      dominantShare: opaque == 0 ? 0 : dominantCount / opaque,
      lumaDeviation: math.sqrt(variance.toDouble()),
      dominant: (dr << 16) | (dg << 8) | db,
    );
  }
}
