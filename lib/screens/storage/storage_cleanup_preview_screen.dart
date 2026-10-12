import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n/storage_locale.dart';
import '../../repositories/storage_maintenance_repository.dart';
import '../../services/logger_service.dart';
import '../../services/storage/storage_deletion_manager.dart';
import '../../services/storage/storage_report.dart';
import '../../services/storage/storage_roots.dart';
import '../../services/storage/storage_scanner.dart';
import '../libretro/libretro_skin_manager_screen.dart';
import 'storage_screen_widgets.dart';

/// Preview of one cleanup level (docs/storage-audit-cleanup.md § 3.10), the
/// only page of NeoStation that deletes storage: the candidates of the plan
/// by root, each with its box (levels 1 and 2 ticked, level 3 never), its
/// raw path, its size and its warning badges, the orphan metadata rows as one
/// box, the paths the session guards left out (greyed) and the selected
/// total. « Supprimer » asks for a confirmation that repeats the warnings,
/// the number of items and their size; the deletion manager then deletes
/// exactly the ticked items (each one checked again, § 3.8), with its
/// progress and a cancel button, and the page shows its result: deleted,
/// changed since the preview, already gone, refused (translated reason, raw
/// technical code and raw path) and the journal. Going back runs a new
/// analysis ([onFinished]).
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

  @override
  State<StorageCleanupPreviewScreen> createState() =>
      _StorageCleanupPreviewScreenState();
}

