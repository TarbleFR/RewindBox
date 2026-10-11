import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

import 'logger_service.dart';
import 'rpcs3_internal_service.dart';

/// Final state of one file picked for a RAP licence import.
enum Rpcs3RapImportStatus { imported, replaced, alreadyPresent, rejected }

/// Why a picked file was not installed.
enum Rpcs3RapRejection {
  /// The extension is not `.rap` (in any case).
  notRapFile,

  /// The file name is not a 36-character PS3 content ID.
  invalidContentId,

  /// The file is not exactly 16 bytes long.
  invalidSize,

  /// The file could not be read (missing, iCloud placeholder, permission).
  unreadable,

  /// An earlier file of the same selection has the same content ID with
  /// different bytes; the first one was used.
  selectionConflict,

  /// A different licence is installed for this content ID and the user kept
  /// it.
  conflictKept,

  /// `Data/vfs.yml` moves `dev_hdd0` away from NeoStation's RPCS3 folder.
  storageRedirected,

  /// Writing or verifying the licence failed.
  writeFailed,
}

/// One line of the per-file report, in picker order.
@immutable
class Rpcs3RapImportEntry {
  const Rpcs3RapImportEntry({
    required this.fileName,
    required this.status,
    this.contentId,
    this.rejection,
    this.byteCount,
    this.technicalDetail,
    this.backupPath,
  });

  /// Raw file name as picked (never translated).
  final String fileName;
  final Rpcs3RapImportStatus status;

  /// Upper-case content ID (also the installed stem) when the name is valid.
  final String? contentId;
  final Rpcs3RapRejection? rejection;

  /// Actual size for [Rpcs3RapRejection.invalidSize].
  final int? byteCount;

  /// Raw operating-system diagnostic, shown apart from the translated text.
  final String? technicalDetail;

  /// Copy of the replaced licence for [Rpcs3RapImportStatus.replaced].
  final String? backupPath;

  /// Name RPCS3 looks up: `<CONTENT_ID>.rap`.
  String? get installedName => contentId == null
      ? null
      : '$contentId${Rpcs3RapLicenceService.extension}';
}

/// Result of [Rpcs3RapLicenceService.commit].
@immutable
class Rpcs3RapImportReport {
  Rpcs3RapImportReport(List<Rpcs3RapImportEntry> entries)
    : entries = List.unmodifiable(entries);

  final List<Rpcs3RapImportEntry> entries;

  int _count(Rpcs3RapImportStatus status) =>
      entries.where((entry) => entry.status == status).length;

  int get imported => _count(Rpcs3RapImportStatus.imported);
  int get replaced => _count(Rpcs3RapImportStatus.replaced);
  int get alreadyPresent => _count(Rpcs3RapImportStatus.alreadyPresent);
  int get rejected => _count(Rpcs3RapImportStatus.rejected);

  String get logSummary =>
      'imported=$imported replaced=$replaced alreadyPresent=$alreadyPresent '
      'rejected=$rejected';
}

/// One picked file after the read-only planning pass.
@immutable
class Rpcs3RapPlannedFile {
  const Rpcs3RapPlannedFile._({
    required this.fileName,
    this.contentId,
    this.bytes,
    this.rejection,
    this.byteCount,
    this.technicalDetail,
    this.conflictsWithInstalled = false,
  });

  final String fileName;
  final String? contentId;

  /// The 16 licence bytes, kept in memory so the security-scoped picker URLs
  /// can be released before any dialog or write.
  final Uint8List? bytes;
  final Rpcs3RapRejection? rejection;
  final int? byteCount;
  final String? technicalDetail;

  /// First file of the selection for this content ID whose bytes differ from
  /// the licence installed for the active user.
  final bool conflictsWithInstalled;

  bool get accepted => rejection == null;
}

/// Read-only result of [Rpcs3RapLicenceService.plan].
@immutable
class Rpcs3RapImportPlan {
  Rpcs3RapImportPlan(List<Rpcs3RapPlannedFile> files)
    : files = List.unmodifiable(files);

