import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

void main() {
  test('ARMSX2 in-game UI follows the 12 NeoStation locales', () {
    final locale = File(
      'packages/armsx2_internal_bridge/ios/Classes/ARMSX2InGameLocalization.mm',
    ).readAsStringSync();
    final menu = File(
      'packages/armsx2_internal_bridge/ios/Classes/Armsx2SessionMenu.mm',
    ).readAsStringSync();
    final centralLabels = File(
      'packages/retro_achievements_session/ios/Classes/RBRALocalization.m',
    ).readAsStringSync();
    final native = File(
      'packages/armsx2_internal_bridge/ios/Classes/Armsx2InternalBridgePlugin.mm',
    ).readAsStringSync();
    final bridge = File(
      'packages/armsx2_internal_bridge/lib/armsx2_internal_bridge.dart',
    ).readAsStringSync();
    final launcher = File(
      'lib/services/game/game_launch_service.dart',
    ).readAsStringSync();

    for (final key in <String>[
      'de', 'es', 'pt', 'ru', 'zh', 'zh_Hant',
      'fr', 'it', 'id', 'ja', 'ko',
    ]) {
      expect(locale, contains('@"$key": @{'));
    }
    // English is the stable source-key table/fallback and is therefore the
    // twelfth locale even though it does not duplicate every source string.
    expect(locale, contains('return english ?: @""'));

    for (final label in <String>[
      'Graphics',
      'Compatibility / Cheats',
      'Controls',
      'Save State',
      'Load State',
      'Internal Resolution',
      'Screen Format',
      'Graphics Hacks',
      'Automatic',
      'Touch Controls',
      'Manual graphics hacks',
      'GPU palette conversion',
      'CPU framebuffer conversion',
      'Disable depth emulation',
      'Blending Accuracy',
      'Default for all PS2 games',
      'Blending accuracy updated for this game.',
    ]) {
      expect(locale, contains('@"$label"'));
    }

    expect(menu, contains('ARMSX2LocalizedText'));
    for (final key in const [
      'en', 'de', 'es', 'pt', 'ru', 'zh', 'zh_Hant',
      'fr', 'it', 'id', 'ja', 'ko',
    ]) {
      expect(centralLabels, contains('@"$key": @['), reason: key);
    }
    expect(menu, contains('RBRALocalizedText(@"hardcoreBlocked", self.localeIdentifier)'));
    expect(native, contains('RBRALocalizedText(@"hardcoreBlocked", controller.uiLocale)'));
    expect(centralLabels, contains('[tag hasPrefix:@"zh-hant"]'));
    expect(centralLabels, contains('[tag hasPrefix:@"zh-tw"]'));
    expect(centralLabels, contains('[tag hasPrefix:@"zh-hk"]'));
    expect(native, contains('ARMSX2CanonicalLocale(args[@"uiLocale"])'));
    expect(bridge, contains("'uiLocale': uiLocale"));
    // Snapshot the explicit UI locale before asynchronous launch work, then
    // forward that same value instead of reading a potentially disposed context.
    const capture =
        'final launchLocale = Localizations.localeOf(context).toLanguageTag();';
    final ps2Launch = launcher.indexOf(
      'Armsx2LibraryService.launchGameByRomPath(',
    );
    expect(ps2Launch, greaterThanOrEqualTo(0));
    expect(
      launcher.lastIndexOf(capture, ps2Launch),
      greaterThanOrEqualTo(0),
    );
    final arguments = launcher.substring(
      ps2Launch,
      launcher.indexOf(');', ps2Launch),
    );
    expect(arguments, contains('uiLocale: launchLocale'));
    expect(arguments, isNot(contains('Localizations.localeOf(context)')));

    // Native menus must track NeoStation's explicit locale, not iOS language.
    expect(menu, isNot(contains('NSLocale.preferredLanguages')));
    expect(centralLabels, isNot(contains('NSLocale.preferredLanguages')));
    expect(native, isNot(contains('NSLocale.preferredLanguages')));
  });
}
