import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_link_locale.dart';
import 'package:neostation/services/gamepad/gamepad_navigation_manager.dart';
import 'package:neostation/services/library_folder_inspection.dart';
import 'package:neostation/utils/gamepad_nav.dart';

enum LibraryReportLineKind { folder, heading, playlist, detail, warning, problem }

/// One line of the report shown before a library folder is added.
class LibraryReportLine {
  const LibraryReportLine(this.kind, this.text);

  final LibraryReportLineKind kind;
  final String text;
}

/// The report of a [LibraryFolderInspection] as lines of text: which folder
/// feeds which playlist first, then what is left out, each with its reason.
abstract final class LibraryFolderReport {
  /// Unrecognised folders listed before the rest is summed up.
  static const int unknownLimit = 8;

  static List<LibraryReportLine> lines(
    LibraryFolderInspection inspection, {
    required String language,
    required String location,
    required List<String> exampleFolders,
  }) {
    String t(String key, [Map<String, Object?> values = const <String, Object?>{}]) =>
        LibraryLinkLocale.textFor(language, key, values);

    final lines = <LibraryReportLine>[LibraryReportLine(LibraryReportLineKind.folder, t('reportFolder', {'folder': location}))];
    if (!inspection.recognised) {
      lines.add(LibraryReportLine(
        LibraryReportLineKind.problem,
        t('reportNothing', {'examples': exampleFolders.join(', ')}),
      ));
    }
    final scanned = inspection.scanned.toList();
    if (scanned.isNotEmpty) {
      lines.add(LibraryReportLine(LibraryReportLineKind.heading, t('reportScanned')));
      for (final console in scanned) {
        lines.add(LibraryReportLine(
          LibraryReportLineKind.playlist,
          t(console.games > 0 ? 'reportConsole' : 'reportConsoleEmpty', {
            'console': console.system.name,
            'folder': console.folderName,
            'count': console.games,
          }),
        ));
        if (console.examples.isNotEmpty) {
          lines.add(LibraryReportLine(
            LibraryReportLineKind.detail,
            t('reportExamples', {'names': console.examples.join(', ')}),
          ));
        }
      }
    }
    for (final console in inspection.importOnly) {
      lines.add(LibraryReportLine(
        LibraryReportLineKind.warning,
        t('reportImportOnly', {
          'console': console.system.name,
          'folder': console.folderName,
          'count': console.games,
        }),
      ));
    }
    if (inspection.unknownFolders.isNotEmpty) {
      lines.add(LibraryReportLine(LibraryReportLineKind.heading, t('reportUnknownTitle')));
      for (final folder in inspection.unknownFolders.take(unknownLimit)) {
        final suggestion = folder.suggestion;
        lines.add(LibraryReportLine(
          LibraryReportLineKind.warning,
          suggestion == null
              ? t('reportUnknown', {'folder': folder.folderName, 'count': folder.files})
              : t('reportUnknownSuggest', {
                  'folder': folder.folderName,
                  'count': folder.files,
                  'console': suggestion.name,
                  'name': suggestion.primaryFolder,
                }),
        ));
      }
      final more = inspection.unknownFolders.length - unknownLimit;
      if (more > 0) lines.add(LibraryReportLine(LibraryReportLineKind.detail, '+ $more'));
    }
    if (inspection.looseGames > 0) {
      lines.add(LibraryReportLine(LibraryReportLineKind.warning, t('reportLoose', {'count': inspection.looseGames})));
    }
    if (inspection.truncated) {
      lines.add(LibraryReportLine(LibraryReportLineKind.detail, t('reportTruncated')));
    }
    return lines;
  }
}

/// Shows what RewindBox will read in a library folder, before it is added.
///
/// Gamepad wiring follows `ConfirmActionDialog` (the layer is pushed after
/// the first frame); up and down scroll a long report. Returns `true` when
/// the user confirms, `false` on cancel, back or dismissal.
class LibraryFolderReportDialog extends StatefulWidget {
  const LibraryFolderReportDialog({
    super.key,
    required this.lines,
    required this.confirmLabel,
    required this.positive,
  });

  final List<LibraryReportLine> lines;
  final String confirmLabel;

  /// Whether confirming adds the folder (primary colour) or only leads to
  /// another choice (neutral colour).
  final bool positive;

  /// [confirmKey] is the `LibraryLinkLocale` key of the confirm button;
  /// [confirmLabel], when given, is shown instead.
  static Future<bool> show(
    BuildContext context, {
    required LibraryFolderInspection inspection,
    required String location,
    required List<String> exampleFolders,
    required String confirmKey,
    String? confirmLabel,
    bool positive = true,
  }) async {
    final language = LibraryLinkLocale.languageOf(Localizations.localeOf(context));
    final result = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (_) => LibraryFolderReportDialog(
        lines: LibraryFolderReport.lines(
          inspection,
          language: language,
          location: location,
          exampleFolders: exampleFolders,
        ),
        confirmLabel: confirmLabel ?? LibraryLinkLocale.textFor(language, confirmKey),
        positive: positive,
      ),
    );
    return result ?? false;
  }

  @override
  State<LibraryFolderReportDialog> createState() => _LibraryFolderReportDialogState();
}

