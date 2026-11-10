import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import '../l10n/app_locale.dart';
import '../l10n/game_box_locale.dart';
import '../services/game_box/game_box_sources.dart';
import '../utils/gamepad_nav.dart';
import '../services/game_service.dart';
import 'glass/glass_surface.dart';

/// Specialized dialog content providing gamepad-friendly navigation for
/// scraping session summaries.
///
/// Extracted verbatim from `ScreenScraperService`'s private
/// `_ScrapingSummaryDialogContent` so the service file stays lean; behavior and
/// layout are unchanged.
class ScrapingSummaryDialog extends StatefulWidget {
  final int totalGames;
  final int successfulGames;
  final int failedGames;
  final String elapsedTime;

  /// What the session wrote (docs/game-box-3d.md § 18).
  final int mediaAdded;
  final int mediaReplaced;

  /// Box faces found, by source id (`screenscraper`, `gametdb`, `mobygames`).
  final Map<String, int> facesBySource;
  final int facesMissing;

  const ScrapingSummaryDialog({
    super.key,
    required this.totalGames,
    required this.successfulGames,
    required this.failedGames,
    required this.elapsedTime,
    this.mediaAdded = 0,
    this.mediaReplaced = 0,
    this.facesBySource = const {},
    this.facesMissing = 0,
  });

  @override
  State<ScrapingSummaryDialog> createState() => _ScrapingSummaryDialogState();
}

