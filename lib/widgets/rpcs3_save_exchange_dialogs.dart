import 'package:flutter/material.dart';

import '../l10n/rpcs3_saves_locale.dart';
import '../services/rpcs3_save_exchange_service.dart';
import 'library_focus_gamepad_layer.dart';

/// Lets the user choose where the saves come from. Null when cancelled.
Future<Rpcs3SaveImportSourceKind?> showRpcs3SaveImportSourceDialog(
  BuildContext context,
) => showDialog<Rpcs3SaveImportSourceKind>(
  context: context,
  useRootNavigator: true,
  builder: (_) => const Rpcs3SaveImportSourceDialog(),
);

/// Asks once whether the staged saves may replace the different saves
/// installed under the same names. Returns false when the user keeps them
/// (button, B or dismissal).
Future<bool> showRpcs3SaveReplaceDialog(
  BuildContext context,
  List<Rpcs3SaveImportCandidate> conflicts,
) async {
  final replace = await showDialog<bool>(
    context: context,
    useRootNavigator: true,
    barrierDismissible: false,
    builder: (_) => Rpcs3SaveReplaceDialog(conflicts: conflicts),
  );
  return replace ?? false;
}

/// Shows the per-save result of an import.
Future<void> showRpcs3SaveImportReport(
  BuildContext context,
  Rpcs3SaveImportReport report,
) => showDialog<void>(
  context: context,
  useRootNavigator: true,
  builder: (_) => Rpcs3SaveImportReportDialog(report: report),
);

/// Shows what an export produced and where, with a Share action.
Future<void> showRpcs3SaveExportReport(
  BuildContext context,
  Rpcs3SaveExportResult result, {
  required Future<void> Function(String zipPath) onShare,
}) => showDialog<void>(
  context: context,
  useRootNavigator: true,
  builder: (_) => Rpcs3SaveExportReportDialog(result: result, onShare: onShare),
);

/// Shows a refusal: translated [message], raw [technicalDetail] apart.
Future<void> showRpcs3SaveExchangeFailure(
  BuildContext context,
  String message, {
  String? technicalDetail,
}) => showDialog<void>(
  context: context,
  useRootNavigator: true,
  builder: (_) => Rpcs3SaveExchangeFailureDialog(
    message: message,
    technicalDetail: technicalDetail,
  ),
);

/// Translated text of a whole-operation failure.
String rpcs3SaveFailureText(
  BuildContext context,
  Rpcs3SaveExchangeFailure failure,
) {
  final key = switch (failure) {
    Rpcs3SaveExchangeFailure.noSaves => 'failNoSaves',
    Rpcs3SaveExchangeFailure.nothingFound => 'failNothingFound',
    Rpcs3SaveExchangeFailure.storageRedirected => 'reasonStorageRedirected',
    Rpcs3SaveExchangeFailure.notZip => 'failNotZip',
    Rpcs3SaveExchangeFailure.unreadable => 'reasonUnreadable',
    Rpcs3SaveExchangeFailure.exportWriteFailed => 'failExportWrite',
    Rpcs3SaveExchangeFailure.importWriteFailed => 'reasonWriteFailed',
  };
  return Rpcs3SavesLocale.text(context, key);
}

