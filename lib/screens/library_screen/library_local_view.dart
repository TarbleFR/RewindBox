import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:flutter/foundation.dart' show ValueListenable;
import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import 'package:neostation/l10n/library_local_locale.dart';
import 'package:neostation/services/library_local_library_service.dart';
import 'package:neostation/services/library_local_models.dart';
import 'package:neostation/services/library_reading_store.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';
import 'package:neostation/widgets/neo_glass.dart';

import 'library_gamepad_view_controller.dart';
import 'library_reader_launcher.dart';
import 'library_sources_view.dart'
    show LibraryFocusSectionDelegate, LibraryTechnicalDetails;

/// Opens an imported book (default: [LibraryReaderLauncher.openLocalBook]).
typedef LibraryLocalBookOpener =
    Future<void> Function(BuildContext context, LibraryLocalBook book);

/// Translation key of an import or open problem.
String libraryBookIssueKey(LibraryBookIssue issue) => switch (issue) {
  LibraryBookIssue.unsupportedFormat => 'issueUnsupportedFormat',
  LibraryBookIssue.rarArchive => 'issueRarArchive',
  LibraryBookIssue.sevenZipArchive => 'issueSevenZipArchive',
  LibraryBookIssue.kindleFormat => 'issueKindleFormat',
  LibraryBookIssue.folder => 'issueFolder',
  LibraryBookIssue.emptyFile => 'issueEmptyFile',
  LibraryBookIssue.drmProtected => 'issueDrmProtected',
  LibraryBookIssue.passwordProtected => 'issuePasswordProtected',
  LibraryBookIssue.encryptedArchive => 'issueEncryptedArchive',
  LibraryBookIssue.unsupportedCompression => 'issueUnsupportedCompression',
  LibraryBookIssue.corrupt => 'issueCorrupt',
  LibraryBookIssue.noContent => 'issueNoContent',
  LibraryBookIssue.tooLarge => 'issueTooLarge',
  LibraryBookIssue.duplicate => 'issueDuplicate',
  LibraryBookIssue.duplicateInSelection => 'issueDuplicateInSelection',
  LibraryBookIssue.sameNameInSelection => 'issueSameNameInSelection',
  LibraryBookIssue.unreadable => 'issueUnreadable',
  LibraryBookIssue.storageFailed => 'issueStorageFailed',
};

/// Translated outcome of one imported file.
String libraryImportOutcomeText(
  BuildContext context,
  LibraryImportOutcome outcome,
) {
  if (outcome.imported) {
    return LibraryLocalLocale.text(context, 'outcomeImported');
  }
  final issue = outcome.issue ?? LibraryBookIssue.unreadable;
  final duplicate = outcome.duplicateOf;
  if (issue == LibraryBookIssue.duplicate && duplicate != null) {
    return LibraryLocalLocale.format(context, 'outcomeDuplicateOf', {
      'title': duplicate.title,
    });
  }
  return LibraryLocalLocale.text(context, libraryBookIssueKey(issue));
}

String _formatName(LibraryBookFormat format) => switch (format) {
  LibraryBookFormat.epub => 'EPUB',
  LibraryBookFormat.pdf => 'PDF',
  LibraryBookFormat.cbz => 'CBZ',
  LibraryBookFormat.txt => 'TXT',
};

String _sortKey(LibraryBookSort sort) => switch (sort) {
  LibraryBookSort.title => 'sortTitle',
  LibraryBookSort.author => 'sortAuthor',
  LibraryBookSort.added => 'sortAdded',
  LibraryBookSort.lastRead => 'sortLastRead',
  LibraryBookSort.format => 'sortFormat',
  LibraryBookSort.size => 'sortSize',
};

String _sizeText(BuildContext context, int bytes) {
  if (bytes < 1024 * 1024) {
    return LibraryLocalLocale.format(context, 'sizeKb', {
      'size': math.max(1, (bytes / 1024).ceil()),
    });
  }
  return LibraryLocalLocale.format(context, 'sizeMb', {
    'size': (bytes / (1024 * 1024)).toStringAsFixed(1),
  });
}

/// Minimum touch target (Apple HIG: 44 pt), whatever the .r scale.
double _tap(double value) => math.max(44.0, value);

/// Local library section (Build 437): works without any account or
/// catalogue. Import from Files with progress and a per-file result sheet,
/// accent-insensitive search, sort, format filters, rescan, a grid of books
/// with covers and reading progress, and per-book actions (open, rename the
/// displayed title, delete NeoStation's copy, information).
class LibraryLocalView extends StatefulWidget {
  const LibraryLocalView({
    super.key,
    required this.controller,
    required this.onBack,
    this.service,
    this.readingStore,
    this.bookOpener,
    this.enableGamepad = true,
  });

