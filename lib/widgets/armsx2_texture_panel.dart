import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../l10n/armsx2_texture_locale.dart';
import '../services/armsx2_texture_service.dart';
import '../services/gamepad/gamepad_navigation_manager.dart';
import '../services/rpcs3_save_exchange_service.dart';
import '../utils/gamepad_nav.dart';
import 'confirm_action_dialog.dart';
import 'settings_rows.dart';

/// "HD textures" section of a PS2 game's settings (Build 485).
///
/// Three things are shown apart: the pack installed in
/// `ARMSX2/textures/<serial>/replacements`, NeoStation's switch for the game
/// (written into the game's ARMSX2 settings when it starts) and, only in the
/// game's pause menu, what the engine recognized and loaded. An import here
/// checks files; it never claims that the game uses them.
///
/// Rows are driven by the parent tab's gamepad navigation: [selectedRow]
/// highlights one, [Armsx2TexturePanelState.activateRow] runs it.
class Armsx2TexturePanel extends StatefulWidget {
  const Armsx2TexturePanel({
    super.key,
    required this.gamePath,
    this.selectedRow = -1,
    this.client = const Armsx2TextureChannelClient(),
    this.onRowsChanged,
  });

  final String gamePath;
  final int selectedRow;
  final Armsx2TextureClient client;
  final VoidCallback? onRowsChanged;

  static const Key switchKey = ValueKey('armsx2-hd-textures-toggle');
  static Key rowKey(String row) => ValueKey('armsx2-hd-textures-$row');

  @override
  State<Armsx2TexturePanel> createState() => Armsx2TexturePanelState();
}

class Armsx2TexturePanelState extends State<Armsx2TexturePanel> {
  Map<String, dynamic>? _status;
  bool _busy = false;
  bool _confirming = false;
  String? _token;
  double _fraction = 0;
  String _phase = '';
  String? _message;
  StreamSubscription<Map<String, dynamic>>? _progress;

  String _t(String key) => Armsx2TextureLocale.text(context, key);
  String _f(String key, Map<String, Object?> values) =>
      Armsx2TextureLocale.format(context, key, values);

  Map<String, dynamic> get _game => _map(_status?['game']);
  Map<String, dynamic> get _pack => _map(_status?['pack']);
  String get _serial => (_game['serial'] as String?) ?? '';
  bool get _installed => _pack['installed'] == true;
  bool get _sessionActive => _status?['sessionActive'] == true;

  static Map<String, dynamic> _map(Object? value) =>
      value is Map ? Map<String, dynamic>.from(value) : const {};

  /// The actionable rows, in order: the switch, the two imports, removal
  /// when a pack is installed, the help. While importing: only cancel.
  List<String> get rows => _busy
      ? const ['cancel']
      : [
          'switch',
          'importFolder',
          'importArchive',
          if (_installed) 'remove',
          'help',
        ];

  @override
  void initState() {
    super.initState();
    _progress = widget.client.progress.listen((event) {
      if (!mounted || event['token'] != _token) return;
      setState(() {
        _fraction = (event['fraction'] as num?)?.toDouble() ?? 0;
        _phase = (event['phase'] as String?) ?? '';
      });
    });
    _reload();
  }

  @override
  void dispose() {
    _progress?.cancel();
    final token = _token;
    if (token != null) {
      widget.client.cancel(token);
      widget.client.discard(token);
    }
    super.dispose();
  }

  Future<void> _reload() async {
    final status = await widget.client.status(widget.gamePath);
    if (!mounted) return;
    setState(() => _status = status);
    widget.onRowsChanged?.call();
  }

  void _setBusy(bool busy) {
    setState(() {
      _busy = busy;
      _fraction = 0;
      _phase = '';
    });
    widget.onRowsChanged?.call();
  }

  /// Runs a row chosen with the gamepad (A) or a touch.
  Future<void> activateRow(int index) async {
    final list = rows;
    if (index < 0 || index >= list.length) return;
    switch (list[index]) {
      case 'cancel':
        final token = _token;
        if (token != null) await widget.client.cancel(token);
      case 'switch':
        await _toggle();
      case 'importFolder':
        await _import(folder: true);
      case 'importArchive':
        await _import(folder: false);
      case 'remove':
        await _remove();
      case 'help':
        await _showHelp();
    }
  }

