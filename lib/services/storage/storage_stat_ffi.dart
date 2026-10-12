/// `lstat`/`statvfs` through `dart:ffi` (docs/storage-audit-cleanup.md § 3.3):
/// allocated size of each file and free/total bytes of the volume. Only
/// `dart:ffi` (no `package:ffi`): the UTF-8 path is copied into a buffer
/// from the C library's `calloc`, released with `free`. Symbols come from
/// `DynamicLibrary.process()` (libSystem on Darwin, glibc on Linux).
///
/// Layouts, chosen by `Abi.current()`:
/// - Darwin arm64 (iOS, macOS; the `lstat` symbol is the 64-bit inode
///   variant there): `struct stat` 144 bytes — `st_dev` int32 @0, `st_mode`
///   uint16 @4, `st_nlink` uint16 @6, `st_ino` uint64 @8, `st_size` int64
///   @96, `st_blocks` int64 @104; `struct statvfs` 64 bytes — `f_frsize`
///   unsigned long @8, `f_blocks` @16, `f_bavail` @24 (unsigned int).
///   Field order from the macOS SDK as generated in package:posix 6.5.0,
///   offsets checked with `clang -target arm64-apple-ios` static asserts;
///   still a hypothesis on the device (§ 7).
/// - Linux x86_64 glibc (CI; `lstat` exported since glibc 2.33):
///   `struct stat` 144 bytes — `st_dev` u64 @0, `st_ino` u64 @8, `st_nlink`
///   u64 @16, `st_mode` u32 @24, `st_size` i64 @48, `st_blocks` i64 @64;
///   `struct statvfs` 112 bytes — `f_frsize` @8, `f_blocks` @16, `f_bavail`
///   @32 (unsigned long). Checked with `offsetof` on glibc 2.39.
/// Any other ABI, a missing symbol, an exception or a failed self-test
/// gives [StorageStatLogical] for the session (`statViaFfi = false`).
library;

import 'dart:convert';
import 'dart:ffi';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/foundation.dart' show visibleForTesting;

/// File metadata the storage tool needs beyond `FileStat`.
abstract class StorageStat {
  /// True when sizes come from `lstat` (allocated bytes and volume space
  /// are meaningful).
  bool get available;

  /// `lstat` of [path] (a link is described, never followed); null on
  /// error.
  StorageStatInfo? lstat(String path);

  /// `statvfs` of the volume holding [path]; null when unavailable.
  StorageVolumeInfo? statvfs(String path);
}

class StorageStatInfo {
  const StorageStatInfo({
    required this.size,
    required this.blocks,
    required this.nlink,
    required this.ino,
    required this.dev,
    required this.mode,
  });

  final int size;

  /// 512-byte blocks allocated (`st_blocks`); 0 from [StorageStatLogical].
  final int blocks;
  final int nlink;
  final int ino;
  final int dev;
  final int mode;

  int get allocatedBytes => blocks * 512;
  bool get isLink => (mode & 0xF000) == 0xA000;
  bool get isDirectory => (mode & 0xF000) == 0x4000;
  bool get isRegularFile => (mode & 0xF000) == 0x8000;

  @override
  String toString() =>
      'StorageStatInfo(size: $size, blocks: $blocks, nlink: $nlink, '
      'mode: 0${mode.toRadixString(8)})';
}

class StorageVolumeInfo {
  const StorageVolumeInfo({
    required this.freeBytes,
    required this.totalBytes,
    required this.fragmentSize,
  });

  /// `f_bavail * f_frsize` (not the « Disponible » of iOS Settings, which
  /// counts purgeable space).
  final int freeBytes;

  /// `f_blocks * f_frsize`.
  final int totalBytes;

  /// `f_frsize`.
  final int fragmentSize;
}

/// Resolves a C symbol; null when it is not exported.
typedef StorageSymbolLookup = Pointer<Void>? Function(String symbol);

/// Byte offsets of `struct stat` and `struct statvfs` for one ABI.
class StorageStatLayout {
  const StorageStatLayout._({
    required this.name,
    required this.statSize,
    required this.devOffset,
    required this.devBytes,
    required this.modeOffset,
    required this.modeBytes,
    required this.nlinkOffset,
    required this.nlinkBytes,
    required this.inoOffset,
    required this.sizeOffset,
    required this.blocksOffset,
    required this.statvfsSize,
    required this.frsizeOffset,
    required this.vfsBlocksOffset,
    required this.vfsAvailOffset,
    required this.vfsCountBytes,
  });

  final String name;
  final int statSize;
  final int devOffset;
  final int devBytes;
  final int modeOffset;
  final int modeBytes;
  final int nlinkOffset;
  final int nlinkBytes;
  final int inoOffset;
  final int sizeOffset;
  final int blocksOffset;
  final int statvfsSize;
  final int frsizeOffset;
  final int vfsBlocksOffset;
  final int vfsAvailOffset;
  final int vfsCountBytes;

