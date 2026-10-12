import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/l10n/external_display_locale.dart';
import 'package:neostation/services/external_display_service.dart';
import 'package:neostation/themes/app_themes.dart';

import '../../../../widgets/custom_toggle_switch.dart';
import 'setting_row.dart';
import 'setting_value_chip.dart';

/// Settings › General › "AirPlay and external screen" (iOS, Build 447):
/// three rows after "120 Hz interface", all reading the same
/// [ExternalDisplayService].
///
/// 1. [ExternalDisplayEnabledRow] — the own-window switch and the state of
///    the external screen;
/// 2. [ExternalDisplayModeRow] — the picture format, cycled by a chip, with
///    the crop warning of "Fill the screen";
/// 3. [ExternalDisplayMenuRow] — the "menu on the TV" switch.
///
/// Every value shown is the one re-read from iOS; a refused save shows its
/// error under the row that asked for it and the native value stays.
abstract class _ExternalDisplayRow extends StatefulWidget {
  const _ExternalDisplayRow({super.key, required this.focused, this.service});

  final bool focused;

  /// Tests inject their own service; the app uses the singleton.
  final ExternalDisplayService? service;
}

abstract class _ExternalDisplayRowState<T extends _ExternalDisplayRow>
    extends State<T> {
  ExternalDisplayService get service =>
      widget.service ?? ExternalDisplayService.instance;

  @override
  void initState() {
    super.initState();
    service.addListener(_changed);
    // A TV can be connected or removed between visits; concurrent reads of
    // the three rows share one channel call.
    unawaited(service.refresh());
  }

  @override
  void didUpdateWidget(covariant T oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = oldWidget.service ?? ExternalDisplayService.instance;
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

  String text(String key) => ExternalDisplayLocale.text(context, key);

  TextStyle? get muted => Theme.of(context).textTheme.bodyMedium?.copyWith(
    fontSize: 9.r,
    color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6),
  );

  TextStyle? get warning => Theme.of(context).textTheme.bodyMedium?.copyWith(
    fontSize: 9.r,
    fontWeight: FontWeight.w600,
    color: AppThemes.getCustomColors(context).warningColor as Color?,
  );

  TextStyle? get failure => Theme.of(context).textTheme.bodyMedium?.copyWith(
    fontSize: 9.r,
    fontWeight: FontWeight.w600,
    color: Theme.of(context).colorScheme.error,
  );

  TextStyle? get technical => Theme.of(context).textTheme.bodySmall?.copyWith(
    fontSize: 8.r,
    fontFamily: 'monospace',
    color: Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.45),
  );

  Widget technicalLine(String code) => Text(
    ExternalDisplayLocale.format(
      context,
      ExternalDisplayLocale.technicalCode,
      <String, Object?>{'code': code},
    ),
    style: technical,
  );

  /// The save error of [field], if the last failed action was writing it.
  List<Widget> errorLines(ExternalDisplayField field) {
    if (service.error != ExternalDisplayError.saveFailed ||
        service.errorField != field) {
      return const <Widget>[];
    }
    final code = service.errorCode;
    return <Widget>[
      Text(text(ExternalDisplayLocale.saveFailed), style: failure),
      if (code != null) technicalLine(code),
    ];
  }

  Widget subtitle(List<Widget> lines) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: <Widget>[
      for (var index = 0; index < lines.length; index++) ...[
        if (index > 0) SizedBox(height: 2.r),
        lines[index],
      ],
    ],
  );
}

/// Row 1: own window on the external screen (`Enabled`) and its state.
class ExternalDisplayEnabledRow extends _ExternalDisplayRow {
  const ExternalDisplayEnabledRow({
    super.key,
    required super.focused,
    super.service,
  });

  static const Key toggleKey = Key('externalDisplay.enabled');

  @override
  State<ExternalDisplayEnabledRow> createState() =>
      _ExternalDisplayEnabledRowState();
}

