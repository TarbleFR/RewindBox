import 'dart:io';

import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;

import '../../../models/game_model.dart';
import '../../dolphin_internal_v2_service.dart';
import '../../logger_service.dart';
import '../enhancement_adapter.dart';
import '../enhancement_catalog.dart';
import '../enhancement_models.dart';
import '../enhancement_store.dart';
import '../ini_document.dart';

/// Widescreen, 60 FPS and graphics codes of Dolphin's own Sys/GameSettings.
///
/// The code bodies already ship inside the engine (dolphin-ios at the
/// catalogue's pinned revision). Dolphin merges the user's
/// `User/GameSettings/<GAMEID>.ini` and `<GAMEID>r<rev>.ini` over them and
/// applies a code when its `$name` is in `[<Section>_Enabled]` and in no
/// `[<Section>_Disabled]`. RewindBox writes only those name lines in
/// `<GAMEID>.ini`; the in-game cheat menu keeps its `<GAMEID>r<rev>.ini`.
class DolphinEnhancementAdapter extends EnhancementAdapter {
  DolphinEnhancementAdapter({
    Future<Directory> Function()? userDirectory,
    Future<Map<String, dynamic>?> Function(String gamePath, String system)? nativeIdentity,
  }) : _userDirectory = userDirectory ?? _defaultUserDirectory,
       _nativeIdentity = nativeIdentity ?? _saveIdentity;

  static const _channel = MethodChannel('neostation/dolphin_internal');
  static const sections = {'onframe': 'OnFrame', 'gecko': 'Gecko', 'ar': 'ActionReplay'};

  final Future<Directory> Function() _userDirectory;
  final Future<Map<String, dynamic>?> Function(String gamePath, String system) _nativeIdentity;
  final _log = LoggerService.instance;

  static final _gameId = RegExp(r'^[A-Z0-9]{6}$');

  static Future<Directory> _defaultUserDirectory() async =>
      Directory(path.join((await DolphinInternalV2Service.rootDirectory()).path, 'User'));

  static Future<Map<String, dynamic>?> _saveIdentity(String gamePath, String system) =>
      _channel.invokeMapMethod<String, dynamic>('saveIdentity', {
        'gamePath': gamePath,
        'system': system,
      });

  @override
  EnhancementEngine get engine => EnhancementEngine.dolphin;

  @override
  bool handles(String systemFolder) => DolphinInternalV2Service.isDolphinSystem(systemFolder);

  @override
  Future<EnhancementGameIdentity> identify(GameModel game, String systemFolder) async {
    final title = game.titleName ?? game.name;
    final romPath = game.romPath;
    if (romPath == null || !romPath.startsWith('/')) {
      return EnhancementGameIdentity.unavailable(
        engine,
        EnhancementProblem.identityUnavailable,
        title: title,
      );
    }
    String? gameId;
    try {
      final identity = await _nativeIdentity(romPath, systemFolder.toLowerCase());
      gameId = identity?['gameId']?.toString().toUpperCase();
    } on PlatformException catch (error) {
      _log.w('Enhancements: Dolphin identity unavailable: ${error.message}');
    } on MissingPluginException {
      gameId = null;
    }
    if (gameId == null || !_gameId.hasMatch(gameId)) {
      return EnhancementGameIdentity.unavailable(
        engine,
        EnhancementProblem.identityUnavailable,
        title: title,
      );
    }
    return EnhancementGameIdentity(
      engine: engine,
      key: gameId,
      title: title,
      revision: await discRevision(romPath, gameId),
    );
  }

  /// The disc revision byte of the image header when the container keeps a
  /// plain copy of it; null for compressed layouts (GCZ) and unknown files.
  static Future<int?> discRevision(String imagePath, String gameId) async {
    final extension = imagePath.split('.').last.toLowerCase();
    final offset = switch (extension) {
      'iso' || 'gcm' => 0,
      'ciso' => 0x8000,
      'wbfs' => 0x200,
      'rvz' || 'wia' => 0x58,
      _ => null,
    };
    if (offset == null) return null;
    RandomAccessFile? file;
    try {
      file = await File(imagePath).open();
      await file.setPosition(offset);
      final header = await file.read(8);
      if (header.length != 8 || String.fromCharCodes(header.sublist(0, 6)) != gameId) {
        return null;
      }
      return header[7];
    } on FileSystemException {
      return null;
    } finally {
      await file?.close();
    }
  }

