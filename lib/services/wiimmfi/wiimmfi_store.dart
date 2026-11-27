import 'dart:convert';
import 'dart:io';

import 'package:path/path.dart' as p;

import '../dolphin_system_files.dart';

class WiimmfiException implements Exception {
  const WiimmfiException(this.code);
  final String code;
  @override
  String toString() => code;
}

/// Only app-owned preferences and fingerprints. Never console credentials.
class WiimmfiStore {
  WiimmfiStore(this.directory);
  final Directory directory;
  File get _file => File(p.join(directory.path, 'settings.json'));

  Future<Map<String, dynamic>> load() async {
    if (!await _file.exists()) {
      return {'enabled': false, 'images': <String, dynamic>{}};
    }
    try {
      if (await _file.length() > 1024 * 1024) throw const FormatException();
      final decoded = jsonDecode(await _file.readAsString());
      if (decoded is! Map<String, dynamic> ||
          decoded['schema'] != 1 ||
          decoded['enabled'] is! bool ||
          decoded['images'] is! Map<String, dynamic>) {
        throw const FormatException();
      }
      return decoded;
    } on FormatException {
      // Fail closed, keep the original for recovery rather than overwriting it.
      throw const WiimmfiException('configurationInvalid');
    }
  }

  Future<void> save(Map<String, dynamic> settings) async {
    await directory.create(recursive: true);
    final incoming = File('${_file.path}.incoming');
    try {
      await incoming.writeAsString(
        jsonEncode({...settings, 'schema': 1}),
        flush: true,
      );
      await incoming.rename(_file.path);
    } finally {
      if (await incoming.exists()) await incoming.delete();
    }
  }

  Future<void> clear() async {
    // This directory holds configuration only. NAND, saves and games stay.
    if (await _file.exists()) await _file.delete();
  }
}

/// Merge only existing save-data directories after native extraction. The
/// user's current profiles win over the console backup; the old NAND is also
/// retained by replaceSnapshot in a separate backup.
Future<void> preserveWiiSaveData(Directory current, Directory stage) async {
  final titles = Directory(p.join(current.path, 'title'));
  final type = await FileSystemEntity.type(titles.path, followLinks: false);
  if (type == FileSystemEntityType.notFound) return;
  if (type != FileSystemEntityType.directory) {
    throw const WiimmfiException('unsafePath');
  }
  final hex = RegExp(r'^[0-9a-fA-F]{8}$');
  await for (final high in titles.list(followLinks: false)) {
    if (!hex.hasMatch(p.basename(high.path))) continue;
    if (high is! Directory) throw const WiimmfiException('unsafePath');
    await for (final low in high.list(followLinks: false)) {
      if (!hex.hasMatch(p.basename(low.path))) continue;
      if (low is! Directory) throw const WiimmfiException('unsafePath');
      final data = Directory(p.join(low.path, 'data'));
      if (!await data.exists()) continue;
      final destination = Directory(
        p.join(
          stage.path,
          'title',
          p.basename(high.path),
          p.basename(low.path),
          'data',
        ),
      );
      if (await destination.exists()) await destination.delete(recursive: true);
      await DolphinSystemFiles.copyTree(data, destination.path);
    }
  }
}
