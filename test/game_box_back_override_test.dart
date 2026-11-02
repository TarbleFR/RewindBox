// "Edit the back" and "Restore the automatic back" (docs/game-box-3d.md
// § 21), on Bladestorm (PS3, BLES00113, Europe): the GameTDB back of this
// edition is a 160 × 184 thumbnail; the player imports a readable back,
// framed on its panel. It stays first after a restart and a new scrape,
// changes only this game's back, and the automatic back comes back intact.
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/screens/game_box/game_box_back_editor.dart';
import 'package:neostation/services/game_box/game_box_back_override.dart';
import 'package:neostation/services/game_box/game_box_batch.dart';
import 'package:neostation/services/game_box/game_box_enhance.dart';
import 'package:neostation/services/game_box/game_box_fetcher.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/game_box/game_box_profile.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
import 'package:neostation/widgets/game_box/game_box_scene.dart';
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

/// A picture with print-like detail: bands of a colour and dark strokes.
Future<Uint8List> _picture(int w, int h, Color color, {Rect? panel}) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  c.drawRect(Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble()), Paint()..color = const Color(0xFFF2F2F2));
  final area = panel ?? Rect.fromLTWH(0, 0, w.toDouble(), h.toDouble());
  c.drawRect(area, Paint()..color = color);
  for (var i = 0; i < 12; i++) {
    c.drawRect(
      Rect.fromLTWH(area.left + area.width * 0.1, area.top + area.height * (0.1 + i * 0.06), area.width * 0.7, 3),
      Paint()..color = const Color(0xFF101010),
    );
  }
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

GameModel _game(String rom, String name, {String? titleId}) => GameModel(
      romname: rom, realname: name, name: name, year: '2007', developer: 'Koei', publisher: 'Koei',
      genre: 'Action', players: '1', rating: 0, systemId: 'ps3', systemFolderName: 'ps3', titleId: titleId,
    );

String _md5(String path) => md5.convert(File(path).readAsBytesSync()).toString();

