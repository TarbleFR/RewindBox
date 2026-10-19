import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_regions.dart';
import 'package:path/path.dart' as p;

class _TestFileProvider extends FileProvider {
  _TestFileProvider(this.root);
  final String root;

  @override
  bool get isInitialized => true;

  @override
  String getMediaPath(String systemFolderName, String imageType, String romName, String extension) =>
      p.join(root, 'media', systemFolderName, imageType, '${FileProvider.stripRomExtension(romName)}.$extension');

  @override
  String getMediaDirectoryPath() => p.join(root, 'media');

  @override
  List<String> getEsdeMediaCandidates(String systemFolderName, String imageType, String romName) => const [];
}

GameModel _game(String romname) => GameModel(
      romname: romname,
      realname: 'Test',
      name: 'Test Game',
      year: '',
      developer: '',
      publisher: '',
      genre: '',
      players: '',
      rating: 0,
    );

Map<String, dynamic> _ss(String type, String region, {String? md5, String format = 'png'}) => {
      'type': type,
      'parent': 'jeu',
      'url': 'https://neoclone.screenscraper.fr/api2/mediaJeu.php?devid=DEV&devpassword=SECRET'
          '&softname=neostation&ssid=user&sspassword=PASS&systemeid=57&jeuid=1234&media=$type($region)',
      'region': region,
      'crc': 'CRC$region',
      'md5': md5 ?? 'md5-$type-$region',
      'sha1': 'sha-$type-$region',
      'size': '12345',
      'format': format,
    };

