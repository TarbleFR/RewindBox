import 'dart:async';
import 'dart:isolate';

import 'package:external_folder_access/external_folder_access.dart';
import 'package:file_picker/file_picker.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:path/path.dart' as p;

import '../../l10n/libretro_locale.dart';
import '../../services/libretro_3ds_language.dart';
import '../../services/libretro_3ds_system_data_service.dart';
import '../../services/libretro_core_catalog.dart';
import '../../services/libretro_core_option_store.dart';
import '../../services/logger_service.dart';
import '../../widgets/confirm_action_dialog.dart';
import 'libretro_library_actions.dart' show libretroLibraryLocation;
import 'libretro_skin_manager_screen.dart';

/// Picks a ZIP archive or individual files; the chosen paths, null when the
/// user backed out.
typedef Libretro3dsFilePicker = Future<List<String>?> Function();

/// Picks a folder; its path, null when the user backed out.
typedef Libretro3dsFolderPicker = Future<String?> Function();

/// Turns the chosen sources into an import plan.
typedef Libretro3dsAnalyzer =
    Future<Libretro3dsImportPlan> Function(List<String> sources);

/// Emulators tab of the Nintendo 3DS › "System settings" (Build 447,
/// docs/libretro-3ds-system-settings.md § 3.4).
///
/// System: the language, region and model of the emulated console, read
/// from and written to `Config/Azahar.json` through [LibretroCoreOptionStore]
/// (one file per core, no per-game scope). The language entry "Automatic"
/// is the absence of a stored value: the launch then hands the core the
/// language matching NeoStation's ([Libretro3dsLanguage]). The core applies
/// the language only while the region is Auto, hence the warning and the
/// "back to Auto" button when a fixed region is chosen.
///
/// System data: a read-only inventory of the core's user directory
/// (`Saves/Azahar/Azahar`: keys, seed database, CFG save, NAND titles,
/// region fonts, console-unique files), an import assistant (ZIP, folder
/// or individual files, analyzed into a plan the user confirms, installed
/// with per-file backups) and the restore of the last backup, all through
/// [Libretro3dsSystemDataService]. Every write is refused while a game runs.
///
/// Raw values (core option values, file paths, title ids, technical codes)
/// are shown as they are, under translated labels.
class Libretro3dsSystemScreen extends StatefulWidget {
  const Libretro3dsSystemScreen({
    super.key,
    this.store,
    this.dataService,
    this.languageNames = const <String, String>{},
    this.pickFiles,
    this.pickFolder,
    this.analyze,
  });

  /// Option store (tests); the app's own by default.
  final LibretroCoreOptionStore? store;

  /// System data service (tests); the app's own by default.
  final Libretro3dsSystemDataService? dataService;

  /// NeoStation's languages by catalog key, each named in itself (the
  /// app's own language list). Names the current language in the
  /// "Automatic" entry; without it the console's label of the matching
  /// language is used.
  final Map<String, String> languageNames;

  /// File picker (tests); the Files app picker by default.
  final Libretro3dsFilePicker? pickFiles;

  /// Folder picker (tests); the Files app folder picker by default.
  final Libretro3dsFolderPicker? pickFolder;

  /// Analysis (tests); [Libretro3dsSystemDataService.analyzeSources] in a
  /// separate isolate by default.
  final Libretro3dsAnalyzer? analyze;

  @override
  State<Libretro3dsSystemScreen> createState() =>
      _Libretro3dsSystemScreenState();
}

/// Outcome of a choice dialog: null when the user backed out, else the
/// chosen core value (null value = the "Automatic" entry).
class _Choice {
  const _Choice(this.value);

  final String? value;
}

