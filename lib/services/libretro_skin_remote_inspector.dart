import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;
import 'package:path/path.dart' as path;

/// What the catalogs need from a remote skin archive before offering it:
/// its info.json and the names of its files, read with HTTP range requests
/// (the end of the ZIP for its central directory, then info.json alone), so
/// a catalog of hundreds of skins is checked with a few kilobytes each. A
/// host that ignores ranges sends the whole file, read up to the import
/// limit. A ZIP holding a single `.deltaskin` / `.manicskin` is opened the
/// same way as the import does.
class LibretroRemoteSkinArchive {
  const LibretroRemoteSkinArchive({required this.infoJson, required this.entries});

  /// info.json bytes.
  final List<int> infoJson;

  /// Every file of the skin, relative to the folder holding info.json
  /// (`__MACOSX` left out).
  final List<String> entries;
}

class LibretroRemoteSkinInspectionException implements Exception {
  const LibretroRemoteSkinInspectionException(this.message, {this.network = false});

  final String message;

  /// The host could not be reached or answered with an error (retry
  /// later), as opposed to a file that is not a skin.
  final bool network;

  @override
  String toString() => 'LibretroRemoteSkinInspectionException: $message';
}

class LibretroRemoteSkinInspector {
  LibretroRemoteSkinInspector({
    required http.Client client,
    this.timeout = const Duration(seconds: 30),
    this.maxArchiveBytes = 50 * 1024 * 1024,
    this.tailBytes = 65536,
  }) : _client = client;

  final http.Client _client;
  final Duration timeout;
  final int maxArchiveBytes;
  final int tailBytes;

  static const int maxEntries = 1024;
  static const int maxInfoBytes = 1024 * 1024;

  Future<LibretroRemoteSkinArchive> read(Uri uri) async {
    final tail = await _get(uri, range: 'bytes=-$tailBytes');
    if (tail.statusCode == 200) return _fromWhole(tail.bodyBytes);
    if (tail.statusCode != 206) {
      throw LibretroRemoteSkinInspectionException('HTTP ${tail.statusCode} ${uri.host}', network: true);
    }
    final total = _totalLength(tail.headers['content-range']);
    if (total == null || total > maxArchiveBytes) {
      throw const LibretroRemoteSkinInspectionException('archive size unknown or over the import limit');
    }
    final tailStart = total - tail.bodyBytes.length;
    final directory = _centralDirectory(tail.bodyBytes);
    Uint8List central;
    if (directory.offset >= tailStart && directory.offset + directory.size <= total) {
      central = Uint8List.sublistView(
        tail.bodyBytes,
        directory.offset - tailStart,
        directory.offset - tailStart + directory.size,
      );
    } else {
      final response =
          await _get(uri, range: 'bytes=${directory.offset}-${directory.offset + directory.size - 1}');
      if (response.statusCode != 206) {
        throw LibretroRemoteSkinInspectionException('HTTP ${response.statusCode} ${uri.host}', network: true);
      }
      central = response.bodyBytes;
    }
    final entries = _entries(central, directory.count);
    final nested = _nestedSkin(entries);
    if (nested != null) {
      // A ZIP wrapping one skin: its inner archive is needed whole.
      final inner = await _fetchEntry(uri, nested, total);
      if (inner.length > maxArchiveBytes) throw const LibretroRemoteSkinInspectionException('inner skin too large');
      return _fromWhole(inner);
    }
    final info = _infoEntry(entries);
    final bytes = await _fetchEntry(uri, info, total);
    return LibretroRemoteSkinArchive(infoJson: bytes, entries: _relativeNames(entries, info));
  }

  /// Writes the inspection folder the native parser reads: info.json and,
  /// for every image of the archive, a small file of the same name with the
  /// signature of its type (the parser recognises images by content). The
  /// verdict is then about the real layout; the real images are checked
  /// again when the skin is downloaded and installed.
  static Future<void> materialize(LibretroRemoteSkinArchive archive, Directory directory) async {
    await directory.create(recursive: true);
    await File(path.join(directory.path, 'info.json')).writeAsBytes(archive.infoJson, flush: true);
    for (final name in archive.entries) {
      final stub = stubFor(name);
      if (stub == null || !_safeName(name)) continue;
      final file = File(path.join(directory.path, name));
      await file.parent.create(recursive: true);
      await file.writeAsBytes(stub);
    }
  }

  /// Signature bytes of an image named [name], null for other files.
  static List<int>? stubFor(String name) => switch (path.extension(name).toLowerCase()) {
        '.png' => const <int>[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A],
        '.jpg' || '.jpeg' => const <int>[0xFF, 0xD8, 0xFF, 0xE0],
        '.pdf' => ascii.encode('%PDF-1.4\n%%EOF\n'),
        _ => null,
      };

