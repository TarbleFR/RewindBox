import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/adapters/melonx_enhancement_adapter.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';
import 'package:neostation/services/enhancements/enhancement_origin.dart';
import 'package:neostation/services/enhancements/enhancement_service.dart';
import 'package:neostation/services/enhancements/enhancement_store.dart';
import 'package:path/path.dart' as path;

import 'enhancement_test_support.dart';

/// A title of a source RewindBox does not host: the catalogue holds names and
/// pointers, the codes come from the source's own file. Made-up codes.
const _title = '0100000000010000';
const _origin = 'https://raw.githubusercontent.com/example/switch-cheats/0123456789abcdef0123456789abcdef01234567/';

Uint8List _file() => Uint8List.fromList(
  utf8.encode(
    jsonEncode({
      '3CA12DFAAF9C82DA': {
        '[Moon Jump]': '[Moon Jump]\n04000000 00000000 00000001\n',
        '{Master}': '{Master}\n80000002\n',
      },
      'F5DCCDDB37E97724': {'[Moon Jump]': '[Moon Jump]\n04000000 00000010 00000001\n20000000\n'},
      'attribution': {'Moon Jump.txt': 'By someone'},
    }),
  ),
);

Map<String, dynamic> _record(Uint8List file) => {
  'title': 'Super Mario Odyssey',
  'credits': ['By someone'],
  'origin': [
    {
      'source': 'switch-cheats-db',
      'path': 'cheats/$_title.json',
      'size': file.length,
      'sha256': sha256.convert(file).toString(),
    },
  ],
  'master': {
    '3CA12DFAAF9C82DA': {'o': 0, 'k': '{Master}'},
  },
  'entries': [
    {
      'id': 'moon-jump',
      'cat': 'cheat',
      'name': 'Moon Jump',
      'source': 'switch-cheats-db',
      'builds': {
        '3CA12DFAAF9C82DA': {'o': 0, 'k': '[Moon Jump]'},
        'F5DCCDDB37E97724': {'o': 0, 'k': '[Moon Jump]'},
      },
    },
  ],
};

void main() {
  late Directory temp;
  late Directory root;

  setUp(() {
    temp = Directory.systemTemp.createTempSync('enh-origin-');
    root = Directory(path.join(temp.path, 'MeloNX'))..createSync();
  });
  tearDown(() => temp.deleteSync(recursive: true));

  final game = testGame(name: 'Super Mario Odyssey', romPath: '/Documents/MeloNX/smo.nsp');

  EnhancementService serviceFor(Uint8List served, {Uint8List? recorded, List<Uri>? requests}) => EnhancementService(
    catalog: fixtureCatalog(
      Directory(path.join(temp.path, 'cache')),
      {
        'melonx': {_title: _record(recorded ?? served)},
      },
      sources: [
        {
          'id': 'switch-cheats-db',
          'name': 'Example',
          'url': 'https://example.org',
          'license': 'None',
          'origin': _origin,
        },
      ],
      origins: {'${_origin}cheats/$_title.json': served},
      requests: requests,
    ),
    store: EnhancementStore(root: () async => Directory(path.join(temp.path, 'store'))),
    adapters: [
      MelonxEnhancementAdapter(root: () async => root, metadata: (_) async => {'titleId': _title, 'version': '1.3.0'}),
    ],
    texturesSupported: (_) => false,
  );

  test('the codes are read from the original file and installed as before', () async {
    final requests = <Uri>[];
    final service = serviceFor(_file(), requests: requests);
    expect((await service.open(game, 'switch')).items, isEmpty, reason: 'nothing is fetched without consent');
    var view = await service.open(game, 'switch', download: true);
    expect(requests.map((uri) => uri.toString()), contains('${_origin}cheats/$_title.json'));
    final jump = view.items.single;
    expect(jump.name, 'Moon Jump');
    view = await service.setActive(game, 'switch', view, jump, true);
    final files = Directory(
      path.join(root.path, 'mods', 'contents', _title.toLowerCase(), 'RewindBox', 'cheats'),
    ).listSync().whereType<File>().map((f) => path.basename(f.path)).toSet();
    expect(files, {'3CA12DFAAF9C82DA.txt', 'F5DCCDDB37E97724.txt'});
    final text = File(
      path.join(root.path, 'mods', 'contents', _title.toLowerCase(), 'RewindBox', 'cheats', 'F5DCCDDB37E97724.txt'),
    ).readAsStringSync();
    expect(text, contains('04000000 00000010 00000001\n20000000'));
    expect(view.items.single.status, EnhancementStatus.active);

    // The verified file is cached: reopening fetches nothing more.
    final count = requests.length;
    await serviceFor(_file(), requests: requests).open(game, 'switch');
    expect(requests.length, count);
  });

  test('a file that changed at the source is refused, nothing is installed', () async {
    final changed = Uint8List.fromList([..._file(), 32]);
    final service = serviceFor(changed, recorded: _file());
    await expectLater(
      service.open(game, 'switch', download: true),
      throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'origin_integrity')),
    );
    expect(Directory(path.join(root.path, 'mods')).existsSync(), isFalse);
  });

  test('pointers follow the builder rules for Atmosphere words', () {
    expect(EnhancementOrigin.switchLines(['04000000 0000000a 00000001', '', '20000000']), [
      '04000000 0000000A 00000001',
      '20000000',
    ]);
    expect(EnhancementOrigin.switchLines(['not a code']), isNull);
    final resolved = EnhancementOrigin.resolve(
      EnhancementEngine.melonx,
      {
        ..._record(_file()),
        'entries': [
          ...(_record(_file())['entries'] as List),
          {
            'id': 'gone',
            'cat': 'cheat',
            'name': 'Gone',
            'source': 'switch-cheats-db',
            'builds': {
              '3CA12DFAAF9C82DA': {'o': 0, 'k': '[Missing]'},
            },
          },
        ],
      },
      [_file()],
    );
    expect((resolved['entries'] as List).map((e) => (e as Map)['name']), [
      'Moon Jump',
    ], reason: 'an entry whose code is not in the file is left out');
    expect(resolved['master'], {
      '3CA12DFAAF9C82DA': ['80000002'],
    });
    expect(resolved.containsKey('origin'), isTrue);
  });
}
