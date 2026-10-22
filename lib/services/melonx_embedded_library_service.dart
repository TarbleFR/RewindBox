import 'dart:convert';
import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:path/path.dart' as path;

import '../data/datasources/sqlite_service.dart';
import '../providers/file_provider.dart';
import '../providers/sqlite_config_provider.dart';
import '../repositories/system_repository.dart';
import '../utils/switch_title_extractor.dart';
import 'config_service.dart';
import 'melonx_internal_service.dart';
import 'storage/storage_import_activity.dart';
import 'storage/storage_picker_copies.dart';

/// Owns only user-supplied Switch files. Native content inspection runs on the
/// bridge's library queue; copying uses asynchronous file IO and bounded RAM.
abstract final class MelonxEmbeddedLibraryService {
  static Future<Directory> libraryDirectory() async {
    final root = await MelonxInternalService.rootDirectory();
    final directory = Directory(path.join(root.path, 'roms', 'switch'));
    await directory.create(recursive: true);
    return directory;
  }

  static Future<File?> pick(Set<String> extensions) async {
    final selection = await FilePicker.pickFiles(
      type: FileType.custom,
      allowedExtensions: extensions.toList()..sort(),
      withData: false,
      allowMultiple: false,
    );
    final picked = selection?.files.single;
    if (picked?.path == null) return null;
    final file = File(picked!.path!);
    if (!extensions.contains(
          path.extension(file.path).substring(1).toLowerCase(),
        ) ||
        !await file.exists() ||
        await file.length() <= 0) {
      throw const FormatException('A readable local file is required.');
    }
    return file;
  }

  static Future<File> _copyUnique(File source, Directory destination) async {
    await destination.create(recursive: true);
    final name = path.basename(source.path);
    var file = File(path.join(destination.path, name));
    for (var index = 2; await file.exists(); index++) {
      if (index > 10000)
        throw const FileSystemException('No free import filename.');
      file = File(
        path.join(
          destination.path,
          '${path.basenameWithoutExtension(name)} ($index)${path.extension(name)}',
        ),
      );
    }
    final temporary = File('${file.path}.importing');
    try {
      await source.copy(temporary.path);
      if (await source.length() != await temporary.length()) {
        throw const FileSystemException('Incomplete import.');
      }
      return await temporary.rename(file.path);
    } catch (_) {
      if (await temporary.exists()) await temporary.delete();
      rethrow;
    }
  }

  static Future<bool> importGame(
    SqliteConfigProvider config,
  ) => StorageImportActivity.run(() async {
    final source = await pick(MelonxInternalService.gameExtensions);
    if (source == null) return false;
    final info = await MelonxInternalService.content(
      'metadata',
      filePath: source.path,
    );
    final directory = await libraryDirectory();
    final output = await _copyUnique(source, directory);
    final system = await SystemRepository.getSystemByFolderName('switch');
    if (system?.id == null)
      throw StateError('Nintendo Switch system definition missing.');
    final title = info['title']?.toString();
    final titleId = info['titleId']?.toString();
    try {
      final db = await SqliteService.getDatabase();
      await db.rawInsert(
        '''INSERT INTO user_roms
        (app_system_id, filename, rom_path, title_id, title_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, datetime('now'), datetime('now'))
        ON CONFLICT(rom_path) DO UPDATE SET title_id=excluded.title_id,
          title_name=excluded.title_name, updated_at=datetime('now')''',
        [system!.id, path.basename(output.path), output.path, titleId, title],
      );
      await SystemRepository.addDetectedSystem(system.id!, 'switch');
    } catch (_) {
      await output.delete();
      rethrow;
    }
    // The normal scanner can rediscover this real file on later cold starts.
    await config.addRomFolder(path.dirname(directory.path), scan: false);
    await config.refreshDetectedSystems();
    final iconPath = info['iconPath']?.toString();
    if (iconPath != null) {
      final root = await MelonxInternalService.rootDirectory();
      if (path.isWithin(root.path, iconPath) && await File(iconPath).exists()) {
        final media = Directory(
          path.join(await ConfigService.getMediaPath(), 'switch', 'box2d'),
        );
        await media.create(recursive: true);
        final target = File(
          path.join(
            media.path,
            '${FileProvider.stripRomExtension(path.basename(output.path))}.jpg',
          ),
        );
        if (!await target.exists()) await File(iconPath).copy(target.path);
      }
    }
    await StoragePickerCopies.discardAfterVerifiedImport(
      source.path,
      expectedLength: await output.length(),
    );
    return true;
  });

