import '../models/system_model.dart';
import 'libretro_core_catalog.dart';
import 'libretro_internal_service.dart';

/// What runs a console's games on iOS.
enum ConsoleEngine {
  /// A libretro core embedded in NeoStation ("RetroArch built in").
  libretro,

  /// Dolphin (GameCube, Wii), embedded.
  dolphin,

  /// ARMSX2 (PlayStation 2), embedded.
  armsx2,

  /// RPCS3 (PlayStation 3), embedded.
  rpcs3,

  /// KartPad and Dusklight (Ports), embedded.
  ports,

  /// The MeloNX app (Nintendo Switch), external.
  melonx,

  /// The RetroArch app, external.
  retroarch,
}

/// A console of the Consoles tab (Build 448): one line per console the iOS
/// app can run, whatever runs it.
class ConsoleEntry {
  const ConsoleEntry({
    required this.id,
    required this.name,
    required this.engine,
    required this.importSystem,
    required this.systems,
    this.libretro,
  });

  /// Stable id: the libretro console id ("md", "psx"...) for the consoles of
  /// the embedded libretro engine, otherwise the system id ("gc", "ps2",
  /// "2600"...). Ids never collide (see test/console_catalog_test.dart).
  final String id;

  /// Product name, never translated.
  final String name;
  final ConsoleEngine engine;

  /// System (an `assets/systems` id) put in the main menu for the console.
  final String importSystem;

  /// Canonical system keys standing for the console in the main menu.
  final Set<String> systems;

  /// The embedded libretro console, for its games import and skins.
  final LibretroConsole? libretro;

  /// The console's games can run in an engine embedded in NeoStation, which
  /// the user may switch off (Consoles tab, Settings › General).
  bool get hasEmbeddedEngine =>
      engine != ConsoleEngine.melonx && engine != ConsoleEngine.retroarch;

  /// With the embedded engine off, the RetroArch app takes the games (all of
  /// them for libretro consoles; for the PlayStation 2, the games outside
  /// NeoStation's ARMSX2 folder only).
  bool get retroArchFallback =>
      engine == ConsoleEngine.libretro || engine == ConsoleEngine.armsx2;

  /// Logo of the console in `assets/images/logos`.
  String get logoAsset => 'assets/images/logos/$importSystem.webp';
}

/// Every console of the iOS app, built from the engines it ships and from
/// the systems whose `assets/systems` definition names an iOS emulator.
abstract final class ConsoleCatalog {
  /// Systems run only by the RetroArch app on iOS (their `assets/systems`
  /// definition names `url_scheme: retroarch` and no embedded engine binds
  /// them), with their product names. Checked against the assets by
  /// test/console_manager_test.dart.
  ///
  /// A system whose console moves to the embedded libretro engine leaves
  /// this list and becomes a [LibretroCoreCatalog.consoles] entry with the
  /// same id and product name, so a console added from the Consoles tab or
  /// switched off there keeps its stored choice (lots 1 and 2:
  /// docs/libretro-consoles-lot1.md, docs/libretro-consoles-lot2.md).
  static const Map<String, String> retroArchSystems = <String, String>{
    '3do': 'Panasonic 3DO',
    'a2': 'Apple II',
    'a2001': 'Emerson Arcadia 2001',
    'amiga': 'Commodore Amiga',
    'ast': 'Atari ST',
    'aw': 'Atomiswave',
    'bbcmicro': 'BBC Micro',
    'c64': 'Commodore 64',
    'cdi': 'Philips CD-i',
    'cpc': 'Amstrad CPC',
    'dc': 'Sega Dreamcast',
    'dos': 'MS-DOS',
    'jag': 'Atari Jaguar',
    'mame': 'M.A.M.E.',
    'msx': 'MSX',
    'naomi': 'Sega Naomi',
    'naomi2': 'Sega Naomi 2',
    'naomigd': 'Sega Naomi GD-ROM',
    'ngcd': 'Neo Geo CD',
    'palm': 'Palm OS',
    'pc88': 'NEC PC-8801',
    'pc98': 'NEC PC-9801',
    'pet': 'Commodore - PET',
    'pico8': 'PICO-8',
    'plus4': 'Commodore - PLUS/4',
    'rpgmaker': 'RPG Maker',
    'sat': 'Sega Saturn',
    'scummvm': 'ScummVM',
    'sharpx68000': 'Sharp X68000',
    'tic80': 'TIC-80',
    'vc4k': 'Interton VC 4000',
    'vect': 'Vectrex',
    'vic20': 'VIC-20',
    'x1': 'Sharp X1',
    'zx81': 'ZX 81',
    'zxspectrum': 'ZX Spectrum',
  };

