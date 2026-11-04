// Reconstructed after scratch cleanup. This is not the lost original harness.
// Runs production import, ZIP readers, classification, canonicalizer and preview
// reader with Flutter's real test engine. HTTP is served from the supplied ZIPs.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/services/dolphin_skins.dart';
import 'package:neostation/services/libretro_skin_catalog_service.dart';
import 'package:neostation/services/libretro_skin_catalogs.dart';
import 'package:neostation/services/libretro_skin_compatibility.dart';
import 'package:neostation/services/libretro_skin_remote_inspector.dart';
import 'package:neostation/services/libretro_skin_service.dart';
import 'package:path/path.dart' as path;

Map<String, dynamic> readInfo(String directory) => Map<String, dynamic>.from(
  jsonDecode(File(path.join(directory, 'info.json')).readAsStringSync()) as Map,
);
Future<void> saveInfo(String directory, Map<String, dynamic> info) async {
  await File(path.join(directory, 'info.json')).writeAsString(jsonEncode(info));
}

String background(Map<String, dynamic> info, String orientation) {
  final layout = DolphinSkins.layoutFor(info, orientation)!.$1;
  final assets = layout['assets'] as Map;
  return (assets['resizable'] ??
          assets['large'] ??
          assets['medium'] ??
          assets['small'])
      as String;
}

Future<Directory> copyFixture(String source, Directory parent) async {
  final target = await Directory(path.join(parent.path, 'fixture')).create();
  await for (final entity in Directory(
    source,
  ).list(recursive: true, followLinks: false)) {
    final dest = path.join(
      target.path,
      path.relative(entity.path, from: source),
    );
    if (entity is Directory) {
      await Directory(dest).create(recursive: true);
    } else if (entity is File) {
      await File(dest).parent.create(recursive: true);
      await entity.copy(dest);
    } else {
      throw StateError(
        'Original fixture must not contain symlinks: ${entity.path}',
      );
    }
  }
  return target;
}

void removeInput(Object? node, String console, String canonical) {
  if (node is Map) {
    final raw = node['inputs'];
    if (raw is List) {
      raw.removeWhere(
        (value) =>
            value is String &&
            DolphinSkins.canonicalInput(console, value) == canonical,
      );
    } else if (raw is Map) {
      raw.removeWhere(
        (key, value) =>
            value is String &&
            DolphinSkins.canonicalInput(console, value) == canonical,
      );
    }
    for (final child in node.values.toList()) {
      removeInput(child, console, canonical);
    }
  } else if (node is List) {
    for (final child in node) {
      removeInput(child, console, canonical);
    }
  }
}

