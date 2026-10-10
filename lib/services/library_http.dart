import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:http/http.dart' as http;

/// Shared network layer of the reading Library (Build 437).
///
/// Every Library request (source catalogues, manga pages, catalogue indexes,
/// covers) goes through [LibraryHttp] so that:
/// * one keep-alive client is reused instead of one client per request;
/// * concurrency is bounded per host and globally;
/// * identical in-flight requests are shared (deduplicated);
/// * superseded work can be cancelled ([LibraryCancelToken]);
/// * responses can be kept in a size-limited persistent cache with
///   freshness rules, `ETag` / `Last-Modified` revalidation and stale
///   fallback when the network fails;
/// * failures are typed ([LibraryNetworkException]) so the UI can show a
///   translated explanation while keeping the raw technical detail.
///
/// The cache only ever stores network responses. It never contains imported
/// books, favourites or reading progress, so trimming or clearing it cannot
/// lose user data.

/// Reason a Library request failed.
enum LibraryNetworkErrorKind {
  /// No connection, DNS failure, TLS failure or connection reset.
  offline,

  /// The request (or the whole response body) took longer than allowed.
  timeout,

  /// The caller cancelled the request through a [LibraryCancelToken].
  cancelled,

  /// The site answered with an anti-bot browser verification
  /// (e.g. Cloudflare `cf-mitigated: challenge`, "Just a moment...",
  /// "Attention Required! | Cloudflare"). Never retried automatically.
  challenge,

  /// The origin is down or overloaded (HTTP 500-504, Cloudflare 520-530).
  serverUnavailable,

  /// HTTP 404 / 410.
  notFound,

  /// Any other non-success HTTP status.
  httpStatus,

  /// The body exceeded the request's size limit.
  tooLarge,

  /// The body could not be decoded/parsed as expected.
  invalidResponse,
}

class LibraryNetworkException implements Exception {
  const LibraryNetworkException(
    this.kind, {
    this.uri,
    this.statusCode,
    this.detail,
  });

  final LibraryNetworkErrorKind kind;
  final Uri? uri;
  final int? statusCode;

  /// Raw technical detail (English, untranslated). Shown separately from the
  /// translated explanation, never as the only user message.
  final String? detail;

  String get host => uri?.host ?? '';

  @override
  String toString() {
    final parts = <String>[
      kind.name,
      if (host.isNotEmpty) host,
      if (statusCode != null) 'HTTP $statusCode',
      if (detail != null && detail!.isNotEmpty) detail!,
    ];
    return 'LibraryNetworkException(${parts.join(', ')})';
  }
}

/// Cooperative cancellation shared by every request started for one user
/// action (a search, a source page, a chapter). Cancelling aborts the
/// underlying socket when no other caller still waits for the same request.
class LibraryCancelToken {
  final Completer<void> _completer = Completer<void>();

  bool get isCancelled => _completer.isCompleted;

  /// Completes when [cancel] is called.
  Future<void> get whenCancelled => _completer.future;

  void cancel() {
    if (!_completer.isCompleted) _completer.complete();
  }

  void throwIfCancelled([Uri? uri]) {
    if (isCancelled) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.cancelled,
        uri: uri,
      );
    }
  }
}

/// Freshness rules for one request.
///
/// A cached response younger than [freshFor] is returned without any network
/// access. Older responses are revalidated (`If-None-Match` /
/// `If-Modified-Since` when the server supplied validators). A response
/// younger than [freshFor] + [staleFor] may still be returned, marked
/// [LibraryHttpResponse.stale], when the network fails or when the caller
/// explicitly asks for cached data ([LibraryFetchMode.cacheOnly]).
class LibraryCachePolicy {
  const LibraryCachePolicy({
    required this.freshFor,
    this.staleFor = Duration.zero,
    this.persist = true,
  });

  final Duration freshFor;
  final Duration staleFor;

  /// Store on disk (survives app restarts). When false the response is only
  /// kept in the in-memory cache for the current session.
  final bool persist;

  bool get isCacheable => freshFor > Duration.zero || staleFor > Duration.zero;

  /// Never cached.
  static const LibraryCachePolicy none = LibraryCachePolicy(
    freshFor: Duration.zero,
    persist: false,
  );

  /// Catalogue indexes (`index.min.json`, `source.json`). GitHub serves them
  /// with `max-age=300` and an `ETag`.
  static const LibraryCachePolicy catalogIndex = LibraryCachePolicy(
    freshFor: Duration(minutes: 5),
    staleFor: Duration(days: 30),
  );

