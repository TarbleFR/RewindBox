import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;

import 'package:html/dom.dart';
import 'package:html/parser.dart' as html_parser;

import 'library_addon_service.dart' show LibraryAddonException;
import 'library_aidoku_parsing.dart';
import 'library_catalog_service.dart';
import 'library_http.dart';
import 'library_manga_models.dart';
import 'library_source_support.dart';

/// Source-level failure (the network worked but the content did not match
/// what the adapter expects). Network failures are reported separately as
/// [LibraryNetworkException].
enum LibrarySourceErrorKind {
  /// No adapter for this source (see `LibrarySourceUnsupportedReason`).
  unsupported,

  /// A listing returned no title.
  noResults,

  /// The details page was read but no chapter was found.
  noChapters,

  /// The chapter page was read but no page image was found.
  noPages,

  /// The chapter is locked by the site (premium / unlock token).
  protectedChapter,

  /// The page could not be understood (site markup changed).
  parseFailed,

  /// A page image request did not return an image.
  invalidImage,

  /// A network failure wrapped by a legacy wrapper method (see
  /// [LibrarySourceException.networkError]).
  network,
}

/// Typed source error. Extends [LibraryAddonException] so existing callers
/// that catch it keep working; [message] is a raw technical diagnostic, never
/// user text: the UI translates [kind].
class LibrarySourceException extends LibraryAddonException {
  LibrarySourceException(
    this.kind, {
    this.sourceId = '',
    this.uri,
    this.detail,
    this.networkError,
  }) : super(_describe(kind, sourceId, detail, networkError));

  final LibrarySourceErrorKind kind;
  final String sourceId;
  final Uri? uri;
  final String? detail;

  /// The underlying network failure for [LibrarySourceErrorKind.network].
  final LibraryNetworkException? networkError;

  static String _describe(
    LibrarySourceErrorKind kind,
    String sourceId,
    String? detail,
    LibraryNetworkException? networkError,
  ) {
    final parts = <String>[
      kind.name,
      if (sourceId.isNotEmpty) sourceId,
      if (detail != null && detail.isNotEmpty) detail,
      if (networkError != null) networkError.toString(),
    ];
    return 'LibrarySourceException(${parts.join(', ')})';
  }

  @override
  String toString() => message;
}

/// Static configuration of one supported site (plain data, sendable to the
/// parsing isolate).
class LibraryAidokuSite {
  const LibraryAidokuSite({
    required this.sourceId,
    required this.name,
    required this.engine,
    required this.baseUrl,
    this.sourcePath = 'manga',
    this.language = 'fr',
    this.listingPageSize,
    this.explicitFirstPage = false,
    this.detailsTimeout,
  });

  final String sourceId;
  final String name;
  final LibrarySourceEngine engine;

  /// Canonical origin without trailing slash (`https://www.lelscanfr.com`).
  final String baseUrl;

  /// Path segment before manga slugs (`manga`, `oeuvre`, `catalogue`).
  final String sourcePath;
  final String language;

  /// Items per full listing page, when the site has a fixed size (used for
  /// `hasMore` instead of an extra empty request).
  final int? listingPageSize;

  /// Request `?page=1&order=...` for the first listing page (the form the
  /// site links to itself) instead of `?order=...`.
  final bool explicitFirstPage;

  /// Timeout for the details page when the site is slow to generate it.
  final Duration? detailsTimeout;

  Uri get baseUri => Uri.parse('$baseUrl/');
  String get host => baseUri.host;

  /// Registrable part of [host] (`www.` removed).
  String get domain => host.startsWith('www.') ? host.substring(4) : host;

  /// Exact headers the site accepts for covers and page images. The Referer
  /// keeps its trailing slash: sushiscan.net answers 403 without it.
  Map<String, String> get imageHeaders => <String, String>{
    'User-Agent': LibraryHttp.defaultUserAgent,
    'Referer': '$baseUrl/',
    'Accept': 'image/avif,image/webp,image/apng,image/*,*/*;q=0.8',
  };
}

/// Adapters available on 2026-10-10.
abstract final class LibraryAidokuSites {
  static const Map<String, LibraryAidokuSite> all = <String, LibraryAidokuSite>{
    'fr.mangasorigines': LibraryAidokuSite(
      sourceId: 'fr.mangasorigines',
      name: 'Mangas Origines',
      engine: LibrarySourceEngine.madaraOrigines,
      baseUrl: 'https://mangas-origines.fr',
      sourcePath: 'oeuvre',
      listingPageSize: 16,
    ),
    'fr.mangascantrad': LibraryAidokuSite(
      sourceId: 'fr.mangascantrad',
      name: 'Manga Scantrad',
      engine: LibrarySourceEngine.madara,
      baseUrl: 'https://manga-scantrad.io',
    ),
    'fr.lelscanfr': LibraryAidokuSite(
      sourceId: 'fr.lelscanfr',
      name: 'LelscanFR',
      engine: LibrarySourceEngine.lelscan,
      baseUrl: 'https://www.lelscanfr.com',
      detailsTimeout: Duration(seconds: 30),
    ),
    'fr.sushiscan': LibraryAidokuSite(
      sourceId: 'fr.sushiscan',
      name: 'SushiScan',
      engine: LibrarySourceEngine.mangaThemesia,
      baseUrl: 'https://sushiscan.net',
      sourcePath: 'catalogue',
    ),
    'fr.sushiscans': LibraryAidokuSite(
      sourceId: 'fr.sushiscans',
      name: 'Sushi Scans',
      engine: LibrarySourceEngine.mangaThemesia,
      baseUrl: 'https://sushiscan.fr',
      sourcePath: 'catalogue',
      explicitFirstPage: true,
    ),
  };
}

/// Per-operation request state: fetch mode, cancellation and the cache
/// provenance of every response used to build the result.
class LibraryAidokuFetchContext {
  LibraryAidokuFetchContext({
    required LibraryFetcher fetcher,
    this.mode = LibraryFetchMode.cacheFirst,
    this.cancel,
    DateTime Function()? clock,
  }) : _fetcher = fetcher,
       _clock = clock ?? DateTime.now;

  final LibraryFetcher _fetcher;
  final DateTime Function() _clock;
  final LibraryFetchMode mode;
  final LibraryCancelToken? cancel;

  int _requests = 0;
  bool _allFromCache = true;
  bool _anyStale = false;
  DateTime? _oldest;

  int get requestCount => _requests;
  bool get fromCache => _requests > 0 && _allFromCache;
  bool get stale => _anyStale;
  DateTime get fetchedAt => _oldest ?? _clock();
  DateTime now() => _clock();

  Future<LibraryHttpResponse> send(LibraryRequest request) async {
    cancel?.throwIfCancelled(request.uri);
    final response = await _fetcher(request, mode: mode, cancel: cancel);
    cancel?.throwIfCancelled(request.uri);
    _requests++;
    if (!response.fromCache) _allFromCache = false;
    if (response.stale) _anyStale = true;
    final oldest = _oldest;
    if (oldest == null || response.fetchedAt.isBefore(oldest)) {
      _oldest = response.fetchedAt;
    }
    return response;
  }
}

/// Input of the isolate-safe parsers.
class _ParseInput {
  const _ParseInput(this.site, this.base, this.fetchedAt, {this.variant = 0});

  final LibraryAidokuSite site;

  /// URL the body came from (after redirects), for relative URLs.
  final Uri base;
  final DateTime fetchedAt;
  final int variant;
}

class _ParsedListing {
  const _ParsedListing(this.items, this.hasMore);

  static const _ParsedListing empty = _ParsedListing(
    <LibraryCatalogItem>[],
    false,
  );

  final List<LibraryCatalogItem> items;
  final bool hasMore;
}

class _ParsedManga {
  _ParsedManga();

  String title = '';
  String? cover;
  String description = '';
  String author = '';
  String artist = '';
  String typeLabel = '';
  LibraryMangaStatus status = LibraryMangaStatus.unknown;
  List<String> genres = const <String>[];
  List<String> alternativeTitles = const <String>[];
  int contentRating = LibraryContentRating.safe;
  List<LibraryMangaChapter> chapters = const <LibraryMangaChapter>[];
  String? mangaIntId;
  int chapterPages = 1;
}

class _ParsedPages {
  const _ParsedPages(this.urls, {this.protectedChapter = false});

  final List<String> urls;
  final bool protectedChapter;
}

/// Engine shared by the sites of one template.
abstract class LibraryAidokuEngine {
  LibraryAidokuEngine(this.site);

