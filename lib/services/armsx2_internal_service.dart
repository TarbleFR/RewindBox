import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import 'armsx2_folder_service.dart';
import 'config_service.dart';
import 'logger_service.dart';
import 'storage/file_content_compare.dart';
import 'storage/storage_import_activity.dart';
import 'storage/storage_picker_copies.dart';

/// Why one picked file was not imported; [code] is one of the
/// `Armsx2InternalService.reason*` codes.
class Armsx2ImportFailure {
  const Armsx2ImportFailure(this.name, this.code, {this.detail});

  final String name;
  final String code;

  /// OS text of a failed copy (never a path), shown after the reason.
  final String? detail;
}

class Armsx2ImportResult {
  const Armsx2ImportResult({
    required this.imported,
    required this.rejected,
    this.errors = const <String>[],
    this.failures = const <Armsx2ImportFailure>[],
    this.alreadyPresent = 0,
    this.acceptedExtensions = const <String>[],
  });

  final int imported;
  final int rejected;
  final List<String> errors;
  final List<Armsx2ImportFailure> failures;

  /// Picked files whose name and content already match a file of the folder.
  final int alreadyPresent;

  /// Extensions named by the "wrong file type" reason (games only).
  final List<String> acceptedExtensions;

  /// Report lines for the refused files and the already-present ones (the
  /// imported count has its own message): "N file(s) not imported:", up to
  /// [Armsx2InternalService.maxListed] "name — reason" lines, "and N more".
  /// [text] resolves an Armsx2UiLocale key. Empty when there is nothing to say.
  String problemSummary(String Function(String key) text) {
    String fill(String key, Map<String, Object> values) {
      var value = text(key);
      for (final item in values.entries) {
        value = value.replaceAll('{${item.key}}', '${item.value}');
      }
      return value;
    }

    String withDetail(Armsx2ImportFailure failure, String reason) {
      final detail = failure.detail;
      return failure.code == Armsx2InternalService.reasonCopyFailed &&
              detail != null &&
              detail.isNotEmpty
          ? '$reason ($detail)'
          : reason;
    }

    final lines = <String>[];
    if (alreadyPresent > 0) {
      lines.add(fill('importAlready', {'count': alreadyPresent}));
    }
    if (failures.isNotEmpty) {
      lines.add(fill('importNotImported', {'count': failures.length}));
      for (final failure in failures.take(Armsx2InternalService.maxListed)) {
        lines.add(
          fill('importLine', {
            'name': failure.name,
            'reason': withDetail(
              failure,
              fill(Armsx2InternalService.reasonKey(failure.code), {
                'extensions': acceptedExtensions.join(', '),
              }),
            ),
          }),
        );
      }
      final more = failures.length - Armsx2InternalService.maxListed;
      if (more > 0) lines.add(fill('importMore', {'count': more}));
    }
    return lines.join('\n');
  }
}

/// Outcome of copying one file into the Games or BIOS folder.
class Armsx2CopyOutcome {
  const Armsx2CopyOutcome.copied(this.length)
    : failureCode = null,
      errorText = null,
      alreadyPresent = false;
  const Armsx2CopyOutcome.already(this.length)
    : failureCode = null,
      errorText = null,
      alreadyPresent = true;
  const Armsx2CopyOutcome.failed(this.failureCode, {this.errorText})
    : length = 0,
      alreadyPresent = false;

  final int length;
  final String? failureCode;
  final bool alreadyPresent;
  final String? errorText;
}

class _LengthMismatch implements Exception {
  const _LengthMismatch();
}

class _Claim {
  const _Claim(this.file, {this.alreadyPresent = false});

  final File? file;
  final bool alreadyPresent;
}

/// Files-app-visible storage and import surface for NeoStation's embedded
/// ARMSX2 engine. This is the canonical PS2 storage root on iOS.
class Armsx2InternalService {
  Armsx2InternalService._();

  static const reasonWrongType = 'wrongType';
  static const reasonUnreadable = 'unreadable';
  static const reasonNoSpace = 'noSpace';
  static const reasonCopyFailed = 'copyFailed';
  static const reasonBiosTooLarge = 'biosTooLarge';

  /// Files named in the report; the rest is summarised as "and N more".
  static const maxListed = 3;

  /// Real PS2 BIOS dumps are a few MiB; anything larger is a game image.
  static const biosMaxBytes = 64 * 1024 * 1024;

  static bool isTooLargeForBios(int length) => length > biosMaxBytes;

  static String reasonKey(String code) => switch (code) {
    reasonWrongType => 'reasonWrongType',
    reasonUnreadable => 'reasonUnreadable',
    reasonNoSpace => 'reasonNoSpace',
    reasonBiosTooLarge => 'reasonBiosTooLarge',
    _ => 'reasonCopyFailed',
  };

