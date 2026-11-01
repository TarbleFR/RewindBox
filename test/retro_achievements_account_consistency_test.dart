import 'dart:async';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/retro_achievements_dashboard_models.dart';
import 'package:neostation/models/retro_achievements_game_info.dart';
import 'package:neostation/models/retro_achievements_gotw.dart';
import 'package:neostation/models/retro_achievements_summary.dart';
import 'package:neostation/models/retro_achievements_user.dart';
import 'package:neostation/providers/retro_achievements_provider.dart';

import 'support/ra_dashboard_fixture.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('matching Web credentials restore only the confirmed native account', () async {
    final native = RANativeFixture(username: 'Alice');
    final source = RADashboardFixture()
      ..savedUsername = 'aLiCe'
      ..savedApiKey = 'alice-web-key';
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });

    await Future.wait([provider.initialize(), provider.initialize()]);
    expect(provider.isConnected, isTrue);
    expect(provider.user!.user.toLowerCase(), 'alice');
    expect(source.profiles, [('aLiCe', 'alice-web-key')]);
    expect(native.calls.map((call) => call.method), ['account']);
    // Restoring a Web API key cannot log in an emulator or enable RA.
    expect(native.service.preferences.enabled, isFalse);
  });

  test('a different stored Web account is ignored without destroying migration inputs', () async {
    final native = RANativeFixture(username: 'Bob');
    final source = RADashboardFixture()
      ..savedUsername = 'Alice'
      ..savedApiKey = 'alice-web-key';
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();

    expect(source.profiles, isEmpty);
    expect(source.writes, isEmpty);
    expect(source.savedUsername, 'Alice');
    expect(source.savedApiKey, 'alice-web-key');
    expect(provider.isConnected, isFalse);
    expect(await provider.connect('Alice', apiKey: 'alice-web-key'), isFalse);
    expect(provider.accountErrorKey, AppLocale.raSessionDifferentAccount);
    expect(source.profiles, isEmpty);
    expect(await provider.connect('Bob', apiKey: 'bob-web-key'), isTrue);
    expect(provider.user!.user, 'Bob');
  });

  test('saved Web data restores the dashboard but never authenticates a signed-out native account', () async {
    final native = RANativeFixture(username: '');
    final source = RADashboardFixture()
      ..savedUsername = 'Alice'
      ..savedApiKey = 'alice-web-key';
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();

    // Build 608 refused this valid pair locally ("sign in here to enable
    // in-game achievements"): the dashboard and the in-game session use
    // different credentials, so a signed-out game session is not a conflict.
    expect(provider.isConnected, isTrue);
    expect(provider.accountErrorKey, isNull);
    expect(source.profiles, [('Alice', 'alice-web-key')]);
    expect(await provider.connect('Alice', apiKey: 'alice-web-key'), isTrue);
    // The Web API key still never signs in an emulator nor enables RA.
    expect(native.service.authenticated, isFalse);
    expect(native.service.preferences.enabled, isFalse);
    expect(native.calls.map((call) => call.method), isNot(contains('login')));
  });

  test('desktop Web-only login remains available without the native plugin', () async {
    final native = RANativeFixture(username: '', available: false);
    final source = RADashboardFixture()
      ..savedUsername = 'DesktopUser'
      ..savedApiKey = 'desktop-web-key';
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();

    expect(provider.isConnected, isTrue);
    expect(provider.user!.user, 'DesktopUser');
    expect(native.calls, isEmpty);
  });

  test('a pending connect cannot republish or persist an account after disconnect', () async {
    final gate = Completer<RetroAchievementsUser?>();
    final source = RADashboardFixture()..profile = (_, _) => gate.future;
    final provider = RetroAchievementsProvider(source: source);
    addTearDown(provider.dispose);
    final connecting = provider.connect('Alice', apiKey: 'alice-web-key');
    expect(provider.isLoading, isTrue);
    provider.disconnect();
    gate.complete(RetroAchievementsUser.fromJson({'User': 'Alice'}));

    expect(await connecting, isFalse);
    await Future<void>.delayed(Duration.zero);
    expect(provider.isConnected, isFalse);
    expect(provider.isLoading, isFalse);
    expect(provider.user, isNull);
    expect(provider.username, isEmpty);
    expect(provider.apiKey, isEmpty);
    expect(source.savedUsername, isNull);
    expect(source.savedApiKey, isNull);
    expect(source.writes, ['clear:username', 'clear:key']);
  });

  test('the newer connection wins even when an older request finishes last', () async {
    final alice = Completer<RetroAchievementsUser?>();
    final source = RADashboardFixture()
      ..profile = (username, _) => username == 'Alice' ? alice.future
          : Future.value(RetroAchievementsUser.fromJson({'User': username}));
    final provider = RetroAchievementsProvider(source: source);
    addTearDown(provider.dispose);
    final old = provider.connect('Alice', apiKey: 'alice-web-key');
    expect(await provider.connect('Bob', apiKey: 'bob-web-key'), isTrue);
    alice.complete(RetroAchievementsUser.fromJson({'User': 'Alice'}));

    expect(await old, isFalse);
    expect(provider.user!.user, 'Bob');
    expect(provider.username, 'Bob');
    expect(provider.apiKey, 'bob-web-key');
    expect(source.savedUsername, 'Bob');
    expect(source.savedApiKey, 'bob-web-key');
    expect(source.writes, ['username:Bob', 'key:bob-web-key']);
  });

  test('credential pair writes and an explicit disconnect are ordered', () async {
    final source = RADashboardFixture()
      ..writeGate = Completer<void>()
      ..writeStarted = Completer<void>();
    final provider = RetroAchievementsProvider(source: source);
    addTearDown(provider.dispose);
    final old = provider.connect('Alice', apiKey: 'alice-web-key');
    await source.writeStarted!.future;
    provider.disconnect();
    final current = provider.connect('Bob', apiKey: 'bob-web-key');
    source.writeGate!.complete();

    expect(await old, isFalse);
    expect(await current, isTrue);
    expect(source.writes, ['username:Alice', 'key:alice-web-key',
      'clear:username', 'clear:key', 'username:Bob', 'key:bob-web-key']);
    expect(source.savedUsername, 'Bob');
    expect(source.savedApiKey, 'bob-web-key');
    expect(provider.user!.user, 'Bob');
  });

  test('native account changes invalidate Web data without any widget callback', () async {
    final native = RANativeFixture();
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    expect(await provider.connect('Alice', apiKey: 'alice-web-key'), isTrue);
    final old = await provider.getGameInfoAndUserProgress(42);
    expect(old!.title, 'Alice progress');

    expect(await native.service.login('Bob', 'fixture-password'), isTrue);
    expect(provider.isConnected, isFalse);
    expect(provider.user, isNull);
    expect(provider.apiKey, isEmpty);
    // A native account change does not erase old migration/read-only inputs.
    expect(source.savedUsername, 'Alice');
    expect(await provider.connect('Bob', apiKey: 'bob-web-key'), isTrue);
    final current = await provider.getGameInfoAndUserProgress(42);
    expect(current!.title, 'Bob progress');
    expect(source.games.map((request) => request.$2), ['Alice', 'Bob']);
    // Signing out of the in-game session alone keeps the Web dashboard (its
    // own Web API key); only a different in-game account invalidates it.
    expect(await native.service.logout(), isTrue);
    expect(provider.isConnected, isTrue);
    expect(provider.user!.user, 'Bob');
  });

  test('policy and live-session notifications do not reconnect the same account', () async {
    final native = RANativeFixture();
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(() { provider.dispose(); native.dispose(); });
    await provider.initialize();
    expect(await provider.connect('Alice', apiKey: 'alice-web-key'), isTrue);
    await native.service.setEnabled(true);
    await native.service.setHardcore(true);
    native.client.onSessionChanged!({'sessionId': 'running', 'engine': 'libretro',
      'enabled': true, 'supported': true, 'active': true, 'generation': 2});

    expect(provider.isConnected, isTrue);
    expect(provider.user!.user, 'Alice');
    expect(source.profiles, hasLength(1));
  });

  test('all delayed account data and game caches are discarded on account change', () async {
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(source: source);
    addTearDown(provider.dispose);
    expect(await provider.connect('Alice', apiKey: 'alice-web-key'), isTrue);
    final summary = Completer<RetroAchievementsUserSummary?>();
    final awards = Completer<Map<String, dynamic>?>();
    final progress = Completer<RetroAchievementCompletionProgressSummary>();
    final games = Completer<List<RetroAchievementRecentlyPlayedGameItem>>();
    final unlocks = Completer<List<RetroAchievementRecentUnlockItem>>();
    final game = Completer<GameInfoAndUserProgress?>();
    final week = Completer<RetroAchievementsGOTW?>();
    source.summary = (_, _) => summary.future;
    source.awards = (_, _) => awards.future;
    source.completion = (_, _) => progress.future;
    source.recentGames = (_, _) => games.future;
    source.recentUnlocks = (_, _) => unlocks.future;
    source.game = (_, _, _) => game.future;
    source.week = (_) => week.future;
    final pending = [provider.loadUserSummary(), provider.fetchUserAwards(),
      provider.fetchCompletionProgress(), provider.fetchRecentlyPlayedGames(),
      provider.fetchRecentUnlocks(), provider.fetchGOTW()];
    final pendingGame = provider.getGameInfoAndUserProgress(71);

    provider.disconnect(clearSavedUser: false);
    source.summary = null;
    source.game = null;
    expect(await provider.connect('Bob', apiKey: 'bob-web-key'), isTrue);
    summary.complete(RetroAchievementsUserSummary.fromJson({'User': 'Alice'}));
    awards.complete({'UserAwards': <Object>[]});
    progress.complete(const RetroAchievementCompletionProgressSummary(count: 1, total: 77, results: []));
    games.complete([RetroAchievementRecentlyPlayedGameItem.fromJson({'GameID': 71, 'Title': 'Alice game'})]);
    unlocks.complete([RetroAchievementRecentUnlockItem.fromJson({'AchievementID': 8, 'Title': 'Alice unlock'})]);
    game.complete(GameInfoAndUserProgress.fromJson({'ID': 71, 'Title': 'Alice progress'}));
    week.complete(RetroAchievementsGOTW.fromJson({'Achievement': {'ID': 8, 'Title': 'Alice week'},
      'Game': {'ID': 71, 'Title': 'Alice game'}, 'Console': <String, Object>{}}));

    expect(await Future.wait(pending), everyElement(isFalse));
    expect(await pendingGame, isNull);
    expect(provider.user!.user, 'Bob');
    expect(provider.userSummary!.user, 'Bob');
    expect(provider.userAwards, isNull);
    expect(provider.completionProgress, isNull);
    expect(provider.recentlyPlayedGames, isEmpty);
    expect(provider.recentUnlocks, isEmpty);
    expect(provider.gotw, isNull);
    expect(provider.ownedWeekGame, isNull);
    expect((await provider.getGameInfoAndUserProgress(71))!.title, 'Bob progress');
    expect(source.games.map((request) => request.$2), ['Alice', 'Bob']);
    expect(provider.recentUnlocksLoading, isFalse);
    expect(provider.userAwardsLoading, isFalse);
    expect(provider.completionProgressLoading, isFalse);
    expect(provider.recentlyPlayedLoading, isFalse);
    expect(provider.gotwLoading, isFalse);
  });

  test('stale failures cannot overwrite a current error or loading state', () async {
    final source = RADashboardFixture();
    final provider = RetroAchievementsProvider(source: source);
    addTearDown(provider.dispose);
    expect(await provider.connect('Alice', apiKey: 'alice-web-key'), isTrue);
    final old = Completer<List<RetroAchievementRecentUnlockItem>>();
    source.recentUnlocks = (_, _) => old.future;
    final oldLoad = provider.fetchRecentUnlocks();
    provider.disconnect(clearSavedUser: false);
    expect(await provider.connect('Bob', apiKey: 'bob-web-key'), isTrue);
    final current = Completer<List<RetroAchievementRecentUnlockItem>>();
    source.recentUnlocks = (_, _) => current.future;
    final currentLoad = provider.fetchRecentUnlocks();
    old.completeError(StateError('old account failure'));
    expect(await oldLoad, isFalse);
    expect(provider.recentUnlocksLoading, isTrue);
    expect(provider.recentUnlocksError, isNull);
    current.complete([RetroAchievementRecentUnlockItem.fromJson({'AchievementID': 9, 'Title': 'Bob unlock'})]);
    expect(await currentLoad, isTrue);
    expect(provider.recentUnlocks.single.title, 'Bob unlock');
  });

  test('unreadable credentials are preserved and cannot trigger a login', () async {
    final source = RADashboardFixture()
      ..savedUsername = 'Alice'
      ..savedApiKey = 'alice-web-key'
      ..readsFail = true;
    final provider = RetroAchievementsProvider(source: source);
    addTearDown(provider.dispose);
    expect(await provider.tryAutoLogin(), isFalse);
    expect(source.profiles, isEmpty);
    expect(source.writes, isEmpty);
    expect(source.savedUsername, 'Alice');
    expect(source.savedApiKey, 'alice-web-key');
  });

  test('disconnect cancels an auto-login while credential reads are pending', () async {
    final source = RADashboardFixture()
      ..savedUsername = 'Alice'
      ..savedApiKey = 'alice-web-key'
      ..readGate = Completer<void>();
    final provider = RetroAchievementsProvider(source: source);
    addTearDown(provider.dispose);
    final loading = provider.tryAutoLogin();
    provider.disconnect(clearSavedUser: false);
    source.readGate!.complete();
    expect(await loading, isFalse);
    expect(source.profiles, isEmpty);
    expect(provider.isConnected, isFalse);
    expect(source.savedUsername, 'Alice');
  });

  test('disposing the provider invalidates pending work and detaches native listeners', () async {
    final native = RANativeFixture();
    final gate = Completer<RetroAchievementsUser?>();
    final source = RADashboardFixture()..profile = (_, _) => gate.future;
    final provider = RetroAchievementsProvider(sessionService: native.service, source: source);
    addTearDown(native.dispose);
    await provider.initialize();
    var notifications = 0;
    provider.addListener(() { notifications++; });
    final pending = provider.connect('Alice', apiKey: 'alice-web-key');
    provider.dispose();
    final countAtDisposal = notifications;
    gate.complete(RetroAchievementsUser.fromJson({'User': 'Alice'}));
    expect(await pending, isFalse);
    expect(await native.service.logout(), isTrue);
    expect(notifications, countAtDisposal);
    expect(source.writes, isEmpty);
  });
}
