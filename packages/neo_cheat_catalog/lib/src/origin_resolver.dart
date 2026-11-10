import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';

import 'canonical_json.dart';
import 'origin_recipe.dart';

/// Downloads [uri] (at most [limit] bytes).
typedef OriginFetch = Future<Uint8List> Function(Uri uri, int limit);

/// Rebuilds the packs of the unified catalogue's origin publication (v2).
///
/// A v2 pack is a hosted pack whose programs from sources RewindBox does not
/// host keep no code: each holds a recipe (`origin`) pointing into a file of
/// the pack's own `origin.files` table, at the source's pinned revision.
/// [resolve] downloads those files from the sources (each checked against
/// its size and SHA-256, then cached), rebuilds every chunk and returns the
/// pack as the hosted publication would have served it. The native catalogue
/// then verifies each chunk against the manifest, as it always does.
class OriginResolver {
  OriginResolver({required this.cache, OriginFetch? fetch}) : _fetch = fetch ?? httpFetch;

  final Directory cache;
  final OriginFetch _fetch;
  final Map<String, Archive> _zips = {};

  /// The standard pack JSON (`{schema_version, files: [{game_id, data}]}`)
  /// of a v2 pack's JSON bytes.
  Future<Uint8List> resolve(Uint8List packJson, {void Function(int done, int total)? onProgress}) async {
    final pack = jsonDecode(utf8.decode(packJson)) as Map<String, dynamic>;
    final origin = pack['origin'] as Map<String, dynamic>? ?? const {};
    final table = [for (final file in (origin['files'] as List? ?? const [])) Map<String, dynamic>.from(file as Map)];
    final sources = Map<String, dynamic>.from(origin['sources'] as Map? ?? const {});
    final contents = <int, Uint8List>{};
    final needed = <int>{};
    for (final file in (pack['files'] as List)) {
      if ((file as Map)['skeleton'] == null) continue;
      final chunk = jsonDecode(utf8.decode(base64Decode(file['skeleton'] as String))) as Map<String, dynamic>;
      for (final program in (chunk['cheats'] as List)) {
        final recipe = (program as Map)['origin'];
        if (recipe is Map) needed.add(recipe['f'] as int);
      }
    }
    var done = 0;
    for (final index in needed) {
      contents[index] = await _file(table[index], Map<String, dynamic>.from(sources[table[index]['source']] as Map));
      onProgress?.call(++done, needed.length);
    }
    final files = <Map<String, dynamic>>[];
    for (final file in (pack['files'] as List)) {
      final entry = Map<String, dynamic>.from(file as Map);
      final skeleton = entry.remove('skeleton');
      if (skeleton == null) {
        files.add(entry);
        continue;
      }
      final chunk = jsonDecode(utf8.decode(base64Decode(skeleton as String))) as Map<String, dynamic>;
      chunk['cheats'] = [
        for (final program in (chunk['cheats'] as List))
          _program(Map<String, dynamic>.from(program as Map), table, contents),
      ];
      files.add({...entry, 'data': base64Encode(canonicalJson(chunk))});
    }
    return Uint8List.fromList(utf8.encode(jsonEncode({'schema_version': 1, 'files': files})));
  }

  Map<String, dynamic> _program(
    Map<String, dynamic> program,
    List<Map<String, dynamic>> table,
    Map<int, Uint8List> contents,
  ) {
    final recipe = program.remove('origin');
    if (recipe is! Map) return program;
    final index = recipe['f'] as int;
    var member = contents[index]!;
    final inner = recipe['z'];
    if (inner is String) {
      final archive = _zips[table[index]['sha256'] as String] ??= ZipDecoder().decodeBytes(member);
      final found = archive.findFile(inner);
      if (found == null) throw FormatException('origin member missing: $inner');
      member = Uint8List.fromList(found.content as List<int>);
    }
    return {
      ...program,
      ...OriginRecipe.rebuild(Map<String, dynamic>.from(recipe), member, program['dialect'] as String),
    };
  }

