import 'dart:async';
import 'dart:collection';

import 'package:flutter/foundation.dart';

import 'library_addon_service.dart';
import 'library_aidoku_native_service.dart';
import 'library_catalog_service.dart';
import 'library_http.dart';
import 'library_metadata_provider_service.dart';

/// Where a catalogue entry comes from.
enum LibraryFeedSourceKind {
  /// Aidoku source read by a native NeoStation adapter.
  aidoku,

  /// NeoStation catalogue source (JSON catalogue, Gallica OPDS...).
  catalog,

  /// Metadata provider (search only).
  metadata,
}

/// Why a source could not be loaded. Services never return user text: the
/// UI translates these values and shows [LibraryFeedFailure.technical]
/// separately, untranslated.
enum LibraryFeedIssue {
  challenge,
  offline,
  timeout,
  serverUnavailable,
  notFound,
  httpStatus,
  tooLarge,
  invalidResponse,
  parseFailed,
  siteChanged,
  parked,
  unsupported,
  unknown,
}

/// Typed failure of one source.
@immutable
class LibraryFeedFailure {
  const LibraryFeedFailure(
    this.issue, {
    required this.at,
    this.statusCode,
    this.uri,
    this.detail,
    this.known = false,
    this.verifiedOn,
  });

  final LibraryFeedIssue issue;

  /// When the failure was observed (or, for [known], when it was recorded).
  final DateTime at;
  final int? statusCode;
  final Uri? uri;

  /// Raw technical detail (English, untranslated).
  final String? detail;

  /// Comes from the static verification registry, not from a request made
  /// by this feed.
  final bool known;

  /// Day the [known] state was verified.
  final DateTime? verifiedOn;

  /// Single untranslated line with the raw diagnostic (host, HTTP status,
  /// error detail).
  String get technical {
    final parts = <String>[
      issue.name,
      if (uri != null && uri!.host.isNotEmpty) uri!.host,
      if (statusCode != null) 'HTTP $statusCode',
      if (detail != null && detail!.trim().isNotEmpty) detail!.trim(),
    ];
    return parts.join(' · ');
  }

  /// Failures that make further requests pointless for a while (the site
  /// answers with an anti-bot page or cannot be reached at all).
  bool get isBlocking =>
      issue == LibraryFeedIssue.challenge ||
      issue == LibraryFeedIssue.offline ||
      issue == LibraryFeedIssue.parked;

  /// Maps any error thrown by the Library services; null for cancellations.
  static LibraryFeedFailure? fromError(Object error, DateTime at) {
    if (error is LibraryNetworkException) return _fromNetwork(error, at);
    if (error is LibrarySourceException) {
      final network = error.networkError;
      if (network != null) return _fromNetwork(network, at);
      return LibraryFeedFailure(
        switch (error.kind) {
          LibrarySourceErrorKind.unsupported => LibraryFeedIssue.unsupported,
          LibrarySourceErrorKind.parseFailed => LibraryFeedIssue.parseFailed,
          LibrarySourceErrorKind.invalidImage =>
            LibraryFeedIssue.invalidResponse,
          _ => LibraryFeedIssue.unknown,
        },
        at: at,
        uri: error.uri,
        detail: error.message,
      );
    }
    if (error is LibraryAddonException) {
      final network = error.network;
      if (network != null) return _fromNetwork(network, at);
      return LibraryFeedFailure(
        LibraryFeedIssue.unknown,
        at: at,
        detail: error.message,
      );
    }
    if (error is TimeoutException) {
      return LibraryFeedFailure(
        LibraryFeedIssue.timeout,
        at: at,
        detail: error.toString(),
      );
    }
    return LibraryFeedFailure(
      LibraryFeedIssue.unknown,
      at: at,
      detail: error.toString(),
    );
  }

  static LibraryFeedFailure? _fromNetwork(
    LibraryNetworkException error,
    DateTime at,
  ) {
    final issue = switch (error.kind) {
      LibraryNetworkErrorKind.cancelled => null,
      LibraryNetworkErrorKind.offline => LibraryFeedIssue.offline,
      LibraryNetworkErrorKind.timeout => LibraryFeedIssue.timeout,
      LibraryNetworkErrorKind.challenge => LibraryFeedIssue.challenge,
      LibraryNetworkErrorKind.serverUnavailable =>
        LibraryFeedIssue.serverUnavailable,
      LibraryNetworkErrorKind.notFound => LibraryFeedIssue.notFound,
      LibraryNetworkErrorKind.httpStatus => LibraryFeedIssue.httpStatus,
      LibraryNetworkErrorKind.tooLarge => LibraryFeedIssue.tooLarge,
      LibraryNetworkErrorKind.invalidResponse =>
        LibraryFeedIssue.invalidResponse,
    };
    if (issue == null) return null;
    return LibraryFeedFailure(
      issue,
      at: at,
      statusCode: error.statusCode,
      uri: error.uri,
      detail: error.detail,
    );
  }

  /// Failure recorded by the 2026-10-10 verification for a source that is
  /// not requested automatically ([LibraryCatalogFeed.isKnownBlocked]).
  static LibraryFeedFailure? fromKnownState(LibrarySourceSupport support) {
    final issue = switch (support.knownState) {
      LibrarySourceKnownState.challenge => LibraryFeedIssue.challenge,
      LibrarySourceKnownState.offline => LibraryFeedIssue.offline,
      LibrarySourceKnownState.parked => LibraryFeedIssue.parked,
      LibrarySourceKnownState.siteChanged => LibraryFeedIssue.siteChanged,
      _ => null,
    };
    if (issue == null) return null;
    final verified =
        support.verifiedOn ?? LibrarySourceSupportRegistry.verifiedOn;
    return LibraryFeedFailure(
      issue,
      at: verified,
      known: true,
      verifiedOn: verified,
      detail: support.evidence.isEmpty ? null : support.evidence,
    );
  }
}

/// Content filter rules ("safe mode").
///
/// Sources rated "primarily NSFW" (Aidoku content rating 2) are hidden as a
/// whole. Every other item is checked individually from its own flags and
/// from the VALUES of its title and genre-like fields; JSON key names (such
/// as a `"nsfw": 0` entry) are never matched.
abstract final class LibraryContentFilter {
  static bool sourceHiddenInSafeMode(LibraryAddon? addon) =>
      addon != null &&
      addon.contentRating >= LibraryAddon.contentRatingPrimarilyNsfw;

