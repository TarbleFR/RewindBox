import 'package:flutter/material.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/game_box_locale.dart';

/// Result of [showGameBoxLanguagePicker]: a language code, or [followApp].
const String gameBoxFollowApp = '';

/// Lets the user choose the reading language of a box among NeoStation's
/// twelve languages. It never changes the application language.
///
/// [scanLanguages] are the languages with a scan published for them (marked
/// as such); the others are read translated.
Future<String?> showGameBoxLanguagePicker(
  BuildContext context, {
  required String current,
  bool followingApp = false,
  String? appLanguage,
  Set<String> scanLanguages = const {},
}) {
  return showModalBottomSheet<String>(
    context: context,
    showDragHandle: true,
    isScrollControlled: true,
    builder: (ctx) {
      final theme = Theme.of(ctx);
      Widget tile(String value, String title, String? subtitle, bool selected, {bool scan = false}) => ListTile(
            selected: selected,
            title: Text(title),
            subtitle: subtitle == null ? null : Text(subtitle),
            leading: Icon(selected ? Icons.check_circle : Icons.circle_outlined,
                color: selected ? theme.colorScheme.primary : theme.colorScheme.outline),
            trailing: scan
                ? Tooltip(
                    message: GameBoxLocale.format(ctx, GameBoxLocale.scanInLanguage,
                        {'language': GameBoxLocale.languageName(ctx, value)}),
                    child: const Icon(Icons.photo_library_outlined, size: 20),
                  )
                : null,
            onTap: () => Navigator.of(ctx).pop(value),
          );
      return SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxHeight: MediaQuery.sizeOf(ctx).height * 0.8),
          child: ListView(
            shrinkWrap: true,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Text(GameBoxLocale.text(ctx, GameBoxLocale.readingLanguage), style: theme.textTheme.titleMedium),
              ),
              if (appLanguage != null)
                tile(
                  gameBoxFollowApp,
                  GameBoxLocale.format(ctx, GameBoxLocale.followApp,
                      {'language': AppLocale.supportedLanguages[appLanguage] ?? appLanguage}),
                  null,
                  followingApp,
                  scan: false,
                ),
              for (final code in AppLocale.supportedLanguages.keys)
                tile(
                  code,
                  AppLocale.supportedLanguages[code]!,
                  GameBoxLocale.languageName(ctx, code),
                  !followingApp && code == current,
                  scan: scanLanguages.contains(code),
                ),
            ],
          ),
        ),
      );
    },
  );
}