  factory LibraryAidokuEngine.forSite(LibraryAidokuSite site) {
    return switch (site.engine) {
      LibrarySourceEngine.madaraOrigines => MangasOriginesEngine(site),
      LibrarySourceEngine.madara => MadaraEngine(site),
      LibrarySourceEngine.mangaThemesia => MangaThemesiaEngine(site),
      LibrarySourceEngine.lelscan => LelscanEngine(site),
      _ => throw LibrarySourceException(
        LibrarySourceErrorKind.unsupported,
        sourceId: site.sourceId,
      ),
    };
  }

  final LibraryAidokuSite site;

  /// Listings offered by this engine, default first.
  List<LibraryMangaListing> get listings;

  Future<LibraryMangaCatalogPage> catalog(
    LibraryAidokuFetchContext context, {
    required int page,
    required String query,
    required LibraryMangaListing listing,
  });

  Future<LibraryMangaDetails> manga(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
  );

  Future<List<String>> pages(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
    LibraryMangaChapter chapter,
  );

  Map<String, String> htmlHeaders({
    String? referer,
    Map<String, String> extra = const <String, String>{},
  }) => <String, String>{
    'User-Agent': LibraryHttp.defaultUserAgent,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Referer': ?referer,
    ...extra,
  };

  Map<String, String> ajaxHeaders({required String referer, String? accept}) =>
      <String, String>{
        'User-Agent': LibraryHttp.defaultUserAgent,
        'Accept': accept ?? 'text/html, */*; q=0.01',
        'X-Requested-With': 'XMLHttpRequest',
        'Referer': referer,
      };

  /// True when [url] is an https URL of this site (any subdomain).
  bool ownsUrl(String url) {
    final uri = Uri.tryParse(url);
    if (uri == null || uri.scheme != 'https') return false;
    return uri.host == site.domain || uri.host.endsWith('.${site.domain}');
  }

  /// Canonical details URL of [item], with a trailing slash unless [slash]
  /// is false.
  String mangaUrl(LibraryCatalogItem item, {bool slash = true}) {
    final stored = item.raw['mangaUrl']?.toString() ?? '';
    final storedUri = Uri.tryParse(stored);
    String url;
    if (ownsUrl(stored) &&
        storedUri != null &&
        storedUri.path.contains('/${site.sourcePath}/')) {
      url = Uri(
        scheme: 'https',
        host: site.host,
        path: storedUri.path,
      ).toString();
    } else {
      url =
          '${site.baseUrl}/${site.sourcePath}/${Uri.encodeComponent(item.id)}';
    }
    final trimmed = url.replaceFirst(RegExp(r'/+$'), '');
    return slash ? '$trimmed/' : trimmed;
  }

  /// URL of [chapter], rebuilt from its id when the stored URL does not
  /// belong to the site.
  String chapterUrl(LibraryMangaChapter chapter) {
    if (ownsUrl(chapter.url)) return chapter.url;
    final id = chapter.id.replaceFirst(RegExp(r'^/+'), '');
    return '${site.baseUrl}/${site.sourcePath}/$id';
  }

  LibraryMangaCatalogPage _toPage(
    LibraryAidokuFetchContext context,
    _ParsedListing parsed, {
    required int page,
    required LibraryMangaListing listing,
    required String query,
  }) {
    return LibraryMangaCatalogPage(
      items: List<LibraryCatalogItem>.unmodifiable(parsed.items),
      page: page,
      hasMore: parsed.hasMore,
      listing: listing,
      query: query,
      fetchedAt: context.requestCount == 0 ? null : context.fetchedAt,
      fromCache: context.fromCache,
      stale: context.stale,
    );
  }

  LibraryMangaDetails _assemble(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
    _ParsedManga parsed, {
    required String url,
    bool chaptersComplete = true,
  }) {
    final listingCategories = _stringList(item.raw['categories']);
    final categories = <String>{
      ...parsed.genres,
      if (parsed.typeLabel.isNotEmpty) parsed.typeLabel,
      ...listingCategories,
    }.toList(growable: false);
    final rating = LibraryContentRating.combine(
      LibraryContentRating.combine(
        parsed.contentRating,
        LibraryContentRating.clamp(item.raw['contentRating']),
      ),
      LibraryContentRating.fromLabels(categories),
    );
    final title = parsed.title.isNotEmpty ? parsed.title : item.title;
    final refreshed = _catalogItem(
      site,
      id: item.id,
      title: title,
      url: url,
      cover: parsed.cover ?? item.coverUrl,
      description: parsed.description.isNotEmpty
          ? parsed.description
          : item.description,
      subtitle: parsed.author.isNotEmpty ? parsed.author : site.name,
      categories: categories,
      contentRating: rating,
      typeLabel: parsed.typeLabel.isNotEmpty
          ? parsed.typeLabel
          : item.raw['mangaType']?.toString() ?? '',
      status: parsed.status,
    );
    return LibraryMangaDetails(
      item: refreshed,
      author: parsed.author,
      artist: parsed.artist,
      status: parsed.status,
      genres: List<String>.unmodifiable(parsed.genres),
      readingMode: LibraryAidokuText.readingMode(
        parsed.typeLabel,
        parsed.genres,
      ),
      contentRating: rating,
      chapters: List<LibraryMangaChapter>.unmodifiable(parsed.chapters),
      alternativeTitles: List<String>.unmodifiable(parsed.alternativeTitles),
      typeLabel: parsed.typeLabel,
      chaptersComplete: chaptersComplete,
      fetchedAt: context.fetchedAt,
      fromCache: context.fromCache,
      stale: context.stale,
    );
  }

  List<String> _requirePages(
    _ParsedPages parsed,
    LibraryMangaChapter chapter,
    Uri uri,
  ) {
    if (parsed.urls.isNotEmpty) {
      return List<String>.unmodifiable(parsed.urls);
    }
    throw LibrarySourceException(
      parsed.protectedChapter
          ? LibrarySourceErrorKind.protectedChapter
          : LibrarySourceErrorKind.noPages,
      sourceId: site.sourceId,
      uri: uri,
      detail: chapter.id,
    );
  }
}

// ---------------------------------------------------------------------------
// Madara (WordPress wp-manga)
// ---------------------------------------------------------------------------

/// Generic Madara engine (Manga Scantrad and the base of Mangas Origines).
class MadaraEngine extends LibraryAidokuEngine {
  MadaraEngine(super.site);

  static const Map<LibraryMangaListing, String> _metaKeys =
      <LibraryMangaListing, String>{
        LibraryMangaListing.latest: '_latest_update',
        LibraryMangaListing.popular: '_wp_manga_views',
        LibraryMangaListing.trending: '_wp_manga_week_views_value',
      };

  @override
  List<LibraryMangaListing> get listings => const <LibraryMangaListing>[
    LibraryMangaListing.latest,
    LibraryMangaListing.popular,
    LibraryMangaListing.trending,
  ];

  Uri get adminAjax => Uri.parse('${site.baseUrl}/wp-admin/admin-ajax.php');

  @override
  Future<LibraryMangaCatalogPage> catalog(
    LibraryAidokuFetchContext context, {
    required int page,
    required String query,
    required LibraryMangaListing listing,
  }) async {
    final parsed = query.isEmpty
        ? await _loadListing(context, page, listing)
        : await _search(context, page, query);
    return _toPage(context, parsed, page: page, listing: listing, query: query);
  }