  /// Catalogue files Dolphin merges for a game, broadest first.
  static List<String> stems(EnhancementGameIdentity identity) => [
    identity.key.substring(0, 1),
    identity.key.substring(0, 3),
    identity.key,
    if (identity.revision != null) '${identity.key}r${identity.revision}',
  ];

  @override
  Future<bool> listed(EnhancementCatalog catalog, EnhancementGameIdentity identity) async {
    final index = await catalog.index();
    return stems(identity).any((stem) => index.contains(engine, stem));
  }

  @override
  Future<Map<String, dynamic>?> loadRecord(
    EnhancementCatalog catalog,
    EnhancementGameIdentity identity, {
    bool download = true,
    EnhancementProgress? onProgress,
  }) async {
    final merged = <String, Map<String, dynamic>>{};
    final defaults = <String, Set<String>>{};
    var title = '';
    var found = false;
    for (final stem in stems(identity)) {
      final record = await catalog.record(engine, stem, download: download, onProgress: onProgress);
      if (record == null) continue;
      found = true;
      if ((record['title']?.toString() ?? '').isNotEmpty) title = record['title'].toString();
      final recordDefaults = record['defaults'];
      if (recordDefaults is Map) {
        for (final entry in recordDefaults.entries) {
          defaults.putIfAbsent(entry.key.toString(), () => <String>{}).addAll([
            for (final name in (entry.value as List? ?? const [])) name.toString(),
          ]);
        }
      }
      for (final entry in (record['entries'] as List? ?? const [])) {
        if (entry is Map) {
          final value = Map<String, dynamic>.from(entry);
          merged['${value['kind']}\u001f${value['name']}'] = value; // narrower file wins
        }
      }
    }
    if (!found) return null;
    final entries = [
      for (final entry in merged.values)
        if (!(defaults[entry['kind']]?.contains(entry['name']) ?? false)) entry,
    ];
    return {'title': title, 'entries': entries};
  }

