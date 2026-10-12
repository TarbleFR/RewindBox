/// Executes a previewed cleanup plan (docs/storage-audit-cleanup.md § 3.8).
///
/// For each selected path: (1) it must be a candidate of the plan; (2) its
/// parent, resolved (`resolveSymbolicLinks()`), must be exactly where the scan
/// saw it inside a resolved root of the whitelist: a link anywhere below the
/// container is refused, and so are the roots themselves, the containers,
/// `Documents`, the library folders, the linked folder, the hidden library
/// folder, `Caches/NeoSwap*`, `dev_flash`, `exdata`, `savedata`,
/// `Libretro/System`, `ARMSX2/BIOS` and `StikJIT`; a path the registry
/// protects is refused, except the selectable duplicate copy of § 3.7;
/// (3) `lstat`: a link is refused; (4) a file whose size or modification time
/// differs from the preview is skipped (`changedSincePreview`); (5) deletion
/// file by file, then each directory with `Directory.delete(recursive:
/// false)` (`notEmpty` otherwise); ENOENT is tolerated (`skippedMissing`),
/// EACCES/EPERM are refused with the raw system text; (6) the session guard is
/// checked again before the start and every 50 files (a game launch, an
/// import, `StorageImportActivity`, or a library scan stops the rest), a
/// cancellation stops after the current file; (7) the Library caches go
/// through their API, never file by file; (8) the metadata rows after the
/// files, the guard checked again: `VACUUM INTO` copy, then the transaction
/// of [StorageMaintenanceRepository]; (9) a journal
/// `Documents/Diagnostics/storage-cleanup-<yyyyMMdd-HHmmss>.jsonl` (paths
/// relative to their container, never absolute), at most 20 of them.
///
/// RPCS3 candidates (INV-10, INV-16 … INV-19) run inside one
/// `Rpcs3InternalService.runSaveExchange(body)`: a refusal of the guard
/// (`gameRunning`, `libraryBusy`) refuses them all (`rpcs3Busy`); a
/// redirection of `dev_hdd0` by `Data/vfs.yml` refuses INV-16 … INV-19
/// (`redirected`).
///
/// Review of the storage services, before deleting: orphan media, covers
/// and metadata rows are checked again against a fresh read of the database
/// and of the library index ([StorageOrphanDetector.recheck]); a duplicate
/// goes only if the kept copy still has its size and modification time and
/// is another file (`dev:ino`); a 3DS staging folder goes only while no
/// 3DS pass is interrupted on the disk.
///
/// Never `FilePicker.clearTemporaryFiles()`, never a recursive deletion.
library;

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;

import '../../data/datasources/sqlite_service.dart';
import '../../repositories/storage_maintenance_repository.dart';
import '../diagnostics_directory.dart';
import '../library_http.dart';
import '../library_image_cache.dart';
import '../library_source_files.dart';
import '../rpcs3_internal_service.dart';
import '../rpcs3_rap_licence_service.dart';
import 'storage_cleanup_planner.dart';
import 'storage_orphan_detector.dart';
import 'storage_roots.dart';
import 'storage_scanner.dart';
import 'storage_stat_ffi.dart';

export 'storage_cleanup_planner.dart'
    show
        StorageCacheApi,
        StorageCandidateEntry,
        StorageCandidateSource,
        StorageCleanupCandidate,
        StorageCleanupLevel,
        StorageCleanupPlan,
        StoragePlanRefusal,
        StorageSessionGuard,
        StorageSessionState;

/// Why a path is not proposed or not deleted (§ 3.8). The catalog key of each
/// value is `StorageLocale.refusalKeys[reason.name]`; the planner re-exports
/// it for its refusals.
enum StorageRefusalReason {
  sessionActive,
  notInPlan,
  outsideWhitelist,
  isRoot,
  isProtected,
  isLink,
  changedSincePreview,
  accessDenied,
  notEmpty,
  cacheApiFailed,
  rpcs3Busy,
  redirected,
  unknown,

  /// The game library is being scanned (addition, review of the storage
  /// services): the whole cleanup is refused or stopped.
  libraryScanActive,

  /// The library database held a transaction of another operation: the
  /// metadata rows were left in place (addition, review of the storage
  /// services).
  databaseBusy,
}

/// Clears one Library cache through its API (INV-26).
typedef StorageCacheClearer = Future<void> Function(StorageCacheApi cache);

/// Runs [body] under the RPCS3 guard (`Rpcs3InternalService.runSaveExchange`).
typedef StorageRpcs3Guard = Future<void> Function(Future<void> Function() body);

/// What the deletion is doing.
enum StorageDeletionPhase { files, rpcs3, libraryCaches, metadata, done }

class StorageDeletionProgress {
  const StorageDeletionProgress({
    required this.done,
    required this.total,
    required this.deletedFiles,
    required this.deletedBytes,
    required this.phase,
    this.currentPath,
  });

  /// Operations done (files, caches, metadata) out of [total].
  final int done;
  final int total;
  final int deletedFiles;
  final int deletedBytes;
  final StorageDeletionPhase phase;

  /// `<Container>/relative` form of the entry just handled.
  final String? currentPath;
}

/// Outcome of [StorageDeletionManager.execute] (§ 3.8).
///
/// Additions: [deletedDirectories], [clearedCaches], [stoppedBySession],
/// [journalDisplayPath] and [journalError].
class StorageDeletionResult {
  const StorageDeletionResult({
    required this.deletedFiles,
    required this.deletedBytes,
    required this.skippedChanged,
    required this.skippedMissing,
    required this.refusals,
    this.metadata,
    required this.journalPath,
    required this.cancelled,
    this.deletedDirectories = 0,
    this.clearedCaches = const [],
    this.stoppedBySession = false,
    this.stopReason,
    this.journalDisplayPath,
    this.journalError,
  });

  final int deletedFiles;

  /// Bytes of the deleted files plus the bytes the cache APIs freed.
  final int deletedBytes;

  /// Files left in place: changed since the preview.
  final int skippedChanged;

  /// Files already gone (ENOENT).
  final int skippedMissing;
  final List<StoragePlanRefusal> refusals;
  final StorageMetadataDeletion? metadata;

  /// Absolute path of the journal (`''` when it could not be written).
  final String journalPath;
  final bool cancelled;
  final int deletedDirectories;
  final List<StorageCacheApi> clearedCaches;

  /// A game, an import or a library scan started: the rest was refused.
  final bool stoppedBySession;

  /// Why it stopped ([StorageRefusalReason.sessionActive] for a game or an
  /// import, [StorageRefusalReason.libraryScanActive] for a library scan);
  /// null when it did not.
  final StorageRefusalReason? stopReason;

