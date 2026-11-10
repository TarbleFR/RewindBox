import 'dart:io';

import 'package:flutter/material.dart';

import '../models/game_model.dart';
import '../models/retro_achievements_game_info.dart';
import '../models/system_model.dart';
import '../providers/retro_achievements_provider.dart';
import '../repositories/retro_achievements_repository.dart';
import '../services/logger_service.dart';
import '../services/retroachievements_hash_service.dart';
import 'retro_achievements_identity.dart';

/// Reusable helper for resolving a local game to its RetroAchievements metadata.
///
/// Encapsulates the multi-step identification pipeline (hash generation, local
/// database lookups, filename normalization, and recent-history heuristics) so
/// it can be reused by both the details card and standalone achievement dialogs.
class RetroAchievementsHelper {
  static final _log = LoggerService.instance;

  RetroAchievementsHelper._();

  @visibleForTesting
  static RetroAchievementsIdentityStore? storeOverride;

  /// Replaces the bundled hash list (application database) in tests.
  @visibleForTesting
  static Future<int?> Function(String hash)? bundledLookupOverride;
  static RetroAchievementsIdentityStore get _store =>
      storeOverride ?? RetroAchievementsHashService.identityStore;

  /// Loads RetroAchievements metadata for [game].
  ///
  /// Returns `null` when the user is not connected, the game cannot be
  /// identified, or the API call fails.
  static Future<GameInfoAndUserProgress?> loadGameInfo({
    required GameModel game,
    required RetroAchievementsProvider provider,
    required SystemModel effectiveSystem,
    bool isAllMode = false,
    bool forceRefresh = false,
  }) async => (await loadGameInfoWithIdentity(game: game, provider: provider,
    effectiveSystem: effectiveSystem, isAllMode: isAllMode, forceRefresh: forceRefresh)).$1;

  /// Same as [loadGameInfo], with how the game was identified (shown in the
  /// achievements tab: recognized file, title-only match, or not recognized).
  static Future<(GameInfoAndUserProgress?, RetroAchievementsIdentity)> loadGameInfoWithIdentity({
    required GameModel game,
    required RetroAchievementsProvider provider,
    required SystemModel effectiveSystem,
    bool isAllMode = false,
    bool forceRefresh = false,
  }) async {
    if (!provider.isConnected) return (null, RetroAchievementsIdentity.unknown);

    final identity = await identify(
      game: game,
      summary: provider.userSummary,
      effectiveSystem: effectiveSystem,
      isAllMode: isAllMode,
    );
    final gameId = identity.gameId;
    if (gameId == null) return (null, identity);

    final info = await provider.getGameInfoAndUserProgress(
      gameId,
      forceRefresh: forceRefresh,
      md5Hash: identity.hash,
    );
    return (info, identity);
  }

  /// The file's hash with the rules of [RetroAchievementsHashService]: on iOS
  /// always (rcheevos, any size, recomputed once if it came from the older
  /// Dart code); elsewhere only below 512 MB for systems without a specific
  /// algorithm.
  static Future<String?> hashFor(GameModel game) async {
    if (RetroAchievementsNativeHash.available) {
      return RetroAchievementsHashService.generateHashForGame(game);
    }
    final cached = game.raHash;
    if (cached != null && cached.isNotEmpty) return cached;
    if (RetroAchievementsHashService.hasSpecificHashGenerator(game.systemFolderName)) {
      return RetroAchievementsHashService.generateHashForGame(game);
    }
    final romPath = game.romPath;
    if (romPath == null) return null;
    final file = File(romPath);
    if (!await file.exists()) return null;
    const maxSize = 512 * 1024 * 1024;
    if (await file.length() >= maxSize) return null;
    return RetroAchievementsHashService.generateHashForGame(game);
  }

