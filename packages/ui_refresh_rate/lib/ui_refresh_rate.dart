import 'package:flutter/services.dart';

/// Native state of the "120 Hz interface" option (iOS, Build 440).
///
/// Field names follow the `neostation/ui_refresh_rate` channel contract
/// (`UiRefreshRatePlugin.m`).
class UiRefreshRateState {
  const UiRefreshRateState({
    required this.hookStatus,
    required this.storedEnabled,
    required this.activeEnabled,
    required this.screenMaxHz,
    required this.engineTargetHz,
    required this.cappedHz,
    required this.lowPowerMode,
    required this.thermalState,
  });

  factory UiRefreshRateState.fromMap(Map<Object?, Object?> map) =>
      UiRefreshRateState(
        hookStatus: map['hookStatus'] as String? ?? hookNotInstalled,
        storedEnabled: map['storedEnabled'] as bool? ?? true,
        activeEnabled: map['activeEnabled'] as bool? ?? true,
        screenMaxHz: (map['screenMaxHz'] as num?)?.toInt() ?? 0,
        engineTargetHz: (map['engineTargetHz'] as num?)?.toDouble() ?? 0,
        cappedHz: (map['cappedHz'] as num?)?.toDouble() ?? 60,
        lowPowerMode: map['lowPowerMode'] as bool? ?? false,
        thermalState: (map['thermalState'] as num?)?.toInt() ?? 0,
      );

  /// State reported when the native side cannot answer: the plugin is not
  /// part of the app ([hookPluginMissing]) or the channel failed (the raw
  /// error code). Never available.
  factory UiRefreshRateState.unreachable([String status = hookPluginMissing]) =>
      UiRefreshRateState(
        hookStatus: status,
        storedEnabled: true,
        activeEnabled: true,
        screenMaxHz: 0,
        engineTargetHz: 0,
        cappedHz: 60,
        lowPowerMode: false,
        thermalState: 0,
      );

  static const String hookInstalledStatus = 'installed';
  static const String hookNotInstalled = 'notInstalled';
  static const String hookPluginMissing = 'pluginMissing';

  /// Raw technical status of the engine hook: installed, notInstalled,
  /// classMissing, methodMissing, signatureMismatch or pluginMissing.
  final String hookStatus;

  /// Preference stored for the next launch.
  final bool storedEnabled;

  /// Preference applied to the running process (read once at launch).
  final bool activeEnabled;

  /// `UIScreen.maximumFramesPerSecond`, never capped by the option.
  final int screenMaxHz;

  /// Rate the Flutter engine currently receives (through the hook).
  final double engineTargetHz;

  /// Cap applied while the option is off.
  final double cappedHz;

  final bool lowPowerMode;

  /// `NSProcessInfo.thermalState`: 0 nominal, 1 fair, 2 serious, 3 critical.
  final int thermalState;

  bool get hookInstalled => hookStatus == hookInstalledStatus;

  /// The screen is known to go above 60 Hz.
  bool get screenSupportsHighRate => screenMaxHz > 60;

  /// Low Power Mode can make iOS report 60 Hz for a ProMotion screen, so
  /// the screen cannot be judged while it is on.
  bool get screenCapabilityUnknown => !screenSupportsHighRate && lowPowerMode;

  /// The option can act on this device.
  bool get available =>
      hookInstalled && (screenSupportsHighRate || screenCapabilityUnknown);

  /// The stored choice differs from the one the running engine uses.
  bool get restartRequired => storedEnabled != activeEnabled;

  bool get thermalLimited => thermalState >= 2;

  /// iOS itself limits the display rate right now.
  bool get systemLimited => lowPowerMode || thermalLimited;
}

/// Method channel wrapper (`neostation/ui_refresh_rate`).
class UiRefreshRateChannel {
  const UiRefreshRateChannel();

  static const MethodChannel channel = MethodChannel(
    'neostation/ui_refresh_rate',
  );

  /// Current state. A missing plugin reports
  /// [UiRefreshRateState.hookPluginMissing]; other platform errors propagate.
  Future<UiRefreshRateState> getState() async {
    try {
      final map = await channel.invokeMapMethod<Object?, Object?>('getState');
      return UiRefreshRateState.fromMap(map ?? const <Object?, Object?>{});
    } on MissingPluginException {
      return UiRefreshRateState.unreachable();
    }
  }

  /// Stores the preference for the next launch and returns the new state.
  /// Throws [PlatformException] `SAVE_FAILED` when iOS did not keep it.
  Future<UiRefreshRateState> setEnabled(bool enabled) async {
    final map = await channel.invokeMapMethod<Object?, Object?>(
      'setEnabled',
      <String, Object?>{'enabled': enabled},
    );
    return UiRefreshRateState.fromMap(map ?? const <Object?, Object?>{});
  }
}
