import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neo_cheat_catalog/neo_cheat_catalog.dart';
import 'package:neo_cheat_catalog/src/canonical_json.dart';
import 'package:neo_cheat_catalog/src/origin_recipe.dart';

/// Packs of the origin publication rebuild to the chunks the hosted
/// publication served. Made-up programs in the shapes tools/cheats/origin
/// writes; the published data is checked by cheat_origin_publication_test.
/// Recipe items for every line of [bytes]: ranges joined by "\n".
List<Object> lineRanges(Uint8List bytes) {
  final items = <Object>[];
  var start = 0;
  for (var i = 0; i <= bytes.length; i++) {
    if (i == bytes.length || bytes[i] == 0x0A) {
      if (i > start) {
        if (items.isNotEmpty) items.add('\n');
        items.add([start, i]);
      }
      start = i + 1;
    }
  }
  return items;
}

void main() {
  late Directory temp;
  setUp(() => temp = Directory.systemTemp.createTempSync('cheat-origin-'));
  tearDown(() => temp.deleteSync(recursive: true));

  final gecko = Uint8List.fromList(utf8.encode('GALE01\nInfinite Health\n0400abcd 00000063\n*Keeps you alive\n'));
  final ini = Uint8List.fromList(
    utf8.encode('cheat "Infinite Lives"\ndefault 0\n0 "Disabled"\n1 "Enabled", 0, 0x562, 0x20\n'),
  );
  final gg = Uint8List(16)
    ..buffer.asByteData().setUint32(0, 1, Endian.little)
    ..buffer.asByteData().setUint32(4, 0xA23B, Endian.little)
    ..buffer.asByteData().setUint32(8, 0x05, Endian.little)
    ..buffer.asByteData().setUint32(12, 0x10, Endian.little);
  final zip = Uint8List.fromList(ZipEncoder().encode(Archive()..addFile(ArchiveFile('Lives.gg', gg.length, gg))));

  Map<String, dynamic> file(String source, String path, Uint8List bytes) => {
    'source': source,
    'path': path,
    'size': bytes.length,
    'sha256': sha256.convert(bytes).toString(),
  };
  final sources = {
    'geckoarchive': {'raw': 'https://raw.githubusercontent.com/o/gecko/0123/{path}'},
    'fbneo': {'raw': 'https://raw.githubusercontent.com/o/fbneo/0123/{path}'},
    'mister': {'raw': 'https://raw.githubusercontent.com/o/mister/0123/{path}'},
  };
  final served = {
    'https://raw.githubusercontent.com/o/gecko/0123/codes/GALE01.txt': gecko,
    'https://raw.githubusercontent.com/o/fbneo/0123/cheats/sf2.ini': ini,
    'https://raw.githubusercontent.com/o/mister/0123/Cheats/NES/Tecmo%20Bowl%20%5B00%5D.zip': zip,
  };

  // The published programs, as review_program left them.
  final published = {
    'schema_version': 1,
    'game': {'id': 'g1', 'system': 'gc'},
    'cheats': [
      {
        'id': 'a',
        'name': 'Infinite Health',
        'dialect': 'gecko',
        'code': '0400abcd 00000063',
        'lines': ['0400ABCD 00000063'],
        'status': 'available',
        'enabled': false,
      },
      {
        'id': 'b',
        'name': 'Infinite Lives',
        'dialect': 'fbneo-ini',
        ...OriginRecipe.fbneo('cheat "Infinite Lives"\ndefault 0\n0 "Disabled"\n1 "Enabled", 0, 0x562, 0x20'),
        'status': 'available',
        'enabled': false,
      },
      {
        'id': 'c',
        'name': 'Lives',
        'dialect': 'nes-raw',
        'code': 'A23B?05:10',
        'lines': ['A23B?05:10'],
        'source_code': '010000003BA200000500000010000000',
        'status': 'available',
        'enabled': false,
      },
    ],
  };
  final start = utf8.decode(gecko).indexOf('0400abcd 00000063');
  final skeleton = {
    ...published,
    'cheats': [
      {
        ...{
          for (final e in (published['cheats'] as List)[0].entries)
            if (!const {'code', 'lines', 'source_code'}.contains(e.key)) e.key: e.value,
        },
        'origin': {
          'f': 0,
          'r': [
            [start, start + 17],
          ],
        },
      },
      {
        ...{
          for (final e in (published['cheats'] as List)[1].entries)
            if (!const {'code', 'lines', 'choices', 'native_document'}.contains(e.key)) e.key: e.value,
        },
        'origin': {'f': 1, 'k': 'fbneo', 'r': lineRanges(ini)},
      },
      {
        ...{
          for (final e in (published['cheats'] as List)[2].entries)
            if (!const {'code', 'lines', 'source_code'}.contains(e.key)) e.key: e.value,
        },
        'origin': {'f': 2, 'k': 'mister', 's': 'nes', 'z': 'Lives.gg'},
      },
    ],
  };
  Uint8List pack(Map<String, dynamic> origin) => Uint8List.fromList(
    utf8.encode(
      jsonEncode({
        'schema_version': 1,
        'origin': origin,
        'files': [
          {'game_id': 'g1', 'skeleton': base64Encode(canonicalJson(skeleton))},
          {'game_id': 'g2', 'data': 'aG9zdGVk'},
        ],
      }),
    ),
  );
  final origin = {
    'version': 1,
    'sources': sources,
    'files': [
      file('geckoarchive', 'codes/GALE01.txt', gecko),
      file('fbneo', 'cheats/sf2.ini', ini),
      file('mister', 'Cheats/NES/Tecmo Bowl [00].zip', zip),
    ],
  };

  test('a v2 pack rebuilds the published chunks, hosted ones untouched', () async {
    final requests = <Uri>[];
    final resolver = OriginResolver(
      cache: temp,
      fetch: (uri, limit) async {
        requests.add(uri);
        return served[uri.toString()]!;
      },
    );
    final result = jsonDecode(utf8.decode(await resolver.resolve(pack(origin)))) as Map<String, dynamic>;
    final files = (result['files'] as List).cast<Map<String, dynamic>>();
    expect(utf8.decode(base64Decode(files[0]['data'] as String)), utf8.decode(canonicalJson(published)));
    expect(files[1], {'game_id': 'g2', 'data': 'aG9zdGVk'});
    expect(requests, hasLength(3));

    // Cached by SHA-256: a second pack fetches nothing.
    await OriginResolver(cache: temp, fetch: (uri, limit) async => throw StateError('offline')).resolve(pack(origin));
  });

  test('Flutter registers the resolver the native catalogue calls', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    NeoCheatCatalog.registerWith();
    const codec = StandardMethodCodec();
    Future<Object?> call(Object? arguments) async {
      final reply = Completer<ByteData?>();
      await TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.handlePlatformMessage(
        'neostation/cheat_catalog',
        codec.encodeMethodCall(MethodCall('resolveOriginPack', arguments)),
        reply.complete,
      );
      return codec.decodeEnvelope((await reply.future)!);
    }

    // A program with no recipe needs no origin file: nothing is downloaded.
    final chunk = {
      'schema_version': 1,
      'game': {'id': 'g'},
      'cheats': [
        {'id': 'p', 'name': 'Hosted', 'code': '01FF10C0'},
      ],
    };
    final body = Uint8List.fromList(
      utf8.encode(
        jsonEncode({
          'schema_version': 1,
          'origin': {'version': 1, 'sources': {}, 'files': []},
          'files': [
            {'game_id': 'g', 'skeleton': base64Encode(canonicalJson(chunk))},
          ],
        }),
      ),
    );
    final answer = await call({'pack': body, 'cache': '${temp.path}/origin'});
    final files = (jsonDecode(utf8.decode(answer! as Uint8List))['files'] as List).cast<Map<String, dynamic>>();
    expect(files.single['data'], base64Encode(canonicalJson(chunk)));
    await expectLater(
      call({'pack': body}),
      throwsA(isA<PlatformException>().having((e) => e.code, 'code', 'origin_arguments')),
    );
  });

  test('an origin file that changed at its source is refused', () async {
    final resolver = OriginResolver(
      cache: temp,
      fetch: (uri, limit) async => Uint8List.fromList([...served[uri.toString()]!, 0x20]),
    );
    await expectLater(resolver.resolve(pack(origin)), throwsA(isA<OriginIntegrityError>()));
  });

  test('recipes only carry separators and known transforms', () {
    expect(() => OriginRecipe.rawText(['0400'], gecko, 'utf-8'), throwsFormatException);
    expect(
      () => OriginRecipe.rawText(
        [
          [0, 4, 'eval'],
        ],
        gecko,
        'utf-8',
      ),
      throwsFormatException,
    );
    expect(
      () => OriginRecipe.rawText(
        [
          [0, 999],
        ],
        gecko,
        'utf-8',
      ),
      throwsFormatException,
    );
    expect(
      OriginResolver.originUri({'path': 'a b/c#.txt'}, {'raw': 'https://h/x/{path}'}).toString(),
      'https://h/x/a%20b/c%23.txt',
    );
  });

  test('a 429 from raw files switches the source to its pinned archive', () async {
    final tar = Archive()
      ..addFile(ArchiveFile('repo-0123/codes/GALE01.txt', gecko.length, gecko))
      ..addFile(ArchiveFile('repo-0123/README.md', 6, utf8.encode('readme')));
    final archive = File('${temp.path}/archive.tar.gz')
      ..writeAsBytesSync(GZipEncoder().encode(TarEncoder().encode(tar)));
    final requested = <Uri>[];
    final resolver =
        OriginResolver(
            cache: Directory('${temp.path}/cache'),
            fetch: (uri, limit) async {
              if (uri.host == 'raw.githubusercontent.com' && uri.path.contains('/gecko/')) {
                throw HttpException('HTTP 429', uri: uri);
              }
              return served[uri.toString()]!;
            },
          )
          ..fetchToFile = (uri) async {
            requested.add(uri);
            final copy = File('${temp.path}/download.tar.gz');
            archive.copySync(copy.path);
            return copy;
          };
    final withArchive = {
      ...origin,
      'sources': {
        ...sources,
        'geckoarchive': {...sources['geckoarchive']!, 'archive': 'https://codeload.github.com/o/gecko/tar.gz/0123'},
      },
    };
    final result = jsonDecode(utf8.decode(await resolver.resolve(pack(withArchive)))) as Map<String, dynamic>;
    expect(
      utf8.decode(base64Decode((result['files'] as List).first['data'] as String)),
      utf8.decode(canonicalJson(published)),
    );
    expect(requested.single.toString(), 'https://codeload.github.com/o/gecko/tar.gz/0123');
  });
}
