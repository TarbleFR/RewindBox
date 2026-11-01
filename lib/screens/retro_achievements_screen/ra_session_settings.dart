import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';

import '../../l10n/app_locale.dart';
import '../../services/game_service.dart' show GamepadNavigationManager;
import '../../services/retro_achievements_session_service.dart';
import '../../utils/gamepad_nav.dart';
import '../../utils/login_form_selection.dart';

String raSessionErrorLabel(String? code) {
  if (code?.startsWith('login_failed_') ?? false) return AppLocale.raSessionLoginError;
  return switch (code) {
  'RA_LOGIN_REQUIRED' || 'RA_CREDENTIALS_MISSING' => AppLocale.raSessionLoginNeeded,
  'RA_AUTHENTICATION_FAILED' || 'RA_LOGIN_FAILED' => AppLocale.raSessionLoginError,
  'RA_NETWORK_UNAVAILABLE' || 'RA_NETWORK' || 'RA_RATE_LIMITED' => AppLocale.raSessionNetworkError,
  'RA_STORAGE_UNAVAILABLE' || 'RA_MIGRATION_EXPIRED' => AppLocale.raSessionStorageError,
  'RA_HARDCORE_OPTIONS' || 'RA_HARDCORE_RESET_REQUIRED' || 'hardcore_inactive' => AppLocale.raSessionHardcoreError,
  'RA_UNSUPPORTED' => AppLocale.raSessionUnsupported,
  'RA_CORE_UNSUPPORTED' || 'RA_MEMORY_UNAVAILABLE' || 'RA_ACHIEVEMENTS_UNSUPPORTED' => AppLocale.raSessionUnverified,
  'RA_NO_ACHIEVEMENTS' || 'RA_GAME_NOT_RECOGNIZED' => AppLocale.noAchievementsFound,
  _ => AppLocale.raSessionUnavailable,
};
}

/// This dialog is opened only by RAContent, never by an in-game menu or a
/// console settings page. The native adapters have no equivalent write UI.
class RASessionSettings extends StatefulWidget {
  const RASessionSettings({super.key, required this.initialUsername,
    required this.onAccountChanged, this.service});
  final String initialUsername;
  final Future<void> Function(String?) onAccountChanged;
  final RetroAchievementsSessionService? service;

  @override
  State<RASessionSettings> createState() => _RASessionSettingsState();
}

