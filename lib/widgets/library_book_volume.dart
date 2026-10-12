import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:neostation/services/library_local_models.dart'
    show LibraryBookFormat;

/// Thickness of a book volume, as a fraction of the width of its front cover
/// (`docs/library-books-3d-plan.md`, § 3.1, decisions Q14 and Q15).
abstract final class LibraryBookThickness {
  /// Thinnest volume: [minimumPages] pages or fewer.
  static const double minimum = 0.035;

  /// Thickest volume: [maximumPages] pages or more.
  static const double maximum = 0.22;

  /// Titles whose length is unknown, such as online catalogue entries.
  static const double fixed = 0.09;

  static const int minimumPages = 40;
  static const int maximumPages = 1200;

  /// Pages assumed for a CBZ or PDF whose page count is unknown.
  static const int defaultPageCount = 120;

  /// File bytes per estimated page of an EPUB or TXT book (Q14).
  static const int bytesPerPage = 1800;

  /// Bounded page estimate: the page count of a CBZ or PDF
  /// ([defaultPageCount] when unknown), the file size of an EPUB or TXT
  /// divided by [bytesPerPage]; always within [minimumPages] and
  /// [maximumPages].
  static int estimatePages({
    required LibraryBookFormat format,
    int? pageCount,
    required int sizeBytes,
  }) {
    final pages = switch (format) {
      LibraryBookFormat.cbz ||
      LibraryBookFormat.pdf => pageCount ?? defaultPageCount,
      LibraryBookFormat.epub ||
      LibraryBookFormat.txt => sizeBytes ~/ bytesPerPage,
    };
    return pages.clamp(minimumPages, maximumPages);
  }

  /// Thickness of a book of [pages] pages: [minimum] at [minimumPages],
  /// [maximum] at [maximumPages], linear in between.
  static double of(int pages) {
    final bounded = pages.clamp(minimumPages, maximumPages);
    final t = (bounded - minimumPages) / (maximumPages - minimumPages);
    return minimum + (maximum - minimum) * t;
  }

  /// [of] the [estimatePages] of a book, or [fixed] when an EPUB or TXT book
  /// has no known [sizeBytes] (nothing to estimate from).
  static double estimate({
    required LibraryBookFormat format,
    int? pageCount,
    int? sizeBytes,
  }) {
    final bytes = sizeBytes;
    final needsSize =
        format == LibraryBookFormat.epub || format == LibraryBookFormat.txt;
    if (needsSize && bytes == null) return fixed;
    return of(
      estimatePages(
        format: format,
        pageCount: pageCount,
        sizeBytes: bytes ?? 0,
      ),
    );
  }
}

/// A point or a direction of a book volume, in logical pixels: x to the
/// right, y down and z away from the viewer, the front cover at z = 0.
///
/// `vector_math` is only a transitive dependency of Flutter (which re-exports
/// its `Matrix4` alone), so the volume uses this small value type instead of
/// a new dependency.
@immutable
class LibraryBookVector3 {
  const LibraryBookVector3(this.x, this.y, this.z);

  final double x;
  final double y;
  final double z;

  LibraryBookVector3 operator *(double factor) =>
      LibraryBookVector3(x * factor, y * factor, z * factor);

  double dot(LibraryBookVector3 other) =>
      x * other.x + y * other.y + z * other.z;

  double get length => math.sqrt(dot(this));

  /// This direction with a length of 1 (unchanged when it has no length).
  LibraryBookVector3 normalized() {
    final size = length;
    return size == 0 ? this : this * (1 / size);
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryBookVector3 &&
      other.x == x &&
      other.y == y &&
      other.z == z;

  @override
  int get hashCode => Object.hash(x, y, z);

  @override
  String toString() => 'LibraryBookVector3($x, $y, $z)';
}

/// The six faces of a closed book. [spine] is the hinge side, [foreEdge] the
/// opposite page edge, [head] the top edge and [tail] the bottom edge.
enum LibraryBookFaceKind { front, back, spine, foreEdge, head, tail }

/// One projected face of a book volume.
@immutable
class LibraryBookFace {
  const LibraryBookFace({
    required this.kind,
    required this.points,
    required this.facing,
    required this.light,
  });

  final LibraryBookFaceKind kind;

