import 'dart:io';

import 'package:path/path.dart' as path;

import '../../../models/game_model.dart';
import '../../logger_service.dart';
import '../../melonx_internal_service.dart';
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
class MelonxEnhancementAdapter extends EnhancementAdapter {
  MelonxEnhancementAdapter({
    Future<Directory> Function()? root,
    Future<Map<String, dynamic>> Function(String gamePath)? metadata,
  }) : _root = root ?? MelonxInternalService.rootDirectory,
       _metadata = metadata ?? _nativeMetadata;

  static const modName = 'RewindBox';
  static const masterName = 'RewindBox master code';

  final Future<Directory> Function() _root;
  final Future<Map<String, dynamic>> Function(String gamePath) _metadata;
  final _log = LoggerService.instance;

  static final _titleId = RegExp(r'^[0-9A-Fa-f]{16}$');
  static final _buildId = RegExp(r'^[0-9A-F]{16}$');
  static final _opcode = RegExp(r'^[0-9A-F]{8}( [0-9A-F]{8}){0,3}$');
  static final _unsafeName = RegExp(r'//|[#;\[\]{}\r\n]');

  static Future<Map<String, dynamic>> _nativeMetadata(String gamePath) =>
      MelonxInternalService.content('metadata', filePath: gamePath);

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
    var title = game.titleName ?? game.name;
    final romPath = game.romPath;
    if (romPath != null && romPath.startsWith('/')) {
      try {
        final report = await _metadata(romPath);
        final reported = report['titleId']?.toString();
        if (applicationTitleId(reported) != null) {
          raw = _rawTitleId(reported);
          titleId = applicationTitleId(reported);
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
      final patches = _exefs(entry);
      if (patches.isNotEmpty) {
        // Exefs mods are written only while active: no installed state.
        final bids = [for (final patch in patches) patch.bid.substring(0, 16)]..sort();
        items.add(
          EnhancementItem(
            id: id,
            engine: engine,
            category: category,
            name: name,
            sourceId: entry['source']?.toString() ?? '',
            status: state?.active.contains(id) == true
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
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          status: EnhancementAdapter.statusOf(id, state),
          compatibility:
              'Title ID ${entry['program'] ?? identity.key} · Build ID ${buildList.join(', ')}',
          version: '${buildList.length}',
          exclusiveGroup: entry['group']?.toString() ?? '',
          payload: {'builds': buildList},
        ),
      );
    }
    return items;
  }

  @override
  List<String> credits(Map<String, dynamic> record) => [
    for (final credit in (record['credits'] as List? ?? const [])) credit.toString(),
  ];

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

    // A file of the player's at one of these paths is never overwritten.
    for (final plan in plans.values) {
      for (final file in plan.files.keys) {
        final current = await EnhancementFiles.digestOf(File(file));
        if (current != null && current != state.files[file]) {
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
        state.files[file.key] = await EnhancementFiles.writeText(File(file.key), file.value);
        written.add(file.key);
      }
    }
    for (final stale in state.files.keys.where((p) => !written.contains(p)).toList()) {
      if (await EnhancementFiles.deleteIfOwned(File(stale), state.files[stale]!)) {
        state.files.remove(stale);
      }
    }
    state.installed = true;
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

    // One Atmosphere file per Build ID with every listed program.
    final perBuild = <String, StringBuffer>{};
    final allKeys = <String>{};
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
        continue;
      }
      if (!_safeName(name)) continue;
      for (final build in _builds(entry).entries) {
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
        final key = programKey(build.key, name);
        allKeys.add(key);
        if (active.contains(id)) {
          activeKeys.add(key);
          activeBuilds.add(build.key);
        }
      }
    }
    for (final build in masters.keys) {
      if (perBuild.containsKey(build)) allKeys.add(programKey(build, masterName));
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
  }

  /// Programs of the player's own cheat files, parsed like Ryujinx does.
  Future<List<String>> _existingProgramKeys(Directory titleDirectory) async {
    final root = await _root();
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
    for (final entry in state.files.entries.toList()) {
      if (!await EnhancementFiles.deleteIfOwned(File(entry.key), entry.value)) {
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
