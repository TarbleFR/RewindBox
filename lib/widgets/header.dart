import 'package:flutter/material.dart';
import 'package:battery_plus/battery_plus.dart';
import 'package:material_symbols_icons/symbols.dart';
import 'package:neoplay_bridge/neoplay_bridge.dart';
import 'package:provider/provider.dart';

import 'dart:async';
import 'dart:io';

import 'package:neostation/l10n/neoplay_companion_locale.dart';
import 'package:neostation/l10n/rpcs3_ui_locale.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/services/controller_battery_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/services/permission_service.dart';
import 'package:neostation/services/rpcs3_internal_service.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/widgets/header_battery.dart';
import 'header_layout.dart';
import 'package:neostation/widgets/liquid_battery.dart';
import 'package:neostation/widgets/liquid_motion_clock.dart';
import 'package:neostation/l10n/liquid_motion_locale.dart';
import 'package:ui_refresh_rate/ui_refresh_rate.dart';
import 'package:neostation/widgets/header_sort_dropdown.dart';
import 'package:neostation/widgets/main_menu_tab_strip.dart';
import 'package:neostation/widgets/bumper_glyph.dart';
import 'package:neostation/widgets/notification_bell.dart';
import 'package:neostation/screens/app_screen.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/utils/time_format.dart';

import 'package:neostation/themes/chrome_surface.dart';
import 'package:neostation/widgets/neo_glass.dart';

import '../themes/corner_radii.dart';

class Header extends StatefulWidget {
  final int selectedTabIndex;
  final Function(int) onTabSelected;
  final ValueChanged<double>? onExtentChanged;

  const Header({
    super.key,
    required this.selectedTabIndex,
    required this.onTabSelected,
    this.onExtentChanged,
  });

  @override
  HeaderState createState() => HeaderState();
}

class HeaderState extends State<Header> with WidgetsBindingObserver {
  final Battery _battery = Battery();
  // Unknown until read: never show a level the device did not report.
  int _batteryLevel = -1;
  bool _batteryRetried = false;
  BatteryState? _batteryState;
  StreamSubscription<BatteryState>? _batteryStateSubscription;
  StreamSubscription<bool>? _powerSubscription;
  StreamSubscription<Rpcs3RuntimeState>? _rpcs3RuntimeSubscription;
  Timer? _jitStatusTimer;
  bool _jitActive =
      Rpcs3InternalService.jitPrepared ||
      Rpcs3InternalService.runtimeState.jitReady;
  bool _isTelevision = false;
  DateTime _now = DateTime.now();
  Timer? _timeUpdateTimer;
  late final List<FocusNode> _tabFocusNodes;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    if (Platform.isIOS) {
      _powerSubscription = UiRefreshRateChannel.powerChanges.listen(
        (low) => LiquidMotionClock.instance.lowPower = low,
        onError: (Object _) {},
      );
    }
    _tabFocusNodes = List.generate(
      NavTab.values.length,
      (_) => FocusNode(skipTraversal: true),
    );
    _getBatteryLevel();
    _listenToBatteryState();
    ControllerBatteryService.instance.attach();
    _rpcs3RuntimeSubscription = Rpcs3InternalService.runtimeStates.listen((
      state,
    ) {
      final active = state.jitReady || Rpcs3InternalService.jitPrepared;
      if (mounted && active && !_jitActive) {
        setState(() => _jitActive = true);
        _jitStatusTimer?.cancel();
        _jitStatusTimer = null;
      }
    });
    unawaited(_refreshJitStatus());
    _jitStatusTimer = Timer.periodic(const Duration(seconds: 2), (_) {
      unawaited(_refreshJitStatus());
    });
    _updateTime();
    _startTimeUpdateTimer();
    if (Platform.isAndroid) {
      PermissionService.isTelevision().then((isTV) {
        if (mounted && isTV) setState(() => _isTelevision = true);
      });
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _timeUpdateTimer?.cancel();
    _batteryStateSubscription?.cancel();
    _powerSubscription?.cancel();
    ControllerBatteryService.instance.detach();
    _rpcs3RuntimeSubscription?.cancel();
    _jitStatusTimer?.cancel();
    for (final node in _tabFocusNodes) {
      node.dispose();
    }
    super.dispose();
  }

