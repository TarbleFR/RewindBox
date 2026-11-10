import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/models/retro_achievements_session.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/screens/game_screen/game_details_card/tabs/ra_identity_note.dart';
import 'package:neostation/services/retro_achievements_helper.dart';
import 'package:neostation/services/retro_achievements_identity.dart';
import 'package:neostation/services/retro_achievements_session_service.dart';
import 'package:neostation/services/retroachievements_hash_service.dart';
import 'package:neostation/utils/optimized_md5_utils.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'support/ra_dashboard_fixture.dart';

/// NEOSTATION_RA_IDENTIFICATION_V1 and NEOSTATION_RA_DISC_READER_V1 (Dart
/// side): the library hashes files with rcheevos on iOS, asks
/// RetroAchievements about hashes the bundled list does not know, remembers
/// what an emulator recognized at launch, and says how a game was matched.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/neostation/libretro-hash');
  const hashA = '0123456789abcdef0123456789abcdef';
  const hashB = 'fedcba9876543210fedcba9876543210';
  late Directory folder;
  late MemoryRetroAchievementsIdentityStore store;
  late List<MethodCall> nativeCalls;
  late List<http.Request> requests;
  String? nativeAnswer;

  GameModel game(String name, {String system = 'psx', String? raHash}) {
    final file = File('${folder.path}/$name')..writeAsBytesSync(List.filled(4096, 7));
    return GameModel(romname: name, realname: name, name: name.split('.').first, year: '', developer: '',
      publisher: '', genre: '', players: '', rating: 0, systemFolderName: system,
      romPath: file.path, raHash: raHash);
  }

  setUp(() {
    folder = Directory.systemTemp.createTempSync('ra-identity-');
    store = MemoryRetroAchievementsIdentityStore();
    nativeCalls = [];
    requests = [];
    nativeAnswer = hashA;
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel,
        (call) async {
      nativeCalls.add(call);
      return nativeAnswer;
    });
    RetroAchievementsNativeHash.channelOverride = channel;
    RetroAchievementsNativeHash.availableOverride = true;
    RetroAchievementsHashService.identityStore = store;
    RetroAchievementsHashService.consoleIdOverride = (folder) async => folder == 'psx' ? 12 : null;
    RetroAchievementsHashService.bundledLookupOverride = (hash, console) async => null;
    RetroAchievementsHelper.storeOverride = store;
    RetroAchievementsHelper.bundledLookupOverride = (hash) async => null;
    RetroAchievementsHashLookup.clock = DateTime.now;
    RetroAchievementsHashLookup.clientOverride = MockClient((request) async {
      requests.add(request);
      final hash = request.bodyFields['m'];
      return http.Response(jsonEncode({'Success': true, 'GameID': hash == hashA ? 11234 : 0}), 200);
    });
  });

  tearDown(() {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
    RetroAchievementsNativeHash.channelOverride = null;
    RetroAchievementsNativeHash.availableOverride = null;
    RetroAchievementsHashService.identityStore = const SqlRetroAchievementsIdentityStore();
    RetroAchievementsHashService.consoleIdOverride = null;
    RetroAchievementsHashService.bundledLookupOverride = null;
    RetroAchievementsHelper.storeOverride = null;
    RetroAchievementsHelper.bundledLookupOverride = null;
    RetroAchievementsHashLookup.clientOverride = null;
    RetroAchievementsHashLookup.clock = DateTime.now;
    folder.deleteSync(recursive: true);
  });

  group('library hash through rcheevos (iOS)', () {
    test('a disc is hashed natively and an older Dart hash is recomputed once', () async {
      // The cached value was the whole-file MD5 of the older Dart code.
      final disc = game('Crash.chd', raHash: hashB);
      expect(await RetroAchievementsHashService.generateHashForGame(disc), hashA);
      expect(nativeCalls.single.method, 'retroAchievementsHash');
      expect(nativeCalls.single.arguments, {'path': disc.romPath, 'consoleId': 12});
      expect(store.roms[disc.romPath]!.algorithm, RetroAchievementsNativeHash.algorithm);
      // Second time: from the store, no new native call.
      expect(await RetroAchievementsHashService.generateHashForGame(disc), hashA);
      expect(nativeCalls, hasLength(1));
    });

    test('a file rcheevos cannot hash yields no hash, and nothing is stored', () async {
      nativeAnswer = null;
      final disc = game('Unknown.chd');
      expect(await RetroAchievementsHashService.generateHashForGame(disc), isNull);
      expect(store.roms, isEmpty);
      nativeAnswer = 'not-a-hash';
      expect(await RetroAchievementsHashService.generateHashForGame(disc), isNull);
    });

    test('without the native hash (desktop), the cached Dart hash is kept', () async {
      RetroAchievementsNativeHash.availableOverride = false;
      final disc = game('Spyro.cue', raHash: hashB);
      expect(await RetroAchievementsHashService.generateHashForGame(disc), hashB);
      expect(nativeCalls, isEmpty);
    });

    test('PC Engine copier headers are skipped like rcheevos does', () async {
      final rom = List<int>.generate(8192, (i) => i % 251);
      final plain = File('${folder.path}/plain.pce')..writeAsBytesSync(rom);
      final headered = File('${folder.path}/headered.pce')
        ..writeAsBytesSync([...List.filled(512, 0xEE), ...rom]);
      final expected = crypto.md5.convert(rom).toString();
      expect(await OptimizedMd5Utils.calculatePceMd5(plain.path), expected);
      expect(await OptimizedMd5Utils.calculatePceMd5(headered.path), expected);
    });
  });

  group('RetroAchievements asked about unknown hashes', () {
    test('a known hash is asked once with no account data and cached', () async {
      expect(await RetroAchievementsHashLookup.resolve(hashA.toUpperCase(), store), 11234);
      expect(requests.single.url, RetroAchievementsHashLookup.endpoint);
      expect(requests.single.bodyFields, {'r': 'gameid', 'm': hashA});
      expect(requests.single.headers['User-Agent'], contains('NeoStation'));
      expect(await RetroAchievementsHashLookup.resolve(hashA, store), 11234);
      expect(requests, hasLength(1));
    });

    test('an unknown hash is cached for 3 days, a known one for 30', () async {
      var now = DateTime(2026, 11, 1);
      RetroAchievementsHashLookup.clock = () => now;
      expect(await RetroAchievementsHashLookup.resolve(hashB, store), 0);
      expect(await RetroAchievementsHashLookup.resolve(hashA, store), 11234);
      now = now.add(const Duration(days: 2));
      await RetroAchievementsHashLookup.resolve(hashB, store);
      await RetroAchievementsHashLookup.resolve(hashA, store);
      expect(requests, hasLength(2));
      now = now.add(const Duration(days: 2));
      await RetroAchievementsHashLookup.resolve(hashB, store);
      await RetroAchievementsHashLookup.resolve(hashA, store);
      expect(requests.map((r) => r.bodyFields['m']), [hashB, hashA, hashB]);
    });

    test('offline or server errors are not cached and ask again later', () async {
      var fail = true;
      RetroAchievementsHashLookup.clientOverride = MockClient((request) async {
        requests.add(request);
        if (fail) return http.Response('maintenance', 503);
        return http.Response(jsonEncode({'Success': true, 'GameID': 77}), 200);
      });
      expect(await RetroAchievementsHashLookup.resolve(hashA, store), isNull);
      expect(store.lookups, isEmpty);
      fail = false;
      expect(await RetroAchievementsHashLookup.resolve(hashA, store), 77);
      RetroAchievementsHashLookup.clientOverride = MockClient((_) async => throw const SocketException('offline'));
      expect(await RetroAchievementsHashLookup.resolve(hashB, store), isNull);
    });

    test('anything but an MD5 hash is never sent', () async {
      expect(await RetroAchievementsHashLookup.resolve('../etc/passwd', store), isNull);
      expect(await RetroAchievementsHashLookup.resolve('', store), isNull);
      expect(requests, isEmpty);
    });
  });

  group('identification order', () {
    test('learned at launch, then bundled list, then online', () async {
      final launched = game('Launched.chd');
      await store.saveGameId(launched.romPath!, 555, source: 'launch');
      final byLaunch = await RetroAchievementsHelper.fileIdentity(launched, hashA);
      expect(byLaunch!.match, RetroAchievementsMatch.launch);
      expect(byLaunch.gameId, 555);
      expect(requests, isEmpty);

      RetroAchievementsHelper.bundledLookupOverride = (hash) async => hash == hashB ? 42 : null;
      final bundled = await RetroAchievementsHelper.fileIdentity(game('Bundled.cue'), hashB);
      expect(bundled!.match, RetroAchievementsMatch.hash);
      expect(bundled.gameId, 42);
      expect(requests, isEmpty);

      final newer = game('Newer.chd');
      final online = await RetroAchievementsHelper.fileIdentity(newer, hashA);
      expect(online!.match, RetroAchievementsMatch.online);
      expect(online.gameId, 11234);
      expect(store.roms[newer.romPath]!.gameId, 11234);
      expect(store.roms[newer.romPath]!.source, 'online');
      expect(online.recognizedByFile, isTrue);
    });

    test('a different file at the same path does not reuse the launched game', () async {
      final replaced = game('Replaced.chd');
      await store.saveHash(replaced.romPath!, hashB, consoleId: 12, algorithm: 2);
      await store.saveGameId(replaced.romPath!, 555, source: 'launch');
      await store.saveHash(replaced.romPath!, hashA, consoleId: 12, algorithm: 2);
      final identity = await RetroAchievementsHelper.fileIdentity(replaced, hashA);
      expect(identity!.match, RetroAchievementsMatch.online);
    });

    test('an unknown file is reported with its hash', () async {
      expect(await RetroAchievementsHelper.fileIdentity(game('Hack.chd'), hashB), isNull);
      expect(await RetroAchievementsHelper.fileIdentity(game('NoHash.chd'), null), isNull);
    });
  });

  group('learned at launch', () {
    test('the launched file is remembered once the engine loads the set', () async {
      final learned = <(String, int)>[];
      final native = RANativeFixture(username: 'Alice');
      addTearDown(native.dispose);
      final service = RetroAchievementsSessionService(native: native.client,
        readPreferences: () async => const RetroAchievementsPreferences(enabled: true, migrationVersion: 1),
        writePreferences: (_) async {},
        gameIdentified: (path, id) async => learned.add((path, id)));
      addTearDown(service.dispose);
      await service.initialize();
      final launch = await service.prepareLaunch(engine: 'libretro', system: 'ps1', core: 'swanstation',
        language: 'fr', contentPath: '/games/Crash.chd');
      expect(launch['raSessionId'], 'fixture-session');
      // The path stays on the Dart side.
      final prepared = native.calls.lastWhere((call) => call.method == 'prepareSession');
      expect((prepared.arguments as Map).values, isNot(contains('/games/Crash.chd')));

      native.client.onSessionChanged!({'sessionId': 'fixture-session', 'engine': 'libretro',
        'enabled': true, 'supported': true, 'gameLoaded': false, 'gameId': 0});
      expect(learned, isEmpty);
      native.client.onSessionChanged!({'sessionId': 'other', 'engine': 'libretro',
        'enabled': true, 'supported': true, 'gameLoaded': true, 'gameId': 99});
      expect(learned, isEmpty);
      native.client.onSessionChanged!({'sessionId': 'fixture-session', 'engine': 'libretro',
        'enabled': true, 'supported': true, 'gameLoaded': true, 'gameId': 1234, 'active': true});
      native.client.onSessionChanged!({'sessionId': 'fixture-session', 'engine': 'libretro',
        'enabled': true, 'supported': true, 'gameLoaded': true, 'gameId': 1234, 'unlockedCount': 1});
      await Future<void>.delayed(Duration.zero);
      expect(learned, [('/games/Crash.chd', 1234)]);
      expect(service.session!.gameId, 1234);
    });
  });

  group('achievements tab note', () {
    final localization = FlutterLocalization.instance;
    setUpAll(() async {
      SharedPreferences.setMockInitialValues({});
      await localization.ensureInitialized();
    });

    Future<void> pump(WidgetTester tester, RetroAchievementsIdentity identity) async {
      localization.init(mapLocales: [MapLocale('fr', AppLocale.fr)], initLanguageCode: 'fr');
      localization.translate('fr');
      tester.view.physicalSize = const Size(852, 393);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(ScreenUtilInit(designSize: const Size(640, 480),
        builder: (_, _) => MaterialApp(locale: const Locale('fr'),
          supportedLocales: localization.supportedLocales,
          localizationsDelegates: localization.localizationsDelegates,
          home: Scaffold(body: Center(child: RetroAchievementsIdentityNote(identity: identity))))));
      await tester.pumpAndSettle();
    }

    String fr(String key) => AppLocale.fr[key] as String;

    testWidgets('a file RetroAchievements does not know shows its hash to compare', (tester) async {
      await pump(tester, const RetroAchievementsIdentity(hash: hashB, match: RetroAchievementsMatch.none));
      expect(find.text(fr(AppLocale.raFileNotRecognized)), findsOneWidget);
      expect(find.text(fr(AppLocale.raFileNotRecognizedHelp)), findsOneWidget);
      expect(find.text(hashB), findsOneWidget);
      expect(find.byKey(const ValueKey('ra-identity-copy')), findsOneWidget);
      expect(find.byKey(const ValueKey('ra-identity-game-page')), findsNothing);
      expect(tester.takeException(), isNull);
    });

    testWidgets('a title-only match warns and links to the game page', (tester) async {
      await pump(tester, const RetroAchievementsIdentity(gameId: 1234, hash: hashB,
        match: RetroAchievementsMatch.name));
      expect(find.text(fr(AppLocale.raTitleOnlyMatch)), findsOneWidget);
      expect(find.byKey(const ValueKey('ra-identity-game-page')), findsOneWidget);
      expect(RetroAchievementsIdentityNote.gamePage(1234).toString(),
        'https://retroachievements.org/game/1234');
      expect(tester.takeException(), isNull);
    });

    testWidgets('a recognized file shows nothing more', (tester) async {
      for (final match in [RetroAchievementsMatch.hash, RetroAchievementsMatch.online,
          RetroAchievementsMatch.launch]) {
        await pump(tester, RetroAchievementsIdentity(gameId: 1, hash: hashA, match: match));
        expect(find.byType(Text), findsNothing, reason: match.name);
      }
    });
  });
}
