import 'dart:convert';
import 'dart:io';
import 'dart:math';
import 'dart:typed_data';

import 'package:archive/archive.dart' show Archive, ArchiveFile, ZipEncoder;
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/services/libretro_overlay_converter.dart';
import 'package:neostation/services/libretro_skin_catalog_service.dart';
import 'package:neostation/services/libretro_skin_catalogs.dart';
import 'package:neostation/services/libretro_skin_compatibility.dart';
import 'package:neostation/services/libretro_skin_remote_inspector.dart';
import 'package:neostation/services/libretro_skin_service.dart';
import 'package:path/path.dart' as path;

const _bridge = MethodChannel('neostation/libretro_internal');

/// A GBA overlay with every construct the converter handles: a portrait
/// page, a landscape page, and a pause page reached by overlay_next.
const _gbaOverlay = '''
overlays = 3
overlay0_name = "portrait"
overlay0_full_screen = true
overlay0_normalized = true
overlay0_aspect_ratio = 0.5
overlay0_overlay = "img/bg.png"
overlay0_descs = 9
overlay0_desc0 = "dpad_area,0.2,0.8,rect,0.1,0.05"
overlay0_desc0_overlay = "img/dpad.png"
overlay0_desc0_reach_x = 1.5
overlay0_desc1 = "a,0.85,0.78,radial,0.05,0.025"
overlay0_desc1_overlay = img/a.png # comment
overlay0_desc2 = "a|b,0.8,0.8,radial,0.04,0.02"
overlay0_desc3 = "b,0.75,0.82,radial,0.05,0.025"
overlay0_desc3_reach_y = 0
overlay0_desc3_overlay = "img/b.png"
overlay0_desc4 = "l,0.1,0.6,rect,0.08,0.02"
overlay0_desc5 = "menu_toggle,0.5,0.95,rect,0.05,0.02"
overlay0_desc6 = "overlay_next,0.6,0.95,rect,0.05,0.02"
overlay0_desc6_next_target = "pause"
overlay0_desc7 = "overlay_next,0.4,0.95,rect,0.05,0.02"
overlay0_desc7_next_target = "landscape"
overlay0_desc8 = "rewind,0.3,0.95,rect,0.05,0.02"
overlay1_name = "landscape"
overlay1_full_screen = true
overlay1_normalized = true
overlay1_aspect_ratio = 2.0
overlay1_descs = 2
overlay1_desc0 = "start,0.5,0.9,rect,0.05,0.04"
overlay1_desc1 = "hold_fast_forward,0.6,0.9,rect,0.05,0.04"
overlay2_name = "pause"
overlay2_full_screen = true
overlay2_normalized = true
overlay2_descs = 1
overlay2_desc0 = "save_state,0.5,0.5,rect,0.1,0.1"
''';

Map<String, Object?> _layout(LibretroOverlayConversion conversion, String orientation, {String device = 'iphone'}) {
  final representations = conversion.info['representations']! as Map<String, Object?>;
  final displays = representations[device]! as Map<String, Object?>;
  final layouts = displays[device == 'ipad' ? 'standard' : 'edgeToEdge']! as Map<String, Object?>;
  return layouts[orientation]! as Map<String, Object?>;
}

List<Map<String, Object?>> _items(Map<String, Object?> layout) =>
    (layout['items']! as List).cast<Map<String, Object?>>();

Map<String, Object?> _itemWith(Map<String, Object?> layout, Object inputs) =>
    _items(layout).singleWhere((item) => jsonEncode(item['inputs']) == jsonEncode(inputs));

/// A Delta skin archive: info.json first, then [files].
List<int> _skinZip(Map<String, Object?> info, {Map<String, List<int>> files = const {}, String folder = ''}) {
  final archive = Archive()..add(ArchiveFile.bytes('${folder}info.json', utf8.encode(jsonEncode(info))));
  files.forEach((name, bytes) => archive.add(ArchiveFile.bytes('$folder$name', bytes)));
  return ZipEncoder().encodeBytes(archive);
}

Map<String, Object?> _info(String name, String gameType) => <String, Object?>{
      'name': name,
      'identifier': 'com.example.${name.toLowerCase().replaceAll(' ', '')}',
      'gameTypeIdentifier': gameType,
      'representations': <String, Object?>{},
    };

/// Incompressible bytes, so the end of an archive holds no info.json data.
List<int> _noise(int length) {
  final random = Random(7);
  return List<int>.generate(length, (_) => random.nextInt(256));
}

/// A host serving [files] with HTTP range support (suffix and closed
/// ranges, 206 + Content-Range), or ignoring ranges ([ranges] false).
class _Host {
  _Host(this.files, {this.ranges = true});

  final Map<String, List<int>> files;
  final bool ranges;
  final requests = <http.Request>[];
  var transferred = 0;
  var online = true;

