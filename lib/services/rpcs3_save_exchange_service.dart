import 'dart:async';
import 'dart:io';
import 'dart:io' as io show ZLibDecoder;
import 'dart:math' as math;

import 'package:archive/archive_io.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/foundation.dart';
import 'package:path/path.dart' as p;
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';

import 'logger_service.dart';
import 'rpcs3_internal_service.dart';
import 'rpcs3_param_sfo.dart';
import 'rpcs3_rap_licence_service.dart';

/// Where the saves of an import come from.
enum Rpcs3SaveImportSourceKind {
  /// `Documents/RPCS3/Import/Game Saves`, visible in the Files app.
  filesFolder,

  /// A `.zip` chosen with the system picker (copied into the app).
  zipFile,

  /// A folder opened in place with the documents picker.
  folder,
}

/// Final state of one save directory of an import, in source order.
enum Rpcs3SaveImportStatus { imported, replaced, alreadyPresent, kept, rejected }

/// Why a save directory, or a whole source, was not installed.
enum Rpcs3SaveRejection {
  /// The directory name does not match RPCS3's `dirName` rule.
  invalidDirectoryName,

  /// `PARAM.SFO` is missing or does not parse (before or after staging).
  invalidParamSfo,

  /// The same directory name appeared earlier in the selection.
  duplicateInSelection,

  /// A different save is installed under this name and the user kept it.
  conflictKept,

  /// `Data/vfs.yml` moves `dev_hdd0` away from NeoStation's RPCS3 folder.
  storageRedirected,

  /// An archive entry could escape the destination (`..`, absolute path,
  /// backslash, empty segment).
  unsafeEntry,

  /// A symbolic link was found in the archive or the folder.
  symbolicLink,

  /// More than [Rpcs3SaveExchangeService.maxEntries] entries.
  tooManyEntries,

  /// More than [Rpcs3SaveExchangeService.maxTotalBytes] in total.
  tooLarge,

  /// One file larger than [Rpcs3SaveExchangeService.maxFileBytes].
  fileTooLarge,

  /// The file is not a ZIP archive.
  invalidArchive,

  /// No `PARAM.SFO` folder in the source.
  noSaveFound,

  /// The source could not be read (iCloud placeholder, permission).
  unreadable,

  /// Extracted bytes differ from the archive's size or CRC.
  corruptData,

  /// Staging, backup or the final move failed.
  writeFailed,
}

/// Why an export or an import could not start or finish as a whole.
enum Rpcs3SaveExchangeFailure {
  noSaves,
  nothingFound,
  storageRedirected,
  notZip,
  unreadable,
  exportWriteFailed,
  importWriteFailed,
}

class Rpcs3SaveExchangeException implements Exception {
  const Rpcs3SaveExchangeException(this.failure, {this.technicalDetail});

  final Rpcs3SaveExchangeFailure failure;

  /// Raw diagnostic (path, exception text), shown apart from translations.
  final String? technicalDetail;

  @override
  String toString() =>
      'Rpcs3SaveExchangeException(${failure.name}'
      '${technicalDetail == null ? '' : ', $technicalDetail'})';
}

/// One line of a report: a save directory, or a source that was rejected
/// as a whole (then [name] is the file or folder name).
@immutable
class Rpcs3SaveImportEntry {
  const Rpcs3SaveImportEntry({
    required this.name,
    required this.status,
    this.title,
    this.rejection,
    this.technicalDetail,
    this.fileCount = 0,
    this.byteCount = 0,
    this.backupPath,
  });

  /// Raw save directory name (or source name), never translated.
  final String name;

  /// `TITLE` of PARAM.SFO when it was read.
  final String? title;
  final Rpcs3SaveImportStatus status;
  final Rpcs3SaveRejection? rejection;

  /// Raw system diagnostic, shown apart from the translated reason.
  final String? technicalDetail;
  final int fileCount;
  final int byteCount;

  /// Where the replaced folder was moved for [Rpcs3SaveImportStatus.replaced].
  final String? backupPath;
}

/// Result of [Rpcs3SaveExchangeService.commit].
@immutable
class Rpcs3SaveImportReport {
  Rpcs3SaveImportReport({
    required this.sourceKind,
    required this.sourceName,
    required List<Rpcs3SaveImportEntry> entries,
  }) : entries = List.unmodifiable(entries);

  final Rpcs3SaveImportSourceKind sourceKind;

  /// Raw name of the picked file or folder (or the Files folder label).
  final String sourceName;
  final List<Rpcs3SaveImportEntry> entries;

  int _count(Rpcs3SaveImportStatus status) =>
      entries.where((entry) => entry.status == status).length;

  int get imported => _count(Rpcs3SaveImportStatus.imported);
  int get replaced => _count(Rpcs3SaveImportStatus.replaced);
  int get alreadyPresent => _count(Rpcs3SaveImportStatus.alreadyPresent);
  int get kept => _count(Rpcs3SaveImportStatus.kept);
  int get rejected => _count(Rpcs3SaveImportStatus.rejected);

  String get logSummary =>
      'imported=$imported replaced=$replaced alreadyPresent=$alreadyPresent '
      'kept=$kept rejected=$rejected';
}

/// One save directory found by a prepare pass. Accepted candidates are
/// already copied, verified, into the staging folder.
@immutable
class Rpcs3SaveImportCandidate {
  const Rpcs3SaveImportCandidate._({
    required this.name,
    this.title,
    this.stagedPath,
    this.fileCount = 0,
    this.byteCount = 0,
    this.conflictsWithInstalled = false,
    this.alreadyPresent = false,
    this.rejection,
    this.technicalDetail,
  });

  final String name;
  final String? title;
  final String? stagedPath;
  final int fileCount;
  final int byteCount;

  /// A save of the same name with different content is installed.
  final bool conflictsWithInstalled;

  /// The installed save has exactly the same files and bytes.
  final bool alreadyPresent;
  final Rpcs3SaveRejection? rejection;
  final String? technicalDetail;

  bool get accepted => rejection == null;
}

/// Staged, verified result of a prepare pass, waiting for [commit].
@immutable
class Rpcs3SaveImportPlan {
  Rpcs3SaveImportPlan._({
    required this.sourceKind,
    required this.sourceName,
    required this.stagingRoot,
    required List<Rpcs3SaveImportCandidate> candidates,
  }) : candidates = List.unmodifiable(candidates);

  final Rpcs3SaveImportSourceKind sourceKind;
  final String sourceName;

  /// `<Data>/dev_hdd0/home/00000001/.neostation-save-import-<ts>`, null
  /// when nothing was staged.
  final String? stagingRoot;
  final List<Rpcs3SaveImportCandidate> candidates;

  /// Accepted saves whose installed version differs; the user is asked
  /// once for all of them.
  List<Rpcs3SaveImportCandidate> get conflicts => [
    for (final candidate in candidates)
      if (candidate.accepted && candidate.conflictsWithInstalled) candidate,
  ];
}