  /// `madara_load_more` listing. `vars[paged]` stays 1: the offset is
  /// carried by `page` (as the site's own ajax.js does), otherwise every
  /// other page would be skipped.
  Future<_ParsedListing> _loadListing(
    LibraryAidokuFetchContext context,
    int page,
    LibraryMangaListing listing,
  ) async {
    final request = LibraryRequest.postForm(
      adminAjax,
      <String, String>{
        'action': 'madara_load_more',
        'page': '${page - 1}',
        'template': 'madara-core/content/content-archive',
        'vars[paged]': '1',
        'vars[orderby]': 'meta_value_num',
        'vars[template]': 'archive',
        'vars[sidebar]': 'full',
        'vars[post_type]': 'wp-manga',
        'vars[post_status]': 'publish',
        'vars[meta_key]': _metaKeys[listing] ?? '_latest_update',
        'vars[order]': 'desc',
        'vars[meta_query][relation]': 'OR',
        'vars[manga_archives_item_layout]': 'big_thumbnail',
      },
      headers: ajaxHeaders(referer: '${site.baseUrl}/'),
      cache: LibraryCachePolicy.listing,
    );
    final response = await context.send(request);
    return libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseMadaraListing,
    );
  }

  Future<_ParsedListing> _search(
    LibraryAidokuFetchContext context,
    int page,
    String query,
  ) async {
    final uri = Uri.parse('${site.baseUrl}/page/$page/').replace(
      queryParameters: <String, String>{
        's': query.toLowerCase(),
        'post_type': 'wp-manga',
      },
    );
    final response = await context.send(
      LibraryRequest.get(
        uri,
        headers: htmlHeaders(
          referer: '${site.baseUrl}/',
          extra: const <String, String>{'Cookie': 'wpmanga-adault=1'},
        ),
        cache: LibraryCachePolicy.search,
        acceptStatuses: page > 1 ? const <int>{404} : const <int>{},
      ),
    );
    if (response.statusCode == 404) return _ParsedListing.empty;
    return libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseMadaraSearch,
    );
  }

  Future<LibraryHttpResponse> fetchDetails(
    LibraryAidokuFetchContext context,
    String url,
  ) {
    return context.send(
      LibraryRequest.get(
        Uri.parse(url),
        headers: htmlHeaders(referer: '${site.baseUrl}/'),
        cache: LibraryCachePolicy.details,
        timeout: site.detailsTimeout,
      ),
    );
  }

  @override
  Future<LibraryMangaDetails> manga(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
  ) async {
    final url = mangaUrl(item);
    final response = await fetchDetails(context, url);
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseMadaraDetails,
    );
    if (parsed.chapters.isEmpty) {
      parsed.chapters = await loadAjaxChapters(context, url, parsed.mangaIntId);
    }
    _requireDetails(parsed, response);
    return _assemble(context, item, parsed, url: url);
  }

  void _requireDetails(_ParsedManga parsed, LibraryHttpResponse response) {
    if (parsed.title.isEmpty && parsed.chapters.isEmpty) {
      throw LibrarySourceException(
        LibrarySourceErrorKind.parseFailed,
        sourceId: site.sourceId,
        uri: response.finalUri,
        detail: 'details markup not recognized',
      );
    }
  }

  /// Whether `admin-ajax manga_get_chapters` may follow an empty or missing
  /// `ajax/chapters/` answer. Mangas Origines answers HTTP 400 to it.
  bool get adminAjaxChapterFallback => true;

  /// Chapter list through `{mangaUrl}ajax/chapters/` (body-less POST, as
  /// the site's script.js does), then `admin-ajax manga_get_chapters` with
  /// the numeric id when the first endpoint is missing or empty (only when
  /// [adminAjaxChapterFallback] is true).
  Future<List<LibraryMangaChapter>> loadAjaxChapters(
    LibraryAidokuFetchContext context,
    String mangaUrl,
    String? mangaIntId,
  ) async {
    List<LibraryMangaChapter> chapters = const <LibraryMangaChapter>[];
    LibraryNetworkException? firstError;
    try {
      final response = await context.send(
        LibraryRequest.postForm(
          Uri.parse('${mangaUrl}ajax/chapters/'),
          const <String, String>{},
          headers: ajaxHeaders(referer: mangaUrl),
          cache: LibraryCachePolicy.details,
          timeout: site.detailsTimeout,
        ),
      );
      chapters = await libraryAidokuParse(
        response.bodyBytes,
        _ParseInput(site, response.finalUri, response.fetchedAt),
        _parseMadaraChapterList,
      );
    } on LibraryNetworkException catch (error) {
      if (error.kind != LibraryNetworkErrorKind.notFound &&
          error.kind != LibraryNetworkErrorKind.httpStatus) {
        rethrow;
      }
      firstError = error;
    }
    if (chapters.isNotEmpty ||
        mangaIntId == null ||
        !adminAjaxChapterFallback) {
      if (chapters.isEmpty && firstError != null) throw firstError;
      return chapters;
    }
    final response = await context.send(
      LibraryRequest.postForm(
        adminAjax,
        <String, String>{'action': 'manga_get_chapters', 'manga': mangaIntId},
        headers: ajaxHeaders(referer: mangaUrl),
        cache: LibraryCachePolicy.details,
        timeout: site.detailsTimeout,
      ),
    );
    return libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseMadaraChapterList,
    );
  }

  @override
  Future<List<String>> pages(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
    LibraryMangaChapter chapter,
  ) async {
    final base = Uri.parse(chapterUrl(chapter));
    final uri = base.replace(
      queryParameters: <String, String>{
        ...base.queryParameters,
        'style': 'list',
      },
    );
    final response = await context.send(
      LibraryRequest.get(
        uri,
        headers: htmlHeaders(referer: mangaUrl(item)),
        cache: LibraryCachePolicy.chapterPages,
      ),
    );
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseMadaraPages,
    );
    return _requirePages(parsed, chapter, response.finalUri);
  }
}

/// Mangas Origines: Madara listings, plus the "child-origines" theme for
/// search (`madara_child_catalogue` JSON), details and the chapter list
/// embedded in the details page (one request for both).
class MangasOriginesEngine extends MadaraEngine {
  MangasOriginesEngine(super.site);

  /// `admin-ajax manga_get_chapters` answers HTTP 400 on this site: a title
  /// without chapter rows keeps its details and an empty chapter list.
  @override
  bool get adminAjaxChapterFallback => false;

  @override
  Future<_ParsedListing> _search(
    LibraryAidokuFetchContext context,
    int page,
    String query,
  ) async {
    final response = await context.send(
      LibraryRequest.postForm(
        adminAjax,
        <String, String>{
          'action': 'madara_child_catalogue',
          's': query,
          'genres': '',
          'statut': 'tous',
          'note': '0',
          'origine': '',
          'tri': 'recents',
          'chmin': '0',
          'chmax': '0',
          'page': '$page',
          'auteur': '',
          'artiste': '',
          'annee': '',
          'vue': 'grille',
        },
        headers: ajaxHeaders(
          referer: '${site.baseUrl}/',
          accept: 'application/json, text/javascript, */*; q=0.01',
        ),
        cache: LibraryCachePolicy.search,
      ),
    );
    return libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseOriginesCatalogue,
    );
  }

  @override
  Future<LibraryMangaDetails> manga(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
  ) async {
    final url = mangaUrl(item);
    final response = await fetchDetails(context, url);
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseOriginesDetails,
    );
    if (parsed.chapters.isEmpty) {
      parsed.chapters = await loadAjaxChapters(context, url, parsed.mangaIntId);
    }
    _requireDetails(parsed, response);
    return _assemble(context, item, parsed, url: url);
  }
}

_ParsedListing _parseMadaraListing(String body, _ParseInput input) {
  if (body.trim().isEmpty) return _ParsedListing.empty;
  final document = html_parser.parse(body);
  final nodes = document.querySelectorAll('div.page-item-detail');
  final items = <LibraryCatalogItem>[];
  for (final node in nodes) {
    if (node.querySelector('.web-novel') != null) continue;
    Element? link;
    for (final selector in const <String>[
      'h3.h5 > a',
      '.post-title a',
      'h3 a',
      '.item-thumb a',
    ]) {
      final candidate = node.querySelector(selector);
      if ((candidate?.attributes['href'] ?? '').isNotEmpty) {
        link = candidate;
        break;
      }
    }
    if (link == null) continue;
    final url = LibraryAidokuText.absoluteUrl(
      link.attributes['href'],
      input.base,
    );
    if (url == null) continue;
    final id = LibraryAidokuText.segmentAfter(url, input.site.sourcePath);
    var title = LibraryAidokuText.without(link, '.manga-title-badges');
    if (title.isEmpty) {
      title = LibraryAidokuText.clean(
        node.querySelector('.item-thumb a')?.attributes['title'] ?? '',
      );
    }
    if (id == null || id.isEmpty || title.isEmpty) continue;

    final categories = <String>[];
    var rating = LibraryContentRating.safe;
    for (final badge in node.querySelectorAll('.manga-title-badges')) {
      if (badge.classes.contains('adult')) {
        rating = LibraryContentRating.explicit;
      }
      final label = LibraryAidokuText.of(badge.querySelector('.text') ?? badge);
      final lower = label.toLowerCase();
      if (label.isEmpty || lower == 'hot' || lower == 'new') continue;
      if (!categories.contains(label)) categories.add(label);
    }
    items.add(
      _catalogItem(
        input.site,
        id: id,
        title: title,
        url: url,
        cover: LibraryAidokuText.imageUrl(
          node.querySelector('img'),
          input.base,
        ),
        categories: categories,
        contentRating: LibraryContentRating.combine(
          rating,
          LibraryContentRating.fromLabels(categories),
        ),
        typeLabel: categories.isEmpty ? '' : categories.first,
      ),
    );
  }
  final pageSize = input.site.listingPageSize;
  final hasMore = pageSize == null
      ? nodes.isNotEmpty
      : nodes.length >= pageSize;
  return _ParsedListing(items, hasMore);
}

