import 'dart:convert';
import 'dart:io';
import 'dart:isolate';

import 'package:archive/archive_io.dart';
import 'package:path/path.dart' as p;

import 'enhancements/adapters/melonx_enhancement_adapter.dart';

/// One mod of a Switch game, as the engine's ModLoader sees it.
class MelonxMod {
  const MelonxMod({
    required this.name,
    required this.enabled,
    required this.romfs,
    required this.exefs,
    required this.cheats,
    required this.path,
  });

  final String name;
  final bool enabled;
  final bool romfs; // replaces game files
  final bool exefs; // patches game code
  final bool cheats; // carries its own cheats
  final String path;
}

/// Why an import or a change was refused; [code] is a key of MelonxModsLocale.
class MelonxModException implements Exception {
  const MelonxModException(this.code, [this.detail = '']);
  final String code;
  final String detail;
  @override
  String toString() => 'MelonxModException($code${detail.isEmpty ? '' : ': $detail'})';
}

/// The game's mods for the embedded engine (Ryujinx's ModLoader, as pinned).
///
/// The engine reads `<MeloNX root>/mods/contents/<title id>/<mod>/` (title id
/// matched without case; a mod may sit in sub-folders) and loads every `romfs`
/// and `exefs` folder it finds there when the game starts; a `cheats` folder is
/// the Cheats & Enhancements screen's business. Its own "disabled" list
/// (`games/<title id>/mods.json`) names mods by absolute path, which changes when
/// iOS moves the app's container, so RewindBox turns a mod off by moving its
/// folder to `mods/rewindbox-disabled/<title id>/<mod>`, where the engine never
/// looks, and back to turn it on (removing any mods.json entry that would keep
/// it off). Mods that only carry cheats are left to the Cheats screen and not
/// listed. RewindBox's own folder ([ownFolder]) is never a mod here.
abstract final class MelonxModsService {
  static const disabledFolder = 'rewindbox-disabled';
  static const maxFiles = 200000;
  static final _titleId = RegExp(r'^[0-9a-fA-F]{16}$');
  static final _kinds = {'romfs', 'exefs', 'cheats'};

  /// Whether [name] is RewindBox's own folder of a game (`RewindBox`), where
  /// the Cheats & Enhancements page writes its cheats and exefs patches and
  /// records each file. It is not listed, turned off or deleted here, and no
  /// import takes its name: turning it off moved RewindBox's files away while
  /// the page still said Active, and an FPS mod lost its engine refresh (the
  /// page now reclaims such a copy, see [reclaimOwnFolder]).
  static bool ownFolder(String name) => name.toLowerCase() == MelonxEnhancementAdapter.modName.toLowerCase();

  /// A mod's folder name: printable, no path separator, not '.' or '..'.
  static bool validName(String name) =>
      name.isNotEmpty &&
      name.length <= 64 &&
      name.trim() == name &&
      name != '.' &&
      name != '..' &&
      !name.startsWith('.') &&
      !RegExp(r'[/\\:*?"<>|\x00-\x1f]').hasMatch(name);

  static String _id(String titleId) {
    if (!_titleId.hasMatch(titleId)) throw const MelonxModException('invalidGame');
    return titleId.toLowerCase();
  }

  /// The engine's folder of the game: an existing one in any case, else lowercase.
  static Directory contents(Directory root, String titleId) {
    final id = _id(titleId);
    final parent = Directory(p.join(root.path, 'mods', 'contents'));
    if (parent.existsSync()) {
      for (final entry in parent.listSync(followLinks: false)) {
        if (entry is Directory && p.basename(entry.path).toLowerCase() == id) return entry;
      }
    }
    return Directory(p.join(parent.path, id));
  }

  static Directory disabled(Directory root, String titleId) =>
      Directory(p.join(root.path, 'mods', disabledFolder, _id(titleId)));

  static File _metadata(Directory root, String titleId) =>
      File(p.join(root.path, 'games', _id(titleId), 'mods.json'));

  /// The game's mods, enabled first, each list by name.
  static Future<List<MelonxMod>> list(Directory root, String titleId) async {
    final offInJson = await _jsonDisabled(root, titleId);
    final mods = <MelonxMod>[];
    for (final (folder, enabled) in [(contents(root, titleId), true), (disabled(root, titleId), false)]) {
      if (!await folder.exists()) continue;
      final entries = await folder.list(followLinks: false).toList();
      entries.sort((a, b) => p.basename(a.path).toLowerCase().compareTo(p.basename(b.path).toLowerCase()));
      for (final entry in entries) {
        // A copy of RewindBox's folder an older version let the player turn off stays hidden too.
        if (entry is! Directory || p.basename(entry.path).startsWith('.') || ownFolder(p.basename(entry.path))) continue;
        final kinds = _kindsOf(entry);
        if (!kinds.contains('romfs') && !kinds.contains('exefs')) continue;
        mods.add(MelonxMod(
          name: p.basename(entry.path),
          enabled: enabled && !offInJson.contains(p.normalize(entry.path)),
          romfs: kinds.contains('romfs'),
          exefs: kinds.contains('exefs'),
          cheats: kinds.contains('cheats'),
          path: entry.path,
        ));
      }
    }
    return mods;
  }