/// Result of [Rpcs3SaveExchangeService.exportToFiles].
@immutable
class Rpcs3SaveExportResult {
  const Rpcs3SaveExportResult({
    required this.zipPath,
    required this.saveCount,
    required this.fileCount,
    required this.byteCount,
    required this.directories,
    required this.skipped,
    required this.otherUsersWithSaves,
  });

  final String zipPath;
  String get zipFileName => p.basename(zipPath);
  final int saveCount;
  final int fileCount;

  /// Uncompressed bytes of the exported files.
  final int byteCount;
  final List<String> directories;

  /// Folders of `savedata` that are not valid saves (rejected entries).
  final List<Rpcs3SaveImportEntry> skipped;

  /// Other valid RPCS3 user folders holding saves; the iOS Core only uses
  /// user `00000001`, so they are reported, not exported.
  final List<String> otherUsersWithSaves;
}

/// Runs a whole exchange under the RPCS3 busy guard.
typedef Rpcs3SaveExchangeGuard =
    Future<T> Function<T>(Future<T> Function() body);

/// Asked once per import when installed saves differ.
typedef Rpcs3SaveReplaceConfirmation =
    Future<bool> Function(List<Rpcs3SaveImportCandidate> conflicts);

/// Exports and imports PS3 game saves (savedata, not savestates) between
/// the live RPCS3 tree and the user.
///
/// The pinned iOS Core runs as user `00000001` and keeps its saves in
/// `<Data>/dev_hdd0/home/00000001/savedata/<DIR>/` as plain folders
/// (`PARAM.SFO`, icons, data files); `<Data>` is the support path passed to
/// the Core (`Rpcs3InternalService.dataDirectory()`). The path is resolved
/// at call time and refused when `Data/vfs.yml` redirects `dev_hdd0`.
///
/// Export writes one ZIP (`savedata/<DIR>/...`) in
/// `Documents/RPCS3/Export/Game Saves`, streamed to disk through a temporary
/// name. Import stages every candidate inside the user folder (same
/// volume), verifies it, then moves it into place with a single rename; a
/// replaced save is first moved to `NeoStation/RPCS3/SaveBackups`, outside
/// the Core tree and never deleted. Nothing is consumed or deleted in the
/// Files workspace, and the live tree is never touched by an export.
class Rpcs3SaveExchangeService {
  Rpcs3SaveExchangeService({
    required this.dataRoot,
    required this.backupRoot,
    required this.filesWorkspace,
    this.storageRedirection = Rpcs3RapLicenceService.storageRedirection,
    this.guard = Rpcs3InternalService.runSaveExchange,
    this.maxEntries = defaultMaxEntries,
    this.maxTotalBytes = defaultMaxTotalBytes,
    this.maxFileBytes = defaultMaxFileBytes,
    this.now = DateTime.now,
  });

  static const int defaultMaxEntries = 2000;
  static const int defaultMaxTotalBytes = 1 << 30;
  static const int defaultMaxFileBytes = 512 << 20;

  /// Labels of the default limits for messages (raw units).
  static const String defaultMaxTotalLabel = '1 GiB';
  static const String defaultMaxFileLabel = '512 MiB';

  static const String paramSfoName = 'PARAM.SFO';
  static const String savedataFolderName = 'savedata';

  /// Folder of [Rpcs3InternalService.rootDirectory] holding replaced saves.
  static const String backupFolderName = 'SaveBackups';

  /// Prefix of the staging folder created beside `savedata`.
  static const String stagingPrefix = '.neostation-save-import-';

  /// Files-visible folders, relative to `Documents/RPCS3`.
  static const String exportFolderName = 'Export/Game Saves';
  static const String importFolderName = 'Import/Game Saves';

  /// `RPCS3-saves-<yyyyMMdd-HHmmss>.zip`.
  static const String exportFilePrefix = 'RPCS3-saves-';

  /// RPCS3's `dirName` rule (`[A-Za-z0-9_-]`, 1 to 32 characters).
  static final RegExp directoryNamePattern = RegExp(r'^[A-Za-z0-9_\-]{1,32}$');

  /// Folder scan depth below a source root (`<X>/<Y>/<DIR>/PARAM.SFO`).
  static const int _folderScanDepth = 3;

  static final _log = LoggerService.instance;

  final Future<String> Function() dataRoot;
  final Future<String> Function() backupRoot;
  final Future<String> Function() filesWorkspace;
  final Future<String?> Function(String dataRoot) storageRedirection;
  final Rpcs3SaveExchangeGuard guard;
  final int maxEntries;
  final int maxTotalBytes;
  final int maxFileBytes;
  final DateTime Function() now;

  static Rpcs3SaveExchangeService? _instance;

  /// Production instance bound to NeoStation's RPCS3 folders.
  static Rpcs3SaveExchangeService get instance =>
      _instance ??= Rpcs3SaveExchangeService(
        dataRoot: () async => (await Rpcs3InternalService.dataDirectory()).path,
        backupRoot: () async => p.join(
          (await Rpcs3InternalService.rootDirectory()).path,
          backupFolderName,
        ),
        filesWorkspace: () async =>
            (await Rpcs3InternalService.filesWorkspaceDirectory()).path,
      );

  /// `<dataRoot>/dev_hdd0/home/00000001`.
  static String userHomePath(String dataRoot) => p.join(
    dataRoot,
    'dev_hdd0',
    'home',
    Rpcs3RapLicenceService.activeUserId,
  );

  /// `<dataRoot>/dev_hdd0/home/00000001/savedata`.
  static String savedataPath(String dataRoot) =>
      p.join(userHomePath(dataRoot), savedataFolderName);

  static bool isValidDirectoryName(String name) =>
      directoryNamePattern.hasMatch(name);

  /// `12.3 MB` style, decimal units like the Files app; never translated.
  static String formatBytes(int bytes) {
    if (bytes < 1000) return '$bytes B';
    const units = ['KB', 'MB', 'GB', 'TB'];
    var value = bytes.toDouble();
    var unit = -1;
    while (value >= 1000 && unit < units.length - 1) {
      value /= 1000;
      unit++;
    }
    final digits = value >= 100
        ? 0
        : value >= 10
        ? 1
        : 2;
    var text = value.toStringAsFixed(digits);
    if (text.contains('.')) {
      text = text.replaceFirst(RegExp(r'\.?0+$'), '');
    }
    return '$text ${units[unit]}';
  }

  // ---------------------------------------------------------------------
  // Export
  // ---------------------------------------------------------------------

