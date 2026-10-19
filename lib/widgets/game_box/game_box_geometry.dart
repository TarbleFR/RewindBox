import 'dart:math' as math;
import 'dart:ui' show Offset, Rect, Size;

import 'package:flutter/widgets.dart' show Matrix4;

import 'package:neostation/services/game_box/game_box_profile.dart';

/// A small 3D vector (millimetres or logical pixels).
///
/// Flutter only re-exports `Matrix4` from vector_math; the scene keeps its
/// own value type (as `LibraryBookVolume` does) instead of depending on the
/// transitive package directly.
class BoxV3 {
  const BoxV3(this.x, this.y, this.z);
  final double x;
  final double y;
  final double z;

  static const zero = BoxV3(0, 0, 0);

  BoxV3 operator +(BoxV3 o) => BoxV3(x + o.x, y + o.y, z + o.z);
  BoxV3 operator -(BoxV3 o) => BoxV3(x - o.x, y - o.y, z - o.z);
  BoxV3 operator *(double k) => BoxV3(x * k, y * k, z * k);
  double dot(BoxV3 o) => x * o.x + y * o.y + z * o.z;
  BoxV3 cross(BoxV3 o) =>
      BoxV3(y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x);
  double get length => math.sqrt(dot(this));
  BoxV3 get normalized {
    final l = length;
    return l == 0 ? this : this * (1 / l);
  }

  @override
  String toString() => 'BoxV3(${x.toStringAsFixed(3)}, '
      '${y.toStringAsFixed(3)}, ${z.toStringAsFixed(3)})';
}

/// A 3×3 rotation, row-major.
class BoxM3 {
  const BoxM3(this.m);
  final List<double> m;

  static const identity = BoxM3([1, 0, 0, 0, 1, 0, 0, 0, 1]);

  /// Right-handed rotation about +x (screen coordinates: x right, y down,
  /// z away from the viewer). A positive angle shows the top face.
  static BoxM3 rotationX(double a) {
    final c = math.cos(a), s = math.sin(a);
    return BoxM3([1, 0, 0, 0, c, -s, 0, s, c]);
  }

  /// Right-handed rotation about +y. A negative angle brings the left face
  /// (the spine) toward the viewer.
  static BoxM3 rotationY(double a) {
    final c = math.cos(a), s = math.sin(a);
    return BoxM3([c, 0, s, 0, 1, 0, -s, 0, c]);
  }

  BoxV3 apply(BoxV3 v) => BoxV3(
        m[0] * v.x + m[1] * v.y + m[2] * v.z,
        m[3] * v.x + m[4] * v.y + m[5] * v.z,
        m[6] * v.x + m[7] * v.y + m[8] * v.z,
      );

  BoxM3 operator *(BoxM3 o) {
    final r = List<double>.filled(9, 0);
    for (var i = 0; i < 3; i++) {
      for (var j = 0; j < 3; j++) {
        var sum = 0.0;
        for (var k = 0; k < 3; k++) {
          sum += m[i * 3 + k] * o.m[k * 3 + j];
        }
        r[i * 3 + j] = sum;
      }
    }
    return BoxM3(r);
  }
}

/// A rotation followed by a translation.
class BoxRigid {
  const BoxRigid(this.rotation, this.translation);
  final BoxM3 rotation;
  final BoxV3 translation;

  static const identity = BoxRigid(BoxM3.identity, BoxV3.zero);

  BoxV3 apply(BoxV3 p) => rotation.apply(p) + translation;
  BoxV3 applyVector(BoxV3 v) => rotation.apply(v);

  /// `this ∘ other`: apply [other] first.
  BoxRigid compose(BoxRigid other) => BoxRigid(
        rotation * other.rotation,
        rotation.apply(other.translation) + translation,
      );

  /// Rotation by [rotation] around the line through [pivot].
  static BoxRigid about(BoxV3 pivot, BoxM3 rotation) =>
      BoxRigid(rotation, pivot - rotation.apply(pivot));

  static BoxRigid translate(BoxV3 t) => BoxRigid(BoxM3.identity, t);
}

/// What a face shows. The widget layer turns it into an image region or a
/// neutral surface (docs/game-box-3d.md § 4).
enum BoxSurface {
  front,
  back,
  spine,

