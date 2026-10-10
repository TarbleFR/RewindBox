import 'dart:async';
import 'dart:collection';
import 'dart:typed_data';

import 'library_addon_service.dart';
import 'library_aidoku_engines.dart';
import 'library_catalog_service.dart';
import 'library_http.dart';
import 'library_manga_models.dart';
import 'library_source_support.dart';

export 'library_aidoku_engines.dart'
    show LibrarySourceErrorKind, LibrarySourceException;
export 'library_manga_models.dart';
export 'library_source_support.dart';

/// Step of a source health check, in execution order.
enum LibrarySourceHealthStep { listing, details, chapters, pages, image }

/// Result of one health check step.
class LibrarySourceHealthStepResult {
  const LibrarySourceHealthStepResult({
    required this.step,
    required this.ok,
    this.skipped = false,
    this.networkError,
    this.sourceError,
    this.statusCode,
    this.count = 0,
    this.durationMs = 0,
    this.detail,
  });

  const LibrarySourceHealthStepResult.skipped(this.step)
    : ok = false,
      skipped = true,
      networkError = null,
      sourceError = null,
      statusCode = null,
      count = 0,
      durationMs = 0,
      detail = null;

  final LibrarySourceHealthStep step;
  final bool ok;

  /// Not run because an earlier step failed.
  final bool skipped;
  final LibraryNetworkErrorKind? networkError;
  final LibrarySourceErrorKind? sourceError;
  final int? statusCode;

  /// Items, chapters or pages obtained; image size in bytes for
  /// [LibrarySourceHealthStep.image].
  final int count;
  final int durationMs;

  /// Raw technical detail (untranslated).
  final String? detail;

  /// Name of the failure (`challenge`, `noChapters`, ...), null when ok.
  String? get errorKind =>
      networkError?.name ?? sourceError?.name ?? (skipped ? 'skipped' : null);

  Map<String, Object?> toJson() => <String, Object?>{
    'step': step.name,
    'ok': ok,
    if (skipped) 'skipped': true,
    if (networkError != null) 'networkError': networkError!.name,
    if (sourceError != null) 'sourceError': sourceError!.name,
    if (statusCode != null) 'statusCode': statusCode,
    'count': count,
    'durationMs': durationMs,
    if (detail != null) 'detail': detail,
  };

  static LibrarySourceHealthStepResult? fromJson(Object? json) {
    if (json is! Map) return null;
    T? byName<T extends Enum>(List<T> values, Object? name) {
      for (final value in values) {
        if (value.name == name) return value;
      }
      return null;
    }

    final step = byName(LibrarySourceHealthStep.values, json['step']);
    if (step == null) return null;
    return LibrarySourceHealthStepResult(
      step: step,
      ok: json['ok'] == true,
      skipped: json['skipped'] == true,
      networkError: byName(
        LibraryNetworkErrorKind.values,
        json['networkError'],
      ),
      sourceError: byName(LibrarySourceErrorKind.values, json['sourceError']),
      statusCode: (json['statusCode'] as num?)?.toInt(),
      count: (json['count'] as num?)?.toInt() ?? 0,
      durationMs: (json['durationMs'] as num?)?.toInt() ?? 0,
      detail: json['detail']?.toString(),
    );
  }
}

/// Outcome of [LibraryAidokuNativeService.checkHealth]: listing, details,
/// chapter list, page list and first page image, measured on the device.
class LibrarySourceHealthReport {
  LibrarySourceHealthReport({
    required this.sourceId,
    required this.checkedAt,
    required List<LibrarySourceHealthStepResult> steps,
  }) : steps = List<LibrarySourceHealthStepResult>.unmodifiable(steps);

  final String sourceId;
  final DateTime checkedAt;
  final List<LibrarySourceHealthStepResult> steps;

  LibrarySourceHealthStepResult step(LibrarySourceHealthStep step) =>
      steps.firstWhere(
        (result) => result.step == step,
        orElse: () => LibrarySourceHealthStepResult.skipped(step),
      );

  bool _ok(LibrarySourceHealthStep value) => step(value).ok;