  /// Projected corners, clockwise on screen when the face is [facing].
  final List<Offset> points;

  /// Whether the face is turned towards the viewer (projected normal).
  final bool facing;

  /// Lambert intensity of the face, ambient light included (0 to 1).
  final double light;
}

/// The body of a book behind its front cover (Phase 2 of
/// `docs/library-books-3d-plan.md`): spine, page edges, back board and a
/// ground shadow, drawn by [LibraryBookVolumePainter] around [front].
///
/// The volume is decorative (excluded from semantics) and static: it has no
/// animation of its own and only repaints when one of its fields changes.
/// [front] keeps its own semantics, hit testing and transforms, and is laid
/// out in [LibraryBookVolumePainter.frontRect] of the available size.
class LibraryBookVolume extends StatelessWidget {
  const LibraryBookVolume({
    super.key,
    required this.opening,
    required this.thickness,
    required this.rightToLeft,
    required this.radius,
    this.image,
    this.spineColor,
    required this.front,
  });

  /// Opening of the front cover, from 0 (closed) to 1 (open): the volume
  /// itself stays still, only its ground shadow deepens.
  final double opening;

  /// Depth of the book as a fraction of the front width
  /// ([LibraryBookThickness]).
  final double thickness;

  /// Hinge (and spine) on the right, as for manga.
  final bool rightToLeft;

  /// Corner radius of the front cover.
  final double radius;

  /// Decoded cover image, whose hinge-side band is drawn on the spine;
  /// [spineColor] is used without it.
  final ui.Image? image;

  /// Spine colour without [image] (default [defaultSpineColor]).
  final Color? spineColor;

  /// The front cover.
  final Widget front;

  /// Book cloth used for the spine when there is no cover image.
  static const Color defaultSpineColor = Color(0xFF6E5C49);

  /// Size used when the constraints are unbounded.
  static const Size _fallbackSize = Size(120, 176);

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final box = constraints.hasBoundedWidth && constraints.hasBoundedHeight
            ? constraints.biggest
            : constraints.constrain(_fallbackSize);
        final face = LibraryBookVolumePainter.frontRect(
          box,
          thickness: thickness,
          rightToLeft: rightToLeft,
        );
        return SizedBox.fromSize(
          size: box,
          child: Stack(
            // Not directional: the hinge side is [rightToLeft], whatever the
            // ambient text direction.
            alignment: Alignment.topLeft,
            fit: StackFit.expand,
            children: <Widget>[
              ExcludeSemantics(
                child: CustomPaint(
                  painter: LibraryBookVolumePainter(
                    opening: opening,
                    thickness: thickness,
                    rightToLeft: rightToLeft,
                    radius: radius,
                    image: image,
                    spineColor: spineColor ?? defaultSpineColor,
                  ),
                ),
              ),
              Positioned.fromRect(rect: face, child: front),
            ],
          ),
        );
      },
    );
  }
}

/// Paints a closed book seen slightly from above and from its hinge side.
///
/// The eight corners of the book are projected with an off-axis perspective
/// whose picture plane is the front cover ([project]): the front face keeps
/// exactly its rectangle (the 443 cover drawn above it is untouched) while
/// the deeper corners recede towards the eye, which reveals the spine on the
/// hinge side and the head of the pages. Faces are painted back to front
/// ([sortedFaces]), each lit by a Lambert term of its normal in the viewer's
/// frame. Each side face is drawn as the extrusion of its side of the
/// cover's rounded outline, so the volume keeps the rounded corners.
///
/// Painting allocates no image: the spine samples the cover image already
/// decoded for the front face, through a short-lived [ui.ImageShader].
class LibraryBookVolumePainter extends CustomPainter {
  const LibraryBookVolumePainter({
    required this.opening,
    required this.thickness,
    required this.rightToLeft,
    required this.radius,
    this.image,
    this.spineColor = LibraryBookVolume.defaultSpineColor,
  });

  final double opening;
  final double thickness;
  final bool rightToLeft;
  final double radius;
  final ui.Image? image;
  final Color spineColor;

  /// Sideways view angle (radians) towards the hinge side: shows the spine.
  /// Positive: hinge and eye on the left; negative: on the right.
  static const double viewTilt = 0.42;

