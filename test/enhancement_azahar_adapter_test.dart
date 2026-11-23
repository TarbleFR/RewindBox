import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/adapters/azahar_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:path/path.dart' as path;

import 'enhancement_test_support.dart';

/// Pokémon X: its Sharkive codes are in the committed catalogue.
const _pokemonX = '0004000000055D00';
const _record = '0004000000ABCD00';

/// An NCCH header (0x200 bytes) naming [programId].
Uint8List _ncch(String programId) {
  final bytes = Uint8List(0x200);
  bytes.setAll(0x100, 'NCCH'.codeUnits);
  final view = ByteData.sublistView(bytes);
  view.setUint32(0x118, int.parse(programId.substring(8), radix: 16), Endian.little);
  view.setUint32(0x11C, int.parse(programId.substring(0, 8), radix: 16), Endian.little);
  return bytes;
}

/// An NCSD (`.3ds`, `.cci`) whose partition 0 is at 0x200.
Uint8List _ncsd(String programId) {
  final header = Uint8List(0x200);
  header.setAll(0x100, 'NCSD'.codeUnits);
  ByteData.sublistView(header).setUint32(0x120, 1, Endian.little);
  return Uint8List.fromList([...header, ..._ncch(programId)]);
}

/// A CIA whose content 0 is the game's NCCH (certificate chain, ticket and TMD of 0x40 bytes each).
Uint8List _cia(String programId) {
  final header = Uint8List(0x2040);
  final view = ByteData.sublistView(header);
  view.setUint32(0, 0x2020, Endian.little);
  view.setUint32(0x08, 0x40, Endian.little);
  view.setUint32(0x0C, 0x40, Endian.little);
  view.setUint32(0x10, 0x40, Endian.little);
  return Uint8List.fromList([...header, ...Uint8List(0xC0), ..._ncch(programId)]);
}

