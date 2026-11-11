import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import '../../l10n/libretro_locale.dart';
import '../../providers/sqlite_config_provider.dart';
import '../../services/libretro_bios_check_service.dart';
import '../../services/libretro_core_catalog.dart';
import '../../services/libretro_internal_service.dart';
import '../../services/logger_service.dart';
import '../../widgets/libretro_3ds_import_route.dart';
import 'libretro_skin_manager_screen.dart';

/// Settings › Tools › BIOS checker (iOS): for every console of the embedded
/// libretro engine, the BIOS and system files its cores read, where they are
/// expected, what was found and whether the checksum matches a published
/// dump. Read only: the page changes nothing in System, Saves, Config or the
/// libraries, and never blocks a launch. Its only action is the existing
/// "Copy RetroArch saves and BIOS" import, followed by a new check.
///
/// The check runs when the page opens, on "Check again", when the app comes
/// back to the foreground (after files were added in the Files app) and when
/// the registered library folders change. Other pages open it with a
/// [console] (a key of `LibretroCoreCatalog.consoles`) to preselect the
/// console filter.
class LibretroBiosCheckerScreen extends StatefulWidget {
  const LibretroBiosCheckerScreen({super.key, this.console, this.service, this.copyRetroArch, this.open3dsImport});

  /// Console filter to preselect; null shows every console.
  final String? console;

  /// Checker to use (tests); the app's own by default.
  final LibretroBiosCheckService? service;

  /// RetroArch import to run (tests); [LibretroInternalService.copyRetroArchData]
  /// by default.
  final Future<LibretroRetroArchCopy?> Function()? copyRetroArch;

  /// Opens the Nintendo 3DS system data import (tests);
  /// [openLibretro3dsImport] by default.
  final Future<void> Function(BuildContext context)? open3dsImport;

  @override
  State<LibretroBiosCheckerScreen> createState() => _LibretroBiosCheckerScreenState();
}