class _ScrapingSummaryDialogState extends State<ScrapingSummaryDialog> {
  late GamepadNavigation _gamepadNav;

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onSelectItem: () => Navigator.of(context).pop(),
      onBack: () => Navigator.of(context).pop(),
    );
    _gamepadNav.initialize();
    GamepadNavigationManager.pushLayer(
      'scraping_summary_dialog',
      onActivate: () => _gamepadNav.activate(),
      onDeactivate: () => _gamepadNav.deactivate(),
    );
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer('scraping_summary_dialog');
    _gamepadNav.dispose();
    super.dispose();
  }

  String _t(String key) => GameBoxLocale.text(context, key);

  /// "12 (GameTDB 8, ScreenScraper 4)".
  String _faces() {
    final total = widget.facesBySource.values.fold(0, (a, b) => a + b);
    final parts = [
      for (final p in GameBoxProvider.values)
        if ((widget.facesBySource[p.id] ?? 0) > 0)
          '${p.label} ${widget.facesBySource[p.id]}',
    ];
    return parts.isEmpty ? '$total' : '$total (${parts.join(', ')})';
  }

  @override
  Widget build(BuildContext context) {
    final facesFound = widget.facesBySource.values.fold(0, (a, b) => a + b);
    final nothingNew =
        widget.totalGames > 0 &&
        widget.mediaAdded == 0 &&
        widget.mediaReplaced == 0 &&
        facesFound == 0;
    final rate = widget.totalGames > 0
        ? ((widget.successfulGames / widget.totalGames) * 100).toStringAsFixed(
            1,
          )
        : '0.0';
    return Dialog(
      backgroundColor: Colors.transparent,
      insetPadding: EdgeInsets.symmetric(horizontal: 10.w, vertical: 6.h),
      child: GlassSurface(
        role: GlassRole.modal,
        radiusSize: GlassRadius.m,
        constraints: BoxConstraints(maxWidth: 240.w),
        child: ClipRRect(
          borderRadius: LiquidGlassTheme.of(context).radius(GlassRadius.m),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: double.infinity,
                padding: EdgeInsets.symmetric(vertical: 8.h),
                decoration: BoxDecoration(
                  color: Theme.of(
                    context,
                  ).scaffoldBackgroundColor.withValues(alpha: 0.2),
                  border: Border(
                    bottom: BorderSide(
                      color: Theme.of(
                        context,
                      ).colorScheme.outline.withValues(alpha: 0.1),
                      width: 1.r,
                    ),
                  ),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Icon(
                      Symbols.check_circle_rounded,
                      size: 16.r,
                      color: Colors.green,
                    ),
                    SizedBox(width: 6.w),
                    Text(
                      _t(GameBoxLocale.scrapeSummaryTitle),
                      style: TextStyle(
                        fontSize: 13.r,
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.onSurface,
                      ),
                    ),
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.symmetric(horizontal: 12.w, vertical: 10.h),
                child: Column(
                  children: [
                    _buildCompactStatRow(
                      _t(GameBoxLocale.scrapeSummaryGames),
                      widget.totalGames.toString(),
                    ),
                    SizedBox(height: 4.h),
                    _buildCompactStatRow(
                      _t(GameBoxLocale.scrapeSummarySuccess),
                      '${widget.successfulGames} ($rate%)',
                      valueColor: Colors.green,
                    ),
                    SizedBox(height: 4.h),
                    _buildCompactStatRow(
                      _t(GameBoxLocale.scrapeSummaryFailed),
                      widget.failedGames.toString(),
                      valueColor: widget.failedGames > 0
                          ? Colors.orange
                          : Theme.of(context).colorScheme.onSurface,
                    ),
                    SizedBox(height: 4.h),
                    _buildCompactStatRow(
                      _t(GameBoxLocale.scrapeSummaryDuration),
                      widget.elapsedTime,
                      valueColor: Theme.of(context).colorScheme.primary,
                    ),
                    if (widget.mediaAdded > 0) ...[
                      SizedBox(height: 4.h),
                      _buildCompactStatRow(
                        _t(GameBoxLocale.scrapeSummaryAdded),
                        '${widget.mediaAdded}',
                      ),
                    ],
                    if (widget.mediaReplaced > 0) ...[
                      SizedBox(height: 4.h),
                      _buildCompactStatRow(
                        _t(GameBoxLocale.scrapeSummaryReplaced),
                        '${widget.mediaReplaced}',
                      ),
                    ],
                    if (facesFound > 0) ...[
                      SizedBox(height: 4.h),
                      _buildCompactStatRow(
                        _t(GameBoxLocale.scrapeSummaryFaces),
                        _faces(),
                      ),
                    ],
                    if (widget.facesMissing > 0) ...[
                      SizedBox(height: 4.h),
                      _buildCompactStatRow(
                        _t(GameBoxLocale.scrapeSummaryFacesMissing),
                        '${widget.facesMissing}',
                        valueColor: Colors.orange,
                      ),
                    ],
                    if (nothingNew) ...[
                      SizedBox(height: 6.h),
                      Text(
                        _t(GameBoxLocale.scrapeSummaryNothing),
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: 10.r,
                          color: Theme.of(
                            context,
                          ).colorScheme.onSurface.withValues(alpha: 0.7),
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              Padding(
                padding: EdgeInsets.only(left: 12.r, right: 12.r, bottom: 10.r),
                child: SizedBox(
                  width: double.infinity,
                  height: 32.h,
                  child: ElevatedButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Theme.of(context).colorScheme.primary,
                      foregroundColor: Colors.white,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8.r),
                      ),
                    ),
                    child: Text(
                      AppLocale.ok.getString(context),
                      style: TextStyle(
                        fontSize: 12.r,
                        fontWeight: FontWeight.bold,
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildCompactStatRow(String label, String value, {Color? valueColor}) {
    // Labels are translated and values can be long ("12 (GameTDB 8, …)"):
    // both wrap instead of overflowing the narrow dialog.
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Expanded(
          child: Text(
            label,
            style: TextStyle(
              fontSize: 11.r,
              color: Theme.of(context).colorScheme.onSurface,
            ),
          ),
        ),
        SizedBox(width: 8.w),
        Flexible(
          child: Text(
            value,
            textAlign: TextAlign.end,
            style: TextStyle(
              fontSize: 11.r,
              fontWeight: FontWeight.bold,
              color: valueColor ?? Theme.of(context).colorScheme.onSurface,
            ),
          ),
        ),
      ],
    );
  }
}
