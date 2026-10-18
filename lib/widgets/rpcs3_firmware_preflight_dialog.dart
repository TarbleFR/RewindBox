import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/rpcs3_firmware_locale.dart';
import 'library_focus_gamepad_layer.dart';

/// Shown before every PS3 firmware installation or reinstallation (Build 482):
/// the Get More RAM app and its procedure come first, then the user returns
/// here for the PS3UPDAT.PUP file. Returns true to continue to the firmware
/// picker, false to go back (button, B or dismissal). Continuing is an
/// acknowledgement only: nothing here inspects the phone's configuration.
Future<bool> showRpcs3FirmwarePreflight(
  BuildContext context, {
  required bool reinstall,
  Future<bool> Function(Uri uri)? openUrl,
}) async {
  final proceed = await showDialog<bool>(
    context: context,
    useRootNavigator: true,
    barrierDismissible: false,
    builder: (_) =>
        Rpcs3FirmwarePreflightDialog(reinstall: reinstall, openUrl: openUrl),
  );
  return proceed ?? false;
}

class Rpcs3FirmwarePreflightDialog extends StatefulWidget {
  const Rpcs3FirmwarePreflightDialog({
    super.key,
    required this.reinstall,
    this.openUrl,
  });

  /// True when a firmware is already installed: only the title changes, the
  /// procedure is the same before a reinstallation.
  final bool reinstall;

  /// Opens the verified official repository page; defaults to url_launcher.
  final Future<bool> Function(Uri uri)? openUrl;

  @override
  State<Rpcs3FirmwarePreflightDialog> createState() =>
      _Rpcs3FirmwarePreflightDialogState();
}

class _Rpcs3FirmwarePreflightDialogState
    extends State<Rpcs3FirmwarePreflightDialog> {
  bool _openFailed = false;

  Future<void> _openPage() async {
    final uri = Uri.parse(Rpcs3FirmwareLocale.getMoreRamUrl);
    var opened = false;
    try {
      opened = await (widget.openUrl ??
          (Uri target) => launchUrl(target, mode: LaunchMode.externalApplication))(uri);
    } catch (_) {
      opened = false;
    }
    if (mounted) setState(() => _openFailed = !opened);
  }

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3FirmwareLocale.text(context, key);
    final theme = Theme.of(context);
    final steps = <String>[
      t('preflightStep1'),
      t('preflightStep2'),
      t('preflightStep3'),
      t('preflightStep4'),
      t('preflightStep5'),
    ];
    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_firmware_preflight',
      autofocus: false,
      onBack: () => Navigator.of(context).pop(false),
      child: AlertDialog(
        key: const ValueKey('rpcs3-firmware-preflight-dialog'),
        title: Text(
          t(widget.reinstall
              ? 'preflightTitleReinstall'
              : 'preflightTitleInstall'),
        ),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  t('preflightLead'),
                  key: const ValueKey('rpcs3-firmware-preflight-lead'),
                  style: theme.textTheme.bodyLarge?.copyWith(
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 12),
                Text(t('preflightWhy')),
                const SizedBox(height: 12),
                Text(
                  t('preflightStepsTitle'),
                  style: theme.textTheme.titleSmall,
                ),
                const SizedBox(height: 6),
                for (var index = 0; index < steps.length; index++)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        SizedBox(
                          width: 22,
                          child: Text(
                            '${index + 1}.',
                            style: theme.textTheme.bodyMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ),
                        Expanded(child: Text(steps[index])),
                      ],
                    ),
                  ),
                const SizedBox(height: 8),
                Text(t('preflightDistinction')),
                const SizedBox(height: 8),
                Text(
                  t('preflightNoCheck'),
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontStyle: FontStyle.italic,
                  ),
                ),
                const SizedBox(height: 8),
                // The address is a technical identifier: shown raw, never translated.
                SelectableText(
                  Rpcs3FirmwareLocale.getMoreRamUrl,
                  style: theme.textTheme.bodySmall?.copyWith(
                    fontFamily: 'monospace',
                  ),
                ),
                LibraryFocusRing(
                  radius: 8,
                  child: TextButton.icon(
                    key: const ValueKey('rpcs3-firmware-preflight-open'),
                    onPressed: _openPage,
                    icon: const Icon(Icons.open_in_new, size: 18),
                    label: Text(t('preflightOpenPage')),
                  ),
                ),
                if (_openFailed)
                  Text(
                    Rpcs3FirmwareLocale.formatContext(
                      context,
                      'preflightOpenPageFailed',
                      {'url': Rpcs3FirmwareLocale.getMoreRamUrl},
                    ),
                    key: const ValueKey('rpcs3-firmware-preflight-open-failed'),
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.error,
                    ),
                  ),
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: TextButton(
              key: const ValueKey('rpcs3-firmware-preflight-back'),
              autofocus: true,
              onPressed: () => Navigator.of(context).pop(false),
              child: Text(t('preflightBack')),
            ),
          ),
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-firmware-preflight-continue'),
              onPressed: () => Navigator.of(context).pop(true),
              child: Text(t('preflightContinue')),
            ),
          ),
        ],
      ),
    );
  }
}
