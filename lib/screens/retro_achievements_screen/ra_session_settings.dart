import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_localization/flutter_localization.dart';

import '../../l10n/app_locale.dart';
import '../../services/game_service.dart' show GamepadNavigationManager;
import '../../services/retro_achievements_session_service.dart';
import '../../utils/gamepad_nav.dart';
import '../../utils/login_form_selection.dart';

/// RetroAchievements Web API keys are 32 letters and digits. A password field
/// holding that shape, or the account's own key, almost certainly received
/// the key by mistake (Build 610 recording). Only a live warning for the
/// shape: a real password may look the same and is still sent.
bool raLooksLikeWebApiKey(String value, {String knownKey = ''}) {
  final entered = value.trim();
  if (entered.isEmpty) return false;
  final key = knownKey.trim();
  if (key.isNotEmpty && entered == key) return true;
  return RegExp(r'^[A-Za-z0-9]{32}$').hasMatch(entered);
}

/// Input errors, authentication refusals and network/server failures keep
/// separate messages. Raw codes are never shown to the player.
String raSessionErrorLabel(String? code) {
  if (code?.startsWith('login_failed_') ?? false) {
    // Dolphin forwards the signed rcheevos result of its token login.
    return switch (code) {
      'login_failed_-33' || 'login_failed_-34' || 'login_failed_-35' => AppLocale.raSessionTokenRejected,
      'login_failed_-32' => AppLocale.raSessionNetworkError,
      'login_failed_-26' => AppLocale.raSessionServerError,
      _ => AppLocale.raSessionLoginError,
    };
  }
  return switch (code) {
  'RA_INPUT_REQUIRED' => AppLocale.raSessionInputRequired,
  'RA_LOGIN_REQUIRED' || 'RA_CREDENTIALS_MISSING' => AppLocale.raSessionLoginNeeded,
  'RA_AUTHENTICATION_FAILED' || 'RA_LOGIN_FAILED' => AppLocale.raSessionLoginError,
  'RA_TOKEN_REJECTED' => AppLocale.raSessionTokenRejected,
  'RA_SERVER_ERROR' => AppLocale.raSessionServerError,
  'RA_NETWORK_UNAVAILABLE' || 'RA_NETWORK' || 'RA_RATE_LIMITED' || 'RA_SYNC_PENDING' => AppLocale.raSessionNetworkError,
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
    required this.onAccountChanged, this.service, this.dashboardAccount = '', this.webApiKey = ''});
  final String initialUsername;
  final Future<void> Function(String?) onAccountChanged;
  final RetroAchievementsSessionService? service;

  /// One account for everything: when the RetroAchievements tab is already
  /// signed in, the in-game session uses that account and only asks for its
  /// password once (no second username/sign-in).
  final String dashboardAccount;

  /// The saved Web API key, only to recognize it when it is pasted into the
  /// password field (a refused sign-in that looked like a lost password).
  final String webApiKey;

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

  final _formErrorKey = GlobalKey();

  /// A local refusal (the Web API key pasted as password); never sent.
  String? _localErrorKey;

  int get _migrationSlots => !service.authenticated && service.migrationCandidates.isNotEmpty
      ? service.migrationCandidates.length + 1 : 0;

  /// The sign-in form is shown when no account is stored, or when an engine
  /// reported that RetroAchievements refused the stored token.
  bool get _showForm => !service.authenticated || service.tokenRejected;

  /// The account of the RetroAchievements tab, reused instead of a second
  /// username field.
  String get _sharedAccount => widget.dashboardAccount.trim();
  bool get _usesSharedAccount => _sharedAccount.isNotEmpty;

  int get _passwordSlot => _migrationSlots + (_usesSharedAccount ? 0 : 1);
  int get _loginSlot => _passwordSlot + 1;

  @override
  List<FocusNode?> get selectionSlots => !_showForm
      ? [null, null, null, null]
      : [for (var i = 0; i < _migrationSlots; i++) null,
         if (!_usesSharedAccount) usernameFocus, passwordFocus, null, null];

  int get _closeSlot => _showForm ? _loginSlot + 1 : 3;
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
    if (!_showForm) {
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
    } else if (selectedSlot == _loginSlot) {
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
    final webKey = widget.webApiKey.trim();
    if (webKey.isNotEmpty && enteredPassword.trim() == webKey) {
      // The 1 November 2026 recording: the Web API key (32 characters) was
      // pasted here; RetroAchievements refused it and the field was cleared.
      setState(() => _localErrorKey = AppLocale.raPasswordIsApiKey);
      _keepPasswordForCorrection();
      return;
    }
    if (_localErrorKey != null) setState(() => _localErrorKey = null);
    final success = await service.login(_usesSharedAccount ? _sharedAccount : username.text, enteredPassword);
    if (success) {
      // Only now: a refused password stays in the (obscured) field so the
      // player sees what was sent and can correct it. Never stored. The
      // dialog may already be closed (its controller then is disposed).
      if (mounted) password.clear();
      // Signing in for games is asking for achievements in games.
      if (!service.preferences.enabled) await service.setEnabled(true);
      await widget.onAccountChanged(service.username);
      if (mounted) { exitTextEntry(); resetSelection(); }
    } else if (mounted) {
      _keepPasswordForCorrection();
    }
  }

  /// Keeps the refused password selected (typing replaces it) and brings its
  /// error, shown under the button, into view.
  void _keepPasswordForCorrection() {
    password.selection = TextSelection(baseOffset: 0, extentOffset: password.text.length);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final target = _formErrorKey.currentContext;
      if (mounted && target != null) {
        unawaited(Scrollable.ensureVisible(target, duration: const Duration(milliseconds: 150)));
      }
    });
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
    final theme = Theme.of(context);
    // On a landscape iPhone the keyboard leaves ~180 pt. Build 608 kept the
    // default dialog insets, title padding and a bottom action row, so the
    // scrollable content got a zero-height viewport and the focused fields
    // disappeared while typing. Compact chrome keeps the field on screen.
    final keyboard = MediaQuery.viewInsetsOf(context).bottom > 0;
    final sessionError = session?.running == true && (session?.errorCode?.isNotEmpty ?? false)
        ? session!.errorCode : null;
    final error = service.errorCode ?? (service.tokenRejected ? 'RA_TOKEN_REJECTED' : sessionError);
    return AlertDialog(
      insetPadding: EdgeInsets.symmetric(horizontal: 24, vertical: keyboard ? 4 : 24),
      titlePadding: EdgeInsets.fromLTRB(24, keyboard ? 4 : 16, 12, 0),
      contentPadding: EdgeInsets.fromLTRB(24, keyboard ? 4 : 12, 24, keyboard ? 8 : 20),
      title: Row(children: [
        Expanded(child: Text(text(AppLocale.raSessionSettings),
          style: keyboard ? theme.textTheme.titleMedium : null)),
        _highlight(_closeSlot, TextButton(onPressed: () => Navigator.of(context).pop(),
          child: Text(text(AppLocale.close)))),
      ]),
      content: SizedBox(width: 560, child: SingleChildScrollView(controller: scroll,
        child: Column(mainAxisSize: MainAxisSize.min, crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          if (!service.initialized && service.errorCode == null) const LinearProgressIndicator(),
          Text(text(_showForm && _usesSharedAccount
              ? AppLocale.raSessionPasswordOnly : AppLocale.raSessionAccountHelp)),
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
          if (_showForm) ...[
            // RetroAchievements usernames are ASCII letters/digits: no
            // autocorrection, smart punctuation or capitalization may alter
            // them (an accidental "´" or autocorrected name was a refusal).
            if (_usesSharedAccount)
              InputDecorator(key: const ValueKey('ra-native-account'),
                decoration: InputDecoration(labelText: text(AppLocale.username)),
                child: Text(_sharedAccount))
            else
              _highlight(_migrationSlots, TextField(key: const ValueKey('ra-native-username'), controller: username,
                focusNode: usernameFocus, enabled: !service.busy, autocorrect: false,
                enableSuggestions: false, textCapitalization: TextCapitalization.none,
                smartDashesType: SmartDashesType.disabled, smartQuotesType: SmartQuotesType.disabled,
                keyboardType: TextInputType.visiblePassword,
                decoration: InputDecoration(labelText: text(AppLocale.username)),
                textInputAction: TextInputAction.next, onSubmitted: (_) => passwordFocus.requestFocus())),
            const SizedBox(height: 8),
            _highlight(_passwordSlot, TextField(key: const ValueKey('ra-native-password'), controller: password,
              focusNode: passwordFocus, enabled: !service.busy, obscureText: true,
              enableSuggestions: false, autocorrect: false,
              smartDashesType: SmartDashesType.disabled, smartQuotesType: SmartQuotesType.disabled,
              // "Account password": the Web API key never goes here.
              decoration: InputDecoration(labelText: text(AppLocale.raAccountPasswordLabel),
                hintText: text(AppLocale.raAccountPasswordHint)),
              textInputAction: TextInputAction.done,
              onChanged: (_) => setState(() {}),
              onSubmitted: (_) => _login())),
            if (raLooksLikeWebApiKey(password.text, knownKey: widget.webApiKey))
              Padding(key: const ValueKey('ra-native-password-looks-like-key'),
                padding: const EdgeInsets.only(top: 6),
                child: Text(text(AppLocale.raPasswordLooksLikeApiKey),
                  style: TextStyle(color: theme.colorScheme.error))),
            const SizedBox(height: 12),
            _highlight(_loginSlot, FilledButton(onPressed: service.busy ? null : _login,
              child: Text(text(AppLocale.login)))),
            // Directly under the button: a refusal must never be hidden below
            // the visible part of the dialog (the recording showed only the
            // later "enter your password" message for an emptied field).
            if (_localErrorKey != null || error != null)
              Padding(key: _formErrorKey, padding: const EdgeInsets.only(top: 8),
                child: Text(text(_localErrorKey ?? raSessionErrorLabel(error)),
                  style: TextStyle(color: theme.colorScheme.error))),
          ] else ...[
            Text(service.username, style: Theme.of(context).textTheme.titleMedium),
            _highlight(0, SwitchListTile.adaptive(key: const ValueKey('ra-central-enabled'),
              contentPadding: EdgeInsets.zero, title: Text(text(AppLocale.raSessionEnable)),
              subtitle: service.preferences.enabled ? null : Text(text(AppLocale.raSessionEnableHint)),
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
          if (error != null) ...[
            const SizedBox(height: 8),
            if (!_showForm)
              Text(text(raSessionErrorLabel(error)),
                style: TextStyle(color: Theme.of(context).colorScheme.error)),
            if (!service.initialized || const {'RA_MIGRATION_EXPIRED', 'RA_STORAGE_UNAVAILABLE'}.contains(service.errorCode)) TextButton(onPressed: service.busy ? null : service.retry,
              child: Text(text(AppLocale.retry))),
            if (service.canRecoverLegacy) TextButton(onPressed: service.busy ? null : _ignoreLegacy,
              child: Text(text(AppLocale.raSessionMigrationSkip))),
          ],
          ExpansionTile(tilePadding: EdgeInsets.zero,
            title: Text(text(AppLocale.raSessionCompatibility)), children: [
              ListTile(title: const Text('Switch · 3DS · Atari 5200 · Game & Watch · Sega Pico'),
                subtitle: Text(text(AppLocale.raSessionUnsupported))),
              // Implemented through optional RPCS3 Core hooks, not yet validated on device.
              ListTile(title: const Text('PS3 · RPCS3'), subtitle: Text(text(AppLocale.raSessionUnverified))),
              ListTile(title: const Text('NES/FDS · Nestopia'), subtitle: Text(text(AppLocale.raSessionUnsupported))),
              ListTile(title: const Text('Gearcoleco · Genesis Plus GX Wide · PicoDrive (SMS/Game Gear)'),
                subtitle: Text(text(AppLocale.raSessionUnverified))),
            ]),
          if (service.busy) const LinearProgressIndicator(),
        ]))),
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
