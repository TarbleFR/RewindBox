import 'dart:async';

import 'package:flutter/material.dart';

import '../l10n/switch_online_locale.dart';
import '../services/logger_service.dart';
import '../services/nextendo/nextendo_catalog.dart';
import '../services/nextendo/nextendo_config.dart';
import '../services/nextendo/nextendo_engine_support.dart';
import '../services/nextendo/nextendo_online_play.dart';
import '../services/nextendo/nextendo_servers.dart';
import '../services/nextendo/nextendo_service.dart';
import 'online_service_widgets.dart';

/// The player's Nextendo Network screen: one button for the account (sign in
/// on nextendo.network, or sign out) and one switch for online services.
/// Everything else is automatic: the server addresses are looked up by name,
/// the engine, the account and the last game connection are checked in the
/// background and summed up in one line, and each launch of a compatible game
/// gets its token, versions, BCAT data and account id by itself.
class NextendoDialog extends StatefulWidget {
  const NextendoDialog({super.key, this.service, this.engineSupported});
  final NextendoService? service;

  /// Whether the shipped engine takes online play; [NextendoEngineSupport] by default.
  final Future<bool> Function()? engineSupported;
  @override
  State<NextendoDialog> createState() => _NextendoDialogState();
}

class _NextendoDialogState extends State<NextendoDialog> {
  NextendoConfig? _config;
  NextendoCatalog? _catalog;
  bool _catalogLoaded = false;
  NextendoAccount? _account;
  bool _online = false;
  bool _busy = false;
  bool _checking = false;
  String? _status; // the one line under the switch; null while nothing was checked
  bool _statusIsError = false;
  String? _message; // an action that failed (sign-in, switch)
  int _checkGeneration = 0;