_ParsedListing _parseMadaraSearch(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  final items = <LibraryCatalogItem>[];
  final seen = <String>{};
  for (final node in document.querySelectorAll('div.c-tabs-item__content')) {
    final type = LibraryAidokuText.of(
      node.querySelector('.post-content_item .summary-content a'),
    ).toLowerCase();
    if (type.contains('novel')) continue;
    final link = node.querySelector('.post-title a[href], h3 a[href], a[href]');
    if (link == null) continue;
    final url = LibraryAidokuText.absoluteUrl(
      link.attributes['href'],
      input.base,
    );
    if (url == null) continue;
    final id = LibraryAidokuText.segmentAfter(url, input.site.sourcePath);
    var title = LibraryAidokuText.clean(link.attributes['title'] ?? '');
    if (title.isEmpty) {
      title = LibraryAidokuText.without(link, '.manga-title-badges');
    }
    if (id == null || title.isEmpty || !seen.add(id)) continue;
    final genres = node
        .querySelectorAll('.mg_genres a, .genres a')
        .map(LibraryAidokuText.of)
        .where((genre) => genre.isNotEmpty)
        .toList();
    items.add(
      _catalogItem(
        input.site,
        id: id,
        title: title,
        url: url,
        cover: LibraryAidokuText.imageUrl(
          node.querySelector('img'),
          input.base,
        ),
        categories: genres,
        contentRating: LibraryContentRating.fromLabels(genres),
      ),
    );
  }
  final next = document.querySelector(
    '.nav-previous a, a.nextpostslink, .wp-pagenavi a.nextpostslink, '
    'a.next.page-numbers, link[rel="next"]',
  );
  return _ParsedListing(items, items.isNotEmpty && next != null);
}

final RegExp _mangaIdPattern = RegExp(r'"manga_id"\s*:\s*"?(\d+)');

String? _madaraIntId(Document document) {
  final script = document.querySelector('script#wp-manga-js-extra');
  if (script != null) {
    var text = script.text;
    if (text.trim().isEmpty) {
      final src = script.attributes['src'] ?? '';
      final comma = src.indexOf('base64,');
      if (comma >= 0) {
        try {
          text = utf8.decode(
            base64.decode(src.substring(comma + 'base64,'.length)),
            allowMalformed: true,
          );
        } on FormatException {
          text = '';
        }
      }
    }
    final match = _mangaIdPattern.firstMatch(text);
    if (match != null) return match.group(1);
  }
  final holder =
      document.querySelector('#manga-chapters-holder')?.attributes['data-id'] ??
      document.querySelector('.ori-chl[data-manga]')?.attributes['data-manga'];
  final trimmed = holder?.trim() ?? '';
  return RegExp(r'^\d+$').hasMatch(trimmed) ? trimmed : null;
}

_ParsedManga _parseMadaraDetails(String body, _ParseInput input) =>
    _madaraDetails(html_parser.parse(body), input);

_ParsedManga _madaraDetails(Document document, _ParseInput input) {
  final parsed = _ParsedManga();
  final heading = document.querySelector(
    'div.post-title h1, div.post-title h3',
  );
  if (heading != null) {
    parsed.title = LibraryAidokuText.without(heading, '.manga-title-badges');
  }
  parsed.cover =
      LibraryAidokuText.imageUrl(
        document.querySelector('div.summary_image img'),
        input.base,
      ) ??
      LibraryAidokuText.absoluteUrl(
        document
            .querySelector('meta[property="og:image"]')
            ?.attributes['content'],
        input.base,
      );
  parsed.author = _joinLinks(document.querySelector('div.author-content'));
  parsed.artist = _joinLinks(document.querySelector('div.artist-content'));
  for (final selector in const <String>[
    'div.description-summary .summary__content',
    'div.summary__content',
    'div.manga-excerpt',
    'div.post-content_item.mg_summary .summary-content',
  ]) {
    final text = LibraryAidokuText.paragraphs(document.querySelector(selector));
    if (text.isNotEmpty) {
      parsed.description = text;
      break;
    }
  }
  parsed.genres = _distinctTexts(
    document.querySelectorAll('div.genres-content a'),
  );
  for (final row in document.querySelectorAll('div.post-content_item')) {
    final label = LibraryContentRating.normalizeLabel(
      LibraryAidokuText.of(row.querySelector('.summary-heading')),
    );
    final value = LibraryAidokuText.of(row.querySelector('.summary-content'));
    if (value.isEmpty) continue;
    if (label.startsWith('status') || label.startsWith('statut')) {
      parsed.status = LibraryAidokuText.status(value);
    } else if (label.startsWith('type')) {
      parsed.typeLabel = value;
    } else if (label.startsWith('alternati')) {
      parsed.alternativeTitles = _splitList(value);
    }
  }
  var rating = LibraryContentRating.fromLabels(parsed.genres);
  if (document.querySelector('.manga-title-badges.adult') != null) {
    rating = LibraryContentRating.explicit;
  }
  parsed.contentRating = rating;
  parsed.mangaIntId = _madaraIntId(document);
  parsed.chapters = _madaraChapters(document, input);
  return parsed;
}

List<LibraryMangaChapter> _parseMadaraChapterList(
  String body,
  _ParseInput input,
) {
  final document = html_parser.parse(body);
  final rows = _originesChapters(document, input);
  return rows.isNotEmpty ? rows : _madaraChapters(document, input);
}

List<LibraryMangaChapter> _madaraChapters(
  Document document,
  _ParseInput input,
) {
  final chapters = <LibraryMangaChapter>[];
  final seen = <String>{};
  for (final row in document.querySelectorAll('li.wp-manga-chapter')) {
    final link = row.querySelector('a[href]');
    if (link == null) continue;
    final url = LibraryAidokuText.absoluteUrl(
      link.attributes['href'],
      input.base,
    );
    if (url == null || !seen.add(url)) continue;
    final label = LibraryAidokuText.of(link);
    final id =
        LibraryAidokuText.pathAfter(url, input.site.sourcePath) ??
        Uri.parse(url).path;
    final volume = LibraryAidokuText.volumeNumberInLabel(label);
    final number = volume != null
        ? null
        : LibraryAidokuText.chapterNumberInLabel(label) ??
              _numberFromSlug(url) ??
              LibraryAidokuText.firstNumber(label);
    final dateElement = row.querySelector('span.chapter-release-date');
    final dateText =
        LibraryAidokuText.of(dateElement?.querySelector('i')).isNotEmpty
        ? LibraryAidokuText.of(dateElement?.querySelector('i'))
        : (dateElement?.querySelector('a[title]')?.attributes['title'] ??
              LibraryAidokuText.of(dateElement));
    chapters.add(
      LibraryMangaChapter(
        id: id,
        url: url,
        title: label,
        number: number,
        volume: volume,
        date: LibraryAidokuDates.parse(dateText, now: input.fetchedAt),
        language: input.site.language,
      ),
    );
  }
  return chapters;
}

/// Number from the last slug segment: the first numeric token is the
/// integer part and an immediately following numeric token the decimal
/// part (`chapitre-062-5` = 62.5, `chapitre-100-fin-saison-1` = 100).
double? _numberFromSlug(String url) {
  final last = LibraryAidokuText.lastSegment(url);
  if (last == null) return null;
  String? integer;
  for (var token in last.split('-')) {
    final underscore = token.indexOf('_');
    if (underscore >= 0) token = token.substring(0, underscore);
    final numeric = RegExp(r'^\d+$').hasMatch(token);
    if (integer == null) {
      if (numeric) integer = token;
      continue;
    }
    if (numeric) return double.tryParse('$integer.$token');
    break;
  }
  return integer == null ? null : double.tryParse(integer);
}

_ParsedPages _parseMadaraPages(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  var images = document.querySelectorAll('div.page-break > img');
  if (images.isEmpty) {
    images = document.querySelectorAll('.reading-content img');
  }
  return _ParsedPages(_imageList(images, input.base));
}

