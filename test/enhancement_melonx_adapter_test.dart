import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/adapters/melonx_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:path/path.dart' as path;

import 'enhancement_test_support.dart';

/// Super Mario Odyssey's Title ID with three Build IDs. The committed
/// catalogue lists no Switch source (none licenses its codes), so these
/// tests run on made-up records shaped as tools/enhancements writes them.
const _title = '0100000000010000';
const _line = '04000000 00000000 00000001';

Map<String, dynamic> _cheat(String name, List<String> builds, {String cat = 'cheat'}) => {
  'id': name.toLowerCase().replaceAll(RegExp('[^a-z0-9]+'), '-'),
  'cat': cat,
  'name': name,
  'source': 'fixture',
  'builds': {
    for (final build in builds) build: [_line],
  },
};

Map<String, dynamic> _exefsMod(String name, String cat, String group) {
  final bid = '0123456789ABCDEF0123456789ABCDEF${name.length.toRadixString(16).toUpperCase().padLeft(8, '0')}';
  return {
    'id': 'exefs-${name.toLowerCase().replaceAll(RegExp('[^a-z0-9]+'), '-')}',
    'cat': cat,
    'name': name,
    'source': 'fixture',
    'group': group,
    'exefs': [
      {'bid': bid, 'text': '@nsobid-$bid\n@flag offset_shift 0x100\n@enabled\n00001000 1F2003D5\n@stop\n'},
    ],
  };
}

Map<String, dynamic> _record(String title, List<Map<String, dynamic>> entries) => {
  'title': title,
  'master': <String, dynamic>{},
  'credits': ['Fixture'],
  'entries': entries,
};

final _records = <String, Map<String, dynamic>>{
  _title: _record('Super Mario Odyssey', [
    _cheat('9999 Coins Save 1', ['3CA12DFAAF9C82DA', 'F5DCCDDB37E97724']),
    _cheat('Infinite Health', ['B424BE150A8E7D78', 'F5DCCDDB37E97724']),
  ]),
  for (var program = 0; program < 4; program++)
    '010049900F54600$program': _record('Super Mario 3D All-Stars', [
      _cheat('Infinite Lives $program', ['A638857E6DF584F$program']),
    ]),
  '0100A21017C42000': _record("Another Crab's Treasure", [
    _exefsMod('21.9 Ultrawide v1.0.103.9', 'ultrawide', 'display/0100A21017C42000'),
    _exefsMod('4K', 'graphics', 'display/0100A21017C42000'),
  ]),
};

