import 'package:flutter/material.dart';

import '../../../../widgets/glass/glass_controls.dart';

/// Compact pill showing the current value of a settings row (language, a
/// cyclable option, etc.). Pair it as the [SettingRow.trailing] control; wrap
/// the owning row in a tap handler to cycle or open a picker.
///
/// Optionally renders a trailing glyph (e.g. a dropdown caret) to signal that
/// tapping opens a picker.
class SettingValueChip extends StatelessWidget {
  /// Text of the current value.
  final String text;

  /// Optional trailing glyph, e.g. a dropdown caret for picker-backed rows.
  final IconData? trailingIcon;

  const SettingValueChip({super.key, required this.text, this.trailingIcon});

  @override
  Widget build(BuildContext context) =>
      GlassChip(label: text, trailingIcon: trailingIcon);
}