  /// Opening side of a jewel case: the other spine of the back inlay.
  spineRight,
  top,
  bottom,
  edge,
  interior,
  lidInner,
  supportFront,
  supportBack,
  supportEdge,
}

/// A flat rectangle of the model, in millimetres.
///
/// Local face coordinates run from the top-left corner along [u] (right)
/// and [v] (down); the outward normal is `v × u`.
class BoxFace {
  const BoxFace({
    required this.id,
    required this.surface,
    required this.origin,
    required this.u,
    required this.v,
    required this.width,
    required this.height,
    this.source = const Rect.fromLTWH(0, 0, 1, 1),
    this.cornerRadius = 0,
  });

  final String id;
  final BoxSurface surface;
  final BoxV3 origin;
  final BoxV3 u;
  final BoxV3 v;
  final double width;
  final double height;

  /// The part of the surface's image shown on this face (fractions). The
  /// spine is split between the opening panel and the body of the box.
  final Rect source;

  /// Rounded corners of a front or back face (mm), clipped when painted.
  final double cornerRadius;

  BoxV3 get normal => v.cross(u).normalized;
  BoxV3 get center => origin + u * (width / 2) + v * (height / 2);
}

/// A group of faces moved together (the body, the lid, the support).
class BoxPart {
  const BoxPart({
    required this.id,
    required this.faces,
    this.transform = BoxRigid.identity,
    this.layer = 0,
    this.cull = true,
  });

  final String id;
  final List<BoxFace> faces;
  final BoxRigid transform;

  /// Parts are painted in layer order; faces of one part are depth sorted.
  final int layer;

  /// Flat supports drawn on the tray face the viewer in every opening pose
  /// and keep both sides.
  final bool cull;
}

/// Orientation of the model in front of the camera.
class BoxPose {
  const BoxPose({
    this.yaw = 0,
    this.pitch = 0,
    this.zoom = 1,
    this.panX = 0,
    this.panY = 0,
    this.perspective = 1,
  });

  /// Rotation about the vertical axis, radians. Free: the box turns 360°.
  final double yaw;

  /// Tilt about the horizontal axis, radians (bounded by the inspector).
  final double pitch;
  final double zoom;
  final double panX;
  final double panY;

  /// 1 = normal perspective, 0 = (almost) orthographic. The reading pose
  /// lowers it so the back is not distorted.
  final double perspective;

  /// Front face toward the viewer, slight top and spine.
  static const rest = BoxPose(yaw: -0.42, pitch: 0.12);
  static const front = BoxPose();
  static const back = BoxPose(yaw: math.pi, perspective: 0.15);

  static const maxPitch = 1.3;
  static const minZoom = 1.0;
  static const maxZoom = 4.0;

  BoxPose copyWith({
    double? yaw,
    double? pitch,
    double? zoom,
    double? panX,
    double? panY,
    double? perspective,
  }) =>
      BoxPose(
        yaw: yaw ?? this.yaw,
        pitch: pitch ?? this.pitch,
        zoom: zoom ?? this.zoom,
        panX: panX ?? this.panX,
        panY: panY ?? this.panY,
        perspective: perspective ?? this.perspective,
      );

  /// Interpolates toward [to]; the yaw takes the shortest way round.
  static BoxPose lerp(BoxPose from, BoxPose to, double t) {
    final dy = shortestAngle(from.yaw, to.yaw);
    double l(double a, double b) => a + (b - a) * t;
    return BoxPose(
      yaw: from.yaw + dy * t,
      pitch: l(from.pitch, to.pitch),
      zoom: l(from.zoom, to.zoom),
      panX: l(from.panX, to.panX),
      panY: l(from.panY, to.panY),
      perspective: l(from.perspective, to.perspective),
    );
  }

  /// Signed difference `to - from` wrapped into (-π, π].
  static double shortestAngle(double from, double to) {
    var d = (to - from) % (2 * math.pi);
    if (d > math.pi) d -= 2 * math.pi;
    if (d <= -math.pi) d += 2 * math.pi;
    return d;
  }

  BoxM3 get rotation => BoxM3.rotationX(pitch) * BoxM3.rotationY(yaw);