  final LibraryGamepadViewController controller;

  /// Returns to the Library hub.
  final VoidCallback onBack;

  /// Defaults to [LibraryLocalLibraryService.instance].
  final LibraryLocalLibraryService? service;

  /// Defaults to [LibraryReadingStore.instance].
  final LibraryReadingStore? readingStore;

  /// Defaults to [LibraryReaderLauncher.openLocalBook].
  final LibraryLocalBookOpener? bookOpener;

  /// Dialogs register their own controller layer; false in widget tests
  /// that do not stub the gamepad plugin.
  final bool enableGamepad;

  @override
  State<LibraryLocalView> createState() => _LibraryLocalViewState();
}

class _LibraryLocalViewState extends State<LibraryLocalView> {
  /// Sort and order, remembered while the app runs.
  static LibraryBookSort _sessionSort = LibraryBookSort.title;
  static bool _sessionAscending = true;

  final FocusScopeNode _scope = FocusScopeNode(debugLabel: 'LibraryLocalView');
  late final LibraryFocusSectionDelegate _delegate =
      LibraryFocusSectionDelegate(_scope, onSecondary: _secondary);
  final TextEditingController _search = TextEditingController();
  final ScrollController _scroll = ScrollController();
  Timer? _searchDebounce;

  String _query = '';
  LibraryBookSort _sort = _sessionSort;
  bool _ascending = _sessionAscending;
  final Set<LibraryBookFormat> _formats = <LibraryBookFormat>{};
  List<LibraryLocalBook> _visible = const <LibraryLocalBook>[];
  Object? _loadError;
  bool _importing = false;
  bool _recoveredNoticeDismissed = false;
  String? _focusedBookId;
  int _progressSignature = 0;

  LibraryLocalLibraryService get _service =>
      widget.service ?? LibraryLocalLibraryService.instance;
  LibraryReadingStore get _store =>
      widget.readingStore ?? LibraryReadingStore.instance;

  String _t(String key) => LibraryLocalLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      LibraryLocalLocale.format(context, key, values);

  @override
  void initState() {
    super.initState();
    widget.controller.attach(_delegate);
    _service.addListener(_onServiceChanged);
    _store.addListener(_onStoreChanged);
    _requery();
    unawaited(_load());
    unawaited(
      _store.load().then((_) => _onStoreChanged(), onError: (Object _) {}),
    );
  }

