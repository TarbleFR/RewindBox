import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../l10n/app_locale.dart';
import '../../models/my_systems.dart';
import '../../themes/glacier_theme.dart';

/// The Glacier action bar under the systems grid: a dark glass band as wide
/// as the grid.
///
/// - Recent game: controller icon, the game's own thumbnail (its database
///   artwork), "Last played", the title and the glacier "A · Play" button.
/// - System: its art, name and game count, with the existing "Settings" and
///   "A · Enter" actions.
class GlacierSystemsFooter extends StatelessWidget {
  const GlacierSystemsFooter({
    super.key,
    required this.system,
    required this.onEnter,
    required this.onSettings,
    this.systemArtPath,
  });

  final SystemInfo system;
  final VoidCallback onEnter;
  final VoidCallback onSettings;

  /// The System Art image of [system] (pack or personal), if any.
  final String? systemArtPath;

  @override
  Widget build(BuildContext context) {
    final game = system.isGame;
    final thumbnail = game
        ? _firstExisting([system.customBackgroundPath, system.customWheelImage])
        : _firstExisting([system.customBackgroundPath, systemArtPath]);
    final count = system.folderName == 'android'
        ? AppLocale.apps.getString(context)
        : system.folderName == 'music'
        ? AppLocale.tracks.getString(context)
        : AppLocale.games.getString(context);
    final title = system.title ?? system.shortName ?? '';
    final secondary = game
        ? AppLocale.lastPlayed.getString(context)
        : '${system.numOfRoms} $count';

    return Container(
      key: const ValueKey('glacier-systems-footer'),
      // Grows with larger text instead of clipping it.
      constraints: BoxConstraints(minHeight: 31.7.r),
      padding: EdgeInsets.fromLTRB(11.r, 3.r, 3.r, 3.r),
      decoration: BoxDecoration(
        color: GlacierColors.panel.withValues(alpha: .80),
        borderRadius: BorderRadius.circular(5.r),
        border: Border.all(
          color: GlacierColors.silver.withValues(alpha: .16),
          width: .8,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: .35),
            blurRadius: 9.r,
            offset: Offset(0, 3.r),
          ),
        ],
      ),
      child: Row(
        children: [
          if (game) ...[
            Icon(
              Symbols.sports_esports,
              size: 14.r,
              fill: 1,
              color: GlacierColors.text,
            ),
            SizedBox(width: 9.r),
          ],
          if (thumbnail != null) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(3.r),
              child: Image.file(
                File(thumbnail),
                key: ValueKey('glacier-footer-thumb-$thumbnail'),
                width: 30.r,
                height: 25.5.r,
                fit: BoxFit.cover,
                cacheWidth: 192,
                errorBuilder: (_, _, _) =>
                    SizedBox(width: 30.r, height: 25.5.r),
              ),
            ),
            SizedBox(width: 7.r),
          ],
          Expanded(
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (game)
                  _line(
                    secondary,
                    7.r,
                    GlacierColors.secondaryText,
                    FontWeight.w500,
                  ),
                _line(title, 10.5.r, GlacierColors.text, FontWeight.w600),
                if (!game)
                  _line(
                    secondary,
                    7.r,
                    GlacierColors.secondaryText,
                    FontWeight.w500,
                  ),
              ],
            ),
          ),
          if (!game) ...[
            GlacierActionButton(
              key: const ValueKey('glacier-footer-settings'),
              glyphAsset: 'assets/images/gamepad/Xbox_Menu_button.png',
              label: AppLocale.settings.getString(context),
              onTap: onSettings,
            ),
            SizedBox(width: 5.r),
          ],
          GlacierActionButton(
            key: const ValueKey('glacier-footer-primary'),
            primary: true,
            glyphAsset: 'assets/images/gamepad/Xbox_A_button.png',
            label: game
                ? AppLocale.play.getString(context)
                : AppLocale.enter.getString(context),
            onTap: onEnter,
          ),
        ],
      ),
    );
  }

  static Widget _line(
    String text,
    double size,
    Color color,
    FontWeight weight,
  ) => Text(
    text,
    maxLines: 1,
    overflow: TextOverflow.ellipsis,
    style: TextStyle(
      color: color,
      fontSize: size,
      fontWeight: weight,
      height: 1.25,
    ),
  );

  static String? _firstExisting(List<String?> paths) {
    for (final candidate in paths) {
      if (candidate == null || candidate.isEmpty) continue;
      final lower = candidate.toLowerCase();
      if (lower.endsWith('.mp4') ||
          lower.endsWith('.m4v') ||
          lower.endsWith('.mov')) {
        continue;
      }
      if (File(candidate).existsSync()) return candidate;
    }
    return null;
  }
}

/// A Glacier footer action: the controller glyph and its label. The primary
/// one is glacier blue with graphite text; the other is smoked glass.
class GlacierActionButton extends StatelessWidget {
  const GlacierActionButton({
    super.key,
    required this.glyphAsset,
    required this.label,
    required this.onTap,
    this.primary = false,
  });

  final String glyphAsset;
  final String label;
  final VoidCallback onTap;
  final bool primary;

  @override
  Widget build(BuildContext context) {
    final foreground = primary ? GlacierColors.actionText : GlacierColors.text;
    final radius = BorderRadius.circular(5.r);
    return Semantics(
      button: true,
      label: label,
      excludeSemantics: true,
      child: Material(
        color: primary
            ? GlacierColors.focus
            : GlacierColors.panelRaised.withValues(alpha: .9),
        borderRadius: radius,
        child: InkWell(
          onTap: onTap,
          canRequestFocus: false,
          borderRadius: radius,
          child: Container(
            constraints: BoxConstraints(
              minHeight: 25.4.r,
              minWidth: primary ? 70.r : 0,
            ),
            padding: EdgeInsets.symmetric(horizontal: 10.r),
            decoration: BoxDecoration(
              borderRadius: radius,
              border: primary
                  ? null
                  : Border.all(
                      color: GlacierColors.silver.withValues(alpha: .2),
                      width: .8,
                    ),
              boxShadow: primary
                  ? [
                      BoxShadow(
                        color: GlacierColors.focus.withValues(alpha: .35),
                        blurRadius: 8.r,
                      ),
                    ]
                  : null,
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                Image.asset(
                  glyphAsset,
                  width: 12.5.r,
                  height: 12.5.r,
                  color: foreground,
                  colorBlendMode: BlendMode.srcIn,
                ),
                SizedBox(width: 8.r),
                Text(
                  label,
                  maxLines: 1,
                  style: TextStyle(
                    color: foreground,
                    fontSize: 11.r,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
