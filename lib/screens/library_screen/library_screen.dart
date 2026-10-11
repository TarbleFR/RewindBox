import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:url_launcher/url_launcher.dart';

import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/l10n/library_feature_locale.dart';
import 'package:neostation/services/gamepad/gamepad_navigation_manager.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_catalog_feed.dart';
import 'package:neostation/services/library_catalog_service.dart';
import 'package:neostation/services/library_download_service.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_manga_models.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/utils/gamepad_nav.dart';
import 'package:neostation/widgets/neo_glass.dart';

import 'library_favorites_view.dart';
import 'library_gamepad_view_controller.dart';
import 'library_local_view.dart';
import 'library_manga_details_screen.dart';
import 'library_reader_launcher.dart';
import 'library_reader_screen.dart';
import 'library_sources_view.dart';

/// Sections opened from the Library hub's shortcut cards.
enum LibraryHubSection { sources, local, favorites }

/// Builds a hub section (tests replace the real sections).
typedef LibraryHubSectionBuilder =
    Widget Function(
      BuildContext context,
      LibraryHubSection section,
      LibraryGamepadViewController controller,
      VoidCallback onBack,
    );

/// Native reading Library for iOS.
///
/// The hub shows the catalogue feed of the active sources ([LibraryCatalogFeed],
/// which survives tab switches), the filters, the search and three sections:
/// Sources, Local library and Favourites & continue reading. Provider
/// websites are never embedded.
class LibraryScreen extends StatefulWidget {
  const LibraryScreen({
    super.key,
    this.feed,
    this.loadAddons,
    this.sectionBuilder,
    this.openOnlineTitle,
    this.enableSounds = true,
  });

  /// Defaults to [LibraryCatalogFeed.instance].
  final LibraryCatalogFeed? feed;

  /// Defaults to [LibraryAddonService.load] of the shared service.
  final Future<List<LibraryAddon>> Function()? loadAddons;

  /// Replaces the section widgets (tests).
  final LibraryHubSectionBuilder? sectionBuilder;

  /// Defaults to [LibraryMangaDetailsScreen.open].
  final LibraryOnlineTitleOpener? openOnlineTitle;

  /// Navigation sounds (off in widget tests).
  final bool enableSounds;

  static LibraryScreenState? _currentState;

  /// The Library state that may take controller input: none while another
  /// route covers the app (title page, reader, picker, dialog, snack-bar
  /// details), so the input never acts on the hidden hub behind it.
  static LibraryScreenState? get _inputTarget {
    final state = _currentState;
    return state != null && state._routeIsCurrent ? state : null;
  }

  static bool navigateLeft() => _inputTarget?._navigateHorizontal(-1) ?? false;
  static bool navigateRight() => _inputTarget?._navigateHorizontal(1) ?? false;
  static bool navigateUp() => _inputTarget?._navigateVertical(-1) ?? false;
  static bool navigateDown() => _inputTarget?._navigateVertical(1) ?? false;
  static void selectCurrent() => _inputTarget?._activateSelection();
  static void backCurrent() => _inputTarget?._back();
  static void deleteCurrent() => _inputTarget?._secondaryAction();

  @override
  State<LibraryScreen> createState() => LibraryScreenState();
}

enum _HubFocus { header, shortcuts, filters, books, empty, searchBar }

enum _HeaderAction { unavailable, refresh }

enum _SearchBarItem { field, filters, close }

/// Scroll controller whose scroll views start at the offset remembered in
/// [LibraryFeedHubMemory] when they are (re)built: after a tab switch,
/// after a section and when switching between the catalogue and the
/// search. Page storage is not used, so the memory is the only source.
class _MemoryScrollController extends ScrollController {
  _MemoryScrollController(this._offset) : super(keepScrollOffset: false);

  final double Function() _offset;

  @override
  double get initialScrollOffset => _offset();
}

/// Geometry of the title grid, used to restore and anchor the scroll
/// position (the grid has a fixed row extent).
class _GridGeometry {
  double start = 0;
  double rowExtent = 0;
  int columns = 5;
}

class _EmptyAction {
  const _EmptyAction(this.icon, this.label, this.onPressed);
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
}

class LibraryScreenState extends State<LibraryScreen> {
  String _lt(String key) => LibraryFeatureLocale.text(context, key);
  String _ltf(String key, Map<String, Object?> values) =>
      LibraryFeatureLocale.format(context, key, values);

  late final LibraryCatalogFeed _feed =
      widget.feed ?? LibraryCatalogFeed.instance;
  LibraryFeedHubMemory get _memory => _feed.hubMemory;
  final LibraryGamepadViewController _sectionController =
      LibraryGamepadViewController();
  final LibraryCatalogService _catalogService = LibraryCatalogService.instance;

  late final ScrollController _catalogueScroll;
  late final ScrollController _searchScroll;
  final _GridGeometry _catalogueGrid = _GridGeometry();
  final _GridGeometry _searchGrid = _GridGeometry();

  final TextEditingController _searchController = TextEditingController();
  final FocusNode _searchFocus = FocusNode(debugLabel: 'library_title_search');
  Timer? _searchDebounce;
  bool _searchFiltersExpanded = false;

  LibraryHubSection? _section;
  _HubFocus _focus = _HubFocus.shortcuts;
  int _headerIndex = 0;
  int _shortcutIndex = 0;
  int _filterIndex = 0;
  int _emptyIndex = 0;
  _SearchBarItem _searchBarItem = _SearchBarItem.field;

  List<LibraryAddon> _addons = const <LibraryAddon>[];
  bool _addonsLoaded = false;
  int _seenContentVersion = -1;

  Object? _visibleKey;
  List<LibraryFeedEntry> _visible = const <LibraryFeedEntry>[];
  Map<String, int> _visibleIndex = const <String, int>{};
  int _languageOptionsVersion = -1;
  List<String> _languageOptionsCache = const <String>['all'];
  int _sourceOptionsVersion = -1;
  Map<String, String> _sourceOptionsCache = const <String, String>{};

  /// How many times the visible list was computed (memoization tests).
  @visibleForTesting
  int visibleComputations = 0;

  /// The titles currently shown, in display order.
  @visibleForTesting
  List<LibraryFeedEntry> get visibleEntries => _visibleEntries();

  @override
  void initState() {
    super.initState();
    LibraryScreen._currentState = this;
    _catalogueScroll = _MemoryScrollController(
      () => _memory.catalogue.scrollOffset,
    )..addListener(_onCatalogueScroll);
    _searchScroll = _MemoryScrollController(() => _memory.search.scrollOffset)
      ..addListener(_onSearchScroll);
    _section = _sectionFromName(_memory.section);
    _searchController.text = _memory.query;
    _seenContentVersion = _feed.contentVersion;
    _feed.addListener(_onFeedChanged);
    if (_memory.searchMode) {
      _focus = _HubFocus.books;
      final query = _memory.query.trim();
      if (query.length >= _feed.minQueryLength &&
          _feed.currentSearch?.query != query) {
        unawaited(_feed.search(query));
      }
    } else if (_memory.catalogue.scrollOffset > 0) {
      _focus = _HubFocus.books;
    }
    if (_section == null) _restorePositionAfterLayout();
    unawaited(_loadAddons());
  }

  ModalRoute<Object?>? _route;

