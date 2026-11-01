// Box media from several sources, checked before adoption, with their
// provenance (docs/game-box-3d.md § 14, § 15).
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/services/game_box/game_box_art_fit.dart';
import 'package:neostation/services/game_box/game_box_fetcher.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
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

Future<Uint8List> _png(int w, int h, {Color? flat}) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  final s = Size(w.toDouble(), h.toDouble());
  if (flat != null) {
    c.drawRect(Offset.zero & s, Paint()..color = flat);
  } else {
    c.drawRect(Offset.zero & s, Paint()..color = const Color(0xFF203060));
    c.drawCircle(Offset(w / 2, h / 2), w / 3, Paint()..color = const Color(0xFFE0C060));
    c.drawRect(Rect.fromLTWH(4, h - 40.0, 30, 30), Paint()..color = Colors.white);
  }
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

// A trimmed GameTDB page: art links of the game and of other games, and the
// case row (the markup GameTDB uses, 1 Nov 2026).
const _page = '''
<td class='head' align='right'  valign='top'>case
</td><td  valign='top'>
<table border='1' width='16' height='16' bgcolor='#ff0000' >
</table>
<a href="https://art.gametdb.com/ps3/coverHQ/US/BLUS30902.jpg?1">x</a>
<img src="https://art.gametdb.com/ps3/cover/US/BLUS30902.jpg?2">
<a href="https://art.gametdb.com/ps3/backHQ/US/BLUS30902.jpg">x</a>
<a href="https://art.gametdb.com/ps3/coverfullHQ/US/BLUS30902.jpg">x</a>
<a href="https://art.gametdb.com/ps3/coverHQB/US/BLUS30902.jpg">alternate</a>
<a href="https://art.gametdb.com/ps3/discM/EN/BLUS30902.png">disc</a>
<a href="https://art.gametdb.com/ps3/box/US/BLUS30902.png">3D render</a>
<img src="https://art.gametdb.com/ps3/cover/US/BLUS31153.jpg">
''';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  group('GameTDB', () {
    test('a game page gives its covers, backs, sheets and discs, never its 3D render', () {
      final r = GameTdb.parsePage(_page, 'BLUS30902');
      final types = r.candidates.map((c) => c.type).toList();
      expect(types, containsAll(['gametdb:coverHQ', 'gametdb:cover', 'gametdb:backHQ', 'gametdb:coverfullHQ', 'gametdb:discM']));
      expect(types, isNot(contains('gametdb:box')));
      expect(r.candidates.where((c) => c.productId != 'BLUS30902'), isEmpty, reason: 'other games left out');
      final front = r.candidates.firstWhere((c) => c.type == 'gametdb:coverHQ');
      expect(front.kind, GameBoxMediaKind.front);
      expect(front.region, 'us');
      expect(front.quality, 3);
      expect((front.width, front.height), (928, 1080));
      expect(front.url, 'https://art.gametdb.com/ps3/coverHQ/US/BLUS30902.jpg');
      final sheet = r.candidates.firstWhere((c) => c.type == 'gametdb:coverfullHQ');
      expect((sheet.kind, sheet.nature), (GameBoxMediaKind.full, GameBoxArtNature.wrap));
      expect(r.candidates.firstWhere((c) => c.type == 'gametdb:coverHQB').edition, 'B');
      expect(r.candidates.firstWhere((c) => c.type == 'gametdb:discM').kind, GameBoxMediaKind.support);
      expect(r.caseColor, 'ff0000');
    });

    test('a Switch product code is found by exact title only', () {
      const txt = 'TITLES = https://www.gametdb.com (type: Switch language: EN)\n'
          'AR3XA = Hogwarts Legacy\n'
          'AR3XD = Hogwarts Legacy: Digital Deluxe Edition\n'
          'AUZPA = Super Mario 3D World + Bowser\'s Fury\n'
          'A98EA = Matisse\'s 3D World\n';
      expect(GameTdb.idsForTitle(txt, 'Hogwarts Legacy [0100F7E00C70E000][v0]'), ['AR3XA']);
      expect(GameTdb.idsForTitle(txt, 'Super Mario 3D World + Bowser’s Fury'), ['AUZPA']);
      expect(GameTdb.idsForTitle(txt, 'Hogwarts'), isEmpty);
    });

    test('PS3 serial regions', () {
      expect(GameTdb.regionsOfPs3Serial('BCES00510'), ['eu']);
      expect(GameTdb.regionsOfPs3Serial('BLUS30902'), ['us']);
      expect(GameTdb.regionsOfPs3Serial('BLJM61149'), ['jp']);
      expect(GameTdb.regionsOfPs3Serial('0100F7E00C70E000'), isEmpty);
    });
  });

  test('MobyGames cover groups become candidates with their country and size', () {
    final json = jsonDecode('''{"cover_groups":[{"comments":"Platinum","countries":["France"],"covers":[
      {"scan_of":"Front Cover","image":"https://cdn.mobygames.com/covers/1.jpg","width":1500,"height":1745},
      {"scan_of":"Back Cover","image":"https://cdn.mobygames.com/covers/2.jpg","width":1500,"height":1745},
      {"scan_of":"Spine/Sides","image":"https://cdn.mobygames.com/covers/3.jpg","width":200,"height":1745},
      {"scan_of":"Manual","image":"https://cdn.mobygames.com/covers/4.jpg","width":900,"height":900}]}]}''') as Map<String, dynamic>;
    final c = MobyGames.parseCovers(json, gameId: '42');
    expect(c.map((e) => e.kind), [GameBoxMediaKind.front, GameBoxMediaKind.back, GameBoxMediaKind.spine]);
    expect(c.first.region, 'fr');
    expect(c.first.edition, 'Platinum');
    expect((c.first.width, c.first.height), (1500, 1745));
    expect(c.first.provider, GameBoxProvider.mobygames);
  });

  test('ScreenScraper scans are downloaded at full size', () {
    const url = 'https://api.screenscraper.fr/api2/mediaJeu.php?devid=x&jeuid=1&media=box-2D-back(eu)&maxwidth=640&maxheight=480';
    final full = Uri.parse(ScreenScraperBoxSource.fullSize(url));
    expect(full.queryParameters.containsKey('maxwidth'), isFalse);
    expect(full.queryParameters.containsKey('maxheight'), isFalse);
    expect(full.queryParameters['media'], 'box-2D-back(eu)');
  });

  group('ranking: the right edition before a larger scan', () {
    GameBoxCandidate cand(GameBoxProvider pr, String region, int quality, int w, {String? product, bool byProduct = false}) =>
        GameBoxCandidate(
          provider: pr,
          kind: GameBoxMediaKind.back,
          type: '${pr.name}:back',
          identity: '${pr.name}:$region:$quality',
          region: region,
          quality: quality,
          width: w,
          height: (w * 1.6).round(),
          productId: product,
          byProduct: byProduct,
        );

    test('a French copy prefers a small French back over a large US one', () {
      const hint = GameBoxEditionHint(gameRegions: ['fr', 'eu']);
      final ranked = GameBoxCandidateRanking.rank([
        cand(GameBoxProvider.mobygames, 'us', 3, 4000),
        cand(GameBoxProvider.screenscraper, 'fr', 2, 350),
        cand(GameBoxProvider.gametdb, 'uk', 3, 1166),
      ], hint);
      expect(ranked.map((c) => c.region).toList(), ['fr', 'uk', 'us']);
    });

    test('the player\'s product code wins, then quality within the edition', () {
      const hint = GameBoxEditionHint(gameRegions: ['eu'], productId: 'BCES00510');
      final ranked = GameBoxCandidateRanking.rank([
        cand(GameBoxProvider.screenscraper, 'eu', 2, 900),
        cand(GameBoxProvider.gametdb, 'fr', 3, 928, product: 'BCES00510', byProduct: true),
        cand(GameBoxProvider.gametdb, 'fr', 2, 350, product: 'BCES00510', byProduct: true),
      ], hint);
      expect(ranked.first.quality, 3);
      expect(ranked.first.productId, 'BCES00510');
      expect(ranked[1].productId, 'BCES00510');
    });

    test('3D renders and catalogue art are never candidates', () {
      final ranked = GameBoxCandidateRanking.rank([
        const GameBoxCandidate(
          provider: GameBoxProvider.gametdb, kind: GameBoxMediaKind.front, type: 'gametdb:box',
          identity: 'r', nature: GameBoxArtNature.render3d),
      ], const GameBoxEditionHint());
      expect(ranked, isEmpty);
    });
  });

  group('manifest v2', () {
    test('version 1 manifests are still read; face records, rejections and the case survive a round trip', () {
      final v1 = GameBoxManifest.fromJson({
        'version': 1,
        'screenscraper': {'systemId': '225', 'gameId': '9'},
        'matchedBy': 'fileName',
        'media': [],
      });
      expect(v1, isNotNull);
      final m = v1!.copyWith(
        faces: {
          GameBoxMediaKind.back: GameBoxFaceRecord(
            provider: 'gametdb', type: 'gametdb:backHQ', region: 'uk', productId: 'AUZPA',
            width: 1166, height: 1888, md5: 'abc', bytes: 10, attribution: 'GameTDB (gametdb.com)'),
          GameBoxMediaKind.front: GameBoxFaceRecord(provider: 'manual', type: 'manual:import', manual: true,
              note: 'The Cover Project — retail cover'),
        },
        rejected: {'screenscraper:md5:00ff00'},
        identifiedCase: const GameBoxIdentifiedCase(color: Color(0xFFFF0000), source: 'gametdb:BLUS30902'),
      );
      final json = jsonEncode(m.toJson());
      expect(json, isNot(contains('http')));
      final back = GameBoxManifest.fromJson(jsonDecode(json) as Map<String, dynamic>)!;
      expect(back.faces[GameBoxMediaKind.back]!.type, 'gametdb:backHQ');
      expect(back.faces[GameBoxMediaKind.back]!.width, 1166);
      expect(back.faces[GameBoxMediaKind.front]!.manual, isTrue);
      expect(back.rejected, {'screenscraper:md5:00ff00'});
      expect(back.identifiedCase!.color, const Color(0xFFFF0000));
      expect(back.screenScraperGameId, '9');
    });
  });

  group('adoption', () {
    late Directory dir;
    late GameBoxSearchContext ctx;
    late GameBoxMediaStore store;
    final fetched = <String>[];
    final served = <String, Uint8List>{};

    setUp(() {
      dir = Directory.systemTemp.createTempSync('gbsrc');
      final fp = _FP(dir.path);
      const game = GameModel(
        romname: 'Super Mario 3D World.nsp', realname: 'Super Mario 3D World + Bowser\'s Fury',
        name: 'Super Mario 3D World + Bowser\'s Fury', year: '', developer: '', publisher: '', genre: '',
        players: '', rating: 0, systemId: 'switch', systemFolderName: 'switch', titleId: '010028600EBDA000',
      );
      ctx = GameBoxSearchContext(
        game: game, systemFolder: 'switch', fileProvider: fp,
        profile: GameBoxProfile.forSystem('switch'), appSystemId: 'switch',
      );
      store = GameBoxMediaStore(fp);
      fetched.clear();
      served.clear();
      GameBoxMediaService.debugFetch = (url) async {
        fetched.add(url);
        return served[url];
      };
      GameBoxMediaChecker.clearCache();
    });

    tearDown(() {
      GameBoxMediaService.debugFetch = null;
      GameBoxMediaService.debugScreenScraper = null;
      dir.deleteSync(recursive: true);
    });

    GameBoxCandidate back(String url, String identity, {String region = 'au', GameBoxProvider provider = GameBoxProvider.screenscraper}) =>
        GameBoxCandidate(
          provider: provider, kind: GameBoxMediaKind.back, type: '${provider.name}:back', identity: identity,
          region: region, url: url, format: 'png',
        );

    testWidgets('the green back is refused, remembered, and another source fills the face', (tester) async {
      await tester.runAsync(() async {
        served['ss://back-au'] = await _png(1166, 1888, flat: const Color(0xFF00FF00));
        served['https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg'] = await _png(1166, 1888);
        // The player's copy is Australian: ScreenScraper's AU back comes first.
        final search = GameBoxSearch(
          candidates: {
            GameBoxMediaKind.back: [
              back('ss://back-au', 'screenscraper:md5:green'),
              back('https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg', 'gametdb:switch/backHQ/EN/AUZPA',
                  region: 'uk', provider: GameBoxProvider.gametdb),
            ],
          },
          statuses: const {GameBoxProvider.screenscraper: GameBoxSourceStatus.ok},
          hint: const GameBoxEditionHint(gameRegions: ['au']),
        );
        final report = await GameBoxMediaService.complete(ctx, search: search);
        expect(report.outcomes[GameBoxMediaKind.back], GameBoxFaceOutcome.added);
        expect(report.refusals.single.$1, GameBoxMediaKind.back);
        expect(report.refusals.single.$2, GameBoxProvider.screenscraper);
        expect(report.refusals.single.$3, GameBoxImageVerdict.uniform);
        expect(fetched.first, 'ss://back-au', reason: 'the edition of the copy was tried first');
        final local = store.read(ctx.game, 'switch');
        expect(local.manifest!.rejected, contains('screenscraper:md5:green'));
        final record = local.recordOf(GameBoxMediaKind.back)!;
        expect((record.provider, record.type, record.region), ('gametdb', 'gametdb:back', 'uk'));
        expect((record.width, record.height), (1166, 1888));
        expect(record.attribution, contains('GameTDB'));
        expect(record.md5, isNotNull);
        expect((await GameBoxMediaChecker.checkFile(local.back!)).ok, isTrue);
        expect(report.changedPaths, contains(local.back!));
        expect(report.outcomes[GameBoxMediaKind.front], GameBoxFaceOutcome.missing);

        // A second run never downloads the refused back again.
        fetched.clear();
        File(local.back!).deleteSync();
        await GameBoxMediaService.complete(ctx, search: search);
        expect(fetched, isNot(contains('ss://back-au')));
        expect(fetched, contains('https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg'));
      });
    });

    testWidgets('an icon used as front is replaced by a cover; the back follows the same edition', (tester) async {
      await tester.runAsync(() async {
        final iconPath = store.canonicalPath(ctx.game, 'switch', 'box2d', 'png');
        File(iconPath)
          ..createSync(recursive: true)
          ..writeAsBytesSync(await _png(256, 256));
        served['https://art.gametdb.com/switch/coverHQ/EN/AUZPA.jpg'] = await _png(1166, 1888);
        served['https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg'] = await _png(1166, 1888);
        served['https://cdn.example/back-us.jpg'] = await _png(1166, 1888);
        GameBoxCandidate tdb(GameBoxMediaKind kind, String type) => GameBoxCandidate(
              provider: GameBoxProvider.gametdb, kind: kind, type: 'gametdb:$type',
              identity: 'gametdb:switch/$type/EN/AUZPA', region: 'uk', productId: 'AUZPA', quality: 3,
              url: 'https://art.gametdb.com/switch/$type/EN/AUZPA.jpg', width: 1166, height: 1888);
        final search = GameBoxSearch(
          candidates: {
            GameBoxMediaKind.front: [tdb(GameBoxMediaKind.front, 'coverHQ')],
            GameBoxMediaKind.back: [
              // Ranked first on its own (larger), but another product.
              const GameBoxCandidate(
                provider: GameBoxProvider.mobygames, kind: GameBoxMediaKind.back, type: 'mobygames:Back Cover',
                identity: 'mobygames:/back-us', region: 'us', productId: 'moby:1/0', quality: 3,
                url: 'https://cdn.example/back-us.jpg', width: 3000, height: 4860),
              tdb(GameBoxMediaKind.back, 'backHQ'),
            ],
          },
          statuses: const {},
          hint: const GameBoxEditionHint(),
        );
        final report = await GameBoxMediaService.complete(ctx, search: search);
        expect(report.outcomes[GameBoxMediaKind.front], GameBoxFaceOutcome.improved, reason: 'the icon was not a cover');
        expect(report.frontChanged, isTrue);
        final local = store.read(ctx.game, 'switch');
        expect(local.recordOf(GameBoxMediaKind.front)!.productId, 'AUZPA');
        expect(local.recordOf(GameBoxMediaKind.back)!.productId, 'AUZPA', reason: 'one coherent edition');
        expect(fetched, isNot(contains('https://cdn.example/back-us.jpg')));
      });
    });

    testWidgets('a face chosen by hand is never replaced by a completion', (tester) async {
      await tester.runAsync(() async {
        final mine = File('${dir.path}/mine.png')..writeAsBytesSync(await _png(1166, 1888));
        final imported = await GameBoxMediaService.importFile(ctx, GameBoxMediaKind.back, mine.path,
            note: 'The Cover Project — retail cover');
        expect(imported.ok, isTrue);
        final before = File(imported.path!).readAsBytesSync();
        served['https://x/back.png'] = await _png(1166, 1888);
        final report = await GameBoxMediaService.complete(ctx,
            search: GameBoxSearch(
              candidates: {GameBoxMediaKind.back: [back('https://x/back.png', 'x', provider: GameBoxProvider.gametdb)]},
              statuses: const {},
              hint: const GameBoxEditionHint(),
            ));
        expect(report.outcomes[GameBoxMediaKind.back], GameBoxFaceOutcome.manualKept);
        expect(File(imported.path!).readAsBytesSync(), before);
        expect(fetched, isEmpty);
        final record = store.read(ctx.game, 'switch').recordOf(GameBoxMediaKind.back)!;
        expect(record.manual, isTrue);
        expect(record.note, 'The Cover Project — retail cover');
      });
    });

    testWidgets('an imported uniform picture or a 3D render is refused', (tester) async {
      await tester.runAsync(() async {
        final green = File('${dir.path}/green.png')..writeAsBytesSync(await _png(600, 900, flat: const Color(0xFF00FF00)));
        final r1 = await GameBoxMediaService.importFile(ctx, GameBoxMediaKind.back, green.path);
        expect(r1.ok, isFalse);
        expect(r1.verdict, GameBoxImageVerdict.uniform);
        // A landscape picture is not a Switch back.
        final wide = File('${dir.path}/wide.png')..writeAsBytesSync(await _png(1280, 720));
        final r2 = await GameBoxMediaService.importFile(ctx, GameBoxMediaKind.back, wide.path);
        expect(r2.ok, isFalse);
        expect(store.read(ctx.game, 'switch').back, isNull);
      });
    });

    testWidgets('a full sheet is kept only with a verified layout', (tester) async {
      await tester.runAsync(() async {
        served['https://x/full.png'] = await _png(2454, 1888);
        served['https://x/odd.png'] = await _png(2000, 1888);
        GameBoxCandidate full(String url) => GameBoxCandidate(
              provider: GameBoxProvider.gametdb, kind: GameBoxMediaKind.full, type: 'gametdb:coverfullHQ',
              identity: url, nature: GameBoxArtNature.wrap, url: url, format: 'png');
        expect((await GameBoxMediaService.adopt(ctx, full('https://x/odd.png'))).ok, isFalse);
        final ok = await GameBoxMediaService.adopt(ctx, full('https://x/full.png'));
        expect(ok.ok, isTrue);
        expect(p.basename(p.dirname(ok.path!)), GameBoxMediaFolders.full);
        expect(store.read(ctx.game, 'switch').full, ok.path);
      });
    });

    testWidgets('a ScreenScraper scan becomes the default edition of its face; another source does not', (tester) async {
      await tester.runAsync(() async {
        served['ss://back-eu'] = await _png(1166, 1888);
        served['https://x/tdb-back.png'] = await _png(1166, 1888);
        expect((await GameBoxMediaService.adopt(ctx, back('ss://back-eu', 'screenscraper:md5:abc', region: 'eu'))).ok,
            isTrue);
        expect(store.read(ctx.game, 'switch').manifest!.defaults[GameBoxMediaKind.back], 'md5:abc');
        expect(store.read(ctx.game, 'switch').recordOf(GameBoxMediaKind.back)!.region, 'eu');
        expect((await GameBoxMediaService.adopt(ctx,
                back('https://x/tdb-back.png', 'gametdb:x', region: 'uk', provider: GameBoxProvider.gametdb))).ok,
            isTrue);
        expect(store.read(ctx.game, 'switch').manifest!.defaults[GameBoxMediaKind.back], isNull);
      });
    });

    test('the old ScreenScraper fetch maps its statuses', () async {
      GameBoxMediaService.debugScreenScraper = (_) async => (null, GameBoxSourceStatus.needsLogin);
      final search = await GameBoxMediaService.search(ctx, providers: const {GameBoxProvider.screenscraper});
      expect(search.statuses[GameBoxProvider.screenscraper], GameBoxSourceStatus.needsLogin);
      expect(GameBoxFetchStatus.values, contains(GameBoxFetchStatus.needsLogin));
    });
  });
}