class _RASessionSettingsState extends State<RASessionSettings>
    with LoginFormSelection<RASessionSettings> {
  late final RetroAchievementsSessionService service;
  late final TextEditingController username;
  final password = TextEditingController();
  final usernameFocus = FocusNode();
  final passwordFocus = FocusNode();
  final scroll = ScrollController();
  late final GamepadNavigation navigation;

  int get _migrationSlots => !service.authenticated && service.migrationCandidates.isNotEmpty
      ? service.migrationCandidates.length + 1 : 0;

  @override
  List<FocusNode?> get selectionSlots => service.authenticated
      ? [null, null, null, null]
      : [for (var i = 0; i < _migrationSlots; i++) null, usernameFocus, passwordFocus, null, null];
  @override
  List<FocusNode> get ownedFocusNodes => [usernameFocus, passwordFocus];

  @override
  void initState() {
    super.initState();
    service = widget.service ?? RetroAchievementsSessionService.shared;
    username = TextEditingController(text: service.username.isNotEmpty ? service.username : widget.initialUsername);
    service.addListener(_changed);
    unawaited(service.initialize());
    attachFocusSelectionListeners();
    navigation = GamepadNavigation(
      onNavigateUp: () => moveSelection(-1), onNavigateDown: () => moveSelection(1),
      onSelectItem: _select, isTextFieldFocused: isAnyFieldFocused,
      onBack: () { if (isAnyFieldFocused()) { exitTextEntry(); } else { Navigator.of(context).pop(); } },
      allowRepeat: false,
    );
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      navigation.initialize();
      GamepadNavigationManager.pushLayer('ra_session_settings',
        onActivate: navigation.activate, onDeactivate: navigation.deactivate);
    });
  }

  void _changed() { if (mounted) setState(() {}); }

  void _select() {
    if (service.busy || focusSelectedField()) return;
    if (service.authenticated) {
      switch (selectedSlot) {
        case 0: unawaited(service.setEnabled(!service.preferences.enabled));
        case 1: unawaited(service.setHardcore(!service.preferences.hardcore));
        case 2: unawaited(_logout());
        default: Navigator.of(context).pop();
      }
    } else if (selectedSlot < _migrationSlots) {
      if (selectedSlot < service.migrationCandidates.length) {
        unawaited(_importLegacy(service.migrationCandidates[selectedSlot].id));
      } else {
        unawaited(_ignoreLegacy());
      }
    } else if (selectedSlot == _migrationSlots + 2) {
      unawaited(_login());
    } else {
      Navigator.of(context).pop();
    }
  }

  Future<void> _importLegacy(String id) async {
    if (await service.importLegacy(id)) {
      await widget.onAccountChanged(service.username);
      if (mounted) resetSelection();
    }
  }

  Future<void> _ignoreLegacy() async {
    if (await service.ignoreLegacy()) {
      await widget.onAccountChanged(null);
      if (mounted) resetSelection();
    }
  }

  Future<void> _login() async {
    if (service.busy) return;
    final enteredPassword = password.text;
    password.clear();
    final success = await service.login(username.text, enteredPassword);
    if (success) {
      await widget.onAccountChanged(service.username);
      if (mounted) { exitTextEntry(); resetSelection(); }
    }
  }

  Future<void> _logout() async {
    if (await service.logout()) {
      await widget.onAccountChanged(null);
      if (mounted) resetSelection();
    }
  }

  Widget _highlight(int slot, Widget child) => DecoratedBox(
    decoration: BoxDecoration(borderRadius: BorderRadius.circular(8),
      border: Border.all(color: isSelected(slot) ? Theme.of(context).colorScheme.primary : Colors.transparent)),
    child: child,
  );

  @override
  Widget build(BuildContext context) {
    String text(String key) => key.getString(context);
    final session = service.session;
    return AlertDialog(
      title: Text(text(AppLocale.raSessionSettings)),
      content: SizedBox(width: 560, child: SingleChildScrollView(controller: scroll,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (!service.initialized && service.errorCode == null) const LinearProgressIndicator(),
          Text(text(AppLocale.raSessionAccountHelp)),
          const SizedBox(height: 12),
          if (service.migrationCandidates.isNotEmpty && !service.authenticated) ...[
            Text(text(AppLocale.raSessionMigrationChoice)),
            for (final (index, candidate) in service.migrationCandidates.indexed)
              Card(child: Padding(padding: const EdgeInsets.all(12), child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch, children: [
                  Text(candidate.username, style: Theme.of(context).textTheme.titleMedium),
                  Text(candidate.sources.join(' · ')),
                  Text('${text(AppLocale.raSessionEnable)}: ${text(candidate.enabled ? AppLocale.enabled : AppLocale.disabled)}'),
                  Text('${text(AppLocale.raSessionHardcore)}: ${text(candidate.hardcore ? AppLocale.enabled : AppLocale.disabled)}'),
                  _highlight(index, TextButton(onPressed: service.busy ? null : () => _importLegacy(candidate.id),
                    child: Text(text(AppLocale.raSessionMigrationImport)))),
                ]))),
            _highlight(service.migrationCandidates.length, TextButton(
              onPressed: service.busy ? null : _ignoreLegacy,
              child: Text(text(AppLocale.raSessionMigrationSkip)))),
            const Divider(),
          ],
          if (!service.authenticated) ...[
            _highlight(_migrationSlots, TextField(key: const ValueKey('ra-native-username'), controller: username,
              focusNode: usernameFocus, enabled: !service.busy, autocorrect: false,
              decoration: InputDecoration(labelText: text(AppLocale.username)),
              textInputAction: TextInputAction.next, onSubmitted: (_) => passwordFocus.requestFocus())),
            const SizedBox(height: 8),
            _highlight(_migrationSlots + 1, TextField(key: const ValueKey('ra-native-password'), controller: password,
              focusNode: passwordFocus, enabled: !service.busy, obscureText: true,
              enableSuggestions: false, autocorrect: false,
              decoration: InputDecoration(labelText: text(AppLocale.password)),
              onSubmitted: (_) => _login())),
            const SizedBox(height: 12),
            _highlight(_migrationSlots + 2, FilledButton(onPressed: service.busy ? null : _login,
              child: Text(text(AppLocale.login)))),
          ] else ...[
            Text(service.username, style: Theme.of(context).textTheme.titleMedium),
            _highlight(0, SwitchListTile.adaptive(key: const ValueKey('ra-central-enabled'),
              contentPadding: EdgeInsets.zero, title: Text(text(AppLocale.raSessionEnable)),
              value: service.preferences.enabled,
              onChanged: service.busy || !service.initialized ? null : (value) => service.setEnabled(value))),
            _highlight(1, SwitchListTile.adaptive(key: const ValueKey('ra-central-hardcore'),
              contentPadding: EdgeInsets.zero, title: Text(text(AppLocale.raSessionHardcore)),
              subtitle: Text(text(AppLocale.raSessionHardcoreHelp)), value: service.preferences.hardcore,
              onChanged: service.busy || !service.initialized ? null : (value) => service.setHardcore(value))),
            _highlight(2, TextButton(onPressed: service.busy ? null : _logout,
              child: Text(text(AppLocale.logout)))),
          ],
          const SizedBox(height: 12),
          Text(text(AppLocale.raSessionNotifications)),
          const SizedBox(height: 8),
          Text(text(service.changesPending ? AppLocale.raSessionPending : AppLocale.raSessionNextLaunch)),
          const Divider(),
          Text(text(session?.running == true
            ? !session!.supported ? AppLocale.raSessionUnsupported
              : session.active ? AppLocale.raSessionActive : AppLocale.raSessionAwaiting
            : service.preferences.enabled ? AppLocale.raSessionReady : AppLocale.raSessionNoGame)),
          if (session?.running == true && session!.gameLoaded)
            Text('${text(AppLocale.raSessionHardcore)}: ${text(session.hardcoreActive ? AppLocale.enabled : AppLocale.disabled)}'),
          if (service.errorCode != null || (session?.running == true && (session?.errorCode?.isNotEmpty ?? false))) ...[
            const SizedBox(height: 8),
            Text(text(raSessionErrorLabel(service.errorCode ?? session?.errorCode)),
              style: TextStyle(color: Theme.of(context).colorScheme.error)),
            if (!service.initialized || const {'RA_MIGRATION_EXPIRED', 'RA_STORAGE_UNAVAILABLE'}.contains(service.errorCode)) TextButton(onPressed: service.busy ? null : service.retry,
              child: Text(text(AppLocale.retry))),
            if (service.canRecoverLegacy) TextButton(onPressed: service.busy ? null : _ignoreLegacy,
              child: Text(text(AppLocale.raSessionMigrationSkip))),
          ],
          ExpansionTile(tilePadding: EdgeInsets.zero,
            title: Text(text(AppLocale.raSessionCompatibility)), children: [
              ListTile(title: const Text('PS3 · Switch · 3DS · Atari 5200 · Game & Watch · Sega Pico'),
                subtitle: Text(text(AppLocale.raSessionUnsupported))),
              ListTile(title: const Text('NES/FDS · Nestopia'), subtitle: Text(text(AppLocale.raSessionUnsupported))),
              ListTile(title: const Text('Gearcoleco · Genesis Plus GX Wide · PicoDrive (SMS/Game Gear)'),
                subtitle: Text(text(AppLocale.raSessionUnverified))),
            ]),
          if (service.busy) const LinearProgressIndicator(),
        ]))),
      actions: [_highlight(_migrationSlots + 3, TextButton(onPressed: () => Navigator.of(context).pop(),
        child: Text(text(AppLocale.close))))],
    );
  }

  @override
  void dispose() {
    GamepadNavigationManager.popLayer('ra_session_settings');
    navigation.dispose();
    detachFocusSelectionListeners();
    service.removeListener(_changed);
    username.dispose(); password.dispose(); usernameFocus.dispose(); passwordFocus.dispose(); scroll.dispose();
    super.dispose();
  }
}
