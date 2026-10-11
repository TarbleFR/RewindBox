import 'dart:async';
import 'dart:io';
import 'dart:math' as math;

import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:path/path.dart' as p;

import 'package:neostation/l10n/library_sources_locale.dart';
import 'package:neostation/services/library_addon_service.dart';
import 'package:neostation/services/library_aidoku_native_service.dart';
import 'package:neostation/services/library_http.dart';
import 'package:neostation/services/library_image_cache.dart';
import 'package:neostation/services/library_source_catalog_service.dart';
import 'package:neostation/services/library_source_health_store.dart';
import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/library_focus_gamepad_layer.dart';
import 'package:neostation/widgets/neo_glass.dart';

import 'library_catalog_preview_screen.dart';
import 'library_gamepad_view_controller.dart';

/// A catalogue file chosen by the user (`.json` or `.aix`).
class LibraryPickedCatalogFile {
  const LibraryPickedCatalogFile({required this.name, required this.bytes});

  final String name;
  final List<int> bytes;
}

/// Opens the system file picker for a catalogue file; null when cancelled.
typedef LibraryCatalogFilePicker = Future<LibraryPickedCatalogFile?> Function();

/// True when the device can reach the Internet at all (used to tell a device
/// that is offline from a source that is offline).
typedef LibraryConnectivityProbe = Future<bool> Function();

/// Default catalogue picker: any file type (an `.aix` has no system type on
/// iOS, so the extension is checked after the pick).
Future<LibraryPickedCatalogFile?> libraryPickCatalogFile() async {
  final result = await FilePicker.pickFiles(
    type: FileType.any,
    allowMultiple: false,
  );
  final file = result?.files.firstOrNull;
  final path = file?.path;
  if (file == null || path == null) return null;
  final source = File(path);
  final size = await source.length();
  if (size > LibrarySourceCatalogService.maxIndexBytes) {
    // Never read a huge file into memory: the preview refuses it anyway.
    throw LibraryCatalogException(
      LibraryCatalogErrorKind.tooLarge,
      detail: '$size bytes',
    );
  }
  return LibraryPickedCatalogFile(
    name: file.name,
    bytes: await source.readAsBytes(),
  );
}

/// Default connectivity probe: resolves a well-known host name.
Future<bool> libraryDeviceSeemsOnline() async {
  try {
    final addresses = await InternetAddress.lookup(
      'www.apple.com',
    ).timeout(const Duration(seconds: 4));
    return addresses.isNotEmpty;
  } on Object {
    return false;
  }
}

/// Kind of an installed Library source, for its label.
enum LibrarySourceKindLabel { aidoku, neoStation, gallica, tachiyomi, local }

LibrarySourceKindLabel librarySourceKindOf(LibraryAddon addon) {
  if (addon.isAidokuRepositorySource) return LibrarySourceKindLabel.aidoku;
  if (addon.isTachiyomiRepositorySource) {
    return LibrarySourceKindLabel.tachiyomi;
  }
  if (addon.isGallicaSource) return LibrarySourceKindLabel.gallica;
  if (addon.sourceKind == LibrarySourceKind.localLibrary) {
    return LibrarySourceKindLabel.local;
  }
  return LibrarySourceKindLabel.neoStation;
}

String librarySourceKindKey(LibrarySourceKindLabel kind) => switch (kind) {
  LibrarySourceKindLabel.aidoku => 'kindAidoku',
  LibrarySourceKindLabel.neoStation => 'kindNeoStation',
  LibrarySourceKindLabel.gallica => 'kindGallica',
  LibrarySourceKindLabel.tachiyomi => 'kindTachiyomi',
  LibrarySourceKindLabel.local => 'kindLocal',
};

/// State of one rung of the verification ladder.
enum LibraryLadderState { ok, failed, unknown }

/// Verification ladder of an Aidoku source: catalogue imported → adapter
/// available (or why not) → navigation verified → chapter reading verified.
/// Dates come from the latest health check run on this device when there
/// is one, otherwise from the static registry (verified from a PC).
class LibrarySourceLadder {
  const LibrarySourceLadder({
    required this.adapterAvailable,
    required this.navigation,
    required this.reading,
    this.adapterProblemKey,
    this.stateWarningKey,
    this.date,
    this.fromDevice = false,
  });

  /// Computes the ladder of [addon]; null for sources that are not Aidoku
  /// repository sources.
  static LibrarySourceLadder? of(
    LibraryAddon addon,
    LibraryAidokuNativeService aidoku,
    LibrarySourceHealthReport? report,
  ) {
    final support = aidoku.support(addon);
    if (support == null) return null;
    final supported = aidoku.supports(addon);
    final reason = aidoku.unsupportedReasonKind(addon);
    if (!supported) {
      return LibrarySourceLadder(
        adapterAvailable: false,
        adapterProblemKey: reason == null
            ? 'reasonAdapterMissing'
            : LibrarySourcesLocale.unsupportedReasonKey(reason),
        navigation: LibraryLadderState.unknown,
        reading: LibraryLadderState.unknown,
        date: support.verifiedOn,
      );
    }
    if (report != null) {
      LibraryLadderState readingState() {
        if (report.readingWorking) return LibraryLadderState.ok;
        final pages = report.step(LibrarySourceHealthStep.pages);
        final image = report.step(LibrarySourceHealthStep.image);
        final failed =
            (!pages.ok && !pages.skipped) || (!image.ok && !image.skipped);
        return failed ? LibraryLadderState.failed : LibraryLadderState.unknown;
      }

      final state = report.state;
      return LibrarySourceLadder(
        adapterAvailable: true,
        navigation: report.navigationWorking
            ? LibraryLadderState.ok
            : LibraryLadderState.failed,
        reading: readingState(),
        stateWarningKey: state == LibrarySourceKnownState.working
            ? null
            : LibrarySourcesLocale.knownStateKey(state),
        date: report.checkedAt,
        fromDevice: true,
      );
    }
    return LibrarySourceLadder(
      adapterAvailable: true,
      navigation: support.navigationVerified
          ? LibraryLadderState.ok
          : LibraryLadderState.unknown,
      reading: support.readingVerified
          ? LibraryLadderState.ok
          : LibraryLadderState.unknown,
      stateWarningKey: support.knownState == LibrarySourceKnownState.working
          ? null
          : LibrarySourcesLocale.knownStateKey(support.knownState),
      date: support.verifiedOn,
    );
  }