  final List<Rpcs3RapPlannedFile> files;

  /// Content IDs whose installed licence differs from the selected one, in
  /// picker order; the user is asked once for all of them.
  List<String> get conflictingContentIds => [
    for (final file in files)
      if (file.conflictsWithInstalled) file.contentId!,
  ];
}

/// Installs PS3 RAP licences where the pinned RPCS3 Core reads them.
///
/// The pinned Core (XITRIX/rpcs3 `22f1152`, see
/// `docs/rpcs3-rap-import-build438.md`) resolves a licence with
/// `rpcs3::utils::get_rap_file_path` (`rpcs3/Emu/system_utils.cpp`): it scans
/// every user of `<dev_hdd0>/home/` and opens
/// `<user>/exdata/<CONTENT_ID>.rap`, lower-case extension, name taken from the
/// NPD header (upper case). `dev_hdd0` is `$(EmulatorDir)dev_hdd0/`, the
/// emulator directory is the support path NeoStation passes to the Core
/// (`<AppSupport>/NeoStation/RPCS3/Data`), and the iOS Core always selects
/// user `00000001` (`Emu.SetUsr("00000001")`, `rpcs3/ios/RPCS3IOS.cpp`).
///
/// The import runs entirely in Dart: no Core, JIT, VPN or library scan. It
/// writes only `exdata/<CONTENT_ID>.rap` (through a verified temporary file
/// in the same folder) and, when the user replaces a different licence, a
/// copy of the previous file in `NeoStation/RPCS3/RapBackups`.
abstract final class Rpcs3RapLicenceService {
  /// User RPCS3 runs as on iOS (`RPCS3IOS.cpp`: `Emu.SetUsr("00000001")`).
  static const String activeUserId = '00000001';

  /// `GetKeyFromRap` and `npDrmIsAvailable` read exactly 16 bytes.
  static const int rapByteLength = 16;

  /// Extension RPCS3 appends to the content ID (case-sensitive on iOS).
  static const String extension = '.rap';

  /// Folder of [Rpcs3InternalService.rootDirectory] holding replaced files.
  static const String backupFolderName = 'RapBackups';

  /// Content ID shown as an example in the report (never translated).
  static const String exampleContentId = 'EP0001-BLES00000_00-0123456789ABCDEF';

  /// `XXYYYY-ZZZZNNNNN_NN-<16 characters>`: 36 characters, as stored in the
  /// NPD header of the licensed content.
  static final RegExp contentIdPattern = RegExp(
    r'^[A-Z]{2}[0-9]{4}-[A-Z]{4}[0-9]{5}_[0-9]{2}-[A-Z0-9_]{16}$',
  );

  /// Copy suffix added to a duplicate name: ` (1)` (downloads) or ` 2`
  /// (Files "Keep Both"). A content ID never contains a space.
  static final RegExp _duplicateSuffix = RegExp(r'\s+(?:\(\d+\)|\d+)$');

  /// iOS name of a file provider item that is not downloaded.
  static final RegExp _iCloudPlaceholder = RegExp(r'^\.(.+)\.icloud$');

  static final _log = LoggerService.instance;
  static bool _running = false;
  static int _tempCounter = 0;

  /// `<dataRoot>/dev_hdd0/home/00000001/exdata`.
  static String exdataPath(String dataRoot) =>
      p.join(dataRoot, 'dev_hdd0', 'home', activeUserId, 'exdata');

  /// Content ID (upper case) for a picked file name, or the rejection.
  static ({String? contentId, Rpcs3RapRejection? rejection}) parseFileName(
    String fileName,
  ) {
    final name = fileName.trim();
    if (name.length <= extension.length ||
        name.substring(name.length - extension.length).toLowerCase() !=
            extension) {
      return (contentId: null, rejection: Rpcs3RapRejection.notRapFile);
    }
    final stem = name
        .substring(0, name.length - extension.length)
        .replaceFirst(_duplicateSuffix, '')
        .trim()
        .toUpperCase();
    if (!contentIdPattern.hasMatch(stem)) {
      return (contentId: null, rejection: Rpcs3RapRejection.invalidContentId);
    }
    return (contentId: stem, rejection: null);
  }