  /// Downward view angle (radians): shows the head of the pages.
  static const double viewPitch = 0.2;

  /// Eye distance, as a multiple of the longest side of the front face.
  static const double focalFactor = 2.4;

  /// Light received by a face turned away from the light.
  static const double ambient = 0.55;

  /// Margins of the 443 cover around its front face: hinge side, top,
  /// fore-edge side and bottom (the last two keep room for the shadow).
  static const double hingeMargin = 1;
  static const double topMargin = 2;
  static const double foreMargin = 5;
  static const double bottomMargin = 5;

  static const Color _board = Color(0xFFDACDB8);
  static const Color _paper = Color(0xFFF4EEE2);
  static const Color _paperStroke = Color(0xFFC8BEAB);
  static final Float64List _identity = Matrix4.identity().storage;

  /// Each face: its outward normal and its corner indices (see [corners]),
  /// clockwise when the face is seen from outside.
  static const List<_FaceDefinition> _faces = <_FaceDefinition>[
    _FaceDefinition(_Side.back, LibraryBookVector3(0, 0, 1), (4, 6, 7, 5)),
    _FaceDefinition(_Side.left, LibraryBookVector3(-1, 0, 0), (4, 0, 2, 6)),
    _FaceDefinition(_Side.right, LibraryBookVector3(1, 0, 0), (1, 5, 7, 3)),
    _FaceDefinition(_Side.top, LibraryBookVector3(0, -1, 0), (1, 0, 4, 5)),
    _FaceDefinition(_Side.bottom, LibraryBookVector3(0, 1, 0), (2, 3, 7, 6)),
    _FaceDefinition(_Side.front, LibraryBookVector3(0, 0, -1), (0, 1, 3, 2)),
  ];

  /// The front face inside a [box]: the 443 margins plus the room taken by
  /// the spine (hinge side) and the head of the pages (top) of a book of
  /// [thickness].
  static Rect frontRect(
    Size box, {
    required double thickness,
    required bool rightToLeft,
  }) {
    final depthRatio = thickness.clamp(0.0, 1.0).toDouble();
    final spine = depthRatio * math.tan(viewTilt);
    final head = depthRatio * math.tan(viewPitch);
    final width = math.max(
      1.0,
      (box.width - hingeMargin - foreMargin) / (1 + spine),
    );
    // Upper bounds of the projected spine and head (the perspective only
    // shortens them).
    final spineWidth = width * spine;
    final headHeight = width * head;
    final height = math.max(
      1.0,
      box.height - topMargin - bottomMargin - headHeight,
    );
    final left = rightToLeft ? foreMargin : hingeMargin + spineWidth;
    return Rect.fromLTWH(left, topMargin + headHeight, width, height);
  }

  /// The eight corners of a closed book with a front face of [size] and a
  /// [depth]: bit 0 of the index is the right side (x = width), bit 1 the
  /// bottom (y = height) and bit 2 the back (z = depth).
  static List<LibraryBookVector3> corners(Size size, double depth) =>
      List<LibraryBookVector3>.unmodifiable(<LibraryBookVector3>[
        for (var index = 0; index < 8; index++)
          LibraryBookVector3(
            index & 1 == 0 ? 0 : size.width,
            index & 2 == 0 ? 0 : size.height,
            index & 4 == 0 ? 0 : depth,
          ),
      ]);

  /// Projects [corners] (coordinates of a front face of [size]) on the plane
  /// of the front face, seen from an eye turned by [tilt] towards the hinge
  /// side and by [pitch] above the book.
  ///
  /// Points at z = 0 keep their position; deeper points move towards the
  /// foot of the eye. Pure: same inputs, same result; nothing is modified.
  static List<Offset> project(
    List<LibraryBookVector3> corners,
    Size size,
    double tilt, {
    double pitch = viewPitch,
  }) {
    final focal = math.max(1.0, focalFactor * size.longestSide);
    final hingeX = tilt >= 0 ? 0.0 : size.width;
    final eyeX = hingeX - focal * math.tan(tilt);
    final eyeY = -focal * math.tan(pitch);
    return List<Offset>.unmodifiable(<Offset>[
      for (final point in corners) _projectPoint(point, eyeX, eyeY, focal),
    ]);
  }