  String _errorText(Map<String, dynamic> result) {
    return _f(Armsx2TextureErrors.keyFor(result['error']), {
      'detail': result['detail'] ?? '',
      'serial': (result['gameSerial'] as String?)?.isNotEmpty == true
          ? result['gameSerial']
          : _serial,
      'needed': _bytes(result['needed']),
      'available': _bytes(result['available']),
    });
  }

  static String _bytes(Object? value) =>
      Rpcs3SaveExchangeService.formatBytes(value is num ? value.toInt() : 0);

  /// NeoStation's choice; without one, the game's own settings or the global
  /// ARMSX2 default (off unless set elsewhere).
  bool get _switchOn {
    final choice = _pack['enabled'];
    if (choice is bool) return choice;
    final ini = _pack['iniEnabled'];
    if (ini is bool) return ini;
    return _pack['globalEnabled'] == true;
  }

  /// The choice is saved but the game's settings still hold the other value
  /// (or are not known yet): it takes effect when the game starts.
  bool get _pending {
    final choice = _pack['enabled'];
    return choice is bool && _pack['iniEnabled'] != choice;
  }

  Future<void> _toggle() async {
    if (_serial.isEmpty || _sessionActive) {
      setState(
        () => _message = _t(
          _sessionActive ? 'errSessionActive' : 'errGameUnknown',
        ),
      );
      return;
    }
    final result = await widget.client.setEnabled(widget.gamePath, !_switchOn);
    if (!mounted) return;
    setState(() {
      _message = result['success'] == true
          ? _t((result['message'] as String?) ?? 'enabledNext')
          : _errorText(result);
    });
    await _reload();
  }

  String _label(String serial, String region) =>
      region.isEmpty ? serial : '$serial ($region)';

  String confirmationText(Map<String, dynamic> inspection) {
    final serial = (inspection['gameSerial'] as String?) ?? '';
    final game = _label(serial, (inspection['gameRegion'] as String?) ?? '');
    final lines = <String>[];
    switch (inspection['match']) {
      case 'otherSerial':
        lines.add(
          _f('confirmOther', {
            'pack': _label(
              (inspection['packSerial'] as String?) ?? '',
              (inspection['packRegion'] as String?) ?? '',
            ),
            'game': game,
          }),
        );
      case 'noSerial':
        lines.add(_f('confirmNoSerial', {'game': game}));
    }
    if (inspection['regionConflict'] == true) {
      lines.add(
        _f('confirmRegion', {
          'regions': ((inspection['regions'] as List?) ?? const []).join(', '),
          'region': inspection['gameRegion'] ?? '',
        }),
      );
    }
    if (inspection['crcConflict'] == true) {
      lines.add(
        _f('confirmCrc', {
          'crcs': ((inspection['crcs'] as List?) ?? const []).join(', '),
          'crc': inspection['gameCrc'] ?? '',
        }),
      );
    }
    if (inspection['uncertain'] == true) {
      lines.add(_f('confirmUncertain', {'serial': serial}));
    }
    if (inspection['needsConfirmation'] == true) {
      lines.add(_t('confirmMatching'));
    }
    if (inspection['replacing'] == true) lines.add(_t('confirmReplace'));
    return lines.join('\n\n');
  }

