import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/l10n/neoswap_locale.dart';
import 'package:neostation/l10n/storage_locale.dart';
import 'package:neostation/screens/libretro/libretro_bios_checker_screen.dart';
import 'package:neostation/screens/settings_screen/neoswap_dialog.dart';
import 'package:neostation/screens/storage/storage_audit_screen.dart';
import 'package:neostation/l10n/pairing_file_locale.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/pairing_file_service.dart';
import 'package:neostation/widgets/custom_notification.dart';

import 'settings_title.dart';
import 'widgets/settings_card_row.dart';
import 'widgets/settings_action_button.dart';
import '../../../widgets/glass/glass_surface.dart';

class ToolsSettingsContent extends StatefulWidget {
  final bool isContentFocused;
  final int selectedContentIndex;

  const ToolsSettingsContent({
    super.key,
    required this.isContentFocused,
    required this.selectedContentIndex,
  });

  @override
  State<ToolsSettingsContent> createState() => ToolsSettingsContentState();
}

class ToolsSettingsContentState extends State<ToolsSettingsContent> {
  static final _log = LoggerService.instance;

  bool _pairingStateLoaded = false;
  bool _hasPairingFile = false;
  bool _isImportingPairingFile = false;

  @override
  void initState() {
    super.initState();
    _refreshPairingState();
  }

  /// The BIOS checker of the embedded libretro cores (Build 440) exists on
  /// iOS only, where the engine runs (the platform Flutter reports, so a
  /// widget test can stand in for an iPhone).
  bool get _showBiosChecker => defaultTargetPlatform == TargetPlatform.iOS;

  /// The storage analysis and cleanup (docs/storage-audit-cleanup.md § 3.10)
  /// measures the iOS app container: iOS only, the same gate as the BIOS
  /// checker.
  bool get _showStorageAudit => defaultTargetPlatform == TargetPlatform.iOS;

  /// Pairing and NeoSwap everywhere; the BIOS checker third and the storage
  /// analysis fourth, on iOS. The StikDebug fallback row was removed: the
  /// integrated helper is the only JIT method.
  int getItemCount() => _showBiosChecker ? 4 : 2;

  final List<GlobalKey> _rowKeys = List<GlobalKey>.generate(
    4,
    (_) => GlobalKey(),
  );

  void _openNeoSwap() {
    showDialog<void>(context: context, builder: (_) => const NeoSwapDialog());
  }

