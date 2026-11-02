import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:path/path.dart' as path;
import 'package:neostation/services/logger_service.dart';
import 'package:neostation/services/rpcs3_title_catalog_service.dart';

import '../providers/file_provider.dart';
import '../repositories/scraper_repository.dart';
import 'game_box/game_box_batch.dart';
import 'game_box/game_box_fetcher.dart';
import 'game_box/game_box_media.dart';
import 'game_box/game_box_media_service.dart';
import 'game_box/game_box_preferences.dart';
import 'game_box/game_box_sources.dart';
import 'screenscraper/region_config.dart';
import 'game_manual_french_sources.dart';
import 'screenscraper/rom_hasher.dart';
import 'screenscraper/media_resolver.dart';
import 'screenscraper/screenscraper_client.dart';
import 'screenscraper/media_downloader.dart';
import 'screenscraper/game_id_media_fallback.dart';
import 'screenscraper/screenscraper_exceptions.dart';
import '../providers/scraping_provider.dart';
import '../l10n/app_locale.dart';
import '../widgets/scraping_summary_dialog.dart';

/// Service responsible for scraping game metadata and media from the
/// ScreenScraper.fr API.
///
/// Features:
/// - Multi-threaded scraping with configurable concurrency.
/// - Support for MD5-based identification.
/// - Local caching of metadata and media (images, videos, wheels).
/// - Automatic system mapping between NeoStation and ScreenScraper IDs.
/// - Daily request quota management and credentials verification.
class ScreenScraperService {
  static const String _baseUrl = 'https://api.screenscraper.fr/api2';
  static final _log = LoggerService.instance;

  // Developer credentials — provided at build time via --dart-define
  // or at runtime via environment variables.
  static String get _devId {
    const compileTime = String.fromEnvironment('SCREENSCRAPER_DEV_ID');
    if (compileTime.isNotEmpty) return compileTime;
    return Platform.environment['SCREENSCRAPER_DEV_ID'] ?? '';
  }

  static String get _devPassword {
    const compileTime = String.fromEnvironment('SCREENSCRAPER_DEV_PASSWORD');
    if (compileTime.isNotEmpty) return compileTime;
    return Platform.environment['SCREENSCRAPER_DEV_PASSWORD'] ?? '';
  }

  static Map<String, dynamic>? _cachedCredentials;
  /// The batch run in progress (null when none) and the number of the last
  /// one started: a newer run makes the older one stop at its next step.
  static Future<void>? _activeRun;
  static int _runGeneration = 0;

  /// Largest ROM file hashed during a batch run; a larger one is looked up by
  /// its bare title (docs/game-box-3d.md § 19).
  static const int batchMd5Limit = 1024 * 1024 * 1024;

  /// A file name without extension nor bracketed tags: `Super Mario Odyssey
  /// [0100000000010000][v0].nsp` gives `Super Mario Odyssey`.
  @visibleForTesting
  static String bareTitleOf(String filename) => FileProvider.stripRomExtension(filename)
      .replaceAll(RegExp(r'\[[^\]]*\]|\([^)]*\)'), ' ')
      .replaceAll(RegExp(r'\s+'), ' ')
      .trim();

  /// How long a new Start waits for the previous run to stop.
  @visibleForTesting
  static Duration previousRunWait = const Duration(seconds: 60);

  /// Pause before the games that met a passing failure are tried again.
  @visibleForTesting
  static Duration retryPause = const Duration(seconds: 3);

  /// Authenticates user credentials against the ScreenScraper API.
  static Future<Map<String, dynamic>?> verifyCredentials(
    String username,
    String password,
  ) async {
    try {
      final softname = await ScreenscraperClient.getSoftname();
      final url = Uri.parse('$_baseUrl/ssuserInfos.php').replace(
        queryParameters: {
          'devid': _devId,
          'devpassword': _devPassword,
          'softname': softname,
          'output': 'json',
          'ssid': username,
          'sspassword': password,
        },
      );

      final response = await ScreenscraperClient.httpGetWithRetry(
        url,
        headers: {'User-Agent': 'NeoStation/1.0', 'Accept': 'application/json'},
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        if (data['header']['success'] == 'true') {
          return data;
        } else {
          _log.e('Invalid credentials: ${data['header']['error']}');
          return null;
        }
      } else if (response.statusCode == 403) {
        _log.e('Error 403: Invalid credentials');
        return null;
      } else {
        _log.e('HTTP Error ${response.statusCode}: ${response.body}');
        return null;
      }
    } catch (e) {
      _log.e('Error verifying credentials: $e');
      return null;
    }
  }

  /// Persists encrypted ScreenScraper credentials and user tier information
  /// to the local database.
  static Future<bool> saveCredentials(
    String username,
    String password, [
    Map<String, dynamic>? userInfo,
    String? preferredLanguage,
  ]) async {
    try {
      return await ScraperRepository.saveCredentials(
        username,
        password,
        userInfo,
        preferredLanguage,
      );
    } catch (e) {
      _log.e('Error saving credentials: $e');
      return false;
    }
  }

  /// Refreshes local user statistics and account tier from the API.
  static Future<bool> refreshCredentials() async {
    try {
      final credentials = await getSavedCredentials();
      if (credentials == null) return false;

      final username = credentials['username']!;
      final password = credentials['password']!;

      final userInfo = await verifyCredentials(username, password);
      if (userInfo != null) {
        return await saveCredentials(
          username,
          password,
          userInfo['response']['ssuser'] as Map<String, dynamic>?,
          credentials['preferred_language'],
        );
      }
      return false;
    } catch (e) {
      _log.e('Error refreshing credentials: $e');
      return false;
    }
  }

  /// Retrieves the saved ScreenScraper credentials from the database.
  static Future<Map<String, String>?> getSavedCredentials() async {
    try {
      return await ScraperRepository.getSavedCredentials();
    } catch (e) {
      _log.e('Error getting saved credentials: $e');
      return null;
    }
  }

  /// Deletes saved credentials from the local database.
  static Future<bool> clearCredentials() async {
    try {
      return await ScraperRepository.clearCredentials();
    } catch (e) {
      _log.e('Error deleting credentials: $e');
      return false;
    }
  }

  /// Checks if credentials have been saved locally.
  static Future<bool> hasSavedCredentials() async {
    final credentials = await getSavedCredentials();
    return credentials != null;
  }

  /// Retrieves the current scraper configuration (modes and media types to fetch).
  static Future<Map<String, dynamic>> getScraperConfig() async {
    try {
      return await ScraperRepository.getScraperConfig();
    } catch (e) {
      _log.e('Error getting scraper configuration: $e');
      return {
        'scrape_mode': 'new_only',
        'scrape_metadata': true,
        'scrape_images': true,
        'scrape_videos': true,
      };
    }
  }

  /// Updates the scraper configuration.
  static Future<bool> saveScraperConfig(Map<String, dynamic> config) async {
    try {
      return await ScraperRepository.saveScraperConfig(config);
    } catch (e) {
      _log.e('Error saving scraper configuration: $e');
      return false;
    }
  }

  /// Retrieves the internal system mappings for enabled ScreenScraper integration.
  static Future<List<Map<String, dynamic>>> getSystemMappings() async {
    try {
      return await ScraperRepository.getSystemMappings();
    } catch (e) {
      _log.e('Error getting system mappings: $e');
      return [];
    }
  }