  static Offset _projectPoint(
    LibraryBookVector3 point,
    double eyeX,
    double eyeY,
    double focal,
  ) {
    // Share of the way towards the foot of the eye: exactly 0 on the
    // picture plane, so the front face keeps its rectangle exactly.
    final toEye = point.z / math.max(1e-6, focal + point.z);
    return Offset(
      point.x + (eyeX - point.x) * toEye,
      point.y + (eyeY - point.y) * toEye,
    );
  }

  /// The six faces of the [projected] [corners], back to front: faces turned
  /// away from the viewer first (the back board deepest), then the visible
  /// ones, the front face last. [tilt] gives the hinge side (positive: left)
  /// and, with [pitch], the viewer's frame of the Lambert lighting, whose
  /// light comes from above the fore-edge side. Pure.
  static List<LibraryBookFace> sortedFaces(
    List<Offset> projected,
    double tilt, {
    double pitch = viewPitch,
  }) {
    assert(projected.length == 8, 'eight projected corners expected');
    final hingeLeft = tilt >= 0;
    final light = LibraryBookVector3(
      hingeLeft ? 0.35 : -0.35,
      -0.55,
      -0.76,
    ).normalized();
    final entries = <(int, int, LibraryBookFace)>[];
    for (var index = 0; index < _faces.length; index++) {
      final definition = _faces[index];
      final (a, b, c, d) = definition.corners;
      final points = List<Offset>.unmodifiable(<Offset>[
        projected[a],
        projected[b],
        projected[c],
        projected[d],
      ]);
      final kind = switch (definition.side) {
        _Side.front => LibraryBookFaceKind.front,
        _Side.back => LibraryBookFaceKind.back,
        _Side.left =>
          hingeLeft ? LibraryBookFaceKind.spine : LibraryBookFaceKind.foreEdge,
        _Side.right =>
          hingeLeft ? LibraryBookFaceKind.foreEdge : LibraryBookFaceKind.spine,
        _Side.top => LibraryBookFaceKind.head,
        _Side.bottom => LibraryBookFaceKind.tail,
      };
      final normal = _toViewer(definition.normal, tilt, pitch);
      final lambert = math.max(0.0, normal.dot(light));
      final face = LibraryBookFace(
        kind: kind,
        points: points,
        facing: _signedArea(points) > 1e-6,
        light: ambient + (1 - ambient) * lambert,
      );
      final depthRank = switch (definition.side) {
        _Side.back => 0,
        _Side.front => 2,
        _ => 1,
      };
      entries.add((face.facing ? 1 : 0, depthRank * 10 + index, face));
    }
    entries.sort((a, b) {
      final facing = a.$1.compareTo(b.$1);
      return facing != 0 ? facing : a.$2.compareTo(b.$2);
    });
    return List<LibraryBookFace>.unmodifiable(<LibraryBookFace>[
      for (final entry in entries) entry.$3,
    ]);
  }

  /// [normal] in the viewer's frame: turned by [tilt] around the vertical
  /// axis, then by [pitch] around the horizontal one.
  static LibraryBookVector3 _toViewer(
    LibraryBookVector3 normal,
    double tilt,
    double pitch,
  ) {
    final cosTilt = math.cos(tilt);
    final sinTilt = math.sin(tilt);
    final x = normal.x * cosTilt - normal.z * sinTilt;
    final z = normal.x * sinTilt + normal.z * cosTilt;
    final cosPitch = math.cos(pitch);
    final sinPitch = math.sin(pitch);
    return LibraryBookVector3(
      x,
      normal.y * cosPitch - z * sinPitch,
      normal.y * sinPitch + z * cosPitch,
    );
  }

  /// Shoelace area: positive for a polygon drawn clockwise on screen.
  static double _signedArea(List<Offset> points) {
    var twice = 0.0;
    for (var index = 0; index < points.length; index++) {
      final a = points[index];
      final b = points[(index + 1) % points.length];
      twice += a.dx * b.dy - b.dx * a.dy;
    }
    return twice / 2;
  }

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;
    final front = frontRect(
      size,
      thickness: thickness,
      rightToLeft: rightToLeft,
    );
    final depth = math.max(0.0, thickness) * front.width;
    final tilt = rightToLeft ? -viewTilt : viewTilt;
    final projected = project(corners(front.size, depth), front.size, tilt);
    final faces = sortedFaces(projected, tilt);
    final body = _BookBody(front.size, depth, tilt, radius);