  /// The romfs/exefs/cheats folders under [dir], as the engine walks them.
  static Set<String> _kindsOf(Directory dir, [int depth = 0]) {
    final found = <String>{};
    if (depth > 8) return found;
    for (final entry in dir.listSync(followLinks: false)) {
      if (entry is! Directory) continue;
      final name = p.basename(entry.path).toLowerCase();
      if (_kinds.contains(name)) {
        found.add(name);
      } else {
        found.addAll(_kindsOf(entry, depth + 1));
      }
    }
    return found;
  }

  static Future<Set<String>> _jsonDisabled(Directory root, String titleId) async {
    try {
      final file = _metadata(root, titleId);
      if (!await file.exists()) return const {};
      final decoded = jsonDecode(await file.readAsString());
      final list = decoded is Map ? decoded['mods'] : null;
      if (list is! List) return const {};
      return {
        for (final item in list)
          if (item is Map && item['enabled'] == false && item['path'] is String) p.normalize(item['path'] as String),
      };
    } on Object {
      return const {};
    }
  }

  /// Turns a mod on (back into the engine's folder) or off (out of it).
  static Future<void> setEnabled(Directory root, String titleId, String name, bool enabled) async {
    if (!validName(name)) throw const MelonxModException('invalidName');
    if (ownFolder(name)) throw MelonxModException('missing', name);
    final on = Directory(p.join(contents(root, titleId).path, name));
    final off = Directory(p.join(disabled(root, titleId).path, name));
    final from = enabled ? off : on;
    final to = enabled ? on : off;
    if (await from.exists()) {
      if (await to.exists()) throw const MelonxModException('exists');
      await to.parent.create(recursive: true);
      await from.rename(to.path);
    } else if (!await to.exists()) {
      throw const MelonxModException('missing');
    }
    if (enabled) await _clearJsonEntry(root, titleId, on.path);
  }

  /// Removes a mods.json entry that would keep [modPath] off; other entries stay.
  static Future<void> _clearJsonEntry(Directory root, String titleId, String modPath) async {
    final file = _metadata(root, titleId);
    if (!await file.exists()) return;
    try {
      final decoded = jsonDecode(await file.readAsString());
      if (decoded is! Map || decoded['mods'] is! List) return;
      final mods = (decoded['mods'] as List)
          .where((item) => !(item is Map && item['path'] is String && p.normalize(item['path'] as String) == p.normalize(modPath)))
          .toList();
      if (mods.length == (decoded['mods'] as List).length) return;
      final temporary = File('${file.path}.rewindbox-tmp');
      await temporary.writeAsString(const JsonEncoder.withIndent('  ').convert({...decoded, 'mods': mods}), flush: true);
      await temporary.rename(file.path);
    } on Object {
      // An unreadable mods.json is the engine's to report; the folder move stands.
    }
  }

  /// RewindBox's own folder of a game that an older version let the player
  /// turn off here: moved to `rewindbox-disabled/<title id>/RewindBox`, where
  /// the engine never looks, while the Cheats & Enhancements page still said
  /// its codes were on. Moved back to the engine's folder when [restore] (the
  /// page records files in it) and that place is free; deleted otherwise, as
  /// RewindBox's own superseded or untracked copy. Null when there is no such
  /// copy, true when it was moved back.
  static Future<bool?> reclaimOwnFolder(Directory root, String titleId, {required bool restore}) async {
    final parent = disabled(root, titleId);
    if (!await parent.exists()) return null;
    final copies = [
      for (final entry in await parent.list(followLinks: false).toList())
        if (entry is Directory && ownFolder(p.basename(entry.path))) entry,
    ];
    if (copies.isEmpty) return null;
    final live = Directory(p.join(root.path, 'mods', 'contents', _id(titleId), MelonxEnhancementAdapter.modName));
    var moved = false;
    for (final copy in copies) {
      if (restore && !moved && !await live.exists()) {
        await live.parent.create(recursive: true);
        await copy.rename(live.path);
        moved = true;
      } else {
        await copy.delete(recursive: true);
      }
    }
    for (final folder in [parent, parent.parent]) {
      if (await folder.exists() && await folder.list().isEmpty) await folder.delete();
    }
    return moved;
  }

