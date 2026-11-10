import 'dart:io';

import 'package:battery_plus_platform_interface/battery_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neoplay_bridge/neoplay_bridge.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/services/controller_battery_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';
import 'package:neostation/widgets/header.dart';
import 'package:neostation/widgets/notification_bell.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

class _Battery extends BatteryPlatform {
  @override
  Future<int> get batteryLevel async => 55;
  @override
  Future<bool> get isInBatterySaveMode async => false;
  @override
  Stream<BatteryState> get onBatteryStateChanged => const Stream.empty();
  @override
  Future<BatteryState> get batteryState async => BatteryState.discharging;
}

/// The main menu header keeps the view-mode pill, the navigation bar and the
/// status pill on one line on a landscape iPhone, controller connected, with
/// the widest navigation options; the status pill shows only what the user
/// keeps, and the JIT dot is gone.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final ios = TargetPlatformVariant.only(TargetPlatform.iOS);

  setUpAll(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger
        .setMockMethodCallHandler(
          const MethodChannel('neostation/neoplay/controller_battery'),
          (_) async => null,
        );
    SharedPreferences.setMockInitialValues({});
    BatteryPlatform.instance = _Battery();
    SfxService().setEnabled(false);
    await FlutterLocalization.instance.ensureInitialized();
    FlutterLocalization.instance.init(
      mapLocales: [MapLocale('fr', AppLocale.fr)],
      initLanguageCode: 'fr',
    );
    // Real font metrics: Flutter Test's Ahem font would overstate widths.
    final roboto = File(
      '${File(Platform.resolvedExecutable).parent.parent.parent.path}/material_fonts/Roboto-Regular.ttf',
    );
    await (FontLoader('Roboto')
          ..addFont(roboto.readAsBytes().then((b) => ByteData.sublistView(b))))
        .load();
  });
  tearDownAll(() => SfxService().setEnabled(true));
  tearDown(() => ControllerBatteryService.instance.controllers.value = []);

  Future<void> pumpHeader(
    WidgetTester tester,
    InterfaceStyleSettings settings, {
    Size size = const Size(956, 440),
    EdgeInsets safe = const EdgeInsets.symmetric(horizontal: 59),
    double textScale = 1,
  }) async {
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    await tester.binding.setSurfaceSize(size);
    addTearDown(() => tester.binding.setSurfaceSize(null));
    ControllerBatteryService.instance.controllers.value = [
      const NeoPlayControllerBattery(
        player: 1,
        name: 'DualSense',
        percent: 100,
        charge: 'discharging',
        low: false,
      ),
    ];
    final config = SqliteConfigProvider();
    addTearDown(config.dispose);
    final theme = ThemeProvider.testing(interfaceStyle: settings);
    addTearDown(theme.dispose);
    await tester.pumpWidget(
      ScreenUtilInit(
        designSize: const Size(640, 480),
        minTextAdapt: true,
        splitScreenMode: true,
        builder: (_, _) => MultiProvider(
          providers: [
            ChangeNotifierProvider.value(value: theme),
            ChangeNotifierProvider.value(value: config),
          ],
          child: MaterialApp(
            localizationsDelegates:
                FlutterLocalization.instance.localizationsDelegates,
            supportedLocales: FlutterLocalization.instance.supportedLocales,
            locale: const Locale('fr'),
            theme: applyLiquidGlass(AppThemes.darkTheme, settings),
            home: MediaQuery(
              data: MediaQueryData(
                size: size,
                viewPadding: safe,
                textScaler: TextScaler.linear(textScale),
              ),
              child: Scaffold(
                body: Align(
                  alignment: Alignment.topCenter,
                  child: Header(selectedTabIndex: 0, onTabSelected: (_) {}),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 20));
  }

  List<Rect> groups(WidgetTester tester) => [
    'header-controls',
    'tabs-container',
    'header-status',
  ].map((key) => tester.getRect(find.byKey(ValueKey(key)))).toList();

  Future<void> finish(WidgetTester tester) async {
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(minutes: 1));
  }

  for (final (name, settings) in [
    ('Liquid Glass defaults', InterfaceStyleSettings.defaults),
    (
      'classic bar, large icons and labels',
      const InterfaceStyleSettings(
        tabBarStyle: TabBarStyle.classic,
        tabIconSize: TabIconSize.large,
        tabLabels: TabLabelMode.always,
      ),
    ),
    (
      'NeoStation with LB/RB glyphs',
      InterfaceStyleSettings.presetFor(InterfaceStyle.neoStation),
    ),
  ]) {
    for (final (size, safe) in [
      (const Size(956, 440), const EdgeInsets.symmetric(horizontal: 59)),
      (const Size(852, 393), const EdgeInsets.symmetric(horizontal: 59)),
    ]) {
      testWidgets('one line on $size with a controller: $name', (tester) async {
        await pumpHeader(tester, settings, size: size, safe: safe);
        expect(
          find.byKey(const ValueKey('header-controller-battery')),
          findsOneWidget,
        );
        final rects = groups(tester);
        for (var i = 0; i < rects.length; i++) {
          expect(rects[i].left, greaterThanOrEqualTo(safe.left - .01));
          expect(
            rects[i].right,
            lessThanOrEqualTo(size.width - safe.right + .1),
          );
          for (var j = i + 1; j < rects.length; j++) {
            expect(rects[i].overlaps(rects[j]), isFalse);
          }
        }
        // Same row: every group centred on the same line.
        expect(rects[0].center.dy, closeTo(rects[1].center.dy, .01));
        expect(rects[1].center.dy, closeTo(rects[2].center.dy, .01));
        expect(
          find.byKey(const ValueKey('header-jit-active-dot')),
          findsNothing,
        );
        await finish(tester);
      }, variant: ios);
    }
  }

  testWidgets('large accessibility text keeps its size on a navigation row', (
    tester,
  ) async {
    await pumpHeader(
      tester,
      InterfaceStyleSettings.defaults,
      size: const Size(393, 852),
      safe: const EdgeInsets.only(top: 59),
      textScale: 1.4,
    );
    final rects = groups(tester);
    expect(rects[1].top, greaterThanOrEqualTo(rects[2].bottom - .01));
    await finish(tester);
  }, variant: ios);

  testWidgets('the status pill shows only the elements the user keeps', (
    tester,
  ) async {
    await pumpHeader(tester, InterfaceStyleSettings.defaults);
    expect(find.byKey(const ValueKey('header-clock')), findsOneWidget);
    expect(find.byType(NotificationBell), findsOneWidget);
    expect(find.byKey(const ValueKey('header-device-battery')), findsOneWidget);
    final full = tester.getSize(find.byKey(const ValueKey('header-status')));
    await finish(tester);

    await pumpHeader(
      tester,
      const InterfaceStyleSettings(
        showClock: false,
        showNotifications: false,
        showDeviceBattery: false,
      ),
    );
    expect(find.byKey(const ValueKey('header-clock')), findsNothing);
    expect(find.byType(NotificationBell), findsNothing);
    expect(find.byKey(const ValueKey('header-device-battery')), findsNothing);
    expect(
      find.byKey(const ValueKey('header-controller-battery')),
      findsOneWidget,
    );
    expect(
      tester.getSize(find.byKey(const ValueKey('header-status'))).width,
      lessThan(full.width),
    );
    await finish(tester);

    await pumpHeader(
      tester,
      const InterfaceStyleSettings(showControllerBattery: false),
    );
    expect(
      find.byKey(const ValueKey('header-controller-battery')),
      findsNothing,
    );
    expect(find.byKey(const ValueKey('header-device-battery')), findsOneWidget);
    await finish(tester);
  }, variant: ios);
}
