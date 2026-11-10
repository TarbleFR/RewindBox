import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/xenia_locale.dart';
import '../screens/xenia/xenia_settings_screen.dart';
import '../services/xenia_internal_service.dart';

/// Import button of the Xbox 360 playlist, at the place of the other
/// embedded playlists' buttons: import games from Files, Xbox 360 settings.
class XeniaInternalPlaylistActions extends StatefulWidget {
  const XeniaInternalPlaylistActions({
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
  State<XeniaInternalPlaylistActions> createState() =>
      _XeniaInternalPlaylistActionsState();
}

class _XeniaInternalPlaylistActionsState
    extends State<XeniaInternalPlaylistActions> {
  bool _busy = false;

  String _t(String key) => XeniaLocale.text(context, key);
  String _tf(String key, Map<String, Object?> values) =>
      XeniaLocale.textf(context, key, values);

  void _interaction(bool active) => widget.onInteractionChanged?.call(active);

  void _notice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _import() async {
    final control = XeniaImportControl();
    final progress = ValueNotifier<XeniaImportProgress?>(null);
    var dialogShown = false;
    void showProgress() {
      if (dialogShown || !mounted) return;
      dialogShown = true;
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (context) =>
            _XeniaImportDialog(progress: progress, onCancel: control.cancel),
      );
    }

    XeniaImportResult? result;
    try {
      result = await XeniaInternalService.importGames(
        control: control,
        onProgress: (value) {
          progress.value = value;
          showProgress();
        },
      );
    } finally {
      if (dialogShown && mounted) Navigator.of(context).pop();
      progress.dispose();
    }
    if (result == null || !mounted) return;
    if (result.imported > 0) await widget.onLibraryChanged();
    if (!mounted) return;
    if (result.cancelled) _notice(_t('cancelled'));
    if (result.imported > 0) {
      _notice(_tf('imported', {'count': result.imported}));
    }
    if (result.duplicates > 0) {
      _notice(_tf('duplicates', {'count': result.duplicates}));
    }
    for (final item in result.rejected.take(3)) {
      _notice(
        _tf('rejectedItem', {'name': item.name, 'reason': _t(item.reason)}),
      );
    }
  }

  Future<void> _selected(String action) async {
    if (_busy) return;
    setState(() => _busy = true);
    _interaction(true);
    try {
      if (action == 'games') {
        await _import();
      } else if (action == 'settings') {
        await XeniaSettingsScreen.open(context);
      }
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
        key: const ValueKey('xenia-internal-import-menu'),
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
            key: const ValueKey('xenia-import-games'),
            value: 'games',
            child: Text(_t('importGames')),
          ),
          PopupMenuItem(
            key: const ValueKey('xenia-global-settings'),
            value: 'settings',
            child: Text(_t('globalSettings')),
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

class _XeniaImportDialog extends StatelessWidget {
  const _XeniaImportDialog({required this.progress, required this.onCancel});

  final ValueListenable<XeniaImportProgress?> progress;
  final VoidCallback onCancel;

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: false,
      child: AlertDialog(
        content: ValueListenableBuilder<XeniaImportProgress?>(
          valueListenable: progress,
          builder: (context, value, _) => Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(
                XeniaLocale.textf(context, 'importing', {
                  'name': value?.name ?? '',
                  'index': value?.index ?? 0,
                  'count': value?.count ?? 0,
                }),
              ),
              const SizedBox(height: 12),
              LinearProgressIndicator(value: value?.fraction),
            ],
          ),
        ),
        actions: [
          TextButton(
            key: const ValueKey('xenia-import-cancel'),
            autofocus: true,
            onPressed: onCancel,
            child: Text(XeniaLocale.text(context, 'cancel')),
          ),
        ],
      ),
    );
  }
}
