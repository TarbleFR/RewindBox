import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

import 'package:neostation/models/game_model.dart';
import 'package:neostation/services/enhancements/enhancement_catalog.dart';

/// A catalogue backed by the committed files: the bundled index from
/// assets/data and shards served from native/enhancements/catalogue, exactly
/// as raw.githubusercontent.com would serve them.
EnhancementCatalog repositoryCatalog(
  Directory cache, {
  List<Uri>? requests,
  Uint8List Function(Uri uri, Uint8List bytes)? tamper,
}) => EnhancementCatalog(
  cacheRoot: () async => cache,
  bundledIndex: () => File('assets/data/enhancements_index.json.gz').readAsBytes(),
  fetcher: (uri, {required limit, onProgress}) async {
    requests?.add(uri);
    final relative = uri.path.split('/native/enhancements/catalogue/').last;
    var bytes = await File('native/enhancements/catalogue/$relative').readAsBytes();
    if (tamper != null) bytes = tamper(uri, bytes);
    if (bytes.length > limit) throw StateError('limit');
    onProgress?.call(bytes.length, bytes.length);
    return bytes;
  },
);

/// A catalogue holding only [records] (`engine -> key -> record`), built
/// the way tools/enhancements writes one. For engines whose committed
/// catalogue has no entry to test with; the codes in it are made up.
///
/// [origins] serves the original files of sources the catalogue points
/// into (absolute URL → bytes); [sources] become the index's sources.
EnhancementCatalog fixtureCatalog(
  Directory cache,
  Map<String, Map<String, Map<String, dynamic>>> records, {
  List<Map<String, dynamic>> sources = const [],
  Map<String, Uint8List> origins = const {},
  List<Uri>? requests,
}) {
  const base = 'https://raw.githubusercontent.com/TarbleFR/RewindBox/Claude/native/enhancements/catalogue/';
  final files = <String, Uint8List>{};
  final shards = <String, dynamic>{};
  final engines = <String, dynamic>{};
  for (final engine in records.entries) {
    final shard = '${engine.key}-00';
    final packed = Uint8List.fromList(
      gzip.encode(utf8.encode(jsonEncode({'schema': 1, 'engine': engine.key, 'shard': shard, 'keys': engine.value}))),
    );
    files['shards/$shard.json.gz'] = packed;
    shards[shard] = {
      'path': 'shards/$shard.json.gz',
      'size': packed.length,
      'expanded': packed.length * 8,
      'sha256': sha256.convert(packed).toString(),
    };
    engines[engine.key] = {
      'keys': {
        for (final record in engine.value.entries)
          record.key: [
            record.value['title'] ?? '',
            {for (final entry in (record.value['entries'] as List)) (entry as Map)['cat']: 1},
            shard,
          ],
      },
    };
  }
  final index = Uint8List.fromList(
    gzip.encode(
      utf8.encode(
        jsonEncode({
          'schema': 1,
          'catalogue': 'rewindbox-enhancements',
          'revision': 'fixture',
          'base_url': base,
          'sources': sources,
          'engines': engines,
          'shards': shards,
        }),
      ),
    ),
  );
  return EnhancementCatalog(
    cacheRoot: () async => cache,
    bundledIndex: () async => index,
    fetcher: (uri, {required limit, onProgress}) async {
      requests?.add(uri);
      final url = uri.toString();
      final bytes = url.startsWith(base) ? files[url.substring(base.length)]! : origins[url];
      if (bytes == null) throw StateError('not served: $url');
      onProgress?.call(bytes.length, bytes.length);
      return bytes;
    },
  );
}

/// A library row as the game settings dialog passes it.
GameModel testGame({String name = 'Game', String? romPath, String? titleId}) => GameModel(
  romname: romPath?.split('/').last ?? name,
  realname: name,
  name: name,
  year: '',
  developer: '',
  publisher: '',
  genre: '',
  players: '',
  rating: 0,
  romPath: romPath,
  titleId: titleId,
);