/// Translated explanation of a rejection; limits are inserted raw.
String? rpcs3SaveRejectionText(
  BuildContext context,
  Rpcs3SaveRejection? rejection,
) {
  String t(String key) => Rpcs3SavesLocale.text(context, key);
  String f(String key, Object max) =>
      Rpcs3SavesLocale.formatContext(context, key, {'max': max});
  return switch (rejection) {
    null => null,
    Rpcs3SaveRejection.invalidDirectoryName => t('reasonInvalidName'),
    Rpcs3SaveRejection.invalidParamSfo => t('reasonInvalidParamSfo'),
    Rpcs3SaveRejection.duplicateInSelection => t('reasonDuplicate'),
    Rpcs3SaveRejection.conflictKept => t('reasonConflictKept'),
    Rpcs3SaveRejection.storageRedirected => t('reasonStorageRedirected'),
    Rpcs3SaveRejection.unsafeEntry => t('reasonUnsafeEntry'),
    Rpcs3SaveRejection.symbolicLink => t('reasonSymbolicLink'),
    Rpcs3SaveRejection.tooManyEntries => f(
      'reasonTooManyEntries',
      Rpcs3SaveExchangeService.defaultMaxEntries,
    ),
    Rpcs3SaveRejection.tooLarge => f(
      'reasonTooLarge',
      Rpcs3SaveExchangeService.defaultMaxTotalLabel,
    ),
    Rpcs3SaveRejection.fileTooLarge => f(
      'reasonFileTooLarge',
      Rpcs3SaveExchangeService.defaultMaxFileLabel,
    ),
    Rpcs3SaveRejection.invalidArchive => t('reasonInvalidArchive'),
    Rpcs3SaveRejection.noSaveFound => t('reasonNoSave'),
    Rpcs3SaveRejection.unreadable => t('reasonUnreadable'),
    Rpcs3SaveRejection.corruptData => t('reasonCorruptData'),
    Rpcs3SaveRejection.writeFailed => t('reasonWriteFailed'),
  };
}

class Rpcs3SaveImportSourceDialog extends StatelessWidget {
  const Rpcs3SaveImportSourceDialog({super.key});

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3SavesLocale.text(context, key);
    Widget option({
      required Key key,
      required IconData icon,
      required String title,
      required String hint,
      required Rpcs3SaveImportSourceKind kind,
      bool autofocus = false,
    }) => LibraryFocusRing(
      radius: 8,
      child: ListTile(
        key: key,
        autofocus: autofocus,
        leading: Icon(icon),
        title: Text(title),
        subtitle: Text(hint),
        onTap: () => Navigator.of(context).pop(kind),
      ),
    );

    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_saves_source',
      autofocus: false,
      onBack: () => Navigator.of(context).pop(),
      child: AlertDialog(
        key: const ValueKey('rpcs3-saves-source-dialog'),
        title: Text(t('importSourceTitle')),
        contentPadding: const EdgeInsets.fromLTRB(8, 16, 8, 0),
        content: SizedBox(
          width: 480,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Text(t('importSourceBody')),
                ),
                const SizedBox(height: 8),
                option(
                  key: const ValueKey('rpcs3-saves-source-files'),
                  icon: Icons.folder_special_outlined,
                  title: t('sourceFilesFolder'),
                  hint: t('sourceFilesFolderHint'),
                  kind: Rpcs3SaveImportSourceKind.filesFolder,
                  autofocus: true,
                ),
                option(
                  key: const ValueKey('rpcs3-saves-source-zip'),
                  icon: Icons.folder_zip_outlined,
                  title: t('sourceZip'),
                  hint: t('sourceZipHint'),
                  kind: Rpcs3SaveImportSourceKind.zipFile,
                ),
                option(
                  key: const ValueKey('rpcs3-saves-source-folder'),
                  icon: Icons.folder_open_outlined,
                  title: t('sourceFolder'),
                  hint: t('sourceFolderHint'),
                  kind: Rpcs3SaveImportSourceKind.folder,
                ),
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: TextButton(
              key: const ValueKey('rpcs3-saves-source-cancel'),
              onPressed: () => Navigator.of(context).pop(),
              child: Text(t('cancel')),
            ),
          ),
        ],
      ),
    );
  }
}

class Rpcs3SaveReplaceDialog extends StatelessWidget {
  const Rpcs3SaveReplaceDialog({super.key, required this.conflicts});

  final List<Rpcs3SaveImportCandidate> conflicts;

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3SavesLocale.text(context, key);
    final theme = Theme.of(context);
    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_saves_replace',
      autofocus: false,
      onBack: () => Navigator.of(context).pop(false),
      child: AlertDialog(
        key: const ValueKey('rpcs3-saves-replace-dialog'),
        title: Text(t('replaceTitle')),
        content: SizedBox(
          width: 480,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Rpcs3SavesLocale.formatContext(context, 'replaceBody', {
                    'count': conflicts.length,
                  }),
                ),
                const SizedBox(height: 12),
                for (final candidate in conflicts) ...[
                  Text(
                    candidate.name,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                    ),
                  ),
                  if (candidate.title != null)
                    Padding(
                      padding: const EdgeInsets.only(left: 12, bottom: 4),
                      child: Text(
                        candidate.title!,
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: TextButton(
              key: const ValueKey('rpcs3-saves-keep'),
              autofocus: true,
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(t('keepExisting')),
            ),
          ),
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-saves-replace'),
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(t('replace')),
            ),
          ),
        ],
      ),
    );
  }
}