  /// Source listing pages (latest updates, popular...).
  static const LibraryCachePolicy listing = LibraryCachePolicy(
    freshFor: Duration(minutes: 15),
    staleFor: Duration(days: 7),
  );

  /// Search results: short-lived, memory only.
  static const LibraryCachePolicy search = LibraryCachePolicy(
    freshFor: Duration(minutes: 5),
    staleFor: Duration(hours: 1),
    persist: false,
  );

  /// Manga details and chapter lists.
  static const LibraryCachePolicy details = LibraryCachePolicy(
    freshFor: Duration(minutes: 10),
    staleFor: Duration(days: 7),
  );

  /// Chapter page lists (rarely change once published).
  static const LibraryCachePolicy chapterPages = LibraryCachePolicy(
    freshFor: Duration(days: 1),
    staleFor: Duration(days: 30),
  );
}

enum LibraryFetchMode {
  /// Fresh cache is returned without network. Otherwise the network is used
  /// (conditionally when validators exist); on network failure a cached
  /// response within the stale window is returned marked `stale`.
  cacheFirst,

  /// Always ask the network (conditionally when validators exist). Used by
  /// manual refresh and background revalidation. Network failure throws; the
  /// caller keeps showing what it already displays.
  refresh,

  /// Never touch the network: returns the cached response (fresh or within
  /// the stale window) or throws [LibraryNetworkErrorKind.notFound] with
  /// detail `cache-miss`.
  cacheOnly,
}

/// Immutable description of one request. [key] identifies it for
/// deduplication and caching.
class LibraryRequest {
  LibraryRequest.get(
    this.uri, {
    Map<String, String> headers = const <String, String>{},
    this.cache = LibraryCachePolicy.none,
    this.timeout,
    this.maxBytes,
    this.cacheKey,
    Set<int> acceptStatuses = const <int>{},
    this.followRedirects = true,
  }) : method = 'GET',
       headers = Map<String, String>.unmodifiable(headers),
       form = null,
       acceptStatuses = Set<int>.unmodifiable(acceptStatuses);

  LibraryRequest.postForm(
    this.uri,
    Map<String, String> form, {
    Map<String, String> headers = const <String, String>{},
    this.cache = LibraryCachePolicy.none,
    this.timeout,
    this.maxBytes,
    this.cacheKey,
    Set<int> acceptStatuses = const <int>{},
    this.followRedirects = false,
  }) : method = 'POST',
       headers = Map<String, String>.unmodifiable(headers),
       form = Map<String, String>.unmodifiable(form),
       acceptStatuses = Set<int>.unmodifiable(acceptStatuses);

  final String method;
  final Uri uri;
  final Map<String, String> headers;

  /// `application/x-www-form-urlencoded` body for POST requests, encoded in
  /// insertion order.
  final Map<String, String>? form;
  final LibraryCachePolicy cache;

  /// Whole-request timeout (connection + headers + body). Defaults to
  /// [LibraryHttp.defaultTimeout].
  final Duration? timeout;

  /// Maximum accepted body size. Defaults to [LibraryHttp.defaultMaxBytes].
  final int? maxBytes;

  /// Overrides the computed cache/dedup key.
  final String? cacheKey;

  /// Non-2xx statuses returned as normal responses instead of throwing
  /// (e.g. `{404}` when a missing page means "no more results").
  final Set<int> acceptStatuses;
  final bool followRedirects;

  String get key {
    final explicit = cacheKey;
    if (explicit != null && explicit.isNotEmpty) return explicit;
    final buffer = StringBuffer('$method ${uri.toString()}');
    final body = form;
    if (body != null && body.isNotEmpty) {
      buffer.write(' ');
      buffer.write(
        body.entries
            .map(
              (entry) =>
                  '${Uri.encodeQueryComponent(entry.key)}='
                  '${Uri.encodeQueryComponent(entry.value)}',
            )
            .join('&'),
      );
    }
    return buffer.toString();
  }
}

/// Response returned by [LibraryHttp]. Bodies are kept as bytes; decode with
/// [text] or [json].
class LibraryHttpResponse {
  const LibraryHttpResponse({
    required this.request,
    required this.statusCode,
    required this.bodyBytes,
    required this.headers,
    required this.finalUri,
    required this.fetchedAt,
    this.fromCache = false,
    this.stale = false,
    this.revalidated = false,
    this.networkTime = Duration.zero,
  });