  final bool adapterAvailable;
  final String? adapterProblemKey;

  /// Verified state that is not "working" (challenge, server unavailable…).
  final String? stateWarningKey;
  final LibraryLadderState navigation;
  final LibraryLadderState reading;
  final DateTime? date;

  /// [date] comes from a health check run on this device.
  final bool fromDevice;
}

/// Sources & catalogues section of the Library (Build 437): remembered
/// catalogues (preview, refresh, forget), import by URL or file with a
/// preview where nothing is pre-selected, and the active sources with their
/// verification ladder, an on-device test and deactivation.
class LibrarySourcesView extends StatefulWidget {
  const LibrarySourcesView({
    super.key,
    required this.controller,
    required this.onBack,
    required this.onSourcesChanged,
    this.catalogService,
    this.addonService,
    this.aidokuService,
    this.healthStore,
    this.connectivityProbe,
    this.catalogFilePicker,
    this.imageCache,
    this.enableGamepad = true,
  });

  final LibraryGamepadViewController controller;

  /// Returns to the Library hub.
  final VoidCallback onBack;

  /// Called after sources were activated, deactivated or updated so the hub
  /// reloads its source list.
  final VoidCallback onSourcesChanged;

  /// Defaults to [LibrarySourceCatalogService.instance].
  final LibrarySourceCatalogService? catalogService;

  /// Must be the add-on service used by [catalogService]; defaults to
  /// [LibraryAddonService.instance].
  final LibraryAddonService? addonService;
  final LibraryAidokuNativeService? aidokuService;
  final LibrarySourceHealthStore? healthStore;
  final LibraryConnectivityProbe? connectivityProbe;
  final LibraryCatalogFilePicker? catalogFilePicker;
  final LibraryImageCache? imageCache;

  /// Pushed dialogs and routes register their own controller layer; false
  /// in widget tests that do not stub the gamepad plugin.
  final bool enableGamepad;

  @override
  State<LibrarySourcesView> createState() => _LibrarySourcesViewState();
}

/// Controller input of an embedded Library section, applied to Flutter's
/// focus inside [scope]. `back` returns false (LibraryScreen returns to the
/// hub) unless a text field is being edited.
class LibraryFocusSectionDelegate implements LibraryGamepadViewDelegate {
  LibraryFocusSectionDelegate(this.scope, {this.onSecondary});

  final FocusNode scope;

  /// X button; returns whether it did something.
  final bool Function()? onSecondary;

  /// True while another route covers the section (a dialog or sheet without
  /// its own controller layer): the input is swallowed so it never moves
  /// the focus to, or activates, a control hidden behind that route, and B
  /// does not switch the Library behind it.
  bool get _covered {
    final context = scope.context;
    if (context == null || !context.mounted) return true;
    return !(ModalRoute.isCurrentOf(context) ?? true);
  }

  @override
  bool navigate(int dx, int dy) {
    if (_covered) return true;
    final direction = dy < 0
        ? TraversalDirection.up
        : dy > 0
        ? TraversalDirection.down
        : dx < 0
        ? TraversalDirection.left
        : TraversalDirection.right;
    LibraryFocusNavigation.move(scope, direction);
    return true;
  }

  @override
  bool activate() {
    if (_covered) return true;
    if (!LibraryFocusNavigation.activate(scope)) {
      LibraryFocusNavigation.showFocus();
      LibraryFocusNavigation.focusFirst(scope);
    }
    return true;
  }

  @override
  bool back() {
    if (_covered) return true;
    if (LibraryFocusNavigation.editingText(scope)) {
      FocusManager.instance.primaryFocus?.unfocus();
      return true;
    }
    return false;
  }

  @override
  bool secondary() {
    if (_covered) return true;
    return onSecondary?.call() ?? false;
  }
}

class _LibrarySourcesViewState extends State<LibrarySourcesView> {
  late final LibraryFocusSectionDelegate _delegate =
      LibraryFocusSectionDelegate(_scope, onSecondary: _secondary);
  final FocusScopeNode _scope = FocusScopeNode(
    debugLabel: 'LibrarySourcesView',
  );
  final ScrollController _scroll = ScrollController();

  List<LibraryStoredCatalog> _catalogs = const <LibraryStoredCatalog>[];
  List<LibraryAddon> _addons = const <LibraryAddon>[];
  bool _loading = true;
  Object? _loadError;
  String? _focusedAddonId;
  int _reloadGeneration = 0;

  LibrarySourceCatalogService get _catalogService =>
      widget.catalogService ?? LibrarySourceCatalogService.instance;
  LibraryAddonService get _addonService =>
      widget.addonService ?? LibraryAddonService.instance;
  LibraryAidokuNativeService get _aidoku =>
      widget.aidokuService ?? LibraryAidokuNativeService.instance;
  LibrarySourceHealthStore get _health =>
      widget.healthStore ?? LibrarySourceHealthStore.instance;

  String _t(String key) => LibrarySourcesLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      LibrarySourcesLocale.format(context, key, values);

  @override
  void initState() {
    super.initState();
    widget.controller.attach(_delegate);
    _health.addListener(_onHealthChanged);
    unawaited(_health.load().catchError((Object _) {}));
    unawaited(_reload());
  }