  late final MockClient client = MockClient((request) async {
    if (!online) return http.Response('offline', 503);
    requests.add(request);
    final bytes = files[request.url.path];
    if (bytes == null) return http.Response('missing', 404);
    final range = request.headers['Range'];
    if (!ranges || range == null) {
      transferred += bytes.length;
      return http.Response.bytes(bytes, 200);
    }
    int start, end;
    final suffix = RegExp(r'^bytes=-(\d+)$').firstMatch(range);
    if (suffix != null) {
      start = max(0, bytes.length - int.parse(suffix.group(1)!));
      end = bytes.length - 1;
    } else {
      final closed = RegExp(r'^bytes=(\d+)-(\d+)$').firstMatch(range)!;
      start = int.parse(closed.group(1)!);
      end = min(bytes.length - 1, int.parse(closed.group(2)!));
    }
    transferred += end - start + 1;
    return http.Response.bytes(
      bytes.sublist(start, end + 1),
      206,
      headers: <String, String>{'content-range': 'bytes $start-$end/${bytes.length}'},
    );
  });
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('RetroArch overlay conversion', () {
    LibretroOverlayConversion convert(String cfg, String console, {String device = 'iphone'}) =>
        LibretroOverlayConverter.convert(
          cfg,
          cfgPath: 'gamepads/gba/test.cfg',
          console: console,
          name: 'Test',
          identifier: 'org.neostation.overlay.test.$console',
          device: device,
        );

    test('pages, D-pad, buttons, combos, decoration, commands and the game area', () {
      final conversion = convert(_gbaOverlay, 'gba');
      expect(conversion.problems, isEmpty);
      expect(conversion.converted, isTrue);
      expect(conversion.orientations, <String>['portrait', 'landscape']);
      expect(conversion.info['gameTypeIdentifier'], 'com.rileytestut.delta.game.gba');
      expect(conversion.droppedCommands, <String>['rewind']);

      final portrait = _layout(conversion, 'portrait');
      expect(portrait['mappingSize'], <String, Object?>{'width': 1000.0, 'height': 2000.0});
      expect(portrait['translucent'], isTrue);
      final dpad = _itemWith(portrait, <String, Object?>{'up': 'up', 'down': 'down', 'left': 'left', 'right': 'right'});
      expect(dpad['frame'], <String, Object?>{'x': 100.0, 'y': 1500.0, 'width': 200.0, 'height': 200.0});
      // reach_x 1.5 widens the touch area by half the half-width on each side.
      expect(dpad['extendedEdges'], <String, Object?>{'top': 0.0, 'bottom': 0.0, 'left': 50.0, 'right': 50.0});
      expect(_itemWith(portrait, <String>['a'])['asset'], isNotNull);
      _itemWith(portrait, <String>['a', 'b']);
      _itemWith(portrait, <String>['l']);
      // menu_toggle and overlay_next to the pause page both open the menu.
      expect(_items(portrait).where((item) => jsonEncode(item['inputs']) == '["menu"]').length, 2);
      // A zero reach is never pressed in RetroArch: drawn only.
      final decoration = _itemWith(portrait, <String>[]);
      expect(decoration['asset'], isNotNull);
      // The orientation switch is dropped (NeoStation rotates by itself).
      expect(_items(portrait).length, 7);
      // The game takes the room above the topmost control (L at 0.58).
      final screens = (portrait['screens']! as List).cast<Map<String, Object?>>();
      expect(screens.single['outputFrame'], <String, Object?>{'x': 0.0, 'y': 0.0, 'width': 1000.0, 'height': 1140.0});

      final landscape = _layout(conversion, 'landscape');
      expect(landscape['mappingSize'], <String, Object?>{'width': 1000.0, 'height': 500.0});
      expect(landscape.containsKey('screens'), isFalse);
      _itemWith(landscape, <String>['start']);
      _itemWith(landscape, <String>['fastForward']);

      // Images resolved next to the .cfg, each listed once.
      expect(
        conversion.files.values.toSet(),
        <String>{'gamepads/gba/img/bg.png', 'gamepads/gba/img/dpad.png', 'gamepads/gba/img/a.png', 'gamepads/gba/img/b.png'},
      );
      expect(conversion.files.keys.every((name) => name.startsWith('images/')), isTrue);
    });

    test('page rectangles move every image and touch area together', () {
      final result = LibretroOverlayConverter.convert(
        '$_gbaOverlay\noverlay1_rect = 0.1,0.2,0.8,0.6\noverlay1_overlay = img/bg.png',
        cfgPath: 'gba/layout.cfg', console: 'gba', name: 'Composite', identifier: 'test.rect');
      expect(result.converted, isTrue);
      final landscape = _layout(result, 'landscape');
      final start = _itemWith(landscape, <String>['start']);
      expect(start['frame'], {'x': 460.0, 'y': 358.0, 'width': 80.0, 'height': 24.0});
      expect(_items(landscape).first['frame'], {'x': 100.0, 'y': 100.0, 'width': 800.0, 'height': 300.0});
      expect(landscape['assets'], isNull);
    });

    test('untrusted counts and nonfinite geometry fail before allocation', () {
      for (final extra in <String>[
        'overlays = 2147483647', 'overlay0_descs = 9999999',
        'overlay0_aspect_ratio = NaN', 'overlay0_aspect_ratio = 0',
        'overlay0_desc0 = "a,NaN,0.8,rect,0.1,0.1"',
        'overlay0_desc0_reach_x = Infinity', 'overlay0_rect = 0,0,-1,1',
        'overlay0_desc0_normalized = false', 'overlay0_desc0_overlay = ../../secret.png',
      ]) {
        final result = LibretroOverlayConverter.convert('$_gbaOverlay\n$extra',
          cfgPath: 'gba/skin.cfg', console: 'gba', name: 'Invalid', identifier: 'test.invalid');
        expect(result.converted, isFalse, reason: extra);
        expect(result.problems, isNotEmpty, reason: extra);
      }
    });

    test('RetroPad names become the console buttons they press', () {
      const cfg = '''
overlays = 1
overlay0_name = "landscape"
overlay0_full_screen = true
overlay0_normalized = true
overlay0_descs = 4
overlay0_desc0 = "a,0.9,0.5,radial,0.05,0.05"
overlay0_desc1 = "b,0.8,0.5,radial,0.05,0.05"
overlay0_desc2 = "y,0.7,0.5,radial,0.05,0.05"
overlay0_desc3 = "abxy_area,0.5,0.5,rect,0.1,0.1"
overlay0_desc3_up = "l"
''';
      // Genesis: RetroPad A is C, B is B, Y is A (LibretroInputMap).
      final genesis = _layout(convert(cfg, 'md'), 'landscape');
      expect(_items(genesis).map((item) => item['inputs']).take(3).toList(), <Object?>[
        <String>['c'],
        <String>['b'],
        <String>['a'],
      ]);
      // abxy_area: up / down / left / right press X / B / Y / A, with
      // their redefinitions.
      final snes = _layout(convert(cfg, 'snes'), 'landscape');
      expect(_items(snes).last['inputs'], <String, Object?>{'up': 'l', 'down': 'b', 'left': 'y', 'right': 'a'});
      // A single unnamed page without aspect ratio: landscape, 19.5:9.
      expect(snes['mappingSize'], <String, Object?>{'width': 1000.0, 'height': 461.54});
    });

    test('pages meant for no orientation: the first one, in the orientation its path names', () {
      const pages = '''
overlays = 3
overlay0_name = "GameBoy"
overlay0_full_screen = true
overlay0_normalized = true
overlay0_descs = 1
overlay0_desc0 = "a,0.8,0.8,radial,0.05,0.05"
overlay1_name = "GameBoyColor"
overlay1_full_screen = true
overlay1_normalized = true
overlay1_descs = 1
overlay1_desc0 = "b,0.8,0.8,radial,0.05,0.05"
overlay2_name = "hidden"
overlay2_full_screen = true
overlay2_normalized = true
overlay2_descs = 0
''';
      LibretroOverlayConversion at(String cfgPath) => LibretroOverlayConverter.convert(pages,
          cfgPath: cfgPath, console: 'gb', name: 'GB', identifier: 'org.neostation.overlay.gb');
      final portrait = at('gamepads/gb_anim_portrait/gb_big.cfg');
      expect(portrait.orientations, <String>['portrait']);
      expect(_items(_layout(portrait, 'portrait')).single['inputs'], <String>['a']);
      final landscape = at('gamepads/arcade-anim/gb.cfg');
      expect(landscape.orientations, <String>['landscape']);
      expect(_items(_layout(landscape, 'landscape')).single['inputs'], <String>['a']);

      // Pixel coordinates depend on the images' sizes: refused with the reason.
      final pixels = LibretroOverlayConverter.convert(pages.replaceAll('_normalized = true', '_normalized = false'),
          cfgPath: 'gamepads/old/gb.cfg', console: 'gb', name: 'GB', identifier: 'org.neostation.overlay.gb');
      expect(pixels.converted, isFalse);
      expect(pixels.problems.single, contains('normalized'));
    });

    test('sticks, Nintendo 64 C buttons, the DS screens and iPad layouts', () {
      const sticks = '''
overlays = 1
overlay0_full_screen = true
overlay0_normalized = true
overlay0_descs = 3
overlay0_desc0 = "analog_left,0.2,0.7,radial,0.1,0.1"
overlay0_desc0_overlay = "stick.png"
overlay0_desc1 = "r_x_minus,0.8,0.7,radial,0.05,0.05"
overlay0_desc2 = "l_y_minus,0.5,0.7,radial,0.05,0.05"
''';
      final n64 = _layout(convert(sticks, 'n64'), 'landscape');
      final stick = _items(n64).first;
      expect(stick['inputs'], <String, Object?>{
        'up': 'leftStickUp',
        'down': 'leftStickDown',
        'left': 'leftStickLeft',
        'right': 'leftStickRight',
      });
      expect((stick['thumbstick']! as Map)['name'], startsWith('images/'));
      expect(_items(n64)[1]['inputs'], <String>['cLeft']);
      expect(_items(n64)[2]['inputs'], <String>['leftStickUp']);

      final ds = _layout(convert(sticks, 'nds'), 'landscape');
      final screens = (ds['screens']! as List).cast<Map<String, Object?>>();
      expect(screens.length, 2);
      expect(screens.last['inputFrame'], <String, Object?>{'x': 0, 'y': 192, 'width': 256, 'height': 192});
      expect(_items(ds).last, <String, Object?>{
        'inputs': <String, Object?>{'x': 'touchScreenX', 'y': 'touchScreenY'},
        'frame': screens.last['outputFrame'],
      });

      // An overlay drawn for iPads becomes an iPad layout (4:3 by default).
      final tablet = convert(sticks, 'n64', device: 'ipad');
      expect((tablet.info['representations']! as Map).keys, <String>['ipad']);
      expect(_layout(tablet, 'landscape', device: 'ipad')['mappingSize'], <String, Object?>{'width': 1000.0, 'height': 750.0});
    });

    test('overlays NeoStation cannot reproduce faithfully are refused with their reason', () {
      const notFullScreen = '''
overlays = 1
overlay0_name = "landscape"
overlay0_normalized = true
overlay0_descs = 1
overlay0_desc0 = "a,0.5,0.5,radial,0.1,0.1"
''';
      final windowed = convert(notFullScreen, 'gba');
      expect(windowed.converted, isFalse);
      expect(windowed.problems.single, contains('full_screen'));

      const crowded = '''
overlays = 1
overlay0_name = "portrait"
overlay0_full_screen = true
overlay0_normalized = true
overlay0_descs = 1
overlay0_desc0 = "a,0.5,0.15,radial,0.1,0.1"
''';
      expect(convert(crowded, 'gba').problems.single, contains('no room for the game'));
      expect(convert('#include "other.cfg"\n$_gbaOverlay', 'gba').problems, contains('#include is not supported'));
      expect(convert(_gbaOverlay, '3ds').converted, isFalse);
      expect(convert('overlays = 0\n', 'gba').problems, <String>['no portrait or landscape page']);
    });
  });

