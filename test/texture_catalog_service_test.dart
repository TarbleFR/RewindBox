import 'package:flutter/services.dart';
import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neo_texture_catalog/neo_texture_catalog.dart';
import 'package:neostation/l10n/texture_catalog_locale.dart';
import 'package:neostation/services/texture_catalog_service.dart';

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
  });

  test('only the consoles whose embedded engine replaces textures', () {
    for (final entry in {
      'ps2': 'ps2', 'PS2': 'ps2', 'gc': 'gc', 'ngc': 'gc', 'gamecube': 'gc', 'wii': 'wii',
      'psp': 'psp', 'pspminis': 'psp', '3ds': '3ds', 'n3ds': '3ds',
    }.entries) {
      expect(TextureCatalogService.textureSystem(entry.key), entry.value, reason: entry.key);
    }
    for (final folder in ['psx', 'n64', 'nds', 'ps3', 'switch', 'gba', 'dreamcast', 'wiiu', '']) {
      expect(TextureCatalogService.textureSystem(folder), isNull, reason: folder);
    }
  });

  test('the rows exist on iOS only', () {
    TextureCatalogService.debugIsIOS = false;
    expect(TextureCatalogService.supports('ps2'), isFalse);
    TextureCatalogService.debugIsIOS = true;
    expect(TextureCatalogService.supports('ps2'), isTrue);
    expect(TextureCatalogService.supports('psx'), isFalse);
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
