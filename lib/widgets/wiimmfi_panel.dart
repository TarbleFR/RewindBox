import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:path/path.dart' as p;
import 'package:share_plus/share_plus.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/wiimmfi_locale.dart';
import '../services/dolphin_internal_v2_service.dart';
import '../services/dolphin_system_files.dart';
import '../services/gamepad/gamepad_navigation_manager.dart';
import '../services/wiimmfi/wiimmfi_catalog.dart';
import '../services/wiimmfi/wiimmfi_service.dart';
import '../utils/gamepad_nav.dart';
import 'confirm_action_dialog.dart';
import 'online_service_widgets.dart';
import 'wiimmfi_dialog_controls.dart';

class WiimmfiPanel extends StatefulWidget {
  const WiimmfiPanel({super.key, this.gamePath, this.onLaunch});

  final String? gamePath;
  final Future<String?> Function(bool online)? onLaunch;

  static Future<void> open(
    BuildContext context, {
    String? gamePath,
    Future<String?> Function(bool online)? onLaunch,
  }) async {
    final route = DialogRoute<void>(
      context: context,
      barrierDismissible: false,
      builder: (_) => WiimmfiPanel(gamePath: gamePath, onLaunch: onLaunch),
    );
    await Navigator.of(context, rootNavigator: true).push(route);
    await route.completed;
  }

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
  String? _selected = 'console';
  bool _showAdvanced = false;
  bool _showGames = false;
  bool _loading = true;
  int _loadGeneration = 0;
  String _code = '';
  Map<String, dynamic>? _settings;
  Map<String, dynamic>? _status;
  Map<String, dynamic>? _progress;
  Map<String, dynamic>? _identity;
  String? _message;
  bool _messageIsError = false;
  Timer? _timer;

