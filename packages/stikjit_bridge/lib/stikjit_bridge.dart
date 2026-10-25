import 'package:flutter/services.dart';

class StikjitBridge {
  StikjitBridge._();

  static const MethodChannel _channel = MethodChannel('neostation/stikjit');
  static Future<LocalDevVpnRouteState> probeLocalDevVpnRoute() async {
    final raw = await _channel.invokeMethod<Object?>('probeLocalDevVpnRoute');
    if (raw is! Map) {
      throw StateError('LocalDevVPN route probe returned an invalid response.');
    }
    final state = LocalDevVpnRouteState.fromMap(Map<String, dynamic>.from(raw));
    if (!state.reachable ||
        state.host != LocalDevVpnRouteState.expectedHost ||
        state.port != LocalDevVpnRouteState.expectedPort) {
      throw PlatformException(
        code: 'localdevvpn_route_unavailable',
        message:
            'LocalDevVPN did not expose RemotePairing at '
            '${LocalDevVpnRouteState.expectedHost}:'
            '${LocalDevVpnRouteState.expectedPort} '
            '(state=${state.state}, elapsedMs=${state.elapsedMs}).',
        details: raw,
      );
    }
    return state;
  }

}

class LocalDevVpnRouteState {
  const LocalDevVpnRouteState({
    required this.reachable,
    required this.host,
    required this.port,
    required this.elapsedMs,
    required this.state,
    required this.networkState,
    this.errorDomain,
    this.errorCode,
    this.errorDescription,
  });

  factory LocalDevVpnRouteState.fromMap(Map<String, dynamic> data) =>
      LocalDevVpnRouteState(
        reachable: data['reachable'] == true,
        host: data['host']?.toString() ?? '',
        port: (data['port'] as num?)?.toInt() ?? 0,
        elapsedMs: (data['elapsedMs'] as num?)?.toInt() ?? 0,
        state: data['state']?.toString() ?? 'unknown',
        networkState: data['networkState']?.toString() ?? 'unknown',
        errorDomain: data['errorDomain']?.toString(),
        errorCode: data['errorCode']?.toString(),
        errorDescription: data['errorDescription']?.toString(),
      );

  static const expectedHost = '10.7.0.1';
  static const expectedPort = 49152;

  final bool reachable;
  final String host;
  final int port;
  final int elapsedMs;
  final String state;
  final String networkState;
  final String? errorDomain;
  final String? errorCode;
  final String? errorDescription;
}
