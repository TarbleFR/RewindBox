import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';

import 'dart:async';
import 'dart:io';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;

import '../data/datasources/sqlite_service.dart';
import '../l10n/melonx_library_locale.dart';
import '../l10n/melonx_transfer_locale.dart';
import '../providers/sqlite_config_provider.dart';
import '../services/melonx_embedded_library_service.dart';
import '../services/melonx_file_transaction.dart';
import '../services/melonx_internal_service.dart';
import '../services/melonx_migration_service.dart';
import '../services/melonx_transfer_source.dart';
import '../services/storage/storage_import_activity.dart';

class MelonxProgress {
  const MelonxProgress(
    this.phase, [
    this.done = 0,
    this.total = 0,
    this.detail = '',
  ]);
  final String phase;
  final String detail;
  final int done, total;
}

Future<T> runMelonxProgress<T>(
  BuildContext context,
  MelonxTransferControl control,
  Future<T> Function(ValueNotifier<MelonxProgress>) body, {
  bool cancellable = true,
  VoidCallback? onCancel,
}) async {
  final progress = ValueNotifier(const MelonxProgress('analyzing'));
  final navigator = Navigator.of(context, rootNavigator: true);
  final route = DialogRoute<void>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => PopScope(
      canPop: false,
      child: ValueListenableBuilder<MelonxProgress>(
        valueListenable: progress,
        builder: (ctx, state, _) => AlertDialog(
          title: Text(MelonxTransferLocale.text(ctx, state.phase)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (state.detail.isNotEmpty) Text(state.detail),
              LinearProgressIndicator(
                value: state.total > 0
                    ? (state.done / state.total).clamp(0, 1)
                    : null,
              ),
              if (state.total > 0) Text('${state.done} / ${state.total} B'),
            ],
          ),
          actions: cancellable
              ? [
                  TextButton(
                    onPressed: () {
                      control.cancelled = true;
                      onCancel?.call();
                    },
                    child: Text(
                      MelonxLibraryLocale.text(
                        Localizations.localeOf(ctx),
                        'Cancel',
                      ),
                    ),
                  ),
                ]
              : null,
        ),
      ),
    ),
  );
  unawaited(navigator.push(route));
  try {
    return await body(progress);
  } finally {
    if (route.isActive) navigator.removeRoute(route);
    progress.dispose();
  }
}

Future<bool> _confirm(
  BuildContext context,
  String title,
  String body,
  String action,
) async =>
    await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(title),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(child: SelectableText(body)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: Text(
              MelonxLibraryLocale.text(Localizations.localeOf(ctx), 'Cancel'),
            ),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: Text(action),
          ),
        ],
      ),
    ) ??
    false;

Future<String?> _choose(
  BuildContext context,
  String title,
  Map<String, String> choices,
) => showDialog<String>(
  context: context,
  builder: (ctx) => SimpleDialog(
    title: Text(title),
    children: [
      for (final entry in choices.entries)
        SimpleDialogOption(
          onPressed: () => Navigator.pop(ctx, entry.key),
          child: Text(entry.value),
        ),
    ],
  ),
);

