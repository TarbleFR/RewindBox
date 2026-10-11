import 'dart:async';
import 'dart:collection';
import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:crypto/crypto.dart';
import 'package:http/http.dart' as http;
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

import 'library_io_client.dart';

/// Shared network layer of the reading Library (Build 437).
///
/// Every Library request (source catalogues, manga pages, catalogue indexes,
/// covers) goes through [LibraryHttp] so that:
/// * one keep-alive client is reused instead of one client per request;
/// * concurrency is bounded per host and globally, with a separate budget
///   for images ([LibraryRequestLane.media]) so covers never delay
///   catalogue, search or details requests;
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
  final Set<_CancelListener> _listeners = <_CancelListener>{};

  bool get isCancelled => _completer.isCompleted;

  /// Completes when [cancel] is called.
  Future<void> get whenCancelled => _completer.future;

  void cancel() {
    if (_completer.isCompleted) return;
    _completer.complete();
    final listeners = _listeners.toList(growable: false);
    _listeners.clear();
    for (final listener in listeners) {
      scheduleMicrotask(listener.callback);
    }
  }

  /// Calls [onCancel] once (asynchronously) when the token is cancelled, or
  /// soon if it already is. Returns a function that unregisters it: call it
  /// when the work finished, so a long-lived token does not keep finished
  /// requests (and their bodies) reachable.
  void Function() addCancelListener(void Function() onCancel) {
    if (isCancelled) {
      scheduleMicrotask(onCancel);
      return () {};
    }
    final listener = _CancelListener(onCancel);
    _listeners.add(listener);
    return () => _listeners.remove(listener);
  }

  /// Listeners still registered (diagnostics and tests).
  int get listenerCount => _listeners.length;

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

/// Concurrency budget a request uses in [LibraryHttp].
enum LibraryRequestLane {
  /// Catalogues, listings, search, details, chapter and page lists: what
  /// the user waits for before anything can be shown.
  standard,

  /// Cover and page images. They have their own per-host and global
  /// budget, so tens of queued images never delay a [standard] request to
  /// the same host.
  media,
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
    this.lane = LibraryRequestLane.standard,
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
    this.lane = LibraryRequestLane.standard,
  }) : method = 'POST',
       headers = Map<String, String>.unmodifiable(headers),
       form = Map<String, String>.unmodifiable(form),
       acceptStatuses = Set<int>.unmodifiable(acceptStatuses);

  /// Concurrency budget used while the request waits for and holds a
  /// connection slot. Not part of [key].
  final LibraryRequestLane lane;

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
      buffer.write(_encodedForm(body));
    }
    return buffer.toString();
  }
}