  /// Fetches the global list of supported systems from ScreenScraper.
  static Future<List<Map<String, dynamic>>?> getSystemsList() async {
    try {
      final credentials = await getSavedCredentials();
      if (credentials == null) {
        _log.e('There is no saved credentials to get systems list');
        return null;
      }

      final softname = await ScreenscraperClient.getSoftname();
      final url = Uri.parse('$_baseUrl/systemesListe.php').replace(
        queryParameters: {
          'devid': _devId,
          'devpassword': _devPassword,
          'softname': softname,
          'output': 'json',
          'ssid': credentials['username'],
          'sspassword': credentials['password'],
        },
      );

      final response = await ScreenscraperClient.httpGetWithRetry(
        url,
        headers: {'User-Agent': 'NeoStation/1.0', 'Accept': 'application/json'},
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        if (data['header']['success'] == 'true') {
          final systems = data['response']['systemes'] as List;
          return systems.cast<Map<String, dynamic>>();
        } else {
          _log.e('Error getting systems list: ${data['header']['error']}');
          return null;
        }
      } else {
        _log.e('HTTP Error ${response.statusCode}: ${response.body}');
        return null;
      }
    } catch (e) {
      _log.e('Error getting systems list: $e');
      return null;
    }
  }

  /// Synchronizes local system IDs with ScreenScraper IDs by matching folder names.
  static Future<bool> syncSystemIds() async {
    try {
      final unmappedCount = await ScraperRepository.getUnmappedSystemsCount();
      if (unmappedCount == 0) {
        await ScraperRepository.initializeScraperSystemConfig();
        return true;
      }

      final detectedSystems =
          await ScraperRepository.getDetectedSystemsWithScraperIds();

      if (detectedSystems.isEmpty) {
        _log.w('There is no detected systems to sync');
        return true;
      }

      final systemsList = await getSystemsList();
      if (systemsList == null) {
        return false;
      }

      final screenscraperMap = <String, int>{};
      for (final system in systemsList) {
        final noms = system['noms'] as Map<String, dynamic>;
        final nomRecalbox = noms['nom_recalbox']?.toString();
        if (nomRecalbox != null) {
          final names = nomRecalbox.split(',');
          for (final name in names) {
            final trimmedName = name.trim();
            if (trimmedName.isNotEmpty) {
              screenscraperMap[trimmedName] =
                  int.tryParse(system['id']?.toString() ?? '0') ?? 0;
            }
          }
        }
      }

      for (final system in detectedSystems) {
        final appSystemId = system['id'].toString();
        final folderName = system['folder_name']?.toString();
        final realName = system['real_name']?.toString();

        if (folderName == null || realName == null) continue;

        if (system['screenscraper_id'] != null) continue;

        final foundScreenscraperId = screenscraperMap[folderName];

        if (foundScreenscraperId != null) {
          await ScraperRepository.updateSystemScraperId(
            appSystemId,
            foundScreenscraperId,
          );
        }
      }

      await ScraperRepository.initializeScraperSystemConfig();
      return true;
    } catch (e) {
      _log.e('Error syncing system IDs: $e');
      return false;
    }
  }

  static void _addSerialLookup(
    Map<String, String> queryParameters,
    String? serialNumber,
  ) {
    final serial = serialNumber?.trim() ?? '';
    if (serial.isNotEmpty) queryParameters['serialnum'] = serial;
  }

  /// `mediaJeu.php` address of one media of a game already identified
  /// ([gameId] from `jeuInfos.php`), e.g. `box-2D-back(fr)` for the 3D box
  /// (docs/game-box-3d.md § 6). Credentials are added here at request time;
  /// callers keep only the credential-free ids and media token.
  static Future<Uri?> mediaJeuUri({
    required String systemId,
    required String gameId,
    required String media,
  }) async {
    final credentials = _cachedCredentials ?? await getSavedCredentials();
    if (credentials == null) return null;
    _cachedCredentials ??= credentials;
    final softname = await ScreenscraperClient.getSoftname();
    return Uri.parse('$_baseUrl/mediaJeu.php').replace(queryParameters: {
      'devid': _devId,
      'devpassword': _devPassword,
      'softname': softname,
      'ssid': credentials['username'] ?? '',
      'sspassword': credentials['password'] ?? '',
      'crc': '',
      'md5': '',
      'sha1': '',
      'systemeid': systemId,
      'jeuid': gameId,
      'media': media,
    });
  }

  /// Pure lookup parameters used by tests and by [fetchGameInfo].
  @visibleForTesting
  static Map<String, String> buildGameLookupParametersForTesting({
    required String systemId,
    required String romName,
    String? serialNumber,
  }) {
    final parameters = <String, String>{
      'systemeid': systemId,
      'romtype': 'rom',
      'romnom': romName,
    };
    _addSerialLookup(parameters, serialNumber);
    return parameters;
  }

  /// Fetches game information from the API using name or hash.
  ///
  /// Returns a map containing both `gameInfo` and updated `userInfo` (quota).
  static Future<Map<String, dynamic>?> fetchGameInfo(
    String systemId,
    String romName, {
    String? appSystemId,
    String? md5,
    int? maxDailyRequests,
    String? gameName,
    String? serialNumber,
  }) async {
    try {
      final credentials = _cachedCredentials ?? await getSavedCredentials();
      if (credentials == null) {
        _log.e('There is no saved credentials to get game information');
        return null;
      }

      _cachedCredentials ??= credentials;
      final softname = await ScreenscraperClient.getSoftname();

      String? targetAppSystemId = appSystemId;
      if (targetAppSystemId == null) {
        try {
          targetAppSystemId = await ScraperRepository.getAppSystemIdByScraperId(
            systemId,
          );
        } catch (_) {}
      }

      final cleanRomName = await ScreenscraperRomHasher.getCleanRomName(
        gameName ?? romName,
        targetAppSystemId,
      );

      final queryParameters = <String, String>{
        'devid': _devId,
        'devpassword': _devPassword,
        'softname': softname,
        'output': 'json',
        'ssid': credentials['username'] ?? '',
        'sspassword': credentials['password'] ?? '',
        ...buildGameLookupParametersForTesting(
          systemId: systemId,
          romName: cleanRomName,
          serialNumber: serialNumber,
        ),
      };

      final preferredLanguage = credentials['preferred_language'];
      if (preferredLanguage != null && preferredLanguage.isNotEmpty) {
        queryParameters['langue'] = preferredLanguage;
      }

      if (md5 != null && md5.isNotEmpty) {
        queryParameters['md5'] = md5;
      }

      final url = Uri.parse('$_baseUrl/jeuInfos.php')
          .replace(queryParameters: queryParameters);

      final response = await ScreenscraperClient.httpGetWithRetry(
        url,
        headers: {'User-Agent': 'NeoStation/1.0', 'Accept': 'application/json'},
        maxDailyRequests: maxDailyRequests,
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        if (data['header']['success'] == 'true') {
          return {
            'gameInfo': data['response']['jeu'],
            'userInfo': data['response']['ssuser'],
          };
        } else {
          _log.e('Error getting game information: ${data['header']['error']}');
          return null;
        }
      } else {
        _log.e('HTTP Error ${response.statusCode}: ${response.body}');
        return null;
      }
    } on ScreenscraperQuotaExceededException {
      rethrow;
    } catch (e) {
      _log.e('Error getting game information: $e');
      return null;
    }
  }

