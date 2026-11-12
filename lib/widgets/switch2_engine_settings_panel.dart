import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/switch2_settings_locale.dart';
import '../services/s2arm_internal_service.dart';

typedef S2ArmSettingsLoader = Future<S2ArmSettings?> Function();
typedef S2ArmSettingsSaver = Future<S2ArmSettings?> Function(S2ArmSettings settings);

/// Switch 2 engine settings (Settings > Systems > Switch 2 > Emulators and the playlist menu): resolution, anti-aliasing,
/// scaling filter, frame rate limit, console mode, image format, performance overlay and game language. The native
/// host stores them; they apply at the next game start, after RewindBox is restarted (one game per app launch).
class Switch2EngineSettingsPanel extends StatefulWidget {
  const Switch2EngineSettingsPanel({super.key, this.load, this.save});

  /// Test seams; production uses S2ArmInternalService.
  final S2ArmSettingsLoader? load;
  final S2ArmSettingsSaver? save;

  @override
  State<Switch2EngineSettingsPanel> createState() => _Switch2EngineSettingsPanelState();
}

class _Switch2EngineSettingsPanelState extends State<Switch2EngineSettingsPanel> {
  S2ArmSettings? _settings;
  bool _loaded = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    S2ArmSettings? settings;
    try {
      settings = await (widget.load ?? S2ArmInternalService.loadSettings)();
    } catch (_) {
      settings = null;
    }
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _loaded = true;
    });
  }

  Future<void> _change(S2ArmSettings next) async {
    final current = _settings;
    if (current == null || _busy) return;
    setState(() {
      _settings = next;
      _busy = true;
    });
    S2ArmSettings? stored;
    try {
      stored = await (widget.save ?? S2ArmInternalService.saveSettings)(next);
    } catch (_) {
      stored = null;
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _settings = stored ?? current;
    });
  }

  String _t(String key) => Switch2SettingsLocale.text(context, key);

  static const Map<String, String> _resolutionKeys = <String, String>{'0.5': 'res050', '0.75': 'res075', '1': 'res100'};
  static const Map<String, String> _aaKeys = <String, String>{
    'None': 'aaNone',
    'SmaaMedium': 'aaSmaaMedium',
    'SmaaHigh': 'aaSmaaHigh',
  };
  static const Map<String, String> _filterKeys = <String, String>{'Bilinear': 'filterBilinear', 'Nearest': 'filterNearest'};
  static const Map<String, String> _fpsKeys = <String, String>{
    '30': 'fps30',
    '60': 'fps60',
    '120': 'fps120',
    '0': 'fpsUnlimited',
  };

  Widget _dropdown({
    required Key key,
    required String title,
    required String value,
    required Map<String, String> labels,
    required ValueChanged<String> onChanged,
  }) {
    return ListTile(
      title: Text(title),
      trailing: ConstrainedBox(
        constraints: BoxConstraints(maxWidth: 190.r),
        child: DropdownButton<String>(
          key: key,
          value: labels.containsKey(value) ? value : null,
          isDense: true,
          isExpanded: true,
          items: [
            for (final entry in labels.entries)
              DropdownMenuItem<String>(value: entry.key, child: Text(entry.value, overflow: TextOverflow.ellipsis)),
          ],
          onChanged: _busy
              ? null
              : (selected) {
                  if (selected != null && selected != value) onChanged(selected);
                },
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (!_loaded) return const SizedBox.shrink();
    final settings = _settings;
    final theme = Theme.of(context);
    if (settings == null) {
      return Padding(
        padding: EdgeInsets.all(16.r),
        child: Text(_t('unavailable'), style: theme.textTheme.bodyMedium),
      );
    }
    final languages = <String, String>{
      'auto': _t('languageAuto'),
      for (final name in S2ArmSettings.gameLanguages) name: Switch2SettingsLocale.languageNames[name] ?? name,
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(16.r, 8.r, 16.r, 4.r),
          child: Text(_t('graphicsSection'), style: theme.textTheme.titleSmall?.copyWith(color: theme.colorScheme.primary)),
        ),
        _dropdown(
          key: const ValueKey('s2arm-setting-resolution'),
          title: _t('resolution'),
          value: settings.resolutionScale,
          labels: {for (final entry in _resolutionKeys.entries) entry.key: _t(entry.value)},
          onChanged: (value) => _change(settings.copyWith(resolutionScale: value)),
        ),
        _dropdown(
          key: const ValueKey('s2arm-setting-anti-aliasing'),
          title: _t('antiAliasing'),
          value: settings.antiAliasing,
          labels: {for (final entry in _aaKeys.entries) entry.key: _t(entry.value)},
          onChanged: (value) => _change(settings.copyWith(antiAliasing: value)),
        ),
        _dropdown(
          key: const ValueKey('s2arm-setting-scaling-filter'),
          title: _t('scalingFilter'),
          value: settings.scalingFilter,
          labels: {for (final entry in _filterKeys.entries) entry.key: _t(entry.value)},
          onChanged: (value) => _change(settings.copyWith(scalingFilter: value)),
        ),
        _dropdown(
          key: const ValueKey('s2arm-setting-frame-rate'),
          title: _t('frameRateLimit'),
          value: settings.frameRateLimit,
          labels: {for (final entry in _fpsKeys.entries) entry.key: _t(entry.value)},
          onChanged: (value) => _change(settings.copyWith(frameRateLimit: value)),
        ),
        _dropdown(
          key: const ValueKey('s2arm-setting-mode'),
          title: _t('mode'),
          value: settings.docked ? 'docked' : 'handheld',
          labels: {'handheld': _t('modeHandheld'), 'docked': _t('modeDocked')},
          onChanged: (value) => _change(settings.copyWith(docked: value == 'docked')),
        ),
        _dropdown(
          key: const ValueKey('s2arm-setting-image-format'),
          title: _t('imageFormat'),
          value: settings.widescreen ? 'wide' : '16:9',
          labels: {'wide': _t('formatWide'), '16:9': _t('format169')},
          onChanged: (value) => _change(settings.copyWith(widescreen: value == 'wide')),
        ),
        SwitchListTile.adaptive(
          key: const ValueKey('s2arm-setting-performance-overlay'),
          value: settings.performanceOverlay,
          title: Text(_t('performanceOverlay')),
          onChanged: _busy ? null : (value) => _change(settings.copyWith(performanceOverlay: value)),
        ),
        _dropdown(
          key: const ValueKey('s2arm-setting-game-language'),
          title: _t('gameLanguage'),
          value: settings.gameLanguage,
          labels: languages,
          onChanged: (value) => _change(settings.copyWith(gameLanguage: value)),
        ),
        Padding(
          padding: EdgeInsets.fromLTRB(16.r, 8.r, 16.r, 4.r),
          child: Text(_t('nextLaunchNote'), style: theme.textTheme.bodySmall),
        ),
        Padding(
          padding: EdgeInsets.fromLTRB(16.r, 4.r, 16.r, 12.r),
          child: Text(_t('inGameMenuNote'), style: theme.textTheme.bodySmall),
        ),
      ],
    );
  }
}