  @override
  String toString() =>
      'BoxPose(yaw: ${yaw.toStringAsFixed(3)}, pitch: ${pitch.toStringAsFixed(3)}, '
      'zoom: ${zoom.toStringAsFixed(2)})';
}

/// How far the box is open (0 = closed) and how far its support has come out.
class BoxOpening {
  const BoxOpening({this.lid = 0, this.support = 0});
  final double lid;
  final double support;
  static const closed = BoxOpening();
  bool get isClosed => lid <= 0 && support <= 0;
}

/// The model of one retail box: body, opening panel and support.
class GameBoxModel {
  GameBoxModel(this.profile);

  final GameBoxProfile profile;

  double get width => profile.width;
  double get height => profile.height;
  double get depth => profile.depth;

  /// Maximum opening angles (radians).
  static const double lidOpenAngle = 2.62; // ~150°: lies open on the left.
  static const double flapOpenAngle = 1.95; // ~112°: flap folded back.

  /// Faces of an axis-aligned box spanning [min]..[max] (mm), named with
  /// [prefix]. The spine is the left face; [leftSource] selects the part of
  /// the spine image it shows (x: 0 = back edge, 1 = front edge).
  ///
  /// With a [radius], the four corners of the front outline are rounded, as
  /// on plastic keep cases: the side faces stop short of the corners and each
  /// corner is approximated by [segments] narrow faces.
  static List<BoxFace> cuboid(
    String prefix,
    BoxV3 min,
    BoxV3 max, {
    BoxSurface front = BoxSurface.front,
    BoxSurface back = BoxSurface.back,
    BoxSurface left = BoxSurface.spine,
    BoxSurface right = BoxSurface.edge,
    BoxSurface top = BoxSurface.top,
    BoxSurface bottom = BoxSurface.bottom,
    Rect leftSource = const Rect.fromLTWH(0, 0, 1, 1),
    bool includeFront = true,
    bool includeTop = true,
    double radius = 0,
    int segments = 3,
  }) {
    final w = max.x - min.x, h = max.y - min.y, d = max.z - min.z;
    final r = radius.clamp(0.0, math.min(w, h) / 2).toDouble();
    const px = BoxV3(1, 0, 0), nx = BoxV3(-1, 0, 0);
    const py = BoxV3(0, 1, 0);
    const pz = BoxV3(0, 0, 1), nz = BoxV3(0, 0, -1);
    // The spine image covers the full height; the straight part of a rounded
    // spine shows the matching middle band.
    final spineSource = r == 0
        ? leftSource
        : Rect.fromLTRB(leftSource.left, r / h, leftSource.right, 1 - r / h);
    final faces = <BoxFace>[
      if (includeFront)
        BoxFace(
          id: '$prefix.front', surface: front,
          origin: BoxV3(min.x, min.y, min.z), u: px, v: py, width: w, height: h,
          cornerRadius: r,
        ),
      BoxFace(
        id: '$prefix.back', surface: back,
        origin: BoxV3(max.x, min.y, max.z), u: nx, v: py, width: w, height: h,
        cornerRadius: r,
      ),
      BoxFace(
        id: '$prefix.left', surface: left,
        origin: BoxV3(min.x, min.y + r, max.z), u: nz, v: py, width: d, height: h - 2 * r,
        source: spineSource,
      ),
      BoxFace(
        id: '$prefix.right', surface: right,
        origin: BoxV3(max.x, min.y + r, min.z), u: pz, v: py, width: d, height: h - 2 * r,
      ),
      if (includeTop)
        BoxFace(
          id: '$prefix.top', surface: top,
          origin: BoxV3(min.x + r, min.y, max.z), u: px, v: nz, width: w - 2 * r, height: d,
        ),
      BoxFace(
        id: '$prefix.bottom', surface: bottom,
        origin: BoxV3(min.x + r, max.y, min.z), u: px, v: pz, width: w - 2 * r, height: d,
      ),
    ];
    if (r > 0 && segments > 0) {
      final corners = [
        (BoxV3(min.x + r, min.y + r, 0), math.pi, 'tl'),
        (BoxV3(max.x - r, min.y + r, 0), 1.5 * math.pi, 'tr'),
        (BoxV3(max.x - r, max.y - r, 0), 0.0, 'br'),
        (BoxV3(min.x + r, max.y - r, 0), 0.5 * math.pi, 'bl'),
      ];
      for (final (c, start, name) in corners) {
        for (var i = 0; i < segments; i++) {
          final a = start + (math.pi / 2) * i / segments;
          final b = start + (math.pi / 2) * (i + 1) / segments;
          final pa = BoxV3(c.x + r * math.cos(a), c.y + r * math.sin(a), 0);
          final pb = BoxV3(c.x + r * math.cos(b), c.y + r * math.sin(b), 0);
          final u = (pb - pa).normalized;
          final mid = (a + b) / 2;
          final outward = BoxV3(math.cos(mid), math.sin(mid), 0);
          // Choose the depth direction so that v × u points outward.
          final towardBack = pz.cross(u).dot(outward) > 0;
          faces.add(BoxFace(
            id: '$prefix.corner.$name$i',
            surface: BoxSurface.edge,
            origin: BoxV3(pa.x, pa.y, towardBack ? min.z : max.z),
            u: u,
            v: towardBack ? pz : nz,
            width: (pb - pa).length,
            height: d,
          ));
        }
      }
    }
    return faces;
  }

