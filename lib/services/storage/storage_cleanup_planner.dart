/// Cleanup planner (docs/storage-audit-cleanup.md § 3.7): turns a scan and its
/// orphan report into the candidates of one cleanup level. Read-only: nothing
/// is deleted, nothing is written; [StorageDeletionManager] executes a plan.
///
/// - Level 1 « Sûr » (preselected): picker copies in `tmp/` and
///   `tmp/*-Inbox/` (regular files, idle for at least one hour), the SoLoud
///   temporary files, the Dolphin frame-pacing file without the Dolphin
///   marker, `*.part` older than one hour, `user-data/temp/**`,
///   `Skins/.staging/*` older than one hour, `background.importing*`,
///   `RPCS3/Imports/*.PUP` older than one hour, `.neostation-save-import-*`,
///   `KartPad/Runtime/GameData.{import,rollback}-*`, the 3DS staging folders,
///   `Caches/Libretro/Content/*`, `dev_hdd0/tmp/*` and the music player's
///   metadata copies older than 10 minutes (decision of the lead). A folder
///   of `tmp/` other than `*-Inbox` is never proposed (unknown content).
/// - Level 2 « Régénérable » (preselected, with warnings): level 1, the two
///   Library caches (through their API, one candidate each), the libretro
///   skin caches and catalogs, `Dolphin/ShaderCache`, `RPCS3/Cache`, orphan
///   media, orphan metadata rows, orphan covers, Dolphin session logs and
///   KartPad logs beyond the 10 newest, recovered Dolphin markers, the
///   google_fonts copies, `Caches/<bundle-id>/` and the KartPad and
///   Dusklight cache folders `Caches/{KartPad,Dusklight}/*` (decision of the
///   lead).
/// - Level 3 « Avec confirmation détaillée » (nothing preselected, not even
///   its level-1 and level-2 candidates nor the metadata rows: each item is
///   ticked one by one, review of 5d): level 2, `Documents/Diagnostics/*`,
///   the native logs at the Documents root, Dolphin recordings, RPCS3 save
///   exports, `Libretro/Logs/*`, `user-data/app.log.old` (decision of the
///   lead: level 3), `dolphin-persistent.jsonl`, `RPCS3/Data/dev_hdd1`,
///   `KartPad/Runtime/GameData` and the duplicate copies the library does
///   not use whose checksums equal the kept copy's. The backups NeoStation
///   makes before a replacement (RPCS3 saves and licences, 3DS system data,
///   the copies of data.sqlite) are never proposed (review of the storage
///   services).
///
/// Ages are idle times from the later of the modification and the status
/// change (`FileStat.changed`) of an entry and of everything below it:
/// file_picker's copies keep the original modification time, their status
/// change is the copy itself (review of 5d).
///
/// Session guards: nothing while a game runs (`GameLaunchManager().isActive`),
/// an import runs (`StorageImportActivity`) or the game library is scanned;
/// the libretro roots (INV-14, INV-25) while a libretro session is declared
/// or its journal is unfinished; the Dolphin roots (INV-20 … INV-22) and the
/// frame-pacing file while the Dolphin marker exists; every RPCS3 root
/// (INV-16 … INV-19) while `Data/vfs.yml` redirects `dev_hdd0`; the 3DS
/// staging folders while a pass is interrupted on the disk or the walk of
/// INV-14 was cut. Excluded candidates are listed as refusals.
library;

import 'dart:async';
import 'dart:collection';
import 'dart:io';
import 'dart:typed_data';

import 'package:libretro_internal_bridge/libretro_internal_bridge.dart';
import 'package:path/path.dart' as p;

import '../../l10n/storage_locale.dart';
import '../game_launch_manager.dart';
import '../libretro_3ds_system_data_service.dart';
import 'storage_categorizer.dart';
import 'storage_deletion_manager.dart' show StorageRefusalReason;
import 'storage_import_activity.dart';
import 'storage_orphan_detector.dart';
import 'storage_roots.dart';
import 'storage_scanner.dart';

// Declared with the deletion manager (§ 3.8), shared by the plan refusals.
export 'storage_deletion_manager.dart' show StorageRefusalReason;

/// The three cleanup levels; each includes the lower ones.
enum StorageCleanupLevel { safe, regenerable, confirmed }

/// Where a candidate comes from (addition to § 3.7).
enum StorageCandidateSource {
  /// A line of the level table, from the scan's classification.
  rule,

  /// `StorageOrphanReport.media` (level 2).
  orphanMedia,

  /// `StorageOrphanReport.libraryCovers` (level 2).
  orphanCover,

  /// `StorageDuplicateCopy.selectable` (level 3): the only candidate inside a
  /// never-class game folder (§ 3.7, « copie non référencée seule »).
  duplicate,

  /// A Library cache cleared through its API, never file by file (INV-26).
  cacheApi,
}

/// The two Library caches of INV-26.
enum StorageCacheApi {
  /// `Caches/Library/library_http`: `LibraryHttp.instance.clearCache()`.
  libraryHttp,

  /// `Caches/Library/library_images`: `LibraryImageCache.instance.clear()`.
  libraryImages,
}

/// One file or directory a candidate will delete, as previewed.
class StorageCandidateEntry {
  const StorageCandidateEntry({
    required this.path,
    required this.kind,
    required this.logicalBytes,
    this.allocatedBytes,
    this.modified,
  });

  /// Absolute path, as scanned.
  final String path;

  /// [StorageEntryKind.file] or [StorageEntryKind.directory].
  final StorageEntryKind kind;
  final int logicalBytes;
  final int? allocatedBytes;

  /// `FileStat.modified` at the scan; a file is deleted only if it still has
  /// this size and this modification time.
  final DateTime? modified;
}

/// One proposed deletion (§ 3.7).
///
/// Additions to § 3.7 (documented deviations): [level], [source], [rootId],
/// [ruleId], [container], [relativePath], [fileCount], [cacheApi],
/// [entries] and [pairedDisplayPath].
class StorageCleanupCandidate {
  const StorageCleanupCandidate({
    required this.path,
    required this.kind,
    required this.logicalBytes,
    this.allocatedBytes,
    required this.modified,
    required this.category,
    required this.deletionClass,
    required this.reasonKey,
    this.warningKeys = const [],
    required this.preselected,
    this.pairedPath,
    this.engine,
    required this.level,
    required this.source,
    required this.rootId,
    this.ruleId,
    required this.container,
    required this.relativePath,
    required this.fileCount,
    this.cacheApi,
    this.entries = const [],
    this.pairedDisplayPath,
    this.pairedLogicalBytes,
    this.pairedModified,
    this.sha256,
  });

  /// Absolute path, as scanned: the selection key of the preview.
  final String path;

  /// [StorageEntryKind.file] or [StorageEntryKind.directory].
  final StorageEntryKind kind;

  /// Bytes of the files this candidate deletes ([entries]); the scanned
  /// size of the cache for [StorageCandidateSource.cacheApi].
  final int logicalBytes;