LibretroSkinService serviceAt(Directory root) => LibretroSkinService(
  skinsDirectory: path.join(root.path, 'skins'),
  frontendDirectory: path.join(root.path, 'frontend'),
  cacheDirectory: path.join(root.path, 'cache'),
);
MockClient archiveClient(
  Uint8List bytes, {
  required bool ranges,
  void Function()? onRequest,
}) => MockClient((request) async {
  onRequest?.call();
  final range = request.headers['range'];
  if (!ranges || range == null) return http.Response.bytes(bytes, 200);
  final match = RegExp(r'^bytes=(\d*)-(\d*)$').firstMatch(range)!;
  final first = match.group(1)!;
  final last = match.group(2)!;
  final start = first.isEmpty
      ? (bytes.length - int.parse(last)).clamp(0, bytes.length)
      : int.parse(first);
  final end = first.isEmpty || last.isEmpty
      ? bytes.length - 1
      : int.parse(last).clamp(0, bytes.length - 1);
  return http.Response.bytes(
    bytes.sublist(start, end + 1),
    206,
    headers: {
      'content-range': 'bytes $start-$end/${bytes.length}',
      'content-length': '${end - start + 1}',
    },
  );
});

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  for (final console in ['wii', 'gc', 'ps2']) {
    group('Pocket $console production behavior', () {
      late Directory root;
      late LibretroSkinService service;
      late LibretroInstalledSkin installed;
      late Uint8List zipBytes;
      setUpAll(() async {
        final variable = switch (console) {
          'wii' => 'POCKET_WII_ARCHIVE',
          'ps2' => 'POCKET_PS2_ARCHIVE',
          _ => 'POCKET_GC_ARCHIVE',
        };
        final supplied =
            Platform.environment[variable] ??
            path.join(
              'assets',
              'skins',
              'pocket',
              switch (console) {
                'wii' => 'wii-pocket.manicskin',
                'ps2' => 'ps2-pocket.manicskin',
                _ => 'gamecube-pocket.manicskin',
              },
            );
        if (!File(supplied).existsSync()) {
          throw StateError(
            'Pocket archive missing at $supplied (override with $variable).',
          );
        }
        zipBytes = await File(supplied).readAsBytes();
        root = await Directory.systemTemp.createTemp(
          'rewindbox-pocket-real-$console-',
        );
        service = serviceAt(root);
        final result = await service.importFromFile(
          supplied,
          targetConsole: console,
          source: 'pocket-test-original-archive',
        );
        expect(
          result,
          isA<LibretroSkinImported>(),
          reason: result is LibretroSkinImportFailed
              ? '${result.messageKey}: ${result.technicalDetails}'
              : '$result',
        );
        installed = (result as LibretroSkinImported).skin;
      });
      tearDownAll(() async {
        if (root.existsSync()) await root.delete(recursive: true);
      });

      test(
        'real ZIP importer and directory inspector retain full compatibility',
        () async {
          expect(LibretroSkinService.isZipSignature(zipBytes), isTrue);
          expect(installed.consoles, [console]);
          expect(installed.source, 'pocket-test-original-archive');
          final parsed = await DolphinSkins.inspectDirectory(
            installed.directory,
          );
          expect(parsed, isNotNull);
          expect(parsed!.console, console);
          expect(parsed.compatibility.verdict, LibretroSkinVerdict.compatible);
          expect(parsed.orientations.toSet(), {'portrait', 'landscape'});
          expect(parsed.compatibility.orientations, {
            'portrait': 'compatible',
            'landscape': 'compatible',
          });
          expect(parsed.compatibility.missingControls, isEmpty);
          expect(parsed.compatibility.missingOptionalControls, isEmpty);
          expect(parsed.compatibility.unsupportedInputs, isEmpty);
          expect(parsed.warnings, isEmpty);
          expect(
            (await service.installedSkins(console: console)).single.id,
            installed.id,
          );
          for (final orientation in ['portrait', 'landscape']) {
            expect(installed.supports(orientation), isTrue);
          }
        },
      );

      for (final ranges in [false, true]) {
        test(
          'real remote ZIP reader and classification with HTTP ${ranges ? '206 ranges' : '200 fallback'}',
          () async {
            var requests = 0;
            final client = archiveClient(
              zipBytes,
              ranges: ranges,
              onRequest: () {
                requests++;
              },
            );
            final remote = await LibretroRemoteSkinInspector(
              client: client,
            ).read(Uri.parse('https://pocket.invalid/$console.manicskin'));
            final remoteInfo = Map<String, dynamic>.from(
              jsonDecode(utf8.decode(remote.infoJson)) as Map,
            );
            for (final orientation in ['portrait', 'landscape']) {
              expect(
                remote.entries,
                contains(background(remoteInfo, orientation)),
              );
            }
            expect(
              (jsonDecode(utf8.decode(remote.infoJson)) as Map)['identifier'],
              installed.identifier,
            );
            final provenance = LibretroSkinCatalogService(
              cacheDirectory: service.cacheDirectory,
              skins: service,
              client: client,
            );
            final catalogs = LibretroSkinCatalogs(
              skins: service,
              provenance: provenance,
              client: client,
              overlayIndex: () async => '{"overlays":[]}',
            );
            final archive = LibretroSkinCatalogEntry(
              id: '$console-${ranges ? 'range' : 'whole'}',
              name: installed.name,
              systems: [console],
              downloadURL:
                  'https://pocket.invalid/$console.manicskin?range=$ranges',
            );
            final entry = LibretroSkinCatalogs.fromProvenance(archive);
            final verdict = await catalogs.classify(entry, console);
            expect(verdict.verdict, LibretroSkinVerdict.compatible);
            expect(verdict.orientations.keys.toSet(), {
              'portrait',
              'landscape',
            });
            expect(requests, greaterThan(0));
            final wrong = console == 'wii' ? 'gc' : 'wii';
            final falselyListed = LibretroCatalogSkin(
              key: 'wrong-$console-$ranges',
              source: entry.source,
              name: entry.name,
              consoles: [wrong],
              archive: archive,
            );
            final wrongVerdict = await catalogs.classify(falselyListed, wrong);
            expect(wrongVerdict.verdict, LibretroSkinVerdict.incompatible);
            expect(
              wrongVerdict.reasons,
              contains(LibretroSkinCompatibility.otherConsole),
            );
            catalogs.dispose();
            provenance.dispose();
            client.close();
          },
        );
      }

      for (final orientation in ['portrait', 'landscape']) {
        test(
          'installed manager $orientation preview is declared complete art',
          () async {
            final info = readInfo(installed.directory);
            final declared =
                (info['previewImages'] as Map)[orientation] as String;
            final expected = await File(
              path.join(installed.directory, declared),
            ).readAsBytes();
            final body = await File(
              path.join(installed.directory, background(info, orientation)),
            ).readAsBytes();
            expect(
              expected,
              isNot(orderedEquals(body)),
              reason: 'Housing without controls cannot be manager preview.',
            );
            expect(
              await DolphinSkins.previewImage(installed.directory, orientation),
              orderedEquals(expected),
            );
            expect(
              await service.preview(
                skin: installed,
                console: console,
                orientation: orientation,
                width: orientation == 'portrait' ? 393 : 852,
                height: orientation == 'portrait' ? 852 : 393,
              ),
              orderedEquals(expected),
            );
          },
        );
      }

      test('all normal and pressed control assets exist and differ', () async {
        final info = readInfo(installed.directory);
        var pairs = 0;
        for (final orientation in ['portrait', 'landscape']) {
          final layout = DolphinSkins.layoutFor(info, orientation)!.$1;
          for (final item in layout['items'] as List) {
            final asset = (item as Map)['asset'];
            if (asset is! Map || asset['normal'] == null) continue;
            expect(
              asset['pressed'],
              isA<String>(),
              reason: '$orientation ${item['inputs']}',
            );
            final normal = await File(
              path.join(installed.directory, asset['normal'] as String),
            ).readAsBytes();
            final pressed = await File(
              path.join(installed.directory, asset['pressed'] as String),
            ).readAsBytes();
            expect(pressed, isNot(orderedEquals(normal)));
            pairs++;
          }
        }
        expect(pairs, greaterThan(8));
      });

      for (final mode in [
        'missing',
        'invalid-image',
        'parent-traversal',
        'absolute',
        'backslash',
        'symlink-outside',
        'legacy',
      ]) {
        test('preview $mode safely falls back to layout background', () async {
          final temporary = await Directory.systemTemp.createTemp(
            'rewindbox-preview-$console-',
          );
          try {
            final fixture = await copyFixture(installed.directory, temporary);
            final info = readInfo(fixture.path);
            final declared = Map<String, dynamic>.from(
              info['previewImages'] as Map,
            );
            final outside = File(path.join(temporary.path, 'outside.png'));
            await outside.writeAsBytes(
              await File(
                path.join(fixture.path, declared['portrait'] as String),
              ).readAsBytes(),
            );
            switch (mode) {
              case 'missing':
                declared['portrait'] = 'previews/does-not-exist.png';
                break;
              case 'invalid-image':
                final invalid = File(
                  path.join(fixture.path, 'previews/invalid.png'),
                );
                await invalid.parent.create(recursive: true);
                await invalid.writeAsString('not a bitmap');
                declared['portrait'] = 'previews/invalid.png';
                break;
              case 'parent-traversal':
                declared['portrait'] = '../outside.png';
                break;
              case 'absolute':
                declared['portrait'] = outside.path;
                break;
              case 'backslash':
                declared['portrait'] = r'..\outside.png';
                break;
              case 'symlink-outside':
                final link = Link(
                  path.join(fixture.path, 'previews/outside.png'),
                );
                await link.parent.create(recursive: true);
                await link.create(outside.path);
                declared['portrait'] = 'previews/outside.png';
                break;
              case 'legacy':
                info.remove('previewImages');
                break;
            }
            if (mode != 'legacy') info['previewImages'] = declared;
            await saveInfo(fixture.path, info);
            final expected = await File(
              path.join(fixture.path, background(info, 'portrait')),
            ).readAsBytes();
            expect(
              await DolphinSkins.previewImage(fixture.path, 'portrait'),
              orderedEquals(expected),
            );
          } finally {
            await temporary.delete(recursive: true);
          }
        });
      }

      test(
        'missing A in every device/display/orientation is refused by actual parser',
        () async {
          final temporary = await Directory.systemTemp.createTemp(
            'rewindbox-missing-a-$console-',
          );
          try {
            final fixture = await copyFixture(installed.directory, temporary);
            final info = readInfo(fixture.path);
            // A control every console needs: the A button, or Cross on a PS2.
            final essential = console == 'ps2' ? 'cross' : 'a';
            removeInput(info['representations'], console, essential);
            await saveInfo(fixture.path, info);
            final parsed = await DolphinSkins.inspectDirectory(fixture.path);
            expect(parsed, isNotNull);
            expect(
              parsed!.compatibility.verdict,
              LibretroSkinVerdict.incompatible,
            );
            expect(parsed.compatibility.missingControls, contains(essential));
            expect(parsed.orientations, isEmpty);
            expect(parsed.compatibility.orientations, {
              'portrait': 'incompatible',
              'landscape': 'incompatible',
            });
          } finally {
            await temporary.delete(recursive: true);
          }
        },
      );

      test(
        'alien gameType is rejected, then unsafe/corrupt ZIPs are refused by importer',
        () async {
          final temporary = await Directory.systemTemp.createTemp(
            'rewindbox-refusals-$console-',
          );
          try {
            final fixture = await copyFixture(installed.directory, temporary);
            final info = readInfo(fixture.path)
              ..['gameTypeIdentifier'] = 'public.aoshuang.game.psp';
            await saveInfo(fixture.path, info);
            expect(await DolphinSkins.inspectDirectory(fixture.path), isNull);
            final corrupt = File(
              path.join(temporary.path, 'corrupt.manicskin'),
            );
            await corrupt.writeAsBytes([1, 2, 3, 4]);
            final bad = await service.importFromFile(
              corrupt.path,
              targetConsole: console,
            );
            expect(bad, isA<LibretroSkinImportFailed>());
            expect(
              (bad as LibretroSkinImportFailed).messageKey,
              LibretroSkinMessages.notArchive,
            );
            final unsafe = Archive()
              ..addFile(
                ArchiveFile.string('../escape.txt', 'must never escape'),
              );
            final unsafeFile = File(
              path.join(temporary.path, 'unsafe.manicskin'),
            );
            await unsafeFile.writeAsBytes(ZipEncoder().encode(unsafe));
            final refused = await service.importFromFile(
              unsafeFile.path,
              targetConsole: console,
            );
            expect(refused, isA<LibretroSkinImportFailed>());
            expect(
              (refused as LibretroSkinImportFailed).messageKey,
              LibretroSkinMessages.unsafe,
            );
            expect(
              File(
                path.join(
                  service.skinsDirectory,
                  LibretroSkinService.stagingFolderName,
                  'escape.txt',
                ),
              ).existsSync(),
              isFalse,
            );
          } finally {
            await temporary.delete(recursive: true);
          }
        },
      );
    });
  }

  test(
    'production canonicalizer maps published GC/Wii controls and rejects unsupported raw names',
    () {
      const cases = <String, Map<String, String>>{
        'gc': {
          'l2': 'l',
          'r2': 'r',
          'r1': 'z',
          'plus': 'start',
          'leftThumbstickUp': 'stickUp',
          'rightThumbstickRight': 'cRight',
        },
        'wii': {
          'one': 'one',
          'two': 'two',
          'home': 'home',
          'l1': 'c',
          'r1': 'z',
          'x': 'one',
          'y': 'two',
          'start': 'plus',
          'select': 'minus',
        },
        'ps2': {
          'cross': 'cross',
          'circle': 'circle',
          'square': 'square',
          'triangle': 'triangle',
          'l1': 'l1',
          'l2': 'l2',
          'r1': 'r1',
          'r2': 'r2',
          'select': 'select',
          'start': 'start',
          'l3': 'l3',
          'r3': 'r3',
          'up': 'up',
          'dpadLeft': 'left',
          'leftThumbstickUp': 'stickUp',
          'rightThumbstickDown': 'rstickDown',
          'rightStickRight': 'rstickRight',
          'menu': 'menu',
          'pause': 'menu',
        },
      };
      for (final console in cases.entries) {
        for (final mapping in console.value.entries) {
          expect(
            DolphinSkins.canonicalInput(console.key, mapping.key),
            mapping.value,
            reason: '${console.key}:${mapping.key}',
          );
        }
      }
      expect(DolphinSkins.canonicalInput('wii', 'shake'), isNull);
      expect(DolphinSkins.canonicalInput('gc', 'triangle'), isNull);
      // PlayStation names only: nothing Nintendo is guessed on a PS2 skin.
      for (final raw in ['a', 'b', 'x', 'y', 'z', 'home', 'plus', 'c', 'l', 'quickSave']) {
        expect(DolphinSkins.canonicalInput('ps2', raw), isNull, reason: raw);
      }
      for (final alias in ['ps2', 'playstation2', 'armsx2', 'pcsx2']) {
        expect(DolphinSkins.consoleOfGameType('public.test.game.$alias'), 'ps2');
      }
      expect(DolphinSkins.consoleOfGameType('public.aoshuang.game.ps1'), isNull);
      for (final alias in ['ngc', 'gc', 'gamecube', 'dol', 'dolphin']) {
        expect(DolphinSkins.consoleOfGameType('public.test.game.$alias'), 'gc');
      }
      for (final alias in ['wii', 'rvl', 'revolution']) {
        expect(
          DolphinSkins.consoleOfGameType('public.test.game.$alias'),
          'wii',
        );
      }
      expect(DolphinSkins.consoleOfGameType('public.test.game.psp'), isNull);
    },
  );
}