class _ExternalDisplayEnabledRowState
    extends _ExternalDisplayRowState<ExternalDisplayEnabledRow> {
  /// What the external screen shows right now, from the native state.
  Widget _status(ExternalDisplayState state) {
    if (!state.enabled) {
      return Text(text(ExternalDisplayLocale.mirroringOff), style: muted);
    }
    if (!state.connected) {
      return Text(text(ExternalDisplayLocale.noExternalScreen), style: muted);
    }
    if (state.content == ExternalDisplayContent.game) {
      return Text(text(ExternalDisplayLocale.gameOnExternal), style: muted);
    }
    if (state.suspended) {
      // The running engine (Dusklight, KartPad) cannot draw there: the
      // window is hidden and iOS mirrors the iPhone.
      return Text(text(ExternalDisplayLocale.unsupportedEngine), style: warning);
    }
    if (!state.menuOnTV) {
      // Outside a game the TV shows a copy of the iPhone, by choice.
      return Text(text(ExternalDisplayLocale.menuOffMirroring), style: muted);
    }
    // The menu is on the TV, or about to be (iOS mirrors the iPhone until
    // the menu engine exists): the neutral line.
    return Text(
      ExternalDisplayLocale.format(
        context,
        ExternalDisplayLocale.externalScreen,
        <String, Object?>{
          'width': state.screenWidth.round(),
          'height': state.screenHeight.round(),
        },
      ),
      style: muted,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = service.state;
    final supported = state?.supported ?? false;
    final lines = <Widget>[
      Text(text(ExternalDisplayLocale.description), style: muted),
    ];
    if (state != null) {
      if (!supported) {
        lines
          ..add(Text(text(ExternalDisplayLocale.unavailable), style: warning))
          ..add(technicalLine(state.accessoryStatus));
      } else {
        lines
          ..addAll(errorLines(ExternalDisplayField.enabled))
          ..add(_status(state));
      }
    }
    return SettingRow(
      focused: widget.focused,
      title: text(ExternalDisplayLocale.title),
      subtitle: '',
      subtitleWidget: subtitle(lines),
      trailing: CustomToggleSwitch(
        key: ExternalDisplayEnabledRow.toggleKey,
        value: supported && state!.enabled,
        onChanged: (value) => unawaited(service.setEnabled(value)),
        disabled: !supported || service.saving,
        activeColor: theme.colorScheme.primary,
      ),
    );
  }
}

/// Row 2: picture format on the external screen, cycled by its chip.
class ExternalDisplayModeRow extends _ExternalDisplayRow {
  const ExternalDisplayModeRow({
    super.key,
    required super.focused,
    super.service,
  });

  static const Key chipKey = Key('externalDisplay.mode');

  /// Catalog key of the name of [mode].
  static String nameKey(ExternalDisplayMode mode) => switch (mode) {
    ExternalDisplayMode.automatic => ExternalDisplayLocale.modeAutomatic,
    ExternalDisplayMode.fit => ExternalDisplayLocale.modeFit,
    ExternalDisplayMode.fill => ExternalDisplayLocale.modeFill,
    ExternalDisplayMode.original => ExternalDisplayLocale.modeOriginal,
  };

  /// Catalog key of the explanation of [mode].
  static String helpKey(ExternalDisplayMode mode) => switch (mode) {
    ExternalDisplayMode.automatic => ExternalDisplayLocale.modeAutomaticHelp,
    ExternalDisplayMode.fit => ExternalDisplayLocale.modeFitHelp,
    ExternalDisplayMode.fill => ExternalDisplayLocale.modeFillHelp,
    ExternalDisplayMode.original => ExternalDisplayLocale.modeOriginalHelp,
  };

  @override
  State<ExternalDisplayModeRow> createState() => _ExternalDisplayModeRowState();
}

class _ExternalDisplayModeRowState
    extends _ExternalDisplayRowState<ExternalDisplayModeRow> {
  @override
  Widget build(BuildContext context) {
    final state = service.state;
    final supported = state?.supported ?? false;
    final mode = state?.mode ?? ExternalDisplayMode.automatic;
    final lines = <Widget>[
      Text(text(ExternalDisplayModeRow.helpKey(mode)), style: muted),
      if (mode.crops)
        // The crop is announced where the choice is made.
        Text(text(ExternalDisplayLocale.fillCrops), style: warning),
      if (supported) ...errorLines(ExternalDisplayField.mode),
    ];
    final enabled = supported && !service.saving;
    return SettingRow(
      focused: widget.focused,
      title: text(ExternalDisplayLocale.modeTitle),
      subtitle: '',
      subtitleWidget: subtitle(lines),
      trailing: Semantics(
        button: true,
        enabled: enabled,
        child: GestureDetector(
          key: ExternalDisplayModeRow.chipKey,
          behavior: HitTestBehavior.opaque,
          onTap: enabled ? () => unawaited(service.cycleMode()) : null,
          child: Opacity(
            opacity: supported ? 1 : 0.5,
            child: SettingValueChip(
              text: text(ExternalDisplayModeRow.nameKey(mode)),
              trailingIcon: Symbols.arrow_drop_down_rounded,
            ),
          ),
        ),
      ),
    );
  }
}

/// Row 3: the TV shows the NeoStation menu outside a game (`MenuOnTV`).
class ExternalDisplayMenuRow extends _ExternalDisplayRow {
  const ExternalDisplayMenuRow({
    super.key,
    required super.focused,
    super.service,
  });

  static const Key toggleKey = Key('externalDisplay.menu');

  @override
  State<ExternalDisplayMenuRow> createState() => _ExternalDisplayMenuRowState();
}

class _ExternalDisplayMenuRowState
    extends _ExternalDisplayRowState<ExternalDisplayMenuRow> {
  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final state = service.state;
    final supported = state?.supported ?? false;
    final lines = <Widget>[
      Text(text(ExternalDisplayLocale.menuOnTvHelp), style: muted),
      if (supported) ...errorLines(ExternalDisplayField.menuOnTV),
    ];
    return SettingRow(
      focused: widget.focused,
      title: text(ExternalDisplayLocale.menuOnTv),
      subtitle: '',
      subtitleWidget: subtitle(lines),
      trailing: CustomToggleSwitch(
        key: ExternalDisplayMenuRow.toggleKey,
        value: supported && state!.menuOnTV,
        onChanged: (value) => unawaited(service.setMenuOnTV(value)),
        disabled: !supported || service.saving,
        activeColor: theme.colorScheme.primary,
      ),
    );
  }
}
