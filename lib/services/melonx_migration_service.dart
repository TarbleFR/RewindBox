import 'dart:convert';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'melonx_file_transaction.dart';
import 'melonx_internal_service.dart';
import 'melonx_library_scanner.dart';
import 'melonx_transfer_source.dart';

class MelonxMigrationPlan {
  const MelonxMigrationPlan(
    this.source,
    this.items,
    this.unsupported, [
    this.linkedGames = const [],
  ]);
  final Directory source;
  final List<MelonxTransferItem> items;
  final List<String> unsupported;
  final List<Directory> linkedGames;
  int get bytes => items.fold(0, (n, item) => n + item.bytes);
  bool get restartRequired => items.any(
    (item) =>
        item.relative == 'bis' ||
        item.relative == p.join('system', 'Profiles.json'),
  );
}

class MelonxSaveCandidate {
  const MelonxSaveCandidate(this.folder, this.titleId, [this.profileId]);
  final Directory folder;
  final String? titleId;
  final String? profileId;
}

class MelonxPreparedSave {
  const MelonxPreparedSave(this.item, this.association);
  final MelonxTransferItem item;
  final Map<String, String> association;
}

abstract final class MelonxMigrationService {
  static const settings = {
    'resScale',
    'disableShaderCache',
    'enableAsyncShaderCompilation',
    'vSyncMode',
    'disableVSync',
    'scalingFilter',
    'disablePTC',
    'enableTextureRecompression',
    'enableHostMemoryBudgetTracking',
    'disableDockedMode',
    'disableMacroHLE',
    'ignoreMissingServices',
    'systemTimeZone',
    'systemTimeOffset',
    'audioVolume',
    'maxAnisotropy',
    'aspectRatio',
    'antiAliasing',
    'backendThreading',
    'systemLanguage',
    'systemRegion',
  };
  static Map<String, dynamic> sanitizedSettings(Map<String, dynamic> input) {
    const booleans = {
      'disableShaderCache',
      'enableAsyncShaderCompilation',
      'disableVSync',
      'disablePTC',
      'enableTextureRecompression',
      'enableHostMemoryBudgetTracking',
      'disableDockedMode',
      'disableMacroHLE',
      'ignoreMissingServices',
    };
    const ranges = {
      'vSyncMode': 1,
      'scalingFilter': 3,
      'aspectRatio': 5,
      'antiAliasing': 5,
      'backendThreading': 2,
      'systemLanguage': 19,
      'systemRegion': 6,
    };
    final result = Map<String, dynamic>.from(input);
    for (final entry in input.entries) {
      final key = entry.key, value = entry.value;
      bool valid = true;
      if (booleans.contains(key))
        valid = value is bool;
      else if (ranges.containsKey(key))
        valid = value is int && value >= 0 && value <= ranges[key]!;
      else if (key == 'resScale')
        valid = value is num && value.isFinite && value >= 0.5 && value <= 2;
      else if (key == 'audioVolume')
        valid = value is num && value.isFinite && value >= 0 && value <= 1;
      else if (key == 'maxAnisotropy')
        valid = value is num && value.isFinite && value >= -1 && value <= 16;
      else if (key == 'systemTimeZone')
        valid = value is String && value.isNotEmpty && value.length <= 128;
      else if (key == 'systemTimeOffset')
        valid = value is int;
      if (!valid) result.remove(key);
    }
    return result;
  }

  static Future<Directory> findRoot(Directory selected) async {
    Future<bool> recognized(Directory directory) async =>
        await File(
          p.join(directory.path, 'system', 'Profiles.json'),
        ).exists() ||
        await Directory(p.join(directory.path, 'bis', 'user')).exists() ||
        (await Directory(p.join(directory.path, 'roms')).exists() &&
            await Directory(p.join(directory.path, 'system')).exists());
    if (await recognized(selected)) return selected;
    final matches = <Directory>[];
    await for (final child in selected.list(followLinks: false)) {
      if (child is Directory && await recognized(child)) matches.add(child);
    }
    if (matches.length != 1) throw const FormatException('sourceUnknown');
    return matches.single;
  }

