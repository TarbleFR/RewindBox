/// Phone-shake preferences of the embedded Dolphin engine's first Wii Remote
/// (Build 442). The values live in the native user defaults
/// (`NeoStation.Dolphin.PhoneShake.Enabled` and
/// `NeoStation.Dolphin.PhoneShake.Sensitivity`) that the Swift detector reads;
/// Flutter only mirrors them through the bridge's method channel.
class DolphinPhoneShakeSettings {
  const DolphinPhoneShakeSettings({
    required this.enabled,
    required this.sensitivity,
  });

  /// Raw sensitivity values accepted by the native side, in increasing order.
  static const List<String> sensitivities = <String>['low', 'medium', 'high'];
  static const String defaultSensitivity = 'medium';

  final bool enabled;

  /// One of [sensitivities]; unknown native values read as the default.
  final String sensitivity;

  factory DolphinPhoneShakeSettings.fromMap(Map<String, dynamic> map) {
    final raw = map['sensitivity'];
    final sensitivity = raw is String ? raw.trim().toLowerCase() : '';
    return DolphinPhoneShakeSettings(
      enabled: map['enabled'] != false,
      sensitivity: sensitivities.contains(sensitivity)
          ? sensitivity
          : defaultSensitivity,
    );
  }

  DolphinPhoneShakeSettings copyWith({bool? enabled, String? sensitivity}) =>
      DolphinPhoneShakeSettings(
        enabled: enabled ?? this.enabled,
        sensitivity: sensitivity ?? this.sensitivity,
      );

  @override
  bool operator ==(Object other) =>
      other is DolphinPhoneShakeSettings &&
      other.enabled == enabled &&
      other.sensitivity == sensitivity;

  @override
  int get hashCode => Object.hash(enabled, sensitivity);

  @override
  String toString() =>
      'DolphinPhoneShakeSettings(enabled: $enabled, sensitivity: $sensitivity)';
}
