import '../models/retro_achievements_dashboard_models.dart';
import '../models/retro_achievements_game_info.dart';
import '../models/retro_achievements_gotw.dart';
import '../models/retro_achievements_summary.dart';
import '../models/retro_achievements_user.dart';
import '../repositories/retro_achievements_repository.dart';
import '../services/retro_achievements_service.dart';

/// The existing Web API and credential storage, injectable independently of
/// the native emulator account. This source never receives a game login token.
class RetroAchievementsDashboardSource {
  const RetroAchievementsDashboardSource();

  Future<RetroAchievementsUser?> getUserProfile(String username, String apiKey) =>
      RetroAchievementsService.getUserProfile(username, apiKey: apiKey);

  Future<RetroAchievementsUserSummary?> getUserSummary(
    String username,
    String apiKey,
  ) => RetroAchievementsService.getUserSummary(username, apiKey: apiKey);

  Future<RetroAchievementsGOTW?> getAchievementOfTheWeek(String apiKey) =>
      RetroAchievementsService.getAchievementOfTheWeek(apiKey: apiKey);

  Future<Map<String, dynamic>?> getUserAwards(String username, String apiKey) =>
      RetroAchievementsService.getUserAwards(username, apiKey: apiKey);

  Future<GameInfoAndUserProgress?> getGameInfoAndUserProgress(
    int gameId,
    String username,
    String apiKey, {
    String? md5Hash,
  }) => RetroAchievementsService.getGameInfoAndUserProgress(
    gameId,
    username,
    md5Hash: md5Hash,
    apiKey: apiKey,
  );

  Future<RetroAchievementCompletionProgressSummary> getUserCompletionProgress(
    String username,
    String apiKey,
  ) => RetroAchievementsService.getUserCompletionProgress(
    username,
    apiKey: apiKey,
  );

  Future<List<RetroAchievementRecentlyPlayedGameItem>> getUserRecentlyPlayedGames(
    String username,
    String apiKey,
  ) => RetroAchievementsService.getUserRecentlyPlayedGames(
    username,
    apiKey: apiKey,
  );

  Future<List<RetroAchievementRecentUnlockItem>> getUserRecentAchievements(
    String username,
    String apiKey,
  ) => RetroAchievementsService.getUserRecentAchievements(
    username,
    apiKey: apiKey,
  );

  Future<OwnedWeekGameResolution?> findBestLocalGameByRaGameId(int gameId) =>
      RetroAchievementsRepository.findBestLocalGameByRaGameId(gameId);

  Future<String?> readUsername() => RetroAchievementsRepository.getRAUser();
  Future<String?> readApiKey() => RetroAchievementsRepository.getRAApiKey();
  Future<void> saveUsername(String username) =>
      RetroAchievementsRepository.saveRAUser(username);
  Future<void> saveApiKey(String apiKey) =>
      RetroAchievementsRepository.saveRAApiKey(apiKey);
  Future<void> clearUsername() => RetroAchievementsRepository.clearRAUser();
  Future<void> clearApiKey() => RetroAchievementsRepository.clearRAApiKey();
}
