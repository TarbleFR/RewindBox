import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../l10n/storage_locale.dart';
import '../../repositories/storage_maintenance_repository.dart';
import '../../services/logger_service.dart';
import '../../services/storage/storage_deletion_manager.dart';
import '../../services/storage/storage_orphan_detector.dart'
    show StorageOrphanMetadataKey;
import '../../services/storage/storage_report.dart';
import '../../services/storage/storage_roots.dart';
import '../../services/storage/storage_scanner.dart';
import '../libretro/libretro_skin_manager_screen.dart';
import 'storage_screen_widgets.dart';

/// Preview of one cleanup level (docs/storage-audit-cleanup.md § 3.10), the
/// only page of NeoStation that deletes storage: the candidates of the plan
/// by root, each with its box, its raw path, its size and its warning
/// badges; the orphan metadata rows as one box, their raw keys listed on
/// demand; the paths the session guards left out (greyed) and the selected
/// total.
///
/// Levels 1 and 2 open with the plan's preselection ticked, level 3 with
/// nothing ticked at all, its metadata rows included (review of phase 5d).
/// A group holding a ticked item starts open, and every group header counts
/// its ticked items: nothing ticked is ever out of sight. Every list is built
/// lazily, and a tick rebuilds only its box, its group header and the total.
/// On a controller, RB (E on a keyboard) goes straight to the action of the
/// page — « Supprimer », Cancel while it runs, « Analyser à nouveau » on the
/// result — and LB (Q) back to the top, without walking through every item.
///
/// « Supprimer » asks for a confirmation that repeats the warnings, the
/// number of items, their size and the metadata rows; the deletion manager
/// then deletes exactly the ticked items (each one checked again, § 3.8),
/// with its progress and a cancel button, and the page shows its result:
/// deleted, changed since the preview, already gone, refused (translated
/// reason, raw technical code and raw path) and the journal. Going back runs
/// a new analysis ([onFinished]).
class StorageCleanupPreviewScreen extends StatefulWidget {
  const StorageCleanupPreviewScreen({
    super.key,
    required this.plan,
    required this.level,
    required this.deletionManager,
    this.maintenance,
    this.registry,
    this.onFinished,
  });

  /// Plan of [level], built from the analysis the user just saw.
  final StorageCleanupPlan plan;
  final StorageCleanupLevel level;

  /// Runs the confirmed selection.
  final StorageDeletionManager deletionManager;

  /// Orphan metadata rows; [StorageMaintenanceRepository] by default.
  final StorageMaintenanceRepository? maintenance;

  /// Inventory of the analysis: names each root group.
  final StorageRootRegistry? registry;

  /// Called once a deletion ran, with its result (null when it failed
  /// unexpectedly): the analysis page then analyses again.
  final ValueChanged<StorageDeletionResult?>? onFinished;

  /// Boxes ticked when the preview opens: the plan's preselection at levels
  /// 1 and 2; nothing at level 3, whatever the plan holds (review of phase
  /// 5d).
  @visibleForTesting
  static Set<String> initialSelection(
    StorageCleanupPlan plan,
    StorageCleanupLevel level,
  ) =>
      level == StorageCleanupLevel.confirmed ||
          plan.level == StorageCleanupLevel.confirmed
      ? <String>{}
      : {...plan.preselectedPaths};

  @override
  State<StorageCleanupPreviewScreen> createState() =>
      _StorageCleanupPreviewScreenState();
}