  /// Writes every valid save of user `00000001` to a new ZIP in
  /// `Documents/RPCS3/Export/Game Saves` and returns its identity.
  Future<Rpcs3SaveExportResult> exportToFiles() async {
    final data = await dataRoot();
    final redirect = await storageRedirection(data);
    if (redirect != null) {
      throw Rpcs3SaveExchangeException(
        Rpcs3SaveExchangeFailure.storageRedirected,
        technicalDetail: redirect,
      );
    }
    final scan = await _scanInstalledSaves(savedataPath(data));
    if (scan.valid.isEmpty) {
      throw const Rpcs3SaveExchangeException(Rpcs3SaveExchangeFailure.noSaves);
    }

    final workspace = await filesWorkspace();
    final exportDir = Directory(p.join(workspace, 'Export', 'Game Saves'));
    await exportDir.create(recursive: true);
    final stamp = _localStamp(now());
    var zipName = '$exportFilePrefix$stamp.zip';
    var target = File(p.join(exportDir.path, zipName));
    for (var index = 2; await target.exists(); index++) {
      zipName = '$exportFilePrefix$stamp-$index.zip';
      target = File(p.join(exportDir.path, zipName));
    }
    final temp = File(p.join(exportDir.path, '.$zipName.part'));

    var fileCount = 0;
    var byteCount = 0;
    final encoder = ZipFileEncoder();
    var open = false;
    try {
      if (await temp.exists()) await temp.delete();
      encoder.create(temp.path, level: DeflateLevel.defaultCompression);
      open = true;
      for (final save in scan.valid) {
        final root = Directory(save.path);
        final entities = await root
            .list(recursive: true, followLinks: false)
            .toList();
        entities.sort((a, b) => a.path.compareTo(b.path));
        encoder.addArchiveFile(
          ArchiveFile.directory('$savedataFolderName/${save.name}'),
        );
        for (final entity in entities) {
          final relative = p.split(p.relative(entity.path, from: root.path));
          final archiveName =
              '$savedataFolderName/${save.name}/${relative.join('/')}';
          if (entity is Directory) {
            encoder.addArchiveFile(ArchiveFile.directory(archiveName));
          } else if (entity is File) {
            await encoder.addFile(entity, archiveName);
            fileCount++;
            byteCount += await entity.length();
          }
          // Links are never followed nor exported.
        }
      }
      await encoder.close();
      open = false;
      await temp.rename(target.path);
    } catch (error, stack) {
      _log.e('Rpcs3SaveExport failed', error: error, stackTrace: stack);
      if (open) {
        try {
          await encoder.close();
        } catch (_) {}
      }
      try {
        if (await temp.exists()) await temp.delete();
      } catch (_) {}
      throw Rpcs3SaveExchangeException(
        Rpcs3SaveExchangeFailure.exportWriteFailed,
        technicalDetail: _detail(error),
      );
    }

    final otherUsers = await _otherUsersWithSaves(data);
    _log.i(
      'Rpcs3SaveExport: ${scan.valid.length} save(s), $fileCount file(s), '
      '$byteCount byte(s) -> $zipName',
    );
    return Rpcs3SaveExportResult(
      zipPath: target.path,
      saveCount: scan.valid.length,
      fileCount: fileCount,
      byteCount: byteCount,
      directories: [for (final save in scan.valid) save.name],
      skipped: scan.skipped,
      otherUsersWithSaves: otherUsers,
    );
  }

  /// [exportToFiles] under the busy guard (no export while a game runs).
  Future<Rpcs3SaveExportResult> exportGuarded() => guard(exportToFiles);

  // ---------------------------------------------------------------------
  // Import: prepare (stage + verify), then commit (move into place)
  // ---------------------------------------------------------------------

  /// Stages the save folders and ZIP archives found in
  /// `Documents/RPCS3/Import/Game Saves` (nothing there is moved or
  /// deleted). Save folders are found up to three levels deep
  /// (`<DIR>`, `<X>/<DIR>`, `<X>/<Y>/<DIR>`), archives directly inside.
  Future<Rpcs3SaveImportPlan> prepareFromFilesFolder() async {
    final workspace = await filesWorkspace();
    final root = Directory(p.join(workspace, 'Import', 'Game Saves'));
    final sources = <_ImportSource>[];
    if (await root.exists()) {
      final children = await root.list(followLinks: false).toList();
      children.sort((a, b) => p.basename(a.path).compareTo(p.basename(b.path)));
      var hasFolder = false;
      for (final child in children) {
        if (child is Directory) {
          hasFolder = true;
        } else if (child is File &&
            p.basename(child.path).toLowerCase().endsWith('.zip')) {
          sources.add(_ImportSource.zip(child.path));
        }
      }
      if (hasFolder) {
        sources.insert(
          0,
          _ImportSource.folder(
            root.path,
            rootMayBeSave: false,
            maxDepth: _folderScanDepth,
          ),
        );
      }
    }
    if (sources.isEmpty) {
      throw const Rpcs3SaveExchangeException(
        Rpcs3SaveExchangeFailure.nothingFound,
      );
    }
    return _prepare(
      Rpcs3SaveImportSourceKind.filesFolder,
      sourceName: importFolderName,
      sources: sources,
      emptyMeansNothingFound: true,
    );
  }

  /// Stages every `<...>/<DIR>/PARAM.SFO` save of a ZIP archive.
  Future<Rpcs3SaveImportPlan> prepareFromZip(String zipPath) => _prepare(
    Rpcs3SaveImportSourceKind.zipFile,
    sourceName: p.basename(zipPath),
    sources: [_ImportSource.zip(zipPath)],
  );

  /// Stages the save folders of [folderPath]: the folder itself when it
  /// holds `PARAM.SFO`, otherwise its sub-folders up to three levels deep.
  Future<Rpcs3SaveImportPlan> prepareFromFolder(String folderPath) => _prepare(
    Rpcs3SaveImportSourceKind.folder,
    sourceName: p.basename(folderPath),
    sources: [
      _ImportSource.folder(
        folderPath,
        rootMayBeSave: true,
        maxDepth: _folderScanDepth,
      ),
    ],
  );

  Future<Rpcs3SaveImportPlan> _prepare(
    Rpcs3SaveImportSourceKind kind, {
    required String sourceName,
    required List<_ImportSource> sources,
    bool emptyMeansNothingFound = false,
  }) async {
    final data = await dataRoot();
    final redirect = await storageRedirection(data);
    if (redirect != null) {
      return Rpcs3SaveImportPlan._(
        sourceKind: kind,
        sourceName: sourceName,
        stagingRoot: null,
        candidates: [
          Rpcs3SaveImportCandidate._(
            name: sourceName,
            rejection: Rpcs3SaveRejection.storageRedirected,
            technicalDetail: redirect,
          ),
        ],
      );
    }

    final home = Directory(userHomePath(data));
    await _removeStaleStaging(home);
    await home.create(recursive: true);
    final stagingRoot = Directory(
      p.join(home.path, '$stagingPrefix${now().microsecondsSinceEpoch}'),
    );
    await stagingRoot.create();
    final installed = await _ExactNames.load(Directory(savedataPath(data)));

    final candidates = <Rpcs3SaveImportCandidate>[];
    final seen = <String>{};
    try {
      for (final source in sources) {
        if (source.zipPath != null) {
          await _stageZip(
            source.zipPath!,
            stagingRoot: stagingRoot.path,
            installed: installed,
            seen: seen,
            into: candidates,
          );
        } else {
          await _stageFolderSource(
            source,
            stagingRoot: stagingRoot.path,
            installed: installed,
            seen: seen,
            into: candidates,
          );
        }
      }
    } catch (error, stack) {
      _log.e('Rpcs3SaveImport staging failed', error: error, stackTrace: stack);
      await _deleteQuietly(stagingRoot);
      if (error is Rpcs3SaveExchangeException) rethrow;
      throw Rpcs3SaveExchangeException(
        Rpcs3SaveExchangeFailure.importWriteFailed,
        technicalDetail: _detail(error),
      );
    }

    if (candidates.isEmpty) {
      await _deleteQuietly(stagingRoot);
      if (emptyMeansNothingFound) {
        throw const Rpcs3SaveExchangeException(
          Rpcs3SaveExchangeFailure.nothingFound,
        );
      }
      candidates.add(
        Rpcs3SaveImportCandidate._(
          name: sourceName,
          rejection: Rpcs3SaveRejection.noSaveFound,
        ),
      );
    }
    final staged = candidates.any((candidate) => candidate.accepted);
    if (!staged) await _deleteQuietly(stagingRoot);
    return Rpcs3SaveImportPlan._(
      sourceKind: kind,
      sourceName: sourceName,
      stagingRoot: staged ? stagingRoot.path : null,
      candidates: candidates,
    );
  }

