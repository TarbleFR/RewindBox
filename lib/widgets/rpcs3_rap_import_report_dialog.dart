import 'package:flutter/material.dart';

import '../l10n/rpcs3_rap_locale.dart';
import '../services/rpcs3_rap_licence_service.dart';
import 'library_focus_gamepad_layer.dart';

/// Asks once whether the selected RAP licences may replace the different
/// licences installed under the same content IDs. Returns false when the
/// user keeps them (button, B or dismissal).
Future<bool> showRpcs3RapReplaceDialog(
  BuildContext context,
  List<String> contentIds,
) async {
  final replace = await showDialog<bool>(
    context: context,
    useRootNavigator: true,
    barrierDismissible: false,
    builder: (_) => Rpcs3RapReplaceDialog(contentIds: contentIds),
  );
  return replace ?? false;
}

/// Shows the per-file result of a RAP licence import.
Future<void> showRpcs3RapImportReport(
  BuildContext context,
  Rpcs3RapImportReport report,
) => showDialog<void>(
  context: context,
  useRootNavigator: true,
  builder: (_) => Rpcs3RapImportReportDialog(report: report),
);

class Rpcs3RapReplaceDialog extends StatelessWidget {
  const Rpcs3RapReplaceDialog({super.key, required this.contentIds});

  final List<String> contentIds;

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3RapLocale.text(context, key);
    final theme = Theme.of(context);
    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_rap_replace',
      autofocus: false,
      onBack: () => Navigator.of(context).pop(false),
      child: AlertDialog(
        key: const ValueKey('rpcs3-rap-replace-dialog'),
        title: Text(t('rapReplaceTitle')),
        content: SizedBox(
          width: 480,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Rpcs3RapLocale.formatContext(context, 'rapReplaceBody', {
                    'count': contentIds.length,
                  }),
                ),
                const SizedBox(height: 12),
                for (final id in contentIds)
                  Text(
                    id,
                    style: theme.textTheme.bodySmall?.copyWith(
                      fontFamily: 'monospace',
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: TextButton(
              key: const ValueKey('rpcs3-rap-keep'),
              autofocus: true,
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(t('rapKeep')),
            ),
          ),
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-rap-replace'),
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(t('rapReplace')),
            ),
          ),
        ],
      ),
    );
  }
}

class Rpcs3RapImportReportDialog extends StatelessWidget {
  const Rpcs3RapImportReportDialog({super.key, required this.report});

  final Rpcs3RapImportReport report;

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3RapLocale.text(context, key);
    String count(String key, int value) =>
        Rpcs3RapLocale.formatContext(context, key, {'count': value});
    final summary = <String>[
      if (report.imported > 0) count('rapCountImported', report.imported),
      if (report.replaced > 0) count('rapCountReplaced', report.replaced),
      if (report.alreadyPresent > 0)
        count('rapCountAlreadyPresent', report.alreadyPresent),
      if (report.rejected > 0) count('rapCountRejected', report.rejected),
    ];
    final theme = Theme.of(context);

    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_rap_report',
      autofocus: false,
      child: AlertDialog(
        key: const ValueKey('rpcs3-rap-report'),
        title: Text(t('rapReportTitle')),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  summary.join(' • '),
                  key: const ValueKey('rpcs3-rap-summary'),
                  style: theme.textTheme.titleSmall,
                ),
                const SizedBox(height: 12),
                for (var index = 0; index < report.entries.length; index++)
                  _ReportRow(
                    key: ValueKey('rpcs3-rap-row-$index'),
                    entry: report.entries[index],
                  ),
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-rap-close'),
              autofocus: true,
              onPressed: () => Navigator.of(context).pop(),
              child: Text(t('rapClose')),
            ),
          ),
        ],
      ),
    );
  }
}

class _ReportRow extends StatelessWidget {
  const _ReportRow({super.key, required this.entry});

  final Rpcs3RapImportEntry entry;

  /// Translated explanation of a rejection; file names, content IDs and
  /// sizes are inserted raw.
  static String? reason(BuildContext context, Rpcs3RapImportEntry entry) {
    String t(String key) => Rpcs3RapLocale.text(context, key);
    return switch (entry.rejection) {
      null => null,
      Rpcs3RapRejection.notRapFile => t('rapReasonNotRap'),
      Rpcs3RapRejection.invalidContentId => Rpcs3RapLocale.formatContext(
        context,
        'rapReasonContentId',
        {'example': Rpcs3RapLicenceService.exampleContentId},
      ),
      Rpcs3RapRejection.invalidSize => Rpcs3RapLocale.formatContext(
        context,
        'rapReasonSize',
        {'size': entry.byteCount ?? 0},
      ),
      Rpcs3RapRejection.unreadable => t('rapReasonUnreadable'),
      Rpcs3RapRejection.selectionConflict => t('rapReasonSelectionConflict'),
      Rpcs3RapRejection.conflictKept => t('rapReasonConflictKept'),
      Rpcs3RapRejection.storageRedirected => t('rapReasonStorageRedirected'),
      Rpcs3RapRejection.writeFailed => t('rapReasonWriteFailed'),
    };
  }

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3RapLocale.text(context, key);
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final (icon, color, status) = switch (entry.status) {
      Rpcs3RapImportStatus.imported => (
        Icons.check_circle_outline,
        scheme.primary,
        t('rapStatusImported'),
      ),
      Rpcs3RapImportStatus.replaced => (
        Icons.published_with_changes,
        scheme.primary,
        t('rapStatusReplaced'),
      ),
      Rpcs3RapImportStatus.alreadyPresent => (
        Icons.verified_outlined,
        scheme.secondary,
        t('rapStatusAlreadyPresent'),
      ),
      Rpcs3RapImportStatus.rejected => (
        Icons.block,
        scheme.error,
        t('rapStatusRejected'),
      ),
    };
    final installedName = entry.installedName;
    final renamed =
        entry.status != Rpcs3RapImportStatus.rejected &&
        installedName != null &&
        installedName != entry.fileName;
    final explanation = reason(context, entry);
    final small = theme.textTheme.bodySmall;

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
                        entry.fileName,
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      Text(
                        status,
                        style: theme.textTheme.labelLarge?.copyWith(
                          color: color,
                        ),
                      ),
                      if (renamed)
                        Text(
                          Rpcs3RapLocale.formatContext(
                            context,
                            'rapInstalledAs',
                            {'name': installedName},
                          ),
                          style: small,
                        ),
                      if (entry.status == Rpcs3RapImportStatus.replaced)
                        Text(t('rapBackupKept'), style: small),
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
