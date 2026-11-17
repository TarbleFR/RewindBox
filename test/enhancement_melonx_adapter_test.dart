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
  // A fighting game shaped like the catalogue's Smash Bros. record: FPS codes named after their target, for the
  // update's build and an older one.
  _fighter: _record('Fighter', [
    _cheat('120 FPS (Emulator)', [_update, _older], cat: 'fps'),
    _cheat('30 FPS', [_update, _older], cat: 'fps'),
    _cheat('FPS Unlock', [_update], cat: 'fps'),
    _cheat('P1 0% damage', [_older]),
  ]),
};

const _fighter = '0100F1F1F1F1E000';
const _base = '1111222233334444';
const _update = 'B9B166DF1DB90BAF';
const _older = '77104350C9768709';

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

    // Only the chosen program is on disk: a lost enable list cannot run the others.
    final files = modCheats().listSync().whereType<File>().toList();
    expect(
      files.map((file) => path.basenameWithoutExtension(file.path)).toSet(),
      {'3CA12DFAAF9C82DA', 'F5DCCDDB37E97724'},
    );
    for (final file in files) {
      final names = MelonxEnhancementAdapter.parseCheatNames(file.readAsStringSync());
      expect(names, ['9999 Coins Save 1'], reason: 'Ryujinx must read exactly the chosen program in ${file.path}');
    }
    final enabled = enabledList().readAsLinesSync();
    expect(
      enabled,
      containsAll(['3CA12DFAAF9C82DA-<9999 Coins Save 1 Cheat>', 'F5DCCDDB37E97724-<9999 Coins Save 1 Cheat>']),
    );
    expect(enabled.where((line) => line.contains('Infinite Health')), isEmpty);

    // Off again: no RewindBox code stays on disk and the enable list is emptied.
    view = await service.setActive(game, 'switch', view, view.items.firstWhere((i) => i.id == coins.id), false);
    expect(enabledList().readAsStringSync().trim(), isEmpty);
    expect(modCheats().existsSync() ? modCheats().listSync().whereType<File>() : const <File>[], isEmpty);
    expect(view.installed, isTrue);
  });

  test('an old absolute key is re-rooted at the MeloNX segment that holds mods', () {
    final now = Directory('/new/Documents/MeloNX');
    expect(
      MelonxEnhancementAdapter.resolveStateKey(now, '/old/Documents/MeloNX/mods/contents/t/RewindBox/MeloNX/x.txt'),
      '/new/Documents/MeloNX/mods/contents/t/RewindBox/MeloNX/x.txt',
    );
    expect(MelonxEnhancementAdapter.resolveStateKey(now, 'mods/contents/t/a.txt'), '/new/Documents/MeloNX/mods/contents/t/a.txt');
    expect(MelonxEnhancementAdapter.resolveStateKey(now, '/elsewhere/file.txt'), '/elsewhere/file.txt');
  });

  test('after the app container moves, RewindBox still owns its files', () async {
    var view = await service.open(game, 'switch', download: true);
    view = await service.setActive(game, 'switch', view, view.items.first, true);
    // Keys written by an older version were absolute, in a container iOS has since moved.
    final store = EnhancementStore(root: () async => Directory(path.join(temp.path, 'store')));
    await store.transaction((games) async {
      final state = games.values.single;
      final moved = {
        for (final entry in state.files.entries)
          path.join('/var/mobile/Containers/Data/Application/OLD-CONTAINER/Documents/MeloNX', entry.key): entry.value,
      };
      state.files
        ..clear()
        ..addAll(moved);
    });

    // Turning the code off rewrites RewindBox's own file instead of refusing it as the player's.
    view = await service.setActive(game, 'switch', view, view.items.first, false);
    expect(enabledList().readAsStringSync().trim(), isEmpty);
    await service.restore(view.identity.storeKey);
    expect(modCheats().existsSync(), isFalse, reason: 'restore finds and removes the files after the move');
    expect(enabledList().existsSync(), isFalse);
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

  test('RewindBox cheat files without an enable list are all disabled before a launch', () async {
    // Hogwarts Legacy case: the catalogue file is on disk, the enable list is gone, so the engine enabled every program.
    var view = await service.open(game, 'switch', download: true);
    view = await service.setActive(game, 'switch', view, view.items.first, true);
    expect(modCheats().listSync().whereType<File>(), isNotEmpty);
    enabledList().deleteSync();
    // A cheat file of the player's own keeps the engine default: still enabled.
    File(path.join(root.path, 'mods', 'contents', _title.toLowerCase(), 'cheats', '0123456789ABCDEF.txt'))
        .writeAsStringSync('[Own Code]\n$_line\n');

    final repaired = await MelonxEnhancementAdapter.disableUnchosenCatalogueCheats(root, const {});

    expect(repaired, [_title.toLowerCase()]);
    expect(enabledList().readAsLinesSync(), ['0123456789ABCDEF-<Own Code Cheat>']);
  });

  test('catalogue codes listed but not chosen in RewindBox are removed; chosen ones stay', () async {
    var view = await service.open(game, 'switch', download: true);
    final coins = view.items.firstWhere((item) => item.name == '9999 Coins Save 1');
    view = await service.setActive(game, 'switch', view, coins, true);
    final chosen = MelonxEnhancementAdapter.chosenKeys(await service.store.all());
    expect(chosen, containsAll(['3CA12DFAAF9C82DA-<9999 Coins Save 1 Cheat>', 'F5DCCDDB37E97724-<9999 Coins Save 1 Cheat>']));
    expect(await MelonxEnhancementAdapter.disableUnchosenCatalogueCheats(root, chosen), isEmpty, reason: 'nothing to change');

    // The same list with nothing recorded as chosen (an older version, or no way left to turn them off): all removed,
    // the player's other lines kept.
    enabledList().writeAsStringSync('${enabledList().readAsStringSync()}0123456789ABCDEF-<Other Cheat>\n');
    expect(await MelonxEnhancementAdapter.disableUnchosenCatalogueCheats(root, const {}), [_title.toLowerCase()]);
    expect(enabledList().readAsLinesSync(), ['0123456789ABCDEF-<Other Cheat>']);
  });

  test('an existing enable list and titles without RewindBox files are left alone', () async {
    var view = await service.open(game, 'switch', download: true);
    view = await service.setActive(game, 'switch', view, view.items.first, true);
    final before = enabledList().readAsStringSync();
    final other = Directory(path.join(root.path, 'mods', 'contents', '0100f7e00c70e000', 'cheats'))
      ..createSync(recursive: true);
    File(path.join(other.path, '0123456789ABCDEF.txt')).writeAsStringSync('[Own Code]\n$_line\n');

    final chosen = MelonxEnhancementAdapter.chosenKeys(await service.store.all());
    expect(await MelonxEnhancementAdapter.disableUnchosenCatalogueCheats(root, chosen), isEmpty);
    expect(enabledList().readAsStringSync(), before);
    expect(File(path.join(other.path, 'enabled.txt')).existsSync(), isFalse);
    expect(await MelonxEnhancementAdapter.disableUnchosenCatalogueCheats(Directory(path.join(temp.path, 'none')), chosen), isEmpty);
  });

  group('installed build', () {
    MelonxEnhancementAdapter withBuild(String? build, {String title = _title, Map<String, dynamic>? update, bool refresh = false}) =>
        MelonxEnhancementAdapter(
          root: () async => root,
          metadata: (_) async => {'titleId': title, 'version': '1.0.0', 'buildId': ?build},
          inspectUpdate: (updatePath, titleId) async {
            expect(titleId, title.toLowerCase(), reason: 'the update is inspected for its base title');
            if (update == null) throw StateError('unreadable');
            return update;
          },
          refreshSupported: () async => refresh,
        );
    EnhancementService serviceWith(MelonxEnhancementAdapter adapter) => EnhancementService(
      catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [adapter],
      texturesSupported: (_) => false,
    );
    void selectUpdate(String title) {
      final file = File(path.join(root.path, 'addons', title.toLowerCase(), 'update.nsp'))..createSync(recursive: true);
      File(path.join(root.path, 'games', title.toLowerCase(), 'updates.json'))
        ..createSync(recursive: true)
        ..writeAsStringSync('{"selected":"${path.relative(file.path, from: root.path)}","paths":[]}');
    }

    test('a code for another build is incompatible and never counted active', () async {
      final service = serviceWith(withBuild('3CA12DFAAF9C82DA'));
      var view = await service.open(game, 'switch', download: true);
      final coins = view.items.firstWhere((item) => item.name == '9999 Coins Save 1');
      final health = view.items.firstWhere((item) => item.name == 'Infinite Health');
      expect(coins.status, EnhancementStatus.available);
      expect(health.status, EnhancementStatus.incompatible);
      expect(health.problem, EnhancementProblem.versionMismatch);
      expect(health.compatibility, endsWith('installed 3CA12DFAAF9C82DA'));
      expect(MelonxEnhancementAdapter.unmatchedBuild(view.items), isNull, reason: 'one code matches');
      await expectLater(
        service.setActive(game, 'switch', view, health, true),
        throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'incompatible')),
      );

      // A code turned on for an earlier build (the update changed) stays off the count.
      await service.store.transaction((games) async {
        games['melonx:$_title'] = EnhancementGameState(
          storeKey: 'melonx:$_title',
          engine: 'melonx',
          key: _title,
          installed: true,
          active: {health.id},
        );
      });
      view = await service.open(game, 'switch', download: true);
      expect(view.items.firstWhere((item) => item.id == health.id).status, EnhancementStatus.incompatible);
      expect(view.activeCount, 0);
      view = await service.setActive(game, 'switch', view, view.items.firstWhere((item) => item.id == coins.id), true);
      expect((await service.store.game('melonx:$_title'))!.active, {coins.id}, reason: 'the incompatible code is dropped');
      expect(view.activeCount, 1);
    });

    test('when no code is for the installed build, the page gets the catalogue builds', () async {
      final view = await serviceWith(withBuild('0123456789abcdef')).open(game, 'switch', download: true);
      expect(view.items.every((item) => item.status == EnhancementStatus.incompatible), isTrue);
      final unmatched = MelonxEnhancementAdapter.unmatchedBuild(view.items)!;
      expect(unmatched.build, '0123456789ABCDEF');
      expect(unmatched.targets, ['3CA12DFAAF9C82DA', 'B424BE150A8E7D78', 'F5DCCDDB37E97724']);
    });

    test('the selected update is what runs; an unreadable one leaves every code as before', () async {
      selectUpdate(_title);
      var view = await serviceWith(withBuild('B424BE150A8E7D78', update: {'buildId': '3CA12DFAAF9C82DA'}))
          .open(game, 'switch', download: true);
      expect(view.items.firstWhere((item) => item.name == '9999 Coins Save 1').status, EnhancementStatus.available);
      expect(view.items.firstWhere((item) => item.name == 'Infinite Health').status, EnhancementStatus.incompatible,
          reason: 'the base build matches it, the selected update does not');

      view = await serviceWith(withBuild('B424BE150A8E7D78')).open(game, 'switch', download: true);
      expect(view.items.map((item) => item.status).toSet(), {EnhancementStatus.available});
      expect(view.items.any((item) => item.payload.containsKey('installedBuild')), isFalse);
    });

    test('an engine without buildId (older Core) changes nothing', () async {
      final view = await service.open(game, 'switch', download: true);
      expect(view.items.map((item) => item.status).toSet(), {EnhancementStatus.available});
      expect(view.items.every((item) => item.problem == EnhancementProblem.none), isTrue);
      expect(view.items.firstWhere((item) => item.name == 'Infinite Health').compatibility,
          'Title ID $_title · Build ID B424BE150A8E7D78, F5DCCDDB37E97724');
      expect(MelonxEnhancementAdapter.unmatchedBuild(view.items), isNull);
      expect(MelonxEnhancementAdapter.buildIdOf('0000000000000000'), isNull);
      expect(MelonxEnhancementAdapter.buildIdOf('b9b166df1db90baf'), 'B9B166DF1DB90BAF');
      expect(MelonxEnhancementAdapter.buildIdOf('B9B166DF1DB90BAF00'), isNull);
    });

    test("a collection's other programs keep their status", () async {
      final view = await serviceWith(withBuild('9999999999999999', title: '010049900F546000'))
          .open(testGame(name: 'Super Mario 3D All-Stars', romPath: '/Documents/MeloNX/3das.nsp'), 'switch', download: true);
      final byProgram = {for (final item in view.items) item.compatibility.split(' · ').first: item.status};
      expect(byProgram['Title ID 010049900F546000'], EnhancementStatus.incompatible);
      expect(byProgram['Title ID 010049900F546001'], EnhancementStatus.available);
      expect(byProgram['Title ID 010049900F546003'], EnhancementStatus.available);
      expect(MelonxEnhancementAdapter.unmatchedBuild(view.items), isNotNull);
    });
  });

  group('engine refresh of an FPS code', () {
    final fighter = testGame(name: 'Fighter', romPath: '/Documents/MeloNX/roms/switch/fighter.nsp');
    late MelonxEnhancementAdapter adapter;
    late EnhancementService service;
    var supported = true;
    Future<int?> launch({Map<String, dynamic>? update}) => MelonxEnhancementAdapter.launchRefresh(
      fighter.romPath!,
      states: service.store.all,
      root: () async => root,
      metadata: (_) async => {'titleId': _fighter, 'buildId': _base},
      inspectUpdate: (_, _) async => update ?? {'buildId': _update},
      supported: () async => supported,
    );
    EnhancementItem named(EnhancementGameView view, String name) => view.items.firstWhere((item) => item.name == name);

    setUp(() {
      supported = true;
      final file = File(path.join(root.path, 'addons', _fighter.toLowerCase(), 'update.nsp'))..createSync(recursive: true);
      File(path.join(root.path, 'games', _fighter.toLowerCase(), 'updates.json'))
        ..createSync(recursive: true)
        ..writeAsStringSync('{"selected":"${path.relative(file.path, from: root.path)}"}');
      adapter = MelonxEnhancementAdapter(
        root: () async => root,
        metadata: (_) async => {'titleId': _fighter, 'version': '13.0.3', 'buildId': _base},
        inspectUpdate: (_, _) async => {'buildId': _update},
        refreshSupported: () async => supported,
      );
      service = EnhancementService(
        catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
        store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
        adapters: [adapter],
        texturesSupported: (_) => false,
      );
    });

    test('the target comes from the name, within what the engine takes', () {
      expect(MelonxEnhancementAdapter.refreshTarget('120 FPS (Emulator)'), 120);
      expect(MelonxEnhancementAdapter.refreshTarget('Default 60 FPS'), 60);
      expect(MelonxEnhancementAdapter.refreshTarget('60fps mode'), 60);
      expect(MelonxEnhancementAdapter.refreshTarget('30 FPS'), 30);
      expect(MelonxEnhancementAdapter.refreshTarget('FPS Unlock'), isNull);
      expect(MelonxEnhancementAdapter.refreshTarget('20 FPS'), isNull);
      expect(MelonxEnhancementAdapter.refreshTarget('300 FPS'), isNull);
      expect(MelonxEnhancementAdapter.refreshTarget('1000 FPS'), isNull);
    });

    test('on for the build that runs: the launch carries the target and the page says so', () async {
      var view = await service.open(fighter, 'switch', download: true);
      expect(named(view, 'P1 0% damage').status, EnhancementStatus.incompatible, reason: 'only for the older build');
      expect(named(view, '120 FPS (Emulator)').payload['refreshHz'], 120);
      expect(named(view, 'FPS Unlock').payload.containsKey('refreshHz'), isFalse);
      expect(await launch(), isNull, reason: 'nothing is on yet');

      view = await service.setActive(fighter, 'switch', view, named(view, '120 FPS (Emulator)'), true);
      expect(MelonxEnhancementAdapter.engineRefresh(view.items), 120);
      expect(await launch(), 120);
      final refresh = (await service.store.game('melonx:$_fighter'))!.data['refresh'] as Map;
      expect(refresh[_update], {'hz': 120, 'program': _fighter.toLowerCase(), 'keys': ['$_update-<120 FPS (Emulator) Cheat>']});

      // Another build runs (the update was changed): the code would not be installed, the refresh stays.
      expect(await launch(update: {'buildId': _base}), isNull);
      expect(await launch(update: {}), isNull, reason: 'unknown build');

      // Off again: the player's VSync choice applies.
      view = await service.setActive(fighter, 'switch', view, named(view, '120 FPS (Emulator)'), false);
      expect(MelonxEnhancementAdapter.engineRefresh(view.items), isNull);
      expect(await launch(), isNull);
      expect((await service.store.game('melonx:$_fighter'))!.data.containsKey('refresh'), isFalse);
    });

    test('an engine without vsyncFps is never sent it', () async {
      supported = false;
      var view = await service.open(fighter, 'switch', download: true);
      expect(named(view, '120 FPS (Emulator)').payload.containsKey('refreshHz'), isFalse);
      view = await service.setActive(fighter, 'switch', view, named(view, '120 FPS (Emulator)'), true);
      expect(MelonxEnhancementAdapter.engineRefresh(view.items), isNull);
      expect(await launch(), isNull);
    });

    test('a code the engine would not install, or two targets at once, set no refresh', () async {
      var view = await service.open(fighter, 'switch', download: true);
      view = await service.setActive(fighter, 'switch', view, named(view, '120 FPS (Emulator)'), true);
      final enabled = File(path.join(root.path, 'mods', 'contents', _fighter.toLowerCase(), 'cheats', 'enabled.txt'));
      final before = enabled.readAsStringSync();
      enabled.writeAsStringSync(before.replaceAll('$_update-<120 FPS (Emulator) Cheat>', ''));
      expect(await launch(), isNull, reason: 'the enable list no longer names it');
      enabled.writeAsStringSync(before);
      expect(await launch(), 120);
      File(path.join(root.path, 'mods', 'contents', _fighter.toLowerCase(), 'RewindBox', 'cheats', '$_update.txt')).deleteSync();
      expect(await launch(), isNull, reason: 'its file is gone');

      view = await service.setActive(fighter, 'switch', view, named(view, '120 FPS (Emulator)'), true);
      view = await service.setActive(fighter, 'switch', view, named(view, '30 FPS'), true);
      expect(MelonxEnhancementAdapter.engineRefresh(view.items), isNull);
      expect(await launch(), isNull);
      expect(
        await MelonxEnhancementAdapter.launchRefresh(fighter.romPath!, states: () async => throw StateError('store'), supported: () async => true),
        isNull,
        reason: 'never throws',
      );
    });

    test('the Core marker is searched as UTF-16 text', () {
      final bundle = Directory(path.join(temp.path, 'Runner.app'));
      final core = File(path.join(bundle.path, 'Frameworks', 'MeloNXCore.framework', 'MeloNXCore'))..createSync(recursive: true);
      core.writeAsBytesSync([0, 1, 2]);
      expect(MelonxEnhancementAdapter.refreshSupportedIn(bundle.path), isFalse);
      final marker = MelonxEnhancementAdapter.refreshMarker;
      core.writeAsBytesSync([
        ...List.filled(7, 0),
        for (final unit in marker.codeUnits) ...[unit & 0xFF, unit >> 8],
      ]);
      expect(MelonxEnhancementAdapter.refreshSupportedIn(bundle.path), isTrue);
      expect(MelonxEnhancementAdapter.refreshSupportedIn(path.join(temp.path, 'none')), isFalse);
    });
  });
}
