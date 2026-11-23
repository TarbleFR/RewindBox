import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:path/path.dart' as path;

import '../../../models/game_model.dart';
import '../../logger_service.dart';
import '../../melonx_internal_service.dart';
import '../../melonx_mods_service.dart';
import '../../nextendo/nextendo_engine_support.dart';
import '../enhancement_adapter.dart';
import '../enhancement_catalog.dart';
import '../enhancement_models.dart';
import '../enhancement_store.dart';

/// Switch cheats and graphics codes for the embedded MeloNX (Ryujinx).
///
/// Ryujinx's ModLoader reads `Documents/MeloNX/mods/contents/TITLEID/MOD/
/// cheats/BUILDID.txt` when a game starts and installs only the files whose
/// name matches a loaded executable's Build ID: a code for another game
/// version is never applied. `mods/contents/<title id>/cheats/enabled.txt`
/// lists the enabled programs (`BUILDID-<name Cheat>`); when that file is
/// absent the engine enables every cheat, so RewindBox only ever creates it
/// with the player's existing cheats preserved.
///
/// The installed build: an engine from the cheat report lot answers the main
/// executable's Build ID of the game file (`metadata`, `buildId`) and of an
/// update (`inspectUpdate`, `buildId`), in the cheat files' 16-digit form. The
/// selected update (`games/<title id>/updates.json`) is what runs; a selected
/// update that cannot be read leaves the build unknown. When it is known, a
/// code of the application whose catalogue Build IDs do not include it is shown
/// incompatible (the engine would skip it silently). Without it, the display
/// version that runs names the build through the catalogue's game versions
/// (`releases`); when neither is known, the page says it cannot tell.
///
/// An FPS code or exefs mod with a target (`120 FPS`) only raises the game's own limit; the
/// engine still presents at the Switch's 60 Hz unless its refresh follows. An
/// engine that takes the `vsyncFps` graphics option (its marker text is in the
/// Core binary) gets the code's target at launch ([launchRefresh]) while the
/// code is on for the installed build; off, the player's VSync choice applies.
/// An engine without the option is never sent it (it refuses unknown keys).
/// A code the catalogue flags as the game's default (`Default 30 FPS`) or as
/// not raising the frame-rate limit (`Dynamic Resolution Target 45 FPS`)
/// never sets it; [sync] recomputes a refresh recorded before those flags.
///
/// The catalogue's flags go to each item's payload (`flags`). A mod that
/// needs the expanded 8 GB DRAM layout is incompatible: RewindBox offers no
/// such layout (one turned on before the flag shows as on, to be turned
/// off). An entry whose builds are all older than the newest update the
/// catalogue knows (`latest`) is marked `olderThan`, never blocked.
class MelonxEnhancementAdapter extends EnhancementAdapter {
  MelonxEnhancementAdapter({
    Future<Directory> Function()? root,
    Future<Map<String, dynamic>> Function(String gamePath)? metadata,
    Future<Map<String, dynamic>> Function(String updatePath, String titleId)? inspectUpdate,
    Future<bool> Function()? refreshSupported,
  }) : _root = root ?? MelonxInternalService.rootDirectory,
       _metadata = metadata ?? _nativeMetadata,
       _inspectUpdate = inspectUpdate ?? _nativeInspectUpdate,
       _refreshSupported = refreshSupported ?? engineTakesRefresh;

  static const modName = 'RewindBox';
  static const masterName = 'RewindBox master code';

  /// Text of the engine's `vsyncFps` option kept in the Core binary
  /// (EmbeddedGraphicsSettings.VsyncFpsRange, UTF-16 under NativeAOT).
  static const refreshMarker = 'RewindBox graphics vsyncFps: 30 to 240 frames per second.';

  /// The launch graphics key and the range the engine accepts.
  static const refreshKey = 'vsyncFps';
  static const minRefresh = 30;
  static const maxRefresh = 240;

  final Future<Directory> Function() _root;
  final Future<Map<String, dynamic>> Function(String gamePath) _metadata;
  final Future<Map<String, dynamic>> Function(String updatePath, String titleId) _inspectUpdate;
  final Future<bool> Function() _refreshSupported;
  final _log = LoggerService.instance;

  /// The installed main Build ID of each identified application (null: not
  /// known) and whether the engine takes `vsyncFps`, from the last [identify].
  final _installedBuilds = <String, String?>{};

  /// The display version that runs (the selected update's), when known.
  final _installedVersions = <String, String?>{};
  bool _refreshTaken = false;

  static final _titleId = RegExp(r'^[0-9A-Fa-f]{16}$');
  static final _buildId = RegExp(r'^[0-9A-F]{16}$');
  static final _opcode = RegExp(r'^[0-9A-F]{8}( [0-9A-F]{8}){0,3}$');
  static final _unsafeName = RegExp(r'//|[#;\[\]{}\r\n]');

  static Future<Map<String, dynamic>> _nativeMetadata(String gamePath) =>
      MelonxInternalService.content('metadata', filePath: gamePath);

  static Future<Map<String, dynamic>> _nativeInspectUpdate(String updatePath, String titleId) =>
      MelonxInternalService.content('inspectUpdate', filePath: updatePath, titleId: titleId);

  static Future<bool>? _refreshSupport;

  /// Whether the Switch engine of this build takes the `vsyncFps` graphics
  /// option, read once from the Core binary without loading it (loading the
  /// Core from a menu would mark the process as a Switch 1 one).
  static Future<bool> engineTakesRefresh() => _refreshSupport ??= _checkRefresh();

  /// For tests: forget the cached answer.
  static void resetRefreshSupport() => _refreshSupport = null;

  static Future<bool> _checkRefresh() async {
    if (!Platform.isIOS) return false;
    final bundle = File(Platform.resolvedExecutable).parent.path;
    try {
      return await Isolate.run(() => refreshSupportedIn(bundle));
    } on Object {
      return false;
    }
  }

  /// Whether the Core of the application bundle at [bundle] takes `vsyncFps`.
  static bool refreshSupportedIn(String bundle) =>
      NextendoEngineSupport.containsAny('$bundle/Frameworks/MeloNXCore.framework/MeloNXCore', const [refreshMarker]);

  /// A Build ID in the cheat files' form (16 upper-case hex digits), or null.
  static String? buildIdOf(Object? value) {
    final text = value?.toString().trim().toUpperCase() ?? '';
    return _buildId.hasMatch(text) && text.replaceAll('0', '').isNotEmpty ? text : null;
  }

  /// The frame rate an FPS code's name targets (`120 FPS (Emulator)` → 120),
  /// when the engine can present at it; null otherwise.
  static int? refreshTarget(String name) {
    final match = RegExp(r'(?<![0-9])([0-9]{2,3}) ?fps', caseSensitive: false).firstMatch(name);
    final value = match == null ? null : int.tryParse(match.group(1)!);
    return value != null && value >= minRefresh && value <= maxRefresh ? value : null;
  }

  /// The engine refresh an FPS entry asks for: its name's target, unless the
  /// catalogue flags it as the game's default or as not raising the limit
  /// (510 `Default` codes and 95 dynamic-resolution targets of the catalogue
  /// of 23 November 2026 named one: `DRT 45 FPS` set 45 Hz on a 30 FPS game).
  /// Null for other categories.
  static int? entryRefresh(Map<String, dynamic> entry) {
    final flags = EnhancementFlags.of(entry);
    if (entry['cat'] != EnhancementCategory.fps.name ||
        flags.contains(EnhancementFlags.restoresDefault) ||
        flags.contains(EnhancementFlags.noRefresh)) {
      return null;
    }
    return refreshTarget(entry['name']?.toString() ?? '');
  }

