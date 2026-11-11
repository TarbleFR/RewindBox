import 'package:flutter/material.dart';

import '../../l10n/xenia_locale.dart';
import '../../services/xenia_internal_service.dart';
import '../../services/xenia_settings_service.dart';
import '../libretro/libretro_skin_manager_screen.dart'
    show LibretroFocusRing, LibretroPageNavigation, libretroPageAppBar;

/// XeniOS settings (docs/xenios-playlist.md § Settings): every Xbox 360
/// game ([gameKey] null) or one game, whose rows show the inherited value
/// and can go back to it. Controller, D-pad and touch use the same page
/// navigation as the other embedded-console pages.
class XeniaSettingsScreen extends StatefulWidget {
  const XeniaSettingsScreen({
    super.key,
    this.gameKey,
    this.gameTitle,
    this.service,
  });

  final String? gameKey;
  final String? gameTitle;

  /// Production: [XeniaInternalService.settings].
  final XeniaSettingsService? service;

  static Future<void> open(
    BuildContext context, {
    String? gameKey,
    String? gameTitle,
  }) => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) =>
          XeniaSettingsScreen(gameKey: gameKey, gameTitle: gameTitle),
    ),
  );

  @override
  State<XeniaSettingsScreen> createState() => _XeniaSettingsScreenState();
}

