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
import '../../services/rpcs3_save_exchange_service.dart' show Rpcs3SaveExchangeService;
import '../../services/storage/storage_import_activity.dart';
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

/// Forgets the folder picked for an import once its pass is over.
typedef Libretro3dsFolderRelease = Future<void> Function();

/// Emulators tab of the Nintendo 3DS › "System settings" (Build 447,
/// docs/libretro-3ds-system-settings.md § 3.4 and § 6.4).
///
/// System: the language, region and model of the emulated console, read
/// from and written to `Config/Azahar.json` through [LibretroCoreOptionStore]
/// (one file per core, no per-game scope). The language entry "Automatic"
/// is the absence of a stored value: the launch then hands the core the
/// language matching NeoStation's ([Libretro3dsLanguage]). An absent region
/// or model is the core's own default, which the page does not name. The
/// core applies the language only while the region is Auto, hence the
/// warning and the "back to Auto" button when a fixed region is chosen.
///
/// System data: a read-only inventory of the core's user directory
/// (`Saves/Azahar/Azahar`: keys, seed database, NAND titles, region fonts,
/// console data — the CFG save included), an import assistant (ZIP, folder
/// or individual files, analyzed into a plan the user confirms, installed
/// as a crash-safe pass) and the restore of the last complete backup, all
/// through [Libretro3dsSystemDataService]. What an interrupted pass left is
/// dealt with when the page opens and before each analysis. Every write is
/// refused while a game runs.
///
/// Raw values (core option values, file paths, title ids, technical codes,
/// sizes, dates) are shown as they are, under translated labels.
class Libretro3dsSystemScreen extends StatefulWidget {
  const Libretro3dsSystemScreen({
    super.key,
    this.store,
    this.dataService,
    this.languageNames = const <String, String>{},
    this.pickFiles,
    this.pickFolder,
    this.analyze,
    this.releaseFolder,
    this.startImport = false,
  });

  /// Starts the import assistant once the page is read: opened from the
  /// Nintendo 3DS import menu of the library, or after a RetroArch copy was
  /// given an Azahar, Citra or Lime3DS folder (`openLibretro3dsImport`).
  final bool startImport;

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

  /// Forgets the picked folder (tests); clears its bookmark by default.
  final Libretro3dsFolderRelease? releaseFolder;

  /// When a backup was made, in the phone's time zone, as an unambiguous
  /// date and time (`2026-10-12 10:00`, never translated).
  @visibleForTesting
  static String backupDate(DateTime createdAt) {
    final local = createdAt.toLocal();
    String two(int value) => value.toString().padLeft(2, '0');
    return '${local.year}-${two(local.month)}-${two(local.day)} '
        '${two(local.hour)}:${two(local.minute)}';
  }

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

/// A failure shown on the page: a translated sentence and, apart, the raw
/// technical detail.
class _Failure {
  const _Failure(this.textKey, this.detail);

  _Failure.of(Object error) : textKey = 'system3dsFailed', detail = error;

