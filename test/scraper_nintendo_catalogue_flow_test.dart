// The batch run with Nintendo's eShop catalogues (docs/s2arm-switch2-library.md,
// Scraping), end to end against an in-memory database, a fake ScreenScraper
// and a fake Nintendo: nothing of Nintendo's is stored here.
//
// Before, a Switch 2 game ScreenScraper does not list (The Legend of Zelda:
// Ocarina of Time, released on 5 November 2026: 76 Switch 2 games on
// ScreenScraper, none with pictures) got nothing at all, and one it lists under
// its own spelling was missed by the exact name comparison.
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/data/datasources/sqlite_service.dart';
import 'package:neostation/providers/scraping_provider.dart';
import 'package:neostation/repositories/scraper_repository.dart';
import 'package:neostation/services/game_box/game_box_media_check.dart';
import 'package:neostation/services/game_box/game_box_media_service.dart';
import 'package:neostation/services/nintendo_eshop_catalogue.dart';
import 'package:neostation/services/screenscraper/screenscraper_client.dart';
import 'package:neostation/services/screenscraper_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path/path.dart' as p;
import 'package:shared_preferences/shared_preferences.dart';

import 'database_test_helper.dart';

/// Signature-only pictures: what the downloader checks, never decoded.
List<int> _jpeg(int tag) => [0xff, 0xd8, 0xff, 0xe0, 0, 16, tag, 0, 0, 0, 0, 0, 0xff, 0xd9];
List<int> _png(int tag) => [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, tag];
List<int> get _webp => [...ascii.encode('RIFF'), 20, 0, 0, 0, ...ascii.encode('WEBPVP8X'), 0, 0, 0, 0];

const _s2Id = '0400cafe00001000';
const _s1Id = '0100cafe00002000';
const _eu = 'https://www.nintendo.com/eu/media/images/test';

/// A ScreenScraper that knows what [games] lists, by title search (Switch 2)
/// and by file name (the others), with its pictures on media.test.
class _FakeScreenScraper {
  final requests = <Uri>[];
  final games = <Map<String, dynamic>>[];

  http.Client get client => MockClient((request) async {
        final url = request.url;
        requests.add(url);
        Map<String, dynamic> ok(Map<String, dynamic> response) => {
              'header': {'success': 'true'},
              'response': {
                'ssuser': {'requeststoday': '1', 'maxrequestsperday': '20000'},
                ...response,
              },
            };
        if (url.path.endsWith('jeuRecherche.php')) {
          return http.Response.bytes(utf8.encode(jsonEncode(ok({'jeux': games}))), 200,
              headers: {'content-type': 'application/json; charset=utf-8'});
        }
        if (url.path.endsWith('jeuInfos.php')) {
          return http.Response(jsonEncode({'header': {'success': 'false', 'error': 'Jeu non trouvée'}}), 200);
        }
        if (url.host == 'media.test') return http.Response.bytes(_png(9), 200);
        return http.Response('not found', 404);
      });
}

/// Nintendo's catalogues and picture servers.
class _FakeNintendo {
  final requests = <Uri>[];
  final europe = <String, Map<String, dynamic>>{};
  final japan = <Map<String, dynamic>>[];

  http.Client get client => MockClient((request) async {
        final url = request.url;
        requests.add(url);
        if (url.host == NintendoEshopCatalogue.europeHost) {
          final id = url.queryParameters['fq']!.split(':').last;
          final docs = [?europe[id]];
          return http.Response.bytes(utf8.encode(jsonEncode({'response': {'docs': docs}})), 200);
        }
        if (url.host == NintendoEshopCatalogue.japanHost) {
          return http.Response.bytes(utf8.encode(jsonEncode({'result': {'items': japan}})), 200);
        }
        if (request.method == 'HEAD') {
          final known = url.path.contains('1600w') || url.path.endsWith('software_img_package.webp');
          return http.Response('', known ? 200 : 404);
        }
        final path = url.path;
        if (path.endsWith('.webp')) return http.Response.bytes(_webp, 200);
        if (path.contains('packshots')) return http.Response.bytes(_jpeg(1), 200);
        if (path.contains('1600w')) return http.Response.bytes(_jpeg(2), 200);
        if (path.contains('shot')) return http.Response.bytes(_jpeg(3), 200);
        return http.Response('not found', 404);
      });

  bool get asked => requests.any((u) =>
      u.host == NintendoEshopCatalogue.europeHost || u.host == NintendoEshopCatalogue.japanHost);
}

