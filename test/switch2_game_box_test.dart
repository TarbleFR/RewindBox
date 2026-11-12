import 'dart:io';
import 'dart:ui' show Size;

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/widgets/game_box/game_box_spine_design.dart';

/// Switch 2 game boxes are the Switch ones, as the maintainer asked after IPA 727. Each one has:
/// - the clear 105 × 170 × 11 mm case with the red band, holding a red game card;
/// - the Switch template for a full sheet;
/// - the Switch spine with the Switch 2 logo.
/// Before, the system's "cartridge" media gave a cardboard box.
void main() {
  test('a Switch 2 game gets the clear Switch case with a red card, not a cardboard box', () {
    final sw = GameBoxProfile.forSystem('switch');
    final sw2 = GameBoxProfile.forSystem('switch2', media: const ['cartridge']);
    expect(sw2.id, 'switch2');
    expect(sw2.caseKind, sw.caseKind);
    expect((sw2.width, sw2.height, sw2.depth, sw2.cornerRadius), (105.0, 170.0, 11.0, sw.cornerRadius));
    expect(sw2.material, GameBoxCaseMaterial.clear);
    expect(sw2.support, GameBoxSupportKind.card);
    expect(sw2.caseColor, sw.caseColor);
    expect(sw2.resolvedInsertColor, sw.resolvedInsertColor, reason: 'the red band of the Switch cover');
    final card = sw2.cartridge!;
    final switchCard = sw.cartridge!;
    expect((card.width, card.height, card.thickness), (switchCard.width, switchCard.height, switchCard.thickness));
    expect(card.bodyColor.r, greaterThan(0.7), reason: 'Switch 2 game cards are red');
    expect(card.bodyColor.g, lessThan(0.2));
    expect(card.id, 'switch2');
    for (final aspect in [320 / 176, 1.0, 0.45, 1.9, double.nan, null]) {
      final p = sw2.withFrontAspect(aspect);
      expect((p.width, p.height, p.depth), (sw2.width, sw2.height, sw2.depth), reason: 'a rigid case at $aspect');
    }
  });

  test('a full Switch 2 sheet is cut with the Switch template', () {
    final layout = GameBoxWrapLayout.forProfile(GameBoxProfile.forSystem('switch2'))!;
    final switchLayout = GameBoxWrapLayout.forProfile(GameBoxProfile.forSystem('switch'))!;
    expect((layout.panel, layout.spine, layout.height, layout.spineFit),
        (switchLayout.panel, switchLayout.spine, switchLayout.height, switchLayout.spineFit));
    expect(layout.matches(const Size(2454, 1888)), isTrue);
  });

  test('the spine is the Switch spine with the Switch 2 logo, which ships', () {
    final design = GameBoxSpineDesign.of(GameBoxProfile.forSystem('switch2'));
    final switchDesign = GameBoxSpineDesign.of(GameBoxProfile.forSystem('switch'));
    expect(design.logo, 'switch2');
    expect((design.background, design.head, design.headMm), (switchDesign.background, switchDesign.head, switchDesign.headMm));
    expect(GameBoxSpineDesign.logos, contains('switch2'));
    expect(File(design.logoAsset!).existsSync(), isTrue);
  });
}