class _LibretroBiosCheckerScreenState extends State<LibretroBiosCheckerScreen>
    with LibretroPageNavigation<LibretroBiosCheckerScreen>, WidgetsBindingObserver {
  static final _log = LoggerService.instance;

  late final LibretroBiosCheckService _service = widget.service ?? LibretroBiosCheckService();
  LibretroBiosReport? _report;
  Object? _error;
  bool _checking = false;
  bool _checkAgain = false;
  bool _copying = false;
  String? _console;
  LibretroBiosStatus? _status;
  List<String>? _roots;

  String _t(String key) => LibretroLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) => LibretroLocale.formatContext(context, key, values);

  @override
  void initState() {
    super.initState();
    final console = widget.console;
    _console = console != null && LibretroCoreCatalog.consoles.containsKey(console) ? console : null;
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    // The registered library folders: their console folders are game
    // folders FBNeo and Snes9x read. A change triggers a new check.
    final provider = Provider.of<SqliteConfigProvider?>(context);
    final roots = List<String>.unmodifiable(provider?.config.romFolders ?? const <String>[]);
    if (_roots == null || !listEquals(_roots, roots)) {
      _roots = roots;
      unawaited(_check());
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Files may have been added or renamed in the Files app meanwhile.
    if (state == AppLifecycleState.resumed && !_copying) unawaited(_check());
  }

  /// Runs a check; a request made while one runs is honoured once it ends.
  Future<void> _check() async {
    if (_checking) {
      _checkAgain = true;
      return;
    }
    if (mounted) setState(() => _checking = true);
    try {
      do {
        _checkAgain = false;
        try {
          final report = await _service.check(libraryRoots: _roots ?? const <String>[]);
          if (!mounted) return;
          setState(() {
            _report = report;
            _error = null;
          });
        } catch (error, stackTrace) {
          _log.e('BIOS check failed', error: error, stackTrace: stackTrace);
          if (!mounted) return;
          setState(() => _error = error);
        }
      } while (_checkAgain && mounted);
    } finally {
      _checking = false;
      if (mounted) setState(() {});
    }
  }

  void _notice(String message, {SnackBarAction? action}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message), action: action));
  }

  /// The Nintendo 3DS system data import, for an Azahar, Citra or Lime3DS
  /// folder given to the RetroArch copy; the check runs again on return.
  Future<void> _open3dsImport() async {
    await (widget.open3dsImport ?? openLibretro3dsImport)(context);
    if (mounted) await _check();
  }

  /// The existing RetroArch import (saves, states and System, nothing
  /// overwritten), then a new check.
  Future<void> _copyRetroArch() async {
    if (_copying) return;
    setState(() => _copying = true);
    pausePageNavigation();
    try {
      final copied = await (widget.copyRetroArch ?? LibretroInternalService.copyRetroArchData)();
      resumePageNavigation();
      if (copied == null || !mounted) return;
      if (copied.total == 0 && copied.emulator3dsFolder) {
        _notice(
          _t('retroArch3dsFolder'),
          action: SnackBarAction(label: _t('system3dsImport'), onPressed: () => unawaited(_open3dsImport())),
        );
        return;
      }
      _notice(
        copied.total == 0
            ? _t('retroArchNothing')
            : _f('retroArchImported', {'saves': copied.saves, 'states': copied.states, 'system': copied.system}),
      );
      await _check();
    } catch (error) {
      _log.w('RetroArch copy from the BIOS checker failed: $error');
      if (mounted) _notice(_f('importFailed', {'error': error}));
    } finally {
      resumePageNavigation();
      if (mounted) setState(() => _copying = false);
    }
  }

  // ------------------------------------------------------------ texts

  String _statusLabel(LibretroBiosStatus status) => switch (status) {
        LibretroBiosStatus.verified => _t('biosStatusVerified'),
        LibretroBiosStatus.presentUnverified => _t('biosStatusUnverified'),
        LibretroBiosStatus.missingRequired => _t('biosStatusMissingRequired'),
        LibretroBiosStatus.missingOptional => _t('biosStatusMissingOptional'),
        LibretroBiosStatus.invalid => _t('biosStatusInvalid'),
      };

  IconData _statusIcon(LibretroBiosStatus status) => switch (status) {
        LibretroBiosStatus.verified => Icons.verified_rounded,
        LibretroBiosStatus.presentUnverified => Icons.help_outline_rounded,
        LibretroBiosStatus.missingRequired => Icons.error_outline_rounded,
        LibretroBiosStatus.missingOptional => Icons.remove_circle_outline_rounded,
        LibretroBiosStatus.invalid => Icons.block_rounded,
      };

  Color _statusColor(LibretroBiosStatus status, ColorScheme scheme) => switch (status) {
        LibretroBiosStatus.verified => Colors.green.shade600,
        LibretroBiosStatus.presentUnverified => Colors.amber.shade800,
        LibretroBiosStatus.missingRequired => scheme.error,
        LibretroBiosStatus.missingOptional => scheme.onSurfaceVariant,
        LibretroBiosStatus.invalid => scheme.error,
      };

  String _condition(LibretroBiosEntryResult result) {
    final condition = result.condition;
    if (condition == null) return '';
    return _f(condition.key, condition.arguments);
  }

  String _level(LibretroBiosEntryResult result) => switch (result.need) {
        LibretroBiosNeed.required => _t('biosLevelRequired'),
        LibretroBiosNeed.requiredFor => _f('biosLevelRequiredFor', {'condition': _condition(result)}),
        LibretroBiosNeed.recommended => _t('biosLevelRecommended'),
        LibretroBiosNeed.onlyFor => _f('biosLevelConditional', {'condition': _condition(result)}),
        LibretroBiosNeed.optional => _t('biosLevelOptional'),
        LibretroBiosNeed.bundled => _t('biosLevelBundled'),
      };

  String? _region(String? region) => switch (region) {
        'na' => _t('biosRegionNorthAmerica'),
        'eu' => _t('biosRegionEurope'),
        'jp' => _t('biosRegionJapan'),
        'world' => _t('biosRegionWorld'),
        _ => null,
      };

  String _note(LibretroBiosNote note) => _f(note.key, note.arguments);

  // ------------------------------------------------------------- build

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final report = _report;
    final consoles = report == null ? const <LibretroBiosConsoleResult>[] : _visibleConsoles(report);
    return libretroPage(Scaffold(
      appBar: libretroPageAppBar(context, _t('biosCheckerTitle')),
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
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
                    child: Text(
                      _t('biosCheckerIntro'),
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                  _buildHeader(context, report),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        _f('biosScanFailed', {'error': _error}),
                        style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.error),
                      ),
                    ),
                  if (report != null) ...[
                    _buildFilters(context, report),
                    if (report.libraryUnavailable)
                      Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: Text(_t('biosLibraryUnavailable'), style: theme.textTheme.bodySmall),
                      ),
                    for (final console in consoles) _buildConsole(context, console),
                    if (consoles.isEmpty)
                      Padding(
                        padding: const EdgeInsets.all(24),
                        child: Text(_t('biosNoResults'), textAlign: TextAlign.center),
                      ),
                  ] else if (_error == null)
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    ));
  }

  /// Consoles shown with the filters; a console without any matching file
  /// is shown only when no status is selected (its notes still apply).
  List<LibretroBiosConsoleResult> _visibleConsoles(LibretroBiosReport report) => <LibretroBiosConsoleResult>[
        for (final console in report.consoles)
          if (_console == null || console.id == _console)
            if (_status == null || console.entries.any((entry) => entry.status == _status)) console,
      ];

  Widget _buildHeader(BuildContext context, LibretroBiosReport? report) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final counts = report?.counts;
    return Card(
      margin: const EdgeInsets.only(bottom: 16),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.fact_check_outlined, color: scheme.primary),
                const SizedBox(width: 12),
                Expanded(
                  child: Text(
                    report != null
                        ? _f('biosConsolesReady', {'ready': report.readyConsoles, 'total': report.availableConsoles})
                        : _t(_checking ? 'biosChecking' : 'biosCheckerTitle'),
                    style: theme.textTheme.titleMedium,
                  ),
                ),
                if (_checking)
                  const SizedBox(width: 20, height: 20, child: CircularProgressIndicator(strokeWidth: 2)),
              ],
            ),
            if (counts != null) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final status in LibretroBiosStatus.values)
                    _SummaryCount(
                      key: ValueKey('bios-summary-${status.name}'),
                      icon: _statusIcon(status),
                      color: _statusColor(status, scheme),
                      label: _statusLabel(status),
                      count: counts[status] ?? 0,
                    ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                _f('biosScanStats', {
                  'files': report!.examinedFiles,
                  'hashed': report.hashedFiles,
                  'cached': report.cachedFiles,
                  'ms': report.elapsed.inMilliseconds,
                }),
                style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
            const SizedBox(height: 10),
            Text(_t('biosWhereToPut'), style: theme.textTheme.bodySmall),
            const SizedBox(height: 4),
            Text(
              _t('biosCopyRetroArchHint'),
              style: theme.textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                LibretroFocusRing(
                  child: FilledButton.tonalIcon(
                    key: const ValueKey('libretro-bios-check-again'),
                    onPressed: _checking ? null : () => unawaited(_check()),
                    icon: const Icon(Icons.refresh_rounded),
                    label: Text(_checking ? _t('biosChecking') : _t('biosCheckAgain')),
                  ),
                ),
                LibretroFocusRing(
                  child: OutlinedButton.icon(
                    key: const ValueKey('libretro-bios-copy-retroarch'),
                    onPressed: _copying ? null : _copyRetroArch,
                    icon: const Icon(Icons.drive_folder_upload_outlined),
                    label: Text(_t('importRetroArch')),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _chip({required Key key, required String label, required bool selected, required VoidCallback onSelected, int? count}) =>
      LibretroFocusRing(
        radius: 12,
        child: ChoiceChip(
          key: key,
          selected: selected,
          onSelected: (_) => onSelected(),
          label: count == null
              ? Text(label)
              : Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [Text(label), const SizedBox(width: 6), Text(count.toString())],
                ),
        ),
      );

  Widget _buildFilters(BuildContext context, LibretroBiosReport report) {
    final theme = Theme.of(context);
    final counts = report.counts;
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(_t('biosFilterConsole'), style: theme.textTheme.labelLarge),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _chip(
                key: const ValueKey('bios-console-all'),
                label: _t('biosFilterAllConsoles'),
                selected: _console == null,
                onSelected: () => setState(() => _console = null),
              ),
              for (final console in report.consoles)
                _chip(
                  key: ValueKey('bios-console-${console.id}'),
                  label: console.name,
                  selected: _console == console.id,
                  onSelected: () => setState(() => _console = console.id),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Text(_t('biosFilterStatus'), style: theme.textTheme.labelLarge),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _chip(
                key: const ValueKey('bios-status-all'),
                label: _t('biosFilterAllStatuses'),
                selected: _status == null,
                onSelected: () => setState(() => _status = null),
              ),
              for (final status in LibretroBiosStatus.values)
                _chip(
                  key: ValueKey('bios-status-${status.name}'),
                  label: _statusLabel(status),
                  count: counts[status] ?? 0,
                  selected: _status == status,
                  onSelected: () => setState(() => _status = status),
                ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildConsole(BuildContext context, LibretroBiosConsoleResult console) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final entries = console.entries.where((entry) => _status == null || entry.status == _status).toList(growable: false);
    final problems = console.problems;
    return Card(
      key: ValueKey('bios-console-card-${console.id}'),
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(Icons.sports_esports_outlined, color: scheme.primary),
                const SizedBox(width: 12),
                Expanded(child: Text(console.name, style: theme.textTheme.titleMedium)),
                if (console.available)
                  _Badge(
                    icon: console.ready ? Icons.check_circle_rounded : Icons.error_outline_rounded,
                    color: console.ready ? Colors.green.shade600 : scheme.error,
                    label: console.ready ? _t('biosConsoleReady') : _f('biosConsoleProblems', {'count': problems}),
                  ),
              ],
            ),
            if (console.gateNote != null) ...[
              const SizedBox(height: 8),
              _NoteLine(
                icon: console.gateNote!.key == 'biosGateOk' ? Icons.check_circle_outline_rounded : Icons.error_outline_rounded,
                color: console.gateNote!.key == 'biosGateOk' ? Colors.green.shade600 : scheme.error,
                text: _note(console.gateNote!),
              ),
            ],
            for (final note in console.notes) ...[
              const SizedBox(height: 6),
              _NoteLine(icon: Icons.info_outline_rounded, color: scheme.onSurfaceVariant, text: _note(note)),
            ],
            for (final entry in entries) _buildEntry(context, entry),
          ],
        ),
      ),
    );
  }

  Widget _buildEntry(BuildContext context, LibretroBiosEntryResult result) {
    final theme = Theme.of(context);
    final scheme = theme.colorScheme;
    final entry = result.entry;
    final region = _region(entry.region);
    final coreNames = result.cores.map((id) => LibretroCoreCatalog.cores[id]?.displayName ?? id).join(', ');
    final expected = result.expected.map((path) => path ?? _t('biosLocationGameFolder')).join(' → ');
    final alternatives = entry.allNames().skip(1).toList(growable: false);
    final status = result.status;
    return Container(
      key: ValueKey('bios-entry-${entry.id}'),
      margin: const EdgeInsets.only(top: 10),
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 4),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: _statusColor(status, scheme).withValues(alpha: 0.5)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(child: Text(entry.names.first, style: theme.textTheme.titleSmall)),
              const SizedBox(width: 8),
              _Badge(
                key: ValueKey('bios-status-badge-${entry.id}'),
                icon: _statusIcon(status),
                color: _statusColor(status, scheme),
                label: _statusLabel(status),
                filled: status == LibretroBiosStatus.verified,
              ),
            ],
          ),
          const SizedBox(height: 6),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _Tag(text: _level(result), emphasised: result.neededNow),
              if (region != null) _Tag(text: region),
            ],
          ),
          const SizedBox(height: 6),
          Text(_f('biosCoresLabel', {'cores': coreNames}), style: theme.textTheme.bodySmall),
          Text(_f('biosExpected', {'paths': expected}), style: theme.textTheme.bodySmall),
          if (alternatives.isNotEmpty)
            Text(_f('biosAlsoAccepted', {'names': alternatives.join(', ')}), style: theme.textTheme.bodySmall),
          Text(
            result.found == null ? _t('biosNotFound') : _f('biosDetected', {'path': result.found!.displayPath}),
            style: theme.textTheme.bodySmall?.copyWith(fontWeight: FontWeight.w600),
          ),
          for (final note in result.notes) ...[
            const SizedBox(height: 4),
            _NoteLine(icon: Icons.info_outline_rounded, color: scheme.onSurfaceVariant, text: _note(note)),
          ],
          LibretroFocusRing(
            radius: 12,
            child: Theme(
              data: theme.copyWith(dividerColor: Colors.transparent),
              child: ExpansionTile(
                key: ValueKey('bios-details-${entry.id}'),
                tilePadding: EdgeInsets.zero,
                childrenPadding: const EdgeInsets.only(bottom: 8),
                expandedCrossAxisAlignment: CrossAxisAlignment.start,
                title: Text(_t('biosDetails'), style: theme.textTheme.labelLarge),
                children: _details(context, result),
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Raw technical values (paths, sizes, checksums, references): never
  /// translated, under translated labels.
  List<Widget> _details(BuildContext context, LibretroBiosEntryResult result) {
    final style = Theme.of(context).textTheme.bodySmall?.copyWith(fontFamily: 'monospace');
    final facts = result.facts;
    final lines = <String>[
      for (final copy in result.copies) copy.displayPath,
      if (facts != null) _f('biosDetailSize', {'bytes': facts.size}),
      if (facts?.md5 != null) 'MD5 ${facts!.md5}',
      if (facts?.sha1 != null) 'SHA-1 ${facts!.sha1}',
      for (final dump in result.entry.knownDumps) ...[
        _f('biosDetailReference', {'label': dump.label, 'source': dump.source}),
        [
          _f('biosDetailSize', {'bytes': dump.size}),
          if (dump.md5 != null) 'MD5 ${dump.md5}',
          if (dump.sha1 != null) 'SHA-1 ${dump.sha1}',
        ].join(' · '),
      ],
    ];
    return <Widget>[for (final line in lines) SelectableText(line, style: style)];
  }
}

class _SummaryCount extends StatelessWidget {
  const _SummaryCount({super.key, required this.icon, required this.color, required this.label, required this.count});

  final IconData icon;
  final Color color;
  final String label;
  final int count;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18, color: color),
          const SizedBox(width: 6),
          Text(label, style: theme.textTheme.bodySmall),
          const SizedBox(width: 6),
          Text(count.toString(), style: theme.textTheme.titleSmall?.copyWith(color: color)),
        ],
      ),
    );
  }
}

