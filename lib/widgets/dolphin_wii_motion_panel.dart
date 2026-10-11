import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/dolphin_import_locale.dart';
import '../l10n/dolphin_shake_locale.dart';
import '../models/dolphin_phone_shake_settings.dart';
import '../services/dolphin_internal_v2_service.dart';

typedef DolphinPhoneShakeLoader = Future<DolphinPhoneShakeSettings?> Function();
typedef DolphinPhoneShakeSaver =
    Future<DolphinPhoneShakeSettings?> Function({
      bool? enabled,
      String? sensitivity,
    });

/// Wii settings (Settings › Systems › Wii › Emulators, Build 442): phone
/// shaking of the first Wii Remote on/off and its sensitivity. The values are
/// the native preferences the in-game Controls menu also edits; a running
/// session applies a change at once. Nothing here touches the Dolphin core.
class DolphinWiiMotionPanel extends StatefulWidget {
  const DolphinWiiMotionPanel({super.key, this.load, this.save});

  /// Test seams; production reads and writes through the Dolphin bridge.
  final DolphinPhoneShakeLoader? load;
  final DolphinPhoneShakeSaver? save;

  static const Key switchKey = ValueKey('dolphin-wii-phone-shake-switch');
  static const Key sensitivityKey = ValueKey('dolphin-wii-shake-sensitivity');

  @override
  State<DolphinWiiMotionPanel> createState() => _DolphinWiiMotionPanelState();
}

class _DolphinWiiMotionPanelState extends State<DolphinWiiMotionPanel> {
  DolphinPhoneShakeSettings? _settings;
  bool _loaded = false;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final loader = widget.load ?? DolphinInternalV2Service.phoneShakeSettings;
    DolphinPhoneShakeSettings? settings;
    try {
      settings = await loader();
    } catch (_) {
      settings = null;
    }
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _loaded = true;
    });
  }

  Future<void> _apply({bool? enabled, String? sensitivity}) async {
    final current = _settings;
    if (current == null || _saving) return;
    final saver = widget.save ?? DolphinInternalV2Service.setPhoneShakeSettings;
    setState(() {
      _saving = true;
      // Optimistic: the native side confirms or restores the stored values.
      _settings = current.copyWith(enabled: enabled, sensitivity: sensitivity);
    });
    DolphinPhoneShakeSettings? stored;
    try {
      stored = await saver(enabled: enabled, sensitivity: sensitivity);
    } catch (_) {
      stored = null;
    }
    if (!mounted) return;
    setState(() {
      _saving = false;
      _settings = stored ?? current;
    });
  }

  String _t(String key) {
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    return DolphinShakeLocale.labels(DolphinImportLocale.localeKey(locale))[key] ??
        key;
  }

  @override
  Widget build(BuildContext context) {
    final settings = _settings;
    if (!_loaded || settings == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(16.r, 8.r, 16.r, 4.r),
          child: Text(
            _t('wiiMotionSection'),
            style: theme.textTheme.titleSmall?.copyWith(
              color: theme.colorScheme.primary,
            ),
          ),
        ),
        SwitchListTile.adaptive(
          key: DolphinWiiMotionPanel.switchKey,
          value: settings.enabled,
          title: Text(_t('phoneShakeToggle')),
          subtitle: Text(_t('phoneShakeToggleHelp')),
          onChanged: _saving ? null : (value) => _apply(enabled: value),
        ),
        ListTile(
          title: Text(_t('shakeSensitivity')),
          subtitle: Padding(
            padding: EdgeInsets.only(top: 8.r),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SegmentedButton<String>(
                  key: DolphinWiiMotionPanel.sensitivityKey,
                  showSelectedIcon: false,
                  segments: [
                    for (final level in DolphinPhoneShakeSettings.sensitivities)
                      ButtonSegment<String>(
                        value: level,
                        label: Text(_t(_labelKey(level))),
                      ),
                  ],
                  selected: <String>{settings.sensitivity},
                  onSelectionChanged: _saving || !settings.enabled
                      ? null
                      : (selection) {
                          if (selection.isEmpty) return;
                          _apply(sensitivity: selection.first);
                        },
                ),
                SizedBox(height: 6.r),
                Text(
                  _t('shakeSensitivityHelp'),
                  style: theme.textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  static String _labelKey(String level) => switch (level) {
    'low' => 'shakeSensitivityLow',
    'high' => 'shakeSensitivityHigh',
    _ => 'shakeSensitivityMedium',
  };
}
