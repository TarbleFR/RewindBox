import 'package:flutter/foundation.dart';

@immutable
class RetroAchievementsPreferences {
  const RetroAchievementsPreferences({this.enabled = false, this.hardcore = false, this.migrationVersion = 0});
  final bool enabled;
  final bool hardcore;
  final int migrationVersion;

  RetroAchievementsPreferences copyWith({bool? enabled, bool? hardcore, int? migrationVersion}) =>
      RetroAchievementsPreferences(enabled: enabled ?? this.enabled,
        hardcore: hardcore ?? this.hardcore, migrationVersion: migrationVersion ?? this.migrationVersion);

  factory RetroAchievementsPreferences.fromRow(Map<String, Object?> row) =>
      RetroAchievementsPreferences(enabled: row['enabled'] == 1, hardcore: row['hardcore'] == 1,
        migrationVersion: (row['migration_version'] as num?)?.toInt() ?? 0);
}

enum RetroAchievementsCapability { supported, unsupported, unverified }

@immutable
class RetroAchievementsMigrationCandidate {
  const RetroAchievementsMigrationCandidate({required this.id, required this.username,
    required this.sources, required this.enabled, required this.hardcore});
  final String id;
  final String username;
  final List<String> sources;
  final bool enabled;
  final bool hardcore;

  factory RetroAchievementsMigrationCandidate.fromMap(Map<Object?, Object?> value) =>
    RetroAchievementsMigrationCandidate(id: value['id'] as String,
      username: value['username'] as String,
      sources: List<String>.unmodifiable((value['sources'] as List).cast<String>()),
      enabled: value['enabled'] == true, hardcore: value['hardcore'] == true);
}

/// Console IDs identify a system; they are not evidence that a particular core
/// exposes the memory required by achievements. Keep this separate from routing.
abstract final class RetroAchievementsCapabilities {
  static RetroAchievementsCapability forEngine(String engine, {String? system, String? core, bool systemMenu = false}) {
    if (systemMenu) return RetroAchievementsCapability.unsupported;
    if (engine == 'dolphin') {
      return const {'gc', 'gamecube', 'wii'}.contains(system)
          ? RetroAchievementsCapability.supported : RetroAchievementsCapability.unsupported;
    }
    if (engine == 'armsx2') {
      return system == 'ps2'
          ? RetroAchievementsCapability.supported : RetroAchievementsCapability.unsupported;
    }
    if (engine != 'libretro') return RetroAchievementsCapability.unsupported;
    if (const {'3ds', '5200', 'gw', 'pico'}.contains(system) ||
        const {'azahar', 'a5200', 'gw', 'nestopia'}.contains(core)) {
      return RetroAchievementsCapability.unsupported;
    }
    if (const {'gearcoleco', 'genesis_plus_gx_wide'}.contains(core) ||
        (core == 'picodrive' && const {'sms', 'mark3', 'gg', 'gg-hacks'}.contains(system))) {
      return RetroAchievementsCapability.unverified;
    }
    // Closed pairs: neither a new core nor an unrelated console inherits RA.
    return (_supportedSystemsByCore[core]?.contains(system) ?? false)
        ? RetroAchievementsCapability.supported : RetroAchievementsCapability.unsupported;
  }

  static const _supportedSystemsByCore = <String, Set<String>>{
    'mesen': {'nes', 'fc', 'nes-hacks', 'fds'},
    'snes9x': {'snes', 'sfc', 'snes-hacks', 'sfc-hacks', 'satellaview'},
    'gambatte': {'gb', 'gb-hacks', 'gbc', 'gbc-hacks'},
    'mgba': {'gb', 'gb-hacks', 'gbc', 'gbc-hacks', 'gba', 'gba-hacks'},
    'genesis_plus_gx': {'md', 'genesis', 'md-hacks', 'gen-hacks', 'mcd', 'scd', 'sms', 'mark3', 'gg', 'gg-hacks', 'sg1k'},
    'picodrive': {'md', 'genesis', 'md-hacks', 'gen-hacks', 'mcd', 'scd', '32x'},
    'fbneo': {'arc', 'fbneo', 'cps1', 'cps2', 'cps3', 'neogeo'},
    'desmume': {'ds'}, 'mupen64plus_next': {'n64'},
    'mednafen_psx_hw': {'ps1'}, 'mednafen_psx': {'ps1'}, 'ppsspp': {'psp', 'pspminis'},
    'mednafen_pce_fast': {'pce', 'tg16', 'pccd', 'tgcd'},
    'mednafen_wswan': {'ws', 'wsc'}, 'mednafen_ngp': {'ngp', 'ngpc'},
    'handy': {'lynx'}, 'mednafen_vb': {'vb'}, 'stella': {'2600'}, 'prosystem': {'7800'},
    'pokemini': {'mini'}, 'sameduck': {'duck'}, 'potator': {'wsv'}, 'ardens': {'ard'},
    'wasm4': {'wasm4'}, 'uzem': {'uze'}, 'freechaf': {'chf'}, 'freeintv': {'intv'},
    'o2em': {'mo2'}, 'mednafen_pcfx': {'pcfx'},
  };
}

@immutable
class RetroAchievementsSessionState {
  const RetroAchievementsSessionState(this.values);
  final Map<String, Object?> values;
  String get id => values['sessionId'] as String? ?? '';
  String get engine => values['engine'] as String? ?? '';
  bool get running => values['ended'] != true && id.isNotEmpty;
  bool get enabled => values['enabled'] == true;
  bool get supported => values['supported'] == true;
  bool get active => values['active'] == true;
  bool get gameLoaded => values['gameLoaded'] == true;
  bool get hardcoreActive => values['hardcoreActive'] == true;
  int get generation => (values['generation'] as num?)?.toInt() ?? 0;
  String? get errorCode => values['errorCode'] as String?;
}
