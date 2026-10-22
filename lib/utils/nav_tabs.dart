import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/libretro_locale.dart';
import 'package:neostation/l10n/neoplay_locale.dart';
import 'package:neostation/models/config_model.dart';

/// Identity of a top-level navigation tab (the L1/R1 strip in the header).
///
/// The ordinal **is** the canonical tab index used by `AppScreenState`
/// (`_selectedTabIndex`, `_buildCurrentTabContent`, the secondary-display tab
/// names). Append new tabs at the end — inserting one renumbers every existing
/// tab and silently repoints all of that dispatch. Where a tab is *drawn* is a
/// separate matter: see [navTabDisplayOrder].
enum NavTab {
  systems,
  search,
  achievements,
  scraper,
  settings,
  library,
  consoles,
  airplay,
}

/// Catalog a tab's [NavTabSpec.labelKey] belongs to.
enum NavTabLabelCatalog {
  /// [AppLocale] key, resolved through flutter_localization.
  app,

  /// [LibretroLocale] key (the embedded-console texts).
  libretro,
  neoplay,
}

/// Static description of one navigation tab: how it is drawn, whether the user
/// may hide it, and how that preference is read and written.
class NavTabSpec {
  const NavTabSpec({
    required this.icon,
    required this.labelKey,
    this.iconData,
    this.badgeIconData,
    this.tintIcon = true,
    this.labelCatalog = NavTabLabelCatalog.app,
    this.available,
    this.hidden,
    this.withHidden,
    this.settingsTitleKey,
    this.settingsSubtitleKey,
  });

  /// Asset drawn in the header strip. Use [iconData] when no asset exists.
  final String icon;

  /// Material symbol fallback for tabs with no webp asset.
  final IconData? iconData;

  /// Small symbol drawn at the top right of [iconData] (the "+" of the
  /// consoles tab), in the same tint.
  final IconData? badgeIconData;

  /// Whether the asset should inherit the active foreground color.
  final bool tintIcon;

  /// Key of the tab's display name, in [labelCatalog].
  final String labelKey;

  /// Catalog [labelKey] is read from.
  final NavTabLabelCatalog labelCatalog;

  /// Whether the tab exists on this platform; `null` means everywhere. Unlike
  /// [hidden] it is not a user preference: an unavailable tab is never drawn
  /// nor offered as a toggle.
  final bool Function()? available;

  /// Reads this tab's "hidden" preference. `null` means the tab can never be
  /// hidden — that is the default for any tab not wired up here.
  final bool Function(ConfigModel config)? hidden;

  /// Returns a copy of [config] with this tab's "hidden" preference set.
  final ConfigModel Function(ConfigModel config, bool hidden)? withHidden;

  /// [AppLocale] keys for this tab's row in General settings.
  final String? settingsTitleKey;
  final String? settingsSubtitleKey;

  /// Whether the tab exists on this platform (see [available]).
  bool get isAvailable => available?.call() ?? true;

  /// Whether the user can toggle this tab's visibility.
  bool get isHidable => hidden != null && withHidden != null;
}

/// Fallback for a [NavTab] with no entry in [navTabSpecs].
///
/// It has no [NavTabSpec.hidden] predicate, so an unregistered tab renders and
/// stays permanently visible rather than disappearing — the safe failure for a
/// tab added in a future version before its toggle is wired up.
const NavTabSpec _fallbackSpec = NavTabSpec(
  icon: 'assets/images/icons/grids.webp',
  labelKey: AppLocale.systems,
);

/// Systems and Settings are deliberately absent a [NavTabSpec.hidden]
/// predicate: Systems is the home tab, and Settings must stay reachable or a
/// user who hid everything else could never turn it back on. The consoles tab
/// has none either: it is how embedded consoles reach the main menu.
const Map<NavTab, NavTabSpec> navTabSpecs = {
  NavTab.systems: NavTabSpec(
    icon: 'assets/images/icons/grids.webp',
    labelKey: AppLocale.systems,
  ),
  NavTab.search: NavTabSpec(
    icon: '',
    labelKey: AppLocale.searchTitle,
    iconData: Symbols.search_rounded,
    hidden: _hideTabSearch,
    withHidden: _withHideTabSearch,
    settingsTitleKey: AppLocale.showSearchTab,
    settingsSubtitleKey: AppLocale.showSearchTabSubtitle,
  ),
  NavTab.achievements: NavTabSpec(
    icon: 'assets/images/icons/enhance-prize.webp',
    labelKey: AppLocale.achievements,
    hidden: _hideTabAchievements,
    withHidden: _withHideTabAchievements,
    settingsTitleKey: AppLocale.showAchievementsTab,
    settingsSubtitleKey: AppLocale.showAchievementsTabSubtitle,
  ),
  NavTab.scraper: NavTabSpec(
    icon: 'assets/images/icons/box-search.webp',
    labelKey: AppLocale.scraping,
    hidden: _hideTabScraper,
    withHidden: _withHideTabScraper,
    settingsTitleKey: AppLocale.showScraperTab,
    settingsSubtitleKey: AppLocale.showScraperTabSubtitle,
  ),
  NavTab.settings: NavTabSpec(
    icon: 'assets/images/icons/setting.webp',
    labelKey: AppLocale.settings,
  ),
  NavTab.library: NavTabSpec(
    icon: '',
    labelKey: AppLocale.library,
    iconData: Symbols.menu_book_rounded,
  ),
  // Embedded (libretro) consoles to add to the main menu: a console with a
  // "+". The engine exists on iOS only, like the AirPlay cell of the strip.
  NavTab.consoles: NavTabSpec(
    icon: '',
    labelKey: 'consolesTab',
    labelCatalog: NavTabLabelCatalog.libretro,
    iconData: Symbols.sports_esports_rounded,
    badgeIconData: Symbols.add_rounded,
    available: _isIOS,
  ),
  // Append the identity to preserve every stored/external tab index. Its
  // display position is shared by touch, bumpers, keyboard and the header.
  NavTab.airplay: NavTabSpec(
    icon: '',
    labelKey: 'subtitle',
    labelCatalog: NavTabLabelCatalog.neoplay,
    iconData: Icons.airplay_rounded,
    available: _isIOS,
  ),
};

