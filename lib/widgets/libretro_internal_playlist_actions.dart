import 'playlist_import_button.dart';
import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../l10n/libretro_locale.dart';
import '../l10n/texture_catalog_locale.dart';
import '../services/texture_catalog_service.dart';
import '../models/system_model.dart';
import '../screens/libretro/libretro_library_actions.dart';
import '../screens/libretro/libretro_skin_manager_screen.dart';
import '../services/libretro_core_catalog.dart';
import '../services/libretro_internal_service.dart';
import 'libretro_3ds_import_route.dart';

/// Embedded console whose system data has its own import
/// ([openLibretro3dsImport]).
const String _console3ds = '3ds';

/// Import button of the playlists run by the embedded libretro engine: the
/// same floating button and tab action as the other embedded engines. Its
/// menu also opens the skins of the playlist's console.
class LibretroInternalPlaylistActions extends StatefulWidget {
  const LibretroInternalPlaylistActions({
    super.key,
    required this.system,
    required this.onLibraryChanged,
    this.onInteractionChanged,
    this.libraryFolders,
    this.embedded = false,
    this.copyRetroArch,
    this.open3dsImport,
  });

  /// System of the playlist. A copy named after an alias folder during a
  /// scan (folder "n3ds" of the 3DS) imports games and opens skins as its
  /// bound system, like its launches.
  final SystemModel system;

  /// Canonical catalog key of [system] ([LibretroInternalService.systemKey]),
  /// also the console folder its games are imported into.
  String get systemFolder => LibretroInternalService.systemKey(system);

  /// Called after games were imported, with the outcome (it names
  /// NeoStation's `roms` folder when that folder received them because no
  /// library folder was registered).
  final Future<void> Function(LibretroImportResult result) onLibraryChanged;

  /// The registered library folders (the configuration's ROM folders): the
  /// games go to one of them, chosen by the user when there are several.
  final List<String> Function()? libraryFolders;
  final ValueChanged<bool>? onInteractionChanged;
  final bool embedded;

  /// RetroArch copy to run (tests); [LibretroInternalService.copyRetroArchData]
  /// by default.
  final Future<LibretroRetroArchCopy?> Function()? copyRetroArch;

  /// Opens the Nintendo 3DS system data import (tests);
  /// [openLibretro3dsImport] by default.
  final Future<void> Function(BuildContext context)? open3dsImport;

  @override
  State<LibretroInternalPlaylistActions> createState() =>
      _LibretroInternalPlaylistActionsState();
}

class _LibretroInternalPlaylistActionsState
    extends State<LibretroInternalPlaylistActions> {
  bool _busy = false;

  String _t(String key) => LibretroLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      LibretroLocale.formatContext(context, key, values);

  void _interaction(bool active) => widget.onInteractionChanged?.call(active);

  /// Embedded console of the playlist (skins belong to the console, not to
  /// the folder); null when the folder is not bound to one.
  String? get _console => LibretroCoreCatalog.bindingFor(widget.systemFolder)?.console;

  Future<void> _openSkins() async {
    final console = _console;
    _interaction(true);
    try {
      if (console == null) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => LibretroSkinManagerScreen(console: console),
        ),
      );
    } finally {
      if (mounted) _interaction(false);
    }
  }

  void _notice(String message, {SnackBarAction? action}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message), action: action));
  }

  /// The Nintendo 3DS system data import (BIOS, NAND, console files): its
  /// page opens with the import assistant started.
  Future<void> _open3dsImport() async {
    _interaction(true);
    try {
      await (widget.open3dsImport ?? openLibretro3dsImport)(context);
    } finally {
      if (mounted) _interaction(false);
    }
  }

  // Build 486: the console's HD textures page (PSP, 3DS; N64 since its catalogue).
  Future<void> _openTextures() async {
    _interaction(true);
    try {
      final opened = await TextureCatalogService.openConsole(widget.system.folderName, consoleKey: widget.systemFolder);
      if (!opened && mounted) _notice(TextureCatalogLocale.text(Localizations.localeOf(context), 'openFailed'));
    } finally {
      if (mounted) _interaction(false);
    }
  }

  Future<void> _selected(String action) async {
    if (_busy) return;
    if (action == 'textures') {
      await _openTextures();
      return;
    }
    if (action == 'skins') {
      await _openSkins();
      return;
    }
    if (action == 'system3ds') {
      await _open3dsImport();
      return;
    }
    setState(() => _busy = true);
    _interaction(true);
    try {
      if (action == 'games') {
        final destination = await chooseLibretroImportDestination(
          context,
          systemFolder: widget.systemFolder,
          registeredRoots: widget.libraryFolders?.call() ?? const <String>[],
          folderAliases: <String>[widget.system.folderName, ...widget.system.folders],
        );
        if (destination.unavailable) {
          _notice(_t('importLibraryUnavailable'));
          return;
        }
        if (destination.cancelled || !mounted) return;
        final result = await LibretroInternalService.importGamesForSystem(
          widget.system,
          library: destination.library,
        );
        if (result.imported > 0) {
          await widget.onLibraryChanged(result);
          _notice(_f('gamesImported', {'count': result.imported}));
        }
        if (result.alreadyPresent > 0) _notice(_f('importAlreadyPresent', {'count': result.alreadyPresent}));
        if (result.rejected > 0) _notice(_t('gamesRejected'));
      } else if (action == 'retroarch') {
        final copied = await (widget.copyRetroArch ?? LibretroInternalService.copyRetroArchData)();
        if (copied == null) return;
        if (copied.total == 0 && copied.emulator3dsFolder) {
          // An Azahar, Citra or Lime3DS folder: its system data has its own
          // import, one touch away.
          _notice(
            _t('retroArch3dsFolder'),
            action: SnackBarAction(label: _t('system3dsImport'), onPressed: () => unawaited(_open3dsImport())),
          );
          return;
        }
        _notice(
          copied.total == 0
              ? _t('retroArchNothing')
              : _f('retroArchImported', {
                  'saves': copied.saves,
                  'states': copied.states,
                  'system': copied.system,
                }),
        );
      }
    } catch (error) {
      _notice(_f('importFailed', {'error': error}));
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        _interaction(false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    // The embedded engine runs on iOS only (the platform Flutter reports, so
    // a widget test can stand in for an iPhone).
    if (defaultTargetPlatform != TargetPlatform.iOS)
      return const SizedBox.shrink();
    return PlaylistImportButton(
      menuKey: const ValueKey('libretro-internal-import-menu'),
      tooltip: _t('importMenu'),
      busy: _busy,
      embedded: widget.embedded,
      onOpened: () => _interaction(true),
      onCanceled: () => _interaction(false),
      onSelected: _selected,
      items: (context) => [
        PopupMenuItem(value: 'games', child: Text(_t('importGames'))),
        // The 3DS reads its BIOS and system files from its own import
        // (Azahar, Citra, Lime3DS user folder, GodMode9 dump, ZIP).
        if (_console == _console3ds)
          PopupMenuItem(value: 'system3ds', child: Text(_t('import3dsSystem'))),
        PopupMenuItem(value: 'retroarch', child: Text(_t('importRetroArch'))),
        if (_console != null)
          PopupMenuItem(value: 'skins', child: Text(_t('skins'))),
        if (TextureCatalogService.supports(widget.systemFolder))
          PopupMenuItem(
            value: 'textures',
            child: Text(
              TextureCatalogLocale.text(
                Localizations.localeOf(context),
                'menuTitle',
              ),
            ),
          ),
      ],
    );
  }
}
