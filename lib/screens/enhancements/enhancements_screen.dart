import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../../l10n/enhancements_locale.dart';
import '../../models/game_model.dart';
import '../../models/system_model.dart';
import '../../services/enhancements/enhancement_models.dart';
import '../../services/enhancements/enhancement_service.dart';
import '../../services/gamepad/gamepad_navigation_manager.dart';
import '../../services/logger_service.dart';
import '../../services/sfx_service.dart';
import '../../services/texture_catalog_service.dart';
import '../../utils/gamepad_nav.dart';
import '../../widgets/confirm_action_dialog.dart';
import '../../widgets/custom_notification.dart';
import '../../widgets/custom_toggle_switch.dart';
import '../../widgets/glass/glass.dart';

/// "Cheats & Enhancements" of one game: Cheats, FPS, Ultrawide, Graphics,
/// Performance and HD textures, each entry switchable in one action.
///
/// Touch and gamepad drive the same rows: Up/Down focus, Left/Right or
/// LB/RB change the category, A switches, B goes back.
class EnhancementsScreen extends StatefulWidget {
  const EnhancementsScreen({
    super.key,
    required this.game,
    required this.system,
    required this.systemFolder,
    this.service,
  });

  final GameModel game;
  final SystemModel system;
  final String systemFolder;
  final EnhancementService? service;

  static const String gamepadLayer = 'enhancements_screen';

  static Future<void> open(
    BuildContext context, {
    required GameModel game,
    required SystemModel system,
    required String systemFolder,
  }) => Navigator.of(context, rootNavigator: true).push(
    PageRouteBuilder<void>(
      barrierDismissible: false,
      transitionDuration: LiquidGlassTheme.of(context).duration(context, GlassMotion.standard),
      reverseTransitionDuration: LiquidGlassTheme.of(context).duration(context, GlassMotion.quick),
      pageBuilder: (_, _, _) =>
          EnhancementsScreen(game: game, system: system, systemFolder: systemFolder),
      transitionsBuilder: (_, animation, _, child) => FadeTransition(
        opacity: CurvedAnimation(parent: animation, curve: Curves.easeOut),
        child: child,
      ),
    ),
  );

  @override
  State<EnhancementsScreen> createState() => _EnhancementsScreenState();
}

/// One focusable line of the page.
class _Row {
  const _Row(this.key, this.activate);
  final String key;
  final VoidCallback? activate;
}

class _EnhancementsScreenState extends State<EnhancementsScreen> {
  static final _log = LoggerService.instance;

  late final EnhancementService _service = widget.service ?? EnhancementService.instance;
  late final GamepadNavigation _gamepadNav;
  final ScrollController _scroll = ScrollController();
  final Map<String, GlobalKey> _rowKeys = {};

  EnhancementGameView? _view;
  Object? _error;
  bool _loading = true;
  String? _busy;
  double? _progress;
  EnhancementCategory _category = EnhancementCategory.cheat;
  int _focus = 0;
  List<_Row> _rows = const [];

  String _t(String key) => EnhancementsLocale.text(context, key);

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onNavigateUp: () => _moveFocus(-1),
      onNavigateDown: () => _moveFocus(1),
      onNavigateLeft: () => _cycleCategory(-1),
      onNavigateRight: () => _cycleCategory(1),
      onPreviousTab: () => _cycleCategory(-1),
      onNextTab: () => _cycleCategory(1),
      onSelectItem: () => _rows.isEmpty ? null : _rows[_focus].activate?.call(),
      onBack: _close,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        EnhancementsScreen.gamepadLayer,
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
    _load(download: true);
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer(EnhancementsScreen.gamepadLayer);
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _close() {
    if (_busy != null) return;
    Navigator.of(context).maybePop();
  }

