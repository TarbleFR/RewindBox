import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:neostation/services/library_http.dart';
import 'package:path/path.dart' as p;

/// One request received by [_FakeClient].
class _Call {
  _Call(this.request, this.trigger) {
    trigger?.then((_) => aborted = true);
  }

  final http.BaseRequest request;
  final Future<void>? trigger;
  final Completer<void> gate = Completer<void>();
  bool aborted = false;

  Uri get url => request.url;

  String? header(String name) {
    for (final entry in request.headers.entries) {
      if (entry.key.toLowerCase() == name) return entry.value;
    }
    return null;
  }

  String get body => (request as http.Request).body;

  /// Waits for [gate] (or [until]) and throws like a real client when the
  /// request's abort trigger fires first.
  Future<void> wait([Future<void>? until]) {
    final completer = Completer<void>();
    (until ?? gate.future).then((_) {
      if (!completer.isCompleted) completer.complete();
    });
    trigger?.then((_) {
      if (!completer.isCompleted) {
        completer.completeError(http.RequestAbortedException(url));
      }
    });
    return completer.future;
  }
}

typedef _Handler = Future<http.StreamedResponse> Function(_Call call);

/// Fake transport honoring `Abortable.abortTrigger` and recording
/// concurrency per host.
class _FakeClient extends http.BaseClient {
  _FakeClient(this.handler);

  _Handler handler;
  final List<_Call> calls = <_Call>[];
  final Map<String, int> activeByHost = <String, int>{};
  final Map<String, int> maxActiveByHost = <String, int>{};
  int active = 0;
  int maxActive = 0;
  bool closed = false;

  @override
  Future<http.StreamedResponse> send(http.BaseRequest request) async {
    final trigger = request is http.Abortable ? request.abortTrigger : null;
    final call = _Call(request, trigger);
    calls.add(call);
    final host = request.url.host;
    active++;
    maxActive = math.max(maxActive, active);
    activeByHost[host] = (activeByHost[host] ?? 0) + 1;
    maxActiveByHost[host] = math.max(
      maxActiveByHost[host] ?? 0,
      activeByHost[host]!,
    );
    try {
      return await handler(call);
    } finally {
      active--;
      activeByHost[host] = activeByHost[host]! - 1;
    }
  }

  @override
  void close() => closed = true;
}

class _UrlResponse extends http.StreamedResponse
    implements http.BaseResponseWithUrl {
  _UrlResponse(super.stream, super.statusCode, {required this.url});

  @override
  final Uri url;
}

