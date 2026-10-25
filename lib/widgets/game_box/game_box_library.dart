import 'dart:io';

import 'package:flutter/widgets.dart';

import 'package:neostation/models/game_model.dart';
import 'package:neostation/models/system_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_inspector.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_preferences.dart';
import 'package:neostation/services/game_manual_service.dart';

/// The 3D box of a library game, shared by the carousel, the grid and the
/// list (docs/game-box-3d.md § 3): the same paths, the same profiles, the
/// same viewer and the same opening before a game starts.
class GameBoxLibrary {
  GameBoxLibrary._();

  static final Map<String, String> _paths = {};
  static final Set<String> _profilesLoading = {};

  /// NeoStation system id that chooses the box family.
  static String? systemIdFor(GameModel game, SystemModel system, {required bool isAllMode}) =>
      (isAllMode ? game.systemId : null) ?? system.id ?? game.systemId;

  /// System id the scraper maps to ScreenScraper.
  static String? appSystemIdFor(GameModel game, SystemModel system, {required bool isAllMode}) =>
      (isAllMode ? game.systemId : null) ?? system.id;

  static String folderFor(GameModel game, SystemModel system, {required bool isAllMode}) =>
      GameManualService.folderFor(game, system, isAllMode: isAllMode);

  /// Existing scan of [folder] (`box2d`, `box2dside`…) or null, cached per
  /// game and artwork version so that scrolling never touches the disk again.
  static String? mediaPath(
    GameModel game,
    String systemFolder,
    String mediaFolder,
    FileProvider fileProvider, {
    int artworkVersion = 0,
  }) {
    final key = '$systemFolder|$mediaFolder|${game.romname}|$artworkVersion';
    final cached = _paths.putIfAbsent(key, () {
      final path = game.getImagePath(systemFolder, mediaFolder, fileProvider);
      return File(path).existsSync() ? path : '';
    });
    return cached.isEmpty ? null : cached;
  }

  /// Forgets the cached scans of [romname] (faces fetched in the viewer).
  static void evict(String romname) => _paths.removeWhere((key, _) => key.contains('|$romname|'));

  /// Forgets every cached scan (after a scrape).
  static void evictAll() => _paths.clear();

  /// Loads the declared media of [systemId] once (families of consoles
  /// without a dedicated profile), then calls [onLoaded] to redraw.
  static void ensureProfile(String? systemId, VoidCallback onLoaded) {
    final id = (systemId ?? '').toLowerCase();
    if (id.isEmpty || !_profilesLoading.add(id)) return;
    GameBoxProfiles.load(id).then((_) => onLoaded());
  }

  static GameBoxSubject subject({
    required GameModel game,
    required SystemModel system,
    required FileProvider fileProvider,
    required bool isAllMode,
    Widget Function()? frontFallback,
  }) =>
      GameBoxSubject(
        game: game,
        systemFolder: folderFor(game, system, isAllMode: isAllMode),
        fileProvider: fileProvider,
        systemId: systemIdFor(game, system, isAllMode: isAllMode),
        appSystemId: appSystemIdFor(game, system, isAllMode: isAllMode),
        frontFallback: frontFallback,
        system: system,
        isAllMode: isAllMode,
      );

  /// Opens the viewer of [game]'s box above the library. The library keeps
  /// its view, selection and scroll position underneath and is not reloaded.
  static Future<void> inspect(
    BuildContext context, {
    required GameModel game,
    required SystemModel system,
    required FileProvider fileProvider,
    required bool isAllMode,
    required VoidCallback onPlay,
    Widget Function()? frontFallback,
    bool autoPlay = false,
  }) async {
    if (GameBoxLaunchGate.busy) return;
    await GameBoxInspector.open(
      context,
      autoPlay: autoPlay,
      onPlay: onPlay,
      subject: subject(
        game: game,
        system: system,
        fileProvider: fileProvider,
        isAllMode: isAllMode,
        frontFallback: frontFallback,
      ),
    );
    // Faces may have been fetched while the box was open.
    evict(game.romname);
    for (final kind in GameBoxMediaKind.values) {
      final path = game.getImagePath(folderFor(game, system, isAllMode: isAllMode), kind.folder, fileProvider);
      GameBoxImageSize.evict(path);
    }
  }

  /// "Play" from the library: the box opens first when it has a front scan
  /// and the opening is on (options of the viewer), then the library's usual
  /// launch runs. Returns false when the game should start directly.
  static Future<bool> playWithOpening(
    BuildContext context, {
    required GameModel game,
    required SystemModel system,
    required FileProvider fileProvider,
    required bool isAllMode,
    required VoidCallback onPlay,
    Widget Function()? frontFallback,
  }) async {
    if (GameBoxLaunchGate.busy) return true;
    final folder = folderFor(game, system, isAllMode: isAllMode);
    if (mediaPath(game, folder, GameBoxMediaKind.front.folder, fileProvider) == null) return false;
    final profile = await GameBoxProfiles.load(systemIdFor(game, system, isAllMode: isAllMode));
    if (!profile.opens) return false;
    if (!await GameBoxPreferences.openingAnimation()) return false;
    if (!context.mounted) return true;
    await inspect(
      context,
      game: game,
      system: system,
      fileProvider: fileProvider,
      isAllMode: isAllMode,
      onPlay: onPlay,
      frontFallback: frontFallback,
      autoPlay: true,
    );
    return true;
  }
}
