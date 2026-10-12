/// Page curl of the paged readers (docs/library-books-3d-plan.md § 3.4).
///
/// * [LibraryPageCurl] draws one frame of a turning page: with the shader
///   `assets/shaders/page_curl.frag` when [LibraryPageCurlProgram.load]
///   succeeded, otherwise (and for the rest of the process once the shader
///   threw while painting) with [LibraryPageCurlMeshPainter].
/// * [LibraryPageCurlController] follows the finger (two directions,
///   right-to-left mirrored) and animates completions, cancellations and
///   the turns asked by the controller or the tap zones.
/// * [LibraryPageCurlLayer] is what a reader stacks above its existing
///   `PageView`. It only takes the horizontal drags it can turn into a curl;
///   any other drag (and every drag while it is disabled) reaches the
///   `PageView` with its own physics. When a page has fully turned it calls
///   `onTurned(target)`: the reader jumps its `PageView` there, without
///   animation, under the curled page.
///
/// ## Integrating a reader (CBZ / online pages)
///
/// ```dart
/// // State (TickerProviderStateMixin):
/// late final LibraryPageCurlController _curl =
///     LibraryPageCurlController(vsync: this);
/// final LibraryPageTextureCache _textures = LibraryPageTextureCache();
/// // dispose(): _curl.dispose(); _textures.dispose();
/// // didHaveMemoryPressure(): the layer already purges all but the spread
/// // on screen; a reader that owns more textures purges them too.
///
/// Stack(children: <Widget>[
///   PageView.builder(controller: _pageController, reverse: rtl, ...),
///   Positioned.fill(
///     child: LibraryPageCurlLayer(
///       // Curl style, not zoomed, not vertical, no Reduce Motion.
///       enabled: curl && !_zoomed && !_vertical && !reduceMotion,
///       controller: _curl,
///       rightToLeft: rtl,
///       currentIndex: _pagedLeading + page,     // PageView item index
///       itemCount: _pagedLeading + count + 1,
///       // null for the chapter cards: their turns stay PageView slides.
///       faceOf: (item) => isPage(item)
///           ? LibraryPageCurlFace.single(item - _pagedLeading)
///           : null,
///       contentKey: source.key,                 // changes with the chapter
///       render: (page, pixels, cancel) => resolveClone(page, cancel),
///       cache: _textures,
///       paperColor: palette.background,
///       onTurned: (item) => _pageController.jumpToPage(item),
///     ),
///   ),
/// ])
///
/// // d-pad and tap zones:
/// final direction = forward ? LibraryPageTurnDirection.forward
///                           : LibraryPageTurnDirection.backward;
/// if (curlEnabled && _curl.canTurn(direction)) {
///   unawaited(_curl.turn(direction));   // 380 ms, then onTurned
/// } else {
///   forward ? _next() : _previous();    // the existing PageView turn
/// }
/// ```
///
/// `render` returns an image the cache owns: for a CBZ or online page,
/// resolve the reader's own `ImageProvider` (same `cacheWidth`/`cacheHeight`
/// as the `PageView` item, so no second decode), clone `ImageInfo.image`,
/// dispose the `ImageInfo` and return the clone; return null once `cancel`
/// is cancelled. The curl draws every image `BoxFit.contain` over
/// `paperColor`, centred for single pages and, for spreads, aligned toward
/// the spine: the `PageView` items must draw them the same way (use
/// [LibraryPageSpreadLayout]) so that the hand-off is seamless.
///
/// ## Two-page spreads and the PDF / EPUB pages modes
///
/// With [LibraryPageSpreads], each `PageView` item is one spread:
/// `faceOf: (i) => LibraryPageCurlFace.of(spreads[i])`, `render` receives
/// page indices and the half-page pixel size, and the item builder is
/// `LibraryPageSpreadLayout(face: ..., pageBuilder: ...)`. A turn then
/// lifts only the outer page of the spread (book-like: its back shows the
/// next spread's facing page). The PDF pages mode composes exactly the same
/// way: a `PageView` of spreads whose items show the textures of the same
/// cache (`LibraryPageTextureKey(contentKey, page, w, h)`, rendered by
/// `PdfPage.render` + `createImage`, the cancel token checked before
/// `createImage` and the `PdfImage` always disposed), the layer on top. EPUB
/// and TXT pages render `Picture.toImage` of the paginated page.
library;

import 'dart:async';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/widgets.dart';

import 'package:neostation/services/library_http.dart' show LibraryCancelToken;

import 'library_page_spreads.dart';
import 'library_page_textures.dart';

/// Direction of a page turn, in reading order.
enum LibraryPageTurnDirection { forward, backward }

// ------------------------------------------------------------------ program

/// The page-curl fragment program, loaded once per process.
class LibraryPageCurlProgram {
  /// Wraps an already loaded [program] (tests, hosts that load it
  /// themselves). Readers use [load].
  LibraryPageCurlProgram(this.program);

  /// Shader asset declared under `shaders:` in `pubspec.yaml`.
  static const String asset = 'assets/shaders/page_curl.frag';

  /// Number of float uniforms of [asset] (see the shader's declarations).
  static const int floatUniforms = 24;

  /// Loads the shader asset (test seam).
  static Future<ui.FragmentProgram> Function(String asset) loader =
      ui.FragmentProgram.fromAsset;

  static Future<LibraryPageCurlProgram?>? _loading;
  static LibraryPageCurlProgram? _loaded;
  static Object? _loadError;

  /// The program, or null to draw with [LibraryPageCurlMeshPainter].
  ///
  /// One attempt per process: the result, null included (missing asset,
  /// compilation refused by the device), is remembered. Never throws.
  static Future<LibraryPageCurlProgram?> load() => _loading ??= _attempt();

  static Future<LibraryPageCurlProgram?> _attempt() async {
    try {
      final program = await loader(asset);
      return _loaded = LibraryPageCurlProgram(program);
    } catch (error) {
      _loadError = error;
      return null;
    }
  }

  /// The program once [load] has succeeded, else null (not loaded yet, or
  /// the painter fallback).
  static LibraryPageCurlProgram? get loaded => _loaded;

  /// Why [load] gave null (diagnostics).
  static Object? get loadError => _loadError;

  /// Forgets the attempt and restores the [loader].
  @visibleForTesting
  static void resetForTesting() {
    _loading = null;
    _loaded = null;
    _loadError = null;
    loader = ui.FragmentProgram.fromAsset;
  }

  final ui.FragmentProgram program;
  Object? _failure;

  /// Whether the shader threw while painting: from then on every
  /// [LibraryPageCurl] of the process uses the painter.
  bool get failed => _failure != null;

  /// The first error thrown while painting with the shader.
  Object? get failure => _failure;

  void reportFailure(Object error) => _failure ??= error;

  /// A new shader of this program (owned and disposed by the caller).
  ui.FragmentShader createShader() => program.fragmentShader();

