// GameTDB for Wii, GameCube, Wii U, DS and 3DS (docs/game-box-3d.md § 25):
// the game's id is read in its ROM header, the edition's region comes from
// it, and a title match is never taken for the player's product.
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/services/game_box/game_box_rom_id.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
import 'package:neostation/widgets/game_box/game_box_art_loader.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

class _FP extends FileProvider {
  _FP(this.root);
  final String root;
  @override
  bool get isInitialized => true;
  @override
  String getMediaPath(String s, String t, String r, String e) =>
      p.join(root, 'media', s, t, '${FileProvider.stripRomExtension(r)}.$e');
  @override
  String getMediaDirectoryPath() => p.join(root, 'media');
  @override
  List<String> getEsdeMediaCandidates(String s, String t, String r) => const [];
}

Uint8List _bytes(int length) => Uint8List(length);

void _put(Uint8List b, int offset, List<int> data) => b.setRange(offset, offset + data.length, data);
void _ascii(Uint8List b, int offset, String s) => _put(b, offset, s.codeUnits);
void _be32(Uint8List b, int o, int v) => _put(b, o, [(v >> 24) & 255, (v >> 16) & 255, (v >> 8) & 255, v & 255]);
void _le32(Uint8List b, int o, int v) => _put(b, o, [v & 255, (v >> 8) & 255, (v >> 16) & 255, (v >> 24) & 255]);

/// A Wii (or GameCube) disc header for [id].
Uint8List _discHeader(String id, {bool gameCube = false}) {
  final h = _bytes(0x440);
  _ascii(h, 0, id);
  if (gameCube) {
    _be32(h, 0x1C, 0xC2339F3D);
  } else {
    _be32(h, 0x18, 0x5D1C9EA3);
  }
  _ascii(h, 0x20, 'GAME TITLE');
  return h;
}

Uint8List _ncch(String product) {
  final n = _bytes(0x200);
  _ascii(n, 0x100, 'NCCH');
  _ascii(n, 0x150, product);
  return n;
}

Future<Uint8List> _png(int w, int h, Color color) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  c.drawRect(Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()), Paint()..color = color);
  for (var i = 0; i < 10; i++) {
    c.drawRect(Rect.fromLTWH(w * 0.1, h * (0.1 + i * 0.07), w * 0.6, h * 0.02), Paint()..color = Colors.black);
  }
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

GameModel _game(String rom, String name, String system, {String? romPath, String? titleId}) => GameModel(
      romname: rom, realname: name, name: name, year: '', developer: '', publisher: '', genre: '', players: '',
      rating: 0, systemId: system, systemFolderName: system, romPath: romPath, titleId: titleId,
    );