  /// Reads and validates [paths] in order without writing anything.
  static Future<Rpcs3RapImportPlan> plan(
    List<String> paths, {
    required String dataRoot,
  }) async {
    final redirect = await storageRedirection(dataRoot);
    final installed = await _ExactNames.load(Directory(exdataPath(dataRoot)));
    final firstBytes = <String, Uint8List>{};
    final files = <Rpcs3RapPlannedFile>[];

    for (final filePath in paths) {
      var fileName = p.basename(filePath);
      final placeholder = _iCloudPlaceholder.firstMatch(fileName);
      if (placeholder != null) fileName = placeholder.group(1)!;

      final parsed = parseFileName(fileName);
      if (parsed.rejection != null) {
        files.add(
          Rpcs3RapPlannedFile._(
            fileName: fileName,
            rejection: parsed.rejection,
          ),
        );
        continue;
      }
      final contentId = parsed.contentId!;
      if (placeholder != null) {
        files.add(
          Rpcs3RapPlannedFile._(
            fileName: fileName,
            contentId: contentId,
            rejection: Rpcs3RapRejection.unreadable,
            technicalDetail: p.basename(filePath),
          ),
        );
        continue;
      }

      final read = await _readLicence(filePath);
      if (read.rejection != null) {
        files.add(
          Rpcs3RapPlannedFile._(
            fileName: fileName,
            contentId: contentId,
            rejection: read.rejection,
            byteCount: read.byteCount,
            technicalDetail: read.detail,
          ),
        );
        continue;
      }
      final bytes = read.bytes!;

      if (redirect != null) {
        files.add(
          Rpcs3RapPlannedFile._(
            fileName: fileName,
            contentId: contentId,
            rejection: Rpcs3RapRejection.storageRedirected,
            technicalDetail: redirect,
          ),
        );
        continue;
      }

      var conflicts = false;
      if (!firstBytes.containsKey(contentId)) {
        firstBytes[contentId] = bytes;
        try {
          final current = await installed.read('$contentId$extension');
          conflicts = current != null && !_sameBytes(current, bytes);
        } catch (error) {
          // Commit reads it again and reports the failure for this file;
          // nothing is replaced without a successful comparison.
          _log.w('Rpcs3Rap[$contentId] installed licence unreadable: $error');
        }
      }
      files.add(
        Rpcs3RapPlannedFile._(
          fileName: fileName,
          contentId: contentId,
          bytes: bytes,
          conflictsWithInstalled: conflicts,
        ),
      );
    }
    return Rpcs3RapImportPlan(files);
  }