  /// Strict word list applied to titles and genre values only.
  static final RegExp strictWords = RegExp(
    r'(^|[^a-z0-9])(hentai|doujinshi|doujin|porn|porno|pornographic|pornography|xxx|nsfw|r[ -]?18|18\+|18 plus|adult(?:s)?(?:[ -]?only|[ -]?content)?|mature(?:[ -]?content)?|explicit(?:[ -]?content)?|uncensored|smut|erotic|erotica|ecchi|sexual(?:[ -]?content)?|sex|hardcore|fetish|bdsm|ahegao|futanari|lolicon|shotacon|oppai|netorare|ntr|incest|rape|non[ -]?consensual|tentacle|milf|nudity|nude)([^a-z0-9]|$)',
    caseSensitive: false,
  );

  static const List<String> _labelKeys = <String>[
    'genres',
    'genre',
    'categories',
    'tags',
    'labels',
    'ageRating',
    'rating',
    'contentWarning',
    'mangaType',
  ];

  static const List<String> _flagKeys = <String>[
    'explicitContent',
    'isAdult',
    'adult',
    'nsfw',
  ];

  /// True when [item] must be hidden in safe mode.
  static bool itemIsAdult(LibraryCatalogItem item) {
    final raw = item.raw;
    for (final key in _flagKeys) {
      if (raw[key] == true) return true;
    }
    if (LibraryContentRating.clamp(raw['contentRating']) >=
        LibraryContentRating.explicit) {
      return true;
    }
    final labels = <String>[];
    for (final key in _labelKeys) {
      _collectLabels(raw[key], labels);
    }
    if (labels.isNotEmpty) {
      if (LibraryContentRating.fromLabels(labels) >=
          LibraryContentRating.explicit) {
        return true;
      }
      for (final label in labels) {
        if (strictWords.hasMatch(label)) return true;
      }
    }
    return strictWords.hasMatch(item.title);
  }

  static void _collectLabels(
    Object? value,
    List<String> into, [
    int depth = 0,
  ]) {
    if (value == null || depth > 3) return;
    if (value is String) {
      final text = value.trim();
      if (text.isNotEmpty) into.add(text);
      return;
    }
    if (value is Iterable) {
      for (final element in value) {
        _collectLabels(element, into, depth + 1);
      }
      return;
    }
    if (value is Map) {
      // Values only (e.g. `{"name": "Hentai"}`); never the keys.
      for (final element in value.values) {
        _collectLabels(element, into, depth + 1);
      }
    }
  }
}

/// One title shown by the hub, with the values the filters need computed
/// once when it is inserted.
@immutable
class LibraryFeedEntry {
  const LibraryFeedEntry._({
    required this.sourceKey,
    required this.kind,
    required this.item,
    required this.identity,
    required this.foldedTitle,
    required this.languages,
    required this.languageBadge,
    required this.adult,
    required this.sourceAdult,
    required this.firstLetter,
    required this.imageHeaders,
    this.addon,
    this.providerId,
  });

  factory LibraryFeedEntry.create({
    required String sourceKey,
    required LibraryFeedSourceKind kind,
    required LibraryCatalogItem item,
    LibraryAddon? addon,
    String? providerId,
  }) {
    final folded = LibraryContentRating.foldAccents(
      item.title.trim().toLowerCase(),
    );
    final languages = _languagesOf(item, addon);
    final badge = languages.isEmpty
        ? ''
        : languages.take(2).map((code) => code.toUpperCase()).join(' • ');
    return LibraryFeedEntry._(
      sourceKey: sourceKey,
      kind: kind,
      item: item,
      addon: addon,
      providerId: providerId,
      identity: '$sourceKey|${item.id}',
      foldedTitle: folded,
      languages: languages,
      languageBadge: badge,
      adult: LibraryContentFilter.itemIsAdult(item),
      sourceAdult: LibraryContentFilter.sourceHiddenInSafeMode(addon),
      firstLetter: _firstLetterOf(folded),
      imageHeaders: _imageHeadersOf(item),
    );
  }

  /// Source key: the addon id, or `provider:<id>` for metadata providers.
  final String sourceKey;
  final LibraryFeedSourceKind kind;
  final LibraryCatalogItem item;
  final LibraryAddon? addon;
  final String? providerId;

  /// `<sourceKey>|<item id>`, unique within the feed.
  final String identity;

  /// Lower case, accents removed (search and sort).
  final String foldedTitle;

  /// ISO-639 codes (2-3 letters).
  final Set<String> languages;

  /// Up to two language codes for the cover badge ("FR • EN").
  final String languageBadge;

  /// Hidden in safe mode ([LibraryContentFilter.itemIsAdult]).
  final bool adult;

  /// The source is primarily NSFW (hidden as a whole in safe mode).
  final bool sourceAdult;

  /// Upper-case first letter of the folded title, or `#`.
  final String firstLetter;

  /// Headers for the cover request (`raw.imageHeaders`), null when none.
  final Map<String, String>? imageHeaders;

  static final RegExp _languageCode = RegExp(r'^[a-z]{2,3}$');
  static final RegExp _letter = RegExp(r'[a-z0-9]');

  static Set<String> _languagesOf(
    LibraryCatalogItem item,
    LibraryAddon? addon,
  ) {
    final result = <String>{};

    void add(Object? value, [int depth = 0]) {
      if (value == null || depth > 2) return;
      if (value is Iterable) {
        for (final element in value) {
          add(element, depth + 1);
        }
        return;
      }
      final raw = value.toString().trim().toLowerCase();
      if (raw.isEmpty || raw == 'null') return;
      final normalized = raw.replaceAll('_', '-').split('-').first;
      if (_languageCode.hasMatch(normalized)) result.add(normalized);
    }

    final raw = item.raw;
    add(raw['language']);
    add(raw['languages']);
    add(raw['lang']);
    final attributes = raw['attributes'];
    if (attributes is Map) {
      add(attributes['availableTranslatedLanguages']);
      add(attributes['translatedLanguage']);
      add(attributes['originalLanguage']);
      final titles = attributes['title'];
      if (titles is Map) add(titles.keys);
    }
    if (result.isEmpty && addon != null) {
      // Gallica's public-domain OPDS feed is primarily French even when an
      // Atom entry omits dc:language.
      if (addon.isGallicaSource) {
        result.add('fr');
      } else {
        final declared = addon.languages;
        if (declared.length == 1) add(declared.single);
      }
    }
    return Set<String>.unmodifiable(result);
  }

