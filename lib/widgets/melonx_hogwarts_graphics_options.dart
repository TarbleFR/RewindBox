import 'package:flutter/material.dart';
import '../l10n/melonx_library_locale.dart';

class MelonxHogwartsGraphicsOptions extends StatelessWidget {
  const MelonxHogwartsGraphicsOptions({super.key, required this.settings, required this.onChanged});
  final Map<String, dynamic> settings;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    String text(String key) => MelonxLibraryLocale.text(Localizations.localeOf(context), key);
    final sync = settings['occlusionQuerySync'] as bool? ?? true;
    return Column(children: [
      Text(text('Hogwarts GPU options apply on the next launch. Disable them here to compare.')),
      SwitchListTile(
        title: Text(text('Synchronize occlusion results')),
        value: sync,
        onChanged: (value) {
          settings['occlusionQuerySync'] = value;
          if (!value) settings['relaxQueryFlushing'] = false;
          onChanged();
        },
      ),
      SwitchListTile(
        title: Text(text('Group GPU query submissions')),
        value: sync && (settings['relaxQueryFlushing'] as bool? ?? true),
        onChanged: sync ? (value) {
          settings['relaxQueryFlushing'] = value;
          onChanged();
        } : null,
      ),
    ]);
  }
}