  /// Installs the accepted files of [plan] in picker order.
  ///
  /// The first file of the selection decides for its content ID. Identical
  /// bytes already installed give [Rpcs3RapImportStatus.alreadyPresent]
  /// without touching the file. A different installed licence is replaced
  /// only for content IDs listed by [Rpcs3RapImportPlan.conflictingContentIds]
  /// and only when [replaceConflicts] is true; its previous bytes are first
  /// copied to [backupRoot].
  static Future<Rpcs3RapImportReport> commit(
    Rpcs3RapImportPlan plan, {
    required String dataRoot,
    required String backupRoot,
    required bool replaceConflicts,
  }) async {
    final exdata = Directory(exdataPath(dataRoot));
    final names = await _ExactNames.load(exdata);
    final outcomes = <String, Rpcs3RapImportEntry>{};
    final firstBytes = <String, Uint8List>{};
    final entries = <Rpcs3RapImportEntry>[];
    Object? preparationError;
    var prepared = false;

    Future<void> prepareExdata() async {
      if (prepared) {
        if (preparationError != null) throw preparationError!;
        return;
      }
      prepared = true;
      try {
        await exdata.create(recursive: true);
        final root = await Directory(dataRoot).resolveSymbolicLinks();
        final resolved = await exdata.resolveSymbolicLinks();
        if (!p.isWithin(root, resolved)) {
          throw FileSystemException(
            'exdata resolves outside the RPCS3 data folder',
            resolved,
          );
        }
      } catch (error) {
        preparationError = error;
        rethrow;
      }
    }

    for (final file in plan.files) {
      if (!file.accepted) {
        entries.add(
          Rpcs3RapImportEntry(
            fileName: file.fileName,
            contentId: file.contentId,
            status: Rpcs3RapImportStatus.rejected,
            rejection: file.rejection,
            byteCount: file.byteCount,
            technicalDetail: file.technicalDetail,
          ),
        );
        continue;
      }
      final contentId = file.contentId!;
      final bytes = file.bytes!;
      final targetName = '$contentId$extension';
      Rpcs3RapImportEntry entry(
        Rpcs3RapImportStatus status, {
        Rpcs3RapRejection? rejection,
        String? detail,
        String? backup,
      }) => Rpcs3RapImportEntry(
        fileName: file.fileName,
        contentId: contentId,
        status: status,
        rejection: rejection,
        technicalDetail: detail,
        backupPath: backup,
      );

      final Uint8List? current;
      try {
        current = await names.read(targetName);
      } catch (error) {
        _log.w('Rpcs3Rap[$contentId] installed licence unreadable: $error');
        entries.add(
          entry(
            Rpcs3RapImportStatus.rejected,
            rejection: Rpcs3RapRejection.writeFailed,
            detail: _detail(error),
          ),
        );
        if (!firstBytes.containsKey(contentId)) {
          firstBytes[contentId] = bytes;
          outcomes[contentId] = entries.last;
        }
        continue;
      }
      final earlier = firstBytes[contentId];
      if (current != null && _sameBytes(current, bytes)) {
        entries.add(entry(Rpcs3RapImportStatus.alreadyPresent));
        outcomes.putIfAbsent(contentId, () => entries.last);
        firstBytes.putIfAbsent(contentId, () => bytes);
        continue;
      }
      if (earlier != null) {
        // The first file of this content ID already decided.
        final first = outcomes[contentId];
        if (_sameBytes(earlier, bytes) &&
            first != null &&
            first.status == Rpcs3RapImportStatus.rejected) {
          entries.add(
            entry(
              Rpcs3RapImportStatus.rejected,
              rejection: first.rejection,
              detail: first.technicalDetail,
            ),
          );
        } else {
          entries.add(
            entry(
              Rpcs3RapImportStatus.rejected,
              rejection: Rpcs3RapRejection.selectionConflict,
            ),
          );
        }
        continue;
      }
      firstBytes[contentId] = bytes;

      if (current != null &&
          !(replaceConflicts && file.conflictsWithInstalled)) {
        entries.add(
          entry(
            Rpcs3RapImportStatus.rejected,
            rejection: Rpcs3RapRejection.conflictKept,
          ),
        );
        outcomes[contentId] = entries.last;
        continue;
      }

      try {
        await prepareExdata();
        String? backup;
        if (current != null) {
          backup = await _backup(backupRoot, contentId, current);
        }
        await _writeVerified(exdata, targetName, bytes);
        names.add(targetName);
        entries.add(
          entry(
            current == null
                ? Rpcs3RapImportStatus.imported
                : Rpcs3RapImportStatus.replaced,
            backup: backup,
          ),
        );
      } catch (error) {
        _log.w('Rpcs3Rap[$contentId] write failed: $error');
        entries.add(
          entry(
            Rpcs3RapImportStatus.rejected,
            rejection: Rpcs3RapRejection.writeFailed,
            detail: _detail(error),
          ),
        );
      }
      outcomes[contentId] = entries.last;
    }
    return Rpcs3RapImportReport(entries);
  }

