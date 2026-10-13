import 'dart:async';

import 'package:flutter/material.dart';

import '../../l10n/libretro_locale.dart';
import '../../services/libretro_core_catalog.dart';
import '../../services/libretro_core_option_store.dart';
import '../../services/libretro_resolution.dart';
import '../../services/libretro_resolution_service.dart';
import '../../services/logger_service.dart';
import 'libretro_skin_manager_screen.dart';

/// "Resolution and picture" of a console (System Settings › Emulators and
/// the Consoles tab, Build 455): the internal resolution each core of the
/// console uses for every game, saved where the in-game menu saves it. A
/// core without internal resolution is explained, not hidden. Picture
/// enlargement and filtering stay in the in-game menu, which also sets a
/// resolution for one game only.
class LibretroResolutionScreen extends StatefulWidget {
  const LibretroResolutionScreen({super.key, required this.console, this.service});

  /// Key of [LibretroCoreCatalog.consoles].
  final String console;

  /// Service to use (tests); the app's own by default.
  final LibretroResolutionService? service;

  @override
  State<LibretroResolutionScreen> createState() => _LibretroResolutionScreenState();
}

class _LibretroResolutionScreenState extends State<LibretroResolutionScreen>
    with LibretroPageNavigation<LibretroResolutionScreen> {
  static final _log = LoggerService.instance;

  late final LibretroResolutionService _service = widget.service ?? LibretroResolutionService();
  List<LibretroCoreResolution>? _cores;
  Object? _error;
  String? _saving;

  String _t(String key) => LibretroLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) => LibretroLocale.formatContext(context, key, values);

  String get _consoleName => LibretroCoreCatalog.consoles[widget.console]?.name ?? widget.console;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  Future<void> _load() async {
    try {
      final cores = await _service.forConsole(widget.console);
      if (!mounted) return;
      setState(() {
        _cores = cores;
        _error = null;
      });
    } catch (error, stackTrace) {
      _log.e('Libretro resolution not read', error: error, stackTrace: stackTrace);
      if (mounted) setState(() => _error = error);
    }
  }

  void _notice(String message) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(message)));
  }

  Future<void> _select(LibretroCoreResolution resolution, String value) async {
    if (_saving != null || value == resolution.current) return;
    setState(() => _saving = resolution.core.id);
    try {
      await _service.setValue(resolution, value);
      await _load();
    } on LibretroCoreOptionStoreException catch (error) {
      _log.w('Libretro resolution not saved: $error');
      _notice(_t('resolutionSessionActive'));
    } catch (error) {
      _log.w('Libretro resolution not saved: $error');
      _notice(_f('resolutionSaveFailed', {'error': error}));
    } finally {
      if (mounted) setState(() => _saving = null);
    }
  }

  String _label(LibretroResolutionChoice choice) {
    if (choice.isNative) return _t('resolutionNative');
    final locale = Localizations.maybeLocaleOf(context) ?? const Locale('en');
    return '×${LibretroResolution.factorText(choice.factor, LibretroLocale.localeKey(locale))}';
  }

  Widget _buildCore(BuildContext context, LibretroCoreResolution resolution) {
    final theme = Theme.of(context);
    final muted = theme.textTheme.bodySmall?.copyWith(color: theme.colorScheme.onSurfaceVariant);
    final name = resolution.core.displayName;
    final multiple = (_cores?.length ?? 0) > 1;
    final title = multiple && LibretroResolutionService.isDefaultFor(resolution.core, widget.console)
        ? _f('coreDefault', {'core': name})
        : name;
    final current = resolution.current;
    final children = <Widget>[
      Text(title, style: theme.textTheme.titleMedium),
      const SizedBox(height: 8),
    ];
    if (resolution.supported) {
      children.addAll(<Widget>[
        Text(_t('settingResolution'), style: theme.textTheme.labelLarge),
        const SizedBox(height: 6),
        Wrap(
          spacing: 6,
          runSpacing: 6,
          children: [
            for (final choice in resolution.choices)
              LibretroFocusRing(
                radius: 12,
                child: ChoiceChip(
                  key: ValueKey('libretro-resolution-${resolution.core.id}-${choice.value}'),
                  selected: choice.value == current,
                  onSelected: _saving != null ? null : (_) => unawaited(_select(resolution, choice.value)),
                  label: Text(
                    choice.width > 0 && choice.height > 0
                        ? '${_label(choice)} · ${choice.width} × ${choice.height}'
                        : _label(choice),
                  ),
                ),
              ),
          ],
        ),
        const SizedBox(height: 8),
        Text(
          <String>[
            resolution.stored != null
                ? _f('resolutionFromCore', {'core': name})
                : _t('resolutionDefaultNative'),
            _t('resolutionAppliesNextGame'),
            _t('resolutionLoadWarning'),
          ].join(' '),
          style: theme.textTheme.bodySmall,
        ),
        if (resolution.gamesWithOwnValue > 0) ...[
          const SizedBox(height: 4),
          Text(
            _f('resolutionGamesOwn', {'count': resolution.gamesWithOwnValue}),
            key: ValueKey('libretro-resolution-games-${resolution.core.id}'),
            style: theme.textTheme.bodySmall,
          ),
        ],
        const SizedBox(height: 4),
        Text(
          _f(resolution.detected ? 'resolutionValuesDetected' : 'resolutionValuesCatalog', {'core': name}),
          style: muted,
        ),
      ]);
    } else {
      children.addAll(<Widget>[
        Text(
          _f('resolutionUnsupported', {'core': name}),
          key: ValueKey('libretro-resolution-unsupported-${resolution.core.id}'),
          style: theme.textTheme.labelLarge,
        ),
        const SizedBox(height: 4),
        // The core has the option, but it did not apply to the way it drew
        // at its last launch (PPSSPP in software rendering).
        Text(
          _f(resolution.inapplicableKey != null ? 'resolutionInapplicableFooter' : 'resolutionUnsupportedFooter',
              {'core': name}),
          style: theme.textTheme.bodySmall,
        ),
      ]);
    }
    return Card(
      key: ValueKey('libretro-resolution-core-${resolution.core.id}'),
      margin: const EdgeInsets.only(bottom: 12),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 12),
        child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: children),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final cores = _cores;
    return libretroPage(Scaffold(
      appBar: libretroPageAppBar(context, '${_t('resolutionPage')} · $_consoleName'),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 860),
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 0, 4, 12),
                    child: Text(
                      _f('resolutionConsoleIntro', {'console': _consoleName}),
                      style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.onSurfaceVariant),
                    ),
                  ),
                  if (_error != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: Text(
                        _f('resolutionSaveFailed', {'error': _error}),
                        style: theme.textTheme.bodyMedium?.copyWith(color: theme.colorScheme.error),
                      ),
                    ),
                  if (cores == null && _error == null)
                    const Padding(
                      padding: EdgeInsets.all(32),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                  if (cores != null)
                    for (final resolution in cores) _buildCore(context, resolution),
                  Padding(
                    padding: const EdgeInsets.fromLTRB(4, 4, 4, 0),
                    child: Text(_t('resolutionInGameHint'), style: theme.textTheme.bodySmall),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    ));
  }
}
