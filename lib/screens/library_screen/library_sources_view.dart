import 'package:flutter/material.dart';

import 'library_gamepad_view_controller.dart';

/// Sources & catalogues section of the Library (contract stub, Build 437
/// wave 2): remembered catalogues, catalogue preview and selective
/// activation, active sources with their verification status.
class LibrarySourcesView extends StatefulWidget {
  const LibrarySourcesView({
    super.key,
    required this.controller,
    required this.onBack,
    required this.onSourcesChanged,
  });

  final LibraryGamepadViewController controller;

  /// Returns to the Library hub.
  final VoidCallback onBack;

  /// Called after sources were activated, deactivated or updated so the hub
  /// reloads its source list.
  final VoidCallback onSourcesChanged;

  @override
  State<LibrarySourcesView> createState() => _LibrarySourcesViewState();
}

class _LibrarySourcesViewState extends State<LibrarySourcesView> {
  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
