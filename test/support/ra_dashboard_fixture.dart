import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/retro_achievements_dashboard_models.dart';
import 'package:neostation/models/retro_achievements_game_info.dart';
import 'package:neostation/models/retro_achievements_gotw.dart';
import 'package:neostation/models/retro_achievements_session.dart';
import 'package:neostation/models/retro_achievements_summary.dart';
import 'package:neostation/models/retro_achievements_user.dart';
import 'package:neostation/providers/retro_achievements_dashboard_source.dart';
import 'package:neostation/services/retro_achievements_session_service.dart';
import 'package:retro_achievements_session/retro_achievements_session.dart';

/// Only the Web API/storage boundary is faked; tests run the real provider and
/// central service. No request can escape to the network or a real database.
class RADashboardFixture extends RetroAchievementsDashboardSource {
  String? savedUsername;
  String? savedApiKey;
  bool readsFail = false;
  Completer<void>? readGate;
  Completer<void>? writeGate;
  Completer<void>? writeStarted;
  final writes = <String>[];
  final profiles = <(String, String)>[];
  final games = <(int, String, String)>[];

  Future<RetroAchievementsUser?> Function(String, String)? profile;
  Future<RetroAchievementsUserSummary?> Function(String, String)? summary;
  Future<Map<String, dynamic>?> Function(String, String)? awards;
  Future<GameInfoAndUserProgress?> Function(int, String, String)? game;
  Future<RetroAchievementCompletionProgressSummary> Function(String, String)? completion;
  Future<List<RetroAchievementRecentlyPlayedGameItem>> Function(String, String)? recentGames;
  Future<List<RetroAchievementRecentUnlockItem>> Function(String, String)? recentUnlocks;
  Future<RetroAchievementsGOTW?> Function(String)? week;
  Future<OwnedWeekGameResolution?> Function(int)? ownedWeek;

  @override
  Future<RetroAchievementsUser?> getUserProfile(String username, String apiKey) {
    profiles.add((username, apiKey));
    return profile?.call(username, apiKey) ??
        Future.value(RetroAchievementsUser.fromJson({'User': username}));
  }

  @override
  Future<RetroAchievementsUserSummary?> getUserSummary(String username, String apiKey) =>
      summary?.call(username, apiKey) ??
      Future.value(RetroAchievementsUserSummary.fromJson({'User': username}));

  @override
  Future<Map<String, dynamic>?> getUserAwards(String username, String apiKey) =>
      awards?.call(username, apiKey) ?? Future.value({'UserAwards': <Object>[]});

  @override
  Future<GameInfoAndUserProgress?> getGameInfoAndUserProgress(int gameId,
      String username, String apiKey, {String? md5Hash}) {
    games.add((gameId, username, apiKey));
    return game?.call(gameId, username, apiKey) ?? Future.value(
      GameInfoAndUserProgress.fromJson({'ID': gameId, 'Title': '$username progress'}),
    );
  }

  @override
  Future<RetroAchievementCompletionProgressSummary> getUserCompletionProgress(
      String username, String apiKey) => completion?.call(username, apiKey) ??
      Future.value(const RetroAchievementCompletionProgressSummary(count: 0, total: 0, results: []));

  @override
  Future<List<RetroAchievementRecentlyPlayedGameItem>> getUserRecentlyPlayedGames(
      String username, String apiKey) => recentGames?.call(username, apiKey) ?? Future.value([]);

  @override
  Future<List<RetroAchievementRecentUnlockItem>> getUserRecentAchievements(
      String username, String apiKey) => recentUnlocks?.call(username, apiKey) ?? Future.value([]);

  @override
  Future<RetroAchievementsGOTW?> getAchievementOfTheWeek(String apiKey) =>
      week?.call(apiKey) ?? Future.value(null);

  @override
  Future<OwnedWeekGameResolution?> findBestLocalGameByRaGameId(int gameId) =>
      ownedWeek?.call(gameId) ?? Future.value(null);

  @override
  Future<String?> readUsername() async {
    await readGate?.future;
    if (readsFail) throw StateError('fixture storage unavailable');
    return savedUsername;
  }

  @override
  Future<String?> readApiKey() async {
    await readGate?.future;
    if (readsFail) throw StateError('fixture storage unavailable');
    return savedApiKey;
  }

  @override
  Future<void> saveUsername(String username) async {
    if (writeStarted?.isCompleted == false) writeStarted!.complete();
    await writeGate?.future;
    writes.add('username:$username');
    savedUsername = username;
  }

  @override
  Future<void> saveApiKey(String apiKey) async {
    writes.add('key:$apiKey');
    savedApiKey = apiKey;
  }

  @override
  Future<void> clearUsername() async {
    writes.add('clear:username');
    savedUsername = null;
  }

  @override
  Future<void> clearApiKey() async {
    writes.add('clear:key');
    savedApiKey = null;
  }
}

/// The native method channel is the boundary; policy serialization, snapshots,
/// account notifications and failure handling run in the production service.
class RANativeFixture {
  RANativeFixture({this.username = 'Alice', bool available = true}) {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      switch (call.method) {
        case 'account':
          if (accountFailures > 0) {
            accountFailures--;
            throw PlatformException(code: 'RA_STORAGE_UNAVAILABLE');
          }
          return account;
        case 'login':
          await loginGate?.future;
          if (loginError != null) throw PlatformException(code: loginError!);
          username = (call.arguments as Map)['username'] as String;
          return account;
        case 'logout': username = ''; return account;
        case 'prepareSession':
          final args = Map<String, Object?>.from(call.arguments as Map);
          final enabled = args['enabled'] == true && args['supported'] == true;
          return {'raSessionId': 'fixture-session', 'enabled': enabled,
            'supported': args['supported'], 'hardcore': enabled && args['hardcore'] == true};
        case 'finishSession':
        case 'completeLegacy': return <String, Object?>{};
        default: throw StateError('Unexpected native fixture method ${call.method}');
      }
    });
    client = RetroAchievementsNativeClient(channel: channel, available: available);
    service = RetroAchievementsSessionService(native: client,
      readPreferences: () async => preferences,
      writePreferences: (value) async { preferences = value; });
  }

  static const channel = MethodChannel('test/rewindbox/ra-account-fixture');
  String username;
  String? loginError;
  /// Transient Keychain/database read failures before `account` succeeds.
  int accountFailures = 0;
  Completer<void>? loginGate;
  final calls = <MethodCall>[];
  RetroAchievementsPreferences preferences = const RetroAchievementsPreferences(migrationVersion: 1);
  late final RetroAchievementsNativeClient client;
  late final RetroAchievementsSessionService service;
  Map<String, Object?> get account => {'authenticated': username.isNotEmpty,
    'username': username, 'session': <String, Object?>{}};

  void dispose() {
    service.dispose();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(channel, null);
  }
}