  /// Moves the staged saves of [plan] into `savedata`, in source order.
  ///
  /// An installed save with identical content is left untouched. A
  /// different installed save is replaced only when [replaceConflicts] is
  /// true: it is first moved to [backupRoot], then the staged folder is
  /// renamed into place. Everything left in the staging folder is removed.
  Future<Rpcs3SaveImportReport> commit(
    Rpcs3SaveImportPlan plan, {
    required bool replaceConflicts,
  }) async {
    final data = await dataRoot();
    final savedata = Directory(savedataPath(data));
    final entries = <Rpcs3SaveImportEntry>[];
    Object? preparationError;
    var prepared = false;

    Future<void> prepareTarget() async {
      if (prepared) {
        if (preparationError != null) throw preparationError!;
        return;
      }
      prepared = true;
      try {
        await savedata.create(recursive: true);
        final root = await Directory(data).resolveSymbolicLinks();
        final resolved = await savedata.resolveSymbolicLinks();
        if (!p.isWithin(root, resolved)) {
          throw FileSystemException(
            'savedata resolves outside the RPCS3 data folder',
            resolved,
          );
        }
      } catch (error) {
        preparationError = error;
        rethrow;
      }
    }

    try {
      for (final candidate in plan.candidates) {
        Rpcs3SaveImportEntry entry(
          Rpcs3SaveImportStatus status, {
          Rpcs3SaveRejection? rejection,
          String? detail,
          String? backup,
        }) => Rpcs3SaveImportEntry(
          name: candidate.name,
          title: candidate.title,
          status: status,
          rejection: rejection ?? candidate.rejection,
          technicalDetail: detail ?? candidate.technicalDetail,
          fileCount: candidate.fileCount,
          byteCount: candidate.byteCount,
          backupPath: backup,
        );

        if (!candidate.accepted) {
          entries.add(entry(Rpcs3SaveImportStatus.rejected));
          continue;
        }
        final staged = Directory(candidate.stagedPath!);
        if (candidate.alreadyPresent) {
          entries.add(entry(Rpcs3SaveImportStatus.alreadyPresent));
          await _deleteQuietly(staged);
          continue;
        }
        if (candidate.conflictsWithInstalled && !replaceConflicts) {
          entries.add(
            entry(
              Rpcs3SaveImportStatus.kept,
              rejection: Rpcs3SaveRejection.conflictKept,
            ),
          );
          await _deleteQuietly(staged);
          continue;
        }

        final target = Directory(p.join(savedata.path, candidate.name));
        try {
          await prepareTarget();
          String? backup;
          if (candidate.conflictsWithInstalled) {
            backup = await _backupExisting(target, candidate.name);
          }
          try {
            await staged.rename(target.path);
          } catch (_) {
            if (backup != null) {
              try {
                await Directory(backup).rename(target.path);
              } catch (restoreError) {
                _log.e(
                  'Rpcs3SaveImport[${candidate.name}] backup restore failed: '
                  '$restoreError',
                );
              }
            }
            rethrow;
          }
          entries.add(
            entry(
              candidate.conflictsWithInstalled
                  ? Rpcs3SaveImportStatus.replaced
                  : Rpcs3SaveImportStatus.imported,
              backup: backup,
            ),
          );
        } catch (error) {
          _log.w('Rpcs3SaveImport[${candidate.name}] install failed: $error');
          entries.add(
            entry(
              Rpcs3SaveImportStatus.rejected,
              rejection: Rpcs3SaveRejection.writeFailed,
              detail: _detail(error),
            ),
          );
          await _deleteQuietly(staged);
        }
      }
    } finally {
      final root = plan.stagingRoot;
      if (root != null) await _deleteQuietly(Directory(root));
    }

    final report = Rpcs3SaveImportReport(
      sourceKind: plan.sourceKind,
      sourceName: plan.sourceName,
      entries: entries,
    );
    _log.i('Rpcs3SaveImport (${plan.sourceKind.name}): ${report.logSummary}');
    for (final item in entries) {
      if (item.status == Rpcs3SaveImportStatus.rejected) {
        _log.i(
          'Rpcs3SaveImport rejected ${item.name}: ${item.rejection?.name}'
          '${item.technicalDetail == null ? '' : ' (${item.technicalDetail})'}',
        );
      }
    }
    return report;
  }

  /// Removes the staging folder of a plan that will not be committed.
  Future<void> discard(Rpcs3SaveImportPlan plan) async {
    final root = plan.stagingRoot;
    if (root != null) await _deleteQuietly(Directory(root));
  }

  /// Full import flow for the manager: picks the source when [kind] needs
  /// one, stages it (security scopes are released right after, before any
  /// dialog), asks [confirmReplace] once when installed saves differ, then
  /// installs. Returns null when a picker is cancelled. Runs under the
  /// busy guard from staging to installation.
  Future<Rpcs3SaveImportReport?> importGuarded(
    Rpcs3SaveImportSourceKind kind, {
    required Rpcs3SaveReplaceConfirmation confirmReplace,
  }) async {
    String? pickedPath;
    var cleanPickerCopies = false;
    switch (kind) {
      case Rpcs3SaveImportSourceKind.filesFolder:
        break;
      case Rpcs3SaveImportSourceKind.zipFile:
        final picked = await FilePicker.pickFiles(
          type: FileType.custom,
          allowedExtensions: const ['zip'],
          allowMultiple: false,
          withData: false,
        );
        if (picked == null || picked.files.isEmpty) return null;
        cleanPickerCopies = true;
        final file = picked.files.first;
        if (!file.name.toLowerCase().endsWith('.zip')) {
          throw Rpcs3SaveExchangeException(
            Rpcs3SaveExchangeFailure.notZip,
            technicalDetail: file.name,
          );
        }
        final path = file.path;
        if (path == null || !await File(path).exists()) {
          throw Rpcs3SaveExchangeException(
            Rpcs3SaveExchangeFailure.unreadable,
            technicalDetail: file.name,
          );
        }
        pickedPath = path;
      case Rpcs3SaveImportSourceKind.folder:
        final folder = await Rpcs3InternalBridge.pickGameFolderOpenInPlace();
        if (folder == null || folder.isEmpty) return null;
        pickedPath = folder;
    }

    try {
      return await guard(() async {
        final Rpcs3SaveImportPlan plan;
        try {
          plan = switch (kind) {
            Rpcs3SaveImportSourceKind.filesFolder =>
              await prepareFromFilesFolder(),
            Rpcs3SaveImportSourceKind.zipFile =>
              await prepareFromZip(pickedPath!),
            Rpcs3SaveImportSourceKind.folder =>
              await prepareFromFolder(pickedPath!),
          };
        } finally {
          if (kind == Rpcs3SaveImportSourceKind.folder) {
            await _releasePickerScopes();
          }
        }
        try {
          final conflicts = plan.conflicts;
          final replace =
              conflicts.isNotEmpty && await confirmReplace(conflicts);
          return await commit(plan, replaceConflicts: replace);
        } catch (_) {
          await discard(plan);
          rethrow;
        }
      });
    } finally {
      if (cleanPickerCopies) {
        try {
          await FilePicker.clearTemporaryFiles();
        } catch (error) {
          _log.w('Rpcs3SaveImport could not clear picker copies: $error');
        }
      }
    }
  }