void main() {
  late Directory dir;
  late _FP fp;
  late GameBoxMediaStore store;
  final bladestorm = _game('Bladestorm.rpcs3', 'Bladestorm: The Hundred Years\' War', titleId: 'BLES00113');
  final other = _game('Heavenly Sword.rpcs3', 'Heavenly Sword', titleId: 'BCES00078');
  GameBoxSearchContext ctxOf(GameModel g) => GameBoxSearchContext(
        game: g, systemFolder: 'ps3', fileProvider: fp, profile: GameBoxProfile.forSystem('ps3'), appSystemId: 'ps3',
      );

  // The library as scraped: GameTDB's EN front and its 160 × 184 back.
  Future<String> scraped(GameModel g, Color color) async {
    final front = store.canonicalPath(g, 'ps3', 'box2d', 'png');
    File(front)
      ..createSync(recursive: true)
      ..writeAsBytesSync(await _picture(928, 1080, color));
    final back = store.canonicalPath(g, 'ps3', GameBoxMediaFolders.back, 'png');
    File(back)
      ..createSync(recursive: true)
      ..writeAsBytesSync(await _picture(160, 184, color));
    await store.writeManifest(
      g,
      'ps3',
      GameBoxManifest.local().copyWith(faces: {
        GameBoxMediaKind.front: GameBoxFaceRecord(
            provider: 'gametdb', type: 'gametdb:coverHQ', region: 'uk', productId: g.titleId, width: 928, height: 1080),
        GameBoxMediaKind.back: GameBoxFaceRecord(
            provider: 'gametdb', type: 'gametdb:back', region: 'uk', productId: g.titleId, width: 160, height: 184),
      }),
    );
    return back;
  }

  setUp(() {
    SharedPreferences.setMockInitialValues({});
    GameBoxMediaChecker.clearCache();
    GameBoxEnhance.clearMemory();
    dir = Directory.systemTemp.createTempSync('gbback');
    fp = _FP(dir.path);
    store = GameBoxMediaStore(fp);
  });
  tearDown(() {
    GameBoxMediaService.debugFetch = null;
    GameBoxMediaService.debugScreenScraper = null;
    dir.deleteSync(recursive: true);
  });

  testWidgets('Bladestorm: import, frame, restart, new scrape, then the automatic back again', (tester) async {
    await tester.runAsync(() async {
      final autoBack = await scraped(bladestorm, const Color(0xFF8A5A2B));
      final autoMd5 = _md5(autoBack);
      final otherBack = await scraped(other, const Color(0xFF203060));
      final otherMd5 = _md5(otherBack);
      final ctx = ctxOf(bladestorm);

      // Import: a photo of the back with the table around it, framed on the
      // panel (10 % margins).
      const window = Rect.fromLTRB(0.1, 0.05, 0.9, 0.95);
      final photo = await _picture(1200, 1400, const Color(0xFF8A5A2B), panel: const Rect.fromLTRB(120, 70, 1080, 1330));
      final adoption = await GameBoxBackOverride.save(ctx, photo, window: window, source: 'photos');
      expect(adoption.ok, isTrue);
      var media = store.read(bladestorm, 'ps3');
      expect(GameBoxBackOverride.isPlayers(media), isTrue);
      final record = media.recordOf(GameBoxMediaKind.back)!;
      expect(record.type, GameBoxBackOverride.recordType);
      expect(record.note, 'photos');
      expect(record.transforms.single, startsWith('crop:back 0.1000,0.0500,0.8000,0.9000 of 1200x1400'));
      final size = GameBoxImageSize.of(media.back!)!;
      expect((size.width, size.height), (960.0, 1260.0), reason: 'only the back panel is kept');
      final aside = GameBoxBackOverride.keptAside(ctx)!;
      expect(_md5(aside.path), autoMd5, reason: 'the automatic back is kept aside untouched');

      // Restart: nothing in memory, everything read from the disk again.
      GameBoxMediaChecker.clearCache();
      GameBoxImageSize.evict(media.back!);
      GameBoxEnhance.clearMemory();
      media = store.read(bladestorm, 'ps3');
      expect(GameBoxBackOverride.isPlayers(media), isTrue);
      final playersMd5 = _md5(media.back!);

      // A new scrape: GameTDB now has a readable back, ScreenScraper one too;
      // the player's back stays.
      GameBoxMediaService.debugFetch = (url) async {
        if (url.contains('backHQ') || url.contains('ss://')) return _picture(928, 1080, const Color(0xFF00AA00));
        return null;
      };
      GameBoxMediaService.debugScreenScraper = (_) async => (
            GameBoxScreenScraperListing(
              systemId: '59', gameId: '1', matchedBy: GameBoxMatch.serial, entries: const [], gameRegions: const ['eu'],
              candidates: const [
                GameBoxCandidate(
                  provider: GameBoxProvider.screenscraper, kind: GameBoxMediaKind.back,
                  type: 'screenscraper:box-2D-back', identity: 'screenscraper:md5:new', region: 'eu',
                  url: 'ss://back-eu', format: 'png', byProduct: true),
              ],
            ),
            GameBoxSourceStatus.ok,
          );
      expect(await GameBoxMediaService.facesToComplete(ctx, {GameBoxMediaKind.back}, upgradeLanguage: true), isEmpty);
      final report = await GameBoxMediaService.complete(ctx, kinds: {GameBoxMediaKind.back}, upgradeLanguage: true);
      expect(report.outcomes[GameBoxMediaKind.back], GameBoxFaceOutcome.manualKept);
      expect(GameBoxBatch.ownedTypes(store.read(bladestorm, 'ps3')), contains(GameBoxMediaKind.back.screenScraperType),
          reason: 'the ScreenScraper download leaves it alone too');
      expect(_md5(store.read(bladestorm, 'ps3').back!), playersMd5);

      // Only this game's back changed.
      expect(_md5(otherBack), otherMd5);
      expect(GameBoxBackOverride.keptAside(ctxOf(other)), isNull);
      expect(store.read(bladestorm, 'ps3').front, isNotNull);

      // Restore: the GameTDB back and its record, without network.
      GameBoxMediaService.debugFetch = (url) async => fail('no download needed: $url');
      expect(await GameBoxBackOverride.restoreAutomatic(ctx), GameBoxBackRestore.restored);
      media = store.read(bladestorm, 'ps3');
      expect(_md5(media.back!), autoMd5);
      expect(media.recordOf(GameBoxMediaKind.back)!.provider, 'gametdb');
      expect(GameBoxBackOverride.isPlayers(media), isFalse);
      expect(GameBoxBackOverride.keptAside(ctx), isNull);
      expect(await GameBoxBackOverride.restoreAutomatic(ctx), GameBoxBackRestore.nothingToRestore);
      expect(_md5(otherBack), otherMd5);
    });
  });

  testWidgets('a game without automatic back: restoring leaves the reconstructed back', (tester) async {
    await tester.runAsync(() async {
      final ctx = ctxOf(other);
      final adoption = await GameBoxBackOverride.save(ctx, await _picture(700, 800, const Color(0xFF335577)), source: 'files');
      expect(adoption.ok, isTrue);
      expect(store.read(other, 'ps3').recordOf(GameBoxMediaKind.back)!.transforms, isEmpty, reason: 'not framed');
      expect(await GameBoxBackOverride.restoreAutomatic(ctx), GameBoxBackRestore.removed);
      final media = store.read(other, 'ps3');
      expect(media.back, isNull);
      expect(media.recordOf(GameBoxMediaKind.back), isNull);
    });
  });

  testWidgets('a blank picture is refused and nothing changes', (tester) async {
    await tester.runAsync(() async {
      final autoBack = await scraped(bladestorm, const Color(0xFF8A5A2B));
      final before = _md5(autoBack);
      final recorder = ui.PictureRecorder();
      Canvas(recorder).drawRect(const Rect.fromLTWH(0, 0, 400, 400), Paint()..color = Colors.white);
      final image = await recorder.endRecording().toImage(400, 400);
      final blank = (await image.toByteData(format: ui.ImageByteFormat.png))!.buffer.asUint8List();
      final adoption = await GameBoxBackOverride.save(ctxOf(bladestorm), blank, source: 'files');
      expect(adoption.ok, isFalse);
      expect(_md5(store.read(bladestorm, 'ps3').back!), before);
    });
  });

  testWidgets('the editor: a full sheet is framed on its back, the frame moves, the box previews it, save', (tester) async {
    late Uint8List sheet;
    await tester.runAsync(() async {
      await scraped(bladestorm, const Color(0xFF8A5A2B));
      sheet = await _picture(2000, 1080, const Color(0xFF8A5A2B)); // GameTDB coverfullHQ template
    });
    tester.view.physicalSize = const Size(800, 1400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    GameBoxBackEdit? result;
    await tester.pumpWidget(MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: ElevatedButton(
              onPressed: () async {
                result = await Navigator.of(context).push<GameBoxBackEdit>(MaterialPageRoute(
                  builder: (_) => GameBoxBackEditor(context: ctxOf(bladestorm), debugPick: (_) async => sheet),
                ));
              },
              child: const Text('edit'),
            ),
          ),
        ),
      ),
    ));
    await tester.tap(find.text('edit'));
    await tester.pumpAndSettle();
    expect(find.text('Edit the back'), findsOneWidget);
    expect(find.text('From Photos'), findsOneWidget);
    expect(find.text('From Files'), findsOneWidget);

    final state = tester.state<GameBoxBackEditorState>(find.byType(GameBoxBackEditor));
    await tester.runAsync(() => state.pick(true));
    await tester.pump();
    expect(state.window.left, closeTo(0, 0.01), reason: 'the back is the left panel of a PS3 sheet');
    expect(state.window.right, lessThan(0.5));
    final before = state.window;
    await tester.drag(find.byKey(const ValueKey('game_box_back_handle_1.0_1.0')), const Offset(-40, -40));
    await tester.pump();
    expect(state.window.right, lessThan(before.right));
    expect(state.window.bottom, lessThan(before.bottom));
    expect(state.window.left, before.left, reason: 'the opposite corner stays');

    await tester.tap(find.text('Preview on the box'));
    await tester.pump();
    final scene = tester.widget<GameBoxScene>(find.byKey(const ValueKey('game_box_back_preview')));
    expect(scene.art.backWindow, state.window);
    expect(scene.pose.yaw, greaterThan(math.pi / 2), reason: 'seen from the back');

    await tester.runAsync(state.save);
    await tester.pumpAndSettle();
    expect(result?.changed, isTrue);
    expect(result?.message, 'Back saved. It stays first after a restart and a new scrape.');
    final media = store.read(bladestorm, 'ps3');
    expect(GameBoxBackOverride.isPlayers(media), isTrue);
    expect(media.recordOf(GameBoxMediaKind.back)!.transforms.single, contains('of 2000x1080'));
  });
}