// Torn out as top-level functions so [navTabSpecs] can stay `const`.
bool _hideTabAchievements(ConfigModel c) => c.hideTabAchievements;
bool _hideTabScraper(ConfigModel c) => c.hideTabScraper;
bool _hideTabSearch(ConfigModel c) => c.hideTabSearch;
bool _isIOS() => defaultTargetPlatform == TargetPlatform.iOS;

ConfigModel _withHideTabAchievements(ConfigModel c, bool hidden) =>
    c.copyWith(hideTabAchievements: hidden);
ConfigModel _withHideTabScraper(ConfigModel c, bool hidden) =>
    c.copyWith(hideTabScraper: hidden);
ConfigModel _withHideTabSearch(ConfigModel c, bool hidden) =>
    c.copyWith(hideTabSearch: hidden);

/// Description of [tab], never null — see [_fallbackSpec].
NavTabSpec navTabSpec(NavTab tab) => navTabSpecs[tab] ?? _fallbackSpec;

/// Left-to-right order of the tabs in the header strip, which is also the
/// LB/RB order. It is independent of the canonical [NavTab] indices: the
/// consoles tab is drawn right after Systems although it was appended last.
const List<NavTab> navTabDisplayOrder = [
  NavTab.systems,
  NavTab.consoles,
  NavTab.search,
  NavTab.airplay,
  NavTab.achievements,
  NavTab.scraper,
  NavTab.settings,
  NavTab.library,
];

/// Position of [tab] in [navTabDisplayOrder]. A tab missing from that list
/// (added later without a place) goes after the listed ones, by index.
int navTabDisplayRank(NavTab tab) {
  final rank = navTabDisplayOrder.indexOf(tab);
  return rank >= 0 ? rank : navTabDisplayOrder.length + tab.index;
}

/// [tabs] in display order (see [navTabDisplayOrder]).
List<NavTab> inNavTabDisplayOrder(Iterable<NavTab> tabs) =>
    List<NavTab>.of(tabs)
      ..sort((a, b) => navTabDisplayRank(a).compareTo(navTabDisplayRank(b)));

/// Tabs the user should see, in display order.
///
/// A tab is visible when it exists on this platform and has no registered
/// hide-predicate that says otherwise, so an unregistered (i.e. newly added)
/// tab is visible by default.
List<NavTab> visibleNavTabs(ConfigModel config) => List<NavTab>.unmodifiable(
  inNavTabDisplayOrder(NavTab.values).where((tab) {
    final spec = navTabSpec(tab);
    return spec.isAvailable && !(spec.hidden?.call(config) ?? false);
  }),
);

/// Tabs the user can toggle, in canonical order. Drives the General settings
/// rows, so wiring a future tab's spec is all it takes to give it a toggle.
List<NavTab> hidableNavTabs() => NavTab.values
    .where((tab) => navTabSpec(tab).isAvailable && navTabSpec(tab).isHidable)
    .toList(growable: false);

/// The tab [step] places away from [current] among [visible] (display
/// order), wrapping at both ends, so a hidden tab is skipped rather than
/// selected and immediately bounced. A [current] tab that is not visible
/// (config changed underneath) steps from the start of the strip. Null when
/// nothing is visible.
NavTab? cycleNavTab(List<NavTab> visible, NavTab current, int step) {
  if (visible.isEmpty) return null;
  final position = visible.indexOf(current);
  final from = position == -1 ? 0 : position;
  final length = visible.length;
  return visible[((from + step) % length + length) % length];
}

/// Translated display name of [tab] (accessibility label of its button).
String navTabLabel(BuildContext context, NavTab tab) {
  final spec = navTabSpec(tab);
  return switch (spec.labelCatalog) {
    NavTabLabelCatalog.libretro => LibretroLocale.text(context, spec.labelKey),
    NavTabLabelCatalog.app => spec.labelKey.getString(context),
    NavTabLabelCatalog.neoplay =>
      'AirPlay · ${NeoPlayLocale.get(context, spec.labelKey)}',
  };
}