class _Libretro3dsSystemScreenState extends State<Libretro3dsSystemScreen>
    with LibretroPageNavigation<Libretro3dsSystemScreen>, WidgetsBindingObserver {
  static final _log = LoggerService.instance;

  /// Bookmark key of the folder picked for an import.
  static const String _folderAccessKey = 'libretro-3ds-import';

  static const String _languageKey = 'citra_language_value';
  static const String _regionKey = 'citra_region_value';
  static const String _modelKey = 'citra_is_new_3ds';
  static const String _autoRegion = 'Auto';

  late final LibretroCoreOptionStore _store =
      widget.store ?? LibretroCoreOptionStore();
  late final Libretro3dsSystemDataService _data =
      widget.dataService ?? Libretro3dsSystemDataService();
  late final LibretroCore _core = LibretroCoreCatalog.cores['azahar']!;

  Map<String, String>? _options;
  Libretro3dsInventory? _inventory;
  bool _hasBackup = false;
  Object? _loadError;
  bool _loading = false;
  bool _loadAgain = false;

  /// A write, an import or a restore runs. The controls stay enabled
  /// meanwhile (their handlers return early): disabling the focused one
  /// while a dialog route is still leaving makes Flutter hand the focus
  /// to the route underneath, out of the controller's reach.
  bool _busy = false;

  /// The last write was refused because a game runs (or the session state
  /// is unknown).
  bool _sessionActive = false;

  /// Raw detail of the last failed write, import or restore.
  Object? _actionError;

  String _t(String key) => LibretroLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      LibretroLocale.formatContext(context, key, values);

  LibretroCuratedSetting _setting(String key) =>
      _core.settings.firstWhere((setting) => setting.key == key);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_reload());
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Files may have been added in the Files app, or a game may have ended
    // and stored its own choices meanwhile.
    if (state == AppLifecycleState.resumed && !_busy) unawaited(_reload());
  }

  /// Reads the stored options, the inventory and the backups; a request
  /// made while one runs is honoured once it ends.
  Future<void> _reload() async {
    if (_loading) {
      _loadAgain = true;
      return;
    }
    _loading = true;
    try {
      do {
        _loadAgain = false;
        try {
          final options = await _store.read(
            LibretroCoreOptionStore.azaharLibraryName,
          );
          final inventory = await _data.inventory();
          final backups = await _data.backups();
          if (!mounted) return;
          setState(() {
            _options = options;
            _inventory = inventory;
            _hasBackup = backups.isNotEmpty;
            _loadError = null;
          });
        } catch (error, stackTrace) {
          _log.e(
            'Nintendo 3DS page load failed',
            error: error,
            stackTrace: stackTrace,
          );
          if (!mounted) return;
          setState(() => _loadError = error);
        }
      } while (_loadAgain && mounted);
    } finally {
      _loading = false;
    }
  }

  void _notice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  // ------------------------------------------------------------ system

  /// Writes [changes] to `Config/Azahar.json`, then shows what the file
  /// holds after a fresh read: a refused write is never shown as saved.
  Future<void> _write(Map<String, String?> changes) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _sessionActive = false;
      _actionError = null;
    });
    try {
      await _store.write(LibretroCoreOptionStore.azaharLibraryName, changes);
      final stored = await _store.read(
        LibretroCoreOptionStore.azaharLibraryName,
      );
      if (!mounted) return;
      setState(() => _options = stored);
      _notice(_t('system3dsSaved'));
    } on LibretroCoreOptionStoreException catch (error) {
      _log.w('Nintendo 3DS option write refused: $error');
      if (!mounted) return;
      setState(() => _sessionActive = true);
    } catch (error, stackTrace) {
      _log.e(
        'Nintendo 3DS option write failed',
        error: error,
        stackTrace: stackTrace,
      );
      if (!mounted) return;
      setState(() => _actionError = error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  /// Name of NeoStation's current language for the "Automatic" entry.
  String _appLanguageName(Locale locale) {
    final own = widget.languageNames[LibretroLocale.localeKey(locale)];
    if (own != null) return own;
    // Without the app's list: the console's label of the matching language
    // is the UI language's own name; the fallback language has no label on
    // the console, so only its catalog key is left.
    if (Libretro3dsLanguage.isFallback(locale)) {
      return LibretroLocale.localeKey(locale);
    }
    final label = Libretro3dsLanguage.labelKeyFor(
      Libretro3dsLanguage.forAppLocale(locale),
    );
    return label == null ? Libretro3dsLanguage.fallback : _t(label);
  }

  /// Translated label of a core value; the raw value when the catalog has
  /// no label for it (a value stored by another version of the core).
  String _valueLabel(LibretroCuratedSetting setting, String value) {
    final key = setting.valueLabelKeys[value];
    return key == null ? value : _t(key);
  }

  /// What a selector shows for its stored value (absent = the core's own
  /// default, the first value; absent language = "Automatic").
  String _currentLabel(LibretroCuratedSetting setting) {
    final stored = _options?[setting.key];
    if (setting.key == _languageKey && stored == null) {
      final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
      return _f('lang3dsAutomatic', {'language': _appLanguageName(locale)});
    }
    return _valueLabel(setting, stored ?? setting.values.first);
  }

  Future<void> _choose(LibretroCuratedSetting setting) async {
    if (_busy) return;
    final automatic = setting.key == _languageKey;
    final stored = _options?[setting.key];
    final current = automatic ? stored : (stored ?? setting.values.first);
    final choice = await showDialog<_Choice>(
      context: context,
      builder: (_) => _ChoiceDialog(
        title: _t(setting.labelKey),
        options: <(String?, String)>[
          if (automatic) (null, _currentLabelFor(setting, null)),
          for (final value in setting.values) (value, _valueLabel(setting, value)),
        ],
        current: current,
      ),
    );
    if (choice == null || !mounted) return;
    if (choice.value == current) return;
    await _write({setting.key: choice.value});
  }

  /// Label of [value] for the choice dialog (the "Automatic" entry names the
  /// current app language like the selector does).
  String _currentLabelFor(LibretroCuratedSetting setting, String? value) {
    if (value == null) {
      final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
      return _f('lang3dsAutomatic', {'language': _appLanguageName(locale)});
    }
    return _valueLabel(setting, value);
  }

  // ------------------------------------------------------- system data

  Future<List<String>?> _pickFiles() async {
    if (widget.pickFiles != null) return widget.pickFiles!();
    final selection = await FilePicker.pickFiles(
      type: FileType.any,
      allowMultiple: true,
      withData: false,
      lockParentWindow: true,
    );
    if (selection == null) return null;
    return <String>[
      for (final file in selection.files)
        if (file.path != null) file.path!,
    ];
  }

  Future<String?> _pickFolder() async {
    if (widget.pickFolder != null) return widget.pickFolder!();
    return ExternalFolderAccess.pickAndActivateFolder(key: _folderAccessKey);
  }

  /// Analyzes off the UI isolate: a GodMode9 dump holds thousands of files.
  Future<Libretro3dsImportPlan> _analyze(List<String> sources) async {
    if (widget.analyze != null) return widget.analyze!(sources);
    final userDirectory = (await _data.userDirectory()).path;
    final limits = _data.limits;
    return Isolate.run(
      () => Libretro3dsSystemDataService.analyzeSources(
        sources,
        userDirectory: userDirectory,
        limits: limits,
      ),
    );
  }

  /// Import assistant: source, analysis, plan and confirmation,
  /// installation, result.
  Future<void> _import() async {
    if (_busy) return;
    final source = await showDialog<_ImportSource>(
      context: context,
      builder: (_) => _SourceDialog(
        title: _t('system3dsImport'),
        labels: {
          _ImportSource.zip: _t('system3dsImportZip'),
          _ImportSource.folder: _t('system3dsImportFolder'),
          _ImportSource.files: _t('system3dsImportFiles'),
        },
      ),
    );
    if (source == null || !mounted) return;

    List<String>? sources;
    pausePageNavigation();
    try {
      switch (source) {
        case _ImportSource.zip:
        case _ImportSource.files:
          sources = await _pickFiles();
        case _ImportSource.folder:
          final folder = await _pickFolder();
          sources = folder == null ? null : <String>[folder];
      }
    } catch (error, stackTrace) {
      _log.e('Nintendo 3DS import picker failed', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _actionError = error);
      return;
    } finally {
      resumePageNavigation();
    }
    if (sources == null || sources.isEmpty || !mounted) return;
    final chosen = sources;

    setState(() {
      _busy = true;
      _sessionActive = false;
      _actionError = null;
    });
    try {
      final plan = await _withProgress(
        _t('system3dsAnalyzing'),
        () => _analyze(chosen),
      );
      if (!mounted) return;
      final decision = await showDialog<_PlanDecision>(
        context: context,
        builder: (_) => _PlanDialog(plan: plan, page: this),
      );
      if (decision == null || !mounted) return;
      final report = await _withProgress(
        _t('system3dsInstalling'),
        () => _data.install(
          plan,
          includeConsoleUnique: decision.includeConsoleUnique,
          includeKeys: decision.includeKeys,
        ),
      );
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (_) => _ResultDialog(report: report, page: this),
      );
    } on Libretro3dsSystemDataException catch (error) {
      _log.w('Nintendo 3DS import refused: $error');
      if (!mounted) return;
      setState(() => _sessionActive = true);
    } catch (error, stackTrace) {
      _log.e('Nintendo 3DS import failed', error: error, stackTrace: stackTrace);
      if (!mounted) return;
      setState(() => _actionError = error);
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        await _reload();
      }
    }
  }

  /// Runs [work] behind a progress dialog that B cannot close; the dialog
  /// closes when the work ends. Errors propagate to the caller.
  Future<T> _withProgress<T>(String label, Future<T> Function() work) async {
    final navigator = Navigator.of(context);
    unawaited(
      showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (_) => _ProgressDialog(label: label),
      ),
    );
    try {
      return await work();
    } finally {
      if (mounted && navigator.canPop()) navigator.pop();
    }
  }

  Future<void> _restore() async {
    if (_busy) return;
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: _t('system3dsRestoreBackup'),
      body: _t('system3dsPlanReplace'),
      confirmLabel: _t('system3dsRestoreBackup'),
      cancelLabel: _t('cancel'),
      icon: Icons.settings_backup_restore_rounded,
      accentColor: Theme.of(context).colorScheme.primary,
    );
    if (!confirmed || !mounted) return;
    setState(() {
      _busy = true;
      _sessionActive = false;
      _actionError = null;
    });
    try {
      final report = await _data.restoreLastBackup();
      if (!mounted) return;
      if (report.failedCount == 0) {
        _notice(_t('system3dsRestored'));
      } else {
        setState(() => _actionError = report.results
            .firstWhere((result) => !result.restored)
            .technicalDetail);
      }
    } on Libretro3dsSystemDataException catch (error) {
      _log.w('Nintendo 3DS restore refused: $error');
      if (!mounted) return;
      switch (error.error) {
        case Libretro3dsSystemDataError.sessionActive:
          setState(() => _sessionActive = true);
        case Libretro3dsSystemDataError.noBackup:
          _notice(_t('system3dsNoBackup'));
      }
    } catch (error, stackTrace) {
      _log.e('Nintendo 3DS restore failed', error: error, stackTrace: stackTrace);
      if (!mounted) return;
      setState(() => _actionError = error);
    } finally {
      if (mounted) {
        setState(() => _busy = false);
        await _reload();
      }
    }
  }

  // ------------------------------------------------------------- texts

  String _rejection(Libretro3dsRejection? rejection) => switch (rejection) {
        Libretro3dsRejection.rawNandImage => _t('system3dsRejectedRawNand'),
        Libretro3dsRejection.unsupportedArchive => _t('system3dsRejectedArchive'),
        Libretro3dsRejection.tooManyEntries ||
        Libretro3dsRejection.tooLarge ||
        Libretro3dsRejection.fileTooLarge =>
          _t('system3dsRejectedTooLarge'),
        Libretro3dsRejection.unsafeEntry ||
        Libretro3dsRejection.symbolicLink =>
          _t('system3dsRejectedUnsafe'),
        Libretro3dsRejection.invalid || null => _t('system3dsRejectedInvalid'),
      };

  String _technical(Object? code) =>
      _f('system3dsTechnicalCode', {'code': code});

  /// Decimal units as the other catalogs print them ("MB").
  static String _formatBytes(int bytes) {
    if (bytes < 1000) return '$bytes B';
    const units = <String>['KB', 'MB', 'GB', 'TB'];
    var value = bytes.toDouble();
    var unit = -1;
    while (value >= 1000 && unit < units.length - 1) {
      value /= 1000;
      unit++;
    }
    final digits = value >= 100 ? 0 : value >= 10 ? 1 : 2;
    return '${value.toStringAsFixed(digits)} ${units[unit]}';
  }

  String _presence(bool present, [int size = 0]) => present
      ? '${_t('system3dsPresent')} · ${_formatBytes(size)}'
      : _t('system3dsAbsent');

  // ------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    return libretroPage(Scaffold(
      appBar: libretroPageAppBar(context, _t('system3dsTitle')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 860),
            // Every card is built (no lazy list), so the D-pad can always
            // reach the next one.
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  if (_sessionActive)
                    _NoteLine(
                      key: const ValueKey('3ds-session-error'),
                      icon: Icons.error_outline_rounded,
                      color: scheme.error,
                      text: _t('system3dsSessionActive'),
                      padding: const EdgeInsets.only(bottom: 12),
                    ),
                  if (_actionError != null)
                    _NoteLine(
                      key: const ValueKey('3ds-action-error'),
                      icon: Icons.error_outline_rounded,
                      color: scheme.error,
                      text: '${_t('system3dsFailed')} — ${_technical(_actionError)}',
                      padding: const EdgeInsets.only(bottom: 12),
                    ),
                  if (_loadError != null)
                    _NoteLine(
                      key: const ValueKey('3ds-load-error'),
                      icon: Icons.error_outline_rounded,
                      color: scheme.error,
                      text: _technical(_loadError),
                      padding: const EdgeInsets.only(bottom: 12),
                    ),
                  _buildSystem(context),
                  _buildData(context),
                ],
              ),
            ),
          ),
        ),
      ),
    ));
  }

  Widget _buildSystem(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    final region = _options?[_regionKey];
    final regionFixed = region != null && region != _autoRegion;
    final languageAutomatic = _options?[_languageKey] == null;
    return Card(
      key: const ValueKey('3ds-system-card'),
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.language_rounded, color: scheme.primary),
                const SizedBox(width: 12),
                Expanded(child: Text(_t('engine3dsSystem'), style: theme.textTheme.titleMedium)),
                if ((_options == null && _loadError == null) || _busy)
                  const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
            const SizedBox(height: 10),
            _selector(_setting(_languageKey), 'language'),
            if (languageAutomatic && Libretro3dsLanguage.isFallback(locale))
              _NoteLine(
                key: const ValueKey('3ds-language-fallback'),
                icon: Icons.info_outline_rounded,
                color: scheme.onSurfaceVariant,
                text: _f('lang3dsFallback', {'language': _appLanguageName(locale)}),
                padding: const EdgeInsets.only(bottom: 8),
              ),
            _selector(_setting(_regionKey), 'region'),
            if (regionFixed) ...[
              _NoteLine(
                key: const ValueKey('3ds-language-ignored'),
                icon: Icons.warning_amber_rounded,
                color: Colors.amber.shade800,
                text: _t('system3dsLanguageIgnored'),
              ),
              Padding(
                padding: const EdgeInsets.fromLTRB(0, 6, 0, 10),
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: LibretroFocusRing(
                    child: FilledButton.tonalIcon(
                      key: const ValueKey('3ds-use-auto-region'),
                      onPressed: () => unawaited(_write({_regionKey: _autoRegion})),
                      icon: const Icon(Icons.undo_rounded),
                      label: Text(_t('system3dsUseAutoRegion')),
                    ),
                  ),
                ),
              ),
            ],
            _selector(_setting(_modelKey), 'model'),
            const SizedBox(height: 4),
            _NoteLine(
              icon: Icons.restart_alt_rounded,
              color: scheme.onSurfaceVariant,
              text: _t('system3dsRestartHint'),
            ),
            const SizedBox(height: 6),
            _NoteLine(
              icon: Icons.info_outline_rounded,
              color: scheme.onSurfaceVariant,
              text: _t('system3dsLanguageAdjusted'),
            ),
            const SizedBox(height: 6),
            _NoteLine(
              icon: Icons.info_outline_rounded,
              color: scheme.onSurfaceVariant,
              text: _t('system3dsSavestateRegion'),
            ),
          ],
        ),
      ),
    );
  }

  /// A setting row: translated label, current value label and the raw
  /// stored value; a press opens the choice dialog.
  Widget _selector(LibretroCuratedSetting setting, String id) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final stored = _options?[setting.key];
    // The raw stored pair, as Config/Azahar.json holds it.
    final rawValue = '${setting.key} = $stored';
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: LibretroFocusRing(
        radius: 14,
        child: OutlinedButton(
          key: ValueKey('3ds-setting-$id'),
          style: OutlinedButton.styleFrom(
            padding: const EdgeInsets.fromLTRB(16, 10, 12, 10),
            alignment: Alignment.centerLeft,
          ),
          onPressed: _options == null ? null : () => unawaited(_choose(setting)),
          child: Row(
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(_t(setting.labelKey), style: theme.textTheme.labelLarge),
                    const SizedBox(height: 2),
                    Text(
                      _options == null ? '' : _currentLabel(setting),
                      key: ValueKey('3ds-setting-$id-value'),
                      style: theme.textTheme.bodyMedium?.copyWith(color: scheme.onSurface),
                    ),
                    if (stored != null)
                      Text(
                        rawValue,
                        style: theme.textTheme.bodySmall?.copyWith(
                          fontFamily: 'monospace',
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                  ],
                ),
              ),
              Icon(Icons.chevron_right_rounded, color: scheme.onSurfaceVariant),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildData(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final inventory = _inventory;
    return Card(
      key: const ValueKey('3ds-data-card'),
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.sd_card_outlined, color: scheme.primary),
                const SizedBox(width: 12),
                Expanded(child: Text(_t('system3dsDataTitle'), style: theme.textTheme.titleMedium)),
                if ((inventory == null && _loadError == null) || _busy)
                  const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
            if (inventory != null) ...[
              const SizedBox(height: 4),
              SelectableText(
                libretroLibraryLocation(inventory.userDirectory),
                key: const ValueKey('3ds-user-directory'),
                style: theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace', color: scheme.onSurfaceVariant),
              ),
              const SizedBox(height: 8),
              _InventoryRow(
                id: 'keys',
                title: _t('system3dsKeys'),
                paths: const [Libretro3dsSystemDataService.keysTarget],
                status: _presence(inventory.keys.exists, inventory.keys.size),
                present: inventory.keys.exists,
                optional: true,
                note: _t('system3dsKeysOptional'),
              ),
              _InventoryRow(
                id: 'seeddb',
                title: _t('system3dsSeeddb'),
                paths: const [Libretro3dsSystemDataService.seeddbTarget],
                status: _presence(inventory.seeddb.exists, inventory.seeddb.size),
                present: inventory.seeddb.exists,
              ),
              _InventoryRow(
                id: 'config',
                title: _t('system3dsConfig'),
                paths: const [Libretro3dsSystemDataService.configTarget],
                status: _presence(inventory.config.exists, inventory.config.size),
                present: inventory.config.exists,
              ),
              _InventoryRow(
                id: 'titles',
                title: _f('system3dsTitles', {
                  'count': inventory.titleCount,
                  'size': _formatBytes(inventory.titleBytes),
                }),
                paths: const [Libretro3dsSystemDataService.titleRoot],
                status: inventory.titleCount > 0
                    ? '${_t('system3dsPresent')} · ${inventory.titleFileCount}'
                    : _t('system3dsAbsent'),
                present: inventory.titleCount > 0,
              ),
              _InventoryRow(
                id: 'fonts',
                title: _t('system3dsFonts'),
                paths: [
                  for (final font in Libretro3dsRegionFont.values)
                    '${Libretro3dsSystemDataService.titleRoot}/0004009b/${font.titleLow}'
                    ' — ${inventory.fonts[font] ?? false ? _t('system3dsPresent') : _t('system3dsAbsent')}',
                ],
                status: inventory.allFontsPresent ? _t('system3dsPresent') : _t('system3dsAbsent'),
                present: inventory.allFontsPresent,
                optional: true,
                note: inventory.allFontsPresent ? null : _t('system3dsFontsMissing'),
              ),
              _InventoryRow(
                id: 'console',
                title: _t('system3dsConsoleData'),
                paths: [
                  for (final file in inventory.consoleUnique)
                    '${file.relativePath} — ${_presence(file.exists, file.size)}',
                ],
                status: inventory.anyConsoleUnique ? _t('system3dsPresent') : _t('system3dsAbsent'),
                present: inventory.anyConsoleUnique,
                optional: true,
              ),
            ],
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                LibretroFocusRing(
                  child: FilledButton.tonalIcon(
                    key: const ValueKey('3ds-import'),
                    onPressed: inventory == null ? null : () => unawaited(_import()),
                    icon: const Icon(Icons.drive_folder_upload_outlined),
                    label: Text(_t('system3dsImport')),
                  ),
                ),
                LibretroFocusRing(
                  child: OutlinedButton.icon(
                    key: const ValueKey('3ds-restore-backup'),
                    onPressed: inventory == null || !_hasBackup ? null : () => unawaited(_restore()),
                    icon: const Icon(Icons.settings_backup_restore_rounded),
                    label: Text(_t('system3dsRestoreBackup')),
                  ),
                ),
              ],
            ),
            if (inventory != null && !_hasBackup) ...[
              const SizedBox(height: 6),
              Text(
                _t('system3dsNoBackup'),
                key: const ValueKey('3ds-no-backup'),
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
            const SizedBox(height: 10),
            _NoteLine(
              icon: Icons.info_outline_rounded,
              color: scheme.onSurfaceVariant,
              text: _t('system3dsNoDistribution'),
            ),
          ],
        ),
      ),
    );
  }
}