  /// A failed copy is reported as a lack of space when the OS says so
  /// (ENOSPC, 28) or when the copy came out shorter than its source.
  static String reasonForCopyError(Object error) {
    if (error is _LengthMismatch) return reasonNoSpace;
    if (error is FileSystemException && error.osError?.errorCode == 28) {
      return reasonNoSpace;
    }
    return reasonCopyFailed;
  }

  static Future<Directory> rootDirectory() async {
    final documents = await getApplicationDocumentsDirectory();
    return Directory(path.join(documents.path, 'ARMSX2'));
  }

  static Future<Directory> gamesDirectory() async {
    final root = await rootDirectory();
    return Directory(path.join(root.path, 'Games'));
  }

  static Future<Directory> biosDirectory() async {
    final root = await rootDirectory();
    return Directory(path.join(root.path, 'BIOS'));
  }

  static Future<Directory> savesDirectory() async {
    final root = await rootDirectory();
    return Directory(path.join(root.path, 'Saves'));
  }

  static Future<void> ensureLayout() async {
    final root = await rootDirectory();
    final games = Directory(path.join(root.path, 'Games'));
    final bios = Directory(path.join(root.path, 'BIOS'));
    final saves = Directory(path.join(root.path, 'Saves'));

    for (final directory in <Directory>[
      root,
      games,
      bios,
      saves,
      Directory(path.join(saves.path, 'Memory Cards')),
      Directory(path.join(saves.path, 'Savestates')),
    ]) {
      await directory.create(recursive: true);
    }

    // Keep the existing scanner/launcher ownership boundary but point it at
    // NeoStation's own Files-visible ARMSX2 root.
    ConfigService.linkedArmsx2FolderPath = root.path;
    ConfigService.linkedArmsx2GameFolderPath = games.path;
  }

  static Set<String> get supportedGameExtensions =>
      Armsx2FolderService.ps2GameExtensions
          .map((extension) => extension.replaceFirst('.', '').toLowerCase())
          .toSet();

  static Future<Armsx2ImportResult> importGames() => StorageImportActivity.run(() async {
    await ensureLayout();
    final extensions = supportedGameExtensions.toList()..sort();
    final selection = await FilePicker.pickFiles(
      allowMultiple: true,
      type: FileType.custom,
      allowedExtensions: extensions,
      withData: false,
      lockParentWindow: true,
    );
    if (selection == null) {
      return const Armsx2ImportResult(imported: 0, rejected: 0);
    }

    final destination = await gamesDirectory();
    return _copySelection(
      selection.files,
      destination,
      acceptedExtensions: supportedGameExtensions,
    );
  });

  static Future<Armsx2ImportResult> importBios() => StorageImportActivity.run(() async {
    await ensureLayout();
    // BIOS dumps are encountered with several extensions (and occasionally
    // none). Let the Core's IsBIOS validation remain authoritative at launch.
    final selection = await FilePicker.pickFiles(
      allowMultiple: true,
      type: FileType.any,
      withData: false,
      lockParentWindow: true,
    );
    if (selection == null) {
      return const Armsx2ImportResult(imported: 0, rejected: 0);
    }
    return _copySelection(
      selection.files,
      await biosDirectory(),
      maxBytes: biosMaxBytes,
    );
  });

  static Future<Armsx2ImportResult> _copySelection(
    List<PlatformFile> files,
    Directory destination, {
    Set<String>? acceptedExtensions,
    int? maxBytes,
  }) async {
    await destination.create(recursive: true);
    var imported = 0;
    var rejected = 0;
    var alreadyPresent = 0;
    final errors = <String>[];
    final failures = <Armsx2ImportFailure>[];
    void refuse(String name, String code, {String? detail}) {
      rejected++;
      errors.add('$name: $code');
      failures.add(Armsx2ImportFailure(name, code, detail: detail));
    }

    // Picked path -> length its import verified (docs/storage-audit-cleanup.md § 4).
    final verifiedCopies = <String, int>{};

    for (final picked in files) {
      final sourcePath = picked.path;
      final extension = path
          .extension(picked.name)
          .replaceFirst('.', '')
          .toLowerCase();
      if (sourcePath == null) {
        refuse(picked.name, reasonUnreadable);
        continue;
      }
      if (acceptedExtensions != null &&
          !acceptedExtensions.contains(extension)) {
        refuse(picked.name, reasonWrongType);
        continue;
      }

      final source = File(sourcePath);
      if (!await source.exists()) {
        refuse(picked.name, reasonUnreadable);
        continue;
      }

      try {
        final outcome = await copyFile(
          source,
          destination,
          picked.name,
          maxBytes: maxBytes,
        );
        final code = outcome.failureCode;
        if (code != null) {
          final text = outcome.errorText;
          if (text != null) {
            LoggerService.instance.e(
              'ARMSX2 import of ${picked.name} failed: $text',
            );
          }
          refuse(
            picked.name,
            code,
            detail: code == reasonCopyFailed ? text : null,
          );
          continue;
        }
        // Copied and verified, or already in the library under the same
        // name and bytes: either way the picker's copy (often several GiB)
        // is not read again.
        verifiedCopies[sourcePath] = outcome.length;
        if (outcome.alreadyPresent) {
          alreadyPresent++;
        } else {
          imported++;
        }
      } catch (error) {
        LoggerService.instance.e(
          'ARMSX2 import of ${picked.name} failed: $error',
        );
        final code = reasonForCopyError(error);
        refuse(
          picked.name,
          code,
          detail: code == reasonCopyFailed ? copyErrorText(error) : null,
        );
      }
    }
    // Games and BIOS alike: once every pick is handled, the picker's copies
    // of the verified imports are not read again.
    for (final copy in verifiedCopies.entries) {
      await StoragePickerCopies.discardAfterVerifiedImport(
        copy.key,
        expectedLength: copy.value,
      );
    }

    return Armsx2ImportResult(
      imported: imported,
      rejected: rejected,
      errors: errors,
      failures: failures,
      alreadyPresent: alreadyPresent,
      acceptedExtensions: acceptedExtensions == null
          ? const <String>[]
          : (acceptedExtensions.toList()..sort()),
    );
  }