  Future<void> _import({required bool folder}) async {
    if (_sessionActive) {
      setState(() => _message = _t('errSessionActive'));
      return;
    }
    _setBusy(true);
    setState(() => _message = null);
    final inspection = await widget.client.pick(
      widget.gamePath,
      folder: folder,
    );
    if (!mounted) return;
    final token = inspection['token'] as String?;
    if (inspection['success'] != true || token == null) {
      if (token != null) await widget.client.discard(token);
      setState(() {
        _message = inspection['cancelled'] == true
            ? null
            : _errorText(inspection);
      });
      _setBusy(false);
      return;
    }
    _token = token;
    final needsConfirmation = inspection['needsConfirmation'] == true;
    if (needsConfirmation || inspection['replacing'] == true) {
      // Nothing runs while the user decides: no progress animation.
      setState(() => _confirming = true);
      final confirmed = await ConfirmActionDialog.show(
        context,
        title: _t('confirmTitle'),
        body: confirmationText(inspection),
        confirmLabel: _f('confirmInstall', {
          'serial': inspection['gameSerial'] ?? '',
        }),
        cancelLabel: _t('cancel'),
        icon: Symbols.texture_rounded,
        accentColor: Theme.of(context).colorScheme.secondary,
      );
      if (!mounted) return;
      setState(() => _confirming = false);
      if (!confirmed) {
        await widget.client.discard(token);
        _token = null;
        _setBusy(false);
        return;
      }
    }
    final result = await widget.client.install(
      token,
      allowMismatch: needsConfirmation,
    );
    await widget.client.discard(token);
    _token = null;
    if (!mounted) return;
    setState(() => _message = _installText(result));
    _setBusy(false);
    await _reload();
  }

  String _installText(Map<String, dynamic> result) {
    if (result['success'] != true) return _errorText(result);
    final lines = <String>[
      _f(result['replaced'] == true ? 'replaced' : 'installed', {
        'serial': result['serial'] ?? '',
        'named': result['named'] ?? 0,
        'size': _bytes(result['bytes']),
      }),
    ];
    final unsupported = (result['unsupported'] as num?)?.toInt() ?? 0;
    if (unsupported > 0) {
      lines.add(
        _f('resultUnsupported', {
          'count': unsupported,
          'files': ((result['unsupportedSamples'] as List?) ?? const []).join(
            ', ',
          ),
        }),
      );
    }
    final excluded = (result['excluded'] as num?)?.toInt() ?? 0;
    if (excluded > 0) lines.add(_f('resultExcluded', {'count': excluded}));
    if (result['enabled'] != true) lines.add(_t('resultOff'));
    return lines.join('\n');
  }