  static String _firstLetterOf(String folded) {
    if (folded.isEmpty) return '#';
    final first = folded.substring(0, 1);
    return _letter.hasMatch(first) ? first.toUpperCase() : '#';
  }

  static Map<String, String>? _imageHeadersOf(LibraryCatalogItem item) {
    final raw = item.raw['imageHeaders'];
    if (raw is! Map) return null;
    final result = <String, String>{};
    for (final entry in raw.entries) {
      final key = entry.key?.toString().trim() ?? '';
      final value = entry.value?.toString().trim() ?? '';
      if (key.isNotEmpty && value.isNotEmpty) result[key] = value;
    }
    return result.isEmpty ? null : Map<String, String>.unmodifiable(result);
  }
}

/// State of one browsable source of the catalogue feed.
class LibraryFeedSource {
  LibraryFeedSource._({
    required this.key,
    required this.kind,
    required LibraryAddon addon,
    this.support,
  }) : _addon = addon;

  final String key;
  final LibraryFeedSourceKind kind;
  LibraryAddon _addon;

  /// Static verification data for Aidoku sources.
  final LibrarySourceSupport? support;

  final List<LibraryFeedEntry> _entries = <LibraryFeedEntry>[];
  final Set<String> _identities = <String>{};
  int _nextPage = 1;
  bool _exhausted = false;
  bool _loading = false;

  /// A page-1 load waits in the queue (it must not be queued twice).
  bool _queued = false;

  /// The queued load was asked for by a manual refresh.
  bool _queuedManual = false;

  /// Identities of the last listing page received, to recognise a site that
  /// ignores the page number (it answers page 1 again).
  String? _lastPageSignature;

  /// Consecutive further pages that brought no new title.
  int _pagesWithoutNew = 0;
  bool _loadingMore = false;
  bool _slow = false;
  bool _cacheRead = false;
  bool _cacheFresh = false;
  LibraryFeedFailure? _failure;
  LibraryFeedFailure? _pageFailure;
  DateTime? _loadMoreRetryAt;
  DateTime? _lastSuccessAt;
  bool _fromCache = false;
  bool _stale = false;
  DateTime? _updatedAt;
  LibraryCancelToken? _token;
  LibraryCancelToken? _pageToken;

  LibraryAddon get addon => _addon;
  String get name =>
      _addon.name.trim().isEmpty ? _addon.id : _addon.name.trim();

  /// Entries in page order (page 1 first).
  List<LibraryFeedEntry> get entries =>
      List<LibraryFeedEntry>.unmodifiable(_entries);
  int get entryCount => _entries.length;

  /// Next listing page to request (1-based).
  int get nextPage => _nextPage;
  bool get exhausted => _exhausted;

  /// Page 1 is being requested.
  bool get loading => _loading;

  /// A further page is being requested.
  bool get loadingMore => _loadingMore;

  /// Page 1 is still loading after the first-paint timeout; it continues in
  /// the background without holding a queue slot.
  bool get slow => _slow;

  /// Last failure of page 1 (or the verified blocked state). Entries already
  /// shown stay visible.
  LibraryFeedFailure? get failure => _failure;

  /// Last failure of a further page.
  LibraryFeedFailure? get pageFailure => _pageFailure;

  /// Entries come from the persistent cache.
  bool get fromCache => _fromCache;

  /// The cached copy shown is older than its fresh window.
  bool get stale => _stale;

  /// When the entries shown were obtained from the site.
  DateTime? get updatedAt => _updatedAt;
}

/// Status of one source during a search.
enum LibraryFeedSearchStatus { searching, done, failed, skipped }

/// Results of one source for the current search.
class LibraryFeedSearchSource {
  LibraryFeedSearchSource._({
    required this.key,
    required this.name,
    required this.kind,
    this.addon,
    this.providerId,
    LibraryFeedSearchStatus status = LibraryFeedSearchStatus.searching,
    LibraryFeedFailure? failure,
  }) : _status = status,
       _failure = failure;

  final String key;
  final String name;
  final LibraryFeedSourceKind kind;
  final LibraryAddon? addon;
  final String? providerId;
  LibraryFeedSearchStatus _status;
  LibraryFeedFailure? _failure;
  List<LibraryFeedEntry> _entries = const <LibraryFeedEntry>[];

  LibraryFeedSearchStatus get status => _status;
  LibraryFeedFailure? get failure => _failure;
  List<LibraryFeedEntry> get entries => _entries;
}

/// The current search, published progressively per source.
class LibraryFeedSearch {
  LibraryFeedSearch._(this.query, this.generation, this.sources);

  final String query;
  final int generation;
  final List<LibraryFeedSearchSource> sources;

  bool get searching => sources.any(
    (source) => source.status == LibraryFeedSearchStatus.searching,
  );

  List<LibraryFeedEntry> get entries => <LibraryFeedEntry>[
    for (final source in sources) ...source._entries,
  ];
}

/// Scroll position and selection of one hub mode, kept while the Library
/// tab is rebuilt (the app rebuilds `LibraryScreen` on every tab change).
class LibraryFeedViewMemory {
  double scrollOffset = 0;
  int selectedIndex = 0;
  String? selectedIdentity;

  /// First visible title and its grid row when the view was left, so the
  /// position follows that title if titles were inserted meanwhile.
  String? anchorIdentity;
  int anchorRow = -1;
}

/// Hub state kept across tab switches.
class LibraryFeedHubMemory {
  final LibraryFeedViewMemory catalogue = LibraryFeedViewMemory();
  final LibraryFeedViewMemory search = LibraryFeedViewMemory();
  String languageFilter = 'all';
  String sourceFilter = 'all';
  bool sortAscending = true;
  bool searchMode = false;
  String query = '';

  /// Section shown inside the Library tab (`hub`, `sources`, `local`,
  /// `favorites`).
  String section = 'hub';
}

/// Data access used by [LibraryCatalogFeed]; tests replace it.
class LibraryCatalogFeedBackend {
  LibraryCatalogFeedBackend({
    LibraryAidokuNativeService? aidoku,
    LibraryCatalogService? catalog,
    LibraryMetadataProviderService? metadata,
  }) : _aidoku = aidoku,
       _catalog = catalog,
       _metadata = metadata;