  // ---------------------------------------------------------------------
  // ZIP source
  // ---------------------------------------------------------------------

  Future<void> _stageZip(
    String zipPath, {
    required String stagingRoot,
    required _ExactNames installed,
    required Set<String> seen,
    required List<Rpcs3SaveImportCandidate> into,
  }) async {
    final sourceName = p.basename(zipPath);
    void rejectSource(Rpcs3SaveRejection rejection, [String? detail]) {
      into.add(
        Rpcs3SaveImportCandidate._(
          name: sourceName,
          rejection: rejection,
          technicalDetail: detail,
        ),
      );
    }

    final InputFileStream input;
    try {
      input = InputFileStream(zipPath);
    } catch (error) {
      rejectSource(Rpcs3SaveRejection.unreadable, _detail(error));
      return;
    }
    try {
      final decoder = ZipDecoder();
      final Archive archive;
      try {
        archive = decoder.decodeStream(input);
      } catch (error) {
        rejectSource(Rpcs3SaveRejection.invalidArchive, _detail(error));
        return;
      }
      if (decoder.directory.filePosition < 0) {
        rejectSource(Rpcs3SaveRejection.invalidArchive, sourceName);
        return;
      }
      if (archive.length > maxEntries) {
        rejectSource(
          Rpcs3SaveRejection.tooManyEntries,
          '${archive.length} entries',
        );
        return;
      }
      var declaredTotal = 0;
      for (final entry in archive.files) {
        final unsafe = _unsafeEntryName(entry.name);
        if (unsafe != null) {
          rejectSource(Rpcs3SaveRejection.unsafeEntry, '$unsafe: ${entry.name}');
          return;
        }
        if (entry.isSymbolicLink || (entry.mode & 0xF000) == 0xA000) {
          rejectSource(Rpcs3SaveRejection.symbolicLink, entry.name);
          return;
        }
        if (entry.isFile) {
          if (entry.size > maxFileBytes) {
            rejectSource(
              Rpcs3SaveRejection.fileTooLarge,
              '${entry.name}: ${entry.size} bytes',
            );
            return;
          }
          declaredTotal += entry.size;
        }
      }
      if (declaredTotal > maxTotalBytes) {
        rejectSource(Rpcs3SaveRejection.tooLarge, '$declaredTotal bytes');
        return;
      }

      final files = archive.files;
      for (final sfoEntry in files) {
        if (sfoEntry.isDirectory) continue;
        final segments = sfoEntry.name.split('/');
        if (segments.first == '__MACOSX') continue;
        if (segments.last != paramSfoName) continue;
        if (segments.length < 2) {
          into.add(
            Rpcs3SaveImportCandidate._(
              name: paramSfoName,
              rejection: Rpcs3SaveRejection.invalidDirectoryName,
              technicalDetail: sfoEntry.name,
            ),
          );
          continue;
        }
        final dirName = segments[segments.length - 2];
        final base = segments.sublist(0, segments.length - 1).join('/');
        if (!isValidDirectoryName(dirName)) {
          into.add(
            Rpcs3SaveImportCandidate._(
              name: dirName,
              rejection: Rpcs3SaveRejection.invalidDirectoryName,
              technicalDetail: sfoEntry.name,
            ),
          );
          continue;
        }
        if (!seen.add(dirName)) {
          into.add(
            Rpcs3SaveImportCandidate._(
              name: dirName,
              rejection: Rpcs3SaveRejection.duplicateInSelection,
              technicalDetail: sfoEntry.name,
            ),
          );
          continue;
        }

        final Rpcs3ParamSfo descriptor;
        try {
          if (sfoEntry.size > Rpcs3ParamSfo.maxFileLength) {
            throw FormatException('PARAM.SFO is ${sfoEntry.size} bytes');
          }
          final bytes = sfoEntry.readBytes();
          if (bytes == null) throw const FormatException('PARAM.SFO unreadable');
          descriptor = Rpcs3ParamSfo.parse(bytes);
        } catch (error) {
          into.add(
            Rpcs3SaveImportCandidate._(
              name: dirName,
              rejection: Rpcs3SaveRejection.invalidParamSfo,
              technicalDetail: '${sfoEntry.name}: ${_detail(error)}',
            ),
          );
          continue;
        }

        into.add(
          await _stageArchiveSave(
            dirName: dirName,
            title: descriptor.title,
            base: '$base/',
            files: files,
            stagingRoot: stagingRoot,
            installed: installed,
          ),
        );
      }
    } finally {
      await input.close();
    }
  }

