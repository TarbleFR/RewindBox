import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as path;

import '../../../l10n/enhancements_locale.dart';
import '../../../models/game_model.dart';
import '../../console_catalog.dart';
import '../../embedded_engine_policy.dart';
import '../../libretro_core_catalog.dart';
import '../../libretro_core_option_store.dart';
import '../../libretro_internal_service.dart';
import '../enhancement_adapter.dart';
import '../enhancement_catalog.dart';
import '../enhancement_models.dart';
import '../enhancement_store.dart';

/// One embedded Beetle PSX core as its per-game options file names it.
class BeetleCore {
  const BeetleCore(this.id, this.libraryName, this.prefix, {this.hardware = false});

  /// Framework id in [LibretroCoreCatalog.cores].
  final String id;

  /// `library_name` of the core: its file is `Config/Games/<library>.json`.
  final String libraryName;

  /// Prefix of every option key the core declares (`BEETLE_OPT`).
  final String prefix;

  /// Built with `HAVE_HW` (Vulkan and OpenGL renderers, Vulkan-only options).
  final bool hardware;
}

/// One built-in preset: core options without their prefix, and the values
/// that make it apply.
class BeetlePreset {
  const BeetlePreset({
    required this.id,
    required this.category,
    required this.nameKey,
    required this.descriptionKey,
    required this.options,
    this.group = '',
    this.hardwareOnly = false,
  });

  /// Stable: a player's choice is stored under it.
  final String id;
  final EnhancementCategory category;

  /// [EnhancementsLocale] keys of RewindBox's own text: the page shows it in
  /// its language.
  final String nameKey;
  final String descriptionKey;
  final Map<String, String> options;

  /// Presets setting the same option share a group: one at a time.
  final String group;

  /// Declared by Beetle PSX HW only (Vulkan renderer).
  final bool hardwareOnly;

  String get name => BeetleEnhancementAdapter.english(nameKey);
  String get description => BeetleEnhancementAdapter.english(descriptionKey);

  bool appliesTo(BeetleCore core) => !hardwareOnly || core.hardware;

  /// Every value of the preset is the one [entry] holds for [core].
  bool inEffect(BeetleCore core, Map<String, Object?> entry) =>
      options.entries.every((option) => entry['${core.prefix}${option.key}'] == option.value);

  /// A value of [entry] that is not RewindBox's ([ours]) differs from the
  /// preset's: turning it on would replace a choice of the player's.
  bool conflictsWith(BeetleCore core, Map<String, Object?> entry, Map<String, String> ours) =>
      options.entries.any((option) {
        final key = '${core.prefix}${option.key}';
        final current = entry[key];
        return current != null && current != option.value && ours[key] != current;
      });
}

/// Built-in Beetle PSX presets for PS1 games: widescreen, PGXP, FMV filter
/// and overclocks, written as per-game core options of the embedded host.
///
/// `LibretroCoreHost` opens `Config/Games/<library>.json`
/// (`{"version": 1, "games": {"<game key>": {key: value}}}`) when a game
/// starts: the running game's values win over the values saved for every
/// game of the core and over NeoStation's defaults; only the session's own
/// overrides (dynarec without JIT, locked options) rank above them. The game
/// key is `ps1/<rom file name>`, exactly what `LibretroInternalService.launch`
/// passes (`'$system/${game.romname}'`, and Beetle runs only the `ps1`
/// system) and what the in-game "this game" resolution and the HD textures
/// page write under. A value kept there applies to this game alone, at its
/// next start; two files of the same name share it, as they share every
/// per-game value of the store.
///
/// A preset is written for both cores (`beetle_psx_hw_` and `beetle_psx_`
/// keys), so a game switched to the other one keeps it; an option only
/// Beetle PSX HW declares goes to its file only. A preset is active when the
/// core the game starts with holds all its values; a game the launch sends to
/// the RetroArch app takes none (set to it, its console's built-in engine
/// off, its file unreadable here or its core missing: [launchesEmbedded]).
/// What RewindBox wrote for a preset the game's core does not read (the MDEC
/// filter on a game set to Beetle PSX) stays for when the game goes back:
/// only turning it off there, or restoring, removes it.
///
/// Nothing of the player's is replaced: RewindBox only adds keys the game's
/// entry lacks and records each value it added. A different value already
/// there refuses the preset (`player_value`); an equal one stays the
/// player's (never copied to the other core), and a preset made only of the
/// player's values cannot be turned off here (`player_keeps_on`). Turning a
/// preset off, or restoring, removes exactly the keys RewindBox added that
/// still hold its value: the entry is as it was. A file RewindBox cannot
/// read is never written (`options_unreadable`): restoring cleans every
/// other file and keeps that one's values recorded. Nothing is written while
/// a libretro session runs or launches (`session_active`: the session owns
/// the running game's entry and rewrites it).
///
/// Nothing to install: a game's state is kept while it holds a value
/// RewindBox added. Names, descriptions and the compatibility line are
/// RewindBox's own text: the items' payload names their [EnhancementsLocale]
/// keys for the page.
///
/// Option names and values are those of the pinned core
/// (`libretro_core_options.h` at native/beetle-psx/source.json's revision).
/// The internal resolution stays with LibretroResolutionService. The PS1
/// serial, read from SYSTEM.CNF when the image allows it, only feeds the
/// compatibility line.
class BeetleEnhancementAdapter extends EnhancementAdapter {
  BeetleEnhancementAdapter({
    Future<Directory> Function()? configDirectory,
    LibretroSessionProbe? sessionActive,
    Future<String?> Function(String system, String romname)? coreChoice,
    Future<bool> Function(GameModel game, String coreId)? runsEmbedded,
  }) : _configDirectory = configDirectory ?? LibretroInternalService.configDirectory,
       _sessionActive = sessionActive ?? LibretroInternalBridge.isSessionActive,
       _coreChoice = coreChoice ?? LibretroInternalService.coreChoiceFor,
       _runsEmbedded = runsEmbedded ?? launchesEmbedded;