/// Same keyboard rules as [LibretroPageNavigation.libretroPage] for the
/// dialogs shown above the page: only the page's navigation layer answers
/// Enter and the arrows, so a key never acts twice (and never pops twice).
Widget _dialogShell(Widget child) => Shortcuts(
      shortcuts: const <ShortcutActivator, Intent>{
        SingleActivator(LogicalKeyboardKey.enter): DoNothingAndStopPropagationIntent(),
        SingleActivator(LogicalKeyboardKey.numpadEnter): DoNothingAndStopPropagationIntent(),
      },
      child: Actions(
        actions: <Type, Action<Intent>>{DirectionalFocusIntent: DoNothingAction()},
        child: child,
      ),
    );

/// One choice per option, the current one focused first so the D-pad
/// starts there; A (or a tap) returns the choice, B returns nothing.
class _ChoiceDialog extends StatelessWidget {
  const _ChoiceDialog({required this.title, required this.options, required this.current});

  final String title;

  /// (core value or null for "Automatic", label).
  final List<(String?, String)> options;
  final String? current;

  @override
  Widget build(BuildContext context) => _dialogShell(AlertDialog(
        title: Text(title),
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        content: SizedBox(
          width: 420,
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                for (final (value, label) in options)
                  LibretroFocusRing(
                    radius: 8,
                    child: ListTile(
                      key: ValueKey('3ds-choice-${value ?? 'auto'}'),
                      autofocus: value == current,
                      selected: value == current,
                      leading: Icon(
                        value == current ? Icons.radio_button_checked_rounded : Icons.radio_button_off_rounded,
                      ),
                      title: Text(label),
                      subtitle: value == null
                          ? null
                          : Text(value, style: const TextStyle(fontFamily: 'monospace')),
                      onTap: () => Navigator.of(context).pop(_Choice(value)),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ));
}

enum _ImportSource { zip, folder, files }

/// Step 1 of the import assistant: where the files come from.
class _SourceDialog extends StatelessWidget {
  const _SourceDialog({required this.title, required this.labels});

  final String title;
  final Map<_ImportSource, String> labels;

  @override
  Widget build(BuildContext context) => _dialogShell(AlertDialog(
        title: Text(title),
        contentPadding: const EdgeInsets.symmetric(vertical: 12),
        content: SizedBox(
          width: 420,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              for (final source in _ImportSource.values)
                LibretroFocusRing(
                  radius: 8,
                  child: ListTile(
                    key: ValueKey('3ds-import-${source.name}'),
                    autofocus: source == _ImportSource.zip,
                    leading: Icon(switch (source) {
                      _ImportSource.zip => Icons.folder_zip_outlined,
                      _ImportSource.folder => Icons.folder_open_outlined,
                      _ImportSource.files => Icons.description_outlined,
                    }),
                    title: Text(labels[source]!),
                    onTap: () => Navigator.of(context).pop(source),
                  ),
                ),
            ],
          ),
        ),
      ));
}

/// Analysis or installation in progress; the page closes it when the work
/// ends, and nothing else can.
class _ProgressDialog extends StatelessWidget {
  const _ProgressDialog({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) => PopScope(
        canPop: false,
        child: AlertDialog(
          key: const ValueKey('3ds-progress'),
          content: Row(
            children: [
              const SizedBox(width: 24, height: 24, child: CircularProgressIndicator(strokeWidth: 2)),
              const SizedBox(width: 16),
              Expanded(child: Text(label)),
            ],
          ),
        ),
      );
}

class _PlanDecision {
  const _PlanDecision({required this.includeConsoleUnique, required this.includeKeys});

