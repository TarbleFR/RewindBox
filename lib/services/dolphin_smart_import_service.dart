import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;

import 'dolphin_internal_v2_service.dart';
import 'logger_service.dart';
import 'storage/file_content_compare.dart';
import 'storage/storage_import_activity.dart';
import 'storage/storage_picker_copies.dart';

/// Why one picked file was not imported. [code] is one of the
/// `DolphinSmartImportService.reason*` codes; the widget shows the localised
/// sentence of that code.
class DolphinImportFailure {
  const DolphinImportFailure(this.name, this.code, {this.detail});

  final String name;
  final String code;

  /// OS text of a failed copy (never a path), shown after the reason.
  final String? detail;
}

class DolphinSmartImportResult {
  const DolphinSmartImportResult({
    required this.imported,
    required this.rejected,
    required this.changedSystems,
    this.errors = const <String>[],
    this.failures = const <DolphinImportFailure>[],
    this.alreadyPresent = 0,
  });

  final int imported;
  final int rejected;
  final Set<String> changedSystems;
  final List<String> errors;
  final List<DolphinImportFailure> failures;

  /// Picked files whose name and size already match a library file: not copied.
  final int alreadyPresent;

  /// The user-facing report of this import, one line per item: the imported
  /// count, the files already present, then up to
  /// [DolphinSmartImportService.maxListed] refused files with their reason.
  /// [text] resolves a locale key; placeholders are filled here. Empty when
  /// nothing happened (picker cancelled).
  String summary(String Function(String key) text) {
    String fill(String key, Map<String, Object> values) {
      var value = text(key);
      for (final item in values.entries) {
        value = value.replaceAll('{${item.key}}', '${item.value}');
      }
      return value;
    }

    String withDetail(DolphinImportFailure failure, String reason) {
      final detail = failure.detail;
      return failure.code == DolphinSmartImportService.reasonCopyFailed &&
              detail != null &&
              detail.isNotEmpty
          ? '$reason ($detail)'
          : reason;
    }

    final extensions = (DolphinSmartImportService.supportedExtensions.toList()
          ..sort())
        .join(', ');
    final lines = <String>[];
    if (imported > 0) lines.add(fill('imported', {'count': imported}));
    if (alreadyPresent > 0) {
      lines.add(fill('importAlready', {'count': alreadyPresent}));
    }
    if (failures.isNotEmpty) {
      lines.add(fill('importNotImported', {'count': failures.length}));
      for (final failure
          in failures.take(DolphinSmartImportService.maxListed)) {
        lines.add(
          fill('importLine', {
            'name': failure.name,
            'reason': withDetail(
              failure,
              fill(
                DolphinSmartImportService.reasonKey(failure.code),
                {'extensions': extensions},
              ),
            ),
          }),
        );
      }
      final more = failures.length - DolphinSmartImportService.maxListed;
      if (more > 0) lines.add(fill('importMore', {'count': more}));
    } else if (rejected > 0) {
      lines.add(text('failed'));
    }
    return lines.join('\n');
  }
}

/// Outcome of copying one image into a library directory.
class DolphinCopyOutcome {
  const DolphinCopyOutcome.copied(this.length)
    : failureCode = null,
      errorText = null,
      alreadyPresent = false;
  const DolphinCopyOutcome.already(this.length)
    : failureCode = null,
      errorText = null,
      alreadyPresent = true;
  const DolphinCopyOutcome.failed(this.failureCode, {this.errorText})
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

/// Routes every selected Dolphin image by the platform reported by DiscIO,
/// never by the library screen from which the picker was opened.
///
/// The native `saveIdentity` bridge is intentionally used here because it can
/// inspect ISO, RVZ, WIA, GCZ, CISO, WBFS and WAD metadata without starting the
/// Dolphin core or requiring JIT. This keeps GameCube images out of the Wii
/// playlist and Wii images out of the GameCube playlist.
class DolphinSmartImportService {
  DolphinSmartImportService._();

  static const MethodChannel _channel = MethodChannel(
    'neostation/dolphin_internal',
  );
  static final _log = LoggerService.instance;

  static const reasonWrongType = 'wrongType';
  static const reasonUnreadable = 'unreadable';
  static const reasonNotDisc = 'notDisc';
  static const reasonNoSpace = 'noSpace';
  static const reasonCopyFailed = 'copyFailed';

