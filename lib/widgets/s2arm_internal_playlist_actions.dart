import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:path/path.dart' as path;

import '../l10n/switch2_library_locale.dart';
import '../l10n/switch2_settings_locale.dart';
import '../repositories/game_repository.dart';
import '../services/s2arm_internal_service.dart';
import '../services/storage/storage_import_activity.dart';
import '../services/switch2_export_content.dart';
import 'delete_game_dialog.dart';
import 'switch2_engine_settings_panel.dart';

/// Menu of the Switch 2 playlist: import games (an export folder from Files,
/// docs/s2arm-switch2-library.md § Import), saves, the Switch 2 settings and
/// delete the highlighted game. Nothing of the Switch 1 engine: no prod.keys
/// (S2Arm needs none) and no firmware. The maintainer wants no ambiguity
/// between the two engines.
class S2ArmInternalPlaylistActions extends StatefulWidget {
  const S2ArmInternalPlaylistActions({
    super.key,
    required this.onLibraryChanged,
    this.onInteractionChanged,
    this.embedded = false,
    this.appSystemId,
    this.gameName,
    this.romName,
    this.romPath,
  });

  /// The highlighted game, for the Delete item (hidden without [romPath]).
  final String? appSystemId;
  final String? gameName;
  final String? romName;
  final String? romPath;

  final Future<void> Function() onLibraryChanged;
  final ValueChanged<bool>? onInteractionChanged;

  /// Inside the game details card (list view): no own surface.
  final bool embedded;

  @override
  State<S2ArmInternalPlaylistActions> createState() =>
      _S2ArmInternalPlaylistActionsState();
}

