import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/switch2_library_locale.dart';
import '../services/s2arm_internal_service.dart';
import '../services/storage/storage_import_activity.dart';

/// Import button of the Switch 2 playlist, at the place of the other embedded
/// playlists' buttons: import a Switch 2 export folder from Files
/// (docs/s2arm-switch2-library.md § Import).
class S2ArmInternalPlaylistActions extends StatefulWidget {
  const S2ArmInternalPlaylistActions({
    super.key,
    required this.onLibraryChanged,
    this.onInteractionChanged,
    this.embedded = false,
  });

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
          dialogTitle: _t('importFolder'),
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
        '${item.name}: ${S2ArmInternalService.localizedError(locale, item.reason)}',
      );
    }
  }

  Future<void> _selected(String action) async {
    if (_busy) return;
    setState(() => _busy = true);
    _interaction(true);
    try {
      if (action == 'folder') await _import();
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _interaction(false);
      }
    }
  }

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
            child: Text(_t('importFolder')),
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
