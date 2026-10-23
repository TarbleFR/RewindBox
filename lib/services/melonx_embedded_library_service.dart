import 'package:archive/archive_io.dart';
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
import 'melonx_file_transaction.dart';
import 'melonx_key_file.dart';
import 'logger_service.dart';

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

  static Future<bool> importFirmware({Future<void> Function(File)? install}) =>
      StorageImportActivity.run(
        () => MelonxInternalService.editLibrary(() async {
          final source = await pick({'zip', 'xci'});
          if (source == null) return false;
          if (path.extension(source.path).toLowerCase() == '.zip') {
            final input = InputFileStream(source.path);
            try {
              final decoder = ZipDecoder();
              final archive = decoder.decodeStream(input);
              if (decoder.directory.filePosition < 0 ||
                  archive.length == 0 ||
                  archive.length > 50000)
                throw const FormatException('invalidArchive');
            } catch (_) {
              throw const FormatException('invalidArchive');
            } finally {
              await input.close();
            }
          }
          if (install != null) {
            await install(source);
          } else {
            await MelonxInternalService.content(
              'installFirmware',
              filePath: source.path,
            );
          }
          return true;
        }),
      );

  static Future<MelonxKeysReport> importKeys() =>
      StorageImportActivity.run(() async {
        final selection = await FilePicker.pickFiles(
          // .keys has no portable iOS document UTI; the import validates the
          // selected files, including provider-added .txt/copy suffixes.
          type: FileType.any,
          withData: false,
          allowMultiple: true,
        );
        if (selection == null) return const MelonxKeysReport([], {});
        return importKeyFiles(
          selection.files
              .where((f) => f.path != null)
              .map((f) => File(f.path!))
              .toList(),
        );
      });

  static Future<MelonxKeysReport> importKeyFiles(
    List<File> files,
  ) => MelonxInternalService.editLibrary(() async {
    final root = await MelonxInternalService.rootDirectory();
    final preview = await Directory.systemTemp.createTemp('rewindbox-keys-');
    final refused = <String, String>{};
    final valid = <String, File>{};
    final ignored = <String, int>{};
    final counts = <String, int>{};
    for (final file in files) {
      final name = MelonxKeyFile.canonicalName(path.basename(file.path));
      if (name == null) continue;
      counts[name] = (counts[name] ?? 0) + 1;
    }
    try {
      for (final file in files) {
        final name = MelonxKeyFile.canonicalName(path.basename(file.path));
        try {
          if (name == null)
            throw const FormatException('unknownKey');
          if (counts[name]! > 1) throw const FormatException('duplicateKey');
          if (await file.length() > 4 * 1024 * 1024 || await file.length() == 0)
            throw const FormatException('keySyntax');
          final canonical = File(path.join(preview.path, name));
          await canonical.writeAsString(
            MelonxKeyFile.normalize(await file.readAsBytes(), name),
            flush: true,
          );
          final validation = await MelonxInternalService.content(
            'reloadKeys',
            filePath: canonical.path,
          );
          valid[name] = canonical;
          final count = validation['ignoredKeys'];
          if (count is int && count > 0) ignored[name] = count;
        } on FormatException catch (error) {
          refused[path.basename(file.path)] = error.message;
        } on MelonxContentException catch (error) {
          refused[path.basename(file.path)] = const {
            'keySyntax', 'keySize', 'keyConflict', 'keyNoSupported',
            'keyReadFailed', 'keyImportFailed',
          }.contains(error.code) ? error.code : 'keyImportFailed';
          // Fixed code only: never log selected file bytes or native text that
          // might contain material from a personal key export.
          LoggerService.instance.e('[MeloNX:keys] ${refused[path.basename(file.path)]}');
        } on FileSystemException {
          refused[path.basename(file.path)] = 'keyReadFailed';
        } catch (_) {
          refused[path.basename(file.path)] = 'keyImportFailed';
          LoggerService.instance.e('[MeloNX:keys] keyImportFailed');
        }
      }
      if (valid.isNotEmpty) {
        final items = <MelonxTransferItem>[];
        for (final entry in valid.entries) {
          items.add(
            MelonxTransferItem(
              entry.value,
              path.join('system', entry.key),
              await entry.value.length(),
              await File(path.join(root.path, 'system', entry.key)).exists(),
            ),
          );
        }
        try {
          await MelonxFileTransaction.apply(
            root,
            items,
            MelonxTransferControl(),
            validateInstalled: () async {
              await MelonxInternalService.content('reloadKeys');
            },
          );
          SwitchTitleExtractor.resetKeys();
        } catch (_) {
          await MelonxInternalService.content('reloadKeys');
          rethrow;
        }
      }
      return MelonxKeysReport(
        valid.keys.toList(),
        refused,
        ignored: ignored,
        prodMissing: !await File(
          path.join(root.path, 'system', 'prod.keys'),
        ).exists(),
      );
    } finally {
      await preview.delete(recursive: true);
    }
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
      StorageImportActivity.run(
        () => MelonxInternalService.editLibrary(() async {
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
        }),
      );
}

class MelonxKeysReport {
  const MelonxKeysReport(
    this.imported,
    this.refused, {
    this.prodMissing = false,
    this.ignored = const {},
  });
  final List<String> imported;
  final Map<String, String> refused;
  final bool prodMissing;
  final Map<String, int> ignored;
}
