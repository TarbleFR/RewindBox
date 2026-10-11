import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';

const List<int> _pngSignature = <int>[
  0x89,
  0x50,
  0x4E,
  0x47,
  0x0D,
  0x0A,
  0x1A,
  0x0A,
];

/// Bytes that pass the image signature check (not decodable).
Uint8List _fakeImage(int seed, {int size = 2048}) {
  final bytes = Uint8List(size);
  bytes.setAll(0, _pngSignature);
  for (var index = _pngSignature.length; index < size; index++) {
    bytes[index] = (index * 31 + seed) & 0xFF;
  }
  return bytes;
}

int _crc32(List<int> bytes) {
  var crc = 0xFFFFFFFF;
  for (final byte in bytes) {
    crc ^= byte;
    for (var bit = 0; bit < 8; bit++) {
      crc = (crc & 1) != 0 ? (crc >> 1) ^ 0xEDB88320 : crc >> 1;
    }
  }
  return crc ^ 0xFFFFFFFF;
}

List<int> _u32(int value) => <int>[
  (value >> 24) & 0xFF,
  (value >> 16) & 0xFF,
  (value >> 8) & 0xFF,
  value & 0xFF,
];

/// A real, decodable RGBA PNG of [width] x [height].
Uint8List _png(int width, int height) {
  final raw = BytesBuilder();
  for (var y = 0; y < height; y++) {
    raw.addByte(0);
    for (var x = 0; x < width; x++) {
      raw.add(<int>[x & 0xFF, y & 0xFF, 128, 255]);
    }
  }
  final out = BytesBuilder()..add(_pngSignature);
  void chunk(String type, List<int> data) {
    final typed = <int>[...ascii.encode(type), ...data];
    out
      ..add(_u32(data.length))
      ..add(typed)
      ..add(_u32(_crc32(typed)));
  }

  chunk('IHDR', <int>[..._u32(width), ..._u32(height), 8, 6, 0, 0, 0]);
  chunk('IDAT', ZLibCodec().encode(raw.takeBytes()));
  chunk('IEND', const <int>[]);
  return out.takeBytes();
}

typedef _FetchHandler =
    Future<LibraryHttpResponse> Function(
      LibraryRequest request,
      LibraryCancelToken? cancel,
    );

/// [LibraryFetcher] fake recording requests and concurrency.
class _FakeFetcher {
  _FakeFetcher(this.handler);

  _FetchHandler handler;
  final List<LibraryRequest> requests = <LibraryRequest>[];
  final List<LibraryCancelToken?> tokens = <LibraryCancelToken?>[];
  int active = 0;
  int maxActive = 0;

  Future<LibraryHttpResponse> call(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    requests.add(request);
    tokens.add(cancel);
    active++;
    maxActive = math.max(maxActive, active);
    try {
      return await handler(request, cancel);
    } finally {
      active--;
    }
  }
}

LibraryHttpResponse _ok(
  LibraryRequest request,
  List<int> bytes, {
  int status = 200,
  Map<String, String> headers = const <String, String>{
    'content-type': 'image/png',
  },
}) {
  return LibraryHttpResponse(
    request: request,
    statusCode: status,
    bodyBytes: Uint8List.fromList(bytes),
    headers: headers,
    finalUri: request.uri,
    fetchedAt: DateTime.utc(2026),
  );
}

/// Completes with [gate] unless [cancel] fires first.
Future<void> _gateOrCancel(Future<void> gate, LibraryCancelToken? cancel) {
  final completer = Completer<void>();
  gate.then((_) {
    if (!completer.isCompleted) completer.complete();
  });
  cancel?.whenCancelled.then((_) {
    if (!completer.isCompleted) {
      completer.completeError(
        const LibraryNetworkException(LibraryNetworkErrorKind.cancelled),
      );
    }
  });
  return completer.future;
}

Future<void> _waitFor(
  bool Function() condition, {
  Duration timeout = const Duration(seconds: 5),
}) async {
  final deadline = DateTime.now().add(timeout);
  while (!condition()) {
    if (DateTime.now().isAfter(deadline)) {
      throw TimeoutException('condition not reached');
    }
    await Future<void>.delayed(const Duration(milliseconds: 5));
  }
}

Matcher _networkError(LibraryNetworkErrorKind kind) => throwsA(
  isA<LibraryNetworkException>().having((error) => error.kind, 'kind', kind),
);