  /// Systems the libretro engine runs while being other hardware than their
  /// bound console (the Sega Pico runs on PicoDrive with the Mega Drive
  /// settings): listed as their own console.
  static const Map<String, String> libretroOtherHardware = <String, String>{
    'pico': 'Sega Pico',
  };

  static final List<ConsoleEntry> entries = List<ConsoleEntry>.unmodifiable(
    _build(),
  );

  static final Map<String, ConsoleEntry> _byId = <String, ConsoleEntry>{
    for (final entry in entries) entry.id: entry,
  };

  static final Map<String, String> _bySystem = <String, String>{
    for (final entry in entries)
      for (final system in entry.systems) system: entry.id,
  };

  static ConsoleEntry? byId(String id) => _byId[id];

  static List<ConsoleEntry> _build() {
    final libretroSystems = <String, Set<String>>{};
    for (final binding in LibretroCoreCatalog.systems.entries) {
      if (libretroOtherHardware.containsKey(binding.key)) continue;
      libretroSystems
          .putIfAbsent(binding.value.console, () => <String>{})
          .add(binding.key);
    }
    return <ConsoleEntry>[
      for (final console in LibretroCoreCatalog.consoles.values)
        ConsoleEntry(
          id: console.id,
          name: console.name,
          engine: ConsoleEngine.libretro,
          importSystem: console.importSystem,
          systems: Set<String>.unmodifiable(
            libretroSystems[console.id] ?? <String>{console.importSystem},
          ),
          libretro: console,
        ),
      for (final other in libretroOtherHardware.entries)
        ConsoleEntry(
          id: other.key,
          name: other.value,
          engine: ConsoleEngine.libretro,
          importSystem: other.key,
          systems: <String>{other.key},
        ),
      const ConsoleEntry(
        id: 'gc',
        name: 'Nintendo GameCube',
        engine: ConsoleEngine.dolphin,
        importSystem: 'gc',
        systems: <String>{'gc'},
      ),
      const ConsoleEntry(
        id: 'wii',
        name: 'Nintendo Wii',
        engine: ConsoleEngine.dolphin,
        importSystem: 'wii',
        systems: <String>{'wii'},
      ),
      const ConsoleEntry(
        id: 'ps2',
        name: 'PlayStation 2',
        engine: ConsoleEngine.armsx2,
        importSystem: 'ps2',
        systems: <String>{'ps2'},
      ),
      const ConsoleEntry(
        id: 'ps3',
        name: 'PlayStation 3',
        engine: ConsoleEngine.rpcs3,
        importSystem: 'ps3',
        systems: <String>{'ps3'},
      ),
      const ConsoleEntry(
        id: 'ports',
        name: 'Ports',
        engine: ConsoleEngine.ports,
        importSystem: 'ports',
        systems: <String>{'ports'},
      ),
      const ConsoleEntry(
        id: 'switch',
        name: 'Nintendo Switch',
        engine: ConsoleEngine.melonx,
        importSystem: 'switch',
        systems: <String>{'switch'},
      ),
      for (final system in retroArchSystems.entries)
        ConsoleEntry(
          id: system.key,
          name: system.value,
          engine: ConsoleEngine.retroarch,
          importSystem: system.key,
          systems: <String>{system.key},
        ),
    ];
  }

  /// Canonical key of a system: its libretro binding when it has one (a
  /// copy named after an alias folder still resolves), otherwise its id,
  /// otherwise its folder name.
  static String systemKey(SystemModel system) {
    final libretro = LibretroInternalService.systemKey(system);
    if (LibretroCoreCatalog.handles(libretro)) return libretro;
    final id = system.id?.trim().toLowerCase();
    if (id != null && id.isNotEmpty && _bySystem.containsKey(id)) return id;
    return system.folderName.trim().toLowerCase();
  }

  /// Console a system stands for, null for a system the iOS app does not
  /// run (virtual systems such as "all" or "favorites" included).
  static ConsoleEntry? entryForSystem(SystemModel system) =>
      entryForKey(systemKey(system));

  static ConsoleEntry? entryForKey(String key) {
    final id = _bySystem[key.trim().toLowerCase()];
    return id == null ? null : _byId[id];
  }
}
