import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../l10n/switch_online_locale.dart';
import '../services/logger_service.dart';
import '../services/nextendo/nextendo_config.dart';
import '../services/nextendo/nextendo_online_play.dart';
import '../services/nextendo/nextendo_service.dart';

/// The player's Nextendo Network account in RewindBox: sign-in on
/// nextendo.network, the linked identity, the online-play switch and why
/// Nextendo may refuse online play. A build without Nextendo's registration
/// values shows the maintainer's fields instead of the sign-in button.
class NextendoDialog extends StatefulWidget {
  const NextendoDialog({super.key, this.service});
  final NextendoService? service;
  @override
  State<NextendoDialog> createState() => _NextendoDialogState();
}

class _NextendoDialogState extends State<NextendoDialog> {
  NextendoConfig? _config;
  NextendoAccount? _account;
  bool _online = true;
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
      final config = await NextendoConfig.load();
      final account = config.canSignIn ? await _service.restore(config) : null;
      final online = await NextendoOnlinePlay.enabled();
      if (!mounted) return;
      setState(() {
        _config = config;
        _account = account;
        _online = online;
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
    } else if (error is FormatException && const {'clientId', 'serverAddress', 'natAddress'}.contains(error.message)) {
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

  Future<void> _check() => _run(() async {
    final config = _config!;
    final status = await _service.onlineStatus(await _service.gameToken(config));
    if (!mounted) return;
    final known = const {'unknown', 'disabled', 'suspended', 'unverified', 'discord_unlinked', 'elsewhere'}.contains(status.reason);
    setState(() {
      _messageIsError = !status.allowed;
      _message = status.allowed
          ? _text(config.canPlayOnline ? 'nextendoAllowed' : 'nextendoServersMissing')
          : _text(known ? 'nextendoReason_${status.reason}' : 'nextendoReason_other', {'detail': status.reason});
    });
  });

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
      SwitchListTile(
        contentPadding: EdgeInsets.zero,
        title: Text(_text('nextendoOnlinePlay')),
        subtitle: Text(_text(config.canPlayOnline ? 'nextendoOnlinePlayHint' : 'nextendoServersMissing')),
        value: _online && config.canPlayOnline,
        onChanged: _busy || !config.canPlayOnline
            ? null
            : (value) async {
                await NextendoOnlinePlay.setEnabled(value);
                if (mounted) setState(() => _online = value);
              },
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

  /// Only in a build without Nextendo's values: the maintainer enters what the
  /// Nextendo Developers portal and Nextendo's team issued for RewindBox.
  Widget _registration() => ExpansionTile(
    tilePadding: EdgeInsets.zero,
    title: Text(_text('nextendoRegistration')),
    children: [
      Text(_text('nextendoRegistrationHint', {'redirect': NextendoConfig.registeredRedirect})),
      for (final field in [(_clientId, 'nextendoClientId'), (_server, 'nextendoServer'), (_nat, 'nextendoNat')])
        TextField(
          controller: field.$1,
          autocorrect: false,
          enableSuggestions: false,
          decoration: InputDecoration(labelText: _text(field.$2)),
        ),
      Align(
        alignment: AlignmentDirectional.centerEnd,
        child: TextButton(onPressed: _busy ? null : _saveLocal, child: Text(_text('save'))),
      ),
    ],
  );

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
              Text(_text('nextendoLimits'), style: Theme.of(context).textTheme.bodySmall),
              if (config != null && !config.fromBuild) _registration(),
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
