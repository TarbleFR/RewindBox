import 'dart:io';

import 'package:battery_plus_platform_interface/battery_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/themes/liquid_glass_theme.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/header.dart';
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

/// The main menu's navigation bar shows its icons only (maintainer, 9 Nov):
/// no tab name under any icon, the active one included, whatever the stored
/// "tab labels" preference and interface style. Icons, order, selection,
/// actions and the VoiceOver names stay; no empty label band remains.
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
    final roboto = File(
      '${File(Platform.resolvedExecutable).parent.parent.parent.path}/material_fonts/Roboto-Regular.ttf',
    );
    await (FontLoader('Roboto')
          ..addFont(roboto.readAsBytes().then((b) => ByteData.sublistView(b))))
        .load();
  });
  tearDownAll(() => SfxService().setEnabled(true));

  Future<List<int>> pumpHeader(
    WidgetTester tester,
    InterfaceStyleSettings settings,
    NavTab selected,
  ) async {
    const size = Size(956, 440);
    tester.view.physicalSize = size;
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final config = SqliteConfigProvider();
    addTearDown(config.dispose);
    final theme = ThemeProvider.testing(interfaceStyle: settings);
    addTearDown(theme.dispose);
    final taps = <int>[];
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
              data: const MediaQueryData(
                size: size,
                viewPadding: EdgeInsets.symmetric(horizontal: 59),
              ),
              child: Scaffold(
                body: Align(
                  alignment: Alignment.topCenter,
                  child: Header(
                    selectedTabIndex: selected.index,
                    onTabSelected: taps.add,
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 20));
    return taps;
  }

  Future<void> finish(WidgetTester tester) async {
    expect(tester.takeException(), isNull);
    await tester.pumpWidget(const SizedBox());
    await tester.pump(const Duration(minutes: 1));
  }

  final styles = {
    'Liquid Glass': InterfaceStyleSettings.defaults,
    'NeoStation': InterfaceStyleSettings.presetFor(InterfaceStyle.neoStation),
    'Glacier': InterfaceStyleSettings.presetFor(InterfaceStyle.glacier),
    'classic bar': const InterfaceStyleSettings(
      tabBarStyle: TabBarStyle.classic,
    ),
  };

  for (final MapEntry(key: name, value: style) in styles.entries) {
    testWidgets('$name: no tab name drawn, whatever the stored label mode', (
      tester,
    ) async {
      final semantics = tester.ensureSemantics();
      final heights = <TabLabelMode, double>{};
      for (final mode in TabLabelMode.values) {
        final taps = await pumpHeader(
          tester,
          style.copyWith(tabLabels: mode),
          NavTab.consoles,
        );
        final strip = find.byKey(const ValueKey('main-menu-tab-strip'));
        expect(strip, findsOneWidget);
        // No Text at all inside the bar: the icons are Icon/Image glyphs.
        expect(
          find.descendant(of: strip, matching: find.byType(Text)),
          findsNothing,
          reason: '$name, labels $mode',
        );
        final context = tester.element(strip);
        final tabs = visibleNavTabs(
          Provider.of<SqliteConfigProvider>(context, listen: false).config,
        );
        expect(tabs, navTabDisplayOrder, reason: 'every tab, in order (iOS)');
        double? lastLeft;
        for (final tab in tabs) {
          final label = navTabLabel(context, tab);
          expect(find.text(label), findsNothing, reason: '$label is drawn');
          // VoiceOver still reads the translated name, and the selection.
          expect(
            tester.getSemantics(find.bySemanticsLabel(label)),
            isSemantics(
              label: label,
              isButton: true,
              isSelected: tab == NavTab.consoles,
              hasTapAction: true,
            ),
          );
          final cell = find.byKey(ValueKey('main-menu-cell-${tab.name}'));
          final rect = tester.getRect(cell);
          if (lastLeft != null) expect(rect.left, greaterThan(lastLeft));
          lastLeft = rect.left;
          await tester.tap(cell);
          await tester.pump(const Duration(milliseconds: 50));
          expect(taps.last, tab.index, reason: 'tapping ${tab.name}');
        }
        heights[mode] = tester.getSize(strip).height;
      }
      // No label band left in any mode: the bar keeps one height.
      expect(heights.values.toSet(), hasLength(1), reason: '$heights');
      semantics.dispose();
      await finish(tester);
    }, variant: ios);
  }

  testWidgets('the icons sit in the middle of the bar', (tester) async {
    for (final style in styles.values) {
      await pumpHeader(
        tester,
        style.copyWith(tabLabels: TabLabelMode.always),
        NavTab.systems,
      );
      final strip = tester.getRect(
        find.byKey(const ValueKey('main-menu-tab-strip')),
      );
      final cell = tester.getRect(
        find.byKey(ValueKey('main-menu-cell-${NavTab.search.name}')),
      );
      expect(cell.center.dy, closeTo(strip.center.dy, 0.6));
    }
    await finish(tester);
  }, variant: ios);
}
