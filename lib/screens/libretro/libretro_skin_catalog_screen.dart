import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n/libretro_locale.dart';
import '../../l10n/skin_browser_locale.dart';
import '../../services/libretro_skin_catalogs.dart';
import '../../services/libretro_skin_compatibility.dart';
import '../../services/libretro_skin_service.dart';
import '../../services/logger_service.dart';
import 'libretro_skin_manager_screen.dart';

/// What the catalog page of a console looked like when it was left (Build
/// 448): its filters, its search and its scroll position come back when it
/// is opened again during the same run.
class _CatalogView {
  String query = '';
  String? source;
  String? orientation;
  bool favoritesOnly = false;
  bool showHidden = false;
  bool? filtersOpen;
  double offset = 0;
}

/// Unified skin catalogs for one embedded console: Provenance (with the
/// DeltaStyles and Delta Skins entries it lists), the Delta Skins site and
/// the RetroArch overlays of PocketArch and libretro common-overlays,
/// deduplicated. Every entry goes through the central iPhone filter
/// (LibretroSkinCompatibility on its real info.json or converted overlay):
/// refused entries are hidden, with their reasons one tap away; the others
/// carry their verdict. Entries are listed at once and checked in the
/// background, most downloaded first; installing an entry not checked yet
/// runs the same filter. Installing downloads the skin and runs the same
/// checks and messages as an import from Files.
class LibretroSkinCatalogScreen extends StatefulWidget {
  const LibretroSkinCatalogScreen({
    super.key,
    required this.console,
    required this.skins,
    this.catalogs,
  });

  /// Console id (a key of LibretroCoreCatalog.consoles).
  final String console;
  final LibretroSkinService skins;

  /// Catalogs; created on top of [skins] when null.
  final LibretroSkinCatalogs? catalogs;

  @override
  State<LibretroSkinCatalogScreen> createState() => _LibretroSkinCatalogScreenState();
}

