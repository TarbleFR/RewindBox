import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as path;

import '../../../models/game_model.dart';
import '../../rpcs3_internal_service.dart';
import '../../rpcs3_launch_service.dart';
import '../../rpcs3_library_service.dart';
import '../enhancement_adapter.dart';
import '../enhancement_models.dart';
import '../enhancement_store.dart';

/// RPCS3 game patches (patch.yml 1.2) through the bridge's own pipeline.
///
/// `Data/NeoStationUnifiedCheats/state.json` is the staging file the RPCS3
/// bridge applies before every boot (RPCS3UnifiedCheats
/// applyPendingWhileStoppedForTitle): it validates the document with the
/// Core's real YAML parser, publishes `patches/<SERIAL>_patch.yml` and calls
/// the Core's set_enabled for each record. RewindBox adds pending records
/// there and never writes the Core's configuration itself. A record names a
/// serial, an APP_VER and a PPU hash: the Core applies it only to that exact
/// executable, so a patch of another game version is never applied.
class Rpcs3EnhancementAdapter extends EnhancementAdapter {
  Rpcs3EnhancementAdapter({
    Future<Directory> Function()? dataDirectory,
    Future<String?> Function(String serial)? installedVersion,
  }) : _dataDirectory = dataDirectory ?? Rpcs3InternalService.dataDirectory,
       _installedVersion = installedVersion ?? _libraryVersion;

  static const sourceTag = 'rewindbox-enhancements';
  static const descriptionPrefix = 'RewindBox/';

  final Future<Directory> Function() _dataDirectory;
  final Future<String?> Function(String serial) _installedVersion;

  static final _version = RegExp(r'^[0-9]{2}\.[0-9]{2}$');
  static final _hash = RegExp(r'^PPU-[0-9A-Fa-f]{40}$');

  static Future<String?> _libraryVersion(String serial) async {
    final cached = Rpcs3LibraryService.cachedGameForTitleId(serial)?.version;
    if (cached != null && cached.isNotEmpty) return cached;
    for (final game in await Rpcs3LibraryService.installedGames()) {
      if (game.titleId.toUpperCase() == serial && game.version.isNotEmpty) {
        return game.version;
      }
    }
    return null;
  }

  @override
  EnhancementEngine get engine => EnhancementEngine.rpcs3;

  @override
  bool handles(String systemFolder) => systemFolder.toLowerCase() == 'ps3';

  @override
  Future<EnhancementGameIdentity> identify(GameModel game, String systemFolder) async {
    final serial = Rpcs3LaunchService.normalizeTitleId(game.titleId);
    final title = game.titleName ?? game.name;
    if (serial == null) {
      return EnhancementGameIdentity.unavailable(
        engine,
        EnhancementProblem.identityUnavailable,
        title: title,
      );
    }
    final version = await _installedVersion(serial);
    return EnhancementGameIdentity(
      engine: engine,
      key: serial,
      title: title,
      version: version != null && _version.hasMatch(version) ? version : null,
    );
  }

  List<Map<String, dynamic>> _entries(Map<String, dynamic> record) => [
    for (final entry in (record['entries'] as List? ?? const []))
      if (entry is Map) Map<String, dynamic>.from(entry),
  ];