String _encodedForm(Map<String, String> form) => form.entries
    .map(
      (entry) =>
          '${Uri.encodeQueryComponent(entry.key)}='
          '${Uri.encodeQueryComponent(entry.value)}',
    )
    .join('&');

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
///
/// * [networkRequests]: requests actually sent (after deduplication).
/// * [memoryHits] / [diskHits]: responses served from the cache without any
///   network access.
/// * [notModified]: conditional requests answered 304.
/// * [deduplicated]: callers that joined an identical in-flight request.
/// * [cancelled]: callers whose request ended because they cancelled.
/// * [failures]: network operations that failed (transport error, timeout,
///   size limit or HTTP status not accepted by the request).
/// * [staleServed]: responses returned with [LibraryHttpResponse.stale].
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
  ///
  /// The persistent cache lives in `<cacheDirectory>/library_http`. Without
  /// [cacheDirectory] it is resolved lazily to
  /// `getApplicationCacheDirectory()/Library/library_http`; when that fails
  /// (no platform plugin) only the memory cache is used.
  ///
  /// [hostLimits] overrides the per-host limits for specific hosts (see
  /// [LibraryHttp.hostLimits]).
  ///
  /// [LibraryRequestLane.media] requests (images) use their own limits,
  /// [maxConcurrentMediaRequests] and [maxConcurrentMediaPerHost], so they
  /// never hold a slot a [LibraryRequestLane.standard] request waits for.
  LibraryHttp({
    http.Client? client,
    Directory? cacheDirectory,
    DateTime Function()? clock,
    int maxConcurrentRequests = 8,
    int maxConcurrentPerHost = 3,
    int maxConcurrentMediaRequests = 6,
    int maxConcurrentMediaPerHost = 3,
    int maxCacheBytes = 96 * 1024 * 1024,
    int maxMemoryCacheBytes = 8 * 1024 * 1024,
    Map<String, int> hostLimits = const <String, int>{},
  }) : maxConcurrentRequests = math.max(1, maxConcurrentRequests),
       maxConcurrentPerHost = math.max(1, maxConcurrentPerHost),
       maxConcurrentMediaRequests = math.max(1, maxConcurrentMediaRequests),
       maxConcurrentMediaPerHost = math.max(1, maxConcurrentMediaPerHost),
       maxCacheBytes = math.max(0, maxCacheBytes),
       _clock = clock ?? DateTime.now,
       _client =
           client ??
           createDefaultClient(
             // Both lanes may be busy on one host at the same time: the
             // client must never queue a request the lanes already let
             // through.
             maxConnectionsPerHost:
                 math.max(1, maxConcurrentRequests) +
                 math.max(1, maxConcurrentMediaRequests),
           ),
       _memory = _MemoryCache(math.max(0, maxMemoryCacheBytes)) {
    _global = _FifoSemaphore(this.maxConcurrentRequests);
    _mediaGlobal = _FifoSemaphore(this.maxConcurrentMediaRequests);
    _disk = LibraryDiskCache(
      () async {
        final base = cacheDirectory ?? await defaultCacheDirectory();
        return Directory(p.join(base.path, httpCacheFolderName));
      },
      maxBytes: this.maxCacheBytes,
      clock: _clock,
    );
    hostLimits.forEach(setHostLimit);
  }

  static const String defaultUserAgent =
      'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) '
      'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 '
      'Mobile/15E148 Safari/604.1 NeoStation/1.0';
  static const Duration defaultTimeout = Duration(seconds: 20);
  static const int defaultMaxBytes = 16 * 1024 * 1024;

  /// Folder of the persistent HTTP cache inside the cache directory.
  static const String httpCacheFolderName = 'library_http';

  /// Kept-alive sockets are closed after this idle time.
  static const Duration idleTimeout = Duration(seconds: 15);

  /// Time allowed to open a TCP/TLS connection.
  static const Duration connectionTimeout = Duration(seconds: 10);

  /// Persisted entries record their last use at most this often, so cache
  /// hits do not rewrite metadata on every access.
  static const Duration _accessRecordInterval = Duration(minutes: 1);

  /// Bytes of an error body inspected for anti-bot challenge markers.
  static const int _challengeSniffBytes = 256 * 1024;

  static LibraryHttp? _instance;

  /// Process-wide instance used by the app. Tests may replace it.
  static LibraryHttp get instance => _instance ??= LibraryHttp();
  static set instance(LibraryHttp value) => _instance = value;

  /// `Caches/Library` of the app (iOS `NSCachesDirectory`). Library caches
  /// only ever write inside sub-folders of this directory.
  static Future<Directory> defaultCacheDirectory() async {
    final base = await getApplicationCacheDirectory();
    return Directory(p.join(base.path, 'Library'));
  }

  /// The keep-alive `dart:io` client used when no client is injected.
  static http.Client createDefaultClient({int maxConnectionsPerHost = 8}) {
    final inner = HttpClient()
      ..idleTimeout = idleTimeout
      ..connectionTimeout = connectionTimeout
      ..maxConnectionsPerHost = math.max(1, maxConnectionsPerHost)
      ..autoUncompress = true
      ..userAgent = defaultUserAgent;
    // Not IOClient: an abort must close the connection whenever it comes
    // (see LibraryIoClient).
    return LibraryIoClient(inner);
  }

  /// Global limit of requests on the wire.
  final int maxConcurrentRequests;

  /// Default per-host limit (see [hostLimits] for overrides).
  final int maxConcurrentPerHost;

  /// Global limit of [LibraryRequestLane.media] requests on the wire, on
  /// top of [maxConcurrentRequests].
  final int maxConcurrentMediaRequests;

  /// Default per-host limit of [LibraryRequestLane.media] requests, on top
  /// of [maxConcurrentPerHost].
  final int maxConcurrentMediaPerHost;

  /// Size limit of the persistent cache.
  final int maxCacheBytes;

  final http.Client _client;
  final DateTime Function() _clock;
  final _MemoryCache _memory;
  late final _FifoSemaphore _global;
  late final _FifoSemaphore _mediaGlobal;
  late final LibraryDiskCache _disk;
  final Map<String, _FifoSemaphore> _hostSemaphores =
      <String, _FifoSemaphore>{};
  final Map<String, _FifoSemaphore> _mediaHostSemaphores =
      <String, _FifoSemaphore>{};
  final Map<String, int> _hostOverrides = <String, int>{};
  final Map<String, _Flight> _flights = <String, _Flight>{};
  final LibraryHttpStats _stats = LibraryHttpStats();
  bool _closed = false;

  LibraryHttpStats get stats => _stats;

  /// Per-host concurrency overrides, keyed by lower-case host name, applied
  /// to each lane. `hostLimits['example.com'] = 1` serialises that host's
  /// standard requests (and, separately, its images); removing the key
  /// restores [maxConcurrentPerHost] / [maxConcurrentMediaPerHost]. Changes
  /// apply to queued requests immediately.
  late final Map<String, int> hostLimits = _HostLimitMap(this);

  /// Sets ([limit] >= 1) or removes (null) the concurrency override of
  /// [host].
  void setHostLimit(String host, int? limit) {
    final normalized = host.trim().toLowerCase();
    if (normalized.isEmpty) return;
    if (limit == null) {
      _hostOverrides.remove(normalized);
    } else {
      _hostOverrides[normalized] = math.max(1, limit);
    }
    for (final lane in LibraryRequestLane.values) {
      _hostSemaphoresOf(lane)[normalized]?.limit = _limitFor(normalized, lane);
    }
  }

  int _limitFor(String host, LibraryRequestLane lane) =>
      _hostOverrides[host] ??
      switch (lane) {
        LibraryRequestLane.standard => maxConcurrentPerHost,
        LibraryRequestLane.media => maxConcurrentMediaPerHost,
      };

  Map<String, _FifoSemaphore> _hostSemaphoresOf(LibraryRequestLane lane) =>
      switch (lane) {
        LibraryRequestLane.standard => _hostSemaphores,
        LibraryRequestLane.media => _mediaHostSemaphores,
      };

  /// Sends [request] according to [mode]. Throws [LibraryNetworkException].
  /// Matches the [LibraryFetcher] signature.
  ///
  /// Concurrent calls with the same [LibraryRequest.key] share one network
  /// operation (unless their own `If-None-Match`, `If-Modified-Since` or
  /// `Range` headers differ). Each caller may cancel independently; the
  /// socket is aborted only when every caller of that operation cancelled.
  Future<LibraryHttpResponse> send(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    if (_closed) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.offline,
        uri: request.uri,
        detail: 'client-closed',
      );
    }
    if (cancel != null && cancel.isCancelled) {
      _stats.cancelled++;
      cancel.throwIfCancelled(request.uri);
    }

    final policy = request.cache;
    final key = request.key;
    LibraryCacheRecord? cached;
    if (policy.isCacheable) {
      final lookup = await _lookup(key, policy);
      if (cancel != null && cancel.isCancelled) {
        _stats.cancelled++;
        cancel.throwIfCancelled(request.uri);
      }
      if (lookup != null) {
        cached = lookup.record;
        final freshness = _freshness(cached, policy);
        final servable =
            (mode == LibraryFetchMode.cacheFirst &&
                freshness == _Freshness.fresh) ||
            (mode == LibraryFetchMode.cacheOnly &&
                freshness != _Freshness.expired);
        if (servable) {
          if (lookup.fromMemory) {
            _stats.memoryHits++;
          } else {
            _stats.diskHits++;
          }
          final stale = freshness != _Freshness.fresh;
          if (stale) _stats.staleServed++;
          _recordAccess(cached, policy);
          return _responseFromRecord(request, cached, stale: stale);
        }
      }
    }

    if (mode == LibraryFetchMode.cacheOnly) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.notFound,
        uri: request.uri,
        detail: 'cache-miss',
      );
    }

    try {
      final outcome = await _joinFlight(request, cached, cancel);
      return _responseFromOutcome(request, outcome);
    } on LibraryNetworkException catch (error) {
      final fallback = cached;
      if (mode == LibraryFetchMode.cacheFirst &&
          fallback != null &&
          _staleFallbackKinds.contains(error.kind) &&
          _freshness(fallback, policy) != _Freshness.expired) {
        _stats.staleServed++;
        _recordAccess(fallback, policy);
        return _responseFromRecord(request, fallback, stale: true);
      }
      rethrow;
    }
  }

  /// Returns the cached response for [request] without network access, or
  /// null. [allowStale] accepts entries in the stale window.
  Future<LibraryHttpResponse?> readCache(
    LibraryRequest request, {
    bool allowStale = true,
  }) async {
    final policy = request.cache;
    if (!policy.isCacheable) return null;
    final lookup = await _lookup(request.key, policy);
    if (lookup == null) return null;
    final freshness = _freshness(lookup.record, policy);
    if (freshness == _Freshness.expired) return null;
    if (freshness == _Freshness.stale && !allowStale) return null;
    if (lookup.fromMemory) {
      _stats.memoryHits++;
    } else {
      _stats.diskHits++;
    }
    _recordAccess(lookup.record, policy);
    return _responseFromRecord(
      request,
      lookup.record,
      stale: freshness == _Freshness.stale,
    );
  }

  /// Drops the cached entry for [request] (memory and disk).
  Future<void> evict(LibraryRequest request) async {
    final key = request.key;
    _memory.remove(key);
    await _disk.remove(key);
  }

  /// Current size of the persistent response cache in bytes.
  Future<int> cacheSizeBytes() => _disk.sizeBytes();

  /// Evicts least recently used entries until the cache fits [maxBytes]
  /// (defaults to the configured limit).
  Future<void> trimCache({int? maxBytes}) async {
    await _disk.trim(maxBytes: maxBytes ?? maxCacheBytes);
  }

  /// Removes every cached response (memory and disk).
  Future<void> clearCache() async {
    _memory.clear();
    await _disk.clear();
  }

  /// Completes when background cache work (access-time updates, automatic
  /// trimming) started by earlier requests is finished.
  Future<void> idle() => _disk.idle();

  /// Closes the underlying client (tests). In-flight and queued requests end
  /// with [LibraryNetworkErrorKind.cancelled].
  void close() {
    if (_closed) return;
    _closed = true;
    for (final flight in _flights.values.toList()) {
      flight.abort(_AbortReason.closed);
    }
    _flights.clear();
    _client.close();
  }

  /// Classifies a non-success HTTP answer following the Library contract.
  /// Returns null for 2xx statuses.
  ///
  /// Any status carrying `cf-mitigated: challenge`, and a 403 whose body
  /// contains a Cloudflare browser check, is a [LibraryNetworkErrorKind.challenge].
  static LibraryNetworkErrorKind? classifyStatus(
    int statusCode, {
    Map<String, String> headers = const <String, String>{},
    List<int> body = const <int>[],
  }) {
    if (statusCode >= 200 && statusCode < 300) return null;
    if (_isChallenge(statusCode, headers, body)) {
      return LibraryNetworkErrorKind.challenge;
    }
    if (statusCode == 404 || statusCode == 410) {
      return LibraryNetworkErrorKind.notFound;
    }
    if ((statusCode >= 500 && statusCode <= 504) ||
        (statusCode >= 520 && statusCode <= 530)) {
      return LibraryNetworkErrorKind.serverUnavailable;
    }
    return LibraryNetworkErrorKind.httpStatus;
  }

  static bool _isChallenge(
    int statusCode,
    Map<String, String> headers,
    List<int> body,
  ) {
    for (final entry in headers.entries) {
      if (entry.key.toLowerCase() == 'cf-mitigated' &&
          entry.value.toLowerCase().contains('challenge')) {
        return true;
      }
    }
    if (statusCode != 403 || body.isEmpty) return false;
    final sniff = body.length > _challengeSniffBytes
        ? body.sublist(0, _challengeSniffBytes)
        : body;
    final text = utf8.decode(sniff, allowMalformed: true);
    return text.contains('<title>Just a moment...</title>') ||
        text.contains('Attention Required! | Cloudflare') ||
        text.contains('challenge-platform');
  }

  static const Set<LibraryNetworkErrorKind> _staleFallbackKinds =
      <LibraryNetworkErrorKind>{
        LibraryNetworkErrorKind.offline,
        LibraryNetworkErrorKind.timeout,
        LibraryNetworkErrorKind.serverUnavailable,
        LibraryNetworkErrorKind.challenge,
      };

  // ---------------------------------------------------------------- cache --

  Future<_Lookup?> _lookup(String key, LibraryCachePolicy policy) async {
    final memory = _memory.get(key);
    if (memory != null) return _Lookup(memory, fromMemory: true);
    if (!policy.persist) return null;
    final record = await _disk.read(key);
    if (record == null) return null;
    _memory.put(record);
    return _Lookup(record, fromMemory: false);
  }

  _Freshness _freshness(LibraryCacheRecord record, LibraryCachePolicy policy) {
    final age = _clock().difference(record.fetchedAt);
    // The clock moved backwards: the age is unknown, so the entry is
    // revalidated but still usable as a fallback.
    if (age.isNegative) return _Freshness.stale;
    if (age < policy.freshFor) return _Freshness.fresh;
    if (age < policy.freshFor + policy.staleFor) return _Freshness.stale;
    return _Freshness.expired;
  }

  void _recordAccess(LibraryCacheRecord record, LibraryCachePolicy policy) {
    final now = _clock();
    if (now.difference(record.lastAccessAt).abs() < _accessRecordInterval) {
      return;
    }
    final touched = record.copyWith(lastAccessAt: now);
    _memory.replaceIfPresent(touched);
    if (policy.persist) {
      unawaited(_disk.touch(record.key, now).catchError((Object _) => false));
    }
  }

  Future<void> _store(LibraryRequest request, LibraryCacheRecord record) async {
    _memory.put(record);
    if (request.cache.persist) {
      try {
        await _disk.write(record);
      } catch (_) {
        // A full or read-only disk must not fail the request itself.
      }
    }
  }

  LibraryHttpResponse _responseFromRecord(
    LibraryRequest request,
    LibraryCacheRecord record, {
    required bool stale,
    bool revalidated = false,
    Duration networkTime = Duration.zero,
  }) {
    return LibraryHttpResponse(
      request: request,
      statusCode: record.statusCode,
      bodyBytes: record.body ?? Uint8List(0),
      headers: record.headers,
      finalUri: Uri.tryParse(record.finalUrl) ?? request.uri,
      fetchedAt: record.fetchedAt,
      fromCache: true,
      stale: stale,
      revalidated: revalidated,
      networkTime: networkTime,
    );
  }

  LibraryHttpResponse _responseFromOutcome(
    LibraryRequest request,
    _NetworkOutcome outcome,
  ) {
    final status = outcome.statusCode;
    final success = status >= 200 && status < 300;
    if (!success && !request.acceptStatuses.contains(status)) {
      final kind =
          classifyStatus(
            status,
            headers: outcome.headers,
            body: outcome.body,
          ) ??
          LibraryNetworkErrorKind.httpStatus;
      throw LibraryNetworkException(
        kind,
        uri: outcome.finalUri,
        statusCode: status,
        detail: kind == LibraryNetworkErrorKind.challenge
            ? 'anti-bot challenge'
            : null,
      );
    }
    return LibraryHttpResponse(
      request: request,
      statusCode: status,
      bodyBytes: outcome.body,
      headers: outcome.headers,
      finalUri: outcome.finalUri,
      fetchedAt: outcome.fetchedAt,
      fromCache: outcome.revalidated,
      revalidated: outcome.revalidated,
      networkTime: outcome.networkTime,
    );
  }

  // -------------------------------------------------------------- network --

  /// Caller headers that change the answer to an otherwise identical
  /// request (conditional and range requests).
  static const List<String> _variantHeaders = <String>[
    'if-none-match',
    'if-modified-since',
    'range',
  ];

  /// Requests share one network operation when their [LibraryRequest.key]
  /// matches and they carry the same [_variantHeaders], so a plain request
  /// never receives the empty 304 answered to a caller's conditional one.
  static String _flightKey(LibraryRequest request) {
    final parts = <String>[];
    for (final name in _variantHeaders) {
      for (final entry in request.headers.entries) {
        if (entry.key.toLowerCase() == name) {
          parts.add('$name: ${entry.value}');
        }
      }
    }
    return parts.isEmpty ? request.key : '${request.key}\n${parts.join('\n')}';
  }

  Future<_NetworkOutcome> _joinFlight(
    LibraryRequest request,
    LibraryCacheRecord? cached,
    LibraryCancelToken? cancel,
  ) {
    final key = _flightKey(request);
    var flight = _flights[key];
    if (flight == null || flight.isAborted) {
      final created = _Flight(key);
      _flights[key] = created;
      created.result.future.ignore();
      unawaited(_runFlight(created, request, cached));
      flight = created;
    } else {
      _stats.deduplicated++;
    }
    flight.waiters++;
    if (cancel == null) return flight.result.future;

    final shared = flight;
    final completer = Completer<_NetworkOutcome>();
    final unregister = cancel.addCancelListener(() {
      if (completer.isCompleted) return;
      _stats.cancelled++;
      completer.completeError(
        LibraryNetworkException(
          LibraryNetworkErrorKind.cancelled,
          uri: request.uri,
        ),
      );
      shared.waiters--;
      if (shared.waiters <= 0) {
        shared.abort(_AbortReason.cancelled);
        if (identical(_flights[key], shared)) _flights.remove(key);
      }
    });
    shared.result.future.then(
      (outcome) {
        unregister();
        if (!completer.isCompleted) completer.complete(outcome);
      },
      onError: (Object error, StackTrace stackTrace) {
        unregister();
        if (!completer.isCompleted) completer.completeError(error, stackTrace);
      },
    );
    return completer.future;
  }

  Future<void> _runFlight(
    _Flight flight,
    LibraryRequest request,
    LibraryCacheRecord? cached,
  ) async {
    try {
      final outcome = await _perform(flight, request, cached);
      if (!flight.result.isCompleted) flight.result.complete(outcome);
    } catch (error, stackTrace) {
      if (!flight.result.isCompleted) {
        flight.result.completeError(error, stackTrace);
      }
    } finally {
      if (identical(_flights[flight.key], flight)) _flights.remove(flight.key);
    }
  }

  Future<_NetworkOutcome> _perform(
    _Flight flight,
    LibraryRequest request,
    LibraryCacheRecord? cached,
  ) async {
    final uri = request.uri;
    if ((uri.scheme != 'http' && uri.scheme != 'https') || uri.host.isEmpty) {
      throw LibraryNetworkException(
        LibraryNetworkErrorKind.invalidResponse,
        uri: uri,
        detail: 'unsupported-url',
      );
    }
    final host = uri.host.toLowerCase();
    final lane = request.lane;
    final hostSemaphores = _hostSemaphoresOf(lane);
    final global = switch (lane) {
      LibraryRequestLane.standard => _global,
      LibraryRequestLane.media => _mediaGlobal,
    };
    final hostSemaphore = hostSemaphores.putIfAbsent(
      host,
      () => _FifoSemaphore(_limitFor(host, lane)),
    );
    if (!await hostSemaphore.acquire(flight.aborted)) {
      _releaseIdleHost(hostSemaphores, host, hostSemaphore);
      throw _abortException(flight.abortReason, uri);
    }
    try {
      if (!await global.acquire(flight.aborted)) {
        throw _abortException(flight.abortReason, uri);
      }
      try {
        return await _transfer(flight, request, cached);
      } finally {
        global.release();
      }
    } finally {
      hostSemaphore.release();
      _releaseIdleHost(hostSemaphores, host, hostSemaphore);
    }
  }

  static void _releaseIdleHost(
    Map<String, _FifoSemaphore> semaphores,
    String host,
    _FifoSemaphore semaphore,
  ) {
    if (semaphore.isIdle && identical(semaphores[host], semaphore)) {
      semaphores.remove(host);
    }
  }

  Future<_NetworkOutcome> _transfer(
    _Flight flight,
    LibraryRequest request,
    LibraryCacheRecord? cached,
  ) async {
    final uri = request.uri;
    if (flight.isAborted) throw _abortException(flight.abortReason, uri);

    final maxBytes = request.maxBytes ?? defaultMaxBytes;
    _AbortReason? reason;
    final trigger = Completer<void>();
    void fire(_AbortReason why) {
      if (trigger.isCompleted) return;
      reason = why;
      trigger.complete();
    }

    final timer = Timer(
      request.timeout ?? defaultTimeout,
      () => fire(_AbortReason.timeout),
    );
    unawaited(
      flight.aborted.then(
        (_) => fire(flight.abortReason ?? _AbortReason.cancelled),
      ),
    );

    var requestHeaders = <String, String>{...request.headers};
    if (!_hasHeader(requestHeaders, 'user-agent')) {
      requestHeaders['User-Agent'] = defaultUserAgent;
    }
    final etag = cached?.headers['etag'];
    final lastModified = cached?.headers['last-modified'];
    final callerConditional =
        _hasHeader(requestHeaders, 'if-none-match') ||
        _hasHeader(requestHeaders, 'if-modified-since');
    final revalidating =
        !callerConditional &&
            ((etag != null && etag.isNotEmpty) ||
                (lastModified != null && lastModified.isNotEmpty))
        ? cached
        : null;
    if (revalidating != null) {
      if (etag != null && etag.isNotEmpty) {
        requestHeaders['If-None-Match'] = etag;
      }
      if (lastModified != null && lastModified.isNotEmpty) {
        requestHeaders['If-Modified-Since'] = lastModified;
      }
    }
    final form = request.form;
    List<int>? requestBody;
    if (form != null) {
      if (!_hasHeader(requestHeaders, 'content-type')) {
        requestHeaders['Content-Type'] =
            'application/x-www-form-urlencoded; charset=utf-8';
      }
      requestBody = utf8.encode(_encodedForm(form));
    }

    // An https request never continues over cleartext. Its redirects are
    // followed here rather than by the client, so a `Location: http://...`
    // is refused before anything is sent to it (path, Referer and other
    // headers included).
    final secure = uri.scheme == 'https';
    final manualRedirects = secure && request.followRedirects;
    var hopUri = uri;
    var hopMethod = request.method;
    var redirects = 0;

    final watch = Stopwatch()..start();
    _stats.networkRequests++;
    try {
      http.StreamedResponse streamed;
      Uri finalUri;
      while (true) {
        final httpRequest = http.AbortableRequest(
          hopMethod,
          hopUri,
          abortTrigger: trigger.future,
        );
        httpRequest
          ..followRedirects = manualRedirects ? false : request.followRedirects
          ..maxRedirects = redirectLimit
          ..persistentConnection = true;
        httpRequest.headers.addAll(requestHeaders);
        final hopBody = requestBody;
        if (hopBody != null) httpRequest.bodyBytes = hopBody;
        final response = await _raceAbort(
          _client.send(httpRequest),
          trigger.future,
          onLate: (abandoned) => unawaited(_discard(abandoned.stream)),
        );
        var responseUri = hopUri;
        if (response case http.BaseResponseWithUrl(:final url)) {
          responseUri = hopUri.resolveUri(url);
        }
        // A client that followed the redirect itself: the cleartext answer
        // is neither parsed nor cached.
        if (secure && responseUri.scheme != 'https') {
          unawaited(_discard(response.stream));
          throw _downgrade(responseUri, response.statusCode);
        }
        final location = manualRedirects
            ? _redirectLocation(hopMethod, response)
            : null;
        if (location == null) {
          streamed = response;
          finalUri = responseUri;
          break;
        }
        final Uri next;
        try {
          next = responseUri.resolveUri(Uri.parse(location));
        } on FormatException {
          unawaited(_discard(response.stream));
          throw LibraryNetworkException(
            LibraryNetworkErrorKind.invalidResponse,
            uri: responseUri,
            statusCode: response.statusCode,
            detail: 'invalid redirect location',
          );
        }
        await _drainBody(response, trigger: trigger.future, uri: responseUri);
        if (next.scheme != 'https' || next.host.isEmpty) {
          throw _downgrade(next, response.statusCode);
        }
        if (++redirects > redirectLimit) {
          // Same classification as the client's own RedirectException.
          throw LibraryNetworkException(
            LibraryNetworkErrorKind.offline,
            uri: next,
            statusCode: response.statusCode,
            detail: 'redirect limit exceeded',
          );
        }
        if (hopMethod == 'POST' && response.statusCode == 303) {
          hopMethod = 'GET';
          requestBody = null;
          requestHeaders = <String, String>{
            for (final entry in requestHeaders.entries)
              if (entry.key.toLowerCase() != 'content-type')
                entry.key: entry.value,
          };
        }
        if (!_sameOrigin(hopUri, next)) {
          requestHeaders = <String, String>{
            for (final entry in requestHeaders.entries)
              if (!_originBoundHeaders.contains(entry.key.toLowerCase()))
                entry.key: entry.value,
          };
        }
        hopUri = next;
      }
      final statusCode = streamed.statusCode;
      final headers = <String, String>{
        for (final entry in streamed.headers.entries)
          entry.key.toLowerCase(): entry.value,
      };
      final Uint8List body;
      if (statusCode == 304 || request.method == 'HEAD') {
        await _drainBody(streamed, trigger: trigger.future, uri: finalUri);
        body = Uint8List(0);
      } else {
        body = await _readBody(
          streamed,
          maxBytes: maxBytes,
          trigger: trigger.future,
          uri: finalUri,
        );
      }
      watch.stop();
      _stats.bytesDownloaded += body.length;
      _stats.networkTime += watch.elapsed;
      final now = _clock();

      if (statusCode == 304 && revalidating != null) {
        _stats.notModified++;
        final revalidated = revalidating.copyWith(
          headers: _mergeValidators(revalidating.headers, headers),
          fetchedAt: now,
          lastAccessAt: now,
        );
        _memory.put(revalidated);
        if (request.cache.persist) {
          final updated = await _disk
              .updateMeta(revalidated)
              .catchError((Object _) => false);
          if (!updated) {
            await _disk.write(revalidated).catchError((Object _) => false);
          }
        }
        return _NetworkOutcome(
          statusCode: revalidated.statusCode,
          headers: revalidated.headers,
          body: revalidated.body ?? Uint8List(0),
          finalUri: Uri.tryParse(revalidated.finalUrl) ?? finalUri,
          fetchedAt: now,
          networkTime: watch.elapsed,
          revalidated: true,
        );
      }

      final success = statusCode >= 200 && statusCode < 300;
      if (success && statusCode != 206 && request.cache.isCacheable) {
        await _store(
          request,
          LibraryCacheRecord(
            key: request.key,
            url: uri.toString(),
            finalUrl: finalUri.toString(),
            statusCode: statusCode,
            headers: LibraryCacheRecord.selectHeaders(headers),
            fetchedAt: now,
            lastAccessAt: now,
            size: body.length,
            body: body,
          ),
        );
      }
      if (!success && !request.acceptStatuses.contains(statusCode)) {
        _stats.failures++;
      }
      return _NetworkOutcome(
        statusCode: statusCode,
        headers: Map<String, String>.unmodifiable(headers),
        body: body,
        finalUri: finalUri,
        fetchedAt: now,
        networkTime: watch.elapsed,
        revalidated: false,
      );
    } catch (error) {
      final mapped = _mapError(error, reason, uri);
      if (mapped.kind != LibraryNetworkErrorKind.cancelled) _stats.failures++;
      _stats.networkTime += watch.elapsed;
      throw mapped;
    } finally {
      timer.cancel();
    }
  }

  static Map<String, String> _mergeValidators(
    Map<String, String> stored,
    Map<String, String> notModified,
  ) {
    final merged = Map<String, String>.of(stored);
    for (final name in const <String>[
      'etag',
      'last-modified',
      'cache-control',
      'expires',
      'date',
    ]) {
      final value = notModified[name];
      if (value != null && value.isNotEmpty) merged[name] = value;
    }
    return Map<String, String>.unmodifiable(merged);
  }

  /// Redirects followed for one request (the `dart:io` default).
  static const int redirectLimit = 5;

  /// Headers dropped when a redirect leaves the origin (as `dart:io` does).
  static const Set<String> _originBoundHeaders = <String>{
    'authorization',
    'www-authenticate',
    'proxy-authorization',
    'proxy-authenticate',
    'cookie',
    'cookie2',
  };

  static LibraryNetworkException _downgrade(Uri target, int statusCode) =>
      LibraryNetworkException(
        LibraryNetworkErrorKind.invalidResponse,
        uri: target,
        statusCode: statusCode,
        detail: 'downgrade',
      );

  /// The `Location` of a redirect `dart:io` would follow for [method]
  /// (GET/HEAD: 301, 302, 303, 307, 308; POST: 303 only), or null.
  static String? _redirectLocation(
    String method,
    http.StreamedResponse response,
  ) {
    final status = response.statusCode;
    final follows = method == 'GET' || method == 'HEAD'
        ? const <int>{301, 302, 303, 307, 308}.contains(status)
        : method == 'POST' && status == 303;
    if (!follows) return null;
    for (final entry in response.headers.entries) {
      if (entry.key.toLowerCase() == 'location') {
        final value = entry.value.trim();
        return value.isEmpty ? null : value;
      }
    }
    return null;
  }

  static bool _sameOrigin(Uri a, Uri b) =>
      a.scheme == b.scheme &&
      a.host.toLowerCase() == b.host.toLowerCase() &&
      a.port == b.port;

  /// Reads and drops a body that is not used (304, HEAD, redirect), rather
  /// than cancelling it, so a non-conforming body cannot leave the
  /// kept-alive connection half-read.
  static Future<void> _drainBody(
    http.StreamedResponse response, {
    required Future<void> trigger,
    required Uri uri,
  }) async {
    try {
      await _readBody(
        response,
        maxBytes: 64 * 1024,
        trigger: trigger,
        uri: uri,
      );
    } on LibraryNetworkException catch (error) {
      if (error.kind != LibraryNetworkErrorKind.tooLarge) rethrow;
    }
  }

  static bool _hasHeader(Map<String, String> headers, String name) {
    for (final key in headers.keys) {
      if (key.toLowerCase() == name) return true;
    }
    return false;
  }

  static Future<T> _raceAbort<T>(
    Future<T> future,
    Future<void> trigger, {
    void Function(T late)? onLate,
  }) {
    final completer = Completer<T>();
    future.then(
      (value) {
        if (completer.isCompleted) {
          onLate?.call(value);
        } else {
          completer.complete(value);
        }
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!completer.isCompleted) completer.completeError(error, stackTrace);
      },
    );
    trigger.then((_) {
      if (!completer.isCompleted) completer.completeError(const _AbortSignal());
    });
    return completer.future;
  }

  static Future<void> _discard(Stream<List<int>> stream) async {
    try {
      await stream.listen(null, cancelOnError: true).cancel();
    } catch (_) {}
  }

  static Future<Uint8List> _readBody(
    http.StreamedResponse response, {
    required int maxBytes,
    required Future<void> trigger,
    required Uri uri,
  }) {
    final declared = response.contentLength;
    if (declared != null && declared > maxBytes) {
      unawaited(_discard(response.stream));
      return Future<Uint8List>.error(
        LibraryNetworkException(
          LibraryNetworkErrorKind.tooLarge,
          uri: uri,
          statusCode: response.statusCode,
          detail: 'content-length $declared > $maxBytes',
        ),
      );
    }
    final completer = Completer<Uint8List>();
    final builder = BytesBuilder(copy: false);
    StreamSubscription<List<int>>? subscription;
    var cancelRequested = false;
    void stop() {
      final active = subscription;
      if (active == null) {
        cancelRequested = true;
      } else {
        unawaited(active.cancel());
      }
    }

    subscription = response.stream.listen(
      (chunk) {
        if (completer.isCompleted) return;
        if (builder.length + chunk.length > maxBytes) {
          stop();
          completer.completeError(
            LibraryNetworkException(
              LibraryNetworkErrorKind.tooLarge,
              uri: uri,
              statusCode: response.statusCode,
              detail: 'body > $maxBytes bytes',
            ),
          );
          return;
        }
        builder.add(chunk);
      },
      onError: (Object error, StackTrace stackTrace) {
        if (!completer.isCompleted) completer.completeError(error, stackTrace);
      },
      onDone: () {
        if (!completer.isCompleted) completer.complete(builder.takeBytes());
      },
      cancelOnError: true,
    );
    if (cancelRequested) unawaited(subscription.cancel());
    trigger.then((_) {
      if (completer.isCompleted) return;
      stop();
      completer.completeError(const _AbortSignal());
    });
    return completer.future;
  }

  static LibraryNetworkException _abortException(
    _AbortReason? reason,
    Uri uri,
  ) {
    if (reason == _AbortReason.timeout) {
      return LibraryNetworkException(LibraryNetworkErrorKind.timeout, uri: uri);
    }
    return LibraryNetworkException(
      LibraryNetworkErrorKind.cancelled,
      uri: uri,
      detail: reason == _AbortReason.closed ? 'client-closed' : null,
    );
  }

  static LibraryNetworkException _mapError(
    Object error,
    _AbortReason? reason,
    Uri uri,
  ) {
    if (error is LibraryNetworkException) return error;
    if (reason != null ||
        error is _AbortSignal ||
        error is http.RequestAbortedException) {
      return _abortException(reason, uri);
    }
    final detail = _shortDetail(error);
    if (error is TimeoutException) {
      return LibraryNetworkException(
        LibraryNetworkErrorKind.timeout,
        uri: uri,
        detail: detail,
      );
    }
    if (error is SocketException) {
      final timedOut = error.message.toLowerCase().contains('timed out');
      return LibraryNetworkException(
        timedOut
            ? LibraryNetworkErrorKind.timeout
            : LibraryNetworkErrorKind.offline,
        uri: uri,
        detail: detail,
      );
    }
    if (error is TlsException ||
        error is HttpException ||
        error is http.ClientException) {
      return LibraryNetworkException(
        LibraryNetworkErrorKind.offline,
        uri: uri,
        detail: detail,
      );
    }
    return LibraryNetworkException(
      LibraryNetworkErrorKind.invalidResponse,
      uri: uri,
      detail: detail,
    );
  }

  static String _shortDetail(Object error) {
    final text = error.toString();
    return text.length > 300 ? '${text.substring(0, 300)}...' : text;
  }
}