class _LibretroSkinCatalogScreenState extends State<LibretroSkinCatalogScreen>
    with LibretroPageNavigation<LibretroSkinCatalogScreen> {
  static final _log = LoggerService.instance;

  /// Per console, for this run of the app.
  static final Map<String, _CatalogView> _views = <String, _CatalogView>{};

  late final _CatalogView _view = _views.putIfAbsent(widget.console, _CatalogView.new);
  final ScrollController _scroll = ScrollController();
  bool _offsetRestored = false;
  bool _filtersToggled = false;

  late final LibretroSkinCatalogs _catalogs = widget.catalogs ?? LibretroSkinCatalogs.over(widget.skins);
  final TextEditingController _search = TextEditingController();

  List<LibretroCatalogSkin> _entries = const <LibretroCatalogSkin>[];
  final Map<String, LibretroSkinCompatibility> _verdicts = <String, LibretroSkinCompatibility>{};
  final Set<String> _favorites = <String>{};
  final Set<String> _installed = <String>{};
  Set<String> _unavailable = const <String>{};
  bool _loading = true;
  bool _failed = false;
  bool _checking = false;
  bool _favoritesOnly = false;
  bool _showHidden = false;
  String _query = '';
  String? _source;
  String? _orientation;
  String? _installing;

  /// Bumped by each load and on dispose: a classification of an older load
  /// stops and its results are ignored.
  int _generation = 0;

  String _t(String key) => LibretroLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) => LibretroLocale.formatContext(context, key, values);

  bool get _tablet => MediaQuery.sizeOf(context).shortestSide >= 600;

  @override
  void initState() {
    super.initState();
    _query = _view.query;
    _search.text = _view.query;
    _source = _view.source;
    _orientation = _view.orientation;
    _favoritesOnly = _view.favoritesOnly;
    _showHidden = _view.showHidden;
    _scroll.addListener(_rememberOffset);
    unawaited(_load());
  }

  @override
  void dispose() {
    _generation++;
    _rememberView();
    if (widget.catalogs == null) _catalogs.dispose();
    _search.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _rememberOffset() {
    // Not before the saved position was put back: the first layout starts
    // at the top.
    if (_offsetRestored && _scroll.hasClients) _view.offset = _scroll.offset;
  }

  void _rememberView() {
    _view
      ..query = _query
      ..source = _source
      ..orientation = _orientation
      ..favoritesOnly = _favoritesOnly
      ..showHidden = _showHidden;
  }

  /// Back where the page was left, once its entries are laid out.
  void _restoreOffset() {
    if (_offsetRestored) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || _offsetRestored) return;
      _offsetRestored = true;
      if (!_scroll.hasClients) return;
      final target = _view.offset.clamp(0.0, _scroll.position.maxScrollExtent).toDouble();
      if (target > 0) _scroll.jumpTo(target);
    });
  }

  /// Phones in landscape keep the screen for the skins: the filters start
  /// folded there (and open elsewhere) until the user opens or folds them.
  bool _filtersOpen(BuildContext context) {
    final chosen = _view.filtersOpen;
    if (chosen != null) return chosen;
    final size = MediaQuery.sizeOf(context);
    return !(size.width > size.height && size.shortestSide < 600);
  }

  int get _activeFilters =>
      (_source == null ? 0 : 1) + (_orientation == null ? 0 : 1) + (_favoritesOnly ? 1 : 0);

  void _retry() {
    setState(() {
      _loading = true;
      _failed = false;
    });
    unawaited(_load(refresh: true));
  }

  Future<void> _load({bool refresh = false}) async {
    final generation = ++_generation;
    List<LibretroCatalogSkin>? entries;
    final favorites = <String>{};
    try {
      entries = await _catalogs.load(refresh: refresh);
      favorites.addAll(await _catalogs.favorites());
    } catch (error) {
      _log.w('Libretro skin catalogs failed: $error');
    }
    if (!mounted || generation != _generation) return;
    final unavailable = _catalogs.unavailableSources;
    // The overlay index ships with NeoStation: without any online catalog
    // (Provenance, cached or not, and the Delta Skins site) nothing can be
    // checked or downloaded, the overlays included.
    final offline = unavailable.contains(LibretroSkinSources.provenance) &&
        unavailable.contains(LibretroSkinSources.deltaSkins);
    setState(() {
      _loading = false;
      _failed = entries == null || offline;
      _entries = _failed ? const <LibretroCatalogSkin>[] : LibretroSkinCatalogs.forConsole(entries!, widget.console);
      _unavailable = unavailable;
      _verdicts.clear();
      _favorites
        ..clear()
        ..addAll(favorites);
      if (_source != null && !_entries.any((entry) => entry.source == _source)) _source = null;
    });
    if (!_failed) {
      _restoreOffset();
      unawaited(_classify(generation));
    }
  }

  Future<void> _classify(int generation) async {
    final entries = _entries;
    if (entries.isEmpty) return;
    setState(() => _checking = true);
    try {
      await _catalogs.classifyAll(
        entries,
        widget.console,
        onVerdict: (entry, verdict) {
          if (!mounted || generation != _generation) return;
          setState(() => _verdicts[entry.key] = verdict);
        },
        cancelled: () => !mounted || generation != _generation,
      );
    } catch (error) {
      _log.w('Libretro skin compatibility check failed: $error');
    }
    if (!mounted || generation != _generation) return;
    setState(() => _checking = false);
  }

  Future<void> _toggleFavorite(LibretroCatalogSkin entry) async {
    final favorite = !_favorites.contains(entry.key);
    setState(() => favorite ? _favorites.add(entry.key) : _favorites.remove(entry.key));
    await _catalogs.setFavorite(entry, favorite);
  }

  Future<void> _install(LibretroCatalogSkin entry) async {
    if (_installing != null) return;
    final skins = widget.skins;
    setState(() => _installing = entry.key);
    LibretroSkinImportResult result;
    try {
      result = await _catalogs.install(entry, widget.console);
    } catch (error) {
      result = LibretroSkinImportFailed(LibretroSkinMessages.download, technicalDetails: '$error');
    }
    if (!mounted) {
      if (result is LibretroSkinNeedsReplaceConfirmation) await skins.discard(result);
      return;
    }
    final installed = await showLibretroSkinImportResult(context, skins, result, console: widget.console);
    if (!mounted) return;
    setState(() {
      // A skin whose info.json declares other consoles is installed for
      // those consoles only (announced as such): it is not marked here.
      if (installed != null && installed.consoles.contains(widget.console)) _installed.add(entry.key);
      final refused = result is LibretroSkinImportFailed ? result.compatibility : const <LibretroSkinCompatibility>[];
      for (final verdict in refused) {
        if (verdict.console == widget.console) _verdicts[entry.key] = verdict;
      }
      _installing = null;
    });
  }

  /// Entries matching the search, source and favorites filters.
  List<LibretroCatalogSkin> get _matching => LibretroSkinCatalogs.search(_entries, _query)
      .where((entry) => _source == null || entry.source == _source)
      .where((entry) => !_favoritesOnly || _favorites.contains(entry.key))
      .toList();

  bool _hidden(LibretroCatalogSkin entry) => LibretroSkinCatalogs.hidden(_verdicts[entry.key], tablet: _tablet);

  bool _inOrientation(LibretroCatalogSkin entry) {
    final orientation = _orientation;
    if (orientation == null) return true;
    return _verdicts[entry.key]?.playableIn(orientation) ?? false;
  }

  @override
  Widget build(BuildContext context) {
    final matching = _matching;
    final shown = matching.where((entry) => !_hidden(entry) && _inOrientation(entry)).toList();
    final hidden = matching.where(_hidden).toList();
    final size = MediaQuery.sizeOf(context);
    // Phones in landscape: a lower bar, the filters folded, more skins.
    final compact = size.width > size.height && size.shortestSide < 600;
    final ready = !_loading && !_failed;
    final filtersOpen = ready && _filtersOpen(context);
    final appBar = libretroPageAppBar(context, _t('catalogTitle'));
    return libretroPage(Scaffold(
      appBar: compact
          ? AppBar(
              leading: appBar.leading,
              title: appBar.title,
              toolbarHeight: 44,
            )
          : appBar,
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 1180),
            child: Column(
              children: [
                _buildHeader(context, compact: compact, ready: ready, filtersOpen: filtersOpen),
                // Animated when the user folds or opens them, not when the
                // page appears.
                if (_filtersToggled)
                  AnimatedSize(
                    duration: const Duration(milliseconds: 180),
                    curve: Curves.easeOut,
                    alignment: Alignment.topCenter,
                    child: filtersOpen ? _buildFilters(context) : const SizedBox(width: double.infinity),
                  )
                else if (filtersOpen)
                  _buildFilters(context),
                if (ready) _buildStatus(context),
                Expanded(child: _buildBody(context, shown, hidden)),
              ],
            ),
          ),
        ),
      ),
    ));
  }

  /// Search, and the button folding the filters (with the number of active
  /// ones).
  Widget _buildHeader(BuildContext context, {required bool compact, required bool ready, required bool filtersOpen}) {
    final active = _activeFilters;
    return Padding(
      padding: EdgeInsets.fromLTRB(16, compact ? 6 : 12, 16, compact ? 4 : 8),
      child: Row(
        children: [
          Expanded(
            child: LibretroFocusRing(
              radius: 8,
              child: TextField(
                controller: _search,
                enabled: ready,
                textInputAction: TextInputAction.search,
                decoration: InputDecoration(
                  labelText: _t('catalogSearch'),
                  prefixIcon: const Icon(Icons.search),
                  border: const OutlineInputBorder(),
                  isDense: compact,
                ),
                onChanged: (value) => setState(() {
                  _query = value;
                  _view.query = value;
                }),
              ),
            ),
          ),
          const SizedBox(width: 8),
          LibretroFocusRing(
            child: Badge(
              isLabelVisible: active > 0 && !filtersOpen,
              label: Text(active.toString()),
              child: IconButton.filledTonal(
                key: const ValueKey('skin-catalog-filters'),
                tooltip: SkinBrowserLocale.text(context, SkinBrowserLocale.filters),
                isSelected: filtersOpen,
                onPressed: ready
                    ? () => setState(() {
                          _filtersToggled = true;
                          _view.filtersOpen = !filtersOpen;
                        })
                    : null,
                icon: const Icon(Icons.tune),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _chip(String label, bool selected, VoidCallback onSelected, {IconData? icon}) => LibretroFocusRing(
        radius: 8,
        child: FilterChip(
          avatar: icon == null ? null : Icon(icon, size: 18),
          label: Text(label),
          selected: selected,
          showCheckmark: icon == null,
          onSelected: (_) => onSelected(),
        ),
      );

  Widget _buildFilters(BuildContext context) {
    final theme = Theme.of(context);
    final sources = <String>[
      for (final source in LibretroSkinSources.all)
        if (_entries.any((entry) => entry.source == source)) source,
    ];
    void change(VoidCallback update) => setState(() {
          update();
          _rememberView();
        });
    return Padding(
      key: const ValueKey('skin-catalog-filter-panel'),
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              _chip(_t('catalogSourcesAll'), _source == null, () => change(() => _source = null)),
              for (final source in sources)
                _chip(LibretroSkinSources.label(source), _source == source, () => change(() => _source = source)),
            ],
          ),
          const SizedBox(height: 4),
          // The preview orientation, whatever the device's: the skins playable
          // in it, their verdict for it and thumbnails shaped like it.
          Wrap(
            spacing: 8,
            runSpacing: 4,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text(SkinBrowserLocale.text(context, SkinBrowserLocale.preview), style: theme.textTheme.labelLarge),
              _chip(_t('catalogOrientationAny'), _orientation == null, () => change(() => _orientation = null)),
              _chip(
                _t('orientationPortrait'),
                _orientation == LibretroSkinService.portrait,
                () => change(() => _orientation = LibretroSkinService.portrait),
                icon: Icons.stay_current_portrait,
              ),
              _chip(
                _t('orientationLandscape'),
                _orientation == LibretroSkinService.landscape,
                () => change(() => _orientation = LibretroSkinService.landscape),
                icon: Icons.stay_current_landscape,
              ),
              _chip(
                _t('catalogFavorites'),
                _favoritesOnly,
                () => change(() => _favoritesOnly = !_favoritesOnly),
                icon: _favoritesOnly ? Icons.star : Icons.star_border,
              ),
            ],
          ),
        ],
      ),
    );
  }

  /// Check progress and the sources that could not be read.
  Widget _buildStatus(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final total = _entries.length;
    final done = _entries.where((entry) => _verdicts.containsKey(entry.key)).length;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (_checking && total > 0) ...[
            LinearProgressIndicator(value: done / total),
            const SizedBox(height: 4),
            Text(_f('catalogChecking', {'done': done, 'total': total}), style: muted),
          ],
          if (_unavailable.isNotEmpty)
            Row(
              children: [
                Icon(Icons.cloud_off, size: 16, color: theme.colorScheme.error),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    _f('catalogSourceUnavailable', {'sources': _unavailable.map(LibretroSkinSources.label).join(', ')}),
                    style: muted,
                  ),
                ),
                LibretroFocusRing(
                  child: TextButton(onPressed: _retry, child: Text(_t('catalogRetry'))),
                ),
              ],
            ),
        ],
      ),
    );
  }

  Widget _buildBody(BuildContext context, List<LibretroCatalogSkin> shown, List<LibretroCatalogSkin> hidden) {
    final theme = Theme.of(context);
    if (_loading) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const CircularProgressIndicator(),
            const SizedBox(height: 12),
            Text(_t('catalogLoading')),
          ],
        ),
      );
    }
    if (_failed) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.cloud_off, size: 40, color: theme.colorScheme.error),
              const SizedBox(height: 12),
              Text(_t('catalogFailed'), textAlign: TextAlign.center),
              const SizedBox(height: 16),
              LibretroFocusRing(
                child: FilledButton.icon(
                  onPressed: _retry,
                  icon: const Icon(Icons.refresh),
                  label: Text(_t('catalogRetry')),
                ),
              ),
            ],
          ),
        ),
      );
    }
    return LayoutBuilder(
      builder: (context, constraints) {
        // One column on phones in portrait, up to three on wide screens.
        final columns = (constraints.maxWidth / 420).floor().clamp(1, 3);
        List<Widget> grid(List<LibretroCatalogSkin> entries, {bool excluded = false}) => <Widget>[
              for (var index = 0; index < entries.length; index += columns)
                Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    for (var column = 0; column < columns; column++) ...[
                      if (column > 0) const SizedBox(width: 10),
                      Expanded(
                        child: index + column < entries.length
                            ? _buildEntry(context, entries[index + column], excluded: excluded)
                            : const SizedBox.shrink(),
                      ),
                    ],
                  ],
                ),
            ];
        final rows = <Widget>[
          ...grid(shown),
          if (shown.isEmpty && !_checking)
            Padding(
              padding: const EdgeInsets.all(24),
              child: Text(_t('catalogEmpty'), textAlign: TextAlign.center),
            ),
          if (hidden.isNotEmpty) _buildHiddenHeader(context, hidden.length),
          if (_showHidden) ...grid(hidden, excluded: true),
        ];
        return Scrollbar(
          controller: _scroll,
          child: ListView.builder(
            key: const ValueKey('skin-catalog-list'),
            controller: _scroll,
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 16),
            itemCount: rows.length,
            itemBuilder: (context, index) => rows[index],
          ),
        );
      },
    );
  }

  Widget _buildHiddenHeader(BuildContext context, int count) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Icon(Icons.visibility_off_outlined, size: 18, color: theme.colorScheme.onSurfaceVariant),
          const SizedBox(width: 8),
          Expanded(child: Text(_f('catalogHidden', {'count': count}), style: theme.textTheme.bodySmall)),
          LibretroFocusRing(
            child: TextButton(
              onPressed: () => setState(() {
                _showHidden = !_showHidden;
                _view.showHidden = _showHidden;
              }),
              child: Text(_t(_showHidden ? 'catalogHideHidden' : 'catalogShowHidden')),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildEntry(BuildContext context, LibretroCatalogSkin entry, {bool excluded = false}) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final verdict = _verdicts[entry.key];
    final installing = _installing == entry.key;
    final installed = _installed.contains(entry.key);
    final downloads = entry.downloadCount;
    final favorite = _favorites.contains(entry.key);
    final origin = entry.origin;
    final sourceLabel = origin == null || origin == LibretroSkinSources.label(entry.source)
        ? LibretroSkinSources.label(entry.source)
        : '${LibretroSkinSources.label(entry.source)} · $origin';

    Widget? button;
    if (excluded) {
      button = null;
    } else if (installing) {
      button = FilledButton.tonal(
        onPressed: null,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2)),
            const SizedBox(width: 8),
            Flexible(child: Text(_t('catalogInstalling'))),
          ],
        ),
      );
    } else {
      button = LibretroFocusRing(
        child: FilledButton.tonalIcon(
          onPressed: _installing == null ? () => _install(entry) : null,
          icon: Icon(installed ? Icons.check : Icons.download),
          label: Text(_t('catalogInstall')),
        ),
      );
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Tooltip(
              message: SkinBrowserLocale.text(context, SkinBrowserLocale.showDetails),
              child: InkWell(
                canRequestFocus: false,
                borderRadius: BorderRadius.circular(10),
                onTap: () => _showDetails(entry),
                child: _Thumbnail(url: _thumbnail(entry), size: _thumbnailSize),
              ),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Expanded(child: Text(entry.name, style: theme.textTheme.titleMedium)),
                      LibretroFocusRing(
                        child: IconButton(
                          tooltip: _t(favorite ? 'catalogFavoriteRemove' : 'catalogFavoriteAdd'),
                          icon: Icon(favorite ? Icons.star : Icons.star_border),
                          onPressed: () => unawaited(_toggleFavorite(entry)),
                        ),
                      ),
                    ],
                  ),
                  Text(entry.author ?? _t('skinsAuthorUnknown'), style: muted),
                  Text(_f('catalogSource', {'source': sourceLabel}), style: muted),
                  if (downloads != null) Text(_f('catalogDownloads', {'count': downloads}), style: muted),
                  if (entry.license != null) Text(_f('skinsLicense', {'license': entry.license}), style: muted),
                  if (entry.overlay != null) Text(_t('catalogConverted'), style: muted),
                  if (verdict != null) ...libretroSkinVerdictRows(context, verdict),
                  if (button != null) ...[
                    const SizedBox(height: 8),
                    button,
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Shaped like the preview orientation: tall for portrait, wide for
  /// landscape, square for both.
  Size get _thumbnailSize => switch (_orientation) {
        LibretroSkinService.portrait => const Size(72, 128),
        LibretroSkinService.landscape => const Size(150, 84),
        _ => const Size(100, 100),
      };

  /// The skin's image as large as the screen allows, with its details.
  Future<void> _showDetails(LibretroCatalogSkin entry) {
    final verdict = _verdicts[entry.key];
    return showDialog<void>(
      context: context,
      builder: (dialogContext) {
        final size = MediaQuery.sizeOf(dialogContext);
        final theme = Theme.of(dialogContext);
        final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
        return AlertDialog(
          key: const ValueKey('skin-catalog-details'),
          title: Text(entry.name),
          content: SizedBox(
            width: (size.width * 0.8).clamp(240.0, 720.0).toDouble(),
            child: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Center(
                    child: _Thumbnail(
                      url: _thumbnail(entry),
                      size: Size(
                        (size.width * 0.7).clamp(200.0, 680.0).toDouble(),
                        (size.height * 0.45).clamp(160.0, 520.0).toDouble(),
                      ),
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(entry.author ?? _t('skinsAuthorUnknown'), style: muted),
                  if (entry.license != null) Text(_f('skinsLicense', {'license': entry.license}), style: muted),
                  if (verdict != null) ...libretroSkinVerdictRows(dialogContext, verdict),
                ],
              ),
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(SkinBrowserLocale.text(dialogContext, SkinBrowserLocale.close)),
            ),
          ],
        );
      },
    );
  }

  /// The catalog's thumbnail, or for an overlay its first image (the
  /// background of its first page in most overlays).
  static String? _thumbnail(LibretroCatalogSkin entry) {
    final overlay = entry.overlay;
    if (entry.thumbnailURL != null || overlay == null || overlay.files.isEmpty) return entry.thumbnailURL;
    return overlay.fileUri(overlay.files.first).toString();
  }
}