  final LibraryAidokuNativeService? _aidoku;
  final LibraryCatalogService? _catalog;
  final LibraryMetadataProviderService? _metadata;

  LibraryAidokuNativeService get aidoku =>
      _aidoku ?? LibraryAidokuNativeService.instance;
  LibraryCatalogService get catalog =>
      _catalog ?? LibraryCatalogService.instance;
  LibraryMetadataProviderService get metadata =>
      _metadata ?? LibraryMetadataProviderService.instance;

  /// Aidoku source with a NeoStation adapter.
  bool isAidokuBrowsable(LibraryAddon addon) =>
      addon.isAidokuRepositorySource && aidoku.supports(addon);

  LibrarySourceSupport? aidokuSupport(LibraryAddon addon) =>
      aidoku.support(addon);

  /// NeoStation catalogue source (JSON catalogue, Gallica...).
  bool isCatalogBrowsable(LibraryAddon addon) =>
      !addon.isRepositorySource && addon.canBrowseOnIos;

  Future<LibraryMangaCatalogPage?> cachedAidokuPage(LibraryAddon addon) =>
      aidoku.cachedCatalogPage(addon);

  Future<LibraryMangaCatalogPage> loadAidokuPage(
    LibraryAddon addon, {
    int page = 1,
    String query = '',
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) => aidoku.loadCatalogPage(
    addon,
    page: page,
    query: query,
    mode: mode,
    cancel: cancel,
  );

  Future<List<LibraryCatalogItem>?> cachedCatalog(LibraryAddon addon) async {
    try {
      return await catalog.loadCatalog(addon, mode: LibraryFetchMode.cacheOnly);
    } on LibraryAddonException {
      return null;
    } on LibraryNetworkException {
      return null;
    }
  }

  Future<List<LibraryCatalogItem>> loadCatalog(
    LibraryAddon addon, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) => catalog.loadCatalog(addon, mode: mode, cancel: cancel);

  Future<void> initializeMetadata() async {
    try {
      await metadata.initialize();
    } catch (_) {
      // The Library stays usable without the imported provider registry.
    }
  }

  /// Imported metadata providers: id → display name.
  Map<String, String> metadataProviders() => metadata.providerLabels;

  Future<List<LibraryCatalogItem>> searchMetadata(
    String providerId,
    String query,
  ) => metadata.searchProvider(providerId, query);
}

class _QueuedTask {
  _QueuedTask(this.run, this.onSlow);

  final Future<void> Function() run;
  final void Function()? onSlow;
  final Completer<void> done = Completer<void>();
}

/// Catalogue feed of the Library hub.
///
/// A process-wide [ChangeNotifier] (the hub widget is rebuilt on every tab
/// change; this state survives it). Every source is first shown from the
/// persistent cache, then refreshed through a bounded queue; each source is
/// published as soon as it completes, without waiting for the others.
class LibraryCatalogFeed extends ChangeNotifier {
  LibraryCatalogFeed({
    LibraryCatalogFeedBackend? backend,
    DateTime Function()? clock,
    this.maxConcurrentSources = 3,
    this.firstPaintTimeout = const Duration(seconds: 8),
    this.freshWindow = const Duration(minutes: 15),
    this.blockedRetryAfter = const Duration(minutes: 10),
    this.failureRetryAfter = const Duration(minutes: 1),
    this.maxConcurrentPages = 2,
    this.loadMoreThrottle = const Duration(milliseconds: 250),
    this.pageRetryAfter = const Duration(seconds: 30),
    this.searchTimeout = const Duration(seconds: 10),
    this.maxConcurrentSearches = 4,
    this.minQueryLength = 2,
    this.maxPagesWithoutNew = 3,
  }) : backend = backend ?? LibraryCatalogFeedBackend(),
       _clock = clock ?? DateTime.now;

  static LibraryCatalogFeed? _instance;

  /// Feed of the app. Tests may replace it.
  static LibraryCatalogFeed get instance => _instance ??= LibraryCatalogFeed();
  static set instance(LibraryCatalogFeed value) => _instance = value;

  final LibraryCatalogFeedBackend backend;
  final DateTime Function() _clock;

  /// Page-1 requests running at once (a slow source frees its slot after
  /// [firstPaintTimeout]).
  final int maxConcurrentSources;
  final Duration firstPaintTimeout;

  /// A source refreshed less than this ago is not requested again
  /// automatically (same window as `LibraryCachePolicy.listing`).
  final Duration freshWindow;

  /// Pause after a challenge/offline failure before automatic retries.
  final Duration blockedRetryAfter;

  /// Pause after any other failure before automatic retries.
  final Duration failureRetryAfter;
  final int maxConcurrentPages;
  final Duration loadMoreThrottle;
  final Duration pageRetryAfter;
  final Duration searchTimeout;
  final int maxConcurrentSearches;
  final int minQueryLength;

  /// Consecutive further pages without any new title after which a listing
  /// is considered finished.
  final int maxPagesWithoutNew;

  /// Hub state kept across tab switches.
  final LibraryFeedHubMemory hubMemory = LibraryFeedHubMemory();

  final LinkedHashMap<String, LibraryFeedSource> _sources =
      LinkedHashMap<String, LibraryFeedSource>();
  final Queue<_QueuedTask> _queue = Queue<_QueuedTask>();
  int _running = 0;
  int _pagesInFlight = 0;
  int _roundRobin = 0;
  DateTime? _lastLoadMoreAt;
  Timer? _deferredLoadMore;
  String? _deferredPreferredKey;
  Map<String, String> _providers = const <String, String>{};
  bool _metadataReady = false;
  bool _safeMode = true;
  List<LibraryAddon> _addons = const <LibraryAddon>[];

  LibraryFeedSearch? _search;
  int _searchGeneration = 0;
  LibraryCancelToken? _searchToken;
  int _searchRunning = 0;
  final Queue<_QueuedTask> _searchQueue = Queue<_QueuedTask>();

  int _version = 0;
  int _contentVersion = 0;
  int _entriesBuiltFor = -1;
  List<LibraryFeedEntry> _entriesCache = const <LibraryFeedEntry>[];
  bool _notifyScheduled = false;
  bool _disposed = false;

  /// Increases on every published change.
  int get version => _version;

  /// Increases only when entries or search results change (memoization of
  /// the visible list).
  int get contentVersion => _contentVersion;