enum _AbortReason { cancelled, timeout, closed }

/// Identity wrapper so the same callback can be registered twice.
class _CancelListener {
  _CancelListener(this.callback);

  final void Function() callback;
}

enum _Freshness { fresh, stale, expired }

class _AbortSignal implements Exception {
  const _AbortSignal();
}

class _Lookup {
  const _Lookup(this.record, {required this.fromMemory});

  final LibraryCacheRecord record;
  final bool fromMemory;
}

class _NetworkOutcome {
  const _NetworkOutcome({
    required this.statusCode,
    required this.headers,
    required this.body,
    required this.finalUri,
    required this.fetchedAt,
    required this.networkTime,
    required this.revalidated,
  });

  final int statusCode;
  final Map<String, String> headers;
  final Uint8List body;
  final Uri finalUri;
  final DateTime fetchedAt;
  final Duration networkTime;
  final bool revalidated;
}

/// One network operation shared by every concurrent caller of the same key.
class _Flight {
  _Flight(this.key);

  final String key;
  final Completer<_NetworkOutcome> result = Completer<_NetworkOutcome>();
  final Completer<void> _aborted = Completer<void>();
  _AbortReason? abortReason;
  int waiters = 0;

  bool get isAborted => _aborted.isCompleted;
  Future<void> get aborted => _aborted.future;

