import 'dart:io';
import 'dart:typed_data';

import 'package:path/path.dart' as path;

/// What a picked Xbox 360 file is, for the embedded XeniOS engine
/// (docs/xenios-playlist.md § Formats).
///
/// Only [discImage] and [zarArchive] are games RewindBox imports as one
/// file. A loose `.xex` is a game executable that needs its whole title
/// folder beside it, and GOD/STFS packages are a header plus a `.data`
/// folder: neither can be imported from a single picked file, so they are
/// refused instead of being half-imported. Profiles and touch layouts are
/// XeniOS user data, never games.
enum XeniaContentKind {
  /// XGD/XISO disc image (`.iso`), read by Xenia's DiscImageDevice.
  discImage,

  /// ZArchive (`.zar`), read by Xenia's DiscZarchiveDevice.
  zarArchive,

  /// Loose title executable (`.xex`): playable only inside its folder.
  looseExecutable,

  /// XeniOS profile (`.xeniosprofile`): account data, not a game.
  profile,

  /// XeniOS touch layout (`.toml`): control layout, not a game.
  touchLayout,

  unsupported,
}

/// Identity read from an Xbox 360 disc image.
class XeniaDiscIdentity {
  const XeniaDiscIdentity({
    required this.partitionOffset,
    this.titleId,
    this.mediaId,
    this.discNumber,
    this.discCount,
  });

  /// Byte offset of the game partition inside the image.
  final int partitionOffset;

  /// Title ID of `default.xex`, 8 upper-case hex digits (the name of the
  /// engine's per-game `config/<TITLEID>.config.toml`), null when the
  /// executable could not be read.
  final String? titleId;
  final String? mediaId;
  final int? discNumber;
  final int? discCount;
}

/// Why an image was refused; the key of a localized message.
enum XeniaContentError {
  /// No GDFX volume descriptor at any partition offset Xenia probes.
  notXboxImage,

  /// The volume descriptor or root directory points past the end of the
  /// file: an incomplete or truncated copy.
  truncated,

  /// The file cannot be read.
  unreadable,
}

class XeniaContentException implements Exception {
  const XeniaContentException(this.error, [this.detail]);
  final XeniaContentError error;
  final String? detail;

  @override
  String toString() =>
      'XeniaContentException(${error.name}${detail == null ? '' : ': $detail'})';
}

abstract final class XeniaContent {
  /// Extensions the Xbox 360 playlist scans and launches.
  static const Set<String> gameExtensions = <String>{'iso', 'zar', 'xex'};

  /// Extensions accepted by the single-file import.
  static const Set<String> importExtensions = <String>{'iso', 'zar'};

  /// Offered by the picker: games plus the extensions that are refused with
  /// a precise reason (so the user learns why rather than seeing nothing).
  static const Set<String> pickerExtensions = <String>{
    'iso',
    'zar',
    'xex',
    'xeniosprofile',
    'toml',
  };

  static XeniaContentKind kindForName(String name) {
    final extension = path.extension(name).replaceFirst('.', '').toLowerCase();
    return switch (extension) {
      'iso' => XeniaContentKind.discImage,
      'zar' => XeniaContentKind.zarArchive,
      'xex' => XeniaContentKind.looseExecutable,
      'xeniosprofile' => XeniaContentKind.profile,
      'toml' => XeniaContentKind.touchLayout,
      _ => XeniaContentKind.unsupported,
    };
  }

  // Constants of xenia/vfs/gdfx_util.h at XeniOS cf7c7ee45.
  static const int sectorSize = 2048;
  static const String _gdfxMagic = 'MICROSOFT*XBOX*MEDIA';

  /// `kGdfxLikelyOffsets`, in the engine's probing order.
  static const List<int> partitionOffsets = <int>[
    0x00000000,
    0x0000FB20,
    0x00020600,
    0x02080000,
    0x0FD90000,
  ];
  static const int _paddingOffset = 0xFFFF;
  static const int _directoryAttribute = 0x10;
  static const int _maxRootSize = 32 * 1024 * 1024;

  // xenia/kernel/util/xex2_info.h.
  static const int _xex2Magic = 0x58455832; // 'XEX2'
  static const int _executionInfoKey = 0x00040006;
  static const int _maxXexHeaderBytes = 16 * 1024 * 1024;

  /// Reads the GDFX partition of [file] and, when found, the title identity
  /// of its `default.xex`. Throws [XeniaContentException] for a file that is
  /// not an Xbox disc image or is truncated. Reads a few KiB with bounded
  /// buffers; never maps or loads the image.
  static Future<XeniaDiscIdentity> inspectDiscImage(File file) async {
    RandomAccessFile? handle;
    try {
      handle = await file.open();
      final length = await handle.length();
      for (final offset in partitionOffsets) {
        final descriptor = offset + 32 * sectorSize;
        if (descriptor + 28 > length) continue;
        final header = await _read(handle, descriptor, 28);
        if (header.length < 28 ||
            String.fromCharCodes(header.sublist(0, 20)) != _gdfxMagic) {
          continue;
        }
        final view = ByteData.sublistView(header);
        final rootSector = view.getUint32(20, Endian.little);
        final rootSize = view.getUint32(24, Endian.little);
        if (rootSize < 13 || rootSize > _maxRootSize) continue;
        final rootStart = offset + rootSector * sectorSize;
        if (rootStart + rootSize > length) {
          throw const XeniaContentException(
            XeniaContentError.truncated,
            'root directory beyond end of file',
          );
        }
        final root = await _read(handle, rootStart, rootSize);
        final xex = _findEntry(root, 0, 'default.xex', 0);
        if (xex == null) {
          return XeniaDiscIdentity(partitionOffset: offset);
        }
        final xexStart = offset + xex.sector * sectorSize;
        if (xexStart + xex.length > length) {
          throw const XeniaContentException(
            XeniaContentError.truncated,
            'default.xex beyond end of file',
          );
        }
        final info = await _readExecutionInfo(handle, xexStart, xex.length);
        return XeniaDiscIdentity(
          partitionOffset: offset,
          titleId: info?.titleId,
          mediaId: info?.mediaId,
          discNumber: info?.discNumber,
          discCount: info?.discCount,
        );
      }
      throw const XeniaContentException(XeniaContentError.notXboxImage);
    } on XeniaContentException {
      rethrow;
    } on FileSystemException catch (error) {
      throw XeniaContentException(XeniaContentError.unreadable, error.message);
    } finally {
      await handle?.close();
    }
  }

