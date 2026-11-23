import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
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
  _strikers: {
    ..._record('Mario Strikers: Battle League', [
      _exefsFor('120FPS v1.3.2', 'fps', 'display/$_strikers', _strikersBuild),
      _exefsFor('60 FPS v1.3.2', 'fps', 'display/$_strikers', _strikersBuild),
      _exefsFor('1920x1080 v1.3.2', 'graphics', 'display/$_strikers', _strikersBuild),
      _exefsFor('21.9 Ultrawide v1.3.2', 'ultrawide', 'display/$_strikers', _strikersBuild),
      _cheat('Infinite Stamina', [_strikersOld]),
    ]),
    'releases': {
      _strikersBuild: {'display': ['1.3.2'], 'update': [196608]},
      _strikersOld: {'display': ['1.3.0']},
    },
  },
  _fighter: _record('Fighter', [
    _cheat('120 FPS (Emulator)', [_update, _older], cat: 'fps'),
    _cheat('30 FPS', [_update, _older], cat: 'fps'),
    _cheat('FPS Unlock', [_update], cat: 'fps'),
    _cheat('P1 0% damage', [_older]),
  ]),
};

// Shaped like the published Mario Strikers record: Fl4sh9174 mods whose names carry the game version
// (`v1.3.2`), all of them grouped as display choices by the catalogue of 18 November 2026.
const _strikers = '010019401051C000';
const _strikersBuild = '2E90F0815B1F92A1';
const _strikersOld = '7F7710633C020A32';

