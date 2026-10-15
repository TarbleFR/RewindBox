import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/libretro_core_catalog.dart';
import 'package:neostation/services/libretro_overlay_converter.dart';
import 'package:neostation/services/libretro_skin_catalog_service.dart';
import 'package:neostation/services/libretro_skin_catalogs.dart';
import 'package:neostation/services/libretro_skin_compatibility.dart';

void main() {
  test('repository paths are encoded once, including spaces, percent, hash and Unicode', () {
    const overlay = LibretroOverlayEntry(id: 'test', source: 'pocketarch',
      path: 'Touch Overlays/Phone Taller (9x20)/PSX/psx_phone_beige.cfg',
      repository: 'stunrelay/PocketArch', commit: '33dc23be', device: 'iphone', files: []);
    final uri = overlay.fileUri(overlay.path);
    expect(uri.pathSegments, ['stunrelay', 'PocketArch', '33dc23be', 'Touch Overlays',
      'Phone Taller (9x20)', 'PSX', 'psx_phone_beige.cfg']);
    expect(uri.toString(), isNot(contains('%2520')));
    const resource = 'images/été 100% #1.png';
    expect(overlay.fileUri(resource).pathSegments.skip(3).join('/'), resource);
  });

  test('console candidates use registry identifiers and aliases, never UI visibility', () {
    LibretroSkinCatalogEntry entry(String code) => LibretroSkinCatalogEntry(
      id: code, name: code, systems: [code], downloadURL: 'https://example.com/skin.zip');
    for (final code in ['psx', 'PS1', ' PlayStation ', 'public.aoshuang.game.ps1']) {
      expect(entry(code).consoles, ['psx'], reason: code);
    }
    for (final platform in LibretroCoreCatalog.consoles.values) {
      expect(entry(platform.id).consoles, contains(platform.id), reason: platform.id);
      expect(entry(platform.importSystem).consoles, contains(platform.id), reason: platform.importSystem);
      for (final code in platform.catalogSystems) {
        expect(entry(code.toUpperCase()).consoles, contains(platform.id), reason: code);
      }
    }
    expect(entry('PS2').consoles, isEmpty);
    expect(entry('dreamcast').consoles, isEmpty);
    const metadataOnly = LibretroSkinCatalogEntry(id: 'meta', name: 'PS1',
      gameTypeIdentifier: 'public.aoshuang.game.ps1', downloadURL: 'https://example.com/skin.zip');
    expect(metadataOnly.consoles, ['psx']);
  });

  final manifest = jsonDecode(File('test/fixtures/libretro_overlays/pocketarch/manifest.json').readAsStringSync()) as Map;
  final configs = manifest['configs'] as Map;
  final resources = manifest['resources'] as Map;
  final entries = LibretroSkinCatalogs.parseOverlayIndex(File(LibretroSkinCatalogs.overlayIndexAsset).readAsStringSync())
      .where((e) => e.source == LibretroSkinSources.pocketArch).toList();

  test('all indexed PocketArch originals are audited, with only the incomplete PSP files excluded', () {
    expect(entries.length, 28);
    expect(configs.keys.toSet(), entries.map((e) => e.overlay!.id).toSet());
    expect(entries.where((e) => e.excludedReason != null).map((e) => e.overlay!.id).toSet(),
      {'po-d0a8dfa31921', 'po-b3669fc2b2dd'});
  });

  for (final entry in entries) {
    for (final console in entry.consoles) {
      test('original ${entry.overlay!.id} on $console: geometry, controls and complete resources', () async {
        final overlay = entry.overlay!;
        final original = configs[overlay.id] as Map;
        final text = original['text'] as String;
        expect(sha256.convert(utf8.encode(text)).toString(), original['sha256']);
        expect(overlay.commit, manifest['commit']);
        expect(overlay.path, original['path']);
        final conversion = LibretroOverlayConverter.convert(text, cfgPath: overlay.path,
          console: console, name: entry.name, identifier: 'org.neostation.audit.${overlay.id}.$console');
        expect(conversion.problems, isEmpty);
        expect(conversion.orientations, ['portrait', 'landscape']);
        final missing = conversion.files.values.where((file) => !overlay.files.contains(file)).toSet();
        if (entry.excludedReason != null) {
          expect(entry.excludedReason, LibretroSkinCompatibility.overlayUnsupported);
          expect(missing, isNotEmpty, reason: 'a real upstream resource is missing');
          return;
        }
        expect(missing, isEmpty);
        for (final resource in conversion.files.values) {
          final image = resources[resource] as Map;
          expect(image['bytes'], greaterThan(0));
          expect((image['size'] as List).every((side) => (side as int) > 0 && side <= 8192), isTrue);
        }
        final output = Platform.environment['NEOSTATION_CATALOG_FIXTURES'];
        if (output != null) {
          final folder = await Directory('$output/${overlay.id}-$console').create(recursive: true);
          await File('${folder.path}/info.json').writeAsString(jsonEncode(conversion.info));
          await File('${folder.path}/resources.json').writeAsString(jsonEncode(conversion.files));
          await File('${folder.path}/source.json').writeAsString(jsonEncode({
            'repository': overlay.repository, 'commit': overlay.commit, 'console': console,
            'id': overlay.id, 'hashes': {for (final file in conversion.files.values) file: resources[file]},
          }));
        }
      });
    }
  }
}