  /// Null when allocated sizes are unavailable (logical fallback).
  final int? allocatedBytes;

  /// Newest modification of the candidate and of everything below it.
  final DateTime modified;
  final StorageCategory category;

  /// Class of the path; [StorageDeletionClass.confirmation] for a duplicate
  /// copy (the exception of § 3.7 to its never-class folder).
  final StorageDeletionClass deletionClass;

  /// `StorageLocale` key: the category key (`catTemporary`, `catCaches`, …)
  /// for rule candidates, `orphanMedia`, `orphanCovers` or `duplicates` for
  /// the analysis candidates (their `{count}`/`{size}` are those of the
  /// candidates sharing the key in the preview).
  final String reasonKey;

  /// `StorageLocale` keys of the warnings (`rpcs3CacheWarning`, …).
  final List<String> warningKeys;

  /// Ticked when the preview opens: the candidates of a level-1 or level-2
  /// plan but its level-3 ones; nothing in a level-3 plan, where each item
  /// is ticked one by one (review of 5d).
  final bool preselected;

  /// Duplicate only: the copy the library references, which is kept.
  final String? pairedPath;
  final StorageEngine? engine;

  /// The level that proposes it.
  final StorageCleanupLevel level;
  final StorageCandidateSource source;

  /// Root (`INV-xx`) owning the path.
  final String rootId;
  final String? ruleId;
  final StorageContainer container;

  /// Relative to [container].
  final String relativePath;

  /// Regular files among [entries].
  final int fileCount;

  /// Set for [StorageCandidateSource.cacheApi] only.
  final StorageCacheApi? cacheApi;

  /// What the deletion manager deletes, in order: the regular files, then
  /// the directories deepest first (the candidate's own directory last).
  /// Entries classified never, links, unreadable entries and the entries of
  /// a separate candidate below this one are never listed: a directory
  /// holding one of them stays (`notEmpty`). Empty for a cache API.
  final List<StorageCandidateEntry> entries;

  /// `<Container>/relative` form of [pairedPath].
  final String? pairedDisplayPath;

  /// Duplicate only (review of the storage services): size and
  /// modification time of the kept copy at the analysis — the deletion
  /// refuses when either changed since.
  final int? pairedLogicalBytes;
  final DateTime? pairedModified;

  /// Duplicate only: the SHA-256 both copies share (a duplicate is offered
  /// only once the checksums proved the copies identical).
  final String? sha256;

  /// `<Documents>/a/b` form of [path].
  String get displayPath {
    final placeholder = StorageContainers.placeholderOf(container);
    return relativePath.isEmpty ? placeholder : '$placeholder/$relativePath';
  }

  bool get isDuplicate => source == StorageCandidateSource.duplicate;

  @override
  String toString() =>
      'StorageCleanupCandidate($displayPath, ${level.name}, '
      '${source.name}, $logicalBytes B)';
}

/// A path the plan does not propose, or the deletion manager did not delete,
/// and why.
///
/// Additions to § 3.7: [displayPath], [rootId], [detail] (raw technical text,
/// never translated: errno text, RPCS3 code, …) and [errorCode] (errno).
class StoragePlanRefusal {
  const StoragePlanRefusal({
    required this.path,
    required this.reason,
    this.displayPath,
    this.rootId,
    this.detail,
    this.errorCode,
  });

  /// Absolute path; [wholePlan] when the refusal covers everything.
  final String path;
  final StorageRefusalReason reason;

  /// `<Container>/relative` form of [path] (never an absolute path).
  final String? displayPath;
  final String? rootId;
  final String? detail;
  final int? errorCode;

  /// [path] of a refusal that covers the whole plan (a game, an import or
  /// a library scan is running).
  static const String wholePlan = '';

  /// `StorageLocale` key of [reason].
  String get localeKey =>
      StorageLocale.refusalKeys[reason.name] ?? StorageLocale.refuseUnknown;

  @override
  String toString() =>
      'StoragePlanRefusal(${displayPath ?? path}, ${reason.name}'
      '${detail == null ? '' : ', $detail'})';
}

/// The candidates of one level (§ 3.7).
///
/// Additions: [containers], [session], [rpcs3Redirected] and the selection
/// helpers. The constructor is not `const` (lookup tables are cached).
class StorageCleanupPlan {
  StorageCleanupPlan({
    required this.level,
    required this.builtAt,
    required this.candidates,
    required this.metadataKeys,
    required this.refusals,
    required this.containers,
    this.session = const StorageSessionState(),
    this.rpcs3Redirected = false,
  });

  final StorageCleanupLevel level;
  final DateTime builtAt;

  /// Sorted by root (inventory order), level, then path.
  final List<StorageCleanupCandidate> candidates;

  /// Orphan `user_screenscraper_metadata` keys (levels 2 and 3), deleted
  /// only when [metadataSelectionKey] is selected.
  final List<StorageOrphanMetadataKey> metadataKeys;
  final List<StoragePlanRefusal> refusals;
  final StorageContainers containers;

  /// Session state the plan was built with.
  final StorageSessionState session;

  /// `Data/vfs.yml` redirects `dev_hdd0`: no RPCS3 candidate (INV-16 … 19).
  final bool rpcs3Redirected;

  /// Selection token of the orphan metadata rows: they are deleted only when
  /// the selection holds it (never a filesystem path).
  static const String metadataSelectionKey =
      'storage-metadata:user_screenscraper_metadata';

  late final Map<String, StorageCleanupCandidate> _byPath = {
    for (final candidate in candidates)
      storageCanonicalPath(candidate.path): candidate,
  };

  /// Logical bytes of every candidate.
  int get bytes =>
      candidates.fold(0, (sum, candidate) => sum + candidate.logicalBytes);

  /// Logical bytes of the preselected candidates.
  int get preselectedBytes => bytesOf(preselectedPaths);

  /// A game, an import or a library scan is running: nothing is proposed.
  bool get blocked => session.wholeCleanupRefused;

  bool get hasMetadata => metadataKeys.isNotEmpty;

  /// Level 2 preselects the metadata rows; level 3 preselects nothing, its
  /// metadata rows included (review of phase 5d).
  bool get metadataPreselected =>
      hasMetadata && level == StorageCleanupLevel.regenerable;

  bool get isEmpty => candidates.isEmpty && metadataKeys.isEmpty;

  /// Initial selection of the preview: the candidates and metadata rows of a
  /// level-1 or level-2 plan; empty at level 3.
  Set<String> get preselectedPaths => {
    for (final candidate in candidates)
      if (candidate.preselected) candidate.path,
    if (metadataPreselected) metadataSelectionKey,
  };

  /// The candidate of [path] (`/private/var` = `/var`), if any.
  StorageCleanupCandidate? candidateFor(String path) =>
      _byPath[storageCanonicalPath(path)];

  /// Logical bytes of the candidates of [selection].
  int bytesOf(Iterable<String> selection) {
    var total = 0;
    for (final path in {...selection}) {
      total += candidateFor(path)?.logicalBytes ?? 0;
    }
    return total;
  }

