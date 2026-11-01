import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';

import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';

/// Image providers of a box, at a browsing size or an inspection size.
///
/// Browsing uses the decode width the carousel already uses for its box art
/// (1024 px), so the 3D card shares its decoded front with the flat card.
/// Inspection asks for a larger decode of the faces read closely (front and
/// back, at most [detailSide] px on their longest side) once the viewer is
/// open, and [evictDetailed] releases them when it closes or before a game
/// starts. Reading the back or zooming in uses a render made for the exact
/// size on screen instead (game_box_sharp_scan.dart).
class GameBoxArtSet {
  GameBoxArtSet({required this.media, required this.title});

  final GameBoxLocalMedia media;
  final String title;

  static const int browseWidth = 1024;

  /// Longest side of an inspection decode. A tall Switch scan (1166 × 1888)
  /// is decoded whole; a 4000 px scan is reduced to 2400 px on its height,
  /// not its width (about 23 MB instead of 60 MB per face).
  static const int detailSide = 2400;

  /// Kept for callers that size by width.
  static const int detailWidth = detailSide;
  static const int spineBrowseHeight = 900;
  static const int spineDetailHeight = 2000;

  final Set<ImageProvider> _detailed = {};

  /// Providers handed out per file, so that a replaced file's decodes are
  /// evicted exactly (see [evictPath]).
  static final Map<String, Set<ImageProvider>> _issued = {};

  static ImageProvider _fileProvider(String path, {int? width, int? height}) {
    final provider = ResizeImage.resizeIfNeeded(width, height, FileImage(File(path)));
    (_issued[path] ??= <ImageProvider>{}).add(provider);
    return provider;
  }

  /// A provider bounded by [side] on the longest side of the image.
  static ImageProvider _bounded(String path, int side) {
    final size = GameBoxImageSize.of(path);
    if (size == null) return _fileProvider(path, width: side);
    if (size.width >= size.height) return _fileProvider(path, width: side);
    final provider = ResizeImage(FileImage(File(path)), width: side, height: side, policy: ResizeImagePolicy.fit);
    (_issued[path] ??= <ImageProvider>{}).add(provider);
    return provider;
  }

  ImageProvider? _face(String? path, {required bool detailed, int width = browseWidth}) {
    if (path == null) return null;
    if (!detailed) return _fileProvider(path, width: width);
    final p = _bounded(path, detailSide);
    _detailed.add(p);
    return p;
  }

  ImageProvider? _spine(String? path, {required bool detailed, required bool landscape, int? browseSize}) {
    if (path == null) return null;
    final size = detailed ? spineDetailHeight : (browseSize ?? spineBrowseHeight);
    // A spine stored lying down is limited by its width instead.
    final p = landscape ? _fileProvider(path, width: size) : _fileProvider(path, height: size);
    if (detailed) _detailed.add(p);
    return p;
  }

  /// A face file is drawn only when its check (when done) found a picture.
  static bool _usable(String? path, Map<String, GameBoxImageCheck>? checks) {
    if (path == null) return false;
    final check = checks?[path] ?? GameBoxMediaChecker.cached(path);
    return check == null || check.ok;
  }