  /// Maps a raw API response to the NeoStation metadata schema.
  ///
  /// Handles language localization priority and region-based selection
  /// using the global priority map (World > US > EU > FR/SP/IT/DE > JP > KR/CN).
  static Future<Map<String, dynamic>> _mapGameInfoToMetadata(
    String filename,
    String romPath,
    Map<String, dynamic> gameInfo, {
    String? preferredLanguage,
  }) async {
    final regionPriority = await ScreenscraperRegionConfig.getRegionPriority();
    final metadata = <String, dynamic>{};
    metadata['filename'] = filename;

    final noms = gameInfo['noms'] as List<dynamic>? ?? [];
    String? realName;
    int bestNamePriority = -1;
    for (final nom in noms) {
      final region = nom['region']?.toString();
      final text = nom['text']?.toString();
      if (text != null && text.isNotEmpty) {
        final priority = regionPriority[region] ?? 0;
        if (priority > bestNamePriority) {
          bestNamePriority = priority;
          realName = text;
        }
      }
    }
    metadata['real_name'] = realName ?? filename;

    final synopses = gameInfo['synopsis'] as List<dynamic>? ?? [];
    String? preferredDescription;

    if (preferredLanguage != null) {
      for (final synopsis in synopses) {
        final langue = synopsis['langue']?.toString();
        final text = synopsis['text']?.toString();
        if (text != null && langue == preferredLanguage) {
          preferredDescription = text;
          break;
        }
      }
    }

    if (preferredDescription == null) {
      const languagePriority = ['en', 'es', 'fr', 'de', 'it', 'pt'];
      for (final lang in languagePriority) {
        for (final synopsis in synopses) {
          final langue = synopsis['langue']?.toString();
          final text = synopsis['text']?.toString();
          if (text != null && langue == lang) {
            preferredDescription = text;
            break;
          }
        }
        if (preferredDescription != null) break;
      }
    }

    for (final synopsis in synopses) {
      final langue = synopsis['langue']?.toString();
      final text = synopsis['text']?.toString();
      if (text != null) {
        switch (langue) {
          case 'en':
            metadata['description_en'] = text;
            break;
          case 'es':
            metadata['description_es'] = text;
            break;
          case 'fr':
            metadata['description_fr'] = text;
            break;
          case 'de':
            metadata['description_de'] = text;
            break;
          case 'it':
            metadata['description_it'] = text;
            break;
          case 'pt':
            metadata['description_pt'] = text;
            break;
        }
      }
    }

    final note = gameInfo['note'];
    if (note != null && note['text'] != null) {
      final rating = double.tryParse(note['text'].toString());
      if (rating != null) metadata['rating'] = rating;
    }

    final dates = gameInfo['dates'] as List<dynamic>? ?? [];
    DateTime? releaseDate;
    int bestDatePriority = -1;
    for (final date in dates) {
      final region = date['region']?.toString();
      final dateText = date['text']?.toString();
      if (dateText != null) {
        try {
          final parsedDate = DateTime.parse(dateText);
          final priority = regionPriority[region] ?? 0;
          if (priority > bestDatePriority) {
            bestDatePriority = priority;
            releaseDate = parsedDate;
          }
        } catch (_) {}
      }
    }
    if (releaseDate != null) {
      metadata['release_date'] = releaseDate.toIso8601String();
    }

    metadata['developer'] = gameInfo['developpeur']?['text']?.toString();
    metadata['publisher'] = gameInfo['editeur']?['text']?.toString();

    final genres = gameInfo['genres'] as List<dynamic>? ?? [];
    if (genres.isNotEmpty) {
      final genre = genres[0];
      final genreNoms = genre['noms'] as List<dynamic>? ?? [];
      String? genreText;

      if (preferredLanguage != null) {
        for (final nom in genreNoms) {
          final langue = nom['langue']?.toString();
          final text = nom['text']?.toString();
          if (text != null && langue == preferredLanguage) {
            genreText = text;
            break;
          }
        }
      }

      if (genreText == null) {
        for (final nom in genreNoms) {
          final langue = nom['langue']?.toString();
          final text = nom['text']?.toString();
          if (text != null && langue == 'en') {
            genreText = text;
            break;
          }
        }
      }

      metadata['genre'] =
          genreText ?? (genreNoms.isNotEmpty ? genreNoms[0]['text'] : null);
    }

    metadata['players'] = gameInfo['joueurs']?['text']?.toString();

    return metadata;
  }

  /// Saves the metadata to the local user_screenscraper_metadata table.
  static Future<bool> _saveGameMetadata(
    Map<String, dynamic> metadata,
    String appSystemId, {
    bool isFullyScraped = false,
  }) async {
    try {
      return await ScraperRepository.saveGameMetadata(
        metadata,
        appSystemId,
        isFullyScraped: isFullyScraped,
      );
    } catch (e) {
      _log.e('Error saving metadata for ${metadata['filename']}: $e');
      return false;
    }
  }

  static Future<Set<String>> _ensureVirtualMediaByGameId({
    required bool isMeloNxVirtual,
    required bool isRpcs3Virtual,
    required Map<String, dynamic> gameInfo,
    required int screenScraperSystemId,
    required String systemFolder,
    required String romName,
    required String appSystemId,
    required List<String> allowedMediaTypes,
    required Map<String, dynamic> downloadResult,
    required List<dynamic> sourceMedias,
    int? maxDailyRequests,
    bool keepExisting = false,
  }) async {
    final successfulTypes = <String>{
      ...(downloadResult['downloadedTypes'] as List<dynamic>? ?? const []).map(
        (value) => value.toString(),
      ),
      ...(downloadResult['existingTypes'] as List<dynamic>? ?? const []).map(
        (value) => value.toString(),
      ),
    };
    if (!isMeloNxVirtual && !isRpcs3Virtual) return successfulTypes;

    final credentials = await getSavedCredentials();
    final gameId = gameInfo['id']?.toString() ?? '';
    if (credentials == null || gameId.isEmpty) return successfulTypes;

    final softname = await ScreenscraperClient.getSoftname();
    final fallbackResult =
        await ScreenscraperGameIdMediaFallback.ensureMediaByGameId(
          gameId: gameId,
          systemId: screenScraperSystemId.toString(),
          systemFolder: systemFolder,
          romName: romName,
          appSystemId: appSystemId,
          devId: _devId,
          devPassword: _devPassword,
          softname: softname,
          username: credentials['username']?.toString() ?? '',
          password: credentials['password']?.toString() ?? '',
          allowedMediaTypes: allowedMediaTypes,
          alreadyDownloadedTypes: successfulTypes.toList(),
          sourceMedias: sourceMedias,
          debugFileName: isRpcs3Virtual
              ? 'rpcs3_scraper_media_debug.txt'
              : 'melonx_scraper_media_debug.txt',
          maxDailyRequests: maxDailyRequests,
          keepExisting: keepExisting,
        );
    return (fallbackResult['successfulTypes'] as List<dynamic>? ?? const [])
        .map((value) => value.toString())
        .toSet();
  }

  static bool _hasUsefulVirtualMedia(
    List<String> allowedMediaTypes,
    Set<String> successfulTypes,
  ) {
    const visualTypes = {'fanart', 'ss', 'wheel', 'box2D', 'video'};
    final requested = allowedMediaTypes.where(visualTypes.contains).toSet();
    return requested.isEmpty || requested.any(successfulTypes.contains);
  }