  /// Content filter: sources rated primarily NSFW are neither shown nor
  /// requested while it is on.
  bool get safeMode => _safeMode;
  set safeMode(bool value) {
    if (_safeMode == value) return;
    _safeMode = value;
    _changed(content: true);
    if (!value) {
      // Sources skipped while the filter was on are loaded now.
      unawaited(open(_addons));
    }
  }

  /// Browsable sources in addon order.
  List<LibraryFeedSource> get sources =>
      List<LibraryFeedSource>.unmodifiable(_sources.values);

  LibraryFeedSource? source(String key) => _sources[key];

  bool get hasSources => _sources.isNotEmpty;

  /// Imported metadata providers (search only): id → name.
  Map<String, String> get metadataProviders => _providers;

  /// Every catalogue entry, source by source in page order.
  List<LibraryFeedEntry> get entries {
    if (_entriesBuiltFor != _contentVersion) {
      _entriesBuiltFor = _contentVersion;
      _entriesCache = List<LibraryFeedEntry>.unmodifiable(<LibraryFeedEntry>[
        for (final source in _sources.values) ...source._entries,
      ]);
    }
    return _entriesCache;
  }

  /// A source hidden as a whole by the content filter.
  bool isHiddenBySafeMode(LibraryFeedSource source) =>
      _safeMode && LibraryContentFilter.sourceHiddenInSafeMode(source.addon);

  /// Page 1 of some visible source is loading and has not timed out.
  bool get isLoading => _sources.values.any(
    (source) => source._loading && !source._slow && !isHiddenBySafeMode(source),
  );

  /// Any page-1 request is still running (including slow ones).
  bool get isRefreshing => _sources.values.any((source) => source._loading);

  bool get isLoadingMore =>
      _sources.values.any((source) => source._loadingMore);

  /// Sources whose page 1 could not be loaded (or known to be blocked).
  List<LibraryFeedSource> get unavailableSources => <LibraryFeedSource>[
    for (final source in _sources.values)
      if (source._failure != null && !isHiddenBySafeMode(source)) source,
  ];

  int get unavailableCount => unavailableSources.length;

  /// Sources for which nothing is shown yet and nothing is loading.
  bool get allSourcesFailed {
    final visible = _sources.values
        .where((source) => !isHiddenBySafeMode(source))
        .toList();
    return visible.isNotEmpty &&
        visible.every(
          (source) =>
              source._entries.isEmpty &&
              !source._loading &&
              source._failure != null,
        );
  }

  /// Sources not requested automatically: verified as blocked on
  /// 2026-10-10 (anti-bot challenge, offline or parked domain).
  static bool isKnownBlocked(LibrarySourceSupport? support) {
    if (support == null) return false;
    return support.knownState == LibrarySourceKnownState.challenge ||
        support.knownState == LibrarySourceKnownState.offline ||
        support.knownState == LibrarySourceKnownState.parked;
  }

  /// The current search (null when the query is shorter than
  /// [minQueryLength]).
  LibraryFeedSearch? get currentSearch => _search;

  // ----------------------------------------------------------- catalogue --

  /// Shows every browsable source of [addons]: page 1 from the cache first,
  /// then refreshed in the background. Safe to call on every tab change:
  /// sources refreshed within [freshWindow] are not requested again.
  /// Completes when every page-1 request started here has finished.
  Future<void> open(List<LibraryAddon> addons) async {
    if (_disposed) return;
    _addons = List<LibraryAddon>.unmodifiable(addons);
    final metadata = _ensureMetadata();
    _reconcile(addons);
    final work = <Future<void>>[metadata];
    for (final source in _sources.values.toList()) {
      if (isHiddenBySafeMode(source)) continue;
      work.add(_openSource(source, manual: false));
    }
    await Future.wait(work);
  }

  /// Manual refresh: requests page 1 of every source again (including
  /// sources that failed recently or are known to be blocked), keeping the
  /// entries shown until the new ones replace them.
  Future<void> refresh() async {
    if (_disposed) return;
    final work = <Future<void>>[];
    for (final source in _sources.values.toList()) {
      if (isHiddenBySafeMode(source)) continue;
      source._loadMoreRetryAt = null;
      source._pageFailure = null;
      work.add(_openSource(source, manual: true));
    }
    await Future.wait(work);
  }

  Future<void> _ensureMetadata() async {
    if (_metadataReady) return;
    await backend.initializeMetadata();
    _metadataReady = true;
    final providers = Map<String, String>.unmodifiable(
      backend.metadataProviders(),
    );
    if (!mapEquals(providers, _providers)) {
      _providers = providers;
      _changed();
    }
  }

  /// Reloads the imported metadata providers (after an import).
  Future<void> reloadMetadataProviders() async {
    _metadataReady = false;
    await _ensureMetadata();
  }

  void _reconcile(List<LibraryAddon> addons) {
    final wanted = <String, LibraryAddon>{};
    final kinds = <String, LibraryFeedSourceKind>{};
    for (final addon in addons) {
      if (backend.isAidokuBrowsable(addon)) {
        wanted[addon.id] = addon;
        kinds[addon.id] = LibraryFeedSourceKind.aidoku;
      } else if (backend.isCatalogBrowsable(addon)) {
        wanted[addon.id] = addon;
        kinds[addon.id] = LibraryFeedSourceKind.catalog;
      }
    }
    var changed = false;
    for (final key in _sources.keys.toList()) {
      final existing = _sources[key]!;
      if (!wanted.containsKey(key) || kinds[key] != existing.kind) {
        existing._token?.cancel();
        existing._pageToken?.cancel();
        _sources.remove(key);
        changed = true;
      }
    }
    final ordered = <String, LibraryFeedSource>{};
    for (final entry in wanted.entries) {
      final existing = _sources[entry.key];
      if (existing != null) {
        existing._addon = entry.value;
        ordered[entry.key] = existing;
        continue;
      }
      final kind = kinds[entry.key]!;
      final support = kind == LibraryFeedSourceKind.aidoku
          ? backend.aidokuSupport(entry.value)
          : null;
      ordered[entry.key] = LibraryFeedSource._(
        key: entry.key,
        kind: kind,
        addon: entry.value,
        support: support,
      );
      changed = true;
    }
    if (!listEquals(ordered.keys.toList(), _sources.keys.toList())) {
      changed = true;
    }
    _sources
      ..clear()
      ..addAll(ordered);
    if (changed) _changed(content: true);
  }

