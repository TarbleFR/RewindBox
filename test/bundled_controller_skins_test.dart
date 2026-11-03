import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/testing.dart';
import 'package:neostation/services/bundled_controller_skins.dart';
import 'package:neostation/services/libretro_skin_catalog_service.dart';
import 'package:neostation/services/libretro_skin_catalogs.dart';
import 'package:neostation/services/libretro_skin_compatibility.dart';
import 'package:neostation/services/libretro_skin_service.dart';
import 'package:path/path.dart' as path;

const _channel = MethodChannel('neostation/libretro_internal');

ByteData _data(List<int> bytes) =>
    ByteData.sublistView(Uint8List.fromList(bytes));

Future<ByteData> _fileAsset(String asset) async =>
    _data(await File(asset).readAsBytes());

Map<String, Object?> _manifestEntry() => <String, Object?>{
  'id': 'rewindbox-wii-pocket',
  'name': 'RewindBox Wii Pocket',
  'console': 'wii',
  'archiveAsset': 'assets/skins/pocket/wii.manicskin',
  'sha256': List.filled(64, 'a').join(),
  'size': 1024,
  'previewAssets': <String, String>{
    'portrait': 'assets/skins/pocket/wii-portrait.png',
    'landscape': 'assets/skins/pocket/wii-landscape.png',
  },
  'author': 'RewindBox',
  'license': 'RewindBox original artwork',
};

Future<List<BundledControllerSkin>> _readManifest(Object? manifest) =>
    BundledControllerSkin.load(
      loadAsset: (_) async => _data(utf8.encode(jsonEncode(manifest))),
    );

