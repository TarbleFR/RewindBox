import 'dart:async';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as path;
import 'package:rpcs3_internal_bridge/rpcs3_internal_bridge.dart';
import 'package:wakelock_plus/wakelock_plus.dart';

import '../l10n/rpcs3_library_file_locale.dart';
import '../services/logger_service.dart';
import '../services/rpcs3_library_file_service.dart';
import '../services/rpcs3_save_exchange_service.dart';
import 'library_focus_gamepad_layer.dart';

/// Build 554: makes a library-folder PS3 disc image ([romPath]) launchable
/// before the launcher boots it. A disc RPCS3 already holds is linked
/// without a question; otherwise the user is asked, then RPCS3 installs it
/// while a progress dialog is shown. Returns null when the user declines.
Future<Rpcs3LibraryFileOutcome?> prepareRpcs3LibraryFileForLaunch(
  BuildContext context,
  String romPath,
) async {
  final resolved = await Rpcs3LibraryFileService.resolve(romPath);
  final plan = resolved.plan;
  if (plan == null) return resolved;
  if (!context.mounted) return null;
  final choice = await showRpcs3LibraryFileInstallPrompt(context, plan);
  if (choice == Rpcs3LibraryFileInstallChoice.cancel) {
    LoggerService.instance.i(
      'RPCS3 library file: installation of ${plan.fileName} declined.',
    );
    return null;
  }
  if (!context.mounted) return null;
  return runWithRpcs3LibraryFileProgress(
    context,
    plan,
    () => Rpcs3LibraryFileService.install(
      plan,
      removeOriginal:
          choice == Rpcs3LibraryFileInstallChoice.installAndFreeSpace,
    ),
  );
}

/// The answer to [Rpcs3LibraryFileInstallPrompt].
enum Rpcs3LibraryFileInstallChoice {
  cancel,
  install,

  /// Build 557: install, then delete the original file and its disc key
  /// (RPCS3 keeps its own copy of both).
  installAndFreeSpace,
}

/// Asks before RPCS3 copies [plan]'s disc into its library.
Future<Rpcs3LibraryFileInstallChoice> showRpcs3LibraryFileInstallPrompt(
  BuildContext context,
  Rpcs3LibraryFilePlan plan,
) async {
  final choice = await showDialog<Rpcs3LibraryFileInstallChoice>(
    context: context,
    useRootNavigator: true,
    barrierDismissible: false,
    builder: (_) => Rpcs3LibraryFileInstallPrompt(plan: plan),
  );
  return choice ?? Rpcs3LibraryFileInstallChoice.cancel;
}

/// Shows the installation progress of [plan] above the launch screen while
/// [task] runs; the dialog cannot be dismissed (RPCS3's import cannot be
/// interrupted) and closes when [task] ends, successful or not. The screen
/// stays on meanwhile: a locked iPhone suspends the copy.
Future<T> runWithRpcs3LibraryFileProgress<T>(
  BuildContext context,
  Rpcs3LibraryFilePlan plan,
  Future<T> Function() task, {
  Stream<Rpcs3InstallProgress>? progress,
  Future<Future<void> Function()> Function()? keepScreenOn,
}) async {
  final route = DialogRoute<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => Rpcs3LibraryFileProgressDialog(
      fileName: plan.fileName,
      progress: progress,
    ),
  );
  unawaited(Navigator.of(context, rootNavigator: true).push(route));
  final releaseScreen = await (keepScreenOn ?? _keepScreenOn)();
  try {
    return await task();
  } finally {
    await releaseScreen();
    if (route.isActive) route.navigator?.removeRoute(route);
  }
}

/// Holds the screen on unless something else already does (a scraping
/// session, the reader); returns what gives it back.
Future<Future<void> Function()> _keepScreenOn() async {
  try {
    if (await WakelockPlus.enabled) return () async {};
    await WakelockPlus.enable();
    return () async {
      try {
        await WakelockPlus.disable();
      } catch (_) {}
    };
  } catch (_) {
    return () async {};
  }
}

class Rpcs3LibraryFileInstallPrompt extends StatefulWidget {
  const Rpcs3LibraryFileInstallPrompt({super.key, required this.plan});

  final Rpcs3LibraryFilePlan plan;

  @override
  State<Rpcs3LibraryFileInstallPrompt> createState() =>
      _Rpcs3LibraryFileInstallPromptState();
}