void main() {
  late Directory temp;
  late Directory root;
  late EnhancementService service;
  late MelonxEnhancementAdapter adapter;

  setUp(() {
    temp = Directory.systemTemp.createTempSync('enh-melonx-');
    root = Directory(path.join(temp.path, 'MeloNX'))..createSync();
    adapter = MelonxEnhancementAdapter(
      root: () async => root,
      metadata: (gamePath) async => {'titleId': '0100000000010800', 'version': '1.3.0', 'title': 'SMO'},
    );
    service = EnhancementService(
      catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [adapter],
      texturesSupported: (_) => false,
    );
  });
  tearDown(() => temp.deleteSync(recursive: true));

  final game = testGame(name: 'Super Mario Odyssey', romPath: '/Documents/MeloNX/roms/switch/smo.nsp');
  File enabledList() => File(path.join(root.path, 'mods', 'contents', _title.toLowerCase(), 'cheats', 'enabled.txt'));
  Directory modCheats() =>
      Directory(path.join(root.path, 'mods', 'contents', _title.toLowerCase(), 'RewindBox', 'cheats'));

  test('the page is offered only where an engine or HD textures exist', () async {
    final offline = EnhancementService(
      catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [adapter],
      texturesSupported: (folder) => folder == 'psx',
      embeddedEngines: () => false,
    );
    expect(offline.supports('switch'), isFalse, reason: 'no embedded MeloNX off iOS');
    expect(offline.supports('psx'), isTrue, reason: 'HD textures');
    expect(offline.supports('snes'), isFalse);
    final view = await offline.open(testGame(name: 'Crash'), 'psx');
    expect(view.identity.problem, EnhancementProblem.unsupportedSystem);
    expect(view.items, isEmpty);
    final ios = EnhancementService(
      catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [adapter],
      texturesSupported: (_) => false,
      embeddedEngines: () => true,
    );
    expect(ios.supports('switch'), isTrue);
  });

  test('an update Title ID resolves to its application', () {
    expect(MelonxEnhancementAdapter.applicationTitleId('0100000000010800'), _title);
    expect(MelonxEnhancementAdapter.applicationTitleId('0100000000011000'), '0100000000010000');
    expect(MelonxEnhancementAdapter.applicationTitleId('not a title'), isNull);
  });

  test('the cheat reader matches Ryujinx GetCheatsInFile', () {
    expect(
      MelonxEnhancementAdapter.parseCheatNames(
        '{Master Code}\n04000000 00000000 00000000\n[Moon Jump] // hold B\n80000002\n\n[Empty]\n[Coins]\n04000000 1 2\n',
      ),
      ['<default>', 'Moon Jump', 'Coins'],
    );
    expect(
      MelonxEnhancementAdapter.parseCheatNames('[Broken # name]\n04000000 00000000 00000000\n'),
      isEmpty,
      reason: 'a comment marker inside a name makes Ryujinx skip the whole file',
    );
  });

  test('activation writes Atmosphere files per Build ID and enables only the choice', () async {
    var view = await service.open(game, 'switch', download: true);
    expect(view.identity.key, _title, reason: 'the update Title ID maps to the application');
    expect(view.identity.version, '1.3.0');
    final coins = view.items.firstWhere((item) => item.name == '9999 Coins Save 1');
    expect(coins.status, EnhancementStatus.available);

    view = await service.setActive(game, 'switch', view, coins, true);
    expect(view.items.firstWhere((item) => item.id == coins.id).status, EnhancementStatus.active);
    expect(view.items.where((item) => item.status == EnhancementStatus.installed), isNotEmpty);

    final files = modCheats().listSync().whereType<File>().toList();
    expect(
      files.map((file) => path.basenameWithoutExtension(file.path)),
      containsAll(['3CA12DFAAF9C82DA', 'B424BE150A8E7D78', 'F5DCCDDB37E97724']),
    );
    for (final file in files) {
      final names = MelonxEnhancementAdapter.parseCheatNames(file.readAsStringSync());
      expect(names, isNotEmpty, reason: 'Ryujinx must not skip ${file.path}');
      expect(names, isNot(contains('<default>')), reason: 'every program is named');
    }
    final enabled = enabledList().readAsLinesSync();
    expect(
      enabled,
      containsAll(['3CA12DFAAF9C82DA-<9999 Coins Save 1 Cheat>', 'F5DCCDDB37E97724-<9999 Coins Save 1 Cheat>']),
    );
    expect(enabled.where((line) => line.contains('Infinite Health')), isEmpty);

    // Off again: the files stay installed, the enable list is emptied.
    view = await service.setActive(game, 'switch', view, view.items.firstWhere((i) => i.id == coins.id), false);
    expect(enabledList().readAsStringSync().trim(), isEmpty);
    expect(view.installed, isTrue);
  });

  test('existing cheats of the player stay enabled and restore removes only ours', () async {
    final own =
        File(path.join(root.path, 'mods', 'contents', _title.toLowerCase(), 'Mine', 'cheats', '3CA12DFAAF9C82DA.txt'))
          ..createSync(recursive: true)
          ..writeAsStringSync('[My code]\n04000000 00000000 00000001\n');
    var view = await service.open(game, 'switch', download: true);
    final item = view.items.firstWhere((item) => item.category == EnhancementCategory.cheat);
    view = await service.setActive(game, 'switch', view, item, true);

    // enabled.txt did not exist: the engine enabled every cheat, so must we.
    expect(enabledList().readAsLinesSync(), contains('3CA12DFAAF9C82DA-<My code Cheat>'));

    await service.restore(view.identity.storeKey);
    expect(enabledList().existsSync(), isFalse, reason: 'the list RewindBox created is removed');
    expect(modCheats().existsSync(), isFalse);
    expect(own.readAsStringSync(), contains('[My code]'), reason: 'the player file is untouched');
    expect(await service.games(), isEmpty);
  });

  test('a file of the player at a RewindBox path is never overwritten', () async {
    final view = await service.open(game, 'switch', download: true);
    final file = File(path.join(modCheats().path, '3CA12DFAAF9C82DA.txt'))
      ..createSync(recursive: true)
      ..writeAsStringSync('[Hand made]\n04000000 00000000 00000001\n');
    await expectLater(
      service.setActive(game, 'switch', view, view.items.first, true),
      throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'user_file_present')),
    );
    expect(file.readAsStringSync(), contains('Hand made'));
    expect(enabledList().existsSync(), isFalse, reason: 'nothing was written before the refusal');
  });

  test('a collection writes each sub-program into its own directory', () async {
    final collection = MelonxEnhancementAdapter(
      root: () async => root,
      metadata: (_) async => {'titleId': '010049900F546000', 'version': '1.1.0'},
    );
    final allStars = EnhancementService(
      catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [collection],
      texturesSupported: (_) => false,
    );
    final game = testGame(name: 'Super Mario 3D All-Stars', romPath: '/Documents/MeloNX/3das.nsp');
    var view = await allStars.open(game, 'switch', download: true);
    expect(
      view.items.map((item) => item.compatibility.split(' · ').first).toSet(),
      containsAll(['Title ID 010049900F546000', 'Title ID 010049900F546001', 'Title ID 010049900F546003']),
    );
    final sunshine = view.items.firstWhere((item) => item.compatibility.startsWith('Title ID 010049900F546002'));
    view = await allStars.setActive(game, 'switch', view, sunshine, true);
    final program = File(path.join(root.path, 'mods', 'contents', '010049900f546002', 'cheats', 'enabled.txt'));
    expect(program.readAsStringSync(), contains('<${sunshine.name} Cheat>'));
    expect(
      File(
        path.join(root.path, 'mods', 'contents', '010049900f546000', 'cheats', 'enabled.txt'),
      ).readAsStringSync().trim(),
      isEmpty,
      reason: 'installed, nothing enabled for the other programs',
    );
    await allStars.restore(view.identity.storeKey);
    expect(Directory(path.join(root.path, 'mods', 'contents', '010049900f546002', 'RewindBox')).existsSync(), isFalse);
    expect(program.existsSync(), isFalse);
  });

  test('an exefs mod is written only while on, header first, one display mod at a time', () async {
    final crab = EnhancementService(
      catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [
        MelonxEnhancementAdapter(
          root: () async => root,
          metadata: (_) async => {'titleId': '0100A21017C42000', 'version': '1.0.103.9'},
        ),
      ],
      texturesSupported: (_) => false,
    );
    final game = testGame(name: "Another Crab's Treasure", romPath: '/Documents/MeloNX/act.nsp');
    var view = await crab.open(game, 'switch', download: true);
    final ultrawide = view.items.firstWhere((item) => item.name == '21.9 Ultrawide v1.0.103.9');
    final fourK = view.items.firstWhere((item) => item.name == '4K');
    expect(ultrawide.category, EnhancementCategory.ultrawide);
    expect(ultrawide.status, EnhancementStatus.available);
    expect(ultrawide.exclusiveGroup, fourK.exclusiveGroup, reason: 'both rewrite the render size');
    final exefs = Directory(path.join(root.path, 'mods', 'contents', '0100a21017c42000', 'RewindBox', 'exefs'));

    view = await crab.setActive(game, 'switch', view, ultrawide, true);
    final files = exefs.listSync().whereType<File>().toList();
    expect(files, isNotEmpty);
    for (final file in files) {
      expect(file.path, endsWith('.pchtxt'));
      expect(file.readAsLinesSync().first, matches(RegExp(r'^@nsobid-[0-9A-F]{32,64}$')));
    }

    view = await crab.setActive(game, 'switch', view, view.items.firstWhere((i) => i.id == fourK.id), true);
    expect(view.items.firstWhere((i) => i.id == ultrawide.id).status, EnhancementStatus.available);
    expect(view.items.firstWhere((i) => i.id == fourK.id).status, EnhancementStatus.active);
    expect(exefs.listSync().whereType<File>().every((f) => f.path.contains(fourK.id)), isTrue);

    await crab.restore(view.identity.storeKey);
    expect(exefs.existsSync(), isFalse);
  });

  test('a homebrew Title ID is matched exactly', () {
    expect(
      MelonxEnhancementAdapter.programAliases('0100414D32524000', '0100414D32524E00'),
      contains('0100414D32524E00'),
    );
    expect(MelonxEnhancementAdapter.programAliases(_title, _title), isNot(contains(_title)));
  });

  test('an existing enable list keeps its lines', () async {
    enabledList()
      ..createSync(recursive: true)
      ..writeAsStringSync('0123456789ABCDEF-<Other Cheat>\n');
    var view = await service.open(game, 'switch', download: true);
    view = await service.setActive(game, 'switch', view, view.items.first, true);
    expect(enabledList().readAsLinesSync().first, '0123456789ABCDEF-<Other Cheat>');
    await service.restore(view.identity.storeKey);
    expect(enabledList().readAsLinesSync(), ['0123456789ABCDEF-<Other Cheat>']);
  });
}
