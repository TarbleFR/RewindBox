import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';

/// One section of a GodMode9 essential backup, read and checked.
class Libretro3dsExefsSection {
  const Libretro3dsExefsSection({
    required this.name,
    required this.start,
    required this.bytes,
    required this.hashed,
    this.problem,
  });

  /// Section name as the ExeFS header spells it (`secinfo`, `otp`…), raw.
  final String name;

  /// Offset of the section's first byte in the file.
  final int start;
  final Uint8List bytes;

  /// The header records a SHA-256 for this section and it matches.
  final bool hashed;

  /// Raw diagnostic when the recorded SHA-256 does not match.
  final String? problem;

  int get size => bytes.length;

  /// Only zero bytes: GodMode9 left the section unfilled.
  bool get blank => bytes.every((byte) => byte == 0);
}

/// Result of [Libretro3dsEssentialExefs.parse]: the sections, or why the
/// file is not a readable essential backup.
class Libretro3dsEssentialExefsContent {
  const Libretro3dsEssentialExefsContent.sections(this.sections)
    : problem = null;
  const Libretro3dsEssentialExefsContent.refused(this.problem)
    : sections = const [];

  final List<Libretro3dsExefsSection> sections;

  /// Raw diagnostic of a refused file.
  final String? problem;
}

/// `essential.exefs`, the essential backup GodMode9 writes with each NAND
/// backup: an ExeFS container (`BuildEssentialBackup`,
/// `arm9/source/utils/nandutil.c`) holding the NAND header, SecureInfo,
/// movable.sed, LocalFriendCodeSeed, the NAND CID, the OTP and the two
/// HWCAL files of one console. The header lists ten entries (name, offset
/// after the 0x200-byte header, size) and the SHA-256 of entry `i` at
/// `0x200 - (i + 1) * 0x20`. GodMode9 leaves the OTP and HWCAL entries
/// listed but unfilled and unhashed when it cannot read them (a locked
/// console, missing HWCAL files).
abstract final class Libretro3dsEssentialExefs {
  static const String fileName = 'essential.exefs';
  static const int headerSize = 0x200;

  /// GodMode9 writes 0x2200 bytes; anything far larger is not one.
  static const int maxBytes = 64 << 10;

  /// Sections the 3DS core reads, by section name, with the lower-case
  /// name of the console file each one holds.
  static const Map<String, String> consoleFiles = {
    'secinfo': 'secureinfo_a',
    'frndseed': 'localfriendcodeseed_b',
    'movable': 'movable.sed',
    'otp': 'otp.bin',
  };

  /// Sections GodMode9 writes that the core never reads.
  static const Set<String> unusedSections = {
    'nand_hdr',
    'nand_cid',
    'hwcal0',
    'hwcal1',
  };

  static const int _entryCount = 10;
  static const int _entrySize = 0x10;
  static const int _hashSize = 0x20;

  /// GodMode9's `ESSENTIAL_MAGIC`: the first entry is `nand_hdr`, offset 0,
  /// size 0x200.
  static const List<int> _magic = [
    0x6E, 0x61, 0x6E, 0x64, 0x5F, 0x68, 0x64, 0x72, // nand_hdr
    0x00, 0x00, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00,
  ];