  /// Number of selected candidates (and the metadata rows as one item).
  int countOf(Iterable<String> selection) {
    var count = 0;
    for (final path in {...selection}) {
      if (path == metadataSelectionKey) {
        if (hasMetadata) count++;
      } else if (candidateFor(path) != null) {
        count++;
      }
    }
    return count;
  }

  /// Warnings of the selected candidates, for the confirmation dialog
  /// (`metadataBackupNote` when the metadata rows are selected).
  List<String> warningKeysOf(Iterable<String> selection) {
    final keys = <String>{};
    for (final path in {...selection}) {
      if (path == metadataSelectionKey) {
        if (hasMetadata) keys.add(StorageLocale.metadataBackupNote);
        continue;
      }
      keys.addAll(candidateFor(path)?.warningKeys ?? const []);
    }
    return keys.toList();
  }

  /// Candidates grouped by root, in inventory order.
  Map<String, List<StorageCleanupCandidate>> get candidatesByRoot {
    final groups = <String, List<StorageCleanupCandidate>>{};
    for (final candidate in candidates) {
      groups.putIfAbsent(candidate.rootId, () => []).add(candidate);
    }
    return groups;
  }
}

/// What the session guards saw (§ 3.7).
class StorageSessionState {
  const StorageSessionState({
    this.launchActive = false,
    this.libretroActive = false,
    this.dolphinMarker = false,
    this.libretroUnfinishedJournal = false,
    this.importActive = false,
    this.libraryScanActive = false,
    this.probeErrors = const {},
  });

  /// `GameLaunchManager().isActive`: nothing is cleaned.
  final bool launchActive;

  /// The game library is being scanned (`SqliteConfigProvider.isScanning`,
  /// `isScanningRoms`, `isSilentScanning`; addition, review of the storage
  /// services): the scan rewrites `user_roms` and holds transactions on the
  /// database — nothing is cleaned.
  final bool libraryScanActive;

  /// `StorageImportActivity.active` (addition, review of 5d): an import runs
  /// between its Files pick and the end of its processing; nothing is
  /// cleaned.
  final bool importActive;

  /// `LibretroInternalBridge.isSessionActive()` (true when the probe fails).
  final bool libretroActive;

  /// `Support/NeoStation/Dolphin/CrashMarkers/active-session.json` exists
  /// (or could not be checked).
  final bool dolphinMarker;

  /// `Documents/Libretro/Logs/session.log` declares a session without its
  /// `END ` line in its last 4 KiB (or could not be read).
  final bool libretroUnfinishedJournal;

  /// Raw errors of the probes that failed (each failure counts as busy).
  final Map<String, String> probeErrors;

  /// INV-14 and INV-25 are excluded.
  bool get libretroBusy => libretroActive || libretroUnfinishedJournal;

  /// A game, an import or a library scan runs: the whole plan is refused
  /// and a deletion stops.
  bool get wholeCleanupRefused =>
      launchActive || importActive || libraryScanActive;

  /// Why the whole cleanup is refused: [StorageRefusalReason.sessionActive]
  /// for a game or an import, [StorageRefusalReason.libraryScanActive] for
  /// a library scan alone; null when it is not.
  StorageRefusalReason? get wholeCleanupReason => launchActive || importActive
      ? StorageRefusalReason.sessionActive
      : libraryScanActive
      ? StorageRefusalReason.libraryScanActive
      : null;

  bool get anyActive =>
      launchActive ||
      importActive ||
      libraryScanActive ||
      libretroBusy ||
      dolphinMarker;

  @override
  String toString() =>
      'StorageSessionState(launch: $launchActive, import: $importActive, '
      'libraryScan: $libraryScanActive, libretro: $libretroActive, '
      'journal: $libretroUnfinishedJournal, dolphin: $dolphinMarker)';
}

/// The session guards of planning and execution (§ 3.7). Each probe is
/// injectable; a probe that fails counts as busy (never an unknown state).
///
/// Addition: [containers] gives the marker and journal paths without
/// `path_provider` (the screens pass `registry.containers`); [importActive]
/// (review of 5d) is `StorageImportActivity.active` by default, read last so
/// an import started during the other probes counts; [libraryScanActive]
/// (review of the storage services) reads the library provider's scan
/// state — the screens pass it. Without it nobody can tell that no scan
/// runs: the guard then counts one (fail closed).
class StorageSessionGuard {
  StorageSessionGuard({
    bool Function()? launchActive,
    Future<bool> Function()? libretroActive,
    Future<bool> Function()? dolphinMarkerPresent,
    Future<bool> Function()? libretroJournalUnfinished,
    bool Function()? importActive,
    bool Function()? libraryScanActive,
    StorageContainers? containers,
  }) : _launchActive = launchActive ?? _gameLaunchActive,
       _libretroActive =
           libretroActive ?? LibretroInternalBridge.isSessionActive,
       _dolphinMarkerPresent = dolphinMarkerPresent,
       _libretroJournalUnfinished = libretroJournalUnfinished,
       _importActive = importActive ?? _importRunning,
       _libraryScanActive = libraryScanActive ?? _libraryScanUnknown,
       _containers = containers;

  final bool Function() _launchActive;
  final bool Function() _importActive;
  final bool Function() _libraryScanActive;
  final Future<bool> Function() _libretroActive;
  final Future<bool> Function()? _dolphinMarkerPresent;
  final Future<bool> Function()? _libretroJournalUnfinished;
  final StorageContainers? _containers;
  StorageContainers? _resolved;

  /// Bytes of `session.log` searched for the END line
  /// (`LibretroSessionJournal.m`, `JournalHasEnd`).
  static const int journalTail = 4096;

  static bool _gameLaunchActive() => GameLaunchManager().isActive;

  static bool _importRunning() => StorageImportActivity.active;

  /// No library scan probe was given: a scan cannot be ruled out.
  static bool _libraryScanUnknown() =>
      throw StateError('no library scan probe');

  Future<StorageContainers> _paths() async =>
      _containers ?? (_resolved ??= await StorageContainers.resolve());

  Future<StorageSessionState> check() async {
    final errors = <String, String>{};
    var launch = true;
    try {
      launch = _launchActive();
    } catch (error) {
      errors['launchActive'] = '$error';
    }
    Future<bool> probe(String name, Future<bool> Function() body) async {
      try {
        return await body();
      } catch (error) {
        errors[name] = '$error';
        return true;
      }
    }

    final libretro = await probe('libretroActive', _libretroActive);
    final marker = await probe(
      'dolphinMarker',
      _dolphinMarkerPresent ??
          () async => markerPresent(
            p.join(
              (await _paths()).applicationSupport,
              StorageLayout.dolphinActiveMarker,
            ),
          ),
    );
    final journal = await probe(
      'libretroJournal',
      _libretroJournalUnfinished ??
          () async => journalUnfinished(
            p.join(
              (await _paths()).documents,
              StorageLayout.libretroSessionLog,
            ),
          ),
    );
    var scanning = true;
    try {
      scanning = _libraryScanActive();
    } catch (error) {
      errors['libraryScanActive'] = '$error';
    }
    var importing = true;
    try {
      importing = _importActive();
    } catch (error) {
      errors['importActive'] = '$error';
    }
    return StorageSessionState(
      launchActive: launch,
      libretroActive: libretro,
      dolphinMarker: marker,
      libretroUnfinishedJournal: journal,
      importActive: importing,
      libraryScanActive: scanning,
      probeErrors: Map.unmodifiable(errors),
    );
  }