  Future<Rpcs3SaveImportCandidate> _stageArchiveSave({
    required String dirName,
    required String? title,
    required String base,
    required List<ArchiveFile> files,
    required String stagingRoot,
    required _ExactNames installed,
  }) async {
    final staged = Directory(p.join(stagingRoot, dirName));
    var fileCount = 0;
    var byteCount = 0;
    try {
      if (await staged.exists()) await staged.delete(recursive: true);
      await staged.create();
      for (final entry in files) {
        if (!entry.name.startsWith(base)) continue;
        final relative = entry.name.substring(base.length);
        if (relative.isEmpty) continue;
        final segments = relative.split('/')..removeWhere((s) => s.isEmpty);
        if (segments.isEmpty) continue;
        final target = p.joinAll([staged.path, ...segments]);
        if (entry.isDirectory) {
          await Directory(target).create(recursive: true);
          continue;
        }
        await Directory(p.dirname(target)).create(recursive: true);
        final output = _VerifyingOutput(
          OutputFileStream(target),
          maxBytes: maxFileBytes,
        );
        try {
          _inflateEntry(entry, output);
        } finally {
          await output.close();
        }
        final expectedCrc = entry.crc32;
        if (output.written != entry.size ||
            (expectedCrc != null && output.crc != expectedCrc)) {
          await _deleteQuietly(staged);
          return Rpcs3SaveImportCandidate._(
            name: dirName,
            title: title,
            rejection: Rpcs3SaveRejection.corruptData,
            technicalDetail:
                '${entry.name}: ${output.written}/${entry.size} bytes, '
                'crc ${output.crc.toRadixString(16)}/'
                '${expectedCrc?.toRadixString(16)}',
          );
        }
        fileCount++;
        byteCount += output.written;
      }
    } on _LimitExceeded catch (error) {
      await _deleteQuietly(staged);
      return Rpcs3SaveImportCandidate._(
        name: dirName,
        title: title,
        rejection: Rpcs3SaveRejection.corruptData,
        technicalDetail: error.toString(),
      );
    } on _UnsupportedEntry catch (error) {
      await _deleteQuietly(staged);
      return Rpcs3SaveImportCandidate._(
        name: dirName,
        title: title,
        rejection: Rpcs3SaveRejection.invalidArchive,
        technicalDetail: error.toString(),
      );
    } catch (error) {
      await _deleteQuietly(staged);
      return Rpcs3SaveImportCandidate._(
        name: dirName,
        title: title,
        rejection: Rpcs3SaveRejection.writeFailed,
        technicalDetail: _detail(error),
      );
    }
    return _finishStaged(
      dirName: dirName,
      title: title,
      staged: staged,
      fileCount: fileCount,
      byteCount: byteCount,
      installed: installed,
    );
  }

  // ---------------------------------------------------------------------
  // Folder sources (Files workspace, picked folder)
  // ---------------------------------------------------------------------

  Future<void> _stageFolderSource(
    _ImportSource source, {
    required String stagingRoot,
    required _ExactNames installed,
    required Set<String> seen,
    required List<Rpcs3SaveImportCandidate> into,
  }) async {
    final root = Directory(source.folderPath!);
    final List<({String name, String path})> found;
    try {
      found = await _findSaveFolders(
        root,
        rootMayBeSave: source.rootMayBeSave,
        maxDepth: source.maxDepth,
      );
    } catch (error) {
      into.add(
        Rpcs3SaveImportCandidate._(
          name: p.basename(root.path),
          rejection: Rpcs3SaveRejection.unreadable,
          technicalDetail: _detail(error),
        ),
      );
      return;
    }
    if (found.isEmpty && source.rootMayBeSave) {
      // A picked folder without any save is reported as such; the Files
      // root without any save is the whole-import refusal of the caller.
      into.add(
        Rpcs3SaveImportCandidate._(
          name: p.basename(root.path),
          rejection: Rpcs3SaveRejection.noSaveFound,
          technicalDetail: root.path,
        ),
      );
      return;
    }
    for (final save in found) {
      if (!isValidDirectoryName(save.name)) {
        into.add(
          Rpcs3SaveImportCandidate._(
            name: save.name,
            rejection: Rpcs3SaveRejection.invalidDirectoryName,
            technicalDetail: save.path,
          ),
        );
        continue;
      }
      if (!seen.add(save.name)) {
        into.add(
          Rpcs3SaveImportCandidate._(
            name: save.name,
            rejection: Rpcs3SaveRejection.duplicateInSelection,
            technicalDetail: save.path,
          ),
        );
        continue;
      }
      final Rpcs3ParamSfo descriptor;
      try {
        descriptor = await _readParamSfo(
          File(p.join(save.path, paramSfoName)),
        );
      } catch (error) {
        into.add(
          Rpcs3SaveImportCandidate._(
            name: save.name,
            rejection: Rpcs3SaveRejection.invalidParamSfo,
            technicalDetail: _detail(error),
          ),
        );
        continue;
      }
      into.add(
        await _stageFolderSave(
          dirName: save.name,
          title: descriptor.title,
          source: Directory(save.path),
          stagingRoot: stagingRoot,
          installed: installed,
        ),
      );
    }
  }

  Future<List<({String name, String path})>> _findSaveFolders(
    Directory root, {
    required bool rootMayBeSave,
    required int maxDepth,
  }) async {
    final result = <({String name, String path})>[];
    Future<bool> hasParamSfo(Directory dir) async {
      await for (final entity in dir.list(followLinks: false)) {
        if (entity is File && p.basename(entity.path) == paramSfoName) {
          return true;
        }
      }
      return false;
    }

    if (rootMayBeSave && await hasParamSfo(root)) {
      result.add((name: p.basename(root.path), path: root.path));
      return result;
    }

    Future<void> visit(Directory dir, int depth) async {
      final children = (await dir.list(followLinks: false).toList())
          .whereType<Directory>()
          .toList();
      children.sort((a, b) => p.basename(a.path).compareTo(p.basename(b.path)));
      for (final child in children) {
        if (await hasParamSfo(child)) {
          result.add((name: p.basename(child.path), path: child.path));
        } else if (depth < maxDepth) {
          await visit(child, depth + 1);
        }
      }
    }

    await visit(root, 1);
    return result;
  }

  Future<Rpcs3SaveImportCandidate> _stageFolderSave({
    required String dirName,
    required String? title,
    required Directory source,
    required String stagingRoot,
    required _ExactNames installed,
  }) async {
    final staged = Directory(p.join(stagingRoot, dirName));
    var fileCount = 0;
    var byteCount = 0;
    var entryCount = 0;
    Rpcs3SaveImportCandidate reject(
      Rpcs3SaveRejection rejection,
      String detail,
    ) => Rpcs3SaveImportCandidate._(
      name: dirName,
      title: title,
      rejection: rejection,
      technicalDetail: detail,
    );

    try {
      if (await staged.exists()) await staged.delete(recursive: true);
      await staged.create();
      await for (final entity in source.list(
        recursive: true,
        followLinks: false,
      )) {
        if (++entryCount > maxEntries) {
          await _deleteQuietly(staged);
          return reject(
            Rpcs3SaveRejection.tooManyEntries,
            'more than $maxEntries entries',
          );
        }
        final relative = p.split(p.relative(entity.path, from: source.path));
        final target = p.joinAll([staged.path, ...relative]);
        if (entity is Link) {
          await _deleteQuietly(staged);
          return reject(Rpcs3SaveRejection.symbolicLink, entity.path);
        }
        if (entity is Directory) {
          await Directory(target).create(recursive: true);
          continue;
        }
        if (entity is! File) continue;
        final length = await entity.length();
        if (length > maxFileBytes) {
          await _deleteQuietly(staged);
          return reject(
            Rpcs3SaveRejection.fileTooLarge,
            '${entity.path}: $length bytes',
          );
        }
        if (byteCount + length > maxTotalBytes) {
          await _deleteQuietly(staged);
          return reject(
            Rpcs3SaveRejection.tooLarge,
            'more than $maxTotalBytes bytes',
          );
        }
        await Directory(p.dirname(target)).create(recursive: true);
        final copied = await entity.copy(target);
        final copiedLength = await copied.length();
        if (copiedLength != length) {
          await _deleteQuietly(staged);
          return reject(
            Rpcs3SaveRejection.corruptData,
            '${entity.path}: $copiedLength/$length bytes',
          );
        }
        fileCount++;
        byteCount += length;
      }
    } catch (error) {
      await _deleteQuietly(staged);
      return reject(Rpcs3SaveRejection.writeFailed, _detail(error));
    }
    return _finishStaged(
      dirName: dirName,
      title: title,
      staged: staged,
      fileCount: fileCount,
      byteCount: byteCount,
      installed: installed,
    );
  }