  @visibleForTesting
  static bool shouldRetryRpcs3ByNameForTesting(
    String? gameName,
    String? serialNumber,
  ) {
    final name = gameName?.trim() ?? '';
    final serial = serialNumber?.trim() ?? '';
    return name.isNotEmpty && name.toUpperCase() != serial.toUpperCase();
  }

  /// Scrapes a single game by its filename and updates its local state.
  static Future<Map<String, dynamic>> scrapeSingleGame({
    required String appSystemId,
    required String romName,
    required String systemFolder,
    required String romPath,
    String? gameName,
    String? serialNumber,
    Function(String status, double progress)? onProgress,
    bool forceOverwrite = false,
  }) async {
    try {
      onProgress?.call(AppLocale.checkingCredentials, 0.05);

      if (!await hasSavedCredentials()) {
        return {'success': false, 'message': AppLocale.scrapeNoCredentials};
      }

      int? screenScraperSystemId =
          await ScraperRepository.getScreenScraperIdByAppSystemId(appSystemId);

      if (screenScraperSystemId == null) {
        await syncSystemIds();
        screenScraperSystemId =
            await ScraperRepository.getScreenScraperIdByAppSystemId(
              appSystemId,
            );
      }

      if (screenScraperSystemId == null) {
        return {'success': false, 'message': AppLocale.scrapeSystemNotMapped};
      }

      onProgress?.call(AppLocale.fetchingMetadata, 0.1);

      final lowerRomPath = romPath.toLowerCase();
      final isMeloNxVirtual = lowerRomPath.startsWith('melonx://');
      final isRpcs3Virtual = lowerRomPath.startsWith('rpcs3-library://');
      var effectiveGameName = gameName;
      if (isRpcs3Virtual &&
          !shouldRetryRpcs3ByNameForTesting(effectiveGameName, serialNumber) &&
          (serialNumber?.trim().isNotEmpty ?? false)) {
        effectiveGameName =
            await Rpcs3TitleCatalogService.resolveTitle(serialNumber!) ??
            effectiveGameName;
      }

      Map<String, dynamic>? gameInfoResult;
      int attempts = 0;
      while (attempts < 3) {
        if (attempts > 0) await Future.delayed(const Duration(seconds: 2));
        gameInfoResult = await fetchGameInfo(
          screenScraperSystemId.toString(),
          romName,
          appSystemId: appSystemId,
          maxDailyRequests: 0,
          gameName:
              (systemFolder == 'android' || isMeloNxVirtual || isRpcs3Virtual)
              ? effectiveGameName
              : null,
          serialNumber: isRpcs3Virtual ? serialNumber : null,
        );
        if (gameInfoResult != null && gameInfoResult['gameInfo'] != null) break;
        attempts++;
      }

      if ((gameInfoResult == null || gameInfoResult['gameInfo'] == null) &&
          isRpcs3Virtual &&
          shouldRetryRpcs3ByNameForTesting(effectiveGameName, serialNumber)) {
        gameInfoResult = await fetchGameInfo(
          screenScraperSystemId.toString(),
          romName,
          appSystemId: appSystemId,
          maxDailyRequests: 0,
          gameName: effectiveGameName,
          serialNumber: null,
        );
      }

      if (gameInfoResult == null || gameInfoResult['gameInfo'] == null) {
        return {'success': false, 'message': AppLocale.scrapeGameNotFound};
      }

      final gameInfo = gameInfoResult['gameInfo'] as Map<String, dynamic>;
      final credentials = await getSavedCredentials();
      final preferredLanguage = credentials?['preferred_language'] ?? 'en';
      final scraperConfig = await getScraperConfig();

      if (scraperConfig['scrape_metadata'] as bool? ?? true) {
        final metadata = await _mapGameInfoToMetadata(
          romName,
          romPath,
          gameInfo,
          preferredLanguage: preferredLanguage,
        );
        await _saveGameMetadata(metadata, appSystemId, isFullyScraped: true);
      }

      onProgress?.call(AppLocale.downloadingImages, 0.2);

      final allowedMediaTypes = await ScraperRepository.getEnabledMediaTypes();

      if (allowedMediaTypes.isEmpty) {
        return {'success': true, 'message': AppLocale.scrapeSuccessful};
      }

      final medias = gameInfo['medias'] as List<dynamic>? ?? [];
      final downloadResult =
          await ScreenscraperMediaDownloader.downloadGameMedia(
            systemFolder,
            romName,
            medias,
            1,
            appSystemId: appSystemId,
            preferredLanguage: preferredLanguage,
            allowedMediaTypes: allowedMediaTypes,
            forceOverwrite: forceOverwrite || isMeloNxVirtual || isRpcs3Virtual,
            maxDailyRequests: null,
            onProgress: (p) =>
                onProgress?.call(AppLocale.downloadingImages, 0.2 + (p * 0.8)),
          );

      var mediaSuccess = downloadResult['success'] == true;
      if (isMeloNxVirtual || isRpcs3Virtual) {
        final successfulTypes = await _ensureVirtualMediaByGameId(
          isMeloNxVirtual: isMeloNxVirtual,
          isRpcs3Virtual: isRpcs3Virtual,
          gameInfo: gameInfo,
          screenScraperSystemId: screenScraperSystemId,
          systemFolder: systemFolder,
          romName: romName,
          appSystemId: appSystemId,
          allowedMediaTypes: allowedMediaTypes,
          downloadResult: downloadResult,
          sourceMedias: medias,
          maxDailyRequests: null,
        );
        mediaSuccess = _hasUsefulVirtualMedia(
          allowedMediaTypes,
          successfulTypes,
        );
      }

      return {
        'success': mediaSuccess,
        'message': mediaSuccess
            ? AppLocale.scrapeSuccessful
            : AppLocale.scrapeMediaDownloadsFailed,
      };
    } on ScreenscraperQuotaExceededException {
      return {'success': false, 'message': AppLocale.scrapeQuotaExceeded};
    } catch (e) {
      _log.e('Error scraping single game: $e');
      return {'success': false, 'message': AppLocale.scrapeUnexpectedError};
    }
  }