  /// Identification by the file itself (NEOSTATION_RA_IDENTIFICATION_V1):
  /// 1. an emulator already loaded this file's set (learned at launch);
  /// 2. the hash is in the list bundled with the app;
  /// 3. RetroAchievements knows the hash (asked once, then cached): games and
  ///    dumps added after the app was built.
  /// Returns null when the file is not recognized this way.
  static Future<RetroAchievementsIdentity?> fileIdentity(GameModel game, String? hash,
      {bool online = true}) async {
    final romPath = game.romPath;
    if (romPath != null) {
      try {
        final record = await _store.rom(romPath);
        final launched = record?.source == 'launch' ? record?.gameId : null;
        final sameFile = record?.hash == null || hash == null || record?.hash == hash;
        if (launched != null && launched > 0 && sameFile) {
          return RetroAchievementsIdentity(gameId: launched, hash: hash,
            match: RetroAchievementsMatch.launch);
        }
      } catch (e) {
        _log.w('RetroAchievements identity unavailable: $e');
      }
    }
    if (hash == null || hash.isEmpty) return null;
    try {
      final lookup = bundledLookupOverride ?? RetroAchievementsRepository.findGameIdByHash;
      final gameId = await lookup(hash);
      if (gameId != null && gameId > 0) {
        return RetroAchievementsIdentity(gameId: gameId, hash: hash, match: RetroAchievementsMatch.hash);
      }
    } catch (e) {
      _log.e('Hash lookup failure: $e');
    }
    if (!online) return null;
    final gameId = await RetroAchievementsHashLookup.resolve(hash, _store);
    if (gameId != null && gameId > 0) {
      if (romPath != null) {
        try {
          await _store.saveGameId(romPath, gameId, source: 'online');
        } catch (e) {
          _log.w('RetroAchievements identity not saved: $e');
        }
      }
      return RetroAchievementsIdentity(gameId: gameId, hash: hash, match: RetroAchievementsMatch.online);
    }
    return null;
  }

  /// Full identification: by the file first, then (systems without a
  /// specific hash rule only) by title and recent history.
  static Future<RetroAchievementsIdentity> identify({
    required GameModel game,
    required dynamic summary,
    required SystemModel effectiveSystem,
    bool isAllMode = false,
  }) async {
    final hash = await hashFor(game);
    final byFile = await fileIdentity(game, hash);
    if (byFile != null) return byFile;

    if (RetroAchievementsHashService.hasSpecificHashGenerator(game.systemFolderName)) {
      return RetroAchievementsIdentity(hash: hash, match: RetroAchievementsMatch.none);
    }

    final byName = await _findGameIdByName(game: game, effectiveSystem: effectiveSystem, isAllMode: isAllMode);
    if (byName != null) {
      return RetroAchievementsIdentity(gameId: byName, hash: hash, match: RetroAchievementsMatch.name);
    }
    final byHistory = _findGameIdInHistory(game: game, summary: summary);
    if (byHistory != null) {
      return RetroAchievementsIdentity(gameId: byHistory, hash: hash, match: RetroAchievementsMatch.history);
    }
    return RetroAchievementsIdentity(hash: hash, match: RetroAchievementsMatch.none);
  }

  /// Evicts previously cached achievement badge images so a forced refresh
  /// displays updated artwork.
  static void evictBadgeCache(GameInfoAndUserProgress? gameInfo) {
    if (gameInfo == null) return;
    for (final ach in gameInfo.achievements.values) {
      final baseUrl =
          'https://media.retroachievements.org/Badge/${ach.badgeName}';
      NetworkImage('$baseUrl.png').evict();
      NetworkImage('${baseUrl}_lock.png').evict();
    }
  }

  static Future<int?> _findGameIdByName({
    required GameModel game,
    required SystemModel effectiveSystem,
    required bool isAllMode,
  }) async {
    // Filename normalization and metadata matching.
    try {
      var filenameWithoutExt = game.romname.contains('.')
          ? game.romname.substring(0, game.romname.lastIndexOf('.'))
          : game.romname;

      filenameWithoutExt = filenameWithoutExt
          .replaceAll(RegExp(r'\([^)]*\)'), '')
          .replaceAll(RegExp(r'\[[^\]]*\]'), '')
          .trim();

      final systemFolderName = isAllMode && game.systemFolderName != null
          ? game.systemFolderName!
          : effectiveSystem.primaryFolderName;

      final gameId = await RetroAchievementsRepository.findGameIdByFilename(
        systemFolderName,
        filenameWithoutExt,
      );
      if (gameId != null && gameId != 0) return gameId;
    } catch (e) {
      _log.e('Database metadata search failed: $e');
    }
    return null;
  }

  static int? _findGameIdInHistory({required GameModel game, required dynamic summary}) {
    // Heuristic matching against the user's recent play history.
    try {
      final gameName = game.name.toLowerCase();
      final normalizedLocal = gameName
          .replaceAll(RegExp(r'[^\w\s]'), '')
          .replaceAll(RegExp(r'\s+'), ' ')
          .trim()
          .toLowerCase();

      for (final recentlyPlayed in summary?.recentlyPlayed ?? const []) {
        final raGameName = recentlyPlayed.title.toLowerCase();
        final normalizedRA = raGameName
            .replaceAll(RegExp(r'[^\w\s]'), '')
            .replaceAll(RegExp(r'\s+'), ' ')
            .trim()
            .toLowerCase();

        if (normalizedLocal == normalizedRA) {
          return recentlyPlayed.gameId;
        }
      }
    } catch (e) {
      _log.e('Recent history metadata resolution failed: $e');
    }
    return null;
  }
}
