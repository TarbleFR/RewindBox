import 'dart:convert';
import 'dart:io';
import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as p;

class MelonxTransferCancelled implements Exception {}

class MelonxTransferControl {
  bool cancelled = false;
  void check() {
    if (cancelled) throw MelonxTransferCancelled();
  }
}

class MelonxTransferItem {
  const MelonxTransferItem(
    this.source,
    this.relative,
    this.bytes,
    this.conflict, {
    this.merge = false,
  });
  final FileSystemEntity source;
  final String relative;
  final int bytes;
  final bool conflict;
  final bool merge;
}

class _DigestSink implements Sink<Digest> {
  Digest? digest;
  @override
  void add(Digest value) {
    digest = value;
  }

  @override
  void close() {}
}

/// Copies to staging, verifies bytes, journals directory swaps and retains
/// recovery copies. A source folder or archive is never modified or removed.
abstract final class MelonxFileTransaction {
  static Future<void> _safeAncestors(Directory root, String target) async {
    var current = root.path;
    if (await FileSystemEntity.type(current, followLinks: false) ==
        FileSystemEntityType.link)
      throw const FormatException('unsafePath');
    for (final part in p.split(p.relative(target, from: root.path))) {
      current = p.join(current, part);
      if (await FileSystemEntity.type(current, followLinks: false) ==
          FileSystemEntityType.link)
        throw const FormatException('unsafePath');
    }
  }

  static String targetPath(Directory root, String relative) {
    final target = p.normalize(p.join(root.path, relative));
    if (p.isAbsolute(relative) ||
        !p.isWithin(root.path, target) ||
        p.split(relative).any((s) => s == '..' || s.startsWith('.rewindbox'))) {
      throw const FormatException('unsafePath');
    }
    return target;
  }

  static Future<int> size(FileSystemEntity entity) async {
    if (entity is File) return entity.length();
    if (entity is! Directory) throw const FormatException('unsafePath');
    var bytes = 0;
    await for (final child in entity.list(followLinks: false)) {
      if (child is Link) throw const FormatException('unsafePath');
      bytes += await size(child);
    }
    return bytes;
  }

  static Future<void> _remove(String location) async {
    final type = await FileSystemEntity.type(location, followLinks: false);
    if (type == FileSystemEntityType.directory)
      await Directory(location).delete(recursive: true);
    else if (type != FileSystemEntityType.notFound)
      await File(location).delete();
  }

  static Future<void> _move(String from, String to) async {
    await Directory(p.dirname(to)).create(recursive: true);
    if (await FileSystemEntity.type(from, followLinks: false) ==
        FileSystemEntityType.directory) {
      await Directory(from).rename(to);
    } else {
      await File(from).rename(to);
    }
  }

  static Future<void> _journal(File journal, Map<String, dynamic> value) async {
    final temporary = File('${journal.path}.writing');
    await temporary.writeAsString(jsonEncode(value), flush: true);
    await temporary.rename(journal.path);
  }

  static Future<void> _cleanStages(Directory root) async {
    await for (final entry in root.list(followLinks: false)) {
      if (RegExp(
        r'^\.rewindbox-stage-[0-9]+$',
      ).hasMatch(p.basename(entry.path)))
        await _remove(entry.path);
    }
    await _remove(p.join(root.path, '.rewindbox-transfer.json.writing'));
  }

  static Future<void> recover(Directory root) async {
    final journal = File(p.join(root.path, '.rewindbox-transfer.json'));
    await _safeAncestors(root, journal.path);
    if (!await journal.exists()) {
      await _cleanStages(root);
      return;
    }
    final record = jsonDecode(await journal.readAsString()) as Map;
    final id = record['id'] as String;
    if (!RegExp(r'^\d+$').hasMatch(id))
      throw const FormatException('unsafePath');
    if (record['committed'] != true) {
      for (final item in (record['started'] as List).reversed) {
        final relative = item['relative'] as String;
        final target = targetPath(root, relative);
        await _safeAncestors(root, target);
        final backup = targetPath(
          root,
          p.join('TransferBackups', id, relative),
        );
        await _safeAncestors(root, backup);
        if (await FileSystemEntity.type(backup) !=
            FileSystemEntityType.notFound) {
          await _remove(target);
          await _move(backup, target);
        } else if (item['existed'] != true) {
          await _remove(target);
        }
      }
    }
    await journal.delete();
    await _remove(p.join(root.path, '.rewindbox-stage-$id'));
    await _cleanStages(root);
  }

