import 'dart:async';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:neostation/services/library_book_formats.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:path/path.dart' as p;

/// Lazy page access to comic archives (CBZ, or a ZIP named `.zip`/`.cbr`).
///
/// One worker isolate per archive path keeps the central directory open and
/// decompresses only the requested page; nothing is cached on either side
/// (the Flutter image cache holds decoded pages). Handles to the same path
/// share the worker through reference counting, and the worker stays alive
/// [idleTimeout] after the last handle closes so page images resolved
/// outside a reader session do not respawn it for every page.
class LibraryArchivePages {
  LibraryArchivePages._(this._shared);

  final _SharedArchive _shared;
  bool _closed = false;

  /// Time a worker without handles stays alive.
  static Duration idleTimeout = const Duration(seconds: 10);

  static final Map<String, _SharedArchive> _archives =
      <String, _SharedArchive>{};

  /// Number of archive workers currently alive or starting.
  @visibleForTesting
  static int get debugOpenArchiveCount => _archives.length;

  /// Opens (or shares) the archive at [path]. Throws [LibraryBookException]
  /// ([LibraryBookIssue.corrupt], [LibraryBookIssue.noContent],
  /// [LibraryBookIssue.unreadable]).
  static Future<LibraryArchivePages> open(String path) async {
    final key = p.normalize(p.absolute(path));
    // A worker keeps the file it opened even after that file is deleted or
    // replaced: share it only while the path still holds the same file.
    final identity = await _identityOf(key);
    var shared = _archives[key];
    if (shared != null && shared.identity != identity) {
      // Handles still using it keep it alive; it ends with the last one.
      _archives.remove(key);
      if (shared._references == 0) unawaited(shared.shutdown());
      shared = null;
    }
    if (shared == null) {
      shared = _SharedArchive(key, identity);
      _archives[key] = shared;
      shared.start();
    }
    shared.retain();
    try {
      await shared.ready;
    } catch (_) {
      shared.release();
      rethrow;
    }
    return LibraryArchivePages._(shared);
  }

  /// Size and modification time of [path]; null when it cannot be read (the
  /// worker then reports the error).
  static Future<String?> _identityOf(String path) async {
    try {
      final stat = await File(path).stat();
      if (stat.type == FileSystemEntityType.notFound) return null;
      return '${stat.size}:${stat.modified.microsecondsSinceEpoch}';
    } on FileSystemException {
      return null;
    }
  }

  String get path => _shared.path;

  int get pageCount => _shared.info!.pageNames.length;

  /// Archive names of the pages, in natural order.
  List<String> get pageNames => _shared.info!.pageNames;

  /// ComicInfo.xml metadata, when present.
  LibraryBookMetadata? get comicInfo => _shared.info!.comicInfo;

  /// Decompressed bytes of page [index]. Throws [RangeError] for an invalid
  /// index and [LibraryBookException] for an encrypted, unsupported,
  /// oversized or damaged entry.
  Future<Uint8List> page(int index) async {
    if (_closed) throw StateError('LibraryArchivePages closed');
    RangeError.checkValidIndex(index, pageNames, 'index');
    final worker = await _shared.ready;
    return await worker.request('page', index) as Uint8List;
  }

  /// Entry names decompressed by the worker since it opened (most recent
  /// 256), for tests.
  @visibleForTesting
  Future<List<String>> debugDecompressedEntries() async {
    final worker = await _shared.ready;
    return (await worker.request('debugReads') as List).cast<String>();
  }

  /// Releases this handle.
  Future<void> close() async {
    if (_closed) return;
    _closed = true;
    await _shared.release();
  }

  /// Closes every worker immediately (for tests).
  @visibleForTesting
  static Future<void> debugCloseAll() async {
    final archives = _archives.values.toList();
    _archives.clear();
    for (final archive in archives) {
      await archive.shutdown();
    }
  }
}

class _ArchiveInfo {
  const _ArchiveInfo(this.pageNames, this.comicInfo);

  final List<String> pageNames;
  final LibraryBookMetadata? comicInfo;
}

class _SharedArchive {
  _SharedArchive(this.path, this.identity);

  final String path;

  /// Identity of the file when the worker was started (see `_identityOf`).
  final String? identity;
  late final Future<LibraryIsolateWorker> ready;
  LibraryIsolateWorker? _worker;
  _ArchiveInfo? info;
  int _references = 0;
  Timer? _idle;
  bool _shutdown = false;

  void start() {
    ready =
        LibraryIsolateWorker.spawn(
          _openArchiveWorker,
          path,
          debugName: 'library-cbz',
        ).then((worker) {
          _worker = worker;
          info = worker.openResult! as _ArchiveInfo;
          if (_shutdown) unawaited(worker.close());
          return worker;
        });
    // Failed opens are forgotten so a later open retries.
    ready.then<void>(
      (_) {},
      onError: (Object _) {
        if (identical(LibraryArchivePages._archives[path], this)) {
          LibraryArchivePages._archives.remove(path);
        }
      },
    );
  }

  void retain() {
    _references++;
    _idle?.cancel();
    _idle = null;
  }