  /// The selected update of `<root>/games/<titleId>/updates.json` (a path
  /// relative to [root] or absolute under it), when its file exists.
  static Future<String?> selectedUpdate(Directory root, String titleId) async =>
      (await _updateSelection(root, titleId)).path;

  /// Whether an update is selected for [titleId], and its file when it lies
  /// under [root] and exists.
  static Future<({bool selected, String? path})> _updateSelection(Directory root, String titleId) async {
    final file = File(path.join(root.path, 'games', titleId.toLowerCase(), 'updates.json'));
    if (!await file.exists() || await file.length() > 1024 * 1024) return (selected: false, path: null);
    final decoded = jsonDecode(await file.readAsString());
    final selected = decoded is Map ? decoded['selected'] : null;
    if (selected is! String || selected.isEmpty) return (selected: false, path: null);
    final absolute = path.isAbsolute(selected) ? selected : path.normalize(path.join(root.path, selected));
    if (!path.isWithin(root.path, absolute) || !await File(absolute).exists()) return (selected: true, path: null);
    return (selected: true, path: absolute);
  }

  /// The main Build ID of what runs for [titleId]: the selected update's when
  /// one is selected (unknown when its Build ID cannot be read), the game
  /// file's ([baseBuild]) otherwise. Never throws.
  static Future<String?> installedBuild({
    required Directory root,
    required String titleId,
    required String? baseBuild,
    required Future<Map<String, dynamic>> Function(String updatePath, String titleId) inspectUpdate,
  }) async =>
      (await installedRelease(root: root, titleId: titleId, baseBuild: baseBuild, inspectUpdate: inspectUpdate))
          .build;

  /// The Build ID and display version of what runs for [titleId]. An update
  /// that is selected but whose file cannot be found or read leaves both
  /// unknown: the game file's build is not what runs then (a code made for it
  /// would be shown as compatible with the update). Never throws.
  static Future<({String? build, String? version})> installedRelease({
    required Directory root,
    required String titleId,
    required String? baseBuild,
    String? baseVersion,
    required Future<Map<String, dynamic>> Function(String updatePath, String titleId) inspectUpdate,
  }) async {
    try {
      final update = await _updateSelection(root, titleId);
      if (!update.selected) return (build: baseBuild, version: baseVersion);
      if (update.path == null) return (build: null, version: null);
      final report = await inspectUpdate(update.path!, titleId.toLowerCase());
      return (build: buildIdOf(report['buildId']), version: displayVersionOf(report['displayVersion']));
    } on Object {
      return (build: null, version: null);
    }
  }

  /// A display version as the engine reports it (`1.3.2`), or null.
  static String? displayVersionOf(Object? value) {
    final text = value?.toString().replaceAll('\u0000', '').trim() ?? '';
    return text.isEmpty || text.length > 32 ? null : text;
  }

  @override
  EnhancementEngine get engine => EnhancementEngine.melonx;

  @override
  bool handles(String systemFolder) => systemFolder.toLowerCase() == 'switch';

  /// Application Title ID of an update or add-on Title ID.
  static String? applicationTitleId(String? raw) {
    final value = raw?.trim() ?? '';
    if (!_titleId.hasMatch(value)) return null;
    final id = BigInt.parse(value, radix: 16) & ~BigInt.from(0x1FFF);
    return id.toRadixString(16).padLeft(16, '0').toUpperCase();
  }

  /// Catalogue keys Ryujinx may load for an application: the exact Title ID
  /// it reported (homebrew), then a collection's sub-programs (+1 to +15).
  static List<String> programAliases(String application, String? raw) {
    final base = BigInt.parse(application, radix: 16);
    final aliases = <String>[
      if (raw != null && raw != application) raw,
      for (var index = 1; index <= 15; index++)
        (base + BigInt.from(index)).toRadixString(16).padLeft(16, '0').toUpperCase(),
    ];
    return aliases.toSet().toList();
  }

  @override
  Future<bool> listed(EnhancementCatalog catalog, EnhancementGameIdentity identity) async {
    final index = await catalog.index();
    return [identity.key, ...identity.aliases].any((key) => index.contains(engine, key));
  }

  /// One record per program, flattened; each entry knows its program.
  @override
  Future<Map<String, dynamic>?> loadRecord(
    EnhancementCatalog catalog,
    EnhancementGameIdentity identity, {
    bool download = true,
    EnhancementProgress? onProgress,
  }) async {
    final index = await catalog.index();
    final programs = <String, Map<String, dynamic>>{};
    for (final key in [identity.key, ...identity.aliases]) {
      if (!index.contains(engine, key)) continue;
      final record = await catalog.record(engine, key, download: download, onProgress: onProgress);
      if (record == null) return null;
      programs[key] = record;
    }
    if (programs.isEmpty) return null;
    return {
      'programs': programs,
      'entries': [
        for (final program in programs.entries)
          for (final entry in (program.value['entries'] as List? ?? const []))
            if (entry is Map) {...Map<String, dynamic>.from(entry), 'program': program.key},
      ],
      'credits': {
        for (final program in programs.values)
          for (final credit in (program['credits'] as List? ?? const [])) credit.toString(),
      }.toList(),
      'unavailable': [
        for (final program in programs.entries)
          for (final entry in (program.value['unavailable'] as List? ?? const []))
            if (entry is Map) {...Map<String, dynamic>.from(entry), 'program': program.key},
      ],
    };
  }

  @override
  Future<EnhancementGameIdentity> identify(GameModel game, String systemFolder) async {
    String? raw = _rawTitleId(game.titleId);
    var titleId = applicationTitleId(game.titleId);
    String? version;
    String? baseBuild;
    var read = false;
    var title = game.titleName ?? game.name;
    final romPath = game.romPath;
    if (romPath != null && romPath.startsWith('/')) {
      try {
        final report = await _metadata(romPath);
        final reported = report['titleId']?.toString();
        if (applicationTitleId(reported) != null) {
          raw = _rawTitleId(reported);
          titleId = applicationTitleId(reported);
          baseBuild = buildIdOf(report['buildId']);
          read = true;
        }
        final displayVersion = report['version']?.toString().trim() ?? '';
        if (displayVersion.isNotEmpty) version = displayVersion;
        final nativeTitle = report['title']?.toString().trim() ?? '';
        if (nativeTitle.isNotEmpty) title = nativeTitle;
      } catch (error) {
        // The library row's Title ID still identifies the game.
        _log.w('Enhancements: MeloNX metadata unavailable: $error');
      }
    }
    if (titleId == null) {
      return EnhancementGameIdentity.unavailable(
        engine,
        EnhancementProblem.identityUnavailable,
        title: title,
      );
    }
    // Only an engine that reports the game file's Build ID tells which build
    // runs; an older one keeps every code as before. The version shown is the
    // one that runs: the selected update's, unknown when it cannot be read.
    String? installed;
    if (read) {
      try {
        final release = await installedRelease(
          root: await _root(),
          titleId: titleId,
          baseBuild: baseBuild,
          baseVersion: version,
          inspectUpdate: _inspectUpdate,
        );
        installed = baseBuild == null ? null : release.build;
        version = release.version;
      } on Object {
        installed = null;
        version = null;
      }
    }
    _installedBuilds[titleId] = installed;
    _installedVersions[titleId] = version;
    try {
      _refreshTaken = installed != null && await _refreshSupported();
    } on Object {
      _refreshTaken = false;
    }
    return EnhancementGameIdentity(
      engine: engine,
      key: titleId,
      title: title,
      version: version,
      aliases: programAliases(titleId, raw),
    );
  }