  static Libretro3dsEssentialExefsContent parse(Uint8List bytes) {
    if (bytes.length < headerSize) {
      return Libretro3dsEssentialExefsContent.refused(
        '${bytes.length} bytes, an ExeFS header needs 0x200',
      );
    }
    if (bytes.length > maxBytes) {
      return Libretro3dsEssentialExefsContent.refused(
        '${bytes.length} bytes, more than an essential backup',
      );
    }
    for (var index = 0; index < _magic.length; index++) {
      if (bytes[index] != _magic[index]) {
        return const Libretro3dsEssentialExefsContent.refused(
          'no nand_hdr entry: not a GodMode9 essential backup',
        );
      }
    }
    final view = ByteData.sublistView(bytes);
    final sections = <Libretro3dsExefsSection>[];
    final names = <String>{};
    for (var entry = 0; entry < _entryCount; entry++) {
      final at = entry * _entrySize;
      if (bytes[at] == 0) continue;
      final nameBytes = <int>[];
      for (var index = 0; index < 8 && bytes[at + index] != 0; index++) {
        final byte = bytes[at + index];
        if (byte < 0x21 || byte > 0x7E) {
          return Libretro3dsEssentialExefsContent.refused(
            'entry $entry: name byte 0x${byte.toRadixString(16)}',
          );
        }
        nameBytes.add(byte);
      }
      final name = ascii.decode(nameBytes);
      if (!names.add(name)) {
        return Libretro3dsEssentialExefsContent.refused(
          'entry $entry: second $name section',
        );
      }
      final offset = view.getUint32(at + 8, Endian.little);
      final size = view.getUint32(at + 12, Endian.little);
      final start = headerSize + offset;
      if (start + size > bytes.length) {
        return Libretro3dsEssentialExefsContent.refused(
          '$name: 0x${size.toRadixString(16)} bytes at '
          '0x${start.toRadixString(16)}, past the end of the file',
        );
      }
      final content = Uint8List.sublistView(bytes, start, start + size);
      final hashAt = headerSize - (entry + 1) * _hashSize;
      final recorded = Uint8List.sublistView(bytes, hashAt, hashAt + _hashSize);
      final unhashed = recorded.every((byte) => byte == 0);
      String? problem;
      if (!unhashed && !_same(recorded, sha256.convert(content).bytes)) {
        problem = '$name: SHA-256 does not match the header';
      }
      sections.add(
        Libretro3dsExefsSection(
          name: name,
          start: start,
          bytes: content,
          hashed: !unhashed && problem == null,
          problem: problem,
        ),
      );
    }
    return Libretro3dsEssentialExefsContent.sections(
      List.unmodifiable(sections),
    );
  }

  static bool _same(List<int> a, List<int> b) {
    if (a.length != b.length) return false;
    for (var index = 0; index < a.length; index++) {
      if (a[index] != b[index]) return false;
    }
    return true;
  }
}

/// NCCH headers as the 3DS core checks them (azahar
/// `NCCHContainer::LoadHeader`): an `NCCH` magic at 0x100, and content the
/// core reads only when the `NoCrypto` bit (0x04) of flags[7] (0x18F) is
/// set — any encrypted NCCH is refused with `ErrorEncrypted`, whatever
/// keys are installed. An NCSD (`.3ds`, `.cci`) is opened at partition 0.
abstract final class Libretro3dsNcch {
  static const int magicOffset = 0x100;
  static const int flagsOffset = 0x18F;
  static const int noCryptoFlag = 0x04;
  static const int _mediaUnit = 0x200;

  static bool _magic(Uint8List header, int offset, String magic) {
    if (header.length < offset + 4) return false;
    for (var index = 0; index < 4; index++) {
      if (header[offset + index] != magic.codeUnitAt(index)) return false;
    }
    return true;
  }

  static bool isNcch(Uint8List header) => _magic(header, magicOffset, 'NCCH');

  static bool isNcsd(Uint8List header) => _magic(header, magicOffset, 'NCSD');

  /// An NCCH header (at least 0x190 bytes) the core refuses as encrypted.
  static bool isEncrypted(Uint8List header) =>
      isNcch(header) &&
      header.length > flagsOffset &&
      (header[flagsOffset] & noCryptoFlag) == 0;

  /// Raw diagnostic when the game at [path] is an NCSD or NCCH the core
  /// would refuse as encrypted; null otherwise (decrypted, another format
  /// — 3DSX, ELF, Z3DS — or unreadable: the core decides).
  static Future<String?> encryptedGameDetail(String path) async {
    RandomAccessFile? file;
    try {
      file = await File(path).open();
      var header = await file.read(_mediaUnit);
      var where = 'NCCH';
      if (isNcsd(header)) {
        if (header.length < 0x128) return null;
        final partition = ByteData.sublistView(
          header,
        ).getUint32(0x120, Endian.little);
        final offset = partition * _mediaUnit;
        if (offset == 0 || offset + _mediaUnit > await file.length()) {
          return null;
        }
        await file.setPosition(offset);
        header = await file.read(_mediaUnit);
        where = 'NCSD partition 0 NCCH at 0x${offset.toRadixString(16)}';
      }
      if (!isEncrypted(header)) return null;
      return '$where: flags[7] 0x'
          '${header[flagsOffset].toRadixString(16).padLeft(2, '0')}, '
          'no NoCrypto bit (encrypted content)';
    } catch (_) {
      return null;
    } finally {
      await file?.close();
    }
  }
}