  /// Listing, details and chapter list obtained.
  bool get navigationWorking =>
      _ok(LibrarySourceHealthStep.listing) &&
      _ok(LibrarySourceHealthStep.details) &&
      _ok(LibrarySourceHealthStep.chapters);

  /// Navigation plus a page list and its first image downloaded.
  bool get readingWorking =>
      navigationWorking &&
      _ok(LibrarySourceHealthStep.pages) &&
      _ok(LibrarySourceHealthStep.image);

  /// First failed (not skipped) step.
  LibrarySourceHealthStepResult? get firstFailure {
    for (final result in steps) {
      if (!result.ok && !result.skipped) return result;
    }
    return null;
  }

  /// State derived from this check.
  LibrarySourceKnownState get state {
    if (readingWorking) return LibrarySourceKnownState.working;
    final failure = firstFailure;
    if (failure == null) return LibrarySourceKnownState.unknown;
    switch (failure.networkError) {
      case LibraryNetworkErrorKind.challenge:
        return LibrarySourceKnownState.challenge;
      case LibraryNetworkErrorKind.serverUnavailable:
      case LibraryNetworkErrorKind.timeout:
        return LibrarySourceKnownState.serverUnavailable;
      case LibraryNetworkErrorKind.offline:
        return LibrarySourceKnownState.offline;
      case LibraryNetworkErrorKind.notFound:
      case LibraryNetworkErrorKind.httpStatus:
      case LibraryNetworkErrorKind.invalidResponse:
      case LibraryNetworkErrorKind.tooLarge:
        return LibrarySourceKnownState.siteChanged;
      case LibraryNetworkErrorKind.cancelled:
      case null:
        break;
    }
    switch (failure.sourceError) {
      case LibrarySourceErrorKind.unsupported:
        return LibrarySourceKnownState.adapterMissing;
      case LibrarySourceErrorKind.noResults:
      case LibrarySourceErrorKind.noChapters:
      case LibrarySourceErrorKind.noPages:
      case LibrarySourceErrorKind.parseFailed:
      case LibrarySourceErrorKind.invalidImage:
        return LibrarySourceKnownState.siteChanged;
      case LibrarySourceErrorKind.protectedChapter:
      case LibrarySourceErrorKind.network:
      case null:
        return LibrarySourceKnownState.unknown;
    }
  }

  Map<String, Object?> toJson() => <String, Object?>{
    'sourceId': sourceId,
    'checkedAt': checkedAt.toUtc().toIso8601String(),
    'steps': steps.map((step) => step.toJson()).toList(),
  };

  static LibrarySourceHealthReport? fromJson(Object? json) {
    if (json is! Map) return null;
    final checkedAt = DateTime.tryParse(json['checkedAt']?.toString() ?? '');
    final sourceId = json['sourceId']?.toString() ?? '';
    if (checkedAt == null || sourceId.isEmpty) return null;
    final steps = <LibrarySourceHealthStepResult>[];
    final rawSteps = json['steps'];
    if (rawSteps is List) {
      for (final raw in rawSteps) {
        final step = LibrarySourceHealthStepResult.fromJson(raw);
        if (step != null) steps.add(step);
      }
    }
    return LibrarySourceHealthReport(
      sourceId: sourceId,
      checkedAt: checkedAt.toUtc(),
      steps: steps,
    );
  }
}

class _MemoEntry {
  _MemoEntry(this.details, this.storedAt);

  final LibraryMangaDetails details;
  final DateTime storedAt;
}

/// Native reader of the French Aidoku sources.
///
/// The .aix packages are not executed: the site templates they use
/// (Madara, MangaThemesia, LelscanFR) are implemented in Dart engines
/// ([LibraryAidokuEngine]). Every request goes through an injectable
/// [LibraryFetcher] (default [LibraryHttp.send]) with the Library cache
/// policies; large pages are parsed off the UI isolate. Services never
/// return user text: failures are [LibraryNetworkException] (passed through
/// from the fetcher) or [LibrarySourceException].
class LibraryAidokuNativeService {
  LibraryAidokuNativeService({
    LibraryFetcher? fetcher,
    DateTime Function()? clock,
    this.memoTtl = const Duration(minutes: 2),
    this.memoCapacity = 24,
  }) : _fetcher = fetcher ?? _defaultFetcher,
       _clock = clock ?? DateTime.now;