Future<bool> showMelonxTransfer(
  BuildContext context,
  SqliteConfigProvider config, {
  required bool savesOnly,
}) => StorageImportActivity.run(
  () => MelonxInternalService.editLibrary(() async {
    String text(String key) => MelonxTransferLocale.text(context, key);
    final root = await MelonxInternalService.rootDirectory();
    await MelonxFileTransaction.recover(root);
    if (!context.mounted) return false;
    final kind =
        await _choose(context, text(savesOnly ? 'importSaves' : 'migrate'), {
          'folder': text('folder'),
          if (!savesOnly) 'linked': text('linkGames'),
          'archive': text('archive'),
        });
    if (kind == null) return false;
    final temporary = await Directory.systemTemp.createTemp(
      'rewindbox-transfer-',
    );
    final control = MelonxTransferControl();
    try {
      Directory? source;
      final bookmark =
          'rewindbox.melonx.transfer.${DateTime.now().microsecondsSinceEpoch}';
      if (kind != 'archive') {
        final selected = await ExternalFolderAccess.pickAndActivateFolder(
          key: bookmark,
        );
        if (selected == null) return false;
        source = Directory(selected);
      } else {
        final archive = await MelonxEmbeddedLibraryService.pick({'zip'});
        if (archive == null || !context.mounted) return false;
        source = Directory(p.join(temporary.path, 'export'));
        final free = await MelonxInternalService.channel.invokeMethod<int>(
          'storageCapacity',
        );
        if (!context.mounted) return false;
        await runMelonxProgress(context, control, (progress) async {
          progress.value = const MelonxProgress('extracting');
          await MelonxTransferSource.extract(
            archive,
            source!,
            control,
            freeBytes: free,
            progress: (done, total) =>
                progress.value = MelonxProgress('extracting', done, total),
          );
        });
      }
      if (!context.mounted) return false;
      if (savesOnly)
        return await _importSaves(context, source, root, temporary, control);
      final preferences = await SharedPreferences.getInstance();
      final previousLinks = preferences.getStringList(
        'rewindbox.melonx.gameFolders',
      );
      final registered = <String>{
        for (final folder in config.config.romFolders)
          p.basename(folder).toLowerCase() == 'switch'
              ? folder
              : p.join(folder, 'switch'),
      };
      for (final encoded in previousLinks ?? <String>[]) {
        try {
          final entry = jsonDecode(encoded) as Map;
          final linked = await ExternalFolderAccess.resolveBookmarkedFolder(
            key: entry['bookmark'] as String,
          );
          final relative = entry['relative'] as String;
          if (linked != null &&
              !p.isAbsolute(relative) &&
              !p.split(relative).contains('..')) {
            registered.add(p.join(linked, relative));
          }
        } catch (_) {
          /* inaccessible sources retain their existing bookmark */
        }
      }
      if (!context.mounted) return false;
      final plan = await runMelonxProgress(
        context,
        control,
        (_) => MelonxMigrationService.analyze(
          source!,
          root,
          control,
          linkGames: kind == 'linked',
          registeredGameFolders: registered,
        ),
      );
      if (!context.mounted) return false;
      final free = await MelonxInternalService.channel.invokeMethod<int>(
        'storageCapacity',
      );
      if (free == null || free < plan.bytes)
        throw const FileSystemException('insufficientSpace');
      if (!context.mounted) return false;
      final summary = [
        text('compatibility'),
        '${text('space')}: ${plan.bytes} B',
        for (final item in plan.items)
          '${item.source.path}\n→ ${p.join(root.path, item.relative)}${item.conflict ? ' ⚠' : ''}',
        for (final folder in plan.linkedGames)
          '${text('linkGames')}: ${folder.path}',
        if (plan.items.any((item) => item.conflict)) text('conflicts'),
        if (plan.restartRequired) text('restart'),
        if (plan.unsupported.isNotEmpty)
          '${text('unsupported')}:\n${plan.unsupported.join('\n')}',
      ].join('\n\n');
      if (!await _confirm(
            context,
            text('migrate'),
            summary,
            text('transfer'),
          ) ||
          !context.mounted)
        return false;
      final links = [...?previousLinks];
      for (final folder in plan.linkedGames) {
        if (registered.any(
          (existing) =>
              p.equals(existing, folder.path) ||
              p.isWithin(existing, folder.path),
        ))
          continue;
        final relative = p.relative(folder.path, from: source.path);
        if (relative.startsWith('..') || p.isAbsolute(relative))
          throw const FormatException('unsafePath');
        links.add(jsonEncode({'bookmark': bookmark, 'relative': relative}));
      }
      bool linksChanged = false;
      try {
        await runMelonxProgress(
          context,
          control,
          (progress) => MelonxMigrationService.apply(
            plan,
            root,
            control,
            progress: (done, total) =>
                progress.value = MelonxProgress('transfer', done, total),
            registerLibrary: () async {
              if (links.length == (previousLinks?.length ?? 0)) return;
              linksChanged = true;
              if (!await preferences.setStringList(
                'rewindbox.melonx.gameFolders',
                links,
              )) {
                throw const FileSystemException('incompleteTransfer');
              }
            },
          ),
        );
      } catch (_) {
        if (linksChanged) {
          if (previousLinks == null) {
            await preferences.remove('rewindbox.melonx.gameFolders');
          } else {
            await preferences.setStringList(
              'rewindbox.melonx.gameFolders',
              previousLinks,
            );
          }
        }
        rethrow;
      }
      await config.addRomFolder(p.join(root.path, 'roms'), scan: false);
      await config.refreshDetectedSystems();
      if (plan.restartRequired && context.mounted) {
        await _confirm(
          context,
          text('migrate'),
          text('restart'),
          MelonxLibraryLocale.text(Localizations.localeOf(context), 'Done'),
        );
      }
      return true;
    } finally {
      await temporary.delete(recursive: true);
    }
  }),
);

