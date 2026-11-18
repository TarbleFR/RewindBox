import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:path/path.dart' as path;

import '../../../models/game_model.dart';
import '../../logger_service.dart';
import '../../melonx_internal_service.dart';
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
/// selected update (`games/<title id>/updates.json`) is what runs. When it is
/// known, a code of the application whose catalogue Build IDs do not include it
/// is shown incompatible (the engine would skip it silently); without it (an
/// older engine) nothing changes.
///
/// An FPS code with a target (`120 FPS`) only raises the game's own limit; the
/// engine still presents at the Switch's 60 Hz unless its refresh follows. An
/// engine that takes the `vsyncFps` graphics option (its marker text is in the
/// Core binary) gets the code's target at launch ([launchRefresh]) while the
/// code is on for the installed build; off, the player's VSync choice applies.
/// An engine without the option is never sent it (it refuses unknown keys).
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

  /// The selected update of `<root>/games/<titleId>/updates.json` (a path
  /// relative to [root] or absolute under it), when its file exists.
  static Future<String?> selectedUpdate(Directory root, String titleId) async {
    final file = File(path.join(root.path, 'games', titleId.toLowerCase(), 'updates.json'));
    if (!await file.exists() || await file.length() > 1024 * 1024) return null;
    final decoded = jsonDecode(await file.readAsString());
    final selected = decoded is Map ? decoded['selected'] : null;
    if (selected is! String || selected.isEmpty) return null;
    final absolute = path.isAbsolute(selected) ? selected : path.normalize(path.join(root.path, selected));
    if (!path.isWithin(root.path, absolute)) return null;
    return await File(absolute).exists() ? absolute : null;
  }

  /// The main Build ID of what runs for [titleId]: the selected update's when
  /// one is selected (unknown when its Build ID cannot be read), the game
  /// file's ([baseBuild]) otherwise. Never throws.
  static Future<String?> installedBuild({
    required Directory root,
    required String titleId,
    required String? baseBuild,
    required Future<Map<String, dynamic>> Function(String updatePath, String titleId) inspectUpdate,
  }) async {
    try {
      final update = await selectedUpdate(root, titleId);
      if (update == null) return baseBuild;
      return buildIdOf((await inspectUpdate(update, titleId.toLowerCase()))['buildId']);
    } on Object {
      return null;
    }
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
    // runs; an older one keeps every code as before.
    String? installed;
    if (read && baseBuild != null) {
      try {
        installed = await installedBuild(root: await _root(), titleId: titleId, baseBuild: baseBuild, inspectUpdate: _inspectUpdate);
      } on Object {
        installed = null;
      }
    }
    _installedBuilds[titleId] = installed;
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

  @override
  List<EnhancementItem> items(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState? state,
  ) {
    final items = <EnhancementItem>[];
    for (final entry in _entries(record)) {
      final id = entry['id']?.toString() ?? '';
      final name = entry['name']?.toString() ?? '';
      final category = EnhancementCategory.parse(entry['cat']?.toString());
      if (id.isEmpty || category == null) continue;
      final program = entry['program']?.toString() ?? identity.key;
      final installed = program == identity.key ? _installedBuilds[identity.key] : null;
      final patches = _exefs(entry);
      if (patches.isNotEmpty) {
        // Exefs mods are written only while active: no installed state.
        final bids = [for (final patch in patches) patch.bid.substring(0, 16)]..sort();
        final matches = installed == null || bids.contains(installed);
        items.add(
          EnhancementItem(
            id: id,
            engine: engine,
            category: category,
            name: name,
            sourceId: entry['source']?.toString() ?? '',
            problem: matches ? EnhancementProblem.none : EnhancementProblem.versionMismatch,
            status: !matches ? EnhancementStatus.incompatible : state?.active.contains(id) == true
                ? EnhancementStatus.active
                : EnhancementStatus.available,
            compatibility:
                'Title ID ${entry['program'] ?? identity.key} · exefs Build ID ${bids.join(', ')}',
            version: '${bids.length}',
            exclusiveGroup: entry['group']?.toString() ?? '',
            payload: {'builds': bids, 'exefs': true},
          ),
        );
        continue;
      }
      final builds = _builds(entry);
      if (!_safeName(name) || builds.isEmpty) continue;
      final buildList = builds.keys.toList()..sort();
      // The installed build is the application's main executable: a
      // collection's other programs run their own and keep their status.
      final matches = installed == null || builds.containsKey(installed);
      final target = category == EnhancementCategory.fps && installed != null && matches && _refreshTaken
          ? refreshTarget(name)
          : null;
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          status: matches ? EnhancementAdapter.statusOf(id, state) : EnhancementStatus.incompatible,
          problem: matches ? EnhancementProblem.none : EnhancementProblem.versionMismatch,
          compatibility:
              'Title ID $program · Build ID ${buildList.join(', ')}${installed == null ? '' : ' · installed $installed'}',
          version: '${buildList.length}',
          exclusiveGroup: entry['group']?.toString() ?? '',
          payload: {
            'builds': buildList,
            'installedBuild': ?installed,
            'refreshHz': ?target,
          },
        ),
      );
    }
    return items;
  }

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
    if (measured.isEmpty || measured.any((item) => item.status != EnhancementStatus.incompatible)) return null;
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
      if (await EnhancementFiles.deleteIfOwned(File(resolveStateKey(root, stale)), state.files[stale]!)) {
        state.files.remove(stale);
      }
    }
    _recordRefresh(identity, record, state, active);
    state.installed = true;
  }

  /// The engine refresh of the active FPS codes, per Build ID with the
  /// enable-list keys that carry it (read at launch by [launchRefresh]). Two
  /// active codes with different targets for one build set none.
  void _recordRefresh(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active,
  ) {
    final refresh = <String, Map<String, dynamic>>{};
    final conflicts = <String>{};
    for (final entry in _entries(record)) {
      final id = entry['id']?.toString() ?? '';
      final name = entry['name']?.toString() ?? '';
      if (!active.contains(id) || entry['cat'] != EnhancementCategory.fps.name || !_safeName(name)) continue;
      final target = refreshTarget(name);
      if (target == null) continue;
      final program = (entry['program']?.toString() ?? identity.key).toLowerCase();
      for (final build in _builds(entry).keys) {
        final current = refresh[build];
        if (current != null && current['hz'] != target) {
          conflicts.add(build);
          continue;
        }
        final value = refresh[build] ??= {'hz': target, 'program': program, 'keys': <String>[]};
        (value['keys'] as List<String>).add(programKey(build, name));
      }
    }
    conflicts.forEach(refresh.remove);
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
      final enabled = File(path.join(title, 'cheats', 'enabled.txt'));
      final file = File(path.join(title, modName, 'cheats', '$build.txt'));
      if (!await enabled.exists() || !await file.exists()) return null;
      final listed = {for (final line in await enabled.readAsLines()) line.trim()};
      final written = {for (final name in parseCheatNames(await file.readAsString())) programKey(build!, name)};
      if (!keys.any((key) => listed.contains(key) && written.contains(key))) return null;
      if (!await (supported ?? engineTakesRefresh)()) return null;
      return hz;
    } on Object {
      return null;
    }
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
    state.data.clear();
    state.installed = false;
    state.active.clear();
  }
}
