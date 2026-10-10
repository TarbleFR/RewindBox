import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/painting.dart';
import 'package:neostation/services/library_http.dart';
import 'package:path/path.dart' as p;

/// Keeps selected cover images out of cache trimming (favourite covers).
abstract interface class LibraryCoverPinner {
  /// Protects [url] from trimming. With [fetch], the image is also
  /// downloaded in the background (best effort) so it is available offline.
  Future<void> pin(
    String url, {
    Map<String, String> headers = const <String, String>{},
    bool fetch = false,
  });

  /// Removes the protection added by [pin]. The file itself stays cached
  /// until normal trimming removes it.
  Future<void> unpin(String url);
}

/// Counters used by tests and performance measurements.
class LibraryImageCacheStats {
  int diskHits = 0;
  int networkLoads = 0;
  int notModified = 0;
  int staleServed = 0;
  int deduplicated = 0;
  int failures = 0;

  Map<String, Object> toJson() => <String, Object>{
    'diskHits': diskHits,
    'networkLoads': networkLoads,
    'notModified': notModified,
    'staleServed': staleServed,
    'deduplicated': deduplicated,
    'failures': failures,
  };
}

/// Persistent cover/page image cache of the reading Library.
///
/// Encoded image bytes are stored in `<cacheDirectory>/library_images`
/// (default `Caches/Library/library_images`) with their own size limit and
/// LRU trimming; [pin]ned URLs are never trimmed. Downloads go through
/// [LibraryHttp] (shared client, per-host limits, typed errors) without its
/// memory body cache: decoded images live in Flutter's `ImageCache`, at the
/// display size requested by [LibraryNetworkImage].
///
/// A cached image is used without network for [freshFor]; afterwards it is
/// revalidated with `If-None-Match` / `If-Modified-Since`. When the network
/// fails, any cached copy is returned. Concurrent loads of one URL share a
/// single operation.
class LibraryImageCache implements LibraryCoverPinner {
  LibraryImageCache({
    LibraryFetcher? fetcher,
    Directory? cacheDirectory,
    DateTime Function()? clock,
    this.maxBytes = defaultMaxBytes,
    this.freshFor = const Duration(days: 30),
    this.requestTimeout = const Duration(seconds: 30),
    this.maxImageBytes = 32 * 1024 * 1024,
  }) : _fetcher = fetcher,
       _clock = clock ?? DateTime.now {
    _disk = LibraryDiskCache(
      () async {
        final base =
            cacheDirectory ?? await LibraryHttp.defaultCacheDirectory();
        return Directory(p.join(base.path, folderName));
      },
      maxBytes: maxBytes,
      clock: _clock,
      keepKeys: () async => Set<String>.of(await _loadPins()),
    );
  }

  static const int defaultMaxBytes = 256 * 1024 * 1024;
  static const String folderName = 'library_images';
  static const String _pinsFileName = 'pins.json';

  /// Cache hits record their use at most this often.
  static const Duration _accessRecordInterval = Duration(hours: 1);

  static LibraryImageCache? _instance;

  /// Process-wide instance used by the app. Tests may replace it.
  static LibraryImageCache get instance => _instance ??= LibraryImageCache();
  static set instance(LibraryImageCache value) => _instance = value;

  final int maxBytes;
  final Duration freshFor;
  final Duration requestTimeout;
  final int maxImageBytes;
  final LibraryFetcher? _fetcher;
  final DateTime Function() _clock;
  late final LibraryDiskCache _disk;
  final Map<String, _SharedLoad> _inflight = <String, _SharedLoad>{};
  final LibraryImageCacheStats stats = LibraryImageCacheStats();
  Set<String>? _pins;
  Future<Set<String>>? _pinsLoading;
  Future<void> _pinsWriting = Future<void>.value();

  LibraryFetcher get _fetch => _fetcher ?? LibraryHttp.instance.send;

