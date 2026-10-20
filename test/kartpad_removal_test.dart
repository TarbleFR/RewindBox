import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/ports_locale.dart';
import 'package:neostation/services/game/game_launch_service.dart';

// KartPad left NeoStation on 19 October 2026 (maintainer decision): a game
// still listed from the old Ports/KartPad folder is refused with a translated
// explanation instead of being handed to Dusklight or another engine.
void main() {
  test('only the old Ports/KartPad/Games folder is recognised', () {
    const documents = '/var/mobile/Containers/Data/Application/ABC/Documents';
    for (final path in <String>[
      '$documents/Ports/KartPad/Games/RMCP01.rvz',
      '$documents/Ports/KartPad/Games/sub/Mario Kart Wii.wbfs',
      '$documents/Ports/../Ports/KartPad/Games/RMCP01.iso',
    ]) {
      expect(isRemovedKartPadGamePath(path), isTrue, reason: path);
    }
    for (final path in <String>[
      '$documents/Ports/Dusklight/Games/GZ2E01.rvz',
      '$documents/Ports/KartPad/Saves/rksys.dat',
      '$documents/Ports/KartPad/Games',
      '$documents/roms/wii/KartPad/Games/RMCP01.rvz',
      '$documents/Ports/kartpad/Games/RMCP01.rvz',
      '',
    ]) {
      expect(isRemovedKartPadGamePath(path), isFalse, reason: path);
    }
  });

  test('the explanation exists in all twelve NeoStation languages', () {
    const locales = <String>[
      'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja',
      'ko',
    ];
    expect(PortsLocale.values.keys.toSet(), locales.toSet());
    final texts = <String>{};
    for (final code in locales) {
      final table = PortsLocale.values[code]!;
      expect(table.keys.toSet(), <String>{'import', 'dusklight', 'kartpadRemoved'},
          reason: code);
      final text = table['kartpadRemoved']!;
      expect(text, contains('Mario Kart Pad'), reason: code);
      expect(text, contains('NeoStation › Ports › KartPad'), reason: code);
      expect(text, isNot(contains('{')), reason: code);
      texts.add(text);
    }
    expect(texts, hasLength(12), reason: 'every language has its own text');

    String resolve(Locale locale) =>
        PortsLocale.forLocale(locale, 'kartpadRemoved');
    expect(resolve(const Locale('fr')), PortsLocale.values['fr']!['kartpadRemoved']);
    expect(
      resolve(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')),
      PortsLocale.values['zh_Hant']!['kartpadRemoved'],
    );
    expect(resolve(const Locale('zh', 'TW')),
        PortsLocale.values['zh_Hant']!['kartpadRemoved']);
    expect(resolve(const Locale('zh', 'CN')),
        PortsLocale.values['zh']!['kartpadRemoved']);
  });
}
