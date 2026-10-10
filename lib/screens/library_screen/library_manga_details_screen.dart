import 'dart:async';

import 'package:flutter/material.dart';

import 'package:neostation/l10n/library_sources_locale.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';

import 'library_reader_launcher.dart';
import 'library_sources_view.dart';

/// Opens one online chapter (default: [LibraryReaderLauncher.openOnlineChapter]).
typedef LibraryOnlineChapterOpener =
    Future<void> Function(
      BuildContext context,
      LibraryOnlineChapterSession session,
    );

/// Online title page (Build 437): the catalogue card is shown at once, then
/// the saved details (cache only), then a background refresh that keeps
/// what is visible and the scroll position. Long chapter lists (LelscanFR)
/// arrive progressively. Favourite toggle, resume button from the reading
/// store, chapter list with read marks and a newest/oldest order remembered
/// for the session. Works for favourites of deactivated sources (saved data
/// only, chapters cannot be opened).
class LibraryMangaDetailsScreen extends StatefulWidget {
  const LibraryMangaDetailsScreen({
    super.key,
    required this.item,
    this.addon,
    this.aidokuSourceId,
    this.aidokuService,
    this.readingStore,
    this.imageCache,
    this.chapterOpener,
    this.enableGamepad = true,
  });

  /// Catalogue card or favourite snapshot (its `raw` carries
  /// `aidokuSourceId`, `mangaId` and `imageHeaders` for Aidoku titles).
  final LibraryCatalogItem item;

  /// Active source; null when the source was deactivated (e.g. opened from
  /// a favourite): the screen then shows cached data and explains how to
  /// re-enable the source.
  final LibraryAddon? addon;

  /// Aidoku source id when [addon] is null.
  final String? aidokuSourceId;

  /// Defaults to [LibraryAidokuNativeService.instance].
  final LibraryAidokuNativeService? aidokuService;

  /// Defaults to [LibraryReadingStore.instance].
  final LibraryReadingStore? readingStore;
  final LibraryImageCache? imageCache;

  /// Defaults to [LibraryReaderLauncher.openOnlineChapter].
  final LibraryOnlineChapterOpener? chapterOpener;

  /// False in widget tests that do not stub the gamepad plugin.
  final bool enableGamepad;

  static Future<void> open(
    BuildContext context, {
    required LibraryCatalogItem item,
    LibraryAddon? addon,
    String? aidokuSourceId,
    LibraryAidokuNativeService? aidokuService,
    LibraryReadingStore? readingStore,
    LibraryImageCache? imageCache,
    LibraryOnlineChapterOpener? chapterOpener,
    bool enableGamepad = true,
  }) {
    return Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryMangaDetailsScreen(
          item: item,
          addon: addon,
          aidokuSourceId: aidokuSourceId,
          aidokuService: aidokuService,
          readingStore: readingStore,
          imageCache: imageCache,
          chapterOpener: chapterOpener,
          enableGamepad: enableGamepad,
        ),
      ),
    );
  }

  /// Compact, JSON-safe copy of [item] stored in a favourite so the title
  /// can be reopened without the network ([itemFromFavorite]).
  static Map<String, Object?> favoriteSnapshot(LibraryCatalogItem item) {
    final description = item.description;
    return <String, Object?>{
      'id': item.id,
      'title': item.title,
      'subtitle': item.subtitle,
      'description': description.length > 600
          ? description.substring(0, 600)
          : description,
      'coverUrl': item.coverUrl,
      'mediaType': item.mediaType.name,
      'raw': item.raw,
    };
  }

  /// Catalogue item rebuilt from a favourite written with
  /// [favoriteSnapshot] (older favourites without a snapshot give a minimal
  /// item built from the favourite fields).
  static LibraryCatalogItem itemFromFavorite(LibraryFavorite favorite) {
    final snapshot = favorite.snapshot;
    final storedRaw = snapshot['raw'];
    final raw = <String, dynamic>{
      if (storedRaw is Map)
        for (final entry in storedRaw.entries)
          entry.key.toString(): entry.value,
    };
    raw.putIfAbsent('aidokuSourceId', () => favorite.sourceId);
    raw.putIfAbsent('mangaId', () => favorite.mangaId);
    if (favorite.mangaUrl != null) {
      raw.putIfAbsent('mangaUrl', () => favorite.mangaUrl);
    }
    if (favorite.coverHeaders.isNotEmpty) {
      raw.putIfAbsent('imageHeaders', () => favorite.coverHeaders);
    }
    raw.putIfAbsent('onlineKey', () => favorite.key);
    String text(String key, String fallback) {
      final value = snapshot[key];
      return value is String ? value : fallback;
    }

    return LibraryCatalogItem(
      id: favorite.mangaId,
      title: text('title', favorite.title),
      mediaType:
          LibraryMediaType.values.asNameMap()[snapshot['mediaType']] ??
          LibraryMediaType.manga,
      subtitle: text('subtitle', ''),
      description: text('description', ''),
      coverUrl: snapshot['coverUrl'] is String
          ? snapshot['coverUrl'] as String
          : favorite.coverUrl,
      content: null,
      contentUrl: null,
      pageUrls: const <String>[],
      raw: raw,
    );
  }

  @override
  State<LibraryMangaDetailsScreen> createState() =>
      _LibraryMangaDetailsScreenState();
}

