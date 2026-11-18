import 'dart:async';
import 'dart:io';
import 'dart:typed_data';

import 'package:archive/archive.dart';
import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;

import 'nextendo_config.dart';

/// A game's BCAT delivery data, kept on the device for the engine to serve.
///
/// Nextendo's integration guide ("BCAT data"): some titles need their delivery
/// data to show menus or rotations (Splatoon 2 and 3, Pokémon Scarlet and
/// Violet, Legends: Z-A, Sword and Shield, Nintendo Switch Sports and Super
/// Smash Bros. Ultimate, whose menu banner otherwise asks to connect to the
/// Internet). Download it as a zip from `GET /api/bcat/<titleId>`, serve it from
/// a writable folder, and replace it when it changes instead of serving a stale
/// copy. A title without data answers 204.
///
/// Folder: `<MeloNX root>/nextendo/bcat/<titleId>/<directory>/<file>`, exactly
/// the zip's two levels. The engine serves it as the game's delivery cache
/// while the session is online. Checked at each online launch of the title: an
/// archive whose SHA-256 differs replaces the folder whole (written apart, then
/// swapped); 204 removes it; a failed request keeps the copy already there.
abstract final class NextendoBcat {
  static const maxArchiveBytes = 64 * 1024 * 1024;
  static const maxFiles = 2048;
  static final _inFlight = <String, Future<String?>>{};
  static const _etagFile = '.archive-etag';
  static const _hashFile = '.archive-sha256';
  // A plain name with at least one letter or digit: never '.' or '..'.
  static final _name = RegExp(r'^(?=.*[A-Za-z0-9])[A-Za-z0-9_.-]{1,31}$');
  static final _titleId = RegExp(r'^[0-9a-f]{16}$');

  /// The folder of [titleId] under [root] (the MeloNX data root).
  static Directory folder(Directory root, String titleId) =>
      Directory(p.join(root.path, 'nextendo', 'bcat', titleId.toLowerCase()));

  /// Brings the title's folder up to date and returns its path, or null when
  /// Nextendo has no data for the title (or never could be reached and nothing
  /// is kept). [onEvent] receives one short word for the launch journal.
  static Future<String?> prepare({
    required Directory root,
    required String titleId,
    http.Client? client,
    void Function(String event)? onEvent,
  }) async {
    final id = titleId.toLowerCase();
    if (!_titleId.hasMatch(id)) return null;
    final target = folder(root, id);
    final pending = _inFlight[target.path];
    if (pending != null) return pending;
    final started = _refresh(target, id, client, onEvent);
    _inFlight[target.path] = started;
    try {
      return await started;
    } finally {
      _inFlight.remove(target.path);
    }
  }

  static Future<String?> _refresh(Directory target, String id, http.Client? client, void Function(String)? onEvent) async {
    final owned = client == null;
    final http.Client http0 = client ?? http.Client();
    try {
      final etagFile = File(p.join(target.path, _etagFile));
      final existing = await _existing(target);
      final etag = existing != null && await etagFile.exists() ? await etagFile.readAsString() : '';
      final response = await _download(http0, id, etag).timeout(const Duration(seconds: 10));
      if (response.statusCode == 304 && existing != null && etag.isNotEmpty) {
        onEvent?.call('current');
        return existing;
      }
      if (response.statusCode == 204 || response.statusCode == 404) {
        if (await target.exists()) await target.delete(recursive: true);
        onEvent?.call('none');
        return null;
      }
      if (response.statusCode != 200 || response.bodyBytes.isEmpty || response.bodyBytes.length > maxArchiveBytes) {
        onEvent?.call('kept:${response.statusCode}');
        return await _existing(target);
      }
      final digest = sha256.convert(response.bodyBytes).toString();
      final newEtag = response.headers['etag'] ?? '';
      final hashFile = File(p.join(target.path, _hashFile));
      if (existing != null && await hashFile.exists() && (await hashFile.readAsString()).trim() == digest) {
        if (newEtag != etag) await etagFile.writeAsString(newEtag);
        onEvent?.call('current');
        return target.path;
      }
      await _install(target, response.bodyBytes, digest, newEtag);
      onEvent?.call('updated');
      return target.path;
    } on Object catch (error) {
      onEvent?.call('kept:${error.runtimeType}');
      return await _existing(target);
    } finally {
      if (owned) http0.close();
    }
  }

