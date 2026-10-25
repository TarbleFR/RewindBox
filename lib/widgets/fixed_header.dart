import 'package:flutter/material.dart';
import 'header.dart';

class FixedHeader extends StatelessWidget {
  final int selectedTabIndex;
  final Function(int) onTabSelected;
  final ValueChanged<double>? onExtentChanged;

  const FixedHeader({
    super.key,
    required this.selectedTabIndex,
    required this.onTabSelected,
    this.onExtentChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Header(
      selectedTabIndex: selectedTabIndex,
      onTabSelected: onTabSelected,
      onExtentChanged: onExtentChanged,
    );
  }
}
