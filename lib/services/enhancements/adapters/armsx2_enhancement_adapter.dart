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
/// PCSX2 prefers `patches/<SERIAL>_<CRC>.pnach` on disk over the bundled
/// patches.zip, and reads the enabled patch names from the per-game
/// `gamesettings/<SERIAL>_<CRC>.ini` (`[Patches] Enable = <name>`), the same
/// file and keys ARMSX2's in-game Patches page writes. The CRC is the boot
/// ELF's, so a patch for another disc revision never matches.
class Armsx2EnhancementAdapter extends EnhancementAdapter {
  Armsx2EnhancementAdapter({
    Future<Directory> Function()? dataDirectory,
    Future<Ps2DiscIdentity> Function(String imagePath)? readIdentity,
  }) : _dataDirectory = dataDirectory ?? Armsx2InternalService.rootDirectory,
       _readIdentity = readIdentity ?? Ps2DiscIdentity.read;

  static const section = 'Patches';

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
      return EnhancementGameIdentity.unavailable(
        engine,
        EnhancementProblem.identityUnavailable,
        title: title,
      );
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
    return EnhancementGameIdentity(
      engine: engine,
      key: identity.serial!,
      crc: identity.crc,
      title: title,
    );
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
      final compatible = crc == identity.crc;
      items.add(
        EnhancementItem(
          id: id,
          engine: engine,
          category: category,
          name: name,
          sourceId: entry['source']?.toString() ?? '',
          status: compatible
              ? EnhancementAdapter.statusOf(id, state)
              : EnhancementStatus.incompatible,
          problem: compatible ? EnhancementProblem.none : EnhancementProblem.revisionMismatch,
          description: entry['description']?.toString() ?? '',
          author: entry['author']?.toString() ?? '',
          compatibility: '${identity.key} · CRC $crc',
          exclusiveGroup: entry['group']?.toString() ?? '',
          payload: {'crc': crc},
        ),
      );
    }
    return items;
  }

  Future<File> _patchFile(String serial, String crc) async =>
      File(path.join((await _dataDirectory()).path, 'patches', '${serial}_$crc.pnach'));

  Future<File> _settingsFile(String serial, String crc) async =>
      File(path.join((await _dataDirectory()).path, 'gamesettings', '${serial}_$crc.ini'));

  @override
  Future<bool> sync(
    EnhancementGameIdentity identity,
    Map<String, dynamic> record,
    EnhancementGameState state,
  ) async {
    final crc = identity.crc;
    if (crc == null) return false;
    final enabled = IniDocument.parse(
      await EnhancementFiles.readText(await _settingsFile(identity.key, crc)),
    ).values(section, 'Enable').toSet();
    final active = {
      for (final entry in _entries(record))
        if (entry['crc'] == crc && enabled.contains(entry['name'])) entry['id'].toString(),
    };
    final file = await _patchFile(identity.key, crc);
    final owned = state.files[file.path];
    final installed = owned != null && await EnhancementFiles.digestOf(file) == owned;
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
    final crc = identity.crc;
    final files = record['files'];
    final payload = files is Map ? files[crc] : null;
    if (crc == null || payload is! Map || payload['text'] is! String) {
      throw const EnhancementException('not_in_catalogue');
    }
    final text = payload['text'] as String;
    if (EnhancementFiles.digest(utf8.encode(text)) != payload['sha256']) {
      throw const EnhancementException('payload_integrity');
    }

    // 1. The catalogue's pnach, never over a file of the player's.
    final patch = await _patchFile(identity.key, crc);
    final existing = await EnhancementFiles.digestOf(patch);
    if (existing != null && existing != state.files[patch.path] && existing != payload['sha256']) {
      throw EnhancementException('user_file_present', patch.path);
    }
    state.files[patch.path] = await EnhancementFiles.writeText(patch, text);

    // 2. Enable lines in the per-game settings, recording only ours.
    final settings = await _settingsFile(identity.key, crc);
    final existed = await settings.exists();
    final ini = IniDocument.parse(await EnhancementFiles.readText(settings));
    final ours = {for (final name in (state.data['enabled'] as List? ?? const [])) name.toString()};
    final wanted = {
      for (final entry in _entries(record))
        if (entry['crc'] == crc && active.contains(entry['id'])) entry['name'].toString(),
    };
    for (final name in ours.difference(wanted)) {
      ini.removeLine(section, 'Enable = $name');
    }
    final present = ini.values(section, 'Enable').toSet();
    for (final name in wanted) {
      if (!present.contains(name)) {
        ini.addLine(section, 'Enable = $name');
        ours.add(name);
      }
    }
    ours.removeWhere((name) => !wanted.contains(name));
    ini.dropEmptySections([section]);
    if (!existed) state.data['settingsCreated'] = true;
    if (ini.isBlank && state.data['settingsCreated'] == true) {
      if (await settings.exists()) await settings.delete();
    } else {
      await EnhancementFiles.writeText(settings, ini.toString());
    }
    state
      ..installed = true
      ..data['enabled'] = (ours.toList()..sort())
      ..data['crc'] = crc;
  }

  @override
  Future<void> remove(EnhancementGameState state) async {
    final crc = state.data['crc']?.toString();
    if (crc != null) {
      final settings = await _settingsFile(state.key, crc);
      if (await settings.exists()) {
        final ini = IniDocument.parse(await settings.readAsString());
        for (final name in (state.data['enabled'] as List? ?? const [])) {
          ini.removeLine(section, 'Enable = $name');
        }
        ini.dropEmptySections([section]);
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