  static Future<MelonxMigrationPlan> analyze(
    Directory selected,
    Directory root,
    MelonxTransferControl control, {
    bool linkGames = false,
    Set<String> registeredGameFolders = const {},
  }) async {
    final source = await findRoot(selected);
    if (p.equals(source.path, root.path) ||
        p.isWithin(source.path, root.path) ||
        p.isWithin(root.path, source.path))
      throw const FormatException('unsafePath');
    final items = <MelonxTransferItem>[];
    final unsupported = <String>[];
    final linkedGames = <Directory>[];
    Future<void> add(FileSystemEntity entity, String relative) async {
      control.check();
      if (entity is Link) throw const FormatException('unsafePath');
      if (MelonxTransferSource.ignored(p.basename(entity.path))) return;
      if (entity is Directory && relative != 'bis') {
        await for (final child in entity.list(followLinks: false)) {
          await add(child, p.join(relative, p.basename(child.path)));
        }
        return;
      }
      if (entity is File &&
          (relative == 'config.json' ||
              relative.startsWith('config${p.separator}'))) {
        if (await entity.length() > 4 * 1024 * 1024)
          throw const FormatException('incompleteTransfer');
        final value = jsonDecode(await entity.readAsString());
        if (value is! Map) throw const FormatException('sourceUnknown');
        final supported = sanitizedSettings(Map<String, dynamic>.from(value));
        for (final key in value.keys.where(
          (key) => !settings.contains(key) || !supported.containsKey(key),
        )) {
          unsupported.add('$relative: $key');
        }
      }
      final destination = MelonxFileTransaction.targetPath(root, relative);
      if (entity is File &&
          await File(destination).exists() &&
          await File(destination).length() == await entity.length() &&
          await MelonxLibraryScanner.fingerprint(File(destination)) ==
              await MelonxLibraryScanner.fingerprint(entity))
        return;
      items.add(
        MelonxTransferItem(
          entity,
          relative,
          await MelonxFileTransaction.size(entity),
          await FileSystemEntity.type(destination, followLinks: false) !=
              FileSystemEntityType.notFound,
        ),
      );
    }

    await for (final entity in source.list(followLinks: false)) {
      control.check();
      final name = p.basename(entity.path);
      if (entity is Directory && name == 'roms') {
        final console = Directory(p.join(entity.path, 'switch'));
        final games = await console.exists() ? console : entity;
        if (linkGames ||
            registeredGameFolders.any(
              (folder) =>
                  p.equals(folder, games.path) ||
                  p.isWithin(folder, games.path),
            ))
          linkedGames.add(games);
        else {
          await add(games, p.join('roms', 'switch'));
        }
      } else if (const {
            'bis',
            'system',
            'games',
            'profiles',
            'mods',
            'sdcard',
            'addons',
            'config',
            'controller_mappings',
            'controller',
          }.contains(name) ||
          name == 'config.json') {
        await add(entity, name);
      } else if (entity is File &&
          MelonxInternalService.gameExtensions.contains(
            p.extension(name).replaceFirst('.', '').toLowerCase(),
          )) {
        await add(entity, p.join('roms', 'switch', name));
      } else if (!MelonxTransferSource.ignored(name)) {
        unsupported.add(name);
      }
    }
    if (linkedGames.isNotEmpty) {
      final gameConfigs = Directory(p.join(source.path, 'games'));
      if (await gameConfigs.exists()) {
        await for (final file in gameConfigs.list(
          recursive: true,
          followLinks: false,
        )) {
          if (file is! File ||
              !{'updates.json', 'dlc.json'}.contains(p.basename(file.path)))
            continue;
          if (await file.length() > 4 * 1024 * 1024)
            throw const FormatException('incompleteTransfer');
          final value = jsonDecode(await file.readAsString());
          final references = p.basename(file.path) == 'updates.json'
              ? [
                  if ((value as Map)['selected']?.toString().isNotEmpty == true)
                    value['selected'],
                ]
              : (value as List).map((e) => e['path']).toList();
          for (final reference in references) {
            final text = reference as String;
            String? relative;
            if (p.isWithin(source.path, text))
              relative = p.relative(text, from: source.path);
            else if (text.contains('/Documents/'))
              relative = text.split('/Documents/').last;
            else if (!p.isAbsolute(text))
              relative = text;
            if (relative == null || !relative.startsWith('roms/')) continue;
            final addon = File(
              MelonxFileTransaction.targetPath(source, relative),
            );
            if (!await addon.exists())
              throw const FormatException('sourceUnknown');
            final target = relative.startsWith('roms/switch/')
                ? relative
                : 'roms/switch/${relative.substring(5)}';
            if (!items.any((item) => item.relative == target))
              await add(addon, target);
          }
        }
      }
    }
    if (items.isEmpty && unsupported.isEmpty && linkedGames.isEmpty)
      throw const FormatException('sourceUnknown');
    return MelonxMigrationPlan(source, items, unsupported, linkedGames);
  }