  /// Paints one frame of [geometry] with [shader]. Throws when the shader
  /// cannot be used (the caller then falls back to the painter).
  void paint(
    Canvas canvas,
    Size size,
    ui.FragmentShader shader,
    LibraryPageCurlGeometry geometry, {
    required ui.Image front,
    ui.Image? back,
    ui.Image? under,
    required Color paperColor,
  }) {
    var index = 0;
    void put(double value) => shader.setFloat(index++, value);
    final page = geometry.page;
    put(size.width);
    put(size.height);
    put(page.left);
    put(page.top);
    put(page.width);
    put(page.height);
    put(geometry.axisPoint.dx);
    put(geometry.axisPoint.dy);
    put(geometry.axisNormal.dx);
    put(geometry.axisNormal.dy);
    put(geometry.radius);
    put(geometry.hingeRight ? 1 : 0);
    put(geometry.alignToHinge ? 1 : 0);
    put(geometry.shadow);
    put(front.width.toDouble());
    put(front.height.toDouble());
    put(back?.width.toDouble() ?? 0);
    put(back?.height.toDouble() ?? 0);
    put(under?.width.toDouble() ?? 0);
    put(under?.height.toDouble() ?? 0);
    final alpha = paperColor.a;
    put(paperColor.r * alpha);
    put(paperColor.g * alpha);
    put(paperColor.b * alpha);
    put(alpha);
    assert(index == floatUniforms);
    // Every sampler must be bound: the missing pages reuse the front, the
    // shader ignores them (size 0).
    shader
      ..setImageSampler(0, front, filterQuality: FilterQuality.low)
      ..setImageSampler(1, back ?? front, filterQuality: FilterQuality.low)
      ..setImageSampler(2, under ?? front, filterQuality: FilterQuality.low);
    canvas.drawRect(Offset.zero & size, Paint()..shader = shader);
  }
}

// ----------------------------------------------------------------- geometry

/// Geometry of one frame of a page turn, shared by the shader and the
/// painter (logical pixels of the drawing surface).
///
/// The turning page ([page]) rolls around a cylinder of [radius] whose axis
/// passes through [axisPoint], perpendicular to [axisNormal] (unit vector
/// toward the edge that lifts). A point of the page at distance `s > 0`
/// beyond the axis wraps around the cylinder; past half a turn (`s > πr`)
/// it lies flat on top of the page, folded back toward the hinge. At
/// progress 0 the axis touches the lifting corner (the page is flat); at
/// progress 1 it reaches the hinge with a zero radius: a single page has
/// left the surface, the outer page of a spread lies on the other half.
@immutable
class LibraryPageCurlGeometry {
  const LibraryPageCurlGeometry({
    required this.page,
    required this.hingeRight,
    required this.alignToHinge,
    required this.axisPoint,
    required this.axisNormal,
    required this.radius,
    required this.shadow,
    required this.progress,
  });

  /// Geometry of a turn in [direction] at [progress] (0..1) on a surface of
  /// [size]. [corner] is the grabbed corner, normalized in the page (its
  /// `dy` tilts the fold: below the middle, the bottom corner leads).
  /// [spread]: the page is the turning half of a two-page spread.
  factory LibraryPageCurlGeometry.resolve({
    required Size size,
    required LibraryPageTurnDirection direction,
    required double progress,
    bool rightToLeft = false,
    Offset corner = const Offset(1, defaultGrab),
    bool spread = false,
  }) {
    final liftsRight = liftsRightEdge(direction, rightToLeft);
    final page = !spread
        ? Offset.zero & size
        : liftsRight
        ? Rect.fromLTWH(size.width / 2, 0, size.width / 2, size.height)
        : Rect.fromLTWH(0, 0, size.width / 2, size.height);
    final t = progress.isFinite ? progress.clamp(0.0, 1.0) : 0.0;
    final grab = corner.dy.isFinite ? corner.dy.clamp(0.0, 1.0) : 0.5;
    final width = page.width;
    final height = page.height;
    final tilt = (grab - 0.5) * 2 * maxTilt * (1 - t);
    // Distance of the axis from the hinge: at t = 0 the axis touches the
    // lifting corner, so the whole page is flat.
    final along = (width + height / 2 * math.tan(tilt.abs())) * (1 - t);
    final cos = math.cos(tilt);
    final sin = math.sin(tilt);
    return LibraryPageCurlGeometry(
      page: page,
      hingeRight: !liftsRight,
      alignToHinge: spread,
      axisPoint: liftsRight
          ? Offset(page.left + along, page.center.dy)
          : Offset(page.right - along, page.center.dy),
      axisNormal: liftsRight ? Offset(cos, sin) : Offset(-cos, sin),
      radius: width * radiusFactor * (1 - t * t),
      shadow: t <= 0 || t >= 1
          ? 0
          : math.min(1.0, t / 0.05) * (1 - t * t * t * t),
      progress: t,
    );
  }

  /// Largest tilt of the fold (radians), at the start of a turn.
  static const double maxTilt = 0.3;

  /// Radius of the roll at the start of a turn, relative to the page width.
  static const double radiusFactor = 0.11;

  /// Grab height of the turns without a finger (controller, tap zones):
  /// the bottom corner leads.
  static const double defaultGrab = 0.86;

  /// Whether a turn lifts the right edge of the page (forward turns of
  /// left-to-right books, backward turns of right-to-left ones).
  static bool liftsRightEdge(
    LibraryPageTurnDirection direction,
    bool rightToLeft,
  ) => (direction == LibraryPageTurnDirection.forward) != rightToLeft;

  /// The page that turns (the whole surface, or the turning half).
  final Rect page;

  /// The hinge is the right edge of [page] (the left edge lifts).
  final bool hingeRight;

  /// Images aligned toward the hinge (the spine of a spread) instead of
  /// centred.
  final bool alignToHinge;
  final Offset axisPoint;
  final Offset axisNormal;
  final double radius;

  /// Strength of the shadows (0 at rest and once the page has landed).
  final double shadow;
  final double progress;

  /// Horizontal alignment of the images in [page] (0 left, 1 right).
  double get alignX => alignToHinge ? (hingeRight ? 1.0 : 0.0) : 0.5;

  /// Width of the shadows on a surface of [size].
  double shadowWidth(Size size) =>
      math.max(size.shortestSide * 0.04, 4.0) + radius;

  /// Signed distance of [q] beyond the axis (positive: the lifting side).
  double distance(Offset q) =>
      (q.dx - axisPoint.dx) * axisNormal.dx +
      (q.dy - axisPoint.dy) * axisNormal.dy;

  /// Where the page point [q] is drawn, whether its back side shows, and
  /// its light (1 = unshaded).
  (Offset, bool, double) project(Offset q) {
    final s = distance(q);
    if (s <= 0) return (q, false, 1.0);
    final foot = q - axisNormal * s;
    final r = radius;
    if (r < 0.01) return (foot - axisNormal * s, true, 0.95);
    final angle = s / r;
    if (angle < math.pi) {
      final d = r * math.sin(angle);
      final k = d / r;
      if (angle <= math.pi / 2) {
        return (foot + axisNormal * d, false, 1.0 - 0.35 * k * k * k);
      }
      return (foot + axisNormal * d, true, 0.78 + 0.17 * (1.0 - k));
    }
    final d = math.pi * r - s;
    return (foot + axisNormal * d, true, 0.85 + 0.1 * math.exp(d / r));
  }

  /// Rect of an image of [image] size drawn `BoxFit.contain` in [page],
  /// vertically centred, at horizontal alignment [alignX] (0..1).
  static Rect fitImage(Size image, Rect page, double alignX) {
    if (image.isEmpty || page.isEmpty) return page;
    final pageAspect = page.width / page.height;
    final imageAspect = image.width / image.height;
    final width = imageAspect > pageAspect
        ? page.width
        : page.width * imageAspect / pageAspect;
    final height = imageAspect > pageAspect
        ? page.height * pageAspect / imageAspect
        : page.height;
    return Rect.fromLTWH(
      page.left + (page.width - width) * alignX,
      page.top + (page.height - height) / 2,
      width,
      height,
    );
  }
}