  /// Picks `.rap` files from Files (open in place, multi-selection), plans
  /// them, asks [confirmReplace] once when installed licences differ, then
  /// installs them. Returns null when the picker is cancelled or another RAP
  /// import is running. Never starts the Core or JIT and never rescans the
  /// library.
  static Future<Rpcs3RapImportReport?> importFromFiles({
    required Future<bool> Function(List<String> contentIds) confirmReplace,
  }) async {
    if (_running) {
      _log.w('Rpcs3Rap import ignored: another import is running');
      return null;
    }
    _running = true;
    try {
      final Rpcs3RapImportPlan plan;
      final String dataRoot;
      try {
        final selected = await Rpcs3InternalBridge.pickGameFilesOpenInPlace();
        if (selected == null || selected.isEmpty) return null;
        dataRoot = (await Rpcs3InternalService.dataDirectory()).path;
        plan = await Rpcs3RapLicenceService.plan(selected, dataRoot: dataRoot);
      } finally {
        await _releasePickerScopes();
      }

      final conflicts = plan.conflictingContentIds;
      final replace = conflicts.isNotEmpty && await confirmReplace(conflicts);
      final root = await Rpcs3InternalService.rootDirectory();
      final report = await commit(
        plan,
        dataRoot: dataRoot,
        backupRoot: p.join(root.path, backupFolderName),
        replaceConflicts: replace,
      );
      _log.i('Rpcs3Rap import: ${report.logSummary}');
      for (final entry in report.entries) {
        if (entry.status == Rpcs3RapImportStatus.rejected) {
          _log.i(
            'Rpcs3Rap rejected ${entry.fileName}: ${entry.rejection?.name}'
            '${entry.technicalDetail == null ? '' : ' (${entry.technicalDetail})'}',
          );
        }
      }
      return report;
    } finally {
      _running = false;
    }
  }

  /// Null when RPCS3 reads `dev_hdd0` from `<dataRoot>/dev_hdd0/`; otherwise
  /// a raw description of the redirection found in `Data/vfs.yml`.
  ///
  /// Mirrors `cfg_vfs::get` and `rpcs3::utils::get_hdd0_dir`: an empty
  /// `$(EmulatorDir)` means the config directory (the support path), and an
  /// empty `/dev_hdd0/` means `$(EmulatorDir)dev_hdd0/`. NeoStation never
  /// writes this file; an unreadable one is treated as a redirection.
  static Future<String?> storageRedirection(String dataRoot) async {
    final config = File(p.join(dataRoot, 'vfs.yml'));
    if (!await config.exists()) return null;
    final Map<String, String> values;
    try {
      values = _topLevelYaml(await config.readAsString());
    } catch (error) {
      return 'vfs.yml: ${_detail(error)}';
    }
    final configDir = '$dataRoot/';
    final emulatorDir = values[r'$(EmulatorDir)'] ?? '';
    final emuDir = emulatorDir.isEmpty ? configDir : emulatorDir;
    var hdd0 = values['/dev_hdd0/'] ?? '';
    if (hdd0.isEmpty) hdd0 = r'$(EmulatorDir)dev_hdd0/';
    final resolved = hdd0.replaceAll(r'$(EmulatorDir)', emuDir);
    if (_samePath(resolved, p.join(dataRoot, 'dev_hdd0'))) return null;
    return 'vfs.yml /dev_hdd0/: $resolved';
  }