void main() {
  late Directory dir;
  setUp(() {
    dir = Directory.systemTemp.createTempSync('gbnin');
    GameBoxRomId.clearCache();
  });
  tearDown(() => dir.deleteSync(recursive: true));

  Future<String> file(String name, Uint8List bytes) async {
    final f = File(p.join(dir.path, name))..writeAsBytesSync(bytes);
    return f.path;
  }

  group('the id in the ROM', () {
    test('Wii and GameCube: ISO, GCM, WBFS, RVZ/WIA, CISO and TGC', () async {
      expect(await GameBoxRomId.read(await file('brawl.iso', _discHeader('RSBP01')), 'wii'), 'RSBP01');
      expect(await GameBoxRomId.read(await file('melee.gcm', _discHeader('GALP01', gameCube: true)), 'wii'), 'GALP01');
      final wbfs = _bytes(0x400)
        ..setAll(0, 'WBFS'.codeUnits)
        ..setAll(0x200, _discHeader('RMCP01').sublist(0, 0x20));
      expect(await GameBoxRomId.read(await file('mkwii.wbfs', wbfs), 'wii'), 'RMCP01');
      for (final magic in ['RVZ\x01', 'WIA\x01']) {
        final rvz = _bytes(0x400)
          ..setAll(0, magic.codeUnits)
          ..setAll(0x58, _discHeader('SMNP01').sublist(0, 0x20));
        expect(await GameBoxRomId.read(await file('nsmb${magic[0]}.rvz', rvz), 'wii'), 'SMNP01', reason: magic);
      }
      final ciso = _bytes(0x8100)
        ..setAll(0, 'CISO'.codeUnits)
        ..setAll(0x8000, _discHeader('RZDP01').sublist(0, 0x20));
      expect(await GameBoxRomId.read(await file('zelda.ciso', ciso), 'wii'), 'RZDP01');
      final tgc = _bytes(0x8100);
      _be32(tgc, 0, 0xAE0F38A2);
      _be32(tgc, 8, 0x8000);
      tgc.setAll(0x8000, _discHeader('GM4P01', gameCube: true).sublist(0, 0x20));
      expect(await GameBoxRomId.read(await file('dd.tgc', tgc), 'wii'), 'GM4P01');
    });

    test('a file without a disc header gives nothing (GCZ, other data)', () async {
      final gcz = _bytes(0x400);
      _le32(gcz, 0, 0xB10BC001);
      expect(await GameBoxRomId.read(await file('x.gcz', gcz), 'wii'), isNull);
      final text = Uint8List.fromList('RSBP01 is not a disc'.padRight(0x400).codeUnits);
      expect(await GameBoxRomId.read(await file('x.iso', text), 'wii'), isNull, reason: 'no disc magic');
    });

    test('DS cartridge code, 3DS product code (CXI, CCI, decrypted CIA)', () async {
      final nds = _bytes(0x200);
      _ascii(nds, 0, 'MARIOKART DS');
      _ascii(nds, 0x0C, 'AMCP');
      expect(await GameBoxRomId.read(await file('mkds.nds', nds), 'ds'), 'AMCP');
      final binary = Uint8List.fromList(List.generate(0x200, (i) => i % 7 == 0 ? 1 : 0x41));
      expect(await GameBoxRomId.read(await file('bad.nds', binary), 'ds'), isNull, reason: 'a title that is not text');

      expect(await GameBoxRomId.read(await file('mk7.cxi', _ncch('CTR-P-AMKP')), '3ds'), 'AMKP');
      final cci = _bytes(0x4200);
      _ascii(cci, 0x100, 'NCSD');
      _le32(cci, 0x120, 0x4000 ~/ 0x200);
      cci.setAll(0x4000, _ncch('CTR-P-AJRP'));
      expect(await GameBoxRomId.read(await file('mm3d.3ds', cci), '3ds'), 'AJRP');
      // CIA: 0x2020 header, then certificates, ticket and TMD (64-aligned).
      const cert = 0xA00, ticket = 0x350, tmd = 0xB34;
      final offset = 0x2040 + cert + 0x380 + 0xB40;
      final cia = _bytes(offset + 0x200);
      _le32(cia, 0, 0x2020);
      _le32(cia, 0x08, cert);
      _le32(cia, 0x0C, ticket);
      _le32(cia, 0x10, tmd);
      _le32(cia, 0x18, 0x100000);
      cia.setAll(offset, _ncch('CTR-P-ECDP'));
      expect(await GameBoxRomId.read(await file('game.cia', cia), '3ds'), 'ECDP');
    });

    test('Wii U: WUD, WUX and an extracted title', () async {
      final wud = _bytes(0x400);
      _ascii(wud, 0, 'WUP-P-ARPP');
      expect(await GameBoxRomId.read(await file('nsmbu.wud', wud), 'wiiu'), 'ARPP');
      // WUX: 0x8000 sectors, index of 2 sectors, data aligned on a sector.
      final wux = _bytes(0x8000 * 3);
      _ascii(wux, 0, 'WUX0');
      _le32(wux, 4, 0x1099D02E);
      _le32(wux, 8, 0x8000);
      _le32(wux, 0x10, 0x8000 * 2);
      _le32(wux, 0x20, 1); // logical sector 0 is stored second
      _ascii(wux, 0x8000 + 0x8000, 'WUP-P-AMKP');
      expect(await GameBoxRomId.read(await file('mk8.wux', wux), 'wiiu'), 'AMKP');
      final title = Directory(p.join(dir.path, 'Mario Kart 8'))..createSync();
      File(p.join(title.path, 'meta', 'meta.xml'))
        ..createSync(recursive: true)
        ..writeAsStringSync('<menu><product_code type="string" length="32">WUP-P-AMKP</product_code>'
            '<company_code type="string" length="8">0001</company_code></menu>');
      expect(await GameBoxRomId.read(title.path, 'wiiu'), 'AMKP01');
      File(p.join(title.path, 'code', 'Turbo.rpx')).createSync(recursive: true);
      expect(await GameBoxRomId.read(p.join(title.path, 'code', 'Turbo.rpx'), 'wiiu'), 'AMKP01');
    });

    test('an id in the file name, the library title id, and the region letter', () async {
      expect(GameBoxRomId.fromFileName('Super Smash Bros. Brawl [RSBP01].iso', 'wii'), 'RSBP01');
      expect(GameBoxRomId.fromFileName('Mario Kart DS (Europe) (AMCP).nds', 'ds'), 'AMCP');
      expect(GameBoxRomId.fromFileName('Mario Kart DS (Europe) (2005).nds', 'ds'), isNull);
      expect(GameBoxRomId.fromFileName('Game (USA).iso', 'wii'), isNull);
      expect(await GameBoxRomId.forGame(_game('x.rpcs3', 'X', 'wii', titleId: 'rsbp01'), 'wii'), 'RSBP01');
      final iso = await file('brawl.iso', _discHeader('RSBF01'));
      expect(await GameBoxRomId.forGame(_game('Brawl [RSBP01].iso', 'Brawl', 'wii', romPath: iso), 'wii'), 'RSBF01',
          reason: 'the header wins over the name');
      expect(GameBoxRomId.regionsOf('RSBP01'), ['eu']);
      expect(GameBoxRomId.regionsOf('RSBF01'), ['fr']);
      expect(GameBoxRomId.regionsOf('AMCE'), ['us']);
      expect(GameBoxRomId.regionsOf('AMKJ'), ['jp']);
    });
  });

  group('GameTDB for the Nintendo platforms', () {
    test('platforms, pages and art', () {
      expect(GameTdb.platformOf('wii'), 'wii');
      expect(GameTdb.platformOf('gc'), 'wii', reason: 'GameTDB lists GameCube games with the Wii');
      expect(GameTdb.platformOf('wiiu'), 'wiiu');
      expect(GameTdb.platformOf('ds'), 'ds');
      expect(GameTdb.platformOf('3ds'), '3ds');
      expect(GameTdb.pagePlatform('wiiu'), 'WiiU');
      expect(GameTdb.pagePlatform('3ds'), '3DS');
      final parsed = GameTdb.parsePage('''
<img src="https://art.gametdb.com/wii/cover/EN/RSBP01.png">
<img src="https://art.gametdb.com/wii/coverfullHQ/FR/RSBP01.png">
<img src="https://art.gametdb.com/wii/cover/EN/SUKP01.png">
<img src="https://art.gametdb.com/wii/disc/EN/RSBP01.png">''', 'RSBP01');
      expect(parsed.candidates.map((c) => c.type), ['gametdb:cover', 'gametdb:coverfullHQ', 'gametdb:disc']);
      final sheet = parsed.candidates[1];
      expect((sheet.width, sheet.height, sheet.region, sheet.kind), (1024, 680, 'fr', GameBoxMediaKind.full));
      expect(GameBoxCandidateRanking.isThumbnail(parsed.candidates.first), isTrue, reason: 'the 160 × 224 front');
      expect(GameBoxWrapLayout.forProfile(GameBoxProfile.forSystem('wii'))!.matches(const Size(1024, 680)), isTrue);
    });

    group('search', () {
      late _FP fp;
      final served = <String, Uint8List>{};
      setUp(() {
        SharedPreferences.setMockInitialValues({});
        GameBoxMediaChecker.clearCache();
        GameBoxMediaService.clearPageCache();
        fp = _FP(dir.path);
        served.clear();
        GameBoxMediaService.debugFetch = (url) async => served[url];
      });
      tearDown(() => GameBoxMediaService.debugFetch = null);

      testWidgets('Brawl from its ISO: the edition is the player\'s, the HQ sheet beats the thumbnail', (tester) async {
        await tester.runAsync(() async {
          final iso = await file('Super Smash Bros. Brawl.iso', _discHeader('RSBP01'));
          final ctx = GameBoxSearchContext(
            game: _game('Super Smash Bros. Brawl.iso', 'Super Smash Bros. Brawl', 'wii', romPath: iso),
            systemFolder: 'wii', fileProvider: fp, profile: GameBoxProfile.forSystem('wii'), appSystemId: 'wii',
          );
          served['${GameTdb.site}/Wii/RSBP01'] = Uint8List.fromList('''
<img src="https://art.gametdb.com/wii/cover/FR/RSBP01.png">
<img src="https://art.gametdb.com/wii/coverfullHQ/FR/RSBP01.png">
<img src="https://art.gametdb.com/wii/coverfullHQ/US/RSBE01.png">'''.codeUnits);
          served['https://art.gametdb.com/wii/cover/FR/RSBP01.png'] = await _png(160, 224, const Color(0xFF3050A0));
          served['https://art.gametdb.com/wii/coverfullHQ/FR/RSBP01.png'] = await _png(1024, 680, const Color(0xFF3050A0));
          final search = await GameBoxMediaService.search(ctx, providers: const {GameBoxProvider.gametdb});
          expect(search.statuses[GameBoxProvider.gametdb], GameBoxSourceStatus.ok);
          expect(search.hint.productId, 'RSBP01');
          expect(search.hint.gameRegions, ['eu']);
          expect(search.of(GameBoxMediaKind.full).single.byProduct, isTrue);
          final report = await GameBoxMediaService.complete(ctx, search: search, kinds: {GameBoxMediaKind.front});
          expect(report.outcomes[GameBoxMediaKind.front], GameBoxFaceOutcome.added);
          final media = GameBoxMediaStore(fp).read(ctx.game, 'wii');
          expect(media.full, isNotNull, reason: 'the HQ sheet, not the 160 px thumbnail');
          expect(media.front, isNull);
          expect(await GameBoxMediaService.facesToComplete(ctx, {GameBoxMediaKind.front, GameBoxMediaKind.back, GameBoxMediaKind.spine}),
              isEmpty, reason: 'the sheet holds every face');
          final art = GameBoxArtSet(media: media, title: 'Brawl').art(detailed: false, profile: ctx.profile);
          expect(art.front, isNotNull);
          expect(art.frontWindow, GameBoxWrapLayout.forProfile(ctx.profile)!.split(const Size(1024, 680))!.front);
        });
      });

      testWidgets('a DS game without a readable ROM: found by title, never taken for the product', (tester) async {
        await tester.runAsync(() async {
          final ctx = GameBoxSearchContext(
            game: _game('Mario Kart DS.nds', 'Mario Kart DS', 'ds'),
            systemFolder: 'ds', fileProvider: fp, profile: GameBoxProfile.forSystem('ds'), appSystemId: 'ds',
          );
          served['${GameTdb.site}/dstdb.txt?LANG=EN'] = Uint8List.fromList(
              'TITLES = https://www.gametdb.com (type: DS)\nAMCE = Mario Kart DS\nAMCP = Mario Kart DS\nA2DE = Other\n'.codeUnits);
          served['${GameTdb.site}/DS/AMCP'] =
              Uint8List.fromList('<img src="https://art.gametdb.com/ds/coverHQ/FR/AMCP.jpg">'.codeUnits);
          final search = await GameBoxMediaService.search(ctx, providers: const {GameBoxProvider.gametdb});
          final fronts = search.of(GameBoxMediaKind.front);
          expect(fronts.map((c) => c.productId), ['AMCP']);
          expect(fronts.single.byProduct, isFalse);
          expect((fronts.single.width, fronts.single.height), (768, 680));
        });
      });

      testWidgets('a title shared by a GameCube and a Wii game keeps the console of the player', (tester) async {
        await tester.runAsync(() async {
          served['${GameTdb.site}/wiitdb.txt?LANG=EN'] = Uint8List.fromList(
              'TITLES = https://www.gametdb.com (type: Wii)\nGZLP01 = The Legend of Zelda: Twilight Princess\n'
                      'RZDP01 = The Legend of Zelda: Twilight Princess\n'
                  .codeUnits);
          final pages = <String>[];
          GameBoxMediaService.debugFetch = (url) async {
            if (url.contains('/Wii/')) pages.add(url.split('/').last);
            return served[url];
          };
          for (final (system, expected) in [('gc', 'GZLP01'), ('wii', 'RZDP01')]) {
            pages.clear();
            final ctx = GameBoxSearchContext(
              game: _game('Twilight Princess.rvz', 'The Legend of Zelda: Twilight Princess', system),
              systemFolder: system, fileProvider: fp, profile: GameBoxProfile.forSystem(system), appSystemId: system,
            );
            await GameBoxMediaService.search(ctx, providers: const {GameBoxProvider.gametdb});
            expect(pages, [expected], reason: system);
          }
        });
      });
    });

    testWidgets('a kept thumbnail gives way on screen to the sheet of the same language, never to another one',
        (tester) async {
      await tester.runAsync(() async {
        final fp = _FP(dir.path);
        final game = _game('Brawl.iso', 'Brawl', 'wii');
        final store = GameBoxMediaStore(fp);
        Future<void> write(String folder, Uint8List bytes) async {
          File(store.canonicalPath(game, 'wii', folder, 'png'))
            ..createSync(recursive: true)
            ..writeAsBytesSync(bytes);
        }

        await write('box2d', await _png(160, 224, const Color(0xFF3050A0)));
        await write(GameBoxMediaFolders.full, await _png(1024, 680, const Color(0xFF3050A0)));
        final profile = GameBoxProfile.forSystem('wii');
        final sheetFront = GameBoxWrapLayout.forProfile(profile)!.split(const Size(1024, 680))!.front;
        for (final (frontRegion, sheetRegion, fromSheet) in [('fr', 'fr', true), ('fr', 'uk', false), ('uk', 'eu', true)]) {
          await store.writeManifest(
            game,
            'wii',
            GameBoxManifest.local().copyWith(faces: {
              GameBoxMediaKind.front: GameBoxFaceRecord(provider: 'gametdb', type: 'gametdb:cover', region: frontRegion),
              GameBoxMediaKind.full: GameBoxFaceRecord(provider: 'gametdb', type: 'gametdb:coverfullHQ', region: sheetRegion),
            }),
          );
          final art = GameBoxArtSet(media: store.read(game, 'wii'), title: 'Brawl').art(detailed: false, profile: profile);
          expect(art.frontWindow == sheetFront, fromSheet, reason: 'front $frontRegion, sheet $sheetRegion');
        }
      });
    });
  });
}