// ------------------------------------------------------------------ painter

final Float64List _identity = Float64List.fromList(<double>[
  1, 0, 0, 0, //
  0, 1, 0, 0, //
  0, 0, 1, 0, //
  0, 0, 0, 1, //
]);

int _shadeColor(Color color, double light, double alpha) {
  int channel(double value) => (value * light * 255).round().clamp(0, 255);
  final a = (color.a * alpha * 255).round().clamp(0, 255);
  return (a << 24) |
      (channel(color.r) << 16) |
      (channel(color.g) << 8) |
      channel(color.b);
}

/// A grid over a rect of the page, projected by the curl.
class _CurlMesh {
  _CurlMesh._(
    this.positions,
    this.textureCoordinates,
    this.lights,
    this.front,
    this.back,
  );

  /// Grid of [region] (page coordinates). With [image], the texture
  /// coordinates map [region] to the whole image, mirrored for the back
  /// side.
  factory _CurlMesh.build(
    LibraryPageCurlGeometry geometry,
    Rect region, {
    Size? image,
    bool mirrored = false,
  }) {
    const columns = LibraryPageCurlMeshPainter.columns;
    const rows = LibraryPageCurlMeshPainter.rows;
    const stride = columns + 1;
    const count = stride * (rows + 1);
    final positions = Float32List(count * 2);
    final texture = image == null ? null : Float32List(count * 2);
    final lights = Float32List(count);
    final distances = Float32List(count);
    var vertex = 0;
    for (var j = 0; j <= rows; j++) {
      final v = j / rows;
      final y = region.top + region.height * v;
      for (var i = 0; i <= columns; i++) {
        final u = i / columns;
        final q = Offset(region.left + region.width * u, y);
        final (position, _, light) = geometry.project(q);
        positions[vertex * 2] = position.dx;
        positions[vertex * 2 + 1] = position.dy;
        lights[vertex] = light;
        distances[vertex] = geometry.distance(q);
        if (texture != null) {
          texture[vertex * 2] = (mirrored ? 1 - u : u) * image!.width;
          texture[vertex * 2 + 1] = v * image.height;
        }
        vertex++;
      }
    }
    // A triangle shows its back side once its centre is past the top of the
    // roll's lower half.
    final limit = math.pi * geometry.radius / 2;
    final front = Uint16List(columns * rows * 6);
    final back = Uint16List(columns * rows * 6);
    var frontCount = 0;
    var backCount = 0;
    void add(int a, int b, int c) {
      final s = (distances[a] + distances[b] + distances[c]) / 3;
      if (s < limit || (limit <= 0 && s <= 0)) {
        front[frontCount++] = a;
        front[frontCount++] = b;
        front[frontCount++] = c;
      } else {
        back[backCount++] = a;
        back[backCount++] = b;
        back[backCount++] = c;
      }
    }

    for (var j = 0; j < rows; j++) {
      for (var i = 0; i < columns; i++) {
        final a = j * stride + i;
        final b = a + 1;
        final c = a + stride;
        final d = c + 1;
        add(a, b, d);
        add(a, d, c);
      }
    }
    return _CurlMesh._(
      positions,
      texture,
      lights,
      Uint16List.sublistView(front, 0, frontCount),
      Uint16List.sublistView(back, 0, backCount),
    );
  }

  final Float32List positions;
  final Float32List? textureCoordinates;
  final Float32List lights;
  final Uint16List front;
  final Uint16List back;

  Int32List _colors(Color base, double alpha) {
    final colors = Int32List(lights.length);
    for (var i = 0; i < lights.length; i++) {
      colors[i] = _shadeColor(base, lights[i], alpha);
    }
    return colors;
  }

  /// Paper (vertex colours only).
  void drawPaper(Canvas canvas, Uint16List indices, Color paper) {
    if (indices.isEmpty) return;
    final vertices = ui.Vertices.raw(
      ui.VertexMode.triangles,
      positions,
      colors: _colors(paper, 1),
      indices: indices,
    );
    canvas.drawVertices(vertices, BlendMode.dst, Paint());
    vertices.dispose();
  }

  /// [image] shaded by the lights, at [alpha].
  void drawImage(
    Canvas canvas,
    Uint16List indices,
    ui.Image image, {
    double alpha = 1,
  }) {
    if (indices.isEmpty || textureCoordinates == null) return;
    final shader = ImageShader(
      image,
      TileMode.clamp,
      TileMode.clamp,
      _identity,
      filterQuality: FilterQuality.low,
    );
    final vertices = ui.Vertices.raw(
      ui.VertexMode.triangles,
      positions,
      textureCoordinates: textureCoordinates,
      colors: _colors(const Color(0xFFFFFFFF), alpha),
      indices: indices,
    );
    canvas.drawVertices(vertices, BlendMode.modulate, Paint()..shader = shader);
    vertices.dispose();
    shader.dispose();
  }
}

/// Painter fallback of the curl: a 24 x 32 mesh per image drawn with
/// [Canvas.drawVertices] and an [ImageShader], the back side darker, the
/// shadows of the roll and of the folded part.
class LibraryPageCurlMeshPainter extends CustomPainter {
  LibraryPageCurlMeshPainter({
    required this.front,
    this.back,
    this.under,
    required this.direction,
    required this.progress,
    this.rightToLeft = false,
    this.corner = const Offset(1, LibraryPageCurlGeometry.defaultGrab),
    this.spread = false,
    this.paperColor = const Color(0xFFFFFFFF),
  });

  /// Grid columns and rows of each mesh.
  static const int columns = 24;
  static const int rows = 32;

  final ui.Image front;
  final ui.Image? back;
  final ui.Image? under;
  final LibraryPageTurnDirection direction;
  final double progress;
  final bool rightToLeft;
  final Offset corner;
  final bool spread;
  final Color paperColor;

  LibraryPageCurlGeometry geometryFor(Size size) =>
      LibraryPageCurlGeometry.resolve(
        size: size,
        direction: direction,
        progress: progress,
        rightToLeft: rightToLeft,
        corner: corner,
        spread: spread,
      );

  static Size _sizeOf(ui.Image image) =>
      Size(image.width.toDouble(), image.height.toDouble());

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final geometry = geometryFor(size);
    final page = geometry.page;
    canvas.save();
    canvas.clipRect(Offset.zero & size);

    // The page revealed under the curl, with the shadow of the roll.
    canvas.save();
    canvas.clipRect(page);
    canvas.drawRect(page, Paint()..color = paperColor);
    final under = this.under;
    if (under != null) {
      final imageSize = _sizeOf(under);
      canvas.drawImageRect(
        under,
        Offset.zero & imageSize,
        LibraryPageCurlGeometry.fitImage(imageSize, page, geometry.alignX),
        Paint()..filterQuality = FilterQuality.low,
      );
    }
    _paintRollShadow(canvas, size, geometry);
    canvas.restore();

    // Front side.
    final pageMesh = _CurlMesh.build(geometry, page);
    pageMesh.drawPaper(canvas, pageMesh.front, paperColor);
    final frontSize = _sizeOf(front);
    final frontMesh = _CurlMesh.build(
      geometry,
      LibraryPageCurlGeometry.fitImage(frontSize, page, geometry.alignX),
      image: frontSize,
    );
    frontMesh.drawImage(canvas, frontMesh.front, front);

