import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;
import 'package:path_provider/path_provider.dart';

import '../logger_service.dart';
import 'enhancement_models.dart';

/// Download progress of a catalogue file: bytes received of [total].
typedef EnhancementProgress = void Function(int received, int total);

/// Fetches the bytes of [uri], reporting progress, up to [limit] bytes.
typedef EnhancementFetcher =
    Future<Uint8List> Function(
      Uri uri, {
      required int limit,
      EnhancementProgress? onProgress,
    });

/// The parsed index: catalogue keys per engine and the shard holding them.
class EnhancementIndex {
  EnhancementIndex._(this.json);

  final Map<String, dynamic> json;

  String get revision => json['revision']?.toString() ?? '';
  String get baseUrl => json['base_url']?.toString() ?? '';

  List<EnhancementSource> get sources => [
    for (final source in (json['sources'] as List? ?? const []))
      if (source is Map) EnhancementSource.fromJson(Map<String, dynamic>.from(source)),
  ];

  Map<String, dynamic> get totals =>
      Map<String, dynamic>.from(json['totals'] as Map? ?? const {});

  Map<String, dynamic> _keys(EnhancementEngine engine) {
    final engines = json['engines'];
    if (engines is! Map) return const {};
    final entry = engines[engine.name];
    if (entry is! Map || entry['keys'] is! Map) return const {};
    return Map<String, dynamic>.from(entry['keys'] as Map);
  }

  bool contains(EnhancementEngine engine, String key) =>
      _keys(engine).containsKey(key);

  /// `[title, {category: count}, shard]` of one key, or null.
  List<dynamic>? entry(EnhancementEngine engine, String key) {
    final value = _keys(engine)[key];
    return value is List && value.length == 3 ? value : null;
  }

  String titleOf(EnhancementEngine engine, String key) =>
      entry(engine, key)?[0]?.toString() ?? '';

  Map<String, dynamic>? shard(String name) {
    final shards = json['shards'];
    if (shards is! Map || shards[name] is! Map) return null;
    return Map<String, dynamic>.from(shards[name] as Map);
  }

  /// Validates the structure the runtime relies on; throws on any defect.
  static EnhancementIndex parse(Map<String, dynamic> json) {
    if (json['schema'] != 1 || json['catalogue'] != 'rewindbox-enhancements') {
      throw const EnhancementException('index_schema');
    }
    final shards = json['shards'];
    if (shards is! Map) throw const EnhancementException('index_shards');
    for (final entry in shards.entries) {
      final meta = entry.value;
      if (meta is! Map ||
          !RegExp(r'^[a-z0-9]+-[0-9]{2}$').hasMatch(entry.key.toString()) ||
          meta['path'] != 'shards/${entry.key}.json.gz' ||
          meta['size'] is! int ||
          meta['expanded'] is! int ||
          !RegExp(r'^[0-9a-f]{64}$').hasMatch(meta['sha256']?.toString() ?? '')) {
        throw EnhancementException('index_shard', entry.key.toString());
      }
    }
    final base = Uri.tryParse(json['base_url']?.toString() ?? '');
    if (base == null || base.scheme != 'https') {
      throw const EnhancementException('index_base_url');
    }
    return EnhancementIndex._(json);
  }
}

/// Shared, lazily loaded catalogue of enhancements.
///
/// Only the compact index is bundled (assets/data). A game's entries live in
/// one shard that is downloaded the first time that game is opened, checked
/// against the SHA-256 and size the index lists, and cached. Nothing here is
/// read when a game launches.
class EnhancementCatalog {
  EnhancementCatalog({
    Future<Directory> Function()? cacheRoot,
    EnhancementFetcher? fetcher,
    Future<Uint8List> Function()? bundledIndex,
  }) : _cacheRoot = cacheRoot ?? defaultCacheRoot,
       _fetcher = fetcher ?? httpFetch,
       _bundledIndex = bundledIndex ?? _loadBundledIndex;

  static final EnhancementCatalog instance = EnhancementCatalog();
  static const bundledIndexAsset = 'assets/data/enhancements_index.json.gz';

  static const _maxIndexBytes = 4 << 20;
  static const _maxIndexExpanded = 32 << 20;
  static const _maxShardBytes = 8 << 20;
  static const _maxShardExpanded = 48 << 20;
  static const _recordCacheSize = 8;

