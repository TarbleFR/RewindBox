import '../l10n/melonx_transfer_locale.dart';
import 'melonx_transfer_dialog.dart';
import 'playlist_import_button.dart';
import 'dart:io';
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/melonx_library_locale.dart';
import '../providers/sqlite_config_provider.dart';
import '../services/logger_service.dart';
import '../services/melonx_internal_service.dart';
import '../services/melonx_embedded_library_service.dart';
import '../services/melonx_library_scanner.dart';
import '../services/melonx_file_transaction.dart';

class MelonxInternalPlaylistActions extends StatefulWidget {
  const MelonxInternalPlaylistActions({
    super.key,
    required this.onLibraryChanged,
    this.onInteractionChanged,
    this.embedded = false,
    this.gamePath,
    this.titleId,
    this.onDelete,
  });
  final Future<void> Function() onLibraryChanged;
  final ValueChanged<bool>? onInteractionChanged;
  final bool embedded;
  final String? gamePath;
  final String? titleId;
  final Future<void> Function()? onDelete;
  @override
  State<MelonxInternalPlaylistActions> createState() =>
      _MelonxInternalPlaylistActionsState();
}

class _MelonxInternalPlaylistActionsState
    extends State<MelonxInternalPlaylistActions>
    with WidgetsBindingObserver {
  bool _busy = false;
  bool _interacting = false;
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    WidgetsBinding.instance.addPostFrameCallback((_) => unawaited(_discover()));
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && !_busy) unawaited(_discover());
  }

  Future<void> _discover() async {
    if (!mounted) return;
    try {
      await MelonxInternalService.editLibrary(() async {
        await MelonxFileTransaction.recover(
          await MelonxInternalService.rootDirectory(),
        );
      });
      if (!mounted) return;
      final changed = await MelonxLibraryScanner.refresh(
        context.read<SqliteConfigProvider>(),
      );
      if (changed > 0 && mounted) await widget.onLibraryChanged();
    } catch (error) {
      LoggerService.instance.w('MeloNX discovery deferred: $error');
    }
  }

  String _text(String key) =>
      MelonxLibraryLocale.text(Localizations.localeOf(context), key);
  void _interaction(bool value) {
    _interacting = value;
    widget.onInteractionChanged?.call(value);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (_interacting) widget.onInteractionChanged?.call(false);
    super.dispose();
  }

  void _notice(String message) {
    if (mounted)
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _selected(String action) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final config = context.read<SqliteConfigProvider>();
      bool changed = false;
      switch (action) {
        case 'games':
          changed = await MelonxEmbeddedLibraryService.importGame(config);
        case 'firmware':
          changed = await MelonxEmbeddedLibraryService.importFirmware(
            install: (source) async {
              if (!mounted) return;
              final control = MelonxTransferControl();
              await runMelonxProgress(
                context,
                control,
                (progress) async {
                  final timer = Timer.periodic(
                    const Duration(milliseconds: 250),
                    (_) async {
                      try {
                        final phase = await MelonxInternalService.channel
                            .invokeMethod<int>('contentProgress');
                        if (mounted && !control.cancelled)
                          progress.value = MelonxProgress(switch (phase) {
                            2 => 'extracting',
                            3 => 'validating',
                            4 => 'installing',
                            _ => 'analyzing',
                          });
                      } catch (_) {
                        /* never invent a completed stage */
                      }
                    },
                  );
                  try {
                    await MelonxInternalService.content(
                      'installFirmware',
                      filePath: source.path,
                    );
                  } finally {
                    timer.cancel();
                  }
                },
                onCancel: () {
                  unawaited(
                    MelonxInternalService.channel.invokeMethod<void>(
                      'cancelContent',
                    ),
                  );
                },
              );
            },
          );
        case 'keys':
          final report = await MelonxEmbeddedLibraryService.importKeys();
          if (!mounted) return;
          await showDialog<void>(
            context: context,
            builder: (ctx) => AlertDialog(
              title: Text(_text('Import personal keys')),
              content: Text(
                [
                  for (final name in report.imported)
                    '${MelonxTransferLocale.text(ctx, 'imported')}: $name',
                  for (final item in report.refused.entries)
                    '${MelonxTransferLocale.text(ctx, 'rejected')}: ${item.key} — ${MelonxTransferLocale.text(ctx, item.value)}',
                  if (report.prodMissing)
                    MelonxTransferLocale.text(ctx, 'requiredProd'),
                ].join('\n'),
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: Text(_text('Done')),
                ),
              ],
            ),
          );
          changed = report.imported.isNotEmpty;
        case 'saves':
          changed = await showMelonxTransfer(context, config, savesOnly: true);
        case 'migration':
          changed = await showMelonxTransfer(context, config, savesOnly: false);
        case 'discover':
          await _discover();
        case 'delete':
          await widget.onDelete?.call();
        case 'update':
          changed = await MelonxEmbeddedLibraryService.importAddon(
            widget.titleId!,
            dlc: false,
          );
        case 'dlc':
          changed = await MelonxEmbeddedLibraryService.importAddon(
            widget.titleId!,
            dlc: true,
          );
        case 'graphics':
          if (!mounted) return;
          await showDialog<void>(
            context: context,
            builder: (_) => _MelonxGraphicsDialog(gamePath: widget.gamePath!),
          );
        case 'status':
          final status = await MelonxInternalService.content('firmwareInfo');
          if (!mounted) return;
          await showDialog<void>(
            context: context,
            builder: (context) => AlertDialog(
              title: Text(_text('Engine status')),
              content: Text(
                '${_text('Firmware')}: ${status['firmware'] ?? '—'}\n${status['root'] ?? ''}',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: Text(_text('Done')),
                ),
              ],
            ),
          );
      }
      if (changed) {
        if (mounted) await MelonxLibraryScanner.refresh(config);
        await widget.onLibraryChanged();
        _notice(_text('Import completed'));
      }
    } catch (error) {
      LoggerService.instance.w('MeloNX library action failed: $error');
      if (mounted)
        _notice(
          MelonxTransferLocale.text(
            context,
            error is MelonxTransferCancelled
                ? 'cancelled'
                : error.toString().contains('libraryBusy')
                ? 'libraryBusy'
                : error is MelonxContentException
                ? error.code
                : error is FormatException
                ? error.message
                : error is FileSystemException
                ? error.message
                : 'failed',
          ),
        );
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _interaction(false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    if (!Platform.isIOS) return const SizedBox.shrink();
    final validTitle =
        widget.titleId != null &&
        RegExp(r'^[0-9a-fA-F]{16}$').hasMatch(widget.titleId!);
    return PlaylistImportButton(
      menuKey: const ValueKey('melonx-import-menu'),
      tooltip: _text('Import'),
      busy: _busy,
      embedded: widget.embedded,
      onOpened: () => _interaction(true),
      onCanceled: () => _interaction(false),
      onSelected: _selected,
      items: (_) => [
        PopupMenuItem(value: 'games', child: Text(_text('Import games'))),
        PopupMenuItem(
          value: 'saves',
          child: Text(MelonxTransferLocale.text(context, 'importSaves')),
        ),
        PopupMenuItem(
          value: 'migration',
          child: Text(MelonxTransferLocale.text(context, 'migrate')),
        ),
        PopupMenuItem(
          value: 'discover',
          child: Text(MelonxTransferLocale.text(context, 'rescan')),
        ),
        if (widget.onDelete != null)
          PopupMenuItem(value: 'delete', child: Text(_text('Delete'))),
        PopupMenuItem(value: 'firmware', child: Text(_text('Import firmware'))),
        PopupMenuItem(
          value: 'keys',
          child: Text(_text('Import personal keys')),
        ),
        if (validTitle) ...[
          const PopupMenuDivider(),
          PopupMenuItem(value: 'update', child: Text(_text('Import update'))),
          PopupMenuItem(value: 'dlc', child: Text(_text('Import DLC'))),
        ],
        if (widget.gamePath != null)
          PopupMenuItem(value: 'graphics', child: Text(_text('Game graphics'))),
        const PopupMenuDivider(),
        PopupMenuItem(value: 'status', child: Text(_text('Engine status'))),
      ],
    );
  }
}

