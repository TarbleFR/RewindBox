import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../../../l10n/app_locale.dart';
import '../../../../services/retro_achievements_identity.dart';
import '../../../../widgets/custom_notification.dart';

/// How the game of the achievements tab was identified
/// (NEOSTATION_RA_IDENTIFICATION_V1): nothing when the file itself is known
/// to RetroAchievements; a warning when only the title matched (the file may
/// not track in game); the file's hash when it is not recognized, so the
/// player can compare it with the files RetroAchievements accepts.
class RetroAchievementsIdentityNote extends StatelessWidget {
  const RetroAchievementsIdentityNote({super.key, required this.identity, this.compact = false});

  final RetroAchievementsIdentity identity;

  /// Inside the achievements header (title-only warning) rather than in the
  /// empty state.
  final bool compact;

  static Uri gamePage(int gameId) => Uri.parse('https://retroachievements.org/game/$gameId');

  static bool hasContent(RetroAchievementsIdentity? identity) => identity != null &&
      (identity.matchedByTitleOnly ||
          (identity.match == RetroAchievementsMatch.none && (identity.hash?.isNotEmpty ?? false)));

  @override
  Widget build(BuildContext context) {
    if (!hasContent(identity)) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.75);
    final hash = identity.hash;
    final gameId = identity.gameId;
    final children = <Widget>[];
    if (identity.matchedByTitleOnly) {
      children.add(Row(
        key: const ValueKey('ra-identity-title-only'),
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Symbols.warning_rounded, size: 13.r, color: Colors.orange),
          SizedBox(width: 4.r),
          Expanded(child: Text(AppLocale.raTitleOnlyMatch.getString(context),
            style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 9.r))),
        ],
      ));
    } else {
      children
        ..add(Text(AppLocale.raFileNotRecognized.getString(context),
          key: const ValueKey('ra-identity-not-recognized'),
          textAlign: TextAlign.center,
          style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 11.r, fontWeight: FontWeight.w600)))
        ..add(SizedBox(height: 4.r))
        ..add(Text(AppLocale.raFileNotRecognizedHelp.getString(context),
          textAlign: TextAlign.center, style: TextStyle(color: muted, fontSize: 9.r)));
    }
    if (hash != null && hash.isNotEmpty) {
      children
        ..add(SizedBox(height: 4.r))
        ..add(Wrap(
          alignment: compact ? WrapAlignment.start : WrapAlignment.center,
          crossAxisAlignment: WrapCrossAlignment.center,
          spacing: 6.r,
          children: [
            Text('${AppLocale.raFileHash.getString(context)}:', style: TextStyle(color: muted, fontSize: 9.r)),
            SelectableText(hash, key: const ValueKey('ra-identity-hash'),
              style: TextStyle(color: theme.colorScheme.onSurface, fontSize: 9.r, fontFamily: 'monospace')),
            TextButton.icon(
              key: const ValueKey('ra-identity-copy'),
              style: TextButton.styleFrom(visualDensity: VisualDensity.compact, padding: EdgeInsets.zero),
              onPressed: () async {
                await Clipboard.setData(ClipboardData(text: hash));
                if (context.mounted) {
                  AppNotification.showNotification(context, AppLocale.raHashCopied.getString(context),
                    type: NotificationType.info);
                }
              },
              icon: Icon(Symbols.content_copy_rounded, size: 12.r),
              label: Text(AppLocale.raCopyHash.getString(context), style: TextStyle(fontSize: 9.r)),
            ),
          ],
        ));
    }
    if (gameId != null && gameId > 0) {
      children.add(Align(
        alignment: compact ? Alignment.centerLeft : Alignment.center,
        child: TextButton.icon(
          key: const ValueKey('ra-identity-game-page'),
          style: TextButton.styleFrom(visualDensity: VisualDensity.compact, padding: EdgeInsets.zero),
          onPressed: () => launchUrl(gamePage(gameId), mode: LaunchMode.externalApplication),
          icon: Icon(Symbols.open_in_new_rounded, size: 12.r),
          label: Text(AppLocale.raOpenGamePage.getString(context), style: TextStyle(fontSize: 9.r)),
        ),
      ));
    }
    return Padding(
      padding: EdgeInsets.only(top: compact ? 4.r : 12.r, left: 12.r, right: 12.r),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: compact ? CrossAxisAlignment.start : CrossAxisAlignment.center,
        children: children,
      ),
    );
  }
}
