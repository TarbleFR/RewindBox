import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:provider/provider.dart';

import '../../l10n/libretro_locale.dart';
import '../../models/system_model.dart';
import '../../providers/sqlite_config_provider.dart';
import '../../repositories/system_repository.dart';
import '../../services/libretro_core_catalog.dart';
import '../../services/libretro_internal_service.dart';
import '../../services/libretro_main_menu.dart';
import '../../services/logger_service.dart';
import '../../widgets/confirm_action_dialog.dart';
import 'libretro_library_actions.dart';
import 'libretro_skin_manager_screen.dart';

/// Embedded consoles (iOS), the body of the main bar's consoles tab (the
/// console with a "+", [inMainBar]): NeoStation's library (its console
/// folders, or a library moved into it), then every console the embedded
/// libretro engine runs, with its place in the main menu, game import and
/// skin management. A console needs no game to be listed or added to the
/// main menu, so the first games of a console (a 3DS, for example) can be
/// imported here, into one of the user's libraries.
class LibretroConsolesScreen extends StatefulWidget {
  const LibretroConsolesScreen({
    super.key,
    this.inMainBar = false,
    this.onPreviousTab,
    this.onNextTab,
    this.mainMenu,
  });

  /// Shown as a main-bar tab under the header (no app bar); LB/RB switch
  /// tabs through [onPreviousTab] and [onNextTab]. Otherwise a pushed page.
  final bool inMainBar;
  final VoidCallback? onPreviousTab;
  final VoidCallback? onNextTab;

  /// Main-menu store; [LibretroMainMenu.instance] when null.
  final LibretroMainMenu? mainMenu;

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

  /// Console being added to the main menu.
  String? _adding;

  /// Consoles whose core ships in this build; null until known (or when the
  /// build could not be asked), which shows every console as available.
  Set<String>? _bundled;

  /// Captured while the page is shown, so the outcome of an operation is
  /// still announced, in the user's language, after a tab switch disposed
  /// the page.
  ScaffoldMessengerState? _messenger;
  Locale _locale = const Locale('en');

  LibretroMainMenu get _mainMenu => widget.mainMenu ?? LibretroMainMenu.instance;

  bool get _busy => _importing != null || _libraryAction != null || _adding != null;

  String _t(String key) => LibretroLocale.forLocale(_locale, key);
  String _f(String key, Map<String, Object?> values) => LibretroLocale.format(_locale, key, values);

  void _notice(String message) {
    final messenger = _messenger;
    if (messenger == null || !messenger.mounted) return;
    messenger.showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  void initState() {
    super.initState();
    _mainMenu.bundledConsoles().then((consoles) {
      if (mounted && consoles != null) setState(() => _bundled = consoles);
    });
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
  /// import, a library action or an add is running.
  void _switchTab(VoidCallback? switchTab) {
    if (_busy) return;
    switchTab?.call();
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

  /// Adds [console] to the main menu (or shows it again when it is hidden in
  /// Settings › Systems). The main menu and Settings › Systems update at once.
  Future<void> _addToMainMenu(LibretroConsole console) async {
    if (_busy) return;
    final provider = context.read<SqliteConfigProvider>();
    setState(() => _adding = console.id);
    try {
      final result = await _mainMenu.add(console, provider);
      switch (result.status) {
        case LibretroMainMenuAddStatus.added:
        case LibretroMainMenuAddStatus.shown:
          _notice(_f('consoleAdded', {'console': console.name}));
        case LibretroMainMenuAddStatus.alreadyPresent:
        case LibretroMainMenuAddStatus.inProgress:
          break;
        case LibretroMainMenuAddStatus.systemUnknown:
          _notice(_t('consoleSystemUnknown'));
        case LibretroMainMenuAddStatus.failed:
          _log.w('Libretro console ${console.id} not added: ${result.error}');
          _notice(_f('consoleAddFailed', {'error': result.error ?? ''}));
      }
    } finally {
      if (mounted) setState(() => _adding = null);
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

  Future<void> _openSkins(LibretroConsole console) async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(builder: (_) => LibretroSkinManagerScreen(console: console.id)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final provider = context.watch<SqliteConfigProvider>();
    final list = Center(
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 860),
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
                  child: Text(_t('embeddedConsoles'), style: theme.textTheme.titleLarge),
                ),
              Padding(
                padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
                child: Text(
                  _t('embeddedConsolesIntro'),
                  style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                ),
              ),
              _buildLibrary(context),
              for (final console in LibretroCoreCatalog.consoles.values)
                _buildConsole(
                  context,
                  console,
                  LibretroMainMenu.stateOf(console, provider.detectedSystems, provider.hiddenSystemFolders),
                ),
            ],
          ),
        ),
      ),
    );
    if (widget.inMainBar) {
      // Under the global header, clear of the notch like the other tabs.
      final safe = MediaQuery.viewPaddingOf(context);
      return libretroPage(Material(
        type: MaterialType.transparency,
        child: Padding(
          padding: EdgeInsets.fromLTRB(safe.left, 46.r, safe.right, 0),
          child: list,
        ),
      ));
    }
    return libretroPage(Scaffold(
      appBar: libretroPageAppBar(context, _t('embeddedConsoles')),
      body: SafeArea(child: list),
    ));
  }

  Widget _buildStatus(BuildContext context, IconData icon, String text, {Key? key}) {
    final theme = Theme.of(context);
    return Padding(
      key: key,
      padding: const EdgeInsets.only(top: 4),
      child: Row(
        children: [
          Icon(icon, size: 16, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              text,
              style: theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildConsole(BuildContext context, LibretroConsole console, LibretroMainMenuState state) {
    final theme = Theme.of(context);
    final importing = _importing == console.id;
    final adding = _adding == console.id;
    final unavailable = _bundled != null && !_bundled!.contains(console.id);
    final busy = _busy;
    return Card(
      key: ValueKey('libretro-console-${console.id}'),
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.sports_esports_outlined, color: theme.colorScheme.primary),
                const SizedBox(width: 12),
                Expanded(child: Text(console.name, style: theme.textTheme.titleMedium)),
                if (importing || adding)
                  const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
            if (state.isPresent)
              _buildStatus(
                context,
                Icons.check_circle_outline,
                _f('inMainMenu', {'systems': state.systemNames}),
                key: ValueKey('libretro-console-in-main-menu-${console.id}'),
              ),
            if (state.isHidden)
              _buildStatus(
                context,
                Icons.visibility_off_outlined,
                _f('hiddenInMainMenu', {'systems': state.systemNames}),
                key: ValueKey('libretro-console-hidden-${console.id}'),
              ),
            if (unavailable)
              _buildStatus(
                context,
                Icons.block,
                _t('consoleUnavailable'),
                key: ValueKey('libretro-console-unavailable-${console.id}'),
              ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                if (!state.isPresent)
                  LibretroFocusRing(
                    child: FilledButton.icon(
                      key: ValueKey('libretro-console-add-${console.id}'),
                      onPressed: busy || unavailable ? null : () => _addToMainMenu(console),
                      icon: Icon(state.isHidden ? Icons.visibility_outlined : Icons.add),
                      label: Text(state.isHidden ? _t('showInMainMenu') : _t('addToMainMenu')),
                    ),
                  ),
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
              ],
            ),
          ],
        ),
      ),
    );
  }
}