    canvas.save();
    canvas.translate(front.left, front.top);
    _paintShadow(canvas, projected);
    for (final face in faces) {
      if (face.facing) break;
      _paintFace(canvas, face, body);
    }
    // Inside of the boards, seen around the pages while the cover opens.
    canvas.drawRRect(
      RRect.fromRectAndRadius(
        Offset.zero & front.size,
        Radius.circular(body.radius),
      ),
      Paint()..color = _board,
    );
    for (final face in faces) {
      if (face.facing && face.kind != LibraryBookFaceKind.front) {
        _paintFace(canvas, face, body);
      }
    }
    canvas.restore();
  }

  void _paintShadow(Canvas canvas, List<Offset> projected) {
    // The book stands on its tail; the light comes from above the fore-edge.
    final offset = Offset(rightToLeft ? 1 : -1, 2.5);
    final footprint = <Offset>[
      for (final corner in const <int>[2, 3, 7, 6]) projected[corner] + offset,
    ];
    canvas.drawPath(
      Path()..addPolygon(footprint, true),
      Paint()
        ..color = Color.fromRGBO(0, 0, 0, 0.26 + 0.08 * opening)
        ..maskFilter = MaskFilter.blur(
          BlurStyle.normal,
          Shadow.convertRadiusToSigma(4 + 2 * opening),
        ),
    );
  }

  void _paintFace(Canvas canvas, LibraryBookFace face, _BookBody body) {
    switch (face.kind) {
      case LibraryBookFaceKind.front:
        // The cover widget is the front face.
        return;
      case LibraryBookFaceKind.back:
        canvas.drawRRect(
          body.backRRect(),
          Paint()..color = _lit(_board, face.light),
        );
      case LibraryBookFaceKind.spine:
        _paintSpine(canvas, face, body);
      case LibraryBookFaceKind.head:
      case LibraryBookFaceKind.tail:
      case LibraryBookFaceKind.foreEdge:
        final side = body.sideOf(face.kind);
        canvas.drawPath(
          body.strip(side),
          Paint()..color = _lit(_paper, face.light),
        );
        if (face.facing && face.kind == LibraryBookFaceKind.head) {
          // Three strokes along the head of the pages suggest the sheets.
          final stroke = Paint()
            ..color = _lit(_paperStroke, face.light)
            ..strokeWidth = 0.5
            ..style = PaintingStyle.stroke;
          for (var line = 1; line <= 3; line++) {
            final ends = body.straight(side, z: body.depth * line / 4);
            canvas.drawLine(ends[0], ends[1], stroke);
          }
        }
    }
  }

  void _paintSpine(Canvas canvas, LibraryBookFace face, _BookBody body) {
    final side = body.sideOf(LibraryBookFaceKind.spine);
    final cover = image;
    if (cover == null ||
        cover.width <= 0 ||
        cover.height <= 0 ||
        body.depth <= 0) {
      canvas.drawPath(
        body.strip(side),
        Paint()..color = _lit(spineColor, face.light),
      );
    } else {
      _paintSpineImage(canvas, cover, face.light, body, side);
    }
    // Groove of the hinge, just behind the front board.
    final groove = body.straight(side, z: body.depth * 0.12);
    canvas.drawLine(
      groove[0],
      groove[1],
      Paint()
        ..color = const Color(0x2E000000)
        ..strokeWidth = 0.8,
    );
  }

  /// The hinge-side band of the visible part of [cover] (fitted as the front
  /// face shows it, `BoxFit.cover`) folded onto the spine: a mesh along the
  /// rounded outline keeps the band continuous with the cover's edge and
  /// straight under the perspective.
  void _paintSpineImage(
    Canvas canvas,
    ui.Image cover,
    double light,
    _BookBody body,
    _Side side,
  ) {
    const columns = 2;
    final size = body.size;
    final imageSize = Size(cover.width.toDouble(), cover.height.toDouble());
    final fitted = applyBoxFit(BoxFit.cover, imageSize, size);
    final source = Alignment.center.inscribe(
      fitted.source,
      Offset.zero & imageSize,
    );
    final scaleX = source.width / size.width;
    final scaleY = source.height / size.height;
    final band = math.min(body.depth * scaleX, source.width * 0.3);
    final inward = body.tilt >= 0 ? 1.0 : -1.0;
    final outline = body.flatOutline(side, divisions: _BookBody.spineDivisions);
    final layers = <List<Offset>>[
      for (var column = 0; column <= columns; column++)
        column == 0
            ? body.flatOutline(
                side,
                divisions: _BookBody.spineDivisions,
                inset: _BookBody.overlap,
              )
            : body.projectFlat(outline, body.depth * column / columns),
    ];
    final rows = outline.length;
    final positions = <Offset>[];
    final texture = <Offset>[];
    for (var row = 0; row < rows; row++) {
      final point = outline[row];
      final edgeU = source.left + point.dx * scaleX;
      final v = source.top + point.dy * scaleY;
      for (var column = 0; column <= columns; column++) {
        positions.add(layers[column][row]);
        final u = edgeU + inward * band * column / columns;
        texture.add(Offset(u.clamp(source.left, source.right), v));
      }
    }
    final indices = <int>[];
    for (var row = 0; row + 1 < rows; row++) {
      for (var column = 0; column < columns; column++) {
        final a = row * (columns + 1) + column;
        final b = a + columns + 1;
        indices.addAll(<int>[a, a + 1, b, a + 1, b + 1, b]);
      }
    }
    final vertices = ui.Vertices(
      ui.VertexMode.triangles,
      positions,
      textureCoordinates: texture,
      indices: indices,
    );
    final shader = ui.ImageShader(
      cover,
      TileMode.clamp,
      TileMode.clamp,
      _identity,
      filterQuality: FilterQuality.low,
    );
    canvas.drawVertices(
      vertices,
      BlendMode.srcOver,
      Paint()
        ..shader = shader
        ..colorFilter = ColorFilter.mode(
          Color.from(alpha: 1, red: light, green: light, blue: light),
          BlendMode.modulate,
        ),
    );
    // The recorded picture keeps what it needs.
    shader.dispose();
    vertices.dispose();
  }

  static Color _lit(Color color, double light) => Color.from(
    alpha: color.a,
    red: (color.r * light).clamp(0.0, 1.0),
    green: (color.g * light).clamp(0.0, 1.0),
    blue: (color.b * light).clamp(0.0, 1.0),
  );

  @override
  bool shouldRepaint(covariant LibraryBookVolumePainter oldDelegate) =>
      oldDelegate.opening != opening ||
      oldDelegate.thickness != thickness ||
      oldDelegate.rightToLeft != rightToLeft ||
      oldDelegate.radius != radius ||
      !identical(oldDelegate.image, image) ||
      oldDelegate.spineColor != spineColor;
}