void main() {
  final dbHelper = DatabaseTestHelper();
  late Directory root;
  late _FakeScreenScraper ss;
  late _FakeNintendo nintendo;

  setUpAll(() => root = Directory.systemTemp.createTempSync('scraper_nintendo'));

  tearDownAll(() {
    ScreenscraperClient.debugClient = null;
    NintendoEshopCatalogue.clientOverride = null;
    root.deleteSync(recursive: true);
  });

  Future<void> addSystem(String id, int ssId, String extension) async {
    final db = await SqliteService.getDatabase();
    await db.execute(
        "INSERT INTO app_systems (id, real_name, folder_name, screenscraper_id) VALUES ('$id', '$id', '$id', $ssId)");
    await db.execute("INSERT INTO user_detected_systems (app_system_id, actual_folder_name) VALUES ('$id', '$id')");
    await db.execute("INSERT INTO user_screenscraper_system_config (app_system_id, enabled) VALUES ('$id', 1)");
    await db.execute("INSERT INTO app_system_extensions (system_id, extension) VALUES ('$id', '$extension')");
  }

  Future<void> addRom(String system, String filename, String romPath, {String? titleId, String? title}) async {
    final db = await SqliteService.getDatabase();
    await db.rawInsert(
      'INSERT INTO user_roms (filename, rom_path, app_system_id, title_id, title_name) VALUES (?, ?, ?, ?, ?)',
      [filename, romPath, system, titleId, title],
    );
  }

  setUp(() async {
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
    await db.execute(
        "ALTER TABLE user_screenscraper_config ADD COLUMN region_priority TEXT DEFAULT '[\"wor\",\"eu\",\"us\",\"jp\"]'");
    await db.execute(
      "INSERT INTO user_screenscraper_credentials (id, username, password, maxthreads, preferred_language) "
      "VALUES (1, 'user', '${base64Encode(utf8.encode('secret'))}', '2', 'fr')",
    );
    await ScraperRepository.saveEnabledMediaTypes(const ['box2D', 'fanart', 'ss', 'wheel']);
    ss = _FakeScreenScraper();
    ScreenscraperClient.debugClient = ss.client;
    ScreenscraperClient.busyDelay = (_) => Duration.zero;
    ScreenScraperService.retryPause = Duration.zero;
    GameBoxMediaService.debugFetch = null;
    nintendo = _FakeNintendo();
    NintendoEshopCatalogue.clientOverride = nintendo.client;
    NintendoEshopCatalogue.interval = Duration.zero;
    NintendoEshopCatalogue.clearCache();

    nintendo.europe[_s2Id] = {
      'title': 'Hylian Quest',
      'excerpt': 'Une quête de test.',
      'pretty_game_categories_txt': ['Aventure'],
      'publisher': 'Test Publisher',
      'dates_released_dts': ['2026-11-05T00:00:00Z'],
      'players_to': 1,
      'system_type': ['nintendoswitch2'],
      'image_url_h16x9_s': '$_eu/banners/16x9_HylianQuest_image500w.jpg',
      'type': 'GAME',
    };
    nintendo.japan.add({
      'title': 'Hylian Quest',
      'hard': '05_BEE',
      'icode': 'AB1JA',
      'siurl': 'hero',
      'sslurl': ['shot01'],
    });
    nintendo.europe[_s1Id] = {
      'title': 'Plumber Trip',
      'excerpt': 'Un voyage de test.',
      'pretty_game_categories_txt': ['Plateformes'],
      'publisher': 'Test Publisher',
      'dates_released_dts': ['2017-10-27T00:00:00Z'],
      'players_to': 2,
      'system_type': ['nintendoswitch_gamecard'],
      'image_url': '$_eu/05_packshots/PS_PlumberTrip_PEGI_image500w.jpg',
      'image_url_h2x1_s': '$_eu/share/H2x1_PlumberTrip_image500w.jpg',
      'type': 'GAME',
    };
  });

  tearDown(() async => dbHelper.tearDown());

  Future<ScrapingProvider> scrape(WidgetTester tester) async {
    late BuildContext context;
    await tester.pumpWidget(Builder(builder: (c) {
      context = c;
      return const SizedBox();
    }));
    await tester.pumpWidget(const SizedBox());
    final provider = ScrapingProvider()..startScraping(maxThreads: 2);
    await tester.runAsync(() => ScreenScraperService.startMetadataScraping(
          context,
          provider,
          shouldCancel: () => !provider.isScraping,
        ));
    return provider;
  }

  File media(String system, String folder, String name) => File(p.join(root.path, 'media', system, folder, name));

  Future<Map<String, dynamic>?> metadata(WidgetTester tester, String system, String filename) =>
      tester.runAsync<Map<String, dynamic>?>(() => ScraperRepository.getGameMetadata(system, filename));

  Future<void> addSwitch2(String title) async {
    await addSystem('switch2', 296, 'npdm');
    await addRom('switch2', '$_s2Id.npdm', p.join(root.path, 'exports', 'game', 'base', 'exefs', 'main.npdm'),
        titleId: _s2Id, title: title);
  }

  testWidgets('a Switch 2 game ScreenScraper does not list: Nintendo describes it', (tester) async {
    await tester.runAsync(() => addSwitch2('Hylian Quest'));
    ss.games.add({
      'id': '7',
      'noms': [
        {'region': 'wor', 'text': 'Another Game'},
      ],
    });

    final run = await scrape(tester);

    expect(run.successfulGames, 1);
    final row = await metadata(tester, 'switch2', '$_s2Id.npdm');
    expect(row?['real_name'], 'Hylian Quest');
    expect(row?['description_fr'], 'Une quête de test.');
    expect(row?['genre'], 'Aventure');
    expect(row?['publisher'], 'Test Publisher');
    expect(media('switch2', 'fanarts', '$_s2Id.jpg').readAsBytesSync(), _jpeg(2), reason: 'the 1600 px banner');
    expect(media('switch2', 'screenshots', '$_s2Id.jpg').readAsBytesSync(), _jpeg(3));
    expect(media('switch2', 'box2d', '$_s2Id.webp').readAsBytesSync(), _webp, reason: "Nintendo's own case");
    final europe = nintendo.requests.firstWhere((u) => u.host == NintendoEshopCatalogue.europeHost);
    expect(europe.path, '/fr/select');
    expect(europe.queryParameters['fq'], contains(_s2Id));
  });

  testWidgets('a game ScreenScraper lists under its own spelling: found, then completed by Nintendo',
      (tester) async {
    await tester.runAsync(() => addSwitch2('HYLIAN QUEST'));
    ss.games.add({
      'id': '8',
      'noms': [
        {'region': 'wor', 'text': 'Hylian Quest -Nintendo Switch 2 Edition-'},
      ],
      'synopsis': [
        {'langue': 'fr', 'text': 'Le résumé de ScreenScraper.'},
      ],
      'medias': [
        {'type': 'fanart', 'region': 'wor', 'format': 'png', 'url': 'https://media.test/fanart.png'},
        {'type': 'wheel', 'region': 'wor', 'format': 'png', 'url': 'https://media.test/wheel.png'},
      ],
    });

    final run = await scrape(tester);

    expect(run.successfulGames, 1);
    final row = await metadata(tester, 'switch2', '$_s2Id.npdm');
    expect(row?['description_fr'], 'Le résumé de ScreenScraper.', reason: 'ScreenScraper first');
    expect(media('switch2', 'fanarts', '$_s2Id.png').readAsBytesSync(), _png(9));
    expect(media('switch2', 'fanarts', '$_s2Id.jpg').existsSync(), isFalse, reason: "ScreenScraper's is kept");
    expect(media('switch2', 'wheels', '$_s2Id.png').existsSync(), isTrue);
    expect(media('switch2', 'screenshots', '$_s2Id.jpg').readAsBytesSync(), _jpeg(3), reason: 'what it lacks');
    expect(media('switch2', 'box2d', '$_s2Id.webp').existsSync(), isTrue);
  });

  testWidgets('extra sources off: Nintendo is not asked', (tester) async {
    SharedPreferences.setMockInitialValues({
      'custom_user_data_path': root.path,
      'NeoStation.GameBox.ScrapeExtraSources': false,
    });
    await tester.runAsync(() => addSwitch2('Hylian Quest'));

    final run = await scrape(tester);

    expect(nintendo.asked, isFalse);
    expect(run.successfulGames, 0);
  });

  testWidgets('a Switch game ScreenScraper does not find: Nintendo by the ID of its file name', (tester) async {
    await tester.runAsync(() async {
      await addSystem('switch', 225, 'nsp');
      final rom = File(p.join(root.path, 'roms', 'switch', 'Plumber [$_s1Id][v0].nsp'))..createSync(recursive: true);
      rom.writeAsBytesSync(List.filled(64, 3));
      await addRom('switch', p.basename(rom.path), rom.path);
    });

    final run = await scrape(tester);

    expect(run.successfulGames, 1);
    const base = 'Plumber [$_s1Id][v0]';
    final row = await metadata(tester, 'switch', '$base.nsp');
    expect(row?['real_name'], 'Plumber Trip');
    expect(row?['players'], '1-2');
    expect(media('switch', 'box2d', '$base.jpg').readAsBytesSync(), _jpeg(1), reason: 'the PEGI packshot');
    expect(media('switch', 'fanarts', '$base.jpg').readAsBytesSync(), _jpeg(2));
    // Japan is asked only with the title Europe gave for that ID.
    expect(nintendo.requests.where((u) => u.host == NintendoEshopCatalogue.japanHost).map((u) => u.queryParameters['q']),
        everyElement('Plumber Trip'));
  });

  testWidgets('another system never asks Nintendo', (tester) async {
    await tester.runAsync(() async {
      await addSystem('snes', 4, 'sfc');
      final rom = File(p.join(root.path, 'roms', 'snes', 'Game.sfc'))..createSync(recursive: true);
      rom.writeAsBytesSync(List.filled(64, 1));
      await addRom('snes', 'Game.sfc', rom.path);
    });

    await scrape(tester);

    expect(nintendo.requests, isEmpty);
  });
}
