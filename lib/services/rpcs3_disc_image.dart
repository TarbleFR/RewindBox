import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as path;

import 'rpcs3_param_sfo.dart';

/// What a PS3 disc image says about itself: `PS3_GAME/PARAM.SFO` read from
/// its ISO 9660 file system.
class Rpcs3DiscIdentity {
  const Rpcs3DiscIdentity({
    required this.titleId,
    required this.title,
    required this.category,
  });

  final String titleId;
  final String title;
  final String category;
}

/// Reads a PS3 disc image where it is, without copying or mounting it
/// (Build 554). A disc image found in the library folder (`roms/ps3`) has no
/// title ID until RPCS3 installs it; these reads let the launcher tell
/// whether RPCS3 already holds that disc and which disc key goes with it.
///
/// ISO 9660 layout used here: 2048-byte sectors; volume descriptors from
/// sector 16 (type byte, then `CD001`; type 1 is the primary descriptor,
/// 255 ends the set); the root directory record at offset 156 of the
/// primary descriptor; each directory record holds its length (byte 0), the
/// extent sector (little-endian u32 at 2), the data length (little-endian
/// u32 at 10), the flags (byte 25, bit 1 for a directory), the name length
/// (byte 32) and the name (from 33, files end with `;1`). Records never
/// cross a sector: a zero length byte skips to the next sector.
abstract final class Rpcs3DiscImage {
  static const int sectorSize = 2048;

  /// Bytes compared by [sameImage] after the sizes match.
  static const int comparedPrefix = 1 << 20;

  static const int _firstDescriptor = 16;
  static const int _maxDescriptors = 32;
  static const int _maxDirectoryLength = 1 << 20;
  static const int _maxParamSfoLength = 1 << 16;

  /// The only disc image extension the PS3 system lists (assets/systems/ps3.json).
  static bool isDiscImagePath(String? romPath) =>
      romPath != null && path.extension(romPath).toLowerCase() == '.iso';

  /// `PS3_GAME/PARAM.SFO` of [isoPath], or null when the image has no
  /// readable ISO 9660 tree, no such file, or a descriptor without a title
  /// ID (an encrypted region reads as noise).
  static Future<Rpcs3DiscIdentity?> readIdentity(String isoPath) async {
    RandomAccessFile? file;
    try {
      file = await File(isoPath).open();
      final opened = file;
      final length = await opened.length();
      Future<Uint8List> read(int offset, int count) async {
        if (offset < 0 || count < 0 || offset + count > length) {
          throw const FormatException('read outside the image');
        }
        await opened.setPosition(offset);
        final bytes = await opened.read(count);
        if (bytes.length != count) {
          throw const FormatException('short read');
        }
        return bytes;
      }

      Uint8List? primary;
      for (var index = 0; index < _maxDescriptors; index++) {
        final descriptor = await read(
          (_firstDescriptor + index) * sectorSize,
          sectorSize,
        );
        if (descriptor[1] != 0x43 ||
            descriptor[2] != 0x44 ||
            descriptor[3] != 0x30 ||
            descriptor[4] != 0x30 ||
            descriptor[5] != 0x31) {
          return null;
        }
        if (descriptor[0] == 1) {
          primary = descriptor;
          break;
        }
        if (descriptor[0] == 255) return null;
      }
      if (primary == null) return null;

      final root = _DirectoryRecord.parse(primary, 156);
      if (root == null || !root.isDirectory) return null;
      final game = await _child(read, root, 'PS3_GAME', directory: true);
      if (game == null) return null;
      final sfo = await _child(read, game, 'PARAM.SFO', directory: false);
      if (sfo == null || sfo.length <= 0 || sfo.length > _maxParamSfoLength) {
        return null;
      }
      final descriptor = Rpcs3ParamSfo.tryParse(
        await read(sfo.sector * sectorSize, sfo.length),
      );
      if (descriptor == null) return null;
      String value(String key) =>
          (descriptor.strings[key] ?? '').replaceAll('\u0000', '').trim();
      final titleId = value('TITLE_ID').toUpperCase();
      if (!RegExp(r'^[A-Z0-9]{9,16}$').hasMatch(titleId)) return null;
      final title = value('TITLE');
      return Rpcs3DiscIdentity(
        titleId: titleId,
        title: title.isEmpty ? titleId : title,
        category: value('CATEGORY').toUpperCase(),
      );
    } on FileSystemException {
      return null;
    } on FormatException {
      return null;
    } on RangeError {
      return null;
    } finally {
      await file?.close();
    }
  }

