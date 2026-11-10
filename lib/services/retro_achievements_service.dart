import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:neostation/services/logger_service.dart';
import '../models/retro_achievements_user.dart';
import '../models/retro_achievements_summary.dart';
import '../models/retro_achievements_game_info.dart';
import '../models/retro_achievements_gotw.dart';
import '../models/retro_achievement_comment.dart';
import '../models/retro_achievements_dashboard_models.dart';

/// Why a Web API sign-in request failed. Carries no URL, key or response body.
enum RetroAchievementsWebFailure { rejected, notFound, network, rateLimited, server }

class RetroAchievementsWebException implements Exception {
  const RetroAchievementsWebException(this.failure, [this.statusCode]);
  final RetroAchievementsWebFailure failure;
  final int? statusCode;

  @override
  String toString() => 'RetroAchievementsWebException(${failure.name}'
      '${statusCode == null ? '' : ', HTTP $statusCode'})';
}

/// Service for interacting with the RetroAchievements API.
///
/// Provides access to user profiles, game achievements, and global community
/// events like "Achievement of the Week". Every request is authenticated with
/// the *user's own* RetroAchievements web API key, supplied at connect time.
///
/// There is deliberately no build-time/environment fallback key: earlier
/// versions silently authenticated every user's traffic with the maintainer's
/// key, which is incorrect. A caller that passes no key gets an empty string
/// and the request-level guards reject it.
class RetroAchievementsService {
  static const String _baseUrl = 'https://retroachievements.org/API';

  /// Returns the trimmed [apiKey], or an empty string if none was supplied.
  /// Callers must pass the signed-in user's key; there is no shared fallback.
  static String resolveApiKey(String? apiKey) => apiKey?.trim() ?? '';

  static final _log = LoggerService.instance;

  /// Fetches the "Achievement of the Week" (GOTW) data.
  ///
  /// Optionally takes a [username] to include user-specific progress toward the achievement.
  static Future<RetroAchievementsGOTW?> getAchievementOfTheWeek({
    String? username,
    String? apiKey,
  }) async {
    final effectiveApiKey = resolveApiKey(apiKey);
    if (effectiveApiKey.isEmpty) {
      throw StateError('A RetroAchievements API key is required');
    }

    final url = Uri.parse(
      '$_baseUrl/API_GetAchievementOfTheWeek.php',
    ).replace(queryParameters: {'y': effectiveApiKey});

    final response = await http.get(
      url,
      headers: {'User-Agent': 'NeoStation/1.0', 'Accept': 'application/json'},
    );

    if (response.statusCode != 200) {
      throw HttpException(
        'RetroAchievements achievement of the week request failed (${response.statusCode})',
      );
    }

    final data = json.decode(response.body);
    if (data != null && data['Achievement'] != null) {
      return RetroAchievementsGOTW.fromJson(data);
    }
    if (data != null && data['Error'] != null) {
      _log.e('API Error: ${data['Error']}');
    }
    return null;
  }

  /// Mapping of NeoStation system identifiers to RetroAchievements console IDs.
  static const Map<String, int> _systemMapping = {
    'nes': 7,
    'snes': 3,
    'gb': 4,
    'gbc': 6,
    'gba': 5,
    'n64': 2,
    'gcn': 16,
    'wii': 82,
    'nds': 18,
    // Reserved console ID, not an assertion of native achievement support.
    // The central capability policy keeps 3DS disabled until official rollout.
    '3ds': 62,
    'genesis': 1,
    'sms': 11,
    'gg': 15,
    'saturn': 39,
    'dreamcast': 40,
    'psx': 12,
    'ps2': 21,
    'psp': 41,
    'atari2600': 25,
    'atari7800': 51,
    'lynx': 13,
    'neogeo': 56,
    'arcade': 27,
    'msx': 29,
  };

  /// Returns the RetroAchievements console ID for a given NeoStation system name.
  static int? getConsoleIdForSystem(String systemFolderName) {
    return _systemMapping[systemFolderName.toLowerCase()];
  }

