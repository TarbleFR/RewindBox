import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/services.dart' show rootBundle;

/// An original controller pack shipped with the app, available offline.
class BundledControllerSkin {
  const BundledControllerSkin({
    required this.id,
    required this.name,
    required this.console,
    required this.archiveAsset,
    required this.sha256,
    required this.size,
    required this.previewAssets,
    required this.author,
    required this.license,
  });

  final String id;
  final String name;
  final String console;
  final String archiveAsset;
  final String sha256;
  final int size;
  final Map<String, String> previewAssets;
  final String author;
  final String license;

  static const catalogAsset = 'assets/skins/pocket/catalog.json';
  static const _prefix = 'assets/skins/pocket/';
  static const maxArchiveBytes = 50 * 1024 * 1024;

  static Future<List<BundledControllerSkin>> load({
    Future<ByteData> Function(String)? loadAsset,
  }) async {
    final data = await (loadAsset ?? rootBundle.load)(catalogAsset);
    final decoded = jsonDecode(
      utf8.decode(
        data.buffer.asUint8List(data.offsetInBytes, data.lengthInBytes),
      ),
    );
    if (decoded is! Map ||
        decoded['schemaVersion'] != 1 ||
        decoded['skins'] is! List) {
      throw const FormatException('Invalid bundled skin catalog');
    }
    final ids = <String>{};
    final result = <BundledControllerSkin>[];
    for (final raw in decoded['skins'] as List) {
      if (raw is! Map) {
        throw const FormatException('Invalid bundled skin');
      }
      String string(String field) {
        final value = raw[field];
        if (value is! String || value.trim().isEmpty) {
          throw FormatException('Missing bundled skin $field');
        }
        return value;
      }

      String asset(String value, String extension) {
        if (!value.startsWith(_prefix) ||
            value.contains('..') ||
            value.contains('\\') ||
            !value.endsWith(extension) ||
            value.substring(_prefix.length).contains('/')) {
          throw const FormatException('Unsafe bundled skin asset');
        }
        return value;
      }

      final id = string('id');
      final console = string('console');
      final digest = string('sha256');
      final size = raw['size'];
      if (!RegExp(r'^[a-z0-9]+(?:-[a-z0-9]+)*$').hasMatch(id) ||
          !ids.add(id) ||
          !const ['gc', 'wii', 'ps2', 'switch'].contains(console) ||
          !RegExp(r'^[a-f0-9]{64}$').hasMatch(digest) ||
          size is! int ||
          size <= 0 ||
          size > maxArchiveBytes) {
        throw const FormatException('Invalid bundled skin metadata');
      }
      final previews = raw['previewAssets'];
      if (previews is! Map) {
        throw const FormatException('Missing bundled skin previews');
      }
      final previewAssets = <String, String>{};
      for (final orientation in const ['portrait', 'landscape']) {
        final value = previews[orientation];
        if (value is! String) {
          throw const FormatException('Missing bundled skin preview');
        }
        previewAssets[orientation] = asset(value, '.png');
      }
      result.add(
        BundledControllerSkin(
          id: id,
          name: string('name'),
          console: console,
          archiveAsset: asset(string('archiveAsset'), '.manicskin'),
          sha256: digest,
          size: size,
          previewAssets: Map.unmodifiable(previewAssets),
          author: string('author'),
          license: string('license'),
        ),
      );
    }
    return List.unmodifiable(result);
  }
}