  static final LibraryAidokuNativeService instance =
      LibraryAidokuNativeService();

  /// Resolved at call time so the service can be built before
  /// [LibraryHttp.instance] is configured.
  static Future<LibraryHttpResponse> _defaultFetcher(
    LibraryRequest request, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) => LibraryHttp.instance.send(request, mode: mode, cancel: cancel);

  final LibraryFetcher _fetcher;
  final DateTime Function() _clock;

  /// How long a parsed details result is reused by [loadManga] (so that
  /// [loadDetails] followed by [loadChapters] costs one request).
  final Duration memoTtl;
  final int memoCapacity;

  final Map<String, LibraryAidokuEngine> _engines =
      <String, LibraryAidokuEngine>{};
  final LinkedHashMap<String, _MemoEntry> _memo =
      LinkedHashMap<String, _MemoEntry>();

  /// Aidoku source id of [addon] (e.g. `fr.sushiscan`), or null when the
  /// addon is not an Aidoku repository source.
  String? sourceIdFor(LibraryAddon addon) {
    if (!addon.isAidokuRepositorySource) return null;
    final provider = addon.manifest['provider'];
    if (provider is Map) {
      final value = provider['sourceId']?.toString().trim();
      if (value != null && value.isNotEmpty) return value;
    }
    if (addon.id.startsWith('aidoku.')) {
      return addon.id.substring('aidoku.'.length);
    }
    return null;
  }

  /// Static support information for [sourceId] (verified 2026-10-10).
  LibrarySourceSupport supportFor(String sourceId) =>
      LibrarySourceSupportRegistry.forSourceId(sourceId);

  /// Support information for [addon], or null when it is not an Aidoku
  /// repository source.
  LibrarySourceSupport? support(LibraryAddon addon) {
    final sourceId = sourceIdFor(addon);
    return sourceId == null ? null : supportFor(sourceId);
  }

  /// True when NeoStation has an adapter for [addon]. Sources with an
  /// adapter stay callable even when their verified state is not
  /// `working`, so a health check can detect recovery.
  bool supports(LibraryAddon addon) {
    final sourceId = sourceIdFor(addon);
    return sourceId != null &&
        supportFor(sourceId).hasAdapter &&
        LibraryAidokuSites.all.containsKey(sourceId);
  }

  /// Why [addon] has no adapter; null when it is supported.
  LibrarySourceUnsupportedReason? unsupportedReasonKind(LibraryAddon addon) {
    final sourceId = sourceIdFor(addon);
    if (sourceId == null) return LibrarySourceUnsupportedReason.notAidokuSource;
    if (supports(addon)) return null;
    return supportFor(sourceId).unsupportedReason ??
        LibrarySourceUnsupportedReason.adapterMissing;
  }

  /// Former API: technical reason code (the
  /// [LibrarySourceUnsupportedReason] name) for an unsupported Aidoku
  /// source, null for supported or non-Aidoku addons. Not user text.
  String? unsupportedReason(LibraryAddon addon) {
    if (!addon.isAidokuRepositorySource) return null;
    return unsupportedReasonKind(addon)?.name;
  }

  /// Listings [addon] exposes, default first (empty when unsupported).
  List<LibraryMangaListing> listings(LibraryAddon addon) {
    final engine = _engineOrNull(addon);
    return engine == null ? const <LibraryMangaListing>[] : engine.listings;
  }

  /// Exact headers for covers and page images of [addon] (User-Agent and
  /// the Referer the site requires).
  Map<String, String> imageHeaders(LibraryAddon addon) {
    final engine = _engineOrNull(addon);
    if (engine == null) {
      return const <String, String>{'User-Agent': LibraryHttp.defaultUserAgent};
    }
    return engine.site.imageHeaders;
  }

