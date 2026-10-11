import 'package:flutter/material.dart';

/// Settings › Tools › BIOS checker for the embedded libretro cores
/// (Build 438).
///
/// Contract stub: the BIOS checker package replaces this file with the real
/// page. Other pages open it with an optional [console] (a key of
/// `LibretroCoreCatalog.consoles`) to preselect the console filter.
class LibretroBiosCheckerScreen extends StatefulWidget {
  const LibretroBiosCheckerScreen({super.key, this.console});

  /// Console filter to preselect; null shows every console.
  final String? console;

  @override
  State<LibretroBiosCheckerScreen> createState() =>
      _LibretroBiosCheckerScreenState();
}

class _LibretroBiosCheckerScreenState extends State<LibretroBiosCheckerScreen> {
  @override
  Widget build(BuildContext context) => const SizedBox.shrink();
}
