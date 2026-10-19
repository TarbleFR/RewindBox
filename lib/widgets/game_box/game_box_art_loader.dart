import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';

import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';

/// Image providers of a box, at a browsing size or an inspection size.
///
/// Browsing uses the decode width the carousel already uses for its box art
/// (1024 px), so the 3D card shares its decoded front with the flat card.
/// Inspection asks for a larger decode of the faces read closely (front and
/// back, up to 2400 px wide) once the viewer is open, and [evictDetailed]
/// releases them when it closes or before a game starts.
class GameBoxArtSet {
  GameBoxArtSet({required this.media, required this.title});

  final GameBoxLocalMedia media;
  final String title;

  static const int browseWidth = 1024;
  static const int detailWidth = 2400;
  static const int spineBrowseHeight = 900;
  static const int spineDetailHeight = 2000;

  final Set<ImageProvider> _detailed = {};

  static ImageProvider _fileProvider(String path, {int? width, int? height}) =>
      ResizeImage.resizeIfNeeded(width, height, FileImage(File(path)));

  ImageProvider? _face(String? path, {required bool detailed}) {
    if (path == null) return null;
    if (!detailed) return _fileProvider(path, width: browseWidth);
    final p = _fileProvider(path, width: detailWidth);
    _detailed.add(p);
    return p;
  }

  ImageProvider? _spine(String? path, {required bool detailed, required bool landscape}) {
    if (path == null) return null;
    final size = detailed ? spineDetailHeight : spineBrowseHeight;
    // A spine stored lying down is limited by its width instead.
    final p = landscape ? _fileProvider(path, width: size) : _fileProvider(path, height: size);
    if (detailed) _detailed.add(p);
    return p;
  }

  /// The art of the box. [backPath] replaces the default back by a scan of
  /// another edition (reading language).
  GameBoxArt art({
    required bool detailed,
    String? backPath,
    Color? edgeColor,
    Widget? frontFallback,
    String backUnavailable = '',
    bool gloss = true,
  }) {
    final back = backPath ?? media.back;
    final spineSize = media.spine == null ? null : GameBoxImageSize.of(media.spine!);
    final landscape = spineSize != null && spineSize.width > spineSize.height;
    final backSize = back == null ? null : GameBoxImageSize.of(back);
    return GameBoxArt(
      title: title,
      front: _face(media.front, detailed: detailed),
      back: _face(back, detailed: detailed),
      spine: _spine(media.spine, detailed: detailed, landscape: landscape),
      support: media.support == null
          ? null
          : _fileProvider(media.support!, width: detailed ? 1400 : 700),
      spineLandscape: landscape,
      backAspect: backSize == null || backSize.height == 0 ? null : backSize.width / backSize.height,
      edgeColor: edgeColor,
      frontFallback: frontFallback,
      backUnavailable: backUnavailable,
      gloss: gloss,
    );
  }

  /// Width / height of the front scan, for the box proportions.
  double? get frontAspect {
    final f = media.front;
    if (f == null) return null;
    final size = GameBoxImageSize.of(f);
    if (size == null || size.height == 0) return null;
    return size.width / size.height;
  }

  /// Releases the large decodes made for inspection.
  void evictDetailed() {
    for (final p in _detailed) {
      p.evict();
    }
    _detailed.clear();
  }

  static final Map<String, Color?> _edgeCache = {};

  /// Average colour of the border of a front scan (cardboard edges), decoded
  /// at 24 px wide; null when the image cannot be read.
  static Future<Color?> edgeColor(String? path) async {
    if (path == null) return null;
    if (_edgeCache.containsKey(path)) return _edgeCache[path];
    Color? result;
    try {
      final bytes = await File(path).readAsBytes();
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      final codec = await ui.instantiateImageCodecFromBuffer(buffer, targetWidth: 24);
      final frame = await codec.getNextFrame();
      final image = frame.image;
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (data != null) result = _borderAverage(data.buffer.asUint8List(), image.width, image.height);
      image.dispose();
      codec.dispose();
    } catch (_) {
      result = null;
    }
    _edgeCache[path] = result;
    return result;
  }

  static Color? _borderAverage(Uint8List rgba, int w, int h) {
    if (w < 2 || h < 2) return null;
    var r = 0, g = 0, b = 0, n = 0;
    void add(int x, int y) {
      final i = (y * w + x) * 4;
      if (rgba[i + 3] < 128) return;
      r += rgba[i];
      g += rgba[i + 1];
      b += rgba[i + 2];
      n++;
    }
    for (var x = 0; x < w; x++) {
      add(x, 0);
      add(x, h - 1);
    }
    for (var y = 1; y < h - 1; y++) {
      add(0, y);
      add(w - 1, y);
    }
    if (n == 0) return null;
    return Color.fromARGB(255, r ~/ n, g ~/ n, b ~/ n);
  }
}
