// The disc or cartridge as a solid, taken out of the open box and turned
// in front of the camera (docs/game-box-3d.md § 30).
import 'dart:math' as math;
import 'dart:ui' show Offset, Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';

const _viewport = Size(400, 500);
const _pose = BoxPose(yaw: -0.22, pitch: 0.1);

GameBoxModel _model(String system) => GameBoxModel(GameBoxProfile.forSystem(system));

BoxOpening _open(GameBoxModel model) =>
    BoxOpening(lid: 1, support: model.profile.caseKind == GameBoxCaseKind.cardboard ? 1 : 0);

BoxProjector _projector(GameBoxModel model, BoxOpening opening) =>
    BoxProjector(model: model, viewport: _viewport, pose: _pose, opening: opening, outlineBlend: 1);

BoxOpening _held(GameBoxModel model, {BoxM3 spin = BoxM3.identity}) {
  final open = _open(model);
  final target = _projector(model, open).supportTakeTarget()!;
  return open.copyWith(supportTake: 1, supportTakeTarget: target, supportSpin: spin);
}

/// Screen corners of [f] (top-left, top-right, bottom-right, bottom-left).
List<Offset> _quad(ProjectedFace f) {
  final m = f.matrix.storage;
  Offset at(double x, double y) {
    final w = m[3] * x + m[7] * y + m[15];
    return Offset((m[0] * x + m[4] * y + m[12]) / w, (m[1] * x + m[5] * y + m[13]) / w);
  }

  return [at(0, 0), at(f.width, 0), at(f.width, f.height), at(0, f.height)];
}

Offset _centre(List<Offset> q) => q.reduce((a, b) => a + b) / q.length.toDouble();

