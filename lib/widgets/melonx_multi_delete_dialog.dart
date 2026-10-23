import 'dart:io';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../l10n/dolphin_import_locale.dart';
import '../models/game_model.dart';
import '../models/system_model.dart';
import '../providers/sqlite_config_provider.dart';
import '../providers/sqlite_database_provider.dart';
import '../repositories/game_repository.dart';
import '../services/melonx_internal_service.dart';
import '../l10n/melonx_transfer_locale.dart';
import 'delete_game_dialog.dart';

/// Switch selection uses the common repository and confirmation dialog. Only
/// game images are removed; engine data and saves are outside this operation.
class MelonxMultiDeleteDialog extends StatefulWidget {
  const MelonxMultiDeleteDialog({
    super.key,
    required this.system,
    required this.games,
    required this.initialGame,
  });

  final SystemModel system;
  final List<GameModel> games;
  final GameModel initialGame;

  static Future<bool?> show({
    required BuildContext context,
    required SystemModel system,
    required List<GameModel> games,
    required GameModel initialGame,
  }) {
    if (!Platform.isIOS || system.folderName.toLowerCase() != 'switch') {
      return Future<bool?>.value(false);
    }
    return showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => MelonxMultiDeleteDialog(
        system: system,
        games: games,
        initialGame: initialGame,
      ),
    );
  }

  @override
  State<MelonxMultiDeleteDialog> createState() =>
      _MelonxMultiDeleteDialogState();
}

class _MelonxMultiDeleteDialogState extends State<MelonxMultiDeleteDialog> {
  final Set<String> _selected = <String>{};
  bool _deleting = false;
  int _deletedCount = 0;
  int _targetCount = 0;
  String? _error;
  final Set<String> _removed = {};
  List<GameModel> get _remaining =>
      widget.games.where((g) => !_removed.contains(_key(g))).toList();

  String _t(String key) => DolphinImportLocale.text(context, key);
  String _tf(String key, Map<String, Object?> values) {
    var value = _t(key);
    for (final item in values.entries) {
      value = value.replaceAll('{${item.key}}', '${item.value ?? ''}');
    }
    return value;
  }

  String _key(GameModel game) =>
      game.romPath ?? '${game.systemId ?? widget.system.id}:${game.romname}';

  @override
  void initState() {
    super.initState();
    _selected.add(_key(widget.initialGame));
  }

  void _toggle(GameModel game) {
    if (_deleting) return;
    final key = _key(game);
    setState(() {
      if (!_selected.add(key)) _selected.remove(key);
    });
  }

  void _toggleAll() {
    if (_deleting) return;
    setState(() {
      if (_selected.length == _remaining.length) {
        _selected.clear();
      } else {
        _selected
          ..clear()
          ..addAll(
            widget.games.where((g) => !_removed.contains(_key(g))).map(_key),
          );
      }
    });
  }

  Future<void> _deleteSelected() async {
    if (_deleting || _selected.isEmpty) return;
    final selectedGames = widget.games
        .where((game) => _selected.contains(_key(game)))
        .toList(growable: false);
    if (selectedGames.isEmpty) return;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => DeleteGameDialog(
        gameName: selectedGames.map((g) => g.name).join('\n'),
        romName: selectedGames.map((g) => g.romPath ?? g.romname).join('\n'),
      ),
    );
    if (confirmed != true || !mounted) return;
    setState(() {
      _deleting = true;
      _deletedCount = 0;
      _targetCount = selectedGames.length;
      _error = null;
    });

    try {
      for (final game in selectedGames) {
        if (!MelonxInternalService.gameExtensions.contains(
          game.romPath?.split('.').last.toLowerCase(),
        ))
          throw StateError('localGameRequired');
        await GameRepository.deleteGame(
          appSystemId: game.systemId ?? widget.system.id,
          filename: game.romname,
          systemFolderName: widget.system.folderName,
          romBaseName: game.romname,
          romPath: game.romPath,
        );
        if (mounted)
          setState(() {
            _deletedCount++;
            _selected.remove(_key(game));
            _removed.add(_key(game));
          });
        if (mounted)
          await context.read<SqliteConfigProvider>().refreshDetectedSystems();
        if (mounted)
          await context.read<SqliteDatabaseProvider>().loadDatabase();
      }

      if (!mounted) return;
      await context.read<SqliteConfigProvider>().refreshDetectedSystems();
      if (!mounted) return;
      await context.read<SqliteDatabaseProvider>().loadDatabase();
      if (!mounted) return;
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error =
            '${MelonxTransferLocale.text(context, error.toString().contains('libraryBusy') ? 'libraryBusy' : 'deleteFailed')}\n$error';
        _deleting = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final allSelected =
        _remaining.isNotEmpty && _selected.length == _remaining.length;

    return AlertDialog(
      title: Text(_t('deleteGames')),
      content: SizedBox(
        width: 520,
        height: 420,
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    _tf('selectedCount', {'count': _selected.length}),
                  ),
                ),
                TextButton.icon(
                  onPressed: _deleting ? null : _toggleAll,
                  icon: Icon(
                    allSelected
                        ? Icons.deselect_rounded
                        : Icons.select_all_rounded,
                  ),
                  label: Text(
                    allSelected ? _t('deselectAll') : _t('selectAll'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Expanded(
              child: ListView.builder(
                itemCount: _remaining.length,
                itemBuilder: (context, index) {
                  final game = _remaining[index];
                  final checked = _selected.contains(_key(game));
                  return CheckboxListTile(
                    value: checked,
                    onChanged: _deleting || _removed.contains(_key(game))
                        ? null
                        : (_) => _toggle(game),
                    controlAffinity: ListTileControlAffinity.leading,
                    dense: true,
                    title: Text(
                      game.name.isNotEmpty ? game.name : game.romname,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                    subtitle: Text(
                      game.romPath ?? game.romname,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                    ),
                  );
                },
              ),
            ),
            if (_deleting) ...[
              const SizedBox(height: 8),
              LinearProgressIndicator(
                value: _targetCount == 0 ? null : _deletedCount / _targetCount,
              ),
              const SizedBox(height: 6),
              Text(
                _tf('deleting', {'done': _deletedCount, 'total': _targetCount}),
              ),
            ],
            if (_error != null) ...[
              const SizedBox(height: 8),
              Text(_error!, style: TextStyle(color: theme.colorScheme.error)),
            ],
          ],
        ),
      ),
      actions: [
        TextButton(
          onPressed: _deleting ? null : () => Navigator.of(context).pop(false),
          child: Text(_t('cancel')),
        ),
        FilledButton.icon(
          onPressed: _deleting || _selected.isEmpty ? null : _deleteSelected,
          icon: const Icon(Icons.delete_forever_rounded),
          label: Text(_tf('deleteCount', {'count': _selected.length})),
        ),
      ],
    );
  }
}