class _LibraryMangaDetailsScreenState extends State<LibraryMangaDetailsScreen> {
  /// Chapter order, remembered while the app runs.
  static bool _newestFirst = true;

  final ScrollController _scroll = ScrollController();
  LibraryMangaDetails? _details;
  List<LibraryMangaChapter> _ascending = const <LibraryMangaChapter>[];
  List<LibraryMangaChapter> _descending = const <LibraryMangaChapter>[];
  bool _loading = true;
  bool _refreshing = false;
  bool _loadingMore = false;
  Object? _error;
  Object? _refreshError;
  bool _descriptionExpanded = false;
  StreamSubscription<LibraryMangaDetails>? _subscription;
  LibraryCancelToken? _cancel;
  Completer<void>? _refreshDone;
  int _storeSignature = 0;

  LibraryAidokuNativeService get _aidoku =>
      widget.aidokuService ?? LibraryAidokuNativeService.instance;
  LibraryReadingStore get _store =>
      widget.readingStore ?? LibraryReadingStore.instance;

  String get _sourceId {
    final raw = widget.item.raw['aidokuSourceId']?.toString();
    if (raw != null && raw.isNotEmpty) return raw;
    final given = widget.aidokuSourceId;
    if (given != null && given.isNotEmpty) return given;
    final addon = widget.addon;
    return addon == null ? '' : _aidoku.sourceIdFor(addon) ?? '';
  }

  String get _onlineKey =>
      _details?.onlineKey ?? LibraryMangaKeys.online(_sourceId, widget.item.id);

  bool get _active {
    final addon = widget.addon;
    return addon != null && _aidoku.supports(addon);
  }

  bool get _deactivated => widget.addon == null;

  LibraryCatalogItem get _item => _details?.item ?? widget.item;

  Map<String, String> get _imageHeaders {
    final raw = widget.item.raw['imageHeaders'];
    if (raw is Map) {
      return <String, String>{
        for (final entry in raw.entries)
          entry.key.toString(): entry.value.toString(),
      };
    }
    final addon = widget.addon;
    return addon == null
        ? const <String, String>{}
        : _aidoku.imageHeaders(addon);
  }

  String _t(String key) => LibrarySourcesLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      LibrarySourcesLocale.format(context, key, values);

  @override
  void initState() {
    super.initState();
    _storeSignature = _computeStoreSignature();
    _store.addListener(_onStoreChanged);
    unawaited(
      _store.load().then((_) => _onStoreChanged(), onError: (Object _) {}),
    );
    if (_active) {
      unawaited(_loadCachedThenRefresh());
    } else if (_deactivated) {
      unawaited(_loadSavedOnly());
    } else {
      _loading = false;
    }
  }

  @override
  void dispose() {
    _store.removeListener(_onStoreChanged);
    _cancel?.cancel();
    unawaited(_subscription?.cancel());
    _completeRefresh();
    _scroll.dispose();
    super.dispose();
  }

  // ------------------------------------------------------------ loading --

  int _computeStoreSignature() {
    final key = _onlineKey;
    final progress = _store.progressFor(key);
    final marks = _store.chapterMarks(key);
    return Object.hash(
      _store.isFavorite(key),
      progress?.updatedAt,
      progress?.chapterId,
      progress?.pageIndex,
      Object.hashAll(
        marks.entries.map(
          (entry) => Object.hash(
            entry.key,
            entry.value.read,
            entry.value.page,
            entry.value.pageCount,
          ),
        ),
      ),
    );
  }

