import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;

import 'libretro_core_catalog.dart';
import 'libretro_core_option_store.dart';
import 'libretro_internal_service.dart';
import 'libretro_resolution.dart';
import 'logger_service.dart';

/// One core's internal resolution as the console settings show it.
class LibretroCoreResolution {
  const LibretroCoreResolution({
    required this.core,
    this.libraryName = '',
    this.key,
    this.choices = const <LibretroResolutionChoice>[],
    this.coreDefault,
    this.neoStationDefault,
    this.apply = LibretroResolutionApply.relaunch,
    this.detected = false,
    this.stored,
    this.gamesWithOwnValue = 0,
  });

  final LibretroCore core;

  /// `library_name` of the core, which names `Config/<library>.json`; empty
  /// when NeoStation does not know it (nothing can be saved then).
  final String libraryName;

  /// The core option, null for a core without internal resolution.
  final String? key;
  final List<LibretroResolutionChoice> choices;
  final String? coreDefault;

  /// NeoStation's default for the option (`optionDefaults` of the catalog).
  final String? neoStationDefault;
  final LibretroResolutionApply apply;

  /// The values come from the core's own declaration at its last launch
  /// (`Config/Resolution/<core>.json`); false: from the catalog's
  /// declaration of the pinned build.
  final bool detected;

  /// The value saved for every game of the core, null when none.
  final String? stored;

  /// Games with a resolution of their own (`Config/Games/<library>.json`).
  final int gamesWithOwnValue;

  bool get supported => key != null && choices.length >= 2 && libraryName.isNotEmpty;

  LibretroResolutionChoice? get native {
    for (final choice in choices) {
      if (choice.isNative) return choice;
    }
    return null;
  }

  bool _offers(String? value) => value != null && choices.any((choice) => choice.value == value);

  /// What every game without a value of its own gets: the saved value, else
  /// NeoStation's default, else the native resolution (applied by the
  /// session when the core's own default is another one), else the core's
  /// default. Mirrors `LibretroCoreOptions valueForEveryGameForKey:` with
  /// the session's native default.
  String? get current {
    if (!supported) return null;
    if (_offers(stored)) return stored;
    if (_offers(neoStationDefault)) return neoStationDefault;
    return native?.value ?? coreDefault;
  }
}

/// Reads and saves the internal resolution of the embedded cores outside a
/// game (System Settings › Emulators, Consoles tab). The value is the same
/// one the in-game menu saves for every game of the core
/// (`Config/<library>.json`, through [LibretroCoreOptionStore], refused
/// while a game runs); a game's own value, set in the in-game menu, is
/// never touched and keeps priority.
class LibretroResolutionService {
  LibretroResolutionService({
    Future<Directory> Function()? configDirectory,
    LibretroCoreOptionStore? store,
  })  : configDirectory = configDirectory ?? LibretroInternalService.configDirectory,
        store = store ?? LibretroCoreOptionStore(configDirectory: configDirectory);

  /// `Documents/Libretro/Config` in production.
  final Future<Directory> Function() configDirectory;
  final LibretroCoreOptionStore store;

  static final _log = LoggerService.instance;

  /// Cores that run [console] (a key of [LibretroCoreCatalog.consoles]):
  /// the default cores of its systems first, then their alternatives, once
  /// each, in the catalog's order.
  static List<LibretroCore> coresForConsole(String console) {
    final bindings = LibretroCoreCatalog.systems.values.where((binding) => binding.console == console);
    final ids = <String>[];
    for (final binding in bindings) {
      if (!ids.contains(binding.coreId)) ids.add(binding.coreId);
    }
    for (final binding in bindings) {
      for (final id in binding.alternatives) {
        if (!ids.contains(id)) ids.add(id);
      }
    }
    return <LibretroCore>[
      for (final id in ids)
        if (LibretroCoreCatalog.cores[id] != null) LibretroCoreCatalog.cores[id]!,
    ];
  }

  /// Whether [core] is the default core of one of [console]'s systems.
  static bool isDefaultFor(LibretroCore core, String console) => LibretroCoreCatalog.systems.values
      .any((binding) => binding.console == console && binding.coreId == core.id);

  Future<List<LibretroCoreResolution>> forConsole(String console) async => <LibretroCoreResolution>[
        for (final core in coresForConsole(console)) await forCore(core, console: console),
      ];

