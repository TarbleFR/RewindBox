import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../l10n/app_locale.dart';
import '../l10n/embedded_emulator_locale.dart';
import '../l10n/libretro_locale.dart';
import '../screens/libretro/libretro_3ds_system_screen.dart';
import '../screens/libretro/libretro_bios_checker_screen.dart';
import '../screens/libretro/libretro_resolution_screen.dart';
import '../screens/libretro/libretro_skin_manager_screen.dart';
import '../services/libretro_core_catalog.dart';
import '../services/sfx_service.dart';
import '../themes/corner_radii.dart';

/// Pages the embedded engine's settings panel opens. [systemData3ds] (the
/// Nintendo 3DS system settings and data, Build 447) exists for the `3ds`
/// console only; [resolution] (internal resolution of the console's cores,
/// Build 455) for every console.
enum LibretroEnginePage { skins, resolution, systemData3ds, biosChecker }

/// Console whose Emulators tab offers the Nintendo 3DS system page.
const String _console3ds = '3ds';

/// Opens [page] for [console] (a key of [LibretroCoreCatalog.consoles], null
/// when the system has none) and completes when the page is closed.
typedef LibretroEnginePageOpener =
    Future<void> Function(
      BuildContext context,
      LibretroEnginePage page,
      String? console,
    );

/// Identity of the embedded libretro engine ("Embedded RetroArch"), in the
/// same style as the other engines compiled into NeoStation (DolphiniOS,
/// ARMSX2, RPCS3): controller icon, product name, the embedded
/// status with the core that runs the system, and a check.
class LibretroEngineIdentityTile extends StatelessWidget {
  const LibretroEngineIdentityTile({
    super.key,
    required this.systemKey,
    this.active = true,
  });

  /// Canonical catalog key of the system (`LibretroInternalService.systemKey`).
  final String systemKey;

  /// Whether the game (or system) runs in the embedded engine. False for a
  /// game still set to the RetroArch app as an earlier setting, or whose file
  /// is not readable here (known only to the RetroArch app's library): no
  /// check is shown then, since that game opens the RetroArch app.
  final bool active;

  /// "Embedded in NeoStation · Snes9x", or "Embedded in NeoStation ·
  /// Genesis Plus GX (default)" when games of the system may choose another
  /// core. Core names are product names and stay untranslated.
  static String subtitle(BuildContext context, String systemKey) {
    final integrated = EmbeddedEmulatorLocale.integrated(context);
    final cores = LibretroCoreCatalog.coresFor(systemKey);
    if (cores.isEmpty) return integrated;
    final name = cores.first.displayName;
    final core = cores.length > 1
        ? LibretroLocale.formatContext(context, 'coreDefault', {'core': name})
        : name;
    return '$integrated · $core';
  }

  @override
  Widget build(BuildContext context) {
    return ListTile(
      leading: const Icon(Symbols.sports_esports_rounded),
      title: Text(LibretroLocale.text(context, 'engineName')),
      subtitle: Text(subtitle(context, systemKey)),
      trailing: active
          ? Icon(
              Icons.check_circle,
              color: Theme.of(context).colorScheme.primary,
            )
          : null,
    );
  }
}

/// Emulators tab of System Settings for a system run by the embedded libretro
/// engine (Build 440): the engine identity, the console's skins, the BIOS
/// checker filtered on the console, and a reminder that screen format,
/// shaders, controls, cheats and core settings live in the in-game menu.
///
/// The host dialog forwards the controller to [LibretroEngineSettingsPanelState]
/// ([moveUp], [moveDown], [trigger]); touch opens a row directly.
class LibretroEngineSettingsPanel extends StatefulWidget {
  const LibretroEngineSettingsPanel({
    super.key,
    required this.systemKey,
    this.openPage,
  });

  /// Canonical catalog key of the system (`LibretroInternalService.systemKey`).
  final String systemKey;

  /// Opens a page; [pushPage] when null.
  final LibretroEnginePageOpener? openPage;

  /// The page a row opens, filtered on [console].
  static Widget pageFor(LibretroEnginePage page, String? console) =>
      switch (page) {
        LibretroEnginePage.skins => LibretroSkinManagerScreen(console: console!),
        LibretroEnginePage.resolution => LibretroResolutionScreen(console: console!),
        // The page names NeoStation's current language in its "Automatic"
        // entry with the app's own language list.
        LibretroEnginePage.systemData3ds => const Libretro3dsSystemScreen(
          languageNames: AppLocale.supportedLanguages,
        ),
        LibretroEnginePage.biosChecker => LibretroBiosCheckerScreen(
          console: console,
        ),
      };

  /// Pushes [pageFor] above the dialog. The page registers its own controller
  /// layer, so the dialog stops reacting until the page is closed.
  static Future<void> pushPage(
    BuildContext context,
    LibretroEnginePage page,
    String? console,
  ) => Navigator.of(context).push(
    MaterialPageRoute<void>(builder: (_) => pageFor(page, console)),
  );

  @override
  State<LibretroEngineSettingsPanel> createState() =>
      LibretroEngineSettingsPanelState();
}

