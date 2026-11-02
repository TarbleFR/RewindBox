// French manuals outside ScreenScraper (docs/game-box-3d.md § 26): the
// Internet Archive by the edition's product code then by exact title on the
// same platform, Nintendo Europe's own PDF of a DS game; only PDFs, never
// over a manual already there.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/game_box/game_box_rom_id.dart';
import 'package:neostation/services/game_manual_french_sources.dart';
import 'package:path/path.dart' as p;

final _pdf = Uint8List.fromList('%PDF-1.4\n% a manual\n'.codeUnits);
final _page = Uint8List.fromList('\n<!DOCTYPE html><html>Not found</html>'.codeUnits);

GameModel _game(String name, String system, {String? romPath}) => GameModel(
      romname: '$name.iso', realname: name, name: name, year: '', developer: '', publisher: '', genre: '',
      players: '', rating: 0, systemId: system, systemFolderName: system, romPath: romPath,
    );

Uint8List _json(Object o) => Uint8List.fromList(utf8.encode(jsonEncode(o)));

Uint8List _search(List<Map<String, Object>> docs) => _json({
      'response': {'numFound': docs.length, 'docs': docs},
    });

Uint8List _files(List<Map<String, Object>> files) => _json({'files': files});

void main() {
  late Directory dir;
  final requests = <String>[];
  late Map<bool Function(String url), Uint8List?> routes;

  setUp(() {
    dir = Directory.systemTemp.createTempSync('gbman');
    GameBoxRomId.clearCache();
    requests.clear();
    routes = {};
    GameManualFrenchSources.debugGet = (url) async {
      requests.add(url);
      for (final e in routes.entries) {
        if (e.key(url)) return e.value;
      }
      return null;
    };
  });
  tearDown(() {
    GameManualFrenchSources.debugGet = null;
    dir.deleteSync(recursive: true);
  });

  bool search(String url) => url.startsWith(GameManualFrenchSources.archiveSearch);
  String query(String url) => Uri.parse(url).queryParameters['q'] ?? '';

  test('Melee from its disc: the French manual of the edition, by its product code', () async {
    final iso = File(p.join(dir.path, 'melee.iso'))..writeAsBytesSync(_disc('GALP01'));
    routes[(u) => search(u) && query(u).contains('title:("GALP")')] = _search([
      {'identifier': 'melee-en', 'title': 'Super Smash Bros. Melee - DOL-GALP-UKV', 'language': 'eng'},
      {
        'identifier': 'super-smash-bros.-melee-mode-demploi',
        'title': "Super Smash Bros. Melee - Nintendo GameCube - Mode d'emploi - France - IM-DOL-GALP-FRA",
        'language': 'fre',
      },
    ]);
    routes[(u) => u.contains('/metadata/super-smash-bros.-melee-mode-demploi')] = _files([
      {'name': 'Super Smash Bros. Melee - IM-DOL-GALP-FRA.pdf', 'source': 'original', 'size': '32091745'},
      {'name': 'Super Smash Bros. Melee - IM-DOL-GALP-FRA_text.pdf', 'source': 'derivative', 'size': '8905346'},
    ]);
    final found = await GameManualFrenchSources.find(
        _game('Super Smash Bros. Melee', 'gc', romPath: iso.path), 'gc', byTitle: false);
    expect(found?.source, 'archive.org');
    expect(found?.byProduct, isTrue);
    expect(found?.url, endsWith('IM-DOL-GALP-FRA.pdf'), reason: 'the original scan, not the text copy');
    expect(requests.where(search).length, 1, reason: 'the English item is not read');
  });

  test('a huge original scan gives way to the archive\'s compressed copy', () async {
    routes[(u) => search(u)] = _search([
      {
        'identifier': 'mkscm',
        'title': 'Mario Kart: Super Circuit [AGB-AMKP-NEU5] Instruction Booklet',
        'language': ['eng', 'fre'],
        'collection': ['tabor62gbamanual', 'consolemanuals'],
      },
    ]);
    routes[(u) => u.contains('/metadata/mkscm')] = _files([
      {'name': '3.5 Manual Scan.pdf', 'source': 'original', 'size': '737856759'},
      {'name': '3.5 Manual Scan_text.pdf', 'source': 'derivative', 'size': '9778003'},
    ]);
    final found = await GameManualFrenchSources.find(_game('Mario Kart: Super Circuit', 'gba'), 'gba');
    expect(found?.url, endsWith('3.5%20Manual%20Scan_text.pdf'));
    expect(found?.byProduct, isFalse, reason: 'found by title');
  });

  test('by title, only a French item of the same platform counts', () async {
    routes[(u) => search(u)] = _search([
      {'identifier': 'a', 'title': 'Rayman - PlayStation - Notice', 'language': 'fre'},
      {'identifier': 'b', 'title': 'Rayman 2 - Nintendo GameCube - Mode d\'emploi', 'language': 'fre'},
      {'identifier': 'c', 'title': 'Rayman - Game Boy Advance [AGB-ARYP]', 'language': 'eng'},
    ]);
    routes[(u) => u.contains('/metadata/')] = _files([
      {'name': 'm.pdf', 'source': 'original', 'size': '1000'},
    ]);
    expect(await GameManualFrenchSources.find(_game('Rayman', 'gba'), 'gba'), isNull,
        reason: 'PlayStation item, another title, an English item');
    expect((await GameManualFrenchSources.find(_game('Rayman', 'ps1'), 'ps1'))?.url, contains('/download/a/'));
    routes = {
      (u) => search(u): _search([
        {'identifier': 'ps2', 'title': 'Rayman - PlayStation 2 - Notice', 'language': 'fre'},
      ]),
      (u) => u.contains('/metadata/'): _files([
        {'name': 'm.pdf', 'source': 'original', 'size': '1000'},
      ]),
    };
    expect(await GameManualFrenchSources.find(_game('Rayman', 'ps1'), 'ps1'), isNull,
        reason: 'a PlayStation 2 manual is not a PlayStation one');
  });

  test('Nintendo Europe: a DS manual by its title; an unknown name answers a page, not a PDF', () async {
    expect(GameManualFrenchSources.nintendoDsName('Mario Kart DS'), 'MarioKartDS');
    expect(GameManualFrenchSources.nintendoDsName('The Legend of Zelda: Phantom Hourglass'),
        'TheLegendOfZeldaPhantomHourglass');
    expect(GameManualFrenchSources.nintendoDsName('WarioWare: Touched!'), 'WarioWareTouched');
    expect(GameManualFrenchSources.nintendoDsName('New Super Mario Bros. (Europe)'), 'NewSuperMarioBros');
    routes[(u) => u.endsWith('Manual_NintendoDS_MarioKartDS_FR.pdf')] = _pdf;
    routes[(u) => u.contains('Manual_NintendoDS_')] = _page;
    final mk = await GameManualFrenchSources.find(_game('Mario Kart DS', 'ds'), 'ds', byTitle: false);
    expect(mk?.source, 'nintendo.eu');
    expect(mk?.bytes, _pdf, reason: 'downloaded once');
    expect(await GameManualFrenchSources.find(_game('Some Game', 'ds'), 'ds', byTitle: false), isNull);
  });

  test('fill writes a PDF only, and never over a manual already there', () async {
    final target = p.join(dir.path, 'manuals', 'Mario Kart DS.pdf');
    routes[(u) => u.endsWith('Manual_NintendoDS_MarioKartDS_FR.pdf')] = _pdf;
    final found = await GameManualFrenchSources.fill(_game('Mario Kart DS', 'ds'), 'ds', target, byTitle: false);
    expect(found, isNotNull);
    expect(File(target).readAsBytesSync(), _pdf);
    expect(File('$target.part').existsSync(), isFalse);
    requests.clear();
    expect(await GameManualFrenchSources.fill(_game('Mario Kart DS', 'ds'), 'ds', target), isNull);
    expect(requests, isEmpty, reason: 'a manual on the device is kept, nothing is asked');

    final other = p.join(dir.path, 'manuals', 'x.pdf');
    routes = {(u) => search(u): _search([{'identifier': 'x', 'title': 'Zelda - Nintendo DS', 'language': 'fre'}])};
    routes[(u) => u.contains('/metadata/x')] = _files([
      {'name': 'x.pdf', 'source': 'original', 'size': '1000'},
    ]);
    routes[(u) => u.contains('/download/x/')] = _page;
    expect(await GameManualFrenchSources.fill(_game('Zelda', 'ds'), 'ds', other), isNull, reason: 'not a PDF');
    expect(File(other).existsSync(), isFalse);
  });

  test('product codes: the disc id\'s product, the DS and GBA codes, a PS3 serial', () async {
    final nds = Uint8List(0x200)
      ..setAll(0, 'MARIOKART DS'.codeUnits)
      ..setAll(0x0C, 'AMCP'.codeUnits);
    final ndsPath = p.join(dir.path, 'mkds.nds');
    File(ndsPath).writeAsBytesSync(nds);
    expect(await GameManualFrenchSources.productCodes(_game('MKDS', 'ds', romPath: ndsPath), 'ds'), ['AMCP']);
    final gba = Uint8List(0xC0)
      ..setAll(0xAC, 'AMKP'.codeUnits)
      ..[0xB2] = 0x96;
    final gbaPath = p.join(dir.path, 'mksc.gba');
    File(gbaPath).writeAsBytesSync(gba);
    expect(await GameManualFrenchSources.productCodes(_game('MKSC', 'gba', romPath: gbaPath), 'gba'), ['AMKP']);
    final ps3 = GameModel(
      romname: 'x', realname: 'x', name: 'x', year: '', developer: '', publisher: '', genre: '', players: '',
      rating: 0, systemId: 'ps3', titleId: 'BLES00113',
    );
    expect(await GameManualFrenchSources.productCodes(ps3, 'ps3'), ['BLES00113', 'BLES-00113']);
  });
}

Uint8List _disc(String id) {
  final h = Uint8List(0x440)..setAll(0, id.codeUnits);
  h.setAll(0x1C, const [0xC2, 0x33, 0x9F, 0x3D]);
  return h;
}