enum _Side { front, back, left, right, top, bottom }

class _FaceDefinition {
  const _FaceDefinition(this.side, this.normal, this.corners);

  final _Side side;
  final LibraryBookVector3 normal;
  final (int, int, int, int) corners;
}

/// Rounded body of a book: each side face is the extrusion of one side of
/// the rounded outline of the front face, from the middle of one corner to
/// the middle of the next, so the volume keeps the corners of the cover.
class _BookBody {
  _BookBody(this.size, this.depth, this.tilt, double radius)
    : radius = radius.clamp(0.0, size.shortestSide / 2).toDouble();

  /// Points along the straight part of the spine, for its image mesh.
  static const int spineDivisions = 7;

  /// The sides start this far under the front cover, so that its
  /// anti-aliased edge blends with the book rather than with the background.
  static const double overlap = 0.75;

  /// Steps of each half corner arc.
  static const int _arcSteps = 3;

  final Size size;
  final double depth;
  final double tilt;
  final double radius;

  _Side sideOf(LibraryBookFaceKind kind) => switch (kind) {
    LibraryBookFaceKind.spine => tilt >= 0 ? _Side.left : _Side.right,
    LibraryBookFaceKind.foreEdge => tilt >= 0 ? _Side.right : _Side.left,
    LibraryBookFaceKind.head => _Side.top,
    LibraryBookFaceKind.tail => _Side.bottom,
    LibraryBookFaceKind.front => _Side.front,
    LibraryBookFaceKind.back => _Side.back,
  };

