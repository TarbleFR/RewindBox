import 'package:flutter/material.dart';

import '../l10n/rpcs3_ui_locale.dart';
import '../services/rpcs3_content_import_service.dart';
import 'library_folder_report_dialog.dart';

/// The lines of a PS3 import result that refused files: what was imported,
/// then EVERY refused file with its reason, then a failed list refresh.
List<LibraryReportLine> rpcs3ImportReportLines({
  required int imported,
  required List<String> errors,
  required String? refreshError,
  required String Function(String key) t,
}) => <LibraryReportLine>[
  if (imported > 0)
    LibraryReportLine(
      LibraryReportLineKind.playlist,
      t('gamesImported').replaceAll('{count}', '$imported'),
    ),
  LibraryReportLine(
    LibraryReportLineKind.heading,
    t('refusedHeader').replaceAll('{count}', '${errors.length}'),
  ),
  for (final error in errors)
    LibraryReportLine(LibraryReportLineKind.warning, error),
  if (refreshError != null)
    LibraryReportLine(LibraryReportLineKind.problem, refreshError),
];

/// Whether the refused files are too many for a notice (which names
/// [Rpcs3ImportMessages.noticeLines] of them and sums up the rest).
bool rpcs3ImportNeedsReport(List<String> errors) =>
    errors.length > Rpcs3ImportMessages.noticeLines;

/// Shows the whole result until the user closes it. A notice that lasts a
/// few seconds cannot name ten refused files; this dialog scrolls.
Future<void> showRpcs3ImportReport(
  BuildContext context, {
  required int imported,
  required List<String> errors,
  String? refreshError,
}) {
  String t(String key) => Rpcs3UiLocale.text(context, key);
  return LibraryFolderReportDialog.showLines(
    context,
    title: t('importGames'),
    lines: rpcs3ImportReportLines(
      imported: imported,
      errors: errors,
      refreshError: refreshError,
      t: t,
    ),
  );
}
