import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:provider/provider.dart';

import '../../l10n/console_manager_locale.dart';
import '../../l10n/libretro_locale.dart';
import '../../models/system_model.dart';
import '../../providers/sqlite_config_provider.dart';
import '../../repositories/system_repository.dart';
import '../../services/console_catalog.dart';
import '../../services/embedded_engine_policy.dart';
import '../../services/libretro_core_catalog.dart';
import '../../services/libretro_internal_service.dart';
import '../../services/libretro_main_menu.dart';
import '../../services/logger_service.dart';
import '../../services/melonx_internal_service.dart';
import '../../widgets/confirm_action_dialog.dart';
import '../../widgets/horizontal_swipe.dart';
import '../../widgets/libretro_engine_panel.dart';
import 'libretro_library_actions.dart';
import 'libretro_skin_manager_screen.dart';

/// Which consoles the Consoles tab lists.
enum ConsoleListFilter { all, shown, hidden }

/// The consoles tab of the main bar (iOS), extended to every console in
/// Build 448: NeoStation's library (its console folders, or a library moved
/// into it), then every console the app runs — the embedded engines
/// (libretro cores, Dolphin, ARMSX2, RPCS3) and the external
/// apps (MeloNX, RetroArch) — each with:
///
/// - its main-menu visibility switch (shown, or hidden like Settings ›
///   Systems does; a console without games is added and remembered). A
///   hidden console keeps its games, covers, saves and settings;
/// - the switch of its built-in engine when it has one. Off, its games take
///   the RetroArch app when it can run them, otherwise launch nothing with
///   an explicit message; Settings › General › "Use built-in emulators"
///   turns every engine off without touching these switches;
/// - for libretro consoles, game import and skins (and the 3DS system page).
///
/// "Show all" and "Restore defaults" act on every listed console, after a
/// confirmation. A console needs no game to be listed or shown.
class LibretroConsolesScreen extends StatefulWidget {
  const LibretroConsolesScreen({
    super.key,
    this.inMainBar = false,
    this.onPreviousTab,
    this.onNextTab,
    this.mainMenu,
    this.policy,
  });

  /// Shown as a main-bar tab under the header (no app bar); LB/RB switch
  /// tabs through [onPreviousTab] and [onNextTab]. Otherwise a pushed page.
  final bool inMainBar;
  final VoidCallback? onPreviousTab;
  final VoidCallback? onNextTab;

  /// Main-menu store; [LibretroMainMenu.instance] when null.
  final LibretroMainMenu? mainMenu;

  /// Built-in engine switches; [EmbeddedEnginePolicy.instance] when null.
  final EmbeddedEnginePolicy? policy;

  @override
  State<LibretroConsolesScreen> createState() => _LibretroConsolesScreenState();
}