  /// One side of the rounded outline of the front face (z = 0), moved
  /// [inset] towards the inside, with [divisions] extra points along its
  /// straight part. Every call with the same [divisions] returns
  /// corresponding points.
  List<Offset> flatOutline(_Side side, {int divisions = 0, double inset = 0}) {
    final rect = (Offset.zero & size).deflate(inset);
    final r = math.max(0.0, radius - inset);
    const quarter = math.pi / 4;
    final (Offset, double, double) first;
    final (Offset, double, double) second;
    switch (side) {
      case _Side.left:
        first = (Offset(rect.left + r, rect.top + r), 5 * quarter, 4 * quarter);
        second = (
          Offset(rect.left + r, rect.bottom - r),
          4 * quarter,
          3 * quarter,
        );
      case _Side.top:
        first = (Offset(rect.left + r, rect.top + r), 5 * quarter, 6 * quarter);
        second = (
          Offset(rect.right - r, rect.top + r),
          6 * quarter,
          7 * quarter,
        );
      case _Side.right:
        first = (
          Offset(rect.right - r, rect.top + r),
          7 * quarter,
          8 * quarter,
        );
        second = (Offset(rect.right - r, rect.bottom - r), 0, quarter);
      case _Side.bottom:
        first = (Offset(rect.right - r, rect.bottom - r), quarter, 2 * quarter);
        second = (
          Offset(rect.left + r, rect.bottom - r),
          2 * quarter,
          3 * quarter,
        );
      case _Side.front:
      case _Side.back:
        return const <Offset>[];
    }
    final points = <Offset>[];
    void arc((Offset, double, double) corner) {
      final (center, start, end) = corner;
      for (var step = 0; step <= _arcSteps; step++) {
        final angle = start + (end - start) * step / _arcSteps;
        points.add(center + Offset(math.cos(angle), math.sin(angle)) * r);
      }
    }

    arc(first);
    final from = points.last;
    final (center, start, _) = second;
    final to = center + Offset(math.cos(start), math.sin(start)) * r;
    for (var step = 1; step <= divisions; step++) {
      points.add(Offset.lerp(from, to, step / (divisions + 1))!);
    }
    arc(second);
    return points;
  }

  /// [points] of the front plane moved back to depth [z], projected.
  List<Offset> projectFlat(List<Offset> points, double z) =>
      LibraryBookVolumePainter.project(
        <LibraryBookVector3>[
          for (final point in points) LibraryBookVector3(point.dx, point.dy, z),
        ],
        size,
        tilt,
      );

  /// One side of the outline at depth [z], projected.
  List<Offset> outline(_Side side, {required double z}) =>
      projectFlat(flatOutline(side), z);

  /// The two ends of the straight part of one side at depth [z], projected.
  List<Offset> straight(_Side side, {required double z}) {
    final r = radius;
    final width = size.width;
    final height = size.height;
    final ends = switch (side) {
      _Side.left => <Offset>[Offset(0, r), Offset(0, height - r)],
      _Side.right => <Offset>[Offset(width, r), Offset(width, height - r)],
      _Side.top => <Offset>[Offset(r, 0), Offset(width - r, 0)],
      _Side.bottom => <Offset>[Offset(r, height), Offset(width - r, height)],
      _Side.front || _Side.back => <Offset>[Offset.zero, Offset.zero],
    };
    return projectFlat(ends, z);
  }

  /// The side face of [side], from just under the front cover to the back.
  Path strip(_Side side) {
    final front = flatOutline(side, inset: overlap);
    final back = outline(side, z: depth);
    return Path()..addPolygon(<Offset>[...front, ...back.reversed], true);
  }

  /// The back board, projected: a rectangle scaled towards the eye.
  RRect backRRect() {
    final corners = projectFlat(<Offset>[
      Offset.zero,
      Offset(size.width, size.height),
    ], depth);
    final rect = Rect.fromPoints(corners[0], corners[1]);
    final scale = size.width > 0 ? rect.width / size.width : 1.0;
    return RRect.fromRectAndRadius(rect, Radius.circular(radius * scale));
  }
}