  void abort(_AbortReason reason) {
    if (_aborted.isCompleted) return;
    abortReason = reason;
    _aborted.complete();
  }
}

/// FIFO counting semaphore. A waiter whose cancel signal fires while queued
/// leaves the queue without ever holding a slot.
class _FifoSemaphore {
  _FifoSemaphore(int limit) : _limit = math.max(1, limit);

  int _limit;
  int _active = 0;
  final Queue<Completer<bool>> _queue = Queue<Completer<bool>>();

  bool get isIdle => _active == 0 && _queue.isEmpty;

  set limit(int value) {
    _limit = math.max(1, value);
    _drain();
  }

  /// Completes with true once a slot is held, or false if [cancelled]
  /// completed first (no slot is held then).
  Future<bool> acquire(Future<void> cancelled) {
    if (_active < _limit && _queue.isEmpty) {
      _active++;
      return Future<bool>.value(true);
    }
    final waiter = Completer<bool>();
    _queue.add(waiter);
    cancelled.then((_) {
      if (_queue.remove(waiter)) waiter.complete(false);
    });
    return waiter.future;
  }

  void release() {
    if (_active > 0) _active--;
    _drain();
  }

  void _drain() {
    while (_active < _limit && _queue.isNotEmpty) {
      _active++;
      _queue.removeFirst().complete(true);
    }
  }
}