  /// Files named in the report; the rest is summarised as "and N more".
  static const maxListed = 3;

  static String reasonKey(String code) => switch (code) {
    reasonWrongType => 'reasonWrongType',
    reasonUnreadable => 'reasonUnreadable',
    reasonNotDisc => 'reasonNotDisc',
    reasonNoSpace => 'reasonNoSpace',
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

  static Set<String> get supportedExtensions => <String>{
    ...DolphinInternalV2Service.extensionsFor('gc'),
    ...DolphinInternalV2Service.extensionsFor('wii'),
  };

  static Future<String?> detectSystem(String gamePath) async {
    for (final system in const <String>['gc', 'wii']) {
      try {
        final identity = await _channel.invokeMapMethod<String, dynamic>(
          'saveIdentity',
          <String, dynamic>{'gamePath': gamePath, 'system': system},
        );
        if (identity != null && identity['system']?.toString() == system) {
          return system;
        }
      } on PlatformException catch (error) {
        _log.w(
          'Dolphin platform detection failed for $gamePath/$system: $error',
        );
      }
    }
    return null;
  }

  static Future<DolphinSmartImportResult> importGames({
    required String requestedSystem,
  }) => StorageImportActivity.run(() async {
    final requested = requestedSystem.trim().toLowerCase();
    if (!DolphinInternalV2Service.isDolphinSystem(requested)) {
      throw ArgumentError.value(requestedSystem, 'requestedSystem');
    }

    await DolphinInternalV2Service.ensureLayout();
    final extensions = supportedExtensions.toList()..sort();
    final selection = await FilePicker.pickFiles(
      allowMultiple: true,
      type: FileType.custom,
      allowedExtensions: extensions,
      withData: false,
      lockParentWindow: true,
    );
    if (selection == null) {
      return const DolphinSmartImportResult(
        imported: 0,
        rejected: 0,
        changedSystems: <String>{},
      );
    }

    var imported = 0;
    var rejected = 0;
    final changedSystems = <String>{};
    var alreadyPresent = 0;
    final errors = <String>[];
    final failures = <DolphinImportFailure>[];
    void refuse(String name, String code, {String? detail}) {
      rejected++;
      errors.add('$name: $code');
      failures.add(DolphinImportFailure(name, code, detail: detail));
    }

    // Picked path -> length its import verified (docs/storage-audit-cleanup.md § 4).
    final verifiedCopies = <String, int>{};

    for (final picked in selection.files) {
      final sourcePath = picked.path;
      final extension = path
          .extension(picked.name)
          .replaceFirst('.', '')
          .toLowerCase();
      if (sourcePath == null) {
        refuse(picked.name, reasonUnreadable);
        continue;
      }
      if (!extensions.contains(extension)) {
        refuse(picked.name, reasonWrongType);
        continue;
      }

      final source = File(sourcePath);
      if (!await source.exists()) {
        refuse(picked.name, reasonUnreadable);
        continue;
      }

      final actualSystem = await detectSystem(source.path);
      if (actualSystem == null) {
        refuse(picked.name, reasonNotDisc);
        continue;
      }

      try {
        final destination = await DolphinInternalV2Service.libraryDirectory(
          actualSystem,
        );
        await destination.create(recursive: true);
        final outcome = await copyImage(source, destination, picked.name);
        final code = outcome.failureCode;
        if (code != null) {
          final text = outcome.errorText;
          if (text != null) {
            _log.e('Dolphin import of ${picked.name} failed: $text');
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
          continue;
        }

        imported++;
        changedSystems.add(actualSystem);
        _log.i(
          actualSystem == requested
              ? 'Dolphin imported ${picked.name} into $actualSystem.'
              : 'Dolphin auto-routed ${picked.name} from $requested to $actualSystem.',
        );
      } catch (error) {
        _log.e('Dolphin import of ${picked.name} failed: $error');
        final code = reasonForCopyError(error);
        refuse(
          picked.name,
          code,
          detail: code == reasonCopyFailed ? copyErrorText(error) : null,
        );
      }
    }

    // Once every pick is handled, the picker's copies of the verified
    // imports are not read again (same rule as DolphinInternalV2Service).
    for (final copy in verifiedCopies.entries) {
      await StoragePickerCopies.discardAfterVerifiedImport(
        copy.key,
        expectedLength: copy.value,
      );
    }
    return DolphinSmartImportResult(
      imported: imported,
      rejected: rejected,
      changedSystems: changedSystems,
      errors: errors,
      failures: failures,
      alreadyPresent: alreadyPresent,
    );
  });

  /// Copies [source] into [destination] under [name], keeping today's
  /// "name (2).ext" rule when the name is taken by a file with other bytes.
  /// A destination file with the same name AND the same content is left
  /// alone ("already imported"). A copy that fails midway removes the file this
  /// copy created, and only that one. [copier] exists for tests.
  static Future<DolphinCopyOutcome> copyImage(
    File source,
    Directory destination,
    String name, {
    Future<void> Function(File source, String to)? copier,
  }) async {
    final int sourceLength;
    try {
      sourceLength = await source.length();
    } on FileSystemException {
      return const DolphinCopyOutcome.failed(reasonUnreadable);
    }
    if (sourceLength <= 0) {
      return const DolphinCopyOutcome.failed(reasonUnreadable);
    }
    final _Claim claim;
    try {
      claim = await _claimDestination(source, destination, name, sourceLength);
    } catch (error) {
      return DolphinCopyOutcome.failed(
        reasonForCopyError(error),
        errorText: copyErrorText(error),
      );
    }
    if (claim.alreadyPresent) return DolphinCopyOutcome.already(sourceLength);

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
      await _deleteIfExists(output);
      return DolphinCopyOutcome.failed(
        reasonForCopyError(error),
        errorText: copyErrorText(error),
      );
    }
    return DolphinCopyOutcome.copied(sourceLength);
  }

  /// Silently repairs files imported by older builds into the opposite private
  /// playlist. A valid image is moved only when DiscIO positively identifies
  /// the other platform; unreadable/unknown files are left untouched.
  static Future<Set<String>> repairLibraryPlacement() async {
    await DolphinInternalV2Service.ensureLayout();
    final changedSystems = <String>{};

    for (final declaredSystem in const <String>['gc', 'wii']) {
      final sourceDirectory = await DolphinInternalV2Service.libraryDirectory(
        declaredSystem,
      );
      if (!await sourceDirectory.exists()) continue;

      await for (final entity in sourceDirectory.list(followLinks: false)) {
        if (entity is! File) continue;
        final extension = path
            .extension(entity.path)
            .replaceFirst('.', '')
            .toLowerCase();
        if (!supportedExtensions.contains(extension)) continue;

        final actualSystem = await detectSystem(entity.path);
        if (actualSystem == null || actualSystem == declaredSystem) continue;

        final targetDirectory = await DolphinInternalV2Service.libraryDirectory(
          actualSystem,
        );
        await targetDirectory.create(recursive: true);
        final output = await _uniqueDestination(
          targetDirectory,
          path.basename(entity.path),
        );

        try {
          await entity.rename(output.path);
        } on FileSystemException {
          await entity.copy(output.path);
          final sourceLength = await entity.length();
          final outputLength = await output.length();
          if (sourceLength <= 0 || sourceLength != outputLength) {
            await _deleteIfExists(output);
            continue;
          }
          await entity.delete();
        }

        changedSystems
          ..add(declaredSystem)
          ..add(actualSystem);
        _log.i(
          'Dolphin repaired ${path.basename(entity.path)}: '
          '$declaredSystem -> $actualSystem.',
        );
      }
    }

    return changedSystems;
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

  static Future<File> _uniqueDestination(
    Directory directory,
    String originalName,
  ) async {
    final safeName = path.basename(originalName);
    var candidate = File(path.join(directory.path, safeName));
    if (!await candidate.exists()) return candidate;

    final stem = path.basenameWithoutExtension(safeName);
    final extension = path.extension(safeName);
    for (var index = 2; index < 10000; index++) {
      candidate = File(
        path.join(directory.path, '$stem ($index)$extension'),
      );
      if (!await candidate.exists()) return candidate;
    }
    throw FileSystemException('No free destination name for $safeName');
  }

  static Future<void> _deleteIfExists(File file) async {
    try {
      if (await file.exists()) await file.delete();
    } catch (_) {}
  }
}
