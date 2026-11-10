// "Box media": complete the faces from ScreenScraper and GameTDB, with the
// summary and the source of each face (docs/game-box-3d.md § 14).
import 'dart:io';
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_media_sheet.dart';
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
  c.drawRect(Offset.zero & s, Paint()..color = flat ?? const Color(0xFFE60012));
  if (flat == null) c.drawCircle(Offset(w / 2, h / 2), w / 3, Paint()..color = const Color(0xFF2040A0));
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

void main() {
  testWidgets('complete: the icon front and the green back are replaced, the summary names each face', (tester) async {
    SharedPreferences.setMockInitialValues({});
    GameBoxMediaChecker.clearCache();
    final dir = Directory.systemTemp.createTempSync('gbsheet');
    addTearDown(() => dir.deleteSync(recursive: true));
    final fp = _FP(dir.path);
    const game = GameModel(
      romname: 'Super Mario 3D World.nsp', realname: 'Super Mario 3D World + Bowser\'s Fury',
      name: 'Super Mario 3D World + Bowser\'s Fury', year: '', developer: '', publisher: '', genre: '',
      players: '', rating: 0, systemId: 'switch', systemFolderName: 'switch',
    );
    final ctx = GameBoxSearchContext(
      game: game, systemFolder: 'switch', fileProvider: fp, profile: GameBoxProfile.forSystem('switch'),
      appSystemId: 'switch',
    );
    final store = GameBoxMediaStore(fp);
    final served = <String, Uint8List>{};
    await tester.runAsync(() async {
      File(store.canonicalPath(game, 'switch', 'box2d', 'jpg'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(await _png(256, 256)); // the title icon copied at import
      File(store.canonicalPath(game, 'switch', GameBoxMediaFolders.back, 'png'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(await _png(233, 377, flat: const Color(0xFF00FF00)));
      served['ss://back-au'] = await _png(233, 377, flat: const Color(0xFF00FF00));
      served['https://art.gametdb.com/switch/coverHQ/EN/AUZPA.jpg'] = await _png(1166, 1888);
      served['https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg'] = await _png(1166, 1888);
      served['https://art.gametdb.com/switch/coverfullHQ/EN/AUZPA.jpg'] = await _png(2454, 1888);
    });
    served['${GameTdb.site}/switchtdb.txt?LANG=EN'] = Uint8List.fromList(
        'TITLES = https://www.gametdb.com (type: Switch)\nAUZPA = Super Mario 3D World + Bowser\'s Fury\n'.codeUnits);
    served['${GameTdb.site}/Switch/AUZPA'] = Uint8List.fromList('''
<a href="https://art.gametdb.com/switch/coverHQ/EN/AUZPA.jpg">c</a>
<a href="https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg">b</a>
<a href="https://art.gametdb.com/switch/coverfullHQ/EN/AUZPA.jpg">f</a>
<a href="https://art.gametdb.com/switch/box/EN/AUZPA.png">render</a>'''.codeUnits);
    final fetched = <String>[];
    GameBoxMediaService.debugFetch = (url) async {
      fetched.add(url);
      return served[url];
    };
    GameBoxMediaService.debugScreenScraper = (_) async => (
          GameBoxScreenScraperListing(
            systemId: '225',
            gameId: '42',
            matchedBy: GameBoxMatch.fileName,
            entries: const [],
            gameRegions: const ['au'],
            candidates: const [
              GameBoxCandidate(
                provider: GameBoxProvider.screenscraper, kind: GameBoxMediaKind.back,
                type: 'screenscraper:box-2D-back', identity: 'screenscraper:md5:green', region: 'au',
                url: 'ss://back-au', format: 'png'),
            ],
          ),
          GameBoxSourceStatus.ok,
        );
    addTearDown(() {
      GameBoxMediaService.debugFetch = null;
      GameBoxMediaService.debugScreenScraper = null;
    });

    // Tall enough for the whole sheet (its list builds visible rows only).
    tester.view.physicalSize = const Size(800, 2000);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    late GameBoxMediaChanges changes;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: ElevatedButton(
              onPressed: () async => changes = await GameBoxMediaSheet.show(context, ctx),
              child: const Text('media'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('media'));
    await tester.pumpAndSettle();
    expect(find.text('Box media'), findsOneWidget);
    // The checks of the files on disk: file reads and decodes run outside
    // fake time, one step after the other.
    for (var i = 0; i < 8; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
      await tester.pump();
    }
    expect(find.textContaining('Not a cover'), findsOneWidget, reason: 'the icon front');
    expect(find.textContaining('Refused — one flat colour'), findsOneWidget, reason: 'the green back');

    final state = tester.state<GameBoxMediaSheetState>(find.byType(GameBoxMediaSheet));
    await tester.runAsync(state.complete);
    await tester.pumpAndSettle();
    expect(find.textContaining('Refused'), findsNothing, reason: 'the replaced back never shows the old verdict');
    for (var i = 0; i < 8; i++) {
      await tester.runAsync(() => Future<void>.delayed(const Duration(milliseconds: 50)));
      await tester.pump();
    }
    expect(find.text('Scan in place'), findsNWidgets(2), reason: 'new front and back checked');
    expect(find.textContaining('GameTDB · backHQ · United Kingdom · 1166 × 1888 px'), findsOneWidget);
    expect(find.textContaining('Added: Spine'), findsOneWidget);
    expect(find.textContaining('Replaced: Front cover, Back cover'), findsOneWidget);
    // Once the GameTDB front (AUZPA) is adopted, the back of the same
    // product comes first: ScreenScraper's green back is never downloaded.
    expect(fetched, isNot(contains('ss://back-au')));
    expect(find.textContaining('picture refused'), findsNothing);
    expect(find.textContaining('ScreenScraper: answered'), findsOneWidget);
    expect(find.textContaining('GameTDB: answered'), findsOneWidget);
    expect(find.textContaining('MobyGames: not configured'), findsOneWidget);
    final local = store.read(game, 'switch');
    expect(local.recordOf(GameBoxMediaKind.front)!.type, 'gametdb:coverHQ');
    expect(local.recordOf(GameBoxMediaKind.back)!.type, 'gametdb:backHQ');
    expect(local.recordOf(GameBoxMediaKind.full)!.type, 'gametdb:coverfullHQ', reason: 'the spine comes from the sheet');
    expect(local.manifest!.screenScraperGameId, '42');

    await tester.tap(find.text('Close'));
    await tester.pumpAndSettle();
    expect(changes.frontChanged, isTrue);
    expect(changes.paths, containsAll([local.front!, local.back!, local.full!]));
  });
}
