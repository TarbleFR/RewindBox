// The embedded fallback tile (RewindBox Glacier), shown for a system the active downloaded pack lacks, is inset by the
// transparent margin of that pack's own tiles, so it is the size of its neighbours. IPA 727: under a pack whose capsules
// sit inside a margin, with their own rounded card and shadow, the full-bleed Switch 2 fallback read about 7 % larger.
// The pack's own tiles and opaque packs are drawn as before. The margin is measured once per pack, asynchronously, and
// is 0 while pending and on any decode error.
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:neostation/models/my_systems.dart';
import 'package:neostation/providers/neo_assets_provider.dart';
import 'package:neostation/screens/systems_screen/my_systems_section/system_card.dart';
import 'package:neostation/services/neo_assets_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/services/system_art/bundled_system_art.dart';
import 'package:neostation/services/system_art/system_art_alias_table.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';
import 'package:path/path.dart' as path;

/// An RGBA tile: an opaque card inside [margin] transparent pixels, with an optional [shadow] ring of alpha 60.
Uint8List tile(int width, int height, {int margin = 0, int shadow = 0, int? left}) {
  final data = Uint8List(width * height * 4);
  final l = left ?? margin;
  for (var y = 0; y < height; y++) {
    for (var x = 0; x < width; x++) {
      final card = x >= l && x < width - margin && y >= margin && y < height - margin;
      final ring = x >= l - shadow && x < width - margin + shadow && y >= margin - shadow && y < height - margin + shadow;
      final i = (y * width + x) * 4;
      data[i] = 200;
      data[i + 1] = 30;
      data[i + 2] = 40;
      data[i + 3] = card ? 255 : (ring ? 60 : 0);
    }
  }
  return data;
}