http.StreamedResponse _response(
  int status, {
  Object body = '',
  Map<String, String> headers = const <String, String>{},
  int? contentLength,
}) {
  final bytes = body is List<int> ? body : utf8.encode(body as String);
  return http.StreamedResponse(
    Stream<List<int>>.value(bytes),
    status,
    headers: headers,
    contentLength: contentLength,
  );
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

const LibraryCachePolicy _shortPolicy = LibraryCachePolicy(
  freshFor: Duration(minutes: 10),
  staleFor: Duration(days: 1),
);

void main() {
  late Directory tmp;
  late DateTime now;

  setUp(() async {
    tmp = await Directory.systemTemp.createTemp('library_infra_http_');
    now = DateTime.utc(2026, 10, 10, 12);
  });

  tearDown(() async {
    try {
      await tmp.delete(recursive: true);
    } catch (_) {}
  });

  LibraryHttp create(
    _FakeClient client, {
    int perHost = 3,
    int global = 8,
    int maxCacheBytes = 96 * 1024 * 1024,
    int maxMemoryCacheBytes = 8 * 1024 * 1024,
  }) {
    return LibraryHttp(
      client: client,
      cacheDirectory: tmp,
      clock: () => now,
      maxConcurrentPerHost: perHost,
      maxConcurrentRequests: global,
      maxCacheBytes: maxCacheBytes,
      maxMemoryCacheBytes: maxMemoryCacheBytes,
    );
  }

  Directory cacheDir() =>
      Directory(p.join(tmp.path, LibraryHttp.httpCacheFolderName));

  Future<List<File>> cacheFiles(String extension) async {
    final directory = cacheDir();
    if (!await directory.exists()) return <File>[];
    return directory
        .list()
        .where((entity) => entity is File && entity.path.endsWith(extension))
        .cast<File>()
        .toList();
  }

  group('deduplication and cancellation', () {
    test('cancel listeners run once and can be removed', () async {
      final token = LibraryCancelToken();
      final calls = <String>[];
      final removeA = token.addCancelListener(() => calls.add('a'));
      token.addCancelListener(() => calls.add('b'));
      expect(token.listenerCount, 2);
      removeA();
      expect(token.listenerCount, 1);
      token.cancel();
      token.cancel();
      await Future<void>.delayed(Duration.zero);
      expect(calls, <String>['b']);
      expect(token.listenerCount, 0);
      token.addCancelListener(() => calls.add('late'));
      await Future<void>.delayed(Duration.zero);
      expect(calls, <String>['b', 'late']);
    });

    test(
      'finished requests do not stay attached to a long-lived token',
      () async {
        final client = _FakeClient((call) async => _response(200, body: 'x'));
        final library = create(client);
        final token = LibraryCancelToken();
        for (var index = 0; index < 5; index++) {
          await library.send(
            LibraryRequest.get(Uri.parse('https://a.test/$index')),
            cancel: token,
          );
        }
        client.handler = (call) async => throw const SocketException('down');
        await expectLater(
          library.send(
            LibraryRequest.get(Uri.parse('https://a.test/fail')),
            cancel: token,
          ),
          _networkError(LibraryNetworkErrorKind.offline),
        );
        expect(token.listenerCount, 0);
      },
    );

    test('concurrent identical requests share one network operation', () async {
      final client = _FakeClient((call) async {
        await call.wait();
        return _response(200, body: 'shared');
      });
      final library = create(client);
      final uri = Uri.parse('https://a.test/list');
      final first = library.send(LibraryRequest.get(uri));
      final second = library.send(LibraryRequest.get(uri));
      await _waitFor(() => client.calls.isNotEmpty);
      client.calls.single.gate.complete();

      final responses = await Future.wait(<Future<LibraryHttpResponse>>[
        first,
        second,
      ]);
      expect(responses.map((response) => response.text), <String>[
        'shared',
        'shared',
      ]);
      expect(client.calls, hasLength(1));
      expect(library.stats.networkRequests, 1);
      expect(library.stats.deduplicated, 1);
    });

    test('one caller cancelling does not abort the shared request', () async {
      final client = _FakeClient((call) async {
        await call.wait();
        return _response(200, body: 'still useful');
      });
      final library = create(client);
      final uri = Uri.parse('https://a.test/details');
      final cancelA = LibraryCancelToken();
      final cancelB = LibraryCancelToken();
      final a = library.send(LibraryRequest.get(uri), cancel: cancelA);
      final b = library.send(LibraryRequest.get(uri), cancel: cancelB);
      await _waitFor(() => client.calls.isNotEmpty);

      cancelA.cancel();
      await expectLater(a, _networkError(LibraryNetworkErrorKind.cancelled));
      expect(client.calls.single.aborted, isFalse);

      client.calls.single.gate.complete();
      expect((await b).text, 'still useful');
      expect(library.stats.cancelled, 1);
    });

    test('the socket is aborted when every caller cancelled', () async {
      final client = _FakeClient((call) async {
        await call.wait();
        return _response(200, body: 'late');
      });
      final library = create(client, perHost: 1);
      final uri = Uri.parse('https://a.test/chapter');
      final cancelA = LibraryCancelToken();
      final cancelB = LibraryCancelToken();
      final a = library.send(LibraryRequest.get(uri), cancel: cancelA);
      final b = library.send(LibraryRequest.get(uri), cancel: cancelB);
      await _waitFor(() => client.calls.isNotEmpty);

      cancelA.cancel();
      cancelB.cancel();
      await expectLater(a, _networkError(LibraryNetworkErrorKind.cancelled));
      await expectLater(b, _networkError(LibraryNetworkErrorKind.cancelled));
      await _waitFor(() => client.calls.single.aborted);
      expect(library.stats.cancelled, 2);

      // The aborted request released its host slot.
      client.handler = (call) async => _response(200, body: 'next');
      final next = await library.send(
        LibraryRequest.get(Uri.parse('https://a.test/next')),
      );
      expect(next.text, 'next');
    });

    test(
      'a request cancelled while queued never reaches the network',
      () async {
        final client = _FakeClient((call) async {
          await call.wait();
          return _response(200, body: call.url.path);
        });
        final library = create(client, perHost: 1);
        final first = library.send(
          LibraryRequest.get(Uri.parse('https://a.test/1')),
        );
        final cancel = LibraryCancelToken();
        final second = library.send(
          LibraryRequest.get(Uri.parse('https://a.test/2')),
          cancel: cancel,
        );
        final third = library.send(
          LibraryRequest.get(Uri.parse('https://a.test/3')),
        );
        await _waitFor(() => client.calls.isNotEmpty);
        await Future<void>.delayed(const Duration(milliseconds: 30));
        expect(client.calls, hasLength(1));

        cancel.cancel();
        await expectLater(
          second,
          _networkError(LibraryNetworkErrorKind.cancelled),
        );
        expect(client.calls, hasLength(1));

        client.calls[0].gate.complete();
        expect((await first).text, '/1');
        await _waitFor(() => client.calls.length == 2);
        expect(client.calls[1].url.path, '/3');
        client.calls[1].gate.complete();
        expect((await third).text, '/3');
        expect(library.stats.networkRequests, 2);
      },
    );
  });

  group('concurrency limits', () {
    test('per-host and global limits are FIFO and independent', () async {
      final client = _FakeClient((call) async {
        await call.wait();
        return _response(200, body: '${call.url.host}${call.url.path}');
      });
      final library = create(client, perHost: 2, global: 3);
      final futures = <Future<LibraryHttpResponse>>[
        for (var index = 1; index <= 4; index++)
          library.send(LibraryRequest.get(Uri.parse('https://a.test/$index'))),
        for (var index = 1; index <= 2; index++)
          library.send(LibraryRequest.get(Uri.parse('https://b.test/$index'))),
      ];
      await _waitFor(() => client.calls.length == 3);
      await Future<void>.delayed(const Duration(milliseconds: 30));
      expect(client.calls, hasLength(3));
      expect(client.activeByHost['a.test'], 2);
      expect(client.activeByHost['b.test'], 1);

      var released = 0;
      while (released < 6) {
        await _waitFor(() => client.calls.length > released);
        client.calls[released].gate.complete();
        released++;
      }
      final bodies = (await Future.wait(
        futures,
      )).map((response) => response.text).toList();
      expect(bodies, <String>[
        'a.test/1',
        'a.test/2',
        'a.test/3',
        'a.test/4',
        'b.test/1',
        'b.test/2',
      ]);
      expect(client.maxActiveByHost['a.test'], 2);
      expect(client.maxActive, lessThanOrEqualTo(3));
      // FIFO per host.
      expect(
        client.calls
            .where((call) => call.url.host == 'a.test')
            .map((call) => call.url.path),
        <String>['/1', '/2', '/3', '/4'],
      );
    });

    test('hostLimits overrides the per-host limit', () async {
      final client = _FakeClient((call) async {
        await call.wait();
        return _response(200);
      });
      final library = create(client, perHost: 3);
      library.hostLimits['A.test'] = 1;
      expect(library.hostLimits['a.test'], 1);
      final futures = <Future<LibraryHttpResponse>>[
        for (var index = 0; index < 3; index++)
          library.send(LibraryRequest.get(Uri.parse('https://a.test/$index'))),
      ];
      for (var index = 0; index < 3; index++) {
        await _waitFor(() => client.calls.length > index);
        await Future<void>.delayed(const Duration(milliseconds: 10));
        expect(client.activeByHost['a.test'], 1);
        client.calls[index].gate.complete();
      }
      await Future.wait(futures);
      expect(client.maxActiveByHost['a.test'], 1);

      library.hostLimits.remove('a.test');
      expect(library.hostLimits.containsKey('a.test'), isFalse);
    });
  });

  group('timeouts', () {
    test('a hanging request times out and aborts the socket', () async {
      final client = _FakeClient((call) async {
        await call.wait(Completer<void>().future);
        return _response(200);
      });
      final library = create(client);
      await expectLater(
        library.send(
          LibraryRequest.get(
            Uri.parse('https://a.test/slow'),
            timeout: const Duration(milliseconds: 50),
          ),
        ),
        _networkError(LibraryNetworkErrorKind.timeout),
      );
      await _waitFor(() => client.calls.single.aborted);
      expect(library.stats.failures, 1);
    });

    test('timeout also applies to clients that ignore abort', () async {
      final client = _FakeClient(
        (call) => Completer<http.StreamedResponse>().future,
      );
      final library = create(client);
      await expectLater(
        library.send(
          LibraryRequest.get(
            Uri.parse('https://a.test/stuck'),
            timeout: const Duration(milliseconds: 50),
          ),
        ),
        _networkError(LibraryNetworkErrorKind.timeout),
      );
    });

    test('timeout covers a body that never finishes', () async {
      final controller = StreamController<List<int>>();
      final client = _FakeClient((call) async {
        controller.add(utf8.encode('partial'));
        return http.StreamedResponse(controller.stream, 200);
      });
      final library = create(client);
      await expectLater(
        library.send(
          LibraryRequest.get(
            Uri.parse('https://a.test/trickle'),
            timeout: const Duration(milliseconds: 60),
          ),
        ),
        _networkError(LibraryNetworkErrorKind.timeout),
      );
      expect(controller.hasListener, isFalse);
      await controller.close();
    });
  });

  group('cache freshness and revalidation', () {
    test('ETag: fresh hits skip the network, 304 refreshes', () async {
      final client = _FakeClient((call) async {
        if (call.header('if-none-match') == 'W/"v1"') {
          return _response(304, headers: <String, String>{'etag': 'W/"v1"'});
        }
        return _response(
          200,
          body: '{"sources":1}',
          headers: <String, String>{
            'etag': 'W/"v1"',
            'content-type': 'application/json',
          },
        );
      });
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/index.min.json'),
        cache: _shortPolicy,
      );

      final first = await library.send(request);
      expect(first.fromCache, isFalse);
      expect(first.json(), <String, dynamic>{'sources': 1});

      final second = await library.send(request);
      expect(second.fromCache, isTrue);
      expect(second.stale, isFalse);
      expect(client.calls, hasLength(1));
      expect(library.stats.memoryHits, 1);

      now = now.add(const Duration(minutes: 11));
      final third = await library.send(request);
      expect(client.calls, hasLength(2));
      expect(client.calls[1].header('if-none-match'), 'W/"v1"');
      expect(third.revalidated, isTrue);
      expect(third.fromCache, isTrue);
      expect(third.text, '{"sources":1}');
      expect(third.fetchedAt, now);
      expect(library.stats.notModified, 1);

      now = now.add(const Duration(minutes: 5));
      await library.send(request);
      expect(client.calls, hasLength(2));

      // A new instance reads the revalidated entry from disk.
      final reopened = create(client);
      final fromDisk = await reopened.send(request);
      expect(fromDisk.fromCache, isTrue);
      expect(fromDisk.text, '{"sources":1}');
      expect(reopened.stats.diskHits, 1);
      expect(client.calls, hasLength(2));
    });

    test('Last-Modified: If-Modified-Since revalidation', () async {
      const lastModified = 'Wed, 07 Oct 2026 10:00:00 GMT';
      final client = _FakeClient((call) async {
        if (call.header('if-modified-since') == lastModified) {
          return _response(304);
        }
        return _response(
          200,
          body: 'listing',
          headers: <String, String>{'last-modified': lastModified},
        );
      });
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/latest'),
        cache: _shortPolicy,
      );
      await library.send(request);
      now = now.add(const Duration(minutes: 30));
      final revalidated = await library.send(request);
      expect(client.calls[1].header('if-none-match'), isNull);
      expect(client.calls[1].header('if-modified-since'), lastModified);
      expect(revalidated.revalidated, isTrue);
      expect(revalidated.text, 'listing');
    });

    test('refresh mode asks the network even when fresh', () async {
      var version = 0;
      final client = _FakeClient(
        (call) async => _response(200, body: 'v${++version}'),
      );
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/popular'),
        cache: _shortPolicy,
      );
      expect((await library.send(request)).text, 'v1');
      expect(
        (await library.send(request, mode: LibraryFetchMode.refresh)).text,
        'v2',
      );
      expect((await library.send(request)).text, 'v2');
      expect(client.calls, hasLength(2));
    });

    test('stale fallback on SocketException within the stale window', () async {
      var online = true;
      final client = _FakeClient((call) async {
        if (!online) throw const SocketException('Network is unreachable');
        return _response(200, body: 'cached listing');
      });
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/listing'),
        cache: _shortPolicy,
      );
      await library.send(request);

      online = false;
      now = now.add(const Duration(hours: 2));
      final stale = await library.send(request);
      expect(stale.stale, isTrue);
      expect(stale.fromCache, isTrue);
      expect(stale.text, 'cached listing');
      expect(library.stats.staleServed, 1);

      await expectLater(
        library.send(request, mode: LibraryFetchMode.refresh),
        _networkError(LibraryNetworkErrorKind.offline),
      );

      now = now.add(const Duration(days: 2));
      await expectLater(
        library.send(request),
        _networkError(LibraryNetworkErrorKind.offline),
      );
    });

    test('stale fallback also covers server errors and challenges', () async {
      var status = 200;
      final client = _FakeClient((call) async {
        if (status == 403) {
          return _response(
            403,
            headers: <String, String>{'cf-mitigated': 'challenge'},
          );
        }
        return _response(status, body: status == 200 ? 'ok' : 'down');
      });
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/x'),
        cache: _shortPolicy,
      );
      await library.send(request);
      now = now.add(const Duration(hours: 1));
      status = 503;
      expect((await library.send(request)).stale, isTrue);
      status = 403;
      expect((await library.send(request)).text, 'ok');
      status = 404;
      await expectLater(
        library.send(request),
        _networkError(LibraryNetworkErrorKind.notFound),
      );
    });

    test('cacheOnly never touches the network', () async {
      final client = _FakeClient((call) async => _response(200, body: 'body'));
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/cache-only'),
        cache: _shortPolicy,
      );
      await expectLater(
        library.send(request, mode: LibraryFetchMode.cacheOnly),
        throwsA(
          isA<LibraryNetworkException>()
              .having((e) => e.kind, 'kind', LibraryNetworkErrorKind.notFound)
              .having((e) => e.detail, 'detail', 'cache-miss'),
        ),
      );
      expect(client.calls, isEmpty);

      await library.send(request);
      final hit = await library.send(request, mode: LibraryFetchMode.cacheOnly);
      expect(hit.stale, isFalse);

      now = now.add(const Duration(hours: 3));
      final stale = await library.send(
        request,
        mode: LibraryFetchMode.cacheOnly,
      );
      expect(stale.stale, isTrue);
      expect(await library.readCache(request, allowStale: false), isNull);

      now = now.add(const Duration(days: 3));
      await expectLater(
        library.send(request, mode: LibraryFetchMode.cacheOnly),
        _networkError(LibraryNetworkErrorKind.notFound),
      );
      expect(client.calls, hasLength(1));
    });

    test('memory-only policies are not written to disk', () async {
      final client = _FakeClient((call) async => _response(200, body: 'hits'));
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/search?q=solo'),
        cache: LibraryCachePolicy.search,
      );
      await library.send(request);
      expect((await library.send(request)).fromCache, isTrue);
      expect(await cacheFiles(LibraryDiskCache.bodyExtension), isEmpty);
      final reopened = create(client);
      expect(await reopened.readCache(request), isNull);
    });

    test('POST forms are encoded and cached by body', () async {
      final client = _FakeClient(
        (call) async => _response(200, body: 'echo:${call.body}'),
      );
      final library = create(client);
      LibraryRequest search(String query) => LibraryRequest.postForm(
        Uri.parse('https://a.test/wp-admin/admin-ajax.php'),
        <String, String>{'action': 'madara_load_more', 'vars[s]': query},
        cache: _shortPolicy,
      );

      final first = await library.send(search('solo leveling'));
      expect(client.calls.single.request.method, 'POST');
      expect(
        client.calls.single.header('content-type'),
        startsWith('application/x-www-form-urlencoded'),
      );
      expect(
        first.text,
        'echo:action=madara_load_more&vars%5Bs%5D=solo+leveling',
      );
      expect(search('a').key, isNot(search('b').key));

      expect((await library.send(search('solo leveling'))).fromCache, isTrue);
      expect(client.calls, hasLength(1));
      await library.send(search('one piece'));
      expect(client.calls, hasLength(2));
    });
  });

  group('status and error mapping', () {
    final cases =
        <String, (int, Map<String, String>, String, LibraryNetworkErrorKind)>{
          'cf-mitigated header': (
            403,
            <String, String>{'cf-mitigated': 'challenge'},
            '',
            LibraryNetworkErrorKind.challenge,
          ),
          'just a moment page': (
            403,
            <String, String>{},
            '<html><head><title>Just a moment...</title></head></html>',
            LibraryNetworkErrorKind.challenge,
          ),
          'attention required page': (
            403,
            <String, String>{},
            '<title>Attention Required! | Cloudflare</title>',
            LibraryNetworkErrorKind.challenge,
          ),
          'challenge platform script': (
            403,
            <String, String>{},
            '<script src="/cdn-cgi/challenge-platform/h/b/orchestrate"></script>',
            LibraryNetworkErrorKind.challenge,
          ),
          'plain forbidden': (
            403,
            <String, String>{},
            'Forbidden',
            LibraryNetworkErrorKind.httpStatus,
          ),
          '404': (
            404,
            <String, String>{},
            '',
            LibraryNetworkErrorKind.notFound,
          ),
          '410': (
            410,
            <String, String>{},
            '',
            LibraryNetworkErrorKind.notFound,
          ),
          '500': (
            500,
            <String, String>{},
            '',
            LibraryNetworkErrorKind.serverUnavailable,
          ),
          '504': (
            504,
            <String, String>{},
            '',
            LibraryNetworkErrorKind.serverUnavailable,
          ),
          '522': (
            522,
            <String, String>{},
            '',
            LibraryNetworkErrorKind.serverUnavailable,
          ),
          '429': (
            429,
            <String, String>{},
            '',
            LibraryNetworkErrorKind.httpStatus,
          ),
          '505': (
            505,
            <String, String>{},
            '',
            LibraryNetworkErrorKind.httpStatus,
          ),
        };
    for (final entry in cases.entries) {
      test('maps ${entry.key}', () async {
        final (status, headers, body, kind) = entry.value;
        final client = _FakeClient(
          (call) async => _response(status, body: body, headers: headers),
        );
        final library = create(client);
        await expectLater(
          library.send(LibraryRequest.get(Uri.parse('https://a.test/page'))),
          throwsA(
            isA<LibraryNetworkException>()
                .having((e) => e.kind, 'kind', kind)
                .having((e) => e.statusCode, 'statusCode', status)
                .having((e) => e.host, 'host', 'a.test'),
          ),
        );
        expect(library.stats.failures, 1);
      });
    }

    test('transport errors are typed', () async {
      final errors = <Object, LibraryNetworkErrorKind>{
        const SocketException('Failed host lookup'):
            LibraryNetworkErrorKind.offline,
        const SocketException('HTTP connection timed out after 0:00:10'):
            LibraryNetworkErrorKind.timeout,
        const HandshakeException('CERTIFICATE_VERIFY_FAILED'):
            LibraryNetworkErrorKind.offline,
        const HttpException('Connection closed before full header'):
            LibraryNetworkErrorKind.offline,
        http.ClientException('Connection reset by peer'):
            LibraryNetworkErrorKind.offline,
        TimeoutException('read'): LibraryNetworkErrorKind.timeout,
        StateError('unexpected'): LibraryNetworkErrorKind.invalidResponse,
      };
      for (final entry in errors.entries) {
        final client = _FakeClient((call) async => throw entry.key);
        final library = create(client);
        await expectLater(
          library.send(LibraryRequest.get(Uri.parse('https://a.test/e'))),
          throwsA(
            isA<LibraryNetworkException>()
                .having((e) => e.kind, 'kind', entry.value)
                .having((e) => e.detail, 'detail', isNotEmpty),
          ),
          reason: '${entry.key}',
        );
      }
    });

    test('accepted statuses are returned and not cached', () async {
      final client = _FakeClient(
        (call) async => _response(404, body: 'no more pages'),
      );
      final library = create(client);
      final request = LibraryRequest.get(
        Uri.parse('https://a.test/page/9'),
        cache: _shortPolicy,
        acceptStatuses: const <int>{404},
      );
      final response = await library.send(request);
      expect(response.statusCode, 404);
      expect(response.ok, isFalse);
      expect(response.text, 'no more pages');
      await library.send(request);
      expect(client.calls, hasLength(2));
      expect(library.stats.failures, 0);
    });

    test('maxBytes rejects declared and streamed oversized bodies', () async {
      final big = List<int>.filled(1000, 65);
      var declare = true;
      final client = _FakeClient((call) async {
        if (declare) return _response(200, body: big, contentLength: 1000);
        return http.StreamedResponse(
          Stream<List<int>>.fromIterable(<List<int>>[
            big.sublist(0, 400),
            big.sublist(400),
          ]),
          200,
        );
      });
      final library = create(client);
      LibraryRequest request(int maxBytes) => LibraryRequest.get(
        Uri.parse('https://a.test/big'),
        maxBytes: maxBytes,
      );
      await expectLater(
        library.send(request(100)),
        _networkError(LibraryNetworkErrorKind.tooLarge),
      );
      declare = false;
      await expectLater(
        library.send(request(500)),
        _networkError(LibraryNetworkErrorKind.tooLarge),
      );
      expect((await library.send(request(1000))).bodyBytes, hasLength(1000));
    });

    test('default User-Agent is added, a custom one is kept', () async {
      final client = _FakeClient((call) async => _response(200));
      final library = create(client);
      await library.send(LibraryRequest.get(Uri.parse('https://a.test/1')));
      await library.send(
        LibraryRequest.get(
          Uri.parse('https://a.test/2'),
          headers: const <String, String>{'user-agent': 'Custom/1.0'},
        ),
      );
      expect(
        client.calls[0].header('user-agent'),
        LibraryHttp.defaultUserAgent,
      );
      expect(client.calls[1].header('user-agent'), 'Custom/1.0');
    });

    test('finalUri comes from the redirected response URL', () async {
      final client = _FakeClient(
        (call) async => _UrlResponse(
          Stream<List<int>>.value(utf8.encode('moved')),
          200,
          url: Uri.parse('https://www.a.test/manga/'),
        ),
      );
      final library = create(client);
      final response = await library.send(
        LibraryRequest.get(Uri.parse('https://a.test/manga/')),
      );
      expect(response.finalUri, Uri.parse('https://www.a.test/manga/'));
    });

    test('close ends in-flight requests and rejects new ones', () async {
      final client = _FakeClient((call) async {
        await call.wait();
        return _response(200);
      });
      final library = create(client);
      final pending = library.send(
        LibraryRequest.get(Uri.parse('https://a.test/x')),
      );
      await _waitFor(() => client.calls.isNotEmpty);
      library.close();
      await expectLater(
        pending,
        _networkError(LibraryNetworkErrorKind.cancelled),
      );
      expect(client.closed, isTrue);
      await expectLater(
        library.send(LibraryRequest.get(Uri.parse('https://a.test/y'))),
        _networkError(LibraryNetworkErrorKind.offline),
      );
    });
  });

  group('persistent cache maintenance', () {
    test('trimCache evicts least recently used entries', () async {
      final body = 'x' * 4000;
      final client = _FakeClient((call) async => _response(200, body: body));
      final library = create(client, maxMemoryCacheBytes: 0);
      LibraryRequest request(String name) => LibraryRequest.get(
        Uri.parse('https://a.test/$name'),
        cache: const LibraryCachePolicy(freshFor: Duration(days: 30)),
      );
      await library.send(request('a'));
      now = now.add(const Duration(hours: 1));
      await library.send(request('b'));
      now = now.add(const Duration(hours: 1));
      await library.send(request('c'));
      now = now.add(const Duration(hours: 1));
      // Using "a" makes "b" the least recently used entry.
      expect(await library.readCache(request('a')), isNotNull);
      await library.idle();

      final before = await library.cacheSizeBytes();
      expect(before, greaterThan(12000));
      await library.trimCache(maxBytes: before - 1000);
      expect(await library.cacheSizeBytes(), lessThanOrEqualTo(before - 1000));
      expect(await library.readCache(request('b')), isNull);
      expect(await library.readCache(request('a')), isNotNull);
      expect(await library.readCache(request('c')), isNotNull);
    });

    test('writes beyond the size limit trigger automatic trimming', () async {
      final body = 'y' * 4000;
      final client = _FakeClient((call) async => _response(200, body: body));
      final library = create(
        client,
        maxCacheBytes: 10000,
        maxMemoryCacheBytes: 0,
      );
      for (var index = 0; index < 5; index++) {
        await library.send(
          LibraryRequest.get(
            Uri.parse('https://a.test/$index'),
            cache: const LibraryCachePolicy(freshFor: Duration(days: 1)),
          ),
        );
        now = now.add(const Duration(minutes: 5));
      }
      await library.idle();
      expect(await library.cacheSizeBytes(), lessThanOrEqualTo(10000));
      expect(
        await library.readCache(
          LibraryRequest.get(
            Uri.parse('https://a.test/4'),
            cache: const LibraryCachePolicy(freshFor: Duration(days: 1)),
          ),
        ),
        isNotNull,
      );
    });

    test(
      'corrupt metadata or truncated bodies are misses and deleted',
      () async {
        var served = 0;
        final client = _FakeClient(
          (call) async => _response(200, body: 'payload ${++served}'),
        );
        final request = LibraryRequest.get(
          Uri.parse('https://a.test/entry'),
          cache: _shortPolicy,
        );
        await create(client, maxMemoryCacheBytes: 0).send(request);
        final metas = await cacheFiles(LibraryDiskCache.metaExtension);
        final bodies = await cacheFiles(LibraryDiskCache.bodyExtension);
        expect(metas, hasLength(1));
        expect(bodies, hasLength(1));

        await metas.single.writeAsString('{not json');
        final reopened = create(client, maxMemoryCacheBytes: 0);
        expect(await reopened.readCache(request), isNull);
        expect(await metas.single.exists(), isFalse);
        expect(await bodies.single.exists(), isFalse);

        expect((await reopened.send(request)).text, 'payload 2');
        final body = (await cacheFiles(LibraryDiskCache.bodyExtension)).single;
        await body.writeAsString('pay');
        final again = create(client, maxMemoryCacheBytes: 0);
        expect(await again.readCache(request), isNull);
        expect(await cacheFiles(LibraryDiskCache.metaExtension), isEmpty);
        expect((await again.send(request)).text, 'payload 3');
      },
    );

    test('evict and clearCache remove entries', () async {
      final client = _FakeClient((call) async => _response(200, body: 'z'));
      final library = create(client);
      final first = LibraryRequest.get(
        Uri.parse('https://a.test/1'),
        cache: _shortPolicy,
      );
      final second = LibraryRequest.get(
        Uri.parse('https://a.test/2'),
        cache: _shortPolicy,
      );
      await library.send(first);
      await library.send(second);
      await library.evict(first);
      expect(await library.readCache(first), isNull);
      expect(await library.readCache(second), isNotNull);
      await library.clearCache();
      expect(await library.readCache(second), isNull);
      expect(await library.cacheSizeBytes(), 0);
    });

    test('disk store trim keeps protected keys', () async {
      final store = LibraryDiskCache(
        () async => Directory(p.join(tmp.path, 'store')),
        maxBytes: 1 << 20,
        clock: () => now,
        keepKeys: () async => <String>{'pinned'},
      );
      LibraryCacheRecord record(String key, DateTime at) => LibraryCacheRecord(
        key: key,
        url: 'https://a.test/$key',
        finalUrl: 'https://a.test/$key',
        statusCode: 200,
        headers: const <String, String>{},
        fetchedAt: at,
        lastAccessAt: at,
        size: 2000,
        body: Uint8List(2000),
      );
      await store.write(record('pinned', now));
      await store.write(record('old', now.add(const Duration(minutes: 1))));
      await store.write(record('new', now.add(const Duration(minutes: 2))));
      await store.touch('old', now.add(const Duration(minutes: 3)));
      await store.idle();

      final total = await store.sizeBytes();
      final entry = total ~/ 3;
      // One eviction is enough: "new" goes first because "old" was touched
      // after it was written.
      var remaining = await store.trim(maxBytes: total - entry ~/ 2);
      expect(remaining, lessThanOrEqualTo(total - entry ~/ 2));
      expect(await store.readMeta('new'), isNull);
      expect(await store.readMeta('old'), isNotNull);
      expect(await store.readMeta('pinned'), isNotNull);

      remaining = await store.trim(maxBytes: 0);
      expect(await store.readMeta('old'), isNull);
      expect(await store.readMeta('pinned'), isNotNull);
      expect(remaining, greaterThan(0));

      await store.clear();
      expect(await store.readMeta('pinned'), isNotNull);
      await store.clear(includeKept: true);
      expect(await store.readMeta('pinned'), isNull);
    });
  });

  group('default dart:io client against a loopback server', () {
    late HttpServer server;
    late LibraryHttp library;
    late Completer<void> streamStarted;
    final remotePorts = <int>[];

    /// Streams chunks for a bounded time. The server keeps reading the
    /// socket while it streams, so `connectionsInfo()` sees the client
    /// closing it.
    Future<void> streamSlowly(HttpResponse response) async {
      response.bufferOutput = false;
      response.headers.contentType = ContentType.text;
      final deadline = DateTime.now().add(const Duration(seconds: 10));
      while (DateTime.now().isBefore(deadline) &&
          server.connectionsInfo().total > 0) {
        try {
          response.add(utf8.encode('chunk\n'));
          await response.flush();
        } catch (_) {
          return;
        }
        if (!streamStarted.isCompleted) streamStarted.complete();
        await Future<void>.delayed(const Duration(milliseconds: 20));
      }
    }

    setUp(() async {
      remotePorts.clear();
      streamStarted = Completer<void>();
      server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      server.listen((request) async {
        remotePorts.add(request.connectionInfo!.remotePort);
        switch (request.uri.path) {
          case '/old':
            request.response
              ..statusCode = HttpStatus.movedPermanently
              ..headers.set(HttpHeaders.locationHeader, '/new');
            await request.response.close();
          case '/new':
            request.response.headers.set('content-encoding', 'gzip');
            request.response.add(gzip.encode(utf8.encode('moved here')));
            await request.response.close();
          case '/hang':
            // Never answers; the client must abort the request.
            break;
          case '/etag':
            if (request.headers.value('if-none-match') == '"e1"') {
              request.response.statusCode = HttpStatus.notModified;
            } else {
              request.response.headers.set('etag', '"e1"');
              request.response.write('etag body');
            }
            await request.response.close();
          case '/stream':
            await streamSlowly(request.response);
          default:
            request.response.write('ua=${request.headers.value('user-agent')}');
            await request.response.close();
        }
      });
      library = LibraryHttp(cacheDirectory: tmp);
    });

    tearDown(() async {
      library.close();
      await server.close(force: true);
    });

    Uri local(String path) => Uri.parse('http://127.0.0.1:${server.port}$path');

    test('follows redirects, decompresses and reports finalUri', () async {
      final response = await library.send(LibraryRequest.get(local('/old')));
      expect(response.text, 'moved here');
      expect(response.finalUri, local('/new'));
    });

    test('a 304 revalidation keeps the connection alive', () async {
      final revalidating = LibraryHttp(
        cacheDirectory: tmp,
        clock: () => now,
        maxMemoryCacheBytes: 0,
      );
      addTearDown(revalidating.close);
      final request = LibraryRequest.get(local('/etag'), cache: _shortPolicy);
      expect((await revalidating.send(request)).text, 'etag body');
      now = now.add(const Duration(hours: 1));
      final revalidated = await revalidating.send(request);
      expect(revalidated.revalidated, isTrue);
      expect(revalidated.text, 'etag body');
      await revalidating.send(LibraryRequest.get(local('/after')));
      expect(remotePorts, hasLength(3));
      expect(remotePorts.toSet(), hasLength(1));
    });

    test('reuses the kept-alive connection', () async {
      final first = await library.send(LibraryRequest.get(local('/a')));
      await library.send(LibraryRequest.get(local('/b')));
      expect(first.text, 'ua=${LibraryHttp.defaultUserAgent}');
      expect(remotePorts, hasLength(2));
      expect(remotePorts.toSet(), hasLength(1));
    });

    test('cancelling during the body closes the real socket', () async {
      final cancel = LibraryCancelToken();
      final pending = library.send(
        LibraryRequest.get(local('/stream')),
        cancel: cancel,
      );
      await streamStarted.future.timeout(const Duration(seconds: 5));
      expect(server.connectionsInfo().total, 1);
      cancel.cancel();
      await expectLater(
        pending,
        _networkError(LibraryNetworkErrorKind.cancelled),
      );
      await _waitFor(() => server.connectionsInfo().total == 0);
    });

    test('a timeout during the body closes the real socket', () async {
      await expectLater(
        library.send(
          LibraryRequest.get(
            local('/stream'),
            timeout: const Duration(milliseconds: 150),
          ),
        ),
        _networkError(LibraryNetworkErrorKind.timeout),
      );
      expect(streamStarted.isCompleted, isTrue);
      await _waitFor(() => server.connectionsInfo().total == 0);
    });

    test('cancelling before the response ends the request', () async {
      final cancel = LibraryCancelToken();
      final pending = library.send(
        LibraryRequest.get(local('/hang')),
        cancel: cancel,
      );
      await _waitFor(() => remotePorts.isNotEmpty);
      cancel.cancel();
      await expectLater(
        pending,
        _networkError(LibraryNetworkErrorKind.cancelled),
      );
      // The host slot was released.
      final next = await library.send(LibraryRequest.get(local('/after')));
      expect(next.ok, isTrue);
    });
  });
}