  final bool includeConsoleUnique;
  final bool includeKeys;
}

/// Steps 2 and 3: the plan (added, replaced, identical, ignored, refused),
/// the two opt-in boxes (console-unique data, keys) unchecked by default,
/// and the confirmation.
class _PlanDialog extends StatefulWidget {
  const _PlanDialog({required this.plan, required this.page});

  final Libretro3dsImportPlan plan;
  final _Libretro3dsSystemScreenState page;

  @override
  State<_PlanDialog> createState() => _PlanDialogState();
}

class _PlanDialogState extends State<_PlanDialog> {
  bool _includeConsole = false;
  bool _includeKeys = false;

  Libretro3dsImportPlan get _plan => widget.plan;
  _Libretro3dsSystemScreenState get _page => widget.page;

  bool get _hasConsoleUnique =>
      _plan.installable.any((item) => item.kind == Libretro3dsItemKind.consoleUnique);
  bool get _hasKeys => _plan.installable.any((item) => item.kind == Libretro3dsItemKind.keys);

  /// Elements an install would write with the boxes as they are.
  int get _selected => _plan.installable.where((item) => switch (item.kind) {
        Libretro3dsItemKind.consoleUnique => _includeConsole,
        Libretro3dsItemKind.keys => _includeKeys,
        _ => true,
      }).length;

