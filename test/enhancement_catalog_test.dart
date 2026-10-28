import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/services/enhancements/enhancement_catalog.dart';
import 'package:neostation/services/enhancements/enhancement_models.dart';

import 'enhancement_test_support.dart';

void main() {
  late Directory cache;

  setUp(() => cache = Directory.systemTemp.createTempSync('enh-catalog-'));
  tearDown(() => cache.deleteSync(recursive: true));

  test('the bundled index is the published index and lists every engine', () async {
    final bundled = File('assets/data/enhancements_index.json.gz').readAsBytesSync();
    final published = File('native/enhancements/catalogue/index.json.gz').readAsBytesSync();
    expect(bundled, published, reason: 'the IPA index and the remote index must be identical');

    final index = await repositoryCatalog(cache).index();
    expect(index.baseUrl, startsWith('https://raw.githubusercontent.com/TarbleFR/RewindBox/'));
    for (final engine in ['melonx', 'rpcs3', 'armsx2', 'dolphin']) {
      expect(index.totals[engine], isNotNull, reason: engine);
    }
    expect(index.sources.map((s) => s.id), containsAll(['switch-cheats-db', 'rpcs3-patches', 'pcsx2-patches', 'dolphin-gamesettings']));
    expect(index.contains(EnhancementEngine.melonx, '0100000000010000'), isTrue);
    expect(index.contains(EnhancementEngine.rpcs3, 'BLUS30443'), isTrue);
  });

  test('a record is downloaded once, verified and served from the cache', () async {
    final requests = <Uri>[];
    final catalog = repositoryCatalog(cache, requests: requests);
    expect(await catalog.isDownloaded(EnhancementEngine.melonx, '0100000000010000'), isFalse);
    expect(
      await catalog.record(EnhancementEngine.melonx, '0100000000010000', download: false),
      isNull,
      reason: 'no network without consent',
    );
    final progress = <int>[];
    final record = await catalog.record(
      EnhancementEngine.melonx,
      '0100000000010000',
      onProgress: (received, total) => progress.add(received),
    );
    expect(record?['entries'], isNotEmpty);
    expect(progress, isNotEmpty);
    expect(requests, hasLength(1));
    expect(await catalog.isDownloaded(EnhancementEngine.melonx, '0100000000010000'), isTrue);

    // A fresh instance (next app start) reads the verified cached shard.
    final reopened = repositoryCatalog(cache, requests: requests);
    expect(await reopened.record(EnhancementEngine.melonx, '0100000000010000', download: false), isNotNull);
    expect(requests, hasLength(1));
  });

  test('a shard whose bytes differ from the index is rejected and not cached', () async {
    final catalog = repositoryCatalog(
      cache,
      tamper: (uri, bytes) => Uint8List.fromList([...bytes]..[bytes.length ~/ 2] ^= 0xff),
    );
    await expectLater(
      catalog.record(EnhancementEngine.rpcs3, 'BLUS30443'),
      throwsA(isA<EnhancementException>().having((e) => e.code, 'code', 'shard_integrity')),
    );
    expect(await catalog.isDownloaded(EnhancementEngine.rpcs3, 'BLUS30443'), isFalse);
  });

  test('a damaged cached shard is discarded and downloaded again', () async {
    final requests = <Uri>[];
    final catalog = repositoryCatalog(cache, requests: requests);
    await catalog.record(EnhancementEngine.rpcs3, 'BLUS30443');
    final shard = cache
        .listSync(recursive: true)
        .whereType<File>()
        .firstWhere((file) => file.path.endsWith('.json.gz'));
    shard.writeAsBytesSync([1, 2, 3]);
    final reopened = repositoryCatalog(cache, requests: requests);
    expect(await reopened.record(EnhancementEngine.rpcs3, 'BLUS30443'), isNotNull);
    expect(requests, hasLength(2));
  });

  test('refresh keeps a newer valid index and refuses a malformed one', () async {
    final source = jsonDecode(
      utf8.decode(gzip.decode(File('native/enhancements/catalogue/index.json.gz').readAsBytesSync())),
    ) as Map<String, dynamic>;
    Uint8List encode(Map<String, dynamic> json) => Uint8List.fromList(gzip.encode(utf8.encode(jsonEncode(json))));

    final newer = Map<String, dynamic>.from(source)..['revision'] = '9999-01-01.newer';
    final catalog = EnhancementCatalog(
      cacheRoot: () async => cache,
      bundledIndex: () async => encode(source),
      fetcher: (uri, {required limit, onProgress}) async {
        expect(uri.toString(), endsWith('/native/enhancements/catalogue/index.json.gz'));
        return encode(newer);
      },
    );
    expect(await catalog.refresh(), isTrue);
    expect((await catalog.index()).revision, '9999-01-01.newer');
    expect(await catalog.refresh(), isFalse, reason: 'same revision');

    final broken = Map<String, dynamic>.from(source)
      ..['revision'] = '9999-12-31'
      ..['base_url'] = 'http://insecure.example/';
    final refusing = EnhancementCatalog(
      cacheRoot: () async => cache,
      bundledIndex: () async => encode(source),
      fetcher: (uri, {required limit, onProgress}) async => encode(broken),
    );
    await expectLater(refusing.refresh(), throwsA(isA<EnhancementException>()));
    expect((await refusing.index()).revision, '9999-01-01.newer', reason: 'the kept index is unchanged');
  });

  test('every shard listed by the index exists with its size and SHA-256', () async {
    final index = await repositoryCatalog(cache).index();
    final shards = index.json['shards'] as Map;
    expect(shards, isNotEmpty);
    for (final entry in shards.entries) {
      final meta = entry.value as Map;
      final bytes = File('native/enhancements/catalogue/${meta['path']}').readAsBytesSync();
      expect(bytes.length, meta['size'], reason: entry.key);
      expect(sha256.convert(bytes).toString(), meta['sha256'], reason: entry.key);
    }
  });
}