  /// Rebuilds only when this title's favourite, progress or marks changed
  /// (the store notifies on every page turn of any reader).
  void _onStoreChanged() {
    if (!mounted) return;
    final signature = _computeStoreSignature();
    if (signature == _storeSignature) return;
    setState(() => _storeSignature = signature);
  }

  void _apply(LibraryMangaDetails details) {
    _details = details;
    _ascending = details.chaptersAscending;
    _descending = _ascending.reversed.toList(growable: false);
    _error = null;
    _storeSignature = _computeStoreSignature();
  }

  Future<void> _loadCachedThenRefresh() async {
    final addon = widget.addon!;
    final token = LibraryCancelToken();
    _cancel = token;
    try {
      final cached = await _aidoku.loadManga(
        addon,
        widget.item,
        mode: LibraryFetchMode.cacheOnly,
        cancel: token,
      );
      if (mounted && !token.isCancelled && _details == null) {
        setState(() {
          _apply(cached);
          _loading = false;
        });
      }
    } on Object {
      // Nothing usable is saved: the refresh below loads it.
    }
    if (!mounted || token.isCancelled) return;
    _watch(LibraryFetchMode.cacheFirst);
  }

  Future<void> _loadSavedOnly() async {
    final sourceId = _sourceId;
    LibraryMangaDetails? cached;
    if (sourceId.isNotEmpty) {
      try {
        cached = await _aidoku.cachedMangaForSource(sourceId, widget.item);
      } on Object {
        cached = null;
      }
    }
    if (!mounted) return;
    setState(() {
      if (cached != null) _apply(cached);
      _loading = false;
    });
  }

  /// Loads (or refreshes) through [LibraryAidokuNativeService.watchManga],
  /// cancelling a load still running. Visible data stays while it runs.
  Future<void> _watch(LibraryFetchMode mode) {
    final addon = widget.addon;
    if (addon == null || !_active) return Future<void>.value();
    _cancel?.cancel();
    unawaited(_subscription?.cancel());
    _completeRefresh();
    final token = LibraryCancelToken();
    _cancel = token;
    final done = Completer<void>();
    _refreshDone = done;
    setState(() {
      _refreshing = _details != null;
      _loading = _details == null;
      _refreshError = null;
      if (_details == null) _error = null;
    });
    _subscription = _aidoku
        .watchManga(addon, widget.item, mode: mode, cancel: token)
        .listen(
          (details) {
            if (!mounted || token.isCancelled) return;
            setState(() {
              _apply(details);
              _loading = false;
              _loadingMore = !details.chaptersComplete;
            });
          },
          onError: (Object error) {
            if (!mounted || token.isCancelled) return;
            setState(() {
              if (_details == null) {
                _error = error;
              } else {
                _refreshError = error;
              }
            });
          },
          onDone: () {
            if (mounted && !token.isCancelled) {
              setState(() {
                _loading = false;
                _refreshing = false;
                _loadingMore = false;
              });
            }
            if (!done.isCompleted) done.complete();
          },
        );
    return done.future;
  }

  void _completeRefresh() {
    final done = _refreshDone;
    if (done != null && !done.isCompleted) done.complete();
    _refreshDone = null;
  }

  Future<void> _refresh() => _watch(LibraryFetchMode.refresh);

