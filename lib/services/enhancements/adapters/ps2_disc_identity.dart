import 'dart:io';
import 'dart:typed_data';

/// Serial and boot ELF CRC of an uncompressed PS2 disc image.
///
/// Same algorithm as NeoTextureIdentity::PS2 and PCSX2: SYSTEM.CNF names the
/// boot ELF (`BOOT2 = cdrom0:\SLUS_210.50;1` gives `SLUS-21050`) and the CRC
/// is the XOR of all its 32-bit little-endian words. Reads ISO (2048-byte
/// sectors) and raw BIN (2352-byte MODE1/MODE2 sectors); compressed images
/// (CHD, CSO, ZSO, GZ) return [Ps2DiscIdentity.unsupportedFormat].
class Ps2DiscIdentity {
  const Ps2DiscIdentity(this.serial, this.crc, [this.problem]);

  final String? serial;
  final String? crc;
  final String? problem;

  static const unsupportedFormat = 'unsupportedFormat';
  static const _maxElf = 64 << 20;

  bool get known => serial != null && crc != null;

  static Future<Ps2DiscIdentity> read(String imagePath) async {
    final extension = imagePath.split('.').last.toLowerCase();
    if (extension != 'iso' && extension != 'bin' && extension != 'img') {
      return const Ps2DiscIdentity(null, null, unsupportedFormat);
    }
    RandomAccessFile? file;
    try {
      file = await File(imagePath).open();
      final sectors = await _Sectors.detect(file);
      if (sectors == null) return const Ps2DiscIdentity(null, null, unsupportedFormat);
      final cnf = await sectors.find(['SYSTEM.CNF']);
      if (cnf == null || cnf.directory || cnf.size > 4096) {
        return const Ps2DiscIdentity(null, null, 'noSystemCnf');
      }
      final text = String.fromCharCodes(await sectors.readFile(cnf));
      final boot = RegExp(r'BOOT2\s*=\s*[^:\r\n]*:([^\r\n]+)').firstMatch(text);
      if (boot == null) return const Ps2DiscIdentity(null, null, 'noBoot2');
      final parts = boot
          .group(1)!
          .trim()
          .split(RegExp(r'[\\/]'))
          .where((part) => part.trim().isNotEmpty)
          .map((part) => part.trim())
          .toList();
      if (parts.isEmpty) return const Ps2DiscIdentity(null, null, 'noBoot2');
      final serial = serialFromBootName(parts.last);
      if (serial == null) return const Ps2DiscIdentity(null, null, 'noSerial');
      final elf = await sectors.find(parts);
      if (elf == null || elf.directory || elf.size > _maxElf) {
        return Ps2DiscIdentity(serial, null, 'noElf');
      }
      return Ps2DiscIdentity(serial, await sectors.crc(elf), null);
    } on FileSystemException {
      return const Ps2DiscIdentity(null, null, 'unreadable');
    } finally {
      await file?.close();
    }
  }

  /// `SLUS_210.50;1` -> `SLUS-21050`.
  static String? serialFromBootName(String name) {
    var base = name.toUpperCase();
    final semicolon = base.indexOf(';');
    if (semicolon >= 0) base = base.substring(0, semicolon);
    final letters = StringBuffer();
    final digits = StringBuffer();
    for (final rune in base.runes) {
      final c = String.fromCharCode(rune);
      if (RegExp('[A-Z]').hasMatch(c) && digits.isEmpty) {
        letters.write(c);
      } else if (RegExp('[0-9]').hasMatch(c)) {
        digits.write(c);
      }
    }
    if (letters.length != 4 || digits.length != 5) return null;
    return '$letters-$digits';
  }
}

class _IsoFile {
  const _IsoFile(this.extent, this.size, this.directory);
  final int extent;
  final int size;
  final bool directory;
}

class _Sectors {
  _Sectors(this._file, this._stride, this._offset);

  final RandomAccessFile _file;
  final int _stride;
  final int _offset;