    // Shadow of the folded part, then its back side.
    _paintFoldShadow(canvas, size, geometry);
    pageMesh.drawPaper(canvas, pageMesh.back, paperColor);
    final back = this.back;
    if (back != null) {
      final backSize = _sizeOf(back);
      final mirrored = LibraryPageCurlGeometry.fitImage(
        backSize,
        page,
        1 - geometry.alignX,
      );
      final region = Rect.fromLTRB(
        page.left + page.right - mirrored.right,
        mirrored.top,
        page.left + page.right - mirrored.left,
        mirrored.bottom,
      );
      final backMesh = _CurlMesh.build(
        geometry,
        region,
        image: backSize,
        mirrored: true,
      );
      backMesh.drawImage(canvas, backMesh.back, back);
    } else {
      // Paper seen from behind: the front shows through, mirrored by the
      // fold.
      frontMesh.drawImage(canvas, frontMesh.back, front, alpha: 0.12);
    }
    canvas.restore();
  }

  void _paintRollShadow(
    Canvas canvas,
    Size size,
    LibraryPageCurlGeometry geometry,
  ) {
    if (geometry.shadow <= 0) return;
    final width = geometry.shadowWidth(size);
    final extent = size.longestSide * 2;
    canvas.save();
    canvas.translate(geometry.axisPoint.dx, geometry.axisPoint.dy);
    canvas.rotate(math.atan2(geometry.axisNormal.dy, geometry.axisNormal.dx));
    final gradient = ui.Gradient.linear(
      Offset(geometry.radius, 0),
      Offset(geometry.radius + width, 0),
      <Color>[
        Color.fromRGBO(0, 0, 0, 0.45 * geometry.shadow),
        const Color(0x00000000),
      ],
    );
    canvas.drawRect(
      Rect.fromLTRB(0, -extent, geometry.radius + width, extent),
      Paint()..shader = gradient,
    );
    gradient.dispose();
    canvas.restore();
  }

  void _paintFoldShadow(
    Canvas canvas,
    Size size,
    LibraryPageCurlGeometry geometry,
  ) {
    if (geometry.shadow <= 0) return;
    // Outline of the part of the page showing its back side.
    final limit = math.pi * geometry.radius / 2;
    final page = geometry.page;
    final corners = <Offset>[
      page.topLeft,
      page.topRight,
      page.bottomRight,
      page.bottomLeft,
    ];
    final polygon = <Offset>[];
    for (var i = 0; i < corners.length; i++) {
      final a = corners[i];
      final b = corners[(i + 1) % corners.length];
      final da = geometry.distance(a) - limit;
      final db = geometry.distance(b) - limit;
      if (da >= 0) polygon.add(a);
      if ((da >= 0) != (db >= 0)) {
        polygon.add(Offset.lerp(a, b, da / (da - db))!);
      }
    }
    if (polygon.length < 3) return;
    const steps = 12;
    final path = Path();
    for (var i = 0; i < polygon.length; i++) {
      final a = polygon[i];
      final b = polygon[(i + 1) % polygon.length];
      for (var k = 0; k < steps; k++) {
        final (point, _, _) = geometry.project(Offset.lerp(a, b, k / steps)!);
        if (i == 0 && k == 0) {
          path.moveTo(point.dx, point.dy);
        } else {
          path.lineTo(point.dx, point.dy);
        }
      }
    }
    path.close();
    canvas.drawPath(
      path,
      Paint()
        ..color = Color.fromRGBO(0, 0, 0, 0.3 * geometry.shadow)
        ..maskFilter = MaskFilter.blur(
          BlurStyle.normal,
          math.max(2.0, size.shortestSide * 0.012),
        ),
    );
  }

  @override
  bool shouldRepaint(covariant LibraryPageCurlMeshPainter old) =>
      !identical(old.front, front) ||
      !identical(old.back, back) ||
      !identical(old.under, under) ||
      old.direction != direction ||
      old.progress != progress ||
      old.rightToLeft != rightToLeft ||
      old.corner != corner ||
      old.spread != spread ||
      old.paperColor != paperColor;
}

// ------------------------------------------------------------------- widget

/// One frame of a turning page.
///
/// [front] is the page that turns; [under] the page it reveals (paper when
/// null); [back] the page printed on its back side (the facing page of the
/// next spread), or null for paper through which the front faintly shows.
/// Images are drawn `BoxFit.contain` over [paperColor]: centred, or aligned
/// toward the spine when [spread] (the page is the turning half of a
/// two-page spread: the right half when the right edge lifts, see
/// [LibraryPageCurlGeometry.liftsRightEdge]). The widget never takes
/// ownership of the images.
class LibraryPageCurl extends StatefulWidget {
  const LibraryPageCurl({
    super.key,
    required this.front,
    this.back,
    this.under,
    this.rightToLeft = false,
    required this.direction,
    required this.progress,
    this.corner = const Offset(1, LibraryPageCurlGeometry.defaultGrab),
    this.spread = false,
    this.paperColor = const Color(0xFFFFFFFF),
    this.program,
  });

  final ui.Image front;
  final ui.Image? back;
  final ui.Image? under;
  final bool rightToLeft;
  final LibraryPageTurnDirection direction;

  /// 0 (flat) to 1 (fully turned).
  final double progress;

  /// Grabbed corner, normalized in the page: `dx` the lifting edge (0 left,
  /// 1 right), `dy` the grab height (0 top, 1 bottom).
  final Offset corner;
  final bool spread;
  final Color paperColor;

  /// The shader; null draws with [LibraryPageCurlMeshPainter].
  final LibraryPageCurlProgram? program;

  @override
  State<LibraryPageCurl> createState() => LibraryPageCurlState();
}

class LibraryPageCurlState extends State<LibraryPageCurl> {
  ui.FragmentShader? _shader;
  LibraryPageCurlProgram? _shaderProgram;
  bool _shaderFailed = false;
  bool? _lastPaintUsedShader;

  /// Whether the last frame was drawn by the shader (null before the first
  /// frame).
  @visibleForTesting
  bool? get lastPaintUsedShader => _lastPaintUsedShader;

  /// Whether this curl has switched to the painter after a shader error.
  @visibleForTesting
  bool get shaderFailed => _shaderFailed;

  @override
  void initState() {
    super.initState();
    _updateShader();
  }

  @override
  void didUpdateWidget(covariant LibraryPageCurl oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.program, widget.program)) _updateShader();
  }

  @override
  void dispose() {
    _shader?.dispose();
    _shader = null;
    super.dispose();
  }

  void _updateShader() {
    final program = widget.program;
    if (identical(program, _shaderProgram)) return;
    _shader?.dispose();
    _shader = null;
    _shaderProgram = program;
    if (program == null || program.failed || _shaderFailed) return;
    try {
      _shader = program.createShader();
    } catch (error) {
      _onShaderError(error);
    }
  }

  // Called while painting: only flags, the next frames use the painter.
  void _onShaderError(Object error) {
    _shaderFailed = true;
    _shaderProgram?.reportFailure(error);
  }

  void _onPainted(bool usedShader) => _lastPaintUsedShader = usedShader;

  @override
  Widget build(BuildContext context) {
    final program = _shaderProgram;
    final usable = !_shaderFailed && program != null && !program.failed
        ? _shader
        : null;
    return CustomPaint(
      willChange: true,
      painter: _LibraryPageCurlPainter(
        mesh: LibraryPageCurlMeshPainter(
          front: widget.front,
          back: widget.back,
          under: widget.under,
          direction: widget.direction,
          progress: widget.progress,
          rightToLeft: widget.rightToLeft,
          corner: widget.corner,
          spread: widget.spread,
          paperColor: widget.paperColor,
        ),
        program: usable == null ? null : program,
        shader: usable,
        onShaderError: _onShaderError,
        onPainted: _onPainted,
      ),
      child: const SizedBox.expand(),
    );
  }
}

