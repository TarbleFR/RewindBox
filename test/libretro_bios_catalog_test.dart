import 'dart:convert';
import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/services/libretro_bios_catalog.dart';
import 'package:neostation/services/libretro_core_catalog.dart';

void main() {
  final catalog = LibretroBiosCatalog.parse(File(LibretroBiosCatalog.assetPath).readAsStringSync());
  final english = LibretroLocale.values['en']!;
  final placeholders = RegExp(r'\{(\w+)\}');

  /// Every LibretroLocale key the checker can show: the requirement data,
  /// the notes the service builds and the keys of the page and Tools row.
  Set<String> checkerKeys() {
    final keys = <String>{
      for (final console in catalog.consoles.values) ...console.noteKeys,
      for (final entry in catalog.entries) ...[
        ...entry.noteKeys,
        if (entry.condition != null) entry.condition!.key,
      ],
    };
    final service = File('lib/services/libretro_bios_check_service.dart').readAsStringSync();
    keys.addAll(RegExp(r"LibretroBiosNote\(\s*'(\w+)'").allMatches(service).map((match) => match[1]!));
    keys.addAll(RegExp(r"\?\s*'(bios\w+)'\s*:\s*'(bios\w+)'").allMatches(service).expand((match) => <String>[match[1]!, match[2]!]));
    for (final file in <String>[
      'lib/screens/libretro/libretro_bios_checker_screen.dart',
      'lib/screens/settings_screen/new_settings_options/tools_settings_content.dart',
    ]) {
      keys.addAll(RegExp(r"'(bios[A-Z]\w*)'").allMatches(File(file).readAsStringSync()).map((match) => match[1]!));
    }
    return keys;
  }

  test('the shipped data parses and names real consoles, cores and systems', () {
    expect(catalog.schema, 1);
    expect(catalog.entries.length, greaterThan(40));
    expect(catalog.consoles.keys.toSet(), LibretroCoreCatalog.consoles.keys.toSet());
    for (final entry in catalog.entries) {
      expect(entry.consoles, isNotEmpty, reason: entry.id);
      for (final console in entry.consoles) {
        expect(LibretroCoreCatalog.consoles, contains(console), reason: entry.id);
      }
      for (final core in entry.cores) {
        expect(LibretroCoreCatalog.cores, contains(core), reason: entry.id);
        // The core runs a system of this console.
        expect(
          LibretroCoreCatalog.systems.values.any((binding) =>
              entry.consoles.contains(binding.console) &&
              (binding.coreId == core || binding.alternatives.contains(core))),
          isTrue,
          reason: '${entry.id}: $core',
        );
      }
      expect(entry.names, isNotEmpty, reason: entry.id);
      expect(entry.locations, isNotEmpty, reason: entry.id);
      for (final core in entry.coreNames.keys) {
        expect(entry.cores, contains(core), reason: entry.id);
      }
      final systems = <String>{
        ...entry.gameFolderSystems,
        ...?entry.condition?.games.expand((clause) => clause.systems),
        ...?entry.condition?.possibleIn,
      };
      for (final system in systems) {
        expect(LibretroCoreCatalog.systems, contains(system), reason: '${entry.id}: $system');
      }
      if (entry.locations.any((location) => location.gameFolder)) {
        expect(entry.gameFolderSystems, isNotEmpty, reason: entry.id);
      }
      for (final dump in entry.knownDumps) {
        expect(dump.md5 ?? dump.sha1, isNotNull, reason: entry.id);
        if (dump.md5 != null) expect(dump.md5, matches(RegExp(r'^[0-9a-f]{32}$')), reason: entry.id);
        if (dump.sha1 != null) expect(dump.sha1, matches(RegExp(r'^[0-9a-f]{40}$')), reason: entry.id);
        if (dump.crc != null) expect(dump.crc, matches(RegExp(r'^[0-9a-f]{8}$')), reason: entry.id);
      }
      if (entry.regional) expect(<String>{'na', 'eu', 'jp'}, contains(entry.region), reason: entry.id);
      if (entry.level == LibretroBiosLevel.bundled) expect(entry.bundledPath, isNotNull, reason: entry.id);
    }
  });

  test('every packaged core is either described or has nothing to check', () {
    final manifest = jsonDecode(File('build-utils/libretro/cores.json').readAsStringSync()) as Map;
    final packaged = <String>{for (final core in manifest['cores'] as List) (core as Map)['id'] as String};
    final described = catalog.entries.expand((entry) => entry.cores).toSet();
    expect(packaged.difference(described), <String>{'azahar'}, reason: 'Azahar needs no BIOS');
    expect(catalog.consoles['3ds']!.noteKeys, contains('biosNoteAzahar'));
  });

  test('the PlayStation rows carry exactly the names of NeoStation’s launch rule', () {
    final rows = catalog.entries.where((entry) => entry.gate == 'psx').toList();
    expect(rows.map((entry) => entry.region), <String>['jp', 'na', 'eu']);
    final gate = <String>{
      for (final entry in rows)
        for (final core in entry.cores) ...LibretroCoreCatalog.cores[core]!.biosAnyOf,
    };
    expect(gate, <String>{'scph5500.bin', 'scph5501.bin', 'scph5502.bin'});
    for (final name in gate) {
      expect(rows.where((entry) => entry.names.contains(name)), hasLength(1), reason: name);
    }
    for (final entry in rows) {
      expect(entry.level, LibretroBiosLevel.required);
      expect(entry.psxChecksumScan, isTrue);
      expect(entry.knownDumps.single.size, 512 * 1024);
    }
  });

  test('files of consoles NeoStation never sends to a core are excluded with a reason', () {
    final fbneoSystems = LibretroCoreCatalog.systems.entries
        .where((binding) => binding.value.coreId == 'fbneo')
        .map((binding) => binding.key)
        .toSet();
    expect(fbneoSystems, <String>{'arc', 'fbneo', 'cps1', 'cps2', 'cps3', 'neogeo'});
    String excluded(String core) => (catalog.excluded
            .where((exclusion) => exclusion.core == core)
            .map((exclusion) => exclusion.path)
            .toList()
          ..sort())
        .join(' ');
    expect(
      excluded('fbneo'),
      'fbneo/channelf.zip fbneo/coleco.zip fbneo/fdsbios.zip fbneo/msx.zip fbneo/ngp.zip '
      'fbneo/spec128.zip fbneo/spec1282a.zip fbneo/spectrum.zip',
    );
    // Genesis Plus GX Wide runs Mega Drive games only.
    final wideConsoles = LibretroCoreCatalog.systems.values
        .where((binding) => binding.coreId == 'genesis_plus_gx_wide' || binding.alternatives.contains('genesis_plus_gx_wide'))
        .map((binding) => binding.console)
        .toSet();
    expect(wideConsoles, <String>{'md'});
    expect(excluded('genesis_plus_gx_wide'),
        'bios.gg bios_CD_E.bin bios_CD_J.bin bios_CD_U.bin bios_E.sms bios_J.sms bios_U.sms');
    expect(excluded('genesis_plus_gx'), isEmpty);
    for (final exclusion in catalog.excluded) {
      expect(exclusion.reason.trim(), isNotEmpty);
      expect(
        catalog.entries.any((entry) =>
            entry.cores.contains(exclusion.core) && entry.names.contains(exclusion.path.split('/').last)),
        isFalse,
        reason: '${exclusion.core} ${exclusion.path}',
      );
    }
  });

  test('every text the checker shows exists in the twelve languages with its placeholders', () {
    final keys = checkerKeys();
    expect(keys.length, greaterThan(60));
    for (final key in keys) {
      expect(english, contains(key), reason: key);
    }
    final englishBios = english.keys.where((key) => key.startsWith('bios')).toSet();
    expect(englishBios.difference(keys), isEmpty, reason: 'unused BIOS checker texts');
    for (final locale in LibretroLocale.values.entries) {
      for (final key in keys) {
        final value = locale.value[key];
        expect(value, isNotNull, reason: '${locale.key}:$key');
        expect(value!.trim(), isNotEmpty, reason: '${locale.key}:$key');
        expect(
          placeholders.allMatches(value).map((match) => match[1]).toSet(),
          placeholders.allMatches(english[key]!).map((match) => match[1]).toSet(),
          reason: '${locale.key}:$key',
        );
        if (locale.key != 'en') expect(value, isNot(english[key]), reason: '${locale.key}:$key');
      }
    }
    // Arguments of the data fill the placeholders of their texts.
    for (final entry in catalog.entries) {
      final condition = entry.condition;
      if (condition == null) continue;
      expect(
        condition.arguments.keys.toSet(),
        placeholders.allMatches(english[condition.key]!).map((match) => match[1]).toSet(),
        reason: entry.id,
      );
    }
  });

  test('Traditional Chinese is selected by script or region for the checker', () {
    for (final locale in <Locale>[
      const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'),
      const Locale('zh', 'TW'),
      const Locale('zh', 'HK'),
      const Locale('zh', 'MO'),
    ]) {
      expect(LibretroLocale.forLocale(locale, 'biosCheckerTitle'), LibretroLocale.values['zh_Hant']!['biosCheckerTitle']);
      expect(
        LibretroLocale.format(locale, 'biosGateMissing', <String, Object?>{'files': 'scph5501.bin'}),
        LibretroLocale.values['zh_Hant']!['biosGateMissing']!.replaceAll('{files}', 'scph5501.bin'),
      );
    }
    expect(LibretroLocale.forLocale(const Locale('zh'), 'biosCheckerTitle'), LibretroLocale.values['zh']!['biosCheckerTitle']);
    expect(LibretroLocale.forLocale(const Locale('fr'), 'biosCheckerTitle'), 'Vérificateur de BIOS');
  });

  test('game file names give their regions', () {
    expect(catalog.regionsOf('Sonic CD (USA).cue'), <String>{'na'});
    expect(catalog.regionsOf('Snatcher (Europe) (En,Fr).cue'), <String>{'eu'});
    expect(catalog.regionsOf('Crash (USA, Europe).cue'), <String>{'na', 'eu'});
    expect(catalog.regionsOf('Lunar (Japan) (Rev 1).cue'), <String>{'jp'});
    expect(catalog.regionsOf('Game (World).cue'), isEmpty);
    expect(catalog.regionsOf('Homebrew [!].cue'), isEmpty);
  });

  test('option conditions use the stored value, else the core default', () {
    const condition = LibretroBiosOptionCondition(keys: <String>['a', 'b'], enabled: <String>{'on'}, defaultValue: 'off');
    expect(condition.isOn(const <String, String>{}), isFalse);
    expect(condition.isOn(const <String, String>{'b': 'on'}), isTrue);
    expect(condition.isOn(const <String, String>{'a': 'off', 'b': 'on'}), isFalse);
  });
}
