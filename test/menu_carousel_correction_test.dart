import 'dart:convert';
import 'dart:io';
// Inject real plugin interface readings in the full header fixture.
// ignore: depend_on_referenced_packages
import 'package:battery_plus_platform_interface/battery_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localization/flutter_localization.dart';
import 'package:flutter_screenutil/flutter_screenutil.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:neoplay_bridge/neoplay_bridge.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:neostation/l10n/app_locale.dart';
import 'package:neostation/themes/app_themes.dart';
import 'package:neostation/providers/sqlite_config_provider.dart';
import 'package:neostation/providers/theme_provider.dart';
import 'package:neostation/services/controller_battery_service.dart';
import 'package:neostation/services/sfx_service.dart';
import 'package:neostation/utils/nav_tabs.dart';
import 'package:neostation/widgets/header.dart';
import 'package:neostation/widgets/bumper_glyph.dart';
import 'package:neostation/widgets/main_menu_tab_strip.dart';
import 'package:neostation/widgets/mau_ali_tab_motion.dart';
import 'package:neostation/widgets/native_carousel.dart';

class _Battery extends BatteryPlatform {
  @override
  Future<int> get batteryLevel async => 90;
  @override
  Future<bool> get isInBatterySaveMode async => false;
  @override
  Stream<BatteryState> get onBatteryStateChanged => const Stream.empty();
  @override
  Future<BatteryState> get batteryState async => BatteryState.discharging;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late ThemeProvider theme;
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
    theme = await ThemeProvider.create();
    // Use the actual font metrics, not Flutter Test's fixed-width Ahem font,
    // when asserting whether all three production groups fit on one row.
    final roboto = File(
      '${File(Platform.resolvedExecutable).parent.parent.parent.path}/material_fonts/Roboto-Regular.ttf',
    );
    await (FontLoader('Roboto')
          ..addFont(roboto.readAsBytes().then((b) => ByteData.sublistView(b))))
        .load();
  });
  tearDownAll(() {
    theme.dispose();
    SfxService().setEnabled(true);
  });
  tearDown(() {
    ControllerBatteryService.instance.controllers.value = [];
  });

  test(
    'all author selection segments preserve full timing, contour, scale, rim and capsule pulse',
    () {
      final bundled = jsonDecode(
        File('assets/data/mau-ali-tab-motion.json').readAsStringSync(),
      );
      expect(MauAliTabMotion.data, bundled);
      expect(MauAliTabMotion.segments.length, 21);
      expect(
        MauAliTabMotion.durationFor('PnW'),
        const Duration(milliseconds: 550),
      );
      expect(MauAliTabMotion.durationFor('AnPr').inMicroseconds, 533333);
      final peak = MauAliTabMotion.sample('PnW', 8 / 33);
      expect(peak.scaleX, closeTo(188.29 / 161.29, .000001));
      expect(peak.scaleY, closeTo(205.29 / 161.29, .000001));
      expect(peak.containerScale, closeTo(62.509 / 60.909, .000001));
      expect(peak.fillOpacity, lessThan(.1));
      expect(peak.shape['v'][1][0], closeTo(8.515, .00001));
      expect(peak.rimEnd, isNot(MauAliTabMotion.sample('PnW', 0).rimEnd));
      for (final segment in MauAliTabMotion.segments) {
        final name = segment['cm'] as String;
        for (var i = 0; i <= 33; i++) {
          final frame = MauAliTabMotion.sample(name, i / 33);
          expect(frame.position.isFinite, isTrue);
          expect(frame.scaleX, inInclusiveRange(.9, 1.3));
          expect(frame.scaleY, inInclusiveRange(.85, 1.35));
          expect(
            frame.contour(const Size(36, 23)).getBounds().isFinite,
            isTrue,
          );
        }
      }
    },
  );

  testWidgets(
    'full selection deforms and retargets from its current position across all eight tabs',
    (tester) async {
      final selected = ValueNotifier(NavTab.systems);
      addTearDown(selected.dispose);
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          minTextAdapt: true,
          splitScreenMode: true,
          builder: (_, _) => MaterialApp(
            home: Scaffold(
              body: Center(
                child: ValueListenableBuilder<NavTab>(
                  valueListenable: selected,
                  builder: (_, tab, _) => MainMenuTabStrip(
                    tabs: NavTab.values,
                    selected: tab,
                    tabBuilder: (tab) => TextButton(
                      onPressed: () => selected.value = tab,
                      child: Text(tab.name),
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      selected.value = NavTab.airplay;
      await tester.pump();
      await tester.pump(const Duration(microseconds: 133333));
      final painter =
          tester
                  .widget<CustomPaint>(
                    find.byKey(const ValueKey('main-menu-tab-indicator')),
                  )
                  .painter!
              as MauAliSelectionPainter;
      expect(painter.scaleY, greaterThan(1.2));
      final before = tester
          .getRect(find.byKey(const ValueKey('main-menu-tab-indicator')))
          .left;
      selected.value = NavTab.consoles;
      await tester.pump();
      expect(
        tester
            .getRect(find.byKey(const ValueKey('main-menu-tab-indicator')))
            .left,
        closeTo(before, .01),
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .getRect(find.byKey(const ValueKey('main-menu-tab-indicator')))
            .left,
        closeTo(
          tester
              .getRect(find.byKey(const ValueKey('main-menu-cell-consoles')))
              .left,
          .01,
        ),
      );
      for (final tab in NavTab.values) {
        selected.value = tab;
        await tester.pumpAndSettle();
        expect(
          tester
              .getRect(find.byKey(const ValueKey('main-menu-tab-indicator')))
              .center
              .dx,
          closeTo(
            tester
                .getRect(find.byKey(ValueKey('main-menu-cell-${tab.name}')))
                .center
                .dx,
            .01,
          ),
        );
      }
      expect(tester.takeException(), isNull);
    },
  );

  for (final size in [
    const Size(956, 440),
    const Size(852, 393),
    const Size(1024, 768),
    const Size(1366, 1024),
    const Size(393, 852),
    const Size(320, 568),
  ]) {
    for (final scale in [1.0, 1.4]) {
      testWidgets(
        'compact production header aligns tabs and both batteries: $size / $scale',
        (tester) async {
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
          final safe = size.width >= 1000
              ? const EdgeInsets.only(top: 24)
              : size.width > size.height
              ? const EdgeInsets.symmetric(horizontal: 59)
              : const EdgeInsets.only(top: 59);
          double extent = 0;
          var selected = 0;
          final selections = <int>[];
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
                  supportedLocales:
                      FlutterLocalization.instance.supportedLocales,
                  locale: const Locale('fr'),
                  theme: AppThemes.darkTheme,
                  home: MediaQuery(
                    data: MediaQueryData(
                      size: size,
                      viewPadding: safe,
                      textScaler: TextScaler.linear(scale),
                    ),
                    child: Scaffold(
                      body: Align(
                        alignment: Alignment.topCenter,
                        child: StatefulBuilder(
                          builder: (context, setSelection) => Header(
                            selectedTabIndex: selected,
                            onTabSelected: (index) => setSelection(() {
                              selected = index;
                              selections.add(index);
                            }),
                            onExtentChanged: (h) => extent = h,
                          ),
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
          expect(
            find.byKey(const ValueKey('header-device-battery')),
            findsOneWidget,
          );
          expect(
            find.byKey(const ValueKey('header-controller-battery')),
            findsOneWidget,
          );
          expect(
            find.byKey(const ValueKey('main-menu-cell-airplay')),
            findsOneWidget,
          );
          final groups = [
            'header-controls',
            'tabs-container',
            'header-status',
          ].map((key) => tester.getRect(find.byKey(ValueKey(key)))).toList();
          for (var i = 0; i < groups.length; i++) {
            expect(groups[i].left, greaterThanOrEqualTo(safe.left));
            expect(
              groups[i].right,
              lessThanOrEqualTo(size.width - safe.right + .1),
            );
            for (var j = i + 1; j < groups.length; j++) {
              expect(groups[i].overlaps(groups[j]), isFalse);
            }
          }
          expect(find.byType(BumperGlyph), findsNothing);
          debugPrint('HEADER $size / $scale: $groups extent=$extent');
          if (size.width >= 1000 || (size.width >= 852 && scale == 1)) {
            expect(groups[0].center.dy, closeTo(groups[1].center.dy, .01));
            expect(groups[1].center.dy, closeTo(groups[2].center.dy, .01));
          }
          if (size == const Size(956, 440) && scale == 1) {
            for (final tab in navTabDisplayOrder) {
              await tester.tap(
                find.byKey(ValueKey('main-menu-cell-${tab.name}')),
              );
              await tester.pump();
              await tester.pump(const Duration(milliseconds: 600));
              expect(selected, tab.index);
              expect(
                tester
                    .getRect(
                      find.byKey(const ValueKey('main-menu-tab-indicator')),
                    )
                    .center
                    .dx,
                closeTo(
                  tester
                      .getRect(
                        find.byKey(ValueKey('main-menu-cell-${tab.name}')),
                      )
                      .center
                      .dx,
                  .1,
                ),
              );
            }
            expect(
              selections,
              navTabDisplayOrder.map((tab) => tab.index).toList(),
            );
          }
          expect(extent, greaterThan(0));
          expect(
            groups.map((r) => r.bottom).reduce((a, b) => a > b ? a : b),
            lessThanOrEqualTo(extent + .1),
          );
          expect(tester.takeException(), isNull);
          await tester.pumpWidget(const SizedBox());
          await tester.pump(
            const Duration(minutes: 1),
          ); // drain the existing minute alignment task
        },
        variant: ios,
      );
    }
  }

  testWidgets(
    'depth sorting paints the centre last and taps the actual centred artwork',
    (tester) async {
      final key = GlobalKey<NativeCarouselState>();
      final page = ValueNotifier(2.0);
      addTearDown(page.dispose);
      final d = ConsoleCoverFlowDelegate(
        page: page,
        indices: [0, 1, 2, 3, 4],
        extent: 200,
        reduced: false,
      );
      expect(d.paintOrder.last, 2);
      final left = MatrixUtils.transformRect(
        d.transformFor(1, const Size(844, 300)),
        const Rect.fromLTWH(0, 0, 200, 200),
      );
      final right = MatrixUtils.transformRect(
        d.transformFor(3, const Size(844, 300)),
        const Rect.fromLTWH(0, 0, 200, 200),
      );
      expect(left.width, closeTo(right.width, .001));
      expect(left.center.dx + right.center.dx, closeTo(844, .001));

      expect(d.transformFor(1, const Size(844, 300)).entry(3, 2), isNot(0));
      var tapped = -1;
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SizedBox(
              height: 280,
              child: NativeCarousel(
                key: key,
                perspective: true,
                itemCount: 8,
                initialIndex: 2,
                itemBuilder: (_, i) => GestureDetector(
                  onTap: () => tapped = i,
                  child: ColoredBox(
                    color: Colors.blue,
                    child: Text('Console $i'),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tapAt(const Offset(400, 140));
      await tester.pump();
      expect(tapped, 2);
      await tester.fling(
        find.byType(Scrollable).first,
        const Offset(-150, 0),
        1200,
      );
      await tester.pumpAndSettle();
      expect(key.currentState!.currentIndex, greaterThan(2));
      expect(tester.takeException(), isNull);
    },
  );
  testWidgets(
    'rapid repeated selection keeps the original bounded lens and capsule scale',
    (tester) async {
      final selected = ValueNotifier(NavTab.systems);
      addTearDown(selected.dispose);
      await tester.pumpWidget(
        ScreenUtilInit(
          designSize: const Size(640, 480),
          builder: (_, _) => MaterialApp(
            home: Scaffold(
              body: Center(
                child: ValueListenableBuilder<NavTab>(
                  valueListenable: selected,
                  builder: (_, tab, _) => MainMenuTabStrip(
                    tabs: NavTab.values,
                    selected: tab,
                    tabBuilder: (tab) => Text(tab.name),
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      for (var i = 0; i < 24; i++) {
        selected.value = i.isEven ? NavTab.settings : NavTab.systems;
        await tester.pump();
        await tester.pump(const Duration(microseconds: 133333));
        final painter =
            tester
                    .widget<CustomPaint>(
                      find.byKey(const ValueKey('main-menu-tab-indicator')),
                    )
                    .painter!
                as MauAliSelectionPainter;
        final capsule = tester.widget<Transform>(
          find.byKey(const ValueKey('main-menu-capsule-pulse')),
        );
        expect(painter.scaleX, lessThanOrEqualTo(1.18));
        expect(painter.scaleY, lessThanOrEqualTo(1.28));
        expect(capsule.transform.entry(0, 0), lessThanOrEqualTo(1.027));
      }
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
    },
  );
}