  /// The Dolphin marker exists at [path] (any kind of entry; a failure to
  /// check counts as present).
  static Future<bool> markerPresent(String path) async {
    try {
      return await FileSystemEntity.type(path, followLinks: false) !=
          FileSystemEntityType.notFound;
    } catch (_) {
      return true;
    }
  }

  /// The libretro journal at [path] declares a session without its END line
  /// in its last [journalTail] bytes. Absent or empty: false; unreadable:
  /// true.
  static Future<bool> journalUnfinished(String path) async {
    RandomAccessFile? handle;
    try {
      final type = await FileSystemEntity.type(path, followLinks: false);
      if (type == FileSystemEntityType.notFound) return false;
      handle = await File(path).open();
      final length = await handle.length();
      if (length <= 0) return false;
      final start = length > journalTail ? length - journalTail : 0;
      await handle.setPosition(start);
      final tail = await handle.read(length - start);
      return !journalTailHasEnd(tail);
    } catch (_) {
      return true;
    } finally {
      try {
        await handle?.close();
      } catch (_) {}
    }
  }

  static final Uint8List _endMarker = Uint8List.fromList('\nEND '.codeUnits);

  /// Whether [tail] holds `\nEND ` (the marker `JournalHasEnd` searches).
  static bool journalTailHasEnd(List<int> tail) {
    final marker = _endMarker;
    for (var start = tail.length - marker.length; start >= 0; start--) {
      var found = true;
      for (var index = 0; index < marker.length; index++) {
        if (tail[start + index] != marker[index]) {
          found = false;
          break;
        }
      }
      if (found) return true;
    }
    return false;
  }
}

/// How a line of the level table finds its candidates.
enum _UnitMode {
  /// Entries directly in the rule's directory carrying the rule.
  direct,

  /// Entries directly inside each entry the rule matched (`tmp/*-Inbox/*`,
  /// `Caches/<bundle-id>/*`).
  insideMatched,

  /// Anywhere (the `*.part` name override).
  anywhere,
}

class _Line {
  const _Line(
    this.ruleId,
    this.level,
    this.mode, {
    this.filesOnly = false,
    this.minimumAge,
    this.keepNewest = 0,
    this.warningKeys = const [],
    this.reasonKey,
  });

  final String ruleId;
  final StorageCleanupLevel level;
  final _UnitMode mode;
  final bool filesOnly;

  /// Required age on top of the rule's own minimum age.
  final Duration? minimumAge;

  /// The newest entries of the line kept (never proposed), by modification
  /// time.
  final int keepNewest;
  final List<String> warningKeys;

  /// `StorageLocale` key replacing the category key of the candidates.
  final String? reasonKey;
}

class _Frame {
  const _Frame(
    this.node,
    this.parent,
    this.parentRuleId,
    this.grandparent,
    this.cap,
    this.enclosing,
  );

  final StorageNode node;

  /// Canonical path of the parent directory.
  final String parent;
  final String? parentRuleId;
  final String? grandparent;

  /// Highest level index a unit may have here.
  final int cap;
  final _Unit? enclosing;
}

class _Unit {
  _Unit(this.node, this.line, this.parent);

  final StorageNode node;
  final _Line line;
  final String parent;

  /// Canonical paths of separate (lower-level) units below this one.
  final Set<String> inner = {};
}

class StorageCleanupPlanner {
  StorageCleanupPlanner({
    required StorageRootRegistry registry,
    required StorageSessionGuard guard,
    DateTime Function()? now,
  }) : _registry = registry,
       _guard = guard,
       _now = now ?? DateTime.now;

  final StorageRootRegistry _registry;
  final StorageSessionGuard _guard;
  final DateTime Function() _now;

  /// Picker copies (regular files of `tmp/` and `tmp/*-Inbox/`) are never
  /// proposed before this idle time: 10 minutes in § 3.7, one hour since the
  /// review of 5d (defence in depth behind [StorageImportActivity]).
  static const Duration pickerCopyAge = Duration(hours: 1);

  /// The music player's metadata copies (decision of the lead, 12 October
  /// 2026): not picker copies, they keep the 10 minutes of § 3.7.
  static const Duration musicCopyAge = Duration(minutes: 10);

  /// `*.part`, `Skins/.staging/*` and `*.PUP` age (§ 3.7).
  static const Duration staleAge = Duration(hours: 1);

  /// Minimum idle time of every « temporaire si inactif » candidate without
  /// a longer age (documented addition: an entry modified in the last ten
  /// minutes may belong to an operation still running).
  static const Duration idleAge = Duration(minutes: 10);

  /// Newest Dolphin session logs and KartPad logs kept (§ 3.7, decision 31).
  static const int keptLogs = 10;

  /// Roots excluded while a libretro session is declared (INV-14, INV-25).
  static const Set<String> libretroRootIds = {'INV-14', 'INV-25'};

  /// Roots excluded while the Dolphin marker exists (INV-20 … INV-22).
  static const Set<String> dolphinRootIds = {'INV-20', 'INV-21', 'INV-22'};

  /// Rule of the frame-pacing file, excluded with the Dolphin roots.
  static const String framePacingRuleId = 'INV-28.framePacing';

  /// Roots whose candidates run inside `Rpcs3InternalService.runSaveExchange`
  /// (INV-16 … INV-19, and the Files workspace INV-10 where the save
  /// exchange writes: documented addition).
  static const Set<String> rpcs3GuardedRootIds = {
    'INV-10',
    ...StorageRootRegistry.rpcs3RootIds,
  };

  /// Game folders holding duplicate copies (§ 3.5).
  static const Set<String> duplicateRootIds = {
    'INV-01',
    'INV-11',
    'INV-12',
    'INV-13',
    'INV-20',
  };

  /// The Library caches root, cleared only through its API.
  static const String libraryCachesRootId = 'INV-26';

  /// Write-ahead journal and completion marker of a 3DS backup folder
  /// (`Backups/Azahar/<stamp>`, crash-safe passes of
  /// `Libretro3dsSystemDataService`). A folder holding the journal without
  /// the marker belongs to an interrupted pass, recovered from it (and from
  /// its staging folder) by the 3DS page: every 3DS staging folder is then
  /// never proposed. The backup folders themselves are never proposed at
  /// all (review of the storage services).
  static const String threeDsPassLogName =
      Libretro3dsSystemDataService.passLogName;
  static const String threeDsCompleteMarkerName =
      Libretro3dsSystemDataService.completeMarkerName;