  Future<void> _remove() async {
    if (_sessionActive) {
      setState(() => _message = _t('errSessionActive'));
      return;
    }
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: _f('removeTitle', {'serial': _serial}),
      body: _f('removeMessage', {'serial': _serial}),
      confirmLabel: _t('removeConfirm'),
      cancelLabel: _t('cancel'),
      icon: Symbols.delete_rounded,
    );
    if (!confirmed || !mounted) return;
    final result = await widget.client.remove(widget.gamePath);
    if (!mounted) return;
    setState(() {
      _message = result['success'] == true ? _t('removed') : _errorText(result);
    });
    await _reload();
  }

  Future<void> _showHelp() => showDialog<void>(
    context: context,
    builder: (_) => _Armsx2TextureHelpDialog(
      title: _t('help'),
      body: _t('helpBody'),
      closeLabel: _t('close'),
    ),
  );

  String _serialSource() => switch (_game['source']) {
    'session' => _t('serialSession'),
    'disc' => _t('serialDisc'),
    'name' => _t('serialName'),
    _ => _t('serialNone'),
  };

  String _formatList() {
    final formats = _map(_pack['formats']);
    const names = {
      'png': 'PNG',
      'ddsRgba': 'DDS RGBA',
      'ddsBc1': 'DDS BC1',
      'ddsBc2': 'DDS BC2',
      'ddsBc3': 'DDS BC3',
      'ddsBc7': 'DDS BC7',
      'astc': 'ASTC',
      'ktx': 'KTX',
    };
    return [
      for (final entry in names.entries)
        if (((formats[entry.key] as num?) ?? 0) > 0)
          '${entry.value} ${formats[entry.key]}',
    ].join(' · ');
  }

  List<String> _packLines() {
    if (!_installed) return [_t('packNone')];
    final lines = <String>[
      _f('packCounts', {
        'named': _pack['named'] ?? 0,
        'size': _bytes(_pack['bytes']),
      }),
    ];
    final mips = (_pack['mips'] as num?)?.toInt() ?? 0;
    if (mips > 0) lines.add(_f('packMips', {'mips': mips}));
    final formats = _formatList();
    if (formats.isNotEmpty) lines.add(_f('packFormats', {'formats': formats}));
    final unsupported = (_pack['unsupported'] as num?)?.toInt() ?? 0;
    if (unsupported > 0) {
      lines.add(_f('packUnsupported', {'count': unsupported}));
    }
    final packSerial = (_pack['packSerial'] as String?) ?? '';
    if (packSerial.isNotEmpty && packSerial != _serial) {
      lines.add(_f('packFor', {'serial': packSerial}));
    }
    if (_pack['external'] == true) {
      lines.add(_t('packExternal'));
    } else if (((_pack['source'] as String?) ?? '').isNotEmpty) {
      lines.add(_f('packSource', {'source': _pack['source']}));
    }
    if (((_pack['folder'] as String?) ?? '').isNotEmpty) {
      lines.add(_f('packFolder', {'folder': _pack['folder']}));
    }
    return lines;
  }

  String _formatsLine() {
    final formats = _map(_status?['formats']);
    return _f('formatsDevice', {
      'bc': _t(formats['bcTextures'] == true ? 'bcNative' : 'bcCpu'),
      'astc': _t(formats['astcTextures'] == true ? 'astcYes' : 'astcNo'),
    });
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final muted = theme.colorScheme.onSurface.withValues(alpha: 0.7);
    final small = TextStyle(fontSize: 10.r, color: muted);
    if (_status == null) {
      return Padding(
        padding: EdgeInsets.all(8.r),
        child: const LinearProgressIndicator(),
      );
    }
    final list = rows;
    bool selected(String row) => widget.selectedRow == list.indexOf(row);
    final gameLine = <String>[
      if (((_game['region'] as String?) ?? '').isNotEmpty)
        _game['region'] as String,
      if (((_game['version'] as String?) ?? '').isNotEmpty)
        _f('gameVersion', {'version': _game['version']}),
    ].join(' · ');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.only(left: 4.r, top: 8.r, bottom: 4.r),
          child: Text(
            _t('title'),
            style: TextStyle(
              fontSize: 11.r,
              fontWeight: FontWeight.w600,
              color: muted,
            ),
          ),
        ),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: 8.r, vertical: 2.r),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                _serial.isEmpty ? _t('unknownSerial') : _serial,
                style: TextStyle(fontSize: 12.r, fontWeight: FontWeight.w600),
              ),
              if (gameLine.isNotEmpty) Text(gameLine, style: small),
              Text(_serialSource(), style: small),
              SizedBox(height: 4.r),
              Text(
                _t(_installed ? 'packInstalled' : 'packNone'),
                style: TextStyle(fontSize: 12.r, fontWeight: FontWeight.w600),
              ),
              if (_installed)
                for (final line in _packLines()) Text(line, style: small),
            ],
          ),
        ),
        SizedBox(height: 4.r),
        if (_busy) ...[
          if (!_confirming)
            Padding(
              padding: EdgeInsets.symmetric(horizontal: 8.r),
              child: LinearProgressIndicator(
                value: _phase.isEmpty || _fraction < 0
                    ? null
                    : _fraction.clamp(0, 1),
              ),
            ),
          Padding(
            padding: EdgeInsets.all(8.r),
            child: Text(_progressText(), style: small),
          ),
          SettingsRow(
            key: Armsx2TexturePanel.rowKey('cancel'),
            isSelected: selected('cancel'),
            icon: Symbols.close_rounded,
            label: _t('cancel'),
            subtitle: '',
            onTap: () => activateRow(list.indexOf('cancel')),
          ),
        ] else ...[
          SettingsRow(
            key: Armsx2TexturePanel.rowKey('switch'),
            isSelected: selected('switch'),
            icon: Symbols.texture_rounded,
            label: _t('enable'),
            subtitle: _t(_pending ? 'enablePending' : 'enableNext'),
            trailing: Switch(
              key: Armsx2TexturePanel.switchKey,
              value: _switchOn,
              onChanged: _serial.isEmpty
                  ? null
                  : (_) => activateRow(list.indexOf('switch')),
            ),
            onTap: () => activateRow(list.indexOf('switch')),
          ),
          SettingsRow(
            key: Armsx2TexturePanel.rowKey('importFolder'),
            isSelected: selected('importFolder'),
            icon: Symbols.folder_open_rounded,
            label: _t('importFolder'),
            subtitle: _installed ? _t('importReplaces') : '',
            onTap: () => activateRow(list.indexOf('importFolder')),
          ),
          SettingsRow(
            key: Armsx2TexturePanel.rowKey('importArchive'),
            isSelected: selected('importArchive'),
            icon: Symbols.folder_zip_rounded,
            label: _t('importArchive'),
            subtitle: _installed ? _t('importReplaces') : '',
            onTap: () => activateRow(list.indexOf('importArchive')),
          ),
          if (_installed)
            SettingsRow(
              key: Armsx2TexturePanel.rowKey('remove'),
              isSelected: selected('remove'),
              icon: Symbols.delete_rounded,
              label: _t('remove'),
              subtitle: '',
              onTap: () => activateRow(list.indexOf('remove')),
            ),
          SettingsRow(
            key: Armsx2TexturePanel.rowKey('help'),
            isSelected: selected('help'),
            icon: Symbols.help_rounded,
            label: _t('help'),
            subtitle: '',
            onTap: () => activateRow(list.indexOf('help')),
          ),
        ],
        if (_message != null)
          Padding(
            padding: EdgeInsets.symmetric(horizontal: 8.r, vertical: 4.r),
            child: Text(
              _message!,
              style: TextStyle(
                fontSize: 10.r,
                color: theme.colorScheme.secondary,
              ),
            ),
          ),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: 8.r, vertical: 4.r),
          child: Text('${_formatsLine()}\n${_t('engineInGame')}', style: small),
        ),
      ],
    );
  }

  String _progressText() {
    final percent = (_fraction.clamp(0, 1) * 100).round();
    return switch (_phase) {
      'installing' => _f('installing', {'percent': percent}),
      'expanding' =>
        _fraction < 0
            ? _t('expandingUnknown')
            : _f('expanding', {'percent': percent}),
      _ => _t('checking'),
    };
  }
}

