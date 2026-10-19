import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/neo_assets_service.dart';
import 'package:neostation/services/system_art/canvas_es_de_capsules.dart';

void main() {
  group('NeoAssetsService external System Art routing', () {
    test('routes RiiSU backgrounds to the original RiiSU repository', () {
      expect(
        NeoAssetsService.getBackgroundUrl('RiiSU', 'ps3'),
        'https://raw.githubusercontent.com/mult1v4c/RiiSU/main/themes/RiiSU/backgrounds/ps3.webp',
      );
      expect(
        NeoAssetsService.getBackgroundUrl('RiiSU', 'switch', ext: 'gif'),
        'https://raw.githubusercontent.com/mult1v4c/RiiSU/main/themes/RiiSU/backgrounds/switch.gif',
      );
    });

    test('routes RiiSU metadata to the original RiiSU repository', () {
      expect(
        NeoAssetsService.getThemeMetadataUrl('RiiSU'),
        'https://raw.githubusercontent.com/mult1v4c/RiiSU/main/themes/RiiSU/theme.json',
      );
    });

    test('keeps existing packs on the default NeoStation assets host', () {
      expect(
        NeoAssetsService.getBackgroundUrl('NeoStation', 'ps3'),
        'https://raw.githubusercontent.com/misobadev/neostation-assets/main/themes/NeoStation/backgrounds/ps3.webp',
      );
      expect(
        NeoAssetsService.getThemeMetadataUrl('NeoStation'),
        'https://raw.githubusercontent.com/misobadev/neostation-assets/main/themes/NeoStation/theme.json',
      );
    });
  });

  group('Canvas (ES-DE) System Art', () {
    const raw =
        'https://raw.githubusercontent.com/zenandiko/canvas-es-de/'
        '12d03b1856b892497a3fa1c943888c1f542f9236/theme/flat/webp';

    test('maps NeoStation folders and aliases to ES-DE capsules', () {
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'ps1'),
        '$raw/psx.webp',
      );
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'psx'),
        '$raw/psx.webp',
      );
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'Nintendo 3DS'),
        '$raw/3ds.webp',
      );
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'ds'),
        '$raw/nds.webp',
      );
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'GC'),
        '$raw/gc.webp',
      );
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'favorites'),
        '$raw/auto-favorites.webp',
      );
      // An alias that has its own capsule keeps it.
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'megadrivejp'),
        '$raw/megadrivejp.webp',
      );
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'md'),
        '$raw/megadrive.webp',
      );
    });

    test('requests nothing for an uncovered system or another format', () {
      expect(NeoAssetsService.getBackgroundUrl('CanvasESDE', 'vc4k'), isNull);
      expect(NeoAssetsService.getBackgroundUrl('CanvasESDE', 'gog'), isNull);
      expect(
        NeoAssetsService.getBackgroundUrl('CanvasESDE', 'ps2', ext: 'gif'),
        isNull,
      );
    });

    test('every capsule exists at the pinned revision', () {
      final published = File('tools/system_art/canvas-es-de-flat-webp.txt')
          .readAsLinesSync()
          .where((line) => line.trim().isNotEmpty)
          .toSet();
      expect(published, hasLength(247));
      for (final capsule in canvasEsDeCapsuleByFolder.values) {
        expect(published, contains(capsule));
      }
      for (final folder in canvasEsDeCapsuleByFolder.keys) {
        expect(folder, folder.toLowerCase());
      }
    });

    test('covers the main systems by their NeoStation id', () {
      final ids = <String>{};
      for (final file in Directory('assets/systems').listSync()) {
        if (file is! File || !file.path.endsWith('.json')) continue;
        final system = (jsonDecode(file.readAsStringSync())
            as Map<String, dynamic>)['system'] as Map<String, dynamic>;
        ids.add(system['id'] as String);
      }
      final uncovered = ids
          .where((id) => NeoAssetsService.canvasCapsuleFor(id) == null)
          .toSet();
      // The pack has no capsule for these systems; their cards keep the
      // default appearance.
      expect(uncovered, {
        'amazon',
        'gog',
        'music',
        'pet',
        'pico',
        'vc4k',
      });
    });
  });
}
