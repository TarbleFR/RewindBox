import 'package:flutter/material.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/game_box_locale.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import '../../settings_screen/new_settings_options/settings_title.dart';
import 'package:neostation/widgets/custom_radio_button.dart';
import 'package:neostation/widgets/custom_toggle_switch.dart';
import '../../../widgets/glass/glass_surface.dart';

/// What the scraper's Start does (docs/game-box-3d.md § 18): the three
/// modes, then whether the box faces still missing are also looked for on
/// GameTDB and MobyGames.
class ScrapeModeContent extends StatefulWidget {
  final bool isContentFocused;
  final int selectedContentIndex;
  final String currentMode;
  final ValueChanged<String> onModeChanged;

  const ScrapeModeContent({
    super.key,
    required this.isContentFocused,
    required this.selectedContentIndex,
    required this.currentMode,
    required this.onModeChanged,
  });

  /// Modes, in the order they are listed.
  static const modes = ['new_only', 'all', 'faces_only'];

  /// Rows for the screen's gamepad navigation: the modes and the toggle.
  static int get itemCount => modes.length + 1;

  @override
  State<ScrapeModeContent> createState() => ScrapeModeContentState();
}

class ScrapeModeContentState extends State<ScrapeModeContent> {
  bool _extraSources = true;

  @override
  void initState() {
    super.initState();
    GameBoxPreferences.scrapeExtraSources().then((value) {
      if (mounted) setState(() => _extraSources = value);
    });
  }

  Future<void> _setExtraSources(bool value) async {
    setState(() => _extraSources = value);
    await GameBoxPreferences.setScrapeExtraSources(value);
  }

  void selectItem(int index) {
    const modes = ScrapeModeContent.modes;
    if (index >= 0 && index < modes.length) {
      widget.onModeChanged(modes[index]);
    } else if (index == modes.length) {
      _setExtraSources(!_extraSources);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final modes = [
      {
        'value': 'new_only',
        'title': AppLocale.newContentOnly.getString(context),
        'description': GameBoxLocale.text(context, GameBoxLocale.scrapeModeNewDesc),
      },
      {
        'value': 'all',
        'title': AppLocale.allContent.getString(context),
        'description': GameBoxLocale.text(context, GameBoxLocale.scrapeModeAllDesc),
      },
      {
        'value': 'faces_only',
        'title': GameBoxLocale.text(context, GameBoxLocale.scrapeModeFacesOnly),
        'description': GameBoxLocale.text(context, GameBoxLocale.scrapeModeFacesOnlyDesc),
      },
    ];
    final toggleFocused = widget.isContentFocused && widget.selectedContentIndex == modes.length;

    return SingleChildScrollView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SettingsTitle(
            title: AppLocale.scrapeMode.getString(context),
            subtitle: AppLocale.scrapeModeSub.getString(context),
          ),
          SizedBox(height: 12.r),
          ...modes.asMap().entries.map((entry) {
            final index = entry.key;
            final mode = entry.value;
            final isFocused =
                widget.isContentFocused && widget.selectedContentIndex == index;

            return Padding(
              padding: EdgeInsets.only(bottom: 8.r),
              child: CustomRadioButton<String>(
                title: mode['title']!,
                subtitle: mode['description'],
                value: mode['value']!,
                groupValue: widget.currentMode,
                onChanged: (value) {
                  if (value != null) {
                    widget.onModeChanged(value);
                  }
                },
                isFocused: isFocused,
              ),
            );
          }),
          SizedBox(height: 4.r),
          Container(
            padding: EdgeInsets.symmetric(horizontal: 12.r, vertical: 6.r),
            decoration: BoxDecoration(
              color: LiquidGlassTheme.of(context).fill(context, GlassRole.bubble),
              borderRadius: BorderRadius.circular(8.r),
              border: Border.all(
                color: toggleFocused ? theme.colorScheme.primary : Colors.transparent,
                width: 2,
              ),
            ),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        GameBoxLocale.text(context, GameBoxLocale.scrapeExtraSources),
                        style: theme.textTheme.bodyLarge?.copyWith(
                          fontSize: 12.r,
                          fontWeight: FontWeight.w500,
                          color: toggleFocused ? theme.colorScheme.primary : theme.colorScheme.onSurface,
                        ),
                      ),
                      SizedBox(height: 4.r),
                      Text(
                        GameBoxLocale.text(context, GameBoxLocale.scrapeExtraSourcesDesc),
                        style: theme.textTheme.bodyMedium?.copyWith(
                          fontSize: 9.r,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                        ),
                      ),
                    ],
                  ),
                ),
                CustomToggleSwitch(
                  value: _extraSources,
                  onChanged: _setExtraSources,
                  activeColor: theme.colorScheme.primary,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