/// A minimal PNG (8-bit RGBA, no filter) of [rgba], so the engine's own decoder reads it.
Uint8List png(Uint8List rgba, int width, int height) {
  final crcTable = List<int>.generate(256, (n) {
    var c = n;
    for (var k = 0; k < 8; k++) {
      c = (c & 1) != 0 ? 0xEDB88320 ^ (c >> 1) : c >> 1;
    }
    return c;
  });
  int crc(List<int> bytes) {
    var c = 0xFFFFFFFF;
    for (final b in bytes) {
      c = crcTable[(c ^ b) & 0xFF] ^ (c >> 8);
    }
    return c ^ 0xFFFFFFFF;
  }

  List<int> chunk(String type, List<int> body) {
    final typed = [...type.codeUnits, ...body];
    final length = ByteData(4)..setUint32(0, body.length);
    final check = ByteData(4)..setUint32(0, crc(typed));
    return [...length.buffer.asUint8List(), ...typed, ...check.buffer.asUint8List()];
  }

  final header = ByteData(13)
    ..setUint32(0, width)
    ..setUint32(4, height)
    ..setUint8(8, 8)
    ..setUint8(9, 6);
  final raw = <int>[];
  for (var y = 0; y < height; y++) {
    raw.add(0);
    raw.addAll(rgba.sublist(y * width * 4, (y + 1) * width * 4));
  }
  return Uint8List.fromList([
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A,
    ...chunk('IHDR', header.buffer.asUint8List()),
    ...chunk('IDAT', zlib.encode(raw)),
    ...chunk('IEND', const []),
  ]);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('the margin of one tile', () {
    test('an opaque tile, or a fully transparent one, has none', () {
      expect(NeoAssetsProvider.tileInsetFromRgba(tile(96, 96), 96, 96), 0);
      final empty = Uint8List(96 * 96 * 4);
      expect(NeoAssetsProvider.tileInsetFromRgba(empty, 96, 96), 0);
      expect(NeoAssetsProvider.tileInsetFromRgba(Uint8List(3), 96, 96), 0, reason: 'a short buffer');
    });

    test('a card inside a transparent margin gives the margin; a soft shadow does not count', () {
      expect(NeoAssetsProvider.tileInsetFromRgba(tile(100, 100, margin: 5), 100, 100), closeTo(0.05, 1e-9));
      expect(NeoAssetsProvider.tileInsetFromRgba(tile(100, 100, margin: 5, shadow: 3), 100, 100), closeTo(0.05, 1e-9));
      expect(NeoAssetsProvider.tileInsetFromRgba(tile(100, 100, margin: 6, left: 3), 100, 100), closeTo(0.03, 1e-9),
          reason: 'the smallest side');
    });

    test('the median of the tiles, clamped to 0–12 %', () {
      expect(NeoAssetsProvider.medianInset([0.03, 0.05, 0.04, 0.2]), closeTo(0.045, 1e-9));
      expect(NeoAssetsProvider.medianInset([0.04, 0.2, 0.05]), closeTo(0.05, 1e-9));
      expect(NeoAssetsProvider.medianInset([0.3]), 0.12);
      expect(NeoAssetsProvider.medianInset([-0.1]), 0);
      expect(NeoAssetsProvider.medianInset(const []), 0);
    });
  });

  group('the pack measure', () {
    late Directory root;
    late Directory themes;
    late NeoAssetsProvider assets;

    File write(String name, List<int> bytes) =>
        File(path.join(root.path, name))
          ..createSync(recursive: true)
          ..writeAsBytesSync(bytes);

    void pack(String folder, List<int> Function(int index) bytes, {int count = 3}) {
      for (var i = 0; i < count; i++) {
        File(path.join(themes.path, folder, 'backgrounds', 'system$i.webp'))
          ..createSync(recursive: true)
          ..writeAsBytesSync(bytes(i));
      }
    }

    setUp(() {
      root = Directory.systemTemp.createTempSync('system-art-inset-');
      themes = Directory(path.join(root.path, 'themes'))..createSync();
      NeoAssetsService.debugSetThemesDirectory(themes.path);
      SystemArtAliasTable.invalidate();
      assets = NeoAssetsProvider();
    });

    tearDown(() {
      assets.dispose();
      NeoAssetsService.debugSetThemesDirectory(null);
      SystemArtAliasTable.invalidate();
      root.deleteSync(recursive: true);
    });

    test('tiles decoded by the engine: a margin is found, an opaque pack gives 0', () async {
      final margined = [for (var i = 0; i < 3; i++) write('m$i.png', png(tile(100, 100, margin: 5, shadow: 2), 100, 100))];
      expect(await NeoAssetsProvider.measureTileInset(margined), closeTo(0.05, 0.012));
      final opaque = [for (var i = 0; i < 3; i++) write('o$i.png', png(tile(100, 100), 100, 100))];
      expect(await NeoAssetsProvider.measureTileInset(opaque), 0);
      expect(await NeoAssetsProvider.measureTileInset(const []), 0);
    });

    test('a decode failure gives 0, even beside good tiles', () async {
      final broken = write('broken.webp', const [1, 2, 3, 4, 5]);
      expect(await NeoAssetsProvider.measureTileInset([broken]), 0);
      final good = write('good.png', png(tile(100, 100, margin: 5), 100, 100));
      expect(await NeoAssetsProvider.measureTileInset([good, broken]), 0);
      expect(await NeoAssetsProvider.measureTileInset([File(path.join(root.path, 'missing.png'))]), 0);
    });

    test('a pack with margins: 0 while pending, then its margin, measured once, listeners told once', () async {
      pack('margin-pack', (_) => png(tile(100, 100, margin: 5, shadow: 2), 100, 100));
      assets.debugSetActiveTheme('margin-pack');
      var told = 0;
      assets.addListener(() => told++);
      final measure = assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, 0, reason: 'pending');
      await measure;
      expect(assets.fallbackInset, closeTo(0.05, 0.012));
      expect(told, 1);
      // Once per folder: a second call measures nothing.
      pack('margin-pack', (_) => png(tile(100, 100), 100, 100));
      await assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, closeTo(0.05, 0.012));
      expect(told, 1);
    });

    test('an opaque pack and a broken pack give 0 and tell no one', () async {
      var told = 0;
      assets.addListener(() => told++);
      pack('opaque-pack', (_) => png(tile(100, 100), 100, 100));
      assets.debugSetActiveTheme('opaque-pack');
      told = 0;
      await assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, 0);
      pack('broken-pack', (i) => i == 1 ? const [9, 9, 9] : png(tile(100, 100, margin: 5), 100, 100));
      assets.debugSetActiveTheme('broken-pack');
      told = 0;
      await assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, 0);
      expect(told, 0);
    });

    test('the embedded pack, "None" and a pack not installed yet are never inset', () async {
      pack(BundledSystemArt.folder, (_) => png(tile(100, 100, margin: 5), 100, 100));
      assets.debugSetActiveTheme(BundledSystemArt.folder);
      await assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, 0);
      assets.debugSetActiveTheme('');
      await assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, 0);
      // Not installed: not measured, and not remembered as 0 either.
      assets.debugSetActiveTheme('later-pack');
      await assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, 0);
      pack('later-pack', (_) => png(tile(100, 100, margin: 5), 100, 100));
      await assets.ensureFallbackInsetMeasured();
      expect(assets.fallbackInset, closeTo(0.05, 0.012));
    });
  });

  group('the system card', () {
    late Directory themes;
    late NeoAssetsProvider assets;
    late String fallbackArt;
    late String packArt;

    setUp(() {
      themes = Directory.systemTemp.createTempSync('system-art-card-');
      NeoAssetsService.debugSetThemesDirectory(themes.path);
      SystemArtAliasTable.invalidate();
      final art = File('assets/system_art/rewindbox-glacier/backgrounds/switch2.webp').readAsBytesSync();
      fallbackArt = (File(path.join(themes.path, BundledSystemArt.folder, 'backgrounds', 'switch2.webp'))
            ..createSync(recursive: true)
            ..writeAsBytesSync(art))
          .path;
      packArt = (File(path.join(themes.path, 'test-pack', 'backgrounds', 'snes.webp'))
            ..createSync(recursive: true)
            ..writeAsBytesSync(art))
          .path;
      assets = NeoAssetsProvider()..debugSetActiveTheme('test-pack');
    });

    tearDown(() {
      assets.dispose();
      NeoAssetsService.debugSetThemesDirectory(null);
      SystemArtAliasTable.invalidate();
      themes.deleteSync(recursive: true);
    });

    Future<void> pump(WidgetTester tester) async {
      SfxService().setEnabled(false);
      addTearDown(() => SfxService().setEnabled(true));
      Widget card(String folder, String title) => SizedBox(
        width: 150,
        height: 190,
        child: SystemCard(info: SystemInfo(folderName: folder, title: title), isSelected: false),
      );
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (_, _) => ChangeNotifierProvider.value(
            value: assets,
            child: MaterialApp(
              theme: ThemeData.dark().copyWith(
                extensions: [LiquidGlassTheme(settings: InterfaceStyleSettings(showSystemBubbles: false))],
              ),
              home: MediaQuery(
                data: const MediaQueryData(size: Size(844, 390), disableAnimations: true),
                child: Scaffold(
                  body: Center(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [card('switch2', 'Nintendo Switch 2'), const SizedBox(width: 24), card('snes', 'Super Nintendo')],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pump();
    }

    Rect artRect(WidgetTester tester, String file) => tester.getRect(find.byKey(ValueKey('${file}_0')));

    testWidgets('under a pack with margins only the fallback is inset, corners scaled with it', (tester) async {
      await tester.binding.setSurfaceSize(const Size(844, 390));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      assets.debugSetFallbackInset('test-pack', 0.05);
      await pump(tester);
      expect(find.byKey(const ValueKey('system-art-fallback-inset')), findsOneWidget);
      final fallback = artRect(tester, fallbackArt);
      final own = artRect(tester, packArt);
      final side = own.width;
      expect(fallback.width, closeTo(side * 0.9, 0.5));
      expect(fallback.center.dx - tester.getRect(find.byType(SystemCard).first).center.dx, closeTo(0, 0.5));
      final padding = tester.widget<Padding>(find.byKey(const ValueKey('system-art-fallback-inset')));
      expect((padding.padding as EdgeInsets).left, closeTo(side * 0.05, 0.5));
      final clip = tester.widget<ClipRRect>(
        find.descendant(of: find.byKey(const ValueKey('system-art-fallback-inset')), matching: find.byType(ClipRRect)).first,
      );
      final ownClip = tester.widget<ClipRRect>(
        find.ancestor(of: find.byKey(ValueKey('${packArt}_0')), matching: find.byType(ClipRRect)).first,
      );
      expect((clip.borderRadius as BorderRadius).topLeft.x, closeTo((ownClip.borderRadius as BorderRadius).topLeft.x * 0.9, 1e-6));
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('an opaque pack: margin 0, the layout is unchanged', (tester) async {
      await tester.binding.setSurfaceSize(const Size(844, 390));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      assets.debugSetFallbackInset('test-pack', 0);
      await pump(tester);
      expect(find.byKey(const ValueKey('system-art-fallback-inset')), findsNothing);
      expect(artRect(tester, fallbackArt).size, artRect(tester, packArt).size);
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox());
    });
  });
}
