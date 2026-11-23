// Nintendo's eShop catalogues as a scrape source (docs/s2arm-switch2-library.md,
// Scraping), against synthetic answers: nothing of Nintendo's is stored here.
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:neostation/services/nintendo_eshop_catalogue.dart';
import 'package:neostation/services/screenscraper_service.dart';

const _id = '0400aaaabbbb0000';
const _banner = 'https://www.nintendo.com/eu/media/images/assets/test/banners/16x9_Test_image500w.jpg';
const _packshot = 'https://www.nintendo.com/eu/media/images/05_packshots/games_13/test/PS_Test_PEGI_image500w.jpg';

Map<String, dynamic> _europeDoc({
  String title = 'Test Quest',
  List<String> system = const ['nintendoswitch2'],
  String? imageUrl,
  String? banner = _banner,
}) => {
      'title': title,
      'excerpt': 'Une aventure de test.',
      'pretty_game_categories_txt': ['Action', 'Aventure'],
      'publisher': 'Test Publisher',
      'developer': 'Test Studio',
      'dates_released_dts': ['2026-11-05T00:00:00Z'],
      'players_to': 4,
      'system_type': system,
      'image_url_h16x9_s': ?banner,
      'image_url': ?imageUrl,
      'type': 'GAME',
    };

Map<String, dynamic> _japanItem({String title = 'テストクエスト'}) => {
      'title': title,
      'hard': '05_BEE',
      'icode': 'AB1JA',
      'siurl': 'hero00',
      'sslurl': ['shot01', 'shot02'],
      'text': '日本語の説明。',
      'maker': 'テスト',
      'dsdate': '2026-11-05 00:00:00',
    };

class _Nintendo {
  final requests = <http.Request>[];
  List<Map<String, dynamic>> europe = [_europeDoc()];
  List<Map<String, dynamic>> japan = [_japanItem()];
  int europeStatus = 200;
  final existing = <String>{};

  http.Client get client => MockClient((request) async {
        requests.add(request);
        final url = request.url;
        if (url.host == NintendoEshopCatalogue.europeHost) {
          if (europeStatus != 200) return http.Response('busy', europeStatus);
          return http.Response.bytes(
              utf8.encode(jsonEncode({'response': {'numFound': europe.length, 'docs': europe}})), 200);
        }
        if (url.host == NintendoEshopCatalogue.japanHost) {
          return http.Response.bytes(utf8.encode(jsonEncode({'result': {'total': japan.length, 'items': japan}})), 200);
        }
        if (request.method == 'HEAD') {
          return http.Response('', existing.contains(url.toString()) ? 200 : 404);
        }
        return http.Response('not found', 404);
      });

  Iterable<Uri> on(String host) => requests.map((r) => r.url).where((u) => u.host == host);
}

