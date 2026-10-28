import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../l10n/enhancements_locale.dart';
import '../../services/enhancements/enhancement_catalog.dart';
import '../../services/enhancements/enhancement_models.dart';
import '../../services/enhancements/enhancement_service.dart';
import '../../services/enhancements/enhancement_store.dart';
import '../../services/gamepad/gamepad_navigation_manager.dart';
import '../../services/logger_service.dart';
import '../../services/sfx_service.dart';
import '../../utils/gamepad_nav.dart';
import '../../widgets/confirm_action_dialog.dart';
import '../../widgets/custom_notification.dart';
import '../../widgets/glass/glass.dart';

/// Settings › Tools › Cheats & Enhancements catalogue: revision, sources and
/// licences, catalogue updates, downloaded data and every game RewindBox
/// changed, each restorable to its original configuration.
class EnhancementsCatalogScreen extends StatefulWidget {
  const EnhancementsCatalogScreen({super.key, this.service});

  final EnhancementService? service;

  static const String gamepadLayer = 'enhancements_catalog_screen';

  @override
  State<EnhancementsCatalogScreen> createState() => _EnhancementsCatalogScreenState();
}

class _Action {
  const _Action(this.key, this.run);
  final String key;
  final VoidCallback? run;
}

class _EnhancementsCatalogScreenState extends State<EnhancementsCatalogScreen> {
  static final _log = LoggerService.instance;

  late final EnhancementService _service = widget.service ?? EnhancementService.instance;
  late final GamepadNavigation _gamepadNav;
  final ScrollController _scroll = ScrollController();
  final Map<String, GlobalKey> _keys = {};

  EnhancementIndex? _index;
  List<EnhancementGameState> _games = const [];
  int _cacheBytes = 0;
  bool _busy = false;
  int _focus = 0;
  List<_Action> _actions = const [];

  String _t(String key) => EnhancementsLocale.text(context, key);

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onNavigateUp: () => _move(-1),
      onNavigateDown: () => _move(1),
      onSelectItem: () => _actions.isEmpty ? null : _actions[_focus].run?.call(),
      onBack: () => Navigator.of(context).maybePop(),
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        EnhancementsCatalogScreen.gamepadLayer,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
    _reload();
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(EnhancementsCatalogScreen.gamepadLayer);
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _reload() async {
    try {
      final index = await _service.catalog.index();
      final games = await _service.games();
      final bytes = await _service.catalog.cacheBytes();
      if (!mounted) return;
      setState(() {
        _index = index;
        _games = games;
        _cacheBytes = bytes;
      });
    } catch (error) {
      _log.w('Enhancements: catalogue tool failed to load: $error');
    }
  }

