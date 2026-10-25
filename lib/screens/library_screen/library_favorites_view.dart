import 'package:neostation/widgets/liquid_progress.dart';
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_feature_locale.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/confirm_action_dialog.dart';
import 'package:neostation/widgets/library_book_cover.dart';
import 'package:neostation/widgets/library_book_open_transition.dart';
import 'package:neostation/widgets/neo_glass.dart';

import 'library_gamepad_view_controller.dart';
import 'library_hub_dialog.dart';
import 'library_manga_details_screen.dart';
import 'library_reader_launcher.dart';

/// Opens an online title page (defaults to [LibraryMangaDetailsScreen.open]).
typedef LibraryOnlineTitleOpener =
    Future<void> Function(
      BuildContext context, {
      required LibraryCatalogItem item,
      LibraryAddon? addon,
      String? aidokuSourceId,
    });

/// Favourites & continue reading section of the Library hub.
///
/// "Continue reading" lists the most recent unfinished positions of the
/// reading store (local books and online titles); "Favourites" lists the
/// favourite titles, with a badge when their source is no longer active.
/// Removing a favourite asks for confirmation and keeps the reading
/// progress.
class LibraryFavoritesView extends StatefulWidget {
  const LibraryFavoritesView({
    super.key,
    required this.controller,
    required this.onBack,
    this.addons = const <LibraryAddon>[],
    this.store,
    this.resolveLocalBook,
    this.localCoverPath,
    this.openLocalBook,
    this.openOnlineTitle,
  });

  final LibraryGamepadViewController controller;

  /// Returns to the Library hub.
  final VoidCallback onBack;

  /// Active sources (an online title whose source is not among them shows
  /// the "source inactive" badge and opens from its saved data).
  final List<LibraryAddon> addons;

  /// Defaults to [LibraryReadingStore.instance].
  final LibraryReadingStore? store;

  /// Finds an imported book by id; defaults to the local library service.
  final Future<LibraryLocalBook?> Function(String bookId)? resolveLocalBook;

  /// Thumbnail path of a local book; defaults to the local library service.
  final String? Function(LibraryLocalBook book)? localCoverPath;

  /// Defaults to [LibraryReaderLauncher.openLocalBook]. An opener that also
  /// takes `{LibraryBookOpenOrigin? origin}` ([LibraryLocalBookOriginOpener])
  /// receives the card the book is opened from.
  final Future<void> Function(BuildContext context, LibraryLocalBook book)?
  openLocalBook;

  /// Defaults to [LibraryMangaDetailsScreen.open].
  final LibraryOnlineTitleOpener? openOnlineTitle;

  /// `(sourceId, mangaId)` of an `online:<source>:<manga>` key.
  static ({String sourceId, String mangaId})? parseOnlineKey(String key) {
    const prefix = 'online:';
    if (!key.startsWith(prefix)) return null;
    final rest = key.substring(prefix.length);
    final separator = rest.indexOf(':');
    if (separator <= 0 || separator == rest.length - 1) return null;
    return (
      sourceId: rest.substring(0, separator),
      mangaId: rest.substring(separator + 1),
    );
  }