  /// Raw destination (or source entry) and size of one element.
  static String _line(Libretro3dsImportItem item) {
    final name = item.relativeTarget ?? item.sourceEntry;
    if (item.kind == Libretro3dsItemKind.rejected) return name;
    return '$name · ${_Libretro3dsSystemScreenState._formatBytes(item.size)}';
  }

  Widget _group(BuildContext context, String key, String label, Iterable<Libretro3dsImportItem> items,
      {bool rejected = false}) {
    if (items.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final mono = theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace');
    return Padding(
      key: ValueKey('3ds-plan-$key'),
      padding: const EdgeInsets.only(bottom: 8),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: theme.textTheme.labelLarge?.copyWith(color: rejected ? scheme.error : null)),
          for (final item in items) ...[
            Text(_line(item), style: mono),
            if (item.kind == Libretro3dsItemKind.consoleUnique)
              Text(_page._t('system3dsConsoleData'), style: theme.textTheme.bodySmall),
            if (item.kind == Libretro3dsItemKind.keys)
              Text(_page._t('system3dsKeys'), style: theme.textTheme.bodySmall),
            if (rejected) ...[
              Text(_page._rejection(item.rejection), style: theme.textTheme.bodySmall),
              if (item.technicalDetail != null)
                Text(_page._technical(item.technicalDetail), style: mono),
            ],
          ],
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final plan = _plan;
    final nothing = !plan.hasRecognized;
    // "Install these files (3)": how many the boxes currently select.
    final confirmLabel = '${_page._t('system3dsConfirm')} ($_selected)';
    return _dialogShell(AlertDialog(
      title: Text(_page._t('system3dsImport')),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (nothing)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    _page._t('system3dsNothingRecognized'),
                    key: const ValueKey('3ds-plan-nothing'),
                    style: theme.textTheme.bodyMedium?.copyWith(color: scheme.error),
                  ),
                ),
              _group(context, 'create', _page._t('system3dsPlanCreate'),
                  plan.recognized.where((item) => item.action == Libretro3dsPlanAction.create)),
              _group(context, 'replace', _page._t('system3dsPlanReplace'),
                  plan.recognized.where((item) => item.action == Libretro3dsPlanAction.replace)),
              _group(context, 'identical', _page._t('system3dsPlanIdentical'),
                  plan.recognized.where((item) => item.action == Libretro3dsPlanAction.skipIdentical)),
              _group(context, 'ignored', _page._t('system3dsPlanIgnored'), plan.ignored),
              _group(context, 'rejected', _page._t('system3dsFailed'), plan.rejected, rejected: true),
              if (!nothing) ...[
                LibretroFocusRing(
                  radius: 8,
                  child: CheckboxListTile(
                    key: const ValueKey('3ds-include-console'),
                    value: _includeConsole,
                    onChanged: _hasConsoleUnique ? (value) => setState(() => _includeConsole = value ?? false) : null,
                    controlAffinity: ListTileControlAffinity.leading,
                    contentPadding: EdgeInsets.zero,
                    title: Text(_page._t('system3dsIncludeConsoleData')),
                    subtitle: Text(_page._t('system3dsIncludeConsoleDataHelp')),
                  ),
                ),
                LibretroFocusRing(
                  radius: 8,
                  child: CheckboxListTile(
                    key: const ValueKey('3ds-include-keys'),
                    value: _includeKeys,
                    onChanged: _hasKeys ? (value) => setState(() => _includeKeys = value ?? false) : null,
                    controlAffinity: ListTileControlAffinity.leading,
                    contentPadding: EdgeInsets.zero,
                    title: Text(_page._t('system3dsIncludeKeys')),
                    subtitle: Text(_page._t('system3dsIncludeKeysHelp')),
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
      actions: [
        LibretroFocusRing(
          child: TextButton(
            key: const ValueKey('3ds-import-cancel'),
            autofocus: nothing,
            onPressed: () => Navigator.of(context).pop(),
            child: Text(_page._t('cancel')),
          ),
        ),
        if (!nothing)
          LibretroFocusRing(
            child: FilledButton(
              key: const ValueKey('3ds-import-confirm'),
              autofocus: true,
              onPressed: _selected == 0
                  ? null
                  : () => Navigator.of(context).pop(
                        _PlanDecision(includeConsoleUnique: _includeConsole, includeKeys: _includeKeys),
                      ),
              child: Text(confirmLabel),
            ),
          ),
      ],
    ));
  }
}

/// Step 5: what happened to each element, the backup folder of the
/// replaced files and the raw code of any failure.
class _ResultDialog extends StatelessWidget {
  const _ResultDialog({required this.report, required this.page});

  final Libretro3dsInstallReport report;
  final _Libretro3dsSystemScreenState page;

  String _status(Libretro3dsInstallResult result) {
    final backupRoot = report.backupDirectory == null ? null : p.dirname(report.backupDirectory!);
    return switch (result.status) {
      Libretro3dsInstallStatus.installed => page._t('system3dsInstalled'),
      Libretro3dsInstallStatus.replaced => page._f('system3dsReplaced', {
          'backup': result.backupPath == null || backupRoot == null
              ? ''
              : p.relative(result.backupPath!, from: backupRoot),
        }),
      Libretro3dsInstallStatus.skippedIdentical ||
      Libretro3dsInstallStatus.excluded ||
      Libretro3dsInstallStatus.ignored =>
        page._t('system3dsSkipped'),
      Libretro3dsInstallStatus.rejected => page._rejection(result.item.rejection),
      Libretro3dsInstallStatus.failed ||
      Libretro3dsInstallStatus.rolledBack ||
      Libretro3dsInstallStatus.notAttempted =>
        page._t('system3dsFailed'),
    };
  }

  bool _failed(Libretro3dsInstallStatus status) =>
      status == Libretro3dsInstallStatus.failed ||
      status == Libretro3dsInstallStatus.rolledBack ||
      status == Libretro3dsInstallStatus.notAttempted;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final mono = theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace');
    final shown = report.results.where((result) => result.status != Libretro3dsInstallStatus.ignored);
    return _dialogShell(AlertDialog(
      title: Text(page._t(report.succeeded ? 'system3dsInstalled' : 'system3dsFailed')),
      content: SizedBox(
        width: 560,
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              if (report.failure != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    page._technical(report.failure),
                    key: const ValueKey('3ds-result-failure'),
                    style: mono?.copyWith(color: scheme.error),
                  ),
                ),
              if (report.backupDirectory != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: SelectableText(
                    libretroLibraryLocation(report.backupDirectory!),
                    key: const ValueKey('3ds-result-backup'),
                    style: mono,
                  ),
                ),
              for (final result in shown) ...[
                Text(
                  result.item.relativeTarget ?? result.item.sourceEntry,
                  key: ValueKey('3ds-result-${result.item.relativeTarget ?? result.item.sourceEntry}'),
                  style: mono,
                ),
                Text(
                  _status(result),
                  style: theme.textTheme.bodySmall?.copyWith(
                    color: _failed(result.status) ? scheme.error : null,
                  ),
                ),
                if (_failed(result.status))
                  Text(
                    page._technical('${result.status.name}: ${result.technicalDetail ?? ''}'),
                    style: mono?.copyWith(color: scheme.error),
                  ),
                const SizedBox(height: 6),
              ],
            ],
          ),
        ),
      ),
      actions: [
        LibretroFocusRing(
          child: FilledButton(
            key: const ValueKey('3ds-import-close'),
            autofocus: true,
            onPressed: () => Navigator.of(context).pop(),
            child: Text(page._t('controlsEditDone')),
          ),
        ),
      ],
    ));
  }
}