class _HostLimitMap extends MapBase<String, int> {
  _HostLimitMap(this._owner);

  final LibraryHttp _owner;

  @override
  int? operator [](Object? key) =>
      key is String ? _owner._hostOverrides[key.trim().toLowerCase()] : null;

  @override
  void operator []=(String key, int value) => _owner.setHostLimit(key, value);

  @override
  void clear() {
    for (final host in _owner._hostOverrides.keys.toList()) {
      _owner.setHostLimit(host, null);
    }
  }

  @override
  Iterable<String> get keys => _owner._hostOverrides.keys.toList();

  @override
  int? remove(Object? key) {
    if (key is! String) return null;
    final previous = this[key];
    _owner.setHostLimit(key, null);
    return previous;
  }
}

/// Byte-bounded LRU of response records for the current session.
class _MemoryCache {
  _MemoryCache(this.maxBytes);

  final int maxBytes;
  final LinkedHashMap<String, LibraryCacheRecord> _entries =
      LinkedHashMap<String, LibraryCacheRecord>();
  int _bytes = 0;

  LibraryCacheRecord? get(String key) {
    final record = _entries.remove(key);
    if (record != null) _entries[key] = record;
    return record;
  }

  void put(LibraryCacheRecord record) {
    remove(record.key);
    final size = record.body?.length ?? 0;
    // A single response may use at most a quarter of the budget so one large
    // page cannot flush everything else.
    if (record.body == null || size > maxBytes ~/ 4) return;
    _entries[record.key] = record;
    _bytes += size;
    while (_bytes > maxBytes && _entries.isNotEmpty) {
      remove(_entries.keys.first);
    }
  }

