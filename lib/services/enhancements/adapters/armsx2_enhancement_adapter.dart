import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as path;

import '../../../models/game_model.dart';
import '../../armsx2_internal_service.dart';
import '../enhancement_adapter.dart';
import '../enhancement_models.dart';
import '../enhancement_store.dart';
import '../ini_document.dart';
import 'ps2_disc_identity.dart';

/// PCSX2 patches (widescreen, 60 FPS, no-interlacing...) for ARMSX2.
///
/// Two kinds of entries, both enabled by name in the per-game
/// `gamesettings/<SERIAL>_<CRC>.ini`, the file ARMSX2's in-game Patches and
/// Cheats pages write:
///
/// * `patch`: a group of the patches.zip ARMSX2 ships. Nothing is written but
///   `[Patches] Enable = <name>`. PCSX2 reads the zip only while `patches/`
///   holds no file for the game, so RewindBox never writes there.
/// * `cheat`: a licensed group the zip lacks. The catalogue's cheat file goes
///   to `cheats/<SERIAL>_<CRC>_rewindbox.pnach` while one is on, enabled by
///   `[Cheats] Enable = <name>` and the per-game `[EmuCore] EnableCheats`.
///
/// The CRC is the boot ELF's, so a patch for another disc revision never
/// matches.
class Armsx2EnhancementAdapter extends EnhancementAdapter {
  Armsx2EnhancementAdapter({
    Future<Directory> Function()? dataDirectory,
    Future<Ps2DiscIdentity> Function(String imagePath)? readIdentity,
  }) : _dataDirectory = dataDirectory ?? Armsx2InternalService.rootDirectory,
       _readIdentity = readIdentity ?? Ps2DiscIdentity.read;

  static const patches = 'Patches';
  static const cheats = 'Cheats';

  final Future<Directory> Function() _dataDirectory;
  final Future<Ps2DiscIdentity> Function(String imagePath) _readIdentity;
  static final Map<String, Ps2DiscIdentity> _identityCache = {};

  @override
  EnhancementEngine get engine => EnhancementEngine.armsx2;

  @override
  bool handles(String systemFolder) => systemFolder.toLowerCase() == 'ps2';

  @override
  Future<EnhancementGameIdentity> identify(GameModel game, String systemFolder) async {
    final title = game.titleName ?? game.name;
    final romPath = game.romPath;
    if (romPath == null || !romPath.startsWith('/') || !await File(romPath).exists()) {
      return EnhancementGameIdentity.unavailable(engine, EnhancementProblem.identityUnavailable, title: title);
    }
    final stat = await File(romPath).stat();
    final cacheKey = '$romPath|${stat.size}|${stat.modified.millisecondsSinceEpoch}';
    final identity = _identityCache[cacheKey] ??= await _readIdentity(romPath);
    if (!identity.known) {
      return EnhancementGameIdentity.unavailable(
        engine,
        identity.problem == Ps2DiscIdentity.unsupportedFormat
            ? EnhancementProblem.imageFormat
            : EnhancementProblem.identityUnavailable,
        title: title,
      );
    }
    return EnhancementGameIdentity(engine: engine, key: identity.serial!, crc: identity.crc, title: title);
  }

  List<Map<String, dynamic>> _entries(Map<String, dynamic> record) => [
    for (final entry in (record['entries'] as List? ?? const []))
      if (entry is Map) Map<String, dynamic>.from(entry),
  ];