class _Rpcs3LibraryFileInstallPromptState
    extends State<Rpcs3LibraryFileInstallPrompt> {
  /// Build 557: off by default; the original is the user's file.
  bool _freeSpace = false;

  void _close(Rpcs3LibraryFileInstallChoice choice) =>
      Navigator.of(context).pop(choice);

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3LibraryFileLocale.text(context, key);
    final theme = Theme.of(context);
    final plan = widget.plan;
    final identity = plan.identity;
    final keyPath = plan.keyPath;
    final size = Rpcs3SaveExchangeService.formatBytes(plan.sizeBytes);
    return LibraryFocusGamepadLayer(
      debugLabel: 'rpcs3_library_file_prompt',
      autofocus: false,
      onBack: () => _close(Rpcs3LibraryFileInstallChoice.cancel),
      child: AlertDialog(
        key: const ValueKey('rpcs3-library-file-prompt'),
        title: Text(t('promptTitle')),
        content: SizedBox(
          width: 520,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  Rpcs3LibraryFileLocale.formatContext(context, 'promptBody', {
                    'file': plan.fileName,
                    'size': size,
                  }),
                ),
                if (identity != null) ...[
                  const SizedBox(height: 10),
                  // The disc's own title and serial: data, never translated.
                  Text(
                    '${identity.title} · ${identity.titleId}',
                    key: const ValueKey('rpcs3-library-file-identity'),
                    style: theme.textTheme.bodySmall,
                  ),
                ],
                if (keyPath != null) ...[
                  const SizedBox(height: 10),
                  Text(
                    Rpcs3LibraryFileLocale.formatContext(context, 'promptKey', {
                      'key': path.basename(keyPath),
                    }),
                    key: const ValueKey('rpcs3-library-file-key'),
                    style: theme.textTheme.bodySmall,
                  ),
                ],
                const SizedBox(height: 8),
                LibraryFocusRing(
                  child: CheckboxListTile(
                    key: const ValueKey('rpcs3-library-file-free-space'),
                    value: _freeSpace,
                    onChanged: (value) =>
                        setState(() => _freeSpace = value ?? false),
                    controlAffinity: ListTileControlAffinity.leading,
                    contentPadding: EdgeInsets.zero,
                    dense: true,
                    title: Text(
                      Rpcs3LibraryFileLocale.formatContext(
                        context,
                        keyPath == null
                            ? 'promptFreeSpace'
                            : 'promptFreeSpaceKey',
                        {'size': size},
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
        actions: [
          LibraryFocusRing(
            child: TextButton(
              key: const ValueKey('rpcs3-library-file-cancel'),
              onPressed: () => _close(Rpcs3LibraryFileInstallChoice.cancel),
              child: Text(t('promptCancel')),
            ),
          ),
          LibraryFocusRing(
            child: FilledButton(
              key: const ValueKey('rpcs3-library-file-install'),
              autofocus: true,
              onPressed: () => _close(
                _freeSpace
                    ? Rpcs3LibraryFileInstallChoice.installAndFreeSpace
                    : Rpcs3LibraryFileInstallChoice.install,
              ),
              child: Text(t('promptInstall')),
            ),
          ),
        ],
      ),
    );
  }
}

class Rpcs3LibraryFileProgressDialog extends StatefulWidget {
  const Rpcs3LibraryFileProgressDialog({
    super.key,
    required this.fileName,
    this.progress,
  });

  final String fileName;

  /// RPCS3's import progress; defaults to the bridge's stream.
  final Stream<Rpcs3InstallProgress>? progress;

  @override
  State<Rpcs3LibraryFileProgressDialog> createState() =>
      _Rpcs3LibraryFileProgressDialogState();
}

class _Rpcs3LibraryFileProgressDialogState
    extends State<Rpcs3LibraryFileProgressDialog> {
  StreamSubscription<Rpcs3InstallProgress>? _subscription;
  Rpcs3InstallProgress? _latest;

  @override
  void initState() {
    super.initState();
    _subscription = (widget.progress ?? Rpcs3InternalBridge.installProgress)
        .listen((event) {
          if (mounted) setState(() => _latest = event);
        });
  }

  @override
  void dispose() {
    _subscription?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    String t(String key) => Rpcs3LibraryFileLocale.text(context, key);
    final theme = Theme.of(context);
    final latest = _latest;
    final fraction = latest == null || latest.total <= 0
        ? null
        : (latest.current / latest.total).clamp(0.0, 1.0).toDouble();
    final detail = latest?.detail.trim() ?? '';
    return PopScope(
      canPop: false,
      child: LibraryFocusGamepadLayer(
        debugLabel: 'rpcs3_library_file_progress',
        autofocus: false,
        // Nothing to go back to: RPCS3's import cannot be interrupted.
        onBack: () {},
        child: AlertDialog(
          key: const ValueKey('rpcs3-library-file-progress'),
          title: Text(t('progressTitle')),
          content: SizedBox(
            width: 480,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(
                  widget.fileName,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleSmall,
                ),
                const SizedBox(height: 14),
                LinearProgressIndicator(value: fraction),
                const SizedBox(height: 8),
                Text(
                  fraction == null
                      ? t('progressPreparing')
                      : '${(fraction * 100).round()} %',
                  key: const ValueKey('rpcs3-library-file-progress-value'),
                  textAlign: TextAlign.center,
                ),
                if (detail.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  // RPCS3's own stage label: technical, shown as it comes.
                  Text(
                    detail,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodySmall,
                  ),
                ],
                const SizedBox(height: 12),
                Text(
                  t('progressKeepOpen'),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