_ParsedListing _parseOriginesCatalogue(String body, _ParseInput input) {
  Object? decoded;
  try {
    decoded = jsonDecode(body);
  } on FormatException {
    throw LibrarySourceException(
      LibrarySourceErrorKind.parseFailed,
      sourceId: input.site.sourceId,
      uri: input.base,
      detail: 'madara_child_catalogue did not return JSON',
    );
  }
  if (decoded is! Map || decoded['success'] != true) {
    return _ParsedListing.empty;
  }
  final data = decoded['data'];
  if (data is! Map) return _ParsedListing.empty;
  final html = data['html']?.toString() ?? '';
  final items = <LibraryCatalogItem>[];
  if (html.trim().isNotEmpty) {
    final fragment = html_parser.parseFragment(html);
    for (final card in fragment.querySelectorAll('a.ori-card')) {
      final url = LibraryAidokuText.absoluteUrl(
        card.attributes['href'],
        input.base,
      );
      if (url == null) continue;
      final id = LibraryAidokuText.segmentAfter(url, input.site.sourcePath);
      final cover = card.querySelector('.ori-card-cover img');
      var title = LibraryAidokuText.of(card.querySelector('.ori-card-title'));
      if (title.isEmpty) {
        title = LibraryAidokuText.clean(cover?.attributes['alt'] ?? '');
      }
      if (id == null || title.isEmpty) continue;
      final labels = LibraryAidokuText.of(card.querySelector('.ori-card-sub'))
          .split('·')
          .map(LibraryAidokuText.clean)
          .where((label) => label.isNotEmpty)
          .toList();
      items.add(
        _catalogItem(
          input.site,
          id: id,
          title: title,
          url: url,
          cover: LibraryAidokuText.imageUrl(
            cover,
            input.base,
            attributes: const <String>['src', 'data-src'],
          ),
          categories: labels,
          contentRating: LibraryContentRating.fromLabels(labels),
          typeLabel: labels.length > 1 ? labels.last : '',
          status: LibraryAidokuText.status(
            card.querySelector('.ori-cat-dot')?.attributes['title'] ?? '',
          ),
        ),
      );
    }
  }
  return _ParsedListing(items, data['more'] == true);
}

_ParsedManga _parseOriginesDetails(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  final parsed = _madaraDetails(document, input);
  final heading = document.querySelector('h1.ori-sr-title');
  if (heading != null) parsed.title = LibraryAidokuText.of(heading);
  parsed.cover =
      LibraryAidokuText.imageUrl(
        document.querySelector('div.ori-sr-cover > img'),
        input.base,
        attributes: const <String>['src', 'data-src'],
      ) ??
      parsed.cover;
  final synopsis = LibraryAidokuText.paragraphs(
    document.querySelector('div.ori-sr-syn-texte'),
  );
  if (synopsis.isNotEmpty) parsed.description = synopsis;

  final infos = <String, String>{};
  final list = document.querySelector('#ori-sr-infos dl');
  if (list != null) {
    String? label;
    for (final child in list.children) {
      if (child.localName == 'dt') {
        label = LibraryContentRating.normalizeLabel(
          LibraryAidokuText.of(child),
        );
      } else if (child.localName == 'dd' && label != null) {
        infos[label] = LibraryAidokuText.of(child);
        label = null;
      }
    }
  }
  final signature = document.querySelector('div.ori-sr-signature');
  parsed.author =
      infos['scenario'] ??
      _joinLinks(signature, selector: 'a[href*="/manga-auteurs/"]');
  parsed.artist =
      infos['dessin'] ??
      _joinLinks(signature, selector: 'a[href*="/manga-artistes/"]');
  if (parsed.author.isEmpty) {
    parsed.author = _joinLinks(document.querySelector('div.author-content'));
  }
  if (infos['statut'] != null) {
    parsed.status = LibraryAidokuText.status(infos['statut']!);
  }
  if (infos['type'] != null) parsed.typeLabel = infos['type']!;
  final genres = _distinctTexts(
    document.querySelectorAll('div.ori-sr-genres a.ori-sr-genre'),
  );
  if (genres.isNotEmpty) parsed.genres = genres;

  // The class list of div.ori-sr-page names every genre slug, including the
  // ones collapsed behind "see all genres".
  final slugs = <String>[
    for (final token
        in document.querySelector('div.ori-sr-page')?.classes ?? <String>{})
      if (token.startsWith('wp-manga-genre-'))
        token.substring('wp-manga-genre-'.length).replaceAll('-', ' '),
  ];
  parsed.contentRating = LibraryContentRating.combine(
    parsed.contentRating,
    LibraryContentRating.fromLabels(<String>[...parsed.genres, ...slugs]),
  );
  final rows = _originesChapters(document, input);
  if (rows.isNotEmpty) parsed.chapters = rows;
  return parsed;
}

List<LibraryMangaChapter> _originesChapters(
  Document document,
  _ParseInput input,
) {
  var rows = document.querySelectorAll('div.ori-chl-liste div.ori-chl-row');
  if (rows.isEmpty) rows = document.querySelectorAll('div.ori-chl-row');
  final chapters = <LibraryMangaChapter>[];
  final seen = <String>{};
  for (final row in rows) {
    final link =
        row.querySelector('a.ori-chl-corps[href]') ??
        row.querySelector('a[href]');
    final url = LibraryAidokuText.absoluteUrl(
      link?.attributes['href'],
      input.base,
    );
    if (url == null || !seen.add(url)) continue;
    var label = LibraryAidokuText.of(row.querySelector('.ori-chl-nom-long'));
    if (label.isEmpty) {
      label = LibraryAidokuText.clean(row.attributes['data-nom'] ?? '');
    }
    final number =
        double.tryParse(row.attributes['data-num']?.trim() ?? '') ??
        LibraryAidokuText.chapterNumberInLabel(label);
    final dateElement = row.querySelector('.ori-chl-date');
    DateTime? date;
    final timestamp = int.tryParse(dateElement?.attributes['data-ts'] ?? '');
    if (timestamp != null && timestamp > 0) {
      date = DateTime.fromMillisecondsSinceEpoch(timestamp * 1000, isUtc: true);
    } else {
      date =
          LibraryAidokuDates.parse(
            dateElement?.attributes['title'],
            now: input.fetchedAt,
          ) ??
          LibraryAidokuDates.parse(
            LibraryAidokuText.of(dateElement),
            now: input.fetchedAt,
          );
    }
    chapters.add(
      LibraryMangaChapter(
        id:
            LibraryAidokuText.pathAfter(url, input.site.sourcePath) ??
            Uri.parse(url).path,
        url: url,
        title: label,
        number: number,
        date: date,
        language: input.site.language,
        sortKey: double.tryParse(row.attributes['data-ordre']?.trim() ?? ''),
      ),
    );
  }
  return chapters;
}

// ---------------------------------------------------------------------------
// MangaThemesia / MangaStream (ts_reader)
// ---------------------------------------------------------------------------

/// SushiScan (.net) and Sushi Scans (.fr).
class MangaThemesiaEngine extends LibraryAidokuEngine {
  MangaThemesiaEngine(super.site);

  static const Map<LibraryMangaListing, String> _orders =
      <LibraryMangaListing, String>{
        LibraryMangaListing.latest: 'update',
        LibraryMangaListing.popular: 'popular',
        LibraryMangaListing.newest: 'latest',
      };

  static final RegExp _typographic = RegExp('[‘’“”«»–—]');

  @override
  List<LibraryMangaListing> get listings => const <LibraryMangaListing>[
    LibraryMangaListing.latest,
    LibraryMangaListing.popular,
    LibraryMangaListing.newest,
  ];

  /// Replaces iOS smart punctuation (’ “ ” – ...) by spaces: the site's
  /// search returns nothing for `l’attaque` but finds `l attaque`.
  static String normalizeQuery(String query) =>
      LibraryAidokuText.clean(query.replaceAll(_typographic, ' '));