  static const StorageStatLayout darwinArm64 = StorageStatLayout._(
    name: 'darwin-arm64',
    statSize: 144,
    devOffset: 0,
    devBytes: 4,
    modeOffset: 4,
    modeBytes: 2,
    nlinkOffset: 6,
    nlinkBytes: 2,
    inoOffset: 8,
    sizeOffset: 96,
    blocksOffset: 104,
    statvfsSize: 64,
    frsizeOffset: 8,
    vfsBlocksOffset: 16,
    vfsAvailOffset: 24,
    vfsCountBytes: 4,
  );

  static const StorageStatLayout linuxX64 = StorageStatLayout._(
    name: 'linux-x64',
    statSize: 144,
    devOffset: 0,
    devBytes: 8,
    modeOffset: 24,
    modeBytes: 4,
    nlinkOffset: 16,
    nlinkBytes: 8,
    inoOffset: 8,
    sizeOffset: 48,
    blocksOffset: 64,
    statvfsSize: 112,
    frsizeOffset: 8,
    vfsBlocksOffset: 16,
    vfsAvailOffset: 32,
    vfsCountBytes: 8,
  );

  /// Null for every ABI without a verified layout (logical sizes there).
  static StorageStatLayout? forAbi(Abi abi) {
    if (abi == Abi.iosArm64 || abi == Abi.macosArm64) return darwinArm64;
    if (abi == Abi.linuxX64) return linuxX64;
    return null;
  }

  static int _read(ByteData data, int offset, int bytes) => switch (bytes) {
    2 => data.getUint16(offset, Endian.host),
    4 => data.getUint32(offset, Endian.host),
    _ => data.getUint64(offset, Endian.host),
  };

  StorageStatInfo readStat(ByteData data) => StorageStatInfo(
    dev: devBytes == 4
        ? data.getInt32(devOffset, Endian.host)
        : _read(data, devOffset, devBytes),
    mode: _read(data, modeOffset, modeBytes),
    nlink: _read(data, nlinkOffset, nlinkBytes),
    ino: data.getUint64(inoOffset, Endian.host),
    size: data.getInt64(sizeOffset, Endian.host),
    blocks: data.getInt64(blocksOffset, Endian.host),
  );

  ({int frsize, int blocks, int available}) readStatvfs(ByteData data) => (
    frsize: data.getUint64(frsizeOffset, Endian.host),
    blocks: _read(data, vfsBlocksOffset, vfsCountBytes),
    available: _read(data, vfsAvailOffset, vfsCountBytes),
  );
}

typedef _PathBufferNative = Int32 Function(Pointer<Uint8>, Pointer<Uint8>);
typedef _PathBufferDart = int Function(Pointer<Uint8>, Pointer<Uint8>);
typedef _CallocNative = Pointer<Void> Function(Size, Size);
typedef _CallocDart = Pointer<Void> Function(int, int);
typedef _FreeNative = Void Function(Pointer<Void>);
typedef _FreeDart = void Function(Pointer<Void>);

/// [StorageStat] through `lstat`/`statvfs`. Its function bindings are
/// plain closures: an instance can be sent to the scanner's isolates.
class StorageStatFfi implements StorageStat {
  StorageStatFfi._(
    this.layout,
    this._lstat,
    this._statvfs,
    this._calloc,
    this._free,
  );

  final StorageStatLayout layout;
  final _PathBufferDart _lstat;
  final _PathBufferDart _statvfs;
  final _CallocDart _calloc;
  final _FreeDart _free;

  /// Bytes reserved for the structure before the path in each buffer.
  static const int _structBytes = 256;

  static StorageStatFfi? _session;
  static bool _sessionFailed = false;

  /// The FFI implementation when this process supports it and its self-test
  /// passes on [probePath] (a readable directory: the Documents container),
  /// null otherwise. Without injected [lookup]/[abi] the verdict is kept
  /// for the session: once failed, every later call returns null.
  static StorageStatFfi? tryLoad({
    String? probePath,
    @visibleForTesting StorageSymbolLookup? lookup,
    @visibleForTesting Abi? abi,
  }) {
    final injected = lookup != null || abi != null;
    if (!injected) {
      if (_sessionFailed) return null;
      final cached = _session;
      if (cached != null) return cached;
    }
    StorageStatFfi? loaded;
    try {
      loaded = _load(
        probePath ?? Directory.current.path,
        lookup ?? _processLookup,
        abi ?? Abi.current(),
      );
    } catch (_) {
      loaded = null;
    }
    if (!injected) {
      _session = loaded;
      _sessionFailed = loaded == null;
    }
    return loaded;
  }

  /// Forgets the session verdict (tests).
  @visibleForTesting
  static void resetSession() {
    _session = null;
    _sessionFailed = false;
  }

  static Pointer<Void>? _processLookup(String symbol) {
    final library = DynamicLibrary.process();
    return library.providesSymbol(symbol) ? library.lookup<Void>(symbol) : null;
  }