  /// One origin file, from the cache or its source, always SHA-256 checked.
  Future<Uint8List> _file(Map<String, dynamic> file, Map<String, dynamic> source) async {
    final digest = file['sha256'] as String;
    final size = file['size'] as int;
    if (!RegExp(r'^[0-9a-f]{64}$').hasMatch(digest)) throw const FormatException('origin digest');
    final cached = await _cached(digest, size);
    if (cached != null) return cached;
    final archive = source['archive'];
    final name = file['source'] as String;
    // Many files of one source (a bulk install): its pinned archive, once,
    // instead of thousands of requests.
    if (archive is String &&
        (_archiveMode.contains(name) || (_rawRequests[name] = (_rawRequests[name] ?? 0) + 1) > archiveThreshold)) {
      if (_archived.add(name)) {
        try {
          await extractArchive(Uri.parse(archive), _fetchToFile);
        } on Exception {
          // The archive is only a shortcut: the raw files remain the source.
          _archiveMode.remove(name);
          _rawRequests[name] = -1 << 30;
        }
      }
      final extracted = await _cached(digest, size);
      if (extracted != null) return extracted;
    }
    final uri = originUri(file, source);
    Uint8List bytes;
    try {
      bytes = await _fetch(uri, size);
    } on HttpException catch (error) {
      if (archive is! String || !error.message.contains('429') || _archived.contains(name) || !_archiveMode.add(name)) {
        rethrow;
      }
      return _file(file, source);
    }
    if (bytes.length != size || sha256.convert(bytes).toString() != digest) {
      throw OriginIntegrityError(uri);
    }
    await _store(digest, bytes);
    _remember(digest, bytes);
    return bytes;
  }

  /// Raw requests to one source before its archive is used instead.
  static const archiveThreshold = 64;
  final Map<String, int> _rawRequests = {};
  final Set<String> _archiveMode = {};
  final Set<String> _archived = {};

  /// Downloads [uri] into a temporary file (large archives never sit in memory).
  Future<File> Function(Uri uri)? fetchToFile;

  Future<File> _fetchToFile(Uri uri) async {
    final custom = fetchToFile;
    if (custom != null) return custom(uri);
    final target = File('${cache.path}/archive-${DateTime.now().microsecondsSinceEpoch}.tar.gz');
    await cache.create(recursive: true);
    final client = HttpClient()..connectionTimeout = const Duration(seconds: 20);
    try {
      final response = await (await client.getUrl(uri)).close();
      if (response.statusCode != HttpStatus.ok) throw HttpException('HTTP ${response.statusCode}', uri: uri);
      await response.pipe(target.openWrite());
      return target;
    } finally {
      client.close(force: true);
    }
  }

  /// Stores every regular file of a .tar.gz under its SHA-256. Names are not
  /// trusted: a file is only ever used when a pack asks for that digest.
  Future<void> extractArchive(Uri uri, Future<File> Function(Uri uri) download) async {
    final archive = await download(uri);
    try {
      await for (final entry in tarEntries(archive.openRead().transform(gzip.decoder))) {
        await _store(sha256.convert(entry).toString(), entry);
      }
    } finally {
      if (await archive.exists()) await archive.delete();
    }
  }

  /// Verified files kept in memory across the packs of one install (a large
  /// shared file such as a whole cheat database is hashed once).
  static const memoryBudget = 64 << 20;
  final Map<String, Uint8List> _memory = {};
  var _memoryBytes = 0;

  void _remember(String digest, Uint8List bytes) {
    if (bytes.length > memoryBudget ~/ 2 || _memory.containsKey(digest)) return;
    while (_memoryBytes + bytes.length > memoryBudget && _memory.isNotEmpty) {
      _memoryBytes -= _memory.remove(_memory.keys.first)!.length;
    }
    _memory[digest] = bytes;
    _memoryBytes += bytes.length;
  }

