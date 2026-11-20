import 'dart:async';

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/switch_online_locale.dart';
import '../services/logger_service.dart';
import '../services/nextendo/nextendo_catalog.dart';
import '../services/nextendo/nextendo_config.dart';
import '../services/nextendo/nextendo_engine_support.dart';
import '../services/nextendo/nextendo_online_play.dart';
import '../services/nextendo/nextendo_servers.dart';
import '../services/nextendo/nextendo_service.dart';

/// The player's Nextendo Network account in RewindBox: sign-in on
/// nextendo.network, the linked identity, and the three conditions of online
/// play shown apart (account, game servers, engine) with the action each
/// missing one needs. The online switch only turns on when all three hold. The
/// server addresses are looked up by name ([NextendoServers]); the maintainer's
/// fields only show while no lookup has ever succeeded.
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
  bool _online = true;
  bool _smashPrivateTls = false;
  bool? _engine; // null while the engine binary is checked
  bool _busy = false;
  String? _message;
  bool _messageIsError = false;
  final _clientId = TextEditingController();
  final _server = TextEditingController();
  final _nat = TextEditingController();

  NextendoService get _service => widget.service ?? NextendoService.instance;
  String _text(String key, [Map<String, Object?> parameters = const {}]) => SwitchOnlineLocale.text(context, key, parameters);

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _clientId.dispose();
    _server.dispose();
    _nat.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    try {
      await NextendoOnlinePlay.restoreSmashTls();
      await NextendoServers.refresh();
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
      final smashPrivateTls = await NextendoOnlinePlay.smashPrivateTlsEnabled();
      unawaited((widget.engineSupported ?? NextendoEngineSupport.supported)().then((supported) {
        if (mounted) setState(() => _engine = supported);
      }, onError: (Object _) {
        if (mounted) setState(() => _engine = false);
      }));
      if (!mounted) return;
      setState(() {
        _config = config;
        _account = account;
        _online = online;
        _smashPrivateTls = smashPrivateTls;
        _clientId.text = config.clientId;
        _server.text = config.serverAddress;
        _nat.text = config.natAddress;
      });
    } catch (error) {
      if (mounted) _fail(error);
    }
  }

  void _fail(Object error) {
    final String text;
    if (error is NextendoException) {
      text = _text(error.code, {'detail': error.detail});
    } else if (error is FormatException && const {'clientId', 'serverAddress', 'natAddress', 'sameAddresses'}.contains(error.message)) {
      text = _text('nextendoInvalid_${error.message}');
    } else {
      LoggerService.instance.w('Nextendo action failed: ${error.runtimeType}');
      text = _text('nextendoFailed');
    }
    setState(() {
      _message = text;
      _messageIsError = true;
    });
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
      if (mounted) _fail(error);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _signIn() => _run(() async {
    final account = await _service.signIn(_config!);
    if (mounted) setState(() => _account = account);
  });

  Future<void> _signOut() => _run(() async {
    await _service.signOut(_config!);
    if (mounted) setState(() => _account = null);
  });

  /// The first missing condition of online play, as the action it needs; null
  /// when the servers and the engine are ready (the account is signed in here).
  String? _missing(NextendoConfig config) {
    if (!config.serversConfigured) {
      return _text(config.serversIssue == 'same' ? 'nextendoActionServersSame' : 'nextendoActionServers');
    }
    if (_engine == false) return _text('nextendoActionEngine');
    if (_engine == null) return _text('nextendoStatusEngineChecking');
    return null;
  }

  /// Nextendo's answer for the account, then what this build still lacks. An
  /// accepted account is never presented as a working match.
  Future<void> _check() => _run(() async {
    final config = _config!;
    final status = await _service.onlineStatus(await _service.gameToken(config));
    if (!mounted) return;
    final known = const {'unknown', 'disabled', 'suspended', 'unverified', 'discord_unlinked', 'elsewhere'}.contains(status.reason);
    final missing = _missing(config);
    final smashTlsRefused = NextendoOnlinePlay.lastSmashTls == 'refused';
    setState(() {
      _messageIsError = !status.allowed || missing != null || smashTlsRefused;
      _message = !status.allowed
          ? _text(known ? 'nextendoReason_${status.reason}' : 'nextendoReason_other', {'detail': status.reason})
          : missing != null
          ? _text('nextendoAllowedNotReady', {'cause': missing})
          : smashTlsRefused
          ? _text('nextendoSmashTlsRejected')
          : NextendoOnlinePlay.lastSmashTls == 'compatibility'
          ? _text('nextendoSmashTlsCompatibility')
          : _text('nextendoAllowedReady');
    });
  });

  Future<void> _setSmashPrivateTls(bool value) => _run(() async {
    if (value) {
      final accepted = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          scrollable: true,
          title: Text(_text('nextendoSmashPrivateTls')),
          content: Text(_text('nextendoSmashPrivateTlsWarning')),
          actions: [
            TextButton(onPressed: () => Navigator.pop(context, false), child: Text(_text('cancel'))),
            FilledButton(onPressed: () => Navigator.pop(context, true), child: Text(_text('nextendoSmashPrivateTlsAccept'))),
          ],
        ),
      );
      if (accepted != true || !mounted) return;
    }
    await NextendoOnlinePlay.setSmashPrivateTlsEnabled(value);
    if (mounted) {
      setState(() {
        _smashPrivateTls = value;
        _messageIsError = false;
        _message = _text('nextendoOnlinePlayHint');
      });
    }
  });

  Widget _status(bool? ok, String text, [String? action]) {
    final colors = Theme.of(context).colorScheme;
    return ListTile(
      contentPadding: EdgeInsets.zero,
      dense: true,
      leading: Icon(
        ok == null ? Icons.hourglass_empty : (ok ? Icons.check_circle : Icons.cancel),
        color: ok == null ? null : (ok ? colors.primary : colors.error),
      ),
      title: Text(text),
      subtitle: action == null ? null : Text(action),
    );
  }

  Future<void> _saveLocal() => _run(() async {
    final previous = _config!;
    final config = await NextendoConfig.saveLocal(clientId: _clientId.text, serverAddress: _server.text, natAddress: _nat.text);
    // A session belongs to the application that opened it: with another
    // client identifier the previous one is closed on Nextendo's side too.
    if (previous.clientId != config.clientId && _account != null) await _service.signOut(previous);
    final account = config.canSignIn ? await _service.restore(config) : null;
    if (!mounted) return;
    setState(() {
      _config = config;
      _account = account;
      _messageIsError = false;
      _message = _text('nextendoSaved');
    });
  });

  List<Widget> _accountSection(NextendoConfig config) {
    final account = _account;
    if (account == null) {
      return [
        if (!config.canSignIn) Text(_text('nextendoNotConfigured')),
        const SizedBox(height: 8),
        FilledButton.icon(
          key: const ValueKey('nextendo-sign-in'),
          onPressed: _busy || !config.canSignIn ? null : _signIn,
          icon: const Icon(Icons.login),
          label: Text(_text('nextendoSignIn')),
        ),
        TextButton(
          onPressed: () => launchUrl(Uri.parse('${NextendoConfig.apiBase}/register.html'), mode: LaunchMode.externalApplication),
          child: Text(_text('nextendoCreateAccount')),
        ),
      ];
    }
    return [
      ListTile(
        contentPadding: EdgeInsets.zero,
        leading: const CircleAvatar(child: Icon(Icons.person)),
        title: Text(_text('nextendoSignedInAs', {'name': account.shownName})),
        subtitle: Text([
          if (account.shownName != account.username) account.username,
          if (account.friendCode.isNotEmpty) '${_text('nextendoFriendCode')}: ${account.friendCode}',
        ].join('\n')),
      ),
      Text(_text('nextendoStatusTitle'), style: Theme.of(context).textTheme.titleSmall),
      _status(true, _text('nextendoStatusAccount')),
      if (config.serversConfigured)
        _status(true, _text('nextendoStatusServersOk'))
      else if (config.serversIssue == 'same')
        _status(false, _text('nextendoStatusServersSame'), _text('nextendoActionServersSame'))
      else
        _status(false, _text('nextendoStatusServersMissing'), _text('nextendoActionServers')),
      if (NextendoOnlinePlay.lastSmashTls == 'refused')
        _status(false, _text('nextendoSmashTlsRejected')),
      if (NextendoOnlinePlay.lastSmashTls == 'compatibility')
        ListTile(
          contentPadding: EdgeInsets.zero,
          dense: true,
          leading: const Icon(Icons.info_outline),
          title: Text(_text('nextendoSmashTlsCompatibility')),
        ),
      if (_engine == null)
        _status(null, _text('nextendoStatusEngineChecking'))
      else if (_engine!)
        _status(true, _text('nextendoStatusEngineOk'))
      else
        _status(false, _text('nextendoStatusEngineMissing'), _text('nextendoActionEngine')),
      Builder(builder: (context) {
        final missing = _missing(config);
        return SwitchListTile(
          key: const ValueKey('nextendo-online-play'),
          contentPadding: EdgeInsets.zero,
          title: Text(_text('nextendoOnlinePlay')),
          subtitle: Text(missing ?? _text('nextendoOnlinePlayHint')),
          value: _online && missing == null,
          onChanged: _busy || missing != null
              ? null
              : (value) async {
                  await NextendoOnlinePlay.setEnabled(value);
                  if (mounted) setState(() => _online = value);
                },
        );
      }),
      if (_smashPrivateTls || NextendoOnlinePlay.lastSmashTls != null)
        SwitchListTile(
          key: const ValueKey('nextendo-smash-private-tls'),
          contentPadding: EdgeInsets.zero,
          title: Text(_text('nextendoSmashPrivateTls')),
          subtitle: Text(_text('nextendoSmashPrivateTlsHint')),
          value: _smashPrivateTls,
          onChanged: _busy || (!_smashPrivateTls && (_engine != true || !config.serverResolved))
              ? null : _setSmashPrivateTls,
        ),
      Wrap(
        spacing: 8,
        children: [
          OutlinedButton(onPressed: _busy ? null : _check, child: Text(_text('nextendoCheck'))),
          TextButton(onPressed: _busy ? null : _signOut, child: Text(_text('nextendoSignOut'))),
        ],
      ),
    ];
  }

  /// Only while the server addresses are neither in the build nor found by
  /// name: the maintainer enters values for a test. A value the build carries
  /// or a lookup found is shown and cannot be changed here.
  Widget _registration(NextendoConfig config) => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text(_text('nextendoRegistration')),
    children: [
      Text(_text('nextendoRegistrationHint', {'redirect': NextendoConfig.registeredRedirect})),
      for (final field in [
        (_clientId, 'nextendoClientId', config.clientIdFromBuild),
        (_server, 'nextendoServer', config.serverFromBuild || config.serverResolved),
        (_nat, 'nextendoNat', config.natFromBuild || config.natResolved),
      ])
        TextField(
          controller: field.$1,
          enabled: !field.$3,
          autocorrect: false,
          enableSuggestions: false,
          keyboardType: field.$2 == 'nextendoClientId' ? TextInputType.text : const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: _text(field.$2)),
        ),
      Align(
        alignment: AlignmentDirectional.centerEnd,
        child: TextButton(onPressed: _busy ? null : _saveLocal, child: Text(_text('save'))),
      ),
    ],
  );

  /// Nextendo's signed catalog: each game and the exact version its servers
  /// accept. NPLN titles also need online patches RewindBox does not apply yet.
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
              const SizedBox(height: 8),
              if (config == null && _message == null) const Center(child: CircularProgressIndicator()),
              if (config != null) ..._accountSection(config),
              if (_busy) const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator()),
              if (_message != null) Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(_message!, style: _messageIsError ? TextStyle(color: Theme.of(context).colorScheme.error) : null),
              ),
              const SizedBox(height: 8),
              Text(_text('nextendoGames'), style: Theme.of(context).textTheme.bodySmall),
              const SizedBox(height: 4),
              Text(_text('nextendoLimits'), style: Theme.of(context).textTheme.bodySmall),
              _games(),
              if (config != null && !config.serversAutomatic) _registration(config),
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