  /// The libretro system Beetle runs (`LibretroCoreCatalog.systems`): first
  /// part of the game key.
  static const libretroSystem = 'ps1';

  /// Library folders of PS1 games (TextureCatalogService.textureSystem).
  static const folders = {'ps1', 'psx', 'playstation'};

  static const sourceId = 'beetle-psx-core-options';

  /// The system's default core first.
  static const cores = [
    BeetleCore('mednafen_psx_hw', 'Beetle PSX HW', 'beetle_psx_hw_', hardware: true),
    BeetleCore('mednafen_psx', 'Beetle PSX', 'beetle_psx_'),
  ];

  static const presets = [
    BeetlePreset(
      id: 'beetle-widescreen-16-9',
      category: EnhancementCategory.ultrawide,
      nameKey: EnhancementsLocale.beetleWidescreen,
      descriptionKey: EnhancementsLocale.beetleWidescreenNote,
      options: {'widescreen_hack': 'enabled', 'widescreen_hack_aspect_ratio': '16:9'},
    ),
    BeetlePreset(
      id: 'beetle-pgxp-geometry',
      category: EnhancementCategory.graphics,
      nameKey: EnhancementsLocale.beetlePgxpGeometry,
      descriptionKey: EnhancementsLocale.beetlePgxpGeometryNote,
      group: 'beetle-pgxp',
      options: {'pgxp_mode': 'memory only', 'pgxp_texture': 'disabled'},
    ),
    BeetlePreset(
      id: 'beetle-pgxp-textures',
      category: EnhancementCategory.graphics,
      nameKey: EnhancementsLocale.beetlePgxpTextures,
      descriptionKey: EnhancementsLocale.beetlePgxpTexturesNote,
      group: 'beetle-pgxp',
      options: {'pgxp_mode': 'memory only', 'pgxp_texture': 'enabled'},
    ),
    BeetlePreset(
      id: 'beetle-mdec-chroma',
      category: EnhancementCategory.graphics,
      nameKey: EnhancementsLocale.beetleMdec,
      descriptionKey: EnhancementsLocale.beetleMdecNote,
      hardwareOnly: true,
      options: {'mdec_yuv': 'enabled'},
    ),
    BeetlePreset(
      id: 'beetle-gte-overclock',
      category: EnhancementCategory.performance,
      nameKey: EnhancementsLocale.beetleGte,
      descriptionKey: EnhancementsLocale.beetleGteNote,
      options: {'gte_overclock': 'enabled'},
    ),
    BeetlePreset(
      id: 'beetle-cpu-150',
      category: EnhancementCategory.performance,
      nameKey: EnhancementsLocale.beetleCpu150,
      descriptionKey: EnhancementsLocale.beetleCpu150Note,
      group: 'beetle-cpu-clock',
      options: {'cpu_freq_scale': '150%'},
    ),
    BeetlePreset(
      id: 'beetle-cpu-200',
      category: EnhancementCategory.performance,
      nameKey: EnhancementsLocale.beetleCpu200,
      descriptionKey: EnhancementsLocale.beetleCpu200Note,
      group: 'beetle-cpu-clock',
      options: {'cpu_freq_scale': '200%'},
    ),
  ];