  bool get _routeIsCurrent => mounted && (_route?.isCurrent ?? true);

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _route = ModalRoute.of(context);
  }

  @override
  void deactivate() {
    // Still attached to the scroll views here (they detach before dispose).
    if (_section == null) _rememberPosition();
    super.deactivate();
  }

  @override
  void dispose() {
    if (identical(LibraryScreen._currentState, this)) {
      LibraryScreen._currentState = null;
    }
    _feed.removeListener(_onFeedChanged);
    _catalogueScroll.dispose();
    _searchScroll.dispose();
    _searchDebounce?.cancel();
    _searchController.dispose();
    _searchFocus.dispose();
    super.dispose();
  }

  static LibraryHubSection? _sectionFromName(String name) {
    for (final section in LibraryHubSection.values) {
      if (section.name == name) return section;
    }
    return null;
  }

  void _navSound() {
    if (widget.enableSounds) unawaited(SfxService().playNavSound());
  }

  Future<void> _loadAddons() async {
    List<LibraryAddon> addons;
    try {
      addons = await (widget.loadAddons ?? LibraryAddonService.instance.load)();
    } catch (_) {
      addons = const <LibraryAddon>[];
    }
    if (!mounted) return;
    setState(() {
      _addons = addons;
      _addonsLoaded = true;
    });
    await _feed.open(addons);
  }

  // ------------------------------------------------------------ feed sync --

  LibraryFeedViewMemory get _modeMemory =>
      _memory.searchMode ? _memory.search : _memory.catalogue;
  ScrollController get _activeScroll =>
      _memory.searchMode ? _searchScroll : _catalogueScroll;
  _GridGeometry get _activeGrid =>
      _memory.searchMode ? _searchGrid : _catalogueGrid;

  int get _selectedIndex => _modeMemory.selectedIndex;
  set _selectedIndex(int value) {
    final memory = _modeMemory;
    memory.selectedIndex = value;
    final visible = _visible;
    memory.selectedIdentity = value >= 0 && value < visible.length
        ? visible[value].identity
        : null;
  }

  void _onFeedChanged() {
    if (!mounted) return;
    if (_feed.contentVersion != _seenContentVersion) {
      _seenContentVersion = _feed.contentVersion;
      _keepPositionAcrossUpdate();
    }
    setState(() {});
    _scheduleFillCheck();
  }

  /// First visible title of the active grid and its row, or null when the
  /// grid is not scrolled into view.
  (String, int)? _firstVisible() {
    final shown = _visible;
    final grid = _activeGrid;
    final controller = _activeScroll;
    if (!controller.hasClients ||
        shown.isEmpty ||
        grid.rowExtent <= 0 ||
        grid.columns <= 0) {
      return null;
    }
    final within = controller.position.pixels - grid.start;
    if (within <= 0) return null;
    final row = (within / grid.rowExtent).floor();
    final index = row * grid.columns;
    if (index >= shown.length) return null;
    return (shown[index].identity, row);
  }

  /// Records the position of the active grid before its scroll view is
  /// removed (tab switch, section, search).
  void _rememberPosition() {
    final memory = _modeMemory;
    final first = _firstVisible();
    memory
      ..anchorIdentity = first?.$1
      ..anchorRow = first?.$2 ?? -1;
    final controller = _activeScroll;
    if (controller.hasClients) memory.scrollOffset = controller.offset;
  }

  /// After the active grid is rebuilt at its remembered offset, moves it so
  /// the remembered first title is still first when titles were inserted
  /// above it meanwhile.
  void _restorePositionAfterLayout() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final memory = _modeMemory;
      final identity = memory.anchorIdentity;
      memory.anchorIdentity = null;
      final controller = _activeScroll;
      final grid = _activeGrid;
      if (identity == null || !controller.hasClients || grid.rowExtent <= 0) {
        return;
      }
      _visibleEntries();
      final index = _visibleIndex[identity];
      if (index == null) return;
      final row = index ~/ grid.columns;
      if (row == memory.anchorRow) return;
      final position = controller.position;
      controller.jumpTo(
        (position.pixels + (row - memory.anchorRow) * grid.rowExtent).clamp(
          0.0,
          position.maxScrollExtent,
        ),
      );
    });
  }

  /// Keeps the first visible title and the selected title in place when
  /// titles are inserted above them (sources arrive progressively and the
  /// grid is sorted).
  void _keepPositionAcrossUpdate() {
    final previous = _visible;
    final grid = _activeGrid;
    final controller = _activeScroll;
    final first = _firstVisible();
    final anchor = first?.$1;
    final anchorRow = first?.$2 ?? -1;
    final memory = _modeMemory;
    final selectedIdentity =
        memory.selectedIdentity ??
        (memory.selectedIndex >= 0 && memory.selectedIndex < previous.length
            ? previous[memory.selectedIndex].identity
            : null);

    final next = _visibleEntries();

    if (selectedIdentity != null) {
      final index = _visibleIndex[selectedIdentity] ?? -1;
      if (index >= 0) {
        memory.selectedIndex = index;
        memory.selectedIdentity = selectedIdentity;
      } else if (memory.selectedIndex >= next.length) {
        memory.selectedIndex = next.isEmpty ? 0 : next.length - 1;
        memory.selectedIdentity = null;
      }
    }
    if (anchor != null) {
      final index = _visibleIndex[anchor] ?? -1;
      if (index >= 0) {
        final row = index ~/ grid.columns;
        if (row != anchorRow) {
          // Applied before the next layout, which lays out the new list.
          controller.position.correctBy((row - anchorRow) * grid.rowExtent);
          memory.scrollOffset = controller.position.pixels;
        }
      }
    }
    if (_focus == _HubFocus.books && next.isEmpty) {
      _focus = _memory.searchMode ? _HubFocus.searchBar : _HubFocus.filters;
    }
  }

  void _onCatalogueScroll() {
    _memory.catalogue.scrollOffset = _catalogueScroll.offset;
    _maybeLoadMore(scrolled: true);
  }

  void _onSearchScroll() {
    _memory.search.scrollOffset = _searchScroll.offset;
  }

  /// Visible titles when the last automatic (non-scroll) page request was
  /// made; null when none was made since the filters last changed.
  int? _autoFillVisibleCount;

  /// Requests further pages when the end of the grid is near. Without a
  /// scroll ([scrolled] false: a page arrived, a filter changed), a request
  /// is made only if the previous automatic one made the grid grow, so a
  /// filter that hides every new title cannot page through whole sites.
  void _maybeLoadMore({bool scrolled = false}) {
    if (_memory.searchMode || _section != null) return;
    if (!_catalogueScroll.hasClients) return;
    final position = _catalogueScroll.position;
    final threshold = math.max(900.0, position.viewportDimension * 2.2);
    if (position.extentAfter > threshold || !_feed.canLoadMore) return;
    final shown = _visibleEntries().length;
    if (!scrolled) {
      final previous = _autoFillVisibleCount;
      if (previous != null && shown <= previous) return;
    }
    _autoFillVisibleCount = shown;
    final source = _memory.sourceFilter;
    unawaited(
      _feed.loadMore(
        preferredSourceKey: source == 'all' || source.startsWith('provider:')
            ? null
            : source,
      ),
    );
  }

  void _scheduleFillCheck() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _maybeLoadMore();
    });
  }

  // ---------------------------------------------------------- visibility --

  bool get _safeMode => _feed.safeMode;

  String get _activeQuery => _memory.searchMode ? _memory.query.trim() : '';

  List<LibraryFeedEntry> _visibleEntries() {
    final query = _activeQuery;
    final key = (
      _feed.contentVersion,
      _memory.searchMode,
      query,
      _memory.languageFilter,
      _memory.sourceFilter,
      _safeMode,
      _memory.sortAscending,
    );
    if (key == _visibleKey) return _visible;
    _visibleKey = key;
    visibleComputations++;

    final language = _memory.languageFilter;
    final source = _memory.sourceFilter;
    final safe = _safeMode;
    final seen = <String>{};
    final result = <LibraryFeedEntry>[];
    void consider(LibraryFeedEntry entry) {
      if (!seen.add(entry.identity)) return;
      if (safe && (entry.adult || entry.sourceAdult)) return;
      if (language != 'all' && !entry.languages.contains(language)) return;
      if (source != 'all' && entry.sourceKey != source) return;
      result.add(entry);
    }

    if (_memory.searchMode) {
      final folded = LibraryContentRating.foldAccents(query.toLowerCase());
      if (query.length >= _feed.minQueryLength) {
        for (final entry in _feed.entries) {
          if (entry.foldedTitle.contains(folded)) consider(entry);
        }
        final search = _feed.currentSearch;
        if (search != null && search.query == query) {
          search.entries.forEach(consider);
        }
      }
    } else {
      _feed.entries.forEach(consider);
    }
    final ascending = _memory.sortAscending;
    result.sort((a, b) {
      var comparison = a.foldedTitle.compareTo(b.foldedTitle);
      if (comparison == 0) comparison = a.identity.compareTo(b.identity);
      return ascending ? comparison : -comparison;
    });
    _visible = List<LibraryFeedEntry>.unmodifiable(result);
    _visibleIndex = <String, int>{
      for (var i = 0; i < result.length; i++) result[i].identity: i,
    };
    return _visible;
  }

  List<String> get _languageOptions {
    if (_languageOptionsVersion == _feed.contentVersion) {
      return _languageOptionsCache;
    }
    _languageOptionsVersion = _feed.contentVersion;
    final languages = <String>{
      for (final entry in _feed.entries) ...entry.languages,
      ...?_feed.currentSearch?.entries.expand((entry) => entry.languages),
    };
    const preferred = <String>['fr', 'en'];
    final sorted = languages.toList()
      ..sort((a, b) {
        final ai = preferred.indexOf(a);
        final bi = preferred.indexOf(b);
        if (ai >= 0 || bi >= 0) {
          if (ai < 0) return 1;
          if (bi < 0) return -1;
          return ai.compareTo(bi);
        }
        return a.compareTo(b);
      });
    _languageOptionsCache = <String>['all', ...sorted];
    return _languageOptionsCache;
  }

  /// Source filter options: key → display name (`all` first).
  Map<String, String> get _sourceOptions {
    if (_sourceOptionsVersion == _feed.version) return _sourceOptionsCache;
    _sourceOptionsVersion = _feed.version;
    final pairs = <MapEntry<String, String>>[
      for (final source in _feed.sources) MapEntry(source.key, source.name),
      for (final provider in _feed.metadataProviders.entries)
        MapEntry('provider:${provider.key}', provider.value),
    ]..sort((a, b) => a.value.toLowerCase().compareTo(b.value.toLowerCase()));
    _sourceOptionsCache = <String, String>{
      'all': 'all',
      for (final pair in pairs) pair.key: pair.value,
    };
    return _sourceOptionsCache;
  }

  String _sourceLabel(String key) {
    if (key == 'all') return _lt('allSources');
    return _sourceOptions[key] ?? key;
  }

  String _languageLabel(String code) {
    if (code == 'all') return _lt('all');
    const labels = <String, String>{
      'fr': 'Français',
      'en': 'English',
      'es': 'Español',
      'de': 'Deutsch',
      'it': 'Italiano',
      'pt': 'Português',
      'ja': '日本語',
      'ko': '한국어',
      'zh': '中文',
      'ru': 'Русский',
      'id': 'Bahasa Indonesia',
    };
    return labels[code] ?? code.toUpperCase();
  }

  String _contentFilterLabel() =>
      _safeMode ? _lt('hideAdultShort') : _lt('showAll');

  String _issueText(LibraryFeedIssue issue) => _lt(switch (issue) {
    LibraryFeedIssue.challenge => 'issueChallenge',
    LibraryFeedIssue.offline => 'issueOffline',
    LibraryFeedIssue.timeout => 'issueTimeout',
    LibraryFeedIssue.serverUnavailable => 'issueServerUnavailable',
    LibraryFeedIssue.notFound => 'issueNotFound',
    LibraryFeedIssue.httpStatus => 'issueHttpStatus',
    LibraryFeedIssue.tooLarge => 'issueTooLarge',
    LibraryFeedIssue.invalidResponse => 'issueInvalidResponse',
    LibraryFeedIssue.parseFailed => 'issueParseFailed',
    LibraryFeedIssue.siteChanged => 'issueSiteChanged',
    LibraryFeedIssue.parked => 'issueParked',
    LibraryFeedIssue.unsupported => 'issueUnsupported',
    LibraryFeedIssue.unknown => 'issueUnknown',
  });

  // ------------------------------------------------------------- sections --

  void _openSection(LibraryHubSection section) {
    _searchFocus.unfocus();
    if (_section == null) _rememberPosition();
    setState(() {
      _section = section;
      _memory.section = section.name;
    });
  }

  void _backToHub() {
    final section = _section;
    setState(() {
      _section = null;
      _memory.section = 'hub';
      _focus = _HubFocus.shortcuts;
      _shortcutIndex = section == null ? 0 : section.index;
    });
    _restorePositionAfterLayout();
    if (section == LibraryHubSection.sources) unawaited(_reloadAddons());
  }

  Future<void> _reloadAddons() async {
    await _feed.reloadMetadataProviders();
    await _loadAddons();
  }

  Widget _buildSection(BuildContext context, LibraryHubSection section) {
    final builder = widget.sectionBuilder;
    if (builder != null) {
      return builder(context, section, _sectionController, _backToHub);
    }
    return switch (section) {
      LibraryHubSection.sources => LibrarySourcesView(
        controller: _sectionController,
        onBack: _backToHub,
        onSourcesChanged: () => unawaited(_reloadAddons()),
      ),
      LibraryHubSection.local => LibraryLocalView(
        controller: _sectionController,
        onBack: _backToHub,
      ),
      LibraryHubSection.favorites => LibraryFavoritesView(
        controller: _sectionController,
        onBack: _backToHub,
        addons: _addons,
        openOnlineTitle: widget.openOnlineTitle,
      ),
    };
  }

  // -------------------------------------------------------------- gamepad --

  List<_HeaderAction> get _headerActions => <_HeaderAction>[
    if (_feed.unavailableCount > 0) _HeaderAction.unavailable,
    _HeaderAction.refresh,
  ];

  int get _filterCount => _memory.searchMode ? 5 : 6;

  bool _navigateHorizontal(int delta) {
    if (_section != null) return _sectionController.navigate(delta, 0);
    switch (_focus) {
      case _HubFocus.header:
        final actions = _headerActions;
        final next = (_headerIndex + delta).clamp(0, actions.length - 1);
        if (next == _headerIndex) return false;
        setState(() => _headerIndex = next);
        return true;
      case _HubFocus.shortcuts:
        final next = (_shortcutIndex + delta).clamp(0, 2);
        if (next == _shortcutIndex) return false;
        setState(() => _shortcutIndex = next);
        return true;
      case _HubFocus.filters:
        final next = (_filterIndex + delta).clamp(0, _filterCount - 1);
        if (next == _filterIndex) return false;
        setState(() => _filterIndex = next);
        return true;
      case _HubFocus.searchBar:
        final next = (_searchBarItem.index + delta).clamp(
          0,
          _SearchBarItem.values.length - 1,
        );
        if (next == _searchBarItem.index) return false;
        setState(() => _searchBarItem = _SearchBarItem.values[next]);
        return true;
      case _HubFocus.empty:
        final actions = _emptyActions();
        if (actions.isEmpty) return false;
        final next = (_emptyIndex + delta).clamp(0, actions.length - 1);
        if (next == _emptyIndex) return false;
        setState(() => _emptyIndex = next);
        return true;
      case _HubFocus.books:
        final visible = _visibleEntries();
        if (visible.isEmpty) return false;
        final next = (_selectedIndex + delta).clamp(0, visible.length - 1);
        if (next == _selectedIndex) return false;
        setState(() => _selectedIndex = next);
        _ensureSelectedVisible();
        return true;
    }
  }

  bool _navigateVertical(int delta) {
    if (_section != null) return _sectionController.navigate(0, delta);
    final visible = _visibleEntries();
    final search = _memory.searchMode;

    void focusContentBelow() {
      if (visible.isNotEmpty) {
        _focus = _HubFocus.books;
        _selectedIndex = _selectedIndex.clamp(0, visible.length - 1);
        _ensureSelectedVisible();
      } else if (_emptyActions().isNotEmpty) {
        _focus = _HubFocus.empty;
        _emptyIndex = 0;
      }
    }

    switch (_focus) {
      case _HubFocus.header:
        if (delta <= 0) return false;
        setState(() => _focus = _HubFocus.shortcuts);
        return true;
      case _HubFocus.shortcuts:
        if (delta < 0) {
          setState(() {
            _focus = _HubFocus.header;
            _headerIndex = _headerIndex.clamp(0, _headerActions.length - 1);
          });
          _scrollToTop();
          return true;
        }
        setState(() => _focus = _HubFocus.filters);
        return true;
      case _HubFocus.searchBar:
        if (delta < 0) return false;
        final before = _focus;
        setState(() {
          if (_searchFiltersExpanded) {
            _focus = _HubFocus.filters;
            _filterIndex = _filterIndex.clamp(0, _filterCount - 1);
          } else {
            focusContentBelow();
          }
        });
        return _focus != before;
      case _HubFocus.filters:
        if (delta < 0) {
          setState(
            () => _focus = search ? _HubFocus.searchBar : _HubFocus.shortcuts,
          );
          return true;
        }
        final before = _focus;
        setState(focusContentBelow);
        return _focus != before;
      case _HubFocus.empty:
        if (delta > 0) return false;
        setState(
          () => _focus = search && !_searchFiltersExpanded
              ? _HubFocus.searchBar
              : _HubFocus.filters,
        );
        return true;
      case _HubFocus.books:
        if (visible.isEmpty) return false;
        final columns = _activeGrid.columns;
        final next = _selectedIndex + delta * columns;
        if (delta < 0 && next < 0) {
          setState(
            () => _focus = search && !_searchFiltersExpanded
                ? _HubFocus.searchBar
                : _HubFocus.filters,
          );
          if (!search) _scrollToFilters();
          return true;
        }
        final clamped = next.clamp(0, visible.length - 1);
        if (clamped == _selectedIndex) {
          // Down on the last row asks for more titles (a controller user
          // may have nothing left to scroll).
          if (delta > 0) _maybeLoadMore(scrolled: true);
          return false;
        }
        setState(() => _selectedIndex = clamped);
        _ensureSelectedVisible();
        return true;
    }
  }

  void _activateSelection() {
    if (_section != null) {
      _sectionController.activate();
      return;
    }
    switch (_focus) {
      case _HubFocus.header:
        final actions = _headerActions;
        final action = actions[_headerIndex.clamp(0, actions.length - 1)];
        if (action == _HeaderAction.unavailable) {
          unawaited(_showUnavailableSources());
        } else {
          unawaited(_feed.refresh());
        }
        return;
      case _HubFocus.shortcuts:
        _openSection(LibraryHubSection.values[_shortcutIndex]);
        return;
      case _HubFocus.filters:
        _activateFilter(_filterIndex);
        return;
      case _HubFocus.searchBar:
        switch (_searchBarItem) {
          case _SearchBarItem.field:
            _searchFocus.requestFocus();
          case _SearchBarItem.filters:
            _toggleSearchFilters();
          case _SearchBarItem.close:
            _leaveSearchMode();
        }
        return;
      case _HubFocus.empty:
        final actions = _emptyActions();
        if (actions.isEmpty) return;
        actions[_emptyIndex.clamp(0, actions.length - 1)].onPressed();
        return;
      case _HubFocus.books:
        final visible = _visibleEntries();
        if (_selectedIndex >= 0 && _selectedIndex < visible.length) {
          unawaited(_openEntry(visible[_selectedIndex]));
        }
        return;
    }
  }

  void _back() {
    if (_section != null) {
      if (!_sectionController.back()) _backToHub();
      return;
    }
    if (_memory.searchMode) {
      if (_searchFocus.hasFocus) {
        _searchFocus.unfocus();
        unawaited(_dismissKeyboard());
        return;
      }
      if (_focus == _HubFocus.books || _focus == _HubFocus.empty) {
        setState(() => _focus = _HubFocus.searchBar);
        return;
      }
      _leaveSearchMode();
      return;
    }
    switch (_focus) {
      case _HubFocus.books:
      case _HubFocus.empty:
        setState(() => _focus = _HubFocus.filters);
        _scrollToFilters();
      case _HubFocus.filters:
      case _HubFocus.header:
        setState(() => _focus = _HubFocus.shortcuts);
      case _HubFocus.shortcuts:
      case _HubFocus.searchBar:
        break;
    }
  }

  void _secondaryAction() {
    if (_section != null) _sectionController.secondary();
  }

  void _scrollToTop() {
    if (!_catalogueScroll.hasClients || _memory.searchMode) return;
    unawaited(
      _catalogueScroll.animateTo(
        0,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
      ),
    );
  }

  void _scrollToFilters() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_catalogueScroll.hasClients) return;
      final target = math.max(0.0, _catalogueGrid.start - 260.r);
      if (_catalogueScroll.offset > target) {
        unawaited(
          _catalogueScroll.animateTo(
            target,
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutCubic,
          ),
        );
      }
    });
  }

  void _ensureSelectedVisible() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _focus != _HubFocus.books) return;
      final controller = _activeScroll;
      final grid = _activeGrid;
      if (!controller.hasClients || grid.rowExtent <= 0) return;
      final row = _selectedIndex ~/ grid.columns;
      final top = grid.start + row * grid.rowExtent;
      final bottom = top + grid.rowExtent;
      final position = controller.position;
      final current = position.pixels;
      var target = current;
      if (top < current) {
        target = top;
      } else if (bottom > current + position.viewportDimension) {
        target = bottom - position.viewportDimension;
      }
      target = target.clamp(0.0, position.maxScrollExtent);
      if ((target - current).abs() > 1) {
        unawaited(
          controller.animateTo(
            target,
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutCubic,
          ),
        );
      }
    });
  }

  // -------------------------------------------------------------- filters --

  void _activateFilter(int index) {
    switch (index) {
      case 0:
        unawaited(_openLanguageMenu());
      case 1:
        unawaited(_openSortMenu());
      case 2:
        unawaited(_openIndexMenu());
      case 3:
        unawaited(_openSourceMenu());
      case 4:
        unawaited(_openContentMenu());
      default:
        _enterSearchMode();
    }
  }

  void _filtersChanged() {
    _modeMemory
      ..selectedIndex = 0
      ..selectedIdentity = null;
    _autoFillVisibleCount = null;
    _scheduleFillCheck();
  }

  /// Shows a choice list that works with touch and with the controller
  /// (d-pad moves, A picks, B closes). Popup menus are not used: the
  /// controller cannot reach them.
  Future<T?> _pickChoice<T>({
    required String title,
    required List<_LibraryChoice<T>> choices,
    String? message,
  }) {
    _searchFocus.unfocus();
    return showDialog<T>(
      context: context,
      builder: (_) => _LibraryChoiceDialog<T>(
        title: title,
        message: message,
        choices: choices,
      ),
    );
  }

  Future<void> _openLanguageMenu() async {
    final options = _languageOptions;
    final selected = await _pickChoice<String>(
      title: _lt('language'),
      choices: [
        for (final code in options)
          _LibraryChoice(
            code,
            _languageLabel(code),
            checked: code == _memory.languageFilter,
          ),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _memory.languageFilter = selected;
      _filtersChanged();
    });
  }

  Future<void> _openSortMenu() async {
    final selected = await _pickChoice<bool>(
      title: _lt('sort'),
      choices: [
        _LibraryChoice(true, 'A → Z', checked: _memory.sortAscending),
        _LibraryChoice(false, 'Z → A', checked: !_memory.sortAscending),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _memory.sortAscending = selected;
      _filtersChanged();
    });
  }

  Future<void> _openIndexMenu() async {
    final visible = _visibleEntries();
    if (visible.isEmpty) return;
    final letters = <String>{
      for (final entry in visible) entry.firstLetter,
    }.toList()..sort();
    final selected = await _pickChoice<String>(
      title: _lt('index'),
      choices: [for (final letter in letters) _LibraryChoice(letter, letter)],
    );
    if (!mounted || selected == null) return;
    final index = _visibleEntries().indexWhere(
      (entry) => entry.firstLetter == selected,
    );
    if (index < 0) return;
    setState(() {
      _focus = _HubFocus.books;
      _selectedIndex = index;
    });
    _ensureSelectedVisible();
  }

  Future<void> _openSourceMenu() async {
    final options = _sourceOptions;
    final selected = await _pickChoice<String>(
      title: _lt('source'),
      choices: [
        for (final key in options.keys)
          _LibraryChoice(
            key,
            _sourceLabel(key),
            checked: key == _memory.sourceFilter,
          ),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _memory.sourceFilter = selected;
      _filtersChanged();
    });
  }

  Future<void> _openContentMenu() async {
    final selected = await _pickChoice<bool>(
      title: _lt('content'),
      choices: [
        _LibraryChoice(true, _lt('hideAdult'), checked: _safeMode),
        _LibraryChoice(false, _lt('showAll'), checked: !_safeMode),
      ],
    );
    if (!mounted || selected == null) return;
    setState(() {
      _feed.safeMode = selected;
      _filtersChanged();
    });
  }

  // --------------------------------------------------------------- search --

  Future<void> _dismissKeyboard() async {
    FocusManager.instance.primaryFocus?.unfocus();
    try {
      await SystemChannels.textInput.invokeMethod<void>('TextInput.hide');
    } catch (_) {}
  }

  void _enterSearchMode() {
    _rememberPosition();
    _searchController.value = TextEditingValue(
      text: _memory.query,
      selection: TextSelection.collapsed(offset: _memory.query.length),
    );
    setState(() {
      _memory.searchMode = true;
      _searchFiltersExpanded = false;
      _focus = _HubFocus.searchBar;
      _searchBarItem = _SearchBarItem.field;
      _visibleKey = null;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _memory.searchMode) _searchFocus.requestFocus();
    });
  }

  void _leaveSearchMode() {
    _searchDebounce?.cancel();
    _searchFocus.unfocus();
    unawaited(_dismissKeyboard());
    _feed.clearSearch();
    _searchController.clear();
    setState(() {
      _memory.searchMode = false;
      _memory.query = '';
      _memory.search
        ..scrollOffset = 0
        ..selectedIndex = 0
        ..selectedIdentity = null;
      _searchFiltersExpanded = false;
      _focus = _HubFocus.filters;
      _filterIndex = 5;
    });
    _restorePositionAfterLayout();
  }

  void _onQueryChanged(String value) {
    _searchDebounce?.cancel();
    final query = value.trim();
    setState(() {
      _memory.query = value;
      _memory.search
        ..selectedIndex = 0
        ..selectedIdentity = null;
    });
    if (query.length < _feed.minQueryLength) {
      _feed.clearSearch();
      return;
    }
    _searchDebounce = Timer(const Duration(milliseconds: 420), () {
      if (mounted) _runSearch(query);
    });
  }

  void _runSearch(String query) {
    if (query.length < _feed.minQueryLength) return;
    final current = _feed.currentSearch;
    if (current != null && current.query == query) return;
    if (_searchScroll.hasClients) _searchScroll.jumpTo(0);
    unawaited(_feed.search(query));
  }

  void _onQuerySubmitted(String value) {
    _searchDebounce?.cancel();
    _searchFocus.unfocus();
    unawaited(_dismissKeyboard());
    _runSearch(value.trim());
    setState(() {
      if (_visibleEntries().isNotEmpty) _focus = _HubFocus.books;
    });
  }

  void _clearQuery() {
    _searchDebounce?.cancel();
    _searchController.clear();
    _feed.clearSearch();
    setState(() {
      _memory.query = '';
      _memory.search
        ..selectedIndex = 0
        ..selectedIdentity = null;
    });
    _searchFocus.requestFocus();
  }

  void _toggleSearchFilters() {
    _searchFocus.unfocus();
    unawaited(_dismissKeyboard());
    setState(() {
      _searchFiltersExpanded = !_searchFiltersExpanded;
      if (!_searchFiltersExpanded && _focus == _HubFocus.filters) {
        _focus = _HubFocus.searchBar;
      }
      _filterIndex = _filterIndex.clamp(0, _filterCount - 1);
    });
  }

  // ------------------------------------------------------------- opening --

  Future<void> _openEntry(LibraryFeedEntry entry) async {
    switch (entry.kind) {
      case LibraryFeedSourceKind.metadata:
        await _openMetadataProviderItem(entry.item);
      case LibraryFeedSourceKind.aidoku:
        final open = widget.openOnlineTitle ?? LibraryMangaDetailsScreen.open;
        try {
          await open(
            context,
            item: entry.item,
            addon: entry.addon,
            aidokuSourceId: entry.addon?.aidokuSourceId,
          );
        } catch (error) {
          _showError(_lt('openFailed'), technical: error.toString());
        }
      case LibraryFeedSourceKind.catalog:
        await _openCatalogItem(entry.item);
    }
  }

  Future<void> _openCatalogItem(LibraryCatalogItem item) async {
    if (item.pageUrls.isNotEmpty) {
      await _showPageReader(item.title, item.pageUrls, subtitle: item.subtitle);
      return;
    }
    String text;
    try {
      _showMessage(_lt('loadingBook'));
      text = await _catalogService.loadReadableText(item);
    } catch (error) {
      if (item.description.isNotEmpty) {
        text = item.description;
      } else {
        _showError(_lt('readFailed'), technical: _technicalOf(error));
        return;
      }
    }
    if (!mounted) return;
    _hideMessage();
    await _showTextReader(item, text);
  }

  Future<void> _openMetadataProviderItem(LibraryCatalogItem item) async {
    final hasReadable =
        item.pageUrls.isNotEmpty ||
        (item.content?.trim().isNotEmpty ?? false) ||
        item.contentUrl != null;
    final acquisitions = item.acquisitionLinks;

    if (acquisitions.isEmpty) {
      if (hasReadable) {
        await _readProviderItem(item);
        return;
      }
      _showMessage(_lt('unreadableSource'));
      return;
    }

    // The choice list has its own controller layer (the former dialog's
    // empty modal layer swallowed every button, B included).
    final choice = await _pickChoice<String>(
      title: item.title,
      message: _lt('chooseSourceAction'),
      choices: [
        if (hasReadable)
          _LibraryChoice(
            'read',
            _lt('readNow'),
            icon: Symbols.menu_book_rounded,
          ),
        for (var i = 0; i < acquisitions.length; i++)
          if (acquisitions[i].isExternalReader)
            _LibraryChoice(
              'external:$i',
              _ltf('readOn', {'label': acquisitions[i].label}),
              icon: Symbols.open_in_new_rounded,
            )
          else if (acquisitions[i].canDownload)
            _LibraryChoice(
              'download:$i',
              '${_lt('download')} ${acquisitions[i].label}',
              icon: Symbols.download_rounded,
            ),
      ],
    );

    if (!mounted || choice == null) return;
    if (choice == 'read') {
      await _readProviderItem(item);
      return;
    }
    final separator = choice.indexOf(':');
    if (separator <= 0) return;
    final index = int.tryParse(choice.substring(separator + 1));
    if (index == null || index < 0 || index >= acquisitions.length) return;
    final acquisition = acquisitions[index];

    if (choice.startsWith('external:')) {
      final uri = Uri.tryParse(acquisition.url);
      if (uri == null || uri.scheme != 'https' || uri.host.isEmpty) return;
      await launchUrl(uri, mode: LaunchMode.externalApplication);
      return;
    }
    if (choice.startsWith('download:')) {
      await _downloadProviderAcquisition(item, acquisition);
    }
  }

  Future<void> _readProviderItem(LibraryCatalogItem item) async {
    if (item.pageUrls.isNotEmpty) {
      await _showPageReader(item.title, item.pageUrls, subtitle: item.subtitle);
      return;
    }
    try {
      final text = await _catalogService.loadReadableText(item);
      if (!mounted) return;
      await _showTextReader(item, text);
    } catch (error) {
      _showError(_lt('readFailed'), technical: _technicalOf(error));
    }
  }

  Future<void> _downloadProviderAcquisition(
    LibraryCatalogItem item,
    LibraryAcquisitionLink acquisition,
  ) async {
    _showMessage(_lt('downloading'));
    try {
      final result = await LibraryDownloadService.download(
        acquisition: acquisition,
        title: item.title,
      );
      if (!mounted) return;

      if (result.format == 'epub') {
        try {
          final text = await _catalogService.loadReadableFile(result.filePath);
          if (!mounted) return;
          _hideMessage();
          await _showTextReader(item, text);
        } catch (error) {
          _showError(_lt('readFailed'), technical: _technicalOf(error));
        }
        return;
      }

      if (result.format == 'pdf') {
        _hideMessage();
        try {
          await LibraryReaderLauncher.openPdf(
            context,
            path: result.filePath,
            title: item.title,
            progressKey: 'download:${result.fileName}',
          );
        } catch (error) {
          _showError(_lt('readFailed'), technical: _technicalOf(error));
        }
        return;
      }

      _showMessage(_ltf('downloadSaved', {'file': result.fileName}));
    } catch (error) {
      _showError(_lt('downloadFailedPlain'), technical: _technicalOf(error));
    }
  }

  Future<void> _showTextReader(LibraryCatalogItem item, String text) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryReaderScreen(
          title: item.title,
          subtitle: item.subtitle,
          coverUrl: item.coverUrl,
          text: text,
          bookmarkId: 'book:${item.id}:${item.title}',
        ),
      ),
    );
  }

  Future<void> _showPageReader(
    String title,
    List<String> pages, {
    String subtitle = '',
  }) async {
    await Navigator.of(context).push<void>(
      MaterialPageRoute<void>(
        builder: (_) => LibraryReaderScreen(
          title: title,
          subtitle: subtitle,
          pages: pages,
          bookmarkId: 'pages:$title:$subtitle',
        ),
      ),
    );
  }

  // ------------------------------------------------------------- messages --

  static String _technicalOf(Object error) {
    if (error is LibraryAddonException) {
      final network = error.network;
      return network == null ? error.message : '${error.message} · $network';
    }
    return error.toString();
  }

  void _hideMessage() {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)?.hideCurrentSnackBar();
  }

  void _showMessage(String message) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 3)),
      );
  }

  /// Translated [message]; the raw [technical] detail stays behind the
  /// "Details" action, untranslated.
  void _showError(String message, {String? technical}) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          content: Text(message),
          duration: const Duration(seconds: 5),
          action: technical == null || technical.isEmpty
              ? null
              : SnackBarAction(
                  label: _lt('details'),
                  onPressed: () => unawaited(
                    _showInfoDialog(
                      title: message,
                      children: [_technicalBlock(technical)],
                    ),
                  ),
                ),
        ),
      );
  }

  Widget _technicalBlock(String technical) {
    return Builder(
      builder: (context) {
        final theme = Theme.of(context);
        return Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              LibraryFeatureLocale.text(context, 'technicalDetails'),
              style: theme.textTheme.labelSmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
            const SizedBox(height: 2),
            SelectableText(
              technical,
              style: theme.textTheme.bodySmall?.copyWith(
                fontFamily: 'monospace',
                color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
              ),
            ),
          ],
        );
      },
    );
  }

  Future<void> _showInfoDialog({
    required String title,
    required List<Widget> children,
    String? primaryLabel,
    VoidCallback? onPrimary,
  }) {
    return showDialog<void>(
      context: context,
      builder: (_) => _LibraryHubDialog(
        title: title,
        primaryLabel: primaryLabel,
        onPrimary: onPrimary,
        children: children,
      ),
    );
  }

  Future<void> _showUnavailableSources() {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) => ListenableBuilder(
        listenable: _feed,
        builder: (context, _) {
          final sources = _feed.unavailableSources;
          final theme = Theme.of(context);
          return _LibraryHubDialog(
            title: _lt('unavailableSourcesTitle'),
            primaryLabel: _lt('refreshSources'),
            onPrimary: () => unawaited(_feed.refresh()),
            children: [
              Text(
                _lt('unavailableSourcesHelp'),
                style: theme.textTheme.bodySmall,
              ),
              const SizedBox(height: 12),
              for (final source in sources) ...[
                _buildUnavailableRow(context, source),
                const SizedBox(height: 12),
              ],
            ],
          );
        },
      ),
    );
  }

  Widget _buildUnavailableRow(BuildContext context, LibraryFeedSource source) {
    final theme = Theme.of(context);
    final failure = source.failure;
    if (failure == null) return const SizedBox.shrink();
    final verified = failure.verifiedOn;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Row(
          children: [
            Icon(
              Symbols.cloud_off_rounded,
              size: 18,
              color: theme.colorScheme.error,
            ),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                source.name,
                style: theme.textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
            if (source.loading)
              const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              ),
          ],
        ),
        const SizedBox(height: 3),
        Text(_issueText(failure.issue), style: theme.textTheme.bodyMedium),
        if (failure.known && verified != null)
          Text(
            _ltf('knownStateVerified', {
              'date': MaterialLocalizations.of(
                context,
              ).formatMediumDate(verified.toLocal()),
            }),
            style: theme.textTheme.bodySmall,
          ),
        if (source.entryCount > 0)
          Text(_lt('savedCopyShown'), style: theme.textTheme.bodySmall),
        const SizedBox(height: 3),
        _technicalBlock(failure.technical),
      ],
    );
  }

  void _showSearchSourceDetails(LibraryFeedSearchSource source) {
    final failure = source.failure;
    if (failure == null) return;
    unawaited(
      _showInfoDialog(
        title: source.name,
        children: [
          Text(_issueText(failure.issue)),
          const SizedBox(height: 8),
          _technicalBlock(failure.technical),
        ],
      ),
    );
  }

  // ----------------------------------------------------------------- build --

  @override
  Widget build(BuildContext context) {
    final section = _section;
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(24.r, 54.r, 24.r, 18.r),
        child: section != null
            ? _buildSection(context, section)
            : _memory.searchMode
            ? _buildSearchHub(context)
            : _buildHub(context),
      ),
    );
  }

  Widget _buildHeader(BuildContext context) {
    final theme = Theme.of(context);
    final unavailable = _feed.unavailableCount;
    final actions = _headerActions;
    bool headerSelected(_HeaderAction action) =>
        _focus == _HubFocus.header &&
        actions.indexOf(action) == _headerIndex.clamp(0, actions.length - 1);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        SizedBox(
          width: 58.r,
          height: 58.r,
          child: Center(
            child: Icon(
              Symbols.menu_book_rounded,
              size: 44.r,
              color: theme.colorScheme.onSurface,
            ),
          ),
        ),
        SizedBox(width: 14.r),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                AppLocale.library.getString(context),
                style: theme.textTheme.headlineSmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              SizedBox(height: 3.r),
              Text(
                AppLocale.libraryIntro.getString(context),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodyMedium?.copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.68),
                ),
              ),
            ],
          ),
        ),
        if (_feed.isRefreshing) ...[
          SizedBox(width: 10.r),
          Semantics(
            label: _lt('updatingSources'),
            child: const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
        ],
        if (unavailable > 0) ...[
          SizedBox(width: 8.r),
          _HubHeaderButton(
            selected: headerSelected(_HeaderAction.unavailable),
            icon: Symbols.cloud_off_rounded,
            label: _ltf('sourcesUnavailable', {'count': unavailable}),
            color: theme.colorScheme.error,
            onPressed: () {
              setState(() {
                _focus = _HubFocus.header;
                _headerIndex = 0;
              });
              unawaited(_showUnavailableSources());
            },
          ),
        ],
        SizedBox(width: 8.r),
        _HubHeaderButton(
          selected: headerSelected(_HeaderAction.refresh),
          icon: Symbols.refresh_rounded,
          tooltip: _lt('refreshSources'),
          onPressed: () {
            setState(() {
              _focus = _HubFocus.header;
              _headerIndex = actions.indexOf(_HeaderAction.refresh);
            });
            unawaited(_feed.refresh());
          },
        ),
      ],
    );
  }

  Widget _buildShortcuts(BuildContext context) {
    Widget card(int index, IconData icon, String title, String subtitle) {
      return Expanded(
        child: _LibraryEntryCard(
          selected: _focus == _HubFocus.shortcuts && _shortcutIndex == index,
          icon: icon,
          title: title,
          subtitle: subtitle,
          onTap: () {
            _navSound();
            setState(() {
              _focus = _HubFocus.shortcuts;
              _shortcutIndex = index;
            });
            _openSection(LibraryHubSection.values[index]);
          },
        ),
      );
    }

    return Row(
      children: [
        card(
          LibraryHubSection.sources.index,
          Symbols.hub_rounded,
          _lt('sourcesSection'),
          _lt('sourcesSectionSubtitle'),
        ),
        SizedBox(width: 14.r),
        card(
          LibraryHubSection.local.index,
          Symbols.folder_open_rounded,
          AppLocale.libraryLocal.getString(context),
          AppLocale.libraryLocalSubtitle.getString(context),
        ),
        SizedBox(width: 14.r),
        card(
          LibraryHubSection.favorites.index,
          Symbols.collections_bookmark_rounded,
          _lt('favoritesSection'),
          _lt('favoritesSectionSubtitle'),
        ),
      ],
    );
  }

  Widget _buildHub(BuildContext context) {
    final theme = Theme.of(context);
    final visible = _visibleEntries();
    return CustomScrollView(
      controller: _catalogueScroll,
      physics: const BouncingScrollPhysics(
        parent: AlwaysScrollableScrollPhysics(),
      ),
      slivers: [
        SliverToBoxAdapter(child: _buildHeader(context)),
        SliverToBoxAdapter(child: SizedBox(height: 20.r)),
        SliverToBoxAdapter(child: _buildShortcuts(context)),
        SliverToBoxAdapter(child: SizedBox(height: 12.r)),
        SliverToBoxAdapter(child: _buildFilters(context, visible)),
        SliverToBoxAdapter(child: SizedBox(height: 12.r)),
        _buildGridSliver(context, theme, visible, _catalogueGrid),
        _buildLoadingMoreSliver(),
        SliverToBoxAdapter(child: SizedBox(height: 42.r)),
      ],
    );
  }

  Widget _buildSearchHub(BuildContext context) {
    final theme = Theme.of(context);
    final visible = _visibleEntries();
    // The query band stays fixed and only the results scroll, so the iOS
    // keyboard never covers the field being typed in.
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildSearchRow(context, theme, visible),
        if (_searchFiltersExpanded) ...[
          SizedBox(height: 8.r),
          _buildFilters(context, visible, includeSearch: false),
        ],
        SizedBox(height: 8.r),
        _buildSearchStatusRow(context, theme),
        SizedBox(height: 8.r),
        Expanded(
          child: CustomScrollView(
            controller: _searchScroll,
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            physics: const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
            slivers: [
              _buildGridSliver(context, theme, visible, _searchGrid),
              SliverToBoxAdapter(child: SizedBox(height: 42.r)),
            ],
          ),
        ),
      ],
    );
  }

  Widget _focusRing({required bool selected, required Widget child}) {
    final theme = Theme.of(context);
    return AnimatedContainer(
      duration: const Duration(milliseconds: 130),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(14.r),
        border: Border.all(
          color: selected ? theme.colorScheme.primary : Colors.transparent,
          width: 2,
        ),
      ),
      child: child,
    );
  }

  Widget _buildSearchRow(
    BuildContext context,
    ThemeData theme,
    List<LibraryFeedEntry> visible,
  ) {
    final activeFilters = <bool>[
      _memory.languageFilter != 'all',
      _memory.sourceFilter != 'all',
      !_safeMode,
    ].where((value) => value).length;
    bool barSelected(_SearchBarItem item) =>
        _focus == _HubFocus.searchBar && _searchBarItem == item;
    final searching = _feed.currentSearch?.searching ?? false;

    return Row(
      children: [
        Expanded(
          child: _focusRing(
            selected:
                barSelected(_SearchBarItem.field) || _searchFocus.hasFocus,
            child: TextField(
              controller: _searchController,
              focusNode: _searchFocus,
              textInputAction: TextInputAction.search,
              onTap: () => setState(() {
                _focus = _HubFocus.searchBar;
                _searchBarItem = _SearchBarItem.field;
              }),
              onChanged: _onQueryChanged,
              onSubmitted: _onQuerySubmitted,
              decoration: InputDecoration(
                hintText: _lt('searchHint'),
                prefixIcon: const Icon(Symbols.search_rounded),
                suffixIcon: _searchController.text.isEmpty
                    ? null
                    : IconButton(
                        tooltip: _lt('clear'),
                        constraints: const BoxConstraints(
                          minWidth: 44,
                          minHeight: 44,
                        ),
                        onPressed: _clearQuery,
                        icon: const Icon(Symbols.close_rounded),
                      ),
                isDense: true,
                contentPadding: EdgeInsets.symmetric(
                  horizontal: 12.r,
                  vertical: 12,
                ),
                filled: true,
                fillColor: theme.colorScheme.surfaceContainerHighest.withValues(
                  alpha: 0.5,
                ),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(12.r),
                  borderSide: BorderSide.none,
                ),
              ),
            ),
          ),
        ),
        SizedBox(width: 10.r),
        if (searching) ...[
          Semantics(
            label: _lt('searchingSources'),
            child: const SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2),
            ),
          ),
          SizedBox(width: 7.r),
        ],
        Text(
          _ltf('resultsCount', {'count': visible.length}),
          style: theme.textTheme.bodySmall?.copyWith(
            fontWeight: FontWeight.w600,
            color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
          ),
        ),
        SizedBox(width: 10.r),
        _focusRing(
          selected: barSelected(_SearchBarItem.filters),
          child: TextButton.icon(
            style: TextButton.styleFrom(minimumSize: const Size(44, 44)),
            onPressed: () {
              setState(() {
                _focus = _HubFocus.searchBar;
                _searchBarItem = _SearchBarItem.filters;
              });
              _toggleSearchFilters();
            },
            icon: const Icon(Symbols.tune_rounded),
            label: Text(
              activeFilters > 0
                  ? '${_lt('filters')} ($activeFilters)'
                  : _lt('filters'),
            ),
          ),
        ),
        SizedBox(width: 6.r),
        _focusRing(
          selected: barSelected(_SearchBarItem.close),
          child: IconButton(
            tooltip: _lt('closeSearch'),
            constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
            onPressed: _leaveSearchMode,
            icon: const Icon(Symbols.close_rounded),
          ),
        ),
      ],
    );
  }

  Widget _buildSearchStatusRow(BuildContext context, ThemeData theme) {
    final search = _feed.currentSearch;
    final query = _memory.query.trim();
    if (search == null || search.query != query || search.sources.isEmpty) {
      return const SizedBox(height: 44);
    }
    return SizedBox(
      height: 44,
      child: ListView.separated(
        scrollDirection: Axis.horizontal,
        itemCount: search.sources.length,
        separatorBuilder: (_, _) => SizedBox(width: 8.r),
        itemBuilder: (context, index) {
          final source = search.sources[index];
          final (
            IconData icon,
            Color color,
            String label,
          ) = switch (source.status) {
            LibraryFeedSearchStatus.searching => (
              Symbols.hourglass_top_rounded,
              theme.colorScheme.primary,
              _ltf('searchSourceSearching', {'source': source.name}),
            ),
            LibraryFeedSearchStatus.done => (
              Symbols.check_circle_rounded,
              theme.colorScheme.primary,
              _ltf('searchSourceResults', {
                'source': source.name,
                'count': source.entries.length,
              }),
            ),
            LibraryFeedSearchStatus.failed => (
              Symbols.error_rounded,
              theme.colorScheme.error,
              _ltf('searchSourceFailed', {'source': source.name}),
            ),
            LibraryFeedSearchStatus.skipped => (
              Symbols.block_rounded,
              theme.colorScheme.onSurface.withValues(alpha: 0.55),
              _ltf('searchSourceSkipped', {'source': source.name}),
            ),
          };
          final hasDetails = source.failure != null;
          return Center(
            child: InkWell(
              borderRadius: BorderRadius.circular(18),
              onTap: hasDetails ? () => _showSearchSourceDetails(source) : null,
              child: Container(
                constraints: const BoxConstraints(minHeight: 44),
                padding: const EdgeInsets.symmetric(horizontal: 10),
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(18),
                  color: color.withValues(alpha: 0.10),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    if (source.status == LibraryFeedSearchStatus.searching)
                      SizedBox(
                        width: 14,
                        height: 14,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: color,
                        ),
                      )
                    else
                      Icon(icon, size: 16, color: color),
                    const SizedBox(width: 6),
                    Text(label, style: theme.textTheme.labelMedium),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildFilters(
    BuildContext context,
    List<LibraryFeedEntry> visible, {
    bool includeSearch = true,
  }) {
    final countLabel = _ltf('titlesCount', {'count': visible.length});

    Widget control({
      required int index,
      required IconData icon,
      required String label,
      required String value,
    }) {
      return Expanded(
        child: SizedBox(
          height: math.max(120.0, 190.r),
          child: _FilterControl(
            selected: _focus == _HubFocus.filters && _filterIndex == index,
            icon: icon,
            label: label,
            value: value,
            onTap: () {
              setState(() {
                _focus = _HubFocus.filters;
                _filterIndex = index;
              });
              _activateFilter(index);
            },
          ),
        ),
      );
    }

    final gap = SizedBox(width: 8.r);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            control(
              index: 0,
              icon: Symbols.translate_rounded,
              label: _lt('language'),
              value: _languageLabel(_memory.languageFilter),
            ),
            gap,
            control(
              index: 1,
              icon: Symbols.sort_by_alpha_rounded,
              label: _lt('sort'),
              value: _memory.sortAscending ? 'A → Z' : 'Z → A',
            ),
            gap,
            control(
              index: 2,
              icon: Symbols.abc_rounded,
              label: _lt('index'),
              value: 'A–Z',
            ),
            gap,
            control(
              index: 3,
              icon: Symbols.source_rounded,
              label: _lt('source'),
              value: _sourceLabel(_memory.sourceFilter),
            ),
            gap,
            control(
              index: 4,
              icon: Symbols.visibility_off_rounded,
              label: _lt('content'),
              value: _contentFilterLabel(),
            ),
            if (includeSearch) ...[
              gap,
              control(
                index: 5,
                icon: Symbols.search_rounded,
                label: _lt('search'),
                value: _lt('title'),
              ),
            ],
          ],
        ),
        if (includeSearch)
          SizedBox(
            height: 28.r,
            child: Align(
              alignment: Alignment.centerRight,
              child: Text(
                countLabel,
                style: Theme.of(context).textTheme.bodySmall?.copyWith(
                  color: Theme.of(
                    context,
                  ).colorScheme.onSurface.withValues(alpha: 0.58),
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),
          ),
      ],
    );
  }

  List<_EmptyAction> _emptyActions() {
    if (_memory.searchMode) return const <_EmptyAction>[];
    if (_visibleEntries().isNotEmpty) return const <_EmptyAction>[];
    final noSource =
        _addonsLoaded && !_feed.hasSources && _feed.metadataProviders.isEmpty;
    if (noSource) {
      return <_EmptyAction>[
        _EmptyAction(
          Symbols.library_add_rounded,
          _lt('addCatalogue'),
          () => _openSection(LibraryHubSection.sources),
        ),
        _EmptyAction(
          Symbols.upload_file_rounded,
          _lt('importYourFiles'),
          () => _openSection(LibraryHubSection.local),
        ),
      ];
    }
    if (_feed.allSourcesFailed) {
      return <_EmptyAction>[
        _EmptyAction(
          Symbols.refresh_rounded,
          _lt('refreshSources'),
          () => unawaited(_feed.refresh()),
        ),
        _EmptyAction(
          Symbols.info_rounded,
          _lt('unavailableSourcesTitle'),
          () => unawaited(_showUnavailableSources()),
        ),
      ];
    }
    return const <_EmptyAction>[];
  }

  Widget _buildEmptyState(BuildContext context, ThemeData theme) {
    final search = _memory.searchMode;
    final query = _memory.query.trim();
    final currentSearch = _feed.currentSearch;
    final actions = _emptyActions();
    final noSource =
        !search &&
        _addonsLoaded &&
        !_feed.hasSources &&
        _feed.metadataProviders.isEmpty;

    bool busy;
    String title;
    String? body;
    if (search) {
      if (query.length < _feed.minQueryLength) {
        busy = false;
        title = _lt('searchMinChars');
      } else if (currentSearch == null ||
          currentSearch.query != query ||
          currentSearch.searching) {
        busy = true;
        title = _lt('searchingCatalogs');
      } else {
        busy = false;
        title = _lt('noResults');
      }
    } else if (noSource) {
      busy = false;
      title = _lt('emptyNoSourceTitle');
      body = _lt('emptyNoSourceBody');
    } else if (!_addonsLoaded ||
        (_feed.isRefreshing && _feed.entries.isEmpty)) {
      busy = true;
      title = _lt('loadingCatalogues');
    } else if (_feed.allSourcesFailed) {
      busy = false;
      title = _lt('emptyAllFailedTitle');
      body = _ltf('sourcesUnavailable', {'count': _feed.unavailableCount});
    } else {
      busy = false;
      final source = _feed.source(_memory.sourceFilter);
      title = source != null && _feed.isHiddenBySafeMode(source)
          ? _lt('sourceHiddenBySafeMode')
          : _lt('noBooksFilter');
    }

    return SizedBox(
      height: math.max(200.0, 240.r),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (busy)
              const CircularProgressIndicator()
            else
              Icon(
                Symbols.collections_bookmark_rounded,
                size: 38.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.35),
              ),
            SizedBox(height: 8.r),
            Text(
              title,
              textAlign: TextAlign.center,
              style: theme.textTheme.titleMedium?.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
            if (body != null) ...[
              SizedBox(height: 5.r),
              Text(
                body,
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                ),
              ),
            ],
            if (actions.isNotEmpty) ...[
              SizedBox(height: 14.r),
              Wrap(
                spacing: 12,
                runSpacing: 8,
                alignment: WrapAlignment.center,
                children: [
                  for (var i = 0; i < actions.length; i++)
                    _focusRing(
                      selected: _focus == _HubFocus.empty && _emptyIndex == i,
                      child: FilledButton.tonalIcon(
                        style: FilledButton.styleFrom(
                          minimumSize: const Size(44, 44),
                        ),
                        onPressed: () {
                          setState(() {
                            _focus = _HubFocus.empty;
                            _emptyIndex = i;
                          });
                          actions[i].onPressed();
                        },
                        icon: Icon(actions[i].icon),
                        label: Text(actions[i].label),
                      ),
                    ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildGridSliver(
    BuildContext context,
    ThemeData theme,
    List<LibraryFeedEntry> visible,
    _GridGeometry geometry,
  ) {
    if (visible.isEmpty) {
      return SliverToBoxAdapter(child: _buildEmptyState(context, theme));
    }
    final selectedIndex = _focus == _HubFocus.books ? _selectedIndex : -1;
    return SliverLayoutBuilder(
      builder: (context, constraints) {
        final columns = constraints.crossAxisExtent >= 1200 ? 6 : 5;
        final spacing = 12.r;
        final cardWidth =
            (constraints.crossAxisExtent - (columns - 1) * spacing) / columns;
        final cardHeight = cardWidth / 0.68;
        geometry
          ..columns = columns
          ..start = constraints.precedingScrollExtent
          ..rowExtent = cardHeight + spacing;
        // Decoded at the card's size, rounded up to share cache entries
        // between the catalogue and search layouts.
        final dpr = MediaQuery.devicePixelRatioOf(context);
        final cacheWidth = ((cardWidth * dpr) / 64).ceil() * 64;
        return SliverGrid(
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: columns,
            crossAxisSpacing: spacing,
            mainAxisSpacing: spacing,
            childAspectRatio: 0.68,
          ),
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              final entry = visible[index];
              return _LibraryCatalogCard(
                key: ValueKey<String>(entry.identity),
                entry: entry,
                cacheWidth: cacheWidth,
                selected: selectedIndex == index,
                onTap: () {
                  _navSound();
                  setState(() {
                    _focus = _HubFocus.books;
                    _selectedIndex = index;
                  });
                  unawaited(_openEntry(entry));
                },
              );
            },
            childCount: visible.length,
            findChildIndexCallback: (key) =>
                key is ValueKey<String> && identical(visible, _visible)
                ? _visibleIndex[key.value]
                : null,
            addAutomaticKeepAlives: false,
          ),
        );
      },
    );
  }

  Widget _buildLoadingMoreSliver() {
    if (!_feed.isLoadingMore) {
      return const SliverToBoxAdapter(child: SizedBox.shrink());
    }
    return SliverToBoxAdapter(
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: 20.r),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const SizedBox(
              width: 18,
              height: 18,
              child: CircularProgressIndicator(strokeWidth: 2.2),
            ),
            SizedBox(width: 10.r),
            Text(_lt('loadingMore')),
          ],
        ),
      ),
    );
  }
}

/// Header action with a 44 pt minimum touch target.
class _HubHeaderButton extends StatelessWidget {
  const _HubHeaderButton({
    required this.selected,
    required this.icon,
    required this.onPressed,
    this.label,
    this.tooltip,
    this.color,
  });

  final bool selected;
  final IconData icon;
  final VoidCallback onPressed;
  final String? label;
  final String? tooltip;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final foreground = color ?? theme.colorScheme.primary;
    final text = label;
    final Widget button = text == null
        ? IconButton(
            tooltip: tooltip,
            constraints: const BoxConstraints(minWidth: 44, minHeight: 44),
            onPressed: onPressed,
            icon: Icon(icon, color: foreground),
          )
        : TextButton.icon(
            style: TextButton.styleFrom(
              minimumSize: const Size(44, 44),
              foregroundColor: foreground,
            ),
            onPressed: onPressed,
            icon: Icon(icon, size: 18),
            label: Text(text),
          );
    return AnimatedContainer(
      duration: const Duration(milliseconds: 130),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: selected ? theme.colorScheme.primary : Colors.transparent,
          width: 2,
        ),
      ),
      child: button,
    );
  }
}

