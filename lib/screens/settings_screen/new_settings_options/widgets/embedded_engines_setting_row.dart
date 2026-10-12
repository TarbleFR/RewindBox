import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/l10n/console_manager_locale.dart';
import 'package:neostation/services/embedded_engine_policy.dart';

import '../../../../widgets/custom_toggle_switch.dart';
import 'setting_row.dart';

/// Settings › General › "Use built-in emulators" (iOS, Build 448). Off,
/// NeoStation is a frontend only: every game opens in an external app,
/// RetroArch first. The switch of each console (Consoles tab) is kept as it
/// is and applies again once this one is back on.
class EmbeddedEnginesSettingRow extends StatefulWidget {
  const EmbeddedEnginesSettingRow({
    super.key,
    required this.focused,
    this.policy,
  });

  final bool focused;

  /// Tests inject their own policy; the app uses the singleton.
  final EmbeddedEnginePolicy? policy;

  static const Key toggleKey = Key('embeddedEngines.enabled');

  @override
  State<EmbeddedEnginesSettingRow> createState() =>
      _EmbeddedEnginesSettingRowState();
}

class _EmbeddedEnginesSettingRowState extends State<EmbeddedEnginesSettingRow> {
  EmbeddedEnginePolicy get policy =>
      widget.policy ?? EmbeddedEnginePolicy.instance;

  bool _saving = false;
  bool _failed = false;

  @override
  void initState() {
    super.initState();
    policy.addListener(_changed);
    unawaited(policy.load());
  }

  @override
  void didUpdateWidget(covariant EmbeddedEnginesSettingRow oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = oldWidget.policy ?? EmbeddedEnginePolicy.instance;
    if (!identical(previous, policy)) {
      previous.removeListener(_changed);
      policy.addListener(_changed);
    }
  }

  @override
  void dispose() {
    policy.removeListener(_changed);
    super.dispose();
  }

  void _changed() {
    if (mounted) setState(() {});
  }

  Future<void> _set(bool value) async {
    if (_saving) return;
    setState(() {
      _saving = true;
      _failed = false;
    });
    final saved = await policy.setUseEmbedded(value);
    if (!mounted) return;
    setState(() {
      _saving = false;
      _failed = !saved;
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String text(String key) => ConsoleManagerLocale.text(context, key);
    final muted = theme.textTheme.bodyMedium?.copyWith(
      fontSize: 9.r,
      color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
    );
    final on = policy.useEmbedded;
    return SettingRow(
      focused: widget.focused,
      title: text(ConsoleManagerLocale.useEmbeddedTitle),
      subtitle: '',
      subtitleWidget: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            text(
              on
                  ? ConsoleManagerLocale.useEmbeddedOn
                  : ConsoleManagerLocale.useEmbeddedOff,
            ),
            style: muted,
          ),
          if (_failed)
            Text(
              ConsoleManagerLocale.format(
                Localizations.maybeLocaleOf(context) ?? const Locale('en'),
                ConsoleManagerLocale.changeFailed,
                <String, Object?>{'error': EmbeddedEnginePolicy.globalPreferenceKey},
              ),
              style: muted?.copyWith(color: theme.colorScheme.error),
            ),
        ],
      ),
      trailing: CustomToggleSwitch(
        key: EmbeddedEnginesSettingRow.toggleKey,
        value: on,
        disabled: _saving,
        onChanged: (value) => unawaited(_set(value)),
        activeColor: theme.colorScheme.primary,
      ),
    );
  }
}
