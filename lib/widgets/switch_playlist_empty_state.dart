import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';

import '../l10n/app_locale.dart';
import 'core_footer.dart';

/// An empty Switch library remains a playlist. Its import action is owned by
/// the surrounding route; no scan preference or setup dialog is needed here.
class SwitchPlaylistEmptyState extends StatelessWidget {
  const SwitchPlaylistEmptyState({
    super.key,
    required this.systemName,
    required this.onBack,
  });

  final String systemName;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) => Stack(
    key: const ValueKey('switch-playlist-empty'),
    fit: StackFit.expand,
    children: [
      Center(
        child: Padding(
          padding: EdgeInsets.all(24.r),
          child: Text(
            AppLocale.noGamesFoundFor
                .getString(context)
                .replaceFirst('{name}', systemName),
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodyMedium?.copyWith(
              color: Theme.of(context).colorScheme.onSurface
                  .withValues(alpha: .55),
            ),
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