/// Catalog thumbnail: only https images, a neutral placeholder otherwise or
/// when the image cannot be loaded. The whole image is shown (a skin is a
/// tall or a wide drawing: cropping it would hide its buttons), decoded at
/// the size it is drawn and faded in once loaded.
class _Thumbnail extends StatelessWidget {
  const _Thumbnail({required this.url, required this.size});

  final String? url;
  final Size size;

  Uri? get _uri {
    final raw = url;
    if (raw == null) return null;
    final uri = Uri.tryParse(raw.trim().replaceAll(' ', '%20').replaceAll('#', '%23'));
    return uri != null && uri.scheme == 'https' && uri.host.isNotEmpty ? uri : null;
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final placeholder = Center(child: Icon(Icons.image_outlined, color: scheme.onSurfaceVariant));
    final uri = _uri;
    final ratio = MediaQuery.devicePixelRatioOf(context);
    return Container(
      width: size.width,
      height: size.height,
      decoration: BoxDecoration(
        color: scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(10),
      ),
      clipBehavior: Clip.antiAlias,
      child: uri == null
          ? placeholder
          : Image.network(
              uri.toString(),
              fit: BoxFit.contain,
              // Decoded no larger than drawn: the longest side bounds both.
              cacheWidth: (size.longestSide * ratio).round(),
              frameBuilder: (context, child, frame, synchronous) => synchronous
                  ? child
                  : Stack(
                      fit: StackFit.expand,
                      children: [
                        if (frame == null) placeholder,
                        AnimatedOpacity(
                          opacity: frame == null ? 0 : 1,
                          duration: const Duration(milliseconds: 180),
                          child: child,
                        ),
                      ],
                    ),
              errorBuilder: (context, error, stackTrace) => placeholder,
            ),
    );
  }
}