  /// Catalogue item of an online title rebuilt from a favourite snapshot
  /// and/or a reading position, so the title page can open without a new
  /// search. Accepted snapshot shapes: `{item: {title, subtitle,
  /// description, coverUrl, raw}}`, `{raw: {...}}`, or the raw map itself.
  static LibraryCatalogItem? onlineItemFor({
    LibraryFavorite? favorite,
    LibraryReadingProgress? progress,
  }) {
    final key = favorite?.key ?? progress?.key;
    if (key == null) return null;
    final parsed = parseOnlineKey(key);
    final sourceId = favorite?.sourceId ?? parsed?.sourceId;
    final mangaId = favorite?.mangaId ?? parsed?.mangaId;
    if (sourceId == null || sourceId.isEmpty || mangaId == null) return null;

    final snapshot = favorite?.snapshot ?? const <String, Object?>{};
    final snapshotItem = snapshot['item'];
    final itemMap = snapshotItem is Map ? snapshotItem : null;
    final raw = <String, dynamic>{};
    final rawSource = itemMap != null ? itemMap['raw'] : snapshot['raw'];
    if (rawSource is Map) {
      rawSource.forEach((k, v) => raw[k.toString()] = v);
    } else if (itemMap == null) {
      snapshot.forEach((k, v) {
        if (k != 'item') raw[k] = v;
      });
    }

    String? text(Object? value) {
      final result = value?.toString().trim();
      return result == null || result.isEmpty ? null : result;
    }

    raw.putIfAbsent('nativeProvider', () => 'aidoku-web');
    raw['aidokuSourceId'] = sourceId;
    raw['mangaId'] = mangaId;
    raw['onlineKey'] = key;
    final mangaUrl = text(favorite?.mangaUrl);
    if (mangaUrl != null) raw['mangaUrl'] = mangaUrl;
    final language = text(favorite?.language);
    if (language != null) raw.putIfAbsent('language', () => language);
    final headers = (favorite?.coverHeaders.isNotEmpty ?? false)
        ? favorite!.coverHeaders
        : (progress?.coverHeaders ?? const <String, String>{});
    if (headers.isNotEmpty && raw['imageHeaders'] is! Map) {
      raw['imageHeaders'] = Map<String, String>.of(headers);
    }

    final title =
        text(favorite?.title) ??
        text(progress?.title) ??
        text(itemMap?['title']) ??
        mangaId;
    final subtitle =
        text(itemMap?['subtitle']) ??
        text(snapshot['subtitle']) ??
        text(raw['sourceName']) ??
        text(progress?.subtitle) ??
        '';
    final description =
        text(itemMap?['description']) ?? text(snapshot['description']) ?? '';
    final coverUrl =
        text(favorite?.coverUrl) ??
        text(progress?.coverUrl) ??
        text(itemMap?['coverUrl']);

    return LibraryCatalogItem(
      id: mangaId,
      title: title,
      mediaType: LibraryMediaType.manga,
      subtitle: subtitle,
      description: description,
      coverUrl: coverUrl,
      content: null,
      contentUrl: null,
      pageUrls: const <String>[],
      raw: Map<String, dynamic>.unmodifiable(raw),
    );
  }

  @override
  State<LibraryFavoritesView> createState() => _LibraryFavoritesViewState();
}

enum _FavoritesRegion { header, continueRow, favorites }

class _LocalBookState {
  const _LocalBookState(this.book, {this.missing = false});
  final LibraryLocalBook? book;
  final bool missing;
}

/// Controller input of the section. A separate object because the
/// delegate's `activate()` would otherwise override [State.activate].
class _FavoritesGamepad implements LibraryGamepadViewDelegate {
  _FavoritesGamepad(this._state);

  final _LibraryFavoritesViewState _state;

  @override
  bool navigate(int dx, int dy) => _state._navigate(dx, dy);

  @override
  bool activate() => _state._activateSelection();

  /// B always returns to the hub.
  @override
  bool back() => false;

  /// X removes the selected favourite (after confirmation).
  @override
  bool secondary() => _state._removeSelection();
}

class _LibraryFavoritesViewState extends State<LibraryFavoritesView> {
  late final _FavoritesGamepad _gamepad = _FavoritesGamepad(this);
  late LibraryReadingStore _store;
  final ScrollController _scroll = ScrollController();
  final ScrollController _continueScroll = ScrollController();
  final Map<String, _LocalBookState> _localBooks = <String, _LocalBookState>{};
  final Set<String> _resolving = <String>{};

  /// Covers of the local books' cards, by card (`continue:<key>`,
  /// `favorite:<key>`): where the book flies from when it opens.
  final Map<String, GlobalKey> _coverKeys = <String, GlobalKey>{};

  List<LibraryReadingProgress> _continue = const <LibraryReadingProgress>[];
  List<LibraryFavorite> _favorites = const <LibraryFavorite>[];
  _FavoritesRegion _region = _FavoritesRegion.continueRow;
  int _continueIndex = 0;
  int _favoriteIndex = 0;
  int _columns = 5;
  double _gridStart = 0;
  double _rowExtent = 200;
  double _continueExtent = 160;
  bool _loaded = false;

  /// True while a book or title opened here is open (the opener completes
  /// when its route closes): a second tap or A press during the push
  /// transition, which still reaches this view, would open a second
  /// reader or title page on top of the first.
  bool _opening = false;

  String _lt(String key) => LibraryFeatureLocale.text(context, key);
  String _ltf(String key, Map<String, Object?> values) =>
      LibraryFeatureLocale.format(context, key, values);