  Future<void> _refreshJitStatus() async {
    if (!Platform.isIOS || _jitActive) return;
    final active = await Rpcs3InternalService.jitEnabledForUi();
    if (!mounted || !active) return;
    setState(() => _jitActive = true);
    _jitStatusTimer?.cancel();
    _jitStatusTimer = null;
  }

  /// Subscribes to real-time battery state changes (charging/discharging/full).
  void _listenToBatteryState() {
    try {
      _batteryStateSubscription = _battery.onBatteryStateChanged.listen((
        state,
      ) {
        if (mounted) {
          setState(() => _batteryState = state);
          unawaited(_getBatteryLevel());
        }
      });
    } catch (_) {
      // Some platforms don't expose battery state; ignore silently.
    }
  }

  void _updateTime() {
    if (mounted) {
      setState(() {
        _now = DateTime.now();
      });
      // Also update battery every minute
      _getBatteryLevel();
    }
  }

  void _startTimeUpdateTimer() {
    // Calculate how many seconds remain until the next minute
    final now = DateTime.now();
    final secondsUntilNextMinute = 60 - now.second;

    // Create initial timer that fires at the start of the next minute
    Future.delayed(Duration(seconds: secondsUntilNextMinute), () {
      if (mounted) {
        _updateTime();
        // Then create a periodic timer every 60 seconds
        _timeUpdateTimer = Timer.periodic(const Duration(minutes: 1), (timer) {
          if (mounted) {
            _updateTime();
          } else {
            timer.cancel();
          }
        });
      }
    });
  }

  Future<void> _getBatteryLevel() async {
    try {
      final level = await _battery.batteryLevel;
      // Reuse the same infrequent system read; no new poller or plugin.
      try {
        LiquidMotionClock.instance.lowPower =
            await _battery.isInBatterySaveMode;
      } catch (_) {
        /* Unsupported platforms retain the static fallback. */
      }
      if (mounted) {
        setState(() {
          // On Linux, 0% often indicates no battery (desktop), so we treat it as such
          if (Platform.isLinux && level == 0) {
            _batteryLevel = -1;
          } else {
            _batteryLevel = level;
          }
        });
      }
    } catch (e) {
      // Fallback for devices without battery (e.g., desktops)
      if (mounted) {
        setState(() {
          _batteryLevel = -1; // Indicate no battery
        });
      }
      // iOS reports an unknown state right after battery monitoring is
      // switched on: read again shortly instead of waiting a minute.
      if (!_batteryRetried && Platform.isIOS) {
        _batteryRetried = true;
        Future<void>.delayed(const Duration(seconds: 2), () {
          if (mounted) _getBatteryLevel();
        });
      }
    }
  }