  /// Dart mirror of `rpcs3::utils::get_rap_file_path` for tests and
  /// diagnostics: the first `home/<user>/exdata/<contentId>.rap` that is a
  /// file, users being 8-character names with a non-zero numeric prefix.
  /// Names are compared exactly, as on iOS's case-sensitive file system.
  @visibleForTesting
  static Future<String?> resolveLikeRpcs3(
    String dataRoot,
    String contentId,
  ) async {
    if (contentId.isEmpty ||
        contentId.length > 0x30 ||
        !RegExp(r'^[A-Za-z0-9_-]+$').hasMatch(contentId)) {
      return null;
    }
    final home = Directory(p.join(dataRoot, 'dev_hdd0', 'home'));
    if (!await home.exists()) return null;
    await for (final user in home.list(followLinks: false)) {
      final name = p.basename(user.path);
      if (_checkUser(name) == 0) continue;
      if (await FileSystemEntity.type(user.path) !=
          FileSystemEntityType.directory) {
        continue;
      }
      final names = await _ExactNames.load(
        Directory(p.join(user.path, 'exdata')),
      );
      final candidate = '$contentId$extension';
      if (names.contains(candidate) &&
          await FileSystemEntity.type(names.pathOf(candidate)) ==
              FileSystemEntityType.file) {
        return names.pathOf(candidate);
      }
    }
    return null;
  }

  /// `check_user` (`system_utils.cpp`): 8 characters whose leading digits
  /// parse to a non-zero number.
  static int _checkUser(String user) {
    if (user.length != 8) return 0;
    final digits = RegExp(r'^[0-9]+').firstMatch(user)?.group(0);
    if (digits == null) return 0;
    return int.parse(digits);
  }

  static Future<_LicenceRead> _readLicence(String filePath) async {
    final file = File(filePath);
    try {
      final stat = await file.stat();
      if (stat.type != FileSystemEntityType.file) {
        return _LicenceRead.rejected(
          Rpcs3RapRejection.unreadable,
          detail: stat.type == FileSystemEntityType.notFound
              ? 'not found: $filePath'
              : 'not a file: ${stat.type}',
        );
      }
      if (stat.size != rapByteLength) {
        return _LicenceRead.rejected(
          Rpcs3RapRejection.invalidSize,
          byteCount: stat.size,
        );
      }
      final handle = await file.open();
      final Uint8List bytes;
      try {
        bytes = await handle.read(rapByteLength + 1);
      } finally {
        await handle.close();
      }
      if (bytes.length != rapByteLength) {
        return _LicenceRead.rejected(
          Rpcs3RapRejection.invalidSize,
          byteCount: bytes.length,
        );
      }
      return _LicenceRead.accepted(bytes);
    } catch (error) {
      return _LicenceRead.rejected(
        Rpcs3RapRejection.unreadable,
        detail: _detail(error),
      );
    }
  }

  static Future<String> _backup(
    String backupRoot,
    String contentId,
    Uint8List previous,
  ) async {
    final directory = Directory(backupRoot);
    await directory.create(recursive: true);
    final now = DateTime.now().toUtc();
    String two(int value) => value.toString().padLeft(2, '0');
    final stamp =
        '${now.year}${two(now.month)}${two(now.day)}T'
        '${two(now.hour)}${two(now.minute)}${two(now.second)}Z';
    var file = File(p.join(backupRoot, '$contentId-$stamp$extension'));
    for (var index = 2; await file.exists(); index++) {
      file = File(p.join(backupRoot, '$contentId-$stamp-$index$extension'));
    }
    await file.writeAsBytes(previous, flush: true);
    if (!_sameBytes(await file.readAsBytes(), previous)) {
      throw FileSystemException('backup verification failed', file.path);
    }
    return file.path;
  }

  static Future<void> _writeVerified(
    Directory exdata,
    String targetName,
    Uint8List bytes,
  ) async {
    final temp = File(
      p.join(
        exdata.path,
        '.$targetName.neostation-'
        '${DateTime.now().microsecondsSinceEpoch}-${_tempCounter++}.tmp',
      ),
    );
    final target = p.join(exdata.path, targetName);
    try {
      await temp.writeAsBytes(bytes, flush: true);
      if (!_sameBytes(await temp.readAsBytes(), bytes)) {
        throw FileSystemException('licence verification failed', temp.path);
      }
      await temp.rename(target);
    } catch (_) {
      try {
        if (await temp.exists()) await temp.delete();
      } catch (_) {}
      rethrow;
    }
    if (!_sameBytes(await File(target).readAsBytes(), bytes)) {
      throw FileSystemException('installed licence differs', target);
    }
  }