void main() {
  test('a disc is a solid: label, data side and a rim lit as one curve', () {
    for (final (segments, rim) in [(8, 48), (3, 16)]) {
      final model = GameBoxModel(GameBoxProfile.forSystem('ps2'), cornerSegments: segments);
      final faces = model.supportFaces();
      final front = faces.singleWhere((f) => f.id == 'support.front');
      final back = faces.singleWhere((f) => f.id == 'support.back');
      expect(front.normal.z, closeTo(-1, 1e-9), reason: 'the label toward the viewer');
      expect(back.normal.z, closeTo(1, 1e-9));
      expect((back.origin.z - front.origin.z), closeTo(1.2, 1e-9), reason: 'its thickness');
      final rims = faces.where((f) => f.id.startsWith('support.rim')).toList();
      expect(rims, hasLength(rim));
      for (var i = 0; i < rims.length; i++) {
        final a = rims[i], b = rims[(i + 1) % rims.length];
        expect(a.normalEnd!.x, closeTo(b.normalStart!.x, 1e-9), reason: 'facets meet without a step');
        expect(a.normalEnd!.y, closeTo(b.normalStart!.y, 1e-9));
        // Each facet faces out of the disc.
        final c = a.center;
        expect(a.normal.dot(BoxV3(c.x, c.y, 0).normalized), greaterThan(0.99));
      }
    }
  });

  test('cartridges and cards are blocks with rounded corners; the Game Boy corner is cut', () {
    for (final system in ['snes', 'n64', 'ds', 'gb', 'psp']) {
      final faces = _model(system).supportFaces();
      final front = faces.singleWhere((f) => f.id == 'support.front');
      expect(front.cornerRadius, greaterThan(0), reason: '$system: rounded like its shell');
      final sides = faces.where((f) => f.id.startsWith('support.side')).toList();
      final curved = sides.where((f) => f.normalStart != null);
      final chamfers = sides.where((f) => f.normalStart == null && (f.normal.x.abs() - f.normal.y.abs()).abs() < 1e-6);
      if (system == 'gb') {
        expect(chamfers, hasLength(1), reason: 'the cut corner at 45°');
        expect(chamfers.single.normal.x, greaterThan(0));
        expect(chamfers.single.normal.y, greaterThan(0), reason: 'bottom right');
        expect(curved, hasLength(3 * 8));
      } else {
        expect(chamfers, isEmpty, reason: system);
        expect(curved, hasLength(4 * 8), reason: system);
      }
      for (final f in sides) {
        expect(f.normal.z.abs(), lessThan(1e-9), reason: '$system: sides stand across the thickness');
        final c = f.center;
        expect(f.normal.dot(BoxV3(c.x, c.y, 0)), greaterThan(0), reason: '$system ${f.id} faces out');
      }
    }
  });

  test('taken, the support faces the camera squarely in the middle of the view, and fills it', () {
    for (final system in ['ps2', 'gc', 'snes', 'ds', 'psp']) {
      final model = _model(system);
      final faces = _projector(model, _held(model)).project();
      final front = faces.singleWhere((f) => f.face.id == 'support.front');
      final quad = _quad(front);
      expect(_centre(quad).dx, closeTo(_viewport.width / 2, 2), reason: system);
      expect(_centre(quad).dy, closeTo(_viewport.height / 2, 2), reason: system);
      expect(front.facing, closeTo(1, 0.01), reason: '$system: square to the camera');
      expect(quad[1].dy - quad[0].dy, closeTo(0, 0.5), reason: '$system: level');
      final (w, h, _, round) = model.fittedSupportSize!;
      final extent = round ? w : math.sqrt(w * w + h * h);
      final shown = (quad[1] - quad[0]).distance * extent / w;
      expect(shown, closeTo(0.72 * _viewport.width, 0.02 * _viewport.width), reason: '$system: its extent fills the view');
      expect(faces.last.part.id, 'support', reason: '$system: drawn over the box');
    }
  });

  test('the box keeps its framing while its support is out', () {
    for (final system in ['ps2', 'snes', 'ds']) {
      final model = _model(system);
      final open = _projector(model, _open(model));
      final held = _projector(model, _held(model));
      expect(held.scale, closeTo(open.scale, 1e-9), reason: system);
      expect(held.offsetX, closeTo(open.offsetX, 1e-9), reason: system);
      expect(held.offsetY, closeTo(open.offsetY, 1e-9), reason: system);
    }
  });

  test('a turn of the held support is a turn about its centre and the axes of the screen', () {
    final model = _model('snes');
    ProjectedFace? face(BoxOpening o, String id) {
      for (final f in _projector(model, o).project()) {
        if (f.face.id == id) return f;
      }
      return null;
    }

    // Turned to the right (as a drag to the right does): its right side goes away.
    final right = face(_held(model, spin: BoxM3.rotationY(-0.6)), 'support.front')!;
    final q = _quad(right);
    expect((q[2] - q[1]).distance, lessThan((q[3] - q[0]).distance));
    // Tilted forward (a drag down): its bottom goes away.
    final down = _quad(face(_held(model, spin: BoxM3.rotationX(0.6)), 'support.front')!);
    expect((down[2] - down[3]).distance, lessThan((down[1] - down[0]).distance));
    // Half a turn: the back, upright and not mirrored; the label is hidden.
    final turned = _held(model, spin: BoxM3.rotationY(math.pi));
    expect(face(turned, 'support.front'), isNull);
    final back = _quad(face(turned, 'support.back')!);
    expect(back[1].dx, greaterThan(back[0].dx), reason: 'not mirrored');
    expect(back[3].dy, greaterThan(back[0].dy), reason: 'upright');
    // Whatever the turn, it stays in the middle.
    for (final spin in [BoxM3.rotationY(1.1), BoxM3.rotationX(-0.9) * BoxM3.rotationY(2.4)]) {
      final centre = _projector(model, _held(model, spin: spin)).supportCenter!;
      expect(centre.dx, closeTo(_viewport.width / 2, 3));
      expect(centre.dy, closeTo(_viewport.height / 2, 3));
    }
  });

  test('a touch finds a disc inside its circle only, and a cartridge not behind its box', () {
    final ps2 = _model('ps2');
    final held = _projector(ps2, _held(ps2));
    const c = Offset(200, 250);
    expect(held.hitsSupport(c), isTrue);
    final r = (_quad(held.project().singleWhere((f) => f.face.id == 'support.front'))[1] - _quad(held.project().singleWhere((f) => f.face.id == 'support.front'))[0]).distance / 2;
    expect(held.hitsSupport(c + Offset(r * 0.95, 0)), isTrue);
    expect(held.hitsSupport(c + Offset(r * 0.9, r * 0.9)), isFalse, reason: 'the corner of its square is not the disc');

    final snes = _model('snes');
    final open = _projector(snes, _open(snes));
    final front = open.project().singleWhere((f) => f.face.id == 'support.front');
    final q = _quad(front);
    final top = Offset((q[0].dx + q[1].dx) / 2, q[0].dy + 4);
    final low = Offset((q[3].dx + q[2].dx) / 2, q[3].dy - 4);
    expect(open.hitsSupport(top), isTrue, reason: 'the part standing out of the box');
    expect(open.hitsSupport(low), isFalse, reason: 'the part inside, behind the box front');
  });

  test('put back, the support lies where it was taken from', () {
    for (final system in ['ps2', 'snes', 'ds']) {
      final model = _model(system);
      final rest = model.parts(_open(model)).firstWhere((p) => p.id == 'support');
      final back = model.parts(_held(model, spin: BoxM3.rotationY(2)).copyWith(supportTake: 0)).firstWhere((p) => p.id == 'support');
      expect(back.transform.translation.length, closeTo(0, 1e-9), reason: system);
      expect(back.faces.first.origin.z, closeTo(rest.faces.first.origin.z, 1e-9), reason: system);
      expect(back.layer, rest.layer);
    }
  });
}
