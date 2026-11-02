// The ScreenScraper batch run, end to end against an in-memory database and
// a fake ScreenScraper (docs/game-box-3d.md § 18): "New content only" after
// the choices change, imported console icons, protected faces, and the box
// faces completed from the other sources on the same Start button.
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:crypto/crypto.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/providers/file_provider.dart';
import 'package:neostation/providers/scraping_provider.dart';
import 'package:neostation/repositories/scraper_repository.dart';
import 'package:neostation/services/game_box/game_box_batch.dart';
import 'package:neostation/services/game_box/game_box_media.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/game_box/game_box_sources.dart';
import 'package:neostation/services/screenscraper/scrape_choices.dart';
import 'package:neostation/services/screenscraper/screenscraper_client.dart';
import 'package:neostation/services/screenscraper_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';

/// Signature-only payloads: enough for the plain download, never decoded.
const _mp4 = [0, 0, 0, 0x18, 0x66, 0x74, 0x79, 0x70, 0x69, 0x73, 0x6f, 0x6d];
const _pdf = [0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x34];

/// A PNG header of [w] × [h] (what the size reader looks at), plus [tag].
List<int> _pngHeader(int w, int h, {int tag = 0}) => [
      0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, //
      0, 0, 0, 13, 0x49, 0x48, 0x44, 0x52,
      (w >> 24) & 255, (w >> 16) & 255, (w >> 8) & 255, w & 255,
      (h >> 24) & 255, (h >> 16) & 255, (h >> 8) & 255, h & 255,
      8, 6, 0, 0, 0, 0, 0, 0, 0, tag,
    ];

/// A baseline JPEG header of [w] × [h] (SOF0), as a Switch title icon.
List<int> _jpegHeader(int w, int h) => [
      0xff, 0xd8, 0xff, 0xc0, 0x00, 0x11, 0x08, //
      (h >> 8) & 255, h & 255, (w >> 8) & 255, w & 255,
      0x03, 1, 0x22, 0, 2, 0x11, 1, 3, 0x11, 1, 0xff, 0xd9,
    ];

/// A real, decodable picture (the box faces are checked before adoption).
Future<Uint8List> _picture(int w, int h, {Color color = const Color(0xFFE60012)}) async {
  final recorder = ui.PictureRecorder();
  final c = Canvas(recorder);
  final s = Size(w.toDouble(), h.toDouble());
  c.drawRect(Offset.zero & s, Paint()..color = color);
  c.drawCircle(Offset(w / 2, h / 2), w / 3, Paint()..color = const Color(0xFF2040A0));
  final image = await recorder.endRecording().toImage(w, h);
  final data = await image.toByteData(format: ui.ImageByteFormat.png);
  image.dispose();
  return data!.buffer.asUint8List();
}

/// A ScreenScraper that knows one game and serves the media it lists.
class _FakeScreenScraper {
  final requests = <Uri>[];
  final files = <String, List<int>>{};
  final medias = <Map<String, dynamic>>[];
  String name = 'Game';

  /// Lists [bytes] as the [type] media of [region], with its MD5 and size.
  void serve(String type, List<int> bytes, {String region = 'us', String format = 'png'}) {
    final file = '$type-$region.$format';
    files[file] = bytes;
    medias.add({
      'type': type,
      'region': region,
      'format': format,
      'url': 'https://media.test/$file',
      'md5': md5.convert(bytes).toString(),
      'size': '${bytes.length}',
    });
  }

  void serveDefaults({List<int>? front}) {
    serve('box-2D', front ?? _pngHeader(400, 560, tag: 1));
    serve('ss', _pngHeader(640, 480, tag: 2));
    serve('fanart', _pngHeader(1920, 1080, tag: 3), region: 'wor');
    serve('wheel', _pngHeader(400, 150, tag: 4), region: 'wor');
    serve('video', _mp4, format: 'mp4');
    serve('box-2D-back', _pngHeader(400, 560, tag: 5));
    serve('box-2D-side', _pngHeader(40, 560, tag: 6));
    serve('support-2D', _pngHeader(300, 300, tag: 7));
    serve('manuel', _pdf, format: 'pdf');
  }

