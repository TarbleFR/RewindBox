// A system missing from the active downloaded pack shows its default image
// (RewindBox Glacier) instead of an empty card.
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/services/neo_assets_service.dart';
import 'package:neostation/services/system_art/bundled_system_art.dart';
import 'package:neostation/services/system_art/system_art_alias_table.dart';
import 'package:path/path.dart' as path;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory themes;
  late NeoAssetsProvider assets;

  String art(String pack, String system) {
    final file =
        File(path.join(themes.path, pack, 'backgrounds', '$system.webp'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(const [0]);
    return file.path;
  }

  setUp(() {
    themes = Directory.systemTemp.createTempSync('system-art-fallback-');
    NeoAssetsService.debugSetThemesDirectory(themes.path);
    SystemArtAliasTable.invalidate();
    assets = NeoAssetsProvider();
  });

  tearDown(() {
    assets.dispose();
    NeoAssetsService.debugSetThemesDirectory(null);
    SystemArtAliasTable.invalidate();
    themes.deleteSync(recursive: true);
  });

  test('the pack art wins, a missing system takes the Glacier image', () {
    final packSnes = art('neo-pack', 'snes');
    art(BundledSystemArt.folder, 'snes');
    final glacierSwitch2 = art(BundledSystemArt.folder, 'switch2');
    assets.debugSetActiveTheme('neo-pack');

    expect(assets.getBackgroundForSystemSync('snes'), packSnes);
    expect(assets.getBackgroundForSystemSync('switch2'), glacierSwitch2);
  });

  test('any image added later to the default pack fills every pack', () {
    // The rule is not a list of systems: a console added to Glacier in a
    // future update is picked up as soon as its image is installed.
    art('neo-pack', 'snes');
    assets.debugSetActiveTheme('neo-pack');
    expect(assets.getBackgroundForSystemSync('future-console'), isNotNull);
    expect(assets.defaultBackgroundForSystemSync('future-console'), isNull);
    final added = art(BundledSystemArt.folder, 'future-console');
    expect(assets.getBackgroundForSystemSync('future-console'), added);
  });

  test('without a default image the former missing path is kept', () {
    art('neo-pack', 'snes');
    assets.debugSetActiveTheme('neo-pack');
    final missing = assets.getBackgroundForSystemSync('switch2');
    expect(missing, isNotNull);
    expect(File(missing!).existsSync(), isFalse);
    expect(assets.defaultBackgroundForSystemSync('switch2'), isNull);
  });

  test('Glacier itself and "None" are unchanged', () {
    art(BundledSystemArt.folder, 'switch2');
    assets.debugSetActiveTheme(BundledSystemArt.folder);
    expect(assets.defaultBackgroundForSystemSync('switch2'), isNull);

    assets.debugSetActiveTheme('');
    expect(assets.getBackgroundForSystemSync('switch2'), isNull);
  });
}