  // ------------------------------------------------------------ actions --

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 3)),
      );
  }

  Future<void> _toggleFavorite() async {
    final item = _item;
    final raw = item.raw;
    final favorite = LibraryFavorite(
      key: _onlineKey,
      sourceId: _sourceId,
      mangaId: widget.item.id,
      title: item.title,
      addonId: widget.addon?.id,
      coverUrl: item.coverUrl,
      coverHeaders: _imageHeaders,
      mangaUrl: raw['mangaUrl']?.toString(),
      language: raw['language']?.toString(),
      snapshot: LibraryMangaDetailsScreen.favoriteSnapshot(item),
    );
    final added = await _store.toggleFavorite(favorite);
    if (!mounted) return;
    _snack(_t(added ? 'favoriteAdded' : 'favoriteRemoved'));
  }

  Future<void> _openChapter(
    LibraryMangaChapter chapter, {
    int? startPage,
  }) async {
    final addon = widget.addon;
    final details = _details;
    if (addon == null || !_active || details == null) {
      _snack(_t('chapterNeedsSource'));
      return;
    }
    final opener =
        widget.chapterOpener ?? LibraryReaderLauncher.openOnlineChapter;
    try {
      await opener(
        context,
        LibraryOnlineChapterSession(
          addon: addon,
          details: details,
          chapter: chapter,
          startPage: startPage,
        ),
      );
    } on Object catch (error) {
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (dialogContext) => LibraryFocusGamepadLayer(
          enableGamepad: widget.enableGamepad,
          debugLabel: 'details_open_error',
          child: AlertDialog(
            title: Text(LibrarySourcesLocale.text(dialogContext, 'openFailed')),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                if (LibrarySourcesLocale.errorKey(error) != 'errorUnknown')
                  Text(
                    LibrarySourcesLocale.text(
                      dialogContext,
                      LibrarySourcesLocale.errorKey(error),
                    ),
                  ),
                LibraryTechnicalDetails(
                  detail: LibrarySourcesLocale.technicalDetail(error),
                ),
              ],
            ),
            actions: <Widget>[
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: Text(LibrarySourcesLocale.text(dialogContext, 'close')),
              ),
            ],
          ),
        ),
      );
    }
  }

  // -------------------------------------------------------------- labels --

  String _chapterLabel(LibraryMangaChapter chapter) {
    final title = chapter.title.trim();
    if (title.isNotEmpty) return title;
    if (chapter.isVolume) {
      return _f('volumeNumber', <String, Object?>{
        'number': LibraryMangaChapter.formatNumber(chapter.volume!),
      });
    }
    if (chapter.number != null) {
      return _f('chapterNumber', <String, Object?>{
        'number': LibraryMangaChapter.formatNumber(chapter.number!),
      });
    }
    return chapter.id;
  }

  String? _statusLabel(LibraryMangaStatus status) => switch (status) {
    LibraryMangaStatus.ongoing => _t('statusOngoing'),
    LibraryMangaStatus.completed => _t('statusCompleted'),
    LibraryMangaStatus.hiatus => _t('statusHiatus'),
    LibraryMangaStatus.cancelled => _t('statusCancelled'),
    LibraryMangaStatus.unknown => null,
  };

  /// True while the chapter list on screen is partial and a load that may
  /// complete it is still running (LelscanFR serves the newest chapters
  /// first: the oldest ones, and maybe the saved one, are not there yet).
  bool get _chaptersPending =>
      _details?.chaptersComplete == false &&
      (_loadingMore || _refreshing || _loading);

  /// Resume target: the saved chapter and page, else the first chapter.
  /// Null while the list is partial and still loading and the saved
  /// chapter is not in it yet: the oldest chapter on screen is then not the
  /// first one of the title.
  ({LibraryMangaChapter chapter, int? startPage, String label})? _resume() {
    if (_ascending.isEmpty) return null;
    final progress = _store.progressFor(_onlineKey);
    final chapterId = progress?.chapterId;
    if (progress != null && chapterId != null) {
      for (final chapter in _ascending) {
        if (chapter.id != chapterId) continue;
        final pageIndex = progress.pageIndex ?? progress.locationPage ?? 0;
        final page = pageIndex + 1;
        final String label;
        if (chapter.isVolume) {
          label = _f('continueVolume', <String, Object?>{
            'volume': LibraryMangaChapter.formatNumber(chapter.volume!),
            'page': page,
          });
        } else if (chapter.number != null) {
          label = _f('continueChapter', <String, Object?>{
            'chapter': LibraryMangaChapter.formatNumber(chapter.number!),
            'page': page,
          });
        } else {
          label = _f('continueTitle', <String, Object?>{
            'title': chapter.displayTitle,
            'page': page,
          });
        }
        return (chapter: chapter, startPage: pageIndex, label: label);
      }
    }
    if (_chaptersPending) return null;
    return (
      chapter: _ascending.first,
      startPage: null,
      label: _t('startReading'),
    );
  }

  // --------------------------------------------------------------- build --

  @override
  Widget build(BuildContext context) {
    final favorite = _store.isFavorite(_onlineKey);
    return LibraryFocusGamepadLayer(
      enableGamepad: widget.enableGamepad,
      debugLabel: 'manga_details',
      onSecondary: () => unawaited(_toggleFavorite()),
      child: Scaffold(
        appBar: AppBar(
          leading: const ExcludeFocus(child: BackButton()),
          title: Text(
            _item.title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
          actions: <Widget>[
            if (_active)
              IconButton(
                tooltip: _t('refresh'),
                onPressed: _refreshing || _loading ? null : _refresh,
                icon: const Icon(Icons.refresh),
              ),
            IconButton(
              key: const ValueKey<String>('favorite-button'),
              tooltip: _t(favorite ? 'favoriteRemove' : 'favoriteAdd'),
              onPressed: _toggleFavorite,
              icon: Icon(favorite ? Icons.favorite : Icons.favorite_border),
            ),
          ],
        ),
        body: SafeArea(
          bottom: false,
          child: LayoutBuilder(
            builder: (context, constraints) {
              final wide = constraints.maxWidth >= 720;
              if (wide) {
                return Row(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    SizedBox(
                      width: (constraints.maxWidth * 0.42).clamp(300, 460),
                      child: SingleChildScrollView(
                        padding: const EdgeInsets.fromLTRB(16, 12, 12, 24),
                        child: _buildHeader(context, favorite),
                      ),
                    ),
                    const VerticalDivider(width: 1),
                    Expanded(child: _buildChapterList(context, header: null)),
                  ],
                );
              }
              return _buildChapterList(
                context,
                header: Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 8),
                  child: _buildHeader(context, favorite),
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(BuildContext context, bool favorite) {
    final theme = Theme.of(context);
    final item = _item;
    final details = _details;
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.68);
    final dpr = MediaQuery.devicePixelRatioOf(context);
    const coverWidth = 112.0;
    final cover = item.coverUrl;
    final status = details == null ? null : _statusLabel(details.status);
    final resume = _resume();
    final sourceName =
        item.raw['sourceName']?.toString() ?? widget.addon?.name ?? _sourceId;
    final genres = details?.genres ?? const <String>[];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        if (_deactivated) _banner(theme, _t('sourceDisabled'), Icons.block),
        if (!_deactivated && !_active)
          _banner(theme, _t('sourceUnsupported'), Icons.block),
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            ClipRRect(
              borderRadius: BorderRadius.circular(10),
              child: SizedBox(
                width: coverWidth,
                height: coverWidth * 1.45,
                child: cover == null
                    ? _coverPlaceholder(theme)
                    : Image(
                        image: LibraryNetworkImage(
                          cover,
                          headers: _imageHeaders,
                          cacheWidth: (coverWidth * dpr).round(),
                          cache: widget.imageCache,
                        ),
                        fit: BoxFit.cover,
                        errorBuilder: (_, _, _) => _coverPlaceholder(theme),
                      ),
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    item.title,
                    style: theme.textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 4),
                  if (details != null && details.author.isNotEmpty)
                    Text(
                      _f('author', <String, Object?>{'name': details.author}),
                      style: theme.textTheme.bodySmall?.copyWith(color: muted),
                    ),
                  if (details != null &&
                      details.artist.isNotEmpty &&
                      details.artist != details.author)
                    Text(
                      _f('artist', <String, Object?>{'name': details.artist}),
                      style: theme.textTheme.bodySmall?.copyWith(color: muted),
                    ),
                  Text(
                    _f('sourceName', <String, Object?>{'name': sourceName}),
                    style: theme.textTheme.bodySmall?.copyWith(color: muted),
                  ),
                  if (details != null && details.typeLabel.isNotEmpty)
                    Text(
                      _f('typeName', <String, Object?>{
                        'type': details.typeLabel,
                      }),
                      style: theme.textTheme.bodySmall?.copyWith(color: muted),
                    ),
                  if (status != null) ...<Widget>[
                    const SizedBox(height: 4),
                    LibraryStatusChip(
                      label: status,
                      state: LibraryLadderState.unknown,
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
        const SizedBox(height: 12),
        Wrap(
          spacing: 8,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: <Widget>[
            FilledButton.icon(
              key: const ValueKey<String>('resume-button'),
              onPressed: resume == null || !_active
                  ? null
                  : () => _openChapter(
                      resume.chapter,
                      startPage: resume.startPage,
                    ),
              icon: const Icon(Icons.menu_book),
              label: Text(
                resume?.label ??
                    _t(
                      _chaptersPending ? 'loadingMoreChapters' : 'startReading',
                    ),
              ),
            ),
            OutlinedButton.icon(
              onPressed: _toggleFavorite,
              icon: Icon(favorite ? Icons.favorite : Icons.favorite_border),
              label: Text(_t(favorite ? 'favoriteRemove' : 'favoriteAdd')),
            ),
          ],
        ),
        if (genres.isNotEmpty) ...<Widget>[
          const SizedBox(height: 10),
          Wrap(
            spacing: 6,
            runSpacing: 4,
            children: <Widget>[
              for (final genre in genres)
                Chip(
                  label: Text(genre),
                  visualDensity: VisualDensity.compact,
                  materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
                ),
            ],
          ),
        ],
        if (item.description.trim().isNotEmpty) ...<Widget>[
          const SizedBox(height: 10),
          Text(
            item.description.trim(),
            maxLines: _descriptionExpanded ? null : 4,
            overflow: _descriptionExpanded
                ? TextOverflow.visible
                : TextOverflow.ellipsis,
            style: theme.textTheme.bodyMedium,
          ),
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: TextButton(
              onPressed: () =>
                  setState(() => _descriptionExpanded = !_descriptionExpanded),
              child: Text(_t(_descriptionExpanded ? 'showLess' : 'showMore')),
            ),
          ),
        ],
        if (details?.stale ?? false)
          _note(theme, _t('savedCopyStale'))
        else if (_deactivated && details != null)
          _note(theme, _t('savedCopy')),
        if (_refreshError != null) _errorNote(theme, _refreshError!),
      ],
    );
  }

  Widget _banner(ThemeData theme, String text, IconData icon) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: DecoratedBox(
        key: const ValueKey<String>('source-banner'),
        decoration: BoxDecoration(
          color: theme.colorScheme.errorContainer,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.all(12),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(icon, color: theme.colorScheme.onErrorContainer),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  text,
                  style: TextStyle(color: theme.colorScheme.onErrorContainer),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _note(ThemeData theme, String text) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Text(
      text,
      style: theme.textTheme.bodySmall?.copyWith(
        color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
      ),
    ),
  );

  Widget _errorNote(ThemeData theme, Object error) => Padding(
    padding: const EdgeInsets.only(top: 8),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: <Widget>[
        Text(
          '${_t('refreshFailed')} ${_t(LibrarySourcesLocale.errorKey(error))}',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.error,
          ),
        ),
        LibraryTechnicalDetails(
          detail: LibrarySourcesLocale.technicalDetail(error),
        ),
      ],
    ),
  );

  Widget _coverPlaceholder(ThemeData theme) => ColoredBox(
    color: theme.colorScheme.primary.withValues(alpha: 0.12),
    child: Icon(Icons.menu_book, size: 40, color: theme.colorScheme.primary),
  );

  Widget _buildChapterList(BuildContext context, {required Widget? header}) {
    final theme = Theme.of(context);
    final chapters = _newestFirst ? _descending : _ascending;
    final marks = _store.chapterMarks(_onlineKey);
    final details = _details;
    final slivers = <Widget>[
      if (header != null) SliverToBoxAdapter(child: header),
      SliverToBoxAdapter(child: _chapterToolbar(theme, chapters.length)),
    ];
    final error = _error;
    if (_loading && details == null) {
      slivers.add(
        const SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.all(32),
            child: Center(child: CircularProgressIndicator()),
          ),
        ),
      );
    } else if (error != null && details == null) {
      slivers.add(SliverToBoxAdapter(child: _errorView(theme, error)));
    } else if (details == null) {
      slivers.add(
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(_t(_deactivated ? 'nothingSaved' : 'noChapters')),
          ),
        ),
      );
    } else if (chapters.isEmpty && !_loadingMore) {
      slivers.add(
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text(_t('noChapters')),
          ),
        ),
      );
    } else {
      slivers.add(
        SliverList.builder(
          itemCount: chapters.length,
          itemBuilder: (context, index) {
            final chapter = chapters[index];
            return _ChapterRow(
              key: ValueKey<String>('chapter-${chapter.id}'),
              label: _chapterLabel(chapter),
              chapter: chapter,
              mark: marks[chapter.id],
              enabled: _active,
              onTap: () => _openChapter(chapter),
            );
          },
        ),
      );
    }
    if (_loadingMore) {
      slivers.add(
        SliverToBoxAdapter(
          child: Padding(
            key: const ValueKey<String>('loading-more-chapters'),
            padding: const EdgeInsets.all(16),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: <Widget>[
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
                const SizedBox(width: 10),
                Text(_t('loadingMoreChapters')),
              ],
            ),
          ),
        ),
      );
    } else if (details != null && !details.chaptersComplete) {
      slivers.add(
        SliverToBoxAdapter(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              _t('chaptersIncomplete'),
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall,
            ),
          ),
        ),
      );
    }
    slivers.add(
      SliverToBoxAdapter(
        child: SizedBox(height: 24 + MediaQuery.paddingOf(context).bottom),
      ),
    );
    final list = CustomScrollView(
      key: const PageStorageKey<String>('manga-chapters'),
      controller: _scroll,
      physics: const AlwaysScrollableScrollPhysics(),
      slivers: slivers,
    );
    if (!_active) return list;
    return RefreshIndicator(onRefresh: _refresh, child: list);
  }

  Widget _chapterToolbar(ThemeData theme, int count) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 8, 8, 4),
      child: Row(
        children: <Widget>[
          Expanded(
            child: Text(
              _f('chapterCount', <String, Object?>{'count': count}),
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          if (_refreshing)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: <Widget>[
                  const SizedBox(
                    width: 14,
                    height: 14,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 6),
                  Text(_t('refreshing'), style: theme.textTheme.bodySmall),
                ],
              ),
            ),
          TextButton.icon(
            key: const ValueKey<String>('order-button'),
            onPressed: () => setState(() => _newestFirst = !_newestFirst),
            icon: Icon(
              _newestFirst ? Icons.arrow_downward : Icons.arrow_upward,
            ),
            label: Text(_t(_newestFirst ? 'newestFirst' : 'oldestFirst')),
          ),
        ],
      ),
    );
  }

  Widget _errorView(ThemeData theme, Object error) {
    return Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: <Widget>[
          Text(
            _t('detailsFailed'),
            style: theme.textTheme.titleMedium?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            _t(LibrarySourcesLocale.errorKey(error)),
            key: const ValueKey<String>('details-error'),
          ),
          LibraryTechnicalDetails(
            detail: LibrarySourcesLocale.technicalDetail(error),
          ),
          const SizedBox(height: 8),
          FilledButton.tonal(onPressed: _refresh, child: Text(_t('retry'))),
        ],
      ),
    );
  }
}

