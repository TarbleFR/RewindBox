import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../data/datasources/sqlite_service.dart';
import '../../l10n/storage_locale.dart';
import '../../providers/sqlite_config_provider.dart';
import '../../repositories/storage_maintenance_repository.dart';
import '../../services/logger_service.dart';
import '../../services/storage/storage_cleanup_planner.dart';
import '../../services/storage/storage_deletion_manager.dart';
import '../../services/storage/storage_orphan_detector.dart';
import '../../services/storage/storage_report.dart';
import '../../services/storage/storage_roots.dart';
import '../../services/storage/storage_scanner.dart';
import '../libretro/libretro_skin_manager_screen.dart';
import 'storage_cleanup_preview_screen.dart';
import 'storage_screen_widgets.dart';

/// SharedPreferences of the storage pages (docs/storage-audit-cleanup.md
/// § 3.10). No SQLite column.
abstract final class StorageAuditPreferences {
  /// Detailed export (relative paths), opt-in; `false` by default.
  static const String detailedExport = 'neostation_storage_detailed_export';

  /// « Calculer les empreintes » (SHA-256 of the duplicates); `false`.
  static const String hashDuplicates = 'neostation_storage_hash_duplicates';

  /// Last cleanup level previewed, 1 … 3; 1 by default.
  static const String lastLevel = 'neostation_storage_last_level';

  /// Start of the last complete analysis, ISO 8601 (UTC).
  static const String lastScanAt = 'neostation_storage_last_scan_at';
}

/// Settings › Tools › « Analyse et nettoyage du stockage » (iOS,
/// docs/storage-audit-cleanup.md § 3.10): measures, read only, the space
/// NeoStation and its engines use — summary, categories A–I, folders,
/// orphans and duplicates — then opens the previewed cleanup of one of the
/// three levels, exports the report and lists the limits of the analysis
/// (§ 7). Nothing is deleted from this page: only the preview page deletes,
/// and only what the user ticked and confirmed.
///
/// The analysis runs when the page opens, on « Analyser à nouveau » and when
/// the app comes back to the foreground (files may have changed in the Files
/// app). While a cleanup preview is open, nothing is analysed: the analysis
/// runs when the preview closes after a cleanup or after a return to the
/// foreground. Every collaborator is injectable (tests).
class StorageAuditScreen extends StatefulWidget {
  const StorageAuditScreen({
    super.key,
    this.scanner,
    this.orphanDetector,
    this.registry,
    this.planner,
    this.deletionManager,
    this.maintenance,
    this.sharer,
  });

  /// Measurement; [StorageScanner] by default.
  final StorageScanner? scanner;

  /// Orphans and duplicates; by default the detector of the analysed
  /// inventory on `SqliteService.instance.database`.
  final StorageOrphanDetector? orphanDetector;

  /// Inventory to analyse; by default resolved again at each analysis from
  /// the registered library folders (`SqliteConfigProvider.config
  /// .romFolders`, read only).
  final StorageRootRegistry? registry;

  /// Cleanup plans; by default the planner of the analysed inventory and its
  /// session guard.
  final StorageCleanupPlanner? planner;

  /// Deletion of a confirmed preview; by default the manager of the analysed
  /// inventory and its session guard.
  final StorageDeletionManager? deletionManager;

  /// Orphan metadata rows; [StorageMaintenanceRepository] by default.
  final StorageMaintenanceRepository? maintenance;

  /// Report sharing; [StorageReportSharer] by default.
  final StorageReportSharer? sharer;

  @override
  State<StorageAuditScreen> createState() => _StorageAuditScreenState();
}

enum _Activity { idle, scanning, detecting }