  NextendoService get _service => widget.service ?? NextendoService.instance;
  String _text(String key, [Map<String, Object?> parameters = const {}]) => SwitchOnlineLocale.text(context, key, parameters);

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    try {
      await NextendoOnlinePlay.restoreGameTls();
      unawaited(NextendoCatalogStore.current().then((catalog) {
        if (mounted) {
          setState(() {
            _catalog = catalog;
            _catalogLoaded = true;
          });
        }
      }));
      final config = await NextendoConfig.load();
      final account = config.canSignIn ? await _service.restore(config) : null;
      final online = await NextendoOnlinePlay.enabled();
      if (!mounted) return;
      setState(() {
        _config = config;
        _account = account;
        _online = online;
      });
      if (account != null && online) unawaited(_check());
    } catch (error) {
      if (mounted) _fail(error);
    }
  }

  String _errorText(Object error) {
    if (error is NextendoException) return _text(error.code, {'detail': error.detail});
    LoggerService.instance.w('Nextendo action failed: ${error.runtimeType}');
    return _text('nextendoFailed');
  }

  void _fail(Object error) => setState(() => _message = _errorText(error));

  Future<void> _run(Future<void> Function() action) async {
    if (_busy) return;
    setState(() {
      _busy = true;
      _message = null;
    });
    try {
      await action();
    } catch (error) {
      if (mounted) _fail(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<NextendoAccount?> _signInNow() async {
    final account = await _service.signIn(_config!);
    if (mounted) setState(() => _account = account);
    return account;
  }

  Future<void> _signIn() => _run(() async {
    await _signInNow();
    if (_online) unawaited(_check());
  });

  Future<void> _signOut() => _run(() async {
    await _service.signOut(_config!);
    if (mounted) {
      setState(() {
        _account = null;
        _status = null;
      });
    }
  });

  /// The single switch. Turning it on signs the player in first when needed
  /// and asks once for the consent the game servers need.
  Future<void> _setOnline(bool value) async {
    if (_busy) return;
    if (value) {
      if (_account == null) await _run(_signInNow);
      if (_account == null || !mounted) return;
      final accepted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          scrollable: true,
          title: Text(_text('nextendoConsentTitle')),
          content: Text(_text('nextendoConsentBody')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: Text(_text('cancel'))),
            FilledButton(
              key: const ValueKey('nextendo-consent-accept'),
              onPressed: () => Navigator.pop(context, true),
              child: Text(_text('nextendoConsentAccept')),
            ),
          ],
        ),
      );
      if (accepted != true || !mounted) return;
    }
    await _run(() async {
      await NextendoOnlinePlay.setEnabled(value);
      if (!mounted) return;
      setState(() {
        _online = value;
        _status = null;
      });
    });
    if (value && _online && mounted) unawaited(_check());
  }

  /// Everything the player no longer sets by hand, checked in the background:
  /// the server names, the engine, the account on Nextendo's side and the last
  /// game connection. One line says what is ready or the first thing that is not.
  Future<void> _check() async {
    final generation = ++_checkGeneration;
    setState(() {
      _checking = true;
      _status = null;
    });
    String status;
    var error = true;
    try {
      await NextendoServers.refresh();
      final config = await NextendoConfig.load();
      final engine = await (widget.engineSupported ?? NextendoEngineSupport.supported)();
      if (!config.serversConfigured) {
        status = _text('nextendoServicesServers');
      } else if (!engine) {
        status = _text('nextendoServicesEngine');
      } else {
        final answer = await _service.onlineStatus(await _service.gameToken(config));
        const known = {'unknown', 'disabled', 'suspended', 'unverified', 'discord_unlinked', 'elsewhere'};
        if (!answer.allowed) {
          status = _text(known.contains(answer.reason) ? 'nextendoReason_${answer.reason}' : 'nextendoReason_other', {'detail': answer.reason});
        } else if (NextendoOnlinePlay.lastGameTls == 'refused') {
          status = _text('nextendoServicesGameRefused');
        } else {
          status = _text('nextendoServicesReady');
          error = false;
        }
      }
      if (mounted) _config = config;
    } catch (failure) {
      status = mounted ? _errorText(failure) : '';
    }
    if (!mounted || generation != _checkGeneration) return;
    setState(() {
      _checking = false;
      _status = status;
      _statusIsError = error;
    });
  }

  Widget _accountSection() {
    final account = _account;
    if (account == null) {
      return OnlineServiceIdentitySection(
        actionKey: const ValueKey('nextendo-sign-in'),
        actionLabel: _text('nextendoSignIn'),
        onAction: _busy ? null : _signIn,
      );
    }
    return OnlineServiceIdentitySection(
      identityTitle: _text('nextendoSignedInAs', {'name': account.shownName}),
      identitySubtitle: [
        if (account.shownName != account.username) account.username,
        if (account.friendCode.isNotEmpty) '${_text('nextendoFriendCode')}: ${account.friendCode}',
      ].join('\n'),
      actionKey: const ValueKey('nextendo-sign-out'),
      actionLabel: _text('nextendoSignOut'),
      onAction: _busy ? null : _signOut,
    );
  }

  Widget _servicesSection() {
    final String line;
    if (!_online) {
      line = _text(_account == null ? 'nextendoServicesSignIn' : 'nextendoServicesOff');
    } else if (_account == null) {
      line = _text('nextendoServicesSignIn');
    } else if (_checking || _status == null) {
      line = _text('nextendoServicesChecking');
    } else {
      line = _status!;
    }
    final problem = _online && _account != null && !_checking && _status != null && _statusIsError;
    return OnlineServicesSwitch(
      key: const ValueKey('nextendo-online-services'),
      title: _text('nextendoOnlineServices'),
      status: line,
      problem: problem,
      checking: _checking || _status == null,
      value: _online && _account != null,
      onChanged: _busy || _config == null || !_config!.canSignIn ? null : _setOnline,
    );
  }

  /// Nextendo's signed catalog: each game and the exact version its servers
  /// accept. Information only; NPLN titles also need Nextendo's signed online
  /// patches, which RewindBox does not apply yet.
  Widget _games() {
    final catalog = _catalog;
    return ExpansionTile(
      key: const ValueKey('nextendo-catalog'),
      tilePadding: EdgeInsets.zero,
      title: Text(_text('nextendoCatalogTitle')),
      children: [
        if (catalog == null)
          Text(_catalogLoaded ? _text('nextendoCatalogUnavailable') : '…')
        else
          for (final game in catalog.games.where((game) => game.enabled))
            ListTile(
              dense: true,
              contentPadding: EdgeInsets.zero,
              title: Text(game.name),
              subtitle: Text([
                game.accepted.join(' / '),
                if (game.needsNplnPatches) _text('nextendoCatalogNpln'),
              ].join('\n')),
            ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final config = _config;
    return AlertDialog(
      title: const Text('Nextendo Network'),
      content: SizedBox(
        width: 480,
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(_text('nextendoIntro')),
              const SizedBox(height: 12),
              if (config == null && _message == null) const Center(child: CircularProgressIndicator()),
              if (config != null && !config.canSignIn) Text(_text('nextendoNotConfigured')),
              if (config != null && config.canSignIn) ...[
                _accountSection(),
                _servicesSection(),
              ],
              if (_busy) const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator()),
              if (_message != null)
                Padding(
                  padding: const EdgeInsets.only(top: 8),
                  child: Text(_message!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
                ),
              const SizedBox(height: 8),
              _games(),
            ],
          ),
        ),
      ),
      actions: [
        TextButton(onPressed: () => Navigator.pop(context), child: Text(_text('close'))),
      ],
    );
  }
}