  /// Downloads only the PDF manual for a single game.
  ///
  /// This deliberately bypasses the user's global media selection: the Manual
  /// tab is an explicit per-game action, so a user can fetch one manual even
  /// when batch manual scraping is disabled in ScreenScraper settings.
  static Future<Map<String, dynamic>> downloadGameManual({
    required String appSystemId,
    required String romName,
    required String systemFolder,
    required String romPath,
    String? gameName,
    String? serialNumber,
    bool forceOverwrite = false,
    Function(String status, double progress)? onProgress,
  }) async {
    try {
      onProgress?.call(AppLocale.checkingCredentials, 0.05);
      if (!await hasSavedCredentials()) {
        return {'success': false, 'message': AppLocale.scrapeNoCredentials};
      }

      int? screenScraperSystemId =
          await ScraperRepository.getScreenScraperIdByAppSystemId(appSystemId);
      if (screenScraperSystemId == null) {
        await syncSystemIds();
        screenScraperSystemId =
            await ScraperRepository.getScreenScraperIdByAppSystemId(
              appSystemId,
            );
      }
      if (screenScraperSystemId == null) {
        return {'success': false, 'message': AppLocale.scrapeSystemNotMapped};
      }

      onProgress?.call(AppLocale.fetchingMetadata, 0.15);
      final lowerRomPath = romPath.toLowerCase();
      final isMeloNxVirtual = lowerRomPath.startsWith('melonx://');
      final isRpcs3Virtual = lowerRomPath.startsWith('rpcs3-library://');

      Map<String, dynamic>? gameInfoResult;
      for (var attempt = 0; attempt < 3; attempt++) {
        if (attempt > 0) await Future.delayed(const Duration(seconds: 2));
        gameInfoResult = await fetchGameInfo(
          screenScraperSystemId.toString(),
          romName,
          appSystemId: appSystemId,
          maxDailyRequests: 0,
          gameName:
              (systemFolder == 'android' || isMeloNxVirtual || isRpcs3Virtual)
              ? gameName : null,
          serialNumber: isRpcs3Virtual ? serialNumber : null,
        );
        if (gameInfoResult != null && gameInfoResult['gameInfo'] != null) break;
      }

      if ((gameInfoResult == null || gameInfoResult['gameInfo'] == null) &&
          isRpcs3Virtual &&
          shouldRetryRpcs3ByNameForTesting(gameName, serialNumber)) {
        gameInfoResult = await fetchGameInfo(
          screenScraperSystemId.toString(),
          romName,
          appSystemId: appSystemId,
          maxDailyRequests: 0,
          gameName: gameName,
          serialNumber: null,
        );
      }

      if (gameInfoResult == null || gameInfoResult['gameInfo'] == null) {
        return {'success': false, 'message': AppLocale.scrapeGameNotFound};
      }

      final gameInfo = gameInfoResult['gameInfo'] as Map<String, dynamic>;
      final medias = gameInfo['medias'] as List<dynamic>? ?? const [];
      final credentials = await getSavedCredentials();
      final preferredLanguage = credentials?['preferred_language'] ?? 'en';
      final regionPriority =
          await ScreenscraperRegionConfig.getRegionPriority();
      final selectedManual = ScreenscraperMediaResolver.selectBestMedia(
        medias,
        'manuel',
        preferredLanguage: preferredLanguage,
        regionPriority: regionPriority,
      );

      if (selectedManual == null) {
        return {'success': false, 'message': AppLocale.manualNotAvailable};
      }

      onProgress?.call(AppLocale.downloadingManual, 0.35);
      final result = await ScreenscraperMediaDownloader.downloadGameMedia(
        systemFolder,
        romName,
        medias,
        1,
        appSystemId: appSystemId,
        preferredLanguage: preferredLanguage,
        allowedMediaTypes: const ['manuel'],
        forceOverwrite: forceOverwrite,
        maxDailyRequests: null,
        onProgress: (p) =>
            onProgress?.call(AppLocale.downloadingManual, 0.35 + (p * 0.65)),
      );

      final cleanRomName = await ScreenscraperRomHasher.getCleanRomName(
        romName,
        appSystemId,
      );
      final mediaRoot = await ScreenscraperMediaResolver.getMediaDirectory();
      final format = selectedManual['format']?.toString().toLowerCase();
      final extension = (format == null || format.isEmpty) ? 'pdf' : format;
      final manualPath = path.join(
        mediaRoot,
        systemFolder,
        'manuals',
        '$cleanRomName.$extension',
      );

      final downloaded =
          result['success'] == true && await File(manualPath).exists();
      return {
        'success': downloaded,
        'message': downloaded
            ? AppLocale.manualDownloaded
            : AppLocale.manualDownloadFailed,
        if (downloaded) 'path': manualPath,
      };
    } on ScreenscraperQuotaExceededException {
      return {'success': false, 'message': AppLocale.scrapeQuotaExceeded};
    } catch (e) {
      _log.e('Error downloading game manual: $e');
      return {'success': false, 'message': AppLocale.manualDownloadFailed};
    }
  }