  http.Client get client => MockClient((request) async {
        requests.add(request.url);
        if (request.url.path.endsWith('jeuInfos.php')) {
          return http.Response(
            jsonEncode({
              'header': {'success': 'true'},
              'response': {
                'ssuser': {'requeststoday': '1', 'maxrequestsperday': '20000'},
                'jeu': {
                  'id': '42',
                  'noms': [
                    {'region': 'wor', 'text': name},
                  ],
                  'medias': medias,
                },
              },
            }),
            200,
          );
        }
        if (request.url.host == 'media.test') {
          final bytes = files[request.url.pathSegments.last];
          return bytes == null ? http.Response('NOMEDIA', 200) : http.Response.bytes(bytes, 200);
        }
        return http.Response('not found', 404);
      });

  /// The same files for the box-media service's own reads (its test hook
  /// replaces every network read, ScreenScraper's included).
  Uint8List? fileOf(String url) {
    final u = Uri.parse(url);
    if (u.host != 'media.test') return null;
    requests.add(u);
    final bytes = files[u.pathSegments.last];
    return bytes == null ? null : Uint8List.fromList(bytes);
  }

  int get lookups => requests.where((u) => u.path.endsWith('jeuInfos.php')).length;
  List<String> get downloads => [
        for (final u in requests)
          if (u.host == 'media.test') u.pathSegments.last,
      ];
}

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