  static const _valuesKey = 'values';
  static const _createdKey = 'created';
  static const _maxOptionsBytes = 4 << 20;
  static const _maxTextBytes = 64 << 10;
  static const _imageExtensions = {'.bin', '.img', '.iso'};
  static const _encoder = JsonEncoder.withIndent('  ');

  final Future<Directory> Function() _configDirectory;
  final LibretroSessionProbe _sessionActive;
  final Future<String?> Function(String system, String romname) _coreChoice;
  final Future<bool> Function(GameModel game, String coreId) _runsEmbedded;

  /// Per game key, from the last [identify] and [sync]: the core it starts
  /// with (null: the RetroArch app) and the locale key of why, its serial,
  /// and the presets a value of the player's or an unreadable file blocks
  /// (see [_blocked]).
  final _routes = <String, BeetleCore?>{};
  final _elsewhere = <String, String>{};
  final _serials = <String, String?>{};
  final _conflicts = <String, Map<String, String?>>{};
  static final Map<String, String?> _serialCache = {};

  /// RewindBox's English text for an [EnhancementsLocale] key.
  static String english(String key) => EnhancementsLocale.values['en']?[key] ?? key;

  /// The Compatibility line of a preset from its item's payload: why the
  /// game's core does not read it, the game's serial, the cores that do.
  /// [text] names the parts in the page's language (English by default).
  static String compatibilityOf(Map<String, dynamic> payload, {String Function(String key) text = english}) => [
    if (payload['reasonKey'] case final String reason) text(reason),
    if (payload['serial'] case final String serial) serial,
    if (payload['coresKey'] case final String cores) text(cores),
  ].join(' · ');

  @override
  EnhancementEngine get engine => EnhancementEngine.beetle;

  @override
  bool handles(String systemFolder) => folders.contains(systemFolder.toLowerCase());

  static String gameKey(String romname) => '$libretroSystem/$romname';

  /// The Beetle core a game starts with, as `LibretroInternalService.launch`
  /// resolves its choice; null when it is set to another core or to the
  /// RetroArch app, where these options apply nowhere.
  static BeetleCore? coreForChoice(String? choice) {
    if (choice == LibretroInternalService.retroArchChoice) return null;
    final binding = LibretroCoreCatalog.bindingFor(libretroSystem);
    final allowed = [?binding?.coreId, ...?binding?.alternatives];
    final id = choice != null && allowed.contains(choice) ? choice : binding?.coreId ?? cores.first.id;
    for (final core in cores) {
      if (core.id == id) return core;
    }
    return null;
  }

  BeetleCore? _startsWith(String key) => _routes.containsKey(key) ? _routes[key] : cores.first;

  /// Whether the launch runs [game] inside RewindBox with [coreId], as
  /// GameLaunchService decides for a PS1 game: the console's built-in engine
  /// is on ([EmbeddedEnginePolicy], under the console of the `ps1` system),
  /// the game file is readable here and the core ships with this build
  /// (LibretroInternalService.shouldLaunchEmbedded). Otherwise the game opens
  /// in the RetroArch app, where these options apply nowhere.
  static Future<bool> launchesEmbedded(
    GameModel game,
    String coreId, {
    EmbeddedEnginePolicy? policy,
    Future<List<String>> Function()? bundledCores,
  }) async {
    final engines = policy ?? EmbeddedEnginePolicy.instance;
    await engines.load();
    final console = ConsoleCatalog.entryForKey(libretroSystem);
    if (!(console == null ? engines.useEmbedded : engines.allows(console.id))) return false;
    final romPath = game.romPath;
    if (romPath == null || romPath.isEmpty || !await File(romPath).exists()) return false;
    try {
      return (await (bundledCores ?? LibretroInternalBridge.availableCores)()).contains(coreId);
    } on Object {
      return false;
    }
  }