  void replaceIfPresent(LibraryCacheRecord record) {
    if (_entries.containsKey(record.key)) _entries[record.key] = record;
  }

  void remove(String key) {
    final removed = _entries.remove(key);
    if (removed != null) _bytes -= removed.body?.length ?? 0;
  }

  void clear() {
    _entries.clear();
    _bytes = 0;
  }
}

/// Metadata (and optionally the body) of one cached network response.
class LibraryCacheRecord {
  const LibraryCacheRecord({
    required this.key,
    required this.url,
    required this.finalUrl,
    required this.statusCode,
    required this.headers,
    required this.fetchedAt,
    required this.lastAccessAt,
    required this.size,
    this.body,
  });

  /// Response headers kept on disk (lower-case names).
  static const Set<String> storedHeaders = <String>{
    'content-type',
    'content-language',
    'content-disposition',
    'etag',
    'last-modified',
    'cache-control',
    'expires',
    'date',
    'vary',
    'link',
    'location',
  };

  /// Keeps only [storedHeaders] from [headers], with lower-case names.
  static Map<String, String> selectHeaders(Map<String, String> headers) {
    final selected = <String, String>{};
    headers.forEach((name, value) {
      final lower = name.toLowerCase();
      if (storedHeaders.contains(lower)) selected[lower] = value;
    });
    return Map<String, String>.unmodifiable(selected);
  }

  final String key;
  final String url;
  final String finalUrl;
  final int statusCode;
  final Map<String, String> headers;
  final DateTime fetchedAt;
  final DateTime lastAccessAt;

  /// Body length in bytes.
  final int size;
  final Uint8List? body;

  LibraryCacheRecord copyWith({
    Map<String, String>? headers,
    DateTime? fetchedAt,
    DateTime? lastAccessAt,
    Uint8List? body,
  }) {
    final nextBody = body ?? this.body;
    return LibraryCacheRecord(
      key: key,
      url: url,
      finalUrl: finalUrl,
      statusCode: statusCode,
      headers: headers ?? this.headers,
      fetchedAt: fetchedAt ?? this.fetchedAt,
      lastAccessAt: lastAccessAt ?? this.lastAccessAt,
      size: nextBody?.length ?? size,
      body: nextBody,
    );
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'v': 1,
    'key': key,
    'url': url,
    'finalUrl': finalUrl,
    'status': statusCode,
    'headers': headers,
    'fetchedAt': fetchedAt.toUtc().millisecondsSinceEpoch,
    'lastAccessAt': lastAccessAt.toUtc().millisecondsSinceEpoch,
    'size': size,
  };

  /// Returns null when [json] is not a valid record.
  static LibraryCacheRecord? fromJson(Object? json) {
    if (json is! Map) return null;
    final key = json['key'];
    final url = json['url'];
    final finalUrl = json['finalUrl'];
    final status = json['status'];
    final headers = json['headers'];
    final fetchedAt = json['fetchedAt'];
    final lastAccessAt = json['lastAccessAt'];
    final size = json['size'];
    if (key is! String ||
        url is! String ||
        finalUrl is! String ||
        status is! int ||
        headers is! Map ||
        fetchedAt is! int ||
        lastAccessAt is! int ||
        size is! int ||
        size < 0) {
      return null;
    }
    final parsedHeaders = <String, String>{};
    for (final entry in headers.entries) {
      final name = entry.key;
      final value = entry.value;
      if (name is String && value is String) {
        parsedHeaders[name.toLowerCase()] = value;
      }
    }
    return LibraryCacheRecord(
      key: key,
      url: url,
      finalUrl: finalUrl,
      statusCode: status,
      headers: Map<String, String>.unmodifiable(parsedHeaders),
      fetchedAt: DateTime.fromMillisecondsSinceEpoch(fetchedAt, isUtc: true),
      lastAccessAt: DateTime.fromMillisecondsSinceEpoch(
        lastAccessAt,
        isUtc: true,
      ),
      size: size,
    );
  }
}

