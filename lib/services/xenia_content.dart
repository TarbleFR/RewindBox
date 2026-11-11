import 'dart:io';
import 'dart:convert';
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:path/path.dart' as path;

/// What a picked Xbox 360 file is, for the embedded XeniOS engine
/// (docs/xenios-playlist.md § Formats).
///
/// Only [discImage] and [zarArchive] are games RewindBox imports as one
/// file. A loose `.xex` is a game executable that needs its whole title
/// folder beside it, and a Games on Demand package is a header plus a
/// `.data` folder: both are imported from a picked folder
/// ([XeniaFolderGame]), never from a single picked file, so they are not
/// half-imported. Profiles and touch layouts are XeniOS user data, never
/// games.
enum XeniaContentKind {
  /// XGD/XISO disc image (`.iso`), read by Xenia's DiscImageDevice.
  discImage,

  /// ZArchive (`.zar`), read by Xenia's DiscZarchiveDevice.
  zarArchive,

  /// Loose title executable (`.xex`): playable only inside its folder.
  looseExecutable,

  /// Xbox 360 content package header (CON/LIVE/PIRS): a Games on Demand
  /// (SVOD) header with its `<header>.data` folder, or a single-file STFS
  /// package (Xbox Live Arcade). Imported packages are named `<title>.god`.
  package,

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
  /// Extensions the Xbox 360 playlist scans and launches on iOS. `god` is
  /// the name RewindBox gives an imported package header; the engine reads
  /// its magic, not its name.
  static const Set<String> gameExtensions = <String>{
    'iso',
    'zar',
    'xex',
    'god',
  };

  /// Extensions accepted by the single-file import.
  static const Set<String> importExtensions = <String>{'iso', 'zar'};

  /// Offered by the picker: games plus the extensions that are refused with
  /// a precise reason (so the user learns why rather than seeing nothing).
  static const Set<String> pickerExtensions = <String>{
    'iso',
    'zar',
    'xex',
    'god',
    'xeniosprofile',
    'toml',
  };