class _StorageAuditScreenState extends State<StorageAuditScreen>
    with LibretroPageNavigation<StorageAuditScreen>, WidgetsBindingObserver {
  static final _log = LoggerService.instance;

  /// Children listed per folder of the tree (the largest first); the rest is
  /// summed on one line.
  static const int _shownChildren = 50;

  late final StorageScanner _scanner = widget.scanner ?? StorageScanner();
  late final StorageReportSharer _sharer =
      widget.sharer ?? StorageReportSharer();

  SharedPreferences? _preferences;
  bool _detailedExport = false;
  bool _hashDuplicates = false;
  StorageCleanupLevel _lastLevel = StorageCleanupLevel.safe;
  DateTime? _lastScanAt;

  StorageRootRegistry? _registry;
  StorageScanResult? _scan;
  StorageOrphanReport? _orphans;
  StorageDeletionResult? _lastCleanup;
  Object? _scanError;
  Object? _orphansError;

  _Activity _activity = _Activity.idle;
  bool _busy = false;
  bool _queuedScan = false;
  bool _queuedDetection = false;
  StorageScanCancelToken? _cancel;
  final ValueNotifier<StorageScanProgress?> _progress = ValueNotifier(null);

  StorageCleanupLevel? _planning;
  Object? _planError;
  bool _previewOpen = false;
  bool _analyseAfterPreview = false;

  bool _sharing = false;
  Object? _shareError;
  final GlobalKey _shareAnchor = GlobalKey();

  /// A cleanup is being planned or previewed: nothing is analysed meanwhile
  /// (the preview keeps the plan the user sees).
  bool get _cleanupOpen => _planning != null || _previewOpen;

  String _t(String key, [Map<String, Object?> parameters = const {}]) =>
      StorageLocale.text(context, key, parameters);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_start());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _cancel?.cancel();
    _progress.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state != AppLifecycleState.resumed || _sharing) return;
    // Never under a cleanup: the preview's plan stays the one the user saw;
    // the analysis runs once the preview is closed.
    if (_cleanupOpen) {
      _analyseAfterPreview = true;
      return;
    }
    unawaited(_analyse());
  }

  Future<void> _start() async {
    await _loadPreferences();
    if (mounted) await _analyse();
  }

  Future<void> _loadPreferences() async {
    try {
      final preferences = await SharedPreferences.getInstance();
      _preferences = preferences;
      final level = preferences.getInt(StorageAuditPreferences.lastLevel);
      final scannedAt = preferences.getString(
        StorageAuditPreferences.lastScanAt,
      );
      if (!mounted) return;
      setState(() {
        _detailedExport =
            preferences.getBool(StorageAuditPreferences.detailedExport) ??
            false;
        _hashDuplicates =
            preferences.getBool(StorageAuditPreferences.hashDuplicates) ??
            false;
        _lastLevel = level != null && level >= 1 && level <= 3
            ? StorageCleanupLevel.values[level - 1]
            : StorageCleanupLevel.safe;
        _lastScanAt = scannedAt == null ? null : DateTime.tryParse(scannedAt);
      });
    } catch (error) {
      _log.w('Storage page preferences unreadable: $error');
    }
  }

  Future<void> _save(Future<bool> Function(SharedPreferences) write) async {
    final preferences = _preferences;
    if (preferences == null) return;
    try {
      await write(preferences);
    } catch (error) {
      _log.w('Storage page preference not saved: $error');
    }
  }

  // ---------------------------------------------------------- analysis

  /// The inventory of this analysis. The library folders protect what they
  /// hold: without them, nothing is analysed (and so nothing can be
  /// proposed).
  Future<StorageRootRegistry> _resolveRegistry() async {
    final injected = widget.registry;
    if (injected != null) return injected;
    final provider = Provider.of<SqliteConfigProvider?>(context, listen: false);
    if (provider == null) {
      throw StateError(
        'SqliteConfigProvider unavailable: registered library folders unknown',
      );
    }
    return StorageRootRegistry.resolve(
      libraryRoots: List<String>.of(provider.config.romFolders),
    );
  }

  /// A new analysis (or, with [rescan] false, only the orphan detection of
  /// the current one); a request made meanwhile runs once it ends.
  Future<void> _analyse({bool rescan = true}) async {
    if (_busy) {
      if (rescan) {
        _queuedScan = true;
      } else {
        _queuedDetection = true;
      }
      return;
    }
    _busy = true;
    try {
      var scanNext = rescan || _scan == null;
      while (mounted) {
        final measured = scanNext ? await _runScan() : _scan != null;
        if (!mounted) return;
        if (measured) await _runDetection();
        if (!mounted) return;
        final again = _queuedScan || _queuedDetection;
        scanNext = _queuedScan;
        _queuedScan = false;
        _queuedDetection = false;
        if (!again) break;
      }
    } finally {
      _busy = false;
      _cancel = null;
      if (mounted) {
        _progress.value = null;
        setState(() => _activity = _Activity.idle);
      }
    }
  }

  /// One measurement; false when it failed or was cancelled (the previous
  /// analysis, if any, stays on screen).
  Future<bool> _runScan() async {
    final token = StorageScanCancelToken();
    _cancel = token;
    _progress.value = null;
    setState(() {
      _activity = _Activity.scanning;
      _scanError = null;
    });
    try {
      final registry = await _resolveRegistry();
      if (!mounted || token.isCancelled) return false;
      final scan = await _scanner.scan(
        registry,
        cancel: token,
        // The last counters of a root may arrive after the page closed.
        onProgress: (progress) {
          if (mounted) _progress.value = progress;
        },
      );
      if (!mounted || scan.cancelled || token.isCancelled) return false;
      setState(() {
        _registry = registry;
        _scan = scan;
        _orphans = null;
        _orphansError = null;
        _planError = null;
        _lastScanAt = scan.startedAt;
      });
      unawaited(
        _save(
          (preferences) => preferences.setString(
            StorageAuditPreferences.lastScanAt,
            scan.startedAt.toUtc().toIso8601String(),
          ),
        ),
      );
      return true;
    } catch (error, stackTrace) {
      _log.e('Storage analysis failed', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _scanError = error);
      return false;
    }
  }

  /// Orphans and duplicates of the current analysis; a cancelled detection
  /// is not shown (its counters would be partial).
  Future<void> _runDetection() async {
    final scan = _scan;
    final registry = _registry;
    if (scan == null || registry == null) return;
    final token = StorageScanCancelToken();
    _cancel = token;
    setState(() {
      _activity = _Activity.detecting;
      _orphansError = null;
    });
    try {
      final detector =
          widget.orphanDetector ??
          StorageOrphanDetector(
            database: () => SqliteService.instance.database,
            registry: registry,
          );
      final report = await detector.detect(
        scan,
        hashDuplicates: _hashDuplicates,
        cancel: token,
      );
      if (!mounted || report.cancelled || token.isCancelled) return;
      if (!identical(scan, _scan)) return;
      setState(() => _orphans = report);
    } catch (error, stackTrace) {
      _log.e(
        'Storage orphan detection failed',
        error: error,
        stackTrace: stackTrace,
      );
      if (mounted) setState(() => _orphansError = error);
    }
  }

  void _cancelAnalysis() {
    final token = _cancel;
    if (token == null || token.isCancelled) return;
    token.cancel();
    _queuedScan = false;
    _queuedDetection = false;
    setState(() {});
  }

  Future<void> _setHashDuplicates(bool value) async {
    if (_busy || _cleanupOpen || value == _hashDuplicates) return;
    setState(() => _hashDuplicates = value);
    await _save(
      (preferences) =>
          preferences.setBool(StorageAuditPreferences.hashDuplicates, value),
    );
    if (mounted && _scan != null) await _analyse(rescan: false);
  }

  Future<void> _setDetailedExport(bool value) async {
    setState(() {
      _detailedExport = value;
      _shareError = null;
    });
    await _save(
      (preferences) =>
          preferences.setBool(StorageAuditPreferences.detailedExport, value),
    );
  }

  // ----------------------------------------------------------- cleanup

  /// Builds the plan of [level] from the analysis on screen, then opens its
  /// preview. Analyses again once a cleanup ran, or when the app came back
  /// to the foreground meanwhile.
  Future<void> _openPreview(StorageCleanupLevel level) async {
    final scan = _scan;
    final registry = _registry;
    if (scan == null || registry == null || _busy || _cleanupOpen) return;
    _analyseAfterPreview = false;
    setState(() {
      _planning = level;
      _planError = null;
      _lastLevel = level;
    });
    unawaited(
      _save(
        (preferences) => preferences.setInt(
          StorageAuditPreferences.lastLevel,
          level.index + 1,
        ),
      ),
    );
    try {
      final guard = StorageSessionGuard(containers: registry.containers);
      final StorageCleanupPlan plan;
      try {
        final planner =
            widget.planner ??
            StorageCleanupPlanner(registry: registry, guard: guard);
        plan = await planner.plan(
          scan,
          _orphans ?? const StorageOrphanReport(),
          level,
        );
      } finally {
        if (mounted) setState(() => _planning = null);
      }
      if (!mounted) return;
      final manager =
          widget.deletionManager ??
          StorageDeletionManager(registry: registry, guard: guard);
      _previewOpen = true;
      try {
        await Navigator.of(context).push(
          MaterialPageRoute<void>(
            builder: (_) => StorageCleanupPreviewScreen(
              plan: plan,
              level: level,
              deletionManager: manager,
              maintenance: widget.maintenance,
              registry: registry,
              onFinished: (result) {
                if (result != null) _lastCleanup = result;
                _analyseAfterPreview = true;
              },
            ),
          ),
        );
      } finally {
        _previewOpen = false;
      }
    } catch (error, stackTrace) {
      _log.e(
        'Storage cleanup plan failed',
        error: error,
        stackTrace: stackTrace,
      );
      if (mounted) setState(() => _planError = error);
    }
    if (!mounted) return;
    setState(() {});
    if (_analyseAfterPreview) {
      _analyseAfterPreview = false;
      unawaited(_analyse());
    }
  }

  // ------------------------------------------------------------ export

  Rect? _shareOrigin() {
    final box = _shareAnchor.currentContext?.findRenderObject();
    if (box is! RenderBox || !box.hasSize) return null;
    return box.localToGlobal(Offset.zero) & box.size;
  }

  /// Totals only by default; relative paths in the opt-in detailed mode
  /// (`StorageReport`, § 3.9).
  Future<void> _share() async {
    final scan = _scan;
    if (scan == null || _sharing) return;
    final origin = _shareOrigin();
    setState(() {
      _sharing = true;
      _shareError = null;
    });
    pausePageNavigation();
    try {
      final report = _detailedExport
          ? StorageReport.detailed(
              scan,
              orphans: _orphans,
              lastCleanup: _lastCleanup,
            )
          : StorageReport.aggregate(
              scan,
              orphans: _orphans,
              lastCleanup: _lastCleanup,
            );
      await _sharer.share(
        StorageReport.encode(report),
        fileName: StorageReport.fileNameFor(DateTime.now()),
        origin: origin,
      );
    } catch (error, stackTrace) {
      _log.e('Storage report not shared', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _shareError = error);
    } finally {
      resumePageNavigation();
      if (mounted) setState(() => _sharing = false);
    }
  }

  // ------------------------------------------------------------- texts

  String _date(DateTime time) {
    final local = time.toLocal();
    final material = MaterialLocalizations.of(context);
    final clock = material.formatTimeOfDay(
      TimeOfDay.fromDateTime(local),
      alwaysUse24HourFormat:
          MediaQuery.maybeAlwaysUse24HourFormatOf(context) ?? false,
    );
    return '${material.formatMediumDate(local)} $clock';
  }

  String _category(StorageCategory category) =>
      _t(StorageLocale.categoryKeys[category.name] ?? StorageLocale.catUnknown);

  static IconData _kindIcon(StorageNode node) => switch (node.kind) {
    StorageEntryKind.directory => Icons.folder_outlined,
    StorageEntryKind.file => Icons.insert_drive_file_outlined,
    StorageEntryKind.link => Icons.link_rounded,
    StorageEntryKind.icloudPlaceholder => Icons.cloud_outlined,
    StorageEntryKind.inaccessible => Icons.block_rounded,
  };

  /// Translated detail of a tree node: its category, its files, links,
  /// unreadable entries and iCloud placeholders.
  String _nodeDetail(StorageNode node) => [
    _category(node.category),
    if (node.isDirectory) _t(StorageLocale.entries, {'count': node.fileCount}),
    if (node.linkCount > 0) _t(StorageLocale.links, {'count': node.linkCount}),
    if (node.inaccessibleCount > 0)
      _t(StorageLocale.inaccessible, {'count': node.inaccessibleCount}),
    if (node.icloudCount > 0)
      _t(StorageLocale.icloudPlaceholders, {'count': node.icloudCount}),
  ].join(' · ');

  // ------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scan = _scan;
    return libretroPage(
      Scaffold(
        appBar: libretroPageAppBar(context, _t(StorageLocale.title)),
        body: SafeArea(
          child: Center(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 860),
              // Every card is built (no lazy list): the D-pad always reaches
              // the next one.
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Padding(
                      padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
                      child: Text(
                        _t(StorageLocale.toolSubtitle),
                        style: theme.textTheme.bodyMedium?.copyWith(
                          color: theme.colorScheme.onSurfaceVariant,
                        ),
                      ),
                    ),
                    _buildStatus(context),
                    if (scan != null) ...[
                      _buildSummary(context, scan),
                      _buildCategories(context, scan),
                      _buildRoots(context, scan),
                      _buildOrphans(context),
                      _buildCleanup(context),
                      _buildExport(context),
                    ],
                    _buildLimits(context, scan),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStatus(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final last = _scan?.startedAt ?? _lastScanAt;
    final headline = switch (_activity) {
      _Activity.scanning => _t(StorageLocale.scanning),
      _Activity.detecting => _t(
        _hashDuplicates ? StorageLocale.hashing : StorageLocale.scanning,
      ),
      _Activity.idle =>
        last == null
            ? _t(StorageLocale.title)
            : _t(StorageLocale.lastScan, {'date': _date(last)}),
    };
    final cancel = _cancel;
    return Card(
      key: const ValueKey('storage-status'),
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Row(
              children: [
                Icon(Icons.storage_rounded, color: scheme.primary),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    headline,
                    key: const ValueKey('storage-status-headline'),
                    style: theme.textTheme.titleMedium,
                  ),
                ),
                if (_busy)
                  const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
              ],
            ),
            if (_activity == _Activity.scanning)
              ValueListenableBuilder<StorageScanProgress?>(
                valueListenable: _progress,
                builder: (context, progress, _) => Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    const SizedBox(height: 10),
                    LinearProgressIndicator(
                      key: const ValueKey('storage-scan-progress'),
                      value: progress == null || progress.rootsTotal <= 0
                          ? null
                          : (progress.rootsDone / progress.rootsTotal).clamp(
                              0.0,
                              1.0,
                            ),
                    ),
                    if (progress != null) ...[
                      const SizedBox(height: 6),
                      Text(
                        _t(StorageLocale.entries, {'count': progress.entries}),
                        key: const ValueKey('storage-scan-entries'),
                        style: theme.textTheme.bodySmall,
                      ),
                      Text(
                        '${progress.rootId} · ${storageSize(progress.bytes)}',
                        style: storageRawStyle(context),
                      ),
                    ],
                  ],
                ),
              ),
            if (_scanError != null) ...[
              const SizedBox(height: 8),
              Text(
                _t(StorageLocale.scanFailed, {'error': _scanError}),
                key: const ValueKey('storage-scan-error'),
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: scheme.error,
                ),
              ),
            ],
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                LibretroFocusRing(
                  child: FilledButton.tonalIcon(
                    key: const ValueKey('storage-scan-again'),
                    onPressed: _busy || _cleanupOpen
                        ? null
                        : () => unawaited(_analyse()),
                    icon: const Icon(Icons.refresh_rounded),
                    label: Text(_t(StorageLocale.scanAgain)),
                  ),
                ),
                if (_busy)
                  LibretroFocusRing(
                    child: OutlinedButton.icon(
                      key: const ValueKey('storage-scan-cancel'),
                      onPressed: cancel == null || cancel.isCancelled
                          ? null
                          : _cancelAnalysis,
                      icon: const Icon(Icons.close_rounded),
                      label: Text(_t(StorageLocale.cancel)),
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSummary(BuildContext context, StorageScanResult scan) {
    final theme = Theme.of(context);
    var links = 0;
    var unreadable = 0;
    var icloud = 0;
    for (final node in scan.roots) {
      links += node.linkCount;
      unreadable += node.inaccessibleCount;
      icloud += node.icloudCount;
    }
    final allocated = scan.statViaFfi ? scan.allocatedBytes : null;
    final free = scan.freeBytes;
    final total = scan.volumeBytes;
    return StorageFocusable(
      child: StorageSectionCard(
        key: const ValueKey('storage-summary'),
        icon: Icons.pie_chart_outline_rounded,
        title: _t(StorageLocale.summary),
        children: [
          Text(
            _t(StorageLocale.totalLogical, {
              'size': storageSize(scan.logicalBytes),
            }),
            key: const ValueKey('storage-total-logical'),
            style: theme.textTheme.titleSmall,
          ),
          Text(
            allocated != null
                ? _t(StorageLocale.totalAllocated, {
                    'size': storageSize(allocated),
                  })
                : _t(StorageLocale.allocatedUnavailable),
            key: const ValueKey('storage-total-allocated'),
          ),
          Text(
            free != null && total != null
                ? _t(StorageLocale.freeSpace, {
                    'free': storageSize(free),
                    'total': storageSize(total),
                  })
                : _t(StorageLocale.freeSpaceUnavailable),
            key: const ValueKey('storage-free-space'),
          ),
          Text(_t(StorageLocale.entries, {'count': scan.entries})),
          if (links > 0) Text(_t(StorageLocale.links, {'count': links})),
          if (unreadable > 0)
            Text(_t(StorageLocale.inaccessible, {'count': unreadable})),
          if (icloud > 0)
            Text(_t(StorageLocale.icloudPlaceholders, {'count': icloud})),
          const SizedBox(height: 8),
          Text(
            _t(StorageLocale.gapExplanation),
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildCategories(BuildContext context, StorageScanResult scan) {
    final theme = Theme.of(context);
    return StorageSectionCard(
      key: const ValueKey('storage-categories'),
      icon: Icons.category_outlined,
      title: _t(StorageLocale.byCategory),
      children: [
        for (final category in StorageCategory.values)
          StorageFocusable(
            key: ValueKey('storage-category-${category.name}'),
            radius: 8,
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
              child: Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(_category(category)),
                        Text(
                          _t(StorageLocale.entries, {
                            'count': scan.byCategory[category]?.fileCount ?? 0,
                          }),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: theme.colorScheme.onSurfaceVariant,
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 8),
                  Text(
                    storageSize(scan.byCategory[category]?.logicalBytes ?? 0),
                    style: theme.textTheme.bodyMedium,
                  ),
                ],
              ),
            ),
          ),
      ],
    );
  }

  Widget _buildRoots(BuildContext context, StorageScanResult scan) {
    final groups = <String, List<StorageNode>>{};
    for (final node in scan.roots) {
      groups.putIfAbsent(node.rootId, () => []).add(node);
    }
    return StorageSectionCard(
      key: const ValueKey('storage-roots'),
      icon: Icons.folder_outlined,
      title: _t(StorageLocale.byRoot),
      children: [
        for (final group in groups.entries)
          if (_registry?.rootById(group.key)?.hidden == true ||
              group.value.any(
                (node) =>
                    node.logicalBytes > 0 ||
                    node.fileCount > 0 ||
                    node.linkCount > 0 ||
                    node.inaccessibleCount > 0 ||
                    node.icloudCount > 0,
              ))
            _rootTile(context, group.key, group.value),
      ],
    );
  }

  Widget _rootTile(
    BuildContext context,
    String rootId,
    List<StorageNode> locations,
  ) {
    final theme = Theme.of(context);
    final root = _registry?.rootById(rootId);
    final label = _t(
      root?.labelKey ??
          StorageLocale.containerKeys[locations.first.container.name] ??
          StorageLocale.rootDocuments,
    );
    var bytes = 0;
    var files = 0;
    var links = 0;
    var unreadable = 0;
    var icloud = 0;
    for (final node in locations) {
      bytes += node.logicalBytes;
      files += node.fileCount;
      links += node.linkCount;
      unreadable += node.inaccessibleCount;
      icloud += node.icloudCount;
    }
    final counters = [
      _t(StorageLocale.entries, {'count': files}),
      if (links > 0) _t(StorageLocale.links, {'count': links}),
      if (unreadable > 0) _t(StorageLocale.inaccessible, {'count': unreadable}),
      if (icloud > 0) _t(StorageLocale.icloudPlaceholders, {'count': icloud}),
    ];
    return StorageExpandableTile(
      key: ValueKey('storage-root-$rootId'),
      headerKey: ValueKey('storage-root-header-$rootId'),
      leading: const Icon(Icons.folder_rounded),
      title: Text(label),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            [
              rootId,
              for (final node in locations) node.displayPath,
            ].join(' · '),
            style: storageRawStyle(context),
          ),
          Text(counters.join(' · '), style: theme.textTheme.bodySmall),
        ],
      ),
      trailing: Text(storageSize(bytes)),
      childrenBuilder: (context) {
        // NeoSwap unlinks its files: nothing to list, only its limit.
        if (root?.hidden ?? false) {
          return [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(24, 4, 8, 8),
              child: StorageFocusable(
                child: Text(
                  _t(StorageLocale.limitNeoSwap),
                  style: theme.textTheme.bodySmall,
                ),
              ),
            ),
          ];
        }
        if (locations.length == 1) {
          return _nodeChildren(context, locations.single, depth: 1);
        }
        return [
          for (final location in locations)
            _nodeTile(context, location, depth: 1, name: location.displayPath),
        ];
      },
    );
  }

  /// The children of [node], the largest first, the rest summed. A subtree
  /// measured but never detailed (the hidden Library folder) is never
  /// listed: the scanner keeps no node for it and its bytes stay in the
  /// parent's total; a node found there anyway is left out too.
  List<Widget> _nodeChildren(
    BuildContext context,
    StorageNode node, {
    required int depth,
  }) {
    final registry = _registry;
    final children = [
      for (final child in node.children)
        if (registry == null || !registry.isAggregateOnly(child.path)) child,
    ];
    final shown = children.take(_shownChildren).toList();
    final rest = children.skip(shown.length).toList();
    final restBytes = rest.fold<int>(
      0,
      (sum, child) => sum + child.logicalBytes,
    );
    return [
      for (final child in shown) _nodeTile(context, child, depth: depth),
      if (rest.isNotEmpty)
        StorageFocusable(
          child: StorageNodeLine(
            key: ValueKey('storage-node-rest-${node.path}'),
            icon: Icons.more_horiz_rounded,
            name: '…',
            detail: _t(StorageLocale.entries, {'count': rest.length}),
            size: storageSize(restBytes),
            indent: depth * 16.0,
          ),
        ),
    ];
  }

  /// A folder of depth 1 opens on its children (depth 2); deeper entries and
  /// files are leaves.
  Widget _nodeTile(
    BuildContext context,
    StorageNode node, {
    required int depth,
    String? name,
  }) {
    final label = name ?? node.name;
    if (depth < 2 && node.children.isNotEmpty) {
      return StorageExpandableTile(
        key: ValueKey('storage-node-${node.path}'),
        headerKey: ValueKey('storage-node-header-${node.path}'),
        indent: depth * 16.0,
        leading: Icon(_kindIcon(node)),
        title: Text(label, style: storageRawStyle(context)),
        subtitle: Text(_nodeDetail(node)),
        trailing: Text(storageSize(node.logicalBytes)),
        childrenBuilder: (context) =>
            _nodeChildren(context, node, depth: depth + 1),
      );
    }
    return StorageFocusable(
      child: StorageNodeLine(
        key: ValueKey('storage-node-${node.path}'),
        icon: _kindIcon(node),
        name: label,
        detail: _nodeDetail(node),
        size: storageSize(node.logicalBytes),
        indent: depth * 16.0,
      ),
    );
  }

  Widget _buildOrphans(BuildContext context) {
    final theme = Theme.of(context);
    final orphans = _orphans;
    final detecting = _activity == _Activity.detecting;
    return StorageSectionCard(
      key: const ValueKey('storage-orphans'),
      icon: Icons.link_off_rounded,
      title: _t(StorageLocale.orphans),
      children: [
        if (orphans != null)
          StorageFocusable(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _t(StorageLocale.orphanMedia, {
                    'count': orphans.media.length,
                    'size': storageSize(
                      orphans.media.fold<int>(
                        0,
                        (sum, entry) => sum + entry.logicalBytes,
                      ),
                    ),
                  }),
                  key: const ValueKey('storage-orphan-media'),
                ),
                Text(
                  _t(StorageLocale.orphanMetadata, {
                    'count': orphans.metadata.length,
                  }),
                  key: const ValueKey('storage-orphan-metadata'),
                ),
                Text(
                  _t(StorageLocale.orphanCovers, {
                    'count': orphans.libraryCovers.length,
                  }),
                  key: const ValueKey('storage-orphan-covers'),
                ),
                Text(
                  _t(StorageLocale.orphanSavesInfo, {
                    'count': orphans.savesAndStates.length,
                  }),
                  key: const ValueKey('storage-orphan-saves'),
                ),
                Text(
                  _t(StorageLocale.duplicates, {
                    'count': orphans.duplicates.length,
                    'size': storageSize(
                      orphans.duplicates.fold<int>(
                        0,
                        (sum, group) => sum + group.selectableBytes,
                      ),
                    ),
                  }),
                  key: const ValueKey('storage-duplicates'),
                ),
                // Analyses not made, with their raw reason.
                for (final skipped in orphans.skipped.entries)
                  Text(
                    _t(StorageLocale.technicalCode, {
                      'code': '${skipped.key}: ${skipped.value}',
                    }),
                    style: storageRawStyle(context),
                  ),
              ],
            ),
          )
        else if (detecting)
          Text(
            _t(
              _hashDuplicates ? StorageLocale.hashing : StorageLocale.scanning,
            ),
            key: const ValueKey('storage-orphans-running'),
          ),
        if (_orphansError != null)
          Text(
            _t(StorageLocale.scanFailed, {'error': _orphansError}),
            key: const ValueKey('storage-orphans-error'),
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.error,
            ),
          ),
        LibretroFocusRing(
          radius: 12,
          child: SwitchListTile(
            key: const ValueKey('storage-hash-toggle'),
            value: _hashDuplicates,
            onChanged: _busy || _cleanupOpen
                ? null
                : (value) => _setHashDuplicates(value),
            contentPadding: const EdgeInsets.symmetric(horizontal: 4),
            title: Text(_t(StorageLocale.computeHashes)),
            subtitle: detecting && _hashDuplicates
                ? Text(_t(StorageLocale.hashing))
                : null,
          ),
        ),
      ],
    );
  }

  Widget _buildCleanup(BuildContext context) {
    final theme = Theme.of(context);
    final enabled = !_busy && !_cleanupOpen;
    final cleanup = _lastCleanup;
    return StorageSectionCard(
      key: const ValueKey('storage-cleanup'),
      icon: Icons.cleaning_services_outlined,
      title: _t(StorageLocale.cleanup),
      children: [
        for (final level in StorageCleanupLevel.values)
          LibretroFocusRing(
            radius: 12,
            child: ListTile(
              key: ValueKey('storage-level-${level.name}'),
              enabled: enabled,
              selected: level == _lastLevel,
              contentPadding: const EdgeInsets.symmetric(horizontal: 8),
              leading: Icon(switch (level) {
                StorageCleanupLevel.safe => Icons.verified_user_outlined,
                StorageCleanupLevel.regenerable => Icons.autorenew_rounded,
                StorageCleanupLevel.confirmed => Icons.rule_rounded,
              }),
              title: Text(
                _t(
                  StorageLocale.levelKeys[level.name] ??
                      StorageLocale.levelSafe,
                ),
              ),
              subtitle: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _t(
                      StorageLocale.levelHelpKeys[level.name] ??
                          StorageLocale.levelSafeHelp,
                    ),
                  ),
                  Text(
                    _t(
                      level == StorageCleanupLevel.confirmed
                          ? StorageLocale.levelNeverPreselectedNote
                          : StorageLocale.levelPreselectedNote,
                    ),
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
              trailing: _planning == level
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(strokeWidth: 2),
                    )
                  : Icon(
                      Icons.chevron_right_rounded,
                      semanticLabel: _t(StorageLocale.preview),
                    ),
              onTap: () => unawaited(_openPreview(level)),
            ),
          ),
        if (_planError != null)
          Text(
            _t(StorageLocale.scanFailed, {'error': _planError}),
            key: const ValueKey('storage-plan-error'),
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.error,
            ),
          ),
        if (cleanup != null)
          Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              _t(StorageLocale.resultDeleted, {
                'count': cleanup.deletedFiles,
                'size': storageSize(cleanup.deletedBytes),
              }),
              key: const ValueKey('storage-last-cleanup'),
              style: theme.textTheme.bodySmall,
            ),
          ),
      ],
    );
  }

  Widget _buildExport(BuildContext context) {
    final theme = Theme.of(context);
    return StorageSectionCard(
      key: const ValueKey('storage-export'),
      icon: Icons.ios_share_rounded,
      title: _t(StorageLocale.export),
      children: [
        LibretroFocusRing(
          radius: 12,
          child: SwitchListTile(
            key: const ValueKey('storage-export-detailed'),
            value: _detailedExport,
            onChanged: _sharing ? null : (value) => _setDetailedExport(value),
            contentPadding: const EdgeInsets.symmetric(horizontal: 4),
            title: Text(_t(StorageLocale.exportDetailed)),
            subtitle: Text(_t(StorageLocale.exportDetailedHelp)),
          ),
        ),
        const SizedBox(height: 8),
        Align(
          alignment: AlignmentDirectional.centerStart,
          child: KeyedSubtree(
            key: _shareAnchor,
            child: LibretroFocusRing(
              child: FilledButton.tonalIcon(
                key: const ValueKey('storage-share'),
                onPressed: _sharing ? null : () => unawaited(_share()),
                icon: const Icon(Icons.ios_share_rounded),
                label: Text(_t(StorageLocale.share)),
              ),
            ),
          ),
        ),
        if (_shareError != null) ...[
          const SizedBox(height: 8),
          Text(
            _t(StorageLocale.shareFailed),
            key: const ValueKey('storage-share-error'),
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.error,
            ),
          ),
          Text(
            _t(StorageLocale.technicalCode, {'code': _shareError}),
            key: const ValueKey('storage-share-error-code'),
            style: storageRawStyle(context),
          ),
        ],
      ],
    );
  }

  /// § 7: what the analysis cannot measure or does not do.
  Widget _buildLimits(BuildContext context, StorageScanResult? scan) {
    final theme = Theme.of(context);
    final keys = [
      if (scan != null && !scan.statViaFfi) StorageLocale.limitFfi,
      StorageLocale.limitFreeSpace,
      StorageLocale.limitNeoSwap,
      StorageLocale.limitExtensions,
      StorageLocale.limitLinkedFolders,
      StorageLocale.limitRpcs3Cache,
      StorageLocale.limitDolphinStates,
      StorageLocale.limitScannerOrphans,
      StorageLocale.limitNoAutoPurge,
      StorageLocale.limitUnverified,
    ];
    return StorageFocusable(
      child: StorageSectionCard(
        key: const ValueKey('storage-limits'),
        icon: Icons.info_outline_rounded,
        title: _t(StorageLocale.limitsTitle),
        children: [
          for (final key in keys)
            Padding(
              padding: const EdgeInsets.only(bottom: 6),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Padding(
                    padding: const EdgeInsets.only(top: 2),
                    child: Icon(
                      Icons.info_outline_rounded,
                      size: 16,
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      _t(key),
                      key: ValueKey('storage-limit-$key'),
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