class _XeniaSettingsScreenState extends State<XeniaSettingsScreen>
    with LibretroPageNavigation<XeniaSettingsScreen> {
  late final XeniaSettingsService _service =
      widget.service ?? XeniaInternalService.settings;
  bool _loaded = false;

  bool get _isGame => widget.gameKey != null;

  String _t(String key) => XeniaLocale.text(context, key);

  @override
  void initState() {
    super.initState();
    _service.load().whenComplete(() {
      if (mounted) setState(() => _loaded = true);
    });
  }

  String _valueLabel(XeniaOption option, String value) {
    if (value == XeniaSettingsService.automatic) return _t('automatic');
    if (option.kind == XeniaOptionKind.toggle) {
      return _t(value == 'true' ? 'on' : 'off');
    }
    return switch (option.key) {
      'user_language' => XeniaSettingsService.languageNames[value] ?? value,
      'user_country' => XeniaSettingsService.countryCodes[value] ?? value,
      'framerate_limit' => value == '0' ? _t('unlimited') : '$value FPS',
      'xma_decoder' => _t(switch (value) {
        'old' => 'decoderOld',
        'master' => 'decoderMaster',
        _ => 'decoderNew',
      }),
      _ => value,
    };
  }

  String _sourceLabel(XeniaValueSource source) => _t(switch (source) {
    XeniaValueSource.engine => 'sourceEngine',
    XeniaValueSource.global => 'sourceGlobal',
    XeniaValueSource.game => 'sourceGame',
  });

  Future<void> _write(String key, String? value) async {
    try {
      if (_isGame) {
        await _service.setGame(widget.gameKey!, key, value);
      } else {
        await _service.setGlobal(key, value);
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            XeniaLocale.textf(context, 'saveFailed', {'error': error}),
          ),
        ),
      );
    }
    if (mounted) setState(() {});
  }

  Future<void> _edit(XeniaOption option) async {
    final current = _service.resolve(option.key, gameKey: widget.gameKey);
    final ownValue = _isGame
        ? _service.gameValue(widget.gameKey!, option.key)
        : _service.globalValue(option.key);
    if (option.kind == XeniaOptionKind.toggle && !_isGame) {
      await _write(option.key, current.value == 'true' ? 'false' : 'true');
      return;
    }
    final inherit = '\u0000inherit';
    final picked = await showDialog<String>(
      context: context,
      builder: (context) => SimpleDialog(
        title: Text(_t(option.key)),
        children: [
          if (ownValue != null)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(context, inherit),
              child: Text(_t('resetGame')),
            ),
          for (final value in option.allowedValues)
            SimpleDialogOption(
              onPressed: () => Navigator.pop(context, value),
              child: Row(
                children: [
                  Icon(
                    value == current.value
                        ? Icons.radio_button_checked
                        : Icons.radio_button_unchecked,
                    size: 18,
                  ),
                  const SizedBox(width: 12),
                  Flexible(child: Text(_valueLabel(option, value))),
                ],
              ),
            ),
        ],
      ),
    );
    if (picked == null) return;
    await _write(option.key, picked == inherit ? null : picked);
  }

  Widget _row(XeniaOption option) {
    final resolved = _service.resolve(option.key, gameKey: widget.gameKey);
    final own =
        resolved.source ==
        (_isGame ? XeniaValueSource.game : XeniaValueSource.global);
    final help = switch (option.key) {
      'user_language' => _t('languageHelp'),
      'user_country' => _t('countryHelp'),
      _ => null,
    };
    final subtitle = <String>[
      own
          ? _valueLabel(option, resolved.value)
          : '${_valueLabel(option, resolved.value)} · '
                '${XeniaLocale.textf(context, 'inheritedFrom', {'source': _sourceLabel(resolved.source)})}',
      ?help,
    ].join('\n');
    return LibretroFocusRing(
      radius: 12,
      child: ListTile(
        key: ValueKey('xenia-setting-${option.key}'),
        title: Text(_t(option.key)),
        subtitle: Text(subtitle),
        isThreeLine: help != null,
        trailing: own && _isGame
            ? IconButton(
                key: ValueKey('xenia-setting-reset-${option.key}'),
                tooltip: _t('resetGame'),
                icon: const Icon(Icons.undo),
                onPressed: () => _write(option.key, null),
              )
            : const Icon(Icons.chevron_right),
        onTap: () => _edit(option),
      ),
    );
  }

  Future<void> _resetAll() async {
    try {
      if (_isGame) {
        await _service.resetGame(widget.gameKey!);
      } else {
        await _service.resetGlobal();
      }
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            XeniaLocale.textf(context, 'saveFailed', {'error': error}),
          ),
        ),
      );
    }
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final title = _isGame
        ? (widget.gameTitle ?? _t('gameScope'))
        : _t('settingsTitle');
    final children = <Widget>[
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
        child: Text(
          _isGame ? _t('gameSettings') : _t('globalScope'),
          style: theme.textTheme.titleMedium,
        ),
      ),
      Padding(
        padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
        child: Text(
          '${_t('appliesNextLaunch')} ${_t('interfaceNote')}',
          style: theme.textTheme.bodySmall?.copyWith(
            color: theme.colorScheme.onSurfaceVariant,
          ),
        ),
      ),
    ];
    for (final section in XeniaOptionSection.values) {
      final rows = XeniaSettingsService.options.where(
        (o) => o.section == section,
      );
      if (rows.isEmpty) continue;
      children.add(
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
          child: Text(
            _t(switch (section) {
              XeniaOptionSection.console => 'sectionConsole',
              XeniaOptionSection.graphics => 'sectionGraphics',
              XeniaOptionSection.audio => 'sectionAudio',
              XeniaOptionSection.system => 'sectionSystem',
            }),
            style: theme.textTheme.labelLarge?.copyWith(
              color: theme.colorScheme.primary,
            ),
          ),
        ),
      );
      children.addAll(rows.map(_row));
    }
    children.add(
      Padding(
        padding: const EdgeInsets.all(16),
        child: LibretroFocusRing(
          child: OutlinedButton.icon(
            key: const ValueKey('xenia-settings-reset-all'),
            onPressed: _resetAll,
            icon: const Icon(Icons.settings_backup_restore),
            label: Text(_t(_isGame ? 'resetGame' : 'resetGlobal')),
          ),
        ),
      ),
    );
    return libretroPage(
      Scaffold(
        appBar: libretroPageAppBar(context, title),
        body: SafeArea(
          child: !_loaded
              ? const Center(child: CircularProgressIndicator())
              : ListView(children: children),
        ),
      ),
    );
  }
}
