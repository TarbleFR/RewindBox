// The RetroAchievements native client reads flags sent as 1/0 as booleans.
//
// 2 November 2026 (IPA 615-618): the plugin answered `account` with
// `authenticated` boxed from a C comparison (@(credentials != nil)), which the
// Flutter codec delivers as the integer 1. The session compared it with
// `== true`, so every launch looked signed out ("password required") while
// the Keychain item was found (app.log: authenticated=false storage=keychain
// keychain=0), and PS3 launches ran without achievements.
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:retro_achievements_session/retro_achievements_session.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('rewindbox/retro_achievements_session');
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() {
    messenger.setMockMethodCallHandler(channel, null);
    RetroAchievementsNativeClient.diagnostics = null;
  });

  test('an account found in the Keychain reads as signed in when sent as 1', () async {
    messenger.setMockMethodCallHandler(channel, (call) async {
      expect(call.method, 'account');
      return {
        'available': 1,
        'authenticated': 1,
        'username': 'player',
        'session': <String, Object?>{},
        'storage': 'keychain',
        'keychainStatus': 0,
      };
    });
    final lines = <String>[];
    RetroAchievementsNativeClient.diagnostics = lines.add;
    final client = RetroAchievementsNativeClient(channel: channel, available: true);
    final account = await client.invoke('account');
    expect(account['authenticated'], isTrue);
    expect(account['available'], isTrue);
    // Non-flag numbers are untouched.
    expect(account['keychainStatus'], 0);
    expect(lines.single, contains('authenticated=true storage=keychain keychain=0'));
    client.dispose();
  });

  test('0 reads as signed out; real booleans and other answers are unchanged', () async {
    final answers = <String, Map<String, Object?>>{
      'account': {'authenticated': 0, 'storage': 'none', 'keychainStatus': -25300},
      'login': {'authenticated': true, 'username': 'player'},
      'prepareSession': {'enabled': 1, 'hardcore': 0, 'raSessionId': 'id', 'generation': 3},
    };
    messenger.setMockMethodCallHandler(channel, (call) async => answers[call.method]);
    final client = RetroAchievementsNativeClient(channel: channel, available: true);
    expect((await client.invoke('account'))['authenticated'], isFalse);
    expect((await client.invoke('login'))['authenticated'], isTrue);
    final launch = await client.invoke('prepareSession');
    expect(launch['enabled'], isTrue);
    expect(launch['hardcore'], isFalse);
    expect(launch['generation'], 3);
    expect(launch['raSessionId'], 'id');
    client.dispose();
  });
}