  @override
  Future<EnhancementGameIdentity> identify(GameModel game, String systemFolder) async {
    final title = game.titleName ?? game.name;
    if (game.romname.isEmpty) {
      return EnhancementGameIdentity.unavailable(engine, EnhancementProblem.identityUnavailable, title: title);
    }
    final key = gameKey(game.romname);
    String? choice;
    try {
      choice = await _coreChoice(libretroSystem, game.romname);
    } on Object {
      choice = null;
    }
    final core = coreForChoice(choice);
    bool embedded;
    try {
      embedded = core != null && await _runsEmbedded(game, core.id);
    } on Object {
      embedded = false; // the launch cannot run it inside RewindBox either
    }
    _routes[key] = embedded ? core : null;
    _elsewhere[key] = core == null ? EnhancementsLocale.beetleOtherCore : EnhancementsLocale.beetleRetroArchRoute;
    final romPath = game.romPath;
    _serials[key] = romPath != null && path.isAbsolute(romPath) ? await _serial(romPath) : null;
    return EnhancementGameIdentity(engine: engine, key: key, title: title);
  }

  /// The presets ship with the adapter: nothing to download.
  @override
  Future<bool> listed(EnhancementCatalog catalog, EnhancementGameIdentity identity) async => identity.known;

  @override
  Future<Map<String, dynamic>?> loadRecord(
    EnhancementCatalog catalog,
    EnhancementGameIdentity identity, {
    bool download = true,
    EnhancementProgress? onProgress,
  }) async => identity.known ? const {'source': sourceId} : null;

  @override
  List<EnhancementItem> items(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState? state,
  ) => [
    for (final preset in presets)
      _item(
        preset,
        _startsWith(identity.key),
        _serials[identity.key],
        active: state?.active.contains(preset.id) == true,
        blocked: _conflicts[identity.key] ?? const {},
        elsewhere: _elsewhere[identity.key] ?? EnhancementsLocale.beetleOtherCore,
      ),
  ];

  /// A preset the core the game starts with does not read is incompatible
  /// (the line says why); one a value of the player's or an unreadable file
  /// blocks says which. The payload names the page's text: locale keys
  /// (`nameKey`, `descriptionKey`, `sourceKey`, `reasonKey`, `coresKey`,
  /// `problemKey`), the serial and the unreadable `file`.
  EnhancementItem _item(
    BeetlePreset preset,
    BeetleCore? core,
    String? serial, {
    required bool active,
    required Map<String, String?> blocked,
    required String elsewhere,
  }) {
    final applies = core != null && preset.appliesTo(core);
    final status = !applies
        ? EnhancementStatus.incompatible
        : active
        ? EnhancementStatus.active
        : blocked.containsKey(preset.id)
        ? EnhancementStatus.incompatible
        : EnhancementStatus.available;
    final shown = applies && !active && blocked.containsKey(preset.id);
    final unreadable = blocked[preset.id];
    final payload = <String, dynamic>{
      'nameKey': preset.nameKey,
      'descriptionKey': preset.descriptionKey,
      'sourceKey': EnhancementsLocale.beetleSource,
      if (core == null)
        'reasonKey': elsewhere
      else if (!applies)
        'reasonKey': EnhancementsLocale.beetleSoftwareCore,
      'serial': ?serial,
      'coresKey': preset.hardwareOnly ? EnhancementsLocale.beetleVulkanCore : EnhancementsLocale.beetleBothCores,
      if (shown)
        'problemKey': unreadable == null ? EnhancementsLocale.playerValue : EnhancementsLocale.optionsUnreadable,
      if (shown) 'file': ?unreadable,
    };
    return EnhancementItem(
      id: preset.id,
      engine: engine,
      category: preset.category,
      name: preset.name,
      sourceId: sourceId,
      status: status,
      description: preset.description,
      compatibility: compatibilityOf(payload),
      exclusiveGroup: preset.group,
      problem: shown ? EnhancementProblem.userFilePresent : EnhancementProblem.none,
      payload: payload,
    );
  }

  Future<File> _file(BeetleCore core) async => File(
    path.join((await _configDirectory()).path, 'Games', LibretroCoreOptionStore.libraryFileName(core.libraryName)),
  );

  Future<_GameOptions> _read(BeetleCore core) async {
    final file = await _file(core);
    if (!await file.exists()) return _GameOptions(file, null);
    try {
      if (await file.length() <= _maxOptionsBytes) {
        final decoded = jsonDecode(await file.readAsString());
        if (decoded is Map && (decoded['games'] == null || decoded['games'] is Map)) {
          return _GameOptions(file, Map<String, dynamic>.from(decoded));
        }
      }
    } on Object {
      // Read as empty below, as the native loader does, and never written.
    }
    return _GameOptions(file, null, readable: false);
  }

  Future<Map<String, _GameOptions>> _readAll() async => {for (final core in cores) core.id: await _read(core)};