Map<String, dynamic> _exefsFor(String name, String cat, String group, String build) {
  final bid = '$build${'0' * 16}';
  return {
    'id': 'fl4sh-${name.toLowerCase().replaceAll(RegExp('[^a-z0-9]+'), '-')}',
    'cat': cat,
    'name': name,
    'source': 'fixture',
    'group': group,
    'exefs': [
      {'bid': bid, 'text': '@nsobid-$bid\n@enabled\n00001000 1F2003D5\n@stop\n'},
    ],
  };
}

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
          'Title ID $_title · Build ID B424BE150A8E7D78, F5DCCDDB37E97724 · installed version 1.3.0');
      expect(MelonxEnhancementAdapter.buildUnknown(view.items), isTrue, reason: 'the page says it cannot tell');
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

  group('frame-rate mods and game versions', () {
    final strikers = testGame(name: 'Mario Strikers', romPath: '/Documents/MeloNX/roms/switch/strikers.nsp');
    EnhancementService serviceFor(Map<String, dynamic> metadata, {Map<String, dynamic>? update, bool refresh = true}) =>
        EnhancementService(
          catalog: fixtureCatalog(Directory(path.join(temp.path, 'cache')), {'melonx': _records}),
          store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
          adapters: [
            MelonxEnhancementAdapter(
              root: () async => root,
              metadata: (_) async => metadata,
              inspectUpdate: (_, _) async => update ?? (throw StateError('unreadable')),
              refreshSupported: () async => refresh,
            ),
          ],
          texturesSupported: (_) => false,
        );
    EnhancementItem named(EnhancementGameView view, String name) => view.items.firstWhere((item) => item.name == name);
    Set<String> active(EnhancementGameView view) => {
      for (final item in view.items)
        if (item.status == EnhancementStatus.active) item.name,
    };

    test('a frame-rate mod stays on with a resolution or ultrawide mod; frame-rate mods exclude each other', () async {
      final service = serviceFor({'titleId': _strikers, 'version': '1.3.2', 'buildId': _strikersBuild});
      var view = await service.open(strikers, 'switch', download: true);
      expect(named(view, '120FPS v1.3.2').exclusiveGroup, 'fps/$_strikers');
      expect(named(view, '1920x1080 v1.3.2').exclusiveGroup, 'display/$_strikers');

      view = await service.setActive(strikers, 'switch', view, named(view, '120FPS v1.3.2'), true);
      view = await service.setActive(strikers, 'switch', view, named(view, '1920x1080 v1.3.2'), true);
      expect(active(view), {'120FPS v1.3.2', '1920x1080 v1.3.2'}, reason: 'the resolution mod no longer turns the 120 FPS mod off');
      view = await service.setActive(strikers, 'switch', view, named(view, '21.9 Ultrawide v1.3.2'), true);
      expect(active(view), {'120FPS v1.3.2', '21.9 Ultrawide v1.3.2'}, reason: 'display choices still exclude each other');

      // Kept across a new opening of the page (the store and the written patch files agree).
      view = await service.open(strikers, 'switch', download: true);
      expect(active(view), {'120FPS v1.3.2', '21.9 Ultrawide v1.3.2'});
      final exefs = Directory(path.join(root.path, 'mods', 'contents', _strikers.toLowerCase(), 'RewindBox', 'exefs'));
      expect(exefs.listSync().map((file) => path.basename(file.path)).toSet(),
          {'fl4sh-120fps-v1-3-2-0.pchtxt', 'fl4sh-21-9-ultrawide-v1-3-2-0.pchtxt'});

      view = await service.setActive(strikers, 'switch', view, named(view, '60 FPS v1.3.2'), true);
      expect(active(view), {'60 FPS v1.3.2', '21.9 Ultrawide v1.3.2'}, reason: 'one frame-rate mod at a time');
    });

    test('an exefs frame-rate mod on for the build that runs sets the engine refresh at launch', () async {
      final service = serviceFor({'titleId': _strikers, 'version': '1.3.2', 'buildId': _strikersBuild});
      Future<int?> launch() => MelonxEnhancementAdapter.launchRefresh(
        strikers.romPath!,
        states: service.store.all,
        root: () async => root,
        metadata: (_) async => {'titleId': _strikers, 'buildId': _strikersBuild},
        inspectUpdate: (_, _) async => throw StateError('none selected'),
        supported: () async => true,
      );
      var view = await service.open(strikers, 'switch', download: true);
      expect(named(view, '120FPS v1.3.2').payload['refreshHz'], 120);
      view = await service.setActive(strikers, 'switch', view, named(view, '120FPS v1.3.2'), true);
      expect(MelonxEnhancementAdapter.engineRefresh(view.items), 120);
      expect(await launch(), 120);
      final refresh = (await service.store.game('melonx:$_strikers'))!.data['refresh'] as Map;
      expect(refresh[_strikersBuild]['exefs'], ['fl4sh-120fps-v1-3-2-0.pchtxt']);

      File(path.join(root.path, 'mods', 'contents', _strikers.toLowerCase(), 'RewindBox', 'exefs',
              'fl4sh-120fps-v1-3-2-0.pchtxt'))
          .deleteSync();
      expect(await launch(), isNull, reason: 'its patch file is gone');
    });

    test('a selected update that cannot be found leaves the build unknown, not the game file\'s', () async {
      File(path.join(root.path, 'games', _strikers.toLowerCase(), 'updates.json'))
        ..createSync(recursive: true)
        ..writeAsStringSync('{"selected":"addons/${_strikers.toLowerCase()}/gone.nsp"}');
      expect(
        await MelonxEnhancementAdapter.installedBuild(
          root: root,
          titleId: _strikers,
          baseBuild: _strikersOld,
          inspectUpdate: (_, _) async => {'buildId': _strikersBuild},
        ),
        isNull,
      );
      final view = await serviceFor({'titleId': _strikers, 'version': '1.3.0', 'buildId': _strikersOld})
          .open(strikers, 'switch', download: true);
      expect(named(view, 'Infinite Stamina').status, EnhancementStatus.available,
          reason: 'the game file\'s build is not what runs: nothing is claimed');
      expect(view.identity.version, isNull, reason: 'the update\'s version is unknown');
      expect(view.items.any((item) => item.payload.containsKey('installedBuild')), isFalse);
      expect(MelonxEnhancementAdapter.buildUnknown(view.items), isTrue);
    });

    test('without the engine\'s Build ID, the version that runs names its build through the catalogue', () async {
      final view = await serviceFor({'titleId': _strikers, 'version': '1.3.0'}).open(strikers, 'switch', download: true);
      expect(view.identity.version, '1.3.0');
      expect(named(view, 'Infinite Stamina').status, EnhancementStatus.available);
      final mod = named(view, '120FPS v1.3.2');
      expect(mod.status, EnhancementStatus.incompatible);
      expect(mod.problem, EnhancementProblem.versionMismatch);
      expect(mod.compatibility, 'Title ID $_strikers · exefs Build ID $_strikersBuild (1.3.2, v196608) · installed version 1.3.0');
      expect(mod.payload.containsKey('refreshHz'), isFalse, reason: 'only a build the engine reports raises the refresh');
      expect(MelonxEnhancementAdapter.buildUnknown(view.items), isFalse);
      await expectLater(
        serviceFor({'titleId': _strikers, 'version': '1.3.0'}).setActive(strikers, 'switch', view, mod, true),
        throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'incompatible')),
      );

      // An update reports its display version: that is the version that runs.
      final file = File(path.join(root.path, 'addons', _strikers.toLowerCase(), 'update.nsp'))..createSync(recursive: true);
      File(path.join(root.path, 'games', _strikers.toLowerCase(), 'updates.json'))
        ..createSync(recursive: true)
        ..writeAsStringSync('{"selected":"${path.relative(file.path, from: root.path)}"}');
      final updated = await serviceFor({'titleId': _strikers, 'version': '1.3.0'}, update: {'displayVersion': '1.3.2'})
          .open(strikers, 'switch', download: true);
      expect(updated.identity.version, '1.3.2');
      expect(named(updated, '120FPS v1.3.2').status, EnhancementStatus.available);
      expect(named(updated, 'Infinite Stamina').status, EnhancementStatus.incompatible);
    });

    test('an active exefs mod whose patch file cannot be fetched stays on while another entry is switched', () async {
      const origin = 'https://raw.githubusercontent.com/example/pchtxt/0123456789012345678901234567890123456789/';
      final bid = '$_strikersBuild${'0' * 16}';
      final files = <String, Uint8List>{};
      Map<String, dynamic> mod(String name, String cat, int index) {
        final text = '@nsobid-$bid\n@enabled\n0000${index}000 1F2003D5\n@stop\n';
        final bytes = Uint8List.fromList(utf8.encode(text));
        files['${origin}Strikers/$_strikers/$name/exefs/1.3.2.pchtxt'] = bytes;
        return {
          'id': 'origin-${name.toLowerCase()}',
          'cat': cat,
          'name': name,
          'source': 'pchtxt',
          'exefs': [
            {'bid': bid, 'o': index, 'size': bytes.length, 'sha256': sha256.convert(bytes).toString()},
          ],
        };
      }
      final entries = [mod('120FPS', 'fps', 0), mod('1440p', 'graphics', 1), mod('Disable DOF', 'graphics', 2)];
      final records = {
        'melonx': {
          _strikers: {
            'title': 'Strikers',
            'master': <String, dynamic>{},
            'credits': <String>[],
            'entries': entries,
            'origin': [
              for (final entry in entries)
                {
                  'source': 'pchtxt',
                  'path': 'Strikers/$_strikers/${entry['name']}/exefs/1.3.2.pchtxt',
                  'size': files['${origin}Strikers/$_strikers/${entry['name']}/exefs/1.3.2.pchtxt']!.length,
                  'sha256': sha256
                      .convert(files['${origin}Strikers/$_strikers/${entry['name']}/exefs/1.3.2.pchtxt']!)
                      .toString(),
                },
            ],
          },
        },
      };
      final sources = [
        {'id': 'pchtxt', 'name': 'Example', 'url': 'https://example.org', 'license': 'None', 'origin': origin, 'engines': ['melonx'], 'revision': 'x'},
      ];
      EnhancementService serving(String cache, Map<String, Uint8List> served) => EnhancementService(
        catalog: fixtureCatalog(Directory(path.join(temp.path, cache)), records, sources: sources, origins: served),
        store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
        adapters: [
          MelonxEnhancementAdapter(
            root: () async => root,
            metadata: (_) async => {'titleId': _strikers, 'buildId': _strikersBuild},
            refreshSupported: () async => true,
          ),
        ],
        texturesSupported: (_) => false,
      );
      final exefs = Directory(path.join(root.path, 'mods', 'contents', _strikers.toLowerCase(), 'RewindBox', 'exefs'));

      var online = serving('cache-online', files);
      var view = await online.open(strikers, 'switch', download: true);
      view = await online.setActive(strikers, 'switch', view, named(view, '120FPS'), true);
      expect(File(path.join(exefs.path, 'origin-120fps-0.pchtxt')).existsSync(), isTrue);

      // A new device cache, offline for the 120 FPS patch file: the mod is not listed, and turning another entry on
      // keeps it on, with its file and the refresh it sets.
      final offline = serving('cache-offline', {
        for (final file in files.entries)
          if (!file.key.contains('/120FPS/')) file.key: file.value,
      });
      view = await offline.open(strikers, 'switch', download: true);
      expect(view.items.map((item) => item.name), isNot(contains('120FPS')));
      view = await offline.setActive(strikers, 'switch', view, named(view, '1440p'), true);
      final state = (await offline.store.game('melonx:$_strikers'))!;
      expect(state.active, {'origin-120fps', 'origin-1440p'});
      expect(File(path.join(exefs.path, 'origin-120fps-0.pchtxt')).existsSync(), isTrue);
      expect((state.data['refresh'] as Map)[_strikersBuild]['hz'], 120);

      // Back online: listed and on as before; another frame-rate choice would replace it as usual.
      online = serving('cache-online', files);
      view = await online.open(strikers, 'switch', download: true);
      expect(active(view), {'120FPS', '1440p'});
    });

    test('catalogue versions read from a record, and names that only carry a version', () {
      final releases = MelonxEnhancementAdapter.releasesOf(_records[_strikers]!, _strikers);
      expect(releases, {_strikersBuild: ['1.3.2', 'v196608'], _strikersOld: ['1.3.0']});
      expect(MelonxEnhancementAdapter.buildsOfVersion(releases, 'v1.3.2'), {_strikersBuild});
      expect(MelonxEnhancementAdapter.buildsOfVersion(releases, null), isEmpty);
      expect(MelonxEnhancementAdapter.describeBuilds([_strikersOld, 'AAAAAAAAAAAAAAAA'], releases),
          '$_strikersOld (1.3.0), AAAAAAAAAAAAAAAA');
    });
  });
}
