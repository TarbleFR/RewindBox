import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neostation/utils/gamepad_nav.dart';
import 'package:provider/provider.dart';
import '../../providers/retro_achievements_provider.dart';
import '../../widgets/confirm_action_dialog.dart';
import '../../widgets/custom_notification.dart';
import '../../responsive.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:flutter/gestures.dart';
import '../../services/game_service.dart' show GamepadNavigationManager;
import '../app_screen.dart' show AppNavigation;
import 'package:flutter_localization/flutter_localization.dart';
import 'package:neostation/l10n/app_locale.dart';
import '../../utils/login_form_selection.dart';
import 'ra_dashboard.dart';
import 'ra_session_settings.dart';
import '../../services/retro_achievements_session_service.dart';
import '../../widgets/glass/glass_surface.dart';

class RAContent extends StatefulWidget {
  const RAContent({super.key});

  @override
  State<RAContent> createState() => _RAContentState();
}

class _RAContentState extends State<RAContent>
    with LoginFormSelection<RAContent> {
  final TextEditingController _usernameController = TextEditingController();
  final TextEditingController _apiKeyController = TextEditingController();
  // One sign-in for everything: the account password (in-game achievements,
  // never stored) is entered in the same form as the Web API key.
  final TextEditingController _passwordController = TextEditingController();
  final FocusNode _usernameFocus = FocusNode();
  final FocusNode _passwordFocus = FocusNode();
  final FocusNode _apiKeyFocus = FocusNode();
  final ScrollController _loginScrollController = ScrollController();
  final ScrollController _dashboardScrollController = ScrollController();

  bool _logoutSelected = false;
  bool _scrollingToLogout = false;
  bool _obscureApiKey = true;
  bool _obscurePassword = true;
  // This form's own in-game sign-in (a sign-in from the dialog only disables it).
  bool _signingIn = false;
  GamepadNavigation? _gamepadNav;
  RetroAchievementsSessionService? _boundSession;
  String? _displayedAccount;

  RetroAchievementsSessionService get _session =>
      _boundSession ?? RetroAchievementsSessionService.shared;

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final session = context.read<RetroAchievementsProvider>().sessionService ??
        RetroAchievementsSessionService.shared;
    if (identical(session, _boundSession)) return;
    _boundSession?.removeListener(_syncAccountFields);
    _boundSession = session;
    session.addListener(_syncAccountFields);
    _syncAccountFields();
  }

  /// Pre-fills the Web form with the in-game account name, without ever
  /// discarding what the player typed or pasted. Build 608 rewrote the username
  /// and cleared the API key on every in-game account notification (for
  /// example right after signing in from the in-game dialog), so a pasted key
  /// silently vanished before "Sign in" was pressed.
  void _syncAccountFields() {
    if (!mounted || !_session.available || !_session.initialized) return;
    final account = _session.authenticated ? _session.username : '';
    final previous = _displayedAccount;
    if (previous == account.toLowerCase()) {
      setState(() {});
      return;
    }
    _displayedAccount = account.toLowerCase();
    final typed = _usernameController.text.trim();
    if (account.isNotEmpty &&
        (typed.isEmpty || (previous != null && typed.toLowerCase() == previous))) {
      _usernameController.text = account;
    }
    setState(() {});
  }

  /// The password is asked in the same form until the in-game session is
  /// signed in (or its token was refused); afterwards only the key remains.
  bool get _needsInGamePassword {
    final session = _session;
    if (!session.available) return false;
    return !(session.initialized && session.authenticated && !session.tokenRejected);
  }

  /// Signed in for games (token saved in the Keychain): the tab says so and
  /// only offers the optional statistics key, never a sign-in form again
  /// (maintainer report, 2 November 2026: the form looked like a sign-out).
  bool get _signedInForGames {
    final session = _session;
    return session.available && session.initialized && session.authenticated && !session.tokenRejected;
  }

  int get _usernameSlot => _signedInForGames ? -1 : 0;
  int get _passwordSlot => _needsInGamePassword ? 1 : -1;
  int get _apiKeySlot => (_signedInForGames ? 0 : 1) + (_needsInGamePassword ? 1 : 0);
  int get _getKeySlot => _apiKeySlot + 1;

  @override
  List<FocusNode?> get selectionSlots => [
    if (!_signedInForGames) _usernameFocus,
    if (_needsInGamePassword) _passwordFocus,
    _apiKeyFocus,
    null,
    null,
  ];

  @override
  List<FocusNode> get ownedFocusNodes => [_usernameFocus, _passwordFocus, _apiKeyFocus];

  @override
  void initState() {
    super.initState();
    attachFocusSelectionListeners();
    _dashboardScrollController.addListener(_releaseLogoutOnScroll);
    _initControllerNavigation();
  }

  void _initControllerNavigation() {
    _gamepadNav = GamepadNavigation(
      onNavigateUp: _handleNavigateUp,
      onNavigateDown: _handleNavigateDown,
      onNavigateLeft: _handleNavigateLeft,
      onNavigateRight: _handleNavigateRight,
      onSelectItem: _selectCurrent,
      onPreviousTab: AppNavigation.previousTab,
      onNextTab: AppNavigation.nextTab,
      onLeftBumper: AppNavigation.previousTab,
      onRightBumper: AppNavigation.nextTab,
      onSettings: _openSessionSettings,
      allowRepeat: false,
      isTextFieldFocused: isAnyFieldFocused,
      onBack: exitTextEntry,
    );
    _gamepadNav!.initialize();
    GamepadNavigationManager.pushLayer(
      'ra_content',
      onActivate: () => _gamepadNav?.activate(),
      onDeactivate: () => _gamepadNav?.deactivate(),
    );
  }

  void _selectCurrent() {
    final raProvider = context.read<RetroAchievementsProvider>();
    if (raProvider.isConnected) {
      if (_logoutSelected) _requestDisconnect();
      return;
    }
    if (focusSelectedField()) return;
    if (selectedSlot == _getKeySlot) {
      _openRaControlPanel();
      return;
    }
    _connectToRA();
  }

  bool _setLogoutSelected(bool selected) {
    if (!mounted || _logoutSelected == selected) return false;
    setState(() => _logoutSelected = selected);
    return true;
  }

  void _releaseLogoutOnScroll() {
    if (_scrollingToLogout) return;
    if (!_logoutSelected || !_dashboardScrollController.hasClients) return;
    final position = _dashboardScrollController.position;
    if (position.pixels > position.minScrollExtent + 1) {
      _setLogoutSelected(false);
    }
  }

  Future<void> _requestDisconnect() async {
    final confirmed = await ConfirmActionDialog.show(
      context,
      title: AppLocale.disconnectRaConfirm.getString(context),
      body: AppLocale.disconnectRaConfirmBody.getString(context),
      confirmLabel: AppLocale.logout.getString(context),
      icon: Symbols.logout_rounded,
    );
    if (!confirmed || !mounted) return;
    final session = _session;
    final provider = context.read<RetroAchievementsProvider>();
    if (session.available && !await session.logout()) {
      if (mounted) {
        AppNotification.showNotification(context,
          raSessionErrorLabel(session.errorCode).getString(context), type: NotificationType.error);
      }
      return;
    }
    provider.disconnect(clearSavedUser: true);
    if (!mounted) return;
    resetSelection();
    _setLogoutSelected(false);
    AppNotification.showNotification(
      context,
      AppLocale.disconnectedRA.getString(context),
      type: NotificationType.info,
    );
  }

  /// One sign-in for everything (maintainer request, 1 November 2026): the
  /// same form takes the account password, which signs the in-game session in
  /// for every supported emulator (never stored), and the Web API key, which
  /// connects the statistics. Either may be given alone; neither depends on
  /// the other being signed in first.
  Future<void> _connectToRA() async {
    final raProvider = context.read<RetroAchievementsProvider>();
    final session = _session;
    if (raProvider.isLoading || session.busy) return;
    // Signed in for games: the statistics use that same account.
    final username = _signedInForGames ? _session.username.trim() : _usernameController.text.trim();
    final password = _needsInGamePassword ? _passwordController.text : '';
    final apiKey = _apiKeyController.text.trim();
    void notify(String key, NotificationType type) => AppNotification.showNotification(
        context, key.getString(context), type: type);
    if (username.isEmpty || (password.isEmpty && apiKey.isEmpty)) {
      notify(_signedInForGames ? AppLocale.raEnterApiKey
          : _needsInGamePassword ? AppLocale.raSignInSecretRequired : AppLocale.pleaseCompleteAllFields,
        NotificationType.error);
      return;
    }
    if (password.isNotEmpty && apiKey.isNotEmpty && password.trim() == apiKey) {
      // The key pasted twice: RetroAchievements would refuse it as a password.
      notify(AppLocale.raPasswordIsApiKey, NotificationType.error);
      _selectAll(_passwordController);
      return;
    }
    if (password.isNotEmpty) {
      setState(() => _signingIn = true);
      final bool signedIn;
      try {
        signedIn = await session.login(username, password);
      } finally {
        if (mounted) setState(() => _signingIn = false);
      }
      if (!mounted) return;
      if (!signedIn) {
        notify(raSessionErrorLabel(session.errorCode), NotificationType.error);
        _selectAll(_passwordController);
        return;
      }
      _passwordController.clear();
      // Signing in for games is asking for achievements in games.
      if (!session.preferences.enabled) await session.setEnabled(true);
      if (!mounted) return;
      if (apiKey.isEmpty) {
        notify(AppLocale.raInGameSignedInAddKey, NotificationType.success);
        setState(() {});
        return;
      }
    }
    final success = await raProvider.connect(username, apiKey: apiKey);
    if (!mounted) return;
    if (success) {
      notify(AppLocale.successConnectedRA, NotificationType.success);
      if (session.available && session.initialized && !session.authenticated) {
        // Statistics work; achievements in games still need the password once.
        notify(AppLocale.raSessionSignInHint, NotificationType.info);
      }
    } else if (raProvider.accountErrorKey != null) {
      notify(raProvider.accountErrorKey!, NotificationType.error);
    } else if (raProvider.error != null) {
      AppNotification.showNotification(context, raProvider.error!, type: NotificationType.error);
    }
  }

  void _selectAll(TextEditingController controller) {
    controller.selection = TextSelection(baseOffset: 0, extentOffset: controller.text.length);
  }

  Future<void> _openRaControlPanel() async {
    final url = Uri.parse(
      'https://retroachievements.org/settings?tab=applications',
    );
    if (await canLaunchUrl(url)) {
      await launchUrl(url, mode: LaunchMode.externalApplication);
    }
  }

  Future<void> _openSessionSettings() async {
    final session = _session;
    if (!session.available) return;
    final provider = context.read<RetroAchievementsProvider>();
    await showDialog<void>(context: context, builder: (_) => RASessionSettings(
      initialUsername: provider.username.isNotEmpty ? provider.username : _usernameController.text,
      // The tab's account: the dialog then asks only for its password, once.
      dashboardAccount: provider.isConnected ? provider.username : '',
      webApiKey: provider.isConnected ? provider.apiKey : _apiKeyController.text.trim(),
      service: session,
      // Identity follows the provider's lifetime listener. This callback only
      // refreshes visible fields and is safe when the dialog/tab has closed.
      onAccountChanged: (_) async => _syncAccountFields(),
    ));
  }

  @override
  void dispose() {
    _boundSession?.removeListener(_syncAccountFields);
    GamepadNavigationManager.popLayer('ra_content');
    _gamepadNav?.dispose();
    detachFocusSelectionListeners();
    _usernameController.dispose();
    _apiKeyController.dispose();
    _passwordController.dispose();
    _usernameFocus.dispose();
    _passwordFocus.dispose();
    _apiKeyFocus.dispose();
    _loginScrollController.dispose();
    _dashboardScrollController.dispose();
    super.dispose();
  }

  bool _handleNavigateUp() {
    if (!context.read<RetroAchievementsProvider>().isConnected) {
      return moveSelection(-1);
    }
    return _scrollDashboard(-160.r);
  }

  bool _handleNavigateDown() {
    if (!context.read<RetroAchievementsProvider>().isConnected) {
      return moveSelection(1);
    }
    return _scrollDashboard(160.r);
  }

  bool _handleNavigateRight() {
    if (!context.read<RetroAchievementsProvider>().isConnected) return false;
    if (_logoutSelected) return false;
    _scrollHeaderIntoView();
    return _setLogoutSelected(true);
  }

  bool _handleNavigateLeft() {
    if (!context.read<RetroAchievementsProvider>().isConnected) return false;
    return _setLogoutSelected(false);
  }

  void _scrollHeaderIntoView() {
    if (!_dashboardScrollController.hasClients) return;
    final position = _dashboardScrollController.position;
    if (position.pixels <= position.minScrollExtent + 1) return;
    _scrollingToLogout = true;
    _dashboardScrollController
        .animateTo(
          position.minScrollExtent,
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
        )
        .whenComplete(() => _scrollingToLogout = false);
  }

  bool _scrollDashboard(double delta) {
    if (!_dashboardScrollController.hasClients) return false;
    final position = _dashboardScrollController.position;
    final target = (position.pixels + delta).clamp(
      position.minScrollExtent,
      position.maxScrollExtent,
    );
    if ((target - position.pixels).abs() < 1) return false;
    _dashboardScrollController.animateTo(
      target,
      duration: const Duration(milliseconds: 180),
      curve: Curves.easeOutCubic,
    );
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<RetroAchievementsProvider>(
      builder: (context, raProvider, child) {
        return Responsive(
          handheldXS: _buildLandscapeLayout(context, raProvider),
          handheldSmall: _buildLandscapeLayout(context, raProvider),
          handheldMedium: _buildLandscapeLayout(context, raProvider),
          handheldLarge: _buildLandscapeLayout(context, raProvider),
          handheldXL: _buildLandscapeLayout(context, raProvider),
        );
      },
    );
  }

  Widget _buildLandscapeLayout(
    BuildContext context,
    RetroAchievementsProvider raProvider,
  ) {
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    final safePadding = MediaQuery.viewPaddingOf(context);
    final isIOS = defaultTargetPlatform == TargetPlatform.iOS;
    final safeLeft = isIOS ? safePadding.left : 0.0;
    final safeRight = isIOS ? safePadding.right : 0.0;

    return Padding(
      padding: EdgeInsets.fromLTRB(12.r + safeLeft, 0, 12.r + safeRight, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(height: 64.r),
          if (_session.available) _buildInGameControls(context, raProvider),
          if (!raProvider.isConnected)
            Expanded(
              child: LayoutBuilder(
                builder: (context, viewport) {
                  return SingleChildScrollView(
                    key: const ValueKey('ra-login-scroll'),
                    controller: _loginScrollController,
                    keyboardDismissBehavior:
                        ScrollViewKeyboardDismissBehavior.onDrag,
                    padding: EdgeInsets.only(bottom: keyboardInset + 16.r),
                    child: ConstrainedBox(
                      constraints: BoxConstraints(minWidth: viewport.maxWidth),
                      child: Align(
                        alignment: Alignment.topCenter,
                        child: ConstrainedBox(
                          constraints: const BoxConstraints(maxWidth: 960),
                          child: Padding(
                            padding: EdgeInsets.symmetric(horizontal: 16.r),
                            child: LayoutBuilder(
                              key: const ValueKey('ra-responsive-layout'),
                              builder: (context, content) {
                                final useColumns = content.maxWidth >= 720;
                                if (useColumns) {
                                  return Row(
                                    key: const ValueKey('ra-two-column-layout'),
                                    crossAxisAlignment:
                                        CrossAxisAlignment.start,
                                    children: [
                                      Expanded(
                                        flex: 10,
                                        child: _buildLandscapeConnectionForm(
                                          context,
                                          raProvider,
                                        ),
                                      ),
                                      SizedBox(width: 16.r),
                                      Expanded(
                                        flex: 11,
                                        child: _buildInfoBox(context),
                                      ),
                                    ],
                                  );
                                }
                                return Column(
                                  key: const ValueKey('ra-stacked-layout'),
                                  crossAxisAlignment:
                                      CrossAxisAlignment.stretch,
                                  children: [
                                    _buildLandscapeConnectionForm(
                                      context,
                                      raProvider,
                                    ),
                                    SizedBox(height: 16.r),
                                    _buildInfoBox(context),
                                  ],
                                );
                              },
                            ),
                          ),
                        ),
                      ),
                    ),
                  );
                },
              ),
            )
          else
            Expanded(
              child: RepaintBoundary(
                child: RADashboardHub(
                  scrollController: _dashboardScrollController,
                  logoutSelected: _logoutSelected,
                  onDisconnectRequested: _requestDisconnect,
                ),
              ),
            ),
        ],
      ),
    );
  }

  /// In-game achievements and Hardcore mode are switched directly in this tab
  /// (maintainer request): no dialog and no credentials to enter again. The
  /// settings button keeps the details (password once, sign-out, systems).
  Widget _buildInGameControls(BuildContext context, RetroAchievementsProvider raProvider) {
    final session = _session;
    final theme = Theme.of(context);
    final ready = session.initialized && !session.busy;
    final signedIn = session.authenticated && !session.tokenRejected;
    Widget toggle(Key key, String label, bool value, ValueChanged<bool>? onChanged) => Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Flexible(child: Text(label, style: theme.textTheme.labelMedium, overflow: TextOverflow.ellipsis)),
        Transform.scale(scale: 0.8, child: Switch.adaptive(key: key, value: value, onChanged: onChanged)),
      ],
    );
    final controls = Wrap(
        alignment: WrapAlignment.end,
        crossAxisAlignment: WrapCrossAlignment.center,
        spacing: 8.r,
        children: [
          toggle(const ValueKey('ra-tab-enabled'), AppLocale.raSessionSettings.getString(context),
            signedIn && session.preferences.enabled,
            !ready ? null : (value) {
              if (signedIn) {
                session.setEnabled(value);
              } else if (!raProvider.isConnected && _needsInGamePassword) {
                // The password field of this same form turns it on.
                _passwordFocus.requestFocus();
              } else {
                _openSessionSettings();
              }
            }),
          toggle(const ValueKey('ra-tab-hardcore'), AppLocale.raSessionHardcore.getString(context),
            session.preferences.hardcore, !ready ? null : (value) => session.setHardcore(value)),
          TextButton.icon(
            key: const ValueKey('ra-central-settings'), onPressed: _openSessionSettings,
            icon: Icon(Symbols.settings_rounded, size: 18.r),
            label: _buildSessionStatus(context, raProvider),
          ),
        ],
      );
    return Align(
      alignment: Alignment.centerRight,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        mainAxisSize: MainAxisSize.min,
        children: [
          controls,
          // A game already running keeps its mode until it is restarted.
          if (session.changesPending)
            Text(AppLocale.raSessionPending.getString(context),
              key: const ValueKey('ra-tab-pending'),
              style: theme.textTheme.bodySmall?.copyWith(fontSize: 9.r)),
        ],
      ),
    );
  }

  /// Always-visible state of the in-game session next to its button, so the
  /// player can see whether games will track achievements (Build 608 gave no
  /// indication outside the dialog).
  Widget _buildSessionStatus(BuildContext context, RetroAchievementsProvider raProvider) {
    final session = _session;
    if (!session.initialized) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final (String key, Color color) = session.tokenRejected
        ? (AppLocale.raSessionStatusRejected, theme.colorScheme.error)
        : !session.authenticated
            ? (raProvider.isConnected ? AppLocale.raSessionStatusPasswordNeeded
                : AppLocale.raSessionStatusSignedOut, theme.colorScheme.error)
            : session.preferences.enabled
                ? (AppLocale.raSessionStatusEnabled, Colors.green.shade400)
                : (AppLocale.raSessionStatusDisabled,
                    theme.colorScheme.onSurface.withValues(alpha: 0.7));
    return Padding(
      padding: EdgeInsets.only(left: 8.r),
      child: DecoratedBox(
        key: const ValueKey('ra-central-status'),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.14),
          borderRadius: BorderRadius.circular(10.r),
          border: Border.all(color: color.withValues(alpha: 0.55)),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: 8.r, vertical: 2.r),
          child: Text(key.getString(context),
            style: theme.textTheme.labelSmall?.copyWith(color: color)),
        ),
      ),
    );
  }

  Widget _buildFieldHighlight({
    required int slot,
    required ThemeData theme,
    required Widget child,
  }) {
    // Keep the same widget structure whether or not the slot is highlighted.
    // Inserting a wrapper only for the selected slot re-created the text
    // field's state as soon as the selection followed focus (tapping the API
    // key field), which closed its keyboard connection: the field looked
    // focused but the keyboard disappeared until it was tapped again.
    final selected = isSelected(slot);
    return DecoratedBox(
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(8.r),
        boxShadow: [
          if (selected)
            BoxShadow(
              color: theme.colorScheme.primary.withValues(alpha: 0.35),
              blurRadius: 6.r,
              spreadRadius: 1.r,
            ),
        ],
      ),
      child: child,
    );
  }

  Widget _buildLandscapeConnectionForm(
    BuildContext context,
    RetroAchievementsProvider raProvider,
  ) {
    final theme = Theme.of(context);
    final keyboardInset = MediaQuery.viewInsetsOf(context).bottom;
    // The in-game sign-in runs first and is just as much "loading".
    final busy = raProvider.isLoading || _session.busy;

    return Container(
      key: const ValueKey('ra-connection-card'),
      width: double.infinity,
      padding: EdgeInsets.all(16.r),
      decoration: BoxDecoration(
        color: LiquidGlassTheme.of(context).fill(context, GlassRole.bubble),
        borderRadius: BorderRadius.circular(12.r),
        border: Border.all(
          color: theme.colorScheme.primary.withValues(alpha: 0.2),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  (_signedInForGames ? AppLocale.raInGameConnected : AppLocale.raLogin).getString(context),
                  key: const ValueKey('ra-form-title'),
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.primary,
                    fontSize: 14.r,
                  ),
                ),
              ),
            ],
          ),
          if (_signedInForGames) ...[
            SizedBox(height: 8.r),
            Row(
              key: const ValueKey('ra-in-game-account'),
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Symbols.check_circle_rounded, size: 16.r, color: Colors.green.shade400),
                SizedBox(width: 6.r),
                Flexible(child: Text(_session.username,
                  style: theme.textTheme.titleSmall?.copyWith(fontWeight: FontWeight.bold, fontSize: 12.r))),
              ],
            ),
            SizedBox(height: 4.r),
            Text(
              AppLocale.raInGameConnectedHelp.getString(context),
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                fontSize: 9.r,
              ),
            ),
            SizedBox(height: 10.r),
            Text(
              AppLocale.raStatsOptional.getString(context),
              style: theme.textTheme.labelMedium?.copyWith(fontWeight: FontWeight.w600, fontSize: 10.r),
            ),
          ],
          if (_needsInGamePassword) ...[
            SizedBox(height: 6.r),
            // Two different secrets, each typed once (maintainer request):
            // say so before the fields, so the key is not pasted twice.
            Text(
              AppLocale.raTwoSecretsIntro.getString(context),
              key: const ValueKey('ra-two-secrets-intro'),
              textAlign: TextAlign.center,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                fontSize: 9.r,
              ),
            ),
          ],
          SizedBox(height: _signedInForGames ? 6.r : 12.r),
          // The account is already known once signed in for games.
          if (!_signedInForGames) Container(
            key: const ValueKey('ra-web-username-box'),
            constraints: BoxConstraints(maxWidth: 220.r),
            child: _buildFieldHighlight(
              slot: _usernameSlot,
              theme: theme,
              child: SizedBox(
                height: 32.r,
                child: TextFormField(
                  key: const ValueKey('ra-web-username'),
                  controller: _usernameController,
                  focusNode: _usernameFocus,
                  // ASCII usernames: iOS must not autocorrect, capitalize or
                  // turn a typed character into smart punctuation.
                  autocorrect: false,
                  enableSuggestions: false,
                  textCapitalization: TextCapitalization.none,
                  smartDashesType: SmartDashesType.disabled,
                  smartQuotesType: SmartQuotesType.disabled,
                  keyboardType: TextInputType.visiblePassword,
                  scrollPadding: EdgeInsets.only(bottom: keyboardInset + 72.r),
                  decoration: InputDecoration(
                    labelText: AppLocale.username.getString(context),
                    labelStyle: TextStyle(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                      fontSize: 10.r,
                    ),
                    floatingLabelStyle: TextStyle(
                      color: theme.colorScheme.primary,
                      fontSize: 10.r,
                      fontWeight: FontWeight.bold,
                    ),
                    hintText: AppLocale.enterUsername.getString(context),
                    hintStyle: TextStyle(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
                      fontSize: 10.r,
                    ),
                    filled: true,
                    fillColor: theme.colorScheme.onSurface.withValues(
                      alpha: 0.05,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide.none,
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide(
                        color: isSelected(_usernameSlot)
                            ? theme.colorScheme.primary
                            : theme.colorScheme.primary.withValues(alpha: 0.1),
                        width: isSelected(_usernameSlot) ? 2.r : 1.r,
                      ),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide(
                        color: theme.colorScheme.primary,
                        width: 1.r,
                      ),
                    ),
                  ),
                  enabled: !busy,
                  style: TextStyle(fontSize: 11.r),
                  textInputAction: TextInputAction.next,
                  onFieldSubmitted: (_) => (_needsInGamePassword ? _passwordFocus : _apiKeyFocus)
                      .requestFocus(),
                ),
              ),
            ),
          ),
          if (_needsInGamePassword) ...[
            SizedBox(height: 6.r),
            Container(
              // Keyed so the API key field below keeps its state when this
              // field disappears after the in-game sign-in.
              key: const ValueKey('ra-web-password-box'),
              constraints: BoxConstraints(maxWidth: 220.r),
              child: _buildFieldHighlight(
                slot: _passwordSlot,
                theme: theme,
                child: SizedBox(
                  height: 32.r,
                  child: TextFormField(
                    key: const ValueKey('ra-web-password'),
                    controller: _passwordController,
                    focusNode: _passwordFocus,
                    obscureText: _obscurePassword,
                    enableSuggestions: false,
                    autocorrect: false,
                    smartDashesType: SmartDashesType.disabled,
                    smartQuotesType: SmartQuotesType.disabled,
                    keyboardType: TextInputType.visiblePassword,
                    autofillHints: const [AutofillHints.password],
                    scrollPadding: EdgeInsets.only(bottom: keyboardInset + 120.r),
                    decoration: InputDecoration(
                      labelText: AppLocale.raAccountPasswordLabel.getString(context),
                      hintText: AppLocale.raAccountPasswordHint.getString(context),
                      hintStyle: TextStyle(
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
                        fontSize: 10.r,
                      ),
                      labelStyle: TextStyle(
                        color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                        fontSize: 10.r,
                      ),
                      floatingLabelStyle: TextStyle(
                        color: theme.colorScheme.primary,
                        fontSize: 10.r,
                        fontWeight: FontWeight.bold,
                      ),
                      filled: true,
                      fillColor: theme.colorScheme.onSurface.withValues(alpha: 0.05),
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8.r),
                        borderSide: BorderSide.none,
                      ),
                      enabledBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8.r),
                        borderSide: BorderSide(
                          color: isSelected(_passwordSlot)
                              ? theme.colorScheme.primary
                              : theme.colorScheme.primary.withValues(alpha: 0.1),
                          width: isSelected(_passwordSlot) ? 2.r : 1.r,
                        ),
                      ),
                      focusedBorder: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8.r),
                        borderSide: BorderSide(color: theme.colorScheme.primary, width: 1.r),
                      ),
                      suffixIcon: IconButton(
                        padding: EdgeInsets.zero,
                        icon: Icon(
                          size: 18.r,
                          _obscurePassword
                              ? Symbols.visibility_rounded
                              : Symbols.visibility_off_rounded,
                          color: theme.colorScheme.onSurface.withValues(alpha: 0.5),
                        ),
                        onPressed: () => setState(() => _obscurePassword = !_obscurePassword),
                      ),
                    ),
                    enabled: !busy,
                    style: TextStyle(fontSize: 11.r),
                    // "Next", never "Done": the keyboard key must not submit
                    // (Build 610 video: the Done key sent the form and the
                    // error stayed off screen).
                    textInputAction: TextInputAction.next,
                    onChanged: (_) => setState(() {}),
                    onFieldSubmitted: (_) => _apiKeyFocus.requestFocus(),
                  ),
                ),
              ),
            ),
            SizedBox(height: 4.r),
            // Live warning while the password field holds what looks like
            // the Web API key; otherwise what the password is for.
            if (raLooksLikeWebApiKey(_passwordController.text, knownKey: _apiKeyController.text))
              Text(
                AppLocale.raPasswordLooksLikeApiKey.getString(context),
                key: const ValueKey('ra-password-looks-like-key'),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.error,
                  fontSize: 9.r,
                  fontWeight: FontWeight.w600,
                ),
              )
            else
              Text(
                AppLocale.raUnifiedPasswordHelp.getString(context),
                key: const ValueKey('ra-unified-password-help'),
                textAlign: TextAlign.center,
                style: theme.textTheme.bodySmall?.copyWith(
                  color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
                  fontSize: 8.r,
                ),
              ),
          ],
          SizedBox(height: 6.r),
          Container(
            key: const ValueKey('ra-web-api-key-box'),
            constraints: BoxConstraints(maxWidth: 220.r),
            child: _buildFieldHighlight(
              slot: _apiKeySlot,
              theme: theme,
              child: SizedBox(
                height: 32.r,
                child: TextFormField(
                  key: const ValueKey('ra-web-api-key'),
                  controller: _apiKeyController,
                  focusNode: _apiKeyFocus,
                  obscureText: _obscureApiKey,
                  enableSuggestions: false,
                  autocorrect: false,
                  smartDashesType: SmartDashesType.disabled,
                  smartQuotesType: SmartQuotesType.disabled,
                  keyboardType: TextInputType.visiblePassword,
                  scrollPadding: EdgeInsets.only(bottom: keyboardInset + 96.r),
                  decoration: InputDecoration(
                    labelText: AppLocale.raApiKeyStatsLabel.getString(context),
                    suffixStyle: TextStyle(
                      color: theme.colorScheme.primary.withValues(alpha: 0.7),
                      fontSize: 12.r,
                    ),
                    labelStyle: TextStyle(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.7),
                      fontSize: 10.r,
                    ),
                    floatingLabelStyle: TextStyle(
                      color: theme.colorScheme.primary,
                      fontSize: 10.r,
                      fontWeight: FontWeight.bold,
                    ),
                    hintText: AppLocale.raEnterApiKey.getString(context),
                    hintStyle: TextStyle(
                      color: theme.colorScheme.onSurface.withValues(alpha: 0.4),
                      fontSize: 10.r,
                    ),
                    filled: true,
                    fillColor: theme.colorScheme.onSurface.withValues(
                      alpha: 0.05,
                    ),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide.none,
                    ),
                    enabledBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide(
                        color: isSelected(_apiKeySlot)
                            ? theme.colorScheme.primary
                            : theme.colorScheme.primary.withValues(alpha: 0.1),
                        width: isSelected(_apiKeySlot) ? 2.r : 1.r,
                      ),
                    ),
                    focusedBorder: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8.r),
                      borderSide: BorderSide(
                        color: theme.colorScheme.primary,
                        width: 1.r,
                      ),
                    ),
                    suffixIcon: IconButton(
                      padding: EdgeInsets.zero,
                      icon: Icon(
                        size: 18.r,
                        _obscureApiKey
                            ? Symbols.visibility_rounded
                            : Symbols.visibility_off_rounded,
                        color: theme.colorScheme.onSurface.withValues(
                          alpha: 0.5,
                        ),
                      ),
                      onPressed: () {
                        setState(() {
                          _obscureApiKey = !_obscureApiKey;
                        });
                      },
                    ),
                  ),
                  enabled: !busy,
                  style: TextStyle(fontSize: 11.r),
                  textInputAction: TextInputAction.done,
                  // The password warning compares against this key.
                  onChanged: _needsInGamePassword ? (_) => setState(() {}) : null,
                  onFieldSubmitted: (_) => _connectToRA(),
                ),
              ),
            ),
          ),
          SizedBox(height: 6.r),
          Container(
            constraints: BoxConstraints(maxWidth: 320.r),
            decoration: isSelected(_getKeySlot)
                ? BoxDecoration(
                    borderRadius: BorderRadius.circular(8.r),
                    boxShadow: [
                      BoxShadow(
                        color: theme.colorScheme.primary.withValues(
                          alpha: 0.35,
                        ),
                        blurRadius: 8.r,
                        spreadRadius: 1.r,
                      ),
                    ],
                  )
                : null,
            child: OutlinedButton.icon(
              onPressed: _openRaControlPanel,
              icon: Icon(Symbols.key_rounded, size: 14.r),
              label: Text(
                AppLocale.raGetApiKey.getString(context),
                style: TextStyle(fontSize: 11.r, fontWeight: FontWeight.w600),
              ),
              style: OutlinedButton.styleFrom(
                minimumSize: Size(double.infinity, 32.r),
                side: BorderSide(
                  color: theme.colorScheme.primary.withValues(alpha: 0.6),
                ),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(8.r),
                ),
              ),
            ),
          ),
          SizedBox(height: 4.r),
          Text(
            AppLocale.raApiKeyHelp.getString(context),
            textAlign: TextAlign.center,
            style: theme.textTheme.bodySmall?.copyWith(
              color: theme.colorScheme.onSurface.withValues(alpha: 0.65),
              fontSize: 8.r,
            ),
          ),
          SizedBox(height: 6.r),
          Container(
            constraints: BoxConstraints(maxWidth: 320.r),
            decoration: isSelected(submitSlot)
                ? BoxDecoration(
                    borderRadius: BorderRadius.circular(8.r),
                    boxShadow: [
                      BoxShadow(
                        color: theme.colorScheme.primary.withValues(alpha: 0.5),
                        blurRadius: 8.r,
                        spreadRadius: 2.r,
                      ),
                    ],
                  )
                : null,
            child: SizedBox(
              width: double.infinity,
              height: 32.r,
              child: ElevatedButton(
                onPressed: busy ? null : _connectToRA,
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.primary,
                  foregroundColor: theme.colorScheme.onPrimary,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8.r),
                  ),
                  elevation: 0,
                  padding: EdgeInsets.zero,
                ),
                child: raProvider.isLoading || _signingIn
                    ? SizedBox(
                        width: 16.r,
                        height: 16.r,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          valueColor: AlwaysStoppedAnimation<Color>(
                            theme.colorScheme.onPrimary,
                          ),
                        ),
                      )
                    : Text(
                        (_signedInForGames ? AppLocale.raAddApiKey : AppLocale.login).getString(context),
                        style: TextStyle(
                          fontSize: 14.r,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoBox(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      key: const ValueKey('ra-info-card'),
      width: double.infinity,
      padding: EdgeInsets.all(16.r),
      decoration: BoxDecoration(
        color: LiquidGlassTheme.of(context).fill(context, GlassRole.bubble),
        borderRadius: BorderRadius.circular(12.r),
        border: Border.all(
          color: theme.colorScheme.primary.withValues(alpha: 0.2),
          width: 1,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Symbols.emoji_events_rounded,
                color: theme.colorScheme.primary,
                size: 24.r,
              ),
              SizedBox(width: 12.r),
              Expanded(
                child: Text(
                  AppLocale.raWhatIs.getString(context),
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.primary,
                    fontSize: 14.r,
                  ),
                  softWrap: true,
                ),
              ),
            ],
          ),
          SizedBox(height: 6.r),
          Text(
            AppLocale.raDescription.getString(context),
            style: theme.textTheme.bodyMedium?.copyWith(
              color: theme.colorScheme.onSurface.withValues(alpha: 0.9),
              fontSize: 8.r,
            ),
            softWrap: true,
          ),
          SizedBox(height: 6.r),
          _buildInfoItem(
            context,
            Symbols.star_outline_rounded,
            AppLocale.raEarnPoints.getString(context),
          ),
          _buildInfoItem(
            context,
            Symbols.public_rounded,
            AppLocale.raGlobalLeaderboards.getString(context),
          ),
          _buildInfoItem(
            context,
            Symbols.history_rounded,
            AppLocale.raGameplayHistory.getString(context),
          ),
          SizedBox(height: 6.r),
          RichText(
            softWrap: true,
            text: TextSpan(
              style: theme.textTheme.bodySmall?.copyWith(
                fontStyle: FontStyle.italic,
                color: theme.colorScheme.onSurface.withValues(alpha: 0.6),
                fontSize: 8.r,
              ),
              children: [
                TextSpan(text: AppLocale.raCreateAccountAt.getString(context)),
                TextSpan(
                  text: 'retroachievements.org',
                  style: TextStyle(
                    color: theme.colorScheme.primary,
                    decoration: TextDecoration.underline,
                  ),
                  recognizer: TapGestureRecognizer()
                    ..onTap = () async {
                      final url = Uri.parse('https://retroachievements.org');
                      if (await canLaunchUrl(url)) {
                        await launchUrl(
                          url,
                          mode: LaunchMode.externalApplication,
                        );
                      }
                    },
                ),
                TextSpan(text: AppLocale.raToStartEarning.getString(context)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInfoItem(BuildContext context, IconData icon, String text) {
    final theme = Theme.of(context);
    return Padding(
      padding: EdgeInsets.only(bottom: 8.r),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(
            icon,
            size: 12.r,
            color: theme.colorScheme.primary.withValues(alpha: 0.7),
          ),
          SizedBox(width: 8.r),
          Expanded(
            child: Text(
              text,
              style: theme.textTheme.bodySmall?.copyWith(
                color: theme.colorScheme.onSurface.withValues(alpha: 0.8),
                fontSize: 8.r,
              ),
              softWrap: true,
            ),
          ),
        ],
      ),
    );
  }
}