  static Future<_Sectors?> detect(RandomAccessFile file) async {
    // ISO, MODE1 raw (16-byte header) and MODE2/XA raw (24-byte header).
    for (final layout in const [(2048, 0), (2352, 16), (2352, 24)]) {
      final sectors = _Sectors(file, layout.$1, layout.$2);
      final pvd = await sectors.read(16, 1);
      if (pvd != null &&
          pvd[0] == 1 &&
          String.fromCharCodes(pvd.sublist(1, 6)) == 'CD001') {
        return sectors;
      }
    }
    return null;
  }

  Future<Uint8List?> read(int sector, int count) async {
    if (_stride == 2048) {
      // Contiguous user data: one read for the whole range.
      await _file.setPosition(sector * 2048);
      final data = await _file.read(count * 2048);
      return data.length == count * 2048 ? data : null;
    }
    final out = Uint8List(count * 2048);
    for (var i = 0; i < count; i++) {
      await _file.setPosition((sector + i) * _stride + _offset);
      final chunk = await _file.read(2048);
      if (chunk.length != 2048) return null;
      out.setRange(i * 2048, i * 2048 + 2048, chunk);
    }
    return out;
  }

  static int _le32(Uint8List data, int at) =>
      ByteData.sublistView(data, at, at + 4).getUint32(0, Endian.little);

  Future<_IsoFile?> find(List<String> components) async {
    final pvd = await read(16, 1);
    if (pvd == null) return null;
    var current = _IsoFile(_le32(pvd, 156 + 2), _le32(pvd, 156 + 10), true);
    for (var wanted in components) {
      final semicolon = wanted.indexOf(';');
      if (semicolon >= 0) wanted = wanted.substring(0, semicolon);
      wanted = wanted.toUpperCase();
      if (!current.directory || current.size > (4 << 20)) return null;
      final count = (current.size + 2047) ~/ 2048;
      final directory = await read(current.extent, count);
      if (directory == null) return null;
      _IsoFile? next;
      var at = 0;
      while (at < current.size) {
        final length = directory[at];
        if (length == 0) {
          at = (at ~/ 2048 + 1) * 2048;
          continue;
        }
        if (at + length > directory.length || length < 34) break;
        final nameLength = directory[at + 32];
        if (33 + nameLength > length) break;
        var name = String.fromCharCodes(directory.sublist(at + 33, at + 33 + nameLength));
        final mark = name.indexOf(';');
        if (mark >= 0) name = name.substring(0, mark);
        if (name.endsWith('.')) name = name.substring(0, name.length - 1);
        if (name.toUpperCase() == wanted) {
          next = _IsoFile(
            _le32(directory, at + 2),
            _le32(directory, at + 10),
            (directory[at + 25] & 2) != 0,
          );
          break;
        }
        at += length;
      }
      if (next == null) return null;
      current = next;
    }
    return current;
  }

  Future<Uint8List> readFile(_IsoFile file) async {
    final data = await read(file.extent, (file.size + 2047) ~/ 2048);
    if (data == null) throw const FileSystemException('short read');
    return Uint8List.sublistView(data, 0, file.size);
  }

  Future<String?> crc(_IsoFile file) async {
    var crc = 0;
    final words = file.size ~/ 4;
    var done = 0;
    for (var sector = 0; done < words; sector += 64) {
      final remaining = file.size - sector * 2048;
      final count = ((remaining + 2047) ~/ 2048).clamp(1, 64);
      final chunk = await read(file.extent + sector, count);
      if (chunk == null) return null;
      final view = ByteData.sublistView(chunk);
      final chunkWords = (words - done).clamp(0, count * 512);
      for (var w = 0; w < chunkWords; w++) {
        crc ^= view.getUint32(w * 4, Endian.little);
      }
      done += chunkWords;
    }
    return crc.toRadixString(16).padLeft(8, '0').toUpperCase();
  }
}
