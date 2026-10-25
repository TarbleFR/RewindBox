import 'dart:math' as math;
import 'dart:ui' show Offset, Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';

/// The manual inside the open box (docs/game-box-3d.md § 11): it exists only
/// with a local PDF, lies where the real booklet lies for each family, is
/// readable the right way round, can be hit by a tap, and when taken comes
/// square to the camera without moving the box.

const _viewport = Size(400, 520);

/// The pose "Open the box" uses: front, a little of the hinge; from above
/// for a cardboard box.
BoxPose _openPose(GameBoxProfile p) => p.caseKind == GameBoxCaseKind.cardboard
    ? const BoxPose(yaw: -0.2, pitch: 0.34)
    : const BoxPose(yaw: -0.22, pitch: 0.1);

BoxOpening _inspectOpening(GameBoxProfile p) => p.caseKind == GameBoxCaseKind.cardboard
    ? const BoxOpening(lid: 1, support: 1, booklet: 1)
    : const BoxOpening(lid: 1);

BoxProjector _projector(GameBoxModel model, {BoxOpening? opening, BoxPose? pose}) => BoxProjector(
      model: model,
      viewport: _viewport,
      pose: pose ?? _openPose(model.profile),
      opening: opening ?? _inspectOpening(model.profile),
      outlineBlend: 1,
    );

Offset _centroid(List<Offset> q) => q.reduce((a, b) => a + b) / q.length.toDouble();

