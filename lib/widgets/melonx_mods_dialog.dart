import 'dart:io';

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';

import '../l10n/melonx_mods_locale.dart';
import '../services/logger_service.dart';
import '../services/melonx_internal_service.dart';
import '../services/melonx_mods_service.dart';
import '../services/storage/storage_import_activity.dart';

/// A Switch game's mods: turn each on or off, import one (.zip), delete one.
/// Every change goes through the library gate, so nothing moves while a game
/// runs; mods load the next time the game starts.
class MelonxModsDialog extends StatefulWidget {
  const MelonxModsDialog({super.key, required this.titleId, this.gameName});
  final String titleId;
  final String? gameName;

  @override
  State<MelonxModsDialog> createState() => _MelonxModsDialogState();
}

class _MelonxModsDialogState extends State<MelonxModsDialog> {
  List<MelonxMod>? _mods;
  bool _busy = false;
  String? _message;
  bool _error = false;

  String _text(String key, [Map<String, Object?> values = const {}]) => MelonxModsLocale.text(context, key, values);

  @override
  void initState() {
    super.initState();
    _reload();
  }

  Future<void> _reload() async {
    try {
      final mods = await MelonxModsService.list(await MelonxInternalService.rootDirectory(), widget.titleId);
      if (mounted) setState(() => _mods = mods);
    } on Object catch (error) {
      _fail(error);
    }
  }

  void _fail(Object error) {
    final String key;
    if (error is MelonxModException) {
      key = switch (error.code) {
        'noMod' => 'errNoMod',
        'wrongGame' => 'errWrongGame',
        'exists' => 'errExists',
        'reservedName' => 'errReserved',
        'unsafePath' || 'invalidArchive' || 'tooManyFiles' || 'invalidName' => 'errArchive',
        _ => 'errFailed',
      };
    } else if (error is StateError && error.message == 'libraryBusy') {
      key = 'errBusy';
    } else {
      LoggerService.instance.w('MeloNX mods: ${error.runtimeType}');
      key = 'errFailed';
    }
    if (!mounted) return;
    setState(() {
      _message = _text(key, {'detail': error is MelonxModException ? error.detail : ''});
      _error = true;
      _mods ??= const [];
    });
  }

  Future<void> _run(Future<String?> Function(Directory root) change) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      final message = await MelonxInternalService.editLibrary(() async => change(await MelonxInternalService.rootDirectory()));
      await _reload();
      if (mounted) {
        setState(() {
          _message = message;
          _error = false;
        });
      }
    } on Object catch (error) {
      _fail(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// The mod archive is picked and imported inside the import activity, as
  /// every pick of the application (test/storage_contract_test.py).
  Future<void> _import() => StorageImportActivity.run(() async {
    final picked = await FilePicker.pickFiles(type: FileType.custom, allowedExtensions: ['zip'], withData: false);
    final path = picked?.files.single.path;
    if (path == null) return;
    // The picker's copy of the archive waits the picker's hourly cleanup, as
    // every other pick's (docs/storage-audit-cleanup.md).
    await _run((root) async {
      final names = await MelonxModsService.importArchive(root, widget.titleId, path);
      return '${_text('imported', {'names': names.join(', ')})}\n${_text('restart')}';
    });
  });

  Future<void> _toggle(MelonxMod mod, bool enabled) =>
      _run((root) async {
        await MelonxModsService.setEnabled(root, widget.titleId, mod.name, enabled);
        return _text('restart');
      });

  Future<void> _delete(MelonxMod mod) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        content: Text(_text('deleteConfirm', {'name': mod.name})),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: Text(_text('cancel'))),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(_text('delete'), style: TextStyle(color: Theme.of(context).colorScheme.error)),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    await _run((root) async {
      await MelonxModsService.delete(root, widget.titleId, mod.name);
      return null;
    });
  }

  @override
  Widget build(BuildContext context) {
    final mods = _mods;
    final theme = Theme.of(context);
    return AlertDialog(
      title: Text(widget.gameName == null ? _text('mods') : '${_text('mods')} · ${widget.gameName}'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_text('intro'), style: theme.textTheme.bodySmall),
              const SizedBox(height: 8),
              if (mods == null)
                const Center(child: CircularProgressIndicator())
              else if (mods.isEmpty)
                Padding(padding: const EdgeInsets.symmetric(vertical: 12), child: Text(_text('empty')))
              else
                for (final mod in mods)
                  SwitchListTile(
                    key: ValueKey('melonx-mod-${mod.name}'),
                    contentPadding: EdgeInsets.zero,
                    title: Text(mod.name),
                    subtitle: Text([
                      if (mod.romfs) _text('romfs'),
                      if (mod.exefs) _text('exefs'),
                      if (mod.cheats) _text('cheats'),
                    ].join(' · ')),
                    value: mod.enabled,
                    onChanged: _busy ? null : (value) => _toggle(mod, value),
                    secondary: IconButton(
                      tooltip: _text('delete'),
                      icon: Icon(Icons.delete_outline, color: theme.colorScheme.error),
                      onPressed: _busy ? null : () => _delete(mod),
                    ),
                  ),
              if (_busy) const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator()),
              if (_message != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_message!, style: _error ? TextStyle(color: theme.colorScheme.error) : null),
                ),
              const SizedBox(height: 8),
              Text(_text('onlineNote'), style: theme.textTheme.bodySmall),
            ],
          ),
        ),
      ),
      actions: [
        TextButton.icon(
          key: const ValueKey('melonx-mod-import'),
          onPressed: _busy ? null : _import,
          icon: const Icon(Icons.add),
          label: Text(_text('import')),
        ),
        TextButton(onPressed: () => Navigator.pop(context), child: Text(_text('close'))),
      ],
    );
  }
}