  /// Rule of the 3DS staging folders (`Saves/Azahar/.neostation-3ds-*`).
  static const String threeDsStagingRuleId = 'INV-14.3dsStaging';

  /// Backup folders of interrupted 3DS passes, read from the disk at the
  /// time of the call (review of the storage services: a scan cut by its
  /// bounds may not have listed a pass journal). Null when the backups
  /// folder cannot be read (or is no plain directory): nothing of the 3DS
  /// is then offered, nor deleted.
  static Future<Set<String>?> interrupted3dsPasses(
    StorageRootRegistry registry,
  ) async {
    final backups = registry.pathIn(
      StorageContainer.documents,
      StorageLayout.libretro3dsBackups,
    );
    try {
      final type = await FileSystemEntity.type(backups, followLinks: false);
      if (type == FileSystemEntityType.notFound) return const {};
      if (type != FileSystemEntityType.directory) return null;
      final interrupted = <String>{};
      await for (final entity in Directory(backups).list(followLinks: false)) {
        if (entity is! Directory) continue;
        // Listed rather than probed: a pass folder that cannot be read
        // fails the whole check instead of reading as « no journal ».
        final names = <String>{};
        await for (final child in entity.list(followLinks: false)) {
          names.add(p.basename(child.path));
        }
        if (names.contains(threeDsPassLogName) &&
            !names.contains(threeDsCompleteMarkerName)) {
          interrupted.add(storageCanonicalPath(entity.path));
        }
      }
      return interrupted;
    } on FileSystemException {
      return null;
    }
  }

  static const String _part = StorageCategorizer.partOverrideRuleId;

  /// The level table of § 3.7, by rule id of the registry.
  static const List<_Line> _table = [
    // Level 1 « Sûr ».
    _Line(
      'INV-28.temporary',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: pickerCopyAge,
    ),
    _Line(
      'INV-28.pickerInbox',
      StorageCleanupLevel.safe,
      _UnitMode.insideMatched,
      filesOnly: true,
      minimumAge: pickerCopyAge,
    ),
    // A staged ARMSX2 shader pack is a regular file directly in tmp/ too.
    _Line(
      'INV-28.armsx2Shaders',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: pickerCopyAge,
    ),
    _Line('INV-28.soloudCache', StorageCleanupLevel.safe, _UnitMode.direct),
    _Line(
      framePacingRuleId,
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
    ),
    _Line(
      _part,
      StorageCleanupLevel.safe,
      _UnitMode.anywhere,
      filesOnly: true,
      minimumAge: staleAge,
    ),
    _Line(
      'INV-10.exportPart',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: staleAge,
    ),
    _Line(
      'INV-12.gamePart',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: staleAge,
    ),
    _Line(
      'INV-13.gamePart',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: staleAge,
    ),
    _Line(
      'INV-15.importPart',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: staleAge,
    ),
    _Line('INV-03.archiveTemp', StorageCleanupLevel.safe, _UnitMode.direct),
    _Line(
      'INV-14.skinStaging',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      minimumAge: staleAge,
    ),
    _Line(
      'INV-04.backgroundImporting',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
    ),
    _Line(
      'INV-19.firmwareImport',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: staleAge,
    ),
    _Line(
      'INV-16.saveImportStaging',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
    ),
    _Line('INV-12.gameDataStaging', StorageCleanupLevel.safe, _UnitMode.direct),
    _Line('INV-14.3dsStaging', StorageCleanupLevel.safe, _UnitMode.direct),
    _Line('INV-25.content', StorageCleanupLevel.safe, _UnitMode.direct),
    _Line('INV-16.hddTmp', StorageCleanupLevel.safe, _UnitMode.direct),
    // Metadata copies of the music player (getTemporaryDirectory(), that is
    // Library/Caches on iOS): decision of the lead, 12 October 2026.
    _Line(
      'INV-28.musicCopy',
      StorageCleanupLevel.safe,
      _UnitMode.direct,
      filesOnly: true,
      minimumAge: musicCopyAge,
    ),
    // Level 2 « Régénérable ».
    _Line(
      'INV-25.skinCache',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
    ),
    _Line(
      'INV-25.skinDownloads',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
    ),
    _Line(
      'INV-25.skinInspection',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
    ),
    _Line(
      'INV-25.catalogs',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      filesOnly: true,
    ),
    _Line(
      'INV-21.shaderCache',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
    ),
    _Line(
      'INV-18.cache',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      warningKeys: [StorageLocale.rpcs3CacheWarning],
    ),
    _Line(
      'INV-22.sessionLog',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      filesOnly: true,
      keepNewest: keptLogs,
    ),
    _Line(
      'INV-12.logs',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      filesOnly: true,
      keepNewest: keptLogs,
    ),
    _Line(
      'INV-22.recoveredMarker',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      filesOnly: true,
    ),
    _Line(
      'INV-29.fonts',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      filesOnly: true,
    ),
    _Line(
      'INV-29.urlCache',
      StorageCleanupLevel.regenerable,
      _UnitMode.insideMatched,
    ),
    // The cachePath of the KartPad and Dusklight engines
    // (getTemporaryDirectory()/<engine>, Library/Caches on iOS): runtime and
    // shader caches, decision of the lead, 12 October 2026. Their sessions
    // are covered by the GameLaunchManager refusal.
    _Line(
      'INV-12.cache',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      reasonKey: StorageLocale.catCaches,
    ),
    _Line(
      'INV-13.cache',
      StorageCleanupLevel.regenerable,
      _UnitMode.direct,
      reasonKey: StorageLocale.catCaches,
    ),
    // Level 3 « Avec confirmation détaillée ».
    _Line(
      'INV-02.appLogOld',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      filesOnly: true,
    ),
    _Line(
      'INV-06.diagnostics',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      warningKeys: [StorageLocale.diagnosticsWarning],
    ),
    _Line(
      'INV-07.neoPlayLog',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      filesOnly: true,
      warningKeys: [StorageLocale.diagnosticsWarning],
    ),
    _Line(
      'INV-07.armsx2JitLog',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      filesOnly: true,
      warningKeys: [StorageLocale.diagnosticsWarning],
    ),
    _Line(
      'INV-07.rpcs3LoadLog',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      filesOnly: true,
      warningKeys: [StorageLocale.diagnosticsWarning],
    ),
    _Line(
      'INV-08.recording',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      filesOnly: true,
    ),
    _Line(
      'INV-10.exportZip',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      filesOnly: true,
    ),
    // The RPCS3 save and licence backups, the maintenance copies of
    // data.sqlite and the 3DS backups are never proposed (review of the
    // storage services: backups of user data).
    _Line('INV-14.logs', StorageCleanupLevel.confirmed, _UnitMode.direct),
    _Line(
      'INV-22.persistentLog',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      filesOnly: true,
    ),
    _Line(
      'INV-17.hdd1',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      warningKeys: [StorageLocale.hdd1Warning],
    ),
    _Line(
      'INV-12.gameData',
      StorageCleanupLevel.confirmed,
      _UnitMode.direct,
      warningKeys: [StorageLocale.kartpadGameDataWarning],
    ),
  ];