class _StorageCleanupPreviewScreenState
    extends State<StorageCleanupPreviewScreen>
    with LibretroPageNavigation<StorageCleanupPreviewScreen> {
  static final _log = LoggerService.instance;

  /// Plans of at most this many candidates open every group; larger ones
  /// open only the groups holding a ticked item.
  static const int _openGroupLimit = 50;

  late final _PreviewSelection _selection = _PreviewSelection(
    widget.plan,
    StorageCleanupPreviewScreen.initialSelection(widget.plan, widget.level),
  );
  late final Map<String, List<StorageCleanupCandidate>> _groups =
      widget.plan.candidatesByRoot;
  final ValueNotifier<StorageDeletionProgress?> _progress = ValueNotifier(null);
  final ScrollController _scroll = ScrollController();
  final FocusNode _topFocus = FocusNode(debugLabel: 'Storage preview top');
  final FocusNode _deleteFocus = FocusNode(debugLabel: 'Storage delete');
  final FocusNode _cancelFocus = FocusNode(debugLabel: 'Storage cancel');
  final FocusNode _rescanFocus = FocusNode(debugLabel: 'Storage rescan');
  bool _running = false;
  bool _cancelRequested = false;
  StorageScanCancelToken? _cancel;
  StorageDeletionResult? _result;
  Object? _failure;

  StorageCleanupPlan get _plan => widget.plan;
  bool get _finished => _result != null || _failure != null;

  String _t(String key, [Map<String, Object?> parameters = const {}]) =>
      StorageLocale.text(context, key, parameters);

  @override
  VoidCallback? get libretroPreviousTab => _jumpToTop;

  @override
  VoidCallback? get libretroNextTab => _jumpToAction;

  @override
  void dispose() {
    _cancel?.cancel();
    _progress.dispose();
    _selection.dispose();
    _scroll.dispose();
    _topFocus.dispose();
    _deleteFocus.dispose();
    _cancelFocus.dispose();
    _rescanFocus.dispose();
    super.dispose();
  }

  /// LB (Q): back to the top, on its first block (focused after the next
  /// frame when it is not built yet).
  void _jumpToTop() {
    if (!mounted) return;
    if (_scroll.hasClients && _scroll.offset > 0) _scroll.jumpTo(0);
    if (_topFocus.context != null) {
      _topFocus.requestFocus();
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _topFocus.context != null) _topFocus.requestFocus();
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  /// RB (E): the action of the page, in the bar below the list — « Supprimer »
  /// (once something is ticked), Cancel while the deletion runs,
  /// « Analyser à nouveau » on the result.
  void _jumpToAction() {
    if (!mounted) return;
    final node = _finished
        ? _rescanFocus
        : _running
        ? _cancelFocus
        : _deleteFocus;
    if (node.context != null && node.canRequestFocus) node.requestFocus();
  }

  /// The confirmation, then the deletion of exactly the ticked items.
  Future<void> _confirmAndDelete() async {
    if (_running || _finished) return;
    final plan = _plan;
    final selection = _selection.selected;
    final count = plan.countOf(selection);
    if (count == 0) return;
    final size = storageSize(plan.bytesOf(selection));
    final warnings = plan.warningKeysOf(selection);
    final metadata =
        plan.hasMetadata &&
            selection.contains(StorageCleanupPlan.metadataSelectionKey)
        ? plan.metadataKeys.length
        : null;
    pausePageNavigation();
    bool confirmed;
    try {
      confirmed =
          await showDialog<bool>(
            context: context,
            barrierDismissible: false,
            builder: (_) => _ConfirmDeletionDialog(
              count: count,
              size: size,
              warningKeys: warnings,
              metadataCount: metadata,
            ),
          ) ??
          false;
    } finally {
      resumePageNavigation();
    }
    if (!confirmed || !mounted) return;
    await _execute(selection);
  }

  Future<void> _execute(Set<String> selection) async {
    final token = StorageScanCancelToken();
    _progress.value = null;
    setState(() {
      _running = true;
      _cancelRequested = false;
      _cancel = token;
    });
    StorageDeletionResult? result;
    Object? failure;
    try {
      result = await widget.deletionManager.execute(
        _plan,
        selectedPaths: selection,
        maintenance: widget.maintenance ?? StorageMaintenanceRepository(),
        onProgress: (progress) {
          if (mounted) _progress.value = progress;
        },
        cancel: token,
      );
    } catch (error, stackTrace) {
      _log.e('Storage cleanup failed', error: error, stackTrace: stackTrace);
      failure = error;
    }
    widget.onFinished?.call(result);
    if (!mounted) return;
    setState(() {
      _running = false;
      _cancel = null;
      _result = result;
      _failure = failure;
    });
    if (_scroll.hasClients) _scroll.jumpTo(0);
  }

  void _cancelDeletion() {
    final token = _cancel;
    if (token == null || token.isCancelled) return;
    token.cancel();
    setState(() => _cancelRequested = true);
  }

  // ------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final plan = _plan;
    final Widget? bar = _finished
        ? _resultBar(context)
        : plan.blocked || plan.isEmpty
        ? null
        : _actionBar(context);
    return libretroPage(
      PopScope(
        // Never left half-way: the manager stops at the cancel button.
        canPop: !_running,
        child: Scaffold(
          appBar: libretroPageAppBar(
            context,
            _t(_finished ? StorageLocale.resultTitle : StorageLocale.preview),
          ),
          body: SafeArea(
            child: Center(
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 860),
                // Lazy lists: only the rows on screen (and just around it)
                // are built; the D-pad scrolls row by row, RB and LB jump.
                child: CustomScrollView(
                  controller: _scroll,
                  slivers: [
                    SliverPadding(
                      padding: const EdgeInsets.all(16),
                      sliver: SliverMainAxisGroup(
                        slivers: _finished
                            ? _resultSlivers(context)
                            : _previewSlivers(context),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          bottomNavigationBar: bar,
        ),
      ),
    );
  }

  List<Widget> _previewSlivers(BuildContext context) {
    final theme = Theme.of(context);
    final plan = _plan;
    final level = widget.level;
    final confirmed = level == StorageCleanupLevel.confirmed;
    return [
      SliverToBoxAdapter(
        child: StorageFocusable(
          focusNode: _topFocus,
          child: StorageSectionCard(
            key: const ValueKey('storage-preview-level'),
            icon: Icons.cleaning_services_outlined,
            title: _t(
              StorageLocale.levelKeys[level.name] ?? StorageLocale.levelSafe,
            ),
            children: [
              Text(
                _t(
                  StorageLocale.levelHelpKeys[level.name] ??
                      StorageLocale.levelSafeHelp,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                _t(
                  confirmed
                      ? StorageLocale.levelNeverPreselectedNote
                      : StorageLocale.levelPreselectedNote,
                ),
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
      if (plan.blocked)
        SliverToBoxAdapter(
          child: StorageFocusable(
            child: Card(
              key: const ValueKey('storage-preview-blocked'),
              margin: const EdgeInsets.only(bottom: 16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  _t(
                    plan.refusals.isEmpty
                        ? StorageLocale.sessionActive
                        : plan.refusals.first.localeKey,
                  ),
                  style: theme.textTheme.bodyMedium?.copyWith(
                    color: theme.colorScheme.error,
                  ),
                ),
              ),
            ),
          ),
        )
      else ...[
        if (plan.isEmpty)
          SliverToBoxAdapter(
            child: StorageFocusable(
              child: Card(
                key: const ValueKey('storage-preview-empty'),
                margin: const EdgeInsets.only(bottom: 16),
                child: Padding(
                  padding: const EdgeInsets.all(16),
                  child: Text(_t(StorageLocale.nothingToClean)),
                ),
              ),
            ),
          ),
        for (final group in _groups.entries)
          _PreviewGroup(
            key: ValueKey('storage-preview-root-${group.key}'),
            rootId: group.key,
            label: _rootLabel(group.key, group.value.first),
            rootPath: _rootPath(group.key),
            candidates: group.value,
            selection: _selection,
            // No ticked item out of sight.
            initiallyExpanded:
                _selection.tickedIn(group.key) > 0 ||
                plan.candidates.length <= _openGroupLimit,
            frozen: _running,
          ),
        if (plan.hasMetadata)
          _MetadataGroup(
            key: const ValueKey('storage-preview-metadata'),
            keys: plan.metadataKeys,
            selection: _selection,
            frozen: _running,
          ),
        if (plan.refusals.isNotEmpty)
          _RefusalGroup(
            key: const ValueKey('storage-preview-refusals'),
            title: _t(StorageLocale.resultRefused, {
              'count': plan.refusals.length,
            }),
            refusals: plan.refusals,
            itemKeyPrefix: 'storage-preview-refusal',
            greyed: true,
          ),
      ],
    ];
  }

  /// Label of a root group: the root's own label, the Library for its three
  /// roots, else its container.
  String _rootLabel(String rootId, StorageCleanupCandidate first) {
    final key =
        widget.registry?.rootById(rootId)?.labelKey ??
        (StorageReport.libraryRootIds.contains(rootId)
            ? StorageLocale.rootLibrary
            : StorageLocale.containerKeys[first.container.name]) ??
        StorageLocale.rootDocuments;
    return _t(key);
  }

  /// `<Container>/relative` of the root directory of [rootId], if known.
  String? _rootPath(String rootId) {
    final root = widget.registry?.rootById(rootId);
    if (root == null) return null;
    final placeholder = StorageContainers.placeholderOf(root.container);
    return root.relative.isEmpty
        ? placeholder
        : '$placeholder/${root.relative}';
  }

  /// The RB glyph next to the action it reaches (images only: the action
  /// keeps its own label).
  Widget _bumperHint(BuildContext context) => ExcludeSemantics(
    child: Padding(
      padding: const EdgeInsetsDirectional.only(end: 6),
      child: Image.asset(
        'assets/images/gamepad/Xbox_RB_bumper.png',
        height: 22,
        color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
        colorBlendMode: BlendMode.srcIn,
      ),
    ),
  );

  Widget _bar(BuildContext context, Widget child) => Material(
    elevation: 8,
    color: Theme.of(context).colorScheme.surfaceContainer,
    child: SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
        child: child,
      ),
    ),
  );

  Widget _actionBar(BuildContext context) {
    final theme = Theme.of(context);
    if (_running) {
      return _bar(
        context,
        ValueListenableBuilder<StorageDeletionProgress?>(
          valueListenable: _progress,
          builder: (context, progress, _) => Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              LinearProgressIndicator(
                key: const ValueKey('storage-delete-progress'),
                value: progress == null || progress.total <= 0
                    ? null
                    : (progress.done / progress.total).clamp(0.0, 1.0),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (progress != null)
                          Text(
                            _t(StorageLocale.deleting, {
                              'done': progress.done,
                              'total': progress.total,
                            }),
                            key: const ValueKey('storage-deleting'),
                          ),
                        if (progress?.currentPath != null)
                          Text(
                            progress!.currentPath!,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: storageRawStyle(context),
                          ),
                      ],
                    ),
                  ),
                  const SizedBox(width: 12),
                  _bumperHint(context),
                  LibretroFocusRing(
                    child: OutlinedButton.icon(
                      key: const ValueKey('storage-delete-cancel'),
                      focusNode: _cancelFocus,
                      onPressed: _cancelRequested ? null : _cancelDeletion,
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
    // Only the total and the button follow the ticks.
    return _bar(
      context,
      ValueListenableBuilder<({int count, int bytes})>(
        valueListenable: _selection.totals,
        builder: (context, totals, _) => Row(
          children: [
            Expanded(
              child: Text(
                _t(StorageLocale.selectedTotal, {
                  'count': totals.count,
                  'size': storageSize(totals.bytes),
                }),
                key: const ValueKey('storage-preview-total'),
                style: theme.textTheme.titleSmall,
              ),
            ),
            const SizedBox(width: 12),
            _bumperHint(context),
            LibretroFocusRing(
              child: FilledButton.icon(
                key: const ValueKey('storage-preview-delete'),
                focusNode: _deleteFocus,
                style: FilledButton.styleFrom(
                  backgroundColor: theme.colorScheme.error,
                  foregroundColor: theme.colorScheme.onError,
                ),
                onPressed: totals.count == 0
                    ? null
                    : () => unawaited(_confirmAndDelete()),
                icon: const Icon(Icons.delete_outline_rounded),
                label: Text(_t(StorageLocale.deleteAction)),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// « Analyser à nouveau » stays in sight below the result, however long
  /// its list of refusals.
  Widget _resultBar(BuildContext context) => _bar(
    context,
    Row(
      children: [
        const Spacer(),
        _bumperHint(context),
        LibretroFocusRing(
          child: FilledButton.tonalIcon(
            key: const ValueKey('storage-result-rescan'),
            focusNode: _rescanFocus,
            onPressed: () => Navigator.of(context).maybePop(),
            icon: const Icon(Icons.refresh_rounded),
            label: Text(_t(StorageLocale.scanAgain)),
          ),
        ),
      ],
    ),
  );

  List<Widget> _resultSlivers(BuildContext context) {
    final theme = Theme.of(context);
    final result = _result;
    final failure = _failure;
    final metadata = result?.metadata;
    return [
      SliverToBoxAdapter(
        child: StorageFocusable(
          focusNode: _topFocus,
          child: StorageSectionCard(
            key: const ValueKey('storage-result'),
            icon: Icons.task_alt_rounded,
            title: _t(StorageLocale.resultTitle),
            children: [
              if (result != null) ...[
                Text(
                  _t(StorageLocale.resultDeleted, {
                    'count': result.deletedFiles,
                    'size': storageSize(result.deletedBytes),
                  }),
                  key: const ValueKey('storage-result-deleted'),
                  style: theme.textTheme.titleSmall,
                ),
                Text(
                  _t(StorageLocale.resultSkippedChanged, {
                    'count': result.skippedChanged,
                  }),
                  key: const ValueKey('storage-result-changed'),
                ),
                Text(
                  _t(StorageLocale.resultMissing, {
                    'count': result.skippedMissing,
                  }),
                  key: const ValueKey('storage-result-missing'),
                ),
                Text(
                  _t(StorageLocale.resultRefused, {
                    'count': result.refusals.length,
                  }),
                  key: const ValueKey('storage-result-refused'),
                ),
                if (metadata != null)
                  Text(
                    _t(StorageLocale.resultMetadata, {
                      'count': metadata.deleted,
                    }),
                    key: const ValueKey('storage-result-metadata'),
                  ),
                if (result.cancelled)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      _t(StorageLocale.cancelled),
                      key: const ValueKey('storage-result-cancelled'),
                    ),
                  ),
                if (result.stoppedBySession)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      // A game or an import, or a library scan.
                      _t(
                        StorageLocale.refusalKeys[result.stopReason?.name] ??
                            StorageLocale.sessionActive,
                      ),
                      key: const ValueKey('storage-result-stopped'),
                      style: TextStyle(color: theme.colorScheme.error),
                    ),
                  ),
                if (result.journalDisplayPath != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      _t(StorageLocale.journalSaved, {
                        'path': result.journalDisplayPath,
                      }),
                      key: const ValueKey('storage-result-journal'),
                      style: theme.textTheme.bodySmall,
                    ),
                  ),
                // The translated explanation, then the raw error apart.
                if (result.journalError != null) ...[
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Text(
                      _t(StorageLocale.journalNotSaved),
                      key: const ValueKey('storage-result-journal-error'),
                      style: TextStyle(color: theme.colorScheme.error),
                    ),
                  ),
                  Text(
                    _t(StorageLocale.technicalCode, {
                      'code': result.journalError,
                    }),
                    key: const ValueKey('storage-result-journal-error-code'),
                    style: storageRawStyle(context),
                  ),
                ],
              ],
              if (failure != null) ...[
                Text(
                  _t(StorageLocale.refuseUnknown),
                  key: const ValueKey('storage-result-failure'),
                  style: TextStyle(color: theme.colorScheme.error),
                ),
                Text(
                  _t(StorageLocale.technicalCode, {'code': failure}),
                  style: storageRawStyle(context),
                ),
              ],
            ],
          ),
        ),
      ),
      if (result != null && result.refusals.isNotEmpty)
        _RefusalGroup(
          key: const ValueKey('storage-result-refusals'),
          title: _t(StorageLocale.resultRefused, {
            'count': result.refusals.length,
          }),
          refusals: result.refusals,
          itemKeyPrefix: 'storage-result-refusal',
        ),
    ];
  }
}

/// The boxes of a preview: one notifier per box, the ticked count of each
/// root group and the selected total. A tick notifies only its own box, its
/// group header and the action bar: nothing else is rebuilt, whatever the
/// size of the plan.
class _PreviewSelection {
  _PreviewSelection(StorageCleanupPlan plan, Set<String> initial) {
    var count = 0;
    var bytes = 0;
    for (final candidate in plan.candidates) {
      final ticked = initial.contains(candidate.path);
      _boxes[candidate.path] = ValueNotifier(ticked);
      _candidates[candidate.path] = candidate;
      final group = _groups.putIfAbsent(
        candidate.rootId,
        () => ValueNotifier(0),
      );
      if (ticked) {
        group.value++;
        count++;
        bytes += candidate.logicalBytes;
      }
    }
    if (plan.hasMetadata) {
      final ticked = initial.contains(StorageCleanupPlan.metadataSelectionKey);
      _boxes[StorageCleanupPlan.metadataSelectionKey] = ValueNotifier(ticked);
      if (ticked) count++;
    }
    totals = ValueNotifier((count: count, bytes: bytes));
  }

  final Map<String, ValueNotifier<bool>> _boxes = {};
  final Map<String, StorageCleanupCandidate> _candidates = {};
  final Map<String, ValueNotifier<int>> _groups = {};

  /// Items ticked (the metadata rows count as one) and their logical bytes.
  late final ValueNotifier<({int count, int bytes})> totals;

  ValueListenable<bool> box(String path) => _boxes[path]!;

  /// Ticked candidates of [rootId], for its group header.
  ValueListenable<int> group(String rootId) => _groups[rootId]!;

  int tickedIn(String rootId) => _groups[rootId]?.value ?? 0;

  /// The ticked paths, and [StorageCleanupPlan.metadataSelectionKey] when
  /// the metadata rows are ticked.
  Set<String> get selected => {
    for (final entry in _boxes.entries)
      if (entry.value.value) entry.key,
  };

  void set(String path, bool ticked) {
    final box = _boxes[path];
    if (box == null || box.value == ticked) return;
    box.value = ticked;
    final change = ticked ? 1 : -1;
    final candidate = _candidates[path];
    if (candidate != null) _groups[candidate.rootId]!.value += change;
    final current = totals.value;
    totals.value = (
      count: current.count + change,
      bytes: current.bytes + change * (candidate?.logicalBytes ?? 0),
    );
  }

  void dispose() {
    for (final notifier in _boxes.values) {
      notifier.dispose();
    }
    for (final notifier in _groups.values) {
      notifier.dispose();
    }
    totals.dispose();
  }
}

/// A reason line of a group: its `{count}`/`{size}` are those of the
/// candidates listed under it.
class _ReasonRow {
  const _ReasonRow(this.reasonKey, this.count, this.bytes);

  final String reasonKey;
  final int count;
  final int bytes;
}

/// The candidates of one root: a header (label, raw root id and path,
/// items, ticked items, size) that opens and closes the group, then its
/// rows, built only while on screen.
class _PreviewGroup extends StatefulWidget {
  const _PreviewGroup({
    super.key,
    required this.rootId,
    required this.label,
    required this.rootPath,
    required this.candidates,
    required this.selection,
    required this.initiallyExpanded,
    required this.frozen,
  });

  final String rootId;
  final String label;
  final String? rootPath;
  final List<StorageCleanupCandidate> candidates;
  final _PreviewSelection selection;
  final bool initiallyExpanded;

  /// The deletion runs: boxes cannot change.
  final bool frozen;

  @override
  State<_PreviewGroup> createState() => _PreviewGroupState();
}

class _PreviewGroupState extends State<_PreviewGroup> {
  late bool _expanded = widget.initiallyExpanded;
  late final int _bytes = widget.candidates.fold<int>(
    0,
    (sum, candidate) => sum + candidate.logicalBytes,
  );

  /// Reason lines and candidates, in plan order.
  late final List<Object> _rows = () {
    final reasons = <String, List<StorageCleanupCandidate>>{};
    for (final candidate in widget.candidates) {
      reasons.putIfAbsent(candidate.reasonKey, () => []).add(candidate);
    }
    return <Object>[
      for (final reason in reasons.entries) ...[
        _ReasonRow(
          reason.key,
          reason.value.length,
          reason.value.fold<int>(0, (sum, c) => sum + c.logicalBytes),
        ),
        ...reason.value,
      ],
    ];
  }();

  String _t(String key, [Map<String, Object?> parameters = const {}]) =>
      StorageLocale.text(context, key, parameters);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rootId = widget.rootId;
    final header = LibretroFocusRing(
      radius: 12,
      child: ListTile(
        key: ValueKey('storage-preview-root-header-$rootId'),
        contentPadding: const EdgeInsetsDirectional.only(start: 8, end: 8),
        leading: const Icon(Icons.folder_rounded),
        title: Text(widget.label),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              [rootId, ?widget.rootPath].join(' · '),
              style: storageRawStyle(context),
            ),
            Text(
              _t(StorageLocale.entries, {'count': widget.candidates.length}),
            ),
            ValueListenableBuilder<int>(
              valueListenable: widget.selection.group(rootId),
              builder: (context, ticked, _) => Text(
                _t(StorageLocale.groupSelected, {
                  'count': ticked,
                  'total': widget.candidates.length,
                }),
                key: ValueKey('storage-preview-root-selected-$rootId'),
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ],
        ),
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(storageSize(_bytes)),
            const SizedBox(width: 4),
            Icon(
              _expanded ? Icons.expand_less_rounded : Icons.expand_more_rounded,
              semanticLabel: _t(
                _expanded
                    ? StorageLocale.detailsHide
                    : StorageLocale.detailsShow,
              ),
            ),
          ],
        ),
        onTap: () => setState(() => _expanded = !_expanded),
      ),
    );
    return StorageSliverCard(
      sliver: SliverPadding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        sliver: SliverMainAxisGroup(
          slivers: [
            SliverToBoxAdapter(child: header),
            if (_expanded)
              SliverList.builder(
                itemCount: _rows.length,
                itemBuilder: (context, index) {
                  final row = _rows[index];
                  if (row is _ReasonRow) {
                    return Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(
                        16,
                        8,
                        16,
                        2,
                      ),
                      child: Text(
                        _t(row.reasonKey, {
                          'count': row.count,
                          'size': storageSize(row.bytes),
                        }),
                        style: theme.textTheme.labelLarge,
                      ),
                    );
                  }
                  return _CandidateTile(
                    candidate: row as StorageCleanupCandidate,
                    selection: widget.selection,
                    frozen: widget.frozen,
                  );
                },
              ),
          ],
        ),
      ),
    );
  }
}

/// One candidate: only its box follows the selection.
class _CandidateTile extends StatelessWidget {
  const _CandidateTile({
    required this.candidate,
    required this.selection,
    required this.frozen,
  });

  final StorageCleanupCandidate candidate;
  final _PreviewSelection selection;
  final bool frozen;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final raw = storageRawStyle(context);
    final details = <String>[
      storageSize(candidate.logicalBytes),
      if (candidate.kind == StorageEntryKind.directory)
        StorageLocale.text(context, StorageLocale.entries, {
          'count': candidate.fileCount,
        }),
    ];
    final paired = candidate.pairedDisplayPath;
    final title = Text(candidate.displayPath, style: raw);
    final subtitle = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(details.join(' · ')),
        if (paired != null) ...[
          const SizedBox(height: 2),
          Text(
            StorageLocale.text(context, StorageLocale.duplicateReferenced),
            style: theme.textTheme.labelSmall?.copyWith(
              fontWeight: FontWeight.w600,
            ),
          ),
          Text(paired, style: raw),
        ],
        if (candidate.warningKeys.isNotEmpty) ...[
          const SizedBox(height: 4),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: [
              for (final warning in candidate.warningKeys)
                StorageWarningBadge(
                  key: ValueKey('storage-warning-${candidate.path}-$warning'),
                  text: StorageLocale.text(context, warning),
                ),
            ],
          ),
        ],
      ],
    );
    final path = candidate.path;
    return LibretroFocusRing(
      radius: 12,
      child: ValueListenableBuilder<bool>(
        valueListenable: selection.box(path),
        builder: (context, ticked, _) => CheckboxListTile(
          key: ValueKey('storage-candidate-$path'),
          value: ticked,
          onChanged: frozen
              ? null
              : (value) => selection.set(path, value ?? false),
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: const EdgeInsetsDirectional.only(start: 8, end: 8),
          title: title,
          subtitle: subtitle,
        ),
      ),
    );
  }
}

/// The orphan metadata rows: one box, and their raw keys
/// (`appSystemId / filename`) listed on demand, built only while on screen.
class _MetadataGroup extends StatefulWidget {
  const _MetadataGroup({
    super.key,
    required this.keys,
    required this.selection,
    required this.frozen,
  });

  final List<StorageOrphanMetadataKey> keys;
  final _PreviewSelection selection;
  final bool frozen;

  @override
  State<_MetadataGroup> createState() => _MetadataGroupState();
}

class _MetadataGroupState extends State<_MetadataGroup> {
  bool _expanded = false;

  String _t(String key, [Map<String, Object?> parameters = const {}]) =>
      StorageLocale.text(context, key, parameters);

  @override
  Widget build(BuildContext context) {
    final raw = storageRawStyle(context);
    const key = StorageCleanupPlan.metadataSelectionKey;
    return StorageSliverCard(
      sliver: SliverPadding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        sliver: SliverMainAxisGroup(
          slivers: [
            SliverToBoxAdapter(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  LibretroFocusRing(
                    radius: 12,
                    child: ValueListenableBuilder<bool>(
                      valueListenable: widget.selection.box(key),
                      builder: (context, ticked, _) => CheckboxListTile(
                        key: const ValueKey('storage-candidate-metadata'),
                        value: ticked,
                        onChanged: widget.frozen
                            ? null
                            : (value) =>
                                  widget.selection.set(key, value ?? false),
                        controlAffinity: ListTileControlAffinity.leading,
                        contentPadding: const EdgeInsetsDirectional.only(
                          start: 8,
                          end: 8,
                        ),
                        title: Text(
                          _t(StorageLocale.orphanMetadata, {
                            'count': widget.keys.length,
                          }),
                        ),
                        subtitle: Text(_t(StorageLocale.metadataBackupNote)),
                      ),
                    ),
                  ),
                  LibretroFocusRing(
                    radius: 12,
                    child: ListTile(
                      key: const ValueKey('storage-preview-metadata-details'),
                      contentPadding: const EdgeInsetsDirectional.only(
                        start: 24,
                        end: 8,
                      ),
                      title: Text(
                        _t(
                          _expanded
                              ? StorageLocale.detailsHide
                              : StorageLocale.detailsShow,
                        ),
                      ),
                      trailing: Icon(
                        _expanded
                            ? Icons.expand_less_rounded
                            : Icons.expand_more_rounded,
                      ),
                      onTap: () => setState(() => _expanded = !_expanded),
                    ),
                  ),
                ],
              ),
            ),
            if (_expanded)
              SliverList.builder(
                itemCount: widget.keys.length,
                itemBuilder: (context, index) {
                  final row = widget.keys[index];
                  return StorageFocusable(
                    key: ValueKey('storage-metadata-key-$index'),
                    radius: 8,
                    child: Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(
                        24,
                        4,
                        16,
                        4,
                      ),
                      child: Text(
                        '${row.appSystemId} / ${row.filename}',
                        style: raw,
                      ),
                    ),
                  );
                },
              ),
          ],
        ),
      ),
    );
  }
}