  static Object? relocate(
    Object? value,
    Directory source,
    Directory root, {
    required bool addon,
  }) {
    if (value is List)
      return value.map((v) => relocate(v, source, root, addon: addon)).toList();
    if (value is Map)
      return value.map(
        (k, v) => MapEntry(k, relocate(v, source, root, addon: addon)),
      );
    if (value is! String) return value;
    String? relative;
    if (p.isWithin(source.path, value)) {
      relative = p.relative(value, from: source.path);
    } else if (value.contains('/Documents/')) {
      relative = value.split('/Documents/').last;
    } else if (!p.isAbsolute(value) &&
        (value.startsWith('roms/') || value.startsWith('addons/'))) {
      relative = value;
    }
    if (relative == null) return value;
    if (relative.startsWith('roms/') && !relative.startsWith('roms/switch/'))
      relative = 'roms/switch/${relative.substring(5)}';
    final result = MelonxFileTransaction.targetPath(root, relative);
    return addon ? p.relative(result, from: root.path) : result;
  }

  static Future<String> apply(
    MelonxMigrationPlan plan,
    Directory root,
    MelonxTransferControl control, {
    void Function(int, int)? progress,
    Future<void> Function()? registerLibrary,
  }) async {
    await MelonxInternalService.content('firmwareInfo');
    try {
      final backup = await MelonxFileTransaction.apply(
        root,
        plan.items,
        control,
        progress: progress,
        validateInstalled: () async {
          await MelonxInternalService.content('reloadKeys');
          final registered = Directory(
            p.join(root.path, 'bis/system/Contents/registered'),
          );
          if (plan.items.any((item) => item.relative == 'bis') &&
              await registered.exists() &&
              !await registered.list().isEmpty) {
            final report = await MelonxInternalService.content('firmwareInfo');
            if (report['firmware']?.toString().isNotEmpty != true)
              throw const FormatException('firmwareUnrecognized');
          }
          for (final item in plan.items) {
            final name = p.basename(item.relative);
            if (item.source is! File ||
                !{'updates.json', 'dlc.json'}.contains(name))
              continue;
            final title = p.basename(p.dirname(item.relative));
            if (!RegExp(r'^[a-fA-F0-9]{16}$').hasMatch(title))
              throw const FormatException('sourceUnknown');
            final value = jsonDecode(
              await File(p.join(root.path, item.relative)).readAsString(),
            );
            final references = name == 'updates.json'
                ? [
                    if ((value as Map)['selected']?.toString().isNotEmpty ==
                        true)
                      value['selected'],
                  ]
                : (value as List).map((e) => e['path']).toList();
            for (final reference in references) {
              final file = p.isAbsolute(reference as String)
                  ? reference
                  : p.join(root.path, reference);
              await MelonxInternalService.content(
                name == 'updates.json' ? 'inspectUpdate' : 'inspectDlc',
                filePath: file,
                titleId: title,
              );
            }
          }
          await registerLibrary?.call();
        },
        validateStaged: (stage) async {
          for (final item in plan.items) {
            control.check();
            final staged = File(p.join(stage.path, item.relative));
            if (item.relative.startsWith('system${p.separator}') &&
                item.relative.endsWith('.keys')) {
              await MelonxInternalService.content(
                'reloadKeys',
                filePath: staged.path,
              );
            }
            if (item.relative == p.join('system', 'Profiles.json')) {
              final profiles = jsonDecode(await staged.readAsString());
              if (profiles is! Map ||
                  profiles['profiles'] is! List ||
                  (profiles['profiles'] as List).isEmpty)
                throw const FormatException('sourceUnknown');
              for (final profile in profiles['profiles'] as List) {
                if (profile is! Map ||
                    !RegExp(
                      r'^[0-9a-fA-F]{32}$',
                    ).hasMatch('${profile['user_id']}'))
                  throw const FormatException('sourceUnknown');
              }
            }
            if (item.source is File &&
                p.extension(item.relative) == '.json' &&
                (item.relative == 'config.json' ||
                    item.relative.startsWith('config${p.separator}') ||
                    item.relative.startsWith('games${p.separator}'))) {
              if (await staged.length() > 4 * 1024 * 1024)
                throw const FormatException('incompleteTransfer');
              final decoded = jsonDecode(await staged.readAsString());
              final value = relocate(
                item.relative.startsWith('games${p.separator}')
                    ? decoded
                    : sanitizedSettings(
                        Map<String, dynamic>.from(decoded as Map),
                      ),
                plan.source,
                root,
                addon: item.relative.startsWith('games${p.separator}'),
              );
              await staged.writeAsString(jsonEncode(value), flush: true);
            }
          }
        },
      );
      if (plan.restartRequired)
        await MelonxInternalService.channel.invokeMethod<void>(
          'markLibraryRestartRequired',
        );
      return backup;
    } catch (_) {
      try {
        await MelonxInternalService.content('reloadKeys');
      } catch (_) {
        /* retain original import failure */
      }
      rethrow;
    }
  }