  /// Retrieves basic profile information for a RetroAchievements user.
  ///
  /// Returns null only when RetroAchievements answered that the user does not
  /// exist. A refused Web API key, an unreachable server and an unexpected
  /// response are reported as [RetroAchievementsWebException] so the sign-in
  /// form can tell an input error, an authentication refusal and a network
  /// problem apart. Neither the key nor the request URL is logged.
  static Future<RetroAchievementsUser?> getUserProfile(
    String username, {
    String? apiKey,
  }) async {
    final url = Uri.parse(
      '$_baseUrl/API_GetUserProfile.php',
    ).replace(queryParameters: {'u': username, 'y': resolveApiKey(apiKey)});
    final http.Response response;
    try {
      response = await http
          .get(
            url,
            headers: {'User-Agent': 'NeoStation/1.0', 'Accept': 'application/json'},
          )
          .timeout(const Duration(seconds: 20));
    } catch (e) {
      // Socket, TLS, DNS and timeout failures: the request never got an answer.
      _log.w('RetroAchievements profile request failed before a response (${e.runtimeType})');
      throw const RetroAchievementsWebException(RetroAchievementsWebFailure.network);
    }
    final failure = classifyProfileStatus(response.statusCode);
    if (failure != null) {
      _log.w('RetroAchievements profile request answered HTTP ${response.statusCode} (${failure.name})');
      if (failure == RetroAchievementsWebFailure.notFound) return null;
      throw RetroAchievementsWebException(failure, response.statusCode);
    }
    final Object? data;
    try {
      data = json.decode(response.body);
    } catch (_) {
      // A captive portal or a proxy error page is not a credential refusal.
      _log.w('RetroAchievements profile response was not JSON');
      throw RetroAchievementsWebException(RetroAchievementsWebFailure.server, response.statusCode);
    }
    if (data is Map<String, dynamic> && data['User'] is String &&
        (data['User'] as String).trim().isNotEmpty) {
      return RetroAchievementsUser.fromJson(data);
    }
    _log.w('RetroAchievements profile response has no user record');
    return null;
  }

  /// Maps a Web API status to the failure shown to the player, or null for a
  /// usable 200 response. 401/403 mean the key was refused; 404/422 mean the
  /// requested username is unknown or malformed.
  static RetroAchievementsWebFailure? classifyProfileStatus(int status) {
    if (status == 200) return null;
    if (status == 401 || status == 403) return RetroAchievementsWebFailure.rejected;
    if (status == 404 || status == 422) return RetroAchievementsWebFailure.notFound;
    if (status == 429) return RetroAchievementsWebFailure.rateLimited;
    return RetroAchievementsWebFailure.server;
  }