/// Dialog of the hub with controller support: B closes, A runs the primary
/// action (or closes when there is none).
class _LibraryHubDialog extends StatefulWidget {
  const _LibraryHubDialog({
    required this.title,
    required this.children,
    this.primaryLabel,
    this.onPrimary,
  });

  final String title;
  final List<Widget> children;
  final String? primaryLabel;
  final VoidCallback? onPrimary;

  @override
  State<_LibraryHubDialog> createState() => _LibraryHubDialogState();
}

class _LibraryHubDialogState extends State<_LibraryHubDialog> {
  late final GamepadNavigation _gamepadNav;
  late final String _layerId = 'library_hub_dialog_${identityHashCode(this)}';
  final ScrollController _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onBack: _close,
      onSelectItem: () {
        final primary = widget.onPrimary;
        if (primary != null) {
          primary();
        } else {
          _close();
        }
      },
      onNavigateUp: () => _scrollBy(-120),
      onNavigateDown: () => _scrollBy(120),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(_layerId);
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _close() {
    if (mounted) Navigator.of(context).maybePop();
  }

  void _scrollBy(double delta) {
    if (!_scroll.hasClients) return;
    final position = _scroll.position;
    _scroll.jumpTo(
      (position.pixels + delta).clamp(0.0, position.maxScrollExtent),
    );
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.sizeOf(context);
    final primary = widget.primaryLabel;
    return _LayerOwnedKeys(
      child: AlertDialog(
        title: Text(widget.title),
        content: SizedBox(
          width: math.min(560, size.width * 0.8),
          child: ConstrainedBox(
            constraints: BoxConstraints(maxHeight: size.height * 0.6),
            child: SingleChildScrollView(
              controller: _scroll,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: widget.children,
              ),
            ),
          ),
        ),
        actions: [
          TextButton(
            style: TextButton.styleFrom(minimumSize: const Size(44, 44)),
            onPressed: _close,
            child: Text(AppLocale.close.getString(context)),
          ),
          if (primary != null)
            FilledButton(
              style: FilledButton.styleFrom(minimumSize: const Size(44, 44)),
              onPressed: widget.onPrimary,
              child: Text(primary),
            ),
        ],
      ),
    );
  }
}