void main() {
  late _Nintendo nintendo;

  setUp(() {
    nintendo = _Nintendo();
    NintendoEshopCatalogue.clientOverride = nintendo.client;
    NintendoEshopCatalogue.interval = Duration.zero;
    NintendoEshopCatalogue.clearCache();
  });

  tearDown(() => NintendoEshopCatalogue.clientOverride = null);

  List<Map<String, dynamic>> medias(Map<String, dynamic> info) =>
      (info['medias'] as List).cast<Map<String, dynamic>>();

  test('a Switch 2 game by its program ID: facts, banner, screenshot, case', () async {
    final larger = _banner.replaceFirst('image500w', 'image1600w');
    final caseUrl = 'https://www.nintendo.com/jp/games/switch2/ab1ja/products/assets/img/software_img_package.webp';
    nintendo.existing.addAll([larger, caseUrl]);

    final info = await NintendoEshopCatalogue.gameInfo(
      programId: _id.toUpperCase(),
      switch2: true,
      language: 'fr',
      titles: ['テストクエスト'],
    );

    expect(info, isNotNull);
    final europe = nintendo.on(NintendoEshopCatalogue.europeHost).single;
    expect(europe.path, '/fr/select');
    expect(europe.queryParameters['fq'], 'type:GAME AND application_id_s:$_id', reason: 'exact, lower case');
    final japan = nintendo.on(NintendoEshopCatalogue.japanHost).first;
    expect(japan.queryParameters['opt_hard[]'], '05_BEE');

    expect(info!['noms'], [
      {'region': 'wor', 'text': 'Test Quest'},
      {'region': 'jp', 'text': 'テストクエスト'},
    ]);
    expect(info['synopsis'], [
      {'langue': 'fr', 'text': 'Une aventure de test.'},
      {'langue': 'ja', 'text': '日本語の説明。'},
    ]);
    expect(info['dates'], [
      {'region': 'eu', 'text': '2026-11-05'},
      {'region': 'jp', 'text': '2026-11-05'},
    ]);
    expect(info['genres'], [
      {
        'noms': [
          {'langue': 'fr', 'text': 'Action, Aventure'},
        ],
      },
    ]);
    expect(info['editeur'], {'text': 'Test Publisher'});
    expect(info['developpeur'], {'text': 'Test Studio'});
    expect(info['joueurs'], {'text': '1-4'});
    expect(medias(info), [
      {'type': 'fanart', 'format': 'jpg', 'region': 'eu', 'url': larger},
      {'type': 'fanart', 'format': 'jpg', 'region': 'jp', 'url': '${NintendoEshopCatalogue.japanImages}hero00.jpg'},
      {'type': 'ss', 'format': 'jpg', 'region': 'wor', 'url': '${NintendoEshopCatalogue.japanImages}shot01.jpg'},
      {'type': 'box-2D', 'format': 'webp', 'region': 'jp', 'url': caseUrl},
    ]);
  });

  test('the banner falls back to 1280 then to the width the catalogue gives', () async {
    final at1280 = _banner.replaceFirst('image500w', 'image1280w');
    nintendo.existing.add(at1280);
    expect(await NintendoEshopCatalogue.largestBanner(_banner), at1280);
    nintendo.existing.clear();
    expect(await NintendoEshopCatalogue.largestBanner(_banner), _banner);
  });

  test('an ID with a Switch and a Switch 2 entry: the platform asked for', () async {
    nintendo.europe = [
      _europeDoc(title: 'Test Quest', system: ['nintendoswitch_gamecard'], imageUrl: _packshot),
      _europeDoc(title: 'Test Quest – Nintendo Switch 2 Edition', system: ['nintendoswitch2']),
    ];
    nintendo.japan = [];
    final edition = await NintendoEshopCatalogue.gameInfo(programId: _id, switch2: true, language: 'fr');
    expect((edition!['noms'] as List).first['text'], 'Test Quest – Nintendo Switch 2 Edition');
    final original = await NintendoEshopCatalogue.gameInfo(programId: _id, switch2: false, language: 'fr');
    expect((original!['noms'] as List).first['text'], 'Test Quest');
    expect(medias(original).where((m) => m['type'] == 'box-2D').single['url'], _packshot,
        reason: 'a Switch packshot is the box');
  });

  test('only a packshot is a box, and Japan needs the same title', () async {
    nintendo.europe = [
      _europeDoc(imageUrl: 'https://www.nintendo.com/eu/media/images/03_teaser_module/test_image500w.png'),
    ];
    nintendo.japan = [_japanItem(title: 'テストクエスト2')];
    final info = await NintendoEshopCatalogue.gameInfo(
        programId: _id, switch2: true, language: 'fr', titles: ['テストクエスト']);
    expect(medias(info!).map((m) => m['type']), ['fanart'], reason: 'no box, no Japanese screenshot');
    expect((info['noms'] as List).length, 1);
  });

  test('a language Europe lacks reads the English catalogue', () async {
    await NintendoEshopCatalogue.gameInfo(programId: _id, switch2: true, language: 'ja');
    expect(nintendo.on(NintendoEshopCatalogue.europeHost).single.path, '/en/select');
  });

  test('an unknown game is not asked again; a failed request is', () async {
    nintendo.europe = [];
    nintendo.japan = [];
    expect(await NintendoEshopCatalogue.gameInfo(programId: _id, switch2: true, language: 'fr'), isNull);
    await NintendoEshopCatalogue.gameInfo(programId: _id, switch2: true, language: 'fr');
    expect(nintendo.on(NintendoEshopCatalogue.europeHost).length, 1);

    NintendoEshopCatalogue.clearCache();
    nintendo.requests.clear();
    nintendo.europeStatus = 503;
    expect(await NintendoEshopCatalogue.gameInfo(programId: _id, switch2: true, language: 'fr'), isNull);
    nintendo.europeStatus = 200;
    nintendo.europe = [_europeDoc()];
    expect(await NintendoEshopCatalogue.gameInfo(programId: _id, switch2: true, language: 'fr'), isNotNull);
    expect(nintendo.on(NintendoEshopCatalogue.europeHost).length, 2);
  });

  test('neither an ID nor a title: nothing is asked', () async {
    expect(await NintendoEshopCatalogue.gameInfo(programId: 'main', switch2: true, language: 'fr'), isNull);
    expect(nintendo.requests, isEmpty);
  });

  test('a title ID in a file name', () {
    expect(NintendoEshopCatalogue.programIdInName('Mario [0100000000010000][v0].nsp'), '0100000000010000');
    expect(NintendoEshopCatalogue.programIdInName('Mario (Europe).nsp'), isNull);
  });

  group('the same title written another way', () {
    String key(String t) => NintendoEshopCatalogue.sameTitleKey(t);

    test('ScreenScraper, Nintendo and the game spell it alike', () {
      final nintendo = key('The Legend of Zelda: Breath of the Wild – Nintendo Switch 2 Edition');
      expect(key('Legend of Zelda - Breath of the Wild -Nintendo Switch 2 Edition-, The'), nintendo);
      expect(key('The Legend of Zelda : Breath of the Wild (Nintendo Switch™ 2 Edition)'), nintendo);
      expect(key('Little Nightmares III'), key('Little Nightmares 3'));
      expect(key('Pokémon Légendes'), key('Pokemon Legendes'));
      expect(key('ゼルダの伝説　時のオカリナ'), key('ゼルダの伝説 時のオカリナ'));
    });

    test('other games stay apart', () {
      expect(key('Mario Kart World'), isNot(key('Mario Kart 8 Deluxe')));
      expect(key('Little Nightmares III'), isNot(key('Little Nightmares II')));
    });

    test('a ScreenScraper search result is matched by the game or Nintendo title', () {
      final games = [
        {
          'id': '1',
          'noms': [
            {'region': 'wor', 'text': 'Legend of Zelda - Tears of the Kingdom -Nintendo Switch 2 Edition-, The'},
          ],
        },
        {
          'id': '2',
          'noms': [
            {'region': 'wor', 'text': 'Legend of Zelda - Breath of the Wild -Nintendo Switch 2 Edition-, The'},
          ],
        },
      ];
      expect(
        ScreenScraperService.findSwitch2GameByName(
            games, ['Breath of the Wild', 'The Legend of Zelda: Breath of the Wild – Nintendo Switch 2 Edition'])?['id'],
        '2',
      );
      expect(ScreenScraperService.findSwitch2GameByName(games, ['Mario Kart World', null]), isNull);
    });
  });
}