  /// Title identity of a standalone XEX2 file (a loose `default.xex`).
  static Future<XeniaDiscIdentity?> inspectExecutable(File file) async {
    RandomAccessFile? handle;
    try {
      handle = await file.open();
      final info = await _readExecutionInfo(handle, 0, await handle.length());
      if (info == null) return null;
      return XeniaDiscIdentity(
        partitionOffset: 0,
        titleId: info.titleId,
        mediaId: info.mediaId,
        discNumber: info.discNumber,
        discCount: info.discCount,
      );
    } on FileSystemException {
      return null;
    } finally {
      await handle?.close();
    }
  }

  static Future<Uint8List> _read(
    RandomAccessFile handle,
    int offset,
    int count,
  ) async {
    await handle.setPosition(offset);
    return handle.read(count);
  }

  /// GdfxFindFileInDirectory: a binary tree of 4-byte-aligned entries
  /// (left u16, right u16, sector u32, length u32, attributes u8, name
  /// length u8, name), little-endian, with 0xFFFF padding entries that
  /// stand for the entry starting the next sector.
  static _GdfxEntry? _findEntry(
    Uint8List directory,
    int ordinal,
    String name,
    int depth,
  ) {
    if (depth > 4096) return null;
    final offset = ordinal * 4;
    if (offset + 14 > directory.length) return null;
    final view = ByteData.sublistView(directory);
    final left = view.getUint16(offset, Endian.little);
    final right = view.getUint16(offset + 2, Endian.little);
    if (left == _paddingOffset) {
      if (offset % sectorSize == 0) return null;
      final padded = (offset ~/ sectorSize + 1) * sectorSize ~/ 4;
      return _findEntry(directory, padded, name, depth + 1);
    }
    final sector = view.getUint32(offset + 4, Endian.little);
    final length = view.getUint32(offset + 8, Endian.little);
    final attributes = directory[offset + 12];
    final nameLength = directory[offset + 13];
    if (offset + 14 + nameLength > directory.length) return null;
    final entryName = String.fromCharCodes(
      directory.sublist(offset + 14, offset + 14 + nameLength),
    );
    if ((attributes & _directoryAttribute) == 0 &&
        entryName.toLowerCase() == name) {
      return _GdfxEntry(sector, length);
    }
    if (left != 0) {
      final found = _findEntry(directory, left, name, depth + 1);
      if (found != null) return found;
    }
    if (right != 0) {
      return _findEntry(directory, right, name, depth + 1);
    }
    return null;
  }

  static Future<_ExecutionInfo?> _readExecutionInfo(
    RandomAccessFile handle,
    int start,
    int available,
  ) async {
    if (available < 0x18) return null;
    final head = await _read(handle, start, 0x18);
    if (head.length < 0x18) return null;
    final view = ByteData.sublistView(head);
    if (view.getUint32(0) != _xex2Magic) return null;
    final headerSize = view.getUint32(8);
    final count = view.getUint32(0x14);
    if (headerSize < 0x18 ||
        headerSize > available ||
        headerSize > _maxXexHeaderBytes ||
        0x18 + count * 8 > headerSize) {
      return null;
    }
    final header = await _read(handle, start, headerSize);
    if (header.length < headerSize) return null;
    final data = ByteData.sublistView(header);
    for (var index = 0; index < count; index++) {
      final key = data.getUint32(0x18 + index * 8);
      if (key != _executionInfoKey) continue;
      final at = data.getUint32(0x18 + index * 8 + 4);
      if (at + 0x18 > headerSize) return null;
      String hex(int value) =>
          value.toRadixString(16).toUpperCase().padLeft(8, '0');
      return _ExecutionInfo(
        mediaId: hex(data.getUint32(at)),
        titleId: hex(data.getUint32(at + 0xC)),
        discNumber: header[at + 0x12],
        discCount: header[at + 0x13],
      );
    }
    return null;
  }

  /// Normalized title ID (8 upper-case hex digits) or null.
  static String? normalizeTitleId(String? value) {
    final trimmed = value?.trim().toUpperCase();
    if (trimmed == null || !RegExp(r'^[0-9A-F]{8}$').hasMatch(trimmed)) {
      return null;
    }
    if (trimmed == '00000000' || trimmed == 'FFFFFFFF') return null;
    return trimmed;
  }
}

class _GdfxEntry {
  const _GdfxEntry(this.sector, this.length);
  final int sector;
  final int length;
}

class _ExecutionInfo {
  const _ExecutionInfo({
    required this.mediaId,
    required this.titleId,
    required this.discNumber,
    required this.discCount,
  });
  final String mediaId;
  final String titleId;
  final int discNumber;
  final int discCount;
}