  /// Parts for [opening]. Closed boxes are one convex body.
  List<BoxPart> parts(BoxOpening opening) {
    final w = width, h = height, d = depth;
    final min = BoxV3(-w / 2, -h / 2, -d / 2);
    final max = BoxV3(w / 2, h / 2, d / 2);
    if (!profile.opens || opening.isClosed) {
      return [BoxPart(id: 'body', faces: _closedFaces(min, max))];
    }
    switch (profile.caseKind) {
      case GameBoxCaseKind.cardboard:
        return _cardboardParts(opening, min, max);
      case GameBoxCaseKind.keepCase:
      case GameBoxCaseKind.jewelCase:
      case GameBoxCaseKind.clamshell:
        return _hingedParts(opening, min, max);
      case GameBoxCaseKind.flat:
        return [BoxPart(id: 'body', faces: _closedFaces(min, max))];
    }
  }

  bool get _jewel => profile.caseKind == GameBoxCaseKind.jewelCase;

  List<BoxFace> _closedFaces(BoxV3 min, BoxV3 max) => cuboid(
        'body', min, max,
        radius: profile.cornerRadius,
        // A jewel case shows the second spine of its back inlay on the
        // opening side.
        right: _jewel ? BoxSurface.spineRight : BoxSurface.edge,
      );

  /// Plastic cases: the front panel (thickness `lidThickness`) turns around
  /// the front-left edge toward the viewer and to the left.
  List<BoxPart> _hingedParts(BoxOpening opening, BoxV3 min, BoxV3 max) {
    final t = profile.lidThickness.clamp(0.5, depth * 0.45).toDouble();
    final splitZ = min.z + t;
    final spineSplit = 1 - t / depth; // fraction of the spine on the body.
    final body = cuboid(
      'body',
      BoxV3(min.x, min.y, splitZ),
      max,
      front: BoxSurface.interior,
      right: _jewel ? BoxSurface.spineRight : BoxSurface.edge,
      leftSource: _jewel ? const Rect.fromLTWH(0, 0, 1, 1) : Rect.fromLTRB(0, 0, spineSplit, 1),
      radius: profile.cornerRadius,
    );
    final lidFaces = cuboid(
      'lid',
      min,
      BoxV3(max.x, max.y, splitZ),
      back: BoxSurface.lidInner,
      // The jewel lid is clear plastic: its hinge edge carries no print.
      left: _jewel ? BoxSurface.edge : BoxSurface.spine,
      leftSource: Rect.fromLTRB(spineSplit, 0, 1, 1),
      radius: profile.cornerRadius,
    );
    final angle = lidOpenAngle * _ease(opening.lid);
    final hinge = BoxV3(min.x, 0, splitZ);
    final lid = BoxRigid.about(hinge, BoxM3.rotationY(angle));
    final support = supportPart(opening, trayZ: splitZ);
    return [
      BoxPart(id: 'body', faces: body, layer: 0),
      ?support,
      BoxPart(id: 'lid', faces: lidFaces, transform: lid, layer: 2),
    ];
  }