  static Future<String> apply(
    Directory root,
    List<MelonxTransferItem> items,
    MelonxTransferControl control, {
    void Function(int, int)? progress,
    Future<void> Function(Directory)? validateStaged,
    Future<void> Function()? validateInstalled,
  }) async {
    await recover(root);
    final id = DateTime.now().microsecondsSinceEpoch.toString();
    final stage = Directory(p.join(root.path, '.rewindbox-stage-$id'));
    final journal = File(p.join(root.path, '.rewindbox-transfer.json'));
    await _safeAncestors(root, journal.path);
    await _safeAncestors(root, '${journal.path}.writing');
    await _safeAncestors(root, stage.path);
    for (final item in items) {
      await _safeAncestors(
        root,
        targetPath(root, p.join('TransferBackups', id, item.relative)),
      );
    }
    final record = <String, dynamic>{
      'id': id,
      'committed': false,
      'started': <Map<String, dynamic>>[],
    };
    final targets = items.map((e) => targetPath(root, e.relative)).toList();
    for (final target in targets) {
      await _safeAncestors(root, target);
    }
    for (var i = 0; i < targets.length; i++) {
      for (var j = i + 1; j < targets.length; j++) {
        if (p.equals(targets[i], targets[j]) ||
            p.isWithin(targets[i], targets[j]) ||
            p.isWithin(targets[j], targets[i])) {
          throw const FormatException('overlappingTargets');
        }
      }
    }
    final total = items.fold<int>(0, (sum, item) => sum + item.bytes);
    var done = 0;
    try {
      await stage.create(recursive: true);
      for (final item in items) {
        control.check();
        if (item.merge &&
            await Directory(targetPath(root, item.relative)).exists()) {
          await copy(
            Directory(targetPath(root, item.relative)),
            targetPath(stage, item.relative),
            control,
          );
        }
        await copy(
          item.source,
          targetPath(stage, item.relative),
          control,
          progress: (n) {
            done += n;
            progress?.call(done, total);
          },
        );
      }
      await validateStaged?.call(stage);
      control.check();
      await _journal(journal, record);
      for (final item in items) {
        control.check();
        final target = targetPath(root, item.relative);
        await _safeAncestors(root, target);
        final existed =
            await FileSystemEntity.type(target) !=
            FileSystemEntityType.notFound;
        if (existed && !item.conflict)
          throw const FileSystemException('newConflict');
        (record['started'] as List).add({
          'relative': item.relative,
          'existed': existed,
        });
        await _journal(journal, record);
        if (existed)
          await _move(
            target,
            targetPath(root, p.join('TransferBackups', id, item.relative)),
          );
        await _move(targetPath(stage, item.relative), target);
      }
      await validateInstalled?.call();
      control.check();
      record['committed'] = true;
      await _journal(journal, record);
      await recover(root);
      return p.join(root.path, 'TransferBackups', id);
    } catch (_) {
      if (await journal.exists()) await recover(root);
      if (await stage.exists()) await stage.delete(recursive: true);
      rethrow;
    }
  }

  static Future<void> copy(
    FileSystemEntity source,
    String destination,
    MelonxTransferControl control, {
    void Function(int)? progress,
  }) async {
    control.check();
    if (source is Directory) {
      await Directory(destination).create(recursive: true);
      await for (final entry in source.list(followLinks: false)) {
        if (p.basename(entry.path) == '__MACOSX' ||
            p.basename(entry.path).startsWith('._'))
          continue;
        await copy(
          entry,
          p.join(destination, p.basename(entry.path)),
          control,
          progress: progress,
        );
      }
      return;
    }
    if (source is! File ||
        await FileSystemEntity.type(source.path, followLinks: false) !=
            FileSystemEntityType.file) {
      throw const FormatException('unsafePath');
    }
    await Directory(p.dirname(destination)).create(recursive: true);
    final stat = await source.stat();
    final input = await source.open();
    final output = await File(destination).open(mode: FileMode.write);
    final sink = _DigestSink();
    final hash = sha256.startChunkedConversion(sink);
    var bytes = 0;
    try {
      while (true) {
        control.check();
        final chunk = await input.read(1024 * 1024);
        if (chunk.isEmpty) break;
        await output.writeFrom(chunk);
        hash.add(chunk);
        bytes += chunk.length;
        progress?.call(chunk.length);
      }
      await output.flush();
    } finally {
      hash.close();
      await input.close();
      await output.close();
    }
    control.check();
    final after = await source.stat();
    if (bytes != stat.size ||
        after.size != stat.size ||
        after.modified != stat.modified ||
        (await sha256.bind(File(destination).openRead()).first) !=
            sink.digest) {
      throw const FileSystemException('incompleteTransfer');
    }
  }
}