  /// Rule ids of the table, by level (tests and documentation).
  static Map<StorageCleanupLevel, List<String>> get ruleIdsByLevel => {
    for (final level in StorageCleanupLevel.values)
      level: [
        for (final line in _table)
          if (line.level == level) line.ruleId,
      ],
  };

  Future<StorageCleanupPlan> plan(
    StorageScanResult scan,
    StorageOrphanReport orphans,
    StorageCleanupLevel level,
  ) async {
    final builtAt = _now();
    final session = await _guard.check();
    final containers = _registry.containers;
    final refused = session.wholeCleanupReason;
    if (refused != null) {
      return StorageCleanupPlan(
        level: level,
        builtAt: builtAt,
        candidates: const [],
        metadataKeys: const [],
        refusals: [
          StoragePlanRefusal(
            path: StoragePlanRefusal.wholePlan,
            reason: refused,
          ),
        ],
        containers: containers,
        session: session,
        rpcs3Redirected: _registry.rpcs3Redirected,
      );
    }
    return _PlanBuilder(
      registry: _registry,
      scan: scan,
      orphans: orphans,
      level: level,
      builtAt: builtAt,
      session: session,
      interrupted3ds: await interrupted3dsPasses(_registry),
    ).build();
  }
}

class _PlanBuilder {
  _PlanBuilder({
    required this.registry,
    required this.scan,
    required this.orphans,
    required this.level,
    required this.builtAt,
    required this.session,
    required this.interrupted3ds,
  });

  final StorageRootRegistry registry;
  final StorageScanResult scan;
  final StorageOrphanReport orphans;
  final StorageCleanupLevel level;
  final DateTime builtAt;

  /// [StorageCleanupPlanner.interrupted3dsPasses] at planning time.
  final Set<String>? interrupted3ds;
  final StorageSessionState session;

  final Map<String, StorageRule> _rules = {};
  final Map<String, StorageRoot> _ruleRoots = {};
  final Map<String, String> _anchors = {};
  final Map<String, _Line> _lines = {};
  final Map<String, int> _rootOrder = {};
  final List<StorageCleanupCandidate> _candidates = [];
  final List<StoragePlanRefusal> _refusals = [];
  final Set<String> _seen = {};

  StorageContainers get containers => registry.containers;

  void _index() {
    var order = 0;
    for (final root in registry.roots) {
      _rootOrder[root.id] = order++;
      for (final rule in root.rules) {
        if (rule.id.isEmpty || _rules.containsKey(rule.id)) continue;
        _rules[rule.id] = rule;
        _ruleRoots[rule.id] = root;
      }
    }
    for (final line in StorageCleanupPlanner._table) {
      if (line.level.index > level.index) continue;
      if (line.mode != _UnitMode.anywhere) {
        final rule = _rules[line.ruleId];
        final root = _ruleRoots[line.ruleId];
        // A rule the registry does not declare proposes nothing.
        if (rule == null || root == null || rule.absolutePath != null) {
          continue;
        }
        _anchors[line.ruleId] = storageCanonicalPath(
          registry.pathIn(rule.container ?? root.container, rule.relative),
        );
      }
      _lines[line.ruleId] = line;
    }
  }

  /// Minimum age of the rule [ruleId] (the `*.part` override: one hour).
  Duration? _ruleAge(String? ruleId) {
    if (ruleId == null) return null;
    if (ruleId == StorageCategorizer.partOverrideRuleId) {
      return StorageCategorizer.partMinimumAge;
    }
    return _rules[ruleId]?.minimumAge;
  }

  /// Age [entry] must have: its rule's, and one hour for any `*.part` (a
  /// partial file inside a temporary folder keeps the folder's rule).
  Duration _entryAge(StorageNode entry) {
    final age = _ruleAge(entry.ruleId) ?? Duration.zero;
    return entry.name.endsWith('.part')
        ? _longest(age, StorageCategorizer.partMinimumAge)
        : age;
  }

  StorageEngine? _engineOf(String rootId, String? ruleId) =>
      (ruleId == null ? null : _rules[ruleId]?.engine) ??
      registry.rootById(rootId)?.engine;

  static Duration _longest(Duration a, Duration? b) =>
      b != null && b > a ? b : a;

  static DateTime _epoch() => DateTime.fromMillisecondsSinceEpoch(0);

  /// Last activity of [node]: the later of its modification and its status
  /// change (`FileStat.changed`). file_picker's copies keep the original
  /// modification time; their status change is the copy (review of 5d).
  static DateTime _activityOf(StorageNode node) =>
      _newer(node.modified ?? _epoch(), node.changed);

  /// A level-3 plan preselects nothing (review of 5d, decision of the lead).
  bool get _preselects => level != StorageCleanupLevel.confirmed;

  static DateTime _newer(DateTime a, DateTime? b) =>
      b != null && b.isAfter(a) ? b : a;

  /// Nothing of the 3DS may be offered (review of the storage services):
  /// an interrupted pass on the disk, its backups folder unreadable, or the
  /// walk of INV-14 cut by a bound or unreadable (the staging folders seen
  /// may not be all, nor the pass journals).
  bool get _threeDsBlocked {
    final interrupted = interrupted3ds;
    if (interrupted == null || interrupted.isNotEmpty) return true;
    if (scan.truncations.any((cut) => cut.rootId == 'INV-14')) return true;
    for (final location in scan.nodesOfRoot('INV-14')) {
      if (location.truncated ||
          location.kind == StorageEntryKind.inaccessible ||
          location.kind == StorageEntryKind.link) {
        return true;
      }
    }
    return false;
  }

  StorageCleanupPlan build() {
    _index();
    final units = _traverse();
    final kept = _keepNewest(units);
    final threeDsBlocked = _threeDsBlocked;
    for (final unit in units) {
      if (kept.contains(unit)) continue;
      if (threeDsBlocked &&
          unit.line.ruleId == StorageCleanupPlanner.threeDsStagingRuleId) {
        continue;
      }
      final candidate = _ruleCandidate(unit);
      if (candidate != null) _offer(candidate);
    }
    if (level.index >= StorageCleanupLevel.regenerable.index) {
      _libraryCaches();
      for (final entry in orphans.media) {
        _orphan(
          entry,
          StorageCandidateSource.orphanMedia,
          StorageLocale.orphanMedia,
          const [StorageLocale.mediaQuotaWarning],
        );
      }
      for (final entry in orphans.libraryCovers) {
        _orphan(
          entry,
          StorageCandidateSource.orphanCover,
          StorageLocale.orphanCovers,
          const [],
        );
      }
    }
    if (level == StorageCleanupLevel.confirmed) _duplicates();
    if (registry.rpcs3Redirected) _redirectedRoots();

    _candidates.sort((a, b) {
      final byRoot = (_rootOrder[a.rootId] ?? 1 << 20).compareTo(
        _rootOrder[b.rootId] ?? 1 << 20,
      );
      if (byRoot != 0) return byRoot;
      final byLevel = a.level.index.compareTo(b.level.index);
      if (byLevel != 0) return byLevel;
      return a.path.compareTo(b.path);
    });
    return StorageCleanupPlan(
      level: level,
      builtAt: builtAt,
      candidates: List.unmodifiable(_candidates),
      metadataKeys: level.index >= StorageCleanupLevel.regenerable.index
          ? List.unmodifiable(LinkedHashSet.of(orphans.metadata))
          : const [],
      refusals: List.unmodifiable(_refusals),
      containers: containers,
      session: session,
      rpcs3Redirected: registry.rpcs3Redirected,
    );
  }

