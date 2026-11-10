import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:neostation/services/logger_service.dart';
import '../models/game_model.dart';
import '../repositories/retro_achievements_repository.dart';
import '../repositories/system_repository.dart';
import '../utils/optimized_md5_utils.dart';
import 'archive_service.dart';
import 'retro_achievements_identity.dart';

/// Service responsible for generating system-specific hashes required by
/// RetroAchievements (RA) for game identification.
///
/// RA uses different hashing algorithms depending on the platform (e.g., NES
/// hashes excluding headers, SNES hashes with specific offsets). This service
/// coordinates these algorithms, handles archive extraction, and offloads
/// processing to background isolates.
class RetroAchievementsHashService {
  /// Maximum file size permitted for hash generation (512 MB).
  static const int maxFileSizeBytes = 512 * 1024 * 1024;

  static final _log = LoggerService.instance;

  /// Where identification results are kept (application database; tests
  /// replace it with a memory store).
  static RetroAchievementsIdentityStore identityStore = const SqlRetroAchievementsIdentityStore();

  /// Replaces the bundled hash list (application database) in tests.
  @visibleForTesting
  static Future<int?> Function(String hash, String consoleId)? bundledLookupOverride;

  /// RetroAchievements console id of a library system (its `ra_id`).
  @visibleForTesting
  static Future<int?> Function(String systemFolderName)? consoleIdOverride;
  static final Map<String, int?> _consoleIds = {};

  static Future<int?> raConsoleId(String? systemFolderName) async {
    if (systemFolderName == null || systemFolderName.isEmpty) return null;
    final override = consoleIdOverride;
    if (override != null) return override(systemFolderName);
    if (_consoleIds.containsKey(systemFolderName)) return _consoleIds[systemFolderName];
    int? id;
    try {
      final system = await SystemRepository.getSystemByFolderName(systemFolderName);
      id = int.tryParse(system?.raId ?? '');
    } catch (e) {
      _log.w('RetroAchievements console id unavailable for $systemFolderName: $e');
      return null;
    }
    _consoleIds[systemFolderName] = id;
    return id;
  }

  /// Generates the appropriate RA hash for a specific game if not already present.
  ///
  /// On iOS the hash is computed by rcheevos itself, with the same code and
  /// the same .chd/.cso reader as the emulators (NEOSTATION_RA_DISC_READER_V1):
  /// discs (PlayStation, Saturn, Dreamcast...) are hashed the way
  /// RetroAchievements expects, whatever their size. Hashes computed by the
  /// older Dart code are recomputed once. Elsewhere, the Dart implementation
  /// is used (cartridge rules; discs fall back to a whole-file MD5).
  static Future<String?> generateHashForGame(GameModel game) async {
    try {
      final romPath = game.romPath;
      if (romPath == null) return null;
      final consoleId = await raConsoleId(game.systemFolderName);
      final native = RetroAchievementsNativeHash.available && consoleId != null && consoleId > 0;

      if (native) {
        RomIdentityRecord? record;
        try {
          record = await identityStore.rom(romPath);
        } catch (e) {
          _log.w('RetroAchievements identity unavailable: $e');
        }
        final stored = record?.hash;
        if (stored != null && stored.isNotEmpty && record!.algorithm >= RetroAchievementsNativeHash.algorithm) {
          return stored;
        }
      } else if (game.raHash != null && game.raHash!.isNotEmpty) {
        return game.raHash;
      }

      if (!await OptimizedMd5Utils.fileExists(romPath)) {
        return null;
      }

      if (!native) {
        final existingHash = await RetroAchievementsRepository.getRomRaHash(romPath);
        if (existingHash != null && existingHash.isNotEmpty) {
          return existingHash;
        }
        final fileSize = await OptimizedMd5Utils.getFileSize(romPath);
        if (fileSize > maxFileSizeBytes) {
          return null;
        }
      }

      String romPathToProcess = romPath;
      final bool isArchive =
          (romPathToProcess.toLowerCase().endsWith('.zip') ||
              romPathToProcess.toLowerCase().endsWith('.7z')) &&
          !isArcadeSystem(game.systemFolderName);

      if (isArchive) {
        final extractedPath = await ArchiveService.extractRom(
          romPathToProcess,
          game.systemFolderName ?? 'unknown',
        );
        if (extractedPath != null) {
          romPathToProcess = extractedPath;
        } else {
          _log.w(
            'Failed to extract compressed file, aborting hash: ${game.name}',
          );
          return null;
        }
      }

      String? hash;
      try {
        if (native) {
          hash = await RetroAchievementsNativeHash.hash(romPathToProcess, consoleId);
        } else {
          await Future.delayed(const Duration(milliseconds: 500));
          final isolateToken = RootIsolateToken.instance!;
          hash = await compute(_generateHashForSystemIsolate, {
            'romPath': romPathToProcess,
            'systemFolderName': game.systemFolderName,
            'gameName': game.name,
            'token': isolateToken,
          });
        }
      } finally {
        if (isArchive) {
          await ArchiveService.cleanupTempFolder(
            game.systemFolderName ?? 'unknown',
            romPath,
          );
        }
      }

      if (hash != null && hash.isNotEmpty) {
        if (native) {
          await identityStore.saveHash(romPath, hash, consoleId: consoleId,
            algorithm: RetroAchievementsNativeHash.algorithm);
        } else {
          await RetroAchievementsRepository.updateRomRaHash(romPath, hash);
        }
        if (consoleId != null) {
          await _lookupAndSaveGameIdByHash(hash, consoleId.toString(), game);
        }
      }

      return hash;
    } catch (e) {
      _log.e('Error generating hash for ${game.name}: $e');
      return null;
    }
  }

