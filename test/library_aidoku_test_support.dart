// Shared fakes for the Aidoku source tests: an in-memory LibraryFetcher that
// serves the minimized fixtures of test/fixtures/library_aidoku and applies
// the status mapping contract of LibraryHttp, and an Aidoku addon builder.
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_http.dart';

const String aidokuFixtureDir = 'test/fixtures/library_aidoku';

Uint8List aidokuFixture(String name) =>
    File('$aidokuFixtureDir/$name').readAsBytesSync();

LibraryAddon aidokuAddon(String sourceId) {
  return LibraryAddon.fromManifest(<String, dynamic>{
    'schema': LibraryAddon.schemaV1,
    'id': 'aidoku.$sourceId',
    'name': sourceId,
    'version': '1',
    'baseUrl': 'https://example.com/',
    'iosCompatibility': 'metadata-only',
    'provider': <String, dynamic>{
      'type': LibraryAddon.aidokuProviderType,
      'sourceId': sourceId,
      'sourceLang': 'fr',
      'downloadUrl': 'https://example.com/source.aix',
      'repositoryOrigin': 'https://example.com/index.min.json',
    },
  }, origin: 'https://example.com/index.min.json');
}

class FakeRoute {
  FakeRoute({
    required this.method,
    required this.url,
    required this.status,
    required this.body,
    this.headers = const <String, String>{},
    this.form,
    this.cached = false,
    this.delay = Duration.zero,
    this.error,
  });

  final String method;
  final String url;
  final int status;
  final Uint8List body;
  final Map<String, String> headers;

  /// When set, the route only matches a POST whose form contains these
  /// entries.
  final Map<String, String>? form;

  /// Served for [LibraryFetchMode.cacheOnly] (as a stale cache entry).
  final bool cached;
  final Duration delay;
  final LibraryNetworkException? error;

  bool matches(LibraryRequest request) {
    if (request.method != method || request.uri.toString() != url) {
      return false;
    }
    final expected = form;
    if (expected == null) return true;
    final actual = request.form ?? const <String, String>{};
    return expected.entries.every((entry) => actual[entry.key] == entry.value);
  }
}

/// Fetcher double. Unknown requests fail the test with a [StateError] so
/// every network access of the code under test is explicit.
class FakeLibraryFetcher {
  FakeLibraryFetcher({DateTime? now})
    : now = now ?? DateTime.utc(2026, 10, 10, 21);

  final DateTime now;
  final List<FakeRoute> _routes = <FakeRoute>[];
  final List<LibraryRequest> requests = <LibraryRequest>[];
  final List<LibraryFetchMode> modes = <LibraryFetchMode>[];

  void get(
    String url, {
    String? fixture,
    String? body,
    Uint8List? bytes,
    int status = 200,
    Map<String, String> headers = const <String, String>{
      'content-type': 'text/html; charset=UTF-8',
    },
    bool cached = false,
    Duration delay = Duration.zero,
    LibraryNetworkException? error,
  }) => _add(
    'GET',
    url,
    fixture: fixture,
    body: body,
    bytes: bytes,
    status: status,
    headers: headers,
    cached: cached,
    delay: delay,
    error: error,
  );

  void post(
    String url, {
    Map<String, String>? form,
    String? fixture,
    String? body,
    int status = 200,
    Map<String, String> headers = const <String, String>{
      'content-type': 'text/html; charset=UTF-8',
    },
    LibraryNetworkException? error,
  }) => _add(
    'POST',
    url,
    form: form,
    fixture: fixture,
    body: body,
    status: status,
    headers: headers,
    error: error,
  );

  void _add(
    String method,
    String url, {
    Map<String, String>? form,
    String? fixture,
    String? body,
    Uint8List? bytes,
    required int status,
    required Map<String, String> headers,
    bool cached = false,
    Duration delay = Duration.zero,
    LibraryNetworkException? error,
  }) {
    _routes.add(
      FakeRoute(
        method: method,
        url: url,
        status: status,
        body:
            bytes ??
            (fixture != null
                ? aidokuFixture(fixture)
                : Uint8List.fromList(utf8.encode(body ?? ''))),
        headers: headers,
        form: form,
        cached: cached,
        delay: delay,
        error: error,
      ),
    );
  }

  List<LibraryRequest> requestsTo(String url) =>
      requests.where((request) => request.uri.toString() == url).toList();

  Future<LibraryHttpResponse> call(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    cancel?.throwIfCancelled(request.uri);
    requests.add(request);
    modes.add(mode);
    final route = _routes.cast<FakeRoute?>().firstWhere(
      (candidate) => candidate!.matches(request),
      orElse: () => null,
    );
    if (route == null) {
      throw StateError(
        'Unexpected ${request.method} ${request.uri} ${request.form ?? ''}',
      );
    }
    if (mode == LibraryFetchMode.cacheOnly && !route.cached) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.notFound,
        uri: request.uri,
        detail: 'cache-miss',
      );
    }
    if (route.delay > Duration.zero) await Future<void>.delayed(route.delay);
    cancel?.throwIfCancelled(request.uri);
    if (route.error != null) throw route.error!;
    final status = route.status;
    final ok = status >= 200 && status < 300;
    if (!ok && !request.acceptStatuses.contains(status)) {
      throw LibraryNetworkException(
        _kindFor(status, route),
        uri: request.uri,
        statusCode: status,
      );
    }
    return LibraryHttpResponse(
      request: request,
      statusCode: status,
      bodyBytes: route.body,
      headers: route.headers,
      finalUri: request.uri,
      fetchedAt: now,
      fromCache: mode == LibraryFetchMode.cacheOnly,
      stale: mode == LibraryFetchMode.cacheOnly,
    );
  }

  /// Status mapping contract of LibraryHttp (design.md).
  static LibraryNetworkErrorKind _kindFor(int status, FakeRoute route) {
    final body = utf8.decode(route.body, allowMalformed: true);
    if (status == 403 &&
        (route.headers['cf-mitigated'] == 'challenge' ||
            body.contains('<title>Just a moment...</title>') ||
            body.contains('Attention Required! | Cloudflare'))) {
      return LibraryNetworkErrorKind.challenge;
    }
    if (status == 404 || status == 410) return LibraryNetworkErrorKind.notFound;
    if ((status >= 500 && status <= 504) || (status >= 520 && status <= 530)) {
      return LibraryNetworkErrorKind.serverUnavailable;
    }
    return LibraryNetworkErrorKind.httpStatus;
  }
}
