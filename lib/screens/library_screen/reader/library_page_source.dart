import 'dart:async';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';

import 'package:neostation/services/library_archive_pages.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_local_models.dart';

/// Pages of one chapter or one comic book, decoded lazily at display size.
abstract class LibraryPageSource {
  /// Identity of the pages (progress and caches).
  String get key;

  int get length;

  /// Image of page [index] decoded to fit inside [cacheWidth] x
  /// [cacheHeight] physical pixels (null = no limit on that side; aspect
  /// ratio kept, never upscaled).
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight});

  /// Warms page [index] (best effort: download to the disk cache).
  void prefetch(int index);

  /// Releases the resources of the pages (archive worker, downloads).
  Future<void> dispose();
}

/// Online chapter pages, through the Library image cache.
class LibraryNetworkPageSource implements LibraryPageSource {
  LibraryNetworkPageSource(
    List<String> urls, {
    Map<String, String> headers = const <String, String>{},
    String? key,
    LibraryImageCache? cache,
  }) : urls = List<String>.unmodifiable(urls),
       headers = Map<String, String>.unmodifiable(headers),
       key = key ?? (urls.isEmpty ? 'pages:' : 'pages:${urls.first}'),
       _cache = cache;

  final List<String> urls;
  final Map<String, String> headers;
  @override
  final String key;
  final LibraryImageCache? _cache;
  final LibraryCancelToken _cancel = LibraryCancelToken();
  final Set<int> _prefetched = <int>{};

  LibraryImageCache get _imageCache => _cache ?? LibraryImageCache.instance;

  @override
  int get length => urls.length;

  @override
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight}) =>
      LibraryNetworkImage(
        urls[index],
        headers: headers,
        cacheWidth: cacheWidth,
        cacheHeight: cacheHeight,
        cache: _cache,
      );

  @override
  void prefetch(int index) {
    if (index < 0 || index >= urls.length || _cancel.isCancelled) return;
    if (!_prefetched.add(index)) return;
    unawaited(
      _imageCache
          .prefetch(<String>[urls[index]], headers: headers, cancel: _cancel)
          .catchError((Object _) {}),
    );
  }

  @override
  Future<void> dispose() async => _cancel.cancel();
}

/// Pages of a comic archive (CBZ) read by its worker isolate. The handle is
/// kept open while the reader shows the book so every page reuses the same
/// worker.
class LibraryArchivePageSource implements LibraryPageSource {
  LibraryArchivePageSource._(this._pages, this._version);

  /// Opens [path]. Throws [LibraryBookException] (corrupt, no page,
  /// unreadable).
  static Future<LibraryArchivePageSource> open(String path) async {
    final version = await _versionOf(path);
    final pages = await LibraryArchivePages.open(path);
    return LibraryArchivePageSource._(pages, version);
  }

  /// Size and modification time: images decoded from a file later replaced
  /// at the same path are never shown for the new one.
  static Future<String> _versionOf(String path) async {
    try {
      final stat = await File(path).stat();
      return '${stat.size}:${stat.modified.microsecondsSinceEpoch}';
    } on FileSystemException {
      return '';
    }
  }

  final LibraryArchivePages _pages;
  final String _version;
  bool _disposed = false;

  String get path => _pages.path;

  /// ComicInfo.xml metadata, when present.
  LibraryBookMetadata? get comicInfo => _pages.comicInfo;

  @override
  String get key => 'archive:$path:$_version';

  @override
  int get length => _pages.pageCount;

  @override
  ImageProvider imageFor(int index, {int? cacheWidth, int? cacheHeight}) =>
      LibraryVersionedArchivePageImage(
        LibraryArchivePageImage(
          path,
          index,
          cacheWidth: cacheWidth,
          cacheHeight: cacheHeight,
        ),
        _version,
      );

  @override
  void prefetch(int index) {
    // Pages are local: the worker decompresses one in a few milliseconds.
  }

  @override
  Future<void> dispose() async {
    if (_disposed) return;
    _disposed = true;
    await _pages.close();
  }
}

/// [LibraryArchivePageImage] keyed by the file version as well, so the
/// Flutter image cache never serves pages of a replaced file.
@immutable
class LibraryVersionedArchivePageImage
    extends ImageProvider<LibraryVersionedArchivePageImage> {
  const LibraryVersionedArchivePageImage(this.page, this.version);

  final LibraryArchivePageImage page;
  final String version;

  @override
  Future<LibraryVersionedArchivePageImage> obtainKey(
    ImageConfiguration configuration,
  ) => SynchronousFuture<LibraryVersionedArchivePageImage>(this);

  @override
  ImageStreamCompleter loadImage(
    LibraryVersionedArchivePageImage key,
    ImageDecoderCallback decode,
  ) {
    final completer = key.page.loadImage(key.page, decode);
    // Failures are not kept under this key either: a retry reloads. The
    // listener removes itself after the first outcome so it never keeps a
    // decoded page alive.
    late final ImageStreamListener listener;
    listener = ImageStreamListener(
      (ImageInfo info, bool _) {
        info.dispose();
        completer.removeListener(listener);
      },
      onError: (Object _, StackTrace? _) {
        completer.removeListener(listener);
        scheduleMicrotask(() => PaintingBinding.instance.imageCache.evict(key));
      },
    );
    completer.addListener(listener);
    return completer;
  }

  @override
  bool operator ==(Object other) =>
      other is LibraryVersionedArchivePageImage &&
      other.page == page &&
      other.version == version;

  @override
  int get hashCode => Object.hash(page, version);

  @override
  String toString() => 'LibraryVersionedArchivePageImage($page, $version)';
}