  /// Batch processes hashes for a list of games in the background, with the
  /// same rules (and cache) as [generateHashForGame].
  static Future<int> processGamesHashesInBackground(
    List<GameModel> games,
  ) async {
    int hashesGenerated = 0;
    for (final game in games) {
      if (game.romPath == null) continue;
      final before = game.raHash;
      final hash = await generateHashForGame(game);
      if (hash != null && hash.isNotEmpty && hash != before) hashesGenerated++;
    }
    return hashesGenerated;
  }

  /// Determines if a specific system requires a non-standard hashing algorithm
  /// recognized by RetroAchievements.
  static bool hasSpecificHashGenerator(String? systemFolderName) {
    if (systemFolderName == null) return false;
    final system = systemFolderName.toLowerCase();

    return system == 'nes' ||
        system == 'fc' ||
        system == 'ds' ||
        system == 'snes' ||
        system == 'sfc' ||
        system == 'satellaview' ||
        system == 'arc' ||
        system == 'fbneo' ||
        system == 'neogeo' ||
        system == 'naomi' ||
        system == 'naomi2' ||
        system == 'naomigd' ||
        system == 'aw' ||
        system == 'cps1' ||
        system == 'cps2' ||
        system == 'cps3' ||
        system == 'mame' ||
        system == 'gb' ||
        system == 'gbc' ||
        system == 'gba' ||
        system == 'vb' ||
        system == 'ngp' ||
        system == 'ngpc' ||
        system == '32x' ||
        system == 'sms' ||
        system == 'mark3' ||
        system == 'wasm4' ||
        system == 'md' ||
        system == 'genesis' ||
        system == 'jag' ||
        system == 'ws' ||
        system == 'wsc' ||
        system == 'chf' ||
        system == 'vect' ||
        system == 'mo2' ||
        system == 'intv' ||
        system == 'cv' ||
        system == '2600' ||
        system == '7800' ||
        system == 'lynx' ||
        system == 'ard' ||
        system == 'n64' ||
        system == 'sg1k' ||
        system == 'duck' ||
        system == 'wsv' ||
        system == 'gg' ||
        system == 'mini';
  }