  @override
  void initState() {
    super.initState();
    _store = widget.store ?? LibraryReadingStore.instance;
    _store.addListener(_onStoreChanged);
    widget.controller.attach(_gamepad);
    _refreshLists();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(LibraryFavoritesView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.controller, widget.controller)) {
      oldWidget.controller.detach(_gamepad);
      widget.controller.attach(_gamepad);
    }
    final store = widget.store ?? LibraryReadingStore.instance;
    if (!identical(store, _store)) {
      _store.removeListener(_onStoreChanged);
      _store = store;
      _store.addListener(_onStoreChanged);
      _refreshLists();
    }
  }

  @override
  void dispose() {
    widget.controller.detach(_gamepad);
    _store.removeListener(_onStoreChanged);
    _scroll.dispose();
    _continueScroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      await _store.load();
    } catch (_) {
      // The store keeps working in memory when its file cannot be read.
    }
    if (!mounted) return;
    setState(() {
      _loaded = true;
      _refreshLists();
    });
  }

  void _onStoreChanged() {
    if (!mounted) return;
    setState(_refreshLists);
  }

  void _refreshLists() {
    // Library books and online titles only. Provider downloads are books of
    // the local library (indexed in Library/Downloads, read under their
    // `local:` key); older keys (`reader:` of the former text reader,
    // `download:` of earlier Build 437 PDF downloads) have no entry to
    // open and are not listed.
    _continue = <LibraryReadingProgress>[
      for (final progress in _store.recent(limit: 30))
        if (!progress.isFinished &&
            (progress.key.startsWith('local:') ||
                progress.key.startsWith('online:')))
          progress,
    ];
    _favorites = _store.favorites;
    final cards = <String>{
      for (final progress in _continue) _continueCard(progress.key),
      for (final favorite in _favorites) _favoriteCard(favorite.key),
    };
    _coverKeys.removeWhere((card, _) => !cards.contains(card));
    if (_continueIndex >= _continue.length) {
      _continueIndex = _continue.isEmpty ? 0 : _continue.length - 1;
    }
    if (_favoriteIndex >= _favorites.length) {
      _favoriteIndex = _favorites.isEmpty ? 0 : _favorites.length - 1;
    }
    if (_region == _FavoritesRegion.continueRow && _continue.isEmpty) {
      _region = _favorites.isEmpty
          ? _FavoritesRegion.header
          : _FavoritesRegion.favorites;
    } else if (_region == _FavoritesRegion.favorites && _favorites.isEmpty) {
      _region = _continue.isEmpty
          ? _FavoritesRegion.header
          : _FavoritesRegion.continueRow;
    }
    for (final progress in _continue) {
      if (progress.kind == LibraryReadingKind.local) {
        _resolveLocal(_localBookId(progress.key));
      }
    }
  }

  static String _localBookId(String key) =>
      key.startsWith('local:') ? key.substring('local:'.length) : key;

  static String _continueCard(String key) => 'continue:$key';
  static String _favoriteCard(String key) => 'favorite:$key';

  /// Cover key of a card; only local books open from their card.
  GlobalKey? _coverKeyFor(String card, LibraryReadingKind kind) =>
      kind == LibraryReadingKind.local
      ? _coverKeys.putIfAbsent(card, () => GlobalKey(debugLabel: card))
      : null;

  void _resolveLocal(String bookId) {
    if (_localBooks.containsKey(bookId) || !_resolving.add(bookId)) return;
    final resolver = widget.resolveLocalBook ?? _defaultResolveLocalBook;
    unawaited(() async {
      _LocalBookState state;
      try {
        final book = await resolver(bookId);
        state = _LocalBookState(book, missing: book == null);
      } catch (_) {
        // Unknown (library not readable now), not missing.
        state = const _LocalBookState(null);
      }
      _resolving.remove(bookId);
      if (!mounted) return;
      setState(() => _localBooks[bookId] = state);
    }());
  }

  static Future<LibraryLocalBook?> _defaultResolveLocalBook(
    String bookId,
  ) async {
    final service = LibraryLocalLibraryService.instance;
    await service.load();
    return service.bookById(bookId);
  }

  String? _coverPathFor(LibraryLocalBook book) {
    final resolver = widget.localCoverPath;
    if (resolver != null) return resolver(book);
    try {
      return LibraryLocalLibraryService.instance.coverPath(book);
    } catch (_) {
      return null;
    }
  }

  /// Thickness of a card's volume: estimated for a known local book, fixed
  /// otherwise (online titles, local books not resolved yet).
  static double _thicknessOf(LibraryLocalBook? book) => book == null
      ? LibraryBookThickness.fixed
      : LibraryBookThickness.estimate(
          format: book.format,
          pageCount: book.pageCount,
          sizeBytes: book.sizeBytes,
        );

  /// Hinge side of a card's volume: the book's own reading direction; on the
  /// right for online titles, which are Aidoku manga (the hub's rule).
  static bool _rightToLeftOf(LibraryReadingKind kind, LibraryLocalBook? book) =>
      kind == LibraryReadingKind.online || (book?.rightToLeft ?? false);

  LibraryAddon? _activeAddonFor(String sourceId) {
    for (final addon in widget.addons) {
      if (addon.aidokuSourceId == sourceId) return addon;
    }
    return null;
  }

  // ------------------------------------------------------------ actions --

  Future<void> _openOnce(Future<void> Function() open) async {
    if (_opening) return;
    _opening = true;
    try {
      await open();
    } finally {
      _opening = false;
    }
  }

  /// Opens [progress]; a local book flies open from its card's [cover].
  Future<void> _openProgress(
    LibraryReadingProgress progress, {
    GlobalKey? cover,
  }) async {
    if (progress.kind == LibraryReadingKind.local) {
      final bookId = _localBookId(progress.key);
      var state = _localBooks[bookId];
      if (state == null || (state.book == null && !state.missing)) {
        final resolver = widget.resolveLocalBook ?? _defaultResolveLocalBook;
        try {
          final book = await resolver(bookId);
          state = _LocalBookState(book, missing: book == null);
        } catch (error) {
          if (mounted) _showError(_lt('readFailed'), error.toString());
          return;
        }
        if (!mounted) return;
        setState(() => _localBooks[bookId] = state!);
      }
      final book = state.book;
      if (book == null) {
        _showMessage(_lt('bookMissing'));
        return;
      }
      try {
        await LibraryReaderLauncher.openLocalBookWith(
          widget.openLocalBook,
          context,
          book,
          origin: cover == null ? null : LibraryBookOpenOrigin.ofCover(cover),
        );
      } catch (error) {
        if (mounted) _showError(_lt('readFailed'), error.toString());
      }
      return;
    }
    final item = LibraryFavoritesView.onlineItemFor(
      favorite: _store.favorite(progress.key),
      progress: progress,
    );
    if (item == null) {
      _showError(_lt('openFailed'), progress.key);
      return;
    }
    await _openOnline(item);
  }

  Future<void> _openFavorite(
    LibraryFavorite favorite, {
    GlobalKey? cover,
  }) async {
    if (favorite.kind == LibraryReadingKind.local) {
      final progress = _store.progressFor(favorite.key);
      await _openProgress(
        progress ??
            LibraryReadingProgress(
              key: favorite.key,
              location: '',
              fraction: 0,
              title: favorite.title,
            ),
        cover: cover,
      );
      return;
    }
    final item = LibraryFavoritesView.onlineItemFor(
      favorite: favorite,
      progress: _store.progressFor(favorite.key),
    );
    if (item == null) {
      _showError(_lt('openFailed'), favorite.key);
      return;
    }
    await _openOnline(item);
  }

  Future<void> _openOnline(LibraryCatalogItem item) async {
    final sourceId = item.raw['aidokuSourceId']?.toString() ?? '';
    final addon = _activeAddonFor(sourceId);
    final open = widget.openOnlineTitle ?? LibraryMangaDetailsScreen.open;
    try {
      await open(context, item: item, addon: addon, aidokuSourceId: sourceId);
    } catch (error) {
      if (mounted) _showError(_lt('openFailed'), error.toString());
    }
  }

  Future<void> _confirmRemove(LibraryFavorite favorite) async {
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: _ltf('removeFavoriteQuestion', {'title': favorite.title}),
      body: _lt('removeFavoriteBody'),
      confirmLabel: _lt('removeFavorite'),
      icon: Symbols.heart_minus_rounded,
    );
    if (!confirmed || !mounted) return;
    await _store.removeFavorite(favorite.key);
    if (!mounted) return;
    _showMessage(_lt('favoriteRemoved'));
  }

  void _showMessage(String message) {
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  void _showError(String message, String technical) {
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          action: SnackBarAction(
            label: _lt('details'),
            onPressed: () => _showTechnical(message, technical),
          ),
        ),
      );
  }

  void _showTechnical(String message, String technical) {
    if (!mounted) return;
    // Controller-aware (B closes): the hub ignores the controller while a
    // dialog covers it.
    unawaited(
      showDialog<void>(
        context: context,
        builder: (_) => LibraryHubDialog(
          title: message,
          children: [LibraryTechnicalDetails(technical)],
        ),
      ),
    );
  }

  // ------------------------------------------------------------ gamepad --

  bool _navigate(int dx, int dy) {
    switch (_region) {
      case _FavoritesRegion.header:
        if (dy > 0) {
          if (_continue.isNotEmpty) {
            setState(() => _region = _FavoritesRegion.continueRow);
            _revealContinue();
            return true;
          }
          if (_favorites.isNotEmpty) {
            setState(() => _region = _FavoritesRegion.favorites);
            _revealFavorite();
            return true;
          }
        }
        return false;
      case _FavoritesRegion.continueRow:
        if (dx != 0) {
          final next = (_continueIndex + dx).clamp(0, _continue.length - 1);
          if (next == _continueIndex) return false;
          setState(() => _continueIndex = next);
          _revealContinue();
          return true;
        }
        if (dy > 0 && _favorites.isNotEmpty) {
          setState(() => _region = _FavoritesRegion.favorites);
          _revealFavorite();
          return true;
        }
        if (dy < 0) {
          setState(() => _region = _FavoritesRegion.header);
          _scrollTo(0);
          return true;
        }
        return false;
      case _FavoritesRegion.favorites:
        if (_favorites.isEmpty) return false;
        if (dx != 0) {
          final next = (_favoriteIndex + dx).clamp(0, _favorites.length - 1);
          if (next == _favoriteIndex) return false;
          setState(() => _favoriteIndex = next);
          _revealFavorite();
          return true;
        }
        if (dy != 0) {
          final next = _favoriteIndex + dy * _columns;
          if (next < 0) {
            setState(
              () => _region = _continue.isNotEmpty
                  ? _FavoritesRegion.continueRow
                  : _FavoritesRegion.header,
            );
            if (_region == _FavoritesRegion.continueRow) {
              _revealContinue();
            } else {
              _scrollTo(0);
            }
            return true;
          }
          final clamped = next.clamp(0, _favorites.length - 1);
          if (clamped == _favoriteIndex) return false;
          setState(() => _favoriteIndex = clamped);
          _revealFavorite();
          return true;
        }
        return false;
    }
  }

  bool _activateSelection() {
    switch (_region) {
      case _FavoritesRegion.header:
        widget.onBack();
        return true;
      case _FavoritesRegion.continueRow:
        if (_continueIndex < _continue.length) {
          final progress = _continue[_continueIndex];
          final cover = _coverKeys[_continueCard(progress.key)];
          unawaited(_openOnce(() => _openProgress(progress, cover: cover)));
          return true;
        }
        return false;
      case _FavoritesRegion.favorites:
        if (_favoriteIndex < _favorites.length) {
          final favorite = _favorites[_favoriteIndex];
          final cover = _coverKeys[_favoriteCard(favorite.key)];
          unawaited(_openOnce(() => _openFavorite(favorite, cover: cover)));
          return true;
        }
        return false;
    }
  }

  bool _removeSelection() {
    if (_region != _FavoritesRegion.favorites ||
        _favoriteIndex >= _favorites.length) {
      return false;
    }
    unawaited(_confirmRemove(_favorites[_favoriteIndex]));
    return true;
  }

  void _scrollTo(double offset) {
    if (!_scroll.hasClients) return;
    final position = _scroll.position;
    final target = offset.clamp(0.0, position.maxScrollExtent);
    if ((target - position.pixels).abs() < 1) return;
    _scroll.animateTo(
      target,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOutCubic,
    );
  }

  void _revealContinue() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _scrollTo(0);
      if (!_continueScroll.hasClients) return;
      final position = _continueScroll.position;
      final left = _continueIndex * _continueExtent;
      final right = left + _continueExtent;
      var target = position.pixels;
      if (left < position.pixels) {
        target = left;
      } else if (right > position.pixels + position.viewportDimension) {
        target = right - position.viewportDimension;
      }
      target = target.clamp(0.0, position.maxScrollExtent);
      if ((target - position.pixels).abs() > 1) {
        _continueScroll.animateTo(
          target,
          duration: const Duration(milliseconds: 180),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }

  void _revealFavorite() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scroll.hasClients) return;
      final position = _scroll.position;
      final row = _favoriteIndex ~/ _columns;
      final top = _gridStart + row * _rowExtent;
      final bottom = top + _rowExtent;
      var target = position.pixels;
      if (top < position.pixels) {
        target = top;
      } else if (bottom > position.pixels + position.viewportDimension) {
        target = bottom - position.viewportDimension;
      }
      _scrollTo(target);
    });
  }

  // -------------------------------------------------------------- build --

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return CustomScrollView(
      controller: _scroll,
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      slivers: [
        SliverToBoxAdapter(child: _buildHeader(theme)),
        SliverToBoxAdapter(child: SizedBox(height: 16.r)),
        SliverToBoxAdapter(
          child: _sectionTitle(
            theme,
            Symbols.auto_stories_rounded,
            _lt('continueReading'),
          ),
        ),
        SliverToBoxAdapter(child: SizedBox(height: 8.r)),
        SliverToBoxAdapter(child: _buildContinueRow(theme)),
        SliverToBoxAdapter(child: SizedBox(height: 18.r)),
        SliverToBoxAdapter(
          child: _sectionTitle(
            theme,
            Symbols.favorite_rounded,
            _lt('favoritesTitle'),
          ),
        ),
        SliverToBoxAdapter(child: SizedBox(height: 8.r)),
        _buildFavoritesSliver(theme),
        SliverToBoxAdapter(child: SizedBox(height: 32.r)),
      ],
    );
  }

  Widget _buildHeader(ThemeData theme) {
    final selected = _region == _FavoritesRegion.header;
    return Row(
      children: [
        Icon(
          Symbols.collections_bookmark_rounded,
          size: 34.r,
          color: theme.colorScheme.onSurface,
        ),
        SizedBox(width: 12.r),
        Expanded(
          child: Text(
            _lt('favoritesSection'),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.headlineSmall?.copyWith(
              fontWeight: FontWeight.w700,
            ),
          ),
        ),
        AnimatedContainer(
          duration: const Duration(milliseconds: 140),
          decoration: BoxDecoration(
            borderRadius: BorderRadius.circular(22),
            border: Border.all(
              color: selected ? theme.colorScheme.primary : Colors.transparent,
              width: 2,
            ),
          ),
          child: FilledButton.tonalIcon(
            style: FilledButton.styleFrom(minimumSize: const Size(44, 44)),
            onPressed: widget.onBack,
            icon: const Icon(Symbols.arrow_back_rounded),
            label: Text(AppLocale.back.getString(context)),
          ),
        ),
      ],
    );
  }

  Widget _sectionTitle(ThemeData theme, IconData icon, String title) {
    return Row(
      children: [
        Icon(icon, size: 18.r, color: theme.colorScheme.primary),
        SizedBox(width: 7.r),
        Text(
          title,
          style: theme.textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.w700,
          ),
        ),
      ],
    );
  }

  Widget _emptyLine(ThemeData theme, String text) {
    return Padding(
      padding: EdgeInsets.symmetric(vertical: 18.r),
      child: Text(
        text,
        style: theme.textTheme.bodyMedium?.copyWith(
          color: theme.colorScheme.onSurface.withValues(alpha: 0.62),
        ),
      ),
    );
  }

  Widget _buildContinueRow(ThemeData theme) {
    if (_continue.isEmpty) {
      return _loaded
          ? _emptyLine(theme, _lt('nothingInProgress'))
          : SizedBox(height: 48.r);
    }
    final height = 150.r.clamp(120.0, 220.0);
    final width = height * 1.9;
    _continueExtent = width + 12.r;
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final coverWidth = (height * 0.66 * dpr).ceil();
    return SizedBox(
      height: height,
      child: ListView.builder(
        controller: _continueScroll,
        scrollDirection: Axis.horizontal,
        itemCount: _continue.length,
        itemExtent: _continueExtent,
        itemBuilder: (context, index) {
          final progress = _continue[index];
          final cover = _coverKeyFor(
            _continueCard(progress.key),
            progress.kind,
          );
          return Padding(
            padding: EdgeInsets.only(right: 12.r),
            child: _buildContinueCard(
              theme,
              progress,
              coverWidth,
              coverKey: cover,
              selected:
                  _region == _FavoritesRegion.continueRow &&
                  _continueIndex == index,
              onTap: () {
                SfxService().playNavSound();
                setState(() {
                  _region = _FavoritesRegion.continueRow;
                  _continueIndex = index;
                });
                unawaited(
                  _openOnce(() => _openProgress(progress, cover: cover)),
                );
              },
            ),
          );
        },
      ),
    );
  }

  Widget _buildContinueCard(
    ThemeData theme,
    LibraryReadingProgress progress,
    int coverWidth, {
    GlobalKey? coverKey,
    required bool selected,
    required VoidCallback onTap,
  }) {
    final percent = (progress.fraction * 100).floor().clamp(0, 100);
    ImageProvider? cover;
    String title = progress.title ?? '';
    String subtitle = progress.chapterTitle ?? progress.subtitle ?? '';
    var missing = false;
    final local = progress.kind == LibraryReadingKind.local;
    final state = local ? _localBooks[_localBookId(progress.key)] : null;
    final book = state?.book;
    if (local) {
      missing = state?.missing ?? false;
      if (book != null) {
        if (title.isEmpty) title = book.title;
        final path = _coverPathFor(book);
        if (path != null) {
          cover = ResizeImage(FileImage(File(path)), width: coverWidth);
        }
      }
      if (subtitle.isEmpty) subtitle = _lt('localBookLabel');
    } else {
      final url = progress.coverUrl;
      if (url != null && url.isNotEmpty) {
        cover = LibraryNetworkImage(
          url,
          headers: progress.coverHeaders.isEmpty ? null : progress.coverHeaders,
          cacheWidth: coverWidth,
        );
      }
      if (subtitle.isEmpty) {
        final parsed = LibraryFavoritesView.parseOnlineKey(progress.key);
        final addon = parsed == null ? null : _activeAddonFor(parsed.sourceId);
        subtitle = addon?.name ?? parsed?.sourceId ?? '';
      }
    }
    if (title.isEmpty) title = progress.key;
    final percentLabel = _ltf('progressPercent', {'percent': percent});
    return Semantics(
      container: true,
      button: true,
      label: '$title, $percentLabel',
      // The card's own tap is excluded with its texts: VoiceOver
      // activates it through this node.
      onTap: onTap,
      excludeSemantics: true,
      child: _SelectableCard(
        selected: selected,
        onTap: onTap,
        child: Opacity(
          opacity: missing ? 0.55 : 1,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              AspectRatio(
                aspectRatio: 0.66,
                child: _Cover(
                  coverKey: coverKey,
                  image: cover,
                  selected: selected,
                  thickness: _thicknessOf(book),
                  rightToLeft: _rightToLeftOf(progress.kind, book),
                ),
              ),
              SizedBox(width: 10.r),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      title,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    SizedBox(height: 4.r),
                    Text(
                      missing ? _lt('bookMissing') : subtitle,
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodySmall?.copyWith(
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.62,
                        ),
                      ),
                    ),
                    const Spacer(),
                    ClipRRect(
                      borderRadius: BorderRadius.circular(3),
                      child: LiquidProgressIndicator(
                        value: progress.fraction,
                        minHeight: 4,
                      ),
                    ),
                    SizedBox(height: 4.r),
                    Text(percentLabel, style: theme.textTheme.labelSmall),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildFavoritesSliver(ThemeData theme) {
    if (_favorites.isEmpty) {
      return SliverToBoxAdapter(
        child: _loaded
            ? _emptyLine(theme, _lt('noFavorites'))
            : SizedBox(height: 48.r),
      );
    }
    return SliverLayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.crossAxisExtent >= 1200 ? 6 : 5;
        final spacing = 12.r;
        final cardWidth =
            (constraints.crossAxisExtent - (columns - 1) * spacing) / columns;
        final cardHeight = cardWidth / 0.62;
        _columns = columns;
        _gridStart = constraints.precedingScrollExtent;
        _rowExtent = cardHeight + spacing;
        final dpr = MediaQuery.devicePixelRatioOf(context);
        final coverWidth = (cardWidth * dpr).ceil();
        return SliverGrid(
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            crossAxisSpacing: spacing,
            mainAxisSpacing: spacing,
            childAspectRatio: 0.62,
          ),
          delegate: SliverChildBuilderDelegate(
            (context, index) => _buildFavoriteCard(
              theme,
              _favorites[index],
              coverWidth,
              selected:
                  _region == _FavoritesRegion.favorites &&
                  _favoriteIndex == index,
              index: index,
            ),
            childCount: _favorites.length,
            addAutomaticKeepAlives: false,
          ),
        );
      },
    );
  }

  Widget _buildFavoriteCard(
    ThemeData theme,
    LibraryFavorite favorite,
    int coverWidth, {
    required bool selected,
    required int index,
  }) {
    final online = favorite.kind == LibraryReadingKind.online;
    final addon = online ? _activeAddonFor(favorite.sourceId) : null;
    final inactive = online && addon == null;
    final sourceLabel = !online
        ? _lt('localBookLabel')
        : addon?.name ??
              favorite.snapshot['sourceName']?.toString() ??
              favorite.sourceId;
    final url = favorite.coverUrl;
    final cover = url == null || url.isEmpty
        ? null
        : LibraryNetworkImage(
            url,
            headers: favorite.coverHeaders.isEmpty
                ? null
                : favorite.coverHeaders,
            cacheWidth: coverWidth,
          );
    // A local favourite also listed in "Continue reading" is already known.
    final book = online ? null : _localBooks[_localBookId(favorite.key)]?.book;
    final coverKey = _coverKeyFor(_favoriteCard(favorite.key), favorite.kind);
    return _SelectableCard(
      selected: selected,
      onTap: () {
        SfxService().playNavSound();
        setState(() {
          _region = _FavoritesRegion.favorites;
          _favoriteIndex = index;
        });
        unawaited(_openOnce(() => _openFavorite(favorite, cover: coverKey)));
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Expanded(
            child: Stack(
              fit: StackFit.expand,
              children: [
                _Cover(
                  coverKey: coverKey,
                  image: cover,
                  selected: selected,
                  thickness: _thicknessOf(book),
                  rightToLeft: _rightToLeftOf(favorite.kind, book),
                ),
                if (inactive)
                  Positioned(
                    left: 6.r,
                    bottom: 6.r,
                    right: 6.r,
                    child: Tooltip(
                      message: _lt('sourceInactiveHelp'),
                      child: Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: 6.r,
                          vertical: 3.r,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.72),
                          borderRadius: BorderRadius.circular(6.r),
                        ),
                        child: Text(
                          _lt('sourceInactive'),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: const TextStyle(
                            color: Colors.white,
                            fontSize: 11,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                      ),
                    ),
                  ),
                Positioned(
                  top: 0,
                  right: 0,
                  child: IconButton(
                    tooltip: _lt('removeFavorite'),
                    constraints: const BoxConstraints(
                      minWidth: 44,
                      minHeight: 44,
                    ),
                    style: IconButton.styleFrom(
                      backgroundColor: Colors.black.withValues(alpha: 0.45),
                      foregroundColor: Colors.white,
                    ),
                    onPressed: () => unawaited(_confirmRemove(favorite)),
                    icon: const Icon(Symbols.heart_minus_rounded, size: 20),
                  ),
                ),
              ],
            ),
          ),
          SizedBox(height: 6.r),
          Text(
            favorite.title,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.titleSmall?.copyWith(
              fontWeight: FontWeight.w700,
              height: 1.05,
            ),
          ),
          SizedBox(height: 2.r),
          Text(
            sourceLabel,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurface.withValues(alpha: 0.58),
            ),
          ),
        ],
      ),
    );
  }
}