  @override
  Future<LibraryMangaCatalogPage> catalog(
    LibraryAidokuFetchContext context, {
    required int page,
    required String query,
    required LibraryMangaListing listing,
  }) async {
    final normalized = normalizeQuery(query);
    final Uri uri;
    final LibraryCachePolicy policy;
    if (normalized.isEmpty) {
      final order = _orders[listing] ?? 'update';
      final path = '${site.baseUrl}/${site.sourcePath}/';
      uri = Uri.parse(
        page == 1 && !site.explicitFirstPage
            ? '$path?order=$order'
            : '$path?page=$page&order=$order',
      );
      policy = LibraryCachePolicy.listing;
    } else {
      uri = Uri.parse(
        '${site.baseUrl}/${site.sourcePath}/page/$page/',
      ).replace(queryParameters: <String, String>{'s': normalized});
      policy = LibraryCachePolicy.search;
    }
    final response = await context.send(
      LibraryRequest.get(
        uri,
        headers: htmlHeaders(referer: '${site.baseUrl}/'),
        cache: policy,
        // A search page past the last one is a 404: the end, not an error.
        // On page 1 a 404 stays an error (the search path itself moved).
        acceptStatuses: normalized.isNotEmpty && page > 1
            ? const <int>{404}
            : const <int>{},
      ),
    );
    final parsed = response.statusCode == 404
        ? _ParsedListing.empty
        : await libraryAidokuParse(
            response.bodyBytes,
            _ParseInput(site, response.finalUri, response.fetchedAt),
            _parseThemesiaListing,
          );
    return _toPage(
      context,
      parsed,
      page: page,
      listing: listing,
      query: normalized,
    );
  }

  @override
  Future<LibraryMangaDetails> manga(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
  ) async {
    final url = mangaUrl(item);
    final response = await context.send(
      LibraryRequest.get(
        Uri.parse(url),
        headers: htmlHeaders(referer: '${site.baseUrl}/'),
        cache: LibraryCachePolicy.details,
        timeout: site.detailsTimeout,
      ),
    );
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseThemesiaDetails,
    );
    if (parsed.title.isEmpty && parsed.chapters.isEmpty) {
      throw LibrarySourceException(
        LibrarySourceErrorKind.parseFailed,
        sourceId: site.sourceId,
        uri: response.finalUri,
        detail: 'details markup not recognized',
      );
    }
    return _assemble(context, item, parsed, url: url);
  }

  @override
  Future<List<String>> pages(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
    LibraryMangaChapter chapter,
  ) async {
    final url = ownsUrl(chapter.url)
        ? chapter.url
        : '${site.baseUrl}/${chapter.id.replaceAll(RegExp(r'^/+|/+$'), '')}/';
    final response = await context.send(
      LibraryRequest.get(
        Uri.parse(url),
        headers: htmlHeaders(referer: '${site.baseUrl}/'),
        cache: LibraryCachePolicy.chapterPages,
      ),
    );
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseThemesiaPages,
    );
    return _requirePages(parsed, chapter, response.finalUri);
  }
}

_ParsedListing _parseThemesiaListing(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  final items = <LibraryCatalogItem>[];
  final seen = <String>{};
  for (final node in document.querySelectorAll('.listupd .bsx')) {
    final link = node.querySelector('a[href]');
    if (link == null) continue;
    final url = LibraryAidokuText.absoluteUrl(
      link.attributes['href'],
      input.base,
    );
    if (url == null) continue;
    var title = LibraryAidokuText.clean(link.attributes['title'] ?? '');
    if (title.isEmpty) title = LibraryAidokuText.of(node.querySelector('.tt'));
    if (title.isEmpty || title.toLowerCase().contains('light novel')) continue;
    final id =
        LibraryAidokuText.segmentAfter(url, input.site.sourcePath) ??
        LibraryAidokuText.lastSegment(url);
    if (id == null || !seen.add(id)) continue;
    var typeLabel = LibraryAidokuText.of(node.querySelector('span.typename'));
    if (typeLabel.isEmpty) {
      final typeClasses = node.querySelector('span.type')?.classes;
      typeLabel =
          typeClasses?.firstWhere(
            (token) => token != 'type',
            orElse: () => '',
          ) ??
          '';
    }
    items.add(
      _catalogItem(
        input.site,
        id: id,
        title: title,
        url: url,
        cover: LibraryAidokuText.imageUrl(
          node.querySelector('img'),
          input.base,
          attributes: const <String>['src', 'data-lazy-src', 'data-src'],
        ),
        categories: typeLabel.isEmpty ? const <String>[] : <String>[typeLabel],
        typeLabel: typeLabel,
      ),
    );
  }
  final next = document.querySelector('.hpage a.r, .pagination a.next');
  return _ParsedListing(items, next != null);
}

_ParsedManga _parseThemesiaDetails(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  final parsed = _ParsedManga();
  parsed.title = LibraryAidokuText.of(document.querySelector('h1.entry-title'));
  parsed.cover = LibraryAidokuText.imageUrl(
    document.querySelector(
      '.thumb img, .infomanga [itemprop="image"] img, '
      '[itemprop="image"] img',
    ),
    input.base,
    attributes: const <String>['src', 'data-lazy-src', 'data-src'],
  );

  final table = <String, String>{};
  for (final row in document.querySelectorAll('.infotable tr')) {
    final cells = row.querySelectorAll('td, th');
    if (cells.length < 2) continue;
    table[LibraryContentRating.normalizeLabel(LibraryAidokuText.of(cells[0]))] =
        LibraryAidokuText.of(cells[1]);
  }
  for (final cell in document.querySelectorAll('.tsinfo .imptdt')) {
    final value = LibraryAidokuText.of(cell.querySelector('i, a'));
    final label = LibraryAidokuText.of(cell).replaceFirst(value, '');
    if (value.isNotEmpty) {
      table.putIfAbsent(
        LibraryContentRating.normalizeLabel(label),
        () => value,
      );
    }
  }
  String cell(List<String> labels) {
    for (final label in labels) {
      final value = table[label] ?? '';
      if (value.isNotEmpty && value != '-') return value;
    }
    return '';
  }

  parsed.status = LibraryAidokuText.status(cell(const ['statut', 'status']));
  parsed.typeLabel = cell(const ['type']);
  parsed.author = cell(const ['auteur', 'author']);
  parsed.artist = cell(const ['dessinateur', 'artiste', 'artist']);
  parsed.description = LibraryAidokuText.paragraphs(
    document.querySelector(
      'div.entry-content[itemprop="description"], div.desc, '
      '[itemprop="description"]',
    ),
  );
  parsed.genres = _distinctTexts(
    document.querySelectorAll('.seriestugenre a, .mgen a'),
  );
  parsed.alternativeTitles = _splitList(
    LibraryAidokuText.of(document.querySelector('.seriestualt, .alternative')),
  );
  parsed.contentRating = LibraryContentRating.fromLabels(parsed.genres);

  final chapters = <LibraryMangaChapter>[];
  final seen = <String>{};
  for (final row in document.querySelectorAll('#chapterlist li')) {
    final link = row.querySelector('a[href]');
    final href = link?.attributes['href'] ?? '';
    if (href.contains('{{') || href.startsWith('#')) continue;
    final url = LibraryAidokuText.absoluteUrl(href, input.base);
    if (url == null || !seen.add(url)) continue;
    var label = LibraryAidokuText.of(row.querySelector('span.chapternum'));
    if (label.isEmpty) {
      label = LibraryAidokuText.clean(row.attributes['data-num'] ?? '');
    }
    final volume = LibraryAidokuText.volumeNumberInLabel(label);
    final number = volume != null
        ? null
        : double.tryParse(row.attributes['data-num']?.trim() ?? '') ??
              LibraryAidokuText.chapterNumberInLabel(label) ??
              LibraryAidokuText.firstNumber(label);
    chapters.add(
      LibraryMangaChapter(
        id: LibraryAidokuText.lastSegment(url) ?? url,
        url: url,
        title: label,
        number: number,
        volume: volume,
        date: LibraryAidokuDates.parse(
          LibraryAidokuText.of(row.querySelector('span.chapterdate')),
          now: input.fetchedAt,
        ),
        language: input.site.language,
      ),
    );
  }
  parsed.chapters = chapters;
  return parsed;
}

_ParsedPages _parseThemesiaPages(String body, _ParseInput input) {
  final config = LibraryAidokuText.tsReaderConfig(body);
  var protectedChapter = false;
  if (config != null) {
    protectedChapter =
        config['protected'] == true ||
        (config['unlock_token'] != null && config['unlock_token'] != '');
    final sources = config['sources'];
    if (sources is List) {
      final preferred = config['defaultSource']?.toString();
      final ordered = <Map>[
        ...sources.whereType<Map>().where(
          (source) => source['source']?.toString() == preferred,
        ),
        ...sources.whereType<Map>(),
      ];
      for (final source in ordered) {
        final images = source['images'];
        if (images is! List) continue;
        final urls = <String>[];
        final seen = <String>{};
        for (final image in images) {
          final url = LibraryAidokuText.absoluteUrl(
            image?.toString(),
            input.base,
          );
          if (url != null && seen.add(url)) urls.add(url);
        }
        if (urls.isNotEmpty) return _ParsedPages(urls);
      }
    }
  }
  final document = html_parser.parse(body);
  final urls = _imageList(
    document.querySelectorAll('#readerarea img'),
    input.base,
    attributes: const <String>['src', 'data-src', 'data-lazy-src'],
  );
  return _ParsedPages(urls, protectedChapter: protectedChapter);
}

