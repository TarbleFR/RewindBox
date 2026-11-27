import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/wiimmfi_locale.dart';
import '../services/dolphin_internal_v2_service.dart';
import '../services/dolphin_system_files.dart';
import '../services/wiimmfi/wiimmfi_service.dart';
import '../services/wiimmfi/wiimmfi_catalog.dart';
import 'glass/glass_surface.dart';

class WiimmfiPanel extends StatefulWidget {
  const WiimmfiPanel({super.key, this.gamePath, this.onLaunch});
  final String? gamePath;
  final Future<String?> Function(bool online)? onLaunch;
  @override
  State<WiimmfiPanel> createState() => _WiimmfiPanelState();
}

class _WiimmfiPanelState extends State<WiimmfiPanel> {
  bool _busy = false;
  bool _importing = false;
  Map<String, dynamic>? _settings;
  Map<String, dynamic>? _status;
  Map<String, dynamic>? _progress;
  Map<String, dynamic>? _identity;
  String? _message;
  Timer? _timer;
  final _code = TextEditingController();
  String t(String key) => WiimmfiLocale.text(context, key);

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void dispose() {
    _timer?.cancel();
    _code.dispose();
    super.dispose();
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
          /* Remains unknown. */
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
    if (_busy) return;
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
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<bool> _confirm(String key) async =>
      await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: const Text('Wiimmfi'),
          content: Text(t(key)),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text(t('cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, true),
              child: Text(t('continue')),
            ),
          ],
        ),
      ) ??
      false;

  Future<void> _import() async {
    if (!await _confirm('importHelp') || !mounted) return;
    await _run(() async {
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
          /* The import itself reports errors. */
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
      }
    });
  }

  Future<void> _open(String url) async {
    if (!await launchUrl(Uri.parse(url), mode: LaunchMode.inAppBrowserView) &&
        mounted) {
      setState(() => _message = t('error'));
    }
  }

  Future<void> _launch(bool online) => _run(() async {
    final message = await widget.onLaunch!(online);
    if (mounted && message != null) setState(() => _message = message);
  });

  Future<void> _diagnose() => _run(() async {
    final result = await WiimmfiService.diagnose();
    if (!mounted) return;
    await showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(t('diagnose')),
        content: SingleChildScrollView(
          child: Text(
            [
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
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text(t('close')),
          ),
        ],
      ),
    );
  });

  Widget _button(String key, IconData icon, VoidCallback? action) => ListTile(
    leading: Icon(icon),
    title: Text(t(key)),
    onTap: _busy ? null : action,
    enabled: !_busy && action != null,
  );

  @override
  Widget build(BuildContext context) {
    final enabled = _settings?['enabled'] == true;
    final supported = _status?['supported'] == true;
    final images = _settings?['images'];
    final declared = images is Map && images[widget.gamePath] is Map;
    final panel = PopScope(
      canPop: !_busy,
      child: GlassSurface(
        margin: const EdgeInsets.symmetric(vertical: 8),
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Wiimmfi', style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(t('intro')),
            if (_status != null && !supported)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(t('engineUnavailable')),
              ),
            SwitchListTile.adaptive(
              contentPadding: EdgeInsets.zero,
              title: Text(t('enabled')),
              value: enabled,
              onChanged: !_busy && (supported || enabled)
                  ? (value) => _run(() => WiimmfiService.setEnabled(value))
                  : null,
            ),
            ListTile(
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.memory),
              title: Text(t('nand')),
              subtitle: Text(
                t(
                  _status?['nandRecognized'] == true
                      ? 'recognized'
                      : 'nandMissing',
                ),
              ),
            ),
            _button('importNand', Icons.file_open, supported ? _import : null),
            if (_importing) ...[
              LinearProgressIndicator(
                value: _progress?['percent'] == null
                    ? null
                    : ((_progress!['percent'] as num?)?.toDouble() ?? 0) / 100,
              ),
              Text(
                '${t(_progress?['phase']?.toString() ?? 'importNand')}${_progress?['percent'] == null ? '' : ' · ${_progress!['percent']}%'}',
              ),
              ValueListenableBuilder<String>(
                valueListenable: WiimmfiService.importPhase,
                builder: (context, phase, _) => TextButton(
                  onPressed: phase == 'committing' || phase == 'idle'
                      ? null
                      : WiimmfiService.cancelImport,
                  child: Text(t('cancel')),
                ),
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
                Icons.verified_user_outlined,
                supported
                    ? () async {
                        if (await _confirm('patchHelp') && mounted) {
                          await _run(
                            () => WiimmfiService.registerPatchedImage(
                              widget.gamePath!,
                            ),
                          );
                        }
                      }
                    : null,
              ),
              _button(
                'launch',
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
                Icons.videogame_asset,
                supported && widget.onLaunch != null
                    ? () => _launch(false)
                    : null,
              ),
            ],
            _button(
              'diagnose',
              Icons.network_check,
              enabled ? _diagnose : null,
            ),
            ExpansionTile(
              title: Text(t('games')),
              children: [
                Text(t('catalogHelp')),
                for (final game in WiimmfiCatalog.candidates)
                  ListTile(
                    title: Text(game.name),
                    subtitle: Text(t('notTested')),
                  ),
              ],
            ),
            _button(
              'officialStats',
              Icons.query_stats,
              () => _open('https://wiimmfi.de/stat'),
            ),
            _button(
              'documentation',
              Icons.help_outline,
              () => _open('https://wiimmfi.de/patcher'),
            ),
            TextField(
              controller: _code,
              decoration: InputDecoration(labelText: t('code')),
              keyboardType: TextInputType.number,
              maxLength: 5,
            ),
            TextButton(
              onPressed: _busy
                  ? null
                  : () async {
                      final code = _code.text.trim();
                      if (!RegExp(r'^\d{5}$').hasMatch(code)) return;
                      setState(
                        () => _message =
                            '$code: ${t(WiimmfiLocale.errorKey(code))}',
                      );
                      await _open('https://wiimmfi.de/error?e=$code');
                    },
              child: Text(t('lookup')),
            ),
            _button('clear', Icons.settings_backup_restore, () async {
              if (await _confirm('clearHelp') && mounted) {
                await _run(WiimmfiService.clear);
              }
            }),
            if (_busy && !_importing) const LinearProgressIndicator(),
            if (_message != null)
              Padding(padding: const EdgeInsets.all(8), child: Text(_message!)),
          ],
        ),
      ),
    );
    if (widget.gamePath == null) return panel;
    return ExpansionTile(
      leading: const Icon(Icons.public),
      title: const Text('Wiimmfi'),
      subtitle: Text(t(declared ? 'declared' : 'notTested')),
      children: [panel],
    );
  }
}
