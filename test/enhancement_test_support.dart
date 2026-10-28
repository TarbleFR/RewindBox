import 'dart:io';
import 'dart:typed_data';

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
  bundledIndex: () => File(
    'assets/data/enhancements_index.json.gz',
  ).readAsBytes(),
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