  /// Initiates a background scraping process for all detected ROMs.
  ///
  /// Coordinates system synchronization, batch processing, and thread-safe
  /// quota monitoring. Notifies the provided [ScrapingProvider] about progress.
  ///
  /// The scrape mode decides what Start does: `new_only` fetches what the
  /// current choices call for and is not on disk yet, `all` fetches every
  /// game again, `faces_only` only completes the box faces still missing.
  /// With [fileProvider], the box faces the media choices ask for are then
  /// completed from the ranked sources (docs/game-box-3d.md § 18).
  static Future<bool> startMetadataScraping(
    BuildContext context,
    ScrapingProvider scrapingProvider, {
    bool Function()? shouldCancel,
    FileProvider? fileProvider,
  }) async {
    // A new Start stops the run still finishing (after Stop, or blocked on a
    // slow game) and waits for it instead of failing at once
    // (docs/game-box-3d.md § 19).
    final generation = ++_runGeneration;
    final previous = _activeRun;
    if (previous != null) {
      _log.i('Scraper run #$generation: waiting for run #${generation - 1} to stop');
      try {
        await previous.timeout(previousRunWait);
      } catch (_) {
        _log.w('Scraper run #$generation: the previous run did not stop in time; starting anyway');
      }
    }
    if (generation != _runGeneration) return false;
    final done = Completer<void>();
    _activeRun = done.future;
    bool cancelled() => generation != _runGeneration || (shouldCancel?.call() ?? false);
    var outcome = 'error';

    try {
      final startTime = DateTime.now();
      final credentials = await getSavedCredentials();
      if (credentials == null) {
        outcome = 'no ScreenScraper account';
        return false;
      }

      ScreenscraperClient.initializeDailyCounter(0);
      final maxThreads = int.tryParse(credentials['maxthreads'] ?? '4') ?? 4;
      ScreenscraperClient.updateRequestSemaphore(maxThreads);

      final preferredLanguage = credentials['preferred_language'] ?? 'en';
      final scraperConfig = await getScraperConfig();
      final scrapeMode = scraperConfig['scrape_mode'].toString();
      final enabledTypes = await ScraperRepository.getEnabledMediaTypes();
      final boxKinds = fileProvider == null
          ? const <GameBoxMediaKind>{}
          : GameBoxBatch.kindsOf(enabledTypes);
      final extraSources = await GameBoxPreferences.scrapeExtraSources();

      final systemMappings = await getSystemMappings();
      if (systemMappings.isEmpty) {
        outcome = 'no system to scrape';
        return false;
      }

      final systemsWithRoms = <Map<String, dynamic>>[];
      int totalGamesToProcess = 0;

      for (final systemMapping in systemMappings) {
        final appSystemId = systemMapping['app_system_id'].toString();
        final count = await ScraperRepository.getRomCountForScraping(
          appSystemId,
          scrapeMode,
        );
        if (count > 0) {
          systemsWithRoms.add(systemMapping);
          totalGamesToProcess += count;
        }
      }

      _log.i(
        'Scraper run #$generation: mode=$scrapeMode language=$preferredLanguage '
        'threads=$maxThreads media=${enabledTypes.join(',')} games=$totalGamesToProcess '
        'boxFaces=${boxKinds.map((k) => k.name).join(',')} extraSources=$extraSources',
      );

      if (systemsWithRoms.isEmpty) {
        outcome = 'nothing to do';
        scrapingProvider.stopScraping();
        return true;
      }

      scrapingProvider.updateProgress(
        totalGames: totalGamesToProcess,
        processedGames: 0,
        successfulGames: 0,
        failedGames: 0,
      );

      final allRomsToProcess = <Map<String, dynamic>>[];
      for (final systemMapping in systemsWithRoms) {
        final appSystemId = systemMapping['app_system_id'].toString();
        final romsQueryResult = await ScraperRepository.getRomsForScraping(
          appSystemId,
          scrapeMode,
        );

        for (final rom in romsQueryResult) {
          final copy = Map<String, dynamic>.from(rom);
          copy['system_id'] = appSystemId;
          copy['screenscraper_system_id'] =
              systemMapping['screenscraper_system_id'];
          copy['system_name'] = systemMapping['real_name'];
          copy['system_folder'] = systemMapping['primary_folder_name'];
          allRomsToProcess.add(copy);
        }
      }

      int totalProcessedGames = 0;
      int totalSuccessfulGames = 0;
      int totalFailedGames = 0;
      var wasCancelled = false;
      final retry = <Map<String, dynamic>>[];

      Future<Map<String, dynamic>> processOne(Map<String, dynamic> rom, int threadId) {
        // The game's passing network failures are collected in its zone.
        final transient = <Object>[];
        return runZoned(
          () => _processRomInThread(
            rom: rom,
            threadId: threadId,
            systemName: rom['system_name'],
            systemFolder: rom['system_folder'],
            screenscraperSystemId:
                int.tryParse(rom['screenscraper_system_id']?.toString() ?? '0') ?? 0,
            appSystemId: rom['system_id'],
            maxThreads: maxThreads,
            maxDailyRequests: 100000,
            preferredLanguage: preferredLanguage,
            scrapingProvider: scrapingProvider,
            shouldCancel: cancelled,
            scraperConfig: scraperConfig,
            fileProvider: fileProvider,
            boxKinds: boxKinds,
            extraSources: extraSources,
          ),
          zoneValues: {ScreenscraperClient.transientErrorsKey: transient},
        ).then((result) {
          if (result['success'] != true && result['cancelled'] != true && transient.isNotEmpty) {
            return {...result, 'transient': transient.first.toString()};
          }
          return result;
        });
      }

      void count(Map<String, dynamic> result, {bool retried = false}) {
        scrapingProvider.addMediaResult(
          added: result['mediaAdded'] as int? ?? 0,
          replaced: result['mediaReplaced'] as int? ?? 0,
        );
        scrapingProvider.addFaceResult(
          (result['facesBySource'] as Map<String, int>?) ?? const {},
          result['facesMissing'] as int? ?? 0,
        );
        if (retried) {
          if (result['success'] == true) {
            totalSuccessfulGames++;
            totalFailedGames--;
          }
        } else {
          totalProcessedGames++;
          if (result['success'] == true) {
            totalSuccessfulGames++;
          } else {
            totalFailedGames++;
          }
        }
        scrapingProvider.updateProgress(
          totalGames: totalGamesToProcess,
          processedGames: totalProcessedGames,
          successfulGames: totalSuccessfulGames,
          failedGames: totalFailedGames,
        );
      }

      // A pool of workers: each takes the next game as soon as it is free,
      // so one slow game no longer holds the others back.
      Future<void> runPool(List<Map<String, dynamic>> queue, {required bool retried}) async {
        var next = 0;
        Future<void> worker(int threadId) async {
          while (!wasCancelled) {
            if (cancelled()) {
              wasCancelled = true;
              return;
            }
            if (next >= queue.length) return;
            final rom = queue[next++];
            final result = await processOne(rom, threadId);
            if (result['cancelled'] == true) {
              wasCancelled = true;
              return;
            }
            count(result, retried: retried);
            final why = result['transient'];
            if (!retried && why != null) {
              _log.w('Scraper run #$generation: ${rom['system_folder']}/${rom['filename']}: '
                  'passing failure ($why), tried again at the end');
              retry.add(rom);
            }
            scrapingProvider.markThreadCompleted(threadId);
          }
        }

        await Future.wait([
          for (var t = 1; t <= math.min(maxThreads, queue.length); t++) worker(t),
        ]);
      }

      scrapingProvider.clearCompletedThreads();
      await runPool(allRomsToProcess, retried: false);
      if (!wasCancelled && retry.isNotEmpty) {
        _log.i('Scraper run #$generation: trying ${retry.length} game(s) again after passing failures');
        await Future.delayed(retryPause);
        scrapingProvider.clearCompletedThreads();
        await runPool(retry, retried: true);
      }
      if (wasCancelled) {
        outcome = generation != _runGeneration ? 'stopped by a new run' : 'stopped by the user';
        scrapingProvider.stopScraping();
        return false;
      }

      final elapsed = DateTime.now().difference(startTime);
      outcome = 'finished: $totalProcessedGames processed, $totalSuccessfulGames found, '
          '$totalFailedGames failed, ${retry.length} retried, ${elapsed.inSeconds}s';
      if (context.mounted) {
        _showScrapingSummaryDialog(
          context,
          totalGames: totalGamesToProcess,
          successfulGames: totalSuccessfulGames,
          failedGames: totalFailedGames,
          elapsedTime: '${elapsed.inSeconds}s',
          totalRequests: 0,
          mediaAdded: scrapingProvider.mediaAdded,
          mediaReplaced: scrapingProvider.mediaReplaced,
          facesBySource: scrapingProvider.facesBySource,
          facesMissing: scrapingProvider.facesMissing,
        );
      }

      scrapingProvider.stopScraping();
      return true;
    } on ScreenscraperQuotaExceededException {
      outcome = 'daily ScreenScraper quota reached';
      _log.e('Daily scraping quota exceeded; stopping scraping session.');
      scrapingProvider.stopScraping();
      rethrow;
    } catch (e, stack) {
      outcome = 'error: $e';
      _log.e('Error during scraping process: $e', error: e, stackTrace: stack);
      scrapingProvider.stopScraping();
      return false;
    } finally {
      _log.i('Scraper run #$generation ended: $outcome');
      _cachedCredentials = null;
      done.complete();
      if (identical(_activeRun, done.future)) _activeRun = null;
    }
  }