void main() {
  const families = ['ps2', 'ps1', 'gc', 'ds', 'psp', 'md', 'nes', 'snes', 'n64'];

  test('without a manual on the device there is never a booklet', () {
    for (final id in families) {
      final model = GameBoxModel(GameBoxProfile.forSystem(id));
      for (final opening in [BoxOpening.closed, const BoxOpening(lid: 1, support: 1, booklet: 1)]) {
        expect(model.parts(opening).any((p) => p.id == 'booklet'), isFalse, reason: id);
      }
      expect(model.bookletSize, isNull, reason: id);
    }
  });

  test('a closed box never draws its manual', () {
    for (final id in families) {
      final model = GameBoxModel(GameBoxProfile.forSystem(id), booklet: const GameBoxBooklet());
      expect(model.parts(BoxOpening.closed).any((p) => p.id == 'booklet'), isFalse, reason: id);
    }
  });

  test('the manual fits inside its box and follows the first page proportions', () {
    for (final id in families) {
      final profile = GameBoxProfile.forSystem(id);
      for (final aspect in [null, 0.7, 1.0, 1.42]) {
        final model = GameBoxModel(profile, booklet: GameBoxBooklet(pageAspect: aspect));
        final (w, h, t) = model.bookletSize!;
        expect(w, lessThan(profile.width), reason: '$id $aspect');
        expect(h, lessThan(profile.height), reason: '$id $aspect');
        expect(t, inInclusiveRange(1.0, 2.5), reason: 'a thin booklet ($id)');
        if (aspect != null) expect(w / h, closeTo(aspect, 1e-6), reason: '$id $aspect');
      }
    }
    // A CD booklet is square by default, a DVD manual portrait.
    final (jw, jh, _) = GameBoxModel(GameBoxProfile.forSystem('ps1'), booklet: const GameBoxBooklet()).bookletSize!;
    expect(jw / jh, closeTo(1, 1e-6));
    final (dw, dh, _) = GameBoxModel(GameBoxProfile.forSystem('ps2'), booklet: const GameBoxBooklet()).bookletSize!;
    expect(dw / dh, lessThan(0.8));
  });

  test('in an open case the manual faces the viewer, readable, and can be touched', () {
    for (final id in families) {
      final model = GameBoxModel(GameBoxProfile.forSystem(id), booklet: const GameBoxBooklet());
      final projector = _projector(model);
      final ids = projector.project().map((f) => f.face.id).toSet();
      expect(ids, contains('booklet.front'), reason: '$id: the cover is drawn');
      final quad = projector.faceQuad('booklet.front')!;
      // Not mirrored, not upside down.
      expect(quad[1].dx, greaterThan(quad[0].dx), reason: '$id left to right');
      expect(quad[3].dy, greaterThan(quad[0].dy), reason: '$id top to bottom');
      // The visible part: all of it in a case, its top out of a cardboard box.
      final cardboard = model.profile.caseKind == GameBoxCaseKind.cardboard;
      final probe = cardboard
          ? Offset.lerp(Offset.lerp(quad[0], quad[1], 0.5)!, Offset.lerp(quad[3], quad[2], 0.5)!, 0.04)!
          : _centroid(quad);
      expect(projector.hitsBooklet(probe), isTrue, reason: '$id: a tap on the manual takes it');
      expect(projector.hitsBooklet(const Offset(2, 2)), isFalse, reason: '$id: elsewhere it does not');
      if (cardboard) {
        expect(projector.hitsBooklet(_centroid(quad)), isFalse,
            reason: '$id: the part hidden by the front of the box does not take the tap');
      }
      for (final corner in quad) {
        expect(corner.dx, inInclusiveRange(-1, _viewport.width + 1), reason: '$id in view');
        expect(corner.dy, inInclusiveRange(-1, _viewport.height + 1), reason: '$id in view');
      }
    }
  });

  test('a disc case: the manual lies in the front panel, the disc on its tray', () {
    final model = GameBoxModel(GameBoxProfile.forSystem('ps2'), booklet: const GameBoxBooklet());
    final projector = _projector(model);
    final booklet = _centroid(projector.faceQuad('booklet.front')!);
    final disc = projector.supportCenter!;
    expect(booklet.dx, lessThan(disc.dx), reason: 'the opened panel lies on the left of the tray');
  });

  test('a cardboard box: the manual stands behind the cartridge and rises out of the top', () {
    final profile = GameBoxProfile.forSystem('nes');
    final model = GameBoxModel(profile, booklet: const GameBoxBooklet());
    final parts = model.parts(_inspectOpening(profile));
    final names = [for (final p in parts..sort((a, b) => a.layer.compareTo(b.layer))) p.id];
    expect(names.indexOf('booklet'), lessThan(names.indexOf('support')), reason: 'painted behind the cartridge');
    expect(names.indexOf('booklet'), lessThan(names.indexOf('body')), reason: 'inside the box');
    final booklet = parts.firstWhere((p) => p.id == 'booklet');
    var top = double.infinity;
    for (final f in booklet.faces) {
      top = math.min(top, booklet.transform.apply(f.origin).y);
    }
    expect(top, lessThan(-profile.height / 2), reason: 'it stands out of the open top');
  });

  test('the manual stays under the panel until the panel turns toward the viewer', () {
    final model = GameBoxModel(GameBoxProfile.forSystem('ps2'), booklet: const GameBoxBooklet());
    int layer(String id, double lid) => model.parts(BoxOpening(lid: lid)).firstWhere((p) => p.id == id).layer;
    expect(layer('booklet', 0.25), lessThan(layer('lid', 0.25)));
    expect(layer('booklet', 1), greaterThan(layer('lid', 1)));
  });

  test('taken, the manual comes square to the camera, centred and large, and the box does not move', () {
    for (final id in families) {
      final model = GameBoxModel(GameBoxProfile.forSystem(id), booklet: const GameBoxBooklet(pageAspect: 0.7));
      for (final pose in [_openPose(model.profile), _openPose(model.profile).copyWith(zoom: 1.6, panX: 30, panY: -20)]) {
        final rest = _projector(model, pose: pose);
        final target = rest.bookletTakeTarget()!;
        final taken = _projector(
          model,
          pose: pose,
          opening: _inspectOpening(model.profile).copyWith(take: 1, takeTarget: target),
        );
        expect(taken.scale, closeTo(rest.scale, 1e-9), reason: '$id: same framing');
        expect(taken.offsetX, closeTo(rest.offsetX, 1e-9), reason: id);
        expect(taken.offsetY, closeTo(rest.offsetY, 1e-9), reason: id);
        final quad = taken.faceQuad('booklet.front')!;
        final c = _centroid(quad);
        expect(c.dx, closeTo(_viewport.width / 2, _viewport.width * 0.02), reason: '$id centred');
        expect(c.dy, closeTo(_viewport.height / 2, _viewport.height * 0.02), reason: '$id centred');
        expect((quad[1].dy - quad[0].dy).abs(), lessThan(1), reason: '$id square to the camera');
        expect((quad[3].dx - quad[0].dx).abs(), lessThan(1), reason: '$id square to the camera');
        final height = quad[3].dy - quad[0].dy;
        final width = quad[1].dx - quad[0].dx;
        final fill = math.max(height / _viewport.height, width / _viewport.width);
        expect(fill, inInclusiveRange(0.78, 0.9), reason: '$id fills most of the view');
        final layers = taken.project();
        expect(layers.last.part.id, 'booklet', reason: '$id: nearest of all');
      }
    }
  });

  test('turning between two orientations takes the shortest way', () {
    final a = BoxM3.rotationY(0.2);
    final b = BoxM3.rotationY(-0.9) * BoxM3.rotationX(0.3);
    final mid = BoxRigid.lerp(BoxRigid(a, BoxV3.zero), BoxRigid(b, BoxV3.zero), 0).rotation;
    final end = BoxRigid.lerp(BoxRigid(a, BoxV3.zero), BoxRigid(b, BoxV3.zero), 1).rotation;
    for (var i = 0; i < 9; i++) {
      expect(mid.m[i], closeTo(a.m[i], 1e-9));
      expect(end.m[i], closeTo(b.m[i], 1e-9));
    }
  });
}
