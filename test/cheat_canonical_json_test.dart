import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:neo_cheat_catalog/src/canonical_json.dart';

/// Every game chunk of the published unified catalogue is verified by the
/// SHA-256 of Python's canonical JSON. A chunk the app rebuilds from origin
/// files must therefore re-encode to the very same bytes.
/// CANONICAL_ALL=1 checks every pack instead of one in 25.
void main() {
  test('Python float repr', () {
    expect(pythonFloat(1.0), '1.0');
    expect(pythonFloat(1.2), '1.2');
    expect(pythonFloat(0.0001), '0.0001');
    expect(pythonFloat(0.00001), '1e-05');
    expect(pythonFloat(1e16), '1e+16');
    expect(pythonFloat(123456789012345.6), '123456789012345.6');
    expect(pythonFloat(3.68e61), '3.68e+61');
    expect(pythonFloat(-2.5), '-2.5');
    expect(pythonFloat(1.5e-7), '1.5e-07');
  });

  test('strings, keys and nesting match json.dumps', () {
    expect(utf8.decode(canonicalJson({'b': 1, 'a': ['é', '"\\\n\u0001'], 'c': null, 'd': true})),
        '{"a":["é","\\"\\\\\\n\\u0001"],"b":1,"c":null,"d":true}\n');
  });

  test('published chunks re-encode byte for byte', () {
    final directory = Directory('native/cheats/catalogue');
    final manifest = jsonDecode(utf8.decode(gzip.decode(File('${directory.path}/manifest.json.gz').readAsBytesSync())))
        as Map<String, dynamic>;
    final all = Platform.environment['CANONICAL_ALL'] == '1';
    final packs = (manifest['packs'] as List).cast<Map<String, dynamic>>();
    var chunks = 0;
    for (var i = 0; i < packs.length; i += all ? 1 : 25) {
      final body = jsonDecode(utf8.decode(gzip.decode(File('${directory.path}/${packs[i]['path']}').readAsBytesSync())))
          as Map<String, dynamic>;
      for (final file in (body['files'] as List).cast<Map<String, dynamic>>()) {
        final bytes = base64Decode(file['data'] as String);
        final encoded = canonicalJson(jsonDecode(utf8.decode(bytes)));
        expect(encoded, bytes, reason: '${packs[i]['path']} ${file['game_id']}');
        chunks++;
      }
    }
    expect(chunks, greaterThan(all ? 50000 : 1500));
  }, timeout: const Timeout(Duration(minutes: 30)));
}