  @override
  void didUpdateWidget(covariant LibrarySourcesView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(oldWidget.controller, widget.controller)) {
      oldWidget.controller.detach(_delegate);
      widget.controller.attach(_delegate);
    }
    if (!identical(oldWidget.healthStore, widget.healthStore)) {
      (oldWidget.healthStore ?? LibrarySourceHealthStore.instance)
          .removeListener(_onHealthChanged);
      _health.addListener(_onHealthChanged);
    }
  }

  @override
  void dispose() {
    widget.controller.detach(_delegate);
    // Leaving the section gives the focus highlight back to touch mode.
    scheduleMicrotask(LibraryFocusNavigation.restoreTouchHighlight);
    _health.removeListener(_onHealthChanged);
    _scope.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _onHealthChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _reload() async {
    final generation = ++_reloadGeneration;
    try {
      final results = await Future.wait<Object>(<Future<Object>>[
        _catalogService.list(),
        _addonService.load(),
      ]);
      if (!mounted || generation != _reloadGeneration) return;
      setState(() {
        _catalogs = results[0] as List<LibraryStoredCatalog>;
        _addons = List<LibraryAddon>.of(results[1] as List<LibraryAddon>);
        _loading = false;
        _loadError = null;
      });
    } on Object catch (error) {
      if (!mounted || generation != _reloadGeneration) return;
      setState(() {
        _loading = false;
        _loadError = error;
      });
    }
  }

  // ------------------------------------------------------------- gamepad --

  /// X on a focused source row runs its test.
  bool _secondary() {
    final id = _focusedAddonId;
    if (id == null) return false;
    final addon = _addons.where((item) => item.id == id).firstOrNull;
    if (addon == null || !_aidoku.supports(addon)) return false;
    unawaited(_testSource(addon));
    return true;
  }

  // ------------------------------------------------------------- actions --

  void _snack(String message) {
    if (!mounted) return;
    ScaffoldMessenger.maybeOf(context)
      ?..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(content: Text(message), duration: const Duration(seconds: 3)),
      );
  }

  Future<void> _addFromUrl() async {
    final url = await showDialog<String>(
      context: context,
      barrierDismissible: false,
      builder: (_) => _CatalogUrlDialog(enableGamepad: widget.enableGamepad),
    );
    if (!mounted || url == null || url.trim().isEmpty) return;
    await _previewAndOpen(
      (cancel) => _catalogService.preview(url.trim(), cancel: cancel),
      retry: () => _previewAndOpenUrl(url.trim()),
    );
  }

  Future<void> _previewAndOpenUrl(String url, {bool refresh = false}) =>
      _previewAndOpen(
        (cancel) =>
            _catalogService.preview(url, cancel: cancel, refresh: refresh),
        retry: () => _previewAndOpenUrl(url, refresh: refresh),
      );

  Future<void> _importFile() async {
    final LibraryPickedCatalogFile? file;
    try {
      file = await (widget.catalogFilePicker ?? libraryPickCatalogFile)();
    } on Object catch (error) {
      if (!mounted) return;
      await _showError(error, titleKey: 'fileUnreadable');
      return;
    }
    if (!mounted || file == null) return;
    final extension = p.extension(file.name).toLowerCase();
    if (extension != '.json' && extension != '.aix') {
      _snack(_t('fileWrongType'));
      return;
    }
    final picked = file;
    await _previewAndOpen(
      (_) =>
          _catalogService.previewDocument(picked.bytes, fileName: picked.name),
    );
  }

  /// Runs [load] behind a cancellable progress dialog, then opens the
  /// preview. Errors are shown translated with their technical detail.
  Future<void> _previewAndOpen(
    Future<LibraryCatalogPreview> Function(LibraryCancelToken cancel) load, {
    Future<void> Function()? retry,
  }) async {
    final cancel = LibraryCancelToken();
    final LibraryCatalogPreview preview;
    try {
      final result = await _withProgress(
        _t('loadingCatalog'),
        cancel,
        () => load(cancel),
      );
      if (result == null) return;
      preview = result;
    } on Object catch (error) {
      if (!mounted || cancel.isCancelled) return;
      final again = await _showError(error, retryable: retry != null);
      if (again && retry != null && mounted) await retry();
      return;
    }
    if (!mounted) return;
    final result = await LibraryCatalogPreviewScreen.open(
      context,
      preview,
      catalogService: _catalogService,
      aidokuService: _aidoku,
      imageCache: widget.imageCache,
      enableGamepad: widget.enableGamepad,
    );
    if (!mounted) return;
    if (result != null && result.changed) widget.onSourcesChanged();
    await _reload();
  }

  /// Shows a modal progress dialog with a cancel button while [task] runs.
  /// Returns null when the user cancelled.
  Future<T?> _withProgress<T>(
    String message,
    LibraryCancelToken cancel,
    Future<T> Function() task,
  ) async {
    final navigator = Navigator.of(context, rootNavigator: true);
    late final DialogRoute<void> route;
    void cancelAndClose() {
      cancel.cancel();
      if (route.isCurrent) navigator.pop();
    }

    route = DialogRoute<void>(
      context: context,
      barrierDismissible: false,
      barrierLabel: MaterialLocalizations.of(context).modalBarrierDismissLabel,
      themes: InheritedTheme.capture(from: context, to: navigator.context),
      builder: (dialogContext) => LibraryFocusGamepadLayer(
        enableGamepad: widget.enableGamepad,
        debugLabel: 'sources_progress',
        onBack: cancelAndClose,
        child: AlertDialog(
          content: Row(
            children: <Widget>[
              const SizedBox(
                width: 28,
                height: 28,
                child: CircularProgressIndicator(strokeWidth: 3),
              ),
              const SizedBox(width: 16),
              Expanded(child: Text(message)),
            ],
          ),
          actions: <Widget>[
            TextButton(
              onPressed: cancelAndClose,
              child: Text(LibrarySourcesLocale.text(dialogContext, 'cancel')),
            ),
          ],
        ),
      ),
    );
    unawaited(navigator.push(route));
    try {
      final value = await task();
      if (cancel.isCancelled) return null;
      return value;
    } finally {
      // Closes this dialog itself, never a route pushed above it meanwhile.
      if (route.isActive && navigator.mounted) {
        if (route.isCurrent) {
          navigator.pop();
        } else {
          navigator.removeRoute(route);
        }
      }
    }
  }

  /// Translated error dialog with the raw detail apart. Returns true when
  /// the user chose to retry.
  Future<bool> _showError(
    Object error, {
    bool retryable = false,
    String titleKey = 'catalogErrorTitle',
  }) async {
    final retry = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => LibraryFocusGamepadLayer(
        enableGamepad: widget.enableGamepad,
        debugLabel: 'sources_error',
        child: AlertDialog(
          title: Text(LibrarySourcesLocale.text(dialogContext, titleKey)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  LibrarySourcesLocale.text(
                    dialogContext,
                    LibrarySourcesLocale.errorKey(error),
                  ),
                ),
                const SizedBox(height: 8),
                LibraryTechnicalDetails(
                  detail: LibrarySourcesLocale.technicalDetail(error),
                ),
              ],
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: Text(LibrarySourcesLocale.text(dialogContext, 'close')),
            ),
            if (retryable)
              FilledButton(
                onPressed: () => Navigator.of(dialogContext).pop(true),
                child: Text(LibrarySourcesLocale.text(dialogContext, 'retry')),
              ),
          ],
        ),
      ),
    );
    return retry ?? false;
  }

  Future<void> _refreshCatalog(LibraryStoredCatalog catalog) async {
    final cancel = LibraryCancelToken();
    try {
      final preview = await _withProgress(
        _t('loadingCatalog'),
        cancel,
        () =>
            _catalogService.preview(catalog.url, cancel: cancel, refresh: true),
      );
      if (preview == null || !mounted) return;
      await _reload();
      _snack(
        _f('refreshed', <String, Object?>{
          'name': preview.name ?? catalog.name ?? catalog.url,
          'count': preview.sources.length,
        }),
      );
    } on Object catch (error) {
      if (!mounted || cancel.isCancelled) return;
      final again = await _showError(error, retryable: true);
      if (again && mounted) await _refreshCatalog(catalog);
    }
  }

  Future<void> _forgetCatalog(LibraryStoredCatalog catalog) async {
    final choice = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => LibraryFocusGamepadLayer(
        enableGamepad: widget.enableGamepad,
        debugLabel: 'sources_forget',
        child: AlertDialog(
          title: Text(LibrarySourcesLocale.text(dialogContext, 'forgetTitle')),
          content: Text(
            LibrarySourcesLocale.format(dialogContext, 'forgetBody', {
              'name': catalog.name ?? catalog.url,
            }),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(),
              child: Text(LibrarySourcesLocale.text(dialogContext, 'cancel')),
            ),
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: Text(
                LibrarySourcesLocale.text(dialogContext, 'forgetKeep'),
              ),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: Text(
                LibrarySourcesLocale.text(dialogContext, 'forgetDeactivate'),
              ),
            ),
          ],
        ),
      ),
    );
    if (!mounted || choice == null) return;
    try {
      final removed = await _catalogService.forget(
        catalog.url,
        deactivateSources: choice,
      );
      if (!mounted) return;
      if (choice) widget.onSourcesChanged();
      await _reload();
      _snack(
        removed > 0
            ? _f('forgottenWithSources', <String, Object?>{'count': removed})
            : _t('forgotten'),
      );
    } on Object catch (error) {
      if (mounted) await _showError(error, titleKey: 'errorUnknown');
    }
  }

  Future<void> _deactivate(LibraryAddon addon) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (dialogContext) => LibraryFocusGamepadLayer(
        enableGamepad: widget.enableGamepad,
        debugLabel: 'sources_deactivate',
        child: AlertDialog(
          title: Text(
            LibrarySourcesLocale.format(dialogContext, 'deactivateTitle', {
              'name': addon.name,
            }),
          ),
          content: Text(
            LibrarySourcesLocale.text(dialogContext, 'deactivateBody'),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(dialogContext).pop(false),
              child: Text(LibrarySourcesLocale.text(dialogContext, 'cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.of(dialogContext).pop(true),
              child: Text(
                LibrarySourcesLocale.text(dialogContext, 'deactivate'),
              ),
            ),
          ],
        ),
      ),
    );
    if (!mounted || confirmed != true) return;
    try {
      await _catalogService.deactivate(addon.id);
    } on Object catch (error) {
      if (mounted) await _showError(error, titleKey: 'errorUnknown');
      return;
    }
    if (!mounted) return;
    widget.onSourcesChanged();
    await _reload();
    _snack(_f('deactivated', <String, Object?>{'name': addon.name}));
  }

  Future<void> _testSource(LibraryAddon addon) async {
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => LibrarySourceHealthDialog(
        addon: addon,
        aidokuService: _aidoku,
        healthStore: _health,
        connectivityProbe: widget.connectivityProbe ?? libraryDeviceSeemsOnline,
        enableGamepad: widget.enableGamepad,
      ),
    );
  }

  // --------------------------------------------------------------- build --

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
              SizedBox(height: 12.r),
              _buildActions(theme),
              SizedBox(height: 12.r),
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
          Symbols.extension_rounded,
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

  Widget _buildActions(ThemeData theme) {
    return Wrap(
      spacing: 10.r,
      runSpacing: 8.r,
      children: <Widget>[
        FilledButton.icon(
          onPressed: _addFromUrl,
          icon: const Icon(Symbols.link_rounded),
          label: Text(_t('addCatalogUrl')),
        ),
        OutlinedButton.icon(
          onPressed: _importFile,
          icon: const Icon(Symbols.upload_file_rounded),
          label: Text(_t('importCatalogFile')),
        ),
      ],
    );
  }

  Widget _buildBody(ThemeData theme) {
    if (_loading) {
      return const Center(child: CircularProgressIndicator());
    }
    final error = _loadError;
    if (error != null) {
      return Center(
        child: ConstrainedBox(
          constraints: BoxConstraints(maxWidth: 520.r),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: <Widget>[
              Text(_t(LibrarySourcesLocale.errorKey(error))),
              SizedBox(height: 6.r),
              LibraryTechnicalDetails(
                detail: LibrarySourcesLocale.technicalDetail(error),
              ),
              SizedBox(height: 10.r),
              FilledButton.tonal(
                onPressed: () {
                  setState(() => _loading = true);
                  unawaited(_reload());
                },
                child: Text(_t('retry')),
              ),
            ],
          ),
        ),
      );
    }
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.62);
    return CustomScrollView(
      controller: _scroll,
      slivers: <Widget>[
        SliverToBoxAdapter(child: _sectionTitle(theme, _t('catalogs'))),
        if (_catalogs.isEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 10.r),
              child: Text(
                _t('noCatalogs'),
                style: theme.textTheme.bodyMedium?.copyWith(color: muted),
              ),
            ),
          )
        else
          SliverList.builder(
            itemCount: _catalogs.length,
            itemBuilder: (context, index) => Padding(
              padding: EdgeInsets.only(bottom: 8.r),
              child: _CatalogRow(
                catalog: _catalogs[index],
                onOpen: () => _previewAndOpenUrl(_catalogs[index].url),
                onRefresh: () => _refreshCatalog(_catalogs[index]),
                onForget: () => _forgetCatalog(_catalogs[index]),
              ),
            ),
          ),
        SliverToBoxAdapter(child: SizedBox(height: 12.r)),
        SliverToBoxAdapter(child: _sectionTitle(theme, _t('activeSources'))),
        if (_addons.isEmpty)
          SliverToBoxAdapter(
            child: Padding(
              padding: EdgeInsets.symmetric(vertical: 10.r),
              child: Text(
                _t('noActiveSources'),
                style: theme.textTheme.bodyMedium?.copyWith(color: muted),
              ),
            ),
          )
        else
          SliverList.builder(
            itemCount: _addons.length,
            itemBuilder: (context, index) {
              final addon = _addons[index];
              final sourceId = _aidoku.sourceIdFor(addon);
              return Padding(
                key: ValueKey<String>('source-${addon.id}'),
                padding: EdgeInsets.only(bottom: 8.r),
                child: _SourceRow(
                  addon: addon,
                  ladder: LibrarySourceLadder.of(
                    addon,
                    _aidoku,
                    sourceId == null ? null : _health.latest(sourceId),
                  ),
                  canTest: _aidoku.supports(addon),
                  imageCache: widget.imageCache,
                  onFocusChange: (focused) {
                    if (focused) {
                      _focusedAddonId = addon.id;
                    } else if (_focusedAddonId == addon.id) {
                      _focusedAddonId = null;
                    }
                  },
                  onTest: () => _testSource(addon),
                  onDeactivate: () => _deactivate(addon),
                ),
              );
            },
          ),
        SliverToBoxAdapter(child: SizedBox(height: 28.r)),
      ],
    );
  }

  Widget _sectionTitle(ThemeData theme, String text) => Padding(
    padding: EdgeInsets.only(bottom: 7.r),
    child: Text(
      text,
      style: theme.textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
    ),
  );
}

