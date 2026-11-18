import 'package:flutter/material.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:material_symbols_icons/symbols.dart';

import '../l10n/switch_online_locale.dart';
import '../services/nextendo/nextendo_config.dart';
import '../services/nextendo/nextendo_service.dart';
import 'nextendo_dialog.dart';

typedef _FriendsResult = ({List<String> names, Object? error});

class NextendoFriendsButton extends StatelessWidget {
  const NextendoFriendsButton({super.key, this.service});

  final NextendoService? service;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: SwitchOnlineLocale.text(context, 'nextendoFriendsOnline'),
      child: Semantics(
        button: true,
        child: InkWell(
          customBorder: const CircleBorder(),
          onTap: () => showDialog<void>(
            context: context,
            builder: (_) =>
                _FriendsDialog(service: service ?? NextendoService.instance),
          ),
          child: Icon(
            Symbols.group_rounded,
            size: 14.r,
            color: Theme.of(context).colorScheme.onSurface,
          ),
        ),
      ),
    );
  }
}

class _FriendsDialog extends StatefulWidget {
  const _FriendsDialog({required this.service});

  final NextendoService service;

  @override
  State<_FriendsDialog> createState() => _FriendsDialogState();
}

class _FriendsDialogState extends State<_FriendsDialog> {
  late final Future<NextendoConfig> _configuration;
  NextendoAccount? _owner;
  Future<_FriendsResult>? _friends;

  @override
  void initState() {
    super.initState();
    _configuration = _loadConfiguration();
  }

  Future<NextendoConfig> _loadConfiguration() async {
    final config = await NextendoConfig.load();
    if (config.canSignIn) await widget.service.restore(config);
    return config;
  }

  Future<_FriendsResult> _loadFriends(NextendoConfig config) async {
    try {
      return (names: await widget.service.onlineFriends(config), error: null);
    } catch (error) {
      return (names: const <String>[], error: error);
    }
  }

  String _text(String key) => SwitchOnlineLocale.text(context, key);

  void _openAccount() => showDialog<void>(
    context: context,
    builder: (_) => NextendoDialog(service: widget.service),
  );

  Widget _dialog(Widget content, {Widget? action}) => AlertDialog(
    title: Text(_text('nextendoFriendsOnline')),
    content: SizedBox(width: 320, child: content),
    actions: [
      if (action != null) action,
      TextButton(
        onPressed: () => Navigator.of(context).pop(),
        child: Text(MaterialLocalizations.of(context).closeButtonLabel),
      ),
    ],
  );

  Widget _loading() =>
      const Center(heightFactor: 1, child: CircularProgressIndicator());

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<NextendoConfig>(
      future: _configuration,
      builder: (context, settings) {
        if (settings.hasError) return _dialog(Text(_text('nextendoFailed')));
        final config = settings.data;
        if (config == null) return _dialog(_loading());
        if (!config.canSignIn) return _dialog(Text(_text('notConfigured')));
        return ValueListenableBuilder<NextendoAccount?>(
          valueListenable: widget.service.account,
          builder: (context, account, _) {
            if (!identical(_owner, account)) {
              _owner = account;
              _friends = account == null ? null : _loadFriends(config);
            }
            if (account == null) {
              return _dialog(
                Text(_text('signedOut')),
                action: TextButton(
                  onPressed: _openAccount,
                  child: Text(_text('nextendoSignIn')),
                ),
              );
            }
            return FutureBuilder<_FriendsResult>(
              future: _friends,
              builder: (context, result) {
                final answer = result.data;
                if (result.connectionState != ConnectionState.done ||
                    answer == null) {
                  return _dialog(_loading());
                }
                final (:names, :error) = answer;
                final Widget content;
                if (error is NextendoException) {
                  content = Text(
                    SwitchOnlineLocale.text(context, error.code, {
                      'detail': error.detail,
                    }),
                  );
                } else if (error != null) {
                  content = Text(_text('nextendoFailed'));
                } else if (names.isEmpty) {
                  content = Text(_text('nextendoFriendsEmpty'));
                } else {
                  content = ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 240),
                    child: ListView.builder(
                      primary: false,
                      padding: EdgeInsets.zero,
                      shrinkWrap: true,
                      itemCount: names.length,
                      itemBuilder: (_, index) => ListTile(
                        contentPadding: EdgeInsets.zero,
                        dense: true,
                        title: Text(names[index]),
                      ),
                    ),
                  );
                }
                return _dialog(
                  content,
                  action: TextButton(
                    onPressed: () => setState(() {
                      _friends = _loadFriends(config);
                    }),
                    child: Text(_text('nextendoFriendsRefresh')),
                  ),
                );
              },
            );
          },
        );
      },
    );
  }
}
