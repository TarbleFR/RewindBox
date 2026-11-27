import 'dart:async';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:url_launcher/url_launcher.dart';

import '../l10n/wiimmfi_locale.dart';
import '../services/dolphin_internal_v2_service.dart';
import '../services/dolphin_system_files.dart';
import '../services/gamepad/gamepad_navigation_manager.dart';
import '../services/wiimmfi/wiimmfi_catalog.dart';
import '../services/wiimmfi/wiimmfi_service.dart';
import '../utils/gamepad_nav.dart';
import 'confirm_action_dialog.dart';
import 'wiimmfi_dialog_controls.dart';

class WiimmfiPanel extends StatefulWidget {
  const WiimmfiPanel({super.key, this.gamePath, this.onLaunch});

  final String? gamePath;
  final Future<String?> Function(bool online)? onLaunch;

  static Future<void> open(
    BuildContext context, {
    String? gamePath,
    Future<String?> Function(bool online)? onLaunch,
  }) => showDialog<void>(
    context: context,
    barrierDismissible: false,
    builder: (_) => WiimmfiPanel(gamePath: gamePath, onLaunch: onLaunch),
  );

  @override
  State<WiimmfiPanel> createState() => _WiimmfiPanelState();
}

class _WiimmfiPanelState extends State<WiimmfiPanel>
    with WidgetsBindingObserver {
  final _scroll = ScrollController();
  final _focus = FocusNode();
  final _itemKeys = <String, GlobalKey>{};
  final _actions = <String, VoidCallback?>{};
  late final String _navigationId;
  late final GamepadNavigation _navigation;
  bool _registered = false;
  bool _layerActive = false;
  bool _busy = false;
  bool _importing = false;
  bool _cancelling = false;
  String? _selected = 'enabled';
  String _code = '';
  Map<String, dynamic>? _settings;
  Map<String, dynamic>? _status;
  Map<String, dynamic>? _progress;
  Map<String, dynamic>? _identity;
  String? _message;
  Timer? _timer;

  String t(String key) => WiimmfiLocale.text(context, key);
  bool get _current => mounted && ModalRoute.of(context)?.isCurrent == true;
  bool get _canCancel =>
      _importing &&
      !_cancelling &&
      WiimmfiService.importPhase.value != 'committing' &&
      WiimmfiService.importPhase.value != 'idle';

  @override
  void initState() {
    super.initState();
    _navigationId = 'wiimmfi_${identityHashCode(this)}';
    _navigation = GamepadNavigation(
      onNavigateUp: () => _move(-1),
      onNavigateDown: () => _move(1),
      onSelectItem: _select,
      onBack: _back,
      allowRepeat: false,
      isTextFieldFocused: () => false,
    );
    WidgetsBinding.instance.addObserver(this);
    WiimmfiService.importPhase.addListener(_phaseChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _navigation.initialize();
      _registered = true;
      GamepadNavigationManager.pushLayer(
        _navigationId,
        modal: true,
        onActivate: () {
          _layerActive = true;
          _refreshNavigation();
        },
        onDeactivate: () {
          _layerActive = false;
          _navigation.deactivate();
        },
      );
    });
    unawaited(_load());
  }

  void _refreshNavigation() {
    final lifecycle = WidgetsBinding.instance.lifecycleState;
    if (_layerActive &&
        _current &&
        (lifecycle == null || lifecycle == AppLifecycleState.resumed) &&
        !(_importing && WiimmfiService.importPhase.value == 'selecting')) {
      _navigation.activate();
      _focus.requestFocus();
    } else {
      _navigation.deactivate();
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) =>
      _refreshNavigation();

  void _phaseChanged() {
    if (!mounted) return;
    setState(() {});
    _refreshNavigation();
  }

  @override
  void dispose() {
    _timer?.cancel();
    WiimmfiService.importPhase.removeListener(_phaseChanged);
    WidgetsBinding.instance.removeObserver(this);
    if (_registered) GamepadNavigationManager.popLayer(_navigationId);
    _navigation.dispose();
    _scroll.dispose();
    _focus.dispose();
    super.dispose();
  }

  void _move(int delta) {
    if (!_current) return;
    final enabled = _actions.keys
        .where((key) => _actions[key] != null)
        .toList();
    if (enabled.isEmpty) return;
    final index = enabled.indexOf(_selected ?? '');
    setState(() {
      _selected = enabled[index < 0 ? 0 : (index + delta) % enabled.length];
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final itemContext = _itemKeys[_selected]?.currentContext;
      if (itemContext != null) {
        Scrollable.ensureVisible(
          itemContext,
          alignment: 0.5,
          duration: const Duration(milliseconds: 180),
        );
      }
    });
  }

  void _select() {
    if (_current) _actions[_selected]?.call();
  }

  void _back() {
    if (!_current) return;
    if (_busy) {
      if (_canCancel) unawaited(_cancelImport());
      return;
    }
    Navigator.of(context).maybePop();
  }

  Future<void> _load() async {
    try {
      await DolphinInternalV2Service.ensureLayout();
      final settings = await WiimmfiService.settings();
      final status = await WiimmfiService.status();
      Map<String, dynamic>? identity;
      if (widget.gamePath != null && status['supported'] == true) {
        try {
          identity = await WiimmfiService.identity(widget.gamePath!);
        } catch (_) {
          // Remains unknown.
        }
      }
      if (mounted) {
        setState(() {
          _settings = settings;
          _status = status;
          _identity = identity;
        });
      }
    } catch (error) {
      if (mounted) setState(() => _message = _error(error));
    }
  }

  String _error(Object error) {
    final key = switch (error) {
      WiimmfiException e => e.code,
      DolphinSystemFilesException e => e.code,
      _ => 'error',
    };
    return WiimmfiLocale.labels(Localizations.localeOf(context))[key] ??
        t('error');
  }

  Future<void> _run(Future<void> Function() action) async {
    if (_busy || !_current) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      await _load();
      if (mounted) {
        setState(() => _busy = false);
        _refreshNavigation();
      }
    }
  }

  Future<bool> _confirm(String key) => ConfirmActionDialog.show(
    context,
    title: 'Wiimmfi',
    body: t(key),
    confirmLabel: t('continue'),
    cancelLabel: t('cancel'),
    icon: Icons.public,
    accentColor: Theme.of(context).colorScheme.primary,
  );

  Future<void> _cancelImport() async {
    if (!_canCancel || !_current) return;
    setState(() => _cancelling = true);
    try {
      await WiimmfiService.cancelImport();
    } catch (error) {
      if (mounted) setState(() => _message = _error(error));
    } finally {
      if (mounted) setState(() => _cancelling = false);
    }
  }

  Future<void> _import() => _run(() async {
    if (!await _confirm('importHelp') || !mounted) return;
    setState(() {
      _importing = true;
      _progress = null;
    });
    var polling = false;
    _timer = Timer.periodic(const Duration(milliseconds: 400), (_) async {
      if (polling) return;
      polling = true;
      try {
        final progress = await WiimmfiService.importProgress();
        if (mounted && _importing) setState(() => _progress = progress);
      } catch (_) {
        // The import itself reports errors.
      } finally {
        polling = false;
      }
    });
    try {
      if (await WiimmfiService.importBootMii() && mounted) {
        setState(() => _message = t('imported'));
      }
    } finally {
      _timer?.cancel();
      _timer = null;
      if (mounted) setState(() => _importing = false);
      _refreshNavigation();
    }
  });

  Future<void> _open(String url) async {
    // The system browser owns input while the app is inactive. An in-app
    // browser's Future ends at first load rather than at dismissal.
    if (!await launchUrl(
          Uri.parse(url),
          mode: LaunchMode.externalApplication,
        ) &&
        mounted) {
      setState(() => _message = t('error'));
    }
  }

  Future<void> _launch(bool online) => _run(() async {
    final message = await widget.onLaunch!(online);
    if (mounted && message != null) setState(() => _message = message);
  });

  Future<void> _showMessage(String title, String message) => showWiimmfiMessage(
    context,
    title: title,
    message: message,
    closeLabel: t('close'),
  );

  Future<void> _diagnose() => _run(() async {
    final result = await WiimmfiService.diagnose();
    if (!mounted) return;
    await _showMessage(
      t('diagnose'),
      [
        '${t('nand')}: ${t(result['nandRecognized'] == true ? 'recognized' : 'nandMissing')}',
        if (result['supported'] != true) t('engineUnavailable'),
        for (final key in [
          'dns',
          'website',
          'servers',
          'players',
          'authentication',
          'matchmaking',
        ])
          '${t(key)}: ${t(result[key]?.toString() ?? 'unknown')}',
        if (result['httpStatus'] != null) 'HTTP ${result['httpStatus']}',
        result['checkedAt']?.toString() ?? '',
      ].join('\n'),
    );
  });

  Future<void> _lookupCode() => _run(() async {
    final code = await editWiimmfiErrorCode(
      context,
      initialCode: _code,
      title: t('code'),
      confirmLabel: t('lookup'),
      cancelLabel: t('cancel'),
    );
    if (!mounted || code == null) return;
    setState(() {
      _code = code;
      _message = '$code: ${t(WiimmfiLocale.errorKey(code))}';
    });
    await _open('https://wiimmfi.de/error?e=$code');
  });

  Widget _button(
    String id,
    String label,
    IconData icon,
    VoidCallback? action, {
    bool allowWhileBusy = false,
    Widget? trailing,
  }) {
    final callback = !_busy || allowWhileBusy ? action : null;
    _actions[id] = callback;
    return Builder(
      builder: (context) => ListTile(
        key: _itemKeys.putIfAbsent(id, () => GlobalKey()),
        selected: _selected == id && callback != null,
        selectedTileColor: Theme.of(context).colorScheme.primaryContainer,
        leading: Icon(icon),
        title: Text(label),
        trailing: trailing,
        enabled: callback != null,
        onTap: callback == null
            ? null
            : () {
                if (!_current) return;
                setState(() => _selected = id);
                callback();
              },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final enabled = _settings?['enabled'] == true;
    final supported = _status?['supported'] == true;
    final imageKey = widget.gamePath == null
        ? null
        : p.normalize(p.absolute(widget.gamePath!));
    final images = _settings?['images'];
    final declared = images is Map && images[imageKey] is Map;
    _actions.clear();
    final controls = <Widget>[
      Text(t('intro')),
      if (_status != null && !supported) Text(t('engineUnavailable')),
      _button(
        'enabled',
        t('enabled'),
        Icons.public,
        supported || enabled
            ? () => _run(() => WiimmfiService.setEnabled(!enabled))
            : null,
        trailing: Switch.adaptive(
          value: enabled,
          onChanged: !_busy && (supported || enabled)
              ? (value) => _run(() => WiimmfiService.setEnabled(value))
              : null,
        ),
      ),
      ListTile(
        leading: const Icon(Icons.memory),
        title: Text(t('nand')),
        subtitle: Text(
          t(_status?['nandRecognized'] == true ? 'recognized' : 'nandMissing'),
        ),
      ),
      _button(
        'importNand',
        t('importNand'),
        Icons.file_open,
        supported ? _import : null,
      ),
      if (_importing) ...[
        LinearProgressIndicator(
          value: _progress?['percent'] == null
              ? null
              : ((_progress!['percent'] as num).toDouble() / 100).clamp(0, 1),
        ),
        Text(
          '${t(_progress?['phase']?.toString() ?? 'importNand')}${_progress?['percent'] == null ? '' : ' · ${_progress!['percent']}%'}',
        ),
        _button(
          'cancel',
          t('cancel'),
          Icons.cancel_outlined,
          _canCancel ? () => unawaited(_cancelImport()) : null,
          allowWhileBusy: true,
        ),
      ],
      if (widget.gamePath != null) ...[
        if (_identity != null)
          Text(
            '${_identity!['gameId']} · ${_identity!['region']} · r${_identity!['revision']}',
          ),
        if (declared) Text(t('declared')),
        _button(
          'patch',
          t('patch'),
          Icons.verified_user_outlined,
          supported
              ? () => _run(() async {
                  if (await _confirm('patchHelp') && mounted) {
                    await WiimmfiService.registerPatchedImage(widget.gamePath!);
                  }
                })
              : null,
        ),
        _button(
          'launch',
          t('launch'),
          Icons.public,
          supported &&
                  enabled &&
                  declared &&
                  _status?['nandRecognized'] == true &&
                  widget.onLaunch != null
              ? () => _launch(true)
              : null,
        ),
        _button(
          'offline',
          t('offline'),
          Icons.videogame_asset,
          supported && widget.onLaunch != null ? () => _launch(false) : null,
        ),
      ],
      _button(
        'diagnose',
        t('diagnose'),
        Icons.network_check,
        enabled ? _diagnose : null,
      ),
      _button(
        'games',
        t('games'),
        Icons.sports_esports,
        () => _run(
          () => _showMessage(
            t('games'),
            [
              t('catalogHelp'),
              for (final game in WiimmfiCatalog.candidates)
                '${game.name}: ${t('notTested')}',
            ].join('\n\n'),
          ),
        ),
      ),
      _button(
        'officialStats',
        t('officialStats'),
        Icons.query_stats,
        () => _run(() => _open('https://wiimmfi.de/stat')),
      ),
      _button(
        'documentation',
        t('documentation'),
        Icons.help_outline,
        () => _run(() => _open('https://wiimmfi.de/patcher')),
      ),
      _button(
        'code',
        _code.isEmpty ? t('code') : '${t('code')}: $_code',
        Icons.pin,
        _lookupCode,
      ),
      _button(
        'clear',
        t('clear'),
        Icons.settings_backup_restore,
        () => _run(() async {
          if (await _confirm('clearHelp') && mounted) {
            await WiimmfiService.clear();
          }
        }),
      ),
      if (_busy && !_importing) const LinearProgressIndicator(),
      if (_message != null)
        Padding(padding: const EdgeInsets.all(8), child: Text(_message!)),
    ];
    final close = _button('close', t('close'), Icons.close, _back);
    final available = _actions.keys.where((id) => _actions[id] != null);
    if (_settings != null && _actions[_selected] == null) {
      _selected = available.firstOrNull;
    }
    return PopScope(
      canPop: !_busy,
      child: Focus(
        focusNode: _focus,
        autofocus: true,
        // The global navigator owns keyboard actions. Do not let a focused
        // Material button activate a second command for the same key.
        onKeyEvent: (_, _) =>
            _current ? KeyEventResult.handled : KeyEventResult.ignored,
        child: ExcludeFocus(
          child: AlertDialog(
            title: const Text('Wiimmfi'),
            content: SizedBox(
              width: 600,
              child: SingleChildScrollView(
                controller: _scroll,
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: controls,
                ),
              ),
            ),
            actions: [close],
          ),
        ),
      ),
    );
  }
}