  Future<LibretroCoreResolution> forCore(LibretroCore core, {String? console}) async {
    final consoleEntry = console != null ? LibretroCoreCatalog.consoles[console] : null;
    final consoleSize = consoleEntry == null ? null : <int>[consoleEntry.width, consoleEntry.height];
    final directory = await configDirectory();
    final snapshot = await _readJson(p.join(directory.path, 'Resolution', '${core.id}.json'));
    LibretroCoreResolution resolution;
    if (snapshot != null && snapshot['coreId'] == core.id && snapshot['libraryName'] is String) {
      resolution = _fromSnapshot(core, snapshot);
    } else {
      resolution = _fromDeclaration(core, consoleSize);
    }
    if (!resolution.supported) return resolution;
    final stored = await store.read(resolution.libraryName);
    final games = await _readJson(
      p.join(directory.path, 'Games', LibretroCoreOptionStore.libraryFileName(resolution.libraryName)),
    );
    var own = 0;
    final entries = games?['games'];
    if (entries is Map) {
      for (final values in entries.values) {
        if (values is Map && values[resolution.key] is String) own++;
      }
    }
    return LibretroCoreResolution(
      core: core,
      libraryName: resolution.libraryName,
      key: resolution.key,
      choices: resolution.choices,
      coreDefault: resolution.coreDefault,
      neoStationDefault: resolution.neoStationDefault,
      apply: resolution.apply,
      detected: resolution.detected,
      stored: stored[resolution.key],
      gamesWithOwnValue: own,
    );
  }

  LibretroCoreResolution _fromDeclaration(LibretroCore core, List<int>? consoleSize) {
    final declaration = core.resolution;
    if (declaration == null) return LibretroCoreResolution(core: core);
    final profile = LibretroResolution.profileFor(declaration.key);
    return LibretroCoreResolution(
      core: core,
      libraryName: declaration.libraryName,
      key: declaration.key,
      choices: LibretroResolution.choices(
        declaration.values,
        nativeSize: profile?.nativeSize,
        consoleSize: consoleSize,
        maxFactor: profile?.maxFactor ?? 0,
      ),
      coreDefault: declaration.coreDefault,
      neoStationDefault: core.optionDefaults[declaration.key],
      apply: profile?.apply ?? LibretroResolutionApply.relaunch,
    );
  }

  /// The native session's record of the core's last launch; a malformed
  /// entry counts as a core without internal resolution.
  LibretroCoreResolution _fromSnapshot(LibretroCore core, Map<String, Object?> snapshot) {
    final libraryName = snapshot['libraryName'] as String;
    final internal = snapshot['internalResolution'];
    if (internal is! Map) return LibretroCoreResolution(core: core, libraryName: libraryName, detected: true);
    final key = internal['key'];
    final list = internal['choices'];
    if (key is! String || key.isEmpty || list is! List) {
      return LibretroCoreResolution(core: core, libraryName: libraryName, detected: true);
    }
    final choices = <LibretroResolutionChoice>[];
    for (final entry in list) {
      if (entry is! Map) continue;
      final value = entry['value'];
      final factor = entry['factor'];
      if (value is! String || factor is! num || factor <= 0) continue;
      final width = entry['width'];
      final height = entry['height'];
      choices.add(LibretroResolutionChoice(
        value: value,
        factor: factor.toDouble(),
        width: width is int ? width : 0,
        height: height is int ? height : 0,
      ));
    }
    choices.sort((a, b) => a.factor.compareTo(b.factor));
    final coreDefault = internal['coreDefault'];
    return LibretroCoreResolution(
      core: core,
      libraryName: libraryName,
      key: key,
      choices: choices,
      coreDefault: coreDefault is String ? coreDefault : null,
      neoStationDefault: core.optionDefaults[key],
      apply: internal['apply'] == 'live' ? LibretroResolutionApply.live : LibretroResolutionApply.relaunch,
      detected: true,
    );
  }

  /// Saves [value] for every game of the core. Throws
  /// [LibretroCoreOptionStoreException] while a game runs (nothing written).
  Future<void> setValue(LibretroCoreResolution resolution, String value) async {
    final key = resolution.key;
    if (!resolution.supported || key == null || !resolution.choices.any((choice) => choice.value == value)) {
      throw ArgumentError.value(value, 'value', 'not offered by ${resolution.core.id}');
    }
    await store.write(resolution.libraryName, <String, String?>{key: value});
  }

  static Future<Map<String, Object?>?> _readJson(String path) async {
    final file = File(path);
    try {
      if (!await file.exists()) return null;
      final decoded = jsonDecode(await file.readAsString());
      return decoded is Map<String, Object?> ? decoded : null;
    } catch (error) {
      _log.w('Libretro resolution: $path unreadable: $error');
      return null;
    }
  }
}
