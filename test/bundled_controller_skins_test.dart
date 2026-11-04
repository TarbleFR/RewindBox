import 'dart:convert';
import 'dart:io';

import 'package:archive/archive.dart';
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

const _shippedPacks = <String, String>{
  'wii-pocket': 'wii',
  'gamecube-pocket': 'gc',
  'ps2-pocket': 'ps2',
  'gamecube-pocket-original': 'gc',
  'wii-pocket-original': 'wii',
  'ps2-pocket-original': 'ps2',
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
    'shipped catalog contains the Wii, GameCube, PS2 Pocket packs and the three board Originals with intact archives and PNG previews',
    () async {
      final entries = await BundledControllerSkin.load(loadAsset: _fileAsset);
      expect({
        for (final entry in entries) entry.id: entry.console,
      }, _shippedPacks);
      expect(
        {for (final entry in entries) entry.id: entry.name},
        containsPair('gamecube-pocket-original', 'GameCube Pocket — Original'),
      );
      expect({
        for (final entry in entries) entry.id: entry.name,
      }, containsPair('wii-pocket-original', 'Wii Pocket — Original'));
      expect({
        for (final entry in entries) entry.id: entry.name,
      }, containsPair('ps2-pocket-original', 'PS2 Pocket — Original'));
      // New archives and previews of their own: nothing of an earlier pack is reused.
      expect(entries.map((entry) => entry.archiveAsset).toSet(), hasLength(6));
      expect(entries.map((entry) => entry.sha256).toSet(), hasLength(6));
      expect(
        entries.expand((entry) => entry.previewAssets.values).toSet(),
        hasLength(12),
      );
      // The earlier PS2 Pocket keeps its id, archive and previews unchanged.
      final ps2 = entries.singleWhere((entry) => entry.id == 'ps2-pocket');
      expect(ps2.archiveAsset, 'assets/skins/pocket/ps2-pocket.manicskin');
      expect(
        ps2.sha256,
        '2106e5f755dd5128c7ab20f06e503164e9f7fd2cd02d88650ee1fc0aae9a16ad',
      );
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
      expect(entries, hasLength(_shippedPacks.length));
      expect(entries.every((entry) => entry.bundled != null), isTrue);
      final installedPerConsole = <String, int>{};
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
        installedPerConsole[console] = (installedPerConsole[console] ?? 0) + 1;
        // An Original installs beside the earlier pack of its console, never over it.
        expect(
          await skins.installedSkins(console: console),
          hasLength(installedPerConsole[console]),
        );
      }
      expect(installedPerConsole, <String, int>{'wii': 2, 'gc': 2, 'ps2': 2});
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
    'unified catalog keeps every shipped pack when remote catalogs are offline',
    () async {
      final service = catalogs();
      final entries = await service.load();
      expect(entries, isNotNull);
      expect(
        entries!.map((entry) => entry.consoles.single),
        unorderedEquals(<String>['wii', 'gc', 'ps2', 'gc', 'wii', 'ps2']),
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
      final wii = (await service.bundledEntries())
          .where((entry) => entry.consoles.single == 'wii')
          .toList();
      expect(wii, hasLength(2), reason: 'Wii Pocket and its board Original');
      for (final entry in wii) {
        final verdict = await service.classify(entry, 'gc');
        expect(verdict.offered, isFalse);
        expect(
          verdict.reasons,
          contains(LibretroSkinCompatibility.otherConsole),
        );
        expect(
          await service.install(entry, 'gc'),
          isA<LibretroSkinImportFailed>(),
        );
      }
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

  test(
    'Originals coexist with the earlier packs: selection, persistence and read-back by id, old choices kept',
    () async {
      // Frontend settings stored like the native bridge: console scope, then games.
      final stored = <String, Map<String, Object?>>{};
      messenger.setMockMethodCallHandler(_channel, (call) async {
        nativeCalls.add(call);
        final args = Map<String, Object?>.from(
          (call.arguments as Map?) ?? const {},
        );
        final console = args['console'] as String;
        final scopes = stored.putIfAbsent(
          console,
          () => <String, Object?>{
            'console': <String, Object?>{},
            'games': <String, Object?>{},
          },
        );
        if (call.method == 'frontendSettings') return scopes;
        if (call.method == 'setFrontendSetting') {
          final game = args['game'] as String?;
          final scope = game == null
              ? scopes['console'] as Map<String, Object?>
              : ((scopes['games'] as Map<String, Object?>).putIfAbsent(
                      game,
                      () => <String, Object?>{},
                    )
                    as Map<String, Object?>);
          final value = args['value'];
          if (value == null) {
            scope.remove(args['key']);
          } else {
            scope[args['key'] as String] = value;
          }
          return true;
        }
        fail('Unexpected native operation ${call.method}');
      });
      final service = catalogs();
      final installed = <String, LibretroInstalledSkin>{};
      for (final entry in await service.bundledEntries()) {
        final result = await service.install(entry, entry.consoles.single);
        expect(result, isA<LibretroSkinImported>());
        installed[entry.bundled!.id] = (result as LibretroSkinImported).skin;
      }
      expect(installed.keys.toSet(), _shippedPacks.keys.toSet());
      expect(
        installed.values.map((skin) => skin.id).toSet(),
        hasLength(6),
        reason: 'distinct installed ids',
      );
      expect(
        installed['gamecube-pocket-original']!.identifier,
        'org.rewindbox.gamecube-pocket-original',
      );
      expect(
        installed['wii-pocket-original']!.identifier,
        'org.rewindbox.wii-pocket-original',
      );
      expect(
        installed['gamecube-pocket']!.identifier,
        isNot(installed['gamecube-pocket-original']!.identifier),
      );
      // Nothing was selected by installing: the defaults are untouched.
      for (final console in ['gc', 'wii', 'ps2']) {
        expect(await skins.selectedSkins(console), <String, String?>{
          'portrait': null,
          'landscape': null,
        });
      }
      // A user who chose the earlier Wii pack keeps it.
      final oldWii = installed['wii-pocket']!.id;
      for (final orientation in ['portrait', 'landscape']) {
        await skins.select(
          console: 'wii',
          orientation: orientation,
          skinId: oldWii,
        );
      }
      // GameCube: the Original in portrait, the earlier pack in landscape, and a
      // game choosing the Original in both.
      final gcOriginal = installed['gamecube-pocket-original']!.id;
      final gcOld = installed['gamecube-pocket']!.id;
      await skins.select(
        console: 'gc',
        orientation: 'portrait',
        skinId: gcOriginal,
      );
      await skins.select(
        console: 'gc',
        orientation: 'landscape',
        skinId: gcOld,
      );
      for (final orientation in ['portrait', 'landscape']) {
        await skins.select(
          console: 'gc',
          orientation: orientation,
          skinId: gcOriginal,
          game: 'GALE01',
        );
      }
      expect(await skins.selectedSkins('gc'), <String, String?>{
        'portrait': gcOriginal,
        'landscape': gcOld,
      });
      expect(await skins.selectedSkins('gc', game: 'GALE01'), <String, String?>{
        'portrait': gcOriginal,
        'landscape': gcOriginal,
      });
      expect(await skins.selectedSkins('wii'), <String, String?>{
        'portrait': oldWii,
        'landscape': oldWii,
      });
      // The stored values are the installed ids, read back from disk.
      final read = await skins.installedSkin(gcOriginal);
      expect(read, isNotNull);
      expect(read!.identifier, 'org.rewindbox.gamecube-pocket-original');
      expect(read.supports('portrait') && read.supports('landscape'), isTrue);
      // Wii Original selectable too; the earlier pack still installed and readable.
      final wiiOriginal = installed['wii-pocket-original']!.id;
      await skins.select(
        console: 'wii',
        orientation: 'landscape',
        skinId: wiiOriginal,
      );
      expect(await skins.selectedSkins('wii'), <String, String?>{
        'portrait': oldWii,
        'landscape': wiiOriginal,
      });
      expect(await skins.installedSkin(oldWii), isNotNull);
      expect(await skins.installedSkin(gcOld), isNotNull);
      expect(await skins.installedSkins(console: 'gc'), hasLength(2));
      expect(await skins.installedSkins(console: 'wii'), hasLength(2));
      // PS2: a player who chose the earlier PS2 Pocket keeps it; the Original is a
      // distinct installed skin, selectable for the console or one game.
      final ps2Old = installed['ps2-pocket']!.id;
      final ps2Original = installed['ps2-pocket-original']!.id;
      expect(
        installed['ps2-pocket-original']!.identifier,
        'org.rewindbox.ps2-pocket-original',
      );
      expect(ps2Original, isNot(ps2Old));
      for (final orientation in ['portrait', 'landscape']) {
        await skins.select(
          console: 'ps2',
          orientation: orientation,
          skinId: ps2Old,
        );
        await skins.select(
          console: 'ps2',
          orientation: orientation,
          skinId: ps2Original,
          game: 'SLUS-20062',
        );
      }
      expect(await skins.selectedSkins('ps2'), <String, String?>{
        'portrait': ps2Old,
        'landscape': ps2Old,
      });
      expect(
        await skins.selectedSkins('ps2', game: 'SLUS-20062'),
        <String, String?>{'portrait': ps2Original, 'landscape': ps2Original},
      );
      final readPs2 = await skins.installedSkin(ps2Original);
      expect(readPs2!.identifier, 'org.rewindbox.ps2-pocket-original');
      expect(
        readPs2.supports('portrait') && readPs2.supports('landscape'),
        isTrue,
      );
      expect(await skins.installedSkin(ps2Old), isNotNull);
      expect(await skins.installedSkins(console: 'ps2'), hasLength(2));
      expect(requests, isEmpty);
    },
  );

  test(
    'a RewindBox pack installed by an earlier build follows the shipped archive, selections kept, nothing else touched',
    () async {
      // Frontend settings stored like the native bridge; forgetSkin also clears
      // what still names the deleted skin, as LibretroFrontendStore does.
      final stored = <String, Map<String, Object?>>{};
      Map<String, Object?> scopes(String console) => stored.putIfAbsent(
        console,
        () => <String, Object?>{
          'console': <String, Object?>{},
          'games': <String, Object?>{},
        },
      );
      final forgotten = <String>[];
      messenger.setMockMethodCallHandler(_channel, (call) async {
        nativeCalls.add(call);
        final args = Map<String, Object?>.from(
          (call.arguments as Map?) ?? const {},
        );
        if (call.method == 'forgetSkin') {
          final id = args['skinId'] as String;
          forgotten.add(id);
          for (final console in stored.values) {
            (console['console'] as Map<String, Object?>).removeWhere(
              (_, value) => value == id,
            );
            for (final game
                in (console['games'] as Map<String, Object?>).values) {
              (game as Map<String, Object?>).removeWhere(
                (_, value) => value == id,
              );
            }
          }
          return true;
        }
        final console = args['console'] as String;
        if (call.method == 'frontendSettings') return scopes(console);
        if (call.method == 'setFrontendSetting') {
          final game = args['game'] as String?;
          final scope = game == null
              ? scopes(console)['console'] as Map<String, Object?>
              : ((scopes(console)['games'] as Map<String, Object?>).putIfAbsent(
                      game,
                      () => <String, Object?>{},
                    )
                    as Map<String, Object?>);
          scope[args['key'] as String] = args['value'];
          return true;
        }
        fail('Unexpected native operation ${call.method}');
      });
      // The device state of the maintainer's recording: GameCube Pocket —
      // Original installed by an earlier build (same identifier, other archive
      // bytes), chosen for the console and for one game.
      Future<String> rewrite(
        String asset,
        String name, {
        String? identifier,
      }) async {
        final source = ZipDecoder().decodeBytes(
          await File(asset).readAsBytes(),
        );
        final out = Archive();
        for (final file in source.files) {
          var bytes = file.readBytes()!;
          if (file.name == 'LICENSE.txt') {
            bytes = Uint8List.fromList([
              ...bytes,
              ...utf8.encode('\nearlier build\n'),
            ]);
          }
          if (identifier != null && file.name == 'info.json') {
            final info = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
            info['identifier'] = identifier;
            info['name'] = 'My own GameCube skin';
            bytes = Uint8List.fromList(utf8.encode(jsonEncode(info)));
          }
          out.addFile(ArchiveFile(file.name, bytes.length, bytes));
        }
        final target = File(path.join(root.path, name));
        await target.writeAsBytes(ZipEncoder().encode(out), flush: true);
        return target.path;
      }

      final shipped = {
        for (final bundle in await BundledControllerSkin.load(
          loadAsset: _fileAsset,
        ))
          bundle.id: bundle,
      };
      final stale = await skins.importFromFile(
        await rewrite(
          'assets/skins/pocket/gamecube-pocket-original.manicskin',
          'earlier.manicskin',
        ),
        source: 'RewindBox Originals',
        targetConsole: 'gc',
      );
      expect(stale, isA<LibretroSkinImported>());
      final old = (stale as LibretroSkinImported).skin;
      expect(old.identifier, 'org.rewindbox.gamecube-pocket-original');
      expect(old.sha256, isNot(shipped['gamecube-pocket-original']!.sha256));
      // Beside it: a current bundled pack and a skin of the user's own.
      final service = catalogs();
      final wii = (await service.bundledEntries()).singleWhere(
        (entry) => entry.bundled!.id == 'wii-pocket',
      );
      final current =
          (await service.install(wii, 'wii') as LibretroSkinImported).skin;
      final own =
          (await skins.importFromFile(
                    await rewrite(
                      'assets/skins/pocket/gamecube-pocket.manicskin',
                      'own.manicskin',
                      identifier: 'com.example.my-gamecube',
                    ),
                    targetConsole: 'gc',
                  )
                  as LibretroSkinImported)
              .skin;
      for (final orientation in ['portrait', 'landscape']) {
        await skins.select(
          console: 'gc',
          orientation: orientation,
          skinId: old.id,
        );
        await skins.select(
          console: 'wii',
          orientation: orientation,
          skinId: current.id,
        );
      }
      await skins.select(
        console: 'gc',
        orientation: 'landscape',
        skinId: old.id,
        game: 'GFEP01',
      );
      await skins.select(
        console: 'gc',
        orientation: 'portrait',
        skinId: own.id,
        game: 'GALE01',
      );

      final refreshed = await service.refreshInstalledBundledSkins();

      expect(refreshed, hasLength(1));
      final fresh = refreshed.single;
      final bundle = shipped['gamecube-pocket-original']!;
      expect(fresh.identifier, old.identifier);
      expect(
        fresh.sha256,
        bundle.sha256,
        reason: 'the archive this build ships',
      );
      expect(fresh.id, bundle.sha256.substring(0, 16));
      expect(
        await skins.installedSkin(old.id),
        isNull,
        reason: 'old copy deleted',
      );
      expect(forgotten, <String>[old.id]);
      expect(await skins.selectedSkins('gc'), <String, String?>{
        'portrait': fresh.id,
        'landscape': fresh.id,
      });
      expect(await skins.selectedSkins('gc', game: 'GFEP01'), <String, String?>{
        'portrait': null,
        'landscape': fresh.id,
      }, reason: 'the game choice moved to the shipped copy');
      expect(
        (await skins.selectedSkins('gc', game: 'GALE01'))['portrait'],
        own.id,
        reason: 'the user skin and its choice are untouched',
      );
      expect(await skins.selectedSkins('wii'), <String, String?>{
        'portrait': current.id,
        'landscape': current.id,
      });
      expect(
        (await skins.installedSkins()).map((skin) => skin.id).toSet(),
        <String>{fresh.id, current.id, own.id},
        reason: 'no pack installed that was not installed before',
      );
      // The refreshed skin is the shipped one, read back from disk.
      final read = await skins.installedSkin(fresh.id);
      expect(read!.supports('portrait') && read.supports('landscape'), isTrue);
      expect(read.source, 'RewindBox Originals');
      // Up to date: nothing more to do, no archive replaced.
      nativeCalls.clear();
      expect(await service.refreshInstalledBundledSkins(), isEmpty);
      expect(
        nativeCalls.where((call) => call.method != 'frontendSettings'),
        isEmpty,
      );
      expect(requests, isEmpty);
    },
  );
}