  String t(String key) => WiimmfiLocale.text(context, key);
  bool get _nandReady => _status?['nandRecognized'] == true;
  bool get _tlsRejected => _status?['tlsFilesValid'] == false;
  bool get _declared {
    final images = _settings?['images'];
    final path = widget.gamePath;
    return path != null &&
        images is Map &&
        images[p.normalize(p.absolute(path))] is Map;
  }

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
    final generation = ++_loadGeneration;
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
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _settings = settings;
          _status = status;
          _identity = identity;
        });
      }
    } catch (error) {
      if (mounted && generation == _loadGeneration) {
        setState(() {
          _message = _error(error);
          _messageIsError = true;
        });
      }
    } finally {
      if (mounted && generation == _loadGeneration) {
        setState(() => _loading = false);
      }
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
      _messageIsError = false;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) {
        setState(() {
          _message = _error(error);
          _messageIsError =
              !(error is WiimmfiException && error.code == 'cancelled');
        });
      }
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
      if (mounted) {
        setState(() {
          _message = _error(error);
          _messageIsError =
              !(error is WiimmfiException && error.code == 'cancelled');
        });
      }
    } finally {
      if (mounted) setState(() => _cancelling = false);
    }
  }

  Future<void> _import() => _run(() async {
    await _importConsole();
  });

  Future<bool> _importConsole() async {
    if (!await _confirm('importHelp') || !mounted) return false;
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
      final imported = await WiimmfiService.importBootMii();
      if (imported && mounted) setState(() => _message = t('imported'));
      return imported;
    } finally {
      _timer?.cancel();
      _timer = null;
      if (mounted) setState(() => _importing = false);
      _refreshNavigation();
    }
  }

  Future<bool> _declareGame() async {
    if (!await _confirm('patchHelp') || !mounted) return false;
    await WiimmfiService.registerPatchedImage(widget.gamePath!);
    return true;
  }

  Future<void> _setOnline(bool value) => _run(() async {
    if (value) {
      if (_status?['supported'] != true) {
        throw const WiimmfiException('engineUnavailable');
      }
      // Like Nextendo's switch, complete the missing preparation first.
      if (!_nandReady && !await _importConsole()) return;
      if (!mounted) return;
      if ((await WiimmfiService.status())['nandRecognized'] != true) {
        throw const WiimmfiException('nandMissing');
      }
      if (widget.gamePath != null && !_declared && !await _declareGame()) {
        return;
      }
    }
    await WiimmfiService.setEnabled(value);
  });

  String _servicesLine(bool enabled, bool supported) {
    if (_loading) return t('servicesChecking');
    if (_settings == null) return _message ?? t('error');
    if (!supported) return t('engineUnavailable');
    if (!_nandReady) return t('servicesPrepareConsole');
    if (_tlsRejected) return t('tlsFilesRejected');
    if (!enabled) return t('servicesOff');
    if (widget.gamePath == null) return t('servicesConsolePrepared');
    if (widget.gamePath != null && !_declared) return t('servicesPrepareGame');
    return t('servicesPrepared');
  }

  Future<void> _open(String url) async {
    // The system browser owns input while the app is inactive. An in-app
    // browser's Future ends at first load rather than at dismissal.
    if (!await launchUrl(
          Uri.parse(url),
          mode: LaunchMode.externalApplication,
        ) &&
        mounted) {
      setState(() {
        _message = t('error');
        _messageIsError = true;
      });
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
        if (result['tlsFilesValid'] case final bool valid)
          t(valid ? 'tlsFilesAccepted' : 'tlsFilesRejected'),
        if (result['bootNand'] == 3) t('identityLoaded'),
        if (result['bootNand'] == -3 || result['bootNand'] == -4)
          t('identityNotLoaded'),
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
        'TLS: ${t(result['websiteTls']?.toString() ?? 'unknown')}',
        if (result['httpStatus'] != null) 'HTTP ${result['httpStatus']}',
        result['checkedAt']?.toString() ?? '',
      ].join('\n'),
    );
  });

  Future<void> _exportDiagnostic() => _run(() async {
    final status = await WiimmfiService.diagnosticSnapshot();
    if (!mounted) return;
    final data = WiimmfiService.diagnosticReport(status, enteredCode: _code);
    final renderBox = context.findRenderObject() as RenderBox?;
    const name = 'rewindbox-wiimmfi-diagnostic.json';
    await SharePlus.instance.share(
      ShareParams(
        files: [
          XFile.fromData(
            Uint8List.fromList(
              utf8.encode(const JsonEncoder.withIndent('  ').convert(data)),
            ),
            mimeType: 'application/json',
          ),
        ],
        fileNameOverrides: const [name],
        sharePositionOrigin: renderBox == null || !renderBox.hasSize
            ? null
            : renderBox.localToGlobal(Offset.zero) & renderBox.size,
      ),
    );
  });

  Future<void> _prepareGameHelp() => _run(() async {
    if (await _confirm('prepareGameHelp') && mounted) {
      await _open('https://wiimmfi.de/patcher/iso');
    }
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

  Widget _control(
    String id,
    VoidCallback? action,
    Widget Function(VoidCallback? callback) build, {
    bool allowWhileBusy = false,
  }) {
    final callback = !_busy || allowWhileBusy ? action : null;
    _actions[id] = callback;
    return Builder(
      builder: (context) {
        final selected = _selected == id && callback != null;
        return Semantics(
          key: _itemKeys.putIfAbsent(id, () => GlobalKey()),
          selected: selected,
          child: Material(
            color: selected
                ? Theme.of(context).colorScheme.primaryContainer
                : Colors.transparent,
            borderRadius: BorderRadius.circular(8),
            child: build(
              callback == null
                  ? null
                  : () {
                      if (!_current) return;
                      setState(() => _selected = id);
                      callback();
                    },
            ),
          ),
        );
      },
    );
  }

  Widget _button(
    String id,
    String label,
    IconData icon,
    VoidCallback? action, {
    bool allowWhileBusy = false,
    Widget? trailing,
    String? subtitle,
  }) => _control(
    id,
    action,
    (callback) => ListTile(
      contentPadding: EdgeInsets.zero,
      selected: _selected == id && callback != null,
      leading: Icon(icon),
      title: Text(label),
      subtitle: subtitle == null ? null : Text(subtitle),
      trailing: trailing,
      enabled: callback != null,
      onTap: callback,
    ),
    allowWhileBusy: allowWhileBusy,
  );

  @override
  Widget build(BuildContext context) {
    final enabled = _settings?['enabled'] == true;
    final supported = _status?['supported'] == true;
    final declared = _declared;
    _actions.clear();
    final controls = <Widget>[
      Text(t('simpleIntro')),
      const SizedBox(height: 12),
      if (_loading && _message == null)
        const Center(child: CircularProgressIndicator()),
      _control(
        'console',
        supported ? _import : null,
        (callback) => OnlineServiceIdentitySection(
          actionKey: const ValueKey('wiimmfi-console'),
          actionLabel: t(_nandReady ? 'changeConsole' : 'prepareConsole'),
          actionIcon: Icons.download_for_offline_outlined,
          onAction: callback,
          identityTitle: _nandReady ? t('consolePrepared') : null,
          identitySubtitle: _nandReady ? t('consolePreparedDetail') : null,
          identityIcon: Icons.videogame_asset,
        ),
      ),
      _control(
        'enabled',
        supported || enabled ? () => _setOnline(!enabled) : null,
        (callback) => OnlineServicesSwitch(
          key: const ValueKey('wiimmfi-online-services'),
          title: t('onlineServices'),
          status: _servicesLine(enabled, supported),
          value: enabled,
          checking: _loading,
          problem:
              enabled &&
              (!supported ||
                  !_nandReady ||
                  _tlsRejected ||
                  (widget.gamePath != null && !declared)),
          onChanged: callback == null ? null : (_) => callback(),
        ),
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
        const SizedBox(height: 8),
        if (!declared)
          _button(
            'patcher',
            t('officialPatcher'),
            Icons.open_in_new,
            _prepareGameHelp,
          ),
        if (declared)
          ListTile(
            contentPadding: EdgeInsets.zero,
            leading: const Icon(Icons.check_circle_outline),
            title: Text(t('gamePrepared')),
            subtitle: Text(t('declared')),
          )
        else
          _button(
            'patch',
            t('patch'),
            Icons.verified_user_outlined,
            supported
                ? () => _run(() async {
                    await _declareGame();
                  })
                : null,
            subtitle: t('gameSetup'),
          ),
        _button(
          'launch',
          t('launch'),
          Icons.public,
          supported &&
                  enabled &&
                  declared &&
                  _nandReady &&
                  !_tlsRejected &&
                  widget.onLaunch != null
              ? () => _launch(true)
              : null,
        ),
        _button(
          'offline',
          t('offline'),
          Icons.videogame_asset,
          (supported || _status?['abi'] == 4) && widget.onLaunch != null
              ? () => _launch(false)
              : null,
        ),
      ],
      const SizedBox(height: 8),
      _button(
        'games',
        t('games'),
        Icons.sports_esports,
        () => setState(() => _showGames = !_showGames),
        trailing: Icon(_showGames ? Icons.expand_less : Icons.expand_more),
      ),
      if (_showGames) ...[
        Text(t('catalogHelp')),
        for (final (index, game) in WiimmfiCatalog.candidates.indexed)
          _button(
            'candidate-$index',
            game.name,
            Icons.videogame_asset,
            () => _run(() => _showMessage(game.name, t('catalogHelp'))),
            subtitle: t('notTested'),
          ),
      ],
      _button(
        'advanced',
        t('advanced'),
        Icons.tune,
        () => setState(() => _showAdvanced = !_showAdvanced),
        trailing: Icon(_showAdvanced ? Icons.expand_less : Icons.expand_more),
      ),
      if (_showAdvanced) ...[
        ListTile(
          contentPadding: EdgeInsets.zero,
          leading: const Icon(Icons.memory),
          title: Text(t('nand')),
          subtitle: Text(t(_nandReady ? 'recognized' : 'nandMissing')),
        ),
        if (_identity != null)
          Text(
            '${_identity!['gameId']} · ${_identity!['region']} · r${_identity!['revision']}',
          ),
        if (declared) ...[
          Text(t('declared')),
          _button(
            'patch',
            t('patch'),
            Icons.verified_user_outlined,
            supported
                ? () => _run(() async {
                    await _declareGame();
                  })
                : null,
          ),
        ],
        _button(
          'diagnose',
          t('diagnose'),
          Icons.network_check,
          enabled ? _diagnose : null,
        ),
        _button(
          'exportDiagnostic',
          t('exportDiagnostic'),
          Icons.ios_share,
          _exportDiagnostic,
        ),
        _button(
          'code',
          _code.isEmpty ? t('code') : '${t('code')}: $_code',
          Icons.pin,
          _lookupCode,
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
          'clear',
          t('clear'),
          Icons.settings_backup_restore,
          () => _run(() async {
            if (await _confirm('clearHelp') && mounted) {
              await WiimmfiService.clear();
            }
          }),
        ),
      ],
      if (_busy && !_importing) const LinearProgressIndicator(),
      if (_message != null)
        Padding(
          padding: const EdgeInsets.only(top: 8),
          child: Text(
            _message!,
            style: _messageIsError
                ? TextStyle(color: Theme.of(context).colorScheme.error)
                : null,
          ),
        ),
    ];
    final close = _control(
      'close',
      _back,
      (callback) => TextButton(onPressed: callback, child: Text(t('close'))),
    );
    final available = _actions.keys.where((id) => _actions[id] != null);
    if (_settings != null && _actions[_selected] == null) {
      _selected = available.firstOrNull;
    }
    return PopScope(
      canPop: !_busy,
      child: Focus(
        focusNode: _focus,
        autofocus: true,
        onKeyEvent: (_, _) =>
            _current ? KeyEventResult.handled : KeyEventResult.ignored,
        child: ExcludeFocus(
          child: AlertDialog(
            title: const Text('Wiimmfi'),
            content: SizedBox(
              width: 480,
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