  @override
  List<EnhancementItem> items(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState? state,
  ) {
    final entries = _entries(record);
    final ownCrc = entries.any((entry) => entry['crc'] == identity.crc);
    final shadowed = state?.data['zipShadowed'] == true;
    final items = <EnhancementItem>[];
    for (final entry in entries) {
      final id = entry['id']?.toString() ?? '';
      final name = entry['name']?.toString() ?? '';
      final crc = entry['crc']?.toString() ?? '';
      final category = EnhancementCategory.parse(entry['cat']?.toString());
      if (id.isEmpty || name.isEmpty || category == null) continue;
      // Another revision's patches are only listed when this one has none,
      // so the player sees why nothing applies.
      if (crc != identity.crc && ownCrc) continue;
      final cheat = entry['kind'] == 'cheat';
      final problem = crc != identity.crc
          ? EnhancementProblem.revisionMismatch
          : !cheat && shadowed
          ? EnhancementProblem
                .userFilePresent // the engine skips its patches.zip
          : EnhancementProblem.none;
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          status: problem != EnhancementProblem.none
              ? EnhancementStatus.incompatible
              : state?.active.contains(id) == true
              ? EnhancementStatus.active
              : cheat
              ? EnhancementStatus
                    .available // written to cheats/ when on
              : EnhancementStatus.installed, // the body ships with the engine
          problem: problem,
          description: entry['description']?.toString() ?? '',
          author: entry['author']?.toString() ?? '',
          compatibility: '${identity.key} · CRC $crc',
          exclusiveGroup: entry['group']?.toString() ?? '',
          payload: {'crc': crc, 'kind': cheat ? cheats : patches},
        ),
      );
    }
    return items;
  }

  Future<Directory> _folder(String name) async => Directory(path.join((await _dataDirectory()).path, name));

  Future<File> _cheatFile(String serial, String crc) async =>
      File(path.join((await _folder('cheats')).path, '${serial}_${crc}_rewindbox.pnach'));

  Future<File> _settingsFile(String serial, String crc) async =>
      File(path.join((await _folder('gamesettings')).path, '${serial}_$crc.ini'));

  /// Whether `patches/` holds a file PCSX2 prefers to patches.zip for this
  /// game (`<SERIAL>_<CRC>*.pnach` or `<CRC>*.pnach`), other than one
  /// RewindBox wrote before and removes on its next write.
  Future<bool> _zipShadowed(String serial, String crc, EnhancementGameState state) async {
    final directory = await _folder('patches');
    if (!await directory.exists()) return false;
    final pattern = RegExp('^(${RegExp.escape(serial)}_)?${RegExp.escape(crc)}.*\\.pnach\$', caseSensitive: false);
    await for (final entity in directory.list(followLinks: false)) {
      if (entity is! File || !pattern.hasMatch(path.basename(entity.path))) continue;
      final owned = state.files[entity.path];
      if (owned == null || await EnhancementFiles.digestOf(entity) != owned) return true;
    }
    return false;
  }

  Set<String> _names(Map<String, dynamic> record, String crc, String kind, bool Function(String id) test) => {
    for (final entry in _entries(record))
      if (entry['crc'] == crc && (entry['kind'] == 'cheat') == (kind == cheats) && test(entry['id'].toString()))
        entry['name'].toString(),
  };

  @override
  Future<bool> sync(EnhancementGameIdentity identity, Map<String, dynamic> record, EnhancementGameState state) async {
    final crc = identity.crc;
    if (crc == null) return false;
    final ini = IniDocument.parse(await EnhancementFiles.readText(await _settingsFile(identity.key, crc)));
    final disabled = ini.values(patches, 'Disable').toSet();
    final enabledPatches = ini.values(patches, 'Enable').toSet().difference(disabled);
    final enabledCheats = ini.values(cheats, 'Enable').toSet();
    final cheatFile = await _cheatFile(identity.key, crc);
    final owned = state.files[cheatFile.path];
    final cheatsInstalled = owned != null && await EnhancementFiles.digestOf(cheatFile) == owned;
    final active = {
      for (final entry in _entries(record))
        if (entry['crc'] == crc &&
            (entry['kind'] == 'cheat'
                ? cheatsInstalled && enabledCheats.contains(entry['name'])
                : enabledPatches.contains(entry['name'])))
          entry['id'].toString(),
    };
    state.data['zipShadowed'] = await _zipShadowed(identity.key, crc, state);
    final changed = active.length != state.active.length || !active.containsAll(state.active);
    state
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
    final crc = identity.crc;
    if (crc == null) throw const EnhancementException('not_in_catalogue');
    final wantedPatches = _names(record, crc, patches, active.contains);
    final wantedCheats = _names(record, crc, cheats, active.contains);

    // 1. The cheat file, present only while one of its groups is on, never
    //    over a file of the player's. Files of an earlier layout are removed.
    final cheatFile = await _cheatFile(identity.key, crc);
    for (final entry in state.files.entries.toList()) {
      if (entry.key == cheatFile.path) continue;
      await EnhancementFiles.deleteIfOwned(File(entry.key), entry.value);
      state.files.remove(entry.key);
    }
    if (wantedCheats.isNotEmpty) {
      final files = record['files'];
      final payload = files is Map ? files[crc] : null;
      if (payload is! Map || payload['text'] is! String) throw const EnhancementException('not_in_catalogue');
      final text = payload['text'] as String;
      if (EnhancementFiles.digest(utf8.encode(text)) != payload['sha256']) {
        throw const EnhancementException('payload_integrity');
      }
      final existing = await EnhancementFiles.digestOf(cheatFile);
      if (existing != null && existing != state.files[cheatFile.path] && existing != payload['sha256']) {
        throw EnhancementException('user_file_present', cheatFile.path);
      }
      state.files[cheatFile.path] = await EnhancementFiles.writeText(cheatFile, text);
    } else if (state.files[cheatFile.path] case final owned?) {
      await EnhancementFiles.deleteIfOwned(cheatFile, owned);
      state.files.remove(cheatFile.path);
    }

    // 2. Enable lines in the per-game settings, recording only ours.
    final settings = await _settingsFile(identity.key, crc);
    final existed = await settings.exists();
    final ini = IniDocument.parse(await EnhancementFiles.readText(settings));
    state.data['enabled'] = _enable(ini, patches, state.data['enabled'], wantedPatches);
    state.data['cheats'] = _enable(ini, cheats, state.data['cheats'], wantedCheats);
    // A patch the player turned off in-game is lifted while RewindBox turns it on.
    final lifted = {for (final name in (state.data['liftedDisabled'] as List? ?? const [])) name.toString()};
    for (final name in lifted.difference(wantedPatches)) {
      ini.addLine(patches, 'Disable = $name');
    }
    lifted.removeWhere((name) => !wantedPatches.contains(name));
    for (final name in wantedPatches) {
      if (ini.removeLine(patches, 'Disable = $name') > 0) lifted.add(name);
    }
    state.data['liftedDisabled'] = lifted.toList()..sort();
    _cheatSwitch(ini, state, wantedCheats.isNotEmpty);
    ini.dropEmptySections([patches, cheats, 'EmuCore']);
    if (!existed) state.data['settingsCreated'] = true;
    if (ini.isBlank && state.data['settingsCreated'] == true) {
      if (await settings.exists()) await settings.delete();
    } else {
      await EnhancementFiles.writeText(settings, ini.toString());
    }
    state
      ..installed = true
      ..data['crc'] = crc;
  }

  /// Makes exactly [wanted] of RewindBox's `Enable` lines present in
  /// [section]; a line the player wrote stays theirs. Returns ours.
  List<String> _enable(IniDocument ini, String section, Object? recorded, Set<String> wanted) {
    final ours = {for (final name in (recorded as List? ?? const [])) name.toString()};
    for (final name in ours.difference(wanted)) {
      ini.removeLine(section, 'Enable = $name');
    }
    ours.removeWhere((name) => !wanted.contains(name));
    final present = ini.values(section, 'Enable').toSet();
    for (final name in wanted) {
      if (!present.contains(name)) {
        ini.addLine(section, 'Enable = $name');
        ours.add(name);
      }
    }
    return ours.toList()..sort();
  }

  /// The per-game cheat switch ARMSX2's Cheats page sets: on while one of
  /// RewindBox's cheats is, then back to the player's previous value.
  void _cheatSwitch(IniDocument ini, EnhancementGameState state, bool on) {
    final recorded = state.data['cheatSwitch'];
    if (on && recorded is! Map) {
      final previous = ini.values('EmuCore', 'EnableCheats');
      state.data['cheatSwitch'] = {'previous': previous.isEmpty ? null : previous.first};
      ini.setValue('EmuCore', 'EnableCheats', 'true');
    } else if (!on && recorded is Map) {
      final previous = recorded['previous'];
      if (previous == null) {
        ini.removeKey('EmuCore', 'EnableCheats');
      } else {
        ini.setValue('EmuCore', 'EnableCheats', previous.toString());
      }
      state.data.remove('cheatSwitch');
    }
  }

  @override
  Future<void> remove(EnhancementGameState state) async {
    final crc = state.data['crc']?.toString();
    if (crc != null) {
      final settings = await _settingsFile(state.key, crc);
      if (await settings.exists()) {
        final ini = IniDocument.parse(await settings.readAsString());
        _enable(ini, patches, state.data['enabled'], const {});
        _enable(ini, cheats, state.data['cheats'], const {});
        for (final name in (state.data['liftedDisabled'] as List? ?? const [])) {
          ini.addLine(patches, 'Disable = $name');
        }
        _cheatSwitch(ini, state, false);
        ini.dropEmptySections([patches, cheats, 'EmuCore']);
        if (ini.isBlank && state.data['settingsCreated'] == true) {
          await settings.delete();
        } else {
          await EnhancementFiles.writeText(settings, ini.toString());
        }
      }
    }
    for (final entry in state.files.entries.toList()) {
      await EnhancementFiles.deleteIfOwned(File(entry.key), entry.value);
      state.files.remove(entry.key);
    }
    state
      ..installed = false
      ..active.clear()
      ..data.clear();
  }
}