// ---------------------------------------------------------------------------
// LelscanFR (Laravel / Tailwind)
// ---------------------------------------------------------------------------

/// LelscanFR. Chapter lists are paginated by 100 on the details page.
class LelscanEngine extends LibraryAidokuEngine {
  LelscanEngine(super.site);

  /// Upper bound of chapter list pages fetched for one title (100 chapters
  /// each), to bound memory and time.
  static const int maxChapterPages = 60;
  static const int chapterPageConcurrency = 2;

  static const int _cardsAll = 0;
  static const int _cardsLatestSection = 1;
  static const int _cardsPopular = 2;

  @override
  List<LibraryMangaListing> get listings => const <LibraryMangaListing>[
    LibraryMangaListing.latest,
    LibraryMangaListing.popular,
    LibraryMangaListing.newest,
  ];

  @override
  Future<LibraryMangaCatalogPage> catalog(
    LibraryAidokuFetchContext context, {
    required int page,
    required String query,
    required LibraryMangaListing listing,
  }) async {
    final Uri uri;
    final int variant;
    var policy = LibraryCachePolicy.listing;
    if (query.isNotEmpty) {
      uri = Uri.parse('${site.baseUrl}/manga').replace(
        queryParameters: <String, String>{'page': '$page', 'title': query},
      );
      variant = _cardsAll;
      policy = LibraryCachePolicy.search;
    } else if (listing == LibraryMangaListing.popular) {
      // The popular carousel exists only on the home page (one page).
      if (page > 1) {
        return _toPage(
          context,
          _ParsedListing.empty,
          page: page,
          listing: listing,
          query: query,
        );
      }
      uri = Uri.parse('${site.baseUrl}/');
      variant = _cardsPopular;
    } else if (listing == LibraryMangaListing.newest) {
      uri = Uri.parse('${site.baseUrl}/manga?page=$page');
      variant = _cardsAll;
    } else {
      uri = Uri.parse(
        page == 1 ? '${site.baseUrl}/' : '${site.baseUrl}/?page=$page',
      );
      variant = _cardsLatestSection;
    }
    final response = await context.send(
      LibraryRequest.get(
        uri,
        headers: htmlHeaders(referer: '${site.baseUrl}/'),
        cache: policy,
      ),
    );
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(
        site,
        response.finalUri,
        response.fetchedAt,
        variant: variant,
      ),
      _parseLelscanCards,
    );
    return _toPage(context, parsed, page: page, listing: listing, query: query);
  }

  LibraryRequest _detailsRequest(String url) => LibraryRequest.get(
    Uri.parse(url),
    headers: htmlHeaders(referer: '${site.baseUrl}/'),
    cache: LibraryCachePolicy.details,
    timeout: site.detailsTimeout,
  );

  @override
  Future<LibraryMangaDetails> manga(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
  ) => mangaProgressive(context, item);

  /// [manga] that also reports the details with the chapters obtained so
  /// far: once the first chapter list page is read, then each time the
  /// contiguous run of list pages grows (newest chapters first, so the list
  /// only grows at its end). Partial results have `chaptersComplete` false;
  /// the returned value is the same as [manga]'s.
  Future<LibraryMangaDetails> mangaProgressive(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item, {
    void Function(LibraryMangaDetails partial)? onPartial,
  }) async {
    final url = mangaUrl(item, slash: false);
    final response = await context.send(_detailsRequest(url));
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseLelscanDetails,
    );
    if (parsed.title.isEmpty && parsed.chapters.isEmpty) {
      throw LibrarySourceException(
        LibrarySourceErrorKind.parseFailed,
        sourceId: site.sourceId,
        uri: response.finalUri,
        detail: 'details markup not recognized',
      );
    }
    final total = math.min(parsed.chapterPages, maxChapterPages);
    var complete = parsed.chapterPages <= maxChapterPages;
    if (total > 1) {
      final firstPage = parsed.chapters;
      final pages = <int>[for (var page = 2; page <= total; page++) page];
      final results = List<List<LibraryMangaChapter>?>.filled(
        pages.length,
        null,
      );
      final resolved = List<bool>.filled(pages.length, false);

      List<LibraryMangaChapter> merged(int pageCount) {
        final seen = firstPage.map((chapter) => chapter.url).toSet();
        final all = <LibraryMangaChapter>[...firstPage];
        for (var index = 0; index < pageCount; index++) {
          final list = results[index];
          if (list == null) continue;
          for (final chapter in list) {
            if (seen.add(chapter.url)) all.add(chapter);
          }
        }
        return all;
      }

      var reported = 0;
      void report() {
        if (onPartial == null || (context.cancel?.isCancelled ?? false)) {
          return;
        }
        var prefix = reported;
        while (prefix < pages.length && resolved[prefix]) {
          prefix++;
        }
        if (prefix == reported || prefix == pages.length) return;
        reported = prefix;
        parsed.chapters = merged(prefix);
        onPartial(
          _assemble(context, item, parsed, url: url, chaptersComplete: false),
        );
      }

      if (onPartial != null) {
        onPartial(
          _assemble(context, item, parsed, url: url, chaptersComplete: false),
        );
      }

      var next = 0;
      Future<void> worker() async {
        while (next < pages.length) {
          final index = next++;
          try {
            final page = await context.send(
              _detailsRequest('$url?page=${pages[index]}'),
            );
            results[index] = await libraryAidokuParse(
              page.bodyBytes,
              _ParseInput(site, page.finalUri, page.fetchedAt),
              _parseLelscanChapterPage,
            );
          } on LibraryNetworkException catch (error) {
            if (error.kind == LibraryNetworkErrorKind.cancelled) rethrow;
            complete = false;
          } on LibrarySourceException {
            complete = false;
          }
          resolved[index] = true;
          report();
        }
      }

      await Future.wait(<Future<void>>[
        for (var i = 0; i < math.min(chapterPageConcurrency, pages.length); i++)
          worker(),
      ]);
      parsed.chapters = merged(pages.length);
    }
    return _assemble(
      context,
      item,
      parsed,
      url: url,
      chaptersComplete: complete,
    );
  }

  @override
  Future<List<String>> pages(
    LibraryAidokuFetchContext context,
    LibraryCatalogItem item,
    LibraryMangaChapter chapter,
  ) async {
    final url = ownsUrl(chapter.url)
        ? Uri.parse(chapter.url).replace(host: site.host).toString()
        : '${mangaUrl(item, slash: false)}/${chapter.id}';
    final response = await context.send(
      LibraryRequest.get(
        Uri.parse(url),
        headers: htmlHeaders(referer: mangaUrl(item, slash: false)),
        cache: LibraryCachePolicy.chapterPages,
      ),
    );
    final parsed = await libraryAidokuParse(
      response.bodyBytes,
      _ParseInput(site, response.finalUri, response.fetchedAt),
      _parseLelscanPages,
    );
    return _requirePages(parsed, chapter, response.finalUri);
  }
}

final RegExp _pageOf = RegExp(
  r'Page\s+(\d+)\s+of\s+(\d+)',
  caseSensitive: false,
);

(int, int)? _lelscanPagination(Document document) {
  for (final heading in document.querySelectorAll('nav h3, h3')) {
    final match = _pageOf.firstMatch(heading.text);
    if (match != null) {
      return (int.parse(match.group(1)!), int.parse(match.group(2)!));
    }
  }
  return null;
}