  /// Re-checks PARAM.SFO after staging and compares with the installed save.
  Future<Rpcs3SaveImportCandidate> _finishStaged({
    required String dirName,
    required String? title,
    required Directory staged,
    required int fileCount,
    required int byteCount,
    required _ExactNames installed,
  }) async {
    try {
      await _readParamSfo(File(p.join(staged.path, paramSfoName)));
    } catch (error) {
      await _deleteQuietly(staged);
      return Rpcs3SaveImportCandidate._(
        name: dirName,
        title: title,
        rejection: Rpcs3SaveRejection.invalidParamSfo,
        technicalDetail: 'after staging: ${_detail(error)}',
      );
    }
    var conflicts = false;
    var alreadyPresent = false;
    if (installed.contains(dirName)) {
      final current = Directory(installed.pathOf(dirName));
      try {
        alreadyPresent = await _sameTree(staged, current);
      } catch (error) {
        _log.w('Rpcs3SaveImport[$dirName] installed save unreadable: $error');
      }
      conflicts = !alreadyPresent;
    }
    return Rpcs3SaveImportCandidate._(
      name: dirName,
      title: title,
      stagedPath: staged.path,
      fileCount: fileCount,
      byteCount: byteCount,
      conflictsWithInstalled: conflicts,
      alreadyPresent: alreadyPresent,
    );
  }

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------

  Future<({List<_InstalledSave> valid, List<Rpcs3SaveImportEntry> skipped})>
  _scanInstalledSaves(String savedataDir) async {
    final valid = <_InstalledSave>[];
    final skipped = <Rpcs3SaveImportEntry>[];
    final directory = Directory(savedataDir);
    if (!await directory.exists()) return (valid: valid, skipped: skipped);
    final entities = await directory.list(followLinks: false).toList();
    entities.sort((a, b) => p.basename(a.path).compareTo(p.basename(b.path)));
    for (final entity in entities) {
      final name = p.basename(entity.path);
      if (entity is Link) {
        skipped.add(
          Rpcs3SaveImportEntry(
            name: name,
            status: Rpcs3SaveImportStatus.rejected,
            rejection: Rpcs3SaveRejection.symbolicLink,
            technicalDetail: entity.path,
          ),
        );
        continue;
      }
      if (entity is! Directory) continue;
      if (!isValidDirectoryName(name)) {
        skipped.add(
          Rpcs3SaveImportEntry(
            name: name,
            status: Rpcs3SaveImportStatus.rejected,
            rejection: Rpcs3SaveRejection.invalidDirectoryName,
          ),
        );
        continue;
      }
      try {
        final names = await _ExactNames.load(entity);
        if (!names.contains(paramSfoName)) {
          throw const FormatException('PARAM.SFO is missing');
        }
        final descriptor = await _readParamSfo(File(names.pathOf(paramSfoName)));
        valid.add(
          _InstalledSave(name: name, path: entity.path, title: descriptor.title),
        );
      } catch (error) {
        skipped.add(
          Rpcs3SaveImportEntry(
            name: name,
            status: Rpcs3SaveImportStatus.rejected,
            rejection: Rpcs3SaveRejection.invalidParamSfo,
            technicalDetail: _detail(error),
          ),
        );
      }
    }
    return (valid: valid, skipped: skipped);
  }

  Future<List<String>> _otherUsersWithSaves(String data) async {
    final users = <String>[];
    final home = Directory(p.join(data, 'dev_hdd0', 'home'));
    if (!await home.exists()) return users;
    try {
      final entities = await home.list(followLinks: false).toList();
      entities.sort((a, b) => a.path.compareTo(b.path));
      for (final entity in entities) {
        final name = p.basename(entity.path);
        if (entity is! Directory ||
            name == Rpcs3RapLicenceService.activeUserId ||
            _checkUser(name) == 0) {
          continue;
        }
        final scan = await _scanInstalledSaves(
          p.join(entity.path, savedataFolderName),
        );
        if (scan.valid.isNotEmpty) users.add(name);
      }
    } catch (error) {
      _log.w('Rpcs3SaveExport could not list other users: $error');
    }
    return users;
  }

  /// `check_user` (`rpcs3/Emu/system_utils.cpp`): 8 characters whose
  /// leading digits parse to a non-zero number.
  static int _checkUser(String user) {
    if (user.length != 8) return 0;
    final digits = RegExp(r'^[0-9]+').firstMatch(user)?.group(0);
    if (digits == null) return 0;
    return int.parse(digits);
  }

  static Future<Rpcs3ParamSfo> _readParamSfo(File file) async {
    final stat = await file.stat();
    if (stat.type != FileSystemEntityType.file) {
      throw FileSystemException('PARAM.SFO is not a file', file.path);
    }
    if (stat.size > Rpcs3ParamSfo.maxFileLength) {
      throw FormatException('PARAM.SFO is ${stat.size} bytes', file.path);
    }
    return Rpcs3ParamSfo.parse(await file.readAsBytes());
  }

  /// Streams one archive entry into [output] chunk by chunk, so a header
  /// that lies about its size can neither fill the memory nor the disk:
  /// stored entries are copied, deflated entries go through dart:io's
  /// chunked inflater. Encrypted or otherwise compressed entries are not
  /// exports of a save and are refused.
  static void _inflateEntry(ArchiveFile entry, OutputStream output) {
    final content = entry.rawContent;
    if (content is! ZipFile) {
      entry.writeContent(output);
      return;
    }
    if ((content.flags & 0x1) != 0) {
      throw _UnsupportedEntry('${entry.name}: encrypted entry');
    }
    final raw = content.getStream(decompress: false);
    raw.reset();
    const chunkSize = 256 * 1024;
    try {
      switch (content.compressionMethod) {
        case CompressionType.none:
          while (!raw.isEOS) {
            final chunk = raw
                .readBytes(math.min(chunkSize, raw.length))
                .toUint8List();
            if (chunk.isEmpty) break;
            output.writeBytes(chunk);
          }
        case CompressionType.deflate:
          final sink = io.ZLibDecoder(
            raw: true,
          ).startChunkedConversion(_ChunkSink(output));
          while (!raw.isEOS) {
            final chunk = raw
                .readBytes(math.min(chunkSize, raw.length))
                .toUint8List();
            if (chunk.isEmpty) break;
            sink.add(chunk);
          }
          sink.close();
        default:
          throw _UnsupportedEntry(
            '${entry.name}: unsupported compression '
            '${content.compressionMethod.name}',
          );
      }
    } finally {
      raw.reset();
    }
  }