  /// Cardboard: the top flap turns backward around the top-back edge, then
  /// the cartridge rises out of the opening.
  List<BoxPart> _cardboardParts(BoxOpening opening, BoxV3 min, BoxV3 max) {
    final body = cuboid('body', min, max, includeTop: false);
    final opening2 = BoxFace(
      id: 'body.opening',
      surface: BoxSurface.interior,
      origin: BoxV3(min.x, min.y + 0.01, max.z),
      u: const BoxV3(1, 0, 0),
      v: const BoxV3(0, 0, -1),
      width: max.x - min.x,
      height: max.z - min.z,
    );
    final flapFaces = [
      BoxFace(
        id: 'flap.top', surface: BoxSurface.top,
        origin: BoxV3(min.x, min.y, max.z), u: const BoxV3(1, 0, 0),
        v: const BoxV3(0, 0, -1), width: max.x - min.x, height: max.z - min.z,
      ),
      BoxFace(
        id: 'flap.inner', surface: BoxSurface.lidInner,
        origin: BoxV3(min.x, min.y, min.z), u: const BoxV3(1, 0, 0),
        v: const BoxV3(0, 0, 1), width: max.x - min.x, height: max.z - min.z,
      ),
    ];
    final angle = flapOpenAngle * _ease(opening.lid);
    final hinge = BoxV3(0, min.y, max.z);
    final flap = BoxRigid.about(hinge, BoxM3.rotationX(-angle));
    final support = supportPart(opening, trayZ: 0);
    // While the flap closes over the opening it is nearer than the support;
    // once folded back (and before the support rises) it is behind it.
    final flapBehind = opening.lid >= 0.62;
    return [
      BoxPart(id: 'opening', faces: [opening2], layer: 0, cull: false),
      BoxPart(id: 'flap', faces: flapFaces, transform: flap, layer: flapBehind ? 1 : 4),
      ?support,
      BoxPart(id: 'body', faces: body, layer: 3),
    ];
  }

  /// Size of the support face (mm) and whether it is round.
  (double, double, double, bool)? get supportSize {
    final cart = profile.cartridge;
    final disc = profile.disc;
    switch (profile.support) {
      case GameBoxSupportKind.disc:
      case GameBoxSupportKind.miniDisc:
        final dd = disc?.diameter ?? 120;
        return (dd, dd, 1.2, true);
      case GameBoxSupportKind.umd:
        return (65, 64, 4.2, false);
      case GameBoxSupportKind.cartridge:
      case GameBoxSupportKind.card:
      case GameBoxSupportKind.hucard:
        final c = cart;
        if (c == null) return (90, 70, 14, false);
        return (c.width, c.height, c.thickness, false);
      case GameBoxSupportKind.floppy:
        return (90, 94, 3.3, false);
      case GameBoxSupportKind.cassette:
        return (100, 64, 12, false);
      case GameBoxSupportKind.none:
        return null;
    }
  }

  /// Whether the support comes out of the box (cartridges) or stays in its
  /// slot (discs).
  bool get supportLifts => switch (profile.support) {
        GameBoxSupportKind.disc || GameBoxSupportKind.miniDisc || GameBoxSupportKind.umd => false,
        GameBoxSupportKind.none => false,
        _ => true,
      };

