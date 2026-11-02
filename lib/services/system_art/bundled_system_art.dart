import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart' as crypto;
import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as path;

import '../config_service.dart';
import '../logger_service.dart';

/// Installs the System Art pack embedded in the application ("RewindBox
/// Glacier", stable id `rewindbox-glacier`) into the same folder as downloaded
/// packs, `<user data>/themes/rewindbox-glacier/`, without any network request
/// — a first launch in airplane mode included.
///
/// - The installation is versioned by the pack's `contentDigest`
///   (`bundle-index.json`): an installed copy at the same digest is only
///   checked file by file (sizes), never copied or decoded again at startup.
/// - Files are written to a staging folder, verified (size and SHA-256), then
///   swapped in; the previous copy is kept until the swap succeeded and is
///   restored if the new one could not be completed. A swap interrupted by a
///   kill is resumed on the next launch.
/// - Concurrent requests share one installation.
class BundledSystemArt {
  BundledSystemArt._();

  static const String folder = 'rewindbox-glacier';
  static const String assetRoot = 'assets/system_art/rewindbox-glacier';
  static const String indexAsset = '$assetRoot/bundle-index.json';
  static const String themeAsset = '$assetRoot/theme.json';
  static const String previewAsset = '$assetRoot/preview.webp';
  static const String installRecordName = '.bundle-install.json';

  static final _log = LoggerService.instance;
  static final RegExp _safeRelative = RegExp(
    r'^(backgrounds/)?[A-Za-z0-9][A-Za-z0-9._ -]*$',
  );

  @visibleForTesting
  static AssetBundle? bundleOverride;
  @visibleForTesting
  static Future<String> Function()? themesDirectoryOverride;

  static Future<bool>? _inFlight;

  static bool isBundled(String themeFolder) => themeFolder == folder;

  static AssetBundle get _bundle => bundleOverride ?? rootBundle;

  static Future<String> _themesDirectory() async {
    final override = themesDirectoryOverride;
    if (override != null) return override();
    return path.join(await ConfigService.getUserDataPath(), 'themes');
  }

  /// Name, author and AI flag of the embedded pack (from its theme.json).
  static Future<Map<String, dynamic>> metadata() async {
    final decoded = jsonDecode(await _bundle.loadString(themeAsset));
    return decoded is Map<String, dynamic> ? decoded : const {};
  }

  /// Installs (or confirms) the embedded pack. Returns whether a complete copy
  /// of the current version is in place.
  static Future<bool> ensureInstalled() {
    final running = _inFlight;
    if (running != null) return running;
    final future = _install();
    _inFlight = future;
    return future.whenComplete(() => _inFlight = null);
  }

  static Future<bool> _install() async {
    final Map<String, dynamic> index;
    try {
      final decoded = jsonDecode(await _bundle.loadString(indexAsset));
      if (decoded is! Map<String, dynamic> ||
          decoded['schema'] != 1 ||
          decoded['id'] != folder) {
        throw const FormatException('Unexpected bundle index');
      }
      index = decoded;
    } catch (e) {
      _log.e('Bundled System Art index unavailable: $e');
      return false;
    }
    final files = (index['files'] as List? ?? const [])
        .whereType<Map>()
        .map((entry) => Map<String, dynamic>.from(entry))
        .toList(growable: false);
    final digest = index['contentDigest']?.toString() ?? '';
    if (files.isEmpty || digest.isEmpty) return false;

    final themes = Directory(await _themesDirectory());
    final target = Directory(path.join(themes.path, folder));
    final previous = Directory(path.join(themes.path, '.$folder.previous'));
    try {
      await themes.create(recursive: true);
      await _recover(themes, target, previous);
      if (await _isComplete(target, digest, files)) return true;
    } catch (e) {
      _log.w('Bundled System Art check failed: $e');
    }

    final staging = Directory(
      path.join(
        themes.path,
        '.$folder.installing-${DateTime.now().microsecondsSinceEpoch}',
      ),
    );
    try {
      await staging.create(recursive: true);
      for (final file in files) {
        final relative = file['path']?.toString() ?? '';
        if (!_safeRelative.hasMatch(relative) || relative.contains('..')) {
          throw StateError('Unsafe pack entry: $relative');
        }
        final data = await _bundle.load('$assetRoot/$relative');
        final bytes = data.buffer.asUint8List(
          data.offsetInBytes,
          data.lengthInBytes,
        );
        if (bytes.length != file['size'] ||
            crypto.sha256.convert(bytes).toString() != file['sha256']) {
          throw StateError(
            'Embedded pack file differs from its index: $relative',
          );
        }
        final out = File(path.join(staging.path, relative));
        if (!path.isWithin(staging.path, out.path)) {
          throw StateError('Pack entry outside the pack: $relative');
        }
        await out.parent.create(recursive: true);
        await out.writeAsBytes(bytes, flush: true);
      }
      await File(path.join(staging.path, installRecordName)).writeAsString(
        jsonEncode({
          'schema': 1,
          'id': folder,
          'version': index['version'],
          'contentDigest': digest,
          'files': files.length,
          'complete': true,
          'installedAt': DateTime.now().toUtc().toIso8601String(),
        }),
        flush: true,
      );
      // Swap: the previous copy stays until the new one is in place.
      if (await previous.exists()) await previous.delete(recursive: true);
      if (await target.exists()) await target.rename(previous.path);
      await staging.rename(target.path);
      if (await previous.exists()) await previous.delete(recursive: true);
      _log.i(
        'Bundled System Art installed: $folder ${index['version']} (${files.length} files)',
      );
      return true;
    } catch (e) {
      _log.e('Bundled System Art installation failed, previous pack kept: $e');
      try {
        if (await staging.exists()) await staging.delete(recursive: true);
        if (!await target.exists() && await previous.exists()) {
          await previous.rename(target.path);
        }
      } catch (_) {
        // The next launch resumes from whatever state remains.
      }
      return false;
    }
  }

  /// Resumes a swap interrupted between its two renames and removes stale
  /// staging folders.
  static Future<void> _recover(
    Directory themes,
    Directory target,
    Directory previous,
  ) async {
    if (!await target.exists() && await previous.exists()) {
      await previous.rename(target.path);
    } else if (await previous.exists()) {
      await previous.delete(recursive: true);
    }
    await for (final entry in themes.list()) {
      if (entry is Directory &&
          path.basename(entry.path).startsWith('.$folder.installing-')) {
        await entry.delete(recursive: true);
      }
    }
  }

  static Future<bool> _isComplete(
    Directory target,
    String digest,
    List<Map<String, dynamic>> files,
  ) async {
    final record = File(path.join(target.path, installRecordName));
    if (!await record.exists()) return false;
    try {
      final decoded = jsonDecode(await record.readAsString());
      if (decoded is! Map ||
          decoded['complete'] != true ||
          decoded['contentDigest'] != digest) {
        return false;
      }
    } catch (_) {
      return false;
    }
    for (final file in files) {
      final entry = File(path.join(target.path, file['path'].toString()));
      if (!await entry.exists() || await entry.length() != file['size']) {
        return false;
      }
    }
    return true;
  }
}