/// One line of the inventory: translated title, raw paths, status.
class _InventoryRow extends StatelessWidget {
  const _InventoryRow({
    required this.id,
    required this.title,
    required this.paths,
    required this.status,
    required this.present,
    this.optional = false,
    this.note,
  });

  final String id;
  final String title;
  final List<String> paths;
  final String status;
  final bool present;
  final bool optional;
  final String? note;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final color = present
        ? Colors.green.shade600
        : optional
            ? scheme.onSurfaceVariant
            : Colors.amber.shade800;
    return Container(
      key: ValueKey('3ds-inventory-$id'),
      margin: const EdgeInsets.only(top: 8),
      padding: const EdgeInsets.fromLTRB(12, 8, 12, 8),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: Text(title, style: theme.textTheme.titleSmall)),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                decoration: BoxDecoration(
                  color: color.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      present ? Icons.check_circle_rounded : Icons.remove_circle_outline_rounded,
                      size: 16,
                      color: color,
                    ),
                    const SizedBox(width: 4),
                    Flexible(
                      child: Text(
                        status,
                        key: ValueKey('3ds-inventory-$id-status'),
                        style: theme.textTheme.labelMedium?.copyWith(color: color),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          for (final path in paths)
            SelectableText(
              path,
              style: theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace', color: scheme.onSurfaceVariant),
            ),
          if (note != null) ...[
            const SizedBox(height: 4),
            _NoteLine(icon: Icons.info_outline_rounded, color: scheme.onSurfaceVariant, text: note!),
          ],
        ],
      ),
    );
  }
}

class _NoteLine extends StatelessWidget {
  const _NoteLine({
    super.key,
    required this.icon,
    required this.color,
    required this.text,
    this.padding = EdgeInsets.zero,
  });

  final IconData icon;
  final Color color;
  final String text;
  final EdgeInsetsGeometry padding;

  @override
  Widget build(BuildContext context) => Padding(
        padding: padding,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(padding: const EdgeInsets.only(top: 1), child: Icon(icon, size: 16, color: color)),
            const SizedBox(width: 6),
            Expanded(child: Text(text, style: Theme.of(context).textTheme.bodySmall)),
          ],
        ),
      );
}