/// Minimum touch target (Apple HIG: 44 pt), whatever the .r scale.
double _tap(double value) => math.max(44.0, value);

String libraryShortDate(BuildContext context, DateTime date) =>
    MaterialLocalizations.of(context).formatShortDate(date.toLocal());

class _CatalogRow extends StatelessWidget {
  const _CatalogRow({
    required this.catalog,
    required this.onOpen,
    required this.onRefresh,
    required this.onForget,
  });

  final LibraryStoredCatalog catalog;
  final VoidCallback onOpen;
  final VoidCallback onRefresh;
  final VoidCallback onForget;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String t(String key) => LibrarySourcesLocale.text(context, key);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.64);
    return NeoGlass(
      role: GlassSurfaceRole.card,
      borderRadius: BorderRadius.circular(12.r),
      enableBackdropBlur: false,
      showSheen: false,
      padding: EdgeInsets.symmetric(horizontal: 12.r, vertical: 8.r),
      child: Row(
        children: <Widget>[
          Icon(
            Symbols.library_books_rounded,
            size: 26.r,
            color: theme.colorScheme.primary,
          ),
          SizedBox(width: 10.r),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: <Widget>[
                Text(
                  catalog.name ??
                      Uri.tryParse(catalog.url)?.host ??
                      catalog.url,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleSmall?.copyWith(
                    fontWeight: FontWeight.w700,
                  ),
                ),
                Text(
                  catalog.url,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.bodySmall?.copyWith(color: muted),
                ),
                Text(
                  '${LibrarySourcesLocale.format(context, 'sourceCount', {'count': catalog.sourceCount})}'
                  ' • '
                  '${LibrarySourcesLocale.format(context, 'lastRefresh', {'date': libraryShortDate(context, catalog.lastFetchedAt)})}',
                  style: theme.textTheme.bodySmall?.copyWith(color: muted),
                ),
              ],
            ),
          ),
          SizedBox(width: 8.r),
          LibraryFocusRing(
            child: TextButton.icon(
              onPressed: onOpen,
              icon: const Icon(Symbols.visibility_rounded),
              label: Text(t('showSources')),
            ),
          ),
          LibraryFocusRing(
            child: IconButton(
              tooltip: t('refresh'),
              constraints: BoxConstraints(
                minWidth: _tap(40.r),
                minHeight: _tap(40.r),
              ),
              onPressed: onRefresh,
              icon: const Icon(Symbols.refresh_rounded),
            ),
          ),
          LibraryFocusRing(
            child: IconButton(
              tooltip: t('forget'),
              constraints: BoxConstraints(
                minWidth: _tap(40.r),
                minHeight: _tap(40.r),
              ),
              onPressed: onForget,
              icon: const Icon(Symbols.delete_rounded),
            ),
          ),
        ],
      ),
    );
  }
}