  static String? _rawTitleId(String? value) {
    final trimmed = value?.trim() ?? '';
    return _titleId.hasMatch(trimmed) ? trimmed.toUpperCase() : null;
  }

  List<Map<String, dynamic>> _entries(Map<String, dynamic> record) => [
    for (final entry in (record['entries'] as List? ?? const []))
      if (entry is Map) Map<String, dynamic>.from(entry),
  ];

  static Map<String, List<String>> _builds(Map<String, dynamic> entry) {
    final builds = <String, List<String>>{};
    final raw = entry['builds'];
    if (raw is! Map) return builds;
    for (final build in raw.entries) {
      final id = build.key.toString().toUpperCase();
      final lines = [
        for (final line in (build.value as List? ?? const [])) line.toString().toUpperCase(),
      ];
      if (_buildId.hasMatch(id) && lines.isNotEmpty && lines.every(_opcode.hasMatch)) {
        builds[id] = lines;
      }
    }
    return builds;
  }

  static bool _safeName(String name) =>
      name.trim().isNotEmpty && name.trim() == name && !_unsafeName.hasMatch(name);

  static final _nsobid = RegExp(r'^@nsobid-([0-9A-F]{32,64})\n');

  /// IPSwitch patches of an exefs entry: Ryujinx reads the `@nsobid-` header
  /// on the first line and applies the file only to that executable.
  static List<({String bid, String text})> _exefs(Map<String, dynamic> entry) => [
    for (final patch in (entry['exefs'] as List? ?? const []))
      if (patch is Map &&
          patch['text'] is String &&
          _nsobid.firstMatch(patch['text'] as String)?.group(1) == patch['bid'] &&
          (patch['text'] as String).length <= 64 * 1024)
        (bid: patch['bid'] as String, text: patch['text'] as String),
  ];

  /// The record of [program] in a record [loadRecord] merged, else [record].
  static Map<dynamic, dynamic> _programRecord(Map<String, dynamic> record, String program) {
    final programs = record['programs'];
    return programs is Map && programs[program] is Map ? programs[program] as Map : record;
  }

  /// Game versions the catalogue names for each Build ID of [program]:
  /// switch-cheats-db's update numbers (ints, see [updateIndex]), then the
  /// display versions of the patch files (`1.3.2`). Language-neutral: the
  /// page names the updates. Empty for a catalogue without them.
  static Map<String, List<Object>> releasesOf(Map<String, dynamic> record, String program) {
    final raw = _programRecord(record, program)['releases'];
    final releases = <String, List<Object>>{};
    if (raw is! Map) return releases;
    for (final release in raw.entries) {
      final build = buildIdOf(release.key);
      final value = release.value;
      if (build == null || value is! Map) continue;
      final labels = <Object>[
        for (final update in (value['update'] as List? ?? const []))
          if (update is int && update >= 0) update,
        for (final version in (value['display'] as List? ?? const [])) ?displayVersionOf(version),
      ];
      if (labels.isNotEmpty) releases[build] = labels;
    }
    return releases;
  }

  /// The update a versions.json number stands for: they count in steps of
  /// 0x10000, so 393216 is update 6 and 0 the game itself. Null for another
  /// value (shown raw, `v65537`).
  static int? updateIndex(int update) => update >= 0 && update % 0x10000 == 0 ? update >> 16 : null;

  /// The update numbers versions.json gives each Build ID of [program].
  static Map<String, List<int>> updatesOf(Map<String, dynamic> record, String program) {
    final raw = _programRecord(record, program)['releases'];
    final updates = <String, List<int>>{};
    if (raw is! Map) return updates;
    for (final release in raw.entries) {
      final build = buildIdOf(release.key);
      final value = release.value;
      if (build == null || value is! Map) continue;
      final numbers = [
        for (final update in (value['update'] as List? ?? const []))
          if (update is int && update >= 0) update,
      ];
      if (numbers.isNotEmpty) updates[build] = numbers;
    }
    return updates;
  }

  /// The newest update the catalogue knows for [program] (versions.json's
  /// `latest`): its update number, main Build ID and display version.
  static SwitchLatest? latestOf(Map<String, dynamic> record, String program) {
    final latest = _programRecord(record, program)['latest'];
    final update = latest is Map ? latest['update'] : null;
    if (update is! int || update < 0) return null;
    return (update: update, build: buildIdOf(latest['build']), display: displayVersionOf(latest['display']));
  }

  /// Whether an entry is only for versions older than [latest]: none of its
  /// [builds] is the newest known build and each has a lower update number.
  /// A Build ID without one (a newer build, or the module an exefs mod
  /// patches) leaves it unknown: not older.
  static bool olderOnly(Iterable<String> builds, Map<String, List<int>> updates, SwitchLatest? latest) {
    if (latest == null || latest.build == null || builds.isEmpty) return false;
    for (final build in builds) {
      final numbers = updates[build];
      if (build == latest.build || numbers == null || numbers.any((update) => update >= latest.update)) {
        return false;
      }
    }
    return true;
  }

  /// The payload mark of an entry made only for older versions (shown on the
  /// page, never blocking: it still applies to the build it was made for).
  static Map<String, dynamic>? _olderThan(Iterable<String> builds, _Catalogued known) {
    final latest = known.latest;
    if (!olderOnly(builds, known.updates, latest)) return null;
    return {
      'olderThan': {'update': latest!.update, 'display': ?latest.display},
    };
  }

  /// The catalogue's Build IDs whose display version is [version] (the one
  /// that runs, when the engine did not say which build it is).
  static Set<String> buildsOfVersion(Map<String, List<Object>> releases, String? version) {
    final wanted = version?.trim().replaceFirst(RegExp('^[vV]'), '') ?? '';
    if (wanted.isEmpty) return const {};
    return {
      for (final release in releases.entries)
        if (release.value.any((label) => label is String && label.replaceFirst(RegExp('^[vV]'), '') == wanted))
          release.key,
    };
  }

  /// Build IDs with the game versions the catalogue knows for them (at most
  /// four each): update numbers named by [updateName], left out without it,
  /// then display versions.
  static String describeBuilds(
    List<String> builds,
    Map<dynamic, dynamic> releases, {
    String Function(int update)? updateName,
  }) => [
    for (final build in builds) _describeBuild(build, releases[build], updateName),
  ].join(', ');

  static String _describeBuild(String build, Object? labels, String Function(int update)? updateName) {
    final named = [
      for (final label in labels is List ? labels : const [])
        if (label is int) ?updateName?.call(label) else label.toString(),
    ].take(4);
    return named.isEmpty ? build : '$build (${named.join(', ')})';
  }

