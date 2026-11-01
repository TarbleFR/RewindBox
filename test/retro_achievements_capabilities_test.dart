import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/retro_achievements_session.dart';
import 'package:neostation/services/libretro_core_catalog.dart';

void main() {
  const supported = RetroAchievementsCapability.supported;
  const unsupported = RetroAchievementsCapability.unsupported;
  const unverified = RetroAchievementsCapability.unverified;

  test('capabilities are checked against the cores actually packaged by the project', () {
    final manifest = jsonDecode(File('build-utils/libretro/cores.json').readAsStringSync()) as Map;
    final packaged = (manifest['cores'] as List).map((value) => (value as Map)['id'] as String).toSet();
    expect(LibretroCoreCatalog.cores.keys.toSet(), packaged);
    expect(packaged, contains('nestopia'));
    expect(packaged, contains('mesen'));
    expect(packaged, isNot(contains('fmsx')));
    expect(packaged, isNot(contains('pcsx_rearmed')));
    for (final entry in LibretroCoreCatalog.systems.entries) {
      for (final core in [entry.value.coreId, ...entry.value.alternatives]) {
        expect(packaged, contains(core), reason: '${entry.key}/$core');
      }
    }
  });

  test('a supported libretro pair must be a real core choice for that exact system', () {
    for (final system in LibretroCoreCatalog.systems.entries) {
      final configured = {system.value.coreId, ...system.value.alternatives};
      for (final core in LibretroCoreCatalog.cores.keys) {
        final capability = RetroAchievementsCapabilities.forEngine('libretro',
          system: system.key, core: core);
        if (capability == supported) {
          expect(configured, contains(core), reason: '${system.key}/$core');
          expect(system.value.achievementsConsoleId, greaterThan(0), reason: system.key);
        } else if (!configured.contains(core)) {
          expect(capability, isNot(supported), reason: '${system.key}/$core');
        }
      }
    }
  });

  test('positive console IDs cannot activate pending or unsupported native systems', () {
    for (final system in ['3ds', '5200', 'gw', 'nes', 'fc', 'nes-hacks', 'fds']) {
      final binding = LibretroCoreCatalog.systems[system]!;
      expect(binding.achievementsConsoleId, greaterThan(0));
      expect(RetroAchievementsCapabilities.forEngine('libretro', system: system,
        core: binding.coreId), unsupported, reason: '$system/${binding.coreId}');
    }
    final pico = LibretroCoreCatalog.systems['pico']!;
    expect(pico.achievementsConsoleId, 0);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'pico', core: pico.coreId), unsupported);
  });

  test('actual alternative cores retain their own capability without changing routing', () {
    expect(LibretroCoreCatalog.systems['nes']!.coreId, 'nestopia');
    expect(LibretroCoreCatalog.systems['nes']!.alternatives, contains('mesen'));
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'nes', core: 'nestopia'), unsupported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'nes', core: 'mesen'), supported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'nes', core: 'mgba'), unsupported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'gb', core: 'gambatte'), supported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'gb', core: 'mgba'), supported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'ps1', core: 'mednafen_psx'), supported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'ps1', core: 'mednafen_psx_hw'), supported);
  });

  test('unverified packaged routes stay unverified until actual memory support is proven', () {
    for (final pair in [('cv', 'gearcoleco'), ('md', 'genesis_plus_gx_wide'),
      ('sms', 'picodrive'), ('mark3', 'picodrive'), ('gg', 'picodrive'), ('gg-hacks', 'picodrive')]) {
      final binding = LibretroCoreCatalog.systems[pair.$1]!;
      expect({binding.coreId, ...binding.alternatives}, contains(pair.$2));
      expect(RetroAchievementsCapabilities.forEngine('libretro', system: pair.$1,
        core: pair.$2), unverified, reason: '${pair.$1}/${pair.$2}');
    }
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'md', core: 'picodrive'), supported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: '32x', core: 'picodrive'), supported);
  });

  test('unknown systems, absent cores and engines without RA never inherit support', () {
    for (final system in ['dos', 'msdos', 'c64', 'zxspectrum', 'zx', 'ti83']) {
      expect(LibretroCoreCatalog.systems.containsKey(system), isFalse, reason: system);
      expect(RetroAchievementsCapabilities.forEngine('libretro', system: system, core: 'mgba'), unsupported);
    }
    for (final core in ['fmsx', 'pcsx_rearmed', 'future-core']) {
      expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'ps1', core: core), unsupported);
    }
    for (final engine in ['melonx', 'rpcs3', 'future-engine']) {
      for (final system in ['switch', 'ps3', 'gc', 'gba']) {
        expect(RetroAchievementsCapabilities.forEngine(engine, system: system, core: 'mgba'), unsupported);
      }
    }
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'gba'), unsupported);
  });

  test('Dolphin and ARMSX2 support only their actual game systems and no system menu', () {
    for (final system in ['gc', 'gamecube', 'wii']) {
      expect(RetroAchievementsCapabilities.forEngine('dolphin', system: system), supported);
      expect(RetroAchievementsCapabilities.forEngine('dolphin', system: system, systemMenu: true), unsupported);
    }
    expect(RetroAchievementsCapabilities.forEngine('armsx2', system: 'ps2'), supported);
    expect(RetroAchievementsCapabilities.forEngine('armsx2', system: 'ps2', systemMenu: true), unsupported);
    expect(RetroAchievementsCapabilities.forEngine('dolphin', system: 'ps2'), unsupported);
    expect(RetroAchievementsCapabilities.forEngine('armsx2', system: 'gc'), unsupported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'gba', core: 'mgba', systemMenu: true), unsupported);
  });
}