  /// `<Documents>/Diagnostics/storage-cleanup-….jsonl`.
  final String? journalDisplayPath;

  /// Raw reason the journal could not be written, if any.
  final String? journalError;

  /// Refusals by reason.
  Map<StorageRefusalReason, int> get refusalCounts {
    final counts = <StorageRefusalReason, int>{};
    for (final refusal in refusals) {
      counts[refusal.reason] = (counts[refusal.reason] ?? 0) + 1;
    }
    return counts;
  }
}

/// Outcome of the checks of one path.
enum _Check { ok, missing, refused, changed }

class _Validation {
  const _Validation(
    this.outcome, {
    this.resolved,
    this.reason,
    this.detail,
    this.errorCode,
  });

  final _Check outcome;
  final String? resolved;
  final StorageRefusalReason? reason;
  final String? detail;
  final int? errorCode;
}

/// Stops the deletion: a game, an import or a library scan started.
class _SessionStop implements Exception {
  const _SessionStop();
}

/// The user cancelled.
class _Cancelled implements Exception {
  const _Cancelled();
}

class StorageDeletionManager {
  StorageDeletionManager({
    required StorageRootRegistry registry,
    required StorageSessionGuard guard,
    StorageStat? stat,
    Future<void> Function(String path)? deleteFile,
    Future<String> Function()? journalDirectory,
    DateTime Function()? now,
    this.journalLimit = 20,
    StorageRpcs3Guard? rpcs3Guard,
    Future<bool> Function()? rpcs3Redirected,
    StorageOrphanDetector? orphans,
  }) : _registry = registry,
       _guard = guard,
       _stat = stat,
       _deleteFile = deleteFile ?? _defaultDeleteFile,
       _journalDirectory = journalDirectory ?? _defaultJournalDirectory,
       _now = now ?? DateTime.now,
       _rpcs3Guard = rpcs3Guard ?? _defaultRpcs3Guard,
       _rpcs3Redirected = rpcs3Redirected,
       _orphans =
           orphans ??
           StorageOrphanDetector(
             database: () => SqliteService.instance.database,
             registry: registry,
           );

  final StorageRootRegistry _registry;
  final StorageSessionGuard _guard;
  final StorageStat? _stat;
  final Future<void> Function(String path) _deleteFile;
  final Future<String> Function() _journalDirectory;
  final DateTime Function() _now;
  final StorageRpcs3Guard _rpcs3Guard;
  final Future<bool> Function()? _rpcs3Redirected;

  /// Checks orphans again before they go (review of the storage services);
  /// by default the detector of the registry on `SqliteService`'s database.
  final StorageOrphanDetector _orphans;

  /// `storage-cleanup-*.jsonl` journals kept (the newest).
  final int journalLimit;

  /// Files between two checks of the session guard.
  static const int guardInterval = 50;

  /// `storage-cleanup-<yyyyMMdd-HHmmss>.jsonl` (`-<n>` when two runs share a
  /// second): the only files the journal cap ever removes.
  static final RegExp journalName = RegExp(
    r'^storage-cleanup-(\d{8}-\d{6})(?:-(\d+))?\.jsonl$',
  );

  static Future<void> _defaultDeleteFile(String path) => File(path).delete();

  static Future<void> _defaultRpcs3Guard(Future<void> Function() body) =>
      Rpcs3InternalService.runSaveExchange<void>(body);

  static Future<String> _defaultJournalDirectory() async =>
      (await DiagnosticsDirectory.directory()).path;

  static Future<void> _defaultClearLibraryCache(StorageCacheApi cache) =>
      switch (cache) {
        StorageCacheApi.libraryHttp => LibraryHttp.instance.clearCache(),
        StorageCacheApi.libraryImages => LibraryImageCache.instance.clear(),
      };

  /// `yyyyMMdd-HHmmss` of [time].
  static String stamp(DateTime time) {
    String two(int value) => value.toString().padLeft(2, '0');
    return '${time.year.toString().padLeft(4, '0')}${two(time.month)}'
        '${two(time.day)}-${two(time.hour)}${two(time.minute)}'
        '${two(time.second)}';
  }

  /// Deletes the [selectedPaths] of [plan] (and its orphan metadata rows
  /// when [StorageCleanupPlan.metadataSelectionKey] is selected), never
  /// anything else. Never throws for a path: every problem is a refusal.
  Future<StorageDeletionResult> execute(
    StorageCleanupPlan plan, {
    required Set<String> selectedPaths,
    StorageMaintenanceRepository? maintenance,
    StorageCacheClearer? clearLibraryCaches,
    void Function(StorageDeletionProgress)? onProgress,
    StorageScanCancelToken? cancel,
  }) => _Run(
    manager: this,
    plan: plan,
    selected: selectedPaths,
    maintenance: maintenance,
    clearCache: clearLibraryCaches ?? _defaultClearLibraryCache,
    onProgress: onProgress,
    cancel: cancel,
  ).run();
}

class _Run {
  _Run({
    required this.manager,
    required this.plan,
    required this.selected,
    required this.maintenance,
    required this.clearCache,
    required this.onProgress,
    required this.cancel,
  });

  final StorageDeletionManager manager;
  final StorageCleanupPlan plan;
  final Set<String> selected;
  final StorageMaintenanceRepository? maintenance;
  final StorageCacheClearer clearCache;
  final void Function(StorageDeletionProgress)? onProgress;
  final StorageScanCancelToken? cancel;

  StorageRootRegistry get registry => manager._registry;
  StorageContainers get containers => registry.containers;

  late final StorageStat _stat =
      manager._stat ??
      StorageStatFfi.tryLoad(probePath: containers.documents) ??
      const StorageStatLogical();

  StorageSessionState _state = const StorageSessionState();
  int _sinceCheck = 0;
  bool _stopped = false;
  bool _cancelled = false;

  /// Why the run stopped (a game or an import, or a library scan).
  StorageRefusalReason? _stopReason;

  /// What the stop refuses: the reason of the stop, `sessionActive` when
  /// unknown.
  StorageRefusalReason get _stopRefusal =>
      _stopReason ?? StorageRefusalReason.sessionActive;

  /// [StorageOrphanDetector.recheck] of the selected orphans, made before
  /// the files.
  StorageOrphanRecheck? _orphansNow;

  int _deletedFiles = 0;
  int _deletedBytes = 0;
  int _deletedDirectories = 0;
  int _skippedChanged = 0;
  int _skippedMissing = 0;
  int _done = 0;
  int _total = 0;
  StorageDeletionPhase _phase = StorageDeletionPhase.files;
  final List<StoragePlanRefusal> _refusals = [];
  final List<StorageCacheApi> _cleared = [];
  StorageMetadataDeletion? _metadata;

