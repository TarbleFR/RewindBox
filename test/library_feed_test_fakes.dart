// Shared fakes for the Library hub/feed tests: a scriptable
// LibraryCatalogFeedBackend (no network, no plugins) and small builders for
// addons, items and pages.
import 'dart:async';

import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';

LibraryAddon aidokuTestAddon(
  String sourceId, {
  String? name,
  int contentRating = 0,
  Object? nsfw,
  List<String> languages = const <String>['fr'],
}) {
  return LibraryAddon(
    id: 'aidoku.$sourceId',
    name: name ?? sourceId,
    version: '1',
    baseUrl: 'https://example.com/',
    description: '',
    iconUrl: null,
    origin: 'https://example.com/index.min.json',
    installedAt: DateTime.utc(2026, 10, 10),
    manifest: <String, dynamic>{
      'iosCompatibility': 'metadata-only',
      'provider': <String, dynamic>{
        'type': LibraryAddon.aidokuProviderType,
        'sourceId': sourceId,
        'languages': languages,
        'contentRating': contentRating,
        'nsfw': nsfw ?? contentRating,
        'repositoryOrigin': 'https://example.com/index.min.json',
      },
    },
  );
}

LibraryAddon catalogTestAddon(String id, {String? name, bool gallica = false}) {
  return LibraryAddon(
    id: id,
    name: name ?? id,
    version: '1',
    baseUrl: 'https://catalog.example.com/',
    description: '',
    iconUrl: null,
    origin: 'file:$id.json',
    installedAt: DateTime.utc(2026, 10, 10),
    manifest: <String, dynamic>{
      'endpoints': <String, dynamic>{'catalog': 'catalog.json'},
      if (gallica)
        'provider': <String, dynamic>{'type': LibraryAddon.gallicaProviderType},
    },
  );
}

LibraryCatalogItem testItem(
  String id, {
  String? title,
  Map<String, dynamic> raw = const <String, dynamic>{},
  String? coverUrl,
}) {
  return LibraryCatalogItem(
    id: id,
    title: title ?? id,
    mediaType: LibraryMediaType.manga,
    subtitle: '',
    description: '',
    coverUrl: coverUrl,
    content: null,
    contentUrl: null,
    pageUrls: const <String>[],
    raw: raw,
  );
}

LibraryMangaCatalogPage testPage(
  List<LibraryCatalogItem> items, {
  int page = 1,
  bool hasMore = true,
  bool stale = false,
  bool fromCache = false,
  DateTime? fetchedAt,
}) {
  return LibraryMangaCatalogPage(
    items: items,
    page: page,
    hasMore: hasMore,
    stale: stale,
    fromCache: fromCache,
    fetchedAt: fetchedAt,
  );
}

/// One recorded backend call.
class FeedCall {
  FeedCall(
    this.kind,
    this.sourceKey, {
    this.page = 1,
    this.query = '',
    this.mode,
    this.cancel,
  });

  /// `cache`, `page`, `catalog`, `catalogCache` or `metadata`.
  final String kind;
  final String sourceKey;
  final int page;
  final String query;
  final LibraryFetchMode? mode;
  final LibraryCancelToken? cancel;

  @override
  String toString() =>
      '$kind:$sourceKey:p$page${query.isEmpty ? '' : ':$query'}';
}

typedef AidokuPageHandler =
    Future<LibraryMangaCatalogPage> Function(FeedCall call);

/// Scriptable backend. Unknown requests throw so every access is explicit.
class FakeFeedBackend extends LibraryCatalogFeedBackend {
  FakeFeedBackend();

  final List<FeedCall> calls = <FeedCall>[];

  /// Cached page 1 per source id (null: cache miss).
  final Map<String, LibraryMangaCatalogPage> cachedPages =
      <String, LibraryMangaCatalogPage>{};

  /// Page handler per source id; receives every listing/search call.
  final Map<String, AidokuPageHandler> pages = <String, AidokuPageHandler>{};

  /// Verified support per source id (defaults: working adapter).
  final Map<String, LibrarySourceSupport> support =
      <String, LibrarySourceSupport>{};