  /// Copies [source] into [destination] under [name], keeping today's
  /// "name (2).ext" rule when the name is taken by a file with other bytes.
  /// A file of the same name AND the same content is left alone ("already
  /// imported"). With [maxBytes], a larger source is refused before any copy.
  /// A copy that fails midway removes the file this copy created, and only
  /// that one. [copier] exists for tests.
  static Future<Armsx2CopyOutcome> copyFile(
    File source,
    Directory destination,
    String name, {
    int? maxBytes,
    Future<void> Function(File source, String to)? copier,
  }) async {
    final int sourceLength;
    try {
      sourceLength = await source.length();
    } on FileSystemException {
      return const Armsx2CopyOutcome.failed(reasonUnreadable);
    }
    if (maxBytes != null && sourceLength > maxBytes) {
      return const Armsx2CopyOutcome.failed(reasonBiosTooLarge);
    }
    if (sourceLength <= 0) {
      return const Armsx2CopyOutcome.failed(reasonUnreadable);
    }
    final _Claim claim;
    try {
      claim = await _claimDestination(source, destination, name, sourceLength);
    } catch (error) {
      return Armsx2CopyOutcome.failed(
        reasonForCopyError(error),
        errorText: copyErrorText(error),
      );
    }
    if (claim.alreadyPresent) return Armsx2CopyOutcome.already(sourceLength);

    // Created by this call (exclusive create): the only file it may delete.
    final output = claim.file!;
    try {
      if (copier != null) {
        await copier(source, output.path);
      } else {
        await source.copy(output.path);
      }
      final outputLength = await output.length();
      if (sourceLength <= 0 || sourceLength != outputLength) {
        throw const _LengthMismatch();
      }
    } catch (error) {
      try {
        if (await output.exists()) await output.delete();
      } catch (_) {}
      return Armsx2CopyOutcome.failed(
        reasonForCopyError(error),
        errorText: copyErrorText(error),
      );
    }
    return Armsx2CopyOutcome.copied(sourceLength);
  }

  /// Text of a copy error for the log and the refusal line: the OS message
  /// only, never the path.
  static String copyErrorText(Object error) {
    if (error is FileSystemException) {
      final os = error.osError?.message ?? '';
      return os.isNotEmpty ? os : error.message;
    }
    return error.runtimeType.toString();
  }

  /// Creates the destination file without ever replacing another one:
  /// `create(exclusive: true)` fails when the name is taken, so the next
  /// free "name (N)" is tried. A taken name that holds the same bytes as
  /// [source] means "already in the library".
  static Future<_Claim> _claimDestination(
    File source,
    Directory destination,
    String name,
    int sourceLength,
  ) async {
    final safeName = path.basename(name);
    final stem = path.basenameWithoutExtension(safeName);
    final extension = path.extension(safeName);
    for (var index = 1; index < 10000; index++) {
      final candidate = File(
        path.join(
          destination.path,
          index == 1 ? safeName : '$stem ($index)$extension',
        ),
      );
      try {
        await candidate.create(exclusive: true);
        return _Claim(candidate);
      } on FileSystemException {
        if (await FileSystemEntity.type(candidate.path) ==
            FileSystemEntityType.notFound) {
          rethrow;
        }
        if (!await FileSystemEntity.isFile(candidate.path)) continue;
        if (await candidate.length() == sourceLength &&
            await filesHaveSameContent(source, candidate)) {
          return const _Claim(null, alreadyPresent: true);
        }
      }
    }
    throw FileSystemException('No free destination name for $safeName');
  }
}
