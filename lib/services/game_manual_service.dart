import 'dart:io';

import 'package:flutter/foundation.dart';

import '../l10n/app_locale.dart';
import '../models/game_model.dart';
import '../models/system_model.dart';
import '../providers/file_provider.dart';
import '../repositories/system_repository.dart';
import '../constants/system_folder_names.dart';
import '../repositories/scraper_repository.dart';
import 'game_manual_french_sources.dart';
import 'screenscraper/media_resolver.dart';
import 'screenscraper/rom_hasher.dart';
import 'screenscraper_service.dart';

/// Result of [GameManualService.download]: [messageKey] is an [AppLocale] key.
class GameManualDownload {
  const GameManualDownload({required this.success, required this.messageKey});
  final bool success;
  final String messageKey;
}

/// The game's PDF manual as NeoStation keeps it.
///
/// Game Settings › Manual and the 3D box both go through here, so they read
/// the same file ([GameModel.getManualPath], resolved by the [FileProvider],
/// canonical `media/<system>/manuals/<game>.pdf`) and download it with the same
/// ScreenScraper call, credentials, preferred language, regions and quota. A
/// manual already on the device is never downloaded again, and nothing keeps a
/// second copy of it.
class GameManualService {
  GameManualService._();

  /// Media folder of [game]: its own system in the All and Favorites lists.
  static String folderFor(GameModel game, SystemModel system, {required bool isAllMode}) =>
      isAllMode && game.systemFolderName != null ? game.systemFolderName! : system.primaryFolderName;

  /// Whether [system] is one of the lists that gather several consoles.
  static bool isAllModeSystem(SystemModel system) =>
      system.folderName == SystemFolderNames.all || system.folderName == SystemFolderNames.favorites;

  /// The canonical path of the manual (existing or not).
  static String pathFor(GameModel game, String folder, FileProvider fileProvider) =>
      game.getManualPath(folder, fileProvider);

  /// The path of the manual when the file is on the device, else null.
  static Future<String?> existing(GameModel game, String folder, FileProvider fileProvider) async {
    final path = pathFor(game, folder, fileProvider);
    try {
      return await File(path).exists() ? path : null;
    } catch (_) {
      return null;
    }
  }

  /// The game's own system in the All and Favorites lists.
  static Future<SystemModel> targetSystem(GameModel game, SystemModel system, {required bool isAllMode}) async {
    if (isAllMode && game.systemFolderName != null) {
      final original = await SystemRepository.getSystemByFolderName(game.systemFolderName!);
      if (original != null) return original;
    }
    return system;
  }

  /// Downloads the manual from ScreenScraper into its canonical place. A
  /// game without a ROM path or a system id cannot be identified: nothing is
  /// requested.
  /// Replaces the ScreenScraper download in tests.
  @visibleForTesting
  static Future<GameManualDownload> Function(GameModel game, SystemModel targetSystem)? debugDownloader;

  static Future<GameManualDownload> download({
    required GameModel game,
    required SystemModel targetSystem,
    bool forceOverwrite = false,
    void Function(double progress)? onProgress,
  }) async {
    final debug = debugDownloader;
    if (debug != null) return debug(game, targetSystem);
    final romPath = game.romPath;
    final systemId = targetSystem.id;
    // In French, the edition's own French manual first: by its product code
    // on the Internet Archive, or Nintendo Europe's PDF of a DS game
    // (docs/game-box-3d.md § 26).
    final french = systemId != null && await _scrapesInFrench();
    String? target;
    if (french) {
      target = await _canonicalPath(game, targetSystem);
      if (await GameManualFrenchSources.fill(game, systemId, target, byTitle: false) != null) {
        return const GameManualDownload(success: true, messageKey: AppLocale.manualDownloaded);
      }
    }
    if (romPath == null || systemId == null) {
      return _frenchByTitle(french, game, systemId, target);
    }
    final result = await ScreenScraperService.downloadGameManual(
      appSystemId: systemId,
      romName: game.romname,
      systemFolder: targetSystem.primaryFolderName,
      romPath: romPath,
      gameName: game.name,
      serialNumber: game.titleId,
      forceOverwrite: forceOverwrite,
      onProgress: (status, progress) => onProgress?.call(progress),
    );
    final success = result['success'] == true;
    if (!success && french) {
      final byTitle = await _frenchByTitle(french, game, systemId, target);
      if (byTitle.success) return byTitle;
    }
    return GameManualDownload(
      success: success,
      messageKey: result['message']?.toString() ??
          (success ? AppLocale.manualDownloaded : AppLocale.manualDownloadFailed),
    );
  }

  /// A French manual found by the game's exact title on the Internet Archive
  /// (the same platform named), when nothing else gave one.
  static Future<GameManualDownload> _frenchByTitle(bool french, GameModel game, String? systemId, String? target) async {
    if (french && systemId != null && target != null) {
      if (await GameManualFrenchSources.fill(game, systemId, target) != null) {
        return const GameManualDownload(success: true, messageKey: AppLocale.manualDownloaded);
      }
    }
    return const GameManualDownload(success: false, messageKey: AppLocale.manualDownloadFailed);
  }

  static Future<bool> _scrapesInFrench() async {
    try {
      return (await ScraperRepository.getPreferredLanguage()).toLowerCase().startsWith('fr');
    } catch (_) {
      return false;
    }
  }

  /// Where ScreenScraper writes the manual, for the same file name.
  static Future<String> _canonicalPath(GameModel game, SystemModel system) async {
    final clean = await ScreenscraperRomHasher.getCleanRomName(game.romname, system.id!);
    final root = await ScreenscraperMediaResolver.getMediaDirectory();
    return '$root/${system.primaryFolderName}/manuals/$clean.pdf';
  }
}