  static bool _safeName(String name) =>
      name.isNotEmpty &&
      !name.startsWith('/') &&
      !name.contains('\\') &&
      !name.split('/').any((part) => part == '..' || part == '__MACOSX');

  Future<http.Response> _get(Uri uri, {String? range}) async {
    final request = http.Request('GET', uri);
    if (range != null) request.headers['Range'] = range;
    try {
      final response = await _client.send(request).timeout(timeout);
      final declared = response.contentLength;
      if (declared != null && declared > maxArchiveBytes) {
        await response.stream.listen(null).cancel();
        throw const LibretroRemoteSkinInspectionException('response over the import limit');
      }
      final builder = BytesBuilder(copy: false);
      await for (final chunk in response.stream.timeout(timeout)) {
        builder.add(chunk);
        if (builder.length > maxArchiveBytes) {
          throw const LibretroRemoteSkinInspectionException('response over the import limit');
        }
      }
      return http.Response.bytes(builder.takeBytes(), response.statusCode, headers: response.headers);
    } on LibretroRemoteSkinInspectionException {
      rethrow;
    } on TimeoutException catch (error) {
      throw LibretroRemoteSkinInspectionException('$error', network: true);
    } on IOException catch (error) {
      throw LibretroRemoteSkinInspectionException('$error', network: true);
    } on http.ClientException catch (error) {
      throw LibretroRemoteSkinInspectionException('$error', network: true);
    }
  }

  static int? _totalLength(String? contentRange) {
    if (contentRange == null) return null;
    final slash = contentRange.lastIndexOf('/');
    return slash < 0 ? null : int.tryParse(contentRange.substring(slash + 1).trim());
  }

  Future<Uint8List> _fetchEntry(Uri uri, _ZipEntry entry, int total) async {
    if (entry.uncompressedSize > maxInfoBytes && entry.name.toLowerCase().endsWith('.json')) {
      throw const LibretroRemoteSkinInspectionException('info.json too large');
    }
    final end = (entry.localOffset + 30 + 1024 + entry.compressedSize).clamp(0, total) - 1;
    final response = await _get(uri, range: 'bytes=${entry.localOffset}-$end');
    if (response.statusCode != 206) {
      throw LibretroRemoteSkinInspectionException('HTTP ${response.statusCode} ${uri.host}', network: true);
    }
    final bytes = response.bodyBytes;
    if (bytes.length >= 30) {
      // A local header whose name and extra field exceed the 1 KiB guessed:
      // read the entry again with its exact length.
      final header = ByteData.sublistView(bytes);
      final needed = 30 +
          header.getUint16(26, Endian.little) +
          header.getUint16(28, Endian.little) +
          entry.compressedSize;
      if (needed > bytes.length && entry.localOffset + needed <= total) {
        final again = await _get(uri, range: 'bytes=${entry.localOffset}-${entry.localOffset + needed - 1}');
        if (again.statusCode != 206) {
          throw LibretroRemoteSkinInspectionException('HTTP ${again.statusCode} ${uri.host}', network: true);
        }
        return _entryData(again.bodyBytes, 0, entry);
      }
    }
    return _entryData(bytes, 0, entry);
  }

  LibretroRemoteSkinArchive _fromWhole(Uint8List bytes) {
    if (bytes.length > maxArchiveBytes) throw const LibretroRemoteSkinInspectionException('archive too large');
    final directory = _centralDirectory(bytes);
    if (directory.offset + directory.size > bytes.length) {
      throw const LibretroRemoteSkinInspectionException('truncated archive');
    }
    final entries = _entries(Uint8List.sublistView(bytes, directory.offset, directory.offset + directory.size),
        directory.count);
    final nested = _nestedSkin(entries);
    if (nested != null) {
      final inner = _entryData(bytes, nested.localOffset, nested);
      return _fromWhole(inner);
    }
    final info = _infoEntry(entries);
    return LibretroRemoteSkinArchive(
      infoJson: _entryData(bytes, info.localOffset, info),
      entries: _relativeNames(entries, info),
    );
  }

  static _CentralDirectory _centralDirectory(Uint8List bytes) {
    final data = ByteData.sublistView(bytes);
    for (var index = bytes.length - 22; index >= 0 && index >= bytes.length - 22 - 65535; index--) {
      if (data.getUint32(index, Endian.little) == 0x06054b50) {
        return _CentralDirectory(
          count: data.getUint16(index + 10, Endian.little),
          size: data.getUint32(index + 12, Endian.little),
          offset: data.getUint32(index + 16, Endian.little),
        );
      }
    }
    throw const LibretroRemoteSkinInspectionException('not a ZIP archive');
  }