class _LibraryPageCurlPainter extends CustomPainter {
  _LibraryPageCurlPainter({
    required this.mesh,
    required this.program,
    required this.shader,
    required this.onShaderError,
    required this.onPainted,
  });

  final LibraryPageCurlMeshPainter mesh;
  final LibraryPageCurlProgram? program;
  final ui.FragmentShader? shader;
  final void Function(Object error) onShaderError;
  final void Function(bool usedShader) onPainted;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final program = this.program;
    final shader = this.shader;
    if (program != null && shader != null && !program.failed) {
      canvas.save();
      try {
        program.paint(
          canvas,
          size,
          shader,
          mesh.geometryFor(size),
          front: mesh.front,
          back: mesh.back,
          under: mesh.under,
          paperColor: mesh.paperColor,
        );
        canvas.restore();
        onPainted(true);
        return;
      } catch (error) {
        canvas.restore();
        onShaderError(error);
      }
    }
    mesh.paint(canvas, size);
    onPainted(false);
  }

  @override
  bool shouldRepaint(covariant _LibraryPageCurlPainter old) =>
      !identical(old.shader, shader) ||
      !identical(old.program, program) ||
      mesh.shouldRepaint(old.mesh);
}

// --------------------------------------------------------------- controller

/// What a [LibraryPageCurlController] needs from the surface it turns
/// (implemented by [LibraryPageCurlLayer]).
abstract interface class LibraryPageCurlDelegate {
  /// Size of the page that turns (the whole surface, or the turning half of
  /// a spread): a drag across its width turns it completely.
  Size get curlPageSize;

  /// Right-to-left reading: a leftward drag turns backward.
  bool get curlRightToLeft;

  /// Whether a turn in [direction] can be drawn as a curl now.
  bool canCurl(LibraryPageTurnDirection direction);

  /// The page has fully turned in [direction] (called once per turn, while
  /// its last frame is shown).
  void curlCompleted(LibraryPageTurnDirection direction);
}

enum _CurlPhase { idle, pending, dragging, settling, landed }

/// Drives a page turn: follows a drag, then completes it (more than 30 %
/// of the page, or a flick toward the turn faster than 600 px/s) or
/// cancels it in 220 ms; [turn] animates a whole turn in 380 ms.
///
/// The progress is the distance the finger travelled toward the hinge over
/// the page width, so the fold follows the finger. Right to left, the drag
/// directions are mirrored. A turn needs an attached delegate
/// ([LibraryPageCurlLayer] attaches itself).
class LibraryPageCurlController extends ChangeNotifier {
  LibraryPageCurlController({required TickerProvider vsync})
    : _animation = AnimationController(vsync: vsync) {
    _animation.addListener(_onTick);
  }

  /// Share of the page past which a released drag completes the turn.
  static const double completionThreshold = 0.3;

  /// Speed (px/s) past which a released drag follows its flick.
  static const double flingVelocity = 600;

  /// Return of a cancelled drag.
  static const Duration cancelDuration = Duration(milliseconds: 220);

  /// A whole turn ([turn]) and the end of a completed drag (pro rata).
  static const Duration turnDuration = Duration(milliseconds: 380);

  final AnimationController _animation;
  LibraryPageCurlDelegate? _delegate;
  _CurlPhase _phase = _CurlPhase.idle;
  LibraryPageTurnDirection? _direction;
  double _progress = 0;
  Offset _corner = const Offset(1, LibraryPageCurlGeometry.defaultGrab);
  Offset? _dragOrigin;
  Completer<bool>? _result;
  int _generation = 0;
  bool _disposed = false;

  /// Direction of the turn in progress, null at rest.
  LibraryPageTurnDirection? get direction => _direction;

  /// 0 (flat) to 1 (fully turned).
  double get progress => _progress;

  /// Grabbed corner, normalized in the turning page (see
  /// [LibraryPageCurl.corner]).
  Offset get corner => _corner;

  /// A page is turning (followed, animated, or landing).
  bool get isActive => _direction != null;

  /// The finger holds the page.
  bool get isDragging => _phase == _CurlPhase.dragging;

  /// The page is animating toward the end or back.
  bool get isAnimating => _phase == _CurlPhase.settling;

  bool get isAttached => _delegate != null;

  /// Turn direction of a horizontal drag of [dx] (negative: leftward).
  static LibraryPageTurnDirection directionOfDrag(
    double dx, {
    required bool rightToLeft,
  }) => (dx < 0) != rightToLeft
      ? LibraryPageTurnDirection.forward
      : LibraryPageTurnDirection.backward;

  /// Attaches the surface turned by this controller (one at a time).
  void attach(LibraryPageCurlDelegate delegate) {
    if (identical(_delegate, delegate)) return;
    reset();
    _delegate = delegate;
  }

  void detach(LibraryPageCurlDelegate delegate) {
    if (!identical(_delegate, delegate)) return;
    reset();
    _delegate = null;
  }

  /// Whether a turn in [direction] would be a curl (false: let the
  /// `PageView` turn).
  bool canTurn(LibraryPageTurnDirection direction) =>
      _delegate?.canCurl(direction) ?? false;

  bool _liftsRight(LibraryPageTurnDirection direction) =>
      LibraryPageCurlGeometry.liftsRightEdge(
        direction,
        _delegate?.curlRightToLeft ?? false,
      );

  /// A finger touched the page at [local] (layer coordinates).
  void beginDrag(Offset local) {
    if (_delegate == null || _phase != _CurlPhase.idle) {
      _dragOrigin = null;
      return;
    }
    _dragOrigin = local;
    _phase = _CurlPhase.pending;
  }

  /// The finger moved to [local]. The first horizontal move picks the
  /// direction; a direction without a curl ends the drag.
  void updateDrag(Offset local) {
    final origin = _dragOrigin;
    final delegate = _delegate;
    if (origin == null || delegate == null) return;
    if (_phase == _CurlPhase.pending) {
      final dx = local.dx - origin.dx;
      if (dx == 0) return;
      final direction = directionOfDrag(
        dx,
        rightToLeft: delegate.curlRightToLeft,
      );
      if (!delegate.canCurl(direction)) {
        _dragOrigin = null;
        _phase = _CurlPhase.idle;
        return;
      }
      _direction = direction;
      _phase = _CurlPhase.dragging;
    }
    if (_phase != _CurlPhase.dragging) return;
    final liftsRight = _liftsRight(_direction!);
    final size = delegate.curlPageSize;
    final travel = liftsRight ? origin.dx - local.dx : local.dx - origin.dx;
    _progress = size.width > 0 ? (travel / size.width).clamp(0.0, 1.0) : 0.0;
    _corner = Offset(
      liftsRight ? 1 : 0,
      size.height > 0 ? (local.dy / size.height).clamp(0.0, 1.0) : 0.5,
    );
    notifyListeners();
  }