  /// RewindBox's values per core id (a copy): `data.values.<core>.<key>`.
  static Map<String, Map<String, String>> _owned(EnhancementGameState state) {
    final recorded = state.data[_valuesKey];
    return {
      for (final core in cores)
        core.id: {
          if (recorded is Map && recorded[core.id] is Map)
            for (final entry in (recorded[core.id] as Map).entries)
              if (entry.value is String) entry.key.toString(): entry.value as String,
        },
    };
  }

  static void _record(EnhancementGameState state, Map<String, Map<String, String>> owned) {
    final values = {
      for (final entry in owned.entries)
        if (entry.value.isNotEmpty) entry.key: Map<String, String>.of(entry.value),
    };
    if (values.isEmpty) {
      state.data.remove(_valuesKey);
    } else {
      state.data[_valuesKey] = values;
    }
  }

  static Set<String> _created(EnhancementGameState state) => {
    for (final id in (state.data[_createdKey] as List? ?? const [])) id.toString(),
  };

  static void _recordCreated(EnhancementGameState state, Set<String> created) {
    if (created.isEmpty) {
      state.data.remove(_createdKey);
    } else {
      state.data[_createdKey] = created.toList()..sort();
    }
  }

  /// A value the player changed or removed since RewindBox wrote it is no
  /// longer RewindBox's. True when one was forgotten.
  static bool _forgetChanged(Map<String, Map<String, String>> owned, Map<String, _GameOptions> files, String key) {
    var forgot = false;
    for (final core in cores) {
      final options = files[core.id]!;
      if (!options.readable) continue;
      final entry = options.entry(key);
      final ours = owned[core.id]!;
      final before = ours.length;
      ours.removeWhere((option, value) => entry[option] != value);
      forgot |= ours.length != before;
    }
    return forgot;
  }

  /// The presets a value of the player's or a file RewindBox cannot read
  /// keeps from being turned on: preset id to that file's name, null for a
  /// value of the player's (an unreadable file wins: it blocks everything).
  static Map<String, String?> _blocked(
    Map<String, Map<String, String>> owned,
    Map<String, _GameOptions> files,
    String key,
  ) {
    final blocked = <String, String?>{};
    for (final preset in presets) {
      for (final core in cores) {
        if (!preset.appliesTo(core)) continue;
        final options = files[core.id]!;
        if (!options.writable) {
          blocked[preset.id] ??= options.name;
        } else if (preset.conflictsWith(core, options.entry(key), owned[core.id]!)) {
          blocked.putIfAbsent(preset.id, () => null);
        }
      }
    }
    return blocked;
  }

  /// The game's options are the truth: a preset is active when the core the
  /// game starts with holds all its values, whoever wrote them. Nothing to
  /// install: the state is installed while it holds a value RewindBox added,
  /// so one holding none and nothing active leaves the store.
  @override
  Future<bool> sync(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
  ) async {
    final key = identity.key;
    final files = await _readAll();
    final owned = _owned(state);
    final forgot = _forgetChanged(owned, files, key);
    _record(state, owned);
    _conflicts[key] = _blocked(owned, files, key);
    final core = _startsWith(key);
    final active = {
      if (core != null)
        for (final preset in presets)
          if (preset.appliesTo(core) && preset.inEffect(core, files[core.id]!.entry(key))) preset.id,
    };
    final installed = owned.values.any((values) => values.isNotEmpty);
    final changed =
        forgot ||
        installed != state.installed ||
        active.length != state.active.length ||
        !active.containsAll(state.active);
    state
      ..installed = installed
      ..active.clear()
      ..active.addAll(active);
    return changed;
  }

  /// The values the [active] presets set, per core id.
  static Map<String, Map<String, String>> _wanted(Set<String> active) => {
    for (final core in cores)
      core.id: {
        for (final preset in presets)
          if (active.contains(preset.id) && preset.appliesTo(core))
            for (final option in preset.options.entries) '${core.prefix}${option.key}': option.value,
      },
  };

  /// [entry] holding exactly [wanted] of RewindBox's values: a key no longer
  /// wanted is removed while it still holds RewindBox's value, a missing one
  /// is added. [ours] becomes the keys RewindBox holds afterwards.
  static Map<String, Object?> _planned(
    Map<String, Object?> entry,
    Map<String, String> wanted,
    Map<String, String> ours,
  ) {
    final result = Map<String, Object?>.of(entry);
    for (final option in ours.keys.toList()) {
      if (wanted.containsKey(option)) continue;
      if (result[option] == ours[option]) result.remove(option);
      ours.remove(option);
    }
    for (final value in wanted.entries) {
      // Already so: RewindBox's stays its own, the player's stays theirs.
      if (result[value.key] == value.value) continue;
      result[value.key] = value.value;
      ours[value.key] = value.value;
    }
    return result;
  }