  static Future<void> _releasePickerScopes() async {
    try {
      await Rpcs3InternalBridge.releaseScopedResources();
    } catch (error) {
      _log.w('Rpcs3Rap could not release picker scopes: $error');
    }
  }

  static Map<String, String> _topLevelYaml(String text) {
    final values = <String, String>{};
    for (final raw in text.split(RegExp(r'\r?\n'))) {
      if (raw.isEmpty || raw.startsWith(' ') || raw.startsWith('\t')) continue;
      if (raw.trimLeft().startsWith('#')) continue;
      final separator = raw.indexOf(': ');
      final String key;
      final String value;
      if (separator > 0) {
        key = raw.substring(0, separator).trim();
        value = raw.substring(separator + 2).trim();
      } else if (raw.trimRight().endsWith(':')) {
        key = raw.trimRight().substring(0, raw.trimRight().length - 1).trim();
        value = '';
      } else {
        continue;
      }
      values[_unquote(key)] = _unquote(value);
    }
    return values;
  }

  static String _unquote(String value) {
    if (value.length >= 2 &&
        ((value.startsWith('"') && value.endsWith('"')) ||
            (value.startsWith("'") && value.endsWith("'")))) {
      return value.substring(1, value.length - 1);
    }
    return value;
  }

  static bool _samePath(String a, String b) {
    String clean(String value) {
      var normalized = p.normalize(value.replaceAll('\\', '/'));
      while (normalized.length > 1 &&
          (normalized.endsWith('/') || normalized.endsWith('\\'))) {
        normalized = normalized.substring(0, normalized.length - 1);
      }
      return normalized;
    }

    return p.equals(clean(a), clean(b));
  }

  static bool _sameBytes(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    for (var index = 0; index < a.length; index++) {
      if (a[index] != b[index]) return false;
    }
    return true;
  }

  static String _detail(Object error) {
    if (error is FileSystemException) {
      final os = error.osError;
      return [
        error.message,
        if (error.path != null) error.path!,
        if (os != null) '${os.message} (errno ${os.errorCode})',
      ].join(' • ');
    }
    return error.toString();
  }
}

class _LicenceRead {
  const _LicenceRead.accepted(Uint8List this.bytes)
    : rejection = null,
      byteCount = null,
      detail = null;

  const _LicenceRead.rejected(this.rejection, {this.byteCount, this.detail})
    : bytes = null;

  final Uint8List? bytes;
  final Rpcs3RapRejection? rejection;
  final int? byteCount;
  final String? detail;
}

/// Exact (case-sensitive) names of one folder, like iOS's file system sees
/// them, so a `x.RAP` or lower-case ID is never mistaken for the licence
/// RPCS3 opens, even on a case-insensitive test host.
class _ExactNames {
  _ExactNames._(this._directory, this._names);

  static Future<_ExactNames> load(Directory directory) async {
    final names = <String>{};
    if (await directory.exists()) {
      await for (final entity in directory.list(followLinks: false)) {
        names.add(p.basename(entity.path));
      }
    }
    return _ExactNames._(directory, names);
  }

  final Directory _directory;
  final Set<String> _names;

  bool contains(String name) => _names.contains(name);
  String pathOf(String name) => p.join(_directory.path, name);
  void add(String name) => _names.add(name);

  /// Bytes of the regular file named exactly [name], else null.
  Future<Uint8List?> read(String name) async {
    if (!_names.contains(name)) return null;
    final path = pathOf(name);
    if (await FileSystemEntity.type(path) != FileSystemEntityType.file) {
      return null;
    }
    return File(path).readAsBytes();
  }
}