void main() {
  late Directory temp;
  late Directory user;
  late EnhancementService service;

  EnhancementService serviceWith(Map<String, Map<String, Map<String, dynamic>>>? records) => EnhancementService(
    catalog: records == null
        ? repositoryCatalog(Directory(path.join(temp.path, 'cache')))
        : fixtureCatalog(Directory(path.join(temp.path, 'cache')), records),
    store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
    adapters: [AzaharEnhancementAdapter(userDirectory: () async => user)],
    texturesSupported: (_) => false,
    embeddedEngines: () => true,
  );

  String game(String name, Uint8List bytes) {
    final file = File(path.join(temp.path, 'roms', name))..createSync(recursive: true);
    file.writeAsBytesSync(bytes);
    return file.path;
  }

  File cheats(String titleId) => File(path.join(user.path, 'cheats', '$titleId.txt'));

  setUp(() {
    temp = Directory.systemTemp.createTempSync('enh-azahar-');
    user = Directory(path.join(temp.path, 'Saves', 'Azahar', 'Azahar'))..createSync(recursive: true);
    service = serviceWith(null);
  });
  tearDown(() => temp.deleteSync(recursive: true));

  group('Title ID of the game file', () {
    test('NCSD partition 0, NCCH and CIA content 0', () async {
      expect((await AzaharEnhancementAdapter.readTitleId(game('x.3ds', _ncsd(_pokemonX)))).titleId, _pokemonX);
      expect((await AzaharEnhancementAdapter.readTitleId(game('x.cxi', _ncch(_pokemonX)))).titleId, _pokemonX);
      expect((await AzaharEnhancementAdapter.readTitleId(game('x.cia', _cia(_pokemonX)))).titleId, _pokemonX);
    });

    test('an update or add-on maps to its application; system titles and compressed images have none', () async {
      expect(AzaharEnhancementAdapter.applicationTitleId('0004000E00055D00'), _pokemonX);
      expect(AzaharEnhancementAdapter.applicationTitleId('0004008c00055d00'), _pokemonX);
      expect(AzaharEnhancementAdapter.applicationTitleId('000400020017D501'), '000400020017D501');
      expect(AzaharEnhancementAdapter.applicationTitleId('0004001000020800'), isNull);
      final compressed = await AzaharEnhancementAdapter.readTitleId(game('x.zcci', _ncsd(_pokemonX)));
      expect(compressed.titleId, isNull);
      expect(compressed.problem, EnhancementProblem.imageFormat);
      final homebrew = await AzaharEnhancementAdapter.readTitleId(game('x.3dsx', Uint8List(0x400)));
      expect(homebrew.problem, EnhancementProblem.identityUnavailable);
      final garbage = await AzaharEnhancementAdapter.readTitleId(game('x.3ds', Uint8List(0x40)));
      expect(garbage.titleId, isNull);
    });
  });

  test('the committed catalogue offers a 3DS game its Sharkive codes, checked against Azahar\'s grammar', () async {
    final rom = game('Pokemon X.3ds', _ncsd(_pokemonX));
    final view = await service.open(testGame(name: 'Pokemon X', romPath: rom), '3ds', download: true);
    expect(view.identity.key, _pokemonX);
    expect(view.items, isNotEmpty);
    expect(view.items.every((item) => item.engine == EnhancementEngine.azahar), isTrue);
    expect(view.credits.single, contains('Sharkive'));
    final money = view.items.firstWhere((item) => item.name == 'Max Money');
    expect(money.status, EnhancementStatus.available);
    expect(money.compatibility, 'Title ID $_pokemonX');
  });

  test('turning codes on writes the core\'s cheat file with only them, enabled; off removes it', () async {
    final rom = game('Pokemon X.3ds', _ncsd(_pokemonX));
    final row = testGame(name: 'Pokemon X', romPath: rom);
    var view = await service.open(row, '3ds', download: true);
    final money = view.items.firstWhere((item) => item.name == 'Max Money');
    final miles = view.items.firstWhere((item) => item.name == 'Max Pokemilles');

    view = await service.setActive(row, '3ds', view, money, true);
    expect(cheats(_pokemonX).readAsStringSync(), '[Max Money]\n*citra_enabled\n08C6A69C 0098967F\n\n');
    view = await service.setActive(row, '3ds', view, miles, true);
    final text = cheats(_pokemonX).readAsStringSync();
    expect(text, contains('[Max Money]\n*citra_enabled\n'));
    expect(text, contains('[Max Pokemilles]\n*citra_enabled\n08C82B90 0098967F\n'));
    expect(RegExp(r'^\[').allMatches(text).length + RegExp(r'\n\[').allMatches(text).length, 2,
        reason: 'only the chosen codes are in the file');
    expect(view.activeCount, 2);

    view = await service.setActive(row, '3ds', view, money, false);
    view = await service.setActive(row, '3ds', view, miles, false);
    expect(cheats(_pokemonX).existsSync(), isFalse);
    expect(view.activeCount, 0);
  });

  test('a cheat file of the player\'s is never written over, and restore removes only RewindBox\'s', () async {
    final rom = game('Pokemon X.3ds', _ncsd(_pokemonX));
    final row = testGame(name: 'Pokemon X', romPath: rom);
    cheats(_pokemonX)
      ..createSync(recursive: true)
      ..writeAsStringSync('[Mine]\n00000000 00000001\n');
    var view = await service.open(row, '3ds', download: true);
    final money = view.items.firstWhere((item) => item.name == 'Max Money');
    await expectLater(
      service.setActive(row, '3ds', view, money, true),
      throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'user_file_present')),
    );
    expect(cheats(_pokemonX).readAsStringSync(), '[Mine]\n00000000 00000001\n');

    cheats(_pokemonX).deleteSync();
    view = await service.setActive(row, '3ds', view, money, true);
    expect(cheats(_pokemonX).existsSync(), isTrue);
    await service.restore('azahar:$_pokemonX');
    expect(cheats(_pokemonX).existsSync(), isFalse);
  });

  test('a code made for an update is incompatible until Azahar holds an update of the game', () async {
    final records = {
      'azahar': {
        _record: {
          'title': '',
          'credits': ['Fixture'],
          'entries': [
            {'id': 'base', 'cat': 'cheat', 'name': 'Coins v1.0', 'source': 'fixture', 'lines': ['00000000 00000001'], 'versions': ['1.0']},
            {'id': 'patched', 'cat': 'cheat', 'name': 'Coins v1.5', 'source': 'fixture', 'lines': ['00000000 00000002'], 'versions': ['1.5']},
            {'id': 'keyed', 'cat': 'cheat', 'name': 'Moon jump', 'source': 'fixture', 'update': true, 'lines': ['00000000 00000003']},
            {'id': 'combo', 'cat': 'cheat', 'name': 'Teleport', 'source': 'fixture', 'combo': [['L', 'R']],
              'lines': ['DD000000 00000300', '00000000 00000004', 'D2000000 00000000']},
            {'id': 'broken', 'cat': 'cheat', 'name': 'Short patch', 'source': 'fixture', 'lines': ['E0000000 00000010', '11111111 22222222']},
          ],
        },
      },
    };
    final service = serviceWith(records);
    final rom = game('Fixture.3ds', _ncsd(_record));
    final row = testGame(name: 'Fixture', romPath: rom);
    var view = await service.open(row, '3ds', download: true);
    EnhancementItem named(String name) => view.items.firstWhere((item) => item.name == name);
    expect(view.items.map((item) => item.name), isNot(contains('Short patch')), reason: 'Azahar would read past the code');
    expect(named('Coins v1.0').status, EnhancementStatus.available);
    expect(named('Coins v1.5').status, EnhancementStatus.incompatible);
    expect(named('Coins v1.5').problem, EnhancementProblem.versionMismatch);
    expect(named('Coins v1.5').compatibility, 'Title ID $_record · v1.5');
    expect(named('Moon jump').status, EnhancementStatus.incompatible);
    expect(named('Teleport').payload['combo'], [
      ['L', 'R'],
    ]);
    await expectLater(
      service.setActive(row, '3ds', view, named('Coins v1.5'), true),
      throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'incompatible')),
    );

    Directory(path.join(user.path, 'sdmc', 'Nintendo 3DS', '0' * 32, '0' * 32, 'title', '0004000e', _record.substring(8).toLowerCase()))
        .createSync(recursive: true);
    view = await service.open(row, '3ds', download: true);
    expect(named('Coins v1.5').status, EnhancementStatus.available, reason: 'an update is installed');
    expect(named('Moon jump').status, EnhancementStatus.available);
  });

  test('a cheat file RewindBox wrote and the player deleted no longer counts as active', () async {
    final rom = game('Pokemon X.3ds', _ncsd(_pokemonX));
    final row = testGame(name: 'Pokemon X', romPath: rom);
    var view = await service.open(row, '3ds', download: true);
    view = await service.setActive(row, '3ds', view, view.items.firstWhere((item) => item.name == 'Max Money'), true);
    expect(view.activeCount, 1);
    cheats(_pokemonX).deleteSync();
    view = await service.open(row, '3ds', download: true);
    expect(view.activeCount, 0);
  });

  test("the catalogue's flags reach the item for the page's warnings", () async {
    final service = serviceWith({
      'azahar': {
        _record: {
          'title': 'Fixture',
          'credits': ['Fixture'],
          'entries': [
            {
              'id': 'jump',
              'cat': 'cheat',
              'name': 'Jump Over Anything (D-pad. exiting map may crash)',
              'source': 'sharkive-3ds',
              'flags': ['crashRisk'],
              'lines': ['DD000000 00000080', '20000000 00000001', 'D2000000 00000000'],
            },
            {
              'id': 'coins',
              'cat': 'cheat',
              'name': 'Coins',
              'source': 'sharkive-3ds',
              'lines': ['20000000 00000001'],
            },
          ],
        },
      },
    });
    final view = await service.open(testGame(name: 'Fixture', romPath: game('Fixture.3ds', _ncsd(_record))), '3ds', download: true);
    final jump = view.items.firstWhere((item) => item.id == 'jump');
    expect(jump.payload['flags'], ['crashRisk']);
    expect(jump.status, EnhancementStatus.available, reason: 'a warning, not a block');
    expect(view.items.firstWhere((item) => item.id == 'coins').payload.containsKey('flags'), isFalse);
  });
}