  @override
  Future<void> apply(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active,
  ) async {
    final key = identity.key;
    final files = await _readAll();
    final owned = _owned(state);
    _forgetChanged(owned, files, key);
    final starts = _startsWith(key);
    // A preset on through the player's values alone stays theirs: RewindBox
    // neither copies it to the other core nor removes it.
    final theirs = {
      for (final preset in presets)
        if (state.active.contains(preset.id) &&
            !cores.any(
              (core) => preset.options.entries.any(
                (option) => owned[core.id]!['${core.prefix}${option.key}'] == option.value,
              ),
            ))
          preset.id,
    };
    // A preset the game's core does not read (the MDEC filter on a game set
    // to Beetle PSX, every preset on a game set elsewhere) is neither added
    // nor removed: RewindBox's values for it stay for when the game goes back.
    final kept = {
      for (final preset in presets)
        if (starts == null || !preset.appliesTo(starts)) preset.id,
    };
    final wanted = _wanted(active.difference(theirs).difference(kept));
    final keptOptions = _wanted(kept);
    for (final core in cores) {
      for (final option in keptOptions[core.id]!.keys) {
        if (owned[core.id]![option] case final String value) wanted[core.id]!.putIfAbsent(option, () => value);
      }
    }

    // 1. No value of the player's is replaced, no unreadable file written.
    for (final core in cores) {
      final options = files[core.id]!;
      final values = wanted[core.id]!;
      final ours = owned[core.id]!;
      if (values.isEmpty && ours.isEmpty) continue;
      if (!options.writable) throw EnhancementException('options_unreadable', options.name);
      final entry = options.entry(key);
      for (final value in values.entries) {
        final current = entry[value.key];
        if (current != null && current != value.value && ours[value.key] != current) {
          throw EnhancementException('player_value', '${options.name}: ${value.key}');
        }
      }
    }

    // 2. A preset turned off stays on when all its values are the player's:
    //    say so rather than leave it on silently.
    final planned = {
      for (final core in cores) core.id: _planned(files[core.id]!.entry(key), wanted[core.id]!, owned[core.id]!),
    };
    if (starts != null) {
      for (final preset in presets) {
        if (!state.active.contains(preset.id) || active.contains(preset.id) || !preset.appliesTo(starts)) continue;
        if (preset.inEffect(starts, planned[starts.id]!)) throw EnhancementException('player_keeps_on', preset.id);
      }
    }

    // 3. Written where something changes; each file recorded once written.
    final created = _created(state);
    for (final core in cores) {
      final options = files[core.id]!;
      if (!_same(options.entry(key), planned[core.id]!)) await _write(core, options, key, planned[core.id]!, created);
      _record(state, {..._owned(state), core.id: owned[core.id]!});
      _recordCreated(state, created);
    }
    state.installed = owned.values.any((values) => values.isNotEmpty);
  }

  /// Every file RewindBox can read is restored. One it cannot read keeps its
  /// values recorded (and the state with them, for a later restore), and is
  /// named once all the others are done (`options_unreadable`).
  @override
  Future<void> remove(EnhancementGameState state) async {
    final key = state.key;
    final owned = _owned(state);
    final created = _created(state);
    final unreadable = <String>[];
    for (final core in cores) {
      final ours = owned[core.id]!;
      if (ours.isEmpty && !created.contains(core.id)) continue;
      final options = await _read(core);
      if (options.readable && options.document == null) {
        created.remove(core.id); // the file is gone, and RewindBox's values with it
      } else if (options.writable) {
        // A value the player changed since stays theirs.
        final restored = Map<String, Object?>.of(options.entry(key))
          ..removeWhere((option, value) => ours[option] == value);
        await _write(core, options, key, restored, created);
        created.remove(core.id); // left with values of the player's: theirs now
      } else if (ours.isNotEmpty) {
        unreadable.add(options.name);
        continue;
      } else {
        created.remove(core.id); // nothing of RewindBox's to take out of it
      }
      ours.clear();
      _record(state, owned);
      _recordCreated(state, created);
    }
    if (unreadable.isNotEmpty) throw EnhancementException('options_unreadable', unreadable.join(', '));
    state
      ..installed = false
      ..active.clear()
      ..data.clear();
  }

