import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:path/path.dart' as path;

import '../l10n/switch2_library_locale.dart';
import '../l10n/switch2_settings_locale.dart';
import '../repositories/game_repository.dart';
import '../repositories/scraper_repository.dart';
import '../services/logger_service.dart';
import '../services/s2arm_internal_service.dart';
import '../services/screenscraper_service.dart';
import '../services/storage/storage_import_activity.dart';
import '../services/switch2_export_content.dart';
import 'delete_game_dialog.dart';
import 'switch2_engine_settings_panel.dart';

/// Menu of the Switch 2 playlist: import games (an export folder or NUP
/// containers from Files, docs/s2arm-switch2-library.md § Import), saves, the
/// Switch 2 settings and delete the highlighted game. A coloured button (with
/// its label where there is room) and an opaque menu with an icon per item: the
/// maintainer found the bare icon and the see-through menu too easy to miss. Nothing of the Switch 1 engine: no prod.keys
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

  /// [action] 'folder' (an export folder) or 'nup' (NUP containers).
  Future<void> _import(String action) async {
    final control = S2ArmImportControl();
    final progress = ValueNotifier<S2ArmImportProgress?>(null);
    final navigator = Navigator.of(context, rootNavigator: true);
    DialogRoute<void>? dialog;
    void showProgress() {
      if (dialog != null || !mounted) return;
      final route = DialogRoute<void>(
        context: context,
        barrierDismissible: false,
        themes: InheritedTheme.capture(from: context, to: navigator.context),
        builder: (context) =>
            _S2ArmImportDialog(progress: progress, onCancel: control.cancel),
      );
      dialog = route;
      navigator.push(route);
    }

    S2ArmImportResult? result;
    try {
      void onProgress(S2ArmImportProgress value) {
        progress.value = value;
        showProgress();
      }

      result = await StorageImportActivity.run(
        () => action == 'nup'
            ? S2ArmInternalService.importNupFiles(
                control: control,
                onProgress: onProgress,
              )
            : S2ArmInternalService.importFolder(
                dialogTitle: _t('importGames'),
                control: control,
                onProgress: onProgress,
              ),
      );
    } on FileSystemException {
      if (mounted) _notice(S2ArmInternalService.localizedError(Localizations.localeOf(context), 'storageError'));
    } on PlatformException {
      if (mounted) _notice(S2ArmInternalService.localizedError(Localizations.localeOf(context), 'storageError'));
    } finally {
      final route = dialog;
      if (route != null) {
        if (navigator.mounted && route.isActive) navigator.removeRoute(route);
        await route.completed;
      }
      progress.dispose();
    }
    if (result == null || !mounted) return;
    if (result.imported > 0) await widget.onLibraryChanged();
    if (!mounted) return;
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    if (result.cancelled) _notice(_t('cancelled'));
    if (result.imported > 0) {
      _notice(_tf('imported', {'count': result.imported}));
      unawaited(_scrapeImportedGames(result));
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

  Future<void> _scrapeImportedGames(S2ArmImportResult result) async {
    const system = S2ArmInternalService.systemFolder;
    try {
      final config = await ScraperRepository.getSystemScraperConfig();
      if (config[system] == false) return;
      final entries = {
        for (final item in result.items)
          if (item.imported && item.destination != null)
            path.normalize(item.destination!),
      };
      var scraped = false;
      for (final game in await GameRepository.getGamesBySystem(system)) {
        final export = path.normalize(Switch2ExportContent.exportFolder(game.romPath));
        if (!entries.contains(export) || Switch2ExportContent.isGenericTitle(game.titleName)) {
          continue;
        }
        if (!await ScreenScraperService.canScrapeGame(system, game.titleId)) continue;
        final existing = await ScraperRepository.getGameMetadata(system, game.filename);
        if (existing != null) continue;
        await ScreenScraperService.scrapeSingleGame(
          appSystemId: system,
          romName: game.filename,
          systemFolder: system,
          romPath: game.romPath,
          gameName: game.titleName,
          serialNumber: game.titleId,
        );
        scraped = true;
      }
      if (scraped && mounted) await widget.onLibraryChanged();
    } catch (error) {
      LoggerService.instance.w('Switch 2 import: automatic scraping failed: $error');
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
      if (action == 'folder' || action == 'nup') await _import(action);
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

  /// One menu entry: an icon, the title in bold, and a line that says what it does.
  Widget _item(IconData icon, String title, [String? subtitle, Color? color]) {
    final theme = Theme.of(context);
    final tint = color ?? theme.colorScheme.primary;
    return ConstrainedBox(
      constraints: BoxConstraints(minHeight: 48.r),
      child: Row(
        children: [
          Container(
            width: 36.r,
            height: 36.r,
            decoration: BoxDecoration(
              color: tint.withValues(alpha: 0.14),
              borderRadius: BorderRadius.circular(10.r),
            ),
            child: Icon(icon, size: 20.r, color: tint),
          ),
          SizedBox(width: 12.r),
          Expanded(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    color: color,
                  ),
                ),
                if (subtitle != null)
                  Padding(
                    padding: EdgeInsets.only(top: 2.r),
                    child: Text(subtitle, style: theme.textTheme.bodySmall),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (defaultTargetPlatform != TargetPlatform.iOS) {
      return const SizedBox.shrink();
    }
    final scheme = Theme.of(context).colorScheme;
    final background = widget.embedded ? Colors.transparent : scheme.primary;
    final foreground = widget.embedded ? scheme.onSurface : scheme.onPrimary;
    final label = Text(
      _t('importButton'),
      maxLines: 1,
      style: TextStyle(
        color: foreground,
        fontSize: 15.r,
        fontWeight: FontWeight.w700,
      ),
    );
    final icon = _busy
        ? SizedBox(
            width: 18.r,
            height: 18.r,
            child: CircularProgressIndicator(strokeWidth: 2, color: foreground),
          )
        : Icon(
            Icons.file_upload_outlined,
            size: widget.embedded ? 19.r : 22.r,
            color: foreground,
          );
    // The tab bar supplies the embedded button's background.
    final face = Container(
      width: widget.embedded ? 30.r : null,
      height: widget.embedded ? 28.r : 40.r,
      alignment: Alignment.center,
      padding: widget.embedded
          ? EdgeInsets.zero
          : EdgeInsets.symmetric(horizontal: 14.r),
      decoration: BoxDecoration(
        color: _busy ? background.withValues(alpha: 0.6) : background,
        borderRadius: BorderRadius.circular(widget.embedded ? 9.r : 12.r),
      ),
      child: widget.embedded
          ? icon
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                icon,
                SizedBox(width: 8.r),
                label,
                SizedBox(width: 2.r),
                Icon(Icons.arrow_drop_down, size: 22.r, color: foreground),
              ],
            ),
    );
    // An opaque menu: the theme's glass fill let the game card behind show through the items (maintainer's
    // screenshot of IPA 777), so its tint is laid on the surface colour at full opacity, with a rim and a shadow.
    final menuColor = Color.alphaBlend(
      Theme.of(context).popupMenuTheme.color ?? scheme.surfaceContainerHigh,
      scheme.surface,
    ).withValues(alpha: 1);
    final button = PopupMenuButton<String>(
      key: const ValueKey('s2arm-internal-import-menu'),
      tooltip: _t('importMenu'),
      enabled: !_busy,
      padding: EdgeInsets.zero,
      constraints: BoxConstraints(minWidth: 300.r, maxWidth: 380.r),
      color: menuColor,
      surfaceTintColor: Colors.transparent,
      elevation: 8,
      shadowColor: Colors.black,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14.r),
        side: BorderSide(color: scheme.outline.withValues(alpha: 0.6)),
      ),
      onOpened: () => _interaction(true),
      onCanceled: () => _interaction(false),
      onSelected: _selected,
      itemBuilder: (context) => [
        PopupMenuItem(
          key: const ValueKey('s2arm-import-folder'),
          value: 'folder',
          child: _item(
            Icons.create_new_folder_outlined,
            _t('importGames'),
            _t('importGamesHint'),
          ),
        ),
        const PopupMenuDivider(),
        PopupMenuItem(
          key: const ValueKey('s2arm-import-nup'),
          value: 'nup',
          child: _item(
            Icons.inventory_2_outlined,
            _t('importNup'),
            _t('importNupHint'),
          ),
        ),
        const PopupMenuDivider(),
        // Saves come after the games, with or without a selected game; a divider between every option.
        PopupMenuItem(
          key: const ValueKey('s2arm-import-save'),
          value: 'importSave',
          child: _item(
            Icons.save_alt_outlined,
            _t('importSave'),
            _t('importSaveHint'),
          ),
        ),
        const PopupMenuDivider(),
        PopupMenuItem(
          key: const ValueKey('s2arm-open-saves'),
          value: 'openSaves',
          child: widget.romPath == null
              ? _item(Icons.folder_open_outlined, _t('openSaves'), _t('openSavesHint'))
              : FutureBuilder<String?>(
                  future: S2ArmInternalService.saveImportStatus(
                    Switch2ExportContent.exportFolder(widget.romPath!),
                  ),
                  builder: (context, state) => _item(
                    Icons.folder_open_outlined,
                    _t('openSaves'),
                    _t(state.data ?? 'openSavesHint'),
                  ),
                ),
        ),
        const PopupMenuDivider(),
        PopupMenuItem(
          key: const ValueKey('s2arm-settings'),
          value: 'settings',
          child: _item(
            Icons.tune,
            Switch2SettingsLocale.text(context, 'title'),
          ),
        ),
        if (widget.romPath != null && widget.appSystemId != null) ...[
          const PopupMenuDivider(),
          PopupMenuItem(
            key: const ValueKey('s2arm-delete-game'),
            value: 'delete',
            child: _item(
              Icons.delete_outline,
              _t('deleteGame'),
              null,
              scheme.error,
            ),
          ),
        ],
      ],
      child: face,
    );
    // The dividers between the options in a clearly visible line (DividerTheme is carried into the menu's route).
    final menu = DividerTheme(
      data: DividerTheme.of(context).copyWith(
        color: scheme.outline.withValues(alpha: 0.7),
        thickness: 1,
      ),
      child: button,
    );
    if (widget.embedded) return Center(child: menu);
    return Material(
      color: Colors.transparent,
      elevation: 4,
      shadowColor: scheme.shadow,
      borderRadius: BorderRadius.circular(12.r),
      child: menu,
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
                Switch2LibraryLocale.textf(
                  context,
                  switch (value?.step) {
                    'nup' => 'unpacking',
                    'scan' => 'preparing',
                    'clone' => 'cloningFolder',
                    _ => 'importing',
                  },
                  {'name': value?.name ?? ''},
                ),
              ),
              const SizedBox(height: 12),
              LinearProgressIndicator(value: value?.fraction),
              if (value != null && value.count > 1)
                Text(Switch2LibraryLocale.textf(
                  context, 'prepCount', {'done': value.index, 'total': value.count},
                )),
              if (value?.step == 'scan' && value?.unitsDone != null) ...[
                const SizedBox(height: 6),
                Text(Switch2LibraryLocale.textf(
                  context, 'prepCountEntries', {'count': value!.unitsDone},
                )),
              ],
              if (value != null && value.fraction != null) ...[
                const SizedBox(height: 6),
                Text(
                  '${(value.fraction! * 100).floor()} %',
                  textAlign: TextAlign.end,
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
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
/// The launch preparation of a Switch 2 game: the step and its part, the phase with its own counts, one bar for the whole
/// preparation (weighted by step, the code stage first) and the elapsed time, so a long code stage never looks frozen.
class S2ArmPrepareDialog extends StatefulWidget {
  const S2ArmPrepareDialog({
    super.key,
    required this.progress,
    required this.title,
  });

  final ValueListenable<S2ArmImportProgress?> progress;
  final String title;

  /// The clock of the elapsed time; tests replace it.
  @visibleForTesting
  static DateTime Function() clock = DateTime.now;

  @override
  State<S2ArmPrepareDialog> createState() => _S2ArmPrepareDialogState();
}

class _S2ArmPrepareDialogState extends State<S2ArmPrepareDialog> {
  late final DateTime _started = S2ArmPrepareDialog.clock();
  Timer? _ticker;

  @override
  void initState() {
    super.initState();
    _ticker = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) setState(() {});
    });
  }

  @override
  void dispose() {
    _ticker?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    final elapsed = S2ArmPrepareDialog.clock().difference(_started);
    return PopScope(
      canPop: false,
      child: AlertDialog(
        key: const ValueKey('s2arm-prepare-dialog'),
        content: ValueListenableBuilder<S2ArmImportProgress?>(
          valueListenable: widget.progress,
          builder: (context, value, _) {
            final lines = s2armPreparationLines(locale, value);
            final bar = value?.overall ?? value?.fraction;
            final status = [
              // floor, so 100 % means done; the epsilon absorbs 0.29 * 100 = 28.999999999999996.
              if (bar != null) '${(bar * 100 + 1e-6).floor().clamp(0, 100)} %',
              Switch2LibraryLocale.format(locale, 'prepElapsed', {'time': s2armElapsedText(locale, elapsed)}),
            ].join(' · ');
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  Switch2LibraryLocale.textf(context, 'preparing', {
                    'name': widget.title,
                  }),
                ),
                for (final line in lines) ...[
                  const SizedBox(height: 8),
                  Text(line, style: Theme.of(context).textTheme.bodySmall),
                ],
                const SizedBox(height: 12),
                LinearProgressIndicator(value: bar),
                const SizedBox(height: 8),
                Text(
                  status,
                  key: const ValueKey('s2arm-prepare-status'),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// The step line (step, part, pass) and the phase line (phase, counts) of a preparation; the step and its percent for an
/// older event without step. Visible for tests.
List<String> s2armPreparationLines(Locale locale, S2ArmImportProgress? value) {
  if (value == null) return const [];
  String t(String key, [Map<String, Object?> parameters = const {}]) => Switch2LibraryLocale.format(locale, key, parameters);
  final step = value.step;
  if (step == null) {
    final fraction = value.fraction;
    return [if (value.name.isNotEmpty) fraction == null ? value.name : '${value.name} · ${(fraction * 100).round()}%'];
  }
  if (step == 'done') return [if (value.part == 'reused') t('prepReused')];
  const stepKeys = {
    'unpack': 'prepStepUnpack',
    'code': 'prepStepCode',
    'caps': 'prepStepCaps',
    'direct': 'prepStepDirect',
    'graphics': 'prepStepDirect',
    'module': 'prepStepModule',
    'pack': 'prepStepPack',
  };
  final head = <String>[if (stepKeys[step] != null) t(stepKeys[step]!)];
  final part = value.part;
  if (step == 'code' && part != null && part.isNotEmpty) {
    const partKeys = {
      'main': 'prepPartMain',
      'zbic': 'prepPartZbic',
      'addr_need': 'prepPartAddrNeed',
      'nro': 'prepPartNro',
      'tables': 'prepPartTables',
    };
    head.add(partKeys[part] != null ? t(partKeys[part]!) : t('prepPartModule', {'name': part}));
  }
  if (value.attempt > 1) head.add(t('prepAttempt', {'n': value.attempt}));
  final detail = <String>[];
  const phaseKeys = {
    'load': 'prepPhaseRead',
    'prepass': 'prepPhaseRead',
    'boundaries': 'prepPhaseFind',
    'scan': 'prepPhaseFind',
    'data': 'prepPhaseFind',
    'analyze': 'prepPhaseAnalyze',
    'generate': 'prepPhaseGenerate',
    'late': 'prepPhaseGenerate',
    'spins': 'prepPhaseGenerate',
    'outputs': 'prepPhaseWrite',
  };
  final phase = value.phase;
  if (phase != null && phaseKeys[phase] != null) detail.add(t(phaseKeys[phase]!));
  final done = value.unitsDone ?? 0, total = value.unitsTotal ?? 0;
  if ((phase == 'walk' || (step == 'graphics' && total == 0)) && done > 0) {
    detail.add(t('prepCountEntries', {'count': done}));
  } else if (total > 0) {
    if (phase == 'analyze') {
      detail.add(t('prepCountFunctions', {'done': done, 'total': total}));
    } else if (phase == 'generate' || step == 'graphics') {
      detail.add(t('prepCount', {'done': done, 'total': total}));
    } else if (const {'boundaries', 'scan', 'spins', 'zbic'}.contains(phase)) {
      detail.add(t('prepCountMegabytes', {'done': (done / 1000000).round(), 'total': (total / 1000000).round()}));
    }
  }
  return [
    if (head.isNotEmpty) head.join(' · '),
    if (detail.isNotEmpty) detail.join(' · '),
  ];
}

/// "1 min 05 s", "42 s" (each locale's units). Visible for tests.
String s2armElapsedText(Locale locale, Duration elapsed) {
  final seconds = elapsed.inSeconds < 0 ? 0 : elapsed.inSeconds;
  final minutes = seconds ~/ 60;
  if (minutes == 0) return Switch2LibraryLocale.format(locale, 'prepSeconds', {'s': seconds});
  return Switch2LibraryLocale.format(locale, 'prepMinutesSeconds', {'m': minutes, 's': (seconds % 60).toString().padLeft(2, '0')});
}

/// The localized message of an S2Arm launch failure key: the iOS 26 line of
/// the library locale, every other key through S2ArmInternalService (which
/// maps engine states and native codes to S2ArmEngineLocale).
String s2armLaunchMessage(Locale locale, String? error) =>
    error == 'requiresIOS26'
    ? Switch2LibraryLocale.forLocale(locale, 'requiresIOS26')
    : S2ArmInternalService.localizedError(locale, error);