  static Future<bool> importFirmware() => StorageImportActivity.run(() async {
    final source = await pick({'zip', 'xci'});
    if (source == null) return false;
    await MelonxInternalService.content(
      'installFirmware',
      filePath: source.path,
    );
    return true;
  });

  static Future<bool> importKeys() => StorageImportActivity.run(() async {
    final source = await pick({'keys'});
    if (source == null) return false;
    final name = path.basename(source.path).toLowerCase();
    if (!{'prod.keys', 'title.keys'}.contains(name) ||
        await source.length() > 4 * 1024 * 1024) {
      throw const FormatException(
        'Choose your personal prod.keys or title.keys file.',
      );
    }
    // Validate before replacing any existing keys. This call reloads the old
    // live keyset; the second reload only follows a successful atomic rename.
    await MelonxInternalService.content('reloadKeys', filePath: source.path);
    final root = await MelonxInternalService.rootDirectory();
    final directory = Directory(path.join(root.path, 'system'));
    await directory.create(recursive: true);
    final target = File(path.join(directory.path, name));
    final temporary = File('${target.path}.importing');
    final oldBytes = await target.exists() ? await target.readAsBytes() : null;
    await source.copy(temporary.path);
    try {
      await temporary.rename(target.path);
      await MelonxInternalService.content('reloadKeys', filePath: target.path);
      SwitchTitleExtractor.resetKeys();
    } catch (_) {
      if (oldBytes == null) {
        if (await target.exists()) await target.delete();
      } else {
        await target.writeAsBytes(oldBytes, flush: true);
      }
      await MelonxInternalService.content('reloadKeys');
      rethrow;
    } finally {
      if (await temporary.exists()) await temporary.delete();
    }
    return true;
  });

  static String baseTitleId(String value) {
    if (!RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(value))
      throw const FormatException('A valid base-game title ID is required.');
    return (int.parse(value, radix: 16) & ~0x1fff)
        .toRadixString(16)
        .padLeft(16, '0');
  }

  static Future<void> _writeJson(File target, Object value) async {
    await target.parent.create(recursive: true);
    final temporary = File('${target.path}.importing');
    try {
      await temporary.writeAsString(jsonEncode(value), flush: true);
      await temporary.rename(target.path);
    } finally {
      if (await temporary.exists()) await temporary.delete();
    }
  }

  static Future<bool> importAddon(String titleId, {required bool dlc}) =>
      StorageImportActivity.run(() async {
        final title = baseTitleId(titleId);
        final source = await pick({'nsp'});
        if (source == null) return false;
        final info = await MelonxInternalService.content(
          dlc ? 'inspectDlc' : 'inspectUpdate',
          filePath: source.path,
          titleId: title,
        );
        final root = await MelonxInternalService.rootDirectory();
        final output = await _copyUnique(
          source,
          Directory(path.join(root.path, 'addons', title)),
        );
        final relative = path.relative(output.path, from: root.path);
        final configuration = File(
          path.join(
            root.path,
            'games',
            title,
            dlc ? 'dlc.json' : 'updates.json',
          ),
        );
        try {
          if (dlc) {
            final previous = await configuration.exists()
                ? jsonDecode(await configuration.readAsString()) as List
                : <dynamic>[];
            await _writeJson(configuration, [
              ...previous,
              {'path': relative, 'dlc_nca_list': info['dlc_nca_list']},
            ]);
          } else {
            final previous = await configuration.exists()
                ? jsonDecode(await configuration.readAsString()) as Map
                : <String, dynamic>{};
            await _writeJson(configuration, {
              'selected': relative,
              'paths': <dynamic>{
                ...(previous['paths'] as List? ?? []),
                relative,
              }.toList(),
            });
          }
        } catch (_) {
          await output.delete();
          rethrow;
        }
        await StoragePickerCopies.discardAfterVerifiedImport(
          source.path,
          expectedLength: await output.length(),
        );
        return true;
      });
}