/// Refused paths (session guards of the preview, or the result), built
/// only while on screen.
class _RefusalGroup extends StatelessWidget {
  const _RefusalGroup({
    super.key,
    required this.title,
    required this.refusals,
    required this.itemKeyPrefix,
    this.greyed = false,
  });

  final String title;
  final List<StoragePlanRefusal> refusals;
  final String itemKeyPrefix;

  /// Left out by the session guards: shown greyed.
  final bool greyed;

  @override
  Widget build(BuildContext context) => StorageSliverCard(
    spacing: 16,
    sliver: SliverPadding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
      sliver: SliverMainAxisGroup(
        slivers: [
          SliverToBoxAdapter(
            child: StorageSectionTitle(icon: Icons.block_rounded, title: title),
          ),
          SliverList.builder(
            itemCount: refusals.length,
            itemBuilder: (context, index) {
              final lines = _RefusalLines(refusal: refusals[index]);
              return StorageFocusable(
                key: ValueKey('$itemKeyPrefix-$index'),
                child: greyed ? Opacity(opacity: 0.6, child: lines) : lines,
              );
            },
          ),
        ],
      ),
    ),
  );
}

/// A refused path: the translated reason, then the raw technical code (the
/// errno text, the RPCS3 code, …) and the raw path, apart.
class _RefusalLines extends StatelessWidget {
  const _RefusalLines({required this.refusal});