class _SourceRow extends StatelessWidget {
  const _SourceRow({
    required this.addon,
    required this.ladder,
    required this.canTest,
    required this.onTest,
    required this.onDeactivate,
    required this.onFocusChange,
    this.imageCache,
  });

  final LibraryAddon addon;
  final LibrarySourceLadder? ladder;
  final bool canTest;
  final VoidCallback onTest;
  final VoidCallback onDeactivate;
  final ValueChanged<bool> onFocusChange;
  final LibraryImageCache? imageCache;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String t(String key) => LibrarySourcesLocale.text(context, key);
    String f(String key, Map<String, Object?> values) =>
        LibrarySourcesLocale.format(context, key, values);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.64);
    final kind = librarySourceKindOf(addon);
    final languages = addon.languages;
    final ladder = this.ladder;
    final iconSize = 40.r;
    final iconUrl = addon.iconUrl;
    final dpr = MediaQuery.devicePixelRatioOf(context);

    return LibraryFocusRing(
      onFocusChange: onFocusChange,
      child: NeoGlass(
        role: GlassSurfaceRole.card,
        borderRadius: BorderRadius.circular(12.r),
        enableBackdropBlur: false,
        showSheen: false,
        padding: EdgeInsets.all(10.r),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: <Widget>[
            Row(
              children: <Widget>[
                ClipRRect(
                  borderRadius: BorderRadius.circular(8.r),
                  child: SizedBox(
                    width: iconSize,
                    height: iconSize,
                    child: iconUrl == null
                        ? _iconPlaceholder(theme)
                        : Image(
                            image: LibraryNetworkImage(
                              iconUrl,
                              cacheWidth: (iconSize * dpr).round(),
                              cache: imageCache,
                            ),
                            fit: BoxFit.cover,
                            errorBuilder: (_, _, _) => _iconPlaceholder(theme),
                          ),
                  ),
                ),
                SizedBox(width: 10.r),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: <Widget>[
                      Text(
                        addon.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.titleSmall?.copyWith(
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                      Text(
                        <String>[
                          t(librarySourceKindKey(kind)),
                          f('version', <String, Object?>{
                            'version': addon.version,
                          }),
                          if (languages.isNotEmpty)
                            f('languages', <String, Object?>{
                              'languages': languages.join(', '),
                            }),
                        ].join(' • '),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: theme.textTheme.bodySmall?.copyWith(
                          color: muted,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: 6.r),
                LibraryRatingBadge(rating: addon.contentRating),
                SizedBox(width: 6.r),
                if (canTest)
                  TextButton.icon(
                    onPressed: onTest,
                    icon: const Icon(Symbols.network_check_rounded),
                    label: Text(t('test')),
                  ),
                TextButton.icon(
                  onPressed: onDeactivate,
                  icon: const Icon(Symbols.block_rounded),
                  label: Text(t('deactivate')),
                ),
              ],
            ),
            if (ladder != null) ...<Widget>[
              SizedBox(height: 6.r),
              Wrap(
                spacing: 6.r,
                runSpacing: 4.r,
                children: _ladderChips(context, ladder),
              ),
              if (ladder.date != null && ladder.adapterAvailable) ...<Widget>[
                SizedBox(height: 4.r),
                Text(
                  f(ladder.fromDevice ? 'deviceNote' : 'staticNote', {
                    'date': libraryShortDate(context, ladder.date!),
                  }),
                  style: theme.textTheme.bodySmall?.copyWith(color: muted),
                ),
              ],
            ],
          ],
        ),
      ),
    );
  }

  Widget _iconPlaceholder(ThemeData theme) => ColoredBox(
    color: theme.colorScheme.primary.withValues(alpha: 0.14),
    child: Icon(Symbols.extension_rounded, color: theme.colorScheme.primary),
  );

  List<Widget> _ladderChips(BuildContext context, LibrarySourceLadder ladder) {
    String t(String key) => LibrarySourcesLocale.text(context, key);
    String dated(String key) => LibrarySourcesLocale.format(context, key, {
      'date': ladder.date == null
          ? ''
          : libraryShortDate(context, ladder.date!),
    });
    final chips = <Widget>[
      LibraryStatusChip(
        label: t('ladderImported'),
        state: LibraryLadderState.ok,
      ),
    ];
    if (!ladder.adapterAvailable) {
      chips.add(
        LibraryStatusChip(
          label: t(ladder.adapterProblemKey ?? 'reasonAdapterMissing'),
          state: LibraryLadderState.failed,
        ),
      );
      return chips;
    }
    chips.add(
      LibraryStatusChip(
        label: t('ladderAdapter'),
        state: LibraryLadderState.ok,
      ),
    );
    final warning = ladder.stateWarningKey;
    if (warning != null) {
      chips.add(
        LibraryStatusChip(label: t(warning), state: LibraryLadderState.failed),
      );
    }
    chips.add(
      LibraryStatusChip(
        label: switch (ladder.navigation) {
          LibraryLadderState.ok => dated('ladderNavigationOk'),
          LibraryLadderState.failed => dated('ladderNavigationFailed'),
          LibraryLadderState.unknown => t('ladderNavigationUnknown'),
        },
        state: ladder.navigation,
      ),
    );
    chips.add(
      LibraryStatusChip(
        label: switch (ladder.reading) {
          LibraryLadderState.ok => dated('ladderReadingOk'),
          LibraryLadderState.failed => dated('ladderReadingFailed'),
          LibraryLadderState.unknown => t('ladderReadingUnknown'),
        },
        state: ladder.reading,
      ),
    );
    return chips;
  }
}

/// Small coloured label of a ladder rung or a status.
class LibraryStatusChip extends StatelessWidget {
  const LibraryStatusChip({
    super.key,
    required this.label,
    required this.state,
  });

  final String label;
  final LibraryLadderState state;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (Color color, IconData icon) = switch (state) {
      LibraryLadderState.ok => (Colors.green.shade600, Icons.check_circle),
      LibraryLadderState.failed => (scheme.error, Icons.error_outline),
      LibraryLadderState.unknown => (
        scheme.onSurface.withValues(alpha: 0.55),
        Icons.help_outline,
      ),
    };
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.45)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 4),
          Flexible(
            child: Text(
              label,
              style: Theme.of(
                context,
              ).textTheme.labelSmall?.copyWith(color: scheme.onSurface),
            ),
          ),
        ],
      ),
    );
  }
}

