import 'dart:io';

import 'package:armsx2_internal_bridge/armsx2_internal_bridge.dart';
import 'package:flutter/material.dart';
import 'package:neostation/l10n/armsx2_ui_locale.dart';
import 'package:neostation/l10n/launch_prerequisite_locale.dart';
import 'package:neostation/l10n/pairing_file_locale.dart';
import 'package:neostation/main.dart' show rootNavigatorKey;
import 'package:neostation/services/armsx2_bios_service.dart';
import 'package:neostation/widgets/armsx2_bios_picker.dart';
import 'package:neostation/services/armsx2_folder_service.dart';
import 'package:neostation/services/armsx2_internal_service.dart';
import 'package:neostation/services/config_service.dart';
import 'package:neostation/services/diagnostics_directory.dart';
import 'package:neostation/services/launch_prerequisites.dart';
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/pairing_file_service.dart';
import 'package:path/path.dart' as path;
import 'package:stikjit_bridge/stikjit_bridge.dart';
import 'retro_achievements_session_service.dart';

/// Native ARMSX2 launch transaction.
///
/// This path targets NeoStation's own PID. It never launches an ARMSX2 app,
/// Shortcut, custom URL, or VPN. LocalDevVPN is only probed as the existing
/// RemotePairing transport and is never toggled here.
class StikJitArmsx2Service {
  StikJitArmsx2Service._();

  static final _log = LoggerService.instance;
  static String? _lastError;
  static bool _busy = false;
  static int _transactionSeed = 0;

  static String? get lastError => _lastError;

  /// The `LaunchPrerequisiteLocale` key of what the user has to put right
  /// when the last launch stopped for a known reason (no BIOS, LocalDevVPN
  /// off, no pairing file, …); null when it ran or failed for another one.
  static String? _lastErrorKey;
  static String? get lastErrorKey => _lastErrorKey;

  /// The sentence of [lastErrorKey] in [language], or null. The technical
  /// text stays in [lastError] for the details and the journal.
  static String? lastErrorText(String language) {
    final key = _lastErrorKey;
    if (key == null) return null;
    return LaunchPrerequisiteLocale.textFor(language, key, {
      'action': Armsx2UiLocale.textFor(language, 'importBios'),
    });
  }

  /// Forgets the outcome of an earlier launch.
  static void resetLastError() {
    _lastError = null;
    _lastErrorKey = null;
  }

  static Future<bool> launch({
    required String gamePath,
    String uiLocale = 'en',
  }) =>
      _launchTransaction(gamePath: gamePath, bootBios: false, uiLocale: uiLocale);

  static Future<bool> launchBios({String uiLocale = 'en'}) =>
      _launchTransaction(gamePath: '', bootBios: true, uiLocale: uiLocale);