class _ChapterRow extends StatelessWidget {
  const _ChapterRow({
    super.key,
    required this.label,
    required this.chapter,
    required this.mark,
    required this.enabled,
    required this.onTap,
  });

  final String label;
  final LibraryMangaChapter chapter;
  final LibraryChapterMark? mark;
  final bool enabled;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final read = mark?.read ?? false;
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.6);
    final subtitle = <String>[
      if (chapter.date != null)
        MaterialLocalizations.of(
          context,
        ).formatShortDate(chapter.date!.toLocal()),
      if (chapter.scanlator != null && chapter.scanlator!.isNotEmpty)
        chapter.scanlator!,
      if (!read && mark?.page != null)
        mark!.pageCount != null
            ? LibrarySourcesLocale.format(context, 'chapterPage', {
                'page': mark!.page! + 1,
                'count': mark!.pageCount,
              })
            : LibrarySourcesLocale.format(context, 'chapterPageOnly', {
                'page': mark!.page! + 1,
              }),
    ];
    return LibraryFocusRing(
      radius: 8,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 52),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: <Widget>[
                SizedBox(
                  width: 24,
                  child: read
                      ? Semantics(
                          label: LibrarySourcesLocale.text(
                            context,
                            'chapterRead',
                          ),
                          child: Icon(
                            Icons.check_circle,
                            size: 18,
                            color: theme.colorScheme.primary,
                          ),
                        )
                      : mark?.page != null
                      ? Icon(
                          Icons.timelapse,
                          size: 18,
                          color: theme.colorScheme.primary,
                        )
                      : null,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        label,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodyLarge?.copyWith(
                          color: read ? muted : null,
                        ),
                      ),
                      if (subtitle.isNotEmpty)
                        Text(
                          subtitle.join(' • '),
                          style: theme.textTheme.bodySmall?.copyWith(
                            color: muted,
                          ),
                        ),
                    ],
                  ),
                ),
                Icon(
                  enabled ? Icons.chevron_right : Icons.lock_outline,
                  color: muted,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