class _StorageCleanupPreviewScreenState
    extends State<StorageCleanupPreviewScreen>
    with LibretroPageNavigation<StorageCleanupPreviewScreen> {
  static final _log = LoggerService.instance;

  /// Groups larger than this start closed (the D-pad reaches the next group
  /// without walking through every item).
  static const int _openGroupLimit = 50;

  /// Initial selection: levels 1 and 2 ticked, level 3 never, the metadata
  /// rows at levels 2 and 3 (§ 3.7).
  late final Set<String> _selection = {...widget.plan.preselectedPaths};
  final ValueNotifier<StorageDeletionProgress?> _progress = ValueNotifier(null);
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
  void dispose() {
    _cancel?.cancel();
    _progress.dispose();
    super.dispose();
  }

  void _toggle(String path, bool selected) {
    if (_running || _finished) return;
    setState(() {
      if (selected) {
        _selection.add(path);
      } else {
        _selection.remove(path);
      }
    });
  }

  /// The confirmation, then the deletion of exactly the ticked items.
  Future<void> _confirmAndDelete() async {
    if (_running || _finished) return;
    final plan = _plan;
    final selection = Set<String>.of(_selection);
    final count = plan.countOf(selection);
    if (count == 0) return;
    final size = storageSize(plan.bytesOf(selection));
    final warnings = plan.warningKeysOf(selection);
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
    final actions = !_finished && !plan.blocked && !plan.isEmpty;
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
                // Every row is built (no lazy list): the D-pad always
                // reaches the next one.
                child: SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: _finished
                        ? _resultView(context)
                        : _previewView(context),
                  ),
                ),
              ),
            ),
          ),
          bottomNavigationBar: actions ? _actionBar(context) : null,
        ),
      ),
    );
  }

  List<Widget> _previewView(BuildContext context) {
    final theme = Theme.of(context);
    final plan = _plan;
    final level = widget.level;
    final confirmed = level == StorageCleanupLevel.confirmed;
    return [
      StorageFocusable(
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
      if (plan.blocked)
        StorageFocusable(
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
        )
      else ...[
        if (plan.isEmpty)
          StorageFocusable(
            child: Card(
              key: const ValueKey('storage-preview-empty'),
              margin: const EdgeInsets.only(bottom: 16),
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: Text(_t(StorageLocale.nothingToClean)),
              ),
            ),
          ),
        for (final group in plan.candidatesByRoot.entries)
          _rootGroup(context, group.key, group.value),
        if (plan.hasMetadata) _metadataCard(context),
        if (plan.refusals.isNotEmpty)
          StorageSectionCard(
            key: const ValueKey('storage-preview-refusals'),
            icon: Icons.block_rounded,
            title: _t(StorageLocale.resultRefused, {
              'count': plan.refusals.length,
            }),
            children: [
              for (final (index, refusal) in plan.refusals.indexed)
                StorageFocusable(
                  key: ValueKey('storage-preview-refusal-$index'),
                  child: Opacity(
                    opacity: 0.6,
                    child: _RefusalLines(refusal: refusal),
                  ),
                ),
            ],
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

  Widget _rootGroup(
    BuildContext context,
    String rootId,
    List<StorageCleanupCandidate> candidates,
  ) {
    final bytes = candidates.fold<int>(0, (sum, c) => sum + c.logicalBytes);
    final path = _rootPath(rootId);
    // Candidates sharing a reason, in plan order: their {count}/{size} are
    // those of the candidates listed under the reason.
    final reasons = <String, List<StorageCleanupCandidate>>{};
    for (final candidate in candidates) {
      reasons.putIfAbsent(candidate.reasonKey, () => []).add(candidate);
    }
    final theme = Theme.of(context);
    return Card(
      key: ValueKey('storage-preview-root-$rootId'),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.symmetric(vertical: 4),
        child: StorageExpandableTile(
          headerKey: ValueKey('storage-preview-root-header-$rootId'),
          initiallyExpanded: _plan.candidates.length <= _openGroupLimit,
          leading: const Icon(Icons.folder_rounded),
          title: Text(_rootLabel(rootId, candidates.first)),
          subtitle: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                [rootId, ?path].join(' · '),
                style: storageRawStyle(context),
              ),
              Text(_t(StorageLocale.entries, {'count': candidates.length})),
            ],
          ),
          trailing: Text(storageSize(bytes)),
          childrenBuilder: (context) => [
            for (final reason in reasons.entries) ...[
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(16, 8, 16, 2),
                child: Text(
                  _t(reason.key, {
                    'count': reason.value.length,
                    'size': storageSize(
                      reason.value.fold<int>(
                        0,
                        (sum, c) => sum + c.logicalBytes,
                      ),
                    ),
                  }),
                  style: theme.textTheme.labelLarge,
                ),
              ),
              for (final candidate in reason.value)
                _candidateTile(context, candidate),
            ],
          ],
        ),
      ),
    );
  }

  Widget _candidateTile(
    BuildContext context,
    StorageCleanupCandidate candidate,
  ) {
    final theme = Theme.of(context);
    final raw = storageRawStyle(context);
    final details = <String>[
      storageSize(candidate.logicalBytes),
      if (candidate.kind == StorageEntryKind.directory)
        _t(StorageLocale.entries, {'count': candidate.fileCount}),
    ];
    final paired = candidate.pairedDisplayPath;
    return LibretroFocusRing(
      radius: 12,
      child: CheckboxListTile(
        key: ValueKey('storage-candidate-${candidate.path}'),
        value: _selection.contains(candidate.path),
        onChanged: _running
            ? null
            : (value) => _toggle(candidate.path, value ?? false),
        controlAffinity: ListTileControlAffinity.leading,
        contentPadding: const EdgeInsetsDirectional.only(start: 8, end: 8),
        title: Text(candidate.displayPath, style: raw),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(details.join(' · ')),
            if (paired != null) ...[
              const SizedBox(height: 2),
              Text(
                _t(StorageLocale.duplicateReferenced),
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
                      key: ValueKey(
                        'storage-warning-${candidate.path}-$warning',
                      ),
                      text: _t(warning),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _metadataCard(BuildContext context) => Card(
    key: const ValueKey('storage-preview-metadata'),
    margin: const EdgeInsets.only(bottom: 12),
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: LibretroFocusRing(
        radius: 12,
        child: CheckboxListTile(
          key: const ValueKey('storage-candidate-metadata'),
          value: _selection.contains(StorageCleanupPlan.metadataSelectionKey),
          onChanged: _running
              ? null
              : (value) => _toggle(
                  StorageCleanupPlan.metadataSelectionKey,
                  value ?? false,
                ),
          controlAffinity: ListTileControlAffinity.leading,
          contentPadding: const EdgeInsetsDirectional.only(start: 8, end: 8),
          title: Text(
            _t(StorageLocale.orphanMetadata, {
              'count': _plan.metadataKeys.length,
            }),
          ),
          subtitle: Text(_t(StorageLocale.metadataBackupNote)),
        ),
      ),
    ),
  );

  Widget _actionBar(BuildContext context) {
    final theme = Theme.of(context);
    final plan = _plan;
    final count = plan.countOf(_selection);
    final bytes = plan.bytesOf(_selection);
    return Material(
      elevation: 8,
      color: theme.colorScheme.surfaceContainer,
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 10),
          child: _running
              ? ValueListenableBuilder<StorageDeletionProgress?>(
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
                          LibretroFocusRing(
                            child: OutlinedButton.icon(
                              key: const ValueKey('storage-delete-cancel'),
                              onPressed: _cancelRequested
                                  ? null
                                  : _cancelDeletion,
                              icon: const Icon(Icons.close_rounded),
                              label: Text(_t(StorageLocale.cancel)),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                )
              : Row(
                  children: [
                    Expanded(
                      child: Text(
                        _t(StorageLocale.selectedTotal, {
                          'count': count,
                          'size': storageSize(bytes),
                        }),
                        key: const ValueKey('storage-preview-total'),
                        style: theme.textTheme.titleSmall,
                      ),
                    ),
                    const SizedBox(width: 12),
                    LibretroFocusRing(
                      child: FilledButton.icon(
                        key: const ValueKey('storage-preview-delete'),
                        style: FilledButton.styleFrom(
                          backgroundColor: theme.colorScheme.error,
                          foregroundColor: theme.colorScheme.onError,
                        ),
                        onPressed: count == 0
                            ? null
                            : () => unawaited(_confirmAndDelete()),
                        icon: const Icon(Icons.delete_outline_rounded),
                        label: Text(_t(StorageLocale.deleteAction)),
                      ),
                    ),
                  ],
                ),
        ),
      ),
    );
  }

  List<Widget> _resultView(BuildContext context) {
    final theme = Theme.of(context);
    final result = _result;
    final failure = _failure;
    final metadata = result?.metadata;
    return [
      StorageFocusable(
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
                  _t(StorageLocale.resultMetadata, {'count': metadata.deleted}),
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
                    _t(StorageLocale.sessionActive),
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
              if (result.journalError != null)
                Text(
                  _t(StorageLocale.technicalCode, {
                    'code': result.journalError,
                  }),
                  style: storageRawStyle(context),
                ),
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
      if (result != null && result.refusals.isNotEmpty)
        StorageSectionCard(
          key: const ValueKey('storage-result-refusals'),
          icon: Icons.block_rounded,
          title: _t(StorageLocale.resultRefused, {
            'count': result.refusals.length,
          }),
          children: [
            for (final (index, refusal) in result.refusals.indexed)
              StorageFocusable(
                key: ValueKey('storage-result-refusal-$index'),
                child: _RefusalLines(refusal: refusal),
              ),
          ],
        ),
      Align(
        alignment: AlignmentDirectional.centerStart,
        child: LibretroFocusRing(
          child: FilledButton.tonalIcon(
            key: const ValueKey('storage-result-rescan'),
            onPressed: () => Navigator.of(context).maybePop(),
            icon: const Icon(Icons.refresh_rounded),
            label: Text(_t(StorageLocale.scanAgain)),
          ),
        ),
      ),
    ];
  }
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
/// size and every warning of the selection. It carries its own controller
/// layer (the page's is paused meanwhile): the D-pad moves between Cancel
/// and Delete, A activates the one shown, B cancels.
class _ConfirmDeletionDialog extends StatefulWidget {
  const _ConfirmDeletionDialog({
    required this.count,
    required this.size,
    required this.warningKeys,
  });

  final int count;
  final String size;
  final List<String> warningKeys;

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