  /// The art of the box. [backPath] replaces the default back by a scan of
  /// another edition (reading language). [compactWidth] is the decode width
  /// of the small boxes of the grid and list (the size their flat cover
  /// already used): only the front and spine are decoded for them.
  ///
  /// With a [profile], each image is recognised (docs/game-box-3d.md § 13):
  /// a full cover sheet gives its windows to the missing faces, catalogue art
  /// is marked so that it is never drawn as a print, and a picture refused by
  /// its check ([checks]) is left out like a missing scan.
  GameBoxArt art({
    required bool detailed,
    String? backPath,
    Color? edgeColor,
    Widget? frontFallback,
    String backUnavailable = '',
    bool gloss = true,
    double glossStrength = 1,
    int? compactWidth,
    ui.Image? bookletCover,
    GameBoxProfile? profile,
    Map<String, GameBoxImageCheck>? checks,
    Color? frontBand,
    Color? backBand,
  }) {
    final compact = compactWidth != null && !detailed;
    final frontPath = _usable(media.front, checks) ? media.front : null;
    var back = compact ? null : (backPath ?? media.back);
    if (!_usable(back, checks)) back = null;
    var spinePath = _usable(media.spine, checks) ? media.spine : null;
    final fullPath = _usable(media.full, checks) ? media.full : null;

    var frontNature = GameBoxArtNature.scan;
    var frontWindow = GameBoxArtLayout.full;
    var backNature = GameBoxArtNature.scan;
    var backWindow = GameBoxArtLayout.full;
    var spineWindow = GameBoxArtLayout.full;
    String? backFile = back;
    String? frontFile = frontPath;
    final frontSize = frontFile == null ? null : GameBoxImageSize.of(frontFile);
    final wrap = profile == null ? null : GameBoxWrapLayout.forProfile(profile);

    if (profile != null && frontFile != null) {
      frontNature = GameBoxArtClassifier.classify(
        profile: profile,
        size: frontSize,
        provenance: _provenance(GameBoxMediaKind.front),
        opaqueShare: (checks?[frontFile] ?? GameBoxMediaChecker.cached(frontFile))?.opaqueShare,
      );
      if (frontNature == GameBoxArtNature.wrap) {
        final parts = frontSize == null ? null : wrap?.split(frontSize);
        if (parts == null) {
          frontNature = GameBoxArtNature.promo;
        } else {
          frontWindow = parts.front;
          if (backFile == null && !compact) {
            backFile = frontFile;
            backWindow = parts.back;
          }
          if (spinePath == null) {
            spinePath = frontFile;
            spineWindow = parts.spine;
          }
        }
      }
    }
    // A full cover sheet kept beside the faces fills those still missing.
    if (fullPath != null && wrap != null) {
      final size = GameBoxImageSize.of(fullPath);
      final parts = size == null ? null : wrap.split(size);
      if (parts != null) {
        if (spinePath == null) {
          spinePath = fullPath;
          spineWindow = parts.spine;
        }
        if (backFile == null && !compact) {
          backFile = fullPath;
          backWindow = parts.back;
        }
      }
    }
    if (profile != null && backFile != null && backWindow == GameBoxArtLayout.full) {
      final size = GameBoxImageSize.of(backFile);
      backNature = GameBoxArtClassifier.classify(
        profile: profile,
        size: size,
        provenance: backFile == media.back ? _provenance(GameBoxMediaKind.back) : null,
        opaqueShare: (checks?[backFile] ?? GameBoxMediaChecker.cached(backFile))?.opaqueShare,
        front: false,
      );
      if (backNature == GameBoxArtNature.wrap) {
        final parts = size == null ? null : wrap?.split(size);
        if (parts == null) {
          backNature = GameBoxArtNature.promo;
        } else {
          backWindow = parts.back;
          backNature = GameBoxArtNature.scan;
        }
      }
    }

    final spineSize = spinePath == null ? null : GameBoxImageSize.of(spinePath);
    final landscape = spineWindow == GameBoxArtLayout.full && spineSize != null && spineSize.width > spineSize.height;
    final backSize = backFile == null ? null : GameBoxImageSize.of(backFile);
    return GameBoxArt(
      title: title,
      front: _face(frontFile, detailed: detailed, width: compact ? compactWidth : browseWidth),
      back: _face(backFile, detailed: detailed),
      spine: spineWindow == GameBoxArtLayout.full
          ? _spine(spinePath, detailed: detailed, landscape: landscape, browseSize: compact ? compactWidth : null)
          : _face(spinePath, detailed: detailed, width: compact ? compactWidth : browseWidth),
      support: media.support == null || compact || !_usable(media.support, checks)
          ? null
          : _fileProvider(media.support!, width: detailed ? 1400 : 700),
      spineLandscape: landscape,
      backAspect: backSize == null || backSize.height == 0 ? null : backSize.width / backSize.height,
      edgeColor: edgeColor,
      frontFallback: frontFallback,
      backUnavailable: backUnavailable,
      gloss: gloss && !compact,
      glossStrength: glossStrength,
      bookletCover: bookletCover,
      compact: compact,
      frontAspect: frontSize == null || frontSize.height == 0 ? null : frontSize.width / frontSize.height,
      frontNature: frontNature,
      frontWindow: frontWindow,
      backNature: backNature,
      backWindow: backWindow,
      spineWindow: spineWindow,
      frontBand: frontBand,
      backBand: backBand,
    );
  }

  final Map<GameBoxMediaKind, String?> _provenances = {};

  /// Provenance type of the file of [kind], when the manifest recorded it
  /// for that very file (read once per art set).
  String? _provenance(GameBoxMediaKind kind) =>
      _provenances.putIfAbsent(kind, () => media.recordOf(kind)?.type);

  /// Width / height of the front scan.
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

  /// Forgets every decode, size, colour and check of the file at [path]
  /// (a face replaced at the same path), without touching other images.
  static void evictPath(String path) {
    for (final p in _issued.remove(path) ?? const <ImageProvider>{}) {
      p.evict();
    }
    FileImage(File(path)).evict();
    GameBoxImageSize.evict(path);
    GameBoxMediaChecker.evict(path);
    _edgeCache.remove(path);
    _bandCache.remove(path);
  }

  static final Map<String, Color?> _edgeCache = {};

  /// Average colour of the border of a front scan (cardboard edges), decoded
  /// at 24 px wide; null when the image cannot be read.
  static Future<Color?> edgeColor(String? path) async {
    if (path == null) return null;
    if (_edgeCache.containsKey(path)) return _edgeCache[path];
    Color? result;
    try {
      final rgba = await _small(path);
      if (rgba != null) result = _borderAverage(rgba.$1, rgba.$2, rgba.$3);
    } catch (_) {
      result = null;
    }
    _edgeCache[path] = result;
    return result;
  }

  static final Map<String, Color?> _bandCache = {};

  /// Colour for the neutral bands around a print whose proportions differ
  /// from its printed area: the average of the picture's outermost pixels,
  /// darkened a little so that the band reads as a margin, not as print.
  static Future<Color?> bandColor(String? path) async {
    if (path == null) return null;
    if (_bandCache.containsKey(path)) return _bandCache[path];
    final edge = await edgeColor(path);
    final band = edge == null ? null : Color.lerp(edge, const Color(0xFF000000), 0.18);
    _bandCache[path] = band;
    return band;
  }

  static Future<(Uint8List, int, int)?> _small(String path) async {
    final bytes = await File(path).readAsBytes();
    final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
    final codec = await ui.instantiateImageCodecFromBuffer(buffer, targetWidth: 24);
    final frame = await codec.getNextFrame();
    final image = frame.image;
    try {
      final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
      if (data == null) return null;
      return (data.buffer.asUint8List(), image.width, image.height);
    } finally {
      image.dispose();
      codec.dispose();
    }
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