  /// The Compatibility line of an item, from its payload: `Title ID … ·
  /// Build ID A (Update 6, 1.3.2) · installed …`. The page passes
  /// [updateName] in its language; without it the line stays
  /// language-neutral (display versions only).
  static String compatibilityOf(Map<String, dynamic> payload, {String Function(int update)? updateName}) {
    final builds = [for (final build in (payload['builds'] as List? ?? const [])) build.toString()];
    final installed = payload['installedBuild'];
    final version = payload['installedVersion'];
    return [
      'Title ID ${payload['program']}',
      '${payload['exefs'] == true ? 'exefs ' : ''}Build ID '
          '${describeBuilds(builds, payload['releases'] as Map? ?? const {}, updateName: updateName)}',
      if (installed is String) 'installed $installed' else if (version is String) 'installed version $version',
    ].join(' · ');
  }

  /// The payload part of the game versions the catalogue knows for [builds].
  static Map<String, dynamic>? _releasesFor(Iterable<String> builds, _Catalogued known) {
    final releases = {
      for (final build in builds)
        if (known.releases[build] != null) build: known.releases[build]!,
    };
    return releases.isEmpty ? null : {'releases': releases};
  }

  /// The exclusive group of an entry. Atmosphere codes of one record and
  /// category that write the same targets share an `alt/<key>/<hash>` group
  /// (catalogue of 23 November 2026), kept as is: one alternative of a
  /// setting at a time (`60 FPS` or `45 FPS`). A frame-rate mod is never one
  /// of the display choices: catalogues up to 18 November 2026 read a game
  /// version in its name (`120FPS v1.3.2`) as an aspect ratio and grouped it
  /// with the resolution and ultrawide mods, so turning one of those on
  /// turned the frame-rate mod off. Exefs frame-rate mods of one program
  /// patch the same limit: one of them at a time.
  static String exclusiveGroupOf(
    Map<String, dynamic> entry,
    String program,
    EnhancementCategory category, {
    required bool exefs,
  }) {
    final group = entry['group']?.toString() ?? '';
    if (category != EnhancementCategory.fps) return group;
    if (exefs) return 'fps/${program.toUpperCase()}';
    return group.startsWith('display/') ? '' : group;
  }