class _LibretroConsolesScreenState extends State<LibretroConsolesScreen>
    with LibretroPageNavigation<LibretroConsolesScreen> {
  static final _log = LoggerService.instance;

  /// Console whose import is running; one import at a time.
  String? _importing;

  /// Library action running ('folders' or 'move'), and the move's progress.
  String? _libraryAction;
  int _moveDone = 0;
  int _moveTotal = 0;

  /// Console whose visibility or engine is being changed.
  String? _changing;

  /// "Show all" or "Restore defaults" running.
  String? _bulk;

  ConsoleListFilter _filter = ConsoleListFilter.all;

  /// Libretro consoles whose core ships in this build; null until known (or
  /// when the build could not be asked), which shows every console as
  /// available.
  Set<String>? _bundled;
  bool _melonxAvailable = false;

  /// Captured while the page is shown, so the outcome of an operation is
  /// still announced, in the user's language, after a tab switch disposed
  /// the page.
  ScaffoldMessengerState? _messenger;
  Locale _locale = const Locale('en');

  LibretroMainMenu get _mainMenu => widget.mainMenu ?? LibretroMainMenu.instance;
  EmbeddedEnginePolicy get _policy => widget.policy ?? EmbeddedEnginePolicy.instance;

  bool get _busy =>
      _importing != null || _libraryAction != null || _changing != null || _bulk != null;

  String _t(String key) => LibretroLocale.forLocale(_locale, key);
  String _f(String key, Map<String, Object?> values) => LibretroLocale.format(_locale, key, values);
  String _c(String key) => ConsoleManagerLocale.forLocale(_locale, key);
  String _cf(String key, Map<String, Object?> values) => ConsoleManagerLocale.format(_locale, key, values);

  void _notice(String message) {
    final messenger = _messenger;
    if (messenger == null || !messenger.mounted) return;
    messenger.showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  void initState() {
    super.initState();
    _policy.addListener(_policyChanged);
    unawaited(_policy.load());
    _mainMenu.bundledConsoles().then((consoles) {
      if (mounted && consoles != null) setState(() => _bundled = consoles);
    });
    MelonxInternalService.runtimeAvailable().then((available) {
      if (mounted) setState(() => _melonxAvailable = available);
    });
  }

  @override
  void didUpdateWidget(covariant LibretroConsolesScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    final previous = oldWidget.policy ?? EmbeddedEnginePolicy.instance;
    if (!identical(previous, _policy)) {
      previous.removeListener(_policyChanged);
      _policy.addListener(_policyChanged);
    }
  }

  @override
  void dispose() {
    _policy.removeListener(_policyChanged);
    super.dispose();
  }

  void _policyChanged() {
    if (mounted) setState(() {});
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _messenger = ScaffoldMessenger.maybeOf(context);
    _locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
  }

  @override
  VoidCallback? get libretroPreviousTab => widget.inMainBar ? () => _switchTab(widget.onPreviousTab) : null;

  @override
  VoidCallback? get libretroNextTab => widget.inMainBar ? () => _switchTab(widget.onNextTab) : null;

  /// Leaving the tab disposes the page: the controller keeps it while an
  /// import, a library action or a change of the main menu is running.
  void _switchTab(VoidCallback? switchTab) {
    if (_busy) return;
    switchTab?.call();
  }

  /// A libretro console whose core is missing from this build.
  bool _unavailable(ConsoleEntry entry) {
    if (entry.engine == ConsoleEngine.melonx) return !_melonxAvailable;
    final bundled = _bundled;
    if (bundled == null || entry.engine != ConsoleEngine.libretro) return false;
    final console = entry.libretro;
    if (console != null) return !bundled.contains(console.id);
    // Systems of their own on a console's core (the Pico on Mega Drive).
    final binding = LibretroCoreCatalog.bindingFor(entry.importSystem);
    return binding == null || !bundled.contains(binding.console);
  }

  /// The system games of [console] are imported into, from the provider's
  /// systems (the database when they are not loaded yet).
  Future<SystemModel?> _importSystem(SqliteConfigProvider provider, LibretroConsole console) async {
    for (final system in provider.availableSystems) {
      if (system.id == console.importSystem) return system;
    }
    try {
      return await SystemRepository.getSystemById(console.importSystem);
    } catch (error) {
      _log.w('Libretro import system ${console.importSystem} unavailable: $error');
      return null;
    }
  }

  /// The system whose folder received the games ([LibretroImportResult.systemFolder]).
  Future<SystemModel?> _rescanTarget(
    SqliteConfigProvider provider,
    String systemFolder,
    SystemModel? imported,
  ) async {
    if (imported != null && LibretroInternalService.systemKey(imported) == systemFolder) return imported;
    for (final system in provider.availableSystems) {
      if (LibretroInternalService.systemKey(system) == systemFolder) return system;
    }
    try {
      return await SystemRepository.getSystemByFolderName(systemFolder);
    } catch (error) {
      _log.w('Libretro system folder $systemFolder unavailable: $error');
      return null;
    }
  }

  /// Imported games go to one of the user's library folders, then only the
  /// receiving system is rescanned. NeoStation's own `roms` folder received
  /// them only when no library folder was registered ([createdLibraryRoot]):
  /// it is registered first. Returns the failure detail when that
  /// registration did not hold.
  Future<String?> _refreshLibrary(
    SqliteConfigProvider provider,
    SystemModel? system,
    String? createdLibraryRoot,
  ) async {
    if (createdLibraryRoot != null && !provider.config.romFolders.contains(createdLibraryRoot)) {
      await provider.addRomFolder(createdLibraryRoot, scan: false);
      // addRomFolder reports a failed save through `error` only: never
      // announce games the library cannot list.
      if (!provider.config.romFolders.contains(createdLibraryRoot)) return provider.error ?? createdLibraryRoot;
    }
    if (system != null) {
      await provider.rescanSystemSilent(system);
    } else {
      await provider.scanSystems();
    }
    return null;
  }

  Future<void> _importGames(LibretroConsole console) async {
    if (_busy) return;
    final provider = context.read<SqliteConfigProvider>();
    setState(() => _importing = console.id);
    try {
      final system = await _importSystem(provider, console);
      if (!mounted) return;
      final destination = await chooseLibretroImportDestination(
        context,
        systemFolder: system != null ? LibretroInternalService.systemKey(system) : console.importSystem,
        registeredRoots: provider.config.romFolders,
        folderAliases: system == null ? const <String>[] : <String>[system.folderName, ...system.folders],
      );
      if (destination.unavailable) {
        _notice(_t('importLibraryUnavailable'));
        return;
      }
      if (destination.cancelled || !mounted) return;
      pausePageNavigation();
      final result = await LibretroInternalService.importGamesForConsole(
        console.id,
        system: system,
        library: destination.library,
      );
      resumePageNavigation();
      if (result.imported > 0) {
        final target = await _rescanTarget(provider, result.systemFolder, system);
        final failure = await _refreshLibrary(provider, target, result.createdLibraryRoot);
        _notice(
          failure == null
              ? _f('gamesImported', {'count': result.imported})
              : _f('importFailed', {'error': failure}),
        );
      }
      if (result.alreadyPresent > 0) _notice(_f('importAlreadyPresent', {'count': result.alreadyPresent}));
      if (result.rejected > 0) _notice(_t('gamesRejected'));
    } catch (error) {
      _log.w('Libretro import failed for ${console.id}: $error');
      _notice(_f('importFailed', {'error': error}));
    } finally {
      resumePageNavigation();
      if (mounted) setState(() => _importing = null);
    }
  }

  Future<void> _createFolders() async {
    if (_busy) return;
    final provider = context.read<SqliteConfigProvider>();
    setState(() => _libraryAction = 'folders');
    try {
      await createNeoStationConsoleFolders(provider);
      _notice(_t('libraryFoldersCreated'));
    } catch (error) {
      _log.w('Console folders not created: $error');
      _notice(_f('libraryActionFailed', {'error': error}));
    } finally {
      if (mounted) setState(() => _libraryAction = null);
    }
  }

  Future<void> _moveLibrary() async {
    if (_busy) return;
    final provider = context.read<SqliteConfigProvider>();
    setState(() {
      _libraryAction = 'move';
      _moveDone = 0;
      _moveTotal = 0;
    });
    pausePageNavigation();
    try {
      final outcome = await moveLibraryIntoNeoStation(
        provider,
        confirm: (folder) async {
          resumePageNavigation();
          if (!mounted) return false;
          return ConfirmActionDialog.show(
            context,
            title: _t('libraryMoveConfirmTitle'),
            body: _f('libraryMoveConfirmBody', {'folder': folder}),
            confirmLabel: _t('libraryMoveConfirm'),
            icon: Icons.drive_file_move_outline,
          );
        },
        onProgress: (done, total) {
          if (mounted) {
            setState(() {
              _moveDone = done;
              _moveTotal = total;
            });
          }
        },
      );
      if (outcome == null) return;
      final move = outcome.move;
      _notice(
        move.total == 0
            ? _f('libraryMoveNothing', {'folder': outcome.source})
            : _f('libraryMoved', {
                'moved': move.moved + move.notRemoved,
                'kept': move.alreadyPresent,
                'failed': move.failed,
              }),
      );
    } catch (error) {
      _log.w('Library move failed: $error');
      _notice(_f('libraryActionFailed', {'error': error}));
    } finally {
      resumePageNavigation();
      if (mounted) setState(() => _libraryAction = null);
    }
  }

  Widget _buildLibrary(BuildContext context) {
    final theme = Theme.of(context);
    final busy = _busy;
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.folder_special_outlined, color: theme.colorScheme.primary),
                const SizedBox(width: 12),
                Expanded(child: Text(_t('libraryTitle'), style: theme.textTheme.titleMedium)),
                if (_libraryAction != null)
                  const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
            const SizedBox(height: 6),
            Text(
              _libraryAction == 'move' && _moveTotal > 0
                  ? _f('libraryMoving', {'done': _moveDone, 'total': _moveTotal})
                  : _t('libraryIntro'),
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                LibretroFocusRing(
                  child: FilledButton.tonalIcon(
                    key: const ValueKey('libretro-library-create-folders'),
                    onPressed: busy ? null : _createFolders,
                    icon: const Icon(Icons.create_new_folder_outlined),
                    label: Text(_t('libraryCreateFolders')),
                  ),
                ),
                LibretroFocusRing(
                  child: OutlinedButton.icon(
                    key: const ValueKey('libretro-library-move'),
                    onPressed: busy ? null : _moveLibrary,
                    icon: const Icon(Icons.drive_file_move_outline),
                    label: Text(_t('libraryMove')),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  /// Shows or hides [entry] in the main menu; Settings › Systems follows.
  Future<void> _setVisible(ConsoleEntry entry, bool visible) async {
    if (_busy) return;
    final provider = context.read<SqliteConfigProvider>();
    setState(() => _changing = entry.id);
    try {
      final result = visible
          ? await _mainMenu.showEntry(entry, provider)
          : await _mainMenu.hideEntry(entry, provider);
      switch (result.status) {
        case LibretroMainMenuAddStatus.added:
        case LibretroMainMenuAddStatus.shown:
        case LibretroMainMenuAddStatus.alreadyPresent:
        case LibretroMainMenuAddStatus.inProgress:
          break;
        case LibretroMainMenuAddStatus.systemUnknown:
          _notice(_t('consoleSystemUnknown'));
        case LibretroMainMenuAddStatus.failed:
          _log.w('Console ${entry.id} visibility not changed: ${result.error}');
          _notice(_cf(ConsoleManagerLocale.changeFailed, {'error': result.error ?? ''}));
      }
    } finally {
      if (mounted) setState(() => _changing = null);
    }
  }

  /// The console's own built-in engine switch.
  Future<void> _setEngine(ConsoleEntry entry, bool enabled) async {
    if (_busy) return;
    setState(() => _changing = entry.id);
    try {
      if (!await _policy.setConsoleEnabled(entry.id, enabled)) {
        _notice(_cf(ConsoleManagerLocale.changeFailed, {'error': EmbeddedEnginePolicy.disabledPreferenceKey}));
      }
    } finally {
      if (mounted) setState(() => _changing = null);
    }
  }

  Future<void> _showAll() async {
    if (_busy) return;
    final provider = context.read<SqliteConfigProvider>();
    final missing = <ConsoleEntry>[
      for (final entry in ConsoleCatalog.entries)
        if (!LibretroMainMenu.stateOfEntry(entry, provider.detectedSystems, provider.hiddenSystemFolders).isPresent)
          entry,
    ];
    if (missing.isEmpty) {
      _notice(_c(ConsoleManagerLocale.nothingToShow));
      return;
    }
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: _c(ConsoleManagerLocale.showAllTitle),
      body: _cf(ConsoleManagerLocale.showAllBody, {'count': missing.length}),
      confirmLabel: _c(ConsoleManagerLocale.showAll),
      icon: Icons.visibility_outlined,
    );
    if (!confirmed || !mounted) return;
    setState(() => _bulk = 'showAll');
    try {
      final result = await _mainMenu.showAll(missing, provider);
      _notice(_cf(ConsoleManagerLocale.showAllDone, {'count': result.shown}));
      if (result.failed.isNotEmpty) {
        _notice(_cf(ConsoleManagerLocale.changeFailed, {'error': result.failed.join(', ')}));
      }
    } catch (error) {
      _log.w('Show all consoles failed: $error');
      _notice(_cf(ConsoleManagerLocale.changeFailed, {'error': error}));
    } finally {
      if (mounted) setState(() => _bulk = null);
    }
  }

  Future<void> _restoreDefaults() async {
    if (_busy) return;
    final provider = context.read<SqliteConfigProvider>();
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: _c(ConsoleManagerLocale.restoreTitle),
      body: _c(ConsoleManagerLocale.restoreBody),
      confirmLabel: _c(ConsoleManagerLocale.restoreDefaults),
      icon: Icons.settings_backup_restore,
    );
    if (!confirmed || !mounted) return;
    setState(() => _bulk = 'restore');
    try {
      final result = await _mainMenu.restoreDefaults(ConsoleCatalog.entries, provider);
      final engines = await _policy.enableAllConsoles();
      if (result.failed.isEmpty && engines) {
        _notice(_c(ConsoleManagerLocale.restoreDone));
      } else {
        _notice(_cf(ConsoleManagerLocale.changeFailed, {
          'error': <String>[
            ...result.failed,
            if (!engines) EmbeddedEnginePolicy.disabledPreferenceKey,
          ].join(', '),
        }));
      }
    } catch (error) {
      _log.w('Console defaults not restored: $error');
      _notice(_cf(ConsoleManagerLocale.changeFailed, {'error': error}));
    } finally {
      if (mounted) setState(() => _bulk = null);
    }
  }

  Future<void> _openSkins(LibretroConsole console) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => LibretroSkinManagerScreen(console: console.id)),
    );
  }

  Future<void> _open3dsSystem() => LibretroEngineSettingsPanel.pushPage(
        context,
        LibretroEnginePage.systemData3ds,
        '3ds',
      );

  Future<void> _openResolution(LibretroConsole console) => LibretroEngineSettingsPanel.pushPage(
        context,
        LibretroEnginePage.resolution,
        console.id,
      );

  bool _matches(LibretroMainMenuState state) => switch (_filter) {
        ConsoleListFilter.all => true,
        ConsoleListFilter.shown => state.isPresent,
        ConsoleListFilter.hidden => state.isHidden,
      };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final provider = context.watch<SqliteConfigProvider>();
    final states = <ConsoleEntry, LibretroMainMenuState>{
      for (final entry in ConsoleCatalog.entries)
        entry: LibretroMainMenu.stateOfEntry(entry, provider.detectedSystems, provider.hiddenSystemFolders),
    };
    final embedded = <ConsoleEntry>[
      for (final entry in ConsoleCatalog.entries)
        if (entry.hasEmbeddedEngine && _matches(states[entry]!)) entry,
    ];
    final external = <ConsoleEntry>[
      for (final entry in ConsoleCatalog.entries)
        if (!entry.hasEmbeddedEngine && _matches(states[entry]!)) entry,
    ];
    final list = Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 920),
        // Every console is built (no lazy list), so the D-pad can always
        // reach the next one.
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (widget.inMainBar)
                Padding(
                  padding: const EdgeInsets.fromLTRB(4, 0, 4, 6),
                  child: Text(_c(ConsoleManagerLocale.tabTitle), style: theme.textTheme.titleLarge),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
                child: Text(
                  _c(ConsoleManagerLocale.tabIntro),
                  style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
              if (_policy.loaded && !_policy.useEmbedded) _buildGlobalOff(context),
              _buildToolbar(context),
              const SizedBox(height: 12),
              _buildLibrary(context),
              if (embedded.isNotEmpty) ...[
                _buildSection(context, _c(ConsoleManagerLocale.sectionEmbedded)),
                for (final entry in embedded) _buildConsole(context, entry, states[entry]!),
              ],
              if (external.isNotEmpty) ...[
                _buildSection(context, _c(ConsoleManagerLocale.sectionExternal)),
                for (final entry in external) _buildConsole(context, entry, states[entry]!),
              ],
              if (embedded.isEmpty && external.isEmpty)
                Padding(
                  key: const ValueKey('consoles-no-match'),
                  padding: const EdgeInsets.all(24),
                  child: Text(
                    _c(ConsoleManagerLocale.noMatch),
                    textAlign: TextAlign.center,
                    style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
    if (widget.inMainBar) {
      // Under the global header, clear of the notch like the other tabs.
      final safe = MediaQuery.viewPaddingOf(context);
      // Own the swipe recognizer inside the app-level one so this page can
      // preserve its existing busy guard: imports/library mutations keep both
      // LB/RB and touch swipes from disposing the page mid-operation.
      return libretroPage(
        HorizontalSwipe(
          key: const ValueKey('consoles-main-tab-swipe'),
          onSwipeLeft: () => _switchTab(widget.onNextTab),
          onSwipeRight: () => _switchTab(widget.onPreviousTab),
          canSwipeLeft: () => !_busy,
          canSwipeRight: () => !_busy,
          distanceThreshold: 64,
          velocityThreshold: 450,
          dragFeedback: true,
          child: Material(
            type: MaterialType.transparency,
            child: Padding(
              padding: EdgeInsets.fromLTRB(safe.left, 46.r, safe.right, 0),
              child: list,
            ),
          ),
        ),
      );
    }
    return libretroPage(Scaffold(
      appBar: libretroPageAppBar(context, _c(ConsoleManagerLocale.tabTitle)),
      body: SafeArea(child: list),
    ));
  }

  Widget _buildGlobalOff(BuildContext context) {
    final theme = Theme.of(context);
    return Card(
      key: const ValueKey('consoles-global-off'),
      color: theme.colorScheme.secondaryContainer,
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.info_outline, color: theme.colorScheme.onSecondaryContainer),
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                _c(ConsoleManagerLocale.globalOff),
                style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSecondaryContainer),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildToolbar(BuildContext context) {
    final busy = _busy;
    Widget filter(ConsoleListFilter value, String key) => LibretroFocusRing(
          child: ChoiceChip(
            key: ValueKey('consoles-filter-${value.name}'),
            label: Text(_c(key)),
            selected: _filter == value,
            onSelected: (_) => setState(() => _filter = value),
          ),
        );
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        filter(ConsoleListFilter.all, ConsoleManagerLocale.filterAll),
        filter(ConsoleListFilter.shown, ConsoleManagerLocale.filterShown),
        filter(ConsoleListFilter.hidden, ConsoleManagerLocale.filterHidden),
        LibretroFocusRing(
          child: FilledButton.tonalIcon(
            key: const ValueKey('consoles-show-all'),
            onPressed: busy ? null : _showAll,
            icon: _bulk == 'showAll'
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.visibility_outlined),
            label: Text(_c(ConsoleManagerLocale.showAll)),
          ),
        ),
        LibretroFocusRing(
          child: OutlinedButton.icon(
            key: const ValueKey('consoles-restore-defaults'),
            onPressed: busy ? null : _restoreDefaults,
            icon: _bulk == 'restore'
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.settings_backup_restore),
            label: Text(_c(ConsoleManagerLocale.restoreDefaults)),
          ),
        ),
      ],
    );
  }

  Widget _buildSection(BuildContext context, String title) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.fromLTRB(4, 8, 4, 8),
      child: Text(
        title,
        style: theme.textTheme.titleSmall?.copyWith(color: theme.colorScheme.primary, fontWeight: FontWeight.w700),
      ),
    );
  }

  Widget _buildStatus(BuildContext context, IconData icon, String text, {Key? key, Color? color}) {
    final theme = Theme.of(context);
    final tint = color ?? theme.colorScheme.onSurfaceVariant;
    return Padding(
      key: key,
      padding: const EdgeInsets.only(top: 3),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 1),
            child: Icon(icon, size: 15, color: tint),
          ),
          const SizedBox(width: 6),
          Expanded(child: Text(text, style: theme.textTheme.bodySmall?.copyWith(color: tint))),
        ],
      ),
    );
  }

  String _engineLine(ConsoleEntry entry) {
    switch (entry.engine) {
      case ConsoleEngine.libretro:
        final binding = LibretroCoreCatalog.bindingFor(entry.importSystem);
        final core = binding == null ? null : LibretroCoreCatalog.cores[binding.coreId];
        return _cf(ConsoleManagerLocale.engineBuiltIn, {
          'engine': core == null ? 'libretro' : '${core.displayName} (libretro)',
        });
      case ConsoleEngine.dolphin:
        return _cf(ConsoleManagerLocale.engineBuiltIn, {'engine': 'Dolphin'});
      case ConsoleEngine.armsx2:
        return _cf(ConsoleManagerLocale.engineBuiltIn, {'engine': 'ARMSX2'});
      case ConsoleEngine.rpcs3:
        return _cf(ConsoleManagerLocale.engineBuiltIn, {'engine': 'RPCS3'});
      case ConsoleEngine.melonx:
        return _cf(ConsoleManagerLocale.engineBuiltIn, {'engine': 'MeloNX'});
      case ConsoleEngine.retroarch:
        return _cf(ConsoleManagerLocale.engineExternal, {'app': 'RetroArch'});
    }
  }

  String _fallbackLine(ConsoleEntry entry) {
    if (entry.engine == ConsoleEngine.armsx2) return _c(ConsoleManagerLocale.fallbackRetroArchPs2);
    if (entry.retroArchFallback) return _c(ConsoleManagerLocale.fallbackRetroArch);
    return _c(ConsoleManagerLocale.fallbackNone);
  }

  Widget _logo(BuildContext context, ConsoleEntry entry) {
    final tint = Theme.of(context).colorScheme.onSurface;
    return SizedBox(
      width: 44,
      height: 30,
      child: Image.asset(
        entry.logoAsset,
        color: tint,
        fit: BoxFit.contain,
        errorBuilder: (context, error, stack) => Icon(Icons.sports_esports_outlined, color: tint),
      ),
    );
  }

  Widget _switch(
    BuildContext context, {
    required Key key,
    required String label,
    required bool value,
    required ValueChanged<bool>? onChanged,
  }) {
    final theme = Theme.of(context);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: theme.textTheme.labelSmall?.copyWith(color: theme.colorScheme.onSurfaceVariant)),
        LibretroFocusRing(
          child: Switch(
            key: key,
            value: value,
            onChanged: onChanged,
          ),
        ),
      ],
    );
  }

  Widget _buildConsole(BuildContext context, ConsoleEntry entry, LibretroMainMenuState state) {
    final theme = Theme.of(context);
    final busy = _busy;
    final changing = _changing == entry.id || _importing == entry.id;
    final unavailable = _unavailable(entry);
    final console = entry.libretro;
    final engineOn = _policy.isConsoleEnabled(entry.id);
    final engineAllowed = _policy.allows(entry.id);
    final switches = <Widget>[
      _switch(
        context,
        key: ValueKey('console-visible-${entry.id}'),
        label: _c(ConsoleManagerLocale.visibleLabel),
        value: state.isPresent,
        onChanged: busy ? null : (value) => _setVisible(entry, value),
      ),
      if (entry.hasEmbeddedEngine)
        _switch(
          context,
          key: ValueKey('console-engine-${entry.id}'),
          label: _c(ConsoleManagerLocale.engineLabel),
          // The console's own choice, kept while the global switch is off.
          value: engineOn && !unavailable,
          onChanged: busy || unavailable || !_policy.useEmbedded ? null : (value) => _setEngine(entry, value),
        ),
    ];
    final details = <Widget>[
      Row(
        children: [
          Expanded(child: Text(entry.name, style: theme.textTheme.titleMedium)),
          if (changing) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
        ],
      ),
      _buildStatus(context, entry.hasEmbeddedEngine ? Icons.memory : Icons.open_in_new, _engineLine(entry)),
      if (state.isPresent)
        _buildStatus(
          context,
          Icons.check_circle_outline,
          _cf(ConsoleManagerLocale.stateShown, {'systems': state.systemNames}),
          key: ValueKey('console-shown-${entry.id}'),
        )
      else if (state.isHidden)
        _buildStatus(
          context,
          Icons.visibility_off_outlined,
          _cf(ConsoleManagerLocale.stateHidden, {'systems': state.systemNames}),
          key: ValueKey('console-hidden-${entry.id}'),
        )
      else
        _buildStatus(
          context,
          Icons.remove_circle_outline,
          _c(ConsoleManagerLocale.stateAbsent),
          key: ValueKey('console-absent-${entry.id}'),
        ),
      if (unavailable)
        _buildStatus(
          context,
          Icons.block,
          _c(ConsoleManagerLocale.unavailable),
          key: ValueKey('console-unavailable-${entry.id}'),
        )
      else if (entry.hasEmbeddedEngine && !engineAllowed)
        _buildStatus(
          context,
          Icons.power_settings_new,
          _fallbackLine(entry),
          key: ValueKey('console-engine-off-${entry.id}'),
          color: theme.colorScheme.tertiary,
        ),
    ];
    final actions = <Widget>[
      if (console != null) ...[
        LibretroFocusRing(
          child: FilledButton.tonalIcon(
            key: ValueKey('libretro-console-import-${console.id}'),
            onPressed: busy ? null : () => _importGames(console),
            icon: const Icon(Icons.file_upload_outlined),
            label: Text(_t('importGames')),
          ),
        ),
        LibretroFocusRing(
          child: OutlinedButton.icon(
            key: ValueKey('libretro-console-skins-${console.id}'),
            onPressed: () => _openSkins(console),
            icon: const Icon(Icons.palette_outlined),
            label: Text(_t('skins')),
          ),
        ),
        LibretroFocusRing(
          child: OutlinedButton.icon(
            key: ValueKey('libretro-console-resolution-${console.id}'),
            onPressed: busy ? null : () => _openResolution(console),
            icon: const Icon(Icons.high_quality_outlined),
            label: Text(_t('resolutionPage')),
          ),
        ),
        if (console.id == '3ds')
          LibretroFocusRing(
            child: OutlinedButton.icon(
              key: const ValueKey('libretro-console-system-3ds'),
              onPressed: busy ? null : _open3dsSystem,
              icon: const Icon(Icons.settings_applications_outlined),
              label: Text(_t('system3dsTitle')),
            ),
          ),
      ],
    ];
    return Card(
      key: ValueKey('console-${entry.id}'),
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 10, 10, 10),
        child: LayoutBuilder(
          builder: (context, constraints) {
            // Phones in portrait put the switches under the details.
            final wide = constraints.maxWidth >= 520;
            final header = Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Padding(padding: const EdgeInsets.only(top: 2, right: 12), child: _logo(context, entry)),
                Expanded(child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: details)),
                if (wide) ...[
                  const SizedBox(width: 8),
                  for (final item in switches) Padding(padding: const EdgeInsets.only(left: 4), child: item),
                ],
              ],
            );
            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                header,
                if (!wide)
                  Padding(
                    padding: const EdgeInsets.only(top: 6),
                    child: Wrap(spacing: 16, runSpacing: 4, children: switches),
                  ),
                if (actions.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Wrap(spacing: 8, runSpacing: 8, children: actions),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }
}