  IOSink? _journal;
  String _journalPath = '';
  String? _journalError;

  final Map<StorageContainer, String> _resolvedContainers = {};
  late final Set<String> _whitelist = {
    for (final root in registry.resolvedRootPaths) storageCanonicalPath(root),
  };

  // ---------------------------------------------------------------------
  // Journal
  // ---------------------------------------------------------------------

  String? _display(String? path) {
    if (path == null || path.isEmpty) return null;
    return containers.displayPathOf(path) ?? '<outside>';
  }

  /// [text] with every container path replaced by its placeholder (raw
  /// errors may quote absolute paths).
  String _sanitize(String text) {
    var result = text;
    final pairs = <(String, String)>[];
    for (final container in StorageContainer.values) {
      final placeholder = StorageContainers.placeholderOf(container);
      final raw = p.normalize(containers.pathOf(container));
      pairs.add((raw, placeholder));
      pairs.add((storageCanonicalPath(raw), placeholder));
      final resolved = _resolvedContainers[container];
      if (resolved != null) pairs.add((resolved, placeholder));
      if (raw.startsWith('/var/') || raw.startsWith('/tmp/')) {
        pairs.add(('/private$raw', placeholder));
      }
    }
    // Longest first: a container nested in another keeps its own name.
    pairs.sort((a, b) => b.$1.length.compareTo(a.$1.length));
    for (final (path, placeholder) in pairs) {
      if (path.length > 1) result = result.replaceAll(path, placeholder);
    }
    return result;
  }

  void _log(String op, Map<String, Object?> fields) {
    final sink = _journal;
    if (sink == null) return;
    final line = <String, Object?>{
      't': manager._now().toUtc().toIso8601String(),
      'op': op,
    };
    fields.forEach((key, value) {
      if (value == null) return;
      line[key] = value is String && key != 'path' ? _sanitize(value) : value;
    });
    try {
      sink.writeln(jsonEncode(line));
    } catch (error) {
      _journalError ??= _sanitize('$error');
    }
  }

  Future<void> _openJournal() async {
    try {
      final directory = await manager._journalDirectory();
      await Directory(directory).create(recursive: true);
      final base =
          'storage-cleanup-${StorageDeletionManager.stamp(manager._now())}';
      var file = File(p.join(directory, '$base.jsonl'));
      for (
        var index = 2;
        await FileSystemEntity.type(file.path, followLinks: false) !=
            FileSystemEntityType.notFound;
        index++
      ) {
        file = File(p.join(directory, '$base-$index.jsonl'));
      }
      _journal = file.openWrite();
      _journalPath = file.path;
    } catch (error) {
      _journal = null;
      _journalPath = '';
      _journalError = _sanitize('$error');
    }
  }

