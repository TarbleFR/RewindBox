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
  final FocusNode _usernameFocus = FocusNode();
  final FocusNode _apiKeyFocus = FocusNode();
  final ScrollController _loginScrollController = ScrollController();
  final ScrollController _dashboardScrollController = ScrollController();

  bool _logoutSelected = false;
  bool _scrollingToLogout = false;
  bool _obscureApiKey = true;
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

  @override
  List<FocusNode?> get selectionSlots => [
    _usernameFocus,
    _apiKeyFocus,
    null,
    null,
  ];

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
    if (selectedSlot == 2) {
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

  /// Web dashboard sign-in (username + Web API key). It no longer requires the
  /// in-game session: Build 608 refused every attempt locally with "Sign in here
  /// to enable in-game achievements" while the in-game session was signed out.
  Future<void> _connectToRA() async {
    final raProvider = context.read<RetroAchievementsProvider>();
    final session = _session;
    if (raProvider.isLoading) return;
    if (_usernameController.text.trim().isEmpty ||
        _apiKeyController.text.trim().isEmpty) {
      AppNotification.showNotification(
        context,
        AppLocale.pleaseCompleteAllFields.getString(context),
        type: NotificationType.error,
      );
      return;
    }
    final apiKey = _apiKeyController.text.trim();
    final success = await raProvider.connect(
      _usernameController.text,
      apiKey: apiKey,
    );
    if (!mounted) return;
    if (success) {
      AppNotification.showNotification(
        context,
        AppLocale.successConnectedRA.getString(context),
        type: NotificationType.success,
      );
      if (session.available && session.initialized && !session.authenticated) {
        // Statistics work; achievements in games still need the password.
        AppNotification.showNotification(context,
          AppLocale.raSessionSignInHint.getString(context), type: NotificationType.info);
      }
    } else if (raProvider.accountErrorKey != null) {
      AppNotification.showNotification(context,
        raProvider.accountErrorKey!.getString(context), type: NotificationType.error);
    } else if (raProvider.error != null) {
      AppNotification.showNotification(
        context,
        raProvider.error!,
        type: NotificationType.error,
      );
    }
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
    _usernameFocus.dispose();
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
          if (_session.available)
            Align(alignment: Alignment.centerRight, child: TextButton.icon(
              key: const ValueKey('ra-central-settings'), onPressed: _openSessionSettings,
              icon: const Icon(Symbols.settings_rounded),
              // Both parts may wrap: long translations at large text sizes
              // must not overflow the header.
              label: Row(mainAxisSize: MainAxisSize.min, children: [
                Flexible(flex: 3, child: Text(AppLocale.raSessionSettings.getString(context))),
                Flexible(flex: 2, child: _buildSessionStatus(context)),
              ]))),
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

  /// Always-visible state of the in-game session next to its button, so the
  /// player can see whether games will track achievements (Build 608 gave no
  /// indication outside the dialog).
  Widget _buildSessionStatus(BuildContext context) {
    final session = _session;
    if (!session.initialized) return const SizedBox.shrink();
    final theme = Theme.of(context);
    final (String key, Color color) = session.tokenRejected
        ? (AppLocale.raSessionStatusRejected, theme.colorScheme.error)
        : !session.authenticated
            ? (AppLocale.raSessionStatusSignedOut, theme.colorScheme.error)
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
                  (_session.available
                    ? AppLocale.raSessionWeb : AppLocale.raLogin).getString(context),
                  style: theme.textTheme.titleMedium?.copyWith(
                    fontWeight: FontWeight.bold,
                    color: theme.colorScheme.primary,
                    fontSize: 14.r,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: 12.r),
          Container(
            constraints: BoxConstraints(maxWidth: 220.r),
            child: _buildFieldHighlight(
              slot: 0,
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
                        color: isSelected(0)
                            ? theme.colorScheme.primary
                            : theme.colorScheme.primary.withValues(alpha: 0.1),
                        width: isSelected(0) ? 2.r : 1.r,
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
                  enabled: !raProvider.isLoading,
                  style: TextStyle(fontSize: 11.r),
                  textInputAction: TextInputAction.next,
                  onFieldSubmitted: (_) => _apiKeyFocus.requestFocus(),
                ),
              ),
            ),
          ),
          SizedBox(height: 6.r),
          Container(
            constraints: BoxConstraints(maxWidth: 220.r),
            child: _buildFieldHighlight(
              slot: 1,
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
                    labelText: AppLocale.raApiKey.getString(context),
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
                        color: isSelected(1)
                            ? theme.colorScheme.primary
                            : theme.colorScheme.primary.withValues(alpha: 0.1),
                        width: isSelected(1) ? 2.r : 1.r,
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
                  enabled: !raProvider.isLoading,
                  style: TextStyle(fontSize: 11.r),
                  textInputAction: TextInputAction.done,
                  onFieldSubmitted: (_) => _connectToRA(),
                ),
              ),
            ),
          ),
          SizedBox(height: 6.r),
          Container(
            constraints: BoxConstraints(maxWidth: 320.r),
            decoration: isSelected(2)
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
                onPressed: raProvider.isLoading ? null : _connectToRA,
                style: ElevatedButton.styleFrom(
                  backgroundColor: theme.colorScheme.primary,
                  foregroundColor: theme.colorScheme.onPrimary,
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(8.r),
                  ),
                  elevation: 0,
                  padding: EdgeInsets.zero,
                ),
                child: raProvider.isLoading
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
                        AppLocale.login.getString(context),
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