  @override
  List<EnhancementItem> items(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState? state,
  ) {
    final items = <EnhancementItem>[];
    final measured = _installedBuilds[identity.key];
    final version = _installedVersions[identity.key];
    final catalogued = <String, _Catalogued>{};
    _Catalogued known(String program) => catalogued[program] ??= (
      releases: releasesOf(record, program),
      updates: updatesOf(record, program),
      latest: latestOf(record, program),
    );
    // The engine did not say which build runs: the version that runs can
    // still name it through the catalogue's version list.
    final inferred = measured == null ? buildsOfVersion(known(identity.key).releases, version) : const <String>{};
    for (final entry in _entries(record)) {
      final id = entry['id']?.toString() ?? '';
      final name = entry['name']?.toString() ?? '';
      final category = EnhancementCategory.parse(entry['cat']?.toString());
      if (id.isEmpty || category == null) continue;
      final program = entry['program']?.toString() ?? identity.key;
      final application = program == identity.key;
      final installed = application ? measured : null;
      final candidates = application ? inferred : const <String>{};
      final versions = known(program);
      final shownVersion = application && installed == null ? version : null;
      final unknown = application && installed == null && candidates.isEmpty;
      // RewindBox offers no expanded DRAM layout: such a mod cannot apply.
      final unsupported = EnhancementFlags.of(entry).contains(EnhancementFlags.dram8gb);
      EnhancementProblem problemOf(bool matches) => !matches
          ? EnhancementProblem.versionMismatch
          : unsupported
          ? EnhancementProblem.unsupportedSystem
          : EnhancementProblem.none;
      // A code turned on before the catalogue flagged it (8 GB DRAM) is still
      // applied by the engine: it shows as on, with its problem, so the page
      // can turn it off (any write drops it, see EnhancementService). One made
      // for another build is not applied: incompatible.
      EnhancementStatus statusOf(EnhancementProblem problem, EnhancementStatus usable) =>
          problem == EnhancementProblem.none
          ? usable
          : problem != EnhancementProblem.versionMismatch && state?.active.contains(id) == true
          ? EnhancementStatus.active
          : EnhancementStatus.incompatible;
      final patches = _exefs(entry);
      if (patches.isNotEmpty) {
        // Exefs mods are written only while active: no installed state.
        final bids = {for (final patch in patches) patch.bid.substring(0, 16)}.toList()..sort();
        final problem = problemOf(
          installed != null ? bids.contains(installed) : candidates.isEmpty || bids.any(candidates.contains),
        );
        final target = installed != null && problem == EnhancementProblem.none && _refreshTaken ? entryRefresh(entry) : null;
        final payload = <String, dynamic>{
          'program': program,
          'builds': bids,
          'exefs': true,
          ...?_releasesFor(bids, versions),
          'installedBuild': ?installed,
          'installedVersion': ?shownVersion,
          'refreshHz': ?target,
          if (unknown) 'buildUnknown': true,
          ...EnhancementFlags.payload(entry),
          ...?_olderThan(bids, versions),
        };
        items.add(
          EnhancementItem(
            id: id,
            engine: engine,
            category: category,
            name: name,
            sourceId: entry['source']?.toString() ?? '',
            author: entry['author']?.toString() ?? '',
            problem: problem,
            status: statusOf(
              problem,
              state?.active.contains(id) == true ? EnhancementStatus.active : EnhancementStatus.available,
            ),
            compatibility: compatibilityOf(payload),
            version: '${bids.length}',
            exclusiveGroup: exclusiveGroupOf(entry, program, category, exefs: true),
            payload: payload,
          ),
        );
        continue;
      }
      final builds = _builds(entry);
      if (!_safeName(name) || builds.isEmpty) continue;
      final buildList = builds.keys.toList()..sort();
      // The installed build is the application's main executable: a
      // collection's other programs run their own and keep their status.
      final problem = problemOf(
        installed != null ? builds.containsKey(installed) : candidates.isEmpty || buildList.any(candidates.contains),
      );
      final target = installed != null && problem == EnhancementProblem.none && _refreshTaken ? entryRefresh(entry) : null;
      final payload = <String, dynamic>{
        'program': program,
        'builds': buildList,
        ...?_releasesFor(buildList, versions),
        'installedBuild': ?installed,
        'installedVersion': ?shownVersion,
        'refreshHz': ?target,
        if (unknown) 'buildUnknown': true,
        ...EnhancementFlags.payload(entry),
        ...?_olderThan(buildList, versions),
      };
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          author: entry['author']?.toString() ?? '',
          status: statusOf(problem, EnhancementAdapter.statusOf(id, state)),
          problem: problem,
          compatibility: compatibilityOf(payload),
          version: '${buildList.length}',
          exclusiveGroup: exclusiveGroupOf(entry, program, category, exefs: false),
          payload: payload,
        ),
      );
    }
    return items;
  }

  /// Whether the build that runs could not be read, so the page cannot tell
  /// which of the application's codes apply (each applies only to the Build
  /// ID its Compatibility names).
  static bool buildUnknown(Iterable<EnhancementItem> items) => items.any(
    (item) => item.engine == EnhancementEngine.melonx && item.payload['buildUnknown'] == true,
  );

  @override
  List<String> credits(Map<String, dynamic> record) => [
    for (final credit in (record['credits'] as List? ?? const [])) credit.toString(),
  ];

  /// The engine refresh an active FPS code sets at the next start (one target
  /// among the active codes), or null.
  static int? engineRefresh(Iterable<EnhancementItem> items) {
    final targets = {
      for (final item in items)
        if (item.engine == EnhancementEngine.melonx && item.status == EnhancementStatus.active && item.payload['refreshHz'] is int)
          item.payload['refreshHz'] as int,
    };
    return targets.length == 1 ? targets.single : null;
  }

  /// When the installed build is known and none of the application's codes is
  /// for it: that build and the catalogue's Build IDs, for the page to say
  /// which game version the codes were made for. Null otherwise.
  static ({String build, List<String> targets})? unmatchedBuild(Iterable<EnhancementItem> items) {
    final measured = [
      for (final item in items)
        if (item.engine == EnhancementEngine.melonx && item.payload['installedBuild'] is String) item,
    ];
    // A mod the engine cannot run (8 GB DRAM) is still made for this build.
    if (measured.isEmpty || measured.any((item) => item.problem != EnhancementProblem.versionMismatch)) return null;
    final targets = <String>{
      for (final item in measured)
        for (final build in (item.payload['builds'] as List? ?? const [])) build.toString(),
    }.toList()..sort();
    return (build: measured.first.payload['installedBuild'] as String, targets: targets);
  }

  /// Program keys Ryujinx uses in enabled.txt.
  static String programKey(String buildId, String name) => '$buildId-<$name Cheat>';

  Future<Directory> _titleDirectory(String titleId) async =>
      Directory(path.join((await _root()).path, 'mods', 'contents', titleId.toLowerCase()));

  Map<String, dynamic> _programData(EnhancementGameState state, String program) {
    final programs = state.data['programs'] is Map
        ? Map<String, dynamic>.from(state.data['programs'] as Map)
        : <String, dynamic>{};
    state.data['programs'] = programs;
    final data = programs[program] is Map
        ? Map<String, dynamic>.from(programs[program] as Map)
        : <String, dynamic>{};
    programs[program] = data;
    return data;
  }

  /// Before the page lists the codes, and before every write: RewindBox's
  /// folder an older version let the player turn off is reclaimed, and the
  /// engine refresh is recomputed from the record and the active codes. A
  /// refresh recorded before the catalogue flagged `Default` and
  /// dynamic-resolution codes kept sending their target at every launch until
  /// a code of the game was switched. Only builds whose target changes are
  /// rewritten, so the enable-list keys a kept build names stay those of the
  /// files on disk. True when the refresh changed.
  @override
  Future<bool> sync(EnhancementGameIdentity identity, Map<String, dynamic> record, EnhancementGameState state) async {
    await _reclaimOwnFolders(identity, record, state);
    final previous = state.data['refresh'];
    if (state.active.isEmpty && previous == null) return false;
    final kept = {
      for (final raw in _unavailableMods(record))
        if (state.active.contains(raw['id']?.toString())) raw['id'].toString(),
    };
    _recordRefresh(identity, record, state, state.active, kept: kept);
    final before = _targets(previous);
    final after = _targets(state.data['refresh']);
    if (before.length == after.length &&
        before.entries.every((build) => after.containsKey(build.key) && after[build.key] == build.value)) {
      if (previous == null) {
        state.data.remove('refresh');
      } else {
        state.data['refresh'] = previous;
      }
      return false;
    }
    // Only the builds whose target changed are rewritten: a build whose target
    // stays keeps its record as written (enable-list keys of the files on disk,
    // even if the catalogue renamed a code since).
    final current = state.data['refresh'];
    if (previous is Map && current is Map) {
      state.data['refresh'] = {
        for (final build in current.entries)
          build.key.toString(): previous[build.key] is Map && after[build.key.toString()] == before[build.key.toString()]
              ? previous[build.key]
              : build.value,
      };
    }
    return true;
  }

  /// The target each build of a recorded refresh sets.
  static Map<String, Object?> _targets(Object? refresh) => {
    if (refresh is Map)
      for (final build in refresh.entries) build.key.toString(): build.value is Map ? (build.value as Map)['hz'] : null,
  };

  /// Each program's RewindBox folder an older version let the player turn
  /// off in the Mods dialog (moved to `mods/rewindbox-disabled`, where the
  /// engine never looks, while the page still said its codes were on): moved
  /// back while this state records files in it, else deleted. Never throws.
  Future<void> _reclaimOwnFolders(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
  ) async {
    final programs = {
      identity.key,
      if (record['programs'] is Map)
        for (final program in (record['programs'] as Map).keys) program.toString(),
    };
    for (final program in programs) {
      try {
        final root = await _root();
        final folder = path.join((await _titleDirectory(program)).path, modName);
        final recorded = state.files.keys.any((key) => path.isWithin(folder, resolveStateKey(root, key)));
        final moved = await MelonxModsService.reclaimOwnFolder(root, program, restore: recorded);
        if (moved != null) {
          _log.i('Enhancements: RewindBox folder of $program ${moved ? 'moved back' : 'deleted'} from mods/rewindbox-disabled');
        }
      } on Object catch (error) {
        _log.w('Enhancements: RewindBox folder of $program not reclaimed: $error');
      }
    }
  }

  @override
  Future<void> apply(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active,
  ) async {
    final records = record['programs'] is Map
        ? Map<String, dynamic>.from(record['programs'] as Map)
        : {identity.key: record};
    final byProgram = <String, List<Map<String, dynamic>>>{};
    for (final entry in _entries(record)) {
      byProgram.putIfAbsent(entry['program']?.toString() ?? identity.key, () => []).add(entry);
    }
    final plans = <String, ({Directory title, Map<String, String> files, Set<String> all, Set<String> active})>{};
    for (final program in byProgram.entries) {
      final source = records[program.key];
      plans[program.key] = await _plan(
        program.key,
        program.value,
        source is Map ? source['master'] : null,
        active,
      );
    }

    final kept = _keepUnavailable(identity, record, state, active);
    final root = await _root();
    _rebaseStateFiles(root, state);

    // A file of the player's at one of these paths is never overwritten.
    for (final plan in plans.values) {
      for (final file in plan.files.keys) {
        final current = await EnhancementFiles.digestOf(File(file));
        if (current != null && current != state.files[stateKey(root, file)]) {
          throw EnhancementException('user_file_present', file);
        }
      }
    }

    // Native enable lists first, so no newly written code runs before it is
    // listed: the engine enables every cheat when enabled.txt is absent.
    for (final plan in plans.entries) {
      await _writeEnabledList(plan.value.title, _programData(state, plan.key), plan.value.all, plan.value.active);
    }

    final written = <String>{};
    for (final plan in plans.values) {
      for (final file in plan.files.entries) {
        final key = stateKey(root, file.key);
        state.files[key] = await EnhancementFiles.writeText(File(file.key), file.value);
        written.add(key);
      }
    }
    for (final stale in state.files.keys.where((p) => !written.contains(p)).toList()) {
      if (_heldBy(stale, kept)) continue;
      if (await EnhancementFiles.deleteIfOwned(File(resolveStateKey(root, stale)), state.files[stale]!)) {
        state.files.remove(stale);
      }
    }
    _recordRefresh(identity, record, state, active, kept: kept);
    state.installed = true;
  }

  /// Exefs mods the record cannot offer now (a source file that could not be
  /// fetched: the newest catalogue lists another patch file for the mod, and
  /// the device is offline) stay as they are while they were on and no other
  /// choice of their group is turned on: their files stay as written and the
  /// engine still applies them. Turning another entry on used to remove them.
  /// They are added to [active]; returns them.
  Set<String> _keepUnavailable(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active,
  ) {
    final taken = <String>{
      for (final entry in _entries(record))
        if (active.contains(entry['id'])) ?_groupOf(entry, identity),
    };
    final kept = <String>{};
    for (final raw in _unavailableMods(record)) {
      final id = raw['id']?.toString() ?? '';
      if (!state.active.contains(id) || active.contains(id)) continue;
      final group = _groupOf(Map<String, dynamic>.from(raw), identity);
      if (group != null && taken.contains(group)) continue;
      kept.add(id);
    }
    active.addAll(kept);
    return kept;
  }

  /// The exefs mods [record] cannot offer now (see [_keepUnavailable]).
  static List<Map<dynamic, dynamic>> _unavailableMods(Map<String, dynamic> record) => [
    for (final raw in (record['unavailable'] as List? ?? const []))
      if (raw is Map && raw['exefs'] == true && raw['cheat'] != true) raw,
  ];

  String? _groupOf(Map<String, dynamic> entry, EnhancementGameIdentity identity) {
    final category = EnhancementCategory.parse(entry['cat']?.toString());
    if (category == null) return null;
    final group = exclusiveGroupOf(
      entry,
      entry['program']?.toString() ?? identity.key,
      category,
      exefs: entry['exefs'] is List || entry['exefs'] == true,
    );
    return group.isEmpty ? null : group;
  }

  /// Whether a recorded file is an exefs patch of a kept mod.
  static bool _heldBy(String key, Set<String> kept) =>
      path.split(key).contains('exefs') && kept.any((id) => path.basename(key).startsWith('$id-'));

  /// The engine refresh of the active FPS codes, per Build ID with the
  /// enable-list keys that carry it (read at launch by [launchRefresh]). Two
  /// active codes with different targets for one build set none; a code
  /// flagged as the game's default or as not raising the limit sets none
  /// ([entryRefresh]).
  void _recordRefresh(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active, {
    Set<String> kept = const {},
  }) {
    final previous = state.data['refresh'];
    final refresh = <String, Map<String, dynamic>>{};
    final conflicts = <String>{};
    for (final entry in _entries(record)) {
      final id = entry['id']?.toString() ?? '';
      final name = entry['name']?.toString() ?? '';
      if (!active.contains(id)) continue;
      final target = entryRefresh(entry);
      if (target == null) continue;
      final program = (entry['program']?.toString() ?? identity.key).toLowerCase();
      // An exefs frame-rate mod (`120FPS v1.3.2`) raises the game's limit
      // like a cheat does: it carries the patch files it writes for a build.
      final patches = _exefs(entry);
      final builds = patches.isNotEmpty
          ? {for (final patch in patches) patch.bid.substring(0, 16)}
          : _safeName(name)
          ? _builds(entry).keys.toSet()
          : const <String>{};
      for (final build in builds) {
        final current = refresh[build];
        if (current != null && current['hz'] != target) {
          conflicts.add(build);
          continue;
        }
        final value = refresh[build] ??= {'hz': target, 'program': program, 'keys': <String>[]};
        if (patches.isEmpty) {
          (value['keys'] as List<String>).add(programKey(build, name));
          continue;
        }
        final files = (value['exefs'] as List<String>?) ?? (value['exefs'] = <String>[]);
        for (var index = 0; index < patches.length; index++) {
          if (patches[index].bid.startsWith(build)) files.add('$id-$index.pchtxt');
        }
      }
    }
    conflicts.forEach(refresh.remove);
    // A kept mod (see _keepUnavailable) keeps the refresh its files carry.
    if (previous is Map && kept.isNotEmpty) {
      for (final value in previous.entries) {
        final files = [
          for (final file in (value.value is Map ? (value.value as Map)['exefs'] as List? ?? const [] : const []))
            if (kept.any((id) => file.toString().startsWith('$id-'))) file.toString(),
        ];
        if (files.isEmpty || refresh.containsKey(value.key)) continue;
        refresh[value.key.toString()] = {...Map<String, dynamic>.from(value.value as Map), 'keys': <String>[], 'exefs': files};
      }
    }
    if (refresh.isEmpty) {
      state.data.remove('refresh');
    } else {
      state.data['refresh'] = refresh;
    }
  }

  /// The `vsyncFps` of a launch: the target of an FPS code that is on for the
  /// build that runs, only when the engine takes the option, the code's
  /// RewindBox file is on disk and the engine's enable list names it (a code
  /// the engine would not install never raises the refresh: a game made for
  /// 60 Hz could then run fast). Null otherwise; never throws.
  static Future<int?> launchRefresh(
    String gamePath, {
    Future<List<EnhancementGameState>> Function()? states,
    Future<Directory> Function()? root,
    Future<Map<String, dynamic>> Function(String gamePath)? metadata,
    Future<Map<String, dynamic>> Function(String updatePath, String titleId)? inspectUpdate,
    Future<bool> Function()? supported,
  }) async {
    try {
      final all = await (states ?? EnhancementStore.instance.all)();
      final candidates = [
        for (final state in all)
          if (state.engine == EnhancementEngine.melonx.name && state.data['refresh'] is Map && (state.data['refresh'] as Map).isNotEmpty)
            state,
      ];
      if (candidates.isEmpty) return null;
      final report = await (metadata ?? _nativeMetadata)(gamePath);
      final titleId = applicationTitleId(report['titleId']?.toString());
      final baseBuild = buildIdOf(report['buildId']);
      if (titleId == null || baseBuild == null) return null;
      EnhancementGameState? state;
      for (final candidate in candidates) {
        if (candidate.key == titleId) state = candidate;
      }
      if (state == null) return null;
      final directory = await (root ?? MelonxInternalService.rootDirectory)();
      final build = await installedBuild(
        root: directory,
        titleId: titleId,
        baseBuild: baseBuild,
        inspectUpdate: inspectUpdate ?? _nativeInspectUpdate,
      );
      final entry = build == null ? null : (state.data['refresh'] as Map)[build];
      if (entry is! Map) return null;
      final hz = entry['hz'];
      final program = entry['program']?.toString() ?? '';
      if (hz is! int || hz < minRefresh || hz > maxRefresh || !_titleId.hasMatch(program)) return null;
      final keys = {for (final key in (entry['keys'] as List? ?? const [])) key.toString()};
      final title = path.join(directory.path, 'mods', 'contents', program);
      if (!await _exefsWritten(title, build!, entry['exefs']) && !await _cheatListed(title, build, keys)) return null;
      if (!await (supported ?? engineTakesRefresh)()) return null;
      return hz;
    } on Object {
      return null;
    }
  }

  /// Whether the engine installs one of [keys] for [build]: RewindBox's cheat
  /// file of that build holds it and the enable list names it.
  static Future<bool> _cheatListed(String title, String build, Set<String> keys) async {
    if (keys.isEmpty) return false;
    final enabled = File(path.join(title, 'cheats', 'enabled.txt'));
    final file = File(path.join(title, modName, 'cheats', '$build.txt'));
    if (!await enabled.exists() || !await file.exists()) return false;
    final listed = {for (final line in await enabled.readAsLines()) line.trim()};
    final written = {for (final name in parseCheatNames(await file.readAsString())) programKey(build, name)};
    return keys.any((key) => listed.contains(key) && written.contains(key));
  }

  /// Whether one of the exefs patch files an active frame-rate mod writes for
  /// [build] is on disk, headed by that executable's Build ID (the engine
  /// applies a `.pchtxt` only to the executable its `@nsobid-` line names).
  static Future<bool> _exefsWritten(String title, String build, Object? files) async {
    for (final name in (files as List? ?? const [])) {
      final file = name.toString();
      if (path.basename(file) != file || !file.endsWith('.pchtxt')) continue;
      final patch = File(path.join(title, modName, 'exefs', file));
      if (!await patch.exists() || await patch.length() > 64 * 1024) continue;
      if ((await patch.readAsString()).startsWith('@nsobid-$build')) return true;
    }
    return false;
  }

  /// The recorded files are keyed relative to the MeloNX root. iOS can move
  /// the app container between installs (a Hogwarts Legacy player's moved
  /// between IPA 658 and 672), and absolute keys then named files RewindBox
  /// could no longer find: its own files were refused as the player's and a
  /// restore left them on disk without their enable list.
  static String stateKey(Directory root, String file) => path.relative(file, from: root.path);

  /// The current path of a recorded key; an absolute key written by an older
  /// version is re-rooted at the current MeloNX root. Every file RewindBox
  /// records lies under `<root>/mods/`, so the root is the segment named like
  /// it that is directly followed by `mods` (a deeper segment of the same name
  /// cannot be taken for it).
  static String resolveStateKey(Directory root, String key) {
    if (!path.isAbsolute(key)) return path.join(root.path, key);
    final parts = path.split(key);
    final name = path.basename(root.path);
    for (var index = 0; index + 1 < parts.length; index++) {
      if (parts[index] == name && parts[index + 1] == 'mods') {
        return path.joinAll([root.path, ...parts.sublist(index + 1)]);
      }
    }
    return key;
  }

  static void _rebaseStateFiles(Directory root, EnhancementGameState state) {
    final entries = state.files.entries.toList();
    state.files.clear();
    for (final entry in entries) {
      state.files[stateKey(root, resolveStateKey(root, entry.key))] = entry.value;
    }
  }

  /// Files and enable-list keys of one program's directory.
  Future<({Directory title, Map<String, String> files, Set<String> all, Set<String> active})> _plan(
    String program,
    List<Map<String, dynamic>> entries,
    Object? rawMasters,
    Set<String> active,
  ) async {
    final titleDirectory = await _titleDirectory(program);
    final cheatsDirectory = Directory(path.join(titleDirectory.path, modName, 'cheats'));
    final exefsDirectory = Directory(path.join(titleDirectory.path, modName, 'exefs'));
    final exefsFiles = <String, String>{};
    final masters = <String, List<String>>{};
    if (rawMasters is Map) {
      for (final master in rawMasters.entries) {
        final lines = [
          for (final line in (master.value as List? ?? const [])) line.toString().toUpperCase(),
        ];
        final id = master.key.toString().toUpperCase();
        if (_buildId.hasMatch(id) && lines.isNotEmpty && lines.every(_opcode.hasMatch)) {
          masters[id] = lines;
        }
      }
    }

    // One Atmosphere file per Build ID with only the enabled programs: the
    // engine enables every cheat of a file when enabled.txt is absent, so a
    // lost list must never run a code the player did not choose (a Hogwarts
    // Legacy player ran 93 catalogue codes at once). Every catalogue program
    // still has its enable-list key, so the list stays RewindBox's to manage.
    final perBuild = <String, StringBuffer>{};
    final allKeys = <String>{};
    final allBuilds = <String>{};
    final activeKeys = <String>{};
    final activeBuilds = <String>{};
    for (final entry in entries) {
      final id = entry['id']?.toString() ?? '';
      final name = entry['name']?.toString() ?? '';
      if (id.isEmpty) continue;
      final patches = _exefs(entry);
      if (patches.isNotEmpty) {
        if (active.contains(id)) {
          for (var index = 0; index < patches.length; index++) {
            exefsFiles[path.join(exefsDirectory.path, '$id-$index.pchtxt')] = patches[index].text;
          }
        }
        if (!entry.containsKey('builds')) continue;
      }
      if (!_safeName(name)) continue;
      for (final build in _builds(entry).entries) {
        final key = programKey(build.key, name);
        allKeys.add(key);
        allBuilds.add(build.key);
        if (!active.contains(id)) continue;
        activeKeys.add(key);
        activeBuilds.add(build.key);
        final buffer = perBuild.putIfAbsent(build.key, () {
          final header = StringBuffer();
          final master = masters[build.key];
          if (master != null) {
            header.writeln('[$masterName]');
            master.forEach(header.writeln);
            header.writeln();
          }
          return header;
        });
        buffer.writeln('[$name]');
        build.value.forEach(buffer.writeln);
        buffer.writeln();
      }
    }
    for (final build in masters.keys) {
      if (allBuilds.contains(build)) allKeys.add(programKey(build, masterName));
    }
    for (final build in activeBuilds) {
      if (masters.containsKey(build)) activeKeys.add(programKey(build, masterName));
    }
    return (
      title: titleDirectory,
      files: {
        for (final build in perBuild.entries)
          path.join(cheatsDirectory.path, '${build.key}.txt'): build.value.toString(),
        ...exefsFiles,
      },
      all: allKeys,
      active: activeKeys,
    );
  }

  Future<void> _writeEnabledList(
    Directory titleDirectory,
    Map<String, dynamic> data,
    Set<String> allKeys,
    Set<String> activeKeys,
  ) async {
    final file = File(path.join(titleDirectory.path, 'cheats', 'enabled.txt'));
    final ours = <String>{
      ...allKeys,
      for (final key in (data['keys'] as List? ?? const [])) key.toString(),
    };
    List<String> foreign;
    if (await file.exists()) {
      foreign = [
        for (final line in (await file.readAsLines()))
          if (line.trim().isNotEmpty && !ours.contains(line.trim())) line.trim(),
      ];
    } else {
      // Every existing cheat was enabled by the missing list: keep them so.
      foreign = await _existingProgramKeys(titleDirectory);
      data['enabledListCreated'] = true;
    }
    final lines = [...foreign, ...(activeKeys.toList()..sort())];
    await EnhancementFiles.writeText(file, lines.isEmpty ? '' : '${lines.join('\n')}\n');
    data['keys'] = allKeys.toList()..sort();
    // The codes the player chose here, read back before every launch (disableUnchosenCatalogueCheats).
    data['activeKeys'] = activeKeys.toList()..sort();
  }

  /// Enable-list keys of the codes the player turned on in RewindBox, from
  /// the enhancement state of every MeloNX game (recorded by apply).
  static Set<String> chosenKeys(Iterable<EnhancementGameState> states) => {
    for (final state in states)
      if (state.engine == 'melonx' && state.data['programs'] is Map)
        for (final program in (state.data['programs'] as Map).values)
          if (program is Map)
            for (final key in (program['activeKeys'] as List? ?? const [])) key.toString(),
  };

  /// Before a launch: no RewindBox catalogue code runs unless the player chose
  /// it in RewindBox ([chosen], from [chosenKeys]).
  ///
  /// A Hogwarts Legacy player ran 93 catalogue codes at once, ten conflicting
  /// resolution codes among them, and the game aborted within two minutes in
  /// every session: the RewindBox files held every catalogue program of the
  /// version, and either their enable list was gone (the engine then enables
  /// every cheat) or it still listed codes the player could no longer turn off.
  /// Each title holding RewindBox cheat files gets an enable list without the
  /// catalogue codes that are not in [chosen]; the player's own cheat files keep
  /// the engine's default (they stay listed) and other lines of the list stay.
  /// Returns the title IDs whose list was written.
  static Future<List<String>> disableUnchosenCatalogueCheats(Directory root, Set<String> chosen) async {
    final contents = Directory(path.join(root.path, 'mods', 'contents'));
    final repaired = <String>[];
    if (!await contents.exists()) return repaired;
    await for (final title in contents.list(followLinks: false)) {
      if (title is! Directory) continue;
      final ours = Directory(path.join(title.path, modName, 'cheats'));
      if (!await ours.exists()) continue;
      final catalogue = <String>{};
      await for (final file in ours.list(followLinks: false)) {
        final stem = path.basenameWithoutExtension(file.path);
        if (file is! File || path.extension(file.path).toLowerCase() != '.txt' || !_buildId.hasMatch(stem.toUpperCase())) {
          continue;
        }
        for (final name in parseCheatNames(await file.readAsString())) {
          catalogue.add(programKey(stem.toUpperCase(), name));
        }
      }
      if (catalogue.isEmpty) continue;
      final enabled = File(path.join(title.path, 'cheats', 'enabled.txt'));
      final List<String> lines;
      if (await enabled.exists()) {
        final current = [
          for (final line in await enabled.readAsLines())
            if (line.trim().isNotEmpty) line.trim(),
        ];
        lines = [for (final line in current) if (!catalogue.contains(line) || chosen.contains(line)) line];
        if (lines.length == current.length) continue;
      } else {
        // The engine enables every cheat without a list: list the player's own
        // files (its default for them) and only the chosen catalogue codes.
        lines = [
          ...await _existingProgramKeysIn(root, title),
          ...(catalogue.where(chosen.contains).toList()..sort()),
        ];
      }
      await EnhancementFiles.writeText(enabled, lines.isEmpty ? '' : '${lines.join('\n')}\n');
      repaired.add(path.basename(title.path));
    }
    return repaired;
  }

  /// Programs of the player's own cheat files, parsed like Ryujinx does.
  Future<List<String>> _existingProgramKeys(Directory titleDirectory) async =>
      _existingProgramKeysIn(await _root(), titleDirectory);

  static Future<List<String>> _existingProgramKeysIn(Directory root, Directory titleDirectory) async {
    final title = path.basename(titleDirectory.path);
    final directories = [
      titleDirectory,
      Directory(path.join(root.path, 'sdcard', 'atmosphere', 'contents', title)),
    ];
    final keys = <String>[];
    for (final directory in directories) {
      if (!await directory.exists()) continue;
      await for (final entity in directory.list(recursive: true, followLinks: false)) {
        if (entity is! File) continue;
        final parent = path.basename(entity.parent.path).toLowerCase();
        final stem = path.basenameWithoutExtension(entity.path);
        if (parent != 'cheats' ||
            path.extension(entity.path).toLowerCase() != '.txt' ||
            !RegExp(r'^[0-9A-Fa-f]{16}$').hasMatch(stem) ||
            path.split(entity.path).contains(modName)) {
          continue;
        }
        final build = stem.toUpperCase();
        for (final name in parseCheatNames(await entity.readAsString())) {
          keys.add(programKey(build, name));
        }
      }
    }
    return keys;
  }

  /// Section names of an Atmosphere file as Ryujinx's GetCheatsInFile reads
  /// them; an empty list when the engine would skip the whole file.
  static List<String> parseCheatNames(String text) {
    final names = <String>[];
    var name = '<default>';
    var instructions = 0;
    for (var line in text.split('\n')) {
      final comment = [
        line.indexOf('//'),
        line.indexOf('#'),
        line.indexOf(';'),
      ].where((index) => index >= 0);
      if (comment.isNotEmpty) line = line.substring(0, comment.reduce((a, b) => a < b ? a : b));
      line = line.trim();
      if (line.startsWith('﻿')) line = line.substring(1).trimLeft();
      if (line.isEmpty || (line.length >= 2 && line.startsWith('{') && line.endsWith('}'))) {
        continue;
      }
      if (line.startsWith('[')) {
        if (!line.endsWith(']') || line.length < 3) return const [];
        if (instructions > 0) names.add(name);
        name = line.substring(1, line.length - 1);
        instructions = 0;
      } else {
        instructions++;
      }
    }
    if (instructions > 0) names.add(name);
    return names;
  }

  @override
  Future<void> remove(EnhancementGameState state) async {
    final root = await _root();
    _rebaseStateFiles(root, state);
    for (final entry in state.files.entries.toList()) {
      if (!await EnhancementFiles.deleteIfOwned(File(resolveStateKey(root, entry.key)), entry.value)) {
        _log.w('Enhancements: ${entry.key} changed since RewindBox wrote it; kept');
      }
      state.files.remove(entry.key);
    }
    final contents = Directory(path.join((await _root()).path, 'mods', 'contents'));
    final programs = state.data['programs'] is Map ? state.data['programs'] as Map : const {};
    for (final program in programs.entries) {
      final data = program.value is Map ? program.value as Map : const {};
      final titleDirectory = await _titleDirectory(program.key.toString());
      final enabled = File(path.join(titleDirectory.path, 'cheats', 'enabled.txt'));
      if (data['enabledListCreated'] == true) {
        // The list did not exist: deleting it restores the engine's default.
        if (await enabled.exists()) await enabled.delete();
      } else if (await enabled.exists()) {
        final ours = {for (final key in (data['keys'] as List? ?? const [])) key.toString()};
        final kept = [
          for (final line in await enabled.readAsLines())
            if (line.trim().isNotEmpty && !ours.contains(line.trim())) line.trim(),
        ];
        await EnhancementFiles.writeText(enabled, kept.isEmpty ? '' : '${kept.join('\n')}\n');
      }
      await EnhancementFiles.deleteEmptyParents(
        Directory(path.join(titleDirectory.path, modName, 'cheats')),
        contents,
      );
      await EnhancementFiles.deleteEmptyParents(
        Directory(path.join(titleDirectory.path, modName, 'exefs')),
        contents,
      );
      await EnhancementFiles.deleteEmptyParents(Directory(path.join(titleDirectory.path, 'cheats')), contents);
    }
    // A copy of RewindBox's folder an older version let the player turn off is RewindBox's too.
    for (final program in {state.key, for (final program in programs.keys) program.toString()}) {
      try {
        await MelonxModsService.reclaimOwnFolder(root, program, restore: false);
      } on Object catch (error) {
        _log.w('Enhancements: RewindBox folder of $program in mods/rewindbox-disabled kept: $error');
      }
    }
    state.data.clear();
    state.installed = false;
    state.active.clear();
  }
}

/// The newest update versions.json knows for a Switch program: its update
/// number, main Build ID and display version (from a patch file's name).
typedef SwitchLatest = ({int update, String? build, String? display});

/// The game versions the catalogue knows for one program.
typedef _Catalogued = ({Map<String, List<Object>> releases, Map<String, List<int>> updates, SwitchLatest? latest});