class _LibraryFolderReportDialogState extends State<LibraryFolderReportDialog> {
  static const String _layer = 'library_folder_report_dialog';

  late final GamepadNavigation _gamepadNav;
  final ScrollController _scroll = ScrollController();

  void _scrollBy(double delta) {
    if (!_scroll.hasClients) return;
    final position = _scroll.position;
    final target = (position.pixels + delta).clamp(position.minScrollExtent, position.maxScrollExtent);
    _scroll.animateTo(target.toDouble(), duration: const Duration(milliseconds: 120), curve: Curves.easeOut);
  }

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onNavigateUp: () => _scrollBy(-72),
      onNavigateDown: () => _scrollBy(72),
      onSelectItem: () {
        if (mounted) Navigator.of(context).pop(true);
      },
      onBack: () {
        if (mounted) Navigator.of(context).pop(false);
      },
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        _layer,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(_layer);
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  TextStyle? _style(ThemeData theme, LibraryReportLineKind kind) {
    final base = theme.textTheme.bodyMedium?.copyWith(fontSize: 11.r);
    switch (kind) {
      case LibraryReportLineKind.folder:
        return base?.copyWith(color: theme.colorScheme.onSurface.withValues(alpha: 0.7));
      case LibraryReportLineKind.heading:
        return base?.copyWith(fontWeight: FontWeight.w700, color: theme.colorScheme.onSurface);
      case LibraryReportLineKind.playlist:
        return base?.copyWith(color: theme.colorScheme.primary, fontWeight: FontWeight.w600);
      case LibraryReportLineKind.detail:
        return base?.copyWith(fontSize: 10.r, color: theme.colorScheme.onSurface.withValues(alpha: 0.6));
      case LibraryReportLineKind.warning:
        return base?.copyWith(color: theme.colorScheme.tertiary);
      case LibraryReportLineKind.problem:
        return base?.copyWith(color: theme.colorScheme.error, fontWeight: FontWeight.w600);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final accent = widget.positive ? theme.colorScheme.primary : theme.colorScheme.secondary;
    final onAccent = widget.positive ? theme.colorScheme.onPrimary : theme.colorScheme.onSecondary;
    final language = LibraryLinkLocale.languageOf(Localizations.localeOf(context));
    return AlertDialog(
      shape: RoundedRectangleBorder(
        borderRadius: theme.dialogTheme.shape is RoundedRectangleBorder
            ? (theme.dialogTheme.shape as RoundedRectangleBorder).borderRadius
            : BorderRadius.circular(12.r),
        side: BorderSide(color: accent.withValues(alpha: 0.3)),
      ),
      title: Row(
        children: [
          Icon(Icons.folder_open_outlined, color: accent, size: 20.r),
          SizedBox(width: 8.r),
          Flexible(
            child: Text(
              LibraryLinkLocale.textFor(language, 'reportTitle'),
              style: theme.textTheme.titleMedium?.copyWith(
                fontSize: 14.r,
                color: accent,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
      content: ConstrainedBox(
        constraints: BoxConstraints(
          maxWidth: 520.r,
          maxHeight: MediaQuery.of(context).size.height * 0.55,
        ),
        child: Scrollbar(
          controller: _scroll,
          child: SingleChildScrollView(
            controller: _scroll,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final line in widget.lines)
                  Padding(
                    padding: EdgeInsets.only(
                      top: line.kind == LibraryReportLineKind.heading ? 8.r : 2.r,
                      left: line.kind == LibraryReportLineKind.detail ? 12.r : 0,
                    ),
                    child: Text(line.text, style: _style(theme, line.kind)),
                  ),
              ],
            ),
          ),
        ),
      ),
      actions: [
        TextButton(
          key: const ValueKey('library-folder-report-cancel'),
          onPressed: () => Navigator.of(context).pop(false),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 18.r,
                height: 18.r,
                child: Image.asset(
                  'assets/images/gamepad/Xbox_B_button.png',
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  colorBlendMode: BlendMode.srcIn,
                ),
              ),
              SizedBox(width: 4.r),
              Text(
                AppLocale.cancel.getString(context),
                style: TextStyle(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  fontSize: 12.r,
                ),
              ),
            ],
          ),
        ),
        ElevatedButton(
          key: const ValueKey('library-folder-report-confirm'),
          style: ElevatedButton.styleFrom(
            backgroundColor: accent,
            foregroundColor: onAccent,
            padding: EdgeInsets.symmetric(horizontal: 16.r, vertical: 8.r),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6.r)),
          ),
          onPressed: () => Navigator.of(context).pop(true),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              SizedBox(
                width: 18.r,
                height: 18.r,
                child: Image.asset(
                  'assets/images/gamepad/Xbox_A_button.png',
                  color: onAccent,
                  colorBlendMode: BlendMode.srcIn,
                ),
              ),
              SizedBox(width: 4.r),
              Flexible(
                child: Text(
                  widget.confirmLabel,
                  style: TextStyle(color: onAccent, fontSize: 12.r, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
