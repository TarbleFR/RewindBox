import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/adapters/melonx_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:path/path.dart' as path;

import 'enhancement_test_support.dart';

/// Super Mario Odyssey: three Build IDs in the pinned switch-cheats-db.
const _title = '0100000000010000';

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
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
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
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
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
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
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
    expect(MelonxEnhancementAdapter.parseCheatNames('[Broken # name]\n04000000 00000000 00000000\n'), isEmpty,
        reason: 'a comment marker inside a name makes Ryujinx skip the whole file');
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
    expect(files.map((file) => path.basenameWithoutExtension(file.path)),
        containsAll(['3CA12DFAAF9C82DA', 'B424BE150A8E7D78', 'F5DCCDDB37E97724']));
    for (final file in files) {
      final names = MelonxEnhancementAdapter.parseCheatNames(file.readAsStringSync());
      expect(names, isNotEmpty, reason: 'Ryujinx must not skip ${file.path}');
      expect(names, isNot(contains('<default>')), reason: 'every program is named');
    }
    final enabled = enabledList().readAsLinesSync();
    expect(enabled, containsAll([
      '3CA12DFAAF9C82DA-<9999 Coins Save 1 Cheat>',
      'F5DCCDDB37E97724-<9999 Coins Save 1 Cheat>',
    ]));
    expect(enabled.where((line) => line.contains('Infinite Health')), isEmpty);

    // Off again: the files stay installed, the enable list is emptied.
    view = await service.setActive(game, 'switch', view, view.items.firstWhere((i) => i.id == coins.id), false);
    expect(enabledList().readAsStringSync().trim(), isEmpty);
    expect(view.installed, isTrue);
  });

  test('existing cheats of the player stay enabled and restore removes only ours', () async {
    final own = File(path.join(root.path, 'mods', 'contents', _title.toLowerCase(), 'Mine', 'cheats',
        '3CA12DFAAF9C82DA.txt'))
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
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [collection],
      texturesSupported: (_) => false,
    );
    final game = testGame(name: 'Super Mario 3D All-Stars', romPath: '/Documents/MeloNX/3das.nsp');
    var view = await allStars.open(game, 'switch', download: true);
    expect(view.items.map((item) => item.compatibility.split(' · ').first).toSet(),
        containsAll(['Title ID 010049900F546000', 'Title ID 010049900F546001', 'Title ID 010049900F546003']));
    final sunshine = view.items.firstWhere((item) => item.compatibility.startsWith('Title ID 010049900F546002'));
    view = await allStars.setActive(game, 'switch', view, sunshine, true);
    final program = File(path.join(root.path, 'mods', 'contents', '010049900f546002', 'cheats', 'enabled.txt'));
    expect(program.readAsStringSync(), contains('<${sunshine.name} Cheat>'));
    expect(File(path.join(root.path, 'mods', 'contents', '010049900f546000', 'cheats', 'enabled.txt')).readAsStringSync().trim(),
        isEmpty, reason: 'installed, nothing enabled for the other programs');
    await allStars.restore(view.identity.storeKey);
    expect(Directory(path.join(root.path, 'mods', 'contents', '010049900f546002', 'RewindBox')).existsSync(), isFalse);
    expect(program.existsSync(), isFalse);
  });

  test('a homebrew Title ID is matched exactly', () {
    expect(MelonxEnhancementAdapter.programAliases('0100414D32524000', '0100414D32524E00'),
        contains('0100414D32524E00'));
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