  /// The session owns the running game's entry and rewrites it: no write
  /// while one runs or launches, nor when that cannot be told.
  Future<void> _refuseDuringSession() async {
    bool running;
    try {
      running = await _sessionActive();
    } on Object {
      running = true;
    }
    if (running) throw const EnhancementException('session_active');
  }

  /// Writes [entry] as the game's values, keeping every other game and key
  /// of the file; nothing when the file would not change. A file RewindBox
  /// created is deleted once it holds nothing else.
  Future<void> _write(
    BeetleCore core,
    _GameOptions options,
    String key,
    Map<String, Object?> entry,
    Set<String> created,
  ) async {
    final document = Map<String, dynamic>.of(options.document ?? const {});
    final games = Map<String, dynamic>.from(document['games'] as Map? ?? const {});
    if (entry.isEmpty) {
      games.remove(key);
    } else {
      games[key] = entry;
    }
    document['games'] = games;
    document['version'] ??= 1;
    final blank = games.isEmpty && document.keys.every({'games', 'version'}.contains);
    if (blank && (options.document == null || created.contains(core.id))) {
      if (options.document != null) {
        await _refuseDuringSession();
        await options.file.delete();
      }
      created.remove(core.id);
      return;
    }
    final text = '${_encoder.convert(_sorted(document))}\n';
    if (options.document != null && text == '${_encoder.convert(_sorted(options.document))}\n') return;
    await _refuseDuringSession();
    if (options.document == null) created.add(core.id);
    await EnhancementFiles.writeText(options.file, text);
  }

  static Object? _sorted(Object? value) {
    if (value is Map) {
      final keys = value.keys.map((key) => key.toString()).toList()..sort();
      return {for (final key in keys) key: _sorted(value[key])};
    }
    if (value is List) return [for (final item in value) _sorted(item)];
    return value;
  }

  static bool _same(Map<String, Object?> a, Map<String, Object?> b) =>
      a.length == b.length && a.entries.every((entry) => b.containsKey(entry.key) && b[entry.key] == entry.value);

  Future<String?> _serial(String file) async {
    try {
      final stat = await File(file).stat();
      if (stat.type == FileSystemEntityType.notFound) return null;
      final cacheKey = '$file|${stat.size}|${stat.modified.millisecondsSinceEpoch}';
      if (_serialCache.containsKey(cacheKey)) return _serialCache[cacheKey];
      return _serialCache[cacheKey] = await readSerial(file);
    } on Object {
      return null;
    }
  }

  /// The PS1 serial of a game file (`SLUS-01040`) from the SYSTEM.CNF of
  /// its data track: a BIN, IMG or ISO, a CUE's first FILE, a CCD's IMG, an
  /// M3U's first disc, each named file in the same folder. Null for
  /// compressed images (CHD, PBP...), a disc without SYSTEM.CNF and anything
  /// unreadable.
  static Future<String?> readSerial(String file) => _readSerial(file, playlist: true);

  static Future<String?> _readSerial(String file, {required bool playlist}) async {
    try {
      final extension = path.extension(file).toLowerCase();
      if (_imageExtensions.contains(extension)) return await _imageSerial(file);
      if (extension == '.ccd') {
        final image = '${path.withoutExtension(file)}.img';
        return await FileSystemEntity.type(image, followLinks: false) == FileSystemEntityType.file
            ? await _imageSerial(image)
            : null;
      }
      if (extension == '.cue') {
        final match = RegExp(
          r'^\s*FILE\s+(?:"([^"]+)"|(\S+))',
          multiLine: true,
          caseSensitive: false,
        ).firstMatch(await _smallText(file));
        final track = await _sibling(file, match?.group(1) ?? match?.group(2));
        return track != null && _imageExtensions.contains(path.extension(track).toLowerCase())
            ? await _imageSerial(track)
            : null;
      }
      if (extension == '.m3u' && playlist) {
        final first = (await _smallText(file))
            .split(RegExp(r'\r?\n'))
            .map((line) => line.trim())
            .firstWhere((line) => line.isNotEmpty && !line.startsWith('#'), orElse: () => '');
        final disc = await _sibling(file, first);
        return disc != null && path.extension(disc).toLowerCase() != '.m3u'
            ? await _readSerial(disc, playlist: false)
            : null;
      }
    } on Object {
      return null;
    }
    return null;
  }