class _MelonxGraphicsDialog extends StatefulWidget {
  const _MelonxGraphicsDialog({required this.gamePath});
  final String gamePath;
  @override
  State<_MelonxGraphicsDialog> createState() => _MelonxGraphicsDialogState();
}

class _MelonxGraphicsDialogState extends State<_MelonxGraphicsDialog> {
  Map<String, dynamic>? _settings;
  String? _failure;
  String _text(String key) =>
      MelonxLibraryLocale.text(Localizations.localeOf(context), key);
  @override
  void initState() {
    super.initState();
    MelonxInternalService.graphicsForGame(widget.gamePath)
        .then((value) {
          if (mounted) setState(() => _settings = value);
        })
        .catchError((Object error) {
          if (mounted) setState(() => _failure = error.toString());
        });
  }

  @override
  Widget build(BuildContext context) {
    final settings = _settings;
    return AlertDialog(
      title: Text(_text('Game graphics')),
      content: SizedBox(
        width: 360,
        child: settings == null
            ? Text(_failure ?? '…')
            : SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    DropdownButtonFormField<double>(
                      initialValue: (settings['resolution'] as num? ?? 1)
                          .toDouble(),
                      decoration: InputDecoration(
                        labelText: _text('Resolution'),
                      ),
                      items: [
                        for (final scale in [0.5, 0.75, 1.0, 1.5, 2.0])
                          DropdownMenuItem(
                            value: scale,
                            child: Text('${scale}x'),
                          ),
                      ],
                      onChanged: (value) =>
                          setState(() => settings['resolution'] = value),
                    ),
                    for (final item in [
                      ('shaderCache', 'Shader cache', false),
                      ('asyncShaders', 'Async shaders', true),
                      ('vsync', 'VSync', true),
                    ])
                      SwitchListTile(
                        title: Text(_text(item.$2)),
                        value: settings[item.$1] as bool? ?? item.$3,
                        onChanged: (value) =>
                            setState(() => settings[item.$1] = value),
                      ),
                    DropdownButtonFormField<String>(
                      initialValue: settings['filter'] as String? ?? 'bilinear',
                      decoration: InputDecoration(
                        labelText: _text('Scaling filter'),
                      ),
                      items: [
                        for (final filter in [
                          'bilinear',
                          'nearest',
                          'fsr',
                          'area',
                        ])
                          DropdownMenuItem(value: filter, child: Text(filter)),
                      ],
                      onChanged: (value) =>
                          setState(() => settings['filter'] = value),
                    ),
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: Text(_text('Cancel')),
        ),
        FilledButton(
          onPressed: settings == null
              ? null
              : () async {
                  try {
                    await MelonxInternalService.saveGraphics(
                      widget.gamePath,
                      settings,
                    );
                    if (context.mounted) Navigator.pop(context);
                  } catch (error) {
                    if (mounted) setState(() => _failure = error.toString());
                  }
                },
          child: Text(_text('Save')),
        ),
      ],
    );
  }
}
