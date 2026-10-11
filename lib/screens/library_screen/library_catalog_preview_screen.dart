import 'package:flutter/material.dart';

import 'package:neostation/l10n/library_sources_locale.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';

import 'library_sources_view.dart';

/// Preview of a catalogue before anything is installed (Build 437): one row
/// per source with its icon, languages, version, rating and whether
/// NeoStation has a reader for it. Nothing is ever pre-selected; "Activate"
/// installs exactly the ticked sources, then a summary lists what was added,
/// updated or skipped, and the route pops with the
/// [LibraryActivationResult] (null when nothing was activated).
class LibraryCatalogPreviewScreen extends StatefulWidget {
  const LibraryCatalogPreviewScreen({
    super.key,
    required this.preview,
    this.catalogService,
    this.aidokuService,
    this.imageCache,
    this.enableGamepad = true,
  });

  final LibraryCatalogPreview preview;

  /// Defaults to [LibrarySourceCatalogService.instance].
  final LibrarySourceCatalogService? catalogService;
  final LibraryAidokuNativeService? aidokuService;
  final LibraryImageCache? imageCache;
  final bool enableGamepad;

  static Future<LibraryActivationResult?> open(
    BuildContext context,
    LibraryCatalogPreview preview, {
    LibrarySourceCatalogService? catalogService,
    LibraryAidokuNativeService? aidokuService,
    LibraryImageCache? imageCache,
    bool enableGamepad = true,
  }) {
    return Navigator.of(context).push<LibraryActivationResult>(
      MaterialPageRoute<LibraryActivationResult>(
        builder: (_) => LibraryCatalogPreviewScreen(
          preview: preview,
          catalogService: catalogService,
          aidokuService: aidokuService,
          imageCache: imageCache,
          enableGamepad: enableGamepad,
        ),
      ),
    );
  }

  @override
  State<LibraryCatalogPreviewScreen> createState() =>
      _LibraryCatalogPreviewScreenState();
}