  /// Rest position of the support in box coordinates, before it lifts.
  BoxPart? supportPart(BoxOpening opening, {required double trayZ}) {
    final size = supportSize;
    if (size == null) return null;
    var (sw, sh, st, round) = size;
    // Never larger than the box (wrong data, tiny jewel cases).
    final fit = math.min(1.0, math.min((width * 0.92) / sw, (height * 0.92) / sh));
    sw *= fit;
    sh *= fit;
    st = math.min(st * fit, depth * 0.8);
    final lift = _ease(opening.support);
    switch (profile.caseKind) {
      case GameBoxCaseKind.cardboard:
        // Standing inside, facing the front; rises through the top opening.
        final bottomY = height / 2 - 2;
        final rise = sh * 0.62 * lift;
        final y0 = bottomY - sh - rise;
        final faces = cuboid(
          'support',
          BoxV3(-sw / 2, y0, -st / 2),
          BoxV3(sw / 2, y0 + sh, st / 2),
          front: BoxSurface.supportFront,
          back: BoxSurface.supportBack,
          left: BoxSurface.supportEdge,
          right: BoxSurface.supportEdge,
          top: BoxSurface.supportEdge,
          bottom: BoxSurface.supportEdge,
        );
        return BoxPart(id: 'support', faces: faces, layer: 2);
      case GameBoxCaseKind.keepCase:
      case GameBoxCaseKind.jewelCase:
      case GameBoxCaseKind.clamshell:
        // Lying on the tray. Small cards sit in the upper right like the clip
        // of a DS case; discs are centred on their hub.
        final cx = round || sw > width * 0.6 ? 0.0 : width * 0.18;
        final cy = round || sh > height * 0.6 ? 0.0 : -height * 0.12;
        final out = supportLifts ? (6 + st) * lift : 0.0;
        final z0 = trayZ - (round ? 0.25 : st) - out;
        final upward = supportLifts ? sh * 0.10 * lift : 0.0;
        if (round) {
          return BoxPart(
            id: 'support',
            cull: false,
            layer: 1,
            faces: [
              BoxFace(
                id: 'support.front', surface: BoxSurface.supportFront,
                origin: BoxV3(cx - sw / 2, cy - sh / 2, z0), u: const BoxV3(1, 0, 0),
                v: const BoxV3(0, 1, 0), width: sw, height: sh,
              ),
            ],
          );
        }
        final faces = cuboid(
          'support',
          BoxV3(cx - sw / 2, cy - sh / 2 - upward, z0),
          BoxV3(cx + sw / 2, cy + sh / 2 - upward, z0 + st),
          front: BoxSurface.supportFront,
          back: BoxSurface.supportBack,
          left: BoxSurface.supportEdge,
          right: BoxSurface.supportEdge,
          top: BoxSurface.supportEdge,
          bottom: BoxSurface.supportEdge,
        );
        return BoxPart(id: 'support', faces: faces, layer: 1);
      case GameBoxCaseKind.flat:
        return null;
    }
  }

  static double _ease(double t) {
    final c = t.clamp(0.0, 1.0);
    return c * c * (3 - 2 * c);
  }
}

/// One face ready to paint.
class ProjectedFace {
  const ProjectedFace({
    required this.face,
    required this.part,
    required this.matrix,
    required this.width,
    required this.height,
    required this.shade,
    required this.depth,
    required this.pxPerMm,
  });

  final BoxFace face;
  final BoxPart part;

  /// Maps the face's local logical pixels (0..width, 0..height) to the
  /// viewport.
  final Matrix4 matrix;
  final double width;
  final double height;

  /// 1 = unlit (as authored), lower = darker. The face most turned toward
  /// the viewer keeps 1, so a face read straight on is never darkened.
  final double shade;
  final double depth;

  /// Logical pixels per millimetre of the model at this pose.
  final double pxPerMm;
}

/// Projects the model for a viewport.
class BoxProjector {
  BoxProjector({
    required this.model,
    required this.viewport,
    required this.pose,
    this.opening = BoxOpening.closed,
    this.fitPadding = 0.86,
    this.rotationSafeFit = true,
    this.outlineBlend = 0,
  });

  final GameBoxModel model;
  final Size viewport;
  final BoxPose pose;
  final BoxOpening opening;
  final double fitPadding;

  /// Fit the box's diagonal, so that turning it never changes its size.
  /// Static poses (the carousel card) fit their actual outline instead.
  final bool rotationSafeFit;

  /// 0 = [rotationSafeFit] framing, 1 = the outline of every part at this
  /// pose and opening, centred (an open lid or a cartridge coming out stays
  /// in view). Values in between blend the two, so that a box can move from
  /// the inspector's framing to the opening's without a jump.
  final double outlineBlend;

  late final (double, double, double) _framing = _computeFraming();

  /// Millimetres to logical pixels at zoom 1.
  double get scale => _framing.$1;