  /// Null when [name] can be extracted below a folder; otherwise why not.
  static String? _unsafeEntryName(String name) {
    if (name.isEmpty) return 'empty name';
    if (name.contains('\\')) return 'backslash';
    if (name.contains('\u0000')) return 'NUL character';
    if (name.startsWith('/')) return 'absolute path';
    if (RegExp(r'^[A-Za-z]:').hasMatch(name)) return 'drive letter';
    final segments = name.split('/');
    for (var index = 0; index < segments.length; index++) {
      final segment = segments[index];
      if (segment == '..') return 'parent reference';
      if (segment == '.') return 'current directory reference';
      if (segment.isEmpty && index != segments.length - 1) {
        return 'empty segment';
      }
    }
    return null;
  }

  /// Same relative file list, sizes and bytes (directories alone ignored).
  static Future<bool> _sameTree(Directory a, Directory b) async {
    Future<Map<String, int>> files(Directory root) async {
      final sizes = <String, int>{};
      await for (final entity in root.list(
        recursive: true,
        followLinks: false,
      )) {
        if (entity is File) {
          final relative = p.split(p.relative(entity.path, from: root.path));
          sizes[relative.join('/')] = await entity.length();
        }
      }
      return sizes;
    }

    final left = await files(a);
    final right = await files(b);
    if (left.length != right.length) return false;
    for (final entry in left.entries) {
      if (right[entry.key] != entry.value) return false;
    }
    for (final entry in left.entries) {
      final fileA = File(p.joinAll([a.path, ...entry.key.split('/')]));
      final fileB = File(p.joinAll([b.path, ...entry.key.split('/')]));
      if (!await _sameBytes(fileA, fileB)) return false;
    }
    return true;
  }

  static Future<bool> _sameBytes(File a, File b) async {
    final handleA = await a.open();
    try {
      final handleB = await b.open();
      try {
        const chunk = 64 * 1024;
        while (true) {
          final bytesA = await handleA.read(chunk);
          final bytesB = await handleB.read(chunk);
          if (bytesA.length != bytesB.length) return false;
          if (bytesA.isEmpty) return true;
          for (var index = 0; index < bytesA.length; index++) {
            if (bytesA[index] != bytesB[index]) return false;
          }
        }
      } finally {
        await handleB.close();
      }
    } finally {
      await handleA.close();
    }
  }

  Future<String> _backupExisting(Directory target, String name) async {
    final root = Directory(await backupRoot());
    await root.create(recursive: true);
    final stamp = _utcStamp(now().toUtc());
    var destination = Directory(p.join(root.path, '$name-$stamp'));
    for (var index = 2; await destination.exists(); index++) {
      destination = Directory(p.join(root.path, '$name-$stamp-$index'));
    }
    await target.rename(destination.path);
    return destination.path;
  }

  Future<void> _removeStaleStaging(Directory home) async {
    if (!await home.exists()) return;
    try {
      await for (final entity in home.list(followLinks: false)) {
        if (entity is Directory &&
            p.basename(entity.path).startsWith(stagingPrefix)) {
          await _deleteQuietly(entity);
        }
      }
    } catch (error) {
      _log.w('Rpcs3SaveImport could not clean stale staging: $error');
    }
  }

  static Future<void> _deleteQuietly(Directory directory) async {
    try {
      if (await directory.exists()) await directory.delete(recursive: true);
    } catch (error) {
      _log.w('Rpcs3SaveExchange could not delete ${directory.path}: $error');
    }
  }

  static Future<void> _releasePickerScopes() async {
    try {
      await Rpcs3InternalBridge.releaseScopedResources();
    } catch (error) {
      _log.w('Rpcs3SaveImport could not release picker scopes: $error');
    }
  }

  static String _two(int value) => value.toString().padLeft(2, '0');

  /// `yyyyMMdd-HHmmss` of a local time (export file names).
  static String _localStamp(DateTime time) =>
      '${time.year}${_two(time.month)}${_two(time.day)}-'
      '${_two(time.hour)}${_two(time.minute)}${_two(time.second)}';

  /// `yyyyMMdd-HHmmss` of a UTC time (backup folder names).
  static String _utcStamp(DateTime time) => _localStamp(time.toUtc());

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

class _ImportSource {
  const _ImportSource.zip(this.zipPath)
    : folderPath = null,
      rootMayBeSave = false,
      maxDepth = 0;

  const _ImportSource.folder(
    this.folderPath, {
    required this.rootMayBeSave,
    required this.maxDepth,
  }) : zipPath = null;

  final String? zipPath;
  final String? folderPath;
  final bool rootMayBeSave;
  final int maxDepth;
}

class _InstalledSave {
  const _InstalledSave({required this.name, required this.path, this.title});

  final String name;
  final String path;
  final String? title;
}

class _LimitExceeded implements Exception {
  const _LimitExceeded(this.limit);

  final int limit;

  @override
  String toString() => 'more than $limit bytes written for one file';
}

class _UnsupportedEntry implements Exception {
  const _UnsupportedEntry(this.detail);

  final String detail;

  @override
  String toString() => detail;
}

/// Forwards inflated chunks straight to the verifying output.
class _ChunkSink implements Sink<List<int>> {
  _ChunkSink(this._output);

  final OutputStream _output;

  @override
  void add(List<int> data) => _output.writeBytes(data);

  @override
  void close() {}
}

/// Counts and checksums what the archive really inflates, so a lying
/// header can neither fill the disk nor install truncated data.
class _VerifyingOutput extends OutputStream {
  _VerifyingOutput(this._inner, {required this.maxBytes})
    : super(byteOrder: _inner.byteOrder);

  final OutputFileStream _inner;
  final int maxBytes;
  int written = 0;
  int crc = 0;

  @override
  int get length => _inner.length;

  @override
  bool get isOpen => _inner.isOpen;

  @override
  void clear() => _inner.closeSync();

  @override
  void flush() => _inner.flush();

  @override
  Future<void> close() => _inner.close();

  @override
  void closeSync() => _inner.closeSync();

  void _count(int count) {
    written += count;
    if (written > maxBytes) throw _LimitExceeded(maxBytes);
  }

  @override
  void writeByte(int value) {
    _count(1);
    crc = getCrc32(<int>[value & 0xff], crc);
    _inner.writeByte(value);
  }

  @override
  void writeBytes(List<int> bytes, {int? length}) {
    final count = length ?? bytes.length;
    _count(count);
    crc = getCrc32(count == bytes.length ? bytes : bytes.sublist(0, count), crc);
    _inner.writeBytes(bytes, length: count);
  }

  @override
  void writeStream(InputStream stream) {
    var remaining = stream.length;
    while (remaining > 0) {
      final chunk = stream
          .readBytes(math.min(1024 * 1024, remaining))
          .toUint8List();
      if (chunk.isEmpty) break;
      writeBytes(chunk);
      remaining -= chunk.length;
    }
  }

  @override
  Uint8List subset(int start, [int? end]) => _inner.subset(start, end);
}

/// Exact (case-sensitive) names of one folder, as iOS's file system sees
/// them, so `bles01234-save` is never mistaken for `BLES01234-SAVE` on a
/// case-insensitive test host.
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
}