class _LibraryCatalogPreviewScreenState
    extends State<LibraryCatalogPreviewScreen>
    with LibraryDateFormatPreload<LibraryCatalogPreviewScreen> {
  /// Ticked source ids. Empty when the screen opens.
  final Set<String> _selected = <String>{};
  bool _activating = false;

  LibraryCatalogPreview get _preview => widget.preview;
  LibrarySourceCatalogService get _catalogService =>
      widget.catalogService ?? LibrarySourceCatalogService.instance;
  LibraryAidokuNativeService get _aidoku =>
      widget.aidokuService ?? LibraryAidokuNativeService.instance;

  String _t(String key) => LibrarySourcesLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      LibrarySourcesLocale.format(context, key, values);

  bool _hasReader(LibraryCatalogSourceEntry entry) {
    if (!entry.activatable || !_preview.isActivatable) return false;
    if (!_preview.format.isAidoku) return true;
    return _aidoku.supportFor(entry.id).hasAdapter;
  }

  bool _selectable(LibraryCatalogSourceEntry entry) =>
      entry.activatable && _preview.isActivatable;

  void _toggle(LibraryCatalogSourceEntry entry) {
    if (!_selectable(entry) || _activating) return;
    setState(() {
      if (!_selected.remove(entry.id)) _selected.add(entry.id);
    });
  }

  void _selectWithReader() {
    setState(() {
      for (final entry in _preview.sources) {
        final current = entry.alreadyInstalled && !entry.updateAvailable;
        if (_hasReader(entry) && !current) _selected.add(entry.id);
      }
    });
  }

  Future<void> _activate() async {
    if (_selected.isEmpty || _activating) return;
    setState(() => _activating = true);
    final LibraryActivationResult result;
    try {
      result = await _catalogService.activate(_preview, Set.of(_selected));
    } on Object catch (error) {
      if (!mounted) return;
      setState(() => _activating = false);
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => LibraryFocusGamepadLayer(
          enableGamepad: widget.enableGamepad,
          debugLabel: 'preview_error',
          child: AlertDialog(
            title: Text(
              LibrarySourcesLocale.text(dialogContext, 'activationFailed'),
            ),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  LibrarySourcesLocale.text(
                    dialogContext,
                    LibrarySourcesLocale.errorKey(error),
                  ),
                ),
                LibraryTechnicalDetails(
                  detail: LibrarySourcesLocale.technicalDetail(error),
                ),
              ],
            ),
            actions: <Widget>[
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: Text(LibrarySourcesLocale.text(dialogContext, 'close')),
              ),
            ],
          ),
        ),
      );
      return;
    }
    if (!mounted) return;
    setState(() => _activating = false);
    await showDialog<void>(
      context: context,
      builder: (_) => _ActivationSummaryDialog(
        preview: _preview,
        result: result,
        enableGamepad: widget.enableGamepad,
      ),
    );
    if (!mounted) return;
    Navigator.of(context).pop(result);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final preview = _preview;
    final count = _selected.length;
    // Leaving while the sources are being activated would drop the result:
    // the sources view would not tell the Library hub that its source list
    // changed. Back (button, swipe, controller B) waits for the summary.
    return PopScope(
      canPop: !_activating,
      child: LibraryFocusGamepadLayer(
        enableGamepad: widget.enableGamepad,
        debugLabel: 'catalog_preview',
        child: Scaffold(
          appBar: AppBar(
            title: Text(preview.name ?? _t('previewTitle')),
            leading: const ExcludeFocus(child: BackButton()),
          ),
          body: SafeArea(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                // The catalogue information and the selection buttons scroll
                // with the sources: fixed, they left room for less than two
                // rows on an iPhone in landscape. "Activate" stays in view.
                Expanded(
                  child: CustomScrollView(
                    key: const ValueKey<String>('preview-scroll'),
                    slivers: <Widget>[
                      SliverToBoxAdapter(child: _buildInfo(theme)),
                      if (!preview.isActivatable)
                        SliverToBoxAdapter(child: _buildTachiyomiBanner(theme)),
                      if (preview.isActivatable && preview.sources.isNotEmpty)
                        SliverToBoxAdapter(child: _buildSelectionBar(count)),
                      if (preview.sources.isEmpty)
                        SliverFillRemaining(
                          hasScrollBody: false,
                          child: Center(child: Text(_t('noSourcesInCatalog'))),
                        )
                      else
                        SliverPadding(
                          padding: const EdgeInsets.only(bottom: 12),
                          sliver: SliverList.builder(
                            itemCount: preview.sources.length,
                            itemBuilder: (context, index) {
                              final entry = preview.sources[index];
                              return _EntryRow(
                                key: ValueKey<String>('entry-${entry.id}'),
                                entry: entry,
                                selected: _selected.contains(entry.id),
                                selectable: _selectable(entry),
                                aidokuFormat: preview.format.isAidoku,
                                hasReader: _hasReader(entry),
                                unsupportedKey: _unsupportedKey(entry),
                                imageCache: widget.imageCache,
                                onToggle: () => _toggle(entry),
                              );
                            },
                          ),
                        ),
                    ],
                  ),
                ),
                if (preview.isActivatable)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 12),
                    child: Row(
                      children: <Widget>[
                        if (_activating) ...<Widget>[
                          const SizedBox(
                            width: 22,
                            height: 22,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          const SizedBox(width: 10),
                          Text(_t('activating')),
                        ],
                        const Spacer(),
                        FilledButton.icon(
                          key: const ValueKey<String>('activate-button'),
                          onPressed: count == 0 || _activating
                              ? null
                              : _activate,
                          icon: const Icon(Icons.download_done),
                          label: Text(
                            _f('activateCount', <String, Object?>{
                              'count': count,
                            }),
                          ),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildSelectionBar(int count) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 4),
      child: Wrap(
        spacing: 8,
        runSpacing: 4,
        children: <Widget>[
          OutlinedButton.icon(
            onPressed: _activating ? null : _selectWithReader,
            icon: const Icon(Icons.done_all),
            label: Text(_t('selectWithAdapter')),
          ),
          if (count > 0)
            TextButton(
              onPressed: _activating ? null : () => setState(_selected.clear),
              child: Text(_t('clearSelection')),
            ),
        ],
      ),
    );
  }

  String? _unsupportedKey(LibraryCatalogSourceEntry entry) {
    if (!_preview.format.isAidoku || !entry.activatable) return null;
    final support = _aidoku.supportFor(entry.id);
    if (support.hasAdapter) {
      return support.knownState == LibrarySourceKnownState.working
          ? null
          : LibrarySourcesLocale.knownStateKey(support.knownState);
    }
    final reason = support.unsupportedReason;
    return reason == null
        ? 'reasonAdapterMissing'
        : LibrarySourcesLocale.unsupportedReasonKey(reason);
  }

  Widget _buildInfo(ThemeData theme) {
    final preview = _preview;
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.66);
    final date = libraryShortDate(context, preview.fetchedAt);
    final String origin;
    if (preview.isLocalFile) {
      origin = _t('previewLocalFile');
    } else if (preview.stale) {
      origin = _f('previewStale', <String, Object?>{'date': date});
    } else if (preview.fromCache) {
      origin = _f('previewCached', <String, Object?>{'date': date});
    } else {
      origin = _f('previewFetched', <String, Object?>{'date': date});
    }
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            _t(_formatKey(preview.format)),
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          if (!preview.isLocalFile)
            SelectableText(
              preview.catalogUrl,
              maxLines: 2,
              style: theme.textTheme.bodySmall?.copyWith(color: muted),
            ),
          Text(
            '${_f('sourceCount', <String, Object?>{'count': preview.sources.length})} • $origin',
            style: theme.textTheme.bodySmall?.copyWith(color: muted),
          ),
        ],
      ),
    );
  }

  Widget _buildTachiyomiBanner(ThemeData theme) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 6, 16, 6),
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: theme.colorScheme.secondaryContainer,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(
                Icons.info_outline,
                color: theme.colorScheme.onSecondaryContainer,
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  _t('tachiyomiBanner'),
                  key: const ValueKey<String>('tachiyomi-banner'),
                  style: TextStyle(
                    color: theme.colorScheme.onSecondaryContainer,
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static String _formatKey(LibraryCatalogFormat format) => switch (format) {
    LibraryCatalogFormat.aidokuLegacyIndex => 'formatAidokuLegacyIndex',
    LibraryCatalogFormat.aidokuIndex => 'formatAidokuIndex',
    LibraryCatalogFormat.aidokuSourceJson => 'formatAidokuSourceJson',
    LibraryCatalogFormat.aidokuPackage => 'formatAidokuPackage',
    LibraryCatalogFormat.neoStationManifest => 'formatNeoStationManifest',
    LibraryCatalogFormat.tachiyomiRepository => 'formatTachiyomiRepository',
  };
}

class _EntryRow extends StatelessWidget {
  const _EntryRow({
    super.key,
    required this.entry,
    required this.selected,
    required this.selectable,
    required this.aidokuFormat,
    required this.hasReader,
    required this.unsupportedKey,
    required this.onToggle,
    this.imageCache,
  });

  final LibraryCatalogSourceEntry entry;
  final bool selected;
  final bool selectable;
  final bool aidokuFormat;
  final bool hasReader;
  final String? unsupportedKey;
  final VoidCallback onToggle;
  final LibraryImageCache? imageCache;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String t(String key) => LibrarySourcesLocale.text(context, key);
    String f(String key, Map<String, Object?> values) =>
        LibrarySourcesLocale.format(context, key, values);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.66);
    const iconSize = 40.0;
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final cacheWidth = (iconSize * dpr).round();
    Widget icon = Icon(Icons.extension, color: theme.colorScheme.primary);
    final bytes = entry.iconBytes;
    final url = entry.iconUrl;
    if (bytes != null && bytes.isNotEmpty) {
      icon = Image.memory(
        bytes,
        cacheWidth: cacheWidth,
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) =>
            Icon(Icons.extension, color: theme.colorScheme.primary),
      );
    } else if (url != null) {
      icon = Image(
        image: LibraryNetworkImage(
          url,
          cacheWidth: cacheWidth,
          cache: imageCache,
        ),
        fit: BoxFit.cover,
        errorBuilder: (_, _, _) =>
            Icon(Icons.extension, color: theme.colorScheme.primary),
      );
    }

    final details = <String>[
      if (entry.languages.isNotEmpty)
        f('languages', <String, Object?>{
          'languages': entry.languages.join(', '),
        }),
      f('version', <String, Object?>{'version': entry.versionLabel}),
    ];
    final installState = entry.updateAvailable
        ? f('updateAvailable', <String, Object?>{'version': entry.versionLabel})
        : entry.alreadyInstalled
        ? f('installedVersion', <String, Object?>{
            'version': entry.installedVersionLabel ?? entry.versionLabel,
          })
        : null;

    return LibraryFocusRing(
      radius: 10,
      child: Semantics(
        label: f('selectSource', <String, Object?>{'name': entry.name}),
        checked: selected,
        enabled: selectable,
        // A row that cannot be ticked (Tachiyomi, not activatable) still
        // takes the focus, so a controller can scroll through the list.
        child: Focus(
          canRequestFocus: !selectable,
          skipTraversal: selectable,
          child: InkWell(
            onTap: selectable ? onToggle : null,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minHeight: 56),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                child: Row(
                  children: <Widget>[
                    ExcludeFocus(
                      child: Checkbox(
                        value: selected,
                        onChanged: selectable ? (_) => onToggle() : null,
                      ),
                    ),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: SizedBox(
                        width: iconSize,
                        height: iconSize,
                        child: icon,
                      ),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Text(
                            entry.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.titleSmall?.copyWith(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          Text(
                            details.join(' • '),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                            style: theme.textTheme.bodySmall?.copyWith(
                              color: muted,
                            ),
                          ),
                          const SizedBox(height: 4),
                          Wrap(
                            spacing: 6,
                            runSpacing: 4,
                            children: <Widget>[
                              LibraryRatingBadge(rating: entry.contentRating),
                              if (installState != null)
                                LibraryStatusChip(
                                  label: installState,
                                  state: entry.updateAvailable
                                      ? LibraryLadderState.unknown
                                      : LibraryLadderState.ok,
                                ),
                              if (aidokuFormat && hasReader)
                                LibraryStatusChip(
                                  label: t('adapterAvailable'),
                                  state: LibraryLadderState.ok,
                                ),
                              if (unsupportedKey != null)
                                LibraryStatusChip(
                                  label: t(unsupportedKey!),
                                  state: LibraryLadderState.failed,
                                ),
                            ],
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _ActivationSummaryDialog extends StatelessWidget {
  const _ActivationSummaryDialog({
    required this.preview,
    required this.result,
    required this.enableGamepad,
  });

  final LibraryCatalogPreview preview;
  final LibraryActivationResult result;
  final bool enableGamepad;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String t(String key) => LibrarySourcesLocale.text(context, key);
    String f(String key, Map<String, Object?> values) =>
        LibrarySourcesLocale.format(context, key, values);
    String nameOf(String id) => preview.sourceById(id)?.name ?? id;
    String reason(LibraryActivationSkip skip) => switch (skip.reason) {
      LibraryActivationSkipReason.notInCatalog => t('skipNotInCatalog'),
      LibraryActivationSkipReason.notActivatable => t('skipNotActivatable'),
      LibraryActivationSkipReason.newerVersionInstalled => f(
        'skipNewerInstalled',
        <String, Object?>{'installed': skip.installedVersion ?? '?'},
      ),
      LibraryActivationSkipReason.invalidEntry => t('skipInvalidEntry'),
    };
    return LibraryFocusGamepadLayer(
      enableGamepad: enableGamepad,
      debugLabel: 'preview_summary',
      child: AlertDialog(
        title: Text(t('summaryTitle')),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  f('summaryAdded', <String, Object?>{
                    'count': result.added.length,
                  }),
                  key: const ValueKey<String>('summary-added'),
                  style: theme.textTheme.titleSmall,
                ),
                for (final addon in result.added) Text('• ${addon.name}'),
                const SizedBox(height: 6),
                Text(
                  f('summaryUpdated', <String, Object?>{
                    'count': result.updated.length,
                  }),
                  key: const ValueKey<String>('summary-updated'),
                  style: theme.textTheme.titleSmall,
                ),
                for (final addon in result.updated) Text('• ${addon.name}'),
                if (result.skipped.isNotEmpty) ...<Widget>[
                  const SizedBox(height: 6),
                  Text(
                    f('summarySkipped', <String, Object?>{
                      'count': result.skipped.length,
                    }),
                    key: const ValueKey<String>('summary-skipped'),
                    style: theme.textTheme.titleSmall,
                  ),
                  for (final skip in result.skipped) ...<Widget>[
                    Text('• ${nameOf(skip.id)} – ${reason(skip)}'),
                    if (skip.detail != null)
                      LibraryTechnicalDetails(detail: skip.detail!),
                  ],
                ],
                if (!result.catalogRemembered &&
                    !preview.isLocalFile &&
                    result.changed) ...<Widget>[
                  const SizedBox(height: 8),
                  Text(t('notRemembered')),
                ],
              ],
            ),
          ),
        ),
        actions: <Widget>[
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(t('done')),
          ),
        ],
      ),
    );
  }
}