  /// Identifies if a system belongs to the Arcade category, where ROM archives
  /// (ZIPs) should not be extracted for hashing.
  static bool isArcadeSystem(String? systemFolderName) {
    if (systemFolderName == null) return false;
    final system = systemFolderName.toLowerCase();
    return system == 'arc' ||
        system == 'fbneo' ||
        system == 'neogeo' ||
        system == 'naomi' ||
        system == 'naomi2' ||
        system == 'naomigd' ||
        system == 'aw' ||
        system == 'cps1' ||
        system == 'cps2' ||
        system == 'cps3' ||
        system == 'mame';
  }

  /// Top-level function executed in a background isolate to compute system-specific hashes.
  static Future<String?> _generateHashForSystemIsolate(
    Map<String, dynamic> params,
  ) async {
    final token = params['token'] as RootIsolateToken?;
    if (token != null) {
      BackgroundIsolateBinaryMessenger.ensureInitialized(token);
    }

    final romPath = params['romPath'].toString();
    final systemFolderName = params['systemFolderName']?.toString();
    final systemFolder = systemFolderName?.toLowerCase() ?? '';

    try {
      String? hash;

      if (systemFolder == 'nes' || systemFolder == 'fc' ||
          systemFolder == 'famicom' || systemFolder == 'fds') {
        hash = await OptimizedMd5Utils.calculateNesMd5(romPath);
      } else if (systemFolder == 'pcengine' || systemFolder == 'pce' ||
          systemFolder == 'tg16' || systemFolder == 'sgx' ||
          systemFolder == 'supergrafx') {
        // Same rule as rcheevos: a copier header makes the size 512 bytes
        // over a multiple of 1 KiB.
        hash = await OptimizedMd5Utils.calculatePceMd5(romPath);
      } else if (systemFolder == 'ds') {
        hash = await OptimizedMd5Utils.calculateDsMd5(romPath);
      } else if (systemFolder == 'arc' ||
          systemFolder == 'fbneo' ||
          systemFolder == 'neogeo' ||
          systemFolder == 'naomi' ||
          systemFolder == 'naomi2' ||
          systemFolder == 'naomigd' ||
          systemFolder == 'aw' ||
          systemFolder == 'cps1' ||
          systemFolder == 'cps2' ||
          systemFolder == 'cps3' ||
          systemFolder == 'mame') {
        hash = OptimizedMd5Utils.calculateArcadeMd5(romPath);
      } else if (systemFolder == 'snes' ||
          systemFolder == 'sfc' ||
          systemFolder == 'satellaview') {
        hash = await OptimizedMd5Utils.calculateSnesMd5(romPath);
      } else if (systemFolder == '7800') {
        hash = await OptimizedMd5Utils.calculateAtari7800Md5(romPath);
      } else if (systemFolder == 'lynx') {
        hash = await OptimizedMd5Utils.calculateLynxMd5(romPath);
      } else if (systemFolder == 'ard') {
        hash = await OptimizedMd5Utils.calculateArduboyMd5(romPath);
      } else if (systemFolder == 'n64') {
        hash = await OptimizedMd5Utils.calculateN64Md5(romPath);
      } else {
        hash = await OptimizedMd5Utils.calculateFileMd5(romPath);
      }

      return hash;
    } catch (e) {
      _log.e('Error generating hash for system $systemFolder: $e');
      return null;
    }
  }

  /// Searches for the RetroAchievements Game ID in the local database using the
  /// generated hash and updates the game metadata.
  static Future<void> _lookupAndSaveGameIdByHash(
    String raHash,
    String raConsoleId,
    GameModel game,
  ) async {
    try {
      final override = bundledLookupOverride;
      if (override != null) {
        await override(raHash, raConsoleId);
        return;
      }
      final gameId = await RetroAchievementsRepository.getGameIdByHash(
        raHash,
        raConsoleId,
      );

      if (gameId != null) {
        await RetroAchievementsRepository.updateRomRaGameId(
          game.romPath!,
          gameId,
        );
      } else {
        _log.w('No game ID found in internal DB for RA hash: ${game.name}');
      }
    } catch (e) {
      _log.e('Error looking up game ID by hash: $e');
    }
  }
}