  bool _isCurrent(LibraryFeedSource source) =>
      !_disposed && identical(_sources[source.key], source);

  Future<void> _openSource(
    LibraryFeedSource source, {
    required bool manual,
  }) async {
    if (!source._cacheRead) {
      source._cacheRead = true;
      await _readCache(source);
      if (!_isCurrent(source)) return;
    }
    if (source._loading) return;
    if (source._queued) {
      // Already waiting for a slot (e.g. a tab switch while 4+ sources
      // load): a manual refresh only upgrades the queued load.
      if (manual) source._queuedManual = true;
      return;
    }
    if (!manual && !_needsNetwork(source)) return;
    source
      .._queued = true
      .._queuedManual = manual;
    await _enqueue(
      _queue,
      () {
        final queuedManual = source._queuedManual;
        source
          .._queued = false
          .._queuedManual = false;
        return _loadFirstPage(source, manual: queuedManual);
      },
      onSlow: () {
        if (_isCurrent(source) && source._loading) {
          source._slow = true;
          _changed();
        }
      },
    );
  }

  Future<void> _readCache(LibraryFeedSource source) async {
    try {
      if (source.kind == LibraryFeedSourceKind.aidoku) {
        final page = await backend.cachedAidokuPage(source.addon);
        if (page == null || !_isCurrent(source) || source._entries.isNotEmpty) {
          return;
        }
        _replaceFirstPage(source, page.items);
        source._nextPage = 2;
        source._exhausted = !page.hasMore || page.items.isEmpty;
        source._lastPageSignature = _signatureOf(page.items);
        source._fromCache = true;
        source._stale = page.stale;
        source._updatedAt = page.fetchedAt;
        final fetched = page.fetchedAt;
        source._cacheFresh =
            !page.stale &&
            fetched != null &&
            _clock().difference(fetched) < freshWindow;
        _changed(content: true);
      } else {
        final items = await backend.cachedCatalog(source.addon);
        if (items == null ||
            !_isCurrent(source) ||
            source._entries.isNotEmpty) {
          return;
        }
        _replaceFirstPage(source, items);
        source._nextPage = 2;
        source._exhausted = true;
        source._fromCache = true;
        _changed(content: true);
      }
    } catch (_) {
      // A cache read never blocks the network refresh.
    }
  }

  bool _needsNetwork(LibraryFeedSource source) {
    final now = _clock();
    final success = source._lastSuccessAt;
    if (success != null && now.difference(success) < freshWindow) return false;
    // Verified as blocked: only a manual refresh requests it, until it has
    // answered once in this session. A failure of that manual attempt stays
    // shown instead of the verified state.
    if (success == null && isKnownBlocked(source.support)) {
      source._failure ??= LibraryFeedFailure.fromKnownState(source.support!);
      return false;
    }
    final failure = source._failure;
    if (failure != null && !failure.known) {
      final pause = failure.isBlocking ? blockedRetryAfter : failureRetryAfter;
      if (now.difference(failure.at) < pause) return false;
    }
    if (source._cacheFresh && success == null) {
      source._lastSuccessAt = source._updatedAt;
      return false;
    }
    return true;
  }

  Future<void> _loadFirstPage(
    LibraryFeedSource source, {
    required bool manual,
  }) async {
    if (!_isCurrent(source) || source._loading) return;
    final token = LibraryCancelToken();
    source._token?.cancel();
    source._token = token;
    source._loading = true;
    source._slow = false;
    _changed();
    try {
      if (source.kind == LibraryFeedSourceKind.aidoku) {
        final mode = manual || source._entries.isNotEmpty
            ? LibraryFetchMode.refresh
            : LibraryFetchMode.cacheFirst;
        final page = await backend.loadAidokuPage(
          source.addon,
          page: 1,
          mode: mode,
          cancel: token,
        );
        if (!_isCurrent(source) || token.isCancelled) return;
        final hadPages = source._nextPage > 2;
        _mergeFirstPage(source, page.items);
        if (!hadPages) {
          source._nextPage = 2;
          source._exhausted = !page.hasMore || page.items.isEmpty;
          source._lastPageSignature = _signatureOf(page.items);
          source._pagesWithoutNew = 0;
        }
        source._fromCache = page.fromCache;
        source._stale = page.stale;
        source._updatedAt = page.fetchedAt ?? _clock();
        if (!page.stale) {
          source._failure = null;
          source._lastSuccessAt = _clock();
        }
      } else {
        final items = await backend.loadCatalog(
          source.addon,
          mode: manual ? LibraryFetchMode.refresh : LibraryFetchMode.cacheFirst,
          cancel: token,
        );
        if (!_isCurrent(source) || token.isCancelled) return;
        _replaceFirstPage(source, items);
        source._nextPage = 2;
        source._exhausted = true;
        source._fromCache = false;
        source._stale = false;
        source._updatedAt = _clock();
        source._failure = null;
        source._lastSuccessAt = _clock();
      }
      _changed(content: true);
    } catch (error) {
      if (!_isCurrent(source)) return;
      final failure = LibraryFeedFailure.fromError(error, _clock());
      if (failure != null) {
        source._failure = failure;
        _changed();
      }
    } finally {
      if (_isCurrent(source) && identical(source._token, token)) {
        source._loading = false;
        source._slow = false;
        source._token = null;
        _changed();
      }
    }
  }

  void _replaceFirstPage(
    LibraryFeedSource source,
    List<LibraryCatalogItem> items,
  ) {
    source._entries.clear();
    source._identities.clear();
    _append(source, items);
  }

  /// New page 1 first, then every entry already shown that it does not
  /// contain (later pages keep their place).
  void _mergeFirstPage(
    LibraryFeedSource source,
    List<LibraryCatalogItem> items,
  ) {
    final previous = List<LibraryFeedEntry>.of(source._entries);
    source._entries.clear();
    source._identities.clear();
    _append(source, items);
    for (final entry in previous) {
      if (source._identities.add(entry.identity)) source._entries.add(entry);
    }
  }

  static String _signatureOf(List<LibraryCatalogItem> items) =>
      items.map((item) => item.id).join('\n');

