import 'dart:io';

import 'package:flutter/material.dart';
import 'package:stikjit_bridge/stikjit_bridge.dart';
import 'package:xenia_internal_bridge/xenia_internal_bridge.dart';

import '../l10n/pairing_file_locale.dart';
import '../main.dart' show rootNavigatorKey;
import 'logger_service.dart';
import 'pairing_file_service.dart';

/// How the next XeniOS launch gets JIT (docs/xenios-playlist.md § JIT helper).
enum XeniaJitPlan {
  /// Nothing to do: CS_DEBUGGED is set and the Core needs no attached tool
  /// (its code region is already prepared, or the device has no TXM).
  ready,

  /// The helper prepared for an earlier attempt is still attached with its
  /// handshake live (`handshakeActive`): the launch's nonce probe confirms
  /// it, and it answers the Core's requests.
  reuseAttachedTool,

  /// A debugger is attached but no live helper handshake answers for it
  /// (its transaction was closed): the Core's prepare request would reach a
  /// closed helper, and a new helper cannot attach over it. Refused with
  /// `restartRequired`; nothing is attempted.
  staleTool,

  /// TXM device on iOS 26+, region not prepared: attach the helper with the
  /// universal script for the Core's prepare (x16=1) and detach (x16=0).
  attachForCoreHandshake,

  /// Not debugged and no tool needed afterwards: classic attach, then detach.
  attachClassic,

  /// A tool is needed, but the StikJIT the XeniOS helper would load does not
  /// write full 64-bit addresses (`transportFullWidth` false): the Core's code
  /// region is not kept below 8 GB, so such a tool would prepare the wrong
  /// pages. Refused with `jitToolUnsupported` before any helper attaches
  /// (docs/xenios-playlist.md § Code region).
  toolUnsupported,

  /// A tool is needed, but no address space below 8 GB is held for the code
  /// region its one-time prepare maps (`codeRegionHeld` false): that prepare
  /// would be a XeniOS fatal error that closes RewindBox. Refused with
  /// `jitMemoryUnavailable` before any helper attaches; the next RewindBox
  /// launch reserves the region (docs/xenios-playlist.md § Code region).
  noCodeRegion,
}

class XeniaJitOutcome {
  const XeniaJitOutcome.ok(this.plan) : error = null, detail = null;
  const XeniaJitOutcome.failure(this.error, [this.detail]) : plan = null;

  final XeniaJitPlan? plan;

  /// XeniaLocale key.
  final String? error;
  final String? detail;

  bool get success => error == null;
}

/// The dedicated XeniOS JIT helper transaction, before every launch. The
/// Core decides what it needs (`jitState`); the helper is attached only when
/// required, and only once per process once the Core has prepared its region.
/// RemotePairing over manual LocalDevVPN, as the other embedded engines; no
/// external JIT app, no automatic VPN switching.
abstract final class XeniaJitService {
  static final _log = LoggerService.instance;

  @visibleForTesting
  static Future<Map<String, dynamic>> Function() jitState =
      XeniaInternalBridge.jitState;

  @visibleForTesting
  static Future<File?> Function() pairingFile = _ensurePairingFile;

  @visibleForTesting
  static Future<void> Function() probeRoute = _probeRoute;

  @visibleForTesting
  static Future<Map<String, dynamic>> Function({
    required String pairingFilePath,
    required bool requiresCoreHandshake,
  })
  prepareJit = XeniaInternalBridge.prepareJit;

  @visibleForTesting
  static Future<Map<String, dynamic>> Function() completeJit =
      XeniaInternalBridge.completeJit;

  static Future<void> _probeRoute() async {
    await StikjitBridge.probeLocalDevVpnRoute();
  }

  static XeniaJitPlan planFor(Map<String, dynamic> state) {
    final needsTool = state['needsTool'] == true;
    final attached = state['toolAttached'] == true;
    final debugged = state['debugged'] == true;
    final handshake = state['handshakeActive'] == true;
    if (needsTool) {
      if (state['transportFullWidth'] != true) {
        return XeniaJitPlan.toolUnsupported;
      }
      if (state['codeRegionHeld'] != true) return XeniaJitPlan.noCodeRegion;
      if (!attached) return XeniaJitPlan.attachForCoreHandshake;
      return handshake
          ? XeniaJitPlan.reuseAttachedTool
          : XeniaJitPlan.staleTool;
    }
    return debugged ? XeniaJitPlan.ready : XeniaJitPlan.attachClassic;
  }

  static Future<XeniaJitOutcome> ensure() async {
    final state = await jitState();
    final error = state['error']?.toString();
    if (error != null) {
      return XeniaJitOutcome.failure(error, state['detail']?.toString());
    }
    final plan = planFor(state);
    _log.i('XeniOS JIT: state=$state plan=${plan.name}');
    if (plan == XeniaJitPlan.staleTool) {
      return const XeniaJitOutcome.failure(
        'restartRequired',
        'a debugger is attached without a live XeniOS helper handshake',
      );
    }
    if (plan == XeniaJitPlan.toolUnsupported) {
      return XeniaJitOutcome.failure(
        'jitToolUnsupported',
        state['transportDetail']?.toString(),
      );
    }
    if (plan == XeniaJitPlan.noCodeRegion) {
      return const XeniaJitOutcome.failure(
        'jitMemoryUnavailable',
        'no address space below 8 GB is held for the XeniOS code region',
      );
    }
    if (plan == XeniaJitPlan.ready || plan == XeniaJitPlan.reuseAttachedTool) {
      return XeniaJitOutcome.ok(plan);
    }

    final pairing = await pairingFile();
    if (pairing == null) {
      return const XeniaJitOutcome.failure('pairingRequired');
    }
    try {
      await probeRoute();
    } on Exception catch (error) {
      return XeniaJitOutcome.failure('jitAttachFailed', error.toString());
    }
    final handshake = plan == XeniaJitPlan.attachForCoreHandshake;
    final jit = await prepareJit(
      pairingFilePath: pairing.path,
      requiresCoreHandshake: handshake,
    );
    // Separate facts (docs/PROJECT_RULES.md): helper connected, the expected
    // PID attached and CS_DEBUGGED are each required.
    if (jit['success'] != true ||
        jit['helperConnected'] != true ||
        jit['pidAttached'] != true ||
        jit['debugged'] != true) {
      return XeniaJitOutcome.failure(
        'jitAttachFailed',
        jit['message']?.toString(),
      );
    }
    if (!handshake) {
      final done = await completeJit();
      if (done['success'] != true) {
        return XeniaJitOutcome.failure(
          'jitHelperIncomplete',
          done['message']?.toString(),
        );
      }
    }
    return XeniaJitOutcome.ok(plan);
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
}