  static Future<http.Response> _download(http.Client http0, String id, String etag) async {
    final request = http.Request('GET', Uri.parse('${NextendoConfig.apiBase}/api/bcat/$id'));
    request.headers['Accept'] = 'application/zip';
    if (etag.isNotEmpty && etag.length <= 512 && !etag.contains(RegExp(r'[\r\n]'))) {
      request.headers['If-None-Match'] = etag;
    }
    final response = await http0.send(request);
    if (response.statusCode != 200 || (response.contentLength ?? 0) > maxArchiveBytes) {
      await response.stream.listen((_) {}).cancel();
      return http.Response('', response.statusCode);
    }
    final body = BytesBuilder(copy: false);
    await for (final chunk in response.stream) {
      if (chunk.length > maxArchiveBytes - body.length) throw const FormatException('bcat archive size');
      body.add(chunk);
    }
    return http.Response.bytes(body.takeBytes(), response.statusCode, headers: response.headers);
  }

  static Future<String?> _existing(Directory target) async {
    try {
      if (!await target.exists()) return null;
      await for (final entity in target.list()) {
        if (entity is Directory) return target.path;
      }
    } on Object {
      // Unreadable: nothing to serve.
    }
    return null;
  }

  /// Every entry must be `<directory>/<file>` with plain names; anything else
  /// (deeper paths, absolute or parent paths, odd names, too many files) refuses
  /// the whole archive and leaves the previous folder as it was.
  static Future<void> _install(Directory target, List<int> bytes, String digest, String etag) async {
    final archive = ZipDecoder().decodeBytes(bytes);
    final files = <(String, String, ArchiveFile)>[];
    var total = 0;
    for (final entry in archive) {
      final name = entry.name.replaceAll('\\', '/');
      if (!entry.isFile) {
        final trimmed = name.endsWith('/') ? name.substring(0, name.length - 1) : name;
        if (trimmed.isEmpty || _name.hasMatch(trimmed)) continue;
        throw const FormatException('bcat directory name');
      }
      final parts = name.split('/');
      if (parts.length != 2 || !_name.hasMatch(parts[0]) || !_name.hasMatch(parts[1])) {
        throw const FormatException('bcat entry name');
      }
      total += entry.size;
      if (files.length >= maxFiles || entry.size < 0 || total > maxArchiveBytes * 4) throw const FormatException('bcat archive size');
      files.add((parts[0], parts[1], entry));
    }
    final parent = target.parent;
    await parent.create(recursive: true);
    final stamp = DateTime.now().microsecondsSinceEpoch;
    final staging = Directory(p.join(parent.path, '.${p.basename(target.path)}.new-$stamp'));
    final previous = Directory(p.join(parent.path, '.${p.basename(target.path)}.old-$stamp'));
    var moved = false;
    try {
      for (final (directory, file, entry) in files) {
        final content = entry.content;
        if (content.length != entry.size) throw const FormatException('bcat entry size');
        final out = File(p.join(staging.path, directory, file));
        await out.parent.create(recursive: true);
        await out.writeAsBytes(content, flush: true);
        entry.clear();
      }
      await staging.create(recursive: true);
      await File(p.join(staging.path, _hashFile)).writeAsString(digest, flush: true);
      if (etag.isNotEmpty && etag.length <= 512) await File(p.join(staging.path, _etagFile)).writeAsString(etag);
      if (await target.exists()) {
        await target.rename(previous.path);
        moved = true;
      }
      await staging.rename(target.path);
      moved = false;
    } catch (_) {
      // The swap failed half-way: the previous folder goes back in place.
      if (moved && !await target.exists() && await previous.exists()) await previous.rename(target.path);
      rethrow;
    } finally {
      if (await staging.exists()) await staging.delete(recursive: true);
      if (await previous.exists()) await previous.delete(recursive: true);
    }
  }
}