  void _openBiosChecker() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => const LibretroBiosCheckerScreen(),
      ),
    );
  }

  void _openStorageAudit() {
    Navigator.of(
      context,
    ).push(MaterialPageRoute<void>(builder: (_) => const StorageAuditScreen()));
  }

  /// Keeps the row the controller selects on screen.
  void scrollToIndex(int index) {
    if (index < 0 || index >= _rowKeys.length) return;
    final rowContext = _rowKeys[index].currentContext;
    if (rowContext == null) return;
    Scrollable.ensureVisible(
      rowContext,
      alignment: 0.5,
      duration: const Duration(milliseconds: 150),
    );
  }

  void selectItem(int index) {
    if (index == 3 && _showStorageAudit) {
      _openStorageAudit();
      return;
    }
    if (index == 2 && _showBiosChecker) {
      _openBiosChecker();
      return;
    }
    if (index == 1) {
      _openNeoSwap();
      return;
    }
    if (index == 0) {
      _importOrReplacePairingFile();
    }
  }

  Future<void> _refreshPairingState() async {
    try {
      final configured = await PairingFileService.hasStoredPairingFile();
      if (!mounted) return;
      setState(() {
        _hasPairingFile = configured;
        _pairingStateLoaded = true;
      });
    } catch (error, stackTrace) {
      _log.log(
        'Could not inspect the stored pairing file.',
        level: LogLevel.warning,
        error: error,
        stackTrace: stackTrace,
      );
      if (!mounted) return;
      setState(() {
        _hasPairingFile = false;
        _pairingStateLoaded = true;
      });
    }
  }

  Future<void> _importOrReplacePairingFile() async {
    if (_isImportingPairingFile) return;

    setState(() => _isImportingPairingFile = true);

    try {
      final result = await PairingFileService.importFromPicker(
        dialogTitle: PairingFileLocale.get(
          context,
          PairingFileLocale.pickerTitle,
        ),
      );
      if (!mounted || result == null) return;

      setState(() {
        _hasPairingFile = true;
        _pairingStateLoaded = true;
      });

      AppNotification.showNotification(
        context,
        PairingFileLocale.get(
          context,
          result.replacedExisting
              ? PairingFileLocale.replaced
              : PairingFileLocale.imported,
        ),
        type: NotificationType.success,
      );
    } on PairingFileException catch (error) {
      if (!mounted) return;
      AppNotification.showNotification(
        context,
        _localizedPairingError(error.error),
        type: NotificationType.error,
      );
    } catch (error, stackTrace) {
      _log.e(
        'Failed to import the pairing file.',
        error: error,
        stackTrace: stackTrace,
      );
      if (!mounted) return;
      AppNotification.showNotification(
        context,
        PairingFileLocale.get(context, PairingFileLocale.importFailed),
        type: NotificationType.error,
      );
    } finally {
      if (mounted) setState(() => _isImportingPairingFile = false);
    }
  }

  String _localizedPairingError(PairingFileError error) {
    switch (error) {
      case PairingFileError.invalidExtension:
        return PairingFileLocale.get(
          context,
          PairingFileLocale.invalidExtension,
        );
      case PairingFileError.invalidFile:
        return PairingFileLocale.get(context, PairingFileLocale.invalidFile);
      case PairingFileError.remotePairingRequired:
        return PairingFileLocale.get(
          context,
          PairingFileLocale.remotePairingRequired,
        );
      case PairingFileError.unreadable:
        return PairingFileLocale.get(context, PairingFileLocale.importFailed);
    }
  }

  @override
  Widget build(BuildContext context) {
    final pairingSelected =
        widget.isContentFocused && widget.selectedContentIndex == 0;

    final pairingStatus = !_pairingStateLoaded
        ? PairingFileLocale.get(context, PairingFileLocale.checking)
        : _hasPairingFile
        ? PairingFileLocale.get(context, PairingFileLocale.configured)
        : PairingFileLocale.get(context, PairingFileLocale.notConfigured);

    final pairingDescription = _hasPairingFile
        ? PairingFileLocale.get(context, PairingFileLocale.configuredSubtitle)
        : PairingFileLocale.get(
            context,
            PairingFileLocale.notConfiguredSubtitle,
          );

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SettingsTitle(
          title: AppLocale.tools.getString(context),
          subtitle: AppLocale.toolsSubtitle.getString(context),
        ),
        const GlassGap(),
        Expanded(
          child: ListView(
            physics: const ClampingScrollPhysics(),
            children: [
              SettingsCardRow(
                key: _rowKeys[0],
                icon: Symbols.key_rounded,
                title: PairingFileLocale.get(context, PairingFileLocale.title),
                subtitle: '$pairingStatus — $pairingDescription',
                subtitleMaxLines: 3,
                selected: pairingSelected,
                onTap: _isImportingPairingFile
                    ? null
                    : _importOrReplacePairingFile,
                trailing: _isImportingPairingFile
                    ? SizedBox(
                        width: 22.r,
                        height: 22.r,
                        child: const CircularProgressIndicator(strokeWidth: 2),
                      )
                    : SettingsActionButton(
                        icon: _hasPairingFile
                            ? Symbols.change_circle_rounded
                            : Symbols.upload_file_rounded,
                        selected: pairingSelected,
                      ),
              ),
              SettingsCardRow(
                key: _rowKeys[1],
                icon: Icons.memory,
                title: NeoSwapLocale.get(context, 'title'),
                subtitle: NeoSwapLocale.get(context, 'scope'),
                subtitleMaxLines: 4,
                selected:
                    widget.isContentFocused && widget.selectedContentIndex == 1,
                onTap: _openNeoSwap,
                trailing: const Icon(Icons.chevron_right),
              ),
              if (_showBiosChecker)
                SettingsCardRow(
                  key: _rowKeys[2],
                  icon: Symbols.fact_check_rounded,
                  title: LibretroLocale.text(context, 'biosCheckerTitle'),
                  subtitle: LibretroLocale.text(context, 'biosCheckerSubtitle'),
                  subtitleMaxLines: 4,
                  selected:
                      widget.isContentFocused &&
                      widget.selectedContentIndex == 2,
                  onTap: _openBiosChecker,
                  trailing: const Icon(Icons.chevron_right),
                ),
              if (_showStorageAudit)
                SettingsCardRow(
                  key: _rowKeys[3],
                  icon: Symbols.storage_rounded,
                  title: StorageLocale.text(context, StorageLocale.toolTitle),
                  subtitle: StorageLocale.text(
                    context,
                    StorageLocale.toolSubtitle,
                  ),
                  subtitleMaxLines: 4,
                  selected:
                      widget.isContentFocused &&
                      widget.selectedContentIndex == 3,
                  onTap: _openStorageAudit,
                  trailing: const Icon(Icons.chevron_right),
                ),
            ],
          ),
        ),
      ],
    );
  }
}