/// Inside a dialog driven by its own controller layer, Flutter's arrow-key
/// focus traversal and Enter activation are switched off: the layer also
/// receives hardware-keyboard keys, so one Enter would otherwise act twice
/// (e.g. pop the dialog, then the screen under it).
class _LayerOwnedKeys extends StatelessWidget {
  const _LayerOwnedKeys({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) => Shortcuts(
    shortcuts: const <ShortcutActivator, Intent>{
      SingleActivator(LogicalKeyboardKey.enter):
          DoNothingAndStopPropagationIntent(),
      SingleActivator(LogicalKeyboardKey.numpadEnter):
          DoNothingAndStopPropagationIntent(),
    },
    child: Actions(
      actions: <Type, Action<Intent>>{
        DirectionalFocusIntent: DoNothingAction(),
      },
      child: Focus(autofocus: true, child: child),
    ),
  );
}

/// One option of [_LibraryChoiceDialog].
class _LibraryChoice<T> {
  const _LibraryChoice(
    this.value,
    this.label, {
    this.checked = false,
    this.icon,
  });

  final T value;
  final String label;

  /// The option currently in effect (a check mark is shown).
  final bool checked;

  /// Shown instead of the check-mark column when set.
  final IconData? icon;
}

/// Choice list of the hub (filters, provider actions) usable with touch and
/// with the controller: the d-pad moves the highlight, A picks it, B closes.
class _LibraryChoiceDialog<T> extends StatefulWidget {
  const _LibraryChoiceDialog({
    required this.title,
    required this.choices,
    this.message,
  });