  group('remote skin inspection', () {
    final info = _info('Remote GBA', 'com.rileytestut.delta.game.gba');
    final archive = _skinZip(info, files: <String, List<int>>{
      'images/a.png': _noise(64),
      'images/big.pdf': _noise(200 * 1024),
    });

    test('reads info.json and the file list with a few kilobytes of range requests', () async {
      final host = _Host(<String, List<int>>{'/skin.deltaskin': archive});
      final read = await LibretroRemoteSkinInspector(client: host.client, tailBytes: 4096)
          .read(Uri.https('example.com', '/skin.deltaskin'));
      expect(jsonDecode(utf8.decode(read.infoJson)), info);
      expect(read.entries, <String>['images/a.png', 'images/big.pdf']);
      expect(host.requests.every((request) => request.headers['Range'] != null), isTrue);
      expect(host.transferred, lessThan(archive.length ~/ 10));
    });

    test('a host ignoring ranges sends the whole archive, read the same way', () async {
      final host = _Host(<String, List<int>>{'/skin.deltaskin': archive}, ranges: false);
      final read = await LibretroRemoteSkinInspector(client: host.client).read(Uri.https('example.com', '/skin.deltaskin'));
      expect(jsonDecode(utf8.decode(read.infoJson)), info);
      expect(host.requests.length, 1);
    });

    test('a ZIP wrapping one skin, and a skin inside a single folder', () async {
      final wrapped = ZipEncoder().encodeBytes(Archive()..add(ArchiveFile.bytes('Remote GBA.deltaskin', archive)));
      final folder = _skinZip(info, files: <String, List<int>>{'a.png': _noise(16)}, folder: 'Remote GBA/');
      final host = _Host(<String, List<int>>{'/wrapped.zip': wrapped, '/folder.zip': folder});
      final inspector = LibretroRemoteSkinInspector(client: host.client, tailBytes: 1024);
      final inner = await inspector.read(Uri.https('example.com', '/wrapped.zip'));
      expect(jsonDecode(utf8.decode(inner.infoJson)), info);
      expect(inner.entries, <String>['images/a.png', 'images/big.pdf']);
      final nested = await inspector.read(Uri.https('example.com', '/folder.zip'));
      expect(nested.entries, <String>['a.png']);
    });

    test('an unreachable host is a network failure, a file that is not a skin is not', () async {
      final host = _Host(<String, List<int>>{
        '/page.deltaskin': utf8.encode('<html>store page</html>'),
        '/empty.zip': ZipEncoder().encodeBytes(Archive()..add(ArchiveFile.bytes('readme.txt', utf8.encode('hi')))),
      });
      final inspector = LibretroRemoteSkinInspector(client: host.client);
      Future<LibretroRemoteSkinInspectionException> failure(String file) async {
        try {
          await inspector.read(Uri.https('example.com', file));
        } on LibretroRemoteSkinInspectionException catch (error) {
          return error;
        }
        fail('$file was read');
      }

      expect((await failure('/missing.deltaskin')).network, isTrue);
      expect((await failure('/page.deltaskin')).network, isFalse);
      expect((await failure('/empty.zip')).message, 'no info.json');
    });

    test('the inspection folder holds info.json and image signatures only', () async {
      final directory = Directory.systemTemp.createTempSync('libretro_skin_inspection');
      addTearDown(() => directory.deleteSync(recursive: true));
      await LibretroRemoteSkinInspector.materialize(
        LibretroRemoteSkinArchive(
          infoJson: utf8.encode('{}'),
          entries: const <String>['images/a.png', 'b.JPG', 'c.pdf', 'notes.txt', '../evil.png', '__MACOSX/x.png'],
        ),
        directory,
      );
      final written = directory
          .listSync(recursive: true)
          .whereType<File>()
          .map((file) => path.relative(file.path, from: directory.path))
          .toSet();
      expect(written, <String>{'info.json', path.join('images', 'a.png'), 'b.JPG', 'c.pdf'});
      expect(File(path.join(directory.path, 'images', 'a.png')).readAsBytesSync().take(4), <int>[0x89, 0x50, 0x4E, 0x47]);
      expect(File(path.join(directory.path, 'b.JPG')).readAsBytesSync().take(3), <int>[0xFF, 0xD8, 0xFF]);
      expect(utf8.decode(File(path.join(directory.path, 'c.pdf')).readAsBytesSync()), startsWith('%PDF-'));
    });
  });