class _Armsx2TextureHelpDialog extends StatefulWidget {
  const _Armsx2TextureHelpDialog({
    required this.title,
    required this.body,
    required this.closeLabel,
  });

  final String title;
  final String body;
  final String closeLabel;

  @override
  State<_Armsx2TextureHelpDialog> createState() =>
      _Armsx2TextureHelpDialogState();
}

class _Armsx2TextureHelpDialogState extends State<_Armsx2TextureHelpDialog> {
  late final GamepadNavigation _gamepadNav;
  final ScrollController _scroll = ScrollController();

  void _scrollBy(double delta) {
    if (!_scroll.hasClients) return;
    _scroll.animateTo(
      (_scroll.offset + delta).clamp(0, _scroll.position.maxScrollExtent),
      duration: const Duration(milliseconds: 120),
      curve: Curves.easeOut,
    );
  }

  @override
  void initState() {
    super.initState();
    _gamepadNav = GamepadNavigation(
      onNavigateUp: () => _scrollBy(-80),
      onNavigateDown: () => _scrollBy(80),
      onSelectItem: () {
        if (mounted) Navigator.of(context).pop();
      },
      onBack: () {
        if (mounted) Navigator.of(context).pop();
      },
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _gamepadNav.initialize();
      GamepadNavigationManager.pushLayer(
        'armsx2_texture_help',
        onActivate: () => _gamepadNav.activate(),
        onDeactivate: () => _gamepadNav.deactivate(),
      );
    });
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer('armsx2_texture_help');
    _gamepadNav.dispose();
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AlertDialog(
      backgroundColor: theme.cardColor,
      title: Text(
        widget.title,
        style: TextStyle(fontSize: 14.r, fontWeight: FontWeight.w600),
      ),
      content: ConstrainedBox(
        constraints: BoxConstraints(maxHeight: 280.r, maxWidth: 520.r),
        child: SingleChildScrollView(
          controller: _scroll,
          child: Text(widget.body, style: TextStyle(fontSize: 11.r)),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(widget.closeLabel),
        ),
      ],
    );
  }
}
