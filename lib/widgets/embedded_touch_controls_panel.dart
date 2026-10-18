import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neo_touch_layout/neo_touch_layout.dart';

import '../l10n/touch_layout_locale.dart';

typedef TouchLayoutSettingsLoader =
    Future<NeoTouchLayoutSettings?> Function(String console);
typedef TouchLayoutHideSaver =
    Future<NeoTouchLayoutSettings?> Function(String console, bool hide);
typedef TouchLayoutEditorOpener =
    Future<({bool opened, bool saved})> Function(String layout, String locale);

/// Touch controls of an embedded engine (Settings › Systems › GameCube, Wii,
/// PS2 or PS3 › Emulators, Build 484): "Hide touch controls when a controller
/// is connected" (on by default) and the on-screen editor of the console's
/// layouts. The values are the native preferences the in-game menu also
/// edits; a running session applies a change at once.
class EmbeddedTouchControlsPanel extends StatefulWidget {
  const EmbeddedTouchControlsPanel({
    super.key,
    required this.console,
    this.load,
    this.setHide,
    this.openEditor,
  });

  /// "gc", "wii", "ps2" or "ps3".
  final String console;

  /// Test seams; production uses the neostation/touch_layout channel.
  final TouchLayoutSettingsLoader? load;
  final TouchLayoutHideSaver? setHide;
  final TouchLayoutEditorOpener? openEditor;

  static const Key switchKey = ValueKey('embedded-touch-hide-with-controller');
  static Key editKey(String layout) => ValueKey('embedded-touch-edit-$layout');

  /// Consoles whose embedded engine has editable touch controls.
  static bool supports(String console) =>
      NeoTouchLayout.consoles.contains(console);

  @override
  State<EmbeddedTouchControlsPanel> createState() =>
      _EmbeddedTouchControlsPanelState();
}

class _EmbeddedTouchControlsPanelState
    extends State<EmbeddedTouchControlsPanel> {
  NeoTouchLayoutSettings? _settings;
  bool _loaded = false;
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final loader = widget.load ?? NeoTouchLayout.settings;
    NeoTouchLayoutSettings? settings;
    try {
      settings = await loader(widget.console);
    } catch (_) {
      settings = null;
    }
    if (!mounted) return;
    setState(() {
      _settings = settings;
      _loaded = true;
    });
  }

  Future<void> _setHide(bool hide) async {
    final current = _settings;
    if (current == null || _busy) return;
    final saver = widget.setHide ?? NeoTouchLayout.setHideWithController;
    setState(() => _busy = true);
    NeoTouchLayoutSettings? stored;
    try {
      stored = await saver(widget.console, hide);
    } catch (_) {
      stored = null;
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _settings = stored ?? current;
    });
  }

  Future<void> _edit(String layout) async {
    if (_busy) return;
    final opener = widget.openEditor ?? NeoTouchLayout.openEditor;
    final locale = TouchLayoutLocale.nativeLocale(_locale);
    setState(() => _busy = true);
    var opened = false;
    try {
      opened = (await opener(layout, locale)).opened;
    } catch (_) {
      opened = false;
    }
    if (!mounted) return;
    setState(() => _busy = false);
    if (!opened) {
      ScaffoldMessenger.maybeOf(
        context,
      )?.showSnackBar(SnackBar(content: Text(_t('editorUnavailable'))));
    }
    await _load();
  }

  Locale get _locale =>
      Localizations.maybeLocaleOf(context) ?? const Locale('en');

  String _t(String key) => TouchLayoutLocale.text(key, _locale);

  String _layoutName(String layout) => switch (layout) {
    'gc' => _t('layoutGameCube'),
    'wii' => _t('layoutWii'),
    'wii-classic' => _t('layoutWiiClassic'),
    'ps2' => _t('layoutPS2'),
    'ps3' => _t('layoutPS3'),
    _ => layout,
  };

  @override
  Widget build(BuildContext context) {
    final settings = _settings;
    if (!_loaded || settings == null) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final dolphin = widget.console == 'gc' || widget.console == 'wii';
    final help = dolphin
        ? '${_t('hideWithControllerHelp')}\n\n${_t('dolphinPlayerOneNote')}'
        : _t('hideWithControllerHelp');
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: EdgeInsets.fromLTRB(16.r, 8.r, 16.r, 4.r),
          child: Text(
            _t('touchControls'),
            style: theme.textTheme.titleSmall?.copyWith(
              color: theme.colorScheme.primary,
            ),
          ),
        ),
        SwitchListTile.adaptive(
          key: EmbeddedTouchControlsPanel.switchKey,
          value: settings.hideWithController,
          title: Text(_t('hideWithController')),
          subtitle: Text(help),
          onChanged: _busy ? null : _setHide,
        ),
        for (final layout in settings.layouts)
          ListTile(
            key: EmbeddedTouchControlsPanel.editKey(layout.key),
            leading: const Icon(Icons.touch_app_outlined),
            title: Text(
              settings.layouts.length > 1
                  ? '${_t('editTouchControls')} · ${_layoutName(layout.key)}'
                  : _t('editTouchControls'),
            ),
            subtitle: Text(
              '${_t('editTouchControlsDetail')} · '
              '${layout.customized ? _t('customized') : _t('stockLayout')}',
            ),
            trailing: const Icon(Icons.chevron_right),
            enabled: layout.editable && !_busy,
            onTap: () => _edit(layout.key),
          ),
      ],
    );
  }
}