class Rpcs3SaveImportReportDialog extends StatelessWidget {
  const Rpcs3SaveImportReportDialog({super.key, required this.report});

  final Rpcs3SaveImportReport report;

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3SavesLocale.text(context, key);
    String count(String key, int value) =>
        Rpcs3SavesLocale.formatContext(context, key, {'count': value});
    final summary = <String>[
      if (report.imported > 0) count('countImported', report.imported),
      if (report.replaced > 0) count('countReplaced', report.replaced),
      if (report.alreadyPresent > 0)
        count('countAlreadyPresent', report.alreadyPresent),
      if (report.kept > 0) count('countKept', report.kept),
      if (report.rejected > 0) count('countRejected', report.rejected),
    ];
    final theme = Theme.of(context);
    final small = theme.textTheme.bodySmall;
    final source = report.sourceKind == Rpcs3SaveImportSourceKind.filesFolder
        ? t('importLocation')
        : Rpcs3SavesLocale.formatContext(context, 'importSourceLabel', {
            'name': report.sourceName,
          });

    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_saves_report',
      autofocus: false,
      child: AlertDialog(
        key: const ValueKey('rpcs3-saves-report'),
        title: Text(t('importTitle')),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  summary.join(' • '),
                  key: const ValueKey('rpcs3-saves-summary'),
                  style: theme.textTheme.titleSmall,
                ),
                const SizedBox(height: 4),
                Text(source, style: small),
                const SizedBox(height: 12),
                for (var index = 0; index < report.entries.length; index++)
                  Rpcs3SaveReportRow(
                    key: ValueKey('rpcs3-saves-row-$index'),
                    entry: report.entries[index],
                  ),
                const SizedBox(height: 12),
                Text(t('importDestination'), style: small),
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-saves-close'),
              autofocus: true,
              onPressed: () => Navigator.of(context).pop(),
              child: Text(t('close')),
            ),
          ),
        ],
      ),
    );
  }
}

class Rpcs3SaveExportReportDialog extends StatelessWidget {
  const Rpcs3SaveExportReportDialog({
    super.key,
    required this.result,
    required this.onShare,
  });

  final Rpcs3SaveExportResult result;
  final Future<void> Function(String zipPath) onShare;

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3SavesLocale.text(context, key);
    String f(String key, Map<String, Object?> values) =>
        Rpcs3SavesLocale.formatContext(context, key, values);
    final theme = Theme.of(context);
    final small = theme.textTheme.bodySmall;
    final mono = small?.copyWith(fontFamily: 'monospace');

    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_saves_export',
      autofocus: false,
      child: AlertDialog(
        key: const ValueKey('rpcs3-saves-export-report'),
        title: Text(t('exportTitle')),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  f('exportSummary', {
                    'saves': result.saveCount,
                    'files': result.fileCount,
                    'size': Rpcs3SaveExchangeService.formatBytes(
                      result.byteCount,
                    ),
                  }),
                  key: const ValueKey('rpcs3-saves-export-summary'),
                  style: theme.textTheme.titleSmall,
                ),
                const SizedBox(height: 8),
                Text(f('exportLocation', {'file': result.zipFileName})),
                const SizedBox(height: 4),
                Text(t('exportShareHint'), style: small),
                const SizedBox(height: 12),
                for (final directory in result.directories)
                  Text(directory, style: mono),
                if (result.skipped.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    f('exportSkipped', {'count': result.skipped.length}),
                    style: theme.textTheme.titleSmall,
                  ),
                  for (var index = 0; index < result.skipped.length; index++)
                    Rpcs3SaveReportRow(
                      key: ValueKey('rpcs3-saves-skipped-$index'),
                      entry: result.skipped[index],
                    ),
                ],
                if (result.otherUsersWithSaves.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text(
                    f('exportOtherUsers', {
                      'users': result.otherUsersWithSaves.join(', '),
                    }),
                    style: small,
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: TextButton.icon(
              key: const ValueKey('rpcs3-saves-share'),
              onPressed: () => onShare(result.zipPath),
              icon: const Icon(Icons.ios_share),
              label: Text(t('share')),
            ),
          ),
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-saves-export-close'),
              autofocus: true,
              onPressed: () => Navigator.of(context).pop(),
              child: Text(t('close')),
            ),
          ),
        ],
      ),
    );
  }
}