  /// Returns the encoded bytes of [url] (cache first). Throws
  /// [LibraryNetworkException] when no copy can be obtained. `data:` URIs
  /// are decoded directly.
  Future<Uint8List> load(
    String url, {
    Map<String, String> headers = const <String, String>{},
    LibraryCancelToken? cancel,
  }) {
    final uri = Uri.tryParse(url);
    if (uri == null) {
      return Future<Uint8List>.error(
        const LibraryNetworkException(
          LibraryNetworkErrorKind.invalidResponse,
          detail: 'invalid-url',
        ),
      );
    }
    if (cancel != null && cancel.isCancelled) {
      return Future<Uint8List>.error(
        LibraryNetworkException(LibraryNetworkErrorKind.cancelled, uri: uri),
      );
    }
    if (uri.scheme == 'data') {
      try {
        return Future<Uint8List>.value(uri.data!.contentAsBytes());
      } catch (error) {
        return Future<Uint8List>.error(
          LibraryNetworkException(
            LibraryNetworkErrorKind.invalidResponse,
            detail: 'invalid data URI: $error',
          ),
        );
      }
    }
    if ((uri.scheme != 'http' && uri.scheme != 'https') || uri.host.isEmpty) {
      return Future<Uint8List>.error(
        LibraryNetworkException(
          LibraryNetworkErrorKind.invalidResponse,
          uri: uri,
          detail: 'unsupported-url',
        ),
      );
    }

    var shared = _inflight[url];
    if (shared == null || shared.token.isCancelled) {
      final created = _SharedLoad();
      _inflight[url] = created;
      created.future = _loadShared(url, uri, headers, created.token)
          .whenComplete(() {
            if (identical(_inflight[url], created)) _inflight.remove(url);
          });
      created.future.ignore();
      shared = created;
    } else {
      stats.deduplicated++;
    }
    shared.waiters++;
    if (cancel == null) return shared.future;

    final current = shared;
    final completer = Completer<Uint8List>();
    final unregister = cancel.addCancelListener(() {
      if (completer.isCompleted) return;
      completer.completeError(
        LibraryNetworkException(LibraryNetworkErrorKind.cancelled, uri: uri),
      );
      current.waiters--;
      if (current.waiters <= 0) {
        current.token.cancel();
        if (identical(_inflight[url], current)) _inflight.remove(url);
      }
    });
    current.future.then(
      (bytes) {
        unregister();
        if (!completer.isCompleted) completer.complete(bytes);
      },
      onError: (Object error, StackTrace stackTrace) {
        unregister();
        if (!completer.isCompleted) completer.completeError(error, stackTrace);
      },
    );
    return completer.future;
  }

  /// Whether a usable copy of [url] is on disk ([fresh]: still within
  /// [freshFor]). Does not read the image body.
  Future<bool> isCached(String url, {bool fresh = true}) async {
    final meta = await _disk.readMeta(url);
    if (meta == null) return false;
    if (!fresh) return true;
    final age = _clock().difference(meta.fetchedAt);
    return !age.isNegative && age < freshFor;
  }

  /// Downloads [urls] that are not already fresh on disk, at most
  /// [maxConcurrent] at a time, in order. Failures are ignored; stops early
  /// when [cancel] is cancelled.
  Future<void> prefetch(
    Iterable<String> urls, {
    Map<String, String> headers = const <String, String>{},
    int maxConcurrent = 2,
    LibraryCancelToken? cancel,
  }) async {
    final pending = Queue<String>.of(
      LinkedHashSet<String>.of(urls.where((url) => url.trim().isNotEmpty)),
    );
    if (pending.isEmpty) return;

    Future<void> worker() async {
      while (pending.isNotEmpty) {
        if (cancel != null && cancel.isCancelled) return;
        final url = pending.removeFirst();
        try {
          if (await isCached(url)) continue;
          await load(url, headers: headers, cancel: cancel);
        } catch (_) {
          // Prefetch is best effort; the visible image reports its own error.
        }
      }
    }

    final workers = math.min(math.max(1, maxConcurrent), pending.length);
    await Future.wait(<Future<void>>[
      for (var index = 0; index < workers; index++) worker(),
    ]);
  }

  @override
  Future<void> pin(
    String url, {
    Map<String, String> headers = const <String, String>{},
    bool fetch = false,
  }) async {
    final normalized = url.trim();
    if (normalized.isEmpty) return;
    final pins = await _loadPins();
    if (pins.add(normalized)) await _savePins();
    if (fetch) {
      unawaited(prefetch(<String>[normalized], headers: headers));
    }
  }