_ParsedListing _parseLelscanCards(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  List<Element> cards;
  switch (input.variant) {
    case LelscanEngine._cardsPopular:
      cards = document.querySelectorAll('#popular-cards div[id="card-real"]');
    case LelscanEngine._cardsLatestSection:
      cards = const <Element>[];
      for (final section in document.querySelectorAll('section')) {
        final heading = LibraryContentRating.normalizeLabel(
          LibraryAidokuText.of(section.querySelector('h2')),
        );
        if (heading == 'chapitres recents') {
          cards = section.querySelectorAll('div[id="card-real"]');
          break;
        }
      }
    default:
      cards = document.querySelectorAll('div[id="card-real"]');
  }
  final items = <LibraryCatalogItem>[];
  final seen = <String>{};
  for (final card in cards) {
    final link = card.querySelector('a[href]');
    final url = LibraryAidokuText.absoluteUrl(
      link?.attributes['href'],
      input.base,
    );
    if (url == null) continue;
    final id = LibraryAidokuText.segmentAfter(url, 'manga');
    if (id == null || id == 'random' || !seen.add(id)) continue;
    final image = card.querySelector('img');
    var title = LibraryAidokuText.clean(image?.attributes['alt'] ?? '');
    if (title.isEmpty) {
      final headings = card.querySelectorAll('h2');
      title = headings.isEmpty
          ? ''
          : LibraryAidokuText.of(
              headings.last,
            ).replaceFirst(RegExp(r'\.\.\.$'), '').trim();
    }
    if (title.isEmpty) continue;
    final genres = <String>[];
    final sibling = card.nextElementSibling;
    if (sibling != null && sibling.localName == 'span') {
      for (final genre in sibling.querySelectorAll('a[href*="genre="]')) {
        final label = LibraryAidokuText.of(
          genre.querySelector('span') ?? genre,
        ).replaceFirst(RegExp(r',$'), '').trim();
        if (label.isNotEmpty && !genres.contains(label)) genres.add(label);
      }
    }
    items.add(
      _catalogItem(
        input.site,
        id: id,
        title: title,
        url: '${input.site.baseUrl}/manga/$id',
        cover: LibraryAidokuText.imageUrl(
          image,
          input.base,
          attributes: const <String>['data-src', 'src'],
        ),
        categories: genres,
        contentRating: LibraryContentRating.fromLabels(genres),
      ),
    );
  }
  var hasMore = false;
  if (input.variant != LelscanEngine._cardsPopular) {
    final pagination = _lelscanPagination(document);
    hasMore = pagination != null && pagination.$1 < pagination.$2;
  }
  return _ParsedListing(items, hasMore);
}

_ParsedManga _parseLelscanDetails(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  final parsed = _ParsedManga();
  final main = document.querySelector('main') ?? document.documentElement!;
  final image = main.querySelector('img');
  parsed.title = LibraryAidokuText.clean(image?.attributes['alt'] ?? '');
  parsed.cover = LibraryAidokuText.imageUrl(
    image,
    input.base,
    attributes: const <String>['src', 'data-src'],
  );
  final labels = <String, String>{};
  for (final span in main.querySelectorAll('p > span')) {
    final label = LibraryContentRating.normalizeLabel(
      LibraryAidokuText.of(span),
    );
    final value = LibraryAidokuText.of(span.nextElementSibling);
    if (label.isNotEmpty && value.isNotEmpty) {
      labels.putIfAbsent(label, () => value);
    }
  }
  parsed.author = labels['auteur'] ?? '';
  parsed.artist = labels['artiste'] ?? '';
  parsed.status = LibraryAidokuText.status(labels['statut'] ?? '');
  parsed.typeLabel = labels['type'] ?? '';
  final description =
      document.querySelector('#description + p') ??
      document.querySelector('#description');
  parsed.description = LibraryAidokuText.of(description);
  parsed.genres = _distinctTexts(
    main.querySelectorAll('a[href*="/manga?genre="]'),
  );
  parsed.alternativeTitles = _splitList(
    LibraryAidokuText.of(
      main.querySelector('span.block.text-sm.text-gray-700'),
    ),
  );
  parsed.contentRating = LibraryContentRating.fromLabels(parsed.genres);
  parsed.chapters = _lelscanChapters(document, input);
  var total = _lelscanPagination(document)?.$2;
  if (total == null) {
    for (final item in document.querySelectorAll(
      'li.pagination-link[onclick]',
    )) {
      final match = RegExp(
        r'page=(\d+)',
      ).firstMatch(item.attributes['onclick']!);
      final page = match == null ? null : int.tryParse(match.group(1)!);
      if (page != null && page > (total ?? 1)) total = page;
    }
  }
  parsed.chapterPages = total ?? 1;
  return parsed;
}

List<LibraryMangaChapter> _parseLelscanChapterPage(
  String body,
  _ParseInput input,
) => _lelscanChapters(html_parser.parse(body), input);

List<LibraryMangaChapter> _lelscanChapters(
  Document document,
  _ParseInput input,
) {
  final chapters = <LibraryMangaChapter>[];
  final seen = <String>{};
  for (final link in document.querySelectorAll('#chapters-list > a[href]')) {
    final url = LibraryAidokuText.absoluteUrl(
      link.attributes['href'],
      input.base,
    );
    if (url == null || !seen.add(url)) continue;
    final id = LibraryAidokuText.lastSegment(url) ?? url;
    final label = LibraryAidokuText.of(link.querySelector('span'));
    chapters.add(
      LibraryMangaChapter(
        id: id,
        url: url,
        title: label,
        number:
            double.tryParse(id) ??
            LibraryAidokuText.chapterNumberInLabel(label) ??
            LibraryAidokuText.firstNumber(label),
        date: LibraryAidokuDates.parse(
          LibraryAidokuText.of(link.querySelector('span.text-gray-500')),
          now: input.fetchedAt,
        ),
        language: input.site.language,
      ),
    );
  }
  return chapters;
}

_ParsedPages _parseLelscanPages(String body, _ParseInput input) {
  final document = html_parser.parse(body);
  var images = document.querySelectorAll(
    '#chapter-container img.chapter-image',
  );
  if (images.isEmpty) {
    images = document.querySelectorAll('#chapter-container img');
  }
  return _ParsedPages(
    _imageList(
      images,
      input.base,
      attributes: const <String>['data-src', 'src'],
    ),
  );
}

// ---------------------------------------------------------------------------
// Shared helpers (isolate-safe)
// ---------------------------------------------------------------------------

LibraryCatalogItem _catalogItem(
  LibraryAidokuSite site, {
  required String id,
  required String title,
  required String url,
  String? cover,
  String description = '',
  String? subtitle,
  List<String> categories = const <String>[],
  int contentRating = LibraryContentRating.safe,
  String typeLabel = '',
  LibraryMangaStatus status = LibraryMangaStatus.unknown,
}) {
  return LibraryCatalogItem(
    id: id,
    title: title,
    mediaType: LibraryMediaType.manga,
    subtitle: subtitle ?? site.name,
    description: description,
    coverUrl: cover,
    content: null,
    contentUrl: null,
    pageUrls: const <String>[],
    raw: Map<String, dynamic>.unmodifiable(<String, dynamic>{
      'nativeProvider': 'aidoku-web',
      'aidokuSourceId': site.sourceId,
      'sourceName': site.name,
      'mangaId': id,
      'mangaUrl': url,
      'onlineKey': LibraryMangaKeys.online(site.sourceId, id),
      'language': site.language,
      if (categories.isNotEmpty)
        'categories': List<String>.unmodifiable(categories),
      'contentRating': contentRating,
      if (contentRating >= LibraryContentRating.explicit)
        'explicitContent': true,
      if (typeLabel.isNotEmpty) 'mangaType': typeLabel,
      if (status != LibraryMangaStatus.unknown) 'status': status.name,
      'imageHeaders': Map<String, String>.unmodifiable(site.imageHeaders),
    }),
  );
}

List<String> _imageList(
  List<Element> images,
  Uri base, {
  List<String> attributes = const <String>[
    'data-src',
    'data-lazy-src',
    'src',
    'srcset',
    'data-cfsrc',
  ],
}) {
  final urls = <String>[];
  final seen = <String>{};
  for (final image in images) {
    final url = LibraryAidokuText.imageUrl(image, base, attributes: attributes);
    if (url != null && seen.add(url)) urls.add(url);
  }
  return urls;
}

String _joinLinks(Element? container, {String selector = 'a'}) {
  if (container == null) return '';
  final names = _distinctTexts(container.querySelectorAll(selector));
  if (names.isNotEmpty) return names.join(', ');
  return selector == 'a' ? LibraryAidokuText.of(container) : '';
}

List<String> _distinctTexts(List<Element> elements) {
  final values = <String>[];
  for (final element in elements) {
    final text = LibraryAidokuText.of(element).replaceFirst(RegExp(r',$'), '');
    if (text.isNotEmpty && !values.contains(text)) values.add(text);
  }
  return values;
}

List<String> _splitList(String value) => value
    .split(RegExp(r'\s*[,;/]\s*'))
    .map(LibraryAidokuText.clean)
    .where((part) => part.isNotEmpty)
    .toList();

List<String> _stringList(Object? value) {
  if (value is! Iterable) return const <String>[];
  return value
      .map((entry) => entry?.toString().trim() ?? '')
      .where((entry) => entry.isNotEmpty)
      .toList();
}
