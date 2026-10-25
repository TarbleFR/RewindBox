import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/melonx_locale.dart';
import 'package:neostation/services/embedded_ios_session_status.dart';
import 'package:neostation/services/melonx_internal_service.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('old app links cannot be mistaken for local game files', () {
    for (final link in ['melonx://game?title-id=0100000000000000', 'MELONX://game', 'atariemulator://game']) {
      expect(MelonxInternalService.isRetiredLink(link), isTrue, reason: link);
    }
    for (final file in ['/Documents/roms/switch/homebrew.nro', '/Documents/roms/switch/Example.xci']) {
      expect(MelonxInternalService.isRetiredLink(file), isFalse);
    }
  });

  test('a failed Switch probe does not end a pending teardown or restore menu audio', () async {
    const channel = MethodChannel('neostation/melonx_internal');
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    expect(EmbeddedIOSSessionStatus.handles('ios_melonx_internal'), isTrue);
    for (final value in [true, null, 1, 0]) {
      messenger.setMockMethodCallHandler(channel, (call) async {
        expect(call.method, 'isSessionActive');
        return value;
      });
      expect(await EmbeddedIOSSessionStatus.isActive('ios_melonx_internal'), isTrue);
    }
    messenger.setMockMethodCallHandler(channel, (_) async => throw PlatformException(code: 'unavailable'));
    expect(await EmbeddedIOSSessionStatus.isActive('ios_melonx_internal'), isTrue);
    messenger.setMockMethodCallHandler(channel, (_) async => false);
    expect(await EmbeddedIOSSessionStatus.isActive('ios_melonx_internal'), isFalse);
  });

  test('availability requires a real runtime report, including after a missing plugin', () async {
    final channel = MelonxInternalService.channel;
    final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
    addTearDown(() => messenger.setMockMethodCallHandler(channel, null));
    messenger.setMockMethodCallHandler(channel, null);
    expect(await MelonxInternalService.runtimeAvailable(), isFalse);
    for (final report in [null, true, {'available': false}, {'available': 1}]) {
      messenger.setMockMethodCallHandler(channel, (_) async => report);
      expect(await MelonxInternalService.runtimeAvailable(), isFalse);
    }
    messenger.setMockMethodCallHandler(channel, (_) async => {'available': true});
    expect(await MelonxInternalService.runtimeAvailable(), isTrue);
  });

  test('all status messages exist in twelve languages and Traditional Chinese is selected', () {
    expect(MelonxLocale.values.keys.toSet(), {'en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'});
    for (final entry in MelonxLocale.values.entries) {
      expect(entry.value.keys.toSet(), {'unavailable', 'reimport', 'launchFailed'}, reason: entry.key);
      expect(entry.value.values.every((text) => text.isNotEmpty), isTrue);
    }
    for (final locale in [const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant'), const Locale('zh', 'TW'), const Locale('zh', 'HK')]) {
      expect(MelonxLocale.forLocale(locale, 'reimport'), MelonxLocale.values['zh_Hant']!['reimport']);
    }
  });

  test('no external launch service, sync card or registered legacy JIT handler remains', () {
    for (final file in [
      'lib/services/melonx_library_service.dart',
      'lib/services/stikjit_melonx_service.dart',
      'lib/services/ios_shortcut_jit_launch_service.dart',
    ]) {
      expect(File(file).existsSync(), isFalse, reason: file);
    }
    final pod = File('packages/stikjit_bridge/ios/stikjit_bridge.podspec').readAsStringSync();
    expect(pod, contains("s.exclude_files = ['Classes/StikjitBridgePlugin.swift', 'Classes/StikjitBridgePluginV2.swift']"));
    final directories = File('lib/screens/settings_screen/new_settings_options/directories_settings_content.dart').readAsStringSync();
    expect(directories, isNot(contains('_buildIOSMeloNXSection')));
    final startup = File('lib/main.dart').readAsStringSync();
    expect(startup, isNot(contains('MelonxLibraryService')));
    final router = File('lib/services/game/game_launch_service.dart').readAsStringSync();
    expect(router, isNot(contains('MelonxLibraryService')));
  });
}