  Future<void> release() async {
    if (_references > 0) _references--;
    if (_references > 0) return;
    _idle?.cancel();
    final timeout = LibraryArchivePages.idleTimeout;
    if (timeout <= Duration.zero) {
      await _expire();
    } else {
      _idle = Timer(timeout, () => unawaited(_expire()));
    }
  }

  Future<void> _expire() async {
    _idle = null;
    if (_references > 0) return;
    if (identical(LibraryArchivePages._archives[path], this)) {
      LibraryArchivePages._archives.remove(path);
    }
    await shutdown();
  }

  Future<void> shutdown() async {
    _idle?.cancel();
    _idle = null;
    _shutdown = true;
    final worker = _worker;
    if (worker != null) await worker.close();
  }
}

LibraryWorkerHandler _openArchiveWorker(String path) => _ArchiveWorker(path);

class _ArchiveWorker implements LibraryWorkerHandler {
  _ArchiveWorker(String path) : _zip = LibraryZipArchive.open(path) {
    _pages = libraryComicPageEntries(_zip);
    _zip.onEntryRead = (name) {
      _reads.add(name);
      if (_reads.length > 256) _reads.removeAt(0);
    };
  }

  final LibraryZipArchive _zip;
  late final List<LibraryZipEntry> _pages;
  final List<String> _reads = <String>[];

  @override
  Object? handle(String operation, Object? argument) {
    switch (operation) {
      case 'open':
        if (_pages.isEmpty) {
          throw const LibraryBookException(
            LibraryBookIssue.noContent,
            detail: 'no page image in archive',
          );
        }
        return _ArchiveInfo(
          List<String>.unmodifiable(_pages.map((entry) => entry.name)),
          libraryReadComicInfo(_zip),
        );
      case 'page':
        final index = argument! as int;
        return _zip.read(
          _pages[index],
          maxBytes: LibraryBookLimits.maxPageBytes,
        );
      case 'debugReads':
        return List<String>.of(_reads);
    }
    throw ArgumentError.value(operation, 'operation');
  }

  @override
  void close() => _zip.close();
}

/// Page [index] of the comic archive at [path], decoded no larger than
/// [cacheWidth] x [cacheHeight] (aspect ratio kept, never upscaled).
@immutable
class LibraryArchivePageImage extends ImageProvider<LibraryArchivePageImage> {
  const LibraryArchivePageImage(
    this.path,
    this.index, {
    this.cacheWidth,
    this.cacheHeight,
    this.scale = 1.0,
  });

  final String path;
  final int index;
  final int? cacheWidth;
  final int? cacheHeight;
  final double scale;

  /// Decode size fitting [width] x [height] inside the limits without
  /// upscaling.
  @visibleForTesting
  static ui.TargetImageSize targetSizeFor(
    int width,
    int height, {
    int? maxWidth,
    int? maxHeight,
  }) {
    if (width <= 0 || height <= 0) return const ui.TargetImageSize();
    var factor = 1.0;
    if (maxWidth != null && maxWidth > 0 && maxWidth < width) {
      factor = math.min(factor, maxWidth / width);
    }
    if (maxHeight != null && maxHeight > 0 && maxHeight < height) {
      factor = math.min(factor, maxHeight / height);
    }
    if (factor >= 1.0) return const ui.TargetImageSize();
    return ui.TargetImageSize(
      width: math.max(1, (width * factor).round()),
      height: math.max(1, (height * factor).round()),
    );
  }

  @override
  Future<LibraryArchivePageImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<LibraryArchivePageImage>(this);

  @override
  ImageStreamCompleter loadImage(
    LibraryArchivePageImage key,
    ImageDecoderCallback decode,
  ) => MultiFrameImageStreamCompleter(
    codec: _load(key, decode),
    scale: key.scale,
    debugLabel: '${p.basename(key.path)}#${key.index}',
    informationCollector: () => <DiagnosticsNode>[
      DiagnosticsProperty<String>('Archive', key.path),
      IntProperty('Page', key.index),
    ],
  );

  static Future<ui.Codec> _load(
    LibraryArchivePageImage key,
    ImageDecoderCallback decode,
  ) async {
    LibraryArchivePages? pages;
    try {
      pages = await LibraryArchivePages.open(key.path);
      final bytes = await pages.page(key.index);
      if (bytes.isEmpty) {
        throw const LibraryBookException(
          LibraryBookIssue.corrupt,
          detail: 'empty page',
        );
      }
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      return await decode(
        buffer,
        getTargetSize: (width, height) => targetSizeFor(
          width,
          height,
          maxWidth: key.cacheWidth,
          maxHeight: key.cacheHeight,
        ),
      );
    } catch (_) {
      // Do not keep a failed page in the image cache: a later attempt (after
      // the file reappears, for example) must reload it.
      scheduleMicrotask(() => PaintingBinding.instance.imageCache.evict(key));
      rethrow;
    } finally {
      await pages?.close();
    }
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryArchivePageImage &&
      other.path == path &&
      other.index == index &&
      other.cacheWidth == cacheWidth &&
      other.cacheHeight == cacheHeight &&
      other.scale == scale;

  @override
  int get hashCode => Object.hash(path, index, cacheWidth, cacheHeight, scale);

  @override
  String toString() =>
      'LibraryArchivePageImage(${p.basename(path)}#$index, '
      '${cacheWidth ?? '-'}x${cacheHeight ?? '-'})';
}