  @override
  Future<void> unpin(String url) async {
    final pins = await _loadPins();
    if (pins.remove(url.trim())) await _savePins();
  }

  Future<bool> isPinned(String url) async =>
      (await _loadPins()).contains(url.trim());

  Future<Set<String>> pinnedUrls() async =>
      Set<String>.unmodifiable(await _loadPins());

  /// Size of the image cache on disk in bytes.
  Future<int> cacheSizeBytes() => _disk.sizeBytes();

  /// Deletes least recently used images (never pinned ones) until the cache
  /// fits [maxBytes] (defaults to the configured limit).
  Future<void> trim({int? maxBytes}) async {
    await _disk.trim(maxBytes: maxBytes ?? this.maxBytes);
  }

  /// Removes cached images; pinned images are kept unless [includePinned].
  /// Pins themselves are kept either way.
  Future<void> clear({bool includePinned = false}) =>
      _disk.clear(includeKept: includePinned);

  /// Drops the cached copy of [url].
  Future<void> evict(String url) => _disk.remove(url);

  /// Completes when background trimming triggered by writes is finished.
  Future<void> idle() => _disk.idle();

  Future<Uint8List> _loadShared(
    String url,
    Uri uri,
    Map<String, String> headers,
    LibraryCancelToken token,
  ) async {
    final record = await _disk.read(url);
    token.throwIfCancelled(uri);
    final now = _clock();
    final cachedBody = record?.body;
    if (record != null && cachedBody != null) {
      final age = now.difference(record.fetchedAt);
      if (!age.isNegative && age < freshFor) {
        stats.diskHits++;
        _recordAccess(record, now);
        return cachedBody;
      }
    }

    final requestHeaders = Map<String, String>.of(headers);
    final etag = record?.headers['etag'];
    final lastModified = record?.headers['last-modified'];
    var conditional = false;
    if (record != null && cachedBody != null) {
      if (etag != null && etag.isNotEmpty) {
        requestHeaders['If-None-Match'] = etag;
        conditional = true;
      }
      if (lastModified != null && lastModified.isNotEmpty) {
        requestHeaders['If-Modified-Since'] = lastModified;
        conditional = true;
      }
    }

    try {
      final response = await _fetch(
        LibraryRequest.get(
          uri,
          headers: requestHeaders,
          timeout: requestTimeout,
          maxBytes: maxImageBytes,
          acceptStatuses: conditional ? const <int>{304} : const <int>{},
        ),
        mode: LibraryFetchMode.refresh,
        cancel: token,
      );
      if (response.statusCode == 304) {
        if (record == null || cachedBody == null) {
          throw LibraryNetworkException(
            LibraryNetworkErrorKind.httpStatus,
            uri: response.finalUri,
            statusCode: 304,
          );
        }
        stats.notModified++;
        final refreshed = record.copyWith(
          headers: _mergeValidators(record.headers, response.headers),
          fetchedAt: now,
          lastAccessAt: now,
        );
        final updated = await _disk
            .updateMeta(refreshed)
            .catchError((Object _) => false);
        if (!updated) {
          await _disk.write(refreshed).catchError((Object _) => false);
        }
        return cachedBody;
      }
      final bytes = response.bodyBytes;
      final contentType = response.headers['content-type'];
      if (!looksLikeImage(bytes, contentType: contentType)) {
        throw LibraryNetworkException(
          LibraryNetworkErrorKind.invalidResponse,
          uri: response.finalUri,
          statusCode: response.statusCode,
          detail: 'not an image (${contentType ?? 'no content-type'})',
        );
      }
      stats.networkLoads++;
      await _disk
          .write(
            LibraryCacheRecord(
              key: url,
              url: url,
              finalUrl: response.finalUri.toString(),
              statusCode: response.statusCode,
              headers: LibraryCacheRecord.selectHeaders(response.headers),
              fetchedAt: now,
              lastAccessAt: now,
              size: bytes.length,
              body: bytes,
            ),
          )
          .catchError((Object _) => false);
      return bytes;
    } on LibraryNetworkException catch (error) {
      if (error.kind == LibraryNetworkErrorKind.cancelled) rethrow;
      if (cachedBody != null) {
        stats.staleServed++;
        return cachedBody;
      }
      stats.failures++;
      rethrow;
    }
  }