  final String textKey;
  final Object? detail;
}

class _Libretro3dsSystemScreenState extends State<Libretro3dsSystemScreen>
    with LibretroPageNavigation<Libretro3dsSystemScreen>, WidgetsBindingObserver {
  static final _log = LoggerService.instance;

  /// Bookmark key of the folder picked for an import (cleared once the
  /// import is over).
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

  /// The newest complete backup, the one "Restore the last backup" puts
  /// back.
  Libretro3dsBackup? _latestBackup;
  Object? _loadError;
  bool _loading = false;
  bool _loadAgain = false;

  /// A write, an import or a restore runs. The controls stay enabled
  /// meanwhile (their handlers return early): disabling the focused one
  /// while a dialog route is still leaving makes Flutter hand the focus
  /// to the route underneath, out of the controller's reach.
  bool _busy = false;

  /// The last write was refused because a game runs.
  bool _sessionActive = false;

  /// Raw detail of a session probe that failed: nobody knows whether a
  /// game runs, so nothing was written.
  String? _sessionUnknown;

  /// The last failed write, import or restore.
  _Failure? _actionError;

  /// Paths a failed pass could not put back.
  List<String> _missing = const <String>[];

  /// What the last recovery of an interrupted pass did.
  Libretro3dsRecoveryReport? _recovery;
  Object? _recoveryError;

  String _t(String key) => LibretroLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      LibretroLocale.formatContext(context, key, values);

  LibretroCuratedSetting _setting(String key) =>
      _core.settings.firstWhere((setting) => setting.key == key);

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    unawaited(_open());
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

  /// Deals with what an interrupted import or restore left, then reads the
  /// page.
  Future<void> _open() async {
    await _recover(quiet: true);
    await _reload();
    if (widget.startImport && mounted) await _import();
  }

  /// Runs the recovery of interrupted passes; false when something blocks
  /// a new pass. On opening ([quiet]) a running game or an unknown session
  /// state only defers it: install and restore run it again first.
  Future<bool> _recover({required bool quiet}) async {
    try {
      final report = await _data.recoverUnfinished();
      if (!mounted) return false;
      if (!report.isEmpty) {
        setState(() {
          _recovery = report;
          _recoveryError = null;
        });
      }
      return !report.failed;
    } on Libretro3dsSystemDataException catch (error) {
      _log.w('Nintendo 3DS recovery deferred: $error');
      if (mounted && !quiet) _showRefusal(error);
      return false;
    } catch (error, stackTrace) {
      _log.e('Nintendo 3DS recovery failed', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _recoveryError = error);
      return false;
    }
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
            _latestBackup = backups.isEmpty ? null : backups.first;
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

  /// Clears the notes of the previous action.
  void _clearNotes() {
    _sessionActive = false;
    _sessionUnknown = null;
    _actionError = null;
    _missing = const <String>[];
  }

  /// Shows why the service refused before touching any file.
  void _showRefusal(Libretro3dsSystemDataException error) {
    if (error.error == Libretro3dsSystemDataError.noBackup) {
      _notice(_t('system3dsNoBackup'));
      return;
    }
    setState(() {
      switch (error.error) {
        case Libretro3dsSystemDataError.sessionActive:
          if (error.sessionUnknown) {
            _sessionUnknown = error.technicalDetail ?? '';
          } else {
            _sessionActive = true;
          }
        case Libretro3dsSystemDataError.backupDamaged:
          _actionError = _Failure('system3dsBackupDamaged', error.technicalDetail);
        case Libretro3dsSystemDataError.unfinishedPass:
          _actionError = _Failure('system3dsRecoveryFailed', error.technicalDetail);
        case Libretro3dsSystemDataError.noBackup:
          break;
      }
    });
  }

  // ------------------------------------------------------------ system

  /// Writes [changes] to `Config/Azahar.json`, then shows what the file
  /// holds after a fresh read: a refused write is never shown as saved.
  Future<void> _write(Map<String, String?> changes) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _clearNotes();
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
      // The store only attaches a detail when its session probe failed.
      setState(() {
        if (error.technicalDetail != null) {
          _sessionUnknown = error.technicalDetail;
        } else {
          _sessionActive = true;
        }
      });
    } catch (error, stackTrace) {
      _log.e(
        'Nintendo 3DS option write failed',
        error: error,
        stackTrace: stackTrace,
      );
      if (!mounted) return;
      setState(() => _actionError = _Failure.of(error));
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

  /// What a selector shows for its stored value: an absent language is
  /// "Automatic" (NeoStation's own launch default); any other absent value
  /// is the core's own default, which the page does not claim to know.
  String _currentLabel(LibretroCuratedSetting setting) {
    final stored = _options?[setting.key];
    if (setting.key == _languageKey && stored == null) {
      final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
      return _f('lang3dsAutomatic', {'language': _appLanguageName(locale)});
    }
    if (stored == null) return _t('setting3dsCoreDefault');
    return _valueLabel(setting, stored);
  }

  Future<void> _choose(LibretroCuratedSetting setting) async {
    if (_busy) return;
    final automatic = setting.key == _languageKey;
    final current = _options?[setting.key];
    final options = <(String?, String)>[
      if (automatic) (null, _currentLabelFor(setting, null)),
      for (final value in setting.values) (value, _valueLabel(setting, value)),
    ];
    // Texts resolved now: the dialog may outlive this page's context.
    final title = _t(setting.labelKey);
    final choice = await showDialog<_Choice>(
      context: context,
      builder: (_) => _ChoiceDialog(
        title: title,
        options: options,
        current: current,
        // Nothing stored and no "Automatic" entry: no value is marked, the
        // D-pad starts on the first one.
        focus: options.any((option) => option.$1 == current) ? current : options.first.$1,
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

  /// Forgets the folder of an import that is over (its bookmark is not
  /// kept across launches).
  Future<void> _releaseFolder() async {
    try {
      if (widget.releaseFolder != null) {
        await widget.releaseFolder!();
      } else {
        await ExternalFolderAccess.clearBookmark(key: _folderAccessKey);
      }
    } catch (error) {
      _log.w('Nintendo 3DS import folder not released: $error');
    }
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

  /// Import assistant: source, recovery and analysis, plan and
  /// confirmation, installation, result.
  Future<void> _import() => StorageImportActivity.run(() async {
    if (_busy) return;
    final title = _t('system3dsImport');
    final labels = {
      _ImportSource.zip: _t('system3dsImportZip'),
      _ImportSource.folder: _t('system3dsImportFolder'),
      _ImportSource.files: _t('system3dsImportFiles'),
    };
    final source = await showDialog<_ImportSource>(
      context: context,
      builder: (_) => _SourceDialog(title: title, labels: labels),
    );
    if (source == null || !mounted) return;

    List<String>? sources;
    var folderPicked = false;
    pausePageNavigation();
    try {
      switch (source) {
        case _ImportSource.zip:
        case _ImportSource.files:
          sources = await _pickFiles();
        case _ImportSource.folder:
          final folder = await _pickFolder();
          folderPicked = folder != null;
          sources = folder == null ? null : <String>[folder];
      }
    } catch (error, stackTrace) {
      _log.e('Nintendo 3DS import picker failed', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _actionError = _Failure.of(error));
      return;
    } finally {
      resumePageNavigation();
    }
    if (sources == null || sources.isEmpty || !mounted) {
      if (folderPicked) await _releaseFolder();
      return;
    }
    final chosen = sources;
    // The folder's bookmark is not kept once its pass is over (installed,
    // refused, failed or cancelled).
    var released = !folderPicked;
    Future<void> releaseOnce() async {
      if (released) return;
      released = true;
      await _releaseFolder();
    }

    setState(() {
      _busy = true;
      _clearNotes();
    });
    try {
      final (recovery, plan) = await _withProgress(_t('system3dsAnalyzing'), () async {
        // An interrupted pass is dealt with before the plan is made, so the
        // plan compares the sources with what the user directory really
        // holds.
        final recovery = await _data.recoverUnfinished();
        if (recovery.failed) return (recovery, null);
        return (recovery, await _analyze(chosen));
      });
      if (!mounted) return;
      if (!recovery.isEmpty) setState(() => _recovery = recovery);
      if (plan == null) return;
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
      await releaseOnce();
      if (!mounted) return;
      if (report.recovery != null) setState(() => _recovery = report.recovery);
      await showDialog<void>(
        context: context,
        builder: (_) => _ResultDialog(report: report, page: this),
      );
    } on Libretro3dsSystemDataException catch (error) {
      _log.w('Nintendo 3DS import refused: $error');
      if (!mounted) return;
      _showRefusal(error);
    } catch (error, stackTrace) {
      _log.e('Nintendo 3DS import failed', error: error, stackTrace: stackTrace);
      if (!mounted) return;
      setState(() => _actionError = _Failure.of(error));
    } finally {
      await releaseOnce();
      if (mounted) {
        setState(() => _busy = false);
        await _reload();
      }
    }
  });

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
    final latest = _latestBackup;
    if (latest == null) {
      _notice(_t('system3dsNoBackup'));
      return;
    }
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: _t('system3dsRestoreBackup'),
      body: _f('system3dsRestoreConfirm', {'date': Libretro3dsSystemScreen.backupDate(latest.createdAt)}),
      confirmLabel: _t('system3dsRestoreBackup'),
      cancelLabel: _t('cancel'),
      icon: Icons.settings_backup_restore_rounded,
      accentColor: Theme.of(context).colorScheme.primary,
    );
    if (!confirmed || !mounted) return;
    setState(() {
      _busy = true;
      _clearNotes();
    });
    try {
      final report = await _data.restoreLastBackup();
      if (!mounted) return;
      if (report.recovery != null) setState(() => _recovery = report.recovery);
      if (report.succeeded) {
        _notice(_t('system3dsRestored'));
      } else {
        // Never "restored" without a file back: the raw reason instead.
        final failed = report.results.where((result) => !result.restored);
        setState(() {
          _missing = report.missing;
          _actionError = _Failure(
            'system3dsFailed',
            report.failure ?? (failed.isEmpty ? null : failed.first.technicalDetail),
          );
        });
      }
    } on Libretro3dsSystemDataException catch (error) {
      _log.w('Nintendo 3DS restore refused: $error');
      if (!mounted) return;
      _showRefusal(error);
    } catch (error, stackTrace) {
      _log.e('Nintendo 3DS restore failed', error: error, stackTrace: stackTrace);
      if (!mounted) return;
      setState(() => _actionError = _Failure.of(error));
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
        Libretro3dsRejection.incompleteTitle => _t('system3dsRejectedIncompleteTitle'),
        Libretro3dsRejection.sdTitle => _t('system3dsRejectedSdTitle'),
        Libretro3dsRejection.unsupportedCompression => _t('system3dsRejectedCompression'),
        Libretro3dsRejection.keysFormat => _t('system3dsRejectedKeysFormat'),
        Libretro3dsRejection.encryptedContent => _t('system3dsRejectedEncrypted'),
        Libretro3dsRejection.notDownloaded => _t('system3dsRejectedNotDownloaded'),
        Libretro3dsRejection.invalid || null => _t('system3dsRejectedInvalid'),
      };

  String _technical(Object? code) =>
      _f('system3dsTechnicalCode', {'code': code});

  /// Sizes as the other NeoStation pages print them (decimal units, as the
  /// Files app does; never translated).
  static String _formatBytes(int bytes) => Rpcs3SaveExchangeService.formatBytes(bytes);

  String _presence(bool present, [int size = 0]) => present
      ? _f('system3dsPresentSize', {'size': _formatBytes(size)})
      : _t('system3dsAbsent');

  /// The note of the last recovery: what was undone or finished, and the
  /// raw paths and code of what could not be.
  Widget _recoveryNote(BuildContext context, Libretro3dsRecoveryReport report, {Key? key}) {
    final scheme = Theme.of(context).colorScheme;
    final String text;
    final Color color;
    if (report.failed) {
      text = _t('system3dsRecoveryFailed');
      color = scheme.error;
    } else if (report.partial) {
      text = _t('system3dsRecoveredPartial');
      color = scheme.error;
    } else if (report.rolledBack) {
      text = _t('system3dsRecoveredUndone');
      color = scheme.onSurfaceVariant;
    } else {
      text = _t('system3dsRecoveredFinished');
      color = scheme.onSurfaceVariant;
    }
    final paths = <String>[...report.missing, ...report.kept];
    final codes = <String>[
      for (final pass in report.passes)
        if (pass.technicalDetail != null) '${pass.name}: ${pass.technicalDetail}',
    ];
    return Padding(
      key: key,
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          _NoteLine(icon: Icons.history_rounded, color: color, text: text),
          for (final path in paths) _MonoLine(text: path),
          for (final code in codes) _MonoLine(text: _technical(code)),
        ],
      ),
    );
  }

  // ------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final failure = _actionError;
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
                  if (_recovery != null) _recoveryNote(context, _recovery!, key: const ValueKey('3ds-recovery')),
                  if (_recoveryError != null)
                    _NoteLine(
                      key: const ValueKey('3ds-recovery-error'),
                      icon: Icons.error_outline_rounded,
                      color: scheme.error,
                      text: _technical(_recoveryError),
                      padding: const EdgeInsets.only(bottom: 12),
                    ),
                  if (_sessionActive)
                    _NoteLine(
                      key: const ValueKey('3ds-session-error'),
                      icon: Icons.error_outline_rounded,
                      color: scheme.error,
                      text: _t('system3dsSessionActive'),
                      padding: const EdgeInsets.only(bottom: 12),
                    ),
                  if (_sessionUnknown != null)
                    Padding(
                      key: const ValueKey('3ds-session-unknown'),
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _NoteLine(icon: Icons.error_outline_rounded, color: scheme.error, text: _t('system3dsSessionUnknown')),
                          _MonoLine(text: _technical(_sessionUnknown)),
                        ],
                      ),
                    ),
                  if (failure != null)
                    Padding(
                      key: const ValueKey('3ds-action-error'),
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _NoteLine(icon: Icons.error_outline_rounded, color: scheme.error, text: _t(failure.textKey)),
                          if (failure.detail != null) _MonoLine(text: _technical(failure.detail)),
                          if (_missing.isNotEmpty) ...[
                            _NoteLine(icon: Icons.report_outlined, color: scheme.error, text: _t('system3dsMissingFiles')),
                            for (final path in _missing) _MonoLine(text: path),
                          ],
                        ],
                      ),
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
    final latest = _latestBackup;
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
                id: 'titles',
                title: _f('system3dsTitles', {
                  'count': inventory.titleCount,
                  'size': _formatBytes(inventory.titleBytes),
                }),
                paths: const [Libretro3dsSystemDataService.titleRoot],
                status: inventory.titleCount > 0
                    ? _f('system3dsPresentFiles', {'count': inventory.titleFileCount})
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
              // The CFG save identifies the console: it is console data,
              // with the five console-unique files.
              _InventoryRow(
                id: 'console',
                title: _t('system3dsConsoleData'),
                paths: [
                  for (final file in inventory.consoleData)
                    '${file.relativePath} — ${_presence(file.exists, file.size)}',
                ],
                status: inventory.anyConsoleData ? _t('system3dsPresent') : _t('system3dsAbsent'),
                present: inventory.anyConsoleData,
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
                    onPressed: inventory == null || latest == null ? null : () => unawaited(_restore()),
                    icon: const Icon(Icons.settings_backup_restore_rounded),
                    label: Text(_t('system3dsRestoreBackup')),
                  ),
                ),
              ],
            ),
            if (inventory != null && latest != null) ...[
              const SizedBox(height: 6),
              Text(
                _f('system3dsLastBackup', {'date': Libretro3dsSystemScreen.backupDate(latest.createdAt)}),
                key: const ValueKey('3ds-last-backup'),
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
            if (inventory != null && latest == null) ...[
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

/// One choice per option, the current one marked and the [focus] one
/// focused first so the D-pad starts there; A (or a tap) returns the
/// choice, B returns nothing.
class _ChoiceDialog extends StatelessWidget {
  const _ChoiceDialog({required this.title, required this.options, required this.current, required this.focus});

  final String title;

  /// (core value or null for "Automatic", label).
  final List<(String?, String)> options;

  /// The stored value (null: nothing stored).
  final String? current;
  final String? focus;

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
                      autofocus: value == focus,
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

/// Steps 2 and 3: the plan (added, replaced, left out by the boxes,
/// identical, ignored, refused), the two opt-in boxes (console data, keys)
/// unchecked by default, and the confirmation.
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

  bool get _hasConsoleUnique => _plan.installable.any((item) => item.isConsoleData);
  bool get _hasKeys => _plan.installable.any((item) => item.kind == Libretro3dsItemKind.keys);

  /// Whether the boxes, as they are, let [item] be installed.
  bool _optedIn(Libretro3dsImportItem item) => switch (item.kind) {
        Libretro3dsItemKind.consoleUnique || Libretro3dsItemKind.config => _includeConsole,
        Libretro3dsItemKind.keys => _includeKeys,
        // Encrypted by Azahar for their console: read with its otp.bin only.
        Libretro3dsItemKind.title when item.consoleEncrypted =>
          _plan.consoleOtpReady(includeConsoleUnique: _includeConsole),
        _ => true,
      };

  /// Elements an install would write with the boxes as they are.
  int get _selected => _plan.installable.where(_optedIn).length;

  /// Raw destination (or source entry) and size of one element.
  static String _line(Libretro3dsImportItem item) {
    final name = item.relativeTarget ?? item.sourceEntry;
    if (item.kind == Libretro3dsItemKind.rejected || item.ignoreReason == Libretro3dsIgnoreReason.tooDeep) {
      return name;
    }
    return '$name · ${_Libretro3dsSystemScreenState._formatBytes(item.size)}';
  }

  Widget _group(BuildContext context, String key, String label, Iterable<Libretro3dsImportItem> items,
      {bool rejected = false, List<String> retired = const <String>[]}) {
    if (items.isEmpty && retired.isEmpty) return const SizedBox.shrink();
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
          // Once for the titles Azahar encrypted for their console.
          if (items.any((item) => item.consoleEncrypted))
            Text(
              _page._t('system3dsConsoleEncrypted'),
              key: ValueKey('3ds-plan-$key-console-encrypted'),
              style: theme.textTheme.bodySmall,
            ),
          for (final item in items) ...[
            Text(_line(item), style: mono),
            if (item.isConsoleData)
              Text(_page._t('system3dsConsoleData'), style: theme.textTheme.bodySmall),
            if (item.kind == Libretro3dsItemKind.keys)
              Text(_page._t('system3dsKeys'), style: theme.textTheme.bodySmall),
            if (item.ignoreReason == Libretro3dsIgnoreReason.tooDeep)
              Text(
                _page._f('system3dsIgnoredTooDeep', {'depth': _page._data.limits.maxFolderDepth}),
                style: theme.textTheme.bodySmall,
              ),
            // Build 454: a ZIP inside the chosen folder or archive (an
            // Azahar folder's nand.zip) is not opened; how to import it.
            if (item.ignoreReason == Libretro3dsIgnoreReason.nestedArchive)
              Text(_page._t('system3dsIgnoredNestedZip'), style: theme.textTheme.bodySmall),
            if (rejected) ...[
              Text(_page._rejection(item.rejection), style: theme.textTheme.bodySmall),
              if (item.technicalDetail != null)
                Text(_page._technical(item.technicalDetail), style: mono),
            ],
          ],
          // Installed files of a replaced title that the import does not
          // bring again: they leave with the old title, into the backup.
          for (final path in retired) ...[
            Text(path, style: mono),
            Text(_page._t('system3dsRetired'), style: theme.textTheme.bodySmall),
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
    final confirmLabel = _page._f('system3dsConfirm', {'count': _selected});
    final optedIn = plan.recognized.where(_optedIn);
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
                  optedIn.where((item) => item.action == Libretro3dsPlanAction.create)),
              _group(context, 'replace', _page._t('system3dsPlanReplace'),
                  optedIn.where((item) => item.action == Libretro3dsPlanAction.replace),
                  retired: plan.retiredTargets),
              // Keys and console data stay out until their box is checked.
              _group(context, 'excluded', _page._t('system3dsPlanExcluded'),
                  plan.installable.where((item) => !_optedIn(item))),
              _group(context, 'identical', _page._t('system3dsPlanIdentical'),
                  plan.recognized.where((item) => item.action == Libretro3dsPlanAction.skipIdentical)),
              // Files the core never reads (boot ROMs, key sector, the
              // essential.exefs sections other than the console files) apart
              // from the files nobody recognized.
              _group(context, 'notneeded', _page._t('system3dsPlanNotNeeded'),
                  plan.ignored.where((item) => item.ignoreReason == Libretro3dsIgnoreReason.notNeeded)),
              _group(context, 'ignored', _page._t('system3dsPlanIgnored'),
                  plan.ignored.where((item) => item.ignoreReason != Libretro3dsIgnoreReason.notNeeded)),
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
/// replaced files, the files of replaced titles moved out with them, what
/// a failure could not put back, and the raw code of any failure.
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
      Libretro3dsInstallStatus.rolledBack => page._t('system3dsRolledBack'),
      Libretro3dsInstallStatus.notAttempted => page._t('system3dsNotAttempted'),
      Libretro3dsInstallStatus.failed => page._t('system3dsFailed'),
    };
  }

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
              if (report.recovery != null) page._recoveryNote(context, report.recovery!),
              if (report.failure != null)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Text(
                    page._technical(report.failure),
                    key: const ValueKey('3ds-result-failure'),
                    style: mono?.copyWith(color: scheme.error),
                  ),
                ),
              if (report.missing.isNotEmpty)
                Padding(
                  key: const ValueKey('3ds-result-missing'),
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _NoteLine(icon: Icons.report_outlined, color: scheme.error, text: page._t('system3dsMissingFiles')),
                      for (final path in report.missing) _MonoLine(text: path),
                    ],
                  ),
                ),
              if (shown.any((result) =>
                  result.status == Libretro3dsInstallStatus.excluded && result.item.consoleEncrypted))
                _NoteLine(
                  key: const ValueKey('3ds-result-console-encrypted'),
                  icon: Icons.info_outline,
                  color: scheme.onSurfaceVariant,
                  text: page._t('system3dsConsoleEncrypted'),
                  padding: const EdgeInsets.only(bottom: 8),
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
                    color: result.status == Libretro3dsInstallStatus.failed ? scheme.error : null,
                  ),
                ),
                if (result.status == Libretro3dsInstallStatus.failed)
                  Text(
                    page._technical(result.technicalDetail ?? result.status.name),
                    style: mono?.copyWith(color: scheme.error),
                  ),
                const SizedBox(height: 6),
              ],
              for (final path in report.retired) ...[
                Text(path, key: ValueKey('3ds-result-retired-$path'), style: mono),
                Text(page._t('system3dsRetired'), style: theme.textTheme.bodySmall),
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

/// A raw value (path, technical code) under a note, indented to its text.
class _MonoLine extends StatelessWidget {
  const _MonoLine({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.only(left: 22, top: 2),
      child: SelectableText(
        text,
        style: theme.textTheme.bodySmall?.copyWith(fontFamily: 'monospace', color: theme.colorScheme.onSurfaceVariant),
      ),
    );
  }
}