void main() {
  group('regions', () {
    test('No-Intro and Redump tags give the regions of the copy', () {
      expect(GameBoxRegions.fromFileName('Final Fantasy VII (USA) (Disc 1).cue'), ['us']);
      expect(GameBoxRegions.fromFileName('Tetris (World) (Rev 1).gb'), ['wor']);
      expect(GameBoxRegions.fromFileName('Mario Kart 64 (Europe) (En,Fr,De).z64'), ['eu']);
      expect(GameBoxRegions.fromFileName('Zelda (USA, Europe).sfc'), ['us', 'eu']);
      expect(GameBoxRegions.fromFileName('Game (Beta) (Proto).bin'), isEmpty);
      expect(GameBoxRegions.fromFileName('My Game.iso'), isEmpty);
      expect(GameBoxRegions.languagesFromFileName('Mario Kart 64 (Europe) (En,Fr,De).z64'), ['en', 'fr', 'de']);
    });

    test('the print language is a presumption from the region', () {
      expect(GameBoxRegions.languageOfRegion('jp'), 'ja');
      expect(GameBoxRegions.languageOfRegion('fr'), 'fr');
      expect(GameBoxRegions.languageOfRegion('tw'), 'zh_Hant');
      expect(GameBoxRegions.languageOfRegion('cn'), 'zh');
      expect(GameBoxRegions.languageOfRegion('br'), 'pt');
      expect(GameBoxRegions.languageOfRegion('cus'), isNull);
      expect(GameBoxRegions.isMultilingualRegion('eu'), isTrue);
      expect(GameBoxRegions.recognitionHints('jp').first, 'ja-JP');
    });
  });

  group('manifest', () {
    test('ScreenScraper entries keep the media token, never the credentials', () {
      final entry = GameBoxMediaEntry.fromScreenScraper(_ss('box-2D-back', 'fr'))!;
      expect(entry.kind, GameBoxMediaKind.back);
      expect(entry.token, 'box-2D-back(fr)');
      expect(entry.region, 'fr');
      final manifest = GameBoxManifest(
        screenScraperSystemId: '57',
        screenScraperGameId: '1234',
        matchedBy: GameBoxMatch.md5,
        entries: [entry],
      );
      final json = jsonEncode(manifest.toJson());
      for (final secret in ['SECRET', 'PASS', 'devpassword', 'sspassword', 'DEV&', 'http']) {
        expect(json, isNot(contains(secret)));
      }
      final back = GameBoxManifest.fromJson(jsonDecode(json) as Map<String, dynamic>)!;
      expect(back.entries.single.token, 'box-2D-back(fr)');
      expect(back.matchedBy, GameBoxMatch.md5);
    });

    test('unknown media types are ignored, unsafe edition file names rejected', () {
      expect(GameBoxMediaEntry.fromScreenScraper(_ss('wheel', 'us')), isNull);
      final m = GameBoxManifest.fromJson({
        'version': 1,
        'screenscraper': {'systemId': '1', 'gameId': '2'},
        'matchedBy': 'fileName',
        'media': [],
        'backEditionFiles': {'a': '../escape.png', 'b': 'ok.png', 'c': '.hidden'},
      })!;
      expect(m.backEditionFiles, {'b': 'ok.png'});
    });

    test('one picture listed under several regions is one edition', () {
      final entries = [
        GameBoxMediaEntry.fromScreenScraper(_ss('box-2D-back', 'wor', md5: 'same'))!,
        GameBoxMediaEntry.fromScreenScraper(_ss('box-2D-back', 'us', md5: 'same'))!,
        GameBoxMediaEntry.fromScreenScraper(_ss('box-2D-back', 'fr'))!,
      ];
      final m = GameBoxManifest(
        screenScraperSystemId: '57', screenScraperGameId: '1', matchedBy: GameBoxMatch.fileName, entries: entries,
      );
      final editions = m.backEditions();
      expect(editions, hasLength(2));
      expect(editions.first.regions, ['wor', 'us']);
    });
  });

  group('selection', () {
    final entries = [
      for (final r in ['wor', 'us', 'eu', 'jp', 'fr']) GameBoxMediaEntry.fromScreenScraper(_ss('box-2D-back', r))!,
      GameBoxMediaEntry.fromScreenScraper(_ss('box-2D', 'jp', md5: 'front-jp'))!,
    ];

    test('the edition of the copy wins over the front region and the priority', () {
      final pick = GameBoxMediaSelection.choose(entries, GameBoxMediaKind.back,
          gameRegions: ['eu'], frontRegion: 'jp', regionPriority: {'wor': 100, 'us': 90});
      expect(pick!.region, 'eu');
    });

    test('without a known copy, the edition of the front shown wins', () {
      final pick = GameBoxMediaSelection.choose(entries, GameBoxMediaKind.back,
          frontRegion: 'jp', regionPriority: {'wor': 100, 'us': 90});
      expect(pick!.region, 'jp');
    });

    test('otherwise the user region priority decides', () {
      final pick = GameBoxMediaSelection.choose(entries, GameBoxMediaKind.back,
          regionPriority: {'wor': 100, 'us': 90});
      expect(pick!.region, 'wor');
    });

    test('a reading language finds a scan published for it, or none', () {
      final m = GameBoxManifest(
        screenScraperSystemId: '57', screenScraperGameId: '1', matchedBy: GameBoxMatch.fileName, entries: entries,
      );
      expect(GameBoxMediaSelection.backForLanguage(m, 'fr')!.entry.region, 'fr');
      expect(GameBoxMediaSelection.backForLanguage(m, 'ja')!.entry.region, 'jp');
      expect(GameBoxMediaSelection.backForLanguage(m, 'id'), isNull, reason: 'no Indonesian edition: translated reading');
      expect(GameBoxMediaSelection.backForLanguage(m, 'de'), isNull);
    });
  });

  group('store', () {
    late Directory dir;
    setUp(() => dir = Directory.systemTemp.createTempSync('game_box_media'));
    tearDown(() => dir.deleteSync(recursive: true));

    test('reads the faces at the reader lookup paths and writes the manifest atomically', () async {
      final fp = _TestFileProvider(dir.path);
      final game = _game('Game (USA).cue');
      final store = GameBoxMediaStore(fp);
      final backPath = store.canonicalPath(game, 'ps1', GameBoxMediaFolders.back, 'jpg');
      File(backPath)
        ..createSync(recursive: true)
        ..writeAsBytesSync([0xFF, 0xD8, 0xFF, 0xE0]);
      var local = store.read(game, 'ps1');
      expect(local.back, backPath);
      expect(local.front, isNull);
      expect(local.spine, isNull);
      expect(local.manifest, isNull);

      await store.writeManifest(game, 'ps1', GameBoxManifest(
        screenScraperSystemId: '57', screenScraperGameId: '1', matchedBy: GameBoxMatch.fileName,
        entries: [GameBoxMediaEntry.fromScreenScraper(_ss('box-2D-back', 'us'))!],
        backEditionFiles: {'md5:x': 'us-x.png'},
      ));
      expect(File('${store.manifestPath(game, 'ps1')}.part').existsSync(), isFalse);
      local = store.read(game, 'ps1');
      expect(local.manifest!.entries, hasLength(1));
      expect(local.backEditionsDir, p.join(dir.path, 'media', 'ps1', GameBoxMediaFolders.backEditions, 'Game (USA)'));
    });

    test('a damaged manifest never hides the faces', () {
      final fp = _TestFileProvider(dir.path);
      final game = _game('Game.cue');
      final store = GameBoxMediaStore(fp);
      File(store.manifestPath(game, 'ps1'))
        ..createSync(recursive: true)
        ..writeAsStringSync('{not json');
      final back = store.canonicalPath(game, 'ps1', GameBoxMediaFolders.back, 'png');
      File(back)
        ..createSync(recursive: true)
        ..writeAsBytesSync([0x89, 0x50, 0x4E, 0x47]);
      final local = store.read(game, 'ps1');
      expect(local.manifest, isNull);
      expect(local.back, back);
    });

    test('image sizes come from PNG and JPEG headers', () {
      final png = File(p.join(dir.path, 'a.png'))
        ..writeAsBytesSync([
          0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52,
          0, 0, 2, 0x58, 0, 0, 2, 0x52, 8, 6, 0, 0, 0,
        ]);
      final size = GameBoxImageSize.of(png.path)!;
      expect(size.width, 600);
      expect(size.height, 594);
    });
  });
}
