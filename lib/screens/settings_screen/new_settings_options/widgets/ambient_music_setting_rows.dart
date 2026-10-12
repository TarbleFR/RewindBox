import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/ambient_music_locale.dart';
import 'package:neostation/services/home_music_service.dart';

import '../../../../widgets/custom_toggle_switch.dart';
import 'setting_row.dart';
import 'setting_value_chip.dart';

/// Settings › General › ambient music (Build 448), after "Sound effects":
///
/// 1. [AmbientMusicEnabledRow] — the switch, and the track playing;
/// 2. [AmbientMusicVolumeRow] — the music's own volume (slider for touch,
///    the A button steps it by 10 %).
///
/// Both read and write the single [HomeMusicService]; the values are kept in
/// SharedPreferences by the service.
abstract class _AmbientMusicRow extends StatefulWidget {
  const _AmbientMusicRow({super.key, required this.focused, this.service});

  final bool focused;

  /// Tests inject their own service; the app uses the singleton.
  final HomeMusicService? service;
}

abstract class _AmbientMusicRowState<T extends _AmbientMusicRow>
    extends State<T> {
  HomeMusicService get service => widget.service ?? HomeMusicService();

  @override
  void initState() {
    super.initState();
    service.addListener(_changed);
    unawaited(service.init().then((_) => _changed()));
  }

  @override
  void didUpdateWidget(covariant T oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = oldWidget.service ?? HomeMusicService();
    if (!identical(previous, service)) {
      previous.removeListener(_changed);
      service.addListener(_changed);
    }
  }

  @override
  void dispose() {
    service.removeListener(_changed);
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  String text(String key) => AmbientMusicLocale.text(context, key);

  TextStyle? get muted => Theme.of(context).textTheme.bodyMedium?.copyWith(
    fontSize: 9.r,
    color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
  );
}

/// The track name as shown to the user: the chosen file, or the bundled
/// loop and its author (product names, not translated).
String ambientMusicTrackName(HomeMusicService service) {
  final chosen = service.hasMusic ? service.selectedFileName : null;
  if (chosen != null && chosen.isNotEmpty) return chosen;
  return '${HomeMusicService.bundledTrackTitle} — '
      '${HomeMusicService.bundledTrackArtist}';
}

/// Row 1: ambient music on/off.
class AmbientMusicEnabledRow extends _AmbientMusicRow {
  const AmbientMusicEnabledRow({
    super.key,
    required super.focused,
    super.service,
  });

  static const Key toggleKey = Key('ambientMusic.enabled');

  @override
  State<AmbientMusicEnabledRow> createState() => _AmbientMusicEnabledRowState();
}

class _AmbientMusicEnabledRowState
    extends _AmbientMusicRowState<AmbientMusicEnabledRow> {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SettingRow(
      focused: widget.focused,
      title: text(AmbientMusicLocale.title),
      subtitle: '',
      subtitleWidget: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(text(AmbientMusicLocale.description), style: muted),
          SizedBox(height: 2.r),
          Text(
            AmbientMusicLocale.format(
              context,
              AmbientMusicLocale.track,
              <String, Object?>{'track': ambientMusicTrackName(service)},
            ),
            style: muted,
          ),
          if (!service.hasMusic)
            Text(text(AmbientMusicLocale.trackHelp), style: muted),
        ],
      ),
      trailing: CustomToggleSwitch(
        key: AmbientMusicEnabledRow.toggleKey,
        value: service.enabled,
        onChanged: (value) => unawaited(service.setEnabled(value)),
        activeColor: theme.colorScheme.primary,
      ),
    );
  }
}

/// Row 2: the music's own volume.
class AmbientMusicVolumeRow extends _AmbientMusicRow {
  const AmbientMusicVolumeRow({
    super.key,
    required super.focused,
    super.service,
  });

  static const Key sliderKey = Key('ambientMusic.volume');
  static const Key chipKey = Key('ambientMusic.volumeValue');

  /// The A button: the next 10 % step, back to 10 % after 100 %.
  static double nextStep(double volume) {
    final next = ((volume * 10 + 1e-6).floor() + 1) / 10;
    return next > HomeMusicService.maxVolume + 1e-6 ? 0.1 : next;
  }

  @override
  State<AmbientMusicVolumeRow> createState() => _AmbientMusicVolumeRowState();
}

class _AmbientMusicVolumeRowState
    extends _AmbientMusicRowState<AmbientMusicVolumeRow> {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final volume = service.volume;
    final percent = (volume * 100).round();
    final label = AmbientMusicLocale.format(
      context,
      AmbientMusicLocale.volumeValue,
      <String, Object?>{'percent': percent},
    );
    return Opacity(
      // Still adjustable while the music is off, shown dimmed.
      opacity: service.enabled ? 1 : 0.55,
      child: SettingRow(
        focused: widget.focused,
        title: text(AmbientMusicLocale.volumeTitle),
        subtitle: '',
        subtitleWidget: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(text(AmbientMusicLocale.volumeDescription), style: muted),
            SliderTheme(
              data: SliderTheme.of(context).copyWith(
                trackHeight: 2.r,
                thumbShape: RoundSliderThumbShape(enabledThumbRadius: 6.r),
                overlayShape: RoundSliderOverlayShape(overlayRadius: 12.r),
              ),
              child: Slider(
                key: AmbientMusicVolumeRow.sliderKey,
                value: volume,
                min: HomeMusicService.minVolume,
                max: HomeMusicService.maxVolume,
                divisions: 19,
                label: label,
                semanticFormatterCallback: (_) => label,
                activeColor: theme.colorScheme.primary,
                onChanged: (value) =>
                    unawaited(service.setVolume(value, persist: false)),
                onChangeEnd: (value) => unawaited(service.setVolume(value)),
              ),
            ),
          ],
        ),
        trailing: GestureDetector(
          key: AmbientMusicVolumeRow.chipKey,
          behavior: HitTestBehavior.opaque,
          onTap: () => unawaited(
            service.setVolume(AmbientMusicVolumeRow.nextStep(volume)),
          ),
          child: SettingValueChip(text: label),
        ),
      ),
    );
  }
}