  static List<_ZipEntry> _entries(Uint8List central, int count) {
    if (count > maxEntries) throw const LibretroRemoteSkinInspectionException('too many files');
    final data = ByteData.sublistView(central);
    final entries = <_ZipEntry>[];
    var position = 0;
    while (position + 46 <= central.length && data.getUint32(position, Endian.little) == 0x02014b50) {
      final nameLength = data.getUint16(position + 28, Endian.little);
      final extraLength = data.getUint16(position + 30, Endian.little);
      final commentLength = data.getUint16(position + 32, Endian.little);
      if (position + 46 + nameLength > central.length) break;
      final name = utf8.decode(central.sublist(position + 46, position + 46 + nameLength), allowMalformed: true);
      entries.add(_ZipEntry(
        name: name,
        method: data.getUint16(position + 10, Endian.little),
        compressedSize: data.getUint32(position + 20, Endian.little),
        uncompressedSize: data.getUint32(position + 24, Endian.little),
        localOffset: data.getUint32(position + 42, Endian.little),
      ));
      position += 46 + nameLength + extraLength + commentLength;
      if (entries.length > maxEntries) throw const LibretroRemoteSkinInspectionException('too many files');
    }
    if (entries.isEmpty) throw const LibretroRemoteSkinInspectionException('empty archive');
    return entries;
  }

  static bool _ignored(String name) => name.startsWith('__MACOSX/') || name.endsWith('/');

  /// info.json at the root, or in the single folder holding everything.
  static _ZipEntry _infoEntry(List<_ZipEntry> entries) {
    final files = entries.where((entry) => !_ignored(entry.name)).toList();
    for (final entry in files) {
      if (entry.name == 'info.json') return entry;
    }
    final tops = files.map((entry) => entry.name.split('/').first).toSet();
    if (tops.length == 1) {
      final top = tops.first;
      for (final entry in files) {
        if (entry.name == '$top/info.json') return entry;
      }
    }
    throw const LibretroRemoteSkinInspectionException('no info.json');
  }

  /// The single `.deltaskin` / `.manicskin` of a wrapping ZIP without its own
  /// info.json; null otherwise.
  static _ZipEntry? _nestedSkin(List<_ZipEntry> entries) {
    final files = entries.where((entry) => !_ignored(entry.name)).toList();
    if (files.any((entry) => path.basename(entry.name) == 'info.json')) return null;
    final skins = files.where((entry) {
      final lower = entry.name.toLowerCase();
      return lower.endsWith('.deltaskin') || lower.endsWith('.manicskin');
    }).toList();
    if (skins.length != 1) return null;
    return skins.first;
  }

  static List<String> _relativeNames(List<_ZipEntry> entries, _ZipEntry info) {
    final prefix = info.name.contains('/') ? '${info.name.substring(0, info.name.lastIndexOf('/'))}/' : '';
    return <String>[
      for (final entry in entries)
        if (!_ignored(entry.name) && entry.name.startsWith(prefix) && entry.name != info.name)
          entry.name.substring(prefix.length),
    ];
  }

  /// Data of [entry] whose local header starts at [offset] in [bytes].
  Uint8List _entryData(Uint8List bytes, int offset, _ZipEntry entry) {
    final data = ByteData.sublistView(bytes);
    if (offset + 30 > bytes.length || data.getUint32(offset, Endian.little) != 0x04034b50) {
      throw const LibretroRemoteSkinInspectionException('bad local header');
    }
    final nameLength = data.getUint16(offset + 26, Endian.little);
    final extraLength = data.getUint16(offset + 28, Endian.little);
    final start = offset + 30 + nameLength + extraLength;
    final end = start + entry.compressedSize;
    if (end > bytes.length) throw const LibretroRemoteSkinInspectionException('truncated entry');
    final compressed = Uint8List.sublistView(bytes, start, end);
    switch (entry.method) {
      case 0:
        return Uint8List.fromList(compressed);
      case 8:
        final inflated = ZLibDecoder(raw: true).convert(compressed);
        if (inflated.length > maxArchiveBytes) throw const LibretroRemoteSkinInspectionException('entry too large');
        return Uint8List.fromList(inflated);
      default:
        throw LibretroRemoteSkinInspectionException('compression method ${entry.method}');
    }
  }
}

class _CentralDirectory {
  const _CentralDirectory({required this.count, required this.size, required this.offset});

  final int count;
  final int size;
  final int offset;
}

class _ZipEntry {
  const _ZipEntry({
    required this.name,
    required this.method,
    required this.compressedSize,
    required this.uncompressedSize,
    required this.localOffset,
  });

  final String name;
  final int method;
  final int compressedSize;
  final int uncompressedSize;
  final int localOffset;
}