  /// Fetches a comprehensive summary for a user, including recent games and achievements.
  ///
  /// Employs a cache-busting timestamp to ensure fresh data.
  static Future<RetroAchievementsUserSummary?> getUserSummary(
    String username, {
    String? apiKey,
  }) async {
    try {
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final url = Uri.parse('$_baseUrl/API_GetUserSummary.php').replace(
        queryParameters: {
          'u': username,
          'g': '1', // Include recent games
          'a': '2', // Include recent achievements
          'y': resolveApiKey(apiKey),
          '_t': timestamp.toString(),
        },
      );

      final response = await http.get(
        url,
        headers: {
          'User-Agent': 'NeoStation/1.0',
          'Accept': 'application/json',
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          'Pragma': 'no-cache',
          'Expires': '0',
        },
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);

        if (data is Map && data['User'] != null) {
          return RetroAchievementsUserSummary.fromJson(
            data as Map<String, dynamic>,
          );
        } else if (data is List) {
          if (data.isNotEmpty && data.first is Map) {
            final userData = data.first as Map<String, dynamic>;
            if (userData['User'] != null) {
              return RetroAchievementsUserSummary.fromJson(userData);
            }
          }
          _log.e('Unexpected response: list without valid data');
          return null;
        } else {
          _log.e('User not found or invalid response: $username');
          return null;
        }
      } else {
        _log.e('HTTP error ${response.statusCode}: ${response.body}');
        return null;
      }
    } catch (e) {
      _log.e('Error getting user summary: $e');
      return null;
    }
  }

  /// Retrieves detailed information for a specific game and the user's progress.
  ///
  /// Can take an [md5Hash] for more accurate game identification within the RA database.
  static Future<GameInfoAndUserProgress?> getGameInfoAndUserProgress(
    int gameId,
    String username, {
    String? md5Hash,
    String? apiKey,
  }) async {
    try {
      final timestamp = DateTime.now().millisecondsSinceEpoch;
      final queryParams = {
        'g': gameId.toString(),
        'u': username,
        'y': resolveApiKey(apiKey),
        'a': '1', // Include achievements
        '_t': timestamp.toString(),
      };

      final url = Uri.parse(
        '$_baseUrl/API_GetGameInfoAndUserProgress.php',
      ).replace(queryParameters: queryParams);

      final response = await http.get(
        url,
        headers: {
          'User-Agent': 'NeoStation/1.0',
          'Accept': 'application/json',
          'Cache-Control': 'no-cache, no-store, must-revalidate',
          'Pragma': 'no-cache',
          'Expires': '0',
        },
      );

      if (response.statusCode == 200) {
        final data = json.decode(response.body);

        if (data['ID'] != null) {
          return GameInfoAndUserProgress.fromJson(data);
        } else {
          _log.e('Game not found: $gameId');
          return null;
        }
      } else {
        _log.e('HTTP error ${response.statusCode}: ${response.body}');
        return null;
      }
    } catch (e) {
      _log.e('Error getting game information: $e');
      return null;
    }
  }

  /// Retrieves newest-first comments from an achievement's RA page.
  static Future<RetroAchievementCommentsPage> getAchievementComments(
    int achievementId, {
    int count = 25,
    int offset = 0,
    String? apiKey,
    http.Client? client,
  }) async {
    final effectiveApiKey = resolveApiKey(apiKey);
    if (effectiveApiKey.isEmpty) {
      throw StateError('A RetroAchievements API key is required');
    }

    final url = Uri.parse('$_baseUrl/API_GetComments.php').replace(
      queryParameters: {
        't': '2',
        'i': achievementId.toString(),
        'c': count.clamp(1, 500).toString(),
        'o': offset.clamp(0, 1 << 31).toString(),
        'sort': '-submitted',
        'y': effectiveApiKey,
      },
    );
    final headers = {
      'User-Agent': 'NeoStation/1.0',
      'Accept': 'application/json',
    };
    final response = client == null
        ? await http.get(url, headers: headers)
        : await client.get(url, headers: headers);
    if (response.statusCode != 200) {
      throw HttpException(
        'RetroAchievements comments request failed (${response.statusCode})',
      );
    }

    final decoded = json.decode(response.body);
    if (decoded is! Map) {
      throw const FormatException(
        'Invalid RetroAchievements comments response',
      );
    }
    return RetroAchievementCommentsPage.fromJson(
      Map<String, dynamic>.from(decoded),
    );
  }

  static const String apiGetUserAwards = 'API_GetUserAwards.php';

  static Future<List<RetroAchievementRecentUnlockItem>>
  getUserRecentAchievements(
    String username, {
    int minutes = 43200,
    String? apiKey,
    http.Client? client,
  }) async {
    final url = Uri.parse('$_baseUrl/API_GetUserRecentAchievements.php')
        .replace(
          queryParameters: {
            'u': username,
            'm': minutes.toString(),
            'y': resolveApiKey(apiKey),
          },
        );

    final headers = {
      'User-Agent': 'NeoStation/1.0',
      'Accept': 'application/json',
    };
    final response = client == null
        ? await http.get(url, headers: headers)
        : await client.get(url, headers: headers);

    if (response.statusCode != 200) {
      throw HttpException(
        'RetroAchievements recent achievements request failed (${response.statusCode})',
      );
    }

    final decoded = json.decode(response.body);
    if (decoded is! List) {
      throw const FormatException(
        'Invalid RetroAchievements recent achievements response',
      );
    }

    return decoded
        .map(
          (item) => RetroAchievementRecentUnlockItem.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .toList();
  }

  static Future<List<RetroAchievementRecentlyPlayedGameItem>>
  getUserRecentlyPlayedGames(
    String username, {
    int count = 10,
    int offset = 0,
    String? apiKey,
    http.Client? client,
  }) async {
    final url = Uri.parse('$_baseUrl/API_GetUserRecentlyPlayedGames.php')
        .replace(
          queryParameters: {
            'u': username,
            'c': count.clamp(1, 50).toString(),
            'o': offset.clamp(0, 1 << 31).toString(),
            'y': resolveApiKey(apiKey),
          },
        );

    final headers = {
      'User-Agent': 'NeoStation/1.0',
      'Accept': 'application/json',
    };
    final response = client == null
        ? await http.get(url, headers: headers)
        : await client.get(url, headers: headers);

    if (response.statusCode != 200) {
      throw HttpException(
        'RetroAchievements recently played request failed (${response.statusCode})',
      );
    }

    final decoded = json.decode(response.body);
    if (decoded is! List) {
      throw const FormatException(
        'Invalid RetroAchievements recently played response',
      );
    }

    return decoded
        .map(
          (item) => RetroAchievementRecentlyPlayedGameItem.fromJson(
            Map<String, dynamic>.from(item as Map),
          ),
        )
        .toList();
  }

  static Future<RetroAchievementCompletionProgressSummary>
  getUserCompletionProgress(
    String username, {
    int count = 100,
    int offset = 0,
    String? apiKey,
    http.Client? client,
  }) async {
    final url = Uri.parse('$_baseUrl/API_GetUserCompletionProgress.php')
        .replace(
          queryParameters: {
            'u': username,
            'c': count.clamp(1, 500).toString(),
            'o': offset.clamp(0, 1 << 31).toString(),
            'y': resolveApiKey(apiKey),
          },
        );

    final headers = {
      'User-Agent': 'NeoStation/1.0',
      'Accept': 'application/json',
    };
    final response = client == null
        ? await http.get(url, headers: headers)
        : await client.get(url, headers: headers);

    if (response.statusCode != 200) {
      throw HttpException(
        'RetroAchievements completion progress request failed (${response.statusCode})',
      );
    }

    final decoded = json.decode(response.body);
    if (decoded is! Map) {
      throw const FormatException(
        'Invalid RetroAchievements completion progress response',
      );
    }

    return RetroAchievementCompletionProgressSummary.fromJson(
      Map<String, dynamic>.from(decoded),
    );
  }

  /// Retrieves the list of site-wide awards earned by a user.
  static Future<Map<String, dynamic>?> getUserAwards(
    String username, {
    String? apiKey,
  }) async {
    final effectiveApiKey = resolveApiKey(apiKey);
    if (effectiveApiKey.isEmpty) {
      throw StateError('A RetroAchievements API key is required');
    }

    final timestamp = DateTime.now().millisecondsSinceEpoch;
    final url = Uri.parse('$_baseUrl/$apiGetUserAwards').replace(
      queryParameters: {
        'u': username,
        'y': effectiveApiKey,
        '_t': timestamp.toString(),
      },
    );

    final response = await http.get(
      url,
      headers: {
        'User-Agent': 'NeoStation/1.0',
        'Accept': 'application/json',
        'Cache-Control': 'no-cache, no-store, must-revalidate',
        'Pragma': 'no-cache',
        'Expires': '0',
      },
    );

    if (response.statusCode != 200) {
      throw HttpException(
        'RetroAchievements user awards request failed (${response.statusCode})',
      );
    }

    final data = json.decode(response.body);
    return data as Map<String, dynamic>;
  }
}