  void _move(int delta) {
    if (_actions.isEmpty) return;
    final next = (_focus + delta).clamp(0, _actions.length - 1);
    if (next == _focus) return;
    SfxService().playNavSound();
    setState(() => _focus = next);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ctx = _keys[_actions[next].key]?.currentContext;
      if (ctx != null) Scrollable.ensureVisible(ctx, alignment: 0.5);
    });
  }

  Future<void> _run(Future<String?> Function() body) async {
    if (_busy) return;
    setState(() => _busy = true);
    try {
      final message = await body();
      if (message != null && mounted) {
        AppNotification.showNotification(context, message, type: NotificationType.success);
      }
    } catch (error) {
      _log.w('Enhancements: catalogue action failed: $error');
      if (mounted) {
        AppNotification.showNotification(context, _t(EnhancementsLocale.failed), type: NotificationType.error);
      }
    } finally {
      if (mounted) setState(() => _busy = false);
      await _reload();
    }
  }

  Future<bool> _confirm(String body) => ConfirmActionDialog.show(
    context,
    title: _t(EnhancementsLocale.restore),
    body: body,
    confirmLabel: _t(EnhancementsLocale.confirm),
    cancelLabel: _t(EnhancementsLocale.cancel),
    icon: Symbols.settings_backup_restore_rounded,
  );

  void _checkUpdates() => _run(() async {
    final updated = await _service.catalog.refresh();
    return _t(updated ? EnhancementsLocale.updated : EnhancementsLocale.upToDate);
  });

  void _clearCache() => _run(() async {
    await _service.catalog.clearCache();
    return _t(EnhancementsLocale.cacheCleared);
  });

  Future<void> _restoreAll() async {
    if (!await _confirm(_t(EnhancementsLocale.restoreAllConfirm)) || !mounted) return;
    await _run(() async {
      await _service.restoreAll();
      return _t(EnhancementsLocale.restoreDone);
    });
  }

  Future<void> _restoreGame(EnhancementGameState game) async {
    if (!await _confirm(_t(EnhancementsLocale.restoreConfirm)) || !mounted) return;
    await _run(() async {
      await _service.restore(game.storeKey);
      return _t(EnhancementsLocale.restoreDone);
    });
  }

  static String _size(int bytes) {
    if (bytes < 1024) return '$bytes B';
    if (bytes < 1024 * 1024) return '${(bytes / 1024).toStringAsFixed(0)} KB';
    return '${(bytes / (1024 * 1024)).toStringAsFixed(1)} MB';
  }

  static String _engineName(String engine) => switch (engine) {
    'melonx' => 'MeloNX (Switch)',
    'rpcs3' => 'RPCS3 (PS3)',
    'armsx2' => 'ARMSX2 (PS2)',
    'dolphin' => 'Dolphin (GameCube / Wii)',
    _ => engine,
  };

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.65);
    final actions = <_Action>[];
    final children = <Widget>[];

    void button(String key, String label, IconData icon, VoidCallback? onTap, {bool destructive = false}) {
      actions.add(_Action(key, onTap));
      children
        ..add(
          KeyedSubtree(
            key: _keys.putIfAbsent(key, GlobalKey.new),
            child: GlassButton(
              label: label,
              icon: icon,
              expanded: true,
              focused: actions.length - 1 == _focus,
              variant: destructive ? GlassButtonVariant.destructive : GlassButtonVariant.tonal,
              sound: GlassButtonSound.enter,
              onPressed: _busy ? null : onTap,
            ),
          ),
        )
        ..add(const GlassGap());
    }

    Widget line(String text, {double size = 9}) => Padding(
      padding: EdgeInsets.symmetric(horizontal: 6.r, vertical: 1.r),
      child: Text(text, style: theme.textTheme.bodyMedium?.copyWith(fontSize: size.r, color: muted)),
    );

    final index = _index;
    children.add(GlassSectionHeader(label: _t(EnhancementsLocale.toolTitle), first: true));
    if (index != null) {
      children.add(line('${_t(EnhancementsLocale.revision)}: ${index.revision}'));
      for (final engine in index.totals.entries) {
        final entries = Map<String, dynamic>.from((engine.value as Map)['entries'] as Map? ?? const {});
        final total = entries.values.fold<int>(0, (sum, value) => sum + (value as int));
        children.add(line('${_engineName(engine.key)}: $total · ${(engine.value as Map)['keys']} '
            '${entries.entries.map((e) => '${e.key} ${e.value}').join(' · ')}'));
      }
      children.add(line('${_t(EnhancementsLocale.cacheSize)}: ${_size(_cacheBytes)}'));
      children.add(const GlassGap());
    }
    if (_busy) {
      children
        ..add(const LinearProgressIndicator())
        ..add(const GlassGap());
    }
    button('update', _t(EnhancementsLocale.checkUpdates), Symbols.sync_rounded, _checkUpdates);
    button('cache', _t(EnhancementsLocale.clearCache), Symbols.delete_sweep_rounded, _clearCache);

    children.add(GlassSectionHeader(label: _t(EnhancementsLocale.gamesTitle)));
    if (_games.isEmpty) {
      children
        ..add(GlassBanner(kind: GlassBannerKind.neutral, compact: true, message: _t(EnhancementsLocale.noGames)))
        ..add(const GlassGap());
    }
    for (final game in _games) {
      final label = '${game.title.isEmpty ? game.key : game.title} · ${_engineName(game.engine)} · '
          '${EnhancementsLocale.format(context, EnhancementsLocale.activeCount, {'count': game.active.length})}';
      button('game:${game.storeKey}', label, Symbols.settings_backup_restore_rounded, () => _restoreGame(game));
    }
    if (_games.isNotEmpty) {
      button('restoreAll', _t(EnhancementsLocale.restoreAll), Symbols.restart_alt_rounded, _restoreAll,
          destructive: true);
    }

    children.add(GlassSectionHeader(label: _t(EnhancementsLocale.sources)));
    for (final EnhancementSource source in index?.sources ?? const []) {
      children
        ..add(
          GlassSurface(
            role: GlassRole.bubble,
            padding: glass.bubblePadding,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(source.name, style: theme.textTheme.bodyLarge?.copyWith(fontSize: 10.5.r)),
                Text(source.url, style: theme.textTheme.bodySmall?.copyWith(fontSize: 8.r, color: muted)),
                Text('${source.engines.map(_engineName).join(', ')} · ${source.revision}',
                    style: theme.textTheme.bodySmall?.copyWith(fontSize: 8.r, color: muted)),
                Text(source.license, style: theme.textTheme.bodySmall?.copyWith(fontSize: 8.r, color: muted)),
              ],
            ),
          ),
        )
        ..add(const GlassGap());
    }
    _actions = actions;
    if (_focus >= actions.length) _focus = actions.isEmpty ? 0 : actions.length - 1;

    return GlassBackdrop(
      child: Material(
        color: Colors.transparent,
        child: SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(glass.margin, glass.gap, glass.margin, glass.gap),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                GlassSurface(
                  role: GlassRole.chrome,
                  padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 6.r),
                  child: Row(
                    children: [
                      GlassIconButton(
                        icon: Symbols.arrow_back_rounded,
                        tooltip: _t(EnhancementsLocale.back),
                        onPressed: () => Navigator.of(context).maybePop(),
                        sound: GlassButtonSound.back,
                        size: 26.r,
                      ),
                      SizedBox(width: 10.r),
                      Icon(Symbols.auto_fix_high_rounded, color: theme.colorScheme.primary, size: 16.r),
                      SizedBox(width: 8.r),
                      Expanded(
                        child: Text(
                          _t(EnhancementsLocale.toolTitle),
                          style: theme.textTheme.titleLarge?.copyWith(fontSize: 13.r),
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(height: glass.gap),
                Expanded(
                  child: ListView(controller: _scroll, padding: EdgeInsets.only(bottom: glass.gap), children: children),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