  final LibraryRequest request;
  final int statusCode;
  final Uint8List bodyBytes;

  /// Lower-case header names.
  final Map<String, String> headers;

  /// URL after redirects (relative resources must be resolved against it).
  final Uri finalUri;

  /// When the body was obtained from the server (for a 304 revalidation:
  /// when it was revalidated).
  final DateTime fetchedAt;

  /// Served from the memory or disk cache without a full download.
  final bool fromCache;

  /// Older than the policy's fresh window (returned because the network
  /// failed or because [LibraryFetchMode.cacheOnly] was requested).
  final bool stale;

  /// The server answered 304 Not Modified to a conditional request.
  final bool revalidated;

  /// Time spent waiting for the network (zero for pure cache hits). Lets
  /// measurements separate server time from NeoStation processing time.
  final Duration networkTime;

  bool get ok => statusCode >= 200 && statusCode < 300;

  String get text => utf8.decode(bodyBytes, allowMalformed: true);

  /// Decodes the body as JSON or throws
  /// [LibraryNetworkErrorKind.invalidResponse].
  dynamic json() {
    try {
      return jsonDecode(utf8.decode(bodyBytes));
    } catch (error) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.invalidResponse,
        uri: finalUri,
        statusCode: statusCode,
        detail: 'Invalid JSON: $error',
      );
    }
  }
}

/// Counters used by tests and performance measurements.
class LibraryHttpStats {
  int networkRequests = 0;
  int memoryHits = 0;
  int diskHits = 0;
  int notModified = 0;
  int deduplicated = 0;
  int cancelled = 0;
  int failures = 0;
  int staleServed = 0;
  int bytesDownloaded = 0;
  Duration networkTime = Duration.zero;

  Map<String, Object> toJson() => <String, Object>{
    'networkRequests': networkRequests,
    'memoryHits': memoryHits,
    'diskHits': diskHits,
    'notModified': notModified,
    'deduplicated': deduplicated,
    'cancelled': cancelled,
    'failures': failures,
    'staleServed': staleServed,
    'bytesDownloaded': bytesDownloaded,
    'networkTimeMs': networkTime.inMilliseconds,
  };
}

/// Function type used by services so tests can inject canned responses.
typedef LibraryFetcher =
    Future<LibraryHttpResponse> Function(
      LibraryRequest request, {
      LibraryFetchMode mode,
      LibraryCancelToken? cancel,
    });

class LibraryHttp {
  /// Creates an isolated instance (tests). [client] is used for every
  /// request; [cacheDirectory] holds the persistent cache (a temporary
  /// directory in tests); [clock] allows freshness tests.
  LibraryHttp({
    http.Client? client,
    Directory? cacheDirectory,
    DateTime Function()? clock,
    int maxConcurrentRequests = 8,
    int maxConcurrentPerHost = 3,
    int maxCacheBytes = 96 * 1024 * 1024,
    int maxMemoryCacheBytes = 8 * 1024 * 1024,
  }) {
    throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');
  }

  static const String defaultUserAgent =
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
      'Mobile/15E148 Safari/604.1 NeoStation/1.0';
  static const Duration defaultTimeout = Duration(seconds: 20);
  static const int defaultMaxBytes = 16 * 1024 * 1024;

  /// Process-wide instance used by the app. Tests may replace it.
  static LibraryHttp get instance =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');
  static set instance(LibraryHttp value) =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  LibraryHttpStats get stats =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  /// Sends [request] according to [mode]. Throws [LibraryNetworkException].
  /// Matches the [LibraryFetcher] signature.
  Future<LibraryHttpResponse> send(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) => throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  /// Returns the cached response for [request] without network access, or
  /// null. [allowStale] accepts entries in the stale window.
  Future<LibraryHttpResponse?> readCache(
    LibraryRequest request, {
    bool allowStale = true,
  }) => throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  /// Drops the cached entry for [request] (memory and disk).
  Future<void> evict(LibraryRequest request) =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  /// Current size of the persistent response cache in bytes.
  Future<int> cacheSizeBytes() =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  /// Evicts least recently used entries until the cache fits [maxBytes]
  /// (defaults to the configured limit).
  Future<void> trimCache({int? maxBytes}) =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  /// Removes every cached response (memory and disk).
  Future<void> clearCache() =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');

  /// Closes the underlying client (tests).
  void close() =>
      throw UnimplementedError('LibraryHttp is implemented in Build 437 wave 1');
}