  void _recordAccess(LibraryCacheRecord record, DateTime now) {
    if (now.difference(record.lastAccessAt).abs() < _accessRecordInterval) {
      return;
    }
    unawaited(_disk.touch(record.key, now).catchError((Object _) => false));
  }

  static Map<String, String> _mergeValidators(
    Map<String, String> stored,
    Map<String, String> notModified,
  ) {
    final merged = Map<String, String>.of(stored);
    for (final name in const <String>['etag', 'last-modified']) {
      final value = notModified[name];
      if (value != null && value.isNotEmpty) merged[name] = value;
    }
    return Map<String, String>.unmodifiable(merged);
  }

  /// Accepts bytes with a known image signature (JPEG, PNG, GIF, WebP, BMP,
  /// ICO, HEIF/AVIF), or any non-empty body declared as `image/*`. Rejects
  /// HTML error or challenge pages served with 200.
  static bool looksLikeImage(List<int> bytes, {String? contentType}) {
    if (bytes.isEmpty) return false;
    if (_hasImageSignature(bytes)) return true;
    final type = contentType?.toLowerCase().trim() ?? '';
    return type.startsWith('image/');
  }

  static bool _hasImageSignature(List<int> b) {
    bool at(int offset, List<int> signature) {
      if (b.length < offset + signature.length) return false;
      for (var index = 0; index < signature.length; index++) {
        if (b[offset + index] != signature[index]) return false;
      }
      return true;
    }

    return at(0, const <int>[0xFF, 0xD8, 0xFF]) ||
        at(0, const <int>[0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]) ||
        at(0, const <int>[0x47, 0x49, 0x46, 0x38]) ||
        (at(0, const <int>[0x52, 0x49, 0x46, 0x46]) &&
            at(8, const <int>[0x57, 0x45, 0x42, 0x50])) ||
        at(0, const <int>[0x42, 0x4D]) ||
        at(0, const <int>[0x00, 0x00, 0x01, 0x00]) ||
        at(4, const <int>[0x66, 0x74, 0x79, 0x70]);
  }

  Future<Set<String>> _loadPins() {
    final loaded = _pins;
    if (loaded != null) return Future<Set<String>>.value(loaded);
    return _pinsLoading ??= _readPins().then((pins) {
      _pins = pins;
      return pins;
    });
  }

  Future<Set<String>> _readPins() async {
    final pins = <String>{};
    try {
      final directory = await _disk.directory();
      if (directory == null) return pins;
      final file = File(p.join(directory.path, _pinsFileName));
      if (!await file.exists()) return pins;
      final decoded = jsonDecode(await file.readAsString());
      final urls = decoded is Map ? decoded['urls'] : null;
      if (urls is List) {
        for (final url in urls) {
          if (url is String && url.trim().isNotEmpty) pins.add(url.trim());
        }
      }
    } catch (_) {
      // An unreadable pin list only loses trimming protection.
    }
    return pins;
  }

  Future<void> _savePins() {
    final next = _pinsWriting.then((_) => _writePins());
    _pinsWriting = next.catchError((Object _) {});
    return _pinsWriting;
  }

  Future<void> _writePins() async {
    final directory = await _disk.directory();
    final pins = _pins;
    if (directory == null || pins == null) return;
    final target = File(p.join(directory.path, _pinsFileName));
    final tmp = File('${target.path}.tmp');
    final sorted = pins.toList()..sort();
    await tmp.writeAsString(
      jsonEncode(<String, Object>{'v': 1, 'urls': sorted}),
      flush: true,
    );
    await tmp.rename(target.path);
  }
}

class _SharedLoad {
  final LibraryCancelToken token = LibraryCancelToken();
  late final Future<Uint8List> future;
  int waiters = 0;
}