  final Future<Directory> Function() _cacheRoot;
  final EnhancementFetcher _fetcher;
  final Future<Uint8List> Function() _bundledIndex;
  final _log = LoggerService.instance;

  EnhancementIndex? _index;
  Future<EnhancementIndex>? _loading;
  final Map<String, Map<String, dynamic>?> _records = {};
  final Map<String, Future<Map<String, dynamic>?>> _pending = {};

  static Future<Directory> defaultCacheRoot() async {
    final support = await getApplicationSupportDirectory();
    final root = Directory(path.join(support.path, 'RewindBox', 'Enhancements', 'Catalogue'));
    await root.create(recursive: true);
    return root;
  }

  static Future<Uint8List> _loadBundledIndex() async =>
      (await rootBundle.load(bundledIndexAsset)).buffer.asUint8List();

  /// The cached remote index when it is valid, else the bundled one.
  Future<EnhancementIndex> index() {
    final ready = _index;
    if (ready != null) return Future.value(ready);
    return _loading ??= _loadIndex().whenComplete(() => _loading = null);
  }

  Future<EnhancementIndex> _loadIndex() async {
    EnhancementIndex? cached;
    try {
      final file = File(path.join((await _cacheRoot()).path, 'index.json.gz'));
      if (await file.exists()) {
        cached = EnhancementIndex.parse(
          _decodeJson(await file.readAsBytes(), _maxIndexBytes, _maxIndexExpanded),
        );
      }
    } catch (error) {
      _log.w('Enhancements: cached index ignored: $error');
    }
    final bundled = EnhancementIndex.parse(
      _decodeJson(await _bundledIndex(), _maxIndexBytes, _maxIndexExpanded),
    );
    // Revisions start with an ISO date, so the later string is the newer index.
    final chosen =
        cached != null && cached.revision.compareTo(bundled.revision) > 0
        ? cached
        : bundled;
    _index = chosen;
    return chosen;
  }

  /// Downloads the published index. Returns true when a newer one is kept.
  Future<bool> refresh({EnhancementProgress? onProgress}) async {
    final current = await index();
    final uri = Uri.parse(current.baseUrl).resolve('index.json.gz');
    final bytes = await _fetcher(uri, limit: _maxIndexBytes, onProgress: onProgress);
    final fresh = EnhancementIndex.parse(
      _decodeJson(bytes, _maxIndexBytes, _maxIndexExpanded),
    );
    if (fresh.revision.compareTo(current.revision) <= 0) return false;
    final file = File(path.join((await _cacheRoot()).path, 'index.json.gz'));
    await _writeAtomically(file, bytes);
    _index = fresh;
    _records.clear();
    return true;
  }

  /// Whether the shard holding [key] is already verified in the cache.
  Future<bool> isDownloaded(EnhancementEngine engine, String key) async {
    final index = await this.index();
    final entry = index.entry(engine, key);
    if (entry == null) return false;
    final meta = index.shard(entry[2].toString());
    if (meta == null) return false;
    final file = await _shardFile(entry[2].toString());
    return await file.exists() && await file.length() == meta['size'];
  }

  /// The catalogue record of one game, downloading its shard when allowed.
  /// Null when the game has no entry, or when the shard is not cached and
  /// [download] is false.
  Future<Map<String, dynamic>?> record(
    EnhancementEngine engine,
    String key, {
    bool download = true,
    EnhancementProgress? onProgress,
  }) async {
    final index = await this.index();
    final entry = index.entry(engine, key);
    if (entry == null) return null;
    final cacheKey = '${index.revision}/${engine.name}/$key';
    if (_records.containsKey(cacheKey)) return _records[cacheKey];
    final pending = _pending[cacheKey];
    if (pending != null) return pending;
    final future = _readRecord(index, engine, key, entry[2].toString(), download, onProgress);
    _pending[cacheKey] = future;
    try {
      final record = await future;
      if (record != null) {
        _records[cacheKey] = record;
        while (_records.length > _recordCacheSize) {
          _records.remove(_records.keys.first);
        }
      }
      return record;
    } finally {
      _pending.remove(cacheKey);
    }
  }