  final Map<String, List<LibraryCatalogItem>> cachedCatalogs =
      <String, List<LibraryCatalogItem>>{};
  final Map<String, Future<List<LibraryCatalogItem>> Function(FeedCall)>
  catalogs = <String, Future<List<LibraryCatalogItem>> Function(FeedCall)>{};

  Map<String, String> providers = <String, String>{};
  final Map<String, Future<List<LibraryCatalogItem>> Function(String query)>
  metadataSearch =
      <String, Future<List<LibraryCatalogItem>> Function(String query)>{};

  Iterable<FeedCall> callsOf(String kind) =>
      calls.where((call) => call.kind == kind);

  static String _sourceId(LibraryAddon addon) =>
      addon.aidokuSourceId ?? addon.id;

  @override
  bool isAidokuBrowsable(LibraryAddon addon) =>
      addon.isAidokuRepositorySource &&
      (support[_sourceId(addon)]?.hasAdapter ?? true);

  @override
  LibrarySourceSupport? aidokuSupport(LibraryAddon addon) =>
      support[_sourceId(addon)];

  @override
  Future<LibraryMangaCatalogPage?> cachedAidokuPage(LibraryAddon addon) async {
    calls.add(FeedCall('cache', addon.id));
    return cachedPages[_sourceId(addon)];
  }

  @override
  Future<LibraryMangaCatalogPage> loadAidokuPage(
    LibraryAddon addon, {
    int page = 1,
    String query = '',
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) {
    final call = FeedCall(
      'page',
      addon.id,
      page: page,
      query: query,
      mode: mode,
      cancel: cancel,
    );
    calls.add(call);
    final handler = pages[_sourceId(addon)];
    if (handler == null) {
      return Future<LibraryMangaCatalogPage>.error(
        StateError('no page handler for ${addon.id}'),
      );
    }
    return handler(call);
  }

  @override
  Future<List<LibraryCatalogItem>?> cachedCatalog(LibraryAddon addon) async {
    calls.add(FeedCall('catalogCache', addon.id));
    return cachedCatalogs[addon.id];
  }

  @override
  Future<List<LibraryCatalogItem>> loadCatalog(
    LibraryAddon addon, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) {
    final call = FeedCall('catalog', addon.id, mode: mode, cancel: cancel);
    calls.add(call);
    final handler = catalogs[addon.id];
    if (handler == null) {
      return Future<List<LibraryCatalogItem>>.error(
        StateError('no catalog handler for ${addon.id}'),
      );
    }
    return handler(call);
  }

  @override
  Future<void> initializeMetadata() async {}

  @override
  Map<String, String> metadataProviders() => providers;

  @override
  Future<List<LibraryCatalogItem>> searchMetadata(
    String providerId,
    String query,
  ) {
    calls.add(FeedCall('metadata', 'provider:$providerId', query: query));
    final handler = metadataSearch[providerId];
    if (handler == null) return Future.value(const <LibraryCatalogItem>[]);
    return handler(query);
  }
}

/// Verified support entry used to mark a test source as blocked.
LibrarySourceSupport blockedSupport(
  String sourceId,
  LibrarySourceKnownState state,
) {
  return LibrarySourceSupport(
    sourceId: sourceId,
    name: sourceId,
    engine: LibrarySourceEngine.madara,
    hasAdapter: true,
    knownState: state,
    websiteUrl: 'https://example.com/',
    verifiedOn: DateTime.utc(2026, 10, 10),
    evidence: 'HTTP 403 cf-mitigated: challenge',
  );
}

/// Settable clock for freshness rules.
class TestClock {
  TestClock([DateTime? start]) : now = start ?? DateTime.utc(2026, 10, 11, 12);
  DateTime now;
  DateTime call() => now;
  void advance(Duration duration) => now = now.add(duration);
}

/// Lets queued microtasks and zero-delay timers run.
Future<void> settle([int rounds = 5]) async {
  for (var i = 0; i < rounds; i++) {
    await Future<void>.delayed(Duration.zero);
  }
}

/// A page answered when [complete] is called.
class PendingPage {
  final Completer<LibraryMangaCatalogPage> completer =
      Completer<LibraryMangaCatalogPage>();
  void complete(LibraryMangaCatalogPage page) => completer.complete(page);
  void fail(Object error) => completer.completeError(error);
}
