import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/melonx_library_locale.dart';
import '../providers/sqlite_config_provider.dart';
import '../services/logger_service.dart';
import '../services/melonx_internal_service.dart';
import '../services/melonx_embedded_library_service.dart';

class MelonxInternalPlaylistActions extends StatefulWidget {
  const MelonxInternalPlaylistActions({
    super.key,
    required this.onLibraryChanged,
    this.onInteractionChanged,
    this.gamePath,
    this.titleId,
  });
  final Future<void> Function() onLibraryChanged;
  final ValueChanged<bool>? onInteractionChanged;
  final String? gamePath;
  final String? titleId;
  @override
  State<MelonxInternalPlaylistActions> createState() =>
      _MelonxInternalPlaylistActionsState();
}

class _MelonxInternalPlaylistActionsState
    extends State<MelonxInternalPlaylistActions> {
  bool _busy = false;
  bool _interacting = false;
  String _text(String key) =>
      MelonxLibraryLocale.text(Localizations.localeOf(context), key);
  void _interaction(bool value) {
    _interacting = value;
    widget.onInteractionChanged?.call(value);
  }

  @override
  void dispose() {
    if (_interacting) widget.onInteractionChanged?.call(false);
    super.dispose();
  }

  void _notice(String message) {
    if (mounted)
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(message)));
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
          changed = await MelonxEmbeddedLibraryService.importFirmware();
        case 'keys':
          changed = await MelonxEmbeddedLibraryService.importKeys();
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
        await widget.onLibraryChanged();
        _notice(_text('Import completed'));
      }
    } catch (error) {
      LoggerService.instance.w('MeloNX library action failed: $error');
      if (mounted) _notice('${_text('Import failed')}: $error');
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
    return PopupMenuButton<String>(
      key: const ValueKey('melonx-import-menu'),
      tooltip: _text('Import'),
      enabled: !_busy,
      icon: _busy
          ? const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : const Icon(Icons.file_upload_outlined),
      onOpened: () => _interaction(true),
      onCanceled: () => _interaction(false),
      onSelected: _selected,
      itemBuilder: (_) => [
        PopupMenuItem(value: 'games', child: Text(_text('Import games'))),
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