/// Status of a file or a console. The verified badge is filled green with
/// a check mark.
class _Badge extends StatelessWidget {
  const _Badge({super.key, required this.icon, required this.color, required this.label, this.filled = false});

  final IconData icon;
  final Color color;
  final String label;
  final bool filled;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final foreground = filled ? Colors.white : color;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: filled ? color : color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(20),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: foreground),
          const SizedBox(width: 4),
          Flexible(child: Text(label, style: theme.textTheme.labelMedium?.copyWith(color: foreground))),
        ],
      ),
    );
  }
}

class _Tag extends StatelessWidget {
  const _Tag({required this.text, this.emphasised = false});

  final String text;
  final bool emphasised;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: emphasised ? scheme.errorContainer : scheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        text,
        style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: emphasised ? scheme.onErrorContainer : scheme.onSurfaceVariant,
            ),
      ),
    );
  }
}

class _NoteLine extends StatelessWidget {
  const _NoteLine({required this.icon, required this.color, required this.text});

  final IconData icon;
  final Color color;
  final String text;

  @override
  Widget build(BuildContext context) => Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(padding: const EdgeInsets.only(top: 1), child: Icon(icon, size: 16, color: color)),
          const SizedBox(width: 6),
          Expanded(child: Text(text, style: Theme.of(context).textTheme.bodySmall)),
        ],
      );
}