  /// Session exclusions (§ 3.7), as refusals.
  bool _excluded(String rootId, String? ruleId) =>
      (session.libretroBusy &&
          StorageCleanupPlanner.libretroRootIds.contains(rootId)) ||
      (session.dolphinMarker &&
          (StorageCleanupPlanner.dolphinRootIds.contains(rootId) ||
              ruleId == StorageCleanupPlanner.framePacingRuleId));

  void _offer(StorageCleanupCandidate candidate) {
    if (!_seen.add(storageCanonicalPath(candidate.path))) return;
    if (_excluded(candidate.rootId, candidate.ruleId)) {
      _refusals.add(
        StoragePlanRefusal(
          path: candidate.path,
          reason: StorageRefusalReason.sessionActive,
          displayPath: candidate.displayPath,
          rootId: candidate.rootId,
        ),
      );
      return;
    }
    _candidates.add(candidate);
  }

  static bool _isNeverSubtree(StorageNode node) {
    final id = node.ruleId;
    return node.deletionClass == StorageDeletionClass.never &&
        id != null &&
        id.startsWith('NEVER.');
  }

  bool _matches(_Line line, StorageNode node, _Frame frame) {
    if (line.filesOnly && node.kind != StorageEntryKind.file) return false;
    switch (line.mode) {
      case _UnitMode.anywhere:
        return true;
      case _UnitMode.direct:
        return frame.parent == _anchors[line.ruleId];
      case _UnitMode.insideMatched:
        return frame.parentRuleId == line.ruleId &&
            frame.grandparent == _anchors[line.ruleId];
    }
  }

  /// Every unit of the active lines, outer units first. Inside a unit of
  /// level k only units of a strictly lower level are separate candidates;
  /// the others belong to the outer unit.
  List<_Unit> _traverse() {
    final units = <_Unit>[];
    for (final location in scan.roots) {
      if (location.rootId == StorageCleanupPlanner.libraryCachesRootId) {
        continue;
      }
      if (registry.rpcs3Redirected &&
          StorageRootRegistry.rpcs3RootIds.contains(location.rootId)) {
        continue;
      }
      final base = storageCanonicalPath(location.path);
      final stack = <_Frame>[
        for (final child in location.children.reversed)
          _Frame(
            child,
            base,
            location.ruleId,
            p.dirname(base),
            level.index,
            null,
          ),
      ];
      while (stack.isNotEmpty) {
        final frame = stack.removeLast();
        final node = frame.node;
        final path = storageCanonicalPath(node.path);
        _Unit? unit;
        if (node.deletionClass != StorageDeletionClass.never &&
            (node.kind == StorageEntryKind.file ||
                node.kind == StorageEntryKind.directory)) {
          final line = _lines[node.ruleId];
          if (line != null &&
              line.level.index <= frame.cap &&
              _matches(line, node, frame)) {
            unit = _Unit(node, line, frame.parent);
            units.add(unit);
            frame.enclosing?.inner.add(path);
          }
        }
        if (node.kind != StorageEntryKind.directory || _isNeverSubtree(node)) {
          continue;
        }
        final cap = unit == null ? frame.cap : unit.line.level.index - 1;
        if (cap < 0) continue;
        final enclosing = unit ?? frame.enclosing;
        for (final child in node.children.reversed) {
          stack.add(
            _Frame(child, path, node.ruleId, frame.parent, cap, enclosing),
          );
        }
      }
    }
    return units;
  }

  /// Units of the lines keeping their newest entries (Dolphin session logs
  /// and KartPad logs: 10 by modification time, as `StorageLogRotation`).
  Set<_Unit> _keepNewest(List<_Unit> units) {
    final kept = <_Unit>{};
    final groups = <String, List<_Unit>>{};
    for (final unit in units) {
      if (unit.line.keepNewest <= 0) continue;
      groups
          .putIfAbsent('${unit.line.ruleId}\u0000${unit.parent}', () => [])
          .add(unit);
    }
    for (final group in groups.values) {
      group.sort((a, b) {
        final byTime = (b.node.modified ?? _epoch()).compareTo(
          a.node.modified ?? _epoch(),
        );
        return byTime != 0 ? byTime : b.node.name.compareTo(a.node.name);
      });
      kept.addAll(group.take(group.first.line.keepNewest));
    }
    return kept;
  }

  StorageCleanupCandidate? _ruleCandidate(_Unit unit) {
    final node = unit.node;
    final line = unit.line;
    final now = builtAt;
    var required = line.minimumAge ?? Duration.zero;
    required = _longest(required, _entryAge(node));
    if (node.deletionClass == StorageDeletionClass.temporaryWhenIdle) {
      required = _longest(required, StorageCleanupPlanner.idleAge);
    }
    // Newest modification (the preview's date and the deletion's re-stat
    // keep modification times) and last activity (the idle age).
    var newest = node.modified ?? _epoch();
    var active = _activityOf(node);
    final files = <StorageCandidateEntry>[];
    final directories = <StorageCandidateEntry>[];
    var bytes = 0;
    int? allocated = scan.statViaFfi ? 0 : null;

    StorageCandidateEntry entryOf(StorageNode entry) => StorageCandidateEntry(
      path: entry.path,
      kind: entry.kind,
      logicalBytes: entry.kind == StorageEntryKind.file
          ? entry.logicalBytes
          : 0,
      allocatedBytes: entry.kind == StorageEntryKind.file
          ? entry.allocatedBytes
          : null,
      modified: entry.modified,
    );

    if (node.kind == StorageEntryKind.file) {
      files.add(entryOf(node));
      bytes = node.logicalBytes;
      if (allocated != null) allocated = node.allocatedBytes ?? 0;
    } else {
      // Activity anywhere below counts, even in parts never deleted.
      for (final descendant in node.descendants) {
        newest = _newer(newest, descendant.modified);
        active = _newer(active, _activityOf(descendant));
      }
      final stack = <StorageNode>[...node.children.reversed];
      while (stack.isNotEmpty) {
        final entry = stack.removeLast();
        if (unit.inner.contains(storageCanonicalPath(entry.path))) continue;
        if (entry.deletionClass == StorageDeletionClass.never) continue;
        switch (entry.kind) {
          case StorageEntryKind.file:
            files.add(entryOf(entry));
            bytes += entry.logicalBytes;
            if (allocated != null) allocated += entry.allocatedBytes ?? 0;
            required = _longest(required, _entryAge(entry));
          case StorageEntryKind.directory:
            directories.add(entryOf(entry));
            stack.addAll(entry.children.reversed);
          case StorageEntryKind.link:
          case StorageEntryKind.icloudPlaceholder:
          case StorageEntryKind.inaccessible:
            break;
        }
      }
      directories.sort(
        (a, b) => p.split(b.path).length.compareTo(p.split(a.path).length),
      );
      directories.add(entryOf(node));
    }
    if (now.difference(active) < required) return null;
    final rootId = node.rootId;
    return StorageCleanupCandidate(
      path: node.path,
      kind: node.kind,
      logicalBytes: bytes,
      allocatedBytes: allocated,
      modified: newest,
      category: node.category,
      deletionClass: node.deletionClass,
      reasonKey:
          line.reasonKey ??
          StorageLocale.categoryKeys[node.category.name] ??
          StorageLocale.catUnknown,
      warningKeys: line.warningKeys,
      preselected: _preselects && line.level != StorageCleanupLevel.confirmed,
      engine: _engineOf(rootId, node.ruleId),
      level: line.level,
      source: StorageCandidateSource.rule,
      rootId: rootId,
      ruleId: node.ruleId,
      container: node.container,
      relativePath: node.relativePath,
      fileCount: files.length,
      entries: List.unmodifiable([...files, ...directories]),
    );
  }