class _SelectableCard extends StatelessWidget {
  const _SelectableCard({
    required this.selected,
    required this.onTap,
    required this.child,
  });

  final bool selected;
  final VoidCallback onTap;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: selected
              ? theme.colorScheme.primary
              : theme.colorScheme.outline.withValues(alpha: 0.15),
          width: selected ? 2 : 1,
        ),
      ),
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: radius,
        enableBackdropBlur: false,
        showSheen: false,
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: Padding(padding: EdgeInsets.all(8.r), child: child),
        ),
      ),
    );
  }
}

/// Cover of a card as a book volume (the same cover as the hub). [image] is
/// shown on the front and on the spine.
class _Cover extends StatelessWidget {
  const _Cover({
    this.coverKey,
    required this.image,
    required this.selected,
    this.thickness = LibraryBookThickness.fixed,
    this.rightToLeft = false,
  });

  /// Identifies the [LibraryBookCover] a local book opens from
  /// ([LibraryBookOpenOrigin.ofCover]).
  final GlobalKey? coverKey;
  final ImageProvider? image;
  final bool selected;
  final double thickness;
  final bool rightToLeft;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final placeholder = ColoredBox(
      color: theme.colorScheme.primary.withValues(alpha: 0.10),
      child: Center(
        child: Icon(
          Symbols.menu_book_rounded,
          color: theme.colorScheme.primary,
          size: 30.r,
        ),
      ),
    );
    final provider = image;
    return LibraryBookCover(
      key: coverKey,
      selected: selected,
      rightToLeft: rightToLeft,
      radius: 7.r,
      image: provider,
      thickness: thickness,
      child: provider == null
          ? placeholder
          : Image(
              image: provider,
              fit: BoxFit.cover,
              excludeFromSemantics: true,
              gaplessPlayback: true,
              errorBuilder: (_, _, _) => placeholder,
            ),
    );
  }
}