/// Size-limited persistent store of response bodies, shared by
/// [LibraryHttp] and the Library image cache.
///
/// Each entry is `<sha1(key)>.bin` (body) plus `<sha1(key)>.json` (a small
/// [LibraryCacheRecord]). Writes go to a temporary file renamed into place,
/// body first then metadata; every operation on one entry is serialised in
/// this process. An entry whose metadata is unreadable or whose body length
/// differs from the metadata is treated as a miss and deleted.
///
/// The store only touches files named after a SHA-1 stem in its own
/// directory, so other files placed there (e.g. a pin list) are never
/// trimmed or cleared.
class LibraryDiskCache {
  LibraryDiskCache(
    this._resolveDirectory, {
    required int maxBytes,
    DateTime Function()? clock,
    Future<Set<String>> Function()? keepKeys,
  }) : maxBytes = math.max(0, maxBytes),
       _clock = clock ?? DateTime.now,
       _keepKeys = keepKeys;

  static const String metaExtension = '.json';
  static const String bodyExtension = '.bin';
  static const String _tmpExtension = '.tmp';

  /// Temporary or half-written files younger than this are left alone by
  /// [trim] because a write may still be in progress.
  static const Duration orphanGrace = Duration(minutes: 10);

  static final RegExp _stemPattern = RegExp(r'^[0-9a-f]{40}$');
  static final math.Random _random = math.Random();

  /// Size limit enforced automatically after writes (down to 90 %).
  final int maxBytes;
  final Future<Directory> Function() _resolveDirectory;
  final DateTime Function() _clock;
  final Future<Set<String>> Function()? _keepKeys;
  final Map<String, Future<void>> _locks = <String, Future<void>>{};
  Directory? _directory;
  Future<Directory?>? _opening;
  int? _trackedBytes;
  Future<void>? _maintenance;
  bool _maintenanceAgain = false;
  int _growthDuringMaintenance = 0;
  final Set<Future<void>> _background = <Future<void>>{};

  static String stemFor(String key) =>
      sha1.convert(utf8.encode(key)).toString();

  /// The store directory, created on first use. Null when it cannot be
  /// resolved or created (the cache then behaves as always empty).
  Future<Directory?> directory() async {
    final ready = _directory;
    if (ready != null) return ready;
    final opening = _opening ??= _open();
    final directory = await opening;
    if (directory == null) {
      _opening = null;
    } else {
      _directory = directory;
    }
    return directory;
  }

  Future<Directory?> _open() async {
    try {
      final directory = await _resolveDirectory();
      await directory.create(recursive: true);
      return directory;
    } catch (_) {
      return null;
    }
  }

  File _metaFile(Directory directory, String stem) =>
      File(p.join(directory.path, '$stem$metaExtension'));

  File _bodyFile(Directory directory, String stem) =>
      File(p.join(directory.path, '$stem$bodyExtension'));

  Future<T> _locked<T>(String stem, Future<T> Function() action) {
    final previous = _locks[stem] ?? Future<void>.value();
    final done = Completer<void>();
    _locks[stem] = done.future;
    return previous.then((_) => action()).whenComplete(() {
      done.complete();
      if (identical(_locks[stem], done.future)) _locks.remove(stem);
    });
  }

  /// Reads metadata and body, or null on a miss. Corrupt entries are
  /// deleted.
  Future<LibraryCacheRecord?> read(String key) async {
    final directory = await this.directory();
    if (directory == null) return null;
    final stem = stemFor(key);
    return _locked(stem, () async {
      final metaFile = _metaFile(directory, stem);
      final bodyFile = _bodyFile(directory, stem);
      try {
        if (!await metaFile.exists()) {
          if (await bodyFile.exists()) await _deleteQuietly(bodyFile);
          return null;
        }
        final meta = LibraryCacheRecord.fromJson(
          jsonDecode(await metaFile.readAsString()),
        );
        if (meta != null && meta.key == key) {
          final body = await bodyFile.readAsBytes();
          if (body.length == meta.size) return meta.copyWith(body: body);
        }
      } catch (_) {
        // Falls through to deletion.
      }
      await _deleteStemFiles(directory, stem);
      return null;
    });
  }

  /// Reads only the metadata (no body), or null.
  Future<LibraryCacheRecord?> readMeta(String key) async {
    final directory = await this.directory();
    if (directory == null) return null;
    final stem = stemFor(key);
    return _locked(stem, () async {
      try {
        final meta = LibraryCacheRecord.fromJson(
          jsonDecode(await _metaFile(directory, stem).readAsString()),
        );
        if (meta == null || meta.key != key) return null;
        final length = await _bodyFile(directory, stem).length();
        return length == meta.size ? meta : null;
      } catch (_) {
        return null;
      }
    });
  }

  /// Stores [record] (its body is required). Returns false when the entry
  /// could not be written or is larger than [maxBytes].
  Future<bool> write(LibraryCacheRecord record) async {
    final body = record.body;
    if (body == null) {
      throw ArgumentError.value(record, 'record', 'body is required');
    }
    if (body.length > maxBytes) return false;
    final directory = await this.directory();
    if (directory == null) return false;
    final stem = stemFor(record.key);
    final meta = utf8.encode(jsonEncode(record.copyWith(body: body).toJson()));
    final written = await _locked(stem, () async {
      try {
        await _atomicWrite(_bodyFile(directory, stem), body);
        await _atomicWrite(_metaFile(directory, stem), meta);
        return true;
      } catch (_) {
        await _deleteStemFiles(directory, stem);
        return false;
      }
    });
    if (written) _noteGrowth(body.length + meta.length);
    return written;
  }

  /// Rewrites the metadata of an existing entry (headers, dates). Returns
  /// false when the entry is missing; the body is left untouched.
  Future<bool> updateMeta(LibraryCacheRecord record) async {
    final directory = await this.directory();
    if (directory == null) return false;
    final stem = stemFor(record.key);
    return _locked(stem, () async {
      try {
        final current = LibraryCacheRecord.fromJson(
          jsonDecode(await _metaFile(directory, stem).readAsString()),
        );
        if (current == null || current.key != record.key) return false;
        final length = await _bodyFile(directory, stem).length();
        if (length != current.size) return false;
        final next = LibraryCacheRecord(
          key: current.key,
          url: current.url,
          finalUrl: current.finalUrl,
          statusCode: current.statusCode,
          headers: record.headers,
          fetchedAt: record.fetchedAt,
          lastAccessAt: record.lastAccessAt,
          size: current.size,
        );
        await _atomicWrite(
          _metaFile(directory, stem),
          utf8.encode(jsonEncode(next.toJson())),
        );
        return true;
      } catch (_) {
        return false;
      }
    });
  }

  /// Records a use of [key] for LRU trimming. [idle] waits for it.
  Future<bool> touch(String key, DateTime at) {
    final operation = _touch(key, at);
    final tracked = operation.then<void>((_) {}, onError: (Object _) {});
    _background.add(tracked);
    unawaited(tracked.whenComplete(() => _background.remove(tracked)));
    return operation;
  }

  Future<bool> _touch(String key, DateTime at) async {
    final directory = await this.directory();
    if (directory == null) return false;
    final stem = stemFor(key);
    return _locked(stem, () async {
      try {
        final metaFile = _metaFile(directory, stem);
        final current = LibraryCacheRecord.fromJson(
          jsonDecode(await metaFile.readAsString()),
        );
        if (current == null || current.key != key) return false;
        await _atomicWrite(
          metaFile,
          utf8.encode(jsonEncode(current.copyWith(lastAccessAt: at).toJson())),
        );
        return true;
      } catch (_) {
        return false;
      }
    });
  }

  Future<void> remove(String key) async {
    final directory = await this.directory();
    if (directory == null) return;
    final stem = stemFor(key);
    await _locked(stem, () => _deleteStemFiles(directory, stem));
    _trackedBytes = null;
  }