  /// The disc key beside [isoPath]: the same name with `.dkey` or `.key`,
  /// in any case; `.dkey` first when both exist. RPCS3 needs it for an
  /// encrypted (Redump) image.
  static Future<String?> findDiscKey(String isoPath) async {
    final stem = path.basenameWithoutExtension(isoPath).toLowerCase();
    final found = <String, String>{};
    try {
      await for (final entity in Directory(
        path.dirname(isoPath),
      ).list(followLinks: false)) {
        if (entity is! File) continue;
        final name = path.basename(entity.path);
        final extension = path.extension(name).toLowerCase();
        if ((extension == '.dkey' || extension == '.key') &&
            path.basenameWithoutExtension(name).toLowerCase() == stem) {
          found.putIfAbsent(extension, () => entity.path);
        }
      }
    } on FileSystemException {
      // A file picked in place may be readable while its folder is not.
      for (final extension in const ['.dkey', '.DKEY', '.key', '.KEY']) {
        final candidate = File(path.setExtension(isoPath, extension));
        if (await candidate.exists()) {
          found.putIfAbsent(extension.toLowerCase(), () => candidate.path);
        }
      }
    }
    return found['.dkey'] ?? found['.key'];
  }

  /// Whether [first] and [second] hold the same disc image: equal sizes and
  /// equal first [comparedPrefix] bytes (system area and volume
  /// descriptors). Used when the title ID cannot be read, so a disc RPCS3
  /// already installed is not copied a second time.
  static Future<bool> sameImage(String first, String second) async {
    RandomAccessFile? a;
    RandomAccessFile? b;
    try {
      final left = File(first);
      final right = File(second);
      final size = await left.length();
      if (size <= 0 || size != await right.length()) return false;
      a = await left.open();
      b = await right.open();
      final count = size < comparedPrefix ? size : comparedPrefix;
      final x = await a.read(count);
      final y = await b.read(count);
      if (x.length != count || y.length != count) return false;
      for (var index = 0; index < count; index++) {
        if (x[index] != y[index]) return false;
      }
      return true;
    } on FileSystemException {
      return false;
    } finally {
      await a?.close();
      await b?.close();
    }
  }

  static Future<_DirectoryRecord?> _child(
    Future<Uint8List> Function(int offset, int count) read,
    _DirectoryRecord parent,
    String name, {
    required bool directory,
  }) async {
    if (parent.length <= 0 || parent.length > _maxDirectoryLength) return null;
    final bytes = await read(parent.sector * sectorSize, parent.length);
    var offset = 0;
    while (offset < bytes.length) {
      final recordLength = bytes[offset];
      if (recordLength == 0) {
        offset = (offset ~/ sectorSize + 1) * sectorSize;
        continue;
      }
      if (recordLength < 34 || offset + recordLength > bytes.length) break;
      final record = _DirectoryRecord.parse(bytes, offset);
      if (record != null &&
          record.isDirectory == directory &&
          record.name == name) {
        return record;
      }
      offset += recordLength;
    }
    return null;
  }
}

class _DirectoryRecord {
  const _DirectoryRecord(this.sector, this.length, this.isDirectory, this.name);

  final int sector;
  final int length;
  final bool isDirectory;

  /// Upper case, without the `;1` version or a trailing dot.
  final String name;

  static _DirectoryRecord? parse(Uint8List bytes, int offset) {
    if (offset + 34 > bytes.length) return null;
    final recordLength = bytes[offset];
    final nameLength = bytes[offset + 32];
    if (recordLength < 34 || offset + 33 + nameLength > bytes.length) {
      return null;
    }
    final view = ByteData.sublistView(bytes);
    var name = String.fromCharCodes(
      bytes.sublist(offset + 33, offset + 33 + nameLength),
    ).toUpperCase();
    final version = name.indexOf(';');
    if (version >= 0) name = name.substring(0, version);
    if (name.endsWith('.')) name = name.substring(0, name.length - 1);
    return _DirectoryRecord(
      view.getUint32(offset + 2, Endian.little),
      view.getUint32(offset + 10, Endian.little),
      (bytes[offset + 25] & 0x02) != 0,
      name,
    );
  }
}