  Future<void> _load({required bool download}) async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final view = await _service.open(
        widget.game,
        widget.systemFolder,
        download: download,
        onProgress: _onProgress,
      );
      if (!mounted) return;
      setState(() {
        _view = view;
        _category = _firstCategory(view);
      });
    } catch (error) {
      _log.w('Enhancements: opening ${widget.game.romname} failed: $error');
      if (mounted) setState(() => _error = error);
    } finally {
      if (mounted) {
        setState(() {
          _loading = false;
          _progress = null;
        });
      }
    }
  }

  void _onProgress(int received, int total) {
    if (!mounted || total <= 0) return;
    setState(() => _progress = (received / total).clamp(0, 1).toDouble());
  }

  List<EnhancementCategory> get _categories {
    final view = _view;
    final textures = _service.supportsTextures(widget.systemFolder);
    return [
      for (final category in EnhancementCategory.values)
        if (category == EnhancementCategory.textures
            ? textures
            : category != EnhancementCategory.performance ||
                  (view?.countIn(EnhancementCategory.performance) ?? 0) > 0)
          category,
    ];
  }

  EnhancementCategory _firstCategory(EnhancementGameView view) {
    // Libretro consoles: HD textures here, cheats in the in-game menu.
    if (view.identity.problem == EnhancementProblem.unsupportedSystem &&
        _categories.contains(EnhancementCategory.textures)) {
      return EnhancementCategory.textures;
    }
    if (view.items.isEmpty) {
      return _categories.contains(_category) ? _category : _categories.first;
    }
    for (final category in _categories) {
      if (view.countIn(category) > 0) return category;
    }
    return _categories.first;
  }

  void _cycleCategory(int delta) {
    final categories = _categories;
    if (categories.length < 2) return;
    final index = categories.indexOf(_category);
    final next = categories[(index + delta) % categories.length];
    SfxService().playNavSound();
    setState(() {
      _category = next;
      _focus = 0;
    });
    if (_scroll.hasClients) _scroll.jumpTo(0);
  }

  void _moveFocus(int delta) {
    if (_rows.isEmpty) return;
    final next = (_focus + delta).clamp(0, _rows.length - 1);
    if (next == _focus) return;
    SfxService().playNavSound();
    setState(() => _focus = next);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final ctx = _rowKeys[_rows[next].key]?.currentContext;
      if (ctx != null) {
        Scrollable.ensureVisible(
          ctx,
          alignment: 0.5,
          duration: LiquidGlassTheme.of(context).duration(context, GlassMotion.standard),
        );
      }
    });
  }

  String _categoryLabel(EnhancementCategory category) => _t(switch (category) {
    EnhancementCategory.cheat => EnhancementsLocale.catCheat,
    EnhancementCategory.fps => EnhancementsLocale.catFps,
    EnhancementCategory.ultrawide => EnhancementsLocale.catUltrawide,
    EnhancementCategory.graphics => EnhancementsLocale.catGraphics,
    EnhancementCategory.textures => EnhancementsLocale.catTextures,
    EnhancementCategory.performance => EnhancementsLocale.catPerformance,
  });

  IconData _categoryIcon(EnhancementCategory category) => switch (category) {
    EnhancementCategory.cheat => Symbols.stars_rounded,
    EnhancementCategory.fps => Symbols.speed_rounded,
    EnhancementCategory.ultrawide => Symbols.panorama_wide_angle_rounded,
    EnhancementCategory.graphics => Symbols.tune_rounded,
    EnhancementCategory.textures => Symbols.hd_rounded,
    EnhancementCategory.performance => Symbols.bolt_rounded,
  };

  String _statusLabel(EnhancementStatus status) => _t(switch (status) {
    EnhancementStatus.available => EnhancementsLocale.statusAvailable,
    EnhancementStatus.installed => EnhancementsLocale.statusInstalled,
    EnhancementStatus.active => EnhancementsLocale.statusActive,
    EnhancementStatus.incompatible => EnhancementsLocale.statusIncompatible,
  });

  String? _problemText(EnhancementProblem problem) => switch (problem) {
    EnhancementProblem.none => null,
    EnhancementProblem.unsupportedSystem => _t(EnhancementsLocale.unsupportedSystem),
    EnhancementProblem.identityUnavailable => _t(EnhancementsLocale.identityUnavailable),
    EnhancementProblem.imageFormat => _t(EnhancementsLocale.imageFormat),
    EnhancementProblem.versionUnknown => _t(EnhancementsLocale.versionUnknown),
    EnhancementProblem.versionMismatch => _t(EnhancementsLocale.versionMismatch),
    EnhancementProblem.revisionMismatch => _t(EnhancementsLocale.revisionMismatch),
    EnhancementProblem.userFilePresent => _t(EnhancementsLocale.userFilePresent),
    EnhancementProblem.notInCatalogue => _t(EnhancementsLocale.notInCatalogue),
  };

  String _errorText(Object error) {
    if (error is EnhancementException && error.code == 'user_file_present') {
      return _t(EnhancementsLocale.userFilePresent);
    }
    if (error is EnhancementException && error.code == 'version_unknown') {
      return _t(EnhancementsLocale.versionUnknown);
    }
    return _t(EnhancementsLocale.failed);
  }

  Future<void> _toggle(EnhancementItem item) async {
    final view = _view;
    if (view == null || _busy != null) return;
    final enable = item.status != EnhancementStatus.active;
    if (enable && !item.canActivate) return;
    SfxService().playNavSound();
    setState(() => _busy = item.id);
    try {
      final next = await _service.setActive(
        widget.game,
        widget.systemFolder,
        view,
        item,
        enable,
        onProgress: _onProgress,
      );
      if (mounted) setState(() => _view = next);
    } catch (error) {
      _log.w('Enhancements: switching ${item.id} failed: $error');
      if (mounted) {
        AppNotification.showNotification(context, _errorText(error), type: NotificationType.error);
      }
    } finally {
      if (mounted) {
        setState(() {
          _busy = null;
          _progress = null;
        });
      }
    }
  }

  Future<void> _install() async {
    final view = _view;
    if (view == null || _busy != null) return;
    setState(() => _busy = 'install');
    try {
      final next = await _service.install(widget.game, widget.systemFolder, view, onProgress: _onProgress);
      if (mounted) setState(() => _view = next);
    } catch (error) {
      if (mounted) {
        AppNotification.showNotification(context, _errorText(error), type: NotificationType.error);
      }
    } finally {
      if (mounted) setState(() => _busy = null);
    }
  }

  Future<void> _restore() async {
    final view = _view;
    if (view == null || _busy != null) return;
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: _t(EnhancementsLocale.restore),
      body: _t(EnhancementsLocale.restoreConfirm),
      confirmLabel: _t(EnhancementsLocale.confirm),
      cancelLabel: _t(EnhancementsLocale.cancel),
      icon: Symbols.settings_backup_restore_rounded,
    );
    if (!confirmed || !mounted) return;
    setState(() => _busy = 'restore');
    try {
      await _service.restore(view.identity.storeKey);
      if (mounted) {
        AppNotification.showNotification(
          context,
          _t(EnhancementsLocale.restoreDone),
          type: NotificationType.success,
        );
      }
    } catch (error) {
      if (mounted) {
        AppNotification.showNotification(context, _errorText(error), type: NotificationType.error);
      }
    } finally {
      if (mounted) setState(() => _busy = null);
    }
    await _load(download: true);
  }

  Future<void> _openTextures() async {
    SfxService().playNavSound();
    final opened = await TextureCatalogService.openGame(system: widget.system, game: widget.game);
    if (!opened && mounted) {
      AppNotification.showNotification(context, _t(EnhancementsLocale.failed), type: NotificationType.error);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final glass = LiquidGlassTheme.of(context);
    final children = _buildBody(theme, glass);
    if (_focus >= _rows.length) _focus = _rows.isEmpty ? 0 : _rows.length - 1;
    return GlassBackdrop(
      child: Material(
        color: Colors.transparent,
        child: SafeArea(
          child: Padding(
            padding: EdgeInsets.fromLTRB(glass.margin, glass.gap, glass.margin, glass.gap),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildHeader(theme),
                SizedBox(height: glass.gap),
                _buildCategories(),
                SizedBox(height: glass.gap),
                Expanded(
                  child: ListView(
                    controller: _scroll,
                    padding: EdgeInsets.only(bottom: glass.gap, right: 2.r),
                    children: children,
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader(ThemeData theme) {
    final view = _view;
    final identity = view?.identity;
    final details = <String>[
      if (identity != null && identity.key.isNotEmpty) identity.key,
      if (identity?.crc != null) 'CRC ${identity!.crc}',
      if (identity?.version != null) '${_t(EnhancementsLocale.gameVersion)} ${identity!.version}',
      if (identity?.revision != null) 'rev ${identity!.revision}',
    ];
    return GlassSurface(
      role: GlassRole.chrome,
      padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 6.r),
      child: Row(
        children: [
          GlassIconButton(
            icon: Symbols.arrow_back_rounded,
            tooltip: _t(EnhancementsLocale.back),
            onPressed: _close,
            sound: GlassButtonSound.back,
            size: 26.r,
          ),
          SizedBox(width: 10.r),
          Icon(Symbols.auto_fix_high_rounded, color: theme.colorScheme.primary, size: 16.r),
          SizedBox(width: 8.r),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  '${_t(EnhancementsLocale.title)} · ${widget.game.name}',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: theme.textTheme.titleLarge?.copyWith(fontSize: 13.r),
                ),
                if (details.isNotEmpty)
                  Text(
                    details.join(' · '),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodyMedium?.copyWith(
                      fontSize: 8.r,
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                    ),
                  ),
              ],
            ),
          ),
          if ((view?.activeCount ?? 0) > 0) ...[
            SizedBox(width: 8.r),
            GlassChip(
              key: const ValueKey('enhancements-active-count'),
              label: EnhancementsLocale.format(context, EnhancementsLocale.activeCount, {
                'count': view!.activeCount,
              }),
              icon: Symbols.check_circle_rounded,
              selected: true,
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildCategories() {
    final view = _view;
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: GlassSegmentedControl<EnhancementCategory>(
        key: const ValueKey('enhancements-categories'),
        dense: true,
        value: _category,
        segments: [
          for (final category in _categories)
            GlassSegment(
              value: category,
              icon: _categoryIcon(category),
              label: category == EnhancementCategory.textures || view == null || view.items.isEmpty
                  ? _categoryLabel(category)
                  : '${_categoryLabel(category)} ${view.countIn(category)}',
            ),
        ],
        onChanged: (category) => setState(() {
          _category = category;
          _focus = 0;
        }),
      ),
    );
  }

  /// Builds the list and the focusable rows in the same order.
  List<Widget> _buildBody(ThemeData theme, LiquidGlassTheme glass) {
    final rows = <_Row>[];
    final children = <Widget>[];
    void gap() => children.add(const GlassGap());
    bool focused(String key) => rows.length - 1 == _focus && rows.isNotEmpty && rows.last.key == key;

    Widget keyed(String key, Widget child) => KeyedSubtree(key: _rowKeys.putIfAbsent(key, GlobalKey.new), child: child);

    void action(String key, String label, IconData icon, VoidCallback? onTap, {bool primary = false}) {
      rows.add(_Row(key, onTap));
      children.add(
        keyed(
          key,
          GlassButton(
            key: ValueKey('enhancements-$key'),
            label: label,
            icon: icon,
            expanded: true,
            focused: focused(key),
            variant: primary ? GlassButtonVariant.primary : GlassButtonVariant.tonal,
            sound: GlassButtonSound.enter,
            onPressed: onTap,
          ),
        ),
      );
      gap();
    }

    void banner(String message, {GlassBannerKind kind = GlassBannerKind.info}) {
      children.add(GlassBanner(kind: kind, compact: true, message: message));
      gap();
    }

    final view = _view;
    if (_category == EnhancementCategory.textures) {
      if (_service.supportsTextures(widget.systemFolder)) {
        banner(_t(EnhancementsLocale.texturesNote));
        action('textures', _t(EnhancementsLocale.openTextures), Symbols.hd_rounded, _openTextures, primary: true);
      } else {
        banner(_t(EnhancementsLocale.noTextures));
      }
      _rows = rows;
      return children;
    }

    if (_loading) {
      children.add(
        Padding(
          padding: EdgeInsets.symmetric(vertical: 24.r),
          child: Column(
            children: [
              if (_progress != null)
                LinearProgressIndicator(value: _progress)
              else
                const Center(child: CircularProgressIndicator(strokeWidth: 2)),
              SizedBox(height: 8.r),
              Text(_t(EnhancementsLocale.downloading), style: theme.textTheme.bodyMedium),
            ],
          ),
        ),
      );
      _rows = rows;
      return children;
    }
    if (_error != null || view == null) {
      banner(_t(EnhancementsLocale.failed), kind: GlassBannerKind.error);
      action('retry', _t(EnhancementsLocale.download), Symbols.download_rounded, () => _load(download: true), primary: true);
      _rows = rows;
      return children;
    }

    final problem = _problemText(view.identity.problem);
    if (problem != null) {
      banner(
        problem,
        kind: view.identity.problem == EnhancementProblem.notInCatalogue
            ? GlassBannerKind.info
            : GlassBannerKind.warning,
      );
    }
    final engine = view.identity.engine;
    if (_category == EnhancementCategory.cheat && engine != EnhancementEngine.melonx) {
      banner(_t(EnhancementsLocale.inGameCheats));
    }
    if (view.identity.known && !view.downloaded) {
      action('download', _t(EnhancementsLocale.download), Symbols.download_rounded, () => _load(download: true), primary: true);
    }

    final items = view.inCategory(_category);
    if (view.downloaded) {
      if (items.isNotEmpty) {
        banner(_t(EnhancementsLocale.restartNote));
        if (_category == EnhancementCategory.fps) banner(_t(EnhancementsLocale.fpsNote));
        if (_category == EnhancementCategory.ultrawide) banner(_t(EnhancementsLocale.ultrawideNote));
        if (engine == EnhancementEngine.melonx) banner(_t(EnhancementsLocale.buildNote));
      } else {
        banner(_t(EnhancementsLocale.empty));
      }
    }

    for (final item in items) {
      final key = 'item:${item.id}';
      rows.add(_Row(key, item.canActivate || item.status == EnhancementStatus.active ? () => _toggle(item) : null));
      children.add(keyed(key, _itemBubble(theme, glass, item, focused(key))));
      gap();
    }

    if (view.identity.known && view.downloaded && !view.installed && view.items.isNotEmpty) {
      action('install', _t(EnhancementsLocale.install), Symbols.download_done_rounded, _busy == null ? _install : null);
    }
    if (view.installed || view.activeCount > 0) {
      action(
        'restore',
        _t(EnhancementsLocale.restore),
        Symbols.settings_backup_restore_rounded,
        _busy == null ? _restore : null,
      );
    }
    if (view.credits.isNotEmpty && _category == EnhancementCategory.cheat) {
      children.add(GlassSectionHeader(label: _t(EnhancementsLocale.credits)));
      for (final credit in view.credits) {
        children.add(
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 6.r, vertical: 2.r),
            child: Text(
              credit,
              style: theme.textTheme.bodySmall?.copyWith(
                fontSize: 8.r,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
              ),
            ),
          ),
        );
      }
    }
    _rows = rows;
    return children;
  }

  Widget _itemBubble(ThemeData theme, LiquidGlassTheme glass, EnhancementItem item, bool focused) {
    final busy = _busy == item.id;
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.6);
    final problem = _problemText(item.problem);
    final details = <String>[
      if (item.author.isNotEmpty) '${_t(EnhancementsLocale.author)}: ${item.author}',
      '${_t(EnhancementsLocale.source)}: ${item.sourceId}',
      '${_t(EnhancementsLocale.compatibility)}: ${item.compatibility}',
    ];
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: item.canActivate || item.status == EnhancementStatus.active ? () => _toggle(item) : null,
      child: GlassSurface(
        role: GlassRole.bubble,
        focused: focused,
        padding: glass.bubblePadding,
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          item.name,
                          style: theme.textTheme.bodyLarge?.copyWith(
                            fontSize: 11.r,
                            fontWeight: FontWeight.w500,
                            color: focused ? theme.colorScheme.primary : theme.colorScheme.onSurface,
                          ),
                        ),
                      ),
                      SizedBox(width: 6.r),
                      GlassChip(
                        label: _statusLabel(item.status),
                        selected: item.status == EnhancementStatus.active,
                        accent: item.status != EnhancementStatus.incompatible,
                      ),
                    ],
                  ),
                  if (item.description.isNotEmpty) ...[
                    SizedBox(height: 2.r),
                    Text(
                      item.description,
                      maxLines: focused ? 6 : 2,
                      overflow: TextOverflow.ellipsis,
                      style: theme.textTheme.bodyMedium?.copyWith(fontSize: 8.5.r, color: muted),
                    ),
                  ],
                  SizedBox(height: 2.r),
                  Text(
                    details.join(' · '),
                    maxLines: focused ? 4 : 1,
                    overflow: TextOverflow.ellipsis,
                    style: theme.textTheme.bodySmall?.copyWith(fontSize: 7.5.r, color: muted),
                  ),
                  if (problem != null)
                    Text(
                      problem,
                      style: theme.textTheme.bodySmall?.copyWith(fontSize: 7.5.r, color: theme.colorScheme.error),
                    ),
                  if (item.exclusiveGroup.isNotEmpty && focused)
                    Text(
                      _t(EnhancementsLocale.exclusiveNote),
                      style: theme.textTheme.bodySmall?.copyWith(fontSize: 7.5.r, color: muted),
                    ),
                ],
              ),
            ),
            SizedBox(width: 10.r),
            if (busy)
              SizedBox(
                width: 18.r,
                height: 18.r,
                child: const CircularProgressIndicator(strokeWidth: 2),
              )
            else
              CustomToggleSwitch(
                key: ValueKey('enhancements-toggle-${item.id}'),
                value: item.status == EnhancementStatus.active,
                disabled: !item.canActivate && item.status != EnhancementStatus.active,
                onChanged: (_) => _toggle(item),
              ),
          ],
        ),
      ),
    );
  }
}
