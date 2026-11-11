import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/app_locale.dart';
import 'core_footer.dart';

/// An empty Switch library remains a playlist. Its import action is owned by
/// the surrounding route; no scan preference or setup dialog is needed here.
/// Other embedded playlists (Xbox 360, Switch 2) reuse it with a [hint] that
/// says how to add games; Switch passes none.
class SwitchPlaylistEmptyState extends StatelessWidget {
  const SwitchPlaylistEmptyState({
    super.key,
    required this.systemName,
    required this.onBack,
    this.hint,
  });

  final String systemName;
  final VoidCallback onBack;

  /// Shown under the title when not null (already localized).
  final String? hint;

  @override
  Widget build(BuildContext context) => Stack(
    key: const ValueKey('switch-playlist-empty'),
    fit: StackFit.expand,
    children: [
      Center(
        child: Padding(
          padding: EdgeInsets.all(24.r),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                AppLocale.noGamesFoundFor
                    .getString(context)
                    .replaceFirst('{name}', systemName),
                textAlign: TextAlign.center,
                style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                  color: Theme.of(
                    context,
                  ).colorScheme.onSurface.withValues(alpha: .55),
                ),
              ),
              if (hint != null) ...[
                SizedBox(height: 8.r),
                Text(
                  hint!,
                  key: const ValueKey('switch-playlist-empty-hint'),
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(
                      context,
                    ).colorScheme.onSurface.withValues(alpha: .45),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
      Positioned(
        left: 12.r,
        bottom: 10.r,
        child: SafeArea(
          child: GamepadControl(
            label: AppLocale.back.getString(context),
            iconPath: 'assets/images/gamepad/Xbox_B_button.png',
            onTap: onBack,
          ),
        ),
      ),
    ],
  );
}
