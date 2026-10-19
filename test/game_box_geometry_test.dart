import 'dart:math' as math;
import 'dart:ui' show Offset, Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_geometry.dart';

/// Projects a face corner (local px) through its matrix.
Offset _project(ProjectedFace f, double x, double y) {
  final m = f.matrix.storage;
  final px = m[0] * x + m[4] * y + m[12];
  final py = m[1] * x + m[5] * y + m[13];
  final pw = m[3] * x + m[7] * y + m[15];
  return Offset(px / pw, py / pw);
}

Set<String> _visible(GameBoxModel model, BoxPose pose, {BoxOpening opening = BoxOpening.closed}) =>
    BoxProjector(model: model, viewport: const Size(400, 500), pose: pose, opening: opening)
        .project()
        .map((f) => f.face.id)
        .toSet();

void main() {
  final ps2 = GameBoxModel(GameBoxProfile.forSystem('ps2'));

  group('closed box', () {
    test('front pose shows the front and never the back', () {
      final ids = _visible(ps2, BoxPose.front);
      expect(ids, contains('body.front'));
      expect(ids, isNot(contains('body.back')));
    });

    test('back pose shows the back, read left to right (not mirrored)', () {
      final faces = BoxProjector(model: ps2, viewport: const Size(400, 500), pose: BoxPose.back).project();
      final back = faces.firstWhere((f) => f.face.id == 'body.back');
      expect(faces.any((f) => f.face.id == 'body.front'), isFalse);
      final left = _project(back, 0, back.height / 2);
      final right = _project(back, back.width, back.height / 2);
      expect(right.dx, greaterThan(left.dx), reason: 'the back image must not be mirrored');
      final top = _project(back, back.width / 2, 0);
      final bottom = _project(back, back.width / 2, back.height);
      expect(bottom.dy, greaterThan(top.dy), reason: 'the back image must not be upside down');
    });

    test('the resting pose shows the front and the spine', () {
      final ids = _visible(ps2, BoxPose.rest);
      expect(ids, containsAll(['body.front', 'body.left']));
      expect(ids, isNot(contains('body.back')));
    });

    test('the spine reads left to right when it faces the viewer', () {
      final faces = BoxProjector(
        model: ps2, viewport: const Size(400, 500), pose: const BoxPose(yaw: -math.pi / 2),
      ).project();
      final spine = faces.firstWhere((f) => f.face.id == 'body.left');
      expect(_project(spine, spine.width, 10).dx, greaterThan(_project(spine, 0, 10).dx));
    });

    test('a full turn always shows a face and never front and back together', () {
      for (var i = 0; i < 72; i++) {
        final yaw = i * 2 * math.pi / 72;
        final ids = _visible(ps2, BoxPose(yaw: yaw, pitch: 0.2));
        expect(ids, isNotEmpty, reason: 'yaw $yaw');
        expect(ids.contains('body.front') && ids.contains('body.back'), isFalse, reason: 'yaw $yaw');
        final backward = math.cos(yaw) < -0.05;
        expect(ids.contains('body.back'), backward, reason: 'yaw $yaw');
      }
    });

    test('tilting shows the top or the bottom', () {
      expect(_visible(ps2, const BoxPose(pitch: 0.8)), contains('body.top'));
      expect(_visible(ps2, const BoxPose(pitch: -0.8)), contains('body.bottom'));
    });

    test('rotation-safe framing keeps the same scale whatever the yaw', () {
      double scale(double yaw) =>
          BoxProjector(model: ps2, viewport: const Size(400, 500), pose: BoxPose(yaw: yaw)).scale;
      expect(scale(0), closeTo(scale(1.3), 1e-9));
      expect(scale(math.pi), closeTo(scale(2.2), 1e-9));
    });

    test('rounded keep cases have corner faces; jewel cases are square', () {
      final keep = ps2.parts(BoxOpening.closed).first.faces;
      expect(keep.where((f) => f.id.contains('.corner.')), hasLength(12));
      final jewel = GameBoxModel(GameBoxProfile.forSystem('ps1')).parts(BoxOpening.closed).first.faces;
      expect(jewel.where((f) => f.id.contains('.corner.')), isEmpty);
      expect(jewel.where((f) => f.surface == BoxSurface.spineRight), hasLength(1));
    });

    test('pose interpolation takes the shortest way round', () {
      final mid = BoxPose.lerp(const BoxPose(yaw: 0.1), const BoxPose(yaw: 2 * math.pi - 0.1), 0.5);
      expect(mid.yaw, closeTo(0, 1e-9));
    });
  });

  group('opening', () {
    test('a keep case lid opens to the left of its hinge, the disc stays in its slot', () {
      final open = ps2.parts(const BoxOpening(lid: 1, support: 1));
      final lid = open.firstWhere((p) => p.id == 'lid');
      final corner = lid.transform.apply(BoxV3(ps2.width / 2, 0, -ps2.depth / 2));
      expect(corner.x, lessThan(-ps2.width / 2), reason: 'the free edge ends left of the hinge');
      final support = open.firstWhere((p) => p.id == 'support');
      final closedSupport = ps2.supportPart(const BoxOpening(lid: 1), trayZ: -ps2.depth / 2 + 2)!;
      expect(support.faces.first.origin.z, closeTo(closedSupport.faces.first.origin.z, 1e-9),
          reason: 'a disc does not come out of its hub');
    });

    test('a cartridge rises out of a cardboard box', () {
      final nes = GameBoxModel(GameBoxProfile.forSystem('nes'));
      double top(double support) => nes
          .parts(BoxOpening(lid: 1, support: support))
          .firstWhere((p) => p.id == 'support')
          .faces
          .map((f) => f.origin.y)
          .reduce(math.min);
      expect(top(1), lessThan(top(0) - 20));
      expect(top(1), lessThan(-nes.height / 2), reason: 'it comes above the box');
    });

    test('a card lifts out of a DS case toward the viewer', () {
      final ds = GameBoxModel(GameBoxProfile.forSystem('ds'));
      double z(double s) => ds
          .parts(BoxOpening(lid: 1, support: s))
          .firstWhere((p) => p.id == 'support')
          .faces
          .map((f) => f.origin.z)
          .reduce(math.min);
      expect(z(1), lessThan(z(0) - 3));
    });

    test('outline framing keeps the open box inside the viewport', () {
      const viewport = Size(400, 500);
      for (final system in ['ps1', 'ps2', 'gc', 'ds', 'nes', 'n64', 'md', 'psp']) {
        final model = GameBoxModel(GameBoxProfile.forSystem(system));
        final faces = BoxProjector(
          model: model, viewport: viewport, pose: const BoxPose(yaw: -0.22, pitch: 0.1),
          opening: const BoxOpening(lid: 1, support: 1), outlineBlend: 1,
        ).project();
        for (final f in faces) {
          for (final (x, y) in [(0.0, 0.0), (f.width, 0.0), (0.0, f.height), (f.width, f.height)]) {
            final p = _project(f, x, y);
            expect(p.dx, inInclusiveRange(-1, viewport.width + 1), reason: '$system ${f.face.id}');
            expect(p.dy, inInclusiveRange(-1, viewport.height + 1), reason: '$system ${f.face.id}');
          }
        }
      }
    });

    test('flat profiles never open', () {
      final flat = GameBoxModel(GameBoxProfile.forSystem('arc'));
      expect(flat.profile.opens, isFalse);
      expect(flat.parts(const BoxOpening(lid: 1, support: 1)).single.id, 'body');
    });
  });

  group('profiles', () {
    test('families follow the console and its medium', () {
      expect(GameBoxProfile.forSystem('ps1').caseKind, GameBoxCaseKind.jewelCase);
      expect(GameBoxProfile.forSystem('ps2').caseKind, GameBoxCaseKind.keepCase);
      expect(GameBoxProfile.forSystem('ps2').support, GameBoxSupportKind.disc);
      expect(GameBoxProfile.forSystem('gc').support, GameBoxSupportKind.miniDisc);
      expect(GameBoxProfile.forSystem('psp').support, GameBoxSupportKind.umd);
      expect(GameBoxProfile.forSystem('ds').support, GameBoxSupportKind.card);
      expect(GameBoxProfile.forSystem('nes').caseKind, GameBoxCaseKind.cardboard);
      expect(GameBoxProfile.forSystem('md').caseKind, GameBoxCaseKind.clamshell);
      expect(GameBoxProfile.forSystem('snes-hacks').caseKind, GameBoxCaseKind.cardboard);
      expect(GameBoxProfile.forSystem('unknown', media: ['cd_rom']).caseKind, GameBoxCaseKind.jewelCase);
      expect(GameBoxProfile.forSystem('unknown', media: ['cartridge']).caseKind, GameBoxCaseKind.cardboard);
      expect(GameBoxProfile.forSystem('steam', media: ['digital']).caseKind, GameBoxCaseKind.flat);
    });

    test('a PlayStation jewel case keeps its real size whatever the insert', () {
      final ps1 = GameBoxProfile.forSystem('ps1');
      final square = ps1.withFrontAspect(1.0);
      expect(square.width, 142);
      expect(square.height, 125);
      expect(square.depth, ps1.depth);
      final tall = ps1.withFrontAspect(0.6);
      expect(tall.height, greaterThan(tall.width), reason: 'long boxes follow their insert');
    });

    test('the front scan sets the proportions of other cases, not their thickness', () {
      final snes = GameBoxProfile.forSystem('snes').withFrontAspect(1.4);
      expect(snes.width / snes.height, closeTo(1.4, 1e-9));
      expect(snes.depth, GameBoxProfile.forSystem('snes').depth);
    });
  });
}