  /// Keeps the newest [StorageDeletionManager.journalLimit] journals; only
  /// this manager's own regular files are removed.
  Future<int> _pruneJournals() async {
    if (_journalPath.isEmpty) return 0;
    var removed = 0;
    try {
      final directory = Directory(p.dirname(_journalPath));
      final journals = <(String, int, String)>[];
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is! File) continue;
        final match = StorageDeletionManager.journalName.firstMatch(
          p.basename(entity.path),
        );
        if (match == null) continue;
        journals.add((
          match.group(1)!,
          int.tryParse(match.group(2) ?? '') ?? 1,
          entity.path,
        ));
      }
      journals.sort((a, b) {
        final byStamp = b.$1.compareTo(a.$1);
        return byStamp != 0 ? byStamp : b.$2.compareTo(a.$2);
      });
      final keep = manager.journalLimit < 1 ? 1 : manager.journalLimit;
      for (final old in journals.skip(keep)) {
        if (p.equals(old.$3, _journalPath)) continue;
        if (await FileSystemEntity.type(old.$3, followLinks: false) !=
            FileSystemEntityType.file) {
          continue;
        }
        try {
          await File(old.$3).delete();
          removed++;
        } on FileSystemException {
          // Kept: the cap is best effort.
        }
      }
    } catch (error) {
      _journalError ??= _sanitize('$error');
    }
    return removed;
  }

  Future<void> _closeJournal() async {
    final sink = _journal;
    _journal = null;
    if (sink == null) return;
    try {
      await sink.flush();
      await sink.close();
    } catch (error) {
      _journalError ??= _sanitize('$error');
    }
  }

  // ---------------------------------------------------------------------
  // Bookkeeping
  // ---------------------------------------------------------------------

  void _refuse(
    String path,
    StorageRefusalReason reason, {
    String? rootId,
    String? detail,
    int? errorCode,
  }) {
    final display = path == StorageCleanupPlan.metadataSelectionKey
        ? path
        : _display(path);
    _refusals.add(
      StoragePlanRefusal(
        path: path,
        reason: reason,
        displayPath: display,
        rootId: rootId,
        detail: detail,
        errorCode: errorCode,
      ),
    );
    _log('refuse', {
      'path': display,
      'reason': reason.name,
      'errno': errorCode,
      'detail': detail,
    });
  }

  void _progress([String? path]) {
    final listener = onProgress;
    if (listener == null) return;
    try {
      listener(
        StorageDeletionProgress(
          done: _done,
          total: _total,
          deletedFiles: _deletedFiles,
          deletedBytes: _deletedBytes,
          phase: _phase,
          currentPath: _display(path),
        ),
      );
    } catch (_) {
      // A failing listener never interrupts a deletion half-way.
    }
  }

  Future<void> _checkSession() async {
    try {
      _state = await manager._guard.check();
    } catch (error) {
      _state = StorageSessionState(
        launchActive: true,
        probeErrors: {'guard': '$error'},
      );
    }
    // A game launch, an import (review of 5d) or a library scan (review of
    // the storage services) stops the deletion.
    final reason = _state.wholeCleanupReason;
    if (reason != null && !_stopped) {
      _stopped = true;
      _stopReason = reason;
    }
  }

  /// After each file: cancellation, then the guard every 50 files.
  Future<void> _afterFile(StorageCleanupCandidate candidate) async {
    if (cancel?.isCancelled ?? false) {
      _cancelled = true;
      throw const _Cancelled();
    }
    _sinceCheck++;
    if (_sinceCheck >= StorageDeletionManager.guardInterval) {
      _sinceCheck = 0;
      await _checkSession();
      if (_stopped) throw const _SessionStop();
    }
  }

  bool _excludedNow(StorageCleanupCandidate candidate) =>
      (_state.libretroBusy &&
          StorageCleanupPlanner.libretroRootIds.contains(candidate.rootId)) ||
      (_state.dolphinMarker &&
          (StorageCleanupPlanner.dolphinRootIds.contains(candidate.rootId) ||
              candidate.ruleId == StorageCleanupPlanner.framePacingRuleId));

  // ---------------------------------------------------------------------
  // Path checks
  // ---------------------------------------------------------------------

  Future<String> _resolvedContainer(StorageContainer container) async {
    final cached = _resolvedContainers[container];
    if (cached != null) return cached;
    final path = containers.pathOf(container);
    String resolved;
    try {
      resolved = await Directory(path).resolveSymbolicLinks();
    } on FileSystemException {
      resolved = p.normalize(path);
    }
    _resolvedContainers[container] = resolved;
    return resolved;
  }

  static bool _within(String parent, String child) =>
      parent == child || p.isWithin(parent, child);

  /// Paths never deleted, whatever the plan says (§ 3.8 step 2), in the
  /// registry's namespace; null when [canonical] is none of them.
  StorageRefusalReason? _hardProtected(
    String canonical,
    StorageCleanupCandidate candidate,
  ) {
    String abs(StorageContainer container, String relative) =>
        storageCanonicalPath(registry.pathIn(container, relative));
    const documents = StorageContainer.documents;
    const support = StorageContainer.applicationSupport;
    for (final protected in [
      abs(
        documents,
        p.join(StorageLayout.documentsLibrary, LibrarySourceFiles.folderName),
      ),
      abs(documents, StorageLayout.libretroSystem),
      abs(documents, StorageLayout.armsx2Bios),
      abs(support, StorageLayout.stikjit),
    ]) {
      if (_within(protected, canonical)) {
        return StorageRefusalReason.isProtected;
      }
    }
    final caches = abs(StorageContainer.caches, '');
    if (p.isWithin(caches, canonical)) {
      final first = p.split(p.relative(canonical, from: caches)).first;
      if (first.startsWith('NeoSwap')) return StorageRefusalReason.isProtected;
    }
    final data = storageCanonicalPath(registry.rpcs3DataRoot);
    if (p.isWithin(data, canonical)) {
      final segments = p.split(p.relative(canonical, from: data));
      if (segments.first.startsWith(StorageLayout.rpcs3DevFlash)) {
        return StorageRefusalReason.isProtected;
      }
      // dev_hdd0/home/<user>/{exdata,savedata}, every user.
      if (segments.length >= 4 &&
          segments[0] == 'dev_hdd0' &&
          segments[1] == 'home' &&
          (segments[3] == 'exdata' || segments[3] == 'savedata')) {
        return StorageRefusalReason.isProtected;
      }
    }
    final folders = <String>[
      ...registry.libraryRoots,
      ?registry.linkedExternalFolder,
    ];
    for (final folder in folders) {
      final trimmed = folder.trim();
      if (trimmed.isEmpty) continue;
      final base = storageCanonicalPath(trimmed);
      if (base == canonical) return StorageRefusalReason.isRoot;
      if (p.isWithin(base, canonical) && !_duplicateException(candidate)) {
        return StorageRefusalReason.isProtected;
      }
    }
    return null;
  }

  /// The selectable duplicate copy of § 3.7: the only path of a never-class
  /// game folder a plan may delete.
  static bool _duplicateException(StorageCleanupCandidate candidate) =>
      candidate.source == StorageCandidateSource.duplicate &&
      candidate.kind == StorageEntryKind.file &&
      StorageCleanupPlanner.duplicateRootIds.contains(candidate.rootId);

  /// Steps 2 and 3 for [path] (the candidate itself or one of its entries);
  /// [expect] is the kind the preview saw.
  Future<_Validation> _validate(
    String path,
    StorageCleanupCandidate candidate,
    StorageEntryKind expect,
  ) async {
    final canonical = storageCanonicalPath(path);
    final container = containers.containerOf(path);
    final relative = containers.relativePathOf(path);
    if (container == null || relative == null) {
      return const _Validation(
        _Check.refused,
        reason: StorageRefusalReason.outsideWhitelist,
      );
    }
    if (relative.isEmpty ||
        registry.isContainerPath(path) ||
        registry.isRootPath(path)) {
      return const _Validation(
        _Check.refused,
        reason: StorageRefusalReason.isRoot,
      );
    }
    final hard = _hardProtected(canonical, candidate);
    if (hard != null) return _Validation(_Check.refused, reason: hard);
    final exception =
        _duplicateException(candidate) &&
        canonical == storageCanonicalPath(candidate.path);
    if (registry.isProtected(path) && !exception) {
      return const _Validation(
        _Check.refused,
        reason: StorageRefusalReason.isProtected,
      );
    }

    // Canonical containment: the parent must resolve exactly where the scan
    // listed it (the scanner never follows a link).
    final String resolvedParent;
    try {
      resolvedParent = await Directory(p.dirname(path)).resolveSymbolicLinks();
    } on FileSystemException catch (error) {
      final code = error.osError?.errorCode;
      if (code == 2) return const _Validation(_Check.missing, errorCode: 2);
      return _Validation(
        _Check.refused,
        reason: code == 13 || code == 1
            ? StorageRefusalReason.accessDenied
            : StorageRefusalReason.unknown,
        detail: error.osError?.toString() ?? error.message,
        errorCode: code,
      );
    }
    final base = await _resolvedContainer(container);
    final parentRelative = p.dirname(relative);
    final expected = parentRelative == '.'
        ? base
        : p.join(base, parentRelative);
    final resolved = p.join(resolvedParent, p.basename(path));
    final resolvedCanonical = storageCanonicalPath(resolved);
    final inWhitelist = _whitelist.any(
      (root) => p.isWithin(root, resolvedCanonical),
    );
    if (storageCanonicalPath(resolvedParent) !=
        storageCanonicalPath(expected)) {
      return _Validation(
        _Check.refused,
        reason: inWhitelist
            ? StorageRefusalReason.isLink
            : StorageRefusalReason.outsideWhitelist,
      );
    }
    if (!inWhitelist) {
      return const _Validation(
        _Check.refused,
        reason: StorageRefusalReason.outsideWhitelist,
      );
    }
    if (_whitelist.contains(resolvedCanonical)) {
      return const _Validation(
        _Check.refused,
        reason: StorageRefusalReason.isRoot,
      );
    }

    // lstat: a link is never deleted nor followed.
    final FileSystemEntityType type;
    try {
      type = await FileSystemEntity.type(resolved, followLinks: false);
    } on FileSystemException catch (error) {
      return _Validation(
        _Check.refused,
        reason: StorageRefusalReason.unknown,
        detail: error.osError?.toString() ?? error.message,
        errorCode: error.osError?.errorCode,
      );
    }
    if (type == FileSystemEntityType.notFound) {
      return const _Validation(_Check.missing, errorCode: 2);
    }
    final info = _stat.lstat(resolved);
    if (type == FileSystemEntityType.link || (info?.isLink ?? false)) {
      return const _Validation(
        _Check.refused,
        reason: StorageRefusalReason.isLink,
      );
    }
    final kindNow = type == FileSystemEntityType.directory
        ? StorageEntryKind.directory
        : type == FileSystemEntityType.file
        ? StorageEntryKind.file
        : null;
    if (kindNow != expect) {
      return _Validation(_Check.changed, resolved: resolved);
    }
    return _Validation(_Check.ok, resolved: resolved);
  }

  // ---------------------------------------------------------------------
  // Deletion
  // ---------------------------------------------------------------------

  void _logSkip(String path, String reason, {int? errorCode}) => _log('skip', {
    'path': _display(path),
    'reason': reason,
    'errno': errorCode,
  });

  /// One previewed file: checks, re-stat, deletion.
  Future<void> _deleteFileEntry(
    StorageCandidateEntry entry,
    StorageCleanupCandidate candidate,
  ) async {
    try {
      final check = await _validate(
        entry.path,
        candidate,
        StorageEntryKind.file,
      );
      switch (check.outcome) {
        case _Check.missing:
          _skippedMissing++;
          _logSkip(entry.path, 'missing', errorCode: 2);
          return;
        case _Check.changed:
          _skippedChanged++;
          _logSkip(entry.path, StorageRefusalReason.changedSincePreview.name);
          return;
        case _Check.refused:
          _refuse(
            entry.path,
            check.reason!,
            rootId: candidate.rootId,
            detail: check.detail,
            errorCode: check.errorCode,
          );
          return;
        case _Check.ok:
          break;
      }
      final resolved = check.resolved!;
      final FileStat stat;
      try {
        stat = await FileStat.stat(resolved);
      } on FileSystemException catch (error) {
        _failed(entry.path, candidate, error);
        return;
      }
      if (stat.type == FileSystemEntityType.notFound) {
        _skippedMissing++;
        _logSkip(entry.path, 'missing', errorCode: 2);
        return;
      }
      final modified = entry.modified;
      if (stat.size != entry.logicalBytes ||
          modified == null ||
          !stat.modified.isAtSameMomentAs(modified)) {
        _skippedChanged++;
        _logSkip(entry.path, StorageRefusalReason.changedSincePreview.name);
        return;
      }
      if (candidate.isDuplicate) {
        final paired = await _pairedCopyStillThere(candidate, resolved);
        if (paired != null) {
          _refuse(
            entry.path,
            StorageRefusalReason.changedSincePreview,
            rootId: candidate.rootId,
            detail: paired,
          );
          return;
        }
      }
      try {
        await manager._deleteFile(resolved);
      } on FileSystemException catch (error) {
        _failed(entry.path, candidate, error);
        return;
      }
      _deletedFiles++;
      _deletedBytes += stat.size;
      _log('delete', {'path': _display(entry.path), 'bytes': stat.size});
    } catch (error) {
      if (error is _SessionStop || error is _Cancelled) rethrow;
      _refuse(
        entry.path,
        StorageRefusalReason.unknown,
        rootId: candidate.rootId,
        detail: '$error',
      );
    } finally {
      _done++;
      _progress(entry.path);
    }
  }

  /// A deletion error: ENOENT is tolerated, EACCES/EPERM keep the raw text.
  void _failed(
    String path,
    StorageCleanupCandidate candidate,
    FileSystemException error,
  ) {
    final code = error.osError?.errorCode;
    if (code == 2) {
      _skippedMissing++;
      _logSkip(path, 'missing', errorCode: 2);
      return;
    }
    _refuse(
      path,
      code == 13 || code == 1
          ? StorageRefusalReason.accessDenied
          : StorageRefusalReason.unknown,
      rootId: candidate.rootId,
      detail: error.osError?.toString() ?? error.message,
      errorCode: code,
    );
  }

  /// Null while the copy the library uses is still a regular file of the
  /// same name at its place, with the size and modification time the
  /// analysis saw, and another file than the copy at [resolved] (another
  /// `dev:ino`: not a hard link, nor the same file under another case);
  /// otherwise the technical code of why the duplicate stays
  /// (`noReferencedCopy`, `notHashed`, `referencedCopyInvalid`,
  /// `referencedCopyMissing`, `referencedCopyChanged`, `sameFile`,
  /// `fileIdentityUnknown`, or the raw errno text).
  Future<String?> _pairedCopyStillThere(
    StorageCleanupCandidate candidate,
    String resolved,
  ) async {
    final paired = candidate.pairedPath;
    if (paired == null) return 'noReferencedCopy';
    // Only identical checksums make a duplicate (review of the storage
    // services).
    final digest = candidate.sha256;
    if (digest == null || digest.isEmpty) return 'notHashed';
    if (storageCanonicalPath(paired) == storageCanonicalPath(candidate.path) ||
        p.basename(paired) != p.basename(candidate.path)) {
      return 'referencedCopyInvalid';
    }
    try {
      if (await FileSystemEntity.type(paired, followLinks: false) !=
          FileSystemEntityType.file) {
        return 'referencedCopyMissing';
      }
      final stat = await FileStat.stat(paired);
      final modified = candidate.pairedModified;
      if (stat.size != (candidate.pairedLogicalBytes ?? -1) ||
          modified == null ||
          !stat.modified.isAtSameMomentAs(modified)) {
        return 'referencedCopyChanged';
      }
    } on FileSystemException catch (error) {
      return error.osError?.toString() ?? error.message;
    }
    // Without `lstat` (StorageStatLogical: every inode reads 0) the two
    // copies cannot be told apart: kept.
    if (!_stat.available) return 'fileIdentityUnknown';
    final mine = _stat.lstat(resolved);
    final kept = _stat.lstat(paired);
    if (mine == null || kept == null) return 'fileIdentityUnknown';
    if (mine.dev == kept.dev && mine.ino == kept.ino) return 'sameFile';
    return null;
  }

  static const Set<int> _notEmptyCodes = {39, 66, 17};

  /// Removes the directories of [candidate] (deepest first, its own last)
  /// once its files are gone; a directory still holding something stays.
  Future<void> _removeDirectories(StorageCleanupCandidate candidate) async {
    final kept = <String>[];
    for (final entry in candidate.entries) {
      if (entry.kind != StorageEntryKind.directory) continue;
      final canonical = storageCanonicalPath(entry.path);
      // A parent of a directory left in place cannot be empty.
      if (kept.any((child) => p.isWithin(canonical, child))) {
        kept.add(canonical);
        continue;
      }
      final check = await _validate(
        entry.path,
        candidate,
        StorageEntryKind.directory,
      );
      switch (check.outcome) {
        case _Check.missing:
          continue;
        case _Check.changed:
          kept.add(canonical);
          _logSkip(entry.path, StorageRefusalReason.changedSincePreview.name);
          continue;
        case _Check.refused:
          kept.add(canonical);
          _refuse(
            entry.path,
            check.reason!,
            rootId: candidate.rootId,
            detail: check.detail,
            errorCode: check.errorCode,
          );
          continue;
        case _Check.ok:
          break;
      }
      try {
        await Directory(check.resolved!).delete(recursive: false);
        _deletedDirectories++;
        _log('delete', {
          'path': _display(entry.path),
          'bytes': 0,
          'kind': 'directory',
        });
      } on FileSystemException catch (error) {
        final code = error.osError?.errorCode;
        if (code == 2) continue;
        kept.add(canonical);
        if (_notEmptyCodes.contains(code)) {
          _refuse(
            entry.path,
            StorageRefusalReason.notEmpty,
            rootId: candidate.rootId,
            detail: error.osError?.toString(),
            errorCode: code,
          );
        } else {
          _refuse(
            entry.path,
            code == 13 || code == 1
                ? StorageRefusalReason.accessDenied
                : StorageRefusalReason.unknown,
            rootId: candidate.rootId,
            detail: error.osError?.toString() ?? error.message,
            errorCode: code,
          );
        }
      }
    }
  }

  /// Why [candidate] may not go any more (review of the storage services),
  /// as a refusal and its raw detail; null when it may.
  Future<(StorageRefusalReason, String)?> _stillAllowed(
    StorageCleanupCandidate candidate,
  ) async {
    switch (candidate.source) {
      case StorageCandidateSource.orphanMedia:
      case StorageCandidateSource.orphanCover:
        final now = _orphansNow;
        final refused = now?.refused;
        if (now == null || refused != null) {
          return (
            StorageRefusalReason.changedSincePreview,
            refused ?? 'orphanRecheckMissing',
          );
        }
        final still = candidate.source == StorageCandidateSource.orphanMedia
            ? now.media
            : now.covers;
        if (!still.contains(storageCanonicalPath(candidate.path))) {
          return (StorageRefusalReason.changedSincePreview, 'noLongerOrphan');
        }
      case StorageCandidateSource.rule:
        if (candidate.ruleId == StorageCleanupPlanner.threeDsStagingRuleId) {
          final passes = await StorageCleanupPlanner.interrupted3dsPasses(
            registry,
          );
          if (passes == null) {
            return (
              StorageRefusalReason.isProtected,
              'threeDsBackupsUnreadable',
            );
          }
          if (passes.isNotEmpty) {
            return (StorageRefusalReason.isProtected, 'interrupted3dsPass');
          }
        }
      case StorageCandidateSource.duplicate:
      case StorageCandidateSource.cacheApi:
        break;
    }
    return null;
  }

  /// The selected orphans, checked again on a fresh read before any file
  /// goes.
  Future<void> _recheckOrphans(List<StorageCleanupCandidate> chosen) async {
    final media = <String>[];
    final covers = <String>[];
    for (final candidate in chosen) {
      if (candidate.source == StorageCandidateSource.orphanMedia) {
        media.add(candidate.path);
      } else if (candidate.source == StorageCandidateSource.orphanCover) {
        covers.add(candidate.path);
      }
    }
    if (media.isEmpty && covers.isEmpty) return;
    try {
      _orphansNow = await manager._orphans.recheck(
        media: media,
        covers: covers,
      );
    } catch (error) {
      _orphansNow = StorageOrphanRecheck(refused: 'recheck: $error');
    }
    _log('recheck', {
      'media': media.length,
      'stillMedia': _orphansNow!.media.length,
      'covers': covers.length,
      'stillCovers': _orphansNow!.covers.length,
      'detail': _orphansNow!.refused,
    });
  }

  /// Every file of [candidate], then its directories.
  Future<void> _deleteCandidate(StorageCleanupCandidate candidate) async {
    final files = [
      for (final entry in candidate.entries)
        if (entry.kind == StorageEntryKind.file) entry,
    ];
    final notAllowed = await _stillAllowed(candidate);
    if (notAllowed != null) {
      _done += files.length;
      _refuse(
        candidate.path,
        notAllowed.$1,
        rootId: candidate.rootId,
        detail: notAllowed.$2,
      );
      _progress(candidate.path);
      return;
    }
    if (_excludedNow(candidate)) {
      _done += files.length;
      _refuse(
        candidate.path,
        StorageRefusalReason.sessionActive,
        rootId: candidate.rootId,
      );
      _progress(candidate.path);
      return;
    }
    if (candidate.kind == StorageEntryKind.directory) {
      // The directory itself first: a refusal there covers its entries.
      final check = await _validate(
        candidate.path,
        candidate,
        StorageEntryKind.directory,
      );
      switch (check.outcome) {
        case _Check.missing:
          _skippedMissing += files.length;
          _done += files.length;
          _logSkip(candidate.path, 'missing', errorCode: 2);
          _progress(candidate.path);
          return;
        case _Check.changed:
          _skippedChanged += files.length;
          _done += files.length;
          _logSkip(
            candidate.path,
            StorageRefusalReason.changedSincePreview.name,
          );
          _progress(candidate.path);
          return;
        case _Check.refused:
          _done += files.length;
          _refuse(
            candidate.path,
            check.reason!,
            rootId: candidate.rootId,
            detail: check.detail,
            errorCode: check.errorCode,
          );
          _progress(candidate.path);
          return;
        case _Check.ok:
          break;
      }
    }
    for (var index = 0; index < files.length; index++) {
      await _deleteFileEntry(files[index], candidate);
      try {
        await _afterFile(candidate);
      } on _SessionStop {
        _done += files.length - index - 1;
        rethrow;
      }
      if (_excludedNow(candidate)) {
        // A session of this engine started: the rest of it stays.
        _done += files.length - index - 1;
        _refuse(
          candidate.path,
          StorageRefusalReason.sessionActive,
          rootId: candidate.rootId,
        );
        return;
      }
    }
    if (candidate.kind == StorageEntryKind.directory) {
      await _removeDirectories(candidate);
    }
  }

  /// Candidates handled so far (RPCS3 guard bookkeeping).
  final Set<StorageCleanupCandidate> _handled = {};

  /// Runs [candidates] in order; a session stop refuses the current one
  /// (whatever it still holds stays) and the rest.
  Future<void> _deleteAll(List<StorageCleanupCandidate> candidates) async {
    for (var index = 0; index < candidates.length; index++) {
      if (!_cancelled && (cancel?.isCancelled ?? false)) _cancelled = true;
      if (_stopped || _cancelled) {
        _refuseRest(candidates.sublist(index));
        return;
      }
      final candidate = candidates[index];
      _handled.add(candidate);
      try {
        await _deleteCandidate(candidate);
      } on _SessionStop {
        _refuseRest(candidates.sublist(index));
        return;
      } on _Cancelled {
        return;
      } catch (error) {
        _refuse(
          candidate.path,
          StorageRefusalReason.unknown,
          rootId: candidate.rootId,
          detail: '$error',
        );
      }
    }
  }

  /// After a session stop: the remaining candidates are refused (the
  /// reason of the stop); after a cancellation they are simply not done.
  void _refuseRest(List<StorageCleanupCandidate> rest) {
    if (_cancelled) return;
    for (final candidate in rest) {
      _refuse(candidate.path, _stopRefusal, rootId: candidate.rootId);
    }
  }

  Future<bool> _rpcs3RedirectedNow() async {
    if (registry.rpcs3Redirected || plan.rpcs3Redirected) return true;
    final probe = manager._rpcs3Redirected;
    try {
      if (probe != null) return await probe();
      return await Rpcs3RapLicenceService.storageRedirection(
            registry.rpcs3DataRoot,
          ) !=
          null;
    } catch (_) {
      // An unreadable redirection keeps every RPCS3 root untouched.
      return true;
    }
  }

  /// The RPCS3 candidates, inside one `runSaveExchange`.
  Future<void> _deleteRpcs3(List<StorageCleanupCandidate> candidates) async {
    if (candidates.isEmpty || _stopped || _cancelled) {
      _refuseRest(candidates);
      return;
    }
    _phase = StorageDeletionPhase.rpcs3;
    var guarded = candidates;
    if (await _rpcs3RedirectedNow()) {
      guarded = [];
      for (final candidate in candidates) {
        if (StorageRootRegistry.rpcs3RootIds.contains(candidate.rootId)) {
          _done += candidate.fileCount;
          _refuse(
            candidate.path,
            StorageRefusalReason.redirected,
            rootId: candidate.rootId,
          );
        } else {
          guarded.add(candidate);
        }
      }
      if (guarded.isEmpty) return;
    }
    try {
      await manager._rpcs3Guard(() => _deleteAll(guarded));
    } catch (error) {
      // Refused by the guard before the body (gameRunning, libraryBusy, a
      // Core state other than stopped/ready): nothing of RPCS3 was touched.
      final detail = error is Rpcs3InternalException ? error.code : '$error';
      for (final candidate in guarded) {
        if (_handled.contains(candidate)) continue;
        _done += candidate.fileCount;
        _refuse(
          candidate.path,
          StorageRefusalReason.rpcs3Busy,
          rootId: candidate.rootId,
          detail: detail,
        );
      }
    }
  }

  /// Logical bytes and regular files below [path] (links never followed).
  static Future<(int, int)> _measure(String path) async {
    var bytes = 0;
    var files = 0;
    try {
      if (await FileSystemEntity.type(path, followLinks: false) !=
          FileSystemEntityType.directory) {
        return (0, 0);
      }
      final stack = <Directory>[Directory(path)];
      while (stack.isNotEmpty) {
        final directory = stack.removeLast();
        try {
          await for (final entity in directory.list(followLinks: false)) {
            if (entity is Directory) {
              stack.add(entity);
            } else if (entity is File) {
              try {
                bytes += (await entity.stat()).size;
                files++;
              } on FileSystemException {
                // Gone meanwhile.
              }
            }
          }
        } on FileSystemException {
          // Unreadable: not counted.
        }
      }
    } on FileSystemException {
      return (bytes, files);
    }
    return (bytes, files);
  }

  /// Step 7: the Library caches through their API.
  Future<void> _clearCaches(List<StorageCleanupCandidate> candidates) async {
    if (candidates.isEmpty) return;
    _phase = StorageDeletionPhase.libraryCaches;
    for (final candidate in candidates) {
      if (_stopped || _cancelled) {
        if (!_cancelled) {
          _refuse(candidate.path, _stopRefusal, rootId: candidate.rootId);
        }
        continue;
      }
      try {
        final check = await _validate(
          candidate.path,
          candidate,
          StorageEntryKind.directory,
        );
        if (check.outcome == _Check.missing) {
          _logSkip(candidate.path, 'missing', errorCode: 2);
          continue;
        }
        if (check.outcome == _Check.refused) {
          _refuse(
            candidate.path,
            check.reason!,
            rootId: candidate.rootId,
            detail: check.detail,
            errorCode: check.errorCode,
          );
          continue;
        }
        if (check.outcome == _Check.changed) {
          _refuse(
            candidate.path,
            StorageRefusalReason.changedSincePreview,
            rootId: candidate.rootId,
          );
          continue;
        }
        final before = await _measure(check.resolved!);
        try {
          await clearCache(candidate.cacheApi!);
        } catch (error) {
          _refuse(
            candidate.path,
            StorageRefusalReason.cacheApiFailed,
            rootId: candidate.rootId,
            detail: '$error',
          );
          continue;
        }
        final after = await _measure(check.resolved!);
        final freed = before.$1 > after.$1 ? before.$1 - after.$1 : 0;
        final removed = before.$2 > after.$2 ? before.$2 - after.$2 : 0;
        _deletedBytes += freed;
        _deletedFiles += removed;
        _cleared.add(candidate.cacheApi!);
        _log('delete', {
          'path': _display(candidate.path),
          'bytes': freed,
          'files': removed,
          'api': candidate.cacheApi!.name,
        });
      } finally {
        _done++;
        _progress(candidate.path);
      }
    }
  }

  /// Step 8: the orphan metadata rows, after the files: the guard checked
  /// again (a library scan rewrites `user_roms`), then the keys still
  /// orphan on a fresh read (review of the storage services).
  Future<void> _deleteMetadata() async {
    const token = StorageCleanupPlan.metadataSelectionKey;
    if (!selected.contains(token) || plan.metadataKeys.isEmpty) return;
    _phase = StorageDeletionPhase.metadata;
    if (_cancelled) return;
    if (!_stopped) await _checkSession();
    if (_stopped) {
      _refuse(token, _stopRefusal);
      return;
    }
    StorageOrphanRecheck now;
    try {
      now = await manager._orphans.recheck(metadata: plan.metadataKeys);
    } catch (error) {
      now = StorageOrphanRecheck(refused: 'recheck: $error');
    }
    final refusedNow = now.refused;
    if (refusedNow != null) {
      _refuse(
        token,
        StorageRefusalReason.changedSincePreview,
        detail: refusedNow,
      );
      _log('metadata', {'error': refusedNow});
      _done++;
      _progress();
      return;
    }
    final keys = [
      for (final key in plan.metadataKeys)
        if (now.metadata.contains(key)) key,
    ];
    final repository = maintenance ?? StorageMaintenanceRepository();
    String? version;
    try {
      version = await repository.sqliteVersion();
    } catch (_) {
      version = null;
    }
    try {
      if (keys.isEmpty) {
        _metadata = StorageMetadataDeletion(
          deleted: 0,
          skippedNotOrphan: plan.metadataKeys.length,
          backupPath: '',
        );
        _log('metadata', {
          'deleted': 0,
          'skippedNotOrphan': plan.metadataKeys.length,
          'keys': plan.metadataKeys.length,
          'sqlite': version,
        });
        return;
      }
      final String backup;
      try {
        backup = await repository.backupBeforeDeletion();
      } on StorageMaintenanceBusy catch (error) {
        _refuse(token, StorageRefusalReason.databaseBusy, detail: error.reason);
        _log('metadata', {'error': error.reason, 'sqlite': version});
        return;
      } catch (error) {
        _refuse(
          token,
          StorageRefusalReason.unknown,
          detail: 'backupFailed: $error',
        );
        _log('metadata', {'error': 'backupFailed: $error', 'sqlite': version});
        return;
      }
      try {
        final deletion = await repository.deleteOrphanMetadata(keys);
        _metadata = StorageMetadataDeletion(
          deleted: deletion.deleted,
          skippedNotOrphan:
              deletion.skippedNotOrphan +
              plan.metadataKeys.length -
              keys.length,
          backupPath: deletion.backupPath,
        );
        _log('metadata', {
          'deleted': deletion.deleted,
          'skippedNotOrphan': _metadata!.skippedNotOrphan,
          'keys': plan.metadataKeys.length,
          'backup': _display(
            deletion.backupPath.isEmpty ? backup : deletion.backupPath,
          ),
          'sqlite': version,
        });
      } on StorageMaintenanceBusy catch (error) {
        // Another operation's transaction was open: nothing was written.
        _refuse(token, StorageRefusalReason.databaseBusy, detail: error.reason);
        _log('metadata', {
          'error': error.reason,
          'backup': _display(backup),
          'sqlite': version,
        });
      } catch (error) {
        // The transaction rolled back: no row was removed.
        _refuse(token, StorageRefusalReason.unknown, detail: '$error');
        _log('metadata', {
          'error': '$error',
          'backup': _display(backup),
          'sqlite': version,
        });
      }
    } finally {
      _done++;
      _progress();
    }
  }

  Future<StorageDeletionResult> run() async {
    await _openJournal();
    // Step 1: the selection, restricted to the plan.
    final chosen = <StorageCleanupCandidate>[];
    final notInPlan = <String>[];
    final seen = <String>{};
    for (final path in selected) {
      if (path == StorageCleanupPlan.metadataSelectionKey) continue;
      final candidate = plan.candidateFor(path);
      if (candidate == null) {
        notInPlan.add(path);
        continue;
      }
      if (seen.add(storageCanonicalPath(candidate.path))) {
        chosen.add(candidate);
      }
    }
    final metadataSelected =
        selected.contains(StorageCleanupPlan.metadataSelectionKey) &&
        plan.metadataKeys.isNotEmpty;
    // Descendants before their ancestors (a separate candidate may lie
    // inside a directory candidate).
    chosen.sort(
      (a, b) => p.split(b.path).length.compareTo(p.split(a.path).length),
    );
    final caches = [
      for (final candidate in chosen)
        if (candidate.cacheApi != null) candidate,
    ];
    final rpcs3 = [
      for (final candidate in chosen)
        if (candidate.cacheApi == null &&
            StorageCleanupPlanner.rpcs3GuardedRootIds.contains(
              candidate.rootId,
            ))
          candidate,
    ];
    final files = [
      for (final candidate in chosen)
        if (candidate.cacheApi == null &&
            !StorageCleanupPlanner.rpcs3GuardedRootIds.contains(
              candidate.rootId,
            ))
          candidate,
    ];
    _total =
        [...files, ...rpcs3].fold(0, (sum, c) => sum + c.fileCount) +
        caches.length +
        (metadataSelected ? 1 : 0);

    // Step 6: the guard before the start.
    if (cancel?.isCancelled ?? false) _cancelled = true;
    await _checkSession();
    _log('begin', {
      'level': plan.level.name,
      'candidates': plan.candidates.length,
      'selected': chosen.length,
      'metadataKeys': metadataSelected ? plan.metadataKeys.length : 0,
      'launchActive': _state.launchActive,
      'importActive': _state.importActive,
      'libraryScanActive': _state.libraryScanActive,
      'libretroActive': _state.libretroActive,
      'libretroUnfinishedJournal': _state.libretroUnfinishedJournal,
      'dolphinMarker': _state.dolphinMarker,
    });
    for (final path in notInPlan) {
      _refuse(path, StorageRefusalReason.notInPlan);
    }
    if (_stopped) {
      for (final candidate in chosen) {
        _refuse(candidate.path, _stopRefusal, rootId: candidate.rootId);
      }
      if (metadataSelected) {
        _refuse(StorageCleanupPlan.metadataSelectionKey, _stopRefusal);
      }
    } else if (!_cancelled) {
      _progress();
      await _recheckOrphans(chosen);
      await _deleteAll(files);
      await _deleteRpcs3(rpcs3);
      await _clearCaches(caches);
      await _deleteMetadata();
    }

    _phase = StorageDeletionPhase.done;
    // Every operation is now done or refused.
    if (!_cancelled) _done = _total;
    final pruned = await _pruneJournals();
    _log('end', {
      'deletedFiles': _deletedFiles,
      'deletedBytes': _deletedBytes,
      'deletedDirectories': _deletedDirectories,
      'skippedChanged': _skippedChanged,
      'skippedMissing': _skippedMissing,
      'refusals': _refusals.length,
      'cancelled': _cancelled,
      'stoppedBySession': _stopped,
      'prunedJournals': pruned,
    });
    await _closeJournal();
    _progress();
    return StorageDeletionResult(
      deletedFiles: _deletedFiles,
      deletedBytes: _deletedBytes,
      skippedChanged: _skippedChanged,
      skippedMissing: _skippedMissing,
      refusals: List.unmodifiable(_refusals),
      metadata: _metadata,
      journalPath: _journalPath,
      cancelled: _cancelled,
      deletedDirectories: _deletedDirectories,
      clearedCaches: List.unmodifiable(_cleared),
      stoppedBySession: _stopped,
      stopReason: _stopped ? _stopRefusal : null,
      journalDisplayPath: _journalPath.isEmpty ? null : _display(_journalPath),
      journalError: _journalError,
    );
  }
}