  /// Internal worker thread processing for a single ROM during a batch operation.
  static Future<Map<String, dynamic>> _processRomInThread({
    required Map<String, dynamic> rom,
    required int threadId,
    required String systemName,
    required String systemFolder,
    required int screenscraperSystemId,
    required String appSystemId,
    required int maxThreads,
    required int maxDailyRequests,
    required String? preferredLanguage,
    required ScrapingProvider scrapingProvider,
    required bool Function()? shouldCancel,
    required Map<String, dynamic> scraperConfig,
    FileProvider? fileProvider,
    Set<GameBoxMediaKind> boxKinds = const {},
    bool extraSources = true,
  }) async {
    try {
      final scrapeMode = scraperConfig['scrape_mode'].toString();
      final filename = rom['filename'].toString();
      final romPath = rom['rom_path'].toString();
      final titleName = rom['title_name']?.toString();
      final titleId = rom['title_id']?.toString().trim();
      final lowerRomPath = romPath.toLowerCase();
      final isMeloNxVirtual = lowerRomPath.startsWith('melonx://');
      final isRpcs3Virtual = lowerRomPath.startsWith('rpcs3-library://');
      var effectiveTitleName = titleName;
      if (isRpcs3Virtual &&
          !shouldRetryRpcs3ByNameForTesting(effectiveTitleName, titleId) &&
          (titleId?.isNotEmpty ?? false)) {
        effectiveTitleName =
            await Rpcs3TitleCatalogService.resolveTitle(titleId!) ??
            effectiveTitleName;
      }
      final displayName =
          (isMeloNxVirtual || isRpcs3Virtual) &&
              (effectiveTitleName?.trim().isNotEmpty ?? false)
          ? effectiveTitleName!.trim()
          : filename;

      scrapingProvider.updateThreadProgress(
        threadId: threadId,
        gameName: displayName,
        systemName: systemName,
        isActive: true,
        status: ThreadStatus.active,
        currentStep: ThreadProcessingStep.fetchingMetadata,
        progress: 0.0,
      );

      if (shouldCancel != null && shouldCancel()) {
        return {'success': false, 'cancelled': true, 'requests': 0};
      }

      // The library game the box faces belong to (null without a file
      // provider: the box-face steps are then skipped). The system's box
      // profile is read first: the context keeps the profile it is built with.
      String? scrapedName;
      if (fileProvider != null && boxKinds.isNotEmpty) {
        await GameBoxProfiles.load(appSystemId);
        scrapedName = (await ScraperRepository.getGameMetadata(appSystemId, filename))?['real_name']?.toString();
      }
      GameBoxSearchContext? boxContext(String? name) {
        if (fileProvider == null || boxKinds.isEmpty) return null;
        return GameBoxSearchContext(
          game: GameBoxBatch.gameOf(
            romName: filename,
            romPath: romPath,
            name: name ?? scrapedName ?? effectiveTitleName,
            titleId: titleId,
            titleName: titleName,
            appSystemId: appSystemId,
            systemFolder: systemFolder,
          ),
          systemFolder: systemFolder,
          fileProvider: fileProvider,
          profile: GameBoxProfiles.of(appSystemId),
          appSystemId: appSystemId,
        );
      }

      Map<String, dynamic> faceStats(GameBoxBatchOutcome outcome) {
        final bySource = <String, int>{};
        for (final provider in outcome.adopted.values) {
          bySource[provider.id] = (bySource[provider.id] ?? 0) + 1;
        }
        return {'facesBySource': bySource, 'facesMissing': outcome.missing.length};
      }

      // "Box faces only": no ScreenScraper scrape; the faces the media
      // choices ask for that are missing, refused or an imported icon are
      // looked for in every source (docs/game-box-3d.md § 18).
      if (scrapeMode == 'faces_only') {
        final ctx = boxContext(null);
        if (ctx == null) {
          return {'success': true, 'cancelled': false, 'requests': 0};
        }
        scrapingProvider.updateThreadProgress(
          threadId: threadId,
          gameName: displayName,
          systemName: systemName,
          isActive: true,
          status: ThreadStatus.active,
          currentStep: ThreadProcessingStep.downloadingImages,
          progress: 0.5,
        );
        final outcome = await GameBoxBatch.complete(
          ctx,
          kinds: boxKinds,
          askScreenScraper: true,
          extraSources: extraSources,
          cancel: GameBoxBatchCancel(shouldCancel),
        );
        if (shouldCancel != null && shouldCancel()) {
          return {'success': false, 'cancelled': true, 'requests': 0};
        }
        scrapingProvider.updateThreadProgress(
          threadId: threadId,
          gameName: displayName,
          systemName: systemName,
          isActive: false,
          status: ThreadStatus.completed,
          currentStep: ThreadProcessingStep.completed,
          progress: 1.0,
        );
        // A face no source has is not a failed game: the summary counts it
        // under "box faces still missing".
        return {
          'success': true,
          'cancelled': false,
          'requests': 0,
          ...faceStats(outcome),
        };
      }

      var matchedBy = isRpcs3Virtual && (titleId?.isNotEmpty ?? false)
          ? GameBoxMatch.serial
          : GameBoxMatch.fileName;
      final gameResult = await fetchGameInfo(
        screenscraperSystemId.toString(),
        filename,
        appSystemId: appSystemId,
        maxDailyRequests: maxDailyRequests,
        gameName:
            (systemFolder == 'android' || isMeloNxVirtual || isRpcs3Virtual)
            ? effectiveTitleName
            : null,
        serialNumber: isRpcs3Virtual ? titleId : null,
      );
      var gameInfo = gameResult?['gameInfo'];
      int requestsMade = 1;

      if (gameInfo == null &&
          isRpcs3Virtual &&
          shouldRetryRpcs3ByNameForTesting(effectiveTitleName, titleId)) {
        final nameResult = await fetchGameInfo(
          screenscraperSystemId.toString(),
          filename,
          appSystemId: appSystemId,
          maxDailyRequests: maxDailyRequests,
          gameName: effectiveTitleName,
          serialNumber: null,
        );
        gameInfo = nameResult?['gameInfo'];
        matchedBy = GameBoxMatch.title;
        requestsMade++;
      }

      if (gameResult?['userInfo'] != null) {
        final ui = gameResult!['userInfo'];
        scrapingProvider.updateProgress(
          totalRequests:
              int.tryParse(ui['requeststoday']?.toString() ?? '0') ?? 0,
          maxDailyRequests:
              int.tryParse(ui['maxrequestsperday']?.toString() ?? '0') ?? 0,
        );
      }

      scrapingProvider.updateThreadProgress(
        threadId: threadId,
        gameName: displayName,
        systemName: systemName,
        isActive: true,
        status: ThreadStatus.active,
        currentStep: ThreadProcessingStep.scanningImages,
        progress: 0.33,
      );

      if (shouldCancel != null && shouldCancel()) {
        return {'success': false, 'cancelled': true, 'requests': requestsMade};
      }
      final romFile = File(romPath);
      if (gameInfo == null && systemFolder != 'android' && romFile.existsSync()) {
        final size = romFile.lengthSync();
        if (size <= batchMd5Limit) {
          final hash = await ScreenscraperRomHasher.calculateMd5InIsolate(
            romPath,
          );
          if (shouldCancel != null && shouldCancel()) {
            return {'success': false, 'cancelled': true, 'requests': requestsMade};
          }
          final resWithHash = await fetchGameInfo(
            screenscraperSystemId.toString(),
            filename,
            appSystemId: appSystemId,
            md5: hash,
            maxDailyRequests: maxDailyRequests,
          );
          gameInfo = resWithHash?['gameInfo'];
          if (gameInfo != null) matchedBy = GameBoxMatch.md5;
          requestsMade++;
        } else {
          // A disc or cartridge image of several gigabytes takes minutes to
          // read on the device: the run would seem stopped. Its bare title
          // (without [0100…][v0] or (Europe) tags) is asked instead
          // (docs/game-box-3d.md § 19).
          _log.i('Scraper: $systemFolder/$filename is ${size ~/ (1024 * 1024)} MB: '
              'no MD5 (limit ${batchMd5Limit ~/ (1024 * 1024)} MB), looked up by name');
          final bare = bareTitleOf(filename);
          if (bare.isNotEmpty && bare != FileProvider.stripRomExtension(filename)) {
            final byTitle = await fetchGameInfo(
              screenscraperSystemId.toString(),
              filename,
              appSystemId: appSystemId,
              maxDailyRequests: maxDailyRequests,
              gameName: bare,
            );
            gameInfo = byTitle?['gameInfo'];
            if (gameInfo != null) matchedBy = GameBoxMatch.title;
            requestsMade++;
          }
        }
      }
      if (gameInfo == null) {
        _log.w('Scraper: $systemFolder/$filename: not found on ScreenScraper');
      }

      if (gameInfo != null) {
        String? gameName;
        if (scraperConfig['scrape_metadata'] as bool? ?? true) {
          final metadata = await _mapGameInfoToMetadata(
            filename,
            romPath,
            gameInfo,
            preferredLanguage: preferredLanguage,
          );
          gameName = metadata['real_name']?.toString();
          await _saveGameMetadata(metadata, appSystemId, isFullyScraped: false);
        }

        final allowedTypes = await ScraperRepository.getEnabledMediaTypes();
        final boxCtx = boxContext(gameName);
        // Faces chosen by hand or by the ranked sources are not written by
        // the plain download (docs/game-box-3d.md § 18).
        final ownedTypes = boxCtx == null
            ? const <String>{}
            : GameBoxBatch.ownedTypes(
                GameBoxMediaStore(boxCtx.fileProvider).read(boxCtx.game, systemFolder),
              );
        var mediaAdded = 0, mediaReplaced = 0;
        var faces = <String, dynamic>{};

        if (allowedTypes.isNotEmpty) {
          scrapingProvider.updateThreadProgress(
            threadId: threadId,
            gameName: displayName,
            systemName: systemName,
            isActive: true,
            status: ThreadStatus.active,
            currentStep: ThreadProcessingStep.downloadingImages,
            progress: 0.66,
          );
          final sourceMedias = gameInfo['medias'] as List<dynamic>? ?? [];
          if (shouldCancel != null && shouldCancel()) {
            return {'success': false, 'cancelled': true, 'requests': requestsMade};
          }
          // One media at a time per game: the run's threads already use all
          // the account's request slots; more would wait for a slot until
          // the 15 s limit fails them (docs/game-box-3d.md § 19).
          final res = await ScreenscraperMediaDownloader.downloadGameMedia(
            systemFolder,
            filename,
            sourceMedias,
            1,
            appSystemId: appSystemId,
            preferredLanguage: preferredLanguage,
            shouldCancel: shouldCancel,
            allowedMediaTypes: allowedTypes,
            maxDailyRequests: maxDailyRequests,
            // Imported console icons are replaced in every mode; what is
            // already present is replaced by "All content" only.
            forceOverwrite: scrapeMode == 'all',
            protectedTypes: ownedTypes,
            replaceOtherVariants: scrapeMode == 'new_only',
          );
          final replaced = (res['replacedTypes'] as List<dynamic>? ?? const []).length;
          mediaReplaced += replaced;
          mediaAdded += (res['downloadedTypes'] as List<dynamic>? ?? const []).length - replaced;
          if (res['cancelled'] == true) {
            return {
              'success': false,
              'cancelled': true,
              'requests': requestsMade,
            };
          }

          var mediaSucceeded = res['success'] == true;
          if (isMeloNxVirtual || isRpcs3Virtual) {
            final successfulTypes = await _ensureVirtualMediaByGameId(
              isMeloNxVirtual: isMeloNxVirtual,
              isRpcs3Virtual: isRpcs3Virtual,
              gameInfo: Map<String, dynamic>.from(gameInfo as Map),
              screenScraperSystemId: screenscraperSystemId,
              systemFolder: systemFolder,
              romName: filename,
              appSystemId: appSystemId,
              allowedMediaTypes: allowedTypes,
              downloadResult: res,
              sourceMedias: sourceMedias,
              maxDailyRequests: maxDailyRequests,
              keepExisting: scrapeMode != 'all',
            );
            mediaSucceeded = _hasUsefulVirtualMedia(
              allowedTypes,
              successfulTypes,
            );
          }

          if (mediaSucceeded) {
            await ScraperRepository.markGameFullyScraped(filename);
          }

          // The box faces still missing, refused or an imported icon: other
          // ScreenScraper scans first (no request, the answer is reused),
          // then GameTDB and MobyGames when enabled.
          if (boxCtx != null && !(shouldCancel?.call() ?? false)) {
            final listing = GameBoxMediaFetcher.listingOf(
              game: boxCtx.game,
              jeu: gameInfo as Map,
              screenScraperSystemId: screenscraperSystemId.toString(),
              matchedBy: matchedBy,
              systemFolder: systemFolder,
              fileProvider: boxCtx.fileProvider,
            );
            faces = faceStats(
              await GameBoxBatch.complete(
                boxCtx,
                kinds: boxKinds,
                screenScraperListing: listing,
                extraSources: extraSources,
                cancel: GameBoxBatchCancel(shouldCancel),
                // The game is scraped again (new, reopened by a change of
                // choices, or "All content"): a face of another language
                // gives way to the print in the scraping language.
                upgradeLanguage: true,
              ),
            );
          }

          // A French manual still missing: the edition's own on the Internet
          // Archive, Nintendo Europe's for a DS game, then by exact title
          // (docs/game-box-3d.md § 26).
          if (boxCtx != null &&
              extraSources &&
              allowedTypes.contains('manuel') &&
              '$preferredLanguage'.toLowerCase().startsWith('fr') &&
              !(shouldCancel?.call() ?? false)) {
            final clean = await ScreenscraperRomHasher.getCleanRomName(filename, appSystemId);
            final root = await ScreenscraperMediaResolver.getMediaDirectory();
            final found = await GameManualFrenchSources.fill(
              boxCtx.game,
              appSystemId,
              path.join(root, systemFolder, 'manuals', '$clean.pdf'),
            );
            if (found != null) mediaAdded++;
          }
        }

        scrapingProvider.updateThreadProgress(
          threadId: threadId,
          gameName: displayName,
          systemName: systemName,
          isActive: false,
          status: ThreadStatus.completed,
          currentStep: ThreadProcessingStep.completed,
          progress: 1.0,
        );
        return {
          'success': true,
          'cancelled': false,
          'requests': requestsMade,
          'mediaAdded': mediaAdded,
          'mediaReplaced': mediaReplaced,
          ...faces,
        };
      }
      return {'success': false, 'cancelled': false, 'requests': requestsMade};
    } on ScreenscraperQuotaExceededException {
      rethrow;
    } catch (e) {
      return {'success': false, 'cancelled': false, 'requests': 0};
    }
  }

  /// Displays the final results of a scraping session in a localized dialog.
  static void _showScrapingSummaryDialog(
    BuildContext context, {
    required int totalGames,
    required int successfulGames,
    required int failedGames,
    required String elapsedTime,
    required int totalRequests,
    int mediaAdded = 0,
    int mediaReplaced = 0,
    Map<String, int> facesBySource = const {},
    int facesMissing = 0,
  }) async {
    await showDialog(
      context: context,
      barrierDismissible: true,
      builder: (BuildContext context) => ScrapingSummaryDialog(
        totalGames: totalGames,
        successfulGames: successfulGames,
        failedGames: failedGames,
        elapsedTime: elapsedTime,
        mediaAdded: mediaAdded,
        mediaReplaced: mediaReplaced,
        facesBySource: facesBySource,
        facesMissing: facesMissing,
      ),
    );
  }
}