class _S2ArmInternalPlaylistActionsState
    extends State<S2ArmInternalPlaylistActions> {
  bool _busy = false;

  String _t(String key) => Switch2LibraryLocale.text(context, key);
  String _tf(String key, Map<String, Object?> values) =>
      Switch2LibraryLocale.textf(context, key, values);

  void _interaction(bool active) => widget.onInteractionChanged?.call(active);

  void _notice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _import() async {
    final control = S2ArmImportControl();
    final progress = ValueNotifier<S2ArmImportProgress?>(null);
    var dialogShown = false;
    void showProgress() {
      if (dialogShown || !mounted) return;
      dialogShown = true;
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (context) =>
            _S2ArmImportDialog(progress: progress, onCancel: control.cancel),
      );
    }

    S2ArmImportResult? result;
    try {
      result = await StorageImportActivity.run(
        () => S2ArmInternalService.importFolder(
          dialogTitle: _t('importGames'),
          control: control,
          onProgress: (value) {
            progress.value = value;
            showProgress();
          },
        ),
      );
    } finally {
      if (dialogShown && mounted) Navigator.of(context).pop();
      progress.dispose();
    }
    if (result == null || !mounted) return;
    if (result.imported > 0) await widget.onLibraryChanged();
    if (!mounted) return;
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    if (result.cancelled) _notice(_t('cancelled'));
    if (result.imported > 0) {
      _notice(_tf('imported', {'count': result.imported}));
    }
    final duplicates = result.items
        .where((item) => item.reason == 'duplicate')
        .length;
    if (duplicates > 0) _notice(_tf('duplicates', {'count': duplicates}));
    for (final item in result.rejected.take(3)) {
      _notice(
        '${item.name}: ${S2ArmInternalService.localizedError(locale, item.reason)}'
        '${item.detail == null ? '' : '\n(${item.detail})'}',
      );
    }
  }

  Future<void> _delete() async {
    final romPath = widget.romPath;
    final appSystemId = widget.appSystemId;
    if (romPath == null || appSystemId == null) return;
    final name = widget.gameName ?? widget.romName ?? '';
    final inside = await S2ArmInternalService.isInsideGames(romPath);
    if (!mounted) return;
    final confirmed = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => DeleteGameDialog(
        gameName: name,
        romName: widget.romName ?? name,
        confirmationBody: _tf(inside ? 'deleteConfirm' : 'deleteConfirmLinked', {
          'name': name,
        }),
      ),
    );
    if (confirmed != true || !mounted) return;
    try {
      await GameRepository.deleteGame(
        appSystemId: appSystemId,
        filename: widget.romName ?? name,
        systemFolderName: S2ArmInternalService.systemFolder,
        romBaseName: widget.romName ?? name,
        romPath: romPath,
      );
    } on S2ArmDeleteException catch (error) {
      _notice(_t(error.code));
      return;
    } catch (error) {
      _notice('${_t('deleteFailed')}\n$error');
      return;
    }
    await widget.onLibraryChanged();
    if (mounted) _notice(_tf('deleted', {'name': name}));
  }

  /// Always offered. Without a selected game the save goes to the game it names, or to the
  /// library game the player chooses when it names none.
  Future<void> _importSave() async {
    final romPath = widget.romPath;
    var name = widget.gameName ?? widget.romName ?? '';
    final S2ArmSaveImportResult? result;
    try {
      result = await S2ArmInternalService.importSave(
        romPath == null ? null : Switch2ExportContent.exportFolder(romPath),
        dialogTitle: _t('importSave'),
        chooseGame: (games) async {
          final chosen = await _chooseGame(games);
          if (chosen != null) name = chosen.title;
          return chosen;
        },
      );
    } on S2ArmSaveException catch (error) {
      _notice(_t(error.code));
      return;
    } catch (error) {
      _notice('${_t('saveFailed')}\n$error');
      return;
    }
    if (result == null || !mounted) return;
    final redirected = result.redirectedTo;
    final title = result.redirectedTitle;
    final lines = [
      if (redirected == null) _tf('saveImported', {'name': name, 'count': '${result.files}'}),
      // No game selected: the save named its game.
      if (redirected != null && romPath == null && title != null)
        _tf('saveImported', {'name': title, 'count': '${result.files}'}),
      if (redirected != null && romPath == null && title == null) _tf('saveImportedForId', {'id': redirected}),
      // The selected game was not the one the save names.
      if (redirected != null && romPath != null && title != null) _tf('saveRedirected', {'name': title, 'id': redirected}),
      if (redirected != null && romPath != null && title == null) _tf('saveRedirectedMissing', {'id': redirected}),
      if (result.backup != null) _tf('saveImportedBackup', {'backup': path.basename(result.backup!)}),
    ];
    _notice(lines.join('\n'));
  }

  /// Which library game a save that names no game is for; null when the player cancels.
  Future<S2ArmSaveGame?> _chooseGame(List<S2ArmSaveGame> games) async {
    if (!mounted) return null;
    return showDialog<S2ArmSaveGame>(
      context: context,
      builder: (ctx) => SimpleDialog(
        key: const ValueKey('s2arm-save-choose-game'),
        title: Text(_t('saveChooseGame')),
        children: [
          for (final game in games)
            SimpleDialogOption(
              onPressed: () => Navigator.of(ctx).pop(game),
              child: Text('${game.title} [${game.gid.toUpperCase()}]'),
            ),
          SimpleDialogOption(
            key: const ValueKey('s2arm-save-choose-cancel'),
            onPressed: () => Navigator.of(ctx).pop(),
            child: Text(_t('cancel')),
          ),
        ],
      ),
    );
  }

  /// The selected game's save folder, or the Saves folder itself when no game is selected.
  Future<void> _openSaves() async {
    final romPath = widget.romPath;
    final opened = await S2ArmInternalService.openSaveFolder(
      romPath == null ? null : Switch2ExportContent.exportFolder(romPath),
    );
    if (!opened) _notice(_t('openSavesFailed'));
  }

  Future<void> _openSettings() async {
    await showDialog<void>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(Switch2SettingsLocale.text(ctx, 'title')),
        contentPadding: EdgeInsets.zero,
        content: const SizedBox(
          width: 420,
          child: SingleChildScrollView(child: Switch2EngineSettingsPanel()),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: Text(_t('done')),
          ),
        ],
      ),
    );
  }

  Future<void> _selected(String action) async {
    if (_busy) return;
    setState(() => _busy = true);
    _interaction(true);
    try {
      if (action == 'folder') await _import();
      if (action == 'delete') await _delete();
      if (action == 'settings') await _openSettings();
      if (action == 'importSave') await _importSave();
      if (action == 'openSaves') await _openSaves();
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _interaction(false);
      }
    }
  }

  Widget _item(String title, String subtitle) => Column(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      Text(title),
      Text(subtitle, style: Theme.of(context).textTheme.bodySmall),
    ],
  );

  @override
  Widget build(BuildContext context) {
    if (defaultTargetPlatform != TargetPlatform.iOS) {
      return const SizedBox.shrink();
    }
    final scheme = Theme.of(context).colorScheme;
    final button = SizedBox(
      width: 36.r,
      height: 36.r,
      child: PopupMenuButton<String>(
        key: const ValueKey('s2arm-internal-import-menu'),
        tooltip: _t('importMenu'),
        enabled: !_busy,
        padding: EdgeInsets.zero,
        onOpened: () => _interaction(true),
        onCanceled: () => _interaction(false),
        onSelected: _selected,
        icon: _busy
            ? SizedBox(
                width: 18.r,
                height: 18.r,
                child: const CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(
                Icons.file_upload_outlined,
                size: 18.r,
                color: widget.embedded
                    ? scheme.onSurface
                    : scheme.onTertiaryFixed,
              ),
        itemBuilder: (context) => [
          PopupMenuItem(
            key: const ValueKey('s2arm-import-folder'),
            value: 'folder',
            child: _item(_t('importGames'), _t('importGamesHint')),
          ),
          // Saves come second, with or without a selected game.
          PopupMenuItem(
            key: const ValueKey('s2arm-import-save'),
            value: 'importSave',
            child: _item(_t('importSave'), _t('importSaveHint')),
          ),
          PopupMenuItem(
            key: const ValueKey('s2arm-open-saves'),
            value: 'openSaves',
            child: _item(_t('openSaves'), _t('openSavesHint')),
          ),
          PopupMenuItem(
            key: const ValueKey('s2arm-settings'),
            value: 'settings',
            child: Text(Switch2SettingsLocale.text(context, 'title')),
          ),
          if (widget.romPath != null && widget.appSystemId != null)
            PopupMenuItem(
              key: const ValueKey('s2arm-delete-game'),
              value: 'delete',
              child: Text(_t('deleteGame')),
            ),
        ],
      ),
    );
    if (widget.embedded) return button;
    return Material(
      color: scheme.tertiaryFixed,
      borderRadius: BorderRadius.circular(10.r),
      elevation: 2,
      child: button,
    );
  }
}