class Rpcs3SaveExchangeFailureDialog extends StatelessWidget {
  const Rpcs3SaveExchangeFailureDialog({
    super.key,
    required this.message,
    this.technicalDetail,
  });

  final String message;
  final String? technicalDetail;

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3SavesLocale.text(context, key);
    final theme = Theme.of(context);
    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_saves_failure',
      autofocus: false,
      child: AlertDialog(
        key: const ValueKey('rpcs3-saves-failure'),
        title: Text(t('errorTitle')),
        content: SizedBox(
          width: 480,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(message),
                if (technicalDetail != null) ...[
                  const SizedBox(height: 8),
                  Text(
                    technicalDetail!,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                      color: theme.colorScheme.onSurfaceVariant,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-saves-failure-close'),
              autofocus: true,
              onPressed: () => Navigator.of(context).pop(),
              child: Text(t('close')),
            ),
          ),
        ],
      ),
    );
  }
}

/// One save of a report: raw name and title, translated status and reason,
/// raw diagnostic apart. Focusable so a controller can scroll the list.
class Rpcs3SaveReportRow extends StatelessWidget {
  const Rpcs3SaveReportRow({super.key, required this.entry});

  final Rpcs3SaveImportEntry entry;

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3SavesLocale.text(context, key);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final (icon, color, status) = switch (entry.status) {
      Rpcs3SaveImportStatus.imported => (
        Icons.check_circle_outline,
        scheme.primary,
        t('statusImported'),
      ),
      Rpcs3SaveImportStatus.replaced => (
        Icons.published_with_changes,
        scheme.primary,
        t('statusReplaced'),
      ),
      Rpcs3SaveImportStatus.alreadyPresent => (
        Icons.verified_outlined,
        scheme.secondary,
        t('statusAlreadyPresent'),
      ),
      Rpcs3SaveImportStatus.kept => (
        Icons.shield_outlined,
        scheme.secondary,
        t('statusKept'),
      ),
      Rpcs3SaveImportStatus.rejected => (
        Icons.block,
        scheme.error,
        t('statusRejected'),
      ),
    };
    final explanation = rpcs3SaveRejectionText(context, entry.rejection);
    final small = theme.textTheme.bodySmall;
    final showSize =
        entry.fileCount > 0 && entry.status != Rpcs3SaveImportStatus.rejected;

    return LibraryFocusRing(
      radius: 8,
      child: Focus(
        child: MergeSemantics(
          child: Padding(
            padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                ExcludeSemantics(child: Icon(icon, color: color, size: 20)),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        entry.name,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      if (entry.title != null) Text(entry.title!, style: small),
                      Text(
                        status,
                        style: theme.textTheme.labelLarge?.copyWith(
                          color: color,
                        ),
                      ),
                      if (showSize)
                        Text(
                          Rpcs3SavesLocale.formatContext(context, 'itemSize', {
                            'files': entry.fileCount,
                            'size': Rpcs3SaveExchangeService.formatBytes(
                              entry.byteCount,
                            ),
                          }),
                          style: small,
                        ),
                      if (entry.status == Rpcs3SaveImportStatus.replaced)
                        Text(t('backupKept'), style: small),
                      if (explanation != null) Text(explanation, style: small),
                      if (entry.technicalDetail != null)
                        Text(
                          entry.technicalDetail!,
                          style: small?.copyWith(
                            fontFamily: 'monospace',
                            color: scheme.onSurfaceVariant,
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
}
