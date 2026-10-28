import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/adapters/rpcs3_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:path/path.dart' as path;

import 'enhancement_test_support.dart';

/// Demon's Souls (US): Unlock FPS and exclusive aspect-ratio choices for 01.00.
const _serial = 'BLUS30443';

void main() {
  late Directory temp;
  late Directory data;
  late EnhancementService service;
  String? installedVersion = '01.00';

  File stateFile() => File(path.join(data.path, 'NeoStationUnifiedCheats', 'state.json'));
  File published() => File(path.join(data.path, 'patches', '${_serial}_patch.yml'));
  Map<String, dynamic> readState() => jsonDecode(stateFile().readAsStringSync()) as Map<String, dynamic>;
  List<Map<String, dynamic>> ours() => [
    for (final program in readState()['programs'] as List)
      if ((program as Map)['source'] == Rpcs3EnhancementAdapter.sourceTag) Map<String, dynamic>.from(program),
  ];

  setUp(() {
    installedVersion = '01.00';
    temp = Directory.systemTemp.createTempSync('enh-rpcs3-');
    data = Directory(path.join(temp.path, 'Data'))..createSync();
    service = EnhancementService(
      catalog: repositoryCatalog(Directory(path.join(temp.path, 'cache'))),
      store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
      adapters: [
        Rpcs3EnhancementAdapter(
          dataDirectory: () async => data,
          installedVersion: (serial) async => installedVersion,
        ),
      ],
      texturesSupported: (_) => false,
    );
  });
  tearDown(() => temp.deleteSync(recursive: true));

  final game = testGame(name: "Demon's Souls", romPath: '/rpcs3/BLUS30443', titleId: 'blus30443');

  test('records are staged for the bridge exactly as RPCS3UnifiedCheats reads them', () async {
    var view = await service.open(game, 'ps3', download: true);
    expect(view.identity.key, _serial);
    final fps = view.items.firstWhere((item) => item.name == 'Unlock FPS');
    expect(fps.category, EnhancementCategory.fps);
    view = await service.setActive(game, 'ps3', view, fps, true);
    expect(view.items.firstWhere((item) => item.id == fps.id).status, EnhancementStatus.active);

    final state = readState();
    expect(state['schema_version'], 1);
    expect(state['pending'], isTrue);
    final records = ours();
    expect(records, isNotEmpty);
    for (final record in records) {
      // The fields the bridge's -state loader requires, all non-empty strings.
      for (final key in ['id', 'name', 'serial', 'version', 'hash', 'title', 'description']) {
        expect(record[key], isA<String>().having((value) => value.isNotEmpty, 'non-empty', isTrue), reason: key);
      }
      expect(record['enabled'], isA<bool>());
      expect(record['pending'], isTrue);
      expect(record['hash'], matches(RegExp(r'^PPU-[0-9A-Fa-f]{40}$')));
      expect(record['version'], '01.00');
      final patch = record['patch'] as Map;
      expect(((patch['Games'] as Map)[record['title']] as Map)[_serial], ['01.00']);
      for (final line in patch['Patch'] as List) {
        expect(line, hasLength(3));
        expect(line[1], matches(RegExp(r'^0x[0-9A-Fa-f]{1,8}$')), reason: 'hexadecimal offsets only');
        expect(line[0], isNot('load'), reason: 'anchors are flattened at build time');
      }
    }
    expect(records.where((record) => record['enabled'] == true).map((r) => r['entry']).toSet(), {fps.id});
  });

  test('aspect-ratio choices are exclusive', () async {
    var view = await service.open(game, 'ps3', download: true);
    final choices = view.items.where((item) => item.name.startsWith('Aspect Ratio — ')).toList();
    expect(choices.length, greaterThan(2));
    expect(choices.map((item) => item.exclusiveGroup).toSet(), hasLength(1));
    view = await service.setActive(game, 'ps3', view, choices[0], true);
    view = await service.setActive(game, 'ps3', view, view.items.firstWhere((i) => i.id == choices[1].id), true);
    final active = view.items.where((item) => item.status == EnhancementStatus.active).map((item) => item.id);
    expect(active, [choices[1].id]);
  });

  test('another game version makes every entry incompatible', () async {
    installedVersion = '01.05';
    final view = await service.open(game, 'ps3', download: true);
    expect(view.items, isNotEmpty);
    expect(view.items.every((item) => item.status == EnhancementStatus.incompatible), isTrue);
    expect(view.items.first.problem, EnhancementProblem.versionMismatch);
    await expectLater(
      service.setActive(game, 'ps3', view, view.items.first, true),
      throwsA(isA<EnhancementException>()),
    );
    installedVersion = null;
    final unknown = await service.open(game, 'ps3', download: true);
    expect(unknown.items.first.problem, EnhancementProblem.versionUnknown);
  });

  test('native records survive, and our published entries are withdrawn for the bridge', () async {
    const nativeHash = 'PPU-0123456789abcdef0123456789abcdef01234567';
    final nativePatch = {
      'Games': {"Demon's Souls": {_serial: ['01.00']}},
      'Author': 'CodeFreak',
      'Notes': '',
      'Patch': [
        ['be32', '0x00010000', '0x60000000'],
      ],
    };
    stateFile()
      ..createSync(recursive: true)
      ..writeAsStringSync(jsonEncode({
        'schema_version': 1,
        'pending': false,
        'programs': [
          {
            'id': 'native-1',
            'name': 'Infinite Souls',
            'serial': _serial,
            'version': '01.00',
            'hash': nativeHash,
            'title': "Demon's Souls",
            'description': 'NeoStation/uuid/Infinite Souls',
            'patch': nativePatch,
            'enabled': true,
            'pending': false,
          },
        ],
      }));
    var view = await service.open(game, 'ps3', download: true);
    view = await service.setActive(game, 'ps3', view, view.items.firstWhere((i) => i.name == 'Unlock FPS'), true);

    // Simulate the bridge's boot: publish every staged record of the title.
    final document = <String, dynamic>{'Version': '1.2'};
    for (final record in readState()['programs'] as List) {
      ((document[record['hash']] ??= <String, dynamic>{}) as Map)[record['description']] = record['patch'];
    }
    published()
      ..createSync(recursive: true)
      ..writeAsStringSync(jsonEncode(document));

    await service.restore(view.identity.storeKey);
    final programs = readState()['programs'] as List;
    expect(programs, hasLength(1));
    expect(programs.single['id'], 'native-1');
    expect(programs.single['pending'], isTrue, reason: 'republished without our entries at the next boot');
    final left = jsonDecode(published().readAsStringSync()) as Map;
    expect(left.keys.toSet(), {'Version', nativeHash},
        reason: 'managedTitleFile accepts a file holding only staged native entries');
    expect((left[nativeHash] as Map).keys, ['NeoStation/uuid/Infinite Souls']);
  });

  test('a file published only for RewindBox entries is deleted on restore', () async {
    var view = await service.open(game, 'ps3', download: true);
    view = await service.setActive(game, 'ps3', view, view.items.firstWhere((i) => i.name == 'Unlock FPS'), true);
    final document = <String, dynamic>{'Version': '1.2'};
    for (final record in ours()) {
      ((document[record['hash']] ??= <String, dynamic>{}) as Map)[record['description']] = record['patch'];
    }
    published()
      ..createSync(recursive: true)
      ..writeAsStringSync(jsonEncode(document));
    await service.restore(view.identity.storeKey);
    expect(published().existsSync(), isFalse);
    expect(readState()['programs'], isEmpty);
  });

  test('a choice made in the in-game menu is read back from the staging file', () async {
    var view = await service.open(game, 'ps3', download: true);
    view = await service.install(game, 'ps3', view);
    expect(view.activeCount, 0);
    final state = readState();
    final record = (state['programs'] as List).firstWhere((r) => (r as Map)['source_name'] == 'Skip Intro Videos') as Map;
    record['enabled'] = true;
    stateFile().writeAsStringSync(jsonEncode(state));
    view = await service.open(game, 'ps3');
    expect(view.items.firstWhere((item) => item.name == 'Skip Intro Videos').status, EnhancementStatus.active);
  });
}