  static Future<MelonxPreparedSave> prepareSave(
    Directory root,
    MelonxSaveCandidate candidate,
    Map<String, String> association,
    Directory staged,
    MelonxTransferControl control,
  ) async {
    if (await MelonxFileTransaction.size(candidate.folder) == 0)
      throw const FormatException('noSaves');
    final target = await MelonxInternalService.channel
        .invokeMapMethod<String, dynamic>('saveTarget', association);
    if (target?['success'] != true)
      throw const FormatException('sourceUnknown');
    final destination = target!['path'] as String;
    final relative = p.relative(destination, from: root.path);
    MelonxFileTransaction.targetPath(root, relative);
    if (!RegExp(
      r'^bis/user/save/[a-fA-F0-9]{16}$',
    ).hasMatch(relative.replaceAll(p.separator, '/')))
      throw const FormatException('unsafePath');
    await staged.create(recursive: true);
    if (await Directory(destination).exists()) {
      await for (final entry in Directory(
        destination,
      ).list(followLinks: false)) {
        if (!{'0', '1'}.contains(p.basename(entry.path))) {
          await MelonxFileTransaction.copy(
            entry,
            p.join(staged.path, p.basename(entry.path)),
            control,
          );
        }
      }
    }
    for (final part in ['0', '1']) {
      final data = Directory(p.join(staged.path, part));
      if (await data.exists()) await data.delete(recursive: true);
      await MelonxFileTransaction.copy(candidate.folder, data.path, control);
    }
    return MelonxPreparedSave(
      MelonxTransferItem(
        staged,
        relative,
        await MelonxFileTransaction.size(staged),
        await Directory(destination).exists(),
      ),
      association,
    );
  }

  static Future<String> applySaves(
    Directory root,
    List<MelonxPreparedSave> saves,
    MelonxTransferControl control, {
    void Function(int, int)? progress,
  }) => MelonxFileTransaction.apply(
    root,
    saves.map((s) => s.item).toList(),
    control,
    progress: progress,
    validateInstalled: () async {
      for (final save in saves) {
        final target = await MelonxInternalService.channel
            .invokeMapMethod<String, dynamic>('saveTarget', save.association);
        if (target?['success'] != true ||
            !p.equals(
              target!['path'] as String,
              p.join(root.path, save.item.relative),
            ) ||
            !await Directory(target['dataPath'] as String).exists())
          throw const FormatException('incompleteTransfer');
      }
    },
  );

  static Future<List<MelonxSaveCandidate>> saves(Directory selected) async {
    final found = <MelonxSaveCandidate>[];
    Future<void> visit(Directory dir, int depth) async {
      if (depth > 5) return;
      final name = p.basename(dir.path);
      if (RegExp(r'^010[0-9a-fA-F]{13}$').hasMatch(name)) {
        final profiles = await dir
            .list(followLinks: false)
            .where(
              (entry) =>
                  entry is Directory &&
                  RegExp(r'^[a-fA-F0-9]{32}$').hasMatch(p.basename(entry.path)),
            )
            .toList();
        if (profiles.isNotEmpty) {
          for (final profile in profiles.whereType<Directory>()) {
            final zero = Directory(p.join(profile.path, '0'));
            found.add(
              MelonxSaveCandidate(
                await zero.exists() ? zero : profile,
                name.toLowerCase(),
                p.basename(profile.path).toLowerCase(),
              ),
            );
          }
          return;
        }
        final zero = Directory(p.join(dir.path, '0'));
        found.add(
          MelonxSaveCandidate(
            await zero.exists() ? zero : dir,
            name.toLowerCase(),
          ),
        );
        return;
      }
      await for (final entry in dir.list(followLinks: false)) {
        if (entry is Link) throw const FormatException('unsafePath');
        if (entry is Directory &&
            !MelonxTransferSource.ignored(p.basename(entry.path)))
          await visit(entry, depth + 1);
      }
    }

    // Raw LibHac save IDs are not title IDs. A full NAND belongs in migration,
    // otherwise the user explicitly associates an ordinary save export.
    if (await Directory(p.join(selected.path, 'bis')).exists())
      throw const FormatException('sourceUnknown');
    await visit(selected, 0);
    if (found.isNotEmpty) return found;
    final zero = Directory(p.join(selected.path, '0'));
    if (await zero.exists()) return [MelonxSaveCandidate(zero, null)];
    final entries = await selected.list(followLinks: false).toList();
    if (entries.any(
      (e) => e is File && !MelonxTransferSource.ignored(p.basename(e.path)),
    ))
      return [MelonxSaveCandidate(selected, null)];
    return entries
        .whereType<Directory>()
        .where((e) => !MelonxTransferSource.ignored(p.basename(e.path)))
        .map((e) => MelonxSaveCandidate(e, null))
        .toList();
  }
}