  /// The finger left the page with [velocity]: completes the turn when it
  /// passed [completionThreshold] or flicked toward the turn faster than
  /// [flingVelocity] (a flick away cancels), else returns the page in
  /// [cancelDuration]. True once the page has turned.
  Future<bool> endDrag(Velocity velocity) {
    _dragOrigin = null;
    if (_phase == _CurlPhase.pending) _phase = _CurlPhase.idle;
    if (_phase != _CurlPhase.dragging) return Future<bool>.value(false);
    final vx = velocity.pixelsPerSecond.dx;
    final toward = _liftsRight(_direction!) ? -vx : vx;
    final complete =
        toward > flingVelocity ||
        (toward >= -flingVelocity && _progress > completionThreshold);
    if (!complete) return _animateTo(0, cancelDuration, Curves.easeOut);
    final remaining = (turnDuration.inMilliseconds * (1 - _progress)).round();
    return _animateTo(
      1,
      Duration(milliseconds: math.max(120, remaining)),
      Curves.easeOut,
    );
  }

  /// The drag was interrupted: the page returns.
  Future<bool> cancelDrag() {
    _dragOrigin = null;
    if (_phase == _CurlPhase.pending) _phase = _CurlPhase.idle;
    if (_phase != _CurlPhase.dragging) return Future<bool>.value(false);
    return _animateTo(0, cancelDuration, Curves.easeOut);
  }

  /// Turns a whole page in [direction] (controller, tap zones) in
  /// [turnDuration]. False at once when a turn is already running or when
  /// [canTurn] is false (the reader then turns its `PageView`).
  Future<bool> turn(LibraryPageTurnDirection direction) {
    final delegate = _delegate;
    if (delegate == null ||
        _phase != _CurlPhase.idle ||
        !delegate.canCurl(direction)) {
      return Future<bool>.value(false);
    }
    _direction = direction;
    _progress = 0;
    _corner = Offset(
      _liftsRight(direction) ? 1 : 0,
      LibraryPageCurlGeometry.defaultGrab,
    );
    notifyListeners();
    return _animateTo(1, turnDuration, Curves.easeInOut);
  }

  Future<bool> _animateTo(double target, Duration duration, Curve curve) {
    _phase = _CurlPhase.settling;
    final generation = ++_generation;
    final result = Completer<bool>();
    _result = result;
    _animation.value = _progress;
    _animation
        .animateTo(target, duration: duration, curve: curve)
        .whenCompleteOrCancel(() {
          if (generation == _generation) _settled(target);
        });
    return result.future;
  }

  void _onTick() {
    if (_phase != _CurlPhase.settling) return;
    _progress = _animation.value;
    notifyListeners();
  }

  void _settled(double target) {
    final result = _result;
    _result = null;
    if (target < 1) {
      _clear();
      result?.complete(false);
      return;
    }
    final direction = _direction!;
    _progress = 1;
    _phase = _CurlPhase.landed;
    notifyListeners();
    // The reader moves its PageView under the turned page now; the curl is
    // removed after this frame, once the PageView shows the target.
    _delegate?.curlCompleted(direction);
    result?.complete(true);
    final generation = _generation;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (generation == _generation && _phase == _CurlPhase.landed) _clear();
    });
    SchedulerBinding.instance.ensureVisualUpdate();
  }

  bool get _landed => _phase == _CurlPhase.landed;

  void _clear() {
    _generation++;
    _phase = _CurlPhase.idle;
    _direction = null;
    _progress = 0;
    if (!_disposed) notifyListeners();
  }

  /// Stops any turn without completing it (the page is flat again).
  void reset() {
    _generation++;
    _animation.stop();
    _dragOrigin = null;
    final result = _result;
    _result = null;
    final wasActive = _phase != _CurlPhase.idle;
    _phase = _CurlPhase.idle;
    _direction = null;
    _progress = 0;
    result?.complete(false);
    if (wasActive && !_disposed) notifyListeners();
  }

  @override
  void dispose() {
    _disposed = true;
    reset();
    _animation.dispose();
    super.dispose();
  }
}

// -------------------------------------------------------------------- layer

/// What one `PageView` item shows, for the curl: one page, or the two
/// halves of a spread (a null half is empty paper).
@immutable
class LibraryPageCurlFace {
  /// One page drawn `BoxFit.contain`, centred, on the whole surface.
  const LibraryPageCurlFace.single(int this.page) : left = null, right = null;

  /// A two-page spread; each page `BoxFit.contain` in its half, aligned
  /// toward the spine.
  const LibraryPageCurlFace.spread({this.left, this.right}) : page = null;

  /// The face of [spread].
  factory LibraryPageCurlFace.of(LibraryPageSpread spread) => spread.doublePage
      ? LibraryPageCurlFace.spread(left: spread.left, right: spread.right)
      : LibraryPageCurlFace.single(spread.first);

  /// The page of a single face.
  final int? page;
  final int? left;
  final int? right;

  bool get isSpread => page == null;

  /// Pages shown.
  List<int> get pages => isSpread ? <int>[?left, ?right] : <int>[page!];

  /// Page on the right (or left) half; the page of a single face.
  int? pageOn({required bool right}) =>
      isSpread ? (right ? this.right : left) : page;

  @override
  bool operator ==(Object other) =>
      other is LibraryPageCurlFace &&
      other.page == page &&
      other.left == left &&
      other.right == right;

  @override
  int get hashCode => Object.hash(page, left, right);

  @override
  String toString() => isSpread
      ? 'LibraryPageCurlFace.spread(left: $left, right: $right)'
      : 'LibraryPageCurlFace.single($page)';
}

/// Renders page [page] for the curl at most [pixelSize] physical pixels
/// (the whole surface, or a half for spreads). The image belongs to the
/// texture cache; return null once [cancel] is cancelled.
typedef LibraryPageCurlRender =
    Future<ui.Image?> Function(
      int page,
      Size pixelSize,
      LibraryCancelToken cancel,
    );

/// Lays out one `PageView` item like the curl draws it: a single page on
/// the whole surface, centred; a spread's pages in their halves, aligned
/// toward the spine. [pageBuilder] draws page `page` `BoxFit.contain` at
/// `alignment`.
class LibraryPageSpreadLayout extends StatelessWidget {
  const LibraryPageSpreadLayout({
    super.key,
    required this.face,
    required this.pageBuilder,
  });

  final LibraryPageCurlFace face;
  final Widget Function(BuildContext context, int page, Alignment alignment)
  pageBuilder;

  @override
  Widget build(BuildContext context) {
    if (!face.isSpread) {
      return pageBuilder(context, face.page!, Alignment.center);
    }
    final left = face.left;
    final right = face.right;
    return Row(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        Expanded(
          child: left == null
              ? const SizedBox.shrink()
              : pageBuilder(context, left, Alignment.centerRight),
        ),
        Expanded(
          child: right == null
              ? const SizedBox.shrink()
              : pageBuilder(context, right, Alignment.centerLeft),
        ),
      ],
    );
  }
}

/// The page curl stacked above a reader's `PageView` (see the library
/// documentation above for the recipe).
///
/// Disabled ([enabled] false: another turn style, a zoomed page, the
/// vertical layout, Reduce Motion), it is absent from hit testing and from
/// the gesture arena. Enabled, it is hit first and wins the horizontal
/// drags it can curl (a neighbour item with a [faceOf]); the others (chapter
/// cards, the ends) reach the `PageView`. It renders the pages of the item
/// on screen and its neighbours through [render] into [cache] (retained,
/// never evicted), draws nothing at rest, and calls [onTurned] with the
/// target item when a page has fully turned.
class LibraryPageCurlLayer extends StatefulWidget {
  const LibraryPageCurlLayer({
    super.key,
    required this.enabled,
    required this.controller,
    required this.currentIndex,
    required this.itemCount,
    required this.faceOf,
    required this.render,
    required this.onTurned,
    required this.contentKey,
    this.rightToLeft = false,
    this.paperColor = const Color(0xFFFFFFFF),
    this.cache,
    this.child,
  });