  static Future<String> _smallText(String file) async {
    final handle = File(file);
    if (await handle.length() > _maxTextBytes) return '';
    return utf8.decode(await handle.readAsBytes(), allowMalformed: true);
  }

  /// A regular file of [name] next to [file]; a path is never followed.
  static Future<String?> _sibling(String file, String? name) async {
    final trimmed = name?.trim() ?? '';
    if (trimmed.isEmpty || trimmed == '.' || trimmed == '..' || trimmed.contains('/') || trimmed.contains('\\')) {
      return null;
    }
    final sibling = path.join(path.dirname(file), trimmed);
    return await FileSystemEntity.type(sibling, followLinks: false) == FileSystemEntityType.file ? sibling : null;
  }

  /// SYSTEM.CNF of the root directory of an ISO 9660 track: raw 2352-byte
  /// sectors (MODE2/XA or MODE1) or 2048-byte ones.
  static Future<String?> _imageSerial(String file) async {
    RandomAccessFile? handle;
    try {
      final opened = handle = await File(file).open();
      final length = await opened.length();
      for (final (stride, offset) in const [(2352, 24), (2352, 16), (2048, 0)]) {
        Future<Uint8List?> sector(int index) async {
          final at = index * stride + offset;
          if (index < 0 || at + 2048 > length) return null;
          await opened.setPosition(at);
          final data = await opened.read(2048);
          return data.length == 2048 ? data : null;
        }

        final volume = await sector(16);
        if (volume == null || volume[0] != 1 || String.fromCharCodes(volume.sublist(1, 6)) != 'CD001') continue;
        final root = ByteData.sublistView(volume);
        final extent = root.getUint32(156 + 2, Endian.little);
        final size = root.getUint32(156 + 10, Endian.little);
        for (var index = 0; index < (size + 2047) ~/ 2048 && index < 16; index++) {
          final directory = await sector(extent + index);
          if (directory == null) return null;
          final view = ByteData.sublistView(directory);
          var at = 0;
          while (at + 34 <= 2048 && directory[at] >= 34 && at + directory[at] <= 2048) {
            final record = directory[at];
            final nameLength = directory[at + 32];
            if (33 + nameLength > record) break;
            final name = String.fromCharCodes(directory.sublist(at + 33, at + 33 + nameLength)).split(';').first;
            if (name.toUpperCase() == 'SYSTEM.CNF' && (directory[at + 25] & 2) == 0) {
              final data = await sector(view.getUint32(at + 2, Endian.little));
              final bytes = view.getUint32(at + 10, Endian.little);
              if (data == null || bytes == 0 || bytes > 2048) return null;
              return serialFromSystemCnf(latin1.decode(data.sublist(0, bytes)));
            }
            at += record;
          }
        }
        return null;
      }
      return null;
    } on Object {
      return null;
    } finally {
      await handle?.close();
    }
  }

  /// `BOOT = cdrom:\SLUS_010.40;1` gives `SLUS-01040`; null without a PS1
  /// boot line (a PS2 disc's `BOOT2`, an early disc's `PSX.EXE`).
  static String? serialFromSystemCnf(String text) {
    final boot = RegExp(r'^\s*BOOT\s*=\s*([^\r\n]*)', multiLine: true, caseSensitive: false).firstMatch(text)?.group(1);
    if (boot == null) return null;
    final name = boot.trim().split(RegExp(r'[\\/:]')).last.split(';').first.trim().toUpperCase();
    final match = RegExp(r'^([A-Z]{4})[_-]?(\d{3})\.?(\d{2})$').firstMatch(name);
    return match == null ? null : '${match[1]}-${match[2]}${match[3]}';
  }
}

/// One per-game options file as read.
class _GameOptions {
  _GameOptions(this.file, this.document, {this.readable = true});

  final File file;

  /// The file's name, as messages give it (`Beetle PSX HW.json`).
  String get name => path.basename(file.path);

  /// The JSON object, null when the file is absent or unreadable.
  final Map<String, dynamic>? document;

  /// False for a file that is not a JSON object with a `games` object: read
  /// as empty, as the native loader does, and never written.
  final bool readable;

  /// RewindBox writes only the format it knows (`version` 1).
  bool get writable => readable && (document == null || document!['version'] == null || document!['version'] == 1);

  /// The values of one game ({} when none).
  Map<String, Object?> entry(String key) {
    final games = document?['games'];
    final entry = games is Map ? games[key] : null;
    return entry is Map ? {for (final value in entry.entries) value.key.toString(): value.value} : {};
  }
}
