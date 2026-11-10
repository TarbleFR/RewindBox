import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/retro_achievements_session.dart';
import 'package:neostation/services/retro_achievements_session_service.dart';
import 'package:retro_achievements_session/retro_achievements_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('test/rewindbox/ra-migration');
  late RetroAchievementsSessionService service;
  late RetroAchievementsPreferences saved;
  late List<MethodCall> calls;
  late List<Map<String, Object?>> candidates;
  Map<String, Object?>? central;
  String? nativeFailure;
  bool diskFails = false;
  int writes = 0;

  Map<String, Object?> candidate(String id, String username,
      {bool enabled = true, bool hardcore = false}) => {
    'id': id, 'username': username, 'sources': ['Dolphin'],
    'enabled': enabled, 'hardcore': hardcore,
  };

  RetroAchievementsSessionService makeService() => RetroAchievementsSessionService(
    native: RetroAchievementsNativeClient(channel: channel, available: true),
    readPreferences: () async => saved,
    writePreferences: (next) async {
      if (diskFails) throw StateError('database unavailable');
      writes++;
      saved = next;
    },
  );

  setUp(() {
    calls = []; candidates = []; central = null; nativeFailure = null;
    diskFails = false; writes = 0;
    saved = const RetroAchievementsPreferences();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      if (call.method == nativeFailure) throw PlatformException(code: 'RA_STORAGE_UNAVAILABLE');
      switch (call.method) {
        case 'account': return {
          'authenticated': central != null, 'username': central?['username'] ?? '', 'session': {},
        };
        case 'inspectLegacy': return central != null
          ? {'central': true, 'authenticated': true, ...central!, 'candidates': []}
          : {'central': false, 'candidates': candidates};
        case 'importLegacy':
          final args = Map<String, Object?>.from(call.arguments as Map);
          final selected = candidates.singleWhere((item) => item['id'] == args['id']);
          central ??= {
            'username': selected['username'],
            'policy': {'enabled': selected['enabled'], 'hardcore': selected['hardcore']},
          };
          return {'authenticated': true, ...central!};
        case 'logout': central = null; return {'authenticated': false, 'username': ''};
        case 'login':
          central = {'username': (call.arguments as Map)['username']};
          return {'authenticated': true, ...central!};
        case 'prepareSession':
          final args = call.arguments as Map;
          return {'raSessionId': 'launch', 'enabled': args['enabled'] == true && args['supported'] == true};
        default: return <String, Object?>{};
      }
    });
    service = makeService();
  });

  tearDown(() {
    service.dispose();
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(channel, null);
  });

  test('a single legacy account imports its enabled and Hardcore choices once', () async {
    candidates = [candidate('old-dolphin', 'Alice', hardcore: true)];
    await service.initialize();
    expect(service.initialized, isTrue);
    expect(service.authenticated, isTrue);
    expect(service.username, 'Alice');
    expect(saved.enabled, isTrue);
    expect(saved.hardcore, isTrue);
    expect(saved.migrationVersion, 1);
    expect(service.migrationCandidates, isEmpty);
    expect(calls.singleWhere((call) => call.method == 'importLegacy').arguments,
      {'id': 'old-dolphin'}); // Credentials never cross the Dart boundary.
    await service.initialize();
    expect(calls.where((call) => call.method == 'importLegacy'), hasLength(1));
  });

  test('disabled legacy settings retain the account without opting the user in', () async {
    candidates = [candidate('old', 'Alice', enabled: false, hardcore: true)];
    await service.initialize();
    expect(service.authenticated, isTrue);
    expect(saved.enabled, isFalse);
    expect(saved.hardcore, isTrue);
    expect((await service.prepareLaunch(engine: 'armsx2', system: 'ps2', language: 'fr'))['enabled'], isFalse);
  });

  test('conflicting accounts do not silently activate an emulator account', () async {
    candidates = [candidate('one', 'Alice'), candidate('two', 'Bob', hardcore: true)];
    await service.initialize();
    expect(service.initialized, isTrue);
    expect(service.authenticated, isFalse);
    expect(service.migrationCandidates.map((item) => item.username), ['Alice', 'Bob']);
    expect(calls.where((call) => call.method == 'importLegacy'), isEmpty);
    expect(writes, 0);
    expect((await service.prepareLaunch(engine: 'dolphin', system: 'gc', language: 'ja'))['enabled'], isFalse);
    expect(await service.importLegacy('two'), isTrue);
    expect(service.username, 'Bob');
    expect(saved.enabled, isTrue);
    expect(saved.hardcore, isTrue);
  });

  test('the same name with conflicting policies still requires a choice', () async {
    candidates = [candidate('softcore', 'Alice'), candidate('hardcore', 'Alice', hardcore: true)];
    await service.initialize();
    expect(service.migrationCandidates, hasLength(2));
    expect(writes, 0);
    expect(await service.importLegacy('softcore'), isTrue);
    expect(saved.hardcore, isFalse);
  });

  test('missing legacy credentials finish migration with RA disabled', () async {
    await service.initialize();
    expect(service.initialized, isTrue);
    expect(saved.migrationVersion, 1);
    expect(saved.enabled, isFalse);
    expect(calls.where((call) => call.method == 'importLegacy'), isEmpty);
  });

  test('a confirmed central account cannot be replaced by legacy settings', () async {
    central = {'username': 'Current'};
    candidates = [candidate('old', 'Old', hardcore: true)];
    saved = const RetroAchievementsPreferences(enabled: true);
    await service.initialize();
    expect(service.username, 'Current');
    expect(saved.enabled, isTrue);
    expect(saved.hardcore, isFalse);
    expect(saved.migrationVersion, 1);
    expect(calls.where((call) => call.method == 'importLegacy'), isEmpty);
  });

  test('an unreadable legacy store is not treated as missing or migrated', () async {
    nativeFailure = 'inspectLegacy';
    candidates = [candidate('old', 'Alice')];
    await service.initialize();
    expect(service.initialized, isFalse);
    expect(service.errorCode, 'RA_STORAGE_UNAVAILABLE');
    expect(saved.migrationVersion, 0);
    expect(writes, 0);
    expect(calls.where((call) => call.method == 'logout'), isEmpty);
    nativeFailure = null;
    await service.retry();
    expect(service.username, 'Alice');
    expect(saved.migrationVersion, 1);
  });

  test('a failed Keychain import leaves migration retryable and preserves data', () async {
    candidates = [candidate('old', 'Alice')];
    nativeFailure = 'importLegacy';
    await service.initialize();
    expect(service.initialized, isFalse);
    expect(central, isNull);
    expect(saved.migrationVersion, 0);
    expect(writes, 0);
    nativeFailure = null;
    await service.retry();
    expect(service.authenticated, isTrue);
    expect(saved.migrationVersion, 1);
  });

  test('explicit login can recover from corrupt legacy data after central storage was read', () async {
    nativeFailure = 'inspectLegacy';
    await service.initialize();
    expect(service.initialized, isFalse);
    expect(service.canRecoverLegacy, isTrue);
    expect(await service.login('Chosen', 'temporary-password'), isTrue);
    expect(service.initialized, isTrue);
    expect(service.username, 'Chosen');
    expect(saved.enabled, isFalse);
    expect(saved.migrationVersion, 1);
  });

  test('an unreadable central Keychain never permits a destructive recovery', () async {
    nativeFailure = 'account';
    await service.initialize();
    expect(service.canRecoverLegacy, isFalse);
    expect(await service.ignoreLegacy(), isFalse);
    expect(await service.login('Other', 'temporary-password'), isFalse);
    expect(calls.where((call) => call.method == 'logout' || call.method == 'login'), isEmpty);
    expect(saved.migrationVersion, 0);
  });

  test('database failure after Keychain import resumes the original account and policy', () async {
    candidates = [candidate('old', 'Alice', hardcore: true)];
    diskFails = true;
    await service.initialize();
    expect(service.initialized, isFalse);
    expect(central?['username'], 'Alice');
    expect(saved.migrationVersion, 0);
    expect(service.errorCode, 'RA_STORAGE_UNAVAILABLE');
    candidates = [candidate('changed-store', 'Other')];
    diskFails = false;
    await service.retry();
    expect(service.username, 'Alice');
    expect(saved.enabled, isTrue);
    expect(saved.hardcore, isTrue);
    expect(saved.migrationVersion, 1);
    expect(calls.where((call) => call.method == 'importLegacy'), hasLength(1));
  });

  test('logout remains logged out after restarting despite intact legacy stores', () async {
    candidates = [candidate('old', 'Alice')];
    await service.initialize();
    expect(await service.logout(), isTrue);
    final inspections = calls.where((call) => call.method == 'inspectLegacy').length;
    service.dispose(); service = makeService();
    await service.initialize();
    expect(service.authenticated, isFalse);
    expect(saved.enabled, isFalse);
    expect(saved.migrationVersion, 1);
    expect(candidates, hasLength(1));
    expect(calls.where((call) => call.method == 'inspectLegacy'), hasLength(inspections));
  });

  test('declining conflicting legacy accounts is durable without deleting them', () async {
    candidates = [candidate('one', 'Alice'), candidate('two', 'Bob')];
    await service.initialize();
    expect(await service.ignoreLegacy(), isTrue);
    expect(service.migrationCandidates, isEmpty);
    expect(saved.enabled, isFalse);
    expect(saved.migrationVersion, 1);
    service.dispose(); service = makeService();
    await service.initialize();
    expect(service.authenticated, isFalse);
    expect(service.migrationCandidates, isEmpty);
    expect(candidates, hasLength(2));
    expect(calls.where((call) => call.method == 'importLegacy'), isEmpty);
  });

  test('failed persistence cannot dismiss a pending migration or delete credentials', () async {
    candidates = [candidate('one', 'Alice'), candidate('two', 'Bob')];
    await service.initialize();
    diskFails = true;
    expect(await service.ignoreLegacy(), isFalse);
    expect(saved.migrationVersion, 0);
    expect(service.migrationCandidates, hasLength(2));
    expect(calls.where((call) => call.method == 'logout'), isEmpty);
  });

  test('manual login resolves legacy conflicts without importing a different account', () async {
    candidates = [candidate('one', 'Alice'), candidate('two', 'Bob')];
    await service.initialize();
    expect(await service.login('Chosen', 'temporary-password'), isTrue);
    expect(service.username, 'Chosen');
    expect(saved.migrationVersion, 1);
    expect(saved.enabled, isFalse);
    expect(service.migrationCandidates, isEmpty);
    expect(calls.where((call) => call.method == 'importLegacy'), isEmpty);
  });

  test('queued duplicate choices cannot replace the already imported account', () async {
    candidates = [candidate('one', 'Alice'), candidate('two', 'Bob')];
    await service.initialize();
    final first = service.importLegacy('one');
    final second = service.importLegacy('two');
    expect(await first, isTrue);
    expect(await second, isFalse);
    expect(service.username, 'Alice');
    expect(central?['username'], 'Alice');
    expect(calls.where((call) => call.method == 'importLegacy'), hasLength(1));
  });
}