  /// Appends the entries of [items] not shown yet; returns how many.
  int _append(LibraryFeedSource source, List<LibraryCatalogItem> items) {
    var added = 0;
    for (final item in items) {
      final entry = LibraryFeedEntry.create(
        sourceKey: source.key,
        kind: source.kind,
        item: item,
        addon: source.addon,
      );
      if (source._identities.add(entry.identity)) {
        source._entries.add(entry);
        added++;
      }
    }
    return added;
  }

  /// Sources [loadMore] may request now.
  List<LibraryFeedSource> _loadMoreCandidates(DateTime now) =>
      <LibraryFeedSource>[
        for (final source in _sources.values)
          if (source.kind == LibraryFeedSourceKind.aidoku &&
              !isHiddenBySafeMode(source) &&
              !source._exhausted &&
              !source._loading &&
              !source._loadingMore &&
              source._nextPage >= 2 &&
              source._failure == null &&
              (source._loadMoreRetryAt == null ||
                  !now.isBefore(source._loadMoreRetryAt!)))
            source,
      ];

  /// True when [loadMore] could request a page.
  bool get canLoadMore => _loadMoreCandidates(_clock()).isNotEmpty;

  /// Requests the next page of up to [maxConcurrentPages] sources in turn
  /// (round robin). Calls closer than [loadMoreThrottle] are coalesced into
  /// one call made when the pause ends. With [preferredSourceKey] only that
  /// source is requested.
  Future<void> loadMore({String? preferredSourceKey}) async {
    if (_disposed) return;
    final now = _clock();
    final last = _lastLoadMoreAt;
    final elapsed = last == null ? null : now.difference(last);
    if (elapsed != null && elapsed < loadMoreThrottle) {
      // Throttled: the latest request still runs once the pause is over,
      // so a page answered from the cache within the pause does not leave
      // the grid short with nothing left to trigger the next page.
      _deferredPreferredKey = preferredSourceKey;
      _deferredLoadMore ??= Timer(loadMoreThrottle - elapsed, () {
        _deferredLoadMore = null;
        if (!_disposed) {
          unawaited(_loadMoreNow(_deferredPreferredKey, _clock()));
        }
      });
      return;
    }
    await _loadMoreNow(preferredSourceKey, now);
  }

  Future<void> _loadMoreNow(String? preferredSourceKey, DateTime now) async {
    final capacity = maxConcurrentPages - _pagesInFlight;
    if (capacity <= 0) return;
    var candidates = _loadMoreCandidates(now);
    if (preferredSourceKey != null) {
      candidates = candidates
          .where((source) => source.key == preferredSourceKey)
          .toList();
    }
    if (candidates.isEmpty) return;
    _lastLoadMoreAt = now;
    final ordered = <LibraryFeedSource>[];
    if (candidates.length > 1) {
      final offset = _roundRobin % candidates.length;
      ordered
        ..addAll(candidates.skip(offset))
        ..addAll(candidates.take(offset));
    } else {
      ordered.addAll(candidates);
    }
    final selected = ordered.take(capacity).toList();
    _roundRobin += selected.length;
    await Future.wait(selected.map(_loadNextPage));
  }

  Future<void> _loadNextPage(LibraryFeedSource source) async {
    final pageNumber = source._nextPage;
    final token = LibraryCancelToken();
    source._pageToken = token;
    source._loadingMore = true;
    _pagesInFlight++;
    _changed();
    try {
      final page = await backend.loadAidokuPage(
        source.addon,
        page: pageNumber,
        cancel: token,
      );
      if (!_isCurrent(source) || token.isCancelled) return;
      final signature = _signatureOf(page.items);
      final repeated = signature == source._lastPageSignature;
      source._lastPageSignature = signature;
      final added = _append(source, page.items);
      source._pagesWithoutNew = added > 0 ? 0 : source._pagesWithoutNew + 1;
      if (page.items.isNotEmpty) source._nextPage = pageNumber + 1;
      // A page made only of titles already shown is normal after page 1 was
      // refreshed (new chapters push titles down a "latest" listing), so it
      // does not end the listing. The same page twice (a site ignoring the
      // page number) or several pages without anything new do.
      if (!page.hasMore ||
          page.items.isEmpty ||
          repeated ||
          source._pagesWithoutNew >= maxPagesWithoutNew) {
        source._exhausted = true;
      }
      source._pageFailure = null;
      _changed(content: added > 0);
    } catch (error) {
      if (!_isCurrent(source)) return;
      final failure = LibraryFeedFailure.fromError(error, _clock());
      if (failure != null) {
        source._pageFailure = failure;
        source._loadMoreRetryAt = _clock().add(
          failure.isBlocking ? blockedRetryAfter : pageRetryAfter,
        );
        _changed();
      }
    } finally {
      _pagesInFlight--;
      if (identical(source._pageToken, token)) source._pageToken = null;
      source._loadingMore = false;
      if (_isCurrent(source)) _changed();
    }
  }

  // -------------------------------------------------------------- search --

  /// Searches every searchable source for [query] and publishes each
  /// source's results as they arrive. A new call cancels the previous
  /// search; its late results are never applied. Queries shorter than
  /// [minQueryLength] clear the search.
  Future<void> search(String query) async {
    if (_disposed) return;
    final trimmed = query.trim();
    _cancelSearch();
    if (trimmed.length < minQueryLength) {
      if (_search != null) {
        _search = null;
        _changed(content: true);
      }
      return;
    }
    final generation = _searchGeneration;
    await _ensureMetadata();
    // A newer call (or clearSearch) may have run while the providers were
    // loading: it changed the generation.
    if (_disposed || generation != _searchGeneration) return;
    final token = LibraryCancelToken();
    _searchToken = token;
    final now = _clock();
    final searchSources = <LibraryFeedSearchSource>[];
    for (final source in _sources.values) {
      if (source.kind != LibraryFeedSourceKind.aidoku) continue;
      if (isHiddenBySafeMode(source)) continue;
      LibraryFeedFailure? skip;
      if (isKnownBlocked(source.support)) {
        skip = LibraryFeedFailure.fromKnownState(source.support!);
      } else {
        final failure = source._failure;
        if (failure != null &&
            !failure.known &&
            failure.isBlocking &&
            now.difference(failure.at) < blockedRetryAfter) {
          skip = failure;
        }
      }
      searchSources.add(
        LibraryFeedSearchSource._(
          key: source.key,
          name: source.name,
          kind: LibraryFeedSourceKind.aidoku,
          addon: source.addon,
          status: skip == null
              ? LibraryFeedSearchStatus.searching
              : LibraryFeedSearchStatus.skipped,
          failure: skip,
        ),
      );
    }
    for (final provider in _providers.entries) {
      searchSources.add(
        LibraryFeedSearchSource._(
          key: 'provider:${provider.key}',
          name: provider.value,
          kind: LibraryFeedSourceKind.metadata,
          providerId: provider.key,
        ),
      );
    }
    final search = LibraryFeedSearch._(
      trimmed,
      generation,
      List<LibraryFeedSearchSource>.unmodifiable(searchSources),
    );
    _search = search;
    _changed(content: true);
    final work = <Future<void>>[
      for (final source in searchSources)
        if (source._status == LibraryFeedSearchStatus.searching)
          _enqueue(_searchQueue, () => _searchSource(search, source, token)),
    ];
    await Future.wait(work);
  }