Map<String, Object?> _manifest(List<Object?> entries) => <String, Object?>{
  'schemaVersion': 1,
  'skins': entries,
};

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final messenger =
      TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  late Directory root;
  late LibretroSkinService skins;
  late MockClient offline;
  late List<MethodCall> nativeCalls;
  late List<String> requests;
  final services = <LibretroSkinCatalogs>[];

  LibretroSkinCatalogs catalogs({
    Future<List<BundledControllerSkin>> Function()? loadSkins,
    Future<ByteData> Function(String)? loadAsset,
  }) {
    final service = LibretroSkinCatalogs(
      skins: skins,
      provenance: LibretroSkinCatalogService(
        cacheDirectory: skins.cacheDirectory,
        skins: skins,
        client: offline,
      ),
      client: offline,
      overlayIndex: () async => '{"entries": []}',
      loadBundledSkins:
          loadSkins ??
          (() => BundledControllerSkin.load(loadAsset: _fileAsset)),
      loadAsset: loadAsset ?? _fileAsset,
    );
    services.add(service);
    return service;
  }

  setUp(() async {
    root = await Directory.systemTemp.createTemp('bundled-controller-skins-');
    requests = <String>[];
    nativeCalls = <MethodCall>[];
    offline = MockClient((request) async {
      requests.add(request.url.toString());
      throw const SocketException('Test device is offline');
    });
    messenger.setMockMethodCallHandler(_channel, (call) async {
      nativeCalls.add(call);
      if (call.method == 'frontendSettings') {
        return <String, Object?>{
          'console': <String, Object?>{
            'skin.portrait': 'default',
            'skin.landscape': 'default',
          },
          'games': <String, Object?>{},
        };
      }
      fail(
        'Unexpected native operation ${call.method}: bundled Dolphin parsing stays in Dart.',
      );
    });
    skins = LibretroSkinService(
      skinsDirectory: path.join(root.path, 'Skins'),
      frontendDirectory: path.join(root.path, 'Config', 'Frontend'),
      cacheDirectory: path.join(root.path, 'Caches'),
    );
  });

  tearDown(() async {
    for (final service in services) {
      service.dispose();
    }
    services.clear();
    offline.close();
    messenger.setMockMethodCallHandler(_channel, null);
    await root.delete(recursive: true);
  });

  test(
    'manifest accepts its declared metadata without loading the archives',
    () async {
      final entries = await _readManifest(
        _manifest(<Object?>[_manifestEntry()]),
      );
      final entry = entries.single;
      expect(entry.id, 'rewindbox-wii-pocket');
      expect(entry.console, 'wii');
      expect(entry.archiveAsset, 'assets/skins/pocket/wii.manicskin');
      expect(
        entry.previewAssets.keys,
        unorderedEquals(<String>['portrait', 'landscape']),
      );
      expect(entry.author, 'RewindBox');
      expect(entry.license, 'RewindBox original artwork');
    },
  );

  test('manifest rejects wrong schema, bad rows and duplicate ids', () async {
    for (final manifest in <Object?>[
      <String, Object?>{'schemaVersion': 2, 'skins': <Object?>[]},
      <String, Object?>{'schemaVersion': 1, 'skins': 'not a list'},
      _manifest(<Object?>[null]),
      _manifest(<Object?>[_manifestEntry(), _manifestEntry()]),
    ]) {
      await expectLater(_readManifest(manifest), throwsFormatException);
    }
    for (final change in <Map<String, Object?>>[
      <String, Object?>{'console': 'n64'},
      <String, Object?>{'sha256': 'not-a-digest'},
      <String, Object?>{'size': 0},
      <String, Object?>{'size': LibretroSkinService.maxArchiveBytes + 1},
      <String, Object?>{'id': ''},
    ]) {
      await expectLater(
        _readManifest(
          _manifest(<Object?>[
            <String, Object?>{..._manifestEntry(), ...change},
          ]),
        ),
        throwsFormatException,
        reason: 'reject $change',
      );
    }
  });

  test(
    'manifest never accepts paths outside the bundled skin directory',
    () async {
      for (final unsafe in <String>[
        '../wii.manicskin',
        '/assets/skins/pocket/wii.manicskin',
        'assets/skins/pocket/../wii.manicskin',
        'assets/skins/pocket/../../legal/notice.txt',
        r'assets\skins\pocket\wii.manicskin',
        'https://example.com/wii.manicskin',
        'assets/data/wii.manicskin',
      ]) {
        await expectLater(
          _readManifest(
            _manifest(<Object?>[
              <String, Object?>{..._manifestEntry(), 'archiveAsset': unsafe},
            ]),
          ),
          throwsFormatException,
          reason: unsafe,
        );
        await expectLater(
          _readManifest(
            _manifest(<Object?>[
              <String, Object?>{
                ..._manifestEntry(),
                'previewAssets': <String, String>{
                  'portrait': unsafe,
                  'landscape': unsafe,
                },
              },
            ]),
          ),
          throwsFormatException,
          reason: 'preview $unsafe',
        );
      }
    },
  );

  test(
    'shipped catalog contains exactly Wii, GameCube and PS2 with intact archives and PNG previews',
    () async {
      final entries = await BundledControllerSkin.load(loadAsset: _fileAsset);
      expect(
        entries.map((entry) => entry.console),
        unorderedEquals(<String>['wii', 'gc', 'ps2']),
      );
      expect(entries.map((entry) => entry.id).toSet(), hasLength(3));
      for (final entry in entries) {
        final archive = await File(entry.archiveAsset).readAsBytes();
        expect(archive.length, entry.size, reason: entry.console);
        expect(
          sha256.convert(archive).toString(),
          entry.sha256,
          reason: entry.console,
        );
        expect(LibretroSkinService.isZipSignature(archive), isTrue);
        expect(entry.author, 'RewindBox');
        expect(
          entry.previewAssets.keys,
          unorderedEquals(<String>['portrait', 'landscape']),
        );
        for (final asset in entry.previewAssets.values) {
          expect((await File(asset).readAsBytes()).take(8), <int>[
            137,
            80,
            78,
            71,
            13,
            10,
            26,
            10,
          ]);
        }
      }
    },
  );

  test(
    'bundled entries classify and install offline through normal import without changing selection',
    () async {
      final service = catalogs();
      final entries = await service.bundledEntries();
      expect(entries, hasLength(3));
      expect(entries.every((entry) => entry.bundled != null), isTrue);
      for (final entry in entries) {
        final console = entry.consoles.single;
        final selection = await skins.selectedSkins(console);
        final verdict = await service.classify(entry, console);
        expect(
          verdict.offered,
          isTrue,
          reason: '$console ${verdict.reasons} ${verdict.missingControls}',
        );
        expect(verdict.playableIn('portrait'), isTrue, reason: console);
        expect(verdict.playableIn('landscape'), isTrue, reason: console);
        final result = await service.install(entry, console);
        expect(result, isA<LibretroSkinImported>(), reason: console);
        final installed = (result as LibretroSkinImported).skin;
        expect(installed.consoles, <String>[console]);
        expect(installed.supports('portrait'), isTrue);
        expect(installed.supports('landscape'), isTrue);
        expect(installed.sha256, entry.bundled!.sha256);
        expect(await skins.selectedSkins(console), selection);
        expect(await skins.installedSkins(console: console), hasLength(1));
      }
      expect(
        requests,
        isEmpty,
        reason: 'offline entries do not fetch a catalog, preview or archive',
      );
      expect(
        nativeCalls.where((call) => call.method == 'setFrontendSetting'),
        isEmpty,
      );
    },
  );

  test(
    'unified catalog keeps all three originals when remote catalogs are offline',
    () async {
      final service = catalogs();
      final entries = await service.load();
      expect(entries, isNotNull);
      expect(
        entries!.map((entry) => entry.consoles.single),
        unorderedEquals(<String>['wii', 'gc', 'ps2']),
      );
      expect(entries.every((entry) => entry.bundled != null), isTrue);
      expect(requests, isNotEmpty, reason: 'remote failures were exercised');
      expect(
        service.unavailableSources,
        contains(LibretroSkinSources.provenance),
      );
      expect(
        await skins.installedSkins(),
        isEmpty,
        reason: 'listing does not install an original',
      );
    },
  );

  test(
    'a bundled archive cannot be classified or installed for another console',
    () async {
      final service = catalogs();
      final entry = (await service.bundledEntries()).singleWhere(
        (entry) => entry.consoles.single == 'wii',
      );
      final verdict = await service.classify(entry, 'gc');
      expect(verdict.offered, isFalse);
      expect(verdict.reasons, contains(LibretroSkinCompatibility.otherConsole));
      expect(
        await service.install(entry, 'gc'),
        isA<LibretroSkinImportFailed>(),
      );
      expect(await skins.installedSkins(), isEmpty);
      expect(requests, isEmpty);
    },
  );

  for (final tampering in <String>['size', 'digest']) {
    test(
      '$tampering mismatch refuses bundled classification and import before installation',
      () async {
        final originals = await BundledControllerSkin.load(
          loadAsset: _fileAsset,
        );
        final original = originals.first;
        final bytes = await File(original.archiveAsset).readAsBytes();
        final changed = tampering == 'size'
            ? Uint8List.fromList(<int>[...bytes, 0])
            : (Uint8List.fromList(bytes)..[bytes.length ~/ 2] ^= 1);
        final service = catalogs(
          loadSkins: () async => <BundledControllerSkin>[original],
          loadAsset: (asset) async => asset == original.archiveAsset
              ? _data(changed)
              : _fileAsset(asset),
        );
        final entry = (await service.bundledEntries()).single;
        expect(
          (await service.classify(entry, original.console)).offered,
          isFalse,
        );
        expect(
          await service.install(entry, original.console),
          isA<LibretroSkinImportFailed>(),
        );
        expect(await skins.installedSkins(), isEmpty);
        expect(requests, isEmpty);
        expect(
          nativeCalls,
          isEmpty,
          reason:
              'corrupt bundled bytes must fail before parsing or changing settings',
        );
      },
    );
  }
}