  final StoragePlanRefusal refusal;

  @override
  Widget build(BuildContext context) {
    final code = refusal.detail ?? refusal.errorCode;
    final path = refusal.displayPath ?? refusal.path;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(StorageLocale.text(context, refusal.localeKey)),
          if (code != null)
            Text(
              StorageLocale.text(context, StorageLocale.technicalCode, {
                'code': code,
              }),
              style: storageRawStyle(context),
            ),
          if (path.isNotEmpty) Text(path, style: storageRawStyle(context)),
        ],
      ),
    );
  }
}

/// « Supprimer les éléments sélectionnés ? »: the number of items, their
/// size, the orphan metadata rows when ticked and every warning of the
/// selection. It carries its own controller layer (the page's is paused
/// meanwhile): the D-pad moves between Cancel and Delete, A activates the
/// one shown, B cancels.
class _ConfirmDeletionDialog extends StatefulWidget {
  const _ConfirmDeletionDialog({
    required this.count,
    required this.size,
    required this.warningKeys,
    this.metadataCount,
  });

  final int count;
  final String size;
  final List<String> warningKeys;

  /// Orphan metadata rows ticked (null when they are not).
  final int? metadataCount;

  @override
  State<_ConfirmDeletionDialog> createState() => _ConfirmDeletionDialogState();
}

