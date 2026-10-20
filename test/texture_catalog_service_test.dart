import 'dart:async';

import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neo_texture_catalog/neo_texture_catalog.dart';
import 'package:neostation/l10n/texture_catalog_locale.dart';
import 'package:neostation/services/libretro_internal_service.dart';
import 'package:neostation/services/texture_catalog_service.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Build 486: the Flutter side of the unified HD textures page. The native
/// page (neo_texture_catalog) is exercised on macOS and UIKit
/// (test/texture_catalog_native_test.py, test/texture_catalog_ui_test.py).
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  const channel = MethodChannel('neostation/texture_catalog');
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;

  tearDown(() {
    TextureCatalogService.debugIsIOS = null;
    messenger.setMockMethodCallHandler(channel, null);
    channel.setMethodCallHandler(null);
  });

  /// A call from the native page to Dart, answered through the channel.
  Future<Object?> fromNative(String method, Object? arguments) async {
    const codec = StandardMethodCodec();
    final reply = Completer<ByteData?>();
    await messenger.handlePlatformMessage(channel.name, codec.encodeMethodCall(MethodCall(method, arguments)), reply.complete);
    final data = await reply.future;
    return data == null ? null : codec.decodeEnvelope(data);
  }

  test('only the consoles whose embedded engine replaces textures', () {
    for (final entry in {
      'ps2': 'ps2', 'PS2': 'ps2', 'gc': 'gc', 'ngc': 'gc', 'gamecube': 'gc', 'wii': 'wii',
      'psp': 'psp', 'pspminis': 'psp', '3ds': '3ds', 'n3ds': '3ds',
      // Mupen64Plus-Next (GLideN64) reads hires_texture packs: the N64 catalogue.
      'n64': 'n64', 'N64': 'n64',
      // Build 489: Beetle PSX HW (Vulkan) reads <content>-texture-replacements: the PS1 catalogue.
      'psx': 'ps1', 'ps1': 'ps1', 'PSX': 'ps1', 'playstation': 'ps1',
      // Mesen reads HdPacks/<content>/hires.txt: the NES catalogue (Famicom, FDS and hacks included).
      'nes': 'nes', 'NES': 'nes', 'fc': 'nes', 'famicom': 'nes', 'fds': 'nes', 'nes-hacks': 'nes',
    }.entries) {
      expect(TextureCatalogService.textureSystem(entry.key), entry.value, reason: entry.key);
    }
    // Neither DeSmuME nor melonDS replaces textures: no Nintendo DS catalogue.
    for (final folder in ['nds', 'ps3', 'saturn', 'switch', 'gba', 'snes', 'dreamcast', 'wiiu', '']) {
      expect(TextureCatalogService.textureSystem(folder), isNull, reason: folder);
    }
  });

  test('the rows exist on iOS only', () {
    TextureCatalogService.debugIsIOS = false;
    expect(TextureCatalogService.supports('ps2'), isFalse);
    TextureCatalogService.debugIsIOS = true;
    expect(TextureCatalogService.supports('ps2'), isTrue);
    expect(TextureCatalogService.supports('psx'), isTrue);
    expect(TextureCatalogService.supports('nes'), isTrue);
    expect(TextureCatalogService.supports('nds'), isFalse);
  });

  test('NES packs: the page records Mesen as one game\'s engine, nothing else', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    expect(await TextureCatalogService.selectCore('nes/Contra (USA).nes', 'mesen'), isTrue);
    expect(await LibretroInternalService.coreChoiceFor('nes', 'Contra (USA).nes'), 'mesen');
    // Another game of the system keeps its engine (Nestopia, the default).
    expect(await LibretroInternalService.coreChoiceFor('nes', 'Pac-Man (USA).nes'), isNull);
    expect(await TextureCatalogService.selectCore('fds/Zelda no Densetsu (Japan).fds', 'mesen'), isTrue);
    expect(await LibretroInternalService.coreChoiceFor('fds', 'Zelda no Densetsu (Japan).fds'), 'mesen');
    // A core the system does not offer, a system without Mesen, malformed keys: refused, nothing recorded.
    expect(await TextureCatalogService.selectCore('nes/Contra (USA).nes', 'snes9x'), isFalse);
    expect(await TextureCatalogService.selectCore('snes/Game (USA).sfc', 'mesen'), isFalse);
    for (final key in ['', 'nes', 'nes/', '/Contra (USA).nes', 'unknown/Game.nes']) {
      expect(await TextureCatalogService.selectCore(key, 'mesen'), isFalse, reason: key);
    }
    expect(await LibretroInternalService.coreChoiceFor('nes', 'Contra (USA).nes'), 'mesen');
    expect(await LibretroInternalService.coreChoiceFor('snes', 'Game (USA).sfc'), isNull);
    expect((await SharedPreferences.getInstance()).getKeys().length, 2);
  });

  test('the native page asks for Mesen through the plugin channel', () async {
    SharedPreferences.setMockInitialValues(<String, Object>{});
    final asked = <String>[];
    NeoTextureCatalog.setCoreSelector((gameKey, core) {
      asked.add('$gameKey $core');
      return TextureCatalogService.selectCore(gameKey, core);
    });
    expect(await fromNative('selectLibretroCore', {'gameKey': 'nes/Contra (USA).nes', 'core': 'mesen'}), isTrue);
    expect(await LibretroInternalService.coreChoiceFor('nes', 'Contra (USA).nes'), 'mesen');
    expect(await fromNative('selectLibretroCore', {'gameKey': 'snes/Game (USA).sfc', 'core': 'mesen'}), isFalse);
    // Malformed arguments are refused before the selector runs.
    expect(await fromNative('selectLibretroCore', {'gameKey': 'nes/Contra (USA).nes'}), isFalse);
    expect(await fromNative('selectLibretroCore', 'nes/Contra (USA).nes'), isFalse);
    expect(asked, ['nes/Contra (USA).nes mesen', 'snes/Game (USA).sfc mesen']);
    // Any other call from the page is not handled by Dart.
    expect(await fromNative('somethingElse', null), isNull);
  });

  test('twelve languages, Traditional Chinese selected by script or region', () {
    const languages = ['en', 'es', 'ru', 'zh', 'zh_Hant', 'pt', 'fr', 'de', 'it', 'id', 'ja', 'ko'];
    expect(TextureCatalogLocale.labels.keys.toSet(), languages.toSet());
    final english = TextureCatalogLocale.labels['en']!.keys.toSet();
    for (final language in languages) {
      final table = TextureCatalogLocale.labels[language]!;
      expect(table.keys.toSet(), english, reason: language);
      for (final text in table.values) {
        expect(text.trim(), isNotEmpty, reason: language);
      }
    }
    expect(TextureCatalogLocale.localeKey(const Locale.fromSubtags(languageCode: 'zh', scriptCode: 'Hant')), 'zh_Hant');
    expect(TextureCatalogLocale.localeKey(const Locale('zh', 'TW')), 'zh_Hant');
    expect(TextureCatalogLocale.localeKey(const Locale('zh', 'HK')), 'zh_Hant');
    expect(TextureCatalogLocale.localeKey(const Locale('zh', 'CN')), 'zh');
    expect(TextureCatalogLocale.localeKey(const Locale('nl')), 'en');
    expect(TextureCatalogLocale.nativeLocale(const Locale('zh', 'TW')), 'zh-Hant');
    expect(TextureCatalogLocale.text(const Locale('fr'), 'menuTitle'), 'Textures HD');
    expect(TextureCatalogLocale.text(const Locale('zh', 'TW'), 'menuTitle'),
        isNot(TextureCatalogLocale.text(const Locale('zh', 'CN'), 'menuTitle')));
  });

  test('the page opens through the plugin channel with the given options', () async {
    final calls = <MethodCall>[];
    messenger.setMockMethodCallHandler(channel, (call) async {
      calls.add(call);
      return call.method == 'open' ? true : {'state': 'bundled', 'pack_count': 3};
    });
    final opened = await NeoTextureCatalog.open({
      'system': 'gc', 'locale': 'fr', 'gamePath': '/Documents/roms/gc/game.rvz', 'dolphinUser': '/Library/Dolphin/User',
    });
    expect(opened, isTrue);
    expect(calls.single.method, 'open');
    expect(calls.single.arguments, {
      'system': 'gc', 'locale': 'fr', 'gamePath': '/Documents/roms/gc/game.rvz', 'dolphinUser': '/Library/Dolphin/User',
    });
    final snapshot = await NeoTextureCatalog.snapshot();
    expect(snapshot['state'], 'bundled');
    // A page that could not be shown is reported as such, never as a success.
    messenger.setMockMethodCallHandler(channel, (call) async => null);
    expect(await NeoTextureCatalog.open({'system': 'ps2'}), isFalse);
  });
}
