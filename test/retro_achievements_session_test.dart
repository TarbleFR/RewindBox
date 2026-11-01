import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/retro_achievements_session.dart';
import 'package:neostation/services/retro_achievements_session_service.dart';
import 'package:retro_achievements_session/retro_achievements_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/rewindbox/ra-session');
  late RetroAchievementsNativeClient native;
  late RetroAchievementsSessionService service;
  late RetroAchievementsPreferences saved;
  late List<Map<String, Object?>> prepared;
  late List<String> calls;
  bool account = true;
  bool storageFails = false;
  Completer<void>? writeGate;

  setUp(() {
    account = true; storageFails = false; writeGate = null;
    saved = const RetroAchievementsPreferences(migrationVersion: 1);
    prepared = []; calls = [];
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call.method);
      switch (call.method) {
        case 'account': return {'authenticated': account, 'username': account ? 'Alice' : '', 'session': {}};
        case 'login': account = true; return {'authenticated': true, 'username': 'Alice'};
        case 'logout': account = false; return {'authenticated': false, 'username': ''};
        case 'prepareSession':
          final args = Map<String, Object?>.from(call.arguments as Map);
          prepared.add(args);
          return {'raSessionId': 'launch-${prepared.length}', 'enabled': args['enabled'] == true && args['supported'] == true,
            'supported': args['supported'], 'hardcore': args['hardcore']};
        default: return <String, Object?>{};
      }
    });
    native = RetroAchievementsNativeClient(channel: channel, available: true);
    service = RetroAchievementsSessionService(native: native,
      readPreferences: () async => saved,
      writePreferences: (value) async {
        await writeGate?.future;
        if (storageFails) throw StateError('disk unavailable');
        saved = value;
      });
  });

  tearDown(() {
    service.dispose();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
  });

  test('initialization is shared and default policy is disabled', () async {
    await Future.wait([service.initialize(), service.initialize()]);
    expect(calls.where((name) => name == 'account'), hasLength(1));
    expect(service.authenticated, isTrue);
    expect(service.preferences.enabled, isFalse);
  });

  for (final engine in ['dolphin', 'armsx2', 'libretro']) {
    test('$engine consumes one central policy, never a web key or a password', () async {
      await service.setEnabled(true);
      await service.setHardcore(true);
      final launch = await service.prepareLaunch(engine: engine,
        system: engine == 'dolphin' ? 'gc' : engine == 'armsx2' ? 'ps2' : 'gba',
        core: engine == 'libretro' ? 'mgba' : null, language: 'zh_Hant');
      expect(launch['enabled'], isTrue);
      expect(prepared.single['hardcore'], isTrue);
      expect(prepared.single['language'], 'zh_Hant');
      expect(prepared.single.keys, isNot(contains('token')));
      expect(prepared.single.keys, isNot(contains('password')));
      expect(prepared.single.keys, isNot(contains('apiKey')));
      expect(prepared.single.keys, isNot(contains('notifications')));
    });
  }

  test('running snapshot survives disabled preference until the next launch', () async {
    await service.setEnabled(true);
    await service.prepareLaunch(engine: 'libretro', system: 'gba', core: 'mgba', language: 'fr');
    native.onSessionChanged!({'sessionId': 'running', 'engine': 'libretro',
      'generation': prepared.single['generation'], 'enabled': true, 'supported': true,
      'active': true, 'gameLoaded': true, 'hardcoreActive': false});
    expect(service.changesPending, isFalse);
    await service.setEnabled(false);
    expect(service.session!.enabled, isTrue);
    expect(service.session!.active, isTrue);
    expect(service.changesPending, isTrue);
    final next = await service.prepareLaunch(engine: 'libretro', system: 'gba', core: 'mgba', language: 'fr');
    expect(next['enabled'], isFalse);
  });

  test('Hardcore preference is separate from the observed Hardcore state', () async {
    await service.setEnabled(true);
    await service.setHardcore(true);
    native.onSessionChanged!({'sessionId': 'pending', 'engine': 'dolphin',
      'generation': 2, 'enabled': true, 'supported': true,
      'active': false, 'gameLoaded': false, 'hardcoreActive': false});
    expect(service.preferences.hardcore, isTrue);
    expect(service.session!.hardcoreActive, isFalse);
  });

  test('failed persistence cannot turn RA on or discard a valid account', () async {
    await service.initialize();
    storageFails = true;
    expect(await service.setEnabled(true), isFalse);
    expect(service.preferences.enabled, isFalse);
    expect(saved.enabled, isFalse);
    expect(service.authenticated, isTrue);
    expect(service.errorCode, 'RA_STORAGE_UNAVAILABLE');
  });

  test('rapid preference changes are serialized before a launch snapshot', () async {
    await service.initialize();
    writeGate = Completer<void>();
    final first = service.setEnabled(true);
    final second = service.setEnabled(false);
    final launch = service.prepareLaunch(engine: 'armsx2', system: 'ps2', language: 'ja');
    await Future<void>.delayed(Duration.zero);
    expect(prepared, isEmpty);
    writeGate!.complete();
    expect(await first, isTrue);
    expect(await second, isTrue);
    expect((await launch)['enabled'], isFalse);
    expect(saved.enabled, isFalse);
  });

  test('sign out disables the next launch without rewriting the current session', () async {
    await service.setEnabled(true);
    native.onSessionChanged!({'sessionId': 'playing', 'enabled': true, 'generation': 1,
      'active': true, 'gameLoaded': true, 'supported': true});
    expect(await service.logout(), isTrue);
    expect(service.authenticated, isFalse);
    expect(saved.enabled, isFalse);
    expect(service.session!.active, isTrue);
    expect(service.changesPending, isTrue);
    expect((await service.prepareLaunch(engine: 'armsx2', system: 'ps2', language: 'fr'))['enabled'], isFalse);
  });

  test('enable requires emulator authentication, not a dashboard username', () async {
    account = false;
    expect(await service.setEnabled(true), isFalse);
    expect(service.errorCode, 'RA_LOGIN_REQUIRED');
    expect(saved.enabled, isFalse);
  });

  test('unsupported systems never get an enabled session', () async {
    await service.setEnabled(true);
    for (final pair in [('rpcs3', 'ps3', ''), ('melonx', 'switch', ''),
      ('libretro', '3ds', 'azahar'), ('libretro', '5200', 'a5200'),
      ('libretro', 'gw', 'gw'), ('libretro', 'pico', 'picodrive'), ('libretro', 'nes', 'nestopia')]) {
      final launch = await service.prepareLaunch(engine: pair.$1, system: pair.$2, core: pair.$3, language: 'en');
      expect(launch['supported'], isFalse, reason: '${pair.$2}/${pair.$3}');
      expect(launch['enabled'], isFalse);
    }
  });

  test('unverified cores and system menus do not inherit a positive console ID', () {
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'cv', core: 'gearcoleco'), RetroAchievementsCapability.unverified);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'md', core: 'genesis_plus_gx_wide'), RetroAchievementsCapability.unverified);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'sms', core: 'picodrive'), RetroAchievementsCapability.unverified);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'gg', core: 'picodrive'), RetroAchievementsCapability.unverified);
    expect(RetroAchievementsCapabilities.forEngine('dolphin', system: 'wii', systemMenu: true), RetroAchievementsCapability.unsupported);
    expect(RetroAchievementsCapabilities.forEngine('armsx2', system: 'ps2', systemMenu: true), RetroAchievementsCapability.unsupported);
    expect(RetroAchievementsCapabilities.forEngine('libretro', system: 'nes', core: 'future-core'), RetroAchievementsCapability.unsupported);
  });
}
