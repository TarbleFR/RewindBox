import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/ui_refresh_rate_locale.dart';
import 'package:neostation/services/ui_refresh_rate_service.dart';
import 'package:neostation/themes/app_themes.dart';

import '../../../../widgets/custom_toggle_switch.dart';
import 'setting_row.dart';
import 'setting_value_chip.dart';

/// Settings › General › "120 Hz interface" (iOS, Build 440).
///
/// Shows the stored choice (applied at the next launch), why the option is
/// unavailable or limited, and only measured rates. The "Measure" action runs
/// one bounded animation ([UiRefreshRateService.measureDuration]); nothing
/// here animates otherwise.
class UiRefreshRateSettingRow extends StatefulWidget {
  const UiRefreshRateSettingRow({
    super.key,
    required this.focused,
    this.service,
  });

  final bool focused;

  /// Tests inject their own service; the app uses the singleton.
  final UiRefreshRateService? service;

  static const Key toggleKey = Key('uiRefreshRate.toggle');
  static const Key measureKey = Key('uiRefreshRate.measure');
  static const Key progressKey = Key('uiRefreshRate.progress');

  @override
  State<UiRefreshRateSettingRow> createState() =>
      _UiRefreshRateSettingRowState();
}

class _UiRefreshRateSettingRowState extends State<UiRefreshRateSettingRow>
    with SingleTickerProviderStateMixin {
  late final AnimationController _measure = AnimationController(
    vsync: this,
    duration: UiRefreshRateService.measureDuration,
  );

  UiRefreshRateService get _service =>
      widget.service ?? UiRefreshRateService.instance;

  @override
  void initState() {
    super.initState();
    _service.addListener(_changed);
    // Screen, Low Power Mode and temperature can change between visits.
    unawaited(_service.refresh());
  }

  @override
  void didUpdateWidget(covariant UiRefreshRateSettingRow oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = oldWidget.service ?? UiRefreshRateService.instance;
    if (!identical(previous, _service)) {
      previous.removeListener(_changed);
      _service.addListener(_changed);
    }
  }

  @override
  void dispose() {
    _service.removeListener(_changed);
    if (_measure.isAnimating || _service.measuring) {
      _service.cancelMeasurement();
    }
    _measure.dispose();
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _runMeasurement() async {
    if (_service.measuring) return;
    _service.beginMeasurement();
    try {
      await _measure.forward(from: 0).orCancel;
    } on TickerCanceled {
      return;
    }
    if (!mounted) return;
    await _service.completeMeasurement();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final service = _service;
    final state = service.state;
    final available = state?.available ?? false;
    String text(String key) => UiRefreshRateLocale.text(context, key);
    String hz(String key, num value) => UiRefreshRateLocale.format(
      context,
      key,
      <String, Object?>{'hz': value},
    );

    final muted = theme.textTheme.bodyMedium?.copyWith(
      fontSize: 9.r,
      color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
    );
    final warning = theme.textTheme.bodyMedium?.copyWith(
      fontSize: 9.r,
      fontWeight: FontWeight.w600,
      color: AppThemes.getCustomColors(context).warningColor as Color?,
    );
    final failure = theme.textTheme.bodyMedium?.copyWith(
      fontSize: 9.r,
      fontWeight: FontWeight.w600,
      color: theme.colorScheme.error,
    );
    final technical = theme.textTheme.bodySmall?.copyWith(
      fontSize: 8.r,
      fontFamily: 'monospace',
      color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
    );

    final lines = <Widget>[
      Text(text(UiRefreshRateLocale.description), style: muted),
    ];
    void line(String value, TextStyle? style) {
      lines
        ..add(SizedBox(height: 2.r))
        ..add(Text(value, style: style));
    }

    if (state != null) {
      if (!available) {
        if (state.hookInstalled) {
          line(
            hz(UiRefreshRateLocale.unavailableScreen, state.screenMaxHz),
            warning,
          );
        } else {
          line(text(UiRefreshRateLocale.unavailableEngine), warning);
          line(
            UiRefreshRateLocale.format(
              context,
              UiRefreshRateLocale.technicalCode,
              <String, Object?>{'code': state.hookStatus},
            ),
            technical,
          );
        }
      } else {
        if (service.error == UiRefreshRateError.saveFailed) {
          line(text(UiRefreshRateLocale.saveFailed), failure);
          final code = service.errorCode;
          if (code != null) {
            line(
              UiRefreshRateLocale.format(
                context,
                UiRefreshRateLocale.technicalCode,
                <String, Object?>{'code': code},
              ),
              technical,
            );
          }
        }
        if (state.restartRequired) {
          line(text(UiRefreshRateLocale.restartRequired), warning);
        }
        if (state.lowPowerMode) {
          line(text(UiRefreshRateLocale.limitedLowPower), warning);
        } else if (state.thermalLimited) {
          line(text(UiRefreshRateLocale.limitedThermal), warning);
        }
      }
    }

    final measurement = service.lastMeasurement;
    final postGame = service.postGameMeasurement;
    if (service.measuring) {
      line(text(UiRefreshRateLocale.measuring), muted);
      lines
        ..add(SizedBox(height: 4.r))
        ..add(
          AnimatedBuilder(
            animation: _measure,
            builder: (context, _) => LinearProgressIndicator(
              key: UiRefreshRateSettingRow.progressKey,
              value: _measure.value,
              minHeight: 3.r,
              borderRadius: BorderRadius.circular(2.r),
            ),
          ),
        );
    } else {
      // The last requested measurement may fail while an earlier passive
      // one stays valid: both are shown, never a supposed rate.
      if (measurement != null) {
        line(hz(UiRefreshRateLocale.measured, measurement.effectiveHz), muted);
      }
      if (service.measureFailed) {
        line(text(UiRefreshRateLocale.measureFailed), muted);
      } else if (measurement == null) {
        line(text(UiRefreshRateLocale.notMeasured), muted);
      }
    }
    if (postGame != null) {
      line(
        hz(UiRefreshRateLocale.measuredAfterGame, postGame.effectiveHz),
        muted,
      );
    }
    if (state != null) {
      lines
        ..add(SizedBox(height: 6.r))
        ..add(
          Semantics(
            button: true,
            enabled: !service.measuring,
            label: text(UiRefreshRateLocale.measureHint),
            // excludeSemantics drops the detector's own tap action: give it
            // back here so VoiceOver can start the measurement.
            onTap: service.measuring ? null : _runMeasurement,
            excludeSemantics: true,
            child: GestureDetector(
              key: UiRefreshRateSettingRow.measureKey,
              behavior: HitTestBehavior.opaque,
              onTap: service.measuring ? null : _runMeasurement,
              child: Opacity(
                opacity: service.measuring ? 0.5 : 1,
                child: SettingValueChip(
                  text: text(UiRefreshRateLocale.measureAction),
                ),
              ),
            ),
          ),
        );
    }

    return SettingRow(
      focused: widget.focused,
      title: text(UiRefreshRateLocale.title),
      subtitle: '',
      subtitleWidget: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: lines,
      ),
      trailing: CustomToggleSwitch(
        key: UiRefreshRateSettingRow.toggleKey,
        value: available && state!.storedEnabled,
        onChanged: (value) => unawaited(service.setEnabled(value)),
        disabled: !available || service.saving,
        activeColor: theme.colorScheme.primary,
      ),
    );
  }
}
