import 'dart:io';
import 'dart:ui' show Locale;

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/armsx2_ui_locale.dart';
import 'package:neostation/l10n/launch_prerequisite_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/services/launch_prerequisites.dart';
import 'package:neostation/services/libretro_bios_catalog.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/local_dev_vpn_route_service.dart';
import 'package:path/path.dart' as path;

/// A launch that cannot start says what is missing and what to do about it:
/// LocalDevVPN off, no pairing file, an installation without JIT, an iOS
/// that is too old, no PS2 BIOS, a BIOS only some retro games need.
void main() {
  const languages = <String>['en', 'fr', 'de', 'es', 'it', 'pt', 'ru', 'id', 'ja', 'ko', 'zh', 'zh_Hant'];

  group('what a failure points to', () {
    test('the route probe, whatever its code', () {
      for (final code in <String>[
        'localdevvpn_route_unavailable',
        'localdevvpn_route_probe_timeout',
        'localdevvpn_route_invalid_response',
        'localdevvpn_route_probe_failed',
      ]) {
        expect(
          LaunchPrerequisites.classify(LocalDevVpnRouteException(code: code, message: 'x')),
          LaunchPrerequisite.localDevVpn,
          reason: code,
        );
      }
      expect(
        LaunchPrerequisites.classify(const LocalDevVpnRouteException(code: 'unsupported_platform', message: 'x')),
        isNull,
      );
      expect(
        LaunchPrerequisites.classify(PlatformException(code: 'localdevvpn_route_unavailable')),
        LaunchPrerequisite.localDevVpn,
      );
    });

    test('the route message names RemotePairing: it is the VPN, not the pairing file', () {
      expect(
        LaunchPrerequisites.classifyText(
          'LocalDevVPN did not expose RemotePairing at 10.7.0.1:49152 (state=failed, elapsedMs=2000).',
        ),
        LaunchPrerequisite.localDevVpn,
      );
      expect(
        LaunchPrerequisites.classifyText('stikjit.localdevvpn_route_failed localdevvpn_route_unavailable x'),
        LaunchPrerequisite.localDevVpn,
      );
    });

    test('the sentences of the native JIT bridges', () {
      const cases = <String, LaunchPrerequisite>{
        'Embedded RPCS3 requires iOS 17.4 or newer.': LaunchPrerequisite.iosVersion,
        'Embedded ARMSX2 requires iOS 17.4 or newer.': LaunchPrerequisite.iosVersion,
        'This RewindBox installation does not preserve get-task-allow.': LaunchPrerequisite.developmentSignature,
        'This RewindBox installation does not preserve get-task-allow; Dolphin JIT is blocked.':
            LaunchPrerequisite.developmentSignature,
        'Import a readable pairing file before enabling MeloNX JIT.': LaunchPrerequisite.pairingFile,
        'The stored pairing file could not be read.': LaunchPrerequisite.pairingFile,
        'Pairing file selection was cancelled.': LaunchPrerequisite.pairingFile,
        'stikjit.pairing_missing Import a pairing file in RewindBox before launching Dolphin.':
            LaunchPrerequisite.pairingFile,
        'An RPCS3 JIT operation is already running.': LaunchPrerequisite.jitBusy,
        'An ARMSX2 launch is already active.': LaunchPrerequisite.jitBusy,
        'Could not launch the ARMSX2 JIT helper.': LaunchPrerequisite.jitHelper,
        'StikJIT detached without leaving RewindBox JIT-enabled.': LaunchPrerequisite.jitHelper,
        'Bad state: ARMSX2 JIT attachment failed.': LaunchPrerequisite.jitHelper,
        'The RewindBox process no longer has JIT authorization.': LaunchPrerequisite.jitHelper,
      };
      cases.forEach((text, expected) {
        expect(LaunchPrerequisites.classifyText(text), expected, reason: text);
        expect(LaunchPrerequisites.classify(StateError(text)), expected, reason: text);
      });
    });

    test('anything else names no prerequisite: the caller keeps its own text', () {
      expect(LaunchPrerequisites.classify(null), isNull);
      expect(LaunchPrerequisites.classifyText(null), isNull);
      expect(LaunchPrerequisites.classifyText(''), isNull);
      expect(LaunchPrerequisites.classifyText('ARMSX2 boot failed.'), isNull);
      expect(LaunchPrerequisites.classify(const FileSystemException('Cannot open file')), isNull);
    });

    test('the phrases are the ones the native bridges and the probe write', () {
      const bridges = <String>[
        'packages/armsx2_internal_bridge/ios/Classes/Armsx2JitBridgePlugin.mm',
        'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3JitBridgePlugin.mm',
        'packages/melonx_internal_bridge/ios/Classes/MeloNXJitBridgePlugin.mm',
      ];
      for (final file in bridges) {
        final source = File(file).readAsStringSync();
        for (final phrase in <String>[
          'requires iOS 17.4 or newer.',
          'does not preserve get-task-allow.',
          'Import a readable pairing file before enabling',
          'JIT operation is already running.',
        ]) {
          expect(source, contains(phrase), reason: '$file: $phrase');
          expect(LaunchPrerequisites.classifyText(phrase), isNotNull, reason: phrase);
        }
      }
      final dolphin = File('packages/dolphin_internal_bridge/ios/Classes/DolphinInternalBridgePlugin.mm').readAsStringSync();
      expect(dolphin, contains('does not preserve get-task-allow'));
      final probe = File('packages/stikjit_bridge/lib/stikjit_bridge.dart').readAsStringSync();
      expect(probe, contains("code: 'localdevvpn_route_unavailable'"));
      expect(probe, contains('LocalDevVPN did not expose RemotePairing'));
    });
  });

  group('the sentences', () {
    const keys = <String>[
      'localDevVpn',
      'pairingFile',
      'developmentSignature',
      'iosVersion',
      'jitBusy',
      'jitHelper',
      'ps2BiosMissing',
      'ps2BiosCancelled',
      'gameUnreadable',
      'ps2GameOutside',
    ];

    test('every prerequisite has its sentence in the twelve languages', () {
      expect(LaunchPrerequisiteLocale.values.keys, unorderedEquals(languages));
      final english = LaunchPrerequisiteLocale.values['en']!;
      expect(english.keys, unorderedEquals(keys));
      for (final prerequisite in LaunchPrerequisite.values) {
        expect(keys, contains(prerequisite.key));
      }
      for (final language in languages) {
        final table = LaunchPrerequisiteLocale.values[language]!;
        expect(table.keys, unorderedEquals(keys), reason: language);
        for (final key in keys) {
          final text = table[key]!;
          expect(text.trim(), isNotEmpty, reason: '$language $key');
          if (language != 'en') expect(text, isNot(english[key]), reason: '$language $key');
        }
        // What the sentence must still name, whatever the language.
        expect(table['localDevVpn'], contains('LocalDevVPN'), reason: language);
        expect(table['pairingFile'], contains('.mobiledevicepairing'), reason: language);
        expect(table['developmentSignature'], contains('get-task-allow'), reason: language);
        expect(table['iosVersion'], contains('17.4'), reason: language);
        expect(table['ps2BiosMissing'], contains('{action}'), reason: language);
        expect(table['ps2GameOutside'], contains('ARMSX2'), reason: language);
      }
    });

    test('the PS2 BIOS sentence names the import action of the PlayStation 2 list', () {
      for (final language in languages) {
        final action = Armsx2UiLocale.textFor(language, 'importBios');
        final text = LaunchPrerequisiteLocale.textFor(language, 'ps2BiosMissing', {'action': action});
        expect(text, contains(action), reason: language);
        expect(text, isNot(contains('{action}')), reason: language);
      }
    });

    test('a locale gives its own table, Traditional Chinese apart', () {
      expect(LaunchPrerequisiteLocale.languageOf(const Locale('fr')), 'fr');
      expect(LaunchPrerequisiteLocale.languageOf(const Locale('zh')), 'zh');
      expect(LaunchPrerequisiteLocale.languageOf(const Locale('zh', 'TW')), 'zh_Hant');
      expect(
        LaunchPrerequisiteLocale.languageOf(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')),
        'zh_Hant',
      );
      expect(LaunchPrerequisiteLocale.languageOf(const Locale('sv')), 'en');
    });

    test('every key the PS2 launch records is a sentence', () {
      final source = File('lib/services/stikjit_armsx2_service.dart').readAsStringSync();
      final literal = RegExp(r"'(ps2[A-Za-z]+|gameUnreadable)'");
      final recorded = literal.allMatches(source).map((match) => match.group(1)!).toSet();
      expect(recorded, containsAll(<String>['ps2BiosMissing', 'ps2BiosCancelled', 'ps2GameOutside', 'gameUnreadable']));
      for (final key in recorded) {
        expect(LaunchPrerequisiteLocale.values['en'], contains(key), reason: key);
      }
    });
  });

  group('a BIOS only some retro games need', () {
    late LibretroBiosCatalog catalog;
    late Directory root;
    late String system;
    late String games;

    setUpAll(() {
      catalog = LibretroBiosCatalog.parse(File('assets/data/libretro_bios_requirements.json').readAsStringSync());
    });

    setUp(() {
      root = Directory.systemTemp.createTempSync('conditional-bios-');
      system = path.join(root.path, 'System');
      games = path.join(root.path, 'Games');
      Directory(system).createSync();
      Directory(games).createSync();
    });

    tearDown(() => root.deleteSync(recursive: true));

    void put(String directory, String name) => File(path.join(directory, name))
      ..createSync(recursive: true)
      ..writeAsStringSync('x');

    Future<List<String>> missing(String systemKey, String file, String core,
            [Map<String, String> options = const <String, String>{}]) =>
        LibretroInternalService.missingConditionalBios(
          catalog: catalog,
          system: systemKey,
          romPath: path.join(games, file),
          coreId: core,
          systemDirectory: system,
          options: options,
        );

    test('64DD names the file with its System sub-folder', () async {
      expect(await missing('n64', 'Game.ndd', 'mupen64plus_next'), ['Mupen64plus/IPL.n64']);
      put(path.join(system, 'Mupen64plus'), 'IPL.n64');
      expect(await missing('n64', 'Game.ndd', 'mupen64plus_next'), isEmpty);
    });

    test('PC Engine CD: another System Card selected closes the syscard3 entry', () async {
      expect(await missing('pccd', 'Game.cue', 'mednafen_pce_fast'), ['syscard3.pce']);
      expect(await missing('pccd', 'Game.cue', 'mednafen_pce_fast', {'pce_fast_cdbios': 'System Card 2'}), isEmpty);
    });

    test('Mesen reads FdsBios.bin first', () async {
      expect(await missing('nes', 'Zelda.fds', 'mesen'), ['FdsBios.bin']);
      put(system, 'FdsBios.bin');
      expect(await missing('nes', 'Zelda.fds', 'mesen'), isEmpty);
    });

    test('a Mega-CD disc without any regional BIOS names the three, one is enough', () async {
      expect(await missing('mcd', 'Sonic CD.chd', 'genesis_plus_gx'), ['bios_CD_U.bin / bios_CD_E.bin / bios_CD_J.bin']);
      put(system, 'bios_CD_E.bin');
      expect(await missing('mcd', 'Sonic CD.chd', 'genesis_plus_gx'), isEmpty);
    });

    test('each core is asked for the names it reads', () async {
      // PicoDrive reads its own names first; one of them is enough.
      expect((await missing('scd', 'Game.cue', 'picodrive')).single, startsWith('us_scd2_9306.bin'));
      put(system, 'eu_mcd2_9306.bin');
      expect(await missing('scd', 'Game.cue', 'picodrive'), isEmpty);
      // That file is not one Genesis Plus GX reads.
      expect(await missing('scd', 'Game.cue', 'genesis_plus_gx'), isNotEmpty);
    });

    test('a Famicom disk needs disksys.rom, a cartridge of the same console does not', () async {
      expect(await missing('nes', 'Zelda.fds', 'nestopia'), ['disksys.rom']);
      expect(await missing('nes', 'Zelda.nes', 'nestopia'), isEmpty);
      put(system, 'disksys.rom');
      expect(await missing('nes', 'Zelda.fds', 'nestopia'), isEmpty);
    });

    test('a Neo Geo set finds its BIOS next to the game or in a folder of the core', () async {
      expect(await missing('neogeo', 'mslug.zip', 'fbneo'), ['neogeo.zip']);
      put(games, 'neogeo.zip');
      expect(await missing('neogeo', 'mslug.zip', 'fbneo'), isEmpty);
      File(path.join(games, 'neogeo.zip')).deleteSync();
      put(path.join(system, 'fbneo'), 'neogeo.zip');
      expect(await missing('neogeo', 'mslug.zip', 'fbneo'), isEmpty);
    });

    test('a console without conditional file, or another core, is never told anything', () async {
      expect(await missing('gba', 'Game.gba', 'mgba'), isEmpty);
      expect(await missing('mcd', 'Sonic CD.chd', 'snes9x'), isEmpty);
    });

    test('only a game the core refused or stopped is looked at', () {
      expect(LibretroInternalService.conditionalBiosFailureCodes, {'LIBRETRO_GAME_REJECTED', 'LIBRETRO_CORE_STOPPED'});
    });

    test('the sentence names the file and where it goes, in the twelve languages', () {
      const locales = <Locale>[
        Locale('en'),
        Locale('fr'),
        Locale('de'),
        Locale('es'),
        Locale('it'),
        Locale('pt'),
        Locale('ru'),
        Locale('id'),
        Locale('ja'),
        Locale('ko'),
        Locale('zh'),
        Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      ];
      final english = LibretroLocale.launchError(const Locale('en'), 'LIBRETRO_BIOS_CONDITIONAL_MISSING', 'disksys.rom');
      expect(english, startsWith('This game needs a BIOS that is not installed: disksys.rom.'));
      final seen = <String>{};
      for (final locale in locales) {
        final text = LibretroLocale.launchError(locale, 'LIBRETRO_BIOS_CONDITIONAL_MISSING', 'disksys.rom');
        expect(text, contains('disksys.rom'), reason: '$locale');
        expect(text, contains('RewindBox › Libretro › System'), reason: '$locale');
        expect(text, isNot(contains('{files}')), reason: '$locale');
        expect(seen.add(text), isTrue, reason: 'a translation of its own for $locale');
      }
    });

    test('the outcome keeps what the core answered next to the file names', () {
      const outcome = LibretroLaunchOutcome(
        success: false,
        errorCode: 'LIBRETRO_BIOS_CONDITIONAL_MISSING',
        technicalDetails: 'Core: nestopia\nCode: LIBRETRO_GAME_REJECTED',
        missingFiles: 'disksys.rom',
      );
      expect(outcome.messageFiles, 'disksys.rom');
      expect(outcome.technicalDetails, contains('LIBRETRO_GAME_REJECTED'));
      // The codes that had no separate file list keep theirs.
      const required = LibretroLaunchOutcome(success: false, errorCode: 'LIBRETRO_BIOS_MISSING', technicalDetails: 'scph5501.bin');
      expect(required.messageFiles, 'scph5501.bin');
    });
  });
}