class _S2ArmImportDialog extends StatelessWidget {
  const _S2ArmImportDialog({required this.progress, required this.onCancel});

  final ValueListenable<S2ArmImportProgress?> progress;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: AlertDialog(
        content: ValueListenableBuilder<S2ArmImportProgress?>(
          valueListenable: progress,
          builder: (context, value, _) => Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                Switch2LibraryLocale.textf(context, 'importing', {
                  'name': value?.name ?? '',
                }),
              ),
              const SizedBox(height: 12),
              LinearProgressIndicator(value: value?.fraction),
            ],
          ),
        ),
        actions: [
          TextButton(
            key: const ValueKey('s2arm-import-cancel'),
            autofocus: true,
            onPressed: onCancel,
            child: Text(Switch2LibraryLocale.text(context, 'cancel')),
          ),
        ],
      ),
    );
  }
}

/// Non-dismissible dialog shown while S2ArmInternalService.launch prepares a
/// game (stage and percent from `onPrepareProgress`). The launch route owns
/// its lifetime.
class S2ArmPrepareDialog extends StatelessWidget {
  const S2ArmPrepareDialog({
    super.key,
    required this.progress,
    required this.title,
  });

  final ValueListenable<S2ArmImportProgress?> progress;
  final String title;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: AlertDialog(
        key: const ValueKey('s2arm-prepare-dialog'),
        content: ValueListenableBuilder<S2ArmImportProgress?>(
          valueListenable: progress,
          builder: (context, value, _) {
            final fraction = value?.fraction;
            final stage = value?.name ?? '';
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  Switch2LibraryLocale.textf(context, 'preparing', {
                    'name': title,
                  }),
                ),
                if (stage.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    fraction == null
                        ? stage
                        : '$stage · ${(fraction * 100).round()}%',
                    style: Theme.of(context).textTheme.bodySmall,
                  ),
                ],
                const SizedBox(height: 12),
                LinearProgressIndicator(value: fraction),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// The localized message of an S2Arm launch failure key: the iOS 26 line of
/// the library locale, every other key through S2ArmInternalService (which
/// maps engine states and native codes to S2ArmEngineLocale).
String s2armLaunchMessage(Locale locale, String? error) =>
    error == 'requiresIOS26'
    ? Switch2LibraryLocale.forLocale(locale, 'requiresIOS26')
    : S2ArmInternalService.localizedError(locale, error);