  Future<Uint8List?> _cached(String digest, int size) async {
    final remembered = _memory[digest];
    if (remembered != null) return remembered;
    final cached = File('${cache.path}/$digest');
    if (!await cached.exists()) return null;
    final bytes = await cached.readAsBytes();
    if (bytes.length == size && sha256.convert(bytes).toString() == digest) {
      _remember(digest, bytes);
      return bytes;
    }
    await cached.delete();
    return null;
  }

  Future<void> _store(String digest, List<int> bytes) async {
    await cache.create(recursive: true);
    final target = File('${cache.path}/$digest');
    if (await target.exists()) return;
    final partial = File('${target.path}.partial');
    await partial.writeAsBytes(bytes, flush: true);
    await partial.rename(target.path);
  }

  /// The regular files of a tar stream (ustar, GNU and pax headers skipped),
  /// each at most 64 MiB.
  static Stream<Uint8List> tarEntries(Stream<List<int>> input) async* {
    final pending = BytesBuilder(copy: false);
    var buffer = Uint8List(0);
    var offset = 0;
    Future<bool> fill(int count, StreamIterator<List<int>> it) async {
      while (buffer.length - offset < count) {
        if (!await it.moveNext()) return false;
        pending
          ..add(Uint8List.sublistView(buffer, offset))
          ..add(it.current);
        buffer = pending.takeBytes();
        offset = 0;
      }
      return true;
    }

    final it = StreamIterator(input);
    while (await fill(512, it)) {
      final header = Uint8List.sublistView(buffer, offset, offset + 512);
      offset += 512;
      if (header.every((b) => b == 0)) break;
      final sizeField = ascii.decode(header.sublist(124, 136), allowInvalid: true).replaceAll('\x00', '').trim();
      final size = sizeField.isEmpty ? 0 : int.parse(sizeField, radix: 8);
      if (size > 64 << 20) throw const FormatException('tar entry too large');
      final padded = (size + 511) & ~511;
      if (!await fill(padded, it)) throw const FormatException('truncated tar');
      final type = header[156];
      if (type == 0x30 || type == 0) yield Uint8List.fromList(Uint8List.sublistView(buffer, offset, offset + size));
      offset += padded;
    }
    await it.cancel();
  }

  /// The URL of an origin file: the source's single archive, or its raw
  /// file template with the path's segments escaped.
  static Uri originUri(Map<String, dynamic> file, Map<String, dynamic> source) {
    final bundle = source['bundle'];
    final uri = bundle is String
        ? Uri.parse(bundle)
        : Uri.parse(
            (source['raw'] as String).replaceFirst(
              '{path}',
              (file['path'] as String).split('/').map(Uri.encodeComponent).join('/'),
            ),
          );
    if (uri.scheme != 'https' || uri.host.isEmpty) throw FormatException('origin URL: $uri');
    return uri;
  }

  static Future<Uint8List> httpFetch(Uri uri, int limit) async {
    final client = HttpClient()
      ..connectionTimeout = const Duration(seconds: 20)
      ..idleTimeout = const Duration(seconds: 30);
    try {
      for (var attempt = 0; ; attempt++) {
        final request = await client.getUrl(uri);
        final response = await request.close().timeout(const Duration(seconds: 60));
        if ((response.statusCode == 429 || response.statusCode >= 500) && attempt < 3) {
          await response.drain<void>();
          await Future<void>.delayed(Duration(seconds: 2 << attempt));
          continue;
        }
        if (response.statusCode != HttpStatus.ok) throw HttpException('HTTP ${response.statusCode}', uri: uri);
        final builder = BytesBuilder(copy: false);
        await for (final chunk in response.timeout(const Duration(seconds: 60))) {
          builder.add(chunk);
          if (builder.length > limit) throw HttpException('origin file larger than listed', uri: uri);
        }
        return builder.takeBytes();
      }
    } finally {
      client.close(force: true);
    }
  }
}

/// An origin file whose bytes differ from the pinned revision.
class OriginIntegrityError implements Exception {
  OriginIntegrityError(this.uri);
  final Uri uri;
  @override
  String toString() => 'Origin file changed at its source: $uri';
}
