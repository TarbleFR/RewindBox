import 'package:flutter/material.dart';

import '../../../../widgets/glass/glass_surface.dart';

/// Section divider used to group settings rows under a labelled heading.
///
/// Renders a short primary-colour accent bar followed by an uppercase-weight
/// label, with the category spacing of the Liquid Glass system above it.
/// Shared by any settings content panel that groups its rows into sections
/// (Directories, Secondary).
class SettingsSectionHeader extends StatelessWidget {
  /// Heading text shown beside the accent bar.
  final String label;

  /// The first header of a panel carries no category gap above it.
  final bool first;

  const SettingsSectionHeader({
    super.key,
    required this.label,
    this.first = false,
  });

  @override
  Widget build(BuildContext context) =>
      GlassSectionHeader(label: label, first: first);
}