/// Network image of the reading Library: loaded through
/// [LibraryImageCache] (disk cache, shared client, request headers such as
/// `Referer`) and decoded at most at [cacheWidth] x [cacheHeight] physical
/// pixels.
///
/// The decode size only ever shrinks the image and keeps its aspect ratio
/// (the image fits inside the given box), so a 1800x2700 page requested
/// with `cacheWidth: 1170` is decoded at 1170x1755. Equality ignores
/// [headers] so that rebuilding a header map does not reload the image.
/// Errors are reported through the image stream, so `errorBuilder` works.
@immutable
class LibraryNetworkImage extends ImageProvider<LibraryNetworkImage> {
  const LibraryNetworkImage(
    this.url, {
    this.headers,
    this.cacheWidth,
    this.cacheHeight,
    this.cache,
  });

  final String url;
  final Map<String, String>? headers;
  final int? cacheWidth;
  final int? cacheHeight;

  /// Cache to load through; defaults to [LibraryImageCache.instance].
  final LibraryImageCache? cache;

  @override
  Future<LibraryNetworkImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<LibraryNetworkImage>(this);

  @override
  ImageStreamCompleter loadImage(
    LibraryNetworkImage key,
    ImageDecoderCallback decode,
  ) {
    return MultiFrameImageStreamCompleter(
      codec: _loadCodec(key, decode),
      scale: 1.0,
      debugLabel: key.url,
      informationCollector: () => <DiagnosticsNode>[
        DiagnosticsProperty<ImageProvider>('Image provider', this),
        DiagnosticsProperty<LibraryNetworkImage>('Image key', key),
      ],
    );
  }

  Future<ui.Codec> _loadCodec(
    LibraryNetworkImage key,
    ImageDecoderCallback decode,
  ) async {
    try {
      final bytes = await (key.cache ?? LibraryImageCache.instance).load(
        key.url,
        headers: key.headers ?? const <String, String>{},
      );
      if (bytes.isEmpty) {
        throw LibraryNetworkException(
          LibraryNetworkErrorKind.invalidResponse,
          uri: Uri.tryParse(key.url),
          detail: 'empty image',
        );
      }
      final buffer = await ui.ImmutableBuffer.fromUint8List(bytes);
      return await decode(
        buffer,
        getTargetSize: (intrinsicWidth, intrinsicHeight) => targetSize(
          intrinsicWidth,
          intrinsicHeight,
          cacheWidth: key.cacheWidth,
          cacheHeight: key.cacheHeight,
        ),
      );
    } catch (_) {
      // Let a later rebuild retry instead of keeping the failure cached.
      scheduleMicrotask(() {
        PaintingBinding.instance.imageCache.evict(key);
      });
      rethrow;
    }
  }

  /// Decode size for an image of [intrinsicWidth] x [intrinsicHeight]:
  /// shrinks to fit inside [cacheWidth] x [cacheHeight] (null = no limit),
  /// keeps the aspect ratio and never upscales.
  static ui.TargetImageSize targetSize(
    int intrinsicWidth,
    int intrinsicHeight, {
    int? cacheWidth,
    int? cacheHeight,
  }) {
    if (intrinsicWidth <= 0 || intrinsicHeight <= 0) {
      return const ui.TargetImageSize();
    }
    var scale = 1.0;
    if (cacheWidth != null && cacheWidth > 0 && cacheWidth < intrinsicWidth) {
      scale = math.min(scale, cacheWidth / intrinsicWidth);
    }
    if (cacheHeight != null &&
        cacheHeight > 0 &&
        cacheHeight < intrinsicHeight) {
      scale = math.min(scale, cacheHeight / intrinsicHeight);
    }
    if (scale >= 1.0) return const ui.TargetImageSize();
    return ui.TargetImageSize(
      width: math.max(1, (intrinsicWidth * scale).round()),
      height: math.max(1, (intrinsicHeight * scale).round()),
    );
  }

  @override
  bool operator ==(Object other) {
    if (other.runtimeType != runtimeType) return false;
    return other is LibraryNetworkImage &&
        other.url == url &&
        other.cacheWidth == cacheWidth &&
        other.cacheHeight == cacheHeight;
  }

  @override
  int get hashCode => Object.hash(url, cacheWidth, cacheHeight);

  @override
  String toString() =>
      '${objectRuntimeType(this, 'LibraryNetworkImage')}'
      '("$url", cacheWidth: $cacheWidth, cacheHeight: $cacheHeight)';
}