  List<Map<String, dynamic>> _entries(Map<String, dynamic> record) => [
    for (final entry in (record['entries'] as List? ?? const []))
      if (entry is Map && sections.containsKey(entry['kind'])) Map<String, dynamic>.from(entry),
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
      final status = state?.active.contains(id) == true
          ? EnhancementStatus.active
          : EnhancementStatus.installed; // the body ships with the engine
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          status: status,
          description: entry['label']?.toString() ?? '',
          compatibility:
              '${identity.key}${identity.revision == null ? '' : ' rev ${identity.revision}'} · '
              '${sections[entry['kind']]}',
          payload: {'kind': entry['kind']},
        ),
      );
    }
    return items;
  }

  Future<File> _localFile(String gameId) async =>
      File(path.join((await _userDirectory()).path, 'GameSettings', '$gameId.ini'));

  Future<List<File>> _revisionFiles(String gameId) async {
    final directory = Directory(path.join((await _userDirectory()).path, 'GameSettings'));
    if (!await directory.exists()) return const [];
    final pattern = RegExp('^${RegExp.escape(gameId)}r[0-9]+\\.ini\$');
    return [
      await for (final entity in directory.list(followLinks: false))
        if (entity is File && pattern.hasMatch(path.basename(entity.path))) entity,
    ];
  }

  @override
  Future<bool> sync(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
  ) async {
    final documents = [
      IniDocument.parse(await EnhancementFiles.readText(await _localFile(identity.key))),
      for (final file in await _revisionFiles(identity.key))
        IniDocument.parse(await file.readAsString()),
    ];
    bool listedIn(String section, String name) =>
        documents.any((ini) => ini.lines(section).contains('\$$name'));
    final active = {
      for (final entry in _entries(record))
        if (listedIn('${sections[entry['kind']]}_Enabled', entry['name'].toString()) &&
            !listedIn('${sections[entry['kind']]}_Disabled', entry['name'].toString()))
          entry['id'].toString(),
    };
    final changed = active.length != state.active.length || !active.containsAll(state.active);
    state
      ..installed = true
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
    final local = await _localFile(identity.key);
    final existed = await local.exists();
    final ini = IniDocument.parse(await EnhancementFiles.readText(local));
    final ours = {for (final line in (state.data['enabled'] as List? ?? const [])) line.toString()};
    final removed = [
      for (final item in (state.data['removedDisabled'] as List? ?? const []))
        if (item is Map) Map<String, dynamic>.from(item),
    ];
    final wanted = <String, (String, String)>{};
    for (final entry in _entries(record)) {
      if (active.contains(entry['id'])) {
        final section = sections[entry['kind']]!;
        wanted['$section\u001f${entry['name']}'] = (section, entry['name'].toString());
      }
    }
    for (final key in ours.difference(wanted.keys.toSet())) {
      final parts = key.split('\u001f');
      ini.removeLine('${parts[0]}_Enabled', '\$${parts[1]}');
    }
    ours.removeWhere((key) => !wanted.containsKey(key));
    final revisionDocuments = <File, IniDocument>{
      for (final file in await _revisionFiles(identity.key))
        file: IniDocument.parse(await file.readAsString()),
    };
    var needsCheats = false;
    for (final entry in wanted.entries) {
      final (section, name) = entry.value;
      if (section != 'OnFrame') needsCheats = true;
      if (ini.addLine('${section}_Enabled', '\$$name')) ours.add(entry.key);
      if (ini.removeLine('${section}_Disabled', '\$$name') > 0) {
        removed.add({'file': local.path, 'section': '${section}_Disabled', 'line': '\$$name'});
      }
      for (final revision in revisionDocuments.entries) {
        if (revision.value.removeLine('${section}_Disabled', '\$$name') > 0) {
          removed.add({'file': revision.key.path, 'section': '${section}_Disabled', 'line': '\$$name'});
        }
      }
    }
    ini.dropEmptySections([for (final section in sections.values) '${section}_Enabled']);
    if (!existed) state.data['settingsCreated'] = true;
    if (ini.isBlank && state.data['settingsCreated'] == true) {
      if (await local.exists()) await local.delete();
    } else {
      await EnhancementFiles.writeText(local, ini.toString());
    }
    for (final revision in revisionDocuments.entries) {
      await EnhancementFiles.writeText(revision.key, revision.value.toString());
    }
    if (needsCheats) await _enableCheatEngine(state);
    state
      ..installed = true
      ..data['enabled'] = (ours.toList()..sort())
      ..data['removedDisabled'] = removed;
  }

  /// Gecko and Action Replay codes need Dolphin's cheat switch, which the
  /// in-game menu also turns on by itself. It stays on after a revert: with
  /// no code enabled it has no effect.
  Future<void> _enableCheatEngine(EnhancementGameState state) async {
    final file = File(path.join((await _userDirectory()).path, 'Config', 'Dolphin.ini'));
    final ini = IniDocument.parse(await EnhancementFiles.readText(file));
    final current = ini.values('Core', 'EnableCheats');
    if (current.isNotEmpty && current.first.toLowerCase() == 'true') return;
    ini.setValue('Core', 'EnableCheats', 'True');
    await EnhancementFiles.writeText(file, ini.toString());
    state.data['cheatSwitchTurnedOn'] = true;
  }

  @override
  Future<void> remove(EnhancementGameState state) async {
    final local = await _localFile(state.key);
    if (await local.exists()) {
      final ini = IniDocument.parse(await local.readAsString());
      for (final key in (state.data['enabled'] as List? ?? const [])) {
        final parts = key.toString().split('\u001f');
        if (parts.length == 2) ini.removeLine('${parts[0]}_Enabled', '\$${parts[1]}');
      }
      ini.dropEmptySections([for (final section in sections.values) '${section}_Enabled']);
      if (ini.isBlank && state.data['settingsCreated'] == true) {
        await local.delete();
      } else {
        await EnhancementFiles.writeText(local, ini.toString());
      }
    }
    // Disabled lines RewindBox lifted come back as they were.
    for (final item in (state.data['removedDisabled'] as List? ?? const [])) {
      if (item is! Map) continue;
      final file = File(item['file'].toString());
      final ini = IniDocument.parse(await EnhancementFiles.readText(file));
      ini.addLine(item['section'].toString(), item['line'].toString());
      await EnhancementFiles.writeText(file, ini.toString());
    }
    state
      ..installed = false
      ..active.clear()
      ..data.clear();
  }
}