  static Future<bool> _launchTransaction({
    required String gamePath,
    required bool bootBios,
    required String uiLocale,
  }) async {
    if (!Platform.isIOS || _busy) {
      _lastError = _busy ? 'An ARMSX2 launch is already active.' : null;
      _lastErrorKey = _busy ? LaunchPrerequisite.jitBusy.key : null;
      return false;
    }
    final normalized = bootBios ? '' : path.normalize(gamePath.trim());
    if (!bootBios &&
        (!path.isAbsolute(normalized) || !await File(normalized).exists())) {
      _lastError = 'The selected PS2 game is not readable.';
      _lastErrorKey = 'gameUnreadable';
      return false;
    }

    _busy = true;
    _lastError = null;
    _lastErrorKey = null;
    final transaction =
        (DateTime.now().microsecondsSinceEpoch << 8) | ((_transactionSeed++) & 0xff);

    var nativeTransactionStarted = false;
    Map<String, Object?> raLaunch = const {};
    try {
      await _writeDiagnostic(
        'STATE: START\nTransaction: $transaction\n'
        'Mode: ${bootBios ? 'bios' : 'game'}\nGame: $normalized\n',
      );

      await Armsx2InternalService.ensureLayout();
      final biosStore = await Armsx2BiosStore.open();
      var biosFilename = await biosStore.resolve();
      if (biosFilename == null) {
        final context = rootNavigatorKey.currentContext;
        // No BIOS at all is not the same as a choice the user closed: the
        // first one needs an import, and says where it is done.
        final noBios = (await biosStore.list()).isEmpty;
        if (context == null || !context.mounted) {
          _lastError = 'Choose a PS2 BIOS from the PS2 library first.';
          _lastErrorKey = noBios ? 'ps2BiosMissing' : 'ps2BiosCancelled';
          return false;
        }
        biosFilename = await showArmsx2BiosPicker(context);
        if (biosFilename == null) {
          _lastError = noBios
              ? 'No PS2 BIOS is installed.'
              : 'PS2 BIOS selection was cancelled.';
          _lastErrorKey = noBios ? 'ps2BiosMissing' : 'ps2BiosCancelled';
          return false;
        }
      }
      // Do not attach the debugger until the explicit selected file is readable.
      await biosStore.validate(biosFilename);
      await _appendDiagnostic('BIOS: $biosFilename\n');

      final pairingFile = await _ensurePairingFile();
      if (pairingFile == null) {
        _lastError = 'Pairing file selection was cancelled.';
        _lastErrorKey = LaunchPrerequisite.pairingFile.key;
        return false;
      }

      // Embedded ARMSX2 owns a Files-visible NeoStation/Documents root.
      // Games, BIOS and live saves all remain inside this canonical layout.
      final root = await Armsx2InternalService.rootDirectory();
      final games = await Armsx2InternalService.gamesDirectory();
      final bios = await Armsx2InternalService.biosDirectory();
      ConfigService.linkedArmsx2FolderPath = root.path;
      ConfigService.linkedArmsx2GameFolderPath = games.path;
      if (!bootBios &&
          !Armsx2FolderService.ownsRomPath(normalized, games.path)) {
        _lastError = 'The selected PS2 game is outside NeoStation/ARMSX2/Games.';
        _lastErrorKey = 'ps2GameOutside';
        return false;
      }

      final biosDirectory = bios.path;
      final dataPath = root.path;

      // TCP reachability is a proof only. It has no side effect on either VPN.
      final route = await StikjitBridge.probeLocalDevVpnRoute();
      await _appendDiagnostic(
        'STATE: ROUTE_READY\n'
        'Route: ${route.host}:${route.port}\n'
        'ElapsedMs: ${route.elapsedMs}\n',
      );

      nativeTransactionStarted = true;
      final jit = await Armsx2InternalBridge.prepareJit(
        pairingFilePath: pairingFile.path,
      );
      final jitLogs = jit['logs'];
      if (jitLogs is List && jitLogs.isNotEmpty) {
        await _appendDiagnostic(
          'JIT preparation detail:\n${jitLogs.join('\n')}\n',
        );
      }
      if (jit['success'] != true ||
          jit['helperConnected'] != true ||
          jit['pidAttached'] != true ||
          jit['debugged'] != true) {
        throw StateError(
          jit['message']?.toString() ?? 'ARMSX2 JIT attachment failed.',
        );
      }
      await _appendDiagnostic(
        'STATE: JIT_ATTACHED\n'
        'PID: ${jit['pid']}\n'
        'Message: ${jit['message']}\n',
      );

      raLaunch = await RetroAchievementsSessionService.shared.prepareLaunch(
        engine: 'armsx2', system: 'ps2', language: uiLocale, systemMenu: bootBios,
        contentPath: bootBios ? null : gamePath);
      final launch = await Armsx2InternalBridge.launch(
        transaction: transaction,
        gamePath: normalized,
        bootBios: bootBios,
        uiLocale: uiLocale,
        biosFilename: biosFilename,
        dataPath: dataPath,
        biosDirectory: biosDirectory,
        raSessionId: raLaunch['raSessionId'] as String?,
      );
      if (launch['success'] != true) {
        throw StateError(
          launch['message']?.toString() ?? 'ARMSX2 boot failed.',
        );
      }

      await _appendDiagnostic(
        'STATE: RUNNING\n'
        'BootKind: ${launch['bootKind']}\n'
        'Source: ${launch['sourceRevision']}\n',
      );
      _log.i(
        'ARMSX2 embedded Core running transaction=$transaction '
        'mode=${bootBios ? 'bios' : 'game'} game=$normalized.',
      );
      return true;
    } catch (error, stackTrace) {
      await RetroAchievementsSessionService.shared.finishLaunch(raLaunch);
      _lastError = error.toString();
      // LocalDevVPN off, pairing file refused, installation without JIT…:
      // the display names it; anything else keeps the technical text only.
      _lastErrorKey = LaunchPrerequisites.classify(error)?.key;
      _log.e(
        'Embedded ARMSX2 launch failed: $error',
        error: error,
        stackTrace: stackTrace,
      );
      if (nativeTransactionStarted) {
        try {
          await Armsx2InternalBridge.stop();
        } catch (_) {}
      }
      await _appendDiagnostic(
        'STATE: ERROR\nError: $error\nStack: $stackTrace\n',
      );
      return false;
    } finally {
      _busy = false;
    }
  }

  static Future<File?> _ensurePairingFile() async {
    if (await PairingFileService.hasStoredPairingFile()) {
      return PairingFileService.storedFile();
    }

    final context = rootNavigatorKey.currentContext;
    if (context != null && context.mounted) {
      final accepted = await showDialog<bool>(
        context: context,
        barrierDismissible: false,
        builder: (dialogContext) => AlertDialog(
          title: Text(
            PairingFileLocale.get(dialogContext, PairingFileLocale.setupTitle),
          ),
          content: Text(
            PairingFileLocale.get(dialogContext, PairingFileLocale.setupBody),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: Text(
                PairingFileLocale.get(dialogContext, PairingFileLocale.later),
              ),
            ),
            FilledButton.icon(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              icon: const Icon(Icons.folder_open),
              label: Text(
                PairingFileLocale.get(
                  dialogContext,
                  PairingFileLocale.chooseFile,
                ),
              ),
            ),
          ],
        ),
      );
      if (accepted != true) return null;
    }

    final dialogTitle = context != null && context.mounted
        ? PairingFileLocale.get(context, PairingFileLocale.pickerTitle)
        : 'Select your pairing file';
    final imported = await PairingFileService.importFromPicker(
      dialogTitle: dialogTitle,
    );
    return imported?.file;
  }

  static Future<File> _diagnosticFile() async {
    return DiagnosticsDirectory.file('armsx2_internal_debug.txt');
  }

  static Future<void> _writeDiagnostic(String content) async {
    try {
      await (await _diagnosticFile()).writeAsString(content, flush: true);
    } catch (_) {}
  }

  static Future<void> _appendDiagnostic(String content) async {
    try {
      await (await _diagnosticFile()).writeAsString(
        content,
        mode: FileMode.append,
        flush: true,
      );
    } catch (_) {}
  }
}