  final bool enabled;
  final LibraryPageCurlController controller;

  /// `PageView` item on screen.
  final int currentIndex;
  final int itemCount;

  /// The face of item `index` (0 <= index < [itemCount]), null when the
  /// item cannot be drawn by the curl (a card).
  final LibraryPageCurlFace? Function(int index) faceOf;
  final LibraryPageCurlRender render;

  /// The page has fully turned: jump the `PageView` to `target` without
  /// animation, synchronously.
  final ValueChanged<int> onTurned;

  /// Identity of the pages (a source key, a chapter): textures are keyed
  /// by it, and a change cancels the turn.
  final Object contentKey;
  final bool rightToLeft;

  /// Background of the pages (margins, empty halves, missing pages).
  final Color paperColor;

  /// Texture cache; the layer drives its [LibraryPageTextureCache.retain]
  /// and purges it on memory pressure. Without one the layer owns its own.
  final LibraryPageTextureCache? cache;

  /// Drawn below the curl (the `PageView`), when the layer is not already
  /// placed in the reader's `Stack`.
  final Widget? child;

  @override
  State<LibraryPageCurlLayer> createState() => LibraryPageCurlLayerState();
}

/// The images (own handles) of the turn in progress.
class _CurlTurn {
  _CurlTurn({required this.direction, required this.spread});

  final LibraryPageTurnDirection direction;
  final bool spread;
  ui.Image? front;
  ui.Image? back;
  ui.Image? under;
  bool released = false;

  void dispose() {
    front?.dispose();
    back?.dispose();
    under?.dispose();
    front = back = under = null;
  }
}

class _LibraryPageCurlDragRecognizer extends HorizontalDragGestureRecognizer {
  _LibraryPageCurlDragRecognizer({super.debugOwner});

  /// Whether a drag of `dx` (sign: direction) becomes a curl.
  bool Function(double dx)? canAccept;

  @override
  bool hasSufficientGlobalDistanceToAccept(
    PointerDeviceKind pointerDeviceKind,
    double? deviceTouchSlop,
  ) =>
      super.hasSufficientGlobalDistanceToAccept(
        pointerDeviceKind,
        deviceTouchSlop,
      ) &&
      (canAccept?.call(globalDistanceMoved) ?? true);
}