  /// One page of a listing ([listing], default: the source's first) or of
  /// a search when [query] is not empty.
  Future<LibraryMangaCatalogPage> loadCatalogPage(
    LibraryAddon addon, {
    int page = 1,
    String query = '',
    LibraryMangaListing? listing,
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    final engine = _engine(addon);
    final effectiveListing =
        listing != null && engine.listings.contains(listing)
        ? listing
        : engine.listings.first;
    return engine.catalog(
      _context(mode, cancel),
      page: page < 1 ? 1 : page,
      query: query.trim(),
      listing: effectiveListing,
    );
  }

  /// The cached version of a catalogue page without network access, or null
  /// when nothing usable is cached.
  Future<LibraryMangaCatalogPage?> cachedCatalogPage(
    LibraryAddon addon, {
    int page = 1,
    String query = '',
    LibraryMangaListing? listing,
  }) async {
    try {
      return await loadCatalogPage(
        addon,
        page: page,
        query: query,
        listing: listing,
        mode: LibraryFetchMode.cacheOnly,
      );
    } on LibraryNetworkException {
      return null;
    }
  }

  /// Details and full chapter list of [item]. Sites that embed the chapter
  /// list in the details page cost one request; LelscanFR adds one request
  /// per 100 chapters (two at a time).
  Future<LibraryMangaDetails> loadManga(
    LibraryAddon addon,
    LibraryCatalogItem item, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    final engine = _engine(addon);
    final key = '${engine.site.sourceId}\u0000${item.id}';
    if (mode == LibraryFetchMode.cacheFirst) {
      final memo = _memo.remove(key);
      if (memo != null && _clock().difference(memo.storedAt) < memoTtl) {
        _memo[key] = memo;
        return memo.details;
      }
    }
    final details = await engine.manga(_context(mode, cancel), item);
    if (details.chaptersComplete && !details.stale) {
      _memo.remove(key);
      _memo[key] = _MemoEntry(details, _clock());
      while (_memo.length > memoCapacity) {
        _memo.remove(_memo.keys.first);
      }
    }
    return details;
  }

  /// Absolute URLs of the page images of [chapter], in reading order.
  /// Throws [LibrarySourceException] ([LibrarySourceErrorKind.noPages] or
  /// [LibrarySourceErrorKind.protectedChapter]) when none is found.
  Future<List<String>> loadPages(
    LibraryAddon addon,
    LibraryCatalogItem item,
    LibraryMangaChapter chapter, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    return _engine(addon).pages(_context(mode, cancel), item, chapter);
  }

  /// Former API: first listing page truncated to [limit] items.
  Future<List<LibraryCatalogItem>> loadCatalog(
    LibraryAddon addon, {
    int limit = 24,
  }) async {
    final page = await _legacy(() => loadCatalogPage(addon));
    final safeLimit = limit.clamp(1, 100).toInt();
    return List<LibraryCatalogItem>.unmodifiable(page.items.take(safeLimit));
  }

  /// Former API: refreshed catalogue item. Shares the request of
  /// [loadChapters] through [loadManga].
  Future<LibraryCatalogItem> loadDetails(
    LibraryAddon addon,
    LibraryCatalogItem item, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    final details = await _legacy(
      () => loadManga(addon, item, mode: mode, cancel: cancel),
    );
    return details.item;
  }

  /// Former API: chapters newest first. Shares the request of [loadDetails]
  /// through [loadManga].
  Future<List<LibraryAidokuChapter>> loadChapters(
    LibraryAddon addon,
    LibraryCatalogItem item, {
    LibraryFetchMode mode = LibraryFetchMode.cacheFirst,
    LibraryCancelToken? cancel,
  }) async {
    final details = await _legacy(
      () => loadManga(addon, item, mode: mode, cancel: cancel),
    );
    return details.chapters;
  }

  /// Runs the five reading steps against the live site (network only, no
  /// cache) and reports each step with its timing.
  Future<LibrarySourceHealthReport> checkHealth(
    LibraryAddon addon, {
    LibraryMangaListing? listing,
    LibraryCancelToken? cancel,
  }) async {
    final sourceId = sourceIdFor(addon) ?? addon.id;
    final checkedAt = _clock().toUtc();
    final results = <LibrarySourceHealthStepResult>[];

    if (!supports(addon)) {
      results.add(
        const LibrarySourceHealthStepResult(
          step: LibrarySourceHealthStep.listing,
          ok: false,
          sourceError: LibrarySourceErrorKind.unsupported,
        ),
      );
      return _report(sourceId, checkedAt, results);
    }

    const mode = LibraryFetchMode.refresh;
    final listingResult = await _healthStep(
      LibrarySourceHealthStep.listing,
      () =>
          loadCatalogPage(addon, listing: listing, mode: mode, cancel: cancel),
      count: (page) => page.items.length,
      empty: LibrarySourceErrorKind.noResults,
    );
    results.add(listingResult.$1);
    final page = listingResult.$2;
    if (page == null || page.items.isEmpty) {
      return _report(sourceId, checkedAt, results);
    }

    final detailsWatch = Stopwatch()..start();
    LibraryMangaDetails? details;
    try {
      details = await loadManga(
        addon,
        page.items.first,
        mode: mode,
        cancel: cancel,
      );
      detailsWatch.stop();
      results.add(
        LibrarySourceHealthStepResult(
          step: LibrarySourceHealthStep.details,
          ok: true,
          count: 1,
          durationMs: detailsWatch.elapsedMilliseconds,
          detail: page.items.first.id,
        ),
      );
      final chapterCount = details.chapters.length;
      results.add(
        LibrarySourceHealthStepResult(
          step: LibrarySourceHealthStep.chapters,
          ok: chapterCount > 0,
          sourceError: chapterCount > 0
              ? null
              : LibrarySourceErrorKind.noChapters,
          count: chapterCount,
          durationMs: detailsWatch.elapsedMilliseconds,
        ),
      );
    } catch (error) {
      detailsWatch.stop();
      if (_isCancellation(error)) rethrow;
      results.add(
        _failure(
          LibrarySourceHealthStep.details,
          error,
          detailsWatch.elapsedMilliseconds,
        ),
      );
    }
    if (details == null || details.chapters.isEmpty) {
      return _report(sourceId, checkedAt, results);
    }

    final chapter = details.chapters.first;
    final pagesResult = await _healthStep(
      LibrarySourceHealthStep.pages,
      () =>
          loadPages(addon, details!.item, chapter, mode: mode, cancel: cancel),
      count: (pages) => pages.length,
      empty: LibrarySourceErrorKind.noPages,
      detail: chapter.id,
    );
    results.add(pagesResult.$1);
    final pages = pagesResult.$2;
    if (pages == null || pages.isEmpty) {
      return _report(sourceId, checkedAt, results);
    }

    results.add(await _imageStep(addon, pages.first, cancel));
    return _report(sourceId, checkedAt, results);
  }

  LibrarySourceHealthReport _report(
    String sourceId,
    DateTime checkedAt,
    List<LibrarySourceHealthStepResult> results,
  ) {
    final done = results.map((result) => result.step).toSet();
    return LibrarySourceHealthReport(
      sourceId: sourceId,
      checkedAt: checkedAt,
      steps: <LibrarySourceHealthStepResult>[
        ...results,
        for (final step in LibrarySourceHealthStep.values)
          if (!done.contains(step)) LibrarySourceHealthStepResult.skipped(step),
      ],
    );
  }

  Future<(LibrarySourceHealthStepResult, T?)> _healthStep<T>(
    LibrarySourceHealthStep step,
    Future<T> Function() run, {
    required int Function(T value) count,
    required LibrarySourceErrorKind empty,
    String? detail,
  }) async {
    final watch = Stopwatch()..start();
    try {
      final value = await run();
      watch.stop();
      final total = count(value);
      return (
        LibrarySourceHealthStepResult(
          step: step,
          ok: total > 0,
          sourceError: total > 0 ? null : empty,
          count: total,
          durationMs: watch.elapsedMilliseconds,
          detail: detail,
        ),
        value,
      );
    } catch (error) {
      watch.stop();
      if (_isCancellation(error)) rethrow;
      return (_failure(step, error, watch.elapsedMilliseconds), null);
    }
  }

  Future<LibrarySourceHealthStepResult> _imageStep(
    LibraryAddon addon,
    String url,
    LibraryCancelToken? cancel,
  ) async {
    final watch = Stopwatch()..start();
    try {
      final uri = Uri.parse(url);
      final response = await _fetcher(
        LibraryRequest.get(
          uri,
          headers: imageHeaders(addon),
          maxBytes: 32 * 1024 * 1024,
        ),
        mode: LibraryFetchMode.refresh,
        cancel: cancel,
      );
      watch.stop();
      final type = response.headers['content-type'] ?? '';
      final isImage =
          type.toLowerCase().startsWith('image/') ||
          _looksLikeImage(response.bodyBytes);
      final ok = response.ok && response.bodyBytes.isNotEmpty && isImage;
      return LibrarySourceHealthStepResult(
        step: LibrarySourceHealthStep.image,
        ok: ok,
        sourceError: ok ? null : LibrarySourceErrorKind.invalidImage,
        statusCode: response.statusCode,
        count: response.bodyBytes.length,
        durationMs: watch.elapsedMilliseconds,
        detail: type.isEmpty ? uri.host : '$type ${uri.host}',
      );
    } catch (error) {
      watch.stop();
      if (_isCancellation(error)) rethrow;
      return _failure(
        LibrarySourceHealthStep.image,
        error,
        watch.elapsedMilliseconds,
      );
    }
  }

  static bool _looksLikeImage(Uint8List bytes) {
    if (bytes.length < 12) return false;
    final jpeg = bytes[0] == 0xff && bytes[1] == 0xd8 && bytes[2] == 0xff;
    final png = bytes[0] == 0x89 && bytes[1] == 0x50 && bytes[2] == 0x4e;
    final gif = bytes[0] == 0x47 && bytes[1] == 0x49 && bytes[2] == 0x46;
    final riff =
        bytes[0] == 0x52 &&
        bytes[1] == 0x49 &&
        bytes[2] == 0x46 &&
        bytes[3] == 0x46;
    final avif = bytes[4] == 0x66 && bytes[5] == 0x74 && bytes[6] == 0x79;
    return jpeg || png || gif || riff || avif;
  }

  static bool _isCancellation(Object error) =>
      error is LibraryNetworkException &&
      error.kind == LibraryNetworkErrorKind.cancelled;

  LibrarySourceHealthStepResult _failure(
    LibrarySourceHealthStep step,
    Object error,
    int durationMs,
  ) {
    if (error is LibraryNetworkException) {
      return LibrarySourceHealthStepResult(
        step: step,
        ok: false,
        networkError: error.kind,
        statusCode: error.statusCode,
        durationMs: durationMs,
        detail: error.toString(),
      );
    }
    if (error is LibrarySourceException) {
      return LibrarySourceHealthStepResult(
        step: step,
        ok: false,
        sourceError: error.kind,
        durationMs: durationMs,
        detail: error.message,
      );
    }
    return LibrarySourceHealthStepResult(
      step: step,
      ok: false,
      sourceError: LibrarySourceErrorKind.parseFailed,
      durationMs: durationMs,
      detail: error.runtimeType.toString(),
    );
  }

  /// Former API contract: failures surface as [LibraryAddonException]
  /// (callers catch that type). Network errors are wrapped in a
  /// [LibrarySourceException] of kind [LibrarySourceErrorKind.network].
  Future<T> _legacy<T>(Future<T> Function() run) async {
    try {
      return await run();
    } on LibraryNetworkException catch (error) {
      throw LibrarySourceException(
        LibrarySourceErrorKind.network,
        uri: error.uri,
        networkError: error,
      );
    }
  }

  LibraryAidokuFetchContext _context(
    LibraryFetchMode mode,
    LibraryCancelToken? cancel,
  ) => LibraryAidokuFetchContext(
    fetcher: _fetcher,
    mode: mode,
    cancel: cancel,
    clock: _clock,
  );

  LibraryAidokuEngine? _engineOrNull(LibraryAddon addon) {
    if (!supports(addon)) return null;
    final sourceId = sourceIdFor(addon)!;
    return _engines.putIfAbsent(
      sourceId,
      () => LibraryAidokuEngine.forSite(LibraryAidokuSites.all[sourceId]!),
    );
  }

  LibraryAidokuEngine _engine(LibraryAddon addon) {
    final engine = _engineOrNull(addon);
    if (engine != null) return engine;
    throw LibrarySourceException(
      LibrarySourceErrorKind.unsupported,
      sourceId: sourceIdFor(addon) ?? addon.id,
      detail: unsupportedReasonKind(addon)?.name,
    );
  }
}