  static XeniaContentKind kindForName(String name) {
    final extension = path.extension(name).replaceFirst('.', '').toLowerCase();
    return switch (extension) {
      'iso' => XeniaContentKind.discImage,
      'zar' => XeniaContentKind.zarArchive,
      'xex' => XeniaContentKind.looseExecutable,
      'god' => XeniaContentKind.package,
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

/// Header of an Xbox 360 content package (XContent, big-endian), as read
/// by xenia/vfs/devices/xcontent_container_device.cc and stfs_metadata.cc.
class XeniaPackageInfo {
  const XeniaPackageInfo({
    required this.contentType,
    required this.titleId,
    required this.mediaId,
    required this.isSvod,
    required this.dataFileCount,
    this.displayName,
  });

  final int contentType;
  final String? titleId;
  final String? mediaId;

  /// SVOD volume (Games on Demand: the header plus `<header>.data`);
  /// otherwise a single-file STFS package.
  final bool isSvod;

  /// Files the SVOD volume expects in `<header>.data`.
  final int dataFileCount;
  final String? displayName;

  /// Content types XeniOS's library lists as launchable (installed game,
  /// Xbox 360 title, arcade, demo, community game). Original Xbox titles,
  /// saves, add-ons and updates are not games of this playlist.
  static const Set<int> launchableContentTypes = <int>{
    0x00004000,
    0x00007000,
    0x000D0000,
    0x00080000,
    0x02000000,
  };

  bool get isGame => launchableContentTypes.contains(contentType);
}

enum XeniaFolderGameKind {
  /// A title folder holding `default.xex` (launched by that file: the
  /// engine mounts its parent folder as `game:`).
  executable,

  /// A Games on Demand header plus its `.data` folder, or a single-file
  /// STFS package (launched by the header).
  package,
}

/// One game found in a picked folder.
class XeniaFolderGame {
  const XeniaFolderGame({
    required this.kind,
    required this.launchFile,
    required this.files,
    required this.totalBytes,
    required this.title,
    this.titleId,
    this.mediaId,
    this.discNumber,
    this.dataDirectory,
  });

  final XeniaFolderGameKind kind;

  /// `default.xex`, or the package header.
  final File launchFile;

  /// Every file the import copies: the whole title folder of an
  /// executable; the header then its counted data files for a package.
  final List<File> files;
  final int totalBytes;

  /// Library name: the title folder's name, or the package's display name.
  final String title;
  final String? titleId;
  final String? mediaId;
  final int? discNumber;

  /// `<header>.data` of a Games on Demand package.
  final Directory? dataDirectory;

  /// Directory whose tree an executable import copies.
  Directory get root => launchFile.parent;
}

/// A candidate refused while reading a picked folder; [reason] is a
/// XeniaLocale key.
class XeniaFolderProblem {
  const XeniaFolderProblem(this.name, this.reason);
  final String name;
  final String reason;
}

class XeniaFolderScan {
  const XeniaFolderScan(this.games, this.problems);
  final List<XeniaFolderGame> games;
  final List<XeniaFolderProblem> problems;
}

/// Reads a picked folder for Xbox 360 games, never loading game data
/// (docs/xenios-playlist.md § Folder import).
abstract final class XeniaFolderContent {
  static const String executableName = 'default.xex';

  /// Directories below the picked one that are searched. Covers the
  /// console layout `<TitleID>/00007000/<header>` under a picked
  /// `Content/0000000000000000`.
  static const int maxDepth = 5;
  static const int maxEntries = 200000;

  // xenia/vfs/devices/stfs_xbox.h (XContentHeader + XContentMetadata).
  static const int _headerBytes = 0x971;
  static const int _contentTypeOffset = 0x344;
  static const int _mediaIdOffset = 0x354;
  static const int _titleIdOffset = 0x360;
  static const int _dataFileCountOffset = 0x39D;
  static const int _volumeTypeOffset = 0x3A9;
  static const int _displayNameOffset = 0x411;
  static const int _displayNameBytes = 0x100;

  /// SvodContainerDevice's `MAX_FILE_SIZE` for one data file.
  static const int maxDataFileBytes = 0xA290000;
  static const Set<String> _packageMagics = <String>{'CON ', 'LIVE', 'PIRS'};

  /// Finder and Files metadata that is never game content.
  static bool isSystemClutter(String name) =>
      name == '.DS_Store' || name.startsWith('._');

  static Future<XeniaFolderScan> scan(Directory picked) async {
    final games = <XeniaFolderGame>[];
    final problems = <XeniaFolderProblem>[];
    var visited = 0;

    Future<void> walk(Directory directory, int depth) async {
      final List<FileSystemEntity> children;
      try {
        children = await directory.list(followLinks: false).toList();
      } on FileSystemException {
        problems.add(
          XeniaFolderProblem(path.basename(directory.path), 'unreadable'),
        );
        return;
      }
      visited += children.length;
      final executable = children.whereType<File>().where(
        (file) => path.basename(file.path).toLowerCase() == executableName,
      );
      if (executable.isNotEmpty) {
        final game = await _executableGame(executable.first);
        if (game is XeniaFolderGame) {
          games.add(game);
        } else if (game is XeniaFolderProblem) {
          problems.add(game);
        }
        // A title folder is one game: its other .xex files and subfolders
        // belong to it.
        return;
      }
      children.sort((a, b) => a.path.compareTo(b.path));
      for (final child in children) {
        final name = path.basename(child.path);
        if (child is File) {
          if (isSystemClutter(name) || name.toLowerCase().endsWith('.data')) {
            continue;
          }
          final package = await _packageGame(child);
          if (package is XeniaFolderGame) {
            games.add(package);
          } else if (package is XeniaFolderProblem) {
            problems.add(package);
          }
        } else if (child is Directory &&
            depth < maxDepth &&
            visited < maxEntries &&
            !name.startsWith('.') &&
            !name.toLowerCase().endsWith('.data')) {
          await walk(child, depth + 1);
        }
      }
    }

    await walk(picked, 0);
    if (games.isEmpty && problems.isEmpty) {
      problems.add(
        XeniaFolderProblem(path.basename(picked.path), 'folderNoGame'),
      );
    }
    return XeniaFolderScan(games, problems);
  }

  static Future<Object> _executableGame(File xex) async {
    final root = xex.parent;
    final identity = await XeniaContent.inspectExecutable(xex);
    if (identity == null) {
      return XeniaFolderProblem(path.basename(root.path), 'executableInvalid');
    }
    final files = <File>[];
    var total = 0;
    try {
      await for (final entity in root.list(
        recursive: true,
        followLinks: false,
      )) {
        if (entity is! File || isSystemClutter(path.basename(entity.path))) {
          continue;
        }
        files.add(entity);
        total += await entity.length();
      }
    } on FileSystemException {
      return XeniaFolderProblem(path.basename(root.path), 'unreadable');
    }
    return XeniaFolderGame(
      kind: XeniaFolderGameKind.executable,
      launchFile: xex,
      files: files,
      totalBytes: total,
      title: path.basename(root.path),
      titleId: XeniaContent.normalizeTitleId(identity.titleId),
      mediaId: identity.mediaId,
      discNumber: identity.discNumber,
    );
  }

  /// Null when [file] is not a content package (any other file in the
  /// folder is ignored, like XeniOS's own library scan).
  static Future<Object?> _packageGame(File file) async {
    final name = path.basename(file.path);
    final XeniaPackageInfo? info;
    try {
      info = await inspectPackage(file);
    } on FileSystemException {
      return null;
    }
    if (info == null) return null;
    if (!info.isGame) return XeniaFolderProblem(name, 'packageNotGame');
    final title = _cleanTitle(info.displayName) ?? info.titleId ?? name;
    if (!info.isSvod) {
      final length = await file.length();
      return XeniaFolderGame(
        kind: XeniaFolderGameKind.package,
        launchFile: file,
        files: <File>[file],
        totalBytes: length,
        title: title,
        titleId: info.titleId,
        mediaId: info.mediaId,
      );
    }
    final data = Directory('${file.path}.data');
    if (!await data.exists()) {
      return XeniaFolderProblem(name, 'packageDataMissing');
    }
    final dataFiles = <File>[];
    var total = await file.length();
    try {
      await for (final entity in data.list(followLinks: false)) {
        final entryName = path.basename(entity.path);
        if (isSystemClutter(entryName)) continue;
        // SvodContainerDevice::LoadHostFiles counts every entry of the
        // folder and wants regular files only; the import copies only the
        // data files, so Finder metadata of the source does not count.
        if (entity is! File) {
          return XeniaFolderProblem(name, 'packageIncomplete');
        }
        final length = await entity.length();
        if (length <= 0 || length > maxDataFileBytes) {
          return XeniaFolderProblem(name, 'packageIncomplete');
        }
        dataFiles.add(entity);
        total += length;
      }
    } on FileSystemException {
      return XeniaFolderProblem(name, 'unreadable');
    }
    if (dataFiles.isEmpty || dataFiles.length != info.dataFileCount) {
      return XeniaFolderProblem(name, 'packageIncomplete');
    }
    dataFiles.sort((a, b) => a.path.compareTo(b.path));
    return XeniaFolderGame(
      kind: XeniaFolderGameKind.package,
      launchFile: file,
      files: <File>[file, ...dataFiles],
      totalBytes: total,
      title: title,
      titleId: info.titleId,
      mediaId: info.mediaId,
      dataDirectory: data,
    );
  }

  /// Reads the XContent header of [file]; null when it does not start
  /// with a CON/LIVE/PIRS magic or is shorter than the header.
  static Future<XeniaPackageInfo?> inspectPackage(File file) async {
    final handle = await file.open();
    try {
      final header = await handle.read(_headerBytes);
      if (header.length < _headerBytes) return null;
      if (!_packageMagics.contains(
        String.fromCharCodes(header.sublist(0, 4)),
      )) {
        return null;
      }
      final view = ByteData.sublistView(header);
      String hex(int value) =>
          value.toRadixString(16).toUpperCase().padLeft(8, '0');
      final units = <int>[];
      for (var at = 0; at + 1 < _displayNameBytes; at += 2) {
        final unit = view.getUint16(_displayNameOffset + at);
        if (unit == 0) break;
        units.add(unit);
      }
      return XeniaPackageInfo(
        contentType: view.getUint32(_contentTypeOffset),
        titleId: XeniaContent.normalizeTitleId(
          hex(view.getUint32(_titleIdOffset)),
        ),
        mediaId: hex(view.getUint32(_mediaIdOffset)),
        isSvod: view.getUint32(_volumeTypeOffset) == 1,
        dataFileCount: view.getUint32(_dataFileCountOffset),
        displayName: units.isEmpty ? null : String.fromCharCodes(units),
      );
    } finally {
      await handle.close();
    }
  }

  /// A display name usable as a file name (no separators or controls).
  static String? _cleanTitle(String? value) {
    final cleaned = value
        ?.replaceAll(RegExp(r'[\x00-\x1F/\\:*?"<>|]'), ' ')
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
    if (cleaned == null || cleaned.isEmpty || cleaned.startsWith('.')) {
      return null;
    }
    return cleaned.length > 120 ? cleaned.substring(0, 120).trim() : cleaned;
  }

  // ---------------------------------------------------------------- library

  /// Whether a scanned file is a playlist entry on iOS: only `default.xex`
  /// among executables (a title folder's other .xex files are not games),
  /// and nothing inside a package's `.data` folder.
  static bool isLibraryEntry(String filePath) {
    final segments = path.split(path.dirname(filePath));
    if (segments.any((segment) => segment.toLowerCase().endsWith('.data'))) {
      return false;
    }
    if (XeniaContent.kindForName(filePath) ==
        XeniaContentKind.looseExecutable) {
      return path.basename(filePath).toLowerCase() == executableName;
    }
    return true;
  }

  /// Library file names of the scanned `default.xex` entries, by path.
  ///
  /// The `filename` column is a game's identity in RewindBox's database
  /// (scraped metadata `UNIQUE(app_system_id, filename)`, media named after
  /// it, favorites and history by `getSingleGame(system, filename)`), and
  /// every title folder ends in `default.xex`. Each one gets `<folder>.xex`,
  /// or `<folder> [<digest>].xex` (8 hex digits of its path) only when that
  /// name is already taken by another entry of the scan or another stored
  /// row. A name stored before, other than `default.xex`, is kept, so a
  /// game never changes identity on a later scan. [stored] maps stored
  /// `rom_path` to `filename` for the system (paths compared without case,
  /// like the column).
  static Map<String, String> libraryFileNames(
    Iterable<String> scanned, {
    Map<String, String> stored = const <String, String>{},
  }) {
    final storedByPath = <String, String>{
      for (final entry in stored.entries) entry.key.toLowerCase(): entry.value,
    };
    final taken = <String>{
      for (final name in stored.values)
        if (name.toLowerCase() != executableName) name.toLowerCase(),
    };
    final executables = <String>[];
    for (final location in scanned) {
      if (path.basename(location).toLowerCase() == executableName) {
        executables.add(location);
      } else {
        taken.add(path.basename(location).toLowerCase());
      }
    }
    executables.sort();
    final names = <String, String>{};
    final unnamed = <String>[];
    for (final location in executables) {
      final kept = storedByPath[location.toLowerCase()];
      if (kept != null && kept.toLowerCase() != executableName) {
        names[location] = kept;
        taken.add(kept.toLowerCase());
      } else {
        unnamed.add(location);
      }
    }
    for (final location in unnamed) {
      var folder = path.basename(path.dirname(location)).trim();
      if (folder.isEmpty || folder == '.' || folder == path.separator) {
        folder = 'Xbox 360 game';
      }
      var name = '$folder.xex';
      if (taken.contains(name.toLowerCase())) {
        final digest = sha1
            .convert(utf8.encode(path.normalize(location).toLowerCase()))
            .toString()
            .substring(0, 8);
        name = '$folder [$digest].xex';
      }
      taken.add(name.toLowerCase());
      names[location] = name;
    }
    return names;
  }

  /// Name shown for a scanned entry: the title folder of a `default.xex`,
  /// the package name of a `.god` header; null for files named after
  /// their game already.
  static String? libraryTitle(String filePath) {
    return switch (XeniaContent.kindForName(filePath)) {
      XeniaContentKind.looseExecutable => path.basename(path.dirname(filePath)),
      XeniaContentKind.package => path.basenameWithoutExtension(filePath),
      _ => null,
    };
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