  /// Cancels the running search and forgets its results.
  void clearSearch() {
    _cancelSearch();
    if (_search != null) {
      _search = null;
      _changed(content: true);
    }
  }

  void _cancelSearch() {
    _searchGeneration++;
    _searchToken?.cancel();
    _searchToken = null;
    // Queued searches of an older query never start.
    for (final task in _searchQueue) {
      if (!task.done.isCompleted) task.done.complete();
    }
    _searchQueue.clear();
  }

  bool _searchIsCurrent(LibraryFeedSearch search, LibraryCancelToken token) =>
      !_disposed &&
      identical(_search, search) &&
      search.generation == _searchGeneration &&
      !token.isCancelled;

  Future<void> _searchSource(
    LibraryFeedSearch search,
    LibraryFeedSearchSource source,
    LibraryCancelToken parent,
  ) async {
    if (!_searchIsCurrent(search, parent)) return;
    final child = LibraryCancelToken();
    final unregister = parent.addCancelListener(child.cancel);
    var timedOut = false;
    final timer = Timer(searchTimeout, () {
      timedOut = true;
      child.cancel();
      if (_searchIsCurrent(search, parent) &&
          source._status == LibraryFeedSearchStatus.searching) {
        source._status = LibraryFeedSearchStatus.failed;
        source._failure = LibraryFeedFailure(
          LibraryFeedIssue.timeout,
          at: _clock(),
          detail: 'search > ${searchTimeout.inSeconds} s',
        );
        _changed(content: true);
      }
    });
    try {
      final Future<List<LibraryCatalogItem>> request =
          source.kind == LibraryFeedSourceKind.aidoku
          ? backend
                .loadAidokuPage(
                  source.addon!,
                  page: 1,
                  query: search.query,
                  cancel: child,
                )
                .then((page) => page.items)
          : backend.searchMetadata(source.providerId!, search.query);
      // Providers that cannot abort their request still release the search
      // slot as soon as the search is cancelled or times out.
      final items = await Future.any<List<LibraryCatalogItem>>(
        <Future<List<LibraryCatalogItem>>>[
          request,
          child.whenCancelled.then<List<LibraryCatalogItem>>(
            (_) => throw const LibraryNetworkException(
              LibraryNetworkErrorKind.cancelled,
            ),
          ),
        ],
      );
      if (timedOut || !_searchIsCurrent(search, parent)) return;
      final seen = <String>{};
      final entries = <LibraryFeedEntry>[];
      for (final item in items) {
        final entry = LibraryFeedEntry.create(
          sourceKey: source.key,
          kind: source.kind,
          item: item,
          addon: source.addon,
          providerId: source.providerId,
        );
        if (seen.add(entry.identity)) entries.add(entry);
      }
      source._entries = List<LibraryFeedEntry>.unmodifiable(entries);
      source._status = LibraryFeedSearchStatus.done;
      _changed(content: true);
    } catch (error) {
      if (timedOut || !_searchIsCurrent(search, parent)) return;
      source._status = LibraryFeedSearchStatus.failed;
      source._failure =
          LibraryFeedFailure.fromError(error, _clock()) ??
          LibraryFeedFailure(LibraryFeedIssue.unknown, at: _clock());
      _changed(content: true);
    } finally {
      timer.cancel();
      unregister();
    }
  }

  // --------------------------------------------------------------- queue --

  Future<void> _enqueue(
    Queue<_QueuedTask> queue,
    Future<void> Function() run, {
    void Function()? onSlow,
  }) {
    final task = _QueuedTask(run, onSlow);
    queue.add(task);
    _pump();
    return task.done.future;
  }

  void _pump() {
    while (_running < maxConcurrentSources && _queue.isNotEmpty) {
      _start(_queue.removeFirst(), search: false);
    }
    while (_searchRunning < maxConcurrentSearches && _searchQueue.isNotEmpty) {
      _start(_searchQueue.removeFirst(), search: true);
    }
  }

  void _start(_QueuedTask task, {required bool search}) {
    if (search) {
      _searchRunning++;
    } else {
      _running++;
    }
    var released = false;
    void release() {
      if (released) return;
      released = true;
      if (search) {
        _searchRunning--;
      } else {
        _running--;
      }
      _pump();
    }

    // A slow page 1 keeps loading but frees its slot so the next sources
    // start (searches have their own per-source timeout instead).
    final timer = search
        ? null
        : Timer(firstPaintTimeout, () {
            task.onSlow?.call();
            release();
          });
    () async {
      try {
        await task.run();
      } catch (_) {
        // Each task records its own failure.
      } finally {
        timer?.cancel();
        release();
        if (!task.done.isCompleted) task.done.complete();
      }
    }();
  }

  // ------------------------------------------------------------ publish --

  void _changed({bool content = false}) {
    if (_disposed) return;
    _version++;
    if (content) _contentVersion++;
    if (_notifyScheduled) return;
    _notifyScheduled = true;
    // Coalesce the changes of one microtask (e.g. several cache reads) into
    // one notification.
    scheduleMicrotask(() {
      _notifyScheduled = false;
      if (!_disposed) notifyListeners();
    });
  }

  @override
  void dispose() {
    _disposed = true;
    _deferredLoadMore?.cancel();
    _deferredLoadMore = null;
    _cancelSearch();
    for (final source in _sources.values) {
      source._token?.cancel();
      source._pageToken?.cancel();
    }
    for (final task in _queue) {
      if (!task.done.isCompleted) task.done.complete();
    }
    _queue.clear();
    super.dispose();
  }
}
