import 'package:flutter/services.dart' show PlatformException;

import 'local_dev_vpn_route_service.dart';

/// What the user has to put right before an embedded engine that needs JIT
/// (PlayStation 2, PlayStation 3, GameCube/Wii, Switch) can start.
///
/// The four engines share one JIT route (the pairing file of the device and
/// the LocalDevVPN loopback) and their native bridges report its failures
/// with the same English sentences. A launch that failed used to show that
/// English sentence, or only "the operation failed": the user could not
/// tell a VPN that is off from a missing file or from an installation that
/// can never run JIT.
enum LaunchPrerequisite {
  /// LocalDevVPN is not connected: its RemotePairing route does not answer.
  localDevVpn('localDevVpn'),

  /// The pairing file of the device is missing, unreadable or was not chosen.
  pairingFile('pairingFile'),

  /// The installation was signed without `get-task-allow`: no JIT at all.
  developmentSignature('developmentSignature'),

  /// The JIT route needs iOS 17.4 or later.
  iosVersion('iosVersion'),

  /// Another launch is still preparing the JIT.
  jitBusy('jitBusy'),

  /// The JIT helper could not start, or left the process without JIT.
  jitHelper('jitHelper');

  const LaunchPrerequisite(this.key);

  /// The `LaunchPrerequisiteLocale` key of its sentence.
  final String key;
}

abstract final class LaunchPrerequisites {
  /// The prerequisite [error] points to, or null when it names none (the
  /// caller then keeps its own text).
  static LaunchPrerequisite? classify(Object? error) {
    if (error == null) return null;
    if (error is LocalDevVpnRouteException) {
      return error.code == 'unsupported_platform' ? null : LaunchPrerequisite.localDevVpn;
    }
    if (error is PlatformException) {
      if (error.code.startsWith('localdevvpn_route')) return LaunchPrerequisite.localDevVpn;
      return classifyText('${error.code} ${error.message ?? ''}');
    }
    return classifyText('$error');
  }

  /// [classify] for the text of a failure: a native message, a diagnostic
  /// line or an exception printed as text. The phrases are the ones the
  /// native JIT bridges and the route probe write
  /// (test/launch_prerequisites_test.dart reads them in those sources).
  static LaunchPrerequisite? classifyText(String? text) {
    if (text == null) return null;
    final lower = text.toLowerCase();
    if (lower.isEmpty) return null;
    if (lower.contains('get-task-allow')) return LaunchPrerequisite.developmentSignature;
    if (lower.contains('requires ios 17.4')) return LaunchPrerequisite.iosVersion;
    if (lower.contains('localdevvpn')) return LaunchPrerequisite.localDevVpn;
    if (lower.contains('pairing')) return LaunchPrerequisite.pairingFile;
    if (lower.contains('jit operation is already running') || lower.contains('launch is already active')) {
      return LaunchPrerequisite.jitBusy;
    }
    if (lower.contains('jit helper') ||
        lower.contains('stikjit detached') ||
        lower.contains('jit attachment failed') ||
        lower.contains('no longer has jit authorization')) {
      return LaunchPrerequisite.jitHelper;
    }
    return null;
  }
}
