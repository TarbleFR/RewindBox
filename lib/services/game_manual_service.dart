import 'dart:io';

import 'package:flutter/foundation.dart';

import '../l10n/app_locale.dart';
import '../models/game_model.dart';
import '../models/system_model.dart';
import '../providers/file_provider.dart';
import '../repositories/system_repository.dart';
import '../constants/system_folder_names.dart';
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
    if (romPath == null || systemId == null) {
      return const GameManualDownload(success: false, messageKey: AppLocale.manualDownloadFailed);
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
    return GameManualDownload(
      success: success,
      messageKey: result['message']?.toString() ??
          (success ? AppLocale.manualDownloaded : AppLocale.manualDownloadFailed),
    );
  }
}