class LibretroEngineSettingsPanelState
    extends State<LibretroEngineSettingsPanel> {
  final ScrollController _scrollController = ScrollController();
  final Map<LibretroEnginePage, GlobalKey> _rowKeys =
      <LibretroEnginePage, GlobalKey>{};
  int _selected = 0;
  bool _opening = false;

  LibretroConsole? get _console =>
      LibretroCoreCatalog.consoleFor(widget.systemKey);

  /// Rows the controller moves through, in display order: skins and the
  /// internal resolution belong to a console, so their rows exist only when
  /// the system has one; the Nintendo 3DS system page only for that console.
  List<LibretroEnginePage> get pages => <LibretroEnginePage>[
    if (_console != null) LibretroEnginePage.skins,
    if (_console != null) LibretroEnginePage.resolution,
    if (_console?.id == _console3ds) LibretroEnginePage.systemData3ds,
    LibretroEnginePage.biosChecker,
  ];

  /// Index of the highlighted row in [pages].
  int get selectedIndex => _selected;

  @override
  void dispose() {
    _scrollController.dispose();
    super.dispose();
  }

  void moveUp() => _move(-1);

  void moveDown() => _move(1);

  void _move(int delta) {
    final count = pages.length;
    if (count == 0) return;
    setState(() => _selected = (_selected + delta + count) % count);
    _revealSelected();
  }

  /// Opens the highlighted row (controller A / Enter).
  Future<void> trigger() async {
    final rows = pages;
    if (rows.isEmpty) return;
    await open(rows[_selected.clamp(0, rows.length - 1)]);
  }

  /// Opens [page] once: a second press while the page is opening or shown is
  /// ignored.
  Future<void> open(LibretroEnginePage page) async {
    final index = pages.indexOf(page);
    if (index < 0 || _opening) return;
    setState(() {
      _selected = index;
      _opening = true;
    });
    try {
      final opener = widget.openPage ?? LibretroEngineSettingsPanel.pushPage;
      await opener(context, page, _console?.id);
    } finally {
      if (mounted) setState(() => _opening = false);
    }
  }

  void _revealSelected() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final rows = pages;
      if (!mounted || rows.isEmpty) return;
      final rowContext = _rowKeys[rows[_selected]]?.currentContext;
      if (rowContext == null) return;
      Scrollable.ensureVisible(
        rowContext,
        alignment: 0.5,
        duration: const Duration(milliseconds: 200),
        curve: Curves.easeOut,
      );
    });
  }

  ({IconData icon, String title, String subtitle}) _rowText(
    BuildContext context,
    LibretroEnginePage page,
  ) {
    final consoleName = _console?.name ?? '';
    return switch (page) {
      LibretroEnginePage.skins => (
        icon: Symbols.palette_rounded,
        title: LibretroLocale.text(context, 'skins'),
        subtitle: LibretroLocale.formatContext(
          context,
          'engineSkinsSubtitle',
          {'console': consoleName},
        ),
      ),
      LibretroEnginePage.resolution => (
        icon: Symbols.high_quality_rounded,
        title: LibretroLocale.text(context, 'resolutionPage'),
        subtitle: LibretroLocale.formatContext(
          context,
          'engineResolutionSubtitle',
          {'console': consoleName},
        ),
      ),
      LibretroEnginePage.systemData3ds => (
        icon: Symbols.sd_card_rounded,
        title: LibretroLocale.text(context, 'engine3dsSystem'),
        subtitle: LibretroLocale.formatContext(
          context,
          'engine3dsSystemSubtitle',
          {'console': consoleName},
        ),
      ),
      LibretroEnginePage.biosChecker => (
        icon: Symbols.memory_rounded,
        title: LibretroLocale.text(context, 'engineBiosChecker'),
        subtitle: LibretroLocale.formatContext(
          context,
          'engineBiosCheckerSubtitle',
          {'console': consoleName},
        ),
      ),
    };
  }

  Widget _buildRow(BuildContext context, int index, LibretroEnginePage page) {
    final theme = Theme.of(context);
    final selected = index == _selected;
    final text = _rowText(context, page);
    final radius =
        theme.extension<CornerRadii>()?.radiusInternal ??
        BorderRadius.circular(9.r);
    final accent = selected
        ? theme.colorScheme.primary
        : theme.colorScheme.onSurface;
    return Container(
      key: _rowKeys.putIfAbsent(page, GlobalKey.new),
      margin: EdgeInsets.only(bottom: 6.r),
      decoration: BoxDecoration(
        color: selected
            ? theme.colorScheme.primary.withValues(alpha: 0.15)
            : Colors.transparent,
        borderRadius: radius,
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          canRequestFocus: false,
          borderRadius: radius,
          onTap: () {
            SfxService().playNavSound();
            open(page);
          },
          child: Padding(
            padding: EdgeInsets.symmetric(horizontal: 8.r, vertical: 6.r),
            child: Row(
              children: [
                Container(
                  width: 24.r,
                  height: 24.r,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(
                      alpha: selected ? 0.2 : 0.1,
                    ),
                    borderRadius: radius,
                  ),
                  child: Icon(text.icon, size: 14.r, color: accent),
                ),
                SizedBox(width: 10.r),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        text.title,
                        style: TextStyle(
                          fontSize: 12.r,
                          fontWeight: FontWeight.w600,
                          color: accent,
                        ),
                      ),
                      SizedBox(height: 1.r),
                      Text(
                        text.subtitle,
                        style: TextStyle(
                          fontSize: 10.r,
                          color: theme.colorScheme.onSurface.withValues(
                            alpha: 0.6,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                Icon(Symbols.chevron_right_rounded, size: 16.r, color: accent),
              ],
            ),
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final rows = pages;
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.6);
    return SingleChildScrollView(
      controller: _scrollController,
      padding: EdgeInsets.all(12.r),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          LibretroEngineIdentityTile(systemKey: widget.systemKey),
          SizedBox(height: 6.r),
          for (var index = 0; index < rows.length; index++)
            _buildRow(context, index, rows[index]),
          Padding(
            padding: EdgeInsets.fromLTRB(8.r, 6.r, 8.r, 0),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(Symbols.info_rounded, size: 12.r, color: muted),
                SizedBox(width: 6.r),
                Expanded(
                  child: Text(
                    LibretroLocale.text(context, 'engineInGameSettings'),
                    style: TextStyle(fontSize: 10.r, color: muted),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