  Future<Map<String, dynamic>?> _readRecord(
    EnhancementIndex index,
    EnhancementEngine engine,
    String key,
    String shard,
    bool download,
    EnhancementProgress? onProgress,
  ) async {
    final meta = index.shard(shard);
    if (meta == null) throw EnhancementException('shard_missing', shard);
    final file = await _shardFile(shard);
    Uint8List? bytes;
    if (await file.exists()) {
      final cached = await file.readAsBytes();
      if (_matches(cached, meta)) {
        bytes = cached;
      } else {
        _log.w('Enhancements: cached shard $shard is stale or damaged; discarding');
        await file.delete();
      }
    }
    if (bytes == null) {
      if (!download) return null;
      final uri = Uri.parse(index.baseUrl).resolve(meta['path'] as String);
      final fetched = await _fetcher(
        uri,
        limit: (meta['size'] as int).clamp(0, _maxShardBytes),
        onProgress: onProgress,
      );
      if (!_matches(fetched, meta)) {
        throw EnhancementException('shard_integrity', shard);
      }
      await _writeAtomically(file, fetched);
      bytes = fetched;
    }
    final json = _decodeJson(bytes, _maxShardBytes, _maxShardExpanded);
    if (json['schema'] != 1 || json['engine'] != engine.name || json['shard'] != shard) {
      throw EnhancementException('shard_schema', shard);
    }
    final record = (json['keys'] as Map?)?[key];
    return record is Map ? Map<String, dynamic>.from(record) : null;
  }

  bool _matches(Uint8List bytes, Map<String, dynamic> meta) =>
      bytes.length == meta['size'] &&
      sha256.convert(bytes).toString() == meta['sha256'];

  Future<File> _shardFile(String shard) async =>
      File(path.join((await _cacheRoot()).path, 'shards', '$shard.json.gz'));

  /// Size of the downloaded catalogue data.
  Future<int> cacheBytes() async {
    final root = await _cacheRoot();
    var total = 0;
    if (!await root.exists()) return 0;
    await for (final entity in root.list(recursive: true, followLinks: false)) {
      if (entity is File) total += await entity.length();
    }
    return total;
  }

  /// Removes downloaded shards and the refreshed index. Installed native
  /// files are untouched: the store keeps everything needed to remove them.
  Future<void> clearCache() async {
    final root = await _cacheRoot();
    if (await root.exists()) await root.delete(recursive: true);
    _index = null;
    _records.clear();
  }

  static Map<String, dynamic> _decodeJson(Uint8List bytes, int maxPacked, int maxExpanded) {
    if (bytes.length > maxPacked) throw const EnhancementException('too_large');
    final expanded = GZipCodec().decode(bytes);
    if (expanded.length > maxExpanded) throw const EnhancementException('too_large');
    final value = jsonDecode(utf8.decode(expanded));
    if (value is! Map) throw const EnhancementException('not_an_object');
    return Map<String, dynamic>.from(value);
  }

  static Future<void> _writeAtomically(File file, List<int> bytes) async {
    await file.parent.create(recursive: true);
    final temporary = File('${file.path}.partial');
    await temporary.writeAsBytes(bytes, flush: true);
    await temporary.rename(file.path);
  }

  /// HTTPS download with a hard size limit and progress callbacks.
  static Future<Uint8List> httpFetch(
    Uri uri, {
    required int limit,
    EnhancementProgress? onProgress,
  }) async {
    if (uri.scheme != 'https') throw const EnhancementException('insecure_url');
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 20)
      ..idleTimeout = const Duration(seconds: 20);
    try {
      final request = await client.getUrl(uri);
      final response = await request.close().timeout(const Duration(seconds: 60));
      if (response.statusCode != HttpStatus.ok) {
        throw EnhancementException('http_${response.statusCode}', uri.toString());
      }
      final total = response.contentLength > 0 ? response.contentLength : limit;
      if (response.contentLength > limit) throw const EnhancementException('too_large');
      final builder = BytesBuilder(copy: false);
      await for (final chunk in response.timeout(const Duration(seconds: 60))) {
        builder.add(chunk);
        if (builder.length > limit) throw const EnhancementException('too_large');
        onProgress?.call(builder.length, total);
      }
      return builder.takeBytes();
    } finally {
      client.close(force: true);
    }
  }
}