class LibraryPageCurlLayerState extends State<LibraryPageCurlLayer>
    with WidgetsBindingObserver
    implements LibraryPageCurlDelegate {
  LibraryPageTextureCache? _ownCache;
  LibraryPageCurlProgram? _program = LibraryPageCurlProgram.loaded;
  Size _size = Size.zero;
  double _ratio = 1;
  _CurlTurn? _turn;
  bool _prefetchScheduled = false;

  /// Pages whose render failed or gave no image (not cancelled): their turns
  /// stay `PageView` slides until the next prefetch tries them again.
  final Set<Object> _unrenderable = <Object>{};

  LibraryPageTextureCache get _cache =>
      widget.cache ?? (_ownCache ??= LibraryPageTextureCache());

  /// The cache the layer renders into.
  @visibleForTesting
  LibraryPageTextureCache get cache => _cache;

  /// The shader program in use (null: the painter).
  @visibleForTesting
  LibraryPageCurlProgram? get program => _program;

  LibraryPageCurlController get _controller => widget.controller;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _controller.addListener(_onController);
    _controller.attach(this);
    if (_program == null) {
      unawaited(
        LibraryPageCurlProgram.load().then((program) {
          if (mounted && program != null && !identical(program, _program)) {
            setState(() => _program = program);
          }
        }),
      );
    }
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final ratio = MediaQuery.maybeDevicePixelRatioOf(context) ?? 1.0;
    if (ratio != _ratio) {
      _ratio = ratio;
      _schedulePrefetch();
    }
  }

  @override
  void didUpdateWidget(covariant LibraryPageCurlLayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.controller, widget.controller)) {
      oldWidget.controller.removeListener(_onController);
      oldWidget.controller.detach(this);
      _releaseTurn();
      widget.controller.addListener(_onController);
      widget.controller.attach(this);
    }
    if (!identical(oldWidget.cache, widget.cache)) {
      _releaseTurn();
      oldWidget.cache?.retain(const <Object>{});
      if (widget.cache != null) {
        _ownCache?.dispose();
        _ownCache = null;
      }
    }
    final contentChanged = oldWidget.contentKey != widget.contentKey;
    final layoutChanged =
        oldWidget.rightToLeft != widget.rightToLeft ||
        oldWidget.itemCount != widget.itemCount;
    final indexChanged = oldWidget.currentIndex != widget.currentIndex;
    if (!widget.enabled) {
      if (_controller.isActive) _controller.reset();
      if (oldWidget.enabled) _onDisabled();
      return;
    }
    if (_controller.isActive &&
        (contentChanged ||
            layoutChanged ||
            (indexChanged && !_controller._landed))) {
      // The pages moved under the turn (slider, chapter, rotation).
      _controller.reset();
    }
    if (contentChanged || layoutChanged || indexChanged || !oldWidget.enabled) {
      _schedulePrefetch();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _controller.removeListener(_onController);
    _controller.detach(this);
    _turn?.dispose();
    _turn = null;
    final own = _ownCache;
    if (own != null) {
      own.dispose();
    } else {
      widget.cache?.retain(const <Object>{});
    }
    super.dispose();
  }

  @override
  void didHaveMemoryPressure() {
    // Keep only the item on screen; a turn keeps its own handles.
    _cache.purge(keep: _keysOf(widget.currentIndex));
  }

  // ------------------------------------------------------------ delegate --

  LibraryPageCurlFace? _face(int index) {
    if (index < 0 || index >= widget.itemCount) return null;
    return widget.faceOf(index);
  }

  bool _isSpread(int index) => _face(index)?.isSpread ?? false;

  Size _pageSizeOf(bool spread) =>
      spread ? Size(_size.width / 2, _size.height) : _size;

  @override
  Size get curlPageSize => _pageSizeOf(_isSpread(widget.currentIndex));

  @override
  bool get curlRightToLeft => widget.rightToLeft;

  int _targetOf(LibraryPageTurnDirection direction) =>
      widget.currentIndex +
      (direction == LibraryPageTurnDirection.forward ? 1 : -1);

  @override
  bool canCurl(LibraryPageTurnDirection direction) {
    if (!mounted || !widget.enabled || _size.isEmpty) return false;
    final current = _face(widget.currentIndex);
    final target = _face(_targetOf(direction));
    if (current == null || target == null) return false;
    if (current.isSpread != target.isSpread) return false;
    final liftsRight = LibraryPageCurlGeometry.liftsRightEdge(
      direction,
      widget.rightToLeft,
    );
    final front = current.pageOn(right: liftsRight);
    return front != null &&
        !_unrenderable.contains(_keyOf(front, current.isSpread));
  }

  @override
  void curlCompleted(LibraryPageTurnDirection direction) {
    if (!mounted) return;
    widget.onTurned(_targetOf(direction));
  }

  // ------------------------------------------------------------ textures --

  Size _pixelSizeOf(bool spread) {
    final size = _pageSizeOf(spread);
    return Size(
      (size.width * _ratio).ceilToDouble(),
      (size.height * _ratio).ceilToDouble(),
    );
  }

  Object _keyOf(int page, bool spread) {
    final pixels = _pixelSizeOf(spread);
    return LibraryPageTextureKey(
      widget.contentKey,
      page,
      pixels.width.toInt(),
      pixels.height.toInt(),
    );
  }

  Set<Object> _keysOf(int index) {
    final face = _face(index);
    if (face == null || _size.isEmpty) return <Object>{};
    return <Object>{for (final page in face.pages) _keyOf(page, face.isSpread)};
  }

  Future<LibraryPageTexture?> _acquire(int page, bool spread) {
    final render = widget.render;
    final pixels = _pixelSizeOf(spread);
    final key = _keyOf(page, spread);
    return _cache.acquire(key, (cancel) async {
      ui.Image? image;
      try {
        image = await render(page, pixels, cancel);
      } finally {
        if (image == null && !cancel.isCancelled) _unrenderable.add(key);
      }
      return image;
    });
  }

  void _schedulePrefetch() {
    if (_prefetchScheduled) return;
    _prefetchScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) => _prefetch());
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  /// Renders the item on screen and its neighbours ahead of a turn.
  void _prefetch() {
    _prefetchScheduled = false;
    if (!mounted || !widget.enabled || _size.isEmpty) return;
    final current = widget.currentIndex;
    final wanted = <(int, bool)>[];
    final keys = <Object>{};
    for (final index in <int>[current, current + 1, current - 1]) {
      final face = _face(index);
      if (face == null) continue;
      for (final page in face.pages) {
        wanted.add((page, face.isSpread));
        keys.add(_keyOf(page, face.isSpread));
      }
    }
    _cache.retain(keys);
    // Pages that could not be rendered get another try.
    _unrenderable.clear();
    for (final (page, spread) in wanted) {
      if (!_cache.contains(_keyOf(page, spread))) {
        unawaited(_acquire(page, spread));
      }
    }
  }

  void _onDisabled() {
    _releaseTurn();
    _cache.retain(const <Object>{});
    _ownCache?.purge();
  }

  void _onController() {
    final direction = _controller.direction;
    if (direction == null) {
      _releaseTurn();
      return;
    }
    final turn = _turn;
    if (turn == null || turn.direction != direction) _startTurn(direction);
  }

  void _startTurn(LibraryPageTurnDirection direction) {
    _releaseTurn();
    final current = _face(widget.currentIndex);
    final target = _face(_targetOf(direction));
    if (current == null || target == null) return;
    final spread = current.isSpread;
    final liftsRight = LibraryPageCurlGeometry.liftsRightEdge(
      direction,
      widget.rightToLeft,
    );
    final frontPage = current.pageOn(right: liftsRight);
    final underPage = target.pageOn(right: liftsRight);
    final backPage = spread ? target.pageOn(right: !liftsRight) : null;
    final turn = _CurlTurn(direction: direction, spread: spread);
    _turn = turn;
    void fill(int? page, void Function(ui.Image image) set) {
      if (page == null) return;
      // Usually rendered ahead by _prefetch: drawn from the first frame.
      final cached = _cache.peek(_keyOf(page, spread));
      if (cached != null) {
        set(cached.image.clone());
        return;
      }
      unawaited(
        _acquire(page, spread).then((texture) {
          if (turn.released || texture == null || texture.isDisposed) return;
          set(texture.image.clone());
          if (mounted) setState(() {});
        }),
      );
    }

    fill(frontPage, (image) => turn.front = image);
    fill(backPage, (image) => turn.back = image);
    fill(underPage, (image) => turn.under = image);
  }

  /// Releases the images of the turn after the frame that stops drawing it.
  void _releaseTurn() {
    final turn = _turn;
    if (turn == null) return;
    _turn = null;
    turn.released = true;
    if (!mounted) {
      turn.dispose();
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) => turn.dispose());
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  // ---------------------------------------------------------------- build --

  bool _acceptsDrag(double dx) {
    // A running turn keeps every horizontal drag (no PageView scroll under
    // it).
    if (_controller.isActive) return true;
    return canCurl(
      LibraryPageCurlController.directionOfDrag(
        dx,
        rightToLeft: widget.rightToLeft,
      ),
    );
  }

  void _onDragStart(DragStartDetails details) =>
      _controller.beginDrag(details.localPosition);

  void _onDragUpdate(DragUpdateDetails details) =>
      _controller.updateDrag(details.localPosition);

  void _onDragEnd(DragEndDetails details) =>
      unawaited(_controller.endDrag(details.velocity));

  void _onDragCancel() => unawaited(_controller.cancelDrag());

  void _onLayout(Size constraint) {
    final size = constraint.isFinite ? constraint : Size.zero;
    if (size == _size) return;
    final hadSize = !_size.isEmpty;
    _size = size;
    if (hadSize && _controller.isActive) {
      // Rotation: the turn no longer matches the pages.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _controller.reset();
      });
    }
    _schedulePrefetch();
  }

  Widget _buildCurl(BuildContext context) {
    final direction = _controller.direction;
    final turn = _turn;
    final front = turn?.front;
    if (direction == null || turn == null || front == null) {
      return const SizedBox.expand();
    }
    return LibraryPageCurl(
      front: front,
      back: turn.back,
      under: turn.under,
      rightToLeft: widget.rightToLeft,
      direction: direction,
      progress: _controller.progress,
      corner: _controller.corner,
      spread: turn.spread,
      paperColor: widget.paperColor,
      program: _program,
    );
  }

  @override
  Widget build(BuildContext context) {
    final Widget overlay;
    if (widget.enabled) {
      overlay = RawGestureDetector(
        key: const ValueKey<String>('library-page-curl-gestures'),
        behavior: HitTestBehavior.translucent,
        excludeFromSemantics: true,
        gestures: <Type, GestureRecognizerFactory>{
          _LibraryPageCurlDragRecognizer:
              GestureRecognizerFactoryWithHandlers<
                _LibraryPageCurlDragRecognizer
              >(() => _LibraryPageCurlDragRecognizer(debugOwner: this), (
                recognizer,
              ) {
                recognizer
                  ..dragStartBehavior = DragStartBehavior.down
                  ..canAccept = _acceptsDrag
                  ..onStart = _onDragStart
                  ..onUpdate = _onDragUpdate
                  ..onEnd = _onDragEnd
                  ..onCancel = _onDragCancel;
              }),
        },
        child: IgnorePointer(
          child: LayoutBuilder(
            builder: (context, constraints) {
              _onLayout(constraints.biggest);
              // The curl repaints every frame of a turn: keep it off the
              // PageView's layer.
              return RepaintBoundary(
                child: ListenableBuilder(
                  listenable: _controller,
                  builder: (context, _) => _buildCurl(context),
                ),
              );
            },
          ),
        ),
      );
    } else {
      overlay = const IgnorePointer(
        key: ValueKey<String>('library-page-curl-disabled'),
        child: SizedBox.expand(),
      );
    }
    final child = widget.child;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        if (child != null)
          KeyedSubtree(key: const ValueKey<String>('child'), child: child),
        overlay,
      ],
    );
  }
}
