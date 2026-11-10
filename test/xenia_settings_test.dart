import 'dart:convert';
import 'dart:io';
import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/xenia_locale.dart';
import 'package:neostation/services/xenia_settings_service.dart';
import 'package:path/path.dart' as path;

import 'xenia_test_images.dart';

void main() {
  late Directory temp;
  late Directory frontend;

  XeniaSettingsService service() =>
      XeniaSettingsService(frontendDirectory: () async => frontend);

  setUp(() async {
    temp = await Directory.systemTemp.createTemp('xenia_settings_');
    frontend = Directory(path.join(temp.path, 'Frontend'));
  });

  tearDown(() async {
    await temp.delete(recursive: true);
  });

  test('a game overrides all games, which override the engine; inheriting again works', () async {
    final settings = service();
    await settings.load();
    expect(settings.resolve('framerate_limit').source, XeniaValueSource.engine);
    expect(settings.resolve('framerate_limit').value, '0');
    await settings.setGlobal('framerate_limit', '60');
    await settings.setGame('title:4D5307E6', 'framerate_limit', '30');
    expect(settings.resolve('framerate_limit', gameKey: 'title:4D5307E6').value, '30');
    expect(settings.resolve('framerate_limit', gameKey: 'title:4D5307E6').source, XeniaValueSource.game);
    expect(settings.resolve('framerate_limit', gameKey: 'title:41560817').value, '60');
    expect(settings.resolve('framerate_limit', gameKey: 'title:41560817').source, XeniaValueSource.global);
    await settings.setGame('title:4D5307E6', 'framerate_limit', null);
    expect(settings.resolve('framerate_limit', gameKey: 'title:4D5307E6').value, '60');
    await settings.setGame('title:4D5307E6', 'present_letterbox', 'false');
    await settings.resetGame('title:4D5307E6');
    expect(settings.hasGameOverrides('title:4D5307E6'), isFalse);
    await settings.resetGlobal();
    expect(settings.resolve('framerate_limit').source, XeniaValueSource.engine);
  });

  test('choices survive a restart and stay isolated per game', () async {
    final first = service();
    await first.setGame('title:4D5307E6', 'user_language', '4');
    await first.setGame('title:4D5307E6', 'xma_decoder', 'old');
    await first.setGlobal('apu_max_queued_frames', '16');

    final restarted = service();
    await restarted.load();
    final halo = await restarted.launchSettings(gameKey: 'title:4D5307E6', uiLocale: const Locale('en'));
    final other = await restarted.launchSettings(gameKey: 'title:41560817', uiLocale: const Locale('en'));
    expect(halo['user_language'], '4');
    expect(halo['xma_decoder'], 'old');
    expect(other['user_language'], '1');
    expect(other['xma_decoder'], 'new');
    expect(halo['apu_max_queued_frames'], '16');
    expect(other['apu_max_queued_frames'], '16');
    // Every managed key is sent at every launch, so nothing of a previous
    // title can survive into the next one.
    expect(halo.keys.toSet(), XeniaSettingsService.managedKeys);
    expect(other.keys.toSet(), XeniaSettingsService.managedKeys);
  });

  test('values outside the engine catalogue are refused and dropped from the file', () async {
    final settings = service();
    expect(() => settings.setGlobal('draw_resolution_scale', '2'), throwsArgumentError);
    expect(() => settings.setGlobal('framerate_limit', '75'), throwsArgumentError);
    await frontend.create(recursive: true);
    await File(path.join(frontend.path, XeniaSettingsService.fileName)).writeAsString(jsonEncode({
      'version': 1,
      'global': {'framerate_limit': '999', 'gpu': 'vulkan', 'mount_cache': 'false'},
      'games': {'title:4D5307E6': {'user_language': '10'}},
    }));
    final reloaded = service();
    await reloaded.load();
    expect(reloaded.globalValue('framerate_limit'), isNull);
    expect(reloaded.globalValue('gpu'), isNull);
    expect(reloaded.globalValue('mount_cache'), 'false');
    expect(reloaded.hasGameOverrides('title:4D5307E6'), isFalse, reason: '10 is not an Xbox language ID');
  });

  test('Automatic console language follows the RewindBox language; region follows the device', () async {
    final settings = service();
    Future<Map<String, String>> launch(Locale ui, [Locale? device]) =>
        settings.launchSettings(gameKey: 'title:4D5307E6', uiLocale: ui, deviceLocale: device);
    expect((await launch(const Locale('fr')))['user_language'], '4');
    expect((await launch(const Locale('ja')))['user_language'], '2');
    expect((await launch(const Locale('ko')))['user_language'], '7');
    expect((await launch(const Locale('ru')))['user_language'], '12');
    expect((await launch(const Locale('pt')))['user_language'], '9');
    expect((await launch(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')))['user_language'], '8');
    expect((await launch(const Locale('zh')))['user_language'], '17');
    expect((await launch(const Locale('id')))['user_language'], '1', reason: 'no Indonesian on the Xbox 360');
    expect((await launch(const Locale('en'), const Locale('fr', 'FR')))['user_country'], '34');
    expect((await launch(const Locale('en'), const Locale('ja', 'JP')))['user_country'], '53');
    expect((await launch(const Locale('en'), const Locale('en', 'AQ')))['user_country'], '103');
    // An explicit choice wins over Automatic, for this game only.
    await settings.setGame('title:4D5307E6', 'user_language', '3');
    expect((await launch(const Locale('fr')))['user_language'], '3');
    expect(
      (await settings.launchSettings(gameKey: 'title:41560817', uiLocale: const Locale('fr')))['user_language'],
      '4',
    );
  });

  test('a game key comes from the title ID inside the image, not from its file name', () async {
    final image = await writeXboxImage(path.join(temp.path, 'Whatever Name.iso'));
    expect(await XeniaSettingsService.gameKeyForFile(image.path), 'title:4D5307E6');
    final renamed = await image.rename(path.join(temp.path, 'Renamed.iso'));
    expect(await XeniaSettingsService.gameKeyForFile(renamed.path), 'title:4D5307E6');
    expect(XeniaSettingsService.gameKey(romPath: '/x/Game.ZAR'), 'file:game.zar');
  });

  test('the native bridge accepts exactly the Dart catalogue keys', () {
    final native = File('packages/xenia_internal_bridge/ios/Classes/XeniaInternalBridgePlugin.mm').readAsStringSync();
    final block = RegExp(r'setWithArray:@\[(.*?)\]', dotAll: true).firstMatch(native)!.group(1)!;
    final keys = RegExp(r'@"([a-zA-Z0-9_]+)"').allMatches(block).map((m) => m.group(1)!).toSet();
    expect(keys, XeniaSettingsService.managedKeys);
  });

  test('every option, value label and message exists in the 12 project locales with its placeholders', () {
    const locales = ['en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'];
    expect(XeniaLocale.values.keys.toSet(), locales.toSet());
    final english = XeniaLocale.values['en']!;
    for (final option in XeniaSettingsService.options) {
      expect(english.containsKey(option.key), isTrue, reason: option.key);
    }
    final placeholder = RegExp(r'\{[a-z]+\}');
    for (final code in locales) {
      final values = XeniaLocale.values[code]!;
      expect(values.keys.toSet(), english.keys.toSet(), reason: code);
      for (final entry in english.entries) {
        final translated = values[entry.key]!;
        expect(translated.trim(), isNotEmpty, reason: '$code:${entry.key}');
        expect(
          placeholder.allMatches(translated).map((m) => m.group(0)).toSet(),
          placeholder.allMatches(entry.value).map((m) => m.group(0)).toSet(),
          reason: '$code:${entry.key}',
        );
      }
      if (code != 'en') {
        // Not an English fallback presented as a translation.
        for (final key in ['importGames', 'requiresIOS26', 'engineMissing', 'languageHelp', 'appliesNextLaunch']) {
          expect(values[key], isNot(english[key]), reason: '$code:$key');
        }
      }
    }
    expect(XeniaLocale.values['zh_Hant']!['languageHelp'], isNot(XeniaLocale.values['zh']!['languageHelp']));
    expect(XeniaLocale.codeFor(const Locale('zh', 'TW')), 'zh_Hant');
    expect(XeniaLocale.launchErrorKey('bootFailed'), 'launchFailed');
    expect(XeniaLocale.launchErrorKey('requiresIOS26'), 'requiresIOS26');
  });
}