class _ConfirmDeletionDialogState extends State<_ConfirmDeletionDialog>
    with LibretroPageNavigation<_ConfirmDeletionDialog> {
  String _t(String key, [Map<String, Object?> parameters = const {}]) =>
      StorageLocale.text(context, key, parameters);

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final metadata = widget.metadataCount;
    return libretroPage(
      AlertDialog(
        key: const ValueKey('storage-confirm-dialog'),
        title: Row(
          children: [
            Icon(Icons.delete_outline_rounded, color: scheme.error),
            const SizedBox(width: 8),
            Flexible(child: Text(_t(StorageLocale.confirmTitle))),
          ],
        ),
        content: SizedBox(
          width: 480,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _t(StorageLocale.confirmBody, {
                    'count': widget.count,
                    'size': widget.size,
                  }),
                  key: const ValueKey('storage-confirm-body'),
                ),
                if (metadata != null) ...[
                  const SizedBox(height: 6),
                  Text(
                    _t(StorageLocale.orphanMetadata, {'count': metadata}),
                    key: const ValueKey('storage-confirm-metadata'),
                  ),
                ],
                if (widget.warningKeys.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    _t(StorageLocale.warningTitle),
                    style: theme.textTheme.labelLarge,
                  ),
                  for (final warning in widget.warningKeys)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: StorageWarningBadge(
                        key: ValueKey('storage-confirm-warning-$warning'),
                        text: _t(warning),
                      ),
                    ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          LibretroFocusRing(
            child: TextButton(
              key: const ValueKey('storage-confirm-cancel'),
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(_t(StorageLocale.cancel)),
            ),
          ),
          LibretroFocusRing(
            child: FilledButton(
              key: const ValueKey('storage-confirm-delete'),
              style: FilledButton.styleFrom(
                backgroundColor: scheme.error,
                foregroundColor: scheme.onError,
              ),
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(_t(StorageLocale.deleteAction)),
            ),
          ),
        ],
      ),
    );
  }
}