/// Content rating badge (0 all audiences, 1 some adult content, 2 adults
/// only).
class LibraryRatingBadge extends StatelessWidget {
  const LibraryRatingBadge({super.key, required this.rating});

  final int rating;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final (String key, Color color) = switch (rating) {
      <= 0 => ('ratingSafe', Colors.green.shade600),
      1 => ('ratingSuggestive', Colors.orange.shade700),
      _ => ('ratingExplicit', scheme.error),
    };
    final label = LibrarySourcesLocale.text(context, key);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: color),
      ),
      child: Text(
        label,
        maxLines: 1,
        overflow: TextOverflow.ellipsis,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(color: color),
      ),
    );
  }
}

/// "Technical details" disclosure: the raw, untranslated diagnostic (URL,
/// HTTP status, exception text) shown apart from the translated
/// explanation.
class LibraryTechnicalDetails extends StatefulWidget {
  const LibraryTechnicalDetails({super.key, required this.detail});

  final String detail;

  @override
  State<LibraryTechnicalDetails> createState() =>
      _LibraryTechnicalDetailsState();
}

class _LibraryTechnicalDetailsState extends State<LibraryTechnicalDetails> {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    if (widget.detail.trim().isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        TextButton.icon(
          onPressed: () => setState(() => _open = !_open),
          icon: Icon(_open ? Icons.expand_less : Icons.expand_more),
          label: Text(LibrarySourcesLocale.text(context, 'technicalDetails')),
        ),
        if (_open)
          SelectableText(
            widget.detail,
            style: theme.textTheme.bodySmall?.copyWith(
              fontFamily: 'monospace',
              color: theme.colorScheme.onSurface.withValues(alpha: 0.75),
            ),
          ),
      ],
    );
  }
}