  static StorageStatFfi? _load(
    String probePath,
    StorageSymbolLookup lookup,
    Abi abi,
  ) {
    final layout = StorageStatLayout.forAbi(abi);
    if (layout == null) return null;
    final lstat = lookup('lstat');
    final statvfs = lookup('statvfs');
    final calloc = lookup('calloc');
    final free = lookup('free');
    if (lstat == null || statvfs == null || calloc == null || free == null) {
      return null;
    }
    if (lstat.address == 0 ||
        statvfs.address == 0 ||
        calloc.address == 0 ||
        free.address == 0) {
      return null;
    }
    final instance = StorageStatFfi._(
      layout,
      lstat
          .cast<NativeFunction<_PathBufferNative>>()
          .asFunction<_PathBufferDart>(),
      statvfs
          .cast<NativeFunction<_PathBufferNative>>()
          .asFunction<_PathBufferDart>(),
      calloc.cast<NativeFunction<_CallocNative>>().asFunction<_CallocDart>(),
      free.cast<NativeFunction<_FreeNative>>().asFunction<_FreeDart>(),
    );
    return instance._selfTest(probePath) ? instance : null;
  }

  @override
  bool get available => true;

  @override
  StorageStatInfo? lstat(String path) {
    final data = _call(_lstat, path, layout.statSize);
    return data == null ? null : layout.readStat(data);
  }

  @override
  StorageVolumeInfo? statvfs(String path) {
    final values = _statvfsRaw(path);
    if (values == null) return null;
    return StorageVolumeInfo(
      freeBytes: values.available * values.frsize,
      totalBytes: values.blocks * values.frsize,
      fragmentSize: values.frsize,
    );
  }

  ({int frsize, int blocks, int available})? _statvfsRaw(String path) {
    final data = _call(_statvfs, path, layout.statvfsSize);
    return data == null ? null : layout.readStatvfs(data);
  }

  /// Calls `function(path, buffer)`; a copy of the structure on success.
  ByteData? _call(_PathBufferDart function, String path, int structSize) {
    final bytes = utf8.encode(path);
    if (bytes.contains(0)) return null;
    final total = _structBytes + bytes.length + 1;
    final block = _calloc(1, total);
    if (block.address == 0) return null;
    try {
      final memory = block.cast<Uint8>().asTypedList(total);
      memory.setRange(_structBytes, _structBytes + bytes.length, bytes);
      final status = function(
        Pointer<Uint8>.fromAddress(block.address + _structBytes),
        block.cast<Uint8>(),
      );
      if (status != 0) return null;
      // sublist copies onto the Dart heap before the buffer is freed.
      return ByteData.sublistView(memory.sublist(0, structSize));
    } finally {
      _free(block);
    }
  }

  /// `lstat` of [probe] (a directory) and of its first regular file must
  /// agree with `FileStat` (size and type); `statvfs` must give
  /// `512 <= f_frsize <= 1 MiB`, `0 < f_blocks` and `f_bavail <= f_blocks`.
  bool _selfTest(String probe) {
    if (FileSystemEntity.typeSync(probe, followLinks: false) !=
        FileSystemEntityType.directory) {
      return false;
    }
    final info = lstat(probe);
    final stat = FileStat.statSync(probe);
    if (info == null ||
        !info.isDirectory ||
        stat.type != FileSystemEntityType.directory ||
        info.size != stat.size ||
        info.nlink < 1 ||
        info.blocks < 0) {
      return false;
    }
    File? sample;
    try {
      for (final entity in Directory(probe).listSync(followLinks: false)) {
        if (entity is File &&
            FileSystemEntity.typeSync(entity.path, followLinks: false) ==
                FileSystemEntityType.file) {
          sample = entity;
          break;
        }
      }
    } on FileSystemException {
      sample = null;
    }
    if (sample != null) {
      final fileInfo = lstat(sample.path);
      final fileStat = sample.statSync();
      if (fileInfo == null ||
          !fileInfo.isRegularFile ||
          fileInfo.size != fileStat.size ||
          fileInfo.blocks < 0 ||
          fileInfo.nlink < 1) {
        return false;
      }
    }
    final volume = _statvfsRaw(probe);
    if (volume == null) return false;
    return volume.frsize >= 512 &&
        volume.frsize <= 1024 * 1024 &&
        volume.blocks > 0 &&
        volume.available >= 0 &&
        volume.available <= volume.blocks;
  }
}

/// Logical sizes only (`FileStat`): no allocation, no volume space.
class StorageStatLogical implements StorageStat {
  const StorageStatLogical();

  @override
  bool get available => false;

  @override
  StorageStatInfo? lstat(String path) {
    try {
      final type = FileSystemEntity.typeSync(path, followLinks: false);
      if (type == FileSystemEntityType.notFound) return null;
      if (type == FileSystemEntityType.link) {
        return const StorageStatInfo(
          size: 0,
          blocks: 0,
          nlink: 1,
          ino: 0,
          dev: 0,
          mode: 0xA000,
        );
      }
      final stat = FileStat.statSync(path);
      final typeBits = type == FileSystemEntityType.directory ? 0x4000 : 0x8000;
      return StorageStatInfo(
        size: stat.size,
        blocks: 0,
        nlink: 1,
        ino: 0,
        dev: 0,
        mode: typeBits | (stat.mode & 0xFFF),
      );
    } on FileSystemException {
      return null;
    }
  }

  @override
  StorageVolumeInfo? statvfs(String path) => null;
}