void main() {
  late Directory tmp;
  late DateTime now;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('library_infra_images_');
    now = DateTime.utc(2026, 10, 10, 12);
  });

  tearDown(() async {
    try {
      await tmp.delete(recursive: true);
    } catch (_) {}
  });

  LibraryImageCache create(_FakeFetcher fetcher, {int maxBytes = 1 << 24}) {
    return LibraryImageCache(
      fetcher: fetcher.call,
      cacheDirectory: tmp,
      clock: () => now,
      maxBytes: maxBytes,
    );
  }

  group('LibraryImageCache', () {
    test('serves later loads from disk, across instances', () async {
      final image = _fakeImage(1);
      final fetcher = _FakeFetcher((request, cancel) async {
        return _ok(request, image);
      });
      final cache = create(fetcher);
      const url = 'https://img.test/covers/1.webp';
      expect(
        await cache.load(
          url,
          headers: const <String, String>{'Referer': 'https://a.test/'},
        ),
        image,
      );
      expect(fetcher.requests.single.headers['Referer'], 'https://a.test/');
      expect(fetcher.requests.single.cache.isCacheable, isFalse);

      final reopened = create(fetcher);
      expect(await reopened.load(url), image);
      expect(fetcher.requests, hasLength(1));
      expect(reopened.stats.diskHits, 1);
      expect(await reopened.isCached(url), isTrue);
    });

    test('concurrent loads of one URL share one download', () async {
      final gate = Completer<void>();
      final fetcher = _FakeFetcher((request, cancel) async {
        await _gateOrCancel(gate.future, cancel);
        return _ok(request, _fakeImage(2));
      });
      final cache = create(fetcher);
      const url = 'https://img.test/pages/1.jpg';
      final loads = <Future<Uint8List>>[
        cache.load(url),
        cache.load(url),
        cache.load(url),
      ];
      await _waitFor(() => fetcher.requests.isNotEmpty);
      gate.complete();
      final results = await Future.wait(loads);
      expect(results.toSet().length, 1);
      expect(fetcher.requests, hasLength(1));
      expect(cache.stats.deduplicated, 2);
    });

    test('each caller cancels independently', () async {
      final gate = Completer<void>();
      final fetcher = _FakeFetcher((request, cancel) async {
        await _gateOrCancel(gate.future, cancel);
        return _ok(request, _fakeImage(3));
      });
      final cache = create(fetcher);
      const url = 'https://img.test/pages/2.jpg';
      final cancelA = LibraryCancelToken();
      final a = cache.load(url, cancel: cancelA);
      final b = cache.load(url, cancel: LibraryCancelToken());
      await _waitFor(() => fetcher.requests.isNotEmpty);
      cancelA.cancel();
      await expectLater(a, _networkError(LibraryNetworkErrorKind.cancelled));
      expect(fetcher.tokens.single!.isCancelled, isFalse);
      gate.complete();
      expect(await b, _fakeImage(3));

      // When the only caller cancels, the download itself is cancelled.
      final never = Completer<void>();
      fetcher.handler = (request, cancel) async {
        await _gateOrCancel(never.future, cancel);
        return _ok(request, _fakeImage(4));
      };
      final cancelC = LibraryCancelToken();
      final c = cache.load('https://img.test/pages/3.jpg', cancel: cancelC);
      await _waitFor(() => fetcher.requests.length == 2);
      cancelC.cancel();
      await expectLater(c, _networkError(LibraryNetworkErrorKind.cancelled));
      expect(fetcher.tokens.last!.isCancelled, isTrue);
      expect(await cache.isCached('https://img.test/pages/3.jpg'), isFalse);
    });

    test('revalidates after 30 days with the stored validators', () async {
      final image = _fakeImage(5);
      final fetcher = _FakeFetcher((request, cancel) async {
        if (request.headers['If-None-Match'] == '"cover-v1"') {
          return _ok(request, const <int>[], status: 304);
        }
        return _ok(
          request,
          image,
          headers: const <String, String>{
            'content-type': 'image/webp',
            'etag': '"cover-v1"',
            'last-modified': 'Mon, 05 Oct 2026 08:00:00 GMT',
          },
        );
      });
      final cache = create(fetcher);
      const url = 'https://img.test/covers/5.webp';
      await cache.load(url);

      now = now.add(const Duration(days: 29));
      await cache.load(url);
      expect(fetcher.requests, hasLength(1));

      now = now.add(const Duration(days: 2));
      expect(await cache.load(url), image);
      expect(fetcher.requests, hasLength(2));
      final conditional = fetcher.requests.last;
      expect(conditional.headers['If-None-Match'], '"cover-v1"');
      expect(
        conditional.headers['If-Modified-Since'],
        'Mon, 05 Oct 2026 08:00:00 GMT',
      );
      expect(conditional.acceptStatuses, contains(304));
      expect(cache.stats.notModified, 1);

      // The revalidation restarted the freshness window.
      now = now.add(const Duration(days: 10));
      await cache.load(url);
      expect(fetcher.requests, hasLength(2));
    });

    test('serves the cached copy when the network fails', () async {
      final image = _fakeImage(6);
      var online = true;
      final fetcher = _FakeFetcher((request, cancel) async {
        if (!online) {
          throw LibraryNetworkException(
            LibraryNetworkErrorKind.offline,
            uri: request.uri,
          );
        }
        return _ok(request, image);
      });
      final cache = create(fetcher);
      const url = 'https://img.test/covers/6.png';
      await cache.load(url);
      online = false;
      now = now.add(const Duration(days: 90));
      expect(await cache.load(url), image);
      expect(cache.stats.staleServed, 1);
      await expectLater(
        cache.load('https://img.test/covers/never-cached.png'),
        _networkError(LibraryNetworkErrorKind.offline),
      );
    });

    test('rejects HTML served instead of an image', () async {
      final fetcher = _FakeFetcher((request, cancel) async {
        return _ok(
          request,
          utf8.encode('<html><title>Just a moment...</title></html>'),
          headers: const <String, String>{'content-type': 'text/html'},
        );
      });
      final cache = create(fetcher);
      const url = 'https://img.test/covers/blocked.jpg';
      await expectLater(
        cache.load(url),
        _networkError(LibraryNetworkErrorKind.invalidResponse),
      );
      expect(await cache.isCached(url), isFalse);
      expect(
        LibraryImageCache.looksLikeImage(const <int>[
          1,
          2,
          3,
        ], contentType: 'image/avif'),
        isTrue,
      );
      expect(LibraryImageCache.looksLikeImage(_png(2, 2)), isTrue);
    });

    test('pinned images survive trimming and pins persist', () async {
      final fetcher = _FakeFetcher((request, cancel) async {
        return _ok(request, _fakeImage(request.uri.path.length, size: 4096));
      });
      final cache = create(fetcher);
      const pinned = 'https://img.test/favourite.jpg';
      await cache.load(pinned);
      now = now.add(const Duration(minutes: 1));
      await cache.load('https://img.test/a.jpg');
      now = now.add(const Duration(minutes: 1));
      await cache.load('https://img.test/b.jpg');
      await cache.pin(pinned);
      await cache.idle();

      await cache.trim(maxBytes: 1);
      expect(await cache.isCached(pinned), isTrue);
      expect(await cache.isCached('https://img.test/a.jpg'), isFalse);
      expect(await cache.isCached('https://img.test/b.jpg'), isFalse);

      final reopened = create(fetcher);
      expect(await reopened.isPinned(pinned), isTrue);
      await reopened.clear();
      expect(await reopened.isCached(pinned), isTrue);
      await reopened.unpin(pinned);
      expect(await reopened.isPinned(pinned), isFalse);
      await reopened.trim(maxBytes: 1);
      expect(await reopened.isCached(pinned), isFalse);
    });

    test('automatic trimming keeps the cache under its limit', () async {
      final fetcher = _FakeFetcher((request, cancel) async {
        return _ok(request, _fakeImage(9, size: 4096));
      });
      final cache = create(fetcher, maxBytes: 12000);
      await cache.pin('https://img.test/0.jpg');
      for (var index = 0; index < 6; index++) {
        await cache.load('https://img.test/$index.jpg');
        now = now.add(const Duration(minutes: 1));
      }
      await cache.idle();
      expect(await cache.cacheSizeBytes(), lessThanOrEqualTo(12000));
      expect(await cache.isCached('https://img.test/0.jpg'), isTrue);
      expect(await cache.isCached('https://img.test/5.jpg'), isTrue);
    });

    test(
      'prefetch is bounded, skips cached images and ignores errors',
      () async {
        final gates = <String, Completer<void>>{};
        final fetcher = _FakeFetcher((request, cancel) async {
          final gate = gates.putIfAbsent(
            request.uri.toString(),
            () => Completer<void>(),
          );
          await _gateOrCancel(gate.future, cancel);
          if (request.uri.path.contains('broken')) {
            throw LibraryNetworkException(
              LibraryNetworkErrorKind.notFound,
              uri: request.uri,
            );
          }
          return _ok(request, _fakeImage(request.uri.path.length));
        });
        final cache = create(fetcher);
        final urls = <String>[
          for (var index = 0; index < 5; index++)
            'https://img.test/p$index.jpg',
          'https://img.test/broken.jpg',
        ];
        final done = cache.prefetch(urls, maxConcurrent: 2);
        var released = 0;
        while (released < urls.length) {
          await _waitFor(() => gates.length > released);
          expect(fetcher.active, lessThanOrEqualTo(2));
          gates.values.elementAt(released).complete();
          released++;
        }
        await done;
        expect(fetcher.maxActive, 2);
        for (final url in urls.take(5)) {
          expect(await cache.isCached(url), isTrue);
        }

        await cache.prefetch(urls.take(5));
        expect(fetcher.requests, hasLength(urls.length));
      },
    );

    test('http image URLs are downloaded over https only', () async {
      final image = _fakeImage(3);
      final fetcher = _FakeFetcher((request, cancel) async {
        return _ok(request, image);
      });
      final cache = create(fetcher);
      const url = 'http://img.test/covers/a.jpg';

      expect(await cache.load(url), image);
      expect(
        fetcher.requests.single.uri,
        Uri.parse('https://img.test/covers/a.jpg'),
      );
      // Cached under the address the source gave, so favourites' pins and
      // later loads of the same URL find it.
      expect(await cache.isCached(url), isTrue);
      expect(await cache.load(url), image);
      expect(fetcher.requests, hasLength(1));

      expect(
        LibraryImageCache.secureImageUri(Uri.parse('http://img.test:80/x.png')),
        Uri.parse('https://img.test/x.png'),
      );
      expect(
        LibraryImageCache.secureImageUri(Uri.parse('https://img.test/x.png')),
        Uri.parse('https://img.test/x.png'),
      );
    });

    test('data URIs are decoded without network access', () async {
      final fetcher = _FakeFetcher((request, cancel) async {
        fail('no network expected');
      });
      final cache = create(fetcher);
      final png = _png(1, 1);
      final bytes = await cache.load(
        Uri.dataFromBytes(png, mimeType: 'image/png').toString(),
      );
      expect(bytes, png);
    });

    test('conditional requests work through LibraryHttp', () async {
      final image = _fakeImage(7);
      final seen = <String?>[];
      final client = _MockClient((request) async {
        seen.add(request.headers['If-None-Match']);
        if (request.headers['If-None-Match'] == 'W/"img"') {
          return http.StreamedResponse(const Stream<List<int>>.empty(), 304);
        }
        return http.StreamedResponse(
          Stream<List<int>>.value(image),
          200,
          headers: const <String, String>{
            'etag': 'W/"img"',
            'content-type': 'image/jpeg',
          },
        );
      });
      final library = LibraryHttp(
        client: client,
        cacheDirectory: tmp,
        clock: () => now,
      );
      final cache = LibraryImageCache(
        fetcher: library.send,
        cacheDirectory: tmp,
        clock: () => now,
      );
      const url = 'https://img.test/through-http.jpg';
      expect(await cache.load(url), image);
      now = now.add(const Duration(days: 31));
      expect(await cache.load(url), image);
      expect(seen, <String?>[null, 'W/"img"']);
      expect(cache.stats.notModified, 1);
      expect(await library.cacheSizeBytes(), 0);
    });
  });

  group('LibraryNetworkImage', () {
    test('target size only shrinks and keeps the aspect ratio', () {
      final page = LibraryNetworkImage.targetSize(1800, 2700, cacheWidth: 1170);
      expect(page.width, 1170);
      expect(page.height, 1755);

      final small = LibraryNetworkImage.targetSize(300, 450, cacheWidth: 1170);
      expect(small.width, isNull);
      expect(small.height, isNull);

      final boxed = LibraryNetworkImage.targetSize(
        3840,
        3016,
        cacheWidth: 1170,
        cacheHeight: 600,
      );
      expect(boxed.height, 600);
      expect(boxed.width, (3840 * 600 / 3016).round());

      final none = LibraryNetworkImage.targetSize(800, 600);
      expect(none.width, isNull);
    });

    test('equality ignores headers', () {
      const a = LibraryNetworkImage(
        'https://img.test/x.jpg',
        headers: <String, String>{'Referer': 'https://a.test/'},
        cacheWidth: 300,
      );
      const b = LibraryNetworkImage(
        'https://img.test/x.jpg',
        headers: <String, String>{'Referer': 'https://b.test/'},
        cacheWidth: 300,
      );
      const c = LibraryNetworkImage('https://img.test/x.jpg', cacheWidth: 600);
      expect(a, b);
      expect(a.hashCode, b.hashCode);
      expect(a, isNot(c));
    });

    testWidgets('decodes downloaded images at the requested size', (
      tester,
    ) async {
      final png = _png(300, 450);
      final fetcher = _FakeFetcher((request, cancel) async {
        return _ok(request, png);
      });
      final cache = create(fetcher);
      imageCache.clear();

      Future<ui.Image> resolve(ImageProvider provider) {
        final completer = Completer<ui.Image>();
        final stream = provider.resolve(ImageConfiguration.empty);
        late final ImageStreamListener listener;
        listener = ImageStreamListener(
          (info, _) {
            if (!completer.isCompleted) completer.complete(info.image);
            stream.removeListener(listener);
          },
          onError: (error, stackTrace) {
            if (!completer.isCompleted) {
              completer.completeError(error, stackTrace);
            }
          },
        );
        stream.addListener(listener);
        return completer.future;
      }

      final shrunk = await tester.runAsync(
        () => resolve(
          LibraryNetworkImage(
            'https://img.test/page.png',
            cacheWidth: 120,
            cache: cache,
          ),
        ),
      );
      expect(shrunk!.width, 120);
      expect(shrunk.height, 180);

      final notUpscaled = await tester.runAsync(
        () => resolve(
          LibraryNetworkImage(
            'https://img.test/page.png',
            cacheWidth: 600,
            cache: cache,
          ),
        ),
      );
      expect(notUpscaled!.width, 300);
      expect(notUpscaled.height, 450);

      final boxed = await tester.runAsync(
        () => resolve(
          LibraryNetworkImage(
            'https://img.test/page.png',
            cacheWidth: 100,
            cacheHeight: 100,
            cache: cache,
          ),
        ),
      );
      expect(boxed!.height, 100);
      expect(boxed.width, 67);
      expect(fetcher.requests, hasLength(1));
      imageCache.clear();
    });

    testWidgets('undecodable bytes are not kept in the disk cache', (
      tester,
    ) async {
      final fetcher = _FakeFetcher((request, cancel) async {
        // An error page mislabelled as JPEG passes the content-type check.
        return _ok(
          request,
          utf8.encode('<html><body>image not found</body></html>'),
          headers: const <String, String>{'content-type': 'image/jpeg'},
        );
      });
      final cache = create(fetcher);
      imageCache.clear();
      const url = 'https://img.test/mislabelled.jpg';
      final outcome = await tester.runAsync(() async {
        final completer = Completer<Object>();
        LibraryNetworkImage(url, cache: cache)
            .resolve(ImageConfiguration.empty)
            .addListener(
              ImageStreamListener(
                (info, _) {
                  if (!completer.isCompleted) completer.complete('decoded');
                },
                onError: (error, _) {
                  if (!completer.isCompleted) completer.complete(error);
                },
              ),
            );
        final result = await completer.future;
        // The disk eviction runs in the background after the error.
        for (var attempt = 0; attempt < 100; attempt++) {
          if (!await cache.isCached(url)) break;
          await Future<void>.delayed(const Duration(milliseconds: 10));
        }
        return (result, await cache.isCached(url));
      });
      final (error, stillCached) = outcome!;
      expect(error, isNot('decoded'));
      expect(fetcher.requests, hasLength(1));
      expect(stillCached, isFalse);
      imageCache.clear();
    });

    testWidgets('load failures reach errorBuilder', (tester) async {
      final fetcher = _FakeFetcher((request, cancel) async {
        throw LibraryNetworkException(
          LibraryNetworkErrorKind.notFound,
          uri: request.uri,
          statusCode: 404,
        );
      });
      final cache = create(fetcher);
      imageCache.clear();
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: Image(
            image: LibraryNetworkImage(
              'https://img.test/missing.png',
              cache: cache,
            ),
            errorBuilder: (context, error, stackTrace) => Text(
              error is LibraryNetworkException
                  ? 'failed ${error.kind.name}'
                  : 'failed $error',
            ),
          ),
        ),
      );
      for (var attempt = 0; attempt < 100; attempt++) {
        await tester.runAsync(
          () => Future<void>.delayed(const Duration(milliseconds: 10)),
        );
        await tester.pump();
        if (find.text('failed notFound').evaluate().isNotEmpty) break;
      }
      expect(find.text('failed notFound'), findsOneWidget);
      // The failed key was evicted so a later rebuild can retry.
      expect(
        imageCache.containsKey(
          LibraryNetworkImage('https://img.test/missing.png', cache: cache),
        ),
        isFalse,
      );
    });
  });
}

class _MockClient extends http.BaseClient {
  _MockClient(this.handler);

  final Future<http.StreamedResponse> Function(http.BaseRequest request)
  handler;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) =>
      handler(request);
}