  @override
  void didUpdateWidget(covariant LibraryLocalView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.controller, widget.controller)) {
      oldWidget.controller.detach(_delegate);
      widget.controller.attach(_delegate);
    }
  }

  @override
  void dispose() {
    widget.controller.detach(_delegate);
    // Leaving the section gives the focus highlight back to touch mode.
    scheduleMicrotask(LibraryFocusNavigation.restoreTouchHighlight);
    _service.removeListener(_onServiceChanged);
    _store.removeListener(_onStoreChanged);
    _searchDebounce?.cancel();
    _search.dispose();
    _scroll.dispose();
    _scope.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      await _service.load();
      if (!mounted) return;
      setState(() {
        _loadError = null;
        _requery();
      });
    } on Object catch (error) {
      if (!mounted) return;
      setState(() => _loadError = error);
    }
  }

  void _onServiceChanged() {
    if (!mounted) return;
    setState(_requery);
  }

  int _computeProgressSignature() {
    var hash = 0;
    for (final book in _service.books) {
      final progress = _store.progressFor(book.readingKey);
      if (progress == null) continue;
      hash = Object.hash(
        hash,
        book.id,
        progress.fraction,
        progress.updatedAt.millisecondsSinceEpoch,
      );
    }
    return hash;
  }

  /// Rebuilds only when the progress of a local book changed (the store
  /// notifies on every page turn of any reader).
  void _onStoreChanged() {
    if (!mounted) return;
    final signature = _computeProgressSignature();
    if (signature == _progressSignature) return;
    setState(() {
      _progressSignature = signature;
      if (_sort == LibraryBookSort.lastRead) _requery();
    });
  }

  void _requery() {
    _progressSignature = _computeProgressSignature();
    _visible = _service.query(
      search: _query,
      sort: _sort,
      ascending: _ascending,
      formats: _formats,
      lastRead: (book) =>
          _store.progressFor(book.readingKey)?.updatedAt.millisecondsSinceEpoch,
    );
  }

  void _onSearchChanged(String value) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 250), () {
      if (!mounted || value == _query) return;
      setState(() {
        _query = value;
        _requery();
      });
    });
  }

  void _clearSearch() {
    _searchDebounce?.cancel();
    _search.clear();
    setState(() {
      _query = '';
      _requery();
    });
  }

  void _toggleFormat(LibraryBookFormat format) {
    setState(() {
      if (!_formats.remove(format)) _formats.add(format);
      _requery();
    });
  }

  bool _secondary() {
    final id = _focusedBookId;
    final book = id == null ? null : _service.bookById(id);
    if (book == null) return false;
    unawaited(_showBookMenu(book));
    return true;
  }

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 3)),
      );
  }

  // ------------------------------------------------------------ import --

  Future<void> _import() async {
    if (_importing) return;
    setState(() => _importing = true);
    final progress = ValueNotifier<LibraryImportProgress?>(null);
    final navigator = Navigator.of(context);
    var overlayShown = false;
    var overlayOpen = false;
    void showOverlay() {
      if (overlayShown || !mounted) return;
      overlayShown = true;
      overlayOpen = true;
      unawaited(
        showDialog<void>(
          context: context,
          barrierDismissible: false,
          builder: (_) => PopScope(
            canPop: false,
            // Holds the controller while the import runs (it cannot be
            // cancelled): nothing behind the overlay can be activated.
            child: LibraryFocusGamepadLayer(
              enableGamepad: widget.enableGamepad,
              debugLabel: 'local_import_progress',
              onBack: () {},
              child: _ImportProgressDialog(progress: progress),
            ),
          ),
        ).whenComplete(() => overlayOpen = false),
      );
    }

    List<LibraryImportOutcome>? outcomes;
    Object? failure;
    try {
      outcomes = await _service.pickAndImport(
        onProgress: (value) {
          progress.value = value;
          showOverlay();
        },
      );
    } on Object catch (error) {
      failure = error;
    } finally {
      if (overlayOpen && navigator.mounted) navigator.pop();
      progress.dispose();
      if (mounted) setState(() => _importing = false);
    }
    if (!mounted) return;
    if (failure != null) {
      await _showMessage(_t('importFailed'), detail: failure.toString());
      return;
    }
    final results = outcomes;
    if (results == null || results.isEmpty) return;
    await showDialog<void>(
      context: context,
      builder: (_) => LibraryImportResultsDialog(
        outcomes: results,
        enableGamepad: widget.enableGamepad,
      ),
    );
  }

  Future<void> _rescan() async {
    try {
      await _service.rescan();
    } on Object catch (error) {
      if (mounted) {
        await _showMessage(_t('loadFailed'), detail: error.toString());
      }
    }
  }

  // ------------------------------------------------------------- books --

  Future<void> _open(LibraryLocalBook book) async {
    final opener = widget.bookOpener ?? LibraryReaderLauncher.openLocalBook;
    try {
      await opener(context, book);
    } on Object catch (error) {
      if (!mounted) return;
      final issue = error is LibraryBookException ? error.issue : null;
      await _showMessage(
        issue == null ? _t('openFailed') : _t(libraryBookIssueKey(issue)),
        detail: error.toString(),
      );
    }
  }

  Future<void> _showMessage(String message, {String? detail}) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) => LibraryFocusGamepadLayer(
        enableGamepad: widget.enableGamepad,
        debugLabel: 'local_message',
        child: AlertDialog(
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(message),
              if (detail != null) LibraryTechnicalDetails(detail: detail),
            ],
          ),
          actions: <Widget>[
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(LibraryLocalLocale.text(dialogContext, 'close')),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showBookMenu(LibraryLocalBook book) async {
    final action = await showDialog<_BookAction>(
      context: context,
      builder: (dialogContext) {
        String t(String key) => LibraryLocalLocale.text(dialogContext, key);
        Widget option(_BookAction value, IconData icon, String label) =>
            ListTile(
              key: ValueKey<String>('book-action-${value.name}'),
              leading: Icon(icon),
              title: Text(label),
              onTap: () => Navigator.of(dialogContext).pop(value),
            );
        return LibraryFocusGamepadLayer(
          enableGamepad: widget.enableGamepad,
          debugLabel: 'local_book_menu',
          child: SimpleDialog(
            title: Text(
              book.title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
            children: <Widget>[
              option(_BookAction.open, Icons.menu_book, t('open')),
              option(_BookAction.rename, Icons.edit, t('rename')),
              option(_BookAction.delete, Icons.delete_outline, t('deleteCopy')),
              option(_BookAction.info, Icons.info_outline, t('info')),
            ],
          ),
        );
      },
    );
    if (!mounted || action == null) return;
    switch (action) {
      case _BookAction.open:
        await _open(book);
      case _BookAction.rename:
        await _rename(book);
      case _BookAction.delete:
        await _delete(book);
      case _BookAction.info:
        await _info(book);
    }
  }

  Future<void> _rename(LibraryLocalBook book) async {
    final title = await showDialog<String>(
      context: context,
      builder: (_) => _RenameDialog(
        initial: book.customTitle ?? book.title,
        enableGamepad: widget.enableGamepad,
      ),
    );
    if (!mounted || title == null) return;
    final updated = await _service.rename(book.id, title);
    if (!mounted) return;
    if (updated != null) _snack(_t('renamed'));
  }

  Future<void> _delete(LibraryLocalBook book) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => LibraryFocusGamepadLayer(
        enableGamepad: widget.enableGamepad,
        debugLabel: 'local_delete',
        child: AlertDialog(
          title: Text(
            LibraryLocalLocale.format(dialogContext, 'deleteTitle', {
              'title': book.title,
            }),
          ),
          content: Text(
            LibraryLocalLocale.text(
              dialogContext,
              book.folder == LibraryBookFolder.downloads
                  ? 'deleteBodyDownload'
                  : 'deleteBody',
            ),
            key: const ValueKey<String>('delete-body'),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: Text(LibraryLocalLocale.text(dialogContext, 'cancel')),
            ),
            FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: Theme.of(dialogContext).colorScheme.error,
                foregroundColor: Theme.of(dialogContext).colorScheme.onError,
              ),
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: Text(LibraryLocalLocale.text(dialogContext, 'delete')),
            ),
          ],
        ),
      ),
    );
    if (!mounted || confirmed != true) return;
    final result = await _service.delete(book.id);
    if (!mounted) return;
    switch (result) {
      case LibraryDeleteResult.deleted:
        _snack(_f('deleted', <String, Object?>{'title': book.title}));
      case LibraryDeleteResult.failed:
        _snack(_t('deleteFailed'));
      case LibraryDeleteResult.refused:
        _snack(_t('deleteRefused'));
      case LibraryDeleteResult.notFound:
        unawaited(_rescan());
    }
  }

  Future<void> _info(LibraryLocalBook book) {
    return showDialog<void>(
      context: context,
      builder: (dialogContext) {
        String t(String key) => LibraryLocalLocale.text(dialogContext, key);
        final unknown = t('unknown');
        final rows = <(String, String)>[
          (t('infoFormat'), _formatName(book.format)),
          (t('infoSize'), _sizeText(dialogContext, book.sizeBytes)),
          (
            t('infoAdded'),
            MaterialLocalizations.of(dialogContext).formatShortDate(
              DateTime.fromMillisecondsSinceEpoch(book.addedAtMs),
            ),
          ),
          (
            t('infoLocation'),
            t(
              book.folder == LibraryBookFolder.downloads
                  ? 'locationDownloads'
                  : 'locationBooks',
            ),
          ),
          (t('infoFile'), book.fileName),
          (
            t('infoAuthors'),
            book.authors.isEmpty ? unknown : book.authors.join(', '),
          ),
          if (book.series != null)
            (
              t('infoSeries'),
              book.seriesNumber == null
                  ? book.series!
                  : '${book.series!} ${book.seriesNumber}',
            ),
          (t('infoLanguage'), book.language ?? unknown),
          (t('infoPages'), book.pageCount?.toString() ?? unknown),
        ];
        return LibraryFocusGamepadLayer(
          enableGamepad: widget.enableGamepad,
          debugLabel: 'local_info',
          child: AlertDialog(
            title: Text(book.title),
            content: SizedBox(
              width: 520,
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: <Widget>[
                    for (final (label, value) in rows)
                      Padding(
                        padding: const EdgeInsets.symmetric(vertical: 3),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            SizedBox(
                              width: 140,
                              child: Text(
                                label,
                                style: Theme.of(dialogContext)
                                    .textTheme
                                    .bodySmall
                                    ?.copyWith(fontWeight: FontWeight.w700),
                              ),
                            ),
                            Expanded(child: SelectableText(value)),
                          ],
                        ),
                      ),
                  ],
                ),
              ),
            ),
            actions: <Widget>[
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(),
                child: Text(t('close')),
              ),
            ],
          ),
        );
      },
    );
  }

  Future<void> _chooseSort() async {
    final choice = await showDialog<(LibraryBookSort, bool)>(
      context: context,
      builder: (_) => _SortDialog(
        sort: _sort,
        ascending: _ascending,
        enableGamepad: widget.enableGamepad,
      ),
    );
    if (!mounted || choice == null) return;
    setState(() {
      _sort = _sessionSort = choice.$1;
      _ascending = _sessionAscending = choice.$2;
      _requery();
    });
  }

  // ------------------------------------------------------------- build --

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return FocusScope(
      node: _scope,
      child: FocusTraversalGroup(
        policy: ReadingOrderTraversalPolicy(),
        child: Listener(
          behavior: HitTestBehavior.translucent,
          onPointerDown: (_) => LibraryFocusNavigation.restoreTouchHighlight(),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              _buildHeader(theme),
              SizedBox(height: 10.r),
              _buildToolbar(theme),
              SizedBox(height: 8.r),
              _buildFilters(theme),
              if (_service.indexRecovered && !_recoveredNoticeDismissed)
                _buildRecoveredNotice(theme),
              SizedBox(height: 8.r),
              Expanded(child: _buildBody(theme)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(ThemeData theme) {
    return Row(
      children: <Widget>[
        Icon(
          Symbols.folder_open_rounded,
          size: 36.r,
          color: theme.colorScheme.primary,
        ),
        SizedBox(width: 12.r),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text(
                _t('title'),
                style: theme.textTheme.titleLarge?.copyWith(
                  fontWeight: FontWeight.w800,
                ),
              ),
              SizedBox(height: 2.r),
              Text(
                _t('intro'),
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.68),
                ),
              ),
            ],
          ),
        ),
        SizedBox(width: 8.r),
        FilledButton.tonalIcon(
          onPressed: widget.onBack,
          icon: const Icon(Symbols.arrow_back_rounded),
          label: Text(_t('back')),
        ),
      ],
    );
  }

  Widget _buildToolbar(ThemeData theme) {
    return Row(
      children: <Widget>[
        FilledButton.icon(
          key: const ValueKey<String>('import-button'),
          onPressed: _importing ? null : _import,
          icon: const Icon(Symbols.file_upload_rounded),
          label: Text(_t('importFiles')),
        ),
        SizedBox(width: 10.r),
        Expanded(
          child: TextField(
            key: const ValueKey<String>('local-search'),
            controller: _search,
            onChanged: _onSearchChanged,
            textInputAction: TextInputAction.search,
            decoration: InputDecoration(
              isDense: true,
              hintText: _t('searchHint'),
              prefixIcon: const Icon(Icons.search),
              suffixIcon: _search.text.isEmpty
                  ? null
                  : IconButton(
                      tooltip: _t('clearSearch'),
                      onPressed: _clearSearch,
                      icon: const Icon(Icons.clear),
                    ),
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(12.r),
              ),
            ),
          ),
        ),
        SizedBox(width: 8.r),
        OutlinedButton.icon(
          key: const ValueKey<String>('sort-button'),
          onPressed: _chooseSort,
          icon: Icon(_ascending ? Icons.arrow_upward : Icons.arrow_downward),
          label: Text(_t(_sortKey(_sort))),
        ),
        SizedBox(width: 4.r),
        IconButton(
          tooltip: _t('rescan'),
          constraints: BoxConstraints(
            minWidth: _tap(40.r),
            minHeight: _tap(40.r),
          ),
          onPressed: _service.scanning ? null : _rescan,
          icon: _service.scanning
              ? const SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.refresh),
        ),
      ],
    );
  }

  Widget _buildFilters(ThemeData theme) {
    return Row(
      children: <Widget>[
        Expanded(
          child: Semantics(
            label: _t('formatsFilter'),
            container: true,
            child: Wrap(
              spacing: 6.r,
              runSpacing: 4.r,
              children: <Widget>[
                for (final format in LibraryBookFormat.values)
                  FilterChip(
                    key: ValueKey<String>('format-${format.name}'),
                    label: Text(_formatName(format)),
                    selected: _formats.contains(format),
                    onSelected: (_) => _toggleFormat(format),
                  ),
              ],
            ),
          ),
        ),
        if (_service.scanning)
          Padding(
            padding: EdgeInsets.only(right: 8.r),
            child: Text(_t('scanning'), style: theme.textTheme.bodySmall),
          ),
        Text(
          _f('bookCount', <String, Object?>{'count': _visible.length}),
          style: theme.textTheme.bodySmall,
        ),
      ],
    );
  }

  Widget _buildRecoveredNotice(ThemeData theme) {
    return Padding(
      padding: EdgeInsets.only(top: 8.r),
      child: Material(
        color: theme.colorScheme.tertiaryContainer,
        borderRadius: BorderRadius.circular(10.r),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 4.r),
          child: Row(
            children: <Widget>[
              Expanded(child: Text(_t('indexRecovered'))),
              IconButton(
                tooltip: _t('close'),
                onPressed: () =>
                    setState(() => _recoveredNoticeDismissed = true),
                icon: const Icon(Icons.close),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildBody(ThemeData theme) {
    final error = _loadError;
    if (error != null) {
      return Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Text(_t('loadFailed')),
            LibraryTechnicalDetails(detail: error.toString()),
            FilledButton.tonal(
              onPressed: () {
                setState(() => _loadError = null);
                unawaited(_load());
              },
              child: Text(_t('rescan')),
            ),
          ],
        ),
      );
    }
    if (!_service.loaded && _service.books.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }
    if (_service.books.isEmpty) return _buildEmpty(theme);
    if (_visible.isEmpty) {
      return Center(
        child: Text(
          _t('noMatch'),
          key: const ValueKey<String>('no-match'),
          style: theme.textTheme.bodyMedium,
        ),
      );
    }
    final dpr = MediaQuery.devicePixelRatioOf(context);
    final tileWidth = 128.r;
    return GridView.builder(
      controller: _scroll,
      padding: EdgeInsets.only(bottom: 24.r),
      gridDelegate: SliverGridDelegateWithMaxCrossAxisExtent(
        maxCrossAxisExtent: tileWidth,
        mainAxisSpacing: 10.r,
        crossAxisSpacing: 10.r,
        childAspectRatio: 0.52,
      ),
      itemCount: _visible.length,
      itemBuilder: (context, index) {
        final book = _visible[index];
        return _BookTile(
          key: ValueKey<String>('book-${book.id}'),
          book: book,
          coverPath: book.hasCover ? _coverPath(book) : null,
          cacheWidth: (tileWidth * dpr).round(),
          progress: _store.progressFor(book.readingKey),
          onOpen: () => _open(book),
          onMenu: () => _showBookMenu(book),
          onFocusChange: (focused) {
            if (focused) {
              _focusedBookId = book.id;
            } else if (_focusedBookId == book.id) {
              _focusedBookId = null;
            }
          },
        );
      },
    );
  }

  String? _coverPath(LibraryLocalBook book) {
    try {
      return _service.coverPath(book);
    } on StateError {
      return null;
    }
  }

  Widget _buildEmpty(ThemeData theme) {
    return Center(
      child: SingleChildScrollView(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: 620.r),
          child: NeoGlass(
            role: GlassSurfaceRole.card,
            borderRadius: BorderRadius.circular(16.r),
            enableBackdropBlur: false,
            padding: EdgeInsets.all(20.r),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Icon(
                  Symbols.auto_stories_rounded,
                  size: 44.r,
                  color: theme.colorScheme.primary,
                ),
                SizedBox(height: 10.r),
                Text(
                  _t('emptyTitle'),
                  style: theme.textTheme.titleLarge?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                SizedBox(height: 6.r),
                Text(
                  _t('emptyBody'),
                  key: const ValueKey<String>('empty-body'),
                  textAlign: TextAlign.center,
                  style: theme.textTheme.bodyMedium,
                ),
                SizedBox(height: 14.r),
                FilledButton.icon(
                  onPressed: _importing ? null : _import,
                  icon: const Icon(Symbols.file_upload_rounded),
                  label: Text(_t('importFiles')),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

enum _BookAction { open, rename, delete, info }

class _BookTile extends StatelessWidget {
  const _BookTile({
    super.key,
    required this.book,
    required this.coverPath,
    required this.cacheWidth,
    required this.progress,
    required this.onOpen,
    required this.onMenu,
    required this.onFocusChange,
  });

  final LibraryLocalBook book;
  final String? coverPath;
  final int cacheWidth;
  final LibraryReadingProgress? progress;
  final VoidCallback onOpen;
  final VoidCallback onMenu;
  final ValueChanged<bool> onFocusChange;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final fraction = progress?.fraction ?? 0;
    final finished = progress?.isFinished ?? false;
    final progressLabel = progress == null
        ? LibraryLocalLocale.text(context, 'notStarted')
        : finished
        ? LibraryLocalLocale.text(context, 'finished')
        : LibraryLocalLocale.format(context, 'progressPercent', {
            'percent': (fraction * 100).round(),
          });
    final cover = coverPath;
    return LibraryFocusRing(
      radius: 10,
      onFocusChange: onFocusChange,
      child: Semantics(
        button: true,
        label: '${book.title}, $progressLabel',
        child: InkWell(
          borderRadius: BorderRadius.circular(10),
          onTap: onOpen,
          onLongPress: onMenu,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Expanded(
                child: Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    ClipRRect(
                      borderRadius: BorderRadius.circular(8),
                      child: cover == null
                          ? _FormatPlaceholder(format: book.format)
                          : Image(
                              image: ResizeImage(
                                FileImage(File(cover)),
                                width: cacheWidth,
                                policy: ResizeImagePolicy.fit,
                              ),
                              fit: BoxFit.cover,
                              gaplessPlayback: true,
                              errorBuilder: (_, _, _) =>
                                  _FormatPlaceholder(format: book.format),
                            ),
                    ),
                    Positioned(
                      left: 4,
                      top: 4,
                      child: _Badge(text: _formatName(book.format)),
                    ),
                    Positioned(
                      right: 0,
                      top: 0,
                      child: ExcludeFocus(
                        child: IconButton(
                          tooltip: LibraryLocalLocale.format(
                            context,
                            'moreActions',
                            {'title': book.title},
                          ),
                          constraints: const BoxConstraints(
                            minWidth: 44,
                            minHeight: 44,
                          ),
                          padding: EdgeInsets.zero,
                          onPressed: onMenu,
                          icon: DecoratedBox(
                            decoration: BoxDecoration(
                              color: Colors.black.withValues(alpha: 0.45),
                              shape: BoxShape.circle,
                            ),
                            child: const Padding(
                              padding: EdgeInsets.all(3),
                              child: Icon(
                                Icons.more_horiz,
                                size: 18,
                                color: Colors.white,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (progress != null)
                Padding(
                  padding: const EdgeInsets.only(top: 4),
                  child: LinearProgressIndicator(
                    value: fraction,
                    minHeight: 3,
                    borderRadius: BorderRadius.circular(2),
                  ),
                ),
              const SizedBox(height: 4),
              Text(
                book.title,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
                style: theme.textTheme.bodySmall?.copyWith(
                  fontWeight: FontWeight.w700,
                ),
              ),
              if (book.authors.isNotEmpty)
                Text(
                  book.authors.first,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.labelSmall?.copyWith(
                    color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: Colors.black.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
        child: Text(
          text,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 10,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }
}

class _FormatPlaceholder extends StatelessWidget {
  const _FormatPlaceholder({required this.format});

  final LibraryBookFormat format;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final icon = switch (format) {
      LibraryBookFormat.epub => Icons.menu_book,
      LibraryBookFormat.pdf => Icons.picture_as_pdf,
      LibraryBookFormat.cbz => Icons.collections,
      LibraryBookFormat.txt => Icons.description,
    };
    return ColoredBox(
      color: scheme.primary.withValues(alpha: 0.14),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            Icon(icon, size: 32, color: scheme.primary),
            const SizedBox(height: 4),
            Text(
              _formatName(format),
              style: TextStyle(
                color: scheme.primary,
                fontWeight: FontWeight.w800,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ImportProgressDialog extends StatelessWidget {
  const _ImportProgressDialog({required this.progress});

  final ValueListenable<LibraryImportProgress?> progress;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: Text(LibraryLocalLocale.text(context, 'importing')),
      content: SizedBox(
        width: 480,
        child: ValueListenableBuilder<LibraryImportProgress?>(
          valueListenable: progress,
          builder: (context, value, _) {
            if (value == null) return const LinearProgressIndicator();
            final stage = LibraryLocalLocale.text(
              context,
              switch (value.stage) {
                LibraryImportStage.inspecting => 'stageInspecting',
                LibraryImportStage.storing => 'stageStoring',
                LibraryImportStage.finished => 'stageFinished',
              },
            );
            return Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                LinearProgressIndicator(value: value.fraction),
                const SizedBox(height: 10),
                Text(
                  LibraryLocalLocale.format(context, 'importProgress', {
                    'index': value.index + 1,
                    'total': value.total,
                    'name': value.sourceName,
                    'stage': stage,
                  }),
                  key: const ValueKey<String>('import-progress'),
                  maxLines: 3,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            );
          },
        ),
      ),
    );
  }
}

/// One line per selected file with its translated outcome.
class LibraryImportResultsDialog extends StatelessWidget {
  const LibraryImportResultsDialog({
    super.key,
    required this.outcomes,
    this.enableGamepad = true,
  });

  final List<LibraryImportOutcome> outcomes;
  final bool enableGamepad;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final imported = outcomes.where((outcome) => outcome.imported).length;
    return LibraryFocusGamepadLayer(
      enableGamepad: enableGamepad,
      debugLabel: 'local_import_results',
      child: AlertDialog(
        title: Text(LibraryLocalLocale.text(context, 'resultsTitle')),
        content: SizedBox(
          width: 560,
          height: math.min(
            MediaQuery.sizeOf(context).height * 0.6,
            90.0 + outcomes.length * 72,
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              Text(
                LibraryLocalLocale.format(context, 'resultsSummary', {
                  'imported': imported,
                  'refused': outcomes.length - imported,
                }),
                key: const ValueKey<String>('import-summary'),
                style: theme.textTheme.titleSmall,
              ),
              const SizedBox(height: 8),
              Expanded(
                child: ListView.builder(
                  itemCount: outcomes.length,
                  itemBuilder: (context, index) {
                    final outcome = outcomes[index];
                    final detail = outcome.detail;
                    return Padding(
                      key: ValueKey<String>('outcome-$index'),
                      padding: const EdgeInsets.symmetric(vertical: 4),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: <Widget>[
                          Icon(
                            outcome.imported
                                ? Icons.check_circle
                                : Icons.error_outline,
                            color: outcome.imported
                                ? Colors.green.shade600
                                : theme.colorScheme.error,
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: <Widget>[
                                Text(
                                  outcome.sourceName,
                                  style: theme.textTheme.bodyMedium?.copyWith(
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                                Text(
                                  libraryImportOutcomeText(context, outcome),
                                ),
                                if (!outcome.imported &&
                                    detail != null &&
                                    detail.isNotEmpty)
                                  LibraryTechnicalDetails(detail: detail),
                              ],
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),
              ),
            ],
          ),
        ),
        actions: <Widget>[
          FilledButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(LibraryLocalLocale.text(context, 'close')),
          ),
        ],
      ),
    );
  }
}

class _RenameDialog extends StatefulWidget {
  const _RenameDialog({required this.initial, required this.enableGamepad});

  final String initial;
  final bool enableGamepad;

  @override
  State<_RenameDialog> createState() => _RenameDialogState();
}

class _RenameDialogState extends State<_RenameDialog> {
  late final TextEditingController _controller = TextEditingController(
    text: widget.initial,
  );

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    String t(String key) => LibraryLocalLocale.text(context, key);
    return LibraryFocusGamepadLayer(
      enableGamepad: widget.enableGamepad,
      debugLabel: 'local_rename',
      autofocus: false,
      child: AlertDialog(
        title: Text(t('renameTitle')),
        content: SizedBox(
          width: 480,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              TextField(
                key: const ValueKey<String>('rename-field'),
                controller: _controller,
                autofocus: true,
                decoration: InputDecoration(labelText: t('renameLabel')),
                onSubmitted: (value) => Navigator.of(context).pop(value),
              ),
              const SizedBox(height: 8),
              Text(
                t('renameHelp'),
                key: const ValueKey<String>('rename-help'),
                style: Theme.of(context).textTheme.bodySmall,
              ),
            ],
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(t('cancel')),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(_controller.text),
            child: Text(t('save')),
          ),
        ],
      ),
    );
  }
}

class _SortDialog extends StatefulWidget {
  const _SortDialog({
    required this.sort,
    required this.ascending,
    required this.enableGamepad,
  });

  final LibraryBookSort sort;
  final bool ascending;
  final bool enableGamepad;

  @override
  State<_SortDialog> createState() => _SortDialogState();
}

class _SortDialogState extends State<_SortDialog> {
  late LibraryBookSort _sort = widget.sort;
  late bool _ascending = widget.ascending;

  @override
  Widget build(BuildContext context) {
    String t(String key) => LibraryLocalLocale.text(context, key);
    return LibraryFocusGamepadLayer(
      enableGamepad: widget.enableGamepad,
      debugLabel: 'local_sort',
      child: AlertDialog(
        title: Text(t('sort')),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                for (final sort in LibraryBookSort.values)
                  ListTile(
                    key: ValueKey<String>('sort-${sort.name}'),
                    leading: Icon(
                      sort == _sort
                          ? Icons.radio_button_checked
                          : Icons.radio_button_unchecked,
                    ),
                    title: Text(t(_sortKey(sort))),
                    onTap: () => setState(() => _sort = sort),
                  ),
                const Divider(),
                ListTile(
                  key: const ValueKey<String>('sort-order'),
                  leading: Icon(
                    _ascending ? Icons.arrow_upward : Icons.arrow_downward,
                  ),
                  title: Text(t(_ascending ? 'ascending' : 'descending')),
                  onTap: () => setState(() => _ascending = !_ascending),
                ),
              ],
            ),
          ),
        ),
        actions: <Widget>[
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: Text(t('cancel')),
          ),
          FilledButton(
            key: const ValueKey<String>('sort-apply'),
            onPressed: () => Navigator.of(context).pop((_sort, _ascending)),
            child: Text(t('save')),
          ),
        ],
      ),
    );
  }
}