  final String title;
  final String? message;
  final List<_LibraryChoice<T>> choices;

  @override
  State<_LibraryChoiceDialog<T>> createState() =>
      _LibraryChoiceDialogState<T>();
}

class _LibraryChoiceDialogState<T> extends State<_LibraryChoiceDialog<T>> {
  static const double _rowExtent = 52;

  late final GamepadNavigation _gamepadNav;
  late final String _layerId =
      'library_choice_dialog_${identityHashCode(this)}';
  final ScrollController _scroll = ScrollController();
  late int _highlighted = math.max(
    0,
    widget.choices.indexWhere((choice) => choice.checked),
  );

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onBack: _close,
      onSelectItem: () {
        if (widget.choices.isEmpty) {
          _close();
        } else {
          _pick(_highlighted);
        }
      },
      onNavigateUp: () => _move(-1),
      onNavigateDown: () => _move(1),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        _layerId,
        modal: true,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
      _reveal();
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(_layerId);
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _close() {
    if (mounted) Navigator.of(context).maybePop();
  }

  void _pick(int index) {
    if (!mounted || index < 0 || index >= widget.choices.length) return;
    Navigator.of(context).pop<T>(widget.choices[index].value);
  }

  void _move(int delta) {
    final count = widget.choices.length;
    if (count == 0) return;
    final next = (_highlighted + delta).clamp(0, count - 1);
    if (next == _highlighted) return;
    setState(() => _highlighted = next);
    _reveal();
  }