  /// Deletes a mod wherever it is; RewindBox's own folder in the engine's
  /// folder is never deleted (only a copy an older version turned off).
  static Future<void> delete(Directory root, String titleId, String name) async {
    if (!validName(name)) throw const MelonxModException('invalidName');
    for (final base in [if (!ownFolder(name)) contents(root, titleId), disabled(root, titleId)]) {
      final dir = Directory(p.join(base.path, name));
      if (await dir.exists()) await dir.delete(recursive: true);
    }
  }

  /// Imports a mod archive (.zip) for the game and returns the names added.
  ///
  /// Accepted layouts (romfs/exefs/cheats folders, any case): `romfs/…` at the
  /// archive's top (named after the archive), `<mod>/romfs/…`, and the
  /// Atmosphère layout `…/contents/<title id>/[<mod>/]romfs/…`, whose title id
  /// must be this game's (or its update's). Several mods in one archive become
  /// several mods. Files outside those folders (readme, pictures) are skipped.
  /// Absolute or parent paths, an existing name, RewindBox's reserved one,
  /// another game's title id or an archive without romfs/exefs refuse the
  /// whole import; nothing is left behind. Runs in a background isolate (the
  /// files are streamed, not loaded).
  static Future<List<String>> importArchive(Directory root, String titleId, String archivePath) async {
    final id = _id(titleId);
    final target = contents(root, id).path;
    final fallback = p.basenameWithoutExtension(archivePath).trim();
    final result = await Isolate.run(() => _extract(archivePath, target, id, fallback));
    if (result.$1 != null) throw MelonxModException(result.$1!, result.$2);
    return result.$3;
  }

  static (String?, String, List<String>) _extract(String archivePath, String target, String titleId, String fallback) {
    final staging = Directory(p.join(target, '.import-${DateTime.now().microsecondsSinceEpoch}'));
    InputFileStream? input;
    try {
      input = InputFileStream(archivePath);
      final archive = ZipDecoder().decodeStream(input);
      if (archive.length > maxFiles) return ('tooManyFiles', '', const []);
      final plan = <String, List<(ArchiveFile, List<String>)>>{};
      for (final file in archive) {
        if (!file.isFile || file.isSymbolicLink) continue;
        final parts = file.name.replaceAll('\\', '/').split('/').where((part) => part.isNotEmpty).toList();
        if (file.name.startsWith('/') || file.name.startsWith('\\') || parts.any((part) => part == '..' || part == '.')) {
          return ('unsafePath', file.name, const []);
        }
        final marker = parts.indexWhere((part) => _kinds.contains(part.toLowerCase()));
        if (marker < 0 || marker == parts.length - 1) continue; // not a mod file
        final name = _modName(parts.sublist(0, marker), titleId, fallback);
        if (name.$1 != null) return (name.$1, name.$2, const []);
        plan.putIfAbsent(name.$2, () => []).add((file, parts.sublist(marker)));
      }
      if (plan.isEmpty || !plan.values.any((files) => files.any((f) => f.$2.first.toLowerCase() != 'cheats'))) {
        return ('noMod', '', const []);
      }
      for (final name in plan.keys) {
        if (!validName(name)) return ('invalidName', name, const []);
        // RewindBox's own folder name is reserved, whether or not it exists.
        if (ownFolder(name)) return ('reservedName', name, const []);
        if (Directory(p.join(target, name)).existsSync()) return ('exists', name, const []);
      }
      for (final entry in plan.entries) {
        for (final (file, relative) in entry.value) {
          final out = File(p.joinAll([staging.path, entry.key, ...relative]));
          out.parent.createSync(recursive: true);
          final stream = OutputFileStream(out.path);
          try {
            file.writeContent(stream);
          } finally {
            stream.closeSync();
          }
        }
      }
      for (final name in plan.keys) {
        Directory(p.join(staging.path, name)).renameSync(p.join(target, name));
      }
      return (null, '', plan.keys.toList()..sort());
    } on Object catch (error) {
      return ('invalidArchive', error.runtimeType.toString(), const []);
    } finally {
      input?.closeSync();
      if (staging.existsSync()) staging.deleteSync(recursive: true);
    }
  }

  /// The mod name of a path prefix before its romfs/exefs/cheats folder.
  static (String?, String) _modName(List<String> prefix, String titleId, String fallback) {
    var rest = prefix;
    final contents = prefix.lastIndexWhere((part) => part.toLowerCase() == 'contents');
    if (contents >= 0 && contents + 1 < prefix.length && _titleId.hasMatch(prefix[contents + 1])) {
      final owner = prefix[contents + 1].toLowerCase();
      final base = BigInt.parse(owner, radix: 16) & ~BigInt.from(0x1fff);
      if (base != BigInt.parse(titleId, radix: 16)) return ('wrongGame', owner);
      rest = prefix.sublist(contents + 2);
    }
    if (rest.isEmpty) return (validName(fallback) ? null : 'invalidName', fallback);
    return (null, rest.last);
  }
}