  /// Offset (logical pixels) that centres the framed outline.
  double get offsetX => _framing.$2;
  double get offsetY => _framing.$3;

  (double, double, double) _computeFraming() {
    final base = _fitScale();
    final t = outlineBlend.clamp(0.0, 1.0);
    if (t == 0) return (base, 0, 0);
    final r = pose.rotation;
    var minX = double.infinity, maxX = -double.infinity;
    var minY = double.infinity, maxY = -double.infinity;
    for (final part in model.parts(opening)) {
      for (final face in part.faces) {
        for (final (a, b) in const [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]) {
          final local = face.origin + face.u * (face.width * a) + face.v * (face.height * b);
          final p = r.apply(part.transform.apply(local));
          minX = math.min(minX, p.x);
          maxX = math.max(maxX, p.x);
          minY = math.min(minY, p.y);
          maxY = math.max(maxY, p.y);
        }
      }
    }
    final ew = (maxX - minX) * 1.08, eh = (maxY - minY) * 1.08;
    var outline = (ew <= 0 || eh <= 0)
        ? base
        : math.min(viewport.width * fitPadding / ew, viewport.height * fitPadding / eh);
    var ox = -(minX + maxX) / 2 * outline, oy = -(minY + maxY) / 2 * outline;
    // Parts nearer the camera (an open lid) project larger: refine with the
    // perspective of this pose.
    final zoom = pose.zoom.clamp(BoxPose.minZoom * 0.3, BoxPose.maxZoom);
    for (var pass = 0; pass < 2 && ew > 0 && eh > 0; pass++) {
      var pMinX = double.infinity, pMaxX = -double.infinity;
      var pMinY = double.infinity, pMaxY = -double.infinity;
      final sz = outline * zoom;
      for (final part in model.parts(opening)) {
        for (final face in part.faces) {
          for (final (a, b) in const [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0), (1.0, 1.0)]) {
            final local = face.origin + face.u * (face.width * a) + face.v * (face.height * b);
            final q = r.apply(part.transform.apply(local)) * sz;
            final w = math.max(0.2, 1 + q.z / focal);
            pMinX = math.min(pMinX, q.x / w);
            pMaxX = math.max(pMaxX, q.x / w);
            pMinY = math.min(pMinY, q.y / w);
            pMaxY = math.max(pMaxY, q.y / w);
          }
        }
      }
      final pw = (pMaxX - pMinX) * 1.04 / zoom, ph = (pMaxY - pMinY) * 1.04 / zoom;
      if (pw <= 0 || ph <= 0) break;
      final k = math.min(viewport.width * fitPadding / pw, viewport.height * fitPadding / ph);
      ox = -(pMinX + pMaxX) / 2 / zoom * k;
      oy = -(pMinY + pMaxY) / 2 / zoom * k;
      outline *= k;
    }
    final s = base + (outline - base) * t;
    // Offsets were computed for the outline scale; follow the blended one.
    final follow = outline == 0 ? 0.0 : s / outline;
    return (s, ox * t * zoom * follow, oy * t * zoom * follow);
  }

  /// Where a model point (mm, box coordinates) of [partId] lands on screen.
  Offset? screenPoint(String partId, BoxV3 local) {
    for (final part in model.parts(opening)) {
      if (part.id != partId) continue;
      final s = scale * pose.zoom.clamp(BoxPose.minZoom * 0.3, BoxPose.maxZoom);
      final p = pose.rotation.apply(part.transform.apply(local)) * s;
      final w = 1 + p.z / focal;
      if (w <= 0) return null;
      return Offset(
        viewport.width / 2 + pose.panX + offsetX + p.x / w,
        viewport.height / 2 + pose.panY + offsetY + p.y / w,
      );
    }
    return null;
  }

  /// Centre of the support on screen, when the profile has one.
  Offset? get supportCenter {
    for (final part in model.parts(opening)) {
      if (part.id != 'support' || part.faces.isEmpty) continue;
      var c = BoxV3.zero;
      for (final f in part.faces) {
        c = c + f.center;
      }
      return screenPoint('support', c * (1 / part.faces.length));
    }
    return null;
  }

  /// Focal distance (logical pixels) of the perspective.
  double get focal {
    final base = math.max(viewport.width, viewport.height) * 1.6;
    final p = pose.perspective.clamp(0.02, 2.0);
    return base / p;
  }

  BoxV3 get eye => BoxV3(0, 0, -focal);

  double _fitScale() {
    final w = model.width, h = model.height, d = model.depth;
    if (viewport.width <= 0 || viewport.height <= 0) return 1;
    double ew, eh;
    if (rotationSafeFit) {
      ew = math.sqrt(w * w + d * d);
      eh = math.sqrt(h * h + d * d);
      // A box tilted as far as the inspector allows still fits.
      eh = math.max(eh, h);
    } else {
      // Outline of the eight corners at this pose without perspective.
      final r = pose.rotation;
      var minX = double.infinity, maxX = -double.infinity;
      var minY = double.infinity, maxY = -double.infinity;
      for (final sx in const [-1.0, 1.0]) {
        for (final sy in const [-1.0, 1.0]) {
          for (final sz in const [-1.0, 1.0]) {
            final p = r.apply(BoxV3(sx * w / 2, sy * h / 2, sz * d / 2));
            minX = math.min(minX, p.x);
            maxX = math.max(maxX, p.x);
            minY = math.min(minY, p.y);
            maxY = math.max(maxY, p.y);
          }
        }
      }
      ew = (maxX - minX) * 1.06;
      eh = (maxY - minY) * 1.06;
    }
    return math.min(viewport.width * fitPadding / ew, viewport.height * fitPadding / eh);
  }

  /// All visible faces, back to front.
  List<ProjectedFace> project() {
    final s = scale * pose.zoom.clamp(BoxPose.minZoom * 0.3, BoxPose.maxZoom);
    final rotation = pose.rotation;
    final f = focal;
    final e = eye;
    final light = const BoxV3(-0.25, -0.35, -1).normalized;
    final frontLight = const BoxV3(0, 0, -1).dot(light);
    final perspective = Matrix4.identity()..setEntry(3, 2, 1 / f);
    final center = Matrix4.translationValues(
      viewport.width / 2 + pose.panX + offsetX,
      viewport.height / 2 + pose.panY + offsetY,
      0,
    );
    final viewProjection = center.multiplied(perspective);

    final parts = model.parts(opening)..sort((a, b) => a.layer.compareTo(b.layer));
    final out = <ProjectedFace>[];
    for (final part in parts) {
      final toView = BoxRigid(rotation, BoxV3.zero).compose(part.transform);
      final visible = <ProjectedFace>[];
      for (final face in part.faces) {
        final o = toView.apply(face.origin) * s;
        final u = toView.applyVector(face.u);
        final v = toView.applyVector(face.v);
        final n = v.cross(u).normalized;
        final c = toView.apply(face.center) * s;
        final toFace = c - e;
        final facing = n.dot(toFace) < 0;
        if (part.cull && !facing) continue;
        final lambert = n.dot(light);
        final shade = (0.62 + 0.38 * lambert) / (0.62 + 0.38 * frontLight);
        final m = Matrix4(
          u.x, u.y, u.z, 0,
          v.x, v.y, v.z, 0,
          n.x, n.y, n.z, 0,
          o.x, o.y, o.z, 1,
        );
        visible.add(ProjectedFace(
          face: face,
          part: part,
          matrix: viewProjection.multiplied(m),
          width: face.width * s,
          height: face.height * s,
          shade: shade.clamp(0.55, 1.0).toDouble(),
          depth: toFace.length,
          pxPerMm: s,
        ));
      }
      visible.sort((a, b) => b.depth.compareTo(a.depth));
      out.addAll(visible);
    }
    return out;
  }

  /// Surface of the face most turned toward the viewer (for accessibility
  /// labels and "showing the back" checks).
  BoxSurface? get facingSurface {
    final rotation = pose.rotation;
    BoxSurface? best;
    var bestDot = -2.0;
    for (final face in model.parts(BoxOpening.closed).first.faces) {
      final n = rotation.apply(face.normal);
      final d = -n.z;
      if (d > bestDot) {
        bestDot = d;
        best = face.surface;
      }
    }
    return best;
  }
}