  void _reveal() {
    if (!_scroll.hasClients) return;
    final position = _scroll.position;
    final top = _highlighted * _rowExtent;
    final bottom = top + _rowExtent;
    var target = position.pixels;
    if (top < target) {
      target = top;
    } else if (bottom > target + position.viewportDimension) {
      target = bottom - position.viewportDimension;
    }
    target = target.clamp(0.0, position.maxScrollExtent);
    if ((target - position.pixels).abs() > 0.5) _scroll.jumpTo(target);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final size = MediaQuery.sizeOf(context);
    final message = widget.message;
    final choices = widget.choices;
    final listHeight = math.min(
      choices.length * _rowExtent,
      math.max(_rowExtent, size.height * 0.5),
    );
    final dialog = AlertDialog(
      title: Text(widget.title, maxLines: 2, overflow: TextOverflow.ellipsis),
      content: SizedBox(
        width: math.min(440, size.width * 0.8),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (message != null) ...[
              Text(message, style: theme.textTheme.bodyMedium),
              const SizedBox(height: 10),
            ],
            if (choices.isNotEmpty)
              SizedBox(
                height: listHeight,
                child: ListView.builder(
                  controller: _scroll,
                  itemExtent: _rowExtent,
                  itemCount: choices.length,
                  itemBuilder: (context, index) {
                    final choice = choices[index];
                    final highlighted = index == _highlighted;
                    return Padding(
                      padding: const EdgeInsets.symmetric(vertical: 2),
                      child: Semantics(
                        selected: choice.checked,
                        child: Material(
                          color: highlighted
                              ? theme.colorScheme.primary.withValues(
                                  alpha: 0.12,
                                )
                              : Colors.transparent,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                            side: BorderSide(
                              color: highlighted
                                  ? theme.colorScheme.primary
                                  : Colors.transparent,
                              width: 2,
                            ),
                          ),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(10),
                            onTap: () => _pick(index),
                            child: Padding(
                              padding: const EdgeInsets.symmetric(
                                horizontal: 10,
                              ),
                              child: Row(
                                children: [
                                  SizedBox(
                                    width: 30,
                                    child: choice.icon != null
                                        ? Icon(choice.icon, size: 20)
                                        : choice.checked
                                        ? Icon(
                                            Symbols.check_rounded,
                                            size: 20,
                                            color: theme.colorScheme.primary,
                                          )
                                        : null,
                                  ),
                                  Expanded(
                                    child: Text(
                                      choice.label,
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                      style: theme.textTheme.bodyLarge
                                          ?.copyWith(
                                            fontWeight: choice.checked
                                                ? FontWeight.w700
                                                : null,
                                          ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
          ],
        ),
      ),
      actions: [
        TextButton(
          style: TextButton.styleFrom(minimumSize: const Size(44, 44)),
          onPressed: _close,
          child: Text(AppLocale.close.getString(context)),
        ),
      ],
    );
    return _LayerOwnedKeys(child: dialog);
  }
}

class _LibraryEntryCard extends StatelessWidget {
  const _LibraryEntryCard({
    required this.selected,
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(12.r);

    return AnimatedContainer(
      duration: const Duration(milliseconds: 150),
      decoration: BoxDecoration(
        borderRadius: radius,
        // Constant width: selecting a card must not change its height, which
        // would move the grid below it.
        border: Border.all(
          color: selected ? theme.colorScheme.primary : Colors.transparent,
          width: 2.r,
        ),
        boxShadow: selected
            ? [
                BoxShadow(
                  color: theme.colorScheme.primary.withValues(alpha: 0.18),
                  blurRadius: 12.r,
                  spreadRadius: 1.r,
                ),
              ]
            : null,
      ),
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: radius,
        enableBackdropBlur: false,
        showSheen: true,
        padding: EdgeInsets.all(14.r),
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Row(
              children: [
                Container(
                  width: 42.r,
                  height: 42.r,
                  decoration: BoxDecoration(
                    color: theme.colorScheme.primary.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(10.r),
                  ),
                  child: Icon(
                    icon,
                    size: 24.r,
                    color: theme.colorScheme.primary,
                  ),
                ),
                SizedBox(width: 12.r),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleMedium?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      SizedBox(height: 3.r),
                      Text(
                        subtitle,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: theme.colorScheme.onSurface.withValues(
                            alpha: 0.62,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: 6.r),
                Icon(
                  Symbols.chevron_right_rounded,
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _FilterControl extends StatelessWidget {
  const _FilterControl({
    required this.selected,
    required this.icon,
    required this.label,
    required this.value,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final String label;
  final String value;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);
    final characters = label.trim().runes.map(String.fromCharCode).toList();
    return Tooltip(
      message: LibraryFeatureLocale.format(context, 'filterValue', {
        'label': label,
        'value': value,
      }),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 130),
        decoration: BoxDecoration(
          borderRadius: radius,
          border: Border.all(
            color: selected
                ? theme.colorScheme.primary
                : theme.colorScheme.outline.withValues(alpha: 0.16),
            width: selected ? 2.r : 1.r,
          ),
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            borderRadius: radius,
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: 7.r, vertical: 9.r),
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(icon, size: 20.r, color: theme.colorScheme.primary),
                  SizedBox(height: 7.r),
                  Expanded(
                    child: Center(
                      child: FittedBox(
                        fit: BoxFit.scaleDown,
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            for (final character in characters)
                              SizedBox(
                                height: 14.r,
                                width: 18.r,
                                child: Center(
                                  child: Text(
                                    character,
                                    maxLines: 1,
                                    softWrap: false,
                                    textAlign: TextAlign.center,
                                    style: theme.textTheme.labelSmall?.copyWith(
                                      height: 1,
                                      fontWeight: FontWeight.w700,
                                      color: theme.colorScheme.onSurface
                                          .withValues(alpha: 0.72),
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                  SizedBox(height: 5.r),
                  SizedBox(
                    width: double.infinity,
                    height: 18.r,
                    child: FittedBox(
                      fit: BoxFit.scaleDown,
                      child: Text(
                        value,
                        maxLines: 1,
                        softWrap: false,
                        textAlign: TextAlign.center,
                        style: theme.textTheme.labelSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                          color: theme.colorScheme.onSurface.withValues(
                            alpha: 0.62,
                          ),
                        ),
                      ),
                    ),
                  ),
                  Icon(
                    Symbols.expand_more_rounded,
                    size: 17.r,
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.45),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _LibraryCatalogCard extends StatelessWidget {
  const _LibraryCatalogCard({
    super.key,
    required this.entry,
    required this.cacheWidth,
    required this.selected,
    required this.onTap,
  });

  final LibraryFeedEntry entry;
  final int cacheWidth;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final radius = BorderRadius.circular(10.r);
    final item = entry.item;
    final placeholder = ColoredBox(
      color: theme.colorScheme.primary.withValues(alpha: 0.10),
      child: Center(
        child: Icon(
          Symbols.menu_book_rounded,
          color: theme.colorScheme.primary,
          size: 34.r,
        ),
      ),
    );
    final coverUrl = item.coverUrl;

    return AnimatedContainer(
      duration: const Duration(milliseconds: 140),
      decoration: BoxDecoration(
        borderRadius: radius,
        border: Border.all(
          color: selected
              ? theme.colorScheme.primary
              : theme.colorScheme.outline.withValues(alpha: 0.15),
          width: selected ? 2.r : 1.r,
        ),
        boxShadow: selected
            ? [
                BoxShadow(
                  color: theme.colorScheme.primary.withValues(alpha: 0.16),
                  blurRadius: 10.r,
                ),
              ]
            : null,
      ),
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: radius,
        enableBackdropBlur: false,
        showSheen: false,
        child: InkWell(
          onTap: onTap,
          borderRadius: radius,
          child: Padding(
            padding: EdgeInsets.all(8.r),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(7.r),
                        child: coverUrl == null
                            ? placeholder
                            : Image(
                                image: LibraryNetworkImage(
                                  coverUrl,
                                  headers: entry.imageHeaders,
                                  cacheWidth: cacheWidth,
                                ),
                                fit: BoxFit.cover,
                                excludeFromSemantics: true,
                                gaplessPlayback: true,
                                errorBuilder: (_, _, _) => placeholder,
                              ),
                      ),
                      if (entry.languageBadge.isNotEmpty)
                        Positioned(
                          top: 6.r,
                          right: 6.r,
                          child: Container(
                            padding: EdgeInsets.symmetric(
                              horizontal: 6.r,
                              vertical: 3.r,
                            ),
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.68),
                              borderRadius: BorderRadius.circular(6.r),
                            ),
                            child: Text(
                              entry.languageBadge,
                              style: TextStyle(
                                fontSize: 9.r.clamp(8.0, 12.0),
                                color: Colors.white,
                                fontWeight: FontWeight.w800,
                              ),
                            ),
                          ),
                        ),
                    ],
                  ),
                ),
                SizedBox(height: 7.r),
                Text(
                  item.title,
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                    height: 1.05,
                  ),
                ),
                if (item.subtitle.isNotEmpty) ...[
                  SizedBox(height: 3.r),
                  Text(
                    item.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(
                      color: theme.colorScheme.onSurface.withValues(
                        alpha: 0.58,
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }
}