  bool get _deviceCharging =>
      _batteryState == BatteryState.charging ||
      _batteryState == BatteryState.full;

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) unawaited(_getBatteryLevel());
  }

  /// Resolves the appropriate Material Symbols battery icon based on charge
  /// level and charging state.
  Color _getBatteryColor(dynamic customColors, int? level) {
    if (level == null || level == -1) {
      return customColors.batteryPower;
    }
    if (level > 20) {
      return customColors.batteryFull;
    } else if (level > 5) {
      return customColors.batteryMedium;
    } else {
      return customColors.batteryLow;
    }
  }

  /// The battery beside the clock: the connected controller's when there is
  /// one (gamepad icon, "—" when it does not report a level), else the
  /// device's.
  Widget _buildBattery(
    BuildContext context,
    dynamic customColors,
    List<NeoPlayControllerBattery> controllers,
  ) {
    final battery = HeaderBattery.choose(
      controllers: controllers,
      deviceLevel: _batteryLevel,
      deviceCharging: _deviceCharging,
    );
    if (battery == null) return const SizedBox.shrink();
    final color = battery.controller && battery.percent == null
        ? Theme.of(context).colorScheme.onSurface.withValues(alpha: 0.6)
        : _getBatteryColor(customColors, battery.percent);
    final text = battery.percent == null ? '—' : '${battery.percent}%';
    final row = Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        SizedBox(width: 12.r),
        if (battery.controller)
          Icon(Symbols.sports_esports, color: color, size: 16.r)
        else
          LiquidBattery(
            percent: battery.percent!,
            charging: battery.charging,
            width: 24.r,
            height: 13.r,
          ),
        if (battery.controller && battery.charging)
          Icon(Symbols.bolt, color: color, size: 12.r),
        SizedBox(width: 4.r),
        Text(
          text,
          style: TextStyle(
            color: color,
            fontSize: 12.r,
            fontWeight: FontWeight.w500,
            letterSpacing: 0.3.r,
          ),
        ),
      ],
    );
    if (!battery.controller) {
      return Semantics(
        key: const ValueKey('header-device-battery'),
        label: LiquidMotionLocale.deviceBattery(context),
        value: [
          text,
          if (battery.charging) NeoPlayCompanionLocale.get(context, 'charging'),
        ].join(', '),
        child: ExcludeSemantics(child: row),
      );
    }
    final label = NeoPlayCompanionLocale.get(context, 'battery');
    final controller = Tooltip(
      message: label,
      child: Semantics(
        key: const ValueKey('header-controller-battery'),
        label: label,
        value: battery.percent == null
            ? NeoPlayCompanionLocale.get(context, 'unavailable')
            : [
                text,
                if (battery.charging)
                  NeoPlayCompanionLocale.get(context, 'charging'),
              ].join(', '),
        child: ExcludeSemantics(child: row),
      ),
    );
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (_batteryLevel >= 0)
          Semantics(
            key: const ValueKey('header-device-battery'),
            label: LiquidMotionLocale.deviceBattery(context),
            value: [
              '$_batteryLevel%',
              if (_deviceCharging)
                NeoPlayCompanionLocale.get(context, 'charging'),
            ].join(', '),
            child: ExcludeSemantics(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SizedBox(width: 12.r),
                  LiquidBattery(
                    percent: _batteryLevel,
                    charging: _deviceCharging,
                    width: 24.r,
                    height: 13.r,
                  ),
                  SizedBox(width: 4.r),
                  Text(
                    '$_batteryLevel%',
                    style: TextStyle(color: color, fontSize: 12.r),
                  ),
                ],
              ),
            ),
          ),
        controller,
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final customColors = AppThemes.getCustomColors(context);
    final safe = MediaQuery.viewPaddingOf(context);
    final padding = EdgeInsets.fromLTRB(
      safe.left + 6.r,
      safe.top + 3.r,
      safe.right + 6.r,
      3.r,
    );
    return Consumer2<ThemeProvider, SqliteConfigProvider>(
      builder: (context, themeProvider, configProvider, child) => Padding(
        padding: padding,
        child: ResponsiveHeaderLayout(
          gap: 7.r,
          onExtentChanged: (height) =>
              widget.onExtentChanged?.call(height + padding.vertical),
          leading: KeyedSubtree(
            key: const ValueKey('header-controls'),
            child: widget.selectedTabIndex == AppTabs.systems
                ? FittedBox(fit: BoxFit.scaleDown, child: HeaderSortDropdown())
                : const SizedBox.shrink(),
          ),
          navigation: FittedBox(
            key: const ValueKey('tabs-container'),
            fit: BoxFit.scaleDown,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                _buildShoulderButton('LB', true),
                MainMenuTabStrip(
                  tabs: visibleNavTabs(configProvider.config),
                  selected: NavTab.values[widget.selectedTabIndex],
                  cellExtent: 36.r,
                  tabBuilder: (tab) => _buildTabButton(context, tab),
                  iconBuilder: (tab) => NavTabIcon(
                    spec: navTabSpec(tab),
                    tint: Theme.of(context).colorScheme.onSurface,
                  ),
                ),
                _buildShoulderButton('RB', false),
              ],
            ),
          ),
          status: FittedBox(
            key: const ValueKey('header-status'),
            fit: BoxFit.scaleDown,
            child: NeoGlass(
              role: GlassSurfaceRole.chrome,
              borderRadius:
                  Theme.of(context).extension<CornerRadii>()?.radiusExternal ??
                  BorderRadius.circular(14),
              padding: EdgeInsets.symmetric(horizontal: 10.r, vertical: 4.r),
              boxShadow: [
                BoxShadow(
                  color: Theme.of(
                    context,
                  ).colorScheme.shadow.withValues(alpha: 0.1),
                  blurRadius: 4.r,
                  offset: Offset(2.0.r, 2.0.r),
                ),
              ],
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const NotificationBell(),
                  SizedBox(width: 10.r),
                  Icon(
                    Symbols.schedule,
                    color: Theme.of(context).colorScheme.onSurface,
                    size: 14.r,
                  ),
                  SizedBox(width: 4.r),
                  Text(
                    formatClockTime(
                      _now,
                      use12Hour: configProvider.config.use12HourClock,
                    ),
                    style: TextStyle(
                      color: Theme.of(context).colorScheme.onSurface,
                      fontSize: 12.r,
                      fontWeight: FontWeight.w500,
                      letterSpacing: 0.3.r,
                    ),
                  ),
                  if (!_isTelevision)
                    ValueListenableBuilder<List<NeoPlayControllerBattery>>(
                      valueListenable:
                          ControllerBatteryService.instance.controllers,
                      builder: (context, controllers, _) =>
                          _buildBattery(context, customColors, controllers),
                    ),
                  if (Platform.isIOS && _jitActive) ...[
                    SizedBox(width: 8.r),
                    Tooltip(
                      message: 'JIT ${Rpcs3UiLocale.text(context, 'enabled')}',
                      child: Semantics(
                        label: 'JIT ${Rpcs3UiLocale.text(context, 'enabled')}',
                        child: Container(
                          key: const ValueKey('header-jit-active-dot'),
                          width: 8.r,
                          height: 8.r,
                          decoration: const BoxDecoration(
                            color: Color(0xFF22C55E),
                            shape: BoxShape.circle,
                          ),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  // Steam-style tab button.
  //
  // Most tabs use a webp asset; a Material symbol (Search, Library, the
  // consoles tab and its "+") is drawn by [NavTabIcon] at the same box size
  // and tint. The translated tab name is the button's accessibility label.
  Widget _buildTabButton(BuildContext context, NavTab tab) {
    final tabIndex = tab.index;
    final bool isSelected = tabIndex == widget.selectedTabIndex;
    final Color tint = Theme.of(context).colorScheme.onSurface;

    return Semantics(
      button: true,
      selected: isSelected,
      label: navTabLabel(context, tab),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          canRequestFocus: false,
          focusColor: Colors.transparent,
          hoverColor: Colors.transparent,
          highlightColor: Colors.transparent,
          focusNode: _tabFocusNodes[tabIndex],
          splashColor: Colors.transparent,
          onTap: () {
            SfxService().playNavSound();
            widget.onTabSelected(tabIndex);
          },
          child: Container(
            padding: EdgeInsets.all(8.r),
            child: NavTabIcon(spec: navTabSpec(tab), tint: tint),
          ),
        ),
      ),
    );
  }

  // Steam-style shoulder button (LB/RB)
  Widget _buildShoulderButton(String label, bool isLeft) {
    return Container(
      padding: EdgeInsets.symmetric(horizontal: 6.r, vertical: 2.r),
      child: BumperGlyph(isLeft: isLeft, size: 24.r),
    );
  }
}