Future<bool> _importSaves(
  BuildContext context,
  Directory source,
  Directory root,
  Directory temporary,
  MelonxTransferControl control,
) async {
  String text(String key) => MelonxTransferLocale.text(context, key);
  final info = await MelonxInternalService.content('storageInfo');
  final profiles = {
    for (final profile in info['profiles'] as List)
      '${profile['id']}': '${profile['name']} (${profile['id']})',
  };
  if (profiles.isEmpty) throw const FormatException('noSaves');
  final db = await SqliteService.getDatabase();
  final rows = await db.rawQuery(
    "SELECT DISTINCT title_id,title_name,filename FROM user_roms WHERE app_system_id IN (SELECT id FROM app_systems WHERE folder_name='switch') AND title_id IS NOT NULL",
  );
  final games = {
    for (final row in rows)
      if (RegExp(r'^[0-9a-fA-F]{16}$').hasMatch('${row['title_id']}'))
        '${row['title_id']}':
            '${row['title_name'] ?? row['filename']} (${row['title_id']})',
  };
  final candidates = await MelonxMigrationService.saves(source);
  if (candidates.isEmpty) throw const FormatException('noSaves');
  final prepared = <MelonxPreparedSave>[];
  for (final candidate in candidates) {
    if (!context.mounted) return false;
    final title =
        candidate.titleId ??
        await _choose(
          context,
          '${text('chooseGame')} — ${p.basename(candidate.folder.path)}',
          games,
        );
    if (title == null || !context.mounted) return false;
    final profile =
        candidate.profileId != null && profiles.containsKey(candidate.profileId)
        ? candidate.profileId
        : profiles.length == 1
        ? profiles.keys.single
        : await _choose(context, text('chooseProfile'), profiles);
    if (profile == null) return false;
    final association = {'titleId': title, 'profileId': profile};
    final staged = Directory(
      p.join(
        temporary.path,
        'saves',
        '${DateTime.now().microsecondsSinceEpoch}',
      ),
    );
    if (!context.mounted) return false;
    final save = await runMelonxProgress(context, control, (progress) async {
      progress.value = const MelonxProgress('transfer');
      return MelonxMigrationService.prepareSave(
        root,
        candidate,
        association,
        staged,
        control,
      );
    });
    final duplicate = prepared.indexWhere(
      (s) => s.item.relative == save.item.relative,
    );
    if (duplicate >= 0) {
      if (!context.mounted) return false;
      final choice = await _choose(context, text('selectSave'), {
        'previous': prepared[duplicate].item.source.path,
        'current': candidate.folder.path,
      });
      if (choice == null) return false;
      if (choice == 'current') prepared[duplicate] = save;
    } else {
      prepared.add(save);
    }
  }
  final launchProfiles = <String, String>{};
  for (final title
      in prepared
          .map((save) => save.association['titleId']!.toLowerCase())
          .toSet()) {
    final choices = prepared
        .where((save) => save.association['titleId']!.toLowerCase() == title)
        .map((save) => save.association['profileId']!)
        .toSet();
    if (!context.mounted) return false;
    final selected = choices.length == 1
        ? choices.single
        : await _choose(context, '${text('launchProfile')} — $title', {
            for (final profile in choices)
              profile: profiles[profile] ?? profile,
          });
    if (selected == null) return false;
    launchProfiles[title] = selected;
  }
  if (!context.mounted) return false;
  if (!await _confirm(
        context,
        text('importSaves'),
        [
          text('conflicts'),
          for (final entry in launchProfiles.entries)
            '${text('launchProfile')}: ${entry.key} / ${profiles[entry.value]}\n→ ${p.join(root.path, 'config', '${entry.key}_config.json')}',
          for (final save in prepared)
            '${save.association['titleId']} / ${save.association['profileId']}\n→ ${p.join(root.path, save.item.relative)}',
        ].join('\n\n'),
        text('replace'),
      ) ||
      !context.mounted)
    return false;
  final free = await MelonxInternalService.channel.invokeMethod<int>(
    'storageCapacity',
  );
  final bytes = prepared.fold<int>(0, (sum, save) => sum + save.item.bytes);
  if (free == null || free < bytes)
    throw const FileSystemException('insufficientSpace');
  if (!context.mounted) return false;
  await runMelonxProgress(
    context,
    control,
    (progress) => MelonxMigrationService.applySaves(
      root,
      prepared,
      control,
      launchProfiles: launchProfiles,
      progress: (done, total) =>
          progress.value = MelonxProgress('installing', done, total),
    ),
  );
  return true;
}