class _CatalogUrlDialog extends StatefulWidget {
  const _CatalogUrlDialog({required this.enableGamepad});

  final bool enableGamepad;

  @override
  State<_CatalogUrlDialog> createState() => _CatalogUrlDialogState();
}

class _CatalogUrlDialogState extends State<_CatalogUrlDialog> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _submit() {
    final value = _controller.text.trim();
    if (value.isNotEmpty) Navigator.of(context).pop(value);
  }

  Future<void> _paste() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    final text = data?.text?.trim();
    if (!mounted || text == null || text.isEmpty) return;
    _controller.text = text;
    _controller.selection = TextSelection.collapsed(offset: text.length);
  }

  @override
  Widget build(BuildContext context) {
    String t(String key) => LibrarySourcesLocale.text(context, key);
    return LibraryFocusGamepadLayer(
      enableGamepad: widget.enableGamepad,
      debugLabel: 'sources_url',
      autofocus: false,
      child: AlertDialog(
        title: Text(t('urlDialogTitle')),
        content: SizedBox(
          width: 520,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: <Widget>[
              TextField(
                key: const ValueKey<String>('catalog-url-field'),
                controller: _controller,
                autofocus: true,
                keyboardType: TextInputType.url,
                textInputAction: TextInputAction.go,
                autocorrect: false,
                enableSuggestions: false,
                decoration: InputDecoration(
                  labelText: t('urlDialogLabel'),
                  hintText: 'https://',
                  suffixIcon: IconButton(
                    tooltip: t('paste'),
                    onPressed: _paste,
                    icon: const Icon(Icons.content_paste),
                  ),
                ),
                onSubmitted: (_) => _submit(),
              ),
              const SizedBox(height: 8),
              Text(
                t('urlDialogHelp'),
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
          FilledButton(onPressed: _submit, child: Text(t('showSources'))),
        ],
      ),
    );
  }
}

/// Progress dialog of an on-device source test: each step appears with its
/// result (translated reason and raw detail) as soon as it ends. The report
/// is saved in [healthStore] unless every executed step failed because the
/// device itself is offline.
class LibrarySourceHealthDialog extends StatefulWidget {
  const LibrarySourceHealthDialog({
    super.key,
    required this.addon,
    required this.aidokuService,
    required this.healthStore,
    required this.connectivityProbe,
    this.enableGamepad = true,
  });

  final LibraryAddon addon;
  final LibraryAidokuNativeService aidokuService;
  final LibrarySourceHealthStore healthStore;
  final LibraryConnectivityProbe connectivityProbe;
  final bool enableGamepad;

  @override
  State<LibrarySourceHealthDialog> createState() =>
      _LibrarySourceHealthDialogState();
}

enum _HealthOutcome { working, navigationOnly, failed, deviceOffline }

class _LibrarySourceHealthDialogState extends State<LibrarySourceHealthDialog> {
  final LibraryCancelToken _cancel = LibraryCancelToken();
  final Map<LibrarySourceHealthStep, LibrarySourceHealthStepResult> _done =
      <LibrarySourceHealthStep, LibrarySourceHealthStepResult>{};
  LibrarySourceHealthReport? _report;
  _HealthOutcome? _outcome;
  bool _siteOfflineWhileOnline = false;
  bool _saveFailed = false;
  Object? _error;
  final ScrollController _scroll = ScrollController();

  @override
  void initState() {
    super.initState();
    unawaited(_run());
  }

  @override
  void dispose() {
    _cancel.cancel();
    _scroll.dispose();
    super.dispose();
  }

  /// Brings the verdict into view once the test ends: in landscape on an
  /// iPhone the five steps already fill the dialog, and a controller cannot
  /// scroll text that takes no focus.
  void _revealResult() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_scroll.hasClients) return;
      unawaited(
        _scroll.animateTo(
          _scroll.position.maxScrollExtent,
          duration: const Duration(milliseconds: 250),
          curve: Curves.easeOut,
        ),
      );
    });
  }

  Future<void> _run() async {
    final LibrarySourceHealthReport report;
    try {
      report = await widget.aidokuService.checkHealth(
        widget.addon,
        cancel: _cancel,
        onStep: (result) {
          if (mounted) setState(() => _done[result.step] = result);
        },
      );
    } on Object catch (error) {
      if (!mounted || _cancel.isCancelled) return;
      setState(() => _error = error);
      _revealResult();
      return;
    }
    if (!mounted || _cancel.isCancelled) return;
    final executed = report.steps.where((step) => !step.skipped).toList();
    final allOffline =
        executed.isNotEmpty &&
        executed.every(
          (step) =>
              !step.ok && step.networkError == LibraryNetworkErrorKind.offline,
        );
    var outcome = report.readingWorking
        ? _HealthOutcome.working
        : report.navigationWorking
        ? _HealthOutcome.navigationOnly
        : _HealthOutcome.failed;
    var save = true;
    if (allOffline) {
      final online = await widget.connectivityProbe();
      if (!mounted || _cancel.isCancelled) return;
      if (!online) {
        outcome = _HealthOutcome.deviceOffline;
        save = false;
      } else {
        _siteOfflineWhileOnline = true;
      }
    }
    var saveFailed = false;
    if (save) {
      try {
        await widget.healthStore.record(report);
      } on Object {
        saveFailed = true;
      }
    }
    if (!mounted) return;
    setState(() {
      _report = report;
      _outcome = outcome;
      _saveFailed = saveFailed;
    });
    _revealResult();
  }

  bool get _finished => _report != null || _error != null;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    String t(String key) => LibrarySourcesLocale.text(context, key);
    final report = _report;
    final outcome = _outcome;
    final error = _error;
    return LibraryFocusGamepadLayer(
      enableGamepad: widget.enableGamepad,
      debugLabel: 'sources_health',
      onBack: () => Navigator.of(context).pop(),
      child: AlertDialog(
        title: Text(
          LibrarySourcesLocale.format(context, 'healthTitle', {
            'name': widget.addon.name,
          }),
        ),
        content: SizedBox(
          width: 560,
          child: SingleChildScrollView(
            controller: _scroll,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                Text(t('healthIntro'), style: theme.textTheme.bodySmall),
                const SizedBox(height: 10),
                for (final step in LibrarySourceHealthStep.values)
                  _stepTile(context, step),
                if (outcome != null) ...<Widget>[
                  const Divider(),
                  Text(
                    t(switch (outcome) {
                      _HealthOutcome.working => 'healthWorking',
                      _HealthOutcome.navigationOnly => 'healthNavigationOnly',
                      _HealthOutcome.failed => 'healthFailed',
                      _HealthOutcome.deviceOffline => 'healthDeviceOffline',
                    }),
                    key: const ValueKey<String>('health-outcome'),
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  if (_siteOfflineWhileOnline)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(t('healthSiteOffline')),
                    ),
                  if (_saveFailed)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(t('healthNotSaved')),
                    ),
                  if (report != null && outcome != _HealthOutcome.deviceOffline)
                    Padding(
                      padding: const EdgeInsets.only(top: 4),
                      child: Text(
                        LibrarySourcesLocale.format(context, 'deviceNote', {
                          'date': libraryShortDate(context, report.checkedAt),
                        }),
                        style: theme.textTheme.bodySmall,
                      ),
                    ),
                ],
                if (error != null) ...<Widget>[
                  const Divider(),
                  Text(t(LibrarySourcesLocale.errorKey(error))),
                  LibraryTechnicalDetails(
                    detail: LibrarySourcesLocale.technicalDetail(error),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: <Widget>[
          if (_finished)
            FilledButton(
              onPressed: () => Navigator.of(context).pop(),
              child: Text(t('close')),
            )
          else
            TextButton(
              onPressed: () {
                _cancel.cancel();
                Navigator.of(context).pop();
              },
              child: Text(t('cancel')),
            ),
        ],
      ),
    );
  }

  Widget _stepTile(BuildContext context, LibrarySourceHealthStep step) {
    final theme = Theme.of(context);
    String t(String key) => LibrarySourcesLocale.text(context, key);
    final result = _report?.step(step) ?? _done[step];
    final running =
        result == null &&
        !_finished &&
        LibrarySourceHealthStep.values
            .takeWhile((value) => value != step)
            .every(_done.containsKey);
    final Widget leading;
    final String status;
    String? reason;
    String? detail;
    if (result == null) {
      leading = running
          ? const SizedBox(
              width: 20,
              height: 20,
              child: CircularProgressIndicator(strokeWidth: 2),
            )
          : Icon(Icons.radio_button_unchecked, color: theme.disabledColor);
      status = t(running ? 'stepRunning' : 'stepPending');
    } else if (result.skipped) {
      leading = Icon(Icons.remove_circle_outline, color: theme.disabledColor);
      status = t('stepSkipped');
    } else if (result.ok) {
      leading = Icon(Icons.check_circle, color: Colors.green.shade600);
      status = step == LibrarySourceHealthStep.image
          ? LibrarySourcesLocale.format(context, 'stepImageSize', {
              'size': (result.count / 1024).ceil(),
            })
          : LibrarySourcesLocale.format(context, 'stepCount', {
              'count': result.count,
            });
    } else {
      leading = Icon(Icons.error_outline, color: theme.colorScheme.error);
      status = t('stepFailed');
      final network = result.networkError;
      final source = result.sourceError;
      reason = network != null
          ? t(LibrarySourcesLocale.networkKey(network))
          : source != null
          ? t(LibrarySourcesLocale.sourceErrorKey(source))
          : null;
      detail = <String>[
        ?result.errorKind,
        if (result.statusCode != null) 'HTTP ${result.statusCode}',
        ?result.detail,
      ].join(' – ');
    }
    // Each step takes the focus so a controller can scroll back to it.
    return LibraryFocusRing(
      key: ValueKey<String>('health-step-${step.name}'),
      radius: 6,
      child: Focus(
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 4),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              SizedBox(width: 28, child: Center(child: leading)),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: <Widget>[
                    Text(
                      t(LibrarySourcesLocale.healthStepKey(step)),
                      style: theme.textTheme.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                    Text(
                      result != null && result.durationMs > 0
                          ? '$status (${result.durationMs} ms)'
                          : status,
                      style: theme.textTheme.bodySmall,
                    ),
                    if (reason != null) Text(reason),
                    if (detail != null && detail.isNotEmpty)
                      LibraryTechnicalDetails(detail: detail),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