  /// Targets of [entry] valid for [version]: one PPU hash each.
  static List<Map<String, dynamic>> targetsFor(Map<String, dynamic> entry, String? version) => [
    if (version != null)
      for (final target in (entry['targets'] as List? ?? const []))
        if (target is Map &&
            (target['versions'] as List? ?? const []).contains(version) &&
            _hash.hasMatch(target['hash']?.toString() ?? '') &&
            (target['title']?.toString() ?? '').isNotEmpty &&
            target['patch'] is List &&
            (target['patch'] as List).isNotEmpty)
          Map<String, dynamic>.from(target),
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
      if (id.isEmpty || name.isEmpty || category == null) continue;
      final versions = <String>{
        for (final target in (entry['targets'] as List? ?? const []))
          if (target is Map)
            for (final version in (target['versions'] as List? ?? const [])) version.toString(),
      }.toList()
        ..sort();
      final compatible = targetsFor(entry, identity.version).isNotEmpty;
      final problem = identity.version == null
          ? EnhancementProblem.versionUnknown
          : compatible
          ? EnhancementProblem.none
          : EnhancementProblem.versionMismatch;
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          status: problem == EnhancementProblem.none
              ? EnhancementAdapter.statusOf(id, state)
              : EnhancementStatus.incompatible,
          problem: problem,
          description: entry['notes']?.toString() ?? '',
          author: entry['author']?.toString() ?? '',
          compatibility: '${identity.key} · APP_VER ${versions.join(', ')}',
          version: entry['patch_version']?.toString() ?? '',
          exclusiveGroup: entry['group']?.toString() ?? '',
        ),
      );
    }
    return items;
  }

  Future<File> _stateFile() async =>
      File(path.join((await _dataDirectory()).path, 'NeoStationUnifiedCheats', 'state.json'));

  Future<File> _publishedFile(String serial) async =>
      File(path.join((await _dataDirectory()).path, 'patches', '${serial}_patch.yml'));

  /// The bridge's staging document; refuses anything it would not accept.
  Future<Map<String, dynamic>> _readNative() async {
    final file = await _stateFile();
    if (!await file.exists()) {
      return {'schema_version': 1, 'pending': false, 'programs': <dynamic>[]};
    }
    final decoded = jsonDecode(await file.readAsString());
    if (decoded is! Map ||
        decoded['schema_version'] != 1 ||
        decoded['programs'] is! List) {
      throw const EnhancementException('rpcs3_state_unreadable');
    }
    return Map<String, dynamic>.from(decoded);
  }

  Future<void> _writeNative(Map<String, dynamic> document) async {
    final programs = document['programs'] as List;
    document['pending'] = programs.any((record) => record is Map && record['pending'] == true);
    await EnhancementFiles.writeText(await _stateFile(), jsonEncode(document));
  }

  static bool _ours(dynamic record) => record is Map && record['source'] == sourceTag;

  @override
  Future<bool> sync(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
  ) async {
    final Map<String, dynamic> native;
    try {
      native = await _readNative();
    } on Object {
      return false;
    }
    final staged = [
      for (final program in native['programs'] as List)
        if (_ours(program) && program['serial'] == identity.key && program['version'] == identity.version)
          program as Map,
    ];
    final active = {
      for (final program in staged)
        if (program['enabled'] == true) program['entry']?.toString() ?? '',
    }..remove('');
    final installed = staged.isNotEmpty;
    final changed = installed != state.installed ||
        active.length != state.active.length ||
        !active.containsAll(state.active);
    state
      ..installed = installed
      ..active.clear()
      ..active.addAll(active);
    return changed;
  }

  @override
  Future<void> apply(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
    Set<String> active,
  ) async {
    final version = identity.version;
    if (version == null) throw const EnhancementException('version_unknown');
    final native = await _readNative();
    final programs = (native['programs'] as List).toList();
    programs.removeWhere((program) => _ours(program) && program['serial'] == identity.key);
    final occupied = <String>{
      for (final program in programs)
        if (program is Map && program['serial'] == identity.key && program['version'] == version)
          program['name']?.toString() ?? '',
    };
    for (final entry in _entries(record)) {
      final id = entry['id']?.toString() ?? '';
      final name = entry['name']?.toString() ?? '';
      if (id.isEmpty || name.isEmpty) continue;
      var shown = name;
      if (occupied.contains(shown)) shown = '$name · RewindBox';
      for (final target in targetsFor(entry, version)) {
        final hash = target['hash'] as String;
        final title = target['title'] as String;
        final patch = <String, dynamic>{
          'Games': {
            title: {
              identity.key: [version],
            },
          },
          'Author': entry['author']?.toString() ?? '',
          'Notes': entry['notes']?.toString() ?? '',
          'Patch': target['patch'],
        };
        final group = entry['group']?.toString() ?? '';
        if (group.isNotEmpty) patch['Group'] = group;
        programs.add({
          'id': 'rewindbox:$id:${hash.substring(4, 16).toLowerCase()}',
          'name': shown,
          'source_name': name,
          'serial': identity.key,
          'version': version,
          'hash': hash,
          'title': title,
          'description': '$descriptionPrefix$id/${hash.substring(4, 16).toLowerCase()}/$name',
          'patch': patch,
          'enabled': active.contains(id),
          'pending': true,
          'source': sourceTag,
          'entry': id,
        });
      }
    }
    // Every record of the title is republished from the staging file.
    for (final program in programs) {
      if (program is Map && program['serial'] == identity.key) program['pending'] = true;
    }
    native['programs'] = programs;
    await _withdrawPublished(identity.key, programs);
    await _writeNative(native);
    state
      ..installed = true
      ..data['serial'] = identity.key;
  }

  /// Removes RewindBox entries from the published `<SERIAL>_patch.yml`.
  ///
  /// The bridge refuses to republish a title whose file holds an entry
  /// without an identical staged record (managedTitleFile). Its own entries
  /// stay byte-for-byte; ours are published again from the pending records.
  Future<void> _withdrawPublished(String serial, List<dynamic> programs) async {
    final file = await _publishedFile(serial);
    if (!await file.exists()) return;
    final Object? decoded;
    try {
      decoded = jsonDecode(await file.readAsString());
    } on FormatException {
      return; // Not a bridge-published file: the bridge already reports it.
    }
    if (decoded is! Map) return;
    final document = Map<String, dynamic>.from(decoded);
    var changed = false;
    for (final hash in document.keys.where((key) => key != 'Version').toList()) {
      final patches = document[hash];
      if (patches is! Map) continue;
      final kept = Map<String, dynamic>.from(patches)
        ..removeWhere((description, _) => description.startsWith(descriptionPrefix));
      if (kept.length != patches.length) {
        changed = true;
        if (kept.isEmpty) {
          document.remove(hash);
        } else {
          document[hash] = kept;
        }
      }
    }
    if (!changed) return;
    final hasNativeRecords = programs.any(
      (program) => program is Map && program['serial'] == serial && !_ours(program),
    );
    if (document.keys.every((key) => key == 'Version') && !hasNativeRecords) {
      await file.delete();
    } else {
      await EnhancementFiles.writeText(file, jsonEncode(document));
    }
  }

  @override
  Future<void> remove(EnhancementGameState state) async {
    final serial = state.key;
    final native = await _readNative();
    final programs = (native['programs'] as List).toList()
      ..removeWhere((program) => _ours(program) && program['serial'] == serial);
    for (final program in programs) {
      if (program is Map && program['serial'] == serial) program['pending'] = true;
    }
    native['programs'] = programs;
    await _withdrawPublished(serial, programs);
    await _writeNative(native);
    state
      ..installed = false
      ..active.clear()
      ..data.clear();
  }
}