  /// Bytes used by entries (and in-progress temporary files).
  Future<int> sizeBytes() async {
    final directory = await this.directory();
    if (directory == null) return 0;
    var total = 0;
    try {
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is! File || _stemOf(entity) == null) continue;
        try {
          total += await entity.length();
        } catch (_) {}
      }
    } catch (_) {}
    return total;
  }

  /// Deletes least recently used entries (by `lastAccessAt`) until the store
  /// fits [maxBytes], never deleting keys returned by `keepKeys`. Also
  /// removes stale temporary files and broken entries. Returns the size left.
  Future<int> trim({int? maxBytes}) async {
    final limit = math.max(0, maxBytes ?? this.maxBytes);
    final directory = await this.directory();
    if (directory == null) return 0;
    final keep = await _keep();
    final groups = await _scan(directory);
    final now = DateTime.now();
    final candidates = <_TrimCandidate>[];
    var total = 0;

    for (final group in groups.values) {
      for (final tmp in group.temporary) {
        if (now.difference(tmp.modified) > orphanGrace) {
          await _deleteQuietly(tmp.file);
        } else {
          total += tmp.size;
        }
      }
      final meta = group.meta;
      final body = group.body;
      if (meta == null || body == null) {
        final present = meta ?? body;
        if (present == null) continue;
        if (now.difference(present.modified) > orphanGrace) {
          await _locked(
            group.stem,
            () => _deleteIfBroken(directory, group.stem),
          );
        } else {
          total += present.size;
        }
        continue;
      }
      LibraryCacheRecord? record;
      try {
        record = LibraryCacheRecord.fromJson(
          jsonDecode(await meta.file.readAsString()),
        );
      } catch (_) {
        record = null;
      }
      if (record == null ||
          record.size != body.size ||
          stemFor(record.key) != group.stem) {
        final deleted = await _locked(
          group.stem,
          () => _deleteIfBroken(directory, group.stem),
        );
        if (!deleted) total += meta.size + body.size;
        continue;
      }
      final size = meta.size + body.size;
      total += size;
      if (!keep.contains(record.key)) {
        candidates.add(_TrimCandidate(group.stem, record.lastAccessAt, size));
      }
    }

    if (total > limit) {
      candidates.sort((a, b) => a.lastAccessAt.compareTo(b.lastAccessAt));
      for (final candidate in candidates) {
        if (total <= limit) break;
        await _locked(
          candidate.stem,
          () => _deleteStemFiles(directory, candidate.stem),
        );
        total -= candidate.size;
      }
    }
    _trackedBytes = total;
    return total;
  }

  /// Removes every entry except keys returned by `keepKeys` (unless
  /// [includeKept]) and [alsoKeep].
  Future<void> clear({
    Set<String> alsoKeep = const <String>{},
    bool includeKept = false,
  }) async {
    final directory = await this.directory();
    if (directory == null) return;
    final keep = <String>{if (!includeKept) ...await _keep(), ...alsoKeep};
    final groups = await _scan(directory);
    for (final group in groups.values) {
      if (keep.isNotEmpty && group.meta != null) {
        try {
          final record = LibraryCacheRecord.fromJson(
            jsonDecode(await group.meta!.file.readAsString()),
          );
          if (record != null && keep.contains(record.key)) continue;
        } catch (_) {}
      }
      await _locked(group.stem, () => _deleteStemFiles(directory, group.stem));
    }
    _trackedBytes = null;
  }

  Future<Set<String>> _keep() async {
    final provider = _keepKeys;
    if (provider == null) return const <String>{};
    try {
      return await provider();
    } catch (_) {
      return const <String>{};
    }
  }

  void _noteGrowth(int bytes) {
    if (_maintenance != null) {
      // The running scan may have missed this write: account for it once
      // the scan result is known.
      _growthDuringMaintenance += bytes;
      _maintenanceAgain = true;
      return;
    }
    final tracked = _trackedBytes;
    if (tracked == null) {
      _scheduleMaintenance();
      return;
    }
    _trackedBytes = tracked + bytes;
    if (_trackedBytes! > maxBytes) _scheduleMaintenance();
  }

  void _scheduleMaintenance() {
    if (_maintenance != null) {
      _maintenanceAgain = true;
      return;
    }
    _growthDuringMaintenance = 0;
    _maintenance = _maintain().whenComplete(() {
      _maintenance = null;
      final growth = _growthDuringMaintenance;
      final again = _maintenanceAgain;
      _growthDuringMaintenance = 0;
      _maintenanceAgain = false;
      final tracked = _trackedBytes;
      // May over-count a write the scan already saw; an extra scan then
      // corrects the estimate.
      if (tracked != null) _trackedBytes = tracked + growth;
      if (again && (_trackedBytes ?? maxBytes + 1) > maxBytes) {
        _scheduleMaintenance();
      }
    });
  }

  Future<void> _maintain() async {
    try {
      final size = await sizeBytes();
      _trackedBytes = size;
      if (size > maxBytes) await trim(maxBytes: (maxBytes * 9) ~/ 10);
    } catch (_) {
      _trackedBytes = null;
    }
  }

  /// Completes when access-time updates and automatic trimming scheduled by
  /// previous operations are done (tests and shutdown).
  Future<void> idle() async {
    while (_maintenance != null || _background.isNotEmpty) {
      if (_background.isNotEmpty) {
        await Future.wait(_background.toList());
      }
      final maintenance = _maintenance;
      if (maintenance != null) await maintenance;
    }
  }

  Future<Map<String, _StemGroup>> _scan(Directory directory) async {
    final groups = <String, _StemGroup>{};
    try {
      await for (final entity in directory.list(followLinks: false)) {
        if (entity is! File) continue;
        final stem = _stemOf(entity);
        if (stem == null) continue;
        final FileStat stat;
        try {
          stat = await entity.stat();
        } catch (_) {
          continue;
        }
        final info = _FileInfo(entity, stat.size, stat.modified);
        final group = groups.putIfAbsent(stem, () => _StemGroup(stem));
        final name = p.basename(entity.path);
        final suffix = name.substring(stem.length);
        if (suffix == metaExtension) {
          group.meta = info;
        } else if (suffix == bodyExtension) {
          group.body = info;
        } else {
          group.temporary.add(info);
        }
      }
    } catch (_) {}
    return groups;
  }

  static String? _stemOf(File file) {
    final name = p.basename(file.path);
    final dot = name.indexOf('.');
    if (dot != 40) return null;
    final stem = name.substring(0, dot);
    if (!_stemPattern.hasMatch(stem)) return null;
    final suffix = name.substring(dot);
    if (suffix == metaExtension ||
        suffix == bodyExtension ||
        suffix.endsWith(_tmpExtension)) {
      return stem;
    }
    return null;
  }

  Future<bool> _deleteIfBroken(Directory directory, String stem) async {
    try {
      final meta = LibraryCacheRecord.fromJson(
        jsonDecode(await _metaFile(directory, stem).readAsString()),
      );
      final length = await _bodyFile(directory, stem).length();
      if (meta != null && meta.size == length && stemFor(meta.key) == stem) {
        return false;
      }
    } catch (_) {}
    await _deleteStemFiles(directory, stem);
    return true;
  }

  Future<void> _deleteStemFiles(Directory directory, String stem) async {
    await _deleteQuietly(_metaFile(directory, stem));
    await _deleteQuietly(_bodyFile(directory, stem));
  }

  static Future<void> _deleteQuietly(File file) async {
    try {
      if (await file.exists()) await file.delete();
    } catch (_) {}
  }

  Future<void> _atomicWrite(File target, List<int> bytes) async {
    final suffix =
        '${_clock().microsecondsSinceEpoch.toRadixString(36)}'
        '${_random.nextInt(1 << 32).toRadixString(36)}';
    final tmp = File('${target.path}.$suffix$_tmpExtension');
    try {
      await tmp.writeAsBytes(bytes);
      await tmp.rename(target.path);
    } catch (_) {
      await _deleteQuietly(tmp);
      rethrow;
    }
  }
}

class _FileInfo {
  const _FileInfo(this.file, this.size, this.modified);

  final File file;
  final int size;
  final DateTime modified;
}

class _StemGroup {
  _StemGroup(this.stem);

  final String stem;
  _FileInfo? meta;
  _FileInfo? body;
  final List<_FileInfo> temporary = <_FileInfo>[];
}

class _TrimCandidate {
  const _TrimCandidate(this.stem, this.lastAccessAt, this.size);

  final String stem;
  final DateTime lastAccessAt;
  final int size;
}