void main() {
  final dbHelper = DatabaseTestHelper();
  late Directory root;
  late _FakeScreenScraper ss;

  setUpAll(() {
    // One media root for the file: the resolver keeps the first one it sees.
    root = Directory.systemTemp.createTempSync('scraper_batch');
  });

  tearDownAll(() {
    ScreenscraperClient.debugClient = null;
    GameBoxMediaService.debugFetch = null;
    root.deleteSync(recursive: true);
  });

  Future<void> addSystem(String id, int ssId) async {
    final db = await SqliteService.getDatabase();
    await db.execute(
        "INSERT INTO app_systems (id, real_name, folder_name, screenscraper_id) VALUES ('$id', '$id', '$id', $ssId)");
    await db.execute("INSERT INTO user_detected_systems (app_system_id, actual_folder_name) VALUES ('$id', '$id')");
    await db.execute("INSERT INTO user_screenscraper_system_config (app_system_id, enabled) VALUES ('$id', 1)");
  }

  Future<void> addRom(String system, String filename, String romPath, {String? titleId, String? title}) async {
    final db = await SqliteService.getDatabase();
    await db.rawInsert(
      'INSERT INTO user_roms (filename, rom_path, app_system_id, title_id, title_name) VALUES (?, ?, ?, ?, ?)',
      [filename, romPath, system, titleId, title],
    );
  }

  setUp(() async {
    // The scraping session holds a wake lock; no platform answers here.
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMessageHandler(
      'dev.flutter.pigeon.wakelock_plus_platform_interface.WakelockPlusApi.toggle',
      (_) async => const StandardMessageCodec().encodeMessage(<Object?>[null]),
    );
    final db = await dbHelper.setUp();
    SharedPreferences.setMockInitialValues({'custom_user_data_path': root.path});
    PackageInfo.setMockInitialValues(
        appName: 'RewindBox', packageName: 'test', version: '1.0', buildNumber: '1', buildSignature: '');
    GameBoxMediaChecker.clearCache();
    final media = Directory(p.join(root.path, 'media'));
    if (media.existsSync()) media.deleteSync(recursive: true);
    // The application's table has the region order (migration v85).
    await db.execute(
        "ALTER TABLE user_screenscraper_config ADD COLUMN region_priority TEXT DEFAULT '[\"wor\",\"us\",\"eu\",\"jp\"]'");
    await db.execute(
      "INSERT INTO user_screenscraper_credentials (id, username, password, maxthreads, preferred_language) "
      "VALUES (1, 'user', '${base64Encode(utf8.encode('secret'))}', '2', 'en')",
    );
    ss = _FakeScreenScraper();
    ScreenscraperClient.debugClient = ss.client;
    GameBoxMediaService.debugFetch = null;
  });

  tearDown(() async {
    await dbHelper.tearDown();
  });

  /// One press of Start, as the scraper screen does it.
  Future<ScrapingProvider> scrape(WidgetTester tester, {FileProvider? files}) async {
    late BuildContext context;
    await tester.pumpWidget(Builder(builder: (c) {
      context = c;
      return const SizedBox();
    }));
    // The summary dialog is not part of this check: the context is unmounted.
    await tester.pumpWidget(const SizedBox());
    final provider = ScrapingProvider()..startScraping(maxThreads: 2);
    await tester.runAsync(() => ScreenScraperService.startMetadataScraping(
          context,
          provider,
          shouldCancel: () => !provider.isScraping,
          fileProvider: files,
        ));
    return provider;
  }

  Future<void> choose(WidgetTester tester, List<String> types) =>
      tester.runAsync(() => ScraperRepository.saveEnabledMediaTypes(types)).then((_) {});

  Future<void> mode(WidgetTester tester, String value) =>
      tester.runAsync(() => ScraperRepository.saveScraperConfig({'scrape_mode': value})).then((_) {});

  File file(String system, String folder, String name) => File(p.join(root.path, 'media', system, folder, name));

  Future<int?> complete(WidgetTester tester, String filename) async => await tester.runAsync<int?>(() async {
        final db = await SqliteService.getDatabase();
        final rows = await db.rawQuery(
            'SELECT is_fully_scraped FROM user_screenscraper_metadata WHERE filename = ?', [filename]);
        return rows.isEmpty ? null : int.tryParse(rows.first['is_fully_scraped'].toString());
      });

  group('new content only', () {
    late File rom;
    setUp(() async {
      await addSystem('snes', 4);
      await (await SqliteService.getDatabase())
          .execute("INSERT INTO app_system_extensions (system_id, extension) VALUES ('snes', 'sfc')");
      rom = File(p.join(root.path, 'roms', 'snes', 'Game.sfc'))..createSync(recursive: true);
      rom.writeAsBytesSync(List.filled(64, 1));
      await addRom('snes', 'Game.sfc', rom.path);
      ss.serveDefaults();
    });

    testWidgets('a media type enabled later is fetched for an already scraped game', (tester) async {
      await scrape(tester);
      expect(file('snes', 'box2d', 'Game.png').existsSync(), isTrue);
      expect(file('snes', 'box2dback', 'Game.png').existsSync(), isFalse);
      expect(await complete(tester, 'Game.sfc'), 1);

      await choose(tester, const ['fanart', 'ss', 'wheel', 'box2D', 'video', 'boxFaces']);
      final before = ss.downloads.length;
      final second = await scrape(tester);

      expect(second.totalGames, 1, reason: 'the game is scraped again for the new choice');
      expect(file('snes', 'box2dback', 'Game.png').existsSync(), isTrue);
      expect(file('snes', 'box2dside', 'Game.png').existsSync(), isTrue);
      expect(file('snes', 'support2d', 'Game.png').existsSync(), isTrue);
      expect(ss.downloads.skip(before), unorderedEquals(['box-2D-back-us.png', 'box-2D-side-us.png', 'support-2D-us.png']));
      expect(second.mediaAdded, 3);
      expect(second.mediaReplaced, 0);
      expect(await complete(tester, 'Game.sfc'), 1);

      final third = await scrape(tester);
      expect(third.totalGames, 0, reason: 'nothing left for the current choices');
    });

    testWidgets('another region order applies to the pictures ScreenScraper sent, never to the others',
        (tester) async {
      ss.serve('box-2D', _pngHeader(400, 560, tag: 9), region: 'eu');
      await scrape(tester);
      final front = file('snes', 'box2d', 'Game.png');
      expect(front.readAsBytesSync(), _pngHeader(400, 560, tag: 1), reason: 'US first');
      // The player's own fanart (not a ScreenScraper file).
      final fanart = file('snes', 'fanarts', 'Game.png')..writeAsBytesSync(_pngHeader(1280, 720, tag: 42));

      // What the Regions page saves.
      await tester.runAsync(() => ScrapeChoices.saveRegionPriority(const ['eu', 'us', 'wor', 'jp']));
      expect(await complete(tester, 'Game.sfc'), 0, reason: 'the change reopens completed games');
      final before = ss.downloads.length;
      final second = await scrape(tester);

      expect(second.totalGames, 1);
      expect(front.readAsBytesSync(), _pngHeader(400, 560, tag: 9), reason: 'the EU cover replaces the US one');
      expect(fanart.readAsBytesSync(), _pngHeader(1280, 720, tag: 42), reason: 'not a ScreenScraper file: kept');
      expect(ss.downloads.skip(before), ['box-2D-eu.png']);
      expect(second.mediaReplaced, 1);
    });

    testWidgets('a language change opens completed games again, the same language does not', (tester) async {
      await scrape(tester);
      expect(await complete(tester, 'Game.sfc'), 1);
      await tester.runAsync(() => ScrapeChoices.languageChanged('en', 'en'));
      expect(await complete(tester, 'Game.sfc'), 1);
      await tester.runAsync(() => ScrapeChoices.languageChanged('en', 'fr'));
      expect(await complete(tester, 'Game.sfc'), 0);
    });

    testWidgets('a cover present under another extension is kept', (tester) async {
      final own = file('snes', 'box2d', 'Game.jpg')
        ..createSync(recursive: true)
        ..writeAsBytesSync(_jpegHeader(500, 700));
      await scrape(tester);
      expect(own.existsSync(), isTrue);
      expect(file('snes', 'box2d', 'Game.png').existsSync(), isFalse);
      expect(ss.downloads, isNot(contains('box-2D-us.png')));
    });
  });

  group('library titles', () {
    testWidgets('PS3: the ICON0 copies are replaced, then nothing present is downloaded again', (tester) async {
      await addSystem('ps3', 59);
      await addRom('ps3', 'BCES00510', 'rpcs3-library://game?title-id=BCES00510',
          titleId: 'BCES00510', title: 'God of War III');
      ss.serveDefaults();
      // What the RPCS3 library writes before any scrape.
      final icon = _pngHeader(320, 176, tag: 77);
      final front = file('ps3', 'box2d', 'BCES00510.png')..createSync(recursive: true);
      front.writeAsBytesSync(icon);
      final shot = file('ps3', 'screenshots', 'BCES00510.png')..createSync(recursive: true);
      shot.writeAsBytesSync(icon);

      final first = await scrape(tester);
      expect(front.readAsBytesSync(), _pngHeader(400, 560, tag: 1), reason: 'the icon gave way to the cover');
      expect(shot.readAsBytesSync(), _pngHeader(640, 480, tag: 2));
      expect(first.mediaReplaced, 2);

      // A cover the player put there by hand, then a new choice.
      front.writeAsBytesSync(_pngHeader(400, 560, tag: 99));
      await choose(tester, const ['fanart', 'ss', 'wheel', 'box2D', 'video', 'boxFaces']);
      final before = ss.downloads.length;
      final second = await scrape(tester);
      expect(second.totalGames, 1);
      expect(front.readAsBytesSync(), _pngHeader(400, 560, tag: 99), reason: 'the hand-picked cover stays');
      expect(ss.downloads.skip(before),
          unorderedEquals(['box-2D-back-us.png', 'box-2D-side-us.png', 'support-2D-us.png']),
          reason: 'no video, screenshot or cover downloaded again');
    });

    testWidgets('Switch: the title icon copied by the MeloNX import is replaced', (tester) async {
      await addSystem('switch', 225);
      final rom = File(p.join(root.path, 'roms', 'switch', 'Mario.nsp'))..createSync(recursive: true);
      rom.writeAsBytesSync(List.filled(64, 2));
      await addRom('switch', 'Mario.nsp', rom.path);
      ss.serve('box-2D', _jpegHeader(650, 1050), format: 'jpg');
      final icon = file('switch', 'box2d', 'Mario.jpg')..createSync(recursive: true);
      icon.writeAsBytesSync(_jpegHeader(256, 256));

      await scrape(tester);
      expect(icon.readAsBytesSync(), _jpegHeader(650, 1050));
    });
  });

  group('box faces on the same Start', () {
    const title = "Super Mario 3D World + Bowser's Fury";
    late File rom;
    late _FP files;
    final served = <String, Uint8List>{};

    setUp(() async {
      await addSystem('switch', 225);
      rom = File(p.join(root.path, 'roms', 'switch', 'Mario.nsp'))..createSync(recursive: true);
      rom.writeAsBytesSync(List.filled(64, 3));
      await addRom('switch', 'Mario.nsp', rom.path);
      files = _FP(root.path);
      ss.name = title;
      served
        ..clear()
        ..['${GameTdb.site}/switchtdb.txt?LANG=EN'] =
            Uint8List.fromList(utf8.encode('TITLES = https://www.gametdb.com (type: Switch)\nAUZPA = $title\n'))
        ..['${GameTdb.site}/Switch/AUZPA'] = Uint8List.fromList(utf8.encode('''
<a href="https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg">b</a>
<a href="https://art.gametdb.com/switch/coverfullHQ/EN/AUZPA.jpg">f</a>'''));
      GameBoxMediaService.debugFetch = (url) async => served[url] ?? ss.fileOf(url);
    });

    GameBoxLocalMedia local() => GameBoxMediaStore(files)
        .read(GameBoxBatch.gameOf(romName: 'Mario.nsp', appSystemId: 'switch', systemFolder: 'switch'), 'switch');

    testWidgets('new content only: ScreenScraper first, then GameTDB for the faces it lacks', (tester) async {
      await tester.runAsync(() async {
        ss.serve('box-2D', await _picture(1166, 1888));
        served['https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg'] =
            await _picture(1166, 1888, color: const Color(0xFF00A0E0));
        served['https://art.gametdb.com/switch/coverfullHQ/EN/AUZPA.jpg'] = await _picture(2454, 1888);
      });
      await choose(tester, const ['box2D', 'boxFaces']);

      final run = await scrape(tester, files: files);

      expect(file('switch', 'box2d', 'Mario.png').existsSync(), isTrue, reason: "ScreenScraper's cover");
      expect(run.mediaAdded, 1);
      expect(local().recordOf(GameBoxMediaKind.back)?.type, 'gametdb:backHQ');
      expect(local().recordOf(GameBoxMediaKind.full)?.type, 'gametdb:coverfullHQ',
          reason: 'the spine comes from the sheet');
      expect(local().recordOf(GameBoxMediaKind.front), isNull, reason: 'the good ScreenScraper cover is kept');
      expect(run.facesBySource, {'gametdb': 2});
      expect(run.facesMissing, 1, reason: 'no disc or card anywhere');
      expect(ss.lookups, 1, reason: "the box step reuses ScreenScraper's answer");
    });

    testWidgets('extra sources off: only ScreenScraper', (tester) async {
      SharedPreferences.setMockInitialValues({
        'custom_user_data_path': root.path,
        'NeoStation.GameBox.ScrapeExtraSources': false,
      });
      await tester.runAsync(() async => ss.serve('box-2D', await _picture(1166, 1888)));
      await choose(tester, const ['box2D', 'boxFaces']);
      final run = await scrape(tester, files: files);
      expect(run.facesBySource, isEmpty);
      expect(run.facesMissing, 3);
      expect(local().recordOf(GameBoxMediaKind.back), isNull);
    });

    testWidgets('missing box faces only: no other media, faces from every source', (tester) async {
      await tester.runAsync(() async {
        ss.serve('box-2D', await _picture(1166, 1888));
        ss.serve('ss', await _picture(1280, 720));
        served['https://art.gametdb.com/switch/backHQ/EN/AUZPA.jpg'] =
            await _picture(1166, 1888, color: const Color(0xFF00A0E0));
        served['https://art.gametdb.com/switch/coverfullHQ/EN/AUZPA.jpg'] = await _picture(2454, 1888);
      });
      await choose(tester, const ['ss', 'box2D', 'boxFaces']);
      await mode(tester, 'faces_only');

      final run = await scrape(tester, files: files);

      expect(file('switch', 'screenshots', 'Mario.png').existsSync(), isFalse, reason: 'faces only');
      expect(run.facesBySource, {'screenscraper': 1, 'gametdb': 2});
      expect(run.facesMissing, 1);
      expect(run.failedGames, 0, reason: 'a face no source has is not a failed game');
      expect(await complete(tester, 'Mario.nsp'), isNull, reason: 'no metadata scrape');

      final again = await scrape(tester, files: files);
      expect(again.facesBySource, isEmpty, reason: 'only the support is left, and no source has it');
    });

    testWidgets('all content: a face chosen by hand is never overwritten', (tester) async {
      await tester.runAsync(() async {
        ss.serve('box-2D', await _picture(1166, 1888));
        ss.serve('box-2D-back', await _picture(1166, 1888, color: const Color(0xFF00FF00)));
      });
      await choose(tester, const ['box2D', 'boxFaces']);
      await mode(tester, 'all');
      final game = GameBoxBatch.gameOf(romName: 'Mario.nsp', appSystemId: 'switch', systemFolder: 'switch');
      final mine = await tester.runAsync(() => _picture(1166, 1888, color: const Color(0xFF884400)));
      final back = File(files.getMediaPath('switch', 'box2dback', 'Mario.nsp', 'png'))
        ..createSync(recursive: true)
        ..writeAsBytesSync(mine!);
      await tester.runAsync(
          () => GameBoxMediaStore(files).recordManualFace(game, 'switch', GameBoxMediaKind.back, back.path));

      await scrape(tester, files: files);
      expect(back.readAsBytesSync(), mine, reason: 'chosen by hand');
      expect(ss.downloads, isNot(contains('box-2D-back-us.png')));
    });
  });
}
