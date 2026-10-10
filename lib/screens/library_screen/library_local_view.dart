import 'package:flutter/material.dart';

import 'library_gamepad_view_controller.dart';

/// Local library section (contract stub, Build 437 wave 2): import from
/// Files, search, sort, rename, delete the imported copy, open the reader.
class LibraryLocalView extends StatefulWidget {
  const LibraryLocalView({
    super.key,
    required this.controller,
    required this.onBack,
  });

  final LibraryGamepadViewController controller;

  /// Returns to the Library hub.
  final VoidCallback onBack;

  @override
  State<LibraryLocalView> createState() => _LibraryLocalViewState();
}

class _LibraryLocalViewState extends State<LibraryLocalView> {
  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