  /// INV-26: one candidate per Library cache, cleared through its API.
  void _libraryCaches() {
    const caches = {
      'library_http': StorageCacheApi.libraryHttp,
      'library_images': StorageCacheApi.libraryImages,
    };
    for (final location in scan.nodesOfRoot(
      StorageCleanupPlanner.libraryCachesRootId,
    )) {
      for (final child in location.children) {
        final api = caches[child.name];
        if (api == null || child.kind != StorageEntryKind.directory) continue;
        if (child.deletionClass == StorageDeletionClass.never) continue;
        if (child.logicalBytes <= 0 && child.fileCount == 0) continue;
        var newest = child.modified ?? _epoch();
        for (final descendant in child.descendants) {
          newest = _newer(newest, descendant.modified);
        }
        _offer(
          StorageCleanupCandidate(
            path: child.path,
            kind: StorageEntryKind.directory,
            logicalBytes: child.logicalBytes,
            allocatedBytes: child.allocatedBytes,
            modified: newest,
            category: child.category,
            deletionClass: child.deletionClass,
            reasonKey: StorageLocale.catCaches,
            preselected: _preselects,
            engine: StorageEngine.library,
            level: StorageCleanupLevel.regenerable,
            source: StorageCandidateSource.cacheApi,
            rootId: child.rootId,
            ruleId: child.ruleId,
            container: child.container,
            relativePath: child.relativePath,
            fileCount: child.fileCount,
            cacheApi: api,
          ),
        );
      }
    }
  }

  void _orphan(
    StorageOrphanEntry entry,
    StorageCandidateSource source,
    String reasonKey,
    List<String> warnings,
  ) {
    if (!entry.selectable ||
        entry.entryKind != StorageEntryKind.file ||
        entry.deletionClass == StorageDeletionClass.never) {
      return;
    }
    _offer(
      StorageCleanupCandidate(
        path: entry.path,
        kind: StorageEntryKind.file,
        logicalBytes: entry.logicalBytes,
        allocatedBytes: entry.allocatedBytes,
        modified: entry.modified,
        category: entry.category,
        deletionClass: entry.deletionClass,
        reasonKey: reasonKey,
        warningKeys: warnings,
        preselected: _preselects,
        engine: _engineOf(entry.rootId, entry.ruleId),
        level: StorageCleanupLevel.regenerable,
        source: source,
        rootId: entry.rootId,
        ruleId: entry.ruleId,
        container: entry.container,
        relativePath: entry.relativePath,
        fileCount: 1,
        entries: [
          StorageCandidateEntry(
            path: entry.path,
            kind: StorageEntryKind.file,
            logicalBytes: entry.logicalBytes,
            allocatedBytes: entry.allocatedBytes,
            modified: entry.modified,
          ),
        ],
      ),
    );
  }

  /// Level 3: each copy the detector marked selectable, paired with the copy
  /// the library references (shown and kept). Only copies whose SHA-256
  /// equals the kept copy's are offered (review of the storage services:
  /// the same name and size do not make the same game — a USA and an EUR
  /// image, two GameCube discs of the standard size).
  void _duplicates() {
    for (final group in orphans.duplicates) {
      if (!group.hashed) continue;
      StorageDuplicateCopy? referenced;
      for (final copy in group.copies) {
        if (copy.referenced) {
          referenced = copy;
          break;
        }
      }
      if (referenced == null) continue;
      final digest = referenced.sha256;
      if (digest == null || digest.isEmpty) continue;
      for (final copy in group.copies) {
        if (!copy.selectable || copy.referenced) continue;
        if (copy.sha256 != digest) continue;
        if (!StorageCleanupPlanner.duplicateRootIds.contains(copy.rootId)) {
          continue;
        }
        if (storageCanonicalPath(copy.path) ==
            storageCanonicalPath(referenced.path)) {
          continue;
        }
        _offer(
          StorageCleanupCandidate(
            path: copy.path,
            kind: StorageEntryKind.file,
            logicalBytes: copy.logicalBytes,
            allocatedBytes: copy.allocatedBytes,
            modified: copy.modified,
            category: StorageCategory.games,
            deletionClass: StorageDeletionClass.confirmation,
            reasonKey: StorageLocale.duplicates,
            warningKeys: const [StorageLocale.duplicateWarning],
            preselected: false,
            pairedPath: referenced.path,
            pairedDisplayPath: referenced.displayPath,
            pairedLogicalBytes: referenced.logicalBytes,
            pairedModified: referenced.modified,
            sha256: digest,
            engine: registry.rootById(copy.rootId)?.engine,
            level: StorageCleanupLevel.confirmed,
            source: StorageCandidateSource.duplicate,
            rootId: copy.rootId,
            container: copy.container,
            relativePath: copy.relativePath,
            fileCount: 1,
            entries: [
              StorageCandidateEntry(
                path: copy.path,
                kind: StorageEntryKind.file,
                logicalBytes: copy.logicalBytes,
                allocatedBytes: copy.allocatedBytes,
                modified: copy.modified,
              ),
            ],
          ),
        );
      }
    }
  }

  /// `Data/vfs.yml` redirects `dev_hdd0`: one refusal per RPCS3 root.
  void _redirectedRoots() {
    for (final id in StorageRootRegistry.rpcs3RootIds) {
      final root = registry.rootById(id);
      if (root == null) continue;
      final path = registry.pathIn(root.container, root.relative);
      _refusals.add(
        StoragePlanRefusal(
          path: path,
          reason: StorageRefusalReason.redirected,
          displayPath: containers.displayPathOf(path),
          rootId: id,
        ),
      );
    }
  }
}
