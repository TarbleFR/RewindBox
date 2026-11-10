import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neo_cheat_catalog/src/origin_resolver.dart';

/// End to end on the real publication: every v2 pack, rebuilt by the app's
/// resolver from the sources' pinned files, gives chunks with the SHA-256 the
/// manifest lists (the hosted publication's bytes).
///
/// The origin files are not part of this repository (that is the point), so
/// the test needs a local copy: `ORIGIN_DIR=dir` holding `source/path` and,
/// for single-archive sources, `source.bin` (tools/cheats/origin/sources.py).
/// ORIGIN_PACKS=n limits the run to n packs.
void main() {
  final root = Platform.environment['ORIGIN_DIR'];
  test(
    'every v2 pack rebuilds to the published chunks',
    () async {
      final directory = Directory('native/cheats/catalogue/v2');
      final manifest =
          jsonDecode(utf8.decode(gzip.decode(File('${directory.path}/manifest.json.gz').readAsBytesSync())))
              as Map<String, dynamic>;
      final games = {for (final g in (manifest['games'] as List).cast<Map<String, dynamic>>()) g['id']: g};
      final sources = Map<String, dynamic>.from(manifest['origin']['sources'] as Map);
      final cache = Directory.systemTemp.createTempSync('origin-cache-');
      addTearDown(() => cache.deleteSync(recursive: true));
      // Serves each origin URL from the local copy.
      final byUrl = <String, String>{};
      final resolver = OriginResolver(
        cache: cache,
        fetch: (uri, limit) async => File(byUrl[uri.toString()]!).readAsBytesSync(),
      )..fetchToFile = (uri) async => throw const SocketException('archives are not part of the local copy');
      final packs = (manifest['packs'] as List).cast<Map<String, dynamic>>();
      final limit = int.tryParse(Platform.environment['ORIGIN_PACKS'] ?? '') ?? packs.length;
      var rebuilt = 0;
      for (final pack in packs.take(limit)) {
        final bytes = Uint8List.fromList(gzip.decode(File('${directory.path}/${pack['path']}').readAsBytesSync()));
        final body = jsonDecode(utf8.decode(bytes)) as Map<String, dynamic>;
        for (final file in (body['origin']?['files'] as List? ?? const []).cast<Map<String, dynamic>>()) {
          final source = Map<String, dynamic>.from(sources[file['source']] as Map);
          byUrl[OriginResolver.originUri(file, source).toString()] = source['bundle'] != null
              ? '$root/${file['source']}.bin'
              : '$root/${file['source']}/${file['path']}';
        }
        final resolved = jsonDecode(utf8.decode(await resolver.resolve(bytes))) as Map<String, dynamic>;
        for (final file in (resolved['files'] as List).cast<Map<String, dynamic>>()) {
          final chunk = base64Decode(file['data'] as String);
          final game = games[file['game_id']]!;
          expect(sha256.convert(chunk).toString(), game['sha256'], reason: '${pack['path']} ${file['game_id']}');
          expect(chunk.length, game['size']);
          rebuilt++;
        }
      }
      expect(rebuilt, greaterThan(0));
    },
    skip: root == null ? 'ORIGIN_DIR not set: the origin files are not in the repository' : false,
    timeout: const Timeout(Duration(hours: 2)),
  );
}