  group('unified catalogs', () {
    late Directory root;
    late LibretroSkinService skins;
    final inspected = <String>[];
    final nativeCalls = <MethodCall>[];

    /// The native filter as LibretroSkinCompatibility answers: a report for
    /// the console the skin declares, compatible unless its name says
    /// otherwise.
    Map<String, Object?> nativeInspect(String directory) {
      inspected.add(directory);
      final info = jsonDecode(File(path.join(directory, 'info.json')).readAsStringSync()) as Map;
      final type = info['gameTypeIdentifier'] as String;
      final console = type.split('.').last == 'ds' ? 'nds' : type.split('.').last;
      final refused = '${info['name']}'.contains('Desktop');
      return <String, Object?>{
        'ok': true,
        'device': 'iphone',
        'summary': <String, Object?>{
          'identifier': info['identifier'],
          'name': info['name'],
          'consoles': <String>[console],
          'gameTypeIdentifier': type,
          'orientations': <String, Object?>{'iphone': <String>['portrait', 'landscape']},
          'warnings': <String>[],
          'compatibility': <String, Object?>{
            console: <String, Object?>{
              'status': refused ? 'incompatible' : 'compatible',
              'console': console,
              'orientations': <String, Object?>{
                'portrait': refused ? 'incompatible' : 'compatible',
                'landscape': refused ? 'incompatible' : 'compatible',
              },
              'reasons': refused ? <String>['SKIN_COMPAT_NO_TOUCH_CONTROLS'] : <String>[],
            },
          },
        },
      };
    }

    setUp(() {
      root = Directory.systemTemp.createTempSync('libretro_skin_catalogs_test');
      skins = LibretroSkinService(
        skinsDirectory: path.join(root.path, 'Skins'),
        frontendDirectory: path.join(root.path, 'Frontend'),
        cacheDirectory: path.join(root.path, 'Cache'),
      );
      inspected.clear();
      nativeCalls.clear();
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_bridge, (call) async {
        nativeCalls.add(call);
        if (call.method == 'inspectSkin') return nativeInspect((call.arguments as Map)['directory'] as String);
        return null;
      });
    });

    tearDown(() {
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(_bridge, null);
      root.deleteSync(recursive: true);
    });

    LibretroSkinCatalogs catalogs(
      http.Client client, {
      String overlayIndex = '{"version": 1, "sources": {}, "entries": []}',
      DateTime Function()? clock,
    }) =>
        LibretroSkinCatalogs(
          skins: skins,
          provenance: LibretroSkinCatalogService(cacheDirectory: skins.cacheDirectory, skins: skins, client: client),
          client: client,
          overlayIndex: () async => overlayIndex,
          clock: clock,
        );

    test('Provenance entries are attributed to the site they list', () {
      LibretroCatalogSkin from(String? source) => LibretroSkinCatalogs.fromProvenance(LibretroSkinCatalogEntry(
            id: 'x',
            name: 'X',
            systems: const <String>['gba'],
            downloadURL: 'https://example.com/x.deltaskin',
            source: source,
          ));
      expect(from('DeltaStyles.com').source, LibretroSkinSources.deltaStyles);
      expect(from('DeltaStyles.com').belongsToSource(LibretroSkinSources.provenance), isTrue);
      expect(from('DeltaStyles.com').belongsToSource(LibretroSkinSources.deltaStyles), isTrue);
      expect(from('https://delta-skins.github.io').source, LibretroSkinSources.deltaSkins);
      final provenance = from('LitRitt/emuskins');
      expect(provenance.source, LibretroSkinSources.provenance);
      expect(provenance.origin, 'LitRitt/emuskins');
      expect(provenance.excludedReason, isNull);
      final page = LibretroSkinCatalogs.fromProvenance(const LibretroSkinCatalogEntry(
        id: 'y',
        name: 'Y',
        systems: <String>['gba'],
        downloadURL: 'https://example.com/store-page',
      ));
      expect(page.excludedReason, LibretroSkinCompatibility.notDirect);
    });

    test('a download link is the same whatever its spelling', () {
      final raw = LibretroSkinCatalogs.normalizeDownloadURL('https://raw.githubusercontent.com/o/r/main/My%20Skin.deltaskin');
      expect(LibretroSkinCatalogs.normalizeDownloadURL('https://GitHub.com/o/r/raw/main/My Skin.deltaskin'), raw);
      expect(LibretroSkinCatalogs.normalizeDownloadURL('https://www.github.com/o/r/blob/main/My%20Skin.deltaskin'), raw);
      expect(
        LibretroSkinCatalogs.normalizeDownloadURL('https://drive.google.com/uc?export=download&id=1'),
        isNot(LibretroSkinCatalogs.normalizeDownloadURL('https://drive.google.com/uc?export=download&id=2')),
      );
    });

    test('links with non-ASCII characters or a literal percent sign never throw', () {
      // Two links published in Provenance's catalog (October 2026) whose
      // second decoding threw and made every catalog fail to load.
      const pinball = 'https://deltastyles.com/files/skins/pokÃ©mon pinball GBA.deltaskin';
      const donkeyKong = 'https://deltastyles.com/files/skins/652/DK control + real dpad Â (1981) v.05.zip';
      expect(LibretroSkinCatalogs.normalizeDownloadURL(pinball), 'deltastyles.com/files/skins/pokÃ©mon pinball GBA.deltaskin');
      expect(
        LibretroSkinCatalogs.normalizeDownloadURL(
            'https://DeltaStyles.com/files/skins/pok%C3%83%C2%A9mon%20pinball%20GBA.deltaskin'),
        LibretroSkinCatalogs.normalizeDownloadURL(pinball),
      );
      expect(LibretroSkinCatalogs.normalizeDownloadURL(donkeyKong),
          'deltastyles.com/files/skins/652/DK control + real dpad Â (1981) v.05.zip');
      expect(LibretroSkinCatalogs.normalizeDownloadURL('https://example.com/skins/100%25%20Orange.deltaskin'),
          'example.com/skins/100% Orange.deltaskin');
      // Dart's parser re-encodes a stray '%' itself: same key, no exception.
      expect(LibretroSkinCatalogs.normalizeDownloadURL('https://example.com/bad%zz.deltaskin'),
          'example.com/bad%zz.deltaskin');
      final entry = LibretroSkinCatalogs.fromProvenance(const LibretroSkinCatalogEntry(
        id: 'pinball',
        name: 'Pokémon Pinball',
        systems: <String>['gba'],
        downloadURL: pinball,
        source: 'DeltaStyles.com',
      ));
      expect(entry.excludedReason, isNull);
      expect(entry.archive!.downloadUri!.path, '/files/skins/pok%C3%83%C2%A9mon%20pinball%20GBA.deltaskin');
    });

    test('one unusable catalog entry never takes the other entries and sources down', () async {
      // The two real links above, a regular entry and a site card with a
      // non-ASCII link: every catalog still loads, for every console.
      const provenanceCatalog = '''
{"skins": [
  {"id": "1", "name": "Regular", "author": "A", "systems": ["gba"], "downloadCount": 9,
   "downloadURL": "https://github.com/o/r/raw/main/Regular.deltaskin"},
  {"id": "2", "name": "Pokémon Pinball", "author": "B", "systems": ["gba"], "downloadCount": 4,
   "downloadURL": "https://deltastyles.com/files/skins/pokÃ©mon pinball GBA.deltaskin", "source": "DeltaStyles.com"},
  {"id": "3", "name": "DK control", "author": "C", "systems": ["nes"], "downloadCount": 2,
   "downloadURL": "https://deltastyles.com/files/skins/652/DK control + real dpad Â (1981) v.05.zip", "source": "DeltaStyles.com"},
  {"id": "4", "name": "PlayStation", "author": "D", "systems": ["psx"], "downloadCount": 1,
   "downloadURL": "https://example.com/psx.deltaskin"}
]}
''';
      const page = '''
<img data-console="gba" data-download="https://example.com/café skin.deltaskin" alt="Café" src="c.png">
''';
      final client = MockClient((request) async {
        if (request.url.path.endsWith('catalog.json')) return http.Response.bytes(utf8.encode(provenanceCatalog), 200);
        if (request.url.path.endsWith('/gba.html')) return http.Response.bytes(utf8.encode(page), 200);
        if (request.url.path.endsWith('.html')) return http.Response('', 200);
        return http.Response('missing', 404);
      });
      final unified = catalogs(client);
      final entries = await unified.load();
      expect(entries, isNotNull);
      expect(unified.unavailableSources, isEmpty);
      expect(entries!.map((entry) => entry.name),
          containsAll(<String>['Regular', 'Pokémon Pinball', 'DK control', 'PlayStation', 'Café']));
      expect(LibretroSkinCatalogs.forConsole(entries, 'gba').map((entry) => entry.name),
          <String>['Regular', 'Pokémon Pinball', 'Café']);
      expect(LibretroSkinCatalogs.forConsole(entries, 'psx').map((entry) => entry.name), <String>['PlayStation']);
      expect(
          LibretroSkinCatalogs.search(LibretroSkinCatalogs.forConsole(entries, 'gba'), 'pinball')
              .map((entry) => entry.name),
          <String>['Pokémon Pinball']);
      final pinball = entries.firstWhere((entry) => entry.name == 'Pokémon Pinball');
      expect(pinball.source, LibretroSkinSources.deltaStyles);
      expect(pinball.excludedReason, isNull);
    });


    test('the Delta Skins site cards', () {
      const html = '''
<div class="skin"><img data-console="gbc" data-maker="Maker &amp; Co" data-supports="All phones"
  data-download="https://example.com/a.deltaskin" alt="Pocket" src="images/gbc/pocket one.png"></div>
<img data-console="unofficial" data-download='https://example.com/gg.deltaskin' alt="Game Gear Clear" src="gg.png">
<img data-console="unofficial" data-download="https://example.com/vb.deltaskin" alt="Virtual Boy" src="vb.png">
<img data-console="gba" alt="No download" src="x.png">
''';
      final cards = LibretroSkinCatalogs.parseDeltaSkinsPage(html);
      expect(cards.map((card) => card.name), <String>['Pocket', 'Game Gear Clear']);
      expect(cards.first.consoles, <String>['gb', 'gbc']);
      expect(cards.first.author, 'Maker & Co');
      expect(cards.first.supports, 'All phones');
      expect(cards.first.thumbnailURL,
          'https://raw.githubusercontent.com/delta-skins/delta-skins.github.io/master/images/gbc/pocket%20one.png');
      expect(cards.first.source, LibretroSkinSources.deltaSkins);
      expect(cards.last.consoles, <String>['gg']);
    });

    test('the bundled overlay index: pinned sources, iPhone candidates, exclusions by path', () {
      final entries = LibretroSkinCatalogs.parseOverlayIndex(
        File('assets/data/libretro_skin_overlays.json').readAsStringSync(),
      );
      expect(entries, isNotEmpty);
      final candidates = entries.where((entry) => entry.excludedReason == null).toList();
      expect(candidates, isNotEmpty);
      for (final entry in entries) {
        final overlay = entry.overlay!;
        expect(overlay.commit, matches(RegExp(r'^[0-9a-f]{40}$')));
        expect(overlay.path, endsWith('.cfg'));
        expect(<String>[LibretroSkinSources.pocketArch, LibretroSkinSources.libretroOverlays], contains(entry.source));
        expect(entry.license, isNotNull);
        if (overlay.path.startsWith('keyboards/')) expect(entry.excludedReason, LibretroSkinCompatibility.desktop);
        if (overlay.path.startsWith('borders/')) expect(entry.excludedReason, LibretroSkinCompatibility.decorative);
        if (entry.source == LibretroSkinSources.pocketArch) expect(overlay.path, contains('Phone Taller (9x20)'));
        expect(overlay.fileUri(overlay.path).host, 'raw.githubusercontent.com');
        expect(overlay.fileUri(overlay.path).path, contains(overlay.commit));
      }
      expect(candidates.any((entry) => entry.source == LibretroSkinSources.pocketArch), isTrue);
      expect(candidates.any((entry) => entry.source == LibretroSkinSources.libretroOverlays), isTrue);
    });

    test('sources merged without duplicates, unreachable sources reported', () async {
      const provenanceCatalog = '''
{"skins": [
  {"id": "1", "name": "Shared", "author": "A", "systems": ["gba"], "downloadCount": 9,
   "downloadURL": "https://github.com/o/r/raw/main/Shared.deltaskin"},
  {"id": "2", "name": "Twice", "author": "B", "systems": ["gba"], "downloadCount": 1,
   "downloadURL": "https://example.com/twice-old.deltaskin"},
  {"id": "3", "name": "Twice", "author": "B", "systems": ["gba"], "downloadCount": 5,
   "downloadURL": "https://example.com/twice-new.deltaskin"}
]}
''';
      const page = '''
<img data-console="gba" data-download="https://raw.githubusercontent.com/o/r/main/Shared.deltaskin" alt="Shared again" src="s.png">
<img data-console="gba" data-download="https://example.com/site-only.deltaskin" alt="Site only" src="o.png">
''';
      var siteUp = true;
      final client = MockClient((request) async {
        if (request.url.path.endsWith('catalog.json')) return http.Response(provenanceCatalog, 200);
        if (request.url.path.endsWith('.html')) {
          if (!siteUp) return http.Response('down', 503);
          return http.Response(request.url.path.endsWith('/gba.html') ? page : '', 200);
        }
        return http.Response('missing', 404);
      });
      final unified = catalogs(client);
      final entries = (await unified.load())!;
      expect(entries.map((entry) => entry.name).toList(), <String>['Shared', 'Twice', 'Site only']);
      expect(entries.firstWhere((entry) => entry.name == 'Twice').downloadCount, 5);
      expect(entries.first.source, LibretroSkinSources.provenance);
      expect(entries.first.belongsToSource(LibretroSkinSources.provenance), isTrue);
      expect(unified.unavailableSources, isEmpty);
      expect(LibretroSkinCatalogs.forConsole(entries, 'gba').map((entry) => entry.name), <String>['Shared', 'Twice', 'Site only']);
      // The shared file belongs to both indexes while keeping one download
      // identity and its original author/source attribution.
      expect(entries.first.belongsToSource(LibretroSkinSources.deltaSkins), isTrue);
      expect(LibretroSkinCatalogs.search(entries, 'delta skins').map((entry) => entry.name), <String>['Shared', 'Site only']);

      siteUp = false;
      final again = (await unified.load(refresh: true))!;
      expect(again.map((entry) => entry.name), <String>['Shared', 'Twice']);
      expect(unified.unavailableSources, <String>{LibretroSkinSources.deltaSkins});
    });

    test('verdicts from the real info.json, cached, refreshed when stale or unreachable', () async {
      final files = <String, List<int>>{
        '/good.deltaskin': _skinZip(_info('Good', 'com.rileytestut.delta.game.gba'), files: {'a.png': _noise(32)}),
        '/desktop.deltaskin': _skinZip(_info('Desktop', 'com.rileytestut.delta.game.gba')),
        '/other.deltaskin': _skinZip(_info('Other', 'com.rileytestut.delta.game.snes')),
      };
      final host = _Host(files);
      final client = host.client;
      var now = DateTime.utc(2026, 10, 11);
      final unified = catalogs(client, clock: () => now);
      LibretroCatalogSkin entry(String file) => LibretroSkinCatalogs.fromProvenance(LibretroSkinCatalogEntry(
            id: file,
            name: file,
            systems: const <String>['gba'],
            downloadURL: 'https://example.com/$file',
          ));
      final good = entry('good.deltaskin');
      final desktop = entry('desktop.deltaskin');
      final other = entry('other.deltaskin');
      final missing = entry('missing.deltaskin');

      final reported = <String>[];
      final verdicts = await unified.classifyAll(
        <LibretroCatalogSkin>[good, desktop, other, missing],
        'gba',
        onVerdict: (entry, verdict) => reported.add(entry.name),
      );
      expect(reported.toSet(), <String>{'good.deltaskin', 'desktop.deltaskin', 'other.deltaskin', 'missing.deltaskin'});
      expect(verdicts[good.key]!.verdict, LibretroSkinVerdict.compatible);
      expect(verdicts[desktop.key]!.reasons, <String>['SKIN_COMPAT_NO_TOUCH_CONTROLS']);
      expect(verdicts[other.key]!.reasons, <String>[LibretroSkinCompatibility.otherConsole]);
      expect(verdicts[missing.key]!.reasons, <String>[LibretroSkinCompatibility.unreachable]);
      expect(LibretroSkinCatalogs.hidden(verdicts[good.key]), isFalse);
      expect(LibretroSkinCatalogs.hidden(verdicts[desktop.key]), isTrue);
      expect(LibretroSkinCatalogs.hidden(verdicts[desktop.key], tablet: true), isTrue);
      expect(LibretroSkinCatalogs.hidden(verdicts[other.key]), isTrue);
      // Not checked is not refused: shown, the install checks it again.
      expect(LibretroSkinCatalogs.hidden(verdicts[missing.key]), isFalse);
      expect(inspected.length, 3);
      // The inspection folders are removed.
      expect(Directory(path.join(skins.cacheDirectory, LibretroSkinCatalogs.inspectionFolderName)).listSync(), isEmpty);

      // Cached on disk: a new instance answers without the network.
      host.online = false;
      final cached = catalogs(client, clock: () => now);
      expect((await cached.knownVerdict(good, 'gba'))!.verdict, LibretroSkinVerdict.compatible);
      expect((await cached.classify(desktop, 'gba')).reasons, <String>['SKIN_COMPAT_NO_TOUCH_CONTROLS']);
      expect(inspected.length, 3);
      // An unreachable file is retried after 6 hours, a verdict after 30 days.
      now = now.add(const Duration(hours: 7));
      expect(await cached.knownVerdict(missing, 'gba'), isNull);
      expect(await cached.knownVerdict(good, 'gba'), isNotNull);
      now = now.add(const Duration(days: 31));
      expect(await cached.knownVerdict(good, 'gba'), isNull);
      // A console NeoStation does not emulate is decided without any check.
      expect((await cached.knownVerdict(good, 'saturn'))!.reasons, <String>[LibretroSkinCompatibility.system]);

      // Cached verdicts of older rules are ignored.
      final file = File(path.join(skins.cacheDirectory, LibretroSkinCatalogs.verdictsFileName));
      final json = jsonDecode(file.readAsStringSync()) as Map<String, Object?>;
      file.writeAsStringSync(jsonEncode(<String, Object?>{...json, 'rules': LibretroSkinCatalogs.rulesVersion - 1}));
      now = DateTime.utc(2026, 10, 11);
      expect(await catalogs(client, clock: () => now).knownVerdict(good, 'gba'), isNull);
    });

    test('an overlay is converted, judged by the native filter and installed with its images and license', () async {
      const commit = '33dc23be7ea5938956bbe686c1c9494ef5628e30';
      const cfgPath = 'Touch Overlays/Phone Taller (9x20)/GBA/GBA.cfg';
      const index = '''
{"version": 1,
 "sources": {"pocketarch": {"repository": "stunrelay/PocketArch", "commit": "$commit", "license": "MIT", "author": "stunrelay"}},
 "entries": [
  {"id": "po-1", "source": "pocketarch", "path": "$cfgPath", "name": "GBA", "consoles": ["gba"], "device": "iphone",
   "files": ["Touch Overlays/Phone Taller (9x20)/GBA/img/bg.png", "Touch Overlays/Phone Taller (9x20)/GBA/img/dpad.png",
             "Touch Overlays/Phone Taller (9x20)/GBA/img/a.png", "Touch Overlays/Phone Taller (9x20)/GBA/img/b.png"]},
  {"id": "po-2", "source": "pocketarch", "path": "Touch Overlays/Phone Taller (9x20)/GBA/windowed.cfg", "name": "Windowed",
   "consoles": ["gba"], "device": "iphone", "files": []},
  {"id": "lo-1", "source": "pocketarch", "path": "keyboards/qwerty.cfg", "name": "Keyboard", "consoles": [],
   "excluded": "SKIN_COMPAT_DESKTOP"}
 ]}
''';
      final png = <int>[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, ..._noise(24)];
      final requested = <String>[];
      final client = MockClient((request) async {
        final url = request.url;
        if (url.host != 'raw.githubusercontent.com') return http.Response('offline', 503);
        final file = '/${url.pathSegments.join('/')}';
        requested.add(file);
        if (!file.startsWith('/stunrelay/PocketArch/$commit/')) return http.Response('missing', 404);
        if (file.endsWith('/GBA.cfg')) return http.Response(_gbaOverlay, 200);
        if (file.endsWith('/windowed.cfg')) return http.Response('overlays = 1\noverlay0_descs = 0\n', 200);
        if (file.endsWith('.png')) return http.Response.bytes(png, 200);
        return http.Response('missing', 404);
      });
      final unified = catalogs(client, overlayIndex: index);
      final entries = LibretroSkinCatalogs.parseOverlayIndex(index);
      final overlay = entries.first;
      expect(overlay.license, 'MIT');

      final verdict = await unified.classify(overlay, 'gba');
      expect(verdict.verdict, LibretroSkinVerdict.compatible);
      final windowed = await unified.classify(entries[1], 'gba');
      expect(windowed.reasons, <String>[LibretroSkinCompatibility.overlayUnsupported]);
      expect((await unified.classify(entries[2], 'gba')).reasons, <String>[LibretroSkinCompatibility.desktop]);
      // Only the .cfg files were downloaded to judge them, never an image.
      expect(requested.where((file) => file.endsWith('.png')), isEmpty);
      expect(inspected.length, 1);

      final result = await unified.install(overlay, 'gba');
      expect(result, isA<LibretroSkinImported>());
      final installed = (result as LibretroSkinImported).skin;
      expect(installed.consoles, <String>['gba']);
      expect(installed.license, 'MIT');
      expect(installed.author, 'stunrelay');
      expect(installed.source, 'https://github.com/stunrelay/PocketArch/blob/$commit/Touch%20Overlays/Phone%20Taller%20(9x20)/GBA/GBA.cfg');
      expect(installed.compatibility['gba']?.verdict, LibretroSkinVerdict.compatible);
      final infoJson = jsonDecode(File(path.join(installed.directory, 'info.json')).readAsStringSync()) as Map;
      expect(infoJson['gameTypeIdentifier'], 'com.rileytestut.delta.game.gba');
      final images = Directory(path.join(installed.directory, 'images')).listSync().whereType<File>().toList();
      expect(images.length, 4);
      expect(images.every((file) => file.readAsBytesSync().length == png.length), isTrue);

      // An overlay that cannot be converted is refused with its reason.
      final refused = await unified.install(entries[1], 'gba');
      expect(refused, isA<LibretroSkinImportFailed>());
      expect((refused as LibretroSkinImportFailed).messageKey, LibretroSkinMessages.notPlayable);
      expect(refused.compatibility.single.reasons, <String>[LibretroSkinCompatibility.overlayUnsupported]);
    });

    test('composite previews use native layouts, both orientations, cache and no installation', () async {
      const overlay = LibretroOverlayEntry(id: 'preview-test', source: 'pocketarch',
        path: 'gba/test.cfg', repository: 'stunrelay/PocketArch', commit: 'abc', device: 'iphone',
        files: ['gba/img/bg.png', 'gba/img/dpad.png', 'gba/img/a.png', 'gba/img/b.png']);
      var downloads = 0;
      final client = MockClient((request) async {
        downloads++;
        return request.url.path.endsWith('.cfg') ? http.Response(_gbaOverlay, 200)
            : http.Response.bytes([1, 2, 3], 200);
      });
      var renders = 0;
      Future<Uint8List?> render(String directory, String console, String orientation, double w, double h) async {
        renders++;
        expect(console, 'gba');
        expect(orientation == 'portrait' ? w < h : w > h, isTrue);
        final info = jsonDecode(await File(path.join(directory, 'info.json')).readAsString()) as Map;
        final layout = ((info['representations'] as Map)['iphone'] as Map)['edgeToEdge'] as Map;
        expect(layout.keys, containsAll(['portrait', 'landscape']));
        final portrait = layout['portrait'] as Map;
        expect((portrait['items'] as List).length, greaterThan(4));
        expect(Directory(path.join(directory, 'images')).listSync().length, 4);
        return Uint8List.fromList([137, 80, 78, 71, orientation == 'portrait' ? 1 : 2]);
      }
      final unified = LibretroSkinCatalogs(skins: skins,
        provenance: LibretroSkinCatalogService(cacheDirectory: skins.cacheDirectory, skins: skins, client: client),
        client: client, renderPreview: render);
      final results = await Future.wait([unified.overlayPreviews(overlay, 'gba'), unified.overlayPreviews(overlay, 'gba')]);
      expect(results.first.keys, ['portrait', 'landscape']);
      expect(renders, 2);
      expect(downloads, 5);
      expect(await Directory(skins.skinsDirectory).exists(), isFalse);
      expect(nativeCalls.where((c) => c.method == 'setFrontendSetting'), isEmpty);
      unified.dispose();
      final offline = catalogs(MockClient((_) async => throw const SocketException('offline')));
      final cached = await offline.overlayPreviews(overlay, 'gba');
      expect(cached.keys, ['portrait', 'landscape']);
      expect(cached['portrait'], results.first['portrait']);
      offline.dispose();
    });

    test('missing descriptor images never produce a partial preview or installation', () async {
      const overlay = LibretroOverlayEntry(id: 'broken', source: 'pocketarch', path: 'gba/test.cfg',
        repository: 'stunrelay/PocketArch', commit: 'abc', device: 'iphone', files: ['gba/img/a.png']);
      final unified = catalogs(MockClient((_) async => http.Response(_gbaOverlay, 200)));
      expect(await unified.overlayPreviews(overlay, 'gba'), isEmpty);
      final entry = LibretroCatalogSkin(key: 'broken', source: 'pocketarch', name: 'Broken', consoles: ['gba'], overlay: overlay);
      expect(await unified.install(entry, 'gba'), isA<LibretroSkinImportFailed>());
      expect(nativeCalls.where((c) => c.method == 'skinPreview'), isEmpty);
      unified.dispose();
    });

    test('checks cut by closing the catalogs are not cached as unreachable', () async {
      final client = MockClient((request) async => throw http.ClientException('Connection closed'));
      final unified = catalogs(client);
      final entry = LibretroSkinCatalogs.fromProvenance(const LibretroSkinCatalogEntry(
        id: 'c',
        name: 'C',
        systems: <String>['gba'],
        downloadURL: 'https://example.com/c.deltaskin',
      ));
      unified.dispose();
      expect((await unified.classify(entry, 'gba')).reasons, <String>[LibretroSkinCompatibility.unreachable]);
      expect(await catalogs(client).knownVerdict(entry, 'gba'), isNull);
    });

    test('favorites persist in Documents/Libretro', () async {
      final unified = catalogs(MockClient((request) async => http.Response('', 404)));
      final entry = LibretroSkinCatalogs.fromProvenance(const LibretroSkinCatalogEntry(
        id: 'f',
        name: 'F',
        systems: <String>['gba'],
        downloadURL: 'https://example.com/f.deltaskin',
      ));
      await unified.setFavorite(entry, true);
      expect(await catalogs(MockClient((request) async => http.Response('', 404))).favorites(), <String>{entry.key});
      await unified.setFavorite(entry, false);
      expect(await catalogs(MockClient((request) async => http.Response('', 404))).favorites(), isEmpty);
      expect(File(path.join(root.path, LibretroSkinCatalogs.favoritesFileName)).existsSync(), isTrue);
    });
  });
}
